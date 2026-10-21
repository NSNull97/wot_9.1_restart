use super::*;
fn spec(n:usize)->SceneSpec{SceneSpec{local_root:PathBuf::new(),manifest_path:PathBuf::new(),manifest_sha256:"c".repeat(64),map:"05_prohorovka".into(),
    actors:(0..n).map(|slot|ActorSpec{slot,kind:if slot%2==0{Kind::Ms1}else{Kind::Is7},config_sha256:format!("{:064x}",slot+1),spawn:[0.,1.5,0.],yaw:0.}).collect(),
    catalog_sha256:ZERO.into(),catalog_ids:BTreeSet::new(),pins:Vec::new(),column_ids:BTreeSet::new()}}
fn good(s:&SceneSpec,seq:u32)->Value{json!({"version":7,"event":if seq==0{"ready"}else{"state"},"generation":9,"manifest_sha256":s.manifest_sha256,"catalog_sha256":ZERO,
    "seq":seq,"tick":180+seq*6,"settle_ticks":180,"map":"05_prohorovka","scene_version":0,"scene_sha256":Scene::new(s,&[]).unwrap().sha256,
    "tank_contacts":[],"fracture_claims":[],"actors":s.actors.iter().map(|a|{let(m,p)=a.kind.binding_bits();json!({"slot":a.slot,"kind":a.kind.label(),"config_sha256":a.config_sha256,
        "profile_sha256":a.kind.profile_sha(),"state":{"position":[a.slot as f32*20.,0.,0.],"direction":[0.,0.,0.],"speed":0.,"rspeed":0.,"contacts":6,
        "linear_velocity":[0.,0.,0.],"angular_velocity":[0.,0.,0.],"wheel_contact_masks":[63,63,63,63,63,63],"object_contacts":[],"fractures":[],"motion_witnesses":[],
        "body_binding":{"inverse_mass":f32::from_bits(m),"principal_inverse_diagonal":p.map(f32::from_bits),"inertia_rotation_xyzw":[f32::from_bits(0x3f3504f3),f32::from_bits(0x3f3504f3),0.,0.]}}})}).collect::<Vec<_>>()})}
#[test]fn complete_six_actor_batch_has_one_tick_and_independent_source_profiles(){let s=spec(6);let scene=Scene::new(&s,&[]).unwrap();
    for seq in[0,1,36000]{let f=response(&serde_json::to_vec(&good(&s,seq)).unwrap(),&s,9,&scene,seq).unwrap();assert_eq!(f.actors.len(),6);assert_eq!(f.tick,180+seq*6);
        for a in f.actors{assert_eq!(a.kind,s.actors[a.slot].kind);assert_eq!(a.pose.position[0],a.slot as f32*20.);}}}
#[test]fn whole_batch_rejects_poisoned_last_actor_and_every_identity_boundary(){let s=spec(6);let scene=Scene::new(&s,&[]).unwrap();let good=good(&s,1);
    for mutation in 0..14{let mut v=good.clone();match mutation{0=>{v["actors"].as_array_mut().unwrap().pop();},1=>v["actors"][5]["slot"]=0.into(),2=>v["actors"][5]["state"]["speed"]=26.into(),
        3=>v["actors"][5]["config_sha256"]="f".repeat(64).into(),4=>v["actors"][5]["kind"]="ms1".into(),5=>v["actors"][5]["state"]["body_binding"]["inverse_mass"]=0.into(),
        6=>v["generation"]=10.into(),7=>v["tick"]=187.into(),8=>v["event"]="ready".into(),9=>v["scene_sha256"]="f".repeat(64).into(),10=>v["actors"][5]["state"]["extra"]=1.into(),
        11=>v["tank_contacts"]=json!([{"slot_a":5,"slot_b":1,"substep":1,"point":[0,0,0],"normal":[1,0,0],"relative_velocity":[0,0,0]}]),
        12=>v["actors"][5]["state"]["rspeed"]=1.into(),13=>v["actors"][5]["state"]["wheel_contact_masks"][5]=64.into(),_=>unreachable!()}
        assert!(response(&serde_json::to_vec(&v).unwrap(),&s,9,&scene,1).is_err(),"mutation={mutation}");}
    assert!(response(&serde_json::to_vec(&good).unwrap(),&s,9,&scene,1).is_ok());}
