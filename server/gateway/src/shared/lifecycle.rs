//! Authoritative battle phases; no native entity IDs or client clock enter here.
//! Capture radius/rate/contention are explicit test_lab rules, not historical claims.
use std::io;

pub const POLICY: &str = "test_lab.ctf-lifecycle-v1";
pub const MAX_ACTORS: usize = super::model::MAX_ACTORS;
pub const MAX_STEP_MS: u64 = 1_000;
const COMPLETE: u64 = 100_000;

fn bad(reason: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, format!("battle lifecycle: {reason}"))
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Base { pub owner: u8, pub xz: [f32; 2], pub radius: f32 }
// BW-01 wire codec (tools/bw01_wire_gen.py): Base
impl crate::bw_wire::Wire for Base {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{owner,xz,radius}=self;W::put(owner,bw_o);W::put(xz,bw_o);W::put(radius,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{owner:W::get(bw_i)?,xz:W::get(bw_i)?,radius:W::get(bw_i)?})}
}
// end BW-01 wire codec

#[derive(Clone, Debug, PartialEq)]
pub struct Rules {
    pub prebattle_ms: u64, pub battle_ms: u64, pub afterbattle_ms: u64,
    pub bases: [Base; 2],
}
// BW-01 wire codec (tools/bw01_wire_gen.py): Rules
impl crate::bw_wire::Wire for Rules {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{prebattle_ms,battle_ms,afterbattle_ms,bases}=self;W::put(prebattle_ms,bw_o);W::put(battle_ms,bw_o);W::put(afterbattle_ms,bw_o);W::put(bases,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{prebattle_ms:W::get(bw_i)?,battle_ms:W::get(bw_i)?,afterbattle_ms:W::get(bw_i)?,bases:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl Rules {
    /// Rules of one registry map: the client's ctf bases and round length
    /// (arena_defs), the accepted 30 s / 8 s periods and the accepted 50 m
    /// test_lab capture radius. A map without two ctf bases is unsupported.
    pub fn for_map(map: crate::map_profile091::MapId) -> io::Result<Self> {
        let profile = map.spec();
        let [a, b] = profile.ctf_bases.ok_or_else(|| bad("map has no client ctf bases"))?;
        let rules = Self { prebattle_ms: 30_000, battle_ms: u64::from(profile.round_length_s) * 1_000, afterbattle_ms: 8_000,
            bases: [Base { owner: 1, xz: a, radius: 50. }, Base { owner: 2, xz: b, radius: 50. }] };
        rules.validate()?;
        Ok(rules)
    }
    pub fn prohorovka() -> Self {
        Self { prebattle_ms: 30_000, battle_ms: 900_000, afterbattle_ms: 8_000,
            bases: [Base { owner: 1, xz: [-125.100021, 448.300110], radius: 50. },
                Base { owner: 2, xz: [51.599991, -447.], radius: 50. }] }
    }
    fn validate(&self) -> io::Result<()> {
        if !(1_000..=60_000).contains(&self.prebattle_ms) || !(1_000..=3_000_000).contains(&self.battle_ms)
            || !(1_000..=30_000).contains(&self.afterbattle_ms) { return Err(bad("period bounds")); }
        for (i, base) in self.bases.iter().enumerate() {
            if base.owner != i as u8 + 1 || !base.xz.iter().all(|v| v.is_finite() && v.abs() <= 2_000.)
                || !base.radius.is_finite() || !(5. ..=100.).contains(&base.radius) { return Err(bad("base bounds")); }
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Phase { Waiting, Prebattle, Battle, Afterbattle }
// BW-01 wire codec (tools/bw01_wire_gen.py): Phase
impl crate::bw_wire::Wire for Phase {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){match self {Self::Waiting=>bw_o.tag(0),Self::Prebattle=>bw_o.tag(1),Self::Battle=>bw_o.tag(2),Self::Afterbattle=>bw_o.tag(3),}}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{match bw_i.tag()? {0=>Ok(Self::Waiting),1=>Ok(Self::Prebattle),2=>Ok(Self::Battle),3=>Ok(Self::Afterbattle),t=>crate::bw_wire::variant(t)}}
}
// end BW-01 wire codec
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Reason { Elimination, Capture, Timeout, NoContest, Forfeit }
// BW-01 wire codec (tools/bw01_wire_gen.py): Reason
impl crate::bw_wire::Wire for Reason {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){match self {Self::Elimination=>bw_o.tag(0),Self::Capture=>bw_o.tag(1),Self::Timeout=>bw_o.tag(2),Self::NoContest=>bw_o.tag(3),Self::Forfeit=>bw_o.tag(4),}}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{match bw_i.tag()? {0=>Ok(Self::Elimination),1=>Ok(Self::Capture),2=>Ok(Self::Timeout),3=>Ok(Self::NoContest),4=>Ok(Self::Forfeit),t=>crate::bw_wire::variant(t)}}
}
// end BW-01 wire codec
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Outcome { pub winner: u8, pub reason: Reason, pub ended_ms: u64 }
// BW-01 wire codec (tools/bw01_wire_gen.py): Outcome
impl crate::bw_wire::Wire for Outcome {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{winner,reason,ended_ms}=self;W::put(winner,bw_o);W::put(reason,bw_o);W::put(ended_ms,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{winner:W::get(bw_i)?,reason:W::get(bw_i)?,ended_ms:W::get(bw_i)?})}
}
// end BW-01 wire codec
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Member {
    pub team: u8, pub present: bool, pub ready: bool, pub alive: bool,
    pub position: [f32; 3], pub damage_epoch: u32, pub last_damager: Option<usize>,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Progress { pub owner: u8, pub points: u8, pub stopped: bool }
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct View {
    pub phase: Phase, pub ends_ms: Option<u64>, pub length_ms: u64,
    pub bases: [Progress; 2], pub outcome: Option<Outcome>,
}
#[derive(Clone, Debug, PartialEq)]
pub struct State {
    rules: Rules, phase: Phase, last_ms: u64, entered_ms: u64, battle_start_ms: Option<u64>,
    outcome: Option<Outcome>, progress: [u64; 2], stopped: [bool; 2],
    damage_epochs: Vec<u32>, capture_earned: Vec<u64>, capture_dropped: Vec<u32>, revision: u64,
}
// BW-01 wire codec (tools/bw01_wire_gen.py): State
impl crate::bw_wire::Wire for State {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{rules,phase,last_ms,entered_ms,battle_start_ms,outcome,progress,stopped,damage_epochs,capture_earned,capture_dropped,revision}=self;W::put(rules,bw_o);W::put(phase,bw_o);W::put(last_ms,bw_o);W::put(entered_ms,bw_o);W::put(battle_start_ms,bw_o);W::put(outcome,bw_o);W::put(progress,bw_o);W::put(stopped,bw_o);W::put(damage_epochs,bw_o);W::put(capture_earned,bw_o);W::put(capture_dropped,bw_o);W::put(revision,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{rules:W::get(bw_i)?,phase:W::get(bw_i)?,last_ms:W::get(bw_i)?,entered_ms:W::get(bw_i)?,battle_start_ms:W::get(bw_i)?,outcome:W::get(bw_i)?,progress:W::get(bw_i)?,stopped:W::get(bw_i)?,damage_epochs:W::get(bw_i)?,capture_earned:W::get(bw_i)?,capture_dropped:W::get(bw_i)?,revision:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl State {
    pub fn new(rules: Rules) -> io::Result<Self> {
        rules.validate()?;
        Ok(Self { rules, phase: Phase::Waiting, last_ms: 0, entered_ms: 0, battle_start_ms: None,
            outcome: None, progress: [0; 2], stopped: [false; 2], damage_epochs: Vec::new(),
            capture_earned: Vec::new(), capture_dropped: Vec::new(), revision: 1 })
    }
    /// Readonly constructor-state proof for a new explicit pristine roster.
    /// Waiting/revision1 alone can hide already advanced member/clock cursors.
    pub(super) fn is_pristine(&self)->bool{
        self.phase==Phase::Waiting&&self.last_ms==0&&self.entered_ms==0&&self.battle_start_ms.is_none()
            &&self.outcome.is_none()&&self.progress==[0;2]&&self.stopped==[false;2]
            &&self.damage_epochs.is_empty()&&self.capture_earned.is_empty()&&self.capture_dropped.is_empty()&&self.revision==1
    }
    pub fn phase(&self) -> Phase { self.phase }
    pub fn revision(&self) -> u64 { self.revision }
    pub fn allows_actions(&self) -> bool { self.phase == Phase::Battle }
    pub fn outcome(&self) -> Option<Outcome> { self.outcome }
    pub fn battle_start_ms(&self) -> Option<u64> { self.battle_start_ms }
    pub fn capture_points(&self, slot: usize) -> u16 { self.capture_earned.get(slot).map_or(0, |n| (n / 1_000).min(600) as u16) }
    pub fn dropped_capture_points(&self, slot: usize) -> u16 { self.capture_dropped.get(slot).copied().unwrap_or(0).min(600) as u16 }
    pub fn elapsed_battle_ms(&self) -> u64 {
        self.battle_start_ms.map_or(0, |start| self.outcome.map_or(self.last_ms, |o| o.ended_ms).saturating_sub(start))
    }
    pub fn ready_to_return(&self, now_ms: u64) -> bool {
        self.outcome.is_some_and(|o| now_ms >= o.ended_ms.saturating_add(self.rules.afterbattle_ms))
    }
    pub fn view(&self) -> View {
        let (ends_ms, length_ms) = match self.phase {
            Phase::Waiting => (None, 0),
            Phase::Prebattle => (Some(self.entered_ms + self.rules.prebattle_ms), self.rules.prebattle_ms),
            Phase::Battle => (self.battle_start_ms.map(|t| t + self.rules.battle_ms), self.rules.battle_ms),
            Phase::Afterbattle => (self.outcome.map(|o| o.ended_ms + self.rules.afterbattle_ms), self.rules.afterbattle_ms),
        };
        View { phase: self.phase, ends_ms, length_ms,
            bases: std::array::from_fn(|i| Progress { owner: i as u8 + 1,
                points: (self.progress[i] / 1_000) as u8, stopped: self.stopped[i] }), outcome: self.outcome }
    }
    fn finish(&mut self, winner: u8, reason: Reason, now_ms: u64) {
        self.outcome = Some(Outcome { winner, reason, ended_ms: now_ms });
        self.phase = Phase::Afterbattle;
    }
    /// Atomic: a malformed last member or backwards clock cannot mutate progress.
    pub fn advance(&mut self, now_ms: u64, members: &[Member]) -> io::Result<bool> {
        if now_ms < self.last_ms || now_ms > 3_600_000 || now_ms - self.last_ms > MAX_STEP_MS
            || !(2..=MAX_ACTORS).contains(&members.len()) || (!self.damage_epochs.is_empty() && self.damage_epochs.len() != members.len()) {
            return Err(bad("clock/membership bound"));
        }
        for (i, member) in members.iter().enumerate() {
            if !(1..=2).contains(&member.team) || !member.position.iter().all(|v| v.is_finite() && v.abs() <= 2_000.)
                || member.last_damager.is_some_and(|slot| slot >= members.len())
                || self.damage_epochs.get(i).is_some_and(|old| member.damage_epoch < *old) { return Err(bad("member")); }
        }
        if !members.iter().any(|a| a.team == 1) || !members.iter().any(|a| a.team == 2) { return Err(bad("two teams required")); }
        let old = self.view();
        let mut next = self.clone();
        let dt = now_ms - next.last_ms;
        next.last_ms = now_ms;
        if next.damage_epochs.is_empty() {
            next.damage_epochs = members.iter().map(|a| a.damage_epoch).collect();
            next.capture_earned = vec![0; members.len()]; next.capture_dropped = vec![0; members.len()];
        }
        if matches!(next.phase, Phase::Waiting | Phase::Prebattle) && members.iter().any(|a| !a.present) {
            let remaining = [1,2].map(|team| members.iter().any(|a| a.team == team && a.present && a.alive));
            next.finish(if remaining[0] && !remaining[1] {1} else if remaining[1] && !remaining[0] {2} else {0},
                Reason::Forfeit,now_ms);
        }
        if next.phase == Phase::Waiting && now_ms >= 90_000 { next.finish(0,Reason::NoContest,now_ms); }
        if next.phase == Phase::Waiting && members.iter().all(|a| a.present && a.ready) {
            next.phase = Phase::Prebattle; next.entered_ms = now_ms;
        }
        if next.phase == Phase::Prebattle {
            if now_ms >= next.entered_ms + next.rules.prebattle_ms {
                next.battle_start_ms = Some(next.entered_ms + next.rules.prebattle_ms);
                next.phase = Phase::Battle;
            }
        }
        if next.phase == Phase::Battle {
            let alive = [1, 2].map(|team| members.iter().any(|a| a.team == team && a.alive));
            if !alive[0] || !alive[1] {
                next.finish(if alive[0] { 1 } else if alive[1] { 2 } else { 0 },
                    if alive.iter().any(|v| *v) { Reason::Elimination } else { Reason::NoContest }, now_ms);
            } else if [1,2].iter().any(|team|!members.iter().any(|a|a.team==*team&&a.present&&a.alive)) {
                let present = [1,2].map(|team| members.iter().any(|a| a.team == team && a.present && a.alive));
                next.finish(if present[0] && !present[1] {1} else if present[1] && !present[0] {2} else {0},Reason::Forfeit,now_ms);
            } else {
                // Clamp integration to the active period, including its first tick.
                let start = next.battle_start_ms.ok_or_else(|| bad("battle clock"))?;
                let elapsed = now_ms.min(start + next.rules.battle_ms).saturating_sub((now_ms - dt).max(start));
                for i in 0..2 {
                    let base = next.rules.bases[i];
                    let inside = |a: &Member| a.present && a.alive && {
                        let x = f64::from(a.position[0]) - f64::from(base.xz[0]);
                        let z = f64::from(a.position[2]) - f64::from(base.xz[1]);
                        x*x + z*z <= f64::from(base.radius).powi(2)
                    };
                    let capturers: Vec<usize> = members.iter().enumerate().filter(|(_, a)| a.team != base.owner && inside(a)).map(|(slot, _)| slot).collect();
                    let damaged = capturers.iter().any(|slot| members[*slot].damage_epoch != next.damage_epochs[*slot]);
                    next.stopped[i] = !capturers.is_empty() && members.iter().any(|a| a.team == base.owner && inside(a));
                    // Explicit policy: team progress resets if the zone empties or
                    // a current capturer takes new damage; defenders contest it.
                    if capturers.is_empty() || damaged {
                        if damaged {
                            // A single reset is credited once to the most recent
                            // authoritative damager of the first damaged capturer.
                            if let Some(attacker) = capturers.iter().find(|slot| members[**slot].damage_epoch != next.damage_epochs[**slot])
                                .and_then(|slot| members[*slot].last_damager) {
                                next.capture_dropped[attacker] = next.capture_dropped[attacker].saturating_add((next.progress[i] / 1_000) as u32);
                            }
                        }
                        next.progress[i] = 0;
                    } else if !next.stopped[i] {
                        let mut budget = COMPLETE - next.progress[i];
                        for slot in capturers.iter().take(3) {
                            let earned = elapsed.min(budget); next.capture_earned[*slot] += earned;
                            budget -= earned; next.progress[i] += earned;
                        }
                    }
                }
                match (next.progress[0] == COMPLETE, next.progress[1] == COMPLETE) {
                    (true, true) => next.finish(0, Reason::Capture, now_ms),
                    (true, false) => next.finish(2, Reason::Capture, now_ms),
                    (false, true) => next.finish(1, Reason::Capture, now_ms),
                    _ if now_ms >= start + next.rules.battle_ms => next.finish(0, Reason::Timeout, start + next.rules.battle_ms),
                    _ => {},
                }
            }
        }
        next.damage_epochs = members.iter().map(|a| a.damage_epoch).collect();
        let changed = old != next.view();
        if changed { next.revision = next.revision.checked_add(1).ok_or_else(|| bad("revision overflow"))?; }
        *self = next; Ok(changed)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn members() -> [Member; 2] {
        std::array::from_fn(|i| Member { team: i as u8 + 1, present: true, ready: false,
            alive: true, position: [500., 0., 500.], damage_epoch: 0, last_damager: None })
    }
    fn fast() -> Rules { Rules { prebattle_ms: 1_000, battle_ms: 200_000, ..Rules::prohorovka() } }
    fn battle() -> (State, [Member; 2]) {
        let mut s=State::new(fast()).unwrap(); let mut m=members();m.iter_mut().for_each(|a|a.ready=true);
        s.advance(0,&m).unwrap();s.advance(1_000,&m).unwrap();assert!(s.allows_actions());(s,m)
    }
    #[test] fn readiness_countdown_and_clock_are_server_owned() {
        let mut s=State::new(fast()).unwrap();let mut m=members();
        s.advance(0,&m).unwrap();assert_eq!(s.phase(),Phase::Waiting);
        m[0].ready=true;s.advance(100,&m).unwrap();assert!(!s.allows_actions());
        m[1].ready=true;s.advance(200,&m).unwrap();assert_eq!(s.phase(),Phase::Prebattle);
        s.advance(1_199,&m).unwrap();assert!(!s.allows_actions());s.advance(1_200,&m).unwrap();assert!(s.allows_actions());
        let before=s.clone();assert!(s.advance(1_199,&m).is_err());assert_eq!(s,before);
        assert!(s.advance(2_201,&m).is_err());assert_eq!(s,before);
    }
    #[test] fn countdown_disconnect_is_explicit_technical_forfeit_and_never_waits_forever() {
        let mut s=State::new(fast()).unwrap();let mut m=members();m.iter_mut().for_each(|a|a.ready=true);
        s.advance(0,&m).unwrap();m[1].present=false;s.advance(999,&m).unwrap();
        assert_eq!(s.outcome(),Some(Outcome{winner:1,reason:Reason::Forfeit,ended_ms:999}));
        m[1].present=true;s.advance(1_000,&m).unwrap();assert_eq!(s.phase(),Phase::Afterbattle);
    }
    #[test] fn timeout_draw_and_elimination_are_frozen_once() {
        let (mut s,mut m)=battle();for t in 2..=201 {s.advance(t*1_000,&m).unwrap();}
        assert_eq!(s.outcome(),Some(Outcome{winner:0,reason:Reason::Timeout,ended_ms:201_000}));
        m[1].alive=false;s.advance(202_000,&m).unwrap();assert_eq!(s.outcome().unwrap().winner,0);
        assert!(!s.ready_to_return(208_999));assert!(s.ready_to_return(209_000));
        let (mut s,mut m)=battle();m[1].alive=false;s.advance(1_100,&m).unwrap();assert_eq!(s.outcome().unwrap().winner,1);
        let (mut s,mut m)=battle();m.iter_mut().for_each(|a|a.alive=false);s.advance(1_100,&m).unwrap();assert_eq!(s.outcome().unwrap().winner,0);
    }
    #[test] fn six_actor_battle_survives_individual_departures_until_a_whole_team_is_absent() {
        let mut m:[Member;6]=std::array::from_fn(|i|Member{team:(i%2)as u8+1,present:true,ready:true,
            alive:true,position:[500.,0.,500.],damage_epoch:0,last_damager:None});
        let mut s=State::new(fast()).unwrap();s.advance(0,&m).unwrap();s.advance(1_000,&m).unwrap();
        m[0].position=[51.599991,0.,-447.];m[5].present=false;s.advance(1_100,&m).unwrap();
        assert!(s.allows_actions());assert!(s.outcome().is_none());
        s.advance(2_000,&m).unwrap();assert_eq!(s.view().bases[1].points,1);
        m[3].present=false;s.advance(2_100,&m).unwrap();assert!(s.outcome().is_none());
        m[1].present=false;s.advance(2_200,&m).unwrap();
        assert!(m.iter().all(|a|a.alive));
        assert_eq!(s.outcome(),Some(Outcome{winner:1,reason:Reason::Forfeit,ended_ms:2_200}));
    }
    #[test] fn capture_uses_authoritative_pose_contest_damage_and_empty_reset() {
        let (mut s,mut m)=battle();m[0].position=[51.599991,0.,-447.];
        for t in 2..=11 {s.advance(t*1_000,&m).unwrap();}assert_eq!(s.view().bases[1].points,10);
        m[1].position=m[0].position;s.advance(12_000,&m).unwrap();assert_eq!(s.view().bases[1],Progress{owner:2,points:10,stopped:true});
        m[1].position=[500.,0.,500.];m[0].damage_epoch=1;s.advance(13_000,&m).unwrap();assert_eq!(s.view().bases[1].points,0);
        s.advance(14_000,&m).unwrap();assert_eq!(s.view().bases[1].points,1);
        m[0].position=[500.,0.,500.];s.advance(15_000,&m).unwrap();assert_eq!(s.view().bases[1].points,0);
        m[0].position=[51.599991,0.,-447.];for t in 16..=115{s.advance(t*1_000,&m).unwrap();}
        assert_eq!(s.outcome().unwrap().winner,1);assert_eq!(s.outcome().unwrap().reason,Reason::Capture);
    }
    #[test] fn late_poisoned_member_cannot_partially_advance_capture_or_clock() {
        let (mut s,mut m)=battle();m[0].position=[51.599991,0.,-447.];let before=s.clone();
        m[1].position[2]=f32::NAN;assert!(s.advance(2_000,&m).is_err());assert_eq!(s,before);
        m[1].position[2]=0.;m[1].team=0;assert!(s.advance(2_000,&m).is_err());assert_eq!(s,before);
    }
}
