use super::*;
use super::super::{aim,ap,geometry,materials};
use std::path::Path;

fn bundle(kind:VehicleKind)->geometry::Bundle {
    let root=std::env::var("WOT091_ROOT").unwrap_or_else(|_|"D:/WoT_9.1_Server".into());
    geometry::Bundle::load(&Path::new(&root).join("local"),&Path::new(&root).join("local/evidence/20261016-p04m-source-import01").join(format!("{}-stock.json",kind.label()))).unwrap()
}
fn source(kind:VehicleKind)->serde_json::Value {
    let root=std::env::var("WOT091_ROOT").unwrap_or_else(|_|"D:/WoT_9.1_Server".into());
    let path=Path::new(&root).join("local/evidence/20261016-p04m-source-import01").join(format!("{}-stock.json",kind.label()));
    assert_eq!(bundle(kind).vehicle_kind(),kind); // Production digest gate first.
    serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap()
}
#[test] fn p04m_registry_matches_real_pinned_mounted_source_without_owned_admission() {
    let mut labels=Vec::new();let mut ids=Vec::new();
    for (index,kind) in VehicleKind::ALL.into_iter().enumerate() {
        assert_eq!(kind.index(),index);assert_eq!(VehicleKind::from_label(kind.label()),Some(kind));
        assert_eq!(VehicleKind::from_vehicle_compact_id(kind.vehicle_compact_id()),Some(kind));
        assert!(!labels.contains(&kind.label()));labels.push(kind.label());assert!(!ids.contains(&kind.vehicle_compact_id()));ids.push(kind.vehicle_compact_id());
    }
    assert_eq!(VehicleKind::from_vehicle_compact_id(0),None);assert_eq!(VehicleKind::from_label("T34"),None);
    for kind in [VehicleKind::T26,VehicleKind::T34,VehicleKind::T3485] {
        let d=source(kind);let id=&d["identity"];let gun=&d["gun"];
        assert_eq!(id["type_compact_id"],kind.vehicle_compact_id());assert_eq!(id["max_hp"],kind.max_health());
        assert_eq!(id["module_compact_ids"]["gun"],kind.gun_compact_id());
        assert_eq!(id["descriptor_hex"],kind.descriptor().iter().map(|b|format!("{b:02x}")).collect::<String>());
        assert_eq!(gun["capacity"],kind.ammo_limit());assert_eq!(gun["shell_compact_id"],kind.shell_compact_id());
        assert_eq!(gun["reload_seconds"].as_f64().unwrap() as f32,kind.reload_seconds());
        assert_eq!(gun["damage_hp"],kind.damage());assert_eq!(d["movement_source"]["mass_kg"],kind.mass_kg());
        assert_eq!(gun["raw_speed_mps"].as_f64().unwrap() as f32,kind.shell().raw_speed);
        assert_eq!(gun["penetration_mm"][0].as_f64().unwrap(),kind.shell().power_100);
        assert_eq!(gun["penetration_mm"][1].as_f64().unwrap(),kind.shell().power_500);
        assert!(!kind.battle_admission());assert_eq!(d["battle_admission"],false);
        assert_eq!(kind.initial_ammo(),20);assert_eq!(kind.panel_rows()[1].1,0);assert_eq!(kind.panel_rows()[2].1,0);
    }
    assert_eq!(VehicleKind::T34.vehicle_compact_id(),1);assert_eq!(VehicleKind::T34.gun_compact_id(),4);
}
#[test] fn p04m_mounted_pitch_and_rear_sector_preserve_source_overrides() {
    let t=VehicleKind::T3485.aim();assert!((t.min_pitch-(-22f32).to_radians()).abs()<1e-6);assert!((t.max_pitch-7f32.to_radians()).abs()<1e-6);
    for kind in [VehicleKind::T26,VehicleKind::T3485] {
        for yaw in [-PI,-2.,-0.1,0.,0.3,2.,PI] {assert!((aim::pitch_max_for(kind,yaw)-kind.aim().max_pitch).abs()<1e-6);}
    }
    let edge=PI-42f32.to_radians();
    assert!((aim::pitch_max_for(VehicleKind::T34,PI)-1f32.to_radians()).abs()<1e-6);
    assert!((aim::pitch_max_for(VehicleKind::T34,edge-0.2)-3.5f32.to_radians()).abs()<1e-6);
    assert!((aim::pitch_max_for(VehicleKind::T34,0.)-6f32.to_radians()).abs()<1e-6);
    for yaw in [0.,edge,edge-0.2,edge-0.4,PI] {assert!((aim::pitch_max_for(VehicleKind::T34,yaw)-aim::pitch_max_for(VehicleKind::T34,-yaw)).abs()<1e-6);}
}
#[test] fn p04m_cross_profile_ap_uses_target_catalog_and_selected_gun_without_fallback() {
    for target in [VehicleKind::T26,VehicleKind::T34,VehicleKind::T3485] {
        let b=bundle(target);let plate=b.materials().lookup("Hull","armor_1").unwrap();let armor=plate.effective.as_ref().unwrap().armor.unwrap() as f64;
        for shooter in VehicleKind::ALL {
            let r=ap::resolve_for_pair(shooter,target,ap::Input{material:&plate,segment_direction:[0.,0.,1.],winding_normal:[0.,0.,-1.],distance:100.}).unwrap();
            assert_eq!(r.damage,if shooter.shell().power_100>armor{shooter.damage()}else{0});assert_eq!(r.nominal_power,Some(shooter.shell().power_100));
        }
        let gun=b.materials().lookup(materials::gun_component(target).name(),"armor_1").unwrap();
        assert_eq!(ap::resolve_for_pair(VehicleKind::Ms1,target,ap::Input{material:&gun,segment_direction:[0.,0.,1.],winding_normal:[0.,0.,-1.],distance:100.}).unwrap().outcome,ap::Outcome::Unsupported(ap::Reason::Component));
    }
}
