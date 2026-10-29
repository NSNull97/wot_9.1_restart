//! AV-01: #717 battle feedback that the gateway did not publish before —
//! anonymous tracers of hidden shooters, the own-vehicle hit indicator, the
//! shooter's shot-result voice, the spotter's scout event, engine mode and
//! damage stickers. Research and statuses: docs/plans/AV01_BATTLE_FEEDBACK.md.
//!
//! Codecs and presentation policies only: nothing here decides a hit, damage,
//! visibility or credit. Callers own recipient visibility and queue order.

use std::io;
use super::{model, wire, projectile::Projectile};
use super::impact_wire::ShotOutcome;

fn bad(reason: &'static str) -> io::Error { io::Error::new(io::ErrorKind::InvalidData, reason) }

/// Project policy (the original start point of a hidden shooter's tracer is
/// UNKNOWN): the reference start moves this far along the server ballistic
/// path, so the recipient never receives the hidden muzzle position.
pub const HIDDEN_TRACER_OFFSET_M: f32 = 40.0;
/// Damage stickers kept per vehicle: VAR1 value = i32 count + 8 bytes each.
pub const MAX_STICKERS: usize = 30;

/// Avatar.showTracer (0x4c) with shooterID 0 and a reference point advanced
/// along the trajectory. #717 showTracer line 1683 accepts a missing shooter
/// entity and then draws from refStartPoint. None: the flight is too short.
pub fn anonymous_tracer(p: &Projectile, effects: u8) -> io::Result<Option<Vec<u8>>> {
    if p.sequence == 0 || p.sequence as usize > model::MAX_BATTLE_SHOTS
        || !p.origin.iter().chain(p.velocity.iter()).chain(p.terminal.iter()).all(|v| v.is_finite())
        || !p.gravity.is_finite() || p.gravity <= 0.0 || !p.max_distance.is_finite() || p.max_distance <= 0.0
    { return Err(bad("AV-01 anonymous tracer input")); }
    let span: f32 = (0..3).map(|i| (p.terminal[i] - p.origin[i]).powi(2)).sum::<f32>().sqrt();
    let speed: f32 = p.velocity.iter().map(|v| v * v).sum::<f32>().sqrt();
    if speed <= 0.0 { return Err(bad("AV-01 anonymous tracer speed")); }
    if span <= HIDDEN_TRACER_OFFSET_M + 1.0 || p.max_distance <= HIDDEN_TRACER_OFFSET_M + 1.0 { return Ok(None); }
    let t = HIDDEN_TRACER_OFFSET_M / speed;
    let start = super::projectile::position_at(p.origin, p.velocity, p.gravity, t);
    let velocity = [p.velocity[0], p.velocity[1] - p.gravity * t, p.velocity[2]];
    let mut b = vec![0x13, 0x4c];
    b.extend(0u32.to_le_bytes());
    b.extend(p.sequence.to_le_bytes());
    b.push(effects);
    for v in start.iter().chain(velocity.iter()) { b.extend(v.to_le_bytes()); }
    b.extend(p.gravity.to_le_bytes());
    b.extend((p.max_distance - HIDDEN_TRACER_OFFSET_M).to_le_bytes());
    if b.len() != 43 { return Err(bad("AV-01 anonymous tracer length")); }
    Ok(Some(b))
}

/// Avatar.showOwnVehicleHitDirection (fixed exposed6, 0x41): FLOAT32 yaw, BOOL.
/// #717 passes hitDirYaw unchanged to Aim.showHit → _DamageIndicator.setup →
/// component.wg_globalYaw (VERIFIED avatar.pyc 1498, aims.pyc 372/853/935): a
/// world (global) yaw, the hull/camera rotation is applied by the native
/// component. The yaw is the shell's horizontal flight heading (BigWorld yaw =
/// atan2(x, z)), i.e. the hit vector. Owner native 2026-10-29: the reverse
/// heading drew the indicator on the opposite side. Gravity is vertical, so the
/// launch velocity gives the impact heading without any shooter coordinate.
pub fn hit_direction(velocity: [f32; 3], is_damage: bool) -> io::Result<Vec<u8>> {
    if !velocity.iter().all(|v| v.is_finite()) || velocity[0] == 0.0 && velocity[2] == 0.0 {
        return Err(bad("AV-01 hit direction"));
    }
    let yaw = velocity[0].atan2(velocity[2]);
    let mut b = vec![0x13, 0x41];
    b.extend(yaw.to_le_bytes()); b.push(u8::from(is_damage));
    Ok(b)
}

/// #717 constants.VEHICLE_HIT_FLAGS (constants.pyc line 983).
pub mod hit_flags {
    pub const VEHICLE_KILLED: u32 = 1;
    pub const VEHICLE_WAS_DEAD_BEFORE_ATTACK: u32 = 2;
    pub const RICOCHET: u32 = 8;
    pub const MATERIAL_WITH_POSITIVE_DF_PIERCED_BY_PROJECTILE: u32 = 16;
    pub const MATERIAL_WITH_POSITIVE_DF_NOT_PIERCED_BY_PROJECTILE: u32 = 32;
    pub const ARMOR_WITH_ZERO_DF_PIERCED_BY_PROJECTILE: u32 = 64;
    pub const MATERIAL_WITH_POSITIVE_DF_PIERCED_BY_EXPLOSION: u32 = 4096;
    pub const ATTACK_IS_DIRECT_PROJECTILE: u32 = 524288;
}

/// Direct-hit result flags for the shooter (INFERRED mapping of the server
/// outcome; the original server's flag selection is not recovered). `outcome`
/// None: no visual category, HP change alone decides.
pub fn shot_result_flags(outcome: Option<ShotOutcome>, high_explosive: bool, health_before: i16, health_after: i16) -> u32 {
    use hit_flags::*;
    let mut flags = ATTACK_IS_DIRECT_PROJECTILE;
    if health_before <= 0 { return flags | VEHICLE_WAS_DEAD_BEFORE_ATTACK; }
    let damaged = health_after < health_before;
    if health_after <= 0 { flags |= VEHICLE_KILLED; }
    flags | match (outcome, damaged) {
        (Some(ShotOutcome::Ricochet), false) => RICOCHET,
        (Some(ShotOutcome::Pierced), false) => ARMOR_WITH_ZERO_DF_PIERCED_BY_PROJECTILE,
        (Some(ShotOutcome::Ricochet | ShotOutcome::NotPierced), true) if high_explosive =>
            MATERIAL_WITH_POSITIVE_DF_NOT_PIERCED_BY_PROJECTILE | MATERIAL_WITH_POSITIVE_DF_PIERCED_BY_EXPLOSION,
        (_, true) => MATERIAL_WITH_POSITIVE_DF_PIERCED_BY_PROJECTILE,
        (_, false) => MATERIAL_WITH_POSITIVE_DF_NOT_PIERCED_BY_PROJECTILE,
    }
}

/// Avatar.showShotResults (variable, 0x55, VAR1): ARRAY<UINT64> of
/// vehicleID | flags << 32. #717 Sequence count is signed32LE.
pub fn shot_results(results: &[(usize, u32)]) -> io::Result<Vec<u8>> {
    if results.is_empty() || results.len() > 16 { return Err(bad("AV-01 shot result count")); }
    let mut value = (results.len() as i32).to_le_bytes().to_vec();
    for &(target, flags) in results {
        value.extend((u64::from(wire::vehicle_id(target)?) | u64::from(flags) << 32).to_le_bytes());
    }
    let mut b = vec![0x13, 0x55, value.len() as u8]; b.extend(value);
    Ok(b)
}

/// Avatar.onScoutEvent (fixed exposed7, 0x42): SCOUT_EVENT_TYPE.SPOTTED=0.
pub fn scout_spotted(target: usize) -> io::Result<Vec<u8>> {
    let mut b = vec![0x13, 0x42, 0]; b.extend(wire::vehicle_id(target)?.to_le_bytes());
    Ok(b)
}

/// Vehicle.engineMode property4 (0xa2): (powerMode, dirFlags). #717
/// makeVehicleMovementCommandByKeys flags: forward1, backward2, left4, right8,
/// cruise 50% 16 / 25% 32. Power 0 off, 1 idle, 3 high; low2 is not inferred.
pub fn engine_mode(running: bool, input: model::Input) -> [u8; 2] {
    if !running { return [0, 0]; }
    let motion = match input.throttle { 1 => 1, -1 => 2, _ => 0 };
    let turn = match input.steer { -1 => 4, 1 => 8, _ => 0 };
    if motion == 0 && turn == 0 { return [1, 0]; }
    let cruise = if motion == 0 { 0 } else { match input.speed_percent { 50 => 16, 25 => 32, _ => 0 } };
    [3, motion | turn | cruise]
}
pub fn engine_mode_update(slot: usize, mode: [u8; 2]) -> io::Result<Vec<u8>> {
    if mode[0] > 3 { return Err(bad("AV-01 engine power mode")); }
    let mut b = vec![0x12]; b.extend(wire::vehicle_id(slot)?.to_le_bytes());
    b.push(0xa2); b.extend(mode); b.push(0x13);
    Ok(b)
}

/// shot_effects.xml targetStickers (armorResisted, armorPierced) by effects
/// index, in the EFFECT_NAMES order; IDs are damage_stickers.xml order:
/// small_hole0 small_ricochet1 medium_hole2 medium_ricochet3 main_hole4
/// main_ricochet5 large_hole6 large_ricochet7 (_readDamageStickers).
const TARGET_STICKERS: [(u8, u8); 23] = [
    (1,0),(1,0),(3,2),(3,2),(3,2),(3,2),
    (3,2),(3,2),(3,2),(3,2),(5,4),(5,4),(3,2),(5,4),
    (7,6),(5,4),(3,2),(7,6),(7,6),(5,4),(3,2),(7,6),(5,4)];
/// One sticker code: the showDamageFromShot point with byte0 = stickerID
/// (Vehicle.set_damageStickers line 316 → decodeSegment → addDamageSticker).
pub fn sticker_code(effects: u8, outcome: ShotOutcome, point: [u8; 8]) -> io::Result<u64> {
    let (resisted, pierced) = *TARGET_STICKERS.get(effects as usize).ok_or_else(|| bad("AV-01 sticker effects"))?;
    let mut code = point;
    code[0] = if outcome == ShotOutcome::Pierced { pierced } else { resisted };
    Ok(u64::from_le_bytes(code))
}
/// Full Vehicle.damageStickers update: property6 0xa4, VAR1 i32 count + codes.
pub fn damage_stickers_update(slot: usize, codes: &[u64]) -> io::Result<Vec<u8>> {
    if codes.len() > MAX_STICKERS { return Err(bad("AV-01 sticker count")); }
    let mut value = (codes.len() as i32).to_le_bytes().to_vec();
    for code in codes { value.extend(code.to_le_bytes()); }
    let mut b = vec![0x12]; b.extend(wire::vehicle_id(slot)?.to_le_bytes());
    b.push(0xa4); b.push(value.len() as u8); b.extend(value); b.push(0x13);
    Ok(b)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{Duration, Instant};
    fn shot(terminal: [f32; 3]) -> Projectile {
        Projectile { vehicle_kind: super::super::vehicle_profile::VehicleKind::Ms1, shell: None, sequence: 3, slot: 1,
            origin: [10.0, 5.0, 20.0], velocity: [0.0, 0.0, 400.0], gravity: 9.0, max_distance: 720.0,
            launched: Instant::now(), flight_time: Duration::from_secs(1), terminal, stopped: false }
    }
    #[test] fn av01_anonymous_tracer_hides_muzzle_and_shooter() {
        let b = anonymous_tracer(&shot([10.0, 0.0, 400.0]), 2).unwrap().unwrap();
        assert_eq!(&b[..2], &[0x13, 0x4c]); assert_eq!(&b[2..6], &[0; 4]); assert_eq!(&b[6..10], &3u32.to_le_bytes()); assert_eq!(b[10], 2);
        let f = |o: usize| f32::from_le_bytes(b[o..o + 4].try_into().unwrap());
        assert_eq!(f(11), 10.0); assert!((f(19) - 60.0).abs() < 1e-3); assert!(f(15) < 5.0);
        assert_eq!(f(23), 0.0); assert!(f(27) < 0.0 && f(31) == 400.0); assert!((f(39) - 680.0).abs() < 1e-3);
        assert!(anonymous_tracer(&shot([10.0, 5.0, 50.0]), 2).unwrap().is_none());
    }
    #[test] fn av01_hit_direction_is_shell_heading_for_each_side() {
        use std::f32::consts::{FRAC_PI_2, PI};
        let yaw = |v: [f32; 3]| { let b = hit_direction(v, true).unwrap();
            assert_eq!(&b[..2], &[0x13, 0x41]); assert_eq!(b.len(), 7); assert_eq!(b[6], 1);
            f32::from_le_bytes(b[2..6].try_into().unwrap()) };
        // Target hull faces +z (yaw 0); the shooter stands on the named side.
        // Front: shell flies -z → heading π (not 0, the reversed heading that
        // the owner saw drawn behind the tank).
        assert!((yaw([0.0, -1.0, -400.0]).abs() - PI).abs() < 1e-5);
        // Rear: shell flies +z → heading 0.
        assert!(yaw([0.0, -1.0, 400.0]).abs() < 1e-5);
        // Right side (+x): shell flies -x → -π/2; left side (-x): +π/2.
        assert!((yaw([-400.0, -1.0, 0.0]) + FRAC_PI_2).abs() < 1e-5);
        assert!((yaw([400.0, -1.0, 0.0]) - FRAC_PI_2).abs() < 1e-5);
        // Hull rotation does not enter: the yaw is global.
        assert!((yaw([1.0, 0.0, 1.0]) - PI / 4.0).abs() < 1e-5);
        assert_eq!(hit_direction([0.0, -1.0, 400.0], false).unwrap()[6], 0);
        assert!(hit_direction([0.0, -5.0, 0.0], false).is_err());
    }
    #[test] fn av01_shot_result_flags_select_original_voice_branches() {
        use hit_flags::*;
        let d = ATTACK_IS_DIRECT_PROJECTILE;
        assert_eq!(shot_result_flags(Some(ShotOutcome::Pierced), false, 100, 60), d | MATERIAL_WITH_POSITIVE_DF_PIERCED_BY_PROJECTILE);
        assert_eq!(shot_result_flags(Some(ShotOutcome::NotPierced), false, 100, 100), d | MATERIAL_WITH_POSITIVE_DF_NOT_PIERCED_BY_PROJECTILE);
        assert_eq!(shot_result_flags(Some(ShotOutcome::Ricochet), false, 100, 100), d | RICOCHET);
        assert_eq!(shot_result_flags(Some(ShotOutcome::Pierced), false, 100, 0), d | VEHICLE_KILLED | MATERIAL_WITH_POSITIVE_DF_PIERCED_BY_PROJECTILE);
        assert_eq!(shot_result_flags(Some(ShotOutcome::NotPierced), true, 100, 80),
            d | MATERIAL_WITH_POSITIVE_DF_NOT_PIERCED_BY_PROJECTILE | MATERIAL_WITH_POSITIVE_DF_PIERCED_BY_EXPLOSION);
        assert_eq!(shot_result_flags(None, false, 0, 0), d | VEHICLE_WAS_DEAD_BEFORE_ATTACK);
        let b = shot_results(&[(1, d | RICOCHET)]).unwrap();
        assert_eq!(&b[..7], &[0x13, 0x55, 12, 1, 0, 0, 0]);
        assert_eq!(u64::from_le_bytes(b[7..15].try_into().unwrap()), u64::from(wire::vehicle_id(1).unwrap()) | u64::from(d | RICOCHET) << 32);
        assert!(shot_results(&[]).is_err());
    }
    #[test] fn av01_scout_and_engine_codecs() {
        let s = scout_spotted(2).unwrap();
        assert_eq!(&s[..3], &[0x13, 0x42, 0]); assert_eq!(&s[3..], &wire::vehicle_id(2).unwrap().to_le_bytes());
        let i = |throttle, steer, speed_percent| model::Input { throttle, steer, speed_percent };
        assert_eq!(engine_mode(true, model::Input::STOP), [1, 0]);
        assert_eq!(engine_mode(false, i(1, 1, 100)), [0, 0]);
        assert_eq!(engine_mode(true, i(1, 0, 100)), [3, 1]);
        assert_eq!(engine_mode(true, i(-1, 1, 50)), [3, 26]);
        assert_eq!(engine_mode(true, i(0, -1, 100)), [3, 4]);
        assert_eq!(engine_mode(true, i(1, 0, 25)), [3, 33]);
        assert_eq!(engine_mode_update(0, [1, 0]).unwrap(), [0x12, 3, 0, 0x10, 9, 0xa2, 1, 0, 0x13]);
        assert!(engine_mode_update(0, [4, 0]).is_err());
    }
    #[test] fn av01_damage_sticker_codes_follow_shell_target_stickers() {
        let point = [3, 1, 10, 20, 30, 40, 50, 60];
        let hole = sticker_code(10, ShotOutcome::Pierced, point).unwrap();
        assert_eq!(hole.to_le_bytes(), [4, 1, 10, 20, 30, 40, 50, 60]);
        assert_eq!(sticker_code(10, ShotOutcome::Ricochet, point).unwrap().to_le_bytes()[0], 5);
        assert_eq!(sticker_code(2, ShotOutcome::NotPierced, point).unwrap().to_le_bytes()[0], 3);
        assert!(sticker_code(23, ShotOutcome::Pierced, point).is_err());
        let b = damage_stickers_update(1, &[hole]).unwrap();
        assert_eq!(b[5], 0xa4); assert_eq!(b[6], 12); assert_eq!(&b[7..11], &[1, 0, 0, 0]); assert_eq!(*b.last().unwrap(), 0x13);
        assert_eq!(damage_stickers_update(1, &[0; MAX_STICKERS]).unwrap().len(), 7 + 4 + 8 * MAX_STICKERS + 1);
        assert!(damage_stickers_update(1, &[0; MAX_STICKERS + 1]).is_err());
    }
}
