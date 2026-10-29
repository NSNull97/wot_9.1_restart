//! Explicit local bounded-multiplayer test_lab route. The accepted single-client drive
//! route and its frozen profile checks are not generalized through this module.
pub(crate) mod model;
pub(crate) mod p10b_team_plan;
pub(crate) mod team_spawn;
pub(crate) mod matchmaker;

/// One Driving record length, or None for an ID outside the #717 table.
fn record_size(payload: &[u8], at: usize) -> io::Result<Option<usize>> {
    let id = *payload.get(at).ok_or_else(|| bad())?;
    Ok(Some(match id {
        // Native clients may piggyback area requests with their first
        // aim/movement envelope after READY.  A request is the one
        // fixed seven-byte VAR2 record; it has no length field.
        8 => 7,
        6 => 1, 2 => 17, 3 => 22,
        0x87 | 0x88 | 0x89 | 0x8a | 0x8d | 0x8e | 0x8f | 0x0c | 0x0d | 0x0f | 0x99 => var2_size(payload, at)?,
        id if wire::unimplemented_exposed(id).is_some() => var2_size(payload, at)?,
        _ => return Ok(None),
    }))
}
fn var2_size(payload: &[u8], at: usize) -> io::Result<usize> {
    if payload.len() - at < 3 { return Err(bad()); }
    Ok(3 + u16::from_le_bytes([payload[at+1], payload[at+2]]) as usize)
}
/// First unframed record of a Driving envelope, mirroring the loop below:
/// an optional READY33 prefix, a READY33 suffix, at most 16 records.
fn unframed_record(payload: &[u8], own: usize) -> io::Result<Option<(usize, u8)>> {
    let mut at = if payload.get(..33).is_some_and(|prefix| wire::ready(prefix, own).is_ok()) {33} else {0};
    let mut count = 0;
    while at < payload.len() {
        count += 1; if count > 16 { return Ok(None); }
        if payload.len() - at == 33 && wire::ready(&payload[at..], own).is_ok() { return Ok(None); }
        match record_size(payload, at)? {
            Some(size) => at = at.checked_add(size).ok_or_else(|| bad())?,
            None => return Ok(Some((at, payload[at]))),
        }
    }
    Ok(None)
}
#[cfg(test)]
mod spawn15_wire_tests;
pub(crate) mod visibility;
pub(crate) mod spotting;
pub(crate) mod step_profile;
pub(crate) mod net01;
pub(crate) mod journal;
pub(crate) mod p07b_publication;
pub(crate) mod interest_wire;
pub(crate) mod ammo_detonation;
mod detached_turret;
mod turret_publication;
#[cfg(test)]
mod turret_publication_test_fixture;
pub(crate) mod lifecycle;
pub(crate) mod lifecycle_wire;
mod lifecycle_result;
mod late_results_capture;
mod late_results_protocol;
mod late_results_pending;
mod late_results_notice;
mod late_results_runtime;
mod lifecycle_details;
pub(crate) mod results_session;
pub(crate) mod aim;
pub(crate) mod pose;
pub(crate) mod geometry;
pub(crate) mod p06t_geometry_source;
pub(crate) mod materials;
pub(crate) mod client_marker;
pub(crate) mod ap;
mod account_policy;
mod impact_wire;
mod av01_feedback;
pub(crate) mod terrain;
pub(crate) mod obstacles;
mod terrain_wire;
mod destructible_wire;
pub(crate) mod destructible;
pub(crate) mod dynamic_destructible;
pub(crate) mod fragiles;
pub(crate) mod ram_response;
pub(crate) mod ram_proof;
pub(crate) mod tank_ram;
pub(crate) mod projectile;
pub(crate) mod collision;
pub(crate) mod impact;
pub(crate) mod wire;
mod server;
mod scene_runtime;
mod profile13_session;
mod owner_hold_capture;
mod p10b_writer;
mod p10b_writer_loss;
mod p10b_writer_mode;
mod p10b_selection_job;
mod profile13_queue;
mod profile13_templates;
pub use server::serve_profile13;
pub use server::run_battle_worker;
pub use server::serve_profile13_source_bundle;
pub use server::serve_curated_lab;
pub use server::serve_curated_lab_v2;
pub(crate) mod vehicle_profile;
pub(crate) mod vehicle_catalog;
pub(crate) mod generated_vehicles;
pub use server::serve;
pub use server::serve_integrated;
use super::{Session, Frame, Instant};
use std::io;
use std::collections::VecDeque;
use model::{bad, Command, Input, World};
use crate::{battle091::fire, map_drive_world091 as drive};

/// Area controllers are announced in bounded batches. Vehicle/area create
/// requests share the measured eight-body reliable window through the pending
/// queues; six actors do not enlarge that transport window.
const AREA_ANNOUNCEMENT_BATCH: usize = 6;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum Phase { Account, Enable, Entities, Driving, Leaving, Returning }

#[derive(Clone)]
struct PrivatePending {
    body: Vec<u8>,
    targets: Vec<(usize, u32)>,
}

#[derive(Clone)]
pub(super) struct Client {
    slot: usize,
    phase: Phase,
    view: Option<World>,
    // Only fault containment may retain an immutable revoked battle for Finish/result drain.
    contained_world: Option<std::sync::Arc<World>>,
    announcement: Option<(u32, bool)>,
    announcement_parts: Vec<(u32, bool)>,
    announced_areas: usize,
    creations: [Option<(u32, bool)>; model::MAX_ACTORS],
    creation_announcements: [Option<u32>; model::MAX_ACTORS],
    spotting_enabled: bool,
    interest: Option<interest_wire::Book>,
    private_pending: VecDeque<PrivatePending>,
    turrets: turret_publication::State,
    last_pose_tick: Option<u32>,
    /// NET-01: gateway.json `pose_delivery` (kept across battles, like spotting).
    pose_delivery: net01::PoseDelivery,
    /// NET-01 latest-unreliable: bodies of the newest tick's pose not sent yet.
    poses_out: Vec<Vec<u8>>,
    pose_stats: net01::PoseStats,
    binding: Option<(u32, bool)>,
    area_creation: Option<(u32, bool)>,
    pending_area_scene: bool,
    pending_entity_requests: VecDeque<usize>,
    pending_area_requests: VecDeque<usize>,
    area_scene_sent: u32,
    areas:Vec<(Option<(u32,bool)>,Vec<u8>)>,
    tree_areas:Vec<Vec<u32>>,
    /// MAPS-02 cumulative fallenColumns already queued per area.
    column_areas:Vec<Vec<u16>>,
    correction: bool,
    ready_sent: [bool; model::MAX_ACTORS],
    commands: Vec<Command>,
    entered: Option<Instant>,
    hangar_since: Option<Instant>,
    shot_cursor: u32,
    impact_cursor: usize,
    sixth_sense_sent: u32,
    damage_cursor:usize,
    ram_cursor:usize,
    device_cursor:usize,
    crew_sent:[Option<bool>;model::MAX_ACTORS],
    fire_sent:[Option<bool>;model::MAX_ACTORS],
    armament_sent:Option<([u16;3],u16,u16,u8,Option<Instant>,u32)>,
    devices_snapshot_sent:bool,
    health_sent: [Option<i16>; model::MAX_ACTORS],
    owner_health_sent: Option<i16>,
    tracer_started: [bool; model::MAX_BATTLE_SHOTS],
    tracer_stopped: [bool; model::MAX_BATTLE_SHOTS],
    /// AV-01: last engineMode / damageStickers queued per created vehicle
    /// (None: unknown to the client, publish the current value), and the
    /// scout-event cursor.
    engine_sent: [Option<[u8; 2]>; model::MAX_ACTORS],
    stickers_sent: [Option<Vec<u64>>; model::MAX_ACTORS],
    scout_cursor: usize,
    return_generation: u32,
    return_mask: u8,
    join_requested: bool,
    queue_announced: bool,
    profile13: Option<profile13_session::State>,
    return_source_revision: i64,
    lifecycle_view: Option<lifecycle::View>,
    natural_result: Option<std::sync::Arc<lifecycle_wire::Results>>,
    result_committed: bool,
    result_stream_queued: bool,
    result_leave_requested: bool,
    result_delivery_at: Option<Instant>,
}
impl Client {
    pub(super) fn account_incarnation(&self)->u64{u64::from(self.return_generation)+1}
    fn new(slot: usize) -> Self {
        Self { slot, phase: Phase::Account, view: None, contained_world: None, announcement: None, announcement_parts: Vec::new(), announced_areas: 0, creations: [None; model::MAX_ACTORS],
            creation_announcements: [None; model::MAX_ACTORS], spotting_enabled: false, interest: None,
            private_pending: VecDeque::new(), turrets:turret_publication::State::new(), last_pose_tick: None,
            pose_delivery: net01::PoseDelivery::Reliable, poses_out: Vec::new(), pose_stats: net01::PoseStats::default(),
            area_creation: None, pending_area_scene: false, pending_entity_requests: VecDeque::new(), pending_area_requests: VecDeque::new(), area_scene_sent: 0,areas:Vec::new(),tree_areas:Vec::new(),column_areas:Vec::new(), binding: None, correction: false, ready_sent: [false; model::MAX_ACTORS], commands: Vec::new(), entered: None,
            hangar_since: None, shot_cursor: 0, impact_cursor: 0, sixth_sense_sent: 0, damage_cursor:0,ram_cursor:0,device_cursor:0,crew_sent:[None;model::MAX_ACTORS],fire_sent:[None;model::MAX_ACTORS],armament_sent:None,devices_snapshot_sent:false,health_sent: [None; model::MAX_ACTORS], owner_health_sent: None, tracer_started: [false; model::MAX_BATTLE_SHOTS],
            tracer_stopped: [false; model::MAX_BATTLE_SHOTS], engine_sent: [None; model::MAX_ACTORS], stickers_sent: std::array::from_fn(|_| None), scout_cursor: 0, return_generation: 0, return_mask: 0, join_requested: true, queue_announced: false, profile13: None, return_source_revision: 1, lifecycle_view: None, natural_result: None, result_committed: false, result_stream_queued: false, result_leave_requested: false, result_delivery_at: None }
    }
    /// A new battle gets fresh entity/publication state while the Account
    /// return epoch remains monotonic on its existing authenticated channel.
    fn reset_for_battle(&mut self, slot: usize) {
        let generation = self.return_generation;
        let queue_announced = self.queue_announced;
        let profile13 = self.profile13.take();
        let return_source_revision = self.return_source_revision;
        let spotting_enabled = self.spotting_enabled;
        let pose_delivery = self.pose_delivery;
        *self = Self::new(slot);
        self.pose_delivery = pose_delivery;
        self.return_generation = generation;
        self.queue_announced = queue_announced;
        self.profile13 = profile13;
        self.return_source_revision = return_source_revision;
        self.spotting_enabled = spotting_enabled;
        // An invalid owner remains a checked error at refresh/enable, rather
        // than a process panic during a battle reset.
        if spotting_enabled { self.interest = interest_wire::Book::new(slot).ok(); }
    }
    pub(super) fn profile13_garage_idle(&self) -> bool {
        self.phase == Phase::Account && self.profile13.as_ref().is_some_and(|s| s.garage_idle())
    }
    pub(super) fn profile13_account(&self) -> bool {self.phase==Phase::Account && self.profile13.is_some()}
    /// Candidate32: only the idle garage durable cursor changes here. The
    /// enclosing Session clone also publishes its actual fresh cache +0x57.
    pub(super) fn commit_garage_source_revision(&mut self,old:u64,next:u64)->io::Result<()> {
        let state=self.profile13.as_mut().ok_or_else(bad)?;
        if self.phase!=Phase::Account||!state.garage_idle()||state.revision!=old
            ||next!=old.checked_add(1).ok_or_else(bad)?||next>=i32::MAX as u64
            ||state.hold_projection.is_some(){return Err(bad());}
        state.revision=next;Ok(())
    }
    pub(super) fn profile13_arena_ready(&self) -> bool {
        self.profile13.as_ref().is_some_and(|s| s.has_reservation() && !s.in_flight && !s.has_pending_return())
    }
    pub(super) fn acknowledge(&mut self, cumulative: u32, frame: &Frame) -> io::Result<()> {
        self.turrets.book.ack(cumulative,&frame.selective)?;
        let cleared = match &mut self.interest {
            Some(book) => book.acknowledge(cumulative, &frame.selective)?,
            None if self.spotting_enabled => return Err(bad()),
            None => Vec::new(),
        };
        for slot in cleared { self.clear_creation(slot); }
        for pending in [&mut self.announcement, &mut self.binding, &mut self.area_creation] {
            if let Some((seq, acked)) = pending { *acked |= cumulative > *seq || frame.selective.contains(seq); }
        }
        for (seq, acked) in &mut self.announcement_parts {
            *acked |= cumulative > *seq || frame.selective.contains(seq);
        }
        if !self.announcement_parts.is_empty() {
            if let Some((_, acked)) = &mut self.announcement {
                *acked = self.announcement_parts.iter().all(|(_, acked)| *acked);
            }
        }
        for pending in &mut self.creations {if let Some((seq,acked))=pending{*acked|=cumulative>*seq||frame.selective.contains(seq);}}
        for (pending,_) in &mut self.areas{if let Some((seq,acked))=pending{*acked|=cumulative>*seq||frame.selective.contains(seq);}}
        Ok(())
    }
    fn areas_ready(&self,world:&World)->bool{
        (!world.destructible_enabled()||self.area_creation.is_some_and(|(_,ack)|ack))
            &&world.fragiles.as_ref().is_none_or(|state|self.announced_areas==state.catalog.chunks().len()&&self.areas.len()==state.catalog.chunks().len()&&(self.tree_areas.is_empty()||self.tree_areas.len()==self.areas.len())&&self.areas.iter().all(|(p,_)|p.is_some_and(|(_,a)|a)))
    }
    fn visible(&self) -> [bool; model::MAX_ACTORS] {
        std::array::from_fn(|slot| {
            let acked=self.creations[slot].is_some_and(|(_,ack)|ack);
            if !self.spotting_enabled { return acked; }
            self.interest.as_ref().is_some_and(|book| book.publish_allowed(slot,acked)
                && self.creation_announcements[slot] == book.announcement_sequence(slot))
        })
    }
    pub(super) fn set_pose_delivery(&mut self, mode: net01::PoseDelivery) -> io::Result<()> {
        // Like spotting: chosen before a battle; unreliable poses need the AoI book.
        if self.phase!=Phase::Account || mode==net01::PoseDelivery::LatestUnreliable && !self.spotting_enabled { return Err(bad()); }
        self.pose_delivery=mode;Ok(())
    }
    pub(super) fn pose_delivery(&self) -> net01::PoseDelivery { self.pose_delivery }
    /// Bodies of the newest unsent pose; empty unless latest-unreliable.
    pub(super) fn take_poses(&mut self) -> Vec<Vec<u8>> { std::mem::take(&mut self.poses_out) }
    pub(super) fn take_pose_stats(&mut self) -> net01::PoseStats { std::mem::take(&mut self.pose_stats) }
    pub(super) fn record_pose_packet(&mut self, bytes: usize) { self.pose_stats.packets+=1; self.pose_stats.bytes+=bytes as u64; }
    pub(super) fn in_battle(&self) -> bool { matches!(self.phase, Phase::Driving | Phase::Leaving) }
    pub(super) fn enable_spotting(&mut self) -> io::Result<()> {
        // Enable only before a battle; replacing a live book would unpair AoI.
        if self.phase!=Phase::Account || self.creations.iter().any(Option::is_some) { return Err(bad()); }
        let book=interest_wire::Book::new(self.slot)?;
        self.spotting_enabled=true;self.interest=Some(book);Ok(())
    }
    fn clear_creation(&mut self, slot:usize) {
        self.creations[slot]=None;self.creation_announcements[slot]=None;self.health_sent[slot]=None;self.ready_sent[slot]=false;
        self.crew_sent[slot]=None;self.fire_sent[slot]=None;self.engine_sent[slot]=None;self.stickers_sent[slot]=None;
        self.pending_entity_requests.retain(|pending|*pending!=slot);
        let pending=std::mem::take(&mut self.private_pending);
        for p in pending {
            if p.targets.iter().any(|(target,_)|*target==slot) {self.invalidate_private(&p);}
            else {self.private_pending.push_back(p);}
        }
    }
    fn invalidate_private(&mut self, pending:&PrivatePending) {
        // A discarded compound can carry HP for a still-visible victim while
        // its attacker vanished. Rebuild HP, crew/fire and owner device state;
        // a quick LOS flap may preserve the same native announcement epoch.
        for &(slot,_) in &pending.targets {
            self.health_sent[slot]=None;
            self.crew_sent[slot]=None;self.fire_sent[slot]=None;self.engine_sent[slot]=None;self.stickers_sent[slot]=None;
            if slot==self.slot {self.owner_health_sent=None;self.devices_snapshot_sent=false;}
        }
    }
    fn request_allowed(&self, slot:usize)->bool {
        !self.spotting_enabled || self.interest.as_ref().is_some_and(|book|book.request_allowed(slot))
    }
    fn mark_announced(&mut self, slots:&[usize], sequence:u32)->io::Result<()> {
        if !self.spotting_enabled {return Ok(());}
        for &slot in slots {
            let action=self.interest.as_ref().ok_or_else(||bad())?.transitions().into_iter()
                .find(|a|a.slot==slot && a.kind==interest_wire::Kind::Enter).ok_or_else(||bad())?;
            self.interest.as_mut().ok_or_else(||bad())?.mark_queued(action,sequence)?;
            self.clear_creation(slot);
        }
        Ok(())
    }
    fn private_current(&self, pending:&PrivatePending)->bool {
        let visible=self.visible();
        pending.targets.iter().all(|&(slot,epoch)|visible.get(slot)==Some(&true)
            && self.interest.as_ref().and_then(|b|b.announcement_sequence(slot))==Some(epoch))
    }
    pub(super) fn pending_private_len(&self)->usize {self.private_pending.len()}
    pub(super) fn queue_private(&mut self, outbox:&mut VecDeque<Vec<u8>>, body:Vec<u8>, targets:&[usize])->io::Result<()> {
        if !self.spotting_enabled {outbox.push_back(body);return Ok(());}
        if body.is_empty() || body.len()>512 || targets.is_empty() || targets.len()>model::MAX_ACTORS
            || self.private_pending.len()>=model::MAX_BATTLE_SHOTS*4+32 {return Err(bad());}
        let visible=self.visible();let book=self.interest.as_ref().ok_or_else(||bad())?;
        let mut epochs=Vec::with_capacity(targets.len());
        for &slot in targets {
            if visible.get(slot)!=Some(&true) || epochs.iter().any(|(target,_)|*target==slot) {return Err(bad());}
            epochs.push((slot,book.announcement_sequence(slot).ok_or_else(||bad())?));
        }
        self.private_pending.push_back(PrivatePending{body,targets:epochs});Ok(())
    }
    pub(super) fn refresh_interest(&mut self, world:&World)->io::Result<()> {
        if !self.spotting_enabled {return Ok(());}
        let desired=world.desired_visibility(self.slot)?;
        let active=std::array::from_fn(|slot|slot<world.actors.len());
        let mut book=self.interest.clone().ok_or_else(||bad())?;
        book.set_desired(active,desired)?;
        let mut abandoned=Vec::new();
        for p in &world.projectiles {
            if p.slot>=model::MAX_ACTORS {return Err(bad());}
            if !desired[p.slot] {
                let index=p.sequence.checked_sub(1).ok_or_else(||bad())? as usize;
                if index>=self.tracer_started.len() {return Err(bad());}abandoned.push(index);
            }
        }
        self.interest=Some(book);
        self.pending_entity_requests.retain(|slot|self.interest.as_ref().is_some_and(|b|b.request_allowed(*slot)));
        let pending=std::mem::take(&mut self.private_pending);
        for p in pending {
            if self.private_current(&p) {self.private_pending.push_back(p);}
            else {self.invalidate_private(&p);}
        }
        for index in abandoned {self.tracer_started[index]=false;self.tracer_stopped[index]=true;}
        Ok(())
    }
    pub(super) fn needs_flush(&self) -> bool { matches!(self.phase, Phase::Entities | Phase::Driving) }
}

