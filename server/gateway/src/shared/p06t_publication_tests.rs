//! Authored publication fixtures, actual Client/Book/Window and native codecs.
//! These are not geometry, writer admission, or original client execution tests.
use super::*;
use crate::gateway091::shared::interest_wire;
use crate::{p06t_device_caps::{Device,Profile},p06t_device_state::{State,Health,ModuleHit,Cause},
    p06t_lab_proxy::Target,transport091};

fn mask(slots:&[usize])->[bool;model::MAX_ACTORS] {
    std::array::from_fn(|slot|slots.contains(&slot))
}
fn fixture(now:Instant)->(Session,World) {
    // Publication-only actors are explicit LAB fixtures, not forged Frozen DTOs.
    let authored=model::tests::world(now);
    let mut world=World::new_for_roster(6963,now,crate::map_profile091::MapId::Karelia,2).unwrap();
    world.enable_mixed_ammo().unwrap();world.actors=authored.actors;
    for actor in &mut world.actors {
        actor.fire=crate::battle091::fire::State::with_typed(actor.vehicle_kind().mount(),[5,5,5],2570).unwrap();
        actor.devices=Some(State::new(Profile::Ms1).unwrap());
    }
    let mut s=Session::new(1,[1;16],"127.0.0.1:38302".parse().unwrap(),now);
    let mut c=Client::new(0);c.enable_spotting().unwrap();c.phase=Phase::Driving;
    c.interest.as_mut().unwrap().set_desired(mask(&[0,1]),mask(&[0,1])).unwrap();
    let enters=[wire::enter_vehicle(0).unwrap(),wire::enter_vehicle(1).unwrap()].concat();
    let enter=s.tx.enqueue_body_tracked(&enters).unwrap();assert_eq!(enter,0);
    c.mark_announced(&[0,1],enter).unwrap();
    let creates=[wire::create_vehicle(&world,0).unwrap(),wire::create_vehicle(&world,1).unwrap()].concat();
    let creation=s.tx.enqueue_body_tracked(&creates).unwrap();
    for slot in 0..2 {c.creations[slot]=Some((creation,false));c.creation_announcements[slot]=Some(enter);}
    while s.tx.due(now,s.rx).unwrap().is_some(){}
    let ack=transport091::parse(&transport091::ack(creation+1)).unwrap();
    s.tx.acknowledge(&ack).unwrap();c.acknowledge(s.tx.cumulative,&ack).unwrap();
    assert!(c.visible()[0]&&c.visible()[1]);
    // Establish the ordinary initial publication before testing a later delta.
    c.devices_snapshot_sent=true;c.owner_health_sent=Some(90);
    c.health_sent=[Some(90);model::MAX_ACTORS];c.crew_sent=[Some(true);model::MAX_ACTORS];
    c.fire_sent=[Some(false);model::MAX_ACTORS];
    publish(&mut c,&mut s.outbox,&world,now).unwrap();
    assert!(c.private_pending.is_empty());s.outbox.clear();s.shared=Some(c);(s,world)
}
fn fuel_damage(crew_dead:bool)->(State,Vec<crate::p06t_device_state::Transition>) {
    let mut state=State::new(Profile::Ms1).unwrap();let mut events=Vec::new();
    let shell=crate::p06t_shells091::profile(crate::p06t_shells091::Mount::Ms1Stock).shots[2];
    let health=Health{hp:90,max_hp:90,terminal:false};
    for shot in 1..=6 {
        events.extend(state.apply_hits(&[ModuleHit{cause:Cause{shot,attacker_slot:1},ordinal:0,at_ms:u64::from(shot),
            target:Target::Device(Device::FuelTank),shell,ignition_roll:0.9}],health).unwrap());
    }
    assert!(state.fire_active());
    if crew_dead {
        let cause=Cause{shot:7,attacker_slot:1};
        events.extend(state.apply_hits(&[
            ModuleHit{cause,ordinal:0,at_ms:7,target:Target::Seat(0),shell,ignition_roll:0.9},
            ModuleHit{cause,ordinal:1,at_ms:7,target:Target::Seat(1),shell,ignition_roll:0.9}],health).unwrap());
        assert!(!state.crew_active());
    }
    (state,events)
}
fn contains(body:&[u8],part:&[u8])->bool {body.windows(part.len()).any(|bytes|bytes==part)}
fn fresh_bodies(s:&Session,now:Instant)->Vec<u8> {
    let mut tx=s.tx.clone();let mut result=Vec::new();
    while let Some((_,_,raw))=tx.due(now,s.rx).unwrap(){result.extend(transport091::parse_interactive(&raw).unwrap().body);}
    result
}

