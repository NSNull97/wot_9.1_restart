//! Ordinary own test_lab arena wire, distinct from frozen two-metre probes.
//! #717 source layouts: map-drive/wire/CONTRACT-02, queue-static-02, map-ids-01.
//! Codecs consume ONLY server-owned identity, spawn and physics worker state.
use std::{io,time::{Instant,Duration}};
use crate::{arena_vehicle091 as vehicle,map_drive_worker091::{Input,Pose,MapSpec}};
pub const OWN:u32=vehicle::VEHICLE_ENTITY_ID;
pub const AVATAR:u32=crate::arena_control091::AVATAR_ENTITY_ID;
pub const MAX_ARENAS:u32=32;
pub const WORLD_SECONDS:u32=3600;
fn bad()->io::Error{io::Error::new(io::ErrorKind::InvalidData,"ordinary map-drive contract")}
fn var16(id:u8,args:&[u8])->io::Result<Vec<u8>>{if args.is_empty() || args.len()>512{return Err(bad());}
    let mut b=vec![id];b.extend((args.len() as u16).to_le_bytes());b.extend(args);Ok(b)}
fn string(b:&mut Vec<u8>,x:&[u8])->io::Result<()>{if x.len()>=255{return Err(bad());}b.push(x.len() as u8);b.extend(x);Ok(())}
fn f3(b:&mut Vec<u8>,v:[f32;3]){for x in v{b.extend(x.to_le_bytes());}}
// #717 PE d6da90/d6e490 reverse raw Direction3D into EntityManager YPR;
// named Entity getters +28/+2c/+30 prove yaw/pitch/roll. See map-drive/wire/
// direction-contract-01. Only native createCellPlayer/NoAliasDetailed use RPY;
// createEntityDetailed and Avatar.updateOwnVehiclePosition remain explicit YPR.
fn native_direction(b:&mut Vec<u8>,ypr:[f32;3]){f3(b,[ypr[2],ypr[1],ypr[0]]);}
fn pose(p:&Pose)->io::Result<()>{
    if p.position.iter().any(|x|!x.is_finite() || x.abs()>2000.) || p.direction.iter().any(|x|!x.is_finite() || x.abs()>std::f32::consts::PI)
        || !p.speed.is_finite() || p.speed.abs()>25. || !p.rspeed.is_finite() || p.rspeed.abs()>20. {return Err(bad());}Ok(())
}
fn world(map:&MapSpec,space:u32)->io::Result<()>{
    if space==0 || space>MAX_ARENAS || !matches!((map.asset.as_str(),map.arena_type_id),("01_karelia",1)|("05_prohorovka",4)){return Err(bad());}Ok(())
}
pub fn reset_avatar(seed:&vehicle::VehicleSeed,map:&MapSpec,space:u32,unique:u64)->io::Result<Vec<u8>>{
    world(map,space)?;if unique==0{return Err(bad());}
    // Reuse the frozen seed validator, not its fixed map1/spawn values.
    vehicle::create_requested_vehicle(seed)?;
    let mut p=AVATAR.to_le_bytes().to_vec();p.extend(1u16.to_le_bytes());string(&mut p,seed.name.as_bytes())?;
    p.extend(unique.to_le_bytes());p.extend(map.arena_type_id.to_le_bytes());p.extend([2,2]);
    p.extend([4,0x80,2,b'}',b'.',0,0,0,0]);
    // Original Account.onArenaCreated() precedes actual native reset; no reply
    // is fabricated for request202 (REQUEST_ID_NO_RESPONSE).
    let mut b=vec![0x13,0x3b,4,0];b.extend(var16(5,&p)?);Ok(b)
}
fn roster(seed:&vehicle::VehicleSeed)->io::Result<Vec<u8>>{
    vehicle::create_requested_vehicle(seed)?;
    let mut d=vec![0x80,2,b']',b'(',b'J'];d.extend(OWN.to_le_bytes());
    d.push(b'U');string(&mut d,&seed.descriptor)?;d.push(b'U');string(&mut d,seed.name.as_bytes())?;
    d.extend([b'K',1,0x88,0x89,0x89,b'J']);d.extend(seed.database_id.to_le_bytes());
    d.extend([b'U',0,b'K',0,b'K',0,0x89,b'}',b'K',0,b't',b'a',b'.']);
    let mut b=vec![0x13,0x58,(d.len()+2) as u8,1,d.len() as u8];b.extend(d);Ok(b)
}
pub fn announcement(seed:&vehicle::VehicleSeed,map:&MapSpec,space:u32,p:&Pose)->io::Result<Vec<u8>>{
    world(map,space)?;pose(p)?;
    let mut c=space.to_le_bytes().to_vec();c.extend(0u32.to_le_bytes());f3(&mut c,p.position);c.extend(1f32.to_le_bytes());
    native_direction(&mut c,p.direction);c.push(1);c.extend(OWN.to_le_bytes());c.extend([0,0]);
    if c.len()!=43{return Err(bad());}let mut b=var16(6,&c)?;
    let mut g=space.to_le_bytes().to_vec();g.extend((space as u64).to_le_bytes());g.extend(1u16.to_le_bytes());
    for r in 0..4{for c in 0..4{g.extend((if r==c{1f32}else{0f32}).to_le_bytes());}}
    g.extend(format!("spaces/{}",map.asset).as_bytes());b.extend(var16(7,&g)?);b.extend(roster(seed)?);
    b.push(0x0a);b.extend(OWN.to_le_bytes());b.push(0);if b.len()>512{return Err(bad());}Ok(b)
}
pub fn create_vehicle(seed:&vehicle::VehicleSeed,p:&Pose)->io::Result<Vec<u8>>{
    pose(p)?;let frozen=vehicle::create_requested_vehicle(seed)?;
    if frozen.len()!=97 || frozen[..10]!=[9,94,0,0,3,0,16,9,2,0]{return Err(bad());}
    // Original createDetailed prefix compression0/id/type/XYZ/YPR is fixed31B;
    // all eight validated indexed properties remain exactly the frozen seed.
    let mut b=frozen[..10].to_vec();f3(&mut b,p.position);f3(&mut b,p.direction);b.extend(&frozen[34..]);Ok(b)
}
fn own_position(p:&Pose)->io::Result<Vec<u8>>{pose(p)?;let mut b=vec![0x13,0x4a];
    f3(&mut b,p.position);f3(&mut b,p.direction);b.extend(p.speed.to_le_bytes());b.extend(p.rspeed.to_le_bytes());Ok(b)}
