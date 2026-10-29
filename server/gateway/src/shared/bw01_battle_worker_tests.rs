//! BW-01: arenas stepped by real worker processes of this test binary (the
//! ignored entry test is the worker). Synthetic reservations and worlds, no
//! native client and no Jolt scene (real scenes: `bw01_real_scene_*` below).
use super::*;
use super::queue_loss_tests::{reserved,world};
use super::arena01_dispatch_tests::{reserved_in,waiting};
use battle_worker::tests::{kill,settings};

const OWNER:u32=11;const HANGAR:u32=13;

fn session(table:&mut Table,id:u32)->&mut Session {table.sessions.iter_mut().find(|s|s.id==id).unwrap()}
fn seat(a:&mut arena::Arena,table:&mut Table,id:u32)->usize {
    let s=session(table,id);let frozen=state(s).unwrap().reservation_loss.clone().unwrap().frozen;
    let owner=s.identity.clone().unwrap();
    a.world.attach_owned_loss(model::Identity{account:owner.account_id.clone(),database:owner.database_id,name:owner.name.clone()},id,&frozen).unwrap()
}
/// The second place of a two-place battle: a copy of the seated owner's actor
/// under another account, without a session (a participant already gone).
fn second_place(a:&mut arena::Arena) {
    let mut x=a.world.actors[0].clone();
    x.identity=model::Identity{account:format!("{}-second",x.identity.account),database:x.identity.database+1000,name:"second".into()};
    x.session=None;a.world.actors.push(x);
}
fn remote(mut a:arena::Arena)->arena::Arena {a.worker=Some(Box::new(battle_worker::Remote::new(settings())));a}
/// Codec bytes of a World from a fresh resource table: equal bytes = equal state.
fn bytes(w:&World,anchor:Instant)->Vec<u8> {crate::bw_wire::encode(w,anchor,&mut crate::bw_wire::Arcs::new(false)).unwrap()}
fn step(arenas:&mut [arena::Arena],commands:&[Option<arena::Command>])->Vec<Option<arena::Event>> {battle_worker::step_all(arenas,commands)}

#[test]
fn bw01_worker_steps_match_in_process_steps(){
    // The same started World, the same instants and inputs: one copy steps in
    // this process, the other in a worker. After every step both are byte-equal.
    let now=Instant::now();
    let w=model::tests::world(now);let t=BattleTemplate::new(&w,&None);
    let mut local=arena::Arena::new(0,w.clone(),None,t.clone());
    let mut far=[remote(arena::Arena::new(0,w,None,t))];
    for k in 1..=60u32 {
        let at=now+Duration::from_millis(37*u64::from(k));
        let input=model::Input{throttle:if k%20<12{1}else{-1},steer:[0,1,-1][k as usize%3],speed_percent:100};
        local.world.actors[0].input=input;far[0].world.actors[0].input=input;
        let command=arena::Command::Step{now:at,start:false};
        assert!(matches!(local.handle(command),arena::Event::Stepped));
        let events=step(&mut far,&[Some(command)]);
        assert!(matches!(events[0],Some(arena::Event::Stepped)),"{:?}",events[0]);
        assert_eq!(bytes(&local.world,now),bytes(&far[0].world,now),"step {k}: worker World differs from in-process World");
    }
    assert!(local.world.tick>1000&&local.world.actors[0].position!=model::tests::world(now).actors[0].position,"the battle moved");
    let w=far[0].worker.as_ref().unwrap();
    assert_eq!(w.steps,60);assert!(w.frame_bytes.0>0&&w.frame_bytes.1>0);
}

