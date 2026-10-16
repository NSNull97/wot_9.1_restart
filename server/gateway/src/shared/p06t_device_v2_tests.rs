//! Component/source gates only. No authored proxy hit is a World mesh proof.
use super::*;
use crate::{p06t_device_caps as caps,p06t_lab_proxy as proxy,p06t_shells091::{self as source,Mount}};
use serde_json::Value;
use sha2::{Digest,Sha256};

fn shell(mount:Mount,index:usize)->Shell {source::profile(mount).shots[index]}
fn context(profile:Profile)->Health {Health{hp:MAX_HP[profile.index()],max_hp:MAX_HP[profile.index()],terminal:false}}
fn hit(shot:u32,target:Target,at_ms:u64,ignition_roll:f64)->ModuleHit {
    ModuleHit{cause:Cause{shot,attacker_slot:1},ordinal:0,at_ms,target,shell:shell(Mount::Ms1Stock,0),ignition_roll}
}
fn hash(raw:&[u8])->String {format!("{:x}",Sha256::digest(raw))}
fn value(raw:&[u8])->Value {serde_json::from_slice(raw).unwrap()}
fn role_mask(role:&str)->u8 {match role{"commander"=>1,"gunner"=>2,"driver"=>4,"loader"=>8,"radioman"=>16,_=>panic!("unknown source role")}}

#[test] fn p06t_device_v2_raw_pins_and_old_five_source_policy_rows_are_preserved() {
    let old_caps=include_bytes!("p06t_device_source_caps.json");let caps_v2=include_bytes!("p06t_device_source_caps_v2.json");
    let old_policy=include_bytes!("p06t_device_policy.json");let policy_v2=include_bytes!("p06t_device_policy_v2.json");
    assert_eq!(hash(old_caps),SOURCE_SHA256);assert_eq!(hash(caps_v2),SOURCE_V2_SHA256);
    assert_eq!(hash(old_policy),POLICY_SHA256);assert_eq!(hash(policy_v2),POLICY_V2_SHA256);
    let a=value(old_caps);let b=value(caps_v2);let p=value(old_policy);let q=value(policy_v2);
    assert_eq!(a["schema"],"p06t-device-source-caps.v1");assert_eq!(b["schema"],"p06t-device-source-caps.v2");
    assert_eq!(a["profiles"].as_array().unwrap().as_slice(),&b["profiles"].as_array().unwrap()[..5]);
    assert_eq!(p["profiles"].as_array().unwrap().as_slice(),&q["profiles"].as_array().unwrap()[..5]);
    assert_eq!(p["policy_revision"],POLICY);assert_eq!(q["policy_revision"],POLICY_V2);
    assert_eq!(p["source_caps_sha256"],SOURCE_SHA256);assert_eq!(q["source_caps_sha256"],SOURCE_V2_SHA256);
    assert_eq!(q["laboratory_rules"],p["laboratory_rules"]);assert_eq!(q["proxy_policy_revision"],proxy::POLICY);
    assert_eq!(q["max_primary_seats"],6);assert_eq!(b["new_policy"],"NOT_CREATED");
}

