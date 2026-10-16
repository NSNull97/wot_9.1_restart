//! Actual admitted World5 -> departure -> immutable Outcome -> sole Finish5.
//! No JSON/Inspect/native message can create a registered Link. Original typed
//! reservation, authenticated Profile and actual attached Actor are required.
use std::{io,sync::Arc};
use sha2::{Digest,Sha256};
use crate::{identity091,profile13_hold091 as hold};
use super::{model::World,lifecycle_wire::Results};
fn bad(why:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("owner hold5 capture: {why}"))}

#[derive(Clone)]
pub(super) struct Link{owner:Arc<identity091::Profile>,reservation:hold::Reservation,source:hold::SourceLink,admission_revision:u64}
impl Link{
    pub(super) fn owner(&self)->&Arc<identity091::Profile>{&self.owner}
    pub(super) fn reservation(&self)->&hold::Reservation{&self.reservation}
    pub(super) fn source(&self)->&hold::SourceLink{&self.source}
    pub(super) fn revision(&self)->u64{self.admission_revision}
    /// A future current Account must not provide final CAS/key/source identity.
    /// V5 owner fences keep this actual admitted revision unchanged until the
    /// sole final mutation. Reads/query/ACK and same-run RunOpen do not advance it.
    pub(super) fn context(&self,finalize:bool)->hold::Context{
        let fingerprint=format!("{:x}",Sha256::digest(self.reservation.reservation_id.as_bytes()));
        hold::Context{account_id:self.owner.account_id.clone(),native_database_id:self.owner.database_id,
            command_key:format!("hold5:{}:{fingerprint}",if finalize{"final"}else{"inspect"}),
            expected_revision:self.admission_revision,run_id:self.source.run_id.clone()}
    }
    fn check_actor(&self,world:&World)->io::Result<()>{
        self.source.validate_reservation(&self.reservation,&self.owner.account_id,self.owner.database_id)?;
        let a=world.actors.get(self.source.actor_slot as usize).ok_or_else(||bad("linked slot missing"))?;
        let f=&self.reservation.frozen;
        if !world.owner_hold_enabled()||!world.mixed_ammo()||!world.ammo_detonation_enabled()||world.id!=self.source.battle
            ||world.team(self.source.actor_slot as usize)?!=self.source.team
            ||a.identity.account!=self.owner.account_id||a.identity.database!=self.owner.database_id||a.identity.name!=self.owner.name
            ||a.vehicle_kind()!=f.loss().base.kind||a.owned_hold.as_ref()!=Some(f)||a.owned_loss.as_ref()!=Some(f.loss())||a.owned_v2.as_ref()!=Some(&f.loss().base)
            ||a.session.is_some_and(|sid|sid!=self.source.source_session_id){return Err(bad("actual actor/source5 changed"));}
        Ok(())
    }
    fn same(&self,other:&Self)->bool{self.source==other.source&&self.reservation==other.reservation&&self.admission_revision==other.admission_revision
        &&self.owner.account_id==other.owner.account_id&&self.owner.database_id==other.owner.database_id&&self.owner.name==other.owner.name}
}
#[derive(Clone)]pub(super) struct Seal{results:Option<Arc<Results>>,finals:Vec<(usize,hold::Finish)>}
impl Seal{
    pub(super) fn results(&self)->Option<&Arc<Results>>{self.results.as_ref()}
    pub(super) fn finish(&self,slot:usize)->io::Result<&hold::Finish>{self.finals.iter().find(|r|r.0==slot).map(|r|&r.1).ok_or_else(||bad("sealed slot"))}
}
#[derive(Clone)]
pub(super) struct Capture{run:String,battle:u64,links:Vec<Link>,departures:[Option<hold::Departure>;6],held_inspected:[bool;6],seal:Option<Arc<Seal>>}
impl Capture{
    pub(super) fn new(run:String,battle:u64)->io::Result<Self>{
        // The real request encoder validates UUID/run/context, with no IO.
        hold::encode_request(&hold::Context{account_id:run.clone(),native_database_id:1,command_key:"hold:capture-context".into(),expected_revision:13,run_id:run.clone()},&hold::Request::Inspect)?;
        if battle==0{return Err(bad("zero battle"));}Ok(Self{run,battle,links:Vec::new(),departures:[None;6],held_inspected:[false;6],seal:None})
    }
    pub(super) fn links(&self)->&[Link]{&self.links}
    pub(super) fn seal(&self)->Option<&Arc<Seal>>{self.seal.as_ref()}
    pub(super) fn register(&mut self,world:&World,slot:usize,source_session:u32,
        owner:Arc<identity091::Profile>,reservation:hold::Reservation,admission_revision:u64)->io::Result<bool>{
        if slot>=6||source_session==0||world.id!=self.battle||reservation.run_id!=self.run||reservation.battle!=self.battle
            ||!(13..i32::MAX as u64).contains(&admission_revision)||reservation.status!=hold::ReservationStatus::Active||reservation.result.is_some(){return Err(bad("real active5 admission bounds"));}
        reservation.frozen.validate_owned(&owner.account_id)?;
        let f=&reservation.frozen.loss().base;
        let source=hold::SourceLink{account_id:owner.account_id.clone(),native_database_id:owner.database_id,run_id:self.run.clone(),battle:self.battle,reservation_id:reservation.reservation_id.clone(),
            native_inventory_id:f.native_inventory_id,vehicle_inventory_id:f.vehicle_inventory_id.clone(),frozen_sha256:reservation.frozen.sha256().into(),source_session_id:source_session,actor_slot:slot as u8,team:world.team(slot)?,vehicle_kind:f.kind.label().into()};
        let link=Link{owner,reservation,source,admission_revision};link.check_actor(world)?;
        if let Some(old)=self.links.iter().find(|l|l.source.actor_slot==slot as u8){return if old.same(&link){Ok(false)}else{Err(bad("immutable registered slot"))};}
        if world.started.is_some()||self.seal.is_some()||self.links.len()>=6||world.actors.get(slot).is_none_or(|a|a.session!=Some(source_session))
            ||self.links.iter().any(|l|l.source.account_id==link.source.account_id||l.source.native_database_id==link.source.native_database_id||l.source.source_session_id==source_session){return Err(bad("register only actual attach before start"));}
        self.links.push(link);self.links.sort_by_key(|l|l.source.actor_slot);Ok(true)
    }
    pub(super) fn link(&self,slot:usize)->io::Result<&Link>{self.links.iter().find(|l|usize::from(l.source.actor_slot)==slot).ok_or_else(||bad("unregistered source slot"))}
    /// Caller has staged real World.detach and Session authority revocation.
    /// A later disconnect cannot overwrite first ManualLeave or a frozen result.
    pub(super) fn departed_after_detach(&mut self,world:&World,slot:usize,source_session:u32,reason:hold::DepartureReason)->io::Result<bool>{
        let l=self.link(slot)?;l.check_actor(world)?;
        if l.source.source_session_id!=source_session||world.actors[slot].session.is_some(){return Err(bad("departure must revoke original actual actor"));}
        if self.seal.is_some()||world.lifecycle.as_ref().is_some_and(|l|l.outcome().is_some()){return Ok(false);}
        if !(1000..=37000).contains(&world.tick){return Err(bad("actual departure clock"));}
        if self.departures[slot].is_some(){return Ok(false);}
        self.departures[slot]=Some(hold::Departure{reason,tick:world.tick});Ok(true)
    }
    pub(super) fn departure(&self,slot:usize)->io::Result<Option<hold::Departure>>{self.link(slot)?;Ok(self.departures[slot])}
    pub(super) fn held_inspected(&self,slot:usize)->io::Result<bool>{self.link(slot)?;Ok(self.held_inspected[slot])}
    /// A later real disconnect after a manual return needs one new actual
    /// Inspect/Fresh before releasing the retired Session identity fence.
    pub(super) fn require_retired_inspect(&mut self,reservation:&hold::Reservation)->io::Result<()>{
        if self.seal.is_some(){return Ok(());}
        if let Some(slot)=self.links.iter().find(|l|&l.reservation==reservation).map(|l|usize::from(l.source.actor_slot)){
            if self.departures[slot].is_none(){return Err(bad("retired source not actually detached"));}
            self.held_inspected[slot]=false;
        }Ok(())
    }
    /// The caller must stage the actual Fresh/companion validation together
    /// with this small Capture clone; no live flags are changed on queue error.
    pub(super) fn confirm_held_inspect(&mut self,slot:usize,reply:&hold::Reply,fresh_revision:u64)->io::Result<()> {
        self.check_held_inspect(slot,reply,fresh_revision)?;self.held_inspected[slot]=true;Ok(())
    }
    /// Inspect is read-only. It does not mint a Link, selected-ready state or
    /// permission to attach again. A current authenticated Account is separate.
    pub(super) fn check_held_inspect(&self,slot:usize,reply:&hold::Reply,fresh_revision:u64)->io::Result<()> {
        let link=self.link(slot)?;
        if self.departures[slot].is_none()||self.seal.is_some()||reply.status!=hold::Status::Inspected||reply.replayed||reply.code.is_some()
            ||reply.revision!=fresh_revision||reply.revision!=link.admission_revision||reply.reservation.as_ref()!=Some(&link.reservation){return Err(bad("Inspect/Fresh differs from immutable still-active5 link"));}
        Ok(())
    }
    pub(super) fn freeze_outcome(&mut self,world:&World)->io::Result<bool>{
        if self.seal.is_some(){return Ok(false);}if world.id!=self.battle||!world.owner_hold_enabled()||world.started.is_none()
            ||!(2..=6).contains(&world.actors.len())||self.links.len()!=world.actors.len()||self.links.iter().enumerate().any(|(slot,l)|usize::from(l.source.actor_slot)!=slot){return Err(bad("complete real5 roster/outcome"));}
        let outcome=world.lifecycle.as_ref().and_then(|l|l.outcome()).ok_or_else(||bad("no actual Outcome"))?;
        let tick=1000u32.checked_add(u32::try_from(outcome.ended_ms/100).map_err(|_|bad("Outcome clock width"))?).ok_or_else(||bad("Outcome clock overflow"))?;
        let results=super::lifecycle_result::build(world)?;results.validate_p06t()?;
        if results.interaction_details.is_none(){return Err(bad("actual Results8 required"));}
        let raw=serde_json::to_string(&results).map_err(|_|bad("actual result serialization"))?;
        let mut finals=Vec::with_capacity(self.links.len());
        for link in &self.links{
            let slot=usize::from(link.source.actor_slot);
            finals.push((slot,self.final_from_actor(world,link,hold::Finalization::Outcome{tick},Some(raw.clone()))?));
        }
        self.seal=Some(Arc::new(Seal{results:Some(Arc::new(results)),finals}));Ok(true)
    }
    /// Called on the coherent last accepted domain snapshot before replacing a
    /// failed World. A failed speculative physics/packet candidate is not an
    /// accepted source. This closes registered actors only; unbound admissions
    /// use the separate pristine cancellation builder below.
    pub(super) fn freeze_contained_failure(&mut self,world:&World)->io::Result<bool>{
        if self.seal.is_some(){return Ok(false);}
        if world.id!=self.battle||!world.owner_hold_enabled()||self.links.is_empty()||self.links.len()>6
            ||!(1000..=37000).contains(&world.tick){return Err(bad("contained source bounds"));}
        // A real Outcome must keep its Results8; never demote it to a failure
        // merely because a subsequent native publication encountered pressure.
        if world.lifecycle.as_ref().is_some_and(|s|s.outcome().is_some()){return self.freeze_outcome(world);}
        let mut finals=Vec::with_capacity(self.links.len());
        for link in &self.links{let slot=usize::from(link.source.actor_slot);
            finals.push((slot,self.final_from_actor(world,link,hold::Finalization::ContainedFailure{tick:world.tick},None)?));}
        self.seal=Some(Arc::new(Seal{results:None,finals}));Ok(true)
    }
    fn final_from_actor(&self,world:&World,link:&Link,finalization:hold::Finalization,results_json:Option<String>)->io::Result<hold::Finish>{
            let slot=usize::from(link.source.actor_slot);
            link.check_actor(world)?;let actor=&world.actors[slot];let f=&link.reservation.frozen.loss().base;
            let fire=actor.fire.typed().ok_or_else(||bad("actual typed ammunition missing"))?;
            let counts=fire.counts();let fired=fire.fired();let lost=fire.lost();
            if fire.initial_counts()!=f.counts()||fire.accepted()!=fired.iter().map(|n|u32::from(*n)).sum::<u32>(){return Err(bad("actual accepted/fire source ledger"));}
            let events=world.ammo_detonations().iter().filter(|e|e.target()==slot).collect::<Vec<_>>();
            if events.len()>1||events.first().map_or([0;3],|e|e.lost())!=lost{return Err(bad("actual one causal detonation/lost ledger"));}
            let rows=|counts:[u16;3]|std::array::from_fn(|i|hold::Remaining{shell_compact_id:f.ammunition[i].shell_compact_id,count:counts[i]});
            let finish=hold::Finish{battle:self.battle,native_inventory_id:f.native_inventory_id,reservation_id:link.reservation.reservation_id.clone(),remaining:rows(counts),fired:rows(fired),lost:rows(lost),
                loss_event:events.first().map(|e|crate::profile13_loss091::LossEvent{shot:e.shot(),attacker_slot:e.attacker()as u8,target_slot:e.target()as u8,tick:e.tick(),device_sequence:e.device_sequence()}),
                terminal_hp:actor.health,terminal_state_json:world.terminal_state_json(slot)?,reason:if results_json.is_some(){hold::FinishReason::BattleFinished}else{hold::FinishReason::BattleFailure},results_json,source_link:Some(link.source.clone()),
                departure:self.departures[slot],finalization};
            // Validation context is inert; the real immutable worker descriptor
            // will use its current SQL CAS/key, never this syntax-only context.
            finish.validate_against(&hold::Context{account_id:link.owner.account_id.clone(),native_database_id:link.owner.database_id,command_key:"hold:seal-validate".into(),expected_revision:13,run_id:self.run.clone()},&link.reservation)?;
            Ok(finish)
    }
}

