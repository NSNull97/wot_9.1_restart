//! VIS-PERF: per-part wall timers of the gateway battle step, read only by the
//! ignored release benches. Outside test builds a span is a zero-sized no-op.
#[derive(Clone, Copy, Debug)]
pub(crate) enum Part { Bots, Scene, SceneClone, Advance, AdvanceClone, Projectiles, Spotting, SpotActors, SpotRays, Lifecycle, Turrets }
#[cfg(test)]
pub(crate) const NAMES: [&str; 11] = ["bots", "scene_step", "scene_world_clone", "advance", "advance_mixed_clone", "projectiles",
    "spotting", "spotting_actors", "spotting_rays", "lifecycle", "turret_flights"];
#[cfg(test)]
static NS: [std::sync::atomic::AtomicU64; 11] = [const { std::sync::atomic::AtomicU64::new(0) }; 11];

#[must_use]
pub(crate) struct Span { #[cfg(test)] part: Part, #[cfg(test)] start: std::time::Instant }
#[inline]
pub(crate) fn span(part: Part) -> Span {
    #[cfg(not(test))] { let _ = part; Span {} }
    #[cfg(test)] { Span { part, start: std::time::Instant::now() } }
}
impl Drop for Span {
    #[inline]
    fn drop(&mut self) {
        #[cfg(test)] NS[self.part as usize].fetch_add(u64::try_from(self.start.elapsed().as_nanos()).unwrap_or(u64::MAX), std::sync::atomic::Ordering::Relaxed);
    }
}
/// Cumulative nanoseconds per part (process-wide; one bench per process).
#[cfg(test)]
pub(crate) fn snapshot() -> [u64; 11] { std::array::from_fn(|i| NS[i].load(std::sync::atomic::Ordering::Relaxed)) }
