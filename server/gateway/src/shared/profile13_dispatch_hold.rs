//! API5 branch of the existing Dispatcher, never a second writer scheduler.
//! All external work owns an immutable task. Known completions survive native
//! backpressure; a retry cannot replace its source key or actor snapshot.
use super::*;
use crate::profile13_hold091 as hold;
use super::super::owner_hold_delivery as delivery;
use super::super::super::owner_hold_capture::{Capture,pristine_cancel};

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
enum Purpose{Admit,Inspect{slot:usize,recipient:u32},Final(usize),Pristine}
#[derive(Clone)]
struct TaskHold{session:u32,owner:Arc<crate::identity091::Profile>,context:hold::Context,request:hold::Request,purpose:Purpose}
impl TaskHold{
    fn start(&self,config:Arc<crate::identity091::Config>)->io::Result<service::JobHold>{
        service::JobHold::start(self.session,self.owner.clone(),config,self.context.clone(),self.request.clone())
    }
    fn check(&self,c:&service::CompletionHold)->io::Result<()>{
        if c.source_session!=self.session||c.old_owner.account_id!=self.owner.account_id||c.old_owner.database_id!=self.owner.database_id
            ||c.old_owner.name!=self.owner.name||c.context!=self.context||c.request!=self.request{return Err(model::bad());}Ok(())
    }
}
#[derive(Default)]
pub(super) struct HoldState{
    pub(super) capture:Option<Capture>,settled:[bool;6],task:Option<TaskHold>,job:Option<service::JobHold>,
    completed:Option<service::CompletionHold>,retry:Option<Instant>,
}
impl HoldState{
    pub(super) fn busy(&self)->bool{self.task.is_some()||self.job.is_some()||self.completed.is_some()}
    pub(super) fn unsettled(&self)->bool{self.capture.is_some()}
    pub(super) fn owner_busy(&self,owner:&str)->bool{self.task.as_ref().is_some_and(|t|t.owner.account_id==owner)}
}
impl Dispatcher{
    /// Hold5 avoids an unattached-Account/parked-actor gap: the whole admitted
    /// group attaches/registers in one loop transaction immediately before the
    /// ordinary start call. Older versions keep their original per-peer path.
    pub(in super::super) fn attach_hold_ready_group(&mut self,table:&mut Table,world:&mut World,run:&str,now:Instant)->io::Result<()>{
        if !world.owner_hold_enabled()||world.started.is_some(){return Ok(());}
        if !world.actors.is_empty(){return Err(model::bad());}
        if table.sessions.len()!=world.expected_actors()||table.sessions.iter().any(|s|!entry_ready(s,now)
            ||s.shared.as_ref().and_then(|c|c.profile13.as_ref()).and_then(|p|p.reservation_hold.as_ref()).is_none_or(|r|r.battle!=world.id)){
            return Ok(());
        }
        if self.hold.capture.is_some(){return Err(model::bad());}
        let mut next_world=world.clone();let mut next_table=Table{sessions:table.sessions.clone(),retirement:RetirementWindow::default(),capacity:table.capacity,arena_split:table.arena_split,multi_arena:table.multi_arena};
        attach_waiting_sessions(&mut next_table,&mut next_world,now)?;
        let mut capture=Capture::new(run.to_owned(),world.id)?;
        for(slot,a)in next_world.actors.iter().enumerate(){let sid=a.session.ok_or_else(||model::bad())?;
            let s=next_table.sessions.iter().find(|s|s.id==sid).ok_or_else(||model::bad())?;
            let p=s.shared.as_ref().and_then(|c|c.profile13.as_ref()).ok_or_else(||model::bad())?;
            capture.register(&next_world,slot,sid,s.identity.clone().ok_or_else(||model::bad())?,p.reservation_hold.clone().ok_or_else(||model::bad())?,p.revision)?;
        }
        if next_world.actors.len()!=world.expected_actors(){return Err(model::bad());}
        table.sessions=next_table.sessions;*world=next_world;self.hold.capture=Some(capture);Ok(())
    }
    pub(super) fn terminal_hold(s:&mut Session,world:&World,reason:FinishReason)->io::Result<()>{
        let p=state(s)?;
        if p.reservation_hold.is_none(){return Ok(());}
        if p.reservation.is_some()||p.reservation_v2.is_some()||p.reservation_loss.is_some(){return Err(model::bad());}
        p.selection=None;p.hold_return_pending=true;
        if world.lifecycle.as_ref().is_none_or(|l|l.outcome().is_none())&&p.hold_departure_reason.is_none(){
            p.hold_departure_reason=match reason{FinishReason::ManualLeave=>Some(hold::DepartureReason::ManualLeave),
                FinishReason::Disconnect=>Some(hold::DepartureReason::Disconnect),_=>None};
        }
        let c=s.shared.as_mut().ok_or_else(||model::bad())?;c.join_requested=false;c.commands.clear();
        if s.arena_base{c.phase=Phase::Leaving;}
        Ok(())
    }
    pub(in super::super) fn install_hold_login(&self,s:&mut Session,login:crate::identity091::HoldLogin)->io::Result<()>{
        let owner=s.identity.as_ref().ok_or_else(||model::bad())?;
        let h=s.hangar.as_ref().ok_or_else(||model::bad())?;
        let sha=h.state_sha256().iter().map(|b|format!("{b:02x}")).collect::<String>();
        let rev=s.ammo_service.as_ref().ok_or_else(||model::bad())?.revision();
        if !login.projection.matches(&owner.account_id,owner.database_id,rev,&sha){return Err(model::bad());}
        if let Some(r)=&login.reservation{
            let capture=self.hold.capture.as_ref().ok_or_else(||model::bad())?;
            delivery::check_locked_resume(capture,owner,&login.reply,&login.projection,&sha)?;
            let p=state(s)?;p.reservation_hold=Some(r.clone());p.hold_projection=Some(Arc::new(login.projection));p.hold_account_only=true;
        }
        // With no active reservation this is an ordinary authoritative Fresh;
        // never cache an obsolete held projection or issue an Avatar grant.
        Ok(())
    }
    /// Run only against the accepted World, after actual detach/scene ACK and
    /// before lifecycle result publication may detach natural recipients.
    pub(in super::super) fn observe_hold_world(&mut self,table:&Table,world:&World)->io::Result<()>{
        if !world.owner_hold_enabled(){return Ok(());}
        let Some(capture)=&mut self.hold.capture else{return Ok(());};
        if capture.links().first().is_none_or(|l|l.source().battle!=world.id)||capture.seal().is_some(){return Ok(());}
        for s in table.sessions.iter().chain(self.retired.iter()){
            let Some(p)=s.shared.as_ref().and_then(|c|c.profile13.as_ref())else{continue;};
            let Some(reason)=p.hold_departure_reason else{continue;};
            let slot=capture.links().iter().find_map(|l|(l.source().source_session_id==s.id).then_some(l.source().actor_slot as usize));
            if let Some(slot)=slot.filter(|slot|world.actors.get(*slot).is_some_and(|a|a.session.is_none())){
                capture.departed_after_detach(world,slot,s.id,reason)?;
            }
        }
        if world.lifecycle.as_ref().is_some_and(|l|l.outcome().is_some()){capture.freeze_outcome(world)?;}
        Ok(())
    }
    pub(in super::super) fn before_hold_reset(&mut self,world:&World)->io::Result<()>{
        if let Some(c)=&mut self.hold.capture{
            if c.links().first().is_some_and(|l|l.source().battle==world.id)&&c.seal().is_none(){c.freeze_contained_failure(world)?;}
        }Ok(())
    }
    /// A real registered actor can exist after World.start while its native
    /// Account has not become Avatar. Its cancellation is a contained startup
    /// failure, never a fake Avatar return or a no-actor pristine refund.
    pub(in super::super) fn hold_pre_avatar_failure(&self,table:&Table,world:&World)->Option<io::Error>{
        let c=self.hold.capture.as_ref()?;
        if world.started.is_none()||c.seal().is_some()||c.links().first()?.source().battle!=world.id{return None;}
        c.links().iter().any(|link|table.sessions.iter().chain(self.retired.iter()).any(|s|
            s.id==link.source().source_session_id&&!s.arena_base&&s.shared.as_ref().and_then(|c|c.profile13.as_ref()).is_some_and(|p|
                p.reservation_hold.as_ref()==Some(link.reservation())&&!p.hold_account_only&&p.hold_return_pending)))
            .then(||io::Error::new(io::ErrorKind::InvalidData,"hold5 registered pre-Avatar departure; contained startup failure"))
    }
    pub(in super::super) fn hold_results(&self,battle:u64)->Option<Arc<super::super::super::lifecycle_wire::Results>>{
        self.hold.capture.as_ref().filter(|c|c.links().first().is_some_and(|l|l.source().battle==battle))
            .and_then(|c|c.seal()).and_then(|s|s.results()).cloned()
    }
    fn finish_hold_task(&mut self){self.hold.task=None;self.hold.completed=None;self.hold.retry=None;}
    fn hold_only(&self)->io::Result<()>{
        if self.job.is_some()||self.task.is_some()||self.job_v2.is_some()||self.task_v2.is_some()||self.job_loss.is_some()||self.task_loss.is_some()
            ||self.training_finished.is_some(){return Err(model::bad());}Ok(())
    }
    fn publish_hold_completed(&mut self,table:&mut Table,now:Instant)->io::Result<()> {
        let task=self.hold.task.as_ref().ok_or_else(||model::bad())?.clone();
        let c=self.hold.completed.as_ref().ok_or_else(||model::bad())?;task.check(c)?;
        if c.refresh_error.is_some(){return Err(model::bad());}
        if c.reply.status==hold::Status::Rejected{
            if task.purpose!=Purpose::Admit{return Err(io::Error::new(io::ErrorKind::InvalidData,"hold5 terminal/Inspect rejected; authority remains closed"));}
            let s=table.sessions.iter_mut().chain(self.retired.iter_mut()).find(|s|s.id==task.session).ok_or_else(||model::bad())?;
            let mut next=s.clone();let p=state(&mut next)?;p.in_flight=false;p.selection=None;
            next.shared.as_mut().ok_or_else(||model::bad())?.join_requested=false;
            if next.active{if next.outbox.len()>=128{return Err(model::bad());}
                next.outbox.push_back(crate::battle091::profile13::enqueue_failure(c.reply.code.as_deref().ok_or_else(||model::bad())?)?);next.drain_outbox()?;}
            *s=next;self.finish_hold_task();
            self.retired.retain(|s|s.shared.as_ref().and_then(|c|c.profile13.as_ref()).is_some_and(|p|p.in_flight||p.has_reservation()||p.has_pending_return()));return Ok(());
        }
        match task.purpose{
            Purpose::Admit=>{
                let s=table.sessions.iter_mut().chain(self.retired.iter_mut()).find(|s|s.id==task.session).ok_or_else(||model::bad())?;
                let mut staged=delivery::stage_admitted(s,c)?;
                if staged.needs_pristine_cancel{state(&mut staged.session)?.hold_return_pending=true;}
                *s=staged.session;for d in staged.diagnostics{println!("{d}");}
            },
            Purpose::Inspect{slot,recipient}=>{
                let capture=self.hold.capture.as_ref().ok_or_else(||model::bad())?;
                // Outcome won the race: join/read reply is drained; no stale
                // reserved return is published. The sealed final now wins.
                if capture.seal().is_none(){
                    let s=table.sessions.iter().chain(self.retired.iter()).find(|s|s.id==recipient).ok_or_else(||model::bad())?;
                    let staged=delivery::stage_held_return(s,capture,slot,c,now)?;
                    if let Some(next)=staged.session{
                        let recipient=next.id;
                        *table.sessions.iter_mut().find(|s|s.id==recipient).ok_or_else(||model::bad())?=next;
                    }
                    if let Some(id)=staged.release_retired_source{self.retired.retain(|s|s.id!=id);}
                    self.hold.capture=Some(staged.capture);for d in staged.diagnostics{println!("{d}");}
                }else if let Some(s)=table.sessions.iter_mut().chain(self.retired.iter_mut()).find(|s|s.id==recipient){state(s)?.in_flight=false;}
            },
            Purpose::Final(slot)=>{
                let capture=self.hold.capture.as_ref().ok_or_else(||model::bad())?;
                let staged=if let Some(index)=delivery::current_final_recipient(&table.sessions,capture,slot,c.reply.revision)?{
                    Some((index,delivery::stage_final(&table.sessions[index],capture,slot,c,now)?))
                }else{delivery::validate_finished_without_delivery(capture,slot,c)?;None};
                let source=capture.link(slot)?.reservation();
                let exact=self.retired.iter().filter(|s|s.shared.as_ref().and_then(|c|c.profile13.as_ref()).and_then(|p|p.reservation_hold.as_ref())==Some(source))
                    .map(|s|{delivery::validate_retired_source(s,capture,slot)?;Ok(s.id)}).collect::<io::Result<Vec<_>>>()?;
                if let Some((index,stage))=staged{table.sessions[index]=stage.session;for d in stage.diagnostics{println!("{d}");}}
                // Exact typed receipt+source cache, including a later locked
                // Account SID. A foreign receipt is never retired by owner only.
                self.retired.retain(|s|!exact.contains(&s.id));
                self.hold.settled[slot]=true;
                println!("P08B_HOLD5_FINISHED source_session={} battle={} slot={slot} revision={} replayed={}",task.session,c.request.finished_battle().unwrap_or(0),c.reply.revision,c.reply.replayed);
            },
            Purpose::Pristine=>{
                let s=table.sessions.iter_mut().chain(self.retired.iter_mut()).find(|s|s.id==task.session).ok_or_else(||model::bad())?;
                let staged=delivery::stage_pristine_finished(s,c)?;*s=staged.session;for d in staged.diagnostics{println!("{d}");}
                self.settled_queue=c.request.finished_battle();
            },
        }
        self.finish_hold_task();
        self.retired.retain(|s|s.shared.as_ref().and_then(|c|c.profile13.as_ref()).is_some_and(|p|p.in_flight||p.has_reservation()||p.has_pending_return()));
        if self.hold.capture.as_ref().is_some_and(|c|c.seal().is_some()&&c.links().iter().all(|l|self.hold.settled[l.source().actor_slot as usize])){
            self.settled_queue=self.hold.capture.as_ref().and_then(|c|c.links().first()).map(|l|l.source().battle);
            self.hold.capture=None;self.hold.settled=[false;6];
        }Ok(())
    }
    pub(super) fn poll_hold(&mut self,table:&mut Table,config:Arc<crate::identity091::Config>,now:Instant)->io::Result<()>{
        self.hold_only()?;
        if let Some(done)=self.hold.job.as_mut().and_then(|j|j.poll()){
            self.hold.job=None;
            match done{
                Ok(c)if c.refresh_error.is_none()=>{self.hold.completed=Some(c);self.hold.retry=None;},
                Ok(c)=>{println!("P08B_HOLD5_PROJECTION_RETRY source_session={} committed_status={:?} known_reply_retained=true readonly_fresh_retry=true",c.source_session,c.reply.status);self.hold.completed=Some(c);self.hold.retry=Some(now+Duration::from_secs(2));},
                Err(error)=>{println!("P08B_HOLD5_WRITER_RETRY error={error} immutable_task_retained=true");self.hold.retry=Some(now+Duration::from_secs(2));},
            }
        }
        if self.hold.completed.is_some(){
            if self.hold.retry.is_some_and(|at|now<at){return Ok(());}
            if self.hold.completed.as_ref().is_some_and(|c|c.refresh_error.is_some()){
                if self.hold.job.is_none(){match service::JobHold::refresh(self.hold.completed.as_ref().ok_or_else(||model::bad())?,config){
                    Ok(job)=>{self.hold.job=Some(job);self.hold.retry=None;},
                    Err(error)=>{println!("P08B_HOLD5_FRESH_START_RETRY error={error} known_reply_retained=true");self.hold.retry=Some(now+Duration::from_secs(2));}
                }}return Ok(());
            }
            if let Err(error)=self.publish_hold_completed(table,now){
                println!("P08B_HOLD5_DELIVERY_RETAINED error={error} same_completed_reply=true authority_closed=true");
                self.hold.retry=Some(now+Duration::from_secs(2));
                // Known reply remains in memory. Never repeat SQL just because
                // a current native Window/warm Account cannot accept it yet.
            }return Ok(());
        }
        if self.hold.task.is_some()&&self.hold.job.is_none()&&self.hold.retry.is_none_or(|at|now>=at){
            match self.hold.task.as_ref().ok_or_else(||model::bad())?.start(config){
                Ok(job)=>{self.hold.job=Some(job);self.hold.retry=None;},
                Err(error)=>{println!("P08B_HOLD5_SPAWN_RETRY error={error} immutable_task_retained=true");self.hold.retry=Some(now+Duration::from_secs(2));}
            }
        }Ok(())
    }
    fn install_hold_task(&mut self,table:&mut Table,task:TaskHold,config:Arc<crate::identity091::Config>,now:Instant)->io::Result<()>{
        hold::encode_request(&task.context,&task.request)?;
        if self.hold.busy(){return Err(model::bad());}
        if let Some(s)=table.sessions.iter_mut().chain(self.retired.iter_mut()).find(|s|s.id==task.session){state(s)?.in_flight=true;}
        self.hold.task=Some(task);self.hold.retry=Some(now);
        // The immutable task survives even an OS thread-start failure.
        self.poll_hold(table,config,now)
    }
    pub(super) fn start_hold(&mut self,table:&mut Table,world:&World,config:Arc<crate::identity091::Config>,now:Instant)->io::Result<()>{
        self.hold_only()?;if self.hold.busy(){return Ok(());}
        self.observe_hold_world(table,world)?;
        if let Some(c)=&self.hold.capture{
            if let Some(seal)=c.seal(){
                for link in c.links(){let slot=link.source().actor_slot as usize;if self.hold.settled[slot]{continue;}
                    let task=TaskHold{session:link.source().source_session_id,owner:link.owner().clone(),context:link.context(true),request:hold::Request::Finish(seal.finish(slot)?.clone()),purpose:Purpose::Final(slot)};
                    return self.install_hold_task(table,task,config,now);
                }
            }else{
                for link in c.links(){let slot=link.source().actor_slot as usize;
                    if c.departure(slot)?.is_some()&&!c.held_inspected(slot)?{
                        let recipient=self.retired.iter().chain(table.sessions.iter()).find(|s|s.shared.as_ref().and_then(|c|c.profile13.as_ref()).and_then(|p|p.reservation_hold.as_ref())==Some(link.reservation())).map(|s|s.id).ok_or_else(||model::bad())?;
                        let task=TaskHold{session:link.source().source_session_id,owner:link.owner().clone(),context:link.context(false),request:hold::Request::Inspect,purpose:Purpose::Inspect{slot,recipient}};
                        return self.install_hold_task(table,task,config,now);
                    }
                }
            }
        }
        for s in self.retired.iter_mut().chain(table.sessions.iter_mut()){
            let Some(c)=s.shared.as_ref()else{continue;};let Some(p)=c.profile13.as_ref()else{continue;};
            if p.reservation.is_some()||p.reservation_v2.is_some()||p.reservation_loss.is_some()||p.in_flight{return Err(model::bad());}
            if let Some(r)=p.reservation_hold.as_ref(){
                let registered=self.hold.capture.as_ref().is_some_and(|cap|cap.links().iter().any(|l|l.reservation().reservation_id==r.reservation_id));
                if p.hold_return_pending&&!p.hold_account_only&&!registered&&!world.actors.iter().any(|a|a.owned_hold.as_ref()==Some(&r.frozen)){
                    let owner=s.identity.clone().ok_or_else(||model::bad())?;
                    let fingerprint={use sha2::{Digest,Sha256};format!("{:x}",Sha256::digest(r.reservation_id.as_bytes()))};
                    let task=TaskHold{session:s.id,owner:owner.clone(),context:hold::Context{account_id:owner.account_id.clone(),native_database_id:owner.database_id,
                        command_key:format!("hold5:final:{fingerprint}"),expected_revision:p.revision,run_id:p.run_id.clone()},
                        request:hold::Request::Finish(pristine_cancel(r,&owner)?),purpose:Purpose::Pristine};
                    return self.install_hold_task(table,task,config,now);
                }continue;
            }
            if self.hold.capture.as_ref().is_some_and(|c|c.seal().is_some())||world.started.is_some()||p.selection.is_none()||!s.active||!c.join_requested
                ||p.has_pending_return()||!s.ammo_service.as_ref().is_some_and(ammo_session::State::idle){continue;}
            let owner=s.identity.clone().ok_or_else(||model::bad())?;let sid=s.id;let revision=s.ammo_service.as_ref().ok_or_else(||model::bad())?.revision();
            let p=state(s)?;p.revision=revision;let native_inventory_id=p.selection.ok_or_else(||model::bad())?;let context=p.next_context(&owner,sid)?;
            let task=TaskHold{session:sid,owner,context,request:hold::Request::Admit{battle:world.id,native_inventory_id},purpose:Purpose::Admit};
            return self.install_hold_task(table,task,config,now);
        }Ok(())
    }
}

#[cfg(test)]
#[path="owner_hold_integration_tests.rs"]
mod tests;

// Test-only immutable observations; no worker/receipt/authority injection.
#[cfg(test)]
impl Dispatcher{
    pub(in super::super) fn hold_capture_for_test(&self)->Option<&Capture>{self.hold.capture.as_ref()}
    pub(in super::super) fn hold_final_completed_for_test(&self)->Option<(u32,u64)>{
        if !self.hold.task.as_ref().is_some_and(|t|matches!(t.purpose,Purpose::Final(_))){return None;}
        self.hold.completed.as_ref().filter(|c|c.refresh_error.is_none()&&c.fresh.is_some()&&c.reply.status==hold::Status::Finished).map(|c|(c.source_session,c.reply.revision))
    }
}
