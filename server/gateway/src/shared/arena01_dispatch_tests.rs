//! ARENA-01: two arenas share one writer and one table. A Join goes to the
//! open arena, a pending terminal waits for its actor in any arena, and a
//! failed battle contains only its own sessions. Synthetic reservations.
use super::*;
use super::queue_loss_tests::{account_context,native,receive,reserved,world,writer};

pub(super) fn distinct(mut s:Session,id:u32)->Session{
    s.id=id;s.key=[id as u8;16];s.login_peer=format!("127.0.0.1:{}",43700+id).parse().unwrap();
    s.base_peer=Some(format!("127.0.0.1:{}",44700+id).parse().unwrap());s.login_attempt=Some(LoginAttempt::new(s.key,id,s.login_peer));s
}
fn config(root:&std::path::Path,tag:&str)->Arc<crate::identity091::Config>{
    let token=root.join(format!("arena01-{tag}-token.txt"));fs::write(&token,"a".repeat(43)).unwrap();
    let mut value=serde_json::json!({"login_bind":"127.0.0.1:20321","base_bind":"127.0.0.1:20322","identity_endpoint":"127.0.0.1:20323",
        "identity_token_file":token,"local_root":root,"session_duration_seconds":600,"connection_capacity":256,"arenas":2});
    for field in["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression",
        "crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle","p04m_pool","p06t_mixed_ammo","visibility_v1",
        "p06t_ammo_rack_detonation"]{value[field]=true.into();}
    let path=root.join(format!("arena01-{tag}-config.json"));fs::write(&path,serde_json::to_vec(&value).unwrap()).unwrap();
    let mut config=crate::identity091::Config::load(path.to_str().unwrap()).unwrap();assert_eq!(config.arenas,2);
    // The writer job binds the fixture run; it is started but never reaches a bridge here.
    config.battle_run_id=writer(1).0.run_id;Arc::new(config)
}
pub(super) fn waiting(now:Instant,id:u32)->Session{
    let mut s=distinct(account_context(now,writer(1).0),id);receive(&mut s,&native(700,1,1),now);
    assert!(s.shared.as_ref().unwrap().join_requested);assert!(state(&mut s).unwrap().reservation_loss.is_none());s
}
/// Same owner fixture, its reservation moved to another arena's battle.
pub(super) fn reserved_in(now:Instant,id:u32,battle:u64)->Session{
    let mut s=distinct(reserved(now).0,id);state(&mut s).unwrap().reservation_loss.as_mut().unwrap().battle=battle;s
}
fn two_arenas(now:Instant)->(Vec<arena::Arena>,u64,u64){
    let r=reserved(now).1;let a=world(&r,now);
    let mut b=world(&r,now);let second=r.battle+arena::ARENA_ID_STRIDE;b.id=second;
    let arenas=[a,b].into_iter().enumerate().map(|(i,w)|{let t=BattleTemplate::new(&w,&None);arena::Arena::new(i,w,None,t)}).collect();
    (arenas,r.battle,second)
}

/// The loss writer is process-global (one job at a time); both writer phases
/// run in one test and each job is drained before the next starts.
fn settle(dispatcher:&mut Dispatcher){
    let deadline=Instant::now()+Duration::from_secs(20);
    let mut job=dispatcher.job_loss.take().expect("writer job started");
    while job.poll().is_none(){assert!(Instant::now()<deadline,"writer job bounded");std::thread::sleep(Duration::from_millis(5));}
    dispatcher.task_loss=None;
}

#[test]
fn arena01_join_goes_to_the_open_arena_and_a_terminal_waits_for_its_actor_in_any_arena(){
    join_after_a_full_arena_reserves_a_place_in_the_second_arena();
    pending_terminal_waits_while_its_actor_is_attached_in_another_arena();
}

