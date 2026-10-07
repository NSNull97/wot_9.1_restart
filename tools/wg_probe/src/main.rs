use std::{env, fs, io, io::Seek, sync::Arc};
use rsa::{pkcs8::DecodePrivateKey, RsaPrivateKey};
use wgtk::app::login::{App, Event, element::LoginError};
#[path = "../../../server/gateway/src/protocol/login.rs"]
mod login091;
#[path = "../../../server/gateway/src/protocol/redirect.rs"]
mod redirect091;
#[path = "../../../server/gateway/src/protocol/baseapp.rs"]
mod baseapp091;
#[path = "../../../server/gateway/src/protocol/channel.rs"]
mod channel091;
#[path = "../../../server/gateway/src/protocol/reliable.rs"]
mod reliable091;
#[path = "../../../server/gateway/src/protocol/transport.rs"]
mod transport091;
#[path = "../../../server/gateway/src/session.rs"]
mod gateway091;
#[path = "../../../server/gateway/src/account/model.rs"]
mod account091;
#[path = "../../../server/gateway/src/account/hangar.rs"]
mod hangar091;
#[path = "../../../server/gateway/src/account/identity.rs"]
mod identity091;
#[path = "../../../server/gateway/src/protocol/capture.rs"]
mod capture091;
#[path = "../../../server/gateway/src/arena/codec.rs"]
mod arena091;
#[path = "../../../server/gateway/src/arena/control.rs"]
mod arena_control091;
#[path = "../../../server/gateway/src/arena/vehicle.rs"]
mod arena_vehicle091;
#[path = "../../../server/gateway/src/arena/ready.rs"]
mod arena_ready091;
#[path = "../../../server/gateway/src/arena/movement.rs"]
mod arena_movement091;
#[path = "../../../server/gateway/src/drive/model.rs"]
mod map_drive091;
#[path = "../../../server/gateway/src/drive/worker.rs"]
mod map_drive_worker091;
#[path = "../../../server/gateway/src/drive/world.rs"]
mod map_drive_world091;
#[path = "../../../server/gateway/src/drive/service.rs"]
mod map_drive_service091;
#[path = "../../../server/gateway/src/battle/mod.rs"]
mod battle091;

