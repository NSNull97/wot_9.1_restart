//! Actual owned5 Config/Job/World/Capture/Session pipeline. Transport/ACK and
//! lifecycle scheduling are AUTHORED; no authored Frozen/Completion/HP/results.
use super::*;
use crate::{identity091,hangar091,ammo_service091,profile13_hold091 as hold};
use sha2::{Digest,Sha256};use std::path::PathBuf;
use super::p08c_late_composition_tests as common;
use super::super::{geometry,terrain,lifecycle,aim,model::Command as DomainCommand};
use crate::{p06t_armament091 as arm,p06t_device_caps as caps};

fn barrier(value:&serde_json::Value,name:&str,summary:serde_json::Value){
    use std::io::Write;let root=plain(&PathBuf::from(value["barrier"].as_str().unwrap()));
    let marker=root.join(format!("{name}.ready.json"));let mut file=fs::OpenOptions::new().write(true).create_new(true).open(marker).unwrap();
    let raw=serde_json::to_vec_pretty(&summary).unwrap();assert!(raw.len()<=65536);file.write_all(&raw).unwrap();file.flush().unwrap();drop(file);
    let go=root.join(format!("{name}.go"));let deadline=Instant::now()+Duration::from_secs(40);
    while !go.is_file(){assert!(Instant::now()<deadline,"readonly SQL barrier timeout");std::thread::sleep(Duration::from_millis(10));}
    assert_eq!(fs::read(go).unwrap(),b"GO\n");
}
fn pstate(s:&Session)->&super::super::profile13_session::State{s.shared.as_ref().unwrap().profile13.as_ref().unwrap()}
fn receive(s:&mut Session,raw:&[u8]){let frame=Frame{flags:0x458,sequence:Some(s.rx),cumulative:Some(s.tx.cumulative),selective:vec![],body:[vec![1],s.token.to_le_bytes().to_vec(),raw.to_vec()].concat(),piggybacks:vec![]};assert!(!s.receive(&frame,Instant::now()).unwrap());}
fn session(config:&identity091::Config,user:&serde_json::Value,id:u32,dispatch:&profile13_dispatch::Dispatcher)->Session{
    assert!(config.p08b_owner_battle_hold&&config.p06t_ammo_rack_detonation&&config.visibility_v1&&!config.p08c_late_results&&!config.training_rooms);
    let owner=Arc::new(config.authenticate(user["email"].as_str().unwrap(),user["password"].as_str().unwrap()).unwrap().expect("actual isolated own Config authentication"));
    assert_eq!(owner.account_id,user["account_id"]);let fixtures=Arc::new(hangar091::Fixtures::load_p04m(&owner.fixture_dir).unwrap());
    let binding=ammo_service091::metadata_research(&owner.fixture_dir,&owner.account_id,owner.database_id).unwrap();
    let login=config.inspect_hold_login(&owner,&fixtures,binding).unwrap().expect("actual Inspect5 source binding");
    let now=Instant::now();let mut s=Session::new(id,[id as u8;16],format!("127.0.0.1:{}",41800+id).parse().unwrap(),now);
    s.active=true;s.account_ready=true;s.account_probe=true;s.sync_mask=7;s.rx=1;s.tx=Window::interactive();s.base_peer=Some(format!("127.0.0.1:{}",41900+id).parse().unwrap());
    s.login_attempt=Some(LoginAttempt::new(s.key,s.id,s.login_peer));s.identity=Some(owner);s.hangar=Some(fixtures);
    s.ammo_service=Some(ammo_session::State::new(binding,config.crew_service).with_transfer(config.crew_transfer).with_cross_vehicle(config.crew_cross_vehicle)
        .with_roster_recruitment(config.crew_roster_recruitment).with_progression(config.crew_progression).with_dismissal(config.crew_dismissal)
        .with_barracks(config.crew_barracks_recruitment).with_research(config.research_service));
    s.ammo_service.as_mut().unwrap().replace_pool(s.hangar.as_ref().unwrap().p04m_binding().cloned()).unwrap();
    let mut c=Client::new(0);c.enable_spotting().unwrap();c.join_requested=false;c.hangar_since=Some(now-Duration::from_secs(4));
    c.profile13=Some(super::super::profile13_session::State::new(config.battle_run_id.clone(),binding.revision).unwrap());s.shared=Some(c);
    dispatch.install_hold_login(&mut s,login).unwrap();s
}
fn world(arena:u64,now:Instant)->World{
    let mut w=World::new_for_roster(arena,now,crate::map_profile091::MapId::Karelia,4).unwrap();
    w.bind_geometry(Arc::new(geometry::tests::bundle())).unwrap();w.bind_geometry(Arc::new(geometry::tests::is7_bundle())).unwrap();w.enable_ap_test_lab().unwrap();
    w.bind_terrain(Arc::new(terrain::tests::fixture(-1000.,2000.,2,vec![-100.;4]))).unwrap();w.enable_mixed_ammo().unwrap();
    w.enable_lifecycle(lifecycle::Rules{prebattle_ms:1000,battle_ms:60000,afterbattle_ms:1000,..lifecycle::Rules::prohorovka()}).unwrap();
    w.enable_ammo_detonation().unwrap();w.enable_result_spots().unwrap();w.enable_owner_hold().unwrap();w
}
fn settle_one(dispatch:&mut profile13_dispatch::Dispatcher,table:&mut Table,w:&World,config:Arc<identity091::Config>){
    dispatch.start(table,w,config.clone(),Instant::now()).unwrap();assert!(dispatch.busy(),"real singleton writer must start");let deadline=Instant::now()+Duration::from_secs(50);
    while dispatch.busy(){assert!(Instant::now()<deadline,"same immutable real writer/publication must settle");dispatch.poll(table,config.clone(),Instant::now()).unwrap();std::thread::sleep(Duration::from_millis(10));}
}
fn warm(s:&mut Session,locked:bool){
    assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Returning);common::drain(s);receive(s,&[9]);common::drain(s);
    let cursor=s.shared.as_ref().unwrap().return_source_revision;let fixtures=s.hangar.as_ref().unwrap().clone();receive(s,&common::sync(501,100,cursor));common::drain(s);
    let mut tail=common::sync(502,300,fixtures.shop_sync_revision().unwrap());tail.extend(common::sync(503,600,0));receive(s,&tail);common::drain(s);
    assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Account);assert_eq!(s.ammo_service.as_ref().unwrap().wire_revision(),1);
    assert_eq!(pstate(s).garage_idle(),!locked);assert_eq!(pstate(s).reservation_hold.is_some(),locked);
}

