//! SHELL-PEN: the layered law (spaced layers, tracks, rolled plate) on chosen cases.
use super::*;
use crate::gateway091::shared::shell_rules::{rolls_from_seed, rules as profile, Rolls};
use crate::p06t_shells091::Mount;

fn shot(mount: Mount, family: Family) -> Shell { *crate::p06t_shells091::profile(mount).shots.iter().find(|s| s.family == family).unwrap() }
const NEUTRAL: Rolls = Rolls { seed: 0, penetration: 1.0, damage: 1.0 };
fn plate(shell: Shell, armor: f64, angle: f32, distance: f64) -> DirectInput {
    let a = angle.to_radians();
    DirectInput { shell, plate: Plate { armor_mm: Some(armor), ordinary: true }, chord: [a.sin(), 0., -a.cos()], winding_normal: [0., 0., 1.], distance_m: distance }
}
fn layer(armor: f64, angle: f32, use_hit_angle: bool, may_ricochet: bool) -> Layer {
    let a = angle.to_radians();
    Layer { armor_mm: armor, use_hit_angle, may_ricochet, chord: [a.sin(), 0., -a.cos()], winding_normal: [0., 0., 1.] }
}

#[test] fn neutral_rolls_give_the_single_plate_law_for_integer_calibers() {
    for mount in [Mount::Is7Stock, Mount::T34Stock, Mount::WtE100128] {
        for shell in crate::p06t_shells091::profile(mount).shots {
            assert_eq!(shell.caliber_mm.fract(), 0.);
            for armor in [20., 60., 120., 250.] { for angle in [0f32, 40., 69., 72., 86.] { for distance in [10., 300., 600.] {
                let i = plate(shell, armor, angle, distance);
                let old = resolve_direct_spent(i, 0.).unwrap();
                let new = resolve_layered(i, 0., NEUTRAL).unwrap();
                assert_eq!(new.policy, LAYERS_POLICY);
                assert_eq!(Resolution { policy: POLICY, ..new }, old, "{} {armor} {angle} {distance}", shell.resource);
            } } }
        }
    }
}

#[test] fn rolls_scale_power_and_damage_and_stay_inside_25_percent() {
    let ap = shot(Mount::Is7Stock, Family::ArmorPiercing);
    let low = Rolls { seed: 1, penetration: 0.75, damage: 0.75 };
    let high = Rolls { seed: 2, penetration: 1.25, damage: 1.25 };
    let base = penetration(profile().unwrap(), ap, 50.);
    assert_eq!(resolve_layered(plate(ap, 10., 0., 50.), 0., low).unwrap().nominal_power_mm, base * 0.75);
    assert_eq!(resolve_layered(plate(ap, 10., 0., 50.), 0., high).unwrap().damage_hp, (f64::from(ap.damage_hp) * 1.25).round() as u16);
    // A plate between the low and high rolled power: the roll decides.
    let armor = base;
    assert_eq!(resolve_layered(plate(ap, armor, 0., 50.), 0., low).unwrap().decision, Decision::NotPierced);
    assert_eq!(resolve_layered(plate(ap, armor, 0., 50.), 0., high).unwrap().decision, Decision::Pierced);
    for seed in 0..5000u64 {
        let r = rolls_from_seed(profile().unwrap(), seed);
        let d = resolve_layered(plate(ap, 10., 0., 50.), 0., r).unwrap().damage_hp;
        assert!(f64::from(d) >= (f64::from(ap.damage_hp) * 0.75).round() && f64::from(d) <= (f64::from(ap.damage_hp) * 1.25).round(), "{d}");
    }
    assert!(resolve_layered(plate(ap, 10., 0., 50.), 0., Rolls { seed: 3, penetration: 2.0, damage: 1.0 }).is_err());
}

#[test] fn engine_integer_caliber_moves_the_fv215b_two_caliber_edge() {
    let ap = shot(Mount::Fv215b183, Family::ArmorPiercing);
    assert_eq!(ap.caliber_mm, 182.9);
    // 182.9 >= 2 x 91.2 but 182 < 2 x 91.2: normalization grows only with the old caliber.
    let old = resolve_direct_spent(plate(ap, 91.2, 30., 50.), 0.).unwrap();
    let new = resolve_layered(plate(ap, 91.2, 30., 50.), 0., NEUTRAL).unwrap();
    assert!(old.normalization_degrees > 5. && new.normalization_degrees == 5., "{} {}", old.normalization_degrees, new.normalization_degrees);
}

