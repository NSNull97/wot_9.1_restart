//! UI-06: frags of the players panel and the team killer flag, derived only
//! from committed journals, so a live panel and the final results agree and a
//! reconnect needs no extra state. Nothing here decides a hit or changes the
//! world. The rules are PROJECT POLICY, not WG behaviour: the threshold of the
//! original server is unknown, docs/plans/UI06_EARS_TEAMKILL.md.
use std::io;
use super::lifecycle_wire::{Participant,TeamScore,TeamScoreRow,TEAM_SCORE_POLICY};
use super::model::{self,World};
use super::server::battle_ledger;

#[derive(Clone,Copy,Debug,Default,PartialEq,Eq)]
pub(super) struct Score {pub frags:i16,pub team_kills:u8,pub team_damage:u32,pub team_killer:bool}

/// (killer, victim) of every death with an author. The same journal entries
/// that give the native vehicle_killed, so the attribution has one source; a
/// fire's entry names the shot that set it. A death by one's own hand scores nothing.
fn kills(world:&World)->Vec<(usize,usize)> {
    let mut rows=if world.mixed_ammo() {
        world.damage_events.iter().filter(|e|e.lethal()).map(|e|(e.attacker,e.target)).collect::<Vec<_>>()
    } else {
        world.impacts.iter().filter(|e|e.health_before>0&&e.health_after<=0).map(|e|(e.attacker,e.target)).collect()
    };
    rows.extend(world.ram_damage_events.iter().filter(|e|e.health_before>0&&e.health_after==0).map(|e|(e.attacker,e.target)));
    rows.retain(|(killer,victim)|killer!=victim);rows
}
pub(super) fn table(world:&World)->io::Result<[Score;model::MAX_ACTORS]> {
    let teams=(0..world.actors.len()).map(|slot|world.team(slot)).collect::<io::Result<Vec<_>>>()?;
    let team=|slot:usize|teams.get(slot).copied().ok_or_else(||model::bad());
    let mut rows=[Score::default();model::MAX_ACTORS];
    for(killer,victim)in kills(world) {
        let same=team(killer)?==team(victim)?;
        let row=&mut rows[killer];
        if same {
            row.frags-=1;row.team_kills=row.team_kills.checked_add(1).ok_or_else(||model::bad())?;row.team_killer=true;
        } else {row.frags+=1;}
    }
    for harm in battle_ledger::harms(world,0,0)? {
        if harm.attacker==harm.target||team(harm.attacker)?!=team(harm.target)? {continue;}
        let row=&mut rows[harm.attacker];
        row.team_damage=row.team_damage.checked_add(u32::from(harm.amount)).ok_or_else(||model::bad())?;row.team_killer=true;
    }
    // A contact is journaled against both vehicles, there is no "who did it":
    // ramming counts as team damage and colours only by a kill, above.
    for event in &world.ram_damage_events {
        if event.attacker==event.target||team(event.attacker)?!=team(event.target)? {continue;}
        let lost=u32::try_from(i32::from(event.health_before)-i32::from(event.health_after)).map_err(|_|model::bad())?;
        let row=&mut rows[event.attacker];
        row.team_damage=row.team_damage.checked_add(lost).ok_or_else(||model::bad())?;
    }
    Ok(rows)
}
/// Whether `viewer` may hold the flag of `slot`. The client paints enemies
/// normally everywhere but on the minimap; the enemy team gets no flag at all.
pub(super) fn shown_to(world:&World,slot:usize,viewer:usize)->io::Result<bool> {
    if !world.team_score()||world.team(slot)?!=world.team(viewer)? {return Ok(false);}
    Ok(table(world)?[slot].team_killer)
}
/// Direct hits on an ally; only the native results column reads them.
fn team_hits(world:&World,slot:usize)->io::Result<u16> {
    let team=world.team(slot)?;let mut hits=0u16;
    for contact in world.contacts.iter().filter(|contact|contact.target_slot!=slot) {
        if world.team(contact.target_slot)?==team&&world.shots.iter().any(|shot|shot.sequence==contact.shot&&shot.slot==slot) {
            hits=hits.checked_add(1).ok_or_else(||model::bad())?;
        }
    }
    Ok(hits)
}
pub(super) fn results(world:&World,participants:&[Participant])->io::Result<Option<TeamScore>> {
    if !world.team_score() {return Ok(None);}
    let scores=table(world)?;
    let rows=participants.iter().enumerate().map(|(slot,p)|Ok(TeamScoreRow{vehicle_id:p.vehicle_id,
        frags:scores[slot].frags,team_kills:scores[slot].team_kills,team_damage:scores[slot].team_damage,
        team_hits:team_hits(world,slot)?,team_killer:scores[slot].team_killer})).collect::<io::Result<Vec<_>>>()?;
    Ok(Some(TeamScore{version:1,policy:TEAM_SCORE_POLICY.into(),rows}))
}