#[test] fn p06t_device_v2_supported_seven_match_all_source_caps_roles_and_extras() {
    assert_eq!(Profile::ALL,[Profile::Ms1,Profile::Is7,Profile::T26,Profile::T34,Profile::T3485]);
    assert_eq!(Profile::SUPPORTED.len(),7);let json=value(include_bytes!("p06t_device_source_caps_v2.json"));
    let mut seats=0;let mut devices=0;
    for profile in Profile::SUPPORTED {
        let index=profile.index();let row=&json["profiles"][index];let state=State::new_v2(profile).unwrap();
        assert_eq!(row["vehicle_max_health"].as_u64().unwrap(),u64::from(MAX_HP[index]));
        assert_eq!(row["engine_fire_starting_chance"].as_f64().unwrap(),ENGINE_FIRE_CHANCE[index]);
        assert_eq!(row["devices"].as_array().unwrap().len(),9);
        for (i,device)in row["devices"].as_array().unwrap().iter().enumerate() {
            assert_eq!(device["max_health"].as_u64().unwrap(),u64::from(CAPS[index][i].max));
            assert_eq!(device["max_regen_health"].as_u64().unwrap(),u64::from(CAPS[index][i].regen));
            assert_eq!(device["extra_index"].as_u64().unwrap(),u64::from(Device::ALL[i].extra()));devices+=1;
        }
        let crew=row["crew"].as_array().unwrap();assert_eq!(crew.len(),CREW[index].len());assert_eq!(state.crew(),vec![true;crew.len()]);
        for (i,seat)in crew.iter().enumerate() {
            let roles=seat["roles"].as_array().unwrap();let mask=roles.iter().fold(0,|mask,role|mask|role_mask(role.as_str().unwrap()));
            assert_eq!(CREW[index][i].roles,mask);assert_eq!(CREW[index][i].extra,u8::try_from(seat["extra_index"].as_u64().unwrap()).unwrap());
            assert_eq!(CREW[index][i].primary_driver,roles[0]=="driver");assert_eq!(CREW[index][i].primary_radioman,roles[0]=="radioman");seats+=1;
        }
    }
    assert_eq!((devices,seats),(63,30));
}

#[test] fn p06t_device_v2_explicit_constructor_keeps_v1_closed_without_panicking() {
    for profile in Profile::ALL {
        let v1=State::new(profile).unwrap();let v2=State::new_v2(profile).unwrap();
        assert_eq!(v1.policy_version(),PolicyVersion::V1);assert_eq!(v1.policy_revision(),POLICY);
        assert_eq!(v1.source_caps_sha(),SOURCE_SHA256);assert_eq!(v1.policy_manifest_sha(),POLICY_SHA256);
        assert_eq!(profile.source_sha(),SOURCE_SHA256);
        assert_eq!(v1.health(),v2.health());assert_eq!(v1.crew(),v2.crew());assert_eq!(v1.capabilities(),v2.capabilities());
    }
    for profile in [Profile::Wt128,Profile::Fv183] {
        assert!(State::new(profile).is_err());let state=State::new_v2(profile).unwrap();
        assert_eq!(state.profile(),profile);assert_eq!(profile.source_sha(),SOURCE_V2_SHA256);
    }
    for profile in Profile::SUPPORTED {
        let state=State::new_v2(profile).unwrap();assert_eq!(state.policy_version(),PolicyVersion::V2);
        assert_eq!(state.policy_revision(),POLICY_V2);assert_eq!(state.source_caps_sha(),SOURCE_V2_SHA256);
        assert_eq!(state.policy_manifest_sha(),POLICY_V2_SHA256);
    }
    assert_eq!(Profile::Wt128.label(),"wt-e100-128");assert_eq!(Profile::Fv183.label(),"fv215b-183");
}

#[test] fn p06t_device_v2_old_five_transition_and_capability_outputs_remain_equal() {
    for profile in Profile::ALL {
        let mut v1=State::new(profile).unwrap();let mut v2=State::new_v2(profile).unwrap();let h=context(profile);
        for transaction in [hit(1,Target::Device(Device::Engine),0,0.99),hit(2,Target::Seat(0),0,0.99)] {
            assert_eq!(v1.apply_hits(&[transaction],h).unwrap(),v2.apply_hits(&[transaction],h).unwrap());
            assert_eq!(v1.health(),v2.health());assert_eq!(v1.crew(),v2.crew());assert_eq!(v1.capabilities(),v2.capabilities());
            assert_eq!(v1.sequence(),v2.sequence());
        }
        assert_eq!(v1.policy_revision(),POLICY);assert_eq!(v1.crew().len(),CREW[profile.index()].len());
    }
}

