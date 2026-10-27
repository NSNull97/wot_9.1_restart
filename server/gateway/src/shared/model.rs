//! Two temporary allied laboratory actors. No native IDs, client poses, clocks
//! or garage inventory enter the simulation. Kinematics are deliberately not P05.
use std::{io, sync::Arc, time::{Duration, Instant}};
use crate::battle091::fire;
use super::{ram_proof,aim, ap, destructible, fragiles, geometry, impact, terrain, materials::MaterialFacts, projectile::Projectile, vehicle_profile::VehicleKind};

pub const CAPACITY: usize = 2;
/// ARENA-01: the one type bound for an arena roster (15v15 = 30, client
/// `arena_defs/_default_.xml` maxPlayersInTeam=15). Native wire stays at
/// `wire::MAX_NATIVE_ACTORS`; every module refers to this constant.
pub const MAX_ACTORS: usize = 30;
pub const LIFETIME: Duration = Duration::from_secs(3600);
pub const STEP: Duration = Duration::from_millis(100);
pub const MAX_COMMANDS: usize = 32;
/// Storage ceiling; each immutable profile enforces its own admission limit.
pub const MAX_SHOTS: usize = CAPACITY * 96;
pub const MAX_AMMO_PER_ACTOR: usize = 160;
pub const MAX_BATTLE_SHOTS: usize = MAX_ACTORS * MAX_AMMO_PER_ACTOR;
/// Explicit laboratory policy: retained stock geometry blocks AP at a wreck.
/// No penetration, material thickness or additional damage is inferred.
pub const WRECK_POLICY_REVISION: &str = "test_lab-ms1-wreck-block-v1";
pub fn wreck_policy_revision_for(kind:VehicleKind)->&'static str { match kind {
    VehicleKind::Ms1=>WRECK_POLICY_REVISION,VehicleKind::Is7=>"test_lab-is7-wreck-block-v1",
    VehicleKind::T26|VehicleKind::T34|VehicleKind::T3485=>"test_lab-curated-stock-wreck-block-v1",
    VehicleKind::Wt128|VehicleKind::Fv183=>"test_lab-p06t-extended-source-wreck-block-v1",
    VehicleKind::Generated(_)=>"test_lab-battle-any-generated-wreck-block-v1",
} }
pub const SPAWN: [f32; 3] = [-58.499908, 33.770267, -445.81305];

/// Report the invariant's call site, including lazy Option error branches.
/// Keep calls inside closures: coercing this function to a pointer loses its caller.
#[track_caller]
pub fn bad() -> io::Error {
    let site = std::panic::Location::caller();
    io::Error::new(io::ErrorKind::InvalidData,
        format!("shared laboratory contract at {}:{}:{}", site.file(), site.line(), site.column()))
}

#[derive(Clone, Debug, PartialEq)]
pub struct Identity { pub account: String, pub database: i32, pub name: String }

/// `speed_percent` carries the native partial cruise stage (100, 50 or 25).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Input { pub throttle: i8, pub steer: i8, pub speed_percent: u8 }
impl Input {
    pub const STOP: Self = Self { throttle: 0, steer: 0, speed_percent: 100 };
    fn valid(&self) -> bool {
        (-1..=1).contains(&self.throttle) && (-1..=1).contains(&self.steer)
            && crate::map_drive_worker091::partial_cruise_valid(self.throttle, false, self.speed_percent)
    }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Actor {
    pub identity: Identity,
    pub session: Option<u32>,
    pub ready: bool,
    pub health: i16,
    pub position: [f32; 3],
    /// Server-authoritative hull orientation in worker order: yaw, pitch, roll.
    pub direction: [f32; 3],
    pub yaw: f32,
    pub speed: f32,
    pub input: Input,
    pub fire: fire::State,
    pub aim: aim::State,
    pub mileage_metres: f64,
    origin: [f32; 3],
    vehicle_kind: VehicleKind,
    owned_loadout: Option<crate::battle091::profile13::FrozenLoadout>,
    pub owned_v2:Option<crate::profile13_v2091::Frozen>,
    pub owned_loss:Option<crate::profile13_loss091::FrozenLoss>,
    pub owned_hold:Option<crate::profile13_hold091::FrozenHold>,
    pub devices:Option<crate::p06t_device_state::State>,
}

impl Actor {
    pub fn vehicle_kind(&self) -> VehicleKind { self.vehicle_kind }
    pub fn crew_active(&self)->bool{self.health>0&&self.devices.as_ref().is_none_or(|state|state.crew_active())}
    pub fn alive(&self)->bool{self.crew_active()}
    pub fn public_modifiers(&self)->Vec<u8>{if self.devices.as_ref().is_some_and(|state|state.fire_active()){vec![4]}else{Vec::new()}}
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Command { Move(Input), Aim(aim::Intent), Fire(fire::Command), Armament(crate::p06t_armament091::Command), Leave }

#[derive(Clone,Debug,PartialEq)]
pub struct DamageRecord {
    pub sequence:u32,pub tick:u32,pub attacker:usize,pub target:usize,pub shot:u32,pub reason:u8,
    pub health_before:i16,pub health_after:i16,pub crew_before:bool,pub crew_after:bool,
    pub direct:bool,pub pierced:bool,
}
impl DamageRecord {pub fn lethal(&self)->bool{self.crew_before&&(!self.crew_after||self.health_after==0)}}
pub const MAX_DAMAGE_EVENTS:usize=MAX_BATTLE_SHOTS*16;
#[path="result_spots.rs"]
pub(super) mod result_spots;
#[path="p06t_world.rs"]
pub(super) mod p06t;
#[path="p06t_extended_world.rs"]
pub(crate) mod extended;

#[derive(Clone, Debug, PartialEq)]
pub struct RamDamageRecord { pub sequence:u32,pub tick:u32,pub domain_tick:u32,pub attacker:usize,pub target:usize,pub pair:(usize,usize),pub energy_j:f64,pub closing_speed:f64,pub health_before:i16,pub health_after:i16 }
/// Terminal cause shared by HP publication, writer state and Results8. The tick
/// is always the domain clock; a worker's fixed-step counter is not that clock.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct DeathCause { pub attacker:usize,pub reason:u8,pub tick:u32 }

/// One accepted server action, independent of native entity/method IDs. The
/// laboratory never replenishes ammo, so its complete event history is bounded.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Shot { pub sequence: u32, pub slot: usize, pub tick: u32 }

#[derive(Clone, Debug, PartialEq)]
pub struct Contact {
    pub shot: u32, pub target_slot: usize, pub tick: u32,
    pub segment_start: [f32; 3], pub segment_end: [f32; 3], pub segment_seconds: f32,
    pub endpoint: [f32; 3], pub target_position: [f32; 3], pub target_direction: [f32; 3],
    pub target_aim: [f32; 2], pub triangle: super::collision::Candidate,
    pub geometry_revision: String, pub transform_revision: String,
    pub material_facts: MaterialFacts,
}

/// Committed authoritative outcome. No native IDs or client damage claims.
#[derive(Clone, Debug, PartialEq)]
pub enum ImpactOutcome { Ap(ap::Resolution), Mixed(crate::p06t_damage::Resolution), WreckBlocked }

#[derive(Clone, Debug, PartialEq)]
pub struct AppliedImpact {
    pub shot: u32, pub attacker: usize, pub target: usize, pub tick: u32,
    pub outcome: ImpactOutcome,
    pub health_before: i16, pub health_after: i16,
    pub segment: Option<geometry::ImpactSegment>,
}

/// A surface-only terminal result; never an armor/HP outcome.
#[derive(Clone, Debug, PartialEq)]
pub struct TerrainContact {
    pub shot: u32, pub shooter: usize, pub tick: u32,
    pub hit: terrain::Hit,
    pub segment_start: [f32; 3], pub segment_end: [f32; 3],
    pub direction: [f32; 3],
}

/// MAPS-02 overlap of one hull with a non-blocking falling atom trigger, from
/// the private IPC7 worker. Only the catalog object ID, the manifold geometry,
/// the pre-step hull velocity and the server-pinned profile mass enter.
#[derive(Clone, Debug, PartialEq)]
pub struct ColumnContactInput {
    pub object_id: u32,
    pub shooter: usize,
    pub substep: u8,
    pub point: [f32; 3],
    pub normal: [f32; 3],
    pub velocity: [f32; 3],
    pub mass_kg: f32,
}

/// A bounded contact candidate imported from one private physics worker. The
/// worker's body IDs never cross this boundary; only the hash-bound catalog
/// object ID and validated contact geometry enter the domain state.
#[derive(Clone, Debug, PartialEq)]
pub struct VehicleContactInput {
    pub object_id: u32,
    pub substep: u8,
    pub point: [f32; 3],
    pub normal: [f32; 3],
    pub velocity: [f32; 3],
    /// Server-pinned worker descriptor mass. It is never accepted from a
    /// client frame; the integrated runtime copies the validated map config.
    pub mass_kg: f32,
    pub kind: String,
    pub shooter: usize,
    pub proof: Option<ram_proof::ContactProof>,
}
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct TankContactInput { pub slot_a:usize,pub slot_b:usize,pub substep:u8,pub point:[f32;3],pub normal:[f32;3],pub relative_velocity:[f32;3] }

#[derive(Clone)]
pub struct World {
    pub id: u64,
    vehicle_kind: VehicleKind,
    expected_actors: usize,
    team_plan:Option<super::p10b_team_plan::TeamPlan>,
    mixed_profiles: bool,
    pub map: crate::map_profile091::MapId,
    pub actors: Vec<Actor>,
    pub started: Option<Instant>,
    last: Instant,
    pub tick: u32,
    pub shots: Vec<Shot>,
    pub projectiles: Vec<Projectile>,
    pub impact: impact::Trace,
    /// Enabled only by the profile13 battle service; legacy laboratory tests
    /// preserve their accepted unrestricted drive route.
    pub lifecycle: Option<super::lifecycle::State>,
    pub lifecycle_created_unix: Option<u32>,
    result_spots:Option<Vec<result_spots::SpotRecord>>,
    result_spot_tick:Option<u32>,
    original_spotting: Option<super::spotting::State>,
    mixed_ammo:bool,
    ammo_detonation:Option<super::ammo_detonation::Ledger>,
    turret_flights:Vec<super::ammo_detonation::Flight>,
    turret_visual_ms:Option<u64>,
    extended_lab:bool,
    owner_hold:bool,
    /// SPAWN-15: place teams on `team_spawn` formations instead of LAB lanes.
    team_base_spawn:bool,
    lab_loadouts:[Option<extended::LabLoadout>;MAX_ACTORS],
    pub damage_events:Vec<DamageRecord>,
    pub device_events:Vec<(usize,crate::p06t_device_state::Transition)>,
    rng_state:u64,
    pub rng_draws:Vec<(u32,usize,u8,u64)>,
    geometry: Option<Arc<geometry::Bundle>>,
    geometries: [Option<Arc<geometry::Bundle>>; 7],
    /// BATTLE-ANY: bundles of generated kinds bound to this mixed template.
    generated_geometries: std::collections::BTreeMap<usize,Arc<geometry::Bundle>>,
    pub contacts: Vec<Contact>,
    ap_test_lab: bool,
    pub impacts: Vec<AppliedImpact>,
    terrain: Option<Arc<terrain::Terrain>>,
    pub terrain_contacts: Vec<TerrainContact>,
    pub ram_damage_events: Vec<RamDamageRecord>,
    active_ram_pairs: std::collections::BTreeSet<(usize,usize)>,
    destructible: Option<destructible::State>,
    pub fragiles: Option<fragiles::State>,
    contact_sources:[Option<ram_proof::Source>;MAX_ACTORS],
    contact_sequences:[u32;MAX_ACTORS],
}

impl World {
    pub(super) fn death_cause(&self,target:usize)->io::Result<Option<DeathCause>> {
        let actor=self.actors.get(target).ok_or_else(bad)?;
        let mut found=None;
        let projectile=self.damage_events.iter().filter(|e|self.mixed_ammo&&e.target==target&&e.lethal())
            .map(|e|(DeathCause{attacker:e.attacker,reason:e.reason,tick:e.tick},e.health_after));
        let ap=self.impacts.iter().filter(|e|!self.mixed_ammo&&e.target==target&&e.health_before>0&&e.health_after==0)
            .map(|e|(DeathCause{attacker:e.attacker,reason:0,tick:e.tick},e.health_after));
        let ram=self.ram_damage_events.iter().filter(|e|e.target==target&&e.health_before>0&&e.health_after==0)
            .map(|e|(DeathCause{attacker:e.attacker,reason:2,tick:e.domain_tick},e.health_after));
        for(cause,hp)in projectile.chain(ap).chain(ram){
            if found.is_some()||cause.attacker>=self.actors.len()||cause.reason>10||cause.tick<1000
                ||hp!=actor.health{return Err(bad());}
            found=Some(cause);
        }
        if actor.alive()!=found.is_none(){return Err(bad());}
        Ok(found)
    }
    pub(super) fn health_cause(&self,target:usize)->io::Result<Option<(usize,u8)>> {
        let actor=self.actors.get(target).ok_or_else(bad)?;
        if !(0..=actor.vehicle_kind().max_health()).contains(&actor.health){return Err(bad());}
        // Crew-only terminal transitions can retain the HP of an earlier ram.
        // Their actual lethal journal entry owns the final terminal packet.
        if !actor.alive(){return self.death_cause(target).map(|c|c.map(|c|(c.attacker,c.reason)));}
        if actor.health==actor.vehicle_kind().max_health(){return Ok(None);}
        let projectile=self.damage_events.iter().filter(|e|self.mixed_ammo&&e.target==target
            &&e.health_before>e.health_after&&e.health_after==actor.health).map(|e|(e.attacker,e.reason));
        let ap=self.impacts.iter().filter(|e|!self.mixed_ammo&&e.target==target
            &&e.health_before>e.health_after&&e.health_after==actor.health).map(|e|(e.attacker,0));
        let ram=self.ram_damage_events.iter().filter(|e|e.target==target
            &&e.health_before>e.health_after&&e.health_after==actor.health).map(|e|(e.attacker,2));
        let mut found=None;
        for cause in projectile.chain(ap).chain(ram){
            if found.is_some()||cause.0>=self.actors.len()||cause.1>10{return Err(bad());}
            found=Some(cause);
        }
        found.map(Some).ok_or_else(bad)
    }
    /// Only the pristine, source-bound template may seed another battle.
    pub fn fresh_battle(&self, id: u64, now: Instant) -> io::Result<Self> {
        if id == 0 || id == self.id || self.started.is_some() || !self.actors.is_empty()
            || !self.shots.is_empty() || !self.impact.events().is_empty() || self.scene_version() != 0
            || !self.damage_events.is_empty() || !self.device_events.is_empty() || !self.rng_draws.is_empty()
            || self.result_spots.as_ref().is_some_and(|rows|!rows.is_empty()) || self.result_spot_tick.is_some()
            ||self.ammo_detonation.as_ref().is_some_and(|ledger|!ledger.is_pristine())
            ||!self.turret_flights.is_empty()||self.turret_visual_ms.is_some()
            || !self.ram_damage_events.is_empty() || !self.active_ram_pairs.is_empty() {
            return Err(bad());
        }
        let mut next = self.clone();
        next.id = id; next.last = now;next.rng_state=id;
        Ok(next)
    }

    /// Bounded fault evidence, with resource identity rather than copied meshes.
    /// The original input/cadence journal remains in the service/capture logs.
    pub fn failure_snapshot(&self) -> serde_json::Value {
        let events = self.impact.events();
        let trace_from = events.len().saturating_sub(64);
        let mut snapshot=serde_json::json!({
            "battle":self.id.to_string(), "map":self.map.asset(), "vehicle":self.vehicle_kind.label(),
            "tick":self.tick, "started":self.started.is_some(),"mixed_profiles":self.mixed_profiles,"mixed_ammo":self.mixed_ammo,"expected_actors":self.expected_actors,
            "damage_event_count":self.damage_events.len(),"device_event_count":self.device_events.len(),
            "ammo_detonation_policy":self.ammo_detonation.as_ref().map(|_|super::ammo_detonation::POLICY),
            "ammo_detonations":self.ammo_detonations().iter().map(|event|format!("{event:?}")).collect::<Vec<_>>(),
            "turret_visual_ms":self.turret_visual_ms,"turret_flights":self.turret_flights.iter().map(|flight|format!("{flight:?}")).collect::<Vec<_>>(),
            "damage_tail":self.damage_events.iter().rev().take(64).map(|event|format!("{event:?}")).collect::<Vec<_>>(),
            "device_tail":self.device_events.iter().rev().take(64).map(|event|format!("{event:?}")).collect::<Vec<_>>(),
            "rng_policy":"test_lab.splitmix64.v1","rng_initial_seed":self.id.to_string(),"rng_state":self.rng_state.to_string(),
            "rng_draw_count":self.rng_draws.len(),"rng_tail":self.rng_draws.iter().rev().take(64).map(|event|format!("{event:?}")).collect::<Vec<_>>(),
            "actors":self.actors.iter().map(|a|serde_json::json!({
                "account":a.identity.account,"session":a.session,"ready":a.ready,"health":a.health,"kind":a.vehicle_kind.label(),
                "position":a.position,"direction":a.direction,"speed":a.speed,
                "input":format!("{:?}",a.input),"fire":format!("{:?}",a.fire),"aim":format!("{:?}",a.aim),
                "devices":a.devices.as_ref().map(|state|format!("{state:?}"))
            })).collect::<Vec<_>>(),
            "shots":self.shots.iter().map(|s|serde_json::json!({"sequence":s.sequence,"slot":s.slot,"tick":s.tick})).collect::<Vec<_>>(),
            "projectiles":self.projectiles.iter().map(|p|serde_json::json!({
                "sequence":p.sequence,"slot":p.slot,"origin":p.origin,"velocity":p.velocity,
                "shell":p.shell.map(|shell|shell.compact_descr),
                "gravity":p.gravity,"max_distance":p.max_distance,"terminal":p.terminal,"stopped":p.stopped,
                "launch_ms":self.started.and_then(|start|p.launched.checked_duration_since(start)).map(|d|d.as_millis()),
                "flight_ms":p.flight_time.as_millis()
            })).collect::<Vec<_>>(),
            "geometry_sha256":self.geometry.as_ref().map(|g|g.bundle_sha256()),
            "scene_version":self.scene_version(),"ram_damage_event_count":self.ram_damage_events.len(),
            "fragiles":self.fragiles.as_ref().map(|state|state.failure_snapshot()),
            "destructible_fixture":self.destructible.as_ref().map(|state|format!("{state:?}")),
            "trace_event_count":events.len(),"trace_omitted_prefix":trace_from,
            "trace_tail":events[trace_from..].iter().map(|e|format!("{e:?}")).collect::<Vec<_>>(),
            "scope":"committed world state and bounded trace tail; not a complete deterministic replay"
        });
        if let Some(policy)=self.impact.extended_breech_lab_policy(){
            snapshot.as_object_mut().expect("snapshot object").insert("unarmored_device_policy".into(),policy.into());
        }
        snapshot
    }

