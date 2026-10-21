//! MAPS-01: a registry map other than the two accepted ones loads through the
//! same pinned readers. Real local exports (tools/map_package.py package and
//! tools/compound_destructible_catalog.py --static-index catalog) are read from
//! WOT091_ROOT/local; this does not establish native acceptance.
use std::{fs, path::{Path, PathBuf}, sync::Arc};
use sha2::{Digest, Sha256};
use serde_json::Value;
use crate::map_profile091::MapId;
use crate::map_drive_worker091::CatalogSpec;
use super::super::{fragiles, lifecycle::Rules, obstacles::Obstacles, terrain::{Surface, Terrain}};
use super::validate_catalog_projection;

fn local() -> PathBuf {
    Path::new(&std::env::var("WOT091_ROOT").unwrap_or_else(|_| "D:/WoT_9.1_Server".into())).join("local")
}
fn package(map: MapId) -> PathBuf {
    local().join(map.spec().projectile_manifest_relative).parent().unwrap().parent().unwrap().to_path_buf()
}
/// Catalog directory next to the package directory: <run>/catalogs/<map>/.
fn catalog_path(map: MapId) -> PathBuf {
    package(map).parent().unwrap().parent().unwrap().join("catalogs").join(map.asset()).join("manifest.json")
}
fn catalog_from(path: &Path, raw: &[u8]) -> std::io::Result<fragiles::Catalog> {
    fs::write(path, raw).unwrap();
    fragiles::Catalog::load(&local(), path, &format!("{:x}", Sha256::digest(raw)))
}

#[test]
fn malinovka_registry_loads_real_terrain_obstacles_static_catalog_and_rules() {
    let map = MapId::from_asset("02_malinovka").unwrap();
    assert_eq!((map.arena_type_id(), map.spec().accepted_legacy), (2, false));
    let local = local();
    let terrain_manifest = package(map).join("terrain/manifest.json");
    let terrain = Terrain::load_for(map, &local, &terrain_manifest).unwrap();
    assert_eq!(terrain.source_revision(), map.spec().terrain_revision);
    for other in [MapId::Karelia, MapId::Prohorovka] { assert!(Terrain::load_for(other, &local, &terrain_manifest).is_err()); }
    let projectile = local.join(map.spec().projectile_manifest_relative);
    let obstacles = Arc::new(Obstacles::load_for(map, &local, &projectile).unwrap());
    assert!(Obstacles::load_for(MapId::Prohorovka, &local, &projectile).is_err());
    assert!(super::super::terrain::tests::actual_prohorovka().clone().with_obstacles(obstacles.clone()).is_err());
    let world = terrain.with_obstacles(obstacles).unwrap();
    assert_eq!(world.source_revision(), map.spec().world_revision);
    let bases = map.spec().ctf_bases.unwrap();
    for [x, z] in bases {
        let hit = world.nearest([x, 1000., z], [x, -1000., z]).unwrap().unwrap();
        assert!(hit.normal[1] > 0. && matches!(hit.surface, Surface::Ground | Surface::StaticObstacle { .. }));
    }
    // Lifecycle rules: the client ctf bases and round length of this map.
    let rules = Rules::for_map(map).unwrap();
    assert_eq!((rules.battle_ms, rules.bases[0].xz, rules.bases[1].xz), (900_000, bases[0], bases[1]));
    assert_eq!(Rules::for_map(MapId::Prohorovka).unwrap(), Rules::prohorovka());

    let path = catalog_path(map);
    let raw = fs::read(&path).unwrap();
    let catalog = fragiles::Catalog::load(&local, &path, &format!("{:x}", Sha256::digest(&raw))).unwrap();
    assert_eq!((catalog.map, catalog.version, catalog.objects.len()), (map, 7, 1385));
    assert!(catalog.objects.iter().all(|o| map.spec().contains_chunk_id(o.chunk_id)));
    assert!(catalog.chunks().len() > 128 && catalog.chunks().len() <= 144);
    catalog.bind_geometry(&world).unwrap();
    let worker_path = path.with_file_name(&catalog.worker_file);
    let worker = CatalogSpec::load(&local, &worker_path, &catalog.worker_sha256).unwrap();
    validate_catalog_projection(&catalog, &worker, map).unwrap();
    assert!(validate_catalog_projection(&catalog, &worker, MapId::Prohorovka).is_err());
}

#[test]
fn static_index_provenance_is_exact_and_never_mixed_with_native_exports() {
    let map = MapId::from_asset("02_malinovka").unwrap();
    let good: Value = serde_json::from_slice(&fs::read(catalog_path(map)).unwrap()).unwrap();
    let dir = local().join("tests").join(format!("maps01-static-{}-{}", std::process::id(),
        std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()));
    fs::create_dir_all(&dir).unwrap();
    let path = dir.join("manifest.json");
    assert!(catalog_from(&path, &serde_json::to_vec(&good).unwrap()).is_ok());
    let mut cases = Vec::new();
    let mut both = good.clone(); both["native_exports_sha256"] = serde_json::json!(["a".repeat(64)]); cases.push(both);
    let mut rule = good.clone(); rule["native_index_source"]["rule"] = "static-chunk-order-v2".into(); cases.push(rule);
    let mut class = good.clone(); class["native_index_source"]["classification"] = "VERIFIED".into(); cases.push(class);
    let mut hash = good.clone(); hash["native_index_source"]["static_index_sha256"] = "x".into(); cases.push(hash);
    let mut extra = good.clone(); extra["native_index_source"]["note"] = "guess".into(); cases.push(extra);
    let mut old = good.clone(); old["version"] = 6.into(); cases.push(old);
    let mut outside = good.clone(); outside["objects"][0]["chunk_id"] = serde_json::json!((120u32 << 8) | 127); cases.push(outside);
    let mut wrong_map = good.clone(); wrong_map["map"] = "05_prohorovka".into(); cases.push(wrong_map);
    for case in cases { assert!(catalog_from(&path, &serde_json::to_vec(&case).unwrap()).is_err(), "{case}"); }
    fs::remove_dir_all(&dir).unwrap();
}
