//! Child of shared/server.rs. Actual Session/Window staging only; the caller
//! retains the immutable Completion/Task until this stage commits successfully.
use super::*;
use super::super::{owner_hold_capture::Capture,profile13_session::CompletionHold};
use crate::{identity091,profile13_hold091 as hold,profile13_hold_projection091 as projection};
fn err(s:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("hold5 delivery: {s}"))}
fn state(s:&mut Session)->io::Result<&mut super::super::profile13_session::State>{s.shared.as_mut().and_then(|c|c.profile13.as_mut()).ok_or_else(||err("profile13 state"))}
fn same_owner(s:&Session,l:&super::super::owner_hold_capture::Link)->bool{s.identity.as_ref().is_some_and(|o|o.account_id==l.owner().account_id&&o.database_id==l.owner().database_id&&o.name==l.owner().name)}
fn source_cache(s:&Session,l:&super::super::owner_hold_capture::Link)->io::Result<()> {
    let p=s.shared.as_ref().and_then(|c|c.profile13.as_ref()).ok_or_else(||err("actual current profile13 state"))?;
    let h=s.hangar.as_ref().ok_or_else(||err("actual current hangar"))?;
    let sha=h.state_sha256().iter().map(|b|format!("{b:02x}")).collect::<String>();
    if !same_owner(s,l)||p.reservation_hold.as_ref()!=Some(l.reservation())||p.revision!=l.revision()
        ||s.ammo_service.as_ref().is_none_or(|a|!a.idle()||a.revision()!=l.revision())
        ||p.hold_projection.as_ref().is_none_or(|b|!b.matches(&l.owner().account_id,l.owner().database_id,l.revision(),&sha)){
        return Err(err("held source cache/current cursor changed"));}
    Ok(())
}
fn fresh<'a>(completion:&'a CompletionHold)->io::Result<&'a super::super::profile13_session::FreshHold>{
    if completion.refresh_error.is_some(){return Err(err("actual durable reply waiting for genuine projection"));}
    let f=completion.fresh.as_ref().ok_or_else(||err("actual Fresh missing"))?;
    if f.fresh.binding.revision!=completion.reply.revision||f.fresh.binding.wire_revision!=1{return Err(err("Fresh/current durable revision"));}
    let sha=f.fresh.fixtures.state_sha256().iter().map(|b|format!("{b:02x}")).collect::<String>();
    if !f.projection.matches(&completion.old_owner.account_id,completion.old_owner.database_id,completion.reply.revision,&sha)
        ||f.fresh.owner.account_id!=completion.old_owner.account_id||f.fresh.owner.database_id!=completion.old_owner.database_id||f.fresh.owner.name!=completion.old_owner.name{
        return Err(err("Fresh owner/state source"));}Ok(f)
}
pub(super) struct HeldStage{pub(super) capture:Capture,pub(super) session:Option<Session>,pub(super) release_retired_source:Option<u32>,pub(super) diagnostics:Vec<String>}
pub(super) struct AdmissionStage{pub(super) session:Session,pub(super) needs_pristine_cancel:bool,pub(super) diagnostics:Vec<String>}
pub(super) fn stage_admitted(s:&Session,completion:&CompletionHold)->io::Result<AdmissionStage>{
    let f=fresh(completion)?;let hold::Request::Admit{battle,native_inventory_id}=&completion.request else{return Err(err("not an actual Admit5 completion"));};
    let(battle,native_inventory_id)=(*battle,*native_inventory_id);
    if completion.source_session!=s.id||completion.reply.status!=hold::Status::Admitted||s.arena_base
        ||s.identity.as_ref().is_none_or(|o|o.account_id!=completion.old_owner.account_id||o.database_id!=completion.old_owner.database_id||o.name!=completion.old_owner.name){
        return Err(err("actual Admit5 Session/source"));}
    let r=completion.reply.reservation.as_ref().ok_or_else(||err("actual Admit5 receipt"))?;
    let p=s.shared.as_ref().and_then(|c|c.profile13.as_ref()).ok_or_else(||err("profile13 state"))?;
    if r.status!=hold::ReservationStatus::Active||r.result.is_some()||r.battle!=battle||r.frozen.loss().base.native_inventory_id!=native_inventory_id
        ||p.has_reservation()||p.has_pending_return()||p.selection!=Some(native_inventory_id)||p.revision!=completion.context.expected_revision
        ||s.ammo_service.as_ref().is_none_or(|a|!a.idle()||a.revision()!=completion.context.expected_revision){return Err(err("actual Admit5 current CAS/selection"));}
    f.projection.layout_for(&r.frozen,r.frozen.loss().base.counts())?;
    let mut next=s.clone();next.ammo_service.as_mut().ok_or_else(||err("ammo state"))?.refresh_revision(completion.reply.revision)?;
    next.ammo_service.as_mut().ok_or_else(||err("ammo state"))?.replace_pool(f.fresh.fixtures.p04m_binding().cloned())?;
    next.identity=Some(f.fresh.owner.clone());next.hangar=Some(f.fresh.fixtures.clone());
    let p=state(&mut next)?;p.revision=completion.reply.revision;p.in_flight=false;p.selection=None;p.reservation_hold=Some(r.clone());p.hold_projection=Some(Arc::new(f.projection.clone()));p.hold_departure_reason=None;p.hold_return_pending=false;p.hold_account_only=false;
    let c=next.shared.as_mut().ok_or_else(||err("shared state"))?;
    let needs_pristine_cancel=!next.active||!c.join_requested;
    if !needs_pristine_cancel{if next.outbox.len()>=128{return Err(err("queue callback budget"));}next.outbox.push_back(crate::map_drive_world091::queue_callback(true));c.queue_announced=true;}
    if next.active{next.drain_outbox()?;}
    Ok(AdmissionStage{session:next,needs_pristine_cancel,diagnostics:vec![format!("P08B_HOLD5_ADMITTED source_session={} battle={battle} revision={} owns_actual_reservation=true",s.id,completion.reply.revision)]})
}
pub(super) fn stage_held_return(s:&Session,capture:&Capture,slot:usize,completion:&CompletionHold,now:Instant)->io::Result<HeldStage>{
    let link=capture.link(slot)?;let f=fresh(completion)?;
    if completion.source_session!=link.source().source_session_id||completion.context!=link.context(false)||completion.request!=hold::Request::Inspect
        ||(s.id!=link.source().source_session_id&&(s.active||s.arena_base))||!same_owner(s,link)||completion.old_owner.account_id!=link.owner().account_id
        ||completion.old_owner.database_id!=link.owner().database_id||completion.old_owner.name!=link.owner().name{return Err(err("Inspect actual source/session/context"));}
    capture.check_held_inspect(slot,&completion.reply,f.fresh.binding.revision)?;
    f.projection.layout_for(&link.reservation().frozen,link.reservation().frozen.loss().base.counts())?;
    source_cache(s,link)?;
    let mut staged=capture.clone();staged.confirm_held_inspect(slot,&completion.reply,f.fresh.binding.revision)?;
    if !s.active{
        // No generic auth/retirement guard is bypassed. This exact retained
        // Session can now be removed because Capture owns the source/sole
        // final key and actual Inspect proved its durable ACTIVE5 reservation.
        return Ok(HeldStage{capture:staged,session:None,release_retired_source:Some(s.id),diagnostics:vec![format!("P08B_HOLD5_RETIRED_INSPECTED source_session={} active_reservation_preserved=true",s.id)]});
    }
    if !s.arena_base{return Err(err("manual early return requires actual Avatar"));}
    let mut next=s.clone();let old_wire=next.ammo_service.as_ref().ok_or_else(||err("ammo cursor"))?.wire_revision();
    next.shared.as_mut().ok_or_else(||err("shared state"))?.return_source_revision=old_wire;
    next.ammo_service.as_mut().ok_or_else(||err("ammo state"))?.rebind(f.fresh.binding)?;
    next.ammo_service.as_mut().ok_or_else(||err("ammo state"))?.replace_pool(f.fresh.fixtures.p04m_binding().cloned())?;
    next.identity=Some(f.fresh.owner.clone());next.hangar=Some(f.fresh.fixtures.clone());
    let p=state(&mut next)?;p.revision=completion.reply.revision;p.in_flight=false;p.hold_return_pending=false;p.hold_account_only=true;p.selection=None;p.hold_projection=Some(Arc::new(f.projection.clone()));
    let mut diagnostics=Vec::new();next.shared_return("owner_hold5_inspected_reserved",now,&mut diagnostics)?;
    diagnostics.push(format!("P08B_HOLD5_ACCOUNT_RETURN source_session={} slot={slot} sql_active=true final_finish_written=false",s.id));
    Ok(HeldStage{capture:staged,session:Some(next),release_retired_source:None,diagnostics})
}

