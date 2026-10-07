//! One own laboratory PREBATTLE transition, not a battle implementation.
//!
//! Original #717 ClientArena/constants/PE clock linkage and the actual Vehicle03
//! compound33 are pinned in arena-ready/wire/design-01. Native countdown remains
//! NOT_RUN until root's independent run; these constants are explicit lab choices.
use std::{io,time::{Duration,Instant}};

pub const FREQUENCY:u8=10;
pub const GAME_TICKS:u32=1000;
pub const START_GAME_SECONDS:f64=100.0;
pub const END_GAME_SECONDS:f64=130.0;
pub const PREPARATION:Duration=Duration::from_secs(30);
pub const READY_BODY_BYTES:usize=51;

fn invalid()->io::Error {io::Error::new(io::ErrorKind::InvalidData,"unsupported bounded arena readiness")}

/// Validate all four native method boundaries before exposing a domain command.
/// Only setClientReady is accepted. The other three exact automatic calls remain
/// unsupported controls and MUST be reported as domain_applied=false by caller.
pub fn validate_compound(payload:&[u8],own_vehicle:u32)->io::Result<()> {
    if own_vehicle!=crate::arena_vehicle091::VEHICLE_ENTITY_ID || payload.len()!=33 {return Err(invalid());}
    let mut at=0usize;
    for (method,length) in [(0x0d,8usize),(0x8d,5),(0x86,0),(0x0c,8)] {
        if payload.get(at)!=Some(&method) || at+3+length>payload.len()
            || u16::from_le_bytes([payload[at+1],payload[at+2]]) as usize!=length {return Err(invalid());}
        let args=&payload[at+3..at+3+length];
        let correct=match method {
            0x0d=>args[..4]==[0;4] && args[4..]==own_vehicle.to_le_bytes(),
            0x8d=>args[0]==2 && args[1..]==1i32.to_le_bytes(),
            0x86=>args.is_empty(),
            0x0c=>args==[0;8],
            _=>false,
        };
        if !correct {return Err(invalid());}at+=3+length;
    }
    if at!=payload.len() {return Err(invalid());}Ok(())
}

fn arena_update(body:&mut Vec<u8>,update:u8,literal:&[u8])->io::Result<()> {
    if literal.is_empty() || literal.len()>64 {return Err(invalid());}
    // Already measured client updateArena58: selected Avatar, variable method,
    // UINT8 update type then native short STRING. No arbitrary object encoder.
    body.extend([0x13,0x58,(literal.len()+2) as u8,update,literal.len() as u8]);
    body.extend(literal);Ok(())
}

/// One owned reliable body: native clock bootstrap, roster readiness, PREBATTLE.
/// Original native serverTime advances from this anchor on its own clock. No
/// client clock/UI replacement, no tickSync cadence or RTT accuracy is claimed.
pub fn preparation_body(own_vehicle:u32)->io::Result<Vec<u8>> {
    if own_vehicle!=crate::arena_vehicle091::VEHICLE_ENTITY_ID {return Err(invalid());}
    let mut body=vec![0x02,FREQUENCY,0x03];body.extend(GAME_TICKS.to_le_bytes());
    let mut ready=vec![0x80,2,b'J'];ready.extend((own_vehicle as i32).to_le_bytes());ready.push(b'.');
    arena_update(&mut body,7,&ready)?;
    let mut period=vec![0x80,2,b'(',b'K',2,b'G'];
    period.extend(END_GAME_SECONDS.to_be_bytes());period.push(b'G');
    period.extend((PREPARATION.as_secs() as f64).to_be_bytes());period.extend(b"Nt.");
    arena_update(&mut body,3,&period)?;
    if body.len()!=READY_BODY_BYTES {return Err(invalid());}Ok(body)
}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Phase {Preparing,Expired}

