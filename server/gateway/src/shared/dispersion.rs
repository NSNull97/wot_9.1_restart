//! DISP-01: the aiming circle and the shot deviation of the layered law (owner 2026-11-09).
//!
//! The circle is the #717 client's own `Avatar.getOwnVehicleShotDispersionAngle` (VERIFIED from its
//! bytecode), so the marker the client draws and the server's circle use one formula. How the
//! 0.9.1 server placed a shot inside the circle is UNKNOWN: inside it this is the project's Dual
//! Dispersion 2.0, whose coefficients are experimental.
use std::{io, sync::OnceLock};
use serde_json::Value;
use sha2::{Digest, Sha256};
use super::shell_rules::{dispersion_draws, Accuracy};
use super::vehicle_profile::AimSpec;

include!("gun_dispersion_pins.rs");
pub const ACCURACY_POLICY: &str = "project.dual-dispersion.v1";
const TABLE: &[u8] = include_bytes!("../../../../config/catalog/gun_dispersion.v1.json");

fn bad() -> io::Error { io::Error::new(io::ErrorKind::InvalidData, "invalid gun dispersion") }

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Gun { pub radius_m: f64, pub after_shot: f64, pub spg: bool }

fn parse() -> io::Result<std::collections::BTreeMap<String, Gun>> {
    if format!("{:x}", Sha256::digest(TABLE)) != TABLE_SHA256 { return Err(bad()); }
    let doc: Value = serde_json::from_slice(TABLE).map_err(|_| bad())?;
    if doc["schema"] != "wot091-gun-dispersion.v1" { return Err(bad()); }
    let mut out = std::collections::BTreeMap::new();
    for (name, row) in doc["guns"].as_object().filter(|m| !m.is_empty()).ok_or_else(bad)? {
        let number = |key: &str| row[key].as_f64().filter(|v| v.is_finite() && *v > 0. && *v < 100.).ok_or_else(bad);
        out.insert(name.clone(), Gun { radius_m: number("radius_m")?, after_shot: number("after_shot")?, spg: row["spg"].as_bool().ok_or_else(bad)? });
    }
    Ok(out)
}
/// The gun data of a vehicle kind name (`VehicleKind::name`).
pub fn gun(name: &str) -> io::Result<Gun> {
    static GUNS: OnceLock<Result<std::collections::BTreeMap<String, Gun>, String>> = OnceLock::new();
    GUNS.get_or_init(|| parse().map_err(|e| e.to_string())).as_ref()
        .map_err(|_| bad())?.get(name).copied().ok_or_else(bad)
}

/// The rates one server step gave the actor, in the client's units (m/s, rad/s).
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Motion { pub speed: f32, pub hull_rate: f32, pub turret_rate: f32 }

/// The client's `idealFactor`; `shot` is 0 or the gun's afterShot, the additive factor is 1.
pub fn ideal(spec: &AimSpec, motion: Motion, shot: f64, mult: f64) -> f64 {
    let square = |value: f32, factor: f32| (f64::from(value) * f64::from(factor)).powi(2);
    mult * (1. + square(motion.speed, spec.movement_dispersion) + square(motion.hull_rate, spec.hull_dispersion)
        + square(motion.turret_rate, spec.turret_dispersion) + shot * shot).sqrt()
}