impl Session {
    /// Refresh from the committed authoritative world, independently of any
    /// inbound packet. No native queue or ACK changes escape this clone.
    pub(super) fn shared_refresh_world(&mut self, world:&World)->io::Result<()> {
        let Some(c)=self.shared.as_ref() else{return Ok(());};
        let terminal=c.phase==Phase::Leaving&&world.ammo_detonation_enabled();
        if !c.spotting_enabled || !(terminal||matches!(c.phase,Phase::Enable|Phase::Entities|Phase::Driving)) {return Ok(());}
        if terminal {
            let actor=world.actors.get(c.slot).ok_or_else(||bad())?;
            let owner=self.identity.as_ref().ok_or_else(||bad())?;
            if c.view.as_ref().is_none_or(|old|old.id!=world.id)||actor.identity.account!=owner.account_id
                ||actor.identity.database!=owner.database_id||actor.session.is_some_and(|id|id!=self.id){return Err(bad());}
        }else{world.owned(c.slot,self.id)?;}
        let mut next=self.clone();let c=next.shared.as_mut().ok_or_else(||bad())?;
        c.refresh_interest(world)?;c.view=Some(world.clone());*self=next;Ok(())
    }
    pub(super) fn flush_shared_private(&mut self)->io::Result<()> {
        if self.shared.as_ref().is_none_or(|c|!c.spotting_enabled) || !self.outbox.is_empty() {return Ok(());}
        let mut next=self.clone();
        while next.tx.len()<8 {
            let c=next.shared.as_mut().ok_or_else(||bad())?;
            let Some(pending)=c.private_pending.pop_front() else{break;};
            let terminal=c.phase==Phase::Leaving&&c.view.as_ref().is_some_and(|w|w.ammo_detonation_enabled());
            if !(terminal||matches!(c.phase,Phase::Entities|Phase::Driving)) || !c.private_current(&pending) {c.invalidate_private(&pending);continue;}
            next.tx.enqueue_body(&pending.body)?;
        }
        *self=next;Ok(())
    }
    pub(super) fn flush_shared_interest(&mut self, events:&mut Vec<String>)->io::Result<()> {
        let Some(c)=self.shared.as_ref() else{return Ok(());};
        if !c.spotting_enabled || !matches!(c.phase,Phase::Entities|Phase::Driving) || !self.outbox.is_empty() {return Ok(());}
        let mut next=self.clone();let mut committed=Vec::new();
        let actions=next.shared.as_ref().and_then(|c|c.interest.as_ref()).ok_or_else(||bad())?.transitions();
        for action in actions {
            if next.tx.len()>=8 {break;}
            let body=match action.kind {
                interest_wire::Kind::Enter=>wire::enter_vehicle(action.slot)?,
                interest_wire::Kind::Leave=>wire::leave_vehicle(action.slot)?,
            };
            let sequence=next.tx.enqueue_body_tracked(&body)?;
            let c=next.shared.as_mut().ok_or_else(||bad())?;
            c.interest.as_mut().ok_or_else(||bad())?.mark_queued(action,sequence)?;
            c.clear_creation(action.slot);
            committed.push(format!("P07B_INTEREST session={} slot={} action={:?} sequence={sequence}",next.id,action.slot,action.kind));
        }
        *self=next;events.extend(committed);Ok(())
    }
    pub(super) fn shared_account_response(&self,request:&crate::account091::Request,events:&mut Vec<String>)->io::Result<Vec<Vec<u8>>> {
        if self.shared.is_none() || request.command!=100 {return Err(bad());}
        if self.shared.as_ref().is_some_and(|c|c.profile13.is_some()) {
            events.push(format!("P08B_ACCOUNT_FULL session={} request={} source=confirmed_owner_projection",self.id,request.id));
            return crate::hangar091::response(request,self.hangar.as_ref().ok_or_else(||bad())?);
        }
        let (bodies,event)=account_policy::response(self.identity.as_ref().ok_or_else(||bad())?,
            self.hangar.as_ref().ok_or_else(||bad())?,request,self.id)?;
        events.push(event);Ok(bodies)
    }
    fn shared_start(&mut self, world: &World, now: Instant) -> io::Result<()> {
        if !self.ready_for_arena_base() { return Err(bad()); }
        let slot = self.shared.as_ref().filter(|c| c.phase == Phase::Account).ok_or_else(|| bad())?.slot;
        world.owned(slot, self.id)?;
        let mut next = self.clone();
        next.tx.enqueue_body(&wire::reset(world, slot)?)?; next.arena_base = true;
        next.drive_return_account = None;
        let c = next.shared.as_mut().ok_or_else(|| bad())?;
        c.return_generation = c.return_generation.checked_add(1).ok_or_else(|| bad())?;
        c.phase = Phase::Enable; c.view = Some(world.clone()); c.entered = Some(now);
        c.queue_announced = false;
        c.shot_cursor = world.latest_shot();
        c.impact_cursor = world.impacts.len();
        c.sixth_sense_sent = world.sixth_sense_generation(c.slot)?;
        c.damage_cursor=world.damage_events.len();c.ram_cursor=world.ram_damage_events.len();c.device_cursor=world.device_events.len();
        c.tracer_started = [false; model::MAX_BATTLE_SHOTS];
        c.tracer_stopped = [false; model::MAX_BATTLE_SHOTS];
        *self = next;
        println!("SHARED_ENTRY battle={} session={} slot={slot} avatar={} vehicle={} assignment={} inventory_reserved={}",
            world.id,self.id,wire::avatar_id(slot)?,wire::vehicle_id(slot)?,
            if self.shared.as_ref().is_some_and(|c|c.profile13.is_some()) {"confirmed_owned_loadout"} else {"temporary_server_selected"},
            self.shared.as_ref().is_some_and(|c|c.profile13.is_some()));
        Ok(())
    }
    pub(super) fn shared_return(&mut self, reason: &str, now: Instant, events: &mut Vec<String>) -> io::Result<()> {
        let c = self.shared.as_ref().ok_or_else(|| bad())?;
        if !self.active || !self.account_ready || !self.arena_base || self.sync_mask != 7
            || !matches!(c.phase, Phase::Enable | Phase::Entities | Phase::Driving | Phase::Leaving)
            || c.return_generation == 0 || self.outbox.len() >= 128 { return Err(bad()); }
        let body = drive::return_account(&self.identity.as_ref().ok_or_else(|| bad())?.name)?;
        let generation = c.return_generation;
        let mut next = self.clone();
        // The historical field name is retained: its queue/ACK tracking is a
        // transport contract shared with the ordinary single-player return.
        next.drive_return_account = Some(super::WarmAccountReturn { generation,
            queue_ahead: next.outbox.len(), creation: None, enabled: false, stale_avatar_envelopes: 0 });
        next.battle_results.begin_account_epoch()?;
        next.outbox.push_back(body);
        next.arena_base = false;
        let c = next.shared.as_mut().ok_or_else(|| bad())?;
        c.phase = Phase::Returning; c.contained_world = None; c.return_mask = 0; c.join_requested = false; c.queue_announced = false;
        c.hangar_since = None; c.entered = Some(now); c.commands.clear();
        c.pending_entity_requests.clear(); c.pending_area_requests.clear(); c.pending_area_scene = false;
        c.private_pending.clear();
        // Keep the old view and binding solely to validate already queued
        // Avatar envelopes. No authoritative command can leave Returning.
        next.drain_outbox()?;
        *self = next;
        events.push(format!("SHARED_RETURN session={} generation={generation} reason={reason} channel_reused=true account_recreated=true inventory_changed=false", self.id));
        Ok(())
    }

    fn shared_account_payload(&mut self, payload: &[u8], events: &mut Vec<String>) -> io::Result<()> {
        if self.shared.as_ref().is_some_and(|c| c.profile13.is_some()) {
            return self.profile13_account_payload(payload,events);
        }
        if payload.len() > 512 { return Err(bad()); }
        let mut at = 0; let mut count = 0;
        let mut records = Vec::new(); let mut has_queue_command = false;
        while at < payload.len() {
            count += 1;
            if count > 16 || payload.len() - at < 3 { return Err(bad()); }
            let len = u16::from_le_bytes([payload[at+1], payload[at+2]]) as usize;
            let packet = payload.get(at..at+3+len).ok_or_else(|| bad())?;
            at += packet.len();
            has_queue_command |= drive::account_command(packet)?.is_some();
            records.push(packet);
        }
        // Preserve the existing whole-bundle Account validation, including
        // its duplicate-command rules, whenever no queue RPC is present.
        if !has_queue_command { return self.receive_account(payload, events); }
        for packet in records {
            let Some(command) = drive::account_command(packet)? else {
                self.receive_account(packet, events)?;
                continue;
            };
            let c = self.shared.as_mut().ok_or_else(|| bad())?;
            if !self.active || !self.account_ready || self.arena_base || self.sync_mask != 7
                || c.phase != Phase::Account || self.outbox.len() >= 128 { return Err(bad()); }
            match command {
                drive::AccountCommand::Join => {
                    c.join_requested = true; c.queue_announced = true;
                    self.outbox.push_back(drive::queue_callback(true));
                },
                drive::AccountCommand::Cancel => {
                    c.join_requested = false; c.queue_announced = false;
                    self.outbox.push_back(drive::queue_callback(false));
                },
                drive::AccountCommand::QueueInfo => {
                    if !c.join_requested { return Err(bad()); }
                    self.outbox.push_back(drive::own_queue_info());
                },
            }
            events.push(format!("SHARED_QUEUE session={} command={command:?} join_requested={} assignment=temporary_server_selected inventory_changed=false", self.id, c.join_requested));
        }
        Ok(())
    }

