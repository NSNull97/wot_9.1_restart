//! Two temporary allied laboratory actors. No native IDs, client poses, clocks
//! or garage inventory enter the simulation. Kinematics are deliberately not P05.
use std::{io, sync::Arc, time::{Duration, Instant}};
use crate::battle091::fire;
use super::{aim, ap, geometry, impact, terrain, materials::MaterialFacts, projectile::Projectile};

pub const CAPACITY: usize = 2;
pub const LIFETIME: Duration = Duration::from_secs(3600);
pub const STEP: Duration = Duration::from_millis(100);
pub const MAX_COMMANDS: usize = 32;
pub const MAX_SHOTS: usize = CAPACITY * fire::MS1_INITIAL_AMMO as usize;
/// Explicit laboratory policy: retained stock geometry blocks AP at a wreck.
/// No penetration, material thickness or additional damage is inferred.
pub const WRECK_POLICY_REVISION: &str = "test_lab-ms1-wreck-block-v1";
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
    pub health: i16,
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

#[derive(Clone, Debug, PartialEq)]
pub struct Contact {
    pub shot: u32, pub target_slot: usize, pub tick: u32,
    pub segment_start: [f32; 3], pub segment_end: [f32; 3], pub segment_seconds: f32,
    pub endpoint: [f32; 3], pub target_position: [f32; 3], pub target_direction: [f32; 3],
    pub target_aim: [f32; 2], pub triangle: super::collision::Candidate,
    pub geometry_revision: String, pub transform_revision: String,
    pub material_facts: MaterialFacts,
}

/// Committed authoritative outcome. No native IDs or client damage claims.
#[derive(Clone, Debug, PartialEq)]
pub enum ImpactOutcome { Ap(ap::Resolution), WreckBlocked }

#[derive(Clone, Debug, PartialEq)]
pub struct AppliedImpact {
    pub shot: u32, pub attacker: usize, pub target: usize, pub tick: u32,
    pub outcome: ImpactOutcome,
    pub health_before: i16, pub health_after: i16,
    pub segment: Option<geometry::ImpactSegment>,
}

/// A surface-only terminal result; never an armor/HP outcome.
#[derive(Clone, Debug, PartialEq)]
pub struct TerrainContact {
    pub shot: u32, pub shooter: usize, pub tick: u32,
    pub hit: terrain::Hit,
    pub segment_start: [f32; 3], pub segment_end: [f32; 3],
    pub direction: [f32; 3],
}

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
    geometry: Option<Arc<geometry::Bundle>>,
    pub contacts: Vec<Contact>,
    ap_test_lab: bool,
    pub impacts: Vec<AppliedImpact>,
    terrain: Option<Arc<terrain::Terrain>>,
    pub terrain_contacts: Vec<TerrainContact>,
}

