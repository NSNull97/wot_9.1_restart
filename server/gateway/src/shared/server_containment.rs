//! STAB-02: a failure of one battle closes that battle only. The service loop
//! enters here for every battle fault (seating, step, shot, damage, results,
//! publication, session close) and never receives an error back: the gateway
//! process, the hangar and the other arenas stay alive. A state that cannot be
//! closed the ordinary way is closed the hard way, and every step says so in
//! the journal; nothing is skipped silently and no success is invented.
use super::*;
use std::panic::{self,AssertUnwindSafe};

/// A closed arena retries its reset from the template this often.
pub(super) const REOPEN_RETRY:Duration=Duration::from_secs(5);

/// Contain the battle of arena `a`. Ordinary path: its players get their
/// terminal and the contained return to the hangar, reservations go to the
/// writer, the World is replaced. A session that cannot take that return is
/// retired (its writer lane keeps the reservation). If containment itself
/// fails or panics, every member of the battle is retired; a World that cannot
/// be rebuilt closes the arena (no Join, no step) until a reset succeeds.
pub(super) fn contain_arena(table:&mut Table,dispatcher:&mut profile13_dispatch::Dispatcher,a:&mut arena::Arena,
    now:Instant,stage:&str,late_reason:Option<&'static str>,error:&io::Error){
    if let (Some(late),Some(reason))=(&mut dispatcher.late,late_reason){late.before_reset(&a.world,reason);}
    if let Err(hold)=dispatcher.before_hold_reset(&a.world){
        println!("SHARED_CONTAINMENT_HOLD_FREEZE_FAILED battle={} stage={stage} error={hold} hold_capture_unsealed=true",a.world.id);
    }
    let battle=a.world.id;
    let members:Vec<u32>=table.sessions.iter().filter(|s|arena_member(s,&a.world)).map(|s|s.id).collect();
    let contained=panic::catch_unwind(AssertUnwindSafe(||
        contain_battle_sessions(table,&mut a.world,&mut a.integrated,&a.template,now,stage,error)));
    let reset=match contained {
        Ok(Ok(c))=>{
            for id in c.unreturned {retire_member(table,dispatcher,&mut a.world,id,now,"failed_battle_return");}
            c.reset
        },
        Ok(Err(failure))=>force_close(table,dispatcher,a,&members,battle,now,stage,&failure),
        Err(_)=>force_close(table,dispatcher,a,&members,battle,now,stage,&io::Error::other("battle containment panicked")),
    };
    if let Err(failure)=reset {close_arena(a,now,stage,&failure);}
    a.cursors.reset();
}

/// Containment did not finish: the World and its sessions are in an unknown
/// mix of old and contained state. Retire every member still here, then reset.
pub(super) fn force_close(table:&mut Table,dispatcher:&mut profile13_dispatch::Dispatcher,a:&mut arena::Arena,members:&[u32],
    battle:u64,now:Instant,stage:&str,failure:&io::Error)->io::Result<()>{
    println!("SHARED_CONTAINMENT_FAILED battle={battle} stage={stage} error={failure} members={members:?} forced_retirement=true return_to_hangar=false");
    for id in members {retire_member(table,dispatcher,&mut a.world,*id,now,"failed_battle_containment");}
    match panic::catch_unwind(AssertUnwindSafe(||a.template.replace(&mut a.world,&mut a.integrated,now))) {
        Ok(reset)=>reset,
        Err(_)=>Err(io::Error::other("battle reset panicked")),
    }
}

/// Retire one session of a failed battle. Order: the dispatcher (its writer
/// lane releases the reservation); once more after releasing its actor, when
/// the failed World refused the actor's terminal; the bare transport; last, a
/// journaled drop. Each fallback is a separate explicit line.
pub(super) fn retire_member(table:&mut Table,dispatcher:&mut profile13_dispatch::Dispatcher,world:&mut World,
    id:u32,now:Instant,reason:&str){
    if !table.sessions.iter().any(|s|s.id==id){return;}
    let first=match dispatcher.retire(table,world,id,now,reason){Ok(())=>return,Err(e)=>e};
    if !table.sessions.iter().any(|s|s.id==id){
        println!("SHARED_CONTAINMENT_RETIRE_PARTIAL session={id} battle={} error={first} session_closed=true",world.id);return;
    }
    // The writer lane already holds this session's copy: never queue it twice.
    let second=if dispatcher.retired_sessions().iter().any(|s|s.id==id) {first} else {
        if world.actors.iter().any(|a|a.session==Some(id)) {
            if let Err(e)=world.detach(id){println!("SHARED_CONTAINMENT_DETACH_FAILED session={id} battle={} error={e}",world.id);}
        }
        println!("SHARED_CONTAINMENT_RETIRE_RETRY session={id} battle={} error={first} actor_released=true",world.id);
        match dispatcher.retire(table,world,id,now,reason){Ok(())=>return,Err(e)=>e}
    };
    if !table.sessions.iter().any(|s|s.id==id){
        println!("SHARED_CONTAINMENT_RETIRE_PARTIAL session={id} battle={} error={second} session_closed=true",world.id);return;
    }
    let third=match table.retire(id,world,now,reason){
        Ok(())=>{println!("SHARED_CONTAINMENT_TRANSPORT_RETIRED session={id} battle={} error={second} writer_lane=false reservation_unreleased=true",world.id);return;},
        Err(e)=>e,
    };
    if let Some(index)=table.sessions.iter().position(|s|s.id==id){table.sessions.remove(index);}
    println!("SHARED_SESSION_DROPPED session={id} battle={} reason={reason} error={third} retirement_unrecorded=true reservation_unreleased=true",world.id);
}