#[test]
fn p06t_private_rapid_hide_reveal_without_leave_republishes_crew_and_fire() {
    let now=Instant::now();let(mut s,mut world)=fixture(now);
    let(state,_)=fuel_damage(true);world.actors[1].devices=Some(state);
    assert_eq!(world.actors[1].health,90);assert!(!world.actors[1].alive());
    let c=s.shared.as_mut().unwrap();publish(c,&mut s.outbox,&world,now).unwrap();
    assert_eq!(c.crew_sent[1],Some(false));assert_eq!(c.fire_sent[1],Some(true));
    let stale=c.private_pending.front().unwrap().body.clone();
    assert!(contains(&stale,&native::public_crew_active(wire::vehicle_id(1).unwrap(),false).unwrap()));
    assert!(contains(&stale,&native::public_modifiers(wire::vehicle_id(1).unwrap(),&[4]).unwrap()));
    c.interest.as_mut().unwrap().set_desired(mask(&[0,1]),mask(&[0])).unwrap();
    s.flush_shared_private().unwrap();
    let c=s.shared.as_mut().unwrap();
    assert_eq!(c.crew_sent[1],None);assert_eq!(c.fire_sent[1],None);
    assert_eq!(c.interest.as_ref().unwrap().entry(1),Some(interest_wire::Entry::Announced{enter_seq:0}));
    assert!(fresh_bodies(&s,now).is_empty());
    let c=s.shared.as_mut().unwrap();
    c.interest.as_mut().unwrap().set_desired(mask(&[0,1]),mask(&[0,1])).unwrap();
    publish(c,&mut s.outbox,&world,now).unwrap();s.flush_shared_private().unwrap();
    let sent=fresh_bodies(&s,now);
    assert!(contains(&sent,&native::public_crew_active(wire::vehicle_id(1).unwrap(),false).unwrap()));
    assert!(contains(&sent,&native::public_modifiers(wire::vehicle_id(1).unwrap(),&[4]).unwrap()));
    assert!(!contains(&sent,&wire::leave_vehicle(1).unwrap()));
}

#[test]
fn p06t_private_attacker_epoch_discards_health_and_critical_then_rebuilds_owner_state() {
    let now=Instant::now();let(mut s,mut world)=fixture(now);
    let(state,events)=fuel_damage(false);world.actors[0].devices=Some(state);
    world.device_events.extend(events.into_iter().map(|event|(0,event)));
    world.actors[0].health=60;
    world.damage_events.push(model::DamageRecord{sequence:1,tick:1000,attacker:1,target:0,shot:6,reason:0,
        health_before:90,health_after:60,crew_before:true,crew_after:true,direct:true,pierced:true});
    let c=s.shared.as_mut().unwrap();publish(c,&mut s.outbox,&world,now).unwrap();
    let critical=native::damage_info(wire::vehicle_id(0).unwrap(),5,28,wire::vehicle_id(1).unwrap()).unwrap();
    let health_body=health(&world,0,Some(1),0).unwrap();
    for expected in [&critical,&health_body] {
        let packet=c.private_pending.iter().find(|packet|contains(&packet.body,expected)).unwrap();
        assert!(packet.targets.contains(&(0,0)));assert!(packet.targets.contains(&(1,0)));
    }
    c.interest.as_mut().unwrap().set_desired(mask(&[0,1]),mask(&[0])).unwrap();
    s.flush_shared_private().unwrap();
    assert!(fresh_bodies(&s,now).is_empty());
    let c=s.shared.as_mut().unwrap();assert!(c.visible()[0]);
    assert_eq!(c.owner_health_sent,None);assert!(!c.devices_snapshot_sent);
    publish(c,&mut s.outbox,&world,now).unwrap();
    // Current owner state survives loss of the source entity's AoI epoch.
    assert!(c.private_pending.iter().all(|packet|packet.targets==vec![(0,0)]));
    s.flush_shared_private().unwrap();let sent=fresh_bodies(&s,now);
    assert!(contains(&sent,&native::damage_info(wire::vehicle_id(0).unwrap(),1,28,0).unwrap()));
    assert!(contains(&sent,&native::damage_info(wire::vehicle_id(0).unwrap(),3,4,0).unwrap()));
    assert!(contains(&sent,&native::owner_health(60,true,90).unwrap()));
    assert!(contains(&sent,&health(&world,0,None,0).unwrap()));
    assert!(!contains(&sent,&critical));assert!(!contains(&sent,&health_body));
}

