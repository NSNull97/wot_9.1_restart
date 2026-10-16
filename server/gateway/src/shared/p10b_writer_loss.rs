//! DRAFT additive API4 durable native-room reservation/compensation bridge.
//! Selection comes from the separately checked read-only owned DTO. No native
//! success/claim release can be inferred from timeout or an outstanding Inspect.
use std::{io,sync::Arc};
use crate::{identity091,profile13_loss091 as writer};
use crate::battle091::profile13::{Context,FinishReason};
use super::profile13_session::{JobLoss,CompletionLoss,TerminalLoss};
use crate::training091::domain::{Account,BattleKey,LaunchSnapshot,WriterReadyRef,ReservedRef,ReleasedRef};

fn bad(s:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,s)}
fn digest(s:&str)->io::Result<[u8;32]>{
    if s.len()!=64{return Err(bad("ready digest"));}let mut out=[0;32];
    for(i,pair)in s.as_bytes().chunks_exact(2).enumerate(){
        fn nibble(b:u8)->io::Result<u8>{match b{b'0'..=b'9'=>Ok(b-b'0'),b'a'..=b'f'=>Ok(b-b'a'+10),_=>Err(bad("ready digest hex"))}}
        out[i]=nibble(pair[0])?*16+nibble(pair[1])?;
    }Ok(out)
}
fn account(s:&str)->io::Result<Account>{
    if s.len()!=36||[8,13,18,23].into_iter().any(|i|s.as_bytes()[i]!=b'-'){return Err(bad("ready UUID"));}
    let compact=s.bytes().filter(|b|*b!=b'-').map(char::from).collect::<String>();
    if compact.len()!=32{return Err(bad("ready UUID shape"));}
    let d=digest(&(compact+&"0".repeat(32)))?;Ok(Account(d[..16].try_into().map_err(|_|bad("ready UUID bytes"))?))
}

#[derive(Clone)]
pub(super) struct ReadySelection{owner:Arc<identity091::Profile>,session:u32,context:Context,frozen:writer::FrozenLoss,ready:WriterReadyRef,source_stamp:crate::training091::selection_loss::Stamp}
impl ReadySelection{
    /// Caller first fences actual Session/channel/room/source against the
    /// immutable query origin; parsing this DTO does not authenticate a socket.
    pub(super) fn from_selection(owner:Arc<identity091::Profile>,session:u32,selection:crate::training091::selection_loss::Selection)->io::Result<Self>{
        let(request,_,frozen,fingerprint)=selection.into_parts();
        let base=&request.base;
        crate::training091::selection_loss::encode_request(&request)?;
        frozen.validate_owned(&owner.account_id)?;
        if session==0||base.account_id!=owner.account_id||base.native_database_id!=owner.database_id
            ||frozen.base.native_inventory_id!=base.native_inventory_id{return Err(bad("ready authenticated owner/channel"));}
        let context=Context{account_id:base.account_id.clone(),native_database_id:base.native_database_id,
            run_id:base.run_id.clone(),expected_revision:base.expected_revision,command_key:"p10b:read-only-selection".into()};
        let ready=WriterReadyRef::from_verified_writer(account(&owner.account_id)?,frozen.base.vehicle_inventory_id.clone(),
            base.expected_revision as u32,digest(&fingerprint)?).map_err(|_|bad("room ready ref"))?;
        Ok(Self{owner,session,context,frozen,ready,source_stamp:request.projection_stamp})
    }
    pub(super) fn source_stamp(&self)->&crate::training091::selection_loss::Stamp{&self.source_stamp}
    pub(super) fn run_id(&self)->&str{&self.context.run_id}
    /// AUTHORED cfg(test) scheduling seam between separately saved SQL runs and
    /// tiny cache fixtures. Not a production readiness/ownership constructor.
    #[cfg(test)]
    pub(super) fn with_launch_scheduler_seam_for_test(mut self,run:String,native_state_sha256:String)->Self{
        self.context.run_id=run;self.source_stamp.base.native_state_sha256=native_state_sha256;self
    }
    pub(super) fn reference(&self)->&WriterReadyRef{&self.ready}
    pub(super) fn session(&self)->u32{self.session}
    pub(super) fn owner(&self)->&Arc<identity091::Profile>{&self.owner}
    pub(super) fn frozen(&self)->&writer::FrozenLoss{&self.frozen}
}

