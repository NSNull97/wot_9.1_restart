//! Results from the one authoritative damage/death journal, including fire and
//! positive-hull-HP crew loss. No client outcome or invented HP0 is accepted.
use super::*;
pub(super) fn build(world:&World)->io::Result<Results>{
    let state=world.lifecycle.as_ref().ok_or_else(||model::bad())?;
    let outcome=state.outcome().ok_or_else(||model::bad())?;
    let duration_seconds=u32::try_from(state.elapsed_battle_ms()/1000).map_err(|_|model::bad())?;
    let mut participants=Vec::with_capacity(world.actors.len());
    for(slot,actor)in world.actors.iter().enumerate(){
        let death=world.damage_events.iter().find(|event|event.target==slot&&event.lethal());
        if actor.alive()!=death.is_none(){return Err(model::bad());}
        let damage_dealt=world.damage_events.iter().filter(|event|event.attacker==slot)
            .map(|event|u32::from((event.health_before-event.health_after).max(0)as u16)).sum();
        let damage_received=world.damage_events.iter().filter(|event|event.target==slot)
            .map(|event|u32::from((event.health_before-event.health_after).max(0)as u16)).sum();
        let life_time=death.map_or(duration_seconds,|event|{
            let elapsed=u64::from(event.tick.saturating_sub(1000))*100;
            (elapsed.saturating_sub(state.battle_start_ms().unwrap_or(elapsed))/1000).min(u64::from(duration_seconds))as u32});
        participants.push(Participant{vehicle_id:wire::vehicle_id(slot)?,account_dbid:actor.identity.database,
            name:actor.identity.name.clone(),team:world.team(slot)?,type_compact_descr:actor.vehicle_kind().vehicle_compact_id(),
            health:actor.health,shots:actor.fire.accepted_shots().try_into().map_err(|_|model::bad())?,
            direct_hits:world.contacts.iter().filter(|contact|world.shots.iter().any(|shot|shot.sequence==contact.shot&&shot.slot==slot)).count().try_into().map_err(|_|model::bad())?,
            piercings:world.impacts.iter().filter(|event|event.attacker==slot&&matches!(&event.outcome,
                ImpactOutcome::Mixed(result)if result.decision==crate::p06t_damage::Decision::Pierced)).count().try_into().map_err(|_|model::bad())?,
            damage_dealt,damage_received,kills:world.damage_events.iter().filter(|event|event.attacker==slot&&event.lethal()).count().try_into().map_err(|_|model::bad())?,
            capture_points:state.capture_points(slot),dropped_capture_points:state.dropped_capture_points(slot),
            mileage_metres:actor.mileage_metres.floor()as u32,life_time,killer_id:death.map(|event|wire::vehicle_id(event.attacker)).transpose()?.unwrap_or(0),
            death_reason:death.map_or(-1,|event|event.reason as i8),premature_leave:actor.session.is_none()});
    }
    let result=Results{arena_id:world.id,arena_type_id:world.map.arena_type_id()as i32,
        created_unix:world.lifecycle_created_unix.ok_or_else(||model::bad())?,winner_team:outcome.winner,
        finish_reason:wire::finish_reason(outcome.reason),duration_seconds,interaction_details:Some(project_details(world,&participants)?),participants};
    result.validate_p06t()?;Ok(result)
}
