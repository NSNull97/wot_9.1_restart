//! Frozen actual SQLite corpus; final actor/Link metadata in this first corpus
//! is authored and does not claim World collision authority or native receipt.
use super::*;
const VECTORS:&[u8]=include_bytes!("../../../../tests/fixtures/p08b-owner-hold-first-vectors.json");
fn corpus()->Value{assert_eq!(format!("{:x}",Sha256::digest(VECTORS)),"70b36eb6d441a9b9c799bdd7d7a55512bc9f4508ef9e2ef1091f7dd481730321");serde_json::from_slice(VECTORS).unwrap()}
fn ctx(v:&Value)->Context{Context{account_id:v["account_id"].as_str().unwrap().into(),native_database_id:v["native_database_id"].as_i64().unwrap()as i32,
    command_key:v["command_key"].as_str().unwrap().into(),expected_revision:v["expected_revision"].as_u64().unwrap_or(0),run_id:v["run_id"].as_str().unwrap_or("e6ef9b6e-1316-4d78-9f6a-18659b03b231").into()}}
fn request(v:&Value)->Request{match text(v,"operation").unwrap(){"run_open"=>Request::RunOpen,"inspect"=>Request::Inspect,
    "admit"=>Request::Admit{battle:battle(text(v,"battle_id").unwrap(),text(v,"run_id").unwrap()).unwrap(),native_inventory_id:num(v,"native_inventory_id").unwrap()as u32},
    "finish"=>Request::Finish(Finish{battle:battle(text(v,"battle_id").unwrap(),text(v,"run_id").unwrap()).unwrap(),native_inventory_id:num(v,"native_inventory_id").unwrap()as u32,
        reservation_id:text(v,"reservation_id").unwrap().into(),remaining:rows(&v["remaining_ammunition"]).unwrap(),fired:rows(&v["fired_ammunition"]).unwrap(),lost:rows(&v["lost_ammunition"]).unwrap(),
        loss_event:event(&v["loss_event"]).unwrap(),terminal_hp:num(v,"terminal_hp").unwrap()as i16,terminal_state_json:text(v,"terminal_state_json").unwrap().into(),
        reason:match text(v,"reason").unwrap(){"battle_finished"=>FinishReason::BattleFinished,"battle_failure"=>FinishReason::BattleFailure,"cancelled"=>FinishReason::Cancelled,_=>panic!("authored test reason")},
        results_json:v["results_json"].as_str().map(str::to_owned),source_link:link(&v["source_link"]).unwrap(),departure:departure(&v["departure"]).unwrap(),finalization:finalization(&v["finalization"]).unwrap()}),
    _=>panic!("not battle operation")}}
pub(super) fn admission()->(Context,Reservation){let d=corpus();let r=&d["vectors"][1];let c=ctx(&r["request"]);
    let reply=parse_reply(&serde_json::to_vec(&r["response"]).unwrap(),&c,&request(&r["request"])).unwrap();(c,reply.reservation.unwrap())}
