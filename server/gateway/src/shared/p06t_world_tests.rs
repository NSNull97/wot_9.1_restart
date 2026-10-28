//! Actual source geometry and production World/Trace commands. The first
//! fixture uses an actual isolated SQLite V2 reply, never an authored receipt.
//! Other actors are explicitly cfg(test) temporary LAB actors, not owned grants.
use super::*;
use crate::{p06t_shells091::{self as source,Mount},p06t_device_caps::Profile,
    p06t_device_state::{self as device,State as Devices},p06t_armament091 as arm,
    profile13_v2091 as v2};
use sha2::{Digest,Sha256};

fn actual_frozen_ap_zero()->(Identity,v2::Frozen) {
    let bytes=include_bytes!("../../../../tests/fixtures/p06t-writer-vectors.json");
    assert_eq!(format!("{:x}",Sha256::digest(bytes)),"0e293febb5e3053e34f5b543c19aa2f7420918415b22595aaa4bb16e532b2c21");
    let vectors:serde_json::Value=serde_json::from_slice(bytes).unwrap();
    let row=vectors["vectors"].as_array().unwrap().iter().find(|row|
        row["operation"]=="battle"&&row["request"]["operation"]=="admit"
        &&row["response"]["reservation"]["frozen"]["ammunition"][0]["count"]==0).unwrap();
    let req=&row["request"];
    let context=crate::battle091::profile13::Context{account_id:req["account_id"].as_str().unwrap().into(),
        native_database_id:req["native_database_id"].as_i64().unwrap()as i32,command_key:req["command_key"].as_str().unwrap().into(),
        expected_revision:req["expected_revision"].as_u64().unwrap(),run_id:req["run_id"].as_str().unwrap().into()};
    let battle=req["battle_id"].as_str().unwrap().rsplit(':').next().unwrap().parse().unwrap();
    let request=v2::Request::Admit{battle,native_inventory_id:req["native_inventory_id"].as_u64().unwrap()as u32};
    let parsed=v2::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&context,&request).unwrap();
    let frozen=parsed.reservation.unwrap().frozen;assert_eq!(frozen.counts(),[0,4,11]);
    frozen.validate_owned(&context.account_id).unwrap();
    (Identity{account:context.account_id,database:context.native_database_id,name:"real_sqlite_owner".into()},frozen)
}
fn geometry(kind:VehicleKind)->Arc<geometry::Bundle> {
    match kind {
        VehicleKind::Ms1=>Arc::new(super::super::geometry::tests::bundle()),
        VehicleKind::Is7=>Arc::new(super::super::geometry::tests::is7_bundle()),
        _=>{let root=std::path::PathBuf::from(std::env::var_os("WOT091_ROOT").unwrap_or_else(||"D:/WoT_9.1_Server".into()));
            Arc::new(geometry::Bundle::load(&root.join("local"),&root.join(format!("local/evidence/20261016-p04m-source-import01/{}-stock.json",kind.label()))).unwrap())},
    }
}
fn base(now:Instant,terrain:Arc<terrain::Terrain>)->World {
    let mut world=World::new_for_roster(6963,now,crate::map_profile091::MapId::Karelia,2).unwrap();
    for kind in VehicleKind::ALL {world.bind_geometry(geometry(kind)).unwrap();}
    world.enable_ap_test_lab().unwrap();world.bind_terrain(terrain).unwrap();world.enable_mixed_ammo().unwrap();world
}
fn low_ground()->Arc<terrain::Terrain> {Arc::new(super::super::terrain::tests::fixture(-1000.,2000.,2,vec![-100.;4]))}
fn lab_attach(world:&mut World,kind:VehicleKind,slot:usize,counts:[u16;3]) {
    // Explicit cfg(test) conversion only. This is not an owned Frozen or a new
    // production admission route; no Python/SQLite reservation is fabricated.
    world.mixed_ammo=false;
    let attached=tests::attach_physics_profile(world,kind,Identity{account:format!("p06t-authored-lab-{slot}"),
        database:100+slot as i32,name:format!("temporary{slot}")},slot as u32+1).unwrap();
    world.mixed_ammo=true;assert_eq!(attached,slot);
    let initial=source::profile(kind.mount()).shots[counts.iter().position(|n|*n>0).unwrap()].compact_descr;
    world.actors[slot].fire=fire::State::with_typed(kind.mount(),counts,initial).unwrap();
    world.actors[slot].devices=Some(Devices::new(Profile::ALL[kind.index()]).unwrap());
}
fn start(world:&mut World,now:Instant) {
    for slot in 0..2 {
        let p=if slot==0{[0.;3]}else{[0.,0.,20.]};
        world.actors[slot].position=p;world.actors[slot].origin=p;world.actors[slot].direction=[0.;3];world.actors[slot].yaw=0.;
    }
    world.start(now).unwrap();for slot in 0..2 {world.set_ready(slot,slot as u32+1).unwrap();}
}
fn actual_owner_world(now:Instant)->World {
    let mut world=base(now,low_ground());let (owner,frozen)=actual_frozen_ap_zero();
    world.attach_owned_v2(owner,1,&frozen).unwrap();lab_attach(&mut world,VehicleKind::Ms1,1,[5,5,5]);start(&mut world,now);world
}
fn aim_at(world:&mut World,slot:usize,point:[f32;3],base:Instant) {
    world.apply(slot,slot as u32+1,&[Command::Aim(aim::Intent::Point(point))],base).unwrap();
    for step in 1..=20 {world.advance(base+Duration::from_millis(step*100)).unwrap();}
}
fn current(world:&World,slot:usize)->source::Shell {world.actors[slot].fire.typed().unwrap().current()}

