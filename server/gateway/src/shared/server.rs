//! Bounded two-session native dispatcher. Authentication and channel replay
//! policy are shared with the accepted gateway; no unauthenticated lab login.
use super::{model::{self, World}, ap, impact_wire, terrain_wire, wire, Client, Phase};
use super::super::*;
use crate::map_profile091::MapId;
use super::vehicle_profile::VehicleKind;
use super::ram_proof;
use std::path::{Path,PathBuf};
#[path="profile13_dispatch.rs"]
mod profile13_dispatch;
#[path="owner_hold_delivery.rs"]
mod owner_hold_delivery;
#[path="server_scene_runtime.rs"]
mod batch_scene;
use batch_scene::BatchRuntime;
#[path="p06t_publication.rs"]
mod p06t_publication;
#[path="sixth_sense_wire.rs"]
mod sixth_sense_wire;
#[cfg(test)]
#[path="detached_turret_server_tests.rs"]
mod detached_turret_server_tests;
#[path="p10b_ready_host.rs"]
mod p10b_ready_host;
#[path="p10b_receive_host.rs"]
mod p10b_receive_host;
#[path="p10b_launch_host.rs"]
mod p10b_launch_host;
#[path="p10b_preparing_host.rs"]
mod p10b_preparing_host;
#[path="p10b_host.rs"]
mod p10b_host;
#[path="server_login_admission.rs"]
mod login_admission;
#[path="server_arena.rs"]
mod arena;
#[path="server_containment.rs"]
mod containment;
#[cfg(test)]
#[path="server_arena_bench.rs"]
mod arena_bench;
#[cfg(test)]
#[path="server_bot01_bench.rs"]
mod bot01_bench;
#[cfg(test)]
#[path="server_spawn15_real_tests.rs"]
mod spawn15_real_tests;
#[cfg(test)]
#[path="server_turret01_real_tests.rs"]
mod turret01_real_tests;
use login_admission::{AccountTag,Admission,Decision,Writers};

#[cfg(test)]
#[path="server_visibility_tests.rs"]
mod visibility_tests;
#[cfg(test)]
#[path="server_net01_tests.rs"]
mod net01_tests;
#[cfg(test)]
#[path="server_av01_tests.rs"]
mod av01_tests;
#[cfg(test)]
#[path="server_net01_bench.rs"]
mod net01_bench;

#[cfg(test)]
#[path="server_catalog_tests.rs"]
mod catalog_tests;
#[cfg(test)]
#[path="server_catalog_wire_tests.rs"]
mod catalog_wire_tests;
#[cfg(test)]
use crate::worker_fixtures091 as worker_fixtures;
#[cfg(test)]
#[path="server_contact_barrier_tests.rs"]
mod contact_barrier_tests;
#[cfg(test)]
#[path="server_angular_tests.rs"]
mod angular_tests;
#[cfg(test)]
#[path="server_angular_real_tests.rs"]
mod angular_real_tests;
#[cfg(test)]
#[path="server_cadence_tests.rs"]
mod cadence_tests;
#[cfg(test)]
#[path="server_fracture_real_tests.rs"]
mod fracture_real_tests;
#[cfg(test)]
#[path="server_fence_total_real_tests.rs"]
mod fence_total_real_tests;
#[cfg(test)]
#[path="server_is7_real_tests.rs"]
mod is7_real_tests;
#[cfg(test)]
#[path="server_map_registry_real_tests.rs"]
mod map_registry_real_tests;
#[cfg(test)]
#[path="server_falling_atom_real_tests.rs"]
mod falling_atom_real_tests;
#[cfg(test)]
#[path="server_whole_fracture_real_tests.rs"]
mod whole_fracture_real_tests;
#[cfg(test)]
#[path="server_capacity_tests.rs"]
mod capacity_tests;
#[cfg(test)]
#[path="server_bot01_tests.rs"]
mod bot01_tests;
#[path="server_matchmaker.rs"]
mod matchmaking;
#[cfg(test)]
#[path="server_mm01_tests.rs"]
mod mm01_tests;

/// `capacity` bounds connections. With `arena_split` (GW-01) it is separate
/// from the arena: a hangar session holds no arena place; places are taken by
/// Join reservations up to `world.expected_actors()`. Without it, every
/// session must be in the arena before a battle starts (old path).
/// ARENA-01 `multi_arena`: more than one arena shares this table; failure
/// containment then touches only the sessions of the failed battle.
struct Table { sessions: Vec<Session>, retirement: RetirementWindow,capacity:usize,arena_split:bool,multi_arena:bool }
impl Default for Table {fn default()->Self{Self{sessions:Vec::new(),retirement:RetirementWindow::default(),capacity:model::CAPACITY,arena_split:false,multi_arena:false}}}
/// GW-01 per-socket datagram drain per loop tick when `connection_capacity` is set.
const CAPACITY_DRAIN:usize=64;

/// A consumed worker reply must survive other lanes' pending replies. There
/// is at most one unconsumed advance per lane, and 32 contacts across all lanes.
struct ContactBatch {
    session: u32,
    generation: u32,
    seq: u32,
    scene_version: u32,
    contacts: Vec<model::VehicleContactInput>,
    observed_contacts:usize,
}

/// Owns one accepted P05 worker per shared actor. The handles live outside
/// `World` because `World` is cloned for atomic packet application; cloning a
/// worker would duplicate process authority. Every imported row is copied into
/// the next world snapshot only after the worker contract has validated it.
struct IntegratedRuntime {
    batch:Option<BatchRuntime>,
    pool: Arc<crate::map_drive_worker091::Pool>,
    map_id: MapId,
    workers: [Option<crate::map_drive_worker091::Worker>; model::CAPACITY],
    poses: [Option<([f32; 3], [f32; 3], f32)>; model::CAPACITY],
    // One validated advance per lane may wait for its peer/native tick. Never
    // overwrite it with a catch-up reply or publish the same source twice.
    pose_pending: [bool; model::CAPACITY],
    offsets: [[f32; 3]; model::CAPACITY],
    anchored: [bool; model::CAPACITY],
    // Logical100ms deadlines, not the wall time at which the loop sent IPC.
    dispatched: [Option<Instant>; model::CAPACITY],
    started: bool,
    removal: Option<crate::map_drive_worker091::RemovalSpec>,
    catalog: Option<crate::map_drive_worker091::CatalogSpec>,
    staged: Option<World>,
    synchronizing: [bool; model::CAPACITY],
    generations: [u32; model::CAPACITY],
    worker_sessions: [Option<u32>; model::CAPACITY],
    contact_sequences: [u32; model::CAPACITY],
    contact_batches: [Option<ContactBatch>; model::CAPACITY],
    lag_resync: [LagResync; model::CAPACITY],
}

/// A worker frame may be compared with a client frame in focused tests, but an
/// integrated session now starts each worker at its own map lane. Only the
/// tiny settle drift from that requested lane is anchored. Applying the old
/// cross-terrain X/Z translation would retain a different terrain height while
/// keeping worker Y, which was the airborne-tank bug.
fn worker_frame_offset(client_spawn: [f32; 3], worker_spawn: [f32; 3]) -> [f32; 3] {
    [client_spawn[0] - worker_spawn[0], 0., client_spawn[2] - worker_spawn[2]]
}

fn worker_frame_position(worker_position: [f32; 3], offset: [f32; 3]) -> [f32; 3] {
    [worker_position[0] + offset[0], worker_position[1], worker_position[2] + offset[2]]
}

fn drive_grid(start: Instant, now: Instant) -> io::Result<Instant> {
    let elapsed = now.checked_duration_since(start).ok_or_else(|| model::bad())?;
    let step = crate::map_drive_worker091::STEP;
    let ticks = elapsed.as_nanos() / step.as_nanos();
    let ticks: u32 = ticks.try_into().map_err(|_| model::bad())?;
    start.checked_add(step.checked_mul(ticks).ok_or_else(|| model::bad())?).ok_or_else(|| model::bad())
}

/// Profile13 resets its World for every battle (each bounded by model::LIFETIME),
/// so the hangar service itself may stay up for an owner session. The 1 h
/// process stop made a stand started ahead of the owner's test exit on its
/// own (full-test 2026-10-19). Single-world labs keep model::LIFETIME.
const PROFILE13_SERVICE_LIFETIME: Duration = Duration::from_secs(12 * 3600);
/// Single gateway-loop stall longer than this still closes the battle.
const MAX_STALL: Duration = Duration::from_secs(5);
/// More than `MAX_RESYNCS` lag recoveries inside this window is persistent overload.
const RESYNC_WINDOW: Duration = Duration::from_secs(30);
const MAX_RESYNCS: u32 = 3;

/// Bounded, logged recovery from a transient gateway-loop stall. The owner
/// runs of 2026-10-17/19 lost whole battles to one >500 ms stall with healthy
/// workers. A stall up to MAX_STALL rebases the logical deadline onto the
/// current grid (the skipped steps are not simulated; the domain tick already
/// follows wall time) and prints SHARED_DRIVE_LAG_RESYNC. Longer stalls and
/// repeated recoveries remain fail-closed overload.
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub(super) struct LagResync { window: Option<Instant>, count: u32 }

fn drive_deadline(start: Instant, previous: Option<Instant>, now: Instant, resync: &mut LagResync) -> io::Result<Option<Instant>> {
    let deadline = match previous {
        Some(previous) => previous.checked_add(crate::map_drive_worker091::STEP).ok_or_else(|| model::bad())?,
        None => drive_grid(start, now)?,
    };
    if now < deadline { return Ok(None); }
    // Engineering overload bound, shared with the existing worker contract.
    // Ordinary latency cannot silently reset simulation time or burst forever.
    let lag = now.duration_since(deadline);
    if lag <= crate::map_drive_worker091::MAX_LAG { return Ok(Some(deadline)); }
    if lag > MAX_STALL {
        return Err(io::Error::new(io::ErrorKind::TimedOut, "integrated drive logical deadline lag exceeds5s; fail closed"));
    }
    if resync.window.is_none_or(|window| now.duration_since(window) > RESYNC_WINDOW) {
        *resync = LagResync { window: Some(now), count: 0 };
    }
    resync.count += 1;
    if resync.count > MAX_RESYNCS {
        return Err(io::Error::new(io::ErrorKind::TimedOut,
            "integrated drive logical deadline lag exceeds500ms repeatedly; fail closed"));
    }
    let grid = drive_grid(start, now)?;
    println!("SHARED_DRIVE_LAG_RESYNC lag_ms={} skipped_steps={} resyncs_in_window={} max_resyncs={}",
        lag.as_millis(), grid.duration_since(deadline).as_millis() / crate::map_drive_worker091::STEP.as_millis(),
        resync.count, MAX_RESYNCS);
    Ok(Some(grid))
}

impl IntegratedRuntime {
    fn new(pool: Arc<crate::map_drive_worker091::Pool>) -> Self {
        Self::new_for_map(pool, MapId::Karelia)
    }

    fn new_for_map(pool: Arc<crate::map_drive_worker091::Pool>, map_id: MapId) -> Self {
        Self { batch:None,pool, map_id, workers: std::array::from_fn(|_| None), poses: [None; model::CAPACITY],
            pose_pending: [false; model::CAPACITY],
            offsets: [[0.; 3]; model::CAPACITY],
            anchored: [false; model::CAPACITY],
            dispatched: [None; model::CAPACITY], started: false, removal: None,catalog:None, staged: None, synchronizing: [false; model::CAPACITY], generations: [0; model::CAPACITY],
            worker_sessions: [None; model::CAPACITY], contact_sequences: [0; model::CAPACITY],
            contact_batches: std::array::from_fn(|_| None), lag_resync: [LagResync::default(); model::CAPACITY] }
    }

    fn map(&self) -> io::Result<crate::map_drive_worker091::MapSpec> {
        selected_pool_map(&self.pool, self.map_id).cloned()
    }

    fn lane_spawn(map: &crate::map_drive_worker091::MapSpec, slot: usize) -> [f32; 3] {
        [map.spawn[0] + if slot == 0 { -4. } else { 4. }, map.spawn[1], map.spawn[2]]
    }

    fn clear_slot(&mut self, slot: usize) {
        self.workers[slot].take();
        self.poses[slot] = None;
        self.pose_pending[slot] = false;
        self.anchored[slot] = false;
        self.dispatched[slot] = None;
        self.worker_sessions[slot] = None;
        self.contact_sequences[slot] = 0;
        self.contact_batches[slot] = None;
    }

    fn spawn_slot(&mut self, world: &World, slot: usize, map: crate::map_drive_worker091::MapSpec,
        now: Instant) -> io::Result<()> {
        if world.map != self.map_id || map.asset != self.map_id.asset()
            || world.vehicle_kind()!=self.pool.vehicle_kind()
            || map.arena_type_id != self.map_id.arena_type_id()
            || self.workers[slot].is_some() { return Err(model::bad()); }
        let lane = Self::lane_spawn(&map, slot);
        self.offsets[slot] = [0.; 3];
        self.anchored[slot] = false;
        self.dispatched[slot] = None;
        self.worker_sessions[slot] = world.actors.get(slot).and_then(|a| a.session);
        self.pose_pending[slot] = false;
        if self.worker_sessions[slot].is_none() { return Err(model::bad()); }
        self.contact_sequences[slot] = 0;
        self.contact_batches[slot] = None;
        self.generations[slot] = self.generations[slot].checked_add(1).ok_or_else(|| model::bad())?;
        let generation = self.generations[slot].checked_mul(2).and_then(|n|n.checked_add(slot as u32)).ok_or_else(|| model::bad())?;
        let worker = if let Some(spec)=&self.catalog {
            let scene=crate::map_drive_worker091::Scene::new(spec,&world.fragiles.as_ref().ok_or_else(|| model::bad())?.removed_ids())?;
            crate::map_drive_worker091::Worker::launch_with_catalog(self.pool.clone(),map.clone(),generation,now,Some(lane),spec.clone(),scene)?
        }else if let Some(spec) = &self.removal {
            crate::map_drive_worker091::Worker::launch_with_removal(self.pool.clone(), map.clone(),
                generation, now, Some(lane), spec.clone())?
        } else {
            crate::map_drive_worker091::Worker::launch_at_spawn(self.pool.clone(), map.clone(),
                generation, now, Some(lane))?
        };
        println!("SHARED_INTEGRATED_WORKER_START battle={} slot={} map={} arena_type_id={} config_sha256={} pool_sha256={} physics=test_lab coordinate_bridge=worker_lane_full_pose_bridge=position_ypr spawn_override={:?} offset={:?}",
            world.id, slot, map.asset, map.arena_type_id, map.config_sha256, self.pool.sha256, lane, self.offsets[slot]);
        self.workers[slot] = Some(worker);
        Ok(())
    }

    fn start(&mut self, world: &mut World, now: Instant) -> io::Result<()> {
        if let Some(batch)=&mut self.batch{batch.start(world,now)?;self.started=true;return Ok(());}
        if world.map != self.map_id || world.vehicle_kind()!=self.pool.vehicle_kind()
            || self.started || world.actors.len() != model::CAPACITY
            || world.started.is_none() { return Err(model::bad()); }
        let map = self.map()?;
        let lane_spawns: [[f32;3];model::CAPACITY] = std::array::from_fn(|slot| {
            Self::lane_spawn(&map, slot)
        });
        // Native announcements are emitted later in this same loop. Rebase
        // before that happens so no old flat-lab spawn can reach the client.
        world.rebase_external_spawns(lane_spawns)?;
        for slot in 0..model::CAPACITY {
            self.spawn_slot(world, slot, map.clone(), now)?;
        }
        self.started = true;
        Ok(())
    }

    fn ready_for_native(&self) -> bool {
        if let Some(batch)=&self.batch{return batch.ready_for_native();}
        !self.blocked() && !self.synchronizing.iter().any(|v|*v) && self.workers.iter().all(|worker| worker.as_ref().is_some_and(|value| value.ready()))
    }

    fn blocked(&self) -> bool {if let Some(batch)=&self.batch{return batch.blocked();} self.staged.is_some() || self.workers.iter().flatten().any(|worker|!worker.prepared_ids().is_empty()) }

    fn resume_after_scene_ack(&mut self, world: &World, now: Instant) -> io::Result<()> {
        let grid = drive_grid(world.started.ok_or_else(|| model::bad())?, now)?;
        // This is an intentional transaction pause, not worker overload. Keep
        // any early unpublished pose; only the schedule rebases after all ACKs.
        for slot in 0..model::CAPACITY {
            if self.dispatched[slot].is_some() { self.dispatched[slot] = Some(grid); }
        }
        Ok(())
    }

    fn finish_catalog(&mut self,world:&mut World,now:Instant)->io::Result<()>{
        let staged=self.staged.as_ref().ok_or_else(|| model::bad())?;
        if staged.map!=world.map||world.map!=self.map_id||staged.vehicle_kind()!=world.vehicle_kind()
            ||world.vehicle_kind()!=self.pool.vehicle_kind()||staged.id!=world.id||staged.scene_version()<=world.scene_version()
            ||staged.actors.iter().map(|a|a.session).collect::<Vec<_>>()!=world.actors.iter().map(|a|a.session).collect::<Vec<_>>(){
            return Err(io::Error::new(io::ErrorKind::InvalidData,"catalog transaction membership or scene changed; fail closed"));}
        let scene=crate::map_drive_worker091::Scene::new(self.catalog.as_ref().ok_or_else(|| model::bad())?,
            &staged.fragiles.as_ref().ok_or_else(|| model::bad())?.removed_ids())?;
        if self.workers.iter().flatten().any(|worker|worker.prepared_ids().iter().any(|id|scene.ids().binary_search(id).is_err())) {
            return Err(io::Error::new(io::ErrorKind::InvalidData,"candidate omits prepared worker fracture; fail closed"));
        }
        let mut complete=true;let mut participants=0;
        for slot in 0..model::CAPACITY{
            if world.actors[slot].session.is_none(){continue;}
            let worker=self.workers[slot].as_mut().ok_or_else(|| model::bad())?;
            if !worker.ready(){
                if world.actors[slot].ready||self.anchored[slot]||self.poses[slot].is_some(){return Err(model::bad());}continue;
            }
            participants+=1;
            if worker.poll(now)?.is_some(){return Err(model::bad());}
            if let Some(ack)=worker.take_catalog_ack(){println!("SHARED_CATALOG_WORKER_ACK battle={} slot={} generation={} advance_seq={} tick={} scene_version={} scene_sha256={} removed={:?}",
                world.id,slot,ack.generation,ack.advance_seq,ack.tick,ack.scene_version,ack.scene_sha256,ack.removed_object_ids);}
            if worker.catalog_scene()!=Some(&scene){complete=false;if !worker.pending(){worker.sync_removed(scene.clone(),now)?;}}
        }
        if participants==0{return Err(model::bad());}
        if complete{let before=world.scene_version();self.resume_after_scene_ack(world,now)?;*world=self.staged.take().ok_or_else(|| model::bad())?;
            println!("SHARED_CATALOG_COMMITTED battle={} scene_before={} scene_after={} scene_sha256={} removed={:?} participating_workers={} workers_acknowledged=true",world.id,before,scene.version(),scene.hash(),scene.ids(),participants);}
        Ok(())
    }

    /// Both movement scenes acknowledge before the candidate World, impacts or
    /// native destruction can be published. Transport remains serviced outside.
    fn finish_removal(&mut self, world: &mut World, now: Instant) -> io::Result<()> {
        if self.catalog.is_some(){return self.finish_catalog(world,now);}
        let staged = self.staged.as_ref().ok_or_else(|| model::bad())?;
        if staged.map != world.map || world.map != self.map_id || staged.id != world.id || staged.scene_version() != 1 || world.scene_version() != 0
            || staged.actors.iter().map(|a| a.session).collect::<Vec<_>>()
                != world.actors.iter().map(|a| a.session).collect::<Vec<_>>() {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "destructible transaction membership changed; fail closed"));
        }
        let mut complete = true;
        let mut participants = 0;
        for slot in 0..model::CAPACITY {
            if world.actors[slot].session.is_none() { continue; }
            let worker = self.workers[slot].as_mut().ok_or_else(|| model::bad())?;
            // A starting reconnect has supplied no authoritative pose and is
            // gated from native entry. Restore it to scene1 in the regular path.
            if !worker.ready() {
                if world.actors[slot].ready || self.anchored[slot] || self.poses[slot].is_some() { return Err(model::bad()); }
                continue;
            }
            participants += 1;
            // All advance replies were incorporated before staging. A pose
            // here would invalidate the contact snapshot; never silently discard it.
            if worker.poll(now)?.is_some() { return Err(model::bad()); }
            if let Some(ack) = worker.take_removal_ack() {
                println!("SHARED_DESTRUCTIBLE_WORKER_ACK battle={} slot={} generation={} advance_seq={} tick={} scene_version={} descriptor_sha256={}",
                    world.id, slot, ack.generation, ack.advance_seq, ack.tick, ack.scene_version, ack.descriptor_sha256);
            }
            if worker.scene_version() != 1 {
                complete = false;
                if worker.ready() && !worker.pending() { worker.remove_one(now)?; }
            }
        }
        if participants == 0 { return Err(model::bad()); }
        if complete {
            self.resume_after_scene_ack(world, now)?;
            *world = self.staged.take().ok_or_else(|| model::bad())?;
            let event = world.destructible_transition().ok_or_else(|| model::bad())?;
            println!("SHARED_DESTRUCTIBLE_COMMITTED battle={} shot={} tick={} instance_id={} scene_before=0 scene_after=1 participating_workers={} workers_acknowledged=true", world.id, event.shot, event.tick, event.instance_id,participants);
        }
        Ok(())
    }

    fn step(&mut self, world: &mut World, now: Instant) -> io::Result<()> {
        if let Some(batch)=&mut self.batch{return batch.step(world,now);}
        if world.map != self.map_id || world.vehicle_kind()!=self.pool.vehicle_kind()
            || self.workers.iter().flatten().any(|worker|
            worker.map.asset != self.map_id.asset() || worker.map.arena_type_id != self.map_id.arena_type_id()) {
            return Err(model::bad());
        }
        if world.started.is_none() { return Ok(()); }
        if self.staged.is_some() { return self.finish_removal(world, now); }
        self.synchronizing = [false; model::CAPACITY];
        let mut rows = Vec::new();
        // Revoke every departed slot before admitting another reply against
        // the aggregate bound; iteration order must not retain a stale batch.
        for slot in 0..model::CAPACITY {
            let session = world.actors.get(slot).and_then(|a| a.session);
            // Detach and reattach may occur between two runtime steps. Bind
            // worker ownership to the transport session, not just its slot.
            if self.worker_sessions[slot] != session || session.is_none() { self.clear_slot(slot); }
        }
        for slot in 0..model::CAPACITY {
            let session = world.actors.get(slot).and_then(|a| a.session);
            if session.is_none() {
                if let Some(actor) = world.actors.get(slot) {
                    rows.push((slot,actor.position,actor.direction,0.));
                }
                continue;
            }
            if self.workers[slot].is_none() {
                let map = self.map()?;
                world.reset_external_spawn(slot, Self::lane_spawn(&map, slot))?;
                self.spawn_slot(world, slot, map, now)?;
            }
            let worker = self.workers[slot].as_mut().ok_or_else(|| model::bad())?;
            if let Some(state) = worker.poll(now)? {
                // seq0 is the stationary startup/settle snapshot, not a game
                // advance. Only subsequent replies may supply gameplay hits.
                if state.seq != 0 {
                    let held: usize = self.contact_batches.iter().flatten().map(|b| b.observed_contacts).sum();
                    if self.pose_pending[slot] || self.contact_batches[slot].is_some()
                        || state.seq != self.contact_sequences[slot].checked_add(1).ok_or_else(|| model::bad())?
                        || state.scene_version != world.scene_version()
                        || held + state.object_contacts.len() > 32 { return Err(model::bad()); }
                    let frame=if let Some(proof)=&state.angular_proof {
                        let domain=world.fragiles.as_ref().ok_or_else(|| model::bad())?;
                        let scene=worker.catalog_scene().ok_or_else(|| model::bad())?;
                        Some(Arc::new(ram_proof::ContextFrame{proof:proof.clone(),context:ram_proof::Context{
                            battle:world.id,slot,session:session.ok_or_else(|| model::bad())?,generation:worker.generation,
                            seq:state.seq,tick:state.tick,config_sha256:worker.map.config_sha256.clone(),
                            catalog_sha256:domain.catalog.worker_sha256.clone(),domain_sha256:domain.catalog.sha256.clone(),
                            scene_version:scene.version(),scene_sha256:scene.hash().into()}}))
                    }else{None};
                    let mut contacts = state.object_contacts.iter().filter(|contact|frame.as_ref().is_none_or(|frame|frame.proof.receipts.iter().any(|r|r.object_id==contact.object_id))).map(|contact| {
                        let proof=if let Some(frame)=&frame {Some(ram_proof::ContactProof{frame:frame.clone(),
                            index:frame.proof.receipts.iter().position(|r|r.object_id==contact.object_id).ok_or_else(|| model::bad())?})}else{None};
                        Ok(model::VehicleContactInput {object_id: contact.object_id, substep: contact.substep, point: contact.point,
                            normal: contact.normal, velocity: contact.velocity, mass_kg: worker.map.mass_kg,
                            kind: contact.kind.clone(), shooter: slot,proof})
                    }).collect::<io::Result<Vec<_>>>()?;
                    if frame.is_some(){contacts.sort_by_key(|contact|contact.proof.as_ref().map(|p|p.index));}
                    self.contact_sequences[slot] = state.seq;
                    self.pose_pending[slot] = true;
                    self.contact_batches[slot] = Some(ContactBatch { session: session.ok_or_else(|| model::bad())?,
                        generation: worker.generation, seq: state.seq, scene_version: state.scene_version, contacts,observed_contacts:state.object_contacts.len() });
                    for receipt in &state.fractures {
                        println!("SHARED_FENCE_RESPONSE {}",serde_json::json!({"battle":world.id,
                            "slot":slot,"generation":worker.generation,"seq":state.seq,
                            "scene_version":state.scene_version,"mass_kg":worker.map.mass_kg,
                            "config_sha256":worker.map.config_sha256,"object_id":receipt.object_id,
                            "order":receipt.order,"substep":receipt.substep,"energy_j":receipt.energy_j,
                            "prevelocity":receipt.velocity,"shadow_before":receipt.budget_before,
                            "shadow_after":receipt.budget_after,"solver_before":receipt.solver_before,
                            "solver_after":receipt.solver_after,"status":"validated_preparation"}));
                    }
                }
                if state.seq == 0 {
                    let actor = world.actors.get(slot).ok_or_else(|| model::bad())?;
                    self.offsets[slot] = worker_frame_offset(actor.position, state.pose.position);
                    self.anchored[slot] = true;
                    println!("SHARED_INTEGRATED_WORKER_READY battle={} slot={} process_id={} map={} worker_tick={} settled_position={:?} direction={:?} contacts={} wheel_contact_masks={:?} anchor_offset={:?}",
                        world.id, slot, worker.process_id().ok_or_else(|| model::bad())?, worker.map.asset,
                        state.tick, state.pose.position, state.pose.direction, state.pose.contacts, state.pose.wheel_contact_masks,
                        self.offsets[slot]);
                }
                if !self.anchored[slot] { return Err(model::bad()); }
                let position = worker_frame_position(state.pose.position, self.offsets[slot]);
                if position.iter().any(|v| !v.is_finite()) || state.pose.direction.iter().any(|v| !v.is_finite()) {
                    return Err(model::bad());
                }
                self.poses[slot] = Some((position, state.pose.direction, state.pose.speed));
                rows.push((slot, position, state.pose.direction, state.pose.speed));
            } else if let Some((position, direction, speed)) = self.poses[slot] {
                rows.push((slot, position, direction, speed));
            } else if world.tick != 1000 {
                let actor=&world.actors[slot];
                rows.push((slot,actor.position,actor.direction,0.));
            }
        }
        let mut rejoin_ack = false;
        if self.catalog.is_some(){
            let scene=crate::map_drive_worker091::Scene::new(self.catalog.as_ref().unwrap(),&world.fragiles.as_ref().ok_or_else(|| model::bad())?.removed_ids())?;
            for slot in 0..model::CAPACITY{
                if world.actors[slot].session.is_none(){continue;}
                let worker=self.workers[slot].as_mut().ok_or_else(|| model::bad())?;
                if let Some(ack)=worker.take_catalog_ack(){rejoin_ack=true;println!("SHARED_CATALOG_REJOIN_ACK battle={} slot={} scene_version={} scene_sha256={}",world.id,slot,ack.scene_version,ack.scene_sha256);}
                if worker.catalog_scene()!=Some(&scene){
                    self.synchronizing[slot]=true;
                    if worker.ready()&&!worker.pending(){worker.sync_removed(scene.clone(),now)?;}
                }
            }
        }else if world.scene_version() == 1 {
            for slot in 0..model::CAPACITY {
                if world.actors[slot].session.is_none() { continue; }
                let worker = self.workers[slot].as_mut().ok_or_else(|| model::bad())?;
                if let Some(ack) = worker.take_removal_ack() {
                    rejoin_ack = true;
                    println!("SHARED_DESTRUCTIBLE_REJOIN_ACK battle={} slot={} scene_version={}",world.id,slot,ack.scene_version);
                }
                if worker.scene_version() != 1 {
                    self.synchronizing[slot] = true;
                    if worker.ready() && !worker.pending() { worker.remove_one(now)?; }
                }
            }

        }
        // Restoring a reconnect also intentionally drains the paired movement
        // snapshot. Its bounded ACK wait must not become ordinary drive debt.
        if rejoin_ack { self.resume_after_scene_ack(world, now)?; }
        for (slot,position,direction,speed) in &rows {
            if !world.actors[*slot].ready && world.actors[*slot].session.is_some()
                && !self.synchronizing[*slot] && self.anchored[*slot] && !self.blocked() {
                world.import_unready_external_pose(*slot,*position,*direction,*speed)?;
                self.pose_pending[*slot] = false;
            }
        }
        // A contact candidate can only use a fully drained movement snapshot.
        // Restoring a reconnect worker does not suspend the survivor's commands.
        if (self.catalog.is_some()||self.removal.is_some() && world.scene_version()==0)
            && self.workers.iter().flatten().any(|w|w.pending()) { return Ok(()); }
        // Do not publish a mixed frame while the two workers are settling.
        // The old client-space spawn is deliberately not a fallback pose:
        // waiting one bounded loop keeps the second actor from appearing at
        // the laboratory Y for a single tick before its worker is ready.
        if rows.len() != model::CAPACITY {
            return Ok(());
        }
        if world.tick == 1000 && world.actors.iter().any(|actor| actor.session.is_some() && !actor.ready) {
            if self.blocked(){return Err(io::Error::new(io::ErrorKind::InvalidData,
                "prepared fracture before initial native readiness; fail closed"));}
            // The native arena has not completed its ready handshake yet, but
            // its first announcement must still use the settled worker pose.
            // Before first battle both actors must settle; later a reconnect
            // must not freeze the already playing survivor.
            if world.actors.iter().all(|actor| actor.session.is_some()) {
                world.import_external_poses(&rows)?;
            }
            return Ok(());
        }
        // Validate scheduling before mutating the published World. A fresh
        // source must not turn into a final successful snapshot on overload.
        let mut deadlines = [None; model::CAPACITY];
        for slot in 0..model::CAPACITY {
            if world.actors[slot].session.is_some() && !self.synchronizing[slot]
                && self.workers[slot].as_ref().is_some_and(|w| w.ready() && !w.pending()) {
                deadlines[slot] = drive_deadline(world.started.ok_or_else(|| model::bad())?, self.dispatched[slot], now, &mut self.lag_resync[slot])?;
            }
        }
        let fresh_pair = world.actors.iter().enumerate().all(|(slot, actor)|
            actor.session.is_none() || !actor.ready || self.pose_pending[slot]);
        // Vacuously true only when every actor is parked/unready: preserve the
        // existing projectile/world clock without moving any cached actor.
        let mut candidate = world.clone();
        if self.catalog.as_ref().is_some_and(|catalog|catalog.version()==8) {
            for slot in 0..model::CAPACITY {
                if let Some(session)=world.actors.get(slot).and_then(|a|a.session) {
                    let worker=self.workers[slot].as_ref().ok_or_else(|| model::bad())?;
                    candidate.bind_contact_source(slot,ram_proof::Source{session,generation:worker.generation,
                        config_sha256:worker.map.config_sha256.clone(),profile:ram_proof::Profile::for_vehicle(self.pool.vehicle_kind())})?;
                }else{candidate.revoke_contact_source(slot)?;}
            }
        }
        let published = fresh_pair && candidate.advance_with_external(now, Some(&rows))?;
        let mut vehicle_contacts = Vec::new();
        for (slot, batch) in self.contact_batches.iter().enumerate() {
            if let Some(batch) = batch {
                let worker = self.workers[slot].as_ref().ok_or_else(|| model::bad())?;
                if world.actors[slot].session != Some(batch.session)
                    || self.worker_sessions[slot] != Some(batch.session)
                    || worker.generation != batch.generation || batch.seq != self.contact_sequences[slot]
                    || batch.scene_version != world.scene_version() || worker.scene_version() != batch.scene_version {
                    return Err(model::bad());
                }
                if let Some(proof)=batch.contacts.first().and_then(|contact|contact.proof.as_ref()) {
                    let source=world.fragiles.as_ref().ok_or_else(|| model::bad())?;
                    if proof.frame.context.scene_version!=world.scene_version()
                        ||proof.frame.context.scene_sha256!=source.historical_scene_hash(world.scene_version())?{return Err(model::bad());}
                }
                vehicle_contacts.extend_from_slice(&batch.contacts);
            }
        }
        let vehicle_events = candidate.apply_vehicle_contacts(&vehicle_contacts)?;
        if self.workers.iter().flatten().any(|worker|!worker.prepared_ids().is_empty()) {
            let removed=candidate.fragiles.as_ref().ok_or_else(|| model::bad())?.removed_ids();
            if self.workers.iter().flatten().any(|worker|worker.prepared_ids().iter().any(|id|removed.binary_search(id).is_err())) {
                return Err(io::Error::new(io::ErrorKind::InvalidData,"domain rejected a prepared physical fracture; fail closed"));
            }
        }
        for event in &vehicle_events {
            let closing_speed=event.velocity.iter().zip(event.normal).map(|(v,n)|v*n).sum::<f32>();
            let energy_j=0.5*event.mass_kg*closing_speed*closing_speed;
            let closing_f64=event.velocity.iter().zip(event.normal).map(|(v,n)|f64::from(*v)*f64::from(n)).sum::<f64>();
            let normal_energy_j=0.5*f64::from(event.mass_kg)*closing_f64*closing_f64;
            let ram_response=candidate.fragiles.as_ref().and_then(|s|s.catalog.objects.iter().find(|o|o.object_id==event.object_id)
                .and_then(|o|s.catalog.ram_response(o))).unwrap_or("normal_linear");
            let admission_energy_j=if let Some(p)=&event.proof {
                let r=p.receipt()?;
                if r.mode==ram_proof::Mode::Angular {let w=p.frame.proof.witness(r.substep)?;
                    super::ram_response::inspect(w.pre.scalar(p.frame.proof.binding,w.pre.motion),r.geometry.scalar()).map_err(|_|model::bad())?.normal_energy
                }else if r.mode==ram_proof::Mode::Total{0.5*f64::from(event.mass_kg)*event.velocity.iter().map(|v|f64::from(*v)*f64::from(*v)).sum::<f64>()}
                else{normal_energy_j}
            }else if ram_response=="total_linear" {0.5*f64::from(event.mass_kg)*event.velocity.iter().map(|v|f64::from(*v)*f64::from(*v)).sum::<f64>()}else{normal_energy_j};
            println!("SHARED_VEHICLE_CONTACT battle={} slot={} object_id={} instance_id={} kind={} substep={} closing_speed={} scene_before={} scene_after={} fallen_tree={:?}",
                candidate.id,event.shooter,event.object_id,event.instance_id,event.kind,event.substep,
                closing_speed,event.scene_before,event.scene_after,event.fallen_tree);
            println!("SHARED_VEHICLE_CONTACT_ENERGY battle={} object_id={} mass_kg={} closing_speed={} energy_j={} normal_energy_j={} admission_energy_j={} ram_response={} policy_min_energy_j={}",
                candidate.id,event.object_id,event.mass_kg,closing_speed,energy_j,normal_energy_j,admission_energy_j,ram_response,super::fragiles::RAMMING_MIN_ENERGY_J);
        }
        if candidate.scene_version() != world.scene_version() {
            if self.catalog.is_none()&&(self.removal.is_none() || world.scene_version() != 0 || candidate.scene_version() != 1) {
                return Err(model::bad());
            }
            // The staged candidate owns these outcomes now. ACK-only polls
            // must never apply the same advance's contacts a second time.
            self.contact_batches = std::array::from_fn(|_| None);
            if published { self.pose_pending = [false; model::CAPACITY]; }
            self.staged = Some(candidate);
            return self.finish_removal(world, now);
        }
        *world = candidate;
        if published { self.pose_pending = [false; model::CAPACITY]; }
        self.contact_batches = std::array::from_fn(|_| None);
        for slot in 0..model::CAPACITY {
            if world.actors.get(slot).and_then(|a| a.session).is_none() { continue; }
            let worker = self.workers[slot].as_mut().ok_or_else(|| model::bad())?;
            if !self.synchronizing[slot] && !self.pose_pending[slot] && worker.ready() && !worker.pending()
                && deadlines[slot].is_some() {
                let actor = world.actors.get(slot).ok_or_else(|| model::bad())?;
                let input = crate::map_drive_worker091::Input { throttle: actor.input.throttle,
                    steer: actor.input.steer, brake: actor.input.throttle == 0 && actor.input.steer == 0, speed_percent: actor.input.speed_percent };
                let seq = worker.advance(input, now)?;
                self.dispatched[slot] = deadlines[slot];
                println!("SHARED_INTEGRATED_WORKER_INPUT battle={} slot={} seq={} throttle={} steer={} brake={} speed_percent={}",
                    world.id, slot, seq, input.throttle, input.steer, input.brake, input.speed_percent);
            }
        }
        Ok(())
    }
}
impl Table {
    fn admissible(&mut self, attempt: &LoginAttempt, now: Instant) -> io::Result<()> {
        self.retirement.check_login(attempt, now).map_err(|_| model::bad())?;
        if self.sessions.iter().any(|s| s.same_login_attempt(attempt)) { return Ok(()); }
        if self.full()
            || self.retirement.retained_count() + self.sessions.len() >= self.retirement.limit()
            || self.sessions.iter().any(|s| s.key == attempt.key || s.login_peer == attempt.login_peer
                || s.base_peer == Some(attempt.login_peer)) { return Err(model::bad()); }
        Ok(())
    }
    fn full(&self)->bool {self.sessions.len()>=self.capacity}
    /// GW-01: a Join may reserve an arena place only while fewer sessions
    /// (live and dispatcher-retained) hold a reservation for this battle than
    /// it has places. Without `arena_split` the table itself is the arena bound.
    fn arena_admission_open(&self,retained:&[Session],world:&World)->bool {
        if !self.arena_split {return true;}
        let reserved=self.sessions.iter().chain(retained).filter(|s|s.shared.as_ref().and_then(|c|c.profile13.as_ref())
            .is_some_and(|p|p.reservation_battle()==Some(world.id))).count();
        reserved<world.human_places()
    }
    /// GW-01 start barrier: every arena place belongs to a live entry-ready session.
    /// BOT-01: with bots only the native places; bots fill the rest at start.
    fn arena_ready(&self,world:&World,now:Instant)->bool {
        world.actors.len()==world.human_places()&&world.actors.iter().all(|a|a.session
            .is_some_and(|id|self.sessions.iter().any(|s|s.id==id&&entry_ready(s,now))))
    }
    fn route(&self, peer: SocketAddr, packet: &[u8]) -> io::Result<usize> {
        self.route_inner(peer,packet,None)
    }
    fn route_with_network(&self,peer:SocketAddr,packet:&[u8],network:&crate::identity091::game_network::Network)->io::Result<usize>{
        if !network.allows_peer(peer){return Err(model::bad());}
        self.route_inner(peer,packet,Some(network))
    }
    fn route_inner(&self,peer:SocketAddr,packet:&[u8],network:Option<&crate::identity091::game_network::Network>)->io::Result<usize>{
        if packet.len() == 21 {
            let matches: Vec<_> = self.sessions.iter().enumerate()
                .filter(|(_, s)| base::base_request(packet, s.handoff).is_ok()).map(|(i, _)| i).collect();
            if matches.len() != 1 { return Err(model::bad()); }
            let index = matches[0];
            if network.is_some_and(|n|!n.allows_first_base(self.sessions[index].login_peer,peer)){return Err(model::bad());}
            if self.sessions[index].base_peer.is_some_and(|bound| bound != peer)
                || self.sessions.iter().enumerate().any(|(i, s)| i != index &&
                    (s.base_peer == Some(peer) || s.login_peer == peer)) { return Err(model::bad()); }
            Ok(index)
        } else {
            self.sessions.iter().position(|s| s.base_peer == Some(peer)).ok_or_else(|| model::bad())
        }
    }
    fn retire(&mut self, id: u32, world: &mut World, now: Instant, reason: &str) -> io::Result<()> {
        let index = self.sessions.iter().position(|s| s.id == id).ok_or_else(|| model::bad())?;
        let s = &self.sessions[index];
        self.retirement.retire(s.login_attempt.ok_or_else(|| model::bad())?, s.base_peer, now).map_err(|_| model::bad())?;
        // An explicit leave intent already parked this actor. Disconnect and
        // timeout take the same stop-controller path without touching a peer.
        if world.actors.iter().any(|a| a.session == Some(id)) { world.detach(id)?; }
        self.sessions.remove(index);
        println!("SHARED_SESSION_CLOSED battle={} session={id} reason={reason} survivors={} tick={}", world.id, self.sessions.len(), world.tick);
        Ok(())
    }
}

