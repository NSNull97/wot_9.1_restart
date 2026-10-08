//! Bounded native MS-1 fire/reload command slice for the accepted #717 arena.
//!
//! The incoming BaseMethods are exact zero-argument records.  The server owns
//! the AP count and cooldown; client coordinates, clocks, shell IDs and hit
//! results never enter this module.  Projectile, collision and damage are a
//! later card.

use std::{io, time::{Duration, Instant}};

pub const VEHICLE_SHOOT: u8 = 0x88;
pub const VEHICLE_REPLENISH_AMMO: u8 = 0x89;
pub const UPDATE_VEHICLE_AMMO: u8 = 0x44;
pub const UPDATE_VEHICLE_GUN_RELOAD_TIME: u8 = 0x46;
pub const ENTITY_METHOD_PREFIX: u8 = 0x13;
pub const MS1_AP: u32 = super::native_ammo::MS1_SHELL;
pub const MS1_INITIAL_AMMO: u16 = super::native_ammo::MS1_SHELL_COUNT;
pub const MS1_RELOAD_SECONDS: f32 = super::native_ammo::MS1_RELOAD_SECONDS;
pub const MAX_COMMANDS: usize = 16;
pub const MAX_PAYLOAD: usize = 512;

fn invalid(reason: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, reason)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Command {
    Shoot,
    ReplenishAmmo,
}

/// Parse only the two verified Avatar BaseMethods used by this card.
///
/// `Ok(None)` means the payload belongs to another already-supported method
/// family and must be passed to that family parser.  Once a fire method is the
/// first record, the complete payload must be a bounded stream of fire methods;
/// mixed or truncated records fail closed instead of partially applying.
pub fn parse(payload: &[u8]) -> io::Result<Option<Vec<Command>>> {
    if payload.is_empty() {
        return Ok(None);
    }
    if payload.len() > MAX_PAYLOAD {
        return Err(invalid("native fire payload exceeds bound"));
    }
    if !matches!(payload[0], VEHICLE_SHOOT | VEHICLE_REPLENISH_AMMO) {
        return Ok(None);
    }
    let mut at = 0usize;
    let mut commands = Vec::new();
    while at < payload.len() {
        if commands.len() >= MAX_COMMANDS || payload.len() - at < 3 {
            return Err(invalid("native fire command stream bound"));
        }
        let method = payload[at];
        let length = u16::from_le_bytes([payload[at + 1], payload[at + 2]]) as usize;
        if !matches!(method, VEHICLE_SHOOT | VEHICLE_REPLENISH_AMMO) || length != 0 {
            return Err(invalid("native fire method shape"));
        }
        at += 3;
        commands.push(match method {
            VEHICLE_SHOOT => Command::Shoot,
            VEHICLE_REPLENISH_AMMO => Command::ReplenishAmmo,
            _ => unreachable!(),
        });
    }
    if commands.is_empty() {
        return Err(invalid("empty native fire command stream"));
    }
    Ok(Some(commands))
}

