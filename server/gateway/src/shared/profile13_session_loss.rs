//! Version4 handoff. Fired shells and lost shells remain distinct.
use super::{bad,load_fresh,Fresh,World,WORKER_ACTIVE};
use std::{io,sync::{Arc,mpsc,atomic::Ordering},thread::{self,JoinHandle}};
use crate::identity091;
use crate::battle091::profile13::{Context,FinishReason};
use crate::profile13_loss091::{self as codec,Request,Reply,Status,Reservation,ReservationStatus,Remaining};

#[derive(Clone,Debug,PartialEq,Eq)]
pub(crate) struct TerminalLoss{
    pub(crate) reservation:Reservation,
    pub(crate) remaining_ammunition:[Remaining;3],
    pub(crate) fired_ammunition:[Remaining;3],
    pub(crate) lost_ammunition:[Remaining;3],
    pub(crate) loss_event:Option<codec::LossEvent>,
    pub(crate) terminal_hp:i16,
    pub(crate) terminal_state_json:String,
    pub(crate) reason:FinishReason,
    pub(crate) results_json:Option<String>,
    pub(crate) native_database_id:i32,
}
impl TerminalLoss{
    pub(crate) fn validate(&self)->io::Result<()>{
        let r=&self.reservation;let f=&r.frozen.base;
        let account=f.vehicle_inventory_id.get(..36).ok_or_else(||bad("loss terminal owner"))?;
        r.frozen.validate_owned(account)?;
        if r.status!=ReservationStatus::Active||r.result.is_some()||r.battle==0||self.native_database_id<=0{
            return Err(bad("loss terminal immutable reservation"));
        }
        for i in 0..3{
            let initial=&f.ammunition[i];let a=self.remaining_ammunition[i];let b=self.fired_ammunition[i];let c=self.lost_ammunition[i];
            if [a,b,c].iter().any(|s|s.shell_compact_id!=initial.shell_compact_id)
                ||u32::from(a.count)+u32::from(b.count)+u32::from(c.count)!=u32::from(initial.count){return Err(bad("loss terminal per-stack conservation"));}
        }
        let state=crate::profile13_v2091::validate_terminal_json(&self.terminal_state_json,f,self.terminal_hp)?;
        if let Some(e)=self.loss_event{
            let bay=state.raw["devices"].as_array().and_then(|a|a.iter().find(|d|d["extra_index"]==27));
            if self.terminal_hp!=0||self.remaining_ammunition.iter().any(|a|a.count!=0)||self.lost_ammunition.iter().all(|a|a.count==0)
                ||bay.is_none_or(|d|d["health"]!=0)||state.killer_slot!=Some(e.attacker_slot)
                ||state.raw["death"]["tick"].as_u64()!=Some(e.tick as u64)||e.target_slot>=state.roster_size||e.attacker_slot>=state.roster_size{
                return Err(bad("loss terminal source device/death/cause"));
            }
        }else if self.lost_ammunition.iter().any(|a|a.count!=0){return Err(bad("lost ammunition without detonation"));}
        if self.reason==FinishReason::Cancelled&&(self.loss_event.is_some()||self.terminal_hp!=f.max_hp
            ||self.fired_ammunition.iter().chain(&self.lost_ammunition).any(|a|a.count!=0)){return Err(bad("loss queue cancellation must be pristine"));}
        if let Some(raw)=&self.results_json{
            let stats=super::super::lifecycle_wire::Results::from_json_p06t(raw)?;
            let own=stats.participants.iter().find(|p|p.account_dbid==self.native_database_id).ok_or_else(||bad("loss result owner"))?;
            if own.shots!=self.fired_ammunition.iter().map(|s|s.count).sum::<u16>()||own.health!=self.terminal_hp{
                return Err(bad("loss must not inflate shots in result"));
            }
        }
        codec::encode_request(&Context{account_id:account.into(),native_database_id:self.native_database_id,
            command_key:"p06t:loss:validate".into(),expected_revision:13,run_id:r.run_id.clone()},&self.request())?;Ok(())
    }
    pub(crate) fn from_actor_result(reservation:&Reservation,world:&World,slot:usize,session:u32,reason:FinishReason,
        result:Option<&super::super::lifecycle_wire::Results>)->io::Result<Self>{
        let actor=world.owned(slot,session)?;let f=&reservation.frozen.base;
        reservation.frozen.validate_owned(&actor.identity.account)?;
        if !world.mixed_ammo()||world.id!=reservation.battle||actor.vehicle_kind()!=f.kind||actor.owned_loss.as_ref()!=Some(&reservation.frozen){
            return Err(bad("loss terminal actor battle/frozen contract"));
        }
        let fire=actor.fire.typed().ok_or_else(||bad("loss actor lacks typed ammunition"))?;
        let counts=fire.counts();let event=world.ammo_detonations().iter().find(|e|e.target()==slot);
        let lost=event.map_or([0;3],|e|e.lost());
        let mut fired=[0u16;3];for i in 0..3{
            fired[i]=f.ammunition[i].count.checked_sub(counts[i]).and_then(|n|n.checked_sub(lost[i])).ok_or_else(||bad("loss actor ammunition conservation"))?;
        }
        if fire.initial_counts()!=f.ammunition.each_ref().map(|a|a.count)||fire.fired()!=fired||fire.lost()!=lost||u32::from(fired.iter().sum::<u16>())!=fire.accepted(){return Err(bad("loss actor accepted-shot ledger differs from spending"));}
        let rows=|counts:[u16;3]|std::array::from_fn(|i|Remaining{shell_compact_id:f.ammunition[i].shell_compact_id,count:counts[i]});
        let terminal=Self{reservation:reservation.clone(),remaining_ammunition:rows(counts),fired_ammunition:rows(fired),lost_ammunition:rows(lost),
            loss_event:event.map(|e|codec::LossEvent{shot:e.shot(),attacker_slot:e.attacker()as u8,target_slot:e.target()as u8,tick:e.tick(),device_sequence:e.device_sequence()}),
            terminal_hp:actor.health,terminal_state_json:world.terminal_state_json(slot)?,reason,native_database_id:actor.identity.database,
            results_json:result.map(serde_json::to_string).transpose().map_err(|_|bad("loss result serialization"))?};terminal.validate()?;Ok(terminal)
    }
    pub(crate) fn cancelled(reservation:&Reservation,native_database_id:i32)->io::Result<Self>{
        let f=&reservation.frozen.base;let empty=f.ammunition.each_ref().map(|a|Remaining{shell_compact_id:a.shell_compact_id,count:0});
        let terminal=Self{reservation:reservation.clone(),remaining_ammunition:f.ammunition.each_ref().map(|a|Remaining{shell_compact_id:a.shell_compact_id,count:a.count}),
            fired_ammunition:empty,lost_ammunition:empty,loss_event:None,terminal_hp:f.max_hp,terminal_state_json:World::cancelled_terminal_state(f)?,
            reason:FinishReason::Cancelled,results_json:None,native_database_id};terminal.validate()?;Ok(terminal)
    }
    pub(crate) fn request(&self)->Request{Request::Finish{battle:self.reservation.battle,native_inventory_id:self.reservation.frozen.base.native_inventory_id,
        reservation_id:self.reservation.reservation_id.clone(),remaining_ammunition:self.remaining_ammunition,fired_ammunition:self.fired_ammunition,
        lost_ammunition:self.lost_ammunition,loss_event:self.loss_event,terminal_hp:self.terminal_hp,terminal_state_json:self.terminal_state_json.clone(),
        reason:self.reason,results_json:self.results_json.clone()}}
}
pub(crate) struct CompletionLoss{
    pub(crate) session:u32,pub(crate) old_owner:Arc<identity091::Profile>,pub(crate) context:Context,
    pub(crate) request:Request,pub(crate) reply:Reply,pub(crate) fresh:Option<Fresh>,pub(crate) refresh_error:Option<io::Error>,
}
fn work(session:u32,owner:Arc<identity091::Profile>,config:Arc<identity091::Config>,context:Context,request:Request)->io::Result<CompletionLoss>{
    let reply=config.service_battle_loss(&owner,&context,&request)?;
    let(fresh,refresh_error)=if matches!(reply.status,Status::Ready|Status::Admitted|Status::Finished){
        match load_fresh(&config,&owner,reply.revision){Ok(f)=>(Some(f),None),Err(e)=>(None,Some(e))}
    }else{(None,None)};
    Ok(CompletionLoss{session,old_owner:owner,context,request,reply,fresh,refresh_error})
}
pub(crate) struct JobLoss{
    pub(crate) session:u32,pub(crate) owner:Arc<identity091::Profile>,pub(crate) context:Context,pub(crate) request:Request,
    receiver:Option<mpsc::Receiver<io::Result<CompletionLoss>>>,worker:Option<JoinHandle<()>>,
}
impl JobLoss{
    pub(crate) fn start(session:u32,owner:Arc<identity091::Profile>,config:Arc<identity091::Config>,context:Context,request:Request)->io::Result<Self>{
        codec::encode_request(&context,&request)?;
        if session==0||context.account_id!=owner.account_id||context.native_database_id!=owner.database_id||!config.p06t_ammo_rack_detonation||!config.p06t_mixed_ammo
            ||!config.profile13_battle||context.run_id!=config.battle_run_id{return Err(bad("loss-v1 job authenticated owner/run/opt-in"));}
        if WORKER_ACTIVE.compare_exchange(false,true,Ordering::AcqRel,Ordering::Acquire).is_err(){return Err(bad("another battle writer call is still active"));}
        let(sender,receiver)=mpsc::sync_channel(1);let(task_owner,task_context,task_request)=(owner.clone(),context.clone(),request.clone());let operation=request.operation();
        let started=thread::Builder::new().name("p06t-loss-writer".into()).spawn(move||{
            struct Active;impl Drop for Active{fn drop(&mut self){WORKER_ACTIVE.store(false,Ordering::Release);}}let _active=Active;
            let result=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||work(session,task_owner,config,task_context,task_request)))
                .unwrap_or_else(|_|Err(bad("loss-v1 writer thread panicked; recover immutable operation")));
            match &result{
                Ok(c)=>println!("P06T_LOSS_WRITER_JOB_RESULT session={session} operation={operation} status={:?} revision={} refreshed={} refresh_failed={} native_delivery=not_yet_dispatched",c.reply.status,c.reply.revision,c.fresh.is_some(),c.refresh_error.is_some()),
                Err(e)=>println!("P06T_LOSS_WRITER_JOB_ERROR session={session} operation={operation} error={e} outcome_requires_recovery=true"),
            }
            if sender.send(result).is_err(){println!("P06T_LOSS_JOB_OBSERVER_RETIRED session={session} operation={operation} durable_ledger_retained=true");}
        });
        let worker=match started{Ok(w)=>w,Err(e)=>{WORKER_ACTIVE.store(false,Ordering::Release);return Err(e);}};
        Ok(Self{session,owner,context,request,receiver:Some(receiver),worker:Some(worker)})
    }
    fn join_finished(&mut self)->io::Result<()>{
        if self.worker.as_ref().is_some_and(|w|w.is_finished())&&self.worker.take().ok_or_else(||bad("loss-v1 writer handle"))?.join().is_err(){return Err(bad("loss-v1 writer join panicked"));}Ok(())
    }
    pub(crate) fn poll(&mut self)->Option<io::Result<CompletionLoss>>{
        if self.worker.as_ref().is_some_and(|w|!w.is_finished()){return None;}
        let result=match self.receiver.as_ref()?.try_recv(){Ok(r)=>r,Err(mpsc::TryRecvError::Empty)=>return None,
            Err(mpsc::TryRecvError::Disconnected)=>Err(bad("loss-v1 writer channel ended; recover immutable operation"))};
        self.receiver=None;if let Err(e)=self.join_finished(){return Some(Err(e));}Some(result)
    }
}
impl Drop for JobLoss{fn drop(&mut self){drop(self.receiver.take());if let Err(e)=self.join_finished(){println!("P06T_LOSS_JOB_DROP_ERROR session={} error={e}",self.session);}}}

