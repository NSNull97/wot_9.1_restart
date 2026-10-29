//! Pure explicit laboratory family mathematics. No HP mutation or native IDs.
use std::io;
use crate::p06t_shells091::{Family, Shell, PROFILES};

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
fn penetration(shell: Shell, distance: f64) -> f64 {
    if matches!(shell.family,Family::HollowCharge|Family::HighExplosive) || distance<=100. { shell.penetration_mm[0] }
    else { (shell.penetration_mm[0]+(shell.penetration_mm[1]-shell.penetration_mm[0])*(distance-100.)/400.).max(0.) }
}
fn attenuated_he(shell: Shell, distance: f64, armor: f64) -> io::Result<u16> {
    let radius=shell.explosion_radius_m.ok_or_else(||bad("HE source radius missing"))?;
    if !distance.is_finite() || distance<0. { return Err(bad("HE distance bound")); }
    valid_armor(armor)?;
    // Explicit LAB formula. Neither coefficients nor rounding are claimed to
    // reproduce the original server. No hidden damage/penetration RNG.
    Ok((0.5*f64::from(shell.damage_hp)*(1.-distance/radius).max(0.)-1.1*armor)
        .max(0.).floor().min(f64::from(shell.damage_hp)) as u16)
}
pub fn resolve_direct(i: DirectInput) -> io::Result<Resolution> {
    source_shell(i.shell)?;
    if !i.distance_m.is_finite() || !(0. ..=100_000.).contains(&i.distance_m) { return Err(bad("damage range bound")); }
    if let Some(armor)=i.plate.armor_mm {valid_armor(armor)?;}
    let dir=unit(i.chord)?;let normal=unit(i.winding_normal)?;
    let incidence=dir.iter().zip(normal).map(|(d,n)|d*n).sum::<f64>().abs().clamp(0.,1.).acos().to_degrees();
    let mut r=Resolution {policy:POLICY,decision:Decision::NotPierced,damage_hp:0,
        incidence_degrees:incidence,effective_armor_mm:None,
        nominal_power_mm:penetration(i.shell,i.distance_m),normalization_degrees:0.};
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
    else if i.shell.family==Family::HighExplosive {r.damage_hp=attenuated_he(i.shell,0.,armor)?;}
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
    if shell.family!=Family::HighExplosive || targets.len()>MAX_TARGETS {return Err(bad("damage splash family/count"));}
    let mut seen=[false;MAX_TARGETS];let mut out=Vec::with_capacity(targets.len());
    for target in targets {
        let slot=usize::from(target.slot);
        if slot>=MAX_TARGETS || seen[slot] || !target.distance_m.is_finite() || !(0. ..=100_000.).contains(&target.distance_m) {
            return Err(bad("damage splash identity/distance"));
        }
        valid_armor(target.armor_mm)?;seen[slot]=true;
        let damage=if target.los_clear {attenuated_he(shell,target.distance_m,target.armor_mm)?}else{0};
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
