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

#[test] fn version_two_adds_the_layered_law_settings() {
    let r = rules().unwrap();
    assert!(r.config_version >= 2);
    assert_eq!((r.penetration_random_percent, r.damage_random_percent, r.heat_stops_on_spaced, r.caliber_integer), (25., 25., true, true));
    let bad = mutated(|d| { d["rules"]["layers"]["heat_on_spaced"]["value"] = "explode-later".into(); });
    assert!(parse(&bad, &digest(&bad)).is_err());
    let bad = mutated(|d| { d["rules"]["randomization"]["distribution"]["value"] = "normal".into(); });
    assert!(parse(&bad, &digest(&bad)).is_err());
}

#[test] fn version_three_adds_the_he_screen_splash_and_hesh_settings() {
    let r = rules().unwrap();
    assert!(r.config_version >= 3);
    assert_eq!(r.he_law, crate::p06t_damage::HE_POLICY);
    assert!(r.he_screen_formula);
    assert_eq!((r.he_screen, r.hesh_screen), (Screen { resistance: 1., loss: 0.25 }, Screen { resistance: 1., loss: 0.75 }));
    assert_eq!((r.he_falloff_exponent, r.hesh_splash_factor), (1., 0.5));
    for (label, bad) in [
        ("loss above one", mutated(|d| { d["rules"]["high_explosive"]["screen_loss"]["value"] = 1.5.into(); })),
        ("unknown splash ray", mutated(|d| { d["rules"]["high_explosive"]["splash_ray"]["value"] = "all_surfaces".into(); })),
        ("unknown HE screen rule", mutated(|d| { d["rules"]["layers"]["he_on_spaced"]["value"] = "pass".into(); })),
        ("foreign HE law", mutated(|d| { d["rules"]["laws"]["he"]["value"] = "project.he-other.v9".into(); })),
    ] { assert!(parse(&bad, &digest(&bad)).is_err(), "{label}"); }
    let stop = mutated(|d| { d["rules"]["layers"]["he_on_spaced"]["value"] = "stop".into(); });
    assert!(!parse(&stop, &digest(&stop)).unwrap().he_screen_formula);
}

#[test] fn shot_rolls_are_bounded_reproducible_from_the_seed_and_vary_per_shot() {
    let r = rules().unwrap();
    let mut seen = std::collections::BTreeSet::new();
    let (mut low, mut high) = (f64::MAX, f64::MIN);
    for shot in 0..20_000u32 {
        let roll = shot_rolls(r, 777, shot);
        assert!((0.75..1.25).contains(&roll.penetration) && (0.75..1.25).contains(&roll.damage), "{roll:?}");
        assert_eq!(rolls_from_seed(r, roll.seed), roll);
        assert_eq!(shot_rolls(r, 777, shot), roll, "same process, same battle and shot");
        seen.insert(roll.seed);
        low = low.min(roll.penetration); high = high.max(roll.penetration);
    }
    assert_eq!(seen.len(), 20_000);
    assert!(low < 0.76 && high > 1.24, "{low} {high}");
    assert_ne!(shot_rolls(r, 778, 1).seed, shot_rolls(r, 777, 1).seed);
    let mut flat = r.clone(); flat.penetration_random_percent = 0.; flat.damage_random_percent = 0.;
    assert_eq!(rolls_from_seed(&flat, 99).penetration, 1.);
}

#[test] fn version_four_carries_the_verified_module_chances_and_ten_calibers() {
    let r = rules().unwrap();
    assert_eq!((r.modules_law.as_str(), r.internal_trace_calibers), (MODULES_POLICY, 10.));
    assert!(r.config_version >= 4);
    assert_eq!((r.module_chance(ModuleClass::Engine, false), r.module_chance(ModuleClass::AmmoBay, false)), (0.45, 0.27));
    assert_eq!((r.module_chance(ModuleClass::Crew, false), r.module_chance(ModuleClass::Crew, true)), (0.33, 0.15));
    assert_eq!((r.module_chance(ModuleClass::Track, true), r.module_chance(ModuleClass::Gun, true)), (1., 0.33));
    for (label, bad) in [
        ("chance above one", mutated(|d| { d["rules"]["modules"]["engine_projectile"]["value"] = 1.5.into(); })),
        ("missing chance", mutated(|d| { d["rules"]["modules"].as_object_mut().unwrap().remove("crew_explosion"); })),
        ("unknown gate", mutated(|d| { d["rules"]["modules"]["chance_gate"]["value"] = "always".into(); })),
    ] { assert!(parse(&bad, &digest(&bad)).is_err(), "{label}"); }
}
