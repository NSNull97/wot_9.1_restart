//! Current-recipient detached-turret publication. No queued pose history and
//! no new world authority while the terminal Avatar drains native requests.
use super::*;
use detached_turret::{ActionKind,Book,Entry,Pose};
use ammo_detonation::FlightPhase;
pub(super) const PRESENTATION_TIMEOUT_MS:u64=20_000;
#[derive(Clone)]
pub(super) struct State{pub(super) book:Book,pub(super) effect_cursor:u32,last_pose:[Option<u64>;6],last_colliding:[Option<bool>;6]}
impl State{pub(super) fn new()->Self{Self{book:Book::new(),effect_cursor:0,last_pose:[None;6],last_colliding:[None;6]}}}

// #717 client property1 BOOL in the established generic entity-property
// envelope. Python setter:172 is empty; this sets state, not a fake impact FX.
fn colliding(slot:usize,value:bool)->io::Result<Vec<u8>>{
    let mut body=vec![0x12];body.extend(detached_turret::entity_id(slot)?.to_le_bytes());
    body.extend([0x9f,u8::from(value),0x13]);Ok(body)
}

pub(super) fn parent_create(world:&World,slot:usize)->io::Result<Vec<u8>>{
    let mut body=wire::create_vehicle(world,slot)?;
    if world.ammo_detonations().iter().any(|e|e.target()==slot){
        if world.actors.get(slot).is_none_or(|a|a.health!=0)||body.get(42)!=Some(&3){return Err(bad());}
        let hp=body.get_mut(43..45).ok_or_else(||bad())?;
        hp.copy_from_slice(&detached_turret::DeathKind::Detached.native_health().to_le_bytes());
    }Ok(body)
}
fn refresh(c:&mut Client,world:&World)->io::Result<()>{
    if !world.ammo_detonation_enabled(){return Ok(());}
    let visible=c.visible();let mut seen=[false;6];let mut book=c.turrets.book.clone();
    for flight in world.turret_flights(){
        let event=flight.event();let slot=event.target();
        if slot>=world.actors.len()||slot>=6||seen[slot]||world.actors[slot].health!=0{return Err(bad());}
        seen[slot]=true;let sample=flight.sample();
        let epoch=if c.spotting_enabled{c.interest.as_ref().and_then(|b|b.announcement_sequence(slot))}
            else{c.creations[slot].map(|(seq,_)|seq)};
        // The detached turret is part of the published wreck. A separate LOS
        // ray to its ground-clamped point blocked on the terrain it rests on
        // and sent the attacker an early Leave (owner run 2026-10-19).
        let desired=sample.phase!=FlightPhase::Expired&&visible[slot];
        // Native parent death must already be queued ahead of the child. The
        // private flush below preserves that reliable order before Enter/Create.
        let parent_ready=c.creations[slot].is_some_and(|(_,ack)|ack)&&epoch.is_some()&&c.health_sent[slot]==Some(0);
        book.set_visibility(slot,epoch,parent_ready,visible[slot],desired)?;
    }
    for(slot,present)in seen.into_iter().enumerate(){if !present{book.set_visibility(slot,None,false,false,false)?;}}
    c.turrets.book=book;Ok(())
}

/// Emit source FX only at the current observed event, never upon later reveal.
/// Actual flight and fatal journals are already committed before this call.
pub(super) fn effects(c:&mut Client,outbox:&mut VecDeque<Vec<u8>>,world:&World,now:Instant)->io::Result<()>{
    if !world.ammo_detonation_enabled(){return Ok(());}
    let now_ms=world.lifecycle_ms(now)?;
    let cursor=c.turrets.effect_cursor;
    for event in world.ammo_detonations().iter().filter(|e|e.sequence()>cursor){
        let target=event.target();let attacker=event.attacker();
        if target>=world.actors.len()||attacker>=world.actors.len()||world.actors[target].health!=0{return Err(bad());}
        if c.visible()[target]&&now_ms.saturating_sub(event.born_ms())<=1000{
            // Explicit project visual inputs; the original Python ignores the
            // projected speed, and these values claim no historical impulse.
            let mut body=detached_turret::explosion(target,1.,8.)?;
            let known=c.visible()[attacker];let mut targets=vec![target];
            if known&&attacker!=target{targets.push(attacker);}
            if target==c.slot{body.extend(crate::armament_wire091::damage_info(wire::vehicle_id(target)?,
                if event.from_fire(){23}else{11},crate::p06t_device_caps::Device::AmmoBay.extra(),
                if known{wire::vehicle_id(attacker)?}else{0})?);}
            c.queue_private(outbox,body,&targets)?;
        }
        c.turrets.effect_cursor=event.sequence();
    }Ok(())
}