    pub fn new(id: u64, now: Instant) -> io::Result<Self> {
        Self::new_for_map(id, now, crate::map_profile091::MapId::Karelia)
    }
    pub fn new_for_map(id: u64, now: Instant, map: crate::map_profile091::MapId) -> io::Result<Self> {
        Self::new_for_vehicle(id,now,map,VehicleKind::Ms1)
    }
    pub fn vehicle_kind(&self) -> VehicleKind { self.vehicle_kind }
    pub fn expected_actors(&self) -> usize { self.expected_actors }
    pub fn mixed_profiles(&self) -> bool { self.mixed_profiles }
    pub fn mixed_ammo(&self)->bool{self.mixed_ammo}
    /// Future reserves only: an old V2 receipt cannot opt itself into losses.
    /// Source-backed mixed simulation/terrain and lifecycle must be configured
    /// before this immutable pristine-template policy is selected.
    pub fn enable_ammo_detonation(&mut self)->io::Result<()>{
        if self.ammo_detonation.is_some()||self.extended_lab||self.vehicle_kind.is_extended()||!self.mixed_ammo||!self.mixed_profiles
            ||self.started.is_some()||!self.actors.is_empty()||!self.shots.is_empty()
            ||!self.impact.events().is_empty()||!self.damage_events.is_empty()||!self.device_events.is_empty()
            ||self.terrain.is_none()||self.lifecycle.as_ref().is_none_or(|life|life.phase()!=super::lifecycle::Phase::Waiting){return Err(bad());}
        self.ammo_detonation=Some(super::ammo_detonation::Ledger::new(self.expected_actors as u8)?);Ok(())
    }
    /// Explicit Loss4 training-template constructor. Existing public roster
    /// mutation and fresh_battle(same_id) guards stay unchanged. Ownership is
    /// still supplied only by actual typed admitted receipts after this call.
    pub(super) fn fresh_loss_roster(&self,id:u64,expected_actors:usize,now:Instant)->io::Result<Self>{
        if id==0||id>i64::MAX as u64||!(2..=MAX_ACTORS).contains(&expected_actors)
            ||!self.mixed_ammo||!self.mixed_profiles||!self.ap_test_lab||self.terrain.is_none()
            ||self.extended_lab||self.vehicle_kind.is_extended()||self.impact.extended_breech_lab()
            ||self.lab_loadouts.iter().any(Option::is_some)||self.team_plan().is_some()||self.tick!=1000
            ||self.lifecycle.as_ref().is_none_or(|life|!life.is_pristine())||self.lifecycle_created_unix.is_some()
            ||self.ammo_detonation.as_ref().is_none_or(|ledger|!ledger.is_pristine())
            ||!self.projectiles.is_empty()||!self.contacts.is_empty()||!self.impacts.is_empty()||!self.terrain_contacts.is_empty()
            ||self.contact_sources.iter().any(Option::is_some)||self.contact_sequences.iter().any(|seq|*seq!=0)
            ||self.fragiles.as_ref().is_some_and(|state|!state.events.is_empty()||!state.vehicle_events.is_empty()){
            return Err(bad());
        }
        // First launch legitimately keeps the template's own id. Prove source
        // pristine state with a DISTINCT validation id, preserving the public
        // same-id rejection rather than relaxing it for arbitrary callers.
        let validation_id=if self.id==1{2}else{1};
        let mut next=self.fresh_battle(validation_id,now)?;
        let ledger=super::ammo_detonation::Ledger::new(expected_actors as u8)?;
        next.id=id;next.rng_state=id;
        next.ammo_detonation=None;
        next.set_expected_actors(expected_actors)?;
        next.ammo_detonation=Some(ledger);
        Ok(next)
    }
    pub fn ammo_detonation_enabled(&self)->bool{self.ammo_detonation.is_some()}
    /// Version5 is frozen only on a pristine future battle template. Neither
    /// old v2/v4 rows nor temporary seven LAB profiles acquire hold semantics.
    pub fn enable_owner_hold(&mut self)->io::Result<()> {
        if self.owner_hold||!self.mixed_ammo||!self.mixed_profiles||self.ammo_detonation.is_none()||self.extended_lab
            ||self.started.is_some()||!self.actors.is_empty()||!self.shots.is_empty()||!self.projectiles.is_empty()
            ||!self.impact.events().is_empty()||!self.damage_events.is_empty()||!self.device_events.is_empty()
            ||self.terrain.is_none()||self.result_spots.is_none()
            ||self.lifecycle.as_ref().is_none_or(|s|s.phase()!=super::lifecycle::Phase::Waiting){return Err(bad());}
        self.owner_hold=true;Ok(())
    }
    pub fn owner_hold_enabled(&self)->bool{self.owner_hold}
    pub fn ammo_detonations(&self)->&[super::ammo_detonation::Event]{
        self.ammo_detonation.as_ref().map_or(&[],super::ammo_detonation::Ledger::events)
    }
    pub fn turret_flights(&self)->&[super::ammo_detonation::Flight]{&self.turret_flights}
    /// AUTHORED publication fixture only. It does not prove exterior collision,
    /// DeviceState source authority or inventory admission. Production only
    /// creates these events through direct_mixed's actual module transition.
    #[cfg(test)]
    pub(super) fn install_detonation_publication_fixture(&mut self,input:super::ammo_detonation::Input)->io::Result<()>{
        let actor=self.actors.get(input.target).ok_or_else(||bad())?;
        if actor.vehicle_kind()!=input.kind||actor.health!=input.health_before as i16
            ||actor.fire.typed().is_none_or(|state|state.counts()!=input.counts){return Err(bad());}
        let mut next=self.clone();
        let super::ammo_detonation::Outcome::New(event)=next.ammo_detonation.as_mut().ok_or_else(||bad())?.apply(input)?else{return Err(bad());};
        if next.turret_flights.len()>=MAX_ACTORS{return Err(bad());}
        if next.actors[input.target].fire.lose_loaded_for_detonation()?!=event.lost(){return Err(bad());}
        next.actors[input.target].health=0;next.actors[input.target].input=Input::STOP;next.actors[input.target].speed=0.;
        next.actors[input.target].aim.park();if let Some(state)=&mut next.actors[input.target].devices{state.freeze();}
        next.turret_flights.push(super::ammo_detonation::Flight::new(event));*self=next;Ok(())
    }
    /// Server calls once per loop, including after outcome freeze. Only this
    /// bounded visual timeline advances; battle HP/results/devices stay frozen.
    /// Exact source ground triangles are sampled by a vertical point ray; no
    /// static props, swept body or Jolt contact is invented for the detached FX.
    pub fn advance_turret_flights(&mut self,now:Instant)->io::Result<bool>{
        if self.turret_flights.is_empty(){return Ok(false);}
        let ms=self.lifecycle_ms(now)?;
        if ms>super::ammo_detonation::MAX_TIME_MS||self.turret_visual_ms.is_some_and(|old|ms<old){return Err(bad());}
        if self.turret_visual_ms==Some(ms){return Ok(false);}
        let terrain=self.terrain.as_ref().ok_or_else(||bad())?;
        let mut next=self.turret_flights.clone();let mut changed=false;
        for flight in &mut next{
            let previous=flight.sample();
            let sample=flight.advance(ms,|x,z|{
                let max=terrain::MAX_QUERY_COORDINATE;
                terrain.nearest_ground([x,max,z],[x,-max,z])?.map(|hit|hit.point[1]).ok_or_else(||bad())
            })?;
            changed|=previous!=sample;
        }
        self.turret_flights=next;self.turret_visual_ms=Some(ms);Ok(changed)
    }
    pub fn enable_mixed_ammo(&mut self)->io::Result<()>{
        if self.mixed_ammo||!self.mixed_profiles||self.started.is_some()||!self.actors.is_empty()||!self.shots.is_empty(){return Err(bad());}
        self.mixed_ammo=true;Ok(())
    }
    pub fn shot_limit(&self) -> usize {
        if self.mixed_profiles {
            // Preserve the accepted two-kind v1 ceiling; a curated roster may
            // raise it only to an actual mounted capacity of a bound actor.
            self.expected_actors*self.actors.iter().map(|a|a.vehicle_kind().ammo_limit() as usize).max().unwrap_or(96).max(96)
        } else { self.vehicle_kind.battle_shot_limit() }
    }
    pub fn new_for_roster(id:u64,now:Instant,map:crate::map_profile091::MapId,expected_actors:usize)->io::Result<Self> {
        if !(2..=MAX_ACTORS).contains(&expected_actors) { return Err(bad()); }
        let mut world=Self::new_for_vehicle(id,now,map,VehicleKind::Ms1)?;
        world.set_expected_actors(expected_actors)?;Ok(world)
    }
    pub fn set_expected_actors(&mut self,expected_actors:usize)->io::Result<()> {
        if !(2..=MAX_ACTORS).contains(&expected_actors) || self.team_plan.is_some() || self.started.is_some() || !self.actors.is_empty()
            || !self.shots.is_empty() || !self.impact.events().is_empty() || self.scene_version()!=0
            ||self.ammo_detonation.is_some() {return Err(bad());}
        self.impact.configure_roster(expected_actors)?;self.expected_actors=expected_actors;self.mixed_profiles=true;Ok(())
    }
    pub fn geometry_for(&self,kind:VehicleKind)->io::Result<&Arc<geometry::Bundle>> {
        if kind.is_generated() {return self.generated_geometries.get(&kind.index()).ok_or_else(||bad());}
        let index=kind.index();
        self.geometries[index].as_ref().or_else(||self.geometry.as_ref().filter(|g|g.vehicle_kind()==kind)).ok_or_else(||bad())
    }
    pub fn new_for_vehicle(id: u64, now: Instant, map: crate::map_profile091::MapId, kind: VehicleKind) -> io::Result<Self> {
        if id == 0 { return Err(bad()); }
        Ok(Self { id, map, vehicle_kind:kind, expected_actors:CAPACITY,team_plan:None,mixed_profiles:false,actors: Vec::new(), started: None, last: now, tick: 1000,
            shots: Vec::new(), projectiles: Vec::new(), impact: impact::Trace::new_for_vehicle(map,kind), lifecycle: None, lifecycle_created_unix: None,
            mixed_ammo:false,ammo_detonation:None,turret_flights:Vec::new(),turret_visual_ms:None,
            extended_lab:false,owner_hold:false,team_base_spawn:false,lab_loadouts:[None;MAX_ACTORS],
            damage_events:Vec::new(),device_events:Vec::new(),rng_state:id,rng_draws:Vec::new(),
            result_spots:None,result_spot_tick:None,original_spotting:None,
            geometry: None,geometries:std::array::from_fn(|_|None),generated_geometries:std::collections::BTreeMap::new(),contacts: Vec::new(), ap_test_lab: false, impacts: Vec::new(),
            terrain: None, terrain_contacts: Vec::new(), ram_damage_events:Vec::new(), active_ram_pairs:std::collections::BTreeSet::new(), destructible: None,fragiles:None,
            contact_sources:std::array::from_fn(|_|None),contact_sequences:[0;MAX_ACTORS] })
    }
    pub fn bind_geometry(&mut self, bundle: Arc<geometry::Bundle>) -> io::Result<()> {
        let kind=bundle.vehicle_kind();let index=kind.index();
        if kind.is_generated() {
            // Generated kinds join mixed owned templates only, never a homogeneous world.
            if !self.mixed_profiles || self.started.is_some() || !self.shots.is_empty() || self.geometry.is_none()
                || self.generated_geometries.insert(index,bundle).is_some() { return Err(bad()); }
            return Ok(());
        }
        if !self.mixed_profiles && kind!=self.vehicle_kind || self.started.is_some() || !self.shots.is_empty()
            || self.geometries[index].is_some() || !self.mixed_profiles && self.geometry.is_some() { return Err(bad()); }
        if self.mixed_profiles {self.geometries[index]=Some(bundle.clone());}
        if self.geometry.is_none() || kind==self.vehicle_kind {self.geometry=Some(bundle);}Ok(())
    }
    /// SPAWN-15 explicit project policy (config `spawn_policy`), chosen on the
    /// pristine template; every map of the registry has a formation.
    pub fn enable_team_base_spawn(&mut self)->io::Result<()>{
        if self.team_base_spawn||self.started.is_some()||!self.actors.is_empty()||!self.mixed_profiles{return Err(bad());}
        self.team_base_spawn=true;Ok(())
    }
    pub fn team_base_spawn(&self)->bool{self.team_base_spawn}
    pub fn enable_original_spotting(&mut self, rules: super::spotting::Rules) -> io::Result<()> {
        if self.original_spotting.is_some() || self.started.is_some() || !self.actors.is_empty()
            || self.terrain.is_none() { return Err(bad()); }
        self.original_spotting=Some(super::spotting::State::new(rules)?); Ok(())
    }
    pub fn original_spotting_enabled(&self) -> bool { self.original_spotting.is_some() }
    fn spotting_excluded(&self) -> io::Result<Vec<u32>> {
        let mut excluded=if let Some(state)=&self.fragiles {state.projectile_excluded()}
            else {self.destructible.as_ref().and_then(|state|state.excluded_instance()).into_iter().collect()};
        excluded.sort_unstable();
        if excluded.windows(2).any(|pair|pair[0]==pair[1]) { return Err(bad()); }
        Ok(excluded)
    }
    fn spotting_points(&self, slot: usize) -> io::Result<super::spotting::Points> {
        let actor=self.actors.get(slot).ok_or_else(bad)?;
        self.geometry_for(actor.vehicle_kind())?.spotting_parts().world(actor.position,actor.direction,actor.aim.yaw)
    }
    fn spotting_actors(&self) -> io::Result<Vec<super::spotting::Actor>> {
        let terrain=self.terrain.as_ref().ok_or_else(bad)?;
        self.actors.iter().enumerate().map(|(slot,actor)| {
            if actor.position.into_iter().any(|v|!v.is_finite()||v.abs()>10_000.)
                ||actor.direction.into_iter().any(|v|!v.is_finite()||v.abs()>std::f32::consts::PI){return Err(bad());}
            let mut points=self.spotting_points(slot)?;
            // This is the inherited P05C project correction, not a recovered
            // historical rule. It only rescues the observer when both source
            // observer points are below real ground and never rewrites target points.
            if self.original_spotting.as_ref().is_some_and(|s|s.rules.rollover_world_up_fallback) {
                let underground=points.observers.into_iter().all(|point| {
                    terrain.nearest_ground(point,[point[0],10_000.,point[2]]).ok().flatten().is_some_and(|hit|hit.point[1]>point[1]+0.001)
                });
                if underground { points.observers[0]=Self::visibility_sight_point(actor); }
            }
            let observer_active=actor.alive()&&actor.ready&&actor.session.is_some();
            let commander_active=observer_active&&actor.devices.as_ref().is_none_or(|state|state.crew().first()==Some(&true));
            let view_scale=actor.devices.as_ref().map_or(1.,|state|state.capabilities().view_scale);
            if !view_scale.is_finite()||!(0. ..=1.).contains(&view_scale){return Err(bad());}
            Ok(super::spotting::Actor{slot,team:self.team(slot)?,position:actor.position,points,
                view_range:actor.vehicle_kind().view_range()*view_scale,observer_active,commander_active,wreck:actor.health<=0})
        }).collect()
    }
    pub fn refresh_original_spotting(&mut self, now: Instant) -> io::Result<()> {
        let Some(state)=self.original_spotting.as_ref() else { return Ok(()); };
        if self.actors.is_empty() { return Ok(()); }
        let start=self.started.ok_or_else(bad)?;
        let ms=u64::try_from(now.checked_duration_since(start).ok_or_else(bad)?.as_millis()).map_err(|_|bad())?;
        let actors=self.spotting_actors()?; let excluded=self.spotting_excluded()?; let terrain=self.terrain.as_ref().ok_or_else(bad)?;
        let mut next=state.clone();
        next.refresh(ms,&actors,|_,_,start,end|Ok(terrain.nearest_excluding_many(start,end,&excluded)?.is_none()))?;
        self.original_spotting=Some(next); Ok(())
    }
    pub fn sixth_sense_generation(&self, slot: usize) -> io::Result<u32> {
        self.original_spotting.as_ref().map_or(Ok(0),|state|state.sixth_generation(slot))
    }
    pub fn sixth_sense_eligible(&self, slot: usize) -> io::Result<bool> {
        let actor=self.actors.get(slot).ok_or_else(bad)?;
        Ok(actor.alive() && actor.ready && actor.session.is_some()
            && actor.devices.as_ref().is_none_or(|state|state.crew().first()==Some(&true))
            && self.lifecycle.as_ref().is_none_or(|state|state.allows_actions()))
    }
    pub fn enable_lifecycle(&mut self, rules: super::lifecycle::Rules) -> io::Result<()> {
        if self.started.is_some() || !self.actors.is_empty() || self.lifecycle.is_some() { return Err(bad()); }
        self.lifecycle = Some(super::lifecycle::State::new(rules)?); Ok(())
    }
    /// Explicit result-statistics opt-in. Native interest itself remains the
    /// existing visibility_v1 policy; legacy templates never query it here.
    pub fn enable_result_spots(&mut self)->io::Result<()>{
        if self.result_spots.is_some()||self.result_spot_tick.is_some()||self.started.is_some()
            ||!self.actors.is_empty()||!self.shots.is_empty()||!self.projectiles.is_empty()
            ||!self.impact.events().is_empty()||self.terrain.is_none()
            ||self.lifecycle.as_ref().is_none_or(|state|state.phase()!=super::lifecycle::Phase::Waiting){return Err(bad());}
        self.result_spots=Some(Vec::new());Ok(())
    }
    pub(super) fn result_spots(&self)->Option<&[result_spots::SpotRecord]>{self.result_spots.as_deref()}
    /// Explicit frozen roster teams are set once, before actor identities or
    /// any simulation/Trace events exist. Caller must bind the frozen roster's
    /// identity order before transport attachment; arrival order is not a plan.
    pub fn set_team_plan(&mut self,plan:super::p10b_team_plan::TeamPlan)->io::Result<()> {
        if plan.len()!=self.expected_actors || self.team_plan.is_some() || self.lifecycle.is_none()
            || self.started.is_some() || !self.actors.is_empty() || self.tick!=1000 || !self.shots.is_empty()
            || !self.impact.events().is_empty() || self.scene_version()!=0 {return Err(bad());}
        self.team_plan=Some(plan);Ok(())
    }
    pub fn team_plan(&self)->Option<&super::p10b_team_plan::TeamPlan>{self.team_plan.as_ref()}
    pub fn spawn_lane(&self,slot:usize)->io::Result<usize>{
        if slot>=self.expected_actors{return Err(bad());}
        self.team_plan.as_ref().map_or(Ok(slot),|plan|plan.lane(slot))
    }
    pub fn team(&self, slot: usize) -> io::Result<u8> {
        if slot >= self.actors.len() { return Err(bad()); }
        if let Some(plan)=&self.team_plan {return plan.team(slot);}
        Ok(if self.lifecycle.is_some() { (slot % 2) as u8 + 1 } else { 1 })
    }
    /// Stateless recipient interest from this coherent authoritative snapshot.
    fn visibility_sight_point(actor:&Actor)->[f32;3]{
        let mut offset=super::pose::rotate(actor.vehicle_kind().aim().pivot,actor.direction);
        // The pivot follows the hull; the laboratory clearance remains world-up
        // so a resting roof rollover does not rotate that clearance underground.
        offset[1]+=0.5;
        std::array::from_fn(|axis|actor.position[axis]+offset[axis])
    }
    /// Source stock range, centre-distance and one sight line are the explicit
    /// v1 test_lab policy;0.5m world-up from the rotated stock turret pivot is
    /// not historical camouflage/spotting reconstruction. Parked/dead geometry remains eligible.
    pub(super) fn desired_visibility(&self, own:usize)->io::Result<[bool;MAX_ACTORS]> {
        if own>=self.actors.len()||self.actors.len()>MAX_ACTORS{return Err(bad());}
        if let Some(state)=&self.original_spotting {
            let actors=self.spotting_actors()?;
            if state.initialized() { return state.desired(own); }
            let team=self.team(own)?; let mut row=[false;MAX_ACTORS];
            for actor in actors { row[actor.slot]=actor.slot==own||actor.team==team; }
            return Ok(row);
        }
        let terrain=self.terrain.as_ref().ok_or_else(||bad())?;
        let mut excluded=if let Some(state)=&self.fragiles {state.projectile_excluded()}
            else{self.destructible.as_ref().and_then(|state|state.excluded_instance()).into_iter().collect()};
        excluded.sort_unstable();
        if excluded.windows(2).any(|rows|rows[0]==rows[1]){return Err(bad());}
        let mut actors=Vec::with_capacity(self.actors.len());
        for(slot,actor)in self.actors.iter().enumerate(){
            if actor.direction.iter().any(|v|!v.is_finite()||v.abs()>std::f32::consts::PI){return Err(bad());}
            let kind=actor.vehicle_kind();
            let view_scale=actor.devices.as_ref().map_or(1.,|state|state.capabilities().view_scale);
            actors.push(super::visibility::Actor{slot,team:self.team(slot)?,position:actor.position,
                sight_point:Self::visibility_sight_point(actor),view_range:kind.view_range()*view_scale});
        }
        let desired=super::visibility::desired_set(own,&actors,super::visibility::Allies::Always,|line|{
            if line.start==line.end{return Ok(true);}
            Ok(terrain.nearest_excluding_many(line.start,line.end,&excluded)?.is_none())
        })?;
        let mut result=[false;MAX_ACTORS];for slot in desired.slots(){result[slot]=true;}Ok(result)
    }
    pub fn lifecycle_ms(&self, now: Instant) -> io::Result<u64> {
        let start = self.started.ok_or_else(|| bad())?;
        now.checked_duration_since(start).ok_or_else(|| bad())?.as_millis().try_into().map_err(|_| bad())
    }
    pub fn advance_lifecycle(&mut self, now: Instant) -> io::Result<bool> {
        if self.lifecycle.is_none() || self.started.is_none() { return Ok(false); }
        let elapsed = self.lifecycle_ms(now)?;
        let members = self.actors.iter().enumerate().map(|(slot, actor)| {
            let damage=if self.mixed_ammo {self.damage_events.iter().filter(|i|i.target==slot&&(i.health_after<i.health_before||i.lethal())).map(|i|i.attacker).collect::<Vec<_>>()}
                else{self.impacts.iter().filter(|i|i.target==slot&&i.health_after<i.health_before).map(|i|i.attacker).collect::<Vec<_>>()};
            let ram_count=self.ram_damage_events.iter().filter(|e|e.target==slot&&e.health_after<e.health_before).count();
            let epoch:u32=damage.len().checked_add(ram_count).ok_or_else(bad)?.try_into().map_err(|_|bad())?;
            let last_damager=if ram_count>0{self.health_cause(slot)?.map(|c|c.0)}else{damage.last().copied()};
            Ok(super::lifecycle::Member { team: self.team(slot)?, present: actor.session.is_some(), ready: actor.ready,
                alive: actor.alive(), position: actor.position, damage_epoch: epoch,
                last_damager })
        }).collect::<io::Result<Vec<_>>>()?;
        let changed = if let Some(old)=&self.result_spots {
            // A failed late LOS must leave lifecycle, journal and actor state
            // untouched. Stage only the small lifecycle and <=6 records;
            // cloning the whole World/Trace here would be unnecessary work.
            let mut life=self.lifecycle.as_ref().ok_or_else(||bad())?.clone();
            let changed=life.advance(elapsed,&members)?;
            let next=if life.allows_actions(){
                let observers=members.iter().map(|member|result_spots::Member{
                    team:member.team,present:member.present,ready:member.ready,alive:member.alive}).collect::<Vec<_>>();
                Some(result_spots::refresh(old,self.result_spot_tick,self.tick,&observers,
                    |slot|self.desired_visibility(slot))?)
            }else{None};
            self.lifecycle=Some(life);
            if let Some(next)=next{self.result_spots=Some(next);self.result_spot_tick=Some(self.tick);}
            changed
        }else{self.lifecycle.as_mut().ok_or_else(|| bad())?.advance(elapsed, &members)?};
        if !self.lifecycle.as_ref().ok_or_else(|| bad())?.allows_actions() {
            for actor in &mut self.actors { actor.input = Input::STOP; }
        }
        if self.lifecycle.as_ref().is_some_and(|state|state.outcome().is_some()){
            for actor in &mut self.actors{if let Some(devices)=&mut actor.devices{devices.freeze();}}
        }
        Ok(changed)
    }
    pub fn enable_ap_test_lab(&mut self) -> io::Result<()> {
        let count=if self.geometries[5..].iter().any(Option::is_some){7}
            else if self.geometries[2..5].iter().any(Option::is_some){5}else{2};
        if self.started.is_some() || self.geometry.is_none() || self.ap_test_lab
            || self.mixed_profiles && self.geometries[..count].iter().any(Option::is_none) { return Err(bad()); }
        self.ap_test_lab = true; Ok(())
    }
    pub fn bind_terrain(&mut self, terrain: Arc<terrain::Terrain>) -> io::Result<()> {
        if self.started.is_some() || !self.shots.is_empty() || !self.ap_test_lab
            || self.geometry.is_none() || self.terrain.is_some() || terrain.map_id()!=self.map { return Err(bad()); }
        self.terrain = Some(terrain); Ok(())
    }
    pub fn latest_shot(&self) -> u32 { self.shots.last().map(|s| s.sequence).unwrap_or(0) }
    pub fn bind_destructible_test_lab(&mut self) -> io::Result<()> {
        if self.vehicle_kind!=VehicleKind::Ms1 || self.map!=crate::map_profile091::MapId::Karelia || self.started.is_some() || !self.shots.is_empty() || !self.ap_test_lab || self.destructible.is_some()||self.fragiles.is_some()
            || self.terrain.as_ref().is_none_or(|terrain|terrain.source_revision()!=terrain::WORLD_SOURCE_REVISION) {return Err(bad());}
        self.destructible=Some(destructible::State::default());Ok(())
    }
    pub fn bind_fragiles(&mut self,catalog:Arc<fragiles::Catalog>)->io::Result<()>{
        if catalog.map!=self.map||self.started.is_some()||!self.shots.is_empty()||!self.ap_test_lab||self.destructible.is_some()||self.fragiles.is_some(){return Err(bad());}
        catalog.bind_geometry(self.terrain.as_ref().ok_or_else(|| bad())?)?;
        self.impact.bind_fragiles(catalog.clone())?;let mut state=fragiles::State::new(catalog);
        if self.mixed_profiles{state.configure_roster(self.expected_actors)?;
            for actor in &self.actors {state.bind_ammo_capacity(actor.vehicle_kind().ammo_limit())?;}}
        self.fragiles=Some(state);Ok(())
    }
    pub fn scene_version(&self)->u32{self.fragiles.as_ref().map_or_else(||self.destructible.as_ref().map_or(0,destructible::State::scene_version),fragiles::State::scene_version)}
    pub fn destructible_enabled(&self)->bool{self.destructible.is_some()}
    pub fn destructible_transition(&self)->Option<&destructible::Transition>{self.destructible.as_ref().and_then(destructible::State::transition)}
    pub fn bind_contact_source(&mut self,slot:usize,source:ram_proof::Source)->io::Result<()> {
        if slot>=self.expected_actors||!(self.actors.get(slot).and_then(|a|a.session)==Some(source.session)
            ||self.mixed_profiles&&self.contact_sources[slot].as_ref()==Some(&source))
            ||source.profile!=ram_proof::Profile::for_vehicle(self.actors[slot].vehicle_kind)
            ||!source.follows(self.contact_sources[slot].as_ref()){return Err(bad());}
        self.impact.bind_contact_source(slot,source.clone())?;
        if self.contact_sources[slot].as_ref()!=Some(&source){self.contact_sequences[slot]=0;}
        self.contact_sources[slot]=Some(source);Ok(())
    }
    pub fn revoke_contact_source(&mut self,slot:usize)->io::Result<()> {
        if slot>=self.expected_actors||self.actors.get(slot).and_then(|a|a.session).is_some(){return Err(bad());}
        // Retain the generation floor; actor session absence revokes admission.
        self.impact.revoke_contact_source(slot)?;Ok(())
    }
    /// Apply contacts from a fully drained worker frame to a cloned candidate
    /// world. The caller stages the candidate and waits for both worker scene
    /// ACKs before committing it or publishing native state.
    pub fn apply_vehicle_contacts(&mut self, contacts:&[VehicleContactInput])->io::Result<Vec<fragiles::VehicleContact>> {
        if contacts.len()>if self.mixed_profiles {self.expected_actors*32}else{32} { return Err(bad()); }
        if contacts.is_empty() { return Ok(Vec::new()); }
        // Stage both domain state and trace state. A later malformed contact
        // or a trace admission failure must not leave an earlier contact from
        // the same worker frame committed in this World. The integrated
        // runtime already calls this on a candidate clone, but keeping this
        // method atomic protects every caller and makes the boundary explicit.
        let mut state=self.fragiles.as_ref().ok_or_else(|| bad())?.clone();
        if !state.catalog.contacts { return Err(bad()); }
        let mut trace=self.impact.clone();
        let mut sequences=self.contact_sequences;
        if matches!(state.catalog.version,7|8) {
            let mut frames:[Option<Arc<ram_proof::ContextFrame>>;MAX_ACTORS]=std::array::from_fn(|_|None);
            let mut indices:[Vec<usize>;MAX_ACTORS]=std::array::from_fn(|_|Vec::new());
            for contact in contacts {
                let p=contact.proof.as_ref().ok_or_else(|| bad())?;let c=&p.frame.context;let slot=contact.shooter;
                if slot>=self.expected_actors||c.battle!=self.id||c.slot!=slot||!self.mixed_profiles&&self.actors.get(slot).and_then(|a|a.session)!=Some(c.session)
                    ||!self.contact_sources[slot].as_ref().is_some_and(|s|s.matches(c,p.frame.proof.profile))
                    ||c.seq<=self.contact_sequences[slot]||p.index!=indices[slot].len(){return Err(bad());}
                indices[slot].push(p.index);
                state.validate_proof(p)?;
                if let Some(old)=&frames[slot]{if old.as_ref()!=p.frame.as_ref(){return Err(bad());}}
                else{frames[slot]=Some(p.frame.clone());}
                sequences[slot]=c.seq;
            }
            for (frame,ids) in frames.iter().zip(&indices){if let Some(frame)=frame {
                if ids.iter().copied().collect::<Vec<_>>()!=(0..frame.proof.receipts.len()).collect::<Vec<_>>(){return Err(bad());}
            }}
        }
        let mut outcomes=Vec::new();
        for contact in contacts {
            if contact.shooter>=self.expected_actors { return Err(bad()); }
            if let Some(event)=state.ram_contact_with_proof(contact.object_id,contact.shooter,self.tick,contact.substep,
                contact.point,contact.normal,contact.velocity,contact.mass_kg,contact.kind.clone(),contact.proof.clone())? {
                trace.vehicle_contact(self.id,event.tick,&event)?;
                outcomes.push(event);
            }
        }
        self.fragiles=Some(state);
        self.impact=trace;
        self.contact_sequences=sequences;
        Ok(outcomes)
    }
    /// Atomic like apply_vehicle_contacts: every contact is decided by the
    /// domain rule and replayed by the trace on clones before either commits.
    pub fn apply_column_contacts(&mut self, contacts:&[ColumnContactInput])->io::Result<Vec<fragiles::VehicleContact>> {
        if contacts.len()>self.expected_actors*16 { return Err(bad()); }
        if contacts.is_empty() { return Ok(Vec::new()); }
        let mut state=self.fragiles.as_ref().ok_or_else(|| bad())?.clone();
        if state.catalog.version!=8 { return Err(bad()); }
        let mut trace=self.impact.clone();
        let mut outcomes=Vec::new();
        for c in contacts {
            if c.shooter>=self.expected_actors { return Err(bad()); }
            if let Some(event)=state.column_contact(c.object_id,c.shooter,self.tick,c.substep,c.point,c.normal,c.velocity,c.mass_kg)? {
                trace.vehicle_contact(self.id,event.tick,&event)?;
                outcomes.push(event);
            }
        }
        self.fragiles=Some(state);
        self.impact=trace;
        Ok(outcomes)
    }
    pub fn apply_tank_contacts(&mut self, contacts:&[TankContactInput], sequence:u32, tick:u32)->io::Result<()> {
        // ARENA-01: bounded by the roster's pairs (15 for six, 435 for thirty).
        if sequence==0||tick==0||contacts.len()>self.expected_actors.saturating_mul(self.expected_actors.saturating_sub(1))/2{return Err(bad());}
        let mut pairs=std::collections::BTreeSet::new();let mut resolved=Vec::with_capacity(contacts.len());
        for row in contacts {
            if row.slot_a>=row.slot_b||row.slot_b>=self.actors.len()||!pairs.insert((row.slot_a,row.slot_b)){return Err(bad());}
            let contact=super::tank_ram::Contact{slot_a:row.slot_a,slot_b:row.slot_b,substep:row.substep,point:row.point,normal:row.normal,relative_velocity:row.relative_velocity};
            let a=self.actors[row.slot_a].vehicle_kind().mass_kg();let b=self.actors[row.slot_b].vehicle_kind().mass_kg();
            resolved.push((contact,super::tank_ram::resolve(contact,a,b)?));
        }
        let mut next=self.clone();next.active_ram_pairs=pairs;
        for (contact,result) in resolved {
            if self.active_ram_pairs.contains(&(contact.slot_a,contact.slot_b)){continue;}
            let Some(result)=result else{continue;};let before_a=next.actors[contact.slot_a].health;let before_b=next.actors[contact.slot_b].health;
            if !next.actors[contact.slot_a].alive()||!next.actors[contact.slot_b].alive(){continue;}
            let after_a=(i32::from(before_a)-i32::from(result.damage_a).min(i32::from(before_a))).max(0)as i16;let after_b=(i32::from(before_b)-i32::from(result.damage_b).min(i32::from(before_b))).max(0)as i16;
            next.actors[contact.slot_a].health=after_a;next.actors[contact.slot_b].health=after_b;
            for (attacker,target,before,after) in [(result.attacker,result.target,before_b,after_b),(result.target,result.attacker,before_a,after_a)]{next.ram_damage_events.push(RamDamageRecord{sequence,tick,domain_tick:next.tick,attacker,target,pair:(contact.slot_a,contact.slot_b),energy_j:result.energy_j,closing_speed:result.closing_speed,health_before:before,health_after:after});}
            for slot in [contact.slot_a,contact.slot_b]{if next.actors[slot].health==0{
                let actor=&mut next.actors[slot];actor.input=Input::STOP;actor.speed=0.;actor.aim.park();
                if let Some(devices)=&mut actor.devices{devices.freeze();}
            }}
        }
        *self=next;Ok(())
    }
    /// Authenticated identity only. The caller reserves a transport retirement
    /// slot before committing this world assignment. Rejoin never resets ammo.
    pub fn attach(&mut self, identity: Identity, session: u32) -> io::Result<usize> {
        self.attach_loadout(identity, session, None)
    }
    /// Only a writer-confirmed stock mount can supply owned battle ammunition.
    /// Reattaching the same receipt never replenishes an existing actor.
    pub fn attach_owned(&mut self, identity: Identity, session: u32,
        loadout: &crate::battle091::profile13::FrozenLoadout) -> io::Result<usize> {
        loadout.validate_owned(&identity.account)?;
        if !self.mixed_profiles && loadout.kind != self.vehicle_kind { return Err(bad()); }
        self.attach_loadout(identity, session, Some(loadout.clone()))
    }
    pub fn attach_owned_v2(&mut self,identity:Identity,session:u32,loadout:&crate::profile13_v2091::Frozen)->io::Result<usize>{
        if self.ammo_detonation.is_some(){return Err(bad());}
        self.attach_owned_v2_inner(identity,session,loadout)
    }
    pub fn attach_owned_loss(&mut self,identity:Identity,session:u32,loadout:&crate::profile13_loss091::FrozenLoss)->io::Result<usize>{
        if self.owner_hold{return Err(bad());}
        self.attach_owned_loss_inner(identity,session,loadout)
    }
    /// Only a typed writer5 admission can populate owned_hold. Re-login must
    /// remain Account-only and cannot revive/replenish an existing body.
    pub fn attach_owned_hold(&mut self,identity:Identity,session:u32,loadout:&crate::profile13_hold091::FrozenHold)->io::Result<usize>{
        loadout.validate_owned(&identity.account)?;
        if !self.owner_hold||self.started.is_some()||self.actors.iter().any(|a|a.identity.account==identity.account){return Err(bad());}
        let mut next=self.clone();let slot=next.attach_owned_loss_inner(identity,session,loadout.loss())?;
        next.actors[slot].owned_hold=Some(loadout.clone());*self=next;Ok(slot)
    }
    fn attach_owned_loss_inner(&mut self,identity:Identity,session:u32,loadout:&crate::profile13_loss091::FrozenLoss)->io::Result<usize>{
        loadout.validate_owned(&identity.account)?;
        if self.ammo_detonation.is_none()||self.extended_lab||loadout.base.kind.is_extended(){return Err(bad());}
        let existing=self.actors.iter().position(|actor|actor.identity.account==identity.account);
        if existing.is_some_and(|slot|self.actors[slot].owned_loss.as_ref()!=Some(loadout)){return Err(bad());}
        let mut next=self.clone();let slot=next.attach_owned_v2_inner(identity,session,&loadout.base)?;
        next.actors[slot].owned_loss=Some(loadout.clone());*self=next;Ok(slot)
    }
    fn attach_owned_v2_inner(&mut self,identity:Identity,session:u32,loadout:&crate::profile13_v2091::Frozen)->io::Result<usize>{
        loadout.validate_owned(&identity.account)?;
        if !self.mixed_ammo||!self.mixed_profiles||self.extended_lab||loadout.kind.is_extended(){return Err(bad());}
        let profile=crate::p06t_device_caps::Profile::for_owned(loadout.kind).ok_or_else(bad)?;
        let existing=self.actors.iter().position(|actor|actor.identity.account==identity.account);
        if existing.is_some_and(|slot|self.actors[slot].owned_v2.as_ref()!=Some(loadout)){return Err(bad());}
        let mut next=self.clone();let previous=next.vehicle_kind;
        next.mixed_ammo=false;next.vehicle_kind=loadout.kind;
        let slot=next.attach_loadout(identity,session,None)?;
        next.vehicle_kind=previous;next.mixed_ammo=true;
        if existing.is_none(){
            next.actors[slot].fire=fire::State::with_typed(loadout.mount,loadout.counts(),loadout.initial_shell_compact_id)?;
            next.actors[slot].owned_v2=Some(loadout.clone());
            next.actors[slot].devices=Some(crate::p06t_device_state::State::new(profile)?);
        }
        *self=next;Ok(slot)
    }
    fn attach_loadout(&mut self, identity: Identity, session: u32,
        loadout: Option<crate::battle091::profile13::FrozenLoadout>) -> io::Result<usize> {
        self.attach_loadout_fire(identity,session,loadout,None)
    }
    fn attach_loadout_fire(&mut self,identity:Identity,session:u32,
        loadout:Option<crate::battle091::profile13::FrozenLoadout>,initial_fire:Option<fire::State>)->io::Result<usize>{
        if self.mixed_ammo{return Err(bad());}
        if initial_fire.is_some()&&(!self.extended_lab||loadout.is_some()){return Err(bad());}
        if session == 0 || identity.database <= 0 || identity.account.is_empty()
            || self.actors.iter().any(|a| a.session == Some(session)) { return Err(bad()); }
        if let Some(slot) = self.actors.iter().position(|a| a.identity.account == identity.account) {
            let a = &mut self.actors[slot];
            if a.session.is_some() || a.identity != identity || a.owned_loadout != loadout { return Err(bad()); }
            a.session = Some(session); a.ready = false; a.input = Input::STOP; a.speed = 0.; a.aim.park();
            return Ok(slot);
        }
        if self.actors.len() == self.expected_actors || self.actors.iter().any(|a| a.identity.database == identity.database) {
            return Err(bad());
        }
        let slot = self.actors.len();
        let mut origin = SPAWN; origin[0] += if slot == 0 { -4. } else { 4. };
        let kind=loadout.as_ref().map_or(self.vehicle_kind,|v|v.kind);
        let ammo = loadout.as_ref().map_or(kind.initial_ammo(), |value| value.ap_count);
        let fire=if let Some(fire)=initial_fire {
            if fire.typed().is_none_or(|state|state.mount()!=kind.mount()){return Err(bad());}fire
        }else{fire::State::with_mounted_loadout(ammo,kind.reload_seconds(),kind.ammo_limit())?};
        if self.mixed_profiles {
            let mut trace=self.impact.clone();trace.bind_actor(slot,kind)?;
            let mut fragiles=self.fragiles.clone();
            if let Some(state)=&mut fragiles {state.bind_ammo_capacity(kind.ammo_limit())?;}
            self.impact=trace;self.fragiles=fragiles;
        }
        self.actors.push(Actor { identity, session: Some(session), ready: false, health: kind.max_health(), vehicle_kind:kind,
            position: origin, direction: [0.; 3], origin, yaw: 0., speed: 0., input: Input::STOP,
            fire, aim: aim::State::new(), mileage_metres: 0., owned_loadout:loadout,owned_v2:None,owned_loss:None,owned_hold:None,devices:None });
        Ok(slot)
    }
    pub fn start(&mut self, now: Instant) -> io::Result<()> {
        if self.started.is_some() || self.actors.len() != self.expected_actors || now < self.last
            || self.team_plan.is_some()&&self.lifecycle.is_none() { return Err(bad()); }
        if self.ap_test_lab {for actor in &self.actors {self.geometry_for(actor.vehicle_kind())?;}}
        self.started = Some(now); self.last = now; Ok(())
    }
    /// Integrated map-drive owns the initial lane placement. Rebase happens
    /// in the start tick before native arena announcements; after that first
    /// turn all poses come from the workers atomically.
    pub fn rebase_external_spawns<const N:usize>(&mut self, positions: [[f32; 3]; N]) -> io::Result<()> {
        self.rebase_external_spawn_rows(&positions)
    }
    pub fn rebase_external_spawn_rows(&mut self, positions: &[[f32; 3]]) -> io::Result<()> {
        // The integrated runtime calls this in the same loop turn as
        // `start`, before tick 1000 is published or either actor is ready.
        if positions.len()!=self.expected_actors || self.actors.len() != self.expected_actors || self.tick != 1000 || self.actors.iter().any(|actor| actor.ready) { return Err(bad()); }
        for position in positions {
            if position.iter().any(|value| !value.is_finite() || value.abs() > 2000.) { return Err(bad()); }
        }
        for (actor, position) in self.actors.iter_mut().zip(positions.iter().copied()) {
            actor.position = position;
            actor.origin = position;
        }
        Ok(())
    }
    /// SPAWN-15: as `rebase_external_spawn_rows`, also facing each actor along
    /// its formation yaw (Jolt receives the same yaw in the scene manifest).
    pub fn rebase_external_spawn_poses(&mut self, poses: &[([f32; 3], f32)]) -> io::Result<()> {
        if poses.iter().any(|(_,yaw)|!(-std::f32::consts::PI..=std::f32::consts::PI).contains(yaw)) { return Err(bad()); }
        self.rebase_external_spawn_rows(&poses.iter().map(|(p,_)|*p).collect::<Vec<_>>())?;
        for (actor,(_,yaw)) in self.actors.iter_mut().zip(poses) { actor.direction=[*yaw,0.,0.]; actor.yaw=*yaw; }
        Ok(())
    }
    /// A reconnect gets a fresh worker process. Until that worker is settled,
    /// put the actor back on its server-owned lane so a stale parked pose
    /// cannot become a large cross-terrain anchor offset.
    pub fn reset_external_spawn(&mut self, slot: usize, position: [f32; 3]) -> io::Result<()> {
        let actor = self.actors.get_mut(slot).ok_or_else(|| bad())?;
        if actor.session.is_none() || actor.ready || position.iter().any(|value| !value.is_finite() || value.abs() > 2000.) {
            return Err(bad());
        }
        actor.position = position;
        actor.origin = position;
        actor.direction = [0.; 3];
        actor.yaw = 0.;
        actor.speed = 0.;
        Ok(())
    }
    /// Import the first settled worker frame before native arena creation.
    /// This updates pose only; the simulation tick and gameplay state remain
    /// untouched until both native actors have completed their ready contract.
    pub fn import_external_poses(&mut self,
        external: &[(usize, [f32; 3], [f32; 3], f32)]) -> io::Result<()> {
        if external.len() != self.expected_actors || external.iter().map(|row| row.0).collect::<std::collections::BTreeSet<_>>().len() != self.expected_actors {
            return Err(bad());
        }
        let mut next = self.actors.clone();
        for (slot, position, direction, speed) in external {
            let actor = next.get_mut(*slot).ok_or_else(|| bad())?;
            if actor.session.is_none() || position.iter().any(|value| !value.is_finite())
                || direction.iter().any(|value| !value.is_finite()) || !speed.is_finite()
                || direction.iter().any(|value| !(-std::f32::consts::PI..=std::f32::consts::PI).contains(value))
                || !(-25. ..=25.).contains(speed) { return Err(bad()); }
            actor.position = *position;
            actor.direction = *direction;
            actor.yaw = direction[0];
            actor.speed = *speed;
        }
        self.actors = next;
        Ok(())
    }
    /// A joining actor receives a settled pose only after its scene is restored.
    /// The already playing actor and simulation clock remain untouched.
    pub fn import_unready_external_pose(&mut self, slot:usize, position:[f32;3], direction:[f32;3], speed:f32) -> io::Result<()> {
        let actor=self.actors.get_mut(slot).ok_or_else(|| bad())?;
        if actor.ready || actor.session.is_none() || position.iter().any(|v|!v.is_finite() || v.abs()>2000.)
            || direction.iter().any(|v|!v.is_finite() || !(-std::f32::consts::PI..=std::f32::consts::PI).contains(v))
            || !speed.is_finite() || !(-25. ..=25.).contains(&speed) { return Err(bad()); }
        actor.position=position;actor.direction=direction;actor.yaw=direction[0];actor.speed=speed;Ok(())
    }
    pub fn detach(&mut self, session: u32) -> io::Result<()> {
        let a = self.actors.iter_mut().find(|a| a.session == Some(session)).ok_or_else(|| bad())?;
        a.session = None; a.ready = false; a.input = Input::STOP; a.speed = 0.; a.aim.park(); Ok(())
    }
    pub fn owned(&self, slot: usize, session: u32) -> io::Result<&Actor> {
        self.actors.get(slot).filter(|a| a.session == Some(session)).ok_or_else(|| bad())
    }
    pub fn set_ready(&mut self, slot: usize, session: u32) -> io::Result<()> {
        self.owned(slot, session)?; self.actors[slot].ready = true; Ok(())
    }
    pub fn apply(&mut self, slot: usize, session: u32, commands: &[Command], now: Instant)
        -> io::Result<Vec<fire::Outcome>> {
        if self.started.is_none() || now < self.last || commands.len() > MAX_COMMANDS
            || !self.owned(slot, session)?.ready { return Err(bad()); }
        let mut next = self.actors[slot].clone();
        let mut outcomes = Vec::new();
        let mut shots = self.shots.clone();
        let mut projectiles = self.projectiles.clone();
        let mut impact_trace = self.impact.clone();
        for (at, command) in commands.iter().enumerate() {
            if self.lifecycle.as_ref().is_some_and(|state| !state.allows_actions()) {
                match command {
                    Command::Move(input) => { if !input.valid() { return Err(bad()); } continue; },
                    Command::Fire(_) | Command::Armament(_) => { outcomes.push(fire::Outcome::RejectedBattlePeriod); continue; },
                    Command::Aim(_) | Command::Leave => {},
                }
            }
            // Native dead players may still emit neutral input/aim packets.
            // Validate them, then ignore gameplay; leave remains available.
            if !next.alive() {
                match command {
                    Command::Aim(intent) => { intent.validate()?; continue; },
                    Command::Move(input) => {
                        if !input.valid() { return Err(bad()); }
                        continue;
                    },
                    Command::Fire(_) | Command::Armament(_) => {if next.fire.typed().is_some(){outcomes.push(fire::Outcome::RejectedVehicleState);}continue;},
                    Command::Leave => {},
                }
            }
            match command {
                Command::Aim(intent) => next.aim.set(*intent)?,
                Command::Move(input) => {
                    if !input.valid() { return Err(bad()); }
                    next.input = *input;
                },
                Command::Fire(_) | Command::Armament(_) => {
                    let ammo_before = next.fire.ammo();
                    let counts_before=next.fire.typed().map(|state|state.counts());
                    let shooting=matches!(command,Command::Fire(fire::Command::Shoot)|Command::Armament(crate::p06t_armament091::Command::Shoot));
                    if shooting&&next.devices.as_ref().is_some_and(|state|!state.capabilities().can_fire){outcomes.push(fire::Outcome::RejectedVehicleState);continue;}
                    if let Some(state)=next.devices.as_ref(){next.fire.adjust_reload_scale(state.capabilities().reload_scale,now)?;}
                    let result = match command {
                        Command::Fire(command) if next.fire.typed().is_none()=>next.fire.apply(&[*command],now)?,
                        Command::Fire(command)=>next.fire.apply_typed(&[match command{
                            fire::Command::Shoot=>crate::p06t_armament091::Command::Shoot,
                            fire::Command::ReplenishAmmo=>crate::p06t_armament091::Command::Replenish}],now)?,
                        Command::Armament(command)=>next.fire.apply_typed(&[*command],now)?,
                        _=>unreachable!(),
                    };
                    for outcome in &result {
                        let accepted=match *outcome{
                            fire::Outcome::AcceptedShot{ammo_remaining}=>Some((ammo_remaining,None)),
                            fire::Outcome::Typed(crate::p06t_armament091::Outcome::Shot{shell,remaining,..})=>Some((remaining,Some(shell))),
                            _=>None,
                        };
                        if let Some((ammo_remaining,shell))=accepted {
                            if shots.len() >= self.shot_limit() || projectiles.len() >= self.shot_limit() { return Err(bad()); }
                            let sequence = shots.len() as u32 + 1;
                            let projectile = if let Some(shell)=shell{Projectile::launch_shell_for_limit(sequence,slot,&next,now,self.shot_limit(),shell)?}
                                else if self.mixed_profiles {Projectile::launch_for_limit(sequence,slot,&next,now,self.shot_limit())?}
                                else {Projectile::launch(sequence, slot, &next, now)?};
                            let elapsed_ticks = now.duration_since(self.started.ok_or_else(|| bad())?).as_millis() / 100;
                            let launch_tick = 1000u32.checked_add(u32::try_from(elapsed_ticks).map_err(|_| bad())?)
                                .ok_or_else(|| bad())?;
                            if let Some(shell)=shell{
                                let index=crate::p06t_shells091::profile(next.vehicle_kind().mount()).shots.iter().position(|source|*source==shell).ok_or_else(||bad())?;
                                impact_trace.admission_shell(self.id,sequence,launch_tick,slot,counts_before.ok_or_else(||bad())?[index],ammo_remaining,shell)?;
                            }else{impact_trace.admission(self.id, sequence, launch_tick, slot, ammo_before, ammo_remaining)?;}
                            impact_trace.launch(self.id, &projectile, launch_tick)?;
                            shots.push(Shot { sequence, slot, tick: launch_tick });
                            projectiles.push(projectile);
                        }
                    }
                    outcomes.extend(result);
                },
                Command::Leave => {
                    if at + 1 != commands.len() { return Err(bad()); }
                    next.session = None; next.ready = false; next.input = Input::STOP; next.speed = 0.; next.aim.park();
                },
            }
        }
        self.actors[slot] = next; self.shots = shots; self.projectiles = projectiles;
        self.impact = impact_trace; Ok(outcomes)
    }
    /// One shared monotonic clock; bounded integration, no burst catch-up. The
    /// small flat boxes exist only to make remote-state publication observable.
    pub fn advance(&mut self, now: Instant) -> io::Result<bool> {
        self.advance_with_external(now, None)
    }