/// Parse the contiguous fire-method prefix of a compound Avatar envelope.
///
/// BigWorld may batch `vehicle_shoot` with an already measured aim/movement
/// method in one reliable body.  The strict `parse` function intentionally
/// remains whole-body-only for the legacy route; map-drive uses this bounded
/// prefix reader and validates the remaining methods with its own parser.
pub fn parse_prefix(payload: &[u8]) -> io::Result<Option<(Vec<Command>, usize)>> {
    if payload.is_empty() || !matches!(payload[0], VEHICLE_SHOOT | VEHICLE_REPLENISH_AMMO) {
        return Ok(None);
    }
    if payload.len() > MAX_PAYLOAD { return Err(invalid("native fire payload exceeds bound")); }
    let mut at = 0usize;
    let mut commands = Vec::new();
    while at < payload.len() {
        if commands.len() >= MAX_COMMANDS || payload.len() - at < 3 { break; }
        let method = payload[at];
        if !matches!(method, VEHICLE_SHOOT | VEHICLE_REPLENISH_AMMO) { break; }
        let length = u16::from_le_bytes([payload[at + 1], payload[at + 2]]) as usize;
        if length != 0 { return Err(invalid("native fire method shape")); }
        at += 3;
        commands.push(match method {
            VEHICLE_SHOOT => Command::Shoot,
            VEHICLE_REPLENISH_AMMO => Command::ReplenishAmmo,
            _ => unreachable!(),
        });
    }
    if commands.is_empty() { return Err(invalid("empty native fire command stream")); }
    Ok(Some((commands, at)))
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Outcome {
    AcceptedShot { ammo_remaining: u16 },
    RejectedReload,
    RejectedNoAmmo,
    ReplenishUnsupported,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct State {
    ammo: u16,
    reload_until: Option<Instant>,
    accepted_shots: u32,
    rejected_shots: u32,
    replenish_requests: u32,
}

impl State {
    pub fn new() -> Self {
        Self {
            ammo: MS1_INITIAL_AMMO,
            reload_until: None,
            accepted_shots: 0,
            rejected_shots: 0,
            replenish_requests: 0,
        }
    }

    pub fn ammo(&self) -> u16 { self.ammo }
    pub fn accepted_shots(&self) -> u32 { self.accepted_shots }
    pub fn rejected_shots(&self) -> u32 { self.rejected_shots }
    pub fn replenish_requests(&self) -> u32 { self.replenish_requests }
    pub fn reload_until(&self) -> Option<Instant> { self.reload_until }

    /// Clear the server-owned cooldown only once its monotonic deadline has
    /// passed.  The caller queues the matching native client callback after
    /// this transition succeeds; a full transport queue must therefore leave
    /// the state unchanged by operating on a cloned `State`.
    pub fn finish_reload_if_due(&mut self, now: Instant) -> bool {
        if self.reload_until.is_some_and(|until| now >= until) {
            self.reload_until = None;
            true
        } else {
            false
        }
    }

    /// Apply a bounded command stream against monotonic server time.
    ///
    /// Rejected attempts are observable outcomes but do not consume ammo or
    /// move the cooldown.  Replenishment is deliberately observable only: the
    /// card does not invent an economy or free ammunition grant.
    pub fn apply(&mut self, commands: &[Command], now: Instant) -> io::Result<Vec<Outcome>> {
        if commands.is_empty() || commands.len() > MAX_COMMANDS {
            return Err(invalid("native fire command count"));
        }
        let mut next = self.clone();
        let mut outcomes = Vec::with_capacity(commands.len());
        for command in commands {
            match command {
                Command::Shoot => {
                    if next.reload_until.is_some_and(|until| now < until) {
                        next.rejected_shots = next.rejected_shots.checked_add(1)
                            .ok_or_else(|| invalid("native fire counter overflow"))?;
                        outcomes.push(Outcome::RejectedReload);
                    } else if next.ammo == 0 {
                        next.rejected_shots = next.rejected_shots.checked_add(1)
                            .ok_or_else(|| invalid("native fire counter overflow"))?;
                        next.reload_until = None;
                        outcomes.push(Outcome::RejectedNoAmmo);
                    } else {
                        next.ammo -= 1;
                        next.accepted_shots = next.accepted_shots.checked_add(1)
                            .ok_or_else(|| invalid("native fire counter overflow"))?;
                        next.reload_until = Some(now.checked_add(Duration::from_secs_f32(MS1_RELOAD_SECONDS))
                            .ok_or_else(|| invalid("native reload clock overflow"))?);
                        outcomes.push(Outcome::AcceptedShot { ammo_remaining: next.ammo });
                    }
                }
                Command::ReplenishAmmo => {
                    next.replenish_requests = next.replenish_requests.checked_add(1)
                        .ok_or_else(|| invalid("native replenish counter overflow"))?;
                    outcomes.push(Outcome::ReplenishUnsupported);
                }
            }
        }
        *self = next;
        Ok(outcomes)
    }
}

/// Encode the two verified server→client callbacks after one accepted shot.
/// The fixed AP row is the same native method family that rendered the P03D
/// panel; only its server-owned quantity changes.  The reload callback carries
/// the checked MS-1 2.5 s catalog value as both timeLeft and baseTime.
pub fn accepted_shot_body(ammo_remaining: u16, vehicle_entity_id: u32) -> io::Result<Vec<u8>> {
    if ammo_remaining >= MS1_INITIAL_AMMO || vehicle_entity_id != crate::arena_vehicle091::VEHICLE_ENTITY_ID {
        return Err(invalid("native shot state outside pinned MS-1 bounds"));
    }
    let mut body = Vec::with_capacity(25);
    body.extend([ENTITY_METHOD_PREFIX, UPDATE_VEHICLE_AMMO]);
    body.extend(i32::try_from(MS1_AP).map_err(|_| invalid("native AP descriptor overflow"))?.to_le_bytes());
    body.extend(ammo_remaining.to_le_bytes());
    body.push(0); // single-shot quantity in clip
    body.extend(0i16.to_le_bytes()); // no clip time remaining
    body.extend([ENTITY_METHOD_PREFIX, UPDATE_VEHICLE_GUN_RELOAD_TIME]);
    body.extend(vehicle_entity_id.to_le_bytes());
    body.extend(MS1_RELOAD_SECONDS.to_le_bytes());
    body.extend(MS1_RELOAD_SECONDS.to_le_bytes());
    if body.len() != 25 {
        return Err(invalid("native shot callback body size"));
    }
    Ok(body)
}

/// Encode the server→client callback that ends the single-shot reload.  The
/// vehicle id and catalog base time are fixed by the pinned MS-1 profile; the
/// client must receive `timeLeft=0` or it keeps `aim.isGunReload()` asserted.
pub fn completed_reload_body(vehicle_entity_id: u32) -> io::Result<Vec<u8>> {
    if vehicle_entity_id != crate::arena_vehicle091::VEHICLE_ENTITY_ID {
        return Err(invalid("native reload completion vehicle entity"));
    }
    let mut body = Vec::with_capacity(2 + 4 + 4 + 4);
    body.extend([ENTITY_METHOD_PREFIX, UPDATE_VEHICLE_GUN_RELOAD_TIME]);
    body.extend(vehicle_entity_id.to_le_bytes());
    body.extend(0.0f32.to_le_bytes());
    body.extend(MS1_RELOAD_SECONDS.to_le_bytes());
    if body.len() != 14 {
        return Err(invalid("native reload completion body size"));
    }
    Ok(body)
}

pub fn outcome_name(outcome: Outcome) -> &'static str {
    match outcome {
        Outcome::AcceptedShot { .. } => "accepted",
        Outcome::RejectedReload => "reload",
        Outcome::RejectedNoAmmo => "no_ammo",
        Outcome::ReplenishUnsupported => "replenish_unsupported",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::arena_vehicle091::VEHICLE_ENTITY_ID;

    fn shot() -> [u8; 3] { [VEHICLE_SHOOT, 0, 0] }
    fn replenish() -> [u8; 3] { [VEHICLE_REPLENISH_AMMO, 0, 0] }

    #[test]
    fn exact_zero_arg_methods_parse_and_other_families_remain_unclaimed() {
        assert_eq!(parse(&shot()).unwrap(), Some(vec![Command::Shoot]));
        assert_eq!(parse(&[replenish(), shot()].concat()).unwrap(),
            Some(vec![Command::ReplenishAmmo, Command::Shoot]));
        assert_eq!(parse(&[0x8a, 1, 0, 0]).unwrap(), None);
        assert_eq!(parse(&[]).unwrap(), None);
        let mut compound = shot().to_vec(); compound.extend([0x8e, 8, 0]); compound.extend([0; 8]);
        let (commands, consumed) = parse_prefix(&compound).unwrap().unwrap();
        assert_eq!(commands, vec![Command::Shoot]);
        assert_eq!(consumed, 3);
    }

    #[test]
    fn malformed_or_mixed_stream_fails_before_any_domain_application() {
        let mut oversized = vec![VEHICLE_SHOOT, 0, 0];
        oversized.extend(std::iter::repeat_n(0, 130));
        for payload in [
            vec![VEHICLE_SHOOT],
            vec![VEHICLE_SHOOT, 1, 0, 0],
            vec![VEHICLE_SHOOT, 0, 0, 0x8a, 1, 0, 0],
            vec![VEHICLE_SHOOT, 0, 0, VEHICLE_REPLENISH_AMMO, 1, 0],
            oversized,
        ] {
            assert!(parse(&payload).is_err(), "payload={payload:?}");
        }
        assert!(parse(&[0; MAX_PAYLOAD + 1]).is_err());
    }

    #[test]
    fn accepted_shot_consumes_one_ap_and_enforces_monotonic_reload() {
        let t = Instant::now();
        let mut state = State::new();
        assert_eq!(state.apply(&[Command::Shoot], t).unwrap(),
            vec![Outcome::AcceptedShot { ammo_remaining: 19 }]);
        assert_eq!(state.ammo(), 19);
        assert_eq!(state.apply(&[Command::Shoot], t + Duration::from_millis(1)).unwrap(),
            vec![Outcome::RejectedReload]);
        assert_eq!(state.ammo(), 19);
        assert_eq!(state.apply(&[Command::Shoot], t + Duration::from_secs_f32(MS1_RELOAD_SECONDS)).unwrap(),
            vec![Outcome::AcceptedShot { ammo_remaining: 18 }]);
        assert_eq!(state.ammo(), 18);
    }

    #[test]
    fn no_ammo_and_replenish_are_fail_closed_without_free_grant() {
        let t = Instant::now();
        let mut state = State::new();
        for i in 0..MS1_INITIAL_AMMO {
            state.apply(&[Command::Shoot], t + Duration::from_secs(3 * u64::from(i))).unwrap();
        }
        assert_eq!(state.ammo(), 0);
        assert_eq!(state.apply(&[Command::Shoot], t + Duration::from_secs(100)).unwrap(),
            vec![Outcome::RejectedNoAmmo]);
        assert_eq!(state.apply(&[Command::ReplenishAmmo], t + Duration::from_secs(100)).unwrap(),
            vec![Outcome::ReplenishUnsupported]);
        assert_eq!(state.ammo(), 0);
    }

    #[test]
    fn callback_bytes_are_fixed_and_server_owned() {
        let body = accepted_shot_body(19, VEHICLE_ENTITY_ID).unwrap();
        assert_eq!(body, vec![
            0x13, 0x44, 0x0a, 0x0a, 0, 0, 19, 0, 0, 0, 0,
            0x13, 0x46, 0x03, 0, 0x10, 9,
            0, 0, 32, 64, 0, 0, 32, 64,
        ]);
        assert_eq!(body.len(), 25);
        assert!(accepted_shot_body(20, VEHICLE_ENTITY_ID).is_err());
        assert!(accepted_shot_body(19, VEHICLE_ENTITY_ID + 1).is_err());
    }

    #[test]
    fn reload_completion_clears_at_deadline_and_callback_is_zero_left() {
        let t = Instant::now();
        let mut state = State::new();
        state.apply(&[Command::Shoot], t).unwrap();
        assert!(!state.finish_reload_if_due(t + Duration::from_millis(2499)));
        assert!(state.finish_reload_if_due(t + Duration::from_secs_f32(MS1_RELOAD_SECONDS)));
        assert_eq!(state.reload_until(), None);
        assert!(!state.finish_reload_if_due(t + Duration::from_secs(3)));
        assert_eq!(completed_reload_body(VEHICLE_ENTITY_ID).unwrap(), vec![
            0x13, 0x46, 0x03, 0, 0x10, 9,
            0, 0, 0, 0,
            0, 0, 32, 64,
        ]);
        assert!(completed_reload_body(VEHICLE_ENTITY_ID + 1).is_err());
    }

    #[test]
    fn apply_is_atomic_for_counter_or_command_errors() {
        let t = Instant::now();
        let mut state = State::new();
        let before = state.clone();
        assert!(state.apply(&[], t).is_err());
        assert_eq!(state, before);
    }
}
