//! Domain/parser fixtures, not native identity acceptance. Source resource,
//! span, HP and revision metadata are from the pinned P06O inventory02. Native
//! indices and export/worker hashes below are deliberately synthetic test data.
use super::*;
use serde_json::json;

fn manifest() -> Value {
    json!({
        "version": 1, "profile": "test_lab", "map": "01_karelia",
        "destructibles_sha256": DEFINITIONS_SHA,
        "physics_manifest_sha256": PHYSICS_SHA,
        "projectile_manifest_sha256": obstacles::MANIFEST_SHA256,
        "native_exports_sha256": ["1".repeat(64), "2".repeat(64)],
        "worker": {"file": "physics-removals.json", "sha256": "3".repeat(64)},
        "objects": [
            {"object_id":1513,"instance_id":1512,"chunk_id":31354,"native_index":0,
             "resource":"content/MilitaryEnvironment/mle019_GerBoxes/normal/lod0/mle019_GerBoxes2.model",
             "health":10,"material_kind":73,"projectile_first_triangle":88716,"projectile_triangle_count":33,
             "physics_first_triangle":171781,"physics_triangle_count":33,
             "object_revision":"b89e487735c9cda7b33edb6fd6463ee08ab83e00b54ec8e3df48d9a7f8cff0a6"},
            {"object_id":1514,"instance_id":1513,"chunk_id":31354,"native_index":1,
             "resource":"content/MilitaryEnvironment/mle009_BoxCamouflage/normal/lod0/mle009_BoxCamouflage.model",
             "health":15,"material_kind":73,"projectile_first_triangle":88749,"projectile_triangle_count":42,
             "physics_first_triangle":171814,"physics_triangle_count":42,
             "object_revision":"e403bd09f44b2cf15f7ffdfc4019f5e917d7e6a30626a7fb2650d3b6db27792d"},
            {"object_id":1529,"instance_id":1528,"chunk_id":31355,"native_index":0,
             "resource":"content/MilitaryEnvironment/mle019_GerBoxes/normal/lod0/mle019_GerBoxes3.model",
             "health":9,"material_kind":73,"projectile_first_triangle":89230,"projectile_triangle_count":86,
             "physics_first_triangle":173347,"physics_triangle_count":86,
             "object_revision":"920a99838306917d47128ab027f757ec726c60917ebcd579233f3d0da3032575"}
        ]
    })
}

fn parse_bytes(bytes: &[u8]) -> io::Result<Catalog> {
    Catalog::parse(bytes, &format!("{:x}", Sha256::digest(bytes)))
}
fn parse(value: &Value) -> io::Result<Catalog> {
    parse_bytes(&serde_json::to_vec(value).unwrap())
}

pub(crate) fn catalog() -> Arc<Catalog> {
    Arc::new(parse(&manifest()).unwrap())
}

fn contact_manifest() -> Value {
    let mut value=manifest();
    value["version"]=json!(2);
    value["contacts"]=json!(true);
    for row in value["objects"].as_array_mut().unwrap() { row["kind"]=json!("fragile"); }
    // A tree has no projectile span, a pinned tree material, and its own
    // physics span. The resource path is a domain label, not native code.
    value["objects"][2]["kind"]=json!("tree");
    value["objects"][2]["resource"]=json!("speedtree/karelia/tree_03.spt");
    value["objects"][2]["health"]=json!(70_000u32);
    value["objects"][2]["material_kind"]=json!(71);
    value["objects"][2]["projectile_first_triangle"]=json!(0);
    value["objects"][2]["projectile_triangle_count"]=json!(0);
    value["objects"][2]["physics_first_triangle"]=json!(180_000);
    value["objects"][2]["physics_triangle_count"]=json!(17);
    value
}

pub(crate) fn contact_catalog() -> Arc<Catalog> {
    Arc::new(parse(&contact_manifest()).unwrap())
}

fn hit(index: usize) -> terrain::Hit {
    let object = &catalog().objects[index];
    // Synthetic domain input. Geometry source binding is exercised separately.
    terrain::Hit {
        triangle_id: object.projectile_first_triangle,
        t: 0.5, point: [-402.0, 57.0, -404.0], normal: [0.0, 1.0, 0.0],
        surface: terrain::Surface::StaticObstacle {
            instance_id: object.instance_id, material_kind: object.material_kind,
        },
    }
}