#[test]fn p08b_hold5_actual_sql_corpus_all_battle_results_and_active_inspect(){let d=corpus();for row in d["vectors"].as_array().unwrap(){
    let c=ctx(&row["request"]);let raw=serde_json::to_vec(&row["response"]).unwrap();
    if matches!(text(&row["request"],"operation").unwrap(),"query"|"ack"){
        let arena=text(&row["request"],"arena_id").unwrap().parse().unwrap();let r=if row["request"]["operation"]=="query"{ResultsRequest::Query{arena}}else{ResultsRequest::Ack{arena}};
        assert_eq!(mixed::bounded_json(&encode_results_request(&c,r).unwrap(),2048).unwrap(),row["request"]);
        assert_eq!(parse_results_reply(&raw,&c,r).unwrap().record_contract,Some(RecordContract::HoldV1));
    }else{let r=request(&row["request"]);assert_eq!(mixed::bounded_json(&encode_request(&c,&r).unwrap(),65536).unwrap(),row["request"]);
        parse_reply(&raw,&c,&r).unwrap();}}
}
#[test]fn p08b_hold5_rejects_plain4_or_retagged_reply_and_cross_owner(){let d=corpus();let row=&d["vectors"][1];let c=ctx(&row["request"]);let req=request(&row["request"]);
    for(k,v)in[("version",4.into()),("policy_sha256",loss::POLICY_SHA256.into()),("native_database_id",999.into()),("contract",loss::CONTRACT.into())]{
        let mut reply=row["response"].clone();reply[k]=v;assert!(parse_reply(&serde_json::to_vec(&reply).unwrap(),&c,&req).is_err(),"{k}");}
    let(_,r)=admission();assert!(loss::parse_frozen(r.frozen.value(),&c.account_id,r.frozen.sha256()).is_err());
    let mut c=c;c.account_id=d["vectors"][3]["request"]["account_id"].as_str().unwrap().into();assert!(parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&c,&req).is_err());
}
#[test]fn p08b_hold5_link_final_meta_cannot_replace_actor_or_pristine_cancel(){let d=corpus();let row=&d["vectors"][6];let c=ctx(&row["request"]);let Request::Finish(f)=request(&row["request"])else{panic!()};
    let(_,r)=admission();f.validate_against(&c,&r).unwrap();
    for n in 0..5{let mut p=f.clone();match n{0=>p.source_link.as_mut().unwrap().actor_slot=5,1=>p.source_link.as_mut().unwrap().source_session_id=0,
        2=>p.finalization=Finalization::PristineCancel,3=>p.departure.as_mut().unwrap().tick=37000,4=>p.remaining[1].count+=1,_=>unreachable!()};assert!(p.validate_against(&c,&r).is_err(),"poison{n}");}
}
#[test]fn p08b_hold5_same_run_ready_active_is_hold_not_admit_or_reentry(){let d=corpus();let row=&d["vectors"][5];let c=ctx(&row["request"]);
    let r=parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&c,&Request::RunOpen).unwrap();assert_eq!(r.status,Status::Ready);assert_eq!(r.revision,c.expected_revision);
    assert_eq!(r.reservation.unwrap().status,ReservationStatus::Active);
    let mut bad=row["response"].clone();bad["reservation"]["status"]="finished".into();assert!(parse_reply(&serde_json::to_vec(&bad).unwrap(),&c,&Request::RunOpen).is_err());
}
#[test]fn p08b_hold5_held_inspect_is_not_replayed_finished_or_foreign_run(){let d=corpus();let row=&d["vectors"][4];let c=ctx(&row["request"]);
    for n in 0..3{let mut p=row["response"].clone();match n{0=>p["replayed"]=true.into(),1=>p["reservation"]["status"]="finished".into(),
        2=>p["reservation"]["frozen"]["loss_frozen_sha256"]="a".repeat(64).into(),_=>unreachable!()};assert!(parse_reply(&serde_json::to_vec(&p).unwrap(),&c,&Request::Inspect).is_err());}
}
#[test]fn p08b_hold5_contained_failure_cannot_carry_cancelled_terminal_reason(){let d=corpus();let row=&d["vectors"][6];let c=ctx(&row["request"]);let req=request(&row["request"]);
    let mut reply=row["response"].clone();reply["reservation"]["result"]["reason"]="cancelled".into();reply["reservation"]["result"]["finalization"]["kind"]="contained_failure".into();
    assert!(parse_reply(&serde_json::to_vec(&reply).unwrap(),&c,&req).is_err());
}
#[test]fn p08b_hold5_actual_sql19_preserves_pristine_replay_and_restart_distinction(){
    let raw=include_bytes!("../../../../tests/fixtures/p08b-owner-hold-v5-vectors.json");
    assert_eq!(format!("{:x}",Sha256::digest(raw)),"0f3640fab7e2f9fe71bd66f3a4cfa7bf441459198575aa0c3720cac3457e56a2");
    let d:Value=serde_json::from_slice(raw).unwrap();assert_eq!(d["vectors"].as_array().unwrap().len(),19);
    let mut restart=0;let mut pristine=0;
    for row in d["vectors"].as_array().unwrap(){let q=&row["request"];if matches!(text(q,"operation").unwrap(),"query"|"ack"){continue;}
        let c=ctx(q);let r=request(q);assert_eq!(mixed::bounded_json(&encode_request(&c,&r).unwrap(),65536).unwrap(),*q);
        let reply=parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&c,&r).unwrap();
        if let Some(receipt)=reply.reservation{if receipt.status==ReservationStatus::AbortedRestart{restart+=1;let t=receipt.result.unwrap();
            assert_eq!(t.finalization,Finalization::AbortedRestart);assert!(t.source_link.is_none()&&t.departure.is_none()&&t.hp.is_none());}
            else if receipt.result.as_ref().is_some_and(|t|t.finalization==Finalization::PristineCancel){pristine+=1;}}
    }
    assert!(restart>=2&&pristine>=2,"actual fresh and replay cases must both survive strict reader");
}
