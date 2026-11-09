//! SHELL-CFG: per-shot trace of the armour-level law decisions and their replay.
//!
//! Enabled only by the stand diagnostics directory (`WOT091_STAB_DIAGNOSTICS_DIR`,
//! the same switch as the cadence diagnostics): one JSON line per decision the
//! battle trace has verified (`impact::Trace` direct, track and splash rows), with
//! the law inputs, the result and the `rulesHash` of the process snapshot. Bounded:
//! 8 KiB per line, 256 MiB per process file; the end is marked, never silent.
//! A write failure switches the trace off with one stderr line; battles go on.
//!
//! `sr-gateway shell-shot-replay FILE` recomputes every line with this build's law
//! and snapshot and reports mismatches (expected 0). Accuracy, aiming and RNG fields
//! do not exist yet in the law and are not invented here.
use std::fs::{File, OpenOptions};
use std::io::{self, BufRead, BufReader, Write};
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};
use serde_json::{json, Value};
use crate::p06t_damage::{self as law, DirectInput, Layer, LayerPass, Plate, Resolution, SplashDamage, SplashTarget, TrackPass};
use crate::p06t_shells091::{Family, Shell};
use crate::gateway091::shared::shell_rules::{ModuleClass, Rolls, MODULE_CLASSES};
use super::vehicle_profile::VehicleKind;

pub const SCHEMA: &str = "wot091-shot-trace.v1";
const ENV_DIR: &str = "WOT091_STAB_DIAGNOSTICS_DIR";
const MAX_LINE: usize = 8 * 1024;
const MAX_FILE: u64 = 256 * 1024 * 1024;
const MAX_REPLAY_LINES: usize = 4_000_000;

struct Sink { file: File, path: PathBuf, bytes: u64, closed: bool }
static SINK: OnceLock<Option<Mutex<Sink>>> = OnceLock::new();

fn bad(message: &str) -> io::Error { io::Error::new(io::ErrorKind::InvalidData, format!("shot trace: {message}")) }

fn open() -> Option<Mutex<Sink>> {
    let dir = PathBuf::from(std::env::var_os(ENV_DIR)?);
    if !dir.is_dir() { eprintln!("SHOT_TRACE_DISABLED reason=diagnostics-dir-absent"); return None; }
    let path = dir.join(format!("shots-{}.jsonl", std::process::id()));
    match OpenOptions::new().create_new(true).write(true).open(&path) {
        Ok(file) => { println!("SHOT_TRACE_ENABLED path={} schema={SCHEMA}", path.display()); Some(Mutex::new(Sink { file, path, bytes: 0, closed: false })) }
        Err(e) => { eprintln!("SHOT_TRACE_DISABLED reason=open path={} error={e}", path.display()); None }
    }
}

pub fn enabled() -> bool { SINK.get_or_init(open).is_some() }

fn write(mut record: Value) {
    let Some(sink) = SINK.get_or_init(open) else { return };
    let Ok(mut sink) = sink.lock() else { eprintln!("SHOT_TRACE_DISABLED reason=poisoned"); return };
    if sink.closed { return; }
    let rules = match crate::gateway091::shared::shell_rules::rules() { Ok(r) => r, Err(e) => { eprintln!("SHOT_TRACE_DISABLED reason=rules error={e}"); sink.closed = true; return } };
    record["schema"] = SCHEMA.into();
    record["rules_hash"] = rules.rules_hash.clone().into();
    record["config_version"] = rules.config_version.into();
    let mut line = match serde_json::to_vec(&record) { Ok(v) => v, Err(e) => { eprintln!("SHOT_TRACE_DISABLED reason=encode error={e}"); sink.closed = true; return } };
    line.push(b'\n');
    let over = line.len() > MAX_LINE || sink.bytes + line.len() as u64 > MAX_FILE;
    let result = if over {
        sink.closed = true;
        let end = format!("{{\"schema\":\"{SCHEMA}\",\"kind\":\"limit\",\"bytes\":{},\"line_bytes\":{}}}\n", sink.bytes, line.len());
        eprintln!("SHOT_TRACE_LIMIT path={} bytes={}", sink.path.display(), sink.bytes);
        sink.file.write_all(end.as_bytes())
    } else { sink.file.write_all(&line) };
    match result {
        Ok(()) => sink.bytes += line.len() as u64,
        Err(e) => { eprintln!("SHOT_TRACE_DISABLED reason=write path={} error={e}", sink.path.display()); sink.closed = true; }
    }
}

