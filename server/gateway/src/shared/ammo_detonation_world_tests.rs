//! Production World/Trace/source geometry tests. Temporary shooter identities
//! are explicitly authored LAB fixtures; only the target FrozenLoss below is
//! parsed from an actual isolated SQLite writer response. No inventory grant.
use super::*;
use super::super::super::ammo_detonation::{LAUNCH_DRAWS,LAUNCH_ORDINAL};
use crate::{p06t_armament091 as arm,p06t_shells091 as source,p06t_lab_proxy::Target,
    profile13_loss091 as loss};
use sha2::{Digest,Sha256};

fn actual_reservation()->(Identity,loss::Reservation){
    let raw=include_bytes!("../../../../tests/fixtures/p06t-ammo-loss-writer-vectors.json");
    assert_eq!(format!("{:x}",Sha256::digest(raw)),"251c60f587d14d916e5381567d8af2982b26f0f98335af8464b75bbf1cc1f154");
    let vectors:serde_json::Value=serde_json::from_slice(raw).unwrap();
    let row=vectors["vectors"].as_array().unwrap().iter().find(|row|row["request"]["operation"]=="admit").unwrap();
    let q=&row["request"];let context=loss::Context{account_id:q["account_id"].as_str().unwrap().into(),
        native_database_id:q["native_database_id"].as_i64().unwrap()as i32,command_key:q["command_key"].as_str().unwrap().into(),
        expected_revision:q["expected_revision"].as_u64().unwrap(),run_id:q["run_id"].as_str().unwrap().into()};
    let battle=q["battle_id"].as_str().unwrap().rsplit(':').next().unwrap().parse().unwrap();
    let request=loss::Request::Admit{battle,native_inventory_id:q["native_inventory_id"].as_u64().unwrap()as u32};
    let parsed=loss::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&context,&request).unwrap();
    let reservation=parsed.reservation.unwrap();reservation.frozen.validate_owned(&context.account_id).unwrap();
    assert_eq!(reservation.frozen.base.counts(),[0,4,10]);
    (Identity{account:context.account_id,database:context.native_database_id,name:"actual_sqlite_loss_owner".into()},reservation)
}
fn template(now:Instant,id:u64,optin:bool)->World{
    let mut w=World::new_for_roster(id,now,crate::map_profile091::MapId::Karelia,2).unwrap();
    w.bind_geometry(Arc::new(super::super::super::geometry::tests::bundle())).unwrap();
    w.bind_geometry(Arc::new(super::super::super::geometry::tests::is7_bundle())).unwrap();
    w.enable_ap_test_lab().unwrap();w.bind_terrain(Arc::new(super::super::super::terrain::tests::fixture(-1000.,2000.,2,vec![-100.;4]))).unwrap();
    w.enable_mixed_ammo().unwrap();w.enable_lifecycle(super::super::super::lifecycle::Rules{
        prebattle_ms:1000,battle_ms:60000,..super::super::super::lifecycle::Rules::prohorovka()}).unwrap();
    if optin{w.enable_ammo_detonation().unwrap();}w
}
fn lab_attach(w:&mut World,slot:usize,counts:[u16;3]){
    w.mixed_ammo=false;
    assert_eq!(tests::attach_physics_profile(w,VehicleKind::Ms1,Identity{account:format!("authored-rack-lab-{slot}"),
        database:200+slot as i32,name:format!("rack-lab-{slot}")},slot as u32+1).unwrap(),slot);
    w.mixed_ammo=true;
    let shell=source::PROFILES[0].shots[counts.iter().position(|v|*v>0).unwrap()];
    w.actors[slot].fire=fire::State::with_typed(source::Mount::Ms1Stock,counts,shell.compact_descr).unwrap();
    w.actors[slot].devices=Some(device::State::new(caps::Profile::Ms1).unwrap());
}
fn start(w:&mut World,now:Instant){
    for(slot,p)in [[0.;3],[0.,0.,20.]].into_iter().enumerate(){w.actors[slot].position=p;w.actors[slot].origin=p;}
    w.start(now).unwrap();w.lifecycle_created_unix=Some(1792152000);
    for slot in 0..2{w.set_ready(slot,slot as u32+1).unwrap();}
    w.advance_lifecycle(now).unwrap();
}
fn aim(w:&mut World,point:[f32;3],now:Instant){
    w.apply(0,1,&[Command::Aim(aim::Intent::Point(point))],now).unwrap();
    for step in 1..=20{let at=now+STEP*step;w.advance(at).unwrap();w.advance_lifecycle(at).unwrap();}
}
fn advance_until(w:&mut World,until:Instant){
    // Exercise the production cadence. Lifecycle deliberately rejects a
    // multi-second catch-up; waiting for reload must not skip its 1s bound.
    while w.last<until{
        let at=(w.last+STEP).min(until);w.advance(at).unwrap();w.advance_lifecycle(at).unwrap();
    }
}
/// Search only finite legal Aim intents and actual first nearest contacts.
/// No hand-authored triangle, internal target choice or fake Trace admission.
fn first_rack_hit(base:&World,now:Instant)->(World,[f32;3]){
    for yaw in [0.,-std::f32::consts::PI]{
        for x in [-0.6,-0.3,0.,0.3,0.6]{for y in [0.6,0.8,1.,1.2]{for z in [19.,20.,21.]{
            let mut w=base.clone();w.actors[1].direction=[yaw,0.,0.];w.actors[1].yaw=yaw;
            let point=[x,y,z];aim(&mut w,point,now);let at=now+Duration::from_secs(2);
            w.apply(0,1,&[Command::Armament(arm::Command::Shoot)],at).unwrap();w.advance(at+STEP).unwrap();
            if w.actors[1].alive()&&!w.actors[1].devices.as_ref().unwrap().fire_active()
                &&w.device_events.iter().any(|(slot,event)|*slot==1&&matches!(event.change,
                device::Change::Device{device:caps::Device::AmmoBay,before:60,after:10,..})){
                assert_eq!(w.contacts.len(),1);assert!(w.geometry_for(VehicleKind::Ms1).unwrap().proxy_ray(&w.contacts[0]).is_ok());
                return(w,point);
            }
        }}}
    }panic!("actual source MS1 exterior ray must reach the explicit LAB AmmoBay proxy");
}
fn second(w:&mut World,now:Instant){
    let at=now+Duration::from_secs(5);advance_until(w,at);
    assert!(matches!(w.apply(0,1,&[Command::Armament(arm::Command::Shoot)],at).unwrap().as_slice(),
        [fire::Outcome::Typed(arm::Outcome::Shot{..})]));w.advance(at+STEP).unwrap();
}