#[test]
fn p06t_private_he_splash_never_reveals_a_hidden_primary_vehicle_anchor() {
    let now=Instant::now();let(mut s,mut world)=fixture(now);
    // Publication-only authored collision: the source shooter and this victim
    // are visible, but the primary retained wreck/vehicle is outside AoI.
    let mut hidden=world.actors[1].clone();hidden.identity.account="hidden-primary".into();
    hidden.identity.database=103;hidden.identity.name="hidden".into();hidden.health=0;
    world.actors.push(hidden);
    let shell=crate::p06t_shells091::profile(crate::p06t_shells091::Mount::Ms1Stock).shots[2];
    let mut projectile=crate::gateway091::shared::projectile::Projectile::launch_shell_for_limit(1,1,&world.actors[1],now,world.shot_limit(),shell).unwrap();
    projectile.stopped=true;projectile.terminal=[41.125,1.75,62.5];world.projectiles.push(projectile);
    world.impacts.push(model::AppliedImpact{shot:1,attacker:1,target:2,tick:1001,outcome:model::ImpactOutcome::WreckBlocked,
        health_before:0,health_after:0,segment:None});
    world.actors[0].health=80;world.damage_events.push(model::DamageRecord{sequence:1,tick:1001,attacker:1,target:0,shot:1,reason:0,
        health_before:90,health_after:80,crew_before:true,crew_after:true,direct:false,pierced:false});
    let forbidden=native::explosion(wire::vehicle_id(0).unwrap(),wire::vehicle_id(1).unwrap(),projectile.terminal,shell).unwrap();
    let c=s.shared.as_mut().unwrap();c.tracer_started[0]=true;
    assert!(c.visible()[0]&&c.visible()[1]&&!c.visible()[2]);
    publish(c,&mut s.outbox,&world,now).unwrap();
    assert_eq!(c.damage_cursor,1);
    assert!(c.private_pending.iter().all(|packet|!contains(&packet.body,&forbidden)));
    assert!(s.outbox.iter().all(|packet|!contains(packet,&forbidden)));
    assert!(c.private_pending.iter().any(|packet|contains(&packet.body,&native::owner_health(80,true,90).unwrap())),
        "private HP catch-up must survive suppression of the hidden explosion center");
}

