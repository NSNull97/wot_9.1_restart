//! Actual source terrain/obstacle queries with explicitly authored server poses.
//! No native/Jolt/owned-reservation acceptance is asserted by these fixtures.
use super::*;

fn pristine(now:Instant)->World{
    let mut world=World::new_for_map(0x900123,now,crate::map_profile091::MapId::Prohorovka).unwrap();
    world.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).unwrap();
    world.enable_ap_test_lab().unwrap();
    let terrain=super::super::terrain::tests::actual_prohorovka().clone()
        .with_obstacles(Arc::new(super::super::obstacles::tests::actual_prohorovka().clone())).unwrap();
    assert_eq!(terrain.source_revision(),crate::map_profile091::MapId::Prohorovka.spec().world_revision);
    world.bind_terrain(Arc::new(terrain)).unwrap();
    world.enable_lifecycle(super::super::lifecycle::Rules{
        prebattle_ms:1000,battle_ms:200_000,..super::super::lifecycle::Rules::prohorovka()}).unwrap();
    world
}
fn attach(world:&mut World,now:Instant,count:usize){
    if count!=2{world.set_expected_actors(count).unwrap();}
    for slot in 0..count{
        world.attach(Identity{account:format!("spot-domain-{slot}"),database:slot as i32+1,
            name:format!("spot_{slot}")},slot as u32+1).unwrap();
        world.actors[slot].position=[slot as f32*10.,1000.,0.];
    }
    world.start(now).unwrap();
    for slot in 0..count{world.set_ready(slot,slot as u32+1).unwrap();}
}
fn at(world:&mut World,start:Instant,millis:u64)->io::Result<bool>{
    world.tick=1000+(millis/100)as u32;
    world.advance_lifecycle(start+Duration::from_millis(millis))
}

#[test]fn p08c_firstspot_actual_source_los_waits_for_battle_and_never_reawards(){
    let now=Instant::now();let mut world=pristine(now);world.enable_result_spots().unwrap();attach(&mut world,now,2);
    // Authored high poses isolate actual pinned geometry traversal from worker
    // settlement. They are not claimed historical/physically driven spawns.
    assert!(world.desired_visibility(0).unwrap()[1]);
    at(&mut world,now,0).unwrap();at(&mut world,now,999).unwrap();
    assert_eq!(world.result_spots(),Some([].as_slice()));assert_eq!(world.result_spot_tick,None);
    at(&mut world,now,1000).unwrap();
    let rows=world.result_spots().unwrap().to_vec();assert_eq!(rows.len(),2);
    assert_eq!((rows[0].observer(),rows[0].target(),rows[0].tick()),(1,0,1010));
    assert_eq!((rows[1].observer(),rows[1].target(),rows[1].tick()),(0,1,1010));
    at(&mut world,now,1000).unwrap();assert_eq!(world.result_spots().unwrap(),rows);
    world.actors[1].position[0]=500.;at(&mut world,now,1100).unwrap();
    world.actors[1].position[0]=10.;at(&mut world,now,1200).unwrap();
    assert_eq!(world.result_spots().unwrap(),rows);
    world.terrain=None; // prove terminal phase never attempts a new LOS query
    world.actors[1].session=None;at(&mut world,now,1300).unwrap();
    assert!(world.lifecycle.as_ref().unwrap().outcome().is_some());
    assert_eq!(world.result_spots().unwrap(),rows);
}

#[test]fn p08c_firstspot_actual_ground_occlusion_is_not_credited_until_clear(){
    let now=Instant::now();let mut world=pristine(now);world.enable_result_spots().unwrap();attach(&mut world,now,2);
    let ground=world.terrain.as_ref().unwrap().nearest([0.,1000.,0.],[0.,-1000.,0.]).unwrap().unwrap().point[1];
    // Deliberately authored above/below source-surface endpoints exercise the
    // real terrain blocker; the underground target is not a legal spawn claim.
    world.actors[0].position=[0.,ground+10.,0.];world.actors[1].position=[0.,ground-10.,0.];
    assert!(!world.desired_visibility(0).unwrap()[1]);
    assert!(!world.desired_visibility(1).unwrap()[0]);
    at(&mut world,now,0).unwrap();at(&mut world,now,1000).unwrap();assert!(world.result_spots().unwrap().is_empty());
    world.actors[0].position=[0.,1000.,0.];world.actors[1].position=[10.,1000.,0.];
    assert!(world.desired_visibility(0).unwrap()[1]);
    at(&mut world,now,1100).unwrap();assert_eq!(world.result_spots().unwrap().len(),2);
}

