//! DISP-01: the client's circle, Dual Dispersion statistics and the shot deviation.
use super::*;
use crate::gateway091::shared::shell_rules::{rules, MODULE_CLASSES};
use crate::gateway091::shared::vehicle_profile::VehicleKind;

fn accuracy() -> Accuracy { rules().unwrap().accuracy }
fn spec() -> AimSpec { VehicleKind::T3485.aim() }
const GUN: Gun = Gun { radius_m: 0.35, after_shot: 4., spg: false };
const STILL: Motion = Motion { speed: 0., hull_rate: 0., turret_rate: 0. };
const NORMAL: Factors = Factors { multiplier: 1., additive: 1. };

#[test] fn the_table_has_every_battle_gun_and_the_curated_guns_are_their_mounts() {
    let registry = crate::gateway091::shared::generated_vehicles::registry().unwrap();
    // CONTENT-0 4: a stock entry has its vehicle's row, a build its own turret x gun pair's row; the build of the stock
    // pair carries the stock row's numbers.
    for e in registry.entries() {
        let kind = VehicleKind::from_owned_label(e.label.as_str()).unwrap();
        let own = gun(kind.dispersion_name()).unwrap();
        assert_eq!(e.stock, kind.dispersion_name() == kind.name(), "{}", e.label);
        if let Some(stock) = registry.by_vehicle(&e.vehicle_id).map(|id| VehicleKind::Generated(id)) {
            if crate::gateway091::shared::generated_vehicles::entry(stock.generated().unwrap().id).gun_compact_id == e.gun_compact_id
                && registry.entries()[stock.generated().unwrap().id.get()].parts[1] == e.parts[1] {
                assert_eq!(own, gun(stock.name()).unwrap(), "{}", e.label);
            }
        }
    }
    assert_eq!(pair_key("ussr:KV-3", "res/scripts/item_defs/vehicles/ussr/kv-3.xml:/turrets0[1]/KV-220_mod[1]/guns[1]/_107mm_ZiS-6[1]").as_deref(),
               Some("ussr:KV-3@KV-220_mod/_107mm_ZiS-6"));
    assert_eq!(pair_key("x", "a.xml:/turrets0[1]/T[1]/guns[1]/G[2]"), None);
    for kind in VehicleKind::SUPPORTED { gun(kind.name()).unwrap(); }
    assert!(gun("ussr:no-such").is_err());
    let doc: Value = serde_json::from_slice(TABLE).unwrap();
    for kind in VehicleKind::SUPPORTED {
        assert_eq!(doc["guns"][kind.name()]["compact"].as_u64(), Some(u64::from(crate::p06t_shells091::profile(kind.mount()).gun_compact_descr)), "{}", kind.name());
    }
    let _ = MODULE_CLASSES;
}

#[test] fn the_ideal_factor_is_the_client_formula() {
    let s = spec();
    assert_eq!(ideal(&s, STILL, 0., NORMAL), 1.);
    let m = Motion { speed: 2., hull_rate: 0.5, turret_rate: 0.25 };
    let expected = (1f64 + (2. * f64::from(s.movement_dispersion)).powi(2) + (0.5 * f64::from(s.hull_dispersion)).powi(2)
        + (0.25 * f64::from(s.turret_dispersion)).powi(2) + 16.).sqrt() * 2.;
    assert!((ideal(&s, m, 4., Factors { multiplier: 2., ..NORMAL }) - expected).abs() < 1e-9);
}

#[test] fn content0_s5_stabilizer_scales_all_additive_penalties_before_the_square_root() {
    let s = spec();
    let factors = Factors { multiplier: 2., additive: 0.8 };
    assert_eq!(ideal(&s, STILL, 0., factors), 2.);
    let motion = Motion { speed: 3., hull_rate: 0.5, turret_rate: 0.25 };
    let penalties = (3. * f64::from(s.movement_dispersion)).powi(2) + (0.5 * f64::from(s.hull_dispersion)).powi(2)
        + (0.25 * f64::from(s.turret_dispersion)).powi(2) + 16.;
    assert!((ideal(&s, motion, 4., factors) - 2. * (1. + 0.64 * penalties).sqrt()).abs() < 1e-12);
}

#[test] fn the_circle_decays_with_the_aiming_time_and_blooms_after_a_shot() {
    let s = spec();
    let mut state = State::new(0., 0.);
    state.after_shot(&s, GUN, 0., NORMAL);
    let bloom = (1f64 + 16.).sqrt();
    assert!((state.factor - bloom).abs() < 1e-9);
    state.step(&s, 0., 0., 0., NORMAL, 0.1).unwrap();
    assert!((state.factor - bloom * (-f64::from(0.1f32) / f64::from(s.aiming_time)).exp()).abs() < 1e-9);
    for _ in 0..2000 { state.step(&s, 0., 0., 0., NORMAL, 0.1).unwrap(); }
    assert_eq!(state.factor, 1., "settles at the ideal");
    assert!((state.angle(GUN) - (0.0035f64).atan()).abs() < 1e-12);
    // Motion widens it at once, and the turret rate comes from the yaw change over the step.
    state.step(&s, 3., 0., 0.1, NORMAL, 0.1).unwrap();
    let m = Motion { speed: 3., hull_rate: 0., turret_rate: 1. };
    assert!((state.factor - ideal(&s, m, 0., NORMAL)).abs() < 1e-3, "{}", state.factor);
    assert!(state.step(&s, 0., 0., 0., NORMAL, 0.).is_err());
}