#[test]
fn p06t_world_real_sqlite_ap_zero_admission_switch_preserves_airborne_shell_and_conserves_three_stacks() {
    let now=Instant::now();let mut w=actual_owner_world(now);w.actors[1].position=[300.,0.,300.];w.actors[1].origin=w.actors[1].position;
    let frozen=w.actors[0].owned_v2.clone().unwrap();assert_eq!(frozen.counts(),[0,4,11]);
    let heat=current(&w,0);assert_eq!(heat.family,source::Family::HollowCharge);
    let result=w.apply(0,1,&[Command::Armament(arm::Command::Shoot)],now).unwrap();
    assert!(matches!(result.as_slice(),[fire::Outcome::Typed(arm::Outcome::Shot{shell,..})]if *shell==heat));
    let projectile=w.projectiles[0];assert_eq!(projectile.shell,Some(heat));
    assert_eq!(w.actors[0].fire.typed().unwrap().counts(),[0,3,11]);
    let he=source::profile(Mount::Ms1Stock).shots[2];
    w.apply(0,1,&[Command::Armament(arm::Command::Select(arm::Selection::Current,he.compact_descr))],now+Duration::from_millis(1)).unwrap();
    assert_eq!(current(&w,0),he);assert_eq!(w.projectiles[0],projectile);
    w.advance(now+STEP).unwrap();assert_eq!(w.projectiles[0].shell,Some(heat));assert!(!w.projectiles[0].stopped);
    assert!(w.impact.events().iter().any(|e|matches!(e,impact::Event::Selected{shell,..}if *shell==heat)));
    let counts=w.actors[0].fire.typed().unwrap().counts();
    w.apply(0,1,&[Command::Armament(arm::Command::Replenish)],now+STEP).unwrap();assert_eq!(w.actors[0].fire.typed().unwrap().counts(),counts);
    let actors=w.actors.clone();let shots=w.shots.clone();let events=w.impact.events().to_vec();
    assert!(w.apply(0,1,&[Command::Armament(arm::Command::Select(arm::Selection::Next,heat.compact_descr)),
        Command::Move(Input{throttle:2,steer:0,speed_percent:100})],now+STEP).is_err());
    assert_eq!(w.actors,actors);assert_eq!(w.shots,shots);assert_eq!(w.impact.events(),events);
    let terminal=w.terminal_state_json(0).unwrap();v2::validate_terminal_json(&terminal,&frozen,w.actors[0].health).unwrap();
}

#[test]
fn p06t_world_actual_nearest_source_contact_reaches_trace_lab_module_and_single_hp_ledger() {
    let now=Instant::now();let mut w=actual_owner_world(now);
    w.actors[1].direction=[-std::f32::consts::PI,0.,0.];w.actors[1].yaw=-std::f32::consts::PI;
    let target=w.actors[1].clone();let b=w.geometry_for(target.vehicle_kind()).unwrap().clone();
    let query=b.explosion_contact(&target,[0.,1.,15.],16.,1,1,1000).unwrap().unwrap();
    aim_at(&mut w,0,query.endpoint,now);let fire_at=now+Duration::from_secs(2);
    w.apply(0,1,&[Command::Armament(arm::Command::Shoot)],fire_at).unwrap();w.advance(fire_at+STEP).unwrap();
    assert_eq!(w.contacts.len(),1);let contact=&w.contacts[0];assert_eq!(contact.target_slot,1);
    assert!(b.proxy_ray(contact).is_ok());
    let mesh=b.world_mesh(&w.actors[1],1,contact.tick).unwrap();
    assert_eq!(super::super::collision::query(&mesh,contact.segment_start,contact.segment_end).unwrap()[0],contact.triangle);
    assert!(w.impact.events().iter().any(|e|matches!(e,impact::Event::MaterialContact{..})));
    assert!(w.impact.events().iter().any(|e|matches!(e,impact::Event::MixedResolution{..})));
    assert_eq!(w.damage_events.len(),1);let d=&w.damage_events[0];assert_eq!((d.target,d.attacker,d.shot,d.health_before,d.health_after),(1,0,1,90,60));
    assert!(w.device_events.iter().any(|(slot,e)|*slot==1&&matches!(e.change,device::Change::Device{before,after,..}if before>after)));
    assert!(!w.rng_draws.is_empty());assert_eq!(w.actors[1].health,60);
}

#[test]
fn p06t_world_selected_t3485_ap_and_apcr_have_different_source_damage_on_actual_is7_geometry() {
    let now=Instant::now();let mut base=base(now,low_ground());
    lab_attach(&mut base,VehicleKind::T3485,0,[2,2,2]);lab_attach(&mut base,VehicleKind::Is7,1,[2,2,2]);start(&mut base,now);
    let b=base.geometry_for(VehicleKind::Is7).unwrap().clone();let target=base.actors[1].clone();
    let point=b.explosion_contact(&target,[0.,1.,15.],16.,1,1,1000).unwrap().unwrap().endpoint;
    aim_at(&mut base,0,point,now);let mut damages=Vec::new();
    for index in [0,1] {
        let mut w=base.clone();let selected=source::profile(Mount::T3485Stock).shots[index];
        if index==1 {w.apply(0,1,&[Command::Armament(arm::Command::Select(arm::Selection::Current,selected.compact_descr))],now+Duration::from_secs(2)).unwrap();}
        let at=now+Duration::from_secs(10);w.advance(at).unwrap();
        w.apply(0,1,&[Command::Armament(arm::Command::Shoot)],at).unwrap();w.advance(at+STEP).unwrap();
        assert_eq!(w.projectiles[0].shell,Some(selected));assert_eq!(w.contacts.len(),1);
        let impact=w.impacts.last().unwrap();let ImpactOutcome::Mixed(resolution)=&impact.outcome else {panic!("expected selected resolution")};
        assert_eq!(resolution.nominal_power_mm,selected.penetration_mm[0]);
        damages.push(impact.health_before-impact.health_after);
    }
    assert_ne!(damages[0],damages[1],"actual source plate must distinguish selected AP115/APCR110 or their penetration");
}

