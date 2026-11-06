//! Pure explicit laboratory family mathematics. No HP mutation or native IDs.
//! SHELL-CFG: every number of the law comes from the immutable rules snapshot
//! (`shared/shell_rules.rs`); the policy strings name the law code itself.
use std::io;
use crate::p06t_shells091::{Family, Shell, PROFILES};
use crate::gateway091::shared::shell_rules::{rules, Rolls, Rules};

pub const POLICY: &str = "test_lab.p06t.single-plate-splash.v1";
/// Explicit opt-in LAB rule, not a reconstruction of the historical solver.
pub const UNARMORED_DEVICE_POLICY: &str = "test_lab.p06t.unarmored-gun-breech.v2";
pub const MAX_TARGETS: usize = 6;
fn bad(reason: &'static str) -> io::Error { io::Error::new(io::ErrorKind::InvalidData, reason) }

pub fn source_shell(shell: Shell) -> io::Result<()> {
    if !crate::p06t_shells091::known_shell(&shell) { return Err(bad("damage shell differs from frozen source catalogue")); }
    Ok(())
}
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct Plate {
    pub armor_mm: Option<f64>,
    /// The World adapter must establish the complete ordinary plate flags,
    /// revision and source identity. This is never a client-provided boolean.
    pub ordinary: bool,
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Decision { Pierced, NotPierced, Ricochet, Unsupported, OutOfRange, UnarmoredDevice }
// BW-01 wire codec (tools/bw01_wire_gen.py): Decision
impl crate::bw_wire::Wire for Decision {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){match self {Self::Pierced=>bw_o.tag(0),Self::NotPierced=>bw_o.tag(1),Self::Ricochet=>bw_o.tag(2),Self::Unsupported=>bw_o.tag(3),Self::OutOfRange=>bw_o.tag(4),Self::UnarmoredDevice=>bw_o.tag(5),}}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{match bw_i.tag()? {0=>Ok(Self::Pierced),1=>Ok(Self::NotPierced),2=>Ok(Self::Ricochet),3=>Ok(Self::Unsupported),4=>Ok(Self::OutOfRange),5=>Ok(Self::UnarmoredDevice),t=>crate::bw_wire::variant(t)}}
}
// end BW-01 wire codec
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct Resolution {
    pub policy: &'static str, pub decision: Decision, pub damage_hp: u16,
    pub incidence_degrees: f64, pub effective_armor_mm: Option<f64>,
    pub nominal_power_mm: f64, pub normalization_degrees: f64,
}
// BW-01 wire codec (tools/bw01_wire_gen.py): Resolution
impl crate::bw_wire::Wire for Resolution {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{policy,decision,damage_hp,incidence_degrees,effective_armor_mm,nominal_power_mm,normalization_degrees}=self;W::put(policy,bw_o);W::put(decision,bw_o);W::put(damage_hp,bw_o);W::put(incidence_degrees,bw_o);W::put(effective_armor_mm,bw_o);W::put(nominal_power_mm,bw_o);W::put(normalization_degrees,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{policy:W::get(bw_i)?,decision:W::get(bw_i)?,damage_hp:W::get(bw_i)?,incidence_degrees:W::get(bw_i)?,effective_armor_mm:W::get(bw_i)?,nominal_power_mm:W::get(bw_i)?,normalization_degrees:W::get(bw_i)?})}
}
// end BW-01 wire codec
#[derive(Clone,Copy,Debug)]
pub struct DirectInput {
    pub shell: Shell, pub plate: Plate,
    pub chord: [f32;3], pub winding_normal: [f32;3], pub distance_m: f64,
}
fn unit(v: [f32;3]) -> io::Result<[f64;3]> {
    if v.iter().any(|x| !x.is_finite() || x.abs()>200_000.) { return Err(bad("damage direction bound")); }
    let v=v.map(f64::from); let norm=v.iter().map(|x|x*x).sum::<f64>().sqrt();
    if norm==0. || !norm.is_finite() { return Err(bad("damage zero direction")); }
    Ok(v.map(|x|x/norm))
}
fn valid_armor(armor: f64) -> io::Result<()> {
    if !armor.is_finite() || !(0. ..=100_000.).contains(&armor) { return Err(bad("damage armor bound")); } Ok(())
}
fn penetration(r: &Rules, shell: Shell, distance: f64) -> f64 {
    if !r.family(shell.family).distance_falloff || distance<=r.full_power_until_m { shell.penetration_mm[0] }
    else { (shell.penetration_mm[0]+(shell.penetration_mm[1]-shell.penetration_mm[0])*(distance-r.full_power_until_m)/r.linear_span_m).max(0.) }
}
fn attenuated_he(r: &Rules, shell: Shell, distance: f64, armor: f64) -> io::Result<u16> {
    let radius=shell.explosion_radius_m.ok_or_else(||bad("HE source radius missing"))?;
    if !distance.is_finite() || distance<0. { return Err(bad("HE distance bound")); }
    valid_armor(armor)?;
    // Explicit LAB formula. Neither coefficients nor rounding are claimed to
    // reproduce the original server. No hidden damage/penetration RNG.
    Ok((r.he_damage_factor*f64::from(shell.damage_hp)*(1.-distance/radius).max(0.)-r.he_armor_factor*armor)
        .max(0.).floor().min(f64::from(shell.damage_hp)) as u16)
}
pub fn resolve_direct(i: DirectInput) -> io::Result<Resolution> { resolve_direct_spent(i, 0.) }
/// SHELL-02 track pass. INFERRED from the #717 track MaterialInfo (VERIFIED: armor N mm,
/// `useHitAngle` false, `mayRicochet` false, `vehicleDamageFactor` 0) and the 8.6 notes
/// "tracks act as spaced armour": the nominal track armour is taken off the shell power,
/// with no angle, ricochet or HP. HE detonates on the track. The HEAT loss behind a
/// screen (5 %/10 cm, 8.6) is NOT applied: its form is an open owner question.
pub const TRACK_PASS_POLICY: &str = "test_lab.shell02.track-spaced-nominal-armour.v1";
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct TrackPass { pub power_before_mm: f64, pub power_after_mm: f64, pub stopped: bool }
// BW-01 wire codec (tools/bw01_wire_gen.py): TrackPass
impl crate::bw_wire::Wire for TrackPass {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{power_before_mm,power_after_mm,stopped}=self;W::put(power_before_mm,bw_o);W::put(power_after_mm,bw_o);W::put(stopped,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{power_before_mm:W::get(bw_i)?,power_after_mm:W::get(bw_i)?,stopped:W::get(bw_i)?})}
}
// end BW-01 wire codec
pub fn track_pass(shell: Shell, distance_m: f64, spent_before_mm: f64, armor_mm: f64) -> io::Result<TrackPass> {
    source_shell(shell)?;
    let r = rules()?;
    if !distance_m.is_finite() || !(0. ..=100_000.).contains(&distance_m) { return Err(bad("damage range bound")); }
    valid_armor(armor_mm)?; valid_armor(spent_before_mm)?;
    let power_before_mm = (penetration(r, shell, distance_m) - spent_before_mm).max(0.);
    let left = (power_before_mm - armor_mm).max(0.);
    let stopped = shell.family == Family::HighExplosive || left <= 0.;
    Ok(TrackPass { power_before_mm, power_after_mm: if stopped { 0. } else { left }, stopped })
}
fn valid_roll(r: Rolls) -> io::Result<()> {
    if !(0.5..=1.5).contains(&r.penetration) || !(0.5..=1.5).contains(&r.damage) { return Err(bad("damage roll bound")); } Ok(())
}
/// One spaced layer or track crossed against the winding (SHELL-PEN step 1).
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct Layer { pub armor_mm: f64, pub use_hit_angle: bool, pub may_ricochet: bool, pub chord: [f32;3], pub winding_normal: [f32;3] }
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum PassOutcome { Passed, Absorbed, Ricochet, Stopped }
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct LayerPass { pub power_before_mm: f64, pub incidence_degrees: f64, pub normalization_degrees: f64,
    pub effective_armor_mm: f64, pub power_after_mm: f64, pub outcome: PassOutcome }
