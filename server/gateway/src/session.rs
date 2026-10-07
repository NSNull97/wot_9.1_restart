//! Single-account loopback laboratory gateway. Persistent process, bounded sessions.
//! Native transport; opt-in measured Account creation, no complete game service.
use std::{collections::VecDeque,fs,io,net::{Ipv4Addr,SocketAddr,UdpSocket},thread,time::{Duration,Instant}};
use rsa::rand_core::{OsRng,RngCore};
use sha2::{Digest,Sha256};
use std::{sync::{Arc,mpsc},path::Path};
use crate::{baseapp091 as base,login091 as login,redirect091,transport091::{self,Frame,Window}};
use crate::capture091::{Channel,Recorder};

// R01 measured same-process reconnect reuses the cipher key but changes the
// encrypted nonce and UDP peer. Keep finite attempt and retired-peer isolation;
// neither a nonce nor a socket address authenticates an account by itself.
pub(crate) const MAX_RETIRED: usize = 32;
pub(crate) const RETIRED_TTL: Duration = Duration::from_secs(120);

// Deliberately no Debug/Display/Serialize: key and nonce must not enter logs.
#[derive(Clone, Copy, PartialEq, Eq)]
pub(crate) struct LoginAttempt {
    key: [u8; 16],
    nonce: u32,
    login_peer: SocketAddr,
}

impl LoginAttempt {
    pub(crate) fn new(key: [u8; 16], nonce: u32, login_peer: SocketAddr) -> Self {
        Self { key, nonce, login_peer }
    }

    /// Necessary pending/active duplicate identity. For an authenticated active
    /// Session the caller MUST additionally compare the verified account UUID.
    /// The mutable outer LoginRequest ID is deliberately not an attempt key.
    pub(crate) fn same_attempt(&self, other: &Self) -> bool {
        self == other
    }
}

struct RetiredSession {
    attempt: LoginAttempt,
    base_peer: Option<SocketAddr>,
    closed_at: Instant,
}

impl RetiredSession {
    fn owns_peer(&self, peer: SocketAddr) -> bool {
        self.attempt.login_peer == peer || self.base_peer == Some(peer)
    }
}

/// Only fixed nonsecret reasons may be formatted in a diagnostic event.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub(crate) enum Denial {
    RetiredAttempt,
    RetiredPeerForKey,
    CapacityFull,
    ClockRegression,
}

#[derive(Default)]
pub(crate) struct RetirementWindow {
    records: VecDeque<RetiredSession>,
    last_time: Option<Instant>,
}

impl RetirementWindow {
    fn expire(&mut self, now: Instant) -> Result<(), Denial> {
        if self.last_time.is_some_and(|last| now < last) {
            return Err(Denial::ClockRegression);
        }
        self.last_time = Some(now);
        // Preserve the existing conservative boundary: exactly 120 s remains
        // retained; only age > 120 s expires. Never evict to accept another row.
        while self.records.front().is_some_and(|record| {
            now.duration_since(record.closed_at) > RETIRED_TTL
        }) {
            self.records.pop_front();
        }
        Ok(())
    }

    /// Call before starting the credential worker AND again immediately before
    /// allocating a new Session after its successful result. Allocation itself
    /// is external and permitted only when the previous Session is absent.
    /// A same active-attempt retransmission is handled separately by the caller.
    pub(crate) fn check_login(&mut self, candidate: &LoginAttempt, now: Instant) -> Result<(), Denial> {
        self.expire(now)?;
        for record in &self.records {
            if record.attempt.key != candidate.key {
                continue;
            }
            if record.attempt.nonce == candidate.nonce {
                return Err(Denial::RetiredAttempt);
            }
            if record.owns_peer(candidate.login_peer) {
                return Err(Denial::RetiredPeerForKey);
            }
        }
        if self.retained_count() >= MAX_RETIRED {
            return Err(Denial::CapacityFull);
        }
        Ok(())
    }

    /// Before binding the real BaseApp peer or decrypting/processing its frames,
    /// reject a retained socket address for this repeated cipher key. Checking
    /// only the new login peer would leave tokenless old ACKs/heartbeats exposed.
    /// New key + old peer is permitted; old-key/same-peer is fail-closed for TTL.
    pub(crate) fn check_base_peer(&mut self, candidate: &LoginAttempt, peer: SocketAddr,
                                now: Instant) -> Result<(), Denial> {
        self.expire(now)?;
        if self.records.iter().any(|record| record.attempt.key == candidate.key && record.owns_peer(peer)) {
            return Err(Denial::RetiredPeerForKey);
        }
        Ok(())
    }

    /// Call at actual Session retirement, with that Session's actual peer(s).
    /// The one-active-session caller must reserve room by check_login at final
    /// allocation. CapacityFull here is an invariant violation: fail closed,
    /// never ignore this result or delete an older replay protection entry.
    pub(crate) fn retire(&mut self, attempt: LoginAttempt, base_peer: Option<SocketAddr>,
                        now: Instant) -> Result<(), Denial> {
        self.expire(now)?;
        if self.retained_count() >= MAX_RETIRED {
            return Err(Denial::CapacityFull);
        }
        self.records.push_back(RetiredSession { attempt, base_peer, closed_at: now });
        Ok(())
    }

    pub(crate) fn retained_count(&self) -> usize {
        self.records.len()
    }
}



#[derive(Clone,Copy,Debug,PartialEq,Eq)]
enum ArenaSpaceStage {Disabled,AwaitingEnable,Queued}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
enum ArenaVehicleStage {Disabled,AwaitingEnable,AwaitingEntityRequest,Queued}

// Transport boundary for a new Account on the SAME authenticated channel.
// Track the actual queued reset/create body, never global tx emptiness.
#[derive(Clone,Debug,PartialEq,Eq)]
struct WarmAccountReturn {generation:u32,queue_ahead:usize,creation:Option<(u32,bool)>,enabled:bool,stale_avatar_envelopes:u8}

