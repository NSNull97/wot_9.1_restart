//! Isolated source-bound #717 WT/FV envelope candidate; no VehicleKind/runtime.
//! The formula is an independent f32 restatement of pinned original SSE, not
//! original-code execution or native aim/render qualification. No ballistics.
use std::f32::consts::{FRAC_PI_2,PI};
pub const SOURCE_PROOF_SHA256:&str="ad09cc66372a8ba03405128ea1f0a17c4909d622d13ed75ad7f469784e103733";
#[derive(Clone,Copy,Debug,PartialEq)]pub struct Limits{pub min:f32,pub max:f32}
#[derive(Clone,Copy,Debug,PartialEq)]struct Extra{limits:Limits,sector:f32}
#[derive(Clone,Copy,Debug,PartialEq)]pub struct SourceEnvelope{basic:Limits,absolute:Limits,front:Extra,rear:Extra,transition:f32,yaw:Option<Limits>}
#[derive(Clone,Copy,Debug,PartialEq)]pub struct SourceAim{pub envelope:SourceEnvelope,pub yaw_rate:f32,pub pitch_rate:f32}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Error{SourceBounds,Yaw,Pitch}
pub type Result<T>=std::result::Result<T,Error>;
const BASIC:Limits=Limits{min:f32::from_bits(0xbe860a92),max:f32::from_bits(0x3db2b8c2)};
impl SourceEnvelope{
    /// Source mounted basic(-15,5), rear(-7,5,37), transition5 DEGREES.
    /// WT128 six-shot and WT150 four-shot share this envelope, not clip data.
    pub const fn wt_e100()->Self{Self{basic:BASIC,absolute:BASIC,front:Extra{limits:BASIC,sector:0.},
        rear:Extra{limits:Limits{min:f32::from_bits(0xbdfa35dd),max:f32::from_bits(0x3db2b8c2)},sector:f32::from_bits(0x3f25514d)},
        transition:f32::from_bits(0x3db2b8c2),yaw:None}}
    /// Source mounted basic(-15,5), no rear override, turret yaw(-45,45).
    /// Missing XML transition uses source DEFAULT0.4 RADIANS, not0.4degrees.
    pub const fn fv215b_183()->Self{Self{basic:BASIC,absolute:BASIC,front:Extra{limits:BASIC,sector:0.},rear:Extra{limits:BASIC,sector:0.},
        transition:f32::from_bits(0x3ecccccd),yaw:Some(Limits{min:f32::from_bits(0xbf490fdb),max:f32::from_bits(0x3f490fdb)})}}
    pub fn basic(&self)->Limits{self.basic}pub fn absolute(&self)->Limits{self.absolute}pub fn yaw_limits(&self)->Option<Limits>{self.yaw}
    pub fn transition_radians(&self)->f32{self.transition}
    fn validate(&self)->Result<()>{
        fn limits(l:Limits,bound:f32)->bool{l.min.is_finite()&&l.max.is_finite()&&l.min>=-bound&&l.max<=bound&&l.min<=l.max}
        if !limits(self.absolute,FRAC_PI_2)||!limits(self.basic,FRAC_PI_2)||!limits(self.front.limits,FRAC_PI_2)||!limits(self.rear.limits,FRAC_PI_2)
            ||!self.transition.is_finite()||self.transition<=0.||self.transition>PI
            ||[self.front.sector,self.rear.sector].iter().any(|x|!x.is_finite()||*x<0.||*x>PI)
            ||self.front.sector+self.rear.sector+2.*self.transition>PI
            ||[self.basic,self.front.limits,self.rear.limits].iter().any(|l|l.min<self.absolute.min||l.max>self.absolute.max)
            ||self.yaw.is_some_and(|l|!limits(l,PI)){return Err(Error::SourceBounds);}Ok(())
    }
    pub fn clamp_yaw(&self,target:f32)->Result<f32>{self.validate()?;if !target.is_finite()||target.abs()>PI{return Err(Error::Yaw);}
        Ok(self.yaw.map_or(target,|l|target.clamp(l.min,l.max)))}
    /// Actual turret yaw must already obey its source restriction. Canonical
    /// [-pi,pi] input is required; do not silently wrap corrupted state here.
    pub fn pitch_limits(&self,yaw:f32)->Result<Limits>{
        self.validate()?;if !yaw.is_finite()||yaw.abs()>PI||self.yaw.is_some_and(|l|yaw<l.min||yaw>l.max){return Err(Error::Yaw);}
        let yaw=yaw.abs();if yaw<self.front.sector{return Ok(self.front.limits);}
        if yaw<self.front.sector+self.transition{return Ok(self.blend(yaw,self.front));}
        let delta=(yaw-PI).abs();if delta<self.rear.sector{return Ok(self.rear.limits);}
        if delta<self.rear.sector+self.transition{return Ok(self.blend(delta,self.rear));}Ok(self.basic)
    }
    fn blend(&self,delta:f32,extra:Extra)->Limits{
        // Keep independent f32 multiply/add steps in original observed order.
        let alpha=(delta-extra.sector)/self.transition;let rest=1.-alpha;
        Limits{min:self.basic.min*alpha+extra.limits.min*rest,max:self.basic.max*alpha+extra.limits.max*rest}
    }
    pub fn clamp_pitch(&self,yaw:f32,target:f32)->Result<f32>{if !target.is_finite()||target.abs()>FRAC_PI_2{return Err(Error::Pitch);}
        let limits=self.pitch_limits(yaw)?;Ok(target.clamp(limits.min,limits.max))}
}
impl SourceAim{
    pub fn wt128()->Self{Self{envelope:SourceEnvelope::wt_e100(),yaw_rate:rad(22.),pitch_rate:rad(26.25)}}
    pub fn wt150()->Self{Self{envelope:SourceEnvelope::wt_e100(),yaw_rate:rad(22.),pitch_rate:rad(23.625)}}
    pub fn fv183()->Self{Self{envelope:SourceEnvelope::fv215b_183(),yaw_rate:rad(16.),pitch_rate:rad(23.625)}}
}
fn rad(deg:f64)->f32{(deg*(std::f64::consts::PI/180.))as f32}

#[cfg(test)]#[path="p06t_source_aim_tests.rs"]mod tests;
