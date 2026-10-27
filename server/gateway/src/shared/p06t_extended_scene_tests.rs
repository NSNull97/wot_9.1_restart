//! Genuine resources7 + canonical C# IPC7 + original scalar verifier + World
//! staged scene ACK. The explicit LAB loadout never fabricates owned inventory.
use super::*;
use std::time::{SystemTime,UNIX_EPOCH};
const KINDS:[VehicleKind;6]=[VehicleKind::Wt128,VehicleKind::Fv183,VehicleKind::Ms1,VehicleKind::Is7,VehicleKind::T26,VehicleKind::T34];
const ROOT_DLL_SHA:&str="39900645b1bab6819e47e140add661e7f0c5ab4c7a04992a6f5501f3881f2cfa";
fn resources()->Vec<super::super::super::profile13_templates::Resources>{super::super::super::profile13_templates::extended_test_resources()}

#[test] fn p06t_extended_scene3_rows_require_explicit_resource4_and_exact_source_profile() {
    let rows=resources();let shared=rows[0].shared.as_ref().unwrap();
    for kind in VehicleKind::SUPPORTED {
        let row=BatchRuntime::actor_manifest(shared,kind.index()%wire::MAX_NATIVE_ACTORS,kind,3).unwrap();
        assert_eq!(row.as_object().unwrap().len(),6);assert_eq!(row["kind"],kind.label());
        assert_eq!(row["config"]["sha256"],shared.maps[kind.index()].config_sha256);
        if kind.index()<2 {assert!(row["source_profile"].is_null());}
        else {assert_eq!(row["source_profile"]["sha256"],ram_proof::Profile::for_vehicle(kind).sha());}
        if kind.is_extended(){for version in [1,2]{assert!(BatchRuntime::actor_manifest(shared,0,kind,version).is_err());}}
    }
    let mut wrong=(**shared).clone();wrong.version=3;assert!(BatchRuntime::actor_manifest(&wrong,0,VehicleKind::Wt128,3).is_err());
    wrong=(**shared).clone();wrong.source_profiles[VehicleKind::Fv183.index()].as_mut().unwrap().1="a".repeat(64);
    assert!(BatchRuntime::actor_manifest(&wrong,5,VehicleKind::Fv183,3).is_err());
    assert!(BatchRuntime::profile(scene_worker::Kind::WtE100128,false).is_err());
    assert!(BatchRuntime::profile(scene_worker::Kind::Fv215b183,false).is_err());
    assert_eq!(BatchRuntime::profile(scene_worker::Kind::WtE100128,true).unwrap(),ram_proof::Profile::WtE100128);
    assert_eq!(BatchRuntime::profile(scene_worker::Kind::Fv215b183,true).unwrap(),ram_proof::Profile::Fv215b183);
}