#[test]
fn p06t_private_he_center_tracks_the_primary_vehicle_epoch_until_flush() {
    let now=Instant::now();let(mut s,mut world)=fixture(now);
    let mut primary=world.actors[1].clone();primary.identity.account="visible-primary".into();
    primary.identity.database=103;primary.identity.name="third".into();primary.devices=Some(fuel_damage(true).0);
    assert_eq!(primary.health,90);assert!(!primary.alive());world.actors.push(primary);
    let c=s.shared.as_mut().unwrap();
    c.interest.as_mut().unwrap().set_desired(mask(&[0,1,2]),mask(&[0,1,2])).unwrap();
    let enter=s.tx.enqueue_body_tracked(&wire::enter_vehicle(2).unwrap()).unwrap();c.mark_announced(&[2],enter).unwrap();
    let create=s.tx.enqueue_body_tracked(&wire::create_vehicle(&world,2).unwrap()).unwrap();
    c.creations[2]=Some((create,false));c.creation_announcements[2]=Some(enter);
    while s.tx.due(now,s.rx).unwrap().is_some(){}
    let ack=transport091::parse(&transport091::ack(create+1)).unwrap();s.tx.acknowledge(&ack).unwrap();c.acknowledge(s.tx.cumulative,&ack).unwrap();
    assert!(c.visible()[2]);c.health_sent[2]=Some(90);c.crew_sent[2]=Some(false);c.fire_sent[2]=Some(true);
    let shell=crate::p06t_shells091::profile(crate::p06t_shells091::Mount::Ms1Stock).shots[2];
    let mut projectile=crate::gateway091::shared::projectile::Projectile::launch_shell_for_limit(1,1,&world.actors[1],now,world.shot_limit(),shell).unwrap();
    projectile.stopped=true;projectile.terminal=[41.125,1.75,62.5];world.projectiles.push(projectile);
    // Authored publication-only direct result; no geometric/native acceptance.
    world.impacts.push(model::AppliedImpact{shot:1,attacker:1,target:2,tick:1001,outcome:model::ImpactOutcome::WreckBlocked,
        health_before:90,health_after:90,segment:None});
    world.actors[0].health=80;world.damage_events.push(model::DamageRecord{sequence:1,tick:1001,attacker:1,target:0,shot:1,reason:0,
        health_before:90,health_after:80,crew_before:true,crew_after:true,direct:false,pierced:false});
    c.tracer_started[0]=true;publish(c,&mut s.outbox,&world,now).unwrap();
    let explosion=native::explosion(wire::vehicle_id(0).unwrap(),wire::vehicle_id(1).unwrap(),projectile.terminal,shell).unwrap();
    let packet=c.private_pending.iter().find(|packet|contains(&packet.body,&explosion)).unwrap();
    assert_eq!(packet.targets,vec![(0,0),(1,0),(2,enter)]);
    c.interest.as_mut().unwrap().set_desired(mask(&[0,1,2]),mask(&[0,1])).unwrap();
    s.flush_shared_private().unwrap();assert!(!contains(&fresh_bodies(&s,now),&explosion));
    assert!(s.shared.as_ref().unwrap().private_pending.iter().all(|packet|!contains(&packet.body,&explosion)));
}

/// POSTMORTEM-01 (owner 2026-10-29, -11 battle ...827): arena_c was killed by
/// a vehicle outside arena_e's AoI. Only the health property was sent, and
/// #717 Vehicle.set_health never reaches __onVehicleDeath, so the ally kept a
/// live "0%" marker. The terminal now always calls onHealthChanged; a hidden
/// attacker is FROM_UNKNOWN (ID 0) and its entity epoch is not a target.
#[test]
fn postmortem01_visible_ally_killed_by_hidden_attacker_gets_native_death_callback() {
    let now=Instant::now();let(mut s,mut world)=fixture(now);
    let mut killer=world.actors[1].clone();killer.identity.account="hidden-killer".into();
    killer.identity.database=103;killer.identity.name="hidden".into();world.actors.push(killer);
    world.actors[1].health=0;
    world.damage_events.push(model::DamageRecord{sequence:1,tick:1001,attacker:2,target:1,shot:1,reason:0,
        health_before:90,health_after:0,crew_before:true,crew_after:false,direct:true,pierced:true});
    let c=s.shared.as_mut().unwrap();
    assert!(c.visible()[0]&&c.visible()[1]&&!c.visible()[2]);
    publish(c,&mut s.outbox,&world,now).unwrap();
    let mut callback=vec![0x3c];callback.extend(0i16.to_le_bytes());callback.extend(0u32.to_le_bytes());callback.push(0);
    let packet=c.private_pending.iter().find(|packet|contains(&packet.body,&callback)).unwrap();
    assert!(contains(&packet.body,&[0x12].into_iter().chain(wire::vehicle_id(1).unwrap().to_le_bytes()).collect::<Vec<_>>()));
    assert_eq!(packet.targets,vec![(1,0)]);
    assert!(!contains(&packet.body,&wire::vehicle_id(2).unwrap().to_le_bytes()));
    // isCrewActive=False must follow the callback, or #717 skips the death.
    let at=|part:&[u8]|packet.body.windows(part.len()).position(|bytes|bytes==part).unwrap();
    assert!(at(&callback)<at(&native::public_crew_active(wire::vehicle_id(1).unwrap(),false).unwrap()));
    assert_eq!(c.health_sent[1],Some(0));assert_eq!(c.crew_sent[1],Some(false));
    // A visible attacker keeps its own ID, as before.
    assert!(contains(&health(&world,1,Some(0),0).unwrap(),&[0x3c].into_iter().chain(0i16.to_le_bytes())
        .chain(wire::vehicle_id(0).unwrap().to_le_bytes()).collect::<Vec<_>>()));
}
