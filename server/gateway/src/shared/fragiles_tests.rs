//! Domain/parser fixtures, not native identity acceptance. Source resource,
//! span, HP and revision metadata are from the pinned P06O inventory02. Native
//! indices and export/worker hashes below are deliberately synthetic test data.
use super::*;
use serde_json::json;
// Existing wrappers remain bounded to the accepted 20 rounds per MS-1 actor.
const MAX_SHOTS:usize=192;

#[test]
fn selected_ap_damage_and_shot_limit_preserve_partial_compounds_and_neighbors() {
    let mut v=manifest();v["objects"][0]["health"]=json!(600);
    let catalog=Arc::new(parse(&v).unwrap());
    let mut ms1=State::new(catalog.clone());let mut is7=State::new(catalog);
    let light=ms1.contact(1,0,1001,hit(0)).unwrap().unwrap();
    let heavy=is7.contact_for(VehicleKind::Is7,1,0,1001,hit(0)).unwrap().unwrap();
    assert_eq!((light.health_after,heavy.health_after),(570,110));
    assert_eq!(is7.scene_version(),0);assert!(is7.removed_ids().is_empty());
    let heavy2=is7.contact_for(VehicleKind::Is7,2,0,1002,hit(0)).unwrap().unwrap();
    assert_eq!(heavy2.health_after,0);assert_eq!(is7.health,vec![0,15,9]);
    assert_eq!(is7.removed_ids(),vec![1513]);

    let mut v=manifest();v["objects"][0]["health"]=json!(32767);
    let mut is7=State::new(Arc::new(parse(&v).unwrap()));
    for shot in 1..=60 { is7.contact_for(VehicleKind::Is7,shot,0,1000+shot,hit(0)).unwrap().unwrap(); }
    assert_eq!(is7.health[0],32767-60*490);
    let before=is7.clone();assert!(is7.contact_for(VehicleKind::Is7,61,0,1061,hit(0)).is_err());assert_eq!(is7,before);
}

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
fn whole_contact_policy_admits_slow_heavy_impacts_but_not_light_or_tangent_taps() {
    let mut value=contact_manifest();value["version"]=json!(5);value["ram_policy"]=json!(WHOLE_RAM_POLICY);
    value["area_chunks"]=json!([31354,31355]);
    let catalog=Arc::new(parse(&value).unwrap());
    for id in [1513,1529] {
        let mut heavy=State::new(catalog.clone());
        let event=heavy.ram_contact(id,0,1001,1,[0.;3],[0.,0.,1.],[0.,0.,0.8],68190.,"hull".into()).unwrap().unwrap();
        assert_eq!(event.fallen_tree.is_some(),id==1529);assert_eq!(heavy.scene_version(),1);
        assert!(heavy.ram_contact(id,0,1002,1,[0.;3],[0.,0.,1.],[0.,0.,0.8],68190.,"hull".into()).unwrap().is_none());
        for (mass,velocity) in [(4691.,[0.,0.,0.8]),(68190.,[5.,0.,0.]),(68190.,[5.,0.,-2.]),(68190.,[5.,0.,0.1])] {
            let mut state=State::new(catalog.clone());
            assert!(state.ram_contact(id,0,1001,1,[0.;3],[0.,0.,1.],velocity,mass,"hull".into()).unwrap().is_none());
            assert_eq!(state.scene_version(),0);
        }
        let mut legacy=State::new(contact_catalog());
        assert!(legacy.ram_contact(id,0,1001,1,[0.;3],[0.,0.,1.],[0.,0.,0.8],68190.,"hull".into()).unwrap().is_none());
    }
    for policy in [json!(FENCE_RAM_POLICY),json!("historical"),Value::Null] {
        let mut wrong=value.clone();wrong["ram_policy"]=policy;assert!(parse(&wrong).is_err());
    }
    let mut wrong=value;wrong["version"]=json!(4);assert!(parse(&wrong).is_err());
}