#[test]
fn parses_original_source_rows_and_exact_importer_schema() {
    let catalog = catalog();
    assert_eq!(catalog.objects.len(), 3);
    assert_eq!(catalog.chunks(), vec![31354, 31355]);
    assert_eq!(catalog.objects.iter().map(|o| o.health).collect::<Vec<_>>(), vec![10, 15, 9]);
    assert_eq!(catalog.instance(1513).unwrap().projectile_first_triangle, 88749);
    assert_eq!(catalog.instance(1513).unwrap().physics_first_triangle, 171814);
    assert!(catalog.instance(1514).is_none());
    assert_eq!(catalog.worker_file, "physics-removals.json");
    assert!(!catalog.contacts);
    // Adjacent spans are legal; native indices may repeat in different chunks.
    assert_eq!(catalog.objects[0].projectile_first_triangle + catalog.objects[0].projectile_triangle_count,
        catalog.objects[1].projectile_first_triangle);
    assert_eq!(catalog.objects[0].native_index, catalog.objects[2].native_index);
    let mut one = manifest();
    one["native_exports_sha256"] = json!(["1".repeat(64)]);
    one["objects"][2]["native_index"] = json!(255);
    assert_eq!(parse(&one).unwrap().objects[2].native_index, 255);
}

#[test]
fn parses_contact_v2_tree_and_u32_health_contract() {
    let catalog=parse(&contact_manifest()).unwrap();
    assert!(catalog.contacts);
    assert_eq!(catalog.objects[2].kind,ObjectKind::Tree);
    assert_eq!(catalog.objects[2].health,70_000);
    assert_eq!(catalog.objects[2].material_kind,71);
    assert_eq!(catalog.objects[2].projectile_triangle_count,0);
    assert!(catalog.objects[2].physics_triangle_count>0);
    let mut legacy=manifest();
    legacy["objects"][0]["health"]=json!(i16::MAX as u32 + 1);
    assert!(parse(&legacy).is_err());
}

#[test]
fn contact_parser_accepts_pinned_row_bound_and_rejects_the_next_row() {
    let mut value=contact_manifest();
    let base=value["objects"][0].clone();
    let rows=(0..635u32).map(|i| {
        let mut row=base.clone();
        row["object_id"]=json!(i+1);
        row["instance_id"]=json!(i);
        let chunk=((121+(i%12))<<8)|(121+((i/12)%12));
        row["chunk_id"]=json!(chunk);
        row["native_index"]=json!(i/144);
        row["resource"]=json!(format!("content/test/object_{i}.model"));
        row["health"]=json!(70_000u32+i);
        row["projectile_first_triangle"]=json!(i);
        row["projectile_triangle_count"]=json!(1);
        row["physics_first_triangle"]=json!(1_000+i);
        row["physics_triangle_count"]=json!(1);
        row["object_revision"]=json!(format!("{:064x}",i+1));
        row["kind"]=json!("fragile");
        row
    }).collect::<Vec<_>>();
    value["objects"]=json!(rows);
    let parsed=parse(&value).unwrap();
    assert_eq!(parsed.objects.len(),635);
    assert_eq!(parsed.objects[634].health,70_634);
    value["objects"].as_array_mut().unwrap().resize(MAX_CONTACT_OBJECTS+1,base);
    assert!(parse(&value).is_err());
}

