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

#[test]
fn content0_s5_stereoscope_arms_only_after_three_seconds_of_committed_hull_rest() {
    use crate::{p06t_shells091 as shells, profile13_v2091 as v2};
    let start = Instant::now();
    let kind = VehicleKind::Ms1;
    let mut world = World::new_for_roster(717, start, crate::map_profile091::MapId::Karelia, 2).unwrap();
    world.enable_lifecycle(super::super::lifecycle::Rules::prohorovka()).unwrap();
    world.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).unwrap();
    world.bind_geometry(Arc::new(super::super::geometry::tests::is7_bundle())).unwrap();
    world.enable_ap_test_lab().unwrap();
    world.bind_terrain(Arc::new(super::super::terrain::tests::fixture(-500., 1000., 2, vec![-100.; 4]))).unwrap();
    world.enable_original_spotting(super::super::spotting::Rules::selected().unwrap()).unwrap();
    world.enable_mixed_ammo().unwrap();
    for (slot, devices) in [[v2::COATED_OPTICS, v2::STEREOSCOPE, 0], [0;3]].into_iter().enumerate() {
        let (owner, legacy) = super::tests::profile13_loadout(kind, slot, 20);
        let profile = shells::profile(kind.mount());
        let ammunition = profile.shots.iter().zip(["ap", "heat", "he"]).enumerate().map(|(index, (shot, suffix))| {
            serde_json::json!({"shell_definition_id":format!("shell:ms1-stock-{suffix}"),
                "shell_compact_id":shot.compact_descr,"family":shot.family.source_name(),"count":if index==0{20}else{0}})
        }).collect::<Vec<_>>();
        let mut value = serde_json::json!({"kind":kind.label(),"descriptor_hex":kind.descriptor().iter().map(|b|format!("{b:02x}")).collect::<String>(),
            "native_inventory_id":1,"vehicle_inventory_id":legacy.vehicle_inventory_id,"max_hp":kind.max_health(),
            "crew_ids":legacy.crew_ids,"capacity":profile.capacity,"ammunition":ammunition,
            "initial_shell_compact_id":profile.shots[0].compact_descr});
        if devices != [0;3] {
            value["artefacts"] = serde_json::json!({"optional_devices":devices,"consumables":[0,0,0]});
        }
        use sha2::Digest;
        let digest = format!("{:x}", sha2::Sha256::digest(serde_json::to_vec(&value).unwrap()));
        let frozen = v2::parse_frozen(&value, &owner.account, &digest).unwrap();
        assert_eq!(world.attach_owned_v2(owner, slot as u32 + 1, &frozen).unwrap(), slot);
    }
    world.start(start).unwrap();
    world.set_ready(0, 1).unwrap();
    world.set_ready(1, 2).unwrap();
    let placeholders = crate::armament_wire091::equipment_row(0, 0).unwrap().repeat(3);
    let binding = super::super::wire::binding(&world, 0, start).unwrap();
    assert!(binding.windows(placeholders.len()).any(|bytes| bytes == placeholders));
    // Target is beyond the optics' 264 m but within the active scope's 300 m.
    let mut rows = [(0, [0.;3], [0.;3], 0.), (1, [285.,0.,0.], [0.;3], 0.)];
    for tick in 1..=30 {
        let at = start + STEP * tick;
        world.advance_with_external(at, Some(&rows)).unwrap();
        world.refresh_original_spotting(at).unwrap();
        assert_eq!(world.actors[0].stereoscope_status(), Some(false));
        assert!(!world.own_sightings(0).unwrap()[1]);
    }
    world.actors[0].aim.yaw = 0.3;
    world.actors[0].input = Input { throttle: 1, steer: 0, speed_percent: 100 };
    let at = start + STEP * 31;
    world.advance_with_external(at, Some(&rows)).unwrap();
    world.refresh_original_spotting(at).unwrap();
    assert_eq!(world.actors[0].stereoscope_status(), Some(true));
    assert_eq!(world.actors[0].view_range().unwrap(), 300.);
    assert!(world.own_sightings(0).unwrap()[1]);

    rows[0].2[0] = 0.02;
    let at = start + STEP * 32;
    world.advance_with_external(at, Some(&rows)).unwrap();
    world.refresh_original_spotting(at).unwrap();
    assert_eq!(world.actors[0].stereoscope_status(), Some(false));
    assert_eq!(world.actors[0].view_range().unwrap(), 264.);
    assert!(!world.own_sightings(0).unwrap()[1]);
    for tick in 33..=62 {
        world.advance_with_external(start + STEP * tick, Some(&rows)).unwrap();
    }
    assert_eq!(world.actors[0].stereoscope_status(), Some(true));
    // An actual push resets the scope even with zero reported longitudinal speed.
    rows[0].1[0] = 0.1;
    world.advance_with_external(start + STEP * 63, Some(&rows)).unwrap();
    assert_eq!(world.actors[0].stereoscope_status(), Some(false));
    assert_eq!(world.actors[1].stereoscope_status(), None);
}