#[test] fn k_follows_the_accuracy_within_its_bounds() {
    let a = accuracy();
    assert_eq!(central_zone(&a, 0.35), 0.5);
    assert!((central_zone(&a, 0.40) - 0.54).abs() < 1e-12);
    assert_eq!((central_zone(&a, 0.01), central_zone(&a, 2.)), (0.35, 0.7));
}

#[test] fn statistics_over_100000_shots_put_75_percent_in_the_zone_and_all_in_the_circle() {
    let a = accuracy();
    for radius in [0.29, 0.35, 0.41, 0.57] {
        let g = Gun { radius_m: radius, ..GUN };
        let k = central_zone(&a, radius);
        let (mut inside, mut near, mut quadrant) = (0u32, 0u32, [0u32; 4]);
        const N: u64 = 100_000;
        for seed in 0..N {
            let mixed = seed.wrapping_mul(0x9e37_79b9_7f4a_7c15) ^ 0x5bd1_e995;
            let (r, t) = deviation(&a, g, 1., mixed);
            assert!((0. ..=1.).contains(&r), "inside the circle");
            assert!((0. ..std::f64::consts::TAU).contains(&t));
            if r <= k { inside += 1; }
            if r <= 0.1 { near += 1; }
            quadrant[(t / std::f64::consts::FRAC_PI_2) as usize] += 1;
        }
        let share = f64::from(inside) / N as f64;
        assert!((share - 0.75).abs() < 0.006, "radius {radius}: {share}");
        assert!(f64::from(near) / (N as f64) < 0.12, "radius {radius}: {near} shots at the very centre");
        for q in quadrant { assert!((f64::from(q) / N as f64 - 0.25).abs() < 0.008, "{quadrant:?}"); }
    }
}

#[test] fn the_spg_distribution_stays_in_the_circle_and_is_centre_heavy() {
    let a = accuracy();
    let g = Gun { spg: true, ..GUN };
    assert_eq!(radial_fraction(&a, g, 0.), 0.);
    assert!((radial_fraction(&a, g, 1. - 1e-12) - 1.).abs() < 1e-5);
    let middle = radial_fraction(&a, g, 0.5);
    assert!((0.3..0.7).contains(&middle), "{middle}");
    assert!(radial_fraction(&a, g, 0.2) < radial_fraction(&a, g, 0.8));
}

#[test] fn deviation_turns_the_shot_by_exactly_r_and_is_reproducible() {
    let a = accuracy();
    assert_eq!(deviation(&a, GUN, 0.01, 77), deviation(&a, GUN, 0.01, 77));
    assert_ne!(deviation(&a, GUN, 0.01, 77), deviation(&a, GUN, 0.01, 78));
    for v in [[0., 0., 900.], [300., -20., 700.], [-500., 200., 100.], [0., 800., 0.]] {
        for (r, theta) in [(0.004, 0.), (0.02, 1.7), (0.05, 5.5)] {
            let out = deviate(v, r, theta).unwrap();
            let (a0, b): ([f64; 3], [f64; 3]) = (v.map(f64::from), out.map(f64::from));
            let (la, lb) = (a0.iter().map(|x| x * x).sum::<f64>().sqrt(), b.iter().map(|x| x * x).sum::<f64>().sqrt());
            assert!((la - lb).abs() < 1e-2, "speed {la} {lb}");
            let angle = (a0.iter().zip(&b).map(|(x, y)| x * y).sum::<f64>() / (la * lb)).clamp(-1., 1.).acos();
            assert!((angle - r).abs() < 2e-4, "{angle} {r}");
        }
    }
    assert!(deviate([0.; 3], 0.1, 0.).is_err());
}

#[test] fn the_spg_profile_narrows_the_circle_and_widens_the_blast() {
    let a = accuracy();
    assert_eq!((a.spg_accuracy_divisor, a.spg_splash_radius_factor), (1.25, 1.1));
    let spg = gun("ussr:Object_212").unwrap();
    assert!(spg.spg);
    assert_eq!(firing_gun(&a, "ussr:Object_212").unwrap().radius_m, spg.radius_m / 1.25);
    assert_eq!(blast_factor(&a, "ussr:Object_212").unwrap(), 1.1);
    let tank = gun("ussr:T-34-85").unwrap();
    assert_eq!(firing_gun(&a, "ussr:T-34-85").unwrap(), tank);
    assert_eq!(blast_factor(&a, "ussr:T-34-85").unwrap(), 1.);
}
