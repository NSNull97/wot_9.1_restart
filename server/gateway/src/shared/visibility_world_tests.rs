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

fn rollover_source_box(kind:VehicleKind)->([f32;3],[f32;3]){
    use sha2::Digest;
    let raw=match kind{
        VehicleKind::Ms1=>include_bytes!("../drive/worker/ms1-handling-profile.json").as_slice(),
        VehicleKind::Is7=>include_bytes!("../drive/worker/is7-handling-profile.json").as_slice(),
        _=>panic!("rollover fixture requires the admitted MS-1/IS-7 body"),
    };
    let profile=super::super::ram_proof::Profile::for_vehicle(kind);
    assert_eq!(format!("{:x}",sha2::Sha256::digest(raw)),profile.sha());
    let value:serde_json::Value=serde_json::from_slice(raw).unwrap();
    let vector=|field:&str|std::array::from_fn::<_,3,_>(|axis|value["physics"][field][axis].as_f64().unwrap()as f32);
    let half=vector("body_half_extents");
    assert_eq!(half.map(f32::to_bits),profile.half().map(f32::to_bits));
    (vector("body_center_offset"),half)
}

fn place_box_on_flat(world:&mut World,slot:usize,com_x:f32,roof:bool,yaw:f32){
    let(center,half)=rollover_source_box(world.actors[slot].vehicle_kind());
    // Independent contact geometry: the actual box COM is half.y above y=0.
    // A 180-degree roll negates center.x/y, then ordinary analytic Ry applies.
    // No call to the sight-point helper or pose encoder determines this origin.
    let sign=if roof{-1.}else{1.};let(s,c)=yaw.sin_cos();
    let offset=[c*sign*center[0]+s*center[2],sign*center[1],-s*sign*center[0]+c*center[2]];
    world.actors[slot].position=[com_x-offset[0],half[1]-offset[1],-offset[2]];
    world.actors[slot].direction=[yaw,0.,if roof{std::f32::consts::PI}else{0.}];
}

#[test]fn p05c_rollover_los_source_boxes_resting_on_roof_remain_visible_both_ways(){
    for roof_slot in 0..2{
        for yaw in [0.,0.7,-2.1]{
            let mut world=fixture(&[VehicleKind::Ms1,VehicleKind::Is7]);
            world.terrain=Some(Arc::new(super::super::terrain::tests::fixture(-100.,200.,2,vec![0.;4])));
            for slot in 0..2{place_box_on_flat(&mut world,slot,if slot==0{-10.}else{10.},slot==roof_slot,yaw);}
            let before=world.failure_snapshot();
            for own in 0..2{
                assert!(world.desired_visibility(own).unwrap()[1-own],
                    "source box roof_slot={roof_slot} yaw={yaw} recipient={own} must not put its LOS endpoint underground");
            }
            assert_eq!(world.failure_snapshot(),before);
        }
    }
}

#[test]fn p05c_rollover_los_roof_rest_does_not_bypass_a_static_wall_or_ground_ridge(){
    for roof_slot in 0..2{
        let mut world=fixture(&[VehicleKind::Ms1,VehicleKind::Is7]);
        for slot in 0..2{place_box_on_flat(&mut world,slot,if slot==0{-10.}else{10.},slot==roof_slot,0.7);}
        let wall=super::super::obstacles::tests::fixture(vec![wall(0.)]);
        world.terrain=Some(Arc::new(super::super::terrain::tests::fixture(-100.,200.,2,vec![0.;4])
            .with_obstacles(Arc::new(wall)).unwrap()));
        for own in 0..2{assert!(!world.desired_visibility(own).unwrap()[1-own],"wall roof_slot={roof_slot} recipient={own}");}
        // Both boxes rest on the flat y=0 portions at +/-60. The middle x=0
        // column rises to20m; this is actual Terrain intersection, not a mock.
        for slot in 0..2{place_box_on_flat(&mut world,slot,if slot==0{-60.}else{60.},slot==roof_slot,-2.1);}
        let heights=(0..25).map(|index|if index%5==2{20.}else{0.}).collect();
        world.terrain=Some(Arc::new(super::super::terrain::tests::fixture(-100.,50.,5,heights)));
        for own in 0..2{assert!(!world.desired_visibility(own).unwrap()[1-own],"ridge roof_slot={roof_slot} recipient={own}");}
    }
}

#[test]fn p05c_rollover_los_upright_yaw_keeps_previous_sight_points_exact(){
    let mut world=fixture(&[VehicleKind::Ms1,VehicleKind::Is7]);
    for slot in 0..2{
        for yaw in [-std::f32::consts::PI,-2.1,0.,0.7,std::f32::consts::PI]{
            world.actors[slot].position=[-17.25,7.75,99.125];
            world.actors[slot].direction=[yaw,0.,0.];
            let pivot=world.actors[slot].vehicle_kind().aim().pivot;
            // Independent analytic yaw-only image of the previous local point.
            // This is not a rotation encoder/decoder round trip.
            let(s,c)=yaw.sin_cos();
            let offset=[c*pivot[0]+s*pivot[2],pivot[1]+0.5,-s*pivot[0]+c*pivot[2]];
            let expected=std::array::from_fn::<_,3,_>(|axis|world.actors[slot].position[axis]+offset[axis]);
            let actual=World::visibility_sight_point(&world.actors[slot]);
            assert_eq!(actual.map(f32::to_bits),expected.map(f32::to_bits),"slot={slot} yaw={yaw}");
        }
    }
}

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
    let expected=(0..6).map(|own|world.desired_visibility(own).unwrap()).collect::<Vec<_>>();
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
    assert_eq!(world.desired_visibility(0).unwrap()[..6],[true,false,false,false,false,false]);
    assert_eq!(world.desired_visibility(1).unwrap()[..6],[true,true,false,false,false,false]);
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
        object_revision:format!("unit-{id}"),kind:fragiles::ObjectKind::Fragile,falling:None};
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