#[test]fn p08c_firstspot_actual_source_range_and_six_member_eligibility(){
    let now=Instant::now();let mut world=pristine(now);world.enable_result_spots().unwrap();attach(&mut world,now,6);
    for(slot,actor)in world.actors.iter_mut().enumerate(){actor.position=[slot as f32*300.-750.,1000.,0.];}
    at(&mut world,now,0).unwrap();at(&mut world,now,1000).unwrap();assert!(world.result_spots().unwrap().is_empty());
    for(slot,actor)in world.actors.iter_mut().enumerate(){actor.position=[slot as f32*5.,1000.,0.];}
    world.actors[0].health=0;world.actors[1].session=None;world.actors[2].ready=false;
    at(&mut world,now,1100).unwrap();let rows=world.result_spots().unwrap();
    assert_eq!(rows.len(),3);
    assert_eq!(rows.iter().map(|r|(r.observer(),r.target())).collect::<Vec<_>>(),vec![(4,3),(3,4),(4,5)]);
}

#[test]fn p08c_firstspot_same_point_six_member_tie_uses_domain_slot_order(){
    let now=Instant::now();let mut world=pristine(now);world.enable_result_spots().unwrap();attach(&mut world,now,6);
    for actor in &mut world.actors{actor.position=[0.,1000.,0.];}
    // Same source pivot/orientation gives exactly equal sight points, handled
    // by the existing visibility zero-length clear rule; no invented ray hit.
    at(&mut world,now,0).unwrap();at(&mut world,now,1000).unwrap();let rows=world.result_spots().unwrap();
    assert_eq!(rows.len(),6);
    assert_eq!(rows.iter().map(|r|(r.observer(),r.target())).collect::<Vec<_>>(),
        (0..6).map(|target|(if target%2==0{1}else{0},target)).collect::<Vec<_>>());
}

#[test]fn p08c_firstspot_failed_query_does_not_commit_lifecycle_cursor_or_actor_stop(){
    let now=Instant::now();let mut world=pristine(now);world.enable_result_spots().unwrap();attach(&mut world,now,2);
    at(&mut world,now,0).unwrap();world.terrain=None;
    world.actors[0].input=Input{throttle:1,steer:1,speed_percent:100};
    let phase=world.lifecycle.as_ref().unwrap().view();let actors=world.actors.clone();let rows=world.result_spots().unwrap().to_vec();
    assert!(at(&mut world,now,1000).is_err());
    assert_eq!(world.lifecycle.as_ref().unwrap().view(),phase);assert_eq!(world.actors,actors);
    assert_eq!(world.result_spots().unwrap(),rows);assert_eq!(world.result_spot_tick,None);
}

#[test]fn p08c_firstspot_default_none_keeps_no_terrain_query_legacy_route(){
    let now=Instant::now();let mut world=pristine(now);world.terrain=None;attach(&mut world,now,2);
    at(&mut world,now,0).unwrap();at(&mut world,now,1000).unwrap();
    assert!(world.lifecycle.as_ref().unwrap().allows_actions());assert!(world.result_spots().is_none());
}

#[test]fn p08c_firstspot_optin_and_pristine_template_freshness_are_strict(){
    let now=Instant::now();let mut cold=World::new(17,now).unwrap();assert!(cold.enable_result_spots().is_err());
    cold.enable_lifecycle(super::super::lifecycle::Rules::prohorovka()).unwrap();assert!(cold.enable_result_spots().is_err());
    let mut template=pristine(now);template.enable_result_spots().unwrap();assert!(template.enable_result_spots().is_err());
    let fresh=template.fresh_battle(0x900124,now).unwrap();assert_eq!(fresh.result_spots(),Some([].as_slice()));
    assert!(fresh.result_spot_tick.is_none());
    template.result_spot_tick=Some(1000);assert!(template.fresh_battle(0x900124,now).is_err());
    let mut started=pristine(now);attach(&mut started,now,2);assert!(started.enable_result_spots().is_err());
}