/// The client's aiming factor: it decays by `exp(-dt/aimingTime)`, never below the ideal.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct State { pub factor: f64, pub hull_yaw: f32, pub turret_yaw: f32 }
// BW-01 wire codec (tools/bw01_wire_gen.py): State
impl crate::bw_wire::Wire for State {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{factor,hull_yaw,turret_yaw}=self;W::put(factor,bw_o);W::put(hull_yaw,bw_o);W::put(turret_yaw,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{factor:W::get(bw_i)?,hull_yaw:W::get(bw_i)?,turret_yaw:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl State {
    pub fn new(hull_yaw: f32, turret_yaw: f32) -> Self { Self { factor: 1., hull_yaw, turret_yaw } }
    pub fn step(&mut self, spec: &AimSpec, speed: f32, hull_yaw: f32, turret_yaw: f32, mult: f64, dt: f32) -> io::Result<()> {
        if !(dt > 0.) || !dt.is_finite() || spec.aiming_time <= 0. { return Err(bad()); }
        let wrap = |d: f32| super::aim::wrap(d).abs() / dt;
        let motion = Motion { speed: speed.abs(), hull_rate: wrap(hull_yaw - self.hull_yaw), turret_rate: wrap(turret_yaw - self.turret_yaw) };
        self.hull_yaw = hull_yaw; self.turret_yaw = turret_yaw;
        let decayed = self.factor * (-f64::from(dt) / f64::from(spec.aiming_time)).exp();
        self.factor = decayed.max(ideal(spec, motion, 0., mult));
        if !self.factor.is_finite() { return Err(bad()); }
        Ok(())
    }
    /// The bloom of a fired shot: the ideal with the gun's afterShot, as the client's `withShot`.
    pub fn after_shot(&mut self, spec: &AimSpec, gun: Gun, speed: f32, mult: f64) {
        let bloom = ideal(spec, Motion { speed: speed.abs(), hull_rate: 0., turret_rate: 0. }, gun.after_shot, mult);
        self.factor = self.factor.max(bloom);
    }
    /// The circle's angular radius now (radians).
    pub fn angle(&self, gun: Gun) -> f64 { (gun.radius_m / 100.).atan() * self.factor }
}

/// `k(A)` of Shell Mechanics 2.0 for a gun's accuracy `A` (metres at 100 m).
pub fn central_zone(accuracy: &Accuracy, a: f64) -> f64 {
    (accuracy.base + accuracy.slope * (a - accuracy.reference)).clamp(accuracy.min, accuracy.max)
}
/// Radial inverse CDF of a normal in the disc, truncated at the circle (`s` = sigma / R).
fn truncated(s: f64, u: f64) -> f64 { s * (-2. * (1. - u * (1. - (-1. / (2. * s * s)).exp())).ln()).sqrt() }
/// Share of a truncated normal of sigma `s` that falls inside `k * R`.
fn share_inside(s: f64, k: f64) -> f64 { (1. - (-k * k / (2. * s * s)).exp()) / (1. - (-1. / (2. * s * s)).exp()) }
/// Sigma / R that puts `probability` of the shots inside `k * R` (owner 2026-11-09: the 2.0 `U^alpha`
/// put 41 % of a battle's shots within 0.1 R, so the 75 % target keeps a normal shape instead).
pub fn central_sigma(k: f64, probability: f64) -> f64 {
    let (mut low, mut high) = (0.02f64, 8f64);
    for _ in 0..80 {
        let middle = (low + high) / 2.;
        if share_inside(middle, k) > probability { low = middle; } else { high = middle; }
    }
    (low + high) / 2.
}
/// The radial fraction of the circle: the truncated normal holding the central share in `k(A)`,
/// or the SPG truncated normal.
pub fn radial_fraction(accuracy: &Accuracy, gun: Gun, u: f64) -> f64 {
    let s = if gun.spg { accuracy.spg_sigma_fraction } else { central_sigma(central_zone(accuracy, gun.radius_m), accuracy.central_probability) };
    truncated(s, u)
}
/// The shot's deviation from the barrel line: angle (radians) and direction (radians), from its seed.
pub fn deviation(accuracy: &Accuracy, gun: Gun, angle: f64, seed: u64) -> (f64, f64) {
    let (u, t) = dispersion_draws(seed);
    (angle * radial_fraction(accuracy, gun, u), t * std::f64::consts::TAU)
}
/// `velocity` turned by `r` from itself in the direction `theta` around it; the length is kept.
pub fn deviate(velocity: [f32; 3], r: f64, theta: f64) -> io::Result<[f32; 3]> {
    let v = velocity.map(f64::from);
    let speed = v.iter().map(|x| x * x).sum::<f64>().sqrt();
    if !(speed > 0.) || !speed.is_finite() || !r.is_finite() || !theta.is_finite() { return Err(bad()); }
    let d = v.map(|x| x / speed);
    // A side axis perpendicular to the shot and the world up (the x axis for a vertical shot).
    let side = { let c = [d[2], 0., -d[0]]; let n = (c[0] * c[0] + c[2] * c[2]).sqrt(); if n > 1e-9 { c.map(|x| x / n) } else { [1., 0., 0.] } };
    let up = [d[1] * side[2] - d[2] * side[1], d[2] * side[0] - d[0] * side[2], d[0] * side[1] - d[1] * side[0]];
    let (sr, cr, st, ct) = (r.sin(), r.cos(), theta.sin(), theta.cos());
    Ok(std::array::from_fn(|i| ((cr * d[i] + sr * (ct * side[i] + st * up[i])) * speed) as f32))
}

#[cfg(test)]
#[path = "dispersion_tests.rs"]
mod tests;
