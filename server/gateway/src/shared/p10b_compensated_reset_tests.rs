//! Authored pristine-reset component tests only. No ReadyRef, reservation,
//! ownership or durable completion is fabricated. Actual SQL regression09 is
//! required separately for AllReleased -> fresh room/admissions composition.
use super::*;
fn pristine(id:u64,now:Instant)->World{World::new_for_roster(id,now,MapId::Prohorovka,6).unwrap()}
#[test]
fn p10b_compensated_reset_stages_monotonic_id_fresh_tick_without_live_mutation(){
    let start=Instant::now();let mut world=pristine(911,start);let template=BattleTemplate::new(&world,&None);let mut runtime=None;
    let later=start+Duration::from_secs(7);let staged=CompensatedReset::stage(&world,&runtime,&template,room::BattleKey(911),later).unwrap();
    assert_eq!(world.id,911);assert_eq!(staged.world.id,912);assert_eq!(staged.world.tick,1000);
    assert_eq!(staged.world.expected_actors(),6);assert!(staged.world.actors.is_empty()&&staged.world.started.is_none());
    staged.commit(&mut world,&mut runtime);assert_eq!(world.id,912);assert_eq!(world.tick,1000);assert!(runtime.is_none());
    let next=CompensatedReset::stage(&world,&runtime,&template,room::BattleKey(912),later).unwrap();assert_eq!(next.world.id,913);
}
#[test]
fn p10b_compensated_reset_rejects_stale_battle_and_started_world_before_any_swap(){
    let now=Instant::now();let world=pristine(921,now);let template=BattleTemplate::new(&world,&None);
    assert!(CompensatedReset::stage(&world,&None,&template,room::BattleKey(922),now).is_err());assert_eq!(world.id,921);
    let mut live=world.clone();live.started=Some(now);
    assert!(CompensatedReset::stage(&live,&None,&template,room::BattleKey(921),now).is_err());assert_eq!(live.started,Some(now));
    let mut corrupt_template=BattleTemplate::new(&world,&None);corrupt_template.world.started=Some(now);
    assert!(CompensatedReset::stage(&world,&None,&corrupt_template,room::BattleKey(921),now).is_err());
    // Existing strict same-id source guard remains intact, even for a caller
    // that supplied a wrongly future-dated template.
    let future=BattleTemplate::new(&pristine(922,now),&None);
    assert!(CompensatedReset::stage(&world,&None,&future,room::BattleKey(921),now).is_err());assert_eq!(world.id,921);
}
#[test]
fn p10b_compensated_reset_overflow_and_attached_actor_leave_old_key_intact(){
    let now=Instant::now();let mut world=pristine(u64::MAX,now);let template=BattleTemplate::new(&world,&None);
    assert!(CompensatedReset::stage(&world,&None,&template,room::BattleKey(u64::MAX),now).is_err());assert_eq!(world.id,u64::MAX);
    let boundary=pristine(i64::MAX as u64,now);let boundary_template=BattleTemplate::new(&boundary,&None);
    assert!(CompensatedReset::stage(&boundary,&None,&boundary_template,room::BattleKey(boundary.id),now).is_err());
    world=pristine(931,now);let template=BattleTemplate::new(&world,&None);
    // Authored legacy-lab actor only, not owned authority or an admitted ref.
    world.attach(model::Identity{account:"AUTHORED-reset-guard".into(),database:1,name:"Reset guard".into()},77).unwrap();
    assert!(CompensatedReset::stage(&world,&None,&template,room::BattleKey(931),now).is_err());assert_eq!(world.id,931);assert_eq!(world.actors.len(),1);
}
