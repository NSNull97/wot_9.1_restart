//! Deterministic world/terrain unit fixtures; no native spotting compatibility claim.
use super::*;
use crate::map_profile091::MapId;

fn fixture(kinds:&[VehicleKind])->World{
    let now=Instant::now();
    let mut world=World::new_for_roster(707,now,MapId::Karelia,kinds.len()).unwrap();
    world.enable_lifecycle(super::super::lifecycle::Rules::prohorovka()).unwrap();
    for(slot,kind)in kinds.iter().copied().enumerate(){
        let(identity,loadout)=super::tests::profile13_loadout(kind,slot,7);
        world.attach_owned(identity,slot as u32+1,&loadout).unwrap();
        world.actors[slot].position=[slot as f32*20.,0.,0.];
    }
    world.terrain=Some(Arc::new(super::super::terrain::tests::fixture(-500.,1000.,2,vec![-100.;4])));
    world
}

fn wall(x:f32)->[[f32;3];3]{[[x,-100.,-100.],[x,100.,-100.],[x,0.,100.]]}

#[test]fn p07b_world_pinned_prohorovka_six_mixed_recipients_twenty_snapshots(){
    // Exact source buffers are validated by both existing loaders. Independent
    // f64 triangle observation: local/evidence/20261016-p07b-01/independent-rays01.json
    // SHA256 c0e8bca02da59b55ae1beda890f10b2fd73316fdcdb496a55154b0b262c5f7dd.
    // First chord hits original toilet instance17/triangle8521. The second is
    // clear of both actual terrain and actual static geometry. These are unit
    // poses chosen to exercise geometry, not a native drive/spotting claim.
    let map=MapId::Prohorovka;
    let terrain=super::super::terrain::tests::actual_prohorovka().clone()
        .with_obstacles(Arc::new(super::super::obstacles::tests::actual_prohorovka().clone())).unwrap();
    assert_eq!(terrain.source_revision(),map.spec().world_revision);
    let points=[[85.,12.,71.7],[93.,12.,71.7],[80.,20.,65.],
        [100.,20.,65.],[80.,20.,85.],[100.,20.,85.]];
    let blocked=terrain.nearest(points[0],points[1]).unwrap().unwrap();
    assert_eq!(blocked.triangle_id,8521);
    assert!(matches!(blocked.surface,terrain::Surface::StaticObstacle{instance_id:17,..}));
    assert!(terrain.nearest(points[2],points[3]).unwrap().is_none());
    let mut world=World::new_for_roster(708,Instant::now(),map,MAX_ACTORS).unwrap();
    world.enable_lifecycle(super::super::lifecycle::Rules::prohorovka()).unwrap();
    world.terrain=Some(Arc::new(terrain));
    for(slot,point)in points.into_iter().enumerate(){
        let kind=if slot%2==0{VehicleKind::Ms1}else{VehicleKind::Is7};
        let(identity,loadout)=super::tests::profile13_loadout(kind,slot,7);
        world.attach_owned(identity,slot as u32+1,&loadout).unwrap();
        let pivot=kind.aim().pivot;
        let offset=super::super::pose::rotate([pivot[0],pivot[1]+0.5,pivot[2]],[0.;3]);
        world.actors[slot].position=std::array::from_fn(|axis|point[axis]-offset[axis]);
    }
    let before=world.failure_snapshot();
    let expected=(0..MAX_ACTORS).map(|own|world.desired_visibility(own).unwrap()).collect::<Vec<_>>();
    assert!(!expected[0][1]);assert!(expected[2][3]);
    // All six mixed recipients are in range, with three enemies each: 18 LOS
    // queries per complete snapshot, 360 across these20 recomputations.
    let started=Instant::now();
    for _ in 0..20{for(own,row)in expected.iter().enumerate(){
        assert_eq!(world.desired_visibility(own).unwrap(),*row);
    }}
    let elapsed=started.elapsed();
    assert_eq!(world.failure_snapshot(),before);
    eprintln!("P07B actual Prohorovka: six mixed recipients,20 snapshots,360 LOS queries; elapsed_us={} per_snapshot_us={}; debug/unit observation only, no timing/native acceptance threshold",elapsed.as_micros(),elapsed.as_micros()/20);
}

#[test]fn p07b_world_uses_mixed_source_ranges_and_actual_teams_without_mutation(){
    let mut world=fixture(&[VehicleKind::Ms1,VehicleKind::Is7]);
    world.actors[1].position=[300.,0.,0.];
    let before=world.failure_snapshot();
    assert_eq!(world.desired_visibility(0).unwrap(),[true,false,false,false,false,false]);
    assert_eq!(world.desired_visibility(1).unwrap(),[true,true,false,false,false,false]);
    assert_eq!(world.failure_snapshot(),before);
    world.actors[1].position=[240.,0.,0.];assert!(world.desired_visibility(0).unwrap()[1]);
    world.actors[1].position=[240.001,0.,0.];assert!(!world.desired_visibility(0).unwrap()[1]);
    let mut six=fixture(&[VehicleKind::Ms1;MAX_ACTORS]);
    six.actors[2].position=[900.,0.,0.]; // Allied by authoritative lifecycle slot team.
    assert!(six.desired_visibility(0).unwrap()[2]);
    assert_eq!(six.desired_visibility(5).unwrap().len(),MAX_ACTORS);
    assert!(six.desired_visibility(MAX_ACTORS).is_err());
}