    fn shared_return_payload(&mut self, payload: &[u8], sequence: u32, now: Instant, events: &mut Vec<String>) -> io::Result<()> {
        let c = self.shared.as_ref().ok_or_else(|| bad())?;
        let warm = self.drive_return_account.as_ref().ok_or_else(|| bad())?;
        if !self.active || !self.account_ready || self.arena_base || self.base_peer.is_none()
            || self.sync_mask != 7 || c.phase != Phase::Returning || c.join_requested
            || c.return_generation != warm.generation { return Err(bad()); }
        if payload.is_empty() { return Ok(()); }
        if payload[0] != 9 && !warm.enabled {
            if warm.stale_avatar_envelopes >= 32 { return Err(bad()); }
            // Validate the complete measured shared Avatar namespace, including
            // slot1 IDs and postmortem/area records, on a throwaway clone. The
            // outer receive transaction commits only this bounded drain count.
            let mut retired = self.clone();
            retired.shared.as_mut().ok_or_else(|| bad())?.phase = Phase::Driving;
            retired.shared_payload(payload, sequence, now, &mut Vec::new())?;
            let warm = self.drive_return_account.as_mut().ok_or_else(|| bad())?;
            warm.stale_avatar_envelopes += 1;
            events.push(format!("SHARED_RETIRED_AVATAR_DRAIN session={} generation={} sequence={sequence} payload_bytes={} envelopes={} domain_applied=false", self.id, warm.generation, payload.len(), warm.stale_avatar_envelopes));
            return Ok(());
        }
        if payload.len() > 512 { return Err(bad()); }
        let mut at = 0; let mut count = 0; let mut seen = Vec::new();
        while at < payload.len() {
            count += 1;
            if count > 16 { return Err(bad()); }
            if payload[at] == 9 {
                let warm = self.drive_return_account.as_ref().ok_or_else(|| bad())?;
                let (reset_sequence, acked) = warm.creation.ok_or_else(|| bad())?;
                let c = self.shared.as_ref().ok_or_else(|| bad())?;
                if warm.enabled || !acked || c.phase != Phase::Returning || c.return_mask != 0
                    || c.return_generation != warm.generation { return Err(bad()); }
                self.request_ids.clear(); self.unsupported_request_ids.clear(); self.chat_request_ids.clear();
                self.drive_return_account.as_mut().ok_or_else(|| bad())?.enabled = true;
                events.push(format!("SHARED_ACCOUNT_ENABLED session={} generation={} client_sequence={sequence} reset_sequence={reset_sequence} reset_acked=true chat_epoch_reset=true", self.id, c.return_generation));
                at += 1;
                continue;
            }
            if !self.drive_return_account.as_ref().is_some_and(|warm| warm.enabled)
                || payload.len() - at < 3 { return Err(bad()); }
            if payload[at] == 0x0d {
                // Natural elimination capture: after enableEntities the dead
                // Avatar's explicit-mailbox camera rebind may precede the
                // ordinary Account sync/chat compound in the SAME frame.
                // Keep it bounded to the retained dead epoch and do not pass
                // it to Account dispatch or restore any Avatar authority.
                let raw = payload.get(at..at+11).ok_or_else(|| bad())?;
                let c = self.shared.as_ref().ok_or_else(|| bad())?;
                let warm = self.drive_return_account.as_ref().ok_or_else(|| bad())?;
                if c.phase != Phase::Returning || c.return_mask != 0 || !c.correction
                    || !c.binding.is_some_and(|(_,acked)| acked)
                    || c.view.as_ref().and_then(|world| world.actors.get(c.slot)).is_none_or(|actor| actor.alive())
                    || c.return_generation != warm.generation
                    || !warm.creation.is_some_and(|(_,acked)| acked)
                    || warm.stale_avatar_envelopes >= 32 || seen.contains(&raw) { return Err(bad()); }
                wire::retired_postmortem_rebind(raw,c.slot)?;
                seen.push(raw); at += raw.len();
                self.drive_return_account.as_mut().ok_or_else(|| bad())?.stale_avatar_envelopes += 1;
                events.push(format!("SHARED_RETIRED_POSTMORTEM_DRAIN session={} generation={} client_sequence={sequence} authority_changed=false domain_applied=false",
                    self.id,c.return_generation));
                continue;
            }
            let len = u16::from_le_bytes([payload[at+1], payload[at+2]]) as usize;
            let packet = payload.get(at..at+3+len).ok_or_else(|| bad())?;
            at += packet.len();
            if seen.contains(&packet) { return Err(bad()); }
            seen.push(packet);
            if self.shared.as_ref().is_some_and(|c| c.phase == Phase::Returning)
                && packet.len() == 23 && packet[..3] == [0x8e, 20, 0] {
                let id = i16::from_le_bytes([packet[3], packet[4]]);
                let command = i16::from_le_bytes([packet[5], packet[6]]);
                let rev = i64::from_le_bytes(packet[7..15].try_into().map_err(|_| bad())?);
                let a = i32::from_le_bytes(packet[15..19].try_into().map_err(|_| bad())?);
                let b = i32::from_le_bytes(packet[19..23].try_into().map_err(|_| bad())?);
                if [100, 300, 600].contains(&command) {
                    let bit = crate::account091::command_bit(command);
                    if id <= 0 || self.request_ids.contains(&id) || self.request_ids.len() >= 32
                        || self.shared.as_ref().ok_or_else(|| bad())?.return_mask & bit != 0 { return Err(bad()); }
                    let request = crate::account091::Request { id, command };
                    match command {
                        100 => {
                            let expected=self.shared.as_ref().filter(|c|c.profile13.is_some()).map_or(1,|c|c.return_source_revision);
                            if rev != expected || b != 0 { return Err(bad()); }
                            let bodies=self.shared_account_response(&request,events)?;
                            if self.outbox.len()+bodies.len()>127 {return Err(bad());}
                            self.account_cache_hash = if a == 0 { None } else { Some(a) };
                            self.outbox.extend(bodies);
                        },
                        300 => {
                            let fixtures = self.hangar.as_ref().ok_or_else(|| bad())?;
                            fixtures.validate_shop_cursor(rev,a,b)?;
                            let bodies = crate::hangar091::response(&request, fixtures)?;
                            if self.outbox.len() + bodies.len() > 127 { return Err(bad()); }
                            self.outbox.extend(bodies);
                        },
                        600 => {
                            if b != 0 { return Err(bad()); }
                            let fixtures = self.hangar.as_ref().ok_or_else(|| bad())?;
                            fixtures.validate_dossier_cursor(rev, a)?;
                            let bodies = crate::hangar091::response(&request, fixtures)?;
                            if self.outbox.len() + bodies.len() > 127 { return Err(bad()); }
                            self.outbox.extend(bodies);
                        },
                        _ => unreachable!(),
                    }
                    self.request_ids.push(id);
                    let c = self.shared.as_mut().ok_or_else(|| bad())?;
                    c.return_mask |= bit;
                    events.push(format!("SHARED_RETURN_SYNC session={} generation={} request={id} command={command} revision={rev} client_state_applied=false", self.id, c.return_generation));
                    if c.return_mask == 7 {
                        if self.outbox.len() >= 128 { return Err(bad()); }
                        self.outbox.push_back(crate::hangar091::show_gui(self.identity.as_ref().ok_or_else(|| bad())?.database_id)?);
                        c.phase = Phase::Account; c.entered = None; c.hangar_since = Some(now);
                        events.push(format!("SHARED_HANGAR_RETURNED session={} generation={} join_requested=false inventory_changed=false", self.id, c.return_generation));
                    }
                    continue;
                }
            }
            self.receive_account(packet, events)?;
        }
        Ok(())
    }
    pub(super) fn shared_payload(&mut self, payload: &[u8], sequence: u32, now: Instant, events: &mut Vec<String>) -> io::Result<()> {
        let mut payload = payload;
        let phase = self.shared.as_ref().ok_or_else(|| bad())?.phase;
        if phase == Phase::Returning { return self.shared_return_payload(payload, sequence, now, events); }
        if phase == Phase::Leaving && self.shared.as_ref().is_some_and(|c|c.profile13.is_some()) {
            if payload.is_empty() {return Ok(());}
            let count=self.shared.as_ref().and_then(|c|c.profile13.as_ref()).ok_or_else(||bad())?.stale_envelopes;
            // The opt-in detached visual lasts5s after terminal HP. Keep its
            // authenticated request/ACK drain bounded without the old32-frame
            // postmortem budget prematurely killing an otherwise live channel.
            let detached=self.shared.as_ref().and_then(|c|c.view.as_ref()).is_some_and(|w|w.ammo_detonation_enabled());
            if count>=if detached{240}else{32} {return Err(bad());}
            let mut retired=self.clone();
            retired.shared.as_mut().ok_or_else(||bad())?.phase=Phase::Driving;
            retired.shared_payload(payload,sequence,now,&mut Vec::new())?;
            // Only current detached-entity requests survive terminal validation.
            // World/drive commands still belong to the throwaway Avatar clone.
            if detached{
                turret_publication::retain_terminal_requests(self,payload)?;
            }
            if self.shared.as_ref().is_some_and(|c|c.natural_result.is_some()) {
                self.battle_results=retired.battle_results;
                let leave=retired.shared.as_ref().is_some_and(|c|c.commands.iter().any(|v|matches!(v,Command::Leave)));
                self.shared.as_mut().ok_or_else(||bad())?.result_leave_requested|=leave;
            }
            self.shared.as_mut().and_then(|c|c.profile13.as_mut()).ok_or_else(||bad())?.stale_envelopes=count+1;
            events.push(format!("P08B_TERMINAL_AVATAR_DRAIN session={} envelopes={} domain_applied=false",self.id,count+1));
            return Ok(());
        }
        if phase == Phase::Account {
            return self.shared_account_payload(payload, events);
        }
        if payload.is_empty() { return Ok(()); }
        let current_world=self.shared.as_ref().and_then(|c|c.view.clone()).ok_or_else(||bad())?;
        let world=&current_world;
        let c = self.shared.as_mut().ok_or_else(|| bad())?;
        if c.phase == Phase::Enable {
            let late = drive::late_queue_info(payload)?;
            if late == Some(false) { return Ok(()); }
            if payload != [9] && late != Some(true) { return Err(bad()); }
            c.announcement_parts.clear();
            let mut parts=if c.spotting_enabled {
                c.refresh_interest(world)?;
                wire::announcement_parts_for(world,c.slot,world.desired_visibility(c.slot)?)?
            } else {
                wire::announcement_parts(world,c.slot)?.into_iter()
                    .map(|body|wire::AnnouncementPart{body,enters:Vec::new()}).collect()
            };
            let last=parts.pop().ok_or_else(||bad())?;
            let mut body=last.body;let mut entered_slots=last.enters;
            for part in parts {
                let sequence=self.tx.enqueue_body_tracked(&part.body)?;
                c.announcement_parts.push((sequence,false));
                c.mark_announced(&part.enters,sequence)?;
            }
            if world.destructible_enabled() {body.extend(destructible_wire::announcement());}
            c.announced_areas = 0;
            if let Some(state)=&world.fragiles {
                let chunks=state.catalog.chunks();
                c.areas=vec![(None,Vec::new());chunks.len()];
                c.tree_areas=vec![Vec::new();chunks.len()];
                c.column_areas=vec![Vec::new();chunks.len()];
                for i in 0..chunks.len().min(AREA_ANNOUNCEMENT_BATCH) {
                    let record = destructible_wire::area_announcement(i)?;
                    if body.len() + record.len() > 512 {
                        let sequence = self.tx.enqueue_body_tracked(&body)?;
                        c.announcement_parts.push((sequence, false));
                        c.mark_announced(&entered_slots,sequence)?;entered_slots.clear();
                        body = Vec::new();
                    }
                    body.extend(record);
                    c.announced_areas += 1;
                }
            }
            if !body.is_empty() {
                let sequence = self.tx.enqueue_body_tracked(&body)?;
                c.announcement_parts.push((sequence, false));
                c.mark_announced(&entered_slots,sequence)?;
            }
            let sequence = c.announcement_parts.last().map(|(sequence, _)| *sequence).ok_or_else(|| bad())?;
            c.announcement = Some((sequence, false));
            c.phase = Phase::Entities;
            events.push(format!("SHARED_ANNOUNCED battle={} session={} rows={} own={} areas={} parts={} reliable_sequence={sequence}", world.id, self.id, world.actors.len(), wire::vehicle_id(c.slot)?, c.announced_areas, c.announcement_parts.len()));
            return Ok(());
        }
        if payload.len() > 512 { return Err(bad()); }
        if payload.first() == Some(&8) && c.phase == Phase::Entities {
            // treeobserve08: six area requests + the first READY compound
            // arrive together before Driving. Only a complete owned READY may
            // follow the fixed request prefix; arbitrary methods remain closed.
            let prefix_len = payload.chunks_exact(7).take_while(|raw| raw[0] == 8).count() * 7;
            let (requests, tail) = payload.split_at(prefix_len);
            if !tail.is_empty() && (payload.len() > 512 || wire::ready(tail, c.slot).is_err()) { return Err(bad()); }
            if c.announcement.is_none()
                || requests.is_empty()
                || requests.len() > 7*(world.actors.len()+usize::from(world.destructible_enabled())+c.announced_areas) { return Err(bad()); }
            // Original requests can piggyback vehicles and area controllers.
            // Queue the complete envelope first, then release only as much as
            // the reliable eight-body window can carry. Session's outer receive
            // clone makes the whole envelope atomic on malformed input.
            if c.tree_areas.len()!=c.areas.len(){c.tree_areas=vec![Vec::new();c.areas.len()];}
            if c.column_areas.len()!=c.areas.len(){c.column_areas=vec![Vec::new();c.areas.len()];}
            for raw in requests.chunks_exact(7) {
                if let Some(area)=destructible_wire::area_request(raw,c.areas.len()) {
                    if area >= c.announced_areas || c.areas[area].0.is_some() || c.pending_area_requests.contains(&area) { return Err(bad()); }
                    if world.fragiles.is_none() { return Err(bad()); }
                    c.pending_area_requests.push_back(area);
                }else if destructible_wire::is_request(raw) {
                    if !world.destructible_enabled() || c.area_creation.is_some() || c.pending_area_scene { return Err(bad()); }
                    c.pending_area_scene = true;
                } else {
                    let slots = wire::entity_requests(raw)?.ok_or_else(|| bad())?;
                    for slot in slots {
                        if slot>=world.actors.len() {return Err(bad());}
                        if !c.request_allowed(slot) {
                            events.push(format!("P07B_STALE_ENTITY_REQUEST session={} slot={slot} private_body=false",self.id));continue;
                        }
                        if c.creations[slot].is_some() || c.pending_entity_requests.contains(&slot) { return Err(bad()); }
                        c.pending_entity_requests.push_back(slot);
                    }
                }
            }
            if tail.is_empty() {
                drop(c);
                self.flush_shared_requests(events)?;
                return Ok(());
            }
            // Queue binding before draining creates so requests cannot consume
            // its window slot. Session::receive commits the whole envelope,
            // including ACKs and the final request flush, atomically.
            payload = tail;
        }
        // INPUT-01: frame the whole envelope before any record is applied. An ID
        // outside the #717 Avatar table cannot be framed: the complete envelope
        // is discarded unapplied (atomic, as a reject was) while the caller still
        // consumes its authenticated reliable sequence, so the channel stays live.
        // Only in Driving: before the first READY the strict reject remains, so
        // a damaged handshake is never silently consumed.
        if c.phase == Phase::Driving && let Some((offset, id)) = unframed_record(payload, c.slot)? {
            events.push(format!("SHARED_UNSUPPORTED_ENVELOPE session={} sequence={sequence} id={id:#04x} offset={offset} bytes={} domain_applied=false",
                self.id, payload.len()));
            return Ok(());
        }
        // Native fix06 B204 reverses the first-battle batching order: READY33
        // precedes six area requests. Validate only the exact owned compound,
        // then validate its entire tail in the same receive transaction.
        if payload.get(..33).is_some_and(|prefix| wire::ready(prefix, c.slot).is_ok()) {
            if c.phase != Phase::Driving {
                if c.phase != Phase::Entities || !c.creations[c.slot].is_some_and(|(_, ack)| ack) { return Err(bad()); }
                let sequence = self.tx.enqueue_body_tracked(&wire::binding(world, c.slot, now)?)?;
                c.binding = Some((sequence, false)); c.phase = Phase::Driving;
                // Loading/reconnecting a scene is not a replay of prior gun effects.
                c.shot_cursor = world.latest_shot();
                c.impact_cursor = world.impacts.len();
                c.sixth_sense_sent = world.sixth_sense_generation(c.slot)?;
                c.damage_cursor=world.damage_events.len();c.ram_cursor=world.ram_damage_events.len();c.device_cursor=world.device_events.len();
                c.tracer_started = [false; model::MAX_BATTLE_SHOTS];
                c.tracer_stopped = [false; model::MAX_BATTLE_SHOTS];
                for slot in 0..world.actors.len() { c.ready_sent[slot] = wire::binding_ready(world, c.slot, slot); }
                events.push(format!("SHARED_READY battle={} session={} own={} reliable_sequence={sequence} tick={}", world.id, self.id, wire::vehicle_id(c.slot)?, world.tick));
            }
            payload = &payload[33..];
            if payload.is_empty() { return Ok(()); }
        }
        if c.phase != Phase::Driving { return Err(bad()); }
        // A complete mixed input envelope is validated inside Session's receive
        // clone. No world command can escape a malformed later record/piggyback.
        let mut at = 0; let mut count = 0;
        while at < payload.len() {
            count += 1; if count > 16 { return Err(bad()); }
            // The native initializer can append its complete 33-byte READY
            // compound after area requests.  In Driving this is a harmless
            // duplicate handshake; recognize the whole measured suffix before
            // treating its leading 0x0d as the separate postmortem method.
            if payload.len() - at == 33 && wire::ready(&payload[at..], c.slot).is_ok() {
                at += 33;
                continue;
            }
            let id = payload[at];
            // INPUT-01: unframed IDs were already refused by the pre-scan.
            let size = record_size(payload, at)?.ok_or_else(|| bad())?;
            let raw = payload.get(at..at+size).ok_or_else(|| bad())?; at += size;
            if let Some(method)=wire::unimplemented_exposed(id) {
                // Exposed but not implemented here: skip exactly this record.
                // No reply is invented (Avatar onCmdResponse is unmeasured).
                events.push(format!("SHARED_UNSUPPORTED session={} method={method} id={id:#04x} bytes={} {} domain_applied=false",
                    self.id,raw.len(),wire::unimplemented_detail(raw)));
                continue;
            }
            if id==0x87 {
                if !self.battle_results.confirm_avatar(raw)? {return Err(bad());}
                continue;
            }
            if id == 8 {
                if let Some(slot)=detached_turret::request(raw)?{
                    if !world.ammo_detonation_enabled(){return Err(bad());}
                    let disposition=c.turrets.book.on_request(slot)?;
                    events.push(format!("P06T_TURRET_REQUEST session={} slot={slot} disposition={disposition:?}",self.id));
                    continue;
                }
                if c.tree_areas.len()!=c.areas.len(){c.tree_areas=vec![Vec::new();c.areas.len()];}
            if c.column_areas.len()!=c.areas.len(){c.column_areas=vec![Vec::new();c.areas.len()];}
                if let Some(area)=destructible_wire::area_request(raw,c.areas.len()) {
                    if area >= c.announced_areas || c.areas[area].0.is_some() || c.pending_area_requests.contains(&area) { return Err(bad()); }
                    if world.fragiles.is_none() { return Err(bad()); }
                    c.pending_area_requests.push_back(area);
                } else if destructible_wire::is_request(raw) {
                    if !world.destructible_enabled() || c.area_creation.is_some() || c.pending_area_scene { return Err(bad()); }
                    c.pending_area_scene = true;
                } else {
                    let slots = wire::entity_requests(raw)?.ok_or_else(|| bad())?;
                    for slot in slots {
                        if slot>=world.actors.len() {return Err(bad());}
                        if !c.request_allowed(slot) {
                            events.push(format!("P07B_STALE_ENTITY_REQUEST session={} slot={slot} private_body=false",self.id));continue;
                        }
                        if c.creations[slot].is_some() || c.pending_entity_requests.contains(&slot) { return Err(bad()); }
                        c.pending_entity_requests.push_back(slot);
                    }
                }
            } else if id == 0x0c {
                let target=wire::auto_aim_target(raw)?;
                // Target tracking is explicitly unavailable. The original
                // client has already stopped its mouse rotator on lock, so an
                // ACK-only no-op would leave a false lock. Refuse through its
                // own native loss callback, without consulting target state.
                if target!=0 {
                    if self.outbox.len()>=128 {return Err(bad());}
                    self.outbox.push_back(wire::auto_aim_lost());
                    events.push(format!("SHARED_UNSUPPORTED session={} method=autoAim target={target} refused=true native_callback=onAutoAimVehicleLost domain_applied=false",self.id));
                } else {
                    // The client has already restored mouse control on cancel.
                    // No callback echo, no domain command, no hidden-state read.
                    events.push(format!("SHARED_AUTOAIM_CANCEL session={} domain_applied=false native_callback=false",self.id));
                }
            } else if id == 0x0d {
                if world.actors.get(c.slot).is_none_or(|actor| actor.alive())
                    || !c.correction || !c.binding.is_some_and(|(_,ack)| ack) { return Err(bad()); }
                // Observer camera requests are consumed in every well-formed
                // case: a refused one must not stall the reliable sequence.
                let target=wire::postmortem_bind_target(raw)?;
                match wire::postmortem_camera(world,c.slot,target)? {
                    wire::PostmortemCamera::Own=>events.push(format!("SHARED_POSTMORTEM_REBIND session={} slot={} target={target} authority_changed=false",self.id,c.slot)),
                    wire::PostmortemCamera::Ally(slot)=>events.push(format!("SHARED_POSTMORTEM_OBSERVE session={} slot={} target_slot={slot} target={target} authority_changed=false interest_changed=false",self.id,c.slot)),
                    wire::PostmortemCamera::Unbind=>events.push(format!("SHARED_POSTMORTEM_UNBIND session={} slot={} authority_changed=false",self.id,c.slot)),
                    wire::PostmortemCamera::Refused=>events.push(format!("SHARED_UNSUPPORTED session={} method=bindToVehicle target={target} refused=true domain_applied=false",self.id)),
                }
            } else if let Some(commands) = fire::parse(raw)? {
                if !c.correction { return Err(bad()); }
                c.commands.extend(commands.into_iter().map(Command::Fire));
            } else if let Some(intent)=if world.mixed_ammo(){crate::armament_wire091::command(raw)?}else{None}{
                if !c.correction{return Err(bad());}
                use crate::{armament_wire091::{Intent,Setting},p06t_armament091 as armed};
                let command=match intent{
                    Intent::Select(setting,compact)=>armed::Command::Select(match setting{Setting::Current=>armed::Selection::Current,Setting::Next=>armed::Selection::Next},compact),
                    Intent::ReloadPartialClip=>armed::Command::ReloadClip,
                };
                c.commands.push(Command::Armament(command));
            } else if let Some(intent) = wire::aim_intent(raw, c.slot)? {
                // The native initializer can emit its first target before
                // ACK6 in the same envelope. It is only an intent: simulation
                // cannot advance it before the binding/correction is accepted.
                // Keep it queued so an early native aim packet does not poison
                // the reliable channel while the remaining catalog batches
                // are still draining.
                c.commands.push(Command::Aim(intent));
            } else {
                let mut normalized = raw.to_vec();
                if id == 3 {
                    if raw[1..5] != wire::vehicle_id(c.slot)?.to_le_bytes() { return Err(bad()); }
                    normalized[1..5].copy_from_slice(&crate::arena_vehicle091::VEHICLE_ENTITY_ID.to_le_bytes());
                }
                for method in drive::methods(&normalized)? {
                    match method {
                        drive::Method::CorrectionAck => {
                            if !c.binding.is_some_and(|(_, ack)| ack) { return Err(bad()); } c.correction = true;
                        },
                        drive::Method::Move(flags, input) => {
                            // Both actual native clients send stop then ACK6 in
                            // one initial envelope (8a01000006). Neutral is safe
                            // before correction; nonzero remains gated.
                            if !c.correction && flags != 0 { return Err(bad()); }
                            c.commands.push(Command::Move(Input { throttle: input.throttle, steer: input.steer, speed_percent: input.speed_percent }));
                        },
                        drive::Method::UnsupportedMove(flags) => {
                            c.commands.push(Command::Move(Input::STOP));
                            events.push(format!("SHARED_UNSUPPORTED session={} method=move flags={flags} failsafe_stop=true", self.id));
                        },
                        drive::Method::IgnoredTelemetry(_) => {}, // validated then discarded
                        drive::Method::Leave => {
                            // Original result handler queues Leave from the UI
                            // callback and confirm afterwards in the same turn.
                            let confirm_tail=c.natural_result.is_some() && self.battle_results.avatar_pending()
                                && payload.get(at..)==Some(&[0x87,0,0][..]);
                            if at != payload.len() && !confirm_tail { return Err(bad()); }
                            c.commands.push(Command::Leave); c.phase = Phase::Leaving;
                        },
                        other => events.push(format!("SHARED_UNSUPPORTED session={} method={other:?} domain_applied=false", self.id)),
                    }
                }
            }
            if c.commands.len() > model::MAX_COMMANDS { return Err(bad()); }
        }
        Ok(())
    }

