//! SHELL-CFG: the immutable shell rules snapshot of this gateway build.
//!
//! `config/shell_rules/snapshot.json` is built by `tools/shell_rules.py` from the
//! profile layers (Shell Mechanics 2.0 order) and embedded here with its exact-byte
//! pin (`rulesHash`). The process parses it once; every battle of the process uses
//! the same snapshot, so a profile change applies only to battles of a new build.
//! The laws (`p06t_damage`) read their numbers from here; the law identifiers in the
//! profile must equal the law code of this build.
use std::io;
use std::sync::OnceLock;
use serde_json::Value;
use sha2::{Digest, Sha256};
use crate::p06t_shells091::Family;

include!("shell_rules_pins.rs");
const SNAPSHOT: &[u8] = include_bytes!("../../../../config/shell_rules/snapshot.json");
const SCHEMA: &str = "wot091-shell-rules.v1";
/// SHELL-04 law of modules and crew under the layered law (owner 2026-11-08).
pub const MODULES_POLICY: &str = "project.modules-classic.v1";
const STATUSES: [&str; 5] = ["verified_091", "test_lab", "requires_verification", "experimental", "project_policy"];

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct FamilyRules { pub normalization_deg: f64, pub ricochet_deg: Option<f64>, pub caliber_rules: bool, pub distance_falloff: bool }

#[derive(Clone, Debug, PartialEq)]
pub struct Rules {
    pub rules_hash: String,
    pub config_version: u32,
    pub direct_law: String, pub track_law: String, pub unarmored_device_law: String, pub layers_law: String, pub he_law: String, pub modules_law: String, pub accuracy_law: String,
    /// Indexed by `family_index`.
    pub families: [FamilyRules; 4],
    pub normalization_ratio: f64, pub normalization_multiplier: f64, pub no_ricochet_ratio: f64,
    pub full_power_until_m: f64, pub linear_span_m: f64,
    pub he_damage_factor: f64, pub he_armor_factor: f64,
    /// configVersion 2 (layered law): +-percent of the uniform rolls, one penetration roll per shot.
    pub penetration_random_percent: f64, pub damage_random_percent: f64,
    /// Owner 2026-11-06: HEAT stops on a spaced layer or a track.
    pub heat_stops_on_spaced: bool,
    /// #717 reads the shell caliber with readInt (FV215b 182.9 -> 182).
    pub caliber_integer: bool,
    /// configVersion 3 (SHELL-03, owner 2026-11-08), layered law only: HE/HESH pass a screen or
    /// track by `max(0, (P - t*K) * (1 - L))`; splash falloff exponent; HESH splash factor.
    pub he_screen_formula: bool, pub he_falloff_exponent: f64,
    pub he_screen: Screen, pub hesh_screen: Screen, pub hesh_splash_factor: f64,
    /// configVersion 4 (SHELL-04, owner 2026-11-08), layered law only: internal trace length in
    /// engine-integer calibers and the #717 common/vehicle.xml hit chances [projectile, explosion].
    pub internal_trace_calibers: f64, pub module_chances: [[f64; 2]; 10],
    /// configVersion 5 (DISP-01, owner 2026-11-09), layered law only.
    pub accuracy: Accuracy,
}
/// Shell Mechanics 2.0 section 3: `k(A) = clamp(base + slope*(A - reference), min, max)`, the
/// share of shots inside `k*R`, and the SPG truncated normal's sigma as a fraction of `R`.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Accuracy { pub central_probability: f64, pub reference: f64, pub base: f64, pub slope: f64, pub min: f64, pub max: f64, pub spg_sigma_fraction: f64 }
/// Module groups of #717 common/vehicle.xml MaterialInfo (crew: every role and seat).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ModuleClass { Engine, AmmoBay, FuelTank, Radio, Track, Gun, GunBreech, TurretRotator, SurveyingDevice, Crew }
pub const MODULE_CLASSES: [&str; 10] = ["engine", "ammo_bay", "fuel_tank", "radio", "track", "gun", "gun_breech", "turret_rotator", "surveying_device", "crew"];
impl Rules {
    /// The source chance that a crossing (projectile) or an explosion hits this module.
    pub fn module_chance(&self, class: ModuleClass, explosion: bool) -> f64 { self.module_chances[class as usize][usize::from(explosion)] }
}
/// Shell Mechanics 2.0 section 5 candidate: resistance `K` and extra loss `L` of a screen.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Screen { pub resistance: f64, pub loss: f64 }
impl Rules {
    pub fn family(&self, family: Family) -> FamilyRules { self.families[family_index(family)] }
}