/// AUTHORED transport scheduling using the source-validated native records.
/// All phases, create/binding ACKs and correction are advanced by actual
/// Session::receive/Window. No direct Phase/arena_base/creation/window edits.
fn enter_native_avatar(s:&mut Session){
    let slot=s.shared.as_ref().unwrap().slot;
    assert!(s.arena_base);assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Enable);
    assert_eq!(s.tx.len(),0);assert!(s.outbox.is_empty()); // actual reset ACKed
    receive(s,&[9]);common::drain(s);
    let c=s.shared.as_ref().unwrap();assert_eq!(c.phase,Phase::Entities);
    assert!(c.announcement.is_some_and(|(_,acked)|acked));assert!(c.creations[slot].is_none());
    let mut request=vec![8,4,0];request.extend(wire::vehicle_id(slot).unwrap().to_le_bytes());
    receive(s,&request);common::drain(s);
    assert!(s.shared.as_ref().unwrap().creations[slot].is_some_and(|(_,acked)|acked));
    // Measured native four-method33B READY from shared/wire.rs::ready_is_bound_
    // to_each_players_own_vehicle. Only the explicit own Vehicle ID changes.
    let mut ready=[0x0d,8,0,0,0,0,0,3,0,16,9,0x8d,5,0,2,1,0,0,0,0x86,0,0,0x0c,8,0,0,0,0,0,0,0,0,0];
    ready[7..11].copy_from_slice(&wire::vehicle_id(slot).unwrap().to_le_bytes());
    wire::ready(&ready,slot).unwrap();assert!(wire::ready(&ready,(slot+1)%4).is_err());
    receive(s,&ready);common::drain(s);
    let c=s.shared.as_ref().unwrap();assert_eq!(c.phase,Phase::Driving);
    assert!(c.binding.is_some_and(|(_,acked)|acked));assert!(!c.correction);
    receive(s,&[6]);common::drain(s);
    let c=s.shared.as_ref().unwrap();assert_eq!(c.phase,Phase::Driving);
    assert!(c.correction&&c.binding.is_some_and(|(_,acked)|acked));
    assert_eq!(s.tx.len(),0);assert!(s.outbox.is_empty());
}

