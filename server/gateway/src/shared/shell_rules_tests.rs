//! SHELL-CFG: the embedded snapshot, its pin and the closed schema.
use super::*;
use serde_json::Value;

fn digest(raw: &[u8]) -> String { format!("{:x}", Sha256::digest(raw)) }
fn mutated(edit: impl Fn(&mut Value)) -> Vec<u8> {
    let mut doc: Value = serde_json::from_slice(SNAPSHOT).unwrap();
    edit(&mut doc);
    let mut raw = serde_json::to_vec(&doc).unwrap(); raw.push(b'\n'); raw
}

#[test] fn embedded_snapshot_matches_its_pin_and_the_law_code() {
    let r = rules().unwrap();
    assert_eq!((r.rules_hash.as_str(), r.config_version), (RULES_SHA256, CONFIG_VERSION));
    assert_eq!(r.direct_law, crate::p06t_damage::POLICY);
    assert_eq!(r.track_law, crate::p06t_damage::TRACK_PASS_POLICY);
    assert_eq!(r.unarmored_device_law, crate::p06t_damage::UNARMORED_DEVICE_POLICY);
}

#[test] fn snapshot_carries_exactly_the_former_lab_constants() {
    let r = rules().unwrap();
    let f = |family| r.family(family);
    assert_eq!(f(Family::ArmorPiercing), FamilyRules { normalization_deg: 5., ricochet_deg: Some(70.), caliber_rules: true, distance_falloff: true });
    assert_eq!(f(Family::ArmorPiercingCr), FamilyRules { normalization_deg: 2., ricochet_deg: Some(70.), caliber_rules: true, distance_falloff: true });
    assert_eq!(f(Family::HollowCharge), FamilyRules { normalization_deg: 0., ricochet_deg: Some(85.), caliber_rules: false, distance_falloff: false });
    assert_eq!(f(Family::HighExplosive), FamilyRules { normalization_deg: 0., ricochet_deg: None, caliber_rules: false, distance_falloff: false });
    assert_eq!((r.normalization_ratio, r.normalization_multiplier, r.no_ricochet_ratio), (2., 1.4, 3.));
    assert_eq!((r.full_power_until_m, r.linear_span_m, r.he_damage_factor, r.he_armor_factor), (100., 400., 0.5, 1.1));
}

#[test] fn foreign_bytes_and_schema_breaks_are_refused() {
    assert!(parse(SNAPSHOT, &"0".repeat(64)).is_err(), "pin");
    let cases: Vec<(&str, Vec<u8>)> = vec![
        ("unknown key", mutated(|d| { d["rules"]["caliber"]["extra"] = d["rules"]["caliber"]["no_ricochet_ratio"].clone(); })),
        ("missing key", mutated(|d| { d["rules"]["falloff"].as_object_mut().unwrap().remove("linear_span_m"); })),
        ("bad status", mutated(|d| { d["rules"]["caliber"]["normalization_ratio"]["status"] = "historical".into(); })),
        ("out of bound", mutated(|d| { d["rules"]["families"]["armor_piercing"]["ricochet_deg"]["value"] = 120.0.into(); })),
        ("wrong type", mutated(|d| { d["rules"]["families"]["hollow_charge"]["caliber_rules"]["value"] = 1.into(); })),
        ("foreign law", mutated(|d| { d["rules"]["laws"]["direct"]["value"] = "test_lab.other-law.v9".into(); })),
        ("profile", mutated(|d| { d["profile"] = "historical".into(); })),
        ("null where not allowed", mutated(|d| { d["rules"]["families"]["armor_piercing"]["normalization_deg"]["value"] = Value::Null; })),
    ];
    for (label, raw) in cases { assert!(parse(&raw, &digest(&raw)).is_err(), "{label}"); }
    let same = mutated(|_| {});
    assert_eq!(parse(&same, &digest(&same)).unwrap().families, rules().unwrap().families);
}
