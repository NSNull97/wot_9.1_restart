//! SHELL-04 (owner 2026-11-08): classic module rules of the layered law.
use super::*;
use crate::p06t_shells091::{self as source,Mount};

fn he()->Shell {*source::profile(Mount::Ms1Stock).shots.iter().find(|s|s.family==source::Family::HighExplosive).unwrap()}
fn full(profile:Profile)->Health {Health{hp:profile.max_hp(),max_hp:profile.max_hp(),terminal:false}}
fn track_hit(shot:u32)->ModuleHit {
    ModuleHit{cause:Cause{shot,attacker_slot:1},ordinal:TRACK_ORDINALS[0],at_ms:100,target:Target::Device(Device::LeftTrack),shell:he(),ignition_roll:0.}
}
fn after(events:&[Transition])->(u16,Condition) {
    match events.iter().find_map(|e|match e.change{Change::Device{after,after_condition,..}=>Some((after,after_condition)),_=>None}) {
        Some(v)=>v, None=>panic!("no device transition")}
}

#[test] fn classic_damaged_threshold_is_max_regen_health_inclusive() {
    // MS-1 left track: maxHealth 40, maxRegenHealth 30 (#717 source caps).
    let caps=(*Profile::Ms1.caps())[Device::LeftTrack as usize];
    assert_eq!((caps.max,caps.regen),(40,30));
    for (amount,classic,legacy) in [(9u16,Condition::Normal,Condition::Normal),(10,Condition::Critical,Condition::Normal),
        (20,Condition::Critical,Condition::Critical),(40,Condition::Destroyed,Condition::Destroyed)] {
        let mut s=State::new(Profile::Ms1).unwrap();s.enable_classic().unwrap();
        let events=s.apply_explosion_hits(&[track_hit(1)],&[amount],full(Profile::Ms1)).unwrap();
        assert_eq!(after(&events),(40-amount,classic),"{amount}");
        assert_eq!(condition(40-amount,40),legacy,"LAB max/2 is unchanged");
    }
    // A repaired module (HP = maxRegenHealth) is critical in both, as #717 DEVICE_REPAIRED_TO_CRITICAL shows.
    assert_eq!(classic_condition(30,30),Condition::Critical);
}

#[test] fn classic_rules_are_set_before_any_hit_and_explosion_hits_are_bounded() {
    let mut s=State::new(Profile::Ms1).unwrap();
    assert!(s.apply_explosion_hits(&[track_hit(1)],&[5],full(Profile::Ms1)).is_err(),"LAB state refuses explosion hits");
    s.apply_hits(&[track_hit(1)],full(Profile::Ms1)).unwrap();
    assert!(s.enable_classic().is_err(),"no switch after hits");
    let mut s=State::new(Profile::Ms1).unwrap();s.enable_classic().unwrap();
    let h=full(Profile::Ms1);
    assert!(s.apply_explosion_hits(&[track_hit(1)],&[0],h).is_err(),"zero damage");
    let dd=u32::from(he().device_damage);
    assert!(s.clone().apply_explosion_hits(&[track_hit(1)],&[((dd*5+2)/4) as u16],h).is_ok(),"up to the +25 % roll");
    assert!(s.apply_explosion_hits(&[track_hit(1)],&[((dd*5+2)/4+1) as u16],h).is_err(),"above the +25 % roll");
    let seat=ModuleHit{target:Target::Seat(0),ordinal:CLASSIC_FIRST_ORDINAL,..track_hit(1)};
    assert!(s.apply_explosion_hits(&[seat],&[1],h).is_err(),"no crew from an explosion");
    assert!(!s.hit_by_shot(1,Target::Device(Device::LeftTrack)));
    s.apply_explosion_hits(&[track_hit(1)],&[3],h).unwrap();
    assert!(s.hit_by_shot(1,Target::Device(Device::LeftTrack))&&!s.hit_by_shot(2,Target::Device(Device::LeftTrack)));
}

#[test] fn classic_state_takes_every_box_of_the_internal_trace_in_one_batch() {
    let mut s=State::new(Profile::Is7).unwrap();s.enable_classic().unwrap();
    let shell=source::profile(Mount::Is7Stock).shots[0];
    let targets=[Target::Device(Device::Engine),Target::Device(Device::FuelTank),Target::Device(Device::Radio),Target::Seat(2),Target::Seat(4)];
    let hits:Vec<ModuleHit>=targets.iter().enumerate().map(|(i,t)|ModuleHit{cause:Cause{shot:3,attacker_slot:0},
        ordinal:CLASSIC_FIRST_ORDINAL+i as u8,at_ms:100,target:*t,shell,ignition_roll:0.99}).collect();
    let events=s.apply_hits(&hits,full(Profile::Is7)).unwrap();
    assert_eq!(events.iter().filter(|e|matches!(e.change,Change::Device{..})).count(),3);
    assert_eq!(events.iter().filter(|e|matches!(e.change,Change::Crew{..})).count(),2);
    let mut lab=State::new(Profile::Is7).unwrap();
    assert!(lab.apply_hits(&hits,full(Profile::Is7)).is_err(),"the LAB route keeps two internal hits");
}

#[test] fn classic_internal_hits_take_the_given_rolled_module_damage() {
    let mut s=State::new(Profile::Is7).unwrap();s.enable_classic().unwrap();
    let shell=source::profile(Mount::Is7Stock).shots[0];
    let hit=ModuleHit{cause:Cause{shot:5,attacker_slot:0},ordinal:CLASSIC_FIRST_ORDINAL,at_ms:100,target:Target::Device(Device::Engine),shell,ignition_roll:0.99};
    let amount=(f64::from(shell.device_damage)*0.8).round() as u16;
    let events=s.apply_classic_hits(&[hit],&[amount],full(Profile::Is7)).unwrap();
    assert_eq!(after(&events).0,360-amount,"IS-7 engine 360 HP minus the rolled module damage");
    let mut lab=State::new(Profile::Is7).unwrap();
    assert!(lab.apply_classic_hits(&[hit],&[amount],full(Profile::Is7)).is_err());
}
