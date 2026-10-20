//! Candidate integration tests: NOT_RUN until root promotes the P10B branch.
//! Existing cfg(test) old source loadouts are authored fixtures, not new owned
//! acquisition. Actual source geometry/World commands prove their own boundary.
use super::*;
use super::super::{p10b_team_plan::TeamPlan,lifecycle,lifecycle_result,lifecycle_wire,wire};

fn fixture(teams:&[u8],now:Instant)->World {
    let mut world=World::new_for_roster(31001,now,crate::map_profile091::MapId::Karelia,teams.len()).unwrap();
    let mut rules=lifecycle::Rules::prohorovka();rules.prebattle_ms=1000;
    world.enable_lifecycle(rules).unwrap();world.set_team_plan(TeamPlan::new(teams).unwrap()).unwrap();
    world.terrain=Some(Arc::new(super::super::terrain::tests::fixture(-1000.,2000.,2,vec![-100.;4])));
    for slot in 0..teams.len(){let(identity,loadout)=tests::profile13_loadout(VehicleKind::Ms1,slot,7);
        assert_eq!(world.attach_owned(identity,slot as u32+1,&loadout).unwrap(),slot);
        world.actors[slot].position=[slot as f32*20.,0.,0.];world.actors[slot].origin=world.actors[slot].position;
    }world
}
fn begin(world:&mut World,now:Instant){
    world.start(now).unwrap();for slot in 0..world.actors.len(){world.set_ready(slot,slot as u32+1).unwrap();}
    world.advance_lifecycle(now).unwrap();for step in 1..=10 {world.advance_lifecycle(now+STEP*step).unwrap();world.advance(now+STEP*step).unwrap();}
    assert!(world.lifecycle.as_ref().unwrap().allows_actions());
}

#[test]fn p10b_team_setter_is_atomic_once_and_requires_empty_lifecycle_roster(){
    assert_eq!(MAX_ACTORS,super::super::p10b_team_plan::MAX_ACTORS);
    let now=Instant::now();let mut world=World::new_for_roster(31002,now,crate::map_profile091::MapId::Karelia,4).unwrap();
    let plan=TeamPlan::new(&[1,1,1,2]).unwrap();assert!(world.set_team_plan(plan.clone()).is_err());assert!(world.team_plan().is_none());
    world.enable_lifecycle(lifecycle::Rules::prohorovka()).unwrap();assert!(world.set_team_plan(TeamPlan::new(&[1,2]).unwrap()).is_err());
    assert!(world.team_plan().is_none());world.set_team_plan(plan.clone()).unwrap();assert_eq!(world.team_plan(),Some(&plan));
    assert!(world.set_team_plan(TeamPlan::new(&[2,2,2,1]).unwrap()).is_err());assert_eq!(world.team_plan(),Some(&plan));
    assert!(world.set_expected_actors(6).is_err());assert_eq!(world.expected_actors(),4);
    let mut joined=World::new_for_roster(31003,now,crate::map_profile091::MapId::Karelia,4).unwrap();joined.enable_lifecycle(lifecycle::Rules::prohorovka()).unwrap();
    let(identity,loadout)=tests::profile13_loadout(VehicleKind::Ms1,0,7);joined.attach_owned(identity,1,&loadout).unwrap();
    assert!(joined.set_team_plan(plan).is_err());assert!(joined.team_plan().is_none());
}

#[test]fn p10b_absent_team_plan_preserves_old_allied_and_lifecycle_parity_behaviour(){
    let now=Instant::now();for active in [false,true]{
        let mut world=World::new_for_roster(31004,now,crate::map_profile091::MapId::Karelia,6).unwrap();
        if active{world.enable_lifecycle(lifecycle::Rules::prohorovka()).unwrap();}
        for slot in 0..6{let(identity,loadout)=tests::profile13_loadout(VehicleKind::Ms1,slot,7);world.attach_owned(identity,slot as u32+1,&loadout).unwrap();}
        assert!(world.team_plan().is_none());for slot in 0..6{assert_eq!(world.team(slot).unwrap(),if active{slot as u8%2+1}else{1});assert_eq!(world.spawn_lane(slot).unwrap(),slot);}
    }
}

