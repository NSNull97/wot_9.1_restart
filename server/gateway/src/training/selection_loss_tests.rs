//! New reply/stamp provenance is AUTHORED for codec tests. Frozen4 is retained
//! actual project SQLite writer evidence. No actual selection/readiness claim.
use super::*;
const ACTUAL:&[u8]=include_bytes!("../../../../tests/fixtures/p06t-ammo-loss-writer-vectors.json");
const OLD:&[u8]=include_bytes!("../../../../tests/fixtures/p10b-selection-writer-vectors.json");
fn fixture()->(Request,Value){
    assert_eq!(format!("{:x}",Sha256::digest(ACTUAL)),"251c60f587d14d916e5381567d8af2982b26f0f98335af8464b75bbf1cc1f154");
    assert_eq!(format!("{:x}",Sha256::digest(OLD)),"493511296d5c3b09fa1ce5d9906b48d565b02eab345191659d079d1294e7da97");
    let actual:Value=serde_json::from_slice(ACTUAL).unwrap();let old:Value=serde_json::from_slice(OLD).unwrap();
    let a=actual["vectors"].as_array().unwrap().iter().find(|r|r["request"]["operation"]=="admit").unwrap();let q=&a["request"];
    let c=Context{account_id:q["account_id"].as_str().unwrap().into(),native_database_id:q["native_database_id"].as_i64().unwrap()as i32,
        run_id:q["run_id"].as_str().unwrap().into(),expected_revision:q["expected_revision"].as_u64().unwrap(),command_key:"p10b:selection:authored".into()};
    let stamp=Stamp{base:old::Stamp::parse(&old["vectors"][0]["request"]["projection_stamp"]).unwrap(),loss_policy_sha256:loss::POLICY_SHA256.into(),
        loss_companion_sha256:"a".repeat(64)};
    let r=Request::new(&c,q["native_inventory_id"].as_u64().unwrap()as u32,stamp).unwrap();let wrapper=&a["response"]["reservation"]["frozen"];
    let mut reply=json!({"version":4,"contract":loss::CONTRACT,"schema":SCHEMA,"operation":"select","status":"ready",
        "account_id":c.account_id,"native_database_id":c.native_database_id,"run_id":c.run_id,"native_inventory_id":r.base.native_inventory_id,
        "revision":c.expected_revision,"projection_stamp":r.projection_stamp.value(),"aggregate_sha256":"b".repeat(64),"frozen":wrapper,
        "frozen_sha256":a["response"]["reservation"]["frozen_sha256"]});
    resign(&mut reply);(r,reply)
}
fn resign(v:&mut Value){let mut binding=v.clone();for key in["version","operation","status","frozen","fingerprint"]{binding.as_object_mut().unwrap().remove(key);}
    v["fingerprint"]=digest(&binding).unwrap().into();}
fn parse(v:&Value,r:&Request)->io::Result<Selection>{parse_reply(&serde_json::to_vec(v).unwrap(),r)}
#[test]fn p10b_loss_selection_actual_wrapper_stays_distinct_from_bare_v2(){
    let(r,v)=fixture();let s=parse(&v,&r).unwrap();assert_ne!(s.frozen().sha256,s.frozen().base.sha256);
    s.frozen().validate_owned(&r.base.account_id).unwrap();assert_eq!(s.request(),&r);
    assert!(old::parse_reply(&serde_json::to_vec(&v).unwrap(),&r.base).is_err());
    let mut bare=v.clone();bare["frozen"]=v["frozen"]["loadout"].clone();bare["frozen_sha256"]=v["frozen"]["loadout_sha256"].clone();resign(&mut bare);
    assert!(parse(&bare,&r).is_err());
}
#[test]fn p10b_loss_selection_wrong_policy_hash_companion_and_origin_refuse(){
    let(r,v)=fixture();for key in["loss_policy_sha256","loss_companion_sha256","native_state_sha256","owner_source_sha256"]{
        let mut wrong=v.clone();wrong["projection_stamp"][key]="0".repeat(64).into();resign(&mut wrong);assert!(parse(&wrong,&r).is_err(),"{key}");}
    for(key,value)in[("version",json!(2)),("revision",json!(r.base.expected_revision+1)),("native_inventory_id",json!(2)),("contract",json!("mixed-v2"))]{
        let mut wrong=v.clone();wrong[key]=value;resign(&mut wrong);assert!(parse(&wrong,&r).is_err(),"{key}");}
    let mut wrong=v.clone();wrong["frozen"]["policy_sha256"]="0".repeat(64).into();wrong["frozen_sha256"]=digest(&wrong["frozen"]).unwrap().into();resign(&mut wrong);
    assert!(parse(&wrong,&r).is_err());
}
#[test]fn p10b_loss_selection_extra_duplicate_boolean_bound_and_changed_request_refuse(){
    let(r,v)=fixture();let mut wrong=v.clone();wrong["arbitrary_source_path"]="C:/untrusted".into();assert!(parse(&wrong,&r).is_err());
    let raw=serde_json::to_string(&v).unwrap();let dup=raw.replacen("\"version\":4","\"version\":4,\"version\":4",1);assert_ne!(raw,dup);
    assert!(parse_reply(dup.as_bytes(),&r).is_err());assert!(parse_reply(&vec![b' ';MAX_REPLY+1],&r).is_err());
    wrong=v.clone();wrong["native_database_id"]=true.into();assert!(parse(&wrong,&r).is_err());
    let mut changed=r.clone();changed.projection_stamp.base.native_state_sha256="c".repeat(64);assert!(encode_request(&changed).is_err());
}
