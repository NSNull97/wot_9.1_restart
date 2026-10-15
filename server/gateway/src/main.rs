//! Ordinary server entry point. Research commands remain in tools/wg_probe.
use std::{env, io};
use map_profile091::MapId;
use gateway091::shared::vehicle_profile::VehicleKind;

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
pub(crate) mod gateway091;
#[path = "account/model.rs"]
mod account091;
#[path = "account/hangar.rs"]
mod hangar091;
#[path = "account/ammo_service.rs"]
mod ammo_service091;
#[path = "account/crew_service.rs"]
mod crew_service091;
#[path = "account/crew_transfer.rs"]
mod crew_transfer091;
#[path = "account/crew_progression.rs"]
mod crew_progression091;
#[path = "account/crew_barracks.rs"]
mod crew_barracks091;
#[path = "account/crew_dismissal.rs"]
mod crew_dismissal091;
#[path = "account/research_service.rs"]
mod research_service091;
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
#[path = "drive/map_profile.rs"]
mod map_profile091;
#[path = "drive/worker.rs"]
mod map_drive_worker091;
#[cfg(test)]
#[path = "shared/server_worker_fixtures.rs"]
mod worker_fixtures091;
#[path = "drive/world.rs"]
mod map_drive_world091;
#[path = "drive/service.rs"]
mod map_drive_service091;
#[path = "battle/mod.rs"]
mod battle091;