/// An actual authenticated same-run RunOpen/Inspect may expose a locked
/// Account, never Avatar/re-entry. Caller installs this only after normal auth.
pub(super) fn check_locked_resume(capture:&Capture,owner:&identity091::Profile,reply:&hold::Reply,binding:&projection::Binding,state_sha:&str)->io::Result<usize>{
    let r=reply.reservation.as_ref().ok_or_else(||err("resume has no actual Active5"))?;
    let (slot,link)=capture.links().iter().find_map(|l|(l.owner().account_id==owner.account_id).then_some((usize::from(l.source().actor_slot),l))).ok_or_else(||err("same-run hold lacks registered source"))?;
    if !capture.held_inspected(slot)?||!matches!(reply.status,hold::Status::Ready|hold::Status::Inspected)||reply.code.is_some()
        ||r!=link.reservation()||reply.revision!=link.revision()||owner.database_id!=link.owner().database_id||owner.name!=link.owner().name
        ||!binding.matches(&owner.account_id,owner.database_id,reply.revision,state_sha){return Err(err("actual locked resume source/current run"));}
    binding.layout_for(&r.frozen,r.frozen.loss().base.counts())?;Ok(slot)
}

pub(super) struct FinalStage{pub(super) session:Session,pub(super) diagnostics:Vec<String>}
/// Resolve immediately in the same transport-loop turn as staging/commit.
/// A later authenticated Account that already received a released Fresh must
/// never receive a stale N->N+1 patch from an old held source cache.
pub(super) fn current_final_recipient(sessions:&[Session],capture:&Capture,slot:usize,finished_revision:u64)->io::Result<Option<usize>>{
    let link=capture.link(slot)?;let mut found=None;let mut seen=false;
    for(i,s)in sessions.iter().enumerate().filter(|(_,s)|s.active&&same_owner(s,link)){
        if seen{return Err(err("multiple live authenticated recipients"));}seen=true;
        let p=s.shared.as_ref().and_then(|c|c.profile13.as_ref()).ok_or_else(||err("current recipient has no profile13 mode"))?;
        if p.reservation_hold.as_ref()==Some(link.reservation()){
            source_cache(s,link)?;found=Some(i);
        }else if p.has_reservation()||p.has_pending_return()||p.in_flight||p.hold_projection.is_some()
            ||p.revision<finished_revision||s.ammo_service.as_ref().is_none_or(|a|a.revision()<finished_revision){
            return Err(err("recipient is neither exact held source nor already-released Fresh"));}
        // Otherwise actual new login loaded the released projection already;
        // truthful final may settle without sending an obsolete delta to it.
    }Ok(found)
}
pub(super) fn validate_finished_without_delivery(capture:&Capture,slot:usize,completion:&CompletionHold)->io::Result<()> {
    let link=capture.link(slot)?;let expected=capture.seal().ok_or_else(||err("no actual final seal"))?.finish(slot)?;
    if completion.source_session!=link.source().source_session_id||completion.context!=link.context(true)||completion.request!=hold::Request::Finish(expected.clone())
        ||completion.reply.status!=hold::Status::Finished||completion.reply.revision!=link.revision()+1||completion.old_owner.account_id!=link.owner().account_id
        ||completion.old_owner.database_id!=link.owner().database_id||completion.old_owner.name!=link.owner().name{
        return Err(err("truthful Finished5 source/final mismatch"));}
    let f=fresh(completion)?;let r=completion.reply.reservation.as_ref().ok_or_else(||err("actual final receipt"))?;
    if r.frozen!=link.reservation().frozen||r.reservation_id!=link.reservation().reservation_id||r.status!=hold::ReservationStatus::Finished{return Err(err("actual final5 receipt mismatch"));}
    f.projection.layout_for(&r.frozen,expected.remaining.map(|s|s.count))?;Ok(())
}
/// A replacement authenticated Account is not the immutable source Session,
/// but may be retained after disconnect. Validate the exact old cached receipt
/// before releasing that specific object after genuine Finished/Fresh.
pub(super) fn validate_retired_source(s:&Session,capture:&Capture,slot:usize)->io::Result<()> {
    let link=capture.link(slot)?;
    if s.active||(s.arena_base&&s.id!=link.source().source_session_id){return Err(err("retired delivery identity/Avatar authority"));}
    source_cache(s,link)
}
pub(super) fn stage_final(s:&Session,capture:&Capture,slot:usize,completion:&CompletionHold,now:Instant)->io::Result<FinalStage>{
    validate_finished_without_delivery(capture,slot,completion)?;
    let link=capture.link(slot)?;let seal=capture.seal().ok_or_else(||err("no actual final World seal"))?;let expected=seal.finish(slot)?;
    if completion.source_session!=link.source().source_session_id||completion.context!=link.context(true)||completion.request!=hold::Request::Finish(expected.clone())
        ||completion.reply.status!=hold::Status::Finished||completion.reply.revision!=link.revision()+1||completion.old_owner.account_id!=link.owner().account_id
        ||completion.old_owner.database_id!=link.owner().database_id||completion.old_owner.name!=link.owner().name{
        return Err(err("Finished differs from immutable source/final task"));}
    let f=fresh(completion)?;
    let receipt=completion.reply.reservation.as_ref().ok_or_else(||err("Finished5 receipt missing"))?;
    if receipt.frozen!=link.reservation().frozen||receipt.reservation_id!=link.reservation().reservation_id||receipt.status!=hold::ReservationStatus::Finished{
        return Err(err("actual final5 receipt/source"));}
    let layout=f.projection.layout_for(&receipt.frozen,expected.remaining.map(|s|s.count))?;
    source_cache(s,link)?;
    if !s.active{return Err(err("inactive final native recipient must use no-delivery path"));}
    let mut next=s.clone();let mut diagnostics=Vec::new();
    if next.arena_base{
        if next.id!=link.source().source_session_id{return Err(err("new Account cannot inherit original Avatar"));}
        let wire=next.ammo_service.as_ref().ok_or_else(||err("ammo state"))?.wire_revision();
        next.shared.as_mut().ok_or_else(||err("shared state"))?.return_source_revision=wire;
        next.ammo_service.as_mut().ok_or_else(||err("ammo state"))?.rebind(f.fresh.binding)?;
    }else{
        let c=next.shared.as_ref().ok_or_else(||err("shared state"))?;
        if c.phase!=Phase::Account||!next.account_ready||next.sync_mask!=7
            ||next.drive_return_account.as_ref().is_some_and(|warm|!warm.enabled||!warm.creation.is_some_and(|(_,acked)|acked)||c.return_mask!=7){
            return Err(err("wait for actual Account epoch/idle cursor"));}
        let wire=next.ammo_service.as_ref().ok_or_else(||err("ammo state"))?.wire_revision();
        let body=projection::final_update(layout,wire)?;
        let cancel_queue=next.shared.as_ref().is_some_and(|c|c.queue_announced);
        if next.outbox.len()+1+usize::from(cancel_queue)>128{return Err(err("Account terminal output budget"));}
        next.outbox.push_back(body);
        if cancel_queue{next.outbox.push_back(crate::map_drive_world091::queue_callback(false));}
        let c=next.shared.as_mut().ok_or_else(||err("shared state"))?;c.queue_announced=false;c.join_requested=false;
        next.ammo_service.as_mut().ok_or_else(||err("ammo state"))?.commit_external_update(f.fresh.binding.revision,wire,wire+1)?;
    }
    next.ammo_service.as_mut().ok_or_else(||err("ammo state"))?.replace_pool(f.fresh.fixtures.p04m_binding().cloned())?;
    next.identity=Some(f.fresh.owner.clone());next.hangar=Some(f.fresh.fixtures.clone());
    let p=state(&mut next)?;p.revision=completion.reply.revision;p.in_flight=false;p.reservation_hold=None;p.hold_projection=None;p.hold_return_pending=false;p.hold_account_only=false;p.selection=None;
    if next.arena_base{
        if capture.departure(slot)?.is_some(){
            // Outcome can beat the read-only held Inspect. The owner already
            // requested exit: publish the genuine released Fresh and finish
            // its existing Account return, without requiring a new Avatar
            // result stream that this detached recipient never queued.
            next.shared_return("owner_hold5_final_after_early_departure",now,&mut diagnostics)?;
        }else if let Some(results)=seal.results(){
            if next.shared.as_ref().and_then(|c|c.natural_result.as_deref())!=Some(results.as_ref()){
                return Err(err("actual Avatar result must equal sealed Results8"));}
            next.shared.as_mut().ok_or_else(||err("shared state"))?.result_committed=true;
        }else{next.shared_return("owner_hold5_contained_finish",now,&mut diagnostics)?;}
    }
    next.drain_outbox()?;
    diagnostics.push(format!("P08B_HOLD5_FINAL_DELIVERED source_session={} delivery_session={} slot={slot} revision={} sql_reserved=false incremental_account={}",
        link.source().source_session_id,next.id,completion.reply.revision,!s.arena_base));
    Ok(FinalStage{session:next,diagnostics})
}

