//! Cross-language ACTUAL isolated SQLite request/reply vectors, no self roundtrip.
//! The saved final stats are authored by the writer test; this is not World/UI.
use super::*;
use std::path::PathBuf;
fn fixture()->Value{
    let raw=include_bytes!("../../../../tests/fixtures/p08c-late-loss-two-owner-vectors.json");
    assert_eq!(digest(raw),"fe880dfcdf494c5c237a0c11f261301d1a65d5b12cb8563df009e76fe65a2c3e");serde_json::from_slice(raw).unwrap()
}
fn saved(index:usize)->(Task,Value){
    let f=fixture();let row=&f["append_vectors"][index];let request=row["request"].clone();let reply=row["response"].clone();
    let operation=if request["operation"]=="append"{Operation::Append}else{Operation::ReleaseStamp};
    let body=capture::canonical(&request).unwrap().into_bytes();let stamp=&reply["release_stamp"];
    let owner=Arc::new(identity091::Profile{account_id:request["account_id"].as_str().unwrap().into(),database_id:request["native_database_id"].as_i64().unwrap()as i32,name:"unused saved codec fixture".into(),fixture_dir:PathBuf::new()});
    // Test-only construction from actual saved HTTP DTO, not an admission,
    // runtime Task factory, authenticated Session or live worker claim.
    (Task{owner,operation,sha256:digest(&body),body:Arc::new(body),request,
        expected_finished_revision:stamp["finished_revision"].as_u64().unwrap(),expected_reason:stamp["reason"].as_str().unwrap().into(),
        expected_seal:reply["seal_sha256"].as_str().map(str::to_owned)},reply)
}
#[test]fn p08c_late_protocol_actual_sqlite_read_stamp_has_exact_owner_source_and_revision(){
    let(t,v)=saved(0);assert_eq!(t.request.as_object().unwrap().len(),13);assert!(t.body().len()<=4096);
    assert_eq!(t.request_sha256(),v["request_sha256"]);let Reply::Stamped(stamp)=t.parse_reply(&serde_json::to_vec(&v).unwrap()).unwrap()else{panic!("actual read stamp status")};
    assert_eq!(stamp.finished_revision,113);assert_eq!(stamp.reason,"manual_leave");assert_eq!(stamp.arena_id,"9007199254740993");assert_eq!(stamp.source_contract,"loss-v1");
}
#[test]fn p08c_late_protocol_actual_sqlite_append_and_replay_bind_same_utf8_seal(){
    let(a,reply)=saved(1);let(b,replayed)=saved(2);assert_eq!(a.body(),b.body());assert_eq!(a.request.as_object().unwrap().len(),16);assert!(a.body().len()<=65536);
    assert!(matches!(a.parse_reply(&serde_json::to_vec(&reply).unwrap()).unwrap(),Reply::Appended{replayed:false,..}));
    assert!(matches!(b.parse_reply(&serde_json::to_vec(&replayed).unwrap()).unwrap(),Reply::Appended{replayed:true,..}));
    let seal=a.request["seal_json"].as_str().unwrap();assert!(seal.contains("Танкист_Ёж"));assert_eq!(digest(seal.as_bytes()),reply["seal_sha256"]);
    assert_eq!(capture::canonical(&crate::profile13_v2091::bounded_json(seal.as_bytes(),32768).unwrap()).unwrap(),seal);
}
#[test]fn p08c_late_protocol_wrong_owner_request_policy_and_final_seal_fail_closed(){
    let(t,reply)=saved(1);for field in ["account_id","command_key","request_sha256","policy_sha256","seal_sha256"]{
        let mut poisoned=reply.clone();poisoned[field]="forged".into();assert!(t.parse_reply(&serde_json::to_vec(&poisoned).unwrap()).is_err(),"{field}");}
    let mut poisoned=reply;poisoned["native_database_id"]=99.into();assert!(t.parse_reply(&serde_json::to_vec(&poisoned).unwrap()).is_err());
}
#[test]fn p08c_late_protocol_release_stamp_source_and_finished_revision_are_exact(){
    let(t,reply)=saved(0);for field in ["source_contract","run_id","battle_id","arena_id","reservation_id","frozen_sha256","reason"]{
        let mut poisoned=reply.clone();poisoned["release_stamp"][field]="forged".into();assert!(t.parse_reply(&serde_json::to_vec(&poisoned).unwrap()).is_err(),"{field}");}
    let mut poisoned=reply.clone();poisoned["release_stamp"]["finished_revision"]=114.into();assert!(t.parse_reply(&serde_json::to_vec(&poisoned).unwrap()).is_err());
    let mut poisoned=reply;poisoned["release_stamp"]["release_terminal_sha256"]="not-sha256".into();assert!(t.parse_reply(&serde_json::to_vec(&poisoned).unwrap()).is_err());
}
#[test]fn p08c_late_protocol_known_denial_is_not_append_success_or_mutation_authority(){
    let(t,mut reply)=saved(1);reply["status"]="rejected".into();reply["code"]="LATE_ACTOR_STATE_CHANGED".into();reply["release_stamp"]=Value::Null;reply["seal_sha256"]=Value::Null;
    assert_eq!(t.parse_reply(&serde_json::to_vec(&reply).unwrap()).unwrap(),Reply::Rejected("LATE_ACTOR_STATE_CHANGED".into()));
    reply["code"]="arbitrary server body".into();assert!(t.parse_reply(&serde_json::to_vec(&reply).unwrap()).is_err());
}
#[test]fn p08c_late_protocol_duplicate_truncated_or_oversized_reply_never_passes(){
    let(t,reply)=saved(0);let raw=serde_json::to_vec(&reply).unwrap();for end in [0,1,raw.len()-1]{assert!(t.parse_reply(&raw[..end]).is_err());}
    let raw=String::from_utf8(raw).unwrap();let duplicate=raw.replacen("\"version\":1","\"version\":1,\"version\":1",1);assert_ne!(duplicate,raw);assert!(t.parse_reply(duplicate.as_bytes()).is_err());
    assert!(t.parse_reply(&vec![b' ';4097]).is_err());
}
