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
use crate::p06t_damage::{self as law, DirectInput, Plate, Resolution, SplashDamage, SplashTarget, TrackPass};
use crate::p06t_shells091::{Family, Shell, PROFILES};

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
fn context(kind: &str, battle: u64, shot: u32, tick: u32, attacker: usize, target: usize) -> Value {
    json!({"kind": kind, "battle_id": battle, "shot_id": shot, "server_tick": tick, "attacker": attacker, "target": target,
           "accuracy": Value::Null, "rng": Value::Null})
}

#[allow(clippy::too_many_arguments)]
pub fn direct(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, input: &DirectInput, spent_mm: f64,
              unarmored_device: bool, result: &Resolution) {
    write(direct_record(battle, shot, tick, attacker, target, input, spent_mm, unarmored_device, result));
}
#[allow(clippy::too_many_arguments)]
fn direct_record(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, input: &DirectInput, spent_mm: f64,
                 unarmored_device: bool, result: &Resolution) -> Value {
    let mut v = context("direct", battle, shot, tick, attacker, target);
    v["shell"] = shell_json(&input.shell);
    v["input"] = json!({"armor_mm": fbo(input.plate.armor_mm), "ordinary": input.plate.ordinary, "chord": f3(input.chord),
                        "winding_normal": f3(input.winding_normal), "distance_m": fb(input.distance_m), "spent_mm": fb(spent_mm),
                        "unarmored_device": unarmored_device});
    v["result"] = resolution_json(result);
    v
}
#[allow(clippy::too_many_arguments)]
pub fn track(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, shell: &Shell, distance_m: f64,
             spent_before_mm: f64, armor_mm: f64, pass: &TrackPass) {
    write(track_record(battle, shot, tick, attacker, target, shell, distance_m, spent_before_mm, armor_mm, pass));
}
#[allow(clippy::too_many_arguments)]
fn track_record(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, shell: &Shell, distance_m: f64,
                spent_before_mm: f64, armor_mm: f64, pass: &TrackPass) -> Value {
    let mut v = context("track", battle, shot, tick, attacker, target);
    v["shell"] = shell_json(shell);
    v["input"] = json!({"distance_m": fb(distance_m), "spent_before_mm": fb(spent_before_mm), "armor_mm": fb(armor_mm)});
    v["result"] = pass_json(pass);
    v
}
#[allow(clippy::too_many_arguments)]
pub fn splash(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, shell: &Shell, input: &SplashTarget, result: &SplashDamage) {
    write(splash_record(battle, shot, tick, attacker, target, shell, input, result));
}
#[allow(clippy::too_many_arguments)]
fn splash_record(battle: u64, shot: u32, tick: u32, attacker: usize, target: usize, shell: &Shell, input: &SplashTarget, result: &SplashDamage) -> Value {
    let mut v = context("splash", battle, shot, tick, attacker, target);
    v["shell"] = shell_json(shell);
    v["input"] = json!({"slot": input.slot, "distance_m": fb(input.distance_m), "armor_mm": fb(input.armor_mm), "los_clear": input.los_clear});
    v["result"] = json!({"slot": result.slot, "damage_hp": result.damage_hp});
    v
}

/// Every shell the law can meet: curated mounts and the verified generated registry.
pub fn shell_by_compact(compact: u64) -> Option<Shell> {
    let compact = u16::try_from(compact).ok()?;
    PROFILES.iter().flat_map(|p| p.shots).find(|s| s.compact_descr == compact).or_else(|| {
        crate::gateway091::shared::generated_vehicles::registry().ok()?.entries().iter().flat_map(|e| e.gun.shots).find(|s| s.compact_descr == compact)
    })
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
    let shell = shell_by_compact(record["shell"]["compact"].as_u64().ok_or_else(|| bad("shell"))?).ok_or_else(|| bad("unknown shell"))?;
    let input = &record["input"];
    let recomputed = match record["kind"].as_str() {
        Some("direct") => {
            let i = DirectInput { shell, plate: Plate { armor_mm: f64_opt(input, "armor_mm")?, ordinary: input["ordinary"].as_bool().ok_or_else(|| bad("ordinary"))? },
                chord: vec3(input, "chord")?, winding_normal: vec3(input, "winding_normal")?, distance_m: f64_of(input, "distance_m")? };
            let r = if input["unarmored_device"].as_bool() == Some(true) { law::resolve_unarmored_device(i)? } else { law::resolve_direct_spent(i, f64_of(input, "spent_mm")?)? };
            resolution_json(&r)
        }
        Some("track") => pass_json(&law::track_pass(shell, f64_of(input, "distance_m")?, f64_of(input, "spent_before_mm")?, f64_of(input, "armor_mm")?)?),
        Some("splash") => {
            if shell.family != Family::HighExplosive { return Err(bad("splash family")); }
            let t = SplashTarget { slot: u8::try_from(input["slot"].as_u64().ok_or_else(|| bad("slot"))?).map_err(|_| bad("slot"))?,
                distance_m: f64_of(input, "distance_m")?, armor_mm: f64_of(input, "armor_mm")?, los_clear: input["los_clear"].as_bool().ok_or_else(|| bad("los"))? };
            let d = law::resolve_splash(shell, &[t])?[0];
            json!({"slot": d.slot, "damage_hp": d.damage_hp})
        }
        _ => return Err(bad("record kind")),
    };
    Ok(bits_only(&recomputed) == bits_only(&record["result"]))
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
pub struct Report { pub records: u64, pub equal: u64, pub mismatched: u64, pub foreign_rules: u64, pub limit_marker: bool }

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
        if replay_record(&record)? { report.equal += 1 } else { report.mismatched += 1 }
    }
    Ok(report)
}

/// CLI: print the report; an error status when any record differs or uses other rules.
pub fn replay_command(path: &str) -> io::Result<()> {
    let report = replay(Path::new(path))?;
    let rules = crate::gateway091::shared::shell_rules::rules()?;
    println!("{}", json!({"schema": "wot091-shot-replay.v1", "rules_hash": rules.rules_hash, "records": report.records, "equal": report.equal,
        "mismatched": report.mismatched, "foreign_rules": report.foreign_rules, "limit_marker": report.limit_marker}));
    if report.mismatched != 0 || report.foreign_rules != 0 { return Err(bad("replay differs")); }
    Ok(())
}

#[cfg(test)]
#[path = "shot_trace_tests.rs"]
mod tests;
