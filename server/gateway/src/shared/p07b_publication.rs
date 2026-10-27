//! Recipient-side publication gate for the P07B projectile presentation lane.
//!
//! This module deliberately sits between the authoritative impact/flight
//! records and the native wire codecs.  It does not decide a collision and it
//! does not own an AoI book.  The integration layer supplies the current
//! recipient view (actor epochs and point-interest tokens), then drains the
//! bounded queue into `wire`, `terrain_wire`, or `impact_wire` in the normal
//! native order.
//!
//! The privacy rule is intentionally narrow:
//!
//! * a tracer start/stop carries a muzzle/flight point only when the current
//!   recipient sees the shooter in the current entity epoch;
//! * a vehicle impact carries shooter and target IDs only when both are seen in
//!   their current epochs;
//! * an anonymous terrain terminal may carry its terrain point only when this
//!   recipient has a current, matching point-interest token;
//! * a terminal that loses its view or point-interest before the reliable
//!   flush is suppressed, never rewritten as a different public event.
//!
//! The module stores source events, rather than already encoded bytes, while
//! they wait for reliable capacity.  Revalidation at drain time closes the
//! stale/late-join and hide-before-flush gaps.  The parent server must still
//! perform the final byte encoding and transport ACK bookkeeping.

use std::collections::{HashSet, VecDeque};
use std::io;

pub const MAX_ACTORS: usize = super::model::MAX_ACTORS;
pub const MAX_PENDING: usize = 64;
/// Four publication kinds per admitted shot, with room for the full six-seat
/// laboratory shot ceiling (960).  Keeping the ledger through a battle is
/// required for once-only semantics; it is cleared on `reset_battle`.
pub const MAX_SEEN: usize = 4096;
pub const MAX_POINT_INTEREST: usize = 32;
pub const MAX_COORDINATE: f32 = 100_000.0;

