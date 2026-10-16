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
        actor.devices=Some(State::new(Profile::Ms1));
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
    let mut state=State::new(Profile::Ms1);let mut events=Vec::new();
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
