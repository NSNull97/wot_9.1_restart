//! Canonical source-bound armament candidate; not connected to the live World.
//! Explicit lab policy: quantities include shells in the clip; current switch
//! starts a complete reload, queued next switches at magazine completion.
//! No historical server scheduling fidelity is claimed by these rules.
//! CONTENT-0 2.6: automatic guns. One accepted Shoot starts a burst of
//! min(burst, clip, stack) shells; the first leaves at once, the rest at the
//! source burst interval on server time (`next_burst_shot`). The next burst or
//! the magazine reload counts from the last burst shell. Client 0.9.1 plays
//! the burst muzzle effects itself from `Vehicle.showShooting(burstCount)`.
use std::{io,time::{Duration,Instant}};
use crate::p06t_shells091::{Mount,Shell,PROFILES};

pub const POLICY:&str="test_lab.p06t.source-stacks-including-clip.v1";
/// Mounted clip ceiling (T-60/T7 Combat Car: 50 shells). Not a historical rule.
pub const MAX_CLIP:u8=64;
/// Mounted burst ceiling (0.9.1 source maximum is 5). Not a historical rule.
pub const MAX_BURST:u8=10;
/// Three installed 0.9 factors fit the HUD and clock. Damage can extend reloads by up to 4x.
pub(crate) const MIN_RELOAD_SCALE:f64=0.729;
pub(crate) const MIN_BASE_RELOAD_SECONDS:f64=0.1;
/// The mounted source of a gun. Unit tests may stage a synthetic automatic
/// gun on this thread (`tests::with_source`) without a rebuilt vehicle table.
fn mounted(mount:Mount)->crate::p06t_shells091::GunProfile{
    #[cfg(test)]
    if let Some(p)=tests::SOURCE.with(|cell|cell.get()).filter(|p|p.mount==mount){return p;}
    *crate::p06t_shells091::profile(mount)
}
fn bad(reason:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,reason)}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Selection {Current,Next}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Command {Shoot,Select(Selection,u16),ReloadClip,Replenish}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Refusal {Reloading,Empty,UnknownShell,SameShell,ReplenishUnsupported}
#[derive(Clone,Copy,Debug,PartialEq)]
pub enum Outcome {
    /// `burst`: shells of the burst this shot opens (the native showShooting
    /// count); 0 for a later shell of an already announced burst.
    Shot{shell:Shell,remaining:u16,clip:u8,burst:u8},Selected,ReloadStarted,Refused(Refusal)}
