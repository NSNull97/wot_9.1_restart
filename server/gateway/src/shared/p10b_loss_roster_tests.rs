//! Pristine Loss4 roster constructor component tests. All ledger/lifecycle
//! poison inputs below are explicitly AUTHORED. No collision/owned admission,
//! ReadyRef, reservation or durable Finished proof is constructed.
use super::*;
use super::super::{ammo_detonation as rack,geometry,terrain,p10b_team_plan::TeamPlan};
fn source(id:u64,now:Instant)->World{
    let mut w=World::new_for_roster(id,now,crate::map_profile091::MapId::Karelia,6).unwrap();
    w.bind_geometry(Arc::new(geometry::tests::bundle())).unwrap();w.bind_geometry(Arc::new(geometry::tests::is7_bundle())).unwrap();w.enable_ap_test_lab().unwrap();
    w.bind_terrain(Arc::new(terrain::tests::fixture(-1000.,2000.,2,vec![-100.;4]))).unwrap();w.enable_mixed_ammo().unwrap();
    w.enable_lifecycle(super::super::lifecycle::Rules::prohorovka()).unwrap();w.enable_result_spots().unwrap();w.enable_ammo_detonation().unwrap();w
}
fn input(target:usize,empty:bool)->rack::Input{rack::Input{shot:1,target,attacker:0,tick:1000,device_sequence:1,device_before:1,device_after:0,
    health_before:90,residual_hp:42,counts:if empty{[0;3]}else{[1,0,0]},kind:VehicleKind::Ms1,
    joint:rack::JointPose{position:[0.,2.,0.],direction:[0.;3]},from_fire:false}}
#[test]
fn p10b_loss_roster_N2_to6_same_or_new_id_rebinds_empty_ledger_without_source_mutation(){
    let now=Instant::now();let original=source(951,now);
    // RES-30: rosters 7..30 select the same pristine loss template.
    for n in [2,3,4,5,6,7,30]{for id in [951,952]{
        let mut selected=original.fresh_loss_roster(id,n,now+Duration::from_secs(2)).unwrap();
        assert_eq!(selected.id,id);assert_eq!(selected.last,now+Duration::from_secs(2));assert_eq!(selected.rng_state,id);assert_eq!(selected.tick,1000);
        assert_eq!(selected.expected_actors(),n);assert!(selected.team_plan().is_none());assert!(selected.actors.is_empty()&&selected.started.is_none());
        assert!(selected.lifecycle.as_ref().unwrap().is_pristine());assert!(selected.ammo_detonation.as_ref().unwrap().is_pristine());
        assert_eq!(selected.result_spots(),Some(&[][..]));assert_eq!(selected.result_spot_tick,None);
        assert!(Arc::ptr_eq(selected.geometry_for(VehicleKind::Ms1).unwrap(),original.geometry_for(VehicleKind::Ms1).unwrap()));
        assert!(Arc::ptr_eq(selected.terrain.as_ref().unwrap(),original.terrain.as_ref().unwrap()));
        assert_eq!(selected.vehicle_kind,original.vehicle_kind);assert_eq!(selected.mixed_ammo,original.mixed_ammo);assert_eq!(selected.extended_lab,original.extended_lab);
        let ledger=selected.ammo_detonation.as_mut().unwrap();assert!(ledger.apply(input(n,false)).is_err());assert!(ledger.is_pristine());
        assert!(matches!(ledger.apply(input(n-1,false)).unwrap(),rack::Outcome::New(_)));
        assert_eq!(ledger.events()[0].target(),n-1);assert_eq!(original.expected_actors(),6);assert!(original.ammo_detonation.as_ref().unwrap().is_pristine());
    }}
    for n in [0,1,31]{assert!(original.fresh_loss_roster(952,n,now).is_err());}
    assert!(original.fresh_loss_roster(0,2,now).is_err());assert!(original.fresh_loss_roster(i64::MAX as u64+1,2,now).is_err());
    assert!(original.fresh_battle(original.id,now).is_err());
    let mut legacy_setter=original.clone();assert!(legacy_setter.set_expected_actors(2).is_err());assert!(legacy_setter.set_expected_actors(6).is_err());
    assert_eq!(legacy_setter.expected_actors(),6);assert!(legacy_setter.ammo_detonation.as_ref().unwrap().is_pristine());
}
#[test]
fn p10b_loss_roster_rejects_used_event_and_empty_rack_seen_tombstone(){
    let now=Instant::now();for empty in [false,true]{let mut used=source(961,now);
        let outcome=used.ammo_detonation.as_mut().unwrap().apply(input(1,empty)).unwrap();
        assert!(matches!(outcome,rack::Outcome::New(_))!=empty);
        assert_eq!(used.ammo_detonations().is_empty(),empty);assert!(!used.ammo_detonation.as_ref().unwrap().is_pristine());
        assert!(used.fresh_loss_roster(961,2,now).is_err());assert!(used.fresh_loss_roster(962,6,now).is_err());
        assert_eq!(used.expected_actors(),6);assert_eq!(used.ammo_detonations().len(),usize::from(!empty));
    }
}
fn members(ready:bool)->[super::super::lifecycle::Member;2]{std::array::from_fn(|i|super::super::lifecycle::Member{
    team:i as u8+1,present:true,ready,alive:true,position:[500.,0.,500.],damage_epoch:0,last_damager:None})}
