//! Explicit server-owned tank ramming policy for the P05C test_lab scene.
//! This is engineering policy, not a historical 0.9.1 damage claim.
use std::io;
pub const POLICY:&str="test_lab-tank-ram-energy-v1";
const MIN_CLOSING_SPEED:f64=.5;const DAMAGE_ENERGY_SCALE:f64=12_000.;const MAX_DAMAGE:i16=500;
#[derive(Clone,Copy,Debug,PartialEq)]pub struct Contact{pub slot_a:usize,pub slot_b:usize,pub substep:u8,pub point:[f32;3],pub normal:[f32;3],pub relative_velocity:[f32;3]}
#[derive(Clone,Copy,Debug,PartialEq)]pub struct Resolution{pub attacker:usize,pub target:usize,pub closing_speed:f64,pub energy_j:f64,pub damage_a:i16,pub damage_b:i16}
fn dot(a:[f32;3],b:[f32;3])->f64{a.into_iter().zip(b).map(|(x,y)|f64::from(x)*f64::from(y)).sum()}
fn damage(energy:f64,target:f64,other:f64)->i16{(energy*other/(target+other)/DAMAGE_ENERGY_SCALE).floor().clamp(1.,f64::from(MAX_DAMAGE))as i16}
pub fn resolve(c:Contact,mass_a:f64,mass_b:f64)->io::Result<Option<Resolution>>{
    if c.slot_a>=c.slot_b||c.substep==0||c.substep>6||c.point.iter().any(|v|!v.is_finite()||v.abs()>2000.)||c.normal.iter().any(|v|!v.is_finite())||
       (c.normal.iter().map(|v|f64::from(*v).powi(2)).sum::<f64>()-1.).abs()>.002||c.relative_velocity.iter().any(|v|!v.is_finite()||v.abs()>50.002)||
       !mass_a.is_finite()||!mass_b.is_finite()||!(1000. ..=100000.).contains(&mass_a)||!(1000. ..=100000.).contains(&mass_b){return Err(io::Error::new(io::ErrorKind::InvalidData,POLICY));}
    let signed=dot(c.relative_velocity,c.normal);if signed<MIN_CLOSING_SPEED{return Ok(None);}let reduced=mass_a*mass_b/(mass_a+mass_b);let energy=.5*reduced*signed*signed;
    if !energy.is_finite()||energy<=0.{return Err(io::Error::new(io::ErrorKind::InvalidData,POLICY));}
    Ok(Some(Resolution{attacker:c.slot_a,target:c.slot_b,closing_speed:signed,energy_j:energy,damage_a:damage(energy,mass_a,mass_b),damage_b:damage(energy,mass_b,mass_a)}))
}
#[cfg(test)]mod tests{use super::*;fn c(v:f32)->Contact{Contact{slot_a:0,slot_b:1,substep:1,point:[0.,1.,0.],normal:[1.,0.,0.],relative_velocity:[v,0.,0.]}}
#[test]fn tangent_subthreshold_and_separating_do_not_damage(){assert!(resolve(c(.1),4691.,68190.).unwrap().is_none());assert!(resolve(c(-5.),4691.,68190.).unwrap().is_none());let mut t=c(5.);t.normal=[0.,0.,1.];assert!(resolve(t,4691.,68190.).unwrap().is_none());}
#[test]fn light_target_receives_more_of_same_energy(){let r=resolve(c(5.),4691.,68190.).unwrap().unwrap();assert!(r.damage_a>r.damage_b);assert_eq!((r.attacker,r.target),(0,1));}
#[test]fn malformed_geometry_and_mass_fail_closed(){let mut b=c(5.);b.normal=[2.,0.,0.];assert!(resolve(b,4691.,68190.).is_err());assert!(resolve(c(5.),10.,68190.).is_err());}}