#[test]fn tank_contact_rows_are_typed_sorted_and_reject_reordered_wire_data(){let s=spec(3);let scene=Scene::new(&s,&[]).unwrap();let mut v=good(&s,1);
    v["tank_contacts"]=json!([
        {"slot_a":0,"slot_b":1,"substep":1,"point":[0,0,0],"normal":[1,0,0],"relative_velocity":[5,0,0]},
        {"slot_a":1,"slot_b":2,"substep":2,"point":[1,0,0],"normal":[1,0,0],"relative_velocity":[2,0,0]}]);
    let frame=response(&serde_json::to_vec(&v).unwrap(),&s,9,&scene,1).unwrap();assert_eq!(frame.tank_contacts.len(),2);assert_eq!((frame.tank_contacts[0].slot_a,frame.tank_contacts[1].slot_b),(0,2));
    v["tank_contacts"]=json!([v["tank_contacts"][1].clone(),v["tank_contacts"][0].clone()]);assert!(response(&serde_json::to_vec(&v).unwrap(),&s,9,&scene,1).is_err());}
#[test]fn duplicate_keys_and_oversized_or_deep_json_fail_before_value(){let raw=br#"{"x":{"y":1,"y":2}}"#;assert!(parse(raw,MAX_OUTPUT).is_err());
    assert!(parse(&vec![b' ';MAX_OUTPUT+1],MAX_OUTPUT).is_err());let mut raw="0".to_string();for _ in 0..14{raw=format!("[{raw}]");}assert!(parse(raw.as_bytes(),MAX_OUTPUT).is_err());}
#[test]fn controls_are_exact_complete_batch_and_partial_cruise_is_not_a_brake(){let s=spec(6);let scene=Scene::new(&s,&[]).unwrap();let mut inputs=vec![Input::STOP;6];
    inputs[0]=Input{throttle:1,steer:1,brake:false,speed_percent:25};inputs[1]=Input{throttle:-1,steer:0,brake:false,speed_percent:50};
    let encoded=advance_request(&s,9,&scene,1,&inputs).unwrap();let v=parse(encoded.trim_ascii_end(),MAX_INPUT).unwrap();assert_eq!(v["inputs"][1]["speed_percent"],50);
    assert!(advance_request(&s,9,&scene,1,&inputs[..5]).is_err());for change in 0..4{let mut inputs=inputs.clone();match change{0=>inputs[5].throttle=2,1=>inputs[1].speed_percent=25,
        2=>inputs[0].brake=true,3=>inputs[0].speed_percent=75,_=>unreachable!()}assert!(advance_request(&s,9,&scene,1,&inputs).is_err());}}
#[test]fn cumulative_scene_hash_and_empty_scene_match_checked_csharp_contract(){let s=spec(2);assert_eq!(Scene::new(&s,&[]).unwrap().sha256,digest(b"wot091-empty-battle-scene-v1\0"));
    assert!(Scene::new(&s,&[1]).is_err());let mut c=s.clone();c.catalog_sha256="b".repeat(64);c.catalog_ids=[1,3,5].into_iter().collect();
    assert_eq!(Scene::new(&c,&[]).unwrap().sha256,"3b4d76b3e9b6266fea62459b5d9d2567819a9851fc9abdc2c59640f8e089f81f");
    assert!(Scene::new(&c,&[3,1]).is_err());assert!(Scene::new(&c,&[1,1]).is_err());assert!(Scene::new(&c,&[2]).is_err());}
