//! Candidate tests, NOT_RUN until a separately authorized Rust component build.
use super::*;
const ACTUAL:&[u8]=include_bytes!("../../../../tests/fixtures/p10b-selection-writer-vectors.json");
const ACTUAL_SHA:&str="493511296d5c3b09fa1ce5d9906b48d565b02eab345191659d079d1294e7da97";
fn vectors()->Vec<Value>{
    assert_eq!(format!("{:x}",Sha256::digest(ACTUAL)),ACTUAL_SHA);
    let v:Value=serde_json::from_slice(ACTUAL).unwrap();assert_eq!(v["schema"],"p10b-selection-actual-writer-vectors.v1");
    let rows=v["vectors"].as_array().unwrap();assert_eq!(rows.len(),4);rows.clone()
}
fn request(v:&Value)->Request{
    let c=Context{account_id:v["account_id"].as_str().unwrap().into(),native_database_id:v["native_database_id"].as_i64().unwrap()as i32,
        command_key:"p10b-read-only-not-an-admission-key".into(),run_id:v["run_id"].as_str().unwrap().into(),expected_revision:v["expected_revision"].as_u64().unwrap()};
    Request::new(&c,v["native_inventory_id"].as_u64().unwrap()as u32,Stamp::parse(&v["projection_stamp"]).unwrap()).unwrap()
}
#[test]fn p10b_selection_actual_SQL_C_D_and_concurrent_new_snapshot_match_existing_frozen_validator(){
    let mut counts=Vec::new();
    for (i,row)in vectors().into_iter().enumerate(){let request=request(&row["request"]);
        assert_eq!(serde_json::from_slice::<Value>(&encode_request(&request).unwrap()).unwrap(),row["request"]);
        let selection=parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&request).unwrap();
        assert_eq!(selection.frozen.native_inventory_id,if i==3{2}else{1});
        assert_eq!(selection.frozen.kind,if i==3{crate::gateway091::shared::vehicle_profile::VehicleKind::Is7}else{crate::gateway091::shared::vehicle_profile::VehicleKind::Ms1});
        assert_eq!(selection.frozen.initial_shell_compact_id,if i==3{14858}else{2826});assert_eq!(selection.frozen.crew_ids.len(),if i==3{5}else{2});
        assert_ne!(selection.aggregate_sha256,selection.request.projection_stamp.native_state_sha256);
        selection.frozen.validate_owned(&selection.request.account_id).unwrap();counts.push(selection.frozen.counts());
    }
    assert_eq!(counts,vec![[0,4,10],[0,4,10],[0,3,11],[0,4,10]]);
}
#[test]fn p10b_selection_actual_reply_identity_stamp_source_and_frozen_poison_are_refused(){
    let rows=vectors();let original=&rows[0]["response"];let request=request(&rows[0]["request"]);
    for key in["account_id","run_id","aggregate_sha256","frozen_sha256","fingerprint"]{
        let mut bad=original.clone();bad[key]="0".repeat(64).into();assert!(parse_reply(&serde_json::to_vec(&bad).unwrap(),&request).is_err(),"{key}");
    }
    for(key,value)in[("version",2u64),("native_database_id",4),("native_inventory_id",2),("revision",request.expected_revision+1)]{
        let mut bad=original.clone();bad[key]=value.into();assert!(parse_reply(&serde_json::to_vec(&bad).unwrap(),&request).is_err(),"{key}");
    }
    for key in["native_state_sha256","owner_source_sha256","catalog_sha256","pool_registry_sha256","mixed_policy_sha256","shell_catalog_sha256","terminal_policy_sha256"]{
        let mut bad=original.clone();bad["projection_stamp"][key]="0".repeat(64).into();assert!(parse_reply(&serde_json::to_vec(&bad).unwrap(),&request).is_err(),"{key}");
    }
    let mut bad=original.clone();bad["frozen"]["ammunition"][0]["count"]=1.into();assert!(parse_reply(&serde_json::to_vec(&bad).unwrap(),&request).is_err());
    let mut bad=original.clone();bad["frozen"]["crew_ids"][0]="foreign:crew".into();assert!(parse_reply(&serde_json::to_vec(&bad).unwrap(),&request).is_err());
    assert!(parse_reply(&serde_json::to_vec(&rows[1]["response"]).unwrap(),&request).is_err());
}
#[test]fn p10b_selection_bounds_duplicate_boolean_float_and_extra_claim_fields_are_refused(){
    let rows=vectors();let request=request(&rows[0]["request"]);let original=&rows[0]["response"];
    let raw=serde_json::to_string(original).unwrap();let duplicate=raw.replacen("\"version\":1","\"version\":1,\"version\":1",1);
    assert_ne!(raw,duplicate);assert!(parse_reply(duplicate.as_bytes(),&request).is_err());
    assert!(parse_reply(&vec![b' ';MAX_REPLY+1],&request).is_err());
    for value in[json!(true),json!(3.0),Value::Null]{let mut bad=original.clone();bad["native_database_id"]=value;
        assert!(parse_reply(&serde_json::to_vec(&bad).unwrap(),&request).is_err());}
    let mut bad=original.clone();bad["arbitrary_original_root"]="C:/untrusted".into();assert!(parse_reply(&serde_json::to_vec(&bad).unwrap(),&request).is_err());
    let mut bad=original.clone();bad["status"]="rejected".into();assert!(parse_reply(&serde_json::to_vec(&bad).unwrap(),&request).is_err());
}