#[cfg(test)]
mod tests{
    use super::*;
    fn reservation()->Reservation{
        let data:serde_json::Value=serde_json::from_slice(include_bytes!("../../../../tests/fixtures/p06t-ammo-loss-writer-vectors.json")).unwrap();
        let row=data["vectors"].as_array().unwrap().iter().find(|r|r["request"]["operation"]=="admit").unwrap();let r=&row["request"];
        let c=Context{account_id:r["account_id"].as_str().unwrap().into(),native_database_id:r["native_database_id"].as_i64().unwrap()as i32,
            command_key:r["command_key"].as_str().unwrap().into(),expected_revision:r["expected_revision"].as_u64().unwrap(),run_id:r["run_id"].as_str().unwrap().into()};
        codec::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&c,&Request::Admit{battle:r["battle_id"].as_str().unwrap().rsplit(':').next().unwrap().parse().unwrap(),
            native_inventory_id:r["native_inventory_id"].as_u64().unwrap()as u32}).unwrap().reservation.unwrap()
    }
    #[test]fn p06t_loss_session_queue_cancel_and_first_terminal_fence_all_modes(){
        let r=reservation();let terminal=TerminalLoss::cancelled(&r,1).unwrap();
        assert_eq!(terminal.fired_ammunition.map(|a|a.count),[0;3]);assert_eq!(terminal.lost_ammunition.map(|a|a.count),[0;3]);
        let mut state=super::super::State::new(r.run_id.clone(),13).unwrap();assert!(state.garage_idle());state.reservation_loss=Some(r.clone());
        assert_eq!(state.reservation_battle(),Some(r.battle));assert_eq!(state.reservation_kind(),Some(r.frozen.base.kind));assert!(!state.garage_idle());
        assert!(state.retain_terminal_loss(terminal.clone()).unwrap());assert!(state.has_pending_return());
        assert!(!state.retain_terminal_loss(terminal.clone()).unwrap());
        let before=state.clone();let mut poison=terminal;poison.remaining_ammunition[2].count-=1;
        assert!(state.retain_terminal_loss(poison).is_err());assert_eq!(state,before);
    }
    #[test]fn p06t_loss_actor_terminal_keeps_real_fired_ledger_and_survives_detach(){
        let r=reservation();let now=std::time::Instant::now();let mut world=World::new_for_roster(r.battle,now,crate::map_profile091::MapId::Karelia,2).unwrap();
        world.enable_mixed_ammo().unwrap();
        world.bind_geometry(Arc::new(super::super::super::geometry::tests::bundle())).unwrap();
        world.bind_geometry(Arc::new(super::super::super::geometry::tests::is7_bundle())).unwrap();world.enable_ap_test_lab().unwrap();
        world.bind_terrain(Arc::new(super::super::super::terrain::tests::fixture(-1000.,2000.,2,vec![-100.;4]))).unwrap();
        world.enable_lifecycle(super::super::super::lifecycle::Rules::prohorovka()).unwrap();world.enable_ammo_detonation().unwrap();
        let slot=world.attach_owned_loss(super::super::super::model::Identity{account:r.frozen.base.vehicle_inventory_id[..36].into(),database:1,name:"loss writer".into()},7,&r.frozen).unwrap();
        world.actors[slot].fire.apply_typed(&[crate::p06t_armament091::Command::Shoot],now).unwrap();
        let t=TerminalLoss::from_actor_result(&r,&world,slot,7,FinishReason::ManualLeave,None).unwrap();
        assert_eq!(t.fired_ammunition.map(|a|a.count),[0,1,0]);assert_eq!(t.lost_ammunition.map(|a|a.count),[0;3]);assert!(t.loss_event.is_none());
        let mut state=super::super::State::new(r.run_id.clone(),13).unwrap();state.reservation_loss=Some(r.clone());state.retain_terminal_loss(t.clone()).unwrap();
        world.detach(7).unwrap();assert!(TerminalLoss::from_actor_result(&r,&world,slot,7,FinishReason::Disconnect,None).is_err());
        assert_eq!(state.pending_return_loss,Some(t));
    }
}