/// A session's close hit a battle error (its terminal on the failed World):
/// contain that battle, then close the session on the contained state.
pub(super) fn retire_or_contain(table:&mut Table,dispatcher:&mut profile13_dispatch::Dispatcher,a:&mut arena::Arena,
    id:u32,now:Instant,reason:&str){
    let Err(error)=dispatcher.retire(table,&mut a.world,id,now,reason) else{return;};
    println!("SHARED_SESSION_RETIRE_FAILED session={id} battle={} reason={reason} error={error} battle_contained=true",a.world.id);
    contain_arena(table,dispatcher,a,now,"session_retire",Some("fault_session_retire"),&error);
    if !table.sessions.iter().any(|s|s.id==id){return;}
    let closed=match retire_contained_session(dispatcher,table,&a.world,id,now,reason){
        Ok(true)=>Ok(()),Ok(false)=>dispatcher.retire(table,&mut a.world,id,now,reason),Err(e)=>Err(e),
    };
    if let Err(error)=closed {
        println!("SHARED_SESSION_RETIRE_FAILED session={id} battle={} reason={reason} error={error} after_containment=true",a.world.id);
        retire_member(table,dispatcher,&mut a.world,id,now,reason);
    }
}

/// A contained old Avatar whose retained return no longer checks out: close
/// only that session; the replacement World is not touched.
pub(super) fn retire_contained_or_drop(table:&mut Table,dispatcher:&mut profile13_dispatch::Dispatcher,world:&mut World,
    id:u32,now:Instant,reason:&str)->bool{
    match retire_contained_session(dispatcher,table,world,id,now,reason){
        Ok(done)=>done,
        Err(error)=>{
            println!("SHARED_CONTAINED_RETURN_FAILED session={id} reason={error} replacement_world_unchanged=true");
            retire_member(table,dispatcher,world,id,now,reason);true
        },
    }
}

/// The World could not be rebuilt: the arena keeps an empty World (or, if even
/// that fails, the failed one) that is never stepped and takes no Join.
fn close_arena(a:&mut arena::Arena,now:Instant,stage:&str,failure:&io::Error){
    let next=a.world.id.checked_add(1).unwrap_or(a.world.id);
    a.integrated=None;
    let world=match World::new(next,now){
        Ok(empty)=>{a.world=empty;"empty"},
        Err(e)=>{println!("SHARED_ARENA_EMPTY_WORLD_FAILED arena={} battle={} error={e}",a.index,a.world.id);"failed_retained_inert"},
    };
    a.closed=Some(now+REOPEN_RETRY);
    println!("SHARED_ARENA_CLOSED arena={} battle={} stage={stage} error={failure} world={world} joins_refused=true retry_ms={} service_alive=true",
        a.index,a.world.id,REOPEN_RETRY.as_millis());
}

/// Retry the reset of a closed arena once its retry instant has passed.
pub(super) fn reopen_closed(a:&mut arena::Arena,now:Instant){
    let Some(at)=a.closed else{return;};
    if now<at {return;}
    let retry=match panic::catch_unwind(AssertUnwindSafe(||a.template.replace(&mut a.world,&mut a.integrated,now))) {
        Ok(result)=>result,Err(_)=>Err(io::Error::other("arena reset panicked")),
    };
    match retry {
        Ok(())=>{a.closed=None;a.cursors.reset();println!("SHARED_ARENA_REOPENED arena={} battle={} service_alive=true",a.index,a.world.id);},
        Err(e)=>{a.integrated=None;a.closed=Some(now+REOPEN_RETRY);
            println!("SHARED_ARENA_CLOSED_RETRY arena={} battle={} error={e} retry_ms={}",a.index,a.world.id,REOPEN_RETRY.as_millis());},
    }
}
