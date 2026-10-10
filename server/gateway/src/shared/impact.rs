//! Bounded server-owned flight trace for the P06C impact gate.
//!
//! This module records the server-owned flight facts and the collision-only
//! boundary and source material facts. An explicitly enabled approximate
//! laboratory resolver can append its outcome and health transaction.
//! Geometry labels come from the supplied mesh, never from client hit claims.
//! They are not converted into armor thickness or HP mutation by this module.

use std::io;

use super::projectile::Projectile;
use super::{ap, collision, materials};

pub const RULESET_REVISION: &str = "wot-0.9.1-#717-ms1-ap-full-pose-v2";
pub const PROFILE: &str = "ms1_ap_2570";
pub const MS1_VEHICLE_COMPACT_ID: u32 = 3329;
pub const MS1_GUN_COMPACT_ID: u32 = 5892;
pub const MS1_AP_SHELL_COMPACT_ID: u32 = 2570;
pub const MAX_SEGMENTS_PER_SHOT: usize = 256;
// Admission + launch, segment/query pairs, one terminal collision batch, and
// nearest material record, optional AP resolution and terminal. The model admits only both actors'
// original 20-shell loadouts.
pub const MAX_EVENTS: usize = super::model::MAX_SHOTS
    * (2 + MAX_SEGMENTS_PER_SHOT * 2 + collision::MAX_CANDIDATES + 1 + 1 + 1);
pub const MAX_COORDINATE: f32 = 100_000.0;
pub const MAX_LIFETIME_SECONDS: f32 = 86_400.0;
pub const MAX_SEGMENT_LENGTH: f32 = 200_000.0;
pub const FLIGHT_ONLY_GEOMETRY_REVISION: &str = "flight-only-no-collision-v1";

fn invalid(reason: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, reason)
}

