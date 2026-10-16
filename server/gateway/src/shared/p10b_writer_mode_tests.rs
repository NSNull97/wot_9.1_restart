//! Typed host-boundary tests. Actual saved writer DTOs; no HTTP/native claim.
use super::*;
use serde_json::Value;
use sha2::{Digest,Sha256};
use std::time::Instant;
fn loss_receipt()->Reservation{
    let raw=include_bytes!("../../../../tests/fixtures/p06t-ammo-loss-writer-vectors.json");
    assert_eq!(format!("{:x}",Sha256::digest(raw)),"251c60f587d14d916e5381567d8af2982b26f0f98335af8464b75bbf1cc1f154");
    let v:Value=serde_json::from_slice(raw).unwrap();let row=v["vectors"].as_array().unwrap().iter().find(|r|r["request"]["operation"]=="admit").unwrap();let q=&row["request"];
    let c=Context{account_id:q["account_id"].as_str().unwrap().into(),native_database_id:q["native_database_id"].as_i64().unwrap()as i32,
        run_id:q["run_id"].as_str().unwrap().into(),expected_revision:q["expected_revision"].as_u64().unwrap(),command_key:q["command_key"].as_str().unwrap().into()};
    let r=loss::Request::Admit{battle:q["battle_id"].as_str().unwrap().rsplit(':').next().unwrap().parse().unwrap(),native_inventory_id:1};
    Reservation::Loss(loss::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&c,&r).unwrap().reservation.unwrap())
}
fn source_world(battle:u64,loss:bool)->World{
    let now=Instant::now();let mut w=World::new_for_roster(battle,now,crate::map_profile091::MapId::Karelia,2).unwrap();w.enable_mixed_ammo().unwrap();
    w.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).unwrap();w.bind_geometry(Arc::new(super::super::geometry::tests::is7_bundle())).unwrap();w.enable_ap_test_lab().unwrap();
    w.bind_terrain(Arc::new(super::super::terrain::tests::fixture(-1000.,2000.,2,vec![-100.;4]))).unwrap();
    w.enable_lifecycle(super::super::lifecycle::Rules::prohorovka()).unwrap();if loss{w.enable_ammo_detonation().unwrap();}w
}
fn who(r:&Reservation)->Identity{Identity{account:r.loadout().vehicle_inventory_id[..36].into(),database:1,name:"AUTHORED typed host fixture".into()}}
#[test]fn p10b_loss_host_mode_requires_explicit_training_flag_and_keeps_old_default(){
    assert!(Mode::checked(false,false).is_err());assert!(Mode::checked(false,true).is_err());
    assert_eq!(Mode::checked(true,false).unwrap(),Mode::MixedV2);assert_eq!(Mode::checked(true,true).unwrap(),Mode::LossV4);assert_eq!(Mode::default(),Mode::MixedV2);
}
#[test]fn p10b_loss_host_receipt_installs_only_loss_field_and_refuses_conflicting_run_or_claim(){
    let r=loss_receipt();let mut state=service::State::new(r.run_id().into(),18).unwrap();r.install(&mut state).unwrap();
    let Reservation::Loss(actual)=&r else{panic!("actual loss4 receipt")};assert_eq!(state.reservation_loss.as_ref(),Some(actual));
    assert!(state.reservation_v2.is_none()&&state.reservation.is_none());let before=state.clone();assert!(r.install(&mut state).is_err());assert_eq!(state,before);
    let mut wrong=service::State::new("12345678-1234-4234-8234-123456789abc".into(),18).unwrap();let before=wrong.clone();assert!(r.install(&mut wrong).is_err());assert_eq!(wrong,before);
}
#[test]fn p10b_loss_host_wrong_template_refuses_before_actor_or_inventory_mutation(){
    let r=loss_receipt();let mut w=source_world(r.battle(),false);assert!(w.actors.is_empty());
    assert!(r.attach(&mut w,who(&r),101).is_err());assert!(w.actors.is_empty());assert!(!w.ammo_detonation_enabled());
}
#[test]fn p10b_loss_host_actual_source_attach_retains_wrapper_policy_and_three_stacks(){
    let r=loss_receipt();let mut w=source_world(r.battle(),true);let slot=r.attach(&mut w,who(&r),101).unwrap();assert_eq!(slot,0);
    let Reservation::Loss(actual)=&r else{panic!("actual loss4 receipt")};let actor=&w.actors[slot];
    assert_eq!(actor.owned_loss.as_ref(),Some(&actual.frozen));assert_eq!(actor.fire.typed().unwrap().counts(),actual.frozen.base.counts());
    assert_eq!(actor.fire.typed().unwrap().accepted(),0);assert!(w.ammo_detonations().is_empty());assert!(w.started.is_none());
}
#[test]fn p10b_loss_host_late_link_uses_actual_attached_wrapper_and_rejects_v2_relabel(){
    let r=loss_receipt();let mut w=source_world(r.battle(),true);let identity=who(&r);
    let owner=Arc::new(identity091::Profile{account_id:identity.account.clone(),database_id:identity.database,
        name:identity.name.clone(),fixture_dir:std::path::PathBuf::new()});
    let slot=r.attach(&mut w,identity,101).unwrap();
    let mut capture=super::super::late_results_capture::Capture::new(r.run_id().into(),r.battle()).unwrap();
    assert!(capture.register(&w,slot,101,owner.clone(),r.late_admission()).unwrap());
    assert!(!capture.register(&w,slot,101,owner.clone(),r.late_admission()).unwrap());
    assert_eq!(capture.links().len(),1);assert_eq!(capture.links()[0].admission().source_contract(),"loss-v1");
    let Reservation::Loss(loss)=r else{panic!("actual loss4")};
    let relabel=super::super::late_results_capture::Admission::Mixed(v2::Reservation{
        reservation_id:loss.reservation_id,run_id:loss.run_id,battle:loss.battle,frozen:loss.frozen.base,
        status:v2::ReservationStatus::Active,result:None});
    assert!(capture.register(&w,slot,101,owner,relabel).is_err());assert_eq!(capture.links().len(),1);
}