fn he_ground_world(now:Instant,wall:bool)->World {
    // Controlled ground/static triangles isolate real source vehicle surfaces
    // and LOS behavior. This is not acceptance of a native/original map scene.
    let mut ground=super::super::terrain::tests::fixture(-1000.,2000.,2,vec![0.;4]);
    if wall {ground=ground.with_obstacles(Arc::new(super::super::obstacles::tests::fixture(vec![
        [[0.12,0.,28.],[0.12,2.,28.],[0.12,0.,32.]],[[0.12,2.,28.],[0.12,2.,32.],[0.12,0.,32.]],
    ]))).unwrap();}
    let mut w=base(now,Arc::new(ground));lab_attach(&mut w,VehicleKind::Is7,0,[0,0,3]);lab_attach(&mut w,VehicleKind::Ms1,1,[2,2,2]);start(&mut w,now);
    w.actors[0].position=[0.5,0.,0.];w.actors[0].origin=w.actors[0].position;
    w.actors[1].position=[0.,0.,30.];w.actors[1].origin=w.actors[1].position;
    aim_at(&mut w,0,[0.15,0.,30.],now);w
}
#[test]
fn p06t_world_ground_he_splash_uses_actual_surface_and_triangle_los_not_authored_boolean() {
    let now=Instant::now();let mut damage=Vec::new();
    for wall in [false,true] {
        let mut w=he_ground_world(now,wall);let at=now+Duration::from_secs(2);
        w.apply(0,1,&[Command::Armament(arm::Command::Shoot)],at).unwrap();w.advance(at+STEP).unwrap();
        assert_eq!(w.terrain_contacts.len(),1);assert!(w.projectiles[0].stopped);assert!(w.contacts.is_empty());
        assert!(w.impact.events().iter().any(|e|matches!(e,impact::Event::SplashResolution{..})));
        damage.push(90-w.actors[1].health);
        assert_eq!(w.actors[0].fire.typed().unwrap().counts(),[0,0,2]);
    }
    assert_eq!(damage,[90,0],"intervening actual triangle must block splash HP on the same source vehicle");
}

#[test]
fn p06t_world_late_collision_failure_rolls_back_selected_trace_devices_rng_and_hp_together() {
    let now=Instant::now();let mut w=actual_owner_world(now);
    // Invalidate the later target catalogue after successful admission/launch.
    // The failure must restore the complete mixed World transaction, including
    // any earlier fire/device journal work in this advance.
    w.apply(0,1,&[Command::Armament(arm::Command::Shoot)],now).unwrap();
    w.geometries[VehicleKind::Ms1.index()]=Some(Arc::new(super::super::geometry::tests::invalid_material_bundle()));
    w.geometry=w.geometries[VehicleKind::Ms1.index()].clone();
    let before=w.clone();assert!(w.advance(now+STEP).is_err());
    assert_eq!(w.actors,before.actors);assert_eq!(w.projectiles,before.projectiles);assert_eq!(w.contacts,before.contacts);
    assert_eq!(w.damage_events,before.damage_events);assert_eq!(w.device_events,before.device_events);
    assert_eq!(w.rng_draws,before.rng_draws);assert_eq!(w.rng_state,before.rng_state);assert_eq!(w.impact.events(),before.impact.events());
    assert_eq!(w.tick,before.tick);assert_eq!(w.last,before.last);
}

