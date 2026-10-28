//! Canonical source-bound armament candidate; not connected to the live World.
//! Explicit lab policy: quantities include shells in the clip; current switch
//! starts a complete reload, queued next switches at magazine completion.
//! No historical server scheduling fidelity is claimed by these rules.
use std::{io,time::{Duration,Instant}};
use crate::p06t_shells091::{Mount,Shell,PROFILES};

pub const POLICY:&str="test_lab.p06t.source-stacks-including-clip.v1";
fn bad(reason:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,reason)}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Selection {Current,Next}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Command {Shoot,Select(Selection,u16),ReloadClip,Replenish}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Refusal {Reloading,Empty,UnknownShell,SameShell,ReplenishUnsupported}
#[derive(Clone,Copy,Debug,PartialEq)]
pub enum Outcome {Shot{shell:Shell,remaining:u16,clip:u8},Selected,ReloadStarted,Refused(Refusal)}
#[derive(Clone,Debug,PartialEq)]
pub struct State {
    mount:Mount,counts:[u16;3],current:usize,next:usize,clip:u8,
    until:Option<Instant>,magazine_reload:bool,observed:Option<Instant>,
    accepted:u32,rejected:u32,replenish:u32,reload_scale:f64,
    initial:[u16;3],fired:[u16;3],lost:[u16;3],
}
impl State {
    pub fn new(mount:Mount,counts:[u16;3],initial:u16)->io::Result<Self>{
        let source=*crate::p06t_shells091::profile(mount);
        let total=counts.iter().try_fold(0u16,|n,c|n.checked_add(*c)).ok_or_else(||bad("armament count overflow"))?;
        let current=source.shots.iter().position(|s|s.compact_descr==initial).ok_or_else(||bad("armament initial shell source"))?;
        if total==0||total>source.capacity||counts[current]==0||source.clip_count==0||source.clip_count>6
            ||!source.reload_seconds.is_finite()||!(0.1..=120.).contains(&source.reload_seconds)
            ||!source.clip_interval_seconds.is_finite()||!(0. ..=120.).contains(&source.clip_interval_seconds)
            ||source.clip_count>1&&source.clip_interval_seconds<=0. {return Err(bad("armament mounted source bounds"));}
        Ok(Self{mount,counts,current,next:current,clip:counts[current].min(u16::from(source.clip_count))as u8,
            until:None,magazine_reload:false,observed:None,accepted:0,rejected:0,replenish:0,reload_scale:1.,
            initial:counts,fired:[0;3],lost:[0;3]})
    }
    pub fn mount(&self)->Mount{self.mount}
    pub fn counts(&self)->[u16;3]{self.counts}
    pub fn initial_counts(&self)->[u16;3]{self.initial}
    pub fn fired(&self)->[u16;3]{self.fired}
    pub fn lost(&self)->[u16;3]{self.lost}
    /// Only the opt-in World detonation transaction calls this after recording
    /// its causal module event. Clip shells are already INCLUDED in counts.
    /// Losing loaded ammunition is never a shot, reload or depot mutation.
    pub fn lose_loaded_for_detonation(&mut self)->io::Result<[u16;3]>{
        if self.counts==[0;3]||self.lost!=[0;3]
            ||(0..3).any(|i|u32::from(self.initial[i])!=u32::from(self.fired[i])+u32::from(self.lost[i])+u32::from(self.counts[i]))
            ||self.accepted!=self.fired.iter().map(|n|u32::from(*n)).sum::<u32>(){return Err(bad("armament detonation conservation"));}
        let removed=self.counts;self.lost=removed;self.counts=[0;3];self.clip=0;
        self.until=None;self.magazine_reload=false;Ok(removed)
    }
    pub fn total(&self)->u16{self.counts.iter().sum()}
    pub fn current(&self)->Shell{crate::p06t_shells091::profile(self.mount).shots[self.current]}
    pub fn next(&self)->Shell{crate::p06t_shells091::profile(self.mount).shots[self.next]}
    pub fn clip(&self)->u8{self.clip}
    pub fn deadline(&self)->Option<Instant>{self.until}
    pub fn accepted(&self)->u32{self.accepted}
    pub fn rejected(&self)->u32{self.rejected}
    pub fn replenish_requests(&self)->u32{self.replenish}
    pub fn base_reload_seconds(&self)->f32{
        let source=*crate::p06t_shells091::profile(self.mount);
        if self.magazine_reload||source.clip_count==1 {(source.reload_seconds*self.reload_scale)as f32}
        else {source.clip_interval_seconds as f32}
    }
    pub fn remaining_seconds(&self,now:Instant)->f32{
        self.until.map_or(0.,|until|until.saturating_duration_since(now).as_secs_f32())
    }
    pub fn set_reload_scale(&mut self,scale:f64,now:Instant)->io::Result<()>{
        if !scale.is_finite()||!(1. ..=4.).contains(&scale)||self.observed.is_some_and(|previous|now<previous){return Err(bad("armament capability scale/time"));}
        let mut next=self.clone();next.advance(now);
        if scale!=next.reload_scale&&next.magazine_reload {
            if let Some(until)=next.until{
                let seconds=until.saturating_duration_since(now).as_secs_f64()*scale/next.reload_scale;
                next.until=Some(now.checked_add(Duration::from_secs_f64(seconds)).ok_or_else(||bad("scaled reload overflow"))?);
            }
        }
        next.reload_scale=scale;*self=next;Ok(())
    }
    /// Commit reload transitions against authoritative time even without input.
    /// A queued empty stack is skipped only at a magazine boundary. This cannot
    /// replenish counts and is recorded by the calling world's state journal.
    pub fn advance(&mut self,now:Instant)->bool{
        if self.observed.is_some_and(|previous|now<previous){return false;}
        self.observed=Some(now);
        if self.until.is_none_or(|until|now<until){return false;}
        self.until=None;
        if self.magazine_reload {
            if self.counts[self.next]>0 {self.current=self.next;}
            else if self.counts[self.current]==0 {
                if let Some(index)=self.counts.iter().position(|count|*count>0){self.current=index;}
            }
            self.next=self.current;
            self.clip=self.counts[self.current].min(u16::from(crate::p06t_shells091::profile(self.mount).clip_count))as u8;
        }
        self.magazine_reload=false;true
    }
    fn reload(&mut self,now:Instant,magazine:bool)->io::Result<()> {
        let source=*crate::p06t_shells091::profile(self.mount);
        let seconds=if magazine||source.clip_count==1{source.reload_seconds*self.reload_scale}else{source.clip_interval_seconds};
        self.until=Some(now.checked_add(Duration::from_secs_f64(seconds)).ok_or_else(||bad("armament clock overflow"))?);
        self.magazine_reload=magazine;Ok(())
    }
    fn refuse(&mut self,reason:Refusal)->io::Result<Outcome>{
        self.rejected=self.rejected.checked_add(1).ok_or_else(||bad("armament refusal counter"))?;
        Ok(Outcome::Refused(reason))
    }
    fn one(&mut self,command:Command,now:Instant)->io::Result<Outcome>{
        self.advance(now);
        match command {
            Command::Shoot=>{
                if self.until.is_some(){return self.refuse(Refusal::Reloading);}
                if self.counts[self.current]==0||self.clip==0{return self.refuse(Refusal::Empty);}
                let shell=self.current();self.counts[self.current]-=1;self.clip-=1;
                self.fired[self.current]=self.fired[self.current].checked_add(1).ok_or_else(||bad("armament fired stack overflow"))?;
                self.accepted=self.accepted.checked_add(1).ok_or_else(||bad("armament shot counter"))?;
                let magazine=self.clip==0||self.counts[self.current]==0;
                self.reload(now,magazine)?;
                Ok(Outcome::Shot{shell,remaining:self.counts[self.current],clip:self.clip})
            },
            Command::Select(mode,compact)=>{
                let Some(index)=crate::p06t_shells091::profile(self.mount).shots.iter().position(|s|s.compact_descr==compact)else{return self.refuse(Refusal::UnknownShell)};
                if self.counts[index]==0{return self.refuse(Refusal::Empty);}
                if mode==Selection::Next {self.next=index;return Ok(Outcome::Selected);}
                if index==self.current{return self.refuse(Refusal::SameShell);}
                self.current=index;self.next=index;self.clip=0;
                self.reload(now,true)?;Ok(Outcome::ReloadStarted)
            },
            Command::ReloadClip=>{
                let source=*crate::p06t_shells091::profile(self.mount);
                if source.clip_count==1||self.counts[self.current]==0{return self.refuse(Refusal::Empty);}
                // An existing full reload is never extended by repeated input.
                if self.magazine_reload&&self.until.is_some(){return self.refuse(Refusal::Reloading);}
                self.clip=0;self.reload(now,true)?;Ok(Outcome::ReloadStarted)
            },
            Command::Replenish=>{
                self.replenish=self.replenish.checked_add(1).ok_or_else(||bad("armament replenish counter"))?;
                Ok(Outcome::Refused(Refusal::ReplenishUnsupported))
            },
        }
    }
    /// The whole caller envelope can stage this on its World clone. Structural
    /// failures never partially commit selection, clip, deadlines or counters.
    pub fn apply(&mut self,commands:&[Command],now:Instant)->io::Result<Vec<Outcome>>{
        if commands.is_empty()||commands.len()>32||self.observed.is_some_and(|previous|now<previous){return Err(bad("armament command bound or reversed server time"));}
        let mut next=self.clone();let mut outcomes=Vec::with_capacity(commands.len());
        for &command in commands {outcomes.push(next.one(command,now)?);}
        *self=next;Ok(outcomes)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn shot(state:&mut State,now:Instant)->Shell{
        let outcome=state.apply(&[Command::Shoot],now).unwrap();
        let Outcome::Shot{shell,..}=outcome[0]else{panic!("expected accepted source shot: {outcome:?}")};shell
    }
    #[test]fn ap_zero_other_owned_initial_stack_and_no_free_replenish(){
        let now=Instant::now();let source=PROFILES[Mount::Ms1Stock.index()];
        let mut state=State::new(Mount::Ms1Stock,[0,2,3],source.shots[1].compact_descr).unwrap();
        assert_eq!(shot(&mut state,now),source.shots[1]);assert_eq!(state.counts(),[0,1,3]);
        assert_eq!(state.apply(&[Command::Replenish],now).unwrap(),[Outcome::Refused(Refusal::ReplenishUnsupported)]);
        assert_eq!(state.counts(),[0,1,3]);assert_eq!(state.replenish_requests(),1);
        for counts in [[0,0,0],[96,1,0],[u16::MAX,1,0]]{assert!(State::new(Mount::Ms1Stock,counts,source.shots[1].compact_descr).is_err());}
        assert!(State::new(Mount::Ms1Stock,[0,1,0],source.shots[0].compact_descr).is_err());
    }
    #[test]fn full_stack_source_capacity_and_mounted_reload_are_authoritative(){
        let now=Instant::now();
        for source in PROFILES {
            let mut state=State::new(source.mount,[source.capacity,0,0],source.shots[0].compact_descr).unwrap();
            assert_eq!(shot(&mut state,now),source.shots[0]);
            assert_eq!(state.total(),source.capacity-1);
            assert_eq!(state.apply(&[Command::Shoot],now).unwrap(),[Outcome::Refused(Refusal::Reloading)]);
            let seconds=if source.clip_count>1{source.clip_interval_seconds}else{source.reload_seconds};
            assert!(!state.advance(now+Duration::from_secs_f64(seconds)-Duration::from_nanos(1)));
            assert!(state.advance(now+Duration::from_secs_f64(seconds)));
        }
    }
    #[test]fn wt128_has_six_but_150_has_four_and_reload_is_sixty_vs_fifty(){
        for (mount,count,seconds)in [(Mount::WtE100128,6,60.),(Mount::WtE100150,4,50.)]{
            let source=*crate::p06t_shells091::profile(mount);let start=Instant::now();
            let mut state=State::new(mount,[20,2,0],source.shots[0].compact_descr).unwrap();
            for index in 0..count {let at=start+Duration::from_secs_f64(index as f64*source.clip_interval_seconds);shot(&mut state,at);}
            assert_eq!(state.accepted(),count);assert_eq!(state.clip(),0);
            let last=start+Duration::from_secs_f64((count-1)as f64*source.clip_interval_seconds);
            assert_eq!(state.deadline(),Some(last+Duration::from_secs_f64(seconds)));
            assert!(!state.advance(last+Duration::from_secs_f64(seconds)-Duration::from_nanos(1)));
            assert!(state.advance(last+Duration::from_secs_f64(seconds)));assert_eq!(state.clip(),count as u8);
        }
    }
    #[test]fn queued_next_waits_until_magazine_boundary_and_does_not_rewrite_flying_shell(){
        let source=PROFILES[Mount::WtE100128.index()];let start=Instant::now();
        let mut state=State::new(source.mount,[12,6,0],source.shots[0].compact_descr).unwrap();
        let frozen=shot(&mut state,start);
        state.apply(&[Command::Select(Selection::Next,source.shots[1].compact_descr)],start).unwrap();
        assert!(state.advance(start+Duration::from_secs(2)));assert_eq!(state.current(),source.shots[0]);
        for index in 1..6{shot(&mut state,start+Duration::from_secs(index*2));}
        assert!(state.advance(start+Duration::from_secs(70)));assert_eq!(state.current(),source.shots[1]);
        assert_eq!(state.clip(),6);assert_eq!(frozen,source.shots[0]);assert_eq!(state.counts(),[6,6,0]);
    }
    #[test]fn switch_shoot_order_current_reload_empty_unknown_and_repeat_cannot_skip_reload(){
        let source=PROFILES[Mount::Is7Stock.index()];let start=Instant::now();
        let mut state=State::new(source.mount,[2,2,0],source.shots[0].compact_descr).unwrap();
        let first=state.apply(&[Command::Select(Selection::Current,source.shots[1].compact_descr),Command::Shoot],start).unwrap();
        assert_eq!(first,[Outcome::ReloadStarted,Outcome::Refused(Refusal::Reloading)]);assert_eq!(state.counts(),[2,2,0]);
        let deadline=state.deadline();
        state.apply(&[Command::Select(Selection::Current,source.shots[1].compact_descr)],start+Duration::from_secs(1)).unwrap();
        assert_eq!(state.deadline(),deadline);
        assert!(state.advance(start+Duration::from_secs_f64(13.7)));assert_eq!(shot(&mut state,start+Duration::from_secs_f64(13.7)),source.shots[1]);
        assert_eq!(state.apply(&[Command::Select(Selection::Current,source.shots[2].compact_descr),Command::Select(Selection::Next,65535)],start+Duration::from_secs_f64(13.7)).unwrap(),
            [Outcome::Refused(Refusal::Empty),Outcome::Refused(Refusal::UnknownShell)]);
        let mut other=State::new(source.mount,[2,2,0],source.shots[0].compact_descr).unwrap();
        let outcome=other.apply(&[Command::Shoot,Command::Select(Selection::Current,source.shots[1].compact_descr)],start).unwrap();
        assert!(matches!(outcome[0],Outcome::Shot{shell,..}if shell==source.shots[0]));assert_eq!(other.counts(),[1,2,0]);
    }
    #[test]fn structural_failure_cannot_commit_partial_state(){
        let source=PROFILES[Mount::Ms1Stock.index()];let start=Instant::now();
        let mut state=State::new(source.mount,[1,1,0],source.shots[0].compact_descr).unwrap();
        let before=state.clone();assert!(state.apply(&vec![Command::Shoot;33],start).is_err());assert_eq!(state,before);
        state.accepted=u32::MAX;let before=state.clone();assert!(state.apply(&[Command::Shoot],start).is_err());assert_eq!(state,before);
        state.accepted=0;state.advance(start+Duration::from_secs(1));let before=state.clone();
        assert!(state.apply(&[Command::Shoot],start).is_err());assert_eq!(state,before);
    }
    #[test]fn p06t_loader_and_ammo_damage_scale_only_remaining_full_reload(){
        let source=PROFILES[Mount::WtE100128.index()];let start=Instant::now();
        let mut state=State::new(source.mount,[12,0,0],source.shots[0].compact_descr).unwrap();
        state.apply(&[Command::ReloadClip],start).unwrap();assert_eq!(state.deadline(),Some(start+Duration::from_secs(60)));
        state.set_reload_scale(2.,start+Duration::from_secs(10)).unwrap();
        assert_eq!(state.deadline(),Some(start+Duration::from_secs(110)));assert_eq!(state.base_reload_seconds(),120.);
        let before=state.clone();for scale in [f64::NAN,0.9,4.1]{assert!(state.set_reload_scale(scale,start+Duration::from_secs(11)).is_err());assert_eq!(state,before);}
        state.set_reload_scale(4.,start+Duration::from_secs(20)).unwrap();
        assert_eq!(state.deadline(),Some(start+Duration::from_secs(200)));assert_eq!(state.base_reload_seconds(),240.);
        assert_eq!(state.counts(),[12,0,0]);
    }
}
