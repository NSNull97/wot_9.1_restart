//! ARENA-01: arena ids, routing and the step boundary. Synthetic worlds; no
//! native client or Jolt process is claimed here.
use super::*;

fn arena(index:usize,world:World)->Arena {
    let template=BattleTemplate::new(&world,&None);Arena::new(index,world,None,template)
}
fn started(id:u64,now:Instant)->World {let mut w=model::tests::world(now);w.id=id;w}

#[test]
fn arena01_ids_are_disjoint_positive_i64_and_bounded_to_four_arenas(){
    for random in [0,1,u64::MAX,ARENA_ID_STRIDE-1,ARENA_ID_STRIDE,0x1234_5678_9abc_def0] {
        for count in 1..=4 {
            let ids=arena_ids(count,random).unwrap();assert_eq!(ids.len(),count);
            assert!(ids.iter().all(|id|*id>=1&&*id<=i64::MAX as u64));
            // Each arena counts up by one per battle inside its own 2^56 range.
            for pair in ids.windows(2) {assert_eq!(pair[1]-pair[0],ARENA_ID_STRIDE);}
        }
    }
    assert!(arena_ids(0,7).is_err());assert!(arena_ids(5,7).is_err());
}

#[test]
fn arena01_one_arena_routes_every_session_to_arena_zero(){
    let now=Instant::now();let arenas=vec![arena(0,started(11,now))];
    let s=Session::new(99,[9;16],"127.0.0.1:39999".parse().unwrap(),now);
    assert_eq!(arena_of(&s,&arenas),Some(0));assert_eq!(lobby(&arenas,&Table::default(),&[]),0);
    assert!(attached_outside(&arenas,0).is_empty());
}

#[test]
fn arena01_sessions_route_by_actor_and_view_hangar_goes_to_the_open_arena(){
    let now=Instant::now();
    let mut idle=World::new(21,now).unwrap();idle.set_expected_actors(2).unwrap();
    let arenas=vec![arena(0,started(11,now)),arena(1,idle)];
    let table=Table{arena_split:true,capacity:16,multi_arena:true,..Table::default()};
    // Arena 0 is running: the next Join goes to arena 1.
    assert_eq!(lobby(&arenas,&table,&[]),1);
    let fighter=Session::new(1,[1;16],"127.0.0.1:39001".parse().unwrap(),now);
    assert_eq!(arena_of(&fighter,&arenas),Some(0),"actor of arena 0");
    let mut watcher=Session::new(5,[5;16],"127.0.0.1:39005".parse().unwrap(),now);
    watcher.shared=Some(Client::new(0));watcher.shared.as_mut().unwrap().view=Some(arenas[0].world.clone());
    assert_eq!(arena_of(&watcher,&arenas),Some(0),"a detached avatar still shows arena 0");
    let hangar=Session::new(7,[7;16],"127.0.0.1:39007".parse().unwrap(),now);
    assert_eq!(arena_of(&hangar,&arenas),None);assert_eq!(home(&hangar,&arenas,1),1);
    assert_eq!(attached_outside(&arenas,1),vec![1,2]);assert!(attached_outside(&arenas,0).is_empty());
}

#[test]
fn arena01_failed_step_stays_in_its_arena_while_the_other_steps_on_its_thread(){
    let now=Instant::now();
    // Arena 1's clock is ahead of the step: World::advance refuses (a real
    // fail-closed path), arena 0 advances normally in the same parallel step.
    let broken=started(22,now+Duration::from_secs(10));
    let mut arenas=vec![arena(0,started(11,now)),arena(1,broken)];
    let at=now+Duration::from_millis(300);
    let events=step_all(&mut arenas,&[Some(Command::Step{now:at,start:false}),Some(Command::Step{now:at,start:false})]);
    assert!(matches!(events[0],Some(Event::Stepped)));
    assert!(matches!(&events[1],Some(Event::Failed{stage:"world_step",..})));
    assert!(arenas[0].world.tick>1000,"healthy arena advanced");assert_eq!(arenas[1].world.id,22);
    // A command-less arena is not stepped at all.
    let events=step_all(&mut arenas,&[None,Some(Command::Step{now:at,start:false})]);
    assert!(events[0].is_none());
}

#[test]
fn arena01_unstarted_arenas_step_inline_and_start_flag_counts_as_work(){
    let now=Instant::now();
    let mut a=World::new(31,now).unwrap();a.set_expected_actors(2).unwrap();
    let mut b=World::new(32,now).unwrap();b.set_expected_actors(2).unwrap();
    let mut arenas=vec![arena(0,a),arena(1,b)];
    let events=step_all(&mut arenas,&[Some(Command::Step{now,start:false}),Some(Command::Step{now,start:false})]);
    assert!(events.iter().all(|e|matches!(e,Some(Event::Stepped))));
    // Start without a full roster fails closed in that arena only.
    let events=step_all(&mut arenas,&[Some(Command::Step{now,start:true}),Some(Command::Step{now,start:false})]);
    assert!(matches!(events[0],Some(Event::Failed{..})));assert!(matches!(events[1],Some(Event::Stepped)));
    assert!(arenas.iter().all(|a|!a.started()));
}
