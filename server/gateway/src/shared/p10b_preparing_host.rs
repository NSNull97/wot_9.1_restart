//! Serial room preparation driver, intended child of shared::server.
//! No job starts in the cloned receive transaction. No ordinary deliver_v2,
//! native queue callback, actor attach or pristine Cancel after launch commit.
use super::*;
use std::collections::{BTreeMap,BTreeSet};
use crate::battle091::profile13::Context;
use crate::training091::{controller::{Controller,PrepareTask,Batch},domain as room};
use crate::gateway091::shared::{p10b_writer as saga,profile13_session as persistence};
use crate::profile13_v2091 as writer;
use super::p10b_launch_host::{HeldFresh,LaunchOrigin};

const RETRY:Duration=Duration::from_secs(2);
fn bad(message:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,message)}

/// Fresh is not Clone: retain its immutable Arc data manually after the actual
/// JobV2 output and Saga acceptance. No constructor accepts caller strings.
#[derive(Clone)]
struct CurrentFresh{
    session:u32,owner:Arc<crate::identity091::Profile>,
    fixtures:Arc<crate::hangar091::Fixtures>,binding:crate::ammo_service091::Metadata,
}
impl CurrentFresh{
    fn capture(task:&saga::Task,c:&persistence::CompletionV2)->io::Result<Self>{
        let f=c.fresh.as_ref().ok_or_else(||bad("preparing current projection missing"))?;
        if c.session!=task.session()||c.context!=*task.context()||c.request!=*task.request()
            ||c.old_owner.account_id!=task.owner().account_id||c.old_owner.database_id!=task.owner().database_id
            ||c.refresh_error.is_some()||f.owner.account_id!=task.owner().account_id||f.owner.database_id!=task.owner().database_id
            ||f.owner.name!=task.owner().name||f.binding.revision!=c.reply.revision||f.binding.wire_revision!=1
            ||f.fixtures.p04m_binding().is_none_or(|p|!p.matches(&f.owner.account_id,f.owner.database_id,f.binding.revision)){
            return Err(bad("preparing current projection identity/revision/source"));
        }
        Ok(Self{session:task.session(),owner:f.owner.clone(),fixtures:f.fixtures.clone(),binding:f.binding})
    }
}

