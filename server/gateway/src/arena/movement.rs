//! Explicit one-vehicle laboratory kinematics; NOT terrain or historical physics.
//! Original #717 method/PE contracts: arena-movement/wire/CONTRACT.md.
use std::{io,time::{Duration,Instant}};

pub const FREQUENCY:u32=10;
pub const INITIAL_TICK:u32=1000;
pub const PHASE_SECONDS:u64=60;
pub const STOP_DEADLINE:Duration=Duration::from_secs(8);
pub const MAX_AIM_METHODS:u16=256;
pub const MAX_MOVE_METHODS:u16=32;
pub const POSITION:[f32;3]=[-58.499908447265625,33.770267486572266,-445.81304931640625];
pub const MAX_DISPLACEMENT:f64=2.0;
fn invalid()->io::Error {io::Error::new(io::ErrorKind::InvalidData,"unsupported bounded laboratory movement")}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Command {Idle,Forward}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Method {Move(Command),UnsupportedAim(u8)}

/// Decode the complete application body before any domain state is touched.
/// Aiming is structurally recognized solely to keep its bounded unsupported
/// traffic distinct from unknown messages. Its values are NEVER applied/logged.
pub fn methods(body:&[u8],own_vehicle:u32)->io::Result<Vec<Method>> {
    if own_vehicle!=crate::arena_vehicle091::VEHICLE_ENTITY_ID || body.is_empty() || body.len()>512 {return Err(invalid());}
    let mut out=Vec::new();let mut at=0usize;
    while at<body.len() {
        if out.len()>=16 || body.len()-at<3 {return Err(invalid());}
        let id=body[at];let n=u16::from_le_bytes([body[at+1],body[at+2]]) as usize;
        at+=3;if n>body.len()-at {return Err(invalid());}
        let args=&body[at..at+n];at+=n;
        let method=match (id,n) {
            (0x8a,1)=>Method::Move(match args[0] {0=>Command::Idle,1=>Command::Forward,_=>return Err(invalid())}),
            (0x8e,8)|(0x8f,12)|(0x0f,16)=>{
                let floats=if id==0x0f {
                    if args[..4]!=own_vehicle.to_le_bytes() {return Err(invalid());}&args[4..]
                } else {args};
                for part in floats.chunks_exact(4) {
                    let value=f32::from_le_bytes(part.try_into().map_err(|_|invalid())?);
                    if !value.is_finite() || value.abs()>1_000_000.0 {return Err(invalid());}
                }
                Method::UnsupportedAim(id)
            },
            _=>return Err(invalid()),
        };out.push(method);
    }
    Ok(out)
}

/// One native clock/ready/BATTLE phase body, only in the movement diagnostic.
/// This reuses no mutable old-mode setting: Ready's PREBATTLE remains unchanged.
pub fn phase_body(own_vehicle:u32)->io::Result<Vec<u8>> {
    if own_vehicle!=crate::arena_vehicle091::VEHICLE_ENTITY_ID {return Err(invalid());}
    let mut body=vec![2,FREQUENCY as u8,3];body.extend(INITIAL_TICK.to_le_bytes());
    body.extend([0x13,0x58,10,7,8,0x80,2,b'J']);body.extend(own_vehicle.to_le_bytes());body.push(b'.');
    body.extend([0x13,0x58,28,3,26,0x80,2,b'(',b'K',3,b'G']);
    body.extend(160f64.to_be_bytes());body.push(b'G');body.extend(60f64.to_be_bytes());body.extend(b"Nt.");
    if body.len()!=51 {return Err(invalid());}Ok(body)
}

