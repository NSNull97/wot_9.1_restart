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

#[test] fn he_and_heat_stop_on_a_spaced_layer_or_track() {
    for (mount, family) in [(Mount::Is7Stock, Family::HighExplosive), (Mount::Ms1Stock, Family::HollowCharge)] {
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
