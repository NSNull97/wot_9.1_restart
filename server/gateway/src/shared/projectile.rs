//! Server-owned projectile flight for the pinned #717 MS-1 laboratory profile.
//!
//! The values in this module are the effective values read from the original
//! client's shell/gun resources: the client applies a common projectile speed
//! factor to speed and its square to gravity.  This is a bounded flight model,
//! not the eventual vehicle/terrain/armor simulation.

use std::{io, time::{Duration, Instant}};

use super::{aim, model};

/// Original `_37mm_Gochkins` stock AP speed before the common factor.
pub const MS1_RAW_SPEED: f32 = 442.0;
/// Original `_37mm_Gochkins` stock AP gravity before the common factor.
pub const MS1_RAW_GRAVITY: f32 = 9.81;
/// Original `common/vehicle.xml` projectileSpeedFactor.
pub const PROJECTILE_SPEED_FACTOR: f32 = 0.8;
/// Effective speed passed to the original ProjectileMover.
pub const MS1_SPEED: f32 = MS1_RAW_SPEED * PROJECTILE_SPEED_FACTOR;
/// Effective gravity passed to the original ProjectileMover.
pub const MS1_GRAVITY: f32 = MS1_RAW_GRAVITY * PROJECTILE_SPEED_FACTOR * PROJECTILE_SPEED_FACTOR;
/// Original `_37mm_Gochkins` maxDistance.
pub const MS1_MAX_DISTANCE: f32 = 720.0;
/// Compatibility floor for the original client's unguarded `velocity.x`
/// divisions in its range/arena boundary branches.  The floor is deliberately
/// tiny and preserves the launch speed; it is not a dispersion distribution.
pub const HORIZONTAL_X_FLOOR: f32 = 0.01;
const ROOT_STEP: f32 = 0.25;
const ROOT_LIMIT: f32 = 60.0;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Projectile {
    pub sequence: u32,
    pub slot: usize,
    pub origin: [f32; 3],
    pub velocity: [f32; 3],
    pub gravity: f32,
    pub max_distance: f32,
    pub launched: Instant,
    pub flight_time: Duration,
    pub terminal: [f32; 3],
    pub stopped: bool,
}

impl Projectile {
    pub fn launch(sequence: u32, slot: usize, actor: &model::Actor, now: Instant) -> io::Result<Self> {
        if sequence == 0 || slot >= model::CAPACITY || !actor.position.iter().all(|v| v.is_finite())
            || !actor.yaw.is_finite() || !actor.aim.yaw.is_finite() || !actor.aim.pitch.is_finite()
        {
            return Err(model::bad());
        }
        let (origin, velocity) = aim::shot_geometry(
            actor.position, actor.yaw, actor.aim.yaw, actor.aim.pitch, MS1_SPEED,
        );
        let velocity = regularize_horizontal_x(velocity)?;
        let flight_time = solve_range_time(velocity, MS1_GRAVITY, MS1_MAX_DISTANCE)?;
        let terminal = position_at(origin, velocity, MS1_GRAVITY, flight_time.as_secs_f32());
        if terminal.iter().any(|v| !v.is_finite()) {
            return Err(model::bad());
        }
        Ok(Self {
            sequence,
            slot,
            origin,
            velocity,
            gravity: MS1_GRAVITY,
            max_distance: MS1_MAX_DISTANCE,
            launched: now,
            flight_time,
            terminal,
            stopped: false,
        })
    }

    pub fn end_at(&self) -> io::Result<Instant> {
        self.launched.checked_add(self.flight_time).ok_or_else(model::bad)
    }

    pub fn position_at(&self, now: Instant) -> [f32; 3] {
        let elapsed = now.saturating_duration_since(self.launched).min(self.flight_time);
        position_at(self.origin, self.velocity, self.gravity, elapsed.as_secs_f32())
    }

    pub fn is_expired(&self, now: Instant) -> io::Result<bool> {
        Ok(now >= self.end_at()?)
    }
}

/// The original client divides by X velocity in two range/arena branches.
/// Keep that branch defined in this lab while preserving the effective speed.
pub fn regularize_horizontal_x(mut velocity: [f32; 3]) -> io::Result<[f32; 3]> {
    if velocity.iter().any(|v| !v.is_finite()) || velocity.iter().map(|v| v * v).sum::<f32>() <= 0.0 {
        return Err(model::bad());
    }
    if velocity[0].abs() >= HORIZONTAL_X_FLOOR { return Ok(velocity); }
    let sign = if velocity[0].is_sign_negative() { -1.0 } else { 1.0 };
    let speed2 = velocity.iter().map(|v| v * v).sum::<f32>();
    let rest2 = speed2 - HORIZONTAL_X_FLOOR * HORIZONTAL_X_FLOOR;
    let yz2 = velocity[1] * velocity[1] + velocity[2] * velocity[2];
    if rest2 <= 0.0 || yz2 <= 0.0 { return Err(model::bad()); }
    let scale = (rest2 / yz2).sqrt();
    velocity[0] = sign * HORIZONTAL_X_FLOOR;
    velocity[1] *= scale;
    velocity[2] *= scale;
    Ok(velocity)
}

