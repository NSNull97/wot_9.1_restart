use super::*;
fn roster(now:Instant,n:usize)->World{
    let mut w=World::new_for_roster(5001,now,crate::map_profile091::MapId::Karelia,n).unwrap();
    for slot in 0..n{let kind=if slot%2==0{VehicleKind::Ms1}else{VehicleKind::Is7};
        let(owner,loadout)=tests::profile13_loadout(kind,slot,kind.ammo_limit());w.attach_owned(owner,slot as u32+1,&loadout).unwrap();}
    w
}
#[test]fn mixed_scene_roster_requires_complete_capacity_and_preserves_each_source_budget(){
    let now=Instant::now();for n in [0,1,MAX_ACTORS+1]{assert!(World::new_for_roster(5,now,crate::map_profile091::MapId::Karelia,n).is_err());}
    let mut w=roster(now,6);assert_eq!(w.shot_limit(),576);assert!(w.set_expected_actors(2).is_err());
    w.start(now).unwrap();for slot in 0..6{w.set_ready(slot,slot as u32+1).unwrap();}
    for round in 0..96 {let at=now+Duration::from_secs(round*20);if round>0{w.advance(at).unwrap();}
        for slot in 0..6{w.apply(slot,slot as u32+1,&[Command::Fire(fire::Command::Shoot)],at).unwrap();}}
    assert_eq!(w.shots.len(),378);assert_eq!(w.projectiles.last().unwrap().sequence,378);
    assert!(w.actors.iter().all(|a|a.fire.ammo()==0));
    for slot in 0..6{let before=w.shots.len();w.apply(slot,slot as u32+1,&[Command::Fire(fire::Command::Shoot)],now+Duration::from_secs(1920)).unwrap();assert_eq!(w.shots.len(),before);}
}
#[test]fn mixed_scene_selects_nearest_of_all_other_vehicle_meshes_and_binds_target_armor(){
    let now=Instant::now();let mut w=roster(now,6);
    w.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).unwrap();
    w.bind_geometry(Arc::new(super::super::geometry::tests::is7_bundle())).unwrap();w.enable_ap_test_lab().unwrap();
    w.start(now).unwrap();for slot in 0..6{w.set_ready(slot,slot as u32+1).unwrap();
        let p=match slot{0=>[0.;3],1=>[0.,0.,40.],3=>[0.,0.,10.],5=>[0.,0.,60.],_=>[100.,0.,100.]};
        w.actors[slot].position=p;w.actors[slot].origin=p;w.actors[slot].direction=[0.;3];}
    w.apply(0,1,&[Command::Fire(fire::Command::Shoot)],now).unwrap();w.advance(now+STEP).unwrap();
    assert_eq!(w.contacts.len(),1);assert_eq!(w.contacts[0].target_slot,3);
    assert_eq!(w.contacts[0].geometry_revision,super::super::geometry::source_revision(VehicleKind::Is7));
    assert_eq!(w.contacts[0].material_facts.profile_revision,super::super::materials::profile_revision(VehicleKind::Is7));
    assert_eq!(w.actors[1].health,2150);assert_eq!(w.actors[5].health,2150);
    assert_eq!(w.impacts[0].health_before,2150);assert!(w.impacts[0].health_after>=2120);
}
#[test]fn mixed_scene_imports_pushed_detached_and_dead_bodies_without_restoring_control(){
    let now=Instant::now();let mut w=roster(now,6);w.start(now).unwrap();
    for slot in 0..6{w.set_ready(slot,slot as u32+1).unwrap();}
    w.detach(6).unwrap();w.actors[4].health=0;
    let rows=w.actors.iter().enumerate().map(|(slot,a)|(slot,[a.position[0]+1.,a.position[1],a.position[2]],a.direction,1.)).collect::<Vec<_>>();
    w.advance_with_external(now+STEP,Some(&rows)).unwrap();
    assert_eq!(w.actors[5].position,rows[5].1);assert_eq!(w.actors[4].position,rows[4].1);
    assert_eq!(w.actors[5].session,None);assert_eq!(w.actors[4].health,0);
    assert_eq!(w.actors[5].input,Input::STOP);assert_eq!(w.actors[4].input,Input::STOP);
    assert!(w.apply(5,6,&[Command::Move(Input{throttle:1,steer:0,speed_percent:100})],now+STEP).is_err());
    assert!(w.apply(4,5,&[Command::Fire(fire::Command::Shoot)],now+STEP).unwrap().is_empty());
}