#[test]fn p06t_ammo_detonation_actual_world_trace_owned_loss_one_death_and_results_terminal(){
    let now=Instant::now();let(owner,reservation)=actual_reservation();let mut w=template(now,reservation.battle,true);
    lab_attach(&mut w,0,[0,4,4]);assert_eq!(w.attach_owned_loss(owner,2,&reservation.frozen).unwrap(),1);start(&mut w,now);
    let(mut w,_)=first_rack_hit(&w,now);assert!(w.ammo_detonations().is_empty());assert_eq!(w.actors[1].health,60);
    second(&mut w,now);assert_eq!(w.ammo_detonations().len(),1);let event=w.ammo_detonations()[0];
    assert_eq!((event.target(),event.attacker(),event.shot()),(1,0,2));assert_eq!(event.lost(),[0,4,10]);assert_eq!(event.additional_damage(),30);
    assert_eq!(w.actors[1].health,0);assert!(!w.actors[1].alive());assert_eq!(w.actors[1].fire.typed().unwrap().counts(),[0;3]);
    assert_eq!(w.actors[1].fire.typed().unwrap().lost(),[0,4,10]);assert_eq!(w.actors[1].fire.accepted_shots(),0);
    let raw=w.impact.events().iter().filter_map(|e|match e{impact::Event::MixedResolution{target:1,health_before,health_after,..}=>Some((*health_before,*health_after)),_=>None}).collect::<Vec<_>>();
    assert_eq!(raw,[(90,60),(60,30)],"raw source plate Trace must never claim detonation HP");
    assert_eq!(w.impacts.iter().map(|e|(e.health_before,e.health_after)).collect::<Vec<_>>(),raw);
    assert_eq!(w.damage_events.iter().map(|e|(e.health_before,e.health_after,e.lethal())).collect::<Vec<_>>(),[(90,60,false),(60,0,true)]);
    assert_eq!(w.damage_events.iter().map(|e|e.health_before-e.health_after).sum::<i16>(),90);
    let terminal=super::super::super::profile13_session::TerminalLoss::from_actor_result(&reservation,&w,1,2,
        loss::FinishReason::ManualLeave,None).unwrap();terminal.validate().unwrap();
    assert!(matches!(terminal.request(),loss::Request::Finish{fired_ammunition,lost_ammunition,remaining_ammunition,loss_event:Some(cause),..}
        if fired_ammunition.iter().all(|v|v.count==0)&&lost_ammunition.map(|v|v.count)==[0,4,10]
            &&remaining_ammunition.iter().all(|v|v.count==0)&&cause.shot==2&&cause.target_slot==1));
    w.advance_lifecycle(now+Duration::from_millis(5100)).unwrap();
    let result=super::super::super::lifecycle_result::build(&w).unwrap();assert_eq!(result.participants[0].damage_dealt,90);
    assert_eq!(result.participants[0].kills,1);assert_eq!(result.participants[0].shots,2);assert_eq!(result.participants[1].shots,0);
    let terminal=super::super::super::profile13_session::TerminalLoss::from_actor_result(&reservation,&w,1,2,
        loss::FinishReason::BattleFinished,Some(&result)).unwrap();terminal.validate().unwrap();
    let frozen=w.clone();w.advance(now+Duration::from_secs(7)).unwrap();assert_eq!(w.damage_events,frozen.damage_events);
    w.advance_turret_flights(now+Duration::from_secs(7)).unwrap();assert_ne!(w.turret_flights()[0].sample(),frozen.turret_flights()[0].sample());
    assert_eq!(w.actors,frozen.actors);assert_eq!(w.damage_events,frozen.damage_events);assert_eq!(w.device_events,frozen.device_events);
    assert_eq!(w.ammo_detonations(),frozen.ammo_detonations());
}

