//! Immutable roster-slot teams and a permutation of existing qualified lanes.
//! This is an explicit LAB arrangement policy, not historical map spawn data.
use std::io;

pub const POLICY:&str="test_lab.p10b.team-ordered-qualified-lanes.v1";
pub const MAX_ACTORS:usize=super::model::MAX_ACTORS;

fn bad()->io::Error{io::Error::new(io::ErrorKind::InvalidData,"P10B team plan:2..6 members,1..3 per side and a present roster slot required")}

#[derive(Clone,Debug,PartialEq,Eq)]
pub struct TeamPlan {teams:[u8;MAX_ACTORS],len:u8}
// BW-01 wire codec (tools/bw01_wire_gen.py): TeamPlan
impl crate::bw_wire::Wire for TeamPlan {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{teams,len}=self;W::put(teams,bw_o);W::put(len,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{teams:W::get(bw_i)?,len:W::get(bw_i)?})}
}
// end BW-01 wire codec

impl TeamPlan {
    pub fn new(members:&[u8])->io::Result<Self>{
        if !(2..=MAX_ACTORS).contains(&members.len()){return Err(bad());}
        let mut counts=[0usize;2];
        for team in members {
            if !(1..=2).contains(team){return Err(bad());}
            counts[usize::from(*team-1)]+=1;
        }
        if counts.iter().any(|n|!(1..=3).contains(n)){return Err(bad());}
        let mut teams=[0;MAX_ACTORS];teams[..members.len()].copy_from_slice(members);
        Ok(Self{teams,len:members.len()as u8})
    }
    pub fn len(&self)->usize{usize::from(self.len)}
    pub fn teams(&self)->&[u8]{&self.teams[..self.len()]}
    pub fn team(&self,slot:usize)->io::Result<u8>{self.teams().get(slot).copied().ok_or_else(bad)}
    /// Keep actor identity/physics slot intact. Only select an existing lane:
    /// left/right is the side and its stable earlier-member count is the row.
    pub fn lane(&self,slot:usize)->io::Result<usize>{
        let team=self.team(slot)?;
        let ordinal=self.teams()[..slot].iter().filter(|n|**n==team).count();
        Ok(2*ordinal+usize::from(team-1))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]fn all_rosters_have_exact_count_bounds_and_unique_qualified_lanes(){
        let mut accepted=0;
        for n in 2..=6 {for mask in 0..(1usize<<n){
            let teams=(0..n).map(|i|if mask&(1<<i)==0{1}else{2}).collect::<Vec<_>>();
            let one=teams.iter().filter(|n|**n==1).count();
            let two=n-one;
            let expected=(1..=3).contains(&one)&&(1..=3).contains(&two);
            let actual=TeamPlan::new(&teams);assert_eq!(actual.is_ok(),expected,"{teams:?}");
            if let Ok(plan)=actual {accepted+=1;let mut used=std::collections::BTreeSet::new();
                assert_eq!(plan.teams(),teams);assert_eq!(plan.len(),n);
                for slot in 0..n {let lane=plan.lane(slot).unwrap();assert!(lane<6&&used.insert(lane));
                    assert_eq!(lane%2+1,usize::from(teams[slot]));
                    assert_eq!(lane/2,teams[..slot].iter().filter(|v|**v==teams[slot]).count());
                }
            }
        }}
        assert_eq!(accepted,62);
    }
    #[test]fn three_vs_one_and_one_vs_three_change_lanes_without_reordering_identity(){
        for(teams,lanes)in[([1,1,1,2],[0,2,4,1]),([1,2,2,2],[0,1,3,5])]{
            let plan=TeamPlan::new(&teams).unwrap();
            assert_eq!((0..4).map(|slot|plan.team(slot).unwrap()).collect::<Vec<_>>(),teams);
            assert_eq!((0..4).map(|slot|plan.lane(slot).unwrap()).collect::<Vec<_>>(),lanes);
        }
    }
    #[test]fn parity_teams_preserve_every_legacy_lane(){
        for n in 2..=6 {let teams=(0..n).map(|slot|slot as u8%2+1).collect::<Vec<_>>();let plan=TeamPlan::new(&teams).unwrap();
            assert_eq!((0..n).map(|slot|plan.lane(slot).unwrap()).collect::<Vec<_>>(),(0..n).collect::<Vec<_>>());}
    }
    #[test]fn invalid_sides_and_sizes_fail_without_partial_plan(){
        for bad in[vec![],vec![1],vec![1,1],vec![2,2],vec![1,3],vec![0,2],vec![1,1,1,1,2],vec![1,2,2,2,2],vec![1,2,1,2,1,2,1]]{
            assert!(TeamPlan::new(&bad).is_err(),"{bad:?}");}
    }
    #[test]fn no_ghost_actor_slot_or_mutable_backing_input(){
        let mut input=[2,1,2,1];let plan=TeamPlan::new(&input).unwrap();let cloned=plan.clone();input.fill(1);
        assert_eq!(plan.teams(),[2,1,2,1]);assert_eq!(plan,cloned);
        for slot in [4,5,6,usize::MAX]{assert!(plan.team(slot).is_err());assert!(plan.lane(slot).is_err());}
    }
}