const MAX_GARAGE_JOBS:usize=4;
/// A garage writer keeps its owner after the Session retires.
struct GarageJob {job:ammo_session::Job,account_id:String,account:Option<AccountTag>}

/// Per-account view of every account writer a new login must not overlap.
fn login_writers(serial:bool,dispatch:&profile13_dispatch::Dispatcher,results:&super::results_session::Manager,
    room_host:&Option<p10b_host::Host>,garage:&[GarageJob],table:&Table)->Writers {
    let mut writers=Writers::default();
    let resolve=|owner:&str|table.sessions.iter().chain(dispatch.retired_sessions())
        .find(|s|s.identity.as_ref().is_some_and(|p|p.account_id==owner)).and_then(|s|s.login_account);
    let mut add=|account:Option<AccountTag>|match account.filter(|_|!serial) {
        Some(tag)=>writers.accounts.push(tag), None=>writers.global=true};
    if room_host.as_ref().is_some_and(p10b_host::Host::busy) {add(None);}
    if dispatch.busy() {
        match dispatch.writer_owners() {Some(owners)=>for owner in owners {add(resolve(owner));}, None=>add(None)}
    }
    if results.busy() {add(results.owner_account().and_then(resolve));}
    for job in garage {add(job.account);}
    writers
}

/// Immutable validated resources survive a failed battle; worker handles do not.
#[derive(Clone)]
struct BattleTemplate {
    world: World,
    pool: Option<Arc<crate::map_drive_worker091::Pool>>,
    removal: Option<crate::map_drive_worker091::RemovalSpec>,
    catalog: Option<crate::map_drive_worker091::CatalogSpec>,
    shared:Option<Arc<super::profile13_templates::SharedResources>>,
}
impl BattleTemplate {
    fn from_shared(rows:&[super::profile13_templates::Resources],count:usize,id:u64,now:Instant)->io::Result<Self>{
        Self::from_shared_mode(rows,count,id,now,None)
    }
    fn from_shared_mode(rows:&[super::profile13_templates::Resources],count:usize,id:u64,now:Instant,
        qualification:Option<VehicleKind>)->io::Result<Self>{
        Self::from_shared_policy(rows,count,id,now,qualification,false)
    }
    fn from_shared_policy(rows:&[super::profile13_templates::Resources],count:usize,id:u64,now:Instant,
        qualification:Option<VehicleKind>,breech_v2:bool)->io::Result<Self>{
        let extended=qualification.is_some_and(VehicleKind::is_extended);
        if breech_v2&&!extended{return Err(model::bad());}
        // BATTLE-ANY version5: generated kinds follow the five curated rows (owned mixed battles only).
        let generated=rows.len()>5&&!extended&&qualification.is_none()&&p04m_template_rows(rows);
        if !(matches!(rows.len(),2|5|7)||generated)||(rows.len()==7&&!generated)!=extended
            ||rows.iter().enumerate().any(|(index,row)|row.kind.index()!=index&&!(generated&&index>=5)) {return Err(model::bad());}
        if qualification.is_some_and(|kind|rows.len()!=(if extended{7}else{5})||!rows.iter().any(|row|row.kind==kind)){return Err(model::bad());}
        let shared=rows[0].shared.clone().ok_or_else(||model::bad())?;
        let map=rows[0].map;if rows.iter().any(|row|row.map!=map){return Err(model::bad());}
        let mut world=World::new_for_vehicle(id,now,map,qualification.unwrap_or(VehicleKind::Ms1))?;
        world.set_expected_actors(count)?;
        for row in rows{world.bind_geometry(row.geometry.clone())?;}
        world.enable_ap_test_lab()?;world.bind_terrain(rows[0].terrain.clone())?;
        world.bind_fragiles(rows[0].catalog.0.clone())?;
        if extended{world.enable_extended_lab()?;}
        if breech_v2{world.enable_extended_breech_lab()?;}
        if qualification.is_none(){world.enable_lifecycle(super::lifecycle::Rules::for_map(map)?)?;}
        Ok(Self{world,pool:Some(rows[0].pool.clone()),removal:None,catalog:Some(rows[0].catalog.1.clone()),shared:Some(shared)})
    }
    fn runtime(&self,map:MapId)->io::Result<Option<IntegratedRuntime>>{self.pool.as_ref().map(|pool|{
        let mut r=IntegratedRuntime::new_for_map(pool.clone(),map);r.removal=self.removal.clone();r.catalog=self.catalog.clone();
        if let Some(shared)=&self.shared{r.batch=Some(BatchRuntime::new(shared.clone(),self.catalog.clone().ok_or_else(||model::bad())?));}Ok(r)
    }).transpose()}
    fn from_resources(r:&super::profile13_templates::Resources,id:u64,now:Instant)->io::Result<Self> {
        let mut world=World::new_for_vehicle(id,now,r.map,r.kind)?;
        world.bind_geometry(r.geometry.clone())?;world.enable_ap_test_lab()?;
        world.bind_terrain(r.terrain.clone())?;world.bind_fragiles(r.catalog.0.clone())?;
        world.enable_lifecycle(super::lifecycle::Rules::for_map(r.map)?)?;
        Ok(Self{world,pool:Some(r.pool.clone()),removal:None,catalog:Some(r.catalog.1.clone()),shared:None})
    }
    fn select(&self,world:&mut World,runtime:&mut Option<IntegratedRuntime>,now:Instant)->io::Result<()> {
        if world.started.is_some() || world.actors.iter().any(|a|a.session.is_some()) {return Err(model::bad());}
        let id=world.id;
        *world=if self.world.id==id {self.world.clone()} else {self.world.fresh_battle(id,now)?};*runtime=None;
        *runtime=self.runtime(world.map)?;
        println!("P08B_WORLD_SELECTED battle={id} kind={} homogeneous={} actors={}",world.vehicle_kind().label(),!world.mixed_profiles(),world.expected_actors());
        Ok(())
    }
    fn new(world: &World, runtime: &Option<IntegratedRuntime>) -> Self {
        Self { world:world.clone(), pool:runtime.as_ref().map(|r|r.pool.clone()),
            removal:runtime.as_ref().and_then(|r|r.removal.clone()),
            catalog:runtime.as_ref().and_then(|r|r.catalog.clone()),shared:None }
    }
    fn replace(&self, world: &mut World, runtime: &mut Option<IntegratedRuntime>, now: Instant) -> io::Result<()> {
        let old = world.id;
        let id = old.checked_add(1).ok_or_else(||model::bad())?;
        let fresh = self.world.fresh_battle(id,now)?;
        // Drop the complete old runtime, including staged poses and owned children.
        *runtime = None;
        *world = fresh;
        *runtime = self.runtime(world.map)?;
        println!("SHARED_BATTLE_RESET previous={old} battle={id} workers_revoked=true actors=0 trace_events=0 scene_version=0 service_alive=true");
        Ok(())
    }
}

/// The actual service and failure-injection tests use the same battle boundary.
fn advance_battle(world:&mut World, runtime:&mut Option<IntegratedRuntime>, now:Instant, start:bool)->io::Result<()> {
    if start {
        world.start(now)?;
        if world.lifecycle.is_some() {
            world.lifecycle_created_unix=Some(std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
                .map_err(|_|model::bad())?.as_secs().try_into().map_err(|_|model::bad())?);
        }
        println!("SHARED_WORLD_STARTED battle={} sessions={} actors={} space=1 tick=1000",world.id,world.actors.len(),world.actors.len());
    }
    if world.started.is_some() {
        // BOT-01: bots decide before the step, as native packets arrive before
        // it; a prepared scene transaction owns the World until its ACK.
        if world.bot_plan().is_some() && runtime.as_ref().is_none_or(|r|!r.blocked()) {
            let _span=super::step_profile::span(super::step_profile::Part::Bots);
            if runtime.as_ref().is_none_or(IntegratedRuntime::ready_for_native) {world.ready_bots()?;}
            world.drive_bots(now)?;
        }
        if world.lifecycle.as_ref().is_some_and(|state|state.outcome().is_some()) {
            world.advance(now)?;
            // TURRET-01: a detonation that ended the battle still gets its body.
            if let Some(batch)=runtime.as_mut().and_then(|r|r.batch.as_mut()) {batch.turrets_after_outcome(world,now)?;}
        }
        else if let Some(r)=runtime {
            if !r.started {r.start(world,now)?;}
            let _span=super::step_profile::span(super::step_profile::Part::Scene);
            r.step(world,now)?;
        } else {world.advance(now)?;}
        if runtime.as_ref().is_none_or(|r|!r.blocked()) { let _span=super::step_profile::span(super::step_profile::Part::Spotting); world.refresh_original_spotting(now)?; }
        // A candidate scene owns an atomic World clone. Do not advance the
        // lifecycle outside it and then overwrite a frozen outcome on ACK.
        let lifecycle_span=super::step_profile::span(super::step_profile::Part::Lifecycle);
        if runtime.as_ref().is_none_or(|r|!r.blocked()) && world.advance_lifecycle(now)? {
            println!("P08C_LIFECYCLE battle={} view={:?} policy={}",world.id,
                world.lifecycle.as_ref().map(|l|l.view()),super::lifecycle::POLICY);
        }
        drop(lifecycle_span);
        // A separate bounded visual clock survives the authoritative outcome.
        // Do not mutate a World while a prepared scene clone owns its commit.
        // After the outcome no runtime stages or commits a World, so a worker
        // fracture left prepared then cannot freeze the turret timeline.
        let frozen=world.lifecycle.as_ref().is_some_and(|state|state.outcome().is_some());
        if (frozen||runtime.as_ref().is_none_or(|r|!r.blocked())) && world.ammo_detonation_enabled(){
            let _span=super::step_profile::span(super::step_profile::Part::Turrets);
            world.advance_turret_flights(now)?;
        }
    }
    Ok(())
}

fn stage_lifecycle_results(table:&mut Table,world:&World)->io::Result<()> {
    stage_lifecycle_results_from(table,world,None)
}
fn stage_lifecycle_results_from(table:&mut Table,world:&World,sealed:Option<Arc<super::lifecycle_wire::Results>>)->io::Result<()> {
    if !world.lifecycle.as_ref().is_some_and(|state|state.outcome().is_some()) {return Ok(());}
    let needs=table.sessions.iter().any(|s|s.shared.as_ref().is_some_and(|c|c.natural_result.is_none()
        && c.profile13.as_ref().is_some_and(|p|!p.has_pending_return() && p.reservation_battle()==Some(world.id))));
    if !needs {return Ok(());}
    let result=if let Some(result)=sealed{result}else{Arc::new(super::lifecycle_result::build(world)?)};
    for s in &mut table.sessions {
        let Some(c)=&mut s.shared else{continue;};
        if c.natural_result.is_none() && c.profile13.as_ref().is_some_and(|p|!p.has_pending_return()
            && p.reservation_battle()==Some(world.id)) {
            c.natural_result=Some(result.clone());
            println!("P08C_RESULT_FROZEN battle={} session={} winner={} reason={} shots={} damage={} inventory_not_yet_released=true",
                world.id,s.id,result.winner_team,result.finish_reason,
                result.participants.iter().find(|p|s.identity.as_ref().is_some_and(|o|o.database_id==p.account_dbid)).map_or(0,|p|p.shots),
                result.participants.iter().map(|p|p.damage_dealt).sum::<u32>());
        }
    }
    Ok(())
}

/// Natural results are delivered only after their atomic writer transaction.
/// A native confirmation must precede Account reset; timeout disconnects rather
/// than pretending the original result handler successfully consumed the stream.
// Revoking World membership does not finish the asynchronous writer or the
// native Avatar. Keep its current World until the real Account handoff, even
// when no ammo rack detonated. Queue cancellation has no Avatar and may reset.
fn current_avatar_pending(table:&Table,world:&World)->bool{
    table.sessions.iter().any(|s|s.arena_base&&s.shared.as_ref().is_some_and(|c|
        matches!(c.phase,Phase::Enable|Phase::Entities|Phase::Driving|Phase::Leaving)
            &&c.view.as_ref().is_some_and(|view|view.id==world.id)))
}
fn parked_battle_reset_ready(table:&Table,world:&World)->bool{
    // BOT-01: bots never park; the battle resets once every native player has.
    !world.actors.is_empty()&&world.humans_parked()
        &&!current_avatar_pending(table,world)
}
fn deliver_lifecycle_result(s:&mut Session,world:&World,now:Instant)->io::Result<bool> {
    let Some(c)=s.shared.as_ref() else{return Ok(false);};
    if !c.result_committed || c.natural_result.is_none() || !s.arena_base {return Ok(false);}
    if !c.result_stream_queued&&!s.turret_presentation_ready(world,now)?{return Ok(true);}
    let mut next=s.clone();
    if !c.result_stream_queued {
        let result=c.natural_result.clone().ok_or_else(||model::bad())?;
        let own=next.identity.as_ref().ok_or_else(||model::bad())?.database_id;
        let mixed=c.view.as_ref().is_some_and(|world|world.mixed_ammo());
        let bodies=if mixed{super::lifecycle_wire::avatar_result_stream_p06t(&result,own)?}
            else{super::lifecycle_wire::avatar_result_stream(&result,own)?};
        if next.outbox.len()+bodies.len()>128 {return Ok(true);}
        next.outbox.extend(bodies);
        if mixed{next.battle_results.cache_avatar_p06t(result,own)?;}else{next.battle_results.cache_avatar(result,own)?;}
        let c=next.shared.as_mut().ok_or_else(||model::bad())?;
        c.result_stream_queued=true;c.result_delivery_at=Some(now);
        next.drain_outbox()?;
        println!("P08C_RESULTS_AVATAR_QUEUED session={} durable=true waiting_native_confirmation=true",s.id);
    }
    if next.battle_results.avatar_confirmed() {
        let mut events=Vec::new();next.shared_return("natural_result_confirmed",now,&mut events)?;
        for event in events {println!("{event}");}
    } else if next.shared.as_ref().and_then(|c|c.result_delivery_at).is_some_and(|at|now.duration_since(at)>=Duration::from_secs(30)) {
        return Err(io::Error::new(io::ErrorKind::TimedOut,"native result stream was not confirmed; durable result retained for next login"));
    } else {next.drain_outbox()?;}
    *s=next;Ok(true)
}

// A contained fault has explicitly revoked this exact old battle. Only its
// immutable terminal receipt/result may drain; never publish the replacement
// World to an old Avatar or replay commands into either World.
fn contained_return_world(s:&Session,world:&World)->io::Result<Option<Arc<World>>>{
    let Some(retained)=s.shared.as_ref().and_then(|c|c.contained_world.clone())else{return Ok(None);};
    let c=s.shared.as_ref().ok_or_else(||model::bad())?;
    let owner=s.identity.as_ref().ok_or_else(||model::bad())?;
    let actor=retained.actors.get(c.slot).ok_or_else(||model::bad())?;
    let p=c.profile13.as_ref().ok_or_else(||model::bad())?;
    let pending=p.has_pending_return()&&p.reservation_battle()==Some(retained.id);
    let committed=c.result_committed&&c.natural_result.as_ref().is_some_and(|r|r.arena_id==retained.id);
    if !s.arena_base||c.phase!=Phase::Leaving||retained.id==world.id
        ||c.view.as_ref().is_none_or(|view|view.id!=retained.id||view.mixed_ammo()!=retained.mixed_ammo())
        ||actor.identity.account!=owner.account_id||actor.identity.database!=owner.database_id
        ||actor.session.is_some()||!(pending||committed)
        ||c.natural_result.as_ref().is_some_and(|r|r.arena_id!=retained.id){return Err(model::bad());}
    Ok(Some(retained))
}
// The actual ordinary-mode ingress transaction uses the same terminal
// source proof as polling. A contained Avatar keeps its checked old view;
// refreshing it from the replacement World would reject ACK/confirmation
// before receive() and cannot grant authority in either battle.
fn receive_battle_session(s:&mut Session,frame:&Frame,world:&World,now:Instant)->io::Result<bool>{
    let mut staged=s.clone();
    if contained_return_world(&staged,world)?.is_some(){
        if !staged.active{return Err(model::bad());}
    }else{staged.shared_refresh_world(world)?;}
    // Leaving validates on the existing throwaway Driving clone and retains
    // only terminal transport/result state, never its simulated commands.
    let close=staged.receive(frame,now)?;*s=staged;Ok(close)
}

fn poll_contained_return(s:&mut Session,world:&World,now:Instant)->io::Result<bool>{
    let Some(retained)=contained_return_world(s,world)?else{return Ok(false);};
    if !s.active{return Err(model::bad());}
    // The ordinary Finished delivery either starts warm Account return itself,
    // or marks this immutable natural result committed. Original confirmation
    // and bounded timeout still apply; containment never invents either one.
    deliver_lifecycle_result(s,&retained,now)?;Ok(true)
}
fn contained_return_failure_reason(s:&Session)->Option<&'static str>{
    s.shared.as_ref().is_some_and(|c|c.contained_world.is_some()).then_some("contained_terminal_return_failed")
}
// Closing an old contained Avatar must not pass a new battle to terminal(),
// including Hold5's outcome-sensitive retirement. Clone once on this boundary;
// the current authoritative World is borrowed read-only and cannot be detached.
fn retire_contained_session(dispatcher:&mut profile13_dispatch::Dispatcher,table:&mut Table,
    world:&World,id:u32,now:Instant,reason:&str)->io::Result<bool>{
    let Some(s)=table.sessions.iter().find(|s|s.id==id)else{return Ok(false);};
    let Some(retained)=contained_return_world(s,world)?else{return Ok(false);};
    let mut revoked=retained.as_ref().clone();
    dispatcher.retire(table,&mut revoked,id,now,reason)?;Ok(true)
}

fn poll_battle_session(s:&mut Session,world:&mut World,now:Instant,allow_native_start:bool,blocked:bool)->io::Result<()> {
    if poll_contained_return(s,world,now)?{return Ok(());}
    let mut fresh=s.clone();fresh.shared_refresh_world(world)?;
    fresh.flush_shared_interest(&mut Vec::new())?;
    if world.ammo_detonation_enabled()&&fresh.shared.as_ref().is_some_and(|c|c.phase==Phase::Leaving){
        let c=fresh.shared.as_mut().ok_or_else(||model::bad())?;
        p06t_publication::publish(c,&mut fresh.outbox,world,now)?;
        fresh.drain_outbox()?;
    }
    fresh.flush_shared_private()?;
    let mut turret_events=Vec::new();fresh.flush_shared_turrets(world,&mut turret_events)?;*s=fresh;
    for event in turret_events{println!("{event}");}
    if deliver_lifecycle_result(s,world,now)? {return Ok(());}
    if s.shared.as_ref().and_then(|c|c.profile13.as_ref()).is_some_and(|p|p.has_pending_return()) {return Ok(());}
    let natural_due=if let Some(state)=world.lifecycle.as_ref().filter(|state|state.outcome().is_some()) {
        state.ready_to_return(world.lifecycle_ms(now)?)
    } else {false};
    if natural_due
        && s.shared.as_ref().is_some_and(|c|c.natural_result.is_some()) {
        profile13_dispatch::Dispatcher::terminal(s,world,crate::battle091::profile13::FinishReason::BattleFinished)?;
        if !blocked && world.actors.iter().any(|a|a.session==Some(s.id)) {world.detach(s.id)?;}
        return Ok(());
    }
    if s.shared.as_ref().is_some_and(|c|c.phase==Phase::Leaving && c.profile13.is_some()) {
        profile13_dispatch::Dispatcher::terminal(s,world,crate::battle091::profile13::FinishReason::ManualLeave)?;
        if !blocked && world.actors.iter().any(|a|a.session==Some(s.id)) {world.detach(s.id)?;}
        return Ok(());
    }
    // A prepared scene transaction must finish before membership changes.
    // Keep transport heartbeats outside this gate, including a pending Leave.
    if blocked {return Ok(());}
    // Native Leave is valid before the initial correction ACK as well.
    // Its queued command must not enter the startup motion validator.
    if !s.shared.as_ref().is_some_and(|c|c.phase==Phase::Leaving) {
        poll_with_native_start(s,world,now,allow_native_start)?;
    }
    if s.shared.as_ref().is_some_and(|c|c.phase==Phase::Leaving) {
        // Area/correction readiness can defer apply(Leave). Revoke authority
        // regardless of those publication gates before recreating Account.
        let mut next_world=world.clone();
        if next_world.actors.iter().any(|a|a.session==Some(s.id)) {next_world.detach(s.id)?;}
        let mut events=Vec::new();s.shared_return("native_leave",now,&mut events)?;
        *world=next_world;
        for event in events {println!("{event}");}
    }
    Ok(())
}

fn contain_battle_failure(table:&mut Table, world:&mut World, runtime:&mut Option<IntegratedRuntime>,
    template:&BattleTemplate, now:Instant, stage:&str, error:&io::Error)->io::Result<serde_json::Value> {
    let contained=contain_battle_sessions(table,world,runtime,template,now,stage,error)?;
    // Without the dispatcher (old helper, training rooms) an unreturned session
    // takes the old transport retirement; the service loop uses containment::contain_arena.
    for id in contained.unreturned {table.retire(id,world,now,"failed_battle_return")?;}
    contained.reset?;
    Ok(contained.snapshot)
}

