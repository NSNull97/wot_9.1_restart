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
pub(super) enum Phase { Account, Enable, Entities, Driving, Leaving, Returning }

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
    return_generation: u32,
    return_mask: u8,
    join_requested: bool,
    queue_announced: bool,
}
impl Client {
    fn new(slot: usize) -> Self {
        Self { slot, phase: Phase::Account, view: None, announcement: None, announcement_parts: Vec::new(), announced_areas: 0, creations: [None; 2],
            area_creation: None, pending_area_scene: false, pending_entity_requests: VecDeque::new(), pending_area_requests: VecDeque::new(), area_scene_sent: 0,areas:Vec::new(),tree_areas:Vec::new(), binding: None, correction: false, ready_sent: [false; 2], commands: Vec::new(), entered: None,
            hangar_since: None, shot_cursor: 0, impact_cursor: 0, health_sent: [None; 2], owner_health_sent: None, tracer_started: [false; model::MAX_SHOTS],
            tracer_stopped: [false; model::MAX_SHOTS], return_generation: 0, return_mask: 0, join_requested: true, queue_announced: false }
    }
    /// A new battle gets fresh entity/publication state while the Account
    /// return epoch remains monotonic on its existing authenticated channel.
    fn reset_for_battle(&mut self, slot: usize) {
        let generation = self.return_generation;
        let queue_announced = self.queue_announced;
        *self = Self::new(slot);
        self.return_generation = generation;
        self.queue_announced = queue_announced;
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
        next.drive_return_account = None;
        let c = next.shared.as_mut().ok_or_else(|| bad())?;
        c.return_generation = c.return_generation.checked_add(1).ok_or_else(|| bad())?;
        c.phase = Phase::Enable; c.view = Some(world.clone()); c.entered = Some(now);
        c.queue_announced = false;
        c.shot_cursor = world.latest_shot();
        c.impact_cursor = world.impacts.len();
        c.tracer_started = [false; model::MAX_SHOTS];
        c.tracer_stopped = [false; model::MAX_SHOTS];
        *self = next;
        println!("SHARED_ENTRY battle={} session={} slot={slot} avatar={} vehicle={} assignment=temporary_{} inventory_changed=false",
            world.id, self.id, wire::avatar_id(slot)?, wire::vehicle_id(slot)?, world.vehicle_kind().label());
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
        next.outbox.push_back(body);
        next.arena_base = false;
        let c = next.shared.as_mut().ok_or_else(|| bad())?;
        c.phase = Phase::Returning; c.return_mask = 0; c.join_requested = false; c.queue_announced = false;
        c.hangar_since = None; c.entered = Some(now); c.commands.clear();
        c.pending_entity_requests.clear(); c.pending_area_requests.clear(); c.pending_area_scene = false;
        // Keep the old view and binding solely to validate already queued
        // Avatar envelopes. No authoritative command can leave Returning.
        next.drain_outbox()?;
        *self = next;
        events.push(format!("SHARED_RETURN session={} generation={generation} reason={reason} channel_reused=true account_recreated=true inventory_changed=false", self.id));
        Ok(())
    }

    fn shared_account_payload(&mut self, payload: &[u8], events: &mut Vec<String>) -> io::Result<()> {
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
                            if rev != 1 || b != 0 || self.outbox.len() >= 128 { return Err(bad()); }
                            self.account_cache_hash = if a == 0 { None } else { Some(a) };
                            self.outbox.push_back(crate::hangar091::response_refresh(&request)?);
                        },
                        300 => {
                            if rev != 3 || !(0..=16448).contains(&a) || (a == 0 && b != 0) { return Err(bad()); }
                            let bodies = crate::hangar091::response(&request, self.hangar.as_ref().ok_or_else(|| bad())?)?;
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
        if phase == Phase::Account {
            return self.shared_account_payload(payload, events);
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
        c.return_generation = 1; c.binding = Some((0, true)); c.creations = [Some((0, true)); 2];
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
    // Exact accepted single-client Ride07 native sync/chat bundle. The shared
    // lifecycle must consume the same real Account contract on either slot.
    fn warm() -> Vec<u8> {
        let text = "8e1400e20064000100000000000000d66e1203000000008e1400e3002c01030000000000000006020000250f8ecd8e1400e400580201000000000000004d72c26a0000000093190001000000000000000a00000000ffffffffffffffff000000009319000200000000000000090000000000000000000000000000000093190003000000000000001e00000000000000000000000000000000";
        text.as_bytes().chunks_exact(2).map(|pair| u8::from_str_radix(std::str::from_utf8(pair).unwrap(), 16).unwrap()).collect()
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
        let before = s.clone(); postmortem[7..].copy_from_slice(&wire::vehicle_id(0).unwrap().to_le_bytes());
        assert!(s.receive(&frame(&s, &postmortem, 0), now).is_err()); same(&s, &before);
    }

    #[test]
    fn shared_return_queue_failure_does_not_commit_half_return() {
        let now = Instant::now(); let mut s = live(now, 0); s.outbox.push_back(vec![0; 513]);
        let before = s.clone(); let mut events = Vec::new();
        assert!(s.shared_return("unit_bad_queue", now, &mut events).is_err()); same(&s, &before);
        assert!(events.is_empty()); assert_eq!(s.shared.as_ref().unwrap().phase, Phase::Driving);
    }
}