#[test] fn p06t_device_v2_primary_radio_and_fv_combined_commander_keep_real_seats() {
    let mut wt=State::new_v2(Profile::Wt128).unwrap();let h=context(Profile::Wt128);assert_eq!(wt.crew().len(),6);
    let events=wt.apply_hits(&[hit(1,Target::Seat(3),0,0.99)],h).unwrap();
    assert!(matches!(events[0].change,Change::Crew{seat:3,extra_index:37,..}));assert_eq!(wt.capabilities().radio_scale,0.5);
    assert_eq!(wt.capabilities().view_scale,1.);assert_eq!(wt.capabilities().reload_scale,1.);
    wt.apply_hits(&[hit(2,Target::Seat(2),0,0.99)],h).unwrap();assert_eq!(wt.capabilities().drive_scale,0.5);assert_eq!(wt.capabilities().steer_scale,0.5);
    let mut fv=State::new_v2(Profile::Fv183).unwrap();let h=context(Profile::Fv183);assert_eq!(fv.crew().len(),5);
    fv.apply_hits(&[hit(1,Target::Seat(0),0,0.99)],h).unwrap();let c=fv.capabilities();
    assert_eq!(c.radio_scale,0.5);assert_eq!(c.view_scale,0.75);assert_eq!(c.reload_scale,1.);assert!(c.crew_active);
}

#[test] fn p06t_device_v2_two_wt_loaders_are_independent_and_replay_is_atomic() {
    let mut state=State::new_v2(Profile::Wt128).unwrap();let h=context(Profile::Wt128);let first=hit(1,Target::Seat(4),0,0.99);
    let events=state.apply_hits(&[first],h).unwrap();assert!(matches!(events[0].change,Change::Crew{seat:4,extra_index:41,..}));
    let committed=state.clone();assert!(state.apply_hits(&[first],h).unwrap().is_empty());assert_eq!(state,committed);
    let events=state.apply_hits(&[hit(2,Target::Seat(5),0,0.99)],h).unwrap();assert!(matches!(events[0].change,Change::Crew{seat:5,extra_index:42,..}));
    assert_eq!(state.crew(),[true,true,true,true,false,false]);assert_eq!(state.capabilities().reload_scale,2.);assert_eq!(state.capabilities().radio_scale,1.);
    let before=state.clone();let good=hit(3,Target::Seat(0),0,0.99);let bad=ModuleHit{ordinal:1,target:Target::Seat(6),..good};
    assert!(state.apply_hits(&[good,bad],h).is_err());assert_eq!(state,before);
    assert!(state.apply_hits(&[ModuleHit{ignition_roll:0.1,..first}],h).is_err());assert_eq!(state,before);
    let mut fv=State::new_v2(Profile::Fv183).unwrap();let before=fv.clone();
    assert!(fv.apply_hits(&[hit(1,Target::Seat(5),0,0.99)],context(Profile::Fv183)).is_err());assert_eq!(fv,before);
}

#[test] fn p06t_device_v2_six_dead_crew_stop_without_fabricating_vehicle_hp_zero() {
    let mut state=State::new_v2(Profile::Wt128).unwrap();let h=context(Profile::Wt128);
    for seat in 0..6 {state.apply_hits(&[hit(u32::from(seat)+1,Target::Seat(seat),0,0.99)],h).unwrap();}
    assert_eq!(state.crew(),[false;6]);assert!(!state.crew_active());let c=state.capabilities();
    assert!(!c.can_fire);assert_eq!(c.drive_scale,0.);assert_eq!(c.steer_scale,0.);assert_eq!(h.hp,2000);
    let sequence=state.sequence();assert!(state.advance_fire(1000,h).unwrap().is_empty());assert!(state.frozen());assert_eq!(state.sequence(),sequence);
}

#[test] fn p06t_device_v2_source_half_critical_differs_from_max_regen() {
    let profile=Profile::Wt128;let mut state=State::new_v2(profile).unwrap();let h=context(profile);
    assert_eq!(CAPS[profile.index()][Device::Engine as usize],caps::Cap{max:360,regen:170});
    let shell=shell(Mount::WtE100128,0);assert_eq!(shell.device_damage,180);
    let input=ModuleHit{shell,..hit(1,Target::Device(Device::Engine),0,0.99)};
    let events=state.apply_hits(&[input],h).unwrap();assert_eq!(state.health()[0],180);assert_eq!(state.capabilities().drive_scale,0.5);
    assert!(matches!(events[0].change,Change::Device{after_condition:Condition::Critical,..}));
    state.apply_hits(&[ModuleHit{cause:Cause{shot:2,attacker_slot:1},..input}],h).unwrap();
    assert_eq!(state.health()[0],0);assert_eq!(state.capabilities().drive_scale,0.);assert_eq!(state.capabilities().steer_scale,0.);
}