#[test]
fn p06t_world_positive_hp_inactive_crew_retains_actual_wreck_geometry_without_new_damage_or_death() {
    let now=Instant::now();let mut w=actual_owner_world(now);
    // Authored cfg(test) prior crew casualty state. The acceptance assertion is
    // the subsequent real World projectile/nearest-source/Trace wreck path.
    let shell=source::profile(Mount::Ms1Stock).shots[0];
    let state=w.actors[1].devices.as_mut().unwrap();
    for seat in 0..2 {state.apply_hits(&[device::ModuleHit{cause:device::Cause{shot:seat as u32+1,attacker_slot:0},
        ordinal:0,at_ms:0,target:crate::p06t_lab_proxy::Target::Seat(seat),shell,ignition_roll:0.9}],
        device::Health{hp:90,max_hp:90,terminal:false}).unwrap();}
    w.actors[1].aim.park();assert!(!w.actors[1].alive());assert_eq!(w.actors[1].health,90);
    let b=w.geometry_for(VehicleKind::Ms1).unwrap().clone();
    let point=b.explosion_contact(&w.actors[1],[0.,1.,15.],16.,1,1,1000).unwrap().unwrap().endpoint;
    aim_at(&mut w,0,point,now);let at=now+Duration::from_secs(2);let before=w.actors[1].clone();
    w.apply(0,1,&[Command::Armament(arm::Command::Shoot)],at).unwrap();w.advance(at+STEP).unwrap();
    assert_eq!(w.contacts.len(),1);assert!(w.projectiles[0].stopped);
    let after=&w.actors[1];assert_eq!((after.health,after.position,after.direction,after.input,after.speed),
        (before.health,before.position,before.direction,before.input,before.speed));assert_eq!(after.aim,before.aim);
    assert_eq!(after.fire.typed().unwrap().counts(),before.fire.typed().unwrap().counts());
    let prior=before.devices.as_ref().unwrap();let current=after.devices.as_ref().unwrap();
    assert_eq!((current.health(),current.crew(),current.sequence(),current.fire_ticks(),current.fire_active()),
        (prior.health(),prior.crew(),prior.sequence(),prior.fire_ticks(),prior.fire_active()));
    assert_eq!(w.impacts.len(),1);assert_eq!(w.impacts[0].outcome,ImpactOutcome::WreckBlocked);
    assert_eq!((w.impacts[0].health_before,w.impacts[0].health_after),(90,90));
    assert!(w.damage_events.is_empty());assert!(w.rng_draws.is_empty());
    assert_eq!(w.impact.events().iter().filter(|e|matches!(e,impact::Event::WreckImpact{..})).count(),1);
    let trace=w.impact.clone();w.advance(at+STEP*2).unwrap();assert_eq!(w.impact,trace);
    let ammo=w.actors[1].fire.clone();let aim=w.actors[1].aim.clone();
    let rejected=w.apply(1,2,&[Command::Move(Input{throttle:1,steer:1,speed_percent:100}),
        Command::Aim(aim::Intent::Point([200.,10.,200.])),Command::Armament(arm::Command::Shoot)],at+STEP*2).unwrap();
    assert_eq!(rejected,[fire::Outcome::RejectedVehicleState]);assert_eq!(w.actors[1].fire,ammo);assert_eq!(w.actors[1].aim,aim);
}

#[test]
fn p06t_world_source_gun_contact_damages_only_gun_under_explicit_lab_admission() {
    let now=Instant::now();let mut initial=actual_owner_world(now);
    initial.actors[1].direction=[-std::f32::consts::PI,0.,0.];initial.actors[1].yaw=-std::f32::consts::PI;
    let b=initial.geometry_for(VehicleKind::Ms1).unwrap().clone();let at=now+Duration::from_secs(2);
    // Bounded aim-intent search previews the ACTUAL admitted World projectile's
    // first 100ms chord from its actual muzzle origin. A ray with another origin
    // can hit the barrel while the real shot instead reaches the turret.
    let mut selected=None;
    'search:for x in [0.1,0.2,0.3,0.4] {for y in [1.5,1.55,1.6,1.65,1.7] {for z in [18.,19.,20.] {
        let mut candidate=initial.clone();aim_at(&mut candidate,0,[x,y,z],now);
        assert!(candidate.actors[0].aim.yaw.is_finite()&&candidate.actors[0].aim.pitch.is_finite());
        candidate.apply(0,1,&[Command::Armament(arm::Command::Shoot)],at).unwrap();
        let projectile=candidate.projectiles[0];let mesh=b.world_mesh(&candidate.actors[1],1,1021).unwrap();
        if let Some(hit)=super::super::collision::query(&mesh,projectile.origin,projectile.position_at(at+STEP)).unwrap().first(){
            let facts=b.materials().lookup(&hit.mesh,&hit.material).unwrap();
            if facts.name=="gun"&&facts.kind==25 {selected=Some(candidate);break 'search;}
        }
    }}}
    let mut w=selected.expect("a finite actual World launch ray must reach the source MS1 barrel first");w.advance(at+STEP).unwrap();
    assert_eq!(w.contacts.len(),1);assert_eq!(w.contacts[0].material_facts.name,"gun");assert_eq!(w.contacts[0].material_facts.kind,25);
    assert_eq!(w.actors[1].health,90);assert!(w.damage_events.is_empty());
    let ImpactOutcome::Mixed(resolution)=&w.impacts[0].outcome else{panic!("selected gun contact")};
    assert_eq!(resolution.decision,crate::p06t_damage::Decision::Unsupported);assert_eq!(resolution.damage_hp,0);
    let state=w.actors[1].devices.as_ref().unwrap();assert_eq!(state.health()[6],4);assert_eq!(state.capabilities().dispersion_scale,2.);
    assert!(w.device_events.iter().any(|(slot,e)|*slot==1&&matches!(e.change,device::Change::Device{device:crate::p06t_device_caps::Device::Gun,before:54,after:4,..})));
}

