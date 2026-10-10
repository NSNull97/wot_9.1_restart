//! Bounded server-owned flight trace for the P06C impact gate.
//!
//! This module records the server-owned flight facts and the collision-only
//! boundary. It deliberately stops before penetration and gameplay damage.
//! Geometry labels come from the supplied mesh, never from client hit claims.
//! They are not converted into armor thickness or HP mutation by this module.

use std::io;

use super::projectile::Projectile;
use super::collision;

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
    CollisionQuery,
    Intersection,
    Terminal,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TerminalReason {
    RangeExpired,
    UnavailableImpactResolver,
    UnresolvedCollision,
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
        if segment_tick_end(segment_tick_start, server_tick).is_err()
            || !finite_vector(start) || !finite_vector(end)
            || !self.flight_continuable(shot_id)
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
        let valid_stage = match reason {
            TerminalReason::UnresolvedCollision =>
                matches!(self.last_stage(shot_id), Some(Stage::Intersection)),
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

    /// Query exactly the latest recorded segment with caller-owned world-space
    /// geometry. Query and all intersections commit together or not at all.
    /// Revisions identify the supplied facts; they do not verify native axes.
    /// A zero-candidate query permits further flight, not a whole-shot miss.
    pub fn collision_query(&mut self, battle_id: u64, shot_id: u32,
        server_tick: u32, mesh: &collision::Mesh) -> io::Result<()> {
        self.common(battle_id, shot_id, server_tick)?;
        let (segment_order, start, end) = match self.events.iter().rev()
            .find(|event| event.shot_id() == shot_id) {
            Some(Event::Segment { order, segment_tick_end, start, end, .. })
                if *segment_tick_end == server_tick => (*order, *start, *end),
            _ => return Err(invalid("collision query without current unqueried segment")),
        };
        let candidates = collision::query(mesh, start, end)?;
        let added = 1 + candidates.len();
        // Leave room for a terminal if the caller closes this query now.
        // A future runtime adapter must commit query/terminal with its World
        // transaction so unrelated shots cannot consume that remaining slot.
        if self.events.len() + added + 1 > MAX_EVENTS
            || self.next_order.checked_add(added as u32 + 1).is_none() {
            return Err(invalid("collision query trace capacity"));
        }
        let mut next = self.clone();
        let query_order = next.next_order_value()?;
        next.push(Event::CollisionQuery { order: query_order, battle_id, shot_id, server_tick,
            segment_order, candidate_count: candidates.len(),
            geometry_revision: mesh.geometry_revision().into(),
            transform_revision: mesh.transform_revision().into() })?;
        for candidate in candidates {
            let order = next.next_order_value()?;
            next.push(Event::Intersection { order, battle_id, shot_id, server_tick,
                query_order, segment_order, candidate_index: candidate.candidate_index,
                triangle_id: candidate.triangle_id, mesh: candidate.mesh, group: candidate.group,
                material: candidate.material, normal: candidate.normal, t: candidate.t,
                geometry_revision: mesh.geometry_revision().into(),
                transform_revision: mesh.transform_revision().into() })?;
        }
        next.last_tick = server_tick;
        *self = next;
        Ok(())
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

    #[test]
    fn collision_batch_binds_actual_query_to_exact_segment_and_revisions() {
        let mut trace = launched_trace();
        trace.segment(123, 1, 1001, 1000, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
        trace.collision_query(123, 1, 1001, &two_planes()).unwrap();
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
        trace.collision_query(123, 1, 1001, &two_planes()).unwrap();
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

        let mut trace = launched_trace();
        let mut tick = 1000;
        while trace.events().len() < MAX_EVENTS - 2 {
            trace.segment(123, 1, tick + 1, tick, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
            tick += 1;
        }
        let before = trace.clone();
        assert!(trace.collision_query(123, 1, tick, &mesh).is_err());
        assert_eq!(trace, before);

        let mut trace = launched_trace();
        let mut tick = 1000;
        while trace.events().len() < MAX_EVENTS - 4 {
            trace.segment(123, 1, tick + 1, tick, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
            tick += 1;
        }
        trace.collision_query(123, 1, tick, &mesh).unwrap();
        trace.terminal(123, 1, tick, TerminalReason::UnresolvedCollision).unwrap();
        assert_eq!(trace.events().len(), MAX_EVENTS);
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
    fn interleaved_shots_query_their_own_segment() {
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
        trace.collision_query(123, 2, 1001, &two_planes()).unwrap();
        trace.collision_query(123, 1, 1001, &two_planes()).unwrap();
        let queries: Vec<_> = trace.events().iter().filter_map(|row| match row {
            Event::CollisionQuery { shot_id, segment_order, candidate_count, .. } =>
                Some((*shot_id, *segment_order, *candidate_count)),
            _ => None,
        }).collect();
        assert_eq!(queries, vec![(2, 6, 0), (1, 5, 2)]);
        trace.terminal(123, 1, 1001, TerminalReason::UnresolvedCollision).unwrap();
        trace.segment(123, 2, 1002, 1001, [-1.0, 0.0, 0.0], [3.0, 0.0, 0.0]).unwrap();
        assert_eq!(trace.terminal_shots(), &[1]);
    }
}
