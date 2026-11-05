//! SHELL-CFG: the law reading the rules snapshot gives exactly the results of the
//! former constants (frozen copy of main 008495d2 below) over a wide input grid.
use super::*;

fn old_penetration(shell: Shell, distance: f64) -> f64 {
    if matches!(shell.family,Family::HollowCharge|Family::HighExplosive) || distance<=100. { shell.penetration_mm[0] }
    else { (shell.penetration_mm[0]+(shell.penetration_mm[1]-shell.penetration_mm[0])*(distance-100.)/400.).max(0.) }
}

fn old_attenuated_he(shell: Shell, distance: f64, armor: f64) -> io::Result<u16> {
    let radius=shell.explosion_radius_m.ok_or_else(||bad("HE source radius missing"))?;
    if !distance.is_finite() || distance<0. { return Err(bad("HE distance bound")); }
    valid_armor(armor)?;
    // Explicit LAB formula. Neither coefficients nor rounding are claimed to
    // reproduce the original server. No hidden damage/penetration RNG.
    Ok((0.5*f64::from(shell.damage_hp)*(1.-distance/radius).max(0.)-1.1*armor)
        .max(0.).floor().min(f64::from(shell.damage_hp)) as u16)
}

fn old_track_pass(shell: Shell, distance_m: f64, spent_before_mm: f64, armor_mm: f64) -> io::Result<TrackPass> {
    source_shell(shell)?;
    if !distance_m.is_finite() || !(0. ..=100_000.).contains(&distance_m) { return Err(bad("damage range bound")); }
    valid_armor(armor_mm)?; valid_armor(spent_before_mm)?;
    let power_before_mm = (old_penetration(shell, distance_m) - spent_before_mm).max(0.);
    let left = (power_before_mm - armor_mm).max(0.);
    let stopped = shell.family == Family::HighExplosive || left <= 0.;
    Ok(TrackPass { power_before_mm, power_after_mm: if stopped { 0. } else { left }, stopped })
}

fn old_resolve_direct_spent(i: DirectInput, spent_mm: f64) -> io::Result<Resolution> {
    source_shell(i.shell)?;
    valid_armor(spent_mm)?;
    if spent_mm > 0. && i.shell.family == Family::HighExplosive { return Err(bad("HE stops on the track")); }
    if !i.distance_m.is_finite() || !(0. ..=100_000.).contains(&i.distance_m) { return Err(bad("damage range bound")); }
    if let Some(armor)=i.plate.armor_mm {valid_armor(armor)?;}
    let dir=unit(i.chord)?;let normal=unit(i.winding_normal)?;
    let incidence=dir.iter().zip(normal).map(|(d,n)|d*n).sum::<f64>().abs().clamp(0.,1.).acos().to_degrees();
    let mut r=Resolution {policy:POLICY,decision:Decision::NotPierced,damage_hp:0,
        incidence_degrees:incidence,effective_armor_mm:None,
        nominal_power_mm:(old_penetration(i.shell,i.distance_m)-spent_mm).max(0.),normalization_degrees:0.};
    if i.distance_m>=i.shell.max_distance_m { r.decision=Decision::OutOfRange;return Ok(r); }
    let Some(armor)=i.plate.armor_mm.filter(|a|*a>0.) else {r.decision=Decision::Unsupported;return Ok(r)};
    if !i.plate.ordinary {r.decision=Decision::Unsupported;return Ok(r);}
    let (base_normalization,ricochet,overmatch)=match i.shell.family {
        Family::ArmorPiercing=>(5.,Some(70.),true),
        Family::ArmorPiercingCr=>(2.,Some(70.),true),
        Family::HollowCharge=>(0.,Some(85.),false),
        Family::HighExplosive=>(0.,None,false),
    };
    if ricochet.is_some_and(|angle|incidence>=angle) && (!overmatch || i.shell.caliber_mm<3.*armor) {
        r.decision=Decision::Ricochet;return Ok(r);
    }
    let normalization=if overmatch && i.shell.caliber_mm>=2.*armor {base_normalization*1.4*i.shell.caliber_mm/armor}else{base_normalization};
    if !normalization.is_finite() {return Err(bad("damage normalization overflow"));}
    let angle=(incidence-normalization).max(0.);
    let effective=armor/angle.to_radians().cos().max(f64::MIN_POSITIVE);
    if !effective.is_finite() {return Err(bad("damage effective armor overflow"));}
    r.effective_armor_mm=Some(effective);r.normalization_degrees=normalization;
    if r.nominal_power_mm>effective {r.decision=Decision::Pierced;r.damage_hp=i.shell.damage_hp;}
    else if i.shell.family==Family::HighExplosive {r.damage_hp=old_attenuated_he(i.shell,0.,armor)?;}
    Ok(r)
}

fn shells() -> Vec<Shell> {
    let mut out: Vec<Shell> = PROFILES.iter().flat_map(|p| p.shots).collect();
    let registry = crate::gateway091::shared::generated_vehicles::registry().unwrap();
    out.extend(registry.entries().iter().flat_map(|e| e.gun.shots));
    out
}
fn same<T: PartialEq + std::fmt::Debug>(a: io::Result<T>, b: io::Result<T>, what: &str) {
    match (a, b) { (Ok(a), Ok(b)) => assert_eq!(a, b, "{what}"), (Err(a), Err(b)) => assert_eq!(a.to_string(), b.to_string(), "{what}"),
        (a, b) => panic!("{what}: {a:?} vs {b:?}") }
}

#[test] fn direct_law_equals_the_former_constants_on_every_shell() {
    let shells = shells();
    assert!(shells.len() > 600, "{}", shells.len());
    let mut cases = 0usize;
    for shell in &shells {
        for armor in [None, Some(0.), Some(10.), Some(37.), Some(60.5), Some(91.45), Some(120.), Some(250.), Some(400.)] {
            for ordinary in [true, false] {
                for angle in [0f32, 15., 30., 45., 60., 69.9, 70., 70.1, 75., 80., 84.9, 85., 85.1, 89.] {
                    for distance in [0., 50., 100., 250., 499.9, 500., 650., 719.9, 720.] {
                        for spent in [0., 20., 75.] {
                            let a = angle.to_radians();
                            let i = DirectInput { shell: *shell, plate: Plate { armor_mm: armor, ordinary },
                                chord: [a.sin(), 0.13, -a.cos()], winding_normal: [0.01, 0., 1.], distance_m: distance };
                            same(resolve_direct_spent(i, spent), old_resolve_direct_spent(i, spent), shell.resource);
                            cases += 1;
                        }
                    }
                }
            }
        }
    }
    assert!(cases > 1_000_000, "{cases}");
}

#[test] fn track_and_splash_equal_the_former_constants() {
    for shell in shells() {
        for distance in [0., 99.9, 100., 300., 500., 719.] {
            for spent in [0., 15., 400.] { for armor in [0., 5., 20., 40., 1000.] {
                same(track_pass(shell, distance, spent, armor), old_track_pass(shell, distance, spent, armor), shell.resource);
            } }
        }
        if shell.family != Family::HighExplosive { continue; }
        for distance in [0., 0.3, 1., 2.5, 5.] { for armor in [0., 10., 35., 120.] { for los_clear in [true, false] {
            let target = [SplashTarget { slot: 7, distance_m: distance, armor_mm: armor, los_clear }];
            let old = if los_clear { old_attenuated_he(shell, distance, armor).unwrap() } else { 0 };
            assert_eq!(resolve_splash(shell, &target).unwrap(), vec![SplashDamage { slot: 7, damage_hp: old }], "{}", shell.resource);
        } } }
    }
}