#[derive(Clone)]
struct Session {
    id:u32,key:[u8;16],login_peer:SocketAddr,base_peer:Option<SocketAddr>,handoff:u32,token:u32,
    active:bool,rx:u32,last_rx:Instant,last_keepalive:Instant,last_heartbeat:Instant,tx:Window,
    account_probe:bool,account_ready:bool,
    received:VecDeque<(u32,Vec<u8>)>,sync_mask:u8,request_ids:Vec<i16>,
    hangar:Option<Arc<crate::hangar091::Fixtures>>,outbox:VecDeque<Vec<u8>>,chat_request_ids:Vec<i64>,
    language:Option<&'static str>,
    stats_requests:u32,
    unsupported_request_ids:VecDeque<i16>,
    identity:Option<Arc<crate::identity091::Profile>>,created_at:Instant,
    account_cache_hash:Option<i32>,login_attempt:Option<LoginAttempt>,
    arena_base:bool,avatar_unsupported_envelopes:u8,arena_space:ArenaSpaceStage,
    arena_vehicle:ArenaVehicleStage,arena_vehicle_seed:Option<crate::arena_vehicle091::VehicleSeed>,
    arena_vehicle_announcement:Option<(u32,bool)>,
    arena_ready:bool,arena_vehicle_creation:Option<(u32,bool)>,
    arena_preparation:Option<crate::arena_ready091::Preparation>,
    arena_battle_preparation:Option<crate::battle091::preparation::BattlePreparation>,
    arena_fire:Option<crate::battle091::fire::State>,
    arena_movement:bool,arena_motion:Option<crate::arena_movement091::Motion>,
    map_drive:bool,map_binding:Option<crate::map_drive091::Binding>,
    drive:Option<crate::map_drive_world091::Arena>,
    drive_return_account:Option<WarmAccountReturn>,
    drive_account_policy:Option<Arc<crate::map_drive_service091::AccountPolicy>>,
}
impl Session {
    fn new(id:u32,key:[u8;16],peer:SocketAddr,now:Instant)->Self {
        Self {id,key,login_peer:peer,base_peer:None,handoff:OsRng.next_u32(),token:OsRng.next_u32(),
            active:false,rx:0,last_rx:now,last_keepalive:now,last_heartbeat:now,tx:Window::new(),account_probe:false,account_ready:false,
            received:VecDeque::new(),sync_mask:0,request_ids:Vec::new(),hangar:None,outbox:VecDeque::new(),chat_request_ids:Vec::new(),language:None,stats_requests:0,
            unsupported_request_ids:VecDeque::new(),identity:None,created_at:now,account_cache_hash:None,login_attempt:None,
            arena_base:false,avatar_unsupported_envelopes:0,arena_space:ArenaSpaceStage::Disabled,
            arena_vehicle:ArenaVehicleStage::Disabled,arena_vehicle_seed:None,arena_vehicle_announcement:None,
            arena_ready:false,arena_vehicle_creation:None,arena_preparation:None,arena_battle_preparation:None,arena_fire:None,
            arena_movement:false,arena_motion:None,map_drive:false,map_binding:None,drive:None,drive_return_account:None,drive_account_policy:None}
    }
    fn same_login_attempt(&self,candidate:&LoginAttempt)->bool {
        self.login_attempt.is_some_and(|attempt|attempt.same_attempt(candidate))
    }
    fn verified_duplicate(&self,candidate:&LoginAttempt,account_id:&str)->bool {
        self.same_login_attempt(candidate) && self.identity.as_ref().is_some_and(|p|p.account_id==account_id)
    }
    // This gate is called before even recognizing a BaseApp handshake. In the
    // native legacy transport an ACK/empty heartbeat has no Session token.
    fn guard_base_peer(&self,retirement:&mut RetirementWindow,peer:SocketAddr,now:Instant)->Result<(),Denial> {
        if let Some(attempt)=&self.login_attempt {retirement.check_base_peer(attempt,peer,now)?;}
        Ok(())
    }
    fn drain_outbox(&mut self)->io::Result<()> {
        while self.tx.len()<8 {
            let Some(body)=self.outbox.front() else {break;};
            if let Some(warm)=self.drive_return_account.as_mut().filter(|w|w.creation.is_none()) {
                let sequence=self.tx.enqueue_body_tracked(body)?;
                if warm.queue_ahead==0 {warm.creation=Some((sequence,false));}
                else {warm.queue_ahead-=1;}
            } else {self.tx.enqueue_body(body)?;}
            self.outbox.pop_front();
        }
        Ok(())
    }
    fn ready_for_arena_base(&self)->bool {
        self.active && self.account_ready && self.identity.is_some() && self.hangar.is_some()
            && self.base_peer.is_some() && self.sync_mask==7 && self.outbox.is_empty()
            && self.tx.len()==0 && !self.arena_base
    }
    fn queue_arena_base(&mut self)->io::Result<()> {
        if !self.ready_for_arena_base() {return Err(invalid());}
        let identity=self.identity.as_ref().ok_or_else(invalid)?;
        let body=crate::arena091::reset_to_avatar_base(&crate::arena091::AvatarBaseSeed {
            entity_id:crate::arena_control091::AVATAR_ENTITY_ID,name:&identity.name,
            arena_unique_id:crate::arena_control091::ARENA_UNIQUE_ID,
        })?;
        // A failed encode/enqueue cannot partially change the entity phase,
        // the existing channel, key, identity, fixtures or receive history.
        let mut next=self.clone();next.tx.enqueue_body(&body)?;next.arena_base=true;
        *self=next;Ok(())
    }
    fn queue_arena_checkpoint(&mut self,checkpoint:crate::arena_control091::Checkpoint)->io::Result<()> {
        if matches!(checkpoint,crate::arena_control091::Checkpoint::AvatarVehicle|crate::arena_control091::Checkpoint::AvatarReady|crate::arena_control091::Checkpoint::AvatarMovement|crate::arena_control091::Checkpoint::AvatarDrive) {
            if !self.ready_for_arena_base() || self.arena_vehicle!=ArenaVehicleStage::Disabled
                || self.arena_vehicle_seed.is_some() {return Err(invalid());}
            let identity=self.identity.as_ref().ok_or_else(invalid)?;
            let state=self.hangar.as_ref().ok_or_else(invalid)?.state_sha256();
            // All identity/profile/descriptor/HP bindings must succeed BEFORE
            // even the reset/base body is queued. No fixture is mutated.
            let seed=crate::arena_vehicle091::load(identity,state)?;
            let mut next=self.clone();next.queue_arena_base()?;
            next.arena_vehicle_seed=Some(seed);next.arena_vehicle=ArenaVehicleStage::AwaitingEnable;
            next.arena_ready=matches!(checkpoint,crate::arena_control091::Checkpoint::AvatarReady|crate::arena_control091::Checkpoint::AvatarMovement|crate::arena_control091::Checkpoint::AvatarDrive);
            next.arena_movement=matches!(checkpoint,crate::arena_control091::Checkpoint::AvatarMovement|crate::arena_control091::Checkpoint::AvatarDrive);
            next.map_drive=checkpoint==crate::arena_control091::Checkpoint::AvatarDrive;
            *self=next;return Ok(());
        }
        self.queue_arena_base()?;
        if checkpoint==crate::arena_control091::Checkpoint::AvatarSpace {
            self.arena_space=ArenaSpaceStage::AwaitingEnable;
        }
        Ok(())
    }
    fn queue_arena_space(&mut self)->io::Result<()> {
        if !self.arena_base || self.arena_space!=ArenaSpaceStage::AwaitingEnable
            || !self.active || !self.account_ready || self.identity.is_none() || self.hangar.is_none()
            || self.base_peer.is_none() || self.sync_mask!=7 || !self.outbox.is_empty() {return Err(invalid());}
        // Decoded pinned original map1 space.settings; chosen own laboratory
        // Avatar placement, not a runtime-measured tank spawn or physics body.
        let mut body=crate::arena091::create_cell_avatar(&crate::arena091::AvatarCellSeed {
            space_id:1,player_vehicle_id:0x09100003,
            position:[-58.499908447265625,33.770267486572266,-445.81304931640625],
        })?;
        body.extend(crate::arena091::karelia_space_data(1,1u64.to_le_bytes())?);
        // One reliable body keeps cell-before-space order and exact retry bytes.
        // The caller's receive clone also covers ACKs, history and piggybacks.
        self.tx.enqueue_body(&body)?;
        self.arena_space=ArenaSpaceStage::Queued;Ok(())
    }
    fn queue_arena_vehicle_announcement(&mut self)->io::Result<usize> {
        if !self.arena_base || self.arena_vehicle!=ArenaVehicleStage::AwaitingEnable
            || self.arena_space!=ArenaSpaceStage::Disabled || !self.active || !self.account_ready
            || self.base_peer.is_none() || self.sync_mask!=7 || !self.outbox.is_empty() {return Err(invalid());}
        let seed=self.arena_vehicle_seed.as_ref().ok_or_else(invalid)?;
        seed.validate_session(self.identity.as_ref().ok_or_else(invalid)?,
            self.hangar.as_ref().ok_or_else(invalid)?.state_sha256())?;
        // Vehicle02 showed cached server entities skip prerequisites at enterAoI.
        // Announce the AoI first; no create command precedes the measured request.
        let body=crate::arena_vehicle091::announce_vehicle(seed)?;
        let size=body.len();let mut next=self.clone();let sequence=next.tx.enqueue_body_tracked(&body)?;
        next.arena_vehicle_announcement=Some((sequence,false));
        next.arena_vehicle=ArenaVehicleStage::AwaitingEntityRequest;*self=next;Ok(size)
    }
    fn queue_requested_arena_vehicle(&mut self)->io::Result<usize> {
        if !self.arena_base || self.arena_vehicle!=ArenaVehicleStage::AwaitingEntityRequest
            || self.arena_space!=ArenaSpaceStage::Disabled || !self.active || !self.account_ready
            || self.base_peer.is_none() || self.sync_mask!=7 || !self.outbox.is_empty()
            || !self.arena_vehicle_announcement.is_some_and(|(_,acked)|acked) {return Err(invalid());}
        // Require the announcement's validated ACK, not an empty whole window:
        // a later heartbeat may still be pending. The flag changes only inside
        // receive's clone/commit and cannot acknowledge an unsent packet.
        let seed=self.arena_vehicle_seed.as_ref().ok_or_else(invalid)?;
        seed.validate_session(self.identity.as_ref().ok_or_else(invalid)?,
            self.hangar.as_ref().ok_or_else(invalid)?.state_sha256())?;
        let body=crate::arena_vehicle091::create_requested_vehicle(seed)?;
        let size=body.len();let mut next=self.clone();
        if next.arena_ready {
            let sequence=next.tx.enqueue_body_tracked(&body)?;
            next.arena_vehicle_creation=Some((sequence,false));
        } else {next.tx.enqueue_body(&body)?;}
        next.arena_vehicle=ArenaVehicleStage::Queued;*self=next;Ok(size)
    }
    fn queue_arena_preparation(&mut self,now:Instant)->io::Result<(u32,u32)> {
        if !self.arena_ready || self.arena_movement || !self.arena_base || self.arena_vehicle!=ArenaVehicleStage::Queued
            || self.arena_space!=ArenaSpaceStage::Disabled || !self.active || !self.account_ready
            || self.base_peer.is_none() || self.sync_mask!=7 || !self.outbox.is_empty()
            || self.arena_preparation.is_some() || now<self.created_at || now<self.last_rx
            || !self.arena_vehicle_creation.is_some_and(|(_,acked)|acked) {return Err(invalid());}
        let seed=self.arena_vehicle_seed.as_ref().ok_or_else(invalid)?;
        let identity=self.identity.as_ref().ok_or_else(invalid)?;
        let state=self.hangar.as_ref().ok_or_else(invalid)?.state_sha256();
        let battle_preparation=crate::battle091::preparation::prepare_primary_ms1(seed,identity,state,1)?;
        let preparation=crate::arena_ready091::Preparation::new(now)?;
        // Keep the measured PREBATTLE clock first, then append the bounded
        // native Avatar ammo panel in the same reliable body. The static
        // method id is known; live Avatar receipt/order remains NOT_RUN.
        let mut body=crate::arena_ready091::preparation_body(crate::arena_vehicle091::VEHICLE_ENTITY_ID)?;
        body.extend(crate::battle091::native_ammo::panel_bodies(
            battle_preparation.loadout(), crate::arena_control091::AVATAR_ENTITY_ID)?);
        body.extend(crate::battle091::native_ammo::selected_shell_body(
            battle_preparation.loadout(), crate::arena_control091::AVATAR_ENTITY_ID)?);
        body.extend(crate::battle091::native_ammo::initial_reload_body(
            battle_preparation.loadout(), crate::arena_control091::AVATAR_ENTITY_ID)?);
        let create_sequence=self.arena_vehicle_creation.ok_or_else(invalid)?.0;
        let mut next=self.clone();let sequence=next.tx.enqueue_body_tracked(&body)?;
        next.arena_preparation=Some(preparation);
        next.arena_battle_preparation=Some(battle_preparation);
        next.arena_fire=Some(crate::battle091::fire::State::new());
        *self=next;Ok((create_sequence,sequence))
    }
    fn preparation_expired(&mut self,now:Instant)->io::Result<bool> {
        if !self.arena_ready {return Ok(false);}
        match self.arena_preparation.as_mut() {Some(p)=>p.poll_expired(now),None=>Ok(false)}
    }
    fn movement_guard(&self,now:Instant)->io::Result<()> {
        if !self.arena_movement || !self.arena_ready || !self.arena_base || self.arena_vehicle!=ArenaVehicleStage::Queued
            || self.arena_space!=ArenaSpaceStage::Disabled || !self.active || !self.account_ready
            || self.base_peer.is_none() || self.sync_mask!=7 || !self.outbox.is_empty()
            || self.arena_preparation.is_some() || now<self.created_at || now<self.last_rx
            || !self.arena_vehicle_creation.is_some_and(|(_,acked)|acked) {return Err(invalid());}
        self.arena_vehicle_seed.as_ref().ok_or_else(invalid)?.validate_session(
            self.identity.as_ref().ok_or_else(invalid)?,self.hangar.as_ref().ok_or_else(invalid)?.state_sha256())
    }
    fn queue_arena_movement(&mut self,now:Instant)->io::Result<(u32,u32)> {
        self.movement_guard(now)?;if self.arena_motion.is_some() || self.map_drive {return Err(invalid());}
        let body=crate::arena_movement091::phase_body(crate::arena_vehicle091::VEHICLE_ENTITY_ID)?;
        let mut next=self.clone();let sequence=next.tx.enqueue_body_tracked(&body)?;
        next.arena_motion=Some(crate::arena_movement091::Motion::new(now));
        let create=self.arena_vehicle_creation.ok_or_else(invalid)?.0;*self=next;Ok((create,sequence))
    }
    fn queue_map_binding(&mut self,now:Instant)->io::Result<(u32,u32)> {
        self.movement_guard(now)?;
        if !self.map_drive || self.map_binding.is_some() || self.arena_motion.is_some() {return Err(invalid());}
        let seed=self.arena_vehicle_seed.as_ref().ok_or_else(invalid)?;
        let identity=self.identity.as_ref().ok_or_else(invalid)?;
        let state=self.hangar.as_ref().ok_or_else(invalid)?.state_sha256();
        let generation=self.drive.as_ref().map_or(1,|d|d.generation);
        let preparation=match self.arena_battle_preparation.as_ref() {
            Some(value)=>{value.validate_for(seed,identity,state,generation)?;value.clone()},
            None=>crate::battle091::preparation::prepare_primary_ms1(seed,identity,state,generation)?,
        };
        let mut body=crate::map_drive091::binding_body(crate::arena_vehicle091::VEHICLE_ENTITY_ID)?;
        body.extend(crate::battle091::native_ammo::panel_bodies(
            preparation.loadout(), crate::arena_control091::AVATAR_ENTITY_ID)?);
        body.extend(crate::battle091::native_ammo::selected_shell_body(
            preparation.loadout(), crate::arena_control091::AVATAR_ENTITY_ID)?);
        body.extend(crate::battle091::native_ammo::initial_reload_body(
            preparation.loadout(), crate::arena_control091::AVATAR_ENTITY_ID)?);
        let mut next=self.clone();let sequence=next.tx.enqueue_body_tracked(&body)?;next.arena_battle_preparation=Some(preparation);
        if next.arena_fire.is_none() {next.arena_fire=Some(crate::battle091::fire::State::new());}
        next.map_binding=Some(crate::map_drive091::Binding::new(sequence));
        next.arena_motion=Some(crate::arena_movement091::Motion::new(now));
        let create=self.arena_vehicle_creation.ok_or_else(invalid)?.0;*self=next;Ok((create,sequence))
    }
    fn receive_map_drive(&mut self,payload:&[u8],sequence:u32,now:Instant,events:&mut Vec<String>)->io::Result<()> {
        self.movement_guard(now)?;if !self.map_drive {return Err(invalid());}
        let methods=crate::map_drive091::methods(payload,crate::arena_vehicle091::VEHICLE_ENTITY_ID)?;
        let mut next=self.clone();let mut recorded=Vec::new();
        let motion=next.arena_motion.as_mut().ok_or_else(invalid)?;
        let binding=next.map_binding.as_mut().ok_or_else(invalid)?;
        for (index,method) in methods.into_iter().enumerate() {
            match method {
                crate::map_drive091::Method::CorrectionAck=>{
                    let first=binding.correction_ack()?;
                    recorded.push(format!("MAP_DRIVE_CORRECTION_ACK session={} sequence={sequence} method_index={index} message_id=6 forced_sequence={} force_acked=true first={first} acknowledgements={} token_verified=true domain_applied={first} client_coordinates_used=false",self.id,binding.force_sequence,binding.correction_acks()));
                },
                crate::map_drive091::Method::IgnoredPlayerTelemetry(id)=>{
                    binding.ignored_player_telemetry()?;
                    recorded.push(format!("MAP_DRIVE_IGNORED_CLIENT_TELEMETRY session={} sequence={sequence} method_index={index} message_id={id} count={} exact_shape=true token_verified=true domain_applied=false client_coordinates_used=false",self.id,binding.player_telemetry()));
                },
                crate::map_drive091::Method::Lab(crate::arena_movement091::Method::Move(command))=>{
                    if command==crate::arena_movement091::Command::Forward && !binding.correction_acknowledged() {return Err(invalid());}
                    let action=motion.command(command,now)?;let flags=if command==crate::arena_movement091::Command::Forward {1}else{0};
                    let started=motion.started_seconds().map(|s|format!("{s:.9}")).unwrap_or_else(||"none".to_owned());
                    recorded.push(format!("MAP_DRIVE_MOVE_COMMAND session={} sequence={sequence} method_index={index} flags={flags} action={} phase={} displacement_m={:.9} move_methods={} lab_elapsed_seconds={:.9} movement_started_seconds={started} correction_acknowledged={} token_verified=true domain_applied=true client_coordinates_used=false",self.id,action.name(),motion.phase().name(),motion.displacement(now),motion.move_methods(),motion.elapsed_seconds(now),binding.correction_acknowledged()));
                },
                crate::map_drive091::Method::Lab(crate::arena_movement091::Method::UnsupportedAim(method))=>{
                    motion.unsupported_aim(now)?;
                    recorded.push(format!("MAP_DRIVE_AIM_UNSUPPORTED session={} sequence={sequence} method_index={index} message_id={method} aim_methods={} exact_shape=true token_verified=true domain_applied=false transport_acknowledged=true",self.id,motion.aim_methods()));
                },
            }
        }
        *self=next;events.extend(recorded);Ok(())
    }
    fn receive_movement(&mut self,payload:&[u8],sequence:u32,now:Instant,events:&mut Vec<String>)->io::Result<()> {
        self.movement_guard(now)?;if self.map_drive {return Err(invalid());}
        let methods=crate::arena_movement091::methods(payload,crate::arena_vehicle091::VEHICLE_ENTITY_ID)?;
        let mut next=self.clone();let mut recorded=Vec::new();
        let motion=next.arena_motion.as_mut().ok_or_else(invalid)?;
        for (index,method) in methods.iter().enumerate() {
            match *method {
                crate::arena_movement091::Method::Move(command)=>{
                    let action=motion.command(command,now)?;
                    let flags=if command==crate::arena_movement091::Command::Forward {1}else{0};
                    let started=motion.started_seconds().map(|s|format!("{s:.9}")).unwrap_or_else(||"none".to_owned());
                    recorded.push(format!("ARENA_MOVE_COMMAND session={} sequence={sequence} method_index={index} flags={flags} action={} phase={} displacement_m={:.9} move_methods={} lab_elapsed_seconds={:.9} movement_started_seconds={started} token_verified=true domain_applied=true client_coordinates_used=false",self.id,action.name(),motion.phase().name(),motion.displacement(now),motion.move_methods(),motion.elapsed_seconds(now)));
                },
                crate::arena_movement091::Method::UnsupportedAim(method)=>{
                    motion.unsupported_aim(now)?;
                    recorded.push(format!("ARENA_AIM_UNSUPPORTED session={} sequence={sequence} method_index={index} message_id={method} aim_methods={} exact_shape=true token_verified=true domain_applied=false transport_acknowledged=true",self.id,motion.aim_methods()));
                },
            }
        }
        *self=next;events.extend(recorded);Ok(())
    }
    fn poll_movement(&mut self,now:Instant,events:&mut Vec<String>)->io::Result<Option<&'static str>> {
        if !self.arena_movement || self.arena_motion.is_none() {return Ok(None);}
        self.movement_guard(now)?;
        let mut next=self.clone();let mut recorded=Vec::new();
        let motion=next.arena_motion.as_mut().ok_or_else(invalid)?;
        let failed=match motion.poll(now)? {
            crate::arena_movement091::Pulse::None=>None,
            crate::arena_movement091::Pulse::Position {tick,position}=>{
                let speed=crate::map_drive091::authoritative_speed(motion,now);
                let body=if self.map_drive {
                    if next.map_binding.is_none() {return Err(invalid());}
                    crate::map_drive091::publication_body(crate::arena_vehicle091::VEHICLE_ENTITY_ID,tick,position,speed)?
                } else {crate::arena_movement091::position_body(crate::arena_vehicle091::VEHICLE_ENTITY_ID,tick,position)?};
                let sequence=next.tx.enqueue_body_tracked(&body)?;
                let started=motion.started_seconds().map(|s|format!("{s:.9}")).unwrap_or_else(||"none".to_owned());
                if self.map_drive {
                    recorded.push(format!("MAP_DRIVE_POSITION_QUEUED session={} reliable_sequence={sequence} body_bytes=65 game_tick={tick} tick_low={} phase={} x={:.9} y={:.9} z={:.9} speed={speed:.9} rspeed=0 displacement_m={:.9} lab_elapsed_seconds={:.9} movement_started_seconds={started} authoritative=true own_callback=true generic_control=false terrain=false client_coordinates_used=false",self.id,tick&255,motion.phase().name(),position[0],position[1],position[2],motion.displacement(now),motion.elapsed_seconds(now)));
                } else {
                    recorded.push(format!("ARENA_POSITION_QUEUED session={} reliable_sequence={sequence} body_bytes=31 game_tick={tick} tick_low={} phase={} x={:.9} y={:.9} z={:.9} displacement_m={:.9} lab_elapsed_seconds={:.9} movement_started_seconds={started} authoritative=true clock_source=own_monotonic_lab physics=false client_coordinates_used=false",self.id,tick&255,motion.phase().name(),position[0],position[1],position[2],motion.displacement(now),motion.elapsed_seconds(now)));
                }
                None
            },
            crate::arena_movement091::Pulse::Expired(reason)=>{
                recorded.push(format!("ARENA_MOVEMENT_FAILED session={} reason={reason} phase=failed diagnostic_success=false physics=false",self.id));Some(reason)
            },
        };
        *self=next;events.extend(recorded);Ok(failed)
    }
    fn ordinary_account_policy(&self)->io::Result<Option<&crate::map_drive_service091::AccountPolicy>> {
        if self.drive.is_none() {
            return if self.drive_account_policy.is_none(){Ok(None)}else{Err(invalid())};
        }
        let identity=self.identity.as_ref().ok_or_else(invalid)?;
        match self.drive_account_policy.as_deref() {
            Some(policy)=>{policy.validate(identity,self.hangar.as_ref().ok_or_else(invalid)?)?;Ok(Some(policy))},
            None if identity.account_id!=crate::arena_vehicle091::PRIMARY_ACCOUNT=>Ok(None),
            None=>Err(invalid()),
        }
    }
    fn drive_join(&mut self,now:Instant,events:&mut Vec<String>)->io::Result<()> {
        use crate::map_drive_world091 as world;
        if !self.active || self.arena_base || self.sync_mask!=7 || self.identity.is_none() || self.hangar.is_none()
            || self.outbox.len()>=128 {return Err(invalid());}
        self.ordinary_account_policy()?.ok_or_else(invalid)?;
        if self.arena_battle_preparation.is_some() {return Err(invalid());}
        let identity=self.identity.as_ref().ok_or_else(invalid)?;
        let state=self.hangar.as_ref().ok_or_else(invalid)?.state_sha256();
        let seed=crate::arena_vehicle091::load(identity,state)?;
        let generation=self.drive.as_ref().ok_or_else(invalid)?.generation.checked_add(1).ok_or_else(invalid)?;
        let preparation=crate::battle091::preparation::prepare_primary_ms1(&seed,identity,state,generation)?;
        let drive=self.drive.as_mut().ok_or_else(invalid)?;drive.join(now)?;
        self.drive_return_account=None;
        events.push(preparation.event(self.id));
        self.arena_battle_preparation=Some(preparation);
        self.arena_fire=Some(crate::battle091::fire::State::new());
        self.arena_vehicle_seed=Some(seed);self.outbox.push_back(world::queue_callback(true));
        events.push(format!("MAP_DRIVE_QUEUE session={} generation={} command=700 vehicle_inventory_id=1 map_request=0 queue_type=1 accepted=true worker_started=false",self.id,drive.generation));Ok(())
    }
    fn drive_cancel(&mut self,events:&mut Vec<String>)->io::Result<()> {
        use crate::map_drive_world091 as world;
        let drive=self.drive.as_mut().ok_or_else(invalid)?;
        if drive.phase!=world::Phase::Queued || self.arena_base || self.outbox.len()>=128{return Err(invalid());}
        drive.phase=world::Phase::Idle;drive.input=crate::map_drive_worker091::Input::STOP;
        self.arena_vehicle_seed=None;self.arena_battle_preparation=None;self.arena_fire=None;self.outbox.push_back(world::queue_callback(false));
        events.push(format!("MAP_DRIVE_QUEUE_CANCELLED session={} generation={} command=701 worker_revoked=true",self.id,drive.generation));Ok(())
    }
    fn drive_return(&mut self,reason:&str,events:&mut Vec<String>)->io::Result<()> {
        use crate::map_drive_world091 as world;
        let drive=self.drive.as_ref().ok_or_else(invalid)?;
        if !self.arena_base || !matches!(drive.phase,world::Phase::Enable|world::Phase::EntityRequest|world::Phase::Ready|world::Phase::Driving)
            || self.outbox.len()>=128{return Err(invalid());}
        let body=world::return_account(&self.identity.as_ref().ok_or_else(invalid)?.name)?;
        self.drive_return_account=Some(WarmAccountReturn {generation:drive.generation,
            queue_ahead:self.outbox.len(),creation:None,enabled:false,stale_avatar_envelopes:0});
        self.outbox.push_back(body);let drive=self.drive.as_mut().ok_or_else(invalid)?;
        drive.phase=world::Phase::Returning;drive.input=crate::map_drive_worker091::Input::STOP;drive.pending=false;drive.return_mask=0;
        self.arena_base=false;self.arena_vehicle_seed=None;self.arena_vehicle_announcement=None;self.arena_vehicle_creation=None;self.map_binding=None;
        self.arena_battle_preparation=None;self.arena_fire=None;
        // Preserve channel/history/caches and old mailbox IDs until the exact
        // reset/create is ACKed and native enableEntities opens the new epoch.
        events.push(format!("MAP_DRIVE_RETURN session={} generation={} reason={reason} worker_revoked=true reset_entities=true account_recreated=true profile_changed=false channel_reused=true",self.id,drive.generation));Ok(())
    }
    // Failure recovery is outside receive's clone/commit. Preserve that same
    // atomicity here and queue the real reset without waiting for another RPC.
    fn recover_drive_failure(&mut self,events:&mut Vec<String>)->io::Result<()> {
        let mut next=self.clone();let mut committed=Vec::new();
        if next.arena_base{next.drive_return("worker_or_publication_failure",&mut committed)?;}
        else{next.drive_cancel(&mut committed)?;}
        next.drain_outbox()?;*self=next;events.extend(committed);Ok(())
    }
    // Original Avatar RPCs may already be in the client's reliable queue when
    // a server-owned recovery reset arrives. ACK is transport, not the Python
    // lifecycle boundary: only actual ACK-bound09 opens the new Account epoch.
    fn drain_retired_drive_avatar(&mut self,payload:&[u8],sequence:u32,events:&mut Vec<String>)->io::Result<()> {
        use crate::map_drive_world091 as world;
        let d=self.drive.as_ref().ok_or_else(invalid)?;
        let warm=self.drive_return_account.as_ref().ok_or_else(invalid)?;
        if !self.active || !self.account_ready || self.arena_base || self.base_peer.is_none() || self.sync_mask!=7
            || d.phase!=world::Phase::Returning || warm.generation!=d.generation || warm.enabled
            || warm.stale_avatar_envelopes>=32 || d.input!=crate::map_drive_worker091::Input::STOP || d.pending{return Err(invalid());}
        self.ordinary_account_policy()?.ok_or_else(invalid)?;
        // Full512B/16-method validation includes ignored telemetry and optional
        // leave data; nothing here writes pose, input, worker or Account data.
        let methods=world::methods(payload)?;
        let warm=self.drive_return_account.as_mut().ok_or_else(invalid)?;warm.stale_avatar_envelopes+=1;
        events.push(format!("MAP_DRIVE_RETIRED_AVATAR_DRAIN session={} generation={} sequence={sequence} payload_bytes={} methods={} envelopes={} reset_acked={} awaiting_native_enable=true authority_revoked=true domain_applied=false",self.id,d.generation,payload.len(),methods.len(),warm.stale_avatar_envelopes,warm.creation.is_some_and(|(_,acked)|acked)));
        Ok(())
    }
    fn drive_warm_enable(&mut self,sequence:u32,events:&mut Vec<String>)->io::Result<()> {
        use crate::map_drive_world091::Phase;
        let drive=self.drive.as_ref().ok_or_else(invalid)?;
        let warm=self.drive_return_account.as_ref().ok_or_else(invalid)?;
        let (reset_sequence,acked)=warm.creation.ok_or_else(invalid)?;
        if !self.active || !self.account_ready || self.arena_base || self.base_peer.is_none()
            || self.sync_mask!=7 || drive.phase!=Phase::Returning || drive.return_mask!=0
            || drive.generation!=warm.generation || warm.enabled || !acked {return Err(invalid());}
        self.ordinary_account_policy()?.ok_or_else(invalid)?;
        // Ride07: original Account.onBecomePlayer calls resetEntityManager
        // before warm sync; per-Account ClientChat restarts request IDs1/2/3.
        // Deduplication stays strict inside the new Account epoch. Reliable
        // retries still use the unchanged channel history before this parser.
        self.request_ids.clear();self.unsupported_request_ids.clear();self.chat_request_ids.clear();
        self.drive_return_account.as_mut().ok_or_else(invalid)?.enabled=true;
        events.push(format!("MAP_DRIVE_ACCOUNT_ENABLED session={} generation={} client_sequence={sequence} reset_sequence={reset_sequence} reset_acked=true chat_epoch_reset=true response_queued=false cache_retained=true",self.id,drive.generation));
        Ok(())
    }
    fn drive_queue_info(&mut self,stale:bool,events:&mut Vec<String>)->io::Result<()> {
        use crate::map_drive_world091::{self as world,Phase};
        let drive=self.drive.as_ref().ok_or_else(invalid)?;
        if !self.active || self.sync_mask!=7 || drive.queue_info_requests>=32
            || (stale && (drive.phase!=Phase::Enable || !self.arena_base))
            || (!stale && (drive.phase!=Phase::Queued || self.arena_base || self.outbox.len()>=128)){return Err(invalid());}
        self.arena_vehicle_seed.as_ref().ok_or_else(invalid)?.validate_session(self.identity.as_ref().ok_or_else(invalid)?,self.hangar.as_ref().ok_or_else(invalid)?.state_sha256())?;
        if !stale{self.outbox.push_back(world::own_queue_info());}
        let drive=self.drive.as_mut().ok_or_else(invalid)?;drive.queue_info_requests+=1;
        events.push(format!("MAP_DRIVE_QUEUE_INFO session={} generation={} request=202 command=502 queue_type=1 requests={} phase={} stale_account_request={} response_queued={} queued_players={} domain_mutated=false",self.id,drive.generation,drive.queue_info_requests,
            if stale{"avatar_awaiting_enable"}else{"account_queued"},stale,!stale,if stale{0}else{1}));Ok(())
    }
    fn drive_account(&mut self,payload:&[u8],sequence:u32,now:Instant,events:&mut Vec<String>)->io::Result<()> {
        use crate::map_drive_world091::{self as world,Phase};
        if !payload.is_empty() && payload[0]!=9
            && self.drive.as_ref().is_some_and(|d|d.phase==Phase::Returning)
            && self.drive_return_account.as_ref().is_some_and(|w|!w.enabled) {
            return self.drain_retired_drive_avatar(payload,sequence,events);
        }
        if payload.len()>512{return Err(invalid());}let mut at=0;let mut count=0;let mut seen=Vec::new();
        while at<payload.len(){count+=1;if count>16{return Err(invalid());}
            if payload[at]==9 {self.drive_warm_enable(sequence,events)?;at+=1;continue;}
            if self.drive.as_ref().is_some_and(|d|d.phase==Phase::Returning)
                && !self.drive_return_account.as_ref().is_some_and(|w|w.enabled) {return Err(invalid());}
            if payload.len()-at<3{return Err(invalid());}
            let len=u16::from_le_bytes([payload[at+1],payload[at+2]]) as usize;
            let packet=payload.get(at..at+3+len).ok_or_else(invalid)?;at+=3+len;
            if seen.contains(&packet){return Err(invalid());}seen.push(packet);
            match world::account_command(packet)?{
                Some(world::AccountCommand::Join)=>self.drive_join(now,events)?,
                Some(world::AccountCommand::Cancel)=>self.drive_cancel(events)?,
                Some(world::AccountCommand::QueueInfo)=>self.drive_queue_info(false,events)?,
                None=>{
                    let returning=self.drive.as_ref().is_some_and(|d|d.phase==Phase::Returning);
                    if returning && packet.len()==23 && packet[..3]==[0x8e,20,0] {
                        let id=i16::from_le_bytes([packet[3],packet[4]]);let command=i16::from_le_bytes([packet[5],packet[6]]);
                        let rev=i64::from_le_bytes(packet[7..15].try_into().map_err(|_|invalid())?);
                        let a=i32::from_le_bytes(packet[15..19].try_into().map_err(|_|invalid())?);
                        let b=i32::from_le_bytes(packet[19..23].try_into().map_err(|_|invalid())?);
                        if [100,300,600].contains(&command){
                            if id<=0 || self.request_ids.contains(&id) || self.request_ids.len()>=32{return Err(invalid());}
                            let r=crate::account091::Request{id,command};
                            match command{
                                100=>{
                                    if rev!=1 || b!=0 || self.outbox.len()>=128{return Err(invalid());}
                                    self.ordinary_account_policy()?.ok_or_else(invalid)?;
                                    // Original setAccount(None) saves the persistent
                                    // state. Its next descriptor may differ from the
                                    // cold login hint; only this first warm epoch may
                                    // establish a new opaque hash, never client data.
                                    self.account_cache_hash=if a==0{None}else{Some(a)};
                                    self.outbox.push_back(crate::hangar091::response_refresh(&r)?);
                                },
                                300=>{
                                    if rev!=3 || !(0..=16448).contains(&a) || (a==0 && b!=0){return Err(invalid());}
                                    let bodies=crate::hangar091::response(&r,self.hangar.as_ref().ok_or_else(invalid)?)?;
                                    if self.outbox.len()+bodies.len()>127{return Err(invalid());}self.outbox.extend(bodies);
                                },
                                600=>{
                                    if b!=0{return Err(invalid());}let f=self.hangar.as_ref().ok_or_else(invalid)?;f.validate_dossier_cursor(rev,a)?;
                                    let bodies=crate::hangar091::response(&r,f)?;if self.outbox.len()+bodies.len()>127{return Err(invalid());}self.outbox.extend(bodies);
                                },_=>return Err(invalid()),
                            }
                            self.request_ids.push(id);let bit=crate::account091::command_bit(command);
                            let drive=self.drive.as_mut().ok_or_else(invalid)?;
                            if drive.return_mask&bit!=0{return Err(invalid());}drive.return_mask|=bit;
                            events.push(format!("MAP_DRIVE_RETURN_SYNC session={} generation={} request={id} command={command} revision={rev} client_state_applied=false",self.id,drive.generation));
                            if drive.return_mask==7{
                                if self.outbox.len()>=128{return Err(invalid());}
                                self.outbox.push_back(crate::hangar091::show_gui(self.identity.as_ref().ok_or_else(invalid)?.database_id)?);
                                drive.phase=Phase::Idle;events.push(format!("MAP_DRIVE_HANGAR_RETURNED session={} generation={} data_changed=false",self.id,drive.generation));
                            }
                            continue;
                        }
                    }
                    self.receive_account(packet,events)?;
                },
            }
        }Ok(())
    }
    /// Recognize the exact native Avatar BaseMethod fire stream and apply only
    /// server-owned MS-1 ammunition/reload state.  Unknown method families are
    /// left to their existing parser; a payload that starts as fire but is
    /// malformed fails closed before any state or ACK-visible queue mutation.
    fn receive_battle_fire(&mut self,payload:&[u8],sequence:u32,now:Instant,events:&mut Vec<String>)->io::Result<Option<()>> {
        let Some(commands)=crate::battle091::fire::parse(payload)? else {return Ok(None);};
        if !self.active || !self.account_ready || !self.arena_base || self.base_peer.is_none()
            || self.sync_mask!=7 || self.arena_battle_preparation.is_none() || self.arena_fire.is_none()
            || now<self.created_at || now<self.last_rx {return Err(invalid());}
        let seed=self.arena_vehicle_seed.as_ref().ok_or_else(invalid)?;
        let identity=self.identity.as_ref().ok_or_else(invalid)?;
        let state=self.hangar.as_ref().ok_or_else(invalid)?.state_sha256();
        let generation=self.drive.as_ref().map_or(1,|d|d.generation);
        seed.validate_session(identity,state)?;
        self.arena_battle_preparation.as_ref().ok_or_else(invalid)?.validate_for(seed,identity,state,generation)?;
        // The live map-drive service dispatches Avatar traffic by the
        // presence of `drive`; its legacy checkpoint flag is only populated
        // by the older arena-control probe.  Treat both as the same
        // authoritative driving route so the real owner path cannot reject
        // fire merely because that diagnostic flag is false.
        if self.map_drive || self.drive.is_some() {
            let drive=self.drive.as_ref().ok_or_else(invalid)?;
            if drive.phase!=crate::map_drive_world091::Phase::Driving || self.map_binding.is_none() {
                return Err(invalid());
            }
        } else if self.arena_movement || self.drive.is_some() || !self.arena_ready
            || self.arena_vehicle!=ArenaVehicleStage::Queued || self.arena_preparation.is_none() {
            return Err(invalid());
        }

        let mut next=self.clone();
        let outcomes=next.arena_fire.as_mut().ok_or_else(invalid)?.apply(&commands,now)?;
        let mut response=Vec::new();
        for outcome in &outcomes {
            if let crate::battle091::fire::Outcome::AcceptedShot {ammo_remaining}=*outcome {
                response.extend(crate::battle091::fire::accepted_shot_body(
                    ammo_remaining,crate::arena_vehicle091::VEHICLE_ENTITY_ID)?);
            }
        }
        let response_sequence=if response.is_empty() {None}
            else {Some(next.tx.enqueue_body_tracked(&response)?)};
        *self=next;
        for outcome in outcomes {
            match outcome {
                crate::battle091::fire::Outcome::AcceptedShot {ammo_remaining}=>events.push(format!(
                    "BATTLE_SHOT_ACCEPTED session={} sequence={sequence} method=vehicle_shoot base_method=0x88 response_methods=0x44,0x46 ammo_compact_descr={} ammo_remaining={} reload_seconds={} response_sequence={} domain_applied=true projectile=NOT_RUN hit=NOT_RUN damage=NOT_RUN",
                    self.id,crate::battle091::fire::MS1_AP,ammo_remaining,crate::battle091::fire::MS1_RELOAD_SECONDS,
                    response_sequence.map_or_else(||"none".to_owned(),|value|value.to_string()))),
                crate::battle091::fire::Outcome::RejectedReload=>events.push(format!(
                    "BATTLE_SHOT_REJECTED session={} sequence={sequence} method=vehicle_shoot base_method=0x88 reason=gun_reload domain_applied=false ammo_mutation=false transport_acknowledged=true",
                    self.id)),
                crate::battle091::fire::Outcome::RejectedNoAmmo=>events.push(format!(
                    "BATTLE_SHOT_REJECTED session={} sequence={sequence} method=vehicle_shoot base_method=0x88 reason=no_ammo domain_applied=false ammo_mutation=false transport_acknowledged=true",
                    self.id)),
                crate::battle091::fire::Outcome::ReplenishUnsupported=>events.push(format!(
                    "BATTLE_REPLENISH_UNSUPPORTED session={} sequence={sequence} method=vehicle_replenishAmmo base_method=0x89 domain_applied=false ammo_grant=false economy=false transport_acknowledged=true",
                    self.id)),
            }
        }
        Ok(Some(()))
    }

    /// Publish the authoritative end of a single-shot reload once the server
    /// monotonic deadline has elapsed.  Work is performed on a clone so a
    /// full reliable queue or an encoder/phase error cannot clear the reload
    /// state without its matching client callback.
    fn poll_battle_reload(&mut self,now:Instant,events:&mut Vec<String>)->io::Result<()> {
        let Some(fire)=self.arena_fire.as_ref() else {return Ok(());};
        let Some(until)=fire.reload_until() else {return Ok(());};
        if now<until {return Ok(());}
        if !self.active || !self.account_ready || !self.arena_base || self.base_peer.is_none()
            || self.sync_mask!=7 || self.arena_battle_preparation.is_none()
            || now<self.created_at || now<self.last_rx {return Err(invalid());}
        let seed=self.arena_vehicle_seed.as_ref().ok_or_else(invalid)?;
        let identity=self.identity.as_ref().ok_or_else(invalid)?;
        let state=self.hangar.as_ref().ok_or_else(invalid)?.state_sha256();
        let generation=self.drive.as_ref().map_or(1,|d|d.generation);
        seed.validate_session(identity,state)?;
        self.arena_battle_preparation.as_ref().ok_or_else(invalid)?.validate_for(seed,identity,state,generation)?;
        if self.map_drive || self.drive.is_some() {
            let drive=self.drive.as_ref().ok_or_else(invalid)?;
            if drive.phase!=crate::map_drive_world091::Phase::Driving || self.map_binding.is_none() {return Err(invalid());}
        } else if self.arena_movement || self.drive.is_some() || !self.arena_ready
            || self.arena_vehicle!=ArenaVehicleStage::Queued || self.arena_preparation.is_none() {return Err(invalid());}
        let mut next=self.clone();
        if !next.arena_fire.as_mut().ok_or_else(invalid)?.finish_reload_if_due(now) {return Ok(());}
        let body=crate::battle091::fire::completed_reload_body(crate::arena_vehicle091::VEHICLE_ENTITY_ID)?;
        let sequence=next.tx.enqueue_body_tracked(&body)?;
        *self=next;
        events.push(format!(
            "BATTLE_RELOAD_COMPLETE session={} reliable_sequence={} method=updateVehicleGunReloadTime native_method=0x46 vehicle_id=152043523 time_left=0.0 base_time={} body_bytes=14 domain_applied=true",
            self.id,sequence,crate::battle091::fire::MS1_RELOAD_SECONDS));
        Ok(())
    }

    fn drive_avatar(&mut self,payload:&[u8],sequence:u32,now:Instant,events:&mut Vec<String>)->io::Result<()> {
        use crate::map_drive_world091::{self as world,Phase,Method};
        if !self.active || !self.account_ready || !self.arena_base || self.base_peer.is_none() || self.sync_mask!=7
            || now<self.created_at || now<self.last_rx{return Err(invalid());}
        self.arena_vehicle_seed.as_ref().ok_or_else(invalid)?.validate_session(self.identity.as_ref().ok_or_else(invalid)?,self.hangar.as_ref().ok_or_else(invalid)?.state_sha256())?;
        let current=self.drive.as_ref().ok_or_else(invalid)?;let generation=current.generation;
        self.arena_battle_preparation.as_ref().ok_or_else(invalid)?.validate_for(
            self.arena_vehicle_seed.as_ref().ok_or_else(invalid)?,self.identity.as_ref().ok_or_else(invalid)?,
            self.hangar.as_ref().ok_or_else(invalid)?.state_sha256(),generation)?;
        let late=if current.phase==Phase::Enable{world::late_queue_info(payload)?}else{None};
        if let Some(enable)=late{self.drive_queue_info(true,events)?;if !enable{return Ok(());}}
        let current=self.drive.as_ref().ok_or_else(invalid)?;
        if current.phase==Phase::Enable && (payload==[9] || late==Some(true)){
            let body=world::announcement(self.arena_vehicle_seed.as_ref().ok_or_else(invalid)?,current.map.as_ref().ok_or_else(invalid)?,generation,current.pose.as_ref().ok_or_else(invalid)?)?;
            let bytes=body.len();let seq=self.tx.enqueue_body_tracked(&body)?;self.arena_vehicle_announcement=Some((seq,false));
            self.drive.as_mut().ok_or_else(invalid)?.phase=Phase::EntityRequest;
            events.push(format!("MAP_DRIVE_ANNOUNCED session={} generation={generation} request_sequence={sequence} reliable_sequence={seq} body_bytes={bytes} vehicle_created=false",self.id));return Ok(());
        }
        if current.phase==Phase::EntityRequest && crate::arena_vehicle091::is_own_entity_update_request(payload){
            if !self.arena_vehicle_announcement.is_some_and(|(_,ack)|ack){return Err(invalid());}
            let body=world::create_vehicle(self.arena_vehicle_seed.as_ref().ok_or_else(invalid)?,current.pose.as_ref().ok_or_else(invalid)?)?;
            let seq=self.tx.enqueue_body_tracked(&body)?;self.arena_vehicle_creation=Some((seq,false));self.drive.as_mut().ok_or_else(invalid)?.phase=Phase::Ready;
            events.push(format!("MAP_DRIVE_VEHICLE_CREATED session={} generation={generation} request_sequence={sequence} reliable_sequence={seq} body_bytes=97 announcement_acked=true",self.id));return Ok(());
        }
        if crate::arena_ready091::validate_compound(payload,world::OWN).is_ok(){
            if current.phase==Phase::Driving{events.push(format!("MAP_DRIVE_READY_DUPLICATE session={} generation={generation} enqueued=false clock_reset=false",self.id));return Ok(());}
            if current.phase!=Phase::Ready || !self.arena_vehicle_creation.is_some_and(|(_,ack)|ack){return Err(invalid());}
            let mut body=world::binding(generation,current.pose.as_ref().ok_or_else(invalid)?)?;
            body.extend(crate::battle091::native_ammo::panel_bodies(
                self.arena_battle_preparation.as_ref().ok_or_else(invalid)?.loadout(),
                crate::arena_control091::AVATAR_ENTITY_ID)?);
            body.extend(crate::battle091::native_ammo::selected_shell_body(
                self.arena_battle_preparation.as_ref().ok_or_else(invalid)?.loadout(),
                crate::arena_control091::AVATAR_ENTITY_ID)?);
            body.extend(crate::battle091::native_ammo::initial_reload_body(
                self.arena_battle_preparation.as_ref().ok_or_else(invalid)?.loadout(),
                crate::arena_control091::AVATAR_ENTITY_ID)?);
            if body.len()!=122+crate::battle091::native_ammo::BATTLE_SUFFIX_BYTES {return Err(invalid());}
            let bytes=body.len();let seq=self.tx.enqueue_body_tracked(&body)?;
            self.map_binding=Some(crate::map_drive091::Binding::new(seq));let d=self.drive.as_mut().ok_or_else(invalid)?;d.phase=Phase::Driving;d.created=Some(now);
             events.push(format!("MAP_DRIVE_BOUND session={} generation={generation} request_sequence={sequence} reliable_sequence={seq} body_bytes={bytes} native_ammo_panel_appended=true native_selected_shell_appended=true native_initial_reload_appended=true native_tick=1000 period=3 create_acked=true bind_applied=true domain_ready=true generic_control=false",self.id));
             let panel=self.arena_battle_preparation.as_ref().ok_or_else(invalid)?.loadout();
             events.push(format!("BATTLE_NATIVE_AMMO_PANEL_CANDIDATE session={} generation={generation} route=drive_avatar reliable_sequence={seq} {}",self.id,crate::battle091::native_ammo::panel_event_fields(panel)?));
             events.push(format!("BATTLE_NATIVE_SHELL_SELECTED session={} generation={generation} route=drive_avatar native_method=0x40 setting=CURRENT_SHELLS compact_descr=2570 selected_shell_body_bytes=7 native_static=true native_delivery_candidate=true native_receipt=NOT_RUN",self.id));
             events.push(format!("BATTLE_NATIVE_INITIAL_RELOAD session={} generation={generation} route=drive_avatar native_method=0x46 vehicle_id=152043523 time_left=0.0 base_time=2.5 body_bytes=14 native_static=true native_delivery_candidate=true native_receipt=NOT_RUN",self.id));
            for method in ["vehicle_changeSetting","autoAim"]{events.push(format!("MAP_DRIVE_UNSUPPORTED session={} generation={generation} method={method} domain_applied=false",self.id));}return Ok(());
        }
        if payload.is_empty(){return Ok(());}
        if self.receive_battle_fire(payload,sequence,now,events)?.is_some() {return Ok(());}
        let methods=world::methods(payload)?;
        // Closed manual re-entry packet5663: 8a01000106, cumulativeACK1863
        // for binding1862. Native Move may precede correction6 in one compound.
        // Permit this staged input only inside the fully parsed envelope. The
        // exact later6 must still pass Binding's real force-ACK/budget checks;
        // receive clone/commit rolls back all input/ACK if any later check fails.
        // No worker side effect runs until that whole transaction commits.
        let correction_in_compound=methods.contains(&Method::CorrectionAck);
        for method in methods{
            if method==Method::Leave{self.drive_return("native_leaveArena",events)?;continue;}
            let d=self.drive.as_mut().ok_or_else(invalid)?;
            if d.phase!=Phase::Driving{return Err(invalid());}
            match method{
                Method::CorrectionAck=>{
                    let binding=self.map_binding.as_mut().ok_or_else(invalid)?;let first=binding.correction_ack()?;
                    d.correction_acks=binding.correction_acks();events.push(format!("MAP_DRIVE_FORCE_ACK session={} generation={generation} sequence={sequence} message=6 force_sequence={} force_acked=true first={first}",self.id,binding.force_sequence));
                },
                Method::IgnoredTelemetry(id)=>{
                    if d.telemetry>=500_000{return Err(invalid());}d.telemetry+=1;
                    events.push(format!("MAP_DRIVE_CLIENT_TELEMETRY session={} generation={generation} sequence={sequence} method={id} count={} ignored=true domain_applied=false",self.id,d.telemetry));
                },
                Method::Move(flags,input)=>{
                    if d.commands>=100_000 || (flags!=0 && d.correction_acks==0 && !correction_in_compound){return Err(invalid());}
                    d.commands+=1;d.input=input;
                    events.push(format!("MAP_DRIVE_INPUT session={} generation={generation} sequence={sequence} flags={flags} throttle={} steer={} brake={} command_count={} client_position_used=false",self.id,input.throttle,input.steer,input.brake,d.commands));
                },
                Method::UnsupportedMove(flags)=>{
                    if d.commands>=100_000{return Err(invalid());}d.commands+=1;d.input=crate::map_drive_worker091::Input::STOP;
                    events.push(format!("MAP_DRIVE_UNSUPPORTED_MOVE session={} generation={generation} sequence={sequence} flags={flags} command_count={} domain_applied=false failsafe_stop=true policy=test_lab_neutral",self.id,d.commands));
                },
                Method::UnsupportedAim(id)=>{
                    if d.aim>=500_000{return Err(invalid());}d.aim+=1;
                    events.push(format!("MAP_DRIVE_UNSUPPORTED session={} generation={generation} sequence={sequence} method={id} count={} domain_applied=false",self.id,d.aim));
                },
                Method::UnsupportedCameraAutorotation(enabled)=>{
                    if d.aim>=500_000{return Err(invalid());}d.aim+=1;
                    events.push(format!("MAP_DRIVE_CAMERA_PREFERENCE session={} generation={generation} sequence={sequence} autorotation={enabled} count={} transport_accepted=true domain_applied=false physics_setting_changed=false policy=test_lab_keyboard_only",self.id,d.aim));
                },Method::Leave=>unreachable!(),
            }
        }Ok(())
    }
    fn receive_account(&mut self,payload:&[u8],events:&mut Vec<String>)->io::Result<()> {
use crate::hangar091::Incoming;
let requests=if self.hangar.is_some() {
    if self.identity.is_some() {crate::hangar091::requests_interactive(payload)?}
    else {crate::hangar091::requests(payload)?}}
    else {crate::account091::requests(payload)?.into_iter().map(Incoming::Sync).collect()};
for incoming in requests {
    let r=match incoming {
        Incoming::Sync(r)=>r,
        Incoming::DossierSync {request,version,last_change_time}=>{
            if self.identity.is_none() {return Err(invalid());}
            self.hangar.as_ref().ok_or_else(invalid)?
                .validate_dossier_cursor(version,last_change_time)?;
            events.push(format!("DOSSIER_CACHE_CURSOR session={} request={} version={version} last_change_time={last_change_time} scope=authenticated_fixture",self.id,request.id));
            request
        },
        Incoming::CachedSync {request,descriptor_a,descriptor_b}=>{
            if self.identity.is_none() || self.hangar.is_none() {return Err(invalid());}
            // The cache descriptor never changes data or selects a
            // cached-success response. Continue through the same
            // once-only authoritative full-stream path as cold sync.
            events.push(format!("INITIAL_CACHE_HINT session={} request={} command={} descriptor_a={descriptor_a} descriptor_b={descriptor_b} response=full_stream client_state_applied=false",self.id,request.id,request.command));
            if request.command==100 {self.account_cache_hash=Some(descriptor_a);}
            request
        },
        Incoming::ServerStats=>{
            if (self.identity.is_none() && self.stats_requests>=16) || self.outbox.len()>=128 {return Err(invalid());}
            self.stats_requests+=1;
            self.outbox.push_back(crate::hangar091::server_stats());
            events.push(format!("SERVER_STATS session={} cluster_ccu=1 region_ccu=1 scope=own_lab",self.id));
            continue;
        },
        Incoming::UnsupportedIntArray{id,command,argument_count}=>{
            if self.identity.is_none() || self.request_ids.contains(&id)
                || self.unsupported_request_ids.contains(&id) || self.outbox.len()>=128 {return Err(invalid());}
            self.outbox.push_back(crate::hangar091::unavailable_response(id)?);
            self.unsupported_request_ids.push_back(id);
            if self.unsupported_request_ids.len()>64 {self.unsupported_request_ids.pop_front();}
            events.push(format!("APPLICATION_UNAVAILABLE session={} request={id} command={command} method=doCmdIntArr arguments={argument_count} result=-10 state_changed=false",self.id));
            continue;
        },
        Incoming::Language{id}=>{
            if self.request_ids.contains(&id) || self.request_ids.len()>=32 {return Err(invalid());}
            self.request_ids.push(id);self.language=Some("ru");
            events.push(format!("ACCOUNT_LANGUAGE session={} request={} language=ru persisted=session_only",self.id,id));
            continue;
        },
        Incoming::Refresh(r)=>{
            self.ordinary_account_policy()?;
            if self.account_cache_hash.is_some() {return Err(invalid());}
            if self.sync_mask&1==0 || self.request_ids.contains(&r.id) || self.request_ids.len()>=32 || self.outbox.len()>=128 {return Err(invalid());}
            self.outbox.push_back(crate::hangar091::response_refresh(&r)?);
            self.request_ids.push(r.id);
            events.push(format!("ACCOUNT_REFRESH session={} request={} command=100 revision=1 changed=false",self.id,r.id));
            continue;
        },
        Incoming::CachedRefresh {request:r,persistent_hash}=>{
            self.ordinary_account_policy()?;
            if self.identity.is_none() || self.account_cache_hash!=Some(persistent_hash)
                || self.sync_mask&1==0 || self.request_ids.contains(&r.id)
                || self.request_ids.len()>=32 || self.outbox.len()>=128 {return Err(invalid());}
            self.outbox.push_back(crate::hangar091::response_refresh(&r)?);
            self.request_ids.push(r.id);
            events.push(format!("REFRESH_CACHE_HINT session={} request={} descriptor_a={persistent_hash} descriptor_b=0 response=no_change client_state_applied=false",self.id,r.id));
            events.push(format!("ACCOUNT_REFRESH session={} request={} command=100 revision=1 changed=false",self.id,r.id));
            continue;
        },
        Incoming::Chat(r)=>{
            if self.chat_request_ids.contains(&r.id) || self.chat_request_ids.len()>=128 || self.outbox.len()>=128 {return Err(invalid());}
            let response=crate::hangar091::chat_response(&r)?;
            if let Some(body)=response {
                self.outbox.push_back(body);
                events.push(format!("CHAT_ROSTER_EMPTY session={} request={} entries=0 result=0",self.id,r.id));
            } else {
                let kind=if r.command==10 {"FRIEND_PRESENCE_EMPTY"} else {"SERVICE_HISTORY_EMPTY"};
                events.push(format!("{kind} session={} request={} entries=0",self.id,r.id));
            }
            self.chat_request_ids.push(r.id);
            continue;
        },
    };
    let bit=crate::account091::command_bit(r.command);
    if self.sync_mask&bit!=0 || self.request_ids.contains(&r.id) {return Err(invalid());}
    if let Some(fixtures)=&self.hangar {
        let bodies=if r.command==100 {
            if let Some(policy)=self.ordinary_account_policy()? {
                let bodies=policy.response(&r,self.identity.as_ref().ok_or_else(invalid)?,fixtures)?;
                events.push(policy.stream_event(self.id,r.id));bodies
            } else {crate::hangar091::response(&r,fixtures)?}
        } else {crate::hangar091::response(&r,fixtures)?};
        if self.outbox.len()+bodies.len()>128 {return Err(invalid());}
        self.outbox.extend(bodies);
    } else {self.tx.enqueue_body(&crate::account091::response(&r))?;}
    self.sync_mask|=bit;self.request_ids.push(r.id);
    events.push(format!("ACCOUNT_SYNC_REQUEST session={} request={} command={} applied=1",self.id,r.id,r.command));
    if self.hangar.is_some() && self.sync_mask==7 {
        if self.outbox.len()>=128 {return Err(invalid());}
        let database_id=self.identity.as_ref().map(|p|p.database_id).unwrap_or(900001);
        self.outbox.push_back(crate::hangar091::show_gui(database_id)?);
        events.push(format!("ACCOUNT_SHOW_GUI_QUEUED session={} database_id={database_id}",self.id));
    }
}
        Ok(())
    }
    fn validate_frame(&self,f:&Frame,depth:usize)->io::Result<()> {
        if depth>8 {return Err(invalid());}
        self.tx.validate_ack(f)?;
        if f.flags&0x10!=0 {
            let n=f.sequence.ok_or_else(invalid)?;
            // Only two measured client application messages in this lab scenario.
            if f.body.len()<6 || f.body[0]!=1 || f.body[1..5]!=self.token.to_le_bytes() {return Err(invalid());}
            let valid=(n==0 && f.body[5..]==[9]) || (n==1 && self.active && f.body[5..]==[11,0]);
            if !valid || n>self.rx {return Err(invalid());}
        } else if !self.active || !f.body.is_empty() || !f.piggybacks.is_empty() {return Err(invalid());}
        for p in &f.piggybacks {self.validate_frame(p,depth+1)?;} Ok(())
    }
    fn receive(&mut self,f:&Frame,now:Instant)->io::Result<bool> {
        if self.account_ready {
            // Validate and apply the complete piggyback tree atomically. A later
            // invalid message cannot advance ACK/state or consume earlier RPCs.
            let mut next=self.clone();let mut events=Vec::new();
            let close=next.receive_ready(f,now,&mut events,0,&mut 32)?;
            *self=next;for event in events {println!("{event}");}return Ok(close);
        }
        self.validate_frame(f,0)?;self.tx.acknowledge(f)?;
        println!("CHANNEL_ACK session={} cumulative={} selective={:?} pending={}",self.id,self.tx.cumulative,f.selective,self.tx.len());
        let mut close=false;
        for p in &f.piggybacks {close|=self.receive(p,now)?;}
        if f.flags&0x10!=0 {
            let n=f.sequence.ok_or_else(invalid)?;
            if n==self.rx {
                self.rx+=1;
                if n==0 {
                    self.active=true;
                    if self.account_probe {
                        let creation=if self.account_ready {crate::account091::creation_ready()} else {crate::account091::creation()};
                        self.tx.enqueue_body(&creation)?;
                        println!("ACCOUNT_CREATE_QUEUED session={} entity_id={} type_id=0",self.id,crate::account091::ENTITY_ID);
                    } else {self.tx.enqueue()?;}
                    self.tx.enqueue()?;
                    println!("SESSION_ACTIVE id={} account=p02-local-test active=1",self.id);
                    println!("BASEAPP_NEXT_OBSERVED bytes=24 clear_bytes=16 token_verified=true");
                } else {close=true;}
            } else {println!("CLIENT_DUPLICATE session={} sequence={n}",self.id);}
        }
        self.last_rx=now;Ok(close)
    }
    fn receive_ready(&mut self,f:&Frame,now:Instant,events:&mut Vec<String>,depth:usize,budget:&mut usize)->io::Result<bool> {
        if depth>8 || *budget==0 {return Err(invalid());}*budget-=1;
        self.tx.validate_ack(f)?;
        let mut close=false;
        for p in &f.piggybacks {
            if close {return Err(invalid());}
            close|=self.receive_ready(p,now,events,depth+1,budget)?;
        }
        self.tx.acknowledge(f)?;
        if let Some((sequence,acked))=&mut self.arena_vehicle_announcement {
            *acked|=self.tx.cumulative>*sequence || f.selective.contains(sequence);
        }
        if let Some((sequence,acked))=&mut self.arena_vehicle_creation {
            *acked|=self.tx.cumulative>*sequence || f.selective.contains(sequence);
        }
        if let Some(binding)=&mut self.map_binding {
            binding.force_acked|=self.tx.cumulative>binding.force_sequence || f.selective.contains(&binding.force_sequence);
        }
        if let Some((sequence,acked))=self.drive_return_account.as_mut().and_then(|w|w.creation.as_mut()) {
            *acked|=self.tx.cumulative>*sequence || f.selective.contains(sequence);
        }
        events.push(format!("CHANNEL_ACK session={} cumulative={} selective={:?} pending={}",self.id,self.tx.cumulative,f.selective,self.tx.len()));
        if f.flags&0x10!=0 {
            let n=f.sequence.ok_or_else(invalid)?;
            let limit=if self.identity.is_some() {transport091::INTERACTIVE_MAX_SEQUENCE} else {transport091::MAX_SEQUENCE};
            if n>=limit || n>self.rx {return Err(invalid());}
            // gui-06: a token-only heartbeat can be retransmitted inside a
            // piggyback with an empty body. Normalize only this measured pair;
            // authenticated RPC bytes remain exact and wrong tokens still fail.
            let logical=if self.hangar.is_some() && self.active && n>0 {
                empty_envelope(&f.body,self.token)?
            } else {f.body.as_slice()};
            if n<self.rx {
                if self.received.iter().find(|(sequence,_)|*sequence==n).map(|(_,body)|body.as_slice())!=Some(logical) {return Err(invalid());}
                events.push(format!("CLIENT_DUPLICATE session={} sequence={n}",self.id));
            } else {
                if n==0 {
                    if f.body!=[vec![1],self.token.to_le_bytes().to_vec(),vec![9]].concat() {return Err(invalid());}
                    self.active=true;
                    let creation=if let Some(identity)=&self.identity {crate::hangar091::creation_named(&identity.name)?}
                        else if self.hangar.is_some() {crate::hangar091::creation()} else {crate::account091::creation_ready()};
                    self.tx.enqueue_body(&creation)?;self.tx.enqueue()?;
                    events.push(format!("ACCOUNT_CREATE_QUEUED session={} entity_id={} type_id=0",self.id,crate::account091::ENTITY_ID));
                    events.push(format!("SESSION_ACTIVE id={} account={} active=1",self.id,
                        self.identity.as_ref().map(|p|p.account_id.as_str()).unwrap_or("p02-local-test")));
                } else {
                    if !self.active || close {return Err(invalid());}
                    if !f.body.is_empty() {
                        if f.body.len()<(if self.hangar.is_some(){5}else{6}) || f.body[0]!=1 || f.body[1..5]!=self.token.to_le_bytes() {return Err(invalid());}
                        if f.body[5..]==[11,0] {close=true;}
                        else if self.drive.is_some() {
                            if self.arena_base {self.drive_avatar(&f.body[5..],n,now,events)?;}
                            else {self.drive_account(&f.body[5..],n,now,events)?;}
                        } else if self.arena_base
                            && self.arena_vehicle==ArenaVehicleStage::AwaitingEnable && f.body[5..]==[9] {
                            let body_bytes=self.queue_arena_vehicle_announcement()?;
                            events.push(format!("ARENA_ENABLE_ENTITIES session={} sequence={n} payload_bytes=1 phase=avatar_base checkpoint=avatar_vehicle checkpoint_version=2 token_verified=true domain_stage_advanced=true",self.id));
                            events.push(format!("ARENA_VEHICLE_ANNOUNCED session={} checkpoint_version=2 avatar_entity_id={} space_id=1 player_vehicle_id=152043523 native_inventory_id=1 type_compact_descr=3329 health=90 geometry=spaces/01_karelia position_source=original_space_settings body_bytes={body_bytes} state_sha256={} cell=true roster_rows=1 vehicle_created=false alias=0 reliable_sequence={} awaiting_entity_request=true ammo_transferred=false channel_reused=true",self.id,crate::arena_control091::AVATAR_ENTITY_ID,crate::arena_vehicle091::PRIMARY_STATE_SHA256,self.arena_vehicle_announcement.ok_or_else(invalid)?.0));
                        } else if self.arena_base && self.arena_vehicle==ArenaVehicleStage::AwaitingEntityRequest
                            && crate::arena_vehicle091::is_own_entity_update_request(&f.body[5..]) {
                            let body_bytes=self.queue_requested_arena_vehicle()?;
                            events.push(format!("ARENA_ENTITY_UPDATE_REQUEST session={} sequence={n} checkpoint_version=2 message_id=8 payload_bytes=4 entity_id=152043523 cache_stamps=0 token_verified=true announcement_sequence={} announcement_acked=true domain_stage_advanced=true",self.id,self.arena_vehicle_announcement.ok_or_else(invalid)?.0));
                            events.push(format!("ARENA_VEHICLE_QUEUED session={} checkpoint_version=2 entity_id=152043523 type_id=2 native_inventory_id=1 type_compact_descr=3329 health=90 body_bytes={body_bytes} state_sha256={} request_sequence={n} one_shot=true ammo_transferred=false channel_reused=true",self.id,crate::arena_vehicle091::PRIMARY_STATE_SHA256));
                            if self.arena_ready {
                                events.push(format!("ARENA_READY_WAITING session={} checkpoint={} create_sequence={} ready_accepted=false",self.id,if self.map_drive {"avatar_drive"}else if self.arena_movement {"avatar_movement"}else{"avatar_ready"},self.arena_vehicle_creation.ok_or_else(invalid)?.0));
                            }
                        } else if self.arena_base
                            && self.arena_space==ArenaSpaceStage::AwaitingEnable && f.body[5..]==[9] {
                            // Exact post-reset native enableEntities observed in
                            // base01/base02. Only this opt-in phase may advance;
                            // a reliable retry is handled by history above.
                            self.queue_arena_space()?;
                            events.push(format!("ARENA_ENABLE_ENTITIES session={} sequence={n} payload_bytes=1 phase=avatar_base token_verified=true domain_stage_advanced=true",self.id));
                            events.push(format!("ARENA_SPACE_QUEUED session={} avatar_entity_id={} space_id=1 player_vehicle_id=152043523 geometry=spaces/01_karelia position_source=original_space_settings cell=true vehicle_created=false channel_reused=true",self.id,crate::arena_control091::AVATAR_ENTITY_ID));
                        } else if self.arena_ready && crate::arena_ready091::validate_compound(
                            &f.body[5..],crate::arena_vehicle091::VEHICLE_ENTITY_ID).is_ok() {
                            if self.arena_preparation.is_some() || self.arena_motion.is_some() {
                                events.push(format!("ARENA_READY_DUPLICATE session={} sequence={n} reset_deadline=false enqueued=false domain_applied=false",self.id));
                            } else if self.map_drive {
                                let generation=self.drive.as_ref().map_or(1,|d|d.generation);
                                let (create_sequence,sequence)=self.queue_map_binding(now)?;
                                let panel=self.arena_battle_preparation.as_ref().ok_or_else(invalid)?.loadout();
                                events.push(format!("MAP_DRIVE_BINDING_QUEUED session={} sequence={n} checkpoint=avatar_drive application_bytes=33 methods=4 create_sequence={create_sequence} create_acked=true reliable_sequence={sequence} body_bytes=176 native_ammo_panel_appended=true native_selected_shell_appended=true native_initial_reload_appended=true frequency=10 game_ticks=1000 period=3 avatar_entity_id=152043522 vehicle_entity_id=152043523 space_id=1 relative_origin=true bind_applied=true roster_ready=true token_verified=true domain_ready=true generic_control=false terrain=false",self.id));
                                events.push(format!("BATTLE_NATIVE_AMMO_PANEL_CANDIDATE session={} generation={generation} route=ordinary_map_drive reliable_sequence={sequence} {}",self.id,crate::battle091::native_ammo::panel_event_fields(panel)?));
                                events.push(format!("BATTLE_NATIVE_SHELL_SELECTED session={} generation={generation} route=ordinary_map_drive native_method=0x40 setting=CURRENT_SHELLS compact_descr=2570 selected_shell_body_bytes=7 native_static=true native_delivery_candidate=true native_receipt=NOT_RUN",self.id));
                                events.push(format!("BATTLE_NATIVE_INITIAL_RELOAD session={} generation={generation} route=ordinary_map_drive native_method=0x46 vehicle_id=152043523 time_left=0.0 base_time=2.5 body_bytes=14 native_static=true native_delivery_candidate=true native_receipt=NOT_RUN",self.id));
                                for method in ["vehicle_changeSetting","autoAim"] {
                                    events.push(format!("AVATAR_METHOD_UNSUPPORTED session={} sequence={n} method={method} exact_arguments=true parsed_rpc=true domain_applied=false gameplay=false transport_acknowledged=true",self.id));
                                }
                            } else if self.arena_movement {
                                let (create_sequence,sequence)=self.queue_arena_movement(now)?;
                                events.push(format!("ARENA_MOVEMENT_READY session={} sequence={n} checkpoint=avatar_movement application_bytes=33 methods=4 create_sequence={create_sequence} create_acked=true reliable_sequence={sequence} body_bytes=51 frequency=10 game_ticks=1000 start_game_seconds=100 end_game_seconds=160 period_seconds=60 period=3 roster_ready=true token_verified=true domain_ready=true physics=false",self.id));
                                for method in ["bindToVehicle","vehicle_changeSetting","autoAim"] {
                                    events.push(format!("AVATAR_METHOD_UNSUPPORTED session={} sequence={n} method={method} exact_arguments=true parsed_rpc=true domain_applied=false gameplay=false transport_acknowledged=true",self.id));
                                }
                            } else {
                                let (create_sequence,sequence)=self.queue_arena_preparation(now)?;
                                events.push(self.arena_battle_preparation.as_ref().ok_or_else(invalid)?.event(self.id));
                                let panel=self.arena_battle_preparation.as_ref().ok_or_else(invalid)?.loadout();
                                events.push(format!("BATTLE_NATIVE_AMMO_PANEL_CANDIDATE session={} {}",self.id,crate::battle091::native_ammo::panel_event_fields(panel)?));
                                events.push(format!("BATTLE_NATIVE_SHELL_SELECTED session={} native_method=0x40 setting=CURRENT_SHELLS compact_descr=2570 selected_shell_body_bytes=7 native_static=true native_delivery_candidate=true native_receipt=NOT_RUN",self.id));
                                events.push(format!("BATTLE_NATIVE_INITIAL_RELOAD session={} native_method=0x46 vehicle_id=152043523 time_left=0.0 base_time=2.5 body_bytes=14 native_static=true native_delivery_candidate=true native_receipt=NOT_RUN",self.id));
                                events.push(format!("ARENA_READY_ACCEPTED session={} sequence={n} checkpoint=avatar_ready application_bytes=33 methods=4 ready_count=1 create_sequence={create_sequence} create_acked=true token_verified=true domain_ready=true unsupported_control_methods=3",self.id));
                                for method in ["bindToVehicle","vehicle_changeSetting","autoAim"] {
                                    events.push(format!("AVATAR_METHOD_UNSUPPORTED session={} sequence={n} method={method} exact_arguments=true parsed_rpc=true domain_applied=false gameplay=false transport_acknowledged=true",self.id));
                                }
                                events.push(format!("ARENA_PREPARATION_QUEUED session={} request_sequence={n} reliable_sequence={sequence} body_bytes=105 native_ammo_panel_appended=true native_selected_shell_appended=true native_initial_reload_appended=true frequency=10 game_ticks=1000 start_game_seconds=100 end_game_seconds=130 preparation_seconds=30 period=2 roster_ready=true clock_source=own_monotonic_lab battle_started=false",self.id));
                            }
                        } else if self.map_drive && f.body.len()>5 {
                            // No raw unknown envelope becomes parsed success in
                            // this mode. The full fixed/variable bundle is bounded.
                            self.receive_map_drive(&f.body[5..],n,now,events)?;
                        } else if self.arena_movement && matches!(f.body.get(5),Some(0x8a|0x8e|0x8f|0x0f)) {
                            // Only these original method families are parsed. A
                            // malformed complete envelope fails atomically, including
                            // recognized move prefixes followed by invalid methods.
                            self.receive_movement(&f.body[5..],n,now,events)?;
                        } else if self.arena_base {
                            if self.receive_battle_fire(&f.body[5..],n,now,events)?.is_some() {
                                // Exact native fire/replenish BaseMethods have
                                // been applied (or explicitly observed as
                                // unsupported); transport sequence handling
                                // below remains unchanged.
                            } else {
                            // Experimental observation sink, NOT gameplay. An
                            // authenticated unknown envelope is rejected at the
                            // application boundary, never parsed as Account.
                            // Consume its validated reliable transport sequence
                            // so heartbeat/logout can still arrive afterwards.
                            if f.body.len()>517 {return Err(invalid());}
                            if f.body.len()>5 {
                                if self.avatar_unsupported_envelopes>=32 {return Err(invalid());}
                                self.avatar_unsupported_envelopes+=1;
                                events.push(format!("AVATAR_RPC_UNSUPPORTED session={} sequence={n} payload_bytes={} envelope_count={} parsed_rpc=false domain_applied=false transport_acknowledged=true",self.id,f.body.len()-5,self.avatar_unsupported_envelopes));
                                if self.arena_vehicle==ArenaVehicleStage::Queued {
                                    // Observe only two exact automatic forms. No gameplay
                                    // response/state is fabricated; the bounded unsupported
                                    // application policy above remains in force.
                                    if let Some(methods)=crate::arena_vehicle091::automatic_lifecycle_calls(&f.body[5..]) {
                                        for method in methods {events.push(format!("AVATAR_LIFECYCLE_OBSERVED session={} sequence={n} method={method} exact_arguments=true token_verified=true domain_applied=false gameplay=false transport_acknowledged=true",self.id));}
                                    }
                                }
                            }
                            }
                        } else {
                            self.receive_account(&f.body[5..],events)?;
                        }
                    }
                }
                self.received.push_back((n,logical.to_vec()));self.rx+=1;
                if self.identity.is_some() && self.received.len()>64 {self.received.pop_front();}
            }
        } else if !self.active || !f.body.is_empty() || !f.piggybacks.is_empty() {return Err(invalid());}
        self.drain_outbox()?;
        self.last_rx=now;Ok(close)
    }
}
fn invalid()->io::Error {io::Error::new(io::ErrorKind::InvalidData,"unsupported session input")}
fn empty_envelope(body:&[u8],token:u32)->io::Result<&[u8]> {
    if body.len()==5 && body[0]==1 {
        if body[1..]!=token.to_le_bytes() {return Err(invalid());}
        Ok(&[])
    } else {Ok(body)}
}
fn send_wire(socket:&UdpSocket,peer:SocketAddr,wire:&[u8],channel:Channel,capture:&mut Option<Recorder>)->io::Result<()> {
    let sent=socket.send_to(wire,peer)?;
    if sent!=wire.len() {return Err(io::Error::new(io::ErrorKind::WriteZero,"partial UDP send"));}
    if let Some(recorder)=capture {recorder.observe(channel,false,peer,wire);}Ok(())
}
fn send(socket:&UdpSocket,peer:SocketAddr,clear:&[u8],key:&[u8;16],capture:&mut Option<Recorder>)->io::Result<()> {
    send_wire(socket,peer,&base::encrypt(clear,key)?,Channel::Base,capture)
}