fn update(b:&mut Vec<u8>,kind:u8,d:&[u8]){b.extend([0x13,0x58,(d.len()+2) as u8,kind,d.len() as u8]);b.extend(d);}
pub fn binding(space:u32,p:&Pose)->io::Result<Vec<u8>>{
    if space==0 || space>MAX_ARENAS{return Err(bad());}pose(p)?;
    let mut b=vec![2,10,3];b.extend(1000u32.to_le_bytes());
    let mut ready=vec![0x80,2,b'J'];ready.extend(OWN.to_le_bytes());ready.push(b'.');update(&mut b,7,&ready);
    let mut period=vec![0x80,2,b'(',b'K',3,b'G'];period.extend((100f64+WORLD_SECONDS as f64).to_be_bytes());
    period.push(b'G');period.extend((WORLD_SECONDS as f64).to_be_bytes());period.extend(b"Nt.");update(&mut b,3,&period);
    b.push(0x14);b.extend(AVATAR.to_le_bytes());b.extend(space.to_le_bytes());b.extend(OWN.to_le_bytes());for _ in 0..6{b.extend(0f32.to_le_bytes());}
    b.extend(own_position(p)?);if b.len()!=122{return Err(bad());}Ok(b)
}
/// A/B policy: retain the original one-time binding callback, then feed the
/// native Vehicle filter without resetting Avatar's live matrix provider.
/// This is an experimental compatibility policy, not a claim about WG cadence.
pub const PUBLICATION_POLICY:&str="initial_own_callback_then_entity_only_v1";
pub fn publication_entity_only(tick:u32,p:&Pose)->io::Result<Vec<u8>>{
    pose(p)?;if !(1001..=1000+WORLD_SECONDS*10).contains(&tick){return Err(bad());}
    let mut b=vec![0x0d,tick as u8,0x15];b.extend(OWN.to_le_bytes());f3(&mut b,p.position);native_direction(&mut b,p.direction);
    if b.len()!=31{return Err(bad());}Ok(b)
}
/// Historical 65B policy retained for exact regression and archived evidence.
/// Ordinary steady publication selects publication_entity_only explicitly.
pub fn publication(tick:u32,p:&Pose)->io::Result<Vec<u8>>{
    let mut b=publication_entity_only(tick,p)?;
    b.extend(own_position(p)?);if b.len()!=65{return Err(bad());}Ok(b)
}
pub fn return_account(name:&str)->io::Result<Vec<u8>>{let mut b=vec![4,0];b.extend(crate::hangar091::creation_named(name)?);Ok(b)}
pub fn queue_callback(entered:bool)->Vec<u8>{vec![0x13,if entered{0x3f}else{0x40},1]}
/// #717 Account.receiveQueueInfo (method85, variable8): nullable randoms
/// dictionary, classes ARRAY<UINT32>, then companies/historical None.
/// Queued is one authenticated own MS-1: light/medium/heavy/SPG/AT =1/0/0/0/0.
/// This must precede resetAvatar; it is never sent to an Avatar entity.
pub fn own_queue_info()->Vec<u8>{
    let mut b=vec![0x13,0x55,24,1,5];
    for count in [1u32,0,0,0,0]{b.extend(count.to_le_bytes());}
    b.extend([0,0]);b
}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum AccountCommand{Join,Cancel,QueueInfo}
/// Only original request202, selected MS-1 inventory1, random arenaType0.
/// gameplaysMask is a capability preference; only ctf bit0 can be satisfied.
pub fn account_command(packet:&[u8])->io::Result<Option<AccountCommand>>{
    if packet.first()!=Some(&0x8e) || packet.len()!=23{return Ok(None);}
    let cmd=i16::from_le_bytes([packet[5],packet[6]]);if ![502,700,701].contains(&cmd){return Ok(None);}
    if packet[..5]!=[0x8e,20,0,202,0]{return Err(bad());}
    let vehicle=i64::from_le_bytes(packet[7..15].try_into().map_err(|_|bad())?);
    let mask=i32::from_le_bytes(packet[15..19].try_into().map_err(|_|bad())?);
    let arena=i32::from_le_bytes(packet[19..23].try_into().map_err(|_|bad())?);
    if cmd==502 {if vehicle!=1 || mask!=0 || arena!=0{return Err(bad());}Ok(Some(AccountCommand::QueueInfo))}
    else if cmd==700 {if vehicle!=1 || !(1..=7).contains(&mask) || mask&1==0 || arena!=0{return Err(bad());}Ok(Some(AccountCommand::Join))}
    else {if vehicle!=0 || mask!=0 || arena!=0{return Err(bad());}Ok(Some(AccountCommand::Cancel))}
}
/// An old Account queue poll can cross server resetAvatar before the native
/// client receives it. Accept only this measured poll, optionally followed by
/// native enableEntities in the same ordered envelope; never a generic sink.
pub fn late_queue_info(payload:&[u8])->io::Result<Option<bool>>{
    if payload.first()!=Some(&0x8e) || payload.len()<7 || payload[5..7]!=502i16.to_le_bytes(){return Ok(None);}
    if ![23,24].contains(&payload.len()) || account_command(&payload[..23])?!=Some(AccountCommand::QueueInfo)
        || (payload.len()==24 && payload[23]!=9){return Err(bad());}
    Ok(Some(payload.len()==24))
}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Method{Move(u8,Input),UnsupportedMove(u8),CorrectionAck,IgnoredTelemetry(u8),UnsupportedAim(u8),UnsupportedCameraAutorotation(bool),Leave}
pub fn driving_input(flags:u8)->io::Result<Input>{
    // Source #717 ordinary keyboard flags. Cruise16/32 are NOT brake bits;
    // Unsupported cruise is not interpreted as movement; the whole-envelope
    // caller applies a separately logged safety-neutral policy, never old gas.
    if ![0,1,2,4,8,5,9,6,10].contains(&flags){return Err(bad());}
    Ok(Input{throttle:if flags&1!=0{1}else if flags&2!=0{-1}else{0},
        steer:if flags&4!=0{-1}else if flags&8!=0{1}else{0},brake:flags==0})
}
pub fn methods(b:&[u8])->io::Result<Vec<Method>>{
    if b.is_empty() || b.len()>512{return Err(bad());}let mut at=0;let mut rows=Vec::new();
    while at<b.len(){if rows.len()>=16 || rows.last()==Some(&Method::Leave){return Err(bad());}
        let start=at;let id=b[at];at+=1;
        let row=match id{
            6=>Method::CorrectionAck,
            2|3=>{let len=if id==2{16}else{21};at=at.checked_add(len).ok_or_else(bad)?;
                let raw=b.get(start..at).ok_or_else(bad)?;crate::map_drive091::methods(raw,OWN)?;Method::IgnoredTelemetry(id)},
            0x8a|0x8d|0x8e|0x8f|0x0f|0x99=>{
                if b.len()-at<2{return Err(bad());}let len=u16::from_le_bytes([b[at],b[at+1]]) as usize;at+=2;
                let args=b.get(at..at+len).ok_or_else(bad)?;at+=len;
                match id{
                    0x8a=>{if args.len()!=1{return Err(bad());}match driving_input(args[0]){
                        Ok(input)=>Method::Move(args[0],input),Err(_)=>Method::UnsupportedMove(args[0]),
                    }},
                    // #717 Avatar Base vehicle_changeSetting(UINT8,INT32).
                    // Original sniper entry/return and captured packets1620/1670:
                    // local/evidence/20261006-sniper-camera/capture-review-01.
                    // Recognize ONLY camera autorotation preference. The lab
                    // physics has no gun-driven chassis rotation; no domain
                    // setting, shell selection, equipment or reload is applied.
                    0x8d=>{if args.len()!=5 || args[0]!=2{return Err(bad());}
                        let value=i32::from_le_bytes(args[1..5].try_into().map_err(|_|bad())?);
                        match value{0=>Method::UnsupportedCameraAutorotation(false),1=>Method::UnsupportedCameraAutorotation(true),_=>return Err(bad())}
                    },
                    0x99=>{if args!=[0] && !(args.len()==68 && args[0]==1){return Err(bad());}Method::Leave},
                    _=>{crate::map_drive091::methods(&b[start..at],OWN)?;Method::UnsupportedAim(id)},
                }
            },_=>return Err(bad()),
        };rows.push(row);
    }Ok(rows)
}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Phase{Idle,Queued,Enable,EntityRequest,Ready,Driving,Returning}
#[derive(Clone,Debug,PartialEq)]
pub struct Arena {pub phase:Phase,pub generation:u32,pub requested_at:Instant,pub map:Option<MapSpec>,pub pose:Option<Pose>,
    pub input:Input,pub worker_seq:u32,pub native_tick:u32,pub created:Option<Instant>,pub last_request:Option<Instant>,
    pub pending:bool,pub correction_acks:u16,pub telemetry:u32,pub commands:u32,pub aim:u32,pub return_mask:u8,pub queue_info_requests:u8}
