//! Actual saved SQL admission/finish DTOs; actual source World/Results adapter.
//! Flat terrain and clock/leave commands authored. No native/HTTP/Jolt claim.
use super::*;
use std::{path::PathBuf,time::{Instant,Duration}};
use crate::map_profile091::MapId;
use super::super::{geometry,terrain,lifecycle};
fn vectors()->Value{
    let raw=include_bytes!("../../../../tests/fixtures/p08c-late-loss-two-owner-vectors.json");
    assert_eq!(digest(raw),"fe880dfcdf494c5c237a0c11f261301d1a65d5b12cb8563df009e76fe65a2c3e");
    serde_json::from_slice(raw).unwrap()
}
fn context(row:&Value)->Context{let q=&row["request"];Context{account_id:q["account_id"].as_str().unwrap().into(),native_database_id:q["native_database_id"].as_i64().unwrap()as i32,
    run_id:q["run_id"].as_str().unwrap().into(),command_key:q["command_key"].as_str().unwrap().into(),expected_revision:q["expected_revision"].as_u64().unwrap()}}
fn admission(row:&Value)->loss::Reservation{
    let c=context(row);let q=&row["request"];let req=loss::Request::Admit{battle:q["battle_id"].as_str().unwrap().rsplit(':').next().unwrap().parse().unwrap(),native_inventory_id:q["native_inventory_id"].as_u64().unwrap()as u32};
    loss::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&c,&req).unwrap().reservation.unwrap()
}
fn request(row:&Value)->loss::Request{
    let q=&row["request"];let stacks=|key:&str|std::array::from_fn(|i|mixed::Remaining{shell_compact_id:q[key][i]["shell_compact_id"].as_u64().unwrap()as u16,count:q[key][i]["count"].as_u64().unwrap()as u16});
    assert!(q["loss_event"].is_null(),"this saved case has no detonation");
    loss::Request::Finish{battle:q["battle_id"].as_str().unwrap().rsplit(':').next().unwrap().parse().unwrap(),native_inventory_id:q["native_inventory_id"].as_u64().unwrap()as u32,
        reservation_id:q["reservation_id"].as_str().unwrap().into(),remaining_ammunition:stacks("remaining_ammunition"),fired_ammunition:stacks("fired_ammunition"),lost_ammunition:stacks("lost_ammunition"),loss_event:None,
        terminal_hp:q["terminal_hp"].as_i64().unwrap()as i16,terminal_state_json:q["terminal_state_json"].as_str().unwrap().into(),
        reason:if q["reason"]=="manual_leave"{FinishReason::ManualLeave}else{FinishReason::BattleFinished},results_json:q["results_json"].as_str().map(str::to_owned)}
}
pub(super) struct Fixture{pub(super) capture:Capture,pub(super) world:World,pub(super) now:Instant,manual:handoff::TerminalLoss,finish_row:Value}
pub(super) fn fixture()->Fixture{
    let all=vectors();let rows=all["battle_vectors"].as_array().unwrap();let admitted=rows.iter().filter(|r|r["request"]["operation"]=="admit").collect::<Vec<_>>();assert_eq!(admitted.len(),2);
    let a=admission(admitted[0]);let b=admission(admitted[1]);assert_eq!(a.run_id,b.run_id);assert_eq!(a.battle,b.battle);
    let now=Instant::now();let mut world=World::new_for_roster(a.battle,now,MapId::Karelia,2).unwrap();
    world.bind_geometry(Arc::new(geometry::tests::bundle())).unwrap();world.bind_geometry(Arc::new(geometry::tests::is7_bundle())).unwrap();world.enable_ap_test_lab().unwrap();
    world.bind_terrain(Arc::new(terrain::tests::fixture(-1000.,2000.,2,vec![-100.;4]))).unwrap();world.enable_mixed_ammo().unwrap();
    world.enable_lifecycle(lifecycle::Rules{prebattle_ms:1000,battle_ms:60000,afterbattle_ms:1000,..lifecycle::Rules::prohorovka()}).unwrap();world.enable_ammo_detonation().unwrap();
    let saved_seal:Value=serde_json::from_str(all["append_vectors"][1]["request"]["seal_json"].as_str().unwrap()).unwrap();
    let saved_results:Results=Results::from_json_p06t(saved_seal["results_json"].as_str().unwrap()).unwrap();
    let mut capture=Capture::new(a.run_id.clone(),a.battle).unwrap();
    for (slot,reservation)in [a,b].into_iter().enumerate(){let c=context(admitted[slot]);let p=&saved_results.participants[slot];assert_eq!(p.account_dbid,c.native_database_id);
        let owner=Arc::new(identity091::Profile{account_id:c.account_id,database_id:c.native_database_id,name:p.name.clone(),fixture_dir:PathBuf::new()});
        // Admission proof is parsed from actual SQLite reply. Empty fixture path
        // is only unused transport metadata; no authenticated HTTP is claimed.
        world.attach_owned_loss(model::Identity{account:owner.account_id.clone(),database:owner.database_id,name:owner.name.clone()},slot as u32+1,&reservation.frozen).unwrap();
        capture.register(&world,slot,slot as u32+1,owner,Admission::Loss(reservation)).unwrap();
    }
    world.lifecycle_created_unix=Some(1792080000);world.start(now).unwrap();for slot in 0..2{world.set_ready(slot,slot as u32+1).unwrap();}
    world.advance_lifecycle(now).unwrap();world.advance_lifecycle(now+Duration::from_millis(1000)).unwrap();
    let Admission::Loss(r)=&capture.links[0].admission else{unreachable!()};
    let manual=handoff::TerminalLoss::from_actor_result(r,&world,0,1,FinishReason::ManualLeave,None).unwrap();
    let finish_row=rows.iter().find(|row|row["request"]["operation"]=="finish"&&row["request"]["reason"]=="manual_leave").unwrap().clone();
    assert_eq!(manual.request(),request(&finish_row),"real World snapshot matches actual committed manual request");
    capture.observe_terminal_loss(0,&manual).unwrap();Fixture{capture,world,now,manual,finish_row}
}
pub(super) fn settle_from_saved_actual_reply(f:&mut Fixture){
    let c=context(&f.finish_row);let q=request(&f.finish_row);let reply=loss::parse_reply(&serde_json::to_vec(&f.finish_row["response"]).unwrap(),&c,&q).unwrap();
    assert_eq!(reply.status,loss::Status::Finished);assert_eq!(q,f.manual.request());
    // Test-only pure observer seam: strict actual saved Finished reply was
    // parsed above. This does NOT claim a live Fresh/native delivery/HTTP job.
    f.capture.finished(0,reply.revision,&c.command_key).unwrap();
}
pub(super) fn final_outcome(f:&mut Fixture){f.world.detach(1).unwrap();f.world.advance_lifecycle(f.now+Duration::from_millis(1100)).unwrap();assert_eq!(f.world.lifecycle.as_ref().unwrap().outcome().unwrap().winner,2);}
#[test]fn p08c_late_capture_actual_owned_pair_forfeit_seals_before_world_disposal(){
    let mut f=fixture();settle_from_saved_actual_reply(&mut f);final_outcome(&mut f);assert!(f.capture.capture_final(&f.world).unwrap());
    let seal=f.capture.seal().unwrap().clone();let decoded=mixed::bounded_json(seal.raw().as_bytes(),MAX_SEAL).unwrap();
    assert_eq!(decoded["actors"].as_array().unwrap().len(),2);assert_eq!(decoded["battle_id"],format!("{}:{}",f.capture.run,f.capture.battle));
    assert_eq!(decoded["actors"][1]["vehicle_id"],wire::vehicle_id(1).unwrap());assert_eq!(seal.results().winner_team,2);
    assert_eq!(f.capture.eligible(0).unwrap(),Some(f.finish_row["response"]["revision"].as_u64().unwrap()));
    assert!(!f.capture.capture_final(&f.world).unwrap());let old=seal.raw().to_owned();drop(f.world);assert_eq!(f.capture.seal().unwrap().raw(),old);
}
#[test]fn p08c_late_capture_pending_finish_never_mints_release_or_append(){
    let mut f=fixture();final_outcome(&mut f);f.capture.capture_final(&f.world).unwrap();assert_eq!(f.capture.eligible(0).unwrap(),None);
    assert!(super::super::late_results_protocol::Task::release_stamp(&f.capture,0).is_err());
    settle_from_saved_actual_reply(&mut f);assert!(f.capture.eligible(0).unwrap().is_some());
}
#[test]fn p08c_late_capture_changed_parked_hp_explicitly_refuses_without_rewriting_terminal(){
    let mut f=fixture();settle_from_saved_actual_reply(&mut f);let old=f.capture.releases[0].clone();f.world.detach(1).unwrap();
    // AUTHORED state poison to exercise rejection, not a claimed geometry hit.
    f.world.actors[0].health-=1;f.world.advance_lifecycle(f.now+Duration::from_millis(1100)).unwrap();
    f.capture.capture_final(&f.world).unwrap();assert!(f.capture.eligible(0).unwrap_err().to_string().contains("LATE_ACTOR_STATE_CHANGED"));
    assert_eq!(f.capture.releases[0],old);assert_eq!(f.manual.terminal_hp,90);
}
#[test]fn p08c_late_capture_last_actor_poison_cannot_partially_seal(){
    let mut f=fixture();settle_from_saved_actual_reply(&mut f);final_outcome(&mut f);let admitted=f.capture.links[1].admission.clone();
    f.world.actors[1].owned_loss.as_mut().unwrap().sha256="0".repeat(64);assert!(f.capture.capture_final(&f.world).is_err());assert!(f.capture.seal().is_none());assert_eq!(f.capture.links[1].admission,admitted);
}
#[test]fn p08c_late_capture_foreign_native_cannot_rebind_existing_admission(){
    let mut f=fixture();let link=f.capture.links[0].clone();let owner=Arc::new(identity091::Profile{account_id:link.owner.account_id.clone(),database_id:99,name:link.owner.name.clone(),fixture_dir:PathBuf::new()});
    assert!(f.capture.register(&f.world,0,1,owner,link.admission.clone()).is_err());assert!(f.capture.links[0].same(&link));assert_eq!(f.capture.links.len(),2);
}
#[test]fn p08c_late_capture_final_outcome_required_and_natural_return_cannot_resnapshot_membership(){
    let mut f=fixture();assert!(f.capture.capture_final(&f.world).is_err());assert!(f.capture.seal().is_none());settle_from_saved_actual_reply(&mut f);final_outcome(&mut f);f.capture.capture_final(&f.world).unwrap();
    let old=f.capture.seal().unwrap().clone();assert!(!old.results().participants[1].premature_leave);
    f.world.detach(2).unwrap();assert!(!f.capture.capture_final(&f.world).unwrap());assert_eq!(f.capture.seal().unwrap().raw(),old.raw());
    assert!(!f.capture.seal().unwrap().results().participants[1].premature_leave);
}
/// RES-30: these observers are cloned by value on the gateway main thread
/// (Windows: 1MB). Rows for 30 actors live on the heap, not in the struct.
#[test]fn res30_late_capture_stays_small_on_the_stack(){
    assert!(std::mem::size_of::<Capture>()<=512,"Capture {}",std::mem::size_of::<Capture>());
    let c=Capture::new("87654321-4321-4321-8321-cba987654321".into(),7).unwrap();assert_eq!(c.releases.len(),MAX_ACTORS);
}