fn finite_vector(vector: [f32; 3]) -> bool {
    vector.iter().all(|value| value.is_finite() && value.abs() <= MAX_COORDINATE)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Stage {
    Admission,
    Launch,
    Segment,
    CollisionQuery,
    Intersection,
    MaterialContact,
    ApResolution,
    Terminal,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TerminalReason {
    RangeExpired,
    UnavailableImpactResolver,
    UnresolvedCollision,
    TestLabImpact,
}

/// The trace is intentionally typed and does not contain client-authored
/// positions, clocks, HP, armor or hit markers.
#[derive(Clone, Debug, PartialEq)]
pub enum Event {
    Admission {
        order: u32,
        battle_id: u64,
        shot_id: u32,
        server_tick: u32,
        shooter_slot: usize,
        vehicle_compact_id: u32,
        gun_compact_id: u32,
        shell_compact_id: u32,
        profile: &'static str,
        ammo_before: u16,
        ammo_after: u16,
        reload_ready: bool,
    },
    Launch {
        order: u32,
        battle_id: u64,
        shot_id: u32,
        server_tick: u32,
        origin: [f32; 3],
        velocity: [f32; 3],
        gravity: f32,
        max_distance: f32,
        max_lifetime_seconds: f32,
        pose_revision: &'static str,
    },
    Segment {
        order: u32,
        battle_id: u64,
        shot_id: u32,
        server_tick: u32,
        segment_tick_start: u32,
        segment_tick_end: u32,
        start: [f32; 3],
        end: [f32; 3],
        geometry_revision: &'static str,
    },
    CollisionQuery {
        order: u32,
        battle_id: u64,
        shot_id: u32,
        server_tick: u32,
        segment_order: u32,
        candidate_count: usize,
        geometry_revision: String,
        transform_revision: String,
    },
    Intersection {
        order: u32,
        battle_id: u64,
        shot_id: u32,
        server_tick: u32,
        query_order: u32,
        segment_order: u32,
        candidate_index: usize,
        triangle_id: u32,
        mesh: String,
        group: String,
        material: String,
        normal: [f32; 3],
        t: f32,
        geometry_revision: String,
        transform_revision: String,
    },
    /// Source facts for the nearest intersection in the computed query batch.
    /// Its referenced Intersection retains the raw winding normal; outward
    /// orientation and all penetration/damage outcomes remain unknown.
    MaterialContact {
        order: u32,
        battle_id: u64,
        shot_id: u32,
        server_tick: u32,
        query_order: u32,
        segment_order: u32,
        intersection_order: u32,
        candidate_index: usize,
        facts: materials::MaterialFacts,
    },
    /// Outcome supplied by the enabled laboratory resolver and bound to the
    /// retained nearest material. This records a World health transaction;
    /// appending the event does not itself mutate an actor or publish a packet.
    ApResolution {
        order: u32,
        battle_id: u64,
        shot_id: u32,
        server_tick: u32,
        attacker: usize,
        target: usize,
        material_order: u32,
        resolution: ap::Resolution,
        health_before: i16,
        health_after: i16,
    },
    Terminal {
        order: u32,
        battle_id: u64,
        shot_id: u32,
        server_tick: u32,
        reason: TerminalReason,
    },
}

impl Event {
    pub fn stage(&self) -> Stage {
        match self {
            Self::Admission { .. } => Stage::Admission,
            Self::Launch { .. } => Stage::Launch,
            Self::Segment { .. } => Stage::Segment,
            Self::CollisionQuery { .. } => Stage::CollisionQuery,
            Self::Intersection { .. } => Stage::Intersection,
            Self::MaterialContact { .. } => Stage::MaterialContact,
            Self::ApResolution { .. } => Stage::ApResolution,
            Self::Terminal { .. } => Stage::Terminal,
        }
    }

    pub fn order(&self) -> u32 {
        match self {
            Self::Admission { order, .. }
            | Self::Launch { order, .. }
            | Self::Segment { order, .. }
            | Self::CollisionQuery { order, .. }
            | Self::Intersection { order, .. }
            | Self::MaterialContact { order, .. }
            | Self::ApResolution { order, .. }
            | Self::Terminal { order, .. } => *order,
        }
    }

    pub fn shot_id(&self) -> u32 {
        match self {
            Self::Admission { shot_id, .. }
            | Self::Launch { shot_id, .. }
            | Self::Segment { shot_id, .. }
            | Self::CollisionQuery { shot_id, .. }
            | Self::Intersection { shot_id, .. }
            | Self::MaterialContact { shot_id, .. }
            | Self::ApResolution { shot_id, .. }
            | Self::Terminal { shot_id, .. } => *shot_id,
        }
    }
}

#[derive(Clone, Debug, Default, PartialEq)]
pub struct Trace {
    events: Vec<Event>,
    terminal_shots: Vec<u32>,
    next_order: u32,
    last_tick: u32,
    battle_id: Option<u64>,
}

impl Trace {
    pub fn new() -> Self { Self::default() }
    pub fn events(&self) -> &[Event] { &self.events }
    pub fn terminal_shots(&self) -> &[u32] { &self.terminal_shots }
    pub fn has_terminal(&self, shot_id: u32) -> bool { self.terminal_shots.contains(&shot_id) }

    fn next_order_value(&self) -> io::Result<u32> {
        if self.events.len() >= MAX_EVENTS || self.next_order == u32::MAX {
            return Err(invalid("impact trace event bound"));
        }
        self.next_order.checked_add(1).ok_or_else(|| invalid("impact trace order overflow"))
    }

    fn common(&self, battle_id: u64, shot_id: u32, tick: u32) -> io::Result<()> {
        if battle_id == 0 || self.battle_id.is_some_and(|known| known != battle_id)
            || shot_id == 0 || tick == 0 || tick < self.last_tick {
            return Err(invalid("impact trace identity or tick regression"));
        }
        Ok(())
    }

    fn push(&mut self, event: Event) -> io::Result<()> {
        let expected = self.next_order_value()?;
        if event.order() != expected {
            return Err(invalid("impact trace order"));
        }
        self.events.push(event);
        self.next_order = expected;
        Ok(())
    }

    pub fn admission(
        &mut self,
        battle_id: u64,
        shot_id: u32,
        server_tick: u32,
        shooter_slot: usize,
        ammo_before: u16,
        ammo_after: u16,
    ) -> io::Result<()> {
        self.common(battle_id, shot_id, server_tick)?;
        if shooter_slot >= 2 || ammo_before > crate::battle091::fire::MS1_INITIAL_AMMO
            || ammo_after > crate::battle091::fire::MS1_INITIAL_AMMO
            || ammo_after.checked_add(1) != Some(ammo_before) {
            return Err(invalid("impact admission transition"));
        }
        if self.events.iter().any(|event| event.shot_id() == shot_id) {
            return Err(invalid("duplicate impact shot identity"));
        }
        if self.events.iter().filter(|event| matches!(event, Event::Admission { .. })).count()
            >= super::model::MAX_SHOTS {
            return Err(invalid("impact shot bound"));
        }
        let order = self.next_order_value()?;
        self.push(Event::Admission {
            order, battle_id, shot_id, server_tick, shooter_slot,
            vehicle_compact_id: MS1_VEHICLE_COMPACT_ID,
            gun_compact_id: MS1_GUN_COMPACT_ID,
            shell_compact_id: MS1_AP_SHELL_COMPACT_ID,
            profile: PROFILE,
            ammo_before, ammo_after, reload_ready: true,
        })?;
        if self.battle_id.is_none() { self.battle_id = Some(battle_id); }
        self.last_tick = server_tick;
        Ok(())
    }

    pub fn launch(&mut self, battle_id: u64, projectile: &Projectile, server_tick: u32) -> io::Result<()> {
        self.common(battle_id, projectile.sequence, server_tick)?;
        let (admitted_slot, admitted_tick) = self.admission_facts(projectile.sequence)
            .ok_or_else(|| invalid("impact launch without admission"))?;
        if !matches!(self.last_stage(projectile.sequence), Some(Stage::Admission))
            || !finite_vector(projectile.origin) || !finite_vector(projectile.velocity)
            || !finite_vector(projectile.terminal)
            || !projectile.gravity.is_finite() || projectile.gravity <= 0.0
            || projectile.slot >= 2
            || projectile.slot != admitted_slot
            || server_tick != admitted_tick
            || !projectile.max_distance.is_finite() || projectile.max_distance <= 0.0
            || projectile.max_distance > MAX_COORDINATE
            || !projectile.flight_time.as_secs_f32().is_finite()
            || projectile.flight_time.as_secs_f32() <= 0.0
            || projectile.flight_time.as_secs_f32() > MAX_LIFETIME_SECONDS
        {
            return Err(invalid("impact launch facts"));
        }
        let order = self.next_order_value()?;
        self.push(Event::Launch {
            order, battle_id, shot_id: projectile.sequence, server_tick,
            origin: projectile.origin, velocity: projectile.velocity,
            gravity: projectile.gravity, max_distance: projectile.max_distance,
            max_lifetime_seconds: projectile.flight_time.as_secs_f32(),
            pose_revision: RULESET_REVISION,
        })?;
        self.last_tick = server_tick;
        Ok(())
    }

    pub fn segment(
        &mut self,
        battle_id: u64,
        shot_id: u32,
        server_tick: u32,
        segment_tick_start: u32,
        start: [f32; 3],
        end: [f32; 3],
    ) -> io::Result<()> {
        self.common(battle_id, shot_id, server_tick)?;
        let launch_tick = self.launch_tick(shot_id).ok_or_else(|| invalid("impact segment without launch"))?;
        let previous_segment_end = self.last_segment_end(shot_id);
        let segment_count = self.events.iter().rev()
            .take_while(|event| !matches!(event, Event::Launch { shot_id: id, .. } if *id == shot_id))
            .filter(|event| matches!(event, Event::Segment { shot_id: id, .. } if *id == shot_id)).count();
        if segment_tick_end(segment_tick_start, server_tick).is_err()
            || !finite_vector(start) || !finite_vector(end)
            || !self.flight_continuable(shot_id)
            || self.has_terminal(shot_id)
            || segment_count >= MAX_SEGMENTS_PER_SHOT
            || segment_tick_start < launch_tick
            || previous_segment_end.is_some_and(|previous| segment_tick_start < previous)
            || distance(start, end) > MAX_SEGMENT_LENGTH
        {
            return Err(invalid("impact segment facts"));
        }
        let order = self.next_order_value()?;
        self.push(Event::Segment {
            order, battle_id, shot_id, server_tick,
            segment_tick_start, segment_tick_end: server_tick,
            start, end, geometry_revision: FLIGHT_ONLY_GEOMETRY_REVISION,
        })?;
        self.last_tick = server_tick;
        Ok(())
    }

    pub fn terminal(
        &mut self,
        battle_id: u64,
        shot_id: u32,
        server_tick: u32,
        reason: TerminalReason,
    ) -> io::Result<()> {
        self.common(battle_id, shot_id, server_tick)?;
        let launch_tick = self.launch_tick(shot_id).ok_or_else(|| invalid("impact terminal without launch"))?;
        let previous_segment_end = self.last_segment_end(shot_id);
        let valid_stage = match reason {
            TerminalReason::TestLabImpact => self.last_stage(shot_id) == Some(Stage::ApResolution),
            TerminalReason::UnresolvedCollision =>
                matches!(self.last_stage(shot_id), Some(Stage::Intersection | Stage::MaterialContact)),
            TerminalReason::RangeExpired | TerminalReason::UnavailableImpactResolver =>
                self.flight_continuable(shot_id),
        };
        if self.has_terminal(shot_id) || !valid_stage
            || server_tick < launch_tick
            || previous_segment_end.is_some_and(|previous| server_tick < previous) {
            return Err(invalid("duplicate or unknown impact terminal"));
        }
        let order = self.next_order_value()?;
        self.push(Event::Terminal { order, battle_id, shot_id, server_tick, reason })?;
        self.terminal_shots.push(shot_id);
        self.last_tick = server_tick;
        Ok(())
    }

    /// Append one server outcome against this shot's immediately preceding
    /// nearest material record. Other shots may interleave. The target is the
    /// other actor pinned in the exact geometry pose tag for this tick.
    pub fn ap_resolution(&mut self, battle_id: u64, shot_id: u32,
        server_tick: u32, attacker: usize, target: usize, resolution: &ap::Resolution,
        health_before: i16, health_after: i16) -> io::Result<()> {
        self.common(battle_id, shot_id, server_tick)?;
        if attacker >= super::model::CAPACITY || target >= super::model::CAPACITY
            || attacker == target || self.has_terminal(shot_id)
            || self.admission_facts(shot_id).map(|(slot, _)| slot) != Some(attacker)
            || !(0..=90).contains(&health_before) || !(0..=90).contains(&health_after)
            || resolution.profile_revision != ap::PROFILE_REVISION
            || resolution.damage != (if resolution.outcome == ap::Outcome::Pierced { ap::DAMAGE } else { 0 })
            || health_after != health_before.saturating_sub(resolution.damage as i16).max(0) {
            return Err(invalid("AP resolution identity, damage or health transition"));
        }
        let (material_order, query, segment, intersection, facts) = match self.events.iter().rev()
            .find(|event| event.shot_id() == shot_id) {
            Some(Event::MaterialContact { order, battle_id: battle, server_tick: tick,
                query_order, segment_order, intersection_order, candidate_index: 0, facts, .. })
                if *battle == battle_id && *tick == server_tick =>
                (*order, *query_order, *segment_order, *intersection_order, facts),
            _ => return Err(invalid("AP resolution without latest nearest material")),
        };
        let pose_tag = format!("pose-v1:{target}:{server_tick}:");
        let target_bound = matches!(self.events.iter().find(|event| event.order() == intersection),
            Some(Event::Intersection { battle_id: battle, shot_id: shot, server_tick: tick,
                query_order, segment_order, candidate_index: 0, mesh, material, geometry_revision,
                transform_revision, .. })
                if *battle == battle_id && *shot == shot_id && *tick == server_tick
                && *query_order == query && *segment_order == segment
                && mesh.as_str() == facts.component.name() && material == &facts.name
                && geometry_revision == super::geometry::SOURCE_REVISION
                && transform_revision.strip_prefix(&pose_tag).is_some_and(|digest|
                    digest.len() == 64 && digest.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))));
        if !target_bound || resolution.armor != facts.effective.as_ref().and_then(|e| e.armor).map(f64::from)
            || [resolution.armor, resolution.incidence_degrees, resolution.effective_armor,
                resolution.nominal_power, resolution.normalization_degrees].into_iter().flatten()
                .any(|x| !x.is_finite() || x < 0.0)
            || !resolution.incidence_degrees.is_some_and(|x| x <= 90.0)
            || !resolution.nominal_power.is_some_and(|x| x <= 34.0) {
            return Err(invalid("AP resolution material, target pose or numerical facts"));
        }
        let calculated_plate = matches!(resolution.outcome, ap::Outcome::Pierced | ap::Outcome::NotPierced);
        if calculated_plate != (resolution.effective_armor.is_some() && resolution.normalization_degrees.is_some())
            || (!calculated_plate && (resolution.effective_armor.is_some() || resolution.normalization_degrees.is_some()))
            || (!matches!(resolution.outcome, ap::Outcome::Unsupported(_))
                && !resolution.armor.is_some_and(|x| x > 0.0)) {
            return Err(invalid("AP resolution incomplete outcome facts"));
        }
        // Reserve the matching terminal before mutating either order or rows.
        if self.events.len() + 2 > MAX_EVENTS || self.next_order.checked_add(2).is_none() {
            return Err(invalid("AP resolution trace capacity"));
        }
        let order = self.next_order_value()?;
        self.push(Event::ApResolution { order, battle_id, shot_id, server_tick, attacker, target,
            material_order, resolution: resolution.clone(), health_before, health_after })?;
        self.last_tick = server_tick;
        Ok(())
    }

    /// Query exactly the latest recorded segment with caller-owned world-space
    /// geometry. Query and all intersections commit together or not at all.
    /// Revisions identify the supplied facts; they do not verify native axes.
    /// A zero-candidate query permits further flight, not a whole-shot miss.
    /// Returned candidates are the same ordered batch committed to the trace,
    /// so the caller can stop at the first contact without another query.
    pub fn collision_query(&mut self, battle_id: u64, shot_id: u32,
        server_tick: u32, mesh: &collision::Mesh) -> io::Result<Vec<collision::Candidate>> {
        self.collision_batch(battle_id, shot_id, server_tick, mesh, None)
            .map(|(candidates, _)| candidates)
    }

    /// Bind immutable source material facts to the nearest computed hit. The
    /// query, every intersection and the nearest material event commit as one
    /// batch. No caller-supplied candidate, normal or material fact is accepted.
    /// A miss returns None and records no material event.
    pub fn collision_query_classified(&mut self, battle_id: u64, shot_id: u32,
        server_tick: u32, mesh: &collision::Mesh, catalog: &materials::Catalog)
        -> io::Result<(Vec<collision::Candidate>, Option<materials::MaterialFacts>)> {
        self.collision_batch(battle_id, shot_id, server_tick, mesh, Some(catalog))
    }

    fn collision_batch(&mut self, battle_id: u64, shot_id: u32,
        server_tick: u32, mesh: &collision::Mesh, catalog: Option<&materials::Catalog>)
        -> io::Result<(Vec<collision::Candidate>, Option<materials::MaterialFacts>)> {
        self.common(battle_id, shot_id, server_tick)?;
        let (segment_order, start, end) = match self.events.iter().rev()
            .find(|event| event.shot_id() == shot_id) {
            Some(Event::Segment { order, segment_tick_end, start, end, .. })
                if *segment_tick_end == server_tick => (*order, *start, *end),
            _ => return Err(invalid("collision query without current unqueried segment")),
        };
        let candidates = collision::query(mesh, start, end)?;
        let material = match (catalog, candidates.first()) {
            (Some(catalog), Some(nearest)) => Some(catalog.lookup(&nearest.mesh, &nearest.material)?),
            _ => None,
        };
        let added = 1 + candidates.len() + usize::from(material.is_some());
        // Classified contacts reserve both an optional AP outcome and terminal.
        // A future runtime adapter must commit query/terminal with its World
        // transaction so unrelated shots cannot consume that remaining slot.
        let closing_rows = 1 + usize::from(material.is_some());
        if self.events.len() + added + closing_rows > MAX_EVENTS
            || self.next_order.checked_add((added + closing_rows) as u32).is_none() {
            return Err(invalid("collision query trace capacity"));
        }
        let query_order = self.next_order_value()?;
        let mut batch = Vec::with_capacity(added);
        batch.push(Event::CollisionQuery { order: query_order, battle_id, shot_id, server_tick,
            segment_order, candidate_count: candidates.len(),
            geometry_revision: mesh.geometry_revision().into(),
            transform_revision: mesh.transform_revision().into() });
        for candidate in &candidates {
            let order = query_order + batch.len() as u32;
            batch.push(Event::Intersection { order, battle_id, shot_id, server_tick,
                query_order, segment_order, candidate_index: candidate.candidate_index,
                triangle_id: candidate.triangle_id, mesh: candidate.mesh.clone(), group: candidate.group.clone(),
                material: candidate.material.clone(), normal: candidate.normal, t: candidate.t,
                geometry_revision: mesh.geometry_revision().into(),
                transform_revision: mesh.transform_revision().into() });
        }
        if let Some(facts) = &material {
            batch.push(Event::MaterialContact { order: query_order + batch.len() as u32,
                battle_id, shot_id, server_tick, query_order, segment_order,
                intersection_order: query_order + 1, candidate_index: 0, facts: facts.clone() });
        }
        // All fallible validation precedes mutation; do not clone the complete
        // flight history for every segment in the full-ammo trace.
        self.events.extend(batch);
        self.next_order += added as u32;
        self.last_tick = server_tick;
        Ok((candidates, material))
    }

    fn flight_continuable(&self, shot_id: u32) -> bool {
        matches!(self.events.iter().rev().find(|event| event.shot_id() == shot_id),
            Some(Event::Launch { .. } | Event::Segment { .. }
                | Event::CollisionQuery { candidate_count: 0, .. }))
    }

    fn last_stage(&self, shot_id: u32) -> Option<Stage> {
        self.events.iter().rev().find(|event| event.shot_id() == shot_id).map(Event::stage)
    }

    fn launch_tick(&self, shot_id: u32) -> Option<u32> {
        self.events.iter().find_map(|event| match event {
            Event::Launch { shot_id: id, server_tick, .. } if *id == shot_id => Some(*server_tick),
            _ => None,
        })
    }

    fn admission_facts(&self, shot_id: u32) -> Option<(usize, u32)> {
        self.events.iter().find_map(|event| match event {
            Event::Admission { shot_id: id, shooter_slot, server_tick, .. } if *id == shot_id =>
                Some((*shooter_slot, *server_tick)),
            _ => None,
        })
    }

    fn last_segment_end(&self, shot_id: u32) -> Option<u32> {
        self.events.iter().rev().find_map(|event| match event {
            Event::Segment { shot_id: id, segment_tick_end, .. } if *id == shot_id => Some(*segment_tick_end),
            _ => None,
        })
    }
}

