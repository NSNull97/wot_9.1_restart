//! SHELL-01 chassis loader and ordered layer query on pinned MS-1/IS-7 sources.
//! Our own geometry checks; native ModelHitTester parity is a separate step.
use super::*;
use std::path::PathBuf;
use super::super::{geometry::tests::{bundle, is7_bundle}, model::{Identity, World}};

fn root() -> PathBuf { PathBuf::from(std::env::var("WOT091_ROOT").unwrap_or_else(|_| "D:/WoT_9.1_Server".into())) }
fn chassis_path(name: &str) -> PathBuf { root().join("local/evidence/shell-01-chassis-20261104-02/bundles").join(name) }
fn ms1_chassis() -> ChassisArmor { ChassisArmor::load(&root().join("local"), &chassis_path("ussr-MS-1.json")).unwrap() }

fn actor(kind: VehicleKind, direction: [f32; 3], aim: [f32; 2]) -> Actor {
    let mut world = World::new_for_vehicle(991, std::time::Instant::now(), crate::map_profile091::MapId::Prohorovka, kind).unwrap();
    let slot = world.attach(Identity { account: "chassis-armor-actor".into(), database: 991, name: "chassis_actor".into() }, 991).unwrap();
    let mut a = world.actors[slot].clone();
    a.position = [37., 21., -105.]; a.direction = direction; a.aim.yaw = aim[0]; a.aim.pitch = aim[1];
    a
}

/// A segment through the centroid of one chassis triangle, 3 m on each side along its normal.
fn through_triangle(c: &ChassisArmor, a: &Actor, index: usize) -> ([f32; 3], [f32; 3], u32) {
    let t = &c.triangles[index];
    let [p, q, r] = [t.a, t.b, t.c].map(|i| c.vertices[i as usize]);
    let centroid: [f32; 3] = std::array::from_fn(|k| (p[k] + q[k] + r[k]) / 3.);
    let u: [f32; 3] = std::array::from_fn(|k| q[k] - p[k]);
    let v: [f32; 3] = std::array::from_fn(|k| r[k] - p[k]);
    let n = [u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0]];
    let len = n.iter().map(|x| x * x).sum::<f32>().sqrt();
    let world = |local: [f32; 3]| { let r = pose::rotate(local, a.direction); std::array::from_fn(|k| a.position[k] + r[k]) };
    let start = world(std::array::from_fn(|k| centroid[k] + 3. * n[k] / len));
    let end = world(std::array::from_fn(|k| centroid[k] - 3. * n[k] / len));
    (start, end, t.triangle_id)
}

#[test] fn ms1_chassis_loads_with_source_track_materials() {
    let c = ms1_chassis();
    assert_eq!((c.vehicle_id.as_str(), c.type_compact_id), ("vehicle:ussr:MS-1", 3329));
    assert_eq!(c.materials.len(), 2);
    for m in &c.materials {
        assert_eq!((m.armor_mm, m.damage_kind, m.auto_damage_kind, m.vehicle_damage_factor), (5., 1, true, 0.));
        assert!(m.collide_once_only && !m.use_hit_angle && !m.may_ricochet && !m.continue_trace_if_no_hit);
    }
    assert!(c.triangles.iter().all(|t| t.triangle_id >= CHASSIS_BASE && c.material(&t.material).is_some()));
}

#[test] fn unpinned_or_altered_bytes_are_refused() {
    let raw = fs::read(chassis_path("ussr-MS-1.json")).unwrap();
    let mut changed = raw.clone(); changed.push(b' ');
    assert!(ChassisArmor::from_bytes(&changed).is_err());
    let mut flipped = raw.clone(); let at = flipped.len() / 2; flipped[at] ^= 1;
    assert!(ChassisArmor::from_bytes(&flipped).is_err());
    assert!(ChassisArmor::from_bytes(&[]).is_err());
    assert!(ChassisArmor::from_bytes(&raw).is_ok());
    assert!(ChassisArmor::load(&root().join("local"), Path::new("relative.json")).is_err());
}

#[test] fn embedded_table_pin_matches_and_covers_known_vehicles() {
    let pins = pins().unwrap();
    assert_eq!(pins.len(), 370);
    assert!(pins.values().any(|p| p.vehicle_id == "vehicle:usa:M103"));
    assert!(parse_table(&[TABLE, b" "].concat()).is_err());
}

#[test] fn chassis_binds_only_to_its_own_vehicle_bundle() {
    let c = ms1_chassis();
    assert!(c.check_binding(&bundle()).is_ok());
    assert!(c.check_binding(&is7_bundle()).is_err());
    let is7 = ChassisArmor::load(&root().join("local"), &chassis_path("ussr-IS-7.json")).unwrap();
    assert!(is7.check_binding(&is7_bundle()).is_ok());
    let a = actor(VehicleKind::Is7, [0.; 3], [0.; 2]);
    assert!(armor_layers(&bundle(), &is7, &a, 1, 1000, [0.; 3], [1.; 3]).is_err());
}