/// Exact #717 tickSync followed by avatarUpdateNoAliasDetailed. No reference
/// byte, no controlEntity, no forcedPosition, no client-supplied coordinates.
pub fn position_body(own_vehicle:u32,tick:u32,position:[f32;3])->io::Result<Vec<u8>> {
    if own_vehicle!=crate::arena_vehicle091::VEHICLE_ENTITY_ID || !(INITIAL_TICK..=INITIAL_TICK+600).contains(&tick)
        || position.iter().any(|v|!v.is_finite()) || position[0]!=POSITION[0] || position[1]!=POSITION[1]
        || position[2]<POSITION[2] || position[2]>POSITION[2]+MAX_DISPLACEMENT as f32 {return Err(invalid());}
    let mut body=vec![0x0d,(tick&255) as u8,0x15];body.extend(own_vehicle.to_le_bytes());
    for v in position {body.extend(v.to_le_bytes());}for _ in 0..3 {body.extend(0f32.to_le_bytes());}
    Ok(body)
}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Phase {Waiting,Moving,Stopped,Failed}
impl Phase {pub fn name(self)->&'static str {match self {Self::Waiting=>"waiting",Self::Moving=>"moving",Self::Stopped=>"stopped",Self::Failed=>"failed"}}}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Action {Idle,Started,AlreadyMoving,Stopped,AlreadyStopped}
impl Action {pub fn name(self)->&'static str {match self {Self::Idle=>"idle",Self::Started=>"started",Self::AlreadyMoving=>"already_moving",Self::Stopped=>"stopped",Self::AlreadyStopped=>"already_stopped"}}}
#[derive(Clone,Copy,Debug,PartialEq)]
pub enum Pulse {None,Position {tick:u32,position:[f32;3]},Expired(&'static str)}

/// The domain contains only a typed intention and authoritative monotonic state.
/// It never knows mailbox IDs, client time/coordinates, terrain, HP or economy.
#[derive(Clone,Debug,PartialEq)]
pub struct Motion {
    created:Instant,last_checked:Instant,started:Option<Instant>,phase:Phase,
    stopped_displacement:f64,last_tick:Option<u32>,move_methods:u16,aim_methods:u16,
}
impl Motion {
    pub fn new(now:Instant)->Self {Self {created:now,last_checked:now,started:None,phase:Phase::Waiting,
        stopped_displacement:0.0,last_tick:Some(INITIAL_TICK),move_methods:0,aim_methods:0}}
    pub fn phase(&self)->Phase {self.phase}
    pub fn move_methods(&self)->u16 {self.move_methods}
    pub fn aim_methods(&self)->u16 {self.aim_methods}
    pub fn elapsed_seconds(&self,now:Instant)->f64 {now.saturating_duration_since(self.created).as_secs_f64()}
    pub fn started_seconds(&self)->Option<f64> {self.started.map(|t|t.duration_since(self.created).as_secs_f64())}
    fn valid_clock(&self,now:Instant)->io::Result<()> {
        if now<self.created || now<self.last_checked || self.phase==Phase::Failed {return Err(invalid());}Ok(())
    }
    fn expiry(&self,now:Instant)->Option<&'static str> {
        if now.duration_since(self.created)>=Duration::from_secs(PHASE_SECONDS) {Some("phase_deadline")}
        else if self.phase==Phase::Moving && self.started.is_some_and(|s|now.duration_since(s)>=STOP_DEADLINE) {Some("missing_stop")}
        else {None}
    }
    pub fn displacement(&self,now:Instant)->f64 {
        match self.phase {Phase::Moving=>self.started.map(|s|now.saturating_duration_since(s).as_secs_f64().min(MAX_DISPLACEMENT)).unwrap_or(0.0),
            Phase::Stopped|Phase::Failed=>self.stopped_displacement,Phase::Waiting=>0.0}
    }
    pub fn position(&self,now:Instant)->[f32;3] {
        [POSITION[0],POSITION[1],(POSITION[2] as f64+self.displacement(now)) as f32]
    }
    pub fn command(&mut self,command:Command,now:Instant)->io::Result<Action> {
        self.valid_clock(now)?;
        if self.expiry(now).is_some() || self.move_methods>=MAX_MOVE_METHODS {return Err(invalid());}
        let action=match (self.phase,command) {
            (Phase::Waiting,Command::Idle)=>Action::Idle,
            (Phase::Waiting,Command::Forward)=>Action::Started,
            (Phase::Moving,Command::Forward)=>Action::AlreadyMoving,
            (Phase::Moving,Command::Idle)=>Action::Stopped,
            (Phase::Stopped,Command::Idle)=>Action::AlreadyStopped,
            _=>return Err(invalid()),
        };
        if action==Action::Started {self.started=Some(now);self.phase=Phase::Moving;}
        if action==Action::Stopped {self.stopped_displacement=self.displacement(now);self.phase=Phase::Stopped;}
        self.last_checked=now;self.move_methods+=1;Ok(action)
    }
    pub fn unsupported_aim(&mut self,now:Instant)->io::Result<()> {
        self.valid_clock(now)?;
        if self.expiry(now).is_some() || self.aim_methods>=MAX_AIM_METHODS {return Err(invalid());}
        self.last_checked=now;self.aim_methods+=1;Ok(())
    }
    /// At most one newest sample per poll. Missed ticks are never replayed in a
    /// catch-up loop. Caller commits this state only after bounded enqueue.
    pub fn poll(&mut self,now:Instant)->io::Result<Pulse> {
        self.valid_clock(now)?;
        if let Some(reason)=self.expiry(now) {
            self.stopped_displacement=self.displacement(now);self.phase=Phase::Failed;self.last_checked=now;
            return Ok(Pulse::Expired(reason));
        }
        let tick=INITIAL_TICK+((now.duration_since(self.created).as_millis()/100) as u32);
        self.last_checked=now;
        if self.last_tick==Some(tick) {return Ok(Pulse::None);}
        self.last_tick=Some(tick);Ok(Pulse::Position {tick,position:self.position(now)})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const OWN:u32=crate::arena_vehicle091::VEHICLE_ENTITY_ID;
    #[test] fn static_native_move_bytes_and_whole_mixed_aim_boundaries() {
        assert_eq!(methods(&[0x8a,1,0,1],OWN).unwrap(),vec![Method::Move(Command::Forward)]);
        let mut b=vec![0x8f,12,0];b.extend([0;12]);b.extend([0x8a,1,0,0]);b.extend([0x0f,16,0]);b.extend(OWN.to_le_bytes());b.extend([0;12]);
        assert_eq!(methods(&b,OWN).unwrap(),vec![Method::UnsupportedAim(0x8f),Method::Move(Command::Idle),Method::UnsupportedAim(0x0f)]);
        for n in 0..4 {assert!(methods(&[0x8a,1,0,1][..n],OWN).is_err());}
        for flag in 2..=255 {assert!(methods(&[0x8a,1,0,flag],OWN).is_err());}
        for bad in [vec![0x8a,2,0,1],vec![0x8a,1,1,1],vec![0x8a,1,0,1,0xee],vec![0;513],vec![0x86,0,0]] {assert!(methods(&bad,OWN).is_err());}
        assert!(methods(&[0x8a,1,0,1],OWN+1).is_err());
    }
    #[test] fn aiming_nonfinite_wrong_target_lengths_and_method_bound_rejected() {
        for (id,size) in [(0x8e,8),(0x8f,12),(0x0f,16)] {
            let mut b=vec![id,size,0];if id==0x0f {b.extend(OWN.to_le_bytes());}
            while b.len()<3+size as usize {b.extend(0f32.to_le_bytes());}
            assert!(methods(&b,OWN).is_ok());
            for value in [f32::NAN,f32::INFINITY,f32::NEG_INFINITY,1_000_001.0] {
                let mut bad=b.clone();let at=if id==0x0f{7}else{3};bad[at..at+4].copy_from_slice(&value.to_le_bytes());assert!(methods(&bad,OWN).is_err());
            }
            if id==0x0f {b[3]^=1;assert!(methods(&b,OWN).is_err());}
        }
        assert_eq!(methods(&[0x8a,1,0,0].repeat(16),OWN).unwrap().len(),16);
        assert!(methods(&[0x8a,1,0,0].repeat(17),OWN).is_err());
    }
    #[test] fn native_phase_clock_literal_is_separate_from_preparation() {
        let b=phase_body(OWN).unwrap();assert_eq!(b.len(),51);assert_eq!(&b[..7],&[2,10,3,232,3,0,0]);
        assert_eq!(b[29],3);assert_eq!(&b[31..39],&160f64.to_be_bytes());assert_eq!(&b[40..48],&60f64.to_be_bytes());
        assert_eq!(&b[48..],b"Nt.");assert!(phase_body(OWN+1).is_err());
        let old=crate::arena_ready091::preparation_body(OWN).unwrap();assert_eq!(old[29],2);assert_eq!(&old[31..39],&130f64.to_be_bytes());
    }
    #[test] fn exact_position_body_and_low8_wrap_no_modern_extra_bytes() {
        let b=position_body(OWN,1023,POSITION).unwrap();assert_eq!(b.len(),31);
        assert_eq!(&b[..7],&[13,255,21,3,0,16,9]);assert_eq!(&b[7..11],&POSITION[0].to_le_bytes());
        assert_eq!(&b[11..15],&POSITION[1].to_le_bytes());assert_eq!(&b[15..19],&POSITION[2].to_le_bytes());assert_eq!(&b[19..],&[0;12]);
        assert_eq!(position_body(OWN,1024,POSITION).unwrap()[1],0);
        for bad in [999,1601,u32::MAX] {assert!(position_body(OWN,bad,POSITION).is_err());}
        assert!(position_body(OWN+1,1000,POSITION).is_err());
        for p in [[POSITION[0]+1.0,POSITION[1],POSITION[2]],[POSITION[0],f32::NAN,POSITION[2]],
            [POSITION[0],POSITION[1],POSITION[2]-0.1],[POSITION[0],POSITION[1],POSITION[2]+2.1]] {assert!(position_body(OWN,1000,p).is_err());}
    }
    #[test] fn idle_forward_cap_real_stop_and_duplicate_never_restart() {
        let t=Instant::now();let mut m=Motion::new(t);assert_eq!(m.command(Command::Idle,t).unwrap(),Action::Idle);
        assert_eq!(m.position(t),POSITION);assert_eq!(m.command(Command::Forward,t).unwrap(),Action::Started);
        assert_eq!(m.command(Command::Forward,t+Duration::from_secs(1)).unwrap(),Action::AlreadyMoving);
        assert_eq!(m.displacement(t+Duration::from_secs(1)),1.0);assert_eq!(m.displacement(t+Duration::from_secs(5)),2.0);
        assert_eq!(m.phase(),Phase::Moving);assert_eq!(m.command(Command::Idle,t+Duration::from_secs(5)).unwrap(),Action::Stopped);
        assert_eq!(m.command(Command::Idle,t+Duration::from_secs(6)).unwrap(),Action::AlreadyStopped);
        assert_eq!(m.displacement(t+Duration::from_secs(7)),2.0);let before=m.clone();
        assert!(m.command(Command::Forward,t+Duration::from_secs(7)).is_err());assert_eq!(m,before);
    }
    #[test] fn early_stop_freezes_reached_pose_not_always_the_cap() {
        let t=Instant::now();let mut m=Motion::new(t);assert_eq!(m.started_seconds(),None);
        m.command(Command::Forward,t+Duration::from_secs(1)).unwrap();
        m.command(Command::Idle,t+Duration::from_millis(1750)).unwrap();assert_eq!(m.displacement(t+Duration::from_secs(3)),0.75);
        assert_eq!(m.started_seconds(),Some(1.0));assert_eq!(m.elapsed_seconds(t+Duration::from_secs(3)),3.0);
        assert_eq!(m.position(t+Duration::from_secs(3))[2],(POSITION[2] as f64+0.75) as f32);
    }
    #[test] fn tick_poll_never_catches_up_or_repeats_same_tick() {
        let t=Instant::now();let mut m=Motion::new(t);assert_eq!(m.poll(t).unwrap(),Pulse::None);
        assert_eq!(m.poll(t+Duration::from_millis(99)).unwrap(),Pulse::None);
        assert!(matches!(m.poll(t+Duration::from_millis(2300)).unwrap(),Pulse::Position{tick:1023,..}));
        assert!(matches!(m.poll(t+Duration::from_millis(2400)).unwrap(),Pulse::Position{tick:1024,..}));
        assert_eq!(m.poll(t+Duration::from_millis(2401)).unwrap(),Pulse::None);
    }
    #[test] fn missing_stop_and_phase_deadlines_fail_not_complete() {
        let t=Instant::now();let mut m=Motion::new(t);m.command(Command::Forward,t).unwrap();
        assert!(matches!(m.poll(t+STOP_DEADLINE-Duration::from_nanos(1)).unwrap(),Pulse::Position{..}));
        assert_eq!(m.poll(t+STOP_DEADLINE).unwrap(),Pulse::Expired("missing_stop"));assert_eq!(m.phase(),Phase::Failed);
        assert!(m.command(Command::Idle,t+STOP_DEADLINE).is_err());
        let mut wait=Motion::new(t);assert_eq!(wait.poll(t+Duration::from_secs(60)).unwrap(),Pulse::Expired("phase_deadline"));
    }
    #[test] fn regressed_time_and_counter_limits_do_not_partially_mutate() {
        let t=Instant::now();let mut m=Motion::new(t);m.poll(t+Duration::from_secs(1)).unwrap();let before=m.clone();
        assert!(m.command(Command::Forward,t).is_err());assert_eq!(m,before);assert!(m.poll(t).is_err());assert_eq!(m,before);
        let now=t+Duration::from_secs(1);for _ in 0..MAX_MOVE_METHODS {m.command(Command::Idle,now).unwrap();}
        let before=m.clone();assert!(m.command(Command::Idle,now).is_err());assert_eq!(m,before);
        for _ in 0..MAX_AIM_METHODS {m.unsupported_aim(now).unwrap();}
        let before=m.clone();assert!(m.unsupported_aim(now).is_err());assert_eq!(m,before);
    }
}