#[derive(Debug, PartialEq)]
enum Command<'a> {
    Profile13 { key: &'a str, digest: &'a str, gateway: &'a str, templates: &'a str, capture: &'a str },
    SharedLab { key: &'a str, digest: &'a str, gateway: &'a str, capture: &'a str },
    IntegratedLab { key: &'a str, digest: &'a str, gateway: &'a str, pool: &'a str, capture: &'a str, geometry: Option<&'a str>, ap_test_lab: bool, terrain_test_lab: bool, destructible_test_lab: bool, catalog: Option<(&'a str,&'a str)>, map: MapId, vehicle: VehicleKind },
    Interactive { key: &'a str, digest: &'a str, gateway: &'a str, capture: Option<&'a str> },
    MapDrive { key: &'a str, digest: &'a str, gateway: &'a str, pool: &'a str,
               capture: Option<&'a str>, profile: capture091::Profile },
}

fn command(args: &[String]) -> io::Result<Command<'_>> {
    let invalid = || io::Error::new(io::ErrorKind::InvalidInput,
        "usage: sr-gateway legacy091-profile13 KEY DIGEST GATEWAY TEMPLATES CAPTURE | legacy091-interactive KEY DIGEST GATEWAY [CAPTURE] | legacy091-map-drive KEY DIGEST GATEWAY POOL [CAPTURE [map-drive-phase2-v1]] | legacy091-shared-lab KEY DIGEST GATEWAY CAPTURE | legacy091-integrated-lab KEY DIGEST GATEWAY POOL CAPTURE [MESH --ap-test-lab --terrain-test-lab [--destructible-catalog PATH SHA256] [--map MAP_ASSET] [--vehicle-test-lab ms1|is7]]");
    // A single trailing selector preserves every accepted Karelia invocation.
    // Prohorovka is available only on the cumulative AP + terrain path; the
    // catalog is optional for the read-only original native identity oracle.
    // Explicit homogeneous laboratory profile, stripped before the existing
    // trailing map selector. Other modes and duplicate selectors fail closed.
    let (args, vehicle) = if args.get(1).is_some_and(|v| v == "legacy091-integrated-lab")
        && args.len() >= 4 && args[args.len() - 2] == "--vehicle-test-lab" {
        let kind = match args[args.len() - 1].as_str() {
            "ms1" => VehicleKind::Ms1, "is7" => VehicleKind::Is7, _ => return Err(invalid()),
        };
        (&args[..args.len() - 2], kind)
    } else { (args, VehicleKind::Ms1) };
    let (args, map) = if args.get(1).is_some_and(|v| v == "legacy091-integrated-lab")
        && args.len() >= 4 && args[args.len() - 2] == "--map" {
        (&args[..args.len() - 2], MapId::from_asset(&args[args.len() - 1])?)
    } else { (args, MapId::Karelia) };
    match args.get(1).map(String::as_str) {
        Some("legacy091-profile13") if args.len()==7 && args[2..].iter().all(|value|!value.is_empty()&&!value.starts_with("--")) => Ok(Command::Profile13 {
            key:&args[2],digest:&args[3],gateway:&args[4],templates:&args[5],capture:&args[6],
        }),
        Some("legacy091-shared-lab") if args.len() == 6 && !args[5].is_empty() => Ok(Command::SharedLab {
            key: &args[2], digest: &args[3], gateway: &args[4], capture: &args[5],
        }),
        Some("legacy091-integrated-lab") if matches!(args.len(), 7 | 8 | 9 | 10 | 11 | 13) && !args[5].is_empty() && !args[6].is_empty()
            && (vehicle == VehicleKind::Ms1 || map == MapId::Prohorovka && matches!(args.len(), 10 | 13))
            && (map == MapId::Karelia || matches!(args.len(), 10 | 13))
            && args.get(7).is_none_or(|s| !s.is_empty() && !s.starts_with("--"))
            && args.get(8).is_none_or(|s| s == "--ap-test-lab")
            && args.get(9).is_none_or(|s| s == "--terrain-test-lab")
            && (args.len()<=10 || args.len()==11 && args[10]=="--destructible-test-lab"
                || args.len()==13 && args[10]=="--destructible-catalog" && !args[11].is_empty()
                    && args[12].len()==64 && args[12].bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b))) => Ok(Command::IntegratedLab {
            key: &args[2], digest: &args[3], gateway: &args[4], pool: &args[5], capture: &args[6],
            geometry: args.get(7).map(String::as_str),
            ap_test_lab: args.len() >= 9, terrain_test_lab: args.len() >= 10, destructible_test_lab: args.len() == 11, catalog: if args.len()==13{Some((&args[11],&args[12]))}else{None}, map, vehicle,
        }),
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
        Command::Profile13 { key,digest,gateway,templates,capture } => gateway091::shared::serve_profile13(key,digest,gateway,templates,capture),
        Command::SharedLab { key, digest, gateway, capture } => gateway091::serve_shared_lab(key, digest, gateway, capture),
        Command::IntegratedLab { key, digest, gateway, pool, capture, geometry, ap_test_lab, terrain_test_lab, destructible_test_lab, catalog, map, vehicle } => gateway091::serve_integrated_lab_for_vehicle(key, digest, gateway, pool, capture, geometry, ap_test_lab, terrain_test_lab, destructible_test_lab,catalog,map,vehicle),
        Command::Interactive { key, digest, gateway, capture } => gateway091::serve_interactive(key, digest, gateway, capture),
        Command::MapDrive { key, digest, gateway, pool, capture, profile } => gateway091::serve_map_drive(key, digest, gateway, pool, capture, profile),
    }
}

#[cfg(test)]
mod cli_tests {
    use super::*;
    fn args(values: &[&str]) -> Vec<String> { values.iter().map(|s| (*s).into()).collect() }

