//! Explicit owner-selected PROJECT rule, separate from old device policyv1.
//! This leaf does not mutate World HP/ammunition, authorize a collision, encode
//! native IDs or touch inventory. Root stages its event with one HP/death ledger.
use std::{f32::consts::PI,io};
use super::vehicle_profile::VehicleKind;
use crate::p06t_device_caps::{Device,Profile};

pub const POLICY:&str="test_lab.p06t.ammo-bay-zero-loaded-detonation.v1";
pub const FLIGHT_POLICY:&str="test_lab.p06t.detached-turret-ballistic-terrain-clamp.v2-persistent-resting";
/// RES-30: at most one rack event per actor of a 30-actor roster (was 6).
pub const MAX_EVENTS:usize=super::model::MAX_ACTORS;
pub const MAX_TIME_MS:u64=3_600_000;
pub const FLIGHT_LIFETIME_MS:u64=5_000;
const MAX_SHOT:u32=super::model::MAX_BATTLE_SHOTS as u32;
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
        // Frozen loss-v1 has no qualified extended vehicle/device contract.
        // A public pure Input must refuse these kinds, never index ALL5.
        let profile=Profile::for_owned(self.kind).ok_or_else(||bad("detonation source profile unsupported"))?;
        let max=(*profile.caps())[Device::AmmoBay as usize].max;
        let total=self.counts.iter().map(|n|u32::from(*n)).sum::<u32>();
        if self.shot==0||self.shot>MAX_SHOT||self.target>=usize::from(roster)||self.attacker>=usize::from(roster)||self.attacker==self.target
            ||!(1000..=37000).contains(&self.tick)||!(1..=super::model::MAX_DAMAGE_EVENTS as u32).contains(&self.device_sequence)
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

/// TURRET-01 PROJECT launch policy (no 0.9.1 client data exists for it): the
/// detached turret+gun is a dynamic Jolt body in the battle-scene worker.
pub const JOLT_POLICY:&str="project.turret01.detached-turret-jolt-launch.v1";
/// One battle-RNG draw per launch parameter, journalled in this order.
pub const LAUNCH_DRAWS:usize=6;
/// RNG journal ordinals of the launch draws (ignition rolls use 0..=15).
pub const LAUNCH_ORDINAL:u8=0xe0;
/// Worker samples: one per 100 ms native tick from the detonation, at most 10 s.
pub const MAX_TRAJECTORY_SAMPLES:usize=101;
const MAX_LAUNCH_SPEED:f32=20.;
const MAX_LAUNCH_SPIN:f32=10.;

