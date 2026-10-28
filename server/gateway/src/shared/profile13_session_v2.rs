//! Versioned mixed-ammunition handoff. No v1 frozen-loadout conversions.
use super::{bad,load_fresh,Fresh,World,WORKER_ACTIVE};
use std::{io,sync::{Arc,mpsc,atomic::Ordering},thread::{self,JoinHandle}};
use crate::identity091;
use crate::battle091::profile13::{Context,FinishReason};
use crate::profile13_v2091::{self as codec,Request,Reply,Status,Reservation,ReservationStatus,Remaining};

#[derive(Clone,Debug,PartialEq,Eq)]
pub(crate) struct TerminalV2{
    pub(crate) reservation:Reservation,
    pub(crate) remaining_ammunition:[Remaining;3],
    pub(crate) terminal_hp:i16,
    pub(crate) terminal_state_json:String,
    pub(crate) reason:FinishReason,
    pub(crate) results_json:Option<String>,
    pub(crate) native_database_id:i32,
}
impl TerminalV2{
    pub(crate) fn validate(&self)->io::Result<()>{
        let r=&self.reservation;let account=r.frozen.vehicle_inventory_id.get(..36).ok_or_else(||bad("v2 terminal owner"))?;
        r.frozen.validate_owned(account)?;
        if r.status!=ReservationStatus::Active||r.result.is_some()||r.battle==0||self.native_database_id<=0
            ||self.remaining_ammunition.iter().zip(&r.frozen.ammunition).any(|(a,b)|a.shell_compact_id!=b.shell_compact_id||a.count>b.count){return Err(bad("v2 terminal frozen outcome"));}
        codec::validate_terminal_json(&self.terminal_state_json,&r.frozen,self.terminal_hp)?;
        codec::encode_request(&Context{account_id:account.into(),native_database_id:self.native_database_id,command_key:"p06t:validate".into(),
            expected_revision:13,run_id:r.run_id.clone()},&self.request())?;Ok(())
    }
    pub(crate) fn from_actor_result(reservation:&Reservation,world:&World,slot:usize,session:u32,reason:FinishReason,
        result:Option<&super::super::lifecycle_wire::Results>)->io::Result<Self>{
        let actor=world.owned(slot,session)?;
        reservation.frozen.validate_owned(&actor.identity.account)?;
        if world.ammo_detonation_enabled()||actor.owned_loss.is_some()||!world.mixed_ammo()||world.id!=reservation.battle||actor.vehicle_kind()!=reservation.frozen.kind
            ||actor.owned_v2.as_ref()!=Some(&reservation.frozen){return Err(bad("v2 terminal actor battle/frozen loadout"));}
        let counts=actor.fire.typed().ok_or_else(||bad("v2 actor lacks typed ammunition"))?.counts();
        let terminal=Self{reservation:reservation.clone(),remaining_ammunition:std::array::from_fn(|i|Remaining{
            shell_compact_id:reservation.frozen.ammunition[i].shell_compact_id,count:counts[i]}),terminal_hp:actor.health,
            terminal_state_json:world.terminal_state_json(slot)?,reason,native_database_id:actor.identity.database,
            results_json:result.map(serde_json::to_string).transpose().map_err(|_|bad("v2 result serialization"))?};
        terminal.validate()?;Ok(terminal)
    }
    pub(crate) fn cancelled(reservation:&Reservation,native_database_id:i32)->io::Result<Self>{
        let f=&reservation.frozen;let terminal=Self{reservation:reservation.clone(),remaining_ammunition:f.ammunition.each_ref().map(|a|Remaining{
            shell_compact_id:a.shell_compact_id,count:a.count}),terminal_hp:f.max_hp,
            terminal_state_json:World::cancelled_terminal_state(f)?,reason:FinishReason::Cancelled,results_json:None,native_database_id};
        terminal.validate()?;Ok(terminal)
    }
    pub(crate) fn request(&self)->Request{Request::Finish{battle:self.reservation.battle,native_inventory_id:self.reservation.frozen.native_inventory_id,
        reservation_id:self.reservation.reservation_id.clone(),remaining_ammunition:self.remaining_ammunition,terminal_hp:self.terminal_hp,
        terminal_state_json:self.terminal_state_json.clone(),reason:self.reason,results_json:self.results_json.clone()}}
}