pub fn family_index(family: Family) -> usize {
    match family { Family::ArmorPiercing => 0, Family::ArmorPiercingCr => 1, Family::HollowCharge => 2, Family::HighExplosive => 3 }
}

fn bad(message: String) -> io::Error { io::Error::new(io::ErrorKind::InvalidData, format!("shell rules: {message}")) }

fn exact<'a>(value: &'a Value, keys: &[&str], path: &str) -> io::Result<&'a serde_json::Map<String, Value>> {
    let map = value.as_object().ok_or_else(|| bad(format!("{path}: object")))?;
    if map.len() != keys.len() || keys.iter().any(|k| !map.contains_key(*k)) { return Err(bad(format!("{path}: keys"))); }
    Ok(map)
}
fn leaf<'a>(section: &'a Value, key: &str, path: &str) -> io::Result<&'a Value> {
    let path = format!("{path}.{key}");
    let leaf = exact(&section[key], &["value", "status", "source"], &path)?;
    if !leaf["status"].as_str().is_some_and(|s| STATUSES.contains(&s)) || !leaf["source"].as_str().is_some_and(|s| !s.is_empty() && s.len() <= 512) {
        return Err(bad(format!("{path}: status/source")));
    }
    Ok(&leaf["value"])
}
fn number(section: &Value, key: &str, path: &str, low: f64, high: f64) -> io::Result<f64> {
    leaf(section, key, path)?.as_f64().filter(|v| v.is_finite() && (low..=high).contains(v)).ok_or_else(|| bad(format!("{path}.{key}: number")))
}
fn boolean(section: &Value, key: &str, path: &str) -> io::Result<bool> {
    leaf(section, key, path)?.as_bool().ok_or_else(|| bad(format!("{path}.{key}: bool")))
}
fn choice(section: &Value, key: &str, path: &str, allowed: &[&str]) -> io::Result<String> {
    leaf(section, key, path)?.as_str().filter(|v| allowed.contains(v)).map(str::to_owned).ok_or_else(|| bad(format!("{path}.{key}: choice")))
}
fn law(section: &Value, key: &str, expected: &str) -> io::Result<String> {
    let value = leaf(section, key, "rules.laws")?.as_str().ok_or_else(|| bad(format!("rules.laws.{key}: string")))?;
    if value != expected { return Err(bad(format!("rules.laws.{key}: profile names {value}, this build implements {expected}"))); }
    Ok(value.to_owned())
}

