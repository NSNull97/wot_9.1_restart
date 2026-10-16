//! P10B Saga component tests. SQL request/replies are actual saved writer DTOs;
//! Fresh/cache and transport Session identity below are explicitly AUTHORED
//! scheduling seams. No HTTP, actual refresh, ownership grant or native claim.
//! Intended child module of shared::p10b_writer after coordinated promotion.
use super::*;
use crate::training091::{domain as room,selection};
use serde_json::Value;
use sha2::{Digest,Sha256};
use std::{path::{Path,PathBuf},sync::atomic::{AtomicU64,Ordering}};
const SQL:&[u8]=include_bytes!("../../../../tests/fixtures/p10b-saga-writer-vectors.json");
const SQL_SHA:&str="2986a4eca23fb1cfe176be460ebbbeb015df0bfc0a48fcf86eb69675e92abee9";
const SELECTION:&[u8]=include_bytes!("../../../../tests/fixtures/p10b-selection-writer-vectors.json");
fn cases()->Value{assert_eq!(format!("{:x}",Sha256::digest(SQL)),SQL_SHA);serde_json::from_slice(SQL).unwrap()}
fn case(fragment:&str)->Value{cases()["cases"].as_array().unwrap().iter().find(|c|c["case"].as_str().unwrap().contains(fragment)).unwrap().clone()}
fn call(c:&Value,lane:&str,operation:&str,n:usize)->Value{
 c["calls"][lane].as_array().unwrap().iter().filter(|r|r["request"]["operation"]==operation).nth(n).unwrap().clone()
}
fn context(v:&Value)->Context{Context{account_id:v["account_id"].as_str().unwrap().into(),native_database_id:v["native_database_id"].as_i64().unwrap().try_into().unwrap(),
 command_key:v["command_key"].as_str().unwrap().into(),expected_revision:v["expected_revision"].as_u64().unwrap(),run_id:v["run_id"].as_str().unwrap().into()}}
fn request(v:&Value)->writer::Request{
 let battle=||v["battle_id"].as_str().unwrap().rsplit_once(':').unwrap().1.parse().unwrap();let native=||v["native_inventory_id"].as_u64().unwrap().try_into().unwrap();
 match v["operation"].as_str().unwrap(){"run_open"=>writer::Request::RunOpen,"inspect"=>writer::Request::Inspect,
  "admit"=>writer::Request::Admit{battle:battle(),native_inventory_id:native()},
  "finish"=>{assert_eq!(v["reason"],"cancelled");writer::Request::Finish{battle:battle(),native_inventory_id:native(),reservation_id:v["reservation_id"].as_str().unwrap().into(),
   remaining_ammunition:v["remaining_ammunition"].as_array().unwrap().iter().map(|a|writer::Remaining{shell_compact_id:a["shell_compact_id"].as_u64().unwrap().try_into().unwrap(),count:a["count"].as_u64().unwrap().try_into().unwrap()}).collect::<Vec<_>>().try_into().unwrap(),
   terminal_hp:v["terminal_hp"].as_i64().unwrap().try_into().unwrap(),terminal_state_json:v["terminal_state_json"].as_str().unwrap().into(),reason:FinishReason::Cancelled,results_json:None}},_=>panic!("closed fixture operation")}
}
fn parsed(row:&Value)->(Context,writer::Request,writer::Reply){let c=context(&row["request"]);let r=request(&row["request"]);
 assert_eq!(serde_json::from_slice::<Value>(&writer::encode_request(&c,&r).unwrap()).unwrap(),row["request"]);
 let reply=writer::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&c,&r).unwrap();(c,r,reply)}
