//! BOT-01: the GW-01 start barrier counts native places only; bots fill the
//! rest at start, own no Session and keep no battle alive without natives.
use super::*;
use super::super::{geometry,lifecycle};

fn peer(port:u16)->SocketAddr{SocketAddr::from(([127,0,0,1],port))}
fn three_entry_ready(now:Instant)->Vec<Session>{
    let (a,b,_)=super::tests::visible_pair(now);let mut c=b.clone();c.id=3;
    let mut sessions=vec![a,b,c];
    for (index,s) in sessions.iter_mut().enumerate() {
        let original=s.identity.as_ref().unwrap();
        s.identity=Some(Arc::new(crate::identity091::Profile{account_id:format!("bot01-owner-{index}"),database_id:index as i32+1,
            name:format!("player_{index}"),fixture_dir:original.fixture_dir.clone()}));
        s.key=[s.id as u8;16];s.login_peer=peer(32100+s.id as u16);s.login_attempt=Some(LoginAttempt::new(s.key,s.id,s.login_peer));
        s.base_peer=Some(peer(34100+s.id as u16));s.sync_mask=7;s.arena_base=false;let c=s.shared.as_mut().unwrap();c.phase=Phase::Account;c.join_requested=true;
        c.hangar_since=Some(now-Duration::from_secs(3));
    }
    sessions
}
/// Two native places of four, MS-1 bots, LAB kinematics (no scene).
fn bot_world(now:Instant)->World{model::bots::tests::prepared(crate::map_profile091::MapId::Prohorovka,2,4,1,now)}

#[test]
fn bot01_start_barrier_counts_native_places_and_reset_waits_for_natives_only(){
    let now=Instant::now();
    let mut table=Table{capacity:256,arena_split:true,retirement:RetirementWindow::with_limit(1024),..Table::default()};
    table.sessions=three_entry_ready(now);
    let mut world=bot_world(now);assert_eq!(world.human_places(),2);
    attach_waiting_sessions(&mut table,&mut world,now).unwrap();
    assert_eq!(world.actors.len(),2,"two native places; the third session stays in the hangar");
    assert!(table.arena_ready(&world,now),"start with two natives of four places");
    assert!(table.arena_admission_open(&[],&world),"no profile13 reservation yet");
    world.fill_bots().unwrap();assert_eq!(world.actors.len(),4);
    assert!(!table.arena_ready(&world,now),"filled: no second start");
    // Bot sessions are not Table sessions: no writer, no publication, no return.
    for a in &world.actors[2..] {
        let id=a.session.unwrap();assert!(id>=model::bots::SESSION_BASE);
        assert!(!table.sessions.iter().any(|s|s.id==id));
    }
    assert!(!table.sessions.iter().any(|s|world.actors[2..].iter().any(|a|a.session==Some(s.id))));
    advance_battle(&mut world,&mut None,now,true).unwrap();
    assert!(world.started.is_some());
    assert!(world.actors[2..].iter().all(|a|a.ready),"no scene: bots ready at once");
    assert!(!parked_battle_reset_ready(&table,&world));
    world.detach(1).unwrap();assert!(!parked_battle_reset_ready(&table,&world),"one native still plays");
    world.detach(2).unwrap();assert!(parked_battle_reset_ready(&table,&world),"bots alone do not hold the battle");
}

#[test]
fn bot01_absent_plan_keeps_the_full_roster_barrier(){
    let now=Instant::now();
    let map=crate::map_profile091::MapId::Prohorovka;
    let mut world=World::new_for_roster(0x5eed_b073,now,map,4).unwrap();
    world.enable_lifecycle(lifecycle::Rules::for_map(map).unwrap()).unwrap();
    world.bind_geometry(Arc::new(geometry::tests::bundle())).unwrap();
    let mut table=Table{capacity:256,arena_split:true,retirement:RetirementWindow::with_limit(1024),..Table::default()};
    table.sessions=three_entry_ready(now);
    attach_waiting_sessions(&mut table,&mut world,now).unwrap();
    assert_eq!(world.actors.len(),3);assert_eq!(world.human_places(),4);
    assert!(!table.arena_ready(&world,now),"without bots all four places need natives");
    assert_eq!(world.fill_bots().unwrap(),0);
}
