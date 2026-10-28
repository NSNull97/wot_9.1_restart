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
        let(ram_dealt,ram_received,ram_kills)=ram_totals(world,slot)?;
        let damage_dealt=world.impacts.iter().filter(|i|i.attacker==slot).map(|i|u32::from((i.health_before-i.health_after).max(0) as u16)).sum::<u32>()
            .checked_add(ram_dealt).ok_or_else(||model::bad())?;
        let damage_received=world.impacts.iter().filter(|i|i.target==slot).map(|i|u32::from((i.health_before-i.health_after).max(0) as u16)).sum::<u32>()
            .checked_add(ram_received).ok_or_else(||model::bad())?;
        let death=world.death_cause(slot)?;
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
            kills:u8::try_from(world.impacts.iter().filter(|i|i.attacker==slot && i.health_before>0 && i.health_after==0).count())
                .map_err(|_|model::bad())?.checked_add(ram_kills).ok_or_else(||model::bad())?,
            capture_points:state.capture_points(slot),dropped_capture_points:state.dropped_capture_points(slot),
            mileage_metres:actor.mileage_metres.floor() as u32,life_time,
            killer_id:death.map(|i|wire::vehicle_id(i.attacker)).transpose()?.unwrap_or(0),
            death_reason:death.map_or(-1,|i|i.reason as i8),premature_leave:actor.session.is_none(),
        };
        participants.push(result);
    }
    let result=Results {arena_id:world.id,arena_type_id:world.map.arena_type_id() as i32,
        created_unix:world.lifecycle_created_unix.ok_or_else(||model::bad())?,winner_team:outcome.winner,
        finish_reason:wire::finish_reason(outcome.reason),duration_seconds,interaction_details:Some(project_details(world,&participants)?),participants};
    result.validate()?;Ok(result)
}
/// Contact HP is independent of accepted shots and direct-hit statistics.
/// Count the strict committed HP delta; the policy's requested damage may be
/// capped by the victim's remaining health and is not a results statistic.
fn ram_totals(world:&World,slot:usize)->io::Result<(u32,u32,u8)>{
    let(mut dealt,mut received,mut kills)=(0u32,0u32,0u8);
    for event in &world.ram_damage_events{
        if event.attacker>=world.actors.len()||event.target>=world.actors.len()
            ||event.attacker==event.target||event.sequence==0||event.domain_tick<1000
            ||event.health_before<=0||event.health_before>world.actors[event.target].vehicle_kind().max_health()
            ||event.health_after<0||event.health_after>=event.health_before{return Err(model::bad());}
        let damage=(event.health_before-event.health_after)as u32;
        if event.attacker==slot{
            dealt=dealt.checked_add(damage).ok_or_else(||model::bad())?;
            if event.health_after==0{kills=kills.checked_add(1).ok_or_else(||model::bad())?;}
        }
        if event.target==slot{received=received.checked_add(damage).ok_or_else(||model::bad())?;}
    }
    Ok((dealt,received,kills))
}
// Presentation consumes committed journals only. No simulation/terminal edits.
pub(crate) fn project_module_facts(world:&World)->io::Result<Vec<super::lifecycle_details::Module>>{
    use super::lifecycle_details as d;
    let mut facts=Vec::new();
    for (target,event) in &world.device_events {
        let (extra_index,critical,fire)=match event.change {
            crate::p06t_device_state::Change::Device{device,extra_index,before_condition,after_condition,..}=>
                if extra_index!=device.extra(){return Err(model::bad());}
                else {(extra_index,before_condition!=after_condition&&!event.from_fire,false)},
            crate::p06t_device_state::Change::Crew{extra_index,before_active:true,after_active:false,..}=> (extra_index,true,false),
            crate::p06t_device_state::Change::Fire{before_active:false,after_active:true,..}=>(4,false,true),
            _=>(0,false,false),
        };
        if critical||fire {facts.push(d::Module{attacker:usize::from(event.cause.attacker_slot),target:*target,extra_index,critical,fire});}
    }
    Ok(facts)
}
fn project_details(world:&World,participants:&[Participant])->io::Result<super::lifecycle_details::Details>{
    use super::lifecycle_details as d;
    let roster=super::lifecycle_wire::summaries(participants);
    let shots=world.shots.iter().map(|s|d::Shot{id:s.sequence,attacker:s.slot}).collect::<Vec<_>>();
    let hits=world.contacts.iter().map(|c|d::Hit{shot:c.shot,target:c.target_slot}).collect::<Vec<_>>();
    let pierced=world.impacts.iter().filter(|i|matches!(&i.outcome,
        ImpactOutcome::Ap(r)if r.outcome==ap::Outcome::Pierced)||matches!(&i.outcome,
        ImpactOutcome::Mixed(r)if r.decision==crate::p06t_damage::Decision::Pierced))
        .map(|i|d::Hit{shot:i.shot,target:i.target}).collect::<Vec<_>>();
    let damage=if world.mixed_ammo(){world.damage_events.iter().map(|e|d::TimedDamage{tick:e.tick,damage:d::Damage{sequence:e.sequence,
        shot:e.shot,attacker:e.attacker,target:e.target,health_before:e.health_before,health_after:e.health_after,
        lethal:e.lethal(),reason:e.reason}}).collect::<Vec<_>>()}else{
        world.impacts.iter().enumerate().filter(|(_,i)|i.health_before!=i.health_after).map(|(n,i)|d::TimedDamage{tick:i.tick,damage:d::Damage{
            sequence:n as u32+1,shot:i.shot,attacker:i.attacker,target:i.target,health_before:i.health_before,
            health_after:i.health_after,lethal:i.health_before>0&&i.health_after==0,reason:0}}).collect::<Vec<_>>()};
    let ram=world.ram_damage_events.iter().map(|e|d::RamDamage{sequence:e.sequence,tick:e.domain_tick,
        attacker:e.attacker,target:e.target,health_before:e.health_before,health_after:e.health_after}).collect::<Vec<_>>();
    let splash=world.impact.events().iter().filter_map(|e|match e{super::impact::Event::SplashResolution{
        shot_id,target,terrain_blocker,..}=>Some(d::Splash{shot:*shot_id,target:*target,clear_los:terrain_blocker.is_none()}),_=>None}).collect::<Vec<_>>();
    let spots=world.result_spots().map(|rows|rows.iter().map(|s|d::Spot{observer:s.observer(),target:s.target(),tick:s.tick()}).collect::<Vec<_>>());
    let modules=project_module_facts(world)?;
    let mut details=d::project_with_ram(&roster,&shots,&hits,&pierced,&damage,&ram,&splash,spots.as_deref())?;
    d::apply_module_facts(&mut details,&roster,&modules)?;
    Ok(details)
}

