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
// BW-01 wire codec (tools/bw01_wire_gen.py): PolicyVersion
impl crate::bw_wire::Wire for PolicyVersion {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){match self {Self::V1=>bw_o.tag(0),Self::V2=>bw_o.tag(1),}}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{match bw_i.tag()? {0=>Ok(Self::V1),1=>Ok(Self::V2),t=>crate::bw_wire::variant(t)}}
}
// end BW-01 wire codec
impl PolicyVersion {
    pub fn revision(self)->&'static str{match self{Self::V1=>POLICY,Self::V2=>POLICY_V2}}
    pub fn source_caps_sha(self)->&'static str{match self{Self::V1=>SOURCE_SHA256,Self::V2=>SOURCE_V2_SHA256}}
    pub fn manifest_sha(self)->&'static str{match self{Self::V1=>POLICY_SHA256,Self::V2=>POLICY_V2_SHA256}}
}
pub const MAX_HITS:usize=1920;
/// Module hits of one shot: two internal (ordinals 0/1) plus SHELL-02 chassis tracks
/// (ordinal 2 left, 3 right; `TRACK_ORDINALS`).
pub const MAX_SHOT_HITS:usize=4;
/// SHELL-04 classic modules (layered law): every module on the 10-caliber internal trace, at
/// ordinals 4.. after the two legacy internal and the two track ordinals.
pub const MAX_CLASSIC_SHOT_HITS:usize=16;
pub const CLASSIC_FIRST_ORDINAL:u8=4;
pub const TRACK_ORDINALS:[u8;2]=[2,3];
pub const MAX_TIME_MS:u64=3_600_000;
pub const FIRE_INTERVAL_MS:u64=1000;
pub const MAX_FIRE_TICKS:u8=10;
/// Explicit bounded LAB repair delay. The original client exposes the
/// repaired-state notifications, but the historical server timer/crew
/// modifiers are not established by the available evidence.
pub const MODULE_REPAIR_DELAY_MS:u64=1000;