#[test]
fn tree_contact_packs_immutable_fallen_value_and_excludes_tree() {
    let mut state=State::new(contact_catalog());
    let event=state.ram_contact(1529,1,1001,2,[1.,2.,3.],[1.,0.,0.],[2.,0.,0.],4691.,"hull".into()).unwrap().unwrap();
    let packed=event.fallen_tree.expect("tree contact must pack native fall");
    // Original decodeFallenTree contract, independent of the Rust encoder:
    // zero (0x8000) constrains the animator upright; 0xc000 permits pi/2.
    let pitch=(packed & 0xffff) as f64 * (2. * std::f64::consts::PI) / 65536. - std::f64::consts::PI;
    assert_eq!(packed & 0xffff,0xc000);
    assert!((pitch-std::f64::consts::FRAC_PI_2).abs()<1e-12);
    assert_eq!(state.native_fallen_trees(31355),vec![packed]);
    assert_eq!(state.removed_ids(),vec![1529]);
    assert_eq!(state.excluded(),vec![1528]);
    assert_eq!(state.scene_version(),1);
    let again=state.ram_contact(1529,1,1002,2,[1.,2.,3.],[1.,0.,0.],[4.,0.,0.],4691.,"hull".into()).unwrap();
    assert!(again.is_none());
    assert_eq!(state.native_fallen_trees(31355),vec![packed]);
}

