//! V2 World transaction adapters. Original internal hit volumes and server
//! mechanics are UNKNOWN; each proxy/damage/fire decision names its LAB policy.
use super::*;
use crate::{p06t_device_state as device,p06t_device_caps as caps};
use super::super::ammo_detonation as rack;
/// Source `gun`/extra gunHealth is verified. Admission and deterministic chance
/// below are explicit LAB policy; this surface never applies vehicle HP damage.
pub const MODULE_ADMISSION_POLICY:&str="test_lab.p06t.plate-penetration-or-exterior-gun.v1";

impl World {
    /// Separate explicit LAB31 opt-in. It grants neither owned admission nor
    /// a historical damage claim and cannot be enabled after actor attachment.
    pub fn enable_extended_breech_lab(&mut self)->io::Result<()> {
        if !self.extended_lab||!self.mixed_ammo||!self.mixed_profiles||self.started.is_some()
            ||!self.actors.is_empty()||!self.shots.is_empty()||!self.projectiles.is_empty(){return Err(bad());}
        self.impact.enable_extended_breech_lab()
    }
    pub fn extended_breech_lab(&self)->bool{self.impact.extended_breech_lab()}
    pub fn cancelled_terminal_state(loadout:&crate::profile13_v2091::Frozen)->io::Result<String>{
        let profile=caps::Profile::for_owned(loadout.kind).ok_or_else(bad)?;
        let state=device::State::new(profile)?;
        terminal_json(loadout,&state,0,None)
    }
    pub fn terminal_state_json(&self,slot:usize)->io::Result<String>{
        let actor=self.actors.get(slot).ok_or_else(||bad())?;
        let frozen=actor.owned_v2.as_ref().ok_or_else(||bad())?;
        let state=actor.devices.as_ref().ok_or_else(||bad())?;
        let death=self.death_cause(slot)?;
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
            {let next_sequence=self.damage_events.len() as u32+1;self.damage_events.push(DamageRecord{sequence:next_sequence,tick,attacker,target,shot,reason,
                health_before:before,health_after:after,crew_before,crew_after,direct,pierced});}
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
    /// Explicit LAB SplitMix64 step of the one battle RNG; callers journal it.
    fn splitmix_next(&mut self)->u64{
        self.rng_state=self.rng_state.wrapping_add(0x9e3779b97f4a7c15);
        let mut value=self.rng_state;value=(value^(value>>30)).wrapping_mul(0xbf58476d1ce4e5b9);
        value=(value^(value>>27)).wrapping_mul(0x94d049bb133111eb);value^value>>31
    }
    fn ignition_roll(&mut self,shot:u32,target:usize,ordinal:u8)->io::Result<f64>{
        if self.rng_draws.len()>=MAX_BATTLE_SHOTS*MAX_ACTORS*2{return Err(bad());}
        // Explicit LAB SplitMix64. Seed/draw order are server owned and retained;
        // this does not claim the historical server's random distribution.
        let value=self.splitmix_next();
        self.rng_draws.push((shot,target,ordinal,value));
        Ok((value>>11)as f64/(1u64<<53)as f64)
    }
    /// TURRET-01: six battle-RNG draws, journalled as (shot,target,0xe0+i) in
    /// this order, then the PROJECT launch policy over the actual event: the
    /// attacker→target heading at the detonation and the lost share of the rack.
    pub(super) fn turret_launch(&mut self,actors:&[Actor],event:&rack::Event)->io::Result<rack::Launch>{
        let(target,attacker)=(actors.get(event.target()).ok_or_else(||bad())?,actors.get(event.attacker()).ok_or_else(||bad())?);
        let dx=target.position[0]-attacker.position[0];let dz=target.position[2]-attacker.position[2];
        // Coincident positions: the attacker's own heading stands in.
        let heading=if dx.hypot(dz)>1e-3{dx.atan2(dz)}else{attacker.direction[0]};
        let lost=event.lost().iter().map(|n|f32::from(*n)).sum::<f32>();
        let fill=(lost/f32::from(event.kind().ammo_limit().max(1))).min(1.);
        if self.rng_draws.len()+rack::LAUNCH_DRAWS>MAX_BATTLE_SHOTS*MAX_ACTORS*2{return Err(bad());}
        let mut draws=[0u64;rack::LAUNCH_DRAWS];
        for(i,draw)in draws.iter_mut().enumerate(){
            let value=self.splitmix_next();
            self.rng_draws.push((event.shot(),event.target(),rack::LAUNCH_ORDINAL+i as u8,value));*draw=value;
        }
        rack::Launch::derive(heading,fill,draws)
    }
    pub(super) fn direct_mixed(&mut self,actors:&mut[Actor],trace:&mut impact::Trace,projectile:&Projectile,
        contact:&Contact,bundle:&geometry::Bundle)->io::Result<crate::p06t_damage::Resolution>{
        let shell=projectile.shell.ok_or_else(||bad())?;let slot=contact.target_slot;
        let before=actors.get(slot).ok_or_else(||bad())?.health;let crew_before=actors[slot].alive();
        let chord=std::array::from_fn(|i|contact.segment_end[i]-contact.segment_start[i]);
        let distance=(0..3).map(|i|(f64::from(contact.endpoint[i])-f64::from(projectile.origin[i])).powi(2)).sum::<f64>().sqrt();
        let resolution=impact::resolve_mixed_for(actors[slot].vehicle_kind(),&contact.material_facts,shell,
            chord,contact.triangle.normal,distance,trace.extended_breech_lab())?;
        let after=(i32::from(before)-i32::from(resolution.damage_hp)).max(0)as i16;
        trace.mixed_resolution_source(self.id,projectile.sequence,contact.tick,projectile.slot,slot,contact,&resolution,before,after,bundle,&actors[slot])?;
        let facts=&contact.material_facts;
        let exterior_gun=resolution.decision!=crate::p06t_damage::Decision::OutOfRange
            &&facts.component==super::super::materials::gun_component(actors[slot].vehicle_kind())
            &&facts.profile_revision==super::super::materials::profile_revision(actors[slot].vehicle_kind())
            &&facts.name=="gun"&&facts.kind==25&&facts.source_class==super::super::materials::SourceClass::GunVisualMaterial
            &&facts.effective.as_ref().is_some_and(|material|material.kind==25&&!material.extra_is_none
                &&material.damage_kind==1&&material.vehicle_damage_factor==0.&&!material.use_hit_angle&&material.collide_once_only
                &&material.armor.is_some_and(|armor|armor>0.&&resolution.nominal_power_mm>f64::from(armor)));
        let mut additional=0;
        if resolution.decision==crate::p06t_damage::Decision::UnarmoredDevice {
            // Exact source class gunBreech31 names gunHealth/native extra32.
            // One direct gun hit, no internal proxy or stochastic chance gate.
            // Gun cannot ignite; the unused canonical roll0 is not an RNG draw.
            let input=device::ModuleHit{cause:device::Cause{shot:projectile.sequence,attacker_slot:projectile.slot as u8},
                ordinal:0,at_ms:u64::from(contact.tick-1000)*100,target:crate::p06t_lab_proxy::Target::Device(caps::Device::Gun),
                shell,ignition_roll:0.};
            let actor=&mut actors[slot];let health=device::Health{hp:before as u16,max_hp:actor.vehicle_kind().max_health()as u16,terminal:false};
            let events=actor.devices.as_mut().ok_or_else(||bad())?.apply_hits(&[input],health)?;
            if self.device_events.len()+events.len()>MAX_DAMAGE_EVENTS{return Err(bad());}
            self.device_events.extend(events.into_iter().map(|event|(slot,event)));
        }else if resolution.decision==crate::p06t_damage::Decision::Pierced||exterior_gun {
            let ray=bundle.proxy_ray(contact)?;
            if !ray.is_empty(){
                let kind=actors[slot].vehicle_kind();
                let profile=caps::Profile::for_owned(kind).or_else(||caps::Profile::SUPPORTED.get(kind.index()).copied()).ok_or_else(||bad())?;
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
                    additional=self.apply_rack_transition(actors,slot,&events,before as u16,after as u16,
                        projectile.sequence,projectile.slot,contact.tick)?;
                    self.device_events.extend(events.into_iter().map(|event|(slot,event)));
                }
            }
        }
        // Preserve the raw plate Trace/AppliedImpact. The one authoritative
        // HP/death record includes only the residual HP that detonation removes.
        // Even a simultaneous final-seat wound must not create a second kill.
        let damage=resolution.damage_hp.saturating_add(additional).min(before as u16);
        self.record_damage(actors,slot,projectile.slot,projectile.sequence,contact.tick,0,damage,
            crew_before,true,resolution.decision==crate::p06t_damage::Decision::Pierced)?;
        Ok(resolution)
    }
    fn apply_rack_transition(&mut self,actors:&mut[Actor],slot:usize,events:&[device::Transition],
        health_before:u16,residual_hp:u16,shot:u32,attacker:usize,tick:u32)->io::Result<u16>{
        if self.ammo_detonation.is_none(){return Ok(0);}
        let mut destroyed=events.iter().filter_map(|event|match event.change{
            device::Change::Device{device:caps::Device::AmmoBay,before,after:0,..}if before>0=>Some((event,before)),_=>None});
        let Some((transition,device_before))=destroyed.next()else{return Ok(0);};
        if destroyed.next().is_some()||transition.cause.shot!=shot||usize::from(transition.cause.attacker_slot)!=attacker
            ||transition.at_ms!=u64::from(tick.checked_sub(1000).ok_or_else(||bad())?)*100||transition.from_fire{return Err(bad());}
        let actor=actors.get(slot).ok_or_else(||bad())?;
        let input=rack::Input{shot,target:slot,attacker,tick,device_sequence:transition.sequence,device_before,device_after:0,
            health_before,residual_hp,counts:actor.fire.typed().ok_or_else(||bad())?.counts(),kind:actor.vehicle_kind(),
            joint:turret_joint(actor)?,from_fire:transition.from_fire};
        let mut ledger=self.ammo_detonation.as_ref().ok_or_else(||bad())?.clone();
        let outcome=ledger.apply(input)?;
        match outcome{
            rack::Outcome::New(event)=>{
                if self.turret_flights.len()>=MAX_ACTORS{return Err(bad());}
                let mut fire=actors[slot].fire.clone();
                if fire.lose_loaded_for_detonation()?!=event.lost(){return Err(bad());}
                actors[slot].fire=fire;
                let flight=if self.turret_jolt{rack::Flight::jolt(event,self.turret_launch(actors,&event)?)?}else{rack::Flight::new(event)};
                self.turret_flights.push(flight);
                self.ammo_detonation=Some(ledger);Ok(event.additional_damage())
            },
            rack::Outcome::Empty=>{self.ammo_detonation=Some(ledger);Ok(0)},
            // Actual module replay emits no Transition. Seeing one twice here
            // would attempt to apply HP again and is a causal integration bug.
            rack::Outcome::Replay(_)=>Err(bad()),
        }
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

#[cfg(test)]
impl World{
    /// TURRET-01 SYNTHETIC test/bench hook: the lethal rack event of `target`
    /// by `attacker` without a projectile (no plate Trace). It uses the real
    /// ledger, joint, death bookkeeping and launch derivation.
    pub(crate) fn force_detonation_for_test(&mut self,target:usize,attacker:usize,shot:u32)->io::Result<rack::Event>{
        let mut actors=std::mem::take(&mut self.actors);
        let result=(||{
            let actor=actors.get(target).ok_or_else(||bad())?;
            let input=rack::Input{shot,target,attacker,tick:self.tick,device_sequence:1,device_before:1,device_after:0,
                health_before:actor.health as u16,residual_hp:actor.health as u16,counts:actor.fire.typed().ok_or_else(||bad())?.counts(),
                kind:actor.vehicle_kind(),joint:turret_joint(actor)?,from_fire:false};
            let mut ledger=self.ammo_detonation.clone().ok_or_else(||bad())?;
            let rack::Outcome::New(event)=ledger.apply(input)?else{return Err(bad());};
            let mut fire=actors[target].fire.clone();fire.lose_loaded_for_detonation()?;actors[target].fire=fire;
            let crew=actors[target].alive();
            self.record_damage(&mut actors,target,attacker,shot,self.tick,0,input.health_before,crew,true,true)?;
            let flight=if self.turret_jolt{rack::Flight::jolt(event,self.turret_launch(&actors,&event)?)?}else{rack::Flight::new(event)};
            self.turret_flights.push(flight);self.ammo_detonation=Some(ledger);Ok(event)
        })();
        self.actors=actors;result
    }
}

/// Compose the actual authoritative chassis basis with the source turret yaw.
/// Position is the source first turret joint, never muzzle/client coordinates.
fn turret_joint(actor:&Actor)->io::Result<rack::JointPose>{
    let pivot=super::super::pose::rotate(actor.vehicle_kind().aim().pivot,actor.direction);
    let position=std::array::from_fn(|i|actor.position[i]+pivot[i]);
    let(s,c)=actor.aim.yaw.sin_cos();
    let forward=super::super::pose::rotate([s,0.,c],actor.direction);
    let right=super::super::pose::rotate([c,0.,-s],actor.direction);
    let up=super::super::pose::rotate([0.,1.,0.],actor.direction);
    let pitch=-forward[1].clamp(-1.,1.).asin();
    let horizontal=forward[0].hypot(forward[2]);
    // At the Euler pole, roll=0 and yaw from right encode the same composed R.
    let(yaw,roll)=if horizontal>1e-6{(forward[0].atan2(forward[2]),right[1].atan2(up[1]))}
        else{((-right[2]).atan2(right[0]),0.)};
    let joint=rack::JointPose{position,direction:[yaw,pitch,roll]};
    if joint.position.iter().chain(joint.direction.iter()).any(|v|!v.is_finite()){return Err(bad());}Ok(joint)
}

fn terminal_json(frozen:&crate::profile13_v2091::Frozen,state:&device::State,roster:usize,death:Option<DeathCause>)->io::Result<String>{
    if frozen.crew_ids.len()!=state.crew().len()||roster>MAX_ACTORS
        ||state.policy_version()!=device::PolicyVersion::V1
        ||caps::Profile::for_owned(frozen.kind)!=Some(state.profile()){return Err(bad());}
    let value=serde_json::json!({"policy_revision":device::POLICY,"roster_size":roster,"crew_active":state.crew_active(),
        "crew":frozen.crew_ids.iter().zip(state.crew()).map(|(id,alive)|serde_json::json!({"crew_id":id,"alive":alive})).collect::<Vec<_>>(),
        "devices":state.health().iter().zip(*state.profile().caps()).enumerate().map(|(index,(health,cap))|
            serde_json::json!({"extra_index":26+index,"health":health,"max_health":cap.max})).collect::<Vec<_>>(),
        "fire":{"active":state.fire_active(),"ticks":state.fire_ticks(),"damage":state.proposed_fire_damage()},
        "death":{"reason":death.map_or(-1i16,|event|i16::from(event.reason)),"killer_slot":death.map(|event|event.attacker),
            "tick":death.map_or(0,|event|event.tick)}});
    let raw=serde_json::to_string(&value).map_err(|_|bad())?;if raw.len()>8192{return Err(bad());}Ok(raw)
}

#[cfg(test)]
#[path="ammo_detonation_world_tests.rs"]
mod ammo_detonation_world_tests;

#[cfg(test)]
impl World{
    /// BW-01 x TURRET-01 fixture for tests outside this module.
    pub(crate) fn turret01_jolt_detonation_for_test(now:Instant)->(World,Instant){let w=ammo_detonation_world_tests::jolt_detonation_world(now);let last=w.last;(w,last)}
}
