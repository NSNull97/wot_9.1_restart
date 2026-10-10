//! Rigid chassis orientation measured against #717 Math.Matrix.setRotateYPR.
//! Angles are yaw/pitch/roll in radians; vectors use +Y up and +Z forward.
//! In column-vector notation R = Ry(yaw) * Rx(pitch) * Rz(roll): roll acts
//! first, then pitch, then yaw. This is a rotation only, with no model offsets,
//! suspension/fashion compensation, scaling, or translation.

/// Rotate a finite local vector into the chassis/world orientation. Callers
/// validate external values before mutating authoritative state.
pub fn rotate(vector: [f32; 3], ypr: [f32; 3]) -> [f32; 3] {
    let axes = basis(ypr);
    std::array::from_fn(|i| axes[0][i] * vector[0] + axes[1][i] * vector[1] + axes[2][i] * vector[2])
}

/// Inverse of the measured rigid rotation (transpose, not reversed Euler signs).
pub fn inverse_rotate(vector: [f32; 3], ypr: [f32; 3]) -> [f32; 3] {
    let axes = basis(ypr);
    axes.map(|axis| axis[0] * vector[0] + axis[1] * vector[1] + axis[2] * vector[2])
}

fn basis([yaw, pitch, roll]: [f32; 3]) -> [[f32; 3]; 3] {
    let (sy, cy) = yaw.sin_cos();
    let (sp, cp) = pitch.sin_cos();
    let (sr, cr) = roll.sin_cos();
    [
        [cy * cr + sy * sp * sr, cp * sr, -sy * cr + cy * sp * sr],
        [-cy * sr + sy * sp * cr, cp * cr, sy * sr + cy * sp * cr],
        [sy * cp, -sp, cy * cp],
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn independent_native_mixed_euler_axes_match() {
        // Original #717 native Math oracle, not our own inverse round trip:
        // 20261010-p06i-native-collision-01/runtime-a-oracle01/
        // native-27076-1791611380111.jsonl, shared_collision_math_oracle.
        // Math record SHA256 (UTF-8 line, excluding newline; file may append):
        // 9adb45df77a7b225e9dd2b2d66b4354418db2d960a928546761eae759165b81b.
        // Each row below is the native image of one unit basis vector.
        for (ypr, expected) in [
            ([0.7, -0.3, 0.2], [
                [0.7117737532, 0.1897960901, -0.6762807369],
                [-0.3385351300, 0.9362933636, -0.0935345665],
                [0.6154446602, 0.2955202162, 0.7306816578],
            ]),
            ([-2.1, 0.25, -0.15], [
                [-0.4672630429, -0.1447924972, 0.8721814752],
                [-0.2866066098, 0.9580326080, 0.0054980293],
                [-0.8363743424, -0.2474039495, -0.4891516864],
            ]),
        ] {
            for i in 0..3 {
                let mut unit = [0.; 3]; unit[i] = 1.;
                let actual = rotate(unit, ypr);
                for j in 0..3 { assert!((actual[j] - expected[i][j]).abs() < 2e-7); }
                let local = inverse_rotate(expected[i], ypr);
                for j in 0..3 { assert!((local[j] - unit[j]).abs() < 3e-7); }
            }
        }
    }

    #[test]
    fn native_single_axis_signs_and_inverse_preserve_vectors() {
        let half_pi = std::f32::consts::FRAC_PI_2;
        for (ypr, expected) in [([half_pi, 0., 0.], [1., 0., 0.]),
            ([0., half_pi, 0.], [0., -1., 0.]), ([0., 0., half_pi], [0., 0., 1.])] {
            let result = rotate([0., 0., 1.], ypr);
            for i in 0..3 { assert!((result[i] - expected[i]).abs() < 1e-6); }
        }
        for ypr in [[0.; 3], [1.3, -0.9, 0.7], [-3.1, 1.57, -2.8]] {
            let vector = [17.25, -8.5, 41.75];
            let result = inverse_rotate(rotate(vector, ypr), ypr);
            for i in 0..3 { assert!((result[i] - vector[i]).abs() < 1e-5); }
        }
    }
}