// Finite exterior-ray search adapted from ammo_detonation_world_tests.
// Placements/orientations/Aim scheduling are AUTHORED. Every retained shot,
// contact, module transition, HP change and accepted count comes from World.
fn advance_between(w:&mut World,mut at:Instant,until:Instant){
    assert!(until>=at);while at<until{at=(at+model::STEP).min(until);w.advance(at).unwrap();w.advance_lifecycle(at).unwrap();w.advance_turret_flights(at).unwrap();}
}
fn first_owned_rack_hit(base:&World,at:Instant)->(World,[f32;3],Instant){
    assert_eq!(base.actors.len(),4);assert_eq!(base.actors[0].health,90);
    assert_eq!(base.actors[1].session,Some(12));assert!(base.damage_events.is_empty());
    assert!(base.actors.iter().all(|a|a.owned_hold.is_some()));
    for yaw in [0.,-std::f32::consts::PI]{
        for x in [-0.6,-0.3,0.,0.3,0.6]{for y in [0.6,0.8,1.,1.2]{for z in [19.,20.,21.]{
            let mut w=base.clone();
            let rows=w.actors.iter().enumerate().map(|(slot,a)|(slot,a.position,if slot==0{[yaw,0.,0.]}else{a.direction},0.)).collect::<Vec<_>>();
            w.import_external_poses(&rows).unwrap();
            let point=[x,y,z];w.apply(1,12,&[DomainCommand::Aim(aim::Intent::Point(point))],at).unwrap();
            let fired_at=at+Duration::from_secs(2);advance_between(&mut w,at,fired_at);
            assert!(matches!(w.apply(1,12,&[DomainCommand::Armament(arm::Command::Shoot)],fired_at).unwrap().as_slice(),
                [crate::battle091::fire::Outcome::Typed(arm::Outcome::Shot{..})]));
            let hit_at=fired_at+model::STEP;advance_between(&mut w,fired_at,hit_at);
            if w.actors[0].alive()&&!w.actors[0].devices.as_ref().unwrap().fire_active()
                &&w.device_events.iter().any(|(slot,e)|*slot==0&&matches!(e.change,
                    crate::p06t_device_state::Change::Device{device:caps::Device::AmmoBay,before:60,after:10,..})){
                assert_eq!(w.contacts.len(),1);assert_eq!(w.contacts[0].target_slot,0);
                w.geometry_for(w.actors[0].vehicle_kind()).unwrap().proxy_ray(&w.contacts[0]).unwrap();
                assert_eq!(w.damage_events.len(),1);let hit=&w.damage_events[0];
                assert_eq!((hit.attacker,hit.target,hit.shot,hit.health_before,hit.health_after,hit.lethal()),(1,0,1,90,60,false));
                assert_eq!(w.actors[1].fire.accepted_shots(),1);assert!(w.ammo_detonations().is_empty());
                return(w,point,hit_at);
            }
        }}}
    }panic!("finite legal D Aim/source mesh search did not find genuine first C AmmoBay hit; no fallback/injection");
}
fn phase(value:&serde_json::Value)->serde_json::Value{
    let config=Arc::new(identity091::Config::load(value["config"].as_str().unwrap()).unwrap());let users=value["users"].as_array().unwrap();assert_eq!(users.len(),4);
    assert_eq!(config.battle_players,4);
    let arena=value["arena_id"].as_str().unwrap().parse::<u64>().unwrap();let mut dispatch=profile13_dispatch::Dispatcher::default();
    let sessions=users.iter().enumerate().map(|(slot,user)|session(&config,user,11+slot as u32,&dispatch)).collect::<Vec<_>>();
    assert_eq!(sessions.iter().map(|s|s.identity.as_ref().unwrap().database_id).collect::<Vec<_>>(),[3,4,1,2]);
    assert!(sessions.iter().all(|s|pstate(s).garage_idle()));
    let mut table=Table{sessions,capacity:4,..Table::default()};barrier(value,"after-auth",serde_json::json!({"actual_auth":4}));
    let now=Instant::now();let mut w=world(arena,now);
    for s in &mut table.sessions{let mut join=common::sync(202,700,1);join[15..19].copy_from_slice(&1i32.to_le_bytes());receive(s,&join);}
    for _ in 0..4{settle_one(&mut dispatch,&mut table,&w,config.clone());}
    for s in &mut table.sessions{assert!(pstate(s).reservation_hold.is_some());assert!(common::drain(s).contains(&crate::map_drive_world091::queue_callback(true)));}
    dispatch.attach_hold_ready_group(&mut table,&mut w,&config.battle_run_id,Instant::now()).unwrap();assert_eq!(w.actors.len(),4);
    for slot in 0..4{assert_eq!(w.actors[slot].session,Some(11+slot as u32));assert_eq!(w.team(slot).unwrap(),1+(slot%2)as u8);assert!(w.actors[slot].owned_hold.is_some());}
    assert_eq!(w.actors.iter().map(|a|a.fire.typed().unwrap().counts()).collect::<Vec<_>>(),[[0,4,10],[0,4,10],[0,4,11],[14,0,0]]);
    let capture=dispatch.hold_capture_for_test().unwrap();let sources=capture.links().iter().map(|l|serde_json::json!({"account_id":l.source().account_id,"session_id":l.source().source_session_id,"actor_slot":l.source().actor_slot})).collect::<Vec<_>>();
    let link=capture.link(0).unwrap().source().clone();let reservation=capture.link(0).unwrap().reservation().clone();let source_revision=capture.link(0).unwrap().revision();
    barrier(value,"after-admit",serde_json::json!({"actual_admitted":4,"actors":w.actors.len(),"arena":arena.to_string(),"source_sessions":sources}));
    w.lifecycle_created_unix=Some(u32::try_from(std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs()).unwrap());w.start(now).unwrap();
    // Explicit analytic test placement, before any ready/action. C is the
    // retained target; D shoots; genuine A/B sustain opposite sides away from it.
    w.rebase_external_spawn_rows(&[[0.,0.,20.],[0.,0.,0.],[80.,0.,80.],[80.,0.,100.]]).unwrap();
    for(slot,s)in table.sessions.iter_mut().enumerate(){w.set_ready(slot,s.id).unwrap();s.shared_start(&w,now).unwrap();common::drain(s);}
    // C stays a legitimate Enable early exit; D/A/B genuinely enter Driving.
    assert_eq!(table.sessions[0].shared.as_ref().unwrap().phase,Phase::Enable);
    for s in &mut table.sessions[1..]{enter_native_avatar(s);}
    w.advance_lifecycle(now).unwrap();advance_between(&mut w,now,now+Duration::from_secs(1));
    let(mut w,aim_point,first_at)=first_owned_rack_hit(&w,now+Duration::from_secs(1));
    assert_eq!(w.lifecycle.as_ref().unwrap().phase(),lifecycle::Phase::Battle);
    let departure_hp=w.actors[0].health;let before_departure_damage=w.damage_events.len();
    profile13_dispatch::Dispatcher::terminal(&mut table.sessions[0],&w,crate::battle091::profile13::FinishReason::ManualLeave).unwrap();w.detach(11).unwrap();dispatch.observe_hold_world(&table,&w).unwrap();
    // HTTP is awaited while the AUTHORED logical clock is paused; N4 remains
    // Battle independently because real owned teammate A is present/alive.
    settle_one(&mut dispatch,&mut table,&w,config.clone());warm(&mut table.sessions[0],true);
    assert!(dispatch.hold_capture_for_test().unwrap().held_inspected(0).unwrap());assert_eq!(pstate(&table.sessions[0]).revision,source_revision);
    assert_eq!(pstate(&table.sessions[0]).reservation_hold.as_ref(),Some(&reservation));assert_eq!(w.actors[0].session,None);
    barrier(value,"held-inspect",serde_json::json!({"actual_inspect":1,"actual_reserved_fresh":true,"old_actor_authority":false}));
    dispatch.retire(&mut table,&mut w,11,Instant::now(),"composition_locked_account_disconnect").unwrap();assert!(dispatch.retired_for_test(11).is_some());
    settle_one(&mut dispatch,&mut table,&w,config.clone());assert!(dispatch.retired_for_test(11).is_none());
    let replacement=session(&config,&users[0],77,&dispatch);assert!(!replacement.arena_base&&!replacement.shared.as_ref().unwrap().join_requested);
    assert_eq!(pstate(&replacement).reservation_hold.as_ref(),Some(&reservation));assert!(!pstate(&replacement).garage_idle());table.sessions.push(replacement);assert_eq!(table.sessions.len(),4);
    let cindex=table.sessions.iter().position(|s|s.id==77).unwrap();
    barrier(value,"held-relogin",serde_json::json!({"actual_auth":5,"new_avatar":false,"source_session_id":11,"delivery_session_id":77,"account_locked":true}));
    let second_at=now+Duration::from_secs(6);advance_between(&mut w,first_at,second_at);
    assert_eq!(w.lifecycle.as_ref().unwrap().phase(),lifecycle::Phase::Battle);assert!(w.actors[2].alive()&&w.actors[2].session==Some(13));
    assert!(w.apply(0,11,&[DomainCommand::Armament(arm::Command::Shoot)],second_at).is_err(),"detached C never regains authority");
    assert!(matches!(w.apply(1,12,&[DomainCommand::Armament(arm::Command::Shoot)],second_at).unwrap().as_slice(),[crate::battle091::fire::Outcome::Typed(arm::Outcome::Shot{..})]));
    let hit_at=second_at+model::STEP;advance_between(&mut w,second_at,hit_at);
    assert_eq!(w.lifecycle.as_ref().unwrap().phase(),lifecycle::Phase::Battle);assert_eq!(w.actors[0].session,None);assert_eq!(w.actors[0].health,0);
    assert_eq!(w.damage_events.len(),2);assert_eq!(w.damage_events.len()-before_departure_damage,1);
    let damage=&w.damage_events[1];assert_eq!((damage.attacker,damage.target,damage.shot,damage.health_before,damage.health_after,damage.lethal()),(1,0,2,60,0,true));
    assert_eq!(w.ammo_detonations().len(),1);let event=w.ammo_detonations()[0];assert_eq!((event.attacker(),event.target(),event.shot()),(1,0,2));assert_eq!(event.lost(),[0,4,10]);assert_eq!(event.additional_damage(),30);
    let raw=w.impact.events().iter().filter_map(|e|match e{super::super::impact::Event::MixedResolution{target:0,attacker:1,health_before,health_after,..}=>Some((*health_before,*health_after)),_=>None}).collect::<Vec<_>>();
    assert_eq!(raw,[(90,60),(60,30)],"raw plate trace must not pretend detonation HP");
    assert_eq!(w.damage_events.iter().filter(|e|e.target==0).map(|e|(e.health_before,e.health_after)).collect::<Vec<_>>(),[(90,60),(60,0)]);
    assert_eq!(w.damage_events.iter().filter(|e|e.target==0&&e.lethal()).count(),1);
    assert_eq!(w.actors[0].fire.typed().unwrap().fired(),[0;3]);assert_eq!(w.actors[0].fire.typed().unwrap().lost(),[0,4,10]);assert_eq!(w.actors[0].fire.typed().unwrap().counts(),[0;3]);assert_eq!(w.actors[0].fire.accepted_shots(),0);
    assert_eq!(w.actors[1].fire.typed().unwrap().fired(),[0,2,0]);assert_eq!(w.actors[1].fire.accepted_shots(),2);
    assert_eq!(w.actors[0].devices.as_ref().unwrap().health()[caps::Device::AmmoBay as usize],0);
    // Re-advance accepted time, then a fresh idle tick: no duplicate damage,
    // second loss or kill and no authority comeback. No event replay injection.
    let frozen_damage=w.damage_events.clone();let frozen_racks=w.ammo_detonations().to_vec();
    w.advance(hit_at).unwrap();w.advance_lifecycle(hit_at).unwrap();let idle_at=hit_at+model::STEP;advance_between(&mut w,hit_at,idle_at);
    assert_eq!(w.damage_events,frozen_damage);assert_eq!(w.ammo_detonations(),frozen_racks);
    let parked=serde_json::json!({"actor_slot":0,"account_id":link.account_id,"source_session_id":11,"world_phase":"battle","session_authority":false,
        "account_locked":!pstate(&table.sessions[cindex]).garage_idle(),"actual_held_inspect":dispatch.hold_capture_for_test().unwrap().held_inspected(0).unwrap(),
        "actual_damage_records":w.damage_events.len()-before_departure_damage,"total_damage_records":w.damage_events.len(),"predeparture_damage_records":before_departure_damage,
        "actual_rack_records":w.ammo_detonations().len(),"actual_kill_records":w.damage_events.iter().filter(|e|e.target==0&&e.lethal()).count(),"initial_hp":90,"departure_hp":departure_hp,
        "final_hp":w.actors[0].health,"actual_ammo_bay_hp":w.actors[0].devices.as_ref().unwrap().health()[caps::Device::AmmoBay as usize],"remaining_counts":w.actors[0].fire.typed().unwrap().counts(),
        "fired_counts":w.actors[0].fire.typed().unwrap().fired(),"lost_counts":w.actors[0].fire.typed().unwrap().lost(),"accepted_shots":w.actors[0].fire.accepted_shots(),
        "repeat_event_applied":false,"teammate_alive":w.actors[2].alive(),"damage_actor_present":w.actors.get(0).is_some(),"raw_plate_hp":raw,"aim_point":aim_point,
        "causal_attacker_slot":event.attacker(),"causal_target_slot":event.target(),"causal_shot":event.shot(),"additional_detonation_damage":event.additional_damage()});
    barrier(value,"parked-damaged",parked.clone());
    // AUTHORED timer rules/clock, actual authoritative Timeout outcome. No HP,
    // outcome, result, crew transition or final receipt is constructed by test.
    let outcome_at=now+Duration::from_secs(61);advance_between(&mut w,idle_at,outcome_at);
    let outcome=w.lifecycle.as_ref().unwrap().outcome().unwrap();assert_eq!(outcome.reason,lifecycle::Reason::Timeout);assert_eq!(outcome.winner,0);
    dispatch.observe_hold_world(&table,&w).unwrap();let sealed=dispatch.hold_capture_for_test().unwrap().seal().unwrap().results().unwrap().clone();assert!(sealed.interaction_details.is_some());assert_eq!(sealed.participants.len(),4);
    let cresult=sealed.participants.iter().find(|p|p.account_dbid==3).unwrap();assert!(cresult.premature_leave);assert_eq!(cresult.health,0);assert_eq!(cresult.shots,0);
    let dresult=sealed.participants.iter().find(|p|p.account_dbid==4).unwrap();assert_eq!((dresult.damage_dealt,dresult.kills,dresult.shots),(90,1,2));
    stage_lifecycle_results_from(&mut table,&w,Some(sealed.clone())).unwrap();
    let old_wire=table.sessions[cindex].ammo_service.as_ref().unwrap().wire_revision();for _ in 0..128{table.sessions[cindex].outbox.push_back(vec![13,1]);}
    dispatch.start(&mut table,&w,config.clone(),Instant::now()).unwrap();let deadline=Instant::now()+Duration::from_secs(50);
    let sql_revision=loop{assert!(Instant::now()<deadline);dispatch.poll(&mut table,config.clone(),Instant::now()).unwrap();if let Some((sid,revision))=dispatch.hold_final_completed_for_test(){assert_eq!(sid,11);break revision;}std::thread::sleep(Duration::from_millis(10));};
    assert_eq!(sql_revision,source_revision+1);assert_eq!(pstate(&table.sessions[cindex]).revision,source_revision);assert!(pstate(&table.sessions[cindex]).reservation_hold.is_some());
    barrier(value,"first-final",serde_json::json!({"actual_finished":1}));
    barrier(value,"before-final-update",serde_json::json!({"account_cache_revision":pstate(&table.sessions[cindex]).revision,"sql_revision":sql_revision,"account_locked":true}));
    common::drain(&mut table.sessions[cindex]);dispatch.poll(&mut table,config.clone(),Instant::now()+Duration::from_secs(3)).unwrap();assert!(dispatch.hold_final_completed_for_test().is_none());
    let bodies=common::drain(&mut table.sessions[cindex]);let updates=bodies.iter().filter(|b|b.starts_with(&[0x13,0x57])).collect::<Vec<_>>();assert_eq!(updates.len(),1);
    assert!(pstate(&table.sessions[cindex]).garage_idle());assert_eq!(table.sessions[cindex].ammo_service.as_ref().unwrap().revision(),sql_revision);assert_eq!(table.sessions[cindex].ammo_service.as_ref().unwrap().wire_revision(),old_wire+1);
    let current=&table.sessions[cindex];let owner=current.identity.as_ref().unwrap();let state_sha=current.hangar.as_ref().unwrap().state_sha256().iter().map(|b|format!("{b:02x}")).collect::<String>();
    let binding=config.hold_binding(owner,sql_revision,&state_sha).unwrap();let counts=w.actors[0].fire.typed().unwrap().counts();let layout=binding.layout_for(&reservation.frozen,counts).unwrap();
    assert_eq!(updates[0].as_slice(),crate::profile13_hold_projection091::final_update(layout,old_wire).unwrap().as_slice());
    let native_update_hex=updates[0].iter().map(|b|format!("{b:02x}")).collect::<String>();assert_eq!(dispatch.hold_capture_for_test().unwrap().link(0).unwrap().source(),&link);
    barrier(value,"final-update",serde_json::json!({"method_id":0x57,"source_revision":source_revision,"destination_revision":sql_revision,"old_wire_revision":old_wire,"new_wire_revision":old_wire+1,"lock_removed":true,"source_session_id":11,"delivery_session_id":77}));
    for sid in [12,13,14]{let index=table.sessions.iter().position(|s|s.id==sid).unwrap();
        assert_eq!(table.sessions[index].shared.as_ref().unwrap().phase,Phase::Driving);
        profile13_dispatch::Dispatcher::terminal(&mut table.sessions[index],&w,crate::battle091::profile13::FinishReason::BattleFinished).unwrap();w.detach(sid).unwrap();
        assert_eq!(table.sessions[index].shared.as_ref().unwrap().phase,Phase::Leaving);
        settle_one(&mut dispatch,&mut table,&w,config.clone());assert!(pstate(&table.sessions[index]).reservation_hold.is_none());
        assert_eq!(table.sessions[index].shared.as_ref().unwrap().phase,Phase::Leaving);
        assert!(deliver_lifecycle_result(&mut table.sessions[index],&w,Instant::now()).unwrap());common::drain(&mut table.sessions[index]);receive(&mut table.sessions[index],&[0x99,1,0,0,0x87,0,0]);
        assert!(table.sessions[index].battle_results.avatar_confirmed());assert!(deliver_lifecycle_result(&mut table.sessions[index],&w,Instant::now()).unwrap());warm(&mut table.sessions[index],false);
    }
    assert!(dispatch.hold_capture_for_test().is_none());assert_eq!(table.sessions.len(),4);
    barrier(value,"all-final",serde_json::json!({"actual_finished":4,"actual_world_results8":true,"source_link_unchanged":true}));
    for s in &mut table.sessions{receive(s,&common::sync(601,1500,arena as i64));}
    let mut queries=super::super::results_session::Manager::default();common::results(&mut table,&mut queries,config.clone());
    for s in &mut table.sessions{assert_eq!(s.battle_results.cached().unwrap().as_ref(),sealed.as_ref());assert!(common::drain(s).iter().any(|b|b.starts_with(&[0x13,0x4d])));receive(s,&common::sync(202,1501,arena as i64));}
    common::results(&mut table,&mut queries,config.clone());for s in &mut table.sessions{assert!(common::drain(s).is_empty());}
    barrier(value,"queries-acked",serde_json::json!({"actual_queries":4,"actual_acks":4,"record_contracts":["hold-v1","hold-v1","hold-v1","hold-v1"]}));
    serde_json::json!({"status":"PASS_ACTUAL_HOLD5_FOUR_RUNTIME_HTTP_SQLITE","actual_admitted":4,"actual_finished":4,"new_grants":0,"run":config.battle_run_id,"arena_id":arena.to_string(),"results_json":serde_json::to_string(sealed.as_ref()).unwrap(),"native_update_hex":native_update_hex,"parked":parked,"native_client":"NOT_RUN","authored_control":"Session/ACK; analytic placement/flat terrain; Aim point finite search; ready/100ms clock and 60s timeout rules; no authored Frozen/Completion/HP/device transition/results/death"})
}