/// Clone-only host state: guards and queued tasks are committed with Sessions.
/// The actual worker handle lives only in Driver, outside every frame clone.
#[derive(Clone)]
pub(super) struct Preparing{
    prepare:PrepareTask,saga:saga::Saga,origins:BTreeMap<room::Account,LaunchOrigin>,
    held:Vec<HeldFresh>,current:BTreeMap<u32,CurrentFresh>,
}
impl Preparing{
    /// Caller first ensures there is no other Preparing. This stages ALL selected
    /// guards before any worker; no external action occurs in this method.
    pub(super) fn begin(prepare:PrepareTask,battle:room::BattleKey,
        origins:BTreeMap<room::Account,LaunchOrigin>,controller:&Controller,table:&mut Table)->io::Result<Self>{
        let snapshot=prepare.snapshot();let n=snapshot.members().len();
        if !(2..=6).contains(&n)||origins.len()!=n||table.capacity<n||battle.0==0{
            return Err(bad("preparing roster/owner bound"));
        }
        let actual=controller.registry().room(snapshot.room()).ok_or_else(||bad("preparing room missing"))?;
        if actual.abort_requested()||actual.preparing()!=Some(snapshot){return Err(bad("preparing stale Prepare"));}
        let mut sessions=table.sessions.clone();let mut selected=Vec::new();let mut ids=BTreeSet::new();let mut run=None;
        for member in snapshot.members(){
            let origin=origins.get(&member.account()).ok_or_else(||bad("preparing missing Ready origin"))?;
            let selection=origin.selection();let ready=origin.ready_task();
            if selection.reference()!=member.ready()||ready.room()!=snapshot.room()
                ||controller.registry().member_context(snapshot.room(),member.account())!=Some((ready.caller(),ready.membership()))
                ||!ids.insert(selection.session()){
                return Err(bad("preparing changed ready/member/session"));
            }
            let s=unique_session(&mut sessions,selection.session())?;
            origin.matches_session(s,controller,false)?;
            let p=owned_state(s)?;
            if !p.can_admit_command()||p.selection.is_some()||p.run_id!=selection.run_id()||!s.battle_results.idle(){
                return Err(bad("preparing command budget/run/queued operation"));
            }
            if run.as_ref().is_some_and(|old:&String|old!=&p.run_id){return Err(bad("preparing different writer runs"));}
            run=Some(p.run_id.clone());selected.push(selection.clone());
        }
        let saga=saga::Saga::new(snapshot.clone(),battle,selected)?;
        for id in ids{owned_state_mut(unique_session(&mut sessions,id)?)?.in_flight=true;}
        table.sessions=sessions;
        Ok(Self{prepare,saga,origins,held:Vec::new(),current:BTreeMap::new()})
    }
    pub(super) fn saga(&self)->&saga::Saga{&self.saga}
    pub(super) fn origins(&self)->&BTreeMap<room::Account,LaunchOrigin>{&self.origins}
    pub(super) fn held(&self)->&[HeldFresh]{&self.held}
    pub(super) fn prepare(&self)->&PrepareTask{&self.prepare}
    pub(super) fn owns(&self,session:u32)->bool{self.origins.values().any(|o|o.selection().session()==session)}
    pub(super) fn abort(&mut self){self.saga.abort();}
    /// Root retains this inactive Session in Table until durable compensation;
    /// do NOT call ordinary Dispatcher.retire with its preparing guard present.
    pub(super) fn abort_on_disconnect(&mut self,session:u32)->bool{
        if !self.owns(session){return false;}self.abort();true
    }
    fn key(&self)->(room::RoomKey,u64,room::BattleKey){(self.prepare.snapshot().room(),self.prepare.snapshot().ticket(),self.saga.battle())}
    fn ready_to_launch(&self)->bool{self.saga.reserved_refs().is_ok()&&self.held.len()==self.origins.len()}
    fn ready_to_abort(&self)->bool{
        self.saga.released_refs().is_ok()&&self.current.len()==self.origins.len()
    }
    /// All retained receipt, cache and stage updates either succeed together or
    /// retain the immutable pending task. Called only with real JobV2 output.
    fn accept(&mut self,c:&persistence::CompletionV2)->io::Result<()> {
        let task=self.saga.retry().ok_or_else(||bad("preparing completion without issued Task"))?;
        let mut next=self.clone();
        let admitted=if c.reply.status==writer::Status::Admitted{Some(HeldFresh::capture(&task,c)?)}else{None};
        let current=if c.reply.status==writer::Status::Rejected{None}else{Some(CurrentFresh::capture(&task,c)?)};
        next.saga.complete(c)?;
        if let Some(f)=admitted{
            if next.held.iter().any(|old|old.session()==f.session())||next.held.len()>=6{return Err(bad("preparing duplicate held admission"));}
            next.held.push(f);
        }
        if let Some(f)=current{next.current.insert(f.session,f);}
        *self=next;Ok(())
    }
    /// No pending admit may be replaced by Inspect. Existing pending Task is
    /// always returned verbatim; allocation consumes an actual State counter
    /// once, even if thread start fails, but never clears actual in_flight.
    fn next_task(&mut self,table:&mut Table,all_other_jobs_drained:bool)->io::Result<Option<saga::Task>>{
        if !all_other_jobs_drained{return Ok(None);}
        if let Some(task)=self.saga.retry(){return Ok(Some(task));}
        let origin=if self.saga.aborting(){
            self.saga.next_compensation_origin().or_else(||self.saga.next_inspection_origin())
        }else{self.saga.next_admission_origin()};
        let Some((session,owner,revision))=origin else{return Ok(None);};
        let mut next=self.clone();let mut sessions=table.sessions.clone();
        let selected=next.origins.values().find(|o|o.selection().session()==session).ok_or_else(||bad("preparing allocation origin"))?;
        let s=unique_session(&mut sessions,session)?;validate_guard(s,selected)?;
        if !next.saga.aborting()&&!s.active{return Err(bad("preparing inactive admission requires abort"));}
        let p=owned_state_mut(s)?;let mut allocation=p.clone();allocation.in_flight=false;allocation.revision=revision;
        let context=allocation.next_context(&owner,session)?;
        let task=if !next.saga.aborting(){next.saga.next_admit(context)?}
            else if next.saga.next_compensation_origin().is_some(){next.saga.next_cancel(context)?}
            else{next.saga.next_inspect(context)?};
        if task.is_none(){return Err(bad("preparing origin disappeared"));}
        p.command_counter=allocation.command_counter;
        table.sessions=sessions;*self=next;Ok(task)
    }

