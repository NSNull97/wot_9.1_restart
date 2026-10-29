//! Actual committed tank-contact damage through recipient publication and the
//! reliable private epoch fence. Authored projectile rows below exercise only
//! mixed-cause publication; none of these tests claim native collision/UI.
use super::*;
use crate::gateway091::shared::turret_publication_test_fixture as f;

fn contains(body:&[u8],bytes:&[u8])->bool{body.windows(bytes.len()).any(|part|part==bytes)}
fn contact(world:&mut World,speed:f32,sequence:u32){
    world.apply_tank_contacts(&[model::TankContactInput{slot_a:0,slot_b:1,substep:1,
        point:[0.,1.,0.],normal:[1.,0.,0.],relative_velocity:[speed,0.,0.]}],sequence,180+sequence*6).unwrap();
}
fn shot_damage(world:&mut World,target:usize,after:i16){
    let before=world.actors[target].health;world.actors[target].health=after;
    {let next_sequence=world.damage_events.len() as u32+1;world.damage_events.push(model::DamageRecord{sequence:next_sequence,tick:1001,
        attacker:1-target,target,shot:1,reason:0,health_before:before,health_after:after,
        crew_before:true,crew_after:after>0,direct:true,pierced:true});}
}
fn assert_current_health(s:&Session,world:&World,target:usize,attacker:Option<usize>,reason:u8){
    let expected=health(world,target,attacker,reason).unwrap();
    assert!(s.shared.as_ref().unwrap().private_pending.iter().any(|packet|contains(&packet.body,&expected)),
        "current target {target} HP must retain its committed cause, reason {reason}");
}

#[test]
fn p05c_ram_publication_nonlethal_contact_reaches_both_owners_without_a_shot(){
    for own in 0..2{
        let now=Instant::now();let(mut s,mut world)=f::fixture_for(now,own);contact(&mut world,2.,1);
        assert!(world.actors.iter().all(|a|a.health>0&&a.health<90));
        assert_eq!(world.ram_damage_events.len(),2);
        assert!(world.damage_events.is_empty()&&world.shots.is_empty()&&world.projectiles.is_empty());
        publish(s.shared.as_mut().unwrap(),&mut s.outbox,&world,now).unwrap();
        for target in 0..2{assert_current_health(&s,&world,target,Some(1-target),2);}
        let hp=world.actors[own].health;
        assert!(s.shared.as_ref().unwrap().private_pending.iter().any(|p|contains(&p.body,&native::owner_health(hp,true,90).unwrap())));
    }
}

#[test]
fn p05c_ram_publication_lethal_contact_emits_health_and_each_roster_kill_once(){
    let now=Instant::now();let(mut s,mut world)=f::fixture_for(now,1);contact(&mut world,50.,1);
    assert!(world.actors.iter().all(|a|a.health==0));assert!(world.damage_events.is_empty());
    publish(s.shared.as_mut().unwrap(),&mut s.outbox,&world,now).unwrap();
    for target in 0..2{
        assert_current_health(&s,&world,target,Some(1-target),2);
        let kill=super::super::super::lifecycle_wire::vehicle_killed(wire::vehicle_id(target).unwrap(),wire::vehicle_id(1-target).unwrap(),2).unwrap();
        assert_eq!(s.outbox.iter().filter(|body|contains(body,&kill)).count(),1);
    }
    assert!(s.shared.as_ref().unwrap().private_pending.iter().any(|p|contains(&p.body,&native::owner_health(0,false,90).unwrap())));
    s.outbox.clear();publish(s.shared.as_mut().unwrap(),&mut s.outbox,&world,now).unwrap();
    assert!(s.outbox.is_empty(),"a second publication must not repeat ram roster kills");
}

