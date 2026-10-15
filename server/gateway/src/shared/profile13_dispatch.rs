//! Account writer orchestration outside the cloned native receive transaction.
use super::*;
use super::super::profile13_session::{self as service, Terminal};
use crate::battle091::profile13::{Context, Request, ReplyStatus, FinishReason};

#[derive(Clone)]
struct Task {session:u32,owner:Arc<crate::identity091::Profile>,context:Context,request:Request}
impl Task {
    fn start(&self,config:Arc<crate::identity091::Config>)->io::Result<service::Job> {
        service::Job::start(self.session,self.owner.clone(),config,self.context.clone(),self.request.clone())
    }
}

#[derive(Default)]
pub(super) struct Dispatcher {
    job:Option<service::Job>,task:Option<Task>,retry_at:Option<Instant>,
    retired:Vec<Session>,
    settled_queue:Option<u64>,
}
fn state(s:&mut Session)->io::Result<&mut service::State> {
    s.shared.as_mut().and_then(|c|c.profile13.as_mut()).ok_or_else(||model::bad())
}
impl Dispatcher {
    pub(super) fn finish_empty_queue(&mut self,table:&Table,world:&mut World,runtime:&mut Option<IntegratedRuntime>,
        template:&BattleTemplate,now:Instant)->io::Result<bool> {
        if self.settled_queue!=Some(world.id) || world.started.is_some()
            || world.actors.iter().any(|a|a.session.is_some()) {return Ok(false);}
        let outstanding=table.sessions.iter().chain(self.retired.iter()).any(|s|
            s.shared.as_ref().and_then(|c|c.profile13.as_ref()).is_some_and(|p|p.in_flight
                || p.reservation.as_ref().is_some_and(|r|r.battle==world.id)));
        if outstanding || self.task.is_some() {return Ok(false);}
        template.replace(world,runtime,now)?;self.settled_queue=None;Ok(true)
    }
    pub(super) fn closed_queue(&self,battle:u64)->bool {self.settled_queue==Some(battle)}
    pub(super) fn busy(&self)->bool {self.job.is_some() || self.task.is_some() || !self.retired.is_empty()}
    pub(super) fn owner_busy(&self,owner:&str)->bool {
        self.task.as_ref().is_some_and(|t|t.owner.account_id==owner)
            || self.retired.iter().any(|s|s.identity.as_ref().is_some_and(|p|p.account_id==owner))
    }
    /// Freeze AP/HP before revoking authority. This receipt outlives world reset.
    pub(super) fn terminal(s:&mut Session,world:&World,reason:FinishReason)->io::Result<()> {
        let Some(p)=s.shared.as_ref().and_then(|c|c.profile13.as_ref()) else {return Ok(());};
        if p.pending_return.is_some() {return Ok(());}
        let Some(reservation)=&p.reservation else {return Ok(());};
        let natural=s.shared.as_ref().and_then(|c|c.natural_result.as_deref());
        let reason=if natural.is_some() {FinishReason::BattleFinished} else {reason};
        let terminal=if world.actors.iter().any(|a|a.session==Some(s.id)) {
            Terminal::from_actor_result(reservation,world,s.shared.as_ref().ok_or_else(||model::bad())?.slot,s.id,reason,natural)?
        } else {Terminal::cancelled(reservation)?};
        let p=state(s)?;p.retain_terminal(terminal)?;
        let c=s.shared.as_mut().ok_or_else(||model::bad())?;
        c.join_requested=false;c.commands.clear();
        if s.arena_base {c.phase=Phase::Leaving;}
        println!("P08B_TERMINAL_FROZEN session={} reason={reason:?} authority_revoked=true",s.id);
        Ok(())
    }
    pub(super) fn retire(&mut self,table:&mut Table,world:&mut World,id:u32,now:Instant,reason:&str)->io::Result<()> {
        let s=table.sessions.iter_mut().find(|s|s.id==id).ok_or_else(||model::bad())?;
        Self::terminal(s,world,FinishReason::Disconnect)?;
        let retain=s.shared.as_ref().and_then(|c|c.profile13.as_ref()).is_some_and(|p|
            p.in_flight || p.reservation.is_some() || p.pending_return.is_some());
        if retain {
            if self.retired.len()>=model::MAX_ACTORS {return Err(model::bad());}
            let mut retired=s.clone();retired.active=false;
            if let Some(c)=&mut retired.shared {c.join_requested=false;}
            self.retired.push(retired);
        }
        table.retire(id,world,now,reason)
    }
    fn deliver(s:&mut Session,completion:service::Completion,now:Instant)->io::Result<()> {
        let mut next=s.clone();
        Self::deliver_inner(&mut next,completion,now)?;
        *s=next;Ok(())
    }
    fn deliver_inner(s:&mut Session,completion:service::Completion,now:Instant)->io::Result<()> {
        let sid=s.id;
        if s.identity.as_ref().is_none_or(|p|p.account_id!=completion.old_owner.account_id) {return Err(model::bad());}
        let reply=completion.reply;
        if reply.status==ReplyStatus::Rejected {
            let p=state(s)?;p.in_flight=false;p.selection=None;
            // A rejected finish is not a successful return. Keep its immutable
            // terminal receipt for diagnosis/recovery; do not unlock the UI.
            if completion.request.finished_battle().is_some() {
                return Err(io::Error::new(io::ErrorKind::InvalidData,format!("P08B terminal rejected {:?}",reply.code)));
            }
            s.shared.as_mut().ok_or_else(||model::bad())?.join_requested=false;
            if s.active {s.outbox.push_back(crate::battle091::profile13::enqueue_failure(reply.code.as_deref().unwrap_or("UNAVAILABLE"))?);}
            println!("P08B_ADMISSION_REJECTED session={sid} code={:?} reserved=false",reply.code);
            return Ok(());
        }
        let fresh=completion.fresh.ok_or_else(||io::Error::new(io::ErrorKind::InvalidData,"P08B durable result awaiting trusted projection"))?;
        let recreate=reply.status==ReplyStatus::Finished && s.arena_base;
        if recreate {
            let old_wire=s.ammo_service.as_ref().ok_or_else(||model::bad())?.wire_revision();
            s.shared.as_mut().ok_or_else(||model::bad())?.return_source_revision=old_wire;
            s.ammo_service.as_mut().ok_or_else(||model::bad())?.rebind(fresh.binding)?;
        }
        else {s.ammo_service.as_mut().ok_or_else(||model::bad())?.refresh_revision(fresh.binding.revision)?;}
        s.identity=Some(fresh.owner);s.hangar=Some(fresh.fixtures);
        let p=state(s)?;p.revision=reply.revision;p.in_flight=false;
        match reply.status {
            ReplyStatus::Admitted=>{
                let receipt=reply.reservation.ok_or_else(||model::bad())?;
                p.reservation=Some(receipt);p.selection=None;
                let c=s.shared.as_mut().ok_or_else(||model::bad())?;
                if s.active && c.join_requested {
                    if s.outbox.len()>=128 {return Err(model::bad());}
                    s.outbox.push_back(crate::map_drive_world091::queue_callback(true));c.queue_announced=true;
                } else {
                    let terminal=Terminal::cancelled(c.profile13.as_ref().and_then(|p|p.reservation.as_ref()).ok_or_else(||model::bad())?)?;
                    c.profile13.as_mut().ok_or_else(||model::bad())?.retain_terminal(terminal)?;
                }
                println!("P08B_RESERVED session={sid} revision={} native_enqueue_confirmed={}",reply.revision,s.active&&c.join_requested);
            },
            ReplyStatus::Finished=>{
                p.reservation=None;p.pending_return=None;p.selection=None;
                if s.active {
                    if s.arena_base {
                        if s.shared.as_ref().is_some_and(|c|c.natural_result.is_some()) {
                            // Full result is already in the same durable writer
                            // transaction. Deliver it to Avatar before Account reset.
                            s.shared.as_mut().ok_or_else(||model::bad())?.result_committed=true;
                        } else {
                            let mut events=Vec::new();s.shared_return("profile13_result_committed",now,&mut events)?;
                            for event in events {println!("{event}");}
                        }
                    } else {
                        let c=s.shared.as_mut().ok_or_else(||model::bad())?;
                        if c.queue_announced {s.outbox.push_back(crate::map_drive_world091::queue_callback(false));}
                        c.queue_announced=false;c.join_requested=false;
                    }
                }
                println!("P08B_RESULT_COMMITTED session={sid} revision={} replayed={} account_reset_allowed=true",reply.revision,reply.replayed);
            },
            _=>return Err(model::bad()),
        }
        Ok(())
    }
    pub(super) fn poll(&mut self,table:&mut Table,config:Arc<crate::identity091::Config>,now:Instant)->io::Result<()> {
        if let Some(result)=self.job.as_mut().and_then(|j|j.poll()) {
            self.job=None;
            let task=self.task.as_ref().ok_or_else(||model::bad())?.clone();
            match result {
                Ok(completion) if completion.refresh_error.is_none()=>{
                    let finished=if completion.reply.status==ReplyStatus::Finished {
                        completion.request.finished_battle()
                    } else {None};
                    let target=table.sessions.iter_mut().chain(self.retired.iter_mut()).find(|s|s.id==task.session);
                    let Some(target)=target else {return Err(model::bad());};
                    match Self::deliver(target,completion,now) {
                        Ok(())=>{self.task=None;self.retry_at=None;if finished.is_some(){self.settled_queue=finished;}},
                        Err(error)=>{
                            println!("P08B_DELIVERY_ERROR session={} error={error} authority_closed=true retry_same_command=true",task.session);
                            state(target)?.in_flight=true;self.retry_at=Some(now+Duration::from_secs(2));
                        },
                    }
                },
                outcome=>{
                    match outcome {
                        Ok(c)=>println!("P08B_PROJECTION_RETRY session={} committed_status={:?} error={:?}",task.session,c.reply.status,c.refresh_error),
                        Err(e)=>println!("P08B_WRITER_RETRY session={} error={e} outcome_requires_recovery=true",task.session),
                    }
                    self.retry_at=Some(now+Duration::from_secs(2));
                },
            }
        }
        self.retired.retain(|s|s.shared.as_ref().and_then(|c|c.profile13.as_ref()).is_some_and(|p|
            p.in_flight || p.reservation.is_some() || p.pending_return.is_some()));
        if self.job.is_none() && self.task.is_some() && self.retry_at.is_none_or(|at|now>=at) {
            self.job=Some(self.task.as_ref().ok_or_else(||model::bad())?.start(config)?);
        }
        Ok(())
    }
    pub(super) fn start(&mut self,table:&mut Table,world:&World,config:Arc<crate::identity091::Config>,now:Instant)->io::Result<()> {
        if self.task.is_some() || self.job.is_some() {return Ok(());}
        // Terminal receipts always precede new admissions. Retired owners stay
        // fenced until their known/ambiguous writer outcome is resolved.
        for terminal_only in [true,false] {
            for s in self.retired.iter_mut().chain(table.sessions.iter_mut()) {
                let Some(c)=&s.shared else {continue;};
                let Some(p)=&c.profile13 else {continue;};
                if p.in_flight {return Err(model::bad());}
                let pending=p.pending_return.is_some();
                if terminal_only!=pending {continue;}
                // A scene ACK can postpone membership removal. Persistence may
                // freeze now, but Account recreation waits until the actor is
                // actually detached (or the entire failed world was replaced).
                if pending && world.actors.iter().any(|a|a.session==Some(s.id)) {continue;}
                if !pending && (world.started.is_some() || p.selection.is_none() || !s.active || !c.join_requested
                    || !s.ammo_service.as_ref().is_some_and(ammo_session::State::idle)) {continue;}
                let owner=s.identity.clone().ok_or_else(||model::bad())?;
                let revision=s.ammo_service.as_ref().ok_or_else(||model::bad())?.revision();
                let sid=s.id;let p=state(s)?;p.revision=revision;
                let request=if let Some(t)=&p.pending_return {t.request()} else {Request::Admit{
                    battle:world.id,native_inventory_id:p.selection.ok_or_else(||model::bad())?}};
                let context=p.next_context(&owner,sid)?;
                let task=Task{session:sid,owner,context,request};
                let job=task.start(config.clone())?;p.in_flight=true;
                println!("P08B_WRITER_DISPATCH session={sid} operation={} expected_revision={} battle={}",task.request.operation(),task.context.expected_revision,world.id);
                self.task=Some(task);self.job=Some(job);self.retry_at=Some(now);return Ok(());
            }
        }
        Ok(())
    }
}

#[cfg(test)]
#[path="profile13_flow_tests.rs"]
mod flow_tests;