/// Floats carry their IEEE bits; replay reads and compares the bits, never the decimal text.
fn fb(x: f64) -> Value { json!({"v": x, "bits": format!("{:016x}", x.to_bits())}) }
fn fbo(x: Option<f64>) -> Value { x.map_or(Value::Null, fb) }
fn f3(v: [f32; 3]) -> Value { json!(v.map(|x| json!({"v": x, "bits": format!("{:08x}", x.to_bits())}))) }
fn shell_json(shell: &Shell) -> Value { json!({"compact": shell.compact_descr, "resource": shell.resource}) }
fn resolution_json(r: &Resolution) -> Value {
    json!({"policy": r.policy, "decision": format!("{:?}", r.decision), "damage_hp": r.damage_hp, "incidence_deg": fb(r.incidence_degrees),
           "effective_armor_mm": fbo(r.effective_armor_mm), "nominal_power_mm": fb(r.nominal_power_mm), "normalization_deg": fb(r.normalization_degrees)})
}
fn pass_json(p: &TrackPass) -> Value { json!({"power_before_mm": fb(p.power_before_mm), "power_after_mm": fb(p.power_after_mm), "stopped": p.stopped}) }
/// A shell compact id is not unique: #717 gives piercing power per gun, so the same
/// shell has different power on different guns. The record names the attacker's
/// vehicle kind; replay takes the shell from that kind's gun profile, as the battle did.
#[allow(clippy::too_many_arguments)]
fn context(kind: &str, battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, attacker_kind: VehicleKind) -> Value {
    json!({"kind": kind, "battle_id": battle, "shot_id": shot, "server_tick": tick, "attacker": attacker, "target": target,
           "attacker_kind": attacker_kind.label(), "gun": crate::p06t_shells091::profile(attacker_kind.mount()).gun_compact_descr,
           "accuracy": Value::Null, "rng": Value::Null})
}

