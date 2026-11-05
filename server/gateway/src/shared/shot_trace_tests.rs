//! SHELL-CFG: a traced decision replays to exactly the same result; a changed one does not.
use super::*;

fn stamp(mut v: Value) -> Value {
    let rules = crate::gateway091::shared::shell_rules::rules().unwrap();
    v["schema"] = SCHEMA.into();
    v["rules_hash"] = rules.rules_hash.clone().into();
    v["config_version"] = rules.config_version.into();
    v
}
fn shell(family: Family) -> Shell { *PROFILES.iter().flat_map(|p| p.shots.iter()).find(|s| s.family == family).unwrap() }

fn direct_case(armor: Option<f64>, angle: f32, distance: f64, spent: f64) -> Value {
    let a = angle.to_radians();
    let input = DirectInput { shell: shell(Family::ArmorPiercing), plate: Plate { armor_mm: armor, ordinary: true },
        chord: [a.sin(), 0.11, -a.cos()], winding_normal: [0.013, 0., 1.], distance_m: distance };
    let result = law::resolve_direct_spent(input, spent).unwrap();
    stamp(direct_record(7, 3, 120, 0, 4, &input, spent, false, &result))
}

#[test] fn direct_track_and_splash_records_replay_exactly() {
    for armor in [None, Some(0.), Some(17.3), Some(48.), Some(130.)] {
        for angle in [0., 33.3, 69.99, 71., 88.] {
            for distance in [0.1, 123.456, 500., 719.] {
                for spent in [0., 12.5] {
                    let record = direct_case(armor, angle, distance, spent);
                    let text = serde_json::to_string(&record).unwrap();
                    assert!(replay_record(&serde_json::from_str(&text).unwrap()).unwrap(), "{text}");
                }
            }
        }
    }
    let ap = shell(Family::ArmorPiercing);
    let pass = law::track_pass(ap, 333.3, 0., 20.).unwrap();
    let track = stamp(track_record(7, 4, 121, 0, 4, &ap, 333.3, 0., 20., &pass));
    assert!(replay_record(&serde_json::from_str(&track.to_string()).unwrap()).unwrap());
    let he = shell(Family::HighExplosive);
    let target = SplashTarget { slot: 12, distance_m: 0.37, armor_mm: 25., los_clear: true };
    let damage = law::resolve_splash(he, &[target]).unwrap()[0];
    let splash = stamp(splash_record(7, 5, 122, 0, 12, &he, &target, &damage));
    assert!(replay_record(&serde_json::from_str(&splash.to_string()).unwrap()).unwrap());
}

#[test] fn a_changed_result_or_input_is_reported() {
    let mut record = direct_case(Some(48.), 20., 200., 0.);
    record["result"]["damage_hp"] = 1.into();
    assert!(!replay_record(&record).unwrap());
    let mut record = direct_case(Some(48.), 20., 200., 0.);
    let bits = record["result"]["nominal_power_mm"]["bits"].as_str().unwrap().to_owned();
    let flipped = format!("{:016x}", u64::from_str_radix(&bits, 16).unwrap() ^ 1);
    record["result"]["nominal_power_mm"]["bits"] = flipped.into();
    assert!(!replay_record(&record).unwrap(), "one bit");
    let mut record = direct_case(Some(48.), 20., 200., 0.);
    record["result"]["nominal_power_mm"]["v"] = 1.0e9.into();
    assert!(replay_record(&record).unwrap(), "the readable value never decides");
    let mut record = direct_case(Some(48.), 20., 200., 0.);
    record["input"]["distance_m"]["bits"] = "zz".into();
    assert!(replay_record(&record).is_err());
    let mut record = direct_case(Some(48.), 20., 200., 0.);
    record["shell"]["compact"] = 1.into();
    assert!(replay_record(&record).is_err(), "unknown shell");
}

#[test] fn file_replay_counts_and_refuses_foreign_rules() {
    let dir = std::env::temp_dir().join(format!("wot091-shot-trace-test-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("t.jsonl");
    let mut foreign = direct_case(Some(30.), 10., 50., 0.);
    foreign["rules_hash"] = "0".repeat(64).into();
    let limit = json!({"schema": SCHEMA, "kind": "limit", "bytes": 1, "line_bytes": 9000});
    let lines = [direct_case(Some(30.), 10., 50., 0.), direct_case(None, 0., 10., 0.), foreign, limit];
    std::fs::write(&path, lines.iter().map(|v| v.to_string() + "\n").collect::<String>()).unwrap();
    let report = replay(&path).unwrap();
    assert_eq!(report, Report { records: 3, equal: 2, mismatched: 0, foreign_rules: 1, limit_marker: true });
    assert!(replay_command(path.to_str().unwrap()).is_err(), "foreign rules fail the command");
    std::fs::write(&path, "{\"schema\":\"other\"}\n").unwrap();
    assert!(replay(&path).is_err());
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test] fn every_traced_shell_is_found_by_compact_id() {
    for p in PROFILES.iter() { for s in p.shots { assert_eq!(shell_by_compact(u64::from(s.compact_descr)), Some(s)); } }
    let registry = crate::gateway091::shared::generated_vehicles::registry().unwrap();
    for e in registry.entries() { for s in e.gun.shots { assert_eq!(shell_by_compact(u64::from(s.compact_descr)).map(|x| x.compact_descr), Some(s.compact_descr)); } }
    assert_eq!(shell_by_compact(70_000), None);
}