#[test] fn p06t_extended_actual_mixed_six_world_keeps_scalar_profiles_and_commits_one_scene_ack() {
    let rows=resources();let shared=rows[0].shared.clone().unwrap();let now=Instant::now();
    assert_eq!(format!("{:x}",sha2::Sha256::digest(fs::read(shared.artifacts.executable.with_extension("dll")).unwrap())),ROOT_DLL_SHA);
    let template=BattleTemplate::from_shared_mode(&rows,6,11706,now,Some(VehicleKind::Wt128)).unwrap();
    let mut world=template.world.clone();assert!(world.extended_lab()&&world.mixed_profiles()&&world.mixed_ammo());assert!(world.lifecycle.is_none());
    let identities=(0..6).map(|slot|model::Identity{account:format!("p06t-lab-physics-{slot}"),database:11700+slot,name:format!("lab-{slot}")}).collect::<Vec<_>>();
    let loadouts=KINDS.map(model::extended::LabLoadout::temporary);
    for (slot,loadout) in loadouts.into_iter().enumerate() {
        assert_eq!(world.attach_extended_lab(identities[slot].clone(),5000+slot as u32,loadout).unwrap(),slot);
        assert_eq!(world.actors[slot].vehicle_kind(),KINDS[slot]);
        assert_eq!(world.actors[slot].devices.as_ref().unwrap().policy_revision(),crate::p06t_device_state::POLICY_V2);
        if KINDS[slot].is_extended(){assert!(!KINDS[slot].battle_admission());assert_eq!(KINDS[slot].initial_ammo(),0);}
    }
    assert_eq!(world.actors[0].devices.as_ref().unwrap().crew().len(),6);assert_eq!(world.actors[1].devices.as_ref().unwrap().crew().len(),5);
    let ammo=world.actors.iter().map(|a|a.fire.ammo()).collect::<Vec<_>>();
    world.start(now).unwrap();let mut runtime=BatchRuntime::new(shared.clone(),rows[0].catalog.1.clone());runtime.start(&mut world,now).unwrap();
    let deadline=Instant::now()+Duration::from_secs(120);
    loop {runtime.step(&mut world,Instant::now()).unwrap();if runtime.ready_for_native(){break;}
        assert!(Instant::now()<deadline,"extended actual startup deadline");std::thread::sleep(Duration::from_millis(1));}
    let pid=runtime.runtime.as_ref().unwrap().process_id();let origins=world.actors.iter().map(|a|a.position).collect::<Vec<_>>();
    let spec=runtime.spec.as_ref().unwrap();
    assert_eq!(spec.actors.iter().map(|a|a.kind.extended_vehicle()).collect::<Vec<_>>(),KINDS);
    assert_eq!(spec.actors[0].kind.profile_sha(),ram_proof::Profile::WtE100128.sha());
    assert_eq!(spec.actors[1].kind.profile_sha(),ram_proof::Profile::Fv215b183.sha());
    for slot in 0..6 {world.set_ready(slot,5000+slot as u32).unwrap();world.actors[slot].input=model::Input{throttle:1,steer:0,speed_percent:100};}
    let base=Instant::now();let mut barriers=0;let mut departed=false;let mut rejoined=false;let mut staged_snapshots=Vec::new();
    for frame in 1..=120 {
        if frame==81 {
            assert!(rejoined,"actual prepared/ACK departure must be exercised before parked-body phase");
            world.detach(9000).unwrap();
            // Test-specified old body death verifies parking in the same scene;
            // this physical test makes no claim about an actual shell death.
            world.actors[4].health=0;world.actors[4].input=model::Input::STOP;
        }
        let at=base+Duration::from_millis(frame*100);let before_tick=world.tick;let before_scene=world.scene_version();
        let deadline=Instant::now()+Duration::from_secs(120);let mut saw_staged=false;
        loop {
            runtime.step(&mut world,at).unwrap();
            if let Some(staged)=&runtime.staged {
                assert_eq!(world.scene_version(),before_scene);assert!(staged.scene_version()>before_scene);assert!(staged.tick>before_tick);
                assert!(!runtime.runtime.as_ref().unwrap().prepared_ids().is_empty());
                if !saw_staged {barriers+=1;staged_snapshots.push(runtime.failure_snapshot());saw_staged=true;}
                if !departed {world.detach(5000).unwrap();departed=true;}
            }
            if world.tick>before_tick&&!runtime.blocked(){break;}
            assert!(Instant::now()<deadline,"extended actual World/ACK deadline");std::thread::sleep(Duration::from_millis(1));
        }
        if departed&&!rejoined {
            assert_eq!(world.actors[0].session,None);let pose=world.actors[0].position;let devices=world.actors[0].devices.clone();
            assert_eq!(world.attach_extended_lab(identities[0].clone(),9000,loadouts[0]).unwrap(),0);
            assert_eq!(world.actors[0].position,pose);assert_eq!(world.actors[0].devices,devices);assert_eq!(world.actors[0].fire.ammo(),ammo[0]);
            assert_eq!(runtime.sessions[0],5000,"physical epoch must not become the rejoined control session");
            world.set_ready(0,9000).unwrap();world.actors[0].input=model::Input{throttle:1,steer:0,speed_percent:100};rejoined=true;
        }
        assert_eq!(runtime.runtime.as_ref().unwrap().process_id(),pid);assert_eq!(world.actors.len(),6);
        assert_eq!(world.actors.iter().map(|a|a.vehicle_kind()).collect::<Vec<_>>(),KINDS);
        assert_eq!(runtime.runtime.as_ref().unwrap().scene().ids,world.fragiles.as_ref().unwrap().removed_ids());
    }
    assert!(departed&&rejoined&&barriers>0);assert!(world.scene_version()>0);assert!(world.actors[1].position[2]>origins[1][2]+5.);
    assert_eq!(world.actors[0].session,None);assert_eq!(world.actors[0].input,model::Input::STOP);assert_eq!(world.actors[4].health,0);
    assert_eq!(world.actors.iter().map(|a|a.fire.ammo()).collect::<Vec<_>>(),ammo);assert!(world.shots.is_empty()&&world.impacts.is_empty());
    let state=world.fragiles.as_ref().unwrap();assert_eq!(state.vehicle_events.len(),world.scene_version()as usize);let mut extended_receipts=0;
    for event in &state.vehicle_events {
        let proof=event.proof.as_ref().unwrap();assert_eq!(proof.frame.proof.profile,ram_proof::Profile::for_vehicle(KINDS[event.shooter]));
        assert_eq!(proof.frame.context.slot,event.shooter);assert_eq!(proof.frame.context.session,5000+event.shooter as u32);
        assert_eq!(proof.receipt().unwrap().object_id,event.object_id);if KINDS[event.shooter].is_extended(){extended_receipts+=1;}
    }
    assert!(extended_receipts>0,"a genuinely extended profile must commit an original scalar receipt through Trace/ACK");
    let stamp=SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let out=shared.root.join(format!("evidence/20261016-p06t-world07/domain-{}-{stamp}",std::process::id()));fs::create_dir(&out).unwrap();
    fs::write(out.join("result.json"),serde_json::to_vec_pretty(&serde_json::json!({"status":"PASS_ACTUAL_WORLD7_MIXED6_SCALAR_TRACE_SCENE_ACK",
        "kinds":KINDS.map(VehicleKind::label),"process_id":pid,"batches":120,"staged_scene_acks":barriers,"committed_scene":world.scene_version(),
        "typed_vehicle_events":state.vehicle_events.len(),"extended_typed_receipts":extended_receipts,"root_worker_sha256":ROOT_DLL_SHA,
        "actual_prepared_disconnect":departed,"same_body_typed_loadout_reattach":rejoined,"world":world.failure_snapshot(),
        "native_owner":"NOT_RUN","owned_inventory":"NOT_RUN"})).unwrap()).unwrap();
    fs::write(out.join("staged-acks.json"),serde_json::to_vec_pretty(&staged_snapshots).unwrap()).unwrap();
    println!("P06T_EXTENDED_DOMAIN_ACCEPTED actors=6 process_id={pid} batches=120 scene={} receipts={extended_receipts} acks={barriers} evidence={}",world.scene_version(),out.display());
    runtime.runtime.take().unwrap().shutdown().unwrap();
}

