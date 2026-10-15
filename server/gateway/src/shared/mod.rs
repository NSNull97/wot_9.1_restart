//! Explicit local two-client test_lab route. The accepted single-client drive
//! route and its frozen profile checks are not generalized through this module.
pub(crate) mod model;
pub(crate) mod aim;
pub(crate) mod pose;
pub(crate) mod geometry;
pub(crate) mod materials;
pub(crate) mod client_marker;
pub(crate) mod ap;
mod impact_wire;
pub(crate) mod terrain;
pub(crate) mod obstacles;
mod terrain_wire;
mod destructible_wire;
pub(crate) mod destructible;
pub(crate) mod fragiles;
pub(crate) mod ram_response;
pub(crate) mod ram_proof;
pub(crate) mod projectile;
pub(crate) mod collision;
pub(crate) mod impact;
pub(crate) mod wire;
mod server;
pub(crate) mod vehicle_profile;
pub use server::serve;
pub use server::serve_integrated;
use super::{Session, Frame, Instant};
use std::io;
use std::collections::VecDeque;
use model::{bad, Command, Input, World};
use crate::{battle091::fire, map_drive_world091 as drive};

/// Keep the first native request envelope within the measured eight-body
/// reliable window (two vehicles plus six area controllers).  Later batches
/// contain areas only; using the same bound keeps the state machine uniform.
const AREA_ANNOUNCEMENT_BATCH: usize = 6;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(super) enum Phase { Account, Enable, Entities, Driving, Leaving }

