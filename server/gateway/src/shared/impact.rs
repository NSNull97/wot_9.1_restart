//! Bounded server-owned flight trace for the P06C impact gate.
//!
//! This module deliberately stops before geometry and gameplay resolution. It
//! records facts that the shared laboratory already owns (shot admission,
//! launch pose, flight segments and range expiry) and makes the unavailable
//! impact stages explicit. Static armor labels are not converted into hits.

use std::io;

use super::projectile::Projectile;

pub const RULESET_REVISION: &str = "wot-0.9.1-#717-ms1-ap-flight-v1";
pub const PROFILE: &str = "ms1_ap_2570";
pub const MS1_VEHICLE_COMPACT_ID: u32 = 3329;
pub const MS1_GUN_COMPACT_ID: u32 = 5892;
pub const MS1_AP_SHELL_COMPACT_ID: u32 = 2570;
pub const MAX_EVENTS: usize = 1024;
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
    Terminal,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TerminalReason {
    RangeExpired,
    UnavailableImpactResolver,
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
            Self::Terminal { .. } => Stage::Terminal,
        }
    }

    pub fn order(&self) -> u32 {
        match self {
            Self::Admission { order, .. }
            | Self::Launch { order, .. }
            | Self::Segment { order, .. }
            | Self::Terminal { order, .. } => *order,
        }
    }

    pub fn shot_id(&self) -> u32 {
        match self {
            Self::Admission { shot_id, .. }
            | Self::Launch { shot_id, .. }
            | Self::Segment { shot_id, .. }
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
        if !matches!(self.last_stage(projectile.sequence), Some(Stage::Admission))
            || !finite_vector(projectile.origin) || !finite_vector(projectile.velocity)
            || !finite_vector(projectile.terminal)
            || !projectile.gravity.is_finite() || projectile.gravity <= 0.0
            || projectile.slot >= 2
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
        if segment_tick_end(segment_tick_start, server_tick).is_err()
            || !finite_vector(start) || !finite_vector(end)
            || !matches!(self.last_stage(shot_id), Some(Stage::Launch | Stage::Segment))
            || self.has_terminal(shot_id)
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
        if self.has_terminal(shot_id)
            || !matches!(self.last_stage(shot_id), Some(Stage::Launch | Stage::Segment))
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

    fn last_stage(&self, shot_id: u32) -> Option<Stage> {
        self.events.iter().rev().find(|event| event.shot_id() == shot_id).map(Event::stage)
    }

    fn launch_tick(&self, shot_id: u32) -> Option<u32> {
        self.events.iter().find_map(|event| match event {
            Event::Launch { shot_id: id, server_tick, .. } if *id == shot_id => Some(*server_tick),
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
        assert!(MAX_EVENTS >= model::MAX_SHOTS * 25);
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
    fn regression_nonfinite_and_post_terminal_segments_fail_closed() {
        let now = Instant::now();
        let world = world(now);
        let projectile = super::super::projectile::Projectile::launch(1, 0, &world.actors[0], now).unwrap();
        let mut trace = Trace::new();
        trace.admission(123, 1, 1000, 0, 20, 19).unwrap();
        trace.launch(123, &projectile, 1000).unwrap();
        assert!(trace.segment(123, 1, 1000, 1000, [0.; 3], [1., f32::NAN, 0.]).is_err());
        trace.segment(123, 1, 1001, 1000, [0.; 3], [1.; 3]).unwrap();
        assert!(trace.segment(123, 1, 1002, 1000, [0.; 3], [1.; 3]).is_err());
        trace.terminal(123, 1, 1001, TerminalReason::RangeExpired).unwrap();
        assert!(trace.segment(123, 1, 1002, 1001, [0.; 3], [1.; 3]).is_err());
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
}