#[allow(clippy::too_many_arguments)]
pub fn direct(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, attacker_kind: VehicleKind, input: &DirectInput, spent_mm: f64,
              unarmored_device: bool, rolls: Option<Rolls>, result: &Resolution) {
    let mut v = direct_record(battle, shot, tick, attacker, target, attacker_kind, input, spent_mm, unarmored_device, result);
    v["rng"] = rolls_json(rolls);
    write(v);
}
/// The shot's seed and rolls (null under the single-plate law); replay derives the
/// rolls again from the seed with the snapshot of the record's rulesHash.
fn rolls_json(rolls: Option<Rolls>) -> Value {
    rolls.map_or(Value::Null, |r| json!({"stream": "splitmix64-v1", "seed": format!("{:016x}", r.seed),
        "penetration": fb(r.penetration), "damage": fb(r.damage)}))
}
fn rolls_of(record: &Value) -> io::Result<Option<Rolls>> {
    let rng = &record["rng"];
    if rng.is_null() { return Ok(None); }
    let seed = rng["seed"].as_str().filter(|s| s.len() == 16).and_then(|s| u64::from_str_radix(s, 16).ok()).ok_or_else(|| bad("rng seed"))?;
    Ok(Some(crate::gateway091::shared::shell_rules::rolls_from_seed(crate::gateway091::shared::shell_rules::rules()?, seed)))
}
#[allow(clippy::too_many_arguments)]
fn direct_record(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, attacker_kind: VehicleKind, input: &DirectInput, spent_mm: f64,
                 unarmored_device: bool, result: &Resolution) -> Value {
    let mut v = context("direct", battle, shot, tick, attacker, target, attacker_kind);
    v["shell"] = shell_json(&input.shell);
    v["input"] = json!({"armor_mm": fbo(input.plate.armor_mm), "ordinary": input.plate.ordinary, "chord": f3(input.chord),
                        "winding_normal": f3(input.winding_normal), "distance_m": fb(input.distance_m), "spent_mm": fb(spent_mm),
                        "unarmored_device": unarmored_device});
    v["result"] = resolution_json(result);
    v
}
#[allow(clippy::too_many_arguments)]
pub fn track(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, attacker_kind: VehicleKind, shell: &Shell, distance_m: f64,
             spent_before_mm: f64, armor_mm: f64, rolls: Option<Rolls>, pass: &TrackPass) {
    let mut v = track_record(battle, shot, tick, attacker, target, attacker_kind, shell, distance_m, spent_before_mm, armor_mm, pass);
    v["rng"] = rolls_json(rolls);
    write(v);
}
#[allow(clippy::too_many_arguments)]
fn track_record(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, attacker_kind: VehicleKind, shell: &Shell, distance_m: f64,
                spent_before_mm: f64, armor_mm: f64, pass: &TrackPass) -> Value {
    let mut v = context("track", battle, shot, tick, attacker, target, attacker_kind);
    v["shell"] = shell_json(shell);
    v["input"] = json!({"distance_m": fb(distance_m), "spent_before_mm": fb(spent_before_mm), "armor_mm": fb(armor_mm)});
    v["result"] = pass_json(pass);
    v
}
#[allow(clippy::too_many_arguments)]
pub fn splash(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, attacker_kind: VehicleKind, shell: &Shell, input: &SplashTarget,
              rolls: Option<Rolls>, layers_mm: f64, result: &SplashDamage) {
    write(splash_rolled(battle, shot, tick, attacker, target, attacker_kind, shell, input, rolls, layers_mm, result));
}
#[allow(clippy::too_many_arguments)]
fn splash_rolled(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, attacker_kind: VehicleKind, shell: &Shell, input: &SplashTarget,
                 rolls: Option<Rolls>, layers_mm: f64, result: &SplashDamage) -> Value {
    let mut v = splash_record(battle, shot, tick, attacker, target, attacker_kind, shell, input, result);
    // SHELL-03: the shot's damage roll and, for reading only, the screens/tracks share of armor_mm.
    v["rng"] = rolls_json(rolls);
    if rolls.is_some() { v["input"]["layers_mm"] = fb(layers_mm); v["shell_type"] = if law::hesh(*shell) { "HESH" } else { "HE" }.into(); }
    v
}
#[allow(clippy::too_many_arguments)]
fn splash_record(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, attacker_kind: VehicleKind, shell: &Shell, input: &SplashTarget, result: &SplashDamage) -> Value {
    let mut v = context("splash", battle, shot, tick, attacker, target, attacker_kind);
    v["shell"] = shell_json(shell);
    v["input"] = json!({"slot": input.slot, "distance_m": fb(input.distance_m), "armor_mm": fb(input.armor_mm), "los_clear": input.los_clear});
    v["result"] = json!({"slot": result.slot, "damage_hp": result.damage_hp});
    v
}

/// DISP-01: the shot's deviation inside the aiming circle.
#[allow(clippy::too_many_arguments)]
pub fn shot(battle: u64, shot: u32, tick: u32, attacker: usize, attacker_kind: VehicleKind, shell: &Shell, angle: f64,
            gun: super::dispersion::Gun, seed: u64, r: f64, theta: f64) {
    write(shot_record(battle, shot, tick, attacker, attacker_kind, shell, angle, gun, seed, r, theta));
}
#[allow(clippy::too_many_arguments)]
fn shot_record(battle: u64, shot: u32, tick: u32, attacker: usize, attacker_kind: VehicleKind, shell: &Shell, angle: f64,
               gun: super::dispersion::Gun, seed: u64, r: f64, theta: f64) -> Value {
    let mut v = context("shot", battle, shot, tick, attacker, attacker, attacker_kind);
    v["shell"] = shell_json(shell);
    v["input"] = json!({"angle_rad": fb(angle), "radius_m": fb(gun.radius_m), "spg": gun.spg, "seed": format!("{seed:016x}")});
    v["result"] = json!({"r_rad": fb(r), "theta_rad": fb(theta)});
    v
}

