//! All new selection replies and room/auth origins below are AUTHORED scheduling
//! inputs. Only the Frozen4 request/reply is actual saved SQLite writer evidence.
//! No actual Ready/HTTP/SQL reserve or native acceptance is claimed by these tests.
use super::*;
use crate::training091::{domain as room,selection,selection_loss};
use serde_json::{Value,json};
use sha2::Digest;
const ACTUAL:&[u8]=include_bytes!("../../../../tests/fixtures/p06t-ammo-loss-writer-vectors.json");
const OLD_SELECTION:&[u8]=include_bytes!("../../../../tests/fixtures/p10b-selection-writer-vectors.json");
fn hash(v:&Value)->String{format!("{:x}",sha2::Sha256::digest(serde_json::to_vec(v).unwrap()))}
fn actual()->Value{
    use sha2::Digest;
    assert_eq!(format!("{:x}",sha2::Sha256::digest(ACTUAL)),"251c60f587d14d916e5381567d8af2982b26f0f98335af8464b75bbf1cc1f154");
    let v:Value=serde_json::from_slice(ACTUAL).unwrap();v["vectors"].as_array().unwrap().iter().find(|r|r["request"]["operation"]=="admit").unwrap().clone()
}
fn context(v:&Value)->Context{Context{account_id:v["account_id"].as_str().unwrap().into(),native_database_id:v["native_database_id"].as_i64().unwrap()as i32,
    run_id:v["run_id"].as_str().unwrap().into(),expected_revision:v["expected_revision"].as_u64().unwrap(),command_key:v["command_key"].as_str().unwrap().into()}}
fn stamp()->selection_loss::Stamp{
    let v:Value=serde_json::from_slice(OLD_SELECTION).unwrap();
    selection_loss::Stamp{base:selection::Stamp::parse(&v["vectors"][0]["request"]["projection_stamp"]).unwrap(),
        loss_policy_sha256:writer::POLICY_SHA256.into(),loss_companion_sha256:"a".repeat(64)}
}
fn reowner(v:&mut Value,from:&str,to:&str){match v{Value::String(s)=>*s=s.replace(from,to),Value::Array(a)=>for x in a{reowner(x,from,to)},
    Value::Object(m)=>for x in m.values_mut(){reowner(x,from,to)},_=>{}}}
fn ready(peer:bool)->ReadySelection{
    let row=actual();let mut c=context(&row["request"]);let mut frozen=row["response"]["reservation"]["frozen"].clone();
    if peer{let old=c.account_id.clone();c.account_id="f5326cc1-8524-479c-8bba-72e973489c22".into();c.native_database_id+=1;
        reowner(&mut frozen,&old,&c.account_id);frozen["loadout_sha256"]=hash(&frozen["loadout"]).into();}
    let request=selection_loss::Request::new(&c,1,stamp()).unwrap();
    let mut value=json!({"version":4,"contract":writer::CONTRACT,"schema":selection_loss::SCHEMA,"operation":"select","status":"ready",
        "account_id":c.account_id,"native_database_id":c.native_database_id,"run_id":c.run_id,"native_inventory_id":1,"revision":c.expected_revision,
        "projection_stamp":request.projection_stamp.value(),"aggregate_sha256":"b".repeat(64),"frozen_sha256":hash(&frozen),"frozen":frozen});
    let mut binding=value.clone();for key in["version","operation","status","frozen"]{binding.as_object_mut().unwrap().remove(key);}value["fingerprint"]=hash(&binding).into();
    let selected=selection_loss::parse_reply(&serde_json::to_vec(&value).unwrap(),&request).unwrap();
    let owner=Arc::new(identity091::Profile{account_id:c.account_id.clone(),database_id:c.native_database_id,name:format!("AUTHORED ready {}",c.native_database_id),fixture_dir:std::path::PathBuf::new()});
    ReadySelection::from_selection(owner,if peer{102}else{101},selected).unwrap()
}
fn saga()->Saga{
    let selections=vec![ready(false),ready(true)];let mut reg=room::Registry::default();
    let leases=selections.iter().map(|s|room::AuthLease{account:s.ready.owner(),generation:1}).collect::<Vec<_>>();
    for(s,l)in selections.iter().zip(&leases){reg.bind_authenticated(*l,s.owner.name.clone(),0).unwrap();}
    reg.command(leases[0],room::Command::Create(room::Settings{capacity:2,map:room::QualifiedMap::Prohorovka,seconds:600,opened:true,comment:String::new()}),0).unwrap();
    let key=reg.authenticated_room(leases[0]).unwrap();reg.command(leases[1],room::Command::Join(key),0).unwrap();
    reg.command(leases[0],room::Command::Assign{target:leases[1].account,roster:room::Roster::assigned(room::Side::Two)},0).unwrap();
    for(s,l)in selections.iter().zip(&leases){let context=reg.selection_context(*l).unwrap();reg.command(*l,room::Command::Ready{context,selection:s.ready.clone()},0).unwrap();}
    reg.command(leases[0],room::Command::TeamReady{side:room::Side::One,ready:true,force:true},0).unwrap();
    let snapshot=reg.command(leases[0],room::Command::TeamReady{side:room::Side::Two,ready:true,force:true},0).unwrap().into_iter()
        .find_map(|e|if let room::Event::Prepare(s)=e{Some(s)}else{None}).unwrap();
    Saga::new(snapshot,BattleKey(9007199254740993),selections).unwrap()
}
fn state(s:&Saga)->String{format!("{:?}|{:?}|{}",s.slots.iter().map(|v|(v.stage as u8,v.revision,v.reservation.as_ref().map(|r|(&r.reservation_id,&r.frozen.sha256)))).collect::<Vec<_>>(),
    s.pending.as_ref().map(|t|(t.index,t.session,&t.context,&t.request)),s.aborting)}
