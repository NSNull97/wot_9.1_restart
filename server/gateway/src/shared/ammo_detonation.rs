//! Explicit owner-selected PROJECT rule, separate from old device policyv1.
//! This leaf does not mutate World HP/ammunition, authorize a collision, encode
//! native IDs or touch inventory. Root stages its event with one HP/death ledger.
use std::{f32::consts::PI,io};
use super::vehicle_profile::VehicleKind;
use crate::p06t_device_caps::{CAPS,Device,Profile};

pub const POLICY:&str="test_lab.p06t.ammo-bay-zero-loaded-detonation.v1";
pub const FLIGHT_POLICY:&str="test_lab.p06t.detached-turret-ballistic-terrain-clamp.v1";
pub const MAX_EVENTS:usize=6;
pub const MAX_TIME_MS:u64=3_600_000;
pub const FLIGHT_LIFETIME_MS:u64=5_000;
const MAX_SHOT:u32=960;
const MAX_POSITION:f32=100_000.;
// PROJECT visual trajectory, not historical impulse/Jolt simulation. A point
// samples authoritative static terrain at each publication and clamps on land.
const LOCAL_VELOCITY:[f64;3]=[2.,8.,1.5];
const GRAVITY:f64=9.81;
const ANGULAR_VELOCITY:[f64;3]=[1.2,0.7,2.4];
fn bad(reason:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,reason)}

