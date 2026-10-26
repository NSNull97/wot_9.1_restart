//! GW-01: connection capacity separate from arena places. Table admission,
//! replay-window bound and the start barrier; no native client claim.
use super::*;

fn peer(port:u16)->SocketAddr{SocketAddr::from(([127,0,0,1],port))}
fn bare(id:u32,now:Instant)->Session{
    let mut s=Session::new(id,[id as u8;16],peer(31000+id as u16),now);
    s.login_attempt=Some(LoginAttempt::new(s.key,id,s.login_peer));s
}
fn attempt(id:u32)->LoginAttempt{
    // Non-uniform key: never equal to a fixture session's [id;16].
    let mut key=[0xee;16];key[..4].copy_from_slice(&id.to_le_bytes());LoginAttempt::new(key,1000+id,peer(33000+id as u16))
}
fn split(capacity:usize)->Table{
    Table{capacity,arena_split:true,retirement:RetirementWindow::with_limit(capacity*4),..Table::default()}
}

#[test]
fn gw01_third_login_is_admitted_when_connections_are_separate_from_two_arena_places(){
    let now=Instant::now();
    let mut old=Table{capacity:2,sessions:vec![bare(1,now),bare(2,now)],..Table::default()};
    assert!(old.admissible(&attempt(3),now).is_err(),"old table: the arena size is the connection bound");
    let mut table=split(256);table.sessions=vec![bare(1,now),bare(2,now)];
    table.admissible(&attempt(3),now).unwrap();
    for id in 3..256 {table.sessions.push(bare(id,now));}
    assert_eq!(table.sessions.len(),255);table.admissible(&attempt(300),now).unwrap();
    table.sessions.push(bare(256,now));assert!(table.full());
    assert!(table.admissible(&attempt(301),now).is_err(),"full gateway refuses; the caller sends LoginReply 73");
}

#[test]
fn gw01_replay_window_scales_with_connections_and_stays_bounded(){
    let now=Instant::now();
    let mut old=Table::default();old.capacity=256;
    for id in 0..MAX_RETIRED as u32 {old.retirement.retire(attempt(id),None,now).unwrap();}
    assert!(old.admissible(&attempt(500),now).is_err());
    let mut table=split(256);assert_eq!(table.retirement.limit(),1024);
    for id in 0..200 {table.retirement.retire(attempt(id),None,now).unwrap();}
    table.admissible(&attempt(500),now).unwrap();
    for id in 200..1024 {table.retirement.retire(attempt(id),None,now).unwrap();}
    assert!(table.retirement.retire(attempt(2000),None,now).is_err(),"never evicts replay protection");
    assert!(table.admissible(&attempt(2001),now).is_err());
    assert_eq!(RetirementWindow::with_limit(4).limit(),MAX_RETIRED,"never below the single-session bound");
}

fn three_entry_ready(now:Instant)->(Vec<Session>,World){
    let (a,b,world)=super::tests::visible_pair(now);let mut c=b.clone();c.id=3;
    let mut sessions=vec![a,b,c];
    for (index,s) in sessions.iter_mut().enumerate() {
        let original=s.identity.as_ref().unwrap();
        s.identity=Some(Arc::new(crate::identity091::Profile{account_id:format!("gw01-owner-{index}"),database_id:index as i32+1,
            name:format!("player_{index}"),fixture_dir:original.fixture_dir.clone()}));
        s.key=[s.id as u8;16];s.login_peer=peer(32000+s.id as u16);s.login_attempt=Some(LoginAttempt::new(s.key,s.id,s.login_peer));
        s.base_peer=Some(peer(34000+s.id as u16));s.sync_mask=7;s.arena_base=false;let c=s.shared.as_mut().unwrap();c.phase=Phase::Account;c.join_requested=true;
        c.hangar_since=Some(now-Duration::from_secs(3));
    }
    (sessions,World::new(world.id,now).unwrap())
}

#[test]
fn gw01_arena_takes_only_its_places_and_starts_with_a_hangar_session_present(){
    let now=Instant::now();let (sessions,world)=three_entry_ready(now);assert_eq!(world.expected_actors(),2);
    let mut old=Table{capacity:3,sessions:sessions.clone(),..Table::default()};let mut old_world=world.clone();
    assert!(old.sessions.iter().all(|s|entry_ready(s,now)));
    let result=attach_waiting_sessions(&mut old,&mut old_world,now);
    let overfilled=result.is_err()||old_world.actors.len()>old_world.expected_actors();
    assert!(overfilled,"old path cannot hold a third ready session outside the arena");
    let mut table=split(256);table.sessions=sessions;let mut world=world;
    attach_waiting_sessions(&mut table,&mut world,now).unwrap();
    assert_eq!(world.actors.len(),2);
    assert!(!world.actors.iter().any(|a|a.session==Some(3)),"the third session stays in the hangar");
    assert!(table.arena_ready(&world,now));
    assert_ne!(table.sessions.len(),world.expected_actors(),"old start barrier would never fire here");
    // An attached session that is no longer entry-ready blocks the start.
    table.sessions[0].shared.as_mut().unwrap().join_requested=false;assert!(!table.arena_ready(&world,now));
}

#[test]
fn gw01_without_split_the_arena_gate_is_the_old_table_bound(){
    let now=Instant::now();let (sessions,world)=three_entry_ready(now);
    let table=Table{capacity:3,sessions,..Table::default()};
    assert!(table.arena_admission_open(&[],&world));
}