    #[test]fn profile13_mode_is_explicit_complete_and_does_not_inherit_lab_flags(){
        let base=["exe","legacy091-profile13","key","digest","gateway","templates","capture"];
        assert_eq!(command(&args(&base)).unwrap(),Command::Profile13{key:"key",digest:"digest",gateway:"gateway",templates:"templates",capture:"capture"});
        for length in 0..base.len(){assert!(command(&args(&base[..length])).is_err());}
        for offset in 2..base.len(){let mut wrong=base;wrong[offset]="";assert!(command(&args(&wrong)).is_err());}
        for flag in ["--ap-test-lab","--vehicle-test-lab","--map"]{let mut wrong=args(&base);wrong.push(flag.into());assert!(command(&wrong).is_err());}
    }

    #[test]
    fn shared_lab_is_explicit_and_requires_its_own_capture() {
        assert_eq!(command(&args(&["exe","legacy091-shared-lab","key","digest","config","capture"])).unwrap(),
            Command::SharedLab { key:"key",digest:"digest",gateway:"config",capture:"capture" });
        assert!(command(&args(&["exe","legacy091-shared-lab","key","digest","config"])).is_err());
        assert!(command(&args(&["exe","legacy091-shared-lab","key","digest","config",""])).is_err());
    }

    #[test]
    fn integrated_lab_requires_pool_and_capture() {
        assert_eq!(command(&args(&["exe","legacy091-integrated-lab","key","digest","config","pool","capture"])).unwrap(),
            Command::IntegratedLab { key:"key",digest:"digest",gateway:"config",pool:"pool",capture:"capture",geometry:None,ap_test_lab:false,terrain_test_lab:false,destructible_test_lab:false,catalog:None,map:MapId::Karelia,vehicle:VehicleKind::Ms1 });
        assert_eq!(command(&args(&["exe","legacy091-integrated-lab","key","digest","config","pool","capture","mesh"])).unwrap(),
            Command::IntegratedLab { key:"key",digest:"digest",gateway:"config",pool:"pool",capture:"capture",geometry:Some("mesh"),ap_test_lab:false,terrain_test_lab:false,destructible_test_lab:false,catalog:None,map:MapId::Karelia,vehicle:VehicleKind::Ms1 });
        assert_eq!(command(&args(&["exe","legacy091-integrated-lab","key","digest","config","pool","capture","mesh","--ap-test-lab"])).unwrap(),
            Command::IntegratedLab { key:"key",digest:"digest",gateway:"config",pool:"pool",capture:"capture",geometry:Some("mesh"),ap_test_lab:true,terrain_test_lab:false,destructible_test_lab:false,catalog:None,map:MapId::Karelia,vehicle:VehicleKind::Ms1 });
        assert_eq!(command(&args(&["exe","legacy091-integrated-lab","key","digest","config","pool","capture","mesh","--ap-test-lab","--terrain-test-lab"])).unwrap(),
            Command::IntegratedLab { key:"key",digest:"digest",gateway:"config",pool:"pool",capture:"capture",geometry:Some("mesh"),ap_test_lab:true,terrain_test_lab:true,destructible_test_lab:false,catalog:None,map:MapId::Karelia,vehicle:VehicleKind::Ms1 });
        assert_eq!(command(&args(&["exe","legacy091-integrated-lab","key","digest","config","pool","capture","mesh","--ap-test-lab","--terrain-test-lab","--destructible-test-lab"])).unwrap(),
            Command::IntegratedLab {key:"key",digest:"digest",gateway:"config",pool:"pool",capture:"capture",geometry:Some("mesh"),ap_test_lab:true,terrain_test_lab:true,destructible_test_lab:true,catalog:None,map:MapId::Karelia,vehicle:VehicleKind::Ms1});
        for extra in [vec!["--ap-test-lab"], vec!["mesh","--unverified"], vec!["","--ap-test-lab"],
            vec!["mesh","--terrain-test-lab"],vec!["mesh","--ap-test-lab","--ap-test-lab"],
            vec!["mesh","--ap-test-lab","--terrain-test-lab","--terrain-test-lab"]] {
            let mut values = vec!["exe","legacy091-integrated-lab","key","digest","config","pool","capture"];
            values.extend(extra); assert!(command(&args(&values)).is_err());
        }
        for values in [
            vec!["exe","legacy091-integrated-lab","key","digest","config","pool"],
            vec!["exe","legacy091-integrated-lab","key","digest","config","","capture"],
            vec!["exe","legacy091-integrated-lab","key","digest","config","pool",""]
        ] { assert!(command(&args(&values)).is_err()); }
    }

    #[test]fn imported_catalog_requires_cumulative_flags_explicit_path_and_lowercase_sha(){
        let sha="a".repeat(64);let base=["exe","legacy091-integrated-lab","key","digest","config","pool","capture","mesh","--ap-test-lab","--terrain-test-lab","--destructible-catalog","catalog"];
        let mut valid=base.to_vec();valid.push(&sha);
        assert!(matches!(command(&args(&valid)).unwrap(),Command::IntegratedLab{catalog:Some(("catalog",_)),destructible_test_lab:false,ap_test_lab:true,terrain_test_lab:true,..}));
        for hash in ["", "a", "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"]{
            let mut values=base.to_vec();values.push(hash);assert!(command(&args(&values)).is_err());}
        for index in [8,9,10]{let mut values=valid.clone();values[index]="--wrong";assert!(command(&args(&values)).is_err());}
        assert!(command(&args(&base)).is_err());
    }

    #[test] fn explicit_prohorovka_requires_complete_cumulative_path_and_one_trailing_map() {
        let base=["exe","legacy091-integrated-lab","key","digest","config","pool","capture",
            "mesh","--ap-test-lab","--terrain-test-lab"];
        let mut plain=base.to_vec(); plain.extend(["--map","05_prohorovka"]);
        assert!(matches!(command(&args(&plain)).unwrap(),Command::IntegratedLab {
            map:MapId::Prohorovka,ap_test_lab:true,terrain_test_lab:true,catalog:None,..}));
        let sha="a".repeat(64);
        let mut catalog=base.to_vec();
        catalog.extend(["--destructible-catalog","catalog",&sha,"--map","05_prohorovka"]);
        assert!(matches!(command(&args(&catalog)).unwrap(),Command::IntegratedLab {
            map:MapId::Prohorovka,catalog:Some(("catalog",_)),destructible_test_lab:false,..}));
        for length in 7..=9 {
            let mut values=base[..length].to_vec(); values.extend(["--map","05_prohorovka"]);
            assert!(command(&args(&values)).is_err());
        }
        for tail in [vec!["--map"],vec!["--map","04_prohorovka"],vec!["--map","5"],
            vec!["--map",""],vec!["--map","../05_prohorovka"],
            vec!["--destructible-test-lab","--map","05_prohorovka"],
            vec!["--map","01_karelia","--map","05_prohorovka"],
            vec!["--map","05_prohorovka","--destructible-catalog","catalog",&sha]] {
            let mut values=base.to_vec(); values.extend(tail); assert!(command(&args(&values)).is_err());
        }
        let mut explicit_old=base.to_vec(); explicit_old.extend(["--map","01_karelia"]);
        assert_eq!(command(&args(&base)).unwrap(),command(&args(&explicit_old)).unwrap());
    }

    #[test]
    fn interactive_has_exact_ordinary_arguments_and_optional_capture() {
        for capture in [None, Some("capture")] {
            let mut values = vec!["exe", "legacy091-interactive", "key", "digest", "gateway"];
            if let Some(value) = capture { values.push(value); }
            assert_eq!(command(&args(&values)).unwrap(), Command::Interactive { key: "key", digest: "digest", gateway: "gateway", capture });
        }
    }

    #[test]
    fn is7_selection_is_explicit_homogeneous_and_requires_complete_prohorovka_path() {
        let base=["exe","legacy091-integrated-lab","key","digest","config","pool","capture",
            "mesh","--ap-test-lab","--terrain-test-lab","--map","05_prohorovka"];
        let mut is7=base.to_vec();is7.extend(["--vehicle-test-lab","is7"]);
        assert!(matches!(command(&args(&is7)).unwrap(),Command::IntegratedLab {
            vehicle:VehicleKind::Is7,map:MapId::Prohorovka,..}));
        let mut ms1=base.to_vec();ms1.extend(["--vehicle-test-lab","ms1"]);
        assert_eq!(command(&args(&ms1)).unwrap(),command(&args(&base)).unwrap());
        for tail in [vec!["--vehicle-test-lab"],vec!["--vehicle-test-lab","IS-7"],
            vec!["--vehicle-test-lab","mixed"],vec!["--vehicle-test-lab","is7","--vehicle-test-lab","is7"]] {
            let mut values=base.to_vec();values.extend(tail);assert!(command(&args(&values)).is_err());
        }
        for length in 7..=10 {
            let mut values=base[..length].to_vec();values.extend(["--vehicle-test-lab","is7"]);
            assert!(command(&args(&values)).is_err());
        }
        let mut wrong_map=is7.clone();wrong_map[11]="01_karelia";
        assert!(command(&args(&wrong_map)).is_err());
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