/// A spaced layer or track: HE stops (detonates) on it; HEAT stops by the owner's
/// choice (2026-11-06, option c); AP/APCR take the effective layer armour off the
/// rolled power (normalization and ricochet only where the material uses the hit
/// angle / may ricochet, as the #717 track MaterialInfo does not).
pub fn layer_pass(shell: Shell, distance_m: f64, spent_before_mm: f64, rolls: Rolls, layer: Layer) -> io::Result<LayerPass> {
    source_shell(shell)?;
    let rules = rules()?;
    valid_roll(rolls)?;
    if !distance_m.is_finite() || !(0. ..=100_000.).contains(&distance_m) { return Err(bad("damage range bound")); }
    valid_armor(layer.armor_mm)?; valid_armor(spent_before_mm)?;
    let caliber = if rules.caliber_integer { shell.caliber_mm.trunc() } else { shell.caliber_mm };
    let power_before_mm = (penetration(rules, shell, distance_m) * rolls.penetration - spent_before_mm).max(0.);
    let dir = unit(layer.chord)?; let normal = unit(layer.winding_normal)?;
    let incidence = if layer.use_hit_angle { dir.iter().zip(normal).map(|(d,n)|d*n).sum::<f64>().abs().clamp(0.,1.).acos().to_degrees() } else { 0. };
    let mut pass = LayerPass { power_before_mm, incidence_degrees: incidence, normalization_degrees: 0., effective_armor_mm: layer.armor_mm,
        power_after_mm: 0., outcome: PassOutcome::Stopped };
    if shell.family == Family::HighExplosive || shell.family == Family::HollowCharge && rules.heat_stops_on_spaced { return Ok(pass); }
    let family = rules.family(shell.family);
    if layer.use_hit_angle && layer.armor_mm > 0. {
        let overmatch = family.caliber_rules;
        if layer.may_ricochet && family.ricochet_deg.is_some_and(|a| incidence >= a) && (!overmatch || caliber < rules.no_ricochet_ratio * layer.armor_mm) {
            pass.outcome = PassOutcome::Ricochet; return Ok(pass);
        }
        let normalization = if overmatch && caliber >= rules.normalization_ratio * layer.armor_mm {
            family.normalization_deg * rules.normalization_multiplier * caliber / layer.armor_mm } else { family.normalization_deg };
        if !normalization.is_finite() { return Err(bad("damage normalization overflow")); }
        pass.normalization_degrees = normalization;
        pass.effective_armor_mm = layer.armor_mm / (incidence - normalization).max(0.).to_radians().cos().max(f64::MIN_POSITIVE);
        if !pass.effective_armor_mm.is_finite() { return Err(bad("damage effective armor overflow")); }
    }
    let left = power_before_mm - pass.effective_armor_mm;
    if left > 0. { pass.power_after_mm = left; pass.outcome = PassOutcome::Passed; } else { pass.outcome = PassOutcome::Absorbed; }
    Ok(pass)
}
/// `spent_mm` is the track armour already taken off this shot (`track_pass`); 0 is the old law.
pub fn resolve_direct_spent(i: DirectInput, spent_mm: f64) -> io::Result<Resolution> { resolve_plate(i, spent_mm, None) }
/// SHELL-PEN layered law (owner 2026-11-06): the main armour plate after the spaced
/// layers and tracks of this shot (`spent_mm`), with the shot's one penetration roll
/// and its damage roll; the caliber is the engine integer (#717 readInt).
pub const LAYERS_POLICY: &str = "project.armor-layers.v1";
pub fn resolve_layered(i: DirectInput, spent_mm: f64, rolls: Rolls) -> io::Result<Resolution> { resolve_plate(i, spent_mm, Some(rolls)) }
fn resolve_plate(i: DirectInput, spent_mm: f64, rolls: Option<Rolls>) -> io::Result<Resolution> {
    source_shell(i.shell)?;
    let rules = rules()?;
    valid_armor(spent_mm)?;
    if spent_mm > 0. && i.shell.family == Family::HighExplosive { return Err(bad("HE stops on the track")); }
    if !i.distance_m.is_finite() || !(0. ..=100_000.).contains(&i.distance_m) { return Err(bad("damage range bound")); }
    if let Some(armor)=i.plate.armor_mm {valid_armor(armor)?;}
    if let Some(r)=rolls { valid_roll(r)?; }
    let caliber=if rolls.is_some()&&rules.caliber_integer {i.shell.caliber_mm.trunc()} else {i.shell.caliber_mm};
    let dir=unit(i.chord)?;let normal=unit(i.winding_normal)?;
    let incidence=dir.iter().zip(normal).map(|(d,n)|d*n).sum::<f64>().abs().clamp(0.,1.).acos().to_degrees();
    let power=match rolls { Some(r)=>penetration(rules,i.shell,i.distance_m)*r.penetration, None=>penetration(rules,i.shell,i.distance_m) };
    let mut r=Resolution {policy:if rolls.is_some(){LAYERS_POLICY}else{POLICY},decision:Decision::NotPierced,damage_hp:0,
        incidence_degrees:incidence,effective_armor_mm:None,
        nominal_power_mm:(power-spent_mm).max(0.),normalization_degrees:0.};
    if i.distance_m>=i.shell.max_distance_m { r.decision=Decision::OutOfRange;return Ok(r); }
    let Some(armor)=i.plate.armor_mm.filter(|a|*a>0.) else {r.decision=Decision::Unsupported;return Ok(r)};
    if !i.plate.ordinary {r.decision=Decision::Unsupported;return Ok(r);}
    let family=rules.family(i.shell.family);
    let (base_normalization,ricochet,overmatch)=(family.normalization_deg,family.ricochet_deg,family.caliber_rules);
    if ricochet.is_some_and(|angle|incidence>=angle) && (!overmatch || caliber<rules.no_ricochet_ratio*armor) {
        r.decision=Decision::Ricochet;return Ok(r);
    }
    let normalization=if overmatch && caliber>=rules.normalization_ratio*armor {base_normalization*rules.normalization_multiplier*caliber/armor}else{base_normalization};
    if !normalization.is_finite() {return Err(bad("damage normalization overflow"));}
    let angle=(incidence-normalization).max(0.);
    let effective=armor/angle.to_radians().cos().max(f64::MIN_POSITIVE);
    if !effective.is_finite() {return Err(bad("damage effective armor overflow"));}
    r.effective_armor_mm=Some(effective);r.normalization_degrees=normalization;
    if r.nominal_power_mm>effective {r.decision=Decision::Pierced;r.damage_hp=match rolls {
        Some(roll)=>(f64::from(i.shell.damage_hp)*roll.damage).round().clamp(0.,f64::from(u16::MAX)) as u16,
        None=>i.shell.damage_hp };}
    else if i.shell.family==Family::HighExplosive {r.damage_hp=attenuated_he(rules,i.shell,0.,armor)?;}
    Ok(r)
}
/// Geometry/source identity is established by the Trace source-witness adapter.
/// The nominal HP factor is exactly one; no ordinary plate, ricochet,
/// normalization, historical layer continuation or hidden RNG is invented.
pub fn resolve_unarmored_device(i: DirectInput) -> io::Result<Resolution> {
    if i.plate.ordinary || i.plate.armor_mm != Some(0.) {
        return Err(bad("unarmored device requires explicit zero non-ordinary source plate"));
    }
    let mut result = resolve_direct(i)?; // unchanged canonical shell/range/vector bounds
    result.policy = UNARMORED_DEVICE_POLICY;
    if result.decision != Decision::OutOfRange {
        if result.decision != Decision::Unsupported { return Err(bad("unarmored device plate decision")); }
        result.decision = Decision::UnarmoredDevice;
        result.damage_hp = i.shell.damage_hp;
    }
    Ok(result)
}
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct SplashTarget {pub slot:u8,pub distance_m:f64,pub armor_mm:f64,pub los_clear:bool}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct SplashDamage {pub slot:u8,pub damage_hp:u16}
// BW-01 wire codec (tools/bw01_wire_gen.py): SplashDamage
impl crate::bw_wire::Wire for SplashDamage {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{slot,damage_hp}=self;W::put(slot,bw_o);W::put(damage_hp,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{slot:W::get(bw_i)?,damage_hp:W::get(bw_i)?})}
}
// end BW-01 wire codec
/// World owns the actual center-to-surface distance, LOS query and target
/// identity. Bounded typed facts do not prove that geometry query by themselves.
pub fn resolve_splash(shell:Shell,targets:&[SplashTarget])->io::Result<Vec<SplashDamage>> {
    source_shell(shell)?;
    let rules=rules()?;
    if shell.family!=Family::HighExplosive || targets.len()>MAX_TARGETS {return Err(bad("damage splash family/count"));}
    // Target identity is any actor slot of the battle (RES-30: 30 actors); MAX_TARGETS
    // only bounds the count per call. The old slot<6 bound failed 30-actor battles.
    use crate::gateway091::shared::model::MAX_ACTORS;
    let mut seen=[false;MAX_ACTORS];let mut out=Vec::with_capacity(targets.len());
    for target in targets {
        let slot=usize::from(target.slot);
        if slot>=MAX_ACTORS || seen[slot] || !target.distance_m.is_finite() || !(0. ..=100_000.).contains(&target.distance_m) {
            return Err(bad("damage splash identity/distance"));
        }
        valid_armor(target.armor_mm)?;seen[slot]=true;
        let damage=if target.los_clear {attenuated_he(rules,shell,target.distance_m,target.armor_mm)?}else{0};
        out.push(SplashDamage {slot:target.slot,damage_hp:damage});
    }
    Ok(out)
}

#[cfg(test)]
#[path="p06t_damage_tests.rs"]
mod tests;

#[cfg(test)]
#[path="p06t_breech_damage_tests.rs"]
mod breech_tests;

#[cfg(test)]
#[path="damage_law_rules_tests.rs"]
mod rules_tests;

#[cfg(test)]
#[path="armor_layers_law_tests.rs"]
mod layers_tests;
