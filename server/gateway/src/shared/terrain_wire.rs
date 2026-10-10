//! Original #717 Avatar.explodeProjectile for the stock MS-1 ground-hit lane.
//!
//! Avatar.def / aliases: INT32 shot ID, UINT8 effects, UINT8 effect material,
//! VECTOR3 endpoint, VECTOR3 velocity direction, ARRAY<UINT32> destructibles.
//! Native method index28 = 0x57. The measured #717 variable-method size path
//! returns -1 -> VAR1; its Sequence reader uses an i32 element count.
//! Stock smallArmorPiercing is effects2; ground is effect-material index0.
//! No vehicle outcome, HP, splash damage or terrain destruction is encoded.
//!
//! Send this INSTEAD OF stopTracer for a terrain terminal. Original mover
//! explode schedules/adds the world effect; a later hide clears showExpolosion.
//! The native mover may substitute its local collision position/direction or
//! water effect. These presentation adjustments are never server hit evidence.

use std::io;
use super::model;

const MAX_COORDINATE: f32 = 100_000.0;
// The caller normalizes the authoritative collision chord in f32. Compare
// squared norm to one; accept only rounding-scale deviation, without silently
// normalizing malformed input or changing the supplied endpoint/direction.
const UNIT_SQUARED_TOLERANCE: f64 = 0.0001;

fn bad() -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, "stock ground impact wire bounds")
}

/// One original ground effect on the recipient's Avatar. The shot must have
/// been admitted by the server and observed by this connection; those lifecycle
/// gates and once-only publication remain the caller's responsibility.
pub fn explode(shot_id: u32, point: [f32; 3], direction: [f32; 3]) -> io::Result<Vec<u8>> {
    if shot_id == 0 || u64::from(shot_id) > model::MAX_SHOTS as u64
        || point.iter().any(|v| !v.is_finite() || v.abs() > MAX_COORDINATE)
        || direction.iter().any(|v| !v.is_finite()) {
        return Err(bad());
    }
    let norm_squared = direction.iter().map(|&v| f64::from(v).powi(2)).sum::<f64>();
    if (norm_squared - 1.0).abs() > UNIT_SQUARED_TOLERANCE { return Err(bad()); }
    let shot = i32::try_from(shot_id).map_err(|_| bad())?;
    // 4+1+1+12+12+4 = 34 argument bytes. Outer length is ONE byte;
    // the empty ARRAY count is separately four bytes, never packed uint8.
    let mut body = Vec::with_capacity(37);
    body.extend([0x13, 0x57, 34]);
    body.extend(shot.to_le_bytes());
    body.extend([2, 0]);
    for coordinate in point.into_iter().chain(direction) { body.extend(coordinate.to_le_bytes()); }
    body.extend(0i32.to_le_bytes());
    Ok(body)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_var1_ground_layout_has_exact_offsets_and_empty_i32_array() {
        // Independent literal from the pinned native method/primitive widths;
        // this does not claim original callback execution or rendered success.
        let expected = [
            0x13, 0x57, 0x22, 0x07, 0x00, 0x00, 0x00, 0x02, 0x00,
            0x00, 0x00, 0x80, 0x3f, // x=1
            0x00, 0x00, 0x00, 0xc0, // y=-2
            0x00, 0x00, 0x60, 0x40, // z=3.5
            0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x80, 0xbf, // direction down
            0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, // zero destructibles, i32
        ];
        let body = explode(7, [1.0, -2.0, 3.5], [0.0, -1.0, 0.0]).unwrap();
        assert_eq!(body, expected);
        assert_eq!(usize::from(body[2]), body.len() - 3);
        assert_eq!(i32::from_le_bytes(body[33..37].try_into().unwrap()), 0);
        // The very next native message starts immediately after argument34.
        let mut compound = body; compound.extend([0x13, 0x40, 0]);
        assert_eq!(&compound[3 + usize::from(compound[2])..], &[0x13, 0x40, 0]);
    }

    #[test]
    fn rejects_bad_shots_points_and_nonunit_directions() {
        for shot in [0, model::MAX_SHOTS as u32 + 1, u32::MAX] {
            assert!(explode(shot, [0.0; 3], [1.0, 0.0, 0.0]).is_err());
        }
        for axis in 0..3 {
            for value in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY,
                MAX_COORDINATE + 1.0, -MAX_COORDINATE - 1.0] {
                let mut point = [0.0; 3]; point[axis] = value;
                assert!(explode(1, point, [1.0, 0.0, 0.0]).is_err());
            }
            for value in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY] {
                let mut direction = [1.0, 0.0, 0.0]; direction[axis] = value;
                assert!(explode(1, [0.0; 3], direction).is_err());
            }
        }
        for direction in [[0.0; 3], [2.0, 0.0, 0.0], [0.999, 0.0, 0.0], [1.0, 1.0, 0.0]] {
            assert!(explode(1, [0.0; 3], direction).is_err());
        }
    }

    #[test]
    fn accepts_bounded_unit_direction_without_rewriting_f32_bits() {
        let direction = [1.0 / 3.0f32.sqrt(); 3];
        let point = [MAX_COORDINATE, -MAX_COORDINATE, -0.0];
        let body = explode(model::MAX_SHOTS as u32, point, direction).unwrap();
        for (index, value) in point.into_iter().chain(direction).enumerate() {
            assert_eq!(&body[9 + index * 4..13 + index * 4], &value.to_le_bytes());
        }
        assert_eq!(&body[7..9], &[2, 0]);
    }
}
