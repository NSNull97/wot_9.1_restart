//! First map-drive binding experiment, not a terrain/full-drive implementation.
//! #717 original PE/.def and failed native framing proof: p02-map-drive/wire/CONTRACT-02.md.
//! The native Avatar is attached to the real own Vehicle. No controlEntity,
//! generic client physics, position assignment, or client-coordinate authority.
use std::{io,time::Instant};
use crate::arena_movement091::{self as lab,Method as LabMethod,Motion,Phase};

pub const MAX_CORRECTION_ACKS:u16=8;
pub const MAX_PLAYER_TELEMETRY:u16=1024;
fn invalid()->io::Error {io::Error::new(io::ErrorKind::InvalidData,"unsupported map-drive binding checkpoint")}
fn owned(own:u32)->io::Result<()> {
    if own!=crate::arena_vehicle091::VEHICLE_ENTITY_ID {return Err(invalid());}Ok(())
}

/// Avatar client exposed method15: ID0x4a FIXED32, VECTOR3+VECTOR3+f32+f32.
/// The native method-size lookup uses its fixed argument size: no length byte.
/// Selection13 routes the method to the actual native PlayerAvatar. Here the
/// direction and rotational speed are zero, not invented historical dynamics.
fn own_position(own:u32,position:[f32;3],speed:f32)->io::Result<Vec<u8>> {
    // Reuse the unchanged lab coordinate bounds, never a client observation.
    lab::position_body(own,lab::INITIAL_TICK,position)?;
    if ![0.0,1.0].contains(&speed) {return Err(invalid());}
    let mut out=vec![0x13,0x4a];
    for v in position {out.extend(v.to_le_bytes());}
    for _ in 0..3 {out.extend(0f32.to_le_bytes());}
    out.extend(speed.to_le_bytes());out.extend(0f32.to_le_bytes());
    debug_assert_eq!(out.len(),34);Ok(out)
}

/// Real forcedPosition: PLAYER/space/attachment, relative origin, neutral YPR.
/// Native filter output installs read-only Entity.vehicle. setVehicle alone
/// only changes ServerConnection's map and is insufficient for this proof.
pub fn binding_body(own:u32)->io::Result<Vec<u8>> {
    owned(own)?;
    let mut body=lab::phase_body(own)?;
    body.push(0x14);body.extend(crate::arena_control091::AVATAR_ENTITY_ID.to_le_bytes());
    body.extend(1u32.to_le_bytes());body.extend(own.to_le_bytes());
    for _ in 0..6 {body.extend(0f32.to_le_bytes());}
    body.extend(own_position(own,lab::POSITION,0.0)?);
    debug_assert_eq!(body.len(),122);Ok(body)
}

pub fn publication_body(own:u32,tick:u32,position:[f32;3],speed:f32)->io::Result<Vec<u8>> {
    let mut body=lab::position_body(own,tick,position)?;
    body.extend(own_position(own,position,speed)?);
    debug_assert_eq!(body.len(),65);Ok(body)
}
pub fn authoritative_speed(motion:&Motion,now:Instant)->f32 {
    if motion.phase()==Phase::Moving && motion.displacement(now)<lab::MAX_DISPLACEMENT {1.0}else{0.0}
}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Method {CorrectionAck,IgnoredPlayerTelemetry(u8),Lab(LabMethod)}