#[test]
fn bw01_killed_worker_contains_only_its_battle_and_the_next_battle_starts_a_new_worker(){
    let now=Instant::now();
    let r=reserved(now).1;let first=r.battle;
    let mut other=model::tests::world(now);other.id=first+arena::ARENA_ID_STRIDE;
    let mut arenas:Vec<arena::Arena>=[world(&r,now),other].into_iter().enumerate()
        .map(|(i,w)|{let t=BattleTemplate::new(&w,&None);remote(arena::Arena::new(i,w,None,t))}).collect();
    let mut table=Table{sessions:vec![reserved_in(now,OWNER,first),waiting(now,HANGAR)],
        capacity:256,arena_split:true,multi_arena:true,..Table::default()};
    seat(&mut arenas[0],&mut table,OWNER);second_place(&mut arenas[0]);
    // Battle starts in the worker; both arenas step through their own workers.
    let start=[Some(arena::Command::Step{now,start:true}),Some(arena::Command::Step{now,start:false})];
    let events=step(&mut arenas,&start);
    assert!(events.iter().all(|e|matches!(e,Some(arena::Event::Stepped))),"{events:?}");
    assert!(arenas[0].world.started.is_some(),"started inside the worker");
    for k in 1..=5u64 {
        let at=now+Duration::from_millis(100*k);
        let events=step(&mut arenas,&[Some(arena::Command::Step{now:at,start:false});2]);
        assert!(events.iter().all(|e|matches!(e,Some(arena::Event::Stepped))),"{events:?}");
    }
    let tick=arenas[0].world.tick;assert!(tick>1000,"battle advanced in the worker");
    let other_pid=arenas[1].worker.as_ref().unwrap().pid().unwrap();
    let hangar=session(&mut table,HANGAR).clone();
    // kill -9 the battle worker of arena 0 in the middle of the battle.
    let killed=kill(&arenas[0]);
    let at=now+Duration::from_millis(700);
    let events=step(&mut arenas,&[Some(arena::Command::Step{now:at,start:false});2]);
    let Some(arena::Event::Failed{stage,error})=&events[0] else {panic!("lost worker must fail the step: {events:?}")};
    assert_eq!(*stage,"battle_worker_lost","{error}");
    assert!(matches!(events[1],Some(arena::Event::Stepped)),"the other arena's worker is untouched");
    assert_eq!(arenas[1].worker.as_ref().unwrap().pid(),Some(other_pid));
    assert!(arenas[0].worker.as_ref().unwrap().pid().is_none(),"lost link dropped");
    // The service loop's path: STAB-02 containment of arena 0 only.
    let mut dispatcher=Dispatcher::default();
    let error=io::Error::new(io::ErrorKind::BrokenPipe,format!("{error}"));
    containment::contain_arena(&mut table,&mut dispatcher,&mut arenas[0],at,stage,Some("fault_battle_worker"),&error);
    for id in [OWNER] {
        let s=session(&mut table,id);
        assert!(state(s).unwrap().pending_return_loss.is_some(),"{id}: reservation goes back through the writer (hangar return)");
        assert!(!s.shared.as_ref().unwrap().join_requested);
    }
    assert_eq!(arenas[0].world.id,first+1,"arena 0 reset to its next battle");
    assert!(arenas[0].closed.is_none()&&arenas[0].world.actors.is_empty());
    let kept=session(&mut table,HANGAR);
    assert_eq!(state(kept).unwrap(),state(&mut hangar.clone()).unwrap(),"hangar session unchanged");
    // Repeat battle on the reset arena: a new worker process, a new start.
    let mut table2=Table{sessions:vec![reserved_in(now,21,first+1)],capacity:256,arena_split:true,..Table::default()};
    seat(&mut arenas[0],&mut table2,21);second_place(&mut arenas[0]);
    let at=now+Duration::from_millis(900);
    let events=step(&mut arenas,&[Some(arena::Command::Step{now:at,start:true}),Some(arena::Command::Step{now:at,start:false})]);
    assert!(events.iter().all(|e|matches!(e,Some(arena::Event::Stepped))),"{events:?}");
    let pid=arenas[0].worker.as_ref().unwrap().pid().unwrap();
    assert_ne!(pid,killed,"a new worker process");
    assert!(arenas[0].world.started.is_some()&&arenas[0].world.id==first+1);
    let events=step(&mut arenas,&[Some(arena::Command::Step{now:at+Duration::from_millis(200),start:false});2]);
    assert!(events.iter().all(|e|matches!(e,Some(arena::Event::Stepped))),"{events:?}");
    assert!(arenas[0].world.tick>1000,"the repeat battle advances");
}