// Null Inspect alone is not an unlock. The future training-only JobLoss
// adapter must refresh canonical source at its actual reported revision.
fn fresh_matches(c:&CompletionLoss,s:&ReadySelection,revision:u64)->bool{
    c.refresh_error.is_none()&&c.fresh.as_ref().is_some_and(|f|f.owner.account_id==s.owner.account_id
        &&f.owner.database_id==s.owner.database_id&&f.owner.name==s.owner.name
        &&f.binding.revision==revision&&f.binding.wire_revision==1
        &&f.fixtures.p04m_binding().is_some_and(|p|p.matches(&f.owner.account_id,f.owner.database_id,revision)))
}

#[derive(Clone,Copy,PartialEq,Eq)]enum Stage{Unissued,Reserved,Denied,NoReservation,Released}
#[derive(Clone)]struct Slot{selection:ReadySelection,stage:Stage,reservation:Option<writer::Reservation>,revision:u64}
#[derive(Clone)]pub(super) struct Task{index:usize,session:u32,owner:Arc<identity091::Profile>,context:Context,request:writer::Request}
impl Task{
    pub(super) fn session(&self)->u32{self.session}
    pub(super) fn owner(&self)->&Arc<identity091::Profile>{&self.owner}
    pub(super) fn context(&self)->&Context{&self.context}
    pub(super) fn request(&self)->&writer::Request{&self.request}
    /// Reuse the real singleton writer worker. A transport/refresh error retains
    /// this identical Task; retrying never allocates a new command key.
    pub(super) fn start(&self,config:Arc<identity091::Config>)->io::Result<JobLoss>{
        if !config.training_rooms{return Err(bad("API4 room Task requires explicit training mode"));}
        JobLoss::start(self.session,self.owner.clone(),config,self.context.clone(),self.request.clone())
    }
}
pub(super) struct ReservedBinding{
    pub(super) session:u32,pub(super) owner:Arc<identity091::Profile>,pub(super) reservation:writer::Reservation,
    pub(super) ready:WriterReadyRef,pub(super) revision:u64,pub(super) source_stamp:crate::training091::selection_loss::Stamp,
}
pub(super) struct ReservedLaunch{
    pub(super) snapshot:LaunchSnapshot,pub(super) battle:BattleKey,pub(super) bindings:Vec<ReservedBinding>,pub(super) references:Vec<ReservedRef>,
}
#[derive(Clone)]pub(super) struct Saga{snapshot:LaunchSnapshot,battle:BattleKey,slots:Vec<Slot>,pending:Option<Task>,aborting:bool}
impl Saga{
    pub(super) fn snapshot(&self)->&LaunchSnapshot{&self.snapshot}
    pub(super) fn battle(&self)->BattleKey{self.battle}
    pub(super) fn aborting(&self)->bool{self.aborting}
    fn origin(&self,stage:impl Fn(Stage)->bool)->Option<(u32,Arc<identity091::Profile>,u64)>{
        if self.pending.is_some(){return None;}
        self.slots.iter().find(|s|stage(s.stage)).map(|s|(s.selection.session,s.selection.owner.clone(),s.revision))
    }
    pub(super) fn next_admission_origin(&self)->Option<(u32,Arc<identity091::Profile>,u64)>{
        if self.aborting{return None;}self.origin(|s|s==Stage::Unissued)
    }
    pub(super) fn next_compensation_origin(&self)->Option<(u32,Arc<identity091::Profile>,u64)>{
        if !self.aborting{return None;}self.origin(|s|s==Stage::Reserved)
    }
    pub(super) fn next_inspection_origin(&self)->Option<(u32,Arc<identity091::Profile>,u64)>{
        if !self.aborting{return None;}self.origin(|s|matches!(s,Stage::Unissued|Stage::Denied))
    }