#[test]fn p10b_loss_saga_unresolved_actual_admit_cannot_be_replaced_or_released_without_fresh(){
    let row=actual();let mut s=saga();assert_eq!(s.next_admission_origin().unwrap().0,101);
    let c=context(&row["request"]);let task=s.next_admit(c.clone()).unwrap().unwrap();s.abort();let before=state(&s);
    assert!(s.next_inspect(c.clone()).is_err());assert!(s.next_cancel(c.clone()).is_err());assert!(s.released_refs().is_err());assert_eq!(state(&s),before);
    let reply=writer::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&c,&task.request).unwrap();
    let done=CompletionLoss{session:task.session,old_owner:task.owner.clone(),context:c,request:task.request.clone(),reply,fresh:None,refresh_error:None};
    assert!(s.complete(&done).is_err());assert_eq!(state(&s),before);let retry=s.retry().unwrap();assert_eq!(retry.context,task.context);assert_eq!(retry.request,task.request);
}
#[test]fn p10b_loss_saga_pristine_compensation_keeps_three_stacks_and_no_fired_or_lost(){
    let row=actual();let mut s=saga();let c=context(&row["request"]);let request=writer::Request::Admit{battle:s.battle.0,native_inventory_id:1};
    let receipt=writer::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&c,&request).unwrap().reservation.unwrap();
    // AUTHORED scheduling placement ONLY; no claim that Saga accepted an HTTP Fresh.
    let slot=s.slots.iter_mut().find(|p|p.selection.session==101).unwrap();slot.stage=Stage::Reserved;slot.revision+=1;slot.reservation=Some(receipt.clone());s.abort();
    let task=s.next_cancel(Context{expected_revision:c.expected_revision+1,command_key:"p10b:loss:authored-cancel".into(),..c}).unwrap().unwrap();
    let writer::Request::Finish{remaining_ammunition,fired_ammunition,lost_ammunition,loss_event,terminal_hp,reason,results_json,..}=task.request else{panic!("Finish required")};
    assert_eq!(remaining_ammunition.map(|r|r.count),receipt.frozen.base.counts());assert_eq!(fired_ammunition.map(|r|r.count),[0;3]);
    assert_eq!(lost_ammunition.map(|r|r.count),[0;3]);assert!(loss_event.is_none());assert_eq!(terminal_hp,receipt.frozen.base.max_hp);
    assert_eq!(reason,FinishReason::Cancelled);assert!(results_json.is_none());assert!(s.released_refs().is_err());
}
#[test]fn p10b_loss_saga_null_inspect_without_current_bound_fresh_keeps_pending_and_claims(){
    let mut s=saga();s.abort();let(_,owner,revision)=s.next_inspection_origin().unwrap();
    let selected=s.slots.iter().find(|p|p.selection.owner.account_id==owner.account_id).unwrap().selection.clone();
    let c=Context{expected_revision:revision,command_key:"p10b:loss:inspect-after-drain".into(),..selected.context.clone()};
    let task=s.next_inspect(c.clone()).unwrap().unwrap();let before=state(&s);
    let done=CompletionLoss{session:task.session,old_owner:owner,context:c,request:writer::Request::Inspect,
        reply:writer::Reply{status:writer::Status::Inspected,revision,replayed:false,code:None,reservation:None},fresh:None,refresh_error:None};
    assert!(s.complete(&done).is_err());assert_eq!(state(&s),before);assert!(s.released_refs().is_err());assert!(s.retry().is_some());
}