fn join_after_a_full_arena_reserves_a_place_in_the_second_arena(){
    let now=Instant::now();let(arenas,first,second)=two_arenas(now);
    let third=waiting(now,3);let root=third.identity.as_ref().unwrap().fixture_dir.clone();
    let mut table=Table{sessions:vec![reserved_in(now,1,first),reserved_in(now,2,first),third],capacity:256,arena_split:true,multi_arena:true,..Table::default()};
    assert!(!table.arena_admission_open(&[],&arenas[0].world));
    let lobby=arena::lobby(&arenas,&table,&[]);assert_eq!(lobby,1,"arena 0 is full: the Join goes to arena 1");
    let mut dispatcher=Dispatcher::default();
    dispatcher.start_loss(&mut table,&arenas[lobby].world,config(&root,"join"),now).unwrap();
    let task=dispatcher.task_loss.as_ref().expect("one writer for the waiting Join");
    assert_eq!(task.session,3);assert!(matches!(task.request,RequestLoss::Admit{battle,..} if battle==second));
    settle(&mut dispatcher);
}

fn pending_terminal_waits_while_its_actor_is_attached_in_another_arena(){
    let now=Instant::now();let(mut arenas,_,second)=two_arenas(now);
    let mut s=reserved_in(now,4,second);let root=s.identity.as_ref().unwrap().fixture_dir.clone();
    let frozen=state(&mut s).unwrap().reservation_loss.clone().unwrap().frozen;
    let owner=s.identity.clone().unwrap();
    arenas[1].world.attach_owned_loss(model::Identity{account:owner.account_id.clone(),database:owner.database_id,name:owner.name.clone()},4,&frozen).unwrap();
    Dispatcher::terminal(&mut s,&arenas[1].world,FinishReason::ManualLeave).unwrap();
    assert!(state(&mut s).unwrap().pending_return_loss.is_some());
    let mut table=Table{sessions:vec![s],capacity:256,arena_split:true,multi_arena:true,..Table::default()};
    let mut dispatcher=Dispatcher::default();
    dispatcher.attached_elsewhere=arena::attached_outside(&arenas,0);assert_eq!(dispatcher.attached_elsewhere,vec![4]);
    dispatcher.start_loss(&mut table,&arenas[0].world,config(&root,"pending"),now).unwrap();
    assert!(dispatcher.task_loss.is_none(),"no Finish while the actor is still in arena 1");
    arenas[1].world.detach(4).unwrap();dispatcher.attached_elsewhere=arena::attached_outside(&arenas,0);
    dispatcher.start_loss(&mut table,&arenas[0].world,config(&root,"pending"),now).unwrap();
    assert!(matches!(dispatcher.task_loss.as_ref().unwrap().request,RequestLoss::Finish{battle,..} if battle==second));
    settle(&mut dispatcher);
}

#[test]
fn arena01_failed_battle_returns_only_its_own_players(){
    let now=Instant::now();let(mut arenas,first,second)=two_arenas(now);
    let other=reserved_in(now,2,second);let hangar=waiting(now,3);
    let mut table=Table{sessions:vec![reserved_in(now,1,first),other.clone(),hangar.clone()],capacity:256,arena_split:true,multi_arena:true,..Table::default()};
    let before=arenas[1].world.failure_snapshot();
    let error=io::Error::new(io::ErrorKind::InvalidData,"injected arena 0 failure");
    let a=&mut arenas[0];
    contain_battle_failure(&mut table,&mut a.world,&mut a.integrated,&a.template,now,"world_step",&error).unwrap();
    assert!(state(&mut table.sessions[0]).unwrap().pending_return_loss.is_some(),"arena 0 owner gets its terminal");
    assert_eq!(arenas[0].world.id,first+1,"arena 0 reset to its next battle");
    assert_eq!(state(&mut table.sessions[1]).unwrap(),state(&mut other.clone()).unwrap(),"arena 1 owner keeps its reservation");
    assert_eq!(state(&mut table.sessions[2]).unwrap(),state(&mut hangar.clone()).unwrap());
    assert!(table.sessions[2].shared.as_ref().unwrap().join_requested,"hangar queue kept");
    assert_eq!(arenas[1].world.failure_snapshot(),before,"arena 1 world untouched");
    // Without multi_arena the same failure still terminates every reserved owner (old one-world contract).
    let mut old=Table{sessions:vec![other],capacity:256,arena_split:true,..Table::default()};
    let a=&mut arenas[0];
    contain_battle_failure(&mut old,&mut a.world,&mut a.integrated,&a.template,now,"world_step",&error).unwrap();
    assert!(state(&mut old.sessions[0]).unwrap().pending_return_loss.is_some());
}
