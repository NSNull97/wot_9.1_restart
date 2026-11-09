//! MODVOL-01: the volumes file, its binding and the classic selection over it.
use super::*;
use crate::p06t_device_caps::Profile;
use crate::p06t_lab_proxy::{select_classic, Component as Part, Target};
use serde_json::json;

const BOX: [[f32; 3]; 2] = [[-1., 0., -2.], [1., 1., 2.]];
fn file(volumes: Value) -> Vec<u8> {
    serde_json::to_vec(&json!({"schema": SCHEMA, "policy": POLICY, "vehicle": "vehicle:ussr:MS-1", "depth": {"front_rear_m": 0.5},
        "source": {"archive_sha256": "x", "authors": [], "textures": {}}, "components": {"Hull": {"box": BOX, "volumes": volumes}}})).unwrap()
}
fn ammo_and_seat() -> ModuleVolumes {
    ModuleVolumes::from_bytes(&file(json!({"ammo": [[[-1., 0.2, -1.8], [1., 0.8, -1.2]]], "crew": [[[[-0.4, 0.2, 1.0], [0.4, 0.8, 1.5]]]]}))).unwrap()
}
fn hits(v: Option<&ModuleVolumes>, start: [f32; 3], end: [f32; 3]) -> Vec<Target> {
    select_classic(Profile::Ms1, Part::Hull, BOX, start, end, true, v).unwrap().into_iter().map(|h| h.target).collect()
}

#[test] fn a_device_with_volumes_is_hit_there_and_loses_its_lab_box() {
    let v = ammo_and_seat();
    assert!(v.replaces(Device::AmmoBay) && !v.replaces(Device::Engine));
    let (start, end) = ([0., 0.5, -1.95], [0., 0.5, -1.0]);
    assert!(hits(Some(&v), start, end).contains(&Target::Device(Device::AmmoBay)), "the marked place");
    assert!(!hits(None, start, end).contains(&Target::Device(Device::AmmoBay)), "the LAB box is elsewhere");
    // The LAB ammo box sits mid-hull: a shot only there hits no ammo once the volume replaces it.
    let (start, end) = ([0., 0.5, -0.4], [0., 0.5, 0.5]);
    assert!(hits(None, start, end).contains(&Target::Device(Device::AmmoBay)));
    assert!(!hits(Some(&v), start, end).contains(&Target::Device(Device::AmmoBay)));
    // An unmarked device keeps its LAB box.
    let (start, end) = ([0., 0.5, -1.7], [0., 0.5, -0.8]);
    assert_eq!(hits(Some(&v), start, end).contains(&Target::Device(Device::Engine)), hits(None, start, end).contains(&Target::Device(Device::Engine)));
}

#[test] fn the_driver_takes_the_first_crew_volume_and_each_target_is_hit_once() {
    let v = ModuleVolumes::from_bytes(&file(json!({"crew": [[[[-0.4, 0.2, 1.0], [0.4, 0.8, 1.5]], [[-0.4, 0.2, 1.2], [0.4, 0.8, 1.9]]]]}))).unwrap();
    let driver = Profile::Ms1.crew().iter().position(|c| c.primary_driver).unwrap() as u8;
    let targets = hits(Some(&v), [0., 0.5, 0.9], [0., 0.5, 1.95]);
    assert_eq!(targets.iter().filter(|t| **t == Target::Seat(driver)).count(), 1, "{targets:?}");
    assert!(hits(None, [0., 0.5, 0.9], [0., 0.5, 1.2]).iter().all(|t| *t != Target::Seat(driver)), "LAB seat lies nearer the front");
    assert!(hits(Some(&v), [0., 0.5, 0.9], [0., 0.5, 1.2]).contains(&Target::Seat(driver)));
}

#[test] fn the_turret_ignores_hull_volumes_and_a_gun_component_stays_lab() {
    let v = ammo_and_seat();
    let turret = select_classic(Profile::Ms1, Part::Turret, BOX, [0., 0.5, -1.95], [0., 0.5, -1.0], true, Some(&v)).unwrap();
    assert!(turret.iter().all(|h| h.target != Target::Device(Device::AmmoBay)));
    let gun = select_classic(Profile::Ms1, Part::Gun, BOX, [0., 0.5, -1.95], [0., 0.5, -1.0], true, Some(&v)).unwrap();
    assert_eq!(gun.iter().map(|h| h.target).collect::<Vec<_>>(), vec![Target::Device(Device::Gun)]);
}

#[test] fn binding_and_schema_refuse_a_foreign_or_malformed_file() {
    let v = ammo_and_seat();
    let turret = [[-1., 0., -2.], [1., 1., 2.]];
    assert!(v.check_binding("ussr:MS-1", BOX, turret).is_ok());
    assert!(v.check_binding("ussr:T-34", BOX, turret).is_err(), "other vehicle");
    assert!(v.check_binding("ussr:MS-1", [[-2., 0., -2.], [1., 1., 2.]], turret).is_err(), "other frame");
    for bad in [json!({}), json!({"ammo": []}), json!({"radio": [[[0., 0., 0.], [1., 1., 1.]]]}), json!({"ammo": [[[1., 0., 0.], [0., 1., 1.]]]}),
        json!({"ammo": [[[0., 0., 0.], [99., 1., 1.]]]}), json!({"crew": [[]]})] {
        assert!(ModuleVolumes::from_bytes(&file(bad.clone())).is_err(), "{bad}");
    }
    assert!(ModuleVolumes::from_bytes(b"{}").is_err());
}