/// SHELL-04: one module or crew seat on the internal trace or in an explosion: the #717 chance of
/// its group, the battle roll and whether it was hit (`roll < chance`); `damage` is the module
/// damage of an explosion hit (None on the internal trace: the shell's device damage).
#[allow(clippy::too_many_arguments)]
pub fn module(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, attacker_kind: VehicleKind, shell: &Shell,
              module: &str, class: ModuleClass, explosion: bool, chance: f64, roll: f64, applied: bool) {
    write(module_record(battle, shot, tick, attacker, target, attacker_kind, shell, module, class, explosion, chance, roll, applied));
}
#[allow(clippy::too_many_arguments)]
fn module_record(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, attacker_kind: VehicleKind, shell: &Shell,
                 module: &str, class: ModuleClass, explosion: bool, chance: f64, roll: f64, applied: bool) -> Value {
    let mut v = context("module", battle, shot, tick, attacker, target, attacker_kind);
    v["shell"] = shell_json(shell);
    v["input"] = json!({"module": module, "class": MODULE_CLASSES[class as usize], "explosion": explosion, "roll": fb(roll)});
    v["result"] = json!({"chance": fb(chance), "applied": applied});
    v
}

/// SHELL-PEN: one spaced layer crossed under the layered law.
#[allow(clippy::too_many_arguments)]
pub fn layer(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, attacker_kind: VehicleKind, shell: &Shell,
             distance_m: f64, spent_before_mm: f64, layer: &Layer, rolls: Rolls, pass: &LayerPass) {
    write(layer_record(battle, shot, tick, attacker, target, attacker_kind, shell, distance_m, spent_before_mm, layer, rolls, pass));
}
#[allow(clippy::too_many_arguments)]
fn layer_record(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, attacker_kind: VehicleKind, shell: &Shell,
                distance_m: f64, spent_before_mm: f64, layer: &Layer, rolls: Rolls, pass: &LayerPass) -> Value {
    let mut v = context("layer", battle, shot, tick, attacker, target, attacker_kind);
    v["shell"] = shell_json(shell);
    v["input"] = json!({"distance_m": fb(distance_m), "spent_before_mm": fb(spent_before_mm), "armor_mm": fb(layer.armor_mm),
        "use_hit_angle": layer.use_hit_angle, "may_ricochet": layer.may_ricochet, "chord": f3(layer.chord), "winding_normal": f3(layer.winding_normal)});
    v["rng"] = rolls_json(Some(rolls));
    v["result"] = layer_json(pass);
    v
}
fn layer_json(p: &LayerPass) -> Value {
    json!({"power_before_mm": fb(p.power_before_mm), "incidence_deg": fb(p.incidence_degrees), "normalization_deg": fb(p.normalization_degrees),
           "effective_armor_mm": fb(p.effective_armor_mm), "power_after_mm": fb(p.power_after_mm), "outcome": format!("{:?}", p.outcome)})
}

/// The shell of a vehicle kind's gun profile (the source the battle admitted).
pub fn shell_of(kind_label: &str, compact: u64) -> Option<Shell> {
    // Every closed kind (SUPPORTED, incl. WT E 100 / FV215b) and every generated kind.
    let kind = VehicleKind::SUPPORTED.into_iter().find(|k| k.label() == kind_label).or_else(|| VehicleKind::from_owned_label(kind_label))?;
    let compact = u16::try_from(compact).ok()?;
    crate::p06t_shells091::profile(kind.mount()).shots.iter().copied().find(|s| s.compact_descr == compact)
}