fn ready_pair()->Vec<ReadySelection>{
    // AUTHORED selection4 stamp/reply; only the old selection and both Frozen
    // source payloads are actual saved project DTOs. No real HTTP ready claim.
    let raw=include_bytes!("../../../../tests/fixtures/p10b-selection-writer-vectors.json");
    assert_eq!(format!("{:x}",Sha256::digest(raw)),"493511296d5c3b09fa1ce5d9906b48d565b02eab345191659d079d1294e7da97");
    let v:Value=serde_json::from_slice(raw).unwrap();let row=&v["vectors"][0];let q=&row["request"];
    let c=Context{account_id:q["account_id"].as_str().unwrap().into(),native_database_id:q["native_database_id"].as_i64().unwrap()as i32,run_id:q["run_id"].as_str().unwrap().into(),
        expected_revision:q["expected_revision"].as_u64().unwrap(),command_key:"authored:read-only".into()};
    let b=selection::Stamp::parse(&q["projection_stamp"]).unwrap();let request=selection::Request::new(&c,1,b.clone()).unwrap();
    let selected=selection::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&request).unwrap();
    let profile=|c:&Context|Arc::new(identity091::Profile{account_id:c.account_id.clone(),database_id:c.native_database_id,name:format!("AUTHORED mode{}",c.native_database_id),fixture_dir:std::path::PathBuf::new()});
    let old=ReadySelection::from_selection(profile(&c),101,selected).unwrap();
    let Reservation::Loss(receipt)=loss_receipt()else{panic!("loss receipt")};let owner=receipt.frozen.base.vehicle_inventory_id[..36].to_owned();
    let c=Context{account_id:owner,native_database_id:1,run_id:receipt.run_id.clone(),expected_revision:17,command_key:"authored:loss-read-only".into()};
    let stamp=selection_loss::Stamp{base:b,loss_policy_sha256:loss::POLICY_SHA256.into(),loss_companion_sha256:"a".repeat(64)};
    let request=selection_loss::Request::new(&c,1,stamp).unwrap();
    let actual:Value=serde_json::from_slice(include_bytes!("../../../../tests/fixtures/p06t-ammo-loss-writer-vectors.json")).unwrap();
    let a=actual["vectors"].as_array().unwrap().iter().find(|r|r["request"]["operation"]=="admit").unwrap();
    let mut reply=serde_json::json!({"version":4,"contract":loss::CONTRACT,"schema":selection_loss::SCHEMA,"operation":"select","status":"ready", "account_id":c.account_id,
        "native_database_id":1,"run_id":c.run_id,"native_inventory_id":1,"revision":17,"projection_stamp":request.projection_stamp.value(),"aggregate_sha256":"b".repeat(64),
        "frozen":a["response"]["reservation"]["frozen"],"frozen_sha256":receipt.frozen.sha256});
    let mut binding=reply.clone();for k in["version","operation","status","frozen"]{binding.as_object_mut().unwrap().remove(k);}
    reply["fingerprint"]=format!("{:x}",Sha256::digest(serde_json::to_vec(&binding).unwrap())).into();
    let selected=selection_loss::parse_reply(&serde_json::to_vec(&reply).unwrap(),&request).unwrap();
    vec![old,ReadySelection::from_selection(profile(&c),102,selected).unwrap()]
}
#[test]fn p10b_loss_host_mixed_v2_v4_roster_is_refused_before_issuing_any_writer_task(){
    let selected=ready_pair();assert_ne!(selected[0].mode(),selected[1].mode());let mut registry=room::Registry::default();
    let leases=selected.iter().map(|s|room::AuthLease{account:s.reference().owner(),generation:1}).collect::<Vec<_>>();
    for (s,l)in selected.iter().zip(&leases){registry.bind_authenticated(*l,s.owner().name.clone(),0).unwrap();}
    registry.command(leases[0],room::Command::Create(room::Settings{capacity:2,map:room::QualifiedMap::Prohorovka,seconds:600,opened:true,comment:String::new()}),0).unwrap();
    let key=registry.authenticated_room(leases[0]).unwrap();registry.command(leases[1],room::Command::Join(key),0).unwrap();
    registry.command(leases[0],room::Command::Assign{target:leases[1].account,roster:room::Roster::assigned(room::Side::Two)},0).unwrap();
    for (s,l)in selected.iter().zip(&leases){let context=registry.selection_context(*l).unwrap();registry.command(*l,room::Command::Ready{context,selection:s.reference().clone()},0).unwrap();}
    registry.command(leases[0],room::Command::TeamReady{side:room::Side::One,ready:true,force:true},0).unwrap();
    let snapshot=registry.command(leases[0],room::Command::TeamReady{side:room::Side::Two,ready:true,force:true},0).unwrap().into_iter().find_map(|e|if let room::Event::Prepare(s)=e{Some(s)}else{None}).unwrap();
    assert!(Saga::new(snapshot,room::BattleKey(9007199254740993),selected).is_err());
    for l in leases{assert_eq!(registry.claim(l.account),Some(room::Claim::Room(key)));}
}
