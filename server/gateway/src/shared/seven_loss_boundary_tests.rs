//! Merge boundary regressions. Original stock geometry and actual saved loss4
//! DTO are used; extended flag poisoning and bad wrappers are explicitly
//! AUTHORED negative inputs, never a qualified extended owner or a grant.
use super::*;
use crate::{profile13_loss091 as loss,p06t_device_caps as caps,p06t_device_state as devices};
use sha2::{Digest,Sha256};

fn receipt()->(Identity,loss::Reservation){
    let raw=include_bytes!("../../../../tests/fixtures/p06t-ammo-loss-writer-vectors.json");
    assert_eq!(format!("{:x}",Sha256::digest(raw)),"251c60f587d14d916e5381567d8af2982b26f0f98335af8464b75bbf1cc1f154");
    let v:serde_json::Value=serde_json::from_slice(raw).unwrap();
    let row=v["vectors"].as_array().unwrap().iter().find(|r|r["request"]["operation"]=="admit").unwrap();let q=&row["request"];
    let c=loss::Context{account_id:q["account_id"].as_str().unwrap().into(),native_database_id:q["native_database_id"].as_i64().unwrap()as i32,
        run_id:q["run_id"].as_str().unwrap().into(),command_key:q["command_key"].as_str().unwrap().into(),expected_revision:q["expected_revision"].as_u64().unwrap()};
    let request=loss::Request::Admit{battle:q["battle_id"].as_str().unwrap().rsplit(':').next().unwrap().parse().unwrap(),
        native_inventory_id:q["native_inventory_id"].as_u64().unwrap()as u32};
    let actual=loss::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&c,&request).unwrap().reservation.unwrap();
    (Identity{account:c.account_id,database:c.native_database_id,name:"actual_loss_fixture_owner".into()},actual)
}
fn loss_template(now:Instant,battle:u64)->World{
    let mut w=World::new_for_roster(battle,now,crate::map_profile091::MapId::Karelia,2).unwrap();
    w.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).unwrap();
    w.bind_geometry(Arc::new(super::super::geometry::tests::is7_bundle())).unwrap();
    w.enable_ap_test_lab().unwrap();
    w.bind_terrain(Arc::new(super::super::terrain::tests::fixture(-1000.,2000.,2,vec![-100.;4]))).unwrap();
    w.enable_mixed_ammo().unwrap();w.enable_lifecycle(super::super::lifecycle::Rules::prohorovka()).unwrap();w
}
fn unchanged(w:&World)->(String,bool,[bool;MAX_ACTORS]){
    (w.failure_snapshot().to_string(),w.extended_lab,w.lab_loadouts.map(|loadout|loadout.is_some()))
}
#[test]fn p06t_seven_loss_policy_refuses_extended_flag_before_enabling_ledger(){
    let now=Instant::now();let mut w=loss_template(now,1001);
    // Prove all original loss prerequisites were met by the source-backed twin.
    let mut twin=w.clone();twin.enable_ammo_detonation().unwrap();assert!(twin.ammo_detonation_enabled());
    // AUTHORED cross-policy flag poison, not an enabled seven-profile resource.
    w.extended_lab=true;let before=unchanged(&w);
    assert!(w.enable_ammo_detonation().is_err());assert_eq!(unchanged(&w),before);assert!(!w.ammo_detonation_enabled());
}
#[test]fn p06t_seven_loss_actual_wrapper_cannot_attach_into_extended_mode(){
    let(now,(who,r))=(Instant::now(),receipt());let mut w=loss_template(now,r.battle);w.enable_ammo_detonation().unwrap();
    w.extended_lab=true;let before=unchanged(&w);
    assert!(w.attach_owned_loss(who,17,&r.frozen).is_err());assert_eq!(unchanged(&w),before);assert!(w.actors.is_empty());
}
#[test]fn p06t_seven_loss_forged_extended_wrapper_and_old_cancel_refuse_before_actor_mutation(){
    let(now,(who,r))=(Instant::now(),receipt());
    for kind in[VehicleKind::Wt128,VehicleKind::Fv183]{
        let mut w=loss_template(now,r.battle);w.enable_ammo_detonation().unwrap();let before=unchanged(&w);
        // Poison one actual DTO field while retaining its real original hash:
        // this must never acquire ownership merely because Kind now has seven.
        let mut forged=r.frozen.clone();forged.base.kind=kind;
        assert!(w.attach_owned_loss(who.clone(),17,&forged).is_err());assert_eq!(unchanged(&w),before);
        assert!(World::cancelled_terminal_state(&forged.base).is_err());assert_eq!(unchanged(&w),before);
        assert!(w.actors.is_empty());
    }
}
#[test]fn p06t_seven_loss_public_leaf_refuses_extended_input_without_panic_or_tombstone(){
    let mut ledger=super::super::ammo_detonation::Ledger::new(2).unwrap();
    let mut input=super::super::ammo_detonation::Input{shot:1,target:1,attacker:0,tick:1000,device_sequence:1,
        device_before:1,device_after:0,health_before:90,residual_hp:3,counts:[1,0,0],kind:VehicleKind::Ms1,
        joint:super::super::ammo_detonation::JointPose{position:[0.;3],direction:[0.;3]},from_fire:false};
    for kind in[VehicleKind::Wt128,VehicleKind::Fv183]{input.kind=kind;
        assert!(ledger.apply(input).is_err());assert!(ledger.is_pristine());assert!(ledger.events().is_empty());}
    input.kind=VehicleKind::Ms1;input.device_before=60;
    assert!(matches!(ledger.apply(input).unwrap(),super::super::ammo_detonation::Outcome::New(event)
        if event.lost()==[1,0,0]&&event.additional_damage()==3));
}
#[test]fn p06t_seven_loss_keeps_old_device_contract_closed_and_new_policy_explicit(){
    assert_eq!(VehicleKind::ALL.len(),5);assert_eq!(caps::Profile::ALL.len(),5);
    for kind in[VehicleKind::Wt128,VehicleKind::Fv183]{
        assert!(VehicleKind::from_label(kind.label()).is_none());assert!(!kind.battle_admission());
        let profile=caps::Profile::SUPPORTED[kind.index()];assert!(devices::State::new(profile).is_err());
        let state=devices::State::new_v2(profile).unwrap();assert_eq!(state.policy_revision(),devices::POLICY_V2);
    }
}