    /// Pure aborted-state staging. The caller inserts returned Batch bodies and
    /// drains/bounds all affected Sessions BEFORE committing this object and
    /// removing Preparing in the SAME host transaction. No unlock is live yet.
    pub(super) fn stage_abort(&self,driver:&Driver,table:&Table,controller:&Controller,logical_ms:u64)->io::Result<AbortStage>{
        if !driver.idle()||!self.ready_to_abort(){return Err(bad("preparing abort before complete writer/cache drain"));}
        let mut sessions=table.sessions.clone();let mut next_controller=controller.clone();
        let batch=next_controller.abort_launch(self.prepare.snapshot().room(),self.prepare.snapshot().ticket(),self.saga.released_refs()?,logical_ms)
            .map_err(|_|bad("preparing Controller abort refused"))?;
        if !batch.ready.is_empty()||!batch.prepare.is_empty(){return Err(bad("preparing abort spawned new tasks"));}
        for origin in self.origins.values(){
            let id=origin.selection().session();let s=unique_session(&mut sessions,id)?;validate_guard(s,origin)?;
            let fresh=self.current.get(&id).ok_or_else(||bad("preparing abort current Fresh missing"))?;
            if fresh.owner.account_id!=origin.selection().owner().account_id||fresh.owner.database_id!=origin.selection().owner().database_id{
                return Err(bad("preparing abort Fresh owner mismatch"));
            }
            // Same Account entity: preserve native wire cursor/seen IDs.
            let ammo=s.ammo_service.as_mut().ok_or_else(||bad("preparing abort ammo state missing"))?;
            ammo.refresh_revision(fresh.binding.revision)?;ammo.replace_pool(fresh.fixtures.p04m_binding().cloned())?;
            s.identity=Some(fresh.owner.clone());s.hangar=Some(fresh.fixtures.clone());
            let p=owned_state_mut(s)?;p.revision=fresh.binding.revision;p.in_flight=false;p.selection=None;
            let c=s.shared.as_mut().ok_or_else(||bad("preparing abort Client missing"))?;c.join_requested=false;c.queue_announced=false;
        }
        Ok(AbortStage{sessions,controller:next_controller,batch})
    }
}