fn bits(v: &Value, width: usize) -> io::Result<u64> {
    v["bits"].as_str().filter(|s| s.len() == width).and_then(|s| u64::from_str_radix(s, 16).ok()).ok_or_else(|| bad("float bits"))
}
fn f64_of(v: &Value, key: &str) -> io::Result<f64> {
    Some(f64::from_bits(bits(&v[key], 16)?)).filter(|x| x.is_finite()).ok_or_else(|| bad(key))
}
fn f64_opt(v: &Value, key: &str) -> io::Result<Option<f64>> { if v[key].is_null() { Ok(None) } else { f64_of(v, key).map(Some) } }
fn vec3(v: &Value, key: &str) -> io::Result<[f32; 3]> {
    let a = v[key].as_array().filter(|a| a.len() == 3).ok_or_else(|| bad(key))?;
    let mut out = [0f32; 3];
    for (i, x) in a.iter().enumerate() {
        out[i] = Some(f32::from_bits(u32::try_from(bits(x, 8)?).map_err(|_| bad(key))?)).filter(|x| x.is_finite()).ok_or_else(|| bad(key))?;
    }
    Ok(out)
}

/// Recompute one record; `Ok(true)` when the law gives exactly the recorded result.
pub fn replay_record(record: &Value) -> io::Result<bool> {
    Ok(recompute(record)? == bits_only(&record["result"]))
}

/// The law result of a record's inputs, readable decimals dropped.
fn recompute(record: &Value) -> io::Result<Value> {
    let kind = record["attacker_kind"].as_str().ok_or_else(|| bad("attacker kind"))?;
    let shell = shell_of(kind, record["shell"]["compact"].as_u64().ok_or_else(|| bad("shell"))?).ok_or_else(|| bad("unknown kind/shell"))?;
    let input = &record["input"];
    let recomputed = match record["kind"].as_str() {
        Some("direct") => {
            let i = DirectInput { shell, plate: Plate { armor_mm: f64_opt(input, "armor_mm")?, ordinary: input["ordinary"].as_bool().ok_or_else(|| bad("ordinary"))? },
                chord: vec3(input, "chord")?, winding_normal: vec3(input, "winding_normal")?, distance_m: f64_of(input, "distance_m")? };
            let spent = f64_of(input, "spent_mm")?;
            let r = if input["unarmored_device"].as_bool() == Some(true) { law::resolve_unarmored_device(i)? }
                else if let Some(rolls) = rolls_of(record)? { law::resolve_layered(i, spent, rolls)? } else { law::resolve_direct_spent(i, spent)? };
            resolution_json(&r)
        }
        Some("track") => pass_json(&law::track_layered(shell, f64_of(input, "distance_m")?, f64_of(input, "spent_before_mm")?, f64_of(input, "armor_mm")?, rolls_of(record)?)?),
        Some("layer") => {
            let rolls = rolls_of(record)?.ok_or_else(|| bad("layer without rolls"))?;
            let l = Layer { armor_mm: f64_of(input, "armor_mm")?, use_hit_angle: input["use_hit_angle"].as_bool().ok_or_else(|| bad("use_hit_angle"))?,
                may_ricochet: input["may_ricochet"].as_bool().ok_or_else(|| bad("may_ricochet"))?, chord: vec3(input, "chord")?,
                winding_normal: vec3(input, "winding_normal")? };
            layer_json(&law::layer_pass(shell, f64_of(input, "distance_m")?, f64_of(input, "spent_before_mm")?, rolls, l)?)
        }
        Some("splash") => {
            if shell.family != Family::HighExplosive { return Err(bad("splash family")); }
            let t = SplashTarget { slot: u8::try_from(input["slot"].as_u64().ok_or_else(|| bad("slot"))?).map_err(|_| bad("slot"))?,
                distance_m: f64_of(input, "distance_m")?, armor_mm: f64_of(input, "armor_mm")?, los_clear: input["los_clear"].as_bool().ok_or_else(|| bad("los"))? };
            let d = match rolls_of(record)? { Some(rolls) => law::resolve_splash_layered(shell, &[t], rolls)?[0], None => law::resolve_splash(shell, &[t])?[0] };
            json!({"slot": d.slot, "damage_hp": d.damage_hp})
        }
        Some("shot") => {
            let seed = input["seed"].as_str().filter(|s| s.len() == 16).and_then(|s| u64::from_str_radix(s, 16).ok()).ok_or_else(|| bad("shot seed"))?;
            let gun = super::dispersion::Gun { radius_m: f64_of(input, "radius_m")?, after_shot: 1., spg: input["spg"].as_bool().ok_or_else(|| bad("spg"))? };
            let (r, theta) = super::dispersion::deviation(&crate::gateway091::shared::shell_rules::rules()?.accuracy, gun, f64_of(input, "angle_rad")?, seed);
            json!({"r_rad": fb(r), "theta_rad": fb(theta)})
        }
        Some("module") => {
            let name = input["class"].as_str().ok_or_else(|| bad("module class"))?;
            let index = MODULE_CLASSES.iter().position(|c| *c == name).ok_or_else(|| bad("module class"))?;
            let explosion = input["explosion"].as_bool().ok_or_else(|| bad("explosion"))?;
            let roll = f64_of(input, "roll")?;
            if !(0. ..1.).contains(&roll) { return Err(bad("module roll")); }
            let chance = crate::gateway091::shared::shell_rules::rules()?.module_chances[index][usize::from(explosion)];
            json!({"chance": fb(chance), "applied": roll < chance})
        }
        _ => return Err(bad("record kind")),
    };
    Ok(bits_only(&recomputed))
}

