//! NET-01: pose delivery policy and gateway-loop measurements.
//! `vehicle.def` declares position/yaw/roll/pitch Volatile (VERIFIED, #717);
//! sending them outside the reliable window is project policy behind a key.
use std::time::{Duration,Instant};
use crate::transport091::Histogram;

pub(crate) const RELIABLE_BURST:&str="reliable-burst-v1";
pub(crate) const RELIABLE_BURST_V2:&str="reliable-burst-v2";
pub(crate) const LATEST_UNRELIABLE:&str="latest-unreliable-v1";

#[derive(Clone,Copy,Debug,Default,PartialEq,Eq)]
pub(crate) enum PoseDelivery {
    /// Old path: poses are reliable bodies queued only below four pending;
    /// the loop sends one reliable body per session and iteration.
    #[default] Reliable,
    /// Poses unchanged; the loop sends every due reliable body each iteration.
    ReliableBurst,
    /// Burst for other bodies; the reliable pose of the newest tick is kept
    /// aside and enters the window one part per loop. Only the first part
    /// carries tickSync (one per tick, INFERRED as the native bundle had);
    /// unsent parts of an older tick are replaced, never queued behind.
    ReliableBurstV2,
    /// Burst, and the pose of the newest tick goes outside the window
    /// unreliably; an unsent older pose is replaced, never resent.
    LatestUnreliable,
}
impl PoseDelivery {
    pub(crate) fn parse(value:Option<&str>)->Option<Self> {
        match value {None=>Some(Self::Reliable),Some(RELIABLE_BURST)=>Some(Self::ReliableBurst),Some(RELIABLE_BURST_V2)=>Some(Self::ReliableBurstV2),
            Some(LATEST_UNRELIABLE)=>Some(Self::LatestUnreliable),Some(_)=>None}
    }
    pub(crate) fn burst(self)->bool {self!=Self::Reliable}
    pub(crate) fn label(self)->&'static str {
        match self {Self::Reliable=>"reliable",Self::ReliableBurst=>RELIABLE_BURST,Self::ReliableBurstV2=>RELIABLE_BURST_V2,Self::LatestUnreliable=>LATEST_UNRELIABLE}
    }
}

/// Per-session pose counters since the last report (ticks, not wall time).
#[derive(Clone,Copy,Debug,Default,PartialEq)]
pub(crate) struct PoseStats {pub published:u32,pub gap_max:u32,pub gaps_over_one:u32,pub replaced_unsent:u32,
    pub packets:u32,pub bytes:u64,pub outbox_max:usize}
impl PoseStats {
    pub(crate) fn published(&mut self,previous:Option<u32>,tick:u32) {
        self.published+=1;
        if let Some(gap)=previous.map(|p|tick.saturating_sub(p)) {
            self.gap_max=self.gap_max.max(gap);if gap>1 {self.gaps_over_one+=1;}
        }
    }
}