fn distance(start: [f32; 3], end: [f32; 3]) -> f32 {
    start.iter().zip(end).map(|(a, b)| (a - b) * (a - b)).sum::<f32>().sqrt()
}

fn segment_tick_end(start: u32, end: u32) -> io::Result<()> {
    if end > start { Ok(()) } else { Err(invalid("impact segment tick interval")) }
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::model::{self, tests::world};
    use std::time::{Duration, Instant};

    #[test]
    fn server_owned_stages_are_ordered_and_finite() {
        let now = Instant::now();
        let mut world = world(now);
        world.apply(0, 1, &[model::Command::Fire(crate::battle091::fire::Command::Shoot)], now).unwrap();
        let projectile = world.projectiles[0];
        world.impact.segment(world.id, 1, world.tick + 1, world.tick, projectile.origin, projectile.position_at(now + model::STEP)).unwrap();
        assert_eq!(world.impact.events().iter().map(Event::stage).collect::<Vec<_>>(),
            vec![Stage::Admission, Stage::Launch, Stage::Segment]);
    }

    #[test]
    fn fixed_profile_ids_and_event_budget_are_explicit() {
        assert_eq!(MS1_VEHICLE_COMPACT_ID, 3329);
        assert_eq!(MS1_GUN_COMPACT_ID, 5892);
        assert_eq!(MS1_AP_SHELL_COMPACT_ID, 2570);
        assert_eq!(MAX_SEGMENTS_PER_SHOT, 256);
        assert_eq!(MAX_EVENTS, 25_800);
    }

    #[test]
    fn cross_battle_rows_and_launch_before_admission_fail_closed() {
        let mut trace = Trace::new();
        let now = Instant::now();
        let world = world(now);
        assert!(trace.launch(123, &world.projectiles.get(0).copied().unwrap_or_else(|| {
            super::super::projectile::Projectile::launch(1, 0, &world.actors[0], now).unwrap()
        }), 1000).is_err());
        trace.admission(123, 1, 1000, 0, 20, 19).unwrap();
        assert!(trace.segment(124, 1, 1001, 1000, [0.; 3], [1.; 3]).is_err());
    }

    #[test]
    fn duplicate_shot_and_terminal_are_rejected() {
        let now = Instant::now();
        let world = world(now);
        let projectile = super::super::projectile::Projectile::launch(1, 0, &world.actors[0], now).unwrap();
        let mut trace = Trace::new();
        trace.admission(123, 1, 1000, 0, 20, 19).unwrap();
        assert!(trace.admission(123, 1, 1001, 0, 19, 18).is_err());
        trace.launch(123, &projectile, 1000).unwrap();
        trace.terminal(123, 1, 1001, TerminalReason::UnavailableImpactResolver).unwrap();
        assert!(trace.terminal(123, 1, 1002, TerminalReason::RangeExpired).is_err());
    }

    #[test]
    fn launch_binds_admission_slot_and_tick_without_partial_rows() {
        let now = Instant::now();
        let world = world(now);
        let projectile = super::super::projectile::Projectile::launch(1, 0, &world.actors[0], now).unwrap();
        let mut trace = Trace::new();
        trace.admission(123, 1, 1000, 0, 20, 19).unwrap();

        let mut wrong_slot = projectile;
        wrong_slot.slot = 1;
        let before = trace.clone();
        assert!(trace.launch(123, &wrong_slot, 1000).is_err());
        assert_eq!(trace, before);

        let before = trace.clone();
        assert!(trace.launch(123, &projectile, 1001).is_err());
        assert_eq!(trace, before);

        trace.launch(123, &projectile, 1000).unwrap();
        assert_eq!(trace.events().iter().filter(|event| event.stage() == Stage::Launch).count(), 1);
    }

    #[test]
    fn regression_nonfinite_and_post_terminal_segments_fail_closed() {
        let now = Instant::now();
        let world = world(now);
        let projectile = super::super::projectile::Projectile::launch(1, 0, &world.actors[0], now).unwrap();
        let mut trace = Trace::new();
        trace.admission(123, 1, 1000, 0, 20, 19).unwrap();
        trace.launch(123, &projectile, 1000).unwrap();
        let before = trace.clone();
        assert!(trace.segment(123, 1, 1000, 1000, [0.; 3], [1., f32::NAN, 0.]).is_err());
        assert_eq!(trace, before);
        trace.segment(123, 1, 1001, 1000, [0.; 3], [1.; 3]).unwrap();
        let before = trace.clone();
        assert!(trace.segment(123, 1, 1002, 1000, [0.; 3], [1.; 3]).is_err());
        assert_eq!(trace, before);
        trace.terminal(123, 1, 1001, TerminalReason::RangeExpired).unwrap();
        let before = trace.clone();
        assert!(trace.segment(123, 1, 1002, 1001, [0.; 3], [1.; 3]).is_err());
        assert_eq!(trace, before);
    }

    #[test]
    fn shared_world_emits_bounded_segments_and_one_range_terminal() {
        let now = Instant::now();
        let mut world = world(now);
        world.apply(0, 1, &[model::Command::Fire(crate::battle091::fire::Command::Shoot)], now).unwrap();
        let end = world.projectiles[0].end_at().unwrap();
        world.advance(now + model::STEP).unwrap();
        assert!(world.impact.events().iter().any(|event| event.stage() == Stage::Segment));
        world.advance(end + std::time::Duration::from_millis(100)).unwrap();
        assert_eq!(world.impact.terminal_shots(), &[1]);
        let count = world.impact.events().iter().filter(|event| event.stage() == Stage::Terminal).count();
        world.advance(end + std::time::Duration::from_millis(200)).unwrap();
        assert_eq!(world.impact.events().iter().filter(|event| event.stage() == Stage::Terminal).count(), count);
    }

    #[test]
    fn between_tick_launch_does_not_emit_prelaunch_segment_interval() {
        let now = Instant::now();
        let mut world = world(now);
        let fire_at = now + Duration::from_millis(250);
        world.apply(0, 1, &[model::Command::Fire(crate::battle091::fire::Command::Shoot)], fire_at).unwrap();
        world.advance(now + Duration::from_millis(300)).unwrap();
        let segment = world.impact.events().iter().find_map(|event| {
            if let Event::Segment { segment_tick_start, segment_tick_end, .. } = event {
                Some((*segment_tick_start, *segment_tick_end))
            } else { None }
        }).unwrap();
        assert_eq!(segment, (1002, 1003));
    }

    fn launched_trace() -> Trace {
        let now = Instant::now();
        let world = world(now);
        let projectile = super::super::projectile::Projectile::launch(1, 0, &world.actors[0], now).unwrap();
        let mut trace = Trace::new();
        trace.admission(123, 1, 1000, 0, 20, 19).unwrap();
        trace.launch(123, &projectile, 1000).unwrap();
        trace
    }

    fn two_planes() -> collision::Mesh {
        collision::Mesh::new(
            vec![
                [0.0, -1.0, -1.0], [0.0, 1.0, -1.0], [0.0, 0.0, 1.0],
                [2.0, -1.0, -1.0], [2.0, 1.0, -1.0], [2.0, 0.0, 1.0],
            ],
            vec![
                collision::Triangle { triangle_id: 42, a: 3, b: 4, c: 5,
                    mesh: "synthetic".into(), group: "far".into(), material: "test-b".into() },
                collision::Triangle { triangle_id: 7, a: 0, b: 1, c: 2,
                    mesh: "synthetic".into(), group: "near".into(), material: "test-a".into() },
            ],
            "synthetic-geometry-v1", "synthetic-world-identity-v1").unwrap()
    }

    fn material_planes(component: &str, material: &str, reverse_near: bool) -> collision::Mesh {
        collision::Mesh::new(
            vec![
                [0.0, -1.0, -1.0], [0.0, 1.0, -1.0], [0.0, 0.0, 1.0],
                [2.0, -1.0, -1.0], [2.0, 1.0, -1.0], [2.0, 0.0, 1.0],
            ],
            vec![
                // The farther triangle has the smaller ID and comes first in
                // storage: classification must follow query distance order.
                collision::Triangle { triangle_id: 2, a: 3, b: 4, c: 5,
                    mesh: "Gun_02".into(), group: "far".into(), material: "armor_3".into() },
                collision::Triangle { triangle_id: 7, a: 0,
                    b: if reverse_near { 2 } else { 1 }, c: if reverse_near { 1 } else { 2 },
                    mesh: component.into(), group: "near".into(), material: material.into() },
            ],
            "synthetic-material-planes-v1", "synthetic-world-identity-v1").unwrap()
    }

    fn tagged_plate(component: &str, label: &str, tag: &str) -> collision::Mesh {
        collision::Mesh::new(vec![[0.0,-1.0,-1.0],[0.0,1.0,-1.0],[0.0,0.0,1.0]],
            vec![collision::Triangle { triangle_id:7,a:0,b:1,c:2,mesh:component.into(),
                group:"synthetic-tag-contract".into(),material:label.into() }],
            super::super::geometry::SOURCE_REVISION,tag).unwrap()
    }
    fn ap_contact(component: &str, label: &str, tag: &str) -> (Trace,ap::Resolution) {
        let bundle=super::super::geometry::tests::bundle();
        let mesh=tagged_plate(component,label,tag);
        let mut trace=launched_trace();
        trace.segment(123,1,1001,1000,[-1.0,0.0,0.0],[3.0,0.0,0.0]).unwrap();
        let (hits,facts)=trace.collision_query_classified(123,1,1001,&mesh,bundle.materials()).unwrap();
        let resolution=ap::resolve(ap::Input { material:facts.as_ref().unwrap(),
            segment_direction:[4.0,0.0,0.0],winding_normal:hits[0].normal,distance:10.0 }).unwrap();
        (trace,resolution)
    }
    fn ap_tag(target: usize,tick:u32) -> String { format!("pose-v1:{target}:{tick}:{}","0".repeat(64)) }

    #[test] fn ap_event_pins_nearest_material_and_health_before_terminal() {
        let (mut trace,resolution)=ap_contact("Hull","armor_1",&ap_tag(1,1001));
        let material_order=trace.events().last().unwrap().order();
        let before=trace.clone();
        assert!(trace.terminal(123,1,1001,TerminalReason::TestLabImpact).is_err());
        assert_eq!(trace,before);
        trace.ap_resolution(123,1,1001,0,1,&resolution,90,60).unwrap();
        assert!(matches!(trace.events().last(),Some(Event::ApResolution {
            attacker:0,target:1,material_order:pin,health_before:90,health_after:60,resolution:r,.. })
            if *pin==material_order && *r==resolution));
        let before=trace.clone();
        assert!(trace.ap_resolution(123,1,1001,0,1,&resolution,60,30).is_err());
        assert!(trace.terminal(123,1,1001,TerminalReason::UnresolvedCollision).is_err());
        assert!(trace.terminal(123,1,1001,TerminalReason::RangeExpired).is_err());
        assert!(trace.segment(123,1,1002,1001,[3.0,0.0,0.0],[4.0,0.0,0.0]).is_err());
        assert_eq!(trace,before);
        trace.terminal(123,1,1001,TerminalReason::TestLabImpact).unwrap();
        let before=trace.clone();
        assert!(trace.ap_resolution(123,1,1001,0,1,&resolution,90,60).is_err());
        assert!(trace.terminal(123,1,1001,TerminalReason::TestLabImpact).is_err());
        assert_eq!(trace,before); assert_eq!(trace.terminal_shots(),&[1]);
    }
    #[test] fn ap_wrong_identity_health_and_forged_fields_fail_atomically() {
        let (original,resolution)=ap_contact("Hull","armor_1",&ap_tag(1,1001));
        for (battle,shot,tick,attacker,target) in [(0,1,1001,0,1),(124,1,1001,0,1),
            (123,0,1001,0,1),(123,2,1001,0,1),(123,1,1000,0,1),(123,1,1002,0,1),
            (123,1,1001,1,0),(123,1,1001,0,0),(123,1,1001,0,2)] {
            let mut trace=original.clone();
            assert!(trace.ap_resolution(battle,shot,tick,attacker,target,&resolution,90,60).is_err());
            assert_eq!(trace,original);
        }
        for (before,after) in [(-1,0),(90,-1),(91,61),(90,91),(90,59),(90,90)] {
            let mut trace=original.clone();
            assert!(trace.ap_resolution(123,1,1001,0,1,&resolution,before,after).is_err());
            assert_eq!(trace,original);
        }
        for which in 0..8 {
            let mut bad=resolution.clone();
            match which {0=>bad.profile_revision="unknown",1=>bad.armor=Some(19.0),
                2=>bad.incidence_degrees=Some(f64::NAN),3=>bad.nominal_power=Some(f64::INFINITY),
                4=>bad.damage=0,5=>bad.damage=31,6=>bad.effective_armor=None,
                7=>bad.normalization_degrees=None,_=>unreachable!()}
            let mut trace=original.clone();
            assert!(trace.ap_resolution(123,1,1001,0,1,&bad,90,60).is_err()); assert_eq!(trace,original);
        }
        let mut lethal=original.clone();
        lethal.ap_resolution(123,1,1001,0,1,&resolution,20,0).unwrap();
    }
    #[test] fn ap_unbound_target_pose_and_wrong_material_stage_are_rejected() {
        for tag in [ap_tag(0,1001),ap_tag(1,1002),"synthetic-no-target".into(),
            "pose-v1:1:1001:00".into(),format!("pose-v1:1:1001:{}","z".repeat(64))] {
            let (mut trace,resolution)=ap_contact("Hull","armor_1",&tag);
            let before=trace.clone();
            assert!(trace.ap_resolution(123,1,1001,0,1,&resolution,90,60).is_err()); assert_eq!(trace,before);
        }
        let (_,resolution)=ap_contact("Hull","armor_1",&ap_tag(1,1001));
        let mut trace=launched_trace(); let before=trace.clone();
        assert!(trace.ap_resolution(123,1,1000,0,1,&resolution,90,60).is_err()); assert_eq!(trace,before);
        trace.segment(123,1,1001,1000,[-1.0,0.0,0.0],[3.0,0.0,0.0]).unwrap();
        trace.collision_query(123,1,1001,&two_planes()).unwrap(); let before=trace.clone();
        assert!(trace.ap_resolution(123,1,1001,0,1,&resolution,90,60).is_err()); assert_eq!(trace,before);
    }
    #[test] fn ap_unsupported_surface_records_zero_health_change_with_explicit_outcome() {
        let (mut trace,resolution)=ap_contact("Gun_02","armor_1",&ap_tag(1,1001));
        assert!(matches!(resolution.outcome,ap::Outcome::Unsupported(_)));
        let before=trace.clone();
        assert!(trace.ap_resolution(123,1,1001,0,1,&resolution,90,60).is_err()); assert_eq!(trace,before);
        trace.ap_resolution(123,1,1001,0,1,&resolution,90,90).unwrap();
        trace.terminal(123,1,1001,TerminalReason::TestLabImpact).unwrap();
        let (mut trace,mut resolution)=ap_contact("Hull","armor_1",&ap_tag(1,1001));
        resolution.outcome=ap::Outcome::NotPierced;resolution.damage=0;resolution.nominal_power=Some(0.0);
        trace.ap_resolution(123,1,1001,0,1,&resolution,90,90).unwrap();
        trace.terminal(123,1,1001,TerminalReason::TestLabImpact).unwrap();
    }
    #[test] fn ap_material_and_nearest_intersection_binding_cannot_be_substituted() {
        let (original,resolution)=ap_contact("Hull","armor_1",&ap_tag(1,1001));
        for which in 0..5 {
            let mut trace=original.clone();
            if which < 2 {
                match trace.events.last_mut().unwrap() {
                    Event::MaterialContact { candidate_index,query_order,.. } => {
                        if which==0 {*candidate_index=1;} else {*query_order+=1;}
                    }, _=>unreachable!(),
                }
            } else {
                let row=trace.events.iter_mut().find(|e| matches!(e,Event::Intersection{..})).unwrap();
                match row {
                    Event::Intersection { material,geometry_revision,transform_revision,.. }=>match which {
                        2=>*material="armor_2".into(),3=>*geometry_revision="unknown".into(),
                        4=>*transform_revision=ap_tag(0,1001),_=>unreachable!(),
                    }, _=>unreachable!(),
                }
            }
            let before=trace.clone();
            assert!(trace.ap_resolution(123,1,1001,0,1,&resolution,90,60).is_err());assert_eq!(trace,before);
        }
    }
    #[test] fn ap_append_reserves_terminal_and_order_before_mutation() {
        let (original,resolution)=ap_contact("Hull","armor_1",&ap_tag(1,1001));
        let mut trace=original.clone(); let material=trace.events.pop().unwrap();
        trace.events.resize(MAX_EVENTS-2,trace.events[0].clone());trace.events.push(material);
        let before=trace.clone();
        assert!(trace.ap_resolution(123,1,1001,0,1,&resolution,90,60).is_err());assert_eq!(trace,before);
        let mut trace=original;trace.next_order=u32::MAX-1;let before=trace.clone();
        assert!(trace.ap_resolution(123,1,1001,0,1,&resolution,90,60).is_err());assert_eq!(trace,before);
    }
    #[test] fn ap_resolution_follows_its_own_material_despite_interleaved_other_shot() {
        let now=Instant::now();let w=world(now);let bundle=super::super::geometry::tests::bundle();
        let mut trace=Trace::new();let mut resolutions=Vec::new();
        for (shot,slot) in [(1,0),(2,1)] {
            let projectile=super::super::projectile::Projectile::launch(shot,slot,&w.actors[slot],now).unwrap();
            trace.admission(123,shot,1000,slot,20,19).unwrap();trace.launch(123,&projectile,1000).unwrap();
        }
        for (shot,target) in [(1,1),(2,0)] {
            trace.segment(123,shot,1001,1000,[-1.0,0.0,0.0],[3.0,0.0,0.0]).unwrap();
            let mesh=tagged_plate("Hull","armor_1",&ap_tag(target,1001));
            let (hits,facts)=trace.collision_query_classified(123,shot,1001,&mesh,bundle.materials()).unwrap();
            resolutions.push(ap::resolve(ap::Input{material:facts.as_ref().unwrap(),segment_direction:[4.0,0.0,0.0],
                winding_normal:hits[0].normal,distance:10.0}).unwrap());
        }
        trace.ap_resolution(123,1,1001,0,1,&resolutions[0],90,60).unwrap();
        trace.ap_resolution(123,2,1001,1,0,&resolutions[1],90,60).unwrap();
        trace.terminal(123,1,1001,TerminalReason::TestLabImpact).unwrap();
        trace.terminal(123,2,1001,TerminalReason::TestLabImpact).unwrap();
        assert_eq!(trace.terminal_shots(),&[1,2]);
    }

    #[test]
    fn classified_batch_uses_exact_nearest_intersection_without_changing_query() {
        let bundle = super::super::geometry::tests::bundle();
        let catalog = bundle.materials();
        let mesh = material_planes("Hull", "armor_8", false);
        let mut trace = launched_trace();
        trace.segment(123, 1, 1001, 1000, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
        let mut unclassified = trace.clone();
        let original = unclassified.collision_query(123, 1, 1001, &mesh).unwrap();
        let (candidates, facts) = trace.collision_query_classified(123, 1, 1001, &mesh, catalog).unwrap();
        assert_eq!(candidates, original);
        for (classified, plain) in candidates.iter().zip(&original) {
            assert_eq!(classified.t.to_bits(), plain.t.to_bits());
            assert_eq!(classified.normal.map(f32::to_bits), plain.normal.map(f32::to_bits));
        }
        assert_eq!(candidates.iter().map(|hit| hit.triangle_id).collect::<Vec<_>>(), vec![7, 2]);
        assert_eq!(facts, Some(catalog.lookup("Hull", "armor_8").unwrap()));
        assert_eq!(&trace.events()[..unclassified.events().len()], unclassified.events());
        match trace.events().last().unwrap() {
            Event::MaterialContact { order, battle_id, shot_id, server_tick, query_order,
                segment_order, intersection_order, candidate_index, facts: stored } => {
                assert_eq!((*order, *battle_id, *shot_id, *server_tick), (7, 123, 1, 1001));
                assert_eq!((*query_order, *segment_order, *intersection_order, *candidate_index), (4, 3, 5, 0));
                assert_eq!(Some(stored), facts.as_ref());
                assert!(matches!(trace.events().iter().find(|event| event.order() == *intersection_order),
                    Some(Event::Intersection { triangle_id: 7, candidate_index: 0, .. })));
            }
            _ => panic!("nearest material event missing"),
        }
        let before = trace.clone();
        assert!(trace.terminal(123, 1, 1001, TerminalReason::RangeExpired).is_err());
        assert!(trace.terminal(123, 1, 1001, TerminalReason::UnavailableImpactResolver).is_err());
        assert!(trace.segment(123, 1, 1002, 1001, [3.0, 0.0, 0.0], [4.0, 0.0, 0.0]).is_err());
        assert!(trace.collision_query_classified(123, 1, 1001, &mesh, catalog).is_err());
        assert_eq!(trace, before);
        trace.terminal(123, 1, 1001, TerminalReason::UnresolvedCollision).unwrap();
        assert_eq!(trace.events().last().unwrap().stage(), Stage::Terminal);
        let before = trace.clone();
        assert!(trace.collision_query_classified(123, 1, 1001, &mesh, catalog).is_err());
        assert!(trace.terminal(123, 1, 1001, TerminalReason::UnresolvedCollision).is_err());
        assert_eq!(trace, before);
    }

    #[test]
    fn classification_preserves_winding_normal_without_entry_exit_claims() {
        let bundle = super::super::geometry::tests::bundle();
        let mut trace = launched_trace();
        trace.segment(123, 1, 1001, 1000, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
        let mut reversed = trace.clone();
        let (forward, facts) = trace.collision_query_classified(123, 1, 1001,
            &material_planes("Hull", "armor_8", false), bundle.materials()).unwrap();
        let (backward, reverse_facts) = reversed.collision_query_classified(123, 1, 1001,
            &material_planes("Hull", "armor_8", true), bundle.materials()).unwrap();
        assert_eq!(facts, reverse_facts);
        assert_eq!((forward[0].triangle_id, forward[0].t), (backward[0].triangle_id, backward[0].t));
        assert_eq!((forward[0].normal[0], backward[0].normal[0]), (1.0, -1.0));
        for (trace, candidate) in [(&trace, &forward[0]), (&reversed, &backward[0])] {
            match &trace.events()[4] {
                Event::Intersection { normal, .. } => assert_eq!(normal.map(f32::to_bits), candidate.normal.map(f32::to_bits)),
                _ => panic!("raw intersection missing"),
            }
        }
    }

    #[test]
    fn invalid_nearest_material_or_identity_rejects_the_entire_classified_batch() {
        let bundle = super::super::geometry::tests::bundle();
        let catalog = bundle.materials();
        let mut trace = launched_trace();
        trace.segment(123, 1, 1001, 1000, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
        let before = trace.clone();
        for (component, label) in [("Hull", "unknown"), ("Unknown", "armor_8"), ("Gun_02", "armor_8")] {
            assert!(trace.collision_query_classified(123, 1, 1001,
                &material_planes(component, label, false), catalog).is_err());
            assert_eq!(trace, before);
        }
        let mesh = material_planes("Hull", "armor_8", false);
        for (battle, shot, tick) in [(124, 1, 1001), (123, 2, 1001), (123, 1, 1000), (123, 1, 1002)] {
            assert!(trace.collision_query_classified(battle, shot, tick, &mesh, catalog).is_err());
            assert_eq!(trace, before);
        }
    }

    #[test]
    fn classified_empty_query_has_no_material_event_and_can_continue() {
        let bundle = super::super::geometry::tests::bundle();
        let mesh = material_planes("Hull", "armor_8", false);
        let mut trace = launched_trace();
        let before = trace.clone();
        assert!(trace.collision_query_classified(123, 1, 1000, &mesh, bundle.materials()).is_err());
        assert_eq!(trace, before);
        trace.segment(123, 1, 1001, 1000, [-2.0, 0.0, 0.0], [-1.0, 0.0, 0.0]).unwrap();
        let (candidates, material) = trace.collision_query_classified(123, 1, 1001, &mesh, bundle.materials()).unwrap();
        assert!(candidates.is_empty()); assert!(material.is_none());
        assert!(matches!(trace.events().last(), Some(Event::CollisionQuery { candidate_count: 0, .. })));
        let before = trace.clone();
        assert!(trace.terminal(123, 1, 1001, TerminalReason::UnresolvedCollision).is_err());
        assert!(trace.collision_query_classified(123, 1, 1001, &mesh, bundle.materials()).is_err());
        assert_eq!(trace, before);
        for reason in [TerminalReason::RangeExpired, TerminalReason::UnavailableImpactResolver] {
            let mut ending = trace.clone();
            ending.terminal(123, 1, 1001, reason).unwrap();
        }
        trace.segment(123, 1, 1002, 1001, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
        trace.collision_query_classified(123, 1, 1002, &mesh, bundle.materials()).unwrap();
        assert_eq!(trace.events().iter().filter(|event| matches!(event, Event::MaterialContact { .. })).count(), 1);
    }

    #[test]
    fn classified_batch_reserves_material_and_terminal_capacity_before_append() {
        let bundle = super::super::geometry::tests::bundle();
        let mesh = material_planes("Hull", "armor_8", false);
        let mut original = launched_trace();
        original.segment(123, 1, 1001, 1000, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
        let mut trace = original.clone();
        let segment = trace.events.pop().unwrap();
        trace.events.resize(MAX_EVENTS - 6, trace.events[0].clone());
        trace.events.push(segment); // Five free rows: batch+terminal fit, AP outcome would not.
        let before = trace.clone();
        assert!(trace.collision_query_classified(123, 1, 1001, &mesh, bundle.materials()).is_err());
        assert_eq!(trace, before);

        let mut trace = original;
        trace.next_order = u32::MAX - 5;
        let before = trace.clone();
        assert!(trace.collision_query_classified(123, 1, 1001, &mesh, bundle.materials()).is_err());
        assert_eq!(trace, before);
    }

    #[test]
    fn collision_batch_binds_actual_query_to_exact_segment_and_revisions() {
        let mut trace = launched_trace();
        trace.segment(123, 1, 1001, 1000, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
        let candidates = trace.collision_query(123, 1, 1001, &two_planes()).unwrap();
        assert_eq!(candidates.len(), 2);
        assert_eq!(trace.events().iter().map(Event::stage).collect::<Vec<_>>(),
            vec![Stage::Admission, Stage::Launch, Stage::Segment, Stage::CollisionQuery,
                Stage::Intersection, Stage::Intersection]);
        match &trace.events()[3] {
            Event::CollisionQuery { order, segment_order, candidate_count,
                geometry_revision, transform_revision, .. } => {
                assert_eq!((*order, *segment_order, *candidate_count), (4, 3, 2));
                assert_eq!(geometry_revision, "synthetic-geometry-v1");
                assert_eq!(transform_revision, "synthetic-world-identity-v1");
            }
            _ => panic!("query row missing"),
        }
        for (index, (id, t, material)) in [(7, 0.25, "test-a"), (42, 0.75, "test-b")].iter().enumerate() {
            match &trace.events()[4 + index] {
                Event::Intersection { query_order, segment_order, candidate_index, triangle_id,
                    t: actual_t, material: actual_material, normal, server_tick, .. } => {
                    assert_eq!((*query_order, *segment_order, *candidate_index, *triangle_id), (4, 3, index, *id));
                    assert_eq!((*actual_t, *server_tick, *normal), (*t, 1001, [1.0, 0.0, 0.0]));
                    assert_eq!(actual_material, material);
                    let candidate = &candidates[index];
                    assert_eq!((candidate.candidate_index, candidate.triangle_id, candidate.t, candidate.normal),
                        (*candidate_index, *triangle_id, *actual_t, *normal));
                    assert_eq!(&candidate.material, actual_material);
                }
                _ => panic!("intersection missing"),
            }
        }
        let before = trace.clone();
        assert!(trace.terminal(123, 1, 1001, TerminalReason::RangeExpired).is_err());
        assert!(trace.terminal(123, 1, 1001, TerminalReason::UnavailableImpactResolver).is_err());
        assert!(trace.segment(123, 1, 1002, 1001, [3.0, 0.0, 0.0], [4.0, 0.0, 0.0]).is_err());
        assert_eq!(trace, before);
        trace.terminal(123, 1, 1001, TerminalReason::UnresolvedCollision).unwrap();
        assert_eq!(trace.terminal_shots(), &[1]);
        let before = trace.clone();
        assert!(trace.terminal(123, 1, 1001, TerminalReason::UnresolvedCollision).is_err());
        assert!(trace.collision_query(123, 1, 1001, &two_planes()).is_err());
        assert_eq!(trace, before);
    }

    #[test]
    fn empty_query_allows_further_flight_and_does_not_claim_whole_shot_miss() {
        let mut trace = launched_trace();
        trace.segment(123, 1, 1001, 1000, [-2.0, 0.0, 0.0], [-1.0, 0.0, 0.0]).unwrap();
        assert!(trace.collision_query(123, 1, 1001, &two_planes()).unwrap().is_empty());
        assert!(matches!(trace.events().last(), Some(Event::CollisionQuery { candidate_count: 0, .. })));
        assert!(trace.terminal_shots().is_empty());
        let before = trace.clone();
        assert!(trace.terminal(123, 1, 1001, TerminalReason::UnresolvedCollision).is_err());
        assert!(trace.collision_query(123, 1, 1001, &two_planes()).is_err());
        assert_eq!(trace, before);
        for reason in [TerminalReason::RangeExpired, TerminalReason::UnavailableImpactResolver] {
            let mut ending = trace.clone();
            ending.terminal(123, 1, 1001, reason).unwrap();
            assert_eq!(ending.terminal_shots(), &[1]);
        }
        trace.segment(123, 1, 1002, 1001, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
        trace.collision_query(123, 1, 1002, &two_planes()).unwrap();
        assert!(matches!(trace.events().last(), Some(Event::Intersection { candidate_index: 1, segment_order: 5, .. })));
    }

    #[test]
    fn rejected_collision_queries_do_not_leave_partial_events() {
        let mut trace = launched_trace();
        let mesh = two_planes();
        let before = trace.clone();
        assert!(trace.collision_query(123, 1, 1000, &mesh).is_err());
        assert!(trace.terminal(123, 1, 1000, TerminalReason::UnresolvedCollision).is_err());
        assert_eq!(trace, before);
        trace.segment(123, 1, 1001, 1000, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
        let before = trace.clone();
        for (battle, shot, tick) in [(124, 1, 1001), (123, 2, 1001), (123, 1, 1000), (123, 1, 1002)] {
            assert!(trace.collision_query(battle, shot, tick, &mesh).is_err());
            assert_eq!(trace, before);
        }
        trace.collision_query(123, 1, 1001, &mesh).unwrap();
        let before = trace.clone();
        assert!(trace.collision_query(123, 1, 1001, &mesh).is_err());
        assert_eq!(trace, before);

    }

    #[test]
    fn segment_bound_rejects_overrun_atomically_and_still_allows_terminal() {
        let mut trace = launched_trace();
        let mesh = two_planes();
        let mut tick = 1000;
        for _ in 0..MAX_SEGMENTS_PER_SHOT {
            trace.segment(123, 1, tick + 1, tick, [-2.0, 0.0, 0.0], [-1.0, 0.0, 0.0]).unwrap();
            tick += 1;
            assert!(trace.collision_query(123, 1, tick, &mesh).unwrap().is_empty());
        }
        let before = trace.clone();
        assert!(trace.segment(123, 1, tick + 1, tick, [-2.0, 0.0, 0.0], [-1.0, 0.0, 0.0]).is_err());
        assert_eq!(trace, before);
        trace.terminal(123, 1, tick, TerminalReason::RangeExpired).unwrap();
        assert_eq!(trace.terminal_shots(), &[1]);
    }

    #[test]
    fn query_capacity_and_order_guards_leave_no_partial_batch() {
        let mut trace = launched_trace();
        trace.segment(123, 1, 1001, 1000, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
        let mesh = two_planes();
        // Fault-inject an exhausted event store to exercise the atomic guard.
        // Public admission/segment limits prevent a valid trace exceeding the
        // full-ammo budget tested separately below.
        let segment = trace.events.pop().unwrap();
        trace.events.resize(MAX_EVENTS - 3, trace.events[0].clone());
        trace.events.push(segment);
        let before = trace.clone();
        assert!(trace.collision_query(123, 1, 1001, &mesh).is_err());
        assert_eq!(trace, before);

        let mut trace = launched_trace();
        trace.segment(123, 1, 1001, 1000, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
        trace.next_order = u32::MAX - 3;
        let before = trace.clone();
        assert!(trace.collision_query(123, 1, 1001, &mesh).is_err());
        assert_eq!(trace, before);
    }

    #[test]
    fn full_ammo_maximum_segments_and_collision_batches_fit_exact_budget() {
        let bundle = super::super::geometry::tests::bundle();
        let triangles: Vec<_> = (0..collision::MAX_CANDIDATES).map(|id| collision::Triangle {
            triangle_id: id as u32, a: 0, b: 1, c: 2,
            mesh: "Hull".into(), group: "overlap".into(), material: "armor_8".into(),
        }).collect();
        let now = Instant::now();
        let world = world(now);
        let mut trace = Trace::new();
        let mut tick = 1000;
        for index in 0..model::MAX_SHOTS {
            let shot_id = index as u32 + 1;
            let slot = index / 20;
            // Synthetic overlap geometry exercises the target-tag contract;
            // it is not evidence that these triangles are native geometry.
            let target = 1 - slot;
            let last_tick = tick + MAX_SEGMENTS_PER_SHOT as u32;
            let mesh = collision::Mesh::new(
                vec![[0.0, -1.0, -1.0], [0.0, 1.0, -1.0], [0.0, 0.0, 1.0]],
                triangles.clone(), super::super::geometry::SOURCE_REVISION,
                format!("pose-v1:{target}:{last_tick}:{}", "0".repeat(64))).unwrap();
            let ammo_before = 20 - (index % 20) as u16;
            let projectile = super::super::projectile::Projectile::launch(shot_id, slot, &world.actors[slot], now).unwrap();
            trace.admission(123, shot_id, tick, slot, ammo_before, ammo_before - 1).unwrap();
            trace.launch(123, &projectile, tick).unwrap();
            for segment in 0..MAX_SEGMENTS_PER_SHOT {
                let last = segment + 1 == MAX_SEGMENTS_PER_SHOT;
                let (start, end) = if last { ([-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]) }
                    else { ([-2.0, 0.0, 0.0], [-1.0, 0.0, 0.0]) };
                trace.segment(123, shot_id, tick + 1, tick, start, end).unwrap();
                tick += 1;
                let (candidates, material) = trace.collision_query_classified(123, shot_id, tick, &mesh,
                    bundle.materials()).unwrap();
                assert_eq!(candidates.len(), if last { collision::MAX_CANDIDATES } else { 0 });
                assert_eq!(material.is_some(), last);
                if last {
                    let resolution = ap::resolve(ap::Input { material: material.as_ref().unwrap(),
                        segment_direction: [4.0,0.0,0.0], winding_normal: candidates[0].normal, distance: 10.0 }).unwrap();
                    trace.ap_resolution(123,shot_id,tick,slot,target,&resolution,90,60).unwrap();
                }
            }
            trace.terminal(123, shot_id, tick, TerminalReason::TestLabImpact).unwrap();
        }
        assert_eq!(trace.events().len(), MAX_EVENTS);
        assert_eq!(trace.terminal_shots().len(), model::MAX_SHOTS);
        assert_eq!(trace.events().iter().filter(|event| matches!(event, Event::MaterialContact { .. })).count(), model::MAX_SHOTS);
        assert_eq!(trace.events().iter().filter(|event| matches!(event, Event::ApResolution { .. })).count(), model::MAX_SHOTS);
        assert!(trace.events().iter().enumerate().all(|(index, row)| row.order() as usize == index + 1));
        let before = trace.clone();
        assert!(trace.admission(123, model::MAX_SHOTS as u32 + 1, tick, 0, 20, 19).is_err());
        assert_eq!(trace, before);
    }

    #[test]
    fn shot_bound_applies_even_when_earlier_shots_use_no_segments() {
        let mut trace = Trace::new();
        for shot in 1..=model::MAX_SHOTS as u32 {
            trace.admission(123, shot, 1000, 0, 20, 19).unwrap();
        }
        let before = trace.clone();
        assert!(trace.admission(123, model::MAX_SHOTS as u32 + 1, 1000, 0, 20, 19).is_err());
        assert_eq!(trace, before);
    }

    #[test]
    fn geometry_query_failures_propagate_without_trace_side_effects() {
        let mut trace = launched_trace();
        trace.segment(123, 1, 1001, 1000, [0.0; 3], [0.0; 3]).unwrap();
        let before = trace.clone();
        assert!(trace.collision_query(123, 1, 1001, &two_planes()).is_err());
        assert_eq!(trace, before);

        let triangles = (0..=collision::MAX_CANDIDATES).map(|id| collision::Triangle {
            triangle_id: id as u32, a: 0, b: 1, c: 2,
            mesh: "synthetic".into(), group: "overlap".into(), material: "test".into(),
        }).collect();
        let overlapping = collision::Mesh::new(
            vec![[0.0, -1.0, -1.0], [0.0, 1.0, -1.0], [0.0, 0.0, 1.0]],
            triangles, "synthetic-overlap-v1", "synthetic-world-identity-v1").unwrap();
        let mut trace = launched_trace();
        trace.segment(123, 1, 1001, 1000, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
        let before = trace.clone();
        assert!(trace.collision_query(123, 1, 1001, &overlapping).is_err());
        assert_eq!(trace, before);
    }

    #[test]
    fn collision_trace_does_not_mutate_world_actors_ammo_or_projectiles() {
        let now = Instant::now();
        let mut world = world(now);
        world.apply(0, 1, &[model::Command::Fire(crate::battle091::fire::Command::Shoot)], now).unwrap();
        let before = (world.actors.clone(), world.projectiles.clone(), world.shots.clone());
        world.impact.segment(world.id, 1, world.tick + 1, world.tick,
            [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
        world.impact.collision_query(world.id, 1, world.tick + 1, &two_planes()).unwrap();
        world.impact.terminal(world.id, 1, world.tick + 1, TerminalReason::UnresolvedCollision).unwrap();
        assert_eq!((world.actors, world.projectiles, world.shots), before);
    }

    #[test]
    fn interleaved_classified_shots_query_and_classify_their_own_segment() {
        let bundle = super::super::geometry::tests::bundle();
        let catalog = bundle.materials();
        let hull = material_planes("Hull", "armor_8", false);
        let turret = material_planes("Turret_01", "armor_8", false);
        let now = Instant::now();
        let world = world(now);
        let mut trace = Trace::new();
        for (shot, slot) in [(1, 0), (2, 1)] {
            let projectile = super::super::projectile::Projectile::launch(shot, slot, &world.actors[slot], now).unwrap();
            trace.admission(123, shot, 1000, slot, 20, 19).unwrap();
            trace.launch(123, &projectile, 1000).unwrap();
        }
        trace.segment(123, 1, 1001, 1000, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
        trace.segment(123, 2, 1001, 1000, [-2.0, 0.0, 0.0], [-1.0, 0.0, 0.0]).unwrap();
        assert!(trace.collision_query_classified(123, 2, 1001, &turret, catalog).unwrap().1.is_none());
        assert_eq!(trace.collision_query_classified(123, 1, 1001, &hull, catalog).unwrap().1,
            Some(catalog.lookup("Hull", "armor_8").unwrap()));
        let queries: Vec<_> = trace.events().iter().filter_map(|row| match row {
            Event::CollisionQuery { shot_id, segment_order, candidate_count, .. } =>
                Some((*shot_id, *segment_order, *candidate_count)),
            _ => None,
        }).collect();
        assert_eq!(queries, vec![(2, 6, 0), (1, 5, 2)]);
        trace.terminal(123, 1, 1001, TerminalReason::UnresolvedCollision).unwrap();
        trace.segment(123, 2, 1002, 1001, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
        assert_eq!(trace.terminal_shots(), &[1]);
        assert_eq!(trace.collision_query_classified(123, 2, 1002, &turret, catalog).unwrap().1,
            Some(catalog.lookup("Turret_01", "armor_8").unwrap()));
        trace.terminal(123, 2, 1002, TerminalReason::UnresolvedCollision).unwrap();
        let classifications: Vec<_> = trace.events().iter().filter_map(|event| match event {
            Event::MaterialContact { shot_id, query_order, segment_order, intersection_order, facts, .. } =>
                Some((*shot_id, *query_order, *segment_order, *intersection_order, facts)),
            _ => None,
        }).collect();
        assert_eq!(classifications.len(), 2);
        assert_eq!(classifications[0].0, 1); assert_eq!(classifications[1].0, 2);
        assert_ne!(classifications[0].4, classifications[1].4);
        for (shot, query, segment, intersection, facts) in classifications {
            assert!(matches!(trace.events().iter().find(|event| event.order() == query),
                Some(Event::CollisionQuery { shot_id, segment_order, .. }) if *shot_id == shot && *segment_order == segment));
            match trace.events().iter().find(|event| event.order() == intersection) {
                Some(Event::Intersection { shot_id, query_order, segment_order, candidate_index: 0, mesh, material, .. }) => {
                    assert_eq!((*shot_id, *query_order, *segment_order), (shot, query, segment));
                    assert_eq!(*facts, catalog.lookup(mesh, material).unwrap());
                }
                _ => panic!("classified intersection binding missing"),
            }
        }
        assert_eq!(trace.terminal_shots(), &[1, 2]);
    }
}