pub(crate) struct CompletionV2{
    pub(crate) session:u32,pub(crate) old_owner:Arc<identity091::Profile>,pub(crate) context:Context,
    pub(crate) request:Request,pub(crate) reply:Reply,pub(crate) fresh:Option<Fresh>,pub(crate) refresh_error:Option<io::Error>,
}
fn work(session:u32,owner:Arc<identity091::Profile>,config:Arc<identity091::Config>,context:Context,request:Request)->io::Result<CompletionV2>{
    let reply=config.service_battle_v2(&owner,&context,&request)?;
    // Preparing abort cannot unlock an obsolete Account snapshot after a
    // null Inspect. This additional refresh belongs ONLY to explicit training
    // rooms; strict service_battle_v2 has already parsed the exact Inspect.
    let inspect_refresh=config.training_rooms && request==Request::Inspect && reply.status==Status::Inspected
        && reply.reservation.is_none() && reply.legacy_reservation.is_none();
    let(fresh,refresh_error)=if matches!(reply.status,Status::Ready|Status::Admitted|Status::Finished)||inspect_refresh{
        match load_fresh(&config,&owner,reply.revision){Ok(f)=>(Some(f),None),Err(e)=>(None,Some(e))}
    }else{(None,None)};
    Ok(CompletionV2{session,old_owner:owner,context,request,reply,fresh,refresh_error})
}
pub(crate) struct JobV2{
    pub(crate) session:u32,pub(crate) owner:Arc<identity091::Profile>,pub(crate) context:Context,pub(crate) request:Request,
    receiver:Option<mpsc::Receiver<io::Result<CompletionV2>>>,worker:Option<JoinHandle<()>>,
}
impl JobV2{
    pub(crate) fn start(session:u32,owner:Arc<identity091::Profile>,config:Arc<identity091::Config>,context:Context,request:Request)->io::Result<Self>{
        codec::encode_request(&context,&request)?;
        if config.p06t_ammo_rack_detonation||session==0||context.account_id!=owner.account_id||context.native_database_id!=owner.database_id||!config.p06t_mixed_ammo
            ||!config.profile13_battle||context.run_id!=config.battle_run_id{return Err(bad("v2 job authenticated owner/run/opt-in"));}
        if WORKER_ACTIVE.compare_exchange(false,true,Ordering::AcqRel,Ordering::Acquire).is_err(){return Err(bad("another battle writer call is still active"));}
        let(sender,receiver)=mpsc::sync_channel(1);let(task_owner,task_context,task_request)=(owner.clone(),context.clone(),request.clone());let operation=request.operation();
        let started=thread::Builder::new().name("p06t-account-writer".into()).spawn(move||{
            struct Active;impl Drop for Active{fn drop(&mut self){WORKER_ACTIVE.store(false,Ordering::Release);}}let _active=Active;
            let result=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||work(session,task_owner,config,task_context,task_request)))
                .unwrap_or_else(|_|Err(bad("v2 writer thread panicked; recover immutable operation")));
            match &result{
                Ok(c)=>println!("P06T_WRITER_JOB_RESULT session={session} operation={operation} status={:?} revision={} refreshed={} refresh_failed={} native_delivery=not_yet_dispatched",c.reply.status,c.reply.revision,c.fresh.is_some(),c.refresh_error.is_some()),
                Err(e)=>println!("P06T_WRITER_JOB_ERROR session={session} operation={operation} error={e} outcome_requires_recovery=true"),
            }
            if sender.send(result).is_err(){println!("P06T_JOB_OBSERVER_RETIRED session={session} operation={operation} durable_ledger_retained=true");}
        });
        let worker=match started{Ok(w)=>w,Err(e)=>{WORKER_ACTIVE.store(false,Ordering::Release);return Err(e);}};
        Ok(Self{session,owner,context,request,receiver:Some(receiver),worker:Some(worker)})
    }
    fn join_finished(&mut self)->io::Result<()>{
        if self.worker.as_ref().is_some_and(|w|w.is_finished())&&self.worker.take().ok_or_else(||bad("v2 writer handle"))?.join().is_err(){return Err(bad("v2 writer join panicked"));}Ok(())
    }
    pub(crate) fn poll(&mut self)->Option<io::Result<CompletionV2>>{
        if self.worker.as_ref().is_some_and(|w|!w.is_finished()){return None;}
        let result=match self.receiver.as_ref()?.try_recv(){Ok(r)=>r,Err(mpsc::TryRecvError::Empty)=>return None,
            Err(mpsc::TryRecvError::Disconnected)=>Err(bad("v2 writer channel ended; recover immutable operation"))};
        self.receiver=None;if let Err(e)=self.join_finished(){return Some(Err(e));}Some(result)
    }
}
impl Drop for JobV2{fn drop(&mut self){drop(self.receiver.take());if let Err(e)=self.join_finished(){println!("P06T_JOB_DROP_ERROR session={} error={e}",self.session);}}}

