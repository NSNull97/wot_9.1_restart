//! One source-pinned fragile object, under an explicit approximate lab policy.
//! HP15 and fixed AP30, no resistance/continuation/impulse, are NOT claimed as
//! historical 0.9.1 rules. Native area/item IDs belong to the compatibility layer.
use std::io;
use super::terrain;

pub const OBJECT_ID:u32=1;
pub const INSTANCE_ID:u32=1513;
pub const MATERIAL_KIND:u8=73;
pub const FIRST_TRIANGLE:u32=88749;
pub const TRIANGLE_COUNT:u32=42;
pub const HEALTH:i16=15;
pub const DAMAGE:u16=30;
pub const POLICY_REVISION:&str="test_lab-karelia-fragile-ap-v1";

fn bad()->io::Error{io::Error::new(io::ErrorKind::InvalidData,"one-object destructible contract")}

#[derive(Clone,Debug,PartialEq)]
pub struct Transition {
    pub object_id:u32,pub instance_id:u32,pub scene_before:u32,pub scene_after:u32,
    pub shot:u32,pub shooter:usize,pub tick:u32,pub hit:terrain::Hit,
    pub health_before:i16,pub health_after:i16,pub damage:u16,pub policy_revision:&'static str,
}
impl Transition {
    pub(crate) fn validate(&self)->io::Result<()>{
        if self.object_id!=OBJECT_ID || self.instance_id!=INSTANCE_ID || self.scene_before!=0 || self.scene_after!=1
            || self.shot==0 || self.shot>super::model::MAX_SHOTS as u32 || self.shooter>=super::model::CAPACITY || self.tick==0
            || self.health_before!=HEALTH || self.health_after!=0 || self.damage!=DAMAGE || self.policy_revision!=POLICY_REVISION
            || !selected(&self.hit) || !self.hit.t.is_finite() || !(0. ..=1.).contains(&self.hit.t)
            || self.hit.point.iter().chain(self.hit.normal.iter()).any(|v| !v.is_finite())
            || self.hit.point.iter().any(|v| v.abs()>terrain::MAX_QUERY_COORDINATE)
            || (self.hit.normal.iter().map(|v|v*v).sum::<f32>()-1.).abs()>1e-4 {return Err(bad());}Ok(())
    }
}
pub(crate) fn selected(hit:&terrain::Hit)->bool{
    matches!(hit.surface,terrain::Surface::StaticObstacle{instance_id:INSTANCE_ID,material_kind:MATERIAL_KIND})
        && (FIRST_TRIANGLE..FIRST_TRIANGLE+TRIANGLE_COUNT).contains(&hit.triangle_id)
}

#[derive(Clone,Debug,Default,PartialEq)]
pub(crate) struct State {transition:Option<Transition>}
impl State {
    pub(crate) fn scene_version(&self)->u32{u32::from(self.transition.is_some())}
    pub(crate) fn excluded_instance(&self)->Option<u32>{self.transition.as_ref().map(|_|INSTANCE_ID)}
    pub(crate) fn transition(&self)->Option<&Transition>{self.transition.as_ref()}
    /// Caller supplies only a previously computed server contact. World and
    /// Trace both validate/bind it before the cloned transaction is committed.
    pub(crate) fn contact(&mut self,shot:u32,shooter:usize,tick:u32,hit:terrain::Hit)->io::Result<Option<Transition>>{
        if !matches!(hit.surface,terrain::Surface::StaticObstacle{instance_id:INSTANCE_ID,..}){return Ok(None);}
        if self.transition.is_some(){return Err(bad());}
        let transition=Transition{object_id:OBJECT_ID,instance_id:INSTANCE_ID,scene_before:0,scene_after:1,
            shot,shooter,tick,hit,health_before:HEALTH,health_after:0,damage:DAMAGE,policy_revision:POLICY_REVISION};
        transition.validate()?;self.transition=Some(transition.clone());Ok(Some(transition))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn hit()->terrain::Hit{terrain::Hit{surface:terrain::Surface::StaticObstacle{instance_id:INSTANCE_ID,material_kind:MATERIAL_KIND},
        triangle_id:FIRST_TRIANGLE,t:0.5,point:[0.;3],normal:[1.,0.,0.]}}
    #[test]fn only_pinned_object_changes_once_under_named_approximation(){
        let mut state=State::default();let mut unrelated=hit();unrelated.surface=terrain::Surface::Ground;
        assert_eq!(state.contact(1,0,1001,unrelated).unwrap(),None);assert_eq!(state.scene_version(),0);
        let transition=state.contact(1,0,1001,hit()).unwrap().unwrap();assert_eq!((transition.health_before,transition.health_after,transition.damage),(15,0,30));
        assert_eq!(state.scene_version(),1);assert_eq!(state.excluded_instance(),Some(INSTANCE_ID));
        let before=state.clone();assert!(state.contact(1,0,1001,hit()).is_err());assert!(state.contact(2,1,1002,hit()).is_err());assert_eq!(state,before);
    }
    #[test]fn selected_object_wrong_material_triangle_or_invalid_contact_cannot_mutate(){
        for mode in 0..6{let mut state=State::default();let mut h=hit();match mode{
            0=>h.surface=terrain::Surface::StaticObstacle{instance_id:INSTANCE_ID,material_kind:111},
            1=>h.triangle_id=FIRST_TRIANGLE-1,2=>h.triangle_id=FIRST_TRIANGLE+TRIANGLE_COUNT,
            3=>h.point[0]=f32::NAN,4=>h.t=2.,5=>h.normal=[0.;3],_=>unreachable!()}
            assert!(state.contact(1,0,1001,h).is_err());assert_eq!(state,State::default());}
        for(shot,shooter,tick)in[(0,0,1001),(41,0,1001),(1,2,1001),(1,0,0)]{
            let mut state=State::default();assert!(state.contact(shot,shooter,tick,hit()).is_err());assert_eq!(state,State::default());}
    }
}