#[test] fn p06t_device_v2_source_ignition_boundaries_and_first_cause_bounded_fire() {
    for profile in [Profile::Wt128,Profile::Fv183] {
        let h=context(profile);let chance=ENGINE_FIRE_CHANCE[profile.index()];let mut no=State::new_v2(profile).unwrap();
        no.apply_hits(&[hit(1,Target::Device(Device::Engine),0,chance)],h).unwrap();assert!(!no.fire_active());
        let mut yes=State::new_v2(profile).unwrap();let initial=hit(1,Target::Device(Device::Engine),0,chance-0.000001);
        yes.apply_hits(&[initial],h).unwrap();assert!(yes.fire_active());
        yes.apply_hits(&[hit(2,Target::Device(Device::Engine),500,0.)],h).unwrap();
        let events=yes.advance_fire(100_000,h).unwrap();let damages:Vec<_>=events.iter().filter_map(|event|match event.change{Change::VehicleDamage{amount}=>Some(amount),_=>None}).collect();
        assert_eq!(damages,[100;10]);assert!(events.iter().all(|event|event.cause==initial.cause&&event.from_fire));
        assert_eq!(yes.fire_ticks(),10);assert_eq!(yes.proposed_fire_damage(),1000);assert!(!yes.fire_active());
        let before=yes.clone();assert!(yes.advance_fire(100_000,h).unwrap().is_empty());assert_eq!(yes,before);
    }
}

#[test] fn p06t_device_v2_hp_clamp_and_terminal_freeze_propose_no_extra_damage() {
    for profile in [Profile::Wt128,Profile::Fv183] {
        let mut state=State::new_v2(profile).unwrap();let h=Health{hp:7,..context(profile)};
        state.apply_hits(&[hit(1,Target::Device(Device::Engine),0,0.)],h).unwrap();
        let changes=state.advance_fire(100_000,h).unwrap();let damages:Vec<_>=changes.iter().filter_map(|event|match event.change{Change::VehicleDamage{amount}=>Some(amount),_=>None}).collect();
        assert_eq!(damages,[7]);assert_eq!(state.fire_ticks(),1);assert_eq!(state.proposed_fire_damage(),7);assert!(state.frozen());assert_eq!(h.hp,7);
        let before=state.clone();assert!(state.advance_fire(200_000,Health{hp:0,terminal:true,..h}).unwrap().is_empty());assert_eq!(state.health(),before.health());assert_eq!(state.sequence(),before.sequence());
        let mut outcome=State::new_v2(profile).unwrap();let h=context(profile);outcome.apply_hits(&[hit(1,Target::Device(Device::Engine),0,0.)],h).unwrap();
        outcome.freeze();let before=outcome.clone();assert!(outcome.advance_fire(100_000,Health{terminal:true,..h}).unwrap().is_empty());
        assert_eq!(outcome.health(),before.health());assert_eq!(outcome.crew(),before.crew());assert_eq!(outcome.sequence(),before.sequence());assert_eq!(outcome.proposed_fire_damage(),0);
    }
}

#[test] fn p06t_device_v2_existing_proxy_uses_primary_roles_and_distinct_six_seats() {
    let b=[[0.;3],[1.;3]];
    let radio=proxy::select(Profile::Wt128,proxy::Component::Hull,b,[0.6,0.4,0.69],[0.6,0.4,0.95]).unwrap();
    assert_eq!(radio.iter().map(|hit|hit.target).collect::<Vec<_>>(),[Target::Seat(3)]);
    let fv=proxy::select(Profile::Fv183,proxy::Component::Hull,b,[0.6,0.4,0.69],[0.6,0.4,0.95]).unwrap();
    assert!(fv.iter().all(|hit|hit.target!=Target::Seat(0)),"combined radio duty does not move FV commander into a primary radio box");
    let loaders=proxy::select(Profile::Wt128,proxy::Component::Turret,b,[0.69,0.5,0.5],[0.95,0.5,0.5]).unwrap();
    assert_eq!(loaders.iter().map(|hit|hit.target).collect::<Vec<_>>(),[Target::Seat(4),Target::Seat(5)]);
}