#[test]
fn p06t_world_fire_uses_one_hp_ledger_and_first_cause_then_outcome_freezes_every_journal() {
    let now=Instant::now();let mut w=base(now,low_ground());
    w.enable_lifecycle(super::super::lifecycle::Rules{prebattle_ms:1000,battle_ms:60000,
        ..super::super::lifecycle::Rules::prohorovka()}).unwrap();
    let (owner,frozen)=actual_frozen_ap_zero();w.attach_owned_v2(owner,1,&frozen).unwrap();
    lab_attach(&mut w,VehicleKind::Ms1,1,[2,2,2]);start(&mut w,now);w.actors[1].position=[300.,0.,300.];w.actors[1].origin=w.actors[1].position;
    w.advance_lifecycle(now).unwrap();w.advance(now+Duration::from_secs(1)).unwrap();w.advance_lifecycle(now+Duration::from_secs(1)).unwrap();
    assert!(w.lifecycle.as_ref().unwrap().allows_actions());let at=now+Duration::from_secs(1);
    w.apply(0,1,&[Command::Armament(arm::Command::Shoot)],at).unwrap();let shell=w.projectiles[0].shell.unwrap();
    // Explicit prior LAB engine hit using the actual accepted shot identity.
    // The test below exercises production World fire timing/HP/death/terminal
    // freeze, independently of the actual-nearest hit test above.
    w.actors[1].health=7;
    let changes=w.actors[1].devices.as_mut().unwrap().apply_hits(&[device::ModuleHit{
        cause:device::Cause{shot:1,attacker_slot:0},ordinal:0,at_ms:1000,
        target:crate::p06t_lab_proxy::Target::Device(crate::p06t_device_caps::Device::Engine),shell,ignition_roll:0.}],
        device::Health{hp:7,max_hp:90,terminal:false}).unwrap();
    w.device_events.extend(changes.into_iter().map(|e|(1,e)));assert_eq!(w.actors[1].public_modifiers(),[4]);
    w.advance(now+Duration::from_secs(2)).unwrap();w.advance_lifecycle(now+Duration::from_secs(2)).unwrap();assert_eq!(w.actors[1].health,2);
    w.advance(now+Duration::from_secs(3)).unwrap();w.advance_lifecycle(now+Duration::from_secs(3)).unwrap();
    assert_eq!(w.actors[1].health,0);assert_eq!(w.actors[1].input,Input::STOP);
    assert_eq!(w.damage_events.iter().map(|e|(e.health_before,e.health_after,e.attacker,e.shot,e.reason)).collect::<Vec<_>>(),[(7,2,0,1,1),(2,0,0,1,1)]);
    assert_eq!(w.damage_events.iter().filter(|e|e.lethal()).count(),1);
    assert_eq!(w.lifecycle.as_ref().unwrap().outcome().unwrap().reason,super::super::lifecycle::Reason::Elimination);
    assert!(w.actors.iter().all(|a|a.devices.as_ref().unwrap().frozen()));
    let before=w.clone();assert!(!w.advance(now+Duration::from_secs(20)).unwrap());
    assert_eq!(w.actors,before.actors);assert_eq!(w.damage_events,before.damage_events);assert_eq!(w.device_events,before.device_events);
    assert_eq!(w.impact,before.impact);assert_eq!(w.rng_draws,before.rng_draws);assert_eq!(w.projectiles,before.projectiles);
    let terminal=w.terminal_state_json(0).unwrap();v2::validate_terminal_json(&terminal,&frozen,w.actors[0].health).unwrap();
}

#[test]
fn p06t_world_source_view_range_reacts_to_optics_and_combined_commander_capabilities() {
    let now=Instant::now();let mut initial=base(now,low_ground());
    // Source MS1 range240m, actual clear terrain query and opposite teams.
    // Prior module/crew hits are explicit LAB setup, not an authored LOS bool.
    initial.enable_lifecycle(super::super::lifecycle::Rules::prohorovka()).unwrap();
    lab_attach(&mut initial,VehicleKind::Ms1,0,[2,2,2]);lab_attach(&mut initial,VehicleKind::Ms1,1,[2,2,2]);start(&mut initial,now);
    initial.actors[1].position=[0.,0.,200.];initial.actors[1].origin=initial.actors[1].position;
    assert_eq!(initial.team(0).unwrap(),1);assert_eq!(initial.team(1).unwrap(),2);
    assert!(initial.desired_visibility(0).unwrap()[1]);assert_eq!(VehicleKind::Ms1.view_range(),240.);
    let shell=source::profile(Mount::Ms1Stock).shots[0];
    for (target,expected_range) in [(crate::p06t_lab_proxy::Target::Device(crate::p06t_device_caps::Device::SurveyingDevice),120.),
        (crate::p06t_lab_proxy::Target::Seat(0),180.)] {
        let mut w=initial.clone();w.actors[0].devices.as_mut().unwrap().apply_hits(&[device::ModuleHit{
            cause:device::Cause{shot:1,attacker_slot:1},ordinal:0,at_ms:0,target,shell,ignition_roll:0.9}],
            device::Health{hp:90,max_hp:90,terminal:false}).unwrap();
        assert!(w.actors[0].alive());assert_eq!(w.actors[0].health,90);
        let caps=w.actors[0].devices.as_ref().unwrap().capabilities();assert_eq!(240.*caps.view_scale,expected_range);
        assert!(!w.desired_visibility(0).unwrap()[1],"source range times actual capabilities must drive recipient interest");
        assert!(w.desired_visibility(1).unwrap()[0],"the healthy observer retains its own source range");
    }
}

