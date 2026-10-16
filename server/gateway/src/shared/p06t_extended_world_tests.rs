//! Actual resource-bound World admission and weapon integration. Clock-only
//! tests below do not claim worker/native progression between their commands.
use super::*;
use crate::p06t_armament091 as arm;

fn world(id:u64,now:Instant)->World {
    let rows=super::super::super::profile13_templates::extended_test_resources();
    let mut world=World::new_for_roster(id,now,crate::map_profile091::MapId::Prohorovka,2).unwrap();
    for row in &rows{world.bind_geometry(row.geometry.clone()).unwrap();}
    world.enable_ap_test_lab().unwrap();world.bind_terrain(rows[0].terrain.clone()).unwrap();
    world.bind_fragiles(rows[0].catalog.0.clone()).unwrap();world.enable_extended_lab().unwrap();world
}
fn identity(slot:usize)->Identity {Identity{account:format!("source-lab-{slot}"),database:27000+slot as i32,name:format!("lab{slot}")}}
fn begin(world:&mut World,first:LabLoadout,now:Instant) {
    world.attach_extended_lab(identity(0),1,first).unwrap();
    world.attach_extended_lab(identity(1),2,LabLoadout::temporary(VehicleKind::Fv183)).unwrap();
    world.start(now).unwrap();for slot in 0..2{world.set_ready(slot,slot as u32+1).unwrap();}
}
fn shoot(world:&mut World,at:Instant){world.apply(0,1,&[Command::Armament(arm::Command::Shoot)],at).unwrap();}

#[test]fn p06t_extended_world_temporary_admission_is_explicit_bounded_and_never_owned(){
    let now=Instant::now();let mut world=world(27001,now);let loadout=LabLoadout::temporary(VehicleKind::Wt128);
    assert!(world.attach(identity(0),1).is_err());
    let before=world.failure_snapshot();let mut excessive=loadout;excessive.counts=[61,0,0];
    assert!(world.attach_extended_lab(identity(0),1,excessive).is_err());assert_eq!(world.failure_snapshot(),before);
    let mut empty=loadout;empty.counts=[0,6,6];assert!(world.attach_extended_lab(identity(0),1,empty).is_err());
    world.attach_extended_lab(identity(0),1,loadout).unwrap();let actor=&world.actors[0];
    assert!(actor.owned_loadout.is_none()&&actor.owned_v2.is_none());assert_eq!(actor.health,2000);
    assert_eq!(actor.devices.as_ref().unwrap().crew().len(),6);
    assert_eq!(actor.devices.as_ref().unwrap().policy_revision(),crate::p06t_device_state::POLICY_V2);
    assert_eq!(actor.fire.typed().unwrap().counts(),[12,6,6]);assert!(world.terminal_state_json(0).is_err());
    assert!(!VehicleKind::Wt128.battle_admission());assert_eq!(VehicleKind::Wt128.initial_ammo(),0);
}

#[test]fn p06t_extended_world_reattach_preserves_spent_ammo_and_rejects_changed_initial_loadout(){
    let now=Instant::now();let mut world=world(27002,now);let loadout=LabLoadout::temporary(VehicleKind::Wt128);begin(&mut world,loadout,now);
    shoot(&mut world,now);let ammunition=world.actors[0].fire.clone();let devices=world.actors[0].devices.clone();
    assert_eq!(ammunition.typed().unwrap().counts(),[11,6,6]);world.detach(1).unwrap();
    assert_eq!(world.attach_extended_lab(identity(0),99,loadout).unwrap(),0);
    assert_eq!(world.actors[0].fire,ammunition);assert_eq!(world.actors[0].devices,devices);
    let mut changed=loadout;changed.counts[0]-=1;let before=world.failure_snapshot();
    assert!(world.attach_extended_lab(identity(0),100,changed).is_err());assert_eq!(world.failure_snapshot(),before);
    assert_eq!(world.actors[0].session,Some(99));
}

#[test]fn p06t_extended_world_wt128_uses_six_shots_two_second_interval_and_full_reload(){
    let now=Instant::now();let mut world=world(27003,now);begin(&mut world,LabLoadout::temporary(VehicleKind::Wt128),now);
    for shot in 0..6{shoot(&mut world,now+Duration::from_secs(shot*2));assert_eq!(world.shots.len(),shot as usize+1);}
    assert_eq!(world.actors[0].fire.typed().unwrap().clip(),0);assert_eq!(world.actors[0].fire.typed().unwrap().counts(),[6,6,6]);
    for milliseconds in [12_000,69_999]{shoot(&mut world,now+Duration::from_millis(milliseconds));assert_eq!(world.shots.len(),6);}
    shoot(&mut world,now+Duration::from_secs(70));assert_eq!(world.shots.len(),7);
    assert_eq!(world.actors[0].fire.typed().unwrap().clip(),5);assert_eq!(world.actors[0].fire.typed().unwrap().counts(),[5,6,6]);
    assert!(world.projectiles.iter().all(|p|p.shell.unwrap().compact_descr==13850));
}

#[test]fn p06t_extended_world_fv_premium_hesh_is_frozen_as_he275_without_ap_conversion(){
    let now=Instant::now();let mut world=world(27004,now);let kind=VehicleKind::Fv183;
    let hesh=crate::p06t_shells091::profile(kind.mount()).shots[1];begin(&mut world,LabLoadout{kind,counts:[0,4,0],initial:hesh.compact_descr},now);
    shoot(&mut world,now);let frozen=world.projectiles[0].shell.unwrap();assert_eq!(frozen,hesh);
    assert_eq!(frozen.family,crate::p06t_shells091::Family::HighExplosive);assert_eq!(frozen.penetration_mm,[275.,275.]);
    assert!(frozen.premium_gold_flag);assert_eq!(world.actors[0].fire.typed().unwrap().counts(),[0,3,0]);
    let ap=crate::p06t_shells091::profile(kind.mount()).shots[0];
    world.apply(0,1,&[Command::Armament(arm::Command::Select(arm::Selection::Current,ap.compact_descr))],now+Duration::from_millis(1)).unwrap();
    assert_eq!(world.projectiles[0].shell.unwrap(),hesh);assert_eq!(world.actors[0].fire.typed().unwrap().counts(),[0,3,0]);
}