impl Arena {
    pub fn new(now:Instant)->Self{Self{phase:Phase::Idle,generation:0,requested_at:now,map:None,pose:None,input:Input::STOP,
        worker_seq:0,native_tick:1000,created:None,last_request:None,pending:false,correction_acks:0,telemetry:0,commands:0,aim:0,return_mask:0,queue_info_requests:0}}
    pub fn join(&mut self,now:Instant)->io::Result<()>{
        if self.phase!=Phase::Idle || self.generation>=MAX_ARENAS || now<self.requested_at{return Err(bad());}
        let generation=self.generation+1;*self=Self::new(now);self.generation=generation;self.phase=Phase::Queued;Ok(())
    }
    pub fn due(&self,now:Instant)->io::Result<bool>{
        if self.phase!=Phase::Driving{return Ok(false);}
        let created=self.created.ok_or_else(bad)?;
        if now<created || now.duration_since(created)>=Duration::from_secs(WORLD_SECONDS as u64){return Err(bad());}
        if self.correction_acks==0 || self.pending{return Ok(false);}
        if let Some(last)=self.last_request {if now<last || now.duration_since(last)>crate::map_drive_worker091::MAX_LAG{return Err(bad());}
            // A delayed response may publish in a later native bucket than
            // its dispatch. Do not request a quick successor in that already
            // published bucket. No future tick, reply dropping or catch-up.
            Ok(now.duration_since(last)>=crate::map_drive_worker091::STEP
                && 1000+(now.duration_since(created).as_millis()/100) as u32>self.native_tick)
        }else{Ok(now.duration_since(created)>=crate::map_drive_worker091::STEP)}
    }
}

