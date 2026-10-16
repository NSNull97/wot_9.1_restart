//! Atomic launch preparation only; child of shared::server. No external jobs,
//! filesystem reads, World.start, native Avatar reset or Jolt launch here.
use super::*;
use std::collections::{BTreeMap,BTreeSet};
use crate::training091::{controller::{Controller,ReadyTask,Batch},current_room::Channel,domain as room};
use crate::gateway091::shared::{p10b_writer as saga,profile13_session as persistence};
use crate::profile13_v2091 as writer;

fn bad(message:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,message)}
fn source_hex(bytes:&[u8;32])->String{bytes.iter().map(|b|format!("{b:02x}")).collect()}
fn account(text:&str)->io::Result<room::Account>{
    if text.len()!=36||[8,13,18,23].into_iter().any(|i|text.as_bytes()[i]!=b'-'){return Err(bad("launch account UUID"));}
    let compact=text.bytes().filter(|b|*b!=b'-').collect::<Vec<_>>();if compact.len()!=32{return Err(bad("launch account shape"));}
    let mut bytes=[0;16];for(i,pair)in compact.chunks_exact(2).enumerate(){let nibble=|b|match b{b'0'..=b'9'=>Ok(b-b'0'),b'a'..=b'f'=>Ok(b-b'a'+10),_=>Err(bad("launch account alphabet"))};bytes[i]=16*nibble(pair[0])?+nibble(pair[1])?;}
    if bytes==[0;16]{return Err(bad("launch zero account"));}Ok(room::Account(bytes))
}

/// Captured at successful actual Ready completion, before later Prepare starts.
/// No native/client epoch is invented. Origin carries the real ReadyTask's
/// authenticated channel, membership generation and trusted source stamp.
#[derive(Clone)]
pub(super) struct LaunchOrigin{task:ReadyTask,selection:saga::ReadySelection}
impl LaunchOrigin{
    pub(super) fn capture(s:&Session,controller:&Controller,task:ReadyTask,selection:saga::ReadySelection)->io::Result<Self>{
        let origin=Self{task,selection};origin.validate_session(s,controller,false)?;Ok(origin)
    }
    pub(super) fn ready_task(&self)->&ReadyTask{&self.task}
    pub(super) fn selection(&self)->&saga::ReadySelection{&self.selection}
    pub(super) fn source_stamp(&self)->&crate::training091::selection::Stamp{self.selection.source_stamp()}
    pub(super) fn matches_session(&self,s:&Session,controller:&Controller,preparing:bool)->io::Result<()>{self.validate_session(s,controller,preparing)}
    fn validate_session(&self,s:&Session,controller:&Controller,preparing:bool)->io::Result<()>{
        let owner=s.identity.as_ref().ok_or_else(||bad("launch unauthenticated Session"))?;
        let c=s.shared.as_ref().ok_or_else(||bad("launch missing Client"))?;
        let p=c.profile13.as_ref().ok_or_else(||bad("launch missing owned state"))?;
        let ammo=s.ammo_service.as_ref().ok_or_else(||bad("launch missing ammunition state"))?;
        let stamp=self.selection.source_stamp();stamp.validate()?;
        let channel=Channel{session:s.id,generation:s.training_account_generation()};
        if !s.training_account_ready()||c.phase!=Phase::Account||s.arena_base||c.join_requested||c.queue_announced
            ||p.in_flight!=preparing||p.has_reservation()||p.has_pending_return()||!ammo.idle()
            ||owner.account_id!=self.selection.owner().account_id||owner.database_id!=self.selection.owner().database_id||owner.name!=self.selection.owner().name
            ||s.id!=self.selection.session()||self.task.channel()!=channel
            ||self.task.caller().account!=account(&owner.account_id)?||self.task.caller().generation!=u64::from(s.id)
            ||!controller.is_current_recipient(self.task.caller(),channel,owner.database_id)
            ||self.task.expected_revision()!=self.selection.reference().revision()
            ||p.revision!=u64::from(self.task.expected_revision())||ammo.revision()!=p.revision
            ||self.task.profile().revision!=self.task.expected_revision()
            ||source_hex(&self.task.profile().source_binding)!=stamp.owner_source_sha256
            ||self.task.native_inventory()!=self.selection.frozen().native_inventory_id
            ||source_hex(&s.hangar.as_ref().ok_or_else(||bad("launch missing Account cache"))?.state_sha256())!=stamp.native_state_sha256
            ||s.hangar.as_ref().and_then(|f|f.p04m_binding()).is_none_or(|b|!b.matches(&owner.account_id,owner.database_id,p.revision)){
            return Err(bad("launch changed authenticated channel/source/readiness"));
        }
        Ok(())
    }
}