#[test]fn p06t_ammo_detonation_old_v2_template_stays_device_only_and_new_policy_requires_frozen_wrapper(){
    let now=Instant::now();let(owner,reservation)=actual_reservation();let mut old=template(now,91,false);
    lab_attach(&mut old,0,[0,4,4]);lab_attach(&mut old,1,[2,3,4]);start(&mut old,now);
    let(mut old,_)=first_rack_hit(&old,now);second(&mut old,now);assert_eq!(old.actors[1].health,30);
    assert_eq!(old.actors[1].devices.as_ref().unwrap().health()[caps::Device::AmmoBay as usize],0);
    assert_eq!(old.actors[1].fire.typed().unwrap().counts(),[2,3,4]);assert!(old.ammo_detonations().is_empty());
    assert!(old.enable_ammo_detonation().is_err());
    let mut fresh=template(now,92,true);assert!(fresh.attach_owned_v2(owner.clone(),1,&reservation.frozen.base).is_err());assert!(fresh.actors.is_empty());
    assert!(template(now,93,false).attach_owned_loss(owner.clone(),1,&reservation.frozen).is_err());
    let mut changed=reservation.frozen.clone();changed.policy_sha256="0".repeat(64);
    assert!(fresh.attach_owned_loss(owner,1,&changed).is_err());assert!(fresh.actors.is_empty());
}

#[test]fn p06t_ammo_detonation_actual_last_shot_empty_bay_destroyed_does_not_explode(){
    let now=Instant::now();let mut w=template(now,94,true);lab_attach(&mut w,0,[0,4,4]);lab_attach(&mut w,1,[0,0,1]);start(&mut w,now);
    // Fire the target's actual last shell away before the incoming rack hit.
    w.actors[1].aim.yaw=1.5;w.actors[1].aim.park();w.actors[1].aim.pitch=0.1;w.actors[1].aim.park();
    let at=now+Duration::from_secs(1);w.advance(at).unwrap();w.advance_lifecycle(at).unwrap();
    w.apply(1,2,&[Command::Armament(arm::Command::Shoot)],at).unwrap();assert_eq!(w.actors[1].fire.typed().unwrap().counts(),[0;3]);
    // The bounded search starts at the already observed server time; no source
    // counts/transition or accepted-shot counter is manufactured.
    let(mut w,_)=first_rack_hit(&w,at);second(&mut w,at);
    assert_eq!(w.actors[1].health,30);assert!(w.actors[1].alive());assert_eq!(w.actors[1].fire.accepted_shots(),1);
    assert_eq!(w.actors[1].fire.typed().unwrap().fired(),[0,0,1]);assert_eq!(w.actors[1].fire.typed().unwrap().lost(),[0;3]);
    assert!(w.ammo_detonations().is_empty());assert!(w.turret_flights().is_empty());
}

