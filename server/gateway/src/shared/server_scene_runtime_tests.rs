use super::*;
use std::path::PathBuf;
fn resources()->Vec<super::super::super::profile13_templates::Resources>{
    let root=PathBuf::from(std::env::var("WOT091_ROOT").unwrap_or_else(|_|"D:/WoT_9.1_Server".into())).join("local");
    let (source,_)=crate::portable_test_fixtures::verified(&root.join("stands/p08b-profile13-01/battle-profiles.json"),None);
    let mut v:serde_json::Value=serde_json::from_slice(&fs::read(source).unwrap()).unwrap();
    let artifact=std::env::var_os("WOT_P05C_ARTIFACTS").map(PathBuf::from).unwrap_or_else(||root.join("build/server/physics-p05c-night01/artifacts.json"));
    v["version"]=2.into();v["shared_physics"]=serde_json::json!({"path":artifact,"sha256":format!("{:x}",sha2::Sha256::digest(fs::read(&artifact).unwrap()))});
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let path=root.join(format!("test-runs/p05c-template-{}-{stamp}.json",std::process::id()));fs::write(&path,serde_json::to_vec(&v).unwrap()).unwrap();
    super::super::super::profile13_templates::load(&root,&path).unwrap()
}
#[test]fn p04m_scene_rows_keep_v1_exact_and_require_explicit_null_or_new_pin_in_v2(){
    let rows=resources();let shared=rows[0].shared.as_ref().unwrap();
    let v1=BatchRuntime::actor_manifest(shared,0,VehicleKind::Ms1,1).unwrap();
    assert_eq!(v1.as_object().unwrap().len(),5);assert!(v1.get("source_profile").is_none());
    let old_v2=BatchRuntime::actor_manifest(shared,1,VehicleKind::Is7,2).unwrap();
    assert_eq!(old_v2.as_object().unwrap().len(),6);assert!(old_v2["source_profile"].is_null());
    assert!(BatchRuntime::actor_manifest(shared,2,VehicleKind::T26,2).is_err());
    let mut fixture=(**shared).clone();fixture.maps=vec![shared.maps[0].clone();5];
    // Row encoding only: this authored placeholder is never loaded/launched as
    // a physical profile. Production Pool/SceneSpec perform exact pin binding.
    for kind in VehicleKind::ALL.into_iter().skip(2){
        assert!(BatchRuntime::actor_manifest(&fixture,kind.index(),kind,2).is_err());
        fixture.source_profiles[kind.index()]=Some((fixture.root.join(format!("{}-qualified-placeholder.json",kind.label())),"a".repeat(64)));
        let row=BatchRuntime::actor_manifest(&fixture,kind.index(),kind,2).unwrap();
        assert_eq!(row.as_object().unwrap().len(),6);assert_eq!(row["source_profile"]["sha256"],"a".repeat(64));
        assert_eq!(row["kind"],kind.label());assert!(BatchRuntime::actor_manifest(&fixture,kind.index(),kind,1).is_err());
    }
    assert!(BatchRuntime::actor_manifest(&fixture,model::MAX_ACTORS,VehicleKind::T26,2).is_err());
}
fn spin(runtime:&mut BatchRuntime,world:&mut World,now:Instant,until:impl Fn(&BatchRuntime,&World)->bool){
    let deadline=Instant::now()+Duration::from_secs(120);loop{runtime.step(world,now).unwrap();if until(runtime,world){return;}
        assert!(Instant::now()<deadline,"real IPC7 runtime deadline");std::thread::sleep(Duration::from_millis(1));}
}
#[test]fn p05c_actual_gateway_domain_two_and_six_complete_batches_scalar_proof_ack_and_parked_bodies(){
    let rows=resources();
    for n in [2,6]{
        let now=Instant::now();let template=BattleTemplate::from_shared(&rows,n,6000+n as u64,now).unwrap();let mut world=template.world.clone();
        // Isolate movement/proof/ACK here. Native lifecycle is tested separately.
        world.lifecycle=None;
        for slot in 0..n{let kind=if slot%2==0{VehicleKind::Ms1}else{VehicleKind::Is7};
            let(owner,loadout)=model::tests::profile13_loadout(kind,slot,9);world.attach_owned(owner,slot as u32+1,&loadout).unwrap();}
        world.start(now).unwrap();let mut runtime=BatchRuntime::new(rows[0].shared.clone().unwrap(),rows[0].catalog.1.clone());runtime.start(&mut world,now).unwrap();
        spin(&mut runtime,&mut world,Instant::now(),|r,_|r.ready_for_native());
        let pid=runtime.runtime.as_ref().unwrap().process_id();let origins=world.actors.iter().map(|a|a.position).collect::<Vec<_>>();
        for slot in 0..n{world.set_ready(slot,slot as u32+1).unwrap();world.actors[slot].input=model::Input{throttle:1,steer:0,speed_percent:100};}
        let base=Instant::now();let mut barrier_departure=false;let mut barrier_rejoin=false;
        for frame in 1..=120{
            if frame==61{world.detach(100+n as u32).unwrap();if n==6{world.actors[n-2].health=0;world.actors[n-2].input=model::Input::STOP;}}
            let at=base+Duration::from_millis(frame*100);let before=world.tick;
            let deadline=Instant::now()+Duration::from_secs(120);
            loop{runtime.step(&mut world,at).unwrap();
                if runtime.staged.is_some()&&!barrier_departure{
                    let snapshot=runtime.failure_snapshot();assert_eq!(snapshot["process_id"].as_u64(),Some(u64::from(pid)));
                    assert!(snapshot["staged"].is_object());assert!(snapshot["prepared_ids"].as_array().unwrap().len()>0);
                    world.detach(n as u32).unwrap();barrier_departure=true;
                    println!("P05C_ACK_WINDOW_DISCONNECT actors={n} frame={frame} before_scene={} physical_session={}",world.scene_version(),runtime.sessions[n-1]);
                }
                if world.tick>before&&!runtime.blocked(){break;}
                assert!(Instant::now()<deadline);std::thread::sleep(Duration::from_millis(1));
            }
            if barrier_departure&&!barrier_rejoin{
                assert_eq!(world.actors[n-1].session,None);let parked=world.actors[n-1].position;
                let(owner,loadout)=model::tests::profile13_loadout(VehicleKind::Is7,n-1,9);
                assert_eq!(world.attach_owned(owner,100+n as u32,&loadout).unwrap(),n-1);
                world.set_ready(n-1,100+n as u32).unwrap();assert_eq!(world.actors[n-1].position,parked);
                world.actors[n-1].input=model::Input{throttle:1,steer:0,speed_percent:100};barrier_rejoin=true;
            }
            assert_eq!(runtime.runtime.as_ref().unwrap().process_id(),pid);assert_eq!(world.actors.len(),n);
        }
        assert!(barrier_departure&&barrier_rejoin,"actual prepared/ACK window must be exercised");
        assert!(world.actors[0].position[2]>origins[0][2]+5.);
        assert!(world.scene_version()>0,"real full catalog route must produce accepted fractures");
        let state=world.fragiles.as_ref().unwrap();let events=state.vehicle_events.len();assert_eq!(events,world.scene_version()as usize);
        assert_eq!(runtime.runtime.as_ref().unwrap().scene().ids,state.removed_ids());
        assert_eq!(world.actors[n-1].session,None);assert_eq!(world.actors[n-1].input,model::Input::STOP);
        assert_eq!(world.actors[n-1].fire.ammo(),9);if n==6{assert_eq!(world.actors[n-2].health,0);}
        // Freeze the running producer after a real roster departure. The
        // outcome gate must preserve the committed body/HP/ammo/trace for the
        // complete eight-second AFTERBATTLE period, even with a pending reply.
        let members=world.actors.iter().enumerate().map(|(slot,a)|super::super::super::lifecycle::Member{
            team:(slot%2)as u8+1,present:a.session.is_some(),ready:a.ready,alive:a.health>0,
            position:a.position,damage_epoch:0,last_damager:None}).collect::<Vec<_>>();
        let mut lifecycle=super::super::super::lifecycle::State::new(super::super::super::lifecycle::Rules::prohorovka()).unwrap();
        lifecycle.advance(0,&members).unwrap();assert!(lifecycle.outcome().is_some());world.lifecycle=Some(lifecycle);
        let actors=world.actors.clone();let trace=world.impact.clone();let scene=world.scene_version();let tick=world.tick;
        for step in 1..=80{runtime.step(&mut world,base+Duration::from_millis(12000+step*100)).unwrap();}
        assert_eq!(world.actors,actors);assert_eq!(world.impact,trace);assert_eq!(world.scene_version(),scene);assert_eq!(world.tick,tick);
        println!("P05C_DOMAIN_ACCEPTED actors={n} process_id={pid} batches=120 scene={} events={} physical_sessions={:?}",world.scene_version(),events,runtime.sessions);
        drop(runtime);
    }
}
#[test]fn p05c_staged_ack_reconciles_only_departures_and_rejects_new_authority_atomically(){
    let now=Instant::now();let mut current=World::new_for_roster(9401,now,MapId::Prohorovka,6).unwrap();
    for slot in 0..6{let(owner,loadout)=model::tests::profile13_loadout(if slot%2==0{VehicleKind::Ms1}else{VehicleKind::Is7},slot,9);
        current.attach_owned(owner,slot as u32+1,&loadout).unwrap();current.set_ready(slot,slot as u32+1).unwrap();}
    let mut staged=current.clone();staged.actors[5].position=[20.,10.,30.];current.detach(6).unwrap();
    BatchRuntime::reconcile_departures(&mut staged,&current).unwrap();assert_eq!(staged.actors[5].session,None);
    assert_eq!(staged.actors[5].position,[20.,10.,30.]);assert!(!staged.actors[5].ready);assert_eq!(staged.actors[5].input,model::Input::STOP);
    for mutation in 0..4{let mut changed=current.clone();match mutation{
        0=>changed.actors[5].session=Some(66),1=>changed.actors[0].identity.name="changed".into(),
        2=>{changed.actors.pop();},_=>changed.actors[4].session=Some(55)}
        let mut candidate=staged.clone();let before=candidate.actors.clone();
        assert!(BatchRuntime::reconcile_departures(&mut candidate,&changed).is_err());assert_eq!(candidate.actors,before);
    }
}
#[test]fn p05c_saved_actual_ipc7_actor_uses_existing_scalar_parser_and_rejects_tampered_binding(){
    let rows=resources();let catalog=&rows[0].catalog.1;
    let v:serde_json::Value=serde_json::from_str(include_str!("../../../../tools/p05c_scene_checks/fixtures/ipc7-prepared.json")).unwrap();
    let actors=v["actors"].as_array().unwrap();let mut checked=0;
    for a in actors{let state=&a["state"];let profile=if a["kind"]=="ms1"{ram_proof::Profile::Ms1}else{ram_proof::Profile::Is7};
        let contacts=state["object_contacts"].as_array().unwrap().iter().map(|c|{
            let vec3=|v:&serde_json::Value|std::array::from_fn(|i|v[i].as_f64().unwrap()as f32);
            crate::map_drive_worker091::ObjectContact{object_id:c["object_id"].as_u64().unwrap()as u32,substep:c["substep"].as_u64().unwrap()as u8,
                kind:"hull".into(),point:vec3(&c["point"]),normal:vec3(&c["normal"]),velocity:vec3(&c["velocity"])}}).collect::<Vec<_>>();
        let proof=crate::map_drive_worker091::shared_angular_proof(state,&contacts,catalog,profile,v["seq"].as_u64().unwrap()as u32).unwrap();checked+=proof.receipts.len();
        let mut changed=state.clone();changed["body_binding"]["inverse_mass"]=0.00001.into();
        assert!(crate::map_drive_worker091::shared_angular_proof(&changed,&contacts,catalog,profile,7).is_err());
    }assert!(checked>0);
}