    pub(super) fn new(snapshot:LaunchSnapshot,battle:BattleKey,selections:Vec<ReadySelection>)->io::Result<Self>{
        if battle.0==0||battle.0>i64::MAX as u64||snapshot.members().len()!=selections.len(){return Err(bad("room launch shape"));}
        let mut slots=Vec::new();
        for member in snapshot.members(){
            let matching=selections.iter().filter(|s|s.ready==*member.ready()).collect::<Vec<_>>();
            if matching.len()!=1{return Err(bad("room launch ready mismatch"));}
            let selection=matching[0].clone();let revision=selection.context.expected_revision;
            slots.push(Slot{selection,stage:Stage::Unissued,reservation:None,revision});
        }
        Ok(Self{snapshot,battle,slots,pending:None,aborting:false})
    }
    pub(super) fn retry(&self)->Option<Task>{self.pending.clone()}
    pub(super) fn abort(&mut self){self.aborting=true;}
    pub(super) fn next_admit(&mut self,context:Context)->io::Result<Option<Task>>{
        if self.aborting||self.pending.is_some(){return Err(bad("saga aborting or unresolved writer task"));}
        let Some(index)=self.slots.iter().position(|s|s.stage==Stage::Unissued)else{return Ok(None);};
        let s=&self.slots[index];
        if context.account_id!=s.selection.owner.account_id||context.native_database_id!=s.selection.owner.database_id
            ||context.run_id!=s.selection.context.run_id||context.expected_revision!=s.revision{return Err(bad("admit ready context"));}
        let task=Task{index,session:s.selection.session,owner:s.selection.owner.clone(),context,
            request:writer::Request::Admit{battle:self.battle.0,native_inventory_id:s.selection.frozen.base.native_inventory_id}};
        writer::encode_request(&task.context,&task.request)?;self.pending=Some(task.clone());Ok(Some(task))
    }
    pub(super) fn next_cancel(&mut self,context:Context)->io::Result<Option<Task>>{
        if !self.aborting||self.pending.is_some(){return Err(bad("cancel before drain"));}
        let Some(index)=self.slots.iter().position(|s|s.stage==Stage::Reserved)else{return Ok(None);};let s=&self.slots[index];
        let reservation=s.reservation.as_ref().ok_or_else(||bad("cancel reservation"))?;
        if context.account_id!=s.selection.context.account_id||context.native_database_id!=s.selection.context.native_database_id
            ||context.run_id!=s.selection.context.run_id||context.expected_revision!=s.revision{return Err(bad("cancel context"));}
        // No actor is attached until ALL admits succeed and commit_launch runs.
        // Only that preparing-room invariant permits this pristine cancellation.
        let request=TerminalLoss::cancelled(reservation,s.selection.owner.database_id)?.request();
        writer::encode_request(&context,&request)?;let task=Task{index,session:s.selection.session,owner:s.selection.owner.clone(),context,request};
        self.pending=Some(task.clone());Ok(Some(task))
    }
    /// ONLY after exclusive owner claim and all other writer jobs are drained.
    /// Issue the exact immutable Inspect here; an arbitrary earlier null Inspect
    /// is never a release proof. Timeout/error retains this same pending Task.
    pub(super) fn next_inspect(&mut self,context:Context)->io::Result<Option<Task>>{
        if !self.aborting||self.pending.is_some(){return Err(bad("inspect before abort/drain"));}
        let Some(index)=self.slots.iter().position(|s|matches!(s.stage,Stage::Unissued|Stage::Denied))else{return Ok(None);};
        let s=&self.slots[index];
        if context.account_id!=s.selection.owner.account_id||context.native_database_id!=s.selection.owner.database_id
            ||context.run_id!=s.selection.context.run_id||context.expected_revision!=s.revision{return Err(bad("inspect current owner/revision"));}
        let task=Task{index,session:s.selection.session,owner:s.selection.owner.clone(),context,request:writer::Request::Inspect};
        writer::encode_request(&task.context,&task.request)?;self.pending=Some(task.clone());Ok(Some(task))
    }
    pub(super) fn complete(&mut self,c:&CompletionLoss)->io::Result<()>{
        let mut next=self.clone();next.complete_inner(c)?;*self=next;Ok(())
    }
    fn complete_inner(&mut self,c:&CompletionLoss)->io::Result<()>{
        let task=self.pending.as_ref().ok_or_else(||bad("no unresolved writer task"))?;
        if task.session!=c.session||task.owner.database_id!=c.old_owner.database_id||task.context!=c.context||task.request!=c.request||task.owner.account_id!=c.old_owner.account_id||task.owner.name!=c.old_owner.name{return Err(bad("late foreign completion"));}
        let slot=&mut self.slots[task.index];let reply=&c.reply;
        if task.request==writer::Request::Inspect{
            if !self.aborting||!matches!(slot.stage,Stage::Unissued|Stage::Denied)
                ||reply.status!=writer::Status::Inspected||reply.reservation.is_some()
                ||reply.revision<slot.revision||c.refresh_error.is_some()
                ||!fresh_matches(c,&slot.selection,reply.revision){return Err(bad("issued no-reservation proof mismatch"));}
            slot.stage=Stage::NoReservation;slot.revision=reply.revision;self.pending=None;return Ok(());
        }
        if reply.status==writer::Status::Rejected{
            if task.request.operation()!="admit"||!matches!(reply.code.as_deref(),Some("STALE_REVISION"|"UNKNOWN_VEHICLE"|
                "BATTLE_PROFILE_UNSUPPORTED"|"OWNER_ACCEPTANCE_REQUIRED"|"INCOMPLETE_CREW"|"AMMUNITION_EMPTY"|"AMMUNITION_UNSUPPORTED")){
                return Err(bad("denial does not prove released admission"));}
            slot.revision=slot.revision.max(reply.revision);slot.stage=Stage::Denied;self.aborting=true;
        }else{
            if !fresh_matches(c,&slot.selection,reply.revision){
                return Err(bad("trusted projection revision/owner"));}
            let r=reply.reservation.as_ref().ok_or_else(||bad("reservation receipt absent"))?;
            if r.frozen!=slot.selection.frozen||r.run_id!=task.context.run_id||r.battle!=self.battle.0{return Err(bad("selection receipt mismatch"));}
            match &task.request{
                writer::Request::Admit{..}=>{
                    if reply.status!=writer::Status::Admitted||r.status!=writer::ReservationStatus::Active||r.result.is_some()
                        ||r.reservation_id!=task.context.command_key||reply.revision!=slot.revision+1{return Err(bad("admit receipt"));}
                    slot.stage=Stage::Reserved;
                },
                writer::Request::Finish{reservation_id,remaining_ammunition,..}=>{
                    let result=r.result.as_ref().ok_or_else(||bad("terminal receipt absent"))?;
                    if reply.status!=writer::Status::Finished||r.status!=writer::ReservationStatus::Finished||&r.reservation_id!=reservation_id
                        ||result.reason!="cancelled"||result.remaining!=*remaining_ammunition||result.fired.iter().chain(&result.lost).any(|a|a.count!=0)||result.loss_event.is_some()
                        ||result.terminal_hp!=Some(r.frozen.base.max_hp){return Err(bad("cancel not durably proved"));}
                    slot.stage=Stage::Released;
                },_=>return Err(bad("saga operation")),
            }
            slot.reservation=Some(r.clone());slot.revision=reply.revision;
        }
        self.pending=None;Ok(())
    }
    pub(super) fn reserved_refs(&self)->io::Result<Vec<ReservedRef>>{
        if self.aborting||self.pending.is_some()||self.slots.iter().any(|s|s.stage!=Stage::Reserved){return Err(bad("partial launch"));}
        self.slots.iter().map(|s|ReservedRef::from_verified_writer(s.selection.ready.clone(),s.reservation.as_ref().ok_or_else(||bad("missing reserve"))?.reservation_id.clone(),
            self.battle,self.snapshot.ticket()).map_err(|_|bad("room reserve ref"))).collect()
    }
    /// Caller consumes a staged Saga clone only. The owning coordinator removes
    /// its Saga in the SAME transaction that installs all World/Session state.
    /// A retained clone must never remain an active-battle cancellation handle.
    pub(super) fn into_reserved(self)->io::Result<ReservedLaunch>{
        let references=self.reserved_refs()?;
        let mut bindings=Vec::with_capacity(self.slots.len());
        for slot in self.slots{
            let reservation=slot.reservation.ok_or_else(||bad("launch missing reserved receipt"))?;
            bindings.push(ReservedBinding{session:slot.selection.session,owner:slot.selection.owner,reservation,
                ready:slot.selection.ready,revision:slot.revision,source_stamp:slot.selection.source_stamp});
        }
        Ok(ReservedLaunch{snapshot:self.snapshot,battle:self.battle,bindings,references})
    }
    pub(super) fn released_refs(&self)->io::Result<Vec<ReleasedRef>>{
        if !self.aborting||self.pending.is_some()||self.slots.iter().any(|s|!matches!(s.stage,Stage::NoReservation|Stage::Released)){
            return Err(bad("release not proved"));}
        self.slots.iter().map(|s|ReleasedRef::from_verified_writer(s.selection.ready.clone(),self.snapshot.ticket()).map_err(|_|bad("room release ref"))).collect()
    }
}

#[cfg(test)]
#[path="p10b_writer_loss_tests.rs"]
mod tests;