    pub(super) fn flush_shared_requests(&mut self, events: &mut Vec<String>) -> io::Result<()> {
        let world = self.shared.as_ref().and_then(|c| c.view.clone()).ok_or_else(|| bad())?;
        let mut next = self.clone();
        let mut committed=Vec::new();
        next.shared.as_mut().ok_or_else(||bad())?.refresh_interest(&world)?;
        next.flush_shared_interest(&mut committed)?;
        loop {
            if next.tx.len() >= 8 { break; }
            enum Request { Scene, Vehicle(usize), Area(usize) }
            let request = {
                let c = next.shared.as_mut().ok_or_else(|| bad())?;
                if c.pending_area_scene {
                    c.pending_area_scene = false;
                    Some(Request::Scene)
                } else if let Some(slot) = c.pending_entity_requests.pop_front() {
                    Some(Request::Vehicle(slot))
                } else {
                    c.pending_area_requests.pop_front().map(Request::Area)
                }
            };
            let Some(request) = request else { break; };
            match request {
                Request::Scene => {
                    let state = (world.scene_version() == 1).then_some(destructible_wire::NATIVE_INDEX);
                    let sequence = next.tx.enqueue_body_tracked(&destructible_wire::create(state)?)?;
                    let c = next.shared.as_mut().ok_or_else(|| bad())?;
                    c.area_creation = Some((sequence, false));
                    c.area_scene_sent = world.scene_version();
                    committed.push(format!("SHARED_AREA_CREATED battle={} session={} entity={} scene_version={} reliable_sequence={sequence}", world.id,next.id,destructible_wire::ENTITY_ID,world.scene_version()));
                }
                Request::Vehicle(slot) => {
                    let c=next.shared.as_ref().ok_or_else(||bad())?;
                    if slot>=world.actors.len() {return Err(bad());}
                    if !c.request_allowed(slot) {continue;}
                    if c.creations[slot].is_some() {return Err(bad());}
                    let epoch=if c.spotting_enabled {Some(c.interest.as_ref().and_then(|b|b.announcement_sequence(slot)).ok_or_else(||bad())?)} else {None};
                    let sequence = next.tx.enqueue_body_tracked(&turret_publication::parent_create(&world, slot)?)?;
                    let c = next.shared.as_mut().ok_or_else(|| bad())?;
                    c.creations[slot] = Some((sequence, false));
                    c.creation_announcements[slot]=epoch;
                    c.health_sent[slot] = Some(world.actors[slot].health);
                    committed.push(format!("SHARED_ENTITY_CREATED battle={} session={} entity={} own={} reliable_sequence={sequence}", world.id, next.id, wire::vehicle_id(slot)?, slot == c.slot));
                }
                Request::Area(area) => {
                    let state = world.fragiles.as_ref().ok_or_else(|| bad())?;
                    let chunk = state.catalog.chunks().get(area).copied().ok_or_else(|| bad())?;
                    let indices = state.native_destroyed(chunk);
                    let values = state.native_fragile_values(chunk);
                    let trees = state.native_fallen_trees(chunk);
                    let columns = state.native_fallen_columns(chunk);
                    let sequence = next.tx.enqueue_body_tracked(&destructible_wire::area_create_full(area,chunk,&values,&columns,&trees)?)?;
                    let c = next.shared.as_mut().ok_or_else(|| bad())?;
                    if c.areas.get(area).is_none_or(|(pending, _)| pending.is_some()) { return Err(bad()); }
                    c.areas[area] = (Some((sequence,false)), indices);
                    c.tree_areas[area] = trees;
                    if c.column_areas.len()!=c.areas.len(){c.column_areas=vec![Vec::new();c.areas.len()];}
                    c.column_areas[area] = columns;
                    committed.push(format!("SHARED_CATALOG_AREA_CREATED battle={} session={} entity={} chunk={} scene={} reliable_sequence={sequence}",world.id,next.id,destructible_wire::area_id(area)?,chunk,world.scene_version()));
                }
            }
        }
        next.flush_shared_announcements(&mut committed)?;
        *self = next;events.extend(committed);
        Ok(())
    }

