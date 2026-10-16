//! V2 World transaction adapters. Original internal hit volumes and server
//! mechanics are UNKNOWN; each proxy/damage/fire decision names its LAB policy.
use super::*;
use crate::{p06t_device_state as device,p06t_device_caps as caps};
/// Source `gun`/extra gunHealth is verified. Admission and deterministic chance
/// below are explicit LAB policy; this surface never applies vehicle HP damage.
pub const MODULE_ADMISSION_POLICY:&str="test_lab.p06t.plate-penetration-or-exterior-gun.v1";

impl World {
    pub fn cancelled_terminal_state(loadout:&crate::profile13_v2091::Frozen)->io::Result<String>{
        let state=device::State::new(caps::Profile::ALL[loadout.kind.index()]);
        terminal_json(loadout,&state,0,None)
    }
    pub fn terminal_state_json(&self,slot:usize)->io::Result<String>{
        let actor=self.actors.get(slot).ok_or_else(||bad())?;
        let frozen=actor.owned_v2.as_ref().ok_or_else(||bad())?;
        let state=actor.devices.as_ref().ok_or_else(||bad())?;
        let death=self.damage_events.iter().find(|event|event.target==slot&&event.lethal());
        if actor.alive()!=death.is_none(){return Err(bad());}
        terminal_json(frozen,state,self.actors.len(),death)
    }
    fn record_damage(&mut self,actors:&mut[Actor],target:usize,attacker:usize,shot:u32,tick:u32,
        reason:u8,amount:u16,crew_before:bool,direct:bool,pierced:bool)->io::Result<()> {
        if target>=actors.len()||attacker>=actors.len()||shot==0||shot as usize>self.shot_limit()||tick<1000
            ||reason>10||self.damage_events.len()>=MAX_DAMAGE_EVENTS{return Err(bad());}
        let actor=&mut actors[target];let before=actor.health;
        let after=i32::from(before).saturating_sub(i32::from(amount)).max(0)as i16;
        actor.health=after;let crew_after=actor.alive();
        if before!=after||crew_before!=crew_after {
            self.damage_events.push(DamageRecord{sequence:self.damage_events.len()as u32+1,tick,attacker,target,shot,reason,
                health_before:before,health_after:after,crew_before,crew_after,direct,pierced});
        }
        if !crew_after {actor.input=Input::STOP;actor.speed=0.;actor.aim.park();
            if let Some(state)=&mut actor.devices{state.freeze();}}
        Ok(())
    }
    pub(super) fn drain_fire(&mut self,actors:&mut[Actor],at_ms:u64)->io::Result<()> {
        let mut transitions=Vec::new();
        for (slot,actor)in actors.iter_mut().enumerate(){
            let health=device::Health{hp:actor.health as u16,max_hp:actor.vehicle_kind().max_health()as u16,
                terminal:self.lifecycle.as_ref().is_some_and(|state|state.outcome().is_some())};
            if let Some(state)=actor.devices.as_mut(){
                transitions.extend(state.advance_fire(at_ms,health)?.into_iter().map(|event|(slot,event)));
            }
        }
        transitions.sort_by_key(|(slot,event)|(event.at_ms,*slot,event.sequence));
        for (slot,event)in transitions {
            if let device::Change::VehicleDamage{amount}=event.change{
                let before=actors[slot].alive();
                self.record_damage(actors,slot,usize::from(event.cause.attacker_slot),event.cause.shot,
                    1000+u32::try_from(event.at_ms/100).map_err(|_|bad())?,1,amount,before,false,false)?;
            }
            if self.device_events.len()>=MAX_DAMAGE_EVENTS{return Err(bad());}
            self.device_events.push((slot,event));
        }
        Ok(())
    }
    fn ignition_roll(&mut self,shot:u32,target:usize,ordinal:u8)->io::Result<f64>{
        if self.rng_draws.len()>=MAX_BATTLE_SHOTS*MAX_ACTORS*2{return Err(bad());}
        // Explicit LAB SplitMix64. Seed/draw order are server owned and retained;
        // this does not claim the historical server's random distribution.
        self.rng_state=self.rng_state.wrapping_add(0x9e3779b97f4a7c15);
        let mut value=self.rng_state;value=(value^(value>>30)).wrapping_mul(0xbf58476d1ce4e5b9);
        value=(value^(value>>27)).wrapping_mul(0x94d049bb133111eb);value^=value>>31;
        self.rng_draws.push((shot,target,ordinal,value));
        Ok((value>>11)as f64/(1u64<<53)as f64)
    }
    pub(super) fn direct_mixed(&mut self,actors:&mut[Actor],trace:&mut impact::Trace,projectile:&Projectile,
        contact:&Contact,bundle:&geometry::Bundle)->io::Result<crate::p06t_damage::Resolution>{
        let shell=projectile.shell.ok_or_else(||bad())?;let slot=contact.target_slot;
        let before=actors.get(slot).ok_or_else(||bad())?.health;let crew_before=actors[slot].alive();
        let chord=std::array::from_fn(|i|contact.segment_end[i]-contact.segment_start[i]);
        let distance=(0..3).map(|i|(f64::from(contact.endpoint[i])-f64::from(projectile.origin[i])).powi(2)).sum::<f64>().sqrt();
        let plate=impact::plate_for(actors[slot].vehicle_kind(),&contact.material_facts,chord,contact.triangle.normal,distance)?;
        let resolution=crate::p06t_damage::resolve_direct(crate::p06t_damage::DirectInput{
            shell,plate,chord,winding_normal:contact.triangle.normal,distance_m:distance})?;
        let after=(i32::from(before)-i32::from(resolution.damage_hp)).max(0)as i16;
        trace.mixed_resolution(self.id,projectile.sequence,contact.tick,projectile.slot,slot,contact,&resolution,before,after)?;
        let facts=&contact.material_facts;
        let exterior_gun=resolution.decision!=crate::p06t_damage::Decision::OutOfRange
            &&facts.component==super::super::materials::gun_component(actors[slot].vehicle_kind())
            &&facts.profile_revision==super::super::materials::profile_revision(actors[slot].vehicle_kind())
            &&facts.name=="gun"&&facts.kind==25&&facts.source_class==super::super::materials::SourceClass::GunVisualMaterial
            &&facts.effective.as_ref().is_some_and(|material|material.kind==25&&!material.extra_is_none
                &&material.damage_kind==1&&material.vehicle_damage_factor==0.&&!material.use_hit_angle&&material.collide_once_only
                &&material.armor.is_some_and(|armor|armor>0.&&resolution.nominal_power_mm>f64::from(armor)));
        if resolution.decision==crate::p06t_damage::Decision::Pierced||exterior_gun {
            let ray=bundle.proxy_ray(contact)?;
            if !ray.is_empty(){
                let profile=caps::Profile::ALL[actors[slot].vehicle_kind().index()];
                let component=match ray.component{super::super::materials::Component::Hull=>crate::p06t_lab_proxy::Component::Hull,
                    super::super::materials::Component::Turret01=>crate::p06t_lab_proxy::Component::Turret,
                    super::super::materials::Component::Gun01|super::super::materials::Component::Gun02=>crate::p06t_lab_proxy::Component::Gun};
                let hits=crate::p06t_lab_proxy::select(profile,component,[ray.bbox_min,ray.bbox_max],ray.start,ray.end)?;
                let mut inputs=Vec::new();
                for (ordinal,hit)in hits.iter().enumerate(){inputs.push(device::ModuleHit{
                    cause:device::Cause{shot:projectile.sequence,attacker_slot:projectile.slot as u8},ordinal:ordinal as u8,
                    at_ms:u64::from(contact.tick-1000)*100,target:hit.target,shell,
                    ignition_roll:self.ignition_roll(projectile.sequence,slot,ordinal as u8)?});}
                if !inputs.is_empty(){
                    let actor=&mut actors[slot];let health=device::Health{hp:before as u16,max_hp:actor.vehicle_kind().max_health()as u16,terminal:false};
                    let events=actor.devices.as_mut().ok_or_else(||bad())?.apply_hits(&inputs,health)?;
                    if self.device_events.len()+events.len()>MAX_DAMAGE_EVENTS{return Err(bad());}
                    self.device_events.extend(events.into_iter().map(|event|(slot,event)));
                }
            }
        }
        self.record_damage(actors,slot,projectile.slot,projectile.sequence,contact.tick,0,resolution.damage_hp,
            crew_before,true,resolution.decision==crate::p06t_damage::Decision::Pierced)?;
        Ok(resolution)
    }
    pub(super) fn explode_mixed(&mut self,actors:&mut[Actor],trace:&mut impact::Trace,projectile:&Projectile,
        center:[f32;3],tick:u32,exclude_target:Option<usize>,fragile_state:Option<&fragiles::State>)->io::Result<()> {
        let shell=projectile.shell.ok_or_else(||bad())?;
        if shell.family!=crate::p06t_shells091::Family::HighExplosive{return Ok(());}
        let radius=shell.explosion_radius_m.ok_or_else(||bad())?as f32;
        let terrain=self.terrain.as_ref().ok_or_else(||bad())?.clone();
        let excluded=fragile_state.map_or_else(Vec::new,|state|state.projectile_excluded());
        for slot in 0..actors.len(){
            if exclude_target==Some(slot)||!actors[slot].alive(){continue;}
            let bundle=self.geometry_for(actors[slot].vehicle_kind())?.clone();
            let Some(contact)=bundle.explosion_contact(&actors[slot],center,radius,projectile.sequence,slot,tick)?else{continue;};
            let chord=std::array::from_fn(|i|contact.segment_end[i]-contact.segment_start[i]);
            let distance=(0..3).map(|i|(f64::from(contact.endpoint[i])-f64::from(center[i])).powi(2)).sum::<f64>().sqrt();
            let plate=impact::plate_for(actors[slot].vehicle_kind(),&contact.material_facts,chord,contact.triangle.normal,distance)?;
            if !plate.ordinary{continue;}
            let clear=impact::splash_los(&terrain,center,contact.endpoint,&excluded)?;
            let result=crate::p06t_damage::resolve_splash(shell,&[crate::p06t_damage::SplashTarget{
                slot:slot as u8,distance_m:distance,armor_mm:plate.armor_mm.ok_or_else(||bad())?,los_clear:clear}])?[0];
            let before=actors[slot].health;let after=(i32::from(before)-i32::from(result.damage_hp)).max(0)as i16;
            trace.splash_resolution(self.id,projectile.sequence,tick,projectile.slot,slot,&contact,center,&result,before,after,
                &terrain,&bundle,&actors[slot])?;
            let crew_before=actors[slot].alive();
            self.record_damage(actors,slot,projectile.slot,projectile.sequence,tick,0,result.damage_hp,crew_before,false,false)?;
        }
        Ok(())
    }
}

