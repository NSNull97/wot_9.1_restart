//! #717 impact presentation for the two-actor, stock MS-1 laboratory.
//!
//! IDs/layout: original Vehicle.def, Avatar.def and the P02 native method /
//! client-property tables. VehicleEffects.DamageFromShotDecoder:646 decodes
//! each UINT64 as outcome, component, start XYZ, end XYZ (one byte each).
//! The inverse quantizer below is DERIVED, not a recovered server encoder.
//! Native display/sound acceptance is a separate gate; these bytes do not
//! decide penetration, hit location, damage, death or arena results.

use std::io;
use super::wire;

const MAX_LOCAL_COORDINATE: f32 = 100_000.0;
const MAX_HEALTH: i16 = 90;

fn bad(reason: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, reason)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ShotOutcome { Ricochet, NotPierced, Pierced }

impl ShotOutcome {
    fn code(self) -> u8 {
        match self { Self::Ricochet => 0, Self::NotPierced => 1, Self::Pierced => 3 }
    }
}

impl TryFrom<u8> for ShotOutcome {
    type Error = io::Error;
    fn try_from(value: u8) -> io::Result<Self> {
        match value {
            0 => Ok(Self::Ricochet), 1 => Ok(Self::NotPierced), 3 => Ok(Self::Pierced),
            _ => Err(bad("unsupported laboratory shot outcome")),
        }
    }
}

fn valid_health(hp: i16) -> io::Result<()> {
    // Negative native HP can mean an exploded model. P06L supports ordinary
    // destruction at zero only; it must never invent an ammo-rack explosion.
    if !(0..=MAX_HEALTH).contains(&hp) { return Err(bad("laboratory HP bound")); }
    Ok(())
}

/// Broadcast to observers including the target. Set health property first:
/// Vehicle.onHealthChanged:385 reads self.health but never assigns it.
/// This triggers the native appearance / remote marker / death callback.
/// Own HUD additionally needs owner_health, sent only to the target's session.
pub fn health_changed(target_slot: usize, hp: i16, attacker_slot: usize) -> io::Result<Vec<u8>> {
    valid_health(hp)?;
    let target = wire::vehicle_id(target_slot)?;
    let attacker = wire::vehicle_id(attacker_slot)?;
    let mut body = Vec::with_capacity(17);
    body.push(0x12); body.extend(target.to_le_bytes());
    // Dynamic entityProperty base 0x9e + client property 3, fixed INT16.
    body.push(0xa1); body.extend(hp.to_le_bytes());
    // Vehicle client method index 1, fixed INT16 + OBJECT_ID + UINT8.
    body.push(0x3c); body.extend(hp.to_le_bytes()); body.extend(attacker.to_le_bytes());
    // VehicleMarkersManager.ATTACK_REASONS[0] = "attack" (#717 Battle:2497).
    body.push(0);
    body.push(0x13); // Restore the recipient's current Avatar.
    Ok(body)
}

/// Send ONLY to the damaged actor's session. Avatar.updateVehicleHealth:1145
/// updates own damage panel, aim and postmortem input. Crew stays active in this
/// laboratory; crew damage / knockout is outside this encoder's contract.
pub fn owner_health(hp: i16) -> io::Result<Vec<u8>> {
    valid_health(hp)?;
    let mut body = vec![0x13, 0x3f]; // Avatar exposed index 4, fixed INT16 + BOOL.
    body.extend(hp.to_le_bytes()); body.push(1);
    Ok(body)
}

fn bounded(point: [f32; 3]) -> bool {
    point.iter().all(|v| v.is_finite() && v.abs() <= MAX_LOCAL_COORDINATE)
}

