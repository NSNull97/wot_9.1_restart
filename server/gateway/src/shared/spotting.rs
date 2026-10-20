//! Source-bound #717 spotting rules without camouflage.
//!
//! The point formulas and mounted ranges come from the original client
//! resources. The numeric maximum, proximity shortcut, cadence, retention and
//! radio sharing values are explicit project policy because the 0.9.1 server
//! implementation is not present in the permitted client copy.
use std::io;
use super::{pose, visibility::MAX_VIEW_RANGE};

pub const POLICY: &str = "p07b-717-source-points-no-camo.v1";
pub const MAX_ACTORS: usize = 6;
type Point = [f32; 3];

fn bad(message: &'static str) -> io::Error { io::Error::new(io::ErrorKind::InvalidData, message) }
fn finite(point: Point) -> bool { point.into_iter().all(|v| v.is_finite() && v.abs() <= 10_000.) }
fn add(a: Point, b: Point) -> Point { std::array::from_fn(|i| a[i] + b[i]) }
fn distance2(a: Point, b: Point) -> f64 { a.into_iter().zip(b).map(|(x,y)| (f64::from(x)-f64::from(y)).powi(2)).sum() }

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Parts {
    pub hull: Point,
    pub turret: Point,
    pub gun: Point,
    pub hull_bounds: [Point; 2],
    pub turret_top: f32,
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Points { pub checks: [Point; 7], pub observers: [Point; 2] }

impl Parts {
    /// Literal arithmetic recovered from VehicleDescr.__updateAttributes.
    pub fn local(self) -> io::Result<Points> {
        if ![self.hull, self.turret, self.gun, self.hull_bounds[0], self.hull_bounds[1]].into_iter().all(finite)
            || !self.turret_top.is_finite()
            || self.hull_bounds[0].into_iter().zip(self.hull_bounds[1]).any(|(a,b)| a >= b) { return Err(bad("invalid source spotting parts")); }
        let [lo, hi] = self.hull_bounds;
        let top = hi[1].max(self.turret[1] + self.turret_top);
        let cy = (lo[1] + hi[1]) * 0.5;
        let cz = (lo[2] + hi[2]) * 0.5;
        let joint = add(self.turret, self.gun);
        let mut checks = [
            [0., self.hull[1] + top, 0.],
            add(self.hull, joint),
            add(self.hull, [0., cy, hi[2]]),
            add(self.hull, [0., cy, lo[2]]),
            add(self.hull, [hi[0], joint[1], cz]),
            add(self.hull, [lo[0], joint[1], cz]),
            add(self.hull, joint),
        ];
        let points = Points { checks, observers: [checks[0], self.gun] };
        if !points.checks.into_iter().chain(points.observers).all(finite) { return Err(bad("source spotting point outside bound")); }
        Ok(points)
    }

    /// Full hull YPR is the measured project transform. The moving gunner
    /// target point additionally follows turret yaw; native server ordering is
    /// still UNKNOWN and is recorded in the source ledger.
    pub fn world(self, position: Point, hull_ypr: Point, turret_yaw: f32) -> io::Result<Points> {
        if !finite(position) || !hull_ypr.into_iter().all(|v| v.is_finite() && v.abs() <= std::f32::consts::PI)
            || !turret_yaw.is_finite() || turret_yaw.abs() > std::f32::consts::PI { return Err(bad("invalid spotting transform")); }
        let local = self.local()?;
        let transform = |point| add(position, pose::rotate(point, hull_ypr));
        let gunner = transform(add(add(self.hull, self.turret), pose::rotate(self.gun, [turret_yaw, 0., 0.])));
        let mut checks = local.checks.map(transform);
        checks[6] = gunner;
        let points = Points { checks, observers: [transform(local.observers[0]), gunner] };
        if !points.checks.into_iter().chain(points.observers).all(finite) { return Err(bad("world spotting point outside bound")); }
        Ok(points)
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Rules {
    pub max_detection_m: f32,
    pub proximity_m: f32,
    pub scan_period_ms: u64,
    pub retention_ms: u64,
    pub sixth_sense_delay_ms: u64,
    pub share_with_team: bool,
    pub rollover_world_up_fallback: bool,
}
impl Rules {
    pub fn validate(self) -> io::Result<()> {
        if !self.max_detection_m.is_finite() || !(1. ..=MAX_VIEW_RANGE).contains(&self.max_detection_m)
            || !self.proximity_m.is_finite() || !(0. ..=self.max_detection_m).contains(&self.proximity_m)
            || !(1..=2000).contains(&self.scan_period_ms) || self.retention_ms > 15_000
            || self.sixth_sense_delay_ms > 10_000 { return Err(bad("spotting rules outside bounds")); }
        Ok(())
    }
    pub fn selected() -> io::Result<Self> {
        let value: serde_json::Value = serde_json::from_str(include_str!("../../../../config/rulesets/p07b-original-no-camo.v1.json"))
            .map_err(|_| bad("spotting rules JSON"))?;
        if value.get("schema").and_then(|v| v.as_str()) != Some(POLICY) { return Err(bad("spotting policy schema")); }
        let number = |name: &str| value.get(name).and_then(|v| v.as_f64()).ok_or_else(|| bad("spotting policy number"));
        let rules = Self { max_detection_m: number("max_detection_m")? as f32, proximity_m: number("proximity_m")? as f32,
            scan_period_ms: number("scan_period_ms")? as u64, retention_ms: number("retention_ms")? as u64,
            sixth_sense_delay_ms: number("sixth_sense_delay_ms")? as u64,
            share_with_team: value.get("share_with_team").and_then(|v| v.as_bool()).ok_or_else(|| bad("spotting share policy"))?,
            rollover_world_up_fallback: value.get("rollover_world_up_fallback").and_then(|v| v.as_bool()).ok_or_else(|| bad("spotting rollover policy"))? };
        rules.validate()?; Ok(rules)
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
/// `wreck`: destroyed target. A wreck cannot move or hide, so once published to
/// a recipient it stays published (no retention expiry); a never-seen wreck is
/// still revealed only by ordinary direct LOS. Project policy, owner run 2026-10-19.
pub struct Actor { pub slot: usize, pub team: u8, pub position: Point, pub points: Points, pub view_range: f32, pub observer_active: bool, pub commander_active: bool, pub wreck: bool }

fn validate_actors(actors: &[Actor]) -> io::Result<()> {
    if actors.is_empty() || actors.len() > MAX_ACTORS { return Err(bad("spotting actor count")); }
    let mut seen = [false; MAX_ACTORS];
    for actor in actors {
        if actor.slot >= MAX_ACTORS || seen[actor.slot] || !matches!(actor.team, 1 | 2) || !finite(actor.position)
            || !actor.points.checks.into_iter().chain(actor.points.observers).all(finite)
            || !actor.view_range.is_finite() || !(0. ..=MAX_VIEW_RANGE).contains(&actor.view_range)
            || actor.commander_active && !actor.observer_active { return Err(bad("spotting actor validation")); }
        seen[actor.slot] = true;
    }
    Ok(())
}

#[derive(Clone, Debug, PartialEq)]
pub struct State {
    pub rules: Rules,
    last_ms: Option<u64>,
    last_scan_ms: Option<u64>,
    direct: [[bool; MAX_ACTORS]; MAX_ACTORS],
    last_seen: [[Option<u64>; MAX_ACTORS]; MAX_ACTORS],
    desired: [[bool; MAX_ACTORS]; MAX_ACTORS],
    observed: [bool; MAX_ACTORS],
    pending: [Option<u64>; MAX_ACTORS],
    sixth_generation: [u32; MAX_ACTORS],
}
impl State {
    pub fn new(rules: Rules) -> io::Result<Self> { rules.validate()?; Ok(Self { rules, last_ms: None, last_scan_ms: None, direct: [[false; MAX_ACTORS]; MAX_ACTORS], last_seen: [[None; MAX_ACTORS]; MAX_ACTORS], desired: [[false; MAX_ACTORS]; MAX_ACTORS], observed: [false; MAX_ACTORS], pending: [None; MAX_ACTORS], sixth_generation: [0; MAX_ACTORS] }) }
    pub fn initialized(&self) -> bool { self.last_ms.is_some() }
    pub fn desired(&self, slot: usize) -> io::Result<[bool; MAX_ACTORS]> { self.desired.get(slot).copied().ok_or_else(|| bad("spotting recipient slot")) }
    pub fn sixth_generation(&self, slot: usize) -> io::Result<u32> { self.sixth_generation.get(slot).copied().ok_or_else(|| bad("spotting sixth slot")) }
    pub fn refresh<F>(&mut self, ms: u64, actors: &[Actor], mut clear: F) -> io::Result<()>
    where F: FnMut(usize, usize, Point, Point) -> io::Result<bool> {
        validate_actors(actors)?; self.rules.validate()?;
        if ms > 3_600_000 || self.last_ms.is_some_and(|old| ms < old) { return Err(bad("spotting clock")); }
        let mut next = self.clone();
        let scan = next.last_scan_ms.is_none_or(|old| ms.saturating_sub(old) >= next.rules.scan_period_ms);
        if scan {
            next.direct = [[false; MAX_ACTORS]; MAX_ACTORS];
            for observer in actors.iter().filter(|a| a.observer_active) {
                for target in actors.iter().filter(|a| a.team != observer.team) {
                    let distance = distance2(observer.position, target.position);
                    if distance <= f64::from(next.rules.proximity_m).powi(2) { next.direct[observer.slot][target.slot] = true; continue; }
                    if distance > f64::from(observer.view_range.min(next.rules.max_detection_m)).powi(2) { continue; }
                    'ray: for (observer_point, start) in observer.points.observers.into_iter().enumerate() {
                        for (target_point, end) in target.points.checks.into_iter().enumerate() {
                            if start == end || clear(observer_point, target_point, start, end)? { next.direct[observer.slot][target.slot] = true; break 'ray; }
                        }
                    }
                }
            }
            next.last_scan_ms = Some(ms);
            for observer in actors { for target in actors { if next.direct[observer.slot][target.slot] { next.last_seen[observer.slot][target.slot] = Some(ms); } } }
        }
        let mut observed = [false; MAX_ACTORS];
        for observer in actors {
            if !observer.observer_active { next.direct[observer.slot] = [false; MAX_ACTORS]; }
            for target in actors { if observer.team != target.team && next.direct[observer.slot][target.slot] { observed[target.slot] = true; } }
        }
        next.desired = [[false; MAX_ACTORS]; MAX_ACTORS];
        for recipient in actors { for target in actors {
            let visible = recipient.slot == target.slot || recipient.team == target.team
                || target.wreck && self.desired[recipient.slot][target.slot] || actors.iter().any(|observer| {
                let share = observer.slot == recipient.slot || (next.rules.share_with_team && observer.team == recipient.team);
                share && next.last_seen[observer.slot][target.slot].is_some_and(|at| next.direct[observer.slot][target.slot] || ms.saturating_sub(at) < next.rules.retention_ms)
            });
            next.desired[recipient.slot][target.slot] = visible;
        }}
        for actor in actors {
            if !actor.commander_active { next.pending[actor.slot] = None; continue; }
            if observed[actor.slot] && !next.observed[actor.slot] && next.pending[actor.slot].is_none() { next.pending[actor.slot] = Some(ms.checked_add(next.rules.sixth_sense_delay_ms).ok_or_else(|| bad("sixth sense clock"))?); }
            if next.pending[actor.slot].is_some_and(|due| ms >= due) { next.sixth_generation[actor.slot] = next.sixth_generation[actor.slot].checked_add(1).ok_or_else(|| bad("sixth sense sequence"))?; next.pending[actor.slot] = None; }
        }
        next.observed = observed; next.last_ms = Some(ms); *self = next; Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn parts() -> Parts { Parts { hull:[1.,2.,3.], turret:[4.,5.,6.], gun:[7.,8.,9.], hull_bounds:[[-2.,-1.,-4.],[2.,3.,4.]], turret_top:6. } }
    fn actor(slot:usize,team:u8,x:f32)->Actor { Actor {slot,team,position:[x,0.,0.],points:Points{checks:[[x,1.,0.];7],observers:[[x,1.,0.];2]},view_range:400.,observer_active:true,commander_active:true,wreck:false} }
    #[test] fn source_static_and_dynamic_points_are_bounded_and_transform_full_ypr() {
        let p=parts().local().unwrap(); assert_eq!(p.checks,[[0.,13.,0.],[12.,15.,18.],[1.,3.,7.],[1.,3.,-1.],[3.,15.,3.],[-1.,15.,3.],[12.,15.,18.]]); assert_eq!(p.observers,[[0.,13.,0.],[7.,8.,9.]]);
        let world=parts().world([10.,20.,30.],[0.,0.,0.],std::f32::consts::FRAC_PI_2).unwrap(); assert_eq!(world.checks[6],world.observers[1]); assert!((world.observers[1][0]-24.).abs()<1e-5); assert!((world.observers[1][2]-32.).abs()<1e-5);
        let mixed=parts().world([10.,20.,30.],[0.7,-0.3,0.2],0.).unwrap(); assert_ne!(mixed.checks[0],p.checks[0]);
    }
    #[test] fn rules_are_explicit_and_historical_unknowns_are_not_silently_read_from_memory() { let rules=Rules::selected().unwrap(); assert_eq!(rules.max_detection_m,445.); assert_eq!(rules.proximity_m,50.); assert_eq!(rules.scan_period_ms,100); assert_eq!(rules.retention_ms,5000); assert_eq!(rules.sixth_sense_delay_ms,3000); }
    #[test] fn direct_rays_are_bounded_and_state_is_atomic_on_late_error() {
        let actors=[actor(0,1,0.),actor(1,2,100.)]; let mut state=State::new(Rules::selected().unwrap()).unwrap(); state.refresh(0,&actors,|_,_,_,_|Ok(false)).unwrap(); let old=state.clone(); let mut calls=0; assert!(state.refresh(100,&actors,|_,_,_,_|{calls+=1;if calls==2{Err(io::Error::other("late LOS"))}else{Ok(true)}}).is_err()); assert_eq!(state,old);
        state.refresh(100,&actors,|_,_,_,_|Ok(true)).unwrap(); assert!(state.desired(0).unwrap()[1]);
    }
    #[test] fn sixth_sense_is_delayed_and_requires_functioning_commander() {
        let mut actors=[actor(0,1,0.),actor(1,2,100.)]; let mut state=State::new(Rules::selected().unwrap()).unwrap(); state.refresh(0,&actors,|_,_,_,_|Ok(true)).unwrap(); state.refresh(2999,&actors,|_,_,_,_|Ok(true)).unwrap(); assert_eq!(state.sixth_generation(0).unwrap(),0); state.refresh(3000,&actors,|_,_,_,_|Ok(true)).unwrap(); assert_eq!(state.sixth_generation(0).unwrap(),1); actors[0].commander_active=false; state.refresh(3100,&actors,|_,_,_,_|Ok(true)).unwrap(); state.refresh(6200,&actors,|_,_,_,_|Ok(true)).unwrap(); assert_eq!(state.sixth_generation(0).unwrap(),1);
    }
    #[test] fn a_published_wreck_stays_published_but_an_unseen_wreck_needs_direct_los() {
        // Owner run 2026-10-19: the attacker lost the wreck (and its detached
        // turret) five seconds after the kill once direct LOS was gone.
        let mut actors=[actor(0,1,0.),actor(1,2,100.)]; let mut state=State::new(Rules::selected().unwrap()).unwrap();
        state.refresh(0,&actors,|_,_,_,_|Ok(true)).unwrap(); assert!(state.desired(0).unwrap()[1]);
        actors[1].wreck=true; actors[1].observer_active=false; actors[1].commander_active=false;
        for ms in [100,5100,60_000] { state.refresh(ms,&actors,|_,_,_,_|Ok(false)).unwrap(); assert!(state.desired(0).unwrap()[1],"ms={ms}"); }
        let mut fresh=State::new(Rules::selected().unwrap()).unwrap();
        fresh.refresh(0,&actors,|_,_,_,_|Ok(false)).unwrap(); assert!(!fresh.desired(0).unwrap()[1]);
        fresh.refresh(100,&actors,|_,_,_,_|Ok(true)).unwrap(); assert!(fresh.desired(0).unwrap()[1]);
        fresh.refresh(10_000,&actors,|_,_,_,_|Ok(false)).unwrap(); assert!(fresh.desired(0).unwrap()[1]);
        actors[1].wreck=false; let mut alive=State::new(Rules::selected().unwrap()).unwrap();
        alive.refresh(0,&actors,|_,_,_,_|Ok(true)).unwrap(); alive.refresh(5100,&actors,|_,_,_,_|Ok(false)).unwrap(); assert!(!alive.desired(0).unwrap()[1]);
    }
}