fn synthetic_cache()->(PathBuf,Arc<crate::hangar091::Fixtures>){
 static SERIAL:AtomicU64=AtomicU64::new(0);let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/p10b-saga-component");std::fs::create_dir_all(&root).unwrap();
 let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();let path=root.join(format!("{}-{stamp}-{}",std::process::id(),SERIAL.fetch_add(1,Ordering::Relaxed)));std::fs::create_dir(&path).unwrap();
 for(name,bytes)in[("state.bin",b"\x80\x02}(U\x03revK\x01u.".as_slice()),("shop.bin",b"\x80\x02}(U\x03revK\x03u.".as_slice()),("dossier.bin",b"\x80\x02(K\x00]t.".as_slice())]{std::fs::write(path.join(name),bytes).unwrap();}
 let f=Arc::new(crate::hangar091::Fixtures::load_interactive(&path).unwrap());(path,f)
}
fn profile(c:&Context)->Arc<identity091::Profile>{let(path,_)=synthetic_cache();Arc::new(identity091::Profile{account_id:c.account_id.clone(),database_id:c.native_database_id,name:format!("SQL owner {}",c.native_database_id),fixture_dir:path})}
/// cfg(test) bridge ONLY for earlier actual SQL snapshots whose Ready schema/run
/// predates selection.v1. This is NOT the production selection constructor or
/// independent proof of authentication/current projected source/actual Fresh.
fn old_sql_selection(c:&Value,lane:&str)->ReadySelection{
 let admit=call(c,lane,"admit",0);let context=context(&admit["request"]);let owner=profile(&context);
 let r=c["readies"].as_array().unwrap().iter().find(|r|r["owner"]==owner.account_id).unwrap();
 let frozen_sha=format!("{:x}",Sha256::digest(serde_json::to_vec(&r["frozen"]).unwrap()));let frozen=writer::parse_frozen(&r["frozen"],&owner.account_id,&frozen_sha).unwrap();
 let ready=WriterReadyRef::from_verified_writer(account(&owner.account_id).unwrap(),frozen.vehicle_inventory_id.clone(),r["revision"].as_u64().unwrap().try_into().unwrap(),digest(r["fingerprint"].as_str().unwrap()).unwrap()).unwrap();
 ReadySelection{session:100+owner.database_id as u32,owner,context:Context{expected_revision:r["revision"].as_u64().unwrap(),..context},frozen,ready}
}
fn prepared(selections:&[ReadySelection])->(room::Registry,LaunchSnapshot){
 assert_eq!(selections.len(),2);let mut reg=room::Registry::default();let leases=selections.iter().map(|s|room::AuthLease{account:s.ready.owner(),generation:1}).collect::<Vec<_>>();
 for(s,l)in selections.iter().zip(&leases){reg.bind_authenticated(*l,s.owner.name.clone(),0).unwrap();}
 reg.command(leases[0],room::Command::Create(room::Settings{capacity:2,map:room::QualifiedMap::Karelia,seconds:600,opened:true,comment:String::new()}),0).unwrap();let key=reg.authenticated_room(leases[0]).unwrap();
 reg.command(leases[1],room::Command::Join(key),0).unwrap();reg.command(leases[0],room::Command::Assign{target:leases[1].account,roster:room::Roster::assigned(room::Side::Two)},0).unwrap();
 for(s,l)in selections.iter().zip(&leases){let context=reg.selection_context(*l).unwrap();reg.command(*l,room::Command::Ready{context,selection:s.ready.clone()},0).unwrap();}
 reg.command(leases[0],room::Command::TeamReady{side:room::Side::One,ready:true,force:true},0).unwrap();
 let snapshot=reg.command(leases[0],room::Command::TeamReady{side:room::Side::Two,ready:true,force:true},0).unwrap().into_iter().find_map(|e|if let room::Event::Prepare(s)=e{Some(s)}else{None}).unwrap();(reg,snapshot)
}
fn saga(c:&Value)->(room::Registry,Saga){let selections=vec![old_sql_selection(c,"C"),old_sql_selection(c,"D")];let(reg,snapshot)=prepared(&selections);(reg,Saga::new(snapshot,BattleKey(9007199254740993),selections).unwrap())}
fn lane(task:&Task)->&'static str{if task.owner.database_id==3{"C"}else{assert_eq!(task.owner.database_id,4);"D"}}
fn completion(s:&ReadySelection,row:&Value,fresh:bool)->CompletionV2{let(context,request,reply)=parsed(row);
 let f=if fresh{let(_,fixtures)=synthetic_cache();Some(super::super::profile13_session::Fresh{owner:s.owner.clone(),fixtures,binding:crate::ammo_service091::Metadata{revision:reply.revision,wire_revision:1}})}else{None};
 CompletionV2{session:s.session,old_owner:s.owner.clone(),context,request,reply,fresh:f,refresh_error:None}
}
fn state(s:&Saga)->String{format!("{:?}|{:?}|{}",s.slots.iter().map(|v|(v.stage as u8,v.revision,v.reservation.as_ref().map(|r|(&r.reservation_id,&r.frozen.sha256)))).collect::<Vec<_>>(),s.pending.as_ref().map(|t|(t.index,t.session,&t.context,&t.request)),s.aborting)}
fn pending_admit(s:&mut Saga,c:&Value)->(Task,Value){let index=s.slots.iter().position(|s|s.stage==Stage::Unissued).unwrap();let selection=s.slots[index].selection.clone();let lane=if selection.owner.database_id==3{"C"}else{"D"};let row=call(c,lane,"admit",0);let task=s.next_admit(context(&row["request"])).unwrap().unwrap();(task,row)}