#[path="p06t_lifecycle_result.rs"]
mod p06t;

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{Duration,Instant};
    fn roster()->Vec<super::super::lifecycle_details::Summary>{vec![
        super::super::lifecycle_details::Summary{vehicle_id:10,team:1,direct_hits:1,piercings:1,damage_dealt:90,damage_received:0,kills:1,killer_id:0,death_reason:-1},
        super::super::lifecycle_details::Summary{vehicle_id:20,team:2,direct_hits:0,piercings:0,damage_dealt:0,damage_received:90,kills:0,killer_id:10,death_reason:0},
    ]}
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
    /// RES-30: one owner (slot 0) + 29 synthetic BOT-01-shaped database ids in
    /// an actual 30-actor World; the whole other team leaves (forfeit).
    #[test] fn res30_thirty_actor_world_builds_results_and_owner_terminal() {
        use crate::battle091::profile13::{Reservation,ReservationStatus,FinishReason,Request,Context,encode_request};
        use crate::gateway091::shared::{profile13_session::Terminal,vehicle_profile::VehicleKind,lifecycle_wire};
        let now=Instant::now();let n=super::super::model::MAX_ACTORS;
        let mut w=World::new_for_roster(123,now,crate::map_profile091::MapId::Prohorovka,n).unwrap();
        w.enable_lifecycle(super::super::lifecycle::Rules::prohorovka()).unwrap();
        let mut owner_loadout=None;
        for slot in 0..n {let(mut identity,loadout)=model::tests::profile13_loadout(VehicleKind::Ms1,slot,14);
            identity.database=if slot==0{1}else{0x7F00_0000+slot as i32};w.attach_owned(identity,slot as u32+1,&loadout).unwrap();
            if slot==0{owner_loadout=Some(loadout);}}
        w.start(now).unwrap();w.lifecycle_created_unix=Some(1792080000);w.advance_lifecycle(now).unwrap();
        w.actors[0].health=23;let enemy=(0..n).filter(|s|w.team(*s).unwrap()!=w.team(0).unwrap()).collect::<Vec<_>>();
        assert_eq!(enemy.len(),15);for slot in enemy{w.detach(slot as u32+1).unwrap();}
        w.advance_lifecycle(now+Duration::from_millis(100)).unwrap();
        let result=build(&w).unwrap();assert_eq!(result.participants.len(),30);assert_eq!(result.winner_team,w.team(0).unwrap());
        assert_eq!(result.interaction_details.as_ref().unwrap().rows.len(),30);
        let raw=serde_json::to_string(&result).unwrap();assert!(raw.len()<=lifecycle_wire::result_json_budget(30));
        assert!(lifecycle_wire::compact_results(&result,1).unwrap().len()<=lifecycle_wire::MAX_RESULT_BYTES);
        let frozen=owner_loadout.unwrap();
        let reservation=Reservation {reservation_id:"p08c:test:A".into(),run_id:"87654321-4321-4321-8321-cba987654321".into(),
            battle:123,native_inventory_id:1,vehicle_inventory_id:frozen.vehicle_inventory_id.clone(),status:ReservationStatus::Active,
            frozen,result:None};
        let terminal=Terminal::from_actor_result(&reservation,&w,0,1,FinishReason::BattleFinished,Some(&result)).unwrap();
        assert_eq!((terminal.native_database_id,terminal.terminal_hp),(1,23));
        let request=terminal.request();assert!(matches!(request,Request::FinishResults{terminal_hp:23,..}));
        let context=Context{account_id:"00000001-1234-4234-8234-123456789abc".into(),native_database_id:1,
            run_id:reservation.run_id.clone(),command_key:"res30:finish".into(),expected_revision:14};
        let body=encode_request(&context,&request).unwrap();assert!(body.len()>lifecycle_wire::MAX_RESULT_JSON_LEGACY/8&&body.len()<=lifecycle_wire::MAX_RESULT_REQUEST);
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
    #[test] fn p06t_result_projection_keeps_ammo_bay_extra_identity_before_packing() {
        let now=Instant::now();let mut w=World::new_for_roster(123,now,
            crate::map_profile091::MapId::Karelia,2).unwrap();
        w.device_events.push((1,crate::p06t_device_state::Transition{sequence:1,at_ms:1000,
            cause:crate::p06t_device_state::Cause{shot:1,attacker_slot:0},from_fire:false,
            change:crate::p06t_device_state::Change::Device{device:crate::p06t_device_caps::Device::AmmoBay,
                extra_index:27,max_health:60,before:60,after:10,
                before_condition:crate::p06t_device_state::Condition::Normal,
                after_condition:crate::p06t_device_state::Condition::Critical,repair:false}}));
        let facts=project_module_facts(&w).unwrap();assert_eq!(facts.len(),1);
        assert_eq!((facts[0].extra_index,facts[0].critical,facts[0].fire),(27,true,false));
        let mut forged=w.clone();
        if let Some((_,event))=forged.device_events.first_mut(){
            event.change=crate::p06t_device_state::Change::Device{device:crate::p06t_device_caps::Device::AmmoBay,
                extra_index:28,max_health:60,before:60,after:10,
                before_condition:crate::p06t_device_state::Condition::Normal,
                after_condition:crate::p06t_device_state::Condition::Critical,repair:false};
        }
        assert!(project_module_facts(&forged).is_err());
    }

    #[test] fn p05c_ram_result_has_health_kill_and_reason_without_fake_shot() {
        let mut r=roster();
        r[0].direct_hits=0;r[0].piercings=0;r[0].damage_dealt=90;r[0].kills=1;
        r[1].damage_received=90;r[1].killer_id=10;r[1].death_reason=2;
        let ram=[
            super::super::lifecycle_details::RamDamage{sequence:1,tick:1001,attacker:0,target:1,health_before:90,health_after:45},
            super::super::lifecycle_details::RamDamage{sequence:2,tick:1002,attacker:0,target:1,health_before:45,health_after:0},
        ];
        let d=super::super::lifecycle_details::project_with_ram(&r,&[],&[],&[],&[],&ram,&[],None).unwrap();
        let target=&d.row(10).unwrap().targets[0];
        assert_eq!((target.direct_hits,target.piercings,target.damage_dealt,target.death_reason),(0,0,90,2));
        assert_eq!(d.outgoing(10,"damaged"),1);assert!(d.validate(&r).is_ok());
    }

    #[test] fn p05c_ram_and_projectile_share_domain_hp_chain_without_contact_shot() {
        let mut r=roster();
        r[0].piercings=0;r[0].damage_dealt=90;r[0].kills=1;r[1].damage_received=90;r[1].killer_id=10;r[1].death_reason=2;
        let timed=[super::super::lifecycle_details::TimedDamage{tick:1001,damage:super::super::lifecycle_details::Damage{sequence:1,shot:1,attacker:0,target:1,
            health_before:90,health_after:50,lethal:false,reason:0}}];
        let ram=[super::super::lifecycle_details::RamDamage{sequence:1,tick:1001,attacker:0,target:1,health_before:50,health_after:0}];
        let d=super::super::lifecycle_details::project_with_ram(&r,&[super::super::lifecycle_details::Shot{id:1,attacker:0}],&[super::super::lifecycle_details::Hit{shot:1,target:1}],&[],&timed,&ram,&[],None).unwrap();
        let target=&d.row(10).unwrap().targets[0];
        assert_eq!((target.direct_hits,target.piercings,target.damage_dealt,target.death_reason),(1,0,90,2));
        assert!(d.validate(&r).is_ok());
    }

    #[test] fn p05c_ram_rejects_forged_health_chain_or_duplicate_commit() {
        let mut r=roster();r[0].direct_hits=0;r[0].piercings=0;r[0].damage_dealt=45;r[0].kills=0;
        r[1].damage_received=45;r[1].killer_id=0;r[1].death_reason=-1;
        let forged=[super::super::lifecycle_details::RamDamage{sequence:1,tick:1001,attacker:0,target:1,health_before:90,health_after:45},
            super::super::lifecycle_details::RamDamage{sequence:2,tick:1002,attacker:0,target:1,health_before:90,health_after:45}];
        assert!(super::super::lifecycle_details::project_with_ram(&r,&[],&[],&[],&[],&forged,&[],None).is_err());
        let duplicate=[super::super::lifecycle_details::RamDamage{sequence:1,tick:1001,attacker:0,target:1,health_before:90,health_after:45},
            super::super::lifecycle_details::RamDamage{sequence:1,tick:1001,attacker:0,target:1,health_before:45,health_after:0}];
        assert!(super::super::lifecycle_details::project_with_ram(&r,&[],&[],&[],&[],&duplicate,&[],None).is_err());
    }
}
