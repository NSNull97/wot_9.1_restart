//! Recipient publication of committed v2 state. Private module/crew details
//! remain owner-only; all target-specific public bytes use current P07B epochs.
use super::*;
use crate::{armament_wire091 as native,p06t_device_state::{Change,Condition}};

fn health(world:&World,target:usize,attacker:Option<usize>,reason:u8)->io::Result<Vec<u8>>{
    let actor=world.actors.get(target).ok_or_else(||model::bad())?;
    if !(0..=actor.vehicle_kind().max_health()).contains(&actor.health)||reason>10{return Err(model::bad());}
    if world.ammo_detonations().iter().any(|event|event.target()==target){
        if actor.health!=0{return Err(model::bad());}
        return super::super::detached_turret::terminal_health(target,attacker,reason,
            super::super::detached_turret::DeathKind::Detached);
    }
    let mut body=vec![0x12];body.extend(wire::vehicle_id(target)?.to_le_bytes());
    body.push(0xa1);body.extend(actor.health.to_le_bytes());
    if let Some(attacker)=attacker{
        body.push(0x3c);body.extend(actor.health.to_le_bytes());body.extend(wire::vehicle_id(attacker)?.to_le_bytes());body.push(reason);
    }
    body.push(0x13);Ok(body)
}
fn owner_snapshot(c:&mut Client,outbox:&mut VecDeque<Vec<u8>>,world:&World)->io::Result<()> {
    if c.devices_snapshot_sent||!c.visible()[c.slot]{return Ok(());}
    let actor=world.actors.get(c.slot).ok_or_else(||model::bad())?;
    let state=actor.devices.as_ref().ok_or_else(||model::bad())?;
    let mut body=Vec::new();let id=wire::vehicle_id(c.slot)?;
    for(index,(hp,cap))in state.health().iter().zip(*state.profile().caps()).enumerate(){
        if *hp==0{body.extend(native::damage_info(id,1,26+index as u8,0)?);}
        else if u32::from(*hp)*2<=u32::from(cap.max){body.extend(native::damage_info(id,0,26+index as u8,0)?);}
    }
    for(seat,alive)in state.crew().iter().enumerate(){if !alive{
        body.extend(native::damage_info(id,2,state.profile().crew()[seat].extra,0)?);
    }}
    if state.fire_active(){body.extend(native::damage_info(id,3,4,0)?);}
    // These fixed messages stay bounded (9 devices +5 seats +fire <512 bytes).
    if !body.is_empty(){c.queue_private(outbox,body,&[c.slot])?;}
    c.devices_snapshot_sent=true;Ok(())
}
pub(super) fn publish(c:&mut Client,outbox:&mut VecDeque<Vec<u8>>,world:&World,now:Instant)->io::Result<()> {
    if !world.mixed_ammo(){return Ok(());}
    let owner=world.actors.get(c.slot).ok_or_else(||model::bad())?;
    let state=owner.fire.typed().ok_or_else(||model::bad())?;
    let key=(state.counts(),state.current().compact_descr,state.next().compact_descr,state.clip(),state.deadline(),state.base_reload_seconds().to_bits());
    if c.armament_sent!=Some(key){
        let mut body=native::ammo_snapshot(state.mount(),state.counts(),state.current().compact_descr,state.next().compact_descr,state.clip())?;
        body.extend(native::reload(wire::vehicle_id(c.slot)?,state.remaining_seconds(now),state.base_reload_seconds())?);
        outbox.push_back(body);c.armament_sent=Some(key);
    }
    owner_snapshot(c,outbox,world)?;
    for event in world.damage_events.iter().skip(c.damage_cursor){
        let primary=world.impacts.iter().find(|impact|impact.shot==event.shot).map(|impact|impact.target);
        if event.lethal()&&world.lifecycle.is_some(){
            let mut public=wire::roster_updates(world,event.target)?;
            public.extend(super::super::lifecycle_wire::vehicle_killed(wire::vehicle_id(event.target)?,wire::vehicle_id(event.attacker)?,event.reason)?);
            outbox.push_back(public);
        }
        // One HE terminal can damage several actual targets. Suppress its
        // center unless this recipient saw the launch and currently sees both.
        if !event.direct&&event.reason==0&&event.health_after<event.health_before
            &&c.visible()[event.target]&&c.visible()[event.attacker]
            &&primary.is_none_or(|slot|c.visible()[slot])
            &&c.tracer_started.get(event.shot as usize-1)==Some(&true){
            let projectile=world.projectiles.iter().find(|p|p.sequence==event.shot).ok_or_else(||model::bad())?;
            let shell=projectile.shell.ok_or_else(||model::bad())?;
            let body=native::explosion(wire::vehicle_id(event.target)?,wire::vehicle_id(event.attacker)?,projectile.terminal,shell)?;
            let mut targets=vec![event.target];if event.attacker!=event.target{targets.push(event.attacker);}
            if let Some(primary)=primary{if !targets.contains(&primary){targets.push(primary);}}
            c.queue_private(outbox,body,&targets)?;
        }
        c.damage_cursor=event.sequence as usize;
    }
    for event in world.ram_damage_events.iter().skip(c.ram_cursor){
        if event.health_before>0&&event.health_after==0&&world.lifecycle.is_some(){
            let mut public=wire::roster_updates(world,event.target)?;
            // Source #717 ATTACK_REASONS[2] = ramming, independently of the
            // damageInfo device-notification namespace. Kill attribution is
            // public roster metadata, as for projectile kills above; no pose
            // or private health packet escapes the recipient epoch fence.
            public.extend(super::super::lifecycle_wire::vehicle_killed(wire::vehicle_id(event.target)?,wire::vehicle_id(event.attacker)?,2)?);
            outbox.push_back(public);
        }
        c.ram_cursor+=1;
    }
    for(target,event)in world.device_events.iter().skip(c.device_cursor){
        if *target==c.slot&&c.visible()[c.slot]{
            let notification=match event.change{
                Change::Device{extra_index,before_condition,after_condition,repair,..} if before_condition!=after_condition=>
                    if repair {match after_condition{
                        Condition::Critical=>Some((18,extra_index)),Condition::Normal=>Some((19,extra_index)),Condition::Destroyed=>None}
                    } else {match after_condition{
                        Condition::Critical=>Some((if event.from_fire{12}else{4},extra_index)),
                        Condition::Destroyed=>Some((if event.from_fire{13}else{5},extra_index)),Condition::Normal=>None}},
                Change::Crew{extra_index,before_active:true,after_active:false,..}=>Some((10,extra_index)),
                Change::Fire{after_active,..}=>Some((if after_active{3}else{35},4)),
                _=>None,
            };
            if let Some((code,extra))=notification{
                let attacker=usize::from(event.cause.attacker_slot);
                let id=if c.visible()[attacker]{wire::vehicle_id(attacker)?}else{0};
                let mut targets=vec![c.slot];if id!=0&&attacker!=c.slot{targets.push(attacker);}
                c.queue_private(outbox,native::damage_info(wire::vehicle_id(c.slot)?,code,extra,id)?,&targets)?;
            }
        }
        c.device_cursor+=1;
    }
    for(target,actor)in world.actors.iter().enumerate(){
        if !c.visible()[target]{continue;}
        let crew=actor.crew_active();let fire=!actor.public_modifiers().is_empty();let mut body=Vec::new();
        let changed_crew=c.crew_sent[target]!=Some(crew);let mut targets=vec![target];
        if c.health_sent[target]!=Some(actor.health){
            if actor.health!=actor.vehicle_kind().max_health(){
                let(source,reason)=world.health_cause(target)?.ok_or_else(||model::bad())?;
                let attacker=c.visible()[source].then_some(source);
                body.extend(health(world,target,attacker,reason)?);
                if let Some(attacker)=attacker{if attacker!=target{targets.push(attacker);}}
            }
            c.health_sent[target]=Some(actor.health);
        }
        if changed_crew{body.extend(native::public_crew_active(wire::vehicle_id(target)?,crew)?);c.crew_sent[target]=Some(crew);}
        if c.fire_sent[target]!=Some(fire){
            body.extend(native::public_modifiers(wire::vehicle_id(target)?,&actor.public_modifiers())?);c.fire_sent[target]=Some(fire);
        }
        if target==c.slot&&(c.owner_health_sent!=Some(actor.health)||changed_crew){
            // #717 Avatar.updateVehicleHealth ends with vehicle.health=rawHealth
            // for a dead player vehicle. Sending 0 after the parent's -2 erased
            // the detachment mark, so the victim kept its own turret while the
            // DetachedTurret flew (owner run 2026-10-19). HUD clamps to 0.
            let native=if actor.health==0&&world.ammo_detonations().iter().any(|e|e.target()==target)
                {super::super::detached_turret::DeathKind::Detached.native_health()}else{actor.health};
            body.extend(native::owner_health(native,crew,actor.vehicle_kind().max_health()as u16)?);c.owner_health_sent=Some(actor.health);
        }
        if !body.is_empty(){c.queue_private(outbox,body,&targets)?;}
    }
    super::super::turret_publication::effects(c,outbox,world,now)?;
    Ok(())
}

#[cfg(test)]
#[path="p06t_publication_tests.rs"]
mod tests;
#[cfg(test)]
#[path="p06t_detonation_health_tests.rs"]
mod detonation_tests;
#[cfg(test)]
#[path="p05c_ram_publication_tests.rs"]
mod ram_tests;
