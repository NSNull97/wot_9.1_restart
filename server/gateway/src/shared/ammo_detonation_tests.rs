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
    for bad_input in [Input{shot:0,..input()},Input{shot:super::super::model::MAX_BATTLE_SHOTS as u32+1,..input()},Input{target:2,..input()},Input{attacker:2,..input()},
        Input{tick:999,..input()},Input{tick:37001,..input()},Input{device_sequence:0,..input()},
        Input{device_before:0,..input()},Input{device_before:61,..input()},Input{device_after:1,..input()},
        Input{health_before:0,..input()},Input{health_before:91,..input()},Input{residual_hp:91,..input()},
        Input{counts:[97,0,0],..input()},Input{joint:JointPose{position:[f32::NAN,1.,0.],direction:[0.;3]},..input()}]{
        let before=l.clone();assert!(l.apply(bad_input).is_err());assert_eq!(l,before);
    }
    for n in [0,1,31,255]{assert!(Ledger::new(n).is_err());}
    // RES-30: 7..30 rosters are valid; shot/device journals of a 30-actor battle.
    for n in [7,30]{assert!(Ledger::new(n).is_ok());}
    assert!(l.apply(Input{shot:super::super::model::MAX_BATTLE_SHOTS as u32,device_sequence:super::super::model::MAX_DAMAGE_EVENTS as u32,..input()}).is_ok());
}
#[test]fn p06t_ammo_detonation_max_six_events_have_stable_target_sequence(){
    let mut l=Ledger::new(6).unwrap();for target in 0..6{
        let Outcome::New(e)=l.apply(Input{target,attacker:(target+1)%6,shot:target as u32+1,..input()}).unwrap()else{panic!()};
        assert_eq!(e.sequence(),target as u32+1);
    }assert_eq!(l.events().len(),6);
    let before=l.clone();assert!(l.apply(Input{target:6,..input()}).is_err());assert_eq!(l,before);
}
#[test]fn res30_ammo_detonation_thirty_roster_one_event_per_target(){
    let mut l=Ledger::new(30).unwrap();for target in 0..30{
        let Outcome::New(e)=l.apply(Input{target,attacker:(target+1)%30,shot:target as u32+1,..input()}).unwrap()else{panic!()};
        assert_eq!(e.sequence(),target as u32+1);
    }assert_eq!(l.events().len(),MAX_EVENTS);
    let before=l.clone();assert!(l.apply(Input{target:30,..input()}).is_err());assert_eq!(l,before);
    let mut again=l.clone();assert!(matches!(again.apply(Input{target:29,attacker:0,shot:30,..input()}).unwrap(),Outcome::Replay(Some(_))));
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
    let resting=f.advance(e.born_ms()+5000,|_,_|panic!("resting flight re-queried terrain")).unwrap();
    assert_eq!(resting.phase,FlightPhase::Resting);assert_eq!(resting.position,landed.position);
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
#[test]fn p06t_ammo_detonation_flight_settles_at_lifetime_even_without_contact(){
    let e=event();let mut f=Flight::new(e);let s=f.advance(e.born_ms()+FLIGHT_LIFETIME_MS,|_,_|Ok(-1000.)).unwrap();
    assert_eq!(s.phase,FlightPhase::Resting);assert_eq!(s.position[1],-1000.);
    let late=f.advance(MAX_TIME_MS,|_,_|panic!("resting flight queried terrain")).unwrap();assert_eq!(late.position,s.position);
}

fn draws(seed:u64)->[u64;LAUNCH_DRAWS]{let mut state=seed;std::array::from_fn(|_|{state=state.wrapping_add(0x9e3779b97f4a7c15);
    let mut v=state;v=(v^(v>>30)).wrapping_mul(0xbf58476d1ce4e5b9);v=(v^(v>>27)).wrapping_mul(0x94d049bb133111eb);v^(v>>31)})}
#[test]fn turret01_launch_same_draws_same_motion_different_events_differ(){
    let a=Launch::derive(0.3,0.5,draws(7)).unwrap();assert_eq!(a,Launch::derive(0.3,0.5,draws(7)).unwrap());
    // Another heading, rack fill or battle seed is another launch.
    for other in [Launch::derive(1.3,0.5,draws(7)).unwrap(),Launch::derive(0.3,1.,draws(7)).unwrap(),Launch::derive(0.3,0.5,draws(8)).unwrap()]{
        assert_ne!(a.linear_velocity,other.linear_velocity);
    }
    for seed in 0..500{let l=Launch::derive(seed as f32*0.1,(seed%11)as f32/10.,draws(seed)).unwrap();
        assert!((5. ..=10.).contains(&l.linear_velocity[1]));let side=l.linear_velocity[0].hypot(l.linear_velocity[2]);assert!((1. ..=4.0001).contains(&side));
        assert!(l.angular_velocity[0].abs()<=3.&&l.angular_velocity[1].abs()<=2.&&l.angular_velocity[2].abs()<=3.);}
    // Sideways motion keeps within 60 degrees of the shot heading.
    let l=Launch::derive(0.,0.,[0,u64::MAX,u64::MAX,0,0,0]).unwrap();assert!(l.linear_velocity[0]>0.&&l.linear_velocity[2]>0.);
    assert!(Launch::derive(f32::NAN,0.5,draws(1)).is_err());assert!(Launch::derive(0.,1.5,draws(1)).is_err());
}
#[test]fn turret01_jolt_flight_holds_joint_then_plays_worker_trajectory_by_clock(){
    let e=event();let launch=Launch::derive(0.,0.5,draws(3)).unwrap();let mut f=Flight::jolt(e,launch).unwrap();
    assert!(f.awaiting_trajectory());assert_eq!(f.launch(),Some(launch));
    let s=f.advance(e.born_ms()+250,|_,_|panic!("Jolt flight never samples terrain")).unwrap();
    assert_eq!((s.position,s.phase),(e.joint().position,FlightPhase::Flying));
    let pose=|y:f32|JointPose{position:[0.,y,0.],direction:[0.,0.,y/10.]};
    let bad_start=Trajectory{samples:vec![pose(5.)],slept:true};assert!(f.clone().install_trajectory(bad_start).is_err());
    assert!(f.clone().install_trajectory(Trajectory{samples:vec![],slept:true}).is_err());
    assert!(f.clone().install_trajectory(Trajectory{samples:vec![pose(1.);MAX_TRAJECTORY_SAMPLES+1],slept:true}).is_err());
    f.install_trajectory(Trajectory{samples:vec![pose(1.),pose(3.),pose(2.),pose(0.5)],slept:true}).unwrap();
    assert!(!f.awaiting_trajectory());assert!(f.clone().install_trajectory(Trajectory{samples:vec![pose(1.)],slept:true}).is_err());
    let s=f.advance(e.born_ms()+299,|_,_|panic!()).unwrap();assert_eq!((s.position[1],s.phase),(2.,FlightPhase::Flying));
    let s=f.advance(e.born_ms()+300,|_,_|panic!()).unwrap();assert_eq!((s.position[1],s.direction[2],s.phase),(0.5,0.05,FlightPhase::Resting));
    let s=f.advance(MAX_TIME_MS,|_,_|panic!()).unwrap();assert_eq!((s.position[1],s.phase),(0.5,FlightPhase::Resting));
    // A legacy point flight has no Jolt body to install.
    assert!(Flight::new(e).install_trajectory(Trajectory{samples:vec![pose(1.)],slept:true}).is_err());
}
