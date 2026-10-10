//! Two temporary allied laboratory actors. No native IDs, client poses, clocks
//! or garage inventory enter the simulation. Kinematics are deliberately not P05.
use std::{io, time::{Duration, Instant}};
use crate::battle091::fire;
use super::{aim, impact, projectile::Projectile};

pub const CAPACITY: usize = 2;
pub const LIFETIME: Duration = Duration::from_secs(3600);
pub const STEP: Duration = Duration::from_millis(100);
pub const MAX_COMMANDS: usize = 32;
pub const MAX_SHOTS: usize = CAPACITY * fire::MS1_INITIAL_AMMO as usize;
pub const SPAWN: [f32; 3] = [-58.499908, 33.770267, -445.81305];

pub fn bad() -> io::Error { io::Error::new(io::ErrorKind::InvalidData, "shared laboratory contract") }

#[derive(Clone, Debug, PartialEq)]
pub struct Identity { pub account: String, pub database: i32, pub name: String }

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Input { pub throttle: i8, pub steer: i8 }
impl Input { pub const STOP: Self = Self { throttle: 0, steer: 0 }; }

#[derive(Clone, Debug, PartialEq)]
pub struct Actor {
    pub identity: Identity,
    pub session: Option<u32>,
    pub ready: bool,
    pub position: [f32; 3],
    /// Server-authoritative hull orientation in worker order: yaw, pitch, roll.
    pub direction: [f32; 3],
    pub yaw: f32,
    pub speed: f32,
    pub input: Input,
    pub fire: fire::State,
    pub aim: aim::State,
    origin: [f32; 3],
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Command { Move(Input), Aim(aim::Intent), Fire(fire::Command), Leave }

/// One accepted server action, independent of native entity/method IDs. The
/// laboratory never replenishes ammo, so its complete event history is bounded.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Shot { pub sequence: u32, pub slot: usize, pub tick: u32 }

#[derive(Clone)]
pub struct World {
    pub id: u64,
    pub actors: Vec<Actor>,
    pub started: Option<Instant>,
    last: Instant,
    pub tick: u32,
    pub shots: Vec<Shot>,
    pub projectiles: Vec<Projectile>,
    pub impact: impact::Trace,
}

impl World {
    pub fn new(id: u64, now: Instant) -> io::Result<Self> {
        if id == 0 { return Err(bad()); }
        Ok(Self { id, actors: Vec::new(), started: None, last: now, tick: 1000,
            shots: Vec::new(), projectiles: Vec::new(), impact: impact::Trace::new() })
    }
    pub fn latest_shot(&self) -> u32 { self.shots.last().map(|s| s.sequence).unwrap_or(0) }
    /// Authenticated identity only. The caller reserves a transport retirement
    /// slot before committing this world assignment. Rejoin never resets ammo.
    pub fn attach(&mut self, identity: Identity, session: u32) -> io::Result<usize> {
        if session == 0 || identity.database <= 0 || identity.account.is_empty()
            || self.actors.iter().any(|a| a.session == Some(session)) { return Err(bad()); }
        if let Some(slot) = self.actors.iter().position(|a| a.identity.account == identity.account) {
            let a = &mut self.actors[slot];
            if a.session.is_some() || a.identity != identity { return Err(bad()); }
            a.session = Some(session); a.ready = false; a.input = Input::STOP; a.speed = 0.; a.aim.park();
            return Ok(slot);
        }
        if self.actors.len() == CAPACITY || self.actors.iter().any(|a| a.identity.database == identity.database) {
            return Err(bad());
        }
        let slot = self.actors.len();
        let mut origin = SPAWN; origin[0] += if slot == 0 { -4. } else { 4. };
        self.actors.push(Actor { identity, session: Some(session), ready: false,
            position: origin, direction: [0.; 3], origin, yaw: 0., speed: 0., input: Input::STOP,
            fire: fire::State::new(), aim: aim::State::new() });
        Ok(slot)
    }
    pub fn start(&mut self, now: Instant) -> io::Result<()> {
        if self.started.is_some() || self.actors.len() != CAPACITY || now < self.last { return Err(bad()); }
        self.started = Some(now); self.last = now; Ok(())
    }
    /// Integrated map-drive owns the initial lane placement. Rebase happens
    /// in the start tick before native arena announcements; after that first
    /// turn all poses come from the workers atomically.
    pub fn rebase_external_spawns(&mut self, positions: [[f32; 3]; CAPACITY]) -> io::Result<()> {
        // The integrated runtime calls this in the same loop turn as
        // `start`, before tick 1000 is published or either actor is ready.
        if self.actors.len() != CAPACITY || self.tick != 1000 || self.actors.iter().any(|actor| actor.ready) { return Err(bad()); }
        for position in positions {
            if position.iter().any(|value| !value.is_finite() || value.abs() > 2000.) { return Err(bad()); }
        }
        for (actor, position) in self.actors.iter_mut().zip(positions) {
            actor.position = position;
            actor.origin = position;
        }
        Ok(())
    }
    /// A reconnect gets a fresh worker process. Until that worker is settled,
    /// put the actor back on its server-owned lane so a stale parked pose
    /// cannot become a large cross-terrain anchor offset.
    pub fn reset_external_spawn(&mut self, slot: usize, position: [f32; 3]) -> io::Result<()> {
        let actor = self.actors.get_mut(slot).ok_or_else(bad)?;
        if actor.session.is_none() || actor.ready || position.iter().any(|value| !value.is_finite() || value.abs() > 2000.) {
            return Err(bad());
        }
        actor.position = position;
        actor.origin = position;
        actor.direction = [0.; 3];
        actor.yaw = 0.;
        actor.speed = 0.;
        Ok(())
    }
    /// Import the first settled worker frame before native arena creation.
    /// This updates pose only; the simulation tick and gameplay state remain
    /// untouched until both native actors have completed their ready contract.
    pub fn import_external_poses(&mut self,
        external: &[(usize, [f32; 3], [f32; 3], f32)]) -> io::Result<()> {
        if external.len() != CAPACITY || external.iter().map(|row| row.0).collect::<std::collections::BTreeSet<_>>().len() != CAPACITY {
            return Err(bad());
        }
        let mut next = self.actors.clone();
        for (slot, position, direction, speed) in external {
            let actor = next.get_mut(*slot).ok_or_else(bad)?;
            if actor.session.is_none() || position.iter().any(|value| !value.is_finite())
                || direction.iter().any(|value| !value.is_finite()) || !speed.is_finite()
                || direction.iter().any(|value| !(-std::f32::consts::PI..=std::f32::consts::PI).contains(value))
                || !(-25. ..=25.).contains(speed) { return Err(bad()); }
            actor.position = *position;
            actor.direction = *direction;
            actor.yaw = direction[0];
            actor.speed = *speed;
        }
        self.actors = next;
        Ok(())
    }
    pub fn detach(&mut self, session: u32) -> io::Result<()> {
        let a = self.actors.iter_mut().find(|a| a.session == Some(session)).ok_or_else(bad)?;
        a.session = None; a.ready = false; a.input = Input::STOP; a.speed = 0.; a.aim.park(); Ok(())
    }
    pub fn owned(&self, slot: usize, session: u32) -> io::Result<&Actor> {
        self.actors.get(slot).filter(|a| a.session == Some(session)).ok_or_else(bad)
    }
    pub fn set_ready(&mut self, slot: usize, session: u32) -> io::Result<()> {
        self.owned(slot, session)?; self.actors[slot].ready = true; Ok(())
    }
    pub fn apply(&mut self, slot: usize, session: u32, commands: &[Command], now: Instant)
        -> io::Result<Vec<fire::Outcome>> {
        if self.started.is_none() || now < self.last || commands.len() > MAX_COMMANDS
            || !self.owned(slot, session)?.ready { return Err(bad()); }
        let mut next = self.actors[slot].clone();
        let mut outcomes = Vec::new();
        let mut shots = self.shots.clone();
        let mut projectiles = self.projectiles.clone();
        let mut impact_trace = self.impact.clone();
        for (at, command) in commands.iter().enumerate() {
            match command {
                Command::Aim(intent) => next.aim.set(*intent)?,
                Command::Move(input) => {
                    if !(-1..=1).contains(&input.throttle) || !(-1..=1).contains(&input.steer) { return Err(bad()); }
                    next.input = *input;
                },
                Command::Fire(command) => {
                    let ammo_before = next.fire.ammo();
                    let result = next.fire.apply(&[*command], now)?;
                    for outcome in &result {
                        if let fire::Outcome::AcceptedShot { ammo_remaining } = *outcome {
                            if shots.len() >= MAX_SHOTS || projectiles.len() >= MAX_SHOTS { return Err(bad()); }
                            let sequence = shots.len() as u32 + 1;
                            let projectile = Projectile::launch(sequence, slot, &next, now)?;
                            let elapsed_ticks = now.duration_since(self.started.ok_or_else(bad)?).as_millis() / 100;
                            let launch_tick = 1000u32.checked_add(u32::try_from(elapsed_ticks).map_err(|_| bad())?)
                                .ok_or_else(bad)?;
                            impact_trace.admission(self.id, sequence, launch_tick, slot, ammo_before, ammo_remaining)?;
                            impact_trace.launch(self.id, &projectile, launch_tick)?;
                            shots.push(Shot { sequence, slot, tick: launch_tick });
                            projectiles.push(projectile);
                        }
                    }
                    outcomes.extend(result);
                },
                Command::Leave => {
                    if at + 1 != commands.len() { return Err(bad()); }
                    next.session = None; next.ready = false; next.input = Input::STOP; next.speed = 0.; next.aim.park();
                },
            }
        }
        self.actors[slot] = next; self.shots = shots; self.projectiles = projectiles;
        self.impact = impact_trace; Ok(outcomes)
    }
    /// One shared monotonic clock; bounded integration, no burst catch-up. The
    /// small flat boxes exist only to make remote-state publication observable.
    pub fn advance(&mut self, now: Instant) -> io::Result<bool> {
        self.advance_with_external(now, None)
    }

