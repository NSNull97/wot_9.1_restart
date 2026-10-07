//! Server-owned aiming for the temporary stock MS-1 laboratory profile.
//! Rates/pivots are pinned #717 resources. The independent flat-hull ballistic
//! solver is test_lab approximate, not a claim about the historical server.
use std::{f32::consts::PI, io};
use super::model::bad;

pub const YAW_RATE: f32 = 39. * PI / 180.;
pub const PITCH_RATE: f32 = 52.5 * PI / 180.;
pub const MIN_PITCH: f32 = -25. * PI / 180.;
pub const MAX_PITCH: f32 = 8. * PI / 180.;
const PIVOT: [f32; 3] = [0.001778, 1.316402, 0.033775];
const GUN: [f32; 3] = [-0.238144, 0.234668, 0.410043];

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
        if !dt.is_finite() || !(0. ..=0.2).contains(&dt)
            || !hull_yaw.is_finite() || position.iter().any(|x| !x.is_finite()) { return Err(bad()); }
        self.intent.validate()?;
        let (yaw, pitch) = match self.intent {
            Intent::Point(point) => target_angles(position, hull_yaw, point, self.yaw, self.pitch),
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