#[test]
fn p06t_world_he_hits_retained_wreck_then_splashes_actual_nearby_live_source_geometry() {
    // Both HP0 and genuine HP90/inactive-crew bodies retain the original mesh.
    // The shot and explosion are actual World queries; prior casualties are
    // explicit LAB setup and do not manufacture a contact or a LOS result.
    for wreck_hp in [0,90] {
        let now=Instant::now();let mut w=World::new_for_roster(6973,now,crate::map_profile091::MapId::Karelia,3).unwrap();
        for kind in VehicleKind::ALL {w.bind_geometry(geometry(kind)).unwrap();}
        w.enable_ap_test_lab().unwrap();w.bind_terrain(low_ground()).unwrap();w.enable_mixed_ammo().unwrap();
        lab_attach(&mut w,VehicleKind::Is7,0,[0,0,3]);lab_attach(&mut w,VehicleKind::Ms1,1,[2,2,2]);lab_attach(&mut w,VehicleKind::Ms1,2,[2,2,2]);
        for(slot,p)in [[0.,0.,0.],[0.,0.,20.],[1.75,0.,20.]].into_iter().enumerate(){
            w.actors[slot].position=p;w.actors[slot].origin=p;w.actors[slot].direction=[0.;3];w.actors[slot].yaw=0.;
        }
        w.actors[1].health=wreck_hp;
        if wreck_hp>0 {
            let shell=source::profile(Mount::Ms1Stock).shots[0];
            for seat in 0..2 {w.actors[1].devices.as_mut().unwrap().apply_hits(&[device::ModuleHit{
                cause:device::Cause{shot:seat as u32+1,attacker_slot:0},ordinal:0,at_ms:0,
                target:crate::p06t_lab_proxy::Target::Seat(seat),shell,ignition_roll:0.9}],
                device::Health{hp:90,max_hp:90,terminal:false}).unwrap();}
        }
        assert!(!w.actors[1].alive());w.actors[1].aim.park();
        w.start(now).unwrap();for slot in 0..3 {w.set_ready(slot,slot as u32+1).unwrap();}
        let bundle=w.geometry_for(VehicleKind::Ms1).unwrap().clone();
        let point=bundle.explosion_contact(&w.actors[1],[0.,1.,15.],16.,1,1,1000).unwrap().unwrap().endpoint;
        aim_at(&mut w,0,point,now);let at=now+Duration::from_secs(2);
        w.apply(0,1,&[Command::Armament(arm::Command::Shoot)],at).unwrap();
        assert_eq!(w.projectiles[0].shell.unwrap().family,source::Family::HighExplosive);
        w.advance(at+STEP).unwrap();
        assert_eq!(w.contacts.len(),1);assert_eq!(w.contacts[0].target_slot,1);assert!(bundle.proxy_ray(&w.contacts[0]).is_ok());
        assert_eq!(w.impacts.len(),1);assert_eq!(w.impacts[0].outcome,ImpactOutcome::WreckBlocked);
        assert_eq!((w.impacts[0].health_before,w.impacts[0].health_after),(wreck_hp,wreck_hp));
        assert_eq!(w.actors[1].health,wreck_hp);assert!(!w.actors[1].alive());assert!(w.actors[2].health<90);
        assert_eq!(w.damage_events.len(),1);let damage=&w.damage_events[0];
        assert_eq!((damage.target,damage.attacker,damage.shot,damage.reason,damage.direct),(2,0,1,0,false));
        assert_eq!(damage.health_before,90);assert_eq!(damage.health_after,w.actors[2].health);
        assert!(w.impact.events().iter().any(|e|matches!(e,impact::Event::SplashResolution{target:2,center,..}if *center==w.projectiles[0].terminal)));
        assert!(matches!(w.impact.events().last(),Some(impact::Event::Terminal{reason:impact::TerminalReason::TestLabWreckImpact,..})));
        let before=w.clone();w.advance(at+STEP*2).unwrap();
        assert_eq!(w.impact,before.impact);assert_eq!(w.damage_events,before.damage_events);assert_eq!(w.actors[2].health,before.actors[2].health);
    }
}