pub fn position_at(origin: [f32; 3], velocity: [f32; 3], gravity: f32, seconds: f32) -> [f32; 3] {
    [
        origin[0] + velocity[0] * seconds,
        origin[1] + velocity[1] * seconds - 0.5 * gravity * seconds * seconds,
        origin[2] + velocity[2] * seconds,
    ]
}

fn distance_squared(velocity: [f32; 3], gravity: f32, seconds: f32) -> f32 {
    let p = position_at([0.; 3], velocity, gravity, seconds);
    p.iter().map(|v| v * v).sum()
}

/// Find the first positive radial-distance crossing with bounded bracketing.
/// Stock MS-1 flight crosses 720m in roughly two seconds; the larger bound is
/// only a fail-closed guard for malformed future profiles.
pub fn solve_range_time(velocity: [f32; 3], gravity: f32, max_distance: f32) -> io::Result<Duration> {
    if velocity.iter().any(|v| !v.is_finite()) || velocity.iter().map(|v| v * v).sum::<f32>() <= 0.0
        || !gravity.is_finite() || gravity <= 0.0
        || !max_distance.is_finite() || max_distance <= 0.0 { return Err(model::bad()); }
    let target = max_distance * max_distance;
    let mut low = 0.0f32;
    let mut high = ROOT_STEP;
    while distance_squared(velocity, gravity, high) < target {
        low = high;
        high *= 2.0;
        if high > ROOT_LIMIT { return Err(model::bad()); }
    }
    for _ in 0..40 {
        let middle = (low + high) * 0.5;
        if distance_squared(velocity, gravity, middle) < target { low = middle; } else { high = middle; }
    }
    let seconds = (low + high) * 0.5;
    if !seconds.is_finite() || seconds <= 0.0 { return Err(model::bad()); }
    Ok(Duration::from_secs_f32(seconds))
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::model::tests::world;

    #[test]
    fn pinned_effective_values_match_original_resource_factor() {
        assert!((MS1_SPEED - 353.6).abs() < 1e-5);
        assert!((MS1_GRAVITY - 6.2784).abs() < 1e-5);
        assert_eq!(MS1_MAX_DISTANCE, 720.0);
    }

    #[test]
    fn launch_uses_server_pose_and_native_sign_convention() {
        let now = Instant::now();
        let mut w = world(now);
        w.actors[0].aim.yaw = 0.;
        w.actors[0].aim.pitch = 0.;
        let p = Projectile::launch(1, 0, &w.actors[0], now).unwrap();
        assert!((p.velocity[2] - MS1_SPEED).abs() < 0.01);
        assert!(p.velocity[1].abs() < 0.01);
        w.actors[0].aim.pitch = -20f32.to_radians();
        let raised = Projectile::launch(2, 0, &w.actors[0], now).unwrap();
        assert!(raised.velocity[1] > 0.0);
        assert!(raised.terminal[1] > p.terminal[1]);
    }

    #[test]
    fn range_root_ends_on_exact_radial_distance_and_is_bounded() {
        let now = Instant::now();
        let w = world(now);
        let p = Projectile::launch(1, 0, &w.actors[0], now).unwrap();
        let d = p.terminal.iter().zip(p.origin).map(|(a,b)| (a-b)*(a-b)).sum::<f32>().sqrt();
        assert!((d - MS1_MAX_DISTANCE).abs() < 0.02);
        assert!(p.flight_time > Duration::from_secs_f32(1.0));
        assert!(p.flight_time < Duration::from_secs_f32(4.0));
        assert!(p.position_at(now + Duration::from_secs(100))[2].is_finite());
    }

    #[test]
    fn zero_x_compatibility_floor_preserves_speed() {
        let v = regularize_horizontal_x([0., 1., MS1_SPEED]).unwrap();
        let before = MS1_SPEED * MS1_SPEED + 1.;
        let after = v.iter().map(|x| x*x).sum::<f32>();
        assert_eq!(v[0], HORIZONTAL_X_FLOOR);
        assert!((before - after).abs() < 0.03);
        assert!(solve_range_time(v, MS1_GRAVITY, MS1_MAX_DISTANCE).is_ok());
    }

    #[test]
    fn invalid_geometry_fails_closed() {
        assert!(solve_range_time([0.;3], MS1_GRAVITY, MS1_MAX_DISTANCE).is_err());
        assert!(regularize_horizontal_x([f32::NAN,0.,1.]).is_err());
    }
}
