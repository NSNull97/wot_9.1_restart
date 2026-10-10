//! Server-owned aiming for the temporary stock MS-1 laboratory profile.
//! Rates/pivots are pinned #717 resources. The independent ballistic
//! solver is test_lab approximate, not a claim about the historical server.
use std::{f32::consts::PI, io};
use super::{model::bad, pose};

pub const YAW_RATE: f32 = 39. * PI / 180.;
pub const PITCH_RATE: f32 = 52.5 * PI / 180.;
pub const MIN_PITCH: f32 = -25. * PI / 180.;
pub const MAX_PITCH: f32 = 8. * PI / 180.;
pub(super) const PIVOT: [f32; 3] = [0.001778, 1.316402, 0.033775];
pub(super) const GUN: [f32; 3] = [-0.238144, 0.234668, 0.410043];

/// Compatibility wrapper for callers with a flat hull.
pub(crate) fn shot_geometry(
    position: [f32; 3], hull_yaw: f32, turret_yaw: f32, pitch: f32, speed: f32,
) -> ([f32; 3], [f32; 3]) {
    shot_geometry_pose(position, [hull_yaw, 0., 0.], turret_yaw, pitch, speed)
}

/// Pinned VehicleGunRotator gun-pivot origin and +Z barrel direction with the
/// full measured chassis rotation. Native rendering may use a muzzle node;
/// this reference origin deliberately remains the gun joint.
pub(crate) fn shot_geometry_pose(
    position: [f32; 3], direction: [f32; 3], turret_yaw: f32, pitch: f32, speed: f32,
) -> ([f32; 3], [f32; 3]) {
    let local_origin = {
        let gun = pose::rotate(GUN, [turret_yaw, 0., 0.]);
        [PIVOT[0] + gun[0], PIVOT[1] + gun[1], PIVOT[2] + gun[2]]
    };
    let origin_offset = pose::rotate(local_origin, direction);
    let origin = [
        position[0] + origin_offset[0],
        position[1] + origin_offset[1],
        position[2] + origin_offset[2],
    ];
    let velocity = pose::rotate(pose::rotate([0., 0., speed], [turret_yaw, pitch, 0.]), direction);
    (origin, velocity)
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Intent { Point([f32; 3]), Hold { yaw: f32, pitch: f32 } }
impl Intent {
    pub fn validate(self) -> io::Result<()> {
        let valid = match self {
            Self::Point(p) => p.iter().all(|v| v.is_finite() && v.abs() <= 1_000_000.),
            Self::Hold { yaw, pitch } => yaw.is_finite() && yaw.abs() <= PI + 0.001
                && pitch.is_finite() && pitch.abs() <= PI / 2.,
        };
        if valid { Ok(()) } else { Err(bad()) }
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct State { pub yaw: f32, pub pitch: f32, pub intent: Intent }
impl State {
    pub fn new() -> Self { Self { yaw: 0., pitch: 0., intent: Intent::Hold { yaw: 0., pitch: 0. } } }
    pub fn park(&mut self) { self.intent = Intent::Hold { yaw: self.yaw, pitch: self.pitch }; }
    pub fn set(&mut self, intent: Intent) -> io::Result<()> { intent.validate()?; self.intent = intent; Ok(()) }
    pub fn advance(&mut self, position: [f32; 3], hull_yaw: f32, dt: f32) -> io::Result<()> {
        self.advance_pose(position, [hull_yaw, 0., 0.], dt)
    }
    pub fn advance_pose(&mut self, position: [f32; 3], direction: [f32; 3], dt: f32) -> io::Result<()> {
        if !dt.is_finite() || !(0. ..=0.2).contains(&dt)
            || direction.iter().any(|x| !x.is_finite()) || position.iter().any(|x| !x.is_finite()) { return Err(bad()); }
        self.intent.validate()?;
        let (yaw, pitch) = match self.intent {
            Intent::Point(point) => target_angles_pose(position, direction, point, self.yaw, self.pitch),
            Intent::Hold { yaw, pitch } => (yaw, pitch),
        };
        self.yaw = wrap(self.yaw + wrap(yaw - self.yaw).clamp(-YAW_RATE * dt, YAW_RATE * dt));
        let target = pitch.clamp(MIN_PITCH, pitch_max(self.yaw));
        self.pitch += (target - self.pitch).clamp(-PITCH_RATE * dt, PITCH_RATE * dt);
        Ok(())
    }
}
pub fn wrap(angle: f32) -> f32 { (angle + PI).rem_euclid(2. * PI) - PI }

// Stock turret's rear sector is 35 degrees with a +1 degree lower-gun stop.
// The 0.4 rad linear transition matched all 15 original native oracle samples.
pub fn pitch_max(yaw: f32) -> f32 {
    let outside = (PI - wrap(yaw).abs() - 35f32.to_radians()).max(0.);
    let blend = (outside / 0.4).clamp(0., 1.);
    (1. + 7. * blend).to_radians()
}

/// A tilted hull also rotates gravity into local X/Z, so transforming only the
/// target and reusing a local-Y parabola is wrong. Solve each low arc in world
/// space, then convert its velocity to turret angles. The origin depends on
/// turret yaw; iterate that small offset, with a fixed budget and convergence
/// check. This is an independent lab solver, not native historical equivalence.
/// Near-vertical, unreachable, or non-convergent tilted targets hold the prior
/// angles. Limits/rates are applied by State after the unconstrained solve.
fn target_angles_pose(position: [f32; 3], direction: [f32; 3], point: [f32; 3], old_yaw: f32, old_pitch: f32) -> (f32, f32) {
    if direction[1] == 0. && direction[2] == 0. {
        return target_angles(position, direction[0], point, old_yaw, old_pitch);
    }
    let relative = std::array::from_fn(|i| point[i] - position[i]);
    let local = pose::inverse_rotate(relative, direction);
    let x = (local[0] - PIVOT[0]) as f64;
    let z = (local[2] - PIVOT[2]) as f64;
    let radius = x.hypot(z);
    if radius <= GUN[0].abs() as f64 + 0.001 { return (old_yaw, old_pitch); }
    let mut yaw = (x.atan2(z) - (GUN[0] as f64 / radius).asin()) as f32;
    for _ in 0..16 {
        // Work relative to chassis position to avoid subtracting two rounded
        // large world origins. Raw speed/gravity give the same parabola as the
        // effective pair (speed * factor, gravity * factor squared).
        let (offset, _) = shot_geometry_pose([0.; 3], direction, yaw, 0., 1.);
        let d: [f64; 3] = std::array::from_fn(|i| relative[i] as f64 - offset[i] as f64);
        let horizontal = d[0].hypot(d[2]);
        if horizontal <= 0.001 { return (old_yaw, old_pitch); }
        let v2 = 442f64.powi(2); let g = 9.81;
        let disc = v2 * v2 - g * (g * horizontal * horizontal + 2. * d[1] * v2);
        if !disc.is_finite() || disc < 0. { return (old_yaw, old_pitch); }
        let elevation = ((g * horizontal * horizontal + 2. * d[1] * v2)
            / (horizontal * (v2 + disc.sqrt()))).atan();
        let (s, c) = elevation.sin_cos();
        let local_velocity = pose::inverse_rotate([
            (d[0] / horizontal * c) as f32, s as f32, (d[2] / horizontal * c) as f32,
        ], direction);
        let next_yaw = local_velocity[0].atan2(local_velocity[2]);
        let pitch = -local_velocity[1].atan2(local_velocity[0].hypot(local_velocity[2]));
        if !next_yaw.is_finite() || !pitch.is_finite() { return (old_yaw, old_pitch); }
        if wrap(next_yaw - yaw).abs() < 1e-6 { return (wrap(next_yaw), pitch); }
        yaw = next_yaw;
    }
    (old_yaw, old_pitch)
}

/// +Z forward, positive turret yaw right, negative pitch up. No client pose,
/// clock, hit result or projectile is accepted. Degenerate points hold state.
fn target_angles(position: [f32; 3], hull: f32, point: [f32; 3], old_yaw: f32, old_pitch: f32) -> (f32, f32) {
    let dx = (point[0] - position[0]) as f64; let dz = (point[2] - position[2]) as f64;
    let (s,c) = (hull as f64).sin_cos();
    let x = c * dx - s * dz - PIVOT[0] as f64;
    let z = s * dx + c * dz - PIVOT[2] as f64;
    let y = (point[1] - position[1]) as f64 - PIVOT[1] as f64 - GUN[1] as f64;
    let radial = x.hypot(z);
    if radial <= GUN[0].abs() as f64 + 0.001 { return (old_yaw, old_pitch); }
    let yaw = x.atan2(z) - (GUN[0] as f64 / radial).asin();
    let distance = (radial * radial - (GUN[0] as f64).powi(2)).sqrt() - GUN[2] as f64;
    if distance <= 0.001 { return (old_yaw, old_pitch); }
    let v2 = 442f64.powi(2); let g = 9.81;
    let disc = v2 * v2 - g * (g * distance * distance + 2. * y * v2);
    // For unreachable camera points use the geometric direction, not NaN.
    let elevation = if disc >= 0. {
        ((g * distance * distance + 2. * y * v2) / (distance * (v2 + disc.sqrt()))).atan()
    } else { y.atan2(distance) };
    (wrap(yaw as f32), -elevation as f32)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn tilted_world_gravity_solution_reaches_targets_in_world_space() {
        // Verify the resulting flight in world coordinates. Merely rotating a
        // flat solution would tilt gravity and miss these long oblique shots.
        for direction in [[0.7, -0.3, 0.2], [-2.1, 0.25, -0.15], [0.2, 0.6, -0.5]] {
            let position = [37., 21., -105.];
            for relative in [[0., 0., 100.], [450., -20., 310.], [-300., 60., -400.], [1., 0., 5.]] {
                let point = std::array::from_fn(|i| position[i] + relative[i]);
                let (yaw, pitch) = target_angles_pose(position, direction, point, 0., 0.);
                let (origin, velocity) = shot_geometry_pose(position, direction, yaw, pitch, 442.);
                let horizontal2 = velocity[0] * velocity[0] + velocity[2] * velocity[2];
                let time = ((point[0] - origin[0]) * velocity[0]
                    + (point[2] - origin[2]) * velocity[2]) / horizontal2;
                assert!(time.is_finite() && time > 0.);
                let reached = [origin[0] + velocity[0] * time,
                    origin[1] + velocity[1] * time - 0.5 * 9.81 * time * time,
                    origin[2] + velocity[2] * time];
                let error = (0..3).map(|i| (reached[i] - point[i]).powi(2)).sum::<f32>().sqrt();
                assert!(error < 0.002, "pose={direction:?}, target={point:?}, error={error}");
            }
        }
    }
    #[test] fn full_pose_hold_preserves_local_angles_and_validation_is_atomic() {
        let mut state = State::new(); state.yaw = 0.6; state.pitch = -0.1; state.park();
        let before = state.clone();
        state.advance_pose([10., 20., 30.], [1.2, 0.25, -0.2], 0.1).unwrap();
        assert!(wrap(state.yaw - before.yaw).abs() < 1e-6);
        assert_eq!(state.pitch, before.pitch); assert_eq!(state.intent, before.intent);
        let before = state.clone();
        for axis in 0..3 {
            let mut direction = [0.; 3]; direction[axis] = f32::NAN;
            assert!(state.advance_pose([0.; 3], direction, 0.1).is_err());
            assert_eq!(state, before);
        }
        let held = target_angles_pose([0.; 3], [0.7, -0.3, 0.2], [1_000_000.; 3], 0.6, -0.1);
        assert_eq!(held, (0.6, -0.1));
    }
    #[test] fn flat_wrapper_and_pose_path_keep_the_same_geometry_and_rates() {
        for yaw in [-3., -1., 0., 2.] {
            assert_eq!(shot_geometry([1., 2., 3.], yaw, 0.6, -0.1, 442.),
                shot_geometry_pose([1., 2., 3.], [yaw, 0., 0.], 0.6, -0.1, 442.));
            let mut a = State::new(); a.set(Intent::Point([30., 5., 70.])).unwrap();
            let mut b = a.clone();
            for _ in 0..100 {
                a.advance([0.; 3], yaw, 0.1).unwrap();
                b.advance_pose([0.; 3], [yaw, 0., 0.], 0.1).unwrap();
            }
            assert_eq!(a, b);
        }
    }
    #[test] fn independent_native_oracle_points_and_rear_stops_match_within_one_wire_bin() {
        // Measured BigWorld.wg_getShotAngles via original getShotAngles, #717,
        // stock descriptor, identity matrix and initial yaw/pitch=(0,0).
        // This is an independent native oracle, not our encoder's round trip.
        for (p,native) in [
            ([0.,0.,100.], [0.002364469,0.01307917]),
            ([100.,0.,0.], [1.5735155,0.01307336]),
            ([0.,0.,-100.], [-3.1391845,0.013066344]),
            ([0.,30.,100.], [0.0023644594,-0.28084177]),
            ([0.,-30.,100.], [0.0023644543,0.30440733]),
            ([0.,0.,5.], [0.048820876,0.32814762]),
            ([0.,0.,720.], [0.00032849,-0.015913291]),
            ([0.,0.,10000.], [0.00002363766,-0.26285544]),
        ] {
            let (yaw,pitch)=target_angles([0.;3],0.,p,0.,0.);
            assert!(wrap(yaw-native[0]).abs()<0.0013,"{p:?} yaw");
            assert!((pitch-native[1]).abs()<0.0003,"{p:?} pitch");
        }
        for (degrees,max) in [(120f32,0.13962634),(125.,0.1240694),(130.,0.09741538),
            (135.,0.07076137),(140.,0.044107348),(145.,0.017453328),(180.,0.017453292)] {
            for sign in [-1.,1.] {assert!((pitch_max(sign*degrees.to_radians())-max).abs()<2e-7);}
        }
    }
    #[test] fn input_never_teleports_and_shortest_wrap_is_rate_limited() {
        let mut s=State::new(); s.yaw=179f32.to_radians();
        s.set(Intent::Hold { yaw:-179f32.to_radians(),pitch:-1. }).unwrap();
        let initial=s.yaw; s.advance([0.;3],0.,0.01).unwrap();
        assert!((wrap(s.yaw-initial)-YAW_RATE*0.01).abs()<1e-6);
        assert!((s.pitch+PITCH_RATE*0.01).abs()<1e-6);
        for _ in 0..100 {s.advance([0.;3],0.,0.1).unwrap();}
        assert!((s.yaw-(-179f32.to_radians())).abs()<1e-6); assert_eq!(s.pitch,MIN_PITCH);
    }
    #[test] fn stationary_world_target_counter_rotates_when_hull_turns() {
        let p=[0.,0.,100.]; let mut a=State::new(); a.set(Intent::Point(p)).unwrap();
        let mut b=a.clone();
        for _ in 0..100 {a.advance([0.;3],0.,0.1).unwrap();b.advance([0.;3],PI/2.,0.1).unwrap();}
        assert!((wrap(b.yaw-a.yaw)+PI/2.).abs()<0.002);
        assert!(a.pitch>0. && a.pitch<0.02);
    }
    #[test] fn invalid_values_and_large_time_steps_are_rejected_before_state_changes() {
        for v in [f32::NAN,f32::INFINITY,f32::NEG_INFINITY,1_000_001.] {
            let mut s=State::new(); let before=s.clone();
            assert!(s.set(Intent::Point([v,0.,0.])).is_err());assert_eq!(s,before);
        }
        let mut s=State::new();assert!(s.advance([0.;3],0.,1.).is_err());assert_eq!(s,State::new());
        assert!(s.set(Intent::Hold {yaw:4.,pitch:0.}).is_err());
    }
    #[test] fn rear_depression_and_degenerate_targets_stay_finite() {
        assert!((pitch_max(PI)-1f32.to_radians()).abs()<1e-6);assert_eq!(pitch_max(0.),MAX_PITCH);
        let mut s=State::new();s.set(Intent::Point(PIVOT)).unwrap();s.advance([0.;3],0.,0.1).unwrap();
        assert_eq!(s.yaw,0.);assert_eq!(s.pitch,0.);
        s.set(Intent::Point([1_000_000.;3])).unwrap();
        for _ in 0..100 {s.advance([0.;3],0.,0.1).unwrap();}
        assert!(s.yaw.is_finite() && s.pitch>=MIN_PITCH && s.pitch<=MAX_PITCH);
    }
}
