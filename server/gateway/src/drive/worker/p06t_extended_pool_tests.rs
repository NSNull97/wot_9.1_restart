use super::*;
fn root()->PathBuf {PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap()}
fn fixture(kind:VehicleKind)->(PathBuf,PathBuf,Value) {
    let root=root();let path=root.join(format!("local/night-staging/20261016/p06t-vehicle-aim01/pool-v4/{}-pool.json",kind.label()));
    let value=json(&fs::read(&path).unwrap(),16384).unwrap();(root,path,value)
}
fn fresh(root:&Path)->PathBuf {let path=root.join(format!("local/p06t-pool4-test-{}-{}",std::process::id(),
    std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()));fs::create_dir(&path).unwrap();path}
#[test] fn p06t_extended_pool4_binds_genuine_profiles_and_both_source_map_projections() {
    for kind in [VehicleKind::Wt128,VehicleKind::Fv183] {
        let(root,path,_)=fixture(kind);let pool=Pool::load(&root,&path).unwrap();assert!(pool.shared_only());assert_eq!(pool.vehicle_kind(),kind);
        let selected=pool.shared_source_profile().unwrap();assert_eq!(selected.1,ram_proof::Profile::for_vehicle(kind).sha());
        assert_eq!(pool.maps.len(),2);assert_eq!(pool.maps[0].asset,"01_karelia");assert_eq!(pool.maps[1].asset,"05_prohorovka");
        for map in &pool.maps {assert_eq!(map.mass_kg as f64,kind.mass_kg());pool.vehicle_profile.as_ref().unwrap().verify_map(&root,map).unwrap();}
    }
}
#[test] fn p06t_extended_pool4_is_denied_before_every_independent_worker_spawn() {
    for kind in [VehicleKind::Wt128,VehicleKind::Fv183] {
        let(root,path,_)=fixture(kind);let pool=Arc::new(Pool::load(&root,&path).unwrap());
        for map in pool.maps.clone() {let error=Worker::launch(pool.clone(),map,1,Instant::now()).err().expect("shared-only must deny");
            assert_eq!(error.kind(),io::ErrorKind::InvalidInput);assert!(error.to_string().contains("IPC7 SceneManifest3"));}
    }
}
#[test] fn p06t_extended_pool_profiles_do_not_enter_old_versions_or_wrong_kind() {
    for kind in [VehicleKind::Wt128,VehicleKind::Fv183] {
        let(root,_,value)=fixture(kind);let dir=fresh(&root);let reference=&value["vehicle_profile"];
        for version in [1,2,3] {assert!(VehicleProfile::load(&root,reference,version).is_err());}
        let legacy=serde_json::json!({"path":root.join("local/evidence/20261016-p04m-physics01/getters06/t26-qualified-profile.json"),
            "sha256":ram_proof::Profile::T26.sha()});assert!(VehicleProfile::load(&root,&legacy,4).is_err());
        let mut forged=reference.clone();forged["sha256"]=ram_proof::Profile::for_vehicle(if kind==VehicleKind::Wt128{VehicleKind::Fv183}else{VehicleKind::Wt128}).sha().into();
        assert!(VehicleProfile::load(&root,&forged,4).is_err());
        let mut old=value.clone();old["version"]=3.into();let path=dir.join("old-pool.json");fs::write(&path,serde_json::to_vec(&old).unwrap()).unwrap();assert!(Pool::load(&root,&path).is_err());
    }
}
#[test] fn p06t_extended_pool4_rejects_last_map_physics_substitution_even_with_fresh_config_sha() {
    for kind in [VehicleKind::Wt128,VehicleKind::Fv183] {
        let(root,_,mut value)=fixture(kind);let dir=fresh(&root);
        let original=PathBuf::from(value["maps"][1]["config"].as_str().unwrap());let mut config=json(&fs::read(original).unwrap(),16384).unwrap();
        config["body_half_extents"][0]=(config["body_half_extents"][0].as_f64().unwrap()+0.01).into();let raw=serde_json::to_vec(&config).unwrap();
        let path=dir.join("config.json");fs::write(&path,&raw).unwrap();value["maps"][1]["config"]=path.to_str().unwrap().into();
        value["maps"][1]["config_sha256"]=format!("{:x}",Sha256::digest(raw)).into();let pool=dir.join("pool.json");fs::write(&pool,serde_json::to_vec(&value).unwrap()).unwrap();
        assert!(Pool::load(&root,&pool).is_err());
    }
}