#[derive(Clone)]
pub(super) struct Client {
    slot: usize,
    phase: Phase,
    view: Option<World>,
    announcement: Option<(u32, bool)>,
    announcement_parts: Vec<(u32, bool)>,
    announced_areas: usize,
    creations: [Option<(u32, bool)>; 2],
    binding: Option<(u32, bool)>,
    area_creation: Option<(u32, bool)>,
    pending_area_scene: bool,
    pending_entity_requests: VecDeque<usize>,
    pending_area_requests: VecDeque<usize>,
    area_scene_sent: u32,
    areas:Vec<(Option<(u32,bool)>,Vec<u8>)>,
    tree_areas:Vec<Vec<u32>>,
    correction: bool,
    ready_sent: [bool; 2],
    commands: Vec<Command>,
    entered: Option<Instant>,
    hangar_since: Option<Instant>,
    shot_cursor: u32,
    impact_cursor: usize,
    health_sent: [Option<i16>; 2],
    owner_health_sent: Option<i16>,
    tracer_started: [bool; model::MAX_SHOTS],
    tracer_stopped: [bool; model::MAX_SHOTS],
}
impl Client {
    fn new(slot: usize) -> Self {
        Self { slot, phase: Phase::Account, view: None, announcement: None, announcement_parts: Vec::new(), announced_areas: 0, creations: [None; 2],
            area_creation: None, pending_area_scene: false, pending_entity_requests: VecDeque::new(), pending_area_requests: VecDeque::new(), area_scene_sent: 0,areas:Vec::new(),tree_areas:Vec::new(), binding: None, correction: false, ready_sent: [false; 2], commands: Vec::new(), entered: None,
            hangar_since: None, shot_cursor: 0, impact_cursor: 0, health_sent: [None; 2], owner_health_sent: None, tracer_started: [false; model::MAX_SHOTS],
            tracer_stopped: [false; model::MAX_SHOTS] }
    }
    pub(super) fn acknowledge(&mut self, cumulative: u32, frame: &Frame) {
        for pending in [&mut self.announcement, &mut self.creations[0], &mut self.binding, &mut self.area_creation] {
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
        if let Some((seq, acked)) = &mut self.creations[1] { *acked |= cumulative > *seq || frame.selective.contains(seq); }
        for (pending,_) in &mut self.areas{if let Some((seq,acked))=pending{*acked|=cumulative>*seq||frame.selective.contains(seq);}}
    }
    fn areas_ready(&self,world:&World)->bool{
        (!world.destructible_enabled()||self.area_creation.is_some_and(|(_,ack)|ack))
            &&world.fragiles.as_ref().is_none_or(|state|self.announced_areas==state.catalog.chunks().len()&&self.areas.len()==state.catalog.chunks().len()&&(self.tree_areas.is_empty()||self.tree_areas.len()==self.areas.len())&&self.areas.iter().all(|(p,_)|p.is_some_and(|(_,a)|a)))
    }
    fn visible(&self) -> [bool; 2] { self.creations.map(|row| row.is_some_and(|(_, ack)| ack)) }
    pub(super) fn needs_flush(&self) -> bool { matches!(self.phase, Phase::Entities | Phase::Driving) }
}

impl Session {
    fn shared_start(&mut self, world: &World, now: Instant) -> io::Result<()> {
        if !self.ready_for_arena_base() { return Err(bad()); }
        let slot = self.shared.as_ref().filter(|c| c.phase == Phase::Account).ok_or_else(|| bad())?.slot;
        world.owned(slot, self.id)?;
        let mut next = self.clone();
        next.tx.enqueue_body(&wire::reset(world, slot)?)?; next.arena_base = true;
        let c = next.shared.as_mut().ok_or_else(|| bad())?;
        c.phase = Phase::Enable; c.view = Some(world.clone()); c.entered = Some(now);
        c.shot_cursor = world.latest_shot();
        c.impact_cursor = world.impacts.len();
        c.tracer_started = [false; model::MAX_SHOTS];
        c.tracer_stopped = [false; model::MAX_SHOTS];
        *self = next;
        println!("SHARED_ENTRY battle={} session={} slot={slot} avatar={} vehicle={} assignment=temporary_{} inventory_changed=false",
            world.id, self.id, wire::avatar_id(slot)?, wire::vehicle_id(slot)?, world.vehicle_kind().label());
        Ok(())
    }
    pub(super) fn shared_payload(&mut self, payload: &[u8], now: Instant, events: &mut Vec<String>) -> io::Result<()> {
        let mut payload = payload;
        let phase = self.shared.as_ref().ok_or_else(|| bad())?.phase;
        if phase == Phase::Account {
            if drive::account_command(payload)?.is_some() {
                events.push(format!("SHARED_WAIT session={} reason=automatic_two_hangar_gate command_applied=false", self.id));
                return Ok(());
            }
            return self.receive_account(payload, events);
        }
        if payload.is_empty() { return Ok(()); }
        let c = self.shared.as_mut().ok_or_else(|| bad())?;
        let world = c.view.as_ref().ok_or_else(|| bad())?;
        if c.phase == Phase::Enable {
            let late = drive::late_queue_info(payload)?;
            if late == Some(false) { return Ok(()); }
            if payload != [9] && late != Some(true) { return Err(bad()); }
            let mut body = wire::announcement(world, c.slot)?;
            if world.destructible_enabled() { body.extend(destructible_wire::announcement()); }
            c.announcement_parts.clear();
            c.announced_areas = 0;
            if let Some(state)=&world.fragiles {
                let chunks=state.catalog.chunks();
                c.areas=vec![(None,Vec::new());chunks.len()];
                c.tree_areas=vec![Vec::new();chunks.len()];
                for i in 0..chunks.len().min(AREA_ANNOUNCEMENT_BATCH) {
                    let record = destructible_wire::area_announcement(i)?;
                    if body.len() + record.len() > 512 {
                        let sequence = self.tx.enqueue_body_tracked(&body)?;
                        c.announcement_parts.push((sequence, false));
                        body = Vec::new();
                    }
                    body.extend(record);
                    c.announced_areas += 1;
                }
            }
            if !body.is_empty() {
                let sequence = self.tx.enqueue_body_tracked(&body)?;
                c.announcement_parts.push((sequence, false));
            }
            let sequence = c.announcement_parts.last().map(|(sequence, _)| *sequence).ok_or_else(|| bad())?;
            c.announcement = Some((sequence, false));
            c.phase = Phase::Entities;
            events.push(format!("SHARED_ANNOUNCED battle={} session={} rows=2 own={} areas={} parts={} reliable_sequence={sequence}", world.id, self.id, wire::vehicle_id(c.slot)?, c.announced_areas, c.announcement_parts.len()));
            return Ok(());
        }
        if payload.first() == Some(&8) && c.phase == Phase::Entities {
            // treeobserve08: six area requests + the first READY compound
            // arrive together before Driving. Only a complete owned READY may
            // follow the fixed request prefix; arbitrary methods remain closed.
            let prefix_len = payload.chunks_exact(7).take_while(|raw| raw[0] == 8).count() * 7;
            let (requests, tail) = payload.split_at(prefix_len);
            if !tail.is_empty() && (payload.len() > 512 || wire::ready(tail, c.slot).is_err()) { return Err(bad()); }
            if c.announcement.is_none()
                || requests.is_empty()
                || requests.len() > 7*(2+if world.destructible_enabled(){1}else{c.announced_areas}) { return Err(bad()); }
            // Original requests can piggyback vehicles and area controllers.
            // Queue the complete envelope first, then release only as much as
            // the reliable eight-body window can carry. Session's outer receive
            // clone makes the whole envelope atomic on malformed input.
            if c.tree_areas.len()!=c.areas.len(){c.tree_areas=vec![Vec::new();c.areas.len()];}
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
        if wire::ready(payload, c.slot).is_ok() {
            if c.phase == Phase::Driving { return Ok(()); }
            if c.phase != Phase::Entities || !c.creations[c.slot].is_some_and(|(_, ack)| ack) { return Err(bad()); }
            let sequence = self.tx.enqueue_body_tracked(&wire::binding(world, c.slot, now)?)?;
            c.binding = Some((sequence, false)); c.phase = Phase::Driving;
            // Loading/reconnecting a scene is not a replay of prior gun effects.
            c.shot_cursor = world.latest_shot();
            c.impact_cursor = world.impacts.len();
            c.tracer_started = [false; model::MAX_SHOTS];
            c.tracer_stopped = [false; model::MAX_SHOTS];
            for slot in 0..2 { c.ready_sent[slot] = slot == c.slot || world.actors[slot].ready; }
            events.push(format!("SHARED_READY battle={} session={} own={} reliable_sequence={sequence} tick={}", world.id, self.id, wire::vehicle_id(c.slot)?, world.tick));
            return Ok(());
        }
        if c.phase != Phase::Driving { return Err(bad()); }
        // A complete mixed input envelope is validated inside Session's receive
        // clone. No world command can escape a malformed later record/piggyback.
        if payload.len() > 512 { return Err(bad()); }
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
            let size = match id {
                // Native clients may piggyback area requests with their first
                // aim/movement envelope after READY.  A request is the one
                // fixed seven-byte VAR2 record; it has no length field.
                8 => 7,
                6 => 1, 2 => 17, 3 => 22,
                0x88 | 0x89 | 0x8a | 0x8d | 0x8e | 0x8f | 0x0d | 0x0f | 0x99 => {
                    if payload.len() - at < 3 { return Err(bad()); }
                    3 + u16::from_le_bytes([payload[at+1], payload[at+2]]) as usize
                },
                _ => return Err(bad()),
            };
            let raw = payload.get(at..at+size).ok_or_else(|| bad())?; at += size;
            if id == 8 {
                if c.tree_areas.len()!=c.areas.len(){c.tree_areas=vec![Vec::new();c.areas.len()];}
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
                        if c.creations[slot].is_some() || c.pending_entity_requests.contains(&slot) { return Err(bad()); }
                        c.pending_entity_requests.push_back(slot);
                    }
                }
            } else if id == 0x0d {
                if world.actors.get(c.slot).is_none_or(|actor| actor.health != 0)
                    || !c.correction || !c.binding.is_some_and(|(_,ack)| ack) { return Err(bad()); }
                wire::postmortem_rebind(raw,c.slot)?;
                events.push(format!("SHARED_POSTMORTEM_REBIND session={} slot={} target={} authority_changed=false",self.id,c.slot,wire::vehicle_id(c.slot)?));
            } else if let Some(commands) = fire::parse(raw)? {
                if !c.correction { return Err(bad()); }
                c.commands.extend(commands.into_iter().map(Command::Fire));
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
                            if at != payload.len() { return Err(bad()); }
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
                    events.push(format!("SHARED_AREA_CREATED battle={} session={} entity={} scene_version={} reliable_sequence={sequence}", world.id,next.id,destructible_wire::ENTITY_ID,world.scene_version()));
                }
                Request::Vehicle(slot) => {
                    let sequence = next.tx.enqueue_body_tracked(&wire::create_vehicle(&world, slot)?)?;
                    let c = next.shared.as_mut().ok_or_else(|| bad())?;
                    c.creations[slot] = Some((sequence, false));
                    c.health_sent[slot] = Some(world.actors[slot].health);
                    events.push(format!("SHARED_ENTITY_CREATED battle={} session={} entity={} own={} reliable_sequence={sequence}", world.id, next.id, wire::vehicle_id(slot)?, slot == c.slot));
                }
                Request::Area(area) => {
                    let state = world.fragiles.as_ref().ok_or_else(|| bad())?;
                    let chunk = state.catalog.chunks().get(area).copied().ok_or_else(|| bad())?;
                    let indices = state.native_destroyed(chunk);
                    let values = state.native_fragile_values(chunk);
                    let trees = state.native_fallen_trees(chunk);
                    let sequence = next.tx.enqueue_body_tracked(&destructible_wire::area_create_state(area,chunk,&values,&trees)?)?;
                    let c = next.shared.as_mut().ok_or_else(|| bad())?;
                    if c.areas.get(area).is_none_or(|(pending, _)| pending.is_some()) { return Err(bad()); }
                    c.areas[area] = (Some((sequence,false)), indices);
                    c.tree_areas[area] = trees;
                    events.push(format!("SHARED_CATALOG_AREA_CREATED battle={} session={} entity={} chunk={} scene={} reliable_sequence={sequence}",world.id,next.id,destructible_wire::area_id(area)?,chunk,world.scene_version()));
                }
            }
        }
        *self = next;
        self.flush_shared_announcements(events)?;
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