#[test]fn p10b_saga_actual_six_SQL_cases_all_forty_requests_and_replies_use_strict_codec(){
 let data=cases();assert_eq!(data["cases"].as_array().unwrap().len(),6);let mut count=0;
 for c in data["cases"].as_array().unwrap(){for calls in c["calls"].as_object().unwrap().values(){for row in calls.as_array().unwrap(){parsed(row);count+=1;}}}assert_eq!(count,40);
}
#[test]fn p10b_saga_production_constructor_actual_four_selection_vectors_and_foreign_owner_channel(){
 assert_eq!(format!("{:x}",Sha256::digest(SELECTION)),"493511296d5c3b09fa1ce5d9906b48d565b02eab345191659d079d1294e7da97");let data:Value=serde_json::from_slice(SELECTION).unwrap();
 for row in data["vectors"].as_array().unwrap(){let q=&row["request"];let c=Context{account_id:q["account_id"].as_str().unwrap().into(),native_database_id:q["native_database_id"].as_i64().unwrap().try_into().unwrap(),expected_revision:q["expected_revision"].as_u64().unwrap(),run_id:q["run_id"].as_str().unwrap().into(),command_key:"selection-read-only".into()};
  let request=selection::Request::new(&c,q["native_inventory_id"].as_u64().unwrap().try_into().unwrap(),selection::Stamp::parse(&q["projection_stamp"]).unwrap()).unwrap();
  let parsed=selection::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&request).unwrap();let owner=profile(&c);
  let ready=ReadySelection::from_selection(owner.clone(),103,parsed.clone()).unwrap();assert_eq!(ready.frozen.counts().as_slice(),row["response"]["frozen"]["ammunition"].as_array().unwrap().iter().map(|a|a["count"].as_u64().unwrap()as u16).collect::<Vec<_>>().as_slice());
  assert_eq!(ready.reference().owner(),account(&c.account_id).unwrap());assert_eq!(ready.reference().revision(),c.expected_revision as u32);
  assert!(ReadySelection::from_selection(owner.clone(),0,parsed.clone()).is_err());
  let mut wrong=c.clone();wrong.native_database_id+=1;assert!(ReadySelection::from_selection(profile(&wrong),103,parsed.clone()).is_err());
  wrong.account_id="00000000-0000-4000-8000-000000000001".into();assert!(ReadySelection::from_selection(profile(&wrong),103,parsed).is_err());
 }
}
#[test]fn p10b_saga_all_actual_reserves_required_before_real_registry_launch_claim(){
 let c=case("two_real_owned");let(mut registry,mut saga)=saga(&c);let snapshot=saga.snapshot.clone();assert!(saga.reserved_refs().is_err());
 for n in 0..2{let(task,row)=pending_admit(&mut saga,&c);let selected=saga.slots[task.index].selection.clone();assert_eq!(writer::encode_request(&task.context,&task.request).unwrap(),writer::encode_request(&context(&row["request"]),&request(&row["request"])).unwrap());
  assert!(saga.reserved_refs().is_err());saga.complete(&completion(&selected,&row,true)).unwrap();if n==0{assert!(saga.reserved_refs().is_err());}}
 for m in snapshot.members(){assert_eq!(registry.claim(m.account()),Some(room::Claim::Room(snapshot.room())));}
 let refs=saga.reserved_refs().unwrap();assert_eq!(refs.len(),2);registry.commit_launch(snapshot.room(),snapshot.ticket(),saga.battle,refs,0).unwrap();
 for m in snapshot.members(){assert_eq!(registry.claim(m.account()),Some(room::Claim::Battle(saga.battle)));}
 // Owning coordinator must now REMOVE/consume saga before actor publication.
}
#[test]fn p10b_saga_two_actual_cancelled_receipts_precede_whole_registry_abort_release(){
 let c=case("two_real_owned");let(mut registry,mut saga)=saga(&c);let snapshot=saga.snapshot.clone();
 for _ in 0..2{let(task,row)=pending_admit(&mut saga,&c);let selected=saga.slots[task.index].selection.clone();saga.complete(&completion(&selected,&row,true)).unwrap();}
 registry.command(room::AuthLease{account:snapshot.creator(),generation:1},room::Command::Leave,0).unwrap();
 saga.abort();assert!(saga.reserved_refs().is_err());assert!(saga.released_refs().is_err());
 for n in 0..2{let index=saga.slots.iter().position(|s|s.stage==Stage::Reserved).unwrap();let selected=saga.slots[index].selection.clone();let lane=if selected.owner.database_id==3{"C"}else{"D"};let row=call(&c,lane,"finish",0);
  let task=saga.next_cancel(context(&row["request"])).unwrap().unwrap();assert_eq!(task.request,request(&row["request"]));saga.complete(&completion(&selected,&row,true)).unwrap();
  if n==0{assert!(saga.released_refs().is_err());for m in snapshot.members(){assert_eq!(registry.claim(m.account()),Some(room::Claim::Room(snapshot.room())));}}}
 registry.abort_launch(snapshot.room(),snapshot.ticket(),saga.released_refs().unwrap(),0).unwrap();
 for m in snapshot.members(){assert!(registry.claim(m.account()).is_none());}
}
#[test]fn p10b_saga_pending_null_inspect_cannot_release_late_actual_admit_is_compensated(){
 let c=case("ambiguous_late");let(_,mut saga)=saga(&c);let(task,row)=pending_admit(&mut saga,&c);assert_eq!(lane(&task),"D");let selected=saga.slots[task.index].selection.clone();saga.abort();
 let null=completion(&selected,&call(&c,"D","inspect",0),false);assert!(null.reply.reservation.is_none());let before=state(&saga);
 assert!(saga.next_inspect(null.context.clone()).is_err());assert!(saga.complete(&null).is_err());assert_eq!(state(&saga),before);assert!(saga.released_refs().is_err());
 assert!(saga.next_cancel(task.context.clone()).is_err());assert_eq!(saga.retry().unwrap().request,task.request);
 saga.complete(&completion(&selected,&row,true)).unwrap();assert!(saga.slots[task.index].stage==Stage::Reserved);
 let cancel=call(&c,"D","finish",0);saga.next_cancel(context(&cancel["request"])).unwrap().unwrap();saga.complete(&completion(&selected,&cancel,true)).unwrap();
 assert!(saga.released_refs().is_err()); // untouched C still needs AFTER-drain current Inspect proof.
}
#[test]fn p10b_saga_foreign_late_and_fresh_errors_keep_immutable_actual_task(){
 let c=case("two_real_owned");let(_,original)=saga(&c);
 for poison in 0..9{let mut saga=original.clone();let(task,row)=pending_admit(&mut saga,&c);let selected=saga.slots[task.index].selection.clone();let mut done=completion(&selected,&row,true);
  match poison{0=>done.session+=1,1=>{let mut o=done.context.clone();o.native_database_id+=1;done.old_owner=profile(&o);},2=>done.context.command_key.push_str("-foreign"),3=>done.context.expected_revision+=1,
   4=>done.context.run_id="00000000-0000-4000-8000-000000000002".into(),5=>done.request=writer::Request::Inspect,6=>done.fresh=None,7=>done.refresh_error=Some(bad("authored projection failure")),
   8=>done.fresh.as_mut().unwrap().binding.revision+=1,_=>unreachable!()}
  let before=state(&saga);assert!(saga.complete(&done).is_err(),"poison{poison}");assert_eq!(state(&saga),before);let retry=saga.retry().unwrap();assert_eq!(retry.context,task.context);assert_eq!(retry.request,task.request);assert_eq!(retry.session,task.session);
 }
}
#[test]fn p10b_saga_source_valid_alternate_frozen_cannot_replace_actual_ready_loadout(){
 let c=case("two_real_owned");let(_,mut saga)=saga(&c);
 // Canonical room order is D then C; first actual D admit resolves normally.
 let(task,row)=pending_admit(&mut saga,&c);let selected=saga.slots[task.index].selection.clone();saga.complete(&completion(&selected,&row,true)).unwrap();
 let(task,mut row)=pending_admit(&mut saga,&c);assert_eq!(lane(&task),"C");let selected=saga.slots[task.index].selection.clone();let alt:Value=serde_json::from_slice(SELECTION).unwrap();
 row["response"]["reservation"]["frozen"]=alt["vectors"][2]["response"]["frozen"].clone();row["response"]["reservation"]["frozen_sha256"]=alt["vectors"][2]["response"]["frozen_sha256"].clone();
 // AUTHORED poison composed from two actual Frozen samples; not an actual writer
 // output. Strict V2 parser accepts canonical alternate source/owner shape;
 // Saga must independently retain the immutable READY ammo/Frozen fingerprint.
 let done=completion(&selected,&row,true);assert_eq!(done.reply.reservation.as_ref().unwrap().frozen.counts(),[0,3,11]);
 let before=state(&saga);assert!(saga.complete(&done).is_err());assert_eq!(state(&saga),before);assert!(saga.reserved_refs().is_err());
}
#[test]fn p10b_saga_denial_newer_revision_must_fence_older_actual_null_inspect(){
 let stale=case("second_stale");let null_case=case("ambiguous_late");let(_,mut saga)=saga(&stale);let(task,row)=pending_admit(&mut saga,&stale);assert_eq!(lane(&task),"D");let selected=saga.slots[task.index].selection.clone();
 let denied=completion(&selected,&row,false);assert_eq!(denied.reply.code.as_deref(),Some("STALE_REVISION"));assert_eq!(denied.reply.revision,40);saga.complete(&denied).unwrap();
 let old_row=call(&null_case,"D","inspect",0);let old_null=completion(&selected,&old_row,false);assert_eq!(old_null.reply.revision,39);let before=state(&saga);
 assert!(saga.next_inspect(old_null.context.clone()).is_err());assert_eq!(state(&saga),before);
 let current=Context{expected_revision:40,command_key:"p10b:901:4:inspect-after-drain".into(),..old_null.context.clone()};
 let inspect=saga.next_inspect(current.clone()).unwrap().unwrap();assert_eq!(inspect.request,writer::Request::Inspect);let before=state(&saga);
 // Actual old snapshot arrives AFTER the new issued job. It must not release it.
 assert!(saga.complete(&old_null).is_err());assert_eq!(state(&saga),before);assert_eq!(saga.retry().unwrap().context,current);
 // Positive completion is explicitly AUTHORED scheduler input, not an actual
 // SQL refresh: no saved current Inspect40 exists. Source old Inspect shape is
 // retargeted only to exercise immutable correlation; it proves no ownership.
 let mut current_row=old_row.clone();current_row["request"]["expected_revision"]=40.into();current_row["request"]["command_key"]=current.command_key.clone().into();
 current_row["response"]["source_revision"]=40.into();current_row["response"]["revision"]=40.into();current_row["response"]["command_key"]=current.command_key.clone().into();
 let current_done=completion(&selected,&current_row,false);
 for poison in 0..3{let mut changed=completion(&selected,&current_row,false);match poison{0=>changed.context.command_key.push_str("-old"),1=>changed.context.expected_revision=39,2=>changed.session+=1,_=>unreachable!()}
  let before=state(&saga);assert!(saga.complete(&changed).is_err());assert_eq!(state(&saga),before);}
 saga.complete(&current_done).unwrap();assert!(saga.slots[task.index].stage==Stage::NoReservation);assert!(saga.released_refs().is_err());
}
#[test]fn p10b_saga_actual_fenced_run_is_not_a_safe_no_reservation_denial(){
 let c=case("restart_refunds");let(_,mut saga)=saga(&c);let(task,_)=pending_admit(&mut saga,&c);let selected=saga.slots[task.index].selection.clone();let fenced=call(&c,lane(&task),"admit",1);
 let done=completion(&selected,&fenced,false);assert_eq!(done.reply.code.as_deref(),Some("RUN_FENCED"));let before=state(&saga);
 assert!(saga.complete(&done).is_err());assert_eq!(state(&saga),before);assert!(saga.retry().is_some());assert!(saga.released_refs().is_err());
}