#[test]fn p10b_three_one_and_one_three_visibility_and_native_rows_follow_actual_teams(){
    for teams in [[1,1,1,2],[1,2,2,2]]{
        let mut world=fixture(&teams,Instant::now());
        for(slot,actor)in world.actors.iter_mut().enumerate(){actor.position=[slot as f32*300.,0.,0.];actor.origin=actor.position;}
        for slot in 0..4{
            assert_eq!(world.team(slot).unwrap(),teams[slot]);let view=world.desired_visibility(slot).unwrap();
            for target in 0..4{assert_eq!(view[target],slot==target||teams[slot]==teams[target]);}
            let packet=wire::roster_updates(&world,slot).unwrap();assert_eq!(packet[3],11);
            let name=world.actors[slot].identity.name.as_bytes();let at=packet.windows(name.len()).position(|w|w==name).unwrap()+name.len();
            assert_eq!(&packet[at..at+2],&[b'K',teams[slot]]);
            let parts=wire::announcement_parts(&world,slot).unwrap();assert_eq!(parts[0][39],teams[slot]);
        }
    }
}

#[test]fn p10b_whole_side_departure_results_keep_frozen_roster_identity_and_teams(){
    for(teams,last,winner)in[([1,1,1,2],3,1),([1,2,2,2],0,2)]{
        let now=Instant::now();let mut world=fixture(&teams,now);world.lifecycle_created_unix=Some(1792080000);
        let identities=world.actors.iter().map(|a|a.identity.clone()).collect::<Vec<_>>();
        world.start(now).unwrap();world.advance_lifecycle(now).unwrap();world.detach(last as u32+1).unwrap();
        world.advance_lifecycle(now+STEP).unwrap();let result=lifecycle_result::build(&world).unwrap();
        assert_eq!(result.winner_team,winner);assert_eq!(result.participants.iter().map(|a|a.team).collect::<Vec<_>>(),teams);
        assert_eq!(result.participants.iter().map(|a|a.account_dbid).collect::<Vec<_>>(),identities.iter().map(|i|i.database).collect::<Vec<_>>());
        assert!(result.participants[last].premature_leave);assert_eq!(result.participants[last].health,90);
        assert_eq!(world.team_plan().unwrap().teams(),teams);
        for owner in identities{assert!(!lifecycle_wire::avatar_result_stream(&result,owner.database).unwrap().is_empty());}
    }
}

#[test]fn p10b_actual_source_mesh_shot_preserves_identity_slot_and_team_plan_in_World_Trace(){
    let now=Instant::now();let mut world=fixture(&[1,1,1,2],now);
    let bundle=Arc::new(super::super::geometry::tests::bundle());world.bind_geometry(bundle.clone()).unwrap();
    world.bind_geometry(Arc::new(super::super::geometry::tests::is7_bundle())).unwrap();world.enable_ap_test_lab().unwrap();
    world.actors[0].position=[0.,0.,0.];world.actors[1].position=[400.,0.,0.];world.actors[2].position=[450.,0.,0.];world.actors[3].position=[0.,0.,20.];
    for actor in &mut world.actors{actor.origin=actor.position;}
    begin(&mut world,now);let plan=world.team_plan().cloned().unwrap();
    let hit=bundle.explosion_contact(&world.actors[3],[0.,1.,5.],16.,1,3,world.tick).unwrap().unwrap();
    let at=now+Duration::from_secs(1);world.apply(0,1,&[Command::Aim(aim::Intent::Point(hit.endpoint))],at).unwrap();
    for step in 1..=20{world.advance(at+STEP*step).unwrap();}
    let at=at+Duration::from_secs(2);let accepted=world.apply(0,1,&[Command::Fire(fire::Command::Shoot)],at).unwrap();
    assert!(matches!(accepted.as_slice(),[fire::Outcome::AcceptedShot{..}]));world.advance(at+STEP).unwrap();
    assert_eq!(world.shots.len(),1);assert_eq!(world.shots[0].slot,0);assert_eq!(world.contacts.len(),1);assert_eq!(world.contacts[0].target_slot,3);
    assert!(world.impact.events().len()>3);assert_eq!(world.team_plan(),Some(&plan));assert_eq!(world.team(3).unwrap(),2);
    assert_eq!(world.actors[0].fire.ammo(),6);assert_eq!(world.actors.len(),4);
}