#[derive(Clone,Copy,Debug,PartialEq)]
pub struct JointPose{pub position:[f32;3],pub direction:[f32;3]}
impl JointPose{
    fn validate(self)->io::Result<()>{
        if self.position.iter().any(|v|!v.is_finite()||v.abs()>MAX_POSITION)
            ||self.direction.iter().any(|v|!v.is_finite()||v.abs()>PI+0.001){return Err(bad("detonation joint pose bounds"));}Ok(())
    }
    fn identical(self,other:Self)->bool{self.position.into_iter().zip(other.position).chain(self.direction.into_iter().zip(other.direction)).all(|(a,b)|a.to_bits()==b.to_bits())}
}
/// Caller must bind this to the ACTUAL positive→zero AmmoBay transition and
/// retained source plate/shot proof. These checked scalars cannot prove that
/// provenance by themselves. Counts include any shells already in the clip.
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct Input{
    pub shot:u32,pub target:usize,pub attacker:usize,pub tick:u32,
    pub device_sequence:u32,pub device_before:u16,pub device_after:u16,
    pub health_before:u16,pub residual_hp:u16,pub counts:[u16;3],
    pub kind:VehicleKind,pub joint:JointPose,pub from_fire:bool,
}
impl Input{
    fn validate(self,roster:u8)->io::Result<()>{
        let max=CAPS[Profile::ALL[self.kind.index()].index()][Device::AmmoBay as usize].max;
        let total=self.counts.iter().map(|n|u32::from(*n)).sum::<u32>();
        if self.shot==0||self.shot>MAX_SHOT||self.target>=usize::from(roster)||self.attacker>=usize::from(roster)||self.attacker==self.target
            ||!(1000..=37000).contains(&self.tick)||!(1..=15360).contains(&self.device_sequence)
            ||self.device_before==0||self.device_before>max||self.device_after!=0
            ||self.health_before==0||self.health_before>self.kind.max_health()as u16||self.residual_hp>self.health_before
            ||total>u32::from(self.kind.ammo_limit()){return Err(bad("detonation source transition or counts bounds"));}
        self.joint.validate()
    }
    fn identical(self,other:Self)->bool{
        self.shot==other.shot&&self.target==other.target&&self.attacker==other.attacker&&self.tick==other.tick
            &&self.device_sequence==other.device_sequence&&self.device_before==other.device_before&&self.device_after==other.device_after
            &&self.health_before==other.health_before&&self.residual_hp==other.residual_hp&&self.counts==other.counts
            &&self.kind==other.kind&&self.from_fire==other.from_fire&&self.joint.identical(other.joint)
    }
}
/// Private construction prevents a consumer from manufacturing event authority
/// through a struct literal. It still needs Root's actual World/Trace causality.
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct Event{sequence:u32,input:Input}
impl Event{
    pub fn sequence(self)->u32{self.sequence}
    pub fn policy(self)->&'static str{POLICY}
    pub fn shot(self)->u32{self.input.shot}
    pub fn target(self)->usize{self.input.target}
    pub fn attacker(self)->usize{self.input.attacker}
    pub fn tick(self)->u32{self.input.tick}
    pub fn device_sequence(self)->u32{self.input.device_sequence}
    pub fn from_fire(self)->bool{self.input.from_fire}
    pub fn health_before(self)->u16{self.input.health_before}
    /// Additional HP damage AFTER ordinary plate damage; Root composes both in
    /// ONE DamageRecord, especially if a final crew seat died in the same batch.
    pub fn additional_damage(self)->u16{self.input.residual_hp}
    pub fn final_hp(self)->u16{0}
    pub fn lost(self)->[u16;3]{self.input.counts}
    pub fn kind(self)->VehicleKind{self.input.kind}
    pub fn joint(self)->JointPose{self.input.joint}
    pub fn born_ms(self)->u64{u64::from(self.input.tick-1000)*100}
}
#[derive(Clone,Copy,Debug,PartialEq)]
pub enum Outcome{New(Event),Empty,Replay(Option<Event>)}
#[derive(Clone,Copy,Debug,PartialEq)]
struct Seen{input:Input,event:Option<usize>}
#[derive(Clone,Debug,PartialEq)]
pub struct Ledger{roster:u8,seen:Vec<Seen>,events:Vec<Event>}
impl Ledger{
    pub fn new(roster:u8)->io::Result<Self>{
        if !(2..=MAX_EVENTS as u8).contains(&roster){return Err(bad("detonation roster bounds"));}
        Ok(Self{roster,seen:Vec::new(),events:Vec::new()})
    }
    pub fn events(&self)->&[Event]{&self.events}
    pub fn is_pristine(&self)->bool{self.seen.is_empty()&&self.events.is_empty()}
    /// At most one rack-destruction observation per target, including empty-rack
    /// tombstones. An exact replay is explicit and never creates a second loss.
    pub fn apply(&mut self,input:Input)->io::Result<Outcome>{
        input.validate(self.roster)?;
        if let Some(old)=self.seen.iter().find(|old|old.input.target==input.target){
            if !old.input.identical(input){return Err(bad("conflicting rack transition replay"));}
            return Ok(Outcome::Replay(old.event.map(|index|self.events[index])));
        }
        if self.seen.len()>=usize::from(self.roster)||self.events.len()>=MAX_EVENTS{return Err(bad("detonation journal bounds"));}
        // No event, no lethal HP proposal and no visual flight for an empty rack.
        if input.counts==[0;3]{self.seen.push(Seen{input,event:None});return Ok(Outcome::Empty);}
        let index=self.events.len();let event=Event{sequence:index as u32+1,input};
        self.seen.push(Seen{input,event:Some(index)});self.events.push(event);Ok(Outcome::New(event))
    }
}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum FlightPhase{Flying,Resting,Expired}
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct FlightSample{pub position:[f32;3],pub direction:[f32;3],pub phase:FlightPhase,pub at_ms:u64}
#[derive(Clone,Debug,PartialEq)]
pub struct Flight{event:Event,last_ms:Option<u64>,sample:FlightSample,landing:Option<JointPose>}
impl Flight{
    pub fn new(event:Event)->Self{let joint=event.joint();Self{event,last_ms:None,
        sample:FlightSample{position:joint.position,direction:joint.direction,phase:FlightPhase::Flying,at_ms:event.born_ms()},landing:None}}
    pub fn event(&self)->Event{self.event}
    pub fn sample(&self)->FlightSample{self.sample}
    /// Root calls this independently of the frozen outcome/HP clock. The
    /// callback supplies actual authoritative terrain height at world(X,Z),
    /// never client data. This PROJECT point clamp is neither a swept volume
    /// nor Jolt collision. No actor HP/device/shot state enters this method.
    pub fn advance<F>(&mut self,now_ms:u64,mut ground:F)->io::Result<FlightSample>
        where F:FnMut(f32,f32)->io::Result<f32>{
        if now_ms>MAX_TIME_MS||now_ms<self.event.born_ms()||self.last_ms.is_some_and(|old|now_ms<old){return Err(bad("detached turret flight monotonic clock"));}
        if self.last_ms==Some(now_ms){return Ok(self.sample);}
        let mut next=self.clone();
        if next.sample.phase==FlightPhase::Expired{next.last_ms=Some(now_ms);next.sample.at_ms=now_ms;*self=next;return Ok(self.sample);}
        let elapsed=now_ms-self.event.born_ms();let t=elapsed.min(FLIGHT_LIFETIME_MS)as f64/1000.;
        let joint=if let Some(landing)=next.landing{landing}else{
            let born=self.event.joint();let(s,c)=f64::from(born.direction[0]).sin_cos();
            let velocity=[LOCAL_VELOCITY[0]*c+LOCAL_VELOCITY[2]*s,LOCAL_VELOCITY[1],-LOCAL_VELOCITY[0]*s+LOCAL_VELOCITY[2]*c];
            let mut position:[f32;3]=std::array::from_fn(|i|{
                let drop=if i==1{GRAVITY*t*t/2.}else{0.};
                (f64::from(born.position[i])+velocity[i]*t-drop)as f32
            });
            if position.iter().any(|v|!v.is_finite()||v.abs()>MAX_POSITION){return Err(bad("detached turret trajectory bounds"));}
            let height=ground(position[0],position[2])?;
            if !height.is_finite()||height.abs()>MAX_POSITION{return Err(bad("detached turret terrain height bounds"));}
            let direction=std::array::from_fn(|i|wrap(f64::from(born.direction[i])+ANGULAR_VELOCITY[i]*t));
            if position[1]<=height{position[1]=height;let landed=JointPose{position,direction};next.landing=Some(landed);landed}
            else{JointPose{position,direction}}
        };
        let phase=if elapsed>=FLIGHT_LIFETIME_MS||now_ms==MAX_TIME_MS{FlightPhase::Expired}
            else if next.landing.is_some(){FlightPhase::Resting}else{FlightPhase::Flying};
        next.sample=FlightSample{position:joint.position,direction:joint.direction,phase,at_ms:now_ms};
        next.last_ms=Some(now_ms);*self=next;Ok(self.sample)
    }
}
fn wrap(value:f64)->f32{((value+std::f64::consts::PI).rem_euclid(2.*std::f64::consts::PI)-std::f64::consts::PI)as f32}

#[cfg(test)]
#[path="ammo_detonation_tests.rs"]mod tests;
