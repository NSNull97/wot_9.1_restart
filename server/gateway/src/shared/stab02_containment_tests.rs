//! STAB-02: a battle failure in any phase, including one inside containment,
//! closes only that battle. Synthetic reservations and worlds (no native
//! client): arena 0 fails, arena 1 keeps stepping, the hangar session keeps
//! its queue, the failed battle's owner is returned through its writer lane.
use super::*;
use super::queue_loss_tests::{reserved,world};
use super::arena01_dispatch_tests::{reserved_in,waiting};

const OWNER:u32=11;const SPARE:u32=12;const HANGAR:u32=13;

/// Arena 0: owned-loss World of the reserved fixture battle. Arena 1: a started
/// two-actor World of another battle that keeps stepping.
fn fixture(now:Instant)->(Vec<arena::Arena>,Table,u64){
    let r=reserved(now).1;let first=r.battle;
    let mut other=model::tests::world(now);other.id=first+arena::ARENA_ID_STRIDE;
    let arenas=[world(&r,now),other].into_iter().enumerate()
        .map(|(i,w)|{let t=BattleTemplate::new(&w,&None);arena::Arena::new(i,w,None,t)}).collect();
    let table=Table{sessions:vec![reserved_in(now,OWNER,first),waiting(now,HANGAR)],capacity:256,arena_split:true,multi_arena:true,..Table::default()};
    (arenas,table,first)
}
fn session(table:&mut Table,id:u32)->&mut Session {table.sessions.iter_mut().find(|s|s.id==id).unwrap()}
fn seat(arenas:&mut [arena::Arena],table:&mut Table,id:u32)->usize {
    let s=session(table,id);let frozen=state(s).unwrap().reservation_loss.clone().unwrap().frozen;
    let owner=s.identity.clone().unwrap();
    arenas[0].world.attach_owned_loss(model::Identity{account:owner.account_id.clone(),database:owner.database_id,name:owner.name.clone()},id,&frozen).unwrap()
}
/// The other arena was not touched and still advances on the next step.
fn other_arena_steps(arenas:&mut [arena::Arena],before:&serde_json::Value,now:Instant){
    assert_eq!(&arenas[1].world.failure_snapshot(),before,"arena 1 untouched by the failure");
    let tick=arenas[1].world.tick;
    let events=arena::step_all(arenas,&[None,Some(arena::Command::Step{now:now+Duration::from_millis(300),start:false})]);
    assert!(matches!(events[1],Some(arena::Event::Stepped)));assert!(arenas[1].world.tick>tick,"arena 1 steps on");
}
fn owner_returned(table:&mut Table){
    let s=session(table,OWNER);
    assert!(state(s).unwrap().pending_return_loss.is_some(),"reservation goes back through the writer");
    assert!(!s.shared.as_ref().unwrap().join_requested);
}

#[test]
fn stab02_failure_in_every_battle_phase_closes_only_that_battle(){
    // Stage labels of every service-loop entry into containment. The error is
    // injected; its origin does not change containment (real origins below).
    for (stage,seated) in [("battle_select",false),("world_step",true),("world_step_panic",true),("result_snapshot",true),
        ("publication",true),("leave_terminal",true),("session_retire",true),("lifecycle",true),("battle_reset",true),("queue_reset",false)] {
        let now=Instant::now();let (mut arenas,mut table,first)=fixture(now);
        if seated {seat(&mut arenas,&mut table,OWNER);}
        let hangar=session(&mut table,HANGAR).clone();let before=arenas[1].world.failure_snapshot();
        let mut dispatcher=Dispatcher::default();
        let error=io::Error::new(io::ErrorKind::InvalidData,format!("injected {stage} failure"));
        containment::contain_arena(&mut table,&mut dispatcher,&mut arenas[0],now,stage,Some("fault_injected"),&error);
        owner_returned(&mut table);
        assert_eq!(arenas[0].world.id,first+1,"{stage}: arena 0 reset to its next battle");
        assert!(arenas[0].closed.is_none()&&arenas[0].world.actors.iter().all(|a|a.session.is_none()));
        let kept=session(&mut table,HANGAR);
        assert_eq!(state(kept).unwrap(),state(&mut hangar.clone()).unwrap(),"{stage}: hangar session unchanged");
        assert!(kept.shared.as_ref().unwrap().join_requested,"{stage}: hangar queue kept");
        other_arena_steps(&mut arenas,&before,now);
    }
}

