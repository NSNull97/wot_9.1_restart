//! One server sequence experiment, with one deliberate duplicate. No game payload.
use std::{io, time::{Duration,Instant}};

/// Discovery schedule: withhold sequence 0, send 1, release 0, duplicate 1.
/// This intentional schedule is not an automatic retransmission algorithm.
pub struct GapProbe { started: Option<Instant>, sent: usize }
impl GapProbe {
    pub fn new() -> Self { Self { started:None, sent:0 } }
    pub fn start(&mut self, now:Instant) { if self.started.is_none() {self.started=Some(now);} }
    pub fn due(&mut self, now:Instant) -> Option<(u32,Vec<u8>)> {
        let elapsed=now.duration_since(self.started?);
        let (seconds,sequence)=*[(2,1u32),(4,0),(6,1)].get(self.sent)?;
        if elapsed<Duration::from_secs(seconds) {return None;}
        self.sent+=1;
        let mut clear=vec![0x58,4];clear.extend(sequence.to_le_bytes());clear.extend(1u32.to_le_bytes());
        Some((sequence,clear))
    }
}

pub struct FirstServer {
    started: Option<Instant>,
    sent: u8,
    ack_seen: bool,
}

impl FirstServer {
    pub fn new() -> Self { Self { started:None, sent:0, ack_seen:false } }
    pub fn start(&mut self, now: Instant) { if self.started.is_none() { self.started=Some(now); } }
    pub fn due(&mut self, now: Instant) -> Option<([u8;10],bool)> {
        let elapsed=now.duration_since(self.started?);
        let delay=match self.sent {0=>2,1=>5,_=>return None};
        if elapsed<Duration::from_secs(delay) {return None;}
        let duplicate=self.sent==1;self.sent+=1;
        // Candidate ON_CHANNEL|RELIABLE|SEQUENCE|CUMULATIVE_ACK; seq0, ack1.
        Some(([0x58,4,0,0,0,0,1,0,0,0],duplicate))
    }
    // Call only after the established peer/key decrypt and first-token handshake.
    // Native transport-only feedback has no application token in its body.
    pub fn observe_ack(&mut self, clear: &[u8]) -> io::Result<(u32,u32)> {
        let invalid=||io::Error::new(io::ErrorKind::InvalidData,"unmeasured client ACK");
        if clear.len()!=10 || clear[..2]!=[0x48,4] {return Err(invalid());}
        let sequence=u32::from_le_bytes(clear[2..6].try_into().map_err(|_|invalid())?);
        let cumulative=u32::from_le_bytes(clear[6..10].try_into().map_err(|_|invalid())?);
        // This experiment emits only two copies of server seq0. These ACK packet
        // sequence values were measured, not a proposed global sequence rule.
        if sequence==0 || sequence>self.sent as u32 || cumulative!=1 {return Err(invalid());}
        self.ack_seen=true;
        Ok((sequence,cumulative))
    }
    pub fn ack_seen(&self) -> bool {self.ack_seen}
}

#[cfg(test)]
mod tests {
    use super::*;
    fn ack(sequence:u32,value:u32)->Vec<u8> {let mut v=vec![0x48,4];v.extend(sequence.to_le_bytes());v.extend(value.to_le_bytes());v}
    #[test] fn bounded_first_and_duplicate_schedule() {
        let now=Instant::now();let mut state=FirstServer::new();assert!(state.due(now).is_none());
        state.start(now);assert!(state.due(now+Duration::from_millis(1999)).is_none());
        let (first,dup)=state.due(now+Duration::from_secs(2)).unwrap();assert!(!dup);
        state.start(now+Duration::from_secs(3));assert!(state.due(now+Duration::from_secs(4)).is_none());
        let (second,dup)=state.due(now+Duration::from_secs(5)).unwrap();assert!(dup);assert_eq!(first,second);
        assert!(state.due(now+Duration::from_secs(60)).is_none());
    }
    #[test] fn ack_requires_exact_shape_and_sent_sequence() {
        let now=Instant::now();let mut state=FirstServer::new();let wire=ack(1,1);
        assert!(state.observe_ack(&wire).is_err());state.start(now);state.due(now+Duration::from_secs(2));
        for n in 0..10 {assert!(state.observe_ack(&wire[..n]).is_err());}
        for bad in [ack(0,1),ack(2,1),ack(1,0),ack(1,2),vec![0;1025]] {assert!(state.observe_ack(&bad).is_err());}
        let mut extended=wire.clone();extended.push(0);assert!(state.observe_ack(&extended).is_err());
        let mut wrong=wire.clone();wrong[0]=0x58;assert!(state.observe_ack(&wrong).is_err());
        assert!(!state.ack_seen());assert_eq!(state.observe_ack(&wire).unwrap(),(1,1));assert!(state.ack_seen());
        assert_eq!(state.observe_ack(&wire).unwrap(),(1,1));
        state.due(now+Duration::from_secs(5));assert_eq!(state.observe_ack(&ack(2,1)).unwrap(),(2,1));
    }
}