#[test]fn real_ipc7_prepared_fixture_keeps_one_global_claim_and_rejects_cross_actor_or_substep_replay(){
    let raw=include_bytes!("../../../../../tools/p05c_scene_checks/fixtures/ipc7-prepared.json");
    // Pin the JSONL payload; checkout LF/CRLF is not part of the pipe payload.
    assert_eq!(digest(raw.trim_ascii_end()),"017ea3289d9d4e4a1a81777aeda78a64e1f6efcc79edeb6b1d644105d0d95c1e");
    let v=parse(raw,MAX_OUTPUT).unwrap();let mut s=spec(2);s.manifest_sha256=v["manifest_sha256"].as_str().unwrap().into();s.catalog_sha256=v["catalog_sha256"].as_str().unwrap().into();
    for a in v["actors"].as_array().unwrap(){let slot=a["slot"].as_u64().unwrap()as usize;s.actors[slot].config_sha256=a["config_sha256"].as_str().unwrap().into();}
    s.catalog_ids=v["fracture_claims"].as_array().unwrap().iter().map(|c|c["object_id"].as_u64().unwrap()as u32).collect();
    let scene=Scene::new(&s,&[]).unwrap();let seq=v["seq"].as_u64().unwrap()as u32;assert_eq!(seq,7);assert_eq!(v["scene_version"],0);
    let frame=response(raw,&s,1,&scene,seq).unwrap();assert!(frame.prepared);assert!(!frame.prepared_ids.is_empty());
    let owner=v["fracture_claims"][0]["slot"].as_u64().unwrap()as usize;
    for mutation in 0..5{let mut wrong=v.clone();match mutation{
        0=>wrong["fracture_claims"][0]["slot"]=(1-owner).into(),1=>wrong["fracture_claims"][0]["substep"]=(v["fracture_claims"][0]["substep"].as_u64().unwrap()%6+1).into(),
        2=>{wrong["actors"][owner]["state"]["motion_witnesses"]=json!([]);},
        3=>{let old=wrong["actors"][owner]["state"]["object_contacts"][0]["object_id"].as_u64().unwrap();wrong["actors"][owner]["state"]["object_contacts"][0]["object_id"]=(old+(1u64<<32)).into();},
        4=>{for key in["object_contacts","fractures","motion_witnesses"]{wrong["actors"][1-owner]["state"][key]=wrong["actors"][owner]["state"][key].clone();}},_=>unreachable!()}
        assert!(response(&serde_json::to_vec(&wrong).unwrap(),&s,1,&scene,seq).is_err(),"mutation={mutation}");}
}
#[test]fn artifacts_bind_complete_runtime_tree_and_recheck_before_launch(){
    let root=PathBuf::from(std::env::var_os("CARGO_TARGET_DIR").expect("owned test build target")).join(format!("artifact-component-{}-{}",std::process::id(),
        std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()));
    fs::create_dir_all(root.join("bin")).unwrap();let exe=root.join("bin/test.exe");fs::write(&exe,b"authored component fixture, never executed").unwrap();
    let manifest=root.join("artifacts.json");let v=json!({"version":1,"executable":"bin/test.exe","files":[{"path":"bin/test.exe","bytes":fs::metadata(&exe).unwrap().len(),"sha256":digest(&fs::read(&exe).unwrap())}]});
    fs::write(&manifest,serde_json::to_vec(&v).unwrap()).unwrap();let artifacts=Artifacts::load(&manifest).unwrap();artifacts.verify().unwrap();
    fs::write(root.join("bin/unlisted.dll"),b"unlisted").unwrap();assert!(artifacts.verify().is_err());assert!(Artifacts::load(&manifest).is_err());fs::remove_file(root.join("bin/unlisted.dll")).unwrap();
    fs::write(&exe,b"changed bytes").unwrap();assert!(artifacts.verify().is_err());
}
