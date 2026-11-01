//! UI-03 ledger: blocked and potential damage, assist and burned HP, derived
//! only from committed journals, so a live feed row and a final total agree.
//! Nothing here decides a hit or changes the world. Every formula is PROJECT
//! POLICY, not WG behaviour: docs/plans/UI03_BATTLE_FEEDS.md.
use super::*;
use crate::p06t_device_caps::Device;
use crate::p06t_device_state::{Change,Condition};

/// 10 s of 100 ms ticks after the first-spot credit. The ledger keeps one
/// credit per target, so a later re-spot earns no new window.
pub(super) const SPOT_ASSIST_TICKS:u32=100;

/// Nominal catalog damage of a shell; laboratory shots have none.
pub(super) fn nominal(world:&World,shot:u32)->Option<u16> {
    world.projectiles.iter().find(|p|p.sequence==shot).and_then(|p|p.shell).map(|shell|shell.damage_hp)
}
pub(super) fn armor_stopped(event:&model::AppliedImpact)->bool {
    event.health_after>=event.health_before&&matches!(impact_visual(event).ok().flatten().map(|(_,outcome,_)|outcome),
        Some(impact_wire::ShotOutcome::NotPierced|impact_wire::ShotOutcome::Ricochet))
}
/// HP one shot or fire took from a vehicle, whichever journal owns the mode.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub(super) struct Harm {pub tick:u32,pub attacker:usize,pub target:usize,pub amount:u16}
pub(super) fn harms(world:&World,damage_from:usize,impacts_from:usize)->io::Result<Vec<Harm>> {
    let lost=|before:i16,after:i16|u16::try_from((i32::from(before)-i32::from(after)).max(0)).map_err(|_|model::bad());
    let mut rows=Vec::new();
    if world.mixed_ammo() {
        for e in world.damage_events.iter().skip(damage_from).filter(|e|e.reason<=1) {
            rows.push(Harm{tick:e.tick,attacker:e.attacker,target:e.target,amount:lost(e.health_before,e.health_after)?});
        }
    } else {
        for e in world.impacts.iter().skip(impacts_from).filter(|e|e.health_before>0) {
            rows.push(Harm{tick:e.tick,attacker:e.attacker,target:e.target,amount:lost(e.health_before,e.health_after)?});
        }
    }
    rows.retain(|row|row.amount>0);Ok(rows)
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub(super) enum Assist {Track,Spot}
/// Whose track on `target` is down at `tick`: (left, right) authors.
fn track_authors(world:&World,target:usize,tick:u32)->io::Result<[Option<usize>;2]> {
    let mut authors=[None;2];
    for(slot,event)in world.device_events.iter().filter(|row|row.0==target){
        let at=u32::try_from(event.at_ms/100).ok().and_then(|t|t.checked_add(1000)).ok_or_else(||model::bad())?;
        if at>tick {break;}
        if let Change::Device{device,after_condition,..}=event.change {
            let index=match device {Device::LeftTrack=>0,Device::RightTrack=>1,_=>continue};
            debug_assert_eq!(*slot,target);
            authors[index]=(after_condition==Condition::Destroyed&&!event.from_fire).then(||usize::from(event.cause.attacker_slot));
        }
    }
    Ok(authors)
}
/// One harm earns a recipient at most one assist, a downed track first. Other
/// allies earn theirs in full: nothing is split. The recipient's own damage
/// and a harm that is not ally on enemy earn nothing.
pub(super) fn assist(world:&World,recipient:usize,harm:Harm)->io::Result<Option<Assist>> {
    let team=world.team(recipient)?;
    if harm.attacker==recipient||world.team(harm.attacker)?!=team||world.team(harm.target)?==team {return Ok(None);}
    if track_authors(world,harm.target,harm.tick)?.contains(&Some(recipient)) {return Ok(Some(Assist::Track));}
    let spotted=world.result_spots().unwrap_or(&[]).iter().any(|spot|spot.observer()==recipient&&spot.target()==harm.target
        &&harm.tick>=spot.tick()&&harm.tick-spot.tick()<=SPOT_ASSIST_TICKS);
    Ok(spotted.then_some(Assist::Spot))
}
/// Full battle totals of one vehicle, hidden sources included: a sum at the end
/// of a battle tells no single shot. UI-04 fills the native result fields and
/// its history from here.
#[derive(Clone,Copy,Debug,Default,PartialEq,Eq)]
pub(super) struct Totals {pub blocked:u32,pub potential_received:u32,pub assist_spot:u32,pub assist_track:u32,pub burned:u32}
#[cfg_attr(not(test),allow(dead_code))]
pub(super) fn totals(world:&World,slot:usize)->io::Result<Totals> {
    let mut sum=Totals::default();
    for event in world.impacts.iter().filter(|e|e.target==slot&&e.health_before>0) {
        let Some(hp)=nominal(world,event.shot).map(u32::from) else {continue;};
        sum.potential_received+=hp;
        if armor_stopped(event) {sum.blocked+=hp;}
    }
    for harm in harms(world,0,0)? {
        match assist(world,slot,harm)? {
            Some(Assist::Track)=>sum.assist_track+=u32::from(harm.amount),
            Some(Assist::Spot)=>sum.assist_spot+=u32::from(harm.amount),
            None=>{},
        }
    }
    for event in world.damage_events.iter().filter(|e|e.reason==1&&e.attacker==slot&&e.target!=slot) {
        if world.team(event.target)?!=world.team(slot)? {
            sum.burned+=u32::try_from((i32::from(event.health_before)-i32::from(event.health_after)).max(0)).map_err(|_|model::bad())?;
        }
    }
    Ok(sum)
}
