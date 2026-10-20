use super::*;
#[test]fn p08b_hold5_incremental_update_matches_independent_project_primitive_golden(){
    let v:Value=serde_json::from_slice(include_bytes!("../../../../tests/fixtures/p08b-hold-update-golden.json")).unwrap();
    for r in v["cases"].as_array().unwrap(){let l=NativeLayout{native:r["native_inventory_id"].as_u64().unwrap()as u32,
        turret:r["turret_compact_id"].as_u64().unwrap()as u16,gun:r["gun_compact_id"].as_u64().unwrap()as u16,
        layout:std::array::from_fn(|i|r["shells_layout"][i].as_i64().unwrap()as i32)};
        let wire=r["wire_revision"].as_i64().unwrap();let raw=final_delta(&l,wire).unwrap();let body=final_update(&l,wire).unwrap();
        let hex=|a:&[u8]|a.iter().map(|b|format!("{b:02x}")).collect::<String>();
        assert_eq!(hex(&raw),r["delta_hex"]);assert_eq!(hex(&body),r["body_hex"]);
        assert_eq!(&body[..4],&[0x13,0x57,raw.len()as u8+1,raw.len()as u8]);assert_eq!(body.len(),raw.len()+4);
        assert!(final_update(&l,0).is_err());assert!(final_update(&l,i64::from(i32::MAX)).is_err());
    }
}
fn companion()->Value{serde_json::json!({"version":5,"contract":hold::CONTRACT,"policy_sha256":hold::POLICY_SHA256,"base_loss_policy_sha256":loss::POLICY_SHA256,
    "account_id":"80ad3bc2-476e-4fbd-899d-a4679ea167d2","native_database_id":3,"revision":40,"state_sha256":"a".repeat(64),
    "native_layouts":[{"native_inventory_id":1,"turret_compact_id":5891,"gun_compact_id":5892,"shells_layout":[-2570,0,2826,4,3082,10]}]})}
#[test]fn p08b_hold5_companion_source_state_and_closed_fields_are_required(){
    let v=companion();let a=v["account_id"].as_str().unwrap();parse(&serde_json::to_vec(&v).unwrap(),a,3,40,&"a".repeat(64)).unwrap();
    for(key,x)in[("version",4.into()),("revision",41.into()),("state_sha256","b".repeat(64).into()),("policy_sha256",loss::POLICY_SHA256.into()),("native_database_id",4.into())]{
        let mut bad=v.clone();bad[key]=x;assert!(parse(&serde_json::to_vec(&bad).unwrap(),a,3,40,&"a".repeat(64)).is_err(),"{key}");}
    let mut extra=v.clone();extra["ignored"]=Value::Null;assert!(parse(&serde_json::to_vec(&extra).unwrap(),a,3,40,&"a".repeat(64)).is_err());
}
#[test]fn p08b_hold5_actual_layout_may_preserve_sign_but_cannot_change_source_mount_counts_or_order(){
    let v=companion();let a=v["account_id"].as_str().unwrap();
    for n in 0..5{let mut p=v.clone();match n{0=>p["native_layouts"][0]["shells_layout"][0]=0.into(),1=>p["native_layouts"][0]["shells_layout"][3]=97.into(),
        2=>p["native_layouts"][0]["gun_compact_id"]=14852.into(),3=>p["native_layouts"][0]["native_inventory_id"]=3.into(),4=>p["native_layouts"].as_array_mut().unwrap().push(v["native_layouts"][0].clone()),_=>unreachable!()};
        assert!(parse(&serde_json::to_vec(&p).unwrap(),a,3,40,&"a".repeat(64)).is_err(),"poison{n}");}
    let doc:Value=serde_json::from_slice(include_bytes!("../../../../tests/fixtures/p08b-owner-hold-first-vectors.json")).unwrap();let r=&doc["vectors"][1]["response"]["reservation"];
    let frozen=hold::parse_frozen(&r["frozen"],a,r["frozen_sha256"].as_str().unwrap()).unwrap();
    let b=parse(&serde_json::to_vec(&v).unwrap(),a,3,40,&"a".repeat(64)).unwrap();b.layout_for(&frozen,[0,4,10]).unwrap();assert!(b.layout_for(&frozen,[0,3,10]).is_err());
}