/// An actual typed5 receipt that never attached can be cancelled only with the
/// original source state. This is not an early-leave settlement or a refund of
/// a parked actor. Caller must also prove absence from every live Capture.
pub(super) fn pristine_cancel(reservation:&hold::Reservation,owner:&identity091::Profile)->io::Result<hold::Finish>{
    let f=&reservation.frozen.loss().base;
    let rows=|counts:[u16;3]|std::array::from_fn(|i|hold::Remaining{shell_compact_id:f.ammunition[i].shell_compact_id,count:counts[i]});
    let finish=hold::Finish{battle:reservation.battle,native_inventory_id:f.native_inventory_id,reservation_id:reservation.reservation_id.clone(),
        remaining:rows(f.counts()),fired:rows([0;3]),lost:rows([0;3]),loss_event:None,terminal_hp:f.max_hp,
        terminal_state_json:World::cancelled_terminal_state(f)?,reason:hold::FinishReason::Cancelled,results_json:None,
        source_link:None,departure:None,finalization:hold::Finalization::PristineCancel};
    finish.validate_against(&hold::Context{account_id:owner.account_id.clone(),native_database_id:owner.database_id,
        command_key:"hold:pristine-validate".into(),expected_revision:13,run_id:reservation.run_id.clone()},reservation)?;Ok(finish)
}