    /// Publish the next bounded set of native area controllers after the
    /// preceding announcement and all of its area-create replies have been
    /// acknowledged.  The client only learns IDs from these messages, so a
    /// request for a later area is rejected until its announcement is sent.
    pub(super) fn flush_shared_announcements(&mut self, events: &mut Vec<String>) -> io::Result<()> {
        let Some(shared) = self.shared.as_ref() else { return Ok(()); };
        // Native READY moves the session to Driving as soon as the own
        // vehicle binding is acknowledged.  Area announcements still have
        // to drain in that phase; otherwise a large catalog stalls at the
        // last batch known before READY and the peer eventually overflows
        // its application window with retries.
        if !matches!(shared.phase, Phase::Entities | Phase::Driving) || shared.announced_areas == 0
            || self.tx.len() != 0 || !shared.announcement_parts.iter().all(|(_, ack)| *ack)
            || !shared.pending_entity_requests.is_empty() || !shared.pending_area_requests.is_empty()
            || shared.pending_area_scene || shared.area_creation.is_some_and(|(_, ack)| !ack)
            || shared.areas.iter().take(shared.announced_areas).any(|(pending, _)|
                pending.is_none_or(|(_, ack)| !ack)) {
            return Ok(());
        }
        let world = shared.view.clone().ok_or_else(|| bad())?;
        let Some(total) = world.fragiles.as_ref().map(|state| state.catalog.chunks().len()) else { return Ok(()); };
        if shared.announced_areas >= total { return Ok(()); }
        let start = shared.announced_areas;
        let end = (start + AREA_ANNOUNCEMENT_BATCH).min(total);
        let mut body = Vec::new();
        for area in start..end {
            body.extend(destructible_wire::area_announcement(area)?);
        }
        if body.is_empty() || body.len() > 512 { return Err(bad()); }
        let mut next = self.clone();
        let sequence = next.tx.enqueue_body_tracked(&body)?;
        let c = next.shared.as_mut().ok_or_else(|| bad())?;
        c.announced_areas = end;
        c.announcement_parts.push((sequence, false));
        c.announcement = Some((sequence, false));
        *self = next;
        events.push(format!("SHARED_ANNOUNCEMENT_BATCH session={} start={} end={} reliable_sequence={} body_bytes={}", self.id, start, end, sequence, body.len()));
        Ok(())
    }
}

pub use server::serve_integrated_for_map;
pub use server::serve_integrated_for_vehicle;

#[cfg(test)]
#[path = "interest_session_tests.rs"]
mod p07b_interest_session_tests;

#[cfg(test)]
mod shared_return_tests {
    use super::*;
    use std::{path::Path, sync::Arc};
    use crate::{identity091, hangar091, transport091};
    use super::super::Window;

    fn live(now: Instant, slot: usize) -> Session {
        let id = slot as u32 + 1;
        let directory = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/server/fixtures")
            .join(crate::arena_vehicle091::PRIMARY_ACCOUNT).join("r4-catalog3").canonicalize().unwrap();
        let mut s = Session::new(id, [id as u8; 16], format!("127.0.0.1:{}", 35200 + id).parse().unwrap(), now);
        s.identity = Some(Arc::new(identity091::Profile { account_id: crate::arena_vehicle091::PRIMARY_ACCOUNT.into(),
            database_id: 1, name: crate::arena_vehicle091::PRIMARY_NAME.into(), fixture_dir: directory.clone() }));
        s.hangar = Some(Arc::new(hangar091::Fixtures::load_interactive(&directory).unwrap()));
        s.base_peer = Some(format!("127.0.0.1:{}", 35300 + id).parse().unwrap());
        s.active = true; s.account_ready = true; s.sync_mask = 7; s.arena_base = true;
        s.rx = 1; s.tx = Window::interactive();
        s.request_ids = vec![1, 2, 3]; s.chat_request_ids = vec![1, 2, 3];
        s.unsupported_request_ids.push_back(9); s.account_cache_hash = Some(-42);
        let mut c = Client::new(slot); c.phase = Phase::Driving; c.correction = true;
        c.return_generation = 1; c.binding = Some((0, true)); c.creations = [Some((0, true)); model::MAX_ACTORS];
        c.view = Some(model::tests::world(now));
        s.shared = Some(c); s
    }
    fn frame(s: &Session, payload: &[u8], ack: u32) -> Frame {
        Frame { flags: 0x458, sequence: Some(s.rx), cumulative: Some(ack), selective: vec![],
            body: [vec![1], s.token.to_le_bytes().to_vec(), payload.to_vec()].concat(), piggybacks: vec![] }
    }
    fn pending(now: Instant, slot: usize) -> Session {
        let mut s = live(now, slot);
        s.shared_return("unit_native_leave", now, &mut Vec::new()).unwrap();
        let sent = s.tx.due(now, s.rx).unwrap().unwrap();
        assert_eq!(sent.0, 0);
        assert_eq!(transport091::parse_interactive(&sent.2).unwrap().body,
            drive::return_account(&s.identity.as_ref().unwrap().name).unwrap());
        s
    }
    fn live_secondary(now: Instant) -> Session {
        let mut s = live(now, 1);
        let directory = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/server/fixtures")
            .join("271022a3-41e0-406e-b6fa-59930c320442").join("r1-catalog2").canonicalize().unwrap();
        let compatibility: serde_json::Value = serde_json::from_slice(&std::fs::read(directory.join("compatibility.json")).unwrap()).unwrap();
        s.identity = Some(Arc::new(identity091::Profile {
            account_id: "271022a3-41e0-406e-b6fa-59930c320442".into(),
            database_id: i32::try_from(compatibility["native_database_id"].as_i64().unwrap()).unwrap(),
            name: compatibility["client_name"].as_str().unwrap().into(), fixture_dir: directory.clone() }));
        s.hangar = Some(Arc::new(hangar091::Fixtures::load_interactive(&directory).unwrap()));
        s
    }
    // OBSERVED morning-natural01/session1/slot1, seq1076, flags0x458,
    // cumulativeACK1220. packet-007619-base_client_to_server.bin ciphertext
    // SHA256 6769423feb84f8617be70aa7e3a12b9239e38940d091508114e3ca044a5864a8.
    // Token-stripped application11B SHA256
    // ef7f4c7af5335a14f6b385a3284a78f801fe5e530503224aa98157eca319cf14.
    // Cell autoAim has one OBJECT_ID argument; preceding UINT32 is routing0.
    const P08C_AUTOAIM_CAPTURED: [u8; 11] = [12,8,0,0,0,0,0,3,0,16,9];

    fn p08c_autoaim_target(target: u32) -> Vec<u8> {
        let mut raw = P08C_AUTOAIM_CAPTURED.to_vec(); raw[7..11].copy_from_slice(&target.to_le_bytes()); raw
    }
    fn p08c_autoaim_bodies(s: &Session, now: Instant) -> Vec<Vec<u8>> {
        let mut tx = s.tx.clone(); let mut bodies = Vec::new();
        while let Some((_, _, raw)) = tx.due(now, s.rx).unwrap() {
            bodies.push(transport091::parse_interactive(&raw).unwrap().body);
        }
        bodies.extend(s.outbox.iter().cloned()); bodies
    }
    fn p08c_autoaim_no_domain(before: &Session, after: &Session) {
        let a = before.shared.as_ref().unwrap(); let b = after.shared.as_ref().unwrap();
        let x = a.view.as_ref().unwrap(); let y = b.view.as_ref().unwrap();
        assert_eq!(x.actors, y.actors);
        assert_eq!((x.id,x.tick,x.shots.len(),x.projectiles.len(),x.damage_events.len(),x.device_events.len()),
                   (y.id,y.tick,y.shots.len(),y.projectiles.len(),y.damage_events.len(),y.device_events.len()));
        assert_eq!((&a.commands,a.phase,a.slot,a.join_requested,a.return_generation,a.return_mask),
                   (&b.commands,b.phase,b.slot,b.join_requested,b.return_generation,b.return_mask));
        assert_eq!(a.interest,b.interest); assert_eq!(a.private_pending.len(),b.private_pending.len());
        assert_eq!((before.key,before.token,before.handoff,before.base_peer,before.arena_base),
                   (after.key,after.token,after.handoff,after.base_peer,after.arena_base));
        assert_eq!(before.request_ids,after.request_ids); assert_eq!(before.chat_request_ids,after.chat_request_ids);
        assert_eq!(before.hangar.as_ref().unwrap().state_sha256(),after.hangar.as_ref().unwrap().state_sha256());
    }