/// Parse and verify a snapshot (exact bytes, closed schema, law identity).
pub fn parse(raw: &[u8], expected_sha256: &str) -> io::Result<Rules> {
    let digest = format!("{:x}", Sha256::digest(raw));
    if digest != expected_sha256 { return Err(bad("snapshot bytes differ from the pinned rulesHash".into())); }
    if raw.len() > 64 * 1024 { return Err(bad("snapshot size".into())); }
    let doc: Value = serde_json::from_slice(raw).map_err(|_| bad("snapshot JSON".into()))?;
    let top = exact(&doc, &["schema", "config_version", "profile", "historical_baseline", "layers", "rules"], "snapshot")?;
    if top["schema"] != SCHEMA || top["profile"] != "classic_plus" || top["historical_baseline"] != "wot_0_9_1" {
        return Err(bad("snapshot identity".into()));
    }
    let config_version = top["config_version"].as_u64().and_then(|v| u32::try_from(v).ok()).filter(|v| *v >= 1)
        .ok_or_else(|| bad("config_version".into()))?;
    if config_version != CONFIG_VERSION && expected_sha256 == RULES_SHA256 { return Err(bad("config_version differs from the pin".into())); }
    if !top["layers"].as_array().is_some_and(|l| l.len() == 7) { return Err(bad("layers".into())); }
    let rules = &top["rules"];
    exact(rules, &["laws", "families", "caliber", "falloff", "high_explosive", "randomization", "layers", "engine", "damage", "modules", "accuracy"], "rules")?;
    let laws = &rules["laws"];
    exact(laws, &["direct", "track", "unarmored_device", "layers", "he", "modules", "accuracy"], "rules.laws")?;
    let families = &rules["families"];
    let names = ["armor_piercing", "armor_piercing_cr", "hollow_charge", "high_explosive"];
    exact(families, &names, "rules.families")?;
    let mut table = [FamilyRules { normalization_deg: 0., ricochet_deg: None, caliber_rules: false, distance_falloff: false }; 4];
    for (index, name) in names.iter().enumerate() {
        let path = format!("rules.families.{name}");
        let family = &families[*name];
        exact(family, &["normalization_deg", "ricochet_deg", "caliber_rules", "distance_falloff"], &path)?;
        let ricochet = leaf(family, "ricochet_deg", &path)?;
        table[index] = FamilyRules {
            normalization_deg: number(family, "normalization_deg", &path, 0., 90.)?,
            ricochet_deg: if ricochet.is_null() { None } else {
                Some(ricochet.as_f64().filter(|v| v.is_finite() && (0. ..=90.).contains(v)).ok_or_else(|| bad(format!("{path}.ricochet_deg")))?) },
            caliber_rules: boolean(family, "caliber_rules", &path)?,
            distance_falloff: boolean(family, "distance_falloff", &path)?,
        };
    }
    let caliber = &rules["caliber"];
    exact(caliber, &["normalization_ratio", "normalization_multiplier", "no_ricochet_ratio"], "rules.caliber")?;
    let falloff = &rules["falloff"];
    exact(falloff, &["full_power_until_m", "linear_span_m"], "rules.falloff")?;
    let he = &rules["high_explosive"];
    exact(he, &["damage_factor", "armor_factor", "falloff_exponent", "screen_resistance", "screen_loss",
        "hesh_screen_resistance", "hesh_screen_loss", "hesh_splash_factor", "splash_ray", "damage_roll"], "rules.high_explosive")?;
    choice(he, "splash_ray", "rules.high_explosive", &["one_ray_layers"])?;
    choice(he, "damage_roll", "rules.high_explosive", &["shot_damage_roll"])?;
    let random = &rules["randomization"];
    exact(random, &["penetration_percent", "damage_percent", "distribution", "penetration_rolls_per_shot"], "rules.randomization")?;
    choice(random, "distribution", "rules.randomization", &["uniform"])?;
    choice(random, "penetration_rolls_per_shot", "rules.randomization", &["one"])?;
    let layers = &rules["layers"];
    exact(layers, &["entry", "heat_on_spaced", "he_on_spaced", "after_ricochet"], "rules.layers")?;
    choice(layers, "entry", "rules.layers", &["against_winding"])?;
    choice(layers, "after_ricochet", "rules.layers", &["shot_ends"])?;
    let engine = &rules["engine"];
    exact(engine, &["caliber_integer"], "rules.engine")?;
    let damage = &rules["damage"];
    exact(damage, &["rounding"], "rules.damage")?;
    choice(damage, "rounding", "rules.damage", &["half_away_from_zero"])?;
    let accuracy = &rules["accuracy"];
    exact(accuracy, &["central_probability", "reference_accuracy", "base", "slope", "min", "max", "circle", "spg_distribution", "spg_sigma_fraction"], "rules.accuracy")?;
    choice(accuracy, "circle", "rules.accuracy", &["classic_091"])?;
    choice(accuracy, "spg_distribution", "rules.accuracy", &["truncated_normal"])?;
    let parsed_accuracy = Accuracy {
        central_probability: number(accuracy, "central_probability", "rules.accuracy", 0.5, 0.95)?,
        reference: number(accuracy, "reference_accuracy", "rules.accuracy", 0.05, 2.)?,
        base: number(accuracy, "base", "rules.accuracy", 0.05, 1.)?, slope: number(accuracy, "slope", "rules.accuracy", -5., 5.)?,
        min: number(accuracy, "min", "rules.accuracy", 0.05, 1.)?, max: number(accuracy, "max", "rules.accuracy", 0.05, 1.)?,
        spg_sigma_fraction: number(accuracy, "spg_sigma_fraction", "rules.accuracy", 0.1, 1.)?,
    };
    if parsed_accuracy.min > parsed_accuracy.max || parsed_accuracy.max >= 1. { return Err(bad("rules.accuracy: k bounds".into())); }
    let modules = &rules["modules"];
    let mut module_keys = vec!["internal_trace_calibers", "chance_gate", "critical", "he", "device_damage_roll"];
    let chance_keys: Vec<String> = MODULE_CLASSES.iter().flat_map(|m| [format!("{m}_projectile"), format!("{m}_explosion")]).collect();
    module_keys.extend(chance_keys.iter().map(String::as_str));
    exact(modules, &module_keys, "rules.modules")?;
    choice(modules, "chance_gate", "rules.modules", &["per_module_roll"])?;
    choice(modules, "critical", "rules.modules", &["at_or_below_max_regen"])?;
    choice(modules, "he", "rules.modules", &["external_on_non_penetration"])?;
    choice(modules, "device_damage_roll", "rules.modules", &["shot_damage_roll"])?;
    let mut module_chances = [[0.; 2]; 10];
    for (index, name) in MODULE_CLASSES.iter().enumerate() {
        for (kind, label) in ["projectile", "explosion"].iter().enumerate() {
            module_chances[index][kind] = number(modules, &format!("{name}_{label}"), "rules.modules", 0., 1.)?;
        }
    }
    Ok(Rules {
        rules_hash: digest, config_version,
        direct_law: law(laws, "direct", crate::p06t_damage::POLICY)?,
        track_law: law(laws, "track", crate::p06t_damage::TRACK_PASS_POLICY)?,
        unarmored_device_law: law(laws, "unarmored_device", crate::p06t_damage::UNARMORED_DEVICE_POLICY)?,
        layers_law: law(laws, "layers", crate::p06t_damage::LAYERS_POLICY)?,
        he_law: law(laws, "he", crate::p06t_damage::HE_POLICY)?,
        modules_law: law(laws, "modules", MODULES_POLICY)?,
        accuracy_law: law(laws, "accuracy", crate::gateway091::shared::dispersion::ACCURACY_POLICY)?,
        families: table,
        normalization_ratio: number(caliber, "normalization_ratio", "rules.caliber", 1., 20.)?,
        normalization_multiplier: number(caliber, "normalization_multiplier", "rules.caliber", 0., 10.)?,
        no_ricochet_ratio: number(caliber, "no_ricochet_ratio", "rules.caliber", 1., 20.)?,
        full_power_until_m: number(falloff, "full_power_until_m", "rules.falloff", 0., 1000.)?,
        linear_span_m: number(falloff, "linear_span_m", "rules.falloff", 1., 2000.)?,
        he_damage_factor: number(he, "damage_factor", "rules.high_explosive", 0., 1.)?,
        he_armor_factor: number(he, "armor_factor", "rules.high_explosive", 0., 10.)?,
        penetration_random_percent: number(random, "penetration_percent", "rules.randomization", 0., 50.)?,
        damage_random_percent: number(random, "damage_percent", "rules.randomization", 0., 50.)?,
        heat_stops_on_spaced: choice(layers, "heat_on_spaced", "rules.layers", &["stop", "pass"])? == "stop",
        caliber_integer: boolean(engine, "caliber_integer", "rules.engine")?,
        he_screen_formula: choice(layers, "he_on_spaced", "rules.layers", &["stop", "screen_formula"])? == "screen_formula",
        he_falloff_exponent: number(he, "falloff_exponent", "rules.high_explosive", 0.25, 8.)?,
        he_screen: Screen { resistance: number(he, "screen_resistance", "rules.high_explosive", 0., 10.)?,
            loss: number(he, "screen_loss", "rules.high_explosive", 0., 1.)? },
        hesh_screen: Screen { resistance: number(he, "hesh_screen_resistance", "rules.high_explosive", 0., 10.)?,
            loss: number(he, "hesh_screen_loss", "rules.high_explosive", 0., 1.)? },
        hesh_splash_factor: number(he, "hesh_splash_factor", "rules.high_explosive", 0., 1.)?,
        internal_trace_calibers: number(modules, "internal_trace_calibers", "rules.modules", 1., 100.)?,
        module_chances,
        accuracy: parsed_accuracy,
    })
}

