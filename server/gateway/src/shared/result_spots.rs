//! Bounded first enemy observation ledger from authoritative visibility only.
//!
//! This is an explicit laboratory credit policy, not historical camouflage,
//! radio sharing or simultaneous detector attribution. No native IDs, client
//! coordinates or cached publication sets enter this domain component.
use std::io;

pub(crate) const POLICY: &str = "test_lab.p08c.first-visible-enemy-lowest-slot.v1";
const MAX_ACTORS:usize=6;

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub(crate) struct SpotRecord {observer:usize,target:usize,tick:u32}
impl SpotRecord {
    pub(crate) fn observer(&self)->usize{self.observer}
    pub(crate) fn target(&self)->usize{self.target}
    pub(crate) fn tick(&self)->u32{self.tick}
}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub(super) struct Member {pub team:u8,pub present:bool,pub ready:bool,pub alive:bool}
impl Member {fn eligible(self)->bool{self.present&&self.ready&&self.alive}}
fn bad(reason:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,reason)}

/// Stage at most six first-observation facts without mutating the old journal.
/// The caller invokes this only for an actions-enabled lifecycle phase. Each
/// callback must recompute actual server visibility for the current coherent
/// snapshot. All eligible rows succeed before any new record is returned.
pub(super) fn refresh<F>(old:&[SpotRecord],last_tick:Option<u32>,tick:u32,
    members:&[Member],mut desired:F)->io::Result<Vec<SpotRecord>>
where F:FnMut(usize)->io::Result<[bool;MAX_ACTORS]>{
    if !(2..=MAX_ACTORS).contains(&members.len())||tick<1000||old.len()>members.len()
        ||members.iter().any(|m|!matches!(m.team,1|2))
        ||![1,2].into_iter().all(|team|members.iter().any(|m|m.team==team))
        ||last_tick.is_some_and(|last|last<1000||last>tick)
        ||!old.is_empty()&&last_tick.is_none(){return Err(bad("first spot ledger header"));}
    let mut credited=[false;MAX_ACTORS];
    let mut previous=1000;
    for record in old {
        if record.observer>=members.len()||record.target>=members.len()
            ||record.observer==record.target||members[record.observer].team==members[record.target].team
            ||record.tick<previous||record.tick>last_tick.unwrap_or(0)||credited[record.target]{
            return Err(bad("first spot retained record"));
        }
        previous=record.tick;credited[record.target]=true;
    }
    if last_tick==Some(tick){return Ok(old.to_vec());}
    let mut visible=[None;MAX_ACTORS];
    for(observer,member)in members.iter().enumerate(){
        if !member.eligible()||!members.iter().enumerate().any(|(target,m)|
            !credited[target]&&m.eligible()&&m.team!=member.team){continue;}
        let row=desired(observer)?;
        if !row[observer]||row.iter().skip(members.len()).any(|v|*v){
            return Err(bad("first spot visibility row identity"));
        }
        visible[observer]=Some(row);
    }
    let mut next=old.to_vec();
    for(target,member)in members.iter().enumerate(){
        if credited[target]||!member.eligible(){continue;}
        if let Some(observer)=(0..members.len()).find(|&observer|
            members[observer].team!=member.team&&members[observer].eligible()
                &&visible[observer].is_some_and(|row|row[target])){
            if next.len()>=MAX_ACTORS{return Err(bad("first spot record bound"));}
            next.push(SpotRecord{observer,target,tick});
        }
    }
    Ok(next)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn roster(count:usize)->Vec<Member>{(0..count).map(|slot|Member{team:(slot%2)as u8+1,
        present:true,ready:true,alive:true}).collect()}
    fn all(count:usize)->[bool;MAX_ACTORS]{std::array::from_fn(|slot|slot<count)}
    #[test]fn p08c_first_spot_six_targets_choose_lowest_eligible_enemy_once(){
        let members=roster(6);let mut queried=Vec::new();
        let rows=refresh(&[],None,1000,&members,|slot|{queried.push(slot);Ok(all(6))}).unwrap();
        assert_eq!(queried,(0..6).collect::<Vec<_>>());assert_eq!(rows.len(),6);
        assert_eq!(rows.iter().map(|r|(r.observer(),r.target(),r.tick())).collect::<Vec<_>>(),
            (0..6).map(|target|(if target%2==0{1}else{0},target,1000)).collect::<Vec<_>>());
        let repeated=refresh(&rows,Some(1000),1001,&members,|_|panic!("all targets already credited")).unwrap();
        assert_eq!(rows,repeated);
    }
    #[test]fn p08c_first_spot_no_credit_for_dead_parked_unready_or_allied_actors(){
        for inactive in 0..3{
            let mut members=roster(4);
            match inactive{0=>members[0].alive=false,1=>members[0].present=false,_=>members[0].ready=false}
            let rows=refresh(&[],None,1000,&members,|slot|{assert_ne!(slot,0);Ok(all(4))}).unwrap();
            assert!(rows.iter().all(|r|r.target()!=0&&r.observer()!=0));
            assert_eq!(rows.iter().find(|r|r.target()==1).unwrap().observer(),2);
            assert!(rows.iter().all(|r|members[r.observer()].team!=members[r.target()].team));
        }
    }
    #[test]fn p08c_first_spot_reveal_and_repeated_respot_do_not_change_credit(){
        let members=roster(2);
        let hidden=refresh(&[],None,1000,&members,|slot|{let mut row=[false;6];row[slot]=true;Ok(row)}).unwrap();
        assert!(hidden.is_empty());
        let revealed=refresh(&hidden,Some(1000),1001,&members,|_|Ok(all(2))).unwrap();
        assert_eq!(revealed.len(),2);
        assert_eq!(refresh(&revealed,Some(1001),1002,&members,|_|panic!("respot cannot award")).unwrap(),revealed);
        assert_eq!(refresh(&revealed,Some(1001),1001,&members,|_|panic!("same publication tick")).unwrap(),revealed);
    }
    #[test]fn p08c_first_spot_late_visibility_error_returns_no_partial_journal(){
        let members=roster(4);let old=Vec::new();let mut calls=Vec::new();
        let result=refresh(&old,None,1000,&members,|slot|{
            calls.push(slot);if slot==2{Err(bad("actual LOS failed"))}else{Ok(all(4))}});
        assert!(result.is_err());assert_eq!(calls,vec![0,1,2]);assert!(old.is_empty());
    }
    #[test]fn p08c_first_spot_retained_poison_and_clock_fail_before_visibility(){
        let members=roster(2);
        let good=refresh(&[],None,1000,&members,|_|Ok(all(2))).unwrap();
        for mutation in 0..7{
            let mut rows=good.clone();let(mut last,mut tick)=(Some(1000),1001);
            match mutation{0=>rows[1]=rows[0],1=>rows[0].observer=2,2=>rows[0].target=2,
                3=>rows[0].observer=rows[0].target,4=>last=None,5=>last=Some(1002),_=>tick=999}
            assert!(refresh(&rows,last,tick,&members,|_|panic!("poison must fail first")).is_err());
        }
    }
    #[test]fn p08c_first_spot_invalid_visibility_row_is_not_treated_as_visible(){
        let members=roster(2);
        assert!(refresh(&[],None,1000,&members,|_|Ok([false;6])).is_err());
        assert!(refresh(&[],None,1000,&members,|_|Ok([true;6])).is_err());
        let mut invalid=members;invalid[1].team=1;
        assert!(refresh(&[],None,1000,&invalid,|_|panic!("team validation")).is_err());
    }
}