    /// Advance the shared clock while importing poses from the accepted map
    /// worker. `None` retains the historical bounded laboratory kinematics;
    /// `Some` is used only by the integrated two-client profile. Worker rows
    /// are already validated by the IPC parser and are copied atomically with
    /// the projectile/trace state.
    pub fn advance_with_external(&mut self, now: Instant,
        external: Option<&[(usize, [f32; 3], [f32; 3], f32)]>) -> io::Result<bool> {
        if self.mixed_ammo {
            let mut next=self.clone();let changed=next.advance_inner(now,external)?;*self=next;Ok(changed)
        }else{self.advance_inner(now,external)}
    }
    fn advance_inner(&mut self, now:Instant,external:Option<&[(usize,[f32;3],[f32;3],f32)]>)->io::Result<bool>{
        let Some(start) = self.started else { return Ok(false); };
        if now < self.last || now.duration_since(start) >= LIFETIME { return Err(bad()); }
        if self.lifecycle.as_ref().is_some_and(|state| state.outcome().is_some()) {
            // Outcome/statistics are immutable; late in-flight projectiles do
            // not change HP after the result snapshot has been frozen.
            self.last = now; self.tick = 1000 + (now.duration_since(start).as_millis() / 100) as u32;
            return Ok(false);
        }
        if let Some(rows) = external {
            let slots = rows.iter().map(|row| row.0).collect::<std::collections::BTreeSet<_>>();
            if rows.len() != self.expected_actors || slots.len() != self.expected_actors || slots.iter().any(|slot| *slot >= self.expected_actors) {
                return Err(bad());
            }
            for (slot, position, direction, speed) in rows {
                let actor = self.actors.get(*slot).ok_or_else(|| bad())?;
                // A disconnected actor is parked in the authoritative world;
                // its missing worker must not pause the surviving actor's clock.
                if !self.mixed_profiles && actor.session.is_none() && (*position != actor.position || *direction != actor.direction || *speed != 0.) {
                    return Err(bad());
                }
                if position.iter().any(|v| !v.is_finite()) || direction.iter().any(|v| !v.is_finite()) || !speed.is_finite()
                    || direction.iter().any(|v| !(-std::f32::consts::PI..=std::f32::consts::PI).contains(v))
                    || !(-25. ..=25.).contains(speed) { return Err(bad()); }
            }
        }
        let tick = 1000 + (now.duration_since(start).as_millis() / 100) as u32;
        let tick_changed = tick != self.tick;
        let prior_tick = self.tick;
        let prior_time = self.last;
        let mut next_actors = self.actors.clone();
        let mut next_last = self.last;
        let mut next_tick = self.tick;
        if tick_changed&&self.mixed_ammo{self.drain_fire(&mut next_actors,u64::from(tick-1000)*100)?;}
        if tick_changed {
            let dt = now.duration_since(self.last).as_secs_f32().min(0.2);
            for (slot, a) in next_actors.iter_mut().enumerate() {
                if !a.ready || a.session.is_none() || !a.alive() {
                    // A parked/wreck body stays in the single physical scene and
                    // can be pushed. No disconnected controller gains authority.
                    if self.mixed_profiles {if let Some(rows)=external {let(_,position,direction,speed)=rows.iter().find(|(row,..)|*row==slot).ok_or_else(||bad())?;
                        a.position=*position;a.direction=*direction;a.yaw=direction[0];a.speed=*speed;}}
                    continue;
                }
                let previous_position = a.position;
                if let Some(rows) = external {
                    if let Some((_, position, direction, speed)) = rows.iter().find(|(row, ..)| *row == slot) {
                        a.position = *position; a.direction = *direction; a.yaw = direction[0]; a.speed = *speed;
                    }
                } else {
                    a.yaw = (a.yaw + a.input.steer as f32 * dt * 0.5 + std::f32::consts::PI)
                        .rem_euclid(2. * std::f32::consts::PI) - std::f32::consts::PI;
                    a.direction = [a.yaw, 0., 0.];
                    let before = a.position;
                    a.position[0] = (a.position[0] + a.yaw.sin() * a.input.throttle as f32 * dt)
                        .clamp(a.origin[0] - 2., a.origin[0] + 2.);
                    a.position[2] = (a.position[2] + a.yaw.cos() * a.input.throttle as f32 * dt)
                        .clamp(a.origin[2] - 2., a.origin[2] + 2.);
                    a.speed = if before != a.position { a.input.throttle as f32 } else { 0. };
                }
                a.direction[0] = a.yaw;
                if self.lifecycle.as_ref().is_some_and(|state| state.allows_actions()) && a.alive() {
                    let distance = (0..3).map(|i| (f64::from(a.position[i]) - f64::from(previous_position[i])).powi(2)).sum::<f64>().sqrt();
                    a.mileage_metres += distance;
                    if !a.mileage_metres.is_finite() || a.mileage_metres > 200_000. { return Err(bad()); }
                }
                if a.alive() {
                    if let Some(armament)=a.fire.typed(){
                        let caps=a.devices.as_ref().ok_or_else(||bad())?.capabilities();
                        a.aim.advance_pose_for_selected(a.vehicle_kind,a.position,a.direction,dt,armament.current(),caps)?;
                    }else{a.aim.advance_pose_for(a.vehicle_kind,a.position,a.direction,dt)?;}
                }
            }
            next_last = now; next_tick = tick;
        }
        let mut impact_trace = self.impact.clone();
        let mut next_projectiles = self.projectiles.clone();
        let mut contacts = self.contacts.clone();
        let mut impacts = self.impacts.clone();
        let mut terrain_contacts = self.terrain_contacts.clone();
        let mut next_destructible = self.destructible.clone();
        let mut next_fragiles=self.fragiles.clone();
        if tick_changed {
            'projectile_loop: for projectile in &mut next_projectiles {
                if !projectile.stopped {
                    let shot_tick = self.shots.iter()
                        .find(|shot| shot.sequence == projectile.sequence).ok_or_else(|| bad())?.tick;
                    // The integrated runtime advances only after both workers reply, so
                    // a shot can be admitted in a wall bucket the world has not reached.
                    // An update in that same bucket has no tick interval for it; the
                    // first segment waits for the next update and still starts at launch
                    // (an empty interval stopped the server in is7c17owner01).
                    if shot_tick >= tick { continue; }
                    let first = impact_trace.last_segment_end(projectile.sequence).is_none();
                    let mut segment_start = if first || projectile.launched > prior_time { projectile.launched } else { prior_time };
                    let segment_limit = now.min(projectile.end_at()?);
                    let mut segment_tick_start = shot_tick.max(prior_tick);
                    while segment_start < segment_limit {
                        // Terrain-enabled flight keeps the nominal chord error
                        // bounded even after a delayed server poll. These are
                        // subsegments of one update, not invented world ticks.
                        let segment_end = if self.terrain.is_some() {
                            segment_limit.min(segment_start.checked_add(STEP).ok_or_else(|| bad())?)
                        } else { segment_limit };
                        let start_point = projectile.position_at(segment_start);
                        let end_point = projectile.position_at(segment_end);
                        impact_trace.segment(self.id, projectile.sequence, tick, segment_tick_start,
                            start_point, end_point)?;
                        if self.geometry.is_some() {
                            let mut target_slot = 1usize.checked_sub(projectile.slot).unwrap_or(0);
                            if self.mixed_profiles {
                                let mut selected:Option<(f32,usize)>=None;
                                for (slot,actor) in next_actors.iter().enumerate().filter(|(slot,_)|*slot!=projectile.slot) {
                                    let mesh=self.geometry_for(actor.vehicle_kind())?.world_mesh(actor,slot,tick)?;
                                    let hits=super::collision::query(&mesh,start_point,end_point)?;
                                    let t=hits.first().map_or(f32::INFINITY,|hit|hit.t);
                                    if selected.is_none_or(|(old_t,old_slot)|t<old_t||(t==old_t&&slot<old_slot)){selected=Some((t,slot));}
                                }
                                target_slot=selected.ok_or_else(||bad())?.1;
                            }
                            let target = next_actors.get(target_slot).ok_or_else(|| bad())?.clone();
                            let bundle=self.geometry_for(target.vehicle_kind())?.clone();
                            let mesh = bundle.world_mesh(&target, target_slot, tick)?;
                            let (hits, material_facts, ground) = if let Some(terrain) = &self.terrain {
                                if let Some(state)=&next_destructible {
                                    impact_trace.collision_query_world_filtered(self.id,projectile.sequence,tick,&mesh,bundle.materials(),terrain,
                                        state.scene_version(),state.excluded_instance())?
                                } else {
                                    impact_trace.collision_query_world(self.id, projectile.sequence, tick,
                                        &mesh, bundle.materials(), terrain)?
                                }
                            } else {
                                let (hits, material) = impact_trace.collision_query_classified(
                                    self.id, projectile.sequence, tick, &mesh, bundle.materials())?;
                                (hits, material, None)
                            };
                            // Both candidates refer to the same original flight chord.
                            // Compare in the vehicle query's f32 parameter domain:
                            // terrain wins a shared rounding bucket, no epsilon.
                            if ground.as_ref().is_some_and(|g| hits.first().is_none_or(|v| (g.t as f32) <= v.t)) {
                                if terrain_contacts.len() >= self.shot_limit() { return Err(bad()); }
                                let hit = impact_trace.terrain_contact(self.id, projectile.sequence, tick)?;
                                let chord: [f64; 3] = std::array::from_fn(|i| f64::from(end_point[i])-f64::from(start_point[i]));
                                let length = chord.iter().map(|v| v*v).sum::<f64>().sqrt();
                                if !length.is_finite() || length <= 0. { return Err(bad()); }
                                terrain_contacts.push(TerrainContact { shot: projectile.sequence,
                                    shooter: projectile.slot, tick, hit, segment_start: start_point,
                                    segment_end: end_point, direction: chord.map(|v| (v/length) as f32) });
                                if let Some(state)=&mut next_destructible {
                                    if let Some(transition)=state.contact(projectile.sequence,projectile.slot,tick,hit)? {
                                        impact_trace.destructible_transition(self.id,projectile.sequence,tick,&transition)?;
                                    }
                                }
                                if let Some(state)=&mut next_fragiles {
                                    let damaged=if let Some(shell)=projectile.shell{state.contact_shell_for(projectile.vehicle_kind,shell,projectile.sequence,projectile.slot,tick,hit)?}
                                        else{state.contact_for(projectile.vehicle_kind,projectile.sequence,projectile.slot,tick,hit)?};
                                    if let Some(damage)=damaged{
                                        impact_trace.fragile_damage(self.id,projectile.sequence,tick,&damage)?;
                                    }
                                }
                                projectile.terminal = hit.point; projectile.stopped = true;
                                if projectile.shell.is_some(){self.explode_mixed(&mut next_actors,&mut impact_trace,projectile,hit.point,tick,None,next_fragiles.as_ref())?;}
                                impact_trace.terminal(self.id, projectile.sequence, tick, impact::TerminalReason::TerrainCollision)?;
                                continue 'projectile_loop;
                            }
                            if let Some(nearest) = hits.first() {
                                let endpoint = std::array::from_fn(|i|
                                    start_point[i] + nearest.t * (end_point[i] - start_point[i]));
                                if contacts.len() >= self.shot_limit() { return Err(bad()); }
                                let contact = Contact { shot: projectile.sequence, target_slot, tick,
                                    segment_start: start_point, segment_end: end_point,
                                    segment_seconds: segment_end.duration_since(segment_start).as_secs_f32(), endpoint,
                                    target_position: target.position, target_direction: target.direction,
                                    target_aim: [target.aim.yaw, target.aim.pitch], triangle: nearest.clone(),
                                    geometry_revision: mesh.geometry_revision().into(),
                                    transform_revision: mesh.transform_revision().into(),
                                    material_facts: material_facts.ok_or_else(|| bad())? };
                                let mut terminal_reason = impact::TerminalReason::UnresolvedCollision;
                                if projectile.shell.is_some()&&target.alive(){
                                    if impacts.len()>=self.shot_limit(){return Err(bad());}
                                    let before=target.health;
                                    let resolution=self.direct_mixed(&mut next_actors,&mut impact_trace,projectile,&contact,&bundle)?;
                                    let segment=if matches!(resolution.decision,crate::p06t_damage::Decision::Unsupported|crate::p06t_damage::Decision::OutOfRange){None}
                                        else{Some(bundle.impact_segment(&contact)?)};
                                    impacts.push(AppliedImpact{shot:projectile.sequence,attacker:projectile.slot,target:target_slot,tick,
                                        outcome:ImpactOutcome::Mixed(resolution),health_before:before,
                                        health_after:before.saturating_sub(resolution.damage_hp as i16).max(0),segment});
                                    terminal_reason=impact::TerminalReason::TestLabMixedImpact;
                                }else if self.ap_test_lab && target.alive() {
                                    if impacts.len() >= self.shot_limit() { return Err(bad()); }
                                    let distance = (0..3).map(|i| {
                                        let delta = f64::from(endpoint[i]) - f64::from(projectile.origin[i]);
                                        delta * delta
                                    }).sum::<f64>().sqrt();
                                    let resolution = ap::resolve_for_pair(projectile.vehicle_kind,target.vehicle_kind(),ap::Input {
                                        material: &contact.material_facts,
                                        segment_direction: std::array::from_fn(|i| end_point[i] - start_point[i]),
                                        winding_normal: nearest.normal, distance,
                                    })?;
                                    let before = target.health;
                                    let after = (before - resolution.damage as i16).max(0);
                                    // Unsupported surfaces have no fabricated native outcome.
                                    let segment = if matches!(resolution.outcome, ap::Outcome::Unsupported(_)) { None }
                                        else { Some(bundle.impact_segment(&contact)?) };
                                    impact_trace.ap_resolution(self.id, projectile.sequence, tick,
                                        projectile.slot, target_slot, &resolution, before, after)?;
                                    impacts.push(AppliedImpact { shot: projectile.sequence,
                                        attacker: projectile.slot, target: target_slot, tick,
                                        outcome: ImpactOutcome::Ap(resolution),
                                        health_before: before, health_after: after, segment });
                                    let damaged = next_actors.get_mut(target_slot).ok_or_else(|| bad())?;
                                    damaged.health = after;
                                    if after == 0 {
                                        damaged.input = Input::STOP; damaged.speed = 0.; damaged.aim.park();
                                    }
                                    terminal_reason = impact::TerminalReason::TestLabImpact;
                                } else if projectile.shell.is_some()&&!target.alive(){
                                    if impacts.len()>=self.shot_limit(){return Err(bad());}
                                    let segment=Some(bundle.impact_segment(&contact)?);
                                    impact_trace.wreck_inactive(self.id,projectile.sequence,tick,projectile.slot,target_slot,
                                        target.health,target.health,&target)?;
                                    impacts.push(AppliedImpact{shot:projectile.sequence,attacker:projectile.slot,target:target_slot,tick,
                                        outcome:ImpactOutcome::WreckBlocked,health_before:target.health,health_after:target.health,segment});
                                    terminal_reason=impact::TerminalReason::TestLabWreckImpact;
                                } else if self.ap_test_lab && target.health == 0 {
                                    if impacts.len() >= self.shot_limit() { return Err(bad()); }
                                    // Retained geometry blocks a shell on an already dead actor.
                                    // Require the same validated native segment, but never run
                                    // the live-armor resolver or mutate health/death/input state.
                                    let segment = Some(bundle.impact_segment(&contact)?);
                                    impact_trace.wreck_impact(self.id, projectile.sequence, tick,
                                        projectile.slot, target_slot, 0, 0)?;
                                    impacts.push(AppliedImpact { shot: projectile.sequence,
                                        attacker: projectile.slot, target: target_slot, tick,
                                        outcome: ImpactOutcome::WreckBlocked,
                                        health_before: 0, health_after: 0, segment });
                                    terminal_reason = impact::TerminalReason::TestLabWreckImpact;
                                }
                                contacts.push(contact);
                                projectile.terminal = endpoint; projectile.stopped = true;
                                if projectile.shell.is_some(){self.explode_mixed(&mut next_actors,&mut impact_trace,projectile,endpoint,tick,Some(target_slot),next_fragiles.as_ref())?;}
                                impact_trace.terminal(self.id, projectile.sequence, tick,
                                    terminal_reason)?;
                                continue 'projectile_loop;
                            }
                        }
                        segment_start = segment_end;
                        segment_tick_start = tick;
                    }
                }
            }
        }
        let mut expired = false;
        for projectile in &mut next_projectiles {
            // Geometry must inspect the clamped tail before range expiry. A
            // 5ms poll between the last 100ms segment and end_at may otherwise
            // drop up to ~35m without ever querying it.
            if !projectile.stopped && projectile.is_expired(now)? && (self.geometry.is_none() || tick_changed) {
                projectile.stopped = true;
                impact_trace.terminal(self.id, projectile.sequence, tick,
                    impact::TerminalReason::RangeExpired)?;
                expired = true;
            }
        }
        if self.mixed_ammo{for actor in &mut next_actors{if let Some(state)=actor.devices.as_ref(){
            actor.fire.adjust_reload_scale(state.capabilities().reload_scale,now)?;
        }}}
        self.actors = next_actors;
        self.last = next_last;
        self.tick = next_tick;
        self.projectiles = next_projectiles;
        self.impact = impact_trace;
        self.contacts = contacts;
        self.impacts = impacts;
        self.terrain_contacts = terrain_contacts;
        self.destructible = next_destructible;
        self.fragiles=next_fragiles;
        Ok(tick_changed || expired)
    }
}

#[cfg(test)]
#[path="model_scene_tests.rs"]
mod scene_tests;
#[cfg(test)]
#[path="visibility_world_tests.rs"]
mod visibility_world_tests;
#[cfg(test)]
#[path="spotting_world_tests.rs"]
mod spotting_world_tests;

#[cfg(test)]
#[path="p04m_capacity_tests.rs"]
mod p04m_capacity_tests;
#[cfg(test)]
pub(super) mod tests {
    use super::*;
    /// Explicit physics laboratory fixture. It never manufactures an owned
    /// receipt or bypasses the production admission check in attach_owned.
    pub(crate) fn attach_physics_profile(world:&mut World,kind:VehicleKind,
        identity:Identity,session:u32)->io::Result<usize> {
        if !world.mixed_profiles || world.started.is_some() {return Err(bad());}
        let previous=world.vehicle_kind;
        world.vehicle_kind=kind;
        let result=world.attach_loadout(identity,session,None);
        world.vehicle_kind=previous;
        result
    }
    pub(crate) fn profile13_loadout(kind:VehicleKind,slot:usize,ap_count:u16)
        ->(Identity,crate::battle091::profile13::FrozenLoadout) {
        use sha2::{Digest,Sha256};
        let account=format!("{:08x}-1234-4234-8234-123456789abc",slot+1);
        let native_inventory_id=if kind==VehicleKind::Ms1{1}else{2};
        let vehicle_inventory_id=format!("{account}:{}",if kind==VehicleKind::Ms1{"starter-vehicle-v1"}else{"test-is7-v1"});
        let shell_definition_id=format!("shell:{}-stock-ap",kind.label());
        let crew_ids=(0..if kind==VehicleKind::Ms1{2}else{5}).map(|n|format!("{account}:crew:{n}")).collect::<Vec<_>>();
        let descriptor=kind.descriptor().to_vec();
        let value=serde_json::json!({"kind":kind.label(),"descriptor_hex":descriptor.iter().map(|b|format!("{b:02x}")).collect::<String>(),
            "native_inventory_id":native_inventory_id,"vehicle_inventory_id":vehicle_inventory_id,
            "ap_count":ap_count,"shell_definition_id":shell_definition_id,"shell_compact_id":kind.shell_compact_id(),
            "max_hp":kind.max_health(),"crew_ids":crew_ids});
        let sha256=format!("{:x}",Sha256::digest(serde_json::to_vec(&value).unwrap()));
        (Identity{account,database:slot as i32+1,name:format!("owned-{slot}")},crate::battle091::profile13::FrozenLoadout{
            kind,descriptor,native_inventory_id,vehicle_inventory_id,ap_count,shell_definition_id,
            shell_compact_id:kind.shell_compact_id(),max_hp:kind.max_health(),crew_ids,sha256})
    }
    #[test] fn profile13_owned_counts_survive_peer_leave_and_same_receipt_rejoin_without_refill() {
        for kind in [VehicleKind::Ms1,VehicleKind::Is7] {
            let now=Instant::now();let mut world=World::new_for_vehicle(91,now,crate::map_profile091::MapId::Prohorovka,kind).unwrap();
            let (first,first_loadout)=profile13_loadout(kind,0,7);
            let (second,second_loadout)=profile13_loadout(kind,1,11);
            assert_eq!(world.attach_owned(first.clone(),1,&first_loadout).unwrap(),0);
            assert_eq!(world.attach_owned(second.clone(),2,&second_loadout).unwrap(),1);
            world.start(now).unwrap();world.set_ready(0,1).unwrap();world.set_ready(1,2).unwrap();
            for slot in 0..2 {world.apply(slot,slot as u32+1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();}
            assert_eq!((world.actors[0].fire.ammo(),world.actors[1].fire.ammo()),(6,10));
            let first_fire=world.actors[0].fire.clone();let second_fire=world.actors[1].fire.clone();
            world.apply(1,2,&[Command::Leave],now).unwrap();
            assert_eq!(world.actors[0].fire,first_fire);
            assert!(world.attach(second.clone(),3).is_err());
            let (_,changed)=profile13_loadout(kind,1,12);
            assert!(world.attach_owned(second.clone(),3,&changed).is_err());
            assert_eq!(world.attach_owned(second,3,&second_loadout).unwrap(),1);
            assert_eq!(world.actors[1].fire,second_fire);assert_eq!(world.actors[0].fire,first_fire);
            let binding=super::super::wire::binding(&world,1,now).unwrap();
            let rows=&binding[binding.len()-54..binding.len()-21];
            assert_eq!(&rows[2..6],&kind.shell_compact_id().to_le_bytes());
            assert_eq!(&rows[6..8],&10u16.to_le_bytes());
        }
    }
    #[test] fn profile13_owned_admission_rejects_foreign_changed_descriptor_kind_and_overflow_atomically() {
        let now=Instant::now();
        for kind in [VehicleKind::Ms1,VehicleKind::Is7] {
            let (identity,loadout)=profile13_loadout(kind,0,7);
            for change in 0..8 {
                let mut world=World::new_for_vehicle(92,now,crate::map_profile091::MapId::Prohorovka,kind).unwrap();
                let mut wrong=loadout.clone();let mut who=identity.clone();
                match change {
                    0=>wrong.descriptor[0]^=1,1=>wrong.kind=if kind==VehicleKind::Ms1{VehicleKind::Is7}else{VehicleKind::Ms1},
                    2=>wrong.ap_count=0,3=>wrong.ap_count=kind.ammo_limit()+1,4=>wrong.max_hp+=1,
                    5=>wrong.shell_compact_id+=1,6=>who.account="foreign".into(),7=>wrong.sha256="0".repeat(64),_=>unreachable!(),
                }
                assert!(world.attach_owned(who,1,&wrong).is_err(),"kind={kind:?} mutation={change}");
                assert!(world.actors.is_empty());assert!(world.shots.is_empty());
            }
            let other=if kind==VehicleKind::Ms1{VehicleKind::Is7}else{VehicleKind::Ms1};
            let (identity,other_loadout)=profile13_loadout(other,0,7);
            let mut world=World::new_for_vehicle(93,now,crate::map_profile091::MapId::Prohorovka,kind).unwrap();
            assert!(world.attach_owned(identity,1,&other_loadout).is_err());assert!(world.actors.is_empty());
        }
    }
    #[test] fn profile13_two_full_ms1_loadouts_fire_all_192_owned_rounds_without_history_truncation() {
        let now=Instant::now();let mut world=World::new(94,now).unwrap();
        for slot in 0..2 {let (identity,loadout)=profile13_loadout(VehicleKind::Ms1,slot,96);
            world.attach_owned(identity,slot as u32+1,&loadout).unwrap();}
        world.start(now).unwrap();world.set_ready(0,1).unwrap();world.set_ready(1,2).unwrap();
        for round in 0..96u64 {for slot in 0..2 {
            let result=world.apply(slot,slot as u32+1,&[Command::Fire(fire::Command::Shoot)],now+Duration::from_secs(round*3)).unwrap();
            assert_eq!(result,vec![fire::Outcome::AcceptedShot{ammo_remaining:95-round as u16}]);
        }}
        assert_eq!(world.shots.len(),192);assert_eq!(world.projectiles.len(),192);
        assert_eq!(world.impact.events().iter().filter(|event|matches!(event,impact::Event::Admission{..})).count(),192);
        super::super::wire::tracer_start(world.projectiles.last().unwrap()).unwrap();
        for slot in 0..2 {assert_eq!(world.actors[slot].fire.ammo(),0);
            assert_eq!(world.apply(slot,slot as u32+1,&[Command::Fire(fire::Command::Shoot)],now+Duration::from_secs(288)).unwrap(),
                vec![fire::Outcome::RejectedNoAmmo]);}
        assert_eq!(world.shots.len(),MAX_SHOTS);assert_eq!(VehicleKind::Ms1.battle_shot_limit(),MAX_SHOTS);
    }
    #[test]
    fn contract_error_identifies_direct_and_lazy_call_sites() {
        let direct_line = line!() + 1;
        let direct = bad();
        assert_eq!(direct.kind(), io::ErrorKind::InvalidData);
        assert!(direct.to_string().contains(&format!("{}:{}:", file!(), direct_line)));

        let lazy_line = line!() + 1;
        let lazy = None::<()>.ok_or_else(|| bad()).unwrap_err();
        assert_eq!(lazy.kind(), io::ErrorKind::InvalidData);
        assert!(lazy.to_string().contains(&format!("{}:{}:", file!(), lazy_line)));
        assert_ne!(direct.to_string(), lazy.to_string());
    }
    #[test]fn tank_ram_damages_once_per_contact_and_rearms_after_separation(){
        let now=Instant::now();let mut w=World::new_for_roster(401,now,crate::map_profile091::MapId::Prohorovka,2).unwrap();
        attach_physics_profile(&mut w,VehicleKind::Ms1,Identity{account:"a".into(),database:1,name:"a".into()},1).unwrap();attach_physics_profile(&mut w,VehicleKind::Is7,Identity{account:"b".into(),database:2,name:"b".into()},2).unwrap();
        let c=TankContactInput{slot_a:0,slot_b:1,substep:1,point:[0.,1.,0.],normal:[1.,0.,0.],relative_velocity:[5.,0.,0.]};let before=w.actors.iter().map(|a|a.health).collect::<Vec<_>>();w.apply_tank_contacts(&[c],1,1006).unwrap();let after=w.actors.iter().map(|a|a.health).collect::<Vec<_>>();
        assert!(after[0]<before[0]&&after[1]<before[1]);assert_eq!(w.ram_damage_events.len(),2);w.apply_tank_contacts(&[c],2,1012).unwrap();assert_eq!(w.ram_damage_events.len(),2);w.apply_tank_contacts(&[],3,1018).unwrap();w.apply_tank_contacts(&[c],4,1024).unwrap();assert_eq!(w.ram_damage_events.len(),4);
    }
    #[test]fn tank_ram_batch_is_atomic_on_duplicate_or_bad_geometry(){
        let now=Instant::now();let mut w=World::new_for_roster(402,now,crate::map_profile091::MapId::Prohorovka,2).unwrap();attach_physics_profile(&mut w,VehicleKind::Ms1,Identity{account:"a".into(),database:1,name:"a".into()},1).unwrap();attach_physics_profile(&mut w,VehicleKind::Is7,Identity{account:"b".into(),database:2,name:"b".into()},2).unwrap();let c=TankContactInput{slot_a:0,slot_b:1,substep:1,point:[0.,1.,0.],normal:[1.,0.,0.],relative_velocity:[5.,0.,0.]};assert!(w.apply_tank_contacts(&[c,c],1,1006).is_err());assert!(w.ram_damage_events.is_empty());let mut badc=c;badc.normal=[2.,0.,0.];assert!(w.apply_tank_contacts(&[badc],1,1006).is_err());assert!(w.ram_damage_events.is_empty());
    }
    #[test]fn shot_while_world_lags_wall_bucket_keeps_a_nonempty_first_segment(){
        let now=Instant::now();let mut w=world(now);w.advance(now+STEP).unwrap();assert_eq!(w.tick,1001);
        // Real time is already in bucket 1002 while the world is still at 1001.
        let late=now+STEP*2+Duration::from_millis(10);
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],late).unwrap();assert_eq!(w.shots[0].tick,1002);
        // The next world update lands in the same wall bucket as the shot: no
        // empty interval and no error, the first segment is deferred.
        w.advance(late+Duration::from_millis(20)).unwrap();assert_eq!(w.tick,1002);
        assert!(!w.impact.events().iter().any(|e|matches!(e,impact::Event::Segment{..})));
        w.advance(now+STEP*3).unwrap();assert_eq!(w.tick,1003);
        let launched=w.projectiles[0].position_at(w.projectiles[0].launched);
        assert!(w.impact.events().iter().any(|e|matches!(e,impact::Event::Segment{shot_id:1,segment_tick_start:1002,segment_tick_end:1003,start,..} if *start==launched)));
    }
    pub fn world(now: Instant) -> World {
        let mut w = World::new(123, now).unwrap();
        for i in 0..2 { w.attach(Identity { account: format!("owned-{i}"), database: i + 1,
            name: format!("player_{i}") }, i as u32 + 1).unwrap(); }
        w.start(now).unwrap(); w.set_ready(0, 1).unwrap(); w.set_ready(1, 2).unwrap(); w
    }
    pub fn collision_world(now: Instant, miss: bool) -> World {
        let mut w = world(now);
        w.geometry = Some(Arc::new(super::super::geometry::tests::bundle()));
        for i in 0..2 {
            let p = if i == 0 { [0.; 3] } else if miss { [100., 0., 0.] } else { [0., 0., 10.] };
            w.actors[i].position = p; w.actors[i].origin = p;
            w.actors[i].yaw = if i == 1 && !miss { -std::f32::consts::PI } else { 0. };
            w.actors[i].direction = [w.actors[i].yaw, 0., 0.];
        }
        w
    }
    pub fn ap_world(now: Instant) -> World {
        let mut w = collision_world(now, false); w.ap_test_lab = true; w
    }
    pub fn terrain_world(now: Instant, offset: f32) -> World {
        let mut w = ap_world(now);
        // Plane y=z-offset across the test arena. The genuine MS-1 mesh
        // remains at z10; offset3 puts ground first, offset20 puts armor first.
        w.terrain = Some(Arc::new(super::super::terrain::tests::fixture(-1000.,2000.,2,
            vec![-1000.-offset,-1000.-offset,1000.-offset,1000.-offset])));
        w
    }
    pub fn obstacle_world(now: Instant, offset: f32, wall_z: f32) -> World {
        let mut w=terrain_world(now,offset);
        let obstacles=super::super::obstacles::tests::fixture(vec![
            [[-20.,-20.,wall_z],[20.,-20.,wall_z],[0.,20.,wall_z]]]);
        let terrain=(*w.terrain.take().unwrap()).clone().with_obstacles(Arc::new(obstacles)).unwrap();
        w.terrain=Some(Arc::new(terrain)); w
    }
    pub fn destructible_terrain()->Arc<terrain::Terrain>{
        static SOURCE:std::sync::OnceLock<Arc<terrain::Terrain>>=std::sync::OnceLock::new();
        SOURCE.get_or_init(||{
            let root=std::env::var_os("WOT091_ROOT").map(std::path::PathBuf::from)
                .unwrap_or_else(||std::path::PathBuf::from(r"D:\WoT_9.1_Server"));
            let obstacles=super::super::obstacles::Obstacles::load(&root.join("local"),&root.join(
                "local/evidence/20261010-p06m-terrain-impact-01/projectile-obstacles01/01_karelia/manifest.json")).unwrap();
            // Real source obstacle triangles over a deliberately low synthetic
            // ground. This isolates object state; native terrain acceptance is separate.
            Arc::new(super::super::terrain::tests::fixture(-1000.,2000.,2,vec![-100.;4])
                .with_obstacles(Arc::new(obstacles)).unwrap())
        }).clone()
    }
    pub fn destructible_world(now:Instant)->World{
        let mut w=ap_world(now);w.terrain=Some(destructible_terrain());w.destructible=Some(destructible::State::default());
        for slot in 0..2 {
            let pos=if slot==0 {[-402.07458,55.34893,-412.]}else{[-380.,55.34893,-410.]};
            w.actors[slot].position=pos;w.actors[slot].origin=pos;w.actors[slot].direction=[0.;3];w.actors[slot].yaw=0.;
        }w
    }
    pub fn fragile_world(now:Instant,health:Option<u32>)->World{
        let mut w=destructible_world(now);w.destructible=None;
        let mut catalog=(*super::super::fragiles::tests::catalog()).clone();
        if let Some(h)=health{catalog.objects.iter_mut().find(|o|o.instance_id==1513).unwrap().health=h;}
        let catalog=Arc::new(catalog);catalog.bind_geometry(w.terrain.as_ref().unwrap()).unwrap();
        w.impact.bind_fragiles(catalog.clone()).unwrap();w.fragiles=Some(fragiles::State::new(catalog));w
    }
    pub fn contact_world(now:Instant)->World{
        let mut w=destructible_world(now);w.destructible=None;
        let catalog=super::super::fragiles::tests::contact_catalog();
        catalog.bind_geometry(w.terrain.as_ref().unwrap()).unwrap();
        w.impact.bind_fragiles(catalog.clone()).unwrap();w.fragiles=Some(fragiles::State::new(catalog));w
    }
    #[test]
    fn world_rejects_terrain_and_fragile_catalog_from_another_map() {
        let now=Instant::now();
        let mut world=World::new_for_map(73,now,crate::map_profile091::MapId::Prohorovka).unwrap();
        world.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).unwrap();
        world.enable_ap_test_lab().unwrap();
        let wrong=Arc::new(super::super::terrain::tests::fixture(0.,1.,2,vec![0.;4]));
        assert!(world.bind_terrain(wrong).is_err());
        let right=Arc::new(super::super::terrain::tests::actual_prohorovka().clone());
        world.bind_terrain(right).unwrap();
        assert!(world.bind_destructible_test_lab().is_err());
        assert!(world.bind_fragiles(super::super::fragiles::tests::catalog()).is_err());
    }
    #[test]
    fn vehicle_contact_batch_is_atomic_when_a_later_row_is_invalid() {
        let now=Instant::now();let mut w=contact_world(now);
        let before_fragiles=w.fragiles.clone();let before_impact=w.impact.clone();
        let valid=VehicleContactInput{object_id:1513,substep:1,point:[0.,0.,0.],
            normal:[1.,0.,0.],velocity:[2.,0.,0.],mass_kg:4691.,kind:"hull".into(),shooter:0,proof:None};
        let invalid=VehicleContactInput{object_id:9999,..valid.clone()};
        assert!(w.apply_vehicle_contacts(&[valid.clone(),invalid]).is_err());
        assert_eq!(w.fragiles,before_fragiles);
        assert_eq!(w.impact,before_impact);
        let events=w.apply_vehicle_contacts(&[valid]).unwrap();
        assert_eq!(events.len(),1);
        assert_eq!(w.fragiles.as_ref().unwrap().removed_ids(),vec![1513]);
        assert_eq!(w.impact.events().iter().filter(|e|matches!(e,impact::Event::VehicleContact{..})).count(),1);
    }
    #[test]
    fn column_contacts_commit_atomically_and_trace_replays_the_same_fall() {
        let now=Instant::now();let mut w=destructible_world(now);w.destructible=None;
        let catalog=super::super::fragiles::column_tests::column_catalog();
        catalog.bind_geometry(w.terrain.as_ref().unwrap()).unwrap();
        w.impact.bind_fragiles(catalog.clone()).unwrap();w.fragiles=Some(fragiles::State::new(catalog));
        let before=(w.fragiles.clone(),w.impact.clone());
        let fall=ColumnContactInput{object_id:1601,shooter:0,substep:2,point:[0.;3],normal:[0.,0.,1.],velocity:[0.,0.,5.],mass_kg:68190.};
        let bad_row=ColumnContactInput{object_id:1513,..fall.clone()};
        assert!(w.apply_column_contacts(&[fall.clone(),bad_row]).is_err());
        assert_eq!((w.fragiles.clone(),w.impact.clone()),before);
        let slow=ColumnContactInput{velocity:[0.,0.,1.],..fall.clone()};
        assert!(w.apply_column_contacts(&[slow]).unwrap().is_empty());
        let events=w.apply_column_contacts(&[fall.clone()]).unwrap();
        assert_eq!(events.len(),1);assert_eq!(events[0].fallen_column,Some(0x0782));
        assert_eq!(w.scene_version(),1);
        assert_eq!(w.impact.events().iter().filter(|e|matches!(e,impact::Event::VehicleContact{..})).count(),1);
        // A forged trace row (proof on a column, or a different packed value) is refused.
        let mut forged=events[0].clone();forged.fallen_column=Some(0x0783);
        let mut trace=before.1.clone();assert!(trace.vehicle_contact(w.id,forged.tick,&forged).is_err());
        assert!(w.apply_column_contacts(&[fall]).unwrap().is_empty());
    }
    #[test]fn imported_object_partial_health_preserves_geometry_until_death_and_next_shell_passes(){
        let now=Instant::now();let mut w=fragile_world(now,Some(32));
        for shot in 0..3{
            let at=now+Duration::from_secs(shot*3);if shot>0{w.advance(at).unwrap();}
            w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],at).unwrap();w.advance(at+STEP).unwrap();
            let state=w.fragiles.as_ref().unwrap();
            assert_eq!(state.scene_version(),u32::from(shot>0));
            if shot<2{let damage=state.events.last().unwrap();assert_eq!(damage.instance_id,1513);
                assert_eq!(damage.health_after,if shot==0{2}else{0});assert!(w.projectiles[shot as usize].stopped);
                assert_eq!(damage.hit.point,w.projectiles[shot as usize].terminal);}
            else{assert_eq!(state.events.len(),2);assert!(!w.terrain_contacts.iter().any(|c|c.shot==3&&matches!(c.hit.surface,terrain::Surface::StaticObstacle{instance_id:1513,..})));}
            assert_eq!(state.removed_ids(),if shot==0{vec![]}else{vec![1514]});
        }
        assert_eq!(w.actors[0].fire.ammo(),17);assert_eq!(w.actors[1].health,90);
        assert_eq!(w.fragiles.as_ref().unwrap().native_destroyed(31354),vec![1]);
        let identity=w.actors[0].identity.clone();w.detach(1).unwrap();w.attach(identity,3).unwrap();assert_eq!(w.scene_version(),1);
    }
    #[test]fn imported_same_tick_and_failed_second_flight_are_transactional(){
        let now=Instant::now();let mut w=fragile_world(now,None);
        w.actors[1].position=w.actors[0].position;w.actors[1].origin=w.actors[0].origin;
        for slot in 0..2{w.apply(slot,slot as u32+1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();}
        for actor in &mut w.actors{actor.position[0]+=30.;actor.origin=actor.position;}
        let mut failed=w.clone();failed.projectiles[1].velocity[0]=f32::NAN;let before=failed.clone();
        assert!(failed.advance(now+STEP).is_err());assert_eq!(failed.fragiles,before.fragiles);assert_eq!(failed.impact,before.impact);assert_eq!(failed.actors,before.actors);
        w.advance(now+STEP).unwrap();assert_eq!(w.scene_version(),1);assert_eq!(w.fragiles.as_ref().unwrap().events.len(),1);
        assert!(w.impact.events().iter().any(|e|matches!(e,impact::Event::TerrainQuery{shot_id:2,scene_version:1,excluded_instances,..} if excluded_instances==&vec![1513])));
    }
    #[test]fn destructible_requires_explicit_prestart_terrain_ap_and_cannot_be_rebound(){
        let now=Instant::now();let mut w=World::new(77,now).unwrap();assert!(w.bind_destructible_test_lab().is_err());
        w.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).unwrap();assert!(w.bind_destructible_test_lab().is_err());
        w.enable_ap_test_lab().unwrap();assert!(w.bind_destructible_test_lab().is_err());
        w.bind_terrain(destructible_terrain()).unwrap();w.bind_destructible_test_lab().unwrap();
        assert!(w.destructible_enabled());assert_eq!(w.scene_version(),0);assert!(w.destructible_transition().is_none());
        assert!(w.bind_destructible_test_lab().is_err());assert!(obstacle_world(now,20.,3.).bind_destructible_test_lab().is_err());
        let mut ground=World::new(78,now).unwrap();ground.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).unwrap();
        ground.enable_ap_test_lab().unwrap();ground.bind_terrain(Arc::new(super::super::terrain::tests::fixture(-1000.,2000.,2,vec![-100.;4]))).unwrap();
        assert!(ground.bind_destructible_test_lab().is_err());
    }
    #[test]fn destructible_contact_changes_once_stops_first_shell_and_next_shell_passes_old_box(){
        let now=Instant::now();let mut w=destructible_world(now);
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();w.advance(now+STEP).unwrap();
        let transition=w.destructible_transition().unwrap().clone();assert_eq!((transition.shot,transition.shooter,transition.scene_after),(1,0,1));
        assert_eq!(w.scene_version(),1);assert!(w.projectiles[0].stopped);assert_eq!(w.projectiles[0].terminal,transition.hit.point);
        assert!(destructible::selected(&transition.hit));assert!(w.contacts.is_empty());assert!(w.impacts.is_empty());
        assert_eq!(w.actors.iter().map(|a|a.health).collect::<Vec<_>>(),vec![90,90]);assert_eq!(w.actors[0].fire.ammo(),19);
        let at=now+Duration::from_secs(3);w.advance(at).unwrap();w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],at).unwrap();w.advance(at+STEP).unwrap();
        assert_eq!(w.destructible_transition(),Some(&transition));assert_eq!(w.actors[0].fire.ammo(),18);
        assert_eq!(w.impact.events().iter().filter(|e|matches!(e,impact::Event::DestructibleTransition{..})).count(),1);
        assert!(!w.terrain_contacts.iter().any(|c|c.shot==2 && matches!(c.hit.surface,terrain::Surface::StaticObstacle{instance_id:destructible::INSTANCE_ID,..})));
        assert!(w.impact.events().iter().any(|e|matches!(e,impact::Event::TerrainQuery{shot_id:2,scene_version:1,excluded_instance:Some(destructible::INSTANCE_ID),..})));
        let identity=w.actors[0].identity.clone();w.detach(1).unwrap();w.attach(identity,3).unwrap();assert_eq!(w.scene_version(),1);assert_eq!(w.destructible_transition(),Some(&transition));
    }
    #[test]fn simultaneous_shots_use_one_transition_and_rollback_discards_scene_with_world(){
        let now=Instant::now();let mut w=destructible_world(now);
        // Two admitted flights, independent of which actor is still alive when
        // the update runs. Place the second actor behind the first for this query.
        w.actors[1].position=w.actors[0].position;w.actors[1].origin=w.actors[0].origin;
        for slot in 0..2{w.apply(slot,slot as u32+1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();}
        // Move actor hulls aside after launch; launch facts remain immutable.
        for actor in &mut w.actors {actor.position[0]+=30.;actor.origin=actor.position;}
        let mut failed=w.clone();failed.projectiles[1].velocity[0]=f32::NAN;
        let before=failed.clone();assert!(failed.advance(now+STEP).is_err());
        assert_eq!(failed.scene_version(),0);assert_eq!(failed.destructible,before.destructible);assert_eq!(failed.impact,before.impact);
        assert_eq!(failed.actors,before.actors);assert_eq!(failed.tick,before.tick);assert_eq!(failed.last,before.last);
        assert_eq!(failed.terrain_contacts,before.terrain_contacts);assert_eq!(failed.projectiles[0],before.projectiles[0]);
        w.advance(now+STEP).unwrap();assert_eq!(w.scene_version(),1);
        assert_eq!(w.impact.events().iter().filter(|e|matches!(e,impact::Event::DestructibleTransition{..})).count(),1);
        assert_eq!(w.destructible_transition().unwrap().shot,1);
        assert!(w.impact.events().iter().any(|e|matches!(e,impact::Event::TerrainQuery{shot_id:2,scene_version:1,..})));
    }
    #[test] fn static_surface_participates_in_same_nearest_terrain_armor_decision() {
        let now=Instant::now();
        for (offset,wall_z,kind,hp) in [(20.,3.,"stone",90),(3.,15.,"ground",90),(20.,15.,"armor",60)] {
            let mut w=obstacle_world(now,offset,wall_z);
            w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
            w.advance(now+STEP).unwrap(); assert!(w.projectiles[0].stopped);
            assert_eq!(w.actors[1].health,hp);
            match kind {
                "stone" => {
                    let hit=&w.terrain_contacts[0].hit;
                    assert!(matches!(hit.surface,terrain::Surface::StaticObstacle{material_kind:111,..}));
                    assert_eq!(hit.effect_material_index(),1); assert!((hit.point[2]-3.).abs()<1e-5);
                    assert!(w.impacts.is_empty()); assert!(w.contacts.is_empty());
                },
                "ground" => assert_eq!(w.terrain_contacts[0].hit.surface,terrain::Surface::Ground),
                _ => {assert!(w.terrain_contacts.is_empty());assert_eq!(w.impacts.len(),1);},
            }
        }
    }
    #[test] fn terrain_requires_prestart_geometry_and_explicit_ap_profile() {
        let now=Instant::now(); let source=terrain_world(now,3.).terrain.unwrap();
        let mut w=World::new(44,now).unwrap();
        assert!(w.bind_terrain(source.clone()).is_err());
        w.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).unwrap();
        assert!(w.bind_terrain(source.clone()).is_err());
        w.enable_ap_test_lab().unwrap(); w.bind_terrain(source.clone()).unwrap();
        assert!(w.bind_terrain(source.clone()).is_err());
        assert!(ap_world(now).bind_terrain(source).is_err());
    }
    #[test] fn nearest_surface_blocks_hill_damage_and_preserves_nearer_armor() {
        let now=Instant::now();
        for (offset,ground,hp) in [(3.,true,90),(20.,false,60)] {
            let mut w=terrain_world(now,offset);
            w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
            w.advance(now+STEP).unwrap();
            assert_eq!(w.actors[1].health,hp); assert_eq!(w.actors[0].fire.ammo(),19);
            assert_eq!(w.terrain_contacts.len(),usize::from(ground));
            assert_eq!(w.impacts.len(),usize::from(!ground));
            assert_eq!(w.contacts.len(),usize::from(!ground));
            assert!(w.projectiles[0].stopped);
            if ground {
                let c=&w.terrain_contacts[0]; assert_eq!(w.projectiles[0].terminal,c.hit.point);
                assert!(c.hit.point[2]<8.); assert!((c.direction.iter().map(|v|v*v).sum::<f32>()-1.).abs()<1e-6);
                assert!(w.impact.events().iter().any(|e| matches!(e,impact::Event::Terminal {
                    reason:impact::TerminalReason::TerrainCollision,.. })));
            }
            let retained=(w.terrain_contacts.clone(),w.contacts.clone(),w.impacts.clone(),w.impact.clone());
            w.advance(now+Duration::from_secs(3)).unwrap();
            assert_eq!((w.terrain_contacts,w.contacts,w.impacts,w.impact),retained);
        }
    }
    #[test] fn stalled_terrain_flight_uses_same_chords_as_regular_steps() {
        let now=Instant::now(); let mut slow=terrain_world(now,100.);
        slow.actors[1].position=[100.,0.,10.]; slow.actors[1].origin=slow.actors[1].position;
        slow.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
        let mut regular=slow.clone();
        slow.advance(now+Duration::from_secs(2)).unwrap();
        for step in 1..=20 { regular.advance(now+STEP*step).unwrap(); }
        assert_eq!(slow.terrain_contacts.len(),1); assert_eq!(regular.terrain_contacts.len(),1);
        assert_eq!(slow.projectiles[0].terminal,regular.projectiles[0].terminal);
        assert_eq!(slow.terrain_contacts[0].segment_start,regular.terrain_contacts[0].segment_start);
        assert_eq!(slow.terrain_contacts[0].segment_end,regular.terrain_contacts[0].segment_end);
        assert_eq!(slow.actors[1].health,90);
        assert!(slow.impact.events().iter().filter(|e|e.stage()==impact::Stage::Segment).count()>1);
    }
    #[test] fn terrain_checks_range_tail_and_history_failure_is_atomic() {
        let now=Instant::now(); let mut w=terrain_world(now,100.);
        w.actors[1].position=[100.,0.,10.]; w.actors[1].origin=w.actors[1].position;
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
        let p=w.projectiles[0]; let offset=p.terminal[2]-p.terminal[1]-0.5;
        w.terrain=terrain_world(now,offset).terrain;
        w.advance(now+Duration::from_secs(3)).unwrap();
        assert_eq!(w.terrain_contacts.len(),1);
        assert!((w.projectiles[0].terminal[2]-p.terminal[2]).abs()<1.);
        assert_eq!(w.actors[1].health,90);
        let mut fail=terrain_world(now,3.);
        fail.terrain_contacts=vec![w.terrain_contacts[0].clone();MAX_SHOTS];
        fail.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
        let before=(fail.actors.clone(),fail.projectiles.clone(),fail.impact.clone(),fail.tick,fail.last,fail.terrain_contacts.clone());
        assert!(fail.advance(now+STEP).is_err());
        assert_eq!((fail.actors,fail.projectiles,fail.impact,fail.tick,fail.last,fail.terrain_contacts),before);
    }
    #[test] fn ap_requires_explicit_prestart_geometry_binding() {
        let now = Instant::now(); let mut w = World::new(44,now).unwrap();
        assert!(w.enable_ap_test_lab().is_err());
        w.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).unwrap();
        w.enable_ap_test_lab().unwrap(); assert!(w.enable_ap_test_lab().is_err());
        assert!(world(now).enable_ap_test_lab().is_err());
    }
    #[test] fn ap_contact_changes_health_once_and_three_hits_destroy() {
        let now = Instant::now(); let mut w = ap_world(now);
        for round in 0..3 {
            let at = now+Duration::from_secs(round*3);
            if round > 0 { w.advance(at).unwrap(); }
            w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],at).unwrap();
            w.advance(at+STEP).unwrap();
            assert_eq!(w.impacts.len(),round as usize+1);
            assert!(matches!(&w.impacts.last().unwrap().outcome,
                ImpactOutcome::Ap(resolution) if resolution.outcome == ap::Outcome::Pierced));
            assert_eq!(w.actors[1].health,60-round as i16*30);
            let before = w.impacts.clone(); w.advance(at+STEP*2).unwrap();
            assert_eq!(w.impacts,before);
        }
        assert_eq!(w.actors[1].input,Input::STOP);
        let at = now+Duration::from_secs(9); w.advance(at).unwrap();
        let ammo = w.actors[1].fire.ammo(); let aim = w.actors[1].aim.clone();
        assert!(w.apply(1,2,&[Command::Aim(aim::Intent::Point([100.,20.,50.])),
            Command::Move(Input{throttle:1,steer:1,speed_percent:100}),Command::Fire(fire::Command::Shoot)],at).unwrap().is_empty());
        assert_eq!(w.actors[1].fire.ammo(),ammo); assert_eq!(w.actors[1].aim,aim);
        assert_eq!(w.actors[1].input,Input::STOP);
        // Already dead geometry emits one distinct block outcome, not another
        // AP result, health transition, command or death.
        let wreck_before = w.actors[1].clone();
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],at).unwrap();
        w.advance(at+STEP).unwrap(); assert_eq!(w.impacts.len(),4);
        let event = w.impacts.last().unwrap();
        assert_eq!(event.outcome,ImpactOutcome::WreckBlocked);
        assert_eq!((event.shot,event.attacker,event.target,event.health_before,event.health_after),(4,0,1,0,0));
        assert!(event.segment.is_some()); assert_eq!(w.actors[1],wreck_before);
        assert_eq!(w.actors[0].fire.ammo(),16);
        assert_eq!(w.impact.events().iter().filter(|e| matches!(e,impact::Event::ApResolution{..})).count(),3);
        assert_eq!(w.impact.events().iter().filter(|e| matches!(e,impact::Event::WreckImpact{..})).count(),1);
        assert!(matches!(w.impact.events().last(),Some(impact::Event::Terminal {
            shot_id:4,reason:impact::TerminalReason::TestLabWreckImpact,.. })));
        assert_eq!(w.projectiles[3].terminal,w.contacts[3].endpoint); assert!(w.projectiles[3].stopped);
        let impacts = w.impacts.clone(); let trace = w.impact.clone();
        w.advance(at+STEP*2).unwrap(); assert_eq!(w.impacts,impacts); assert_eq!(w.impact,trace);
        let identity = w.actors[1].identity.clone(); w.detach(2).unwrap();
        w.attach(identity,3).unwrap(); assert_eq!(w.actors[1].health,0); assert_eq!(w.actors[1].fire.ammo(),ammo);
    }
    #[test] fn wreck_impact_requires_opt_in_and_does_not_infer_an_ap_result() {
        let now = Instant::now(); let mut w = collision_world(now,false);
        w.actors[1].health = 0; w.actors[1].aim.park();
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
        let dead = w.actors[1].clone(); w.advance(now+STEP).unwrap();
        assert!(w.impacts.is_empty()); assert_eq!(w.actors[1],dead);
        assert_eq!(w.contacts.len(),1); assert!(w.projectiles[0].stopped);
        assert!(matches!(w.impact.events().last(),Some(impact::Event::Terminal {
            reason:impact::TerminalReason::UnresolvedCollision,.. })));
    }
    #[test] fn wreck_impact_capacity_or_material_failure_rolls_back_complete_advance() {
        let now = Instant::now(); let mut w = ap_world(now);
        w.actors[1].health = 0; w.actors[1].aim.park();
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
        w.advance(now+STEP).unwrap(); assert_eq!(w.impacts[0].outcome,ImpactOutcome::WreckBlocked);
        let at = now+Duration::from_secs(3); w.advance(at).unwrap();
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],at).unwrap();
        for invalid_material in [false,true] {
            let mut invalid = w.clone();
            if invalid_material {
                invalid.geometry = Some(Arc::new(super::super::geometry::tests::invalid_material_bundle()));
            } else {
                invalid.impacts.resize(MAX_SHOTS,invalid.impacts[0].clone());
            }
            let before = invalid.clone(); assert!(invalid.advance(at+STEP).is_err());
            assert_eq!(invalid.actors,before.actors); assert_eq!(invalid.impacts,before.impacts);
            assert_eq!(invalid.impact,before.impact); assert_eq!(invalid.contacts,before.contacts);
            assert_eq!(invalid.projectiles,before.projectiles); assert_eq!(invalid.shots,before.shots);
            assert_eq!(invalid.last,before.last); assert_eq!(invalid.tick,before.tick);
        }
    }
    #[test] fn ap_failures_rollback_damage_and_simultaneous_flights_survive_shooter_death() {
        let now = Instant::now(); let mut w = ap_world(now);
        w.actors[0].health=30; w.actors[1].health=30;
        for i in 0..2 { w.apply(i,i as u32+1,&[Command::Fire(fire::Command::Shoot)],now).unwrap(); }
        let mut invalid = w.clone();
        invalid.geometry = Some(Arc::new(super::super::geometry::tests::invalid_material_bundle()));
        let before = invalid.clone(); assert!(invalid.advance(now+STEP).is_err());
        assert_eq!(invalid.actors,before.actors); assert_eq!(invalid.impacts,before.impacts);
        assert_eq!(invalid.impact,before.impact); assert_eq!(invalid.projectiles,before.projectiles);
        w.advance(now+STEP).unwrap();
        assert_eq!(w.actors.iter().map(|a| a.health).collect::<Vec<_>>(),vec![0,0]);
        assert_eq!(w.impacts.iter().map(|e| e.shot).collect::<Vec<_>>(),vec![1,2]);
    }
    #[test] fn nearest_other_actor_surface_stops_both_shooters_atomically() {
        let now = Instant::now(); let mut w = collision_world(now, false);
        for i in 0..2 { w.apply(i, i as u32+1, &[Command::Fire(fire::Command::Shoot)], now).unwrap(); }
        w.advance(now+STEP).unwrap();
        assert_eq!(w.contacts.len(), 2);
        for (i, contact) in w.contacts.iter().enumerate() {
            assert_eq!(contact.target_slot, 1-i); assert_eq!(contact.triangle.candidate_index, 0);
            assert_eq!(contact.triangle.mesh, "Turret_01");
            assert!(w.projectiles[i].stopped); assert_eq!(w.projectiles[i].terminal, contact.endpoint);
            assert!((contact.endpoint[2] - if i==0 {9.5} else {0.5}).abs() < 0.5);
            assert_eq!(w.actors[i].fire.ammo(), 19);
            let facts = &contact.material_facts;
            assert_eq!(facts.component.name(),contact.triangle.mesh);
            assert_eq!(facts.name,contact.triangle.material);
            assert!(w.impact.events().iter().any(|e| matches!(e, impact::Event::MaterialContact {
                shot_id, facts: recorded, .. } if *shot_id==contact.shot && recorded==facts)));
            assert!(w.impact.events().iter().any(|e| matches!(e, impact::Event::Terminal{
                shot_id, reason: impact::TerminalReason::UnresolvedCollision, ..} if *shot_id==i as u32+1)));
        }
        let before = w.contacts.clone(); w.advance(now+STEP*2).unwrap(); assert_eq!(w.contacts, before);
    }
    #[test] fn failed_material_binding_cannot_publish_a_partial_world_or_stop() {
        let now = Instant::now(); let mut w = collision_world(now,false);
        w.geometry = Some(Arc::new(super::super::geometry::tests::invalid_material_bundle()));
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
        let before = w.clone(); assert!(w.advance(now+STEP).is_err());
        assert_eq!(w.tick,before.tick); assert_eq!(w.last,before.last);
        assert_eq!(w.actors,before.actors); assert_eq!(w.projectiles,before.projectiles);
        assert_eq!(w.contacts,before.contacts); assert_eq!(w.impact,before.impact);
        assert_eq!(w.shots,before.shots); assert!(!w.projectiles[0].stopped);
    }
    #[test] fn full_ammo_real_cadence_hits_and_self_excluding_misses_fit_trace() {
        for miss in [false, true] {
            let now = Instant::now(); let mut w = collision_world(now, miss);
            for step in 0..=600 {
                let at = now + STEP*step;
                if step > 0 { w.advance(at).unwrap(); }
                if step < 600 && step % 30 == 0 {
                    for i in 0..2 { w.apply(i, i as u32+1, &[Command::Fire(fire::Command::Shoot)], at).unwrap(); }
                }
            }
            assert_eq!(w.shots.len(), 40); assert_eq!(w.impact.terminal_shots().len(), 40);
            assert_eq!(w.contacts.len(), if miss {0} else {40});
            assert!(w.impact.events().len() < impact::MAX_EVENTS);
            assert!(w.projectiles.iter().all(|p| p.stopped));
            assert!(w.actors.iter().all(|a| a.fire.ammo()==0));
        }
    }
    #[test] fn invalid_geometry_pose_rolls_back_world_trace_and_contact() {
        let now = Instant::now(); let mut w = collision_world(now, false);
        w.apply(0, 1, &[Command::Fire(fire::Command::Shoot)], now).unwrap();
        let before = w.clone();
        assert!(w.advance_with_external(now+STEP, Some(&[(0,[0.;3],[0.;3],0.),
            (1,[3000.,0.,10.],[0.;3],0.)])).is_err());
        assert_eq!(w.actors,before.actors); assert_eq!(w.projectiles,before.projectiles);
        assert_eq!(w.impact,before.impact); assert_eq!(w.contacts,before.contacts);
        assert_eq!(w.last,before.last); assert_eq!(w.tick,before.tick);
        assert!(w.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).is_err());
    }
    #[test] fn fractional_range_tail_is_queried_before_expiry_and_duration_is_clamped() {
        let now = Instant::now(); let mut w = collision_world(now, true);
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();
        let projectile = w.projectiles[0]; let end = projectile.end_at().unwrap();
        // Native speed produces range expiry between ticks20 and21.
        assert!(end > now+STEP*20 && end < now+STEP*21-Duration::from_millis(1));
        let near_end = projectile.position_at(end-Duration::from_millis(3));
        let target = [near_end[0]+0.236366, near_end[1]-1.55107, near_end[2]];
        w.actors[1].position = target; w.actors[1].origin = target;
        for n in 1..=20 { w.advance(now+STEP*n).unwrap(); }
        assert!(!w.projectiles[0].stopped); assert!(w.contacts.is_empty());
        w.advance(end+Duration::from_millis(1)).unwrap();
        assert!(!w.projectiles[0].stopped); // tail deliberately awaits its query
        w.advance(now+STEP*21).unwrap();
        assert!(w.projectiles[0].stopped); assert_eq!(w.contacts.len(),1);
        let contact = &w.contacts[0];
        assert_eq!(contact.target_slot,1);
        assert!((contact.segment_seconds-(end-(now+STEP*20)).as_secs_f32()).abs()<1e-7);
        assert!((contact.segment_end[2]-projectile.terminal[2]).abs()<1e-5);
    }
    #[test] fn two_controllers_change_one_shared_world_without_cross_ownership() {
        let now = Instant::now(); let mut w = world(now); let other = w.actors[1].clone();
        assert!(w.apply(1, 1, &[Command::Move(Input { throttle: 1, steer: 0, speed_percent: 100 })], now).is_err());
        w.apply(0, 1, &[Command::Move(Input { throttle: 1, steer: 0, speed_percent: 100 })], now).unwrap();
        w.advance(now + STEP).unwrap(); assert!(w.actors[0].position[2] > SPAWN[2]);
        assert_eq!(w.actors[1], other);
    }
    #[test] fn integrated_external_pose_is_authoritative_and_atomic() {
        let now = Instant::now(); let mut w = world(now);
        let pose = [SPAWN[0] + 17., SPAWN[1] + 2., SPAWN[2] - 9.];
        w.advance_with_external(now + STEP, Some(&[(0, pose, [0.75, 0.1, -0.2], 3.5),
            (1, [SPAWN[0] + 4., SPAWN[1], SPAWN[2] + 1.], [-0.25, 0., 0.], 0.)])).unwrap();
        assert_eq!(w.actors[0].position, pose); assert_eq!(w.actors[0].yaw, 0.75);
        assert_eq!(w.actors[0].direction, [0.75, 0.1, -0.2]);
        assert_eq!(w.actors[0].speed, 3.5); assert_eq!(w.actors[1].yaw, -0.25);
        let before = w.clone();
        assert!(w.advance_with_external(now + STEP * 2,
            Some(&[(0, [SPAWN[0], SPAWN[1], SPAWN[2]], [0., 0., 0.], 0.)])).is_err());
        assert_eq!(w.actors, before.actors); assert_eq!(w.tick, before.tick);
        assert!(w.advance_with_external(now + STEP * 2,
            Some(&[(0, [f32::NAN, 0., 0.], [0., 0., 0.], 0.)])).is_err());
        assert_eq!(w.actors, before.actors); assert_eq!(w.tick, before.tick);
    }
    #[test] fn integrated_survivor_keeps_motion_aim_and_flight_when_peer_disconnects() {
        let now=Instant::now(); let mut w=ap_world(now); w.actors[1].health=0;
        w.detach(2).unwrap(); let parked=w.actors[1].clone();
        w.apply(0,1,&[Command::Aim(aim::Intent::Hold{yaw:1.,pitch:0.})],now).unwrap();
        let rows=[(0,[0.,0.,1.],[0.1,0.,0.],1.),(1,parked.position,parked.direction,0.)];
        w.advance_with_external(now+STEP,Some(&rows)).unwrap();
        assert_eq!(w.tick,1001); assert_eq!(w.actors[0].position,[0.,0.,1.]);
        assert!(w.actors[0].aim.yaw>0.); assert_eq!(w.actors[1],parked);
        w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now+STEP).unwrap();
        w.advance_with_external(now+STEP*2,Some(&rows)).unwrap();
        assert!(w.impact.events().iter().any(|e| matches!(e,impact::Event::Segment{..})));
        let before=w.clone(); let mut bad_rows=rows; bad_rows[1].1[0]+=1.;
        assert!(w.advance_with_external(now+STEP*3,Some(&bad_rows)).is_err());
        assert_eq!(w.actors,before.actors); assert_eq!(w.tick,before.tick);
    }
    #[test] fn integrated_spawn_rebase_is_lane_bound_and_pre_ready_only() {
        let now = Instant::now();
        let mut w = World::new(124, now).unwrap();
        for i in 0..2 { w.attach(Identity { account: format!("lane-{i}"), database: i + 11,
            name: format!("lane_{i}") }, i as u32 + 11).unwrap(); }
        w.rebase_external_spawns([
            [-67.4999, 22.4167, -440.8130],
            [-59.4999, 22.4167, -440.8130],
        ]).unwrap();
        assert_eq!(w.actors[0].position, [-67.4999, 22.4167, -440.8130]);
        assert_eq!(w.actors[1].origin, [-59.4999, 22.4167, -440.8130]);
        w.start(now).unwrap();
        assert!(w.rebase_external_spawns([
            [-67., 22., -440.], [-59., 22., -440.]
        ]).is_ok());
        w.actors[0].ready = true;
        assert!(w.rebase_external_spawns([
            [-67., 22., -440.], [-59., 22., -440.]
        ]).is_err());
        w.actors[0].ready = false;
        w.reset_external_spawn(0, [-67., 22., -440.]).unwrap();
        assert_eq!(w.actors[0].position, [-67., 22., -440.]);
    }
    #[test] fn disconnect_and_reconnect_keep_survivor_clock_pose_and_ammo() {
        let now = Instant::now(); let mut w = world(now);
        w.apply(0, 1, &[Command::Fire(fire::Command::Shoot)], now).unwrap();
        w.apply(1, 2, &[Command::Move(Input { throttle: 1, steer: 0, speed_percent: 100 })], now).unwrap();
        w.detach(1).unwrap(); let parked = w.actors[0].position;
        w.advance(now + STEP).unwrap(); assert_eq!(w.actors[0].position, parked);
        assert!(w.actors[1].position[2] > SPAWN[2]);
        let identity = w.actors[0].identity.clone(); assert_eq!(w.attach(identity, 3).unwrap(), 0);
        assert_eq!(w.actors[0].fire.ammo(), 19); assert_eq!(w.tick, 1001);
        assert!(w.actors[0].fire.reload_until().is_some());
    }
    #[test] fn bad_late_command_is_atomic_and_reload_is_separate() {
        let now = Instant::now(); let mut w = world(now); let before = w.actors.clone();
        assert!(w.apply(0, 1, &[Command::Fire(fire::Command::Shoot),
            Command::Move(Input { throttle: 2, steer: 0, speed_percent: 100 })], now).is_err());
        assert_eq!(w.actors, before);
        assert!(w.shots.is_empty());
        w.apply(0, 1, &[Command::Fire(fire::Command::Shoot)], now).unwrap();
        assert_eq!(w.apply(0, 1, &[Command::Fire(fire::Command::Shoot)], now).unwrap(), vec![fire::Outcome::RejectedReload]);
        assert_eq!(w.apply(1, 2, &[Command::Fire(fire::Command::Shoot)], now).unwrap(), vec![fire::Outcome::AcceptedShot { ammo_remaining: 19 }]);
        assert_eq!(w.shots, vec![Shot { sequence:1,slot:0,tick:1000 }, Shot { sequence:2,slot:1,tick:1000 }]);
    }
    #[test] fn same_tick_and_staggered_two_actor_launches_keep_trace_order() {
        let now = Instant::now(); let mut w = world(now);
        w.apply(0, 1, &[Command::Fire(fire::Command::Shoot)], now).unwrap();
        w.apply(1, 2, &[Command::Fire(fire::Command::Shoot)], now + Duration::from_millis(90)).unwrap();
        assert_eq!(w.impact.events().iter().filter(|event| event.stage() == impact::Stage::Admission).count(), 2);
        assert_eq!(w.impact.events().iter().filter(|event| event.stage() == impact::Stage::Launch).count(), 2);
        assert_eq!(w.shots.iter().map(|shot| shot.tick).collect::<Vec<_>>(), vec![1000, 1000]);
        w.advance(now + Duration::from_millis(100)).unwrap();
        assert_eq!(w.impact.events().iter().filter(|event| event.stage() == impact::Stage::Segment).count(), 2);
        assert_eq!(w.impact.events().iter().map(impact::Event::order).collect::<Vec<_>>(), (1..=6).collect::<Vec<_>>());
        assert_eq!(w.projectiles.iter().map(|projectile| projectile.slot).collect::<Vec<_>>(), vec![0, 1]);
    }
    #[test] fn full_flight_cadence_stays_inside_trace_budget() {
        let now = Instant::now(); let mut w = world(now);
        for round in 0..20u64 {
            let at = now + Duration::from_secs(round * 3);
            if round != 0 { w.advance(at).unwrap(); }
            w.apply(0, 1, &[Command::Fire(fire::Command::Shoot)], at).unwrap();
            w.apply(1, 2, &[Command::Fire(fire::Command::Shoot)], at).unwrap();
        }
        w.advance(now + Duration::from_secs(60)).unwrap();
        assert_eq!(w.shots.len(), 40);
        assert_eq!(w.impact.terminal_shots().len(), 40);
        assert!(w.impact.events().len() <= impact::MAX_EVENTS);
        let orders = w.impact.events().iter().map(impact::Event::order).collect::<Vec<_>>();
        assert_eq!(orders, (1..=orders.len() as u32).collect::<Vec<_>>());
    }
    #[test] fn rejected_apply_and_advance_publish_no_partial_state() {
        let now = Instant::now(); let mut w = world(now);
        let before = (w.actors.clone(), w.shots.clone(), w.projectiles.clone(),
            w.impact.clone(), w.tick, w.last);
        assert!(w.apply(0, 1, &[Command::Fire(fire::Command::Shoot),
            Command::Move(Input { throttle: 2, steer: 0, speed_percent: 100 })], now).is_err());
        assert_eq!((w.actors.clone(), w.shots.clone(), w.projectiles.clone(),
            w.impact.clone(), w.tick, w.last), before);

        w.apply(0, 1, &[Command::Fire(fire::Command::Shoot)], now).unwrap();
        w.projectiles[0].origin[0] = impact::MAX_COORDINATE + 1.0;
        let before = (w.actors.clone(), w.shots.clone(), w.projectiles.clone(),
            w.impact.clone(), w.tick, w.last);
        assert!(w.advance(now + STEP).is_err());
        assert_eq!((w.actors.clone(), w.shots.clone(), w.projectiles.clone(),
            w.impact.clone(), w.tick, w.last), before);
    }
    #[test] fn shot_history_is_bounded_by_real_ammo_and_rejections_emit_nothing() {
        let now = Instant::now(); let mut w = world(now);
        for n in 0..fire::MS1_INITIAL_AMMO {
            for slot in 0..2 {
                w.apply(slot, slot as u32 + 1, &[Command::Fire(fire::Command::Shoot)], now + Duration::from_secs(n as u64 * 3)).unwrap();
            }
        }
        assert_eq!(w.shots.len(), 40); assert_eq!(w.latest_shot(), 40);
        let before = w.shots.clone();
        assert_eq!(w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now+Duration::from_secs(61)).unwrap(),vec![fire::Outcome::RejectedNoAmmo]);
        assert_eq!(w.shots, before);
    }
    #[test] fn capacity_duplicate_identity_and_old_controller_fail_closed() {
        let now = Instant::now(); let mut w = world(now);
        assert!(w.attach(w.actors[0].identity.clone(), 3).is_err());
        assert!(w.attach(Identity { account: "third".into(), database: 3, name: "third".into() }, 3).is_err());
        w.detach(1).unwrap(); assert!(w.apply(0, 1, &[], now).is_err());
        let mut identity = w.actors[0].identity.clone(); identity.name = "wrong_name".into();
        assert!(w.attach(identity, 3).is_err());
    }
    #[test] fn clock_and_kinematic_bounds_do_not_depend_on_client_telemetry() {
        let now = Instant::now(); let mut w = world(now);
        w.apply(0, 1, &[Command::Move(Input { throttle: 1, steer: 0, speed_percent: 100 })], now).unwrap();
        for n in 1..100 { w.advance(now + STEP * n).unwrap(); }
        assert!((w.actors[0].position[2] - SPAWN[2]).abs() <= 2.);
        assert_eq!(w.actors[0].position[1], SPAWN[1]);
        assert!(w.advance(now).is_err()); assert!(w.advance(now + LIFETIME).is_err());
    }
}

#[cfg(test)]
#[path = "p06t_world_tests.rs"]
mod p06t_world_tests;

#[cfg(test)]
#[path="result_spots_world_tests.rs"]
mod first_spot_tests;

#[cfg(test)]
#[path="seven_loss_boundary_tests.rs"]
mod seven_loss_boundary_tests;

#[cfg(test)]#[path="p10b_loss_roster_tests.rs"]mod p10b_loss_roster_tests;

#[cfg(test)]
#[path="p10b_team_world_tests.rs"]
mod p10b_team_world_tests;

#[cfg(test)]
#[path="p05c_ram_terminal_tests.rs"]
mod ram_terminal_tests;
