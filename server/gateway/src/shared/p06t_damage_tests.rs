use crate::{p06t_damage as math,p06t_device_state as devices,p06t_lab_proxy as proxy,p06t_device_caps::{self as source_caps,Device,Profile}};
use crate::p06t_shells091::{self as source,Mount,Shell};
fn shell(mount:Mount,index:usize)->Shell {source::profile(mount).shots[index]}
fn direct(shell:Shell,armor:f64,angle:f32,distance:f64)->math::Resolution {
    math::resolve_direct(math::DirectInput {shell,plate:math::Plate {armor_mm:Some(armor),ordinary:true},
        chord:[angle.to_radians().sin(),0.,angle.to_radians().cos()],winding_normal:[0.,0.,1.],distance_m:distance}).unwrap()
}
#[test] fn ap_matches_independent_accepted_plate_boundaries_in_new_mode() {
    let ap=shell(Mount::Ms1Stock,0);
    assert_eq!(direct(ap,18.,0.,100.).damage_hp,30);
    assert_eq!(direct(ap,34.,0.,100.).decision,math::Decision::NotPierced);
    assert_eq!(direct(ap,27.,0.,500.).decision,math::Decision::NotPierced);
    assert_eq!(direct(ap,26.,0.,500.).damage_hp,30);
    assert_eq!(direct(ap,1.,0.,720.).decision,math::Decision::OutOfRange);
    let big=shell(Mount::Is7Stock,0);
    assert_eq!(direct(big,50.,0.,0.).normalization_degrees,18.2);
    assert_eq!(direct(big,130./3.,80.,0.).decision,math::Decision::Pierced);
    assert_eq!(direct(big,130./3.+1e-6,80.,0.).decision,math::Decision::Ricochet);
    assert_eq!(direct(big,100.,70.1,0.).decision,math::Decision::Ricochet);
    assert_ne!(direct(big,100.,69.9,0.).decision,math::Decision::Ricochet);
}
#[test] fn apcr_has_its_source_power_and_two_degree_normalization() {
    let apcr=shell(Mount::Is7Stock,1);
    assert_eq!(direct(apcr,100.,0.,100.).normalization_degrees,2.);
    assert_eq!(direct(apcr,303.,0.,100.).decision,math::Decision::NotPierced);
    assert_eq!(direct(apcr,263.,0.,500.).decision,math::Decision::NotPierced);
    assert_eq!(direct(apcr,262.,0.,500.).damage_hp,490);
    assert_eq!(direct(apcr,50.,0.,0.).normalization_degrees,7.28);
    assert_eq!(direct(apcr,100.,70.1,0.).decision,math::Decision::Ricochet);
}
#[test] fn heat_has_no_normalization_overmatch_or_invented_distance_loss() {
    let heat=shell(Mount::Ms1Stock,1);
    assert_eq!(heat.piercing_power_loss_factor_by_distance,Some(0.05));
    assert_eq!(direct(heat,1.,86.,0.).decision,math::Decision::Ricochet);
    assert_ne!(direct(heat,1.,84.,0.).decision,math::Decision::Ricochet);
    for distance in [0.,100.,500.,719.] {
        let r=direct(heat,43.,0.,distance);assert_eq!(r.damage_hp,30);assert_eq!(r.nominal_power_mm,44.);assert_eq!(r.normalization_degrees,0.);
    }
    assert_eq!(direct(heat,44.,0.,0.).decision,math::Decision::NotPierced);
}
#[test] fn he_full_penetration_equality_and_lab_attenuation_are_separate() {
    let he=shell(Mount::Is7Stock,2);
    assert_eq!(direct(he,67.,0.,100.).damage_hp,640);
    let equal=direct(he,68.,0.,100.);assert_eq!(equal.decision,math::Decision::NotPierced);assert_eq!(equal.damage_hp,245);
    assert_eq!(direct(he,100.,0.,100.).damage_hp,210);
    assert_ne!(direct(he,1.,89.9,100.).decision,math::Decision::Ricochet);
    let hesh=shell(Mount::Fv215b183,1);let normal_he=shell(Mount::Fv215b183,2);
    assert_eq!(direct(hesh,200.,0.,0.).damage_hp,1750);
    assert_eq!(direct(normal_he,200.,0.,0.).damage_hp,655);
    assert_eq!(hesh.penetration_mm,[275.,275.]);
}
#[test] fn splash_uses_frozen_he_radius_surface_armor_and_actual_los_facts() {
    let he=shell(Mount::Is7Stock,2);let radius=he.explosion_radius_m.unwrap();
    let inputs=[math::SplashTarget {slot:0,distance_m:radius/2.,armor_mm:10.,los_clear:true},
        math::SplashTarget {slot:1,distance_m:0.,armor_mm:0.,los_clear:false},
        math::SplashTarget {slot:2,distance_m:radius,armor_mm:0.,los_clear:true}];
    let output=math::resolve_splash(he,&inputs).unwrap();
    assert_eq!(output.iter().map(|r|r.damage_hp).collect::<Vec<_>>(),[149,0,0]);
    assert!(math::resolve_splash(shell(Mount::Ms1Stock,0),&inputs).is_err());
    assert!(math::resolve_splash(he,&[inputs[0],inputs[0]]).is_err());
    assert!(math::resolve_splash(he,&[math::SplashTarget{slot:6,..inputs[0]}]).is_err());
    assert!(math::resolve_splash(he,&[inputs[0];7]).is_err());
}
#[test] fn malformed_or_forged_math_inputs_never_become_plate_damage() {
    let mut ap=shell(Mount::Ms1Stock,0);ap.damage_hp+=1;
    assert!(math::source_shell(ap).is_err());
    let base=math::DirectInput {shell:shell(Mount::Ms1Stock,0),plate:math::Plate{armor_mm:Some(18.),ordinary:true},
        chord:[0.,0.,1.],winding_normal:[0.,0.,1.],distance_m:0.};
    for distance in [f64::NAN,f64::INFINITY,-1.,100001.] {assert!(math::resolve_direct(math::DirectInput{distance_m:distance,..base}).is_err());}
    assert!(math::resolve_direct(math::DirectInput{chord:[0.;3],..base}).is_err());
    assert!(math::resolve_direct(math::DirectInput{plate:math::Plate{armor_mm:Some(f64::NAN),ordinary:true},..base}).is_err());
    assert!(math::resolve_direct(math::DirectInput{plate:math::Plate{armor_mm:Some(f64::from_bits(1)),ordinary:true},..base}).is_err());
    for plate in [math::Plate{armor_mm:None,ordinary:true},math::Plate{armor_mm:Some(0.),ordinary:true},math::Plate{armor_mm:Some(18.),ordinary:false}] {
        let r=math::resolve_direct(math::DirectInput{plate,..base}).unwrap();assert_eq!(r.decision,math::Decision::Unsupported);assert_eq!(r.damage_hp,0);
    }
}
#[test] fn source_five_profiles_keep_exact_device_caps_and_primary_seat_order() {
    let expected=[[25,60,100,90,40,40,54,50,30],[360,210,200,250,250,250,210,170,120],
        [40,75,100,100,50,50,54,60,40],[105,130,150,110,90,90,106,100,70],
        [145,140,150,110,110,110,130,120,80]];
    let crew:&[&[u8]]=&[&[35,36],&[35,39,36,41,42],&[35,36,39],&[35,37,36,41],&[35,39,37,36,41]];
    for profile in Profile::ALL {
        let s=devices::State::new(profile).unwrap();assert_eq!(s.health(),expected[profile.index()]);
        assert_eq!(source_caps::CREW[profile.index()].iter().map(|s|s.extra).collect::<Vec<_>>(),crew[profile.index()]);
        for (i,c) in source_caps::CAPS[profile.index()].iter().enumerate() {assert!(c.regen>0&&c.regen<=c.max);assert_eq!(Device::ALL[i].extra(),26+i as u8);}
        assert_eq!(s.crew(),vec![true;crew[profile.index()].len()]);
    }
    assert_eq!(source_caps::SOURCE_SHA256.len(),64);
}
fn context(profile:Profile)->devices::Health {devices::Health{hp:source_caps::MAX_HP[profile.index()],max_hp:source_caps::MAX_HP[profile.index()],terminal:false}}
fn hit(shot:u32,target:proxy::Target,at:u64,roll:f64)->devices::ModuleHit {
    devices::ModuleHit {cause:devices::Cause {shot,attacker_slot:1},ordinal:0,at_ms:at,target,shell:shell(Mount::Ms1Stock,0),ignition_roll:roll}
}
#[test] fn module_replays_are_idempotent_conflicts_and_bad_compounds_roll_back() {
    let mut s=devices::State::new(Profile::Ms1).unwrap();let h=context(Profile::Ms1);let first=hit(1,proxy::Target::Device(Device::Engine),0,0.1);
    assert_eq!(s.apply_hits(&[first],h).unwrap().len(),2);let committed=s.clone();
    assert!(s.apply_hits(&[first],h).unwrap().is_empty());assert_eq!(s,committed);
    assert!(s.apply_hits(&[devices::ModuleHit{ignition_roll:0.11,..first}],h).is_err());assert_eq!(s,committed);
    let next=hit(2,proxy::Target::Device(Device::Gun),0,0.9);
    let bad=devices::ModuleHit{ordinal:1,ignition_roll:f64::NAN,target:proxy::Target::Seat(0),..next};
    assert!(s.apply_hits(&[next,bad],h).is_err());assert_eq!(s,committed);
    assert!(s.apply_hits(&[hit(961,proxy::Target::Device(Device::Engine),0,0.9)],h).is_err());
    assert!(s.apply_hits(&[hit(2,proxy::Target::Seat(2),0,0.9)],h).is_err());
}
#[test] fn critical_and_destroyed_devices_change_actual_capability_outputs() {
    let mut s=devices::State::new(Profile::T34).unwrap();let h=context(Profile::T34);
    s.apply_hits(&[hit(1,proxy::Target::Device(Device::Engine),0,0.9)],h).unwrap();assert_eq!(s.capabilities().drive_scale,1.);
    s.apply_hits(&[hit(2,proxy::Target::Device(Device::Engine),0,0.9)],h).unwrap();assert_eq!(s.capabilities().drive_scale,0.5);
    s.apply_hits(&[hit(3,proxy::Target::Device(Device::Engine),0,0.9)],h).unwrap();assert_eq!(s.capabilities().drive_scale,0.);assert_eq!(s.capabilities().steer_scale,0.);
    let mut s=devices::State::new(Profile::Ms1).unwrap();let h=context(Profile::Ms1);
    s.apply_hits(&[hit(1,proxy::Target::Device(Device::LeftTrack),0,0.9)],h).unwrap();assert_eq!(s.capabilities().steer_scale,0.);
    s.apply_hits(&[hit(2,proxy::Target::Device(Device::TurretRotator),0,0.9)],h).unwrap();assert_eq!(s.capabilities().turret_scale,0.);
    s.apply_hits(&[hit(3,proxy::Target::Device(Device::Gun),0,0.9)],h).unwrap();assert_eq!(s.capabilities().dispersion_scale,2.);assert!(s.capabilities().can_fire);
    s.apply_hits(&[hit(4,proxy::Target::Device(Device::Gun),0,0.9)],h).unwrap();assert!(!s.capabilities().can_fire);
}
#[test] fn combined_role_wound_and_both_is7_loaders_use_real_seats_not_role_dedup() {
    let mut s=devices::State::new(Profile::Ms1).unwrap();let h=context(Profile::Ms1);
    let changes=s.apply_hits(&[hit(1,proxy::Target::Seat(0),0,0.9)],h).unwrap();
    assert!(matches!(changes[0].change,devices::Change::Crew{seat:0,extra_index:35,..}));
    let c=s.capabilities();assert!(c.crew_active);assert_eq!(c.reload_scale,2.);assert_eq!(c.aim_speed_scale,0.5);assert_eq!(c.radio_scale,0.5);
    s.apply_hits(&[hit(2,proxy::Target::Seat(1),0,0.9)],h).unwrap();assert!(!s.capabilities().crew_active);assert!(!s.capabilities().can_fire);
    assert_eq!(h.hp,90,"crew inactivity does not fabricate HP0");
    let mut s=devices::State::new(Profile::Is7).unwrap();let h=context(Profile::Is7);
    s.apply_hits(&[hit(1,proxy::Target::Seat(3),0,0.9)],h).unwrap();assert_eq!(s.capabilities().radio_scale,1.);
    let events=s.apply_hits(&[hit(2,proxy::Target::Seat(4),0,0.9)],h).unwrap();assert_eq!(s.capabilities().radio_scale,0.5);
    assert!(matches!(events[0].change,devices::Change::Crew{seat:4,extra_index:42,..}));
}
#[test] fn engine_ignition_boundary_and_first_cause_are_explicit_and_do_not_extend_fire() {
    let h=context(Profile::Ms1);let mut no=devices::State::new(Profile::Ms1).unwrap();
    no.apply_hits(&[hit(1,proxy::Target::Device(Device::Engine),0,0.2)],h).unwrap();assert!(!no.fire_active());
    let mut yes=devices::State::new(Profile::Ms1).unwrap();
    yes.apply_hits(&[hit(1,proxy::Target::Device(Device::Engine),0,0.199999)],h).unwrap();
    let second=devices::ModuleHit {cause:devices::Cause{shot:2,attacker_slot:2},..hit(2,proxy::Target::Device(Device::Engine),500,0.)};
    assert!(yes.apply_hits(&[second],h).unwrap().is_empty());
    let events=yes.advance_fire(1000,h).unwrap();assert!(events.iter().all(|e|e.cause.shot==1&&e.cause.attacker_slot==1&&e.at_ms==1000));
    assert!(events.iter().any(|e|e.change==devices::Change::VehicleDamage{amount:5}));
    yes.advance_fire(10_000,h).unwrap();assert!(!yes.fire_active());
}
#[test] fn fire_catchup_is_bounded_monotonic_attributed_and_terminal_freezes() {
    let mut s=devices::State::new(Profile::Is7).unwrap();let h=context(Profile::Is7);
    let initial=devices::ModuleHit {shell:shell(Mount::Is7Stock,0),..hit(1,proxy::Target::Device(Device::Engine),0,0.)};
    s.apply_hits(&[initial],h).unwrap();let events=s.advance_fire(100_000,h).unwrap();
    let hp:Vec<_>=events.iter().filter_map(|e|if let devices::Change::VehicleDamage{amount}=e.change{Some(amount)}else{None}).collect();
    assert_eq!(hp,[108;10]);assert!(!s.fire_active());assert_eq!(s.health()[0],0);assert_eq!(s.health()[2],100);
    assert_eq!(s.fire_ticks(),10);assert_eq!(s.proposed_fire_damage(),1080);
    assert!(events.iter().all(|e|e.cause==initial.cause&&e.from_fire));
    assert!(events.windows(2).all(|w|w[0].sequence<w[1].sequence&&w[0].at_ms<=w[1].at_ms));
    let committed=s.clone();assert!(s.advance_fire(100_000,h).unwrap().is_empty());assert_eq!(s,committed);
    assert!(s.advance_fire(99_999,h).is_err());assert_eq!(s,committed);
    let mut alive=devices::State::new(Profile::Ms1).unwrap();let h=context(Profile::Ms1);
    alive.apply_hits(&[hit(1,proxy::Target::Device(Device::Engine),0,0.)],h).unwrap();let before=alive.health();let seq=alive.sequence();
    assert!(alive.advance_fire(10_000,devices::Health{terminal:true,..h}).unwrap().is_empty());
    assert_eq!(alive.health(),before);assert_eq!(alive.sequence(),seq);assert!(alive.frozen());
}
#[test] fn fire_death_proposal_clamps_to_real_context_hp_without_extra_ticks() {
    let mut s=devices::State::new(Profile::Ms1).unwrap();let h=devices::Health{hp:7,..context(Profile::Ms1)};
    s.apply_hits(&[hit(1,proxy::Target::Device(Device::Engine),0,0.)],h).unwrap();
    let events=s.advance_fire(10_000,h).unwrap();
    let hp:Vec<_>=events.iter().filter_map(|e|if let devices::Change::VehicleDamage{amount}=e.change{Some(amount)}else{None}).collect();
    assert_eq!(hp,[5,2]);assert!(s.frozen());assert!(!s.fire_active());
    assert_eq!(s.fire_ticks(),2);assert_eq!(s.proposed_fire_damage(),7);
    let seq=s.sequence();assert!(s.advance_fire(20_000,devices::Health{hp:0,..h}).unwrap().is_empty());assert_eq!(s.sequence(),seq);
}
#[test] fn pending_fire_ticks_must_commit_before_newer_hits_and_final_outcome_is_immutable() {
    let mut s=devices::State::new(Profile::Ms1).unwrap();let h=context(Profile::Ms1);
    s.apply_hits(&[hit(1,proxy::Target::Device(Device::Engine),0,0.)],h).unwrap();
    let before=s.clone();let next=hit(2,proxy::Target::Device(Device::Gun),1500,0.9);
    assert!(s.apply_hits(&[next],h).is_err());assert_eq!(s,before);
    let fire=s.advance_fire(1500,h).unwrap();assert_eq!(fire[0].at_ms,1000);
    let events=s.apply_hits(&[next],devices::Health{hp:85,..h}).unwrap();assert_eq!(events[0].at_ms,1500);
    assert!(fire.last().unwrap().sequence<events[0].sequence);
    s.freeze();let frozen=s.clone();
    assert!(s.advance_fire(2000,devices::Health{hp:85,terminal:true,..h}).unwrap().is_empty());
    assert_eq!(s.health(),frozen.health());assert_eq!(s.sequence(),frozen.sequence());assert_eq!(s.fire_ticks(),frozen.fire_ticks());
}
#[test] fn proxy_uses_actual_component_chord_and_stable_nearest_two_policy() {
    let b=[[0.;3],[1.;3]];
    let hits=proxy::select(Profile::Ms1,proxy::Component::Hull,b,[0.5,0.5,0.],[0.5,0.5,1.]).unwrap();
    assert_eq!(hits.iter().map(|h|h.target).collect::<Vec<_>>(),[proxy::Target::Device(Device::Engine),proxy::Target::Device(Device::AmmoBay)]);
    assert!((hits[0].entry_fraction-0.05).abs()<1e-12);
    let reverse=proxy::select(Profile::Ms1,proxy::Component::Hull,b,[0.5,0.5,1.],[0.5,0.5,0.]).unwrap();
    assert_eq!(reverse[0].target,proxy::Target::Device(Device::AmmoBay));
    let crew=proxy::select(Profile::T34,proxy::Component::Turret,b,[0.,0.5,0.5],[1.,0.5,0.5]).unwrap();
    assert_eq!(crew.iter().map(|h|h.target).collect::<Vec<_>>(),[proxy::Target::Seat(0),proxy::Target::Seat(3)]);
    let gun=proxy::select(Profile::T26,proxy::Component::Gun,b,[0.,0.5,0.5],[1.,0.5,0.5]).unwrap();assert_eq!(gun[0].target,proxy::Target::Device(Device::Gun));
    let after_engine=proxy::select(Profile::Ms1,proxy::Component::Hull,b,[0.5,0.5,0.37],[0.5,0.5,1.]).unwrap();
    assert!(after_engine.iter().all(|h|h.target!=proxy::Target::Device(Device::Engine)),"a box behind actual exterior contact must never be hit");
    assert!(proxy::select(Profile::Ms1,proxy::Component::Hull,b,[0.;3],[0.;3]).is_err());
    assert!(proxy::select(Profile::Ms1,proxy::Component::Hull,b,[-1.,2.,0.],[2.,2.,0.]).is_err());
    assert!(proxy::select(Profile::Ms1,proxy::Component::Hull,[[0.;3],[0.;3]],[-1.;3],[2.;3]).is_err());
}
