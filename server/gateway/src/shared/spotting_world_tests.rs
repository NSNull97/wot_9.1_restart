use super::*;

fn fixture(now:Instant)->World {
    let mut world=World::new_for_vehicle(717,now,crate::map_profile091::MapId::Karelia,VehicleKind::Ms1).unwrap();
    world.enable_lifecycle(super::super::lifecycle::Rules::prohorovka()).unwrap();
    world.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).unwrap();
    world.enable_ap_test_lab().unwrap();
    world.bind_terrain(Arc::new(super::super::terrain::tests::fixture(-500.,1000.,2,vec![-100.;4]))).unwrap();
    world.enable_original_spotting(super::super::spotting::Rules::selected().unwrap()).unwrap();
    for slot in 0..2 {
        let (identity,loadout)=super::tests::profile13_loadout(VehicleKind::Ms1,slot,7);
        world.attach_owned(identity,slot as u32+1,&loadout).unwrap();
        world.actors[slot].position=[slot as f32*100.,0.,0.];
    }
    world.start(now).unwrap();world.set_ready(0,1).unwrap();world.set_ready(1,2).unwrap();world
}

#[test]
fn p07b_original_world_recomputes_mounted_source_points_and_range_atomically(){
    let now=Instant::now();let mut world=fixture(now);
    world.refresh_original_spotting(now).unwrap();
    assert!(world.desired_visibility(0).unwrap()[1]);
    let before=world.failure_snapshot();
    world.actors[1].position[0]=f32::NAN;
    assert!(world.desired_visibility(0).is_err());
    assert_eq!(world.failure_snapshot()["tick"],before["tick"]);
}

#[test]
fn p07b_original_world_static_obstacle_blocks_all_source_rays_but_surface_fx_is_separate(){
    let now=Instant::now();let mut world=fixture(now);
    let wall_a=[[50.,-100.,-100.],[50.,100.,-100.],[50.,100.,100.]];
    let wall_b=[[50.,-100.,-100.],[50.,100.,100.],[50.,-100.,100.]];
    let terrain=super::super::terrain::tests::fixture(-500.,1000.,2,vec![-100.;4])
        .with_obstacles(Arc::new(super::super::obstacles::tests::fixture(vec![wall_a,wall_b]))).unwrap();
    world.terrain=Some(Arc::new(terrain));
    world.refresh_original_spotting(now).unwrap();
    assert!(!world.desired_visibility(0).unwrap()[1]);
    assert!(world.original_spotting_enabled());
}