/// Wall time of the gateway loop, reported every `REPORT` while a battle runs.
pub(crate) const REPORT:Duration=Duration::from_secs(10);
#[derive(Default)]
pub(crate) struct LoopStats {
    since:Option<Instant>,loops:u32,pub(crate) loop_ms:Histogram,pub(crate) step_ms:Histogram,pub(crate) publish_ms:Histogram,
    pub(crate) tick_interval_ms:Histogram,last_tick:Vec<Option<(u32,Instant)>>,
}
impl LoopStats {
    /// Records one loop; `ticks` are the arena domain ticks after the step.
    pub(crate) fn record(&mut self,start:Instant,step:Duration,publish:Duration,ticks:&[Option<u32>],now:Instant) {
        self.since.get_or_insert(start);self.loops+=1;
        self.loop_ms.record(now.saturating_duration_since(start));self.step_ms.record(step);self.publish_ms.record(publish);
        self.last_tick.resize(ticks.len(),None);
        for (last,tick) in self.last_tick.iter_mut().zip(ticks) {
            match (*last,*tick) {
                (Some((old,at)),Some(t)) if t!=old => {
                    // One interval per advanced tick; a multi-tick jump counts as one late interval.
                    self.tick_interval_ms.record(now.saturating_duration_since(at));*last=Some((t,now));
                },
                (None,Some(t))=>*last=Some((t,now)),
                (_,None)=>*last=None,
                _=>{},
            }
        }
    }
    /// The report line once per `REPORT` (only if a domain tick advanced), then a fresh window.
    pub(crate) fn take_report(&mut self,now:Instant)->Option<String> {
        let since=self.since?;
        if now.saturating_duration_since(since)<REPORT {return None;}
        let line=(self.tick_interval_ms.count()>0).then(||format!(
            "NET01_STEP_STATS window_s={:.1} loops={} loop_ms=[{}] step_ms=[{}] publish_ms=[{}] tick_interval_ms=[{}]",
            now.saturating_duration_since(since).as_secs_f64(),self.loops,self.loop_ms.summary(),self.step_ms.summary(),
            self.publish_ms.summary(),self.tick_interval_ms.summary()));
        let last_tick=std::mem::take(&mut self.last_tick);*self=Self{last_tick,..Self::default()};
        line
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn net01_key_values_are_exact() {
        assert_eq!(PoseDelivery::parse(None),Some(PoseDelivery::Reliable));
        assert_eq!(PoseDelivery::parse(Some(RELIABLE_BURST)),Some(PoseDelivery::ReliableBurst));
        assert_eq!(PoseDelivery::parse(Some(LATEST_UNRELIABLE)),Some(PoseDelivery::LatestUnreliable));
        assert_eq!(PoseDelivery::parse(Some(RELIABLE_BURST_V2)),Some(PoseDelivery::ReliableBurstV2));assert!(PoseDelivery::ReliableBurstV2.burst());
        for bad in ["","reliable","latest-unreliable-v2","LATEST-UNRELIABLE-V1"] {assert_eq!(PoseDelivery::parse(Some(bad)),None);}
        assert!(!PoseDelivery::Reliable.burst());assert!(PoseDelivery::ReliableBurst.burst());assert!(PoseDelivery::LatestUnreliable.burst());
    }
    #[test] fn net01_pose_gaps_count_ticks_between_publications() {
        let mut s=PoseStats::default();s.published(None,1000);s.published(Some(1000),1001);s.published(Some(1001),1004);
        assert_eq!((s.published,s.gap_max,s.gaps_over_one),(3,3,1));
    }
    #[test] fn net01_loop_report_measures_tick_intervals_and_resets() {
        let t0=Instant::now();let mut l=LoopStats::default();
        l.record(t0,Duration::from_millis(30),Duration::from_millis(2),&[Some(1000)],t0+Duration::from_millis(40));
        for n in 1..=100u32 {
            let at=t0+Duration::from_millis(40+100*n as u64);
            l.record(at-Duration::from_millis(40),Duration::from_millis(30),Duration::from_millis(2),&[Some(1000+n)],at);
        }
        assert!(l.take_report(t0+Duration::from_secs(5)).is_none());
        let line=l.take_report(t0+Duration::from_secs(11)).unwrap();
        assert!(line.starts_with("NET01_STEP_STATS window_s=11.0 loops=101 "),"{line}");
        assert!(line.contains("tick_interval_ms=[n=100 mean=100.0 p50<=100.0 p95<=100.0 p99<=100.0 max=100.0]"),"{line}");
        assert!(l.take_report(t0+Duration::from_secs(30)).is_none());
        // The last tick survives the reset: the next interval is measured from it.
        l.record(t0+Duration::from_secs(30),Duration::ZERO,Duration::ZERO,&[Some(1101)],t0+Duration::from_millis(30_040));
        assert_eq!(l.tick_interval_ms.count(),1);assert_eq!(l.tick_interval_ms.max_ms(),20_000.);
    }
}