// Append inside model::p06t_world_tests. Authored cfg(test) LAB actors/poses and
// low flat terrain; actual pinned vehicle mesh, World shots, Trace and journals.
// No owned grant, SQL, worker-physics or original native/UI acceptance claim.
#[test]
fn p08c_actual_world_fired_journals_project_personal_details_and_native_pack() {
    let now=Instant::now();let mut w=base(now,low_ground());
    w.enable_lifecycle(super::super::lifecycle::Rules{prebattle_ms:1000,battle_ms:60000,
        ..super::super::lifecycle::Rules::prohorovka()}).unwrap();
    w.enable_result_spots().unwrap();
    lab_attach(&mut w,VehicleKind::Ms1,0,[0,6,0]);
    lab_attach(&mut w,VehicleKind::Ms1,1,[0,6,0]);start(&mut w,now);
    w.lifecycle_created_unix=Some(1792080000);
    w.actors[1].direction=[-std::f32::consts::PI,0.,0.];w.actors[1].yaw=-std::f32::consts::PI;
    let target_before=w.actors[1].clone();let bundle=w.geometry_for(VehicleKind::Ms1).unwrap().clone();
    // Same real first-surface endpoint as the pre-existing nearest-contact test.
    let point=bundle.explosion_contact(&target_before,[0.,1.,15.],16.,1,1,1000).unwrap().unwrap().endpoint;
    w.advance_lifecycle(now).unwrap();
    for tick in 1..=10 {let at=now+Duration::from_millis(tick*100);w.advance(at).unwrap();w.advance_lifecycle(at).unwrap();}
    assert!(w.lifecycle.as_ref().unwrap().allows_actions());
    w.apply(0,1,&[Command::Aim(aim::Intent::Point(point))],now+Duration::from_secs(1)).unwrap();
    for tick in 11..=30 {let at=now+Duration::from_millis(tick*100);w.advance(at).unwrap();w.advance_lifecycle(at).unwrap();}
    let selected=source::profile(Mount::Ms1Stock).shots[1];
    let mut tick=30u64;let mut fired=0usize;
    for _ in 0..6 {
        if !w.actors[1].alive(){break;}
        let at=now+Duration::from_millis(tick*100);
        let outcome=w.apply(0,1,&[Command::Armament(arm::Command::Shoot)],at).unwrap();
        assert!(matches!(outcome.as_slice(),[fire::Outcome::Typed(arm::Outcome::Shot{shell,..})]if *shell==selected));
        fired+=1;
        // Real 100ms simulation and lifecycle publication ticks. Three seconds
        // between requests exceeds this source reload; no ammo/cooldown edits.
        for _ in 0..30 {
            tick+=1;let at=now+Duration::from_millis(tick*100);
            w.advance(at).unwrap();w.advance_lifecycle(at).unwrap();
            if !w.actors[1].alive(){break;}
        }
    }
    assert!((1..=6).contains(&fired));assert!(!w.actors[1].alive());
    assert_eq!((w.actors[0].health,w.actors[1].health),(90,0));
    assert!(w.lifecycle.as_ref().unwrap().outcome().is_some());
    assert_eq!(w.shots.len(),fired);assert!(w.shots.iter().all(|s|s.slot==0));
    assert!(w.projectiles.iter().all(|p|p.shell==Some(selected)));
    assert!(!w.contacts.is_empty());assert!(w.contacts.iter().all(|c|c.target_slot==1));
    let first=&w.contacts[0];assert!(bundle.proxy_ray(first).is_ok());
    let mesh=bundle.world_mesh(&target_before,1,first.tick).unwrap();
    assert_eq!(super::super::collision::query(&mesh,first.segment_start,first.segment_end).unwrap()[0],first.triangle);
    assert!(w.impact.events().iter().any(|e|matches!(e,impact::Event::MaterialContact{..})));
    assert!(w.impact.events().iter().any(|e|matches!(e,impact::Event::MixedResolution{..})));
    assert!(w.damage_events.iter().all(|d|d.attacker==0&&d.target==1));
    assert_eq!(w.damage_events.iter().map(|d|i32::from(d.health_before-d.health_after)).sum::<i32>(),90);
    let lethal=w.damage_events.iter().find(|d|d.lethal()).expect("actual lethal journal entry");
    assert_eq!(w.damage_events.iter().filter(|d|d.lethal()).count(),1);
    // The exact shot count and death reason come from real journals: an actual
    // engine ignition is allowed to finish the target between accepted shots.
    let direct=u16::try_from(w.contacts.len()).unwrap();
    let pierced=u16::try_from(w.impacts.iter().filter(|i|i.attacker==0&&matches!(&i.outcome,
        ImpactOutcome::Mixed(r)if r.decision==crate::p06t_damage::Decision::Pierced)).count()).unwrap();
    let result=super::super::lifecycle_result::build(&w).unwrap();
    result.validate_p06t().unwrap();
    let own=result.participants.iter().find(|p|p.account_dbid==100).unwrap();
    let enemy=result.participants.iter().find(|p|p.account_dbid==101).unwrap();
    assert_eq!((own.shots,own.direct_hits,own.piercings),(fired as u16,direct,pierced));
    assert_eq!((own.damage_dealt,own.kills,own.damage_received),(90,1,0));
    assert_eq!((enemy.health,enemy.damage_received,enemy.killer_id,enemy.death_reason),(0,90,own.vehicle_id,lethal.reason as i8));
    let spots=w.result_spots().unwrap();
    assert_eq!(spots.iter().filter(|s|s.observer()==0&&s.target()==1).count(),1);
    let details=result.interaction_details.as_ref().unwrap();
    assert_eq!(details.spotting_policy.as_deref(),Some(result_spots::POLICY));
    let row=details.row(own.vehicle_id).unwrap();assert_eq!(row.targets.len(),1);let target=&row.targets[0];
    assert_eq!((target.vehicle_id,target.spotted,target.damage_dealt,target.death_reason),(enemy.vehicle_id,1,90,enemy.death_reason));
    assert_eq!((target.direct_hits,target.piercings,target.explosion_hits),(direct,pierced,0));
    let packed=details.packed(own.vehicle_id).unwrap();assert_eq!(packed.len(),24);
    // Independent #717 <I ID + BbHHHHHHIH scalar unpack, not a round trip of
    // the production serializer. No input pickle deserialization is involved.
    let u16_at=|offset|u16::from_le_bytes(packed[offset..offset+2].try_into().unwrap());
    assert_eq!(u32::from_le_bytes(packed[0..4].try_into().unwrap()),enemy.vehicle_id);
    assert_eq!((packed[4],packed[5] as i8),(1,lethal.reason as i8));
    assert_eq!((u16_at(6),u16_at(8),u16_at(10),u16_at(12)),(direct,0,pierced,90));
    assert_eq!((u16_at(14),u16_at(16),u16_at(22)),(0,0,0));
    // P06T now projects committed module transitions into the packed native
    // result.  Keep the wire assertion tied to the authoritative journal so
    // a future fixture change cannot silently erase the critical counter.
    let expected_crits=w.device_events.iter().filter(|(_,event)|match &event.change {
        device::Change::Device{before_condition,after_condition,..} =>
            before_condition!=after_condition&&!event.from_fire,
        device::Change::Crew{before_active:true,after_active:false,..} => true,
        _ => false,
    }).count() as u32;
    assert!(expected_crits>0);
    assert_eq!(u32::from_le_bytes(packed[18..22].try_into().unwrap()),expected_crits);

    // Tiny independent reader of this test's own bounded protocol2 output.
    // Deliberately no GLOBAL/REDUCE/INST/OBJ/memo/object construction or imports.
    #[derive(Debug,PartialEq)]enum V{Int(i64),Bool(bool),Bytes(Vec<u8>),List(Vec<V>),Tuple(Vec<V>),Dict(Vec<(V,V)>),Mark}
    fn inert(raw:&[u8])->V {
        assert!(raw.len()<32768);assert_eq!(&raw[..2],&[128,2]);let mut at=2;let mut stack=Vec::new();
        while at<raw.len(){let op=raw[at];at+=1;match op{
            b'K'=>{stack.push(V::Int(i64::from(raw[at])));at+=1;},
            b'J'=>{stack.push(V::Int(i64::from(i32::from_le_bytes(raw[at..at+4].try_into().unwrap()))));at+=4;},
            0x8a=>{assert_eq!(raw[at],8);at+=1;stack.push(V::Int(i64::from_le_bytes(raw[at..at+8].try_into().unwrap())));at+=8;},
            b'U'|b'T'=>{let n=if op==b'U'{let n=raw[at] as usize;at+=1;n}else{let n=u32::from_le_bytes(raw[at..at+4].try_into().unwrap())as usize;at+=4;n};
                stack.push(V::Bytes(raw[at..at+n].to_vec()));at+=n;},
            0x88|0x89=>stack.push(V::Bool(op==0x88)),b'('=>stack.push(V::Mark),
            b']'=>stack.push(V::List(Vec::new())),b'}'=>stack.push(V::Dict(Vec::new())),
            b'e'|b'u'|b't'=>{let mark=stack.iter().rposition(|x|matches!(x,V::Mark)).unwrap();let values=stack.split_off(mark+1);assert_eq!(stack.pop(),Some(V::Mark));
                if op==b'e'{let Some(V::List(v))=stack.last_mut()else{panic!("list")};v.extend(values);}
                else if op==b'u'{assert_eq!(values.len()%2,0);let Some(V::Dict(v))=stack.last_mut()else{panic!("dict")};let mut it=values.into_iter();while let Some(k)=it.next(){v.push((k,it.next().unwrap()));}}
                else{stack.push(V::Tuple(values));}},
            0x86|0x87=>{let count=if op==0x86{2}else{3};let values=stack.split_off(stack.len()-count);stack.push(V::Tuple(values));},
            b'.'=>{assert_eq!(at,raw.len());assert_eq!(stack.len(),1);return stack.pop().unwrap();},
            _=>panic!("unexpected primitive output opcode {op}"),
        }}panic!("missing STOP")
    }
    let compact=super::super::lifecycle_wire::compact_results_p06t(&result,100).unwrap();
    let V::Tuple(outer)=inert(&compact)else{panic!("compact tuple")};assert_eq!(outer.len(),3);
    let V::List(personal)=&outer[1]else{panic!("personal list")};assert_eq!(personal.len(),81);
    // Independent original field indices, not production field-name lookup.
    for(index,value)in [(6,fired as i64),(7,i64::from(direct)),(10,i64::from(pierced)),(11,90),(21,1),(23,1)]{
        assert_eq!(personal[index],V::Int(value));
    }
    assert_eq!(personal[43],V::Bytes(packed));
}