#[test] fn heat_stops_on_a_spaced_layer_or_track() {
    for (mount, family) in [(Mount::Ms1Stock, Family::HollowCharge)] {
        let shell = shot(mount, family);
        for l in [layer(20., 0., false, false), layer(8., 45., true, true)] {
            let pass = layer_pass(shell, 100., 0., NEUTRAL, l).unwrap();
            assert_eq!((pass.outcome, pass.power_after_mm), (PassOutcome::Stopped, 0.), "{family:?}");
        }
    }
}

#[test] fn ap_takes_the_nominal_track_armour_and_the_effective_screen_armour() {
    let ap = shot(Mount::Is7Stock, Family::ArmorPiercing);
    let rules = profile().unwrap();
    let power = penetration(rules, ap, 100.);
    // Track MaterialInfo: no hit angle, no ricochet -> the old track pass arithmetic.
    let track = layer_pass(ap, 100., 0., NEUTRAL, layer(20., 80., false, false)).unwrap();
    assert_eq!((track.outcome, track.effective_armor_mm, track.power_after_mm), (PassOutcome::Passed, 20., power - 20.));
    let old = track_pass(ap, 100., 0., 20.).unwrap();
    assert_eq!(old.power_after_mm, track.power_after_mm);
    // Screen at 60 deg: 5 deg normalization (no 2x overmatch for 130 mm on 80 mm).
    let screen = layer_pass(ap, 100., 0., NEUTRAL, layer(80., 60., true, true)).unwrap();
    assert_eq!(screen.normalization_degrees, 5.);
    assert!((screen.effective_armor_mm - 80. / 55f64.to_radians().cos()).abs() < 1e-4, "{}", screen.effective_armor_mm);
    assert_eq!(screen.power_after_mm, power - screen.effective_armor_mm);
    // Ricochet only where the material may ricochet, and not over three calibers.
    assert_eq!(layer_pass(ap, 100., 0., NEUTRAL, layer(80., 75., true, true)).unwrap().outcome, PassOutcome::Ricochet);
    assert_eq!(layer_pass(ap, 100., 0., NEUTRAL, layer(80., 75., true, false)).unwrap().outcome, PassOutcome::Passed);
    assert_ne!(layer_pass(ap, 100., 0., NEUTRAL, layer(40., 75., true, true)).unwrap().outcome, PassOutcome::Ricochet);
    // Power used up on the layer.
    let absorbed = layer_pass(ap, 100., power - 5., NEUTRAL, layer(20., 0., false, false)).unwrap();
    assert_eq!((absorbed.outcome, absorbed.power_after_mm), (PassOutcome::Absorbed, 0.));
}

// SHELL-03 (owner 2026-11-08): HE/HESH by layers.
fn fv(resource: &str) -> Shell { *crate::p06t_shells091::profile(Mount::Fv215b183).shots.iter().find(|s| s.resource == resource).unwrap() }

#[test] fn hesh_is_a_server_table_matching_every_source_hesh_shell() {
    let (hesh_shell, he) = (fv("_183mm_HESH"), fv("_183mm_HE_Mk1"));
    assert!(hesh(hesh_shell) && !hesh(he));
    assert_eq!((hesh_shell.family, hesh_shell.penetration_mm, hesh_shell.damage_hp), (Family::HighExplosive, [275., 275.], 1750), "client kind stays HE");
    // No other shell of any battle or generated gun is HESH, by id or by source name.
    let registry = crate::gateway091::shared::generated_vehicles::registry().unwrap();
    let all = PROFILES.iter().flat_map(|p| p.shots.iter().copied()).chain(registry.entries().iter().flat_map(|e| e.gun.shots.iter().copied()));
    let mut found = std::collections::BTreeSet::new();
    for s in all { assert_eq!(hesh(s), s.resource.contains("HESH"), "{}", s.resource); if hesh(s) { assert_eq!(s.family, Family::HighExplosive); found.insert(s.compact_descr); } }
    assert_eq!(found.into_iter().collect::<Vec<_>>(), HESH_SHELLS.to_vec(), "every table entry is a real shell");
}