impl World {
    pub fn new(id: u64, now: Instant) -> io::Result<Self> {
        if id == 0 { return Err(bad()); }
        Ok(Self { id, actors: Vec::new(), started: None, last: now, tick: 1000,
            shots: Vec::new(), projectiles: Vec::new(), impact: impact::Trace::new(),
            geometry: None, contacts: Vec::new(), ap_test_lab: false, impacts: Vec::new(),
            terrain: None, terrain_contacts: Vec::new() })
    }
    pub fn bind_geometry(&mut self, bundle: Arc<geometry::Bundle>) -> io::Result<()> {
        if self.started.is_some() || !self.shots.is_empty() || self.geometry.is_some() { return Err(bad()); }
        self.geometry = Some(bundle); Ok(())
    }
    pub fn enable_ap_test_lab(&mut self) -> io::Result<()> {
        if self.started.is_some() || self.geometry.is_none() || self.ap_test_lab { return Err(bad()); }
        self.ap_test_lab = true; Ok(())
    }
    pub fn bind_terrain(&mut self, terrain: Arc<terrain::Terrain>) -> io::Result<()> {
        if self.started.is_some() || !self.shots.is_empty() || !self.ap_test_lab
            || self.geometry.is_none() || self.terrain.is_some() { return Err(bad()); }
        self.terrain = Some(terrain); Ok(())
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
        self.actors.push(Actor { identity, session: Some(session), ready: false, health: 90,
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
            // Native dead players may still emit neutral input/aim packets.
            // Validate them, then ignore gameplay; leave remains available.
            if next.health == 0 {
                match command {
                    Command::Aim(intent) => { intent.validate()?; continue; },
                    Command::Move(input) => {
                        if !(-1..=1).contains(&input.throttle) || !(-1..=1).contains(&input.steer) { return Err(bad()); }
                        continue;
                    },
                    Command::Fire(_) => continue,
                    Command::Leave => {},
                }
            }
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
                let actor = self.actors.get(*slot).ok_or_else(bad)?;
                // A disconnected actor is parked in the authoritative world;
                // its missing worker must not pause the surviving actor's clock.
                if actor.session.is_none() && (*position != actor.position || *direction != actor.direction || *speed != 0.) {
                    return Err(bad());
                }
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
                a.direction[0] = a.yaw;
                if a.health > 0 { a.aim.advance_pose(a.position, a.direction, dt)?; }
            }
            next_last = now; next_tick = tick;
        }
        let mut impact_trace = self.impact.clone();
        let mut next_projectiles = self.projectiles.clone();
        let mut contacts = self.contacts.clone();
        let mut impacts = self.impacts.clone();
        let mut terrain_contacts = self.terrain_contacts.clone();
        if tick_changed {
            'projectile_loop: for projectile in &mut next_projectiles {
                if !projectile.stopped {
                    let mut segment_start = if projectile.launched > prior_time { projectile.launched } else { prior_time };
                    let segment_limit = now.min(projectile.end_at()?);
                    let mut segment_tick_start = self.shots.iter()
                        .find(|shot| shot.sequence == projectile.sequence).ok_or_else(bad)?.tick.max(prior_tick);
                    while segment_start < segment_limit {
                        // Terrain-enabled flight keeps the nominal chord error
                        // bounded even after a delayed server poll. These are
                        // subsegments of one update, not invented world ticks.
                        let segment_end = if self.terrain.is_some() {
                            segment_limit.min(segment_start.checked_add(STEP).ok_or_else(bad)?)
                        } else { segment_limit };
                        let start_point = projectile.position_at(segment_start);
                        let end_point = projectile.position_at(segment_end);
                        impact_trace.segment(self.id, projectile.sequence, tick, segment_tick_start,
                            start_point, end_point)?;
                        if let Some(bundle) = &self.geometry {
                            let target_slot = 1usize.checked_sub(projectile.slot).ok_or_else(bad)?;
                            let target = next_actors.get(target_slot).ok_or_else(bad)?;
                            let mesh = bundle.world_mesh(target, target_slot, tick)?;
                            let (hits, material_facts, ground) = if let Some(terrain) = &self.terrain {
                                impact_trace.collision_query_world(self.id, projectile.sequence, tick,
                                    &mesh, bundle.materials(), terrain)?
                            } else {
                                let (hits, material) = impact_trace.collision_query_classified(
                                    self.id, projectile.sequence, tick, &mesh, bundle.materials())?;
                                (hits, material, None)
                            };
                            // Both candidates refer to the same original flight chord.
                            // Compare in the vehicle query's f32 parameter domain:
                            // terrain wins a shared rounding bucket, no epsilon.
                            if ground.as_ref().is_some_and(|g| hits.first().is_none_or(|v| (g.t as f32) <= v.t)) {
                                if terrain_contacts.len() >= MAX_SHOTS { return Err(bad()); }
                                let hit = impact_trace.terrain_contact(self.id, projectile.sequence, tick)?;
                                let chord: [f64; 3] = std::array::from_fn(|i| f64::from(end_point[i])-f64::from(start_point[i]));
                                let length = chord.iter().map(|v| v*v).sum::<f64>().sqrt();
                                if !length.is_finite() || length <= 0. { return Err(bad()); }
                                terrain_contacts.push(TerrainContact { shot: projectile.sequence,
                                    shooter: projectile.slot, tick, hit, segment_start: start_point,
                                    segment_end: end_point, direction: chord.map(|v| (v/length) as f32) });
                                projectile.terminal = hit.point; projectile.stopped = true;
                                impact_trace.terminal(self.id, projectile.sequence, tick, impact::TerminalReason::TerrainCollision)?;
                                continue 'projectile_loop;
                            }
                            if let Some(nearest) = hits.first() {
                                let endpoint = std::array::from_fn(|i|
                                    start_point[i] + nearest.t * (end_point[i] - start_point[i]));
                                if contacts.len() >= MAX_SHOTS { return Err(bad()); }
                                let contact = Contact { shot: projectile.sequence, target_slot, tick,
                                    segment_start: start_point, segment_end: end_point,
                                    segment_seconds: segment_end.duration_since(segment_start).as_secs_f32(), endpoint,
                                    target_position: target.position, target_direction: target.direction,
                                    target_aim: [target.aim.yaw, target.aim.pitch], triangle: nearest.clone(),
                                    geometry_revision: mesh.geometry_revision().into(),
                                    transform_revision: mesh.transform_revision().into(),
                                    material_facts: material_facts.ok_or_else(bad)? };
                                let mut terminal_reason = impact::TerminalReason::UnresolvedCollision;
                                if self.ap_test_lab && target.health > 0 {
                                    if impacts.len() >= MAX_SHOTS { return Err(bad()); }
                                    let distance = (0..3).map(|i| {
                                        let delta = f64::from(endpoint[i]) - f64::from(projectile.origin[i]);
                                        delta * delta
                                    }).sum::<f64>().sqrt();
                                    let resolution = ap::resolve(ap::Input {
                                        material: &contact.material_facts,
                                        segment_direction: std::array::from_fn(|i| end_point[i] - start_point[i]),
                                        winding_normal: nearest.normal, distance,
                                    })?;
                                    let before = target.health;
                                    let after = (before - resolution.damage as i16).max(0);
                                    // Unsupported surfaces have no fabricated native outcome.
                                    let segment = if matches!(resolution.outcome, ap::Outcome::Unsupported(_)) { None }
                                        else { Some(bundle.impact_segment(&contact)?) };
                                    impact_trace.ap_resolution(self.id, projectile.sequence, tick,
                                        projectile.slot, target_slot, &resolution, before, after)?;
                                    impacts.push(AppliedImpact { shot: projectile.sequence,
                                        attacker: projectile.slot, target: target_slot, tick,
                                        outcome: ImpactOutcome::Ap(resolution),
                                        health_before: before, health_after: after, segment });
                                    let damaged = next_actors.get_mut(target_slot).ok_or_else(bad)?;
                                    damaged.health = after;
                                    if after == 0 {
                                        damaged.input = Input::STOP; damaged.speed = 0.; damaged.aim.park();
                                    }
                                    terminal_reason = impact::TerminalReason::TestLabImpact;
                                } else if self.ap_test_lab && target.health == 0 {
                                    if impacts.len() >= MAX_SHOTS { return Err(bad()); }
                                    // Retained geometry blocks a shell on an already dead actor.
                                    // Require the same validated native segment, but never run
                                    // the live-armor resolver or mutate health/death/input state.
                                    let segment = Some(bundle.impact_segment(&contact)?);
                                    impact_trace.wreck_impact(self.id, projectile.sequence, tick,
                                        projectile.slot, target_slot, 0, 0)?;
                                    impacts.push(AppliedImpact { shot: projectile.sequence,
                                        attacker: projectile.slot, target: target_slot, tick,
                                        outcome: ImpactOutcome::WreckBlocked,
                                        health_before: 0, health_after: 0, segment });
                                    terminal_reason = impact::TerminalReason::TestLabWreckImpact;
                                }
                                contacts.push(contact);
                                projectile.terminal = endpoint; projectile.stopped = true;
                                impact_trace.terminal(self.id, projectile.sequence, tick,
                                    terminal_reason)?;
                                continue 'projectile_loop;
                            }
                        }
                        segment_start = segment_end;
                        segment_tick_start = tick;
                    }
                }
            }
        }
        let mut expired = false;
        for projectile in &mut next_projectiles {
            // Geometry must inspect the clamped tail before range expiry. A
            // 5ms poll between the last 100ms segment and end_at may otherwise
            // drop up to ~35m without ever querying it.
            if !projectile.stopped && projectile.is_expired(now)? && (self.geometry.is_none() || tick_changed) {
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
        self.contacts = contacts;
        self.impacts = impacts;
        self.terrain_contacts = terrain_contacts;
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
    pub fn collision_world(now: Instant, miss: bool) -> World {
        let mut w = world(now);
        w.geometry = Some(Arc::new(super::super::geometry::tests::bundle()));
        for i in 0..2 {
            let p = if i == 0 { [0.; 3] } else if miss { [100., 0., 0.] } else { [0., 0., 10.] };
            w.actors[i].position = p; w.actors[i].origin = p;
            w.actors[i].yaw = if i == 1 && !miss { -std::f32::consts::PI } else { 0. };
            w.actors[i].direction = [w.actors[i].yaw, 0., 0.];
        }
        w
    }
    pub fn ap_world(now: Instant) -> World {
        let mut w = collision_world(now, false); w.ap_test_lab = true; w
    }
    pub fn terrain_world(now: Instant, offset: f32) -> World {
        let mut w = ap_world(now);
        // Plane y=z-offset across the test arena. The genuine MS-1 mesh
        // remains at z10; offset3 puts ground first, offset20 puts armor first.
        w.terrain = Some(Arc::new(super::super::terrain::tests::fixture(-1000.,2000.,2,
            vec![-1000.-offset,-1000.-offset,1000.-offset,1000.-offset])));
        w
    }
    #[test] fn terrain_requires_prestart_geometry_and_explicit_ap_profile() {
        let now=Instant::now(); let source=terrain_world(now,3.).terrain.unwrap();
        let mut w=World::new(44,now).unwrap();
        assert!(w.bind_terrain(source.clone()).is_err());
        w.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).unwrap();
        assert!(w.bind_terrain(source.clone()).is_err());
        w.enable_ap_test_lab().unwrap(); w.bind_terrain(source.clone()).unwrap();
        assert!(w.bind_terrain(source.clone()).is_err());
        assert!(ap_world(now).bind_terrain(source).is_err());
    }
    #[test] fn nearest_surface_blocks_hill_damage_and_preserves_nearer_armor() {
        let now=Instant::now();
        for (offset,ground,hp) in [(3.,true,90),(20.,false,60)] {
            let mut w=terrain_world(now,offset);
            w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
            w.advance(now+STEP).unwrap();
            assert_eq!(w.actors[1].health,hp); assert_eq!(w.actors[0].fire.ammo(),19);
            assert_eq!(w.terrain_contacts.len(),usize::from(ground));
            assert_eq!(w.impacts.len(),usize::from(!ground));
            assert_eq!(w.contacts.len(),usize::from(!ground));
            assert!(w.projectiles[0].stopped);
            if ground {
                let c=&w.terrain_contacts[0]; assert_eq!(w.projectiles[0].terminal,c.hit.point);
                assert!(c.hit.point[2]<8.); assert!((c.direction.iter().map(|v|v*v).sum::<f32>()-1.).abs()<1e-6);
                assert!(w.impact.events().iter().any(|e| matches!(e,impact::Event::Terminal {
                    reason:impact::TerminalReason::TerrainCollision,.. })));
            }
            let retained=(w.terrain_contacts.clone(),w.contacts.clone(),w.impacts.clone(),w.impact.clone());
            w.advance(now+Duration::from_secs(3)).unwrap();
            assert_eq!((w.terrain_contacts,w.contacts,w.impacts,w.impact),retained);
        }
    }
    #[test] fn stalled_terrain_flight_uses_same_chords_as_regular_steps() {
        let now=Instant::now(); let mut slow=terrain_world(now,100.);
        slow.actors[1].position=[100.,0.,10.]; slow.actors[1].origin=slow.actors[1].position;
        slow.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
        let mut regular=slow.clone();
        slow.advance(now+Duration::from_secs(2)).unwrap();
        for step in 1..=20 { regular.advance(now+STEP*step).unwrap(); }
        assert_eq!(slow.terrain_contacts.len(),1); assert_eq!(regular.terrain_contacts.len(),1);
        assert_eq!(slow.projectiles[0].terminal,regular.projectiles[0].terminal);
        assert_eq!(slow.terrain_contacts[0].segment_start,regular.terrain_contacts[0].segment_start);
        assert_eq!(slow.terrain_contacts[0].segment_end,regular.terrain_contacts[0].segment_end);
        assert_eq!(slow.actors[1].health,90);
        assert!(slow.impact.events().iter().filter(|e|e.stage()==impact::Stage::Segment).count()>1);
    }
    #[test] fn terrain_checks_range_tail_and_history_failure_is_atomic() {
        let now=Instant::now(); let mut w=terrain_world(now,100.);
        w.actors[1].position=[100.,0.,10.]; w.actors[1].origin=w.actors[1].position;
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
        let p=w.projectiles[0]; let offset=p.terminal[2]-p.terminal[1]-0.5;
        w.terrain=terrain_world(now,offset).terrain;
        w.advance(now+Duration::from_secs(3)).unwrap();
        assert_eq!(w.terrain_contacts.len(),1);
        assert!((w.projectiles[0].terminal[2]-p.terminal[2]).abs()<1.);
        assert_eq!(w.actors[1].health,90);
        let mut fail=terrain_world(now,3.);
        fail.terrain_contacts=vec![w.terrain_contacts[0].clone();MAX_SHOTS];
        fail.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
        let before=(fail.actors.clone(),fail.projectiles.clone(),fail.impact.clone(),fail.tick,fail.last,fail.terrain_contacts.clone());
        assert!(fail.advance(now+STEP).is_err());
        assert_eq!((fail.actors,fail.projectiles,fail.impact,fail.tick,fail.last,fail.terrain_contacts),before);
    }
    #[test] fn ap_requires_explicit_prestart_geometry_binding() {
        let now = Instant::now(); let mut w = World::new(44,now).unwrap();
        assert!(w.enable_ap_test_lab().is_err());
        w.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).unwrap();
        w.enable_ap_test_lab().unwrap(); assert!(w.enable_ap_test_lab().is_err());
        assert!(world(now).enable_ap_test_lab().is_err());
    }
    #[test] fn ap_contact_changes_health_once_and_three_hits_destroy() {
        let now = Instant::now(); let mut w = ap_world(now);
        for round in 0..3 {
            let at = now+Duration::from_secs(round*3);
            if round > 0 { w.advance(at).unwrap(); }
            w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],at).unwrap();
            w.advance(at+STEP).unwrap();
            assert_eq!(w.impacts.len(),round as usize+1);
            assert!(matches!(&w.impacts.last().unwrap().outcome,
                ImpactOutcome::Ap(resolution) if resolution.outcome == ap::Outcome::Pierced));
            assert_eq!(w.actors[1].health,60-round as i16*30);
            let before = w.impacts.clone(); w.advance(at+STEP*2).unwrap();
            assert_eq!(w.impacts,before);
        }
        assert_eq!(w.actors[1].input,Input::STOP);
        let at = now+Duration::from_secs(9); w.advance(at).unwrap();
        let ammo = w.actors[1].fire.ammo(); let aim = w.actors[1].aim.clone();
        assert!(w.apply(1,2,&[Command::Aim(aim::Intent::Point([100.,20.,50.])),
            Command::Move(Input{throttle:1,steer:1}),Command::Fire(fire::Command::Shoot)],at).unwrap().is_empty());
        assert_eq!(w.actors[1].fire.ammo(),ammo); assert_eq!(w.actors[1].aim,aim);
        assert_eq!(w.actors[1].input,Input::STOP);
        // Already dead geometry emits one distinct block outcome, not another
        // AP result, health transition, command or death.
        let wreck_before = w.actors[1].clone();
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],at).unwrap();
        w.advance(at+STEP).unwrap(); assert_eq!(w.impacts.len(),4);
        let event = w.impacts.last().unwrap();
        assert_eq!(event.outcome,ImpactOutcome::WreckBlocked);
        assert_eq!((event.shot,event.attacker,event.target,event.health_before,event.health_after),(4,0,1,0,0));
        assert!(event.segment.is_some()); assert_eq!(w.actors[1],wreck_before);
        assert_eq!(w.actors[0].fire.ammo(),16);
        assert_eq!(w.impact.events().iter().filter(|e| matches!(e,impact::Event::ApResolution{..})).count(),3);
        assert_eq!(w.impact.events().iter().filter(|e| matches!(e,impact::Event::WreckImpact{..})).count(),1);
        assert!(matches!(w.impact.events().last(),Some(impact::Event::Terminal {
            shot_id:4,reason:impact::TerminalReason::TestLabWreckImpact,.. })));
        assert_eq!(w.projectiles[3].terminal,w.contacts[3].endpoint); assert!(w.projectiles[3].stopped);
        let impacts = w.impacts.clone(); let trace = w.impact.clone();
        w.advance(at+STEP*2).unwrap(); assert_eq!(w.impacts,impacts); assert_eq!(w.impact,trace);
        let identity = w.actors[1].identity.clone(); w.detach(2).unwrap();
        w.attach(identity,3).unwrap(); assert_eq!(w.actors[1].health,0); assert_eq!(w.actors[1].fire.ammo(),ammo);
    }
    #[test] fn wreck_impact_requires_opt_in_and_does_not_infer_an_ap_result() {
        let now = Instant::now(); let mut w = collision_world(now,false);
        w.actors[1].health = 0; w.actors[1].aim.park();
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
        let dead = w.actors[1].clone(); w.advance(now+STEP).unwrap();
        assert!(w.impacts.is_empty()); assert_eq!(w.actors[1],dead);
        assert_eq!(w.contacts.len(),1); assert!(w.projectiles[0].stopped);
        assert!(matches!(w.impact.events().last(),Some(impact::Event::Terminal {
            reason:impact::TerminalReason::UnresolvedCollision,.. })));
    }
    #[test] fn wreck_impact_capacity_or_material_failure_rolls_back_complete_advance() {
        let now = Instant::now(); let mut w = ap_world(now);
        w.actors[1].health = 0; w.actors[1].aim.park();
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
        w.advance(now+STEP).unwrap(); assert_eq!(w.impacts[0].outcome,ImpactOutcome::WreckBlocked);
        let at = now+Duration::from_secs(3); w.advance(at).unwrap();
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],at).unwrap();
        for invalid_material in [false,true] {
            let mut invalid = w.clone();
            if invalid_material {
                invalid.geometry = Some(Arc::new(super::super::geometry::tests::invalid_material_bundle()));
            } else {
                invalid.impacts.resize(MAX_SHOTS,invalid.impacts[0].clone());
            }
            let before = invalid.clone(); assert!(invalid.advance(at+STEP).is_err());
            assert_eq!(invalid.actors,before.actors); assert_eq!(invalid.impacts,before.impacts);
            assert_eq!(invalid.impact,before.impact); assert_eq!(invalid.contacts,before.contacts);
            assert_eq!(invalid.projectiles,before.projectiles); assert_eq!(invalid.shots,before.shots);
            assert_eq!(invalid.last,before.last); assert_eq!(invalid.tick,before.tick);
        }
    }
    #[test] fn ap_failures_rollback_damage_and_simultaneous_flights_survive_shooter_death() {
        let now = Instant::now(); let mut w = ap_world(now);
        w.actors[0].health=30; w.actors[1].health=30;
        for i in 0..2 { w.apply(i,i as u32+1,&[Command::Fire(fire::Command::Shoot)],now).unwrap(); }
        let mut invalid = w.clone();
        invalid.geometry = Some(Arc::new(super::super::geometry::tests::invalid_material_bundle()));
        let before = invalid.clone(); assert!(invalid.advance(now+STEP).is_err());
        assert_eq!(invalid.actors,before.actors); assert_eq!(invalid.impacts,before.impacts);
        assert_eq!(invalid.impact,before.impact); assert_eq!(invalid.projectiles,before.projectiles);
        w.advance(now+STEP).unwrap();
        assert_eq!(w.actors.iter().map(|a| a.health).collect::<Vec<_>>(),vec![0,0]);
        assert_eq!(w.impacts.iter().map(|e| e.shot).collect::<Vec<_>>(),vec![1,2]);
    }
    #[test] fn nearest_other_actor_surface_stops_both_shooters_atomically() {
        let now = Instant::now(); let mut w = collision_world(now, false);
        for i in 0..2 { w.apply(i, i as u32+1, &[Command::Fire(fire::Command::Shoot)], now).unwrap(); }
        w.advance(now+STEP).unwrap();
        assert_eq!(w.contacts.len(), 2);
        for (i, contact) in w.contacts.iter().enumerate() {
            assert_eq!(contact.target_slot, 1-i); assert_eq!(contact.triangle.candidate_index, 0);
            assert_eq!(contact.triangle.mesh, "Turret_01");
            assert!(w.projectiles[i].stopped); assert_eq!(w.projectiles[i].terminal, contact.endpoint);
            assert!((contact.endpoint[2] - if i==0 {9.5} else {0.5}).abs() < 0.5);
            assert_eq!(w.actors[i].fire.ammo(), 19);
            let facts = &contact.material_facts;
            assert_eq!(facts.component.name(),contact.triangle.mesh);
            assert_eq!(facts.name,contact.triangle.material);
            assert!(w.impact.events().iter().any(|e| matches!(e, impact::Event::MaterialContact {
                shot_id, facts: recorded, .. } if *shot_id==contact.shot && recorded==facts)));
            assert!(w.impact.events().iter().any(|e| matches!(e, impact::Event::Terminal{
                shot_id, reason: impact::TerminalReason::UnresolvedCollision, ..} if *shot_id==i as u32+1)));
        }
        let before = w.contacts.clone(); w.advance(now+STEP*2).unwrap(); assert_eq!(w.contacts, before);
    }
    #[test] fn failed_material_binding_cannot_publish_a_partial_world_or_stop() {
        let now = Instant::now(); let mut w = collision_world(now,false);
        w.geometry = Some(Arc::new(super::super::geometry::tests::invalid_material_bundle()));
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
        let before = w.clone(); assert!(w.advance(now+STEP).is_err());
        assert_eq!(w.tick,before.tick); assert_eq!(w.last,before.last);
        assert_eq!(w.actors,before.actors); assert_eq!(w.projectiles,before.projectiles);
        assert_eq!(w.contacts,before.contacts); assert_eq!(w.impact,before.impact);
        assert_eq!(w.shots,before.shots); assert!(!w.projectiles[0].stopped);
    }
    #[test] fn full_ammo_real_cadence_hits_and_self_excluding_misses_fit_trace() {
        for miss in [false, true] {
            let now = Instant::now(); let mut w = collision_world(now, miss);
            for step in 0..=600 {
                let at = now + STEP*step;
                if step > 0 { w.advance(at).unwrap(); }
                if step < 600 && step % 30 == 0 {
                    for i in 0..2 { w.apply(i, i as u32+1, &[Command::Fire(fire::Command::Shoot)], at).unwrap(); }
                }
            }
            assert_eq!(w.shots.len(), 40); assert_eq!(w.impact.terminal_shots().len(), 40);
            assert_eq!(w.contacts.len(), if miss {0} else {40});
            assert!(w.impact.events().len() < impact::MAX_EVENTS);
            assert!(w.projectiles.iter().all(|p| p.stopped));
            assert!(w.actors.iter().all(|a| a.fire.ammo()==0));
        }
    }
    #[test] fn invalid_geometry_pose_rolls_back_world_trace_and_contact() {
        let now = Instant::now(); let mut w = collision_world(now, false);
        w.apply(0, 1, &[Command::Fire(fire::Command::Shoot)], now).unwrap();
        let before = w.clone();
        assert!(w.advance_with_external(now+STEP, Some(&[(0,[0.;3],[0.;3],0.),
            (1,[3000.,0.,10.],[0.;3],0.)])).is_err());
        assert_eq!(w.actors,before.actors); assert_eq!(w.projectiles,before.projectiles);
        assert_eq!(w.impact,before.impact); assert_eq!(w.contacts,before.contacts);
        assert_eq!(w.last,before.last); assert_eq!(w.tick,before.tick);
        assert!(w.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).is_err());
    }
    #[test] fn fractional_range_tail_is_queried_before_expiry_and_duration_is_clamped() {
        let now = Instant::now(); let mut w = collision_world(now, true);
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
        let projectile = w.projectiles[0]; let end = projectile.end_at().unwrap();
        // Native speed produces range expiry between ticks20 and21.
        assert!(end > now+STEP*20 && end < now+STEP*21-Duration::from_millis(1));
        let near_end = projectile.position_at(end-Duration::from_millis(3));
        let target = [near_end[0]+0.236366, near_end[1]-1.55107, near_end[2]];
        w.actors[1].position = target; w.actors[1].origin = target;
        for n in 1..=20 { w.advance(now+STEP*n).unwrap(); }
        assert!(!w.projectiles[0].stopped); assert!(w.contacts.is_empty());
        w.advance(end+Duration::from_millis(1)).unwrap();
        assert!(!w.projectiles[0].stopped); // tail deliberately awaits its query
        w.advance(now+STEP*21).unwrap();
        assert!(w.projectiles[0].stopped); assert_eq!(w.contacts.len(),1);
        let contact = &w.contacts[0];
        assert_eq!(contact.target_slot,1);
        assert!((contact.segment_seconds-(end-(now+STEP*20)).as_secs_f32()).abs()<1e-7);
        assert!((contact.segment_end[2]-projectile.terminal[2]).abs()<1e-5);
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
    #[test] fn integrated_survivor_keeps_motion_aim_and_flight_when_peer_disconnects() {
        let now=Instant::now(); let mut w=ap_world(now); w.actors[1].health=0;
        w.detach(2).unwrap(); let parked=w.actors[1].clone();
        w.apply(0,1,&[Command::Aim(aim::Intent::Hold{yaw:1.,pitch:0.})],now).unwrap();
        let rows=[(0,[0.,0.,1.],[0.1,0.,0.],1.),(1,parked.position,parked.direction,0.)];
        w.advance_with_external(now+STEP,Some(&rows)).unwrap();
        assert_eq!(w.tick,1001); assert_eq!(w.actors[0].position,[0.,0.,1.]);
        assert!(w.actors[0].aim.yaw>0.); assert_eq!(w.actors[1],parked);
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now+STEP).unwrap();
        w.advance_with_external(now+STEP*2,Some(&rows)).unwrap();
        assert!(w.impact.events().iter().any(|e| matches!(e,impact::Event::Segment{..})));
        let before=w.clone(); let mut bad_rows=rows; bad_rows[1].1[0]+=1.;
        assert!(w.advance_with_external(now+STEP*3,Some(&bad_rows)).is_err());
        assert_eq!(w.actors,before.actors); assert_eq!(w.tick,before.tick);
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