static RULES: OnceLock<Result<Rules, String>> = OnceLock::new();

/// The process snapshot (embedded bytes, parsed once).
pub fn rules() -> io::Result<&'static Rules> {
    RULES.get_or_init(|| parse(SNAPSHOT, RULES_SHA256).map_err(|e| e.to_string())).as_ref()
        .map_err(|message| io::Error::new(io::ErrorKind::InvalidData, message.clone()))
}

/// One shot's rolls: uniform factors in [1 - p, 1 + p) and the per-shot seed they come from.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Rolls { pub seed: u64, pub penetration: f64, pub damage: f64 }

fn splitmix(state: &mut u64) -> u64 {
    *state = state.wrapping_add(0x9e37_79b9_7f4a_7c15);
    let mut z = *state;
    z = (z ^ (z >> 30)).wrapping_mul(0xbf58_476d_1ce4_e5b9);
    z = (z ^ (z >> 27)).wrapping_mul(0x94d0_49bb_1331_11eb);
    z ^ (z >> 31)
}
fn unit(state: &mut u64) -> f64 { (splitmix(state) >> 11) as f64 / (1u64 << 53) as f64 }

/// Rolls from a recorded per-shot seed (replay) under these rules.
pub fn rolls_from_seed(rules: &Rules, seed: u64) -> Rolls {
    let mut state = seed;
    let penetration = 1. + rules.penetration_random_percent / 100. * (2. * unit(&mut state) - 1.);
    let damage = 1. + rules.damage_random_percent / 100. * (2. * unit(&mut state) - 1.);
    Rolls { seed, penetration, damage }
}