/// Only the no-actor queue cancellation route uses this. The caller must
/// additionally prove no actual actor/registered Capture has this reservation.
pub(super) fn stage_pristine_finished(s:&Session,completion:&CompletionHold)->io::Result<FinalStage>{
    let hold::Request::Finish(command)=&completion.request else{return Err(err("not a pristine Finish5"));};
    if command.finalization!=hold::Finalization::PristineCancel||completion.reply.status!=hold::Status::Finished||s.arena_base
        ||completion.source_session!=s.id||s.identity.as_ref().is_none_or(|o|o.account_id!=completion.old_owner.account_id||o.database_id!=completion.old_owner.database_id||o.name!=completion.old_owner.name){
        return Err(err("pristine actual Account/command"));}
    let p=s.shared.as_ref().and_then(|c|c.profile13.as_ref()).ok_or_else(||err("profile13 state"))?;
    let r=p.reservation_hold.as_ref().ok_or_else(||err("no actual pending hold5"))?;command.validate_against(&completion.context,r)?;
    if p.revision!=completion.context.expected_revision||completion.reply.revision!=p.revision+1{return Err(err("pristine current CAS"));}
    let f=fresh(completion)?;let layout=f.projection.layout_for(&r.frozen,command.remaining.map(|a|a.count))?;
    let mut next=s.clone();let a=next.ammo_service.as_ref().ok_or_else(||err("ammo state"))?;
    if !a.idle()||a.revision()!=p.revision{return Err(err("pristine current native cursor"));}let wire=a.wire_revision();
    if next.active{
        if next.outbox.len()>=127{return Err(err("pristine queue budget"));}next.outbox.push_back(projection::final_update(layout,wire)?);
        next.ammo_service.as_mut().ok_or_else(||err("ammo state"))?.commit_external_update(completion.reply.revision,wire,wire+1)?;
    }else{next.ammo_service.as_mut().ok_or_else(||err("ammo state"))?.refresh_revision(completion.reply.revision)?;}
    next.ammo_service.as_mut().ok_or_else(||err("ammo state"))?.replace_pool(f.fresh.fixtures.p04m_binding().cloned())?;
    next.identity=Some(f.fresh.owner.clone());next.hangar=Some(f.fresh.fixtures.clone());
    let p=state(&mut next)?;p.revision=completion.reply.revision;p.reservation_hold=None;p.hold_projection=None;p.hold_return_pending=false;p.hold_account_only=false;p.in_flight=false;p.selection=None;
    let c=next.shared.as_mut().ok_or_else(||err("shared state"))?;if next.active&&c.queue_announced{next.outbox.push_back(crate::map_drive_world091::queue_callback(false));}c.queue_announced=false;c.join_requested=false;
    if next.active{next.drain_outbox()?;}Ok(FinalStage{session:next,diagnostics:vec![format!("P08B_HOLD5_PRISTINE_FINISHED source_session={} revision={} actor_source_absent=true",s.id,completion.reply.revision)]})
}