#[test]fn p06t_ammo_detonation_joint_composition_matches_all_three_source_axes(){
    let now=Instant::now();let mut w=template(now,95,true);lab_attach(&mut w,0,[1,1,1]);
    let actor=&mut w.actors[0];actor.position=[37.,21.,-105.];actor.direction=[0.7,-0.3,0.2];actor.aim.yaw=-1.1;
    let joint=turret_joint(actor).unwrap();let offset=super::super::super::pose::rotate(actor.vehicle_kind().aim().pivot,actor.direction);
    assert_eq!(joint.position,std::array::from_fn(|i|actor.position[i]+offset[i]));
    for unit in [[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]{
        let expected=super::super::super::pose::rotate(super::super::super::pose::rotate(unit,[actor.aim.yaw,0.,0.]),actor.direction);
        let actual=super::super::super::pose::rotate(unit,joint.direction);
        for axis in 0..3{assert!((actual[axis]-expected[axis]).abs()<3e-7);}
    }
}

#[test]fn p06t_ammo_detonation_authoritative_transition_late_poison_rolls_back_world_candidate(){
    let now=Instant::now();let mut w=template(now,96,true);lab_attach(&mut w,0,[0,4,4]);lab_attach(&mut w,1,[2,3,4]);start(&mut w,now);
    let(mut w,_)=first_rack_hit(&w,now);
    let at=now+Duration::from_secs(5);advance_until(&mut w,at);
    w.apply(0,1,&[Command::Armament(arm::Command::Shoot)],at).unwrap();
    let mut poison=w.projectiles[0];poison.sequence=3;poison.launched=at;poison.stopped=false;w.projectiles.push(poison);
    let before=w.clone();assert!(w.advance(at+STEP).is_err());
    assert_eq!(w.actors,before.actors);assert_eq!(w.damage_events,before.damage_events);assert_eq!(w.device_events,before.device_events);
    assert_eq!(w.ammo_detonations(),before.ammo_detonations());assert_eq!(w.turret_flights(),before.turret_flights());
    assert_eq!(w.impact,before.impact);assert_eq!(w.rng_draws,before.rng_draws);assert_eq!(w.projectiles,before.projectiles);
}

#[test]fn p06t_ammo_detonation_module_batch_final_crew_and_rack_has_one_damage_record(){
    let now=Instant::now();let mut w=template(now,97,true);lab_attach(&mut w,0,[2,2,2]);lab_attach(&mut w,1,[2,3,4]);start(&mut w,now);
    // Explicit precondition only; the batch below is a real ModuleState batch,
    // not a forged Transition. Exterior admission is covered by fired tests.
    let shell=source::PROFILES[0].shots[1];let health=device::Health{hp:90,max_hp:90,terminal:false};
    let prior=[device::ModuleHit{cause:device::Cause{shot:1,attacker_slot:0},ordinal:0,at_ms:0,
        target:Target::Device(caps::Device::AmmoBay),shell,ignition_roll:0.9},
        device::ModuleHit{cause:device::Cause{shot:1,attacker_slot:0},ordinal:1,at_ms:0,
            target:Target::Seat(0),shell,ignition_roll:0.9}];
    w.actors[1].devices.as_mut().unwrap().apply_hits(&prior,health).unwrap();assert!(w.actors[1].alive());
    let crew_before=w.actors[1].alive();let batch=[device::ModuleHit{cause:device::Cause{shot:2,attacker_slot:0},ordinal:0,at_ms:100,
        target:Target::Device(caps::Device::AmmoBay),shell,ignition_roll:0.9},
        device::ModuleHit{cause:device::Cause{shot:2,attacker_slot:0},ordinal:1,at_ms:100,target:Target::Seat(1),shell,ignition_roll:0.9}];
    let mut actors=w.actors.clone();let events=actors[1].devices.as_mut().unwrap().apply_hits(&batch,health).unwrap();
    let extra=w.apply_rack_transition(&mut actors,1,&events,90,60,2,0,1001).unwrap();assert_eq!(extra,60);
    w.record_damage(&mut actors,1,0,2,1001,0,30+extra,crew_before,true,true).unwrap();
    assert_eq!(w.damage_events.len(),1);assert!(w.damage_events[0].lethal());assert_eq!(actors[1].health,0);
    assert_eq!(actors[1].fire.typed().unwrap().lost(),[2,3,4]);
}

