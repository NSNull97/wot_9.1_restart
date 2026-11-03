//! UI-06 publication: the native updates 5 and 10 by difference with what this
//! recipient's ClientArena already holds. No position, HP or module of any
//! vehicle goes here. Policy: docs/plans/UI06_EARS_TEAMKILL.md (git 30a6185).
use super::*;
use super::super::{lifecycle_wire,team_score};

const MAX_BODY:usize=500;
pub(super) fn publish(c:&mut Client,outbox:&mut VecDeque<Vec<u8>>,world:&World)->io::Result<()> {
    if !world.team_score() {return Ok(());}
    let journals=(world.damage_events.len(),world.impacts.len(),world.ram_damage_events.len());
    if c.team_score_journals==Some(journals) {return Ok(());}
    let scores=team_score::table(world)?;
    let mut body=Vec::new();
    let mut add=|record:Vec<u8>,outbox:&mut VecDeque<Vec<u8>>|{
        if body.len()+record.len()>MAX_BODY {outbox.push_back(std::mem::take(&mut body));}
        body.extend(record);
    };
    for slot in 0..world.actors.len() {
        let(frags,flagged)=c.team_score_sent[slot];
        if scores[slot].frags!=frags {add(lifecycle_wire::vehicle_statistics(wire::vehicle_id(slot)?,scores[slot].frags)?,outbox);}
        let flag=flagged||(scores[slot].team_killer&&world.team(slot)?==world.team(c.slot)?);
        if flag&&!flagged {add(lifecycle_wire::team_killer(wire::vehicle_id(slot)?)?,outbox);}
        c.team_score_sent[slot]=(scores[slot].frags,flag);
    }
    if !body.is_empty() {outbox.push_back(body);}
    c.team_score_journals=Some(journals);Ok(())
}