#[test] fn p06t_extended_v2_template_is_explicit_and_survives_fresh_battle_without_upgrading_old_mode(){
    let rows=resources();let now=Instant::now();
    let old=BattleTemplate::from_shared_mode(&rows,2,11730,now,Some(VehicleKind::Wt128)).unwrap();
    assert!(!old.world.extended_breech_lab());assert!(old.world.failure_snapshot().get("unarmored_device_policy").is_none());
    let v2=BattleTemplate::from_shared_policy(&rows,2,11731,now,Some(VehicleKind::Wt128),true).unwrap();
    assert!(v2.world.extended_breech_lab());
    assert_eq!(v2.world.failure_snapshot()["unarmored_device_policy"],crate::p06t_damage::UNARMORED_DEVICE_POLICY);
    assert!(BattleTemplate::from_shared_policy(&rows,2,11732,now,None,true).is_err());
    assert!(BattleTemplate::from_shared_policy(&rows[..5],2,11732,now,Some(VehicleKind::Ms1),true).is_err());
    let mut world=v2.world.clone();let mut runtime=None;
    world.attach_extended_lab(model::Identity{account:"explicit-v2-lab".into(),database:11731,name:"Lab v2".into()},
        1,model::extended::LabLoadout::temporary(VehicleKind::Wt128)).unwrap();
    assert_eq!(world.actors.len(),1);v2.replace(&mut world,&mut runtime,now).unwrap();
    assert_eq!(world.id,11732);assert!(world.actors.is_empty()&&world.extended_breech_lab());
    assert_eq!(world.failure_snapshot()["unarmored_device_policy"],crate::p06t_damage::UNARMORED_DEVICE_POLICY);
    assert!(runtime.as_ref().unwrap().batch.is_some());
    assert!(!old.world.fresh_battle(11733,now).unwrap().extended_breech_lab());
}