/// STAB-02: what a contained failure left for its caller. One session that
/// cannot take the contained return never aborts the others' return.
struct Contained {snapshot:serde_json::Value,unreturned:Vec<u32>,reset:io::Result<()>}
fn unreturned_session(unreturned:&mut Vec<u32>,id:u32,battle:u64,step:&str,error:&io::Error){
    if !unreturned.contains(&id){unreturned.push(id);}
    println!("SHARED_CONTAINMENT_SESSION_UNRETURNED session={id} battle={battle} step={step} error={error} transport_retired=true");
}
/// The failed World may be unable to produce this actor's terminal result
/// (stand -11: its device state refused the profile). The reservation is then
/// cancelled without a battle result; no consumption or damage is invented.
fn contain_profile13_session(s:&mut Session,world:&mut World)->io::Result<()> {
    use crate::battle091::profile13::FinishReason;
    if let Err(error)=profile13_dispatch::Dispatcher::terminal(s,world,FinishReason::BattleFailure) {
        if !world.actors.iter().any(|a|a.session==Some(s.id)) {return Err(error);}
        println!("SHARED_CONTAINMENT_TERMINAL_FALLBACK session={} battle={} error={error} actor_result_discarded=true reservation_cancelled=true",s.id,world.id);
        world.detach(s.id)?;
        profile13_dispatch::Dispatcher::terminal(s,world,FinishReason::BattleFailure)?;
    }
    if world.actors.iter().any(|a|a.session==Some(s.id)) {world.detach(s.id)?;}
    if let Some(c)=&mut s.shared {c.join_requested=false;c.commands.clear();c.hangar_since=None;}
    Ok(())
}
/// Checks the old Avatar's retained return before it is bound to `retained`.
fn retain_contained_return(s:&mut Session,retained:&Arc<World>)->io::Result<()> {
    let c=s.shared.as_ref().ok_or_else(||model::bad())?;
    let owner=s.identity.as_ref().ok_or_else(||model::bad())?;
    let actor=retained.actors.get(c.slot).ok_or_else(||model::bad())?;
    let p=c.profile13.as_ref().ok_or_else(||model::bad())?;
    let pending=p.has_pending_return()&&p.reservation_battle()==Some(retained.id);
    let committed=c.result_committed&&c.natural_result.as_ref().is_some_and(|r|r.arena_id==retained.id);
    if c.phase!=Phase::Leaving||c.view.as_ref().is_none_or(|view|view.id!=retained.id)
        ||actor.identity.account!=owner.account_id||actor.identity.database!=owner.database_id
        ||actor.session.is_some()||!(pending||committed){return Err(model::bad());}
    s.shared.as_mut().ok_or_else(||model::bad())?.contained_world=Some(retained.clone());
    Ok(())
}

fn contain_battle_sessions(table:&mut Table, world:&mut World, runtime:&mut Option<IntegratedRuntime>,
    template:&BattleTemplate, now:Instant, stage:&str, error:&io::Error)->io::Result<Contained> {
    let snapshot=serde_json::json!({"stage":stage,"reason":error.to_string().chars().take(2048).collect::<String>(),
        "world":world.failure_snapshot(),
        "sessions":table.sessions.iter().map(|s|serde_json::json!({"session":s.id,
            "phase":s.shared.as_ref().map(|c|format!("{:?}",c.phase)),
            "queued_commands":s.shared.as_ref().map(|c|format!("{:?}",c.commands))})).collect::<Vec<_>>(),
        "runtime":runtime.as_ref().map(|r|serde_json::json!({"started":r.started,"poses":r.poses,
            "generations":r.generations,"worker_sessions":r.worker_sessions,
            "pose_pending":r.pose_pending,"staged_tick":r.staged.as_ref().map(|w|w.tick),
            "batch":r.batch.as_ref().map(BatchRuntime::failure_snapshot)}))});
    // Stdout is the stand's retained journal. Never continue the failed world.
    println!("SHARED_BATTLE_FAILED {snapshot}");
    let mut retire=Vec::new();let mut unreturned=Vec::new();
    let table_split=table.arena_split;
    // ARENA-01: with several arenas only this battle's sessions are touched:
    // an actor here, its native view of this battle, or its reservation for it.
    let outsiders:Vec<u32>=if table.multi_arena {table.sessions.iter().filter(|s|!arena_member(s,world)).map(|s|s.id).collect()} else {Vec::new()};
    for s in &mut table.sessions {
        if outsiders.contains(&s.id) {continue;}
        if s.shared.as_ref().is_some_and(|c|c.contained_world.is_some()) {
            if let Err(e)=contained_return_world(s,world) {unreturned_session(&mut unreturned,s.id,world.id,"contained_return",&e);}
            continue;
        }
        if s.shared.as_ref().is_some_and(|c|c.profile13.is_some()) {
            // GW-01: a hangar session with no reservation, writer or arena place
            // is not part of the failed battle; keep its queue and commands.
            if table_split && !world.actors.iter().any(|a|a.session==Some(s.id)) && s.shared.as_ref()
                .and_then(|c|c.profile13.as_ref()).is_some_and(|p|!p.has_reservation()&&!p.in_flight&&!p.has_pending_return()) {continue;}
            if let Err(e)=contain_profile13_session(s,world) {unreturned_session(&mut unreturned,s.id,world.id,"terminal",&e);}
            continue;
        }
        if world.actors.iter().any(|a|a.session==Some(s.id)) {world.detach(s.id)?;}
        if s.arena_base {
            let mut events=Vec::new();
            match s.shared_return("battle_failure",now,&mut events) {
                Ok(())=>for event in events {println!("{event}");},
                Err(e)=>{println!("SHARED_RETURN_FAILED session={} reason={e} transport_retired=true",s.id);retire.push(s.id);}
            }
        } else if let Some(c)=&mut s.shared {
            let cancel_queue=c.phase==Phase::Account && c.queue_announced;
            c.join_requested=false; c.commands.clear(); c.hangar_since=None; c.queue_announced=false;
            if cancel_queue {
                if s.outbox.len()>=128 {retire.push(s.id);}
                else {
                    s.outbox.push_back(crate::map_drive_world091::queue_callback(false));
                    if let Err(e)=s.drain_outbox() {
                        println!("SHARED_RETURN_FAILED session={} reason={e} transport_retired=true",s.id);retire.push(s.id);
                    }
                }
            }
        }
    }
    for id in retire {
        if let Err(e)=table.retire(id,world,now,"failed_battle_return") {unreturned_session(&mut unreturned,id,world.id,"transport_retire",&e);}
    }
    // Snapshot once after every membership was revoked. A forced failure reset
    // cannot wait for asynchronous Finish, unlike the ordinary reset barrier.
    let retained=Arc::new(world.clone());
    for s in &mut table.sessions {
        if outsiders.contains(&s.id) {continue;}
        if s.shared.as_ref().is_some_and(|c|c.contained_world.is_some()) {continue;}
        if !s.arena_base||s.shared.as_ref().is_none_or(|c|c.profile13.is_none())||unreturned.contains(&s.id){continue;}
        if let Err(e)=retain_contained_return(s,&retained) {unreturned_session(&mut unreturned,s.id,world.id,"contained_view",&e);}
    }
    let reset=template.replace(world,runtime,now);
    Ok(Contained{snapshot,unreturned,reset})
}

fn arena_member(s:&Session,world:&World)->bool {
    world.actors.iter().any(|a|a.session==Some(s.id))||s.shared.as_ref().is_some_and(|c|
        c.view.as_ref().is_some_and(|v|v.id==world.id)
        ||c.profile13.as_ref().is_some_and(|p|p.reservation_battle()==Some(world.id)))
}

fn contain_results_failure(manager:&super::results_session::Manager,dispatcher:&mut profile13_dispatch::Dispatcher,
    table:&mut Table,world:&mut World,now:Instant,error:&io::Error)->io::Result<()> {
    let target=manager.failure_session(&table.sessions);
    println!("P08C_RESULTS_SESSION_FAILED session={target:?} error={error} service_alive=true durable_result_retained=true");
    if let Some(id)=target.filter(|id|table.sessions.iter().any(|s|s.id==*id)) {
        if !retire_contained_session(dispatcher,table,world,id,now,"native_results_delivery")?{
            dispatcher.retire(table,world,id,now,"native_results_delivery")?;
        }
    }
    Ok(())
}

fn attach_waiting_sessions(table:&mut Table,world:&mut World,now:Instant)->io::Result<()> {
    if world.started.is_some() {return Ok(());}
    let split=table.arena_split;
    for s in &mut table.sessions {
        if !entry_ready(s,now) || world.actors.iter().any(|a|a.session==Some(s.id)) {continue;}
        if split&&world.actors.len()>=world.human_places() {break;}
        let identity=s.identity.as_ref().ok_or_else(||model::bad())?;
        let who=model::Identity{account:identity.account_id.clone(),database:identity.database_id,name:identity.name.clone()};
        let owned=s.shared.as_ref().and_then(|c|c.profile13.as_ref());
        // A profile13 client can reach the shared Account phase before its
        // native Join has completed the durable reservation writer. Keep that
        // session waiting; attaching it here would turn a normal two-owner
        // barrier into a process-wide world-step failure at the receipt read.
        if let Some(p)=owned {
            let missing=if world.owner_hold_enabled(){p.reservation_hold.is_none()}
                else if world.ammo_detonation_enabled(){p.reservation_loss.is_none()}
                else if world.mixed_ammo(){p.reservation_v2.is_none()}
                else {p.reservation.is_none()};
            if missing {continue;}
        }
        let slot=if let Some(p)=owned {
            if world.mixed_ammo(){
                if world.owner_hold_enabled(){
                    let receipt=p.reservation_hold.as_ref().ok_or_else(||model::bad())?;
                    if receipt.battle!=world.id{continue;}
                    world.attach_owned_hold(who,s.id,&receipt.frozen)?
                }else if world.ammo_detonation_enabled(){
                    let receipt=p.reservation_loss.as_ref().ok_or_else(||model::bad())?;
                    if receipt.battle!=world.id{continue;}
                    world.attach_owned_loss(who,s.id,&receipt.frozen)?
                }else{
                    let receipt=p.reservation_v2.as_ref().ok_or_else(||model::bad())?;
                    if receipt.battle!=world.id{continue;}
                    world.attach_owned_v2(who,s.id,&receipt.frozen)?
                }
            }else{
            let receipt=p.reservation.as_ref().ok_or_else(||model::bad())?;
            if receipt.battle!=world.id || !world.mixed_profiles()&&receipt.frozen.kind!=world.vehicle_kind() {continue;}
            world.attach_owned(who,s.id,&receipt.frozen)?
            }
        } else if world.extended_lab(){
            world.attach_extended_lab(who,s.id,model::extended::LabLoadout::temporary(world.vehicle_kind()))?
        } else {world.attach(who,s.id)?};
        let c=s.shared.as_mut().ok_or_else(||model::bad())?;
        let since=c.hangar_since;
        c.reset_for_battle(slot); c.hangar_since=since; c.view=Some(world.clone());
    }
    Ok(())
}

pub fn serve(key_path: &str, digest_path: &str, config_path: &str, capture_path: &str)
    -> Result<(), Box<dyn std::error::Error>> {
    serve_with_pool(key_path, digest_path, config_path, capture_path, None, None, false, None, None,None,MapId::Karelia,VehicleKind::Ms1,None,None,None)
}

/// P04M pool: the five curated kinds in slot order, then only generated kinds
/// (BATTLE-ANY manifest version5); nothing else reaches the pool writer.
fn p04m_template_rows(resources:&[super::profile13_templates::Resources])->bool{
    resources.len()>=5&&resources[..5].iter().map(|r|r.kind).eq(VehicleKind::ALL)&&resources[5..].iter().all(|r|r.kind.is_generated())
}

pub fn serve_profile13(key_path:&str,digest_path:&str,config_path:&str,manifest_path:&str,capture_path:&str)
    ->Result<(),Box<dyn std::error::Error>> {
    let config=crate::identity091::Config::load(config_path)?;
    config.require_game_network(crate::identity091::game_network::Runtime::SharedOwnedProfile13)?;
    if !config.profile13_battle || !config.research_service {return Err(model::bad().into());}
    let resources=super::profile13_templates::load(&config.local_root,Path::new(manifest_path))?;
    if config.p04m_pool&&!p04m_template_rows(&resources){return Err(model::bad().into());}
    let initial=&resources[0];let map=initial.map;
    serve_with_pool(key_path,digest_path,config_path,capture_path,Some(initial.pool.clone()),Some(initial.geometry.clone()),
        true,Some(initial.terrain.clone()),None,Some(initial.catalog.clone()),map,VehicleKind::Ms1,Some(resources),None,None)
}

/// Explicit profile13 shared-world mode with a portable source-bundle guard.
/// The bundle proves the primary owner's source provenance; profile13's
/// reservation/FrozenLoadout remains authoritative for the actual battle.
pub fn serve_profile13_source_bundle(key_path:&str,digest_path:&str,config_path:&str,
    manifest_path:&str,capture_path:&str,bundle_path:&str)
    ->Result<(),Box<dyn std::error::Error>> {
    let config=crate::identity091::Config::load(config_path)?;
    config.require_game_network(crate::identity091::game_network::Runtime::SharedOwnedProfile13)?;
    if !config.profile13_battle || !config.research_service {return Err(model::bad().into());}
    let resources=super::profile13_templates::load(&config.local_root,Path::new(manifest_path))?;
    if config.p04m_pool&&!p04m_template_rows(&resources){return Err(model::bad().into());}
    let root=config.local_root.canonicalize()?;
    let bundle=Path::new(bundle_path).canonicalize()?;
    if bundle==root || !bundle.starts_with(&root) {return Err(model::bad().into());}
    crate::arena_vehicle091::verify_portable_bundle(&bundle)?;
    println!("SHARED_SOURCE_BUNDLE_BOUND root={} policy=HASH_ANCHORED_PORTABLE profile=MS1 state_sha256={}",
        bundle.display(),crate::arena_vehicle091::PRIMARY_STATE_SHA256);
    let initial=&resources[0];let map=initial.map;
    serve_with_pool(key_path,digest_path,config_path,capture_path,Some(initial.pool.clone()),Some(initial.geometry.clone()),
        true,Some(initial.terrain.clone()),None,Some(initial.catalog.clone()),map,VehicleKind::Ms1,Some(resources),None,Some(bundle))
}

/// Explicit temporary qualification scene. It uses frozen laboratory account
/// fixtures and never enters the owned writer/reservation/admission route.
pub fn serve_curated_lab(key_path:&str,digest_path:&str,config_path:&str,manifest_path:&str,
    capture_path:&str,kind:VehicleKind)->Result<(),Box<dyn std::error::Error>> {
    serve_curated_lab_policy(key_path,digest_path,config_path,manifest_path,capture_path,kind,false)
}
/// Separate explicit qualification policy. Existing curated mode keeps its
/// source-breech Unsupported behavior; this mode opts into unarmored Gun damage.
pub fn serve_curated_lab_v2(key_path:&str,digest_path:&str,config_path:&str,manifest_path:&str,
    capture_path:&str,kind:VehicleKind)->Result<(),Box<dyn std::error::Error>> {
    if !kind.is_extended(){return Err(model::bad().into());}
    serve_curated_lab_policy(key_path,digest_path,config_path,manifest_path,capture_path,kind,true)
}
fn serve_curated_lab_policy(key_path:&str,digest_path:&str,config_path:&str,manifest_path:&str,
    capture_path:&str,kind:VehicleKind,breech_v2:bool)->Result<(),Box<dyn std::error::Error>> {
    let config=crate::identity091::Config::load(config_path)?;
    config.require_game_network(crate::identity091::game_network::Runtime::LoopbackOnly)?;
    if config.profile13_battle||config.ammo_service||config.p04m_pool{return Err(model::bad().into());}
    let resources=super::profile13_templates::load(&config.local_root,Path::new(manifest_path))?;
    if resources.len()!=(if kind.is_extended(){7}else{5})||resources.iter().any(|row|row.shared.is_none()){return Err(model::bad().into());}
    let initial=&resources[0];
    println!("P04M_QUALIFICATION kind={} assignment=temporary_server_selected owned_inventory_changed=false battle_admission_changed=false",kind.label());
    if kind.is_extended(){println!("P06T_EXTENDED_QUALIFICATION policy={} device_policy={} temporary_ammunition=true inventory_grant=false scene_manifest=3",
        model::extended::POLICY,crate::p06t_device_state::POLICY_V2);}
    if breech_v2{println!("P06T_UNARMORED_BREECH_QUALIFICATION policy=test_lab.p06t.unarmored-gun-breech.v2 historical_server_solver=UNKNOWN");}
    let map=initial.map;
    serve_with_pool_policy(key_path,digest_path,config_path,capture_path,Some(initial.pool.clone()),Some(initial.geometry.clone()),
        true,Some(initial.terrain.clone()),None,Some(initial.catalog.clone()),map,VehicleKind::Ms1,Some(resources),Some(kind),breech_v2,None)
}

pub(super) fn selected_pool_map(pool: &crate::map_drive_worker091::Pool, selected: MapId)
    -> io::Result<&crate::map_drive_worker091::MapSpec> {
    let mut candidates=pool.maps.iter().filter(|map| map.asset==selected.asset());
    let map=candidates.next().ok_or_else(|| model::bad())?;
    if candidates.next().is_some() || map.arena_type_id!=selected.arena_type_id() { return Err(model::bad()); }
    Ok(map)
}

pub(super) fn selected_pool_config(pool: &crate::map_drive_worker091::Pool, selected: MapId) -> io::Result<serde_json::Value> {
    use std::io::Read;
    let map=selected_pool_map(pool,selected)?;
    // Pool load already validated ownership/schema; recheck these exact bytes
    // so a replaced config cannot substitute projectile geometry afterwards.
    let mut raw=Vec::new(); fs::File::open(&map.config)?.take(16385).read_to_end(&mut raw)?;
    if raw.is_empty() || raw.len()>16384 || format!("{:x}",Sha256::digest(&raw))!=map.config_sha256 { return Err(model::bad()); }
    let config=crate::map_drive_worker091::json(&raw,16384)?;
    if config["map"].as_str()!=Some(selected.asset())
        || config["terrain"]["sha256"].as_str()!=Some(selected.spec().terrain_manifest_sha256)
        || config["obstacles"]["sha256"].as_str()!=Some(selected.spec().physics_manifest_sha256) { return Err(model::bad()); }
    Ok(config)
}

fn terrain_for_pool(pool: &crate::map_drive_worker091::Pool) -> io::Result<Arc<super::terrain::Terrain>> {
    terrain_for_pool_for_map(pool,MapId::Karelia)
}

pub(super) fn terrain_for_pool_for_map(pool: &crate::map_drive_worker091::Pool, selected: MapId) -> io::Result<Arc<super::terrain::Terrain>> {
    let config=selected_pool_config(pool,selected)?;
    let path=config["terrain"]["path"].as_str().ok_or_else(|| model::bad())?;
    let terrain=super::terrain::Terrain::load_for(selected,&pool.local_root,Path::new(path))?;
    // Same original map resources, independently filtered with the original
    // projectile mask128. The vehicle-physics mask18 export is not substituted.
    let obstacle_path=pool.local_root.join(selected.spec().projectile_manifest_relative);
    let obstacles=super::obstacles::Obstacles::load_for(selected,&pool.local_root,&obstacle_path)?;
    Ok(Arc::new(terrain.with_obstacles(Arc::new(obstacles))?))
}

pub fn serve_integrated(key_path: &str, digest_path: &str, config_path: &str,
    pool_path: &str, capture_path: &str, geometry_path: Option<&str>, ap_test_lab: bool, terrain_test_lab: bool, destructible_test_lab: bool,catalog_path:Option<(&str,&str)>) -> Result<(), Box<dyn std::error::Error>> {
    serve_integrated_for_map(key_path,digest_path,config_path,pool_path,capture_path,geometry_path,
        ap_test_lab,terrain_test_lab,destructible_test_lab,catalog_path,MapId::Karelia)
}

pub fn serve_integrated_for_map(key_path: &str, digest_path: &str, config_path: &str,
    pool_path: &str, capture_path: &str, geometry_path: Option<&str>, ap_test_lab: bool, terrain_test_lab: bool,
    destructible_test_lab: bool,catalog_path:Option<(&str,&str)>,map:MapId) -> Result<(), Box<dyn std::error::Error>> {
    serve_integrated_for_vehicle(key_path,digest_path,config_path,pool_path,capture_path,geometry_path,
        ap_test_lab,terrain_test_lab,destructible_test_lab,catalog_path,map,VehicleKind::Ms1)
}

pub fn serve_integrated_for_vehicle(key_path: &str, digest_path: &str, config_path: &str,
    pool_path: &str, capture_path: &str, geometry_path: Option<&str>, ap_test_lab: bool, terrain_test_lab: bool,
    destructible_test_lab: bool,catalog_path:Option<(&str,&str)>,map:MapId,vehicle:VehicleKind) -> Result<(), Box<dyn std::error::Error>> {
    // Karelia keeps its accepted legacy lab modes; every other registry map
    // needs the full pinned stack (AP, terrain, pool), as Prohorovka did.
    if vehicle!=VehicleKind::Ms1 && (map==MapId::Karelia || !ap_test_lab || !terrain_test_lab) { return Err(model::bad().into()); }
    if map!=MapId::Karelia && (!ap_test_lab || !terrain_test_lab || destructible_test_lab) { return Err(model::bad().into()); }
    if ap_test_lab && geometry_path.is_none() { return Err(model::bad().into()); }
    if destructible_test_lab && !terrain_test_lab { return Err(model::bad().into()); }
    if catalog_path.is_some()&&(!terrain_test_lab||destructible_test_lab){return Err(model::bad().into());}
    if terrain_test_lab && !ap_test_lab { return Err(model::bad().into()); }
    let config = crate::identity091::Config::load(config_path)?;
    config.require_game_network(crate::identity091::game_network::Runtime::LoopbackOnly)?;
    if config.ammo_service { return Err(model::bad().into()); }
    let pool = crate::map_drive_worker091::Pool::load(&config.local_root, Path::new(pool_path))?;
    selected_pool_config(&pool,map)?;
    let geometry = geometry_path.map(|path| super::geometry::Bundle::load(&config.local_root, Path::new(path)))
        .transpose()?.map(Arc::new);
    validate_vehicle_binding(vehicle, &pool, geometry.as_deref())?;
    let terrain = if terrain_test_lab { Some(terrain_for_pool_for_map(&pool,map)?) } else { None };
    let removal = if destructible_test_lab {
        let path = pool.local_root.join("evidence/20261010-p06n-destructible-01/boundary/worker-ipc01/descriptor.json");
        Some(crate::map_drive_worker091::RemovalSpec::load(&pool.local_root,&path,
            "ef00e2aed686c16c4f9a216d9db70dbcd1ca3fda84bc33cd9eaa8aed1dbde7fa")?)
    } else { None };
    let catalog=if let Some((path,sha))=catalog_path{
        let path=Path::new(path);let catalog=Arc::new(super::fragiles::Catalog::load(&pool.local_root,path,sha)?);
        let worker=crate::map_drive_worker091::CatalogSpec::load(&pool.local_root,&path.parent().ok_or_else(|| model::bad())?.join(&catalog.worker_file),&catalog.worker_sha256)?;
        validate_catalog_projection(&catalog,&worker,map)?;
        Some((catalog,worker))
    }else{None};
    serve_with_pool(key_path, digest_path, config_path, capture_path, Some(Arc::new(pool)), geometry, ap_test_lab, terrain, removal,catalog,map,vehicle,None,None,None)
}

pub(super) fn validate_catalog_projection(catalog:&super::fragiles::Catalog,worker:&crate::map_drive_worker091::CatalogSpec,map:MapId)->io::Result<()> {
    if catalog.map!=map||worker.map_id()!=map||catalog.worker_sha256!=worker.sha256()||catalog.contacts!=worker.contacts()
        ||worker.version()!=catalog.version+1||worker.entries().len()!=catalog.objects.len()
        ||worker.entries().iter().zip(&catalog.objects).any(|(a,b)|if let Some(f)=&b.falling {
            // MAPS-02: the worker projects the separate trigger span, no energy.
            a.object_id()!=b.object_id||a.instance_id()!=b.instance_id||a.first_triangle()!=f.trigger_first_triangle
            ||a.triangle_count()!=f.trigger_triangle_count||a.object_revision()!=b.object_revision||a.kind()!=b.kind.worker_kind()
            ||a.ram_response()!=Some(crate::map_drive_worker091::FALLING_ATOM_RESPONSE)||a.ram_energy_j()!=0
        }else{
            a.object_id()!=b.object_id||a.instance_id()!=b.instance_id||a.first_triangle()!=b.physics_first_triangle
            ||a.triangle_count()!=b.physics_triangle_count||a.object_revision()!=b.object_revision||a.kind()!=b.kind.worker_kind()
            ||a.ram_response()!=catalog.ram_response(b)
            ||a.ram_energy_j()!=if catalog.version>=5||catalog.version==4&&matches!(b.kind,super::fragiles::ObjectKind::MovementFragile){super::fragiles::RAMMING_MIN_ENERGY_J as u32}else{0}}){return Err(model::bad());}
    Ok(())
}

pub(super) fn validate_vehicle_binding(vehicle:VehicleKind, pool:&crate::map_drive_worker091::Pool,
    geometry:Option<&super::geometry::Bundle>) -> io::Result<()> {
    if pool.vehicle_kind()!=vehicle || geometry.is_some_and(|bundle|bundle.vehicle_kind()!=vehicle)
        || vehicle!=VehicleKind::Ms1 && geometry.is_none() { return Err(model::bad()); }
    Ok(())
}


