//! Candidate loop owner: bounded captures and ONE immutable retrying writer job.
//! No late result can Finish, rebind a garage, mutate ammunition or clear a
//! reservation. Worker errors remain this feature's diagnostics, never a World
//! failure. The source store remains the authority for append eligibility.
use std::{collections::{BTreeSet,VecDeque},io,sync::{Arc,mpsc},thread::{self,JoinHandle},time::{Duration,Instant}};
use crate::identity091;
use super::{super::Session,model::World,profile13_session as handoff,
    late_results_capture::{Capture,Admission},late_results_protocol::{Task,Reply,ReleaseStamp},late_results_pending::Discovery};
const MAX_CAPTURES:usize=8;
const RETRY:Duration=Duration::from_secs(2);
fn bad(why:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("late results runtime: {why}"))}
#[derive(Clone,Default)]
enum OwnerState{#[default] Waiting,Stamped(ReleaseStamp),Appended,Rejected(String)}
#[derive(Clone)]
struct Entry{capture:Capture,owners:[OwnerState;super::model::MAX_ACTORS],invalid:Option<String>}
impl Entry{
    fn new(capture:Capture)->Self{Self{capture,owners:std::array::from_fn(|_|OwnerState::Waiting),invalid:None}}
    fn settled(&self)->bool{self.invalid.is_some()||self.capture.seal().is_some()&&self.capture.links().iter().all(|l|
        self.capture.release_reason(l.slot()).ok().flatten().is_none()||matches!(self.owners[l.slot()],OwnerState::Appended|OwnerState::Rejected(_)))}
}
/// Checked small observer update. It is prepared alongside the actual Session
/// transaction, committed only after delivery/launch succeeds in this loop.
pub(super) struct Install{battle:u64,entry:Entry,index:Option<usize>}
#[derive(Clone)]
struct Work{battle:u64,slot:usize,task:Task}
struct Job{rx:mpsc::Receiver<io::Result<Reply>>,handle:JoinHandle<()>}
impl Job{
    fn start(work:&Work,config:Arc<identity091::Config>)->io::Result<Self>{
        let task=work.task.clone();let(tx,rx)=mpsc::channel();
        let handle=thread::Builder::new().name("p08c-late-result".into()).spawn(move||{
            let out=config.late_results_post(task.owner(),task.body()).and_then(|raw|task.parse_reply(&raw));let _=tx.send(out);
        })?;Ok(Self{rx,handle})
    }
    fn poll(&mut self)->Option<io::Result<Reply>>{if !self.handle.is_finished(){return None;}match self.rx.try_recv(){Ok(v)=>Some(v),Err(mpsc::TryRecvError::Empty)=>None,
        Err(mpsc::TryRecvError::Disconnected)=>Some(Err(bad("worker closed without bounded reply; same task retained")))}}
}
/// Feature-local bounded memory; authoritative reservations continue through
/// the existing Dispatcher even when this optional feature is unsupported.
pub(super) struct Manager{
    captures:Vec<Entry>,accounts:BTreeSet<String>,work:Option<Work>,job:Option<Job>,retry:Option<Instant>,
    experimental_notice:bool,discovery:Discovery,
    registration_refused:VecDeque<u64>,
}
impl Manager{
    pub(super) fn new(accounts:Vec<String>,experimental_notice:bool)->io::Result<Self>{
        if accounts.is_empty()||accounts.len()>6||accounts.iter().collect::<BTreeSet<_>>().len()!=accounts.len(){return Err(bad("explicit1..6 unique configured owners required"));}
        Ok(Self{captures:Vec::new(),accounts:accounts.into_iter().collect(),work:None,job:None,retry:None,experimental_notice,discovery:Discovery::default(),registration_refused:VecDeque::new()})
    }
    /// Only a RUNNING job blocks another SQLite/HTTP worker. An immutable task
    /// waiting2s never starves the actual Finish dispatcher or garage writes.
    pub(super) fn worker_running(&self)->bool{self.job.is_some()||self.discovery.worker_running()}
    pub(super) fn invalidate_source(&mut self,run:&str,battle:u64){
        if let Some(e)=self.captures.iter_mut().find(|e|e.capture.run()==run&&e.capture.battle()==battle){
            e.invalid=Some("source_observer_failure".into());
            println!("P08C_LATE_CAPTURE_UNSUPPORTED battle={battle} reason=source_observer_failure healthy_finish_unchanged=true");
        }
    }
    pub(super) fn before_reset(&mut self,world:&World,reason:&'static str){
        self.seal_world(world);
        if let Some(e)=self.captures.iter_mut().find(|e|e.capture.battle()==world.id){
            if e.capture.seal().is_none()&&e.invalid.is_none(){e.invalid=Some(reason.into());
                println!("P08C_LATE_CAPTURE_UNSUPPORTED battle={} reason={reason} reset_without_final_seal=true",world.id);}
        }
    }
    pub(super) fn stage_install(&self,capture:Capture)->io::Result<Install>{
        if let Some(index)=self.captures.iter().position(|e|e.capture.battle()==capture.battle()){
            let old=&self.captures[index];
            if old.capture.run()!=capture.run()||old.capture.seal().is_some(){return Err(bad("install conflicts with retained battle"));}
            // Existing admission registration extends the old checked capture,
            // never replaces releases/stamps with a new pristine observer.
            return Err(bad("existing battle requires register_world transaction"));
        }
        let index=if self.captures.len()<MAX_CAPTURES{None}else{Some(self.captures.iter().position(|e|e.settled()
            &&!self.work.as_ref().is_some_and(|w|w.battle==e.capture.battle())).ok_or_else(||bad("bounded retained captures full; feature unsupported for new battle"))?)};
        Ok(Install{battle:capture.battle(),entry:Entry::new(capture),index})
    }
    pub(super) fn commit_install(&mut self,install:Install){
        debug_assert_eq!(install.battle,install.entry.capture.battle());
        if let Some(index)=install.index{self.captures[index]=install.entry;}else{self.captures.push(install.entry);}
    }
    /// Call immediately after ACTUAL attachment, before any World start. Source
    /// validation failure disables only this optional capture, with named log.
    pub(super) fn register_world(&mut self,sessions:&[Session],world:&World,run:&str)->io::Result<()>{
        if world.actors.is_empty()||self.registration_refused.contains(&world.id){return Ok(());}
        let result=self.register_world_inner(sessions,world,run);
        if result.is_err(){if self.registration_refused.len()>=MAX_CAPTURES{self.registration_refused.pop_front();}self.registration_refused.push_back(world.id);}
        result
    }
    fn register_world_inner(&mut self,sessions:&[Session],world:&World,run:&str)->io::Result<()>{
        if !world.mixed_ammo(){return Err(bad("legacy AP unsupported; no invented source links"));}
        let old=self.captures.iter().position(|e|e.capture.battle()==world.id);
        if old.is_some_and(|i|self.captures[i].invalid.is_some()){return Ok(());}
        let mut capture=if let Some(i)=old{self.captures[i].capture.clone()}else{Capture::new(run.into(),world.id)?};
        for(slot,a)in world.actors.iter().enumerate(){
            // Existing parked links remain source-bound without live Session.
            if capture.links().iter().any(|l|l.slot()==slot){continue;}
            let sid=a.session.ok_or_else(||bad("unregistered parked actor"))?;
            let s=sessions.iter().find(|s|s.id==sid).ok_or_else(||bad("missing actual attached Session"))?;
            let p=s.shared.as_ref().and_then(|c|c.profile13.as_ref()).ok_or_else(||bad("attached actor lacks owned writer"))?;
            let admission=if world.ammo_detonation_enabled(){Admission::Loss(p.reservation_loss.clone().ok_or_else(||bad("missing actual loss admission"))?)}
                else{Admission::Mixed(p.reservation_v2.clone().ok_or_else(||bad("missing actual mixed admission"))?)};
            capture.register(world,slot,sid,s.identity.clone().ok_or_else(||bad("missing actual owner"))?,admission)?;
        }
        if let Some(i)=old{self.captures[i].capture=capture;}else{let install=self.stage_install(capture)?;self.commit_install(install);}Ok(())
    }
    /// Scan original first-cause receipts BEFORE Dispatcher can consume them.
    /// Includes its retained disconnected Sessions; does not synthesize Finish.
    pub(super) fn observe_sessions<'a>(&mut self,sessions:impl Iterator<Item=&'a Session>){
        for s in sessions{let Some(p)=s.shared.as_ref().and_then(|c|c.profile13.as_ref())else{continue;};
            let battle=p.pending_return_loss.as_ref().map(|t|t.reservation.battle).or_else(||p.pending_return_v2.as_ref().map(|t|t.reservation.battle));
            let Some(e)=battle.and_then(|battle|self.captures.iter_mut().find(|e|e.capture.battle()==battle))else{continue;};
            if e.invalid.is_some(){continue;}
            let Some(slot)=e.capture.links().iter().find(|l|l.session()==s.id).map(|l|l.slot())else{continue;};
            let result=if let Some(t)=&p.pending_return_loss{e.capture.observe_terminal_loss(slot,t)}else if let Some(t)=&p.pending_return_v2{e.capture.observe_terminal_v2(slot,t)}else{continue;};
            if let Err(error)=result{e.invalid=Some(error.to_string());println!("P08C_LATE_CAPTURE_UNSUPPORTED battle={} session={} stage=first_terminal error={error} healthy_battle_unchanged=true",e.capture.battle(),s.id);}
        }
    }
    pub(super) fn stage_finished_v2(&self,c:&handoff::CompletionV2)->io::Result<Option<Install>>{
        let Some(battle)=c.request.finished_battle()else{return Ok(None);};
        let Some(index)=self.captures.iter().position(|e|e.capture.battle()==battle)else{return Ok(None);};let mut entry=self.captures[index].clone();
        if entry.invalid.is_some(){return Ok(None);}let Some(slot)=entry.capture.links().iter().find(|l|l.session()==c.session).map(|l|l.slot())else{return Err(bad("Finished missing actual linked Session"));};
        if entry.capture.release_reason(slot)?.is_none(){return Ok(None);}entry.capture.observe_finished_v2(slot,c)?;
        Ok(Some(Install{battle,entry,index:Some(index)}))
    }
    pub(super) fn stage_finished_loss(&self,c:&handoff::CompletionLoss)->io::Result<Option<Install>>{
        let Some(battle)=c.request.finished_battle()else{return Ok(None);};
        let Some(index)=self.captures.iter().position(|e|e.capture.battle()==battle)else{return Ok(None);};let mut entry=self.captures[index].clone();
        if entry.invalid.is_some(){return Ok(None);}let Some(slot)=entry.capture.links().iter().find(|l|l.session()==c.session).map(|l|l.slot())else{return Err(bad("Finished missing actual linked Session"));};
        if entry.capture.release_reason(slot)?.is_none(){return Ok(None);}entry.capture.observe_finished_loss(slot,c)?;
        Ok(Some(Install{battle,entry,index:Some(index)}))
    }
    /// Final seal MUST precede every normal World reset. Faults without actual
    /// Outcome remain unsupported and cannot turn into fabricated win/draw.
    pub(super) fn seal_world(&mut self,world:&World){
        let Some(e)=self.captures.iter_mut().find(|e|e.capture.battle()==world.id)else{return;};
        if e.invalid.is_some()||e.capture.seal().is_some()||!world.lifecycle.as_ref().is_some_and(|l|l.outcome().is_some()){return;}
        match e.capture.capture_final(world){Ok(true)=>println!("P08C_LATE_SEAL_FROZEN battle={} source=actual_outcome before_world_reset=true",world.id),Ok(false)=>{},
            Err(error)=>{e.invalid=Some(error.to_string());println!("P08C_LATE_CAPTURE_UNSUPPORTED battle={} stage=final_seal error={error} healthy_battle_unchanged=true",world.id);}}
    }
    pub(super) fn sealed_results(&self,battle:u64)->Option<Arc<super::lifecycle_wire::Results>>{
        self.captures.iter().find(|e|e.capture.battle()==battle&&e.invalid.is_none()).and_then(|e|e.capture.seal()).map(|s|s.results().clone())
    }
    fn select_work(&mut self)->io::Result<Option<Work>>{
        for e in &mut self.captures{if e.invalid.is_some()||e.capture.seal().is_none(){continue;}
            for link in e.capture.links(){let slot=link.slot();if !matches!(e.owners[slot],OwnerState::Waiting|OwnerState::Stamped(_)){continue;}
                if !self.accounts.contains(&link.owner().account_id){e.owners[slot]=OwnerState::Rejected("LATE_RESULTS_DISABLED".into());
                    println!("P08C_LATE_OWNER_REJECTED battle={} slot={slot} code=LATE_RESULTS_DISABLED no_http=true",e.capture.battle());continue;}
                match e.capture.eligible(slot){Ok(None)=>continue,Err(error)=>{e.owners[slot]=OwnerState::Rejected("LATE_ACTOR_STATE_CHANGED".into());println!("P08C_LATE_OWNER_REJECTED battle={} slot={slot} code=LATE_ACTOR_STATE_CHANGED error={error} no_append=true",e.capture.battle());continue;},Ok(Some(_))=>{}}
                let task=match &e.owners[slot]{OwnerState::Waiting=>Task::release_stamp(&e.capture,slot),OwnerState::Stamped(stamp)=>Task::append(&e.capture,slot,stamp),_=>continue};
                let task=match task{Ok(task)=>task,Err(error)=>{
                    e.owners[slot]=OwnerState::Rejected("LOCAL_TASK_UNSUPPORTED".into());
                    println!("P08C_LATE_OWNER_REJECTED battle={} slot={slot} code=LOCAL_TASK_UNSUPPORTED error={error} no_http=true",e.capture.battle());continue;
                }};
                return Ok(Some(Work{battle:e.capture.battle(),slot,task}));
            }
        }Ok(None)
    }
    fn spawn_with(&mut self,now:Instant,start:impl FnOnce(&Work)->io::Result<Job>){
        if let Some(work)=&self.work{match start(work){Ok(job)=>{self.job=Some(job);self.retry=None;},Err(error)=>{
            println!("P08C_LATE_SPAWN_RETRY battle={} slot={} error={error} same_request_retained=true",work.battle,work.slot);self.retry=Some(now+RETRY);}}}
    }
    /// Poll always, start only when every existing writer/auth lane is idle.
    /// Spawn/HTTP/parse failures retain EXACT immutable key/body and back off.
    pub(super) fn poll(&mut self,sessions:&mut[Session],config:Arc<identity091::Config>,now:Instant,external_idle:bool,sent_unix:u32){
        if let Some(outcome)=self.job.as_mut().and_then(Job::poll){
            let job=self.job.take().expect("polled job");let _=job.handle.join();
            if let Some(work)=&self.work{match outcome{
                Ok(reply)=>{let e=self.captures.iter_mut().find(|e|e.capture.battle()==work.battle).expect("immutable work retains capture");
                    e.owners[work.slot]=match reply{Reply::Stamped(stamp)=>OwnerState::Stamped(stamp),Reply::Appended{..}=>OwnerState::Appended,
                        Reply::Rejected(code)=>{println!("P08C_LATE_OWNER_REJECTED battle={} slot={} code={code} no_refinish=true",work.battle,work.slot);OwnerState::Rejected(code)}};
                    self.work=None;self.retry=None;},
                Err(error)=>{println!("P08C_LATE_WRITER_RETRY battle={} slot={} error={error} immutable_request=true",work.battle,work.slot);self.retry=Some(now+RETRY);}
            }}
        }
        // Always drain a completed readonly query, but never overlap it with
        // another writer. Notice bytes only come from COMMITTED pending rows.
        if self.experimental_notice{self.discovery.poll(sessions,&self.accounts,config.clone(),now,false,sent_unix);}
        if self.worker_running()||!external_idle||self.retry.is_some_and(|at|now<at){return;}
        if self.work.is_none(){match self.select_work(){Ok(work)=>self.work=work,Err(error)=>{println!("P08C_LATE_LOCAL_TASK_UNSUPPORTED error={error}");self.retry=Some(now+RETRY);return;}}}
        if self.work.is_some(){self.spawn_with(now,|work|Job::start(work,config.clone()));}
        else if self.experimental_notice{self.discovery.poll(sessions,&self.accounts,config,now,true,sent_unix);}
    }
}
#[cfg(test)]
#[path="late_results_runtime_tests.rs"]mod tests;