impl Session{
    pub(super) fn flush_shared_turrets(&mut self,world:&World,events:&mut Vec<String>)->io::Result<()>{
        if !world.ammo_detonation_enabled()||self.shared.as_ref().is_none_or(|c|!matches!(c.phase,Phase::Driving|Phase::Leaving)){return Ok(());}
        let mut next=self.clone();refresh(next.shared.as_mut().ok_or_else(||bad())?,world)?;
        // Native parent terminal health and ordinary entity changes stay in
        // their reliable order. No precise DT bytes are parked in an outbox.
        if !next.outbox.is_empty()||next.shared.as_ref().is_some_and(|c|!c.private_pending.is_empty()){
            *self=next;return Ok(());
        }
        let mut committed=Vec::new();
        while next.tx.len()<8{
            let Some(action)=next.shared.as_ref().ok_or_else(||bad())?.turrets.book.propose()else{break;};
            let body=match action.kind{
                ActionKind::Enter=>detached_turret::enter(action.slot)?,
                ActionKind::Leave=>detached_turret::leave(action.slot)?,
                ActionKind::Create=>{
                    let flight=world.turret_flights().iter().find(|f|f.event().target()==action.slot).ok_or_else(||bad())?;
                    let sample=flight.sample();if sample.phase==FlightPhase::Expired{return Err(bad());}
                    // Collision belongs to the detached entity from the
                    // moment it is created. Waiting until ground contact made
                    // the gun ghost through the first part of the fall.
                    detached_turret::create(action.slot,flight.event().kind(),Pose{position:sample.position,direction:sample.direction},
                        false,true)?
                },
            };
            let seq=next.tx.enqueue_body_tracked(&body)?;
            let c=next.shared.as_mut().ok_or_else(||bad())?;c.turrets.book.mark_queued(action,seq)?;
            c.turrets.last_pose[action.slot]=None;
            c.turrets.last_colliding[action.slot]=if action.kind==ActionKind::Create{
                Some(true)
            }else{None};
            committed.push(format!("P06T_TURRET_NATIVE session={} target={} action={:?} sequence={seq}",next.id,action.slot,action.kind));
        }
        for flight in world.turret_flights(){
            if next.tx.len()>=8{break;}
            let slot=flight.event().target();let sample=flight.sample();let c=next.shared.as_mut().ok_or_else(||bad())?;
            if !c.turrets.book.pose_allowed(slot)||c.turrets.last_pose[slot]==Some(sample.at_ms){continue;}
            let tick=1000u32.checked_add(u32::try_from(sample.at_ms/100).map_err(|_|bad())?).ok_or_else(||bad())?;
            // The detached entity carries the gun collider for the whole
            // flight and while it rests. Do not briefly switch it off between
            // the Create packet and the landing sample.
            let collidable=true;let mut body=Vec::new();
            if c.turrets.last_colliding[slot]!=Some(collidable){body.extend(colliding(slot,collidable)?);}
            body.extend(detached_turret::pose(slot,tick,Pose{position:sample.position,direction:sample.direction})?);
            next.tx.enqueue_body(&body)?;c.turrets.last_pose[slot]=Some(sample.at_ms);c.turrets.last_colliding[slot]=Some(collidable);
        }
        *self=next;events.extend(committed);Ok(())
    }
    pub(super) fn turret_presentation_ready(&self,world:&World,now:Instant)->io::Result<bool>{
        if !world.ammo_detonation_enabled()||world.ammo_detonations().is_empty(){return Ok(true);}
        let c=self.shared.as_ref().ok_or_else(||bad())?;
        let settled=world.turret_flights().iter().all(|f|f.sample().phase==FlightPhase::Resting);
        let entries_ready=(0..6).all(|slot|matches!(c.turrets.book.entry(slot),
            Some(Entry::Hidden)|Some(Entry::Created{acked:true,..})));
        // The detached-turret gate owns only its own reliable request/ACK
        // lifecycle. A normal heartbeat, results envelope, or unrelated
        // entity packet may legitimately remain in the shared Window while
        // this child is already acknowledged; tying readiness to the global
        // queue strands a dead avatar until the bounded timeout.
        let complete=settled&&entries_ready
            &&self.outbox.is_empty()&&c.private_pending.is_empty();
        if complete{return Ok(true);}
        let last=world.ammo_detonations().iter().map(|e|e.born_ms()).max().ok_or_else(||bad())?;
        if world.lifecycle_ms(now)?.saturating_sub(last)>=PRESENTATION_TIMEOUT_MS{
            // A dead avatar must never be stranded in spectator mode merely
            // because the client did not ACK the optional DetachedTurret
            // child. The authoritative result and Account handoff are more
            // important than a visual ACK. Keep the old world alive until the
            // normal result confirmation; the detached entity is then retired
            // together with that world. Callers may record this degraded
            // presentation separately, but must not fail the battle.
            return Ok(true);
        }Ok(false)
    }
}

/// Called after the complete terminal payload was validated on a throwaway
/// Driving clone. Retain only actual08 requests; never retain a world command.
pub(super) fn retain_terminal_requests(s:&mut Session,payload:&[u8])->io::Result<()>{
    let slot=s.shared.as_ref().ok_or_else(||bad())?.slot;let mut at=0;let mut count=0;
    while at<payload.len(){
        count+=1;if count>16{return Err(bad());}
        if payload.get(at..at+33).is_some_and(|raw|wire::ready(raw,slot).is_ok()){at+=33;continue;}
        let id=payload[at];let size=match id{8=>7,6=>1,2=>17,3=>22,
            0x87|0x88|0x89|0x8a|0x8d|0x8e|0x8f|0x0c|0x0d|0x0f|0x99=>{
                let len=payload.get(at+1..at+3).ok_or_else(||bad())?;3+usize::from(u16::from_le_bytes([len[0],len[1]]))},
            _=>return Err(bad()),};
        let raw=payload.get(at..at+size).ok_or_else(||bad())?;at+=size;
        if id==8{if let Some(target)=detached_turret::request(raw)?{s.shared.as_mut().ok_or_else(||bad())?.turrets.book.on_request(target)?;}}
    }Ok(())
}

#[cfg(test)]
#[path="turret_publication_tests.rs"]mod tests;
