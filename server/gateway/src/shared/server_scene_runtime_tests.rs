use super::*;
use std::path::PathBuf;
fn resources()->[super::super::super::profile13_templates::Resources;2]{
    let root=PathBuf::from(std::env::var("WOT091_ROOT").unwrap_or_else(|_|"D:/WoT_9.1_Server".into())).join("local");
    let source=root.join("stands/p08b-profile13-01/battle-profiles.json");
    let mut v:serde_json::Value=serde_json::from_slice(&fs::read(source).unwrap()).unwrap();
    let artifact=std::env::var_os("WOT_P05C_ARTIFACTS").map(PathBuf::from).unwrap_or_else(||root.join("build/server/physics-p05c-night01/artifacts.json"));
    v["version"]=2.into();v["shared_physics"]=serde_json::json!({"path":artifact,"sha256":format!("{:x}",sha2::Sha256::digest(fs::read(&artifact).unwrap()))});
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let path=root.join(format!("test-runs/p05c-template-{}-{stamp}.json",std::process::id()));fs::write(&path,serde_json::to_vec(&v).unwrap()).unwrap();
    super::super::super::profile13_templates::load(&root,&path).unwrap()
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
        let base=Instant::now();
        for frame in 1..=120{
            if frame==61{world.detach(n as u32).unwrap();if n==6{world.actors[n-2].health=0;world.actors[n-2].input=model::Input::STOP;}}
            let at=base+Duration::from_millis(frame*100);let before=world.tick;
            spin(&mut runtime,&mut world,at,|r,w|w.tick>before&&!r.blocked());
            assert_eq!(runtime.runtime.as_ref().unwrap().process_id(),pid);assert_eq!(world.actors.len(),n);
        }
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