#[test]
fn stab02_terminal_refused_inside_containment_cancels_the_reservation_instead_of_exiting(){
    // Stand -11 (2026-10-28): the failed World refused the actor's terminal
    // inside containment and `?` ended the gateway. Real refusal here: the
    // seated actor no longer matches its frozen loss contract.
    let now=Instant::now();let (mut arenas,mut table,first)=fixture(now);
    let slot=seat(&mut arenas,&mut table,OWNER);arenas[0].world.actors[slot].owned_loss=None;
    let s=session(&mut table,OWNER).clone();
    assert!(Dispatcher::terminal(&mut s.clone(),&arenas[0].world,FinishReason::BattleFailure).is_err(),"the refusal is real");
    let before=arenas[1].world.failure_snapshot();
    let error=io::Error::new(io::ErrorKind::InvalidData,"P06T shell must match closed source catalogue");
    let mut dispatcher=Dispatcher::default();
    containment::contain_arena(&mut table,&mut dispatcher,&mut arenas[0],now,"publication",Some("fault_publication"),&error);
    owner_returned(&mut table);
    assert!(table.sessions.iter().any(|s|s.id==HANGAR)&&table.sessions.len()==2,"nobody dropped");
    assert_eq!(arenas[0].world.id,first+1);other_arena_steps(&mut arenas,&before,now);
}

#[test]
fn stab02_world_that_cannot_be_rebuilt_closes_its_arena_and_reopens_on_retry(){
    let now=Instant::now();let (mut arenas,mut table,first)=fixture(now);
    // Real reset refusal: the next battle id overflows.
    arenas[0].world.id=u64::MAX;table.sessions.retain(|s|s.id==HANGAR);
    let before=arenas[1].world.failure_snapshot();let mut dispatcher=Dispatcher::default();
    let error=io::Error::new(io::ErrorKind::InvalidData,"injected world_step failure");
    containment::contain_arena(&mut table,&mut dispatcher,&mut arenas[0],now,"world_step",Some("fault_world_step"),&error);
    assert!(arenas[0].closed.is_some(),"arena closed, not the service");
    assert!(arenas[0].integrated.is_none()&&arenas[0].world.started.is_none());
    // Lobby: never the closed arena while an open unstarted one exists; with
    // none, 0 is returned and the service loop refuses the closed lobby.
    let spare=World::new(first+2*arena::ARENA_ID_STRIDE,now).unwrap();let t=BattleTemplate::new(&spare,&None);
    let mut three:Vec<arena::Arena>=Vec::new();
    for a in arenas.drain(..) {three.push(a);}
    three.push(arena::Arena::new(2,spare,None,t));
    assert_eq!(arena::lobby(&three,&table,&[]),2,"a closed arena takes no Join");
    three.pop();arenas=three;
    assert!(session(&mut table,HANGAR).shared.as_ref().unwrap().join_requested);
    other_arena_steps(&mut arenas,&before,now);
    containment::reopen_closed(&mut arenas[0],now);assert!(arenas[0].closed.is_some(),"no retry before its instant");
    containment::reopen_closed(&mut arenas[0],now+containment::REOPEN_RETRY);
    assert!(arenas[0].closed.is_some(),"the same refusal keeps it closed");
    arenas[0].world.id=first;
    containment::reopen_closed(&mut arenas[0],now+containment::REOPEN_RETRY*3);
    assert!(arenas[0].closed.is_none(),"reset succeeded: arena open again");assert_eq!(arenas[0].world.id,first+1);
}

#[test]
fn stab02_failed_containment_retires_every_member_even_when_retirement_fails(){
    let now=Instant::now();let (mut arenas,mut table,first)=fixture(now);
    seat(&mut arenas,&mut table,OWNER);
    // The spare owner cannot be retired as a transport: it has no login attempt.
    let mut spare=reserved_in(now,SPARE,first);spare.login_attempt=None;table.sessions.push(spare);
    let mut dispatcher=Dispatcher::default();let a=&mut arenas[0];
    let failure=io::Error::other("injected containment failure");
    containment::force_close(&mut table,&mut dispatcher,a,&[OWNER,SPARE],first,now,"world_step",&failure).unwrap();
    assert_eq!(table.sessions.iter().map(|s|s.id).collect::<Vec<_>>(),vec![HANGAR],"both members closed, hangar kept");
    let retired=dispatcher.retired_sessions().iter().map(|s|s.id).collect::<Vec<_>>();
    assert_eq!(retired,vec![OWNER,SPARE],"each reservation queued once on the writer lane");
    assert_eq!(arenas[0].world.id,first+1);
}

#[test]
fn stab02_old_helper_still_contains_the_refused_terminal(){
    // Training rooms and the existing tests keep contain_battle_failure.
    let now=Instant::now();let (mut arenas,mut table,first)=fixture(now);
    let slot=seat(&mut arenas,&mut table,OWNER);arenas[0].world.actors[slot].owned_loss=None;
    let error=io::Error::new(io::ErrorKind::InvalidData,"extended device profile requires explicit v2 policy");
    let a=&mut arenas[0];
    contain_battle_failure(&mut table,&mut a.world,&mut a.integrated,&a.template,now,"world_step",&error).unwrap();
    owner_returned(&mut table);assert_eq!(arenas[0].world.id,first+1);
}