/// Immutable admitted worker outcome retained only after Saga.complete accepts
/// it. No ordinary deliver_v2 is run while individual reservations accumulate.
#[derive(Clone)]
pub(super) struct HeldFresh{
    task:saga::Task,reply:writer::Reply,owner:Arc<crate::identity091::Profile>,
    fixtures:Arc<crate::hangar091::Fixtures>,binding:crate::ammo_service091::Metadata,
}
impl HeldFresh{
    pub(super) fn capture(task:&saga::Task,c:&persistence::CompletionV2)->io::Result<Self>{
        let f=c.fresh.as_ref().ok_or_else(||bad("launch admitted projection missing"))?;
        let row=c.reply.reservation.as_ref().ok_or_else(||bad("launch admitted receipt missing"))?;
        let writer::Request::Admit{battle,native_inventory_id}=task.request() else{return Err(bad("launch held operation"));};
        if c.refresh_error.is_some()||c.reply.status!=writer::Status::Admitted||c.session!=task.session()
            ||c.context!=*task.context()||c.request!=*task.request()
            ||c.old_owner.account_id!=task.owner().account_id||c.old_owner.database_id!=task.owner().database_id
            ||f.owner.account_id!=task.owner().account_id||f.owner.database_id!=task.owner().database_id
            ||f.binding.revision!=c.reply.revision||f.binding.wire_revision!=1
            ||f.fixtures.p04m_binding().is_none_or(|b|!b.matches(&f.owner.account_id,f.owner.database_id,f.binding.revision))
            ||c.reply.revision!=task.context().expected_revision+1||row.status!=writer::ReservationStatus::Active||row.result.is_some()
            ||row.run_id!=task.context().run_id||row.battle!=*battle||row.reservation_id!=task.context().command_key
            ||row.frozen.native_inventory_id!=*native_inventory_id{return Err(bad("launch held Task/completion/source binding"));}
        row.frozen.validate_owned(&task.owner().account_id)?;
        Ok(Self{task:task.clone(),reply:c.reply.clone(),owner:f.owner.clone(),fixtures:f.fixtures.clone(),binding:f.binding})
    }
    pub(super) fn session(&self)->u32{self.task.session()}
    pub(super) fn receipt(&self)->&writer::Reservation{self.reply.reservation.as_ref().expect("private capture retains receipt")}
    pub(super) fn owner(&self)->&Arc<crate::identity091::Profile>{&self.owner}
    pub(super) fn fixtures(&self)->&Arc<crate::hangar091::Fixtures>{&self.fixtures}
    pub(super) fn binding(&self)->crate::ammo_service091::Metadata{self.binding}
}

pub(super) struct CommitEvent{pub(super) battle:room::BattleKey,pub(super) awaiting_handoff:Vec<u32>}
pub(super) struct LaunchStage{
    sessions:Vec<Session>,controller:Controller,world:World,runtime:Option<IntegratedRuntime>,event:CommitEvent,
}
impl LaunchStage{
    /// Parent removes its owning Saga/held outcomes in this same infallible
    /// outer commit. A retained clone is NEVER an active-battle abort handle.
    pub(super) fn commit(self,table:&mut Table,controller:&mut Controller,world:&mut World,runtime:&mut Option<IntegratedRuntime>)->CommitEvent{
        table.sessions=self.sessions;*controller=self.controller;*world=self.world;*runtime=self.runtime;self.event
    }
}