fn terminal_json(frozen:&crate::profile13_v2091::Frozen,state:&device::State,roster:usize,death:Option<&DamageRecord>)->io::Result<String>{
    if frozen.crew_ids.len()!=state.crew().len()||roster>MAX_ACTORS{return Err(bad());}
    let value=serde_json::json!({"policy_revision":device::POLICY,"roster_size":roster,"crew_active":state.crew_active(),
        "crew":frozen.crew_ids.iter().zip(state.crew()).map(|(id,alive)|serde_json::json!({"crew_id":id,"alive":alive})).collect::<Vec<_>>(),
        "devices":state.health().iter().zip(caps::CAPS[state.profile().index()]).enumerate().map(|(index,(health,cap))|
            serde_json::json!({"extra_index":26+index,"health":health,"max_health":cap.max})).collect::<Vec<_>>(),
        "fire":{"active":state.fire_active(),"ticks":state.fire_ticks(),"damage":state.proposed_fire_damage()},
        "death":{"reason":death.map_or(-1i16,|event|i16::from(event.reason)),"killer_slot":death.map(|event|event.attacker),
            "tick":death.map_or(0,|event|event.tick)}});
    let raw=serde_json::to_string(&value).map_err(|_|bad())?;if raw.len()>8192{return Err(bad());}Ok(raw)
}
