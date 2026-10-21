//! MAPS-02: real Prohorovka catalog8/worker9 and a real IPC7 battle scene
//! frame from tools/falling_atom_scene_probe.py (IS-7 driven into pole 50).
//! Read from WOT091_ROOT/local; this is offline evidence, not native acceptance.
use std::path::{Path, PathBuf};
use std::sync::Arc;
use crate::map_profile091::MapId;
use crate::map_drive_worker091::CatalogSpec;
use crate::scene_worker::{self, Scene, SceneSpec};
use super::super::{destructible_wire, fragiles, ram_proof};
use super::validate_catalog_projection;

const RUN: &str = "evidence/20261021-maps02-impl01";
const CATALOG_SHA: &str = "61ce7951421091427a122e1c3875481f4053f3a6b9c910cb98195a644daff6d6";
const WORKER_SHA: &str = "efd831184f87b650479c6dd426e9257b784fc89e70012200b5eb213aee68bf15";
const MANIFEST_SHA: &str = "b119801e374738e366cbe11aa37f5fddf6716ce375849e77f8b23e95dfc3ca8b";

fn local() -> PathBuf {
    Path::new(&std::env::var("WOT091_ROOT").unwrap_or_else(|_| "D:/WoT_9.1_Server".into())).join("local")
}
fn catalog() -> (Arc<fragiles::Catalog>, CatalogSpec) {
    let local = local();
    let path = local.join(RUN).join("catalogs/05_prohorovka/manifest.json");
    let catalog = Arc::new(fragiles::Catalog::load(&local, &path, CATALOG_SHA).unwrap());
    let worker = CatalogSpec::load(&local, &path.parent().unwrap().join(&catalog.worker_file), &catalog.worker_sha256).unwrap();
    (catalog, worker)
}

#[test]
fn prohorovka_catalog8_projects_71_falling_atoms_onto_worker9() {
    let (catalog, worker) = catalog();
    assert_eq!((catalog.version, worker.version(), worker.sha256()), (8, 9, WORKER_SHA));
    validate_catalog_projection(&catalog, &worker, MapId::Prohorovka).unwrap();
    let columns = catalog.objects.iter().filter(|o| o.kind == fragiles::ObjectKind::FallingAtom).count();
    assert_eq!((columns, worker.columns().count(), catalog.objects.len()), (71, 71, 1109));
    // The accepted 1038 non-column objects keep their exact worker projection.
    assert_eq!(worker.entries().iter().filter(|e| e.kind() != "falling_atom").count(), 1038);
    assert!(validate_catalog_projection(&catalog, &worker, MapId::Karelia).is_err());
}

#[test]
fn real_ipc7_column_contact_falls_pole_once_and_publishes_0xa0() {
    let (catalog, _) = catalog();
    let local = local();
    let spec = SceneSpec::load(&local, &local.join(RUN).join("probe02/pole50-candidate-manifest.json"), MANIFEST_SHA).unwrap();
    let raw = std::fs::read(local.join(RUN).join("probe02/pole50-candidate-worker.jsonl")).unwrap();
    let line = raw.split(|b| *b == b'\n').nth(24).unwrap();
    let scene = Scene::new(&spec, &[]).unwrap();
    let frame = scene_worker::response(line, &spec, 1, &scene, 24).unwrap();
    assert_eq!(frame.column_contacts.len(), 1);
    let c = &frame.column_contacts[0];
    assert_eq!((c.object_id, c.slot, c.substep), (50, 0, 5));
    // A worker line that names the pole after it is in the scene is refused.
    assert!(scene_worker::response(line, &spec, 1, &Scene::new(&spec, &[50]).unwrap(), 24).is_err());

    let mut state = fragiles::State::new(catalog.clone());
    state.configure_roster(2).unwrap();
    let mass = ram_proof::Profile::Is7.mass();
    let event = state.column_contact(50, 0, 1024, c.substep, c.point, c.normal, c.velocity, mass).unwrap().unwrap();
    // native index74 (static, OBSERVED equal to native for Prohorovka poles),
    // yaw atan2(0.0914, 7.9669) -> 32, |v| 7.97 -> bucket2.
    assert_eq!(event.fallen_column, Some((74 << 8) | (32 << 2) | 2));
    assert_eq!(state.native_fallen_columns(32639), vec![0x4a82]);
    assert_eq!(state.removed_ids(), vec![50]);
    assert!(state.column_contact(50, 0, 1025, c.substep, c.point, c.normal, c.velocity, mass).unwrap().is_none());
    // The same contact from a light MS-1 at the same speed stays below HP18.
    let mut light = fragiles::State::new(catalog.clone());light.configure_roster(2).unwrap();
    assert!(light.column_contact(50, 0, 1024, c.substep, c.point, c.normal, c.velocity, ram_proof::Profile::Ms1.mass()).unwrap().is_some()
        == fragiles::column_breaks(18, 0., f64::from(ram_proof::Profile::Ms1.mass()),
            c.velocity.iter().map(|v| f64::from(*v) * f64::from(*v)).sum()));

    let area = catalog.chunks().iter().position(|chunk| *chunk == 32639).unwrap();
    let update = destructible_wire::area_update_columns(area, &[0x4a82]).unwrap();
    assert_eq!(update[5], 0xa0);
    assert_eq!(&update[6..], &[6, 1, 0, 0, 0, 0x82, 0x4a, 0x13]);
}