/// Prepare an all-or-nothing launch from settled actual reservations. The
/// original owning Saga remains available for compensation on ANY failure.
pub(super) fn stage_launch(table:&Table,controller:&Controller,placeholder:&World,current_runtime:&Option<IntegratedRuntime>,
    template:&BattleTemplate,saga:&saga::Saga,held:&[HeldFresh],origins:&BTreeMap<room::Account,LaunchOrigin>,now:Instant,logical_ms:u64)->io::Result<LaunchStage>{
    let reserved=saga.clone().into_reserved()?;
    let snapshot=&reserved.snapshot;let battle=reserved.battle;let n=snapshot.members().len();
    if !(2..=6).contains(&n)||held.len()!=n||origins.len()!=n||placeholder.started.is_some()||!placeholder.actors.is_empty()
        ||placeholder.id!=battle.0||placeholder.map!=MapId::Prohorovka||snapshot.settings().map!=room::QualifiedMap::Prohorovka
        ||table.capacity< n||template.world.map!=MapId::Prohorovka||template.world.expected_actors()!=6
        ||current_runtime.as_ref().is_some_and(|r|r.started||r.staged.is_some()||r.workers.iter().any(Option::is_some)||r.blocked()){
        return Err(bad("launch requires pristine map4 world and settled 2..6 snapshot"));
    }
    let current_room=controller.registry().room(snapshot.room()).ok_or_else(||bad("launch room vanished"))?;
    if current_room.abort_requested()||current_room.preparing()!=Some(snapshot){return Err(bad("launch Prepare changed/aborted"));}
    // Preserve World::fresh_battle's strict same-id guard. Validation uses an
    // alternate ID, while the accepted template clone may retain this battle ID.
    let validation_id=if template.world.id==1{2}else{1};
    let pristine=template.world.fresh_battle(validation_id,now)?;
    let mut world=if template.world.id==battle.0{template.world.clone()}else{template.world.fresh_battle(battle.0,now)?};
    drop(pristine);
    if !world.mixed_ammo()||world.extended_lab(){return Err(bad("launch requires owned v2 template"));}
    world.set_expected_actors(n)?;
    let mut rules=super::super::lifecycle::Rules::prohorovka();rules.battle_ms=u64::from(snapshot.settings().seconds).checked_mul(1000).ok_or_else(||bad("launch duration overflow"))?;
    world.lifecycle=Some(super::super::lifecycle::State::new(rules)?);
    let teams=snapshot.members().iter().map(|m|match m.side(){room::Side::One=>1,room::Side::Two=>2}).collect::<Vec<_>>();
    world.set_team_plan(super::super::p10b_team_plan::TeamPlan::new(&teams)?)?;
    let mut sessions=table.sessions.clone();let mut ids=BTreeSet::new();let mut keys=BTreeSet::new();let mut awaiting=Vec::new();
    for(slot,member)in snapshot.members().iter().enumerate(){
        let binding=reserved.bindings.get(slot).ok_or_else(||bad("launch missing settled binding"))?;
        let origin=origins.get(&member.account()).ok_or_else(||bad("launch missing Ready origin"))?;
        if binding.ready!=*member.ready()||binding.ready!=*origin.selection.reference()||binding.source_stamp!=*origin.selection.source_stamp()
            ||binding.reservation.frozen!=*origin.selection.frozen()||binding.session!=origin.selection.session()
            ||origin.task.room()!=snapshot.room()||controller.registry().member_context(snapshot.room(),member.account())!=Some((origin.task.caller(),origin.task.membership()))
            ||!ids.insert(binding.session)||!keys.insert(binding.reservation.reservation_id.clone()){
            return Err(bad("launch frozen order/source/membership mismatch"));
        }
        if sessions.iter().any(|s|s.id!=binding.session&&s.identity.as_ref().is_some_and(|p|p.account_id==binding.owner.account_id)){
            return Err(bad("launch selected account appears on another Session"));
        }
        let mut matches=sessions.iter_mut().filter(|s|s.id==binding.session);
        let s=matches.next().ok_or_else(||bad("launch selected Session missing"))?;
        if matches.next().is_some(){return Err(bad("launch duplicate Session id"));}
        origin.validate_session(s,controller,true)?;
        let mut outcomes=held.iter().filter(|f|f.session()==binding.session);
        let f=outcomes.next().ok_or_else(||bad("launch selected Fresh missing"))?;
        if outcomes.next().is_some()||f.receipt()!=&binding.reservation||f.binding.revision!=binding.revision
            ||f.task.context().expected_revision!=u64::from(binding.ready.revision())
            ||f.owner.account_id!=binding.owner.account_id||f.owner.database_id!=binding.owner.database_id
            ||f.owner.name!=member.name(){return Err(bad("launch held projection not settled reservation"));}
        // Same native Account remains alive: advance durable revision only.
        let ammo=s.ammo_service.as_mut().ok_or_else(||bad("launch ammo state missing"))?;
        ammo.refresh_revision(f.binding.revision)?;ammo.replace_pool(f.fixtures.p04m_binding().cloned())?;
        s.identity=Some(f.owner.clone());s.hangar=Some(f.fixtures.clone());
        let c=s.shared.as_mut().ok_or_else(||bad("launch Client missing"))?;
        let p=c.profile13.as_mut().ok_or_else(||bad("launch owned state missing"))?;
        if p.run_id!=binding.reservation.run_id{return Err(bad("launch writer run changed"));}
        p.reservation_v2=Some(binding.reservation.clone());p.selection=None;p.revision=binding.revision;p.in_flight=false;
        c.reset_for_battle(slot);c.join_requested=true;c.queue_announced=false;c.hangar_since=Some(now);
        let actual=world.attach_owned_v2(model::Identity{account:f.owner.account_id.clone(),database:f.owner.database_id,name:f.owner.name.clone()},s.id,&binding.reservation.frozen)?;
        if actual!=slot{return Err(bad("launch actor order changed"));}awaiting.push(s.id);
    }
    for s in &mut sessions{if ids.contains(&s.id){s.shared.as_mut().ok_or_else(||bad("launch Client vanished"))?.view=Some(world.clone());}}
    let mut next_controller=controller.clone();
    let batch=next_controller.commit_launch(snapshot.room(),snapshot.ticket(),battle,reserved.references,logical_ms)
        .map_err(|_|bad("launch Controller claim/publication commit refused"))?;
    stage_publication(&mut sessions,&next_controller,&batch)?;
    let runtime=template.runtime(world.map)?;
    Ok(LaunchStage{sessions,controller:next_controller,world,runtime,event:CommitEvent{battle,awaiting_handoff:awaiting}})
}