/// BATTLE-ANY stand -11 2026-10-28: a pilot (generated) owned reservation used to
/// fail the seating (legacy placeholder gun with zero initial ammunition) and the
/// v1 device route, which took the whole gateway down. Owned admission itself
/// (`validate_owned` under the process-wide catalog mode) is exercised on the
/// stand; here the two seating steps of `attach_owned_v2_inner` run directly.
#[test]
fn battle_any_generated_seats_with_typed_gun_and_v1_devices() {
    let root=std::path::PathBuf::from(std::env::var_os("WOT091_ROOT").unwrap_or_else(||"D:/WoT_9.1_Server".into()));
    let kind=VehicleKind::from_owned_label("ussr-KV-3").unwrap();assert!(kind.is_generated());
    let p=source::profile(kind.mount());
    let now=Instant::now();let mut world=base(now,low_ground());
    world.bind_geometry(Arc::new(geometry::Bundle::load(&root.join("local"),
        &root.join("local/evidence/20261028-battleany-pilot-sources02/bundles/ussr-KV-3.json")).unwrap())).unwrap();
    let owner=|n:i32|Identity{account:format!("battle-any-pilot-{n}"),database:n,name:"battle_any_pilot".into()};
    world.mixed_ammo=false;world.vehicle_kind=kind;
    // The former placeholder: zero initial ammunition is rejected by the legacy gun.
    assert!(world.clone().attach_loadout_fire(owner(7),1,None,None).is_err());
    let typed=fire::State::with_typed(kind.mount(),[10,5,5],p.shots[0].compact_descr).unwrap();
    let slot=world.attach_loadout_fire(owner(7),1,None,Some(typed)).unwrap();
    assert_eq!(world.actors[slot].fire.typed().unwrap().mount(),kind.mount());
    let profile=Profile::for_owned(kind).unwrap();
    let devices=Devices::new(profile).unwrap();
    assert_eq!((devices.policy_version(),devices.crew().len()),(device::PolicyVersion::V1,profile.crew().len()));
    // The curated extended profiles still need the explicit v2 policy.
    assert!(Devices::new(Profile::Wt128).is_err()&&Devices::new(Profile::Fv183).is_err());
}
