use super::*;

pub(super) fn fixture(now:Instant)->World {
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
fn content0_s5a_assist_evidence_uses_committed_direct_scan_and_actor_liveness() {
    let now=Instant::now();let mut world=fixture(now);
    let extra=world.actors[0].clone();world.actors.push(extra.clone());world.actors.push(extra.clone());world.actors.push(extra);
    world.set_test_teams(&[1,2,1,2,1]);
    world.actors[0].position=[0.,0.,0.];world.actors[1].position=[100.,0.,0.];
    world.actors[2].position=[500.,0.,0.];world.actors[3].position=[5.,0.,0.];world.actors[4].position=[10.,0.,0.];
    world.refresh_original_spotting(now).unwrap();
    let snapshot=world.assist_evidence(&world.actors,2,1,1000).unwrap().unwrap();
    assert_eq!(snapshot.scan_tick,Some(1000));
    assert_eq!(snapshot.direct_mask,(1<<0)|(1<<4));
    let mut changed=world.actors.clone();changed[0].health=0;changed[3].session=None;changed[4].ready=false;
    assert_eq!(world.assist_evidence(&changed,2,1,1000).unwrap().unwrap().direct_mask,0);
    assert_eq!(world.assist_evidence(&world.actors,2,1,1003).unwrap().unwrap().direct_mask,0,"stale scan fails closed");
    assert_eq!(world.assist_evidence(&world.actors,2,1,999).is_err(),true);
    // Losing direct sight does not replace the prior event; the next committed
    // scan has no contributors, even if a published retention remains.
    world.actors[1].position=[900.,0.,0.];world.refresh_original_spotting(now+STEP).unwrap();
    assert!(world.desired_visibility(0).unwrap()[1],"team publication is retained after direct sight is lost");
    assert_eq!(world.assist_evidence(&world.actors,2,1,1001).unwrap().unwrap().direct_mask,0);
    assert_ne!(snapshot.direct_mask,0);
}

#[test]
fn content0_s5a_ram_assist_uses_one_precontact_snapshot_for_both_deaths() {
    let now=Instant::now();let mut world=fixture(now);
    let extra=world.actors[0].clone();for _ in 0..4 {world.actors.push(extra.clone());}
    world.set_test_teams(&[1,2,1,2,1,2]);
    for (slot,x) in [0.,300.,295.,-5.,305.,5.].into_iter().enumerate(){world.actors[slot].position=[x,0.,0.];}
    world.actors[0].health=1;world.actors[1].health=1;
    world.refresh_original_spotting(now).unwrap();
    let c=TankContactInput{slot_a:0,slot_b:1,substep:1,point:[0.,1.,0.],normal:[1.,0.,0.],relative_velocity:[10.,0.,0.]};
    world.apply_tank_contacts(&[c],1,1).unwrap();
    assert_eq!(world.ram_damage_events.len(),2);
    assert_eq!((world.actors[0].health,world.actors[1].health),(0,0));
    let first=&world.ram_damage_events[0];let second=&world.ram_damage_events[1];
    assert_eq!(first.spotting.unwrap().direct_mask,(1<<2)|(1<<4));
    assert_eq!(second.spotting.unwrap().direct_mask,(1<<3)|(1<<5));
    assert_eq!((first.health_before-first.health_after,second.health_before-second.health_after),(1,1));
    let credits=super::super::server::battle_ledger::credits(&world).unwrap();
    assert_eq!(credits.iter().map(|c|(c.recipient,c.target,c.amount)).collect::<Vec<_>>(),vec![(2,1,1),(3,0,1)]);
    let mut gateway=crate::bw_wire::Arcs::new(false);let mut worker=crate::bw_wire::Arcs::new(true);
    let wire=crate::bw_wire::encode(&world.ram_damage_events[0],now,&mut gateway).unwrap();
    let restored:RamDamageRecord=crate::bw_wire::decode(&wire,now,&mut worker).unwrap();
    assert_eq!(&restored,first);
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
fn foliage_project_volume_affects_actual_world_rays_only_when_opted_in() {
    let now=Instant::now();let mut world=fixture(now);
    world.original_spotting.as_mut().unwrap().rules.camouflage=true;
    world.original_spotting.as_mut().unwrap().rules.retention_ms=0;
    world.actors[1].position=[200.,0.,0.];
    world.refresh_original_spotting(now).unwrap();
    assert!(world.own_sightings(0).unwrap()[1]);
    // In this synthetic terrain fixture the same two actors and geometry are
    // retained; only the server-side calibrated foliage input changes.
    world.map=crate::map_profile091::MapId::from_asset("02_malinovka").unwrap();
    world.foliage=Some(Arc::new(super::super::foliage::test_fixture_at([100.,2.,0.],20.)));
    world.refresh_original_spotting(now+STEP).unwrap();
    assert!(!world.own_sightings(0).unwrap()[1]);
    // Existing server fire timestamp supplies the same five-second window
    // to both vehicle and foliage, without a client-provided fire claim.
    world.foliage=Some(Arc::new(super::super::foliage::test_fixture_at([195.,2.,0.],20.)));
    world.actors[1].camouflage_fired_at=Some(now+STEP);
    world.refresh_original_spotting(now+STEP*2).unwrap();
    assert!(world.own_sightings(0).unwrap()[1]);
    world.refresh_original_spotting(now+STEP*51).unwrap();
    assert!(!world.own_sightings(0).unwrap()[1],"fire window has elapsed");
    world.foliage=None;
    world.refresh_original_spotting(now+STEP*52).unwrap();
    assert!(world.own_sightings(0).unwrap()[1]);
}

#[test]
fn foliage_world_binding_refuses_wrong_map_missing_opt_in_and_large_roster() {
    let now=Instant::now();let foliage=Arc::new(super::super::foliage::test_fixture_at([0.;3],1.));
    let mut world=World::new_for_roster(717,now,crate::map_profile091::MapId::Karelia,2).unwrap();
    world.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).unwrap();
    world.bind_geometry(Arc::new(super::super::geometry::tests::is7_bundle())).unwrap();
    world.enable_ap_test_lab().unwrap();
    world.bind_terrain(Arc::new(super::super::terrain::tests::fixture(-500.,1000.,2,vec![-100.;4]))).unwrap();
    let mut rules=super::super::spotting::Rules::selected().unwrap();rules.camouflage=true;
    world.enable_original_spotting(rules).unwrap();
    assert!(world.enable_foliage(foliage.clone()).is_err());
    world.map=crate::map_profile091::MapId::from_asset("02_malinovka").unwrap();
    world.original_spotting.as_mut().unwrap().rules.camouflage=false;
    assert!(world.enable_foliage(foliage.clone()).is_err());
    world.original_spotting.as_mut().unwrap().rules.camouflage=true;world.expected_actors=7;
    assert!(world.enable_foliage(foliage.clone()).is_err());
    world.expected_actors=2;world.enable_foliage(foliage.clone()).unwrap();
    assert!(world.enable_foliage(foliage).is_err());
}

#[test]
fn foliage_world_crosses_bw_once_as_shared_immutable_resource() {
    use crate::bw_wire::{Arcs,encode,decode};
    let now=Instant::now();let mut world=fixture(now);
    world.map=crate::map_profile091::MapId::from_asset("02_malinovka").unwrap();
    world.original_spotting.as_mut().unwrap().rules.camouflage=true;
    world.foliage=Some(Arc::new(super::super::foliage::test_fixture_at([100.,2.,0.],20.)));
    let mut gateway=Arcs::new(false);let mut worker=Arcs::new(true);
    let first=encode(&world,now,&mut gateway).unwrap();
    assert!(first.len() < 256*1024*1024);
    let mut received:World=decode(&first,now,&mut worker).unwrap();
    received.refresh_original_spotting(now).unwrap();
    let back=encode(&received,now,&mut worker).unwrap();
    let returned:World=decode(&back,now,&mut gateway).unwrap();
    assert!(Arc::ptr_eq(world.foliage.as_ref().unwrap(),returned.foliage.as_ref().unwrap()));
    assert_eq!(returned.foliage.as_ref().unwrap().source_sha256,world.foliage.as_ref().unwrap().source_sha256);
}

#[cfg(feature="test_lab")]
#[test]
fn operator_trace_world_reports_actual_object_and_ground_hit_points() {
    let now=Instant::now();let mut world=fixture(now);
    {let rules=&mut world.original_spotting.as_mut().unwrap().rules;rules.camouflage=true;rules.diagnostics=true;rules.retention_ms=0;}
    let wall_a=[[50.,-100.,-100.],[50.,100.,-100.],[50.,100.,100.]];
    let wall_b=[[50.,-100.,-100.],[50.,100.,100.],[50.,-100.,100.]];
    world.terrain=Some(Arc::new(super::super::terrain::tests::fixture(-500.,1000.,2,vec![-100.;4])
        .with_obstacles(Arc::new(super::super::obstacles::tests::fixture(vec![wall_a,wall_b]))).unwrap()));
    world.refresh_original_spotting(now).unwrap();
    let scan_tick=world.tick;
    let scan_position=world.actors[0].position;
    world.tick+=1; world.actors[0].position[0]+=10.;
    let encoded=super::super::visibility_debug::snapshot(&world,"788fa1bf-8a21-4bdb-84de-a63310e390a3",0,1).unwrap().unwrap();
    let delayed:serde_json::Value=serde_json::from_slice(&encoded).unwrap();
    assert_eq!(delayed["tick"],scan_tick);
    assert_eq!(delayed["map"]["actors"][0]["position"],serde_json::json!(scan_position));
    let mut channel=super::super::visibility_debug::Channel::new([7;16]); channel.select((0,1));
    assert!(channel.publish(&world,"788fa1bf-8a21-4bdb-84de-a63310e390a3",&[b'x';43],now,16).unwrap().is_none());
    assert!(channel.publish(&world,"788fa1bf-8a21-4bdb-84de-a63310e390a3",&[b'x';43],now,0).unwrap().is_some());
    assert!(channel.publish(&world,"788fa1bf-8a21-4bdb-84de-a63310e390a3",&[b'x';43],now+Duration::from_secs(13),0).unwrap().is_none());
    let prior_id=world.id;world.id+=1;
    assert!(channel.publish(&world,"788fa1bf-8a21-4bdb-84de-a63310e390a3",&[b'x';43],now,0).unwrap().is_none());
    assert!(channel.pair().is_none());world.id=prior_id;
    world.actors[0].position=scan_position;
    let pairs=world.spotting_diagnostics().unwrap()["pairs"].as_array().unwrap();
    let pair=pairs.iter().find(|p|p["observer"]==0 && p["target"]==1).unwrap();
    assert_eq!(pair["rays"][0]["result"],"object");
    assert!((pair["rays"][0]["hit_point"][0].as_f64().unwrap()-50.).abs()<0.01);
    assert_eq!(pair["unchecked_ray_count"],0);
    world.terrain=Some(Arc::new(super::super::terrain::tests::fixture(-500.,1000.,2,vec![-1.;4])));
    world.actors[1].position[1]=-10.;
    world.refresh_original_spotting(now+STEP).unwrap();
    let pairs=world.spotting_diagnostics().unwrap()["pairs"].as_array().unwrap();
    let pair=pairs.iter().find(|p|p["observer"]==0 && p["target"]==1).unwrap();
    assert_eq!(pair["rays"][0]["result"],"terrain");
    assert!((pair["rays"][0]["hit_point"][1].as_f64().unwrap()+1.).abs()<0.01);
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

    // Adding a net must not change the pre-existing scope anchor/tolerance.
    // The scope stays armed for sub-threshold incremental hull turns while
    // the net immediately resets using its stricter movement classifier.
    let mut scope_only=world.actors[0].clone();let mut both=scope_only.clone();
    both.owned_v2.as_mut().unwrap().optional_devices[2]=super::super::camouflage::NET;
    both.camouflage_rest=Some((both.position,both.direction,at-Duration::from_secs(3),true));
    for step in 1..=6 {
        let when=at+STEP*step;
        for actor in [&mut scope_only,&mut both] {
            let (position,direction)=(actor.position,actor.direction);actor.direction[0]+=0.002;
            actor.update_camouflage_moving(position,direction);actor.update_stereoscope(when);actor.update_camouflage_net(when);
        }
        assert_eq!(scope_only.stereoscope_status(),both.stereoscope_status(),"step={step}");
        assert_eq!(both.camouflage_net_status(),Some(false),"step={step}");
        if step==1 {assert_eq!(both.stereoscope_status(),Some(true));}
    }
    assert_eq!(both.stereoscope_status(),Some(false),"scope keeps its original anchor threshold");

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

#[test]
fn content0_s5a_project_net_changes_actual_direct_spotting_and_resets_on_hull_turn() {
    use crate::{p06t_shells091 as shells, profile13_v2091 as v2};
    let start=Instant::now(); let kind=VehicleKind::Ms1;
    let mut world=World::new_for_roster(717,start,crate::map_profile091::MapId::Karelia,2).unwrap();
    world.enable_lifecycle(super::super::lifecycle::Rules{prebattle_ms:1000,..super::super::lifecycle::Rules::prohorovka()}).unwrap();
    world.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).unwrap();
    world.bind_geometry(Arc::new(super::super::geometry::tests::is7_bundle())).unwrap();
    world.enable_ap_test_lab().unwrap();
    world.bind_terrain(Arc::new(super::super::terrain::tests::fixture(-500.,1000.,2,vec![-100.;4]))).unwrap();
    let mut rules=super::super::spotting::Rules::selected().unwrap(); rules.camouflage=true;
    world.enable_original_spotting(rules).unwrap();world.enable_mixed_ammo().unwrap();
    for slot in 0..2 {
        let (owner,legacy)=super::tests::profile13_loadout(kind,slot,20);
        let profile=shells::profile(kind.mount());
        let ammunition=profile.shots.iter().zip(["ap","heat","he"]).enumerate().map(|(i,(shot,suffix))|
            serde_json::json!({"shell_definition_id":format!("shell:ms1-stock-{suffix}"),"shell_compact_id":shot.compact_descr,"family":shot.family.source_name(),"count":if i==0{20}else{0}})).collect::<Vec<_>>();
        let mut value=serde_json::json!({"kind":kind.label(),"descriptor_hex":kind.descriptor().iter().map(|b|format!("{b:02x}")).collect::<String>(),
            "native_inventory_id":1,"vehicle_inventory_id":legacy.vehicle_inventory_id,"max_hp":kind.max_health(),"crew_ids":legacy.crew_ids,
            "capacity":profile.capacity,"ammunition":ammunition,"initial_shell_compact_id":profile.shots[0].compact_descr});
        if slot==1 {value["artefacts"]=serde_json::json!({"optional_devices":[super::super::camouflage::NET,0,0],"consumables":[0,0,0]});}
        use sha2::Digest;
        let digest=format!("{:x}",sha2::Sha256::digest(serde_json::to_vec(&value).unwrap()));
        let frozen=v2::parse_frozen(&value,&owner.account,&digest).unwrap();
        if slot==1 {
            let mut without=world.clone();without.original_spotting.as_mut().unwrap().rules.camouflage=false;
            assert!(without.attach_owned_v2(owner.clone(),slot as u32+1,&frozen).is_err(),"net must fail closed on ordinary P07B");
        }
        world.attach_owned_v2(owner,slot as u32+1,&frozen).unwrap();
    }
    // Bind the settled initial hull poses before the clock starts. Otherwise
    // the first external frame teleports from the formation spawn and is a
    // real movement event that correctly postpones net arming by one tick.
    for slot in 0..2 {
        world.actors[slot].position=[slot as f32*200.,0.,0.];
        world.actors[slot].direction=[0.;3];world.actors[slot].yaw=0.;
    }
    world.start(start).unwrap();world.set_ready(0,1).unwrap();world.set_ready(1,2).unwrap();
    world.advance_lifecycle(start).unwrap();
    let mut rows=[(0,[0.;3],[0.;3],0.),(1,[200.,0.,0.],[0.;3],0.)];
    for tick in 1..=30 {
        let at=start+STEP*tick;world.advance_with_external(at,Some(&rows)).unwrap();world.advance_lifecycle(at).unwrap();world.refresh_original_spotting(at).unwrap();
        assert_eq!(world.actors[1].camouflage_net_status(),Some(false));
        assert!(world.own_sightings(0).unwrap()[1]);
    }
    let at=start+STEP*31;world.advance_with_external(at,Some(&rows)).unwrap();world.refresh_original_spotting(at).unwrap();
    assert_eq!(world.actors[1].camouflage_net_status(),Some(true));
    assert!(!world.own_sightings(0).unwrap()[1]);
    let shot=world.apply(1,2,&[Command::Fire(fire::Command::Shoot)],at).unwrap();
    assert!(matches!(shot.as_slice(),[fire::Outcome::Typed(crate::p06t_armament091::Outcome::Shot{..})]));
    let at=start+STEP*32;world.advance_with_external(at,Some(&rows)).unwrap();world.refresh_original_spotting(at).unwrap();
    assert!(world.own_sightings(0).unwrap()[1],"actual accepted shot reduces concealment");
    for tick in 33..=81 {world.advance_with_external(start+STEP*tick,Some(&rows)).unwrap();}
    let at=start+STEP*81;world.refresh_original_spotting(at).unwrap();
    assert!(!world.own_sightings(0).unwrap()[1],"fire calibration expires after 5 seconds");
    rows[1].2[0]=0.02;
    let at=start+STEP*82;world.advance_with_external(at,Some(&rows)).unwrap();world.refresh_original_spotting(at).unwrap();
    assert_eq!(world.actors[1].camouflage_net_status(),Some(false));
    assert!(world.own_sightings(0).unwrap()[1]);
    for tick in 83..=112 {world.advance_with_external(start+STEP*tick,Some(&rows)).unwrap();}
    let at=start+STEP*112;world.refresh_original_spotting(at).unwrap();
    assert_eq!(world.actors[1].camouflage_net_status(),Some(true));assert!(!world.own_sightings(0).unwrap()[1]);

    // Rotation that the movement classifier sees must reset the net on the
    // same committed step, not after accumulating the scope anchor's 0.01 rad.
    rows[1].2[0]+=0.002;
    let at=start+STEP*113;world.advance_with_external(at,Some(&rows)).unwrap();world.refresh_original_spotting(at).unwrap();
    assert!(world.actors[1].camouflage_moving);
    assert_eq!(world.actors[1].camouflage_net_status(),Some(false));assert!(world.own_sightings(0).unwrap()[1]);
    for tick in 114..=144 {world.advance_with_external(start+STEP*tick,Some(&rows)).unwrap();}
    assert_eq!(world.actors[1].camouflage_net_status(),Some(true));
    rows[1].1[0]+=0.006;
    let at=start+STEP*145;world.advance_with_external(at,Some(&rows)).unwrap();world.refresh_original_spotting(at).unwrap();
    assert!(world.actors[1].camouflage_moving);assert_eq!(world.actors[1].camouflage_net_status(),Some(false));

    // A disconnected target is still physical. Its classification follows
    // the worker pose both when parked and when pushed by another vehicle.
    world.detach(2).unwrap();
    let at=start+STEP*146;world.advance_with_external(at,Some(&rows)).unwrap();
    assert!(!world.actors[1].camouflage_moving);assert_eq!(world.actors[1].camouflage_net_status(),Some(false));
    rows[1].1[0]+=0.006;
    let at=start+STEP*147;world.advance_with_external(at,Some(&rows)).unwrap();
    assert!(world.actors[1].camouflage_moving);
    let at=start+STEP*148;world.advance_with_external(at,Some(&rows)).unwrap();
    assert!(!world.actors[1].camouflage_moving);
}

#[cfg(feature="test_lab")]
#[test]
fn visibility_debug_backpressure_reserves_gameplay_reliable_window() {
    let now=Instant::now();let mut world=fixture(now);
    {let rules=&mut world.original_spotting.as_mut().unwrap().rules;rules.camouflage=true;rules.diagnostics=true;}
    world.refresh_original_spotting(now).unwrap();
    let account="788fa1bf-8a21-4bdb-84de-a63310e390a3";
    let mut session=super::super::super::Session::new(1,[1;16],"127.0.0.1:30001".parse().unwrap(),now);
    session.identity=Some(Arc::new(crate::identity091::Profile{account_id:account.into(),database_id:1,name:"test".into(),fixture_dir:std::path::PathBuf::new()}));
    let mut client=super::super::Client::new(0);
    client.visibility_debug_owner=Some(account.into());client.visibility_debug_run=Some(account.into());client.visibility_debug_grant=Some(Arc::new(vec![b'x';43]));
    let mut channel=super::super::visibility_debug::Channel::new([7;16]);channel.select((0,1));client.visibility_debug=Some(channel);
    session.shared=Some(client);
    super::super::server::publish_visibility_debug(&mut session,&world,now);assert_eq!(session.tx.len(),1);
    // Even replacing a channel after a new hello cannot reset session pacing.
    let mut replacement=super::super::visibility_debug::Channel::new([7;16]);replacement.select((0,1));
    session.shared.as_mut().unwrap().visibility_debug=Some(replacement);
    for ms in [5,10,99] {super::super::server::publish_visibility_debug(&mut session,&world,now+Duration::from_millis(ms));assert_eq!(session.tx.len(),1);}
    super::super::server::publish_visibility_debug(&mut session,&world,now+Duration::from_millis(100));assert_eq!(session.tx.len(),2);
    super::super::server::publish_visibility_debug(&mut session,&world,now+Duration::from_millis(200));assert_eq!(session.tx.len(),3);
    for ms in [300,500,1000] {super::super::server::publish_visibility_debug(&mut session,&world,now+Duration::from_millis(ms));assert_eq!(session.tx.len(),3);}
    // No ACKs: all five reserved reliable slots remain available to gameplay.
    for _ in 0..5 {session.tx.enqueue_body(b"gameplay").unwrap();}
    assert_eq!(session.tx.len(),8);
    super::super::server::publish_visibility_debug(&mut session,&world,now+Duration::from_millis(1200));assert_eq!(session.tx.len(),8);
}