fn plain(path:&std::path::Path)->PathBuf{
    use std::path::Component;
    assert!(path.is_absolute(),"absolute owned path required");
    let mut cursor=PathBuf::new();
    for part in path.components(){
        assert!(!matches!(part,Component::ParentDir|Component::CurDir),"noncanonical lexical path");
        cursor.push(part.as_os_str());
        if matches!(part,Component::Normal(_)){
            let metadata=fs::symlink_metadata(&cursor).unwrap();assert!(!metadata.file_type().is_symlink(),"linked path refused");
            #[cfg(windows)]{use std::os::windows::fs::MetadataExt;assert_eq!(metadata.file_attributes()&0x400,0,"reparse path refused");}
        }
    }
    path.canonicalize().unwrap()
}
fn bounded_record(path:&std::path::Path)->serde_json::Value{
    let path=plain(path);let raw=fs::read(path).unwrap();assert!(raw.len()<=16384);
    crate::profile13_v2091::bounded_json(&raw,16384).unwrap()
}
fn record_ref(path:&std::path::Path)->serde_json::Value{
    let path=plain(path);serde_json::json!({"path":path,"sha256":format!("{:x}",Sha256::digest(fs::read(&path).unwrap()))})
}
fn allocation(root:&std::path::Path,target:&std::path::Path)->(PathBuf,serde_json::Value){
    let build=plain(&root.join("local/build"));
    if target.starts_with(&build){
        assert_eq!(target.file_name().unwrap(),"target");let output=plain(target.parent().unwrap());assert_ne!(output,build);
        assert!(!output.join("cargo-temp-target.json").exists(),"normal target cannot impersonate temporary allocation");
        return (output,serde_json::Value::Null);
    }
    let os_temp=plain(&std::env::temp_dir());assert_eq!(target.parent().unwrap(),os_temp);
    assert!(target.file_name().unwrap().to_str().unwrap().starts_with("wot091-cargo-"));
    let origin_path=target.join("wot091-build-origin.json");let origin=bounded_record(&origin_path);
    assert_eq!(origin.as_object().unwrap().len(),8);assert_eq!(origin["schema"],"wot091-cargo-temp-target.v1");
    let output=plain(&PathBuf::from(origin["output"].as_str().unwrap()));assert!(output.starts_with(&build)&&output!=build);
    #[cfg(windows)]{
        assert_ne!(os_temp.components().next().unwrap().as_os_str().to_string_lossy().to_lowercase(),
            output.components().next().unwrap().as_os_str().to_string_lossy().to_lowercase(),"temporary allocation must be on another drive");
    }
    let metadata_path=output.join("cargo-temp-target.json");let metadata=bounded_record(&metadata_path);
    assert_eq!(metadata.as_object().unwrap().len(),7);let mut without_output=origin.clone();without_output.as_object_mut().unwrap().remove("output");
    assert_eq!(metadata,without_output);assert_eq!(plain(&PathBuf::from(metadata["target"].as_str().unwrap())),target);
    assert_eq!(plain(&PathBuf::from(metadata["default_os_temp"].as_str().unwrap())),os_temp);
    assert_eq!(metadata["retained_for_audit"],true);assert_eq!(metadata["automatic_delete"],false);
    assert_eq!(metadata["source"],"tempfile.gettempdir(); fresh mkdtemp; no caller path");
    assert!(!metadata["created_utc"].as_str().unwrap().is_empty());
    let environment_path=output.join("cargo-temp-environment.json");let environment=bounded_record(&environment_path);
    let allowed=["CARGO_HOME","RUSTUP_HOME","CARGO_TARGET_DIR","CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER","RUSTFLAGS","CARGO_INCREMENTAL","RUST_TEST_THREADS","CARGO_PROFILE_DEV_DEBUG","CARGO_PROFILE_TEST_DEBUG"];
    assert!(environment.as_object().unwrap().keys().all(|key|allowed.contains(&key.as_str())));
    assert_eq!(plain(&PathBuf::from(environment["CARGO_TARGET_DIR"].as_str().unwrap())),target);
    for (key,value) in environment.as_object().unwrap(){assert_eq!(std::env::var(key).unwrap(),value.as_str().unwrap(),"recorded Cargo environment differs");}
    (output,serde_json::json!({"origin":record_ref(&origin_path),"metadata":record_ref(&metadata_path),"environment":record_ref(&environment_path)}))
}