#[test]
fn p10b_loss_roster_rejects_tick_waiting_clock_countdown_and_outcome_without_actors(){
    let now=Instant::now();let original=source(971,now);let mut tick=original.clone();tick.tick=1001;assert!(tick.fresh_loss_roster(972,2,now).is_err());
    let mut waiting=original.clone();let life=waiting.lifecycle.as_mut().unwrap();assert!(life.is_pristine());assert!(!life.advance(500,&members(false)).unwrap());
    assert_eq!(life.phase(),super::super::lifecycle::Phase::Waiting);assert_eq!(life.revision(),1);assert!(!life.is_pristine());
    assert!(waiting.fresh_battle(972,now).is_ok(),"old API stays unchanged; new constructor owns the stronger guard");assert!(waiting.fresh_loss_roster(972,2,now).is_err());
    let mut countdown=original.clone();countdown.lifecycle.as_mut().unwrap().advance(0,&members(true)).unwrap();
    assert_eq!(countdown.lifecycle.as_ref().unwrap().phase(),super::super::lifecycle::Phase::Prebattle);assert!(countdown.actors.is_empty());assert!(countdown.fresh_loss_roster(972,2,now).is_err());
    let mut ended=original.clone();let mut departed=members(false);departed[0].present=false;ended.lifecycle.as_mut().unwrap().advance(0,&departed).unwrap();
    assert!(ended.lifecycle.as_ref().unwrap().outcome().is_some());assert!(ended.actors.is_empty());assert!(ended.fresh_loss_roster(972,2,now).is_err());
}
#[test]
fn p10b_loss_roster_rejects_team_plan_flights_and_visual_cursor_before_publish(){
    let now=Instant::now();let original=source(981,now);let mut planned=original.clone();planned.set_team_plan(TeamPlan::new(&[1,2,1,2,1,2]).unwrap()).unwrap();
    assert!(planned.fresh_loss_roster(982,2,now).is_err());assert!(planned.team_plan().is_some());
    let mut ledger=rack::Ledger::new(6).unwrap();let rack::Outcome::New(event)=ledger.apply(input(1,false)).unwrap()else{panic!("AUTHORED leaf event required")};
    let mut flight=original.clone();flight.turret_flights.push(rack::Flight::new(event));assert!(flight.fresh_loss_roster(982,2,now).is_err());assert_eq!(flight.turret_flights.len(),1);
    let mut cursor=original.clone();cursor.turret_visual_ms=Some(0);assert!(cursor.fresh_loss_roster(982,2,now).is_err());assert_eq!(cursor.turret_visual_ms,Some(0));
    let mut created=original.clone();created.lifecycle_created_unix=Some(1);assert!(created.fresh_loss_roster(982,2,now).is_err());
}
#[test]
fn p10b_loss_roster_preserves_old_mode_and_rejects_LAB_or_missing_source_prerequisites(){
    let now=Instant::now();let original=source(991,now);
    for variant in 0..8{let mut invalid=original.clone();match variant{
        0=>invalid.ammo_detonation=None,1=>invalid.mixed_ammo=false,2=>invalid.mixed_profiles=false,3=>invalid.ap_test_lab=false,
        4=>invalid.terrain=None,5=>invalid.lifecycle=None,6=>invalid.extended_lab=true,_=>invalid.vehicle_kind=VehicleKind::Wt128,
    }assert!(invalid.fresh_loss_roster(992,2,now).is_err());assert_eq!(invalid.expected_actors(),6);}
    let mut old=original.clone();old.ammo_detonation=None;assert!(old.set_expected_actors(2).is_ok());assert!(!old.ammo_detonation_enabled());
    assert_eq!(original.expected_actors(),6);assert!(original.ammo_detonation.as_ref().unwrap().is_pristine());
}