    #[test]
    fn p08c_autoaim_actual_nonzero_refusal_preserves_ack_replay_and_next_heartbeats() {
        let now=Instant::now();
        for slot in 0..2 {
            let mut s=live(now,slot);
            // An actually sent reliable predecessor makes cumulativeACK1 real.
            s.tx.enqueue_body(&[13,1]).unwrap(); assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,0);
            let before=s.clone();let packet=frame(&s,&P08C_AUTOAIM_CAPTURED,1);
            s.receive(&packet,now).unwrap();
            assert_eq!(s.rx,before.rx+1);assert_eq!(s.tx.cumulative,1);
            assert_eq!(p08c_autoaim_bodies(&s,now),vec![vec![0x13,0x3b]]);
            p08c_autoaim_no_domain(&before,&s);
            let once=s.clone();s.receive(&packet,now).unwrap();same(&s,&once);
            assert_eq!(p08c_autoaim_bodies(&s,now),vec![vec![0x13,0x3b]]);
            // No second callback is emitted by the following token-only frame.
            let old_rx=s.rx;s.receive(&frame(&s,&[],1),now).unwrap();assert_eq!(s.rx,old_rx+1);
            assert_eq!(p08c_autoaim_bodies(&s,now),vec![vec![0x13,0x3b]]);
            p08c_autoaim_no_domain(&before,&s);
            let sent=s.tx.due(now,s.rx).unwrap().unwrap();assert_eq!(sent.0,1);
            assert_eq!(transport091::parse_interactive(&sent.2).unwrap().body,vec![0x13,0x3b]);
            s.receive(&frame(&s,&[],2),now).unwrap();assert_eq!(s.tx.len(),0);
            assert!(p08c_autoaim_bodies(&s,now).is_empty());p08c_autoaim_no_domain(&before,&s);
        }
    }

    #[test]
    fn p08c_autoaim_cancel_zero_is_acknowledged_without_echo_or_gameplay_command() {
        let now=Instant::now();let cancel=p08c_autoaim_target(0);
        assert_eq!(cancel,vec![12,8,0,0,0,0,0,0,0,0,0]);
        for slot in 0..2 {
            let mut s=live(now,slot);let before=s.clone();let packet=frame(&s,&cancel,0);
            s.receive(&packet,now).unwrap();assert_eq!(s.rx,before.rx+1);
            assert!(p08c_autoaim_bodies(&s,now).is_empty());p08c_autoaim_no_domain(&before,&s);
            let once=s.clone();s.receive(&packet,now).unwrap();same(&s,&once);
        }
    }

    #[test]
    fn p08c_autoaim_all_target_classes_get_identical_refusal_without_target_oracle() {
        // Parser-only target-oracle proof: full Session receive/ACK is covered
        // above. Ordinary postreceive interest/LOS refresh is a separate action.
        let now=Instant::now();
        for class in 0..7 {
            let mut s=live(now,1);let mut target=wire::vehicle_id(0).unwrap();
            match class {
                0=>{ // Existing legacy world: both actors have team1 (friendly).
                    let w=s.shared.as_ref().unwrap().view.as_ref().unwrap();assert_eq!(w.team(0).unwrap(),w.team(1).unwrap());
                },
                1=>{ // Fresh, properly constructed two-team world, target alive.
                    let mut w=World::new(123,now).unwrap();w.enable_lifecycle(lifecycle::Rules::prohorovka()).unwrap();
                    for i in 0..2 {w.attach(model::Identity{account:format!("unit-{i}"),database:i+1,name:format!("unit_{i}")},i as u32+1).unwrap();}
                    w.start(now).unwrap();w.set_ready(0,1).unwrap();w.set_ready(1,2).unwrap();
                    assert_ne!(w.team(0).unwrap(),w.team(1).unwrap());s.shared.as_mut().unwrap().view=Some(w);
                },
                2=>s.shared.as_mut().unwrap().view.as_mut().unwrap().actors[0].health=0,
                3=>{ // Known but unannounced target in an actual interest Book.
                    let c=s.shared.as_mut().unwrap();c.spotting_enabled=true;
                    c.interest=Some(interest_wire::Book::new(1).unwrap());c.creations[0]=None;
                    assert!(!c.request_allowed(0));
                },
                4=>target=wire::vehicle_id(1).unwrap(), // Self is equally refused.
                5=>target=u32::MAX, // Arbitrary nonexistent/untrusted ID.
                6=>s.shared.as_mut().unwrap().view.as_mut().unwrap().actors.clear(), // Explicit unit-only absent-roster proof.
                _=>unreachable!(),
            }
            let before=s.clone();s.shared_payload(&p08c_autoaim_target(target),s.rx,now,&mut Vec::new()).unwrap();
            assert_eq!(p08c_autoaim_bodies(&s,now),vec![vec![0x13,0x3b]],"class={class}");
            p08c_autoaim_no_domain(&before,&s);
        }
    }

    #[test]
    fn p08c_autoaim_bad_shape_route_and_late_valid_commands_roll_back_actual_ack() {
        let now=Instant::now();let mut ready=live(now,1);
        ready.tx.enqueue_body(&[13,1]).unwrap();ready.tx.due(now,ready.rx).unwrap();
        let mut invalid=Vec::new();
        for len in 1..11 {invalid.push(P08C_AUTOAIM_CAPTURED[..len].to_vec());}
        for length in [0u16,7,9,u16::MAX] {
            let mut raw=P08C_AUTOAIM_CAPTURED.to_vec();raw[1..3].copy_from_slice(&length.to_le_bytes());invalid.push(raw);
        }
        for route in [wire::avatar_id(1).unwrap(),wire::avatar_id(0).unwrap(),u32::MAX] {
            let mut raw=P08C_AUTOAIM_CAPTURED.to_vec();raw[3..7].copy_from_slice(&route.to_le_bytes());invalid.push(raw);
        }
        let aim=vec![0x8e,8,0,0,0,0,0,0,0,0,0];let movement=vec![0x8a,1,0,1];
        // INPUT-01: an unframed late ID drops the whole envelope, sequence consumed.
        let mut late_bad=P08C_AUTOAIM_CAPTURED.to_vec();late_bad.extend(&aim);late_bad.extend(&movement);late_bad.push(0);
        let mut s=ready.clone();s.receive(&frame(&s,&late_bad,1),now).unwrap();assert_eq!(s.rx,ready.rx+1);
        // The authentic frame's transport ACK is still applied; nothing else.
        assert_eq!(s.tx.cumulative,1);
        let mut unapplied=s.clone();unapplied.rx=ready.rx;unapplied.received=ready.received.clone();unapplied.last_rx=ready.last_rx;
        unapplied.tx=ready.tx.clone();same(&unapplied,&ready);p08c_autoaim_no_domain(&ready,&s);
        let mut bad_route=P08C_AUTOAIM_CAPTURED.to_vec();bad_route[3]=1;
        invalid.push([aim.clone(),movement.clone(),bad_route].concat());
        let mut rejected=0;
        for payload in invalid {
            let mut s=ready.clone();
            // INPUT-01: a lying VAR2 length can leave an unframed ID behind; that
            // envelope is dropped unapplied with its sequence consumed instead.
            if s.receive(&frame(&s,&payload,1),now).is_err() {same(&s,&ready);rejected+=1;}
            else {
                assert_eq!(s.rx,ready.rx+1);
                let mut unapplied=s.clone();unapplied.rx=ready.rx;unapplied.received=ready.received.clone();
                unapplied.last_rx=ready.last_rx;unapplied.tx=ready.tx.clone();same(&unapplied,&ready);
            }
            p08c_autoaim_no_domain(&ready,&s);
        }
        assert!(rejected>=12,"truncations and wrong routes still fail closed: {rejected}");
        // A valid autoAim + Aim + Move child cannot escape a bad later outer frame.
        let child_payload=[P08C_AUTOAIM_CAPTURED.to_vec(),aim,movement].concat();
        // INPUT-01: a truncated record is still malformed (an unframed ID is dropped).
        let child=frame(&ready,&child_payload,1);let mut parent=frame(&ready,&[0x88,1,0],1);
        parent.sequence=Some(ready.rx+1);parent.piggybacks.push(child);
        let mut s=ready.clone();assert!(s.receive(&parent,now).is_err());same(&s,&ready);p08c_autoaim_no_domain(&ready,&s);
        assert_eq!(s.tx.cumulative,0);assert_eq!(s.tx.len(),1);
    }

    #[test]
    fn p08c_autoaim_is_closed_outside_driving_but_retired_drain_has_no_callback() {
        let now=Instant::now();
        for phase in [Phase::Account,Phase::Enable,Phase::Entities,Phase::Leaving] {
            let mut s=live(now,1);s.shared.as_mut().unwrap().phase=phase;let before=s.clone();
            assert!(s.receive(&frame(&s,&P08C_AUTOAIM_CAPTURED,0),now).is_err(),"phase={phase:?}");same(&s,&before);
            p08c_autoaim_no_domain(&before,&s);
        }
        let mut retired=pending(now,1);let before=retired.clone();
        retired.receive(&frame(&retired,&P08C_AUTOAIM_CAPTURED,0),now).unwrap();
        assert_eq!(retired.drive_return_account.as_ref().unwrap().stale_avatar_envelopes,1);
        assert!(p08c_autoaim_bodies(&retired,now).is_empty());p08c_autoaim_no_domain(&before,&retired);
        let mut enabled=pending(now,1);enabled.receive(&frame(&enabled,&[9],1),now).unwrap();let before=enabled.clone();
        assert!(enabled.receive(&frame(&enabled,&P08C_AUTOAIM_CAPTURED,1),now).is_err());same(&enabled,&before);
        p08c_autoaim_no_domain(&before,&enabled);
    }

    #[test]
    fn p08c_autoaim_backpressure_is_bounded_and_cancel_does_not_need_callback_space() {
        let now=Instant::now();let mut full=live(now,1);
        for _ in 0..8 {full.tx.enqueue_body(&[13,1]).unwrap();full.tx.due(now,full.rx).unwrap();}
        for _ in 0..128 {full.outbox.push_back(vec![13,1]);}
        let before=full.clone();
        assert!(full.receive(&frame(&full,&P08C_AUTOAIM_CAPTURED,0),now).is_err());same(&full,&before);p08c_autoaim_no_domain(&before,&full);
        let mut last=before.clone();last.outbox.pop_back();let initial=last.clone();
        last.receive(&frame(&last,&P08C_AUTOAIM_CAPTURED,0),now).unwrap();
        assert_eq!(last.outbox.len(),128);assert_eq!(last.outbox.back(),Some(&vec![0x13,0x3b]));
        assert_eq!(last.tx.len(),8);p08c_autoaim_no_domain(&initial,&last);
        let mut cancel=before.clone();cancel.receive(&frame(&cancel,&p08c_autoaim_target(0),0),now).unwrap();
        assert_eq!(cancel.outbox.len(),128);assert_eq!(cancel.outbox,before.outbox);p08c_autoaim_no_domain(&before,&cancel);
    }

    // Exact accepted single-client Ride07 native sync/chat bundle. The shared
    // lifecycle must consume the same real Account contract on either slot.
    fn warm() -> Vec<u8> {
        let text = "8e1400e20064000100000000000000d66e1203000000008e1400e3002c01030000000000000006020000250f8ecd8e1400e400580201000000000000004d72c26a0000000093190001000000000000000a00000000ffffffffffffffff000000009319000200000000000000090000000000000000000000000000000093190003000000000000001e00000000000000000000000000000000";
        text.as_bytes().chunks_exact(2).map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap()).collect()
    }
    // Native fix04 B: capture-stabfix04/packet-005031-base_client_to_server.bin,
    // SHA256 877c4027e6de5b03ea93fb19e20a27c1b1330eeb41a494718fb0e7baa1801e6a.
    // Exact token-stripped153B body at client sequence891: Account100 rev1,
    // Shop300 rev2, Dossier600 rev0, chatIDs1/2/3. No key/token is retained.
    fn fix04_secondary_warm() -> Vec<u8> {
        let text = "8e1400e200640001000000000000000c4cbf6a000000008e1400e3002c010200000000000000ae0100002c48f55c8e1400e40058020000000000000000000000000000000093190001000000000000000a00000000ffffffffffffffff000000009319000200000000000000090000000000000000000000000000000093190003000000000000001e00000000000000000000000000000000";
        text.as_bytes().chunks_exact(2).map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap()).collect()
    }
    // OBSERVED morning-marker01, session2/clientB sequence3528, flags0x458,
    // cumulativeACK3027; packet-021121-base_client_to_server.bin ciphertext
    // SHA256 ef9b87d728be090aa27866bea7e71d27a29eae3b097211eea0407815153fc259.
    // Exact token-stripped164B application SHA256
    // 5e8aed252f04679cbc695798a84947794e4b87372d74503969e34017696db8c5.
    // Gameplay/cache fields only; no native token, key or credentials.
    fn p08c_natural_return_captured() -> Vec<u8> {
        let hex = "0d080002001009030010098e1400e200640001000000000000005e1a6d3d000000008e1400e3002c010500000000000000435a000023a0cb0e8e1400e4005802010000000000000006ead06a0000000093190001000000000000000a00000000ffffffffffffffff000000009319000200000000000000090000000000000000000000000000000093190003000000000000001e00000000000000000000000000000000";
        let bytes: Vec<u8> = hex.as_bytes().chunks_exact(2)
            .map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap()).collect();
        assert_eq!(bytes.len(), 164);
        assert_eq!(&bytes[..11], &[13,8,0,2,0,16,9,3,0,16,9]);
        bytes
    }

    fn p08c_natural_return_for_slot(slot: usize) -> Vec<u8> {
        let mut bytes = p08c_natural_return_captured();
        // Slot0 is byte-for-byte observed. Slot1 is an explicit source-derived
        // identity variant, not a second native capture or ownership claim.
        if slot != 0 {
            bytes[3..7].copy_from_slice(&wire::avatar_id(slot).unwrap().to_le_bytes());
            bytes[7..11].copy_from_slice(&wire::vehicle_id(slot).unwrap().to_le_bytes());
        }
        bytes
    }

    fn p08c_natural_return_pending(now: Instant, slot: usize) -> Session {
        let mut s = pending(now, slot);
        let fixture = s.hangar.as_ref().unwrap().with_research_shop_for_test(24000, 5).unwrap()
            .with_dossier_cursor_for_test(1, 1792076294).unwrap();
        assert_eq!(fixture.shop_sync_revision().unwrap(), 5);
        fixture.validate_shop_cursor(5, 23107, 248225827).unwrap();
        fixture.validate_dossier_cursor(1, 1792076294).unwrap();
        assert!(fixture.validate_dossier_cursor(1, 1792076295).is_err());
        s.hangar = Some(Arc::new(fixture));
        s.shared.as_mut().unwrap().view.as_mut().unwrap().actors[slot].health = 0;
        s
    }

    fn p08c_natural_return_no_authority(before: &Session, after: &Session) {
        let old = before.shared.as_ref().unwrap(); let current = after.shared.as_ref().unwrap();
        let a = old.view.as_ref().unwrap(); let b = current.view.as_ref().unwrap();
        // Actor equality covers HP/pose/input/aim/fire/owned loadout/device state.
        assert_eq!(a.actors, b.actors);
        assert_eq!((a.id, a.tick, a.shots.len(), a.projectiles.len(), a.damage_events.len(), a.device_events.len()),
                   (b.id, b.tick, b.shots.len(), b.projectiles.len(), b.damage_events.len(), b.device_events.len()));
        assert_eq!((old.slot, old.binding, old.correction, old.return_generation),
                   (current.slot, current.binding, current.correction, current.return_generation));
        assert!(current.commands.is_empty()); assert!(!current.join_requested);
        assert!(after.drive.is_none()); assert!(!after.arena_base);
        assert_eq!((before.id, before.key, before.token, before.handoff, before.base_peer),
                   (after.id, after.key, after.token, after.handoff, after.base_peer));
        assert_eq!(before.hangar.as_ref().unwrap().state_sha256(), after.hangar.as_ref().unwrap().state_sha256());
    }

    #[test]
    fn p08c_natural_return_actual164_after_separate_enable_keeps_channel_replay_and_heartbeat() {
        let now = Instant::now();
        for slot in 0..2 {
            let mut s = p08c_natural_return_pending(now, slot);
            s.receive(&frame(&s, &[9], 1), now).unwrap();
            let before = s.clone();
            let packet = frame(&s, &p08c_natural_return_for_slot(slot), 1);
            s.receive(&packet, now).unwrap();
            assert_eq!(s.shared.as_ref().unwrap().phase, Phase::Account);
            assert_eq!(s.shared.as_ref().unwrap().return_mask, 7);
            assert_eq!(s.drive_return_account.as_ref().unwrap().stale_avatar_envelopes, 1);
            assert_eq!(s.account_cache_hash, Some(1030560350));
            assert_eq!(s.request_ids, vec![226, 227, 228]);
            assert_eq!(s.chat_request_ids, vec![1, 2, 3]);
            assert_eq!(s.rx, before.rx + 1);
            p08c_natural_return_no_authority(&before, &s);
            let once = s.clone(); s.receive(&packet, now).unwrap(); same(&s, &once);
            p08c_natural_return_no_authority(&once, &s);
            // Observed3529/3530/3531 were authentication-only, not new RPCs.
            for _ in 0..3 {
                let before = s.clone(); s.receive(&frame(&s, &[], 1), now).unwrap();
                assert_eq!(s.rx, before.rx + 1);
                assert_eq!(s.request_ids, before.request_ids);
                assert_eq!(s.chat_request_ids, before.chat_request_ids);
                assert_eq!(s.drive_return_account, before.drive_return_account);
                p08c_natural_return_no_authority(&before, &s);
            }
        }
    }

    #[test]
    fn p08c_natural_return_same_frame_enable_and_actual164_is_atomic_and_consumes_one_drain() {
        let now = Instant::now();
        for slot in 0..2 {
            let mut s = p08c_natural_return_pending(now, slot); let before = s.clone();
            let mut payload = vec![9]; payload.extend(p08c_natural_return_for_slot(slot));
            s.receive(&frame(&s, &payload, 1), now).unwrap();
            assert_eq!(s.shared.as_ref().unwrap().phase, Phase::Account);
            assert_eq!(s.shared.as_ref().unwrap().return_mask, 7);
            assert_eq!(s.drive_return_account.as_ref().unwrap().stale_avatar_envelopes, 1);
            assert!(s.drive_return_account.as_ref().unwrap().enabled);
            assert_eq!(s.rx, before.rx + 1);
            p08c_natural_return_no_authority(&before, &s);
        }
    }

    #[test]
    fn p08c_natural_return_wrong_own_route_or_target_and_zero_mailbox_fail_atomically() {
        let now = Instant::now();
        for slot in 0..2 {
            let mut ready = p08c_natural_return_pending(now, slot);
            ready.receive(&frame(&ready, &[9], 1), now).unwrap();
            for (field, replacement) in [
                (3, wire::avatar_id(1-slot).unwrap()),
                (3, 0), (3, wire::vehicle_id(slot).unwrap()),
                (7, wire::vehicle_id(1-slot).unwrap()),
                (7, 0), (7, wire::avatar_id(slot).unwrap()),
            ] {
                let mut payload = p08c_natural_return_for_slot(slot);
                payload[field..field+4].copy_from_slice(&replacement.to_le_bytes());
                let mut s = ready.clone();
                assert!(s.receive(&frame(&s, &payload, 1), now).is_err()); same(&s, &ready);
                p08c_natural_return_no_authority(&ready, &s);
            }
            // Source-only ID validator separation: ordinary Driving still uses
            // the previously measured zero mailbox and rejects explicit Avatar.
            let explicit = p08c_natural_return_for_slot(slot)[..11].to_vec();
            assert!(wire::retired_postmortem_rebind(&explicit, slot).is_ok());
            assert!(wire::postmortem_rebind(&explicit, slot).is_err());
            let mut zero = explicit.clone(); zero[3..7].fill(0);
            assert!(wire::postmortem_rebind(&zero, slot).is_ok());
            assert!(wire::retired_postmortem_rebind(&zero, slot).is_err());
        }
    }

    #[test]
    fn p08c_natural_return_requires_dead_retained_view_binding_correction_and_epoch_guards() {
        let now = Instant::now(); let mut enabled = p08c_natural_return_pending(now, 0);
        enabled.receive(&frame(&enabled, &[9], 1), now).unwrap();
        for guard in 0..10 {
            let mut s = enabled.clone();
            match guard {
                0 => s.shared.as_mut().unwrap().view.as_mut().unwrap().actors[0].health = 90,
                1 => s.shared.as_mut().unwrap().view = None,
                2 => s.shared.as_mut().unwrap().binding = None,
                // Sequence100 cannot be ACKed by the actual cumulative1 below.
                3 => s.shared.as_mut().unwrap().binding = Some((100, false)),
                4 => s.shared.as_mut().unwrap().correction = false,
                5 => s.drive_return_account.as_mut().unwrap().creation = None,
                6 => s.drive_return_account.as_mut().unwrap().creation = Some((100, false)),
                7 => s.drive_return_account.as_mut().unwrap().generation += 1,
                8 => s.shared.as_mut().unwrap().return_mask = 1,
                9 => s.shared.as_mut().unwrap().phase = Phase::Account,
                _ => unreachable!(),
            }
            let before = s.clone();
            assert!(s.receive(&frame(&s, &p08c_natural_return_captured(), 1), now).is_err(), "guard={guard}");
            same(&s, &before);
            assert_eq!(s.shared.as_ref().unwrap().binding, before.shared.as_ref().unwrap().binding);
            assert_eq!(s.shared.as_ref().unwrap().correction, before.shared.as_ref().unwrap().correction);
            assert_eq!(s.shared.as_ref().unwrap().view.as_ref().map(|v| &v.actors),
                       before.shared.as_ref().unwrap().view.as_ref().map(|v| &v.actors));
        }
        let preenable = p08c_natural_return_pending(now, 0);
        for payload in [p08c_natural_return_captured(), [vec![9], p08c_natural_return_captured()].concat()] {
            let mut s = preenable.clone();
            // Without reset ACK, even enable+bind+warm must remain unchanged.
            assert!(s.receive(&frame(&s, &payload, 0), now).is_err()); same(&s, &preenable);
        }
        let mut s = preenable.clone();
        assert!(s.receive(&frame(&s, &p08c_natural_return_captured(), 1), now).is_err()); same(&s, &preenable);
    }

    #[test]
    fn p08c_natural_return_exact_drain_budget_and_duplicate_bind_do_not_consume_warm_half() {
        let now = Instant::now(); let mut enabled = p08c_natural_return_pending(now, 0);
        enabled.receive(&frame(&enabled, &[9], 1), now).unwrap();
        let app = p08c_natural_return_captured();
        let mut last = enabled.clone(); last.drive_return_account.as_mut().unwrap().stale_avatar_envelopes = 31;
        last.receive(&frame(&last, &app, 1), now).unwrap();
        assert_eq!(last.drive_return_account.as_ref().unwrap().stale_avatar_envelopes, 32);
        assert_eq!(last.shared.as_ref().unwrap().phase, Phase::Account);
        let mut bounded = enabled.clone(); bounded.drive_return_account.as_mut().unwrap().stale_avatar_envelopes = 32;
        let before = bounded.clone();
        assert!(bounded.receive(&frame(&bounded, &app, 1), now).is_err()); same(&bounded, &before);
        let duplicate = [&app[..11], app.as_slice()].concat();
        let mut s = enabled.clone();
        assert!(s.receive(&frame(&s, &duplicate, 1), now).is_err()); same(&s, &enabled);
        assert_eq!(s.drive_return_account.as_ref().unwrap().stale_avatar_envelopes, 0);
        // A late bind after an already committed first warm command is refused.
        let mut s = enabled.clone(); s.receive(&frame(&s, &app[11..34], 1), now).unwrap();
        assert_eq!(s.shared.as_ref().unwrap().return_mask, 1); let before = s.clone();
        assert!(s.receive(&frame(&s, &app, 1), now).is_err()); same(&s, &before);
    }

    #[test]
    fn p08c_natural_return_bad_late_warm_cursor_tail_and_piggyback_roll_back_everything() {
        let now = Instant::now(); let ready = p08c_natural_return_pending(now, 0);
        let actual = p08c_natural_return_captured();
        let mut bad_shop = actual.clone(); bad_shop[41..49].copy_from_slice(&4i64.to_le_bytes());
        let mut bad_dossier = actual.clone(); bad_dossier[72..76].copy_from_slice(&1792076295i32.to_le_bytes());
        let mut bad_tail = actual.clone(); bad_tail.push(0);
        for malformed in [bad_shop, bad_dossier, bad_tail] {
            let mut payload = vec![9]; payload.extend(malformed);
            let mut s = ready.clone();
            assert!(s.receive(&frame(&s, &payload, 1), now).is_err()); same(&s, &ready);
            p08c_natural_return_no_authority(&ready, &s);
        }
        let mut good = vec![9]; good.extend(actual);
        let child = frame(&ready, &good, 1);
        let mut outer = frame(&ready, &[0], 1); outer.sequence = Some(ready.rx+1); outer.piggybacks.push(child);
        let mut s = ready.clone();
        assert!(s.receive(&outer, now).is_err()); same(&s, &ready);
        p08c_natural_return_no_authority(&ready, &s);
    }

    fn same(a: &Session, b: &Session) {
        assert_eq!((a.rx, a.tx.cumulative, a.tx.len(), a.sync_mask, a.arena_base, a.last_rx),
            (b.rx, b.tx.cumulative, b.tx.len(), b.sync_mask, b.arena_base, b.last_rx));
        assert_eq!(a.received, b.received); assert_eq!(a.outbox, b.outbox);
        assert_eq!(a.request_ids, b.request_ids); assert_eq!(a.chat_request_ids, b.chat_request_ids);
        assert_eq!(a.unsupported_request_ids, b.unsupported_request_ids);
        assert_eq!(a.account_cache_hash, b.account_cache_hash); assert_eq!(a.drive_return_account, b.drive_return_account);
        let a = a.shared.as_ref().unwrap(); let b = b.shared.as_ref().unwrap();
        assert_eq!((a.phase, a.return_mask, a.return_generation, a.join_requested, &a.commands),
            (b.phase, b.return_mask, b.return_generation, b.join_requested, &b.commands));
    }
    fn queue(command: i16) -> Vec<u8> {
        let mut body = vec![0x8e, 20, 0, 202, 0]; body.extend(command.to_le_bytes());
        body.extend((if command == 700 { 1i64 } else { 0 }).to_le_bytes());
        body.extend((if command == 700 { 7i32 } else { 0 }).to_le_bytes()); body.extend(0i32.to_le_bytes()); body
    }

    #[test]
    fn shared_return_requires_actual_reset_ack_before_native_enable() {
        let now = Instant::now(); let ready = pending(now, 0);
        assert_eq!(ready.drive_return_account.as_ref().unwrap().creation, Some((0, false)));
        assert!(!ready.shared.as_ref().unwrap().join_requested); assert!(ready.drive.is_none());
        for payload in [vec![9], warm()] {
            let mut s = ready.clone(); let f = frame(&s, &payload, 0);
            assert!(s.receive(&f, now).is_err()); same(&s, &ready);
        }
        let mut s = ready.clone(); s.receive(&frame(&s, &[9], 1), now).unwrap();
        assert!(s.drive_return_account.as_ref().unwrap().enabled);
        assert!(s.request_ids.is_empty()); assert!(s.chat_request_ids.is_empty());
        assert!(s.unsupported_request_ids.is_empty()); assert_eq!(s.rx, 2);
    }

    #[test]
    fn shared_return_exact_native_warm_sync_keeps_channel_and_waits_for_new_join() {
        let now = Instant::now();
        for slot in 0..2 {
            let mut s = pending(now, slot);
            let old = (s.key, s.token, s.handoff, s.hangar.as_ref().unwrap().state_sha256().to_owned());
            let mut payload = vec![9]; payload.extend(warm());
            let f = frame(&s, &payload, 1); s.receive(&f, now).unwrap();
            let c = s.shared.as_ref().unwrap();
            assert_eq!(c.phase, Phase::Account); assert_eq!(c.return_mask, 7); assert!(!c.join_requested);
            assert_eq!(s.chat_request_ids, vec![1, 2, 3]); assert_eq!(s.request_ids, vec![226, 227, 228]);
            assert_eq!(s.account_cache_hash, Some(51539670)); assert!(s.drive.is_none());
            assert_eq!((s.key, s.token, s.handoff, s.hangar.as_ref().unwrap().state_sha256().to_owned()), old);
            let once = s.clone(); s.receive(&f, now).unwrap(); same(&s, &once);
            s.receive(&frame(&s, &queue(700), 1), now).unwrap();
            assert!(s.shared.as_ref().unwrap().join_requested);
            s.receive(&frame(&s, &queue(701), 1), now).unwrap();
            assert!(!s.shared.as_ref().unwrap().join_requested);
        }
    }

    #[test]
    fn shared_return_late_bad_tail_rolls_back_ack_epoch_hash_and_sync() {
        let now = Instant::now(); let ready = pending(now, 0);
        for extra in [vec![0], vec![9], queue(700)] {
            let mut s = ready.clone(); let mut payload = vec![9]; payload.extend(warm()[..69].to_vec()); payload.extend(extra);
            assert!(s.receive(&frame(&s, &payload, 1), now).is_err()); same(&s, &ready);
        }
        let mut s = ready.clone(); let mut malformed = vec![9]; malformed.extend(warm()); malformed.push(0);
        assert!(s.receive(&frame(&s, &malformed, 1), now).is_err()); same(&s, &ready);
    }

    #[test]
    fn shared_return_retired_avatar_keeps_owned_slot1_id_and_exact_drain_budget() {
        let now = Instant::now(); let mut s = pending(now, 1);
        let mut own = vec![0x0f, 16, 0]; own.extend(wire::vehicle_id(1).unwrap().to_le_bytes());
        for coordinate in [0f32, 1., 2.] { own.extend(coordinate.to_le_bytes()); }
        let mut wrong = own.clone(); wrong[3..7].copy_from_slice(&wire::vehicle_id(0).unwrap().to_le_bytes());
        let ready = s.clone(); assert!(s.receive(&frame(&s, &wrong, 0), now).is_err()); same(&s, &ready);
        for _ in 0..32 { s.receive(&frame(&s, &own, 0), now).unwrap(); }
        assert_eq!(s.drive_return_account.as_ref().unwrap().stale_avatar_envelopes, 32);
        assert!(s.shared.as_ref().unwrap().commands.is_empty());
        assert_eq!(s.shared.as_ref().unwrap().phase, Phase::Returning);
        let bounded = s.clone(); assert!(s.receive(&frame(&s, &own, 0), now).is_err()); same(&s, &bounded);
        s.receive(&frame(&s, &[9], 1), now).unwrap();
        assert!(s.drive_return_account.as_ref().unwrap().enabled);
    }

    #[test]
    fn shared_return_tracks_reset_after_existing_outbox_and_full_window() {
        let now = Instant::now(); let mut s = live(now, 0);
        for _ in 0..8 { s.tx.enqueue_body(&[13, 1]).unwrap(); s.tx.due(now, s.rx).unwrap(); }
        s.outbox.push_back(vec![13, 2]); s.outbox.push_back(vec![13, 3]);
        s.shared_return("unit_backpressure", now, &mut Vec::new()).unwrap();
        assert_eq!(s.drive_return_account.as_ref().unwrap().creation, None);
        assert_eq!(s.drive_return_account.as_ref().unwrap().queue_ahead, 2);
        s.receive(&frame(&s, &[], 8), now).unwrap();
        assert_eq!(s.drive_return_account.as_ref().unwrap().creation, Some((10, false)));
        for sequence in 8..=10 { assert_eq!(s.tx.due(now, s.rx).unwrap().unwrap().0, sequence); }
        let before = s.clone(); assert!(s.receive(&frame(&s, &[9], 10), now).is_err()); same(&s, &before);
        s.receive(&frame(&s, &[9], 11), now).unwrap();
        assert!(s.drive_return_account.as_ref().unwrap().enabled);
    }

    #[test]
    fn shared_return_bad_queue_tail_is_atomic_and_battle_reset_preserves_epoch() {
        let now = Instant::now(); let mut s = pending(now, 0);
        let mut payload = vec![9]; payload.extend(warm()); s.receive(&frame(&s, &payload, 1), now).unwrap();
        let ready = s.clone(); let mut bad_join = queue(700); bad_join.push(0);
        assert!(s.receive(&frame(&s, &bad_join, 1), now).is_err()); same(&s, &ready);
        let c = s.shared.as_mut().unwrap(); c.reset_for_battle(1);
        assert_eq!(c.return_generation, 1); assert_eq!(c.phase, Phase::Account); assert!(c.join_requested);
        assert!(c.view.is_none()); assert!(c.binding.is_none()); assert_eq!(c.return_mask, 0);
    }

    #[test]
    fn shared_return_rejects_foreign_epoch_and_invalid_warm_revisions_atomically() {
        let now = Instant::now(); let ready = pending(now, 0);
        for offset in [7usize, 30, 53] {
            let mut s = ready.clone(); let mut invalid = warm(); invalid[offset] = 2;
            let mut payload = vec![9]; payload.extend(invalid);
            assert!(s.receive(&frame(&s, &payload, 1), now).is_err()); same(&s, &ready);
        }
        let mut foreign = ready.clone(); foreign.drive_return_account.as_mut().unwrap().generation += 1;
        let before = foreign.clone(); assert!(foreign.receive(&frame(&foreign, &[9], 1), now).is_err()); same(&foreign, &before);
        let mut s = ready.clone(); let mut duplicate = vec![9]; duplicate.extend(&warm()[..23]); duplicate.extend(&warm()[..23]);
        assert!(s.receive(&frame(&s, &duplicate, 1), now).is_err()); same(&s, &ready);
    }

    #[test]
    fn shared_return_retired_slot1_postmortem_is_validated_without_publication() {
        let now = Instant::now(); let mut s = pending(now, 1);
        s.shared.as_mut().unwrap().view.as_mut().unwrap().actors[1].health = 0;
        let mut postmortem = vec![0x0d, 8, 0, 0, 0, 0, 0]; postmortem.extend(wire::vehicle_id(1).unwrap().to_le_bytes());
        s.receive(&frame(&s, &postmortem, 0), now).unwrap();
        assert!(s.shared.as_ref().unwrap().commands.is_empty()); assert_eq!(s.tx.len(), 1);
        // POSTMORTEM-01: an ally camera bind is a drained camera call too.
        postmortem[7..].copy_from_slice(&wire::vehicle_id(0).unwrap().to_le_bytes());
        s.receive(&frame(&s, &postmortem, 0), now).unwrap();
        assert!(s.shared.as_ref().unwrap().commands.is_empty()); assert_eq!(s.tx.len(), 1);
        assert_eq!(s.drive_return_account.as_ref().unwrap().stale_avatar_envelopes, 2);
        let before = s.clone(); postmortem[3] = 1;
        assert!(s.receive(&frame(&s, &postmortem, 0), now).is_err()); same(&s, &before);
    }

    #[test]
    fn shared_return_queue_failure_does_not_commit_half_return() {
        let now = Instant::now(); let mut s = live(now, 0); s.outbox.push_back(vec![0; 513]);
        let before = s.clone(); let mut events = Vec::new();
        assert!(s.shared_return("unit_bad_queue", now, &mut events).is_err()); same(&s, &before);
        assert!(events.is_empty()); assert_eq!(s.shared.as_ref().unwrap().phase, Phase::Driving);
    }

    #[test]
    fn shared_return_fix04_actual_secondary_shop2_sync_accepts_next_native_heartbeat() {
        let now = Instant::now(); let mut s = live_secondary(now);
        assert_eq!(s.hangar.as_ref().unwrap().shop_sync_revision().unwrap(), 2);
        // Reproduce the measured reliable order: reset821, enable890/ACK822,
        // warm891/ACK823, then the token-only heartbeat892. This is a unit
        // replay of actual payload bytes, not a native acceptance claim.
        for expected in 0..821 {
            s.tx.enqueue().unwrap(); assert_eq!(s.tx.due(now, s.rx).unwrap().unwrap().0, expected);
            s.tx.acknowledge(&Frame { flags: 0x408, sequence: None, cumulative: Some(expected+1),
                selective: vec![], body: vec![], piggybacks: vec![] }).unwrap();
        }
        s.rx = 890;
        let fixture_hash = s.hangar.as_ref().unwrap().state_sha256();
        let identity = s.identity.as_ref().unwrap().clone();
        let channel = (s.id, s.key, s.token, s.handoff, s.base_peer);
        s.shared_return("fix04_natural_battle_failure_replay", now, &mut Vec::new()).unwrap();
        assert_eq!(s.drive_return_account.as_ref().unwrap().creation, Some((821, false)));
        assert_eq!(s.tx.due(now, s.rx).unwrap().unwrap().0, 821);
        s.tx.enqueue().unwrap(); assert_eq!(s.tx.due(now, s.rx).unwrap().unwrap().0, 822);
        s.receive(&frame(&s, &[9], 822), now).unwrap(); assert_eq!(s.rx, 891);
        assert!(s.drive_return_account.as_ref().unwrap().enabled);
        let native = fix04_secondary_warm(); assert_eq!(native.len(), 153);
        let sync = frame(&s, &native, 823); s.receive(&sync, now).unwrap();
        assert_eq!(s.rx, 892); assert_eq!(s.shared.as_ref().unwrap().phase, Phase::Account);
        assert_eq!(s.shared.as_ref().unwrap().return_mask, 7); assert!(!s.shared.as_ref().unwrap().join_requested);
        assert_eq!(s.request_ids, vec![226, 227, 228]); assert_eq!(s.chat_request_ids, vec![1, 2, 3]);
        assert_eq!(s.account_cache_hash, Some(1790921740)); assert_eq!(s.sync_mask, 7);
        assert_eq!(s.hangar.as_ref().unwrap().state_sha256(), fixture_hash);
        assert_eq!((s.id, s.key, s.token, s.handoff, s.base_peer), channel);
        assert_eq!(s.identity.as_ref().unwrap().account_id, identity.account_id);
        assert!(s.drive.is_none()); assert!(!s.arena_base);
        s.receive(&frame(&s, &[], 823), now).unwrap(); assert_eq!(s.rx, 893);
        assert!(s.shared.as_ref().unwrap().commands.is_empty());
    }

    #[test]
    fn profile13_shared_return_accepts_actual_large_shop_cache_and_rolls_back_bad_cursor() {
        let now=Instant::now();let mut ready=pending(now,0);
        ready.hangar=Some(Arc::new(ready.hangar.as_ref().unwrap().with_research_shop_for_test(24000,5).unwrap()));
        let source_hash=ready.hangar.as_ref().unwrap().state_sha256();
        // OBSERVED native-fix02 packet2687/seq264 and2725/seq299 both
        // request Shop300(5,23107,248225827), beyond legacy16448. Keep
        // only these public request fields; no native key/token is retained.
        let payload=|revision:i64,size:i32,crc:i32| {
            let mut body=vec![9];let mut sync=warm();
            sync[30..38].copy_from_slice(&revision.to_le_bytes());
            sync[38..42].copy_from_slice(&size.to_le_bytes());
            sync[42..46].copy_from_slice(&crc.to_le_bytes());body.extend(sync);body
        };
        for (revision,size,crc) in [(4,23107,248225827),(6,23107,248225827),
            (5,-1,0),(5,32833,248225827),(5,0,1),(5,0,-1)] {
            let mut s=ready.clone();assert!(s.receive(&frame(&s,&payload(revision,size,crc),1),now).is_err());
            same(&s,&ready);assert_eq!(s.hangar.as_ref().unwrap().state_sha256(),source_hash);
        }
        for (size,crc) in [(23107,248225827),(32832,i32::MIN),(0,0),(1,0)] {
            let mut s=ready.clone();let envelope=frame(&s,&payload(5,size,crc),1);
            s.receive(&envelope,now).unwrap();
            assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Account);
            assert_eq!(s.shared.as_ref().unwrap().return_mask,7);
            assert!(!s.shared.as_ref().unwrap().join_requested);
            assert_eq!(s.request_ids,vec![226,227,228]);assert_eq!(s.chat_request_ids,vec![1,2,3]);
            assert_eq!(s.hangar.as_ref().unwrap().state_sha256(),source_hash);
            assert_eq!(s.hangar.as_ref().unwrap().sizes()[1],24000);
            let mut tx=s.tx.clone();let mut bodies=Vec::new();
            while let Some((_,_,raw))=tx.due(now,s.rx).unwrap() {
                bodies.push(transport091::parse_interactive(&raw).unwrap().body);
            }
            bodies.extend(s.outbox.iter().cloned());
            let first=bodies.iter().position(|body|body.len()>5 && body[..2]==[0x13,0x4d]
                && body[3..5]==227i16.to_le_bytes()).unwrap();
            let chunks=(24000usize+11).div_ceil(400);
            let shop=crate::map_drive_service091::tests::assembled(&bodies[first..first+chunks],227);
            assert_eq!(shop.len(),24000);assert!(shop.starts_with(b"\x80\x02}(U\x03revK\x05U\x01xT"));
            assert_eq!(&shop[shop.len()-2..],b"u.");
            let once=s.clone();s.receive(&envelope,now).unwrap();same(&s,&once);
        }
        // The legacy fixture keeps its smaller admission bound.
        let mut legacy=pending(now,0);let before=legacy.clone();
        assert!(legacy.receive(&frame(&legacy,&payload(3,23107,248225827),1),now).is_err());same(&legacy,&before);
    }

    #[test]
    fn shared_return_shop_revision_is_bound_to_each_loaded_fixture_atomically() {
        let now = Instant::now();
        for (mut s, expected, wrong) in [(live(now, 0), 3i64, 2i64), (live_secondary(now), 2, 3)] {
            assert_eq!(s.hangar.as_ref().unwrap().shop_sync_revision().unwrap(), expected);
            s.shared_return("unit_cross_fixture_revision", now, &mut Vec::new()).unwrap();
            s.tx.due(now, s.rx).unwrap(); s.receive(&frame(&s, &[9], 1), now).unwrap();
            let before = s.clone(); let mut mismatched = fix04_secondary_warm();
            mismatched[30..38].copy_from_slice(&wrong.to_le_bytes());
            assert!(s.receive(&frame(&s, &mismatched, 1), now).is_err()); same(&s, &before);
            let mut own_revision = fix04_secondary_warm(); own_revision[30..38].copy_from_slice(&expected.to_le_bytes());
            s.receive(&frame(&s, &own_revision, 1), now).unwrap();
            assert_eq!(s.shared.as_ref().unwrap().phase, Phase::Account); assert_eq!(s.shared.as_ref().unwrap().return_mask, 7);
        }
    }

    #[test]
    fn shared_initial_and_return_sync_stream_service_policy_for_each_real_account() {
        let now=Instant::now();
        for secondary in [false,true] {
            for returning in [false,true] {
                let mut s=if secondary {live_secondary(now)}else{live(now,0)};
                let before=s.hangar.as_ref().unwrap().state_sha256();
                let source=s.hangar.as_ref().unwrap().state_bytes().to_vec();
                if returning {
                    s.shared_return("unit_policy_return",now,&mut Vec::new()).unwrap();
                    s.tx.due(now,s.rx).unwrap();s.receive(&frame(&s,&[9],1),now).unwrap();
                    let payload=if secondary {fix04_secondary_warm()}else{warm()};
                    s.receive(&frame(&s,&payload,1),now).unwrap();
                    assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Account);
                } else {
                    s.arena_base=false;s.sync_mask=0;s.request_ids.clear();s.chat_request_ids.clear();
                    s.shared.as_mut().unwrap().phase=Phase::Account;
                    let mut payload=fix04_secondary_warm()[..23].to_vec();payload[7..23].fill(0);
                    s.receive(&frame(&s,&payload,0),now).unwrap();assert_eq!(s.sync_mask,1);
                }
                let mut tx=s.tx.clone();let mut bodies=Vec::new();
                while let Some((_,_,raw))=tx.due(now,s.rx).unwrap() {
                    bodies.push(transport091::parse_interactive(&raw).unwrap().body);
                }
                bodies.extend(s.outbox.iter().cloned());
                let first=bodies.iter().position(|body|body.len()>5 && body[..2]==[0x13,0x4d]
                    &&body[3..5]==226i16.to_le_bytes()).unwrap();
                let chunks=(source.len()+11).div_ceil(400);
                let published=crate::map_drive_service091::tests::assembled(&bodies[first..first+chunks],226);
                let offset=if secondary {605}else{802};let mut expected=source;expected[offset]=1;
                assert_eq!(published,expected);assert_eq!(s.hangar.as_ref().unwrap().state_sha256(),before);
                assert!(s.drive.is_none());assert!(s.drive_account_policy.is_none());
            }
        }
    }
}