#[test]
fn rejects_hash_schema_pins_unknown_fields_and_worker_paths() {
    let bytes = serde_json::to_vec(&manifest()).unwrap();
    assert!(Catalog::parse(&bytes, &"0".repeat(64)).is_err());
    assert!(Catalog::parse(&bytes, "").is_err());
    for (field, value) in [
        ("version", json!(2)), ("profile", json!("production")),
        ("map", json!("02_malinovka")), ("destructibles_sha256", json!("0".repeat(64))),
        ("physics_manifest_sha256", json!("0".repeat(64))),
        ("projectile_manifest_sha256", json!("0".repeat(64))),
        ("unknown", json!(false)),
    ] {
        let mut v = manifest(); v[field] = value;
        assert!(parse(&v).is_err(), "accepted invalid top-level {field}");
    }
    for value in [json!([]), json!(["x"]), json!(["A".repeat(64)]),
        json!(["1".repeat(64), "1".repeat(64)]), json!(["2".repeat(64), "1".repeat(64)]),
        json!(["1".repeat(64), "2".repeat(64), "3".repeat(64)])] {
        let mut v = manifest(); v["native_exports_sha256"] = value;
        assert!(parse(&v).is_err());
    }
    for value in ["../physics-removals.json", "D:/physics-removals.json", "other.json", ""] {
        let mut v = manifest(); v["worker"]["file"] = json!(value);
        assert!(parse(&v).is_err());
    }
    for field in ["sha256", "unknown"] {
        let mut v = manifest(); v["worker"][field] = json!("bad");
        assert!(parse(&v).is_err());
    }
    let mut v = manifest(); v["objects"][0]["unknown"] = json!(1);
    assert!(parse(&v).is_err());
    v = manifest(); v["objects"][0].as_object_mut().unwrap().remove("health");
    assert!(parse(&v).is_err());
}

