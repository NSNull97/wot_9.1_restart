//! Child of profile13_session, sharing its actual writer-lane atomic.
//! Inspect is a readonly writer call but still uses this same lane. A reply is
//! not observable until the owned thread has finished and has been joined.
use super::{bad,load_fresh,Fresh,WORKER_ACTIVE};
use std::{io,sync::{Arc,mpsc,atomic::Ordering},thread::{self,JoinHandle}};
use crate::{identity091,profile13_hold091 as codec,profile13_hold_projection091 as projection};

pub(crate) struct FreshHold{pub(crate) fresh:Fresh,pub(crate) projection:projection::Binding}
pub(crate) struct CompletionHold{
    pub(crate) source_session:u32,pub(crate) old_owner:Arc<identity091::Profile>,pub(crate) context:codec::Context,
    pub(crate) request:codec::Request,pub(crate) reply:codec::Reply,pub(crate) fresh:Option<FreshHold>,pub(crate) refresh_error:Option<io::Error>,
}
fn work(source_session:u32,owner:Arc<identity091::Profile>,config:Arc<identity091::Config>,context:codec::Context,request:codec::Request,known:Option<codec::Reply>)->io::Result<CompletionHold>{
    let reply=if let Some(known)=known{known}else{config.service_battle_hold(&owner,&context,&request)?};
    // Real held Inspect also loads the current authoritative RESERVED profile;
    // this is the meaningful difference from old4's Inspect(None Fresh).
    let(fresh,refresh_error)=if reply.status!=codec::Status::Rejected{
        let result=load_fresh(&config,&owner,reply.revision).and_then(|fresh|{
            if fresh.owner.account_id!=owner.account_id||fresh.owner.database_id!=owner.database_id||fresh.owner.name!=owner.name{return Err(bad("hold5 Fresh changed authenticated identity"));}
            let state_sha=fresh.fixtures.state_sha256().iter().map(|b|format!("{b:02x}")).collect::<String>();
            let projection=config.hold_binding(&fresh.owner,reply.revision,&state_sha)?;
            if let Some(r)=&reply.reservation{let counts=if let Some(t)=&r.result{t.remaining.map(|s|s.count)}else{r.frozen.loss().base.counts()};
                projection.layout_for(&r.frozen,counts)?;}
            Ok(FreshHold{fresh,projection})
        });match result{Ok(f)=>(Some(f),None),Err(e)=>(None,Some(e))}
    }else{(None,None)};
    Ok(CompletionHold{source_session,old_owner:owner,context,request,reply,fresh,refresh_error})
}
pub(crate) struct JobHold{
    pub(crate) source_session:u32,pub(crate) owner:Arc<identity091::Profile>,pub(crate) context:codec::Context,pub(crate) request:codec::Request,
    receiver:Option<mpsc::Receiver<io::Result<CompletionHold>>>,worker:Option<JoinHandle<()>>,
}
impl JobHold{
    pub(crate) fn start(source_session:u32,owner:Arc<identity091::Profile>,config:Arc<identity091::Config>,context:codec::Context,request:codec::Request)->io::Result<Self>{
        Self::start_with_reply(source_session,owner,config,context,request,None)
    }
    /// A known durable response is never re-written/re-admitted to recover
    /// native projection. Retry ONLY actual readonly profile publication/Fresh
    /// under the same lane and retain the exact original SQL Reply metadata.
    pub(crate) fn refresh(known:&CompletionHold,config:Arc<identity091::Config>)->io::Result<Self>{
        if known.refresh_error.is_none()||known.fresh.is_some()||known.reply.status==codec::Status::Rejected{return Err(bad("hold5 refresh requires exact known durable reply"));}
        Self::start_with_reply(known.source_session,known.old_owner.clone(),config,known.context.clone(),known.request.clone(),Some(known.reply.clone()))
    }
    fn start_with_reply(source_session:u32,owner:Arc<identity091::Profile>,config:Arc<identity091::Config>,context:codec::Context,request:codec::Request,known:Option<codec::Reply>)->io::Result<Self>{
        codec::encode_request(&context,&request)?;
        if source_session==0||context.account_id!=owner.account_id||context.native_database_id!=owner.database_id||context.run_id!=config.battle_run_id
            ||!config.p08b_owner_battle_hold||!config.p06t_ammo_rack_detonation||!config.p06t_mixed_ammo||!config.profile13_battle{return Err(bad("hold5 job actual owner/source/mode"));}
        if WORKER_ACTIVE.compare_exchange(false,true,Ordering::AcqRel,Ordering::Acquire).is_err(){return Err(bad("another actual battle writer is active"));}
        let(sender,receiver)=mpsc::sync_channel(1);let(o,c,r)=(owner.clone(),context.clone(),request.clone());
        let spawn=thread::Builder::new().name("p08b-hold5-writer".into()).spawn(move||{
            struct Active;impl Drop for Active{fn drop(&mut self){WORKER_ACTIVE.store(false,Ordering::Release);}}let _active=Active;
            let result=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||work(source_session,o,config,c,r,known)))
                .unwrap_or_else(|_|Err(bad("hold5 worker panicked; immutable command must recover")));
            if sender.send(result).is_err(){println!("P08B_HOLD5_OBSERVER_RETIRED source_session={source_session} durable_ledger_retained=true");}
        });
        let worker=match spawn{Ok(w)=>w,Err(e)=>{WORKER_ACTIVE.store(false,Ordering::Release);return Err(e);}};
        Ok(Self{source_session,owner,context,request,receiver:Some(receiver),worker:Some(worker)})
    }
    pub(crate) fn poll(&mut self)->Option<io::Result<CompletionHold>>{
        if self.worker.as_ref().is_some_and(|w|!w.is_finished()){return None;}
        let result=match self.receiver.as_ref()?.try_recv(){Ok(v)=>v,Err(mpsc::TryRecvError::Empty)=>return None,
            Err(mpsc::TryRecvError::Disconnected)=>Err(bad("hold5 worker channel ended; recover same immutable key"))};
        self.receiver=None;if let Some(w)=self.worker.take(){if w.join().is_err(){return Some(Err(bad("hold5 worker join panicked")));}}Some(result)
    }
}
impl Drop for JobHold{fn drop(&mut self){drop(self.receiver.take());if self.worker.as_ref().is_some_and(|w|w.is_finished()){
    if let Some(w)=self.worker.take(){if w.join().is_err(){println!("P08B_HOLD5_JOIN_ERROR source_session={}",self.source_session);}}}
    // An unfinished owned worker keeps WORKER_ACTIVE until its RAII guard
    // exits. No second call can start merely because its observer was retired.
}}
