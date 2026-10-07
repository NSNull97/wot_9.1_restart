//! Ordinary server entry point. Research commands remain in tools/wg_probe.
use std::{env, io};

#[path = "protocol/login.rs"]
mod login091;
#[path = "protocol/redirect.rs"]
mod redirect091;
#[path = "protocol/baseapp.rs"]
mod baseapp091;
#[path = "protocol/channel.rs"]
mod channel091;
#[path = "protocol/reliable.rs"]
mod reliable091;
#[path = "protocol/transport.rs"]
mod transport091;
#[path = "session.rs"]
mod gateway091;
#[path = "account/model.rs"]
mod account091;
#[path = "account/hangar.rs"]
mod hangar091;
#[path = "account/identity.rs"]
mod identity091;
#[path = "protocol/capture.rs"]
mod capture091;
#[path = "arena/codec.rs"]
mod arena091;
#[path = "arena/control.rs"]
mod arena_control091;
#[path = "arena/vehicle.rs"]
mod arena_vehicle091;
#[path = "arena/ready.rs"]
mod arena_ready091;
#[path = "arena/movement.rs"]
mod arena_movement091;
#[path = "drive/model.rs"]
mod map_drive091;
#[path = "drive/worker.rs"]
mod map_drive_worker091;
#[path = "drive/world.rs"]
mod map_drive_world091;
#[path = "drive/service.rs"]
mod map_drive_service091;
#[path = "battle/mod.rs"]
mod battle091;

#[derive(Debug, PartialEq)]
enum Command<'a> {
    Interactive { key: &'a str, digest: &'a str, gateway: &'a str, capture: Option<&'a str> },
    MapDrive { key: &'a str, digest: &'a str, gateway: &'a str, pool: &'a str,
               capture: Option<&'a str>, profile: capture091::Profile },
}

fn command(args: &[String]) -> io::Result<Command<'_>> {
    let invalid = || io::Error::new(io::ErrorKind::InvalidInput,
        "usage: sr-gateway legacy091-interactive KEY DIGEST GATEWAY [CAPTURE] | legacy091-map-drive KEY DIGEST GATEWAY POOL [CAPTURE [map-drive-phase2-v1]]");
    match args.get(1).map(String::as_str) {
        Some("legacy091-interactive") if matches!(args.len(), 5 | 6) => Ok(Command::Interactive {
            key: &args[2], digest: &args[3], gateway: &args[4], capture: args.get(5).map(String::as_str),
        }),
        Some("legacy091-map-drive") if (6..=8).contains(&args.len()) => {
            let capture = args.get(6).map(String::as_str);
            let profile = capture091::Profile::for_map_drive(capture, args.get(7).map(String::as_str))?;
            Ok(Command::MapDrive { key: &args[2], digest: &args[3], gateway: &args[4], pool: &args[5], capture, profile })
        }
        _ => Err(invalid()),
    }
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = env::args().collect();
    match command(&args)? {
        Command::Interactive { key, digest, gateway, capture } => gateway091::serve_interactive(key, digest, gateway, capture),
        Command::MapDrive { key, digest, gateway, pool, capture, profile } => gateway091::serve_map_drive(key, digest, gateway, pool, capture, profile),
    }
}

#[cfg(test)]
mod cli_tests {
    use super::*;
    fn args(values: &[&str]) -> Vec<String> { values.iter().map(|s| (*s).into()).collect() }

    #[test]
    fn interactive_has_exact_ordinary_arguments_and_optional_capture() {
        for capture in [None, Some("capture")] {
            let mut values = vec!["exe", "legacy091-interactive", "key", "digest", "gateway"];
            if let Some(value) = capture { values.push(value); }
            assert_eq!(command(&args(&values)).unwrap(), Command::Interactive { key: "key", digest: "digest", gateway: "gateway", capture });
        }
    }

    #[test]
    fn map_drive_preserves_the_explicit_capture_profile_contract() {
        for (tail, capture, profile) in [
            (vec![], None, capture091::Profile::Ordinary),
            (vec!["capture"], Some("capture"), capture091::Profile::Ordinary),
            (vec!["capture", "map-drive-phase2-v1"], Some("capture"), capture091::Profile::MapDrivePhase2V1),
        ] {
            let mut values = vec!["exe", "legacy091-map-drive", "key", "digest", "gateway", "pool"];
            values.extend(tail);
            assert_eq!(command(&args(&values)).unwrap(), Command::MapDrive {
                key: "key", digest: "digest", gateway: "gateway", pool: "pool", capture, profile });
        }
    }

    #[test]
    fn diagnostic_commands_and_the_old_implicit_probe_cannot_start_here() {
        for mode in ["legacy091", "geometry", "legacy091-hangar", "legacy091-account", "legacy091-gateway",
                     "legacy091-map-drive-probe", "legacy091-arena-base-probe", "legacy091-arena-space-probe",
                     "legacy091-arena-vehicle-probe", "legacy091-arena-ready-probe", "legacy091-arena-movement-probe"] {
            assert!(command(&args(&["exe", mode, "key", "digest", "gateway", "capture", "trigger"])).is_err());
        }
        assert!(command(&args(&["exe", "key"])).is_err());
        assert!(command(&args(&["exe"])).is_err());
    }

    #[test]
    fn bad_arity_unknown_profiles_and_profile_without_capture_fail_before_dispatch() {
        for values in [
            vec!["exe", "legacy091-interactive", "key", "digest"],
            vec!["exe", "legacy091-interactive", "key", "digest", "gateway", "capture", "map-drive-phase2-v1"],
            vec!["exe", "legacy091-map-drive", "key", "digest", "gateway"],
            vec!["exe", "legacy091-map-drive", "key", "digest", "gateway", "pool", "capture", "unknown"],
            vec!["exe", "legacy091-map-drive", "key", "digest", "gateway", "pool", "", "map-drive-phase2-v1"],
            vec!["exe", "legacy091-map-drive", "key", "digest", "gateway", "pool", "capture", "map-drive-phase2-v1", "extra"],
        ] { assert!(command(&args(&values)).is_err()); }
    }
}
