//! UI-02 publication: what this recipient learns about the shells that reached
//! its own vehicle. It reads the committed journals at the same cursors as the
//! native callbacks, so a reconnect replays nothing, and it moves no cursor.
//! Policy: docs/plans/UI02_HIT_INDICATOR.md.
use super::*;
use crate::p06t_device_state::{Change,Condition};
use super::super::battle_events::{self,Channel,Critical,Event,HitReceived,Source,Verdict};

fn heading(world:&World,shot:u32)->Option<f32> {
    let velocity=world.projectiles.iter().find(|projectile|projectile.sequence==shot)?.velocity;
    (velocity.iter().all(|v|v.is_finite())&&(velocity[0]!=0.0||velocity[2]!=0.0)).then(||velocity[0].atan2(velocity[2]))
}
/// Damage to the recipient's own modules, crew or fire from this shot.
fn criticals(c:&Client,world:&World,shot:u32)->Vec<Critical> {
    let mut rows=Vec::new();
    for(target,event)in world.device_events.iter().skip(c.device_cursor){
        if *target!=c.slot||event.cause.shot!=shot||event.from_fire{continue;}
        let critical=match event.change{
            Change::Device{extra_index,before_condition,after_condition,repair:false,..} if before_condition!=after_condition=>match after_condition{
                Condition::Critical=>Some(Critical::Device{extra:extra_index,destroyed:false}),
                Condition::Destroyed=>Some(Critical::Device{extra:extra_index,destroyed:true}),
                Condition::Normal=>None},
            Change::Crew{extra_index,before_active:true,after_active:false,..}=>Some(Critical::Crew{extra:extra_index}),
            Change::Fire{before_active:false,after_active:true}=>Some(Critical::Fire),
            _=>None,
        };
        if let Some(critical)=critical{if rows.len()<battle_events::MAX_CRITICALS{rows.push(critical);}}
    }
    rows
}
fn verdict(event:&model::AppliedImpact)->Verdict {
    match impact_visual(event).ok().flatten().map(|(_,outcome,_)|outcome){
        Some(impact_wire::ShotOutcome::Pierced)=>Verdict::Pierced,
        Some(impact_wire::ShotOutcome::NotPierced)=>Verdict::NotPierced,
        Some(impact_wire::ShotOutcome::Ricochet)=>Verdict::Ricochet,
        None=>Verdict::Unknown,
    }
}
fn source(c:&Client,attacker:usize)->Source {if c.visible()[attacker]{Source::Visible(attacker)}else{Source::Hidden}}
fn friendly(world:&World,own:usize,attacker:usize)->io::Result<bool> {Ok(world.team(own)?==world.team(attacker)?)}
fn hit_events(c:&Client,world:&World)->io::Result<Vec<Event>> {
    let mut rows=Vec::new();
    for event in world.impacts.iter().skip(c.impact_cursor){
        if event.target!=c.slot||event.health_before<=0{continue;}
        let Some(yaw)=heading(world,event.shot) else {continue;};
        let damage=u16::try_from((event.health_before-event.health_after).max(0)).map_err(|_|model::bad())?;
        let verdict=verdict(event);
        let source=source(c,event.attacker);
        // "Удар сдержан": the nominal damage of the shell, a catalog fact of a
        // shooter the recipient sees. A hidden shooter's shell would tell its
        // gun, and the old MS-1 laboratory shots have no catalog shell: absent.
        let blocked=(damage==0&&matches!(verdict,Verdict::NotPierced|Verdict::Ricochet)&&source!=Source::Hidden)
            .then(||world.projectiles.iter().find(|p|p.sequence==event.shot).and_then(|p|p.shell).map(|shell|shell.damage_hp)).flatten();
        rows.push(Event::HitReceived(HitReceived{shot:event.shot,yaw,damage,blocked,verdict,
            friendly:friendly(world,c.slot,event.attacker)?,fatal:event.health_after<=0,source,criticals:criticals(c,world,event.shot)}));
    }
    // An HE terminal that hurt this vehicle without being its direct impact.
    for event in world.damage_events.iter().skip(c.damage_cursor){
        if event.direct||event.reason!=0||event.target!=c.slot||event.health_after>=event.health_before||event.health_before<=0
            ||world.impacts.iter().any(|impact|impact.shot==event.shot&&impact.target==c.slot){continue;}
        let Some(yaw)=heading(world,event.shot) else {continue;};
        let damage=u16::try_from(event.health_before-event.health_after).map_err(|_|model::bad())?;
        rows.push(Event::HitReceived(HitReceived{shot:event.shot,yaw,damage,blocked:None,verdict:Verdict::Splash,
            friendly:friendly(world,c.slot,event.attacker)?,fatal:event.health_after<=0,source:source(c,event.attacker),criticals:criticals(c,world,event.shot)}));
    }
    Ok(rows)
}
/// Runs before the native callbacks of this pass: a prepared client knows the
/// facts of a shell when its native hit indicator arrives.
pub(super) fn publish(c:&mut Client,outbox:&mut VecDeque<Vec<u8>>,world:&World,now:Instant,log:&mut Vec<String>)->io::Result<()> {
    let Some(mut channel)=c.battle_events.take() else {return Ok(());};
    let result=publish_on(&mut channel,c,outbox,world,now,log);
    c.battle_events=Some(channel);result
}
fn publish_on(channel:&mut Channel,c:&Client,outbox:&mut VecDeque<Vec<u8>>,world:&World,now:Instant,log:&mut Vec<String>)->io::Result<()> {
    if let Some(sequence)=channel.take_hello(){outbox.push_back(battle_events::hello_frame(sequence)?);}
    if !c.visible()[c.slot]{return Ok(());}
    let events=hit_events(c,world)?;
    for batch in events.chunks(battle_events::MAX_EVENTS_PER_FRAME){
        match channel.admit(now,outbox.len(),batch.len()){
            Some(sequence)=>{
                let body=battle_events::frame(sequence,batch)?;
                log.push(format!("BATTLE_EVENTS_FRAME battle={} slot={} sequence={sequence} events={} bytes={} recipient_only=true",world.id,c.slot,batch.len(),body.len()));
                outbox.push_back(body);
            },
            None=>log.push(format!("BATTLE_EVENTS_DROPPED battle={} slot={} events={} total_dropped={}",world.id,c.slot,batch.len(),channel.dropped)),
        }
    }
    Ok(())
}