// Original #717 optional_devices.xml StaticFactorDevice compact identities.
pub(crate) const TOOLBOX:u16=249;
pub(crate) const GUN_LAYING_DRIVE:u16=6649;
pub(crate) const RAMMERS:[u16;4]=[5625,5881,6137,6393];
pub(crate) const GUN_LAYING_DRIVE_FACTOR:f32=0.91;
pub(crate) const RAMMER_FACTOR:f64=0.9;
fn bad(reason:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,reason)}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Condition {Normal,Critical,Destroyed}
// BW-01 wire codec (tools/bw01_wire_gen.py): Condition
impl crate::bw_wire::Wire for Condition {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){match self {Self::Normal=>bw_o.tag(0),Self::Critical=>bw_o.tag(1),Self::Destroyed=>bw_o.tag(2),}}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{match bw_i.tag()? {0=>Ok(Self::Normal),1=>Ok(Self::Critical),2=>Ok(Self::Destroyed),t=>crate::bw_wire::variant(t)}}
}
// end BW-01 wire codec
fn condition(hp:u16,max:u16)->Condition {if hp==0{Condition::Destroyed}else if u32::from(hp)*2<=u32::from(max){Condition::Critical}else{Condition::Normal}}
/// SHELL-04 (owner 2026-11-08): damaged at 0 < HP <= maxRegenHealth, the HP a repaired module
/// comes back with as critical (#717 DEVICE_REPAIRED_TO_CRITICAL); INFERRED threshold.
fn classic_condition(hp:u16,regen:u16)->Condition {if hp==0{Condition::Destroyed}else if hp<=regen{Condition::Critical}else{Condition::Normal}}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct Cause {pub shot:u32,pub attacker_slot:u8}
// BW-01 wire codec (tools/bw01_wire_gen.py): Cause
impl crate::bw_wire::Wire for Cause {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{shot,attacker_slot}=self;W::put(shot,bw_o);W::put(attacker_slot,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{shot:W::get(bw_i)?,attacker_slot:W::get(bw_i)?})}
}
// end BW-01 wire codec
#[derive(Clone,Copy,Debug,PartialEq)]
pub struct ModuleHit {
    pub cause:Cause,pub ordinal:u8,pub at_ms:u64,pub target:Target,pub shell:Shell,
    /// World supplies and journals the deterministic draw for ignition-capable
    /// engine/fuel hits. A direct nonigniting Gun-only policy supplies canonical
    /// unused0 without consuming RNG. Replay must preserve that chosen input.
    pub ignition_roll:f64,
}
// BW-01 wire codec (tools/bw01_wire_gen.py): ModuleHit
impl crate::bw_wire::Wire for ModuleHit {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{cause,ordinal,at_ms,target,shell,ignition_roll}=self;W::put(cause,bw_o);W::put(ordinal,bw_o);W::put(at_ms,bw_o);W::put(target,bw_o);W::put(shell,bw_o);W::put(ignition_roll,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{cause:W::get(bw_i)?,ordinal:W::get(bw_i)?,at_ms:W::get(bw_i)?,target:W::get(bw_i)?,shell:W::get(bw_i)?,ignition_roll:W::get(bw_i)?})}
}
// end BW-01 wire codec
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Change {
    Device {device:Device,extra_index:u8,max_health:u16,before:u16,after:u16,before_condition:Condition,after_condition:Condition,repair:bool},
    Crew {seat:u8,extra_index:u8,before_active:bool,after_active:bool},
    Fire {before_active:bool,after_active:bool},
    /// Requested delta; caller must apply through its one HP/death ledger.
    VehicleDamage {amount:u16},
}
// BW-01 wire codec (tools/bw01_wire_gen.py): Change
impl crate::bw_wire::Wire for Change {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;match self {Self::Device{device,extra_index,max_health,before,after,before_condition,after_condition,repair}=>{bw_o.tag(0);W::put(device,bw_o);W::put(extra_index,bw_o);W::put(max_health,bw_o);W::put(before,bw_o);W::put(after,bw_o);W::put(before_condition,bw_o);W::put(after_condition,bw_o);W::put(repair,bw_o);}Self::Crew{seat,extra_index,before_active,after_active}=>{bw_o.tag(1);W::put(seat,bw_o);W::put(extra_index,bw_o);W::put(before_active,bw_o);W::put(after_active,bw_o);}Self::Fire{before_active,after_active}=>{bw_o.tag(2);W::put(before_active,bw_o);W::put(after_active,bw_o);}Self::VehicleDamage{amount}=>{bw_o.tag(3);W::put(amount,bw_o);}}}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;match bw_i.tag()? {0=>Ok(Self::Device{device:W::get(bw_i)?,extra_index:W::get(bw_i)?,max_health:W::get(bw_i)?,before:W::get(bw_i)?,after:W::get(bw_i)?,before_condition:W::get(bw_i)?,after_condition:W::get(bw_i)?,repair:W::get(bw_i)?}),1=>Ok(Self::Crew{seat:W::get(bw_i)?,extra_index:W::get(bw_i)?,before_active:W::get(bw_i)?,after_active:W::get(bw_i)?}),2=>Ok(Self::Fire{before_active:W::get(bw_i)?,after_active:W::get(bw_i)?}),3=>Ok(Self::VehicleDamage{amount:W::get(bw_i)?}),t=>crate::bw_wire::variant(t)}}
}
// end BW-01 wire codec
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct Transition {pub sequence:u32,pub at_ms:u64,pub cause:Cause,pub from_fire:bool,pub change:Change}
// BW-01 wire codec (tools/bw01_wire_gen.py): Transition
impl crate::bw_wire::Wire for Transition {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{sequence,at_ms,cause,from_fire,change}=self;W::put(sequence,bw_o);W::put(at_ms,bw_o);W::put(cause,bw_o);W::put(from_fire,bw_o);W::put(change,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{sequence:W::get(bw_i)?,at_ms:W::get(bw_i)?,cause:W::get(bw_i)?,from_fire:W::get(bw_i)?,change:W::get(bw_i)?})}
}
// end BW-01 wire codec
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct Health {pub hp:u16,pub max_hp:u16,pub terminal:bool}
/// The six once-per-battle consumables wired to the damage model in #717.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Consumable {HandExtinguisher,AutoExtinguisher,SmallMedkit,LargeMedkit,SmallRepairkit,LargeRepairkit}
impl Consumable {
    pub const ALL:[Self;6]=[Self::HandExtinguisher,Self::AutoExtinguisher,Self::SmallMedkit,Self::LargeMedkit,Self::SmallRepairkit,Self::LargeRepairkit];
    pub fn compact(self)->u16 {251+256*self as u16}
    pub fn from_item(item:u16)->Option<Self> {Self::ALL.get(usize::from(item)).copied()}
    pub fn from_compact(compact:u16)->Option<Self> {Self::ALL.into_iter().find(|kind|kind.compact()==compact)}
}

