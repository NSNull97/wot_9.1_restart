//! Source-bound #717 spotting rules without camouflage.
//!
//! The point formulas and mounted ranges come from the original client
//! resources. The numeric maximum, proximity shortcut, cadence, retention and
//! radio sharing values are explicit project policy because the 0.9.1 server
//! implementation is not present in the permitted client copy.
use std::{io, sync::atomic::{AtomicUsize, Ordering}};
use super::{pose, visibility::MAX_VIEW_RANGE};

pub const POLICY: &str = "p07b-717-source-points-no-camo.v1";
pub const MAX_ACTORS: usize = super::model::MAX_ACTORS;
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
    /// Explicit test-lab calibration; old P07B stays byte-for-byte in behavior when off.
    pub camouflage: bool,
    /// Explicitly authenticated local-operator trace, disabled by default.
    pub diagnostics: bool,
    pub max_detection_m: f32,
    pub proximity_m: f32,
    pub scan_period_ms: u64,
    pub retention_ms: u64,
    pub sixth_sense_delay_ms: u64,
    pub share_with_team: bool,
    pub rollover_world_up_fallback: bool,
}
// BW-01 wire codec (tools/bw01_wire_gen.py): Rules
impl crate::bw_wire::Wire for Rules {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{camouflage,diagnostics,max_detection_m,proximity_m,scan_period_ms,retention_ms,sixth_sense_delay_ms,share_with_team,rollover_world_up_fallback}=self;W::put(camouflage,bw_o);W::put(diagnostics,bw_o);W::put(max_detection_m,bw_o);W::put(proximity_m,bw_o);W::put(scan_period_ms,bw_o);W::put(retention_ms,bw_o);W::put(sixth_sense_delay_ms,bw_o);W::put(share_with_team,bw_o);W::put(rollover_world_up_fallback,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{camouflage:W::get(bw_i)?,diagnostics:W::get(bw_i)?,max_detection_m:W::get(bw_i)?,proximity_m:W::get(bw_i)?,scan_period_ms:W::get(bw_i)?,retention_ms:W::get(bw_i)?,sixth_sense_delay_ms:W::get(bw_i)?,share_with_team:W::get(bw_i)?,rollover_world_up_fallback:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl Rules {
    pub fn validate(self) -> io::Result<()> {
        if !self.max_detection_m.is_finite() || !(1. ..=MAX_VIEW_RANGE).contains(&self.max_detection_m)
            || !self.proximity_m.is_finite() || !(0. ..=self.max_detection_m).contains(&self.proximity_m)
            || !(1..=2000).contains(&self.scan_period_ms) || self.retention_ms > 15_000
            || self.sixth_sense_delay_ms > 10_000
            || self.diagnostics && (!cfg!(feature="test_lab") || !self.camouflage) { return Err(bad("spotting rules outside bounds")); }
        Ok(())
    }
    pub fn selected() -> io::Result<Self> {
        let value: serde_json::Value = serde_json::from_str(include_str!("../../../../config/rulesets/p07b-original-no-camo.v1.json"))
            .map_err(|_| bad("spotting rules JSON"))?;
        if value.get("schema").and_then(|v| v.as_str()) != Some(POLICY) { return Err(bad("spotting policy schema")); }
        let number = |name: &str| value.get(name).and_then(|v| v.as_f64()).ok_or_else(|| bad("spotting policy number"));
        let rules = Self { camouflage: false, diagnostics: false, max_detection_m: number("max_detection_m")? as f32, proximity_m: number("proximity_m")? as f32,
            scan_period_ms: number("scan_period_ms")? as u64, retention_ms: number("retention_ms")? as u64,
            sixth_sense_delay_ms: number("sixth_sense_delay_ms")? as u64,
            share_with_team: value.get("share_with_team").and_then(|v| v.as_bool()).ok_or_else(|| bad("spotting share policy"))?,
            rollover_world_up_fallback: value.get("rollover_world_up_fallback").and_then(|v| v.as_bool()).ok_or_else(|| bad("spotting rollover policy"))? };
        rules.validate()?; Ok(rules)
    }
}

#[derive(Clone, Copy, Debug, PartialEq)]
/// `wreck`: destroyed target. A wreck cannot move or hide, so it is published to
/// every recipient and stays published (owner 12.11: an enemy killed while
/// unspotted must appear on the map; before, a never-seen wreck needed direct
/// LOS, owner run 2026-10-19). Project policy.
pub struct Actor { pub slot: usize, pub team: u8, pub position: Point, pub points: Points, pub view_range: f32, pub camouflage: f32,
    pub base:f32, pub base_stationary:f32, pub moving:bool, pub net:f32, pub fire_multiplier:f32, pub net_remaining_ms:Option<u64>,
    pub fired:bool, pub observer_active: bool, pub commander_active: bool, pub wreck: bool }

fn validate_actors(actors: &[Actor]) -> io::Result<()> {
    if actors.is_empty() || actors.len() > MAX_ACTORS { return Err(bad("spotting actor count")); }
    let mut seen = [false; MAX_ACTORS];
    for actor in actors {
        if actor.slot >= MAX_ACTORS || seen[actor.slot] || !matches!(actor.team, 1 | 2) || !finite(actor.position)
            || !actor.points.checks.into_iter().chain(actor.points.observers).all(finite)
            || !actor.view_range.is_finite() || !(0. ..=MAX_VIEW_RANGE).contains(&actor.view_range)
            || !actor.camouflage.is_finite() || !(0. ..=1.).contains(&actor.camouflage)
            || [actor.base,actor.base_stationary,actor.net,actor.fire_multiplier].into_iter().any(|x|!x.is_finite() || !(0. ..=1.).contains(&x))
            || actor.net_remaining_ms.is_some_and(|x|x>3000)
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
    diagnostic_snapshot: Option<serde_json::Value>,
}
// BW-01 wire codec (tools/bw01_wire_gen.py): State
impl crate::bw_wire::Wire for State {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{rules,last_ms,last_scan_ms,direct,last_seen,desired,observed,pending,sixth_generation,diagnostic_snapshot}=self;W::put(rules,bw_o);W::put(last_ms,bw_o);W::put(last_scan_ms,bw_o);W::put(direct,bw_o);W::put(last_seen,bw_o);W::put(desired,bw_o);W::put(observed,bw_o);W::put(pending,bw_o);W::put(sixth_generation,bw_o);W::put(diagnostic_snapshot,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{rules:W::get(bw_i)?,last_ms:W::get(bw_i)?,last_scan_ms:W::get(bw_i)?,direct:W::get(bw_i)?,last_seen:W::get(bw_i)?,desired:W::get(bw_i)?,observed:W::get(bw_i)?,pending:W::get(bw_i)?,sixth_generation:W::get(bw_i)?,diagnostic_snapshot:W::get(bw_i)?})}
}
// end BW-01 wire codec
/// One observer's direct sightings of this scan.
#[derive(Clone,Copy,Debug,PartialEq)]
pub enum RayOutcome { Clear(f32), Blocked { kind:&'static str, hit_point:Option<Point> } }
type RayTrace = (RayOutcome, Option<serde_json::Value>);
type ScanRow = ([bool; MAX_ACTORS], Vec<serde_json::Value>);

fn scan_observer<F>(rules: Rules, observer: &Actor, actors: &[Actor], server_target: Option<usize>, clear: &mut F) -> io::Result<ScanRow>
where F: FnMut(&Actor, &Actor, [usize; 2], Point, Point) -> io::Result<RayTrace> {
    let mut row = [false; MAX_ACTORS];
    let mut records=Vec::new();
    for target in actors.iter().filter(|a| a.team != observer.team) {
        let distance = distance2(observer.position, target.position);
        let limit=if rules.camouflage { super::camouflage::threshold(observer.view_range,rules.max_detection_m,rules.proximity_m,target.camouflage)? }
            else { observer.view_range.min(rules.max_detection_m) };
        let server_trace = server_target == Some(target.slot);
        let trace = rules.diagnostics || server_trace;
        let mut rays=Vec::new();
        let mut reason="no_clear_ray";
        if distance <= f64::from(rules.proximity_m).powi(2) {row[target.slot]=true;reason="proximity";}
        else if distance > f64::from(limit).powi(2) {reason="outside_base_threshold";}
        else {
            'ray: for (observer_point, start) in observer.points.observers.into_iter().enumerate() {
                for (target_point, end) in target.points.checks.into_iter().enumerate() {
                    let (result, foliage_hits) = if start==end { (RayOutcome::Clear(0.), None) }
                        else { clear(observer, target, [observer_point, target_point], start, end)? };
                    let mut ray_limit=limit;
                    if let RayOutcome::Clear(foliage)=result {
                        if !foliage.is_finite() || !(0. ..=1.).contains(&foliage) {return Err(bad("spotting foliage coefficient"));}
                        ray_limit=if rules.camouflage {
                            super::camouflage::threshold(observer.view_range,rules.max_detection_m,rules.proximity_m,(target.camouflage+foliage).min(1.))?
                        } else if foliage==0. {limit} else {return Err(bad("foliage requires camouflage"));};
                    }
                    let direct = matches!(result, RayOutcome::Clear(_)) && distance <= f64::from(ray_limit).powi(2);
                    if trace {
                        let (label,foliage,hit_point)=match result {
                            RayOutcome::Clear(foliage)=>(if start==end {"coincident"} else {"clear"},Some(foliage),None),
                            RayOutcome::Blocked{kind,hit_point}=>(kind,None,hit_point),
                        };
                        let mut ray = serde_json::json!({"observer_point":observer_point,"target_point":target_point,
                            "start":start,"end":end,"result":label,"hit_point":hit_point,
                            "foliage":foliage,"threshold_m":if foliage.is_some(){Some(ray_limit)}else{None}});
                        if server_trace {
                            ray["direct"] = direct.into();
                            ray["foliage_hits"] = foliage_hits.unwrap_or_default();
                        }
                        rays.push(ray);
                    }
                    if direct {row[target.slot]=true;reason="direct_ray";break 'ray;}
                    if matches!(result,RayOutcome::Clear(_)) {reason="foliage_threshold";}
                }
            }
        }
        if trace {
            let checked_ray_count = rays.len();
            let unchecked_ray_count = 14 - checked_ray_count;
            let mut pair = serde_json::json!({"observer":observer.slot,"target":target.slot,"distance_m":distance.sqrt(),
            "view_m":observer.view_range,"base":target.base,"base_stationary":target.base_stationary,"movement_delta":target.base-target.base_stationary,"moving":target.moving,"net":target.net,
            "fire_multiplier":target.fire_multiplier,"fired":target.fired,"effective":target.camouflage,
            "net_remaining_ms":target.net_remaining_ms,"threshold_m":limit,"direct":row[target.slot],"reason":reason,
            "unchecked_ray_count":unchecked_ray_count,"rays":rays});
            if rules.diagnostics {
                pair["unchecked_rays"] = serde_json::Value::Array((checked_ray_count..14).map(|i|serde_json::json!({"observer_point":i/7,"target_point":i%7,
                    "start":observer.points.observers[i/7],"end":target.points.checks[i%7],"result":"not_checked"})).collect());
            } else {
                pair["observer_position"] = serde_json::json!(observer.position);
                pair["target_position"] = serde_json::json!(target.position);
                pair["target_wreck"] = target.wreck.into();
            }
            records.push(pair);
        }
    }
    Ok((row,records))
}

impl State {
    pub fn new(rules: Rules) -> io::Result<Self> { rules.validate()?; Ok(Self { rules, last_ms: None, last_scan_ms: None, direct: [[false; MAX_ACTORS]; MAX_ACTORS], last_seen: [[None; MAX_ACTORS]; MAX_ACTORS], desired: [[false; MAX_ACTORS]; MAX_ACTORS], observed: [false; MAX_ACTORS], pending: [None; MAX_ACTORS], sixth_generation: [0; MAX_ACTORS],diagnostic_snapshot:None }) }
    pub fn initialized(&self) -> bool { self.last_ms.is_some() }
    /// Last committed scan time relative to battle start, not the current
    /// presentation/retention time. Used for server-side impact attribution.
    pub(super) fn last_scan_ms(&self)->Option<u64>{self.last_scan_ms}
    pub fn desired(&self, slot: usize) -> io::Result<[bool; MAX_ACTORS]> { self.desired.get(slot).copied().ok_or_else(|| bad("spotting recipient slot")) }
    /// What `slot` itself sees in the last scan (no team sharing, no retention).
    pub fn direct(&self, slot: usize) -> io::Result<[bool; MAX_ACTORS]> { self.direct.get(slot).copied().ok_or_else(|| bad("spotting observer slot")) }
    pub fn sixth_generation(&self, slot: usize) -> io::Result<u32> { self.sixth_generation.get(slot).copied().ok_or_else(|| bad("spotting sixth slot")) }
    pub fn diagnostics(&self)->Option<&serde_json::Value> {self.diagnostic_snapshot.as_ref()}
    /// Called on a newly completed scan before World commits the cloned state.
    pub(super) fn bind_diagnostic_tick(&mut self,tick:u32,vehicles:&[&str],asset:&str)->io::Result<()> {
        let row=self.diagnostic_snapshot.as_mut().and_then(serde_json::Value::as_object_mut)
            .ok_or_else(||bad("spotting diagnostic snapshot"))?;
        if row.contains_key("scan_tick") {return Err(bad("spotting diagnostic tick already bound"));}
        let actors=row.get_mut("actors").and_then(serde_json::Value::as_array_mut).ok_or_else(||bad("spotting diagnostic actors"))?;
        for actor in actors {
            let slot=actor["slot"].as_u64().and_then(|v|usize::try_from(v).ok()).ok_or_else(||bad("spotting actor slot"))?;
            let vehicle=*vehicles.get(slot).ok_or_else(||bad("spotting vehicle slot"))?;
            if vehicle.is_empty() || vehicle.len()>96 {return Err(bad("spotting vehicle name"));}
            actor.as_object_mut().ok_or_else(||bad("spotting actor"))?.insert("vehicle".into(),vehicle.into());
        }
        if asset.is_empty() || asset.len()>96 {return Err(bad("spotting map asset"));}
        row.insert("map_asset".into(),asset.into());
        row.insert("scan_tick".into(),serde_json::Value::from(tick));Ok(())
    }
    pub fn refresh<F>(&mut self, ms: u64, actors: &[Actor], mut clear: F) -> io::Result<()>
    where F: FnMut(usize, usize, Point, Point) -> io::Result<bool> {
        self.refresh_with(ms, actors, |rules, observers| {
            let mut rows = Vec::with_capacity(observers.len());
            for observer in observers {
                rows.push(scan_observer(rules, observer, actors, None, &mut |_, _, [a, b], c, d| {
                    let outcome = if clear(a,b,c,d)? {RayOutcome::Clear(0.)}else{RayOutcome::Blocked{kind:"terrain_or_object",hit_point:None}};
                    Ok((outcome, None))
                })?);
            }
            Ok(rows)
        }).map(|_| ())
    }
    /// `refresh` over a pure `clear`, the rays spread on up to `threads`
    /// threads. Each observer's row depends only on its own rays, so the
    /// matrix is the one the serial scan builds; the first failing observer
    /// in slot order decides the error.
    pub fn refresh_parallel<F>(&mut self, ms: u64, actors: &[Actor], threads: usize, clear: F) -> io::Result<()>
    where F: Fn(usize, usize, Point, Point) -> io::Result<bool> + Sync {
        self.refresh_foliage_parallel(ms,actors,threads,|a,b,c,d,_|Ok(clear(a,b,c,d)?.then_some(0.)))
    }
    /// Each clear ray carries its authoritative project-calibrated shrub
    /// contribution. None means the terrain/object LOS is blocked. This is
    /// internal server data, not a client-provided visibility result.
    pub fn refresh_foliage_parallel<F>(&mut self, ms:u64, actors:&[Actor], threads:usize, clear:F)->io::Result<()>
    where F: Fn(usize, usize, Point, Point, bool) -> io::Result<Option<f32>> + Sync {
        self.refresh_trace_parallel(ms,actors,threads,|a,b,c,d,f|Ok(match clear(a,b,c,d,f)? {
            Some(value)=>RayOutcome::Clear(value),None=>RayOutcome::Blocked{kind:"terrain_or_object",hit_point:None}}))
    }
    pub fn refresh_trace_parallel<F>(&mut self, ms:u64, actors:&[Actor], threads:usize, clear:F)->io::Result<()>
    where F: Fn(usize, usize, Point, Point, bool) -> io::Result<RayOutcome> + Sync {
        self.refresh_parallel_with(ms, actors, threads, None, |_, target, [a, b], start, end| {
            Ok((clear(a, b, start, end, target.fired)?, None))
        }).map(|_| ())
    }

    /// Ephemeral, server-only records of the actual scan toward one target.
    /// The callback serves the whole scan so ordinary visibility still updates.
    pub fn refresh_server_trace_parallel<F>(&mut self, ms:u64, actors:&[Actor], threads:usize, target:usize, clear:F)
        -> io::Result<Vec<serde_json::Value>>
    where F: Fn(usize, usize, Point, Point, bool) -> io::Result<RayTrace> + Sync {
        if self.rules.diagnostics || target >= MAX_ACTORS { return Err(bad("server spotting trace target or diagnostics")); }
        self.refresh_parallel_with(ms, actors, threads, Some(target), |observer, target, _, start, end| {
            clear(observer.slot, target.slot, start, end, target.fired)
        })
    }

    fn refresh_parallel_with<F>(&mut self, ms:u64, actors:&[Actor], threads:usize, server_target:Option<usize>, clear:F)
        -> io::Result<Vec<serde_json::Value>>
    where F: Fn(&Actor, &Actor, [usize; 2], Point, Point) -> io::Result<RayTrace> + Sync {
        self.refresh_with(ms, actors, |rules, observers| {
            let (next, clear) = (AtomicUsize::new(0), &clear);
            let work = || {
                let mut done = Vec::new();
                loop {
                    let index = next.fetch_add(1, Ordering::Relaxed);
                    let Some(observer) = observers.get(index) else { return done; };
                    done.push((index, scan_observer(rules, observer, actors, server_target, &mut |o, t, points, start, end| {
                        clear(o, t, points, start, end)
                    })));
                }
            };
            let mut done = std::thread::scope(|scope| {
                let helpers = (1..threads.min(observers.len())).map(|_| scope.spawn(work)).collect::<Vec<_>>();
                let mut done = work();
                for helper in helpers { done.extend(helper.join().map_err(|_| bad("spotting scan thread"))?); }
                Ok::<_, io::Error>(done)
            })?;
            done.sort_by_key(|row| row.0);
            done.into_iter().map(|row| row.1).collect()
        })
    }
    fn refresh_with<S>(&mut self, ms: u64, actors: &[Actor], scan_rows: S) -> io::Result<Vec<serde_json::Value>>
    where S: FnOnce(Rules, &[Actor]) -> io::Result<Vec<ScanRow>> {
        validate_actors(actors)?; self.rules.validate()?;
        if self.rules.diagnostics && actors.len()>6 {return Err(bad("spotting diagnostic actor bound"));}
        if ms > 3_600_000 || self.last_ms.is_some_and(|old| ms < old) { return Err(bad("spotting clock")); }
        let mut next = self.clone();
        let mut diagnostic_pairs=Vec::new();
        let scan = next.last_scan_ms.is_none_or(|old| ms.saturating_sub(old) >= next.rules.scan_period_ms);
        if scan {
            next.direct = [[false; MAX_ACTORS]; MAX_ACTORS];
            let observers = actors.iter().filter(|a| a.observer_active).copied().collect::<Vec<_>>();
            for (observer, (row,records)) in observers.iter().zip(scan_rows(next.rules, &observers)?) { next.direct[observer.slot] = row;diagnostic_pairs.extend(records); }
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
                || target.wreck || actors.iter().any(|observer| {
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
        diagnostic_pairs.sort_by_key(|v|(v["observer"].as_u64().unwrap_or(u64::MAX),v["target"].as_u64().unwrap_or(u64::MAX)));
        if scan && next.rules.diagnostics {
            let mut ordered=actors.to_vec();ordered.sort_by_key(|a|a.slot);
            let map_actors=ordered.iter().map(|a|serde_json::json!({"slot":a.slot,"team":a.team,"position":a.position})).collect::<Vec<_>>();
            let mut publications=Vec::new();
            for recipient in &ordered {for target in ordered.iter().filter(|target|target.team!=recipient.team) {
                let (source,spotter)=if target.wreck {("wreck",None)}
                else if next.direct[recipient.slot][target.slot] {("direct",Some(recipient.slot))}
                else if let Some(o)=ordered.iter().find(|o|next.rules.share_with_team && o.team==recipient.team && o.slot!=recipient.slot && next.direct[o.slot][target.slot]) {("team",Some(o.slot))}
                else if next.last_seen[recipient.slot][target.slot].is_some_and(|at|ms.saturating_sub(at)<next.rules.retention_ms) {("direct_retained",Some(recipient.slot))}
                else if let Some(o)=ordered.iter().find(|o|next.rules.share_with_team && o.team==recipient.team && o.slot!=recipient.slot && next.last_seen[o.slot][target.slot].is_some_and(|at|ms.saturating_sub(at)<next.rules.retention_ms)) {("team_retained",Some(o.slot))}
                else {("hidden",None)};
                publications.push(serde_json::json!({"recipient":recipient.slot,"target":target.slot,"visible":next.desired[recipient.slot][target.slot],"source":source,"spotter":spotter}));
            }}
            next.diagnostic_snapshot=Some(serde_json::json!({"schema":"content0-s5a-spotting-trace.v1","scan_ms":ms,
                "next_scan_ms":ms+next.rules.scan_period_ms,"actors":map_actors,"pairs":std::mem::take(&mut diagnostic_pairs),"publications":publications}));
        } else if !next.rules.diagnostics {next.diagnostic_snapshot=None;}
        next.observed = observed; next.last_ms = Some(ms); *self = next; Ok(diagnostic_pairs)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn parts() -> Parts { Parts { hull:[1.,2.,3.], turret:[4.,5.,6.], gun:[7.,8.,9.], hull_bounds:[[-2.,-1.,-4.],[2.,3.,4.]], turret_top:6. } }
    fn actor(slot:usize,team:u8,x:f32)->Actor { Actor {slot,team,position:[x,0.,0.],points:Points{checks:[[x,1.,0.];7],observers:[[x,1.,0.];2]},view_range:400.,camouflage:0.,base:0.,base_stationary:0.,moving:false,net:0.,fire_multiplier:1.,net_remaining_ms:None,fired:false,observer_active:true,commander_active:true,wreck:false} }
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
    #[test] fn project_foliage_is_evaluated_per_clear_ray_before_team_publication() {
        let mut rules=Rules::selected().unwrap();rules.camouflage=true;rules.retention_ms=0;
        let actors=[actor(0,1,0.),actor(1,2,300.),actor(2,1,-1000.)];
        let mut state=State::new(rules).unwrap();
        state.refresh_foliage_parallel(0,&actors,1,|_,_,_,_,_|Ok(Some(0.4))).unwrap();
        assert!(!state.direct(0).unwrap()[1]);assert!(!state.desired(2).unwrap()[1]);
        state.refresh_foliage_parallel(100,&actors,1,|_,_,_,_,_|Ok(Some(0.))).unwrap();
        assert!(state.direct(0).unwrap()[1]);assert!(state.desired(2).unwrap()[1]);
        let old=state.clone();
        assert!(state.refresh_foliage_parallel(200,&actors,1,|_,_,_,_,_|Ok(Some(f32::NAN))).is_err());
        assert_eq!(state,old);
    }
    #[test] fn server_trace_collects_only_actual_target_rays_in_a_thirty_actor_scan() {
        let mut rules=Rules::selected().unwrap();
        rules.camouflage=true;
        let mut actors=(0..30).map(|slot|actor(slot, 1+(slot%2) as u8, 115. + slot as f32 * 8.)).collect::<Vec<_>>();
        actors[0]=actor(0, 1, 0.);
        actors[0].points.checks[0][1]=2.;
        actors[0].points.checks[1][1]=3.;
        actors[0].points.checks[2][1]=4.;
        actors[29]=actor(29, 2, 1000.);
        actors[27].observer_active=false;
        actors[27].commander_active=false;
        let ray=|end:Point|match end[1] {
            2. => RayOutcome::Blocked{kind:"object",hit_point:Some([30.,1.2,0.])},
            3. => RayOutcome::Clear(0.9),
            _ => RayOutcome::Clear(0.),
        };
        let mut plain=State::new(rules).unwrap();
        let mut traced=plain.clone();
        for ms in [0,50,100,3100,8100] {
            plain.refresh_trace_parallel(ms,&actors,4,|_,_,_,end,_|Ok(ray(end))).unwrap();
            let pairs=traced.refresh_server_trace_parallel(ms,&actors,4,0,|observer,target,_,end,_| {
                let hits=(target==0).then(||serde_json::json!({"observer":observer}));
                Ok((ray(end),hits))
            }).unwrap();
            assert_eq!(traced,plain);
            assert!(traced.diagnostics().is_none());
            if ms==50 {
                assert!(pairs.is_empty());
                continue;
            }
            assert_eq!(pairs.len(),14);
            assert!(pairs.iter().all(|pair|pair["target"]==0 && pair["observer"]!=27));
            let nearest=&pairs[0];
            assert_eq!(nearest["observer"],1);
            assert_eq!(nearest["reason"],"direct_ray");
            assert_eq!(nearest["unchecked_ray_count"],11);
            let rays=nearest["rays"].as_array().unwrap();
            assert_eq!(rays.len(),3);
            assert_eq!(rays[0]["result"],"object");
            assert_eq!(rays[1]["foliage_hits"]["observer"],1);
            assert_eq!(rays[1]["direct"],false);
            assert_eq!(rays[2]["direct"],true);
            assert_eq!(pairs.last().unwrap()["reason"],"outside_base_threshold");
            assert!(pairs.last().unwrap()["rays"].as_array().unwrap().is_empty());
        }
    }
    #[cfg(feature="test_lab")]
    #[test] fn operator_trace_is_only_committed_actual_rays_and_survives_bw() {
        let mut rules=Rules::selected().unwrap();rules.camouflage=true;rules.diagnostics=true;
        let actors=[actor(0,1,0.),actor(1,2,300.),actor(2,1,-1000.)];
        let mut state=State::new(rules).unwrap();
        state.refresh_foliage_parallel(0,&actors,1,|_,target_point,_,_,_| {
            Ok(if target_point==0 {None} else {Some(0.1)})
        }).unwrap();
        let snapshot=state.diagnostics().unwrap();
        let pair=snapshot["pairs"].as_array().unwrap().iter().find(|p|p["observer"]==0 && p["target"]==1).unwrap();
        assert_eq!(pair["reason"],"direct_ray");assert_eq!(pair["rays"].as_array().unwrap().len(),2);
        assert_eq!(pair["unchecked_ray_count"],12);assert_eq!(pair["unchecked_rays"][0]["result"],"not_checked");
        assert_eq!(pair["rays"][0]["result"],"terrain_or_object");assert_eq!(pair["rays"][1]["result"],"clear");
        assert_eq!(pair["rays"][1]["foliage"].as_f64().unwrap() as f32,0.1);
        let ally=snapshot["publications"].as_array().unwrap().iter().find(|p|p["recipient"]==2 && p["target"]==1).unwrap();
        assert_eq!(ally["source"],"team");assert_eq!(ally["spotter"],0);
        let old=state.clone();
        assert!(state.refresh_foliage_parallel(100,&actors,1,|_,_,_,_,_|Err(bad("trace LOS failure"))).is_err());
        assert_eq!(state,old);
        let now=std::time::Instant::now();let mut a=crate::bw_wire::Arcs::new(false);let mut b=crate::bw_wire::Arcs::new(true);
        let wire=crate::bw_wire::encode(&state,now,&mut a).unwrap();
        let received:State=crate::bw_wire::decode(&wire,now,&mut b).unwrap();assert_eq!(received.diagnostics(),state.diagnostics());
        let mut disabled=Rules::selected().unwrap();disabled.camouflage=true;
        let mut plain=State::new(disabled).unwrap();plain.refresh(0,&actors,|_,_,_,_|Ok(true)).unwrap();assert!(plain.diagnostics().is_none());
    }
    #[test] fn parallel_scan_builds_the_serial_matrix_and_fails_like_it() {
        let actors=(0..30).map(|slot|{let x=slot as f32*17.;let mut a=actor(slot,1+(slot%2) as u8,x);a.observer_active=slot%7!=3;a.commander_active=a.observer_active;a}).collect::<Vec<_>>();
        let clear=|o:usize,t:usize,s:Point,e:Point|Ok((o*3+t+((s[0]+e[0]) as usize))%5==0);
        let mut serial=State::new(Rules::selected().unwrap()).unwrap();let mut parallel=serial.clone();
        for ms in [0,100,200,5400,5500] {
            serial.refresh(ms,&actors,clear).unwrap();
            for threads in [1,4,64] {let mut copy=parallel.clone();copy.refresh_parallel(ms,&actors,threads,clear).unwrap();assert_eq!(copy,serial,"{ms} {threads}");}
            parallel=serial.clone();
        }
        let old=serial.clone();
        let failing=|_:usize,_:usize,s:Point,_:Point|if s[0]>=170.{Err(bad("late LOS"))}else{Ok(false)};
        let error=serial.refresh_parallel(5600,&actors,4,failing).unwrap_err();
        assert_eq!(error.to_string(),"late LOS");assert_eq!(serial,old);
    }
    #[test] fn sixth_sense_is_delayed_and_requires_functioning_commander() {
        let mut actors=[actor(0,1,0.),actor(1,2,100.)]; let mut state=State::new(Rules::selected().unwrap()).unwrap(); state.refresh(0,&actors,|_,_,_,_|Ok(true)).unwrap(); state.refresh(2999,&actors,|_,_,_,_|Ok(true)).unwrap(); assert_eq!(state.sixth_generation(0).unwrap(),0); state.refresh(3000,&actors,|_,_,_,_|Ok(true)).unwrap(); assert_eq!(state.sixth_generation(0).unwrap(),1); actors[0].commander_active=false; state.refresh(3100,&actors,|_,_,_,_|Ok(true)).unwrap(); state.refresh(6200,&actors,|_,_,_,_|Ok(true)).unwrap(); assert_eq!(state.sixth_generation(0).unwrap(),1);
    }
    #[test] fn every_wreck_is_published_to_every_recipient() {
        // Owner run 2026-10-19: the attacker lost the wreck (and its detached
        // turret) five seconds after the kill once direct LOS was gone.
        let mut actors=[actor(0,1,0.),actor(1,2,100.)]; let mut state=State::new(Rules::selected().unwrap()).unwrap();
        state.refresh(0,&actors,|_,_,_,_|Ok(true)).unwrap(); assert!(state.desired(0).unwrap()[1]);
        actors[1].wreck=true; actors[1].observer_active=false; actors[1].commander_active=false;
        for ms in [100,5100,60_000] { state.refresh(ms,&actors,|_,_,_,_|Ok(false)).unwrap(); assert!(state.desired(0).unwrap()[1],"ms={ms}"); }
        let mut fresh=State::new(Rules::selected().unwrap()).unwrap();
        // Owner 12.11: a never-seen wreck is published too (a kill of an unspotted enemy shows on the map).
        fresh.refresh(0,&actors,|_,_,_,_|Ok(false)).unwrap(); assert!(fresh.desired(0).unwrap()[1]);
        fresh.refresh(100,&actors,|_,_,_,_|Ok(true)).unwrap(); assert!(fresh.desired(0).unwrap()[1]);
        fresh.refresh(10_000,&actors,|_,_,_,_|Ok(false)).unwrap(); assert!(fresh.desired(0).unwrap()[1]);
        actors[1].wreck=false; let mut alive=State::new(Rules::selected().unwrap()).unwrap();
        alive.refresh(0,&actors,|_,_,_,_|Ok(true)).unwrap(); alive.refresh(5100,&actors,|_,_,_,_|Ok(false)).unwrap(); assert!(!alive.desired(0).unwrap()[1]);
    }
}
