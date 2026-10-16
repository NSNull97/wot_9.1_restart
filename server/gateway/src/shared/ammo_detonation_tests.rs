use super::*;
fn input()->Input{Input{shot:1,target:1,attacker:0,tick:1010,device_sequence:3,device_before:12,device_after:0,
    health_before:90,residual_hp:18,counts:[2,3,4],kind:VehicleKind::Ms1,
    joint:JointPose{position:[0.,1.,0.],direction:[0.;3]},from_fire:false}}
fn event()->Event{let Outcome::New(event)=Ledger::new(2).unwrap().apply(input()).unwrap()else{panic!("expected real nonempty policy event")};event}
#[test]fn p06t_ammo_detonation_nonempty_exact_three_stacks_and_one_lethal_remainder(){
    let e=event();assert_eq!(e.policy(),POLICY);assert_eq!(e.lost(),[2,3,4]);assert_eq!(e.additional_damage(),18);
    let ordinary_plate_damage=e.health_before()-18;
    assert_eq!(ordinary_plate_damage,72);assert_eq!(ordinary_plate_damage+e.additional_damage(),90);assert_eq!(e.final_hp(),0);
    assert_eq!((e.shot(),e.attacker(),e.target(),e.tick(),e.device_sequence()),(1,0,1,1010,3));
    assert_eq!(e.born_ms(),1000);assert!(!e.from_fire());
}
#[test]fn p06t_ammo_detonation_empty_after_last_shot_has_no_event_or_visual(){
    let mut l=Ledger::new(2).unwrap();let empty=Input{counts:[0;3],..input()};
    assert_eq!(l.apply(empty).unwrap(),Outcome::Empty);assert!(l.events().is_empty());
    assert_eq!(l.apply(empty).unwrap(),Outcome::Replay(None));
    let before=l.clone();assert!(l.apply(input()).is_err());assert_eq!(l,before);
}
#[test]fn p06t_ammo_detonation_plate_already_lethal_still_loses_loaded_without_extra_hp(){
    let mut l=Ledger::new(2).unwrap();let Outcome::New(e)=l.apply(Input{residual_hp:0,..input()}).unwrap()else{panic!()};
    assert_eq!(e.additional_damage(),0);assert_eq!(e.lost(),[2,3,4]);assert_eq!(e.final_hp(),0);
}
#[test]fn p06t_ammo_detonation_identical_replay_no_second_loss_and_changed_replay_atomic(){
    let mut l=Ledger::new(2).unwrap();let Outcome::New(e)=l.apply(input()).unwrap()else{panic!()};
    assert_eq!(l.apply(input()).unwrap(),Outcome::Replay(Some(e)));assert_eq!(l.events().len(),1);
    for changed in [Input{shot:2,..input()},Input{attacker:1,..input()},Input{counts:[2,3,3],..input()},
        Input{device_sequence:4,..input()},Input{joint:JointPose{position:[-0.,1.,0.],direction:[0.;3]},..input()}]{
        let before=l.clone();assert!(l.apply(changed).is_err());assert_eq!(l,before);
    }
}
#[test]fn p06t_ammo_detonation_bounds_and_source_maxima_reject_without_journal_mutation(){
    let mut l=Ledger::new(2).unwrap();
    for bad_input in [Input{shot:0,..input()},Input{shot:961,..input()},Input{target:2,..input()},Input{attacker:2,..input()},
        Input{tick:999,..input()},Input{tick:37001,..input()},Input{device_sequence:0,..input()},
        Input{device_before:0,..input()},Input{device_before:61,..input()},Input{device_after:1,..input()},
        Input{health_before:0,..input()},Input{health_before:91,..input()},Input{residual_hp:91,..input()},
        Input{counts:[97,0,0],..input()},Input{joint:JointPose{position:[f32::NAN,1.,0.],direction:[0.;3]},..input()}]{
        let before=l.clone();assert!(l.apply(bad_input).is_err());assert_eq!(l,before);
    }
    for n in [0,1,7,255]{assert!(Ledger::new(n).is_err());}
}
#[test]fn p06t_ammo_detonation_max_six_events_have_stable_target_sequence(){
    let mut l=Ledger::new(6).unwrap();for target in 0..6{
        let Outcome::New(e)=l.apply(Input{target,attacker:(target+1)%6,shot:target as u32+1,..input()}).unwrap()else{panic!()};
        assert_eq!(e.sequence(),target as u32+1);
    }assert_eq!(l.events().len(),MAX_EVENTS);
    let before=l.clone();assert!(l.apply(Input{target:6,..input()}).is_err());assert_eq!(l,before);
}
#[test]fn p06t_ammo_detonation_source_kind_caps_and_cause_retained(){
    let mut l=Ledger::new(2).unwrap();let Outcome::New(e)=l.apply(Input{kind:VehicleKind::Is7,
        health_before:2150,residual_hp:2000,device_before:210,counts:[12,7,11],from_fire:true,..input()}).unwrap()else{panic!()};
    assert_eq!(e.kind(),VehicleKind::Is7);assert!(e.from_fire());assert_eq!(e.additional_damage(),2000);
    // This authored flag tests cause preservation, not an actual fire→AmmoBay
    // path: old fire policy currently burns engine/fuel ONLY.
}
#[test]fn p06t_ammo_detonation_flight_independent_after_death_analytic_ballistic_then_terrain(){
    let e=event();assert_eq!(e.final_hp(),0);let mut f=Flight::new(e);
    let s=f.advance(e.born_ms()+1000,|_,_|Ok(0.)).unwrap();assert_eq!(s.phase,FlightPhase::Flying);
    assert!((s.position[0]-2.).abs()<1e-6);assert!((s.position[1]-4.095).abs()<1e-5);assert!((s.position[2]-1.5).abs()<1e-6);
    let landed=f.advance(e.born_ms()+2000,|x,z|{assert_eq!([x,z],[4.,3.]);Ok(0.)}).unwrap();
    assert_eq!(landed.phase,FlightPhase::Resting);assert_eq!(landed.position,[4.,0.,3.]);
    let expired=f.advance(e.born_ms()+5000,|_,_|panic!("resting flight re-queried terrain")).unwrap();
    assert_eq!(expired.phase,FlightPhase::Expired);assert_eq!(expired.position,landed.position);
}
#[test]fn p06t_ammo_detonation_flight_uses_source_joint_world_yaw_and_supplied_ground(){
    let mut l=Ledger::new(2).unwrap();let Outcome::New(e)=l.apply(Input{joint:JointPose{position:[10.,5.,20.],direction:[PI/2.,0.2,-0.1]},..input()}).unwrap()else{panic!()};
    let mut f=Flight::new(e);let s=f.advance(e.born_ms()+1000,|_,_|Ok(4.)).unwrap();
    assert!((s.position[0]-11.5).abs()<1e-5);assert!((s.position[2]-18.).abs()<1e-5);
    let s=f.advance(e.born_ms()+2000,|_,_|Ok(4.)).unwrap();assert_eq!(s.phase,FlightPhase::Resting);assert_eq!(s.position[1],4.);
}
#[test]fn p06t_ammo_detonation_flight_monotonic_or_bad_terrain_errors_are_atomic(){
    let e=event();let mut f=Flight::new(e);let before=f.clone();
    assert!(f.advance(e.born_ms()-1,|_,_|Ok(0.)).is_err());assert_eq!(f,before);
    assert!(f.advance(MAX_TIME_MS+1,|_,_|Ok(0.)).is_err());assert_eq!(f,before);
    assert!(f.advance(e.born_ms()+500,|_,_|Ok(f32::NAN)).is_err());assert_eq!(f,before);
    assert!(f.advance(e.born_ms()+500,|_,_|Err(bad("authored missing terrain"))).is_err());assert_eq!(f,before);
    let s=f.advance(e.born_ms()+500,|_,_|Ok(0.)).unwrap();
    assert_eq!(f.advance(e.born_ms()+500,|_,_|panic!("duplicate timestamp queried terrain")).unwrap(),s);
    let before=f.clone();assert!(f.advance(e.born_ms()+400,|_,_|Ok(0.)).is_err());assert_eq!(f,before);
}
#[test]fn p06t_ammo_detonation_flight_ttl_expires_even_without_ground_contact(){
    let e=event();let mut f=Flight::new(e);let s=f.advance(e.born_ms()+FLIGHT_LIFETIME_MS,|_,_|Ok(-1000.)).unwrap();
    assert_eq!(s.phase,FlightPhase::Expired);assert!(s.position[1]>-1000.);
    let late=f.advance(MAX_TIME_MS,|_,_|panic!("expired flight queried terrain")).unwrap();assert_eq!(late.position,s.position);
}