fn stage_publication(sessions:&mut[Session],controller:&Controller,batch:&Batch)->io::Result<()>{
    if !batch.ready.is_empty()||!batch.prepare.is_empty(){return Err(bad("launch publication issued new jobs"));}
    for(owner,bodies)in &batch.bodies{
        let mut candidates=sessions.iter_mut().filter(|s|s.active&&s.identity.as_ref().is_some_and(|p|account(&p.account_id).ok()==Some(*owner)));
        let s=candidates.next().ok_or_else(||bad("launch publication recipient missing"))?;
        if candidates.next().is_some(){return Err(bad("launch publication recipient duplicate"));}
        let identity=s.identity.as_ref().ok_or_else(||bad("launch publication authenticated owner missing"))?;
        let lease=room::AuthLease{account:*owner,generation:u64::from(s.id)};
        let channel=Channel{session:s.id,generation:s.training_account_generation()};
        if !s.training_account_ready()||!controller.is_current_recipient(lease,channel,identity.database_id){
            return Err(bad("launch publication recipient channel changed"));
        }
        let bytes=s.outbox.iter().chain(bodies).try_fold(0usize,|sum,b|sum.checked_add(b.len())).ok_or_else(||bad("launch outbox overflow"))?;
        if s.outbox.len()+bodies.len()>crate::training091::wire::MAX_OUTBOX||bytes>crate::training091::wire::MAX_OUTBOX_BYTES
            ||bodies.iter().any(|b|b.is_empty()||b.len()>512){return Err(bad("launch publication budget"));}
        s.outbox.extend(bodies.iter().cloned());s.drain_outbox()?;
    }Ok(())
}

/// Actual ordered final411 must leave TX/outbox before World.start and existing
/// shared_start. Unrelated hangars/bench are deliberately excluded from count.
pub(super) fn ready_to_start(table:&Table,world:&World,selected:&[u32],now:Instant)->io::Result<bool>{
    if world.started.is_some()||selected.len()!=world.expected_actors()||world.actors.len()!=selected.len()
        ||world.team_plan().is_none(){return Err(bad("launch handoff World mismatch"));}
    let mut unique=BTreeSet::new();let mut ready=true;
    for(slot,id)in selected.iter().enumerate(){
        if !unique.insert(*id)||world.actors[slot].session!=Some(*id){return Err(bad("launch handoff frozen order mismatch"));}
        let mut matches=table.sessions.iter().filter(|s|s.id==*id);let s=matches.next().ok_or_else(||bad("launch handoff Session missing"))?;
        if matches.next().is_some(){return Err(bad("launch handoff duplicate Session"));}
        ready&=entry_ready(s,now);
    }Ok(ready)
}

#[cfg(test)]#[path="p10b_launch_host_tests.rs"]mod tests;