#[test]
fn bw01_step_error_inside_the_worker_is_the_ordinary_step_failure(){
    // A World the step refuses (start without its roster) fails in the
    // worker as it fails in process: stage world_step, the World comes back.
    let now=Instant::now();
    let w=World::new(77,now).unwrap();let t=BattleTemplate::new(&w,&None);
    let mut local=arena::Arena::new(0,w.clone(),None,t.clone());
    let mut far=[remote(arena::Arena::new(0,w,None,t))];
    let command=arena::Command::Step{now,start:true};
    let arena::Event::Failed{stage:a,..}=local.handle(command) else {panic!("refused in process")};
    let events=step(&mut far,&[Some(command)]);
    let Some(arena::Event::Failed{stage:b,..})=&events[0] else {panic!("refused in worker: {events:?}")};
    assert_eq!((a,*b),("world_step","world_step"));
    assert_eq!(bytes(&local.world,now),bytes(&far[0].world,now));
    assert!(far[0].worker.as_ref().unwrap().pid().is_some(),"a step error is not a lost worker");
}

#[test]
fn bw01_idle_arena_ships_nothing_after_its_first_exchange(){
    let now=Instant::now();
    let w=World::new(78,now).unwrap();let t=BattleTemplate::new(&w,&None);
    let mut far=[remote(arena::Arena::new(0,w,None,t))];
    let idle=[Some(arena::Command::Step{now,start:false})];
    assert!(matches!(step(&mut far,&idle)[0],Some(arena::Event::Stepped)));
    let w=far[0].worker.as_ref().unwrap();assert_eq!(w.steps,1,"a new worker takes the resources once");
    for _ in 0..10 {assert!(matches!(step(&mut far,&idle)[0],Some(arena::Event::Stepped)));}
    assert_eq!(far[0].worker.as_ref().unwrap().steps,1,"an unstarted World without a start is a no-op in any process");
}

#[test]
fn bw01_turret01_jolt_flight_to_rest_is_the_same_in_process_and_in_the_worker(){
    // An actual rack detonation in a Jolt-turret World: the flight first awaits
    // its trajectory, then plays it to rest. No scene runtime here, so the test
    // installs one SYNTHETIC worker trajectory into both copies at the same step;
    // the real Jolt body through a worker is `turret01_detached_bodies_in_real_jolt_scene`
    // with TURRET01_WORKER=1. After every step both Worlds are byte-equal.
    use super::super::super::super::ammo_detonation::{FlightPhase,JointPose,Trajectory};
    let now=Instant::now();
    let(w,start)=World::turret01_jolt_detonation_for_test(now);let anchor=now;let born=w.turret_flights()[0].event().joint();
    let launch=w.turret_flights()[0].launch().unwrap();
    let t=BattleTemplate::new(&w,&None);
    let mut local=arena::Arena::new(0,w.clone(),None,t.clone());
    let mut far=[remote(arena::Arena::new(0,w,None,t))];
    let samples:Vec<JointPose>=(0..12).map(|i|{let k=(i.min(9)) as f32;
        JointPose{position:[born.position[0]+0.3*k,born.position[1]+1.2*k-0.15*k*k,born.position[2]+0.2*k],direction:[0.1*k,0.05*k,0.]}}).collect();
    let trajectory=Trajectory{samples,slept:true};
    for k in 1..=40u32 {
        if k==5 {
            assert!(local.world.turret_flights()[0].awaiting_trajectory()&&far[0].world.turret_flights()[0].awaiting_trajectory());
            local.world.install_turret_trajectory(1,trajectory.clone()).unwrap();far[0].world.install_turret_trajectory(1,trajectory.clone()).unwrap();
        }
        let command=arena::Command::Step{now:start+Duration::from_millis(100*u64::from(k)),start:false};
        let e=local.handle(command);assert!(matches!(e,arena::Event::Stepped),"step {k}: {e:?}");
        let events=step(&mut far,&[Some(command)]);
        assert!(matches!(events[0],Some(arena::Event::Stepped)),"{:?}",events[0]);
        assert_eq!(bytes(&local.world,anchor),bytes(&far[0].world,anchor),"step {k}: worker World differs from in-process World");
    }
    let f=&far[0].world.turret_flights()[0];
    assert_eq!(f.launch(),Some(launch));assert_eq!(f.trajectory(),Some(&trajectory));
    assert_eq!(f.sample().phase,FlightPhase::Resting,"the body came to rest");
    assert_eq!(f.sample().position,trajectory.samples.last().unwrap().position);
    assert_eq!(far[0].worker.as_ref().unwrap().steps,40);
}