pub fn serve(key_path:&str,digest_path:&str)->Result<(),Box<dyn std::error::Error>> {
    serve_inner(key_path,digest_path,false,false,None,None,None,None)
}
pub fn serve_account(key_path:&str,digest_path:&str)->Result<(),Box<dyn std::error::Error>> {
    serve_inner(key_path,digest_path,true,false,None,None,None,None)
}
pub fn serve_account_ready(key_path:&str,digest_path:&str)->Result<(),Box<dyn std::error::Error>> {
    serve_inner(key_path,digest_path,true,true,None,None,None,None)
}
pub fn serve_hangar(key_path:&str,digest_path:&str,fixture_path:&str)->Result<(),Box<dyn std::error::Error>> {
    let fixtures=crate::hangar091::Fixtures::load(Path::new(fixture_path))?;
    println!("HANGAR_FIXTURES sizes={:?} account_id=900001 source=own_test_lab",fixtures.sizes());
    serve_inner(key_path,digest_path,true,true,Some(Arc::new(fixtures)),None,None,None)
}
pub fn serve_interactive(key_path:&str,digest_path:&str,config_path:&str,capture_path:Option<&str>)->Result<(),Box<dyn std::error::Error>> {
    let config=crate::identity091::Config::load(config_path)?;
    let capture=capture_path.map(|path|Recorder::open(path,&config.local_root)).transpose()?;
    serve_inner(key_path,digest_path,true,true,None,Some(Arc::new(config)),capture,None)
}
pub fn serve_arena_base_probe(key_path:&str,digest_path:&str,config_path:&str,capture_path:&str,
                             trigger_path:&str)->Result<(),Box<dyn std::error::Error>> {
    let config=crate::identity091::Config::load(config_path)?;
    let control=crate::arena_control091::ArenaControl::new(Path::new(trigger_path),&config.local_root)?;
    let capture=Recorder::open(capture_path,&config.local_root)?;
    serve_inner(key_path,digest_path,true,true,None,Some(Arc::new(config)),Some(capture),Some(control))
}
pub fn serve_arena_space_probe(key_path:&str,digest_path:&str,config_path:&str,capture_path:&str,
                              trigger_path:&str)->Result<(),Box<dyn std::error::Error>> {
    let config=crate::identity091::Config::load(config_path)?;
    let control=crate::arena_control091::ArenaControl::for_checkpoint(Path::new(trigger_path),&config.local_root,
        crate::arena_control091::Checkpoint::AvatarSpace)?;
    let capture=Recorder::open(capture_path,&config.local_root)?;
    serve_inner(key_path,digest_path,true,true,None,Some(Arc::new(config)),Some(capture),Some(control))
}
pub fn serve_arena_vehicle_probe(key_path:&str,digest_path:&str,config_path:&str,capture_path:&str,
                                trigger_path:&str)->Result<(),Box<dyn std::error::Error>> {
    let config=crate::identity091::Config::load(config_path)?;
    let control=crate::arena_control091::ArenaControl::for_checkpoint(Path::new(trigger_path),&config.local_root,
        crate::arena_control091::Checkpoint::AvatarVehicle)?;
    let capture=Recorder::open(capture_path,&config.local_root)?;
    serve_inner(key_path,digest_path,true,true,None,Some(Arc::new(config)),Some(capture),Some(control))
}
pub fn serve_arena_ready_probe(key_path:&str,digest_path:&str,config_path:&str,capture_path:&str,
                              trigger_path:&str)->Result<(),Box<dyn std::error::Error>> {
    let config=crate::identity091::Config::load(config_path)?;
    let control=crate::arena_control091::ArenaControl::for_checkpoint(Path::new(trigger_path),&config.local_root,
        crate::arena_control091::Checkpoint::AvatarReady)?;
    let capture=Recorder::open(capture_path,&config.local_root)?;
    serve_inner(key_path,digest_path,true,true,None,Some(Arc::new(config)),Some(capture),Some(control))
}
pub fn serve_arena_movement_probe(key_path:&str,digest_path:&str,config_path:&str,capture_path:&str,
                                 trigger_path:&str)->Result<(),Box<dyn std::error::Error>> {
    let config=crate::identity091::Config::load(config_path)?;
    let control=crate::arena_control091::ArenaControl::for_checkpoint(Path::new(trigger_path),&config.local_root,
        crate::arena_control091::Checkpoint::AvatarMovement)?;
    let capture=Recorder::open(capture_path,&config.local_root)?;
    serve_inner(key_path,digest_path,true,true,None,Some(Arc::new(config)),Some(capture),Some(control))
}
pub fn serve_map_drive_probe(key_path:&str,digest_path:&str,config_path:&str,capture_path:&str,
                            trigger_path:&str)->Result<(),Box<dyn std::error::Error>> {
    let config=crate::identity091::Config::load(config_path)?;
    let control=crate::arena_control091::ArenaControl::for_checkpoint(Path::new(trigger_path),&config.local_root,
        crate::arena_control091::Checkpoint::AvatarDrive)?;
    let capture=Recorder::open(capture_path,&config.local_root)?;
    serve_inner(key_path,digest_path,true,true,None,Some(Arc::new(config)),Some(capture),Some(control))
}
struct Authenticated {identity:Arc<crate::identity091::Profile>,fixtures:Arc<crate::hangar091::Fixtures>,
    drive_account_policy:Option<Arc<crate::map_drive_service091::AccountPolicy>>}