/// Whole-envelope validation, including exact fixed-size native messages mixed
/// with the already measured mailbox methods. Positions are checked for bounded
/// representation then discarded; no decoded coordinate survives this reader.
pub fn methods(body:&[u8],own:u32)->io::Result<Vec<Method>> {
    owned(own)?;
    if body.is_empty() || body.len()>512 {return Err(invalid());}
    let mut at=0usize;let mut out=Vec::new();
    while at<body.len() {
        if out.len()>=16 {return Err(invalid());}
        let start=at;let id=body[at];at+=1;
        let method=match id {
            6=>Method::CorrectionAck,
            2|3=>{
                let n=if id==2{16}else{21};
                if body.len()-at<n {return Err(invalid());}
                let args=&body[at..at+n];at+=n;
                let xyz=if id==3 {
                    if args[..4]!=own.to_le_bytes() || args[19]>1 {return Err(invalid());}
                    &args[4..16]
                }else{&args[..12]};
                for b in xyz.chunks_exact(4) {
                    let v=f32::from_le_bytes(b.try_into().map_err(|_|invalid())?);
                    if !v.is_finite() || v.abs()>1_000_000.0 {return Err(invalid());}
                }
                Method::IgnoredPlayerTelemetry(id)
            },
            0x8a|0x8e|0x8f|0x0f=>{
                if body.len()-at<2 {return Err(invalid());}
                let n=u16::from_le_bytes([body[at],body[at+1]]) as usize;at+=2;
                if n>body.len()-at {return Err(invalid());}at+=n;
                let parsed=lab::methods(&body[start..at],own)?;
                if parsed.len()!=1 {return Err(invalid());}Method::Lab(parsed[0])
            },
            // Ward correction7/positions4/5, unknown fields and late malformed
            // methods must fail the entire envelope, never the observation sink.
            _=>return Err(invalid()),
        };out.push(method);
    }
    Ok(out)
}

