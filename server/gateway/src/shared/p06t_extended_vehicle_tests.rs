use super::*;
use crate::p06t_shells091::{self as source,Mount};

#[test] fn p06t_extended_registry_is_explicit_and_old_parsers_are_closed() {
    assert_eq!(VehicleKind::ALL.len(),5);assert_eq!(VehicleKind::SUPPORTED.len(),7);
    for (index,kind) in VehicleKind::SUPPORTED.into_iter().enumerate() {
        assert_eq!(kind.index(),index);
        assert_eq!(VehicleKind::from_extended_label(kind.label()),Some(kind));
        assert_eq!(VehicleKind::from_extended_vehicle_compact_id(kind.vehicle_compact_id()),Some(kind));
        if index<5 {assert_eq!(VehicleKind::from_label(kind.label()),Some(kind));assert!(kind.source_aim().is_none());}
        else {assert_eq!(VehicleKind::from_label(kind.label()),None);assert_eq!(VehicleKind::from_vehicle_compact_id(kind.vehicle_compact_id()),None);
            assert!(!kind.battle_admission());assert_eq!(kind.initial_ammo(),0);assert!(kind.panel_rows().iter().all(|row|row.1==0));}
    }
    for value in ["wt-e100-150","fv215b","WT128",""] {assert_eq!(VehicleKind::from_extended_label(value),None);}
    assert_eq!(VehicleKind::from_extended_vehicle_compact_id(9281),None); // legacy wrong UK nation CD
}

#[test] fn p06t_extended_identity_and_stock_stats_match_pinned_original_source_rows() {
    // Original #717 semantic manifest b1bd8eaa...79d60, not a self-codec oracle.
    for (kind,vehicle,gun,descriptor,view,mass,ammo,reload,shots) in [
        (VehicleKind::Wt128,16913,23060,&[0x11,0x42,0xa1,0,0x2c,0,0xcd,0,0x0d,0,0x86,0,0x5a,0,0][..],420.,100000.,60,60.,[13850,14106,14362]),
        (VehicleKind::Fv183,9297,13908,&[0x51,0x24,0x4f,0,0x3f,0,0xcd,0,0x14,0,0x45,0,0x36,0,0][..],400.,60000.,12,30.,[20826,21082,21338]),
    ] {
        assert_eq!(kind.vehicle_compact_id(),vehicle);assert_eq!(kind.gun_compact_id(),gun);assert_eq!(kind.descriptor(),descriptor);
        assert_eq!(kind.max_health(),2000);assert_eq!(kind.view_range(),view);assert_eq!(kind.mass_kg(),mass);
        assert_eq!(kind.ammo_limit(),ammo);assert_eq!(kind.reload_seconds(),reload);assert_eq!(kind.panel_rows().map(|r|r.0),shots);
        let p=source::profile(kind.mount());assert_eq!(p.vehicle_type_compact_descr,u16::try_from(vehicle).unwrap());
        assert_eq!(p.gun_compact_descr,u16::try_from(gun).unwrap());assert_eq!(p.capacity,ammo);assert_eq!(p.reload_seconds,reload as f64);
        assert_eq!(p.shots.map(|s|u32::from(s.compact_descr)),shots);assert!(p.additional_vehicle_qualification_required);
    }
    assert_eq!(VehicleKind::Wt128.mount(),Mount::WtE100128);assert_eq!(VehicleKind::Fv183.mount(),Mount::Fv215b183);
    assert_eq!(source::profile(VehicleKind::Wt128.mount()).clip_count,6);
    assert_eq!(source::profile(Mount::WtE100150).clip_count,4); // source-only, no VehicleKind
    assert_eq!(source::profile(VehicleKind::Fv183.mount()).shots[1].penetration_mm,[275.,275.]);
}

#[test] fn p06t_extended_default_ap_geometry_and_effects_are_exact_source_properties() {
    for (kind,effect) in [(VehicleKind::Wt128,14),(VehicleKind::Fv183,18)] {
        let raw=source::profile(kind.mount()).shots[0];let shell=kind.shell();
        assert_eq!(shell.caliber,raw.caliber_mm);assert_eq!(shell.damage,raw.damage_hp);
        assert_eq!([shell.power_100,shell.power_500],raw.penetration_mm);
        assert_eq!(shell.raw_speed as f64,raw.raw_speed_mps);assert_eq!(shell.gravity as f64,9.81f32 as f64);
        assert_eq!(shell.effects,effect);assert_eq!(crate::armament_wire091::effect_index(raw).unwrap(),effect);
        assert_eq!(kind.shell_compact_id(),u32::from(raw.compact_descr));
    }
    let wt=VehicleKind::Wt128.aim();assert_eq!(wt.pivot,[0.,1.379118,-1.71333]);assert_eq!(wt.gun,[0.,1.37102,-0.690134]);
    let fv=VehicleKind::Fv183.aim();assert_eq!(fv.pivot,[0.,1.718248,-1.49516]);assert_eq!(fv.gun,[0.,0.583916,1.59175]);
    assert_eq!((wt.aiming_time,fv.aiming_time),(1.5,3.4));
}
