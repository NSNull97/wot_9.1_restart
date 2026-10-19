//! Authored terminal state; production publication and actual private epochs.
use super::*;
use crate::gateway091::shared::{detached_turret as dt,turret_publication_test_fixture as f};
fn contains(body:&[u8],bytes:&[u8])->bool{body.windows(bytes.len()).any(|part|part==bytes)}
#[test]fn p06t_detonation_delayed_publication_skips_intermediate_hp_and_emits_one_terminal_snapshot(){
    let now=Instant::now();let(mut s,mut world)=f::fixture(now);
    world.actors[1].health=60;
    world.damage_events.push(model::DamageRecord{sequence:1,tick:1000,attacker:0,target:1,shot:1,reason:0,
        health_before:90,health_after:60,crew_before:true,crew_after:true,direct:true,pierced:true});
    f::detonate(&mut world);let c=s.shared.as_mut().unwrap();publish(c,&mut s.outbox,&world,now).unwrap();
    let final_hp=dt::terminal_health(1,Some(0),0,dt::DeathKind::Detached).unwrap();
    assert_eq!(c.private_pending.iter().filter(|packet|contains(&packet.body,&final_hp)).count(),1);
    let old_hp=impact_wire::health_changed_for(world.actors[1].vehicle_kind(),1,60,0).unwrap();
    assert!(c.private_pending.iter().all(|packet|!contains(&packet.body,&old_hp)));assert_eq!(c.damage_cursor,2);
    assert_eq!(c.health_sent[1],Some(0));
}
#[test]fn p06t_detonation_native_negative_health_and_explosion_keep_owner_hud_domain_zero(){
    let now=Instant::now();let(mut s,mut world)=f::fixture_for(now,1);f::detonate(&mut world);
    let c=s.shared.as_mut().unwrap();publish(c,&mut s.outbox,&world,now).unwrap();
    let death=dt::terminal_health(1,Some(0),0,dt::DeathKind::Detached).unwrap();
    // #717 Avatar.updateVehicleHealth copies rawHealth into the own Vehicle:
    // the owner value must keep the -2 mark; domain and HUD stay zero.
    let fx=dt::explosion(1,1.,8.).unwrap();let hud=native::owner_health(-2,false,90).unwrap();
    assert!(c.private_pending.iter().any(|p|contains(&p.body,&death)));
    assert!(c.private_pending.iter().any(|p|contains(&p.body,&fx)));
    assert!(c.private_pending.iter().any(|p|contains(&p.body,&hud)));
    assert_eq!(c.health_sent[1],Some(0));assert_eq!(c.owner_health_sent,Some(0));
    assert_eq!(world.actors[1].health,0);assert_eq!(world.actors[1].fire.typed().unwrap().counts(),[0;3]);
    assert!(s.outbox.iter().any(|body|contains(body,&native::ammo_snapshot(world.actors[1].vehicle_kind().mount(),[0;3],
        world.actors[1].fire.typed().unwrap().current().compact_descr,world.actors[1].fire.typed().unwrap().next().compact_descr,
        world.actors[1].fire.typed().unwrap().clip()).unwrap())));
}
#[test]fn p06t_detonation_hidden_attacker_reference_is_zero_and_epoch_drop_rebuilds_negative_death(){
    let now=Instant::now();let(mut s,mut world)=f::fixture_for(now,1);f::detonate(&mut world);
    let c=s.shared.as_mut().unwrap();publish(c,&mut s.outbox,&world,now).unwrap();
    let old=dt::terminal_health(1,Some(0),0,dt::DeathKind::Detached).unwrap();
    assert!(c.private_pending.iter().any(|p|contains(&p.body,&old)&&p.targets.contains(&(0,0))));
    c.interest.as_mut().unwrap().set_desired([true,true,false,false,false,false],[false,true,false,false,false,false]).unwrap();
    // Drain the public ammo/roster bodies before applying the private visibility
    // fence, exactly as the production outbox/window order requires.
    s.drain_outbox().unwrap();s.flush_shared_private().unwrap();
    let c=s.shared.as_mut().unwrap();assert_eq!(c.health_sent[1],None);
    publish(c,&mut s.outbox,&world,now).unwrap();
    let fresh=dt::terminal_health(1,None,0,dt::DeathKind::Detached).unwrap();
    assert!(c.private_pending.iter().any(|p|contains(&p.body,&fresh)&&p.targets==vec![(1,0)]));
    assert!(c.private_pending.iter().all(|p|!contains(&p.body,&old)));
    assert_eq!(c.turrets.effect_cursor,1); // current explosion is never replayed.
}
