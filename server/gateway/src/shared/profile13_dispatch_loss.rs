//! Version4 ammo-loss branch of the same single-account writer dispatcher.
use super::*;
use crate::profile13_loss091::{Request as RequestLoss,Status};

#[derive(Clone)]
pub(super) struct TaskLoss{pub(super) session:u32,pub(super) owner:Arc<crate::identity091::Profile>,pub(super) context:Context,pub(super) request:RequestLoss}
impl TaskLoss{fn start(&self,config:Arc<crate::identity091::Config>)->io::Result<service::JobLoss>{
    service::JobLoss::start(self.session,self.owner.clone(),config,self.context.clone(),self.request.clone())}}

impl Dispatcher{
    pub(super) fn terminal_loss(s:&mut Session,world:&World,reason:FinishReason)->io::Result<()>{
        let Some(p)=s.shared.as_ref().and_then(|c|c.profile13.as_ref())else{return Ok(());};
        if p.pending_return_loss.is_some(){return Ok(());}
        if p.reservation_v2.is_some()||p.pending_return_v2.is_some()||p.reservation.is_some()||p.pending_return.is_some(){return Err(model::bad());}
        let Some(reservation)=&p.reservation_loss else{return Ok(());};
        let natural=s.shared.as_ref().and_then(|c|c.natural_result.as_deref());let reason=if natural.is_some(){FinishReason::BattleFinished}else{reason};
        let terminal=if world.actors.iter().any(|a|a.session==Some(s.id)){
            service::TerminalLoss::from_actor_result(reservation,world,s.shared.as_ref().ok_or_else(||model::bad())?.slot,s.id,reason,natural)?
        }else{service::TerminalLoss::cancelled(reservation,s.identity.as_ref().ok_or_else(||model::bad())?.database_id)?};
        state(s)?.retain_terminal_loss(terminal)?;
        let c=s.shared.as_mut().ok_or_else(||model::bad())?;c.join_requested=false;c.commands.clear();if s.arena_base{c.phase=Phase::Leaving;}
        println!("P06T_LOSS_TERMINAL_FROZEN session={} reason={reason:?} authority_revoked=true",s.id);Ok(())
    }
    pub(super) fn deliver_loss(s:&mut Session,completion:service::CompletionLoss,now:Instant)->io::Result<()>{
        let mut next=s.clone();Self::deliver_loss_inner(&mut next,completion,now)?;*s=next;Ok(())
    }
    fn deliver_loss_inner(s:&mut Session,completion:service::CompletionLoss,now:Instant)->io::Result<()>{
        let sid=s.id;
        if s.identity.as_ref().is_none_or(|p|p.account_id!=completion.old_owner.account_id){return Err(model::bad());}
        let reply=completion.reply;
        if reply.status==Status::Rejected{
            let p=state(s)?;p.in_flight=false;p.selection=None;
            if completion.request.finished_battle().is_some(){return Err(io::Error::new(io::ErrorKind::InvalidData,format!("P06T terminal rejected {:?}",reply.code)));}
            s.shared.as_mut().ok_or_else(||model::bad())?.join_requested=false;
            if s.active{s.outbox.push_back(crate::battle091::profile13::enqueue_failure(reply.code.as_deref().unwrap_or("UNAVAILABLE"))?);}
            println!("P06T_LOSS_ADMISSION_REJECTED session={sid} code={:?} reserved=false",reply.code);return Ok(());
        }
        let fresh=completion.fresh.ok_or_else(||io::Error::new(io::ErrorKind::InvalidData,"P06T durable result awaiting trusted projection"))?;
        let recreate=reply.status==Status::Finished&&s.arena_base;
        if recreate{
            let old_wire=s.ammo_service.as_ref().ok_or_else(||model::bad())?.wire_revision();
            s.shared.as_mut().ok_or_else(||model::bad())?.return_source_revision=old_wire;
            s.ammo_service.as_mut().ok_or_else(||model::bad())?.rebind(fresh.binding)?;
        }else{s.ammo_service.as_mut().ok_or_else(||model::bad())?.refresh_revision(fresh.binding.revision)?;}
        s.ammo_service.as_mut().ok_or_else(||model::bad())?.replace_pool(fresh.fixtures.p04m_binding().cloned())?;
        s.identity=Some(fresh.owner);s.hangar=Some(fresh.fixtures);
        let database=s.identity.as_ref().ok_or_else(||model::bad())?.database_id;
        let p=state(s)?;if p.reservation_v2.is_some()||p.pending_return_v2.is_some()||p.reservation.is_some()||p.pending_return.is_some(){return Err(model::bad());}
        p.revision=reply.revision;p.in_flight=false;
        match reply.status{
            Status::Admitted=>{
                p.reservation_loss=Some(reply.reservation.ok_or_else(||model::bad())?);p.selection=None;
                let c=s.shared.as_mut().ok_or_else(||model::bad())?;
                if s.active&&c.join_requested{
                    if s.outbox.len()>=128{return Err(model::bad());}s.outbox.push_back(crate::map_drive_world091::queue_callback(true));c.queue_announced=true;
                }else{
                    let terminal=service::TerminalLoss::cancelled(c.profile13.as_ref().and_then(|p|p.reservation_loss.as_ref()).ok_or_else(||model::bad())?,database)?;
                    c.profile13.as_mut().ok_or_else(||model::bad())?.retain_terminal_loss(terminal)?;
                }
                println!("P06T_LOSS_RESERVED session={sid} revision={} native_enqueue_confirmed={}",reply.revision,s.active&&c.join_requested);
            },
            Status::Finished=>{
                p.reservation_loss=None;p.pending_return_loss=None;p.selection=None;
                if s.active{
                    if s.arena_base{
                        if s.shared.as_ref().is_some_and(|c|c.natural_result.is_some()){
                            s.shared.as_mut().ok_or_else(||model::bad())?.result_committed=true;
                        }else{let mut events=Vec::new();s.shared_return("profile13_loss_result_committed",now,&mut events)?;for event in events{println!("{event}");}}
                    }else{let c=s.shared.as_mut().ok_or_else(||model::bad())?;
                        if c.queue_announced{s.outbox.push_back(crate::map_drive_world091::queue_callback(false));}c.queue_announced=false;c.join_requested=false;}
                }
                println!("P06T_LOSS_RESULT_COMMITTED session={sid} revision={} replayed={} account_reset_allowed=true",reply.revision,reply.replayed);
            },_=>return Err(model::bad()),
        }Ok(())
    }
    pub(super) fn poll_loss(&mut self,table:&mut Table,config:Arc<crate::identity091::Config>,now:Instant)->io::Result<()>{
        if self.job_v2.is_some()||self.task_v2.is_some()||self.job.is_some()||self.task.is_some(){return Err(model::bad());}
        if let Some(result)=self.job_loss.as_mut().and_then(|j|j.poll()){
            self.job_loss=None;let task=self.task_loss.as_ref().ok_or_else(||model::bad())?.clone();
            match result{
                Ok(completion)if completion.refresh_error.is_none()=>{
                    let finished=if completion.reply.status==Status::Finished{completion.request.finished_battle()}else{None};
                    let target=table.sessions.iter_mut().chain(self.retired.iter_mut()).find(|s|s.id==task.session).ok_or_else(||model::bad())?;
                    match Self::deliver_loss(target,completion,now){
                        Ok(())=>{self.task_loss=None;self.retry_at=None;if finished.is_some(){self.settled_queue=finished;}},
                        Err(e)=>{println!("P06T_LOSS_DELIVERY_ERROR session={} error={e} authority_closed=true retry_same_command=true",task.session);
                            state(target)?.in_flight=true;self.retry_at=Some(now+Duration::from_secs(2));},
                    }
                },outcome=>{
                    match outcome{Ok(c)=>println!("P06T_LOSS_PROJECTION_RETRY session={} committed_status={:?} error={:?}",task.session,c.reply.status,c.refresh_error),
                        Err(e)=>println!("P06T_LOSS_WRITER_RETRY session={} error={e} outcome_requires_recovery=true",task.session)}
                    self.retry_at=Some(now+Duration::from_secs(2));
                }
            }
        }
        self.retired.retain(|s|s.shared.as_ref().and_then(|c|c.profile13.as_ref()).is_some_and(|p|p.in_flight||p.reservation_loss.is_some()||p.pending_return_loss.is_some()));
        if self.job_loss.is_none()&&self.task_loss.is_some()&&self.retry_at.is_none_or(|at|now>=at){self.job_loss=Some(self.task_loss.as_ref().ok_or_else(||model::bad())?.start(config)?);}Ok(())
    }
    pub(super) fn start_loss(&mut self,table:&mut Table,world:&World,config:Arc<crate::identity091::Config>,now:Instant)->io::Result<()>{
        if self.task_v2.is_some()||self.job_v2.is_some()||self.task.is_some()||self.job.is_some(){return Err(model::bad());}
        if self.task_loss.is_some()||self.job_loss.is_some(){return Ok(());}
        if !world.mixed_ammo(){return Err(model::bad());}
        for terminal_only in[true,false]{for s in self.retired.iter_mut().chain(table.sessions.iter_mut()){
            let Some(c)=&s.shared else{continue;};let Some(p)=&c.profile13 else{continue;};
            if p.reservation_v2.is_some()||p.pending_return_v2.is_some()||p.in_flight||p.reservation.is_some()||p.pending_return.is_some(){return Err(model::bad());}
            let pending=p.pending_return_loss.is_some();if terminal_only!=pending{continue;}
            if pending&&world.actors.iter().any(|a|a.session==Some(s.id)){continue;}
            if !pending&&(p.reservation_loss.is_some()||world.started.is_some()||p.selection.is_none()||!s.active||!c.join_requested||!s.ammo_service.as_ref().is_some_and(ammo_session::State::idle)){continue;}
            let owner=s.identity.clone().ok_or_else(||model::bad())?;let revision=s.ammo_service.as_ref().ok_or_else(||model::bad())?.revision();let sid=s.id;
            let p=state(s)?;p.revision=revision;let request=if let Some(t)=&p.pending_return_loss{t.request()}else{RequestLoss::Admit{battle:world.id,native_inventory_id:p.selection.ok_or_else(||model::bad())?}};
            let context=p.next_context(&owner,sid)?;let task=TaskLoss{session:sid,owner,context,request};let job=task.start(config.clone())?;p.in_flight=true;
            println!("P06T_LOSS_WRITER_DISPATCH session={sid} operation={} expected_revision={} battle={}",task.request.operation(),task.context.expected_revision,world.id);
            self.task_loss=Some(task);self.job_loss=Some(job);self.retry_at=Some(now);return Ok(());
        }}Ok(())
    }
}

#[cfg(test)]
#[path="profile13_queue_loss_tests.rs"]
mod queue_loss_tests;

