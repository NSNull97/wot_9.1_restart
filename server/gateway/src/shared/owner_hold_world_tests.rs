//! Child of existing ammo_detonation_world_tests, reusing the genuine bounded
//! exterior-ray search. C/D Frozen5/CAS come from actual SQL; two sustainers in
//! the four-actor test are explicitly AUTHORED physical actors, not owned grants.
use super::*;
use crate::profile13_hold091 as hold;
use crate::gateway091::shared::owner_hold_capture::Capture;
fn source_admissions()->Vec<(Arc<crate::identity091::Profile>,hold::Reservation,u64)>{
    let raw=include_bytes!("../../../../tests/fixtures/p08b-owner-hold-first-vectors.json");
    assert_eq!(format!("{:x}",Sha256::digest(raw)),"70b36eb6d441a9b9c799bdd7d7a55512bc9f4508ef9e2ef1091f7dd481730321");
    let data:serde_json::Value=serde_json::from_slice(raw).unwrap();let mut out=Vec::new();
    for(row,name)in[(&data["vectors"][1],"ExtendedCTest"),(&data["vectors"][3],"ExtendedDTest")]{
        let q=&row["request"];let c=hold::Context{account_id:q["account_id"].as_str().unwrap().into(),native_database_id:q["native_database_id"].as_i64().unwrap()as i32,
            command_key:q["command_key"].as_str().unwrap().into(),expected_revision:q["expected_revision"].as_u64().unwrap(),run_id:q["run_id"].as_str().unwrap().into()};
        let req=hold::Request::Admit{battle:q["battle_id"].as_str().unwrap().rsplit(':').next().unwrap().parse().unwrap(),native_inventory_id:q["native_inventory_id"].as_u64().unwrap()as u32};
        let r=hold::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&c,&req).unwrap();
        out.push((Arc::new(crate::identity091::Profile{account_id:c.account_id,database_id:c.native_database_id,name:name.into(),fixture_dir:std::path::PathBuf::new()}),r.reservation.unwrap(),r.revision));
    }out
}
fn hold_template(now:Instant,battle:u64,count:usize)->World{
    let mut w=World::new_for_roster(battle,now,crate::map_profile091::MapId::Karelia,count).unwrap();
    w.bind_geometry(Arc::new(super::super::super::super::geometry::tests::bundle())).unwrap();
    w.bind_geometry(Arc::new(super::super::super::super::geometry::tests::is7_bundle())).unwrap();
    w.enable_ap_test_lab().unwrap();w.bind_terrain(Arc::new(super::super::super::super::terrain::tests::fixture(-1000.,2000.,2,vec![-100.;4]))).unwrap();
    w.enable_mixed_ammo().unwrap();w.enable_lifecycle(super::super::super::super::lifecycle::Rules{prebattle_ms:1000,battle_ms:60000,
        ..super::super::super::super::lifecycle::Rules::prohorovka()}).unwrap();
    w.enable_ammo_detonation().unwrap();w.enable_result_spots().unwrap();w.enable_owner_hold().unwrap();w
}
fn attach_actual(w:&mut World,rows:&[(Arc<crate::identity091::Profile>,hold::Reservation,u64)])->Capture{
    let mut capture=Capture::new(rows[0].1.run_id.clone(),rows[0].1.battle).unwrap();
    for(slot,(owner,r,revision))in rows.iter().enumerate(){let sid=slot as u32+1;
        let who=Identity{account:owner.account_id.clone(),database:owner.database_id,name:owner.name.clone()};
        assert_eq!(w.attach_owned_hold(who,sid,&r.frozen).unwrap(),slot);
        capture.register(w,slot,sid,owner.clone(),r.clone(),*revision).unwrap();
    }capture
}
fn start_all(w:&mut World,now:Instant){
    w.actors[0].position=[0.;3];w.actors[0].origin=[0.;3];w.actors[1].position=[0.,0.,20.];w.actors[1].origin=[0.,0.,20.];
    w.start(now).unwrap();w.lifecycle_created_unix=Some(1792152000);
    for i in 0..w.actors.len(){w.set_ready(i,i as u32+1).unwrap();}w.advance_lifecycle(now).unwrap();
}
#[test]fn p08b_hold5_actual_two_source_owned_outcome_seals_from_world_not_manual_terminal(){
    let rows=source_admissions();let now=Instant::now();let mut w=hold_template(now,rows[0].1.battle,2);let mut capture=attach_actual(&mut w,&rows);start_all(&mut w,now);
    advance_until(&mut w,now+Duration::from_secs(1));w.detach(1).unwrap();
    assert!(capture.departed_after_detach(&w,0,1,hold::DepartureReason::ManualLeave).unwrap());
    advance_until(&mut w,now+Duration::from_millis(1100));assert!(w.lifecycle.as_ref().unwrap().outcome().is_some());
    assert!(capture.freeze_outcome(&w).unwrap());let seal=capture.seal().unwrap();
    for slot in 0..2{let finish=seal.finish(slot).unwrap();assert_eq!(finish.finalization,hold::Finalization::Outcome{tick:1011});
        finish.validate_against(&capture.link(slot).unwrap().context(true),&rows[slot].1).unwrap();}
    assert_eq!(seal.finish(0).unwrap().departure.unwrap().reason,hold::DepartureReason::ManualLeave);
    let before=seal.finish(0).unwrap().clone();assert!(!capture.departed_after_detach(&w,0,1,hold::DepartureReason::Disconnect).unwrap());
    assert_eq!(capture.seal().unwrap().finish(0).unwrap(),&before);
}
#[test]fn p08b_hold5_partial_n4_actual_parked_owned_body_detonates_while_authored_sides_sustain_battle(){
    let rows=source_admissions();let now=Instant::now();let mut w=hold_template(now,rows[0].1.battle,4);let mut capture=attach_actual(&mut w,&rows);
    for slot in 2..4{
        // Explicit test-only physical/lifecycle sustainers. Their clone source
        // shape is MS1, but no SQL Frozen/receipt/ownership is claimed.
        let mut a=w.actors[slot%2].clone();a.identity=Identity{account:format!("AUTHORED-hold-sustainer-{slot}"),database:2000+slot as i32,name:format!("AUTHORED-{slot}")};
        a.session=Some(slot as u32+1);a.owned_v2=None;a.owned_loss=None;a.owned_hold=None;a.position=[80.,0.,80.+slot as f32*20.];a.origin=a.position;
        w.impact.bind_actor(slot,VehicleKind::Ms1).unwrap();w.actors.push(a);
    }
    start_all(&mut w,now);let(mut w,_)=first_rack_hit(&w,now);assert_eq!(w.actors[1].health,60);
    w.detach(2).unwrap();capture.departed_after_detach(&w,1,2,hold::DepartureReason::ManualLeave).unwrap();
    let original=rows[1].1.clone();assert!(capture.seal().is_none());assert_eq!(capture.link(1).unwrap().reservation(),&original);
    advance_until(&mut w,now+Duration::from_secs(5));assert_eq!(w.lifecycle.as_ref().unwrap().phase(),super::super::super::super::lifecycle::Phase::Battle);
    assert!(matches!(w.apply(0,1,&[Command::Armament(arm::Command::Shoot)],now+Duration::from_secs(5)).unwrap().as_slice(),[fire::Outcome::Typed(arm::Outcome::Shot{..})]));
    w.advance(now+Duration::from_secs(5)+STEP).unwrap();w.advance_lifecycle(now+Duration::from_secs(5)+STEP).unwrap();
    assert_eq!(w.lifecycle.as_ref().unwrap().phase(),super::super::super::super::lifecycle::Phase::Battle);
    assert_eq!(w.actors[1].session,None);assert_eq!(w.actors[1].health,0);assert_eq!(w.ammo_detonations().len(),1);assert_eq!(w.ammo_detonations()[0].lost(),[0,4,10]);
    assert_eq!(w.actors[1].fire.accepted_shots(),0);assert_eq!(w.actors[1].fire.typed().unwrap().counts(),[0;3]);
    // This component has two real owned links and two authored sustainers; a
    // whole-owned Outcome is intentionally refused, not called a 4-owner proof.
    assert!(capture.freeze_outcome(&w).is_err());assert!(capture.seal().is_none());
    assert!(capture.freeze_contained_failure(&w).unwrap());let seal=capture.seal().unwrap();let f=seal.finish(1).unwrap();
    assert_eq!(f.reason,hold::FinishReason::BattleFailure);assert_eq!(f.lost.map(|r|r.count),[0,4,10]);assert_eq!(f.remaining.map(|r|r.count),[0;3]);assert!(f.results_json.is_none());
    f.validate_against(&capture.link(1).unwrap().context(true),&original).unwrap();
    assert_eq!(seal.finish(0).unwrap().fired.map(|r|r.count),[0,2,0]);
}
#[test]fn p08b_hold5_no_implicit_four_reinterpretation_or_account_reattach(){
    let rows=source_admissions();let now=Instant::now();let mut w=hold_template(now,rows[0].1.battle,2);
    let who=Identity{account:rows[0].0.account_id.clone(),database:rows[0].0.database_id,name:rows[0].0.name.clone()};
    assert!(w.attach_owned_loss(who.clone(),1,rows[0].1.frozen.loss()).is_err());assert!(w.actors.is_empty());
    w.attach_owned_hold(who.clone(),1,&rows[0].1.frozen).unwrap();w.detach(1).unwrap();let snapshot=w.failure_snapshot();
    assert!(w.attach_owned_hold(who,99,&rows[0].1.frozen).is_err());assert_eq!(w.failure_snapshot(),snapshot);assert!(w.enable_owner_hold().is_err());
}