#[derive(Clone,Debug,PartialEq)]
pub struct State {
    mount:Mount,counts:[u16;3],current:usize,next:usize,clip:u8,
    until:Option<Instant>,magazine_reload:bool,observed:Option<Instant>,
    accepted:u32,rejected:u32,replenish:u32,reload_scale:f64,
    initial:[u16;3],fired:[u16;3],lost:[u16;3],
    /// Shells of the current burst still to leave, the server time of the
    /// next one, and the reload clock span published for the whole burst.
    burst_left:u8,burst_next:Option<Instant>,burst_span:f64,
}
// BW-01 wire codec (tools/bw01_wire_gen.py): State
impl crate::bw_wire::Wire for State {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{mount,counts,current,next,clip,until,magazine_reload,observed,accepted,rejected,replenish,reload_scale,initial,fired,lost,burst_left,burst_next,burst_span}=self;W::put(mount,bw_o);W::put(counts,bw_o);W::put(current,bw_o);W::put(next,bw_o);W::put(clip,bw_o);W::put(until,bw_o);W::put(magazine_reload,bw_o);W::put(observed,bw_o);W::put(accepted,bw_o);W::put(rejected,bw_o);W::put(replenish,bw_o);W::put(reload_scale,bw_o);W::put(initial,bw_o);W::put(fired,bw_o);W::put(lost,bw_o);W::put(burst_left,bw_o);W::put(burst_next,bw_o);W::put(burst_span,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{mount:W::get(bw_i)?,counts:W::get(bw_i)?,current:W::get(bw_i)?,next:W::get(bw_i)?,clip:W::get(bw_i)?,until:W::get(bw_i)?,magazine_reload:W::get(bw_i)?,observed:W::get(bw_i)?,accepted:W::get(bw_i)?,rejected:W::get(bw_i)?,replenish:W::get(bw_i)?,reload_scale:W::get(bw_i)?,initial:W::get(bw_i)?,fired:W::get(bw_i)?,lost:W::get(bw_i)?,burst_left:W::get(bw_i)?,burst_next:W::get(bw_i)?,burst_span:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl State {
    pub fn new(mount:Mount,counts:[u16;3],initial:u16)->io::Result<Self>{
        let source=mounted(mount);
        let total=counts.iter().try_fold(0u16,|n,c|n.checked_add(*c)).ok_or_else(||bad("armament count overflow"))?;
        let current=source.shots.iter().position(|s|s.compact_descr==initial&&!s.is_absent()).ok_or_else(||bad("armament initial shell source"))?;
        // SPG-02: an absent cell (fewer than three source shells) is never loaded.
        if source.shots.iter().zip(counts).any(|(s,c)|s.is_absent()&&c>0){return Err(bad("armament absent cell loaded"));}
        let burst=source.burst_count;
        if burst==0||burst>MAX_BURST||burst==1&&source.burst_interval_seconds!=0.
            ||burst>1&&(source.clip_count==1||burst>source.clip_count||!source.burst_interval_seconds.is_finite()
                ||!(0.01..=2.).contains(&source.burst_interval_seconds)){return Err(bad("armament mounted burst bounds"));}
        if total==0||total>source.capacity||counts[current]==0||source.clip_count==0||source.clip_count>MAX_CLIP
            ||!source.reload_seconds.is_finite()||!(MIN_BASE_RELOAD_SECONDS..=120.).contains(&source.reload_seconds)
            ||!source.clip_interval_seconds.is_finite()||!(0. ..=120.).contains(&source.clip_interval_seconds)
            ||source.clip_count>1&&source.clip_interval_seconds<=0. {return Err(bad("armament mounted source bounds"));}
        Ok(Self{mount,counts,current,next:current,clip:counts[current].min(u16::from(source.clip_count))as u8,
            until:None,magazine_reload:false,observed:None,accepted:0,rejected:0,replenish:0,reload_scale:1.,
            initial:counts,fired:[0;3],lost:[0;3],burst_left:0,burst_next:None,burst_span:0.})
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
        self.until=None;self.magazine_reload=false;self.end_burst();self.burst_span=0.;Ok(removed)
    }
    pub fn total(&self)->u16{self.counts.iter().sum()}
    pub fn current(&self)->Shell{mounted(self.mount).shots[self.current]}
    pub fn next(&self)->Shell{mounted(self.mount).shots[self.next]}
    pub fn clip(&self)->u8{self.clip}
    pub fn deadline(&self)->Option<Instant>{self.until}
    pub fn accepted(&self)->u32{self.accepted}
    pub fn rejected(&self)->u32{self.rejected}
    pub fn replenish_requests(&self)->u32{self.replenish}
    pub fn base_reload_seconds(&self)->f32{
        let source=mounted(self.mount);
        // One reload clock covers a burst: from its first shell to the next ready shot.
        if self.burst_span>0.&&self.until.is_some(){return self.burst_span as f32;}
        if self.magazine_reload||source.clip_count==1 {(source.reload_seconds*self.reload_scale)as f32}
        else {source.clip_interval_seconds as f32}
    }
    pub fn remaining_seconds(&self,now:Instant)->f32{
        self.until.map_or(0.,|until|until.saturating_duration_since(now).as_secs_f32())
    }
    pub fn set_reload_scale(&mut self,scale:f64,now:Instant)->io::Result<()>{
        if !(MIN_RELOAD_SCALE..=4.).contains(&scale)||self.observed.is_some_and(|previous|now<previous){return Err(bad("armament capability scale/time"));}
        let mut next=self.clone();next.advance(now);
        if scale!=next.reload_scale&&(next.magazine_reload||mounted(next.mount).clip_count==1) {
            if let Some(until)=next.until{
                // Only the reload after the last burst shell is scaled, never the burst cadence.
                let from=next.burst_end()?.map_or(now,|end|end.max(now));
                let seconds=until.saturating_duration_since(from).as_secs_f64()*scale/next.reload_scale;
                let scaled=from.checked_add(Duration::from_secs_f64(seconds)).ok_or_else(||bad("scaled reload overflow"))?;
                if next.burst_span>0. {
                    next.burst_span+=if scaled>=until{scaled.duration_since(until).as_secs_f64()}else{-until.duration_since(scaled).as_secs_f64()};
                }
                next.until=Some(scaled);
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
        // A burst shell never outlives its reload; an unfired one stays loaded.
        self.until=None;self.end_burst();self.burst_span=0.;
        if self.magazine_reload {
            if self.counts[self.next]>0 {self.current=self.next;}
            else if self.counts[self.current]==0 {
                if let Some(index)=self.counts.iter().position(|count|*count>0){self.current=index;}
            }
            self.next=self.current;
            self.clip=self.counts[self.current].min(u16::from(mounted(self.mount).clip_count))as u8;
        }
        self.magazine_reload=false;true
    }
    fn reload(&mut self,now:Instant,magazine:bool)->io::Result<()> {
        let source=mounted(self.mount);
        let seconds=if magazine||source.clip_count==1{source.reload_seconds*self.reload_scale}else{source.clip_interval_seconds};
        self.until=Some(now.checked_add(Duration::from_secs_f64(seconds)).ok_or_else(||bad("armament clock overflow"))?);
        self.magazine_reload=magazine;Ok(())
    }
    fn end_burst(&mut self){self.burst_left=0;self.burst_next=None;}
    /// Server time of the last shell of the running burst.
    fn burst_end(&self)->io::Result<Option<Instant>>{
        let Some(next)=self.burst_next else {return Ok(None)};
        let interval=mounted(self.mount).burst_interval_seconds;
        let rest=Duration::from_secs_f64(interval*f64::from(self.burst_left.saturating_sub(1)));
        next.checked_add(rest).map(Some).ok_or_else(||bad("armament burst clock overflow"))
    }
    pub fn burst_pending(&self)->bool{self.burst_left>0}
    /// The gun stopped mid-burst (destroyed/unmanned): the unfired shells stay
    /// in clip and stack; the reload already running is kept as committed.
    pub fn abort_burst(&mut self){self.end_burst();}
    fn fire_one(&mut self)->io::Result<Shell>{
        if self.counts[self.current]==0||self.clip==0{return Err(bad("armament fire source"));}
        let shell=self.current();self.counts[self.current]-=1;self.clip-=1;
        self.fired[self.current]=self.fired[self.current].checked_add(1).ok_or_else(||bad("armament fired stack overflow"))?;
        self.accepted=self.accepted.checked_add(1).ok_or_else(||bad("armament shot counter"))?;
        Ok(shell)
    }
    /// The next shell of the running burst once its server time is due.
    /// Called by the world step, at most MAX_BURST times per burst; each Some
    /// is one projectile to launch. The burst never reads client time.
    pub fn next_burst_shot(&mut self,now:Instant)->io::Result<Option<Outcome>>{
        if self.burst_left==0{return Ok(None);}
        if self.observed.is_some_and(|previous|now<previous){return Err(bad("armament burst reversed server time"));}
        let due=self.burst_next.ok_or_else(||bad("armament burst clock"))?;
        if now<due{return Ok(None);}
        let mut next=self.clone();next.observed=Some(now);
        let shell=next.fire_one()?;next.burst_left-=1;
        let interval=mounted(next.mount).burst_interval_seconds;
        next.burst_next=if next.burst_left>0{Some(due.checked_add(Duration::from_secs_f64(interval)).ok_or_else(||bad("armament burst clock overflow"))?)}else{None};
        let outcome=Outcome::Shot{shell,remaining:next.counts[next.current],clip:next.clip,burst:0};
        *self=next;Ok(Some(outcome))
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
                let source=mounted(self.mount);
                // Client `__showTimedOutShooting`: min(burst, stack) and, with a clip, min(.., clip).
                let burst=source.burst_count.min(self.clip).min(self.counts[self.current].min(255)as u8);
                let shell=self.fire_one()?;
                let rest=burst-1;
                let magazine=self.clip==rest||self.counts[self.current]==u16::from(rest);
                let last=now.checked_add(Duration::from_secs_f64(source.burst_interval_seconds*f64::from(rest))).ok_or_else(||bad("armament burst clock overflow"))?;
                self.reload(last,magazine)?;
                if rest>0 {
                    self.burst_left=rest;
                    self.burst_next=Some(now.checked_add(Duration::from_secs_f64(source.burst_interval_seconds)).ok_or_else(||bad("armament burst clock overflow"))?);
                    self.burst_span=self.until.ok_or_else(||bad("armament burst reload"))?.duration_since(now).as_secs_f64();
                }else{self.burst_span=0.;}
                Ok(Outcome::Shot{shell,remaining:self.counts[self.current],clip:self.clip,burst})
            },
            Command::Select(mode,compact)=>{
                let Some(index)=mounted(self.mount).shots.iter().position(|s|s.compact_descr==compact)else{return self.refuse(Refusal::UnknownShell)};
                if self.counts[index]==0{return self.refuse(Refusal::Empty);}
                if mode==Selection::Next {self.next=index;return Ok(Outcome::Selected);}
                // A running burst is never cut by a shell change.
                if self.burst_left>0{return self.refuse(Refusal::Reloading);}
                if index==self.current{return self.refuse(Refusal::SameShell);}
                self.current=index;self.next=index;self.clip=0;
                self.reload(now,true)?;Ok(Outcome::ReloadStarted)
            },
            Command::ReloadClip=>{
                let source=mounted(self.mount);
                if source.clip_count==1||self.counts[self.current]==0{return self.refuse(Refusal::Empty);}
                // An existing full reload is never extended by repeated input.
                if self.burst_left>0||self.magazine_reload&&self.until.is_some(){return self.refuse(Refusal::Reloading);}
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
pub(crate) use tests::{auto as test_auto,with_source as test_with_source};
#[cfg(test)]
mod tests {
    use super::*;
    use crate::p06t_shells091::GunProfile;
    thread_local!{pub(super) static SOURCE:std::cell::Cell<Option<GunProfile>>=const{std::cell::Cell::new(None)};}
    /// A synthetic automatic gun on the MS-1 mount (its shells), with 0.9.1
    /// loader semantics: interval = 60/rate, burst interval 0 for a single shot.
    pub(crate) fn auto(clip:u8,burst:u8,rate:f64,reload:f64,capacity:u16)->GunProfile{
        let mut p=PROFILES[Mount::Ms1Stock.index()];
        p.clip_count=clip;p.clip_interval_seconds=if clip>1{60./rate}else{0.};p.burst_count=burst;
        p.burst_interval_seconds=if burst>1{60./rate}else{0.};p.reload_seconds=reload;p.capacity=capacity;p.clip_from_mounted_source=true;p
    }
    pub(crate) fn with_source<R>(p:GunProfile,f:impl FnOnce()->R)->R{SOURCE.with(|c|c.set(Some(p)));let r=f();SOURCE.with(|c|c.set(None));r}
    fn secs(s:f64)->Duration{Duration::from_secs_f64(s)}
    fn burst_shot(state:&mut State,now:Instant)->Option<(u16,u8,u8)>{
        state.next_burst_shot(now).unwrap().map(|o|{let Outcome::Shot{remaining,clip,burst,..}=o else{panic!("{o:?}")};(remaining,clip,burst)})
    }
    /// PzI 20 mm KwK 30 (0.9.1: shared clip 10/280, burst 2/280; vehicle reload 4.3, maxAmmo 240).
    #[test]fn pzi_burst_of_two_from_a_ten_shell_clip_on_server_time(){with_source(auto(10,2,280.,4.3,240),||{
        let p=auto(10,2,280.,4.3,240);let i=60./280.;let t0=Instant::now();
        let mut s=State::new(Mount::Ms1Stock,[50,0,0],p.shots[0].compact_descr).unwrap();assert_eq!(s.clip(),10);
        let out=s.apply(&[Command::Shoot,Command::Shoot],t0).unwrap();
        assert!(matches!(out[0],Outcome::Shot{remaining:49,clip:9,burst:2,..}),"{out:?}");
        assert_eq!(out[1],Outcome::Refused(Refusal::Reloading));assert!(s.burst_pending());
        // The second shell leaves one burst interval later, never earlier, and announces nothing.
        assert_eq!(burst_shot(&mut s,t0+secs(i)-Duration::from_nanos(1)),None);
        assert_eq!(burst_shot(&mut s,t0+secs(i)),Some((48,8,0)));assert!(!s.burst_pending());
        assert_eq!(burst_shot(&mut s,t0+secs(i)),None);
        // Next burst: clip interval from the last shell; one clock spans the burst.
        assert_eq!(s.deadline(),Some(t0+secs(i)+secs(i)));assert!((f64::from(s.base_reload_seconds())-2.*i).abs()<1e-6);
        assert!(s.remaining_seconds(t0)<=s.base_reload_seconds());
        let mut t=s.deadline().unwrap();
        for left in [7u8,5,3] {
            assert!(s.advance(t));assert!(matches!(s.apply(&[Command::Shoot],t).unwrap()[0],Outcome::Shot{burst:2,..}));
            assert_eq!(burst_shot(&mut s,t+secs(i)).map(|r|r.1),Some(left-1));t=s.deadline().unwrap();
        }
        // Last burst empties the clip: the 4.3 s magazine reload starts at its last shell.
        assert!(s.advance(t));s.apply(&[Command::Shoot],t).unwrap();burst_shot(&mut s,t+secs(i)).unwrap();
        assert_eq!((s.clip(),s.total(),s.accepted()),(0,40,10));
        assert_eq!(s.deadline(),Some(t+secs(i)+secs(4.3)));
        assert!(!s.advance(t+secs(i)+secs(4.3)-Duration::from_nanos(1)));assert!(s.advance(t+secs(i)+secs(4.3)));assert_eq!(s.clip(),10);
    })}
    #[test]fn burst_is_cut_by_clip_and_stack_like_the_client_prediction(){with_source(auto(15,3,600.,7.7,750),||{
        let p=auto(15,3,600.,7.7,750);let t0=Instant::now();
        let mut s=State::new(Mount::Ms1Stock,[2,3,0],p.shots[0].compact_descr).unwrap();assert_eq!(s.clip(),2);
        assert!(matches!(s.apply(&[Command::Shoot],t0).unwrap()[0],Outcome::Shot{burst:2,clip:1,remaining:1,..}));
        assert_eq!(burst_shot(&mut s,t0+secs(0.1)),Some((0,0,0)));assert!(!s.burst_pending());
        // The stack ran dry inside the burst: magazine reload from the last shell, then the next stack.
        assert_eq!(s.deadline(),Some(t0+secs(0.1)+secs(7.7)));assert!(s.advance(s.deadline().unwrap()));
        assert_eq!((s.current(),s.clip(),s.counts()),(p.shots[1],3,[0,3,0]));
    })}
    #[test]fn running_burst_refuses_shell_change_and_reload_but_keeps_next_selection(){with_source(auto(30,5,450.,10.,900),||{
        let p=auto(30,5,450.,10.,900);let t0=Instant::now();let i=60./450.;let ms=Duration::from_millis(1);
        let mut s=State::new(Mount::Ms1Stock,[20,20,0],p.shots[0].compact_descr).unwrap();
        s.apply(&[Command::Shoot],t0).unwrap();
        assert_eq!(s.apply(&[Command::Select(Selection::Current,p.shots[1].compact_descr),Command::ReloadClip,
            Command::Select(Selection::Next,p.shots[1].compact_descr)],t0+secs(i/2.)).unwrap(),
            [Outcome::Refused(Refusal::Reloading),Outcome::Refused(Refusal::Reloading),Outcome::Selected]);
        for k in 1..5 {assert!(burst_shot(&mut s,t0+secs(i*k as f64)+ms).is_some());}
        assert_eq!((s.counts(),s.clip(),s.current(),s.next()),([15,20,0],15,p.shots[0],p.shots[1]));
        // Catch-up after a late step: every due shell leaves once, in order, on its own schedule.
        let t1=s.deadline().unwrap();assert!(s.advance(t1));s.apply(&[Command::Shoot],t1).unwrap();
        let deadline=s.deadline();
        assert!(burst_shot(&mut s,t1+secs(3.5*i)).is_some()&&burst_shot(&mut s,t1+secs(3.5*i)).is_some()&&burst_shot(&mut s,t1+secs(3.5*i)).is_some());
        assert_eq!(burst_shot(&mut s,t1+secs(3.5*i)),None);assert_eq!(s.deadline(),deadline);
        assert_eq!(burst_shot(&mut s,t1+secs(4.*i)+ms).map(|r|r.0),Some(10));
        // A reversed server clock is structural and commits nothing.
        s.apply(&[Command::Shoot],t1+secs(6.*i)).unwrap();let before=s.clone();
        assert!(s.next_burst_shot(t1+secs(5.*i)).is_err());assert_eq!(s,before);
    })}
    #[test]fn reload_scale_mid_burst_scales_only_the_reload_after_the_last_shell(){with_source(auto(50,5,600.,33.,1000),||{
        let p=auto(50,5,600.,33.,1000);let t0=Instant::now();
        let mut s=State::new(Mount::Ms1Stock,[5,0,0],p.shots[0].compact_descr).unwrap();
        s.apply(&[Command::Shoot],t0).unwrap();assert_eq!(s.deadline(),Some(t0+secs(0.4)+secs(33.)));
        s.set_reload_scale(2.,t0+secs(0.05)).unwrap();
        let expected=t0+secs(0.4)+secs(66.);let got=s.deadline().unwrap();
        assert!(got.max(expected).duration_since(got.min(expected))<Duration::from_micros(1),"{got:?} {expected:?}");
        assert!((f64::from(s.base_reload_seconds())-66.4).abs()<1e-3);assert!(s.remaining_seconds(t0+secs(0.05))<=s.base_reload_seconds());
        for k in 1..5 {assert!(burst_shot(&mut s,t0+secs(0.1*k as f64)+Duration::from_millis(1)).is_some());}
        assert_eq!((s.total(),s.accepted()),(0,5));
    })}
    #[test]fn detonation_and_aborted_burst_keep_conservation(){with_source(auto(40,5,550.,22.9,1800),||{
        let p=auto(40,5,550.,22.9,1800);let t0=Instant::now();
        let mut s=State::new(Mount::Ms1Stock,[100,0,0],p.shots[0].compact_descr).unwrap();
        s.apply(&[Command::Shoot],t0).unwrap();burst_shot(&mut s,t0+secs(0.2)).unwrap();
        let mut aborted=s.clone();aborted.abort_burst();
        assert!(!aborted.burst_pending()&&aborted.next_burst_shot(t0+secs(1.)).unwrap().is_none());
        assert_eq!((aborted.total(),aborted.clip()),(98,38));
        assert_eq!(s.lose_loaded_for_detonation().unwrap(),[98,0,0]);
        assert!(!s.burst_pending()&&s.next_burst_shot(t0+secs(1.)).unwrap().is_none());
        assert_eq!((s.fired(),s.lost(),s.accepted()),([2,0,0],[98,0,0],2));
    })}
    #[test]fn automatic_gun_source_bounds_fail_closed(){
        let cases=[auto(10,11,280.,4.,240),auto(1,2,280.,4.,240),auto(4,5,280.,4.,240),auto(MAX_CLIP+1,2,280.,4.,240),
            {let mut p=auto(10,2,280.,4.,240);p.burst_interval_seconds=0.;p},{let mut p=auto(10,1,280.,4.,240);p.burst_interval_seconds=0.1;p},
            {let mut p=auto(10,2,280.,4.,240);p.burst_interval_seconds=f64::NAN;p}];
        for p in cases {with_source(p,||assert!(State::new(Mount::Ms1Stock,[10,0,0],p.shots[0].compact_descr).is_err(),"{p:?}"));}
        for p in [auto(50,5,600.,33.,1000),auto(10,1,55.,12.,120),auto(5,1,120.,5.,80)] {
            with_source(p,||assert!(State::new(Mount::Ms1Stock,[60.min(p.capacity),0,0],p.shots[0].compact_descr).is_ok(),"{p:?}"));
        }
    }
    /// GB75 AT 7 (0.9.1 vehicle clip 10/55, no burst): a long drum is single shots at the clip interval.
    #[test]fn long_drum_without_burst_is_single_shots_at_clip_interval(){with_source(auto(10,1,55.,12.,120),||{
        let p=auto(10,1,55.,12.,120);let t0=Instant::now();let i=60./55.;
        let mut s=State::new(Mount::Ms1Stock,[30,0,0],p.shots[0].compact_descr).unwrap();
        let mut t=t0;
        for _ in 0..10 {s.advance(t);assert!(matches!(s.apply(&[Command::Shoot],t).unwrap()[0],Outcome::Shot{burst:1,..}));assert!(!s.burst_pending());
            let next=s.deadline().unwrap();if s.clip()>0{assert_eq!(next,t+secs(i));}t=next;}
        assert_eq!(s.clip(),0);assert_eq!(s.base_reload_seconds(),12.);
    })}
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
        let before=state.clone();for scale in [f64::NAN,0.7,4.1]{assert!(state.set_reload_scale(scale,start+Duration::from_secs(11)).is_err());assert_eq!(state,before);}
        state.set_reload_scale(4.,start+Duration::from_secs(20)).unwrap();
        assert_eq!(state.deadline(),Some(start+Duration::from_secs(200)));assert_eq!(state.base_reload_seconds(),240.);
        assert_eq!(state.counts(),[12,0,0]);
    }

    #[test]
    fn content0_s5_rammer_shortens_full_reload_and_preserves_intershot_cadence(){
        let now=Instant::now();
        let profile=PROFILES[Mount::WtE100128.index()];
        let mut drum=State::new(profile.mount,[12,0,0],profile.shots[0].compact_descr).unwrap();
        drum.set_reload_scale(0.9,now).unwrap();
        drum.apply(&[Command::Shoot],now).unwrap();
        assert_eq!(drum.deadline(),Some(now+Duration::from_secs(2)));
        drum.set_reload_scale(1.8,now+Duration::from_secs(1)).unwrap();
        assert_eq!(drum.deadline(),Some(now+Duration::from_secs(2)));
        drum.set_reload_scale(0.9,now+Duration::from_secs(2)).unwrap();
        drum.apply(&[Command::ReloadClip],now+Duration::from_secs(2)).unwrap();
        assert_eq!(drum.deadline(),Some(now+Duration::from_secs(56)));

        let profile=PROFILES[Mount::Ms1Stock.index()];
        let mut single=State::new(profile.mount,[12,0,0],profile.shots[0].compact_descr).unwrap();
        single.set_reload_scale(0.9,now).unwrap();
        single.apply(&[Command::Shoot],now).unwrap();
        assert_eq!(single.deadline(),Some(now+Duration::from_millis(2250)));
        single.set_reload_scale(1.8,now+Duration::from_millis(250)).unwrap();
        assert_eq!(single.deadline(),Some(now+Duration::from_millis(4250)));
    }
}