/// Frozen optional protection applied to the crew injury roll in a penetrating hit.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub(crate) struct CrewProtection {
    pub(crate) spall_liner: Option<u16>,
    pub(crate) large_medkit: bool,
}

impl CrewProtection {
    pub(crate) fn from_artefacts(devices: [u16; 3], consumables: [u16; 3]) -> Self {
        Self {
            spall_liner: devices.into_iter().find(|id| crate::profile13_v2091::SPALL_LINERS.contains(id)),
            large_medkit: consumables.contains(&Consumable::LargeMedkit.compact()),
        }
    }

    pub(crate) fn apply(self, chance: f64) -> f64 {
        // #717 AntifragmentationLining multiplies crewChanceToHitFactor by 1 - evade.
        let liner_factor = self.spall_liner.and_then(|id| {
            crate::profile13_v2091::SPALL_LINERS.iter().position(|liner| *liner == id)
        }).map_or(1., |index| [0.80, 0.75, 0.70, 0.50][index]);
        // Combine the independently documented relative reductions multiplicatively.
        let medkit_factor = if self.large_medkit { 0.85 } else { 1. };
        chance * liner_factor * medkit_factor
    }
}

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
// BW-01 wire codec (tools/bw01_wire_gen.py): Fire
impl crate::bw_wire::Wire for Fire {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{cause,next_tick_ms,ticks}=self;W::put(cause,bw_o);W::put(next_tick_ms,bw_o);W::put(ticks,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{cause:W::get(bw_i)?,next_tick_ms:W::get(bw_i)?,ticks:W::get(bw_i)?})}
}
// end BW-01 wire codec
#[derive(Clone,Debug,PartialEq)]
pub struct State {
    profile:Profile,policy:PolicyVersion,health:[u16;9],crew:[bool;MAX_CREW],fire:Option<Fire>,
    repair_due:[Option<u64>;9],repair_cause:[Option<Cause>;9],
    observed_ms:Option<u64>,sequence:u32,seen:Vec<ModuleHit>,frozen:bool,
    fire_ticks:u32,proposed_fire_damage:u32,
    /// SHELL-04 classic module rules (layered law); false keeps the LAB rules.
    classic:bool,
    /// #717 equipment XML: the mounted automatic extinguisher's passive factor.
    fire_starting_chance_factor:f64,
    /// #717 large repair kit: +10% speed on the server's module repair timer.
    module_repair_delay_ms:u64,
    optional_devices: [u16; 3],
}
// BW-01 wire codec (tools/bw01_wire_gen.py): State
impl crate::bw_wire::Wire for State {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{profile,policy,health,crew,fire,repair_due,repair_cause,observed_ms,sequence,seen,frozen,fire_ticks,proposed_fire_damage,classic,fire_starting_chance_factor,module_repair_delay_ms,optional_devices}=self;W::put(profile,bw_o);W::put(policy,bw_o);W::put(health,bw_o);W::put(crew,bw_o);W::put(fire,bw_o);W::put(repair_due,bw_o);W::put(repair_cause,bw_o);W::put(observed_ms,bw_o);W::put(sequence,bw_o);W::put(seen,bw_o);W::put(frozen,bw_o);W::put(fire_ticks,bw_o);W::put(proposed_fire_damage,bw_o);W::put(classic,bw_o);W::put(fire_starting_chance_factor,bw_o);W::put(module_repair_delay_ms,bw_o);W::put(optional_devices,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{profile:W::get(bw_i)?,policy:W::get(bw_i)?,health:W::get(bw_i)?,crew:W::get(bw_i)?,fire:W::get(bw_i)?,repair_due:W::get(bw_i)?,repair_cause:W::get(bw_i)?,observed_ms:W::get(bw_i)?,sequence:W::get(bw_i)?,seen:W::get(bw_i)?,frozen:W::get(bw_i)?,fire_ticks:W::get(bw_i)?,proposed_fire_damage:W::get(bw_i)?,classic:W::get(bw_i)?,fire_starting_chance_factor:W::get(bw_i)?,module_repair_delay_ms:W::get(bw_i)?,optional_devices:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl State {
    /// The existing five-profile route never silently upgrades its policy.
    pub fn new(profile:Profile)->io::Result<Self> {Self::create(profile,PolicyVersion::V1)}
    /// Explicit component policy selection; this does not authorize a World,
    /// owned loadout or terminal-journal schema to accept additional vehicles.
    pub fn new_v2(profile:Profile)->io::Result<Self> {Self::create(profile,PolicyVersion::V2)}
    fn create(profile:Profile,policy:PolicyVersion)->io::Result<Self> {
        // Generated (BATTLE-ANY) profiles carry their own registry caps and use the owned v1 route;
        // only the curated extended WT/FV profiles need the explicit v2 policy.
        if policy==PolicyVersion::V1&&!profile.is_legacy()&&!matches!(profile,Profile::Generated(_)) {return Err(bad("extended device profile requires explicit v2 policy"));}
        let seats=profile.crew();
        if seats.is_empty()||seats.len()>MAX_CREW||profile.max_hp()==0
            ||profile.caps().iter().any(|c|c.max==0||c.regen==0||c.regen>c.max)
            ||seats.iter().any(|seat|seat.roles==0||seat.roles&!31!=0||!(35..=42).contains(&seat.extra)) {
            return Err(bad("device source caps/primary-seat bounds"));
        }
        Ok(Self {profile,policy,health:profile.caps().map(|c|c.max),
            crew:std::array::from_fn(|i|i<seats.len()),fire:None,repair_due:[None;9],repair_cause:[None;9],
            observed_ms:None,sequence:0,seen:Vec::new(),frozen:false,fire_ticks:0,proposed_fire_damage:0,classic:false,
            fire_starting_chance_factor:1.,module_repair_delay_ms:MODULE_REPAIR_DELAY_MS,optional_devices:[0;3]})
    }
    pub fn profile(&self)->Profile {self.profile}
    /// SHELL-04: classic module rules before any hit (a later switch would rewrite history).
    pub fn enable_classic(&mut self)->io::Result<()> {
        if self.sequence!=0||!self.seen.is_empty() {return Err(bad("classic module rules after hits"));}
        self.classic=true;Ok(())
    }
    pub fn classic(&self)->bool {self.classic}
    pub fn configure_artefacts(&mut self,devices:[u16;3],consumables:[u16;3])->io::Result<()> {
        if self.frozen || self.observed_ms.is_some() || self.health != self.caps().map(|cap| cap.max) {
            return Err(bad("artefact setup after battle damage"));
        }
        self.optional_devices = devices;
        self.health = self.caps().map(|cap| cap.max);
        self.fire_starting_chance_factor=if consumables.contains(&Consumable::AutoExtinguisher.compact()){0.9}else{1.};
        let toolbox=if devices.contains(&TOOLBOX){125}else{100};
        let repair_kit=if consumables.contains(&Consumable::LargeRepairkit.compact()){110}else{100};
        self.module_repair_delay_ms=(MODULE_REPAIR_DELAY_MS*10_000).div_ceil(toolbox*repair_kit);
        Ok(())
    }
    /// TURPHYS-01 test_lab turret test: a passive test bot's ammo bay starts at 1 HP (before any
    /// hit), so the first penetrating hit that reaches it destroys it and the real rack path runs.
    pub fn weaken_ammo_bay_for_turret_test(&mut self)->io::Result<()> {
        if self.sequence!=0||!self.seen.is_empty() {return Err(bad("turret test ammo bay after hits"));}
        self.health[Device::AmmoBay as usize]=1;Ok(())
    }
    /// Module hits of one shot (target, ordinal), in application order.
    pub fn shot_hits(&self,shot:u32)->Vec<(Target,u8)> {self.seen.iter().filter(|h|h.cause.shot==shot).map(|h|(h.target,h.ordinal)).collect()}
    /// This shot already hit this module or seat (tracks of a later explosion are skipped).
    pub fn hit_by_shot(&self,shot:u32,target:Target)->bool {self.seen.iter().any(|h|h.cause.shot==shot&&h.target==target)}
    fn condition_of(&self,index:usize,hp:u16)->Condition {
        let caps=self.caps()[index];
        if self.classic {classic_condition(hp,caps.regen)} else {condition(hp,caps.max)}
    }
    fn shot_hit_limit(&self)->usize {if self.classic {MAX_CLASSIC_SHOT_HITS} else {MAX_SHOT_HITS}}
    pub fn policy_version(&self)->PolicyVersion {self.policy}
    pub fn policy_revision(&self)->&'static str {self.policy.revision()}
    pub fn source_caps_sha(&self)->&'static str {self.policy.source_caps_sha()}
    pub fn policy_manifest_sha(&self)->&'static str {self.policy.manifest_sha()}
    pub fn health(&self)->[u16;9] {self.health}
    pub fn caps(&self) -> [crate::p06t_device_caps::Cap; 9] { self.profile.equipped_caps(self.optional_devices) }
    pub(crate) fn device_condition(&self, device: Device) -> Condition {self.condition_of(device as usize, self.health[device as usize])}
    pub fn crew(&self)->&[bool] {&self.crew[..self.profile.crew().len()]}
    pub fn crew_active(&self)->bool {self.crew().iter().any(|a|*a)}
    pub fn fire_active(&self)->bool {self.fire.is_some()}
    /// Public state extras of the vehicle (#717 Vehicle.publicStateModifiers):
    /// fire (4) and each destroyed track (30/31), which the client's
    /// TrackHealth extra shows as a crashed track on the model.
    pub fn public_modifiers(&self)->Vec<u8> {
        let mut out=Vec::new();if self.fire_active(){out.push(4);}
        for track in [Device::LeftTrack,Device::RightTrack] {if self.health[track as usize]==0{out.push(track.extra());}}
        out
    }
    pub fn frozen(&self)->bool {self.frozen}
    pub fn sequence(&self)->u32 {self.sequence}
    pub fn fire_ticks(&self)->u32 {self.fire_ticks}
    pub fn proposed_fire_damage(&self)->u32 {self.proposed_fire_damage}
    /// Outcome freeze does not fabricate a new fire-stop or damage event.
    pub fn freeze(&mut self) {self.frozen=true;}
    fn validate_context(&self,now:u64,h:Health)->io::Result<()> {
        if now>MAX_TIME_MS || self.observed_ms.is_some_and(|old|now<old)
            || h.max_hp!=self.profile.max_hp() || h.hp>h.max_hp {return Err(bad("module/fire time or HP context"));} Ok(())
    }
    fn emit(&mut self,out:&mut Vec<Transition>,at_ms:u64,cause:Cause,from_fire:bool,change:Change)->io::Result<()> {
        self.sequence=self.sequence.checked_add(1).ok_or_else(||bad("module transition sequence overflow"))?;
        out.push(Transition {sequence:self.sequence,at_ms,cause,from_fire,change});Ok(())
    }
    fn device(&mut self,out:&mut Vec<Transition>,device:Device,amount:u16,at:u64,cause:Cause,from_fire:bool)->io::Result<()> {
        let index=device as usize;let max=self.caps()[index].max;let before=self.health[index];let after=before.saturating_sub(amount);
        if before!=after {
            self.health[index]=after;
            self.emit(out,at,cause,from_fire,Change::Device {device,extra_index:device.extra(),max_health:max,before,after,
                before_condition:self.condition_of(index,before),after_condition:self.condition_of(index,after),repair:false})?;
            if after==0 && device.repairable() {
                self.repair_due[index]=Some(at.checked_add(self.module_repair_delay_ms).ok_or_else(||bad("module repair clock overflow"))?);
                self.repair_cause[index]=Some(cause);
            }
        } Ok(())
    }
    /// CONTENT-0 regulator wear is an owner module event. It plays the normal
    /// engine damaged/destroyed state and cannot ignite or damage vehicle HP.
    pub(super) fn apply_rpm_limiter_damage(&mut self,amount:u16,at_ms:u64,owner:u8,h:Health)->io::Result<Vec<Transition>> {
        self.validate_context(at_ms,h)?;
        if amount==0 || self.frozen || h.terminal || h.hp==0 || !self.crew_active() {return Ok(Vec::new());}
        let mut next=self.clone();
        let mut out=Vec::new();
        next.device(&mut out,Device::Engine,amount,at_ms,Cause{shot:0,attacker_slot:owner},false)?;
        next.observed_ms=Some(at_ms);
        *self=next;
        Ok(out)
    }
    /// A repaired module comes back damaged (#717 DEVICE_REPAIRED_TO_CRITICAL, code 18): it is at its
    /// source maxRegenHealth, below maxHealth. INFERRED from the client codes; the historical server
    /// timer and full-repair rule are UNKNOWN (LAB).
    fn repair_due_devices(&mut self,out:&mut Vec<Transition>,now:u64)->io::Result<()> {
        let caps = self.caps();
        for device in Device::ALL.into_iter().filter(|d|d.repairable()) {
            let index=device as usize;
            if self.health[index]!=0 || self.repair_due[index].is_none_or(|due|due>now) {continue;}
            let cause=self.repair_cause[index].ok_or_else(||bad("module repair cause missing"))?;
            let max=caps[index].max;
            let after=caps[index].regen;
            if after==0 || after>max {return Err(bad("module repair health bounds"));}
            self.health[index]=after;self.repair_due[index]=None;self.repair_cause[index]=None;
            self.emit(out,now,cause,true,Change::Device {device,extra_index:device.extra(),max_health:max,
                before:0,after,before_condition:Condition::Destroyed,after_condition:Condition::Critical,repair:true})?;
        }
        Ok(())
    }
    /// Shot 0 identifies an owner's repair/heal. A fire stop retains the
    /// ignition cause so the damage feed can sum the burn that just ended.
    pub fn restore(&mut self,kind:Consumable,extra:u16,at:u64,owner:u8,h:Health)->io::Result<Vec<Transition>> {
        self.validate_context(at,h)?;
        if self.frozen||h.terminal||h.hp==0||!self.crew_active(){return Ok(Vec::new());}
        let cause=Cause{shot:0,attacker_slot:owner};let mut next=self.clone();let mut events=Vec::new();
        match kind {
            Consumable::HandExtinguisher|Consumable::AutoExtinguisher if extra==1=>{
                if let Some(fire)=next.fire.take(){
                    next.emit(&mut events,at,fire.cause,false,Change::Fire{before_active:true,after_active:false})?;
                    next.defer_repairs_after_fire(at)?;
                }
            },
            Consumable::SmallMedkit|Consumable::LargeMedkit=>{
                let all=kind==Consumable::LargeMedkit;
                for (seat,source) in next.profile.crew().iter().enumerate(){
                    if !next.crew[seat]&&(if all{extra==1}else{u16::from(source.extra)==extra}){
                        next.crew[seat]=true;
                        next.emit(&mut events,at,cause,false,Change::Crew{seat:seat as u8,extra_index:source.extra,
                            before_active:false,after_active:true})?;
                    }
                }
            },
            Consumable::SmallRepairkit|Consumable::LargeRepairkit=>{
                let all=kind==Consumable::LargeRepairkit;
                let eligible=|d:Device| next.condition_of(d as usize,next.health[d as usize])!=Condition::Normal;
                if all&&(extra!=1||!Device::ALL.into_iter().any(eligible)){return Ok(events);}
                let caps=next.caps();
                for device in Device::ALL{
                    let index=device as usize;let before=next.health[index];let after=caps[index].max;
                    let before_condition=next.condition_of(index,before);
                    if before==after||!all&&(extra!=u16::from(device.extra())||before_condition==Condition::Normal){continue;}
                    next.health[index]=after;next.repair_due[index]=None;next.repair_cause[index]=None;
                    next.emit(&mut events,at,cause,false,Change::Device{device,extra_index:device.extra(),max_health:after,
                        before,after,before_condition,after_condition:Condition::Normal,repair:true})?;
                }
            },
            _=>{},
        }
        if !events.is_empty(){next.observed_ms=Some(at);*self=next;}
        Ok(events)
    }
    /// A module destroyed by the fire is not repaired at the same instant as
    /// the last fire tick.  The native client starts a separate repair clock
    /// after the fire has stopped; when a coarse server advance catches up all
    /// ticks in one call, keep that boundary explicit instead of restoring the
    /// engine/fuel tank immediately in the same transaction.
    fn defer_repairs_after_fire(&mut self,at:u64)->io::Result<()> {
        let due=at.checked_add(self.module_repair_delay_ms)
            .ok_or_else(||bad("module post-fire repair clock overflow"))?;
        for device in Device::ALL.into_iter().filter(|d|d.repairable()) {
            let index=device as usize;
            if self.health[index]==0 && self.repair_due[index].is_some() {
                self.repair_due[index]=Some(self.repair_due[index].unwrap().max(due));
            }
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
        // RES-30: any attacker/shot of a 30-actor battle (was slot<6, shot<=960).
        use crate::gateway091::shared::model::{MAX_ACTORS,MAX_BATTLE_SHOTS};
        if hit.cause.shot==0 || hit.cause.shot as usize>MAX_BATTLE_SHOTS || usize::from(hit.cause.attacker_slot)>=MAX_ACTORS || usize::from(hit.ordinal)>=self.shot_hit_limit()
            || !hit.ignition_roll.is_finite() || !(0. ..1.).contains(&hit.ignition_roll)
            || matches!(hit.target,Target::Seat(s) if usize::from(s)>=self.profile.crew().len())
            || hit.ordinal==TRACK_ORDINALS[0]&&hit.target!=Target::Device(Device::LeftTrack)
            || hit.ordinal==TRACK_ORDINALS[1]&&hit.target!=Target::Device(Device::RightTrack) {
            return Err(bad("module hit source/identity/roll bounds"));
        }
        Ok(())
    }
    /// A caller stages this State with the World clone. Structural errors roll
    /// back the complete batch, including the seen set, journal and fire clock.
    /// Exact duplicate hits are no-ops; a conflicting replay is an error.
    pub fn apply_hits(&mut self,hits:&[ModuleHit],h:Health)->io::Result<Vec<Transition>> {self.apply_with(hits,None,h)}
    /// SHELL-04 (owner 2026-11-08): external modules (tracks, gun) of an HE/HESH explosion take an
    /// explicit device damage each (the shell's device damage scaled by the splash falloff).
    pub fn apply_explosion_hits(&mut self,hits:&[ModuleHit],amounts:&[u16],h:Health)->io::Result<Vec<Transition>> {
        if hits.iter().any(|hit|!matches!(hit.target,Target::Device(Device::LeftTrack|Device::RightTrack|Device::Gun))) {
            return Err(bad("explosion module hit bounds"));
        }
        self.apply_classic_hits(hits,amounts,h)
    }
    /// SHELL-04 (owner 2026-11-08): classic hits with their module damage given (the shell's device
    /// damage times the shot's damage roll, within +-25 %; seats ignore it).
    pub fn apply_classic_hits(&mut self,hits:&[ModuleHit],amounts:&[u16],h:Health)->io::Result<Vec<Transition>> {
        if !self.classic||amounts.len()!=hits.len()||hits.iter().zip(amounts).any(|(hit,a)|*a==0
            ||u32::from(*a)*4>u32::from(hit.shell.device_damage)*5+2) {
            return Err(bad("classic module hit damage bounds"));
        }
        self.apply_with(hits,Some(amounts),h)
    }
    fn apply_with(&mut self,hits:&[ModuleHit],amounts:Option<&[u16]>,h:Health)->io::Result<Vec<Transition>> {
        if hits.is_empty() || hits.len()>if self.classic {MAX_CLASSIC_SHOT_HITS} else {2} {return Err(bad("module hit batch bound"));}
        let now=hits[0].at_ms;self.validate_context(now,h)?;
        let mut next=self.clone();let mut out=Vec::new();
        for (index,&hit) in hits.iter().enumerate() {
            next.validate_hit(hit)?;
            if hit.at_ms!=now || hit.cause!=hits[0].cause {return Err(bad("module hit batch identity"));}
            if let Some(old)=next.seen.iter().find(|old|old.cause.shot==hit.cause.shot&&old.ordinal==hit.ordinal) {
                if *old!=hit {return Err(bad("module conflicting replay"));}continue;
            }
            if next.seen.iter().filter(|old|old.cause.shot==hit.cause.shot).count()>=next.shot_hit_limit()
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
                    let amount=amounts.map_or(hit.shell.device_damage,|a|a[index]);
                    next.device(&mut out,device,amount,now,hit.cause,false)?;
                    let ignition=(device==Device::Engine&&hit.shell.device_damage>=MIN_FIRE_STARTING_DAMAGE
                        &&hit.ignition_roll<next.profile.engine_fire_chance()*next.fire_starting_chance_factor)
                        || (device==Device::FuelTank&&next.health[device as usize]==0);
                    if ignition {next.start_fire(&mut out,now,hit.cause)?;}
                },
                Target::Seat(seat)=>{
                    let index=usize::from(seat);let before=next.crew[index];
                    if before {next.crew[index]=false;next.emit(&mut out,now,hit.cause,false,Change::Crew {
                        seat,extra_index:next.profile.crew()[index].extra,before_active:true,after_active:false})?;}
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
                let amount=next.caps()[device as usize].max.div_ceil(20);
                next.device(&mut out,device,amount,at,fire.cause,true)?;
            }
            if fire.ticks==MAX_FIRE_TICKS || remaining==0 {
                next.fire=None;next.emit(&mut out,at,fire.cause,true,Change::Fire {before_active:true,after_active:false})?;
                next.defer_repairs_after_fire(at)?;
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
        let critical=|d:Device|self.condition_of(d as usize,self.health[d as usize])==Condition::Critical;
        let mut wounded=0u8;for (seat,active) in self.crew().iter().enumerate(){if !active{wounded|=self.profile.crew()[seat].roles;}}
        let crew_active=self.crew_active();let track=destroyed(Device::LeftTrack)||destroyed(Device::RightTrack);
        let live=crew_active&&!self.frozen;
        let mut c=Capabilities {crew_active,can_fire:live&&!destroyed(Device::Gun),
            drive_scale:if !live||track||destroyed(Device::Engine){0.}else if critical(Device::Engine){0.5}else{1.},
            // A damaged (critical) track keeps full steering: only a destroyed one immobilises. The earlier LAB
            // 0.5 duty-cycled the steer row and a repaired (now damaged) track could not pivot (owner 2026-11-04).
            steer_scale:if !live||track||destroyed(Device::Engine){0.}else{1.},
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

#[cfg(test)]
#[path="module_classic_tests.rs"]
mod classic_tests;
