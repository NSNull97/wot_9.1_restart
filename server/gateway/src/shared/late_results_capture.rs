//! Conservative source-linked late results. Candidate only, no active module.
//! A Link is captured from the actual admitted writer receipt AFTER World attach;
//! neither this observer nor a result/notice/transport ACK releases inventory.
use std::{io,sync::Arc};
use serde_json::{Value,json};
use sha2::{Digest,Sha256};
use crate::{identity091,profile13_v2091 as mixed,profile13_loss091 as loss};
use crate::battle091::profile13::{Context,FinishReason};
use super::{model::{self,World},lifecycle_wire::Results,profile13_session as handoff,wire};
pub(super) const POLICY:&str="test_lab.p08c.late-result-unchanged-release.v1";
pub(super) const MAX_SEAL:usize=32768;
/// RES-30 roster30: a seal of 7..30 linked actors (one escaped journal ≤256KiB
/// plus 30 final actors). Rosters 2..6 keep the fixed 32768 budget.
pub(super) const MAX_SEAL_ROSTER30:usize=393216;
pub(super) const MAX_HTTP:usize=super::lifecycle_wire::MAX_RESULT_REQUEST;
pub(super) fn seal_budget(actors:usize)->usize{if actors<=super::lifecycle_wire::LEGACY_PARTICIPANTS{MAX_SEAL}else{MAX_SEAL_ROSTER30}}
use super::model::MAX_ACTORS;
fn bad(why:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("late results capture: {why}"))}
fn digest(raw:&[u8])->String{format!("{:x}",Sha256::digest(raw))}
pub(super) fn canonical(value:&Value)->io::Result<String>{
    // serde_json without preserve_order uses sorted Map keys. Values originate
    // from strict source parsers/own serializers, never incoming pickle.
    serde_json::to_string(value).map_err(|_|bad("canonical JSON"))
}
#[derive(Clone,Debug,PartialEq,Eq)]
pub(super) enum Admission{Mixed(mixed::Reservation),Loss(loss::Reservation)}
impl Admission{
    pub(super) fn base(&self)->&mixed::Frozen{match self{Self::Mixed(r)=>&r.frozen,Self::Loss(r)=>&r.frozen.base}}
    fn run(&self)->&str{match self{Self::Mixed(r)=>&r.run_id,Self::Loss(r)=>&r.run_id}}
    fn battle(&self)->u64{match self{Self::Mixed(r)=>r.battle,Self::Loss(r)=>r.battle}}
    pub(super) fn reservation(&self)->&str{match self{Self::Mixed(r)=>&r.reservation_id,Self::Loss(r)=>&r.reservation_id}}
    pub(super) fn source_contract(&self)->&'static str{match self{Self::Mixed(_)=>"mixed-v2",Self::Loss(_)=>"loss-v1"}}
    pub(super) fn frozen_sha(&self)->&str{match self{Self::Mixed(r)=>&r.frozen.sha256,Self::Loss(r)=>&r.frozen.sha256}}
    fn active(&self)->bool{match self{Self::Mixed(r)=>r.status==mixed::ReservationStatus::Active&&r.result.is_none(),Self::Loss(r)=>r.status==loss::ReservationStatus::Active&&r.result.is_none()}}
}
#[derive(Clone)]
pub(super) struct Link{owner:Arc<identity091::Profile>,session:u32,slot:usize,team:u8,admission:Admission}
impl Link{
    pub(super) fn session(&self)->u32{self.session}
    pub(super) fn owner(&self)->&Arc<identity091::Profile>{&self.owner}
    pub(super) fn slot(&self)->usize{self.slot}
    pub(super) fn admission(&self)->&Admission{&self.admission}
    pub(super) fn value(&self,final_actor:&FinalActor)->Value{json!({"account_id":self.owner.account_id,"native_database_id":self.owner.database_id,
        "slot":self.slot,"vehicle_id":wire::vehicle_id(self.slot).expect("validated slot"),"team":self.team,
        "reservation_id":self.admission.reservation(),"native_inventory_id":self.admission.base().native_inventory_id,
        "source_contract":self.admission.source_contract(),"frozen_sha256":self.admission.frozen_sha(),"final_actor":final_actor.value()})}
    fn same(&self,other:&Self)->bool{self.owner.account_id==other.owner.account_id&&self.owner.database_id==other.owner.database_id
        &&self.session==other.session&&self.slot==other.slot&&self.team==other.team&&self.admission==other.admission}
    fn validate_actor(&self,world:&World)->io::Result<()>{
        let a=world.actors.get(self.slot).ok_or_else(||bad("missing linked actor"))?;let f=self.admission.base();f.validate_owned(&self.owner.account_id)?;
        if world.id!=self.admission.battle()||world.team(self.slot)?!=self.team||a.identity.account!=self.owner.account_id
            ||a.identity.database!=self.owner.database_id||a.identity.name!=self.owner.name||a.vehicle_kind()!=f.kind||a.owned_v2.as_ref()!=Some(f)
            ||!world.mixed_ammo(){return Err(bad("actor admission identity/source changed"));}
        match &self.admission{
            Admission::Mixed(_)=>if world.ammo_detonation_enabled()||a.owned_loss.is_some(){return Err(bad("mixed/loss actor mode"));},
            Admission::Loss(r)=>if !world.ammo_detonation_enabled()||a.owned_loss.as_ref()!=Some(&r.frozen){return Err(bad("loss wrapper changed"));},
        }Ok(())
    }
}
#[derive(Clone,Debug,PartialEq,Eq)]
pub(super) struct FinalActor{hp:i16,state:Value,remaining:[mixed::Remaining;3],fired:[mixed::Remaining;3],lost:[mixed::Remaining;3],loss_event:Option<loss::LossEvent>}
fn stacks(rows:&[mixed::Remaining;3])->Value{Value::Array(rows.iter().map(|a|json!({"shell_compact_id":a.shell_compact_id,"count":a.count})).collect())}
impl FinalActor{
    pub(super) fn value(&self)->Value{json!({"terminal_hp":self.hp,"terminal_state":self.state,
        "remaining_ammunition":stacks(&self.remaining),"fired_ammunition":stacks(&self.fired),"lost_ammunition":stacks(&self.lost),
        "loss_event":self.loss_event.map(|e|json!({"shot":e.shot,"attacker_slot":e.attacker_slot,"target_slot":e.target_slot,"tick":e.tick,"device_sequence":e.device_sequence}))})}
    fn validate(&self,link:&Link)->io::Result<()>{
        let frozen=link.admission.base();mixed::validate_terminal_json(&canonical(&self.state)?,frozen,self.hp)?;
        for i in 0..3{let initial=&frozen.ammunition[i];
            if [self.remaining[i],self.fired[i],self.lost[i]].iter().any(|r|r.shell_compact_id!=initial.shell_compact_id)
                ||u32::from(self.remaining[i].count)+u32::from(self.fired[i].count)+u32::from(self.lost[i].count)!=u32::from(initial.count){return Err(bad("per-stack conservation/source order"));}
        }
        if matches!(link.admission,Admission::Mixed(_))&&(self.loss_event.is_some()||self.lost.iter().any(|s|s.count!=0)){return Err(bad("loss in mixed-v2 record"));}
        if let Some(e)=self.loss_event{
            if self.hp!=0||e.target_slot as usize!=link.slot||self.lost.iter().all(|a|a.count==0)||self.remaining.iter().any(|a|a.count!=0)
                ||self.state["devices"].as_array().is_none_or(|a|!a.iter().any(|d|d["extra_index"]==27&&d["health"]==0))
                ||self.state["death"]["killer_slot"].as_u64()!=Some(u64::from(e.attacker_slot))
                ||self.state["death"]["tick"].as_u64()!=Some(u64::from(e.tick)){return Err(bad("actual loss cause/device/death"));}
        }else if self.lost.iter().any(|a|a.count!=0){return Err(bad("lost shells without event"));}Ok(())
    }
    fn capture(world:&World,link:&Link)->io::Result<Self>{
        link.validate_actor(world)?;let actor=&world.actors[link.slot];let fire=actor.fire.typed().ok_or_else(||bad("missing typed fire ledger"))?;
        let f=link.admission.base();if fire.initial_counts()!=f.counts()||fire.accepted()!=fire.fired().iter().map(|n|u32::from(*n)).sum::<u32>(){
            return Err(bad("frozen initial/accepted firing ledger"));}
        let rows=|counts:[u16;3]|std::array::from_fn(|i|mixed::Remaining{shell_compact_id:f.ammunition[i].shell_compact_id,count:counts[i]});
        let records=world.ammo_detonations().iter().filter(|e|e.target()==link.slot).collect::<Vec<_>>();
        if records.len()>1{return Err(bad("duplicate loss event"));}
        let event=records.first().map(|e|loss::LossEvent{shot:e.shot(),attacker_slot:e.attacker()as u8,target_slot:e.target()as u8,tick:e.tick(),device_sequence:e.device_sequence()});
        if records.first().map_or([0;3],|e|e.lost())!=fire.lost(){return Err(bad("loss journal versus armament ledger"));}
        let state=mixed::validate_terminal_json(&world.terminal_state_json(link.slot)?,f,actor.health)?.raw;
        let out=Self{hp:actor.health,state,remaining:rows(fire.counts()),fired:rows(fire.fired()),lost:rows(fire.lost()),loss_event:event};out.validate(link)?;Ok(out)
    }
}
#[derive(Clone,Debug,PartialEq,Eq)]
enum FrozenTerminal{Mixed(handoff::TerminalV2),Loss(handoff::TerminalLoss)}
#[derive(Clone,Debug,PartialEq,Eq)]
struct Release{terminal:FrozenTerminal,actor:FinalActor,finished:Option<(u64,String)>}
#[derive(Clone,Debug)]
pub(super) struct Seal{raw:String,sha:String,results:Arc<Results>,actors:Vec<FinalActor>}
impl Seal{
    pub(super) fn raw(&self)->&str{&self.raw}
    pub(super) fn sha256(&self)->&str{&self.sha}
    pub(super) fn results(&self)->&Arc<Results>{&self.results}
}
/// One battle's immutable links and seal, owned outside Session receive clones.
/// The loop may clone this SMALL observer transaction, never the whole World.
#[derive(Clone)]
/// RES-30: `releases` is MAX_ACTORS rows on the heap. The Capture is cloned by
/// value on the gateway main thread (1MB on Windows); an inline [_;30] made it ~21KB.
pub(super) struct Capture{run:String,battle:u64,links:Vec<Link>,releases:Box<[Option<Release>]>,seal:Option<Arc<Seal>>}
impl Capture{
    pub(super) fn new(run:String,battle:u64)->io::Result<Self>{
        if run.len()!=36||!run.bytes().enumerate().all(|(i,b)|if [8,13,18,23].contains(&i){b==b'-'}else{b.is_ascii_digit()||(b'a'..=b'f').contains(&b)})
            ||!matches!(run.as_bytes()[14],b'1'..=b'5'){return Err(bad("run UUID"));}
        if battle==0||battle>i64::MAX as u64{return Err(bad("native arena bound"));}
        Ok(Self{run,battle,links:Vec::new(),releases:(0..MAX_ACTORS).map(|_|None).collect(),seal:None})
    }
    pub(super) fn run(&self)->&str{&self.run}
    pub(super) fn battle(&self)->u64{self.battle}
    pub(super) fn release_reason(&self,slot:usize)->io::Result<Option<&'static str>>{
        self.link(slot)?;Ok(self.releases[slot].as_ref().map(|r|match &r.terminal{
            FrozenTerminal::Mixed(t)=>t.reason.name(),FrozenTerminal::Loss(t)=>t.reason.name()}))
    }
    pub(super) fn links(&self)->&[Link]{&self.links}
    pub(super) fn seal(&self)->Option<&Arc<Seal>>{self.seal.as_ref()}
    pub(super) fn register(&mut self,world:&World,slot:usize,session:u32,owner:Arc<identity091::Profile>,admission:Admission)->io::Result<bool>{
        if self.seal.is_some()||world.id!=self.battle||slot>=MAX_ACTORS||session==0||admission.run()!=self.run||admission.battle()!=self.battle||!admission.active(){return Err(bad("register battle/source/phase"));}
        let link=Link{owner,session,slot,team:world.team(slot)?,admission};link.validate_actor(world)?;
        if world.actors[slot].session!=Some(session){return Err(bad("register after actual attach only"));}
        if let Some(old)=self.links.iter().find(|l|l.slot==slot){if old.same(&link){return Ok(false);}return Err(bad("conflicting linked slot"));}
        // Reservation IDs are scoped by authenticated owner in the store.
        // Owner/native/session uniqueness is authoritative; cross-owner equal
        // reservation strings must not become an invented global SQL rule.
        if self.links.len()>=MAX_ACTORS||self.links.iter().any(|l|l.session==session||l.owner.account_id==link.owner.account_id||l.owner.database_id==link.owner.database_id){
            return Err(bad("duplicate admission owner/native/session"));}
        self.links.push(link);self.links.sort_by_key(|l|l.slot);Ok(true)
    }
    fn link(&self,slot:usize)->io::Result<&Link>{self.links.iter().find(|l|l.slot==slot).ok_or_else(||bad("unknown source-linked slot"))}
    pub(super) fn observe_terminal_v2(&mut self,slot:usize,t:&handoff::TerminalV2)->io::Result<bool>{
        t.validate()?;let link=self.link(slot)?;
        if !matches!(&link.admission,Admission::Mixed(r)if r==&t.reservation)||t.native_database_id!=link.owner.database_id{return Err(bad("release source terminal identity"));}
        let f=link.admission.base();let empty=std::array::from_fn(|i|mixed::Remaining{shell_compact_id:f.ammunition[i].shell_compact_id,count:0});
        let fired=std::array::from_fn(|i|mixed::Remaining{shell_compact_id:f.ammunition[i].shell_compact_id,count:f.ammunition[i].count-t.remaining_ammunition[i].count});
        let actor=FinalActor{hp:t.terminal_hp,state:mixed::validate_terminal_json(&t.terminal_state_json,f,t.terminal_hp)?.raw,
            remaining:t.remaining_ammunition,fired,lost:empty,loss_event:None};actor.validate(link)?;
        self.retain(slot,t.reason,Release{terminal:FrozenTerminal::Mixed(t.clone()),actor,finished:None})
    }
    pub(super) fn observe_terminal_loss(&mut self,slot:usize,t:&handoff::TerminalLoss)->io::Result<bool>{
        t.validate()?;let link=self.link(slot)?;
        if !matches!(&link.admission,Admission::Loss(r)if r==&t.reservation)||t.native_database_id!=link.owner.database_id{return Err(bad("release loss source identity"));}
        let actor=FinalActor{hp:t.terminal_hp,state:mixed::validate_terminal_json(&t.terminal_state_json,link.admission.base(),t.terminal_hp)?.raw,
            remaining:t.remaining_ammunition,fired:t.fired_ammunition,lost:t.lost_ammunition,loss_event:t.loss_event};actor.validate(link)?;
        self.retain(slot,t.reason,Release{terminal:FrozenTerminal::Loss(t.clone()),actor,finished:None})
    }
    fn retain(&mut self,slot:usize,reason:FinishReason,release:Release)->io::Result<bool>{
        if !matches!(reason,FinishReason::ManualLeave|FinishReason::Disconnect){return Ok(false);}
        if let Some(old)=&self.releases[slot]{if old.terminal==release.terminal&&old.actor==release.actor{return Ok(false);}return Err(bad("immutable first-cause release"));}
        self.releases[slot]=Some(release);Ok(true)
    }
    fn completion_owner(&self,slot:usize,session:u32,owner:&identity091::Profile,c:&Context)->io::Result<()>{let link=self.link(slot)?;
        if session!=link.session||owner.account_id!=link.owner.account_id||owner.database_id!=link.owner.database_id
            ||c.account_id!=link.owner.account_id||c.native_database_id!=link.owner.database_id||c.run_id!=self.run{return Err(bad("Finished completion source owner/run/session"));}Ok(())}
    /// Prepare on a cloned Capture before actual normal delivery; commit ONLY
    /// after that delivery succeeded. Parsed actual worker Completion required.
    pub(super) fn observe_finished_v2(&mut self,slot:usize,c:&handoff::CompletionV2)->io::Result<bool>{
        self.completion_owner(slot,c.session,&c.old_owner,&c.context)?;
        let release=self.releases[slot].as_ref().ok_or_else(||bad("Finished before original terminal"))?;
        let FrozenTerminal::Mixed(t)=&release.terminal else{return Err(bad("Finished source mode"));};
        if c.reply.status!=mixed::Status::Finished||c.request!=t.request()||c.refresh_error.is_some()||c.fresh.is_none()
            ||!c.reply.reservation.as_ref().is_some_and(|r|r.status==mixed::ReservationStatus::Finished&&r.reservation_id==t.reservation.reservation_id
                &&r.frozen==t.reservation.frozen&&r.run_id==self.run&&r.battle==self.battle){return Err(bad("unsettled/mismatched actual Finished completion"));}
        self.finished(slot,c.reply.revision,&c.context.command_key)
    }
    pub(super) fn observe_finished_loss(&mut self,slot:usize,c:&handoff::CompletionLoss)->io::Result<bool>{
        self.completion_owner(slot,c.session,&c.old_owner,&c.context)?;
        let release=self.releases[slot].as_ref().ok_or_else(||bad("Finished before original terminal"))?;
        let FrozenTerminal::Loss(t)=&release.terminal else{return Err(bad("Finished source mode"));};
        if c.reply.status!=loss::Status::Finished||c.request!=t.request()||c.refresh_error.is_some()||c.fresh.is_none()
            ||!c.reply.reservation.as_ref().is_some_and(|r|r.status==loss::ReservationStatus::Finished&&r.reservation_id==t.reservation.reservation_id
                &&r.frozen==t.reservation.frozen&&r.run_id==self.run&&r.battle==self.battle){return Err(bad("unsettled/mismatched actual loss Finished"));}
        self.finished(slot,c.reply.revision,&c.context.command_key)
    }
    fn finished(&mut self,slot:usize,revision:u64,key:&str)->io::Result<bool>{
        if revision<14||key.is_empty()||key.len()>96{return Err(bad("Finished source receipt revision/key"));}
        let release=self.releases[slot].as_mut().ok_or_else(||bad("missing terminal"))?;
        if let Some(old)=&release.finished{if old==&(revision,key.to_owned()){return Ok(false);}return Err(bad("conflicting immutable Finished proof"));}
        release.finished=Some((revision,key.into()));Ok(true)
    }
    pub(super) fn capture_final(&mut self,world:&World)->io::Result<bool>{
        if world.id!=self.battle{return Err(bad("final capture belongs to another battle"));}
        // Lifecycle freezes combat facts at Outcome, while later Account return
        // legitimately detaches surviving Sessions. Never rebuild premature_leave
        // or other presentation fields from that later membership.
        if self.seal.is_some(){return Ok(false);}
        if world.started.is_none()||!world.lifecycle.as_ref().is_some_and(|l|l.outcome().is_some())
            ||!(2..=MAX_ACTORS).contains(&world.actors.len())||self.links.len()!=world.actors.len()||self.links.iter().enumerate().any(|(slot,l)|l.slot!=slot){return Err(bad("final outcome/complete linked roster"));}
        let mut actors=Vec::with_capacity(self.links.len());for link in &self.links{actors.push(FinalActor::capture(world,link)?);}
        let results=super::lifecycle_result::build(world)?;results.validate_p06t()?;
        for(link,actor)in self.links.iter().zip(&actors){let p=results.participants.iter().find(|p|p.account_dbid==link.owner.database_id).ok_or_else(||bad("result owner roster"))?;
            if p.vehicle_id!=wire::vehicle_id(link.slot)?||p.team!=link.team||p.health!=actor.hp||u32::from(p.shots)!=actor.fired.iter().map(|a|u32::from(a.count)).sum::<u32>(){
                return Err(bad("result versus final source actor"));}}
        let results_json=canonical(&serde_json::to_value(&results).map_err(|_|bad("result canonical value"))?)?;
        let raw=canonical(&json!({"version":1,"policy":POLICY,"run_id":self.run,"battle_id":format!("{}:{}",self.run,self.battle),"arena_id":self.battle.to_string(),
            "results_json":results_json,"actors":self.links.iter().zip(&actors).map(|(link,actor)|link.value(actor)).collect::<Vec<_>>()}))?;
        if raw.len()>seal_budget(actors.len()){return Err(bad("final seal exceeds its roster budget; retain diagnostic"));}
        let sha=digest(raw.as_bytes());
        self.seal=Some(Arc::new(Seal{raw,sha,results:Arc::new(results),actors}));Ok(true)
    }
    /// None = no eligible terminal or still pending actual Finish. Never treat
    /// that state as released or build an append task without a real stamp.
    pub(super) fn eligible(&self,slot:usize)->io::Result<Option<u64>>{
        self.link(slot)?;let Some(seal)=&self.seal else{return Ok(None);};
        let Some(release)=&self.releases[slot]else{return Ok(None);};let Some((revision,_))=&release.finished else{return Ok(None);};
        if seal.actors.get(slot)!=Some(&release.actor){return Err(bad("LATE_ACTOR_STATE_CHANGED"));}Ok(Some(*revision))
    }
}

#[cfg(test)]
pub(super) fn saved_sql_component_fixture()->(Capture,World,std::time::Instant){
    let mut f=tests::fixture();tests::settle_from_saved_actual_reply(&mut f);tests::final_outcome(&mut f);
    f.capture.capture_final(&f.world).unwrap();(f.capture,f.world,f.now)
}
#[cfg(test)]
#[path="late_results_capture_tests.rs"]
mod tests;