#[test] fn track_triangle_is_a_chassis_layer_with_track_facts() {
    let (b, c) = (bundle(), ms1_chassis());
    let a = actor(VehicleKind::Ms1, [0.; 3], [0.; 2]);
    let (start, end, id) = through_triangle(&c, &a, 0);
    let layers = armor_layers(&b, &c, &a, 1, 1000, start, end).unwrap();
    let hit = layers.iter().find(|l| l.triangle_id == id).expect("aimed chassis triangle is crossed");
    assert_eq!(hit.part, Part::Chassis);
    assert!(matches!(&hit.facts, LayerMaterial::Track(m) if m.name == hit.material && m.armor_mm == 5.));
    assert!((hit.t - 0.5).abs() < 1e-4);
    for (i, l) in layers.iter().enumerate() {
        assert_eq!(l.order, i);
        if i > 0 { assert!(layers[i - 1].t <= l.t); }
        assert_eq!(l.tied_with_previous, i > 0 && layers[i - 1].t.to_bits() == l.t.to_bits());
        match l.part { Part::Chassis => assert!(matches!(l.facts, LayerMaterial::Track(_) | LayerMaterial::TrackWithoutRecord)),
            _ => assert!(matches!(l.facts, LayerMaterial::Component(_))) }
    }
}

#[test] fn chassis_follows_the_hull_not_the_turret() {
    let (b, c) = (bundle(), ms1_chassis());
    let still = actor(VehicleKind::Ms1, [0.; 3], [0.; 2]);
    let turned = actor(VehicleKind::Ms1, [0.; 3], [1.2, 0.]);
    let (start, end, _) = through_triangle(&c, &still, c.triangles.len() / 2);
    let pick = |layers: Vec<Layer>| layers.into_iter().filter(|l| matches!(l.part, Part::Chassis | Part::Hull))
        .map(|l| (l.triangle_id, l.t.to_bits())).collect::<Vec<_>>();
    assert_eq!(pick(armor_layers(&b, &c, &still, 1, 1000, start, end).unwrap()),
               pick(armor_layers(&b, &c, &turned, 1, 1000, start, end).unwrap()));
    // Rotating the vehicle moves the chassis: the same world segment no longer crosses the aimed triangle at t=0.5.
    let yawed = actor(VehicleKind::Ms1, [std::f32::consts::FRAC_PI_2, 0., 0.], [0.; 2]);
    let (_, _, id) = through_triangle(&c, &still, c.triangles.len() / 2);
    let moved = armor_layers(&b, &c, &yawed, 1, 1000, start, end).unwrap();
    assert!(!moved.iter().any(|l| l.triangle_id == id && (l.t - 0.5).abs() < 1e-4));
    let (ys, ye, _) = through_triangle(&c, &yawed, c.triangles.len() / 2);
    assert!(armor_layers(&b, &c, &yawed, 1, 1000, ys, ye).unwrap().iter().any(|l| l.triangle_id == id));
}

#[test] fn layers_cross_several_parts_in_segment_order() {
    let (b, c) = (bundle(), ms1_chassis());
    let a = actor(VehicleKind::Ms1, [0.; 3], [0.; 2]);
    // Straight down through the vehicle centre line: turret, hull, then chassis.
    let top = [a.position[0], a.position[1] + 6., a.position[2]];
    let bottom = [a.position[0], a.position[1] - 3., a.position[2]];
    let layers = armor_layers(&b, &c, &a, 1, 1000, top, bottom).unwrap();
    let parts: Vec<Part> = layers.iter().map(|l| l.part).collect();
    assert!(parts.contains(&Part::Hull), "{parts:?}");
    let first_hull = parts.iter().position(|p| *p == Part::Hull).unwrap();
    if let Some(turret) = parts.iter().position(|p| *p == Part::Turret) { assert!(turret < first_hull); }
    assert!(layers.windows(2).all(|w| w[0].t <= w[1].t));
}

#[test] fn bad_pose_or_segment_fails_closed() {
    let (b, c) = (bundle(), ms1_chassis());
    let a = actor(VehicleKind::Ms1, [0.; 3], [0.; 2]);
    assert!(armor_layers(&b, &c, &a, 1, 1000, [1.; 3], [1.; 3]).is_err());
    assert!(armor_layers(&b, &c, &a, 1, 999, [0.; 3], [1.; 3]).is_err());
    let mut far = a.clone(); far.position = [f32::NAN, 0., 0.];
    assert!(armor_layers(&b, &c, &far, 1, 1000, [0.; 3], [1.; 3]).is_err());
}