fn map_drive_capture_args(args:&[String])->io::Result<(Option<&str>,capture091::Profile)> {
    if args.get(1).map(String::as_str)!=Some("legacy091-map-drive") || !(6..=8).contains(&args.len()) {
        return Err(io::Error::new(io::ErrorKind::InvalidInput,"map-drive expects key digest gateway pool [capture [map-drive-phase2-v1]]"));
    }
    let capture=args.get(6).map(String::as_str);
    Ok((capture,capture091::Profile::for_map_drive(capture,args.get(7).map(String::as_str))?))
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    if args.get(1).map(String::as_str)==Some("legacy091-map-drive") {
        let (capture,profile)=map_drive_capture_args(&args)?;
        return gateway091::serve_map_drive(&args[2],&args[3],&args[4],&args[5],capture,profile);
    }
    if args.len()==7 && args[1]=="legacy091-arena-base-probe" {
        return gateway091::serve_arena_base_probe(&args[2],&args[3],&args[4],&args[5],&args[6]);
    }
    if args.len()==7 && args[1]=="legacy091-arena-space-probe" {
        return gateway091::serve_arena_space_probe(&args[2],&args[3],&args[4],&args[5],&args[6]);
    }
    if args.len()==7 && args[1]=="legacy091-arena-vehicle-probe" {
        return gateway091::serve_arena_vehicle_probe(&args[2],&args[3],&args[4],&args[5],&args[6]);
    }
    if args.len()==7 && args[1]=="legacy091-arena-ready-probe" {
        return gateway091::serve_arena_ready_probe(&args[2],&args[3],&args[4],&args[5],&args[6]);
    }
    if args.len()==7 && args[1]=="legacy091-arena-movement-probe" {
        return gateway091::serve_arena_movement_probe(&args[2],&args[3],&args[4],&args[5],&args[6]);
    }
    if args.len()==7 && args[1]=="legacy091-map-drive-probe" {
        return gateway091::serve_map_drive_probe(&args[2],&args[3],&args[4],&args[5],&args[6]);
    }
    if (args.len()==5 || args.len()==6) && args[1]=="legacy091-interactive" {
        return gateway091::serve_interactive(&args[2],&args[3],&args[4],args.get(5).map(String::as_str));
    }
    if args.len()==5 && args[1]=="legacy091-hangar" {
        return gateway091::serve_hangar(&args[2],&args[3],&args[4]);
    }
    if args.len()==4 && args[1]=="legacy091-account-ready" {
        return gateway091::serve_account_ready(&args[2],&args[3]);
    }
    if args.len()==4 && args[1]=="legacy091-account" {
        return gateway091::serve_account(&args[2],&args[3]);
    }
    if args.len()==4 && args[1]=="legacy091-gateway" {
        return gateway091::serve(&args[2],&args[3]);
    }
    if args.len()==3 && args[1]=="legacy091-gap" {
        return baseapp091::serve_mode(&args[2],channel091::AckMode::GapProbe);
    }
    if args.len()==3 && args[1]=="legacy091-server-reliable" {
        return baseapp091::serve_mode(&args[2],channel091::AckMode::ServerFirst);
    }
    if args.len()==3 && args[1]=="legacy091-channel-ack" {
        return baseapp091::serve_mode(&args[2],channel091::AckMode::FirstFrame);
    }
    if args.len()==3 && args[1]=="legacy091-channel-stale" {
        return baseapp091::serve_mode(&args[2],channel091::AckMode::StaleControl);
    }
    if args.len() == 3 && args[1] == "legacy091" {
        return login091::serve(&args[2]);
    }
    if args.len() == 3 && args[1] == "legacy091-redirect" {
        return redirect091::serve(&args[2]);
    }
    if args.len() == 3 && args[1] == "legacy091-baseapp" {
        return baseapp091::serve(&args[2]);
    }
    if args.len() == 4 && args[1] == "legacy091-decode" {
        return login091::offline(&args[2], &args[3]);
    }
    if args.len() == 3 && args[1] == "geometry" {
        use wgtk::model::primitive::{PrimitiveReader, Vertices};
        let mut reader = PrimitiveReader::open(fs::File::open(&args[2])?)?;
        let meta = reader.get_section_meta("vertices").ok_or("no vertices")?;
        let (offset, length) = (meta.off, meta.len);
        let vertices = reader.read_section::<Vertices>("vertices").ok_or("no vertices")??;
        let consumed = reader.into_inner().stream_position()? as usize - offset;
        println!("GEOMETRY vertices={} section_bytes={} consumed_bytes={} trailing_bytes={}",
            vertices.vertices.len(), length, consumed, length.saturating_sub(consumed));
        if consumed != length {
            return Err("FAIL: toolkit vertex layout does not consume the real 0.9.1 section".into());
        }
        return Ok(());
    }
    if args.len() != 2 {
        return Err("usage: p01-wg-probe <local-test-private-key.pem>".into());
    }
    let pem = fs::read_to_string(&args[1])?;
    if pem.len() > 16384 {
        return Err("key file too large".into());
    }
    let key = RsaPrivateKey::from_pkcs8_pem(&pem)?;
    let mut app = App::new("127.0.0.1:20015".parse()?)?;
    app.set_encryption(Arc::new(key));
    println!("BOUND {} toolkit=5b879f0b960ccb4a3b799ede952256e253ef74cb", app.addr()?);
    // The parent owns the bounded deadline and packet/size limits. No login
    // success, entity creation, forwarding outside loopback, or pickle decoding.
    for _ in 0..32 {
        match app.poll() {
            Event::Login(event) => {
                println!("LOGIN_DECODED protocol={} username_bytes={} password_bytes={} session_key_bytes={} digest_present={}",
                    event.request.protocol, event.request.username.len(), event.request.password.len(),
                    event.request.blowfish_key.len(), event.request.digest.is_some());
                if !app.answer_login_error(event.addr, LoginError::ServerNotReady,
                    "P01_LOCAL_PROBE: no game service".to_owned()) {
                    return Err("could not queue diagnostic response".into());
                }
                println!("ERROR_RESPONSE_QUEUED code=74");
            }
            Event::Ping(event) => println!("PING_REPLY {}", event.addr),
            Event::IoError(event) => {
                eprintln!("DECODE_ERROR kind={:?} message={}", event.error.kind(), event.error);
                return Err(io::Error::new(io::ErrorKind::InvalidData, "toolkit native decoding failed").into());
            }
            Event::Challenge(_) => return Err("unexpected challenge in this narrow probe".into()),
        }
    }
    Err("event limit reached".into())
}

#[cfg(test)]mod capture_cli_tests {
    use super::*;
    fn args(extra:&[&str])->Vec<String>{[vec!["exe","legacy091-map-drive","key","digest","gateway","pool"],extra.to_vec()].concat().into_iter().map(str::to_owned).collect()}
    #[test]fn old_map_drive_argv_and_capture_defaults_remain_exact(){
        let a=args(&[]);assert_eq!(map_drive_capture_args(&a).unwrap(),(None,capture091::Profile::Ordinary));
        let a=args(&["capture"]);assert_eq!(map_drive_capture_args(&a).unwrap(),(Some("capture"),capture091::Profile::Ordinary));
    }
    #[test]fn explicit_map_drive_capture_profile_has_one_unambiguous_positional_shape(){
        let a=args(&["capture","map-drive-phase2-v1"]);assert_eq!(map_drive_capture_args(&a).unwrap(),(Some("capture"),capture091::Profile::MapDrivePhase2V1));
        for tail in [vec!["capture","unknown"],vec!["capture","map-drive-phase2-v1","extra"],vec!["","map-drive-phase2-v1"]]{assert!(map_drive_capture_args(&args(&tail)).is_err());}
        let mut a=args(&[]);a.pop();assert!(map_drive_capture_args(&a).is_err());
    }
    #[test]fn no_other_legacy_mode_can_select_map_drive_capture_profile(){
        for mode in ["legacy091-interactive","legacy091-hangar","legacy091-map-drive-probe","legacy091-arena-ready-probe"]{
            let mut a=args(&["capture","map-drive-phase2-v1"]);a[1]=mode.to_owned();assert!(map_drive_capture_args(&a).is_err());
        }
    }
}