#[cfg(test)]
#[path="p10b_special_account_tests.rs"]
mod p10b_special_account_tests;

#[cfg(test)]
pub(crate) mod composition_storage_tests;

#[cfg(test)]
mod garage_fresh32_cursor_tests {
    use super::*;
    fn client()->Client {
        let mut c=Client::new(0);c.join_requested=false;c.return_generation=3;c.return_source_revision=7;
        c.profile13=Some(profile13_session::State::new("e6ef9b6e-1316-4d78-9f6a-18659b03b231".into(),13).unwrap());
        c.profile13.as_mut().unwrap().command_counter=19;c
    }
    #[test]fn garage_fresh32_shared_cursor_commits_once_without_resetting_account_epoch(){
        let mut c=client();let mut expected=c.clone();expected.profile13.as_mut().unwrap().revision=14;
        c.commit_garage_source_revision(13,14).unwrap();
        assert_eq!(c.profile13,expected.profile13);assert_eq!(c.account_incarnation(),4);
        assert_eq!((c.return_source_revision,c.join_requested,c.queue_announced),(7,false,false));
        assert!(c.commit_garage_source_revision(13,14).is_err());assert_eq!(c.profile13,expected.profile13);
        c.commit_garage_source_revision(14,15).unwrap();assert_eq!(c.profile13.as_ref().unwrap().revision,15);
        assert_eq!(c.profile13.as_ref().unwrap().command_counter,19);assert_eq!(c.account_incarnation(),4);
    }
    #[test]fn garage_fresh32_shared_busy_phase_and_wrong_cas_refuse_atomically(){
        for case in 0..6 {
            let mut c=client();match case {
                0=>c.phase=Phase::Enable,1=>c.profile13.as_mut().unwrap().selection=Some(1),
                2=>c.profile13.as_mut().unwrap().in_flight=true,
                3=>c.profile13.as_mut().unwrap().hold_return_pending=true,
                4=>{},_=>{},
            }
            let before=c.profile13.clone();let epoch=c.account_incarnation();
            let(old,next)=match case{4=>(12,13),5=>(13,15),_=>(13,14)};
            assert!(c.commit_garage_source_revision(old,next).is_err());
            assert_eq!(c.profile13,before);assert_eq!(c.account_incarnation(),epoch);
            assert_eq!(c.return_source_revision,7);
        }
    }
}
