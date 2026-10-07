//! Explicit local two-client test_lab route. The accepted single-client drive
//! route and its frozen profile checks are not generalized through this module.
mod model;
mod aim;
mod projectile;
mod wire;
mod server;
pub use server::serve;
use super::{Session, Frame, Instant};
use std::io;
use model::{bad, Command, Input, World};
use crate::{battle091::fire, map_drive_world091 as drive};

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Phase { Account, Enable, Entities, Driving, Leaving }

#[derive(Clone)]
pub(super) struct Client {
    slot: usize,
    phase: Phase,
    view: Option<World>,
    announcement: Option<(u32, bool)>,
    creations: [Option<(u32, bool)>; 2],
    binding: Option<(u32, bool)>,
    correction: bool,
    ready_sent: [bool; 2],
    commands: Vec<Command>,
    entered: Option<Instant>,
    hangar_since: Option<Instant>,
    shot_cursor: u32,
    tracer_started: [bool; model::MAX_SHOTS],
    tracer_stopped: [bool; model::MAX_SHOTS],
}
impl Client {
    fn new(slot: usize) -> Self {
        Self { slot, phase: Phase::Account, view: None, announcement: None, creations: [None; 2],
            binding: None, correction: false, ready_sent: [false; 2], commands: Vec::new(), entered: None,
            hangar_since: None, shot_cursor: 0, tracer_started: [false; model::MAX_SHOTS],
            tracer_stopped: [false; model::MAX_SHOTS] }
    }
    pub(super) fn acknowledge(&mut self, cumulative: u32, frame: &Frame) {
        for pending in [&mut self.announcement, &mut self.creations[0], &mut self.binding] {
            if let Some((seq, acked)) = pending { *acked |= cumulative > *seq || frame.selective.contains(seq); }
        }
        if let Some((seq, acked)) = &mut self.creations[1] { *acked |= cumulative > *seq || frame.selective.contains(seq); }
    }
    fn visible(&self) -> [bool; 2] { self.creations.map(|row| row.is_some_and(|(_, ack)| ack)) }
}

impl Session {
    fn shared_start(&mut self, world: &World, now: Instant) -> io::Result<()> {
        if !self.ready_for_arena_base() { return Err(bad()); }
        let slot = self.shared.as_ref().filter(|c| c.phase == Phase::Account).ok_or_else(bad)?.slot;
        world.owned(slot, self.id)?;
        let mut next = self.clone();
        next.tx.enqueue_body(&wire::reset(world, slot)?)?; next.arena_base = true;
        let c = next.shared.as_mut().ok_or_else(bad)?;
        c.phase = Phase::Enable; c.view = Some(world.clone()); c.entered = Some(now);
        c.shot_cursor = world.latest_shot();
        c.tracer_started = [false; model::MAX_SHOTS];
        c.tracer_stopped = [false; model::MAX_SHOTS];
        *self = next;
        println!("SHARED_ENTRY battle={} session={} slot={slot} avatar={} vehicle={} assignment=temporary_ms1 inventory_changed=false",
            world.id, self.id, wire::avatar_id(slot)?, wire::vehicle_id(slot)?);
        Ok(())
    }
    pub(super) fn shared_payload(&mut self, payload: &[u8], now: Instant, events: &mut Vec<String>) -> io::Result<()> {
        let phase = self.shared.as_ref().ok_or_else(bad)?.phase;
        if phase == Phase::Account {
            if drive::account_command(payload)?.is_some() {
                events.push(format!("SHARED_WAIT session={} reason=automatic_two_hangar_gate command_applied=false", self.id));
                return Ok(());
            }
            return self.receive_account(payload, events);
        }
        if payload.is_empty() { return Ok(()); }
        let c = self.shared.as_mut().ok_or_else(bad)?;
        let world = c.view.as_ref().ok_or_else(bad)?;
        if c.phase == Phase::Enable {
            let late = drive::late_queue_info(payload)?;
            if late == Some(false) { return Ok(()); }
            if payload != [9] && late != Some(true) { return Err(bad()); }
            let sequence = self.tx.enqueue_body_tracked(&wire::announcement(world, c.slot)?)?;
            c.announcement = Some((sequence, false)); c.phase = Phase::Entities;
            events.push(format!("SHARED_ANNOUNCED battle={} session={} rows=2 own={} reliable_sequence={sequence}", world.id, self.id, wire::vehicle_id(c.slot)?));
            return Ok(());
        }
        if let Some(slots) = wire::entity_requests(payload)? {
            if !matches!(c.phase, Phase::Entities | Phase::Driving) || !c.announcement.is_some_and(|(_, ack)| ack) { return Err(bad()); }
            for slot in slots {
                if c.creations[slot].is_some() { return Err(bad()); }
                let sequence = self.tx.enqueue_body_tracked(&wire::create_vehicle(world, slot)?)?;
                c.creations[slot] = Some((sequence, false));
                events.push(format!("SHARED_ENTITY_CREATED battle={} session={} entity={} own={} reliable_sequence={sequence}", world.id, self.id, wire::vehicle_id(slot)?, slot == c.slot));
            }
            return Ok(());
        }
        if wire::ready(payload, c.slot).is_ok() {
            if c.phase == Phase::Driving { return Ok(()); }
            if c.phase != Phase::Entities || !c.creations[c.slot].is_some_and(|(_, ack)| ack) { return Err(bad()); }
            let sequence = self.tx.enqueue_body_tracked(&wire::binding(world, c.slot, now)?)?;
            c.binding = Some((sequence, false)); c.phase = Phase::Driving;
            // Loading/reconnecting a scene is not a replay of prior gun effects.
            c.shot_cursor = world.latest_shot();
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
            let id = payload[at];
            let size = match id {
                6 => 1, 2 => 17, 3 => 22,
                0x88 | 0x89 | 0x8a | 0x8d | 0x8e | 0x8f | 0x0f | 0x99 => {
                    if payload.len() - at < 3 { return Err(bad()); }
                    3 + u16::from_le_bytes([payload[at+1], payload[at+2]]) as usize
                },
                _ => return Err(bad()),
            };
            let raw = payload.get(at..at+size).ok_or_else(bad)?; at += size;
            if let Some(commands) = fire::parse(raw)? {
                if !c.correction { return Err(bad()); }
                c.commands.extend(commands.into_iter().map(Command::Fire));
            } else if let Some(intent) = wire::aim_intent(raw, c.slot)? {
                // The native initializer can emit its first target before
                // ACK6 in the same envelope. It is only an intent: simulation
                // cannot advance it before the binding/correction is accepted.
                if !c.binding.is_some_and(|(_, ack)| ack) { return Err(bad()); }
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
                            c.commands.push(Command::Move(Input { throttle: input.throttle, steer: input.steer }));
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
}
