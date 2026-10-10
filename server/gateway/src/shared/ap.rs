//! Opt-in, deterministic test_lab AP resolver for one measured MS-1 plate.
//!
//! VERIFIED inputs: #717 stock gun5892/AP2570 nominal penetration 34/27,
//! caliber 37 and armor damage 30; P06J component material facts. Source pins
//! and the server-only gaps are recorded in docs/research/P06K_AP_IMPACT_CONTRACT.md.
//! The actual historical server algorithm is UNKNOWN. Every rule below is
//! an explicit approximate laboratory policy, not a reconstructed 0.9.1 solver:
//! - muzzle-to-contact straight-line distance, nominal power continued beyond
//!   500 m until the hard 720 m limit, no penetration or damage RNG;
//! - abs(dot) incidence for an unoriented plane, 5 deg normalization, a 1.4x
//!   caliber/armor boost at >=2x, no ricochet at >=3x, ricochet at >=70deg;
//! - homogenization 1, one positive ordinary hull/turret plate, strict power
//!   > effective armor, fixed 30 damage on penetration, no modules or layers.
//! Normals are not claimed outward: abs(dot) cannot identify entry/exit or
//! validate layer ordering. This pure module neither changes HP nor encodes
//! native effect IDs. The caller owns damage permission and the transaction.

use std::io;
use super::materials::{self, Component, MaterialFacts, SourceClass};

pub const PROFILE_REVISION: &str = "test_lab-ms1-ap-single-plate-v1";
pub const HISTORICAL_FIDELITY: &str = "approximate";
pub const CALIBER: f64 = 37.0;
pub const DAMAGE: u16 = 30;
pub const NORMALIZATION_DEGREES: f64 = 5.0;
pub const RICOCHET_DEGREES: f64 = 70.0;
pub const MAX_DISTANCE: f64 = 720.0;
const MAX_INPUT_DISTANCE: f64 = 100_000.0;
const MAX_INPUT_COMPONENT: f64 = 200_000.0;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Reason {
    MaterialRevision,
    Component,
    MaterialClass,
    MissingMaterial,
    MissingArmor,
    ZeroArmor,
    VehicleDamageFactor,
    ProjectileChance,
    MaterialFlags,
}
impl Reason {
    pub fn label(self) -> &'static str { match self {
        Self::MaterialRevision => "material_revision",
        Self::Component => "component",
        Self::MaterialClass => "material_class",
        Self::MissingMaterial => "missing_material",
        Self::MissingArmor => "missing_armor",
        Self::ZeroArmor => "zero_armor",
        Self::VehicleDamageFactor => "vehicle_damage_factor",
        Self::ProjectileChance => "projectile_chance",
        Self::MaterialFlags => "material_flags",
    } }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Outcome { Ricochet, NotPierced, Pierced, Unsupported(Reason) }
impl Outcome {
    pub fn label(self) -> &'static str { match self {
        Self::Ricochet => "ricochet", Self::NotPierced => "not_pierced",
        Self::Pierced => "pierced", Self::Unsupported(_) => "unsupported",
    } }
}

#[derive(Clone, Copy, Debug)]
pub struct Input<'a> {
    pub material: &'a MaterialFacts,
    /// Exact retained server collision chord, not client aim or hit direction.
    pub segment_direction: [f32; 3],
    pub winding_normal: [f32; 3],
    /// Server muzzle-to-contact straight-line distance, in metres.
    pub distance: f64,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Resolution {
    pub outcome: Outcome,
    pub armor: Option<f64>,
    pub incidence_degrees: Option<f64>,
    /// None when the plate calculation is unavailable or ricochet occurs first.
    pub effective_armor: Option<f64>,
    pub nominal_power: Option<f64>,
    /// None when normalization was not reached (unsupported/ricochet).
    pub normalization_degrees: Option<f64>,
    pub damage: u16,
    pub profile_revision: &'static str,
}

