//! Projection of a committed world into the pinned native results DTO.
use std::io;
use super::{model::{self,World,ImpactOutcome},ap,lifecycle_wire::{Results,Participant},wire};

pub(super) fn build(world:&World)->io::Result<Results> {
    if world.mixed_ammo(){return p06t::build(world);}
    let state=world.lifecycle.as_ref().ok_or_else(||model::bad())?;
    let outcome=state.outcome().ok_or_else(||model::bad())?;
    let duration_seconds=u32::try_from(state.elapsed_battle_ms()/1_000).map_err(|_|model::bad())?;
    let mut participants=Vec::with_capacity(world.actors.len());
    for (slot,actor) in world.actors.iter().enumerate() {
        let damage_dealt=world.impacts.iter().filter(|i|i.attacker==slot).map(|i|u32::from((i.health_before-i.health_after).max(0) as u16)).sum();
        let damage_received=world.impacts.iter().filter(|i|i.target==slot).map(|i|u32::from((i.health_before-i.health_after).max(0) as u16)).sum();
        let death=world.impacts.iter().find(|i|i.target==slot && i.health_before>0 && i.health_after==0);
        let life_time=death.map_or(duration_seconds,|i| {
            let elapsed=u64::from(i.tick.saturating_sub(1_000))*100;
            (elapsed.saturating_sub(state.battle_start_ms().unwrap_or(elapsed))/1_000).min(u64::from(duration_seconds)) as u32
        });
        let result=Participant {vehicle_id:wire::vehicle_id(slot)?,account_dbid:actor.identity.database,
            name:actor.identity.name.clone(),team:world.team(slot)?,type_compact_descr:actor.vehicle_kind().vehicle_compact_id(),
            health:actor.health,shots:actor.fire.accepted_shots().try_into().map_err(|_|model::bad())?,
            direct_hits:world.contacts.iter().filter(|i|world.shots.iter().any(|s|s.sequence==i.shot && s.slot==slot)).count().try_into().map_err(|_|model::bad())?,
            piercings:world.impacts.iter().filter(|i|i.attacker==slot && matches!(&i.outcome,ImpactOutcome::Ap(r) if r.outcome==ap::Outcome::Pierced)).count().try_into().map_err(|_|model::bad())?,
            damage_dealt,damage_received,
            kills:world.impacts.iter().filter(|i|i.attacker==slot && i.health_before>0 && i.health_after==0).count().try_into().map_err(|_|model::bad())?,
            capture_points:state.capture_points(slot),dropped_capture_points:state.dropped_capture_points(slot),
            mileage_metres:actor.mileage_metres.floor() as u32,life_time,
            killer_id:death.map(|i|wire::vehicle_id(i.attacker)).transpose()?.unwrap_or(0),
            death_reason:if actor.health==0 {0} else {-1},premature_leave:actor.session.is_none(),
        };
        participants.push(result);
    }
    let result=Results {arena_id:world.id,arena_type_id:world.map.arena_type_id() as i32,
        created_unix:world.lifecycle_created_unix.ok_or_else(||model::bad())?,winner_team:outcome.winner,
        finish_reason:wire::finish_reason(outcome.reason),duration_seconds,participants};
    result.validate()?;Ok(result)
}
#[path="p06t_lifecycle_result.rs"]
mod p06t;

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{Duration,Instant};
    #[test] fn natural_terminal_binds_each_real_actor_database_id_with_different_hp() {
        use crate::battle091::profile13::{Reservation,ReservationStatus,FinishReason,Request};
        use crate::gateway091::shared::{profile13_session::Terminal,vehicle_profile::VehicleKind};
        let now=Instant::now();let mut w=World::new(123,now).unwrap();
        w.enable_lifecycle(super::super::lifecycle::Rules::prohorovka()).unwrap();
        let mut loadouts=Vec::new();
        for slot in 0..2 {let(mut identity,loadout)=model::tests::profile13_loadout(VehicleKind::Ms1,slot,14);
            identity.database=slot as i32+1;w.attach_owned(identity,slot as u32+1,&loadout).unwrap();loadouts.push(loadout);}
        w.start(now).unwrap();w.lifecycle_created_unix=Some(1792080000);w.advance_lifecycle(now).unwrap();
        w.actors[0].health=23;w.actors[1].health=83;w.detach(1).unwrap();w.advance_lifecycle(now+Duration::from_millis(100)).unwrap();
        let result=build(&w).unwrap();let frozen=loadouts.pop().unwrap();
        let reservation=Reservation {reservation_id:"p08c:test:B".into(),run_id:"87654321-4321-4321-8321-cba987654321".into(),
            battle:123,native_inventory_id:1,vehicle_inventory_id:frozen.vehicle_inventory_id.clone(),status:ReservationStatus::Active,
            frozen,result:None};
        let terminal=Terminal::from_actor_result(&reservation,&w,1,2,FinishReason::BattleFinished,Some(&result)).unwrap();
        assert_eq!(terminal.native_database_id,2);assert_eq!(terminal.terminal_hp,83);
        assert!(matches!(terminal.request(),Request::FinishResults{terminal_hp:83,..}));
    }
    #[test] fn frozen_snapshot_uses_actual_hp_ammo_and_explicit_technical_forfeit() {
        let now=Instant::now();let mut w=World::new(123,now).unwrap();
        w.enable_lifecycle(super::super::lifecycle::Rules::prohorovka()).unwrap();
        for slot in 0..2 {let (identity,loadout)=model::tests::profile13_loadout(super::super::vehicle_profile::VehicleKind::Ms1,slot,14);
            w.attach_owned(identity,slot as u32+1,&loadout).unwrap();}
        w.start(now).unwrap();w.lifecycle_created_unix=Some(1792080000);w.advance_lifecycle(now).unwrap();
        w.detach(2).unwrap();w.advance_lifecycle(now+Duration::from_millis(100)).unwrap();
        let r=build(&w).unwrap();assert_eq!(r.winner_team,1);assert_eq!(r.finish_reason,5);
        assert_eq!(r.duration_seconds,0);assert_eq!(r.participants[0].health,90);
        assert_eq!(r.participants[0].shots,0);assert!(r.participants[1].premature_leave);
        assert_eq!(r.participants[1].death_reason,-1);
    }
}
