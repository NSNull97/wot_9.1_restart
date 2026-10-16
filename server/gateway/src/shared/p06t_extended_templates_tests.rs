use super::*;

pub(super) const TEMPLATE:&str="evidence/20261016-p06t-world07/resources01/battle-profiles-seven.json";
pub(super) const TEMPLATE_SHA:&str="76f198a10768c24082e49cb3d7c850f13eab1a1a249de559f96025c355f933e6";
pub(super) fn actual_resources()->Vec<Resources> {
    // The pinned source files are immutable in this suite; negative cases
    // create separate manifests. Reuse the validated immutable Arc resources.
    static ROWS:std::sync::OnceLock<Vec<Resources>>=std::sync::OnceLock::new();
    ROWS.get_or_init(load_actual_resources).clone()
}
fn load_actual_resources()->Vec<Resources>{
    let root=PathBuf::from(std::env::var_os("WOT091_ROOT").unwrap_or_else(||"D:/WoT_9.1_Server".into())).join("local");
    let path=root.join(TEMPLATE);let raw=fs::read(&path).unwrap();assert_eq!(format!("{:x}",Sha256::digest(&raw)),TEMPLATE_SHA);
    let rows=load(&root,&path).unwrap();assert_eq!(rows.len(),7);assert_eq!(rows.iter().map(|r|r.kind).collect::<Vec<_>>(),VehicleKind::SUPPORTED);
    rows
}
fn structural()->Value {
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
    let reference=|name:&str|serde_json::json!({"path":root.join(name),"sha256":"a".repeat(64)});
    serde_json::json!({"version":4,"map":"05_prohorovka","catalog":reference("source-catalog.json"),"shared_physics":reference("genuine-artifacts.json"),
        "profiles":VehicleKind::SUPPORTED.map(|kind|serde_json::json!({"kind":kind.label(),"pool":reference(&format!("{}-pool.json",kind.label())),
            "geometry":reference(&format!("{}-geometry.json",kind.label()))}))})
}
#[test] fn p06t_extended_resources4_has_exact_seven_canonical_rows_and_old_versions_remain_closed() {
    let value=structural();let expected=parse(&serde_json::to_vec(&value).unwrap()).unwrap();assert_eq!(expected.version,4);
    assert_eq!(expected.profiles.iter().map(|p|p.kind).collect::<Vec<_>>(),VehicleKind::SUPPORTED);
    let mut reverse=value.clone();reverse["profiles"].as_array_mut().unwrap().reverse();assert_eq!(parse(&serde_json::to_vec(&reverse).unwrap()).unwrap(),expected);
    for version in [1,2,3] {
        let mut wrong=value.clone();wrong["version"]=version.into();if version==1{wrong.as_object_mut().unwrap().remove("shared_physics");}
        assert!(parse(&serde_json::to_vec(&wrong).unwrap()).is_err());
        let count=if version==3{5}else{2};wrong["profiles"].as_array_mut().unwrap().truncate(count);
        wrong["profiles"][count-1]["kind"]="fv215b-183".into();assert!(parse(&serde_json::to_vec(&wrong).unwrap()).is_err());
    }
    assert!(VehicleKind::ALL.into_iter().all(|kind|!kind.is_extended()));
    assert!(VehicleKind::SUPPORTED.into_iter().filter(|k|k.is_extended()).all(|kind|!kind.battle_admission()&&kind.initial_ammo()==0));
}
#[test] fn p06t_extended_resources4_rejects_missing_duplicate_extra_and_forged_structural_rows() {
    for mutation in 0..10 {
        let mut wrong=structural();match mutation {
            0=>{wrong["profiles"].as_array_mut().unwrap().pop();},
            1=>{let extra=wrong["profiles"][0].clone();wrong["profiles"].as_array_mut().unwrap().push(extra);},
            2=>wrong["profiles"][6]["kind"]="wt-e100-128".into(),3=>wrong["profiles"][5]["kind"]="wt-e100-150".into(),
            4=>wrong["profiles"][6]["kind"]="Fv183".into(),5=>wrong["profiles"][6]["source_profile"]=Value::Null,
            6=>wrong["profiles"][6]["pool"]["path"]="relative.json".into(),7=>wrong["profiles"][6]["geometry"]["sha256"]="A".repeat(64).into(),
            8=>{wrong.as_object_mut().unwrap().remove("shared_physics");},_=>wrong["version"]=5.into(),
        }
        assert!(parse(&serde_json::to_vec(&wrong).unwrap()).is_err(),"mutation={mutation}");
    }
}
#[test] fn p06t_extended_source_references_require_resource4_and_keep_old_explicit_nulls() {
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
    for kind in VehicleKind::SUPPORTED {
        let source=Some((root.join(format!("{}-source.json",kind.label())),super::super::ram_proof::Profile::for_vehicle(kind).sha().into()));
        assert_eq!(shared_source_reference(kind,4,source.clone()).is_ok(),kind.index()>=2);
        assert_eq!(shared_source_reference(kind,4,None).is_ok(),kind.index()<2);
        if kind.is_extended(){assert!(shared_source_reference(kind,3,source.clone()).is_err());assert!(shared_source_reference(kind,2,source).is_err());}
        else if kind.index()>=2{assert!(shared_source_reference(kind,3,source).is_ok());}
    }
}
#[test] fn p06t_extended_actual_resources_bind_all_seven_real_pools_geometry_and_shared_source_profiles() {
    let rows=actual_resources();let shared=rows[0].shared.as_ref().unwrap();assert_eq!(shared.version,4);assert_eq!(shared.maps.len(),7);
    for row in &rows {
        assert_eq!(row.pool.vehicle_kind(),row.kind);assert_eq!(row.geometry.vehicle_kind(),row.kind);assert_eq!(row.pool.shared_only(),row.kind.is_extended());
        let source=&shared.source_profiles[row.kind.index()];
        if row.kind.index()<2{assert!(source.is_none());}else{assert_eq!(source.as_ref().unwrap().1,super::super::ram_proof::Profile::for_vehicle(row.kind).sha());}
        assert_eq!(shared.maps[row.kind.index()].mass_kg as f64,row.kind.mass_kg());
    }
}
#[test] fn p06t_extended_actual_resources_deny_cross_kind_or_old_pool_substitution_at_last_profile() {
    let rows=actual_resources();let root=&rows[0].shared.as_ref().unwrap().root;let source=root.join(TEMPLATE);
    let value:Value=serde_json::from_slice(&fs::read(source).unwrap()).unwrap();
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let dir=root.join(format!("test-runs/p06t-resources4-{}-{stamp}",std::process::id()));fs::create_dir_all(&dir).unwrap();
    for index in [0,5] {
        let mut wrong=value.clone();wrong["profiles"][6]["pool"]=wrong["profiles"][index]["pool"].clone();
        let path=dir.join(format!("wrong-pool-{index}.json"));fs::write(&path,serde_json::to_vec(&wrong).unwrap()).unwrap();assert!(load(root,&path).is_err());
    }
}