#[test]
fn tree_fall_pitch_preserves_native_identity_direction_speed_and_energy_gate() {
    // Synthetic domain cases using two indices seen in the native trace.
    // Expected bits follow the original codec, not an encoder round-trip.
    for (native_index,speed,speed_bits) in [(4,2.,1u32),(25,4.,2),(255,8.,3)] {
        for (normal,yaw_bits) in [([0.,0.,1.],32u32),([1.,0.,0.],48)] {
            let mut value=contact_manifest();
            value["objects"][2]["native_index"]=json!(native_index);
            let catalog=Arc::new(parse(&value).unwrap());
            let mut state=State::new(catalog);
            let before=state.clone();
            // 2 kJ cannot remove the tree under the pinned test_lab floor.
            assert!(state.ram_contact(1529,0,1001,1,[0.;3],normal,
                normal.map(|x|x*2.),1000.,"hull".into()).unwrap().is_none());
            assert_eq!(state,before);
            let event=state.ram_contact(1529,0,1002,1,[0.;3],normal,
                normal.map(|x|x*speed),4691.,"hull".into()).unwrap().unwrap();
            let expected=(native_index as u32)<<24|yaw_bits<<18|speed_bits<<16|0xc000;
            assert_eq!(event.fallen_tree,Some(expected));
            assert_eq!(state.native_fallen_trees(31355),vec![expected]);
            assert_eq!(state.native_fragile_values(31355),Vec::<u16>::new());
        }
    }
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

fn movement_manifest(count:u32)->Value {
    let mut value=contact_manifest();value["version"]=json!(3);
    let base=value["objects"][0].clone();
    let rows=(0..count).map(|i|{
        let mut row=base.clone();
        row["object_id"]=json!(i+1);row["instance_id"]=json!(i);
        row["chunk_id"]=json!(((121+(i%128)%12)<<8)|(121+(i%128)/12));
        row["native_index"]=json!(i/128);row["kind"]=json!("movement_fragile");
        row["resource"]=json!("content/fence.model");row["health"]=json!(3);
        row["projectile_first_triangle"]=json!(0);row["projectile_triangle_count"]=json!(0);
        row["physics_first_triangle"]=json!(i*2);row["physics_triangle_count"]=json!(2);row
    }).collect::<Vec<_>>();
    value["objects"]=json!(rows);
    let mut chunks=(0..count.min(128)).map(|i|((121+i%12)<<8)|(121+i/12)).collect::<Vec<_>>();
    chunks.sort_unstable();value["area_chunks"]=json!(chunks);value
}

pub(crate) fn fence_total_manifest()->Value {
    let mut value=contact_manifest();value["version"]=json!(6);
    value["ram_policy"]=json!(FENCE_TOTAL_RAM_POLICY);value["area_chunks"]=json!([31354,31355]);
    value["objects"][1]["kind"]=json!("movement_fragile");
    value["objects"][1]["resource"]=json!(FENCE_TOTAL_RESOURCES[0]);
    value["objects"][1]["projectile_triangle_count"]=json!(0);
    for row in value["objects"].as_array_mut().unwrap(){
        row["ram_response"]=json!(if row["kind"]=="movement_fragile"{"total_linear"}else{"normal_linear"});
    }
    value
}
pub(crate) fn fence_total_catalog()->Arc<Catalog>{Arc::new(parse(&fence_total_manifest()).unwrap())}

#[test]
fn fence_total_domain_schema_requires_exact_version_kind_and_source_discriminator() {
    let valid=fence_total_manifest();let c=parse(&valid).unwrap();
    assert_eq!(c.version,6);
    assert_eq!(c.objects.iter().map(|o|c.ram_response(o)).collect::<Vec<_>>(),
        vec![Some("normal_linear"),Some("total_linear"),Some("normal_linear")]);
    for policy in [json!(WHOLE_RAM_POLICY),json!(FENCE_RAM_POLICY),Value::Null,json!(false),json!("unknown")]{
        let mut v=valid.clone();v["ram_policy"]=policy;assert!(parse(&v).is_err());
    }
    for version in [0,5,7]{let mut v=valid.clone();v["version"]=json!(version);assert!(parse(&v).is_err());}
    for i in 0..3 {
        let mut v=valid.clone();v["objects"][i].as_object_mut().unwrap().remove("ram_response");assert!(parse(&v).is_err());
        for mode in [Value::Null,json!(true),json!(1),json!("unknown"),json!(if i==1{"normal_linear"}else{"total_linear"})]{
            let mut v=valid.clone();v["objects"][i]["ram_response"]=mode;assert!(parse(&v).is_err());
        }
        let mut v=valid.clone();v["objects"][i]["ram_energy_j"]=json!(8000);assert!(parse(&v).is_err());
    }
    for resource in ["content/fence.model","content/GatesAndFences/gaf010_Fence/normal/lod0/gaf010_FenceTile9.model",
        "content/MilitaryEnvironment/mle009_BoxCamouflage/normal/lod0/mle009_BoxCamouflage.model"]{
        let mut v=valid.clone();v["objects"][1]["resource"]=json!(resource);assert!(parse(&v).is_err());
    }
    for resource in FENCE_TOTAL_RESOURCES {let mut v=valid.clone();v["objects"][1]["resource"]=json!(resource);parse(&v).unwrap();}
    for version in 1..=5 {
        let mut v=if version==1{manifest()}else{contact_manifest()};v["version"]=json!(version);
        if version>=3{v["area_chunks"]=json!([31354,31355]);}
        if version>=4{v["ram_policy"]=json!(if version==5{WHOLE_RAM_POLICY}else{FENCE_RAM_POLICY});}
        let old=parse(&v).unwrap();assert!(old.objects.iter().all(|o|old.ram_response(o).is_none()));
        v["objects"][0]["ram_response"]=json!("normal_linear");assert!(parse(&v).is_err());
    }
}

#[test]
fn fence_total_admission_uses_full_velocity_but_requires_real_incoming_hull_contact() {
    let catalog=Arc::new(parse(&fence_total_manifest()).unwrap());
    for (mass,velocity,expected) in [(4691.,[0.1,0.,3.],true),(68190.,[0.1,0.,0.8],true),
        (4691.,[0.1,0.,0.8],false),(68190.,[0.,0.,6.],false),(68190.,[-0.1,0.,6.],false),
        (68190.,[0.,0.,0.],false)]{
        let mut state=State::new(catalog.clone());
        let event=state.ram_contact(1514,0,1001,1,[0.;3],[1.,0.,0.],velocity,mass,"hull".into()).unwrap();
        assert_eq!(event.is_some(),expected);assert_eq!(state.scene_version(),u32::from(expected));
        if expected {assert_eq!(state.native_fragile_values(31354),vec![1<<8]);assert_eq!(state.removed_ids(),vec![1514]);
            let before=state.clone();assert!(state.ram_contact(1514,1,1001,2,[0.;3],[1.,0.,0.],velocity,mass,"hull".into()).unwrap().is_none());assert_eq!(state,before);}
        for id in [1513,1529] {let mut normal=State::new(catalog.clone());
            assert!(normal.ram_contact(id,0,1001,1,[0.;3],[1.,0.,0.],velocity,mass,"hull".into()).unwrap().is_none());}
    }
    let mut wheel=State::new(catalog.clone());let before=wheel.clone();
    assert!(wheel.ram_contact(1514,0,1001,1,[0.;3],[1.,0.,0.],[6.,0.,6.],68190.,"wheel".into()).unwrap().is_none());assert_eq!(wheel,before);
    for velocity in [[f32::NAN,0.,3.],[f32::INFINITY,0.,3.],[0.,0.,f32::from_bits(25f32.to_bits()+1)]]{
        let mut state=State::new(catalog.clone());let before=state.clone();
        assert!(state.ram_contact(1514,0,1001,1,[0.;3],[0.,0.,1.],velocity,4691.,"hull".into()).is_err());assert_eq!(state,before);
    }
}

#[test]
fn fence_total_exact_energy_incoming_and_speed_boundaries_use_f64_components() {
    let catalog=Arc::new(parse(&fence_total_manifest()).unwrap());
    for (speed,expected) in [(f32::from_bits(4f32.to_bits()-1),false),(4.,true),(f32::from_bits(4f32.to_bits()+1),true)]{
        let mut state=State::new(catalog.clone());
        assert_eq!(state.ram_contact(1514,0,1001,1,[0.;3],[0.6,0.,0.8],[speed,0.,0.],1000.,"hull".into()).unwrap().is_some(),expected);
    }
    for (closing,expected) in [(f32::from_bits(0.1f32.to_bits()-1),false),(0.1,true),(f32::from_bits(0.1f32.to_bits()+1),true)]{
        let mut state=State::new(catalog.clone());
        assert_eq!(state.ram_contact(1514,0,1001,1,[0.;3],[1.,0.,0.],[closing,0.,3.],4691.,"hull".into()).unwrap().is_some(),expected);
    }
    for velocity in [[0.,0.,25.],[15.,0.,20.]]{let mut state=State::new(catalog.clone());
        assert!(state.ram_contact(1514,0,1001,1,[0.;3],[0.,0.,1.],velocity,4691.,"hull".into()).unwrap().is_some());}
}

#[test]
fn fence_total_retains_normal_tree_fragile_and_projectile_semantics() {
    let newer=fence_total_manifest();let mut older=newer.clone();older["version"]=json!(5);older["ram_policy"]=json!(WHOLE_RAM_POLICY);
    for row in older["objects"].as_array_mut().unwrap(){row.as_object_mut().unwrap().remove("ram_response");}
    let old=Arc::new(parse(&older).unwrap());let new=Arc::new(parse(&newer).unwrap());assert_eq!(old.objects,new.objects);
    for id in [1513,1529]{for (mass,v,n) in [(68190.,[0.,0.,0.8],[0.,0.,1.]),(4691.,[0.,0.,0.8],[0.,0.,1.]),
        (4691.,[3.,0.,5.],[0.6,0.,0.8]),(1000.,[0.,0.,4.],[0.,0.,1.])]{
        let mut a=State::new(old.clone());let mut b=State::new(new.clone());
        assert_eq!(a.ram_contact(id,0,1001,1,[0.;3],n,v,mass,"hull".into()).unwrap(),b.ram_contact(id,0,1001,1,[0.;3],n,v,mass,"hull".into()).unwrap());
        assert_eq!(a.removed_ids(),b.removed_ids());assert_eq!(a.native_fallen_trees(31355),b.native_fallen_trees(31355));
    }}
    let mut partial=newer;partial["objects"][0]["health"]=json!(32);let mut state=State::new(Arc::new(parse(&partial).unwrap()));
    assert_eq!(state.contact(1,0,1001,hit(0)).unwrap().unwrap().health_after,2);assert_eq!(state.scene_version(),0);
    assert!(state.contact(2,0,1002,hit(1)).unwrap().is_none());assert_eq!(state.scene_version(),0);
    assert_eq!(state.contact(3,0,1003,hit(0)).unwrap().unwrap().health_after,0);assert_eq!(state.removed_ids(),vec![1513]);
}
pub(crate) fn movement_catalog(count:u32)->Arc<Catalog>{Arc::new(parse(&movement_manifest(count)).unwrap())}

#[test]
fn fence_response_domain_requires_explicit_policy_and_preserves_native_rows() {
    let old=movement_manifest(1038);
    let mut next=old.clone();next["version"]=json!(4);next["ram_policy"]=json!(FENCE_RAM_POLICY);
    let before=parse(&old).unwrap();let after=parse(&next).unwrap();
    assert_eq!(after.version,4);assert_eq!(after.objects,before.objects);
    assert_eq!(after.chunks(),before.chunks());
    for invalid in [Value::Null,json!(false),json!("historical"),json!("test_lab-fence-energy-v2")] {
        let mut bad=next.clone();bad["ram_policy"]=invalid;assert!(parse(&bad).is_err());
    }
    let mut missing=next.clone();missing.as_object_mut().unwrap().remove("ram_policy");assert!(parse(&missing).is_err());
    let mut legacy=old;legacy["ram_policy"]=json!(FENCE_RAM_POLICY);assert!(parse(&legacy).is_err());
    let mut oversized=movement_manifest(2049);oversized["version"]=json!(4);oversized["ram_policy"]=json!(FENCE_RAM_POLICY);
    assert!(parse(&oversized).is_err());
}

#[test]
fn fence_response_threshold_uses_exact_components_at_adjacent_float_speeds() {
    let mut value=movement_manifest(1);value["version"]=json!(4);value["ram_policy"]=json!(FENCE_RAM_POLICY);
    let catalog=Arc::new(parse(&value).unwrap());
    // Exactly 4 m/s at 1000 kg is 8000 J. Adjacent representable inputs
    // must not cross the hard boundary because C# and Rust rounded differently.
    for (speed,breaks) in [(f32::from_bits(4f32.to_bits()-1),false),(4.,true),
        (f32::from_bits(4f32.to_bits()+1),true)] {
        let mut state=State::new(catalog.clone());
        let event=state.ram_contact(1,0,1,1,[0.;3],[0.,0.,1.],[0.,0.,speed],1000.,"hull".into()).unwrap();
        assert_eq!(event.is_some(),breaks);assert_eq!(state.scene_version(),u32::from(breaks));
    }
    // Oblique f32 components lie just above the exact double threshold;
    // one representable velocity step down must still remain below it.
    for (speed,breaks) in [(f32::from_bits(5f32.to_bits()-1),false),(5.,true)] {
        let mut state=State::new(catalog.clone());
        assert_eq!(state.ram_contact(1,0,1,1,[0.;3],[0.6,0.,0.8],[0.,0.,speed],1000.,"hull".into()).unwrap().is_some(),breaks);
    }
}

#[test]
fn movement_catalog_is_versioned_complete_and_native_area_bounded() {
    for kind in [Value::Null,json!(1),json!(true)] {
        let mut legacy_contact=contact_manifest();legacy_contact["objects"][0]["kind"]=kind;
        assert!(parse(&legacy_contact).is_err());
    }
    for count in [1038,2048] {
        let value=movement_manifest(count);let catalog=parse(&value).unwrap();
        assert_eq!(catalog.version,3);assert_eq!(catalog.objects.len(),count as usize);
        assert_eq!(catalog.chunks().len(),128);
        let mut old=value.clone();old["version"]=json!(2);old.as_object_mut().unwrap().remove("area_chunks");
        assert!(parse(&old).is_err());
    }
    assert!(parse(&movement_manifest(2049)).is_err());
    for mode in 0..7 {
        let mut value=movement_manifest(1);
        match mode {
            0=>value["objects"][0]["projectile_triangle_count"]=json!(1),
            1=>value["objects"][0]["material_kind"]=json!(71),
            2=>value["area_chunks"]=json!([]),
            3=>value["area_chunks"]=json!([31097,31097]),
            4=>value["area_chunks"]=json!([0]),
            5=>value["area_chunks"]=json!([31098]),
            _=>value["objects"][0]["physics_triangle_count"]=json!(0),
        }
        assert!(parse(&value).is_err(),"invalid movement profile {mode}");
    }
    // Explicit empty controller areas support passive catalog acquisition;
    // they never fabricate an object/native index.
    let mut probe=movement_manifest(1);probe["area_chunks"]=json!([31097,31098]);
    assert_eq!(parse(&probe).unwrap().chunks(),vec![31097,31098]);
}

#[test]
fn movement_fragiles_ram_independently_and_never_become_projectile_surfaces() {
    let catalog=Arc::new(parse(&movement_manifest(60)).unwrap());
    let mut state=State::new(catalog);
    // Half the energy gate: the near tap preserves physical presence.
    assert!(state.ram_contact(1,0,1,1,[0.;3],[1.,0.,0.],[2.,0.,0.],1000.,"hull".into()).unwrap().is_none());
    for id in 1..=50 {
        let contact=state.ram_contact(id,0,id+1,1,[0.;3],[1.,0.,0.],[4.,0.,0.],1000.,"hull".into()).unwrap().unwrap();
        assert_eq!(contact.scene_after,id);assert!(contact.fallen_tree.is_none());
    }
    assert_eq!(state.removed_ids(),(1..=50).collect::<Vec<_>>());
    assert_eq!(state.excluded(),(0..50).collect::<Vec<_>>());
    assert!(state.projectile_excluded().is_empty());
    assert_eq!(state.native_fragile_values(31097),vec![0]);
    assert!(state.native_fallen_trees(31097).is_empty());
    let before=state.clone();
    assert!(state.ram_contact(1,0,52,1,[0.;3],[1.,0.,0.],[4.,0.,0.],1000.,"hull".into()).unwrap().is_none());
    assert_eq!(state,before);
    let mut forged=hit(0);forged.surface=terrain::Surface::StaticObstacle{instance_id:50,material_kind:73};
    assert!(state.contact(1,0,53,forged).unwrap().is_none());
    assert_eq!(state,before);
}
