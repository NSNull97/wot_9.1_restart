use super::*;
use crate::{p06t_device_caps::{Device,Profile},p06t_device_state::{self as devices,State as Devices},p06t_lab_proxy::Target,p06t_shells091::{self as source,Mount}};
fn actor()->model::Actor {
    actor_kind(VehicleKind::Ms1)
}
fn actor_kind(kind:VehicleKind)->model::Actor {
    let now=Instant::now();let mut w=World::new_for_vehicle(6961,now,crate::map_profile091::MapId::Prohorovka,kind).unwrap();
    w.attach(model::Identity{account:"p06t-control".into(),database:6961,name:"controls".into()},6961).unwrap();
    let mut a=w.actors[0].clone();a.ready=true;a.input=model::Input{throttle:1,steer:1,speed_percent:100};a
}
#[test] fn p06t_scene_critical_engine_and_driver_compound_before_valid_control_quantization() {
    let mut a=actor_kind(VehicleKind::T34);let mut state=Devices::new(Profile::T34);
    let apply=|state:&mut Devices,shot,target|state.apply_hits(&[devices::ModuleHit{
        cause:devices::Cause{shot,attacker_slot:1},ordinal:0,at_ms:0,target,
        shell:source::profile(Mount::Ms1Stock).shots[0],ignition_roll:0.9}],devices::Health{hp:400,max_hp:400,terminal:false}).unwrap();
    apply(&mut state,1,Target::Device(Device::Engine));apply(&mut state,2,Target::Device(Device::Engine));
    assert_eq!(state.health()[0],5);assert_eq!(state.capabilities().drive_scale,0.5);
    a.devices=Some(state.clone());assert_eq!(actor_input(&a,1000,true).unwrap().speed_percent,50);
    apply(&mut state,3,Target::Seat(2));assert_eq!(state.capabilities().drive_scale,0.25);
    a.devices=Some(state);
    for tick in 1000..1008 {let input=actor_input(&a,tick,true).unwrap();assert_eq!(input.speed_percent,25);assert!(legal(input));}
    a.devices=Some(Devices::new(Profile::Ms1));assert!(actor_input(&a,1000,true).is_err());
}
fn damaged(target:Target)->Devices {
    let mut s=Devices::new(Profile::Ms1);s.apply_hits(&[devices::ModuleHit{
        cause:devices::Cause{shot:1,attacker_slot:1},ordinal:0,at_ms:0,target,
        shell:source::profile(Mount::Ms1Stock).shots[0],ignition_roll:0.9}],devices::Health{hp:90,max_hp:90,terminal:false}).unwrap();s
}
fn legal(input:Input)->bool {(-1..=1).contains(&input.throttle)&&(-1..=1).contains(&input.steer)
    &&(!input.brake||input.throttle==0&&input.steer==0)
    &&(input.speed_percent==100||input.speed_percent==50&&!input.brake&&input.throttle!=0||input.speed_percent==25&&!input.brake&&input.throttle==1)}