#[test]fn p10b_saga_actual_cancel_commit_loss_requires_exact_terminal_replay_before_release(){
 let c=case("two_real_owned");let stale=case("second_stale");let(_,mut saga)=saga(&c);
 for _ in 0..2{let(task,row)=pending_admit(&mut saga,&c);let selected=saga.slots[task.index].selection.clone();saga.complete(&completion(&selected,&row,true)).unwrap();}
 saga.abort();
 // D first by canonical account order; actual happy cancellation completes.
 let(session,owner,revision)=saga.next_compensation_origin().unwrap();assert_eq!(owner.database_id,4);assert_eq!(session,104);assert_eq!(revision,40);
 let row=call(&c,"D","finish",0);let task=saga.next_cancel(context(&row["request"])).unwrap().unwrap();let selected=saga.slots[task.index].selection.clone();saga.complete(&completion(&selected,&row,true)).unwrap();
 // C's actual saved terminal/replay come from another disposable SQL case with
 // exactly matching run/key/owner/Frozen. This is DTO scheduling composition,
 // not a claim that this Rust test ran that database transaction or refresh.
 let first=call(&stale,"C","finish",0);let replay=call(&stale,"C","finish",1);assert!(parsed(&replay).2.replayed);
 let task=saga.next_cancel(context(&first["request"])).unwrap().unwrap();let selected=saga.slots[task.index].selection.clone();
 assert!(saga.released_refs().is_err());let retry=saga.retry().unwrap();assert_eq!(retry.context(),task.context());assert_eq!(retry.request(),task.request());
 assert!(saga.next_compensation_origin().is_none());assert!(saga.next_inspection_origin().is_none());
 saga.complete(&completion(&selected,&replay,true)).unwrap();assert_eq!(saga.released_refs().unwrap().len(),2);
}
