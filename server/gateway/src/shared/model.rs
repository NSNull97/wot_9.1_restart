//! Two temporary allied laboratory actors. No native IDs, client poses, clocks
//! or garage inventory enter the simulation. Kinematics are deliberately not P05.
use std::{io, time::{Duration, Instant}};
use crate::battle091::fire;
use super::{aim, projectile::Projectile};

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
}

impl World {
    pub fn new(id: u64, now: Instant) -> io::Result<Self> {
        if id == 0 { return Err(bad()); }
        Ok(Self { id, actors: Vec::new(), started: None, last: now, tick: 1000,
            shots: Vec::new(), projectiles: Vec::new() })
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
            position: origin, origin, yaw: 0., speed: 0., input: Input::STOP, fire: fire::State::new(), aim: aim::State::new() });
        Ok(slot)
    }
    pub fn start(&mut self, now: Instant) -> io::Result<()> {
        if self.started.is_some() || self.actors.len() != CAPACITY || now < self.last { return Err(bad()); }
        self.started = Some(now); self.last = now; Ok(())
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
        for (at, command) in commands.iter().enumerate() {
            match command {
                Command::Aim(intent) => next.aim.set(*intent)?,
                Command::Move(input) => {
                    if !(-1..=1).contains(&input.throttle) || !(-1..=1).contains(&input.steer) { return Err(bad()); }
                    next.input = *input;
                },
                Command::Fire(command) => {
                    let result = next.fire.apply(&[*command], now)?;
                    for outcome in &result {
                        if matches!(outcome, fire::Outcome::AcceptedShot { .. }) {
                            if shots.len() >= MAX_SHOTS || projectiles.len() >= MAX_SHOTS { return Err(bad()); }
                            let sequence = shots.len() as u32 + 1;
                            shots.push(Shot { sequence, slot, tick: self.tick });
                            projectiles.push(Projectile::launch(sequence, slot, &next, now)?);
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
        self.actors[slot] = next; self.shots = shots; self.projectiles = projectiles; Ok(outcomes)
    }
    /// One shared monotonic clock; bounded integration, no burst catch-up. The
    /// small flat boxes exist only to make remote-state publication observable.
    pub fn advance(&mut self, now: Instant) -> io::Result<bool> {
        let Some(start) = self.started else { return Ok(false); };
        if now < self.last || now.duration_since(start) >= LIFETIME { return Err(bad()); }
        let tick = 1000 + (now.duration_since(start).as_millis() / 100) as u32;
        let tick_changed = tick != self.tick;
        if tick_changed {
            let dt = now.duration_since(self.last).as_secs_f32().min(0.2);
            for a in &mut self.actors {
                if !a.ready || a.session.is_none() { continue; }
                a.yaw = (a.yaw + a.input.steer as f32 * dt * 0.5 + std::f32::consts::PI)
                    .rem_euclid(2. * std::f32::consts::PI) - std::f32::consts::PI;
                let before = a.position;
                a.position[0] = (a.position[0] + a.yaw.sin() * a.input.throttle as f32 * dt)
                    .clamp(a.origin[0] - 2., a.origin[0] + 2.);
                a.position[2] = (a.position[2] + a.yaw.cos() * a.input.throttle as f32 * dt)
                    .clamp(a.origin[2] - 2., a.origin[2] + 2.);
                a.speed = if before != a.position { a.input.throttle as f32 } else { 0. };
                a.aim.advance(a.position, a.yaw, dt)?;
            }
            self.last = now; self.tick = tick;
        }
        let mut expired = false;
        for projectile in &mut self.projectiles {
            if !projectile.stopped && projectile.is_expired(now)? {
                projectile.stopped = true;
                expired = true;
            }
        }
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
