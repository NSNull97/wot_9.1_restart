//! Explicit LAB module/seat/fire state. Root World owns vehicle HP and death.
use std::io;
use crate::{p06t_damage::source_shell,p06t_lab_proxy::Target,p06t_shells091::Shell,
    p06t_device_caps::{Profile,Device,CAPS,CREW,MAX_HP,ENGINE_FIRE_CHANCE,MIN_FIRE_STARTING_DAMAGE,SOURCE_SHA256,SOURCE_V2_SHA256}};

pub const POLICY:&str="test_lab.p06t.devices-proxy-fire.v1";
pub const POLICY_V2:&str="test_lab.p06t.devices-proxy-fire.v2";
pub const POLICY_SHA256:&str="cded466bf3c21243c10c0bcee8a013ab4cffc20f31f7275d4eab1672060b3717";
pub const POLICY_V2_SHA256:&str="a19115167b83e73ae80e83d578490ddbcbf81cbe759c62692fc390c732232918";
pub const MAX_CREW:usize=6;
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum PolicyVersion {V1,V2}
impl PolicyVersion {
    pub fn revision(self)->&'static str{match self{Self::V1=>POLICY,Self::V2=>POLICY_V2}}
    pub fn source_caps_sha(self)->&'static str{match self{Self::V1=>SOURCE_SHA256,Self::V2=>SOURCE_V2_SHA256}}
    pub fn manifest_sha(self)->&'static str{match self{Self::V1=>POLICY_SHA256,Self::V2=>POLICY_V2_SHA256}}
}
pub const MAX_HITS:usize=1920;
pub const MAX_TIME_MS:u64=3_600_000;
pub const FIRE_INTERVAL_MS:u64=1000;
pub const MAX_FIRE_TICKS:u8=10;
/// Explicit bounded LAB repair delay. The original client exposes the
/// repaired-state notifications, but the historical server timer/crew
/// modifiers are not established by the available evidence.
pub const MODULE_REPAIR_DELAY_MS:u64=1000;
fn bad(reason:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,reason)}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Condition {Normal,Critical,Destroyed}
fn condition(hp:u16,max:u16)->Condition {if hp==0{Condition::Destroyed}else if u32::from(hp)*2<=u32::from(max){Condition::Critical}else{Condition::Normal}}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct Cause {pub shot:u32,pub attacker_slot:u8}
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct ModuleHit {
    pub cause:Cause,pub ordinal:u8,pub at_ms:u64,pub target:Target,pub shell:Shell,
    /// World supplies and journals the deterministic draw for ignition-capable
    /// engine/fuel hits. A direct nonigniting Gun-only policy supplies canonical
    /// unused0 without consuming RNG. Replay must preserve that chosen input.
    pub ignition_roll:f64,
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Change {
    Device {device:Device,extra_index:u8,max_health:u16,before:u16,after:u16,before_condition:Condition,after_condition:Condition,repair:bool},
    Crew {seat:u8,extra_index:u8,before_active:bool,after_active:bool},
    Fire {before_active:bool,after_active:bool},
    /// Requested delta; caller must apply through its one HP/death ledger.
    VehicleDamage {amount:u16},
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct Transition {pub sequence:u32,pub at_ms:u64,pub cause:Cause,pub from_fire:bool,pub change:Change}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct Health {pub hp:u16,pub max_hp:u16,pub terminal:bool}
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct Capabilities {
    pub crew_active:bool,pub can_fire:bool,pub drive_scale:f32,pub steer_scale:f32,
    pub turret_scale:f32,pub aim_speed_scale:f32,pub dispersion_scale:f32,
    pub reload_scale:f32,pub view_scale:f32,pub radio_scale:f32,
}
impl Capabilities {
    pub fn validate(self)->io::Result<()> {
        if [self.drive_scale,self.steer_scale,self.turret_scale,self.aim_speed_scale,self.view_scale,self.radio_scale]
            .iter().any(|v|!v.is_finite()||!(0. ..=1.).contains(v))
            || [self.dispersion_scale,self.reload_scale].iter().any(|v|!v.is_finite()||!(1. ..=4.).contains(v))
            || !self.crew_active&&self.can_fire {return Err(bad("device capability bounds"));}Ok(())
    }
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
struct Fire {cause:Cause,next_tick_ms:u64,ticks:u8}
#[derive(Clone,Debug,PartialEq)]
pub struct State {
    profile:Profile,policy:PolicyVersion,health:[u16;9],crew:[bool;MAX_CREW],fire:Option<Fire>,
    repair_due:[Option<u64>;9],repair_cause:[Option<Cause>;9],
    observed_ms:Option<u64>,sequence:u32,seen:Vec<ModuleHit>,frozen:bool,
    fire_ticks:u32,proposed_fire_damage:u32,
}
impl State {
    /// The existing five-profile route never silently upgrades its policy.
    pub fn new(profile:Profile)->io::Result<Self> {Self::create(profile,PolicyVersion::V1)}
    /// Explicit component policy selection; this does not authorize a World,
    /// owned loadout or terminal-journal schema to accept additional vehicles.
    pub fn new_v2(profile:Profile)->io::Result<Self> {Self::create(profile,PolicyVersion::V2)}
    fn create(profile:Profile,policy:PolicyVersion)->io::Result<Self> {
        if policy==PolicyVersion::V1&&!profile.is_legacy() {return Err(bad("extended device profile requires explicit v2 policy"));}
        let index=profile.index();let seats=CREW[index];
        if seats.is_empty()||seats.len()>MAX_CREW||MAX_HP[index]==0
            ||CAPS[index].iter().any(|c|c.max==0||c.regen==0||c.regen>c.max)
            ||seats.iter().any(|seat|seat.roles==0||seat.roles&!31!=0||!(35..=42).contains(&seat.extra)) {
            return Err(bad("device source caps/primary-seat bounds"));
        }
        Ok(Self {profile,policy,health:CAPS[index].map(|c|c.max),
            crew:std::array::from_fn(|i|i<seats.len()),fire:None,repair_due:[None;9],repair_cause:[None;9],
            observed_ms:None,sequence:0,seen:Vec::new(),frozen:false,fire_ticks:0,proposed_fire_damage:0})
    }
    pub fn profile(&self)->Profile {self.profile}
    pub fn policy_version(&self)->PolicyVersion {self.policy}
    pub fn policy_revision(&self)->&'static str {self.policy.revision()}
    pub fn source_caps_sha(&self)->&'static str {self.policy.source_caps_sha()}
    pub fn policy_manifest_sha(&self)->&'static str {self.policy.manifest_sha()}
    pub fn health(&self)->[u16;9] {self.health}
    pub fn crew(&self)->&[bool] {&self.crew[..CREW[self.profile.index()].len()]}
    pub fn crew_active(&self)->bool {self.crew().iter().any(|a|*a)}
    pub fn fire_active(&self)->bool {self.fire.is_some()}
    pub fn frozen(&self)->bool {self.frozen}
    pub fn sequence(&self)->u32 {self.sequence}
    pub fn fire_ticks(&self)->u32 {self.fire_ticks}
    pub fn proposed_fire_damage(&self)->u32 {self.proposed_fire_damage}
    /// Outcome freeze does not fabricate a new fire-stop or damage event.
    pub fn freeze(&mut self) {self.frozen=true;}
    fn validate_context(&self,now:u64,h:Health)->io::Result<()> {
        if now>MAX_TIME_MS || self.observed_ms.is_some_and(|old|now<old)
            || h.max_hp!=MAX_HP[self.profile.index()] || h.hp>h.max_hp {return Err(bad("module/fire time or HP context"));} Ok(())
    }
    fn emit(&mut self,out:&mut Vec<Transition>,at_ms:u64,cause:Cause,from_fire:bool,change:Change)->io::Result<()> {
        self.sequence=self.sequence.checked_add(1).ok_or_else(||bad("module transition sequence overflow"))?;
        out.push(Transition {sequence:self.sequence,at_ms,cause,from_fire,change});Ok(())
    }
    fn device(&mut self,out:&mut Vec<Transition>,device:Device,amount:u16,at:u64,cause:Cause,from_fire:bool)->io::Result<()> {
        let index=device as usize;let max=CAPS[self.profile.index()][index].max;let before=self.health[index];let after=before.saturating_sub(amount);
        if before!=after {
            self.health[index]=after;
            self.emit(out,at,cause,from_fire,Change::Device {device,extra_index:device.extra(),max_health:max,before,after,
                before_condition:condition(before,max),after_condition:condition(after,max),repair:false})?;
            if after==0 && matches!(device,Device::Engine|Device::FuelTank) {
                self.repair_due[index]=Some(at.checked_add(MODULE_REPAIR_DELAY_MS).ok_or_else(||bad("module repair clock overflow"))?);
                self.repair_cause[index]=Some(cause);
            }
        } Ok(())
    }
    fn repair_due_devices(&mut self,out:&mut Vec<Transition>,now:u64)->io::Result<()> {
        for device in [Device::Engine,Device::FuelTank] {
            let index=device as usize;
            if self.health[index]!=0 || self.repair_due[index].is_none_or(|due|due>now) {continue;}
            let cause=self.repair_cause[index].ok_or_else(||bad("module repair cause missing"))?;
            let max=CAPS[self.profile.index()][index].max;
            let after=CAPS[self.profile.index()][index].regen;
            if after==0 || after>max {return Err(bad("module repair health bounds"));}
            self.health[index]=after;self.repair_due[index]=None;self.repair_cause[index]=None;
            self.emit(out,now,cause,true,Change::Device {device,extra_index:device.extra(),max_health:max,
                before:0,after,before_condition:Condition::Destroyed,after_condition:condition(after,max),repair:true})?;
        }
        Ok(())
    }
    fn start_fire(&mut self,out:&mut Vec<Transition>,at:u64,cause:Cause)->io::Result<()> {
        if self.fire.is_none() {
            self.fire=Some(Fire {cause,next_tick_ms:at.checked_add(FIRE_INTERVAL_MS).ok_or_else(||bad("fire clock overflow"))?,ticks:0});
            self.emit(out,at,cause,false,Change::Fire {before_active:false,after_active:true})?;
        } Ok(())
    }
    fn validate_hit(&self,hit:ModuleHit)->io::Result<()> {
        source_shell(hit.shell)?;
        if hit.cause.shot==0 || hit.cause.shot>960 || hit.cause.attacker_slot>=6 || hit.ordinal>=2
            || !hit.ignition_roll.is_finite() || !(0. ..1.).contains(&hit.ignition_roll)
            || matches!(hit.target,Target::Seat(s) if usize::from(s)>=CREW[self.profile.index()].len()) {
            return Err(bad("module hit source/identity/roll bounds"));
        }
        Ok(())
    }
    /// A caller stages this State with the World clone. Structural errors roll
    /// back the complete batch, including the seen set, journal and fire clock.
    /// Exact duplicate hits are no-ops; a conflicting replay is an error.
    pub fn apply_hits(&mut self,hits:&[ModuleHit],h:Health)->io::Result<Vec<Transition>> {
        if hits.is_empty() || hits.len()>2 {return Err(bad("module hit batch bound"));}
        let now=hits[0].at_ms;self.validate_context(now,h)?;
        let mut next=self.clone();let mut out=Vec::new();
        for &hit in hits {
            next.validate_hit(hit)?;
            if hit.at_ms!=now || hit.cause!=hits[0].cause {return Err(bad("module hit batch identity"));}
            if let Some(old)=next.seen.iter().find(|old|old.cause.shot==hit.cause.shot&&old.ordinal==hit.ordinal) {
                if *old!=hit {return Err(bad("module conflicting replay"));}continue;
            }
            if next.seen.iter().filter(|old|old.cause.shot==hit.cause.shot).count()>=2
                || next.seen.iter().any(|old|old.cause.shot==hit.cause.shot&&old.target==hit.target)
                || next.seen.len()>=MAX_HITS {return Err(bad("module hit history bound"));}
            if next.frozen || h.terminal || h.hp==0 || !next.crew_active() {next.frozen=true;continue;}
            // Root drains time effects before later hit transactions. Enforce
            // this order so journal timestamps cannot move backwards when a
            // caller catches up an old fire tick after a newer module event.
            if next.fire.is_some_and(|fire|fire.next_tick_ms<=now) {return Err(bad("drain due fire ticks before new module hits"));}
            next.seen.push(hit);
            match hit.target {
                Target::Device(device)=>{
                    next.device(&mut out,device,hit.shell.device_damage,now,hit.cause,false)?;
                    let ignition=(device==Device::Engine&&hit.shell.device_damage>=MIN_FIRE_STARTING_DAMAGE
                        &&hit.ignition_roll<ENGINE_FIRE_CHANCE[next.profile.index()])
                        || (device==Device::FuelTank&&next.health[device as usize]==0);
                    if ignition {next.start_fire(&mut out,now,hit.cause)?;}
                },
                Target::Seat(seat)=>{
                    let index=usize::from(seat);let before=next.crew[index];
                    if before {next.crew[index]=false;next.emit(&mut out,now,hit.cause,false,Change::Crew {
                        seat,extra_index:CREW[next.profile.index()][index].extra,before_active:true,after_active:false})?;}
                },
            }
        }
        next.observed_ms=Some(now);*self=next;Ok(out)
    }
    /// At most ten 1s ticks are caught up. First fire attribution is immutable;
    /// an ignition during a fire neither changes it nor extends its deadline.
    /// Local remaining HP only bounds proposals; State never owns vehicle HP.
    pub fn advance_fire(&mut self,now:u64,h:Health)->io::Result<Vec<Transition>> {
        self.validate_context(now,h)?;
        let mut next=self.clone();let mut out=Vec::new();next.observed_ms=Some(now);
        if next.frozen || h.terminal || h.hp==0 || !next.crew_active() {next.frozen=true;*self=next;return Ok(out);}
        let mut remaining=h.hp;
        while let Some(mut fire)=next.fire {
            if now<fire.next_tick_ms {break;}
            let at=fire.next_tick_ms;fire.ticks=fire.ticks.checked_add(1).ok_or_else(||bad("fire tick overflow"))?;
            if fire.ticks>MAX_FIRE_TICKS {return Err(bad("fire lifetime bound"));}
            let amount=h.max_hp.div_ceil(20).min(remaining);remaining-=amount;
            next.fire_ticks=next.fire_ticks.checked_add(1).ok_or_else(||bad("fire aggregate tick overflow"))?;
            next.proposed_fire_damage=next.proposed_fire_damage.checked_add(u32::from(amount)).ok_or_else(||bad("fire aggregate damage overflow"))?;
            next.emit(&mut out,at,fire.cause,true,Change::VehicleDamage {amount})?;
            for device in [Device::Engine,Device::FuelTank] {
                let amount=CAPS[next.profile.index()][device as usize].max.div_ceil(20);
                next.device(&mut out,device,amount,at,fire.cause,true)?;
            }
            if fire.ticks==MAX_FIRE_TICKS || remaining==0 {
                next.fire=None;next.emit(&mut out,at,fire.cause,true,Change::Fire {before_active:true,after_active:false})?;
                if remaining==0 {next.frozen=true;}break;
            }
            fire.next_tick_ms=fire.next_tick_ms.checked_add(FIRE_INTERVAL_MS).ok_or_else(||bad("fire clock overflow"))?;
            next.fire=Some(fire);
        }
        if !next.frozen && next.fire.is_none() {next.repair_due_devices(&mut out,now)?;}
        *self=next;Ok(out)
    }
    pub fn capabilities(&self)->Capabilities {
        let destroyed=|d:Device|self.health[d as usize]==0;
        let critical=|d:Device|condition(self.health[d as usize],CAPS[self.profile.index()][d as usize].max)==Condition::Critical;
        let mut wounded=0u8;for (seat,active) in self.crew().iter().enumerate(){if !active{wounded|=CREW[self.profile.index()][seat].roles;}}
        let crew_active=self.crew_active();let track=destroyed(Device::LeftTrack)||destroyed(Device::RightTrack);
        let live=crew_active&&!self.frozen;
        let mut c=Capabilities {crew_active,can_fire:live&&!destroyed(Device::Gun),
            drive_scale:if !live||track||destroyed(Device::Engine){0.}else if critical(Device::Engine){0.5}else{1.},
            steer_scale:if !live||track||destroyed(Device::Engine){0.}else if critical(Device::LeftTrack)||critical(Device::RightTrack){0.5}else{1.},
            turret_scale:if !live||destroyed(Device::TurretRotator){0.}else if critical(Device::TurretRotator){0.5}else{1.},
            aim_speed_scale:if live{1.}else{0.},dispersion_scale:if critical(Device::Gun){2.}else{1.},
            reload_scale:if destroyed(Device::AmmoBay){2.}else if critical(Device::AmmoBay){1.5}else{1.},
            view_scale:if destroyed(Device::SurveyingDevice){0.5}else{1.},radio_scale:if destroyed(Device::Radio){0.5}else{1.}};
        if wounded&4!=0 {c.drive_scale*=0.5;c.steer_scale*=0.5;}
        if wounded&2!=0 {c.aim_speed_scale*=0.5;c.dispersion_scale*=2.;}
        if wounded&8!=0 {c.reload_scale*=2.;}
        if wounded&1!=0 {c.view_scale*=0.75;}
        if wounded&16!=0 {c.radio_scale*=0.5;}
        c
    }
}

#[cfg(test)]
#[path="p06t_device_v2_tests.rs"]
mod tests_v2;