/// The domain timer knows neither native method IDs nor client-provided clocks.
/// It is created once after authenticated readiness and successful output enqueue.
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Preparation {started:Instant,deadline:Instant,last_checked:Instant,phase:Phase}
impl Preparation {
    pub fn new(now:Instant)->io::Result<Self> {
        Ok(Self {started:now,deadline:now.checked_add(PREPARATION).ok_or_else(invalid)?,last_checked:now,phase:Phase::Preparing})
    }
    pub fn phase(&self)->Phase {self.phase}
    pub fn poll_expired(&mut self,now:Instant)->io::Result<bool> {
        if now<self.last_checked || now<self.started {return Err(invalid());}
        self.last_checked=now;
        if self.phase==Phase::Preparing && now>=self.deadline {self.phase=Phase::Expired;return Ok(true);}
        Ok(false)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    pub(crate) const ACTUAL:[u8;33]=[
        0x0d,8,0,0,0,0,0,3,0,16,9,0x8d,5,0,2,1,0,0,0,0x86,0,0,0x0c,8,0,0,0,0,0,0,0,0,0];
    const OWN:u32=crate::arena_vehicle091::VEHICLE_ENTITY_ID;
    #[test] fn actual_whole_compound_has_one_ready_and_three_unsupported_controls() {
        validate_compound(&ACTUAL,OWN).unwrap();
        for id in [0,1,OWN-1,OWN+1,u32::MAX] {assert!(validate_compound(&ACTUAL,id).is_err());}
    }
    #[test] fn every_changed_byte_truncation_and_suffix_fails_before_acceptance() {
        for i in 0..ACTUAL.len() {let mut bad=ACTUAL;bad[i]^=1;assert!(validate_compound(&bad,OWN).is_err(),"byte {i}");}
        for n in 0..ACTUAL.len() {assert!(validate_compound(&ACTUAL[..n],OWN).is_err(),"length {n}");}
        for suffix in [&[0][..],&ACTUAL[..],&ACTUAL[19..22]] {
            assert!(validate_compound(&[ACTUAL.as_slice(),suffix].concat(),OWN).is_err());
        }
        assert!(validate_compound(&vec![0;513],OWN).is_err());
    }
    #[test] fn split_reordered_duplicate_or_unknown_methods_do_not_partially_accept_ready() {
        for bad in [ACTUAL[19..22].to_vec(),ACTUAL[19..].to_vec(),
            [&ACTUAL[11..19],&ACTUAL[..11],&ACTUAL[19..]].concat(),
            [&ACTUAL[..19],&ACTUAL[19..22],&ACTUAL[19..22]].concat(),
            [&ACTUAL[..22],&[0xee,8,0,0,0,0,0,0,0,0,0]].concat()] {
            assert!(validate_compound(&bad,OWN).is_err());
        }
        let mut over=ACTUAL;over[23]=255;over[24]=255;assert!(validate_compound(&over,OWN).is_err());
    }
    #[test] fn literal_clock_ready_period_layout_matches_independent_static_proposal() {
        // Golden from original contract analysis, not a production decoder.
        let expected=[
            2,10,3,232,3,0,0,19,88,10,7,8,128,2,74,3,0,16,9,46,
            19,88,28,3,26,128,2,40,75,2,71,64,96,64,0,0,0,0,0,
            71,64,62,0,0,0,0,0,0,78,116,46];
        assert_eq!(preparation_body(OWN).unwrap(),expected);
        assert_eq!(GAME_TICKS as f64/FREQUENCY as f64,START_GAME_SECONDS);
        assert_eq!(END_GAME_SECONDS-START_GAME_SECONDS,PREPARATION.as_secs() as f64);
        for bad in [0,1,OWN+1,u32::MAX] {assert!(preparation_body(bad).is_err());}
    }
    #[test] fn bounded_literal_cannot_hide_an_object_or_oversized_stream() {
        for value in [vec![],vec![0;65]] {
            let mut body=vec![];assert!(arena_update(&mut body,3,&value).is_err());assert!(body.is_empty());
        }
        let body=preparation_body(OWN).unwrap();assert_eq!(body.len(),51);
        // No production path accepts a supplied literal: only fixed call sites.
        assert_eq!(&body[12..20],&[128,2,74,3,0,16,9,46]);
        assert_eq!(&body[25..31],&[128,2,40,75,2,71]);
        assert_eq!(&body[48..],b"Nt.");
    }
    #[test] fn monotonic_exact_deadline_expires_once_and_never_becomes_battle() {
        let start=Instant::now();let mut p=Preparation::new(start).unwrap();
        assert!(!p.poll_expired(start+PREPARATION-Duration::from_nanos(1)).unwrap());
        assert_eq!(p.phase(),Phase::Preparing);
        assert!(p.poll_expired(start+PREPARATION).unwrap());assert_eq!(p.phase(),Phase::Expired);
        assert!(!p.poll_expired(start+PREPARATION+Duration::from_secs(60)).unwrap());
        assert_eq!(p.phase(),Phase::Expired);
    }
    #[test] fn regressed_time_preserves_domain_deadline_and_phase() {
        let start=Instant::now();let mut p=Preparation::new(start).unwrap();
        p.poll_expired(start+Duration::from_secs(5)).unwrap();let before=p.clone();
        assert!(p.poll_expired(start+Duration::from_secs(4)).is_err());assert_eq!(p,before);
        assert!(p.poll_expired(start.checked_sub(Duration::from_secs(1)).unwrap()).is_err());assert_eq!(p,before);
        assert!(p.poll_expired(start+PREPARATION).unwrap());
    }
}