impl Authenticated {
    fn new(identity:crate::identity091::Profile,fixtures:crate::hangar091::Fixtures,ordinary:bool)->io::Result<Self> {
        // Remains inside the existing bounded auth worker. A bad primary policy
        // reaches AUTH_REJECT before Session creation or any native state bytes.
        let policy=crate::map_drive_service091::AccountPolicy::for_mode(ordinary,&identity,&fixtures)?;
        Ok(Self {identity:Arc::new(identity),fixtures:Arc::new(fixtures),drive_account_policy:policy.map(Arc::new)})
    }
}
struct AuthJob {
    request:u32,attempt:LoginAttempt,ciphertext_tag:[u8;32],
    receiver:mpsc::Receiver<io::Result<Option<Authenticated>>>,
}
impl AuthJob {
    fn pending_duplicate(&self,candidate:&LoginAttempt,ciphertext_tag:&[u8;32])->bool {
        self.attempt.same_attempt(candidate) && self.ciphertext_tag==*ciphertext_tag
    }
}
fn encrypted_attempt_tag(packet:&[u8])->io::Result<[u8;32]> {
    // Hash only the bounded RSA ciphertext, never the password/plaintext. This
    // is an ephemeral equality tag, not authentication and never a log field.
    // Outer request ID is intentionally excluded from duplicate identity.
    Ok(Sha256::digest(login::envelope_interactive(packet)?.ciphertext).into())
}
fn start_auth(config:Arc<crate::identity091::Config>,request:u32,peer:SocketAddr,fields:&login::Fields,
              ciphertext_tag:[u8;32],ordinary:bool)->io::Result<AuthJob> {
    let (email,password)=crate::identity091::credentials(&fields.username,&fields.password)?;
    let (sender,receiver)=mpsc::sync_channel(1);
    thread::Builder::new().name("local-identity".to_owned()).spawn(move || {
        let outcome=config.authenticate(&email,&password).and_then(|identity|identity.map(|identity| {
            let fixtures=crate::hangar091::Fixtures::load_interactive(&identity.fixture_dir)?;
            Authenticated::new(identity,fixtures,ordinary)
        }).transpose());
        let _=sender.send(outcome); // A stopped gateway has no recipient.
    })?;
    Ok(AuthJob {request,attempt:LoginAttempt::new(fields.session_key,fields.nonce,peer),ciphertext_tag,receiver})
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
enum DrivePollInvariant { ArenaState, WorkerGeneration, WorkerReplyState, MissingClock,
    ClockRegression, ClockDeadline, TickReuse, TickGap, EntryDeadline, RequestWindow }
fn drive_poll_error(reason:DrivePollInvariant)->io::Error {
    io::Error::new(io::ErrorKind::InvalidData,format!("map-drive publication invariant={reason:?}"))
}
fn drive_publication_tick(d:&crate::map_drive_world091::Arena,now:Instant)->io::Result<u32> {
    let created=d.created.ok_or_else(||drive_poll_error(DrivePollInvariant::MissingClock))?;
    let elapsed=now.checked_duration_since(created).ok_or_else(||drive_poll_error(DrivePollInvariant::ClockRegression))?;
    if elapsed>=Duration::from_secs(crate::map_drive_world091::WORLD_SECONDS as u64){return Err(drive_poll_error(DrivePollInvariant::ClockDeadline));}
    let tick=1000+(elapsed.as_millis()/100) as u32;
    if tick<=d.native_tick{return Err(drive_poll_error(DrivePollInvariant::TickReuse));}
    if tick-d.native_tick>50{return Err(drive_poll_error(DrivePollInvariant::TickGap));}
    Ok(tick)
}
/// External worker side effects occur ONLY here, after receive's complete
/// clone/commit, and are revoked as soon as the typed arena generation retires.
fn poll_drive(s:&mut Session,slot:&mut Option<(u32,crate::map_drive_worker091::Worker)>,pool:Arc<crate::map_drive_worker091::Pool>,now:Instant)->io::Result<()> {
    use crate::map_drive_world091::{self as world,Phase};
    use crate::map_drive_worker091 as ipc;
    let d=s.drive.as_ref().ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?;
    let needs_worker=matches!(d.phase,Phase::Queued|Phase::Enable|Phase::EntityRequest|Phase::Ready|Phase::Driving);
    if slot.as_ref().is_some_and(|(session,w)|!needs_worker || *session!=s.id || w.generation!=d.generation){
        let (_,w)=slot.take().ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?;println!("MAP_DRIVE_WORKER_RETIRED session={} generation={} authority_revoked=true",s.id,w.generation);drop(w);
    }
    if !needs_worker{return Ok(());}
    if slot.is_none(){
        if d.phase!=Phase::Queued{return Err(drive_poll_error(DrivePollInvariant::ArenaState));}
        // Random choice is server-owned and happens after authenticated queue
        // commit, never from a client map index or speculative packet parse.
        let index=(OsRng.next_u32()&1) as usize;let map=pool.maps.get(index).ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?.clone();
        let worker=ipc::Worker::launch(pool.clone(),map.clone(),d.generation,now)?;
        println!("MAP_DRIVE_WORKER_START session={} generation={} map={} arena_type_id={} config_sha256={} pool_sha256={} physics=test_lab",s.id,d.generation,map.asset,map.arena_type_id,map.config_sha256,pool.sha256);
        *slot=Some((s.id,worker));s.drive.as_mut().ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?.map=Some(map);
    }
    let (_,worker)=slot.as_mut().ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?;
    if let Some(state)=worker.poll(now)?{
        let d=s.drive.as_ref().ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?;
        if d.generation!=worker.generation{return Err(drive_poll_error(DrivePollInvariant::WorkerGeneration));}
        if state.seq==0{
            if d.phase!=Phase::Queued || d.pose.is_some(){return Err(drive_poll_error(DrivePollInvariant::WorkerReplyState));}
            println!("MAP_DRIVE_WORKER_READY session={} generation={} process_id={} map={} worker_tick={} position={:?} direction={:?} contacts={} wheel_contact_masks={:?}",s.id,d.generation,worker.process_id().ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?,worker.map.asset,state.tick,state.pose.position,state.pose.direction,state.pose.contacts,state.pose.wheel_contact_masks);
            s.drive.as_mut().ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?.pose=Some(state.pose);
        }else{
            if d.phase!=Phase::Driving || !d.pending || state.seq!=d.worker_seq+1{return Err(drive_poll_error(DrivePollInvariant::WorkerReplyState));}
            // Dispatch waits for a new own native bucket; retain a typed final
            // invariant guard here. Worker ticks remain independent fixed60Hz.
            let tick=drive_publication_tick(d,now)?;
            let body=world::publication_entity_only(tick,&state.pose)?;let seq=s.tx.enqueue_body_tracked(&body)?;
            let d=s.drive.as_mut().ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?;
            d.pose=Some(state.pose.clone());d.worker_seq=state.seq;d.native_tick=tick;d.pending=false;
            println!("MAP_DRIVE_STATE session={} generation={} worker_seq={} worker_tick={} native_tick={tick} reliable_sequence={seq} body_bytes=31 own_callback=false publication_policy={} position={:?} direction={:?} speed={} rspeed={} contacts={} wheel_contact_masks={:?} linear_velocity={:?} angular_velocity={:?} authority=worker client_position_used=false",s.id,d.generation,state.seq,state.tick,world::PUBLICATION_POLICY,state.pose.position,state.pose.direction,state.pose.speed,state.pose.rspeed,state.pose.contacts,state.pose.wheel_contact_masks,state.pose.linear_velocity,state.pose.angular_velocity);
        }
    }
    let d=s.drive.as_ref().ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?;
    if d.phase==Phase::Queued && d.pose.is_some() && s.ready_for_arena_base(){
        let seed=s.arena_vehicle_seed.as_ref().ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?;
        seed.validate_session(s.identity.as_ref().ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?,s.hangar.as_ref().ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?.state_sha256())?;
        let unique=((s.id as u64)<<32)|d.generation as u64;
        let body=world::reset_avatar(seed,d.map.as_ref().ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?,d.generation,unique)?;
        let seq=s.tx.enqueue_body_tracked(&body)?;let d=s.drive.as_mut().ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?;
        d.phase=Phase::Enable;s.arena_base=true;
        println!("MAP_DRIVE_AVATAR_CREATED session={} generation={} arena_unique_id={unique} reliable_sequence={seq} type_id=1 account_preserved=true",s.id,d.generation);
    }
    let d=s.drive.as_ref().ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?;
    if matches!(d.phase,Phase::Enable|Phase::EntityRequest|Phase::Ready) && now.duration_since(d.requested_at)>Duration::from_secs(180){return Err(drive_poll_error(DrivePollInvariant::EntryDeadline));}
    if d.due(now)?{
        if s.tx.len()>=8 || !s.outbox.is_empty() || worker.pending(){return Err(drive_poll_error(DrivePollInvariant::RequestWindow));}
        let seq=worker.advance(d.input,now)?;
        println!("MAP_DRIVE_WORKER_INPUT session={} generation={} seq={seq} ticks=6 throttle={} steer={} brake={}",s.id,d.generation,d.input.throttle,d.input.steer,d.input.brake);
        let d=s.drive.as_mut().ok_or_else(||drive_poll_error(DrivePollInvariant::ArenaState))?;d.pending=true;d.last_request=Some(now);
    }
    Ok(())
}
fn serve_inner(key_path:&str,digest_path:&str,account_probe:bool,account_ready:bool,hangar:Option<Arc<crate::hangar091::Fixtures>>,
               interactive:Option<Arc<crate::identity091::Config>>,capture:Option<Recorder>,
               arena_control:Option<crate::arena_control091::ArenaControl>)->Result<(),Box<dyn std::error::Error>> {
    serve_inner_drive(key_path,digest_path,account_probe,account_ready,hangar,interactive,capture,arena_control,None)
}
pub fn serve_map_drive(key_path:&str,digest_path:&str,config_path:&str,pool_path:&str,capture_path:Option<&str>,
                       capture_profile:crate::capture091::Profile)->Result<(),Box<dyn std::error::Error>> {
    if capture_path.is_none() && capture_profile!=crate::capture091::Profile::Ordinary{return Err(invalid().into());}
    let config=crate::identity091::Config::load(config_path)?;
    let pool=crate::map_drive_worker091::Pool::load(&config.local_root,Path::new(pool_path))?;
    let capture=capture_path.map(|path|Recorder::open_profile(path,&config.local_root,capture_profile)).transpose()?;
    serve_inner_drive(key_path,digest_path,true,true,None,Some(Arc::new(config)),capture,None,Some(Arc::new(pool)))
}
fn serve_inner_drive(key_path:&str,digest_path:&str,account_probe:bool,account_ready:bool,hangar:Option<Arc<crate::hangar091::Fixtures>>,
               interactive:Option<Arc<crate::identity091::Config>>,mut capture:Option<Recorder>,
               mut arena_control:Option<crate::arena_control091::ArenaControl>,
               drive_pool:Option<Arc<crate::map_drive_worker091::Pool>>)->Result<(),Box<dyn std::error::Error>> {
    let private=login::load_key(key_path)?;
    if fs::metadata(digest_path)?.len()!=16 {return Err(invalid().into());}
    let digest:[u8;16]=fs::read(digest_path)?.try_into().map_err(|_|invalid())?;
    let login_socket=UdpSocket::bind(interactive.as_ref().map(|c|SocketAddr::V4(c.login_bind)).unwrap_or("127.0.0.1:20015".parse()?))?;
    let base_socket=UdpSocket::bind(interactive.as_ref().map(|c|SocketAddr::V4(c.base_bind)).unwrap_or("127.0.0.1:20017".parse()?))?;
    login_socket.set_nonblocking(true)?;base_socket.set_nonblocking(true)?;
    let started=Instant::now();let mut next_id=1u32;let mut session:Option<Session>=None;
    let mut closed:VecDeque<([u8;16],Instant)>=VecDeque::new();let mut count=0u64;
    let mut retirement=RetirementWindow::default();
    let mut auth:Option<AuthJob>=None;let mut last_auth:Option<Instant>=None;
    let mut drive_worker:Option<(u32,crate::map_drive_worker091::Worker)>=None;
    let mut login_fragments=login::LoginFragments::default();
    let mut rate_started=started;let mut rate_count=0u32;
    if let Some(config)=&interactive {
        if let Some(pool)=drive_pool.as_ref() {
            println!("BOUND {} base_backend={} profile=legacy091-map-drive scope=own_primary_ms1_test_lab session_seconds={} max_sequence={} duplicate_history=64 pool_sha256={} maps=2 auto_quit=false",config.login_bind,config.base_bind,config.session_duration.as_secs(),transport091::INTERACTIVE_MAX_SEQUENCE,pool.sha256);
        } else if let Some(control)=arena_control.as_ref() {
            println!("BOUND {} base_backend={} profile={} scope={} session_seconds={} max_sequence={} duplicate_history=64",
                config.login_bind,config.base_bind,control.checkpoint().cli(),control.checkpoint().scope(),config.session_duration.as_secs(),transport091::INTERACTIVE_MAX_SEQUENCE);
        } else {
            println!("BOUND {} base_backend={} profile=legacy091-interactive scope=unified_web_users session_seconds={} max_sequence={} duplicate_history=64",
                config.login_bind,config.base_bind,config.session_duration.as_secs(),transport091::INTERACTIVE_MAX_SEQUENCE);
        }
    } else {println!("BOUND 127.0.0.1:20015 base_backend=127.0.0.1:20017 profile=legacy091-gateway scope=single_lab_account");}
    if account_probe {println!("ACCOUNT_PROBE enabled=true scope={}",if account_ready {"minimal_initial_sync"} else {"creation_only"});}
    if account_ready {println!("ACCOUNT_BOOTSTRAP_EXPERIMENT enabled=true file_endpoints=0 voice_service=false");}
    while interactive.is_some() || (started.elapsed()<Duration::from_secs(900) && count<8192) {
        let now=Instant::now();
        if now.duration_since(rate_started)>=Duration::from_secs(1) {rate_started=now;rate_count=0;}
        while closed.front().is_some_and(|(_,t)|now.duration_since(*t)>Duration::from_secs(120)) {closed.pop_front();}
        let mut close_reason=None;
        let auth_result=auth.as_ref().and_then(|job|match job.receiver.try_recv() {
            Ok(value)=>Some(value),Err(mpsc::TryRecvError::Empty)=>None,
            Err(mpsc::TryRecvError::Disconnected)=>Some(Err(io::Error::new(io::ErrorKind::Other,"identity worker stopped"))),
        });
        if let Some(result)=auth_result {
            let job=auth.take().ok_or_else(invalid)?;
            match result {
                Ok(Some(accepted))=>{
                    // A session may have closed while the bounded KDF worker
                    // ran. Recheck retirement and reserve capacity before any
                    // allocation; a successful password never bypasses either.
                    let denied=retirement.check_login(&job.attempt,now).err();
                    let busy=session.as_ref().is_some_and(|s|!s.verified_duplicate(&job.attempt,&accepted.identity.account_id));
                    if denied.is_some() || busy {
                        send_wire(&login_socket,job.attempt.login_peer,&login::rejection(job.request,73),Channel::Login,&mut capture)?;
                        if let Some(reason)=denied {println!("AUTH_REJECT code=73 allocated=0 reason=retirement_post_auth policy={reason:?}");}
                        else {println!("AUTH_REJECT code=73 allocated=0 reason=verified_session_busy");}
                    } else {
                        if session.is_none() {
                            let mut created=Session::new(next_id,job.attempt.key,job.attempt.login_peer,now);
                            created.login_attempt=Some(job.attempt);
                            created.account_probe=true;created.account_ready=true;created.tx=Window::interactive();
                            println!("SESSION_PENDING id={next_id} account={} native_database_id={} name={} allocated=1 source=website_users fixture_sizes={:?}",
                                accepted.identity.account_id,accepted.identity.database_id,accepted.identity.name,accepted.fixtures.sizes());
                            created.identity=Some(accepted.identity);created.hangar=Some(accepted.fixtures);
                            created.drive_account_policy=accepted.drive_account_policy;
                            if drive_pool.is_some(){created.drive=Some(crate::map_drive_world091::Arena::new(now));}
                            if let Some(policy)=&created.drive_account_policy {println!("{}",policy.binding_event(next_id));}
                            session=Some(created);next_id=next_id.checked_add(1).ok_or_else(invalid)?;
                        } else {println!("LOGIN_DUPLICATE session={}",session.as_ref().ok_or_else(invalid)?.id);}
                        let s=session.as_ref().ok_or_else(invalid)?;
                        let config=interactive.as_ref().ok_or_else(invalid)?;
                        send_wire(&login_socket,job.attempt.login_peer,&redirect091::reply_to(job.request,&s.key,s.handoff,config.base_bind)?,Channel::Login,&mut capture)?;
                        println!("LEGACY091_REDIRECT_SENT request_id={} session={}",job.request,s.id);
                    }
                },
                Ok(None)=>{send_wire(&login_socket,job.attempt.login_peer,&login::rejection(job.request,67),Channel::Login,&mut capture)?;println!("AUTH_REJECT code=67 allocated=0");},
                Err(error)=>{send_wire(&login_socket,job.attempt.login_peer,&login::rejection(job.request,73),Channel::Login,&mut capture)?;println!("AUTH_REJECT code=73 allocated=0 reason=identity_unavailable kind={:?} error={error}",error.kind());},
            }
        }
        for (is_login,socket) in [(true,&login_socket),(false,&base_socket)] {
            let mut data=[0u8;65536];
            let (length,peer)=match socket.recv_from(&mut data) {
                Ok(x)=>x,
                Err(e) if e.kind()==io::ErrorKind::WouldBlock=>continue,
                Err(e) if e.raw_os_error()==Some(10054)=>{println!("UDP_RESET code=10054");continue;},
                Err(e)=>return Err(e.into()),
            };
            if peer.ip()==Ipv4Addr::LOCALHOST {
                if let Some(recorder)=&mut capture {recorder.observe(if is_login {Channel::Login} else {Channel::Base},true,peer,&data[..length]);}
            }
            count+=1;rate_count+=1;
            let maximum=if is_login && interactive.is_some() {login::MAX_INTERACTIVE_DATAGRAM} else {1024};
            if rate_count>128 || length>maximum || peer.ip()!=Ipv4Addr::LOCALHOST {println!("REJECT reason=address_size_rate");continue;}
            let packet=&data[..length];
            if is_login {
                let assembled;
                let packet=if interactive.is_some() {
                    match login_fragments.push(peer,now,packet) {
                        Ok(Some(value))=>{
                            if packet.starts_with(&[0x61,0]) || packet.starts_with(&[0x60,0]) {
                                println!("LOGIN_FRAGMENT_REASSEMBLED request_id={} fragments=2 bytes={}",login::envelope_interactive(&value)?.request_id,value.len());
                            }
                            assembled=value;assembled.as_slice()
                        },
                        Ok(None)=>continue,
                        Err(_)=>{println!("REJECT reason=login_fragment_or_envelope");continue;},
                    }
                } else {packet};
                let decoded=if interactive.is_some() {login::decode_interactive(packet,&private)} else {login::decode_unauthed(packet,&private)};
                let (request,fields)=match decoded {
                    Ok(x)=>x,Err(_)=>{
                        if interactive.is_some() {
                            if let Ok(envelope)=login::envelope_interactive(packet) {send_wire(socket,peer,&login::rejection(envelope.request_id,73),Channel::Login,&mut capture)?;}
                        }
                        println!("REJECT reason=login_framing");continue;
                    }
                };
                if let Some(config)=&interactive {
                    if fields.digest!=digest {send_wire(socket,peer,&login::rejection(request,69),Channel::Login,&mut capture)?;println!("AUTH_REJECT code=69 allocated=0");continue;}
                    let candidate=LoginAttempt::new(fields.session_key,fields.nonce,peer);
                    let ciphertext_tag=encrypted_attempt_tag(packet)?;
                    if let Some(pending)=&auth {
                        if pending.pending_duplicate(&candidate,&ciphertext_tag) {println!("AUTH_PENDING_DUPLICATE request_id={request}");}
                        else {send_wire(socket,peer,&login::rejection(request,73),Channel::Login,&mut capture)?;println!("AUTH_REJECT code=73 allocated=0 reason=identity_busy");}
                        continue;
                    }
                    if session.as_ref().is_some_and(|s|!s.same_login_attempt(&candidate)) {
                        send_wire(socket,peer,&login::rejection(request,73),Channel::Login,&mut capture)?;
                        println!("AUTH_REJECT code=73 allocated=0 reason=session_busy");continue;
                    }
                    if let Err(reason)=retirement.check_login(&candidate,now) {
                        send_wire(socket,peer,&login::rejection(request,73),Channel::Login,&mut capture)?;
                        println!("AUTH_REJECT code=73 allocated=0 reason=retirement_pre_auth policy={reason:?}");continue;
                    }
                    if last_auth.is_some_and(|last|now.duration_since(last)<Duration::from_millis(250)) {
                        send_wire(socket,peer,&login::rejection(request,73),Channel::Login,&mut capture)?;println!("AUTH_REJECT code=73 allocated=0 reason=auth_rate");continue;
                    }
                    // Every new admissible attempt, including key reuse, needs
                    // fresh website credentials. No retired row supplies auth.
                    // One bounded worker, no channel-loop wait during its KDF.
                    match start_auth(config.clone(),request,peer,&fields,ciphertext_tag,drive_pool.is_some()) {
                        Ok(job)=>{auth=Some(job);last_auth=Some(now);println!("AUTH_PENDING request_id={request} allocated=0");},
                        Err(_)=>{send_wire(socket,peer,&login::rejection(request,73),Channel::Login,&mut capture)?;println!("AUTH_REJECT code=73 allocated=0 reason=unsupported_native_credentials");},
                    }
                    continue;
                }
                if !fields.lab_credentials_valid || fields.digest!=digest {
                    let code=if !fields.lab_credentials_valid {67} else {69};
                    send_wire(socket,peer,&login::rejection(request,code),Channel::Login,&mut capture)?;
                    println!("AUTH_REJECT code={code} allocated=0");continue;
                }
                if closed.iter().any(|(key,_)|*key==fields.session_key) {println!("REJECT reason=retired_login_key");continue;}
                if let Some(s)=session.as_ref() {
                    if s.login_peer!=peer || s.key!=fields.session_key {
                        send_wire(socket,peer,&login::rejection(request,73),Channel::Login,&mut capture)?;
                        println!("REJECT reason=account_busy");continue;
                    }
                    println!("LOGIN_DUPLICATE session={}",s.id);
                } else {
                    let mut created=Session::new(next_id,fields.session_key,peer,now);
                    created.account_probe=account_probe;created.account_ready=account_ready;created.hangar=hangar.clone();session=Some(created);
                    println!("SESSION_PENDING id={next_id} account=p02-local-test allocated=1");next_id+=1;
                }
                let s=session.as_ref().ok_or_else(invalid)?;
                login::print_fields(request,&fields);
                send_wire(socket,peer,&redirect091::reply(request,&s.key,s.handoff)?,Channel::Login,&mut capture)?;
                println!("LEGACY091_REDIRECT_SENT request_id={request} session={}",s.id);
            } else if let Some(s)=session.as_mut() {
                if let Err(reason)=s.guard_base_peer(&mut retirement,peer,now) {
                    println!("REJECT reason=retired_base_peer policy={reason:?}");continue;
                }
                if s.base_peer.is_some_and(|p|p!=peer) {println!("REJECT reason=other_base_peer");continue;}
                if length==21 {
                    let (request,attempt)=match base::base_request(packet,s.handoff) {Ok(x)=>x,Err(_)=>{println!("REJECT reason=base_request");continue;}};
                    s.base_peer=Some(peer);send(socket,peer,&base::base_reply(request,s.token),&s.key,&mut capture)?;
                    println!("BASEAPP_REPLY_SENT request_id={request} attempt={attempt} session={}",s.id);
                } else if s.base_peer.is_some() {
                    let frame=base::decrypt(packet,&s.key).and_then(|b|if s.identity.is_some() {transport091::parse_interactive(&b)} else {transport091::parse(&b)});
                    let frame=match frame {Ok(f)=>f,Err(_)=>{println!("REJECT reason=channel_framing");continue;}};
                    match s.receive(&frame,now) {
                        Ok(close)=>{
                            if frame.flags&0x10!=0 {send(socket,peer,&transport091::ack(s.rx),&s.key,&mut capture)?;s.last_keepalive=now;}
                            if close {close_reason=Some("client_disconnect");}
                        },
                        Err(error)=>{
                            println!("REJECT reason=channel_state");
                            if s.identity.is_some() {
                                println!("INTERACTIVE_REJECT flags={} sequence={:?} body_bytes={} error={}",frame.flags,frame.sequence,frame.body.len(),error);
                            } else if s.hangar.is_some() {
                                println!("HANGAR_REJECT flags={} sequence={:?} body={} error={}",frame.flags,frame.sequence,
                                    frame.body.iter().take(512).map(|b|format!("{b:02x}")).collect::<String>(),error);
                            }
                        },
                    }
                } else {println!("REJECT reason=before_base_handshake");}
            } else {println!("REJECT reason=no_session");}
        }
        if let Some(s)=session.as_mut() {
            if interactive.as_ref().is_some_and(|config|now.duration_since(s.created_at)>=config.session_duration) {close_reason=Some("session_deadline");}
            if now.duration_since(s.last_rx)>=Duration::from_secs(8) {close_reason=Some("idle_timeout");}
            if close_reason.is_none() {
                match s.preparation_expired(now) {
                    Ok(true)=>{
                        println!("ARENA_PREPARATION_EXPIRED session={} preparation_seconds=30 state=expired battle_started=false diagnostic_success=false",s.id);
                        close_reason=Some("arena_preparation_deadline");
                    },
                    Ok(false)=>{},Err(_)=>{
                        println!("ARENA_PREPARATION_FAILED session={} reason=clock_regression battle_started=false diagnostic_success=false",s.id);
                        close_reason=Some("arena_preparation_clock");
                    },
                }
            }
            if s.active && close_reason.is_none() {
                if let Some(pool)=drive_pool.as_ref(){
                    if let Err(error)=poll_drive(s,&mut drive_worker,pool.clone(),now){
                        println!("MAP_DRIVE_FAILED session={} error={error} data_changed=false",s.id);
                        drive_worker.take();let mut events=Vec::new();
                        let recovered=s.recover_drive_failure(&mut events);
                        for event in events{println!("{event}");}
                        if recovered.is_err(){close_reason=Some("map_drive_failure");}
                    }
                }
                if close_reason.is_none() {
                    let mut reload_events=Vec::new();
                    if let Err(_)=s.poll_battle_reload(now,&mut reload_events) {
                        println!("BATTLE_RELOAD_FAILED session={} reason=publication_or_state data_changed=false",s.id);
                        close_reason=Some("battle_reload_publication");
                    }
                    for event in reload_events {println!("{event}");}
                }
                if s.ready_for_arena_base() {
                    if let Some(control)=arena_control.as_mut() {
                        let identity=s.identity.as_ref().ok_or_else(invalid)?;
                        match control.poll(&identity.account_id,identity.database_id) {
                            Ok(true)=>match s.queue_arena_checkpoint(control.checkpoint()) {
                                Ok(())=>println!("ARENA_BASE_QUEUED session={} account={} database_id={} entity_id={} arena_unique_id=1 type_id=1 cell=false trigger_consumed_once=true channel_reused=true",s.id,s.identity.as_ref().ok_or_else(invalid)?.account_id,s.identity.as_ref().ok_or_else(invalid)?.database_id,crate::arena_control091::AVATAR_ENTITY_ID),
                                Err(_)=>println!("ARENA_BASE_TRIGGER_REJECT reason=queue_failed consumed_in_memory=true"),
                            },
                            Ok(false)=>{},
                            Err(reason)=>println!("ARENA_BASE_TRIGGER_REJECT reason={reason:?} consumed_in_memory=true"),
                        }
                    }
                }
                let mut movement_events=Vec::new();
                match s.poll_movement(now,&mut movement_events) {
                    Ok(Some(_))=>close_reason=Some("arena_movement_deadline"),
                    Ok(None)=>{},
                    Err(_)=>{
                        println!("ARENA_MOVEMENT_FAILED session={} reason=publication_or_state_bound diagnostic_success=false physics=false",s.id);
                        close_reason=Some("arena_movement_publication");
                    },
                }
                for event in movement_events {println!("{event}");}
                if close_reason.is_none() {
                if s.tx.len()==0 && now.duration_since(s.last_heartbeat)>=Duration::from_secs(2) {
                    if s.tx.enqueue().is_err() {close_reason=Some("sequence_budget");}
                    s.last_heartbeat=now;
                }
                if let Some(peer)=s.base_peer {
                    match s.tx.due(now,s.rx) {
                        Ok(Some((n,attempt,b)))=>{send(&base_socket,peer,&b,&s.key,&mut capture)?;println!("RELIABLE_SENT session={} sequence={n} attempt={attempt}",s.id);},
                        Ok(None)=>{},Err(_)=>close_reason=Some("retry_exhausted"),
                    }
                    if now.duration_since(s.last_keepalive)>=Duration::from_secs(1) {
                        send(&base_socket,peer,&transport091::ack(s.rx),&s.key,&mut capture)?;s.last_keepalive=now;
                    }
                }
                }
            }
        }
        if let Some(reason)=close_reason {
            drive_worker.take();
            // One live session plus the post-KDF capacity reservation leaves a
            // free retirement slot. Record it before dropping Session state;
            // an invariant failure exits closed, never evicts replay history.
            if interactive.is_some() {
                if let Some(s)=session.as_ref() {
                    retirement.retire(s.login_attempt.ok_or_else(invalid)?,s.base_peer,now)
                        .map_err(|_|io::Error::new(io::ErrorKind::InvalidData,"retirement reservation invariant"))?;
                }
            }
            if let Some(s)=session.take() {
                println!("SESSION_CLOSED id={} reason={reason} active=0 pending=0 retired_pending={}",s.id,s.tx.len());
                // Preserve the old conservative lab policy independently.
                if interactive.is_none() {
                    if closed.len()>=32 {closed.pop_front();} closed.push_back((s.key,now));
                }
            }
        }
        thread::sleep(Duration::from_millis(5));
    }
    println!("GATEWAY_STOP reason=lab_budget active={}",usize::from(session.is_some()));
    Ok(())
}

#[cfg(test)]
mod retirement_policy_tests {
    use super::*;

    fn peer(port: u16) -> SocketAddr {
        SocketAddr::from(([127, 0, 0, 1], port))
    }

    fn attempt(key: u8, nonce: u32, port: u16) -> LoginAttempt {
        LoginAttempt::new([key; 16], nonce, peer(port))
    }

    fn retired(now: Instant) -> RetirementWindow {
        let mut window = RetirementWindow::default();
        window.retire(attempt(7, 41, 40000), Some(peer(40001)), now).unwrap();
        window
    }

    #[test]
    fn repeated_key_new_nonce_and_new_peers_pass_policy_but_are_not_authentication() {
        let now = Instant::now();
        let mut window = retired(now);
        let next = attempt(7, 42, 40002);
        window.check_login(&next, now + Duration::from_secs(1)).unwrap();
        window.check_login(&next, now + Duration::from_secs(2)).unwrap();
        window.check_base_peer(&next, peer(40003), now + Duration::from_secs(2)).unwrap();
        // check_login has not allocated a session, authenticated a password or
        // removed the old record. Those operations are intentionally absent.
        assert_eq!(window.retained_count(), 1);
    }

    #[test]
    fn retired_inner_attempt_rejected_even_when_peer_or_outer_request_id_changes() {
        let now = Instant::now();
        let mut window = retired(now);
        for port in [40000, 40001, 40002] {
            // Outer request_id is outside RSA and is not an input to this API.
            for _outer_request_id in [0_u32, 7, u32::MAX] {
                assert_eq!(window.check_login(&attempt(7, 41, port), now), Err(Denial::RetiredAttempt));
            }
        }
        assert_eq!(window.retained_count(), 1);
    }

    #[test]
    fn new_nonce_cannot_reuse_either_retired_socket_for_login() {
        let now = Instant::now();
        let mut window = retired(now);
        for port in [40000, 40001] {
            assert_eq!(window.check_login(&attempt(7, 42, port), now), Err(Denial::RetiredPeerForKey));
        }
        assert_eq!(window.retained_count(), 1);
    }

    #[test]
    fn separate_new_login_peer_does_not_authorize_a_retired_base_peer() {
        let now = Instant::now();
        let mut window = retired(now);
        let next = attempt(7, 42, 40002);
        window.check_login(&next, now).unwrap();
        for port in [40000, 40001] {
            assert_eq!(window.check_base_peer(&next, peer(port), now), Err(Denial::RetiredPeerForKey));
        }
        window.check_base_peer(&next, peer(40002), now).unwrap();
        window.check_base_peer(&next, peer(40003), now).unwrap();
    }

    #[test]
    fn a_new_cipher_key_may_reuse_old_nonce_and_old_socket_addresses() {
        let now = Instant::now();
        let mut window = retired(now);
        let next = attempt(8, 41, 40000);
        window.check_login(&next, now).unwrap();
        window.check_base_peer(&next, peer(40001), now).unwrap();
    }

    #[test]
    fn pending_and_active_attempt_identity_includes_key_nonce_and_peer() {
        let original = attempt(7, 41, 40000);
        assert!(original.same_attempt(&attempt(7, 41, 40000)));
        assert!(!original.same_attempt(&attempt(8, 41, 40000)));
        assert!(!original.same_attempt(&attempt(7, 42, 40000)));
        assert!(!original.same_attempt(&attempt(7, 41, 40001)));
        // Verified UUID equality is an additional caller gate after auth.
    }

    fn login_packet(request:u32,ciphertext_byte:u8)->Vec<u8> {
        // Synthetic framing-only input; it is never RSA-decrypted or passed off
        // as a native capture or valid credentials.
        let mut packet=vec![0;273];packet[..5].copy_from_slice(&[1,0,0,4,1]);
        packet[5..9].copy_from_slice(&request.to_le_bytes());
        packet[11..15].copy_from_slice(&login::PROTOCOL.to_le_bytes());
        packet[15..271].fill(ciphertext_byte);packet[271]=2;packet
    }

    #[test]
    fn pending_duplicate_requires_identical_encrypted_attempt_not_only_key_or_nonce() {
        let original=attempt(7,41,40000);
        let tag=encrypted_attempt_tag(&login_packet(1,11)).unwrap();
        let (_,receiver)=mpsc::sync_channel(1);
        let pending=AuthJob {request:1,attempt:original,ciphertext_tag:tag,receiver};
        let changed_header=encrypted_attempt_tag(&login_packet(u32::MAX,11)).unwrap();
        assert!(pending.pending_duplicate(&original,&changed_header));
        // Same key/nonce/peer but changed encrypted credentials or padding must
        // not reuse the outstanding password result. No plaintext tag is kept.
        let changed_ciphertext=encrypted_attempt_tag(&login_packet(1,12)).unwrap();
        assert!(!pending.pending_duplicate(&original,&changed_ciphertext));
        for changed in [attempt(8,41,40000),attempt(7,42,40000),attempt(7,41,40001)] {
            assert!(!pending.pending_duplicate(&changed,&tag));
        }
    }

    #[test]
    fn encrypted_attempt_tag_keeps_the_bounded_login_envelope_contract() {
        let packet=login_packet(1,11);
        for size in [0,14,16,272] {assert!(encrypted_attempt_tag(&packet[..size]).is_err());}
        let mut changed=packet.clone();changed[11]^=1;assert!(encrypted_attempt_tag(&changed).is_err());
        changed=packet.clone();changed.push(0);assert!(encrypted_attempt_tag(&changed).is_err());
        assert!(encrypted_attempt_tag(&[0;2048]).is_err());
    }

    #[test]
    fn active_duplicate_also_requires_the_freshly_verified_website_identity() {
        let now=Instant::now();let original=attempt(7,41,40000);
        let mut session=Session::new(1,original.key,original.login_peer,now);
        assert!(!session.same_login_attempt(&original));
        session.login_attempt=Some(original);
        assert!(session.same_login_attempt(&original));
        assert!(!session.verified_duplicate(&original,"12345678-1234-4234-8234-123456789abc"));
        session.identity=Some(Arc::new(crate::identity091::Profile {
            account_id:"12345678-1234-4234-8234-123456789abc".to_owned(),database_id:42,
            name:"own_user".to_owned(),fixture_dir:std::path::PathBuf::new(),
        }));
        assert!(session.verified_duplicate(&original,"12345678-1234-4234-8234-123456789abc"));
        assert!(!session.verified_duplicate(&original,"12345678-1234-4234-8234-123456789abd"));
        for changed in [attempt(8,41,40000),attempt(7,42,40000),attempt(7,41,40001)] {
            assert!(!session.verified_duplicate(&changed,"12345678-1234-4234-8234-123456789abc"));
        }
        // This tests only the post-auth identity gate, not a mocked KDF success.
    }

    #[test]
    fn a_session_that_never_bound_base_still_retains_its_login_socket() {
        let now = Instant::now();
        let mut window = RetirementWindow::default();
        window.retire(attempt(7, 41, 40000), None, now).unwrap();
        let next = attempt(7, 42, 40002);
        assert_eq!(window.check_base_peer(&next, peer(40000), now), Err(Denial::RetiredPeerForKey));
        window.check_base_peer(&next, peer(40001), now).unwrap();
    }

    #[test]
    fn duplicate_login_and_base_socket_record_remains_one_entry() {
        let now = Instant::now();
        let mut window = RetirementWindow::default();
        window.retire(attempt(7, 41, 40000), Some(peer(40000)), now).unwrap();
        assert_eq!(window.retained_count(), 1);
        assert_eq!(window.check_login(&attempt(7, 42, 40000), now), Err(Denial::RetiredPeerForKey));
    }

    #[test]
    fn exactly_120_seconds_still_protected_then_expiry_is_explicit() {
        let now = Instant::now();
        let mut window = retired(now);
        let old = attempt(7, 41, 40000);
        assert_eq!(window.check_login(&old, now + RETIRED_TTL), Err(Denial::RetiredAttempt));
        let expired = now + RETIRED_TTL + Duration::from_nanos(1);
        window.check_login(&old, expired).unwrap();
        window.check_base_peer(&old, peer(40001), expired).unwrap();
        assert_eq!(window.retained_count(), 0);
        // Finite TTL is not permanent replay protection.
    }

    #[test]
    fn capacity_fails_closed_without_eviction_or_forgetting_old_attempts() {
        let now = Instant::now();
        let mut window = RetirementWindow::default();
        for n in 0..MAX_RETIRED {
            window.retire(attempt(n as u8, n as u32, 41000 + n as u16), None, now).unwrap();
        }
        let fresh = attempt(200, 1000, 42000);
        assert_eq!(window.check_login(&fresh, now), Err(Denial::CapacityFull));
        assert_eq!(window.retire(fresh, Some(peer(42001)), now), Err(Denial::CapacityFull));
        assert_eq!(window.retained_count(), MAX_RETIRED);
        assert_eq!(window.check_login(&attempt(0, 0, 43000), now), Err(Denial::RetiredAttempt));
    }

    #[test]
    fn expiry_frees_only_old_rows_and_admits_one_reserved_slot() {
        let now = Instant::now();
        let mut window = RetirementWindow::default();
        window.retire(attempt(1, 1, 41000), None, now).unwrap();
        for n in 1..MAX_RETIRED {
            window.retire(attempt(n as u8 + 1, n as u32, 41000 + n as u16), None,
                          now + Duration::from_secs(1)).unwrap();
        }
        let stamp = now + RETIRED_TTL + Duration::from_nanos(1);
        let fresh = attempt(200, 1000, 42000);
        window.check_login(&fresh, stamp).unwrap();
        assert_eq!(window.retained_count(), MAX_RETIRED - 1);
        window.retire(fresh, Some(peer(42001)), stamp).unwrap();
        assert_eq!(window.retained_count(), MAX_RETIRED);
        assert_eq!(window.check_login(&attempt(201, 1001, 42002), stamp), Err(Denial::CapacityFull));
    }

    #[test]
    fn credential_worker_result_requires_a_new_retirement_check() {
        let now = Instant::now();
        let mut window = RetirementWindow::default();
        let candidate = attempt(7, 41, 40000);
        window.check_login(&candidate, now).unwrap();
        window.retire(candidate, Some(peer(40001)), now + Duration::from_secs(1)).unwrap();
        assert_eq!(window.check_login(&candidate, now + Duration::from_secs(2)), Err(Denial::RetiredAttempt));
        assert_eq!(window.retained_count(), 1);
    }

    #[test]
    fn capacity_must_be_rechecked_after_worker_before_allocation() {
        let now = Instant::now();
        let mut window = RetirementWindow::default();
        for n in 0..MAX_RETIRED - 1 {
            window.retire(attempt(n as u8, n as u32, 41000 + n as u16), None, now).unwrap();
        }
        let candidate = attempt(200, 1000, 42000);
        window.check_login(&candidate, now).unwrap();
        window.retire(attempt(201, 1001, 42001), None, now + Duration::from_secs(1)).unwrap();
        assert_eq!(window.check_login(&candidate, now + Duration::from_secs(2)), Err(Denial::CapacityFull));
    }

    #[test]
    fn base_peer_gate_observes_retirement_after_auth_start() {
        let now = Instant::now();
        let mut window = RetirementWindow::default();
        let candidate = attempt(7, 42, 40002);
        window.check_login(&candidate, now).unwrap();
        window.retire(attempt(7, 41, 40000), Some(peer(40001)), now + Duration::from_secs(1)).unwrap();
        assert_eq!(window.check_base_peer(&candidate, peer(40001), now + Duration::from_secs(2)),
                   Err(Denial::RetiredPeerForKey));
    }

    #[test]
    fn backwards_clock_neither_forgets_records_nor_inserts_unsorted_retirement() {
        let now = Instant::now();
        let mut window = retired(now);
        let later = now + Duration::from_secs(10);
        window.check_login(&attempt(7, 42, 40002), later).unwrap();
        assert_eq!(window.check_login(&attempt(7, 42, 40002), now), Err(Denial::ClockRegression));
        assert_eq!(window.retire(attempt(8, 1, 45000), None, now), Err(Denial::ClockRegression));
        assert_eq!(window.retained_count(), 1);
        assert_eq!(window.check_login(&attempt(7, 41, 40003), later), Err(Denial::RetiredAttempt));
    }

    #[test]
    fn nonce_is_an_unsigned_marker_without_invented_monotonic_requirement() {
        let now = Instant::now();
        let mut window = RetirementWindow::default();
        window.retire(attempt(7, u32::MAX, 40000), None, now).unwrap();
        window.check_login(&attempt(7, 0, 40002), now).unwrap();
        assert_eq!(window.check_login(&attempt(7, u32::MAX, 40003), now), Err(Denial::RetiredAttempt));
    }
}



#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn empty_heartbeat_envelope_preserves_rpc_and_validates_token() {
        let token:u32=0x12345678;
        let envelope=[vec![1],token.to_le_bytes().to_vec()].concat();
        assert!(empty_envelope(&envelope,token).unwrap().is_empty());
        assert!(empty_envelope(&[],token).unwrap().is_empty());
        assert!(empty_envelope(&envelope,token^1).is_err());
        let rpc=[envelope,vec![0x8e,20,0,221,0,100,0]].concat();
        assert_eq!(empty_envelope(&rpc,token).unwrap(),rpc);
    }
    fn first(token:u32)->Frame {
        let mut b=vec![0x58,4,1];b.extend(token.to_le_bytes());b.push(9);b.extend([0;8]);transport091::parse(&b).unwrap()
    }
    #[test] fn first_frame_activates_once_and_bad_token_has_no_effect() {
        let now=Instant::now();let mut s=Session::new(1,[1;16],"127.0.0.1:40000".parse().unwrap(),now);
        assert!(s.receive(&first(s.token^1),now).is_err());assert!(!s.active);assert_eq!(s.tx.len(),0);
        let f=first(s.token);assert!(!s.receive(&f,now).unwrap());assert_eq!(s.rx,1);assert_eq!(s.tx.len(),2);
        assert!(!s.receive(&f,now).unwrap());assert_eq!(s.rx,1);assert_eq!(s.tx.len(),2);
    }
    #[test] fn unauthenticated_channel_feedback_cannot_extend_pending_session() {
        let now=Instant::now();let mut s=Session::new(1,[1;16],"127.0.0.1:40000".parse().unwrap(),now);
        let f=transport091::parse(&[0x48,4,1,0,0,0,0,0,0,0]).unwrap();
        assert!(s.receive(&f,now+Duration::from_secs(3)).is_err());assert_eq!(s.last_rx,now);assert!(!s.active);
    }
    #[test] fn invalid_body_cannot_apply_valid_ack() {
        let now=Instant::now();let mut s=Session::new(1,[1;16],"127.0.0.1:40000".parse().unwrap(),now);
        s.receive(&first(s.token),now).unwrap();s.tx.due(now,1).unwrap();
        let mut f=first(s.token);f.cumulative=Some(1);f.body.push(77);
        assert!(s.receive(&f,now).is_err());assert_eq!(s.tx.cumulative,0);assert_eq!(s.tx.len(),2);
    }
    fn ready(now:Instant)->Session {
        let mut s=Session::new(1,[1;16],"127.0.0.1:40000".parse().unwrap(),now);
        s.account_ready=true;s.account_probe=true;s.receive(&first(s.token),now).unwrap();
        s.tx.due(now,1).unwrap();s.tx.due(now,1).unwrap();s
    }
    fn rpc(s:&Session,n:u32,id:i16,command:i16)->Frame {
        let mut f=first(s.token);f.sequence=Some(n);f.cumulative=Some(2);
        f.body.truncate(5);f.body.extend([0x8e,20,0]);f.body.extend(id.to_le_bytes());f.body.extend(command.to_le_bytes());f.body.extend([0;16]);f
    }
    #[test] fn retired_peer_blocks_tokenless_feedback_before_any_new_channel_mutation() {
        // Synthetic transport controls, not native compatibility evidence.
        let now=Instant::now();let old_login="127.0.0.1:40000".parse().unwrap();
        let old_base="127.0.0.1:40001".parse().unwrap();let new_login="127.0.0.1:40002".parse().unwrap();
        let new_base="127.0.0.1:40003".parse().unwrap();let mut retirement=RetirementWindow::default();
        retirement.retire(LoginAttempt::new([1;16],41,old_login),Some(old_base),now).unwrap();
        let mut s=ready(now);s.login_peer=new_login;s.base_peer=Some(new_base);
        s.login_attempt=Some(LoginAttempt::new(s.key,42,new_login));
        s.outbox.push_back(vec![77]);
        let stamp=now+Duration::from_secs(1);
        let ack_clear=transport091::ack(2);
        let wire=base::encrypt(&ack_clear,&[1;16]).unwrap();
        let ack=transport091::parse_interactive(&base::decrypt(&wire,&s.key).unwrap()).unwrap();
        assert!(ack.body.is_empty());
        // Same reused cipher key alone cannot distinguish this old ACK. This
        // positive control proves it would advance the new queue without the
        // socket gate, so token-only tests would not cover the actual problem.
        let mut unguarded=s.clone();unguarded.receive(&ack,stamp).unwrap();
        assert_eq!(unguarded.tx.cumulative,2);assert_ne!(unguarded.outbox,s.outbox);
        let before=(s.rx,s.tx.cumulative,s.tx.len(),s.last_rx,s.received.clone(),s.outbox.clone(),s.base_peer);
        for peer in [old_login,old_base] {
            assert_eq!(s.guard_base_peer(&mut retirement,peer,stamp),Err(Denial::RetiredPeerForKey));
            assert_eq!((s.rx,s.tx.cumulative,s.tx.len(),s.last_rx,s.received.clone(),s.outbox.clone(),s.base_peer),before);
        }
        s.guard_base_peer(&mut retirement,new_base,stamp).unwrap();
        s.receive(&ack,stamp).unwrap();assert_eq!(s.tx.cumulative,2);
        // The conservative peer gate is interactive only; old lab sessions do
        // not acquire a LoginAttempt and retain their existing key retirement.
        let lab=Session::new(3,[1;16],old_login,now);
        lab.guard_base_peer(&mut retirement,old_base,stamp).unwrap();
    }
    #[test] fn new_attempt_does_not_make_old_handoff_or_session_token_valid() {
        let now=Instant::now();let old_peer="127.0.0.1:40000".parse().unwrap();
        let new_peer="127.0.0.1:40002".parse().unwrap();let mut retirement=RetirementWindow::default();
        retirement.retire(LoginAttempt::new([1;16],41,old_peer),None,now).unwrap();
        let mut s=Session::new(2,[1;16],new_peer,now);s.account_ready=true;
        s.login_attempt=Some(LoginAttempt::new(s.key,42,new_peer));s.handoff=200;s.token=400;
        let mut old_handshake=vec![1,0,0,8,0];old_handshake.extend(17u32.to_le_bytes());
        old_handshake.extend([0,0]);old_handshake.extend(100u32.to_le_bytes());
        old_handshake.extend(0u32.to_le_bytes());old_handshake.extend([2,0]);
        assert_eq!(s.guard_base_peer(&mut retirement,old_peer,now),Err(Denial::RetiredPeerForKey));
        s.guard_base_peer(&mut retirement,new_peer,now).unwrap();
        assert!(base::base_request(&old_handshake,s.handoff).is_err());
        assert!(s.receive(&first(300),now).is_err());
        assert_eq!((s.active,s.rx,s.tx.len(),s.received.len(),s.base_peer),(false,0,0,0,None));
        // Correct new channel values are still accepted; no client state or
        // previous sequence window was copied across the two Sessions.
        old_handshake[11..15].copy_from_slice(&s.handoff.to_le_bytes());
        assert_eq!(base::base_request(&old_handshake,s.handoff).unwrap(),(17,0));
        s.receive(&first(s.token),now).unwrap();assert!(s.active);assert_eq!(s.rx,1);
    }
    #[test] fn ready_duplicate_replies_once_and_changed_replay_is_rejected() {
        let now=Instant::now();let mut s=ready(now);let f=rpc(&s,1,221,100);
        s.receive(&f,now).unwrap();assert_eq!((s.rx,s.sync_mask,s.tx.len()),(2,1,1));
        s.receive(&f,now).unwrap();assert_eq!((s.rx,s.sync_mask,s.tx.len()),(2,1,1));
        let changed=rpc(&s,1,222,300);assert!(s.receive(&changed,now).is_err());
        let again=rpc(&s,2,222,100);assert!(s.receive(&again,now).is_err());
        assert_eq!((s.rx,s.sync_mask,s.tx.len()),(2,1,1));assert_eq!(s.request_ids,vec![221]);
    }
    #[test] fn ready_bad_outer_rolls_back_valid_piggyback_and_ack() {
        let now=Instant::now();let mut s=ready(now);
        let mut outer=rpc(&s,2,222,777);outer.piggybacks.push(rpc(&s,1,221,100));
        assert!(s.receive(&outer,now+Duration::from_secs(1)).is_err());
        assert_eq!((s.rx,s.sync_mask,s.tx.cumulative,s.tx.len()),(1,0,0,2));
        assert!(s.request_ids.is_empty());assert_eq!(s.last_rx,now);
    }
    #[test] fn ready_rejects_later_message_after_piggyback_logout_atomically() {
        let now=Instant::now();let mut s=ready(now);
        let mut logout=rpc(&s,1,221,100);logout.body.truncate(5);logout.body.extend([11,0]);
        let mut outer=rpc(&s,3,223,600);outer.piggybacks=vec![logout,rpc(&s,2,222,300)];
        assert!(s.receive(&outer,now).is_err());
        assert_eq!((s.rx,s.sync_mask,s.tx.cumulative,s.tx.len()),(1,0,0,2));
    }
    #[test] fn ready_wrong_token_unsent_ack_and_queue_overflow_are_atomic() {
        let now=Instant::now();let mut s=ready(now);let f=rpc(&s,1,221,100);
        let mut wrong=f.clone();wrong.body[1]^=1;assert!(s.receive(&wrong,now).is_err());
        wrong=f.clone();wrong.cumulative=Some(3);assert!(s.receive(&wrong,now).is_err());
        assert_eq!((s.rx,s.sync_mask,s.tx.cumulative,s.tx.len()),(1,0,0,2));
        for _ in 0..6 {s.tx.enqueue().unwrap();}
        let mut full=f;full.cumulative=Some(0);assert!(s.receive(&full,now).is_err());
        assert_eq!((s.rx,s.sync_mask,s.tx.cumulative,s.tx.len()),(1,0,0,8));
    }
    #[test] fn granted_dossier_sync_is_bound_to_fixture_and_atomic_across_retries() {
        // Own parser-control fixture, not native compatibility evidence.
        let now=Instant::now();let time=1791125440i32;
        let epoch=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let directory=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/unified-wire")
            .join(format!("dossier-session-{}-{epoch}",std::process::id()));
        fs::create_dir_all(&directory).unwrap();
        let mut descriptor=[0u8;70];descriptor[0]=81;descriptor[20]=18;
        descriptor[52..56].copy_from_slice(&time.to_le_bytes());
        let mut payload=b"\x80\x02(K\x01]((M\x01\x1cJ".to_vec();payload.extend(time.to_le_bytes());
        payload.extend([b'U',70]);payload.extend(descriptor);payload.extend(b"tet.");
        for name in ["state.bin","shop.bin"] {fs::write(directory.join(name),b"\x80\x02}.").unwrap();}
        fs::write(directory.join("dossier.bin"),&payload).unwrap();
        use sha2::Digest;
        let cursor=serde_json::json!({"version":1,"last_change_time":time,"vehicle_type_compact_descr":7169});
        let mut record=cursor.clone();record["payload_sha256"]=serde_json::json!(format!("{:x}",sha2::Sha256::digest(&payload)));
        fs::write(directory.join("manifest.json"),serde_json::to_vec(&serde_json::json!({
            "fixture_version":2,"profile_version":2,"snapshot_revision":2,"wire_sync_revision":1,
            "compatibility_catalog_revision":3,"preservation":{"dossier_cache":record},
            "grant":{"grant_id":"test-is7-v1","granted_at_ms":1791125440000u64,"base_profile_sha256":"a".repeat(64)}})).unwrap()).unwrap();
        fs::write(directory.join("compatibility.json"),serde_json::to_vec(&serde_json::json!({
            "snapshot_revision":2,"wire_sync_revision":1,"compatibility_catalog_revision":3,"dossier_cache":cursor})).unwrap()).unwrap();
        let mut s=Session::new(1,[1;16],"127.0.0.1:40000".parse().unwrap(),now);
        s.hangar=Some(Arc::new(crate::hangar091::Fixtures::load_interactive(&directory).unwrap()));
        s.identity=Some(Arc::new(crate::identity091::Profile {account_id:"12345678-1234-4234-8234-123456789abc".to_owned(),
            database_id:42,name:"own_user".to_owned(),fixture_dir:directory}));
        s.tx=Window::interactive();s.account_ready=true;s.account_probe=true;
        s.receive(&first(s.token),now).unwrap();s.tx.due(now,1).unwrap();s.tx.due(now,1).unwrap();
        let initial_session=s.clone();
        let mut cached=rpc(&s,1,223,600);
        cached.body[12..20].copy_from_slice(&1i64.to_le_bytes());
        cached.body[20..24].copy_from_slice(&time.to_le_bytes());
        let before=(s.rx,s.sync_mask,s.tx.cumulative,s.tx.len(),s.request_ids.len());
        for changed in [0,time-1,time+1] {
            let mut wrong=cached.clone();wrong.body[20..24].copy_from_slice(&changed.to_le_bytes());
            assert!(s.receive(&wrong,now+Duration::from_secs(1)).is_err());
            assert_eq!((s.rx,s.sync_mask,s.tx.cumulative,s.tx.len(),s.request_ids.len()),before);
        }
        let mut outer=cached.clone();outer.sequence=Some(2);outer.body[20..24].copy_from_slice(&(time+1).to_le_bytes());
        outer.piggybacks.push(rpc(&s,1,221,100));
        assert!(s.receive(&outer,now+Duration::from_secs(1)).is_err());
        assert_eq!((s.rx,s.sync_mask,s.tx.cumulative,s.tx.len(),s.request_ids.len()),before);
        s.receive(&cached,now+Duration::from_secs(2)).unwrap();
        assert_eq!((s.rx,s.sync_mask,s.request_ids.as_slice()),(2,4,[223].as_slice()));
        let pending=s.tx.len();s.receive(&cached,now+Duration::from_secs(3)).unwrap();assert_eq!(s.tx.len(),pending);
        let mut again=cached;again.sequence=Some(2);again.body[8..10].copy_from_slice(&224i16.to_le_bytes());
        assert!(s.receive(&again,now+Duration::from_secs(4)).is_err());
        assert_eq!((s.rx,s.sync_mask,s.request_ids.as_slice()),(2,4,[223].as_slice()));

        // Complete UI09/UI10 shape: three cached initial requests, the state
        // stream, then native revision1 with the same persistent hash.
        let mut s=initial_session;
        let persistent_hash=-1176871600i32;
        let mut bundle=rpc(&s,1,221,100);bundle.body[20..24].copy_from_slice(&persistent_hash.to_le_bytes());
        let mut shop=rpc(&s,1,222,300);shop.body[20..24].copy_from_slice(&518i32.to_le_bytes());
        shop.body[24..28].copy_from_slice(&(-846328027i32).to_le_bytes());
        let mut dossier=rpc(&s,1,223,600);dossier.body[12..20].copy_from_slice(&1i64.to_le_bytes());
        dossier.body[20..24].copy_from_slice(&time.to_le_bytes());
        bundle.body.extend(&shop.body[5..]);bundle.body.extend(&dossier.body[5..]);
        let mut refresh=rpc(&s,2,224,100);refresh.body[12..20].copy_from_slice(&1i64.to_le_bytes());
        refresh.body[20..24].copy_from_slice(&persistent_hash.to_le_bytes());
        let mut early=refresh.clone();early.sequence=Some(1);
        assert!(s.receive(&early,now+Duration::from_secs(1)).is_err());
        assert_eq!((s.rx,s.sync_mask,s.account_cache_hash),(1,0,None));
        s.receive(&bundle,now+Duration::from_secs(2)).unwrap();
        assert_eq!((s.rx,s.sync_mask,s.account_cache_hash),(2,7,Some(persistent_hash)));
        let mut published=Vec::new();
        while let Some((_,_,clear))=s.tx.due(now+Duration::from_secs(2),s.rx).unwrap() {
            published.push(transport091::parse_interactive(&clear).unwrap().body);
        }
        let fixture=s.hangar.as_ref().unwrap();let mut expected=Vec::new();
        for (id,command) in [(221,100),(222,300),(223,600)] {
            expected.extend(crate::hangar091::response(&crate::account091::Request{id,command},fixture).unwrap());
        }
        expected.push(crate::hangar091::show_gui(42).unwrap());
        assert_eq!(published,expected);
        // Native receipt of those streams is not inferred from this unit test.
        let before=(s.rx,s.sync_mask,s.tx.cumulative,s.tx.len(),s.request_ids.len(),s.account_cache_hash);
        for hash in [0,persistent_hash+1] {
            let mut changed=refresh.clone();changed.body[20..24].copy_from_slice(&hash.to_le_bytes());
            assert!(s.receive(&changed,now+Duration::from_secs(3)).is_err());
            assert_eq!((s.rx,s.sync_mask,s.tx.cumulative,s.tx.len(),s.request_ids.len(),s.account_cache_hash),before);
        }
        let mut unknown=refresh.clone();unknown.body[12..20].copy_from_slice(&2i64.to_le_bytes());
        assert!(s.receive(&unknown,now+Duration::from_secs(3)).is_err());
        let stamp=now+Duration::from_millis(2100);
        s.receive(&refresh,stamp).unwrap();
        assert_eq!((s.rx,s.sync_mask,s.request_ids.as_slice()),(3,7,[221,222,223,224].as_slice()));
        let reply=s.tx.due(stamp,s.rx).unwrap().unwrap().2;
        assert_eq!(transport091::parse_interactive(&reply).unwrap().body,
            crate::hangar091::response_refresh(&crate::account091::Request{id:224,command:100}).unwrap());
        let pending=s.tx.len();s.receive(&refresh,stamp).unwrap();assert_eq!(s.tx.len(),pending);
        let mut changed=refresh.clone();changed.body[20]^=1;
        assert!(s.receive(&changed,stamp).is_err());
        let mut duplicate=refresh;duplicate.sequence=Some(3);
        assert!(s.receive(&duplicate,stamp).is_err());
        assert_eq!((s.rx,s.sync_mask,s.request_ids.as_slice()),(3,7,[221,222,223,224].as_slice()));
    }
    #[test] fn persistent_cache_hints_only_trigger_identical_full_streams_and_remain_atomic() {
        let now=Instant::now();
        let epoch=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let directory=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/unified-wire")
            .join(format!("cache-hint-session-{}-{epoch}",std::process::id()));
        fs::create_dir_all(&directory).unwrap();
        for (name,raw) in [("state.bin",b"\x80\x02}(U\x03revK\x01u.".as_slice()),
                          ("shop.bin",b"\x80\x02}.".as_slice()),("dossier.bin",b"\x80\x02(K\x00]t.".as_slice())] {
            fs::write(directory.join(name),raw).unwrap();
        }
        let mut s=Session::new(1,[1;16],"127.0.0.1:40000".parse().unwrap(),now);
        s.hangar=Some(Arc::new(crate::hangar091::Fixtures::load_interactive(&directory).unwrap()));
        s.identity=Some(Arc::new(crate::identity091::Profile {account_id:"12345678-1234-4234-8234-123456789abc".to_owned(),
            database_id:42,name:"own_user".to_owned(),fixture_dir:directory}));
        s.tx=Window::interactive();s.account_ready=true;s.account_probe=true;
        s.receive(&first(s.token),now).unwrap();s.tx.due(now,1).unwrap();s.tx.due(now,1).unwrap();
        let mut cold=s.clone();let mut original=rpc(&s,1,221,100);
        original.body.extend(&rpc(&s,1,222,300).body[5..]);
        original.body.extend(&rpc(&s,1,223,600).body[5..]);
        let mut cached=original.clone();cached.body[20..24].copy_from_slice(&(-1176871600i32).to_le_bytes());
        cached.body[43..47].copy_from_slice(&518i32.to_le_bytes());
        cached.body[47..51].copy_from_slice(&(-846328027i32).to_le_bytes());
        let before=(s.rx,s.sync_mask,s.tx.cumulative,s.tx.len(),s.request_ids.len());
        let mut bad=cached.clone();bad.body[43..47].copy_from_slice(&(-1i32).to_le_bytes());
        assert!(s.receive(&bad,now+Duration::from_secs(1)).is_err());
        assert_eq!((s.rx,s.sync_mask,s.tx.cumulative,s.tx.len(),s.request_ids.len()),before);
        // A valid cached child followed by an invalid parent must not commit it.
        let mut invalid_parent=rpc(&s,2,222,300);invalid_parent.body[20..24].copy_from_slice(&(-1i32).to_le_bytes());
        let mut child=rpc(&s,1,221,100);child.body[20..24].copy_from_slice(&(-1176871600i32).to_le_bytes());
        invalid_parent.piggybacks.push(child);
        assert!(s.receive(&invalid_parent,now+Duration::from_secs(1)).is_err());
        assert_eq!((s.rx,s.sync_mask,s.tx.cumulative,s.tx.len(),s.request_ids.len()),before);
        cold.receive(&original,now+Duration::from_secs(2)).unwrap();
        s.receive(&cached,now+Duration::from_secs(2)).unwrap();
        assert_eq!((s.rx,s.sync_mask,s.request_ids.as_slice()),(2,7,[221,222,223].as_slice()));
        let pending=s.tx.len();let queued=s.outbox.clone();
        s.receive(&cached,now+Duration::from_secs(3)).unwrap();
        assert_eq!(s.tx.len(),pending);assert_eq!(s.outbox,queued);
        let mut altered=cached.clone();altered.body[20]^=1;
        assert!(s.receive(&altered,now+Duration::from_secs(3)).is_err());
        assert_eq!((s.rx,s.sync_mask,s.tx.len()),(2,7,pending));
        // Cold and cached clients receive exactly the same authoritative bytes.
        assert_eq!(s.outbox,cold.outbox);
        loop {
            let actual=s.tx.due(now+Duration::from_secs(3),s.rx).unwrap();
            let expected=cold.tx.due(now+Duration::from_secs(3),cold.rx).unwrap();
            assert_eq!(actual,expected);if actual.is_none(){break;}
        }
        let mut duplicate_command=cached;duplicate_command.sequence=Some(2);
        duplicate_command.body[8..10].copy_from_slice(&224i16.to_le_bytes());
        assert!(s.receive(&duplicate_command,now+Duration::from_secs(4)).is_err());
        assert_eq!((s.rx,s.sync_mask,s.request_ids.as_slice()),(2,7,[221,222,223].as_slice()));
    }
    #[test] fn interactive_history_is_bounded_and_old_or_changed_replays_cannot_apply() {
        let now=Instant::now();let mut s=Session::new(1,[1;16],"127.0.0.1:40000".parse().unwrap(),now);
        let epoch=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let directory=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/unified-wire").join(format!("session-{}-{epoch}",std::process::id()));
        fs::create_dir_all(&directory).unwrap();
        for (file,body) in [("state.bin",b"\x80\x02}.".as_slice()),("shop.bin",b"\x80\x02}.".as_slice()),("dossier.bin",b"\x80\x02(K\x00]t.".as_slice())] {fs::write(directory.join(file),body).unwrap();}
        s.hangar=Some(Arc::new(crate::hangar091::Fixtures::load_interactive(&directory).unwrap()));
        s.identity=Some(Arc::new(crate::identity091::Profile {account_id:"12345678-1234-4234-8234-123456789abc".to_owned(),database_id:42,name:"own_user".to_owned(),fixture_dir:directory}));
        s.tx=Window::interactive();s.account_ready=true;s.account_probe=true;
        let initial=first(s.token);s.receive(&initial,now).unwrap();
        let created=s.tx.due(now,1).unwrap().unwrap().2;
        assert!(created.windows(b"own_user".len()).any(|w|w==b"own_user"));
        assert!(!created.windows(b"p02-hangar-player".len()).any(|w|w==b"p02-hangar-player"));
        s.tx.due(now,1).unwrap();let mut acknowledged=2;
        for n in 1..201 {
            let mut frame=first(s.token);frame.sequence=Some(n);frame.cumulative=Some(acknowledged);frame.body.truncate(5);
            if n%5==0 {frame.body.extend([0x8e,20,0,202,0,245,1]);frame.body.extend([0;16]);}
            else if n%2==1 {
                frame.body.extend([0x97,72,0]);frame.body.extend((300i16+n as i16).to_le_bytes());
                frame.body.extend(108i16.to_le_bytes());frame.body.extend(16u32.to_le_bytes());
                for value in [1i32,1,6,2570,96,2826,0,3082,0,6,0,0,0,0,0,0] {frame.body.extend(value.to_le_bytes());}
            }
            s.receive(&frame,now+Duration::from_millis(n as u64*500)).unwrap();
            assert!(s.received.len()<=64);
            if n==199 {
                let pending=s.tx.len();let denied=s.unsupported_request_ids.len();
                s.receive(&frame,now+Duration::from_secs(100)).unwrap();
                assert_eq!((s.tx.len(),s.unsupported_request_ids.len()),(pending,denied));
            }
            if n==200 {
                let stats=s.stats_requests;s.receive(&frame,now+Duration::from_millis(n as u64*500)).unwrap();assert_eq!(s.stats_requests,stats);
                let mut changed=frame.clone();changed.body[6]=19;
                assert!(s.receive(&changed,now+Duration::from_secs(102)).is_err());
            }
            while let Some((sequence,_,_))=s.tx.due(now+Duration::from_millis(n as u64*500),s.rx).unwrap() {acknowledged=acknowledged.max(sequence+1);}
        }
        assert_eq!(s.stats_requests,40);assert_eq!(s.rx,201);assert_eq!(s.received.len(),64);
        assert_eq!(s.unsupported_request_ids.len(),64);assert_eq!(s.sync_mask,0);
        let before=(s.rx,s.tx.cumulative,s.last_rx,s.stats_requests);
        assert!(s.receive(&initial,now+Duration::from_secs(103)).is_err());
        assert_eq!((s.rx,s.tx.cumulative,s.last_rx,s.stats_requests),before);
    }

    // Synthetic unit fixtures exercise the boundary and atomic transport state;
    // they are not a native Avatar creation or battle compatibility claim.
    fn arena_ready(now:Instant)->Session {
        use std::sync::atomic::{AtomicUsize,Ordering};
        static NEXT:AtomicUsize=AtomicUsize::new(0);
        let directory=Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../local/evidence/20261005-p02-arena-entry/data/arena-session-unit-files")
            .join(format!("{}-{}",std::process::id(),NEXT.fetch_add(1,Ordering::Relaxed)));
        fs::create_dir_all(&directory).unwrap();
        for (file,body) in [("state.bin",b"\x80\x02}.".as_slice()),("shop.bin",b"\x80\x02}.".as_slice()),
                           ("dossier.bin",b"\x80\x02(K\x00]t.".as_slice())] {
            fs::write(directory.join(file),body).unwrap();
        }
        let mut s=Session::new(7,[1;16],"127.0.0.1:40000".parse().unwrap(),now);
        s.hangar=Some(Arc::new(crate::hangar091::Fixtures::load_interactive(&directory).unwrap()));
        s.identity=Some(Arc::new(crate::identity091::Profile {
            account_id:"00000000-0000-0000-0000-000000000001".to_owned(),database_id:42,
            name:"Танкист_Ёж".to_owned(),fixture_dir:directory,
        }));
        s.tx=Window::interactive();s.account_ready=true;s.account_probe=true;
        s.base_peer=Some("127.0.0.1:40001".parse().unwrap());
        s.receive(&first(s.token),now).unwrap();
        s.tx.due(now,s.rx).unwrap();s.tx.due(now,s.rx).unwrap();
        s.receive(&transport091::parse(&transport091::ack(2)).unwrap(),now).unwrap();
        s.sync_mask=7;s.request_ids=vec![221,222,223];s.account_cache_hash=Some(-42);
        assert!(s.ready_for_arena_base());s
    }
    fn arena_frame(s:&Session,n:u32,payload:&[u8],ack:u32)->Frame {
        Frame {flags:0x458,sequence:Some(n),cumulative:Some(ack),selective:vec![],
            body:[vec![1],s.token.to_le_bytes().to_vec(),payload.to_vec()].concat(),piggybacks:vec![]}
    }
    fn arena_stamp(s:&Session)->(u32,u32,usize,u8,u8,u32,usize,usize,Instant,bool) {
        (s.rx,s.tx.cumulative,s.tx.len(),s.sync_mask,s.avatar_unsupported_envelopes,
         s.stats_requests,s.request_ids.len(),s.outbox.len(),s.last_rx,s.arena_base)
    }
    #[test] fn arena_transition_requires_all_readiness_gates_and_is_opt_in() {
        let now=Instant::now();let ready=arena_ready(now);
        assert!(!ready.arena_base);assert_eq!(ready.avatar_unsupported_envelopes,0);
        for changed in 0..9 {
            let mut s=ready.clone();
            match changed {
                0=>s.active=false,1=>s.account_ready=false,2=>s.identity=None,3=>s.hangar=None,
                4=>s.base_peer=None,5=>s.sync_mask=3,6=>s.outbox.push_back(vec![42]),
                7=>s.tx.enqueue().unwrap(),8=>s.arena_base=true,_=>unreachable!(),
            }
            let before=arena_stamp(&s);assert!(!s.ready_for_arena_base());
            assert!(s.queue_arena_base().is_err());assert_eq!(arena_stamp(&s),before);
        }
        // A fully ready normal interactive channel never changes phase merely
        // by receiving a heartbeat. Only the explicit control path queues it.
        let mut ordinary=ready;
        ordinary.receive(&arena_frame(&ordinary,1,&[],2),now).unwrap();
        assert!(!ordinary.arena_base);assert_eq!(ordinary.tx.len(),0);
    }
    #[test] fn arena_transition_preserves_channel_identity_and_queues_one_owned_body() {
        let now=Instant::now();let mut s=arena_ready(now);let before=s.clone();
        s.queue_arena_base().unwrap();assert!(s.arena_base);
        assert_eq!((s.id,s.key,s.handoff,s.token,s.rx,s.login_peer,s.base_peer,s.created_at),
            (before.id,before.key,before.handoff,before.token,before.rx,before.login_peer,before.base_peer,before.created_at));
        assert!(Arc::ptr_eq(s.identity.as_ref().unwrap(),before.identity.as_ref().unwrap()));
        assert!(Arc::ptr_eq(s.hangar.as_ref().unwrap(),before.hangar.as_ref().unwrap()));
        assert_eq!(s.received,before.received);assert_eq!(s.request_ids,before.request_ids);
        assert_eq!(s.account_cache_hash,before.account_cache_hash);assert_eq!(s.outbox,before.outbox);
        let sent=s.tx.due(now,s.rx).unwrap().unwrap();assert_eq!((sent.0,sent.1),(2,1));
        let actual=transport091::parse_interactive(&sent.2).unwrap();
        let expected=crate::arena091::reset_to_avatar_base(&crate::arena091::AvatarBaseSeed {
            entity_id:crate::arena_control091::AVATAR_ENTITY_ID,name:"Танкист_Ёж",arena_unique_id:1,
        }).unwrap();
        assert_eq!(actual.body,expected);assert_eq!(&actual.body[..3],&[4,0,5]);
        assert!(actual.body.windows("Танкист_Ёж".len()).any(|v|v=="Танкист_Ёж".as_bytes()));
        assert!(s.queue_arena_base().is_err());assert_eq!(s.tx.len(),1);
        let retry=s.tx.due(now+transport091::RETRY,s.rx).unwrap().unwrap();
        assert_eq!((retry.0,retry.1),(2,2));assert_eq!(transport091::parse_interactive(&retry.2).unwrap().body,actual.body);
    }
    #[test] fn arena_encode_or_sequence_exhaustion_cannot_partially_change_phase() {
        let now=Instant::now();let ready=arena_ready(now);
        let mut bad=ready.clone();let identity=bad.identity.as_ref().unwrap();
        bad.identity=Some(Arc::new(crate::identity091::Profile {
            account_id:identity.account_id.clone(),database_id:identity.database_id,
            name:"bad name".to_owned(),fixture_dir:identity.fixture_dir.clone(),
        }));
        let before=arena_stamp(&bad);assert!(bad.queue_arena_base().is_err());assert_eq!(arena_stamp(&bad),before);
        let mut s=ready;s.tx=Window::new();
        for n in 0..transport091::MAX_SEQUENCE {
            s.tx.enqueue().unwrap();s.tx.due(now,s.rx).unwrap();
            s.tx.acknowledge(&transport091::parse(&transport091::ack(n+1)).unwrap()).unwrap();
        }
        let before=arena_stamp(&s);assert!(s.ready_for_arena_base());
        assert!(s.queue_arena_base().is_err());assert_eq!(arena_stamp(&s),before);
    }
    #[test] fn avatar_unknown_envelope_is_explicit_rejection_not_an_account_dispatch() {
        let now=Instant::now();let ready=arena_ready(now);
        let mut payload=vec![0x8e,20,0,202,0,245,1];payload.extend([0;16]);
        // Same bytes before the transition take the pre-existing Account path.
        let mut ordinary=ready.clone();ordinary.receive(&arena_frame(&ordinary,1,&payload,2),now).unwrap();
        assert_eq!(ordinary.stats_requests,1);assert_eq!(ordinary.tx.len(),1);assert!(!ordinary.arena_base);
        let mut s=ready;s.queue_arena_base().unwrap();s.tx.due(now,s.rx).unwrap();
        let frame=arena_frame(&s,1,&payload,3);let mut events=Vec::new();
        assert!(!s.receive_ready(&frame,now,&mut events,0,&mut 32).unwrap());
        assert_eq!((s.rx,s.stats_requests,s.avatar_unsupported_envelopes,s.tx.len(),s.outbox.len()),(2,0,1,0,0));
        assert!(events.iter().any(|e|e.starts_with("AVATAR_RPC_UNSUPPORTED ")
            && e.contains("parsed_rpc=false domain_applied=false transport_acknowledged=true")));
        assert!(!events.iter().any(|e|e.starts_with("SERVER_STATS ") || e.starts_with("ACCOUNT_")));
        // Reliable duplicates don't count/execute again; altered replays fail.
        s.receive(&frame,now).unwrap();assert_eq!(s.avatar_unsupported_envelopes,1);
        let mut altered=frame.clone();altered.body[5]^=1;assert!(s.receive(&altered,now).is_err());
        assert_eq!(s.avatar_unsupported_envelopes,1);
    }
    #[test] fn avatar_wrong_token_oversize_ack_and_bad_outer_preserve_entire_clone() {
        let now=Instant::now();let mut s=arena_ready(now);s.queue_arena_base().unwrap();s.tx.due(now,s.rx).unwrap();
        let before=arena_stamp(&s);let history=s.received.clone();
        let good=arena_frame(&s,1,&[0xee,0],3);
        let mut wrong=good.clone();wrong.body[1]^=1;
        let mut unsent=good.clone();unsent.cumulative=Some(4);
        let large=arena_frame(&s,1,&[0xee;513],3);
        let mut parent=arena_frame(&s,2,&[0xdd],3);parent.body[1]^=1;parent.piggybacks.push(good.clone());
        for input in [wrong,unsent,large,parent] {
            assert!(s.receive(&input,now+Duration::from_secs(1)).is_err());
            assert_eq!(arena_stamp(&s),before);assert_eq!(s.received,history);
        }
        assert!(!s.receive(&good,now+Duration::from_secs(1)).unwrap());
        assert_eq!((s.rx,s.tx.cumulative,s.tx.len(),s.avatar_unsupported_envelopes),(2,3,0,1));
    }
    #[test] fn avatar_rejection_budget_still_allows_heartbeat_and_logout_without_fake_reply() {
        let now=Instant::now();let mut s=arena_ready(now);s.queue_arena_base().unwrap();s.tx.due(now,s.rx).unwrap();
        for sequence in 1..=32 {
            assert!(!s.receive(&arena_frame(&s,sequence,&[0xfe],3),now).unwrap());
        }
        let before=arena_stamp(&s);
        assert!(s.receive(&arena_frame(&s,33,&[0xfe],3),now+Duration::from_secs(1)).is_err());
        assert_eq!(arena_stamp(&s),before);assert_eq!((s.tx.len(),s.outbox.len()),(0,0));
        assert!(!s.receive(&arena_frame(&s,33,&[],3),now+Duration::from_secs(2)).unwrap());
        let mut empty=arena_frame(&s,33,&[],3);empty.body.clear();
        assert!(!s.receive(&empty,now+Duration::from_secs(2)).unwrap());
        assert_eq!((s.rx,s.avatar_unsupported_envelopes),(34,32));
        assert!(s.receive(&arena_frame(&s,34,&[11,0],3),now+Duration::from_secs(3)).unwrap());
        assert_eq!((s.rx,s.avatar_unsupported_envelopes,s.tx.len(),s.outbox.len()),(35,32,0,0));
    }
    fn waiting_space(now:Instant)->Session {
        let mut s=arena_ready(now);
        s.queue_arena_checkpoint(crate::arena_control091::Checkpoint::AvatarSpace).unwrap();
        assert_eq!(s.arena_space,ArenaSpaceStage::AwaitingEnable);
        let reset=s.tx.due(now,s.rx).unwrap().unwrap();
        assert_eq!(&transport091::parse_interactive(&reset.2).unwrap().body[..3],&[4,0,5]);
        s
    }
    #[test] fn space_checkpoint_does_not_advance_without_exact_post_base_enable() {
        let now=Instant::now();let ready=waiting_space(now);
        assert_eq!(ready.tx.len(),1); // only reset/createBase, no cell or space yet
        for payload in [vec![],vec![9,0],vec![8],vec![0xee]] {
            let mut s=ready.clone();
            assert!(!s.receive(&arena_frame(&s,1,&payload,3),now).unwrap());
            assert_eq!(s.arena_space,ArenaSpaceStage::AwaitingEnable);
            assert_eq!((s.tx.len(),s.outbox.len()),(0,0));
        }
        let mut s=ready;assert!(s.receive(&arena_frame(&s,1,&[11,0],3),now).unwrap());
        assert_eq!(s.arena_space,ArenaSpaceStage::AwaitingEnable);assert_eq!(s.tx.len(),0);
    }
    #[test] fn post_base_enable_queues_literal_cell_then_space_once_and_retries_exact_bytes() {
        let now=Instant::now();let mut s=waiting_space(now);let before=s.clone();
        let enable=arena_frame(&s,1,&[9],3);let mut events=Vec::new();
        assert!(!s.receive_ready(&enable,now,&mut events,0,&mut 32).unwrap());
        assert_eq!((s.arena_space,s.rx,s.avatar_unsupported_envelopes),(ArenaSpaceStage::Queued,2,0));
        assert_eq!(events.iter().filter(|e|e.starts_with("ARENA_ENABLE_ENTITIES ")).count(),1);
        assert_eq!(events.iter().filter(|e|e.starts_with("ARENA_SPACE_QUEUED ")).count(),1);
        assert!(!events.iter().any(|e|e.starts_with("AVATAR_RPC_UNSUPPORTED ")));
        assert_eq!((s.id,s.key,s.token,s.handoff,s.login_peer,s.base_peer),(before.id,before.key,before.token,before.handoff,before.login_peer,before.base_peer));
        assert_eq!((s.sync_mask,s.account_cache_hash,s.stats_requests,s.request_ids.clone()),
                   (before.sync_mask,before.account_cache_hash,before.stats_requests,before.request_ids.clone()));
        assert!(Arc::ptr_eq(s.identity.as_ref().unwrap(),before.identity.as_ref().unwrap()));
        assert!(Arc::ptr_eq(s.hangar.as_ref().unwrap(),before.hangar.as_ref().unwrap()));
        let sent=s.tx.due(now,s.rx).unwrap().unwrap();assert_eq!((sent.0,sent.1),(3,1));
        let body=transport091::parse_interactive(&sent.2).unwrap().body;
        // Literal framing/field audit, independent of encoder round-trips.
        assert_eq!(body.len(),144);assert_eq!(&body[..3],&[6,43,0]);
        assert_eq!(&body[3..11],&[1,0,0,0,0,0,0,0]); // space1/unattached0
        assert_eq!(&body[11..23],&[232,255,105,194,193,20,7,66,18,232,222,195]);
        assert_eq!(&body[23..27],&[0,0,128,63]);assert_eq!(&body[27..39],&[0;12]);
        assert_eq!(&body[39..46],&[1,3,0,16,9,0,0]); // team1/ownVehicle ID/unlocked/no ground claim
        assert_eq!(&body[46..49],&[7,95,0]);assert_eq!(&body[49..53],&[1,0,0,0]);
        assert_eq!(&body[53..63],&[1,0,0,0,0,0,0,0,1,0]);
        let mut matrix=vec![0u8;64];for index in [0,5,10,15] {matrix[index*4..index*4+4].copy_from_slice(&[0,0,128,63]);}
        assert_eq!(&body[63..127],matrix.as_slice());assert_eq!(&body[127..],b"spaces/01_karelia");
        s.receive(&enable,now).unwrap();assert_eq!((s.tx.len(),s.rx,s.avatar_unsupported_envelopes),(1,2,0));
        let retry=s.tx.due(now+transport091::RETRY,s.rx).unwrap().unwrap();
        assert_eq!((retry.0,retry.1),(3,2));assert_eq!(transport091::parse_interactive(&retry.2).unwrap().body,body);
        s.receive(&arena_frame(&s,2,&[9],4),now).unwrap();
        assert_eq!((s.tx.len(),s.rx,s.avatar_unsupported_envelopes),(0,3,1)); // new app09 rejected, never recreated
        assert_eq!(s.arena_space,ArenaSpaceStage::Queued);
        assert!(s.queue_arena_space().is_err());
    }
    #[test] fn space_enable_wrong_token_unsent_ack_and_outer_failure_rollback_phase_and_transport() {
        let now=Instant::now();let ready=waiting_space(now);let enable=arena_frame(&ready,1,&[9],3);
        let mut wrong=enable.clone();wrong.body[1]^=1;
        let mut future=enable.clone();future.cumulative=Some(4);
        let mut gap=enable.clone();gap.sequence=Some(2);
        let mut outer=arena_frame(&ready,2,&[0xee],3);outer.body[1]^=1;outer.piggybacks.push(enable.clone());
        for bad in [wrong,future,gap,outer] {
            let mut s=ready.clone();assert!(s.receive(&bad,now+Duration::from_secs(1)).is_err());
            assert_eq!(arena_stamp(&s),arena_stamp(&ready));assert_eq!(s.received,ready.received);
            assert_eq!(s.arena_space,ArenaSpaceStage::AwaitingEnable);
            let retry=s.tx.due(now+transport091::RETRY,s.rx).unwrap().unwrap();
            assert_eq!(&transport091::parse_interactive(&retry.2).unwrap().body[..3],&[4,0,5]);
        }
    }
    #[test] fn space_enable_in_valid_piggyback_advances_only_one_stage() {
        let now=Instant::now();let mut s=waiting_space(now);
        let enable=arena_frame(&s,1,&[9],3);let mut outer=arena_frame(&s,2,&[],3);outer.piggybacks.push(enable.clone());
        assert!(!s.receive(&outer,now).unwrap());
        assert_eq!((s.rx,s.arena_space,s.tx.len(),s.avatar_unsupported_envelopes),(3,ArenaSpaceStage::Queued,1,0));
        assert!(!s.receive(&outer,now).unwrap());assert_eq!((s.rx,s.tx.len()),(3,1));
    }
    #[test] fn space_queue_capacity_failure_does_not_consume_enable_and_retry_can_progress() {
        let now=Instant::now();let mut s=waiting_space(now);
        for _ in 0..7 {s.tx.enqueue().unwrap();}
        for _ in 0..7 {s.tx.due(now,s.rx).unwrap();}
        let before=s.clone();let enable=arena_frame(&s,1,&[9],2);
        assert!(s.receive(&enable,now+Duration::from_secs(1)).is_err());
        assert_eq!(arena_stamp(&s),arena_stamp(&before));assert_eq!(s.received,before.received);
        assert_eq!(s.arena_space,ArenaSpaceStage::AwaitingEnable);
        s.receive(&transport091::parse_interactive(&transport091::ack(10)).unwrap(),now).unwrap();
        assert!(!s.receive(&enable,now).unwrap());assert_eq!((s.rx,s.tx.len(),s.arena_space),(2,1,ArenaSpaceStage::Queued));
    }
    #[test] fn base_probe_and_ordinary_interactive_do_not_send_space_on_enable() {
        let now=Instant::now();let mut normal=arena_ready(now);let old=normal.clone();
        assert!(normal.receive(&arena_frame(&normal,1,&[9],2),now).is_err());
        assert_eq!(arena_stamp(&normal),arena_stamp(&old));assert_eq!(normal.arena_space,ArenaSpaceStage::Disabled);
        let mut base=arena_ready(now);base.queue_arena_checkpoint(crate::arena_control091::Checkpoint::AvatarBase).unwrap();
        base.tx.due(now,base.rx).unwrap();base.receive(&arena_frame(&base,1,&[9],3),now).unwrap();
        assert_eq!((base.arena_space,base.tx.len(),base.avatar_unsupported_envelopes),(ArenaSpaceStage::Disabled,0,1));
        assert!(base.queue_arena_space().is_err());
    }
    #[test] fn space_unknown_sink_retains_original_bounds_after_transition() {
        let now=Instant::now();let mut s=waiting_space(now);
        s.receive(&arena_frame(&s,1,&[9],3),now).unwrap();s.tx.due(now,s.rx).unwrap();
        for n in 2..34 {s.receive(&arena_frame(&s,n,&[0xee],4),now).unwrap();}
        assert_eq!(s.avatar_unsupported_envelopes,32);let before=s.clone();
        for bad in [arena_frame(&s,34,&[0xee],4),arena_frame(&s,34,&[0xee;513],4)] {
            assert!(s.receive(&bad,now).is_err());assert_eq!(arena_stamp(&s),arena_stamp(&before));
            assert_eq!(s.arena_space,ArenaSpaceStage::Queued);
        }
        assert!(!s.receive(&arena_frame(&s,34,&[],4),now).unwrap());
        assert!(s.receive(&arena_frame(&s,35,&[11,0],4),now).unwrap());
    }
    fn vehicle_ready(now:Instant)->Session {
        let mut s=arena_ready(now);
        let directory=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/server/fixtures")
            .join(crate::arena_vehicle091::PRIMARY_ACCOUNT).join("r4-catalog3").canonicalize().unwrap();
        s.hangar=Some(Arc::new(crate::hangar091::Fixtures::load_interactive(&directory).unwrap()));
        s.identity=Some(Arc::new(crate::identity091::Profile {account_id:crate::arena_vehicle091::PRIMARY_ACCOUNT.to_owned(),
            database_id:1,name:crate::arena_vehicle091::PRIMARY_NAME.to_owned(),fixture_dir:directory}));
        s
    }
    fn waiting_vehicle(now:Instant)->Session {
        let mut s=vehicle_ready(now);s.queue_arena_checkpoint(crate::arena_control091::Checkpoint::AvatarVehicle).unwrap();
        assert_eq!(s.arena_vehicle,ArenaVehicleStage::AwaitingEnable);assert_eq!(s.arena_space,ArenaSpaceStage::Disabled);
        s.tx.due(now,s.rx).unwrap();s
    }
    fn waiting_entity_request(now:Instant)->Session {
        let mut s=waiting_vehicle(now);s.receive(&arena_frame(&s,1,&[9],3),now).unwrap();
        assert_eq!(s.arena_vehicle,ArenaVehicleStage::AwaitingEntityRequest);
        let sent=s.tx.due(now,s.rx).unwrap().unwrap();assert_eq!((sent.0,sent.1),(3,1));s
    }
    #[test] fn vehicle_fixture_validation_precedes_all_reset_or_channel_mutation() {
        let now=Instant::now();let ready=vehicle_ready(now);
        for change in 0..5 {
            let mut s=ready.clone();let current=s.identity.as_ref().unwrap();
            let mut identity=crate::identity091::Profile {account_id:current.account_id.clone(),database_id:current.database_id,
                name:current.name.clone(),fixture_dir:current.fixture_dir.clone()};
            match change {0=>identity.account_id="00000000-0000-0000-0000-000000000002".to_owned(),
                1=>identity.database_id=2,2=>identity.name="other".to_owned(),
                3=>{identity.fixture_dir.pop();identity.fixture_dir.push("r3-catalog3");},
                4=>s.hangar=arena_ready(now).hangar,_=>unreachable!()}
            s.identity=Some(Arc::new(identity));let before=s.clone();
            assert!(s.queue_arena_checkpoint(crate::arena_control091::Checkpoint::AvatarVehicle).is_err());
            assert_eq!(arena_stamp(&s),arena_stamp(&before));assert_eq!(s.received,before.received);
            assert_eq!(s.arena_vehicle,ArenaVehicleStage::Disabled);assert!(s.arena_vehicle_seed.is_none());
        }
    }
    #[test] fn vehicle_enable_only_announces_aoi_and_never_creates_before_request() {
        let now=Instant::now();let mut s=waiting_vehicle(now);let before=s.clone();
        let enable=arena_frame(&s,1,&[9],3);let mut events=Vec::new();
        assert!(!s.receive_ready(&enable,now,&mut events,0,&mut 32).unwrap());
        assert_eq!((s.arena_vehicle,s.arena_space,s.rx,s.tx.len(),s.avatar_unsupported_envelopes),
            (ArenaVehicleStage::AwaitingEntityRequest,ArenaSpaceStage::Disabled,2,1,0));
        assert!(Arc::ptr_eq(s.identity.as_ref().unwrap(),before.identity.as_ref().unwrap()));
        assert!(Arc::ptr_eq(s.hangar.as_ref().unwrap(),before.hangar.as_ref().unwrap()));
        assert_eq!((s.key,s.token,s.handoff,s.base_peer),(before.key,before.token,before.handoff,before.base_peer));
        assert!(events.iter().any(|e|e.starts_with("ARENA_VEHICLE_ANNOUNCED ") && e.contains("vehicle_created=false")));
        assert!(!events.iter().any(|e|e.starts_with("ARENA_VEHICLE_QUEUED ")));
        let sent=s.tx.due(now,s.rx).unwrap().unwrap();let body=transport091::parse_interactive(&sent.2).unwrap().body;
        assert_eq!(body,crate::arena_vehicle091::announce_vehicle(s.arena_vehicle_seed.as_ref().unwrap()).unwrap());
        assert_eq!(body.len(),221);s.receive(&enable,now).unwrap();assert_eq!(s.tx.len(),1);
        let retry=s.tx.due(now+transport091::RETRY,s.rx).unwrap().unwrap();
        assert_eq!(transport091::parse_interactive(&retry.2).unwrap().body,body);
        assert!(s.queue_arena_vehicle_announcement().is_err());
        assert!(s.queue_requested_arena_vehicle().is_err()); // announcement is not ACKed
    }
    #[test] fn vehicle_enable_rejects_bad_outer_and_late_validation_without_partial_acks_or_body() {
        let now=Instant::now();let ready=waiting_vehicle(now);let enable=arena_frame(&ready,1,&[9],3);
        let mut token=enable.clone();token.body[1]^=1;
        let mut future=enable.clone();future.cumulative=Some(4);
        let mut outer=arena_frame(&ready,2,&[0xee],3);outer.body[1]^=1;outer.piggybacks.push(enable.clone());
        for bad in [token,future,outer] {
            let mut s=ready.clone();assert!(s.receive(&bad,now+Duration::from_secs(1)).is_err());
            assert_eq!(arena_stamp(&s),arena_stamp(&ready));assert_eq!(s.received,ready.received);
            assert_eq!(s.arena_vehicle,ready.arena_vehicle);assert_eq!(s.arena_vehicle_seed,ready.arena_vehicle_seed);
        }
        let mut s=ready;s.arena_vehicle_seed.as_mut().unwrap().health=91;let before=s.clone();
        assert!(s.receive(&enable,now+Duration::from_secs(1)).is_err());
        assert_eq!(arena_stamp(&s),arena_stamp(&before));assert_eq!(s.received,before.received);
        assert_eq!(s.arena_vehicle,ArenaVehicleStage::AwaitingEnable);
        let retry=s.tx.due(now+transport091::RETRY,s.rx).unwrap().unwrap();
        assert_eq!(&transport091::parse_interactive(&retry.2).unwrap().body[..3],&[4,0,5]);
    }
    #[test] fn vehicle_capacity_failure_rolls_back_all_messages_and_accepts_exact_retry() {
        let now=Instant::now();let mut s=waiting_vehicle(now);
        for _ in 0..7 {s.tx.enqueue().unwrap();s.tx.due(now,s.rx).unwrap();}
        let before=s.clone();let enable=arena_frame(&s,1,&[9],2);
        assert!(s.receive(&enable,now+Duration::from_secs(1)).is_err());
        assert_eq!(arena_stamp(&s),arena_stamp(&before));assert_eq!(s.received,before.received);
        assert_eq!(s.arena_vehicle,ArenaVehicleStage::AwaitingEnable);
        s.receive(&transport091::parse_interactive(&transport091::ack(10)).unwrap(),now).unwrap();
        s.receive(&enable,now).unwrap();assert_eq!((s.rx,s.tx.len(),s.arena_vehicle),(2,1,ArenaVehicleStage::AwaitingEntityRequest));
    }
    #[test] fn vehicle_new_modes_do_not_change_base_space_or_ordinary_behavior() {
        let now=Instant::now();let mut normal=vehicle_ready(now);
        assert!(normal.queue_arena_vehicle_announcement().is_err());assert!(normal.queue_requested_arena_vehicle().is_err());
        assert!(normal.receive(&arena_frame(&normal,1,&[9],2),now).is_err());
        assert!(normal.receive(&arena_frame(&normal,1,&[8,4,0,3,0,16,9],2),now).is_err());
        assert_eq!(normal.arena_vehicle,ArenaVehicleStage::Disabled);assert!(!normal.arena_base);
        for checkpoint in [crate::arena_control091::Checkpoint::AvatarBase,crate::arena_control091::Checkpoint::AvatarSpace] {
            let mut s=vehicle_ready(now);s.queue_arena_checkpoint(checkpoint).unwrap();s.tx.due(now,s.rx).unwrap();
            s.receive(&arena_frame(&s,1,&[9],3),now).unwrap();
            assert_eq!(s.arena_vehicle,ArenaVehicleStage::Disabled);assert!(s.arena_vehicle_seed.is_none());
            assert!(s.queue_arena_vehicle_announcement().is_err());assert!(s.queue_requested_arena_vehicle().is_err());
            if checkpoint==crate::arena_control091::Checkpoint::AvatarSpace {
                let sent=s.tx.due(now,s.rx).unwrap().unwrap();assert_eq!(transport091::parse_interactive(&sent.2).unwrap().body.len(),144);
            } else {assert_eq!(s.tx.len(),0);assert_eq!(s.avatar_unsupported_envelopes,1);}
        }
    }
    #[test] fn vehicle_automatic_calls_are_observed_without_domain_success_or_rpc_reply() {
        let now=Instant::now();let mut s=waiting_entity_request(now);
        s.receive(&arena_frame(&s,2,&[8,4,0,3,0,16,9],4),now).unwrap();
        s.tx.due(now,s.rx).unwrap();let before=s.clone();
        let payload=[0x86,0,0,0x0c,8,0,0,0,0,0,0,0,0,0];let input=arena_frame(&s,3,&payload,5);
        let mut events=Vec::new();s.receive_ready(&input,now,&mut events,0,&mut 32).unwrap();
        assert_eq!(events.iter().filter(|e|e.starts_with("AVATAR_LIFECYCLE_OBSERVED ") && e.contains("domain_applied=false gameplay=false")).count(),2);
        assert_eq!(events.iter().filter(|e|e.starts_with("AVATAR_RPC_UNSUPPORTED ")).count(),1);
        assert_eq!((s.tx.len(),s.outbox.len(),s.stats_requests,s.sync_mask),(0,0,before.stats_requests,before.sync_mask));
        assert_eq!(s.hangar.as_ref().unwrap().state_sha256(),before.hangar.as_ref().unwrap().state_sha256());
        s.receive(&input,now).unwrap();assert_eq!(s.avatar_unsupported_envelopes,1);
        assert!(!s.receive(&arena_frame(&s,4,&[],5),now).unwrap());
        assert!(s.receive(&arena_frame(&s,5,&[11,0],5),now).unwrap());
    }
    #[test] fn vehicle_measured_request_queues_exact_create_once_with_owned_retry() {
        let now=Instant::now();let mut s=waiting_entity_request(now);let before=s.clone();
        let request=arena_frame(&s,2,&[8,4,0,3,0,16,9],4);let mut events=Vec::new();
        s.receive_ready(&request,now,&mut events,0,&mut 32).unwrap();
        assert_eq!((s.rx,s.tx.len(),s.arena_vehicle,s.avatar_unsupported_envelopes),(3,1,ArenaVehicleStage::Queued,0));
        assert_eq!(events.iter().filter(|e|e.starts_with("ARENA_ENTITY_UPDATE_REQUEST ") && e.contains("announcement_acked=true")).count(),1);
        assert_eq!(events.iter().filter(|e|e.starts_with("ARENA_VEHICLE_QUEUED ") && e.contains("body_bytes=97")).count(),1);
        assert!(!events.iter().any(|e|e.starts_with("AVATAR_RPC_UNSUPPORTED ")));
        assert_eq!((s.key,s.token,s.handoff,s.base_peer,s.account_cache_hash,s.stats_requests,s.sync_mask),
            (before.key,before.token,before.handoff,before.base_peer,before.account_cache_hash,before.stats_requests,before.sync_mask));
        assert!(Arc::ptr_eq(s.identity.as_ref().unwrap(),before.identity.as_ref().unwrap()));
        assert!(Arc::ptr_eq(s.hangar.as_ref().unwrap(),before.hangar.as_ref().unwrap()));
        let sent=s.tx.due(now,s.rx).unwrap().unwrap();assert_eq!((sent.0,sent.1),(4,1));
        let body=transport091::parse_interactive(&sent.2).unwrap().body;
        assert_eq!(body.len(),97);assert_eq!(&body[..10],&[9,94,0,0,3,0,16,9,2,0]);
        assert_eq!(body,crate::arena_vehicle091::create_requested_vehicle(s.arena_vehicle_seed.as_ref().unwrap()).unwrap());
        s.receive(&request,now).unwrap();assert_eq!((s.rx,s.tx.len(),s.avatar_unsupported_envelopes),(3,1,0));
        let retry=s.tx.due(now+transport091::RETRY,s.rx).unwrap().unwrap();assert_eq!((retry.0,retry.1),(4,2));
        assert_eq!(transport091::parse_interactive(&retry.2).unwrap().body,body);
        let mut changed=request.clone();changed.body[8]^=1;let old=s.clone();
        assert!(s.receive(&changed,now).is_err());assert_eq!(arena_stamp(&s),arena_stamp(&old));
        s.receive(&arena_frame(&s,3,&[8,4,0,3,0,16,9],5),now).unwrap();
        assert_eq!((s.rx,s.tx.len(),s.avatar_unsupported_envelopes),(4,0,1));
        assert!(s.queue_requested_arena_vehicle().is_err());
    }
    #[test] fn vehicle_request_wrong_token_future_ack_gap_or_late_outer_failure_is_atomic() {
        let now=Instant::now();let ready=waiting_entity_request(now);
        let request=arena_frame(&ready,2,&[8,4,0,3,0,16,9],4);
        let mut wrong=request.clone();wrong.body[1]^=1;
        let mut future=request.clone();future.cumulative=Some(5);
        let mut gap=request.clone();gap.sequence=Some(3);
        let mut outer=arena_frame(&ready,3,&[0xee],4);outer.body[1]^=1;outer.piggybacks.push(request);
        for bad in [wrong,future,gap,outer] {
            let mut s=ready.clone();assert!(s.receive(&bad,now+Duration::from_secs(1)).is_err());
            assert_eq!(arena_stamp(&s),arena_stamp(&ready));assert_eq!(s.received,ready.received);
            assert_eq!(s.arena_vehicle,ArenaVehicleStage::AwaitingEntityRequest);assert_eq!(s.arena_vehicle_seed,ready.arena_vehicle_seed);
            let retry=s.tx.due(now+transport091::RETRY,s.rx).unwrap().unwrap();assert_eq!(retry.0,3);
            assert_eq!(transport091::parse_interactive(&retry.2).unwrap().body.len(),221);
        }
    }
    #[test] fn vehicle_request_requires_announcement_actually_sent_and_acked() {
        let now=Instant::now();let ready=waiting_vehicle(now);
        let enable=arena_frame(&ready,1,&[9],3);let mut jumped=arena_frame(&ready,2,&[8,4,0,3,0,16,9],3);
        jumped.piggybacks.push(enable.clone());let mut s=ready.clone();
        assert!(s.receive(&jumped,now).is_err());assert_eq!(arena_stamp(&s),arena_stamp(&ready));
        assert_eq!(s.arena_vehicle,ArenaVehicleStage::AwaitingEnable);assert_eq!(s.received,ready.received);
        s.receive(&enable,now).unwrap();let queued=s.clone();
        for ack in [3,4] { // no ACK and an impossible ACK of still-unsent announcement
            assert!(s.receive(&arena_frame(&s,2,&[8,4,0,3,0,16,9],ack),now).is_err());
            assert_eq!(arena_stamp(&s),arena_stamp(&queued));assert_eq!(s.received,queued.received);
        }
        s.tx.due(now,s.rx).unwrap();let sent=s.clone();
        assert!(s.receive(&arena_frame(&s,2,&[8,4,0,3,0,16,9],3),now).is_err());assert_eq!(arena_stamp(&s),arena_stamp(&sent));
        s.receive(&arena_frame(&s,2,&[8,4,0,3,0,16,9],4),now).unwrap();
        assert_eq!(s.arena_vehicle,ArenaVehicleStage::Queued);
    }
    #[test] fn vehicle_announcement_ack_allows_later_pending_heartbeat() {
        let now=Instant::now();let mut s=waiting_entity_request(now);
        s.receive(&transport091::parse_interactive(&transport091::ack(4)).unwrap(),now).unwrap();
        assert_eq!(s.arena_vehicle_announcement,Some((3,true)));
        s.tx.enqueue().unwrap();assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,4);
        s.receive(&arena_frame(&s,2,&[8,4,0,3,0,16,9],4),now).unwrap();
        assert_eq!((s.tx.len(),s.arena_vehicle),(2,ArenaVehicleStage::Queued));
        let sent=s.tx.due(now,s.rx).unwrap().unwrap();assert_eq!(sent.0,5);
        assert_eq!(transport091::parse_interactive(&sent.2).unwrap().body.len(),97);
    }
    #[test] fn vehicle_selective_ack_must_cover_announcement_not_later_heartbeat() {
        let now=Instant::now();let mut s=waiting_entity_request(now);
        s.tx.enqueue().unwrap();assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,4);let before=s.clone();
        let mut request=arena_frame(&s,2,&[8,4,0,3,0,16,9],3);request.selective=vec![4];
        assert!(s.receive(&request,now).is_err());assert_eq!(arena_stamp(&s),arena_stamp(&before));
        assert_eq!(s.arena_vehicle_announcement,Some((3,false)));
        request.selective=vec![3];s.receive(&request,now).unwrap();
        assert_eq!((s.tx.len(),s.tx.cumulative,s.arena_vehicle_announcement),(2,3,Some((3,true))));
        assert_eq!(s.arena_vehicle,ArenaVehicleStage::Queued);
    }
    #[test] fn vehicle_request_only_measured_entity_framing_and_phase_can_advance() {
        let now=Instant::now();let ready=waiting_entity_request(now);
        for payload in [vec![8,4,0,4,0,16,9],vec![8,8,0,3,0,16,9,0,0,0,0],
            vec![8,4,0,3,0,16],vec![8,4,0,3,0,16,9,0],vec![9],vec![0x86,0,0]] {
            let mut s=ready.clone();s.receive(&arena_frame(&s,2,&payload,4),now).unwrap();
            assert_eq!((s.rx,s.tx.len(),s.arena_vehicle,s.avatar_unsupported_envelopes),(3,0,ArenaVehicleStage::AwaitingEntityRequest,1));
        }
        let mut s=waiting_vehicle(now);s.receive(&arena_frame(&s,1,&[8,4,0,3,0,16,9],3),now).unwrap();
        assert_eq!((s.arena_vehicle,s.tx.len(),s.avatar_unsupported_envelopes),(ArenaVehicleStage::AwaitingEnable,0,1));
    }
    #[test] fn vehicle_request_late_seed_identity_or_readiness_failure_cannot_consume_ack() {
        let now=Instant::now();let ready=waiting_entity_request(now);
        for change in 0..9 {
            let mut s=ready.clone();match change {
                0=>s.arena_vehicle_seed.as_mut().unwrap().health=91,
                1=>s.arena_vehicle_seed.as_mut().unwrap().descriptor[0]^=1,
                2=>s.arena_vehicle_seed.as_mut().unwrap().state_sha256[0]^=1,
                3=>s.identity=arena_ready(now).identity,4=>s.hangar=arena_ready(now).hangar,
                5=>s.sync_mask=3,6=>s.outbox.push_back(vec![0xee]),
                7=>s.base_peer=None,8=>s.arena_vehicle_seed=None,_=>unreachable!(),
            }
            let before=s.clone();assert!(s.receive(&arena_frame(&s,2,&[8,4,0,3,0,16,9],4),now).is_err(),"change {change}");
            assert_eq!(arena_stamp(&s),arena_stamp(&before));assert_eq!(s.received,before.received);
            assert_eq!(s.arena_vehicle,ArenaVehicleStage::AwaitingEntityRequest);assert_eq!(s.arena_vehicle_seed,before.arena_vehicle_seed);
        }
    }
    #[test] fn vehicle_requested_create_sequence_capacity_failure_rolls_back_receive() {
        let now=Instant::now();let mut s=waiting_entity_request(now);let mut full=Window::new();
        for n in 0..transport091::MAX_SEQUENCE {
            full.enqueue().unwrap();full.due(now,s.rx).unwrap();
            full.acknowledge(&transport091::parse(&transport091::ack(n+1)).unwrap()).unwrap();
        }
        assert_eq!(full.len(),0);s.tx=full;let before=s.clone();
        assert!(s.receive(&arena_frame(&s,2,&[8,4,0,3,0,16,9],transport091::MAX_SEQUENCE),now).is_err());
        assert_eq!(arena_stamp(&s),arena_stamp(&before));assert_eq!(s.received,before.received);
        assert_eq!(s.arena_vehicle,ArenaVehicleStage::AwaitingEntityRequest);
    }
    #[test] fn vehicle_request_in_valid_piggyback_is_once_only_and_unknown_bound_stays_32() {
        let now=Instant::now();let mut s=waiting_entity_request(now);
        let request=arena_frame(&s,2,&[8,4,0,3,0,16,9],4);let mut outer=arena_frame(&s,3,&[],4);outer.piggybacks.push(request);
        s.receive(&outer,now).unwrap();assert_eq!((s.rx,s.tx.len(),s.arena_vehicle),(4,1,ArenaVehicleStage::Queued));
        s.receive(&outer,now).unwrap();assert_eq!((s.rx,s.tx.len(),s.avatar_unsupported_envelopes),(4,1,0));
        s.tx.due(now,s.rx).unwrap();
        for n in 4..36 {s.receive(&arena_frame(&s,n,&[0xee],5),now).unwrap();}
        assert_eq!(s.avatar_unsupported_envelopes,32);let before=s.clone();
        for payload in [vec![0xee],vec![0xee;513]] {
            assert!(s.receive(&arena_frame(&s,36,&payload,5),now).is_err());assert_eq!(arena_stamp(&s),arena_stamp(&before));
        }
        assert!(!s.receive(&arena_frame(&s,36,&[],5),now).unwrap());
        assert!(s.receive(&arena_frame(&s,37,&[11,0],5),now).unwrap());
    }
    // Literal from closed native Vehicle03, not the preparation encoder.
    const READY_COMPOUND:[u8;33]=[
        0x0d,8,0,0,0,0,0,3,0,16,9,0x8d,5,0,2,1,0,0,0,0x86,0,0,0x0c,8,0,0,0,0,0,0,0,0,0];
    fn ready_waiting_enable(now:Instant)->Session {
        let mut s=vehicle_ready(now);s.queue_arena_checkpoint(crate::arena_control091::Checkpoint::AvatarReady).unwrap();
        assert!(s.arena_ready);assert!(s.arena_preparation.is_none());
        assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,2);s
    }
    fn ready_waiting_compound(now:Instant)->Session {
        let mut s=ready_waiting_enable(now);
        s.receive(&arena_frame(&s,1,&[9],3),now).unwrap();
        assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,3);
        s.receive(&arena_frame(&s,2,&[8,4,0,3,0,16,9],4),now).unwrap();
        assert_eq!(s.arena_vehicle_creation,Some((4,false)));
        let sent=s.tx.due(now,s.rx).unwrap().unwrap();assert_eq!(sent.0,4);
        assert_eq!(transport091::parse_interactive(&sent.2).unwrap().body.len(),97);s
    }
    fn unchanged_preparation(s:&Session,before:&Session) {
        assert_eq!(arena_stamp(s),arena_stamp(before));assert_eq!(s.received,before.received);
        assert_eq!((s.arena_ready,s.arena_vehicle,s.arena_space,s.arena_vehicle_announcement,s.arena_vehicle_creation),
            (before.arena_ready,before.arena_vehicle,before.arena_space,before.arena_vehicle_announcement,before.arena_vehicle_creation));
        assert_eq!(s.arena_preparation,before.arena_preparation);
        assert_eq!(s.arena_battle_preparation,before.arena_battle_preparation);
        assert_eq!(s.arena_vehicle_seed,before.arena_vehicle_seed);
        assert_eq!((s.key,s.token,s.handoff,s.base_peer,s.account_cache_hash),(before.key,before.token,before.handoff,before.base_peer,before.account_cache_hash));
        assert!(Arc::ptr_eq(s.identity.as_ref().unwrap(),before.identity.as_ref().unwrap()));
        assert!(Arc::ptr_eq(s.hangar.as_ref().unwrap(),before.hangar.as_ref().unwrap()));
    }
    #[test] fn preparation_whole_ready_accepts_once_after_owned_create_ack_and_keeps_account_immutable() {
        let now=Instant::now();let mut s=ready_waiting_compound(now);let before=s.clone();
        let mut events=Vec::new();s.receive_ready(&arena_frame(&s,3,&READY_COMPOUND,5),now,&mut events,0,&mut 32).unwrap();
        assert_eq!((s.rx,s.tx.len(),s.arena_vehicle_creation,s.avatar_unsupported_envelopes),(4,1,Some((4,true)),0));
        assert_eq!(s.arena_preparation.as_ref().unwrap().phase(),crate::arena_ready091::Phase::Preparing);
        let loadout=s.arena_battle_preparation.as_ref().unwrap().loadout().clone();
        assert_eq!((loadout.turret_compact_descr,loadout.gun_compact_descr,loadout.selected_shell_compact_descr,loadout.selected_shell_count),
            (5891,5892,2570,20));
        assert_eq!(events.iter().filter(|e|e.starts_with("BATTLE_LOADOUT_DOMAIN_READY ")
            && e.contains("native_event=false")
            && e.contains("native_packet=false") && e.contains("hud=false")
            && e.contains("ammo_mutation=false")).count(),1);
        assert_eq!(events.iter().filter(|e|e.starts_with("ARENA_READY_ACCEPTED ") && e.contains("create_acked=true") && e.contains("domain_ready=true")).count(),1);
         assert_eq!(events.iter().filter(|e|e.starts_with("BATTLE_NATIVE_AMMO_PANEL_CANDIDATE ") && e.contains("panel_count=3") && e.contains("native_receipt=NOT_RUN")).count(),1);
         assert_eq!(events.iter().filter(|e|e.starts_with("ARENA_PREPARATION_QUEUED ") && e.contains("body_bytes=105") && e.contains("native_ammo_panel_appended=true") && e.contains("native_selected_shell_appended=true") && e.contains("native_initial_reload_appended=true") && e.contains("battle_started=false")).count(),1);
        assert_eq!(events.iter().filter(|e|e.starts_with("AVATAR_METHOD_UNSUPPORTED ") && e.contains("domain_applied=false gameplay=false")).count(),3);
        assert_eq!((s.account_cache_hash,s.stats_requests,s.sync_mask,s.key,s.token,s.handoff,s.base_peer),
            (before.account_cache_hash,before.stats_requests,before.sync_mask,before.key,before.token,before.handoff,before.base_peer));
        assert!(Arc::ptr_eq(s.identity.as_ref().unwrap(),before.identity.as_ref().unwrap()));
        assert!(Arc::ptr_eq(s.hangar.as_ref().unwrap(),before.hangar.as_ref().unwrap()));
        let sent=s.tx.due(now,s.rx).unwrap().unwrap();assert_eq!((sent.0,sent.1),(5,1));
        let body=transport091::parse_interactive(&sent.2).unwrap().body;
        let clock=crate::arena_ready091::preparation_body(crate::arena_vehicle091::VEHICLE_ENTITY_ID).unwrap();
        assert_eq!(&body[..clock.len()],clock.as_slice());
         assert_eq!(&body[clock.len()..],&[
             0x13,0x44,0x0a,0x0a,0,0,20,0,0,0,0,
             0x13,0x44,0x0a,0x0b,0,0,0,0,0,0,0,
             0x13,0x44,0x0a,0x0c,0,0,0,0,0,0,0,
             0x13,0x40,0,0x0a,0x0a,0,0,
             0x13,0x46,0x03,0x00,0x10,0x09,0,0,0,0,0,0,0x20,0x40,
         ]);
         assert_eq!(body.len(),105);assert_eq!(&body[..7],&[2,10,3,232,3,0,0]);
        let retry=s.tx.due(now+transport091::RETRY,s.rx).unwrap().unwrap();assert_eq!((retry.0,retry.1),(5,2));
        assert_eq!(transport091::parse_interactive(&retry.2).unwrap().body,body);
    }
    #[test] fn preparation_duplicate_ready_never_resets_clock_or_enqueues_another_phase() {
        let now=Instant::now();let mut s=ready_waiting_compound(now);let first=arena_frame(&s,3,&READY_COMPOUND,5);
        s.receive(&first,now).unwrap();let domain=s.arena_preparation.clone();s.tx.due(now,s.rx).unwrap();
        s.receive(&first,now+Duration::from_secs(2)).unwrap();assert_eq!(s.arena_preparation,domain);assert_eq!(s.tx.len(),1);
        let mut events=Vec::new();s.receive_ready(&arena_frame(&s,4,&READY_COMPOUND,6),now+Duration::from_secs(10),&mut events,0,&mut 32).unwrap();
        assert_eq!((s.rx,s.tx.len(),s.avatar_unsupported_envelopes),(5,0,0));assert_eq!(s.arena_preparation,domain);
        assert_eq!(events.iter().filter(|e|e.starts_with("ARENA_READY_DUPLICATE ") && e.contains("reset_deadline=false enqueued=false")).count(),1);
        assert!(!events.iter().any(|e|e.starts_with("ARENA_PREPARATION_QUEUED ") || e.starts_with("ARENA_READY_ACCEPTED ")));
        assert!(!s.preparation_expired(now+Duration::from_secs(29)).unwrap());
        assert!(s.preparation_expired(now+Duration::from_secs(30)).unwrap());
        assert_eq!(s.arena_preparation.as_ref().unwrap().phase(),crate::arena_ready091::Phase::Expired);
        assert!(!s.preparation_expired(now+Duration::from_secs(31)).unwrap());assert_eq!(s.tx.len(),0);
    }
    #[test] fn preparation_requires_create_actually_sent_and_specific_ack_not_a_later_heartbeat() {
        let now=Instant::now();let mut s=ready_waiting_enable(now);
        s.receive(&arena_frame(&s,1,&[9],3),now).unwrap();s.tx.due(now,s.rx).unwrap();
        s.receive(&arena_frame(&s,2,&[8,4,0,3,0,16,9],4),now).unwrap();let before=s.clone();
        for ack in [4,5] {
            assert!(s.receive(&arena_frame(&s,3,&READY_COMPOUND,ack),now).is_err());unchanged_preparation(&s,&before);
        }
        s.tx.due(now,s.rx).unwrap();s.tx.enqueue().unwrap();assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,5);
        let before=s.clone();let mut ready=arena_frame(&s,3,&READY_COMPOUND,4);ready.selective=vec![5];
        assert!(s.receive(&ready,now).is_err());unchanged_preparation(&s,&before);
        ready.selective=vec![4];s.receive(&ready,now).unwrap();
        assert_eq!((s.tx.len(),s.tx.cumulative,s.arena_vehicle_creation),(2,4,Some((4,true))));
        assert!(s.arena_preparation.is_some());assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,6);
    }
    #[test] fn preparation_cumulative_create_ack_allows_independent_pending_heartbeat() {
        let now=Instant::now();let mut s=ready_waiting_compound(now);
        s.tx.enqueue().unwrap();assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,5);
        s.receive(&arena_frame(&s,3,&READY_COMPOUND,5),now).unwrap();
        assert_eq!((s.tx.len(),s.tx.cumulative,s.arena_vehicle_creation),(2,5,Some((4,true))));
        let output=s.tx.due(now,s.rx).unwrap().unwrap();assert_eq!(output.0,6);
         assert_eq!(transport091::parse_interactive(&output.2).unwrap().body.len(),105);
    }
    #[test] fn preparation_wrong_token_future_ack_gap_or_late_piggyback_failure_rolls_back_everything() {
        let now=Instant::now();let ready=ready_waiting_compound(now);let input=arena_frame(&ready,3,&READY_COMPOUND,5);
        let mut wrong=input.clone();wrong.body[1]^=1;
        let mut future=input.clone();future.cumulative=Some(6);
        let mut gap=input.clone();gap.sequence=Some(4);
        let mut outer=arena_frame(&ready,4,&[0xee],5);outer.body[1]^=1;outer.piggybacks.push(input.clone());
        let mut too_big=arena_frame(&ready,4,&vec![0xee;513],5);too_big.piggybacks.push(input.clone());
        for bad in [wrong,future,gap,outer,too_big] {
            let mut s=ready.clone();assert!(s.receive(&bad,now+Duration::from_secs(1)).is_err());unchanged_preparation(&s,&ready);
            let retry=s.tx.due(now+transport091::RETRY,s.rx).unwrap().unwrap();assert_eq!(retry.0,4);
            assert_eq!(transport091::parse_interactive(&retry.2).unwrap().body.len(),97);
        }
    }
    #[test] fn preparation_valid_nested_ready_commits_once_with_following_heartbeat() {
        let now=Instant::now();let mut s=ready_waiting_compound(now);
        let input=arena_frame(&s,3,&READY_COMPOUND,5);let mut outer=arena_frame(&s,4,&[],5);outer.piggybacks.push(input);
        s.receive(&outer,now).unwrap();let domain=s.arena_preparation.clone();assert_eq!((s.rx,s.tx.len()),(5,1));
        s.receive(&outer,now+Duration::from_secs(2)).unwrap();assert_eq!((s.rx,s.tx.len()),(5,1));assert_eq!(s.arena_preparation,domain);
    }
    #[test] fn preparation_late_fixture_identity_phase_and_clock_changes_cannot_consume_ack() {
        let now=Instant::now();let ready=ready_waiting_compound(now);
        for change in 0..11 {
            let mut s=ready.clone();match change {
                0=>s.arena_vehicle_seed.as_mut().unwrap().health=91,
                1=>s.arena_vehicle_seed.as_mut().unwrap().descriptor[0]^=1,
                2=>s.arena_vehicle_seed.as_mut().unwrap().state_sha256[0]^=1,
                3=>s.identity=arena_ready(now).identity,4=>s.hangar=arena_ready(now).hangar,
                5=>s.sync_mask=3,6=>s.outbox.push_back(vec![0xee]),7=>s.base_peer=None,
                8=>s.arena_vehicle_seed=None,9=>s.arena_space=ArenaSpaceStage::Queued,
                10=>s.last_rx=now+Duration::from_secs(2),_=>unreachable!(),
            }
            let before=s.clone();assert!(s.receive(&arena_frame(&s,3,&READY_COMPOUND,5),now).is_err(),"change {change}");
            unchanged_preparation(&s,&before);assert!(s.arena_preparation.is_none());
        }
    }
    #[test] fn preparation_queue_capacity_failure_is_atomic_and_original_ready_can_retry() {
        let now=Instant::now();let mut s=ready_waiting_compound(now);
        s.receive(&transport091::parse_interactive(&transport091::ack(5)).unwrap(),now).unwrap();
        for _ in 0..8 {s.tx.enqueue().unwrap();s.tx.due(now,s.rx).unwrap();}
        let before=s.clone();let ready=arena_frame(&s,3,&READY_COMPOUND,5);
        assert!(s.receive(&ready,now).is_err());unchanged_preparation(&s,&before);
        s.receive(&transport091::parse_interactive(&transport091::ack(6)).unwrap(),now).unwrap();
        s.receive(&ready,now).unwrap();assert_eq!((s.rx,s.tx.len()),(4,8));assert!(s.arena_preparation.is_some());
        let sent=s.tx.due(now,s.rx).unwrap().unwrap();assert_eq!(sent.0,13);
         assert_eq!(transport091::parse_interactive(&sent.2).unwrap().body.len(),105);
    }
    #[test] fn preparation_sequence_exhaustion_fails_without_reusing_sequence_or_setting_deadline() {
        let now=Instant::now();let mut s=ready_waiting_compound(now);let mut full=Window::new();
        for n in 0..transport091::MAX_SEQUENCE {
            full.enqueue().unwrap();full.due(now,s.rx).unwrap();
            full.acknowledge(&transport091::parse(&transport091::ack(n+1)).unwrap()).unwrap();
        }
        s.tx=full;let before=s.clone();
        assert!(s.receive(&arena_frame(&s,3,&READY_COMPOUND,transport091::MAX_SEQUENCE),now).is_err());unchanged_preparation(&s,&before);
    }
    #[test] fn preparation_malformed_or_split_compounds_are_unsupported_without_partial_ready() {
        let now=Instant::now();let ready=ready_waiting_compound(now);
        let mut mutations=Vec::new();
        for i in 0..READY_COMPOUND.len() {let mut b=READY_COMPOUND.to_vec();b[i]^=1;mutations.push(b);}
        for n in 1..READY_COMPOUND.len() {mutations.push(READY_COMPOUND[..n].to_vec());}
        mutations.extend([READY_COMPOUND[19..22].to_vec(),[READY_COMPOUND.as_slice(),&[0]].concat()]);
        for payload in mutations {
            let mut s=ready.clone();s.receive(&arena_frame(&s,3,&payload,5),now).unwrap();
            assert_eq!((s.tx.len(),s.rx,s.avatar_unsupported_envelopes),(0,4,1));assert!(s.arena_preparation.is_none());
        }
        let mut s=ready.clone();for n in 3..35 {s.receive(&arena_frame(&s,n,&[0x86,0,0],5),now).unwrap();}
        assert_eq!(s.avatar_unsupported_envelopes,32);let before=s.clone();
        assert!(s.receive(&arena_frame(&s,35,&[0xee],5),now).is_err());unchanged_preparation(&s,&before);
        assert!(!s.receive(&arena_frame(&s,35,&[],5),now).unwrap());
        assert!(s.receive(&arena_frame(&s,36,&[11,0],5),now).unwrap());
    }
    #[test] fn preparation_cannot_advance_before_real_enable_request_and_create() {
        let now=Instant::now();let initial=ready_waiting_enable(now);let mut announced=initial.clone();
        announced.receive(&arena_frame(&announced,1,&[9],3),now).unwrap();announced.tx.due(now,announced.rx).unwrap();
        for mut s in [initial,announced] {
            let before=s.clone();let ack=if s.rx==1 {3}else{4};
            assert!(s.receive(&arena_frame(&s,s.rx,&READY_COMPOUND,ack),now).is_err());unchanged_preparation(&s,&before);
        }
    }
    #[test] fn preparation_mode_leaves_ordinary_base_space_and_vehicle_readiness_unsupported() {
        let now=Instant::now();let mut ordinary=vehicle_ready(now);let before=ordinary.clone();
        assert!(ordinary.queue_arena_preparation(now).is_err());assert!(!ordinary.preparation_expired(now).unwrap());
        assert!(ordinary.receive(&arena_frame(&ordinary,1,&READY_COMPOUND,2),now).is_err());unchanged_preparation(&ordinary,&before);
        for checkpoint in [crate::arena_control091::Checkpoint::AvatarBase,crate::arena_control091::Checkpoint::AvatarSpace,
            crate::arena_control091::Checkpoint::AvatarVehicle] {
            let mut s=vehicle_ready(now);s.queue_arena_checkpoint(checkpoint).unwrap();s.tx.due(now,s.rx).unwrap();
            s.receive(&arena_frame(&s,1,&READY_COMPOUND,3),now).unwrap();
            assert!(!s.arena_ready);assert!(s.arena_preparation.is_none());assert!(s.arena_vehicle_creation.is_none());
            assert_eq!((s.tx.len(),s.avatar_unsupported_envelopes),(0,1));
            assert!(s.queue_arena_preparation(now).is_err());assert!(!s.preparation_expired(now).unwrap());
        }
    }
    fn movement_waiting(now:Instant)->Session {
        let mut s=vehicle_ready(now);s.queue_arena_checkpoint(crate::arena_control091::Checkpoint::AvatarMovement).unwrap();
        assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,2);
        s.receive(&arena_frame(&s,1,&[9],3),now).unwrap();assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,3);
        s.receive(&arena_frame(&s,2,&[8,4,0,3,0,16,9],4),now).unwrap();assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,4);s
    }
    fn movement_live(now:Instant)->Session {
        let mut s=movement_waiting(now);s.receive(&arena_frame(&s,3,&READY_COMPOUND,5),now).unwrap();
        assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,5);s
    }
    fn unchanged_motion(s:&Session,b:&Session) {
        unchanged_preparation(s,b);assert_eq!(s.arena_movement,b.arena_movement);assert_eq!(s.arena_motion,b.arena_motion);
        assert_eq!(s.last_rx,b.last_rx);assert_eq!(s.outbox,b.outbox);
    }
    #[test] fn movement_ready_requires_its_create_ack_with_later_heartbeat_pending() {
        let t=Instant::now();let mut s=movement_waiting(t);let before=s.clone();
        assert!(s.receive(&arena_frame(&s,3,&READY_COMPOUND,4),t).is_err());unchanged_motion(&s,&before);
        s.tx.enqueue().unwrap();assert_eq!(s.tx.due(t,s.rx).unwrap().unwrap().0,5);
        let mut input=arena_frame(&s,3,&READY_COMPOUND,4);input.selective=vec![4];
        s.receive(&input,t).unwrap();assert_eq!(s.tx.len(),2);assert!(s.arena_preparation.is_none());
        let sent=s.tx.due(t,s.rx).unwrap().unwrap();assert_eq!(sent.0,6);
        let body=transport091::parse_interactive(&sent.2).unwrap().body;
        assert_eq!(body,crate::arena_movement091::phase_body(crate::arena_vehicle091::VEHICLE_ENTITY_ID).unwrap());
        assert_eq!(body[29],3);assert_eq!(s.arena_vehicle_creation,Some((4,true)));
    }
    #[test] fn movement_actual_phase_idle_forward_publication_and_real_stop_are_distinct() {
        let t=Instant::now();let mut s=movement_live(t);let identity=s.identity.clone();let fixtures=s.hangar.clone();
        s.receive(&arena_frame(&s,4,&[0x8a,1,0,0],6),t).unwrap();assert_eq!(s.arena_motion.as_ref().unwrap().phase(),crate::arena_movement091::Phase::Waiting);
        s.receive(&arena_frame(&s,5,&[0x8a,1,0,1],6),t).unwrap();let mut events=Vec::new();
        assert_eq!(s.poll_movement(t+Duration::from_secs(1),&mut events).unwrap(),None);
        let sent=s.tx.due(t+Duration::from_secs(1),s.rx).unwrap().unwrap();let body=transport091::parse_interactive(&sent.2).unwrap().body;
        assert_eq!(body.len(),31);assert_eq!(&body[..7],&[13,242,21,3,0,16,9]);
        assert_eq!(f32::from_le_bytes(body[15..19].try_into().unwrap()),crate::arena_movement091::POSITION[2]+1.0);
        assert!(events[0].contains("phase=moving"));assert!(events[0].contains("lab_elapsed_seconds=1.000000000 movement_started_seconds=0.000000000"));
        s.receive(&arena_frame(&s,6,&[0x8a,1,0,0],7),t+Duration::from_secs(1)).unwrap();
        events.clear();s.poll_movement(t+Duration::from_secs(3),&mut events).unwrap();assert!(events[0].contains("phase=stopped"));
        let last=transport091::parse_interactive(&s.tx.due(t+Duration::from_secs(3),s.rx).unwrap().unwrap().2).unwrap().body;
        assert_eq!(&last[7..],&body[7..]);assert_eq!(last[1],6);
        assert!(Arc::ptr_eq(identity.as_ref().unwrap(),s.identity.as_ref().unwrap()));assert!(Arc::ptr_eq(fixtures.as_ref().unwrap(),s.hangar.as_ref().unwrap()));
    }
    #[test] fn movement_reliable_retry_changed_retry_and_new_sequence_duplicates() {
        let t=Instant::now();let mut s=movement_live(t);let first=arena_frame(&s,4,&[0x8a,1,0,1],6);
        s.receive(&first,t).unwrap();let motion=s.arena_motion.clone();s.receive(&first,t+Duration::from_secs(1)).unwrap();assert_eq!(s.arena_motion,motion);
        let mut bad=first;bad.body[8]=0;let before=s.clone();assert!(s.receive(&bad,t+Duration::from_secs(1)).is_err());unchanged_motion(&s,&before);
        s.receive(&arena_frame(&s,5,&[0x8a,1,0,1],6),t+Duration::from_secs(2)).unwrap();
        assert_eq!(s.arena_motion.as_ref().unwrap().displacement(t+Duration::from_secs(2)),2.0);
        let motion=s.arena_motion.clone();s.receive(&arena_frame(&s,6,&READY_COMPOUND,6),t+Duration::from_secs(3)).unwrap();assert_eq!(s.arena_motion,motion);
        assert_eq!(s.tx.len(),0);assert!(s.arena_preparation.is_none());
    }
    #[test] fn movement_malformed_late_method_or_outer_reverts_command_ack_and_counters() {
        let t=Instant::now();let ready=movement_live(t);
        let mut bads=vec![arena_frame(&ready,4,&[0x8a,1,0,1,0xee],6),arena_frame(&ready,4,&[0x8a,1,0,2],6),arena_frame(&ready,4,&[0x8a,1,0,1,0x8f,12,0],6)];
        let mut token=arena_frame(&ready,4,&[0x8a,1,0,1],6);token.body[1]^=1;bads.push(token);
        let inner=arena_frame(&ready,4,&[0x8a,1,0,1],6);let mut outer=arena_frame(&ready,5,&[],6);outer.body[1]^=1;outer.piggybacks.push(inner);bads.push(outer);
        let mut late=arena_frame(&ready,5,&[0x8a,1,0,2],6);late.piggybacks.push(arena_frame(&ready,4,&[0x8a,1,0,1],6));bads.push(late);
        let mut ack=arena_frame(&ready,4,&[0x8a,1,0,1],7);ack.selective=vec![7];bads.push(ack);
        for bad in bads {let mut s=ready.clone();assert!(s.receive(&bad,t).is_err());unchanged_motion(&s,&ready);}
    }
    #[test] fn movement_whole_mixed_automatic_aim_is_bounded_and_never_applies_aiming() {
        let t=Instant::now();let mut s=movement_live(t);let mut mixed=vec![0x8f,12,0];mixed.extend([0;12]);mixed.extend([0x8a,1,0,1]);
        let mut events=Vec::new();s.receive_ready(&arena_frame(&s,4,&mixed,6),t,&mut events,0,&mut 32).unwrap();
        assert_eq!(s.arena_motion.as_ref().unwrap().aim_methods(),1);assert_eq!(s.arena_motion.as_ref().unwrap().move_methods(),1);assert_eq!(s.avatar_unsupported_envelopes,0);
        assert_eq!(events.iter().filter(|e|e.starts_with("ARENA_AIM_UNSUPPORTED ") && e.contains("domain_applied=false")).count(),1);
        assert_eq!(events.iter().filter(|e|e.starts_with("ARENA_MOVE_COMMAND ") && e.contains("action=started")).count(),1);
        let mut aim=vec![0x8e,8,0];aim.extend([0;8]);for sequence in 5..260 {s.receive(&arena_frame(&s,sequence,&aim,6),t).unwrap();}
        assert_eq!(s.arena_motion.as_ref().unwrap().aim_methods(),256);let before=s.clone();
        assert!(s.receive(&arena_frame(&s,260,&aim,6),t).is_err());unchanged_motion(&s,&before);assert_eq!(s.avatar_unsupported_envelopes,0);
    }
    #[test] fn movement_poll_queue_full_rolls_back_then_only_latest_tick_is_enqueued() {
        let t=Instant::now();let mut s=movement_live(t);s.receive(&arena_frame(&s,4,&[0x8a,1,0,1],6),t).unwrap();
        for _ in 0..8 {s.tx.enqueue().unwrap();s.tx.due(t,s.rx).unwrap();}
        let before=s.clone();let mut events=Vec::new();assert!(s.poll_movement(t+Duration::from_millis(2500),&mut events).is_err());unchanged_motion(&s,&before);assert!(events.is_empty());
        s.receive(&transport091::parse_interactive(&transport091::ack(7)).unwrap(),t+Duration::from_millis(2500)).unwrap();
        s.poll_movement(t+Duration::from_millis(2500),&mut events).unwrap();assert_eq!(s.tx.len(),8);assert_eq!(events.len(),1);
        assert!(events[0].contains("game_tick=1025 tick_low=1"));assert!(events[0].contains("displacement_m=2.000000000"));
    }
    #[test] fn movement_deadline_is_failure_cap_is_not_stop_and_position_retry_is_identical() {
        let t=Instant::now();let mut s=movement_live(t);s.receive(&arena_frame(&s,4,&[0x8a,1,0,1],6),t).unwrap();
        s.poll_movement(t+Duration::from_millis(2400),&mut Vec::new()).unwrap();let first=s.tx.due(t+Duration::from_millis(2400),s.rx).unwrap().unwrap();
        let retry=s.tx.due(t+Duration::from_millis(3200),s.rx).unwrap().unwrap();assert_eq!(first.0,retry.0);
        assert_eq!(transport091::parse_interactive(&first.2).unwrap().body,transport091::parse_interactive(&retry.2).unwrap().body);
        assert_eq!(s.arena_motion.as_ref().unwrap().phase(),crate::arena_movement091::Phase::Moving);
        let mut events=Vec::new();assert_eq!(s.poll_movement(t+Duration::from_secs(8),&mut events).unwrap(),Some("missing_stop"));
        assert!(events[0].contains("diagnostic_success=false"));assert_eq!(s.arena_motion.as_ref().unwrap().phase(),crate::arena_movement091::Phase::Failed);
    }
    #[test] fn movement_fixture_or_phase_mutation_and_time_regression_fail_before_commit() {
        let t=Instant::now();let ready=movement_live(t);
        for change in 0..9 {
            let mut s=ready.clone();match change {
                0=>s.arena_vehicle_seed.as_mut().unwrap().health=91,1=>s.arena_vehicle_seed.as_mut().unwrap().descriptor[0]^=1,
                2=>s.identity=arena_ready(t).identity,3=>s.hangar=arena_ready(t).hangar,4=>s.sync_mask=3,
                5=>s.arena_vehicle_creation=Some((6,false)),6=>s.arena_space=ArenaSpaceStage::Queued,
                7=>s.last_rx=t+Duration::from_secs(1),8=>s.outbox.push_back(vec![0xee]),_=>unreachable!(),
            }
            let before=s.clone();assert!(s.receive(&arena_frame(&s,4,&[0x8a,1,0,1],6),t).is_err(),"change{change}");unchanged_motion(&s,&before);
        }
        let mut s=ready;s.poll_movement(t+Duration::from_secs(1),&mut Vec::new()).unwrap();let before=s.clone();
        assert!(s.poll_movement(t,&mut Vec::new()).is_err());unchanged_motion(&s,&before);
    }
    #[test] fn movement_not_enabled_by_other_mode_or_early_flags_and_old_ready_stays_period2() {
        let t=Instant::now();let mut old=ready_waiting_compound(t);old.receive(&arena_frame(&old,3,&READY_COMPOUND,5),t).unwrap();
        old.tx.due(t,old.rx).unwrap();old.receive(&arena_frame(&old,4,&[0x8a,1,0,1],6),t).unwrap();
        assert!(!old.arena_movement);assert!(old.arena_motion.is_none());assert_eq!(old.avatar_unsupported_envelopes,1);
        assert!(old.arena_preparation.is_some());assert_eq!(old.poll_movement(t,&mut Vec::new()).unwrap(),None);
        let mut early=movement_waiting(t);let before=early.clone();assert!(early.receive(&arena_frame(&early,3,&[0x8a,1,0,1],5),t).is_err());unchanged_motion(&early,&before);
        assert!(early.arena_motion.is_none());
    }
    fn binding_waiting(now:Instant)->Session {
        let mut s=vehicle_ready(now);s.queue_arena_checkpoint(crate::arena_control091::Checkpoint::AvatarDrive).unwrap();
        assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,2);
        s.receive(&arena_frame(&s,1,&[9],3),now).unwrap();assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,3);
        s.receive(&arena_frame(&s,2,&[8,4,0,3,0,16,9],4),now).unwrap();assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,4);s
    }
    fn map_binding_body_with_ammo(s:&Session)->Vec<u8>{
        let mut body=crate::map_drive091::binding_body(crate::arena_vehicle091::VEHICLE_ENTITY_ID).unwrap();
         body.extend(crate::battle091::native_ammo::panel_bodies(
            s.arena_battle_preparation.as_ref().unwrap().loadout(),crate::arena_control091::AVATAR_ENTITY_ID).unwrap());
         body.extend(crate::battle091::native_ammo::selected_shell_body(
            s.arena_battle_preparation.as_ref().unwrap().loadout(),crate::arena_control091::AVATAR_ENTITY_ID).unwrap());
         body.extend(crate::battle091::native_ammo::initial_reload_body(
            s.arena_battle_preparation.as_ref().unwrap().loadout(),crate::arena_control091::AVATAR_ENTITY_ID).unwrap());body
    }
    fn binding_queued(now:Instant)->Session {
        let mut s=binding_waiting(now);s.receive(&arena_frame(&s,3,&READY_COMPOUND,5),now).unwrap();
        assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,5);s
    }
    fn unchanged_binding(s:&Session,b:&Session) {
        unchanged_motion(s,b);assert_eq!(s.map_drive,b.map_drive);assert_eq!(s.map_binding,b.map_binding);
    }
    #[test] fn binding_only_after_whole_ready_and_specific_create_ack() {
        let t=Instant::now();let ready=binding_waiting(t);
        let mut invalids=vec![arena_frame(&ready,3,&READY_COMPOUND,4)];
        for at in [0,7,11,18,19,22,32] {let mut wrong=READY_COMPOUND;wrong[at]^=1;invalids.push(arena_frame(&ready,3,&wrong,5));}
        let mut late=READY_COMPOUND.to_vec();late.push(7);invalids.push(arena_frame(&ready,3,&late,5));
        for f in invalids {let mut s=ready.clone();assert!(s.receive(&f,t).is_err());unchanged_binding(&s,&ready);}
        let mut s=ready;s.tx.enqueue().unwrap();assert_eq!(s.tx.due(t,s.rx).unwrap().unwrap().0,5);
        let mut valid=arena_frame(&s,3,&READY_COMPOUND,4);valid.selective=vec![4];
        s.receive(&valid,t).unwrap();assert_eq!(s.tx.len(),2);
        let sent=s.tx.due(t,s.rx).unwrap().unwrap();assert_eq!(sent.0,6);
        assert_eq!(transport091::parse_interactive(&sent.2).unwrap().body,map_binding_body_with_ammo(&s));
        assert_eq!(s.map_binding.as_ref().unwrap().force_sequence,6);assert_eq!(s.arena_vehicle_creation,Some((4,true)));
    }
    #[test] fn binding_ack6_requires_force_ack_but_not_empty_window_and_gates_forward() {
        let t=Instant::now();let mut s=binding_queued(t);let before=s.clone();
        assert!(s.receive(&arena_frame(&s,4,&[6],5),t).is_err());unchanged_binding(&s,&before);
        assert!(s.receive(&arena_frame(&s,4,&[0x8a,1,0,1],6),t).is_err());unchanged_binding(&s,&before);
        s.tx.enqueue().unwrap();assert_eq!(s.tx.due(t,s.rx).unwrap().unwrap().0,6);
        let mut valid=arena_frame(&s,4,&[6,0x8a,1,0,1],5);valid.selective=vec![5];s.receive(&valid,t).unwrap();
        assert_eq!(s.tx.len(),1);assert_eq!(s.map_binding.as_ref().unwrap().correction_acks(),1);
        assert_eq!(s.arena_motion.as_ref().unwrap().phase(),crate::arena_movement091::Phase::Moving);
        assert_eq!(s.avatar_unsupported_envelopes,0);
    }
    #[test] fn binding_reliable_retries_and_fresh_duplicate_ready_never_repeat_force() {
        let t=Instant::now();let mut s=binding_queued(t);
        let first=arena_frame(&s,4,&[6,0x8a,1,0,1],6);s.receive(&first,t).unwrap();let b=s.map_binding.clone();let m=s.arena_motion.clone();
        s.receive(&first,t+Duration::from_millis(50)).unwrap();assert_eq!(s.map_binding,b);assert_eq!(s.arena_motion,m);
        let mut bad=first.clone();bad.body[5]=7;let before=s.clone();assert!(s.receive(&bad,t+Duration::from_millis(50)).is_err());unchanged_binding(&s,&before);
        s.receive(&arena_frame(&s,5,&READY_COMPOUND,6),t+Duration::from_millis(100)).unwrap();assert_eq!(s.map_binding,b);assert_eq!(s.arena_motion,m);assert_eq!(s.tx.len(),0);
        s.receive(&arena_frame(&s,6,&[6],6),t+Duration::from_millis(150)).unwrap();assert_eq!(s.map_binding.as_ref().unwrap().correction_acks(),2);assert_eq!(s.arena_motion,m);assert_eq!(s.tx.len(),0);
    }
    #[test] fn binding_late_bad_method_and_piggyback_roll_back_ack_correction_and_motion() {
        let t=Instant::now();let ready=binding_queued(t);
        let mut invalids=vec![arena_frame(&ready,4,&[6,0x8a,1,0,1,7,3,0,16,9],6),arena_frame(&ready,4,&[7,3,0,16,9],6),arena_frame(&ready,4,&[6,0],6)];
        let mut bad=arena_frame(&ready,5,&[0xee],6);bad.piggybacks.push(arena_frame(&ready,4,&[6,0x8a,1,0,1],6));invalids.push(bad);
        let mut bad=arena_frame(&ready,5,&[],6);bad.body[1]^=1;bad.piggybacks.push(arena_frame(&ready,4,&[6],6));invalids.push(bad);
        for f in invalids {let mut s=ready.clone();assert!(s.receive(&f,t).is_err());unchanged_binding(&s,&ready);}
    }
    #[test] fn binding_full_window_rolls_back_ready_then_keeps_the_exact_new_sequence() {
        let t=Instant::now();let mut s=binding_waiting(t);
        s.receive(&transport091::parse(&transport091::ack(5)).unwrap(),t).unwrap();
        for _ in 0..8 {s.tx.enqueue().unwrap();s.tx.due(t,s.rx).unwrap();}
        let before=s.clone();assert!(s.receive(&arena_frame(&s,3,&READY_COMPOUND,5),t).is_err());
        unchanged_binding(&s,&before);assert!(s.map_binding.is_none());assert!(s.arena_motion.is_none());
        // Selectively freeing a heartbeat permits one exact new body. It does
        // not renumber any already sent body or recycle the failed allocation.
        let mut retry=arena_frame(&s,3,&READY_COMPOUND,5);retry.selective=vec![5];
        s.receive(&retry,t).unwrap();assert_eq!(s.tx.len(),8);
        assert_eq!(s.map_binding.as_ref().unwrap().force_sequence,13);
        let sent=s.tx.due(t,s.rx).unwrap().unwrap();assert_eq!(sent.0,13);
        assert_eq!(transport091::parse_interactive(&sent.2).unwrap().body,map_binding_body_with_ammo(&s));
    }
    #[test] fn binding_unsent_force_ack_and_forward_before_correction_cannot_commit() {
        let t=Instant::now();let mut s=binding_waiting(t);
        s.receive(&arena_frame(&s,3,&READY_COMPOUND,5),t).unwrap();let before=s.clone();
        assert!(s.receive(&arena_frame(&s,4,&[6],6),t).is_err());unchanged_binding(&s,&before);
        assert_eq!(s.tx.due(t,s.rx).unwrap().unwrap().0,5);let before=s.clone();
        // A late valid ACK6 cannot retroactively authorize an earlier forward.
        assert!(s.receive(&arena_frame(&s,4,&[0x8a,1,0,1,6],6),t).is_err());unchanged_binding(&s,&before);
        s.receive(&arena_frame(&s,4,&[6,0x8a,1,0,1],6),t).unwrap();
        assert!(s.map_binding.as_ref().unwrap().correction_acknowledged());
        assert_eq!(s.arena_motion.as_ref().unwrap().move_methods(),1);
    }
    #[test] fn binding_ignored_player_telemetry_cannot_move_authoritative_state() {
        let t=Instant::now();let mut s=binding_queued(t);
        let mut b=vec![6,2];for v in [99999f32,-99999f32,12345f32]{b.extend(v.to_le_bytes());}b.extend([255,255,255,255]);
        s.receive(&arena_frame(&s,4,&b,6),t).unwrap();assert_eq!(s.map_binding.as_ref().unwrap().player_telemetry(),1);
        assert_eq!(s.arena_motion.as_ref().unwrap().position(t),crate::arena_movement091::POSITION);
        assert_eq!(s.arena_motion.as_ref().unwrap().move_methods(),0);assert_eq!(s.avatar_unsupported_envelopes,0);
        let before=s.clone();let mut ward=vec![4];ward.extend([0;19]);assert!(s.receive(&arena_frame(&s,5,&ward,6),t).is_err());unchanged_binding(&s,&before);
    }
    #[test] fn binding_publications_share_pose_speed_and_retry_bytes_with_atomic_full_queue() {
        let t=Instant::now();let mut s=binding_queued(t);s.receive(&arena_frame(&s,4,&[6,0x8a,1,0,1],6),t).unwrap();
        let mut events=Vec::new();s.poll_movement(t+Duration::from_secs(1),&mut events).unwrap();
        let sent=s.tx.due(t+Duration::from_secs(1),s.rx).unwrap().unwrap();let b=transport091::parse_interactive(&sent.2).unwrap().body;
        assert_eq!(b.len(),65);assert_eq!(&b[7..19],&b[33..45]);assert_eq!(&b[57..61],&1f32.to_le_bytes());assert!(events[0].starts_with("MAP_DRIVE_POSITION_QUEUED "));
        let retry=s.tx.due(t+Duration::from_millis(1800),s.rx).unwrap().unwrap();assert_eq!(sent.0,retry.0);assert_eq!(transport091::parse_interactive(&retry.2).unwrap().body,b);
        s.receive(&arena_frame(&s,5,&[0x8a,1,0,0],7),t+Duration::from_secs(2)).unwrap();
        s.poll_movement(t+Duration::from_secs(3),&mut Vec::new()).unwrap();let b=transport091::parse_interactive(&s.tx.due(t+Duration::from_secs(3),s.rx).unwrap().unwrap().2).unwrap().body;
        assert_eq!(&b[57..],&[0;8]);
        for _ in 0..7 {s.tx.enqueue().unwrap();s.tx.due(t+Duration::from_secs(3),s.rx).unwrap();}
        let before=s.clone();events.clear();assert!(s.poll_movement(t+Duration::from_millis(3400),&mut events).is_err());unchanged_binding(&s,&before);assert!(events.is_empty());
    }
    #[test] fn binding_cannot_weaken_old_modes_or_bypass_fixture_or_channel_guards() {
        let t=Instant::now();let mut old=movement_live(t);assert!(!old.map_drive);assert!(old.map_binding.is_none());
        assert!(old.queue_map_binding(t).is_err());old.receive(&arena_frame(&old,4,&[6],6),t).unwrap();assert!(old.map_binding.is_none());
        assert_eq!(old.avatar_unsupported_envelopes,1);assert_eq!(old.arena_motion.as_ref().unwrap().move_methods(),0);
        let ready=binding_queued(t);
        for change in 0..6 {
            let mut s=ready.clone();match change {0=>s.arena_vehicle_seed.as_mut().unwrap().health=91,
                1=>s.hangar=arena_ready(t).hangar,2=>s.sync_mask=3,3=>s.map_binding=None,
                4=>s.last_rx=t+Duration::from_secs(1),5=>s.outbox.push_back(vec![1]),_=>unreachable!()}
            let before=s.clone();assert!(s.receive(&arena_frame(&s,4,&[6],6),t).is_err());unchanged_binding(&s,&before);
        }
    }

    fn drive_idle(now:Instant)->Session {
        let mut s=vehicle_ready(now);s.drive=Some(crate::map_drive_world091::Arena::new(now));
        s.drive_account_policy=crate::map_drive_service091::AccountPolicy::for_mode(true,s.identity.as_ref().unwrap(),s.hangar.as_ref().unwrap()).unwrap().map(Arc::new);s
    }
    fn drive_join_packet(command:i16)->Vec<u8>{
        let mut b=vec![0x8e,20,0,202,0];b.extend(command.to_le_bytes());b.extend((if command==700{1i64}else{0}).to_le_bytes());
        b.extend((if command==700{7i32}else{0}).to_le_bytes());b.extend(0i32.to_le_bytes());b
    }
    fn drive_enabled(now:Instant)->Session {
        use crate::{map_drive_world091 as world,map_drive_worker091 as ipc};
        let mut s=drive_idle(now);s.arena_vehicle_seed=Some(crate::arena_vehicle091::load(s.identity.as_ref().unwrap(),s.hangar.as_ref().unwrap().state_sha256()).unwrap());
        let d=s.drive.as_mut().unwrap();d.join(now).unwrap();d.phase=world::Phase::Enable;d.map=Some(ipc::tests::map());
        s.arena_battle_preparation=Some(crate::battle091::preparation::prepare_primary_ms1(
            s.arena_vehicle_seed.as_ref().unwrap(),s.identity.as_ref().unwrap(),s.hangar.as_ref().unwrap().state_sha256(),d.generation).unwrap());
        s.arena_fire=Some(crate::battle091::fire::State::new());
        d.pose=Some(ipc::Pose{position:[0.,10.,0.],direction:[0.;3],speed:0.,rspeed:0.,contacts:6,
            linear_velocity:[0.;3],angular_velocity:[0.;3],wheel_contact_masks:[63;6]});
        s.arena_base=true;s
    }
    fn drive_ready(now:Instant)->Session {
        let mut s=drive_enabled(now);s.receive(&arena_frame(&s,1,&[9],2),now).unwrap();s.tx.due(now,s.rx).unwrap();
        s.receive(&arena_frame(&s,2,&[8,4,0,3,0,16,9],3),now).unwrap();s.tx.due(now,s.rx).unwrap();s
    }
    fn drive_live(now:Instant)->Session {
        let mut s=drive_ready(now);s.receive(&arena_frame(&s,3,&READY_COMPOUND,4),now).unwrap();s.tx.due(now,s.rx).unwrap();s
    }
    fn drive_same(a:&Session,b:&Session){assert_eq!(arena_stamp(a),arena_stamp(b));assert_eq!(a.drive,b.drive);
        assert_eq!(a.arena_battle_preparation,b.arena_battle_preparation);
        assert_eq!(a.map_binding,b.map_binding);assert_eq!(a.drive_account_policy,b.drive_account_policy);
        assert_eq!(a.drive_return_account,b.drive_return_account);assert_eq!(a.chat_request_ids,b.chat_request_ids);
        assert_eq!(a.unsupported_request_ids,b.unsupported_request_ids);assert_eq!(a.account_cache_hash,b.account_cache_hash);
        assert_eq!(a.received,b.received);assert_eq!(a.outbox,b.outbox);assert_eq!(a.request_ids,b.request_ids);}
    const RIDE03_QUEUE_INFO:[u8;23]=[0x8e,20,0,202,0,246,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0];
    fn drive_queued(t:Instant)->Session{
        let mut s=drive_idle(t);s.receive(&arena_frame(&s,1,&drive_join_packet(700),2),t).unwrap();
        s.tx.due(t,s.rx).unwrap();s.receive(&transport091::parse(&transport091::ack(3)).unwrap(),t).unwrap();s
    }
    #[test]fn drive_join_requires_domain_loadout_and_records_only_server_diagnostic(){
        let t=Instant::now();let mut s=drive_idle(t);let before=s.clone();
        let mut events=Vec::new();
        s.receive_ready(&arena_frame(&s,1,&drive_join_packet(700),2),t,&mut events,0,&mut 32).unwrap();
        assert_eq!(s.drive.as_ref().unwrap().phase,crate::map_drive_world091::Phase::Queued);
        let preparation=s.arena_battle_preparation.as_ref().unwrap();
        assert_eq!((preparation.loadout().turret_compact_descr,preparation.loadout().gun_compact_descr,
            preparation.loadout().selected_shell_compact_descr,preparation.loadout().selected_shell_count),
            (5891,5892,2570,20));
        assert_eq!(events.iter().filter(|e|e.starts_with("BATTLE_LOADOUT_DOMAIN_READY ")
            && e.contains("native_event=false") && e.contains("native_packet=false")
            && e.contains("hud=false") && e.contains("ammo_mutation=false")).count(),1);
        assert!(s.arena_battle_preparation.is_some());assert!(before.arena_battle_preparation.is_none());
        assert_eq!(s.hangar.as_ref().unwrap().state_sha256(),before.hangar.as_ref().unwrap().state_sha256());
    }
    #[test] fn native_fire_route_consumes_one_ap_queues_reload_callbacks_and_rejects_cooldown() {
        let now=Instant::now();let mut s=ready_waiting_compound(now);
        s.receive(&arena_frame(&s,3,&READY_COMPOUND,5),now).unwrap();
        let fire=[crate::battle091::fire::VEHICLE_SHOOT,0,0];
        s.receive(&arena_frame(&s,4,&fire,5),now).unwrap();
        assert_eq!(s.arena_fire.as_ref().unwrap().ammo(),19);
        let preparation=s.tx.due(now,s.rx).unwrap().unwrap();
        assert_eq!(transport091::parse_interactive(&preparation.2).unwrap().body.len(),105);
        s.receive(&transport091::parse_interactive(&transport091::ack(preparation.0+1)).unwrap(),now).unwrap();
        let callback=s.tx.due(now,s.rx).unwrap().unwrap();
        assert_eq!(transport091::parse_interactive(&callback.2).unwrap().body,
            crate::battle091::fire::accepted_shot_body(19,crate::arena_vehicle091::VEHICLE_ENTITY_ID).unwrap());
        s.receive(&arena_frame(&s,5,&fire,callback.0+1),now+Duration::from_millis(1)).unwrap();
        assert_eq!(s.arena_fire.as_ref().unwrap().ammo(),19);
        let mut reload_events=Vec::new();
        s.poll_battle_reload(now+Duration::from_secs_f32(crate::battle091::fire::MS1_RELOAD_SECONDS),&mut reload_events).unwrap();
        assert_eq!(reload_events.iter().filter(|e|e.starts_with("BATTLE_RELOAD_COMPLETE ") && e.contains("time_left=0.0") && e.contains("body_bytes=14")).count(),1);
        let completed=s.tx.due(now+Duration::from_secs_f32(crate::battle091::fire::MS1_RELOAD_SECONDS),s.rx).unwrap().unwrap();
        assert_eq!(transport091::parse_interactive(&completed.2).unwrap().body,
            crate::battle091::fire::completed_reload_body(crate::arena_vehicle091::VEHICLE_ENTITY_ID).unwrap());
        s.receive(&transport091::parse_interactive(&transport091::ack(completed.0+1)).unwrap(),now+Duration::from_secs_f32(crate::battle091::fire::MS1_RELOAD_SECONDS)).unwrap();
        s.receive(&arena_frame(&s,6,&fire,completed.0+1),now+Duration::from_secs_f32(crate::battle091::fire::MS1_RELOAD_SECONDS)+Duration::from_millis(1)).unwrap();
        assert_eq!(s.arena_fire.as_ref().unwrap().ammo(),18);
        let before=s.clone();let malformed=[crate::battle091::fire::VEHICLE_SHOOT,1,0];
        assert!(s.receive(&arena_frame(&s,7,&malformed,completed.0+1),now).is_err());
        assert_eq!(arena_stamp(&s),arena_stamp(&before));assert_eq!(s.arena_fire,before.arena_fire);
    }
    #[test]fn map_drive_avatar_binding_appends_native_ammo_candidate(){
        let t=Instant::now();let mut s=drive_ready(t);let binding=crate::map_drive_world091::binding(
            1,s.drive.as_ref().unwrap().pose.as_ref().unwrap()).unwrap();
        let ready=arena_frame(&s,3,&READY_COMPOUND,4);let mut events=Vec::new();
        s.receive_ready(&ready,t,&mut events,0,&mut 32).unwrap();
        let sent=s.tx.due(t,s.rx).unwrap().unwrap();let body=transport091::parse_interactive(&sent.2).unwrap().body;
        assert_eq!(&body[..122],binding.as_slice());
         assert_eq!(&body[122..],[
             0x13,0x44,0x0a,0x0a,0,0,20,0,0,0,0,
             0x13,0x44,0x0a,0x0b,0,0,0,0,0,0,0,
             0x13,0x44,0x0a,0x0c,0,0,0,0,0,0,0,
             0x13,0x40,0,0x0a,0x0a,0,0,
             0x13,0x46,0x03,0x00,0x10,0x09,0,0,0,0,0,0,0x20,0x40,
         ]);assert_eq!(body.len(),176);
         assert_eq!(s.map_binding.as_ref().unwrap().force_sequence,sent.0);
         assert_eq!(events.iter().filter(|e|e.starts_with("MAP_DRIVE_BOUND ") && e.contains("body_bytes=176") && e.contains("native_ammo_panel_appended=true") && e.contains("native_selected_shell_appended=true") && e.contains("native_initial_reload_appended=true")).count(),1);
         assert_eq!(events.iter().filter(|e|e.starts_with("BATTLE_NATIVE_AMMO_PANEL_CANDIDATE ") && e.contains("route=drive_avatar") && e.contains("panel_count=3") && e.contains("native_receipt=NOT_RUN")).count(),1);
    }
    #[test]fn map_drive_avatar_fire_consumes_server_owned_ap_and_emits_native_callbacks(){
        let t=Instant::now();let mut s=drive_live(t);
        let fire=[crate::battle091::fire::VEHICLE_SHOOT,0,0];
        s.receive(&arena_frame(&s,4,&fire,5),t).unwrap();
        assert_eq!(s.arena_fire.as_ref().unwrap().ammo(),19);
        let sent=s.tx.due(t,s.rx).unwrap().unwrap();
        assert_eq!(transport091::parse_interactive(&sent.2).unwrap().body,
            crate::battle091::fire::accepted_shot_body(19,crate::arena_vehicle091::VEHICLE_ENTITY_ID).unwrap());
    }
    #[test]fn ordinary_ready_queues_ammo_after_binding_once_and_retries_identical_body(){
        let t=Instant::now();let mut s=binding_waiting(t);
        let binding=crate::map_drive091::binding_body(crate::arena_vehicle091::VEHICLE_ENTITY_ID).unwrap();
        let before_state=s.hangar.as_ref().unwrap().state_sha256();let mut events=Vec::new();
        let ready=arena_frame(&s,3,&READY_COMPOUND,5);
        s.receive_ready(&ready,t,&mut events,0,&mut 32).unwrap();
         assert_eq!(events.iter().filter(|e|e.starts_with("BATTLE_NATIVE_AMMO_PANEL_CANDIDATE ")
             && e.contains("route=ordinary_map_drive") && e.contains("native_receipt=NOT_RUN")).count(),1);
         let first=s.tx.due(t,s.rx).unwrap().unwrap();let body=transport091::parse_interactive(&first.2).unwrap().body;
         assert_eq!(&body[..122],binding.as_slice());assert_eq!(&body[122..],&[
             0x13,0x44,0x0a,0x0a,0,0,20,0,0,0,0,
             0x13,0x44,0x0a,0x0b,0,0,0,0,0,0,0,
             0x13,0x44,0x0a,0x0c,0,0,0,0,0,0,0,
             0x13,0x40,0,0x0a,0x0a,0,0,
             0x13,0x46,0x03,0x00,0x10,0x09,0,0,0,0,0,0,0x20,0x40,
         ]);
         assert_eq!(body.len(),176);assert_eq!(s.map_binding.as_ref().unwrap().force_sequence,first.0);
        // Retransmitted native ready is deduplicated before domain dispatch.
        events.clear();s.receive_ready(&ready,t,&mut events,0,&mut 32).unwrap();
         assert!(!events.iter().any(|e|e.starts_with("BATTLE_NATIVE_AMMO_PANEL_CANDIDATE ")));assert_eq!(s.tx.len(),1);
        let retry=s.tx.due(t+crate::transport091::RETRY,s.rx).unwrap().unwrap();assert_eq!(retry.0,first.0);
        assert_eq!(transport091::parse_interactive(&retry.2).unwrap().body,body);
        // A second ready in a new sequence is an explicit no-op as well.
        events.clear();s.receive_ready(&arena_frame(&s,4,&READY_COMPOUND,6),t+crate::transport091::RETRY,&mut events,0,&mut 32).unwrap();
        assert!(events.iter().any(|e|e.starts_with("ARENA_READY_DUPLICATE ")));
         assert!(!events.iter().any(|e|e.starts_with("BATTLE_NATIVE_AMMO_PANEL_CANDIDATE ")));assert_eq!(s.tx.len(),0);
        assert_eq!(s.hangar.as_ref().unwrap().state_sha256(),before_state);
    }
    #[test]fn queue_info_reply_commits_once_and_blocks_reset_until_its_delivery(){
        let t=Instant::now();let mut s=drive_queued(t);let before_state=s.hangar.as_ref().unwrap().state_sha256();
        let f=arena_frame(&s,2,&RIDE03_QUEUE_INFO,3);s.receive(&f,t).unwrap();
        assert_eq!(s.drive.as_ref().unwrap().queue_info_requests,1);assert_eq!(s.rx,3);assert!(!s.ready_for_arena_base());
        s.receive(&f,t).unwrap();assert_eq!(s.drive.as_ref().unwrap().queue_info_requests,1);assert_eq!(s.tx.len(),1);
        let sent=s.tx.due(t,s.rx).unwrap().unwrap();assert_eq!(sent.0,3);
        assert_eq!(transport091::parse_interactive(&sent.2).unwrap().body,crate::map_drive_world091::own_queue_info());
        assert!(!s.ready_for_arena_base());s.receive(&transport091::parse(&transport091::ack(4)).unwrap(),t).unwrap();
        assert!(s.ready_for_arena_base());assert_eq!(s.hangar.as_ref().unwrap().state_sha256(),before_state);
    }
    #[test]fn ride03_poll_then_heartbeats_then_enable_preserves_native_order(){
        let t=Instant::now();let mut s=drive_queued(t);
        for seq in 2..6{s.receive(&arena_frame(&s,seq,&[],3),t).unwrap();}
        // Real failed reliable6 payload, followed by native7/8 heartbeat and9 enable.
        s.receive(&arena_frame(&s,6,&RIDE03_QUEUE_INFO,3),t).unwrap();s.tx.due(t,s.rx).unwrap();
        s.receive(&transport091::parse(&transport091::ack(4)).unwrap(),t).unwrap();
        let ready=drive_enabled(t);s.drive=ready.drive;s.drive.as_mut().unwrap().queue_info_requests=1;
        s.arena_base=true;
        for seq in [7,8]{s.receive(&arena_frame(&s,seq,&[],4),t).unwrap();}
        s.receive(&arena_frame(&s,9,&[9],4),t).unwrap();
        assert_eq!(s.rx,10);assert_eq!(s.drive.as_ref().unwrap().phase,crate::map_drive_world091::Phase::EntityRequest);
        let sent=s.tx.due(t,s.rx).unwrap().unwrap();assert_eq!(sent.0,4);
        assert_eq!(transport091::parse_interactive(&sent.2).unwrap().body.len(),221);
    }
    #[test]fn queue_info_crossing_reset_is_drained_without_account_reply(){
        let t=Instant::now();let mut s=drive_enabled(t);let tx=s.tx.len();
        let f=arena_frame(&s,1,&RIDE03_QUEUE_INFO,2);s.receive(&f,t).unwrap();
        assert_eq!(s.tx.len(),tx);assert!(s.outbox.is_empty());assert_eq!(s.drive.as_ref().unwrap().queue_info_requests,1);
        s.receive(&f,t).unwrap();assert_eq!(s.drive.as_ref().unwrap().queue_info_requests,1);
        s.receive(&arena_frame(&s,2,&[],2),t).unwrap();s.receive(&arena_frame(&s,3,&[9],2),t).unwrap();
        let sent=s.tx.due(t,s.rx).unwrap().unwrap();assert_eq!(transport091::parse_interactive(&sent.2).unwrap().body.len(),221);
    }
    #[test]fn queue_info_and_enable_in_one_envelope_or_piggybacks_are_atomic(){
        let t=Instant::now();let ready=drive_enabled(t);let mut b=RIDE03_QUEUE_INFO.to_vec();b.push(9);
        let mut s=ready.clone();s.receive(&arena_frame(&s,1,&b,2),t).unwrap();assert_eq!(s.tx.len(),1);
        assert_eq!(s.drive.as_ref().unwrap().queue_info_requests,1);assert_eq!(s.drive.as_ref().unwrap().phase,crate::map_drive_world091::Phase::EntityRequest);
        let mut s=ready.clone();let mut f=arena_frame(&s,2,&[9],2);f.piggybacks.push(arena_frame(&s,1,&RIDE03_QUEUE_INFO,2));
        s.receive(&f,t).unwrap();assert_eq!(s.rx,3);assert_eq!(s.tx.len(),1);
        let mut s=ready.clone();let mut bad=arena_frame(&s,3,&[0xee],2);bad.piggybacks.push(f);
        assert!(s.receive(&bad,t).is_err());drive_same(&s,&ready);
        let mut s=ready.clone();b.push(0xee);assert!(s.receive(&arena_frame(&s,1,&b,2),t).is_err());drive_same(&s,&ready);
    }
    #[test]fn queue_info_queued_late_poison_and_wrong_token_roll_back_reply_and_ack(){
        let t=Instant::now();let ready=drive_queued(t);let mut s=ready.clone();
        let mut b=RIDE03_QUEUE_INFO.to_vec();b.extend([255,1,0,0]);assert!(s.receive(&arena_frame(&s,2,&b,3),t).is_err());drive_same(&s,&ready);
        let mut f=arena_frame(&s,3,&[255],3);f.piggybacks.push(arena_frame(&s,2,&RIDE03_QUEUE_INFO,3));
        assert!(s.receive(&f,t).is_err());drive_same(&s,&ready);
        let mut f=arena_frame(&s,2,&RIDE03_QUEUE_INFO,3);f.body[1]^=1;assert!(s.receive(&f,t).is_err());drive_same(&s,&ready);
    }
    #[test]fn queue_info_does_not_open_other_phases_or_old_interactive_mode(){
        let t=Instant::now();let mut idle=drive_idle(t);let before=idle.clone();assert!(idle.receive(&arena_frame(&idle,1,&RIDE03_QUEUE_INFO,2),t).is_err());drive_same(&idle,&before);
        let mut old=vehicle_ready(t);let before=old.clone();assert!(old.receive(&arena_frame(&old,1,&RIDE03_QUEUE_INFO,2),t).is_err());drive_same(&old,&before);
        let mut entry=drive_enabled(t);entry.receive(&arena_frame(&entry,1,&[9],2),t).unwrap();entry.tx.due(t,entry.rx).unwrap();
        let before=entry.clone();assert!(entry.receive(&arena_frame(&entry,2,&RIDE03_QUEUE_INFO,3),t).is_err());drive_same(&entry,&before);
        let mut driving=drive_live(t);let before=driving.clone();assert!(driving.receive(&arena_frame(&driving,4,&RIDE03_QUEUE_INFO,5),t).is_err());drive_same(&driving,&before);
    }
    #[test]fn queue_info_counter_capacity_and_fixture_guards_do_not_partially_commit(){
        let t=Instant::now();for stale in [false,true]{for change in 0..4{
            let mut s=if stale{drive_enabled(t)}else{drive_queued(t)};
            match change{0=>s.drive.as_mut().unwrap().queue_info_requests=32,1=>s.sync_mask=3,
                2=>s.arena_vehicle_seed.as_mut().unwrap().health=91,3=>s.identity=None,_=>unreachable!()}
            let before=s.clone();let seq=s.rx;let ack=if stale{2}else{3};assert!(s.receive(&arena_frame(&s,seq,&RIDE03_QUEUE_INFO,ack),t).is_err());drive_same(&s,&before);
        }}
        let mut s=drive_queued(t);for _ in 0..128{s.outbox.push_back(vec![1]);}let before=s.clone();
        assert!(s.receive(&arena_frame(&s,2,&RIDE03_QUEUE_INFO,3),t).is_err());drive_same(&s,&before);
        let mut s=drive_enabled(t);for _ in 0..8{s.tx.enqueue().unwrap();s.tx.due(t,s.rx).unwrap();}
        let before=s.clone();let mut b=RIDE03_QUEUE_INFO.to_vec();b.push(9);
        assert!(s.receive(&arena_frame(&s,1,&b,2),t).is_err());drive_same(&s,&before);
    }
    fn policy_cold(now:Instant)->Session {
        let mut s=drive_idle(now);s.sync_mask=0;s.request_ids.clear();s.account_cache_hash=None;s
    }
    #[test]fn ordinary_policy_auth_preparation_is_explicit_and_before_session_publication() {
        let (i,f)=crate::map_drive_service091::tests::actual();let a=Authenticated::new(i,f,true).unwrap();
        assert!(a.drive_account_policy.is_some());assert_eq!(format!("{:x}",Sha256::digest(a.fixtures.state_bytes())),crate::arena_vehicle091::PRIMARY_STATE_SHA256);
        let (i,f)=crate::map_drive_service091::tests::actual();assert!(Authenticated::new(i,f,false).unwrap().drive_account_policy.is_none());
        let (mut i,f)=crate::map_drive_service091::tests::actual();i.database_id=2;assert!(Authenticated::new(i,f,true).is_err());
        let (mut i,f)=crate::map_drive_service091::tests::actual();i.fixture_dir.pop();i.fixture_dir.push("r3-catalog3");assert!(Authenticated::new(i,f,true).is_err());
    }
    #[test]fn ordinary_cached_zero_or_other_crc_receives_projected_full_stream_before_show_gui() {
        let t=Instant::now();
        for hint in [0,51539670,-1176871600] {
            let mut s=policy_cold(t);let mut payload=warm_packet(221,100,0,hint,0);
            payload.extend(warm_packet(222,300,0,518,-846328027));payload.extend(warm_packet(223,600,1,1791128141,0));
            let frame=arena_frame(&s,1,&payload,2);let before_source=s.hangar.as_ref().unwrap().state_sha256();
            s.receive(&frame,t).unwrap();assert_eq!(s.sync_mask,7);assert_eq!(s.tx.len(),8);assert!(s.outbox.is_empty());
            assert_eq!(s.hangar.as_ref().unwrap().state_sha256(),before_source);let p=s.drive_account_policy.clone();
            let mut bodies=Vec::new();while let Some((_,_,raw))=s.tx.due(t,s.rx).unwrap(){bodies.push(transport091::parse_interactive(&raw).unwrap().body);}
            let actual=crate::map_drive_service091::tests::assembled(&bodies[..4],221);
            assert_eq!(format!("{:x}",Sha256::digest(&actual)),crate::map_drive_service091::OUTGOING_STATE_SHA256);
            assert_eq!(actual[802],1);assert_eq!(s.hangar.as_ref().unwrap().state_bytes()[802],0);
            assert_eq!(&bodies[4..6],crate::hangar091::response(&crate::account091::Request{id:222,command:300},s.hangar.as_ref().unwrap()).unwrap());
            assert_eq!(&bodies[6..7],crate::hangar091::response(&crate::account091::Request{id:223,command:600},s.hangar.as_ref().unwrap()).unwrap());
            assert_eq!(bodies[7],crate::hangar091::show_gui(1).unwrap());
            s.receive(&frame,t).unwrap();assert_eq!(s.drive_account_policy,p);assert_eq!(s.tx.len(),8); // exact duplicate only
        }
    }
    #[test]fn old_interactive_and_probe_initial_account_streams_remain_byte_identical() {
        use crate::arena_control091::Checkpoint;
        let t=Instant::now();for checkpoint in [Checkpoint::AvatarBase,Checkpoint::AvatarSpace,Checkpoint::AvatarVehicle,
            Checkpoint::AvatarReady,Checkpoint::AvatarMovement,Checkpoint::AvatarDrive] {
            let mut s=policy_cold(t);s.drive=None;s.drive_account_policy=None;
            // Actual old modes acquire Avatar flags only AFTER the Account
            // initial sync/GUI, outbox and reliable ACK barrier are complete.
            let mut payload=warm_packet(221,100,0,51539670,0);
            payload.extend(warm_packet(222,300,0,518,-846328027));payload.extend(warm_packet(223,600,1,1791128141,0));
            s.receive(&arena_frame(&s,1,&payload,2),t).unwrap();
            let mut bodies=Vec::new();while let Some((_,_,raw))=s.tx.due(t,s.rx).unwrap(){bodies.push(transport091::parse_interactive(&raw).unwrap().body);}
            let mut expected=Vec::new();for (id,command) in [(221,100),(222,300),(223,600)] {
                expected.extend(crate::hangar091::response(&crate::account091::Request{id,command},s.hangar.as_ref().unwrap()).unwrap());}
            expected.push(crate::hangar091::show_gui(1).unwrap());assert_eq!(bodies,expected);
            assert_eq!(format!("{:x}",Sha256::digest(bodies[..4].concat())),"99f2994e6924fc0f29fb9bceae918e017d0ffc662f3fdf7e9e8992be2767de8f");
            assert!(!s.arena_movement && !s.map_drive && !s.arena_base);
            s.receive(&transport091::parse(&transport091::ack(10)).unwrap(),t).unwrap();
            s.queue_arena_checkpoint(checkpoint).unwrap();assert!(s.arena_base);assert!(s.drive_account_policy.is_none());
        }
    }
    #[test]fn ordinary_policy_does_not_silently_fallback_or_escape_its_mode_or_fixture() {
        let t=Instant::now();let ready=policy_cold(t);
        for change in 0..4 {let mut s=ready.clone();match change {0=>s.drive_account_policy=None,1=>s.drive=None,
            2=>s.hangar=arena_ready(t).hangar,3=>s.identity=arena_ready(t).identity,_=>unreachable!()}
            let before=s.clone();assert!(s.receive(&arena_frame(&s,1,&warm_packet(221,100,0,0,0),2),t).is_err());drive_same(&s,&before);
        }
    }
    #[test]fn ordinary_policy_late_bad_bundle_and_piggyback_roll_back_stream_and_cache_commit() {
        let t=Instant::now();let ready=policy_cold(t);let good=warm_packet(221,100,0,51539670,0);
        let mut bad=good.clone();bad.extend([255]);let mut parent=arena_frame(&ready,2,&[255],2);
        parent.piggybacks.push(arena_frame(&ready,1,&good,2));
        for frame in [arena_frame(&ready,1,&bad,2),parent] {let mut s=ready.clone();assert!(s.receive(&frame,t).is_err());
            drive_same(&s,&ready);assert_eq!(s.account_cache_hash,ready.account_cache_hash);assert_eq!(s.hangar.as_ref().unwrap().state_sha256(),ready.hangar.as_ref().unwrap().state_sha256());}
        let mut full=ready.clone();for _ in 0..128 {full.outbox.push_back(vec![1]);}let before=full.clone();
        assert!(full.receive(&arena_frame(&full,1,&good,2),t).is_err());drive_same(&full,&before);assert_eq!(full.account_cache_hash,None);
    }
    #[test]fn warm_no_change_keeps_projected_counter_and_original_seed_source() {
        let t=Instant::now();let mut s=drive_returning(t);let policy=s.drive_account_policy.clone();let source=s.hangar.as_ref().unwrap().state_sha256();
        s.receive(&arena_frame(&s,6,&warm_packet(227,100,1,98765,0),6),t).unwrap();
        let body=transport091::parse_interactive(&s.tx.due(t,s.rx).unwrap().unwrap().2).unwrap().body;
        assert_eq!(body,crate::hangar091::response_refresh(&crate::account091::Request{id:227,command:100}).unwrap());
        assert_eq!(s.drive_account_policy,policy);assert_eq!(s.hangar.as_ref().unwrap().state_sha256(),source);
        let p=s.ordinary_account_policy().unwrap().unwrap();let raw=crate::map_drive_service091::tests::assembled(
            &p.response(&crate::account091::Request{id:221,command:100},s.identity.as_ref().unwrap(),s.hangar.as_ref().unwrap()).unwrap(),221);
        assert_eq!(raw[802],1);crate::arena_vehicle091::load(s.identity.as_ref().unwrap(),source).unwrap();
        let before=s.clone();assert!(s.receive(&arena_frame(&s,7,&warm_packet(230,100,1,98766,0),7),t).is_err());drive_same(&s,&before);
    }
    #[test]fn ordinary_queue_requires_owned_fixture_and_commits_once_with_no_worker_side_effect(){
        let t=Instant::now();let mut s=drive_idle(t);let f=arena_frame(&s,1,&drive_join_packet(700),2);
        s.receive(&f,t).unwrap();assert_eq!(s.drive.as_ref().unwrap().generation,1);assert_eq!(s.drive.as_ref().unwrap().phase,crate::map_drive_world091::Phase::Queued);
        assert_eq!(s.tx.len(),1);assert!(s.drive.as_ref().unwrap().pose.is_none());s.receive(&f,t).unwrap();assert_eq!(s.drive.as_ref().unwrap().generation,1);
        let before=s.clone();assert!(s.receive(&arena_frame(&s,2,&drive_join_packet(700),2),t).is_err());drive_same(&s,&before);
        let mut other=arena_ready(t);other.drive=Some(crate::map_drive_world091::Arena::new(t));let old=other.clone();
        assert!(other.receive(&arena_frame(&other,1,&drive_join_packet(700),2),t).is_err());drive_same(&other,&old);
        let mut old=vehicle_ready(t);assert!(old.receive(&arena_frame(&old,1,&drive_join_packet(700),2),t).is_err());assert!(old.drive.is_none());
    }
    #[test]fn ordinary_queue_late_payload_and_piggyback_failure_never_allocate_generation(){
        let t=Instant::now();let ready=drive_idle(t);
        let mut bad=drive_join_packet(700);bad.push(0);let first=arena_frame(&ready,1,&drive_join_packet(700),2);
        let mut outer=arena_frame(&ready,2,&[255],2);outer.piggybacks.push(first);
        for f in [arena_frame(&ready,1,&bad,2),outer]{let mut s=ready.clone();assert!(s.receive(&f,t).is_err());drive_same(&s,&ready);}
    }
    #[test]fn ordinary_cancel_retires_pending_generation_without_changing_account(){
        let t=Instant::now();let mut s=drive_idle(t);let state=s.hangar.as_ref().unwrap().state_sha256();
        s.receive(&arena_frame(&s,1,&drive_join_packet(700),2),t).unwrap();s.tx.due(t,s.rx).unwrap();
        s.receive(&arena_frame(&s,2,&drive_join_packet(701),3),t).unwrap();assert_eq!(s.drive.as_ref().unwrap().phase,crate::map_drive_world091::Phase::Idle);
        assert_eq!(s.drive.as_ref().unwrap().generation,1);assert_eq!(s.hangar.as_ref().unwrap().state_sha256(),state);assert!(!s.arena_base);
        s.tx.due(t,s.rx).unwrap();s.receive(&arena_frame(&s,3,&drive_join_packet(700),4),t).unwrap();assert_eq!(s.drive.as_ref().unwrap().generation,2);
    }
    #[test]fn ordinary_aoi_request_create_and_ready_are_specific_ack_bound(){
        let t=Instant::now();let mut s=drive_enabled(t);s.receive(&arena_frame(&s,1,&[9],2),t).unwrap();let before=s.clone();
        assert!(s.receive(&arena_frame(&s,2,&[8,4,0,3,0,16,9],3),t).is_err());drive_same(&s,&before); // not sent
        s.tx.due(t,s.rx).unwrap();assert!(s.receive(&arena_frame(&s,2,&[8,4,0,3,0,16,9],2),t).is_err());
        s.receive(&arena_frame(&s,2,&[8,4,0,3,0,16,9],3),t).unwrap();s.tx.due(t,s.rx).unwrap();let before=s.clone();
        assert!(s.receive(&arena_frame(&s,3,&READY_COMPOUND,3),t).is_err());drive_same(&s,&before);
        s.tx.enqueue().unwrap();s.tx.due(t,s.rx).unwrap();let mut f=arena_frame(&s,3,&READY_COMPOUND,3);f.selective=vec![3];
        s.receive(&f,t).unwrap();assert_eq!(s.map_binding.as_ref().unwrap().force_sequence,5);assert_eq!(s.tx.len(),2);
    }
    #[test]fn ordinary_controls_require_force_ack_reject_late_poison_and_ignore_client_coordinates(){
        let t=Instant::now();let ready=drive_live(t);let mut s=ready.clone();
        assert!(s.receive(&arena_frame(&s,4,&[0x8a,1,0,1],5),t).is_err());drive_same(&s,&ready);
        assert!(s.receive(&arena_frame(&s,4,&[6,0x8a,1,0,1,7],5),t).is_err());drive_same(&s,&ready);
        let mut b=vec![6,2];for p in [99999f32,-99999f32,88888f32]{b.extend(p.to_le_bytes());}b.extend([255;4]);b.extend([0x8a,1,0,10]);
        s.receive(&arena_frame(&s,4,&b,5),t).unwrap();let d=s.drive.as_ref().unwrap();assert_eq!(d.input,crate::map_drive_worker091::Input{throttle:-1,steer:1,brake:false});
        assert_eq!(d.pose.as_ref().unwrap().position,[0.,10.,0.]);assert_eq!(d.telemetry,1);assert_eq!(d.commands,1);assert_eq!(d.correction_acks,1);
        let state=s.drive.clone();s.receive(&arena_frame(&s,4,&b,5),t).unwrap();assert_eq!(s.drive,state);
    }
    #[test]fn ordinary_leave_and_late_bad_piggyback_roll_back_whole_generation(){
        let t=Instant::now();let ready=drive_live(t);let mut s=ready.clone();
        let mut f=arena_frame(&s,5,&[255],5);f.piggybacks.push(arena_frame(&s,4,&[0x99,1,0,0],5));
        assert!(s.receive(&f,t).is_err());drive_same(&s,&ready);
        s.receive(&arena_frame(&s,4,&[0x8a,1,0,0,0x99,1,0,0],5),t).unwrap();
        assert_eq!(s.drive.as_ref().unwrap().phase,crate::map_drive_world091::Phase::Returning);assert!(!s.arena_base);assert!(s.map_binding.is_none());
        assert_eq!(s.sync_mask,7);assert_eq!(s.account_cache_hash,Some(-42));assert_eq!(s.identity.as_ref().unwrap().account_id,crate::arena_vehicle091::PRIMARY_ACCOUNT);
        let body=transport091::parse_interactive(&s.tx.due(t,s.rx).unwrap().unwrap().2).unwrap().body;
        assert_eq!(&body[..3],&[4,0,5]);assert_eq!(&body[9..11],&[0,0]);
    }
    #[test]fn ordinary_unsupported_flags_stop_prior_throttle_only_after_whole_commit(){
        let t=Instant::now();let mut ready=drive_live(t);
        ready.receive(&arena_frame(&ready,4,&[6,0x8a,1,0,1],5),t).unwrap();
        assert_eq!(ready.drive.as_ref().unwrap().input.throttle,1);
        for flags in [3,12,15,16,17,32,33,255]{
            let mut s=ready.clone();s.receive(&arena_frame(&s,5,&[0x8a,1,0,flags],5),t).unwrap();
            assert_eq!(s.drive.as_ref().unwrap().input,crate::map_drive_worker091::Input::STOP);
            assert_eq!(s.drive.as_ref().unwrap().commands,2);assert_eq!(s.drive.as_ref().unwrap().pose,ready.drive.as_ref().unwrap().pose);
            let after=s.drive.clone();s.receive(&arena_frame(&s,5,&[0x8a,1,0,flags],5),t).unwrap();assert_eq!(s.drive,after);
            let mut s=ready.clone();assert!(s.receive(&arena_frame(&s,5,&[0x8a,1,0,flags,7],5),t).is_err());drive_same(&s,&ready);
            let mut late=arena_frame(&ready,6,&[255],5);late.piggybacks.push(arena_frame(&ready,5,&[0x8a,1,0,flags],5));
            assert!(s.receive(&late,t).is_err());drive_same(&s,&ready);
        }
    }
    #[test]fn captured_sniper_setting_commits_ack_then_allows_next_heartbeat_and_movement(){
        let t=Instant::now();let mut s=drive_live(t);
        s.receive(&arena_frame(&s,4,&[6,0x8a,1,0,1],5),t).unwrap();
        let pose=s.drive.as_ref().unwrap().pose.clone();let input=s.drive.as_ref().unwrap().input;
        let account=s.hangar.as_ref().unwrap().state_sha256();
        for _ in 0..8{s.tx.enqueue_body(&[13,1]).unwrap();s.tx.due(t,s.rx).unwrap();}assert_eq!(s.tx.len(),8);
        let enter=arena_frame(&s,5,&[0x8d,5,0,2,0,0,0,0],13);
        let before=s.clone();let mut wrong_token=enter.clone();wrong_token.body[1]^=1;
        for bad in [wrong_token,arena_frame(&s,5,&[0x8d,5,0,2,0,0,0,0],14),arena_frame(&s,6,&[0x8d,5,0,2,0,0,0,0],13)]{
            assert!(s.receive(&bad,t).is_err());drive_same(&s,&before);
        }
        s.receive(&enter,t).unwrap();assert_eq!(s.rx,6);assert_eq!(s.tx.cumulative,13);assert_eq!(s.tx.len(),0);
        assert_eq!(s.drive.as_ref().unwrap().aim,1);assert_eq!(s.drive.as_ref().unwrap().input,input);
        assert_eq!(s.drive.as_ref().unwrap().pose,pose);assert_eq!(s.hangar.as_ref().unwrap().state_sha256(),account);
        let once=s.drive.clone();s.receive(&enter,t).unwrap();assert_eq!(s.drive,once);
        let before=s.clone();assert!(s.receive(&arena_frame(&s,5,&[0x8d,5,0,2,1,0,0,0],13),t).is_err());drive_same(&s,&before);
        s.receive(&arena_frame(&s,6,&[],13),t).unwrap();assert_eq!(s.rx,7);
        s.receive(&arena_frame(&s,7,&[0x8d,5,0,2,1,0,0,0,0x8a,1,0,2],13),t).unwrap();
        assert_eq!(s.rx,8);assert_eq!(s.drive.as_ref().unwrap().aim,2);
        assert_eq!(s.drive.as_ref().unwrap().input.throttle,-1);assert_eq!(s.drive.as_ref().unwrap().pose,pose);
    }
    #[test]fn camera_setting_late_poison_phase_and_budget_fail_without_ack_or_state_commit(){
        let t=Instant::now();let ready=drive_live(t);let enter=[0x8d,5,0,2,0,0,0,0];
        for payload in [vec![0x8d,5,0,16,1,0,0,0],vec![0x8d,5,0,2,2,0,0,0],
            [enter.as_slice(),&[7]].concat(),[&[0x8a,1,0,0][..],&[0x8d,5,0,0,1,0,0,0]].concat()]{
            let mut s=ready.clone();assert!(s.receive(&arena_frame(&s,4,&payload,5),t).is_err());drive_same(&s,&ready);
        }
        let mut s=ready.clone();let mut tree=arena_frame(&s,5,&[7],5);tree.piggybacks.push(arena_frame(&s,4,&enter,5));
        assert!(s.receive(&tree,t).is_err());drive_same(&s,&ready);
        for phase in [crate::map_drive_world091::Phase::Ready,crate::map_drive_world091::Phase::EntityRequest,crate::map_drive_world091::Phase::Enable]{
            let mut s=ready.clone();s.drive.as_mut().unwrap().phase=phase;let before=s.clone();
            assert!(s.receive(&arena_frame(&s,4,&enter,5),t).is_err());drive_same(&s,&before);
        }
        let mut s=ready.clone();s.drive.as_mut().unwrap().aim=499_999;
        let final_allowed=arena_frame(&s,4,&enter,5);
        s.receive(&final_allowed,t).unwrap();assert_eq!(s.drive.as_ref().unwrap().aim,500_000);
        s.receive(&final_allowed,t).unwrap();assert_eq!(s.drive.as_ref().unwrap().aim,500_000);
        let before=s.clone();assert!(s.receive(&arena_frame(&s,5,&enter,5),t).is_err());drive_same(&s,&before);
    }
    #[test]fn late_camera_restore_is_only_drained_in_retired_avatar_before_warm_enable(){
        let t=Instant::now();let mut ready=drive_live(t);ready.recover_drive_failure(&mut Vec::new()).unwrap();ready.tx.due(t,ready.rx).unwrap();
        let restore=[0x8d,5,0,2,1,0,0,0];let mut s=ready.clone();
        let frame=arena_frame(&s,4,&restore,6);s.receive(&frame,t).unwrap();
        assert_eq!(s.drive.as_ref().unwrap().input,crate::map_drive_worker091::Input::STOP);
        assert_eq!(s.drive,ready.drive);assert_eq!(s.map_binding,ready.map_binding);
        assert_eq!(s.drive_return_account.as_ref().unwrap().stale_avatar_envelopes,1);
        let once=s.clone();s.receive(&frame,t).unwrap();drive_same(&s,&once);
        s.receive(&arena_frame(&s,5,&[9],6),t).unwrap();let before=s.clone();
        assert!(s.receive(&arena_frame(&s,6,&restore,6),t).is_err());drive_same(&s,&before);
        for change in 0..2{let mut s=ready.clone();let warm=s.drive_return_account.as_mut().unwrap();
            if change==0{warm.generation+=1;}else{warm.stale_avatar_envelopes=32;}
            let before=s.clone();assert!(s.receive(&arena_frame(&s,4,&restore,6),t).is_err());drive_same(&s,&before);
        }
    }
    #[test]fn actual_reentry_move_before_correction_in_one_native_compound_commits_once(){
        // Actual closed fixed-review-01 packet5663, SHA256ab290609...510b3a066.
        // Native seq1864/ACK1863 follows binding1862; fixture renumbers only
        // the reliable envelope, exact application bytes/order are unchanged.
        let t=Instant::now();let mut s=drive_live(t);let payload=[0x8a,1,0,1,6];
        let pose=s.drive.as_ref().unwrap().pose.clone();let frame=arena_frame(&s,4,&payload,5);
        s.receive(&frame,t).unwrap();assert_eq!(s.rx,5);assert_eq!(s.tx.len(),0);
        assert!(s.map_binding.as_ref().unwrap().force_acked);assert_eq!(s.drive.as_ref().unwrap().correction_acks,1);
        assert_eq!(s.drive.as_ref().unwrap().input.throttle,1);assert_eq!(s.drive.as_ref().unwrap().commands,1);
        assert_eq!(s.drive.as_ref().unwrap().pose,pose);assert!(!s.drive.as_ref().unwrap().pending);
        let once=s.clone();s.receive(&frame,t).unwrap();drive_same(&s,&once);
        s.receive(&arena_frame(&s,5,&[0x8a,1,0,0],5),t).unwrap();assert_eq!(s.drive.as_ref().unwrap().input,crate::map_drive_worker091::Input::STOP);
        s.receive(&arena_frame(&s,6,&[0x8d,5,0,2,0,0,0,0],5),t).unwrap();assert_eq!(s.drive.as_ref().unwrap().aim,1);
    }
    #[test]fn move_before_correction_still_requires_real_binding_ack_and_whole_valid_commit(){
        let t=Instant::now();let ready=drive_live(t);
        for (payload,ack) in [(vec![0x8a,1,0,1,6],4),(vec![0x8a,1,0,1],5),
            (vec![0x8a,1,0,1,6,7],5),(vec![0x8a,1,0,1,6,0x8d,5,0,16,1,0,0,0],5),
            ([&[0x8a,1,0,1][..],&[6;9]].concat(),5)]{
            let mut s=ready.clone();assert!(s.receive(&arena_frame(&s,4,&payload,ack),t).is_err());drive_same(&s,&ready);
        }
        // Queued-but-never-sent binding cannot be ACKed or authorize movement.
        let mut unsent=drive_ready(t);unsent.receive(&arena_frame(&unsent,3,&READY_COMPOUND,4),t).unwrap();let before=unsent.clone();
        for ack in [4,5]{assert!(unsent.receive(&arena_frame(&unsent,4,&[0x8a,1,0,1,6],ack),t).is_err());drive_same(&unsent,&before);}
        let mut s=ready.clone();let mut f=arena_frame(&s,5,&[7],5);f.piggybacks.push(arena_frame(&s,4,&[0x8a,1,0,1,6],5));
        assert!(s.receive(&f,t).is_err());drive_same(&s,&ready);
    }

    fn warm_packet(id:i16,command:i16,revision:i64,a:i32,b:i32)->Vec<u8>{
        let mut p=vec![0x8e,20,0];p.extend(id.to_le_bytes());p.extend(command.to_le_bytes());p.extend(revision.to_le_bytes());p.extend(a.to_le_bytes());p.extend(b.to_le_bytes());p
    }
    fn drive_return_pending(t:Instant)->Session{
        let mut s=drive_live(t);s.receive(&arena_frame(&s,4,&[0x99,1,0,0],5),t).unwrap();s.tx.due(t,s.rx).unwrap();s
    }
    fn drive_returning(t:Instant)->Session{
        let mut s=drive_return_pending(t);s.receive(&arena_frame(&s,5,&[9],6),t).unwrap();s
    }
    #[test]fn ordinary_warm100_respects_outbox_bound_and_rolls_back_whole_receive(){
        let t=Instant::now();
        for queued in [127usize,128]{
            let mut s=drive_returning(t);
            // Fill the real send window without peer ACKs, then use valid
            // server-stat requests to reach the application queue boundary.
            for _ in 0..8{s.tx.enqueue().unwrap();}
            for _ in 0..queued{
                let n=s.rx;let request=warm_packet(202,501,0,0,0);
                s.receive(&arena_frame(&s,n,&request,6),t).unwrap();
            }
            assert_eq!(s.outbox.len(),queued);assert_eq!(s.tx.len(),8);
            let before=s.clone();let n=s.rx;
            let result=s.receive(&arena_frame(&s,n,&warm_packet(226,100,1,51539670,0),6),t);
            if queued==127{assert!(result.is_ok());assert_eq!(s.outbox.len(),128);}
            else{assert!(result.is_err());drive_same(&s,&before);}
        }
    }
    #[test]fn ordinary_warm_return_uses_persisted_revisions_new_hash_and_exact_owned_streams(){
        let t=Instant::now();let mut s=drive_returning(t);let state=s.hangar.as_ref().unwrap().state_sha256();
        let mut payload=warm_packet(227,100,1,-999,0);payload.extend(warm_packet(228,300,3,518,-846328027));payload.extend(warm_packet(229,600,1,1791128141,0));
        s.receive(&arena_frame(&s,6,&payload,6),t).unwrap();assert_eq!(s.drive.as_ref().unwrap().phase,crate::map_drive_world091::Phase::Idle);
        assert_eq!(s.drive.as_ref().unwrap().return_mask,7);assert_eq!(s.account_cache_hash,Some(-999));assert_eq!(s.hangar.as_ref().unwrap().state_sha256(),state);
        assert_eq!(s.identity.as_ref().unwrap().database_id,1);assert!(!s.arena_base);
        let first=transport091::parse_interactive(&s.tx.due(t,s.rx).unwrap().unwrap().2).unwrap().body;
        assert_eq!(first,crate::hangar091::response_refresh(&crate::account091::Request{id:227,command:100}).unwrap());
        assert!(first.windows(7).any(|b|b==b"prevRev"));
        let bad=warm_packet(230,100,1,-998,0);let before=s.clone();assert!(s.receive(&arena_frame(&s,7,&bad,6),t).is_err());drive_same(&s,&before);
        let good=warm_packet(230,100,1,-999,0);s.receive(&arena_frame(&s,7,&good,6),t).unwrap();
    }
    #[test]fn ordinary_warm_return_rejects_cold_versions_cursor_poison_and_late_tail_atomically(){
        let t=Instant::now();let ready=drive_returning(t);
        for (command,rev,a,b) in [(100,0,0,0),(100,2,1,0),(100,1,42,1),(300,0,518,1),(300,4,518,1),(300,3,16449,1),(600,1,1,0),(600,1,1791128141,1)]{
            let mut s=ready.clone();assert!(s.receive(&arena_frame(&s,6,&warm_packet(227,command,rev,a,b),6),t).is_err());drive_same(&s,&ready);assert_eq!(s.account_cache_hash,ready.account_cache_hash);
        }
        let mut bad=warm_packet(227,100,1,555,0);bad.extend(warm_packet(228,300,3,518,9));bad.push(0);
        let mut s=ready.clone();assert!(s.receive(&arena_frame(&s,6,&bad,6),t).is_err());drive_same(&s,&ready);assert_eq!(s.account_cache_hash,Some(-42));
        assert!(s.receive(&arena_frame(&s,6,&drive_join_packet(700),6),t).is_err());drive_same(&s,&ready);
    }
    // Ride07 packet701/reliable192: exact token-stripped native153B bundle.
    // Packet700/reliable191 was the preceding one-byte enableEntities09.
    fn ride07_warm()->Vec<u8>{
        let text="8e1400e20064000100000000000000d66e1203000000008e1400e3002c01030000000000000006020000250f8ecd8e1400e400580201000000000000004d72c26a0000000093190001000000000000000a00000000ffffffffffffffff000000009319000200000000000000090000000000000000000000000000000093190003000000000000001e00000000000000000000000000000000";
        text.as_bytes().chunks_exact(2).map(|p|u8::from_str_radix(std::str::from_utf8(p).unwrap(),16).unwrap()).collect()
    }
    #[test]fn ride07_warm_enable_then_exact_native_sync_and_restarted_chat_ids(){
        let t=Instant::now();let mut s=drive_return_pending(t);s.chat_request_ids=vec![1,2,3];
        let original=s.hangar.as_ref().unwrap().state_sha256().to_owned();let policy=s.drive_account_policy.clone();
        let reset=s.drive_return_account.as_ref().unwrap();assert_eq!(reset.creation,Some((5,false)));assert!(!reset.enabled);
        s.receive(&arena_frame(&s,5,&[9],6),t).unwrap();assert!(s.chat_request_ids.is_empty());
        let f=arena_frame(&s,6,&ride07_warm(),6);s.receive(&f,t).unwrap();
        assert_eq!(s.rx,7);assert_eq!(s.drive.as_ref().unwrap().phase,crate::map_drive_world091::Phase::Idle);
        assert_eq!(s.drive.as_ref().unwrap().return_mask,7);assert_eq!(s.chat_request_ids,vec![1,2,3]);
        assert_eq!(s.request_ids,vec![226,227,228]);assert_eq!(s.account_cache_hash,Some(51539670));
        assert_eq!(s.hangar.as_ref().unwrap().state_sha256(),original);assert_eq!(s.drive_account_policy,policy);
        let sent=s.tx.due(t,s.rx).unwrap().unwrap();assert_eq!(sent.0,6);
        assert_eq!(transport091::parse_interactive(&sent.2).unwrap().body,crate::hangar091::response_refresh(&crate::account091::Request{id:226,command:100}).unwrap());
        let before=s.clone();s.receive(&f,t).unwrap();drive_same(&s,&before);
        let before=s.clone();assert!(s.receive(&arena_frame(&s,7,&ride07_warm()[69..],6),t).is_err());drive_same(&s,&before);
    }
    #[test]fn warm_enable_and_rpc_in_one_complete_envelope_do_not_need_artificial_packet_split(){
        let t=Instant::now();let mut s=drive_return_pending(t);s.chat_request_ids=vec![1,2,3];
        let mut body=vec![9];body.extend(ride07_warm());s.receive(&arena_frame(&s,5,&body,6),t).unwrap();
        assert_eq!(s.drive.as_ref().unwrap().return_mask,7);assert_eq!(s.chat_request_ids,vec![1,2,3]);assert_eq!(s.rx,6);
    }
    #[test]fn warm_requires_enable_before_any_new_mailbox_rpc_and_rejects_fresh_duplicate(){
        let t=Instant::now();let ready=drive_return_pending(t);
        for body in [ride07_warm(),ride07_warm()[69..].to_vec(),vec![9,9],vec![9,0]]{
            let mut s=ready.clone();assert!(s.receive(&arena_frame(&s,5,&body,6),t).is_err());drive_same(&s,&ready);
        }
        let mut s=ready.clone();let enable=arena_frame(&s,5,&[9],6);s.receive(&enable,t).unwrap();
        s.chat_request_ids=vec![7];let before=s.clone();s.receive(&enable,t).unwrap();drive_same(&s,&before);
        assert!(s.receive(&arena_frame(&s,6,&[9],6),t).is_err());drive_same(&s,&before);
    }
    #[test]fn warm_enable_requires_specific_sent_reset_ack_but_not_later_heartbeat_ack(){
        let t=Instant::now();let mut s=drive_return_pending(t);let before=s.clone();
        assert!(s.receive(&arena_frame(&s,5,&[9],5),t).is_err());drive_same(&s,&before);
        s.tx.enqueue().unwrap();s.tx.due(t,s.rx).unwrap();let before=s.clone();
        let mut wrong=arena_frame(&s,5,&[9],5);wrong.selective=vec![6];
        assert!(s.receive(&wrong,t).is_err());drive_same(&s,&before);
        let mut exact=arena_frame(&s,5,&[9],5);exact.selective=vec![5];s.receive(&exact,t).unwrap();
        assert!(s.drive_return_account.as_ref().unwrap().enabled);assert_eq!(s.tx.len(),1);assert_eq!(s.tx.cumulative,5);
        // A separately received selective ACK must survive until actual09.
        let mut s=before.clone();let mut ack=transport091::parse(&transport091::ack(5)).unwrap();ack.selective=vec![5];
        s.receive(&ack,t).unwrap();s.receive(&arena_frame(&s,5,&[9],5),t).unwrap();assert_eq!(s.tx.len(),1);
    }
    #[test]fn warm_reset_tracking_preserves_outbox_order_and_full_window_backpressure(){
        let t=Instant::now();let mut s=drive_live(t);
        // Fill the real reliable window with later heartbeat frames; return is
        // retained behind two already-queued application bodies, not reordered.
        for _ in 0..7{s.tx.enqueue().unwrap();}while s.tx.due(t,s.rx).unwrap().is_some(){}
        s.outbox.push_back(vec![0x13,0x48,1,0,0,0,1,0,0,0]);s.outbox.push_back(vec![]);
        s.receive(&arena_frame(&s,4,&[0x99,1,0,0],4),t).unwrap();
        assert_eq!(s.drive_return_account.as_ref().unwrap().creation,None);
        assert_eq!(s.drive_return_account.as_ref().unwrap().queue_ahead,2);
        let before=s.clone();assert!(s.receive(&arena_frame(&s,5,&[9],4),t).is_err());drive_same(&s,&before);
        s.receive(&transport091::parse(&transport091::ack(12)).unwrap(),t).unwrap();
        assert_eq!(s.drive_return_account.as_ref().unwrap().creation,Some((14,false)));
        let before=s.clone();assert!(s.receive(&arena_frame(&s,5,&[9],15),t).is_err());drive_same(&s,&before); // unsent ACK
        let mut bodies=Vec::new();while let Some((n,_,b))=s.tx.due(t,s.rx).unwrap(){bodies.push((n,transport091::parse_interactive(&b).unwrap().body));}
        assert_eq!(bodies.iter().map(|x|x.0).collect::<Vec<_>>(),vec![12,13,14]);assert_eq!(&bodies[2].1[..3],&[4,0,5]);
        s.tx.enqueue().unwrap();s.tx.due(t,s.rx).unwrap();
        s.receive(&arena_frame(&s,5,&[9],15),t).unwrap();assert_eq!(s.tx.len(),1);
    }
    #[test]fn warm_enable_late_bad_tail_and_chat_mutation_roll_back_ack_epoch_and_all_responses(){
        let t=Instant::now();let mut ready=drive_return_pending(t);ready.chat_request_ids=vec![1,2,3];
        let mut good=vec![9];good.extend(ride07_warm());
        let mut bad=good.clone();bad.push(255);
        let mut wrong_chat=good.clone();wrong_chat[1+125+11]=31;
        let mut duplicate_chat=good.clone();duplicate_chat.extend(&ride07_warm()[69..97]);
        for body in [bad,wrong_chat,duplicate_chat]{let mut s=ready.clone();assert!(s.receive(&arena_frame(&s,5,&body,6),t).is_err());drive_same(&s,&ready);}
        let mut late=arena_frame(&ready,7,&[255],6);let mut sync=arena_frame(&ready,6,&ride07_warm(),6);
        sync.piggybacks.push(arena_frame(&ready,5,&[9],6));late.piggybacks.push(sync);
        let mut s=ready.clone();assert!(s.receive(&late,t).is_err());drive_same(&s,&ready);
    }
    #[test]fn warm_piggyback_cannot_borrow_an_ack_from_later_parent_but_earlier_ack_works(){
        let t=Instant::now();let ready=drive_return_pending(t);
        let mut late_ack=arena_frame(&ready,6,&[],6);late_ack.piggybacks.push(arena_frame(&ready,5,&[9],5));
        let mut s=ready.clone();assert!(s.receive(&late_ack,t).is_err());drive_same(&s,&ready);
        let mut early_ack=arena_frame(&ready,6,&[9],5);early_ack.piggybacks.push(arena_frame(&ready,5,&[],6));
        s.receive(&early_ack,t).unwrap();assert_eq!(s.rx,7);assert!(s.drive_return_account.as_ref().unwrap().enabled);
    }
    #[test]fn warm_enable_remains_authenticated_and_bound_to_current_generation_and_policy(){
        let t=Instant::now();let ready=drive_return_pending(t);
        for mutation in 0..8{let mut s=ready.clone();match mutation{
            0=>s.active=false,1=>s.account_ready=false,2=>s.base_peer=None,3=>s.sync_mask=3,
            4=>s.drive_return_account.as_mut().unwrap().generation+=1,
            5=>s.drive_account_policy=None,6=>s.identity=arena_ready(t).identity,
            7=>s.hangar=arena_ready(t).hangar,_=>unreachable!()}
            let before=s.clone();assert!(s.receive(&arena_frame(&s,5,&[9],6),t).is_err());drive_same(&s,&before);
        }
        let mut f=arena_frame(&ready,5,&[9],6);f.body[1]^=1;let mut s=ready.clone();assert!(s.receive(&f,t).is_err());drive_same(&s,&ready);
        let mut s=ready.clone();assert!(s.receive(&arena_frame(&s,6,&[9],6),t).is_err());drive_same(&s,&ready);
    }
    #[test]fn warm_enable_not_available_to_cold_account_or_frozen_ordinary_and_probe_modes(){
        let t=Instant::now();for mut s in [drive_idle(t),drive_queued(t),vehicle_ready(t),arena_ready(t)]{
            let before=s.clone();let n=s.rx;let ack=s.tx.cumulative;
            assert!(s.receive(&arena_frame(&s,n,&[9],ack),t).is_err());drive_same(&s,&before);
        }
    }
    #[test]fn warm_completed_epoch_is_discarded_only_by_new_authorized_queue_generation(){
        let t=Instant::now();let mut s=drive_returning(t);s.receive(&arena_frame(&s,6,&ride07_warm(),6),t).unwrap();
        assert!(s.drive_return_account.as_ref().unwrap().enabled);
        let before=s.clone();let mut bad=drive_join_packet(700);bad.push(255);
        assert!(s.receive(&arena_frame(&s,7,&bad,6),t).is_err());drive_same(&s,&before);
        s.receive(&arena_frame(&s,7,&drive_join_packet(700),6),t).unwrap();
        assert_eq!(s.drive.as_ref().unwrap().generation,2);assert!(s.drive_return_account.is_none());
        assert_eq!(s.chat_request_ids,vec![1,2,3]); // not reset merely by queueing
    }
    #[test]fn ordinary_identity_or_seed_change_cannot_reuse_ready_authority(){
        let t=Instant::now();let ready=drive_live(t);
        for change in 0..5{let mut s=ready.clone();match change{
            0=>s.arena_vehicle_seed.as_mut().unwrap().health=91,1=>s.sync_mask=3,2=>s.active=false,
            3=>s.identity=arena_ready(t).identity,4=>s.hangar=arena_ready(t).hangar,_=>unreachable!()}
            let before=s.clone();assert!(s.receive(&arena_frame(&s,4,&[6],5),t).is_err());drive_same(&s,&before);
        }
    }

    #[test]fn ride17_publication_clock_invariant_names_reuse_and_preserves_bounds(){
        let t=Instant::now();let mut a=crate::map_drive_world091::Arena::new(t);a.created=Some(t);a.native_tick=1252;
        assert!(drive_publication_tick(&a,t+Duration::from_millis(25275)).unwrap_err().to_string().contains("TickReuse"));
        assert_eq!(drive_publication_tick(&a,t+Duration::from_millis(25300)).unwrap(),1253);
        assert!(drive_publication_tick(&a,t+Duration::from_millis(30300)).unwrap_err().to_string().contains("TickGap"));
        assert!(drive_publication_tick(&a,t-Duration::from_millis(1)).unwrap_err().to_string().contains("ClockRegression"));
        a.native_tick=1023;assert_eq!(drive_publication_tick(&a,t+Duration::from_millis(2400)).unwrap(),1024);
        assert!(drive_publication_tick(&a,t+Duration::from_secs(3600)).unwrap_err().to_string().contains("ClockDeadline"));
    }
    #[test]fn ride17_failure_sends_real_reset_without_another_receive(){
        let t=Instant::now();let mut s=drive_live(t);let rx=s.rx;let mut events=Vec::new();
        s.recover_drive_failure(&mut events).unwrap();assert_eq!(s.rx,rx);assert!(s.outbox.is_empty());
        assert_eq!(s.drive_return_account.as_ref().unwrap().creation,Some((5,false)));
        let (sequence,_,wire)=s.tx.due(t,s.rx).unwrap().unwrap();assert_eq!(sequence,5);
        assert_eq!(transport091::parse_interactive(&wire).unwrap().body,crate::map_drive_world091::return_account(&s.identity.as_ref().unwrap().name).unwrap());
        assert!(events[0].contains("reason=worker_or_publication_failure"));
        assert_eq!(s.drive.as_ref().unwrap().input,crate::map_drive_worker091::Input::STOP);
    }
    #[test]fn ride17_real_late487_488_forward_is_retired_before_actual_warm09(){
        // Captured seq487 and488 app bytes8a010001; transport test session uses
        // equivalent contiguous4/5 after the same ordered reset lifecycle.
        let t=Instant::now();let mut s=drive_live(t);let pose=s.drive.as_ref().unwrap().pose.clone();
        s.recover_drive_failure(&mut Vec::new()).unwrap();s.tx.due(t,s.rx).unwrap();
        let first=arena_frame(&s,4,&[0x8a,1,0,1],5);s.receive(&first,t).unwrap();
        assert_eq!(s.drive_return_account.as_ref().unwrap().stale_avatar_envelopes,1);
        let unchanged=s.clone();s.receive(&first,t).unwrap();drive_same(&s,&unchanged);
        // Current transport ACK can arrive on a queued old Avatar method.
        s.receive(&arena_frame(&s,5,&[0x8a,1,0,1],6),t).unwrap();
        assert_eq!(s.drive.as_ref().unwrap().commands,0);assert_eq!(s.drive.as_ref().unwrap().pose,pose);
        assert_eq!(s.drive.as_ref().unwrap().input,crate::map_drive_worker091::Input::STOP);
        assert_eq!(s.drive_return_account.as_ref().unwrap().stale_avatar_envelopes,2);
        s.receive(&arena_frame(&s,6,&[9],6),t).unwrap();
        let before=s.clone();assert!(s.receive(&arena_frame(&s,7,&[0x8a,1,0,1],6),t).is_err());drive_same(&s,&before);
    }
    #[test]fn ride17_recovery_backpressure_keeps_order_and_known_stale_ack_unblocks_reset(){
        let t=Instant::now();let mut s=drive_live(t);
        for _ in 0..7{s.tx.enqueue().unwrap();}while s.tx.due(t,s.rx).unwrap().is_some(){}
        s.outbox.push_back(vec![]);s.recover_drive_failure(&mut Vec::new()).unwrap();
        assert_eq!(s.drive_return_account.as_ref().unwrap().creation,None);assert_eq!(s.outbox.len(),2);
        s.receive(&arena_frame(&s,4,&[0x8a,1,0,1],12),t).unwrap();
        assert_eq!(s.drive_return_account.as_ref().unwrap().creation,Some((13,false)));
        let first=s.tx.due(t,s.rx).unwrap().unwrap();assert_eq!(first.0,12);assert!(transport091::parse_interactive(&first.2).unwrap().body.is_empty());
        let second=s.tx.due(t,s.rx).unwrap().unwrap();assert_eq!(second.0,13);assert_eq!(&transport091::parse_interactive(&second.2).unwrap().body[..3],&[4,0,5]);
    }
    #[test]fn ride17_stale_avatar_tail_piggyback_token_ack_and_generation_are_atomic(){
        let t=Instant::now();let mut ready=drive_live(t);ready.recover_drive_failure(&mut Vec::new()).unwrap();ready.tx.due(t,ready.rx).unwrap();
        for payload in [vec![0x8a,1,0,1,255],vec![255],vec![0x8a,1,0],vec![0x8a,1,0,1,9],vec![6;17],vec![6;513]]{
            let mut s=ready.clone();assert!(s.receive(&arena_frame(&s,4,&payload,6),t).is_err());drive_same(&s,&ready);
        }
        let mut late=arena_frame(&ready,5,&[255],6);late.piggybacks.push(arena_frame(&ready,4,&[0x8a,1,0,1],6));
        let mut s=ready.clone();assert!(s.receive(&late,t).is_err());drive_same(&s,&ready);
        let mut wrong=arena_frame(&ready,4,&[0x8a,1,0,1],6);wrong.body[1]^=1;
        assert!(s.receive(&wrong,t).is_err());drive_same(&s,&ready);
        assert!(s.receive(&arena_frame(&ready,4,&[0x8a,1,0,1],7),t).is_err());drive_same(&s,&ready);
        let mut s=ready.clone();s.drive_return_account.as_mut().unwrap().generation+=1;let before=s.clone();
        assert!(s.receive(&arena_frame(&s,4,&[0x8a,1,0,1],6),t).is_err());drive_same(&s,&before);
        let mut s=ready.clone();assert!(s.receive(&arena_frame(&s,4,&[9],5),t).is_err());drive_same(&s,&ready);
    }
    #[test]fn ride17_retired_drain_has_exact32_envelope_budget_without_domain_effect(){
        let t=Instant::now();let mut s=drive_live(t);s.recover_drive_failure(&mut Vec::new()).unwrap();s.tx.due(t,s.rx).unwrap();
        for n in 4..36{s.receive(&arena_frame(&s,n,&[0x8a,1,0,1],6),t).unwrap();}
        assert_eq!(s.drive_return_account.as_ref().unwrap().stale_avatar_envelopes,32);
        let before=s.clone();assert!(s.receive(&arena_frame(&s,36,&[0x8a,1,0,1],6),t).is_err());drive_same(&s,&before);
        // Budget exhaustion cannot prohibit the real correctly ACK-bound epoch.
        s.receive(&arena_frame(&s,36,&[9],6),t).unwrap();assert!(s.drive_return_account.as_ref().unwrap().enabled);
    }
}