#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Binding {
    pub force_sequence:u32,pub force_acked:bool,
    correction_acks:u16,player_telemetry:u16,
}
impl Binding {
    pub fn new(force_sequence:u32)->Self {Self {force_sequence,force_acked:false,correction_acks:0,player_telemetry:0}}
    pub fn correction_acknowledged(&self)->bool {self.correction_acks>0}
    pub fn correction_acks(&self)->u16 {self.correction_acks}
    pub fn player_telemetry(&self)->u16 {self.player_telemetry}
    pub fn correction_ack(&mut self)->io::Result<bool> {
        if !self.force_acked || self.correction_acks>=MAX_CORRECTION_ACKS {return Err(invalid());}
        let first=self.correction_acks==0;self.correction_acks+=1;Ok(first)
    }
    pub fn ignored_player_telemetry(&mut self)->io::Result<()> {
        if self.player_telemetry>=MAX_PLAYER_TELEMETRY {return Err(invalid());}
        self.player_telemetry+=1;Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;
    const OWN:u32=crate::arena_vehicle091::VEHICLE_ENTITY_ID;
    #[test] fn binding_native_literal_has_player_force_and_exact_own_callback() {
        let b=binding_body(OWN).unwrap();assert_eq!(b.len(),122);
        assert_eq!(&b[..51],lab::phase_body(OWN).unwrap());
        assert_eq!(&b[51..64],&[20,2,0,16,9,1,0,0,0,3,0,16,9]);
        assert_eq!(&b[64..88],&[0;24]);assert_eq!(&b[88..90],&[19,74]);
        for (n,v) in lab::POSITION.iter().enumerate(){assert_eq!(&b[90+n*4..94+n*4],&v.to_le_bytes());}
        assert_eq!(&b[102..],&[0;20]);assert!(binding_body(OWN+1).is_err());
    }
    #[test] fn fixed_method_regression_matches_native_bind01_shifted_float_bits() {
        // Bind01 actual original callback read these first four little-endian
        // float bits from the erroneous VAR1 prefix, not the intended pose.
        let correct=own_position(OWN,lab::POSITION,0.0).unwrap();
        assert_eq!(&correct[..2],&[0x13,0x4a]);assert_eq!(correct[2..].len(),32);
        assert_eq!(&correct[2..14],&[0xe8,0xff,0x69,0xc2,0xc1,0x14,0x07,0x42,0x12,0xe8,0xde,0xc3]);
        let read_fixed=|args:&[u8]|->Option<Vec<u32>> {
            if args.len()!=32{return None;}
            Some(args.chunks_exact(4).map(|b|u32::from_le_bytes(b.try_into().unwrap())).collect())
        };
        assert_eq!(read_fixed(&correct[2..]).unwrap(),vec![0xc269ffe8,0x420714c1,0xc3dee812,0,0,0,0,0]);
        let mut legacy=vec![0x20];legacy.extend(&correct[2..]);
        assert!(read_fixed(&legacy).is_none());
        assert_eq!(&read_fixed(&legacy[..32]).unwrap()[..4],&[0x69ffe820,0x0714c1c2,0xdee81242,0x000000c3]);
        assert_eq!(legacy[32],0); // stray byte also remained after the native method
    }
    #[test] fn publications_keep_vehicle_and_avatar_pose_equal_with_derived_speed() {
        let t=Instant::now();let mut m=Motion::new(t);assert_eq!(authoritative_speed(&m,t),0.0);
        m.command(lab::Command::Forward,t).unwrap();let now=t+Duration::from_millis(500);
        let b=publication_body(OWN,1005,m.position(now),authoritative_speed(&m,now)).unwrap();
        assert_eq!(b.len(),65);assert_eq!(&b[..31],lab::position_body(OWN,1005,m.position(now)).unwrap());
        assert_eq!(&b[31..33],&[19,74]);assert_eq!(&b[33..45],&b[7..19]);
        assert_eq!(&b[57..61],&1f32.to_le_bytes());assert_eq!(&b[61..],&[0;4]);
        assert_eq!(authoritative_speed(&m,t+Duration::from_secs(2)),0.0);
        m.command(lab::Command::Idle,t+Duration::from_millis(750)).unwrap();assert_eq!(authoritative_speed(&m,now),0.0);
        for v in [f32::NAN,f32::INFINITY,-1.0,2.0] {assert!(publication_body(OWN,1001,lab::POSITION,v).is_err());}
        assert_eq!(publication_body(OWN,1024,lab::POSITION,0.0).unwrap()[1],0);
    }
    #[test] fn exact_ack6_mixed_methods_and_player_telemetry_never_return_coordinates() {
        let mut b=vec![6,2];b.extend([0;16]);b.extend([0x8a,1,0,1]);
        assert_eq!(methods(&b,OWN).unwrap(),vec![Method::CorrectionAck,Method::IgnoredPlayerTelemetry(2),Method::Lab(LabMethod::Move(lab::Command::Forward))]);
        let mut explicit=vec![3];explicit.extend(OWN.to_le_bytes());explicit.extend([0;17]);
        assert_eq!(methods(&explicit,OWN).unwrap(),vec![Method::IgnoredPlayerTelemetry(3)]);
        explicit[20]=2;assert!(methods(&explicit,OWN).is_err());
        assert_eq!(methods(&[6],OWN).unwrap(),vec![Method::CorrectionAck]);
        for bad in [vec![6,0],vec![7,3,0,16,9],vec![4;20],vec![5;29],vec![6;17],vec![],vec![6;513]] {assert!(methods(&bad,OWN).is_err());}
    }
    #[test] fn telemetry_truncation_foreign_attachment_and_late_poison_are_rejected() {
        for id in [2,3] {
            let mut b=vec![id];if id==3{b.extend(OWN.to_le_bytes());}b.extend([0;12]);b.extend([0;3]);
            if id==3{b.push(0);}b.push(0);
            assert!(methods(&b,OWN).is_ok());
            for n in 1..b.len(){assert!(methods(&b[..n],OWN).is_err());}
            for v in [f32::NAN,f32::INFINITY,1_000_001.0] {
                let mut bad=b.clone();let at=if id==2{1}else{5};bad[at..at+4].copy_from_slice(&v.to_le_bytes());assert!(methods(&bad,OWN).is_err());
            }
            if id==3{let mut bad=b.clone();bad[1]^=1;assert!(methods(&bad,OWN).is_err());}
            b.extend([0x8a,1,0,1,7]);assert!(methods(&b,OWN).is_err());
        }
    }
    #[test] fn correction_requires_its_ack_and_duplicates_do_not_rebind() {
        let mut b=Binding::new(7);let before=b.clone();assert!(b.correction_ack().is_err());assert_eq!(b,before);
        b.force_acked=true;assert_eq!(b.correction_ack().unwrap(),true);
        for _ in 1..MAX_CORRECTION_ACKS {assert_eq!(b.correction_ack().unwrap(),false);}
        let before=b.clone();assert!(b.correction_ack().is_err());assert_eq!(b,before);assert_eq!(b.force_sequence,7);
        for _ in 0..MAX_PLAYER_TELEMETRY {b.ignored_player_telemetry().unwrap();}
        let before=b.clone();assert!(b.ignored_player_telemetry().is_err());assert_eq!(b,before);
    }
}