#[cfg(test)]
mod tests{
    use super::*;
    fn reservation()->Reservation{
        let v:serde_json::Value=serde_json::from_slice(include_bytes!("../../../../tests/fixtures/p06t-writer-vectors.json")).unwrap();
        let row=v["vectors"].as_array().unwrap().iter().find(|r|r["request"]["operation"]=="admit").unwrap();let r=&row["request"];
        let c=Context{account_id:r["account_id"].as_str().unwrap().into(),native_database_id:r["native_database_id"].as_i64().unwrap()as i32,
            command_key:r["command_key"].as_str().unwrap().into(),expected_revision:r["expected_revision"].as_u64().unwrap(),run_id:r["run_id"].as_str().unwrap().into()};
        codec::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&c,&Request::Admit{battle:9007199254740993,native_inventory_id:1}).unwrap().reservation.unwrap()
    }
    #[test]fn p06t_terminal_freezes_each_owned_stack_and_actual_journal_before_actor_detach(){
        let r=reservation();let now=std::time::Instant::now();
        let mut w=World::new_for_roster(r.battle,now,crate::map_profile091::MapId::Karelia,2).unwrap();w.enable_mixed_ammo().unwrap();
        let slot=w.attach_owned_v2(super::super::super::model::Identity{account:r.frozen.vehicle_inventory_id[..36].into(),database:1,name:"actual writer".into()},7,&r.frozen).unwrap();
        w.actors[slot].fire.apply_typed(&[crate::p06t_armament091::Command::Shoot],now).unwrap();w.actors[slot].health=23;
        let t=TerminalV2::from_actor_result(&r,&w,slot,7,FinishReason::ManualLeave,None).unwrap();
        assert_eq!(t.remaining_ammunition.map(|a|a.count),[0,3,11]);assert_eq!(t.terminal_hp,23);
        let state=codec::validate_terminal_json(&t.terminal_state_json,&r.frozen,23).unwrap();assert!(state.crew_active);assert_eq!(state.roster_size,1);
        w.detach(7).unwrap();assert!(TerminalV2::from_actor_result(&r,&w,slot,7,FinishReason::Disconnect,None).is_err());
        let mut p=super::super::State::new(r.run_id.clone(),19).unwrap();p.reservation_v2=Some(r.clone());
        assert!(p.retain_terminal_v2(t.clone()).unwrap());let mut repeated=t.clone();repeated.reason=FinishReason::Disconnect;
        assert!(!p.retain_terminal_v2(repeated).unwrap());assert_eq!(p.pending_return_v2,Some(t.clone()));
        let before=p.clone();let mut conflicting=t;conflicting.remaining_ammunition[1].count-=1;
        assert!(p.retain_terminal_v2(conflicting).is_err());assert_eq!(p,before);
    }
    #[test]fn res30_terminal_state_accepts_a_thirty_actor_roster(){
        let r=reservation();let t=TerminalV2::cancelled(&r,1).unwrap();
        let mut v:serde_json::Value=serde_json::from_str(&t.terminal_state_json).unwrap();
        for n in [7u64,30]{v["roster_size"]=n.into();
            assert_eq!(codec::validate_terminal_json(&serde_json::to_string(&v).unwrap(),&r.frozen,90).unwrap().roster_size as u64,n);}
        v["roster_size"]=31.into();assert!(codec::validate_terminal_json(&serde_json::to_string(&v).unwrap(),&r.frozen,90).is_err());
        // A killer in slot 29 of a 30-actor roster; slot 30 is outside it.
        v["roster_size"]=30.into();v["crew_active"]=false.into();
        for c in v["crew"].as_array_mut().unwrap(){c["alive"]=false.into();}
        v["death"]=serde_json::json!({"reason":0,"killer_slot":29,"tick":1200});
        let state=codec::validate_terminal_json(&serde_json::to_string(&v).unwrap(),&r.frozen,0).unwrap();assert_eq!(state.killer_slot,Some(29));
        v["death"]["killer_slot"]=30.into();assert!(codec::validate_terminal_json(&serde_json::to_string(&v).unwrap(),&r.frozen,0).is_err());
    }
    #[test]fn p06t_cancelled_queue_refunds_real_three_stacks_and_initial_source_journal_without_actor(){
        let r=reservation();let t=TerminalV2::cancelled(&r,1).unwrap();
        assert_eq!(t.remaining_ammunition.map(|a|a.count),[0,4,11]);assert_eq!(t.terminal_hp,90);
        let j=codec::validate_terminal_json(&t.terminal_state_json,&r.frozen,90).unwrap();assert_eq!(j.roster_size,0);assert!(j.crew_active);
        assert!(j.raw["devices"].as_array().unwrap().iter().all(|d|d["health"]==d["max_health"]));
        let mut p=super::super::State::new(r.run_id.clone(),19).unwrap();assert!(p.garage_idle());p.reservation_v2=Some(r);
        assert!(p.has_reservation());assert!(!p.garage_idle());p.retain_terminal_v2(t).unwrap();assert!(p.has_pending_return());
    }
    #[test]fn p06t_job_channel_delivery_waits_for_actual_worker_exit(){
        let r=reservation();let owner=Arc::new(identity091::Profile{account_id:r.frozen.vehicle_inventory_id[..36].into(),database_id:1,name:"actual writer".into(),fixture_dir:std::path::PathBuf::new()});
        let mut p=super::super::State::new(r.run_id,19).unwrap();let context=p.next_context(&owner,7).unwrap();
        let(sender,receiver)=mpsc::sync_channel(1);let(release,wait)=mpsc::sync_channel(1);let(sent,delivered)=mpsc::sync_channel(1);
        let worker=thread::spawn(move||{sender.send(Err(bad("synthetic v2 executor result"))).unwrap();sent.send(()).unwrap();wait.recv().unwrap();});delivered.recv().unwrap();
        let mut job=JobV2{session:7,owner,context,request:Request::Inspect,receiver:Some(receiver),worker:Some(worker)};
        assert!(job.poll().is_none());release.send(()).unwrap();job.worker.take().unwrap().join().unwrap();assert!(job.poll().unwrap().is_err());assert!(job.poll().is_none());
    }
}