#[test]fn p06t_ammo_detonation_clip_is_included_once_and_loss_never_becomes_fired_or_reload(){
    // Armament supports the source WT128 magazine independently of World kind
    // admission. This is a pure mounted-state regression, not a WT native gate.
    let now=Instant::now();let mounted=source::PROFILES[source::Mount::WtE100128.index()];
    let mut state=arm::State::new(mounted.mount,[6,2,1],mounted.shots[0].compact_descr).unwrap();
    assert_eq!(state.clip(),6);state.apply(&[arm::Command::Shoot],now).unwrap();
    assert_eq!(state.clip(),5);assert_eq!(state.counts(),[5,2,1]);assert_eq!(state.accepted(),1);
    assert_eq!(state.lose_loaded_for_detonation().unwrap(),[5,2,1]);assert_eq!(state.clip(),0);
    assert_eq!(state.counts(),[0;3]);assert_eq!(state.fired(),[1,0,0]);assert_eq!(state.lost(),[5,2,1]);
    assert_eq!(state.initial_counts(),[6,2,1]);assert_eq!(state.accepted(),1);assert_eq!(state.deadline(),None);
    let before=state.clone();assert!(state.lose_loaded_for_detonation().is_err());assert_eq!(state,before);
    state.advance(now+Duration::from_secs(120));assert_eq!(state.counts(),[0;3]);assert_eq!(state.clip(),0);
    assert_eq!(state.apply(&[arm::Command::Shoot],now+Duration::from_secs(120)).unwrap(),[arm::Outcome::Refused(arm::Refusal::Empty)]);
    assert_eq!(state.fired(),[1,0,0]);assert_eq!(state.lost(),[5,2,1]);
}

#[path="owner_hold_world_tests.rs"]
mod owner_hold_world_tests;

#[test]fn turret01_actual_rack_event_launches_jolt_body_from_journalled_battle_rng(){
    let now=Instant::now();
    let base=||{let(owner,reservation)=actual_reservation();let mut w=template(now,reservation.battle,true);
        lab_attach(&mut w,0,[0,4,4]);assert_eq!(w.attach_owned_loss(owner,2,&reservation.frozen).unwrap(),1);start(&mut w,now);
        let(mut w,_)=first_rack_hit(&w,now);w.enable_turret_jolt().unwrap();w};
    let mut w=base();let mut other_seed=w.clone();other_seed.rng_state^=0x5eed;let draws_before=w.rng_draws.len();
    second(&mut w,now);second(&mut other_seed,now);
    let flight=&w.turret_flights()[0];assert!(flight.awaiting_trajectory());let launch=flight.launch().unwrap();
    // Six draws after the hit's own rolls, journalled in order under the rack event's shot/target.
    let journal=&w.rng_draws[w.rng_draws.len()-LAUNCH_DRAWS..];assert!(w.rng_draws.len()>=draws_before+LAUNCH_DRAWS);
    assert_eq!(journal.iter().map(|(shot,target,ordinal,_)|(*shot,*target,*ordinal)).collect::<Vec<_>>(),
        (0..LAUNCH_DRAWS as u8).map(|i|(2,1,LAUNCH_ORDINAL+i)).collect::<Vec<_>>());
    assert_eq!(journal.iter().map(|r|r.3).collect::<Vec<_>>(),launch.draws.to_vec());
    // The attacker stands at -Z of the target: the sideways push keeps within 60 degrees of +Z.
    assert!(launch.linear_velocity[2]>0.&&launch.linear_velocity[2]>=launch.linear_velocity[0].abs()*0.5);
    // The same battle replayed: the same journal and launch. Another seed: another launch.
    let mut rerun=base();second(&mut rerun,now);
    assert_eq!(rerun.turret_flights()[0].launch(),Some(launch));assert_eq!(rerun.rng_draws,w.rng_draws);
    assert_ne!(other_seed.turret_flights()[0].launch().unwrap().linear_velocity,launch.linear_velocity);
    // Worker request: joint pose, turret+gun support points, the dead target as a wreck.
    let event=w.ammo_detonations()[0];
    let request=w.turret_launch_request(1).unwrap();assert_eq!(request.joint,event.joint());assert_eq!(request.wreck_slots,vec![1]);
    assert!((4..=98).contains(&request.turret_points.len())&&(4..=98).contains(&request.gun_points.len()));
    let gun_far=request.gun_points.iter().map(|p|p[2]).fold(f32::MIN,f32::max);
    let turret_far=request.turret_points.iter().map(|p|p[2]).fold(f32::MIN,f32::max);assert!(gun_far>turret_far,"the barrel reaches beyond the turret");
    assert!(w.turret_launch_request(0).is_err());
}