fn bad() -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, "invalid test_lab AP input")
}
fn unit(vector: [f32; 3]) -> io::Result<[f64; 3]> {
    let vector = vector.map(f64::from);
    if vector.iter().any(|v| !v.is_finite() || v.abs() > MAX_INPUT_COMPONENT) { return Err(bad()); }
    let length = vector.iter().map(|v| v * v).sum::<f64>().sqrt();
    if !length.is_finite() || length == 0.0 { return Err(bad()); }
    Ok(vector.map(|v| v / length))
}
fn power(distance: f64) -> f64 {
    if distance >= MAX_DISTANCE { 0.0 }
    else if distance <= 100.0 { 34.0 }
    else { (34.0 + (27.0 - 34.0) * (distance - 100.0) / 400.0).max(0.0) }
}

/// Invalid numerical/contradictory input is an error, allowing complete World
/// rollback. A valid but unsupported surface is a typed zero-damage outcome;
/// it must never acquire invented armor or silently become an ordinary plate.
pub fn resolve(input: Input<'_>) -> io::Result<Resolution> {
    if !input.distance.is_finite() || !(0.0..=MAX_INPUT_DISTANCE).contains(&input.distance) { return Err(bad()); }
    let direction = unit(input.segment_direction)?;
    let normal = unit(input.winding_normal)?;
    let cosine = direction.iter().zip(normal).map(|(d, n)| d * n).sum::<f64>().abs().clamp(0.0, 1.0);
    let incidence = cosine.acos().to_degrees();
    let material = input.material;
    let armor = material.effective.as_ref().and_then(|e| e.armor).map(f64::from);
    if let Some(e) = &material.effective {
        if e.kind != material.kind
            || armor.is_some_and(|v| !v.is_finite() || !(0.0..=100_000.0).contains(&v))
            || [e.vehicle_damage_factor, e.chance_to_hit_by_projectile, e.chance_to_hit_by_explosion]
                .iter().any(|v| !v.is_finite() || !(0.0..=1.0).contains(v))
            || e.damage_kind > 1 { return Err(bad()); }
    }
    let mut result = Resolution { outcome: Outcome::NotPierced, armor,
        incidence_degrees: Some(incidence), effective_armor: None,
        nominal_power: Some(power(input.distance)), normalization_degrees: None,
        damage: 0, profile_revision: PROFILE_REVISION };
    let unsupported = if material.profile_revision != materials::PROFILE_REVISION { Some(Reason::MaterialRevision) }
        else if !matches!(material.component, Component::Hull | Component::Turret01) { Some(Reason::Component) }
        else if material.source_class != SourceClass::ArmorDescriptor { Some(Reason::MaterialClass) }
        else if material.effective.is_none() { Some(Reason::MissingMaterial) }
        else if armor.is_none() { Some(Reason::MissingArmor) }
        else if armor == Some(0.0) { Some(Reason::ZeroArmor) }
        else {
            let max_kind = if material.component == Component::Hull { 12 } else { 10 };
            if material.kind == 0 || material.kind > max_kind || material.name != format!("armor_{}", material.kind) {
                return Err(bad());
            }
            let e = material.effective.as_ref().ok_or_else(bad)?;
            if e.vehicle_damage_factor != 1.0 { Some(Reason::VehicleDamageFactor) }
            else if e.chance_to_hit_by_projectile != 1.0 { Some(Reason::ProjectileChance) }
            else if !e.extra_is_none || !e.use_armor_homogenization || !e.use_hit_angle
                || !e.use_antifragmentation_lining || !e.may_ricochet || e.collide_once_only
                || e.damage_kind != 0 || e.chance_to_hit_by_explosion != 1.0 || !e.continue_trace_if_no_hit {
                Some(Reason::MaterialFlags)
            } else { None }
        };
    if let Some(reason) = unsupported {
        result.outcome = Outcome::Unsupported(reason); return Ok(result);
    }
    resolve_plate(&mut result, armor.ok_or_else(bad)?, incidence, power(input.distance));
    Ok(result)
}