#[test] fn p06t_scene_healthy_and_legacy_controls_remain_exact_and_all_terminal_gates_stop() {
    let mut a=actor();
    for (throttle,speed) in [(0,100),(1,100),(1,50),(1,25),(-1,100),(-1,50)] {
        for steer in -1..=1 {
            a.input=model::Input{throttle,steer,speed_percent:speed};
            let expected=Input{throttle,steer,brake:throttle==0&&steer==0,speed_percent:speed};
            assert_eq!(actor_input(&a,1000,true).unwrap(),expected);
            a.devices=Some(Devices::new(Profile::Ms1));assert_eq!(actor_input(&a,1000,true).unwrap(),expected);a.devices=None;
        }
    }
    assert_eq!(actor_input(&a,1000,false).unwrap(),Input::STOP);
    a.session=None;assert_eq!(actor_input(&a,1000,true).unwrap(),Input::STOP);a.session=Some(6961);
    a.ready=false;assert_eq!(actor_input(&a,1000,true).unwrap(),Input::STOP);a.ready=true;
    a.health=0;assert_eq!(actor_input(&a,1000,true).unwrap(),Input::STOP);a.health=90;
    let mut dead=damaged(Target::Seat(0));dead.apply_hits(&[devices::ModuleHit{cause:devices::Cause{shot:2,attacker_slot:1},
        ordinal:0,at_ms:0,target:Target::Seat(1),shell:source::profile(Mount::Ms1Stock).shots[0],ignition_roll:0.9}],devices::Health{hp:90,max_hp:90,terminal:false}).unwrap();
    a.devices=Some(dead);assert_eq!(a.health,90);assert_eq!(actor_input(&a,1000,true).unwrap(),Input::STOP);
}
#[test] fn p06t_scene_destroyed_engine_tracks_and_driver_reduce_actual_ipc_controls() {
    for target in [Target::Device(Device::Engine),Target::Device(Device::LeftTrack),Target::Device(Device::RightTrack)] {
        let mut a=actor();a.devices=Some(damaged(target));
        for tick in 1000..1008 {assert_eq!(actor_input(&a,tick,true).unwrap(),Input::STOP);}
    }
    let mut a=actor();a.devices=Some(damaged(Target::Seat(1)));
    let rows=(1000..1004).map(|tick|actor_input(&a,tick,true).unwrap()).collect::<Vec<_>>();
    assert_eq!(rows.iter().map(|r|r.speed_percent).collect::<Vec<_>>(),[50;4]);
    assert_eq!(rows.iter().map(|r|r.steer).collect::<Vec<_>>(),[1,1,0,0]);
    a.input.speed_percent=50;assert_eq!(actor_input(&a,1000,true).unwrap().speed_percent,25);
    a.input.speed_percent=25;assert_eq!(actor_input(&a,1000,true).unwrap().speed_percent,25);
    a.input=model::Input{throttle:-1,steer:-1,speed_percent:50};
    let reverse=(1000..1004).map(|tick|actor_input(&a,tick,true).unwrap()).collect::<Vec<_>>();
    assert_eq!(reverse.iter().map(|r|r.throttle).collect::<Vec<_>>(),[-1,-1,0,0]);
    assert_eq!(reverse.iter().map(|r|r.speed_percent).collect::<Vec<_>>(),[50,50,100,100]);
    assert!(rows.into_iter().chain(reverse).all(legal));
}
fn resources()->Vec<super::super::super::profile13_templates::Resources> {
    let root=std::path::PathBuf::from(std::env::var_os("WOT091_ROOT").unwrap_or_else(||"D:/WoT_9.1_Server".into())).join("local");
    let path=root.join("evidence/20261016-p04m-runtime01/domain-fixture01/battle-profiles-five.json");
    assert_eq!(format!("{:x}",sha2::Sha256::digest(fs::read(&path).unwrap())),"b7f272aace7a7746643bf00f0a49d343931d139477765ab30fcacbbf24c668e4");
    super::super::super::profile13_templates::load(&root,&path).unwrap()
}
#[test] fn p06t_actual_scene_destroyed_engine_stays_parked_while_same_worker_healthy_actor_moves() {
    let rows=resources();let now=Instant::now();let template=BattleTemplate::from_shared(&rows,2,6962,now).unwrap();
    let mut world=template.world.clone();world.lifecycle=None;
    for slot in 0..2 {
        world.attach(model::Identity{account:format!("p06t-physical-{slot}"),database:6962+slot as i32,name:format!("physical{slot}")},6962+slot as u32).unwrap();
        world.actors[slot].devices=Some(Devices::new(Profile::Ms1));
    }
    world.actors[0].devices=Some(damaged(Target::Device(Device::Engine)));world.start(now).unwrap();
    let mut runtime=BatchRuntime::new(rows[0].shared.clone().unwrap(),rows[0].catalog.1.clone());runtime.start(&mut world,now).unwrap();
    let limit=Instant::now()+Duration::from_secs(120);
    while !runtime.ready_for_native() {runtime.step(&mut world,Instant::now()).unwrap();assert!(Instant::now()<limit);std::thread::sleep(Duration::from_millis(1));}
    let pid=runtime.runtime.as_ref().unwrap().process_id();let origins=world.actors.iter().map(|a|a.position).collect::<Vec<_>>();
    for slot in 0..2 {world.set_ready(slot,6962+slot as u32).unwrap();world.actors[slot].input=model::Input{throttle:1,steer:0,speed_percent:100};}
    let base=Instant::now();
    for frame in 1..=60 {
        let before=world.tick;let at=base+Duration::from_millis(frame*100);let limit=Instant::now()+Duration::from_secs(120);
        loop {runtime.step(&mut world,at).unwrap();if world.tick>before&&!runtime.blocked(){break;}
            assert!(Instant::now()<limit);std::thread::sleep(Duration::from_millis(1));}
        assert_eq!(runtime.runtime.as_ref().unwrap().process_id(),pid);
        assert_eq!(actor_input(&world.actors[0],world.tick,true).unwrap(),Input::STOP);
    }
    let moved=|slot:usize|(0..3).map(|i|(f64::from(world.actors[slot].position[i])-f64::from(origins[slot][i])).powi(2)).sum::<f64>().sqrt();
    assert!(moved(1)>3.,"healthy actual Jolt actor must move: {}",moved(1));
    assert!(moved(0)<0.5,"destroyed engine must remain physically parked (settling allowed): {}",moved(0));
    assert!(world.actors.iter().all(|a|a.health==90));
}