/// DISP-01: the two dispersion draws of a shot, the stream's third and fourth values after the
/// penetration and damage rolls, in [0, 1).
pub fn dispersion_draws(seed: u64) -> (f64, f64) {
    let mut state = seed;
    unit(&mut state); unit(&mut state);
    let radial = unit(&mut state);
    (radial, unit(&mut state))
}

/// A per-process secret: rolls are not predictable from a battle or shot id a client
/// sees. The per-shot seed (not the secret) goes into the shot trace for replay.
#[cfg(test)]
fn process_secret() -> u64 { 0x5eed_0d15_9e75_ed01 } // Fixed in tests: a shot's rolls and deviation repeat run to run.
#[cfg(not(test))]
fn process_secret() -> u64 {
    static SECRET: OnceLock<u64> = OnceLock::new();
    *SECRET.get_or_init(|| {
        use std::hash::{BuildHasher, Hasher};
        let mut h = std::collections::hash_map::RandomState::new().build_hasher();
        h.write_u128(std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0, |d| d.as_nanos()));
        h.write_u32(std::process::id());
        h.finish()
    })
}

/// The one penetration roll and the damage roll of a shot (same for every layer and
/// for the live World and its Trace check, which both call this).
pub fn shot_rolls(rules: &Rules, battle_id: u64, shot_id: u32) -> Rolls {
    let mut state = process_secret() ^ battle_id.rotate_left(17) ^ u64::from(shot_id).wrapping_mul(0x9e37_79b9_7f4a_7c15);
    let seed = splitmix(&mut state);
    rolls_from_seed(rules, seed)
}

#[cfg(test)]
#[path = "shell_rules_tests.rs"]
mod tests;