// Called only for validated, positive ordinary plates. Boundary choices are
// part of v1's approximate contract, including equality at 2x/3x/70 deg.
fn resolve_plate(result: &mut Resolution, armor: f64, incidence: f64, power: f64) {
    if CALIBER < 3.0 * armor && incidence >= RICOCHET_DEGREES {
        result.outcome = Outcome::Ricochet; return;
    }
    let normalization = if CALIBER >= 2.0 * armor { NORMALIZATION_DEGREES * 1.4 * CALIBER / armor }
        else { NORMALIZATION_DEGREES };
    let angle = (incidence - normalization).max(0.0);
    let cosine = angle.to_radians().cos();
    let effective = armor / cosine;
    result.normalization_degrees = Some(normalization);
    result.effective_armor = Some(effective);
    // All supported paths have positive cosine: a thick grazing plate has
    // already ricocheted, while a >=3x plate gets >=21 deg normalization.
    // Strict equality is a laboratory stop; zero power cannot penetrate.
    if power > effective {
        result.outcome = Outcome::Pierced; result.damage = DAMAGE;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::materials::EffectiveMaterial;

    fn plate(armor: f32) -> MaterialFacts {
        MaterialFacts { component: Component::Hull, name: "armor_1".into(), kind: 1,
            source_class: SourceClass::ArmorDescriptor, profile_revision: materials::PROFILE_REVISION.into(),
            effective: Some(EffectiveMaterial { kind: 1, armor: Some(armor), extra_is_none: true,
                vehicle_damage_factor: 1.0, use_armor_homogenization: true, use_hit_angle: true,
                use_antifragmentation_lining: true, may_ricochet: true, collide_once_only: false,
                damage_kind: 0, chance_to_hit_by_projectile: 1.0, chance_to_hit_by_explosion: 1.0,
                continue_trace_if_no_hit: true }) }
    }
    fn input(material: &MaterialFacts) -> Input<'_> {
        Input { material, segment_direction: [0.0, 0.0, 35.36], winding_normal: [0.0, 0.0, -1.0], distance: 10.0 }
    }
    fn at_angle(material: &MaterialFacts, angle: f64) -> Resolution {
        let a = angle.to_radians(); let mut i = input(material);
        i.segment_direction = [a.sin() as f32, 0.0, a.cos() as f32]; resolve(i).unwrap()
    }
    fn exact_plate(armor: f64, angle: f64, power: f64) -> Resolution {
        let mut result = Resolution { outcome: Outcome::NotPierced, armor: Some(armor),
            incidence_degrees: Some(angle), effective_armor: None, nominal_power: Some(power),
            normalization_degrees: None, damage: 0, profile_revision: PROFILE_REVISION };
        resolve_plate(&mut result, armor, angle, power); result
    }

    #[test] fn nominal_distance_policy_continues_after_500_and_stops_at_720() {
        let m = plate(18.0);
        for (distance, expected) in [(0.0,34.0), (100.0,34.0), (300.0,30.5), (500.0,27.0),
            (600.0,25.25), (719.0,23.1675), (720.0,0.0), (100_000.0,0.0)] {
            let result = resolve(Input { distance, ..input(&m) }).unwrap();
            assert_eq!(result.nominal_power, Some(expected));
            if distance >= MAX_DISTANCE { assert_eq!(result.outcome, Outcome::NotPierced); assert_eq!(result.damage,0); }
        }
    }
    #[test] fn positive_ordinary_plate_has_fixed_damage_and_strict_penetration_equality() {
        assert_eq!(resolve(input(&plate(18.0))).unwrap().damage,30);
        let equal = resolve(input(&plate(34.0))).unwrap();
        assert_eq!(equal.outcome,Outcome::NotPierced); assert_eq!(equal.effective_armor,Some(34.0));
        assert_eq!(equal.damage,0);
        let lower = f32::from_bits(34.0f32.to_bits()-1);
        assert_eq!(resolve(input(&plate(lower))).unwrap().outcome,Outcome::Pierced);
        assert_eq!(resolve(input(&plate(35.0))).unwrap().outcome,Outcome::NotPierced);
    }
    #[test] fn winding_direction_and_vector_scale_do_not_change_unoriented_incidence() {
        let m = plate(18.0); let original = resolve(input(&m)).unwrap();
        for direction in [[0.0,0.0,1.0], [0.0,0.0,-100.0]] {
            for normal in [[0.0,0.0,1.0], [0.0,0.0,-2.0]] {
                assert_eq!(resolve(Input { segment_direction: direction, winding_normal: normal, ..input(&m) }).unwrap(),original);
            }
        }
        let a = at_angle(&m,60.0); assert!(a.incidence_degrees.unwrap()>59.999);
        assert!(a.effective_armor.unwrap()>18.0);
    }
    #[test] fn raw_angle_ricochet_precedes_normalization_at_inclusive_70() {
        let below=exact_plate(37.0,70.0-1e-9,1000.0);
        assert_eq!(below.outcome,Outcome::Pierced); assert_eq!(below.normalization_degrees,Some(5.0));
        for angle in [70.0,70.0+1e-9,90.0] {
            let r=exact_plate(37.0,angle,1000.0);
            assert_eq!(r.outcome,Outcome::Ricochet); assert_eq!(r.damage,0);
            assert_eq!(r.effective_armor,None); assert_eq!(r.normalization_degrees,None);
        }
        let m=plate(37.0);
        assert_ne!(at_angle(&m,69.99).outcome,Outcome::Ricochet);
        assert_eq!(at_angle(&m,70.01).outcome,Outcome::Ricochet);
    }
    #[test] fn inclusive_double_caliber_boost_and_triple_caliber_no_ricochet_are_explicit() {
        assert_eq!(exact_plate(18.5+1e-9,60.0,34.0).normalization_degrees,Some(5.0));
        assert_eq!(exact_plate(18.5,60.0,34.0).normalization_degrees,Some(14.0));
        assert!(exact_plate(18.5-1e-9,60.0,34.0).normalization_degrees.unwrap()>14.0);
        let boundary=CALIBER/3.0;
        assert_eq!(exact_plate(boundary+1e-9,80.0,34.0).outcome,Outcome::Ricochet);
        let no_ricochet=exact_plate(boundary,80.0,34.0);
        assert_ne!(no_ricochet.outcome,Outcome::Ricochet);
        assert!(no_ricochet.normalization_degrees.unwrap()>=21.0-1e-12);
        assert_ne!(exact_plate(boundary-1e-9,80.0,34.0).outcome,Outcome::Ricochet);
    }
    #[test] fn normalization_cannot_turn_a_small_angle_negative_and_thin_grazing_is_finite() {
        let r=exact_plate(18.0,1.0,34.0);
        assert_eq!(r.effective_armor,Some(18.0)); assert_eq!(r.damage,30);
        for armor in [8.0,0.001,f32::MIN_POSITIVE] {
            let r=at_angle(&plate(armor),90.0);
            assert!(r.effective_armor.unwrap().is_finite());
            assert!(r.normalization_degrees.unwrap().is_finite());
            assert!(r.outcome!=Outcome::Ricochet);
        }
    }
    #[test] fn known_unsupported_surfaces_never_receive_damage() {
        for reason in [Reason::MaterialRevision,Reason::Component,Reason::MaterialClass,Reason::MissingMaterial,
            Reason::MissingArmor,Reason::ZeroArmor,Reason::VehicleDamageFactor,Reason::ProjectileChance,Reason::MaterialFlags] {
            let mut m=plate(18.0);
            match reason {
                Reason::MaterialRevision=>m.profile_revision="unknown".into(),
                Reason::Component=>m.component=Component::Gun02,
                Reason::MaterialClass=>m.source_class=SourceClass::SurveyingDeviceVisualMaterial,
                Reason::MissingMaterial=>m.effective=None,
                Reason::MissingArmor=>m.effective.as_mut().unwrap().armor=None,
                Reason::ZeroArmor=>m.effective.as_mut().unwrap().armor=Some(0.0),
                Reason::VehicleDamageFactor=>m.effective.as_mut().unwrap().vehicle_damage_factor=0.0,
                Reason::ProjectileChance=>m.effective.as_mut().unwrap().chance_to_hit_by_projectile=0.33,
                Reason::MaterialFlags=>m.effective.as_mut().unwrap().damage_kind=1,
            }
            let before=m.clone(); let r=resolve(input(&m)).unwrap();
            assert_eq!(r.outcome,Outcome::Unsupported(reason)); assert_eq!(r.damage,0);
            assert_eq!(r.effective_armor,None); assert_eq!(r.normalization_degrees,None); assert_eq!(m,before);
        }
    }
    #[test] fn every_unsupported_source_flag_is_checked() {
        for which in 0..8 {
            let mut m=plate(18.0); let e=m.effective.as_mut().unwrap();
            match which { 0=>e.extra_is_none=false,1=>e.use_armor_homogenization=false,
                2=>e.use_hit_angle=false,3=>e.use_antifragmentation_lining=false,
                4=>e.may_ricochet=false,5=>e.collide_once_only=true,
                6=>e.chance_to_hit_by_explosion=0.5,7=>e.continue_trace_if_no_hit=false,_=>unreachable!() }
            assert_eq!(resolve(input(&m)).unwrap().outcome,Outcome::Unsupported(Reason::MaterialFlags));
        }
    }
    #[test] fn malformed_numbers_and_material_identity_fail_without_outcome() {
        let m=plate(18.0);
        for distance in [-1.0,100_001.0,f64::NAN,f64::INFINITY] {
            assert!(resolve(Input{distance,..input(&m)}).is_err());
        }
        for v in [[0.0;3],[f32::NAN,0.0,1.0],[0.0,f32::INFINITY,1.0],[200_001.0,0.0,1.0]] {
            assert!(resolve(Input{segment_direction:v,..input(&m)}).is_err());
            assert!(resolve(Input{winding_normal:v,..input(&m)}).is_err());
        }
        for armor in [-1.0,100_001.0,f32::NAN,f32::INFINITY] {
            assert!(resolve(input(&plate(armor))).is_err());
        }
        for which in 0..6 {
            let mut m=plate(18.0);
            match which {0=>m.kind=2,1=>m.name="armor_999".into(),
                2=>m.effective.as_mut().unwrap().vehicle_damage_factor=f32::NAN,
                3=>m.effective.as_mut().unwrap().chance_to_hit_by_projectile=1.1,
                4=>m.effective.as_mut().unwrap().chance_to_hit_by_explosion=-0.1,
                5=>m.effective.as_mut().unwrap().damage_kind=2,_=>unreachable!()}
            assert!(resolve(input(&m)).is_err());
        }
    }
    #[test] fn measured_catalog_ordinary_plates_work_and_special_records_remain_unsupported() {
        let b=super::super::geometry::tests::bundle();
        for component in ["Hull","Turret_01"] {
            let m=b.materials().lookup(component,"armor_1").unwrap();
            assert_eq!(resolve(input(&m)).unwrap().outcome,Outcome::Pierced);
            let m=b.materials().lookup(component,"surveyingDevice").unwrap();
            assert!(matches!(resolve(input(&m)).unwrap().outcome,Outcome::Unsupported(_)));
        }
        for (component,label) in [("Hull","armor_10"),("Hull","armor_11"),("Turret_01","armor_8"),
            ("Gun_02","armor_1"),("Gun_02","gun")] {
            let m=b.materials().lookup(component,label).unwrap();
            let r=resolve(input(&m)).unwrap(); assert!(matches!(r.outcome,Outcome::Unsupported(_))); assert_eq!(r.damage,0);
        }
    }
    #[test] fn replay_is_deterministic_and_labels_carry_the_approximation_boundary() {
        let m=plate(18.0); let expected=at_angle(&m,60.0);
        for _ in 0..40 { assert_eq!(at_angle(&m,60.0),expected); }
        assert_eq!(expected.profile_revision,"test_lab-ms1-ap-single-plate-v1");
        assert_eq!(HISTORICAL_FIDELITY,"approximate");
        assert_eq!(Outcome::Pierced.label(),"pierced");
        assert_eq!(Outcome::Unsupported(Reason::ZeroArmor).label(),"unsupported");
        assert_eq!(Reason::ZeroArmor.label(),"zero_armor");
    }
}
