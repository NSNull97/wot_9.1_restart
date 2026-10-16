//! Explicit temporary source qualification. These quantities are LAB state;
//! no owned loadout, inventory grant or durable reservation is fabricated.
use super::*;

pub(crate) const POLICY:&str="test_lab.p06t.extended-source-qualification.v1";

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub(crate) struct LabLoadout {
    pub kind:VehicleKind,
    pub counts:[u16;3],
    pub initial:u16,
}

#[cfg(test)]
#[path="p06t_extended_world_tests.rs"]
mod tests;
#[cfg(test)]
#[path="p06t_extended_hit_tests.rs"]
mod hit_tests;
impl LabLoadout {
    pub fn validate(self)->io::Result<()> {
        let source=crate::p06t_shells091::profile(self.kind.mount());
        let selected=source.shots.iter().position(|shell|shell.compact_descr==self.initial).ok_or_else(bad)?;
        if self.counts.iter().map(|count|u32::from(*count)).sum::<u32>()>u32::from(source.capacity)
            ||self.counts[selected]==0 {return Err(bad());}
        Ok(())
    }
    pub fn temporary(kind:VehicleKind)->Self {
        let counts=match kind{VehicleKind::Wt128=>[12,6,6],VehicleKind::Fv183=>[4,4,4],_=>[kind.ammo_limit().min(20),0,0]};
        Self{kind,counts,initial:kind.shell_compact_id()as u16}
    }
}

impl World {
    pub fn extended_lab(&self)->bool {self.extended_lab}
    /// Resources are bound separately by their exact source loaders. Enabling
    /// this route does not authorize a legacy/native owned admission parser.
    pub fn enable_extended_lab(&mut self)->io::Result<()> {
        if self.extended_lab||self.mixed_ammo||!self.mixed_profiles||self.started.is_some()
            ||!self.actors.is_empty()||!self.shots.is_empty()||!self.projectiles.is_empty()
            ||!self.ap_test_lab||self.terrain.is_none()||self.fragiles.is_none()
            ||self.geometries.iter().any(Option::is_none){return Err(bad());}
        self.extended_lab=true;self.mixed_ammo=true;Ok(())
    }
    /// Reattaching requires the same original LAB loadout and keeps the current
    /// typed ammunition, devices and reload clock. A new request cannot refill.
    pub fn attach_extended_lab(&mut self,identity:Identity,session:u32,loadout:LabLoadout)->io::Result<usize> {
        loadout.validate()?;
        if !self.extended_lab||!self.mixed_ammo||!self.mixed_profiles{return Err(bad());}
        self.geometry_for(loadout.kind)?;
        let existing=self.actors.iter().position(|actor|actor.identity.account==identity.account);
        if existing.is_some_and(|slot|self.lab_loadouts[slot]!=Some(loadout)){return Err(bad());}
        let mut next=self.clone();let previous=next.vehicle_kind;
        next.mixed_ammo=false;next.vehicle_kind=loadout.kind;
        let fire=fire::State::with_typed(loadout.kind.mount(),loadout.counts,loadout.initial)?;
        let slot=next.attach_loadout_fire(identity,session,None,Some(fire))?;
        next.vehicle_kind=previous;next.mixed_ammo=true;
        if existing.is_none(){
            let actor=&mut next.actors[slot];
            actor.devices=Some(crate::p06t_device_state::State::new_v2(
                crate::p06t_device_caps::Profile::SUPPORTED[loadout.kind.index()])?);
            next.lab_loadouts[slot]=Some(loadout);
        }
        *self=next;Ok(slot)
    }
}

#[cfg(test)]
#[path="p06t_breech_world_tests.rs"]
pub(crate) mod breech_tests;
