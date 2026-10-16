//! Explicit native-room host. Socket writes and external jobs remain outside
//! complete-frame clones; no random-queue admission while this mode is active.
use super::*;
use std::collections::{BTreeMap,BTreeSet,VecDeque};
use crate::training091::{controller::{Controller,Batch},domain as room,stream_flight as flight};
use super::{p10b_receive_host as receive,p10b_ready_host as readiness,p10b_launch_host as launch,p10b_preparing_host as prepare};
fn bad(message:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,message)}
const HANDOFF_TIMEOUT:Duration=Duration::from_secs(60);
const HANDOFF_POLICY:&str="test_lab.p10b.account-handoff-deadline-60s.v1";
struct Active{battle:room::BattleKey,selected:Vec<u32>,finished:Vec<room::FinishedRef>,committed_at:Instant}
#[derive(Clone)]
struct ClosedMember{
    origin:receive::RetainedMember,
    // Optional old accepted ReadyTask is display/origin evidence only. A bench
    // entry never becomes a Saga slot or a Reserved/Released/Finished proof.
    display_task:Option<crate::training091::controller::ReadyTask>,
}
#[derive(Default)]pub(super) struct Host{
    mode:super::super::p10b_writer_mode::Mode,controller:Controller,ready:readiness::Manager,bindings:BTreeMap<u32,[u8;32]>,
    preparing:Option<prepare::Preparing>,driver:prepare::Driver,active:Option<Active>,
    deferred:Vec<receive::DeferredRead>,retired_closed:BTreeSet<u32>,closed_members:BTreeMap<room::Account,ClosedMember>,
}
/// A pure staged reset for an entirely compensated Preparing scope. The real
/// Saga/Controller release proof is still required by the AllReleased caller.
/// Construction never drops the old runtime or touches live state.
struct CompensatedReset{world:World,runtime:Option<IntegratedRuntime>}
impl CompensatedReset{
    fn stage(world:&World,runtime:&Option<IntegratedRuntime>,template:&BattleTemplate,battle:room::BattleKey,now:Instant)->io::Result<Self>{
        if world.id!=battle.0||world.started.is_some()||!world.actors.is_empty()
            ||runtime.as_ref().is_some_and(|r|r.started||r.staged.is_some()||r.workers.iter().any(Option::is_some)||r.blocked()){
            return Err(bad("P10B compensated reset requires its exact pristine battle"));
        }
        // Validate the live empty world too, not just the source template. A
        // stray journal/scene transaction must not be silently thrown away.
        let next=world.id.checked_add(1).filter(|id|*id<=i64::MAX as u64).ok_or_else(||bad("P10B compensated battle id overflow"))?;
        drop(world.fresh_battle(next,now)?);
        let fresh=template.world.fresh_battle(next,now)?;
        let prepared_runtime=template.runtime(fresh.map)?;
        Ok(Self{world:fresh,runtime:prepared_runtime})
    }
    fn commit(self,world:&mut World,runtime:&mut Option<IntegratedRuntime>){*world=self.world;*runtime=self.runtime;}
}
impl Host{
    pub(super) fn for_config(config:&crate::identity091::Config)->io::Result<Self>{
        Ok(Self{mode:super::super::p10b_writer_mode::Mode::config(config)?,..Self::default()})
    }
    pub(super) fn bind_session(&mut self,s:&mut Session)->io::Result<()>{
        if self.bindings.len()>=room::MAX_ACCOUNTS||self.bindings.contains_key(&s.id){return Err(bad("P10B authenticated capacity"));}
        let source=readiness::source_binding(s)?;
        s.training_opt_in=true;s.training_flights=Some(flight::Flights::default());self.bindings.insert(s.id,source);Ok(())
    }
    pub(super) fn preparing(&self)->bool{self.preparing.is_some()}
    pub(super) fn owns_preparing(&self,session:u32)->bool{self.preparing.as_ref().is_some_and(|p|p.owns(session)
        ||self.closed_members.values().any(|m|m.origin.session()==session&&m.origin.room()==p.prepare().snapshot().room()))}
    pub(super) fn previously_retired(&self,session:u32)->bool{self.retired_closed.contains(&session)}
    pub(super) fn busy(&self)->bool{self.preparing.is_some()||self.ready.busy()}
    fn writer_idle(&self,external_idle:bool)->bool{external_idle&&!self.ready.query_running()}
    fn retained(&self)->BTreeMap<room::Account,receive::RetainedMember>{
        self.closed_members.iter().map(|(who,m)|(*who,m.origin.clone())).collect()
    }
    fn current_facts(&self,sessions:&[Session],controller:&Controller)->io::Result<BTreeMap<room::Account,crate::training091::adapter::NativeFacts>>{
        let selected=self.ready.facts(sessions,controller)?;
        receive::current_facts_with_retained(sessions,controller,&selected,&self.bindings,&self.retained())
    }
    /// The immutable Preparing origins already own their selected data. Keep
    /// accepted cache entries only while the real room still uses that exact
    /// ReadyRef; departure/repeated402 cannot retain a lifetime Arc cache.
    fn prune_accepted(&mut self){
        let registry=self.controller.registry();
        self.ready.accepted.retain(|who,item|match registry.claim(*who){
            Some(room::Claim::Room(key))=>registry.room(key).is_some_and(|r|r.members()
                .any(|m|m.account()==*who&&m.ready()==Some(item.selection.reference()))),
            _=>false,
        });
    }
    fn publication(&self,sessions:&mut Vec<Session>,controller:&Controller,batch:&Batch)->io::Result<()>{
        let facts=self.current_facts(sessions,controller)?;
        receive::stage_batch(sessions,controller,batch,&self.bindings,&facts,None,None)?;
        for s in sessions.iter_mut(){s.drain_outbox()?;}Ok(())
    }
    pub(super) fn receive(&mut self,table:&mut Table,session:u32,frame:&Frame,world:&World,now:Instant,logical_ms:u64)->io::Result<bool>{
        let mut staged=table.sessions.clone();let mut controller=self.controller.clone();
        let facts=self.ready.facts(&staged,&controller)?;
        let available=self.active.is_none()&&self.preparing.is_none()&&world.started.is_none()&&world.actors.is_empty();
        let result=receive::receive_room_frame_with_retained(&mut staged,&mut controller,session,frame,world,&self.bindings,&facts,now,logical_ms,available,&self.retained())?;
        self.ready.can_enqueue(&result.ready)?;
        let mut deferred=self.deferred.clone();
        for next in &result.deferred_reads{
            deferred.retain(|old|old.call.channel.session!=next.call.channel.session||old.context.kind()!=next.context.kind());
            deferred.push(next.clone());
        }
        if deferred.len()>2*room::MAX_ACCOUNTS||result.prepare.len()>1{return Err(bad("P10B retained descriptors bound"));}
        let mut preparing=self.preparing.clone();
        if let Some(task)=result.prepare.first(){
            if !available{return Err(bad("P10B competing preparation"));}
            let mut origins=BTreeMap::new();
            for member in task.snapshot().members(){
                let item=self.ready.accepted.get(&member.account()).ok_or_else(||bad("P10B launch missing accepted readonly selection"))?;
                if item.selection.mode()!=self.mode{return Err(bad("P10B Preparing selected contract changed"));}
                let s=staged.iter().find(|s|s.id==item.selection.session()).ok_or_else(||bad("P10B launch Session retired"))?;
                origins.insert(member.account(),launch::LaunchOrigin::capture(s,&controller,item.task.clone(),item.selection.clone())?);
            }
            let mut shadow=Table{sessions:staged,retirement:RetirementWindow::default(),capacity:table.capacity};
            preparing=Some(prepare::Preparing::begin(task.clone(),room::BattleKey(world.id),origins,&controller,&mut shadow)?);staged=shadow.sessions;
        }
        if result.events.iter().any(|e|matches!(e,room::Event::AbortRequested{..})){if let Some(p)=&mut preparing{p.abort();}}
        // All fallible staging precedes these assignments; worker dispatch later.
        table.sessions=staged;self.controller=controller;self.preparing=preparing;self.deferred=deferred;
        self.ready.enqueue(result.ready)?;
        self.prune_accepted();
        for message in result.diagnostics{println!("{message}");}
        for refusal in result.refusals{println!("P10B_ROOM_REFUSED session={} reason={:?}",refusal.call.channel.session,refusal.refusal);}
        Ok(result.close)
    }
    fn flush_reads(&mut self,table:&mut Table,logical_ms:u64)->io::Result<()>{
        // One transaction for the complete retained-read batch. A late failure
        // cannot leave the first stream sent while retaining its descriptor.
        let mut sessions=table.sessions.clone();let mut controller=self.controller.clone();
        let mut keep=Vec::new();
        for deferred in &self.deferred{
            let Some(s)=sessions.iter().find(|s|s.id==deferred.call.channel.session)else{continue;};
            if !s.training_account_ready(){continue;}
            let(call,_,_)=receive::bound_call(s,&self.bindings)?;
            if call!=deferred.call{continue;}
            let read=match deferred.read{
                flight::ReadRevision::Listing(_)=>flight::ReadRevision::Listing(controller.read_revision()),
                flight::ReadRevision::Preview{room,revision:_}=>{let Some(r)=controller.registry().room(room)else{continue;};flight::ReadRevision::Preview{room,revision:r.revision()}},
            };
            if read!=deferred.read{println!("P10B_DEFERRED_READ_STALE session={} kind={:?} response_published=false",s.id,deferred.context.kind());continue;}
            if s.training_flights.as_ref().is_some_and(|f|f.busy(deferred.context.kind())){keep.push(deferred.clone());continue;}
            let facts=self.current_facts(&sessions,&controller)?;
            let batch=controller.apply(call,deferred.request.clone(),&facts,logical_ms).map_err(|_|bad("P10B deferred query refused"))?;
            let at=sessions.iter().find(|s|s.id==call.channel.session).ok_or_else(||bad("P10B deferred recipient missing"))?.outbox.len();
            receive::stage_batch(&mut sessions,&controller,&batch,&self.bindings,&facts,Some((call.channel.session,at)),Some(&deferred.context))?;
        }
        for s in &mut sessions{s.drain_outbox()?;}
        table.sessions=sessions;self.controller=controller;self.deferred=keep;Ok(())
    }
    pub(super) fn poll(&mut self,table:&mut Table,world:&mut World,runtime:&mut Option<IntegratedRuntime>,template:&BattleTemplate,
        dispatcher:&mut profile13_dispatch::Dispatcher,config:Arc<crate::identity091::Config>,now:Instant,logical_ms:u64,external_idle:bool)->io::Result<bool>{
        if super::super::p10b_writer_mode::Mode::config(&config)?!=self.mode{
            return Err(bad("P10B Host/Config spending mode changed"));}
        // Readonly publication failure retains its completed descriptor but is
        // not an outstanding SQLite worker. It cannot starve compensation.
        if let Err(error)=self.ready.poll(&mut table.sessions,&mut self.controller,logical_ms){
            println!("P10B_READY_PUBLICATION_RETRY error={error} completed_descriptor_retained=true service_alive=true");
        }
        if self.preparing.is_none(){self.flush_reads(table,logical_ms)?;}
        while let Some(reference)=dispatcher.take_training_finished(){
            let active=self.active.as_mut().ok_or_else(||bad("P10B Finished without committed launch"))?;
            if !active.finished.contains(&reference){if active.finished.len()>=active.selected.len(){return Err(bad("P10B Finished bound"));}active.finished.push(reference);}
        }
        if let Some(active)=self.active.as_ref().filter(|a|a.finished.len()==a.selected.len()){
            let mut controller=self.controller.clone();let mut sessions=table.sessions.clone();
            let batch=controller.finish_battle(active.battle,active.finished.clone(),logical_ms).map_err(|_|bad("P10B actual Finished claim release refused"))?;
            self.publication(&mut sessions,&controller,&batch)?;
            table.sessions=sessions;self.controller=controller;self.active=None;
            self.prune_accepted();
        }
        // Finish polling/publication of an already running readonly query, but
        // queued new queries cannot starve durable reserve/compensate work.
        if self.preparing.is_none(){
            self.ready.start(&mut table.sessions,&mut self.controller,config.clone(),external_idle&&!self.driver.job_active())?;
        }
        let mut committed=false;
        let writer_idle=self.writer_idle(external_idle);
        if let Some(p)=&mut self.preparing{
            let report=self.driver.poll(p,table,config,now,writer_idle);
            if let Some(error)=report.error{println!("P10B_PREPARING_RETRY error={error} immutable_task_retained=true");}
            match report.progress{
                prepare::Progress::AllReserved=>{
                    let staged=match launch::stage_launch(table,&self.controller,world,runtime,template,p.saga(),p.held(),p.origins(),now,logical_ms){
                        Ok(staged)=>staged,
                        Err(error)=>{
                            // No launch state was committed. Even queue pressure
                            // takes the explicit safe path: durably compensate
                            // ALL actual reserves, then publish held411 failure.
                            p.abort();
                            return Err(io::Error::new(error.kind(),format!("P10B launch staging refused; durable compensation retained: {error}")));
                        },
                    };
                    if let Err(error)=dispatcher.begin_training_finished_battle(p.saga().battle()){
                        p.abort();
                        return Err(io::Error::new(error.kind(),format!("P10B Finished scope refused before launch commit; durable compensation retained: {error}")));
                    }
                    // Both observer staging and launch staging precede the
                    // infallible same-loop swaps. The Manager borrow cannot be
                    // replaced between stage_install and commit_install.
                    let late=dispatcher.late.as_mut();
                    let late_install=match(late.as_deref(),staged.late_capture()){
                        (Some(manager),Ok(capture))=>match manager.stage_install(capture.clone()){
                            Ok(install)=>Some(install),
                            Err(_)=>{println!("P08C_TRAINING_LATE_RESULTS_UNSUPPORTED battle={} reason=observer_install_refused authority_unchanged=true",world.id);None}
                        },
                        _=>{println!("P08C_TRAINING_LATE_RESULTS_UNSUPPORTED battle={} reason=observer_or_roster_unavailable authority_unchanged=true",world.id);None}
                    };
                    let event=staged.commit(table,&mut self.controller,world,runtime);
                    if let(Some(manager),Some(install))=(late,late_install){manager.commit_install(install);}
                    self.preparing=None;self.driver=prepare::Driver::default();
                    self.active=Some(Active{battle:event.battle,selected:event.awaiting_handoff,finished:Vec::new(),committed_at:now});
                    self.prune_accepted();
                    committed=true;println!("P10B_LAUNCH_COMMITTED battle={} actors={} receipt_scope={:?} stage=Account",world.id,world.expected_actors(),self.mode);
                },
                prepare::Progress::AllReleased=>{
                    let old_battle=world.id;
                    let reset=CompensatedReset::stage(world,runtime,template,p.saga().battle(),now)?;
                    let mut stage=p.stage_abort(&self.driver,table,&self.controller,logical_ms)?;
                    let facts=self.ready.facts(&stage.sessions,&stage.controller)?;
                    receive::stage_batch(&mut stage.sessions,&stage.controller,&stage.batch,&self.bindings,&facts,None,None)?;
                    for s in &mut stage.sessions{s.drain_outbox()?;}
                    // Every actual reserve is released and abort publication is
                    // fully staged. No fallible operation follows this hook.
                    if let Some(late)=dispatcher.late.as_mut(){late.before_reset(world,"training_preparing_all_released");}
                    table.sessions=stage.sessions;self.controller=stage.controller;
                    reset.commit(world,runtime);self.preparing=None;self.driver=prepare::Driver::default();
                    self.prune_accepted();
                    // Existing caller resets all four publication cursors on
                    // true. This is a world replacement, never a launch claim.
                    committed=true;
                    println!("SHARED_BATTLE_RESET previous={old_battle} battle={} workers_revoked=true actors=0 trace_events=0 scene_version=0 service_alive=true",world.id);
                    println!("P10B_PREPARING_ABORTED all_reserves_released=true service_alive=true");
                },_=>{},
            }
        }Ok(committed)
    }
    pub(super) fn can_start(&self,table:&Table,world:&World,now:Instant)->io::Result<bool>{
        let Some(active)=&self.active else{return Ok(false);};
        if active.battle.0!=world.id||world.started.is_some(){return Ok(false);}
        launch::ready_to_start(table,world,&active.selected,now)
    }
    /// Call BEFORE ordinary retirement/advance for selected close and on each
    /// poll with closing_sid=None. Caller invokes the existing battle-failure
    /// boundary for every actual owned actor; this is NOT a pristine Saga cancel.
    /// Keep Active and its Finished receipts until all durable claims settle,
    /// even after that boundary replaces World with the next pristine battle.
    pub(super) fn prestart_failure(&self,world:&World,closing_sid:Option<u32>,now:Instant)->Option<io::Error>{
        let active=self.active.as_ref()?;
        if world.id!=active.battle.0||world.started.is_some(){return None;}
        let reason=if closing_sid.is_some_and(|id|active.selected.contains(&id)){
            Some("selected Session closed after launch commit before World start")
        }else if world.expected_actors()!=active.selected.len()||world.actors.len()!=active.selected.len()
            ||active.selected.iter().enumerate().any(|(slot,id)|world.actors.get(slot).is_none_or(|a|a.session!=Some(*id))){
            Some("committed launch lost its exact actor set before World start")
        }else if now.saturating_duration_since(active.committed_at)>=HANDOFF_TIMEOUT{
            Some("committed launch Account handoff exceeded 60 seconds")
        }else{None};
        reason.map(|reason|io::Error::new(io::ErrorKind::InvalidData,format!("P10B prestart failure policy={HANDOFF_POLICY}: {reason}")))
    }
    /// Retire Controller first while the actual Account is still present.
    /// Preparing participants remain guarded/inactive in Table until compensation.
    pub(super) fn closing(&mut self,table:&mut Table,session:u32,now:Instant,logical_ms:u64)->io::Result<bool>{
        let mut sessions=table.sessions.clone();let mut controller=self.controller.clone();
        let s=sessions.iter().find(|s|s.id==session).ok_or_else(||bad("P10B closing Session missing"))?;
        let owner=s.identity.as_ref().ok_or_else(||bad("P10B closing owner missing"))?;
        let lease=room::AuthLease{account:readiness::account(&owner.account_id)?,generation:u64::from(s.id)};
        let preparing_room=self.preparing.as_ref().map(|p|p.prepare().snapshot().room());
        let membership=preparing_room.and_then(|key|controller.registry().member_context(key,lease.account)
            .filter(|(current,_)|*current==lease).map(|(_,generation)|(key,generation)));
        let held=membership.is_some();
        // Abort intent is safe and immediate even if publication/fact capture
        // below fails. It neither releases a claim nor changes an actor/receipt.
        if held{self.preparing.as_mut().ok_or_else(||bad("P10B Preparing disappeared"))?.abort();}
        let mut closed=self.closed_members.clone();
        if let Some((key,membership))=membership{
            if let Some(old)=closed.get(&lease.account){
                if old.origin.session()!=session||old.origin.room()!=key||old.origin.membership()!=membership
                    ||old.origin.call().caller!=lease||old.origin.call().channel.generation!=s.training_account_generation(){
                    return Err(bad("P10B held room member incarnation changed"));
                }
            }else{
                if closed.len()>=room::MAX_ACCOUNTS{return Err(bad("P10B held room metadata bound"));}
                let selected=self.preparing.as_ref().and_then(|p|p.origins().get(&lease.account))
                    .map(|origin|receive::RetainedReady{task:origin.ready_task().clone(),reference:origin.selection().reference().clone()});
                let facts=self.current_facts(&sessions,&controller)?;
                let fact=facts.get(&lease.account).ok_or_else(||bad("P10B closing trusted member facts missing"))?;
                let origin=receive::RetainedMember::capture(s,&controller,&self.bindings,fact,selected)?;
                closed.insert(lease.account,ClosedMember{origin,display_task:self.ready.accepted.get(&lease.account).map(|a|a.task.clone())});
            }
        }
        if let Some(channel)=controller.recipient_channel(lease,owner.database_id){
            let facts=self.current_facts(&sessions,&controller)?;
            let batch=controller.retire(lease,channel,&facts,logical_ms).map_err(|_|bad("P10B native room retire refused"))?;
            // Only the local clone becomes inactive before rebuilding facts.
            // Retained metadata is display-only; actual publication still
            // requires a live current Account and cannot target this peer.
            if held{let target=sessions.iter_mut().find(|s|s.id==session).ok_or_else(||bad("P10B closing member vanished"))?;
                target.active=false;target.base_peer=None;
            }
            let selected=self.ready.facts(&sessions,&controller)?;
            let facts=receive::current_facts_with_retained(&sessions,&controller,&selected,&self.bindings,&closed.iter().map(|(who,m)|(*who,m.origin.clone())).collect())?;
            receive::stage_batch(&mut sessions,&controller,&batch,&self.bindings,&facts,None,None)?;
            for s in &mut sessions{s.drain_outbox()?;}
        }
        if held&&!self.retired_closed.contains(&session)&&self.retired_closed.len()>=room::MAX_ACCOUNTS{
            return Err(bad("P10B retained closed Session bound"));
        }
        if held{let original=table.sessions.iter().find(|s|s.id==session).ok_or_else(||bad("P10B held Session missing"))?;
            if original.active{table.retirement.retire(original.login_attempt.ok_or_else(||bad("P10B held login attempt missing"))?,original.base_peer,now).map_err(|_|bad("P10B held retirement bound"))?;}
            else if !self.retired_closed.contains(&session){return Err(bad("P10B inactive held Session lacks committed retirement"));}
            let s=sessions.iter_mut().find(|s|s.id==session).ok_or_else(||bad("P10B held Session missing"))?;s.active=false;s.base_peer=None;
        }
        table.sessions=sessions;self.controller=controller;self.closed_members=closed;
        // Retained only after the held inactive Session and real retirement
        // have committed. The caller must not insert that same LoginAttempt
        // into RetirementWindow again after compensation releases its guard.
        if held{self.retired_closed.insert(session);}
        self.deferred.retain(|d|d.call.channel.session!=session);self.prune_accepted();Ok(held)
    }
    pub(super) fn forget_session(&mut self,session:u32){
        self.bindings.remove(&session);self.retired_closed.remove(&session);self.closed_members.retain(|_,m|m.origin.session()!=session);
    }
}

#[cfg(test)]#[path="p10b_host_tests.rs"]mod tests;
#[cfg(test)]#[path="p10b_host_bench_tests.rs"]mod bench_tests;

#[cfg(test)]#[path="p10b_compensated_reset_tests.rs"]mod compensated_reset_tests;

#[cfg(test)]#[path="p10b_loss_composition_tests.rs"]mod loss_composition_tests;