fn invalid(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

pub type Point = [f32; 3];

fn bounded(point: Point) -> bool {
    point.into_iter().all(|value| value.is_finite() && value.abs() <= MAX_COORDINATE)
}

fn direction(point: Point) -> bool {
    if !bounded(point) { return false; }
    let norm = point.into_iter().map(|value| f64::from(value).powi(2)).sum::<f64>();
    (norm - 1.0).abs() <= 0.0001
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct ActorRef {
    pub slot: usize,
    /// The current enter/create epoch for this actor at the recipient.  A
    /// stale source event with the same slot but an old epoch is rejected.
    pub epoch: u32,
}

impl ActorRef {
    pub fn validate(self) -> io::Result<()> {
        if self.slot >= MAX_ACTORS { return Err(invalid("publication actor slot")); }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct EventId {
    pub battle_epoch: u64,
    pub shot: u32,
    pub tick: u32,
    pub kind: EventKind,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum EventKind {
    TracerStart,
    TracerStop,
    TerrainTerminal,
    VehicleImpact,
}

impl EventId {
    pub fn validate(self) -> io::Result<()> {
        if self.battle_epoch == 0 || self.shot == 0 { return Err(invalid("publication event identity")); }
        Ok(())
    }
}

/// Opaque token issued by the authoritative geometry/interest calculation.
/// The token is intentionally not a position hash exposed to a client.  It
/// only lets the publication gate prove that the terminal belongs to the
/// recipient's current point-interest snapshot.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PointInterest {
    pub shot: u32,
    pub token: u64,
    /// Source enter/create epoch captured by the authoritative point query.
    /// This keeps an old hidden shooter from reusing a fresh-looking token
    /// after a leave/re-enter cycle.
    pub source_epoch: u32,
    pub observed_tick: u32,
    pub valid_until_tick: u32,
}

impl PointInterest {
    pub fn validate(self) -> io::Result<()> {
        if self.shot == 0 || self.token == 0 || self.source_epoch == 0 || self.observed_tick > self.valid_until_tick {
            return Err(invalid("publication point-interest bounds"));
        }
        Ok(())
    }
    fn matches(self, shot: u32, token: u64, source_epoch: u32, tick: u32, current_tick: u32) -> bool {
        self.shot == shot && self.token == token && self.source_epoch == source_epoch && self.observed_tick <= tick
            && tick <= self.valid_until_tick && current_tick <= self.valid_until_tick
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum SourceEvent {
    TracerStart {
        id: EventId,
        shooter: ActorRef,
        muzzle: Point,
        velocity: Point,
    },
    TracerStop {
        id: EventId,
        shooter: ActorRef,
        point: Point,
    },
    TerrainTerminal {
        id: EventId,
        shooter: ActorRef,
        point: Point,
        direction: Point,
        material: u8,
        effects: u8,
        point_token: u64,
    },
    VehicleImpact {
        id: EventId,
        shooter: ActorRef,
        target: ActorRef,
        point: Point,
        direction: Point,
        outcome: u8,
    },
}

impl SourceEvent {
    pub fn id(self) -> EventId {
        match self {
            Self::TracerStart { id, .. }
            | Self::TracerStop { id, .. }
            | Self::TerrainTerminal { id, .. }
            | Self::VehicleImpact { id, .. } => id,
        }
    }

    pub fn validate(self) -> io::Result<()> {
        let id = self.id();
        id.validate()?;
        match self {
            Self::TracerStart { id, shooter, muzzle, velocity } => {
                if id.kind != EventKind::TracerStart || id.tick == 0 { return Err(invalid("tracer start identity")); }
                shooter.validate()?;
                if !bounded(muzzle) || !bounded(velocity) { return Err(invalid("tracer start coordinates")); }
            }
            Self::TracerStop { id, shooter, point } => {
                if id.kind != EventKind::TracerStop { return Err(invalid("tracer stop identity")); }
                shooter.validate()?;
                if !bounded(point) { return Err(invalid("tracer stop point")); }
            }
            Self::TerrainTerminal { id, shooter, point, direction: ray, material, effects, point_token } => {
                if id.kind != EventKind::TerrainTerminal || point_token == 0 || material > 5 { return Err(invalid("terrain terminal identity")); }
                shooter.validate()?;
                if !bounded(point) || !direction(ray) { return Err(invalid("terrain terminal geometry")); }
                // `effects` is an original shell effect index.  The precise
                // table is checked by the native codec; this gate only keeps
                // the value byte-sized and opaque to visibility decisions.
                let _ = effects;
            }
            Self::VehicleImpact { id, shooter, target, point, direction: ray, outcome } => {
                if id.kind != EventKind::VehicleImpact || outcome > 3 { return Err(invalid("vehicle impact identity")); }
                shooter.validate()?;
                target.validate()?;
                if shooter.slot == target.slot || !bounded(point) || !direction(ray) { return Err(invalid("vehicle impact geometry")); }
            }
        }
        Ok(())
    }

    fn priority(self) -> u8 {
        match self {
            // A normal visible shot must win over optional anonymous FX when
            // the native reliable window is full.
            Self::TracerStart { .. } => 0,
            Self::TracerStop { .. } | Self::VehicleImpact { .. } => 1,
            Self::TerrainTerminal { .. } => 2,
        }
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum PublicEvent {
    TracerStart { id: EventId, shooter: usize, muzzle: Point, velocity: Point },
    TracerStop { id: EventId, shooter: usize, point: Point },
    /// `shooter` is `None` for the anonymous hidden-shooter path.  No source
    /// actor/vehicle ID is present in that branch by construction.
    TerrainTerminal { id: EventId, shooter: Option<usize>, point: Point, direction: Point, material: u8, effects: u8 },
    VehicleImpact { id: EventId, shooter: usize, target: usize, point: Point, direction: Point, outcome: u8 },
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Submit {
    Queued,
    SuppressedHidden,
    SuppressedStale,
    Backpressured,
    Duplicate,
}

#[derive(Clone, Debug)]
struct Pending {
    event: SourceEvent,
    priority: u8,
}

/// Per-recipient publication state.  It is deliberately independent of the
/// native `interest_wire::Book`: the integration layer can map its current
/// Enter/Create epoch and ACK state into `set_actor` without exposing those
/// transport IDs to the physics/impact domain.
#[derive(Clone, Debug)]
pub struct Recipient {
    recipient: usize,
    battle_epoch: u64,
    joined_tick: u32,
    current_tick: u32,
    visible: [bool; MAX_ACTORS],
    epochs: [u32; MAX_ACTORS],
    points: Vec<PointInterest>,
    pending: VecDeque<Pending>,
    seen: HashSet<EventId>,
    seen_order: VecDeque<EventId>,
    capacity: usize,
}

impl Recipient {
    pub fn new(recipient: usize, battle_epoch: u64, joined_tick: u32, capacity: usize) -> io::Result<Self> {
        if recipient >= MAX_ACTORS || battle_epoch == 0 || capacity == 0 || capacity > MAX_PENDING {
            return Err(invalid("publication recipient bounds"));
        }
        Ok(Self { recipient, battle_epoch, joined_tick, current_tick: joined_tick,
            visible: [false; MAX_ACTORS], epochs: [0; MAX_ACTORS], points: Vec::new(),
            pending: VecDeque::new(), seen: HashSet::new(), seen_order: VecDeque::new(), capacity })
    }

    pub fn recipient(&self) -> usize { self.recipient }
    pub fn battle_epoch(&self) -> u64 { self.battle_epoch }
    pub fn pending_len(&self) -> usize { self.pending.len() }
    pub fn current_tick(&self) -> u32 { self.current_tick }

    /// Move the recipient clock forward and expire point-interest snapshots.
    /// A backwards clock is rejected before any state mutation.
    pub fn advance_tick(&mut self, tick: u32) -> io::Result<()> {
        if tick < self.current_tick { return Err(invalid("publication clock regressed")); }
        self.current_tick = tick;
        self.points.retain(|interest| interest.valid_until_tick >= tick);
        Ok(())
    }

    /// Replace one actor's current visibility/epoch.  The epoch must advance
    /// when a hidden actor is re-entered; an old source event then fails closed.
    pub fn set_actor(&mut self, actor: ActorRef, visible: bool) -> io::Result<()> {
        actor.validate()?;
        if visible && actor.epoch == 0 { return Err(invalid("visible actor epoch")); }
        if actor.epoch < self.epochs[actor.slot] { return Err(invalid("publication actor epoch regressed")); }
        self.visible[actor.slot] = visible;
        self.epochs[actor.slot] = actor.epoch;
        Ok(())
    }

    pub fn actor_visible(&self, actor: ActorRef) -> bool {
        actor.slot < MAX_ACTORS && self.visible[actor.slot] && self.epochs[actor.slot] == actor.epoch
    }

    pub fn set_point_interest(&mut self, interest: PointInterest) -> io::Result<()> {
        interest.validate()?;
        if interest.observed_tick < self.joined_tick || interest.valid_until_tick < self.current_tick {
            return Err(invalid("stale publication point-interest"));
        }
        if let Some(existing) = self.points.iter_mut().find(|existing| existing.shot == interest.shot) {
            *existing = interest;
        } else {
            if self.points.len() >= MAX_POINT_INTEREST { return Err(invalid("publication point-interest bound")); }
            self.points.push(interest);
        }
        Ok(())
    }

    pub fn clear_point_interest(&mut self, shot: u32) {
        self.points.retain(|interest| interest.shot != shot);
    }

    /// Starts a new battle/late-join epoch.  Existing pending events and the
    /// once-only ledger are intentionally discarded: a reconnect must never
    /// replay old muzzle, impact, or terminal effects.
    pub fn reset_battle(&mut self, battle_epoch: u64, joined_tick: u32) -> io::Result<()> {
        if battle_epoch == 0 || battle_epoch <= self.battle_epoch || joined_tick < self.current_tick {
            return Err(invalid("publication battle epoch"));
        }
        self.battle_epoch = battle_epoch;
        self.joined_tick = joined_tick;
        self.current_tick = joined_tick;
        self.visible = [false; MAX_ACTORS];
        self.epochs = [0; MAX_ACTORS];
        self.points.clear();
        self.pending.clear();
        self.seen.clear();
        self.seen_order.clear();
        Ok(())
    }

    fn point_interest(&self, shot: u32, token: u64, source_epoch: u32, tick: u32) -> bool {
        self.points.iter().any(|interest| interest.matches(shot, token, source_epoch, tick, self.current_tick))
    }

    fn candidate(&self, event: SourceEvent) -> Result<Option<PublicEvent>, Submit> {
        let id = event.id();
        if id.battle_epoch != self.battle_epoch || id.tick < self.joined_tick || id.tick > self.current_tick {
            return Err(Submit::SuppressedStale);
        }
        let public = match event {
            SourceEvent::TracerStart { id, shooter, muzzle, velocity } => {
                if !self.actor_visible(shooter) { return Err(Submit::SuppressedHidden); }
                PublicEvent::TracerStart { id, shooter: shooter.slot, muzzle, velocity }
            }
            SourceEvent::TracerStop { id, shooter, point } => {
                if !self.actor_visible(shooter) { return Err(Submit::SuppressedHidden); }
                PublicEvent::TracerStop { id, shooter: shooter.slot, point }
            }
            SourceEvent::TerrainTerminal { id, shooter, point, direction, material, effects, point_token } => {
                if self.actor_visible(shooter) {
                    PublicEvent::TerrainTerminal { id, shooter: Some(shooter.slot), point, direction, material, effects }
                } else if self.point_interest(id.shot, point_token, shooter.epoch, id.tick) {
                    // The anonymous branch deliberately discards `shooter`.
                    PublicEvent::TerrainTerminal { id, shooter: None, point, direction, material, effects }
                } else {
                    return Err(Submit::SuppressedHidden);
                }
            }
            SourceEvent::VehicleImpact { id, shooter, target, point, direction, outcome } => {
                if !self.actor_visible(shooter) || !self.actor_visible(target) {
                    return Err(Submit::SuppressedHidden);
                }
                PublicEvent::VehicleImpact { id, shooter: shooter.slot, target: target.slot, point, direction, outcome }
            }
        };
        Ok(Some(public))
    }

    fn remember(&mut self, id: EventId) {
        self.seen.insert(id);
        self.seen_order.push_back(id);
        while self.seen_order.len() > MAX_SEEN {
            if let Some(old) = self.seen_order.pop_front() { self.seen.remove(&old); }
        }
    }

    fn forget(&mut self, id: EventId) {
        self.seen.remove(&id);
        self.seen_order.retain(|seen| *seen != id);
    }

    /// Validate and queue one source event.  The once-only mark is committed
    /// only after capacity/priority admission succeeds.
    pub fn submit(&mut self, event: SourceEvent) -> io::Result<Submit> {
        event.validate()?;
        let id = event.id();
        if self.seen.contains(&id) { return Ok(Submit::Duplicate); }
        match self.candidate(event) {
            Ok(Some(_)) => {}
            Ok(None) => return Err(invalid("publication candidate missing")),
            Err(result) => return Ok(result),
        }
        let priority = event.priority();
        if self.pending.len() >= self.capacity {
            if priority == 0 {
                // Preserve normal visible tracer priority by evicting the
                // oldest optional anonymous terrain terminal first.
                if let Some(index) = self.pending.iter().position(|pending| pending.priority > 0) {
                    if let Some(evicted) = self.pending.remove(index) { self.forget(evicted.event.id()); }
                } else {
                    return Ok(Submit::Backpressured);
                }
            } else {
                return Ok(Submit::Backpressured);
            }
        }
        self.pending.push_back(Pending { event, priority });
        self.remember(id);
        Ok(Submit::Queued)
    }

    /// Drain up to `limit` events.  Hidden/stale events are consumed and do
    /// not become available again; the caller may record the suppression in a
    /// diagnostic stream without sending any client bytes.
    pub fn drain(&mut self, limit: usize) -> Vec<PublicEvent> {
        let mut out = Vec::with_capacity(limit.min(self.pending.len()));
        while out.len() < limit {
            // Preserve native publication precedence even when a terrain
            // terminal was observed a few instructions before the normal
            // visible tracer start.  Equal-priority events remain FIFO.
            let Some(index) = self.pending.iter().enumerate()
                .min_by_key(|(_, pending)| pending.priority).map(|(index, _)| index) else { break; };
            let Some(pending) = self.pending.remove(index) else { break; };
            let Ok(Some(public)) = self.candidate(pending.event) else { continue; };
            out.push(public);
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn id(epoch: u64, shot: u32, tick: u32, kind: EventKind) -> EventId {
        EventId { battle_epoch: epoch, shot, tick, kind }
    }
    fn actor(slot: usize, epoch: u32) -> ActorRef { ActorRef { slot, epoch } }
    fn start(epoch: u64, shot: u32, tick: u32, source: ActorRef) -> SourceEvent {
        SourceEvent::TracerStart { id: id(epoch, shot, tick, EventKind::TracerStart), shooter: source,
            muzzle: [1., 2., 3.], velocity: [0., 0., 1.] }
    }
    fn terrain(epoch: u64, shot: u32, tick: u32, source: ActorRef, token: u64) -> SourceEvent {
        SourceEvent::TerrainTerminal { id: id(epoch, shot, tick, EventKind::TerrainTerminal), shooter: source,
            point: [10., 0., 20.], direction: [0., 1., 0.], material: 0, effects: 2, point_token: token }
    }

    fn ready(capacity: usize) -> Recipient {
        let mut recipient = Recipient::new(0, 1, 100, capacity).unwrap();
        recipient.advance_tick(100).unwrap();
        recipient.set_actor(actor(0, 1), true).unwrap();
        recipient.set_actor(actor(1, 7), true).unwrap();
        recipient
    }

    #[test]
    fn visible_tracer_contains_muzzle_and_is_drained_before_optional_terrain_fx() {
        let mut recipient = ready(2);
        recipient.set_actor(actor(1, 7), false).unwrap();
        recipient.set_point_interest(PointInterest { shot: 8, token: 55, source_epoch: 7, observed_tick: 100, valid_until_tick: 100 }).unwrap();
        assert_eq!(recipient.submit(terrain(1, 8, 100, actor(1, 7), 55)).unwrap(), Submit::Queued);
        recipient.set_actor(actor(1, 7), true).unwrap();
        assert_eq!(recipient.submit(start(1, 9, 100, actor(1, 7))).unwrap(), Submit::Queued);
        let events = recipient.drain(2);
        assert!(matches!(events[0], PublicEvent::TracerStart { shooter: 1, muzzle: [1., 2., 3.], .. }));
        assert!(matches!(events[1], PublicEvent::TerrainTerminal { shooter: Some(1), .. }));
    }

    #[test]
    fn hidden_shooter_terrain_is_anonymous_only_with_current_point_interest() {
        let mut recipient = ready(4);
        recipient.set_actor(actor(1, 7), false).unwrap();
        assert_eq!(recipient.submit(terrain(1, 3, 100, actor(1, 7), 91)).unwrap(), Submit::SuppressedHidden);
        recipient.set_point_interest(PointInterest { shot: 3, token: 91, source_epoch: 7, observed_tick: 100, valid_until_tick: 101 }).unwrap();
        let event = terrain(1, 3, 100, actor(1, 7), 91);
        assert_eq!(recipient.submit(event).unwrap(), Submit::Queued);
        let drained = recipient.drain(1);
        let [PublicEvent::TerrainTerminal { shooter: None, point, .. }] = drained.as_slice() else { panic!("anonymous terminal expected") };
        assert_eq!(*point, [10., 0., 20.]);
    }

    #[test]
    fn hidden_muzzle_and_vehicle_impact_never_cross_the_gate() {
        let mut recipient = ready(4);
        recipient.set_actor(actor(1, 7), false).unwrap();
        let stop = SourceEvent::TracerStop { id: id(1, 3, 100, EventKind::TracerStop), shooter: actor(1, 7), point: [10., 0., 20.] };
        assert_eq!(recipient.submit(stop).unwrap(), Submit::SuppressedHidden);
        let impact = SourceEvent::VehicleImpact { id: id(1, 4, 100, EventKind::VehicleImpact), shooter: actor(1, 7), target: actor(0, 1),
            point: [10., 0., 20.], direction: [0., 1., 0.], outcome: 1 };
        assert_eq!(recipient.submit(impact).unwrap(), Submit::SuppressedHidden);
        assert!(recipient.drain(4).is_empty());
    }

    #[test]
    fn stale_epochs_and_late_join_are_consumed_without_replay() {
        let mut recipient = ready(4);
        let old = start(1, 1, 100, actor(1, 7));
        assert_eq!(recipient.submit(old).unwrap(), Submit::Queued);
        recipient.set_actor(actor(1, 8), true).unwrap();
        assert!(recipient.drain(1).is_empty());
        // Old event was consumed; retrying it cannot resurrect the old muzzle.
        assert_eq!(recipient.submit(old).unwrap(), Submit::Duplicate);
        recipient.reset_battle(2, 200).unwrap();
        recipient.set_actor(actor(1, 9), true).unwrap();
        assert_eq!(recipient.submit(start(1, 2, 200, actor(1, 9))).unwrap(), Submit::SuppressedStale);
        assert_eq!(recipient.submit(start(2, 2, 200, actor(1, 9))).unwrap(), Submit::Queued);
    }

    #[test]
    fn backpressure_does_not_mark_rejected_events_and_visible_tracer_evicts_optional_fx() {
        let mut recipient = ready(1);
        recipient.set_actor(actor(1, 7), false).unwrap();
        recipient.set_point_interest(PointInterest { shot: 5, token: 5, source_epoch: 7, observed_tick: 100, valid_until_tick: 100 }).unwrap();
        assert_eq!(recipient.submit(terrain(1, 5, 100, actor(1, 7), 5)).unwrap(), Submit::Queued);
        // A second optional event is refused while the reliable slot is full.
        recipient.set_point_interest(PointInterest { shot: 6, token: 6, source_epoch: 7, observed_tick: 100, valid_until_tick: 100 }).unwrap();
        assert_eq!(recipient.submit(terrain(1, 6, 100, actor(1, 7), 6)).unwrap(), Submit::Backpressured);
        recipient.set_actor(actor(1, 7), true).unwrap();
        assert_eq!(recipient.submit(start(1, 7, 100, actor(1, 7))).unwrap(), Submit::Queued);
        let events = recipient.drain(2);
        assert_eq!(events.len(), 1);
        assert!(matches!(events[0], PublicEvent::TracerStart { shooter: 1, .. }));
        // The backpressured terminal may be admitted after capacity is freed.
        assert_eq!(recipient.submit(terrain(1, 6, 100, actor(1, 7), 6)).unwrap(), Submit::Queued);
    }

    #[test]
    fn duplicate_submission_and_expired_interest_are_once_only_and_fail_closed() {
        let mut recipient = ready(4);
        recipient.set_actor(actor(1, 7), false).unwrap();
        recipient.set_point_interest(PointInterest { shot: 8, token: 8, source_epoch: 7, observed_tick: 100, valid_until_tick: 100 }).unwrap();
        let event = terrain(1, 8, 100, actor(1, 7), 8);
        assert_eq!(recipient.submit(event).unwrap(), Submit::Queued);
        assert_eq!(recipient.submit(event).unwrap(), Submit::Duplicate);
        recipient.advance_tick(101).unwrap();
        assert!(recipient.drain(1).is_empty());
        assert_eq!(recipient.submit(event).unwrap(), Submit::Duplicate);
    }

    #[test]
    fn malformed_source_events_are_rejected_before_mutating_queue() {
        let mut recipient = ready(4);
        let before = recipient.pending_len();
        let malformed = SourceEvent::TerrainTerminal { id: id(1, 1, 100, EventKind::TerrainTerminal), shooter: actor(1, 7),
            point: [f32::NAN, 0., 0.], direction: [0., 1., 0.], material: 0, effects: 2, point_token: 1 };
        assert!(recipient.submit(malformed).is_err());
        assert_eq!(recipient.pending_len(), before);
    }
}
