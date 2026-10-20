//! NOT_RUN candidate until root's P10B canonical gateway/Jolt gate.
//! Actual resource7 is reused; these are valid old source actors, no fake Pool.
use super::*;
use super::super::super::{p10b_team_plan::TeamPlan,lifecycle,profile13_templates};

#[test]fn p10b_explicit_lane_keeps_default_actor_rows_byte_exact_and_slot_identity_separate(){
    let rows=profile13_templates::extended_test_resources();let shared=rows[0].shared.as_ref().unwrap();
    for slot in 0..6 {for kind in VehicleKind::SUPPORTED{
        let default=BatchRuntime::actor_manifest(shared,slot,kind,3).unwrap();
        let explicit=BatchRuntime::actor_manifest_for_lane(shared,slot,kind,3,slot).unwrap();
        assert_eq!(serde_json::to_vec(&default).unwrap(),serde_json::to_vec(&explicit).unwrap());
    }}
    let plan=TeamPlan::new(&[1,1,1,2]).unwrap();
    for slot in 0..4{let lane=plan.lane(slot).unwrap();let row=BatchRuntime::actor_manifest_for_lane(shared,slot,VehicleKind::Ms1,1,lane).unwrap();
        let map=&shared.maps[0];assert_eq!(row["slot"],slot);assert_eq!(row["spawn_origin"][0],map.spawn[0]+if lane%2==0{-4.}else{4.});
        assert_eq!(row["spawn_origin"][2],map.spawn[2]-12.*(lane/2)as f32);
    }
    assert!(BatchRuntime::actor_manifest_for_lane(shared,0,VehicleKind::Ms1,1,6).is_err());
}

#[test]fn p10b_three_one_and_one_three_actual_one_scene_scalar_and_prepared_ACK_keep_identity_teams(){
    let resources=profile13_templates::extended_test_resources();let shared=resources[0].shared.clone().unwrap();
    for(index,teams)in[[1,1,1,2],[1,2,2,2]].into_iter().enumerate(){
        let now=Instant::now();
        // Existing old5 source rows are an actual validated subset of resource7;
        // the shared worker/artifacts and each actor's config remain genuine.
        let template=BattleTemplate::from_shared(&resources[..5],4,31100+index as u64,now).unwrap();let mut world=template.world.clone();
        let mut rules=lifecycle::Rules::prohorovka();rules.prebattle_ms=1000;
        world.lifecycle=Some(lifecycle::State::new(rules).unwrap());
        let plan=TeamPlan::new(&teams).unwrap();world.set_team_plan(plan.clone()).unwrap();
        let kinds=[VehicleKind::Ms1,VehicleKind::Is7,VehicleKind::Ms1,VehicleKind::Is7];
        for(slot,kind)in kinds.into_iter().enumerate(){let(identity,loadout)=model::tests::profile13_loadout(kind,slot,9);
            assert_eq!(world.attach_owned(identity,slot as u32+1,&loadout).unwrap(),slot);}
        world.start(now).unwrap();let mut runtime=BatchRuntime::new(shared.clone(),resources[0].catalog.1.clone());runtime.start(&mut world,now).unwrap();
        let deadline=Instant::now()+Duration::from_secs(120);
        loop{runtime.step(&mut world,Instant::now()).unwrap();if runtime.ready_for_native(){break;}
            assert!(Instant::now()<deadline,"P10B genuine scene startup deadline");std::thread::sleep(Duration::from_millis(1));}
        let spec=runtime.spec.as_ref().unwrap();assert_eq!(spec.actors.len(),4);
        for slot in 0..4{let lane=plan.lane(slot).unwrap();let source=&shared.maps[kinds[slot].index()];
            assert_eq!(spec.actors[slot].slot,slot);assert_eq!(spec.actors[slot].config_sha256,source.config_sha256);
            assert_eq!(spec.actors[slot].spawn,[source.spawn[0]+if lane%2==0{-4.}else{4.},source.spawn[1],source.spawn[2]-12.*(lane/2)as f32]);
            world.set_ready(slot,slot as u32+1).unwrap();world.actors[slot].input=model::Input{throttle:1,steer:0,speed_percent:100};
        }
        let pid=runtime.runtime.as_ref().unwrap().process_id();let mut barriers=0;let base=Instant::now();
        for frame in 1..=120{
            world.advance_lifecycle(now+Duration::from_millis(frame*100)).unwrap();
            if world.lifecycle.as_ref().unwrap().allows_actions(){
                for actor in &mut world.actors{actor.input=model::Input{throttle:1,steer:0,speed_percent:100};}
            }
            let at=base+Duration::from_millis(frame*100);let before=world.tick;let scene=world.scene_version();let mut staged=false;
            let deadline=Instant::now()+Duration::from_secs(120);
            loop{runtime.step(&mut world,at).unwrap();
                if runtime.staged.is_some(){assert_eq!(world.scene_version(),scene);
                    assert!(!runtime.runtime.as_ref().unwrap().prepared_ids().is_empty());if !staged{barriers+=1;staged=true;}}
                if world.tick>before&&!runtime.blocked(){break;}
                assert!(Instant::now()<deadline,"P10B original scalar/World/prepared ACK deadline");std::thread::sleep(Duration::from_millis(1));
            }
            assert_eq!(runtime.runtime.as_ref().unwrap().process_id(),pid);assert_eq!(world.team_plan(),Some(&plan));
            assert_eq!((0..4).map(|s|world.team(s).unwrap()).collect::<Vec<_>>(),teams);
            assert_eq!(world.actors.iter().map(|a|a.identity.database).collect::<Vec<_>>(),[1,2,3,4]);
            assert_eq!(runtime.runtime.as_ref().unwrap().scene().ids,world.fragiles.as_ref().unwrap().removed_ids());
        }
        assert!(barriers>0&&world.scene_version()>0,"at least one actual source catalog fracture must commit through prepared ACK");
        for event in &world.fragiles.as_ref().unwrap().vehicle_events {
            let proof=event.proof.as_ref().unwrap();assert_eq!(proof.frame.context.slot,event.shooter);
            assert_eq!(proof.frame.context.session,event.shooter as u32+1);assert_eq!(proof.receipt().unwrap().object_id,event.object_id);
        }
        runtime.runtime.take().unwrap().shutdown().unwrap();
    }
}