fn packed_segment(component: u8, bbox: [[f32; 3]; 2], start: [f32; 3], end: [f32; 3],
    outcome: ShotOutcome) -> io::Result<[u8; 8]> {
    if component > 3 || !bounded(bbox[0]) || !bounded(bbox[1]) || !bounded(start) || !bounded(end)
        || (0..3).any(|i| bbox[0][i] >= bbox[1][i]) || start == end {
        return Err(bad("invalid component-local visual segment"));
    }
    let lo = bbox[0].map(f64::from);
    let hi = bbox[1].map(f64::from);
    let from = start.map(f64::from);
    let to = end.map(f64::from);
    let direction = [to[0] - from[0], to[1] - from[1], to[2] - from[2]];
    let (mut enter, mut leave) = (0.0f64, 1.0f64);
    // Slab-clip this finite segment, preserving its line and direction. The
    // caller normally supplies a line already extended across the native bbox.
    // Independently clamping coordinates could rotate the ray and is forbidden.
    for i in 0..3 {
        if direction[i] == 0.0 {
            if from[i] < lo[i] || from[i] > hi[i] { return Err(bad("visual segment misses bbox")); }
        } else {
            let a = (lo[i] - from[i]) / direction[i];
            let b = (hi[i] - from[i]) / direction[i];
            enter = enter.max(a.min(b)); leave = leave.min(a.max(b));
        }
    }
    if enter >= leave { return Err(bad("visual segment has no bbox span")); }
    let mut packed = [0u8; 8];
    packed[0] = outcome.code(); packed[1] = component;
    for (point_index, t) in [enter, leave].iter().enumerate() {
        for i in 0..3 {
            let value = from[i] + direction[i] * t;
            // Native decoder: min + (max-min) * byte / 255. Derived inverse:
            // nearest integer, exact .5 ties upwards. Arithmetic uses f64
            // promoted f32 facts. Clamp only the normalized round-off after
            // line-preserving clipping, never the original point coordinates.
            let normalized = ((value - lo[i]) / (hi[i] - lo[i])).clamp(0.0, 1.0);
            packed[2 + point_index * 3 + i] = (normalized * 255.0 + 0.5).floor() as u8;
        }
    }
    // Native decodeHitPoints skips collapsed rays; fail before publishing HP.
    if packed[2..5] == packed[5..8] { return Err(bad("visual segment collapses after quantization")); }
    Ok(packed)
}

/// One component-local visual ray and one explicit resolver outcome. No world
/// coordinates are accepted implicitly. The native decoder extends the decoded
/// segment 1% at both ends and finds its own mesh hit; quantization may change
/// the selected triangle. This is presentation, not collision authority.
pub fn show_damage(attacker_slot: usize, target_slot: usize, component: u8,
    bbox: [[f32; 3]; 2], local_start: [f32; 3], local_end: [f32; 3],
    outcome: ShotOutcome) -> io::Result<Vec<u8>> {
    let attacker = wire::vehicle_id(attacker_slot)?;
    let target = wire::vehicle_id(target_slot)?;
    let packed = packed_segment(component, bbox, local_start, local_end, outcome)?;
    let mut body = Vec::with_capacity(26);
    body.push(0x12); body.extend(target.to_le_bytes());
    body.push(0x42); body.extend(17u16.to_le_bytes()); // Vehicle method 7, VAR2.
    body.extend(attacker.to_le_bytes());
    // #717 native Sequence reader dedc84..dedc97: signed32LE count, not the
    // packed count used by newer BigWorld references. Exactly one UINT64.
    body.extend(1i32.to_le_bytes()); body.extend(packed);
    body.push(2); // Pinned stock AP2570 smallArmorPiercing effectsIndex.
    body.push(0x13);
    Ok(body)
}

#[cfg(test)]
mod tests {
    use super::*;
    const BOX: [[f32; 3]; 2] = [[0.0; 3], [1.0; 3]];

    #[test]
    fn health_sets_property_before_callback_and_restores_avatar() {
        assert_eq!(health_changed(0, 60, 1).unwrap(), [
            0x12, 0x03, 0x00, 0x10, 0x09,
            0xa1, 0x3c, 0x00,
            0x3c, 0x3c, 0x00, 0x05, 0x00, 0x10, 0x09, 0x00, 0x13,
        ]);
        assert_eq!(owner_health(0).unwrap(), [0x13, 0x3f, 0x00, 0x00, 0x01]);
        assert_eq!(owner_health(90).unwrap(), [0x13, 0x3f, 0x5a, 0x00, 0x01]);
        assert_eq!(&health_changed(1, 0, 0).unwrap()[5..8], &[0xa1, 0, 0]);
    }