#[test]fn p07b_world_requires_real_terrain_and_rejects_invalid_authoritative_pose(){
    let mut world=fixture(&[VehicleKind::Ms1;2]);
    world.terrain=None;assert!(world.desired_visibility(0).is_err());
    world.terrain=Some(Arc::new(super::super::terrain::tests::fixture(-500.,1000.,2,vec![-100.;4])));
    world.actors[1].position[0]=f32::NAN;assert!(world.desired_visibility(0).is_err());
    world.actors[1].position=[20.,0.,0.];world.actors[0].direction[2]=f32::INFINITY;
    assert!(world.desired_visibility(0).is_err());
}

#[test]fn p07b_world_terrain_ridge_and_static_wall_really_occlude(){
    let mut world=fixture(&[VehicleKind::Ms1;2]);
    world.actors[0].position=[0.,0.,50.];world.actors[1].position=[100.,0.,50.];
    let heights=vec![0.,20.,0.,0.,20.,0.,0.,20.,0.];
    world.terrain=Some(Arc::new(super::super::terrain::tests::fixture(0.,50.,3,heights)));
    assert!(!world.desired_visibility(0).unwrap()[1]);
    world.terrain=Some(Arc::new(super::super::terrain::tests::fixture(0.,50.,3,vec![0.;9])));
    assert!(world.desired_visibility(0).unwrap()[1]);
    world.actors[0].position=[0.;3];world.actors[1].position=[100.,0.,0.];
    let obstacles=super::super::obstacles::tests::fixture(vec![wall(50.)]);
    let terrain=super::super::terrain::tests::fixture(-500.,1000.,2,vec![-100.;4])
        .with_obstacles(Arc::new(obstacles)).unwrap();
    world.terrain=Some(Arc::new(terrain));assert!(!world.desired_visibility(0).unwrap()[1]);
}

#[test]fn p07b_world_equal_sight_points_are_clear_and_parked_wrecks_remain_targets(){
    let mut world=fixture(&[VehicleKind::Ms1;2]);
    world.actors[1].position=world.actors[0].position;
    // The production Terrain query rejects zero-length chords. This proves
    // equal-point handling occurs before that query, without mocking LOS.
    assert!(world.desired_visibility(0).unwrap()[1]);
    world.actors[1].position=[20.,0.,0.];world.actors[1].health=0;
    world.actors[1].session=None;world.actors[1].ready=false;
    assert!(world.desired_visibility(0).unwrap()[1]);
    world.actors[1].position=[300.,0.,0.];assert!(!world.desired_visibility(0).unwrap()[1]);
}

#[test]fn p07b_world_rotates_the_explicit_lab_sight_offset_with_chassis_pose(){
    let mut world=fixture(&[VehicleKind::Ms1;2]);
    world.actors[1].position=[100.,0.,0.];
    // Horizontal wall separates both upright sight points from the rolled
    // sight points below it. Range/poses stay fixed except authoritative roll.
    let roof=[[-10.,1.,-100.],[110.,1.,-100.],[50.,1.,100.]];
    let terrain=super::super::terrain::tests::fixture(-500.,1000.,2,vec![-100.;4])
        .with_obstacles(Arc::new(super::super::obstacles::tests::fixture(vec![roof]))).unwrap();
    world.terrain=Some(Arc::new(terrain));
    assert!(world.desired_visibility(0).unwrap()[1]);
    world.actors[1].direction=[0.,0.,std::f32::consts::PI];
    assert!(!world.desired_visibility(0).unwrap()[1]);
}

#[test]fn p07b_world_removal_excludes_actual_instance_ids_and_sorts_the_query(){
    let mut world=fixture(&[VehicleKind::Ms1;2]);world.actors[1].position=[100.,0.,0.];
    let terrain=super::super::terrain::tests::fixture(-500.,1000.,2,vec![-100.;4])
        .with_obstacles(Arc::new(super::super::obstacles::tests::fixture(vec![wall(40.),wall(60.)]))).unwrap();
    world.terrain=Some(Arc::new(terrain));
    // Explicit synthetic catalogue: object IDs77/99 differ from actual mesh
    // instance IDs1/0. No client asset or native catalogue is claimed here.
    let object=|id,instance|fragiles::Object{object_id:id,instance_id:instance,chunk_id:0,native_index:0,
        resource:"synthetic-wall".into(),health:1,material_kind:111,projectile_first_triangle:instance,
        projectile_triangle_count:1,physics_first_triangle:instance,physics_triangle_count:1,
        object_revision:format!("unit-{id}"),kind:fragiles::ObjectKind::Fragile};
    let catalog=Arc::new(fragiles::Catalog{map:MapId::Karelia,sha256:"0".repeat(64),worker_file:"unused.json".into(),
        worker_sha256:"0".repeat(64),contacts:false,objects:vec![object(77,1),object(99,0)],version:1,area_chunks:vec![0]});
    let mut state=fragiles::State::new(catalog);
    assert!(!world.desired_visibility(0).unwrap()[1]);
    for(shot,instance)in [(1,1),(2,0)]{
        let hit=terrain::Hit{surface:terrain::Surface::StaticObstacle{instance_id:instance,material_kind:111},
            triangle_id:instance,t:0.5,point:[50.,1.8,0.],normal:[1.,0.,0.]};
        assert!(state.contact_for(VehicleKind::Ms1,shot,0,1001,hit).unwrap().is_some());
    }
    assert_eq!(state.projectile_excluded(),vec![1,0]);
    world.fragiles=Some(state);assert!(world.desired_visibility(0).unwrap()[1]);
}