    /// Advance the shared clock while importing poses from the accepted map
    /// worker. `None` retains the historical bounded laboratory kinematics;
    /// `Some` is used only by the integrated two-client profile. Worker rows
    /// are already validated by the IPC parser and are copied atomically with
    /// the projectile/trace state.
    pub fn advance_with_external(&mut self, now: Instant,
        external: Option<&[(usize, [f32; 3], [f32; 3], f32)]>) -> io::Result<bool> {
        let Some(start) = self.started else { return Ok(false); };
        if now < self.last || now.duration_since(start) >= LIFETIME { return Err(bad()); }
        if let Some(rows) = external {
            let slots = rows.iter().map(|row| row.0).collect::<std::collections::BTreeSet<_>>();
            if rows.len() != CAPACITY || slots.len() != CAPACITY || slots.iter().any(|slot| *slot >= CAPACITY) {
                return Err(bad());
            }
            for (slot, position, direction, speed) in rows {
                if self.actors.get(*slot).and_then(|actor| actor.session).is_none() { return Err(bad()); }
                if position.iter().any(|v| !v.is_finite()) || direction.iter().any(|v| !v.is_finite()) || !speed.is_finite()
                    || direction.iter().any(|v| !(-std::f32::consts::PI..=std::f32::consts::PI).contains(v))
                    || !(-25. ..=25.).contains(speed) { return Err(bad()); }
            }
        }
        let tick = 1000 + (now.duration_since(start).as_millis() / 100) as u32;
        let tick_changed = tick != self.tick;
        let prior_tick = self.tick;
        let prior_time = self.last;
        let mut next_actors = self.actors.clone();
        let mut next_last = self.last;
        let mut next_tick = self.tick;
        if tick_changed {
            let dt = now.duration_since(self.last).as_secs_f32().min(0.2);
            for (slot, a) in next_actors.iter_mut().enumerate() {
                if !a.ready || a.session.is_none() { continue; }
                if let Some(rows) = external {
                    if let Some((_, position, direction, speed)) = rows.iter().find(|(row, ..)| *row == slot) {
                        a.position = *position; a.direction = *direction; a.yaw = direction[0]; a.speed = *speed;
                    }
                } else {
                    a.yaw = (a.yaw + a.input.steer as f32 * dt * 0.5 + std::f32::consts::PI)
                        .rem_euclid(2. * std::f32::consts::PI) - std::f32::consts::PI;
                    a.direction = [a.yaw, 0., 0.];
                    let before = a.position;
                    a.position[0] = (a.position[0] + a.yaw.sin() * a.input.throttle as f32 * dt)
                        .clamp(a.origin[0] - 2., a.origin[0] + 2.);
                    a.position[2] = (a.position[2] + a.yaw.cos() * a.input.throttle as f32 * dt)
                        .clamp(a.origin[2] - 2., a.origin[2] + 2.);
                    a.speed = if before != a.position { a.input.throttle as f32 } else { 0. };
                }
                a.aim.advance(a.position, a.yaw, dt)?;
            }
            next_last = now; next_tick = tick;
        }
        let mut impact_trace = self.impact.clone();
        let mut next_projectiles = self.projectiles.clone();
        if tick_changed {
            for projectile in &self.projectiles {
                if !projectile.stopped {
                    let segment_start = if projectile.launched > prior_time { projectile.launched } else { prior_time };
                    if segment_start < now {
                        let launch_tick = self.shots.iter()
                            .find(|shot| shot.sequence == projectile.sequence).ok_or_else(bad)?.tick;
                        let segment_tick_start = launch_tick.max(prior_tick);
                        impact_trace.segment(self.id, projectile.sequence, tick, segment_tick_start,
                            projectile.position_at(segment_start), projectile.position_at(now))?;
                    }
                }
            }
        }
        let mut expired = false;
        for projectile in &mut next_projectiles {
            if !projectile.stopped && projectile.is_expired(now)? {
                projectile.stopped = true;
                impact_trace.terminal(self.id, projectile.sequence, tick,
                    impact::TerminalReason::RangeExpired)?;
                expired = true;
            }
        }
        self.actors = next_actors;
        self.last = next_last;
        self.tick = next_tick;
        self.projectiles = next_projectiles;
        self.impact = impact_trace;
        Ok(tick_changed || expired)
    }
}

#[cfg(test)]
pub(super) mod tests {
    use super::*;
    pub fn world(now: Instant) -> World {
        let mut w = World::new(123, now).unwrap();
        for i in 0..2 { w.attach(Identity { account: format!("owned-{i}"), database: i + 1,
            name: format!("player_{i}") }, i as u32 + 1).unwrap(); }
        w.start(now).unwrap(); w.set_ready(0, 1).unwrap(); w.set_ready(1, 2).unwrap(); w
    }
    #[test] fn two_controllers_change_one_shared_world_without_cross_ownership() {
        let now = Instant::now(); let mut w = world(now); let other = w.actors[1].clone();
        assert!(w.apply(1, 1, &[Command::Move(Input { throttle: 1, steer: 0 })], now).is_err());
        w.apply(0, 1, &[Command::Move(Input { throttle: 1, steer: 0 })], now).unwrap();
        w.advance(now + STEP).unwrap(); assert!(w.actors[0].position[2] > SPAWN[2]);
        assert_eq!(w.actors[1], other);
    }
    #[test] fn integrated_external_pose_is_authoritative_and_atomic() {
        let now = Instant::now(); let mut w = world(now);
        let pose = [SPAWN[0] + 17., SPAWN[1] + 2., SPAWN[2] - 9.];
        w.advance_with_external(now + STEP, Some(&[(0, pose, [0.75, 0.1, -0.2], 3.5),
            (1, [SPAWN[0] + 4., SPAWN[1], SPAWN[2] + 1.], [-0.25, 0., 0.], 0.)])).unwrap();
        assert_eq!(w.actors[0].position, pose); assert_eq!(w.actors[0].yaw, 0.75);
        assert_eq!(w.actors[0].direction, [0.75, 0.1, -0.2]);
        assert_eq!(w.actors[0].speed, 3.5); assert_eq!(w.actors[1].yaw, -0.25);
        let before = w.clone();
        assert!(w.advance_with_external(now + STEP * 2,
            Some(&[(0, [SPAWN[0], SPAWN[1], SPAWN[2]], [0., 0., 0.], 0.)])).is_err());
        assert_eq!(w.actors, before.actors); assert_eq!(w.tick, before.tick);
        assert!(w.advance_with_external(now + STEP * 2,
            Some(&[(0, [f32::NAN, 0., 0.], [0., 0., 0.], 0.)])).is_err());
        assert_eq!(w.actors, before.actors); assert_eq!(w.tick, before.tick);
    }
    #[test] fn integrated_spawn_rebase_is_lane_bound_and_pre_ready_only() {
        let now = Instant::now();
        let mut w = World::new(124, now).unwrap();
        for i in 0..2 { w.attach(Identity { account: format!("lane-{i}"), database: i + 11,
            name: format!("lane_{i}") }, i as u32 + 11).unwrap(); }
        w.rebase_external_spawns([
            [-67.4999, 22.4167, -440.8130],
            [-59.4999, 22.4167, -440.8130],
        ]).unwrap();
        assert_eq!(w.actors[0].position, [-67.4999, 22.4167, -440.8130]);
        assert_eq!(w.actors[1].origin, [-59.4999, 22.4167, -440.8130]);
        w.start(now).unwrap();
        assert!(w.rebase_external_spawns([
            [-67., 22., -440.], [-59., 22., -440.]
        ]).is_ok());
        w.actors[0].ready = true;
        assert!(w.rebase_external_spawns([
            [-67., 22., -440.], [-59., 22., -440.]
        ]).is_err());
        w.actors[0].ready = false;
        w.reset_external_spawn(0, [-67., 22., -440.]).unwrap();
        assert_eq!(w.actors[0].position, [-67., 22., -440.]);
    }
    #[test] fn disconnect_and_reconnect_keep_survivor_clock_pose_and_ammo() {
        let now = Instant::now(); let mut w = world(now);
        w.apply(0, 1, &[Command::Fire(fire::Command::Shoot)], now).unwrap();
        w.apply(1, 2, &[Command::Move(Input { throttle: 1, steer: 0 })], now).unwrap();
        w.detach(1).unwrap(); let parked = w.actors[0].position;
        w.advance(now + STEP).unwrap(); assert_eq!(w.actors[0].position, parked);
        assert!(w.actors[1].position[2] > SPAWN[2]);
        let identity = w.actors[0].identity.clone(); assert_eq!(w.attach(identity, 3).unwrap(), 0);
        assert_eq!(w.actors[0].fire.ammo(), 19); assert_eq!(w.tick, 1001);
        assert!(w.actors[0].fire.reload_until().is_some());
    }
    #[test] fn bad_late_command_is_atomic_and_reload_is_separate() {
        let now = Instant::now(); let mut w = world(now); let before = w.actors.clone();
        assert!(w.apply(0, 1, &[Command::Fire(fire::Command::Shoot),
            Command::Move(Input { throttle: 2, steer: 0 })], now).is_err());
        assert_eq!(w.actors, before);
        assert!(w.shots.is_empty());
        w.apply(0, 1, &[Command::Fire(fire::Command::Shoot)], now).unwrap();
        assert_eq!(w.apply(0, 1, &[Command::Fire(fire::Command::Shoot)], now).unwrap(), vec![fire::Outcome::RejectedReload]);
        assert_eq!(w.apply(1, 2, &[Command::Fire(fire::Command::Shoot)], now).unwrap(), vec![fire::Outcome::AcceptedShot { ammo_remaining: 19 }]);
        assert_eq!(w.shots, vec![Shot { sequence:1,slot:0,tick:1000 }, Shot { sequence:2,slot:1,tick:1000 }]);
    }
    #[test] fn same_tick_and_staggered_two_actor_launches_keep_trace_order() {
        let now = Instant::now(); let mut w = world(now);
        w.apply(0, 1, &[Command::Fire(fire::Command::Shoot)], now).unwrap();
        w.apply(1, 2, &[Command::Fire(fire::Command::Shoot)], now + Duration::from_millis(90)).unwrap();
        assert_eq!(w.impact.events().iter().filter(|event| event.stage() == impact::Stage::Admission).count(), 2);
        assert_eq!(w.impact.events().iter().filter(|event| event.stage() == impact::Stage::Launch).count(), 2);
        assert_eq!(w.shots.iter().map(|shot| shot.tick).collect::<Vec<_>>(), vec![1000, 1000]);
        w.advance(now + Duration::from_millis(100)).unwrap();
        assert_eq!(w.impact.events().iter().filter(|event| event.stage() == impact::Stage::Segment).count(), 2);
        assert_eq!(w.impact.events().iter().map(impact::Event::order).collect::<Vec<_>>(), (1..=6).collect::<Vec<_>>());
        assert_eq!(w.projectiles.iter().map(|projectile| projectile.slot).collect::<Vec<_>>(), vec![0, 1]);
    }
    #[test] fn full_flight_cadence_stays_inside_trace_budget() {
        let now = Instant::now(); let mut w = world(now);
        for round in 0..20u64 {
            let at = now + Duration::from_secs(round * 3);
            if round != 0 { w.advance(at).unwrap(); }
            w.apply(0, 1, &[Command::Fire(fire::Command::Shoot)], at).unwrap();
            w.apply(1, 2, &[Command::Fire(fire::Command::Shoot)], at).unwrap();
        }
        w.advance(now + Duration::from_secs(60)).unwrap();
        assert_eq!(w.shots.len(), MAX_SHOTS);
        assert_eq!(w.impact.terminal_shots().len(), MAX_SHOTS);
        assert!(w.impact.events().len() <= impact::MAX_EVENTS);
        let orders = w.impact.events().iter().map(impact::Event::order).collect::<Vec<_>>();
        assert_eq!(orders, (1..=orders.len() as u32).collect::<Vec<_>>());
    }
    #[test] fn rejected_apply_and_advance_publish_no_partial_state() {
        let now = Instant::now(); let mut w = world(now);
        let before = (w.actors.clone(), w.shots.clone(), w.projectiles.clone(),
            w.impact.clone(), w.tick, w.last);
        assert!(w.apply(0, 1, &[Command::Fire(fire::Command::Shoot),
            Command::Move(Input { throttle: 2, steer: 0 })], now).is_err());
        assert_eq!((w.actors.clone(), w.shots.clone(), w.projectiles.clone(),
            w.impact.clone(), w.tick, w.last), before);

        w.apply(0, 1, &[Command::Fire(fire::Command::Shoot)], now).unwrap();
        w.projectiles[0].origin[0] = impact::MAX_COORDINATE + 1.0;
        let before = (w.actors.clone(), w.shots.clone(), w.projectiles.clone(),
            w.impact.clone(), w.tick, w.last);
        assert!(w.advance(now + STEP).is_err());
        assert_eq!((w.actors.clone(), w.shots.clone(), w.projectiles.clone(),
            w.impact.clone(), w.tick, w.last), before);
    }
    #[test] fn shot_history_is_bounded_by_real_ammo_and_rejections_emit_nothing() {
        let now = Instant::now(); let mut w = world(now);
        for n in 0..fire::MS1_INITIAL_AMMO {
            for slot in 0..2 {
                w.apply(slot, slot as u32 + 1, &[Command::Fire(fire::Command::Shoot)], now + Duration::from_secs(n as u64 * 3)).unwrap();
            }
        }
        assert_eq!(w.shots.len(), MAX_SHOTS); assert_eq!(w.latest_shot(), 40);
        let before = w.shots.clone();
        assert_eq!(w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now+Duration::from_secs(61)).unwrap(),vec![fire::Outcome::RejectedNoAmmo]);
        assert_eq!(w.shots, before);
    }
    #[test] fn capacity_duplicate_identity_and_old_controller_fail_closed() {
        let now = Instant::now(); let mut w = world(now);
        assert!(w.attach(w.actors[0].identity.clone(), 3).is_err());
        assert!(w.attach(Identity { account: "third".into(), database: 3, name: "third".into() }, 3).is_err());
        w.detach(1).unwrap(); assert!(w.apply(0, 1, &[], now).is_err());
        let mut identity = w.actors[0].identity.clone(); identity.name = "wrong_name".into();
        assert!(w.attach(identity, 3).is_err());
    }
    #[test] fn clock_and_kinematic_bounds_do_not_depend_on_client_telemetry() {
        let now = Instant::now(); let mut w = world(now);
        w.apply(0, 1, &[Command::Move(Input { throttle: 1, steer: 0 })], now).unwrap();
        for n in 1..100 { w.advance(now + STEP * n).unwrap(); }
        assert!((w.actors[0].position[2] - SPAWN[2]).abs() <= 2.);
        assert_eq!(w.actors[0].position[1], SPAWN[1]);
        assert!(w.advance(now).is_err()); assert!(w.advance(now + LIFETIME).is_err());
    }
}