    #[test]
    fn impact_native_layout_golden_includes_i32_count_and_effect() {
        assert_eq!(show_damage(0, 1, 1, BOX, [0.0, 0.5, 1.0], [1.0, 0.25, 0.0], ShotOutcome::Pierced).unwrap(), [
            0x12, 0x05, 0x00, 0x10, 0x09,
            0x42, 0x11, 0x00, 0x03, 0x00, 0x10, 0x09,
            0x01, 0x00, 0x00, 0x00,
            0x03, 0x01, 0x00, 0x80, 0xff, 0xff, 0x40, 0x00, 0x02, 0x13,
        ]);
    }

    #[test]
    fn clipping_keeps_ray_direction_and_reverse_order() {
        let a = packed_segment(2, BOX, [-1.0, -0.5, 0.5], [2.0, 1.0, 0.5], ShotOutcome::Ricochet).unwrap();
        assert_eq!(a, [0, 2, 0, 0, 128, 255, 128, 128]);
        let b = packed_segment(3, BOX, [2.0, 1.0, 0.5], [-1.0, -0.5, 0.5], ShotOutcome::NotPierced).unwrap();
        assert_eq!(b, [1, 3, 255, 128, 128, 0, 0, 128]);
    }

    #[test]
    fn quantizer_uses_component_bbox_and_closed_boundaries() {
        let bbox = [[-2.0, 5.0, -10.0], [2.0, 7.0, 10.0]];
        assert_eq!(packed_segment(0, bbox, [-2.0, 6.0, 10.0], [2.0, 5.0, -10.0], ShotOutcome::Pierced).unwrap(),
            [3, 0, 0, 128, 255, 255, 0, 0]);
        let below = 0.5 - f32::EPSILON;
        let above = 0.5 + f32::EPSILON;
        let value = packed_segment(1, BOX, [0.0, below, 0.0], [1.0, above, 1.0], ShotOutcome::Pierced).unwrap();
        assert_eq!((value[3], value[6]), (127, 128));
    }

    #[test]
    fn misses_tangent_zero_length_and_quantized_collapse_reject() {
        for (a, b) in [
            ([0.5; 3], [0.5; 3]),
            ([-1.0, 2.0, 0.5], [2.0, 2.0, 0.5]),
            ([-1.0; 3], [0.0; 3]),
            ([0.5; 3], [0.50001; 3]),
        ] {
            assert!(packed_segment(1, BOX, a, b, ShotOutcome::Pierced).is_err());
        }
    }

    #[test]
    fn malformed_component_bbox_coordinates_hp_and_slots_reject() {
        for component in [4, 255] {
            assert!(packed_segment(component, BOX, [0.0; 3], [1.0; 3], ShotOutcome::Pierced).is_err());
        }
        for axis in 0..3 {
            for invalid in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, MAX_LOCAL_COORDINATE + 1.0] {
                let mut a = [0.0; 3]; a[axis] = invalid;
                assert!(packed_segment(1, BOX, a, [1.0; 3], ShotOutcome::Pierced).is_err());
                assert!(packed_segment(1, BOX, [0.0; 3], a, ShotOutcome::Pierced).is_err());
                for bound in 0..2 {
                    let mut bbox = BOX; bbox[bound][axis] = invalid;
                    assert!(packed_segment(1, bbox, [0.0; 3], [1.0; 3], ShotOutcome::Pierced).is_err());
                }
            }
            for max in [-1.0, 0.0] {
                let mut bbox = BOX; bbox[1][axis] = max;
                assert!(packed_segment(1, bbox, [0.0; 3], [1.0; 3], ShotOutcome::Pierced).is_err());
            }
        }
        for hp in [-32768, -1, 91, 32767] {
            assert!(health_changed(0, hp, 1).is_err()); assert!(owner_health(hp).is_err());
        }
        for (attacker, target) in [(2, 0), (0, 2), (usize::MAX, 1)] {
            assert!(health_changed(target, 60, attacker).is_err());
            assert!(show_damage(attacker, target, 1, BOX, [0.0; 3], [1.0; 3], ShotOutcome::Pierced).is_err());
        }
        for code in 0..=255 {
            assert_eq!(ShotOutcome::try_from(code).is_ok(), [0, 1, 3].contains(&code));
        }
    }
}
