//! UI-03 ledger: blocked and potential damage, assist and burned HP, derived
//! only from committed journals, so a live feed row and a final total agree.
//! Nothing here decides a hit or changes the world. Every formula is PROJECT
//! POLICY, not WG behaviour: docs/plans/UI03_BATTLE_FEEDS.md (git 30a6185).
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
pub(in super::super) struct Harm {pub tick:u32,pub attacker:usize,pub target:usize,pub amount:u16,
    pub spotting:Option<model::result_spots::AssistEvidence>,pub is_ram:bool}
pub(in super::super) fn harms(world:&World,damage_from:usize,impacts_from:usize,ram_from:usize)->io::Result<Vec<Harm>> {
    let lost=|before:i16,after:i16|u16::try_from((i32::from(before)-i32::from(after)).max(0)).map_err(|_|model::bad());
    let mut rows=Vec::new();
    if world.mixed_ammo() {
        for e in world.damage_events.iter().skip(damage_from).filter(|e|e.reason<=1) {
            rows.push(Harm{tick:e.tick,attacker:e.attacker,target:e.target,amount:lost(e.health_before,e.health_after)?,spotting:e.spotting,is_ram:false});
        }
    } else {
        for e in world.impacts.iter().skip(impacts_from).filter(|e|e.health_before>0) {
            rows.push(Harm{tick:e.tick,attacker:e.attacker,target:e.target,amount:lost(e.health_before,e.health_after)?,spotting:e.spotting,is_ram:false});
        }
    }
    for e in world.ram_damage_events.iter().skip(ram_from).filter(|e|e.health_before>0) {
        rows.push(Harm{tick:e.domain_tick,attacker:e.attacker,target:e.target,amount:lost(e.health_before,e.health_after)?,spotting:e.spotting,is_ram:true});
    }
    rows.retain(|row|row.amount>0);Ok(rows)
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub(in super::super) enum Assist {Track,Spot}
/// Whose track on `target` is down at `tick`: (left, right) authors.
pub(in super::super) fn track_authors(world:&World,target:usize,tick:u32)->io::Result<[Option<usize>;2]> {
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
/// One assist earned in the battle. The native details keep them per target.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub(in super::super) struct Credit {pub recipient:usize,pub target:usize,pub kind:Assist,pub amount:u16}
/// A single HP loss is shared across eligible track and direct-spot helpers.
/// Track takes precedence for a helper in both sets. Integer remainder goes
/// to lowest domain slots. This v1 tie-break is project policy, not #717 fact.
fn credits_for_harm(world:&World,harm:Harm)->io::Result<Vec<Credit>> {
    let team=world.team(harm.attacker)?;
    if world.team(harm.target)?==team || harm.attacker==harm.target || harm.amount==0 {return Ok(Vec::new());}
    if let Some(evidence)=harm.spotting {
        if ((evidence.direct_mask | evidence.track_mask) >> world.actors.len())!=0 ||
            evidence.direct_mask!=0 && evidence.scan_tick.is_none_or(|at|at>harm.tick || harm.tick-at>model::result_spots::ASSIST_MAX_SCAN_AGE_TICKS)
            {return Err(model::bad());}
        let shooter_direct=evidence.direct_mask & (1_u32<<harm.attacker)!=0;
        let mut eligible=Vec::new();
        for recipient in 0..world.actors.len() {
            let direct=evidence.direct_mask & (1_u32<<recipient)!=0;
            if direct && world.team(recipient)?!=team {return Err(model::bad());}
            if recipient==harm.attacker || world.team(recipient)?!=team {continue;}
            let tracked=evidence.track_mask & (1_u32<<recipient)!=0;
            if tracked || direct && !shooter_direct {eligible.push((recipient,if tracked{Assist::Track}else{Assist::Spot}));}
        }
        if eligible.is_empty(){return Ok(Vec::new());}
        let count=eligible.len() as u16;let share=harm.amount/count;let remainder=harm.amount%count;
        return Ok(eligible.into_iter().enumerate().filter_map(|(order,(recipient,kind))|{
            let amount=share+u16::from((order as u16)<remainder);
            (amount>0).then_some(Credit{recipient,target:harm.target,kind,amount})
        }).collect());
    }
    // Legacy paths without P07B evidence retain their prior policy.
    if harm.is_ram {return Ok(Vec::new());}
    let authors=track_authors(world,harm.target,harm.tick)?;
    let spots=world.result_spots().unwrap_or(&[]).iter().filter(|spot|spot.target()==harm.target
        &&harm.tick>=spot.tick()&&harm.tick-spot.tick()<=SPOT_ASSIST_TICKS).map(|spot|spot.observer());
    let mut seen=Vec::new();let mut rows=Vec::new();
    for recipient in authors.into_iter().flatten().chain(spots) {
        if seen.contains(&recipient) || recipient==harm.attacker || world.team(recipient)?!=team {continue;}
        seen.push(recipient);
        rows.push(Credit{recipient,target:harm.target,kind:if authors.contains(&Some(recipient)){Assist::Track}else{Assist::Spot},amount:harm.amount});
    }
    Ok(rows)
}
pub(super) fn assist(world:&World,recipient:usize,harm:Harm)->io::Result<Option<(Assist,u16)>> {
    Ok(credits_for_harm(world,harm)?.into_iter().find(|c|c.recipient==recipient).map(|c|(c.kind,c.amount)))
}
pub(in super::super) fn credits(world:&World)->io::Result<Vec<Credit>> {
    let mut rows=Vec::new();for harm in harms(world,0,0,0)? {rows.extend(credits_for_harm(world,harm)?);} Ok(rows)
}
/// HP the vehicle took from enemies by shell, fire and ram: the sum of its
/// dealt feed records with the hidden targets included.
pub(super) fn dealt(world:&World,slot:usize)->io::Result<u32> {
    let team=world.team(slot)?;
    let mut sum=0u32;
    for harm in harms(world,0,0,0)? {
        if harm.attacker==slot&&world.team(harm.target)?!=team {sum+=u32::from(harm.amount);}
    }
    Ok(sum)
}
/// Full battle totals of one vehicle, hidden sources included: a sum at the end
/// of a battle tells no single shot. The native result fields of UI-04 and the
/// last history record come from here.
#[derive(Clone,Copy,Debug,Default,PartialEq,Eq)]
pub(in super::super) struct Totals {pub blocked:u32,pub potential_received:u32,pub assist_spot:u32,pub assist_track:u32,pub burned:u32}
pub(super) fn totals(world:&World,slot:usize)->io::Result<Totals> {totals_from(world,slot,&credits(world)?)}
pub(in super::super) fn totals_from(world:&World,slot:usize,credits:&[Credit])->io::Result<Totals> {
    let mut sum=Totals::default();
    for event in world.impacts.iter().filter(|e|e.target==slot&&e.health_before>0) {
        // SHELL-02: a shell counts once per target, on its body row when it reached one.
        if event.is_track()&&world.impacts.iter().any(|o|o.shot==event.shot&&o.target==slot&&!o.is_track()){continue;}
        let Some(hp)=nominal(world,event.shot).map(u32::from) else {continue;};
        sum.potential_received+=hp;
        if armor_stopped(event) {sum.blocked+=hp;}
    }
    for credit in credits.iter().filter(|credit|credit.recipient==slot) {
        match credit.kind {
            Assist::Track=>sum.assist_track+=u32::from(credit.amount),
            Assist::Spot=>sum.assist_spot+=u32::from(credit.amount),
        }
    }
    for event in world.damage_events.iter().filter(|e|e.reason==1&&e.attacker==slot&&e.target!=slot) {
        if world.team(event.target)?!=world.team(slot)? {
            sum.burned+=u32::try_from((i32::from(event.health_before)-i32::from(event.health_after)).max(0)).map_err(|_|model::bad())?;
        }
    }
    Ok(sum)
}