fn hold_training_close(pending:&mut Vec<(u32,&'static str)>,id:u32,reason:&'static str){
    if !pending.iter().any(|(old,_)|*old==id){pending.push((id,reason));}
}
fn retire_training_session(host:&mut Option<p10b_host::Host>,dispatcher:&mut profile13_dispatch::Dispatcher,
    table:&mut Table,world:&mut World,runtime:&mut Option<IntegratedRuntime>,template:&BattleTemplate,
    id:u32,reason:&'static str,now:Instant,logical_ms:u64)->io::Result<bool>{
    let h=host.as_mut().ok_or_else(||model::bad())?;
    if let Some(error)=h.prestart_failure(world,Some(id),now){
        contain_battle_failure(table,world,runtime,template,now,"training_prestart_disconnect",&error)?;
    }
    if h.closing(table,id,now,logical_ms)?{return Ok(false);}
    if h.previously_retired(id){
        let index=table.sessions.iter().position(|s|s.id==id).ok_or_else(||model::bad())?;
        if table.sessions[index].active||world.actors.iter().any(|a|a.session==Some(id))
            ||table.sessions[index].shared.as_ref().and_then(|c|c.profile13.as_ref()).is_none_or(|p|!p.garage_idle()){
            return Err(model::bad());
        }
        table.sessions.remove(index);
        println!("P10B_HELD_SESSION_CLOSED session={id} all_reserves_released=true reason={reason}");
    }else{dispatcher.retire(table,world,id,now,reason)?;}
    h.forget_session(id);Ok(true)
}


/// Writer/result faults must cross the same training retirement boundary as a
/// native disconnect. A held/failed close remains queued, including its first
/// reason, and no Host/Registry/member metadata is discarded.
fn retire_service_failure(host:&mut Option<p10b_host::Host>,dispatcher:&mut profile13_dispatch::Dispatcher,
    table:&mut Table,world:&mut World,runtime:&mut Option<IntegratedRuntime>,template:&BattleTemplate,
    pending:&mut Vec<(u32,&'static str)>,id:u32,reason:&'static str,now:Instant,logical_ms:u64)->io::Result<()>{
    if host.is_none(){return dispatcher.retire(table,world,id,now,reason);}
    match retire_training_session(host,dispatcher,table,world,runtime,template,id,reason,now,logical_ms){
        Ok(true)=>{},
        Ok(false)=>hold_training_close(pending,id,reason),
        Err(error)=>{println!("P10B_CLOSE_RETRY session={id} error={error} service_alive=true");hold_training_close(pending,id,reason);},
    }Ok(())
}

/// ARENA-01: the arena a live session belongs to (lobby for a hangar session).
fn session_home(table:&Table,arenas:&[arena::Arena],dispatcher:&profile13_dispatch::Dispatcher,id:u32)->usize {
    let lobby=arena::lobby(arenas,table,dispatcher.retired_sessions());
    table.sessions.iter().find(|s|s.id==id).map_or(lobby,|s|arena::home(s,arenas,lobby))
}
/// A results fault retires its session inside that session's arena only.
fn contain_results_failure_in_arenas(manager:&super::results_session::Manager,host:&mut Option<p10b_host::Host>,
    dispatcher:&mut profile13_dispatch::Dispatcher,table:&mut Table,arenas:&mut [arena::Arena],
    pending:&mut Vec<(u32,&'static str)>,now:Instant,logical_ms:u64,error:&io::Error)->io::Result<()>{
    let home=manager.failure_session(&table.sessions).map_or(0,|id|session_home(table,arenas,dispatcher,id));
    let a=&mut arenas[home];
    contain_results_failure_with_training(manager,host,dispatcher,table,&mut a.world,&mut a.integrated,&a.template,pending,now,logical_ms,error)
}

/// Retain the old helper/API for ordinary mode and its existing tests. Explicit
/// training mode must never remove a room member behind Host's back.
fn contain_results_failure_with_training(manager:&super::results_session::Manager,host:&mut Option<p10b_host::Host>,
    dispatcher:&mut profile13_dispatch::Dispatcher,table:&mut Table,world:&mut World,
    runtime:&mut Option<IntegratedRuntime>,template:&BattleTemplate,pending:&mut Vec<(u32,&'static str)>,
    now:Instant,logical_ms:u64,error:&io::Error)->io::Result<()>{
    if host.is_none(){return contain_results_failure(manager,dispatcher,table,world,now,error);}
    let target=manager.failure_session(&table.sessions);
    println!("P08C_RESULTS_SESSION_FAILED session={target:?} error={error} service_alive=true durable_result_retained=true");
    if let Some(id)=target.filter(|id|table.sessions.iter().any(|s|s.id==*id)){
        retire_service_failure(host,dispatcher,table,world,runtime,template,pending,id,"native_results_delivery",now,logical_ms)?;
    }Ok(())
}

fn serve_with_pool(key_path: &str, digest_path: &str, config_path: &str, capture_path: &str,
    integrated_pool: Option<Arc<crate::map_drive_worker091::Pool>>, geometry: Option<Arc<super::geometry::Bundle>>, ap_test_lab: bool,
    terrain: Option<Arc<super::terrain::Terrain>>, removal: Option<crate::map_drive_worker091::RemovalSpec>,catalog:Option<(Arc<super::fragiles::Catalog>,crate::map_drive_worker091::CatalogSpec)>,map:MapId,vehicle:VehicleKind,resources:Option<Vec<super::profile13_templates::Resources>>,qualification:Option<VehicleKind>,source_bundle:Option<PathBuf>)
    -> Result<(), Box<dyn std::error::Error>> {
    serve_with_pool_policy(key_path,digest_path,config_path,capture_path,integrated_pool,geometry,ap_test_lab,
        terrain,removal,catalog,map,vehicle,resources,qualification,false,source_bundle)
}
fn serve_with_pool_policy(key_path:&str,digest_path:&str,config_path:&str,capture_path:&str,
    integrated_pool:Option<Arc<crate::map_drive_worker091::Pool>>,geometry:Option<Arc<super::geometry::Bundle>>,ap_test_lab:bool,
    terrain:Option<Arc<super::terrain::Terrain>>,removal:Option<crate::map_drive_worker091::RemovalSpec>,
    catalog:Option<(Arc<super::fragiles::Catalog>,crate::map_drive_worker091::CatalogSpec)>,map:MapId,vehicle:VehicleKind,
    resources:Option<Vec<super::profile13_templates::Resources>>,qualification:Option<VehicleKind>,breech_v2:bool,source_bundle:Option<PathBuf>)
    ->Result<(),Box<dyn std::error::Error>> {
    if breech_v2&&!qualification.is_some_and(VehicleKind::is_extended){return Err(model::bad().into());}
    if ap_test_lab && (integrated_pool.is_none() || geometry.is_none()) { return Err(model::bad().into()); }
    if terrain.is_some() && !ap_test_lab { return Err(model::bad().into()); }
    if let Some(pool)=&integrated_pool { selected_pool_config(pool,map)?; validate_vehicle_binding(vehicle,pool,geometry.as_deref())?; }
    else if vehicle!=VehicleKind::Ms1 { return Err(model::bad().into()); }
    if terrain.as_ref().is_some_and(|t|t.map_id()!=map)
        || catalog.as_ref().is_some_and(|(c,w)|c.map!=map||w.map_id()!=map)
        || map!=MapId::Karelia && (integrated_pool.is_none()||!ap_test_lab||terrain.is_none()||removal.is_some()) {
        return Err(model::bad().into());
    }
    let config = Arc::new(crate::identity091::Config::load(config_path)?);
    if config.catalog_v1{crate::profile13_v2091::enable_catalog_v1()?;
        println!("CATALOG_V1 enabled sha256={}",super::vehicle_catalog::CATALOG_SHA256);}
    if let Some(endpoint)=config.domain_endpoint(){println!("DOMAIN_SERVICE enabled endpoint={endpoint}");}
    let profile13_mode=resources.is_some()&&qualification.is_none();
    if source_bundle.is_some()&&!profile13_mode {return Err(model::bad().into());}
    config.require_game_network(if profile13_mode{crate::identity091::game_network::Runtime::SharedOwnedProfile13}else{crate::identity091::game_network::Runtime::LoopbackOnly})?;
    if config.profile13_battle!=profile13_mode || config.ammo_service!=profile13_mode { return Err(model::bad().into()); }
    let private = login::load_key(key_path)?;
    if fs::metadata(digest_path)?.len() != 16 { return Err(model::bad().into()); }
    let digest: [u8; 16] = fs::read(digest_path)?.try_into().map_err(|_| model::bad())?;
    let login_socket = UdpSocket::bind(config.login_bind)?;
    let base_socket = UdpSocket::bind(config.base_bind)?;
    login_socket.set_nonblocking(true)?; base_socket.set_nonblocking(true)?;
    let capture_profile = if integrated_pool.is_some() { crate::capture091::Profile::IntegratedWorldV1 }
        else { crate::capture091::Profile::SharedWorldV1 };
    let mut capture = Some(Recorder::open_profile(capture_path, &config.local_root, capture_profile)?);
    if config.battle_players!=2&&resources.as_ref().is_none_or(|rows|rows[0].shared.is_none()){return Err(model::bad().into());}
    let mut table = Table{capacity:if config.training_rooms{crate::training091::domain::MAX_ACCOUNTS}else{config.battle_players},..Table::default()};
    // GW-01: connections are bounded separately from arena places; the replay
    // window and datagram budget scale with them. Absent key = old path.
    let mut datagram_budget=crate::identity091::game_network::DATAGRAMS_PER_SECOND;let mut drain=1usize;
    if let Some(connections)=config.connection_capacity {
        if !profile13_mode||connections<config.battle_players {return Err(model::bad().into());}
        table.capacity=connections;table.arena_split=true;table.retirement=RetirementWindow::with_limit(connections*4);
        datagram_budget=datagram_budget.max(u32::try_from(connections*4).map_err(|_|model::bad())?);drain=CAPACITY_DRAIN;
    }
    let mut room_host=if config.training_rooms{Some(p10b_host::Host::for_config(&config)?)}else{None};
    let mut room_closing:Vec<(u32,&'static str)>=Vec::new();
    let mut battle_dispatch=profile13_dispatch::Dispatcher::default();
    if config.p08c_late_results{
        battle_dispatch.late=Some(super::late_results_runtime::Manager::new(config.p08c_late_results_accounts.clone(),config.p08c_late_notice_experimental)?);
        println!("P08C_LATE_RESULTS_BOUND policy={} configured_owners={} native_notice_experimental={} native_method=INFERRED",super::late_results_capture::POLICY,config.p08c_late_results_accounts.len(),config.p08c_late_notice_experimental);
    }
    if room_host.is_some(){battle_dispatch.enable_training_finished();}
    let mut garage:Vec<GarageJob>=Vec::new();
    let mut result_manager=super::results_session::Manager::default();
    let started = Instant::now();
    // Native Account.doCmdInt3 carries the result arena key as signed INT64.
    // ARENA-01: K > 1 arenas get non-overlapping battle id ranges; one arena keeps the old id.
    let arena_ids=if config.arenas>1 {Some(arena::arena_ids(config.arenas,OsRng.next_u64())?)} else {None};
    let mut world = World::new_for_vehicle(arena_ids.as_ref().map_or_else(||(OsRng.next_u64() & i64::MAX as u64).max(1),|ids|ids[0]), started,map,vehicle)?;
    if let Some(bundle) = geometry {
        let geometry_revision=super::geometry::source_revision(vehicle);
        let material_revision=super::materials::profile_revision(vehicle);
        let bundle_sha256=bundle.bundle_sha256().to_owned();
        world.bind_geometry(bundle)?;
        println!("SHARED_GEOMETRY_BOUND battle={} vehicle={} revision={} material_revision={} bundle_sha256={} scope=other_actor_only damage={} terrain_projectiles={}",
            world.id, vehicle.label(), geometry_revision, material_revision, bundle_sha256, ap_test_lab, terrain.is_some());
    }
    if ap_test_lab {
        world.enable_ap_test_lab()?;
        println!("SHARED_AP_PROFILE revision={} historical_fidelity={} damage={} rng=false friendly_fire=true persistence={}",
            ap::profile_revision_for(vehicle),ap::HISTORICAL_FIDELITY,vehicle.damage(),profile13_mode);
    }
    if let Some(terrain) = terrain {
        let revision=terrain.source_revision();
        world.bind_terrain(terrain)?;
        println!("SHARED_TERRAIN_BOUND battle={} revision={} manifest_sha256={} obstacle_manifest_sha256={} map={} geometry=original_world material=source_kind terrain_only=false obstacles=true projectile_mask=128 tie_policy=world_first_f32_bucket",
            world.id,revision,map.spec().terrain_manifest_sha256,map.spec().projectile_manifest_sha256,map.asset());
    }
    if removal.is_some() { world.bind_destructible_test_lab()?; }
    if let Some((catalog,_))=&catalog{world.bind_fragiles(catalog.clone())?;
        println!("SHARED_CATALOG_BOUND battle={} sha256={} objects={} chunks={:?} policy={} historical_fidelity=approximate_reference_health",world.id,catalog.sha256,catalog.objects.len(),catalog.chunks(),super::fragiles::policy_for(world.vehicle_kind()));}
    let mut integrated = integrated_pool.map(|pool|IntegratedRuntime::new_for_map(pool,map));
    if let Some(runtime) = &mut integrated { runtime.removal = removal; }
    if let Some(runtime)=&mut integrated {runtime.catalog=catalog.map(|(_,worker)|worker);}
    if profile13_mode { world.enable_lifecycle(super::lifecycle::Rules::prohorovka())?; }
    let mut battle_template=BattleTemplate::new(&world,&integrated);
    if let Some(rows)=resources.as_ref().filter(|rows|rows[0].shared.is_some()){
        battle_template=BattleTemplate::from_shared_policy(rows,config.battle_players,world.id,started,qualification,breech_v2)?;
        battle_template.select(&mut world,&mut integrated,started)?;
    }
    if profile13_mode {
        // SPAWN-15 / owner stand 2026-10-28: a debug gateway keeps up only with
        // two battle places (four places: scheduler lag p50 156 ms, fail-closed).
        let debug=cfg!(debug_assertions);
        println!("GATEWAY_BUILD profile={} battle_players={} arenas={} supported={}",if debug{"debug"}else{"release"},
            config.battle_players,config.arenas,!debug||config.battle_players<=2);
    }
    if config.team_base_spawn{
        // SPAWN-15: only the shared Jolt scene places teams; refuse a roster the
        // map's formation cannot hold before any account is admitted.
        if !profile13_mode||!battle_template.world.mixed_profiles(){return Err(model::bad().into());}
        let teams=(0..config.battle_players).map(|slot|(slot%2) as u8+1).collect::<Vec<_>>();
        super::team_spawn::placement(battle_template.world.map,&teams)?;
        battle_template.world.enable_team_base_spawn()?;
        battle_template.select(&mut world,&mut integrated,started)?;
        println!("SPAWN15_POLICY_BOUND policy={} map={} places={} per_team_max={} native_layout={} historical_spawns=UNKNOWN",
            super::team_spawn::POLICY,battle_template.world.map.asset(),config.battle_players,super::team_spawn::PER_TEAM,
            if config.battle_players>wire::MAX_NATIVE_ACTORS{"spawn15-30"}else{"six"});
    }
    if config.p06t_mixed_ammo{
        if !profile13_mode||qualification.is_some(){return Err(model::bad().into());}
        battle_template.world.enable_mixed_ammo()?;
        battle_template.select(&mut world,&mut integrated,started)?;
        println!("P06T_ARMAMENT_BOUND policy={} damage_policy={} device_policy={} proxy_policy={} module_admission={} source={} historical_internal_volumes=UNKNOWN",
            crate::p06t_armament091::POLICY,crate::p06t_damage::POLICY,crate::p06t_device_state::POLICY,
            crate::p06t_lab_proxy::POLICY,model::p06t::MODULE_ADMISSION_POLICY,crate::p06t_shells091::SOURCE_REVISION);
    }
    if profile13_mode && config.visibility_v1 {
        battle_template.world.enable_original_spotting(super::spotting::Rules::selected()?)?;
        battle_template.world.enable_result_spots()?;
        battle_template.select(&mut world,&mut integrated,started)?;
        println!("P08C_FIRST_SPOT_BOUND policy={}", model::result_spots::POLICY);
    }
    if config.p06t_ammo_rack_detonation{
        if !profile13_mode||!config.p06t_mixed_ammo||!config.visibility_v1||qualification.is_some(){return Err(model::bad().into());}
        battle_template.world.enable_ammo_detonation()?;
        battle_template.select(&mut world,&mut integrated,started)?;
        println!("P06T_AMMO_DETONATION_BOUND policy={} flight_policy={} jolt_launch_policy={} jolt_body_policy={} historical_solver=UNKNOWN",
            super::ammo_detonation::POLICY,super::ammo_detonation::FLIGHT_POLICY,super::ammo_detonation::JOLT_POLICY,crate::scene_worker::TURRET_POLICY);
    }
    if let Some(plan)=&config.bots{
        // Config already requires profile13, connection capacity, visibility and no hold5/training.
        if !profile13_mode||qualification.is_some()||battle_template.shared.is_none()||!table.arena_split||!config.visibility_v1{return Err(model::bad().into());}
        battle_template.world.enable_bots(plan.clone()).map_err(|_|io::Error::other("BOT-01 bots: kinds not bound by the battle profiles or map unsupported"))?;
        battle_template.select(&mut world,&mut integrated,started)?;
        println!("BOT01_POLICY_BOUND policy={} human_places={} places={} bots={} kinds={:?} seed={} accounts=none",
            model::bots::POLICY,plan.human_places,config.battle_players,config.battle_players-plan.human_places,
            plan.kinds.iter().map(|k|k.label()).collect::<Vec<_>>(),plan.seed);
    }
    if config.p08b_owner_battle_hold{
        battle_template.world.enable_owner_hold()?;battle_template.select(&mut world,&mut integrated,started)?;
        println!("P08B_HOLD5_BOUND policy={} early_finish=false training_supported=false",crate::profile13_hold091::POLICY_SHA256);
    }
    // ARENA-01: further arenas are fresh battles of the same validated template,
    // each with its own scene runtime. Config already refused hold5/training.
    if config.arenas>1&&(!profile13_mode||battle_template.shared.is_none()||!table.arena_split){return Err(model::bad().into());}
    table.multi_arena=config.arenas>1;
    let mut arenas=vec![arena::Arena::new(0,world,integrated,battle_template)];
    for (index,id) in arena_ids.iter().flatten().enumerate().skip(1) {
        let next=arena::Arena::from_template(index,&arenas[0].template,*id,started)?;arenas.push(next);
    }
    let mut next_id = 1u32;
    // Owner hold and training rooms keep one login/garage writer at a time:
    // their writers have no per-account owner to separate accounts by.
    let serial_writers=config.p08b_owner_battle_hold||config.training_rooms;
    let mut admission=Admission::new(if serial_writers {1} else {login_admission::MAX_IDENTITY_JOBS})?;
    let garage_limit=if serial_writers {1} else {MAX_GARAGE_JOBS};
    let mut fragments = login::LoginFragments::default();
    let mut rate_started = started; let mut rate_count = 0u32;
    println!("BOUND {} base_backend={} profile={} battle={} capacity={} scope=allied_temporary_{} motion={} physics={} map={} arena_type_id={} inventory_changed=false",
        config.login_bind, config.base_bind,
        if profile13_mode {"legacy091-profile13"} else if qualification.is_some(){"legacy091-curated-lab"}else if arenas[0].integrated.is_some() { "legacy091-integrated-lab" } else { "legacy091-shared-lab" },
        arenas[0].world.id,arenas[0].world.expected_actors(),arenas[0].world.vehicle_kind().label(), if arenas[0].integrated.is_some() { "map_drive_worker" } else { "bounded_kinematic" }, arenas[0].integrated.is_some(),map.asset(),map.arena_type_id());
    if table.arena_split {
        println!("GATEWAY_CAPACITY connections={} arena_places={} retired_limit={} datagrams_per_second={datagram_budget} drain={drain} policy=gw01-hangar-holds-no-arena-place",
            table.capacity,arenas[0].world.expected_actors(),table.retirement.limit());
    }
    if arenas.len()>1 {
        println!("ARENAS count={} places_per_arena={} battles={:?} step_threads=scoped_per_tick policy=arena01-in-process",
            arenas.len(),arenas[0].world.expected_actors(),arenas.iter().map(|a|a.world.id).collect::<Vec<_>>());
    }
    // MM-01: a Join queues; groups take free arenas. Config already requires bots and the P04M pool.
    let mut matchmaker=match (&config.matchmaker,&config.bots) {
        (None,_)=>None,
        (Some(rules),Some(plan)) if profile13_mode&&table.arena_split&&arenas[0].world.bot_plan().is_some()=>{
            let runtime=matchmaking::Runtime::new(rules.clone(),plan)?;
            println!("MM01_POLICY_BOUND policy={} team_size={} places={} tiers={}..{} tier_spread={} wait_s={} lease_s={} arenas={} bot_tiers={:?} historical_matchmaker=UNKNOWN",
                super::matchmaker::POLICY,rules.team_size,rules.places(),rules.tiers.0,rules.tiers.1,rules.tier_spread,rules.wait.as_secs(),
                rules.lease.as_secs(),arenas.len(),runtime.bot_tiers().iter().map(|(k,t)|format!("{}:{t}",k.label())).collect::<Vec<_>>());
            Some(runtime)
        },
        _=>return Err(model::bad().into()),
    };
    let mut net_stats=super::net01::LoopStats::default();
    println!("NET01_POSE_DELIVERY mode={} report_s={}",config.pose_delivery.label(),super::net01::REPORT.as_secs());
    loop {
        let now = Instant::now();
        if now.duration_since(started) >= if profile13_mode {PROFILE13_SERVICE_LIFETIME} else {model::LIFETIME} {
            println!("SHARED_STOP reason=lab_lifetime"); break;
        }
        if now.duration_since(rate_started) >= Duration::from_secs(1) { rate_started = now; rate_count = 0; }
        let mut closing: Vec<(u32, &'static str)> = std::mem::take(&mut room_closing);
        let logical_ms=u64::try_from(now.saturating_duration_since(started).as_millis()).map_err(|_|model::bad())?;
        for (pending, result) in admission.completed(now) {
            let job = pending.job;
            match result {
                Ok(Some(accepted)) => {
                    // A hangar session joins no arena; its log names the arena a Join would take.
                    let lobby=arena::lobby(&arenas,&table,battle_dispatch.retired_sessions());
                    let admitted = (|| -> io::Result<usize> {
                        table.admissible(&job.attempt, now)?;
                        if let Some(index) = table.sessions.iter().position(|s| s.same_login_attempt(&job.attempt)) {
                            if !table.sessions[index].verified_duplicate(&job.attempt, &accepted.identity.account_id) { return Err(model::bad()); }
                            return Ok(index);
                        }
                        if battle_dispatch.owner_busy(&accepted.identity.account_id) || table.sessions.iter().any(|s| s.identity.as_ref().is_some_and(|p| p.account_id == accepted.identity.account_id))
                            || garage.iter().any(|g| g.account_id == accepted.identity.account_id)
                            || result_manager.owner_account() == Some(accepted.identity.account_id.as_str()) { return Err(model::bad()); }
                        if let Some(root)=source_bundle.as_deref() {
                            if accepted.identity.account_id==crate::arena_vehicle091::PRIMARY_ACCOUNT {
                                let seed=crate::arena_vehicle091::load_source_bundle(&accepted.identity,root)?;
                                if seed.descriptor!=crate::arena_vehicle091::MS1_DESCRIPTOR || seed.health!=90 {
                                    return Err(model::bad());
                                }
                                println!("SHARED_SOURCE_BUNDLE_VERIFIED account={} database={} native_inventory_id=1 type_compact_descr=3329 health=90 state_sha256={} policy=HASH_ANCHORED_PORTABLE",
                                    accepted.identity.account_id,accepted.identity.database_id,crate::arena_vehicle091::PRIMARY_STATE_SHA256);
                            }
                        }
                        let mut s = Session::new(next_id, job.attempt.key, job.attempt.login_peer, now);
                        // Explicitly fail closed on the astronomically unlikely
                        // random capability collision instead of ambiguous routing.
                        if s.handoff == 0 || s.token == 0 || table.sessions.iter().any(|old| old.handoff == s.handoff || old.token == s.token) { return Err(model::bad()); }
                        let mut next_world = arenas[lobby].world.clone();
                        let slot = if profile13_mode {0} else {
                            let who=model::Identity{account:accepted.identity.account_id.clone(),database:accepted.identity.database_id,name:accepted.identity.name.clone()};
                            if next_world.extended_lab(){
                                next_world.attach_extended_lab(who,next_id,model::extended::LabLoadout::temporary(next_world.vehicle_kind()))?
                            }else{next_world.attach(who,next_id)?}
                        };
                        s.account_probe = true; s.account_ready = true; s.tx = Window::interactive();
                        s.login_attempt = Some(job.attempt); s.login_account = Some(pending.account); s.identity = Some(accepted.identity);
                        s.hangar = Some(accepted.fixtures); s.shared = Some(Client::new(slot));
                        if config.visibility_v1 {s.shared.as_mut().ok_or_else(||model::bad())?.enable_spotting()?;}
                        s.shared.as_mut().ok_or_else(||model::bad())?.set_pose_delivery(config.pose_delivery)?;
                        if profile13_mode {
                            let binding=accepted.ammo_service.ok_or_else(||model::bad())?;
                            s.ammo_service=Some(ammo_session::State::new(binding,accepted.crew_service).with_transfer(accepted.crew_transfer).with_cross_vehicle(accepted.crew_cross_vehicle).with_roster_recruitment(accepted.crew_roster_recruitment).with_progression(accepted.crew_progression).with_dismissal(accepted.crew_dismissal).with_barracks(accepted.crew_barracks_recruitment).with_research(accepted.research_service));
                            s.ammo_service.as_mut().ok_or_else(||model::bad())?.replace_pool(s.hangar.as_ref().and_then(|f|f.p04m_binding()).cloned())?;
                            let c=s.shared.as_mut().ok_or_else(||model::bad())?;c.join_requested=false;
                            c.profile13=Some(super::profile13_session::State::new(config.battle_run_id.clone(),binding.revision)?);
                            if config.p08b_owner_battle_hold{
                                battle_dispatch.install_hold_login(&mut s,accepted.owner_hold.ok_or_else(||model::bad())?)?;
                            }
                        }
                        if let Some(host)=&mut room_host{host.bind_session(&mut s)?;}
                        println!("SHARED_SESSION_PENDING battle={} session={next_id} slot={slot} account={} database={} authenticated=true", arenas[lobby].world.id,
                            s.identity.as_ref().ok_or_else(|| model::bad())?.account_id, s.identity.as_ref().ok_or_else(|| model::bad())?.database_id);
                        // BOT-01: the bot session band is never handed to a native login.
                        next_id = next_id.checked_add(1).filter(|id|*id<model::bots::SESSION_BASE).ok_or_else(|| model::bad())?;
                        arenas[lobby].world = next_world; table.sessions.push(s); Ok(table.sessions.len() - 1)
                    })();
                    match admitted {
                        Ok(index) => {
                            let s = &table.sessions[index];
                            send_wire(&login_socket, job.attempt.login_peer, &redirect091::reply_advertised(job.request, &s.key, s.handoff, config.game_network().advertised_base())?, Channel::Login, &mut capture)?;
                        },
                        Err(_) => { send_wire(&login_socket, job.attempt.login_peer, &login::rejection(job.request, 73), Channel::Login, &mut capture)?;
                            println!("SHARED_AUTH_REJECT reason=admission_or_world_capacity allocated=0"); },
                    }
                },
                Ok(None) => { send_wire(&login_socket, job.attempt.login_peer, &login::rejection(job.request, 67), Channel::Login, &mut capture)?; },
                Err(error) => { send_wire(&login_socket, job.attempt.login_peer, &login::rejection(job.request, 73), Channel::Login, &mut capture)?;
                    println!("SHARED_AUTH_REJECT reason=identity_unavailable allocated=0 error={error}"); },
            }
        }
        for (is_login, socket) in [(true, &login_socket), (false, &base_socket)] {
            // GW-01: drain up to `drain` datagrams per socket per tick (1 = old path).
            for _ in 0..drain {
                let mut data = [0u8; 65536];
                let (length, peer) = match socket.recv_from(&mut data) {
                    Ok(value) => value, Err(error) if error.kind() == io::ErrorKind::WouldBlock => break,
                    Err(error) if error.raw_os_error() == Some(10054) => continue,
                    Err(error) => return Err(error.into()),
                };
                if !config.game_network().admit_datagram_within(peer,length,if is_login{login::MAX_INTERACTIVE_DATAGRAM}else{1024},&mut rate_count,datagram_budget){continue;}
                if let Some(recorder) = &mut capture { recorder.observe(if is_login { Channel::Login } else { Channel::Base }, true, peer, &data[..length]); }
                let packet = &data[..length];
                if is_login {
                    let assembled = match fragments.push(peer, now, packet) { Ok(Some(value)) => value, Ok(None) => continue,
                        Err(_) => { println!("SHARED_REJECT reason=login_fragments"); continue; } };
                    let (request, fields) = match login::decode_interactive(&assembled, &private) {
                        Ok(value) => value, Err(_) => { println!("SHARED_REJECT reason=login_framing"); continue; }
                    };
                    if fields.digest != digest { send_wire(socket, peer, &login::rejection(request, 69), Channel::Login, &mut capture)?; continue; }
                    let attempt = LoginAttempt::new(fields.session_key, fields.nonce, peer);
                    if admission.refresh(request,&attempt,&fields) {
                        println!("AUTH_PENDING_DUPLICATE request_id={request} reply_request_refreshed=true");
                        continue;
                    }
                    if table.admissible(&attempt, now).is_err() {
                        send_wire(socket, peer, &login::rejection(request, 73), Channel::Login, &mut capture)?;
                        if table.arena_split {println!("GATEWAY_CAPACITY_REJECT request_id={request} sessions={} capacity={} retired={} retired_limit={} code=73",
                            table.sessions.len(),table.capacity,table.retirement.retained_count(),table.retirement.limit());}
                        continue;
                    }
                    let account=match crate::identity091::credentials(&fields.username,&fields.password) {
                        Ok((email,_))=>admission.account(&email),
                        Err(_)=>{ send_wire(socket, peer, &login::rejection(request, 73), Channel::Login, &mut capture)?;
                            println!("SHARED_LOGIN_REJECT request_id={request} reason=unsupported_native_credentials code=73"); continue; },
                    };
                    let writers=login_writers(serial_writers,&battle_dispatch,&result_manager,&room_host,&garage,&table);
                    let sessions=table.sessions.iter().chain(battle_dispatch.retired_sessions())
                        .map(|s|(s.login_account,s.same_login_attempt(&attempt)));
                    match admission.decide(&attempt,&account,sessions,&writers,now) {
                        Decision::Start => match start_auth(config.clone(), request, peer, &fields, false) {
                            Ok(job) => { admission.started(job,account,now);
                                println!("SHARED_LOGIN_STARTED request_id={request} identity_jobs={}",admission.len()); },
                            Err(_) => { send_wire(socket, peer, &login::rejection(request, 73), Channel::Login, &mut capture)?;
                                println!("SHARED_LOGIN_REJECT request_id={request} reason=identity_start code=73"); },
                        },
                        Decision::Defer(reason) => if admission.defer(attempt,now) {
                            println!("SHARED_LOGIN_DEFERRED request_id={request} reason={reason} waited_ms={} max_wait_ms={}",
                                admission.waited(&attempt,now).as_millis(),admission.max_wait().as_millis());
                        } else {
                            send_wire(socket, peer, &login::rejection(request, 73), Channel::Login, &mut capture)?;
                            println!("SHARED_LOGIN_REJECT request_id={request} reason={reason}_window code=73");
                        },
                        Decision::Reject(reason) => { send_wire(socket, peer, &login::rejection(request, 73), Channel::Login, &mut capture)?;
                            println!("SHARED_LOGIN_REJECT request_id={request} reason={reason} code=73"); },
                    }
                } else {
                    let index = match table.route_with_network(peer, packet,config.game_network()) { Ok(i) => i, Err(_) => { println!("SHARED_REJECT reason=base_route"); continue; } };
                    if table.sessions[index].guard_base_peer(&mut table.retirement,peer,now).is_err(){println!("SHARED_REJECT reason=retired_peer");continue;}
                    let h=session_home(&table,&arenas,&battle_dispatch,table.sessions[index].id);
                    if length == 21 {
                        let s=&mut table.sessions[index];
                        let (request, _) = base::base_request(packet, s.handoff)?;
                        s.base_peer = Some(peer); send(socket, peer, &base::base_reply(request, s.token), &s.key, &mut capture)?;
                        println!("SHARED_BASE_BOUND battle={} session={} peer={peer}", arenas[h].world.id, s.id);
                    } else {
                        let sid=table.sessions[index].id;
                        let frame=match base::decrypt(packet,&table.sessions[index].key).and_then(|b|transport091::parse_interactive(&b)){
                            Ok(frame)=>frame,Err(_)=>{println!("SHARED_REJECT session={sid} reason=channel_framing");continue;}
                        };
                        let received=if let Some(host)=&mut room_host{host.receive(&mut table,sid,&frame,&arenas[h].world,now,logical_ms)}else{
                            let s=&mut table.sessions[index];
                            receive_battle_session(s,&frame,&arenas[h].world,now)
                        };
                        let s=&mut table.sessions[index];
                        match received {
                            Ok(close) => {
                                if frame.flags & 0x10 != 0 { send(socket, peer, &transport091::ack(s.rx), &s.key, &mut capture)?; s.last_keepalive = now; }
                                if close { closing.push((s.id, "client_disconnect")); }
                            },
                            Err(error) => println!("SHARED_REJECT session={} reason=channel_state sequence={:?} bytes={} error={error}", s.id, frame.sequence, frame.body.len()),
                        }
                    }
                }
            }
        }
        // Remove known disconnects before applying any queued intent or tick.
        for(id,reason)in closing.drain(..){
            if !table.sessions.iter().any(|s|s.id==id){continue;}
            let home=session_home(&table,&arenas,&battle_dispatch,id);let a=&mut arenas[home];
            if containment::retire_contained_or_drop(&mut table,&mut battle_dispatch,&mut a.world,id,now,reason){continue;}
            if room_host.is_none(){containment::retire_or_contain(&mut table,&mut battle_dispatch,a,id,now,reason);continue;}
            match retire_training_session(&mut room_host,&mut battle_dispatch,&mut table,&mut a.world,&mut a.integrated,&a.template,id,reason,now,logical_ms){
                Ok(true)=>{},Ok(false)=>hold_training_close(&mut room_closing,id,reason),
                Err(error)=>{println!("P10B_CLOSE_RETRY session={id} error={error} service_alive=true");hold_training_close(&mut room_closing,id,reason);}
            }
        }
        if profile13_mode {
            if let Err(error)=result_manager.poll(&mut table.sessions,now) {
                contain_results_failure_in_arenas(&result_manager,&mut room_host,&mut battle_dispatch,&mut table,&mut arenas,
                    &mut room_closing,now,logical_ms,&error)?;
            }
            let lobby=arena::lobby(&arenas,&table,battle_dispatch.retired_sessions());
            // BATTLE_BUSY only when no arena can take this Join (with one arena: it started).
            let all_started=arenas[lobby].started()||arenas[lobby].closed.is_some();
            let mut leave_failures:Vec<(usize,io::Error)>=Vec::new();
            for s in &mut table.sessions {
                let home=arena::home(s,&arenas,lobby);let a=&mut arenas[home];
                // An explicitly contained old Avatar has no authority in the
                // replacement World, including the terminal-freeze pass.
                if s.shared.as_ref().is_some_and(|c|c.contained_world.is_some()) {
                    if let Err(error)=contained_return_world(s,&a.world) {
                        println!("SHARED_CONTAINED_RETURN_FAILED session={} reason={error} replacement_world_unchanged=true",s.id);
                        closing.push((s.id,"contained_terminal_return_failed"));
                    }
                    continue;
                }
                // MM-01: a queued Join waits for a free arena instead.
                if all_started&&matchmaker.is_none() {
                    let busy=s.shared.as_ref().and_then(|c|c.profile13.as_ref()).is_some_and(|p|
                        p.selection.is_some() && !p.has_reservation() && !p.in_flight);
                    if busy {
                        let c=s.shared.as_mut().ok_or_else(||model::bad())?;
                        c.profile13.as_mut().ok_or_else(||model::bad())?.selection=None;c.join_requested=false;
                        s.outbox.push_back(crate::battle091::profile13::enqueue_failure("BATTLE_BUSY")?);
                        println!("P08B_ADMISSION_BUSY session={} battle={} peer_battle_unchanged=true",s.id,a.world.id);
                    }
                }
                let pending=s.shared.as_ref().is_some_and(|c|c.profile13.is_some() &&
                    (c.phase==Phase::Leaving || c.phase==Phase::Account && !c.join_requested
                        && c.profile13.as_ref().is_some_and(|p|p.has_reservation()&&!p.hold_account_only)));
                if pending {
                    if let Err(error)=profile13_dispatch::Dispatcher::terminal(s,&a.world,crate::battle091::profile13::FinishReason::ManualLeave) {
                        println!("SHARED_LEAVE_TERMINAL_FAILED session={} battle={} error={error} battle_contained=true",s.id,a.world.id);
                        leave_failures.push((home,error));continue;
                    }
                    if !a.blocked() && a.has_session(s.id) {a.world.detach(s.id)?;}
                }
            }
            for (home,error) in leave_failures.drain(..) {
                containment::contain_arena(&mut table,&mut battle_dispatch,&mut arenas[home],now,"leave_terminal",Some("fault_leave_terminal"),&error);
            }
            let mut index=0;
            while index<garage.len() {
                let GarageJob{job,account_id,account}=garage.remove(index);
                let id=job.session_id();let mut slot=Some(job);
                let outcome=ammo_session::complete(table.sessions.iter_mut().find(|s|s.id==id),&mut slot);
                if let Some(job)=slot {garage.insert(index,GarageJob{job,account_id,account});index+=1;}
                if let Err(error)=outcome {
                    println!("P08B_GARAGE_FAILED session={id} error={error} reconnect_required=true service_alive=true");
                    if table.sessions.iter().any(|s|s.id==id) {
                        let home=session_home(&table,&arenas,&battle_dispatch,id);let a=&mut arenas[home];
                        retire_service_failure(&mut room_host,&mut battle_dispatch,&mut table,&mut a.world,&mut a.integrated,
                            &a.template,&mut room_closing,id,"garage_writer_ambiguous",now,logical_ms)?;
                    }
                }
            }
            // Hold5 is refused with more than one arena (config); it owns arena 0.
            battle_dispatch.observe_hold_world(&table,&arenas[0].world)?;
            if let Some(error)=battle_dispatch.hold_pre_avatar_failure(&table,&arenas[0].world){
                containment::contain_arena(&mut table,&mut battle_dispatch,&mut arenas[0],now,"hold5_pre_avatar_departure",None,&error);
            }
            if let Some(m)=&mut matchmaker {
                m.tick(&mut table,&mut arenas,battle_dispatch.retired_sessions(),|battle|battle_dispatch.closed_queue(battle),now)?;
                // A dissolved group's battle id is not reused: the same reset as an emptied queue.
                for index in m.take_resets(&table,&arenas,battle_dispatch.retired_sessions()) {
                    let a=&mut arenas[index];
                    if let Some(late)=&mut battle_dispatch.late{late.before_reset(&a.world,"mm01_group_dissolved");}
                    // STAB-02: a failed reset closes only this arena.
                    let reset=battle_dispatch.before_hold_reset(&a.world).and_then(|()|a.template.replace(&mut a.world,&mut a.integrated,now));
                    match reset {
                        Ok(())=>a.cursors.reset(),
                        Err(error)=>containment::contain_arena(&mut table,&mut battle_dispatch,a,now,"mm01_group_reset",None,&error),
                    }
                }
            }
            if garage.is_empty() && !result_manager.busy() && !battle_dispatch.late_running() && (!config.p08b_owner_battle_hold||admission.is_empty()) {
                battle_dispatch.poll(&mut table,config.clone(),now)?;
                for a in arenas.iter_mut().filter(|a|a.closed.is_none()) {
                    match battle_dispatch.finish_empty_queue(&table,&mut a.world,&mut a.integrated,&a.template,now) {
                        Ok(true)=>a.cursors.reset(),Ok(false)=>{},
                        Err(error)=>containment::contain_arena(&mut table,&mut battle_dispatch,a,now,"queue_reset",None,&error),
                    }
                }
                let lobby=arena::lobby(&arenas,&table,battle_dispatch.retired_sessions());
                if matchmaker.is_none()&&battle_dispatch.closed_queue(arenas[lobby].world.id) {
                    for s in &mut table.sessions {
                        let pending=s.shared.as_ref().and_then(|c|c.profile13.as_ref()).is_some_and(|p|
                            p.selection.is_some() && !p.has_reservation() && !p.in_flight);
                        if pending {
                            let c=s.shared.as_mut().ok_or_else(||model::bad())?;
                            c.profile13.as_mut().ok_or_else(||model::bad())?.selection=None;c.join_requested=false;
                            s.outbox.push_back(crate::battle091::profile13::enqueue_failure("BATTLE_BUSY")?);
                        }
                    }
                }
                let a=&mut arenas[lobby];
                if a.closed.is_none() && a.world.started.is_none() && a.world.actors.iter().all(|x|x.session.is_none()) {
                    let kind=table.sessions.iter().find_map(|s|s.shared.as_ref().filter(|c|c.phase==Phase::Account && c.join_requested)
                        .and_then(|c|c.profile13.as_ref()).filter(|p|!p.in_flight && !p.has_pending_return())
                        .filter(|p|p.reservation_battle()==Some(a.world.id)).and_then(|p|p.reservation_kind()));
                    if let Some(kind)=kind.filter(|k|!a.world.mixed_profiles()&&*k!=a.world.vehicle_kind()) {
                        // STAB-02: a kind that cannot be seated fails its battle, not the service;
                        // the old template stays for the reset.
                        let switched=(||->io::Result<BattleTemplate>{
                            let r=resources.as_ref().and_then(|rows|rows.iter().find(|r|r.kind==kind)).ok_or_else(||model::bad())?;
                            let mut template=BattleTemplate::from_resources(r,a.world.id,now)?;
                            if config.visibility_v1 {
                                template.world.enable_original_spotting(super::spotting::Rules::selected()?)?;
                                template.world.enable_result_spots()?;
                            }
                            template.select(&mut a.world,&mut a.integrated,now)?;Ok(template)
                        })();
                        match switched {
                            Ok(template)=>{a.template=template;a.cursors.reset();},
                            Err(error)=>containment::contain_arena(&mut table,&mut battle_dispatch,a,now,"battle_select",None,&error),
                        }
                    }
                }
                for s in &mut table.sessions {
                    // A reservation is valid in the arena of its battle; one for no
                    // live arena (or of the wrong homogeneous kind) is returned.
                    let mismatch=s.shared.as_ref().filter(|c|c.phase==Phase::Account && c.join_requested)
                        .and_then(|c|c.profile13.as_ref()).filter(|p|!p.in_flight && !p.has_pending_return())
                        .is_some_and(|p|p.reservation_battle().is_some_and(|battle|match arenas.iter().find(|a|a.world.id==battle) {
                            None=>true,
                            Some(a)=>!a.world.mixed_profiles()&&p.reservation_kind().is_some_and(|kind|kind!=a.world.vehicle_kind()),
                        }));
                    if mismatch {
                        let a=&arenas[arena::home(s,&arenas,lobby)];
                        profile13_dispatch::Dispatcher::terminal(s,&a.world,crate::battle091::profile13::FinishReason::Cancelled)?;
                        if let Some(c)=&mut s.shared {c.queue_announced=false;}
                        s.outbox.push_back(crate::battle091::profile13::enqueue_failure("BATTLE_BUSY")?);
                        println!("P08B_HOMOGENEOUS_DENIAL session={} battle={} reservation_will_be_returned=true",s.id,a.world.id);
                    }
                }
                if room_host.as_ref().is_none_or(|h|!h.preparing()){
                    let lobby=arena::lobby(&arenas,&table,battle_dispatch.retired_sessions());
                    // MM-01: also every arena of an unstarted group (one writer at a time).
                    // STAB-02: a closed arena takes no admission.
                    for target in matchmaker.as_ref().map_or_else(||vec![lobby],|m|m.admission_arenas(&arenas,lobby)) {
                        if arenas[target].closed.is_some() {continue;}
                        battle_dispatch.attached_elsewhere=arena::attached_outside(&arenas,target);
                        let dispatched=battle_dispatch.start(&mut table,&arenas[target].world,config.clone(),now);
                        battle_dispatch.attached_elsewhere.clear();dispatched?;
                    }
                }
            }
            if !battle_dispatch.busy() && !result_manager.busy() && room_host.as_ref().is_none_or(|h|!h.busy()) && (!config.p08b_owner_battle_hold||admission.is_empty()){
                // One garage writer per account; a login of that account and
                // its retired writer stay mutually exclusive.
                for s in &mut table.sessions {
                    let owner=s.identity.as_ref().map(|p|p.account_id.clone());
                    if garage.len()>=garage_limit || owner.as_ref().is_some_and(|o|garage.iter().any(|g|&g.account_id==o))
                        || s.login_account.is_some_and(|t|admission.has_account(&t)) {continue;}
                    let mut slot=None;ammo_session::start(s,&mut slot,config.clone())?;
                    if let Some(job)=slot {garage.push(GarageJob{job,account_id:owner.ok_or_else(||model::bad())?,account:s.login_account});}
                }
            }
            // Results wait only for a login of an account that is already live
            // here (a same-attempt redirect resend); serial modes keep the old order.
            let results_login_clear=if serial_writers {admission.is_empty()} else {
                !admission.accounts().any(|t|table.sessions.iter().any(|s|s.login_account.as_ref()==Some(t)))};
            if !battle_dispatch.busy() && garage.is_empty() && results_login_clear && room_host.as_ref().is_none_or(|h|!h.busy()) {
                if let Err(error)=result_manager.start_if_idle(&mut table.sessions,config.clone(),now) {
                    contain_results_failure_in_arenas(&result_manager,&mut room_host,&mut battle_dispatch,&mut table,&mut arenas,
                        &mut room_closing,now,logical_ms,&error)?;
                }
            }
        }
        if let Some(host)=&mut room_host{
            // Training rooms are refused with more than one arena (config).
            let a=&mut arenas[0];
            let idle=!battle_dispatch.busy()&&garage.is_empty()&&!result_manager.busy()&&admission.is_empty();
            match host.poll(&mut table,&mut a.world,&mut a.integrated,&a.template,&mut battle_dispatch,config.clone(),now,logical_ms,idle){
                Ok(true)=>{a.cursors.reset();},Ok(false)=>{},
                Err(error)=>println!("P10B_HOST_RETRY error={error} authority_retained=true service_alive=true"),
            }
            if let Some(error)=host.prestart_failure(&a.world,None,now){
                containment::contain_arena(&mut table,&mut battle_dispatch,a,now,"training_handoff",Some("training_handoff_failure"),&error);
            }
        }
        if let Some(late)=&mut battle_dispatch.late{
            late.observe_sessions(table.sessions.iter());
            for a in &mut arenas {
                if a.world.started.is_some()&&a.world.actors.iter().all(|x|x.session.is_none())&&!a.blocked(){
                    if let Err(error)=a.world.advance_lifecycle(now){late.invalidate_source(&config.battle_run_id,a.world.id);
                        println!("P08C_LATE_FINAL_OUTCOME_UNSUPPORTED battle={} error={error}",a.world.id);}
                }
                late.seal_world(&a.world);
            }
        }
        for a in &mut arenas {
            if a.world.owner_hold_enabled()&&a.world.started.is_some()&&a.world.actors.iter().all(|x|x.session.is_none())&&!a.blocked(){
                if let Err(error)=a.world.advance_lifecycle(now) {
                    containment::contain_arena(&mut table,&mut battle_dispatch,a,now,"lifecycle",Some("fault_lifecycle"),&error);continue;
                }
                battle_dispatch.observe_hold_world(&table,&a.world)?;
            }
        }
        for a in &mut arenas {
            if a.closed.is_none() && parked_battle_reset_ready(&table,&a.world) {
                if let Some(late)=&mut battle_dispatch.late{late.before_reset(&a.world,"normal_all_parked_reset");}
                match battle_dispatch.before_hold_reset(&a.world).and_then(|()|a.template.replace(&mut a.world,&mut a.integrated,now)) {
                    Ok(())=>a.cursors.reset(),
                    Err(error)=>containment::contain_arena(&mut table,&mut battle_dispatch,a,now,"battle_reset",None,&error),
                }
            }
        }
        for s in &mut table.sessions {
            if s.ready_for_arena_base() {
                let c = s.shared.as_mut().ok_or_else(|| model::bad())?;
                if c.hangar_since.is_none() { c.hangar_since = Some(now); }
            }
        }
        // Membership and the start barrier stay on this thread; the simulation
        // step of each arena crosses the typed boundary (threads when K > 1).
        let mut commands=Vec::with_capacity(arenas.len());
        let mut failures:Vec<(usize,&'static str,io::Error)>=Vec::new();
        for index in 0..arenas.len() {
            let a=&mut arenas[index];
            containment::reopen_closed(a,now);
            if a.closed.is_some() {commands.push(None);continue;}
            let pre=(||->io::Result<bool> {
                if a.world.owner_hold_enabled(){battle_dispatch.attach_hold_ready_group(&mut table,&mut a.world,&config.battle_run_id,now)?;}
                else{attach_waiting_sessions(&mut table,&mut a.world,now)?;}
                if let Some(late)=&mut battle_dispatch.late{
                    if let Err(error)=if config.p08b_owner_battle_hold{Ok(())}else{late.register_world(&table.sessions,&a.world,&config.battle_run_id)}{
                        late.invalidate_source(&config.battle_run_id,a.world.id);
                        println!("P08C_LATE_ADMISSION_UNSUPPORTED battle={} error={error} normal_owned_battle_unchanged=true",a.world.id);
                    }
                }
                Ok(if let Some(host)=&room_host{host.can_start(&table,&a.world,now)?}
                else if table.arena_split{
                    let start=a.world.started.is_none()&&table.arena_ready(&a.world,now);
                    if start {a.world.fill_bots()?;}
                    start
                }else{
                    a.world.started.is_none() && table.sessions.len()==a.world.expected_actors()
                        && a.world.actors.len()==a.world.expected_actors() && table.sessions.iter().all(|s|entry_ready(s,now)
                            && a.world.actors.iter().any(|x|x.session==Some(s.id)))
                })
            })();
            match pre {
                Ok(start)=>commands.push(Some(arena::Command::Step{now,start})),
                Err(error)=>{commands.push(None);failures.push((index,"world_step",error));},
            }
        }
        let step_started=Instant::now();
        for (index,event) in arena::step_all(&mut arenas,&commands).into_iter().enumerate() {
            if let Some(arena::Event::Failed{stage,error})=event {failures.push((index,stage,error));}
        }
        let step_wall=step_started.elapsed();
        failures.sort_by_key(|f|f.0);
        for (index,stage,error) in failures {
            let late=if stage=="world_step"{"fault_world_step"}else{"fault_world_step_panic"};
            containment::contain_arena(&mut table,&mut battle_dispatch,&mut arenas[index],now,stage,Some(late),&error);
        }
        if let Some(late)=&mut battle_dispatch.late{late.observe_sessions(table.sessions.iter());for a in &arenas{late.seal_world(&a.world);}}
        for a in &mut arenas {
            battle_dispatch.observe_hold_world(&table,&a.world)?;
            let sealed=battle_dispatch.hold_results(a.world.id).or_else(||battle_dispatch.late.as_ref().and_then(|m|m.sealed_results(a.world.id)));
            if let Err(error)=stage_lifecycle_results_from(&mut table,&a.world,sealed) {
                containment::contain_arena(&mut table,&mut battle_dispatch,a,now,"result_snapshot",Some("fault_result_snapshot"),&error);
            }
        }
        let lobby=arena::lobby(&arenas,&table,battle_dispatch.retired_sessions());
        let publish_started=Instant::now();
        let mut publication_failures:Vec<(usize,io::Error)>=Vec::new();
        for s in &mut table.sessions {
            if !s.active&&room_host.as_ref().is_some_and(|h|h.owns_preparing(s.id)){continue;}
            let home=arena::home(s,&arenas,lobby);
            // A failed arena publishes nothing more this tick; others continue.
            if publication_failures.iter().any(|(failed,_)|*failed==home){continue;}
            let reason = if now.duration_since(s.created_at) >= config.session_duration { Some("session_deadline") }
                else if now.duration_since(s.last_rx) >= s.tx.idle_limit() { Some("idle_timeout") } else { None };
            if let Some(reason) = reason { closing.push((s.id, reason)); continue; }
            // Keep the transport alive while workers settle, but gate the
            // native arena reset until both workers have supplied a settled
            // pose. This avoids the old outer `continue`, which also skipped
            // heartbeats and made a client look disconnected during startup.
            let a=&mut arenas[home];
            let (native_ready,blocked)=(a.native_ready(),a.blocked());
            if let Err(error) = poll_battle_session(s,&mut a.world,now,native_ready,blocked) {
                // A revoked old Avatar cannot fail the replacement battle.
                // Retire only its authenticated session; its immutable writer
                // task/durable result remains in the ordinary retired lane.
                if let Some(reason)=contained_return_failure_reason(s){
                    println!("SHARED_CONTAINED_RETURN_FAILED session={} reason={} durable_result_retained=true replacement_world_unchanged=true",s.id,error);
                    closing.push((s.id,reason));continue;
                }
                if error.kind()==io::ErrorKind::TimedOut&&a.world.ammo_detonation_enabled()
                    &&s.shared.as_ref().is_some_and(|c|c.result_committed&&!c.result_stream_queued){
                    println!("P06T_TURRET_PRESENTATION_TIMEOUT session={} durable_result_retained=true",s.id);
                    closing.push((s.id,"native_turret_unconfirmed"));continue;
                }
                if s.shared.as_ref().is_some_and(|c|c.result_committed && c.result_delivery_at
                    .is_some_and(|at|now.duration_since(at)>=Duration::from_secs(30))) {
                    println!("P08C_RESULTS_CONFIRM_TIMEOUT session={} durable_result_retained=true",s.id);
                    closing.push((s.id,"native_results_unconfirmed"));continue;
                }
                println!("SHARED_FAILED session={} reason={}", s.id, error);
                publication_failures.push((home,error));
                if arenas.len()==1 {break;} else {continue;}
            }
            if !s.active { continue; }
            if s.tx.len() == 0 && now.duration_since(s.last_heartbeat) >= Duration::from_secs(2) {
                if s.tx.enqueue().is_err() { closing.push((s.id, "sequence_budget")); continue; } s.last_heartbeat = now;
            }
            if let Some(peer) = s.base_peer {
                let Some(frames) = transmit(s, now)? else { closing.push((s.id, "retry_exhausted")); continue; };
                for clear in frames { send(&base_socket, peer, &clear, &s.key, &mut capture)?; }
                if now.duration_since(s.last_keepalive) >= Duration::from_secs(1) {
                    send(&base_socket, peer, &transport091::ack(s.rx), &s.key, &mut capture)?; s.last_keepalive = now;
                }
            }
        }
        let publish_wall=publish_started.elapsed();
        for (home,error) in publication_failures {
            containment::contain_arena(&mut table,&mut battle_dispatch,&mut arenas[home],now,"publication",Some("fault_publication"),&error);
        }
        for(id,reason)in closing{
            if !table.sessions.iter().any(|s|s.id==id){continue;}
            let home=session_home(&table,&arenas,&battle_dispatch,id);let a=&mut arenas[home];
            if containment::retire_contained_or_drop(&mut table,&mut battle_dispatch,&mut a.world,id,now,reason){continue;}
            if room_host.is_none(){containment::retire_or_contain(&mut table,&mut battle_dispatch,a,id,now,reason);continue;}
            match retire_training_session(&mut room_host,&mut battle_dispatch,&mut table,&mut a.world,&mut a.integrated,&a.template,id,reason,now,logical_ms){
                Ok(true)=>{},Ok(false)=>hold_training_close(&mut room_closing,id,reason),
                Err(error)=>{println!("P10B_CLOSE_RETRY session={id} error={error} service_alive=true");hold_training_close(&mut room_closing,id,reason);}
            }
        }
        let late_idle=!battle_dispatch.busy()&&garage.is_empty()&&admission.is_empty()&&!result_manager.busy();
        if let Some(late)=&mut battle_dispatch.late{
            let utc=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).ok().and_then(|d|u32::try_from(d.as_secs()).ok()).unwrap_or(0);
            late.poll(&mut table.sessions,config.clone(),now,late_idle,utc);
        }
        for a in &mut arenas {
            let world=&a.world;
            for contact in world.contacts.iter().skip(a.cursors.contact) {
                println!("SHARED_GEOMETRIC_CONTACT {}", serde_json::json!({
                    "battle":world.id.to_string(), "shot":contact.shot, "target_slot":contact.target_slot,
                    "tick":contact.tick, "segment_start":contact.segment_start, "segment_end":contact.segment_end,
                    "segment_seconds":contact.segment_seconds, "endpoint":contact.endpoint,
                    "target_position":contact.target_position, "target_direction":contact.target_direction,
                    "target_aim":contact.target_aim, "triangle_id":contact.triangle.triangle_id,
                    "mesh":contact.triangle.mesh, "group":contact.triangle.group, "material":contact.triangle.material,
                    "t":contact.triangle.t, "normal":contact.triangle.normal,
                    "geometry_revision":contact.geometry_revision, "transform_revision":contact.transform_revision,
                    "material_facts":contact.material_facts.json(),
                    "terminal":match world.impacts.iter().find(|event| event.shot==contact.shot).map(|e| &e.outcome) {
                        Some(model::ImpactOutcome::Ap(_)) => "test_lab_impact",
                        Some(model::ImpactOutcome::Mixed(_)) => "test_lab_mixed_impact",
                        Some(model::ImpactOutcome::WreckBlocked) => "test_lab_wreck_impact",
                        None => "unresolved_collision"},
                    "damage_applied":world.impacts.iter().any(|event| event.shot==contact.shot && event.health_after<event.health_before)}));
            }
            a.cursors.contact = world.contacts.len();
            for contact in world.terrain_contacts.iter().skip(a.cursors.terrain) {
                let (surface,instance_id,material_kind)=match contact.hit.surface {
                    super::terrain::Surface::Ground => ("terrain",None,None),
                    super::terrain::Surface::StaticObstacle{instance_id,material_kind} =>
                        ("static_obstacle",Some(instance_id),Some(material_kind)),
                };
                println!("SHARED_TERRAIN_CONTACT {}",serde_json::json!({
                    "battle":world.id.to_string(),"shot":contact.shot,"shooter":contact.shooter,"tick":contact.tick,
                    "triangle_id":contact.hit.triangle_id,"t":contact.hit.t,"endpoint":contact.hit.point,
                    "normal":contact.hit.normal,"direction":contact.direction,
                    "segment_start":contact.segment_start,"segment_end":contact.segment_end,
                    "map":world.map.asset(),"geometry_revision":world.map.spec().world_revision,
                    "geometry_revision_scope":"terrain_and_projectile_obstacles",
                    "surface":surface,"instance_id":instance_id,"material_kind":material_kind,
                    "effect_material_index":contact.hit.effect_material_index(),"material_policy":contact.hit.material_policy(),
                    "damage_applied":false}));
            }
            a.cursors.terrain=world.terrain_contacts.len();
            for event in world.impacts.iter().skip(a.cursors.impact) {
                if let model::ImpactOutcome::WreckBlocked = event.outcome {
                    println!("SHARED_WRECK_IMPACT {}", serde_json::json!({
                        "battle":world.id.to_string(),"shot":event.shot,"attacker":event.attacker,"target":event.target,"tick":event.tick,
                        "policy_revision":model::wreck_policy_revision_for(world.vehicle_kind()),"historical_fidelity":"approximate",
                        "outcome":"wreck_blocked","health_before":event.health_before,"health_after":event.health_after,
                        "damage":0,"native_effect_available":event.segment.is_some()}));
                    continue;
                }
                if let model::ImpactOutcome::Mixed(resolution)=&event.outcome{
                    println!("P06T_DIRECT_IMPACT battle={} shot={} attacker={} target={} tick={} resolution={resolution:?} hp_before={} hp_after={} historical_fidelity=explicit_lab",
                        world.id,event.shot,event.attacker,event.target,event.tick,event.health_before,event.health_after);
                    continue;
                }
                let model::ImpactOutcome::Ap(resolution) = &event.outcome else { return Err(model::bad().into()); };
                println!("SHARED_AP_IMPACT {}", serde_json::json!({
                    "battle":world.id.to_string(),"shot":event.shot,"attacker":event.attacker,"target":event.target,"tick":event.tick,
                    "profile_revision":resolution.profile_revision,"historical_fidelity":ap::HISTORICAL_FIDELITY,
                    "outcome":resolution.outcome.label(),"reason":format!("{:?}",resolution.outcome),
                    "armor":resolution.armor,"incidence_degrees":resolution.incidence_degrees,
                    "normalization_degrees":resolution.normalization_degrees,
                    "effective_armor":resolution.effective_armor,"nominal_power":resolution.nominal_power,
                    "health_before":event.health_before,"health_after":event.health_after,
                    "damage":event.health_before-event.health_after,"native_effect_available":event.segment.is_some()}));
            }
            a.cursors.impact = world.impacts.len();
            if let Some(state)=&world.fragiles{
                for damage in state.events.iter().skip(a.cursors.fragile){println!("SHARED_FRAGILE_DAMAGE {}",serde_json::json!({
                    "battle":world.id.to_string(),"catalog_sha256":state.catalog.sha256,"policy":super::fragiles::policy_for(world.vehicle_kind()),
                    "object_id":damage.object_id,"instance_id":damage.instance_id,"object_revision":damage.object_revision,
                    "shot":damage.shot,"shooter":damage.shooter,"tick":damage.tick,"health_before":damage.health_before,"health_after":damage.health_after,
                    "scene_before":damage.scene_before,"scene_after":damage.scene_after}));}
                a.cursors.fragile=state.events.len();
            }
        }
        // Both peers receive a snapshot of the same completed server tick.
        for s in &mut table.sessions { if let Some(c) = &mut s.shared {
            if c.phase!=Phase::Returning {
                if let Some(a)=arenas.iter().find(|a|a.world.actors.get(c.slot).is_some_and(|x|x.session==Some(s.id))) {
                    c.view = Some(a.world.clone());
                }
            }
        } }
        // NET-01: wall time of this loop and of each running arena's domain tick.
        let ticks=arenas.iter().map(|a|a.world.started.map(|_|a.world.tick)).collect::<Vec<_>>();
        let loop_end=Instant::now();
        net_stats.record(now,step_wall,publish_wall,&ticks,loop_end);
        if let Some(line)=net_stats.take_report(loop_end) {
            println!("{line}");
            for s in &mut table.sessions {
                // Every window restarts, so a battle report never carries hangar traffic.
                let w=std::mem::take(&mut s.tx.stats);
                let Some(c)=s.shared.as_mut() else {continue;};
                let pose=c.take_pose_stats();
                if !c.in_battle() {continue;}
                println!("NET01_SESSION_STATS session={} mode={} pending_now={} pending_max={} outbox_max={} resends={} ack_wait_ms=[{}] queue_wait_ms=[{}] poses={} pose_gap_max_ticks={} pose_gaps_over_1={} pose_replaced_unsent={} pose_packets={} pose_bytes={}",
                    s.id,c.pose_delivery().label(),s.tx.len(),w.pending_max,pose.outbox_max,w.resends,w.ack_wait.summary(),w.queue_wait.summary(),
                    pose.published,pose.gap_max,pose.gaps_over_one,pose.replaced_unsent,pose.packets,pose.bytes);
            }
        }
        thread::sleep(Duration::from_millis(5));
    }
    Ok(())
}

fn poll_with_native_start(s: &mut Session, world: &mut World, now: Instant,
    allow_native_start: bool) -> io::Result<()> {
    if world.started.is_none() { return Ok(()); }
    if allow_native_start && entry_ready(s, now) { s.shared_start(world, now)?; }
    let c = s.shared.as_ref().ok_or_else(|| model::bad())?;
    let full_ready = c.phase == Phase::Driving && c.correction
        && c.binding.is_some_and(|(_,ack)|ack)
        && c.areas_ready(world);
    if matches!(c.phase,Phase::Enable|Phase::Entities|Phase::Driving) && !full_ready
        && c.entered.is_some_and(|start| now.duration_since(start) > Duration::from_secs(90)) { return Err(model::bad()); }
    if !matches!(c.phase, Phase::Driving | Phase::Leaving) { return Ok(()); }
    let slot = c.slot;
    let mut next = s.clone(); let mut next_world = world.clone();
    let area_ready = c.areas_ready(world);
    if !area_ready { return Ok(()); }
    if c.correction { next_world.set_ready(slot, s.id)?; }
    let commands = std::mem::take(&mut next.shared.as_mut().ok_or_else(|| model::bad())?.commands);
    if !c.correction && !commands.is_empty() {
        // Keep a bounded startup intent until ACK6; no pre-correction motion.
        if commands.iter().any(|cmd| !matches!(cmd, model::Command::Aim(_) | model::Command::Move(model::Input::STOP))) { return Err(model::bad()); }
        next.shared.as_mut().ok_or_else(|| model::bad())?.commands = commands;
        *s = next; return Ok(());
    }
    if !c.correction { return Ok(()); }
    let outcomes = next_world.apply(slot, s.id, &commands, now)?;
    if next_world.mixed_ammo()&&outcomes.iter().any(|outcome|matches!(outcome,
        crate::battle091::fire::Outcome::Typed(crate::p06t_armament091::Outcome::Refused(_))
        |crate::battle091::fire::Outcome::RejectedBattlePeriod|crate::battle091::fire::Outcome::RejectedVehicleState)){
        next.shared.as_mut().ok_or_else(||model::bad())?.armament_sent=None;
    }
    for outcome in &outcomes {
        if let crate::battle091::fire::Outcome::AcceptedShot { ammo_remaining } = outcome {
            let mut b = wire::ammo_count_for(next_world.actors[slot].vehicle_kind(),*ammo_remaining)?; b.extend(wire::reload_for(next_world.actors[slot].vehicle_kind(),slot,next_world.actors[slot].vehicle_kind().reload_seconds())?);
            next.outbox.push_back(b);
        }
    }
    if next_world.actors[slot].fire.finish_reload_if_due(now)&&!next_world.mixed_ammo() { next.outbox.push_back(wire::reload_for(next_world.actors[slot].vehicle_kind(),slot,0.)?); }
    next.shared_refresh_world(&next_world)?;
    next.flush_shared_interest(&mut Vec::new())?;
    sixth_sense_wire::publish(&mut next,&next_world)?;
    let c = next.shared.as_mut().ok_or_else(|| model::bad())?;
    let mut shot_publications = Vec::new();
    let mut tracer_starts = Vec::new();
    let mut tracer_stops = Vec::new();
    let mut anonymous_tracers = Vec::new();
    let mut impact_from = usize::MAX;
    let mut impact_publications = Vec::new();
    let prior_projectile_count = world.projectiles.len();
    if c.phase == Phase::Driving {
        if let Some(state)=&next_world.fragiles{
            let chunks=state.catalog.chunks();
            if c.tree_areas.len()!=chunks.len(){c.tree_areas=vec![Vec::new();chunks.len()];}
            if c.column_areas.len()!=chunks.len(){c.column_areas=vec![Vec::new();chunks.len()];}
            for (i,chunk) in chunks.into_iter().enumerate(){
                let indices=state.native_destroyed(chunk);
                let values=state.native_fragile_values(chunk);
                let trees=state.native_fallen_trees(chunk);
                if c.areas[i].1!=indices{
                    if !area_ready||!c.areas[i].1.iter().all(|id|indices.contains(id)){return Err(model::bad());}
                    next.outbox.push_back(super::destructible_wire::area_update_fragiles(i,&values)?);c.areas[i].1=indices.clone();
                    println!("SHARED_CATALOG_PUBLICATION battle={} session={} chunk={} entity={} indices={:?} scene_version={}",next_world.id,s.id,chunk,super::destructible_wire::area_id(i)?,indices,next_world.scene_version());
                }
                if c.tree_areas[i]!=trees {
                    if !area_ready||!c.tree_areas[i].iter().all(|id|trees.contains(id)){return Err(model::bad());}
                    next.outbox.push_back(super::destructible_wire::area_update_trees(i,&trees)?);c.tree_areas[i]=trees.clone();
                    println!("SHARED_TREE_PUBLICATION battle={} session={} chunk={} entity={} fallen_trees={:?} scene_version={}",next_world.id,s.id,chunk,super::destructible_wire::area_id(i)?,trees,next_world.scene_version());
                }
                let columns=state.native_fallen_columns(chunk);
                if c.column_areas[i]!=columns {
                    if !area_ready||!c.column_areas[i].iter().all(|v|columns.contains(v)){return Err(model::bad());}
                    next.outbox.push_back(super::destructible_wire::area_update_columns(i,&columns)?);c.column_areas[i]=columns.clone();
                    println!("SHARED_COLUMN_PUBLICATION battle={} session={} chunk={} entity={} fallen_columns={:?} scene_version={}",next_world.id,s.id,chunk,super::destructible_wire::area_id(i)?,columns,next_world.scene_version());
                }
            }
        }
        if next_world.destructible_enabled() && c.area_scene_sent != next_world.scene_version() {
            if c.area_scene_sent != 0 || next_world.scene_version() != 1 || !area_ready { return Err(model::bad()); }
            next.outbox.push_back(super::destructible_wire::update(super::destructible_wire::NATIVE_INDEX));
            c.area_scene_sent = 1;
            println!("SHARED_DESTRUCTIBLE_PUBLICATION battle={} session={} entity={} native_index={} scene_version=1 queued=true",
                next_world.id,s.id,super::destructible_wire::ENTITY_ID,super::destructible_wire::NATIVE_INDEX);
        }
        for shot in next_world.shots.iter().filter(|shot| shot.sequence > c.shot_cursor).copied().collect::<Vec<_>>() {
            let observable = c.correction && c.binding.is_some_and(|(_, ack)| ack) && c.visible()[shot.slot];
            if observable {
                let index = shot.sequence.checked_sub(1).ok_or_else(|| model::bad())? as usize;
                let projectile = next_world.projectiles.iter().find(|p| p.sequence == shot.sequence)
                    .ok_or_else(|| model::bad())?;
                if !c.tracer_started[index] {
                    // Keep the existing native muzzle/sound cue and then send
                    // the original fixed showTracer callback in one reliable
                    // order. The start flag is committed with this clone.
                    c.queue_private(&mut next.outbox,wire::shooting(shot.slot)?,&[shot.slot])?;
                    c.queue_private(&mut next.outbox,wire::tracer_start(projectile)?,&[shot.slot])?;
                    c.tracer_started[index] = true;
                    tracer_starts.push((shot.sequence, shot.slot));
                }
            } else if c.spotting_enabled && c.correction && c.binding.is_some_and(|(_, ack)| ack) && shot.slot != c.slot {
                // AV-01: #717 showTracer draws a tracer without a shooter
                // entity. Anonymous form: shooter 0, start advanced along the
                // flight; no muzzle cue (Vehicle.showShooting needs the entity).
                let index = shot.sequence.checked_sub(1).ok_or_else(|| model::bad())? as usize;
                let projectile = next_world.projectiles.iter().find(|p| p.sequence == shot.sequence)
                    .ok_or_else(|| model::bad())?;
                if !c.tracer_started[index] {
                    if let Some(body) = super::av01_feedback::anonymous_tracer(projectile, projectile_effects(projectile)?)? {
                        next.outbox.push_back(body);
                        c.tracer_started[index] = true;
                        anonymous_tracers.push((shot.sequence, shot.slot));
                    }
                }
            }
            // Even a skipped event is consumed: becoming visible later must
            // not replay stale gunfire. The cursor commits with the queue.
            c.shot_cursor = shot.sequence;
            shot_publications.push((shot, observable));
        }
        // Expiry is server-owned. A peer receives a stop only if this exact
        // connection received/queued the corresponding start, so reconnects
        // cannot inherit old effects or produce orphan stops.
        if c.correction && c.binding.is_some_and(|(_, ack)| ack) {
            for projectile in next_world.projectiles.iter().filter(|p| p.stopped) {
                let index = projectile.sequence.checked_sub(1).ok_or_else(|| model::bad())? as usize;
                if index >= c.tracer_started.len() { return Err(model::bad()); }
                if c.tracer_started[index] && !c.tracer_stopped[index] {
                    let target=next_world.impacts.iter().find(|e|e.shot==projectile.sequence).map(|e|e.target);
                    // A vehicle collision can reveal a hidden target even while
                    // its shooter remains visible. Native range flight is bounded;
                    // suppress the private terminal rather than invent a hit point.
                    // AV-01: a hidden shooter no longer suppresses the end of
                    // its (anonymous) tracer; stop bodies carry no shooter ID.
                    if c.spotting_enabled && target.is_some_and(|slot|!c.visible()[slot]) {
                        c.tracer_stopped[index]=true;continue;
                    }
                    let mut targets=Vec::new();
                    if !c.spotting_enabled || c.visible()[projectile.slot] {targets.push(projectile.slot);}
                    if let Some(slot)=target {targets.push(slot);}
                    if let Some(contact)=next_world.terrain_contacts.iter().find(|c|c.shot==projectile.sequence) {
                        // Original explodeProjectile terminates its own mover.
                        // A subsequent stopTracer would hide/cancel ground FX.
                        let effect=if let Some(shell)=projectile.shell{super::terrain_wire::explode_material_shell_for_limit(shell,projectile.sequence,
                            contact.hit.point,contact.direction,contact.hit.effect_material_index(),next_world.shot_limit())?}
                            else{super::terrain_wire::explode_material_for_limit(projectile.vehicle_kind,projectile.sequence,
                            contact.hit.point,contact.direction,contact.hit.effect_material_index(),next_world.shot_limit())?};
                        if targets.is_empty() {next.outbox.push_back(effect);} else {c.queue_private(&mut next.outbox,effect,&targets)?;}
                    } else {
                        let stop=wire::tracer_stop(projectile)?;
                        if targets.is_empty() {next.outbox.push_back(stop);} else {c.queue_private(&mut next.outbox,stop,&targets)?;}
                    }
                    c.tracer_stopped[index] = true;
                    tracer_stops.push((projectile.sequence, projectile.slot));
                }
            }
            impact_from = c.impact_cursor;
            for event in next_world.impacts.iter().skip(c.impact_cursor) {
                let shot_index = event.shot.checked_sub(1).ok_or_else(|| model::bad())? as usize;
                let visible = c.visible()[event.target] && c.visible()[event.attacker];
                let observed_shot = c.tracer_started.get(shot_index).copied().ok_or_else(|| model::bad())?;
                let mut body = Vec::new();
                if visible && observed_shot {
                    let projectile=next_world.projectiles.iter().find(|projectile|projectile.sequence==event.shot).ok_or_else(||model::bad())?;
                    let he=projectile.shell.filter(|shell|shell.family==crate::p06t_shells091::Family::HighExplosive);
                    // A verified collision can stop HE on a non-ordinary surface
                    // without authorizing fabricated penetration or hull damage.
                    if let Some(shell)=he{body.extend(crate::armament_wire091::explosion(wire::vehicle_id(event.target)?,
                        wire::vehicle_id(event.attacker)?,projectile.terminal,shell)?);}
                    if let Some((segment,outcome,component)) = impact_visual(event)? {
                        if let Some(shell)=projectile.shell{
                            if he.is_none(){body.extend(impact_wire::show_damage_shell(shell,event.attacker,event.target,component,segment.bounds,segment.start,segment.end,outcome)?);}
                        }else{body.extend(impact_wire::show_damage_for(next_world.actors[event.attacker].vehicle_kind(),event.attacker,event.target,component,
                            segment.bounds,segment.start,segment.end,outcome)?);}
                    }
                    if !next_world.mixed_ammo()&&event.health_after < event.health_before
                        && c.health_sent[event.target].is_none_or(|hp| hp > event.health_after) {
                        body.extend(impact_wire::health_changed_for(next_world.actors[event.target].vehicle_kind(),event.target,event.health_after,event.attacker)?);
                        c.health_sent[event.target] = Some(event.health_after);
                        if event.target == c.slot {
                            body.extend(impact_wire::owner_health_for(next_world.actors[event.target].vehicle_kind(),event.health_after)?);
                            c.owner_health_sent = Some(event.health_after);
                        }
                        if event.health_after == 0 {
                            if !c.spotting_enabled {body.extend(wire::roster_updates(&next_world,event.target)?);}
                            if next_world.lifecycle.is_some() && !c.spotting_enabled {
                                body.extend(super::lifecycle_wire::vehicle_killed(wire::vehicle_id(event.target)?,wire::vehicle_id(event.attacker)?,0)?);
                            }
                        }
                    }
                } else if c.spotting_enabled && event.target == c.slot && c.visible()[c.slot] {
                    // AV-01: an own-vehicle hit from a hidden shooter keeps the
                    // native hit FX/sound with attacker 0; no shooter data.
                    let projectile=next_world.projectiles.iter().find(|projectile|projectile.sequence==event.shot).ok_or_else(||model::bad())?;
                    let he=projectile.shell.filter(|shell|shell.family==crate::p06t_shells091::Family::HighExplosive);
                    let mut own=Vec::new();
                    if let Some(shell)=he{own.extend(crate::armament_wire091::explosion(wire::vehicle_id(event.target)?,0,projectile.terminal,shell)?);}
                    else if let Some((segment,outcome,component)) = impact_visual(event)? {
                        own.extend(impact_wire::show_damage_from(projectile_effects(projectile)?,0,event.target,component,
                            segment.bounds,segment.start,segment.end,outcome)?);
                    }
                    if !own.is_empty() {c.queue_private(&mut next.outbox,own,&[event.target])?;}
                }
                // AV-01: the owner's hit indicator (any shooter visibility; the
                // yaw comes from the shell flight) and the shooter's result
                // voice (vehicle ID and flags only, also for blind fire).
                if c.spotting_enabled && event.health_before > 0 && (event.target == c.slot || event.attacker == c.slot) {
                    let projectile=next_world.projectiles.iter().find(|projectile|projectile.sequence==event.shot).ok_or_else(||model::bad())?;
                    if event.target == c.slot && c.visible()[c.slot] {
                        next.outbox.push_back(super::av01_feedback::hit_direction(projectile.velocity,event.health_after<event.health_before)?);
                    }
                    if event.attacker == c.slot {
                        let he=projectile.shell.is_some_and(|shell|shell.family==crate::p06t_shells091::Family::HighExplosive);
                        // No native visual category (e.g. a LAB decision the FX
                        // path refuses) falls back to the HP change alone.
                        let outcome=impact_visual(event).ok().flatten().map(|(_,outcome,_)|outcome);
                        let flags=super::av01_feedback::shot_result_flags(outcome,he,event.health_before,event.health_after);
                        next.outbox.push_back(super::av01_feedback::shot_results(&[(event.target,flags)])?);
                    }
                }
                let queued = !body.is_empty();
                if queued { c.queue_private(&mut next.outbox,body,&[event.attacker,event.target])?; }
                // Arena kill/alive metadata is public. A hidden attacker must
                // still produce the original kill event without private HP,
                // shot geometry, entity creation or shooter coordinates.
                if !next_world.mixed_ammo()&&c.spotting_enabled && event.health_before>0 && event.health_after==0 && next_world.lifecycle.is_some() {
                    let mut public=wire::roster_updates(&next_world,event.target)?;
                    public.extend(super::lifecycle_wire::vehicle_killed(wire::vehicle_id(event.target)?,wire::vehicle_id(event.attacker)?,0)?);
                    next.outbox.push_back(public);
                }
                impact_publications.push((event.shot,event.target,event.health_after,queued));
                c.impact_cursor += 1;
            }
            // Late creation/reconnect gets current HP, never old effects or
            // an intermediate health value that would resurrect the actor.
            if next_world.mixed_ammo(){p06t_publication::publish(c,&mut next.outbox,&next_world,now)?;}else{for target in 0..next_world.actors.len() {
                if !c.visible()[target] { continue; }
                let hp = next_world.actors[target].health;
                let mut body = Vec::new();
                if c.health_sent[target] != Some(hp) {
                    if hp != next_world.actors[target].vehicle_kind().max_health() {
                        let attacker = next_world.impacts.iter().rev().find(|e| e.target == target)
                            .map(|e| e.attacker).ok_or_else(|| model::bad())?;
                        body.extend(impact_wire::health_changed_for(next_world.actors[target].vehicle_kind(),target,hp,attacker)?);
                        if hp == 0 { body.extend(wire::roster_updates(&next_world,target)?); }
                    }
                    c.health_sent[target] = Some(hp);
                }
                if target == c.slot && hp != next_world.actors[target].vehicle_kind().max_health() && c.owner_health_sent != Some(hp) {
                    body.extend(impact_wire::owner_health_for(next_world.actors[target].vehicle_kind(),hp)?); c.owner_health_sent = Some(hp);
                }
                if !body.is_empty() { c.queue_private(&mut next.outbox,body,&[target])?; }
            }}
        }
        // AV-01 runs with recipient visibility (visibility_v1, as on the owner
        // stands); legacy all-visible laboratory publications stay byte-exact.
        if c.spotting_enabled && c.correction && c.binding.is_some_and(|(_, ack)| ack) {
            publish_av01(c,&mut next.outbox,&next_world,impact_from)?;
        }
        if let Some(state) = &next_world.lifecycle {
            let view = state.view();
            // Native AFTERBATTLE clears the base panel. Final capture/death
            // publications therefore precede that period transition.
            for i in 0..2 {
                if c.lifecycle_view.as_ref().is_none_or(|old| old.bases[i] != view.bases[i]) {
                    let base = view.bases[i];
                    next.outbox.push_back(super::lifecycle_wire::base_points(base.owner,1,base.points,base.stopped)?);
                    if base.points == 100 {next.outbox.push_back(super::lifecycle_wire::base_captured(base.owner,1)?);}
                }
            }
            if c.lifecycle_view.as_ref().is_none_or(|old|old.phase!=view.phase || old.ends_ms!=view.ends_ms) {
                next.outbox.push_back(wire::lifecycle_period(&next_world)?);
            }
            c.lifecycle_view=Some(view);
        }
        for other in 0..next_world.actors.len() {
            if next_world.actors[other].ready && !c.ready_sent[other] && (!c.spotting_enabled || c.visible()[other]) {
                next.outbox.push_back(wire::ready_update(other)?); c.ready_sent[other] = true;
            }
        }
        // No queue of stale poses for a slow peer. Reliable retries retain their
        // exact bytes; the next fresh pose is queued when capacity is available.
        let old_tick = if c.spotting_enabled {c.last_pose_tick.unwrap_or(0)} else {c.view.as_ref().map(|w| w.tick).unwrap_or(0)};
        let latest = c.pose_delivery == super::net01::PoseDelivery::LatestUnreliable;
        let paced = c.pose_delivery == super::net01::PoseDelivery::ReliableBurstV2;
        // NET-01: a held-aside pose never waits for window capacity here.
        if c.correction && c.binding.is_some_and(|(_, ack)| ack) && old_tick != next_world.tick && (latest || paced || next.tx.len() < 4) {
            let mut parts = wire::publication_parts(&next_world, c.visible())?;
            if paced {
                // One tickSync per tick: later parts drop their 2-byte prefix.
                for part in parts.iter_mut().skip(1) {if part.len()<=2 || part[0]!=0x0d {return Err(model::bad());} part.drain(..2);}
            }
            if latest || paced {
                if !c.poses_out.is_empty() {c.pose_stats.replaced_unsent += 1;}
                c.poses_out = parts;
            } else {
                // SPAWN-15: more than 13 visible vehicles take up to three bodies;
                // with <= 4 pending the transport bound (8) is never exceeded.
                for body in parts {next.tx.enqueue_body(&body)?;}
            }
            c.pose_stats.published(c.last_pose_tick, next_world.tick);
            c.last_pose_tick=Some(next_world.tick);
            println!("SHARED_SNAPSHOT battle={} session={} tick={} positions={:?} ready={:?} aim_yaw_pitch={:?}", next_world.id, s.id, next_world.tick,
                next_world.actors.iter().map(|a| a.position).collect::<Vec<_>>(), c.visible(),
                next_world.actors.iter().map(|a| (a.aim.yaw,a.aim.pitch)).collect::<Vec<_>>());
        }
    }
    // At most40 MS-1 or60 IS-7 shots: start cue+tracer+stop+one compound impact, plus
    // bounded reload/readiness/health catch-up. Slow peers cannot grow forever.
    if next.outbox.len()+next.shared.as_ref().ok_or_else(||model::bad())?.pending_private_len() > next_world.shot_limit() * 4 + 32 { return Err(model::bad()); } next.drain_outbox()?;next.flush_shared_private()?;
    {let backlog=next.outbox.len();let c=next.shared.as_mut().ok_or_else(||model::bad())?;c.pose_stats.outbox_max=c.pose_stats.outbox_max.max(backlog);}
    let mut turret_events=Vec::new();next.flush_shared_turrets(&next_world,&mut turret_events)?;
    for outcome in outcomes { println!("SHARED_FIRE battle={} session={} slot={slot} outcome={outcome:?}", world.id, s.id); }
    for command in &commands { if let model::Command::Move(input) = command { println!("SHARED_INPUT battle={} session={} slot={slot} input={input:?} client_position_used=false", world.id, s.id); } }
    for command in &commands { if let model::Command::Aim(intent) = command { println!("SHARED_AIM battle={} session={} slot={slot} intent={intent:?} client_angles_authoritative=false", world.id, s.id); } }
    for (shot, delivered) in shot_publications {
        println!("SHARED_SHOT_CUE battle={} session={} shot={} shooter_slot={} tick={} queued={} reason={}",
            world.id, s.id, shot.sequence, shot.slot, shot.tick, delivered,
            if delivered { "visible_native_vehicle" } else { "not_observable_at_event" });
    }
    if next_world.projectiles.len() > prior_projectile_count {
        for projectile in next_world.projectiles.iter().skip(prior_projectile_count) {
            println!("SHARED_PROJECTILE_LAUNCHED battle={} shot={} shooter_slot={} origin={:?} velocity={:?} gravity={} max_distance={} flight_seconds={:.6}",
                world.id, projectile.sequence, projectile.slot, projectile.origin, projectile.velocity,
                projectile.gravity, projectile.max_distance, projectile.flight_time.as_secs_f32());
        }
    }
    for (sequence, shooter_slot) in tracer_starts {
        println!("SHARED_TRACER_START battle={} session={} shot={} shooter_slot={} native_method=Avatar.showTracer queued=true", world.id, s.id, sequence, shooter_slot);
    }
    for (sequence, shooter_slot) in anonymous_tracers {
        println!("AV01_TRACER_ANONYMOUS battle={} session={} shot={} shooter_slot={} native_method=Avatar.showTracer shooter_id=0 offset_m={}", world.id, s.id, sequence, shooter_slot, super::av01_feedback::HIDDEN_TRACER_OFFSET_M);
    }
    for (sequence, shooter_slot) in tracer_stops {
        if next_world.terrain_contacts.iter().any(|c|c.shot==sequence) {
            println!("SHARED_TERRAIN_PUBLICATION battle={} session={} shot={} shooter_slot={} native_method=Avatar.explodeProjectile queued=true",world.id,s.id,sequence,shooter_slot);
        } else {
            println!("SHARED_TRACER_STOP battle={} session={} shot={} shooter_slot={} native_method=Avatar.stopTracer queued=true", world.id, s.id, sequence, shooter_slot);
        }
    }
    for (shot,target,hp,queued) in impact_publications {
        println!("SHARED_AP_PUBLICATION battle={} session={} shot={} target={} health={} queued={} historical_fidelity=approximate",
            world.id,s.id,shot,target,hp,queued);
    }
    *world = next_world; *s = next;
    for event in turret_events{println!("{event}");}
    Ok(())
}

/// Native visual category and component of one vehicle impact; None without
/// a native segment. Presentation only, never the damage decision.
fn impact_visual(event:&model::AppliedImpact)->io::Result<Option<(&super::geometry::ImpactSegment,impact_wire::ShotOutcome,u8)>> {
    let Some(segment) = &event.segment else { return Ok(None); };
    let outcome = match &event.outcome {
        // Explicit laboratory policy: a wreck blocks the shell.
        // The native resisted FX also works on HP0 entities;
        // this is not an armor calculation or a new death.
        model::ImpactOutcome::WreckBlocked => impact_wire::ShotOutcome::NotPierced,
        model::ImpactOutcome::Ap(resolution) => match resolution.outcome {
            ap::Outcome::Ricochet => impact_wire::ShotOutcome::Ricochet,
            ap::Outcome::NotPierced => impact_wire::ShotOutcome::NotPierced,
            ap::Outcome::Pierced => impact_wire::ShotOutcome::Pierced,
            ap::Outcome::Unsupported(_) => return Err(model::bad()),
        },
        model::ImpactOutcome::Mixed(resolution)=>match resolution.decision{
            crate::p06t_damage::Decision::Ricochet=>impact_wire::ShotOutcome::Ricochet,
            crate::p06t_damage::Decision::NotPierced=>impact_wire::ShotOutcome::NotPierced,
            crate::p06t_damage::Decision::Pierced=>impact_wire::ShotOutcome::Pierced,
            // Native visual category only. The authoritative LAB
            // decision and damage ledger keep UnarmoredDevice /
            // pierced=false; no ordinary armor claim is made.
            crate::p06t_damage::Decision::UnarmoredDevice=>impact_wire::ShotOutcome::Pierced,
            _=>return Err(model::bad()),
        },
    };
    let component = match segment.component {
        super::materials::Component::Hull => 1,
        super::materials::Component::Turret01 => 2,
        super::materials::Component::Gun02 | super::materials::Component::Gun01 => 3,
    };
    Ok(Some((segment,outcome,component)))
}
/// Original effects index frozen at launch.
fn projectile_effects(projectile:&super::projectile::Projectile)->io::Result<u8> {
    match projectile.shell { Some(shell)=>crate::armament_wire091::effect_index(shell), None=>Ok(projectile.vehicle_kind.shell().effects) }
}

/// AV-01 per-recipient state publication for created (visible) vehicles:
/// one private body per vehicle (a hide invalidates only that vehicle), at
/// most six engineMode and two damageStickers bodies per call (bounded queue
/// growth; the rest follows on later calls), and the spotter's first spots.
fn publish_av01(c:&mut Client,outbox:&mut std::collections::VecDeque<Vec<u8>>,world:&World,impact_from:usize)->io::Result<()> {
    use super::av01_feedback as av;
    let visible=c.visible();
    let mut sent=0;
    for slot in 0..world.actors.len() {
        if sent==6 {break;}
        if !visible[slot] {continue;}
        let actor=&world.actors[slot];
        let running=actor.alive()&&actor.devices.as_ref().is_none_or(|d|d.health()[crate::p06t_device_caps::Device::Engine as usize]>0);
        let mode=av::engine_mode(running,actor.input);
        if c.engine_sent[slot]!=Some(mode) {c.queue_private(outbox,av::engine_mode_update(slot,mode)?,&[slot])?;c.engine_sent[slot]=Some(mode);sent+=1;}
    }
    let fresh=world.impacts.get(impact_from..).unwrap_or(&[]);
    let mut sent=0;
    for slot in 0..world.actors.len() {
        if sent==2 {break;}
        if !visible[slot] || c.stickers_sent[slot].is_some() && !fresh.iter().any(|e|e.target==slot) {continue;}
        let codes=sticker_codes(world,slot)?;
        if c.stickers_sent[slot].as_ref()!=Some(&codes) {
            c.queue_private(outbox,av::damage_stickers_update(slot,&codes)?,&[slot])?;sent+=1;
        }
        c.stickers_sent[slot]=Some(codes);
    }
    if let Some(spots)=world.result_spots() {
        for record in spots.iter().skip(c.scout_cursor) {
            if record.observer()==c.slot {outbox.push_back(av::scout_spotted(record.target())?);}
        }
        c.scout_cursor=spots.len();
    }
    Ok(())
}
/// Current damage stickers of one vehicle: its newest distinct impact codes.
/// A decal is optional presentation: an impact without a native visual
/// category or a quantizable segment gets none instead of failing the battle.
fn sticker_codes(world:&World,target:usize)->io::Result<Vec<u64>> {
    let mut codes:Vec<u64>=Vec::new();
    for event in world.impacts.iter().rev().filter(|e|e.target==target) {
        if codes.len()==super::av01_feedback::MAX_STICKERS {break;}
        let Some((segment,outcome,component))=impact_visual(event).ok().flatten() else {continue;};
        let projectile=world.projectiles.iter().find(|p|p.sequence==event.shot).ok_or_else(||model::bad())?;
        let Ok(point)=impact_wire::packed_segment(component,segment.bounds,segment.start,segment.end,outcome) else {continue;};
        let code=super::av01_feedback::sticker_code(projectile_effects(projectile)?,outcome,point)?;
        if !codes.contains(&code) {codes.push(code);}
    }
    codes.reverse();Ok(codes)
}

/// Clear frames for one session this loop, in send order: due reliable bodies
/// (one, or all with a NET-01 burst mode), then the newest unreliable pose.
/// `None`: the reliable window exhausted its retries.
fn transmit(s: &mut Session, now: Instant) -> io::Result<Option<Vec<Vec<u8>>>> {
    let burst = s.shared.as_ref().is_some_and(|c| c.pose_delivery().burst());
    let mut frames = Vec::new();
    loop {
        match s.tx.due(now, s.rx) {
            Ok(Some((_, _, clear))) => { frames.push(clear); if !burst { break; } },
            Ok(None) => break,
            Err(_) => return Ok(None),
        }
    }
    if s.shared.as_ref().is_some_and(|c| c.pose_delivery() == super::net01::PoseDelivery::ReliableBurstV2) {
        let c = s.shared.as_mut().ok_or_else(|| model::bad())?;
        if !c.in_battle() { c.take_poses(); }
        // One reliable pose part per loop, after the bodies already queued.
        else if !c.poses_out.is_empty() && s.tx.len() < 8 {
            let part = c.poses_out.remove(0);
            s.tx.enqueue_body(&part)?;
            match s.tx.due(now, s.rx) {
                Ok(Some((_, _, clear))) => { frames.push(clear); },
                Ok(None) => return Err(model::bad()),
                Err(_) => return Ok(None),
            }
        }
        return Ok(Some(frames));
    }
    if let Some(c) = s.shared.as_mut() {
        // A pose left over from a battle that ended is dropped, never sent.
        let poses = c.take_poses();
        if c.in_battle() {
            for body in poses {
                let clear = transport091::unreliable(s.rx, &body)?;
                c.record_pose_packet(clear.len()); frames.push(clear);
            }
        }
    }
    Ok(Some(frames))
}

fn poll(s: &mut Session, world: &mut World, now: Instant) -> io::Result<()> {
    poll_with_native_start(s, world, now, true)
}

fn entry_ready(s: &Session, now: Instant) -> bool {
    s.ready_for_arena_base() && s.shared.as_ref().is_some_and(|c| c.phase == Phase::Account
        && c.join_requested
        && c.hangar_since.is_some_and(|start| now.saturating_duration_since(start) >= Duration::from_secs(3)))
}

#[cfg(test)]
mod profile13_template_regressions {
    use super::*;
    #[test] fn profile13_template_selection_keeps_same_battle_id_without_weakening_fresh_guard() {
        let now=Instant::now();
        let pristine=World::new_for_vehicle(991,now,MapId::Prohorovka,VehicleKind::Is7).unwrap();
        assert!(pristine.fresh_battle(991,now).is_err());
        let template=BattleTemplate::new(&pristine,&None);
        let mut world=World::new_for_vehicle(991,now,MapId::Prohorovka,VehicleKind::Ms1).unwrap();
        let mut runtime=None;
        template.select(&mut world,&mut runtime,now+Duration::from_secs(1)).unwrap();
        assert_eq!(world.id,991);assert_eq!(world.vehicle_kind(),VehicleKind::Is7);
        assert!(world.actors.is_empty());assert!(world.shots.is_empty());assert!(world.started.is_none());
        template.replace(&mut world,&mut runtime,now+Duration::from_secs(2)).unwrap();
        assert_eq!(world.id,992);assert_eq!(world.vehicle_kind(),VehicleKind::Is7);
        assert!(world.actors.is_empty());assert!(runtime.is_none());
        world.attach(model::Identity{account:"already-owned".into(),database:1,name:"owned".into()},1).unwrap();
        let actors=world.actors.clone();
        assert!(template.select(&mut world,&mut runtime,now+Duration::from_secs(2)).is_err());
        assert_eq!(world.actors,actors);assert_eq!(world.id,992);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn is7_world(now:Instant)->World {
        let mut world=World::new_for_vehicle(123,now,MapId::Prohorovka,VehicleKind::Is7).unwrap();
        for slot in 0..2 { world.attach(model::Identity { account:format!("owned-{slot}"),
            database:slot+1,name:format!("player_{slot}") },slot as u32+1).unwrap(); }
        world.start(now).unwrap();world.set_ready(0,1).unwrap();world.set_ready(1,2).unwrap();world
    }

    #[test]
    fn is7_cannot_start_with_a_heavy_ms1_or_an_unbound_worker_pool() {
        let pool=worker_fixtures::p06n();let bundle=super::super::geometry::tests::bundle();
        assert!(validate_vehicle_binding(VehicleKind::Ms1,&pool,Some(&bundle)).is_ok());
        assert!(validate_vehicle_binding(VehicleKind::Is7,&pool,Some(&bundle)).is_err());
        assert!(validate_vehicle_binding(VehicleKind::Is7,&pool,None).is_err());
        let now=Instant::now();let mut world=is7_world(now);
        let mut runtime=IntegratedRuntime::new_for_map(Arc::new(pool),MapId::Prohorovka);
        assert!(runtime.start(&mut world,now).is_err());
        assert!(runtime.workers.iter().all(Option::is_none));
    }

    #[test]
    fn is7_shot_publishes_own_shell_reload_and_effects_to_both_sessions() {
        let now=Instant::now();let(mut a,mut b,_)=visible_pair(now);let mut world=is7_world(now);
        for s in [&mut a,&mut b] { s.shared.as_mut().unwrap().view=Some(world.clone()); }
        a.shared.as_mut().unwrap().commands.push(model::Command::Fire(crate::battle091::fire::Command::Shoot));
        poll(&mut a,&mut world,now).unwrap();poll(&mut b,&mut world,now).unwrap();
        assert_eq!(world.actors[0].fire.ammo(),29);assert_eq!(world.actors[1].fire.ammo(),30);
        assert_eq!(world.actors[0].health,2150);assert_eq!(world.actors[1].health,2150);
        let mut expected=wire::ammo_count_for(VehicleKind::Is7,29).unwrap();
        expected.extend(wire::reload_for(VehicleKind::Is7,0,13.7).unwrap());
        let start=wire::tracer_start(&world.projectiles[0]).unwrap();
        assert!(queued_bodies(&a,now).contains(&expected));
        for s in [&a,&b] { assert_eq!(queued_bodies(s,now).iter().filter(|v|**v==start).count(),1); }
        a.shared.as_mut().unwrap().commands.push(model::Command::Fire(crate::battle091::fire::Command::Shoot));
        poll(&mut a,&mut world,now+Duration::from_secs(3)).unwrap();
        assert_eq!(world.shots.len(),1);assert_eq!(world.actors[0].fire.ammo(),29);
        // Same actor reconnect preserves profile, ammo and cooldown.
        world.detach(1).unwrap();world.attach(world.actors[0].identity.clone(),3).unwrap();
        assert_eq!(world.actors[0].vehicle_kind(),VehicleKind::Is7);
        assert_eq!(world.actors[0].fire.ammo(),29);assert_eq!(world.actors[0].health,2150);
    }
    #[test] fn selected_map_admission_uses_source_pins_and_rejects_cross_map_workers_before_start() {
        let pool=worker_fixtures::p06n();
        for map_id in [MapId::Karelia,MapId::Prohorovka] {
            let spec=selected_pool_map(&pool,map_id).unwrap();
            assert_eq!(spec.asset,map_id.asset());
            assert_eq!(spec.arena_type_id,map_id.arena_type_id());
            let config=selected_pool_config(&pool,map_id).unwrap();
            assert_eq!(config["map"],map_id.asset());
            assert_eq!(config["terrain"]["sha256"],map_id.spec().terrain_manifest_sha256);
            assert_eq!(config["obstacles"]["sha256"],map_id.spec().physics_manifest_sha256);
        }
        let mut reversed=pool.clone(); reversed.maps.reverse();
        assert_eq!(selected_pool_map(&pool,MapId::Prohorovka).unwrap(),
                   selected_pool_map(&reversed,MapId::Prohorovka).unwrap());
        let mut wrong_id=pool.clone();
        wrong_id.maps.iter_mut().find(|m|m.asset=="05_prohorovka").unwrap().arena_type_id=5;
        assert!(selected_pool_map(&wrong_id,MapId::Prohorovka).is_err());
        let mut duplicate=pool.clone();
        duplicate.maps.push(selected_pool_map(&pool,MapId::Prohorovka).unwrap().clone());
        assert!(selected_pool_map(&duplicate,MapId::Prohorovka).is_err());
        let mut replaced=pool.clone();
        replaced.maps.iter_mut().find(|m|m.asset=="05_prohorovka").unwrap().config_sha256="0".repeat(64);
        assert!(selected_pool_config(&replaced,MapId::Prohorovka).is_err());
        let karelia=selected_pool_map(&pool,MapId::Karelia).unwrap().clone();
        let mut mixed=pool.clone();
        let wrong=mixed.maps.iter_mut().find(|m|m.asset=="05_prohorovka").unwrap();
        wrong.config=karelia.config.clone(); wrong.config_sha256=karelia.config_sha256.clone();
        assert!(selected_pool_config(&mixed,MapId::Prohorovka).is_err());
        let now=Instant::now(); let mut old_world=model::tests::world(now);
        let mut runtime=IntegratedRuntime::new_for_map(Arc::new(pool),MapId::Prohorovka);
        assert!(runtime.start(&mut old_world,now).is_err());
        assert!(runtime.step(&mut old_world,now).is_err());
        old_world.map=MapId::Prohorovka;
        assert!(runtime.spawn_slot(&old_world,0,karelia,now).is_err());
        assert!(runtime.workers.iter().all(Option::is_none));
    }

    #[test] fn incomplete_prohorovka_modes_fail_before_any_file_or_network_access() {
        for (geometry,ap,terrain,legacy_removal) in [
            (None,false,false,false),(Some("missing"),true,false,false),
            (Some("missing"),false,true,false),(Some("missing"),true,true,true),
        ] {
            let error=serve_integrated_for_map("missing","missing","missing","missing","missing",
                geometry,ap,terrain,legacy_removal,None,MapId::Prohorovka).unwrap_err();
            assert_eq!(error.downcast_ref::<io::Error>().unwrap().kind(),io::ErrorKind::InvalidData);
        }
    }
    fn peer(port: u16) -> SocketAddr { SocketAddr::from(([127,0,0,1], port)) }
    #[test]
    fn integrated_worker_bridge_keeps_worker_terrain_height() {
        let client = [-67.499908, 22.416676, -440.81305];
        let worker = [-67.499344, 21.44713, -440.81094];
        let offset = worker_frame_offset(client, worker);
        assert_eq!(offset, [-0.0005645752, 0., -0.0021057129]);

        let bridged = worker_frame_position(worker, offset);
        assert!((bridged[0] - client[0]).abs() < 0.001);
        assert!((bridged[2] - client[2]).abs() < 0.001);
        assert_eq!(bridged[1], worker[1]);
        assert_ne!(bridged[1], client[1]);
    }

    fn session(id: u32, now: Instant) -> Session {
        let mut s = Session::new(id, [id as u8;16], peer(30000 + id as u16), now);
        s.login_attempt = Some(LoginAttempt::new(s.key, id, s.login_peer)); s
    }
    pub(super) fn driving(now: Instant) -> (Session, World) {
        let world = model::tests::world(now);
        let mut s = session(1, now);
        let identity = crate::identity091::Profile {
            account_id: crate::arena_vehicle091::PRIMARY_ACCOUNT.into(), database_id: 1,
            name: crate::arena_vehicle091::PRIMARY_NAME.into(),
            fixture_dir: Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/server/fixtures")
                .join(crate::arena_vehicle091::PRIMARY_ACCOUNT).join("r4-catalog3").canonicalize().unwrap(),
        };
        s.hangar = Some(Arc::new(crate::hangar091::Fixtures::load_interactive(&identity.fixture_dir).unwrap()));
        s.identity = Some(Arc::new(identity)); s.active = true; s.rx = 1; s.account_ready = true;
        s.tx = Window::interactive(); s.arena_base = true;
        let mut c = Client::new(0); c.phase = Phase::Driving; c.correction = true; c.return_generation=1;
        c.binding = Some((0,true)); c.view = Some(world.clone()); s.shared = Some(c); (s,world)
    }
    pub(super) fn frame(s: &Session, payload: &[u8]) -> Frame {
        Frame { flags:0x458, sequence:Some(s.rx), cumulative:Some(0), selective:vec![],
            body:[vec![1],s.token.to_le_bytes().to_vec(),payload.to_vec()].concat(), piggybacks:vec![] }
    }
    pub(super) fn visible_pair(now: Instant) -> (Session, Session, World) {
        let (mut a,w) = driving(now);
        a.shared.as_mut().unwrap().creations = [Some((0,true));model::MAX_ACTORS];
        a.shared.as_mut().unwrap().ready_sent = [true;model::MAX_ACTORS];
        let mut b = a.clone(); b.id = 2; b.shared.as_mut().unwrap().slot = 1;
        (a,b,w)
    }
    pub(super) fn queued_bodies(s: &Session, now: Instant) -> Vec<Vec<u8>> {
        let mut tx = s.tx.clone(); let mut bodies = Vec::new();
        while let Some((_,_,raw)) = tx.due(now,s.rx).unwrap() {
            bodies.push(transport091::parse_interactive(&raw).unwrap().body);
        }
        bodies.extend(s.outbox.iter().cloned()); bodies
    }
    fn returning_pair_fixture(now:Instant)->(Table,World) {
        let (a,b,world)=visible_pair(now);
        let mut table=Table{sessions:vec![a,b],..Table::default()};
        for s in &mut table.sessions {
            s.base_peer=Some(peer(32000+s.id as u16)); s.sync_mask=7;
            s.key=[s.id as u8;16];
            s.login_attempt=Some(LoginAttempt::new(s.key,s.id,s.login_peer));
            s.shared.as_mut().unwrap().entered=Some(now);
        }
        (table,world)
    }
    #[test]
    fn stab01_two_native_leaves_after_90s_keep_channels_and_surviving_authority() {
        let now=Instant::now();let (mut table,mut world)=returning_pair_fixture(now);
        let later=now+Duration::from_secs(91);
        for index in 0..2 {
            let id=table.sessions[index].id;
            let c=table.sessions[index].shared.as_mut().unwrap();
            c.phase=Phase::Leaving;c.commands.push(model::Command::Leave);
            poll_battle_session(&mut table.sessions[index],&mut world,later,true,false).unwrap();
            assert_eq!(table.sessions.len(),2);
            assert_eq!(table.sessions[index].shared.as_ref().unwrap().phase,Phase::Returning);
            assert!(world.actors[index].session.is_none());
            assert!(queued_bodies(&table.sessions[index],later).iter().any(|body|
                body==&crate::map_drive_world091::return_account(&table.sessions[index].identity.as_ref().unwrap().name).unwrap()));
            assert!(table.sessions[index].active);assert_eq!(table.sessions[index].rx,1);
            assert_eq!(table.retirement.retained_count(),0);
            if index==0 {assert!(world.owned(1,2).is_ok());assert!(world.actors[1].ready);}
            assert!(!world.actors.iter().any(|a|a.session==Some(id)));
        }
    }
    #[test]
    fn stab01_leave_waits_for_scene_barrier_then_detaches_even_before_area_ready() {
        let now=Instant::now();let (mut table,_)=returning_pair_fixture(now);
        let mut world=model::tests::destructible_world(now);
        let s=&mut table.sessions[0];let c=s.shared.as_mut().unwrap();
        c.view=Some(world.clone());c.area_creation=None;c.phase=Phase::Leaving;
        c.commands=vec![model::Command::Leave];
        assert!(!c.areas_ready(&world));
        poll_battle_session(s,&mut world,now,true,true).unwrap();
        assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Leaving);
        assert!(world.owned(0,1).is_ok());
        poll_battle_session(s,&mut world,now,true,false).unwrap();
        assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Returning);
        assert!(world.actors[0].session.is_none());assert!(world.owned(1,2).is_ok());
        assert!(s.shared.as_ref().unwrap().commands.is_empty());
    }
    #[test]
    fn stab01_native_leave_before_correction_does_not_end_the_peers_battle() {
        let now=Instant::now();let (mut table,mut world)=returning_pair_fixture(now);
        let s=&mut table.sessions[0];s.shared.as_mut().unwrap().correction=false;
        assert!(s.shared.as_ref().unwrap().areas_ready(&world));
        s.receive(&frame(s,&[0x99,1,0,0]),now).unwrap();
        assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Leaving);
        poll_battle_session(s,&mut world,now,true,false).unwrap();
        assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Returning);
        assert!(world.actors[0].session.is_none());assert!(world.owned(1,2).is_ok());
        assert!(world.started.is_some());assert!(table.sessions[1].active);
        assert_eq!(table.sessions[1].shared.as_ref().unwrap().phase,Phase::Driving);
        assert_eq!(table.retirement.retained_count(),0);
    }
    #[test]
    fn stab01_failure_before_avatar_cancels_only_an_announced_native_queue() {
        let now=Instant::now();let (mut table,mut world)=returning_pair_fixture(now);
        let mut runtime=None;world=World::new(world.id,now).unwrap();
        let template=BattleTemplate::new(&world,&runtime);
        let original=table.sessions[1].identity.as_ref().unwrap();
        table.sessions[1].identity=Some(Arc::new(crate::identity091::Profile{account_id:"owned-second".into(),database_id:2,
            name:"player_2".into(),fixture_dir:original.fixture_dir.clone()}));
        for s in &mut table.sessions {
            s.arena_base=false;let c=s.shared.as_mut().unwrap();c.phase=Phase::Account;
            c.queue_announced=s.id==1;c.hangar_since=Some(now-Duration::from_secs(3));
        }
        // Reattachment precedes worker bootstrap and must retain announced UI state.
        attach_waiting_sessions(&mut table,&mut world,now).unwrap();
        assert_eq!(world.actors.len(),2);
        assert!(table.sessions[0].shared.as_ref().unwrap().queue_announced);
        let error=io::Error::new(io::ErrorKind::InvalidData,"injected startup failure");
        contain_battle_failure(&mut table,&mut world,&mut runtime,&template,now,"world_step",&error).unwrap();
        let cancelled=crate::map_drive_world091::queue_callback(false);
        assert!(queued_bodies(&table.sessions[0],now).contains(&cancelled));
        assert!(!queued_bodies(&table.sessions[1],now).contains(&cancelled));
        assert!(table.sessions.iter().all(|s|s.active&&!s.shared.as_ref().unwrap().join_requested));
        assert!(world.actors.is_empty());
    }
    #[test]
    fn stab01_trace_failure_reaps_real_workers_and_starts_second_battle_in_same_controller() {
        let now=Instant::now();let (mut table,mut world)=returning_pair_fixture(now);
        let pool=Arc::new(worker_fixtures::p06n());
        let mut runtime=Some(IntegratedRuntime::new(pool));
        let pristine=World::new(world.id,now).unwrap();
        let template=BattleTemplate::new(&pristine,&runtime);
        let r=runtime.as_mut().unwrap();let map=r.map().unwrap();
        for slot in 0..2 {r.spawn_slot(&world,slot,map.clone(),now).unwrap();}
        let deadline=Instant::now()+Duration::from_secs(30);
        while !r.workers.iter().all(|w|w.as_ref().unwrap().ready()) {
            assert!(Instant::now()<deadline,"real child bootstrap deadline");
            for w in &mut r.workers {w.as_mut().unwrap().poll(Instant::now()).unwrap();}
            thread::sleep(Duration::from_millis(2));
        }
        let exits=r.workers.iter().map(|w|w.as_ref().unwrap().exit_observer()).collect::<Vec<_>>();
        world.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).unwrap();
        world.projectiles[0].origin[0]=super::super::impact::MAX_COORDINATE+1.;
        let failed_tick=world.tick;let failed_id=world.id;let failed_trace=world.impact.clone();
        // Exercise the same step boundary used by the service, injecting a real trace invariant failure.
        let at=now+model::STEP;
        let error=advance_battle(&mut world,&mut None,at,false).unwrap_err();
        assert_eq!(world.tick,failed_tick);assert_eq!(world.impact,failed_trace);
        let retired=LoginAttempt::new([9;16],99,peer(39999));
        table.retirement.retire(retired,None,now).unwrap();
        let snapshot=contain_battle_failure(&mut table,&mut world,&mut runtime,&template,at,"world_step",&error).unwrap();
        assert_eq!(snapshot["world"]["battle"],failed_id.to_string());
        assert_eq!(snapshot["world"]["shots"].as_array().unwrap().len(),1);
        assert!(!snapshot["world"]["trace_tail"].as_array().unwrap().is_empty());
        assert_ne!(world.id,failed_id);assert!(world.started.is_none());
        assert!(world.actors.is_empty()&&world.shots.is_empty()&&world.impact.events().is_empty());
        assert_eq!(table.sessions.len(),2);
        assert!(table.sessions.iter().all(|s|s.shared.as_ref().unwrap().phase==Phase::Returning));
        assert!(table.retirement.check_login(&retired,at).is_err());
        assert!(runtime.as_ref().unwrap().workers.iter().all(Option::is_none));
        let deadline=Instant::now()+Duration::from_secs(5);
        while exits.iter().any(|observe|observe().is_none()) {
            assert!(Instant::now()<deadline,"failed battle children must be reaped");
            thread::sleep(Duration::from_millis(5));
        }
        assert!(exits.iter().all(|observe|observe()==Some((false,Some(0),true))));
        // Account warm protocol has independent Session.receive replay tests.
        // Here supply its completed state to exercise admission and a fresh world on the same service table.
        for s in &mut table.sessions {
            s.tx=Window::interactive();s.outbox.clear();s.drive_return_account=None;
            let c=s.shared.as_mut().unwrap();c.phase=Phase::Account;c.join_requested=true;c.hangar_since=Some(at);
        }
        let second=&mut table.sessions[1];let original=second.identity.as_ref().unwrap();
        second.identity=Some(Arc::new(crate::identity091::Profile{account_id:"owned-second".into(),database_id:2,
            name:"player_2".into(),fixture_dir:original.fixture_dir.clone()}));
        let again=at+Duration::from_secs(3);
        attach_waiting_sessions(&mut table,&mut world,again).unwrap();
        assert!(table.sessions.iter().all(|s|entry_ready(s,again)));
        advance_battle(&mut world,&mut runtime,again,true).unwrap();
        assert!(world.started.is_some());assert_eq!(world.actors.len(),2);
        assert!(world.shots.is_empty()&&world.impact.events().is_empty());
        assert!(world.actors.iter().all(|a|a.fire.ammo()==20));
    }
    fn destroyed_fixture(now:Instant)->World {
        let mut w=model::tests::destructible_world(now);
        w.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).unwrap();
        w.advance(now+model::STEP).unwrap(); assert_eq!(w.scene_version(),1); w
    }
    #[test] fn incomplete_area_startup_times_out_but_restoring_peer_does_not_block_survivor_commands() {
        let now=Instant::now();let(mut a,_,_)=visible_pair(now);let mut w=destroyed_fixture(now);
        let c=a.shared.as_mut().unwrap();c.view=Some(w.clone());c.shot_cursor=w.latest_shot();
        c.entered=Some(now-Duration::from_secs(91));c.area_creation=None;
        assert!(poll_with_native_start(&mut a,&mut w,now+model::STEP,false).is_err());
        let c=a.shared.as_mut().unwrap();c.area_creation=Some((0,true));c.area_scene_sent=1;
        // Global arena-entry readiness is false while the other worker restores,
        // but 64 successive survivor envelopes must be consumed without overflow.
        for _ in 0..64 {
            a.shared.as_mut().unwrap().commands.push(model::Command::Move(model::Input{throttle:1,steer:0,speed_percent:100}));
            poll_with_native_start(&mut a,&mut w,now+model::STEP,false).unwrap();
            assert!(a.shared.as_ref().unwrap().commands.is_empty());
        }
        assert_eq!(w.actors[0].input.throttle,1);
    }
    #[test] fn area_request_mixed_envelope_is_atomic_and_rejoin_uses_current_state() {
        let now=Instant::now(); let (mut s,_)=driving(now); let w=destroyed_fixture(now);
        let c=s.shared.as_mut().unwrap();c.phase=Phase::Entities;c.view=Some(w.clone());
        c.announcement=Some((0,true));c.creations=[None;model::MAX_ACTORS];
        let mut request=vec![8,4,0];request.extend(super::super::destructible_wire::ENTITY_ID.to_le_bytes());
        request.extend([8,4,0]);request.extend(wire::vehicle_id(0).unwrap().to_le_bytes());
        let mut poisoned=request.clone();poisoned.extend([8,4,0]);poisoned.extend(123u32.to_le_bytes());
        let rx=s.rx;assert!(s.receive(&frame(&s,&poisoned),now).is_err());
        assert_eq!(s.rx,rx);assert!(s.shared.as_ref().unwrap().area_creation.is_none());
        s.receive(&frame(&s,&request),now).unwrap();
        assert!(s.shared.as_ref().unwrap().area_creation.is_some());assert_eq!(s.shared.as_ref().unwrap().area_scene_sent,1);
        let expected=super::super::destructible_wire::create(Some(1)).unwrap();
        assert!(queued_bodies(&s,now).iter().any(|b|b.windows(expected.len()).any(|p|p==expected)));
    }
    #[test] fn area_ack_gates_commands_and_state_update_is_once_and_transactional() {
        let now=Instant::now();let(mut a,mut b,_)=visible_pair(now);let mut w=destroyed_fixture(now);
        for s in [&mut a,&mut b] {
            let c=s.shared.as_mut().unwrap();c.view=Some(w.clone());c.shot_cursor=w.latest_shot();
            c.area_creation=Some((0,false));c.commands.push(model::Command::Move(model::Input{throttle:1,steer:0,speed_percent:100}));
            poll(s,&mut w,now+model::STEP).unwrap();assert_eq!(s.shared.as_ref().unwrap().commands.len(),1);
            assert_eq!(s.shared.as_ref().unwrap().area_scene_sent,0);
            s.shared.as_mut().unwrap().area_creation=Some((0,true));
            s.outbox.push_back(vec![0;513]);assert!(poll(s,&mut w,now+model::STEP).is_err());
            assert_eq!(s.shared.as_ref().unwrap().area_scene_sent,0);s.outbox.clear();
            poll(s,&mut w,now+model::STEP).unwrap();assert!(s.shared.as_ref().unwrap().commands.is_empty());
            let update=super::super::destructible_wire::update(1);let before=queued_bodies(s,now+model::STEP);
            assert_eq!(before.iter().filter(|b|b.windows(update.len()).any(|p|p==update)).count(),1);
            poll(s,&mut w,now+model::STEP).unwrap();assert_eq!(queued_bodies(s,now+model::STEP),before);
        }
    }
    #[test] fn two_real_workers_acknowledge_before_world_commit_and_changed_membership_fails() {
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap();
        let pool=Arc::new(worker_fixtures::p06n());
        let spec=crate::map_drive_worker091::RemovalSpec::load(&root.join("local"),
            &root.join("local/evidence/20261010-p06n-destructible-01/boundary/worker-ipc01/descriptor.json"),
            "ef00e2aed686c16c4f9a216d9db70dbcd1ca3fda84bc33cd9eaa8aed1dbde7fa").unwrap();
        let now=Instant::now();let mut world=model::tests::destructible_world(now);
        world.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).unwrap();
        let mut candidate=world.clone();candidate.advance(now+model::STEP).unwrap();
        let expected=candidate.destructible_transition().unwrap().clone();
        let mut runtime=IntegratedRuntime::new(pool);runtime.removal=Some(spec);let map=runtime.map().unwrap();
        for slot in 0..2 {runtime.spawn_slot(&world,slot,map.clone(),now).unwrap();}
        let deadline=now+Duration::from_secs(60);
        while !runtime.workers.iter().all(|w|w.as_ref().unwrap().ready()) {
            let at=Instant::now();assert!(at<deadline);for w in &mut runtime.workers{w.as_mut().unwrap().poll(at).unwrap();}
            std::thread::sleep(Duration::from_millis(2));
        }
        runtime.staged=Some(candidate.clone());assert!(runtime.blocked());
        runtime.finish_removal(&mut world,Instant::now()).unwrap();assert_eq!(world.scene_version(),0);
        while runtime.blocked(){assert!(Instant::now()<deadline);runtime.finish_removal(&mut world,Instant::now()).unwrap();std::thread::sleep(Duration::from_millis(2));}
        assert_eq!(world.scene_version(),1);assert_eq!(world.destructible_transition(),Some(&expected));
        assert!(runtime.workers.iter().all(|w|w.as_ref().unwrap().scene_version()==1));
        let mut changed=model::tests::destructible_world(now);changed.detach(1).unwrap();
        runtime.staged=Some(candidate);assert!(runtime.finish_removal(&mut changed,Instant::now()).is_err());
        assert_eq!(changed.scene_version(),0);assert!(runtime.blocked());
        // A just-launched reconnect is not yet part of the simulation scene.
        // It must not turn an otherwise valid hit into a seq0-pose barrier error.
        runtime.staged=None;runtime.workers[0].take();runtime.workers[1].take();
        let later=Instant::now();let mut fresh=model::tests::destructible_world(later);
        fresh.actors[1].ready=false;
        fresh.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],later).unwrap();
        let mut candidate=fresh.clone();candidate.advance(later+model::STEP).unwrap();
        runtime.spawn_slot(&fresh,0,map.clone(),later).unwrap();
        while !runtime.workers[0].as_ref().unwrap().ready(){
            assert!(Instant::now()<deadline);
            if let Some(state)=runtime.workers[0].as_mut().unwrap().poll(Instant::now()).unwrap() {
                runtime.anchored[0]=true;runtime.poses[0]=Some((state.pose.position,state.pose.direction,state.pose.speed));
            }
            std::thread::sleep(Duration::from_millis(2));
        }
        runtime.spawn_slot(&fresh,1,map,later).unwrap();
        runtime.staged=Some(candidate);
        while runtime.staged.is_some(){assert!(Instant::now()<deadline);runtime.finish_removal(&mut fresh,Instant::now()).unwrap();std::thread::sleep(Duration::from_millis(2));}
        assert_eq!(fresh.scene_version(),1);assert!(!runtime.workers[1].as_ref().unwrap().ready());
        while runtime.workers[1].as_ref().unwrap().scene_version()!=1 {
            assert!(Instant::now()<deadline);runtime.step(&mut fresh,Instant::now()).unwrap();
            std::thread::sleep(Duration::from_millis(2));
        }
        assert_eq!(runtime.generations,[2,2]);assert!(!fresh.actors[1].ready);
        assert_eq!(fresh.destructible_transition().unwrap().shot,1);
    }
    #[test] fn terrain_fx_is_once_per_peer_excludes_stop_and_queue_retry_is_atomic() {
        let now=Instant::now(); let (mut a,mut b,_)=visible_pair(now);
        let mut w=model::tests::terrain_world(now,3.);
        a.shared.as_mut().unwrap().commands.push(model::Command::Fire(crate::battle091::fire::Command::Shoot));
        poll(&mut a,&mut w,now).unwrap(); poll(&mut b,&mut w,now).unwrap();
        w.advance(now+model::STEP).unwrap(); assert_eq!(w.terrain_contacts.len(),1);
        let c=&w.terrain_contacts[0]; let fx=terrain_wire::explode(c.shot,c.hit.point,c.direction).unwrap();
        let stop=wire::tracer_stop(&w.projectiles[0]).unwrap();
        let (mut retry,_,_)=visible_pair(now); *retry.shared.as_mut().unwrap()=a.shared.as_ref().unwrap().clone();
        retry.outbox.push_back(vec![0;513]);
        assert!(poll(&mut retry,&mut w,now+model::STEP).is_err());
        assert!(!retry.shared.as_ref().unwrap().tracer_stopped[0]);
        assert_eq!(w.actors[1].health,90); assert!(w.impacts.is_empty());
        retry.outbox.clear();
        for s in [&mut a,&mut b,&mut retry] {
            poll(s,&mut w,now+model::STEP).unwrap();
            let before=queued_bodies(s,now+model::STEP);
            assert_eq!(before.iter().filter(|body|body.windows(fx.len()).any(|bytes|bytes==fx)).count(),1);
            assert!(!before.iter().any(|body|body.windows(stop.len()).any(|bytes|bytes==stop)));
            assert!(s.shared.as_ref().unwrap().tracer_stopped[0]);
            poll(s,&mut w,now+model::STEP).unwrap();
            let after=queued_bodies(s,now+model::STEP);
            assert_eq!(after.iter().filter(|body|body.windows(fx.len()).any(|bytes|bytes==fx)).count(),1);
            assert!(!after.iter().any(|body|body.windows(stop.len()).any(|bytes|bytes==stop)));
        }
    }
    #[test] fn p04m_admitted_six_actor_late_ground_terminal_publishes_once_without_battle_fault() {
        // Exercise the production poll branch with real domain-admitted global
        // shot IDs. Only the terminal contact is an authored packet fixture;
        // this is not a native rendering or terrain-query acceptance claim.
        for kind in [VehicleKind::Is7,VehicleKind::Ms1,VehicleKind::T26] {
            let start=Instant::now();
            let mut world=World::new_for_vehicle(4041,start,MapId::Prohorovka,kind).unwrap();
            world.set_expected_actors(model::MAX_ACTORS).unwrap();
            for slot in 0..model::MAX_ACTORS {
                world.attach(model::Identity{account:format!("late-ground-{slot}"),database:slot as i32+1,name:format!("lab-{slot}")},slot as u32+1).unwrap();
                world.actors[slot].fire=crate::battle091::fire::State::with_mounted_loadout(kind.ammo_limit(),kind.reload_seconds(),kind.ammo_limit()).unwrap();
            }
            world.start(start).unwrap();
            for slot in 0..model::MAX_ACTORS {world.set_ready(slot,slot as u32+1).unwrap();}
            for round in 0..kind.ammo_limit() {
                let at=start+Duration::from_secs_f64(round as f64*(kind.reload_seconds() as f64+0.1));
                for slot in (0..model::MAX_ACTORS).rev() {
                    assert!(matches!(world.apply(slot,slot as u32+1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],at).unwrap()[0],crate::battle091::fire::Outcome::AcceptedShot{..}));
                }
            }
            let sequence=world.latest_shot();let index=sequence as usize-1;
            assert_eq!(sequence as usize,model::MAX_ACTORS*kind.ammo_limit() as usize);
            assert!(sequence as usize>kind.battle_shot_limit());
            world.projectiles[index].stopped=true;
            world.terrain_contacts.push(model::TerrainContact{shot:sequence,shooter:0,tick:1,
                hit:super::super::terrain::Hit{surface:super::super::terrain::Surface::Ground,triangle_id:0,t:0.5,point:[1.,2.,3.],normal:[0.,1.,0.]},
                segment_start:[1.,3.,3.],segment_end:[1.,1.,3.],direction:[0.,-1.,0.]});
            let now=start+Duration::from_secs(1000);let(mut a,mut b,_)=visible_pair(now);
            let fx=terrain_wire::explode_material_for_limit(kind,sequence,[1.,2.,3.],[0.,-1.,0.],0,world.shot_limit()).unwrap();
            let stop=wire::tracer_stop(&world.projectiles[index]).unwrap();
            for s in [&mut a,&mut b] {
                let c=s.shared.as_mut().unwrap();c.shot_cursor=sequence;c.tracer_started[index]=true;
                poll(s,&mut world,now).unwrap();
                let raw=queued_bodies(s,now).concat();
                assert_eq!(raw.windows(fx.len()).filter(|bytes|*bytes==fx).count(),1);
                assert!(!raw.windows(stop.len()).any(|bytes|bytes==stop));
                assert!(s.shared.as_ref().unwrap().tracer_stopped[index]);
                poll(s,&mut world,now).unwrap();
                assert_eq!(queued_bodies(s,now).concat(),raw);
            }
        }
    }
    #[test] fn delayed_terrain_fx_follows_tracer_and_reconnect_skips_old_effects() {
        let now=Instant::now(); let (mut a,mut b,_)=visible_pair(now);
        let mut w=model::tests::terrain_world(now,3.);
        w.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).unwrap();
        w.advance(now+model::STEP).unwrap();
        let c=&w.terrain_contacts[0]; let fx=terrain_wire::explode(c.shot,c.hit.point,c.direction).unwrap();
        let start=wire::tracer_start(&w.projectiles[0]).unwrap();
        for s in [&mut a,&mut b] {
            poll(s,&mut w,now+model::STEP).unwrap(); let raw=queued_bodies(s,now+model::STEP).concat();
            assert!(raw.windows(start.len()).position(|v|v==start).unwrap()<raw.windows(fx.len()).position(|v|v==fx).unwrap());
        }
        let (mut rejoin,_,_)=visible_pair(now+model::STEP);
        rejoin.shared.as_mut().unwrap().shot_cursor=w.latest_shot();
        poll(&mut rejoin,&mut w,now+model::STEP).unwrap();
        assert!(!queued_bodies(&rejoin,now+model::STEP).concat().windows(fx.len()).any(|v|v==fx));
    }
    #[test] fn static_stone_effect_uses_original_material_on_both_peers() {
        let now=Instant::now(); let (mut a,mut b,_)=visible_pair(now);
        let mut w=model::tests::obstacle_world(now,20.,3.);
        w.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).unwrap();
        w.advance(now+model::STEP).unwrap(); let c=&w.terrain_contacts[0];
        let fx=terrain_wire::explode_material(c.shot,c.hit.point,c.direction,1).unwrap();
        let wrong=terrain_wire::explode(c.shot,c.hit.point,c.direction).unwrap();
        for s in [&mut a,&mut b] {
            poll(s,&mut w,now+model::STEP).unwrap(); let raw=queued_bodies(s,now+model::STEP).concat();
            assert_eq!(raw.windows(fx.len()).filter(|v|*v==fx).count(),1);
            assert!(!raw.windows(wrong.len()).any(|v|v==wrong));
        }
        assert!(w.impacts.is_empty()); assert_eq!(w.actors[1].health,90);
    }
    #[test] fn ap_publication_is_once_per_peer_and_failed_queue_does_not_repeat_damage() {
        let now=Instant::now(); let (mut a,mut b,_) = visible_pair(now);
        let mut w=model::tests::ap_world(now);
        a.shared.as_mut().unwrap().commands.push(model::Command::Fire(crate::battle091::fire::Command::Shoot));
        poll(&mut a,&mut w,now).unwrap(); poll(&mut b,&mut w,now).unwrap();
        w.advance(now+model::STEP).unwrap(); assert_eq!(w.actors[1].health,60);
        // Make the next drain fail after the world has already committed HP.
        let (mut retry,_,_)=visible_pair(now);
        *retry.shared.as_mut().unwrap()=a.shared.as_ref().unwrap().clone();
        retry.outbox.push_back(vec![0;513]);
        assert!(poll(&mut retry,&mut w,now+model::STEP).is_err());
        assert_eq!(retry.shared.as_ref().unwrap().impact_cursor,0);
        assert_eq!(w.actors[1].health,60); assert_eq!(w.impacts.len(),1);
        retry.outbox.clear(); poll(&mut retry,&mut w,now+model::STEP).unwrap();
        for s in [&mut a,&mut b] { poll(s,&mut w,now+model::STEP).unwrap(); }
        let hp=impact_wire::health_changed(1,60,0).unwrap();
        for s in [&mut a,&mut b,&mut retry] {
            let bodies=queued_bodies(s,now+model::STEP);
            assert_eq!(bodies.iter().filter(|body| body.windows(hp.len()).any(|bytes| bytes==hp)).count(),1);
            let before=bodies.into_iter().filter(|body| body.windows(hp.len()).any(|bytes| bytes==hp)).collect::<Vec<_>>();
            poll(s,&mut w,now+model::STEP).unwrap();
            let after=queued_bodies(s,now+model::STEP).into_iter()
                .filter(|body| body.windows(hp.len()).any(|bytes| bytes==hp)).collect::<Vec<_>>();
            assert_eq!(after,before);
            assert_eq!(s.shared.as_ref().unwrap().impact_cursor,1);
        }
        assert_eq!(w.actors[1].health,60);
    }
    #[test] fn ap_late_publication_is_monotone_and_reconnect_only_catches_current_health() {
        let now=Instant::now(); let (mut a,mut b,_) = visible_pair(now);
        let mut w=model::tests::ap_world(now);
        for round in 0..3 {
            let at=now+Duration::from_secs(round*3); if round>0 {w.advance(at).unwrap();}
            w.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],at).unwrap();
            w.advance(at+model::STEP).unwrap();
        }
        let at=now+Duration::from_secs(7);
        for s in [&mut a,&mut b] {
            poll(s,&mut w,at).unwrap();
            let all=queued_bodies(s,at).concat(); let mut prior=0;
            for hp in [60,30,0] {
                let bytes=impact_wire::health_changed(1,hp,0).unwrap();
                let at=all.windows(bytes.len()).position(|row| row==bytes).unwrap();
                assert!(at>prior); prior=at;
            }
        }
        let (_,mut rejoin,_)=visible_pair(at);
        rejoin.shared.as_mut().unwrap().impact_cursor=w.impacts.len();
        rejoin.shared.as_mut().unwrap().shot_cursor=w.latest_shot();
        rejoin.shared.as_mut().unwrap().health_sent=std::array::from_fn(|slot|[Some(90),Some(0)].get(slot).copied().flatten());
        let creation=wire::create_vehicle(&w,1).unwrap();
        assert!(creation.windows(7).any(|r|r==[3,0,0,4,0,0,5]));
        rejoin.shared.as_mut().unwrap().view=Some(w.clone());
        poll(&mut rejoin,&mut w,at).unwrap();
        assert_eq!(queued_bodies(&rejoin,at),vec![impact_wire::owner_health(0).unwrap()]);
        assert_eq!(w.actors[1].health,0);
    }
    #[test] fn wreck_effect_reaches_both_peers_once_without_health_or_death_replay() {
        let now=Instant::now(); let (mut a,mut b,_) = visible_pair(now);
        let mut w=model::tests::ap_world(now);
        // Kill through real server shots, then fire a fourth shot at the wreck.
        for round in 0..4 {
            let at=now+Duration::from_secs(round*3);
            if round>0 { w.advance(at).unwrap(); }
            w.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],at).unwrap();
            for s in [&mut a,&mut b] { poll(s,&mut w,at).unwrap(); }
            w.advance(at+model::STEP).unwrap();
            if round<3 { for s in [&mut a,&mut b] { poll(s,&mut w,at+model::STEP).unwrap(); } }
        }
        let at=now+Duration::from_secs(9)+model::STEP;
        assert_eq!(w.actors[1].health,0); assert_eq!(w.impacts.len(),4);
        let event=w.impacts.last().unwrap();
        assert_eq!(event.outcome,model::ImpactOutcome::WreckBlocked);
        let segment=event.segment.as_ref().unwrap();
        let component=match segment.component {
            super::super::materials::Component::Hull=>1,
            super::super::materials::Component::Turret01=>2,
            super::super::materials::Component::Gun02|super::super::materials::Component::Gun01=>3,
        };
        let fx=impact_wire::show_damage(0,1,component,segment.bounds,segment.start,segment.end,
            impact_wire::ShotOutcome::NotPierced).unwrap();
        let death=impact_wire::health_changed(1,0,0).unwrap();
        for s in [&mut a,&mut b] {
            let previous=queued_bodies(s,at);
            let death_count=previous.iter().filter(|body| body.windows(death.len()).any(|v|v==death)).count();
            let owner_health=s.shared.as_ref().unwrap().owner_health_sent;
            assert_eq!(s.shared.as_ref().unwrap().impact_cursor,3);
            poll(s,&mut w,at).unwrap();
            let first=queued_bodies(s,at);
            assert_eq!(first.iter().filter(|body|**body==fx).count(),1);
            assert_eq!(first.iter().filter(|body|body.windows(death.len()).any(|v|v==death)).count(),death_count);
            assert_eq!(s.shared.as_ref().unwrap().owner_health_sent,owner_health);
            assert_eq!(s.shared.as_ref().unwrap().impact_cursor,4);
            poll(s,&mut w,at).unwrap();
            assert_eq!(queued_bodies(s,at),first);
        }
        let (_,mut rejoin,_)=visible_pair(at);
        let c=rejoin.shared.as_mut().unwrap();
        c.impact_cursor=w.impacts.len(); c.shot_cursor=w.latest_shot();
        c.health_sent=std::array::from_fn(|slot|[Some(90),Some(0)].get(slot).copied().flatten()); c.owner_health_sent=Some(0); c.view=Some(w.clone());
        poll(&mut rejoin,&mut w,at).unwrap();
        assert!(queued_bodies(&rejoin,at).is_empty());
        assert_eq!(w.actors[1].health,0);
    }
    fn point(slot:usize,p:[f32;3])->Vec<u8> {
        let mut b=vec![0x0f,16,0];b.extend(wire::vehicle_id(slot).unwrap().to_le_bytes());
        for x in p {b.extend(x.to_le_bytes());} b
    }
    #[test] fn native_postmortem_rebind_is_owned_dead_only_and_keeps_reliable_channel_live() {
        let now=Instant::now(); let (_,mut b,mut w)=visible_pair(now);
        let raw=[0x0d,8,0,0,0,0,0,5,0,0x10,9];
        let before=b.rx; assert!(b.receive(&frame(&b,&raw),now).is_err()); assert_eq!(b.rx,before);
        w.actors[1].health=0; b.shared.as_mut().unwrap().view=Some(w.clone());
        b.receive(&frame(&b,&raw),now).unwrap(); assert_eq!(b.rx,before+1);
        b.receive(&frame(&b,&[]),now).unwrap(); assert_eq!(b.rx,before+2);
        assert!(b.shared.as_ref().unwrap().commands.is_empty());
        for offset in [1,3] {
            let mut bad=raw; bad[offset]^=1;
            let before=b.rx; assert!(b.receive(&frame(&b,&bad),now).is_err()); assert_eq!(b.rx,before);
        }
        // POSTMORTEM-01: a well-formed request for a non-vehicle ID is refused
        // as a camera request but consumed, so later keepalives still arrive.
        let mut unknown=raw; unknown[7]^=1;
        let before=b.rx; b.receive(&frame(&b,&unknown),now).unwrap(); assert_eq!(b.rx,before+1);
        b.receive(&frame(&b,&[]),now).unwrap(); assert_eq!(b.rx,before+2);
        assert!(b.shared.as_ref().unwrap().commands.is_empty());
        assert_eq!(w.actors[1].health,0); assert_eq!(b.shared.as_ref().unwrap().slot,1);
    }
    fn bind(target:u32)->Vec<u8> {let mut b=vec![0x0d,8,0,0,0,0,0];b.extend(target.to_le_bytes());b}
    /// Owner 2026-10-29 (-11, battle ...827, session 4): the dead player's
    /// observer camera bound an ally; rejection stalled reliable17381 and every
    /// later 5-byte token-only keepalive failed `n>rx` until idle_timeout.
    #[test] fn postmortem01_observer_camera_switch_to_ally_unbind_and_enemy_keeps_channel_live() {
        let now=Instant::now(); let (_,mut b,mut w)=visible_pair(now);
        // Alive owner: an observer bind is still outside the measured contract.
        let before=b.rx; assert!(b.receive(&frame(&b,&bind(wire::vehicle_id(0).unwrap())),now).is_err()); assert_eq!(b.rx,before);
        w.actors[1].health=0; b.shared.as_mut().unwrap().view=Some(w.clone());
        assert_eq!(w.team(0).unwrap(),w.team(1).unwrap());
        let unchanged=(w.actors.clone(),b.shared.as_ref().unwrap().visible());
        for target in [wire::vehicle_id(0).unwrap(),wire::vehicle_id(1).unwrap(),0,wire::vehicle_id(0).unwrap(),wire::vehicle_id(5).unwrap()] {
            let before=b.rx; b.receive(&frame(&b,&bind(target)),now).unwrap(); assert_eq!(b.rx,before+1);
            b.receive(&frame(&b,&[]),now).unwrap(); assert_eq!(b.rx,before+2);
        }
        let c=b.shared.as_ref().unwrap();
        assert!(c.commands.is_empty()); assert_eq!(c.slot,1); assert_eq!((w.actors.clone(),c.visible()),unchanged);
        // An enemy target is refused without authority or interest change.
        let mut enemy=World::new_for_roster(124,now,crate::map_profile091::MapId::Karelia,3).unwrap();
        enemy.enable_lifecycle(super::super::lifecycle::Rules::prohorovka()).unwrap();
        for i in 0..3 {enemy.attach(model::Identity{account:format!("owned-{i}"),database:i+1,name:format!("player_{i}")},i as u32+1).unwrap();}
        assert_ne!(enemy.team(0).unwrap(),enemy.team(1).unwrap());
        assert_eq!(wire::postmortem_camera(&enemy,1,wire::vehicle_id(0).unwrap()).unwrap(),wire::PostmortemCamera::Refused);
        assert_eq!(wire::postmortem_camera(&enemy,0,wire::vehicle_id(2).unwrap()).unwrap(),wire::PostmortemCamera::Ally(2));
        assert_eq!(wire::postmortem_camera(&enemy,0,wire::vehicle_id(0).unwrap()).unwrap(),wire::PostmortemCamera::Own);
        assert_eq!(wire::postmortem_camera(&enemy,0,0).unwrap(),wire::PostmortemCamera::Unbind);
        assert_eq!(wire::postmortem_camera(&enemy,0,wire::vehicle_id(3).unwrap()).unwrap(),wire::PostmortemCamera::Refused);
        enemy.actors[1].health=0; b.shared.as_mut().unwrap().view=Some(enemy.clone());
        let before=b.rx; b.receive(&frame(&b,&bind(wire::vehicle_id(0).unwrap())),now).unwrap(); assert_eq!(b.rx,before+1);
        b.receive(&frame(&b,&[]),now).unwrap(); assert_eq!(b.rx,before+2);
        assert!(b.shared.as_ref().unwrap().commands.is_empty());
        // Malformed mailbox/length still fails closed.
        let mut bad=bind(wire::vehicle_id(0).unwrap()); bad[4]=1;
        let before=b.rx; assert!(b.receive(&frame(&b,&bad),now).is_err()); assert_eq!(b.rx,before);
    }
    #[test] fn integrated_native_gate_keeps_account_session_alive_until_worker_ready() {
        let now = Instant::now();
        let (mut s, mut world) = driving(now);
        s.arena_base = false;
        s.base_peer = Some(peer(34001));
        s.sync_mask = 7;
        let client = s.shared.as_mut().unwrap();
        client.phase = Phase::Account;
        client.hangar_since = Some(now - Duration::from_secs(3));

        // A settling worker must not trigger the native arena reset yet.
        poll_with_native_start(&mut s, &mut world, now, false).unwrap();
        assert_eq!(s.shared.as_ref().unwrap().phase, Phase::Account);

        // Once both workers are ready, the same session may enter the arena.
        poll_with_native_start(&mut s, &mut world, now, true).unwrap();
        assert_eq!(s.shared.as_ref().unwrap().phase, Phase::Enable);
    }
    #[test] fn native_aim_is_owned_atomic_and_published_from_one_server_state() {
        let now=Instant::now();let (mut a,mut b,mut w)=visible_pair(now);
        let input=point(1,[100.,100.,100.]);
        assert!(a.receive(&frame(&a,&input),now).is_err());
        let mut poison=vec![0x88,0,0];poison.extend(point(0,[f32::NAN,0.,0.]));
        assert!(a.receive(&frame(&a,&poison),now).is_err());assert!(a.shared.as_ref().unwrap().commands.is_empty());
        let packet=frame(&b,&input);b.receive(&packet,now).unwrap();poll(&mut b,&mut w,now).unwrap();
        assert_eq!(w.actors[1].aim.yaw,0.);assert_eq!(w.actors[0].aim,super::super::aim::State::new());
        b.receive(&packet,now).unwrap();assert!(b.shared.as_ref().unwrap().commands.is_empty());
        w.advance(now+model::STEP).unwrap();poll(&mut a,&mut w,now+model::STEP).unwrap();poll(&mut b,&mut w,now+model::STEP).unwrap();
        assert!(w.actors[1].aim.yaw>0.);assert!(w.actors[1].aim.yaw<=super::super::aim::YAW_RATE*0.101);
        let expected=wire::publication(&w,[true,true]).unwrap();
        for s in [&a,&b] {assert!(queued_bodies(s,now+model::STEP).contains(&expected));}
    }
    #[test] fn startup_target_waits_for_correction_and_rejoin_holds_actual_angles() {
        let now=Instant::now();let (mut a,_,mut w)=visible_pair(now);
        a.shared.as_mut().unwrap().correction=false;w.actors[0].ready=false;
        a.receive(&frame(&a,&point(0,[100.,100.,100.])),now).unwrap();poll(&mut a,&mut w,now).unwrap();
        w.advance(now+model::STEP).unwrap();assert_eq!(w.actors[0].aim.yaw,0.);
        a.receive(&frame(&a,&[6]),now+model::STEP).unwrap();poll(&mut a,&mut w,now+model::STEP).unwrap();
        w.advance(now+model::STEP*2).unwrap();let pose=(w.actors[0].aim.yaw,w.actors[0].aim.pitch);
        assert!(pose.0>0.);w.detach(1).unwrap();w.advance(now+model::STEP*3).unwrap();
        w.attach(w.actors[0].identity.clone(),3).unwrap();w.set_ready(0,3).unwrap();w.advance(now+model::STEP*4).unwrap();
        assert_eq!((w.actors[0].aim.yaw,w.actors[0].aim.pitch),pose);
        assert!(w.apply(0,1,&[model::Command::Aim(super::super::aim::Intent::Point([0.;3]))],now+model::STEP*4).is_err());
    }
    #[test] fn native_aim_before_binding_ack_is_queued_until_correction() {
        let now=Instant::now();let (mut s,_,_)=visible_pair(now);
        let c=s.shared.as_mut().unwrap();c.correction=false;c.binding=None;
        s.receive(&frame(&s,&point(0,[100.,100.,100.])),now).unwrap();
        assert!(!s.shared.as_ref().unwrap().correction);
        assert!(s.shared.as_ref().unwrap().binding.is_none());
        assert_eq!(s.shared.as_ref().unwrap().commands.len(),1);
    }
    #[test] fn backpressure_does_not_enqueue_a_history_of_aim_poses() {
        let now=Instant::now();let (mut a,_,mut w)=visible_pair(now);
        for _ in 0..4 {a.tx.enqueue_body(&[19]).unwrap();}
        for n in 1..30 {w.advance(now+model::STEP*n).unwrap();poll(&mut a,&mut w,now+model::STEP*n).unwrap();}
        assert_eq!(a.tx.len(),4);assert!(a.outbox.is_empty());
    }
    #[test] fn accepted_native_shot_reaches_each_known_vehicle_once_with_private_ammo() {
        let now=Instant::now(); let (mut a,mut b,mut w)=visible_pair(now);
        let shot=frame(&a,&[0x88,0,0]); a.receive(&shot,now).unwrap();
        poll(&mut a,&mut w,now).unwrap(); poll(&mut b,&mut w,now).unwrap();
        assert_eq!(w.actors[0].fire.ammo(),19); assert_eq!(w.actors[1].fire.ammo(),20);
        assert_eq!(w.shots.len(),1);
        // Duplicate reliable input and another publication pass emit no event.
        a.receive(&shot,now).unwrap(); poll(&mut a,&mut w,now).unwrap(); poll(&mut b,&mut w,now).unwrap();
        let cue=wire::shooting(0).unwrap();
        let tracer=wire::tracer_start(&w.projectiles[0]).unwrap();
        assert_eq!(queued_bodies(&a,now).iter().filter(|body| **body==cue).count(),1);
        assert_eq!(queued_bodies(&b,now),vec![cue.clone(),tracer.clone()]);
        let rejected=frame(&a,&[0x88,0,0]);a.receive(&rejected,now).unwrap();poll(&mut a,&mut w,now).unwrap();
        assert_eq!(w.shots.len(),1);
        b.receive(&frame(&b,&[0x88,0,0]),now).unwrap();poll(&mut b,&mut w,now).unwrap();poll(&mut a,&mut w,now).unwrap();
        assert_eq!(w.shots.len(),2);
        for s in [&a,&b] {assert_eq!(queued_bodies(s,now).iter().filter(|body| **body==wire::shooting(1).unwrap()).count(),1);}
    }
    #[test] fn server_owned_flight_stops_each_delivered_tracer_once() {
        let now=Instant::now(); let (mut a,mut b,mut w)=visible_pair(now);
        a.receive(&frame(&a,&[0x88,0,0]),now).unwrap();
        poll(&mut a,&mut w,now).unwrap(); poll(&mut b,&mut w,now).unwrap();
        let end=w.projectiles[0].end_at().unwrap();
        w.advance(end + Duration::from_millis(100)).unwrap();
        assert!(w.projectiles[0].stopped);
        poll(&mut a,&mut w,end + Duration::from_millis(100)).unwrap();
        poll(&mut b,&mut w,end + Duration::from_millis(100)).unwrap();
        let stop=wire::tracer_stop(&w.projectiles[0]).unwrap();
        for s in [&a,&b] { assert_eq!(queued_bodies(s,end).iter().filter(|body| **body==stop).count(),1); }
        poll(&mut a,&mut w,end + Duration::from_millis(200)).unwrap();
        poll(&mut b,&mut w,end + Duration::from_millis(200)).unwrap();
        for s in [&a,&b] { assert_eq!(queued_bodies(s,end + Duration::from_millis(200)).iter().filter(|body| **body==stop).count(),1); }
    }
    #[test] fn projectile_continues_after_shooter_disconnect_and_rejoin_does_not_replay() {
        let now=Instant::now(); let (mut a,_,mut w)=visible_pair(now);
        a.receive(&frame(&a,&[0x88,0,0]),now).unwrap(); poll(&mut a,&mut w,now).unwrap();
        let start_body = wire::tracer_start(&w.projectiles[0]).unwrap();
        let end=w.projectiles[0].end_at().unwrap();
        w.detach(1).unwrap();
        w.advance(end + Duration::from_millis(100)).unwrap();
        assert!(w.projectiles[0].stopped);
        w.attach(w.actors[0].identity.clone(),3).unwrap();
        let (mut rejoin,_) = driving(now); rejoin.id=3;
        let c=rejoin.shared.as_mut().unwrap(); c.phase=Phase::Entities; c.correction=false;
        c.binding=None; c.creations=[Some((0,true));model::MAX_ACTORS]; c.view=Some(w.clone());
        let ready=[0x0d,8,0,0,0,0,0,3,0,16,9,0x8d,5,0,2,1,0,0,0,0x86,0,0,0x0c,8,0,0,0,0,0,0,0,0,0];
        rejoin.receive(&frame(&rejoin,&ready),end + Duration::from_millis(100)).unwrap();
        poll(&mut rejoin,&mut w,end + Duration::from_millis(100)).unwrap();
        assert_eq!(rejoin.shared.as_ref().unwrap().shot_cursor,1);
        let bodies = queued_bodies(&rejoin,end + Duration::from_millis(100));
        assert!(bodies.iter().all(|body| *body != start_body));
    }
    #[test] fn contact_before_peer_poll_still_delivers_start_then_stop_once() {
        let now = Instant::now(); let (mut a, mut b, _) = visible_pair(now);
        let mut w = model::tests::collision_world(now, false);
        a.shared.as_mut().unwrap().view = Some(w.clone());
        b.shared.as_mut().unwrap().view = Some(w.clone());
        a.receive(&frame(&a, &[0x88,0,0]), now).unwrap(); poll(&mut a, &mut w, now).unwrap();
        w.advance(now+model::STEP).unwrap(); assert_eq!(w.contacts.len(),1);
        // Receiver has not polled since before launch; first observation is terminal.
        poll(&mut b, &mut w, now+model::STEP).unwrap();
        let start = wire::tracer_start(&w.projectiles[0]).unwrap();
        let stop = wire::tracer_stop(&w.projectiles[0]).unwrap();
        let bodies = queued_bodies(&b,now+model::STEP);
        assert!(bodies.iter().position(|b| *b==start).unwrap() < bodies.iter().position(|b| *b==stop).unwrap());
        poll(&mut b, &mut w, now+model::STEP).unwrap();
        let bodies = queued_bodies(&b,now+model::STEP);
        assert_eq!(bodies.iter().filter(|b| **b==start).count(),1);
        assert_eq!(bodies.iter().filter(|b| **b==stop).count(),1);
    }
    #[test] fn projectile_creation_failure_rolls_back_fire_ammo_and_history() {
        let now=Instant::now(); let (_,_,mut w)=visible_pair(now);
        let before=w.clone();
        w.actors[0].aim.yaw=f32::NAN;
        assert!(w.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).is_err());
        assert_eq!(w.actors[0].fire,before.actors[0].fire);
        assert!(w.shots.is_empty()); assert!(w.projectiles.is_empty());
    }
    #[test] fn uncreated_vehicle_cannot_receive_a_cue_or_replay_it_after_creation() {
        let now=Instant::now();let (mut a,mut b,mut w)=visible_pair(now);
        b.shared.as_mut().unwrap().creations[0]=Some((0,false));
        a.receive(&frame(&a,&[0x88,0,0]),now).unwrap();poll(&mut a,&mut w,now).unwrap();poll(&mut b,&mut w,now).unwrap();
        assert_eq!(b.shared.as_ref().unwrap().shot_cursor,1);assert!(queued_bodies(&b,now).is_empty());
        b.shared.as_mut().unwrap().creations[0]=Some((0,true));poll(&mut b,&mut w,now).unwrap();
        assert!(queued_bodies(&b,now).is_empty());
        let later=now+Duration::from_secs(3);
        a.receive(&frame(&a,&[0x88,0,0]),later).unwrap();poll(&mut a,&mut w,later).unwrap();poll(&mut b,&mut w,later).unwrap();
        assert_eq!(queued_bodies(&b,later),vec![wire::shooting(0).unwrap(), wire::tracer_start(&w.projectiles[1]).unwrap()]);
    }
    #[test] fn rejoin_readiness_starts_after_past_shots_without_replay_or_ammo_grant() {
        let now=Instant::now();let (mut a,_,mut w)=visible_pair(now);
        a.receive(&frame(&a,&[0x88,0,0]),now).unwrap();poll(&mut a,&mut w,now).unwrap();
        w.detach(1).unwrap();w.attach(w.actors[0].identity.clone(),3).unwrap();
        let (mut rejoin,_) = driving(now);rejoin.id=3;
        let c=rejoin.shared.as_mut().unwrap();c.phase=Phase::Entities;c.correction=false;
        c.binding=None;c.creations=[Some((0,true));model::MAX_ACTORS];c.view=Some(w.clone());
        let ready=[0x0d,8,0,0,0,0,0,3,0,16,9,0x8d,5,0,2,1,0,0,0,0x86,0,0,0x0c,8,0,0,0,0,0,0,0,0,0];
        rejoin.receive(&frame(&rejoin,&ready),now).unwrap();poll(&mut rejoin,&mut w,now).unwrap();
        assert_eq!(rejoin.shared.as_ref().unwrap().shot_cursor,1);assert_eq!(w.actors[0].fire.ammo(),19);
        assert!(!queued_bodies(&rejoin,now).contains(&wire::shooting(0).unwrap()));
    }
    #[test] fn publication_failure_does_not_commit_shot_ammo_or_event_cursor() {
        let now=Instant::now();let (mut a,_,mut w)=visible_pair(now);
        a.receive(&frame(&a,&[0x88,0,0]),now).unwrap();
        a.outbox.push_back(vec![0;513]);
        assert!(poll(&mut a,&mut w,now).is_err());
        assert_eq!(w.actors[0].fire.ammo(),20);assert!(w.shots.is_empty());
        assert_eq!(a.shared.as_ref().unwrap().shot_cursor,0);assert_eq!(a.tx.len(),0);
    }
    #[test] fn real_channel_clone_rejects_late_poison_without_partial_input_or_ack() {
        let now = Instant::now(); let (mut s,_) = driving(now);
        let mut payload = vec![0x8a,1,0,1,3];
        payload.extend(wire::vehicle_id(1).unwrap().to_le_bytes()); payload.extend([0;17]);
        let f = frame(&s,&payload);
        assert!(s.receive(&f,now).is_err()); assert_eq!(s.rx,1);
        assert!(s.shared.as_ref().unwrap().commands.is_empty()); assert!(s.received.is_empty());
        let mut f = frame(&s,&[0x88,0,0]); f.body[1]^=1;
        assert!(s.receive(&f,now).is_err()); assert_eq!(s.rx,1);
        let mut parent = frame(&s,&[0xff]); parent.sequence=Some(2);
        parent.piggybacks.push(frame(&s,&[0x88,0,0]));
        assert!(s.receive(&parent,now).is_err()); assert_eq!(s.rx,1);
        assert!(s.shared.as_ref().unwrap().commands.is_empty());
    }
    #[test] fn reliable_shot_duplicate_consumes_once_and_cannot_move_the_other_actor() {
        let now = Instant::now(); let (mut s,mut world) = driving(now);
        let f = frame(&s,&[0x88,0,0,0x8a,1,0,1]);
        s.receive(&f,now).unwrap(); assert_eq!(s.rx,2);
        poll(&mut s,&mut world,now).unwrap(); assert_eq!(world.actors[0].fire.ammo(),19);
        s.receive(&f,now).unwrap(); poll(&mut s,&mut world,now).unwrap();
        assert_eq!(world.actors[0].fire.ammo(),19); assert_eq!(world.actors[1].fire.ammo(),20);
        assert_eq!(world.actors[1].input,model::Input::STOP);
        assert_eq!(world.actors[0].input.throttle,1);
    }
    #[test] fn second_actor_telemetry_is_checked_then_discarded() {
        let now = Instant::now(); let (mut s,world) = driving(now);
        let c=s.shared.as_mut().unwrap(); c.slot=1; c.view=Some(world);
        let mut payload=vec![3];payload.extend(wire::vehicle_id(1).unwrap().to_le_bytes());
        payload.extend(99999f32.to_le_bytes());payload.extend([0;13]);
        s.receive(&frame(&s,&payload),now).unwrap();
        assert!(s.shared.as_ref().unwrap().commands.is_empty());
        payload[1..5].copy_from_slice(&wire::vehicle_id(0).unwrap().to_le_bytes());
        assert!(s.receive(&frame(&s,&payload),now).is_err());
    }
    #[test] fn captured_native_stop_before_correction_is_atomic_and_nonzero_stays_gated() {
        let now=Instant::now();let (mut s,_)=driving(now);
        s.shared.as_mut().unwrap().correction=false;
        assert!(s.receive(&frame(&s,&[0x8a,1,0,1,6]),now).is_err());
        assert!(!s.shared.as_ref().unwrap().correction);
        s.receive(&frame(&s,&[0x8a,1,0,0,6]),now).unwrap();
        assert!(s.shared.as_ref().unwrap().correction);
        assert_eq!(s.shared.as_ref().unwrap().commands,vec![model::Command::Move(model::Input::STOP)]);
        let (mut s,_)=driving(now);let c=s.shared.as_mut().unwrap();c.correction=false;c.binding=Some((0,false));
        assert!(s.receive(&frame(&s,&[0x8a,1,0,0,6]),now).is_err());
        assert!(s.shared.as_ref().unwrap().commands.is_empty());
    }
    #[test] fn reservations_cover_all_live_sessions_before_accepting_auth() {
        let now = Instant::now(); let mut t = Table::default();
        for i in 1..31 { t.retirement.retire(LoginAttempt::new([i;16], i as u32, peer(31000 + i as u16)), None, now).unwrap(); }
        t.sessions.push(session(80, now));
        let candidate = LoginAttempt::new([81;16], 81, peer(32081)); t.admissible(&candidate, now).unwrap();
        t.sessions.push(session(81, now));
        assert!(t.admissible(&LoginAttempt::new([82;16], 82, peer(32082)), now).is_err());
        for s in &t.sessions { t.retirement.retire(s.login_attempt.unwrap(), None, now).unwrap(); }
        assert_eq!(t.retirement.retained_count(), MAX_RETIRED);
    }
    #[test] fn route_never_tries_another_key_or_rebinds_a_live_peer() {
        let now = Instant::now(); let mut t = Table::default(); t.sessions = vec![session(1,now),session(2,now)];
        t.sessions[0].base_peer = Some(peer(33001)); t.sessions[1].base_peer = Some(peer(33002));
        assert_eq!(t.route(peer(33001), &[0;24]).unwrap(), 0);
        assert_eq!(t.route(peer(33002), &[0;24]).unwrap(), 1);
        assert!(t.route(peer(33003), &[0;24]).is_err());
        let mut handshake = vec![1,0,0,8,0]; handshake.extend(1u32.to_le_bytes()); handshake.extend([0,0]);
        handshake.extend(t.sessions[1].handoff.to_le_bytes()); handshake.extend(0u32.to_le_bytes()); handshake.extend([2,0]);
        assert!(t.route(peer(33001), &handshake).is_err());
        assert!(t.route(peer(33003), &handshake).is_err());
        assert_eq!(t.route(peer(33002), &handshake).unwrap(), 1);
        assert!(base::decrypt(&base::encrypt(&transport091::ack(1), &t.sessions[0].key).unwrap(), &t.sessions[1].key).is_err());
    }
    #[test] fn retire_one_keeps_other_channel_and_rejects_its_old_attempt() {
        let now = Instant::now(); let mut world = model::tests::world(now); let mut t = Table::default();
        t.sessions = vec![session(1,now),session(2,now)]; let old = t.sessions[0].login_attempt.unwrap();
        let other = (t.sessions[1].key,t.sessions[1].token,t.sessions[1].handoff);
        t.retire(1,&mut world,now,"test_disconnect").unwrap();
        assert_eq!(t.sessions.len(),1); assert_eq!(t.sessions[0].id,2);
        assert_eq!((t.sessions[0].key,t.sessions[0].token,t.sessions[0].handoff),other);
        assert!(t.admissible(&old,now).is_err()); assert!(world.actors[0].session.is_none());
        assert_eq!(world.actors[1].session,Some(2));
    }
}

#[cfg(test)]
#[path="profile13_restart_cas_tests.rs"]
mod p08b_restart_cas_tests;

#[cfg(test)]
#[path="p08c_late_composition_tests.rs"]
mod p08c_late_composition_tests;

#[cfg(test)]
#[path="server_network_tests.rs"]
mod net02_network_tests;

#[cfg(test)]
#[path="owner_hold_composition_tests.rs"]
mod owner_hold_composition_tests;
#[cfg(test)]
#[path="owner_hold_four_composition_tests.rs"]
mod owner_hold_four_composition_tests;
#[cfg(test)]
#[path="garage_fresh_composition_tests.rs"]
mod garage_fresh_composition_tests;