#[cfg(test)]mod tests{
    use super::*;
    // Ride03 packet1100 / reliable6, stripped only of its session token:
    // SHA256 f212fc5103b2b4ab9983900c8faed8f3077330c0544997c051c0b9e9e0d6db1c.
    const QUEUE_INFO:[u8;23]=[0x8e,20,0,202,0,246,1,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0];
    #[test]fn queue_info_actual_request_has_exact_type_and_no_callback_id(){
        assert_eq!(account_command(&QUEUE_INFO).unwrap(),Some(AccountCommand::QueueInfo));
        for i in 0..QUEUE_INFO.len(){let mut bad=QUEUE_INFO;bad[i]^=128;
            assert_ne!(account_command(&bad).ok().flatten(),Some(AccountCommand::QueueInfo));}
        for n in 0..QUEUE_INFO.len(){assert_ne!(account_command(&QUEUE_INFO[..n]).ok().flatten(),Some(AccountCommand::QueueInfo));}
        let mut other=QUEUE_INFO;other[7]=2;assert!(account_command(&other).is_err());
    }
    #[test]fn queue_info_original_nullable_classes_layout_is_one_real_light_tank(){
        let b=own_queue_info();assert_eq!(b.len(),27);assert_eq!(&b[..5],&[0x13,0x55,24,1,5]);
        assert_eq!(b[2] as usize,b.len()-3);
        let classes:Vec<u32>=b[5..25].chunks_exact(4).map(|x|u32::from_le_bytes(x.try_into().unwrap())).collect();
        assert_eq!(classes,vec![1,0,0,0,0]);assert_eq!(&b[25..],&[0,0]);
    }
    #[test]fn late_queue_info_accepts_only_one_poll_and_optional_native_enable(){
        assert_eq!(late_queue_info(&QUEUE_INFO).unwrap(),Some(false));
        let mut b=QUEUE_INFO.to_vec();b.push(9);assert_eq!(late_queue_info(&b).unwrap(),Some(true));
        for suffix in [vec![0],vec![8],vec![9,9],QUEUE_INFO.to_vec(),vec![9,0xee]]{
            let mut bad=QUEUE_INFO.to_vec();bad.extend(suffix);assert!(late_queue_info(&bad).is_err());}
        for n in 7..QUEUE_INFO.len(){assert!(late_queue_info(&QUEUE_INFO[..n]).is_err());}
        assert_eq!(late_queue_info(&[9]).unwrap(),None);
    }
    fn pose()->Pose{Pose{position:[1.,20.,3.],direction:[0.5,0.1,-0.1],speed:-2.,rspeed:0.3,contacts:6,linear_velocity:[0.;3],angular_velocity:[0.;3],wheel_contact_masks:[63;6]}}
    fn actual_seed_and_maps()->(vehicle::VehicleSeed,Vec<MapSpec>){
        let local=std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
        let identity=crate::identity091::Profile{account_id:vehicle::PRIMARY_ACCOUNT.to_owned(),database_id:1,name:vehicle::PRIMARY_NAME.to_owned(),
            fixture_dir:local.join("server/fixtures").join(vehicle::PRIMARY_ACCOUNT).join("r4-catalog3")};
        let fixture=crate::hangar091::Fixtures::load_interactive(&identity.fixture_dir).unwrap();
        let seed=vehicle::load(&identity,fixture.state_sha256()).unwrap();
        let pool=crate::map_drive_worker091::Pool::load(&local,&local.join("server/map-drive/pool.json")).unwrap();
        (seed,pool.maps)
    }
    fn float_at(b:&[u8],at:usize)->f32{f32::from_le_bytes(b[at..at+4].try_into().unwrap())}
    fn angle_cases()->[[f32;3];4]{[[std::f32::consts::FRAC_PI_2,0.,0.],[0.,0.3,0.],[0.,0.,-0.4],[0.5,0.1,-0.1]]}
    #[test]fn general_packet_literals_fixed32_signed_speed_and_tick_rollover(){
        let p=pose();let b=publication(1024,&p).unwrap();assert_eq!(b.len(),65);assert_eq!(&b[..7],&[13,0,21,3,0,16,9]);
        assert_eq!(&b[31..33],&[19,74]);assert_eq!(&b[7..19],&b[33..45]);
        assert_eq!(&b[19..23],&b[53..57]);assert_eq!(&b[23..27],&b[49..53]);assert_eq!(&b[27..31],&b[45..49]);
        assert_eq!(&b[57..61],&(-2f32).to_le_bytes());
        assert_eq!(binding(2,&p).unwrap().len(),122);assert!(publication(1000,&p).is_err());
        for axis in 0..3{let mut bad=pose();bad.position[axis]=f32::NAN;assert!(publication(1001,&bad).is_err());}
    }
    #[test]fn native_cell_rpy_basis_reaches_named_engine_yaw_pitch_roll(){
        let (seed,maps)=actual_seed_and_maps();
        for map in maps {for direction in angle_cases(){let mut p=pose();p.direction=direction;
            let b=announcement(&seed,&map,1,&p).unwrap();assert_eq!(&b[..3],&[6,43,0]);
            // d6daf3 raw read -> d6db5e..81 reverse -> 5c7c20 scalar forwarding
            // -> 5cfa80 writes Entity+28/+2c/+30 (original named getters).
            assert_eq!([float_at(&b,35),float_at(&b,31),float_at(&b,27)],direction);
            assert_eq!([float_at(&b,11),float_at(&b,15),float_at(&b,19)],p.position);
            assert_eq!(&b[39..46],&[1,3,0,16,9,0,0]);
        }}
    }
    #[test]fn create_detailed_ypr_basis_is_not_native_direction3d(){
        let (seed,_)=actual_seed_and_maps();let frozen=vehicle::create_requested_vehicle(&seed).unwrap();
        for direction in angle_cases(){let mut p=pose();p.direction=direction;
            let b=create_vehicle(&seed,&p).unwrap();assert_eq!(b.len(),97);
            // d6e068/76/84 read independent yaw/pitch/roll scalars; the call
            // at d6e0d1 preserves their order (unlike createCellPlayer).
            assert_eq!([float_at(&b,22),float_at(&b,26),float_at(&b,30)],direction);
            assert_eq!([float_at(&b,10),float_at(&b,14),float_at(&b,18)],p.position);
            assert_eq!(&b[..10],&frozen[..10]);assert_eq!(&b[34..],&frozen[34..]);
        }
    }
    #[test]fn publication_native_rpy_and_python_ypr_preserve_separate_basis_contracts(){
        for direction in angle_cases(){let mut p=pose();p.direction=direction;
            let b=publication(1024,&p).unwrap();
            // d6e4f2..515 -> EntityManager5c8b10 reconstructs wire[2,1,0].
            assert_eq!([float_at(&b,27),float_at(&b,23),float_at(&b,19)],direction);
            // Original Avatar1445 passes VECTOR3 unchanged to setRotateYPR89.
            assert_eq!([float_at(&b,45),float_at(&b,49),float_at(&b,53)],direction);
            let bind=binding(1,&p).unwrap();assert_eq!(&bind[88..90],&[0x13,0x4a]);
            assert_eq!([float_at(&bind,102),float_at(&bind,106),float_at(&bind,110)],direction);
            // forcedPosition attaches Avatar with zero *relative* angles.
            assert_eq!(&bind[76..88],&[0;12]);
        }
    }
    #[test]fn ride05_nonzero_angles_do_not_substitute_worker_roll_for_native_yaw(){
        // Closed Ride05 original callback474 and native advance27: actual
        // heading1.017363109 followed worker roll, rather than yaw -2.4003124.
        // Source: map-drive/gui/ride05-native-review-02/angle-correlation.json.
        let mut p=pose();p.direction=[-2.4003124237060547,-0.31348180770874023,1.0173630714416504];
        p.position=[-41.62068557739258,19.922147750854492,-482.49639892578125];
        let b=publication(1250,&p).unwrap();
        assert_eq!(float_at(&b,27).to_bits(),p.direction[0].to_bits());
        assert_eq!(float_at(&b,19).to_bits(),p.direction[2].to_bits());
        assert_ne!(float_at(&b,27).to_bits(),p.direction[2].to_bits());
        assert_eq!(&b[7..19],&b[33..45]);
        assert_eq!([float_at(&b,45),float_at(&b,49),float_at(&b,53)],p.direction);
    }
    #[test]fn orientation_fix_preserves_zero_angles_and_rejects_invalid_pose_everywhere(){
        let (seed,maps)=actual_seed_and_maps();let mut p=pose();p.direction=[0.;3];
        let b=publication(1001,&p).unwrap();assert_eq!(&b[7..31],&b[33..57]);
        for v in [f32::NAN,f32::INFINITY,f32::NEG_INFINITY,3.2,-3.2]{for axis in 0..3{
            let mut invalid=p.clone();invalid.direction[axis]=v;
            assert!(announcement(&seed,&maps[0],1,&invalid).is_err());assert!(create_vehicle(&seed,&invalid).is_err());
            assert!(publication(1001,&invalid).is_err());assert!(binding(1,&invalid).is_err());
        }}
        assert!(publication(1000,&p).is_err());assert!(publication(1001+WORLD_SECONDS*10,&p).is_err());
    }
    #[test]fn flags_do_not_confuse_cruise_with_brake_or_reverse_turn(){
        for (f,t,s) in [(0,0,0),(1,1,0),(2,-1,0),(4,0,-1),(8,0,1),(5,1,-1),(9,1,1),(6,-1,-1),(10,-1,1)]{
            assert_eq!(driving_input(f).unwrap(),Input{throttle:t,steer:s,brake:f==0});}
        for f in 0..=255{if ![0,1,2,4,8,5,9,6,10].contains(&f){assert!(driving_input(f).is_err());}}
        for f in [3,12,15,16,17,32,33,255]{assert_eq!(methods(&[0x8a,1,0,f]).unwrap(),vec![Method::UnsupportedMove(f)]);}
        // Framing remains strict; adding an unsupported byte is not a means of
        // hiding a corrupt suffix or of treating arbitrary bytes as commands.
        assert!(methods(&[0x8a,1,0,17,7]).is_err());assert!(methods(&[0x8a,2,0,17,0]).is_err());
    }
    #[test]fn captured_sniper_camera_preferences_have_exact_bounded_native_contract(){
        // Actual token-stripped packet1620 (SHA25664d7f147...d49df83)
        // and packet1670 from closed run20261006T051849-cbba00.
        let enter=[0x8d,5,0,2,0,0,0,0];let leave=[0x8d,5,0,2,1,0,0,0];
        assert_eq!(methods(&enter).unwrap(),vec![Method::UnsupportedCameraAutorotation(false)]);
        assert_eq!(methods(&leave).unwrap(),vec![Method::UnsupportedCameraAutorotation(true)]);
        let compound=[enter.as_slice(),&[0x8a,1,0,2]].concat();
        assert_eq!(methods(&compound).unwrap(),vec![Method::UnsupportedCameraAutorotation(false),Method::Move(2,Input{throttle:-1,steer:0,brake:false})]);
        // Compound is a parser unit, not an observed12B camera packet.
        for setting in 0..=255{if setting!=2{let mut b=enter;b[3]=setting;assert!(methods(&b).is_err());}}
        for value in [-1,2,i32::MIN,i32::MAX]{let mut b=enter;b[4..].copy_from_slice(&value.to_le_bytes());assert!(methods(&b).is_err());}
        for n in 0..enter.len(){assert!(methods(&enter[..n]).is_err());}
        for len in [0u16,1,4,6,255,65535]{let mut b=enter;b[1..3].copy_from_slice(&len.to_le_bytes());assert!(methods(&b).is_err());}
        for tail in [&[7][..],&[0x8d,5,0,16,1,0,0,0],&[0x8a,2,0,1,0]]{
            assert!(methods(&[enter.as_slice(),tail].concat()).is_err());}
        assert!(methods(&enter.repeat(17)).is_err());assert_eq!(methods(&enter.repeat(16)).unwrap().len(),16);
    }
    #[test]fn leave_nullable_fixed_dictionary_and_late_tail_are_whole_validated(){
        assert_eq!(methods(&[0x8a,1,0,0,0x99,1,0,0]).unwrap(),vec![Method::Move(0,Input::STOP),Method::Leave]);
        let mut stats=vec![0x99,68,0,1];stats.extend([0;67]);assert_eq!(methods(&stats).unwrap(),vec![Method::Leave]);
        for n in 1..stats.len(){assert!(methods(&stats[..n]).is_err());}
        for bad in [vec![0x99,1,0,2],vec![0x99,1,0,0,6],vec![0x8a,1,0,1,7],vec![0x8a,1,0,1,0x99,0,0]]{assert!(methods(&bad).is_err());}
    }
    #[test]fn queue_native_no_response_own_vehicle_random_only(){
        let mut b=vec![0x8e,20,0,202,0];b.extend(700i16.to_le_bytes());b.extend(1i64.to_le_bytes());b.extend(7i32.to_le_bytes());b.extend(0i32.to_le_bytes());
        assert_eq!(account_command(&b).unwrap(),Some(AccountCommand::Join));
        for offset in [3,7,8,15,19]{let mut wrong=b.clone();wrong[offset]^=128;assert!(account_command(&wrong).is_err());}
    }
    #[test]fn generation_cadence_and_caps_never_reset_in_progress(){
        let now=Instant::now();let mut a=Arena::new(now);a.join(now).unwrap();assert!(a.join(now).is_err());
        a.phase=Phase::Driving;a.created=Some(now);a.correction_acks=1;a.last_request=Some(now);
        assert!(!a.due(now+Duration::from_millis(99)).unwrap());assert!(a.due(now+Duration::from_millis(100)).unwrap());
        assert!(a.due(now+Duration::from_millis(501)).is_err());a.pending=true;assert!(!a.due(now+Duration::from_secs(1)).unwrap());
        a.phase=Phase::Idle;a.generation=MAX_ARENAS;assert!(a.join(now).is_err());
    }

    #[test]fn entity_only_policy_matches_delivered_ride11_prefix_without_repeated_python_method(){
        let p=Pose{position:[f32::from_bits(0xc1700132),f32::from_bits(0x4145c8c0),f32::from_bits(0x4120059a)],direction:[f32::from_bits(0x39c10b79),f32::from_bits(0x3ac6104a),f32::from_bits(0xbca57ff1)],speed:f32::from_bits(0x3834cec9),rspeed:f32::from_bits(0xb651254a),contacts:6,linear_velocity:[0.;3],angular_velocity:[0.;3],wheel_contact_masks:[63;6]};let old:[u8;65]=[0x0d,0xe9,0x15,0x03,0x00,0x10,0x09,0x32,0x01,0x70,0xc1,0xc0,0xc8,0x45,0x41,0x9a,0x05,0x20,0x41,0xf1,0x7f,0xa5,0xbc,0x4a,0x10,0xc6,0x3a,0x79,0x0b,0xc1,0x39,0x13,0x4a,0x32,0x01,0x70,0xc1,0xc0,0xc8,0x45,0x41,0x9a,0x05,0x20,0x41,0x79,0x0b,0xc1,0x39,0x4a,0x10,0xc6,0x3a,0xf1,0x7f,0xa5,0xbc,0xc9,0xce,0x34,0x38,0x4a,0x25,0x51,0xb6];
        assert_eq!(publication(1001,&p).unwrap(),old);
        let next=publication_entity_only(1001,&p).unwrap();
        assert_eq!(next.len(),31);assert_eq!(next,&old[..31]);
        assert_eq!(PUBLICATION_POLICY,"initial_own_callback_then_entity_only_v1");
    }
    #[test]fn initial_binding_remains_exact_delivered_ride11_122_bytes(){
        let p=Pose{position:[f32::from_bits(0xc1700135),f32::from_bits(0x4145c8c0),f32::from_bits(0x41200594)],direction:[f32::from_bits(0x39c10b79),f32::from_bits(0x3ac6104a),f32::from_bits(0xbca57ff1)],speed:f32::from_bits(0x382be150),rspeed:f32::from_bits(0xb6533d09),contacts:6,linear_velocity:[0.;3],angular_velocity:[0.;3],wheel_contact_masks:[63;6]};let expected:[u8;122]=[0x02,0x0a,0x03,0xe8,0x03,0x00,0x00,0x13,0x58,0x0a,0x07,0x08,0x80,0x02,0x4a,0x03,0x00,0x10,0x09,0x2e,0x13,0x58,0x1c,0x03,0x1a,0x80,0x02,0x28,0x4b,0x03,0x47,0x40,0xac,0xe8,0x00,0x00,0x00,0x00,0x00,0x47,0x40,0xac,0x20,0x00,0x00,0x00,0x00,0x00,0x4e,0x74,0x2e,0x14,0x02,0x00,0x10,0x09,0x01,0x00,0x00,0x00,0x03,0x00,0x10,0x09,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x13,0x4a,0x35,0x01,0x70,0xc1,0xc0,0xc8,0x45,0x41,0x94,0x05,0x20,0x41,0x79,0x0b,0xc1,0x39,0x4a,0x10,0xc6,0x3a,0xf1,0x7f,0xa5,0xbc,0x50,0xe1,0x2b,0x38,0x09,0x3d,0x53,0xb6];
        let actual=binding(1,&p).unwrap();assert_eq!(actual,expected);
        assert_eq!(&actual[51..64],&[0x14,2,0,16,9,1,0,0,0,3,0,16,9]);
        assert_eq!(&actual[64..88],&[0;24]);assert_eq!(&actual[88..90],&[0x13,0x4a]);
    }
    #[test]fn entity_only_basis_rollover_and_same_timestamp_are_unmodified(){
        for direction in angle_cases(){let mut p=pose();p.direction=direction;
            for tick in [1001u32,1023,1024,1025,1250,1000+WORLD_SECONDS*10]{
                let b=publication_entity_only(tick,&p).unwrap();assert_eq!(&b[..7],&[0x0d,tick as u8,0x15,3,0,16,9]);
                assert_eq!(b.len(),31);assert_eq!([float_at(&b,7),float_at(&b,11),float_at(&b,15)],p.position);
                assert_eq!([float_at(&b,27),float_at(&b,23),float_at(&b,19)],direction);
                assert_eq!(b,&publication(tick,&p).unwrap()[..31]);
            }
        }
    }
    #[test]fn entity_only_keeps_all_authoritative_pose_and_tick_bounds(){
        let p=pose();for tick in [0,1000,1001+WORLD_SECONDS*10,u32::MAX]{assert!(publication_entity_only(tick,&p).is_err());}
        for invalid in [f32::NAN,f32::INFINITY,f32::NEG_INFINITY]{
            for axis in 0..3{let mut p=pose();p.position[axis]=invalid;assert!(publication_entity_only(1001,&p).is_err());
                let mut p=pose();p.direction[axis]=invalid;assert!(publication_entity_only(1001,&p).is_err());}
            let mut p=pose();p.speed=invalid;assert!(publication_entity_only(1001,&p).is_err());
            let mut p=pose();p.rspeed=invalid;assert!(publication_entity_only(1001,&p).is_err());
        }
        let mut p=pose();p.speed=25.01;assert!(publication_entity_only(1001,&p).is_err());
        let mut p=pose();p.rspeed=-20.01;assert!(publication_entity_only(1001,&p).is_err());
        let probe=crate::map_drive091::publication_body(OWN,1001,crate::arena_movement091::POSITION,0.0).unwrap();
        assert_eq!(probe.len(),65);assert_eq!(&probe[31..33],&[0x13,0x4a]);
    }
    // Ride17 async scheduling counterexample. Times are synthetic same-origin
    // monotonic instants; actual247 poll timestamp was not captured.
    #[test]fn ride17_dispatch_waits_for_new_publication_clock(){
        let t=Instant::now();let mut a=Arena::new(t);
        a.phase=Phase::Driving;a.created=Some(t);a.correction_acks=1;
        a.worker_seq=246;a.native_tick=1252;a.last_request=Some(t+Duration::from_millis(25170));
        let next=t+Duration::from_millis(25270);
        assert!(next.duration_since(a.last_request.unwrap())>=crate::map_drive_worker091::STEP);
        assert_eq!(1000+(next.duration_since(t).as_millis()/100) as u32,1252);
        // Old request-spacing-only predicate is true, but a quick reply25275
        // still has1252 and was fatally rejected after worker.poll consumed it.
        assert!(!a.due(next).unwrap());
        assert!(a.due(t+Duration::from_millis(25300)).unwrap());
        a.pending=true;assert!(!a.due(t+Duration::from_millis(25310)).unwrap());
        a.pending=false;assert!(a.due(t+Duration::from_millis(25671)).is_err());
    }
}
