//! Explicit room writer discrimination. V2 and loss4 authorities never cast.
//! Common base loadout access is READONLY metadata; attach/install stay typed.
use std::{io,sync::Arc};
use crate::{identity091,profile13_v2091 as v2,profile13_loss091 as loss};
use crate::battle091::profile13::Context;
use crate::training091::{selection,selection_loss,domain as room};
use super::{p10b_writer as old,p10b_writer_loss as new,profile13_session as service,model::{World,Identity}};
fn bad(s:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,s)}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub(super) enum Mode{MixedV2,LossV4}
impl Default for Mode{fn default()->Self{Self::MixedV2}}
impl Mode{
    pub(super) fn checked(training:bool,loss:bool)->io::Result<Self>{if !training{return Err(bad("room writer requires training_rooms"));}
        Ok(if loss{Self::LossV4}else{Self::MixedV2})}
    pub(super) fn config(c:&identity091::Config)->io::Result<Self>{Self::checked(c.training_rooms,c.p06t_ammo_rack_detonation)}
}
#[derive(Clone,Debug,PartialEq,Eq)]pub(super) enum Stamp{V2(selection::Stamp),Loss(selection_loss::Stamp)}
impl Stamp{pub(super) fn base(&self)->&selection::Stamp{match self{Self::V2(s)=>s,Self::Loss(s)=>&s.base}}}
#[derive(Clone)]pub(super) enum Selected{V2(selection::Selection),Loss(selection_loss::Selection)}
impl From<selection::Selection> for Selected{fn from(s:selection::Selection)->Self{Self::V2(s)}}
impl From<selection_loss::Selection> for Selected{fn from(s:selection_loss::Selection)->Self{Self::Loss(s)}}
impl Selected{
    pub(super) fn mode(&self)->Mode{match self{Self::V2(_)=>Mode::MixedV2,Self::Loss(_)=>Mode::LossV4}}
    // Common origin fields only; no ownership constructor accepts this base.
    pub(super) fn request(&self)->&selection::Request{match self{Self::V2(s)=>s.request(),Self::Loss(s)=>&s.request().base}}
}
#[derive(Clone)]pub(super) enum ReadySelection{V2(old::ReadySelection),Loss(new::ReadySelection)}
impl ReadySelection{
    pub(super) fn from_selection<S:Into<Selected>>(owner:Arc<identity091::Profile>,session:u32,s:S)->io::Result<Self>{match s.into(){
        Selected::V2(s)=>old::ReadySelection::from_selection(owner,session,s).map(Self::V2),
        Selected::Loss(s)=>new::ReadySelection::from_selection(owner,session,s).map(Self::Loss)}}
    pub(super) fn mode(&self)->Mode{match self{Self::V2(_)=>Mode::MixedV2,Self::Loss(_)=>Mode::LossV4}}
    pub(super) fn owner(&self)->&Arc<identity091::Profile>{match self{Self::V2(s)=>s.owner(),Self::Loss(s)=>s.owner()}}
    pub(super) fn session(&self)->u32{match self{Self::V2(s)=>s.session(),Self::Loss(s)=>s.session()}}
    pub(super) fn run_id(&self)->&str{match self{Self::V2(s)=>s.run_id(),Self::Loss(s)=>s.run_id()}}
    pub(super) fn reference(&self)->&room::WriterReadyRef{match self{Self::V2(s)=>s.reference(),Self::Loss(s)=>s.reference()}}
    pub(super) fn source_stamp(&self)->Stamp{match self{Self::V2(s)=>Stamp::V2(s.source_stamp().clone()),Self::Loss(s)=>Stamp::Loss(s.source_stamp().clone())}}
    pub(super) fn loadout(&self)->&v2::Frozen{match self{Self::V2(s)=>s.frozen(),Self::Loss(s)=>&s.frozen().base}}
    #[cfg(test)]pub(super) fn with_launch_scheduler_seam_for_test(self,run:String,state:String)->Self{match self{
        Self::V2(s)=>Self::V2(s.with_launch_scheduler_seam_for_test(run,state)),Self::Loss(s)=>Self::Loss(s.with_launch_scheduler_seam_for_test(run,state))}}
    pub(super) fn matches_receipt(&self,r:&Reservation)->bool{match(self,r){(Self::V2(s),Reservation::V2(r))=>s.frozen()==&r.frozen,
        (Self::Loss(s),Reservation::Loss(r))=>s.frozen()==&r.frozen,_=>false}}
}
#[derive(Clone,Debug,PartialEq,Eq)]pub(super) enum Reservation{V2(v2::Reservation),Loss(loss::Reservation)}
impl Reservation{
    pub(super) fn mode(&self)->Mode{match self{Self::V2(_)=>Mode::MixedV2,Self::Loss(_)=>Mode::LossV4}}
    pub(super) fn id(&self)->&str{match self{Self::V2(r)=>&r.reservation_id,Self::Loss(r)=>&r.reservation_id}}
    pub(super) fn run_id(&self)->&str{match self{Self::V2(r)=>&r.run_id,Self::Loss(r)=>&r.run_id}}
    pub(super) fn battle(&self)->u64{match self{Self::V2(r)=>r.battle,Self::Loss(r)=>r.battle}}
    pub(super) fn loadout(&self)->&v2::Frozen{match self{Self::V2(r)=>&r.frozen,Self::Loss(r)=>&r.frozen.base}}
    pub(super) fn active(&self)->bool{match self{Self::V2(r)=>r.status==v2::ReservationStatus::Active&&r.result.is_none(),
        Self::Loss(r)=>r.status==loss::ReservationStatus::Active&&r.result.is_none()}}
    pub(super) fn late_admission(&self)->super::late_results_capture::Admission{match self{
        Self::V2(r)=>super::late_results_capture::Admission::Mixed(r.clone()),
        Self::Loss(r)=>super::late_results_capture::Admission::Loss(r.clone())}}
    pub(super) fn validate_owned(&self,owner:&str)->io::Result<()>{match self{Self::V2(r)=>r.frozen.validate_owned(owner),Self::Loss(r)=>r.frozen.validate_owned(owner)}}
    pub(super) fn install(&self,p:&mut service::State)->io::Result<()>{
        if p.run_id!=self.run_id()||p.has_reservation()||p.has_pending_return(){return Err(bad("room install existing reservation"));}
        match self{Self::V2(r)=>p.reservation_v2=Some(r.clone()),Self::Loss(r)=>p.reservation_loss=Some(r.clone())}Ok(())}
    pub(super) fn attach(&self,world:&mut World,who:Identity,session:u32)->io::Result<usize>{
        if world.ammo_detonation_enabled()!=(self.mode()==Mode::LossV4){return Err(bad("room receipt/template spending policy mismatch"));}
        match self{Self::V2(r)=>world.attach_owned_v2(who,session,&r.frozen),Self::Loss(r)=>world.attach_owned_loss(who,session,&r.frozen)}}
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub(super) enum Status{Ready,Admitted,Finished,Inspected,Rejected}
fn old_status(s:v2::Status)->Status{match s{v2::Status::Ready=>Status::Ready,v2::Status::Admitted=>Status::Admitted,v2::Status::Finished=>Status::Finished,v2::Status::Inspected=>Status::Inspected,v2::Status::Rejected=>Status::Rejected}}
fn new_status(s:loss::Status)->Status{match s{loss::Status::Ready=>Status::Ready,loss::Status::Admitted=>Status::Admitted,loss::Status::Finished=>Status::Finished,loss::Status::Inspected=>Status::Inspected,loss::Status::Rejected=>Status::Rejected}}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub(super) enum RequestRef<'a>{V2(&'a v2::Request),Loss(&'a loss::Request)}
impl<'a> RequestRef<'a>{
    pub(super) fn operation(&self)->&'static str{match self{Self::V2(r)=>r.operation(),Self::Loss(r)=>r.operation()}}
    #[cfg(test)]pub(super) fn v2(self)->&'a v2::Request{match self{Self::V2(r)=>r,Self::Loss(_)=>panic!("AUTHORED V2 regression must remain V2")}}
    pub(super) fn admit(&self)->Option<(u64,u32)>{match self{Self::V2(v2::Request::Admit{battle,native_inventory_id})|Self::Loss(loss::Request::Admit{battle,native_inventory_id})=>Some((*battle,*native_inventory_id)),_=>None}}
}
#[derive(Clone)]pub(super) enum Task{V2(old::Task),Loss(new::Task)}
impl Task{
    pub(super) fn mode(&self)->Mode{match self{Self::V2(_)=>Mode::MixedV2,Self::Loss(_)=>Mode::LossV4}}
    pub(super) fn session(&self)->u32{match self{Self::V2(t)=>t.session(),Self::Loss(t)=>t.session()}}
    pub(super) fn owner(&self)->&Arc<identity091::Profile>{match self{Self::V2(t)=>t.owner(),Self::Loss(t)=>t.owner()}}
    pub(super) fn context(&self)->&Context{match self{Self::V2(t)=>t.context(),Self::Loss(t)=>t.context()}}
    pub(super) fn request(&self)->RequestRef<'_>{match self{Self::V2(t)=>RequestRef::V2(t.request()),Self::Loss(t)=>RequestRef::Loss(t.request())}}
    pub(super) fn start(&self,c:Arc<identity091::Config>)->io::Result<Job>{if Mode::config(&c)?!=self.mode(){return Err(bad("room Task/Config contract changed"));}
        match self{Self::V2(t)=>t.start(c).map(Job::V2),Self::Loss(t)=>t.start(c).map(Job::Loss)}}
}
pub(super) enum Job{V2(service::JobV2),Loss(service::JobLoss)}
impl Job{pub(super) fn poll(&mut self)->Option<io::Result<Completion>>{match self{Self::V2(j)=>j.poll().map(|r|r.map(Completion::V2)),Self::Loss(j)=>j.poll().map(|r|r.map(Completion::Loss))}}}
pub(super) enum Completion{V2(service::CompletionV2),Loss(service::CompletionLoss)}
impl Completion{
    pub(super) fn mode(&self)->Mode{match self{Self::V2(_)=>Mode::MixedV2,Self::Loss(_)=>Mode::LossV4}}
    pub(super) fn session(&self)->u32{match self{Self::V2(c)=>c.session,Self::Loss(c)=>c.session}}
    pub(super) fn old_owner(&self)->&Arc<identity091::Profile>{match self{Self::V2(c)=>&c.old_owner,Self::Loss(c)=>&c.old_owner}}
    pub(super) fn context(&self)->&Context{match self{Self::V2(c)=>&c.context,Self::Loss(c)=>&c.context}}
    pub(super) fn request(&self)->RequestRef<'_>{match self{Self::V2(c)=>RequestRef::V2(&c.request),Self::Loss(c)=>RequestRef::Loss(&c.request)}}
    pub(super) fn status(&self)->Status{match self{Self::V2(c)=>old_status(c.reply.status),Self::Loss(c)=>new_status(c.reply.status)}}
    pub(super) fn revision(&self)->u64{match self{Self::V2(c)=>c.reply.revision,Self::Loss(c)=>c.reply.revision}}
    pub(super) fn reservation(&self)->Option<Reservation>{match self{Self::V2(c)=>c.reply.reservation.clone().map(Reservation::V2),Self::Loss(c)=>c.reply.reservation.clone().map(Reservation::Loss)}}
    pub(super) fn fresh(&self)->Option<&service::Fresh>{match self{Self::V2(c)=>c.fresh.as_ref(),Self::Loss(c)=>c.fresh.as_ref()}}
    pub(super) fn refresh_failed(&self)->bool{match self{Self::V2(c)=>c.refresh_error.is_some(),Self::Loss(c)=>c.refresh_error.is_some()}}
    pub(super) fn same_durable(&self,other:&Self)->bool{match(self,other){
        (Self::V2(a),Self::V2(b))=>a.context==b.context&&a.request==b.request&&a.reply.status==b.reply.status&&a.reply.revision==b.reply.revision
            &&a.reply.reservation==b.reply.reservation&&a.reply.legacy_reservation==b.reply.legacy_reservation,
        (Self::Loss(a),Self::Loss(b))=>a.context==b.context&&a.request==b.request&&a.reply.status==b.reply.status&&a.reply.revision==b.reply.revision&&a.reply.reservation==b.reply.reservation,_=>false}}
}
#[derive(Clone)]pub(super) enum Saga{V2(old::Saga),Loss(new::Saga)}
impl Saga{
    pub(super) fn new(snapshot:room::LaunchSnapshot,battle:room::BattleKey,selections:Vec<ReadySelection>)->io::Result<Self>{
        let mode=selections.first().ok_or_else(||bad("empty room roster"))?.mode();if selections.iter().any(|s|s.mode()!=mode){return Err(bad("mixed room spending contracts refused"));}
        match mode{Mode::MixedV2=>old::Saga::new(snapshot,battle,selections.into_iter().map(|s|if let ReadySelection::V2(s)=s{Ok(s)}else{Err(bad("room mode"))}).collect::<io::Result<Vec<_>>>()?).map(Self::V2),
            Mode::LossV4=>new::Saga::new(snapshot,battle,selections.into_iter().map(|s|if let ReadySelection::Loss(s)=s{Ok(s)}else{Err(bad("room mode"))}).collect::<io::Result<Vec<_>>>()?).map(Self::Loss)}}
    pub(super) fn mode(&self)->Mode{match self{Self::V2(_)=>Mode::MixedV2,Self::Loss(_)=>Mode::LossV4}}
    pub(super) fn snapshot(&self)->&room::LaunchSnapshot{match self{Self::V2(s)=>s.snapshot(),Self::Loss(s)=>s.snapshot()}}
    pub(super) fn battle(&self)->room::BattleKey{match self{Self::V2(s)=>s.battle(),Self::Loss(s)=>s.battle()}}
    pub(super) fn aborting(&self)->bool{match self{Self::V2(s)=>s.aborting(),Self::Loss(s)=>s.aborting()}}
    pub(super) fn abort(&mut self){match self{Self::V2(s)=>s.abort(),Self::Loss(s)=>s.abort()}}
    pub(super) fn retry(&self)->Option<Task>{match self{Self::V2(s)=>s.retry().map(Task::V2),Self::Loss(s)=>s.retry().map(Task::Loss)}}
    pub(super) fn next_admission_origin(&self)->Option<(u32,Arc<identity091::Profile>,u64)>{match self{Self::V2(s)=>s.next_admission_origin(),Self::Loss(s)=>s.next_admission_origin()}}
    pub(super) fn next_compensation_origin(&self)->Option<(u32,Arc<identity091::Profile>,u64)>{match self{Self::V2(s)=>s.next_compensation_origin(),Self::Loss(s)=>s.next_compensation_origin()}}
    pub(super) fn next_inspection_origin(&self)->Option<(u32,Arc<identity091::Profile>,u64)>{match self{Self::V2(s)=>s.next_inspection_origin(),Self::Loss(s)=>s.next_inspection_origin()}}
    pub(super) fn next_admit(&mut self,c:Context)->io::Result<Option<Task>>{match self{Self::V2(s)=>s.next_admit(c).map(|r|r.map(Task::V2)),Self::Loss(s)=>s.next_admit(c).map(|r|r.map(Task::Loss))}}
    pub(super) fn next_cancel(&mut self,c:Context)->io::Result<Option<Task>>{match self{Self::V2(s)=>s.next_cancel(c).map(|r|r.map(Task::V2)),Self::Loss(s)=>s.next_cancel(c).map(|r|r.map(Task::Loss))}}
    pub(super) fn next_inspect(&mut self,c:Context)->io::Result<Option<Task>>{match self{Self::V2(s)=>s.next_inspect(c).map(|r|r.map(Task::V2)),Self::Loss(s)=>s.next_inspect(c).map(|r|r.map(Task::Loss))}}
    pub(super) fn complete(&mut self,c:&Completion)->io::Result<()>{match(self,c){(Self::V2(s),Completion::V2(c))=>s.complete(c),(Self::Loss(s),Completion::Loss(c))=>s.complete(c),_=>Err(bad("room completion contract mismatch"))}}
    pub(super) fn reserved_refs(&self)->io::Result<Vec<room::ReservedRef>>{match self{Self::V2(s)=>s.reserved_refs(),Self::Loss(s)=>s.reserved_refs()}}
    pub(super) fn released_refs(&self)->io::Result<Vec<room::ReleasedRef>>{match self{Self::V2(s)=>s.released_refs(),Self::Loss(s)=>s.released_refs()}}
    pub(super) fn into_reserved(self)->io::Result<ReservedLaunch>{match self{
        Self::V2(s)=>{let r=s.into_reserved()?;Ok(ReservedLaunch{mode:Mode::MixedV2,snapshot:r.snapshot,battle:r.battle,references:r.references,
            bindings:r.bindings.into_iter().map(|b|ReservedBinding{session:b.session,owner:b.owner,reservation:Reservation::V2(b.reservation),ready:b.ready,revision:b.revision,source_stamp:Stamp::V2(b.source_stamp)}).collect()})},
        Self::Loss(s)=>{let r=s.into_reserved()?;Ok(ReservedLaunch{mode:Mode::LossV4,snapshot:r.snapshot,battle:r.battle,references:r.references,
            bindings:r.bindings.into_iter().map(|b|ReservedBinding{session:b.session,owner:b.owner,reservation:Reservation::Loss(b.reservation),ready:b.ready,revision:b.revision,source_stamp:Stamp::Loss(b.source_stamp)}).collect()})}}}
}
pub(super) struct ReservedBinding{pub(super) session:u32,pub(super) owner:Arc<identity091::Profile>,pub(super) reservation:Reservation,pub(super) ready:room::WriterReadyRef,pub(super) revision:u64,pub(super) source_stamp:Stamp}
pub(super) struct ReservedLaunch{pub(super) mode:Mode,pub(super) snapshot:room::LaunchSnapshot,pub(super) battle:room::BattleKey,pub(super) bindings:Vec<ReservedBinding>,pub(super) references:Vec<room::ReservedRef>}

#[cfg(test)]#[path="p10b_writer_mode_tests.rs"]mod tests;