/// Initial body motion derived by Root from the actual detonation event and the
/// battle RNG. Velocities, not impulses: the resting place does not depend on a
/// turret mass that the client data does not carry.
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct Launch{pub linear_velocity:[f32;3],pub angular_velocity:[f32;3],pub draws:[u64;LAUNCH_DRAWS]}
impl Launch{
    /// PROJECT policy `JOLT_POLICY`: up 5..10 m/s (more with fuller rack),
    /// 1..4 m/s sideways along the attacker→target heading +-60 degrees,
    /// spin up to 3/2/3 rad/s about yaw-free X/Y/Z. `heading` is the shot's
    /// horizontal direction (radians, client yaw convention), `fill` the lost
    /// share of the rack 0..=1. `draws` are raw SplitMix64 outputs in order.
    pub fn derive(heading:f32,fill:f32,draws:[u64;LAUNCH_DRAWS])->io::Result<Self>{
        if !heading.is_finite()||!(0. ..=1.).contains(&fill){return Err(bad("turret launch source bounds"));}
        let u=draws.map(|v|((v>>11)as f64/(1u64<<53)as f64)as f32);
        let up=5.+3.*fill+2.*u[0];
        let azimuth=heading+(u[1]-0.5)*2.*PI/3.;let side=1.+3.*u[2];
        let launch=Self{linear_velocity:[side*azimuth.sin(),up,side*azimuth.cos()],
            angular_velocity:[(u[3]-0.5)*6.,(u[4]-0.5)*4.,(u[5]-0.5)*6.],draws};
        launch.validate()?;Ok(launch)
    }
    pub fn validate(self)->io::Result<()>{
        let speed=self.linear_velocity.iter().map(|v|v*v).sum::<f32>().sqrt();
        let spin=self.angular_velocity.iter().map(|v|v*v).sum::<f32>().sqrt();
        if !speed.is_finite()||speed>MAX_LAUNCH_SPEED||!spin.is_finite()||spin>MAX_LAUNCH_SPIN{return Err(bad("turret launch motion bounds"));}Ok(())
    }
}
/// Poses of the actual Jolt body at born_ms + 100 ms * index. The last pose is
/// where the body came to rest (or the bounded end of the simulation).
#[derive(Clone,Debug,PartialEq)]
pub struct Trajectory{pub samples:Vec<JointPose>,pub slept:bool}
impl Trajectory{
    pub fn validate(&self)->io::Result<()>{
        if self.samples.is_empty()||self.samples.len()>MAX_TRAJECTORY_SAMPLES{return Err(bad("turret trajectory sample count"));}
        for sample in &self.samples{sample.validate()?;}Ok(())
    }
}
#[derive(Clone,Debug,PartialEq)]
struct Jolt{launch:Launch,trajectory:Option<Trajectory>}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum FlightPhase{Flying,Resting,Expired}
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct FlightSample{pub position:[f32;3],pub direction:[f32;3],pub phase:FlightPhase,pub at_ms:u64}
#[derive(Clone,Debug,PartialEq)]
pub struct Flight{event:Event,last_ms:Option<u64>,sample:FlightSample,landing:Option<JointPose>,jolt:Option<Jolt>}
impl Flight{
    /// Legacy PROJECT point trajectory (`FLIGHT_POLICY`) for a World without a
    /// battle-scene worker. A scene battle uses `Flight::jolt`.
    pub fn new(event:Event)->Self{let joint=event.joint();Self{event,last_ms:None,
        sample:FlightSample{position:joint.position,direction:joint.direction,phase:FlightPhase::Flying,at_ms:event.born_ms()},landing:None,jolt:None}}
    /// TURRET-01: the pose holds at the joint until the scene worker returns
    /// the body's trajectory; then it plays that trajectory by the clock.
    pub fn jolt(event:Event,launch:Launch)->io::Result<Self>{
        launch.validate()?;let mut flight=Self::new(event);flight.jolt=Some(Jolt{launch,trajectory:None});Ok(flight)
    }
    pub fn launch(&self)->Option<Launch>{self.jolt.as_ref().map(|j|j.launch)}
    /// A Jolt flight whose worker trajectory has not arrived yet.
    pub fn awaiting_trajectory(&self)->bool{self.jolt.as_ref().is_some_and(|j|j.trajectory.is_none())}
    pub fn trajectory(&self)->Option<&Trajectory>{self.jolt.as_ref().and_then(|j|j.trajectory.as_ref())}
    /// Exactly once per Jolt flight. The first sample is the detonation joint
    /// pose the request carried; anything else is not this body.
    pub fn install_trajectory(&mut self,trajectory:Trajectory)->io::Result<()>{
        trajectory.validate()?;
        let born=self.event.joint();
        let jolt=self.jolt.as_mut().ok_or_else(||bad("legacy turret flight has no Jolt body"))?;
        if jolt.trajectory.is_some(){return Err(bad("turret trajectory already installed"));}
        let first=trajectory.samples[0];
        if first.position.iter().zip(born.position).any(|(a,b)|(a-b).abs()>0.01){return Err(bad("turret trajectory start differs from joint"));}
        jolt.trajectory=Some(trajectory);Ok(())
    }
    pub fn event(&self)->Event{self.event}
    pub fn sample(&self)->FlightSample{self.sample}
    /// Root calls this independently of the frozen outcome/HP clock. The
    /// callback supplies actual authoritative terrain height at world(X,Z),
    /// never client data. This PROJECT point clamp is neither a swept volume
    /// nor Jolt collision. No actor HP/device/shot state enters this method.
    /// Once the point reaches ground it remains `Resting` for the lifetime of
    /// the battle. The old five-second `Expired` transition made the native
    /// child leave the world while the dead parent was still being observed,
    /// which made the turret snap back or disappear per recipient.
    pub fn advance<F>(&mut self,now_ms:u64,mut ground:F)->io::Result<FlightSample>
        where F:FnMut(f32,f32)->io::Result<f32>{
        if now_ms>MAX_TIME_MS||now_ms<self.event.born_ms()||self.last_ms.is_some_and(|old|now_ms<old){return Err(bad("detached turret flight monotonic clock"));}
        if self.last_ms==Some(now_ms){return Ok(self.sample);}
        let mut next=self.clone();
        if next.sample.phase==FlightPhase::Expired{next.last_ms=Some(now_ms);next.sample.at_ms=now_ms;*self=next;return Ok(self.sample);}
        let elapsed=now_ms-self.event.born_ms();
        if let Some(jolt)=&self.jolt{
            // Whole 100 ms worker samples only: the native pose stream carries
            // one pose per tick and the client filter interpolates between them.
            let(joint,phase)=match &jolt.trajectory{
                None=>(self.event.joint(),FlightPhase::Flying),
                Some(t)=>{let index=usize::try_from(elapsed/100).map_err(|_|bad("turret trajectory index"))?.min(t.samples.len()-1);
                    (t.samples[index],if index+1==t.samples.len(){FlightPhase::Resting}else{FlightPhase::Flying})},
            };
            next.sample=FlightSample{position:joint.position,direction:joint.direction,phase,at_ms:now_ms};
            next.last_ms=Some(now_ms);*self=next;return Ok(self.sample);
        }let t=elapsed.min(FLIGHT_LIFETIME_MS)as f64/1000.;
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
            if position[1]<=height||elapsed>=FLIGHT_LIFETIME_MS{
                position[1]=height;let landed=JointPose{position,direction};next.landing=Some(landed);landed
            }
            else{JointPose{position,direction}}
        };
        let phase=if next.landing.is_some(){FlightPhase::Resting}else{FlightPhase::Flying};
        next.sample=FlightSample{position:joint.position,direction:joint.direction,phase,at_ms:now_ms};
        next.last_ms=Some(now_ms);*self=next;Ok(self.sample)
    }
}
fn wrap(value:f64)->f32{((value+std::f64::consts::PI).rem_euclid(2.*std::f64::consts::PI)-std::f64::consts::PI)as f32}

#[cfg(test)]
#[path="ammo_detonation_tests.rs"]mod tests;