#[test]
fn rejects_duplicate_json_keys_and_bounded_input_excess() {
    let encoded = serde_json::to_string(&manifest()).unwrap();
    let duplicate = format!("{{\"version\":1,{}", &encoded[1..]);
    assert!(parse_bytes(duplicate.as_bytes()).is_err());
    let mut oversized = encoded.into_bytes(); oversized.resize(131073, b' ');
    assert!(parse_bytes(&oversized).is_err());
    assert!(parse_bytes(br#"{"version":1,"objects":[]"#).is_err());
}

#[test]
fn rejects_numeric_narrowing_overflow_and_invalid_identity() {
    for (field, value) in [
        ("object_id", json!(0)), ("object_id", json!(1514)),
        ("instance_id", json!(2918)), ("instance_id", json!(4_294_967_296u64)),
        ("chunk_id", json!(65536)), ("chunk_id", json!(0)),
        ("native_index", json!(256)), ("native_index", json!(-1)),
        ("health", json!(0)), ("health", json!(-1)), ("health", json!(32768)),
        ("health", json!(32.5)), ("health", json!(true)),
        ("material_kind", json!(87)), ("material_kind", json!(329)),
        ("projectile_first_triangle", json!(u32::MAX)),
        ("projectile_triangle_count", json!(0)), ("projectile_triangle_count", json!(u32::MAX)),
        ("physics_first_triangle", json!(u32::MAX)), ("physics_triangle_count", json!(0)),
        ("object_revision", json!("a".repeat(63))), ("object_revision", json!("G".repeat(64))),
        ("resource", json!("content/../escape.model")),
        ("resource", json!("content\\wrong.model")),
        ("resource", json!("content/wrong.visual")),
        ("resource", json!("objects/wrong.model")),
    ] {
        let mut v = manifest(); v["objects"][0][field] = value;
        assert!(parse(&v).is_err(), "accepted invalid object field {field}");
    }
    let mut v = manifest(); v["objects"][0]["physics_first_triangle"] = json!(335550);
    v["objects"][0]["physics_triangle_count"] = json!(2);
    assert!(parse(&v).is_err(), "physics span beyond exact pinned 335551 triangle mesh");
    let mut v = manifest(); v["objects"][0]["projectile_first_triangle"] = json!(179364);
    v["objects"][0]["projectile_triangle_count"] = json!(2);
    assert!(parse(&v).is_err());
}

#[test]
fn rejects_unsorted_or_duplicate_objects_native_identity_and_overlapping_spans() {
    let mut v = manifest(); v["objects"].as_array_mut().unwrap().swap(0, 1);
    assert!(parse(&v).is_err());
    let mut v = manifest(); v["objects"][1] = v["objects"][0].clone();
    assert!(parse(&v).is_err());
    for field in ["native_index", "projectile_first_triangle", "physics_first_triangle"] {
        let mut v = manifest(); v["objects"][1][field] = v["objects"][0][field].clone();
        assert!(parse(&v).is_err(), "accepted duplicate/overlapping {field}");
    }
    // One triangle crossing an otherwise adjacent range must also be rejected.
    for field in ["projectile_triangle_count", "physics_triangle_count"] {
        let mut v = manifest(); v["objects"][0][field] = json!(34);
        assert!(parse(&v).is_err());
    }
}

#[test]
fn enforces_catalog_object_cap_without_truncating() {
    let mut v = manifest();
    let base = v["objects"][0].clone();
    let rows = (0..MAX_OBJECTS).map(|i| {
        let mut row = base.clone();
        row["object_id"] = json!(i + 1); row["instance_id"] = json!(i);
        row["native_index"] = json!(i);
        row["projectile_first_triangle"] = json!(i); row["projectile_triangle_count"] = json!(1);
        row["physics_first_triangle"] = json!(i); row["physics_triangle_count"] = json!(1);
        row
    }).collect::<Vec<_>>();
    v["objects"] = json!(rows);
    assert_eq!(parse(&v).unwrap().objects.len(), MAX_OBJECTS);
    v["objects"].as_array_mut().unwrap().push(base);
    assert!(parse(&v).is_err());
    v["objects"] = json!([]);
    assert!(parse(&v).is_err());
}

#[test]
fn partial_hp32_keeps_geometry_until_second_impact_and_neighbors_untouched() {
    // Policy unit case: override reference HP explicitly, no historical claim.
    let mut v = manifest(); v["objects"][0]["health"] = json!(32);
    let mut state = State::new(Arc::new(parse(&v).unwrap()));
    let first = state.contact(1, 0, 1001, hit(0)).unwrap().unwrap();
    assert_eq!((first.health_before, first.health_after, first.scene_before, first.scene_after), (32, 2, 0, 0));
    assert_eq!(state.health, vec![2, 15, 9]);
    assert_eq!(state.scene_version(), 0);
    assert!(state.removed_ids().is_empty()); assert!(state.excluded().is_empty());
    assert!(state.native_destroyed(31354).is_empty());
    let second = state.contact(2, 1, 1002, hit(0)).unwrap().unwrap();
    assert_eq!((second.health_before, second.health_after, second.scene_before, second.scene_after), (2, 0, 0, 1));
    assert_eq!(state.health, vec![0, 15, 9]);
    assert_eq!(state.removed_ids(), vec![1513]); assert_eq!(state.excluded(), vec![1512]);
    assert_eq!(state.native_destroyed(31354), vec![0]);
    assert!(state.native_destroyed(31355).is_empty());
    assert_eq!(state.events, vec![first, second]);
}

#[test]
fn vehicle_contact_validates_hull_speed_normal_and_repeat_atomically() {
    let mut state=State::new(contact_catalog());
    let before=state.clone();
    assert!(state.ram_contact(1513,0,1001,1,[0.,0.,0.],[1.,0.,0.],[0.,0.,0.],4691.,"wheel".into()).unwrap().is_none());
    assert_eq!(state,before);
    assert!(state.ram_contact(1513,0,1001,1,[0.,0.,0.],[0.,0.,2.],[0.,0.,2.],4691.,"hull".into()).is_err());
    assert!(state.ram_contact(1513,0,1001,1,[0.,0.,0.],[1.,0.,0.],[0.5,0.,0.],4691.,"hull".into()).unwrap().is_none());
    assert!(state.ram_contact(1513,0,1001,1,[0.,0.,0.],[1.,0.,0.],[-2.,0.,0.],4691.,"hull".into()).unwrap().is_none());
    let event=state.ram_contact(1513,0,1001,1,[0.,0.,0.],[1.,0.,0.],[2.,0.,0.],4691.,"hull".into()).unwrap().unwrap();
    assert_eq!((event.scene_before,event.scene_after,event.fallen_tree), (0,1,None));
    assert_eq!(state.native_fragile_values(31354),vec![0]);
    assert_eq!(state.excluded(),vec![1512]);
    let after=state.clone();
    assert!(state.ram_contact(1513,0,1002,1,[0.,0.,0.],[1.,0.,0.],[2.,0.,0.],4691.,"hull".into()).unwrap().is_none());
    assert_eq!(state,after);
    assert!(state.ram_contact(1514,0,1000,1,[0.,0.,0.],[1.,0.,0.],[2.,0.,0.],4691.,"hull".into()).is_err());
    assert_eq!(state,after);
}

#[test]
fn vehicle_contact_uses_server_mass_and_closing_speed_energy_floor() {
    // A light tap from the same measured speed is retained as a candidate,
    // but cannot remove a catalog object. Increasing only the server-pinned
    // mass crosses the policy floor and produces the authoritative removal.
    let mut light = State::new(contact_catalog());
    assert!(light.ram_contact(1513,0,1001,1,[0.,0.,0.],[1.,0.,0.],[2.,0.,0.],1000.,"hull".into()).unwrap().is_none());
    assert_eq!(light.scene_version(),0);
    let mut heavy = State::new(contact_catalog());
    let event=heavy.ram_contact(1513,0,1001,1,[0.,0.,0.],[1.,0.,0.],[2.,0.,0.],4691.,"hull".into()).unwrap().unwrap();
    assert_eq!(event.mass_kg,4691.);
    assert_eq!((event.scene_before,event.scene_after),(0,1));
    let mut malformed = State::new(contact_catalog());
    assert!(malformed.ram_contact(1513,0,1001,1,[0.,0.,0.],[1.,0.,0.],[2.,0.,0.],999.,"hull".into()).is_err());
    assert_eq!(malformed.scene_version(),0);
}

#[test]
fn tree_contact_packs_immutable_fallen_value_and_excludes_tree() {
    let mut state=State::new(contact_catalog());
    let event=state.ram_contact(1529,1,1001,2,[1.,2.,3.],[1.,0.,0.],[2.,0.,0.],4691.,"hull".into()).unwrap().unwrap();
    let packed=event.fallen_tree.expect("tree contact must pack native fall");
    assert_eq!(state.native_fallen_trees(31355),vec![packed]);
    assert_eq!(state.removed_ids(),vec![1529]);
    assert_eq!(state.excluded(),vec![1528]);
    assert_eq!(state.scene_version(),1);
    let again=state.ram_contact(1529,1,1002,2,[1.,2.,3.],[1.,0.,0.],[4.,0.,0.],4691.,"hull".into()).unwrap();
    assert!(again.is_none());
    assert_eq!(state.native_fallen_trees(31355),vec![packed]);
}

#[test]
fn independent_objects_same_tick_remove_sorted_ids_not_kill_order() {
    let mut state = State::new(catalog());
    let first = state.contact(1, 1, 1001, hit(1)).unwrap().unwrap();
    assert_eq!((first.health_before, first.health_after), (15, 0));
    assert_eq!(state.health, vec![10, 0, 9]);
    assert_eq!(state.excluded(), vec![1513]);
    state.contact(2, 0, 1001, hit(0)).unwrap().unwrap();
    assert_eq!(state.health, vec![0, 0, 9]);
    assert_eq!(state.removed_ids(), vec![1513, 1514]);
    assert_eq!(state.excluded(), vec![1512, 1513]);
    assert_eq!(state.native_destroyed(31354), vec![0, 1]);
    assert!(state.native_destroyed(31355).is_empty());
    assert_eq!(state.scene_version(), 2);
    state.contact(3, 0, 1002, hit(2)).unwrap().unwrap();
    assert_eq!(state.scene_version(), 3);
    assert_eq!(state.native_destroyed(31355), vec![0]);
}

fn must_reject_unchanged(state: &mut State, shot: u32, shooter: usize, tick: u32, contact: terrain::Hit) {
    let before = state.clone();
    assert!(state.contact(shot, shooter, tick, contact).is_err());
    assert_eq!(*state, before, "failed contact changed HP, events or exclusions");
}

#[test]
fn repeated_shot_dead_target_or_decreasing_tick_is_atomic_failure() {
    let mut state = State::new(catalog());
    state.contact(1, 0, 1002, hit(0)).unwrap().unwrap();
    must_reject_unchanged(&mut state, 1, 0, 1003, hit(1));
    must_reject_unchanged(&mut state, 2, 0, 1003, hit(0));
    must_reject_unchanged(&mut state, 2, 0, 1001, hit(1));
    state.contact(2, 1, 1003, hit(1)).unwrap().unwrap();
    assert_eq!(state.scene_version(), 2);
}

#[test]
fn malformed_known_contact_never_mutates_state() {
    let mut state = State::new(catalog());
    for (shot, shooter, tick) in [(0, 0, 1), (MAX_SHOTS as u32 + 1, 0, 1), (1, CAPACITY, 1), (1, 0, 0)] {
        must_reject_unchanged(&mut state, shot, shooter, tick, hit(0));
    }
    let original = hit(0);
    let mut invalid = Vec::new();
    for t in [f64::NAN, f64::INFINITY, -0.01, 1.01] {
        let mut contact = original; contact.t = t; invalid.push(contact);
    }
    for point in [[f32::NAN, 0.0, 0.0], [0.0, f32::INFINITY, 0.0],
        [terrain::MAX_QUERY_COORDINATE + 1.0, 0.0, 0.0]] {
        let mut contact = original; contact.point = point; invalid.push(contact);
    }
    for normal in [[0.0; 3], [0.0, 2.0, 0.0], [0.0, f32::NAN, 0.0]] {
        let mut contact = original; contact.normal = normal; invalid.push(contact);
    }
    for triangle_id in [88715, 88749, u32::MAX] {
        let mut contact = original; contact.triangle_id = triangle_id; invalid.push(contact);
    }
    let mut contact = original;
    contact.surface = terrain::Surface::StaticObstacle { instance_id: 1512, material_kind: 87 };
    invalid.push(contact);
    for contact in invalid { must_reject_unchanged(&mut state, 1, 0, 1001, contact); }
}

#[test]
fn ground_and_uncatalogued_obstacle_do_not_acquire_fragile_damage() {
    let mut state = State::new(catalog()); let before = state.clone();
    let mut contact = hit(0); contact.surface = terrain::Surface::Ground;
    assert!(state.contact(1, 0, 1001, contact).unwrap().is_none());
    contact.surface = terrain::Surface::StaticObstacle { instance_id: 1500, material_kind: 73 };
    assert!(state.contact(1, 0, 1001, contact).unwrap().is_none());
    assert_eq!(state, before);
}

#[test]
fn full_shot_bound_records_partial_damage_without_implicit_destruction() {
    let mut v = manifest(); v["objects"][0]["health"] = json!(32767);
    let mut state = State::new(Arc::new(parse(&v).unwrap()));
    for shot in 1..=MAX_SHOTS as u32 {
        state.contact(shot, shot as usize % CAPACITY, 1000 + shot, hit(0)).unwrap().unwrap();
    }
    assert_eq!(state.events.len(), MAX_SHOTS);
    assert_eq!(state.health[0], 32767u32 - 30 * MAX_SHOTS as u32);
    assert_eq!(state.scene_version(), 0); assert!(state.excluded().is_empty());
    must_reject_unchanged(&mut state, MAX_SHOTS as u32 + 1, 0, 1100, hit(0));
}

#[test]
fn catalog_map_pins_are_atomic_and_geometry_cannot_cross_maps() {
    let map=MapId::Prohorovka;
    let mut value=manifest();value["map"]=json!(map.asset());
    assert!(parse(&value).is_err());
    value["physics_manifest_sha256"]=json!(map.spec().physics_manifest_sha256);
    assert!(parse(&value).is_err());
    value["projectile_manifest_sha256"]=json!(map.spec().projectile_manifest_sha256);
    let catalog=parse(&value).unwrap();
    assert_eq!(catalog.map,map);
    let wrong=terrain::tests::fixture(0.,1.,2,vec![0.;4]);
    assert!(catalog.bind_geometry(&wrong).is_err());
    assert!(super::super::impact::Trace::new().bind_fragiles(Arc::new(catalog.clone())).is_err());
    assert!(super::super::impact::Trace::new_for_map(map).bind_fragiles(Arc::new(catalog)).is_ok());
}