#[test] fn he_and_hesh_pass_a_screen_by_resistance_and_loss_or_detonate() {
    let rules = profile().unwrap();
    let (he, hesh_shell) = (fv("_183mm_HE_Mk1"), fv("_183mm_HESH"));
    // 10 mm screen at 0 deg: (92 - 10) * 0.75 and (275 - 10) * 0.25.
    let p = layer_pass(he, 100., 0., NEUTRAL, layer(10., 0., true, true)).unwrap();
    assert_eq!((p.outcome, p.power_after_mm), (PassOutcome::Passed, (92. - 10. * rules.he_screen.resistance) * (1. - rules.he_screen.loss)));
    let p = layer_pass(hesh_shell, 100., 0., NEUTRAL, layer(10., 0., true, true)).unwrap();
    assert_eq!((p.outcome, p.power_after_mm), (PassOutcome::Passed, (275. - 10.) * 0.25));
    // The angle thickens a screen; no ricochet and no normalization for HE.
    let p = layer_pass(he, 100., 0., NEUTRAL, layer(10., 60., true, true)).unwrap();
    assert_eq!((p.normalization_degrees, p.outcome), (0., PassOutcome::Passed));
    assert!((p.effective_armor_mm - 20.).abs() < 1e-4);
    // Thicker than the power: detonation on the layer (Stopped, the splash anchor).
    for l in [layer(100., 0., true, true), layer(92., 0., false, false)] {
        assert_eq!(layer_pass(he, 100., 0., NEUTRAL, l).unwrap().outcome, PassOutcome::Stopped);
    }
    // The penetration roll scales the power before the screen.
    let low = Rolls { seed: 1, penetration: 0.75, damage: 1. };
    let p = layer_pass(he, 100., 0., low, layer(10., 0., false, false)).unwrap();
    assert_eq!(p.power_after_mm, (92. * 0.75 - 10.) * 0.75);
    // A track (no hit angle) by the same law; without rolls the SHELL-02 track pass still stops HE.
    let t = track_layered(he, 100., 0., 20., Some(NEUTRAL)).unwrap();
    assert_eq!((t.stopped, t.power_after_mm), (false, (92. - 20.) * 0.75));
    assert!(track_layered(he, 100., 0., 20., None).unwrap().stopped);
}

#[test] fn he_behind_a_screen_meets_the_main_plate_with_its_remaining_power() {
    let he = fv("_183mm_HE_Mk1");
    let after = (92. - 10.) * 0.75;
    let spent = 92. - after;
    let pierced = resolve_layered(plate(he, 40., 0., 100.), spent, NEUTRAL).unwrap();
    assert_eq!((pierced.decision, pierced.damage_hp), (Decision::Pierced, 1750));
    assert_eq!(pierced.nominal_power_mm, 92. - spent);
    let held = resolve_layered(plate(he, 80., 0., 100.), spent, NEUTRAL).unwrap();
    assert_eq!((held.decision, held.damage_hp), (Decision::NotPierced, (0.5f64 * 1750. - 1.1 * 80.).floor() as u16));
    // The damage roll scales D in the non-penetration formula; HESH direct is HE.
    let low = Rolls { seed: 1, penetration: 1., damage: 0.8 };
    assert_eq!(resolve_layered(plate(he, 80., 0., 100.), spent, low).unwrap().damage_hp, (0.5f64 * 1750. * 0.8 - 1.1 * 80.).floor() as u16);
    assert_eq!(resolve_layered(plate(fv("_183mm_HESH"), 300., 0., 100.), 0., low).unwrap().damage_hp, (0.5f64 * 1750. * 0.8 - 1.1 * 300.).floor() as u16);
    // The single-plate law still refuses HE behind a track.
    assert!(resolve_direct_spent(plate(he, 40., 0., 100.), spent).is_err());
}

#[test] fn layered_splash_falls_off_takes_the_roll_and_halves_hesh() {
    let (he, hesh_shell) = (fv("_183mm_HE_Mk1"), fv("_183mm_HESH"));
    let target = |distance_m: f64, armor_mm: f64| SplashTarget { slot: 3, distance_m, armor_mm, los_clear: true };
    let dmg = |shell, t, r| resolve_splash_layered(shell, &[t], r).unwrap()[0].damage_hp;
    let expected = |k: f64, d: f64, armor: f64, roll: f64| (0.5 * 1750. * roll * k * (1. - d / 5.05) - 1.1 * armor).max(0.).floor() as u16;
    for (d, armor) in [(0., 30.), (1.2, 50.), (3.3, 20.), (5.05, 0.), (6., 0.)] {
        assert_eq!(dmg(he, target(d, armor), NEUTRAL), expected(1., d, armor, 1.), "{d} {armor}");
        assert_eq!(dmg(hesh_shell, target(d, armor), NEUTRAL), expected(0.5, d, armor, 1.), "{d} {armor}");
    }
    let high = Rolls { seed: 7, penetration: 1., damage: 1.2 };
    assert_eq!(dmg(he, target(1., 40.), high), expected(1., 1., 40., 1.2));
    // Neutral rolls and no layers: the LAB splash.
    assert_eq!(resolve_splash_layered(he, &[target(1., 40.)], NEUTRAL).unwrap(), resolve_splash(he, &[target(1., 40.)]).unwrap());
    let hidden = SplashTarget { los_clear: false, ..target(1., 0.) };
    assert_eq!(dmg(he, hidden, high), 0);
    assert!(resolve_splash_layered(he, &[target(1., 0.)], Rolls { seed: 0, penetration: 1., damage: 2. }).is_err(), "roll bound");
}
