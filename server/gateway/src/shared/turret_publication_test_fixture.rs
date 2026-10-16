//! AUTHORED publication state; actual Session/Window/parser, no collision or
//! writer authority claim. Source-contact World tests live in the domain module.
use super::*;
use std::sync::Arc;
use crate::{p06t_device_caps::Profile,p06t_device_state::State as Devices,transport091};

pub(super) fn fixture(now:Instant)->(Session,World){
    fixture_for(now,0)
}
pub(super) fn fixture_for(now:Instant,own:usize)->(Session,World){
    let authored=model::tests::world(now);
    let mut world=World::new_for_roster(6963,now,crate::map_profile091::MapId::Karelia,2).unwrap();
    world.bind_geometry(Arc::new(geometry::tests::bundle())).unwrap();
    world.bind_geometry(Arc::new(geometry::tests::is7_bundle())).unwrap();
    world.enable_ap_test_lab().unwrap();
    world.bind_terrain(Arc::new(terrain::tests::fixture(-1000.,2000.,2,vec![0.;4]))).unwrap();
    world.enable_mixed_ammo().unwrap();world.enable_lifecycle(lifecycle::Rules::prohorovka()).unwrap();
    world.enable_ammo_detonation().unwrap();world.actors=authored.actors;
    for actor in &mut world.actors{
        actor.fire=fire::State::with_typed(actor.vehicle_kind().mount(),[2,3,4],2570).unwrap();
        actor.devices=Some(Devices::new(Profile::Ms1));
    }
    world.start(now).unwrap();
    let owner=&world.actors[own].identity;
    let mut s=Session::new(own as u32+1,[1;16],"127.0.0.1:38302".parse().unwrap(),now);
    s.identity=Some(Arc::new(crate::identity091::Profile{account_id:owner.account.clone(),database_id:owner.database,
        name:owner.name.clone(),fixture_dir:std::path::PathBuf::new()}));
    s.active=true;s.account_ready=true;s.arena_base=true;s.sync_mask=7;s.rx=1;s.tx=super::super::Window::interactive();
    let mut c=Client::new(own);c.enable_spotting().unwrap();c.phase=Phase::Driving;c.correction=true;c.return_generation=1;
    c.interest.as_mut().unwrap().set_desired(mask(true),mask(true)).unwrap();
    let enter=s.tx.enqueue_body_tracked(&[wire::enter_vehicle(0).unwrap(),wire::enter_vehicle(1).unwrap()].concat()).unwrap();
    assert_eq!(enter,0);c.mark_announced(&[0,1],enter).unwrap();
    let creation=s.tx.enqueue_body_tracked(&[wire::create_vehicle(&world,0).unwrap(),wire::create_vehicle(&world,1).unwrap()].concat()).unwrap();
    for slot in 0..2{c.creations[slot]=Some((creation,false));c.creation_announcements[slot]=Some(enter);}
    s.shared=Some(c);ack_all(&mut s,now);
    let c=s.shared.as_mut().unwrap();c.health_sent=[Some(90);6];c.crew_sent=[Some(true);6];c.fire_sent=[Some(false);6];
    c.owner_health_sent=Some(90);c.devices_snapshot_sent=true;c.view=Some(world.clone());(s,world)
}
pub(super) fn mask(enemy:bool)->[bool;6]{[true,enemy,false,false,false,false]}
pub(super) fn detonate(world:&mut World){
    let joint=world.actors[1].position;let hp=world.actors[1].health;let sequence=world.damage_events.len()as u32+1;
    world.install_detonation_publication_fixture(ammo_detonation::Input{shot:sequence,target:1,attacker:0,tick:1000,
        device_sequence:3,device_before:12,device_after:0,health_before:hp as u16,residual_hp:18,counts:[2,3,4],
        kind:vehicle_profile::VehicleKind::Ms1,joint:ammo_detonation::JointPose{position:[joint[0],joint[1]+1.,joint[2]],direction:[0.;3]},from_fire:false}).unwrap();
    world.damage_events.push(model::DamageRecord{sequence,tick:1000,attacker:0,target:1,shot:sequence,reason:0,
        health_before:hp,health_after:0,crew_before:true,crew_after:false,direct:true,pierced:true});
}
pub(super) fn send_pending(s:&mut Session,now:Instant)->Vec<u8>{
    let mut bytes=Vec::new();while let Some((_,_,raw))=s.tx.due(now,s.rx).unwrap(){bytes.extend(transport091::parse_interactive(&raw).unwrap().body);}bytes
}
pub(super) fn ack_all(s:&mut Session,now:Instant){
    let mut cumulative=s.tx.cumulative;
    while let Some((sequence,_,_))=s.tx.due(now+std::time::Duration::from_secs(1),s.rx).unwrap(){cumulative=cumulative.max(sequence+1);}
    let ack=transport091::parse(&transport091::ack(cumulative)).unwrap();
    s.tx.acknowledge(&ack).unwrap();s.shared.as_mut().unwrap().acknowledge(s.tx.cumulative,&ack).unwrap();
}
pub(super) fn frame(s:&Session,payload:&[u8])->Frame{
    Frame{flags:0x458,sequence:Some(s.rx),cumulative:Some(s.tx.cumulative),selective:vec![],
        body:[vec![1],s.token.to_le_bytes().to_vec(),payload.to_vec()].concat(),piggybacks:vec![]}
}