fn parent(){
    use std::{collections::BTreeMap,process::{Command,Stdio}};
    let root=PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap();
    let test_source="server/gateway/src/shared/owner_hold_four_composition_tests.rs";
    let helper="web/tests/helpers/p08b-owner-hold-four-composition.mjs";
    let compiled_test=format!("{:x}",Sha256::digest(include_bytes!("owner_hold_four_composition_tests.rs")));
    let compiled_helper=format!("{:x}",Sha256::digest(include_bytes!("../../../../web/tests/helpers/p08b-owner-hold-four-composition.mjs")));
    let compiled_common=format!("{:x}",Sha256::digest(include_bytes!("../../../../web/tests/helpers/p08c-late-result-composition.mjs")));
    let compiled_barriers=format!("{:x}",Sha256::digest(include_bytes!("../../../../web/tests/helpers/p08b-hold-four-sql-barriers.mjs")));
    assert_eq!(format!("{:x}",Sha256::digest(fs::read(root.join(test_source)).unwrap())),compiled_test);
    assert_eq!(format!("{:x}",Sha256::digest(fs::read(root.join(helper)).unwrap())),compiled_helper);
    let executable=plain(&std::env::current_exe().unwrap());
    let target=plain(&PathBuf::from(std::env::var_os("CARGO_TARGET_DIR").expect("recorded canonical Cargo target required")));
    assert_eq!(executable.parent().unwrap(),target.join("debug/deps"));
    let name=executable.file_name().unwrap().to_str().unwrap();
    assert!(name.starts_with("sr_gateway-")&&name.ends_with(".exe"),"same canonical gateway test artifact required");
    let (output_root,allocation)=allocation(&root,&target);
    let git=|args:&[&str]|{let out=Command::new("git").args(args).current_dir(&root).output().unwrap();assert!(out.status.success());out.stdout};
    let head=String::from_utf8(git(&["rev-parse","HEAD"])).unwrap().trim().to_owned();
    let scopes=["server","tools","client_patch","web/src","tests","web/tests"];
    let mut status=vec!["status","--porcelain","--untracked-files=all","--"];status.extend(scopes);assert!(git(&status).is_empty());
    let mut args=vec!["ls-files","-z","--"];args.extend(scopes);let names=git(&args);
    let mut files=BTreeMap::new();for raw in names.split(|b|*b==0).filter(|s|!s.is_empty()){
        let name=std::str::from_utf8(raw).unwrap().to_owned();let path=root.join(&name).canonicalize().unwrap();assert!(path.starts_with(&root));
        files.insert(name,format!("{:x}",Sha256::digest(fs::read(path).unwrap())));
    }
    let base=root.join("local/test-runs/p08b-owner-hold-composition17");fs::create_dir_all(&base).unwrap();
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let output=base.join(format!("run-{}-{stamp}",std::process::id()));fs::create_dir(&output).unwrap();
    crate::gateway091::shared::composition_storage_tests::compress_fresh_output(&root,&output).unwrap();
    let guard=serde_json::json!({"schema":"p08b-owner-hold-four-parent-in-progress.v1","full_gate":"PENDING_PARENT_FULL_GATE",
        "head":head,"files":files,"parent_pid":std::process::id(),"target_dir":target,"build_output":output_root,"allocation":allocation,
        "compiled_test_source_sha256":compiled_test,"compiled_driver_sha256":compiled_helper,"compiled_common_driver_sha256":compiled_common,"compiled_sql_barriers_sha256":compiled_barriers,
        "test_executable":{"path":executable,"sha256":format!("{:x}",Sha256::digest(fs::read(&executable).unwrap()))},
        "test_name":"gateway091::shared::server::owner_hold_four_composition_tests::p08b_owner_hold17_actual_four_http_sqlite"});
    let control=output.join("parent-control.json");fs::write(&control,serde_json::to_vec_pretty(&guard).unwrap()).unwrap();
    let bundle=std::env::var_os("P04D_TEST_BUNDLE").map(PathBuf::from).unwrap_or_else(||root.join("local/stands/p09e-main-01/source-bundle-05"));
    let original=std::env::var_os("P04D_TEST_ORIGINAL").map(PathBuf::from).unwrap_or_else(||PathBuf::from("C:/WoT_0.9.1_RU_0717_original"));
    assert!(bundle.is_dir()&&original.is_dir(),"actual source prerequisites missing; no skip");
    let stdout=fs::File::create(output.join("controller.stdout.log")).unwrap();let stderr=fs::File::create(output.join("controller.stderr.log")).unwrap();
    let mut child=Command::new("node");child.arg(root.join(helper)).arg("--parent-full").arg(&control).arg(&output).arg(bundle).arg(original).arg(root.join("local/night-staging/20261016/p10b-selection-http01/seed01/seed.json"))
        .current_dir(&root).env_remove("PYTHONPATH").stdin(Stdio::null()).stdout(Stdio::from(stdout)).stderr(Stdio::from(stderr));
    #[cfg(windows)]{use std::os::windows::process::CommandExt;child.creation_flags(0x08000000);}
    let mut child=child.spawn().unwrap();let deadline=Instant::now()+Duration::from_secs(360);let status=loop{if let Some(status)=child.try_wait().unwrap(){break status;}if Instant::now()>=deadline{let _=child.kill();let _=child.wait();panic!("own controller timeout; retained evidence");}std::thread::sleep(Duration::from_millis(20));};assert!(status.success(),"composition controller failed; retained {}",output.display());
    let result:serde_json::Value=serde_json::from_slice(&fs::read(output.join("result.json"))
        .expect("controller exited successfully but actual composition result is absent")).unwrap();
    assert_eq!(result["status"],"PASS_ACTUAL_HOLD5_FOUR_RUNTIME_HTTP_SQLITE");
    assert_eq!(result["parent_full_gate"],"PENDING_PARENT_FULL_GATE");assert_eq!(result["native_client"],"NOT_RUN");
    println!("P08B_HOLD5_COMPOSITION_ACTUAL_PASS evidence={} native=NOT_RUN full_gate=PENDING_PARENT_FULL_GATE",output.display());
}

#[test]
fn p08b_owner_hold17_actual_four_http_sqlite(){
    if std::env::var_os("P08B_HOLD_FOUR_COMPOSITION_CONTROL").is_none(){assert!(std::env::var_os("P08B_HOLD_FOUR_COMPOSITION_OUTPUT").is_none());parent();return;}
    let input=PathBuf::from(std::env::var_os("P08B_HOLD_FOUR_COMPOSITION_CONTROL").unwrap());
    let output=PathBuf::from(std::env::var_os("P08B_HOLD_FOUR_COMPOSITION_OUTPUT").unwrap());assert!(!output.exists());
    let raw=fs::read(input).unwrap();assert!(raw.len()<=65536);let value=crate::profile13_v2091::bounded_json(&raw,65536).unwrap();
    let keys=["schema","phase","config","users","barrier","arena_id"];assert_eq!(value.as_object().unwrap().len(),keys.len());assert!(keys.iter().all(|k|value.get(*k).is_some()));
    assert_eq!(value["schema"],"p08b-owner-hold-four-composition.v1");assert_eq!(value["phase"],"four_held_parked_damage_then_outcome");
    let result=phase(&value);fs::write(output,serde_json::to_vec_pretty(&result).unwrap()).unwrap();
}
