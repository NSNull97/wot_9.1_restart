//! Actual source-capacity domain admissions; not an owned inventory grant.
use super::*;

#[test] fn p04m_six_t26_full_source_capacity_commits_960_shots_without_truncation() {
    let now=Instant::now();let kind=VehicleKind::T26;
    assert_eq!(kind.ammo_limit(),160);
    let mut world=World::new_for_vehicle(404,now,crate::map_profile091::MapId::Prohorovka,kind).unwrap();
    world.set_expected_actors(6).unwrap();
    for slot in 0..6 {
        world.attach(Identity{account:format!("explicit-lab-t26-{slot}"),database:slot as i32+1,name:format!("lab-{slot}")},slot as u32+1).unwrap();
        world.actors[slot].fire=fire::State::with_mounted_loadout(160,kind.reload_seconds(),kind.ammo_limit()).unwrap();
    }
    world.start(now).unwrap();for slot in 0..6 {world.set_ready(slot,slot as u32+1).unwrap();}
    assert_eq!(world.shot_limit(),960);assert_eq!(6*MAX_AMMO_PER_ACTOR,960);
    for round in 0..160 {
        let at=now+Duration::from_secs_f64(round as f64*(kind.reload_seconds() as f64+0.1));
        for slot in 0..6 {
            let outcome=world.apply(slot,slot as u32+1,&[Command::Fire(fire::Command::Shoot)],at).unwrap();
            assert_eq!(outcome,vec![fire::Outcome::AcceptedShot{ammo_remaining:159-round as u16}]);
        }
    }
    assert_eq!(world.latest_shot(),960);assert_eq!(world.projectiles.len(),960);
    assert_eq!(world.impact.events().len(),1920);
    let after=now+Duration::from_secs(1000);
    for slot in 0..6 {assert_eq!(world.apply(slot,slot as u32+1,&[Command::Fire(fire::Command::Shoot)],after).unwrap(),vec![fire::Outcome::RejectedNoAmmo]);}
    assert_eq!(world.latest_shot(),960);
    assert!(Projectile::launch_for_limit(961,5,&world.actors[5],after,world.shot_limit()).is_err());
}

#[test] fn p04m_mounted_fire_capacity_does_not_expand_legacy_loadout_contract() {
    assert!(fire::State::with_loadout(97,2.5).is_err());
    for (ammo,capacity)in [(0,160),(161,160),(160,159),(1,161)] {
        assert!(fire::State::with_mounted_loadout(ammo,2.5,capacity).is_err());
    }
    assert_eq!(fire::State::with_mounted_loadout(160,2.5,160).unwrap().ammo(),160);
    let now=Instant::now();let mut legacy=World::new_for_roster(405,now,crate::map_profile091::MapId::Prohorovka,6).unwrap();
    for slot in 0..6 {legacy.attach(Identity{account:format!("old-{slot}"),database:slot+1,name:format!("old-{slot}")},slot as u32+1).unwrap();}
    assert_eq!(legacy.shot_limit(),576);
}

#[test] fn p04m_fragile_budget_requires_capacity_binding_before_any_event() {
    let catalog=super::super::fragiles::tests::catalog();
    let object=&catalog.objects[0];
    let hit=terrain::Hit{surface:terrain::Surface::StaticObstacle{instance_id:object.instance_id,material_kind:object.material_kind},
        triangle_id:object.projectile_first_triangle,t:0.5,point:[0.;3],normal:[1.,0.,0.]};
    let mut state=fragiles::State::new(catalog.clone());state.configure_roster(6).unwrap();
    assert!(state.contact_for(VehicleKind::T26,960,0,1000,hit).is_err());assert!(state.events.is_empty());
    assert!(state.bind_ammo_capacity(161).is_err());state.bind_ammo_capacity(160).unwrap();
    assert!(state.contact_for(VehicleKind::T26,960,0,1000,hit).unwrap().is_some());
    assert_eq!(state.events[0].shot,960);assert!(state.contact_for(VehicleKind::T26,961,0,1001,hit).is_err());
    let mut late=fragiles::State::new(catalog);late.configure_roster(6).unwrap();
    assert!(late.contact_for(VehicleKind::Ms1,1,0,1000,hit).unwrap().is_some());
    assert!(late.bind_ammo_capacity(160).is_err());
}
