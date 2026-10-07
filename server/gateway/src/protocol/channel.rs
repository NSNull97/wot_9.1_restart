//! ACK hypothesis experiment for the one measured first reliable frame.
//! This does not implement a general channel, messages, entities, or ACK windows.
use std::time::{Duration, Instant};

#[derive(Clone, Copy, PartialEq, Eq)]
pub enum AckMode { Disabled, FirstFrame, StaleControl, ServerFirst, GapProbe }

impl AckMode {
    pub fn profile(self) -> &'static str {
        match self {
            Self::Disabled => "legacy091-baseapp",
            Self::FirstFrame => "legacy091-channel-ack",
            Self::StaleControl => "legacy091-channel-stale",
            Self::ServerFirst => "legacy091-server-reliable",
            Self::GapProbe => "legacy091-gap",
        }
    }
}

pub struct FirstAck {
    mode: AckMode,
    enabled: bool,
    last_sent: Option<Instant>,
    sent: u8,
}

impl FirstAck {
    pub fn new(mode: AckMode) -> Self { Self { mode, enabled:false, last_sent:None, sent:0 } }
    // Caller must first verify the exact measured frame AND the session token.
    pub fn observe_verified_first(&mut self) { self.enabled=true; }
    pub fn due(&mut self, now: Instant) -> Option<[u8;6]> {
        if !self.enabled || self.mode==AckMode::Disabled || self.sent>=32 ||
            self.last_sent.is_some_and(|t|now.duration_since(t)<Duration::from_secs(1)) { return None; }
        self.last_sent=Some(now);self.sent+=1;
        // Candidate ON_CHANNEL | HAS_CUMULATIVE_ACK, no application payload.
        // ACK=1 acknowledges only sequence 0. Stale=0 is an explicit negative control.
        Some([8,4,if self.mode==AckMode::StaleControl {0} else {1},0,0,0])
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn no_ack_before_verified_first_or_when_disabled() {
        let now=Instant::now();
        let mut ack=FirstAck::new(AckMode::FirstFrame);assert!(ack.due(now).is_none());
        let mut off=FirstAck::new(AckMode::Disabled);off.observe_verified_first();assert!(off.due(now).is_none());
    }
    #[test] fn rate_count_and_duplicate_observation_bound() {
        let now=Instant::now();let mut ack=FirstAck::new(AckMode::FirstFrame);ack.observe_verified_first();
        assert_eq!(ack.due(now),Some([8,4,1,0,0,0]));ack.observe_verified_first();
        assert!(ack.due(now+Duration::from_millis(999)).is_none());
        for n in 1..32 {assert!(ack.due(now+Duration::from_secs(n)).is_some());}
        assert!(ack.due(now+Duration::from_secs(32)).is_none());
        ack.observe_verified_first();assert!(ack.due(now+Duration::from_secs(40)).is_none());
    }
    #[test] fn stale_control_has_zero_end_sequence() {
        let mut ack=FirstAck::new(AckMode::StaleControl);ack.observe_verified_first();
        assert_eq!(ack.due(Instant::now()),Some([8,4,0,0,0,0]));
    }
}