/// No commit method intentionally: Root's actual publication transaction must
/// first stage all Batch bodies/aliases and validate every reliable drain. This
/// typed object can be consumed only by trusted same-server host code.
pub(super) struct AbortStage{
    pub(super) sessions:Vec<Session>,pub(super) controller:Controller,pub(super) batch:Batch,
}
fn unique_session(sessions:&mut[Session],id:u32)->io::Result<&mut Session>{
    let mut candidates=sessions.iter_mut().filter(|s|s.id==id);
    let s=candidates.next().ok_or_else(||bad("preparing retained Session missing"))?;
    if candidates.next().is_some(){return Err(bad("preparing duplicate Session"));}Ok(s)
}
fn owned_state(s:&Session)->io::Result<&super::super::profile13_session::State>{
    s.shared.as_ref().and_then(|c|c.profile13.as_ref()).ok_or_else(||bad("preparing owned state missing"))
}
fn owned_state_mut(s:&mut Session)->io::Result<&mut super::super::profile13_session::State>{
    s.shared.as_mut().and_then(|c|c.profile13.as_mut()).ok_or_else(||bad("preparing owned state missing"))
}
fn validate_guard(s:&Session,origin:&LaunchOrigin)->io::Result<()> {
    let p=owned_state(s)?;let owner=s.identity.as_ref().ok_or_else(||bad("preparing retained identity missing"))?;
    if s.id!=origin.selection().session()||s.training_account_generation()!=origin.ready_task().channel().generation
        ||owner.account_id!=origin.selection().owner().account_id||owner.database_id!=origin.selection().owner().database_id
        ||p.run_id!=origin.selection().run_id()||!p.in_flight||p.has_reservation()||p.has_pending_return()||p.selection.is_some()
        ||s.arena_base||s.shared.as_ref().is_none_or(|c|c.phase!=Phase::Account||c.join_requested||c.queue_announced)
        ||s.ammo_service.as_ref().is_none_or(|a|!a.idle())||!s.battle_results.idle(){
        return Err(bad("preparing retained authority/guard changed"));
    }Ok(())
}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub(super) enum Progress{Waiting,Started,Accepted,RetryRetained,AllReserved,AllReleased}
pub(super) struct Report{pub(super) progress:Progress,pub(super) error:Option<io::Error>}
/// Non-Clone actual worker owner. Root polls ONLY outside native frame clones.
#[derive(Default)]
pub(super) struct Driver{
    key:Option<(room::RoomKey,u64,room::BattleKey)>,job:Option<persistence::JobV2>,
    known:Option<persistence::CompletionV2>,retry_at:Option<Instant>,unresolved:bool,
}
impl Driver{
    pub(super) fn idle(&self)->bool{self.job.is_none()&&self.known.is_none()&&!self.unresolved}
    pub(super) fn job_active(&self)->bool{self.job.is_some()}
    pub(super) fn known_status(&self)->Option<writer::Status>{self.known.as_ref().map(|c|c.reply.status)}
    fn report(progress:Progress,error:Option<io::Error>)->Report{Report{progress,error}}
    fn retained(&mut self,now:Instant,error:io::Error)->Report{
        self.retry_at=Some(now+RETRY);Self::report(Progress::RetryRetained,Some(error))
    }
    fn completed(&mut self,p:&mut Preparing,outcome:io::Result<persistence::CompletionV2>,now:Instant)->Report{
        match outcome{
            Err(error)=>self.retained(now,error),
            Ok(c)=>{
                // A known committed mutation cannot become another receipt
                // when its exact command is replayed after projection error.
                if let Some(old)=self.known.as_ref().filter(|old|matches!(old.reply.status,writer::Status::Admitted|writer::Status::Finished)){
                    if old.context!=c.context||old.request!=c.request||old.reply.status!=c.reply.status||old.reply.revision!=c.reply.revision
                        ||old.reply.reservation!=c.reply.reservation||old.reply.legacy_reservation!=c.reply.legacy_reservation{
                        return self.retained(now,bad("preparing immutable durable reply changed on replay"));
                    }
                }
                match p.accept(&c){
                    Ok(())=>{self.known=None;self.retry_at=None;self.unresolved=false;Self::report(Progress::Accepted,None)},
                    Err(error)=>{self.known=Some(c);self.retained(now,error)},
                }
            },
        }
    }
    pub(super) fn poll(&mut self,p:&mut Preparing,table:&mut Table,config:Arc<crate::identity091::Config>,
        now:Instant,all_other_jobs_drained:bool)->Report{
        if self.key.is_some_and(|key|key!=p.key())&&!self.idle(){return self.retained(now,bad("preparing Driver belongs to unresolved old launch"));}
        self.key=Some(p.key());
        if let Some(job)=&mut self.job{
            let Some(outcome)=job.poll()else{return Self::report(Progress::Waiting,None);};self.job=None;
            return self.completed(p,outcome,now);
        }
        if p.ready_to_launch(){return Self::report(Progress::AllReserved,None);}
        if p.ready_to_abort(){return Self::report(Progress::AllReleased,None);}
        if self.retry_at.is_some_and(|at|now<at)||!all_other_jobs_drained{return Self::report(Progress::Waiting,None);}
        let task=match p.next_task(table,all_other_jobs_drained){
            Ok(Some(task))=>task,Ok(None)=>return Self::report(Progress::Waiting,None),Err(error)=>return self.retained(now,error),
        };
        self.unresolved=true;
        // This is the only external writer start. JobV2 enforces the same
        // process-global singleton as the old dispatcher and checks Config.
        match task.start(config){
            Ok(job)=>{self.job=Some(job);Self::report(Progress::Started,None)},
            Err(error)=>self.retained(now,error),
        }
    }
}

#[cfg(test)]#[path="p10b_preparing_host_tests.rs"]pub(in crate::gateway091::shared::server) mod tests;