#[test]
fn p05c_ram_publication_mixed_cause_uses_current_hp_not_incomparable_journal_sequences(){
    for shot_first in [false,true]{
        let now=Instant::now();let(mut s,mut world)=f::fixture_for(now,0);
        if shot_first{shot_damage(&mut world,0,80);}
        contact(&mut world,2.,1);
        if !shot_first{shot_damage(&mut world,0,65);}
        // The worker tick and the wall-clock domain tick use distinct cadence;
        // matching the monotonic HP transition establishes which cause is last.
        assert_eq!(world.damage_events[0].tick,1001);assert_eq!(world.ram_damage_events[0].tick,186);
        publish(s.shared.as_mut().unwrap(),&mut s.outbox,&world,now).unwrap();
        assert_current_health(&s,&world,0,Some(1),if shot_first{2}else{0});
        assert_current_health(&s,&world,1,Some(0),2);
        assert_eq!(world.damage_events.len(),1);assert!(world.shots.is_empty()&&world.projectiles.is_empty());
    }
}

#[test]
fn p05c_ram_publication_hidden_attacker_epoch_discards_then_rebuilds_owner_hp(){
    let now=Instant::now();let(mut s,mut world)=f::fixture_for(now,0);contact(&mut world,2.,1);
    publish(s.shared.as_mut().unwrap(),&mut s.outbox,&world,now).unwrap();
    let stale=health(&world,0,Some(1),2).unwrap();assert_current_health(&s,&world,0,Some(1),2);
    s.shared.as_mut().unwrap().interest.as_mut().unwrap().set_desired(f::mask(true),f::mask(false)).unwrap();
    s.drain_outbox().unwrap();s.flush_shared_private().unwrap();
    assert_eq!(s.shared.as_ref().unwrap().owner_health_sent,None);
    publish(s.shared.as_mut().unwrap(),&mut s.outbox,&world,now).unwrap();
    assert_current_health(&s,&world,0,None,2);
    let c=s.shared.as_ref().unwrap();assert!(c.private_pending.iter().all(|packet|packet.targets==vec![(0,0)]));
    assert!(c.private_pending.iter().all(|packet|!contains(&packet.body,&stale)));
    s.flush_shared_private().unwrap();let sent=f::send_pending(&mut s,now);
    assert!(contains(&sent,&native::owner_health(world.actors[0].health,true,90).unwrap()));assert!(!contains(&sent,&stale));
}

#[test]
fn p05c_ram_publication_later_crew_knockout_keeps_projectile_terminal_reason(){
    let now=Instant::now();let(mut s,mut world)=f::fixture_for(now,0);contact(&mut world,2.,1);
    let hp=world.actors[0].health;let shell=crate::p06t_shells091::profile(crate::p06t_shells091::Mount::Ms1Stock).shots[2];
    let cause=crate::p06t_device_state::Cause{shot:1,attacker_slot:1};
    let events=world.actors[0].devices.as_mut().unwrap().apply_hits(&[
        crate::p06t_device_state::ModuleHit{cause,ordinal:0,at_ms:100,target:crate::p06t_lab_proxy::Target::Seat(0),shell,ignition_roll:0.9},
        crate::p06t_device_state::ModuleHit{cause,ordinal:1,at_ms:100,target:crate::p06t_lab_proxy::Target::Seat(1),shell,ignition_roll:0.9}],
        crate::p06t_device_state::Health{hp:hp as u16,max_hp:90,terminal:false}).unwrap();
    assert!(!world.actors[0].crew_active());world.device_events.extend(events.into_iter().map(|event|(0,event)));
    world.damage_events.push(model::DamageRecord{sequence:1,tick:1001,attacker:1,target:0,shot:1,reason:0,
        health_before:hp,health_after:hp,crew_before:true,crew_after:false,direct:true,pierced:true});
    publish(s.shared.as_mut().unwrap(),&mut s.outbox,&world,now).unwrap();
    assert_current_health(&s,&world,0,Some(1),0);
    assert!(s.shared.as_ref().unwrap().private_pending.iter().any(|p|contains(&p.body,&native::owner_health(hp,false,90).unwrap())));
}

#[test]
fn p05c_ram_publication_unjournaled_hp_still_fails_closed(){
    let now=Instant::now();let(mut s,mut world)=f::fixture_for(now,0);world.actors[0].health=80;
    assert!(publish(s.shared.as_mut().unwrap(),&mut s.outbox,&world,now).is_err());
}
