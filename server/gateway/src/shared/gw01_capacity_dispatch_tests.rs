//! GW-01: a Join reserves an arena place only while the battle has one; the
//! hangar session that waits is untouched by the writer and by a failed battle.
use super::*;
use super::queue_loss_tests::{account_context,native,receive,reserved,world,writer};

fn distinct(mut s:Session,id:u32)->Session{
    s.id=id;s.key=[id as u8;16];s.login_peer=format!("127.0.0.1:{}",41700+id).parse().unwrap();
    s.base_peer=Some(format!("127.0.0.1:{}",42700+id).parse().unwrap());s.login_attempt=Some(LoginAttempt::new(s.key,id,s.login_peer));s
}
fn config(root:&std::path::Path)->Arc<crate::identity091::Config>{
    fs::write(root.join("gw01-token.txt"),"a".repeat(43)).unwrap();
    let mut value=serde_json::json!({"login_bind":"127.0.0.1:20311","base_bind":"127.0.0.1:20312","identity_endpoint":"127.0.0.1:20313",
        "identity_token_file":root.join("gw01-token.txt"),"local_root":root,"session_duration_seconds":600,"connection_capacity":256});
    for field in["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression",
        "crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle","p04m_pool","p06t_mixed_ammo","visibility_v1",
        "p06t_ammo_rack_detonation"]{value[field]=true.into();}
    let path=root.join("gw01-config.json");fs::write(&path,serde_json::to_vec(&value).unwrap()).unwrap();
    Arc::new(crate::identity091::Config::load(path.to_str().unwrap()).unwrap())
}
fn waiting(now:Instant)->Session{
    let mut s=distinct(account_context(now,writer(1).0),3);receive(&mut s,&native(700,1,1),now);
    let c=s.shared.as_ref().unwrap();assert!(c.join_requested);assert!(state(&mut s).unwrap().reservation_loss.is_none());s
}

#[test]
fn gw01_join_beyond_arena_places_waits_without_a_writer_and_keeps_its_queue(){
    let now=Instant::now();let (first,r)=reserved(now);let (second,_)=reserved(now);
    let third=waiting(now);let before=third.clone();let w=world(&r,now);assert_eq!(w.expected_actors(),2);
    let root=third.identity.as_ref().unwrap().fixture_dir.clone();
    let mut table=Table{sessions:vec![distinct(first,1),distinct(second,2),third],capacity:256,arena_split:true,..Table::default()};
    assert!(!table.arena_admission_open(&[],&w));
    let mut dispatcher=Dispatcher::default();
    dispatcher.start_loss(&mut table,&w,config(&root),now).unwrap();
    assert!(dispatcher.task_loss.is_none()&&dispatcher.job_loss.is_none(),"no writer for a Join without an arena place");
    assert_eq!(state(&mut table.sessions[2]).unwrap(),state(&mut before.clone()).unwrap());
    assert!(table.sessions[2].shared.as_ref().unwrap().join_requested);
    // One place frees (the second owner retired without a reservation) -> the gate reopens.
    state(&mut table.sessions[1]).unwrap().reservation_loss=None;
    assert!(table.arena_admission_open(&[],&w));
    // Dispatcher-retained owners still count against the arena.
    let retained=vec![distinct(reserved(now).0,9)];assert!(!table.arena_admission_open(&retained,&w));
}

#[test]
fn gw01_battle_failure_leaves_a_waiting_hangar_session_queued(){
    let now=Instant::now();let (first,r)=reserved(now);let third=waiting(now);
    let mut w=world(&r,now);let mut runtime=None;let template=BattleTemplate::new(&w,&runtime);
    let mut table=Table{sessions:vec![distinct(first,1),third],capacity:256,arena_split:true,..Table::default()};
    let error=io::Error::new(io::ErrorKind::InvalidData,"injected failure");
    contain_battle_failure(&mut table,&mut w,&mut runtime,&template,now,"world_step",&error).unwrap();
    assert!(state(&mut table.sessions[0]).unwrap().pending_return_loss.is_some(),"the reserved owner gets its terminal");
    let c=table.sessions[1].shared.as_ref().unwrap();
    assert!(c.join_requested,"the hangar session keeps its queue");assert!(state(&mut table.sessions[1]).unwrap().selection.is_some());
    let mut old=Table{sessions:vec![table.sessions[1].clone()],..Table::default()};
    contain_battle_failure(&mut old,&mut w,&mut runtime,&template,now,"world_step",&error).unwrap();
    assert!(!old.sessions[0].shared.as_ref().unwrap().join_requested,"old path clears it");
}