/// The readable decimal `v` of a float is dropped; its `bits` decide.
fn bits_only(value: &Value) -> Value {
    match value {
        Value::Object(map) => Value::Object(map.iter().filter(|(k, _)| k.as_str() != "v" || !map.contains_key("bits"))
            .map(|(k, v)| (k.clone(), bits_only(v))).collect()),
        Value::Array(items) => Value::Array(items.iter().map(bits_only).collect()),
        other => other.clone(),
    }
}

#[derive(Debug, Default, PartialEq)]
pub struct Report { pub records: u64, pub equal: u64, pub mismatched: u64, pub foreign_rules: u64, pub limit_marker: bool,
    /// The first mismatches: line, kind, recorded and recomputed result.
    pub examples: Vec<Value> }

pub fn replay(path: &Path) -> io::Result<Report> {
    let rules = crate::gateway091::shared::shell_rules::rules()?;
    let reader = BufReader::new(File::open(path)?);
    let mut report = Report::default();
    for (n, line) in reader.lines().enumerate() {
        if n >= MAX_REPLAY_LINES { return Err(bad("line count bound")); }
        let line = line?;
        if line.len() > MAX_LINE { return Err(bad("line bound")); }
        let record: Value = serde_json::from_str(&line).map_err(|_| bad("line JSON"))?;
        if record["schema"] != SCHEMA { return Err(bad("schema")); }
        if record["kind"] == "limit" { report.limit_marker = true; continue; }
        report.records += 1;
        if record["rules_hash"] != rules.rules_hash.as_str() { report.foreign_rules += 1; continue; }
        let recomputed = recompute(&record)?;
        if recomputed == bits_only(&record["result"]) { report.equal += 1 } else {
            report.mismatched += 1;
            if report.examples.len() < 5 {
                report.examples.push(json!({"line": n + 1, "kind": record["kind"], "input": record["input"],
                    "recorded": record["result"], "recomputed": recomputed}));
            }
        }
    }
    Ok(report)
}

/// CLI: print the report; an error status when any record differs or uses other rules.
pub fn replay_command(path: &str) -> io::Result<()> {
    let report = replay(Path::new(path))?;
    let rules = crate::gateway091::shared::shell_rules::rules()?;
    println!("{}", json!({"schema": "wot091-shot-replay.v1", "rules_hash": rules.rules_hash, "records": report.records, "equal": report.equal,
        "mismatched": report.mismatched, "foreign_rules": report.foreign_rules, "limit_marker": report.limit_marker,
        "examples": report.examples}));
    if report.mismatched != 0 || report.foreign_rules != 0 { return Err(bad("replay differs")); }
    Ok(())
}

#[cfg(test)]
#[path = "shot_trace_tests.rs"]
mod tests;
