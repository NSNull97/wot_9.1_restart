//! Explicit original #717 map identities, read from the compiled-in map
//! registry (`server/contracts/map_registry.json`), not from enum arms.
//! Asset filename prefixes are not IDs: original arena_defs/_list_.xml assigns
//! Prohorovka arena type 4, not 5. Every registry entry pins its exported
//! terrain/physics/projectile sources by SHA256 (tools/map_package.py).
//!
//! The registry is part of the reviewed source. It is validated once on first
//! use; an invalid registry cannot pass the unit tests below, so first use
//! failing is a build defect and panics instead of serving with partial maps.
use std::{io, sync::OnceLock};
use serde_json::Value;

const REGISTRY_JSON: &str = include_str!("../../../contracts/map_registry.json");
/// Registry ordinals of the two accepted maps. Their position is checked.
const KARELIA_ASSET: &str = "01_karelia";
const PROHOROVKA_ASSET: &str = "05_prohorovka";
const MAX_MAPS: usize = 64;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub struct MapId(u8);

impl Default for MapId {
    fn default() -> Self { Self::Karelia }
}

#[allow(non_upper_case_globals)]
impl MapId {
    pub const Karelia: MapId = MapId(0);
    pub const Prohorovka: MapId = MapId(1);

    pub fn from_asset(asset: &str) -> io::Result<Self> {
        registry().iter().position(|profile| profile.asset == asset).map(|index| MapId(index as u8))
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "unsupported pinned map asset"))
    }
    pub fn from_arena_type_id(id: i32) -> io::Result<Self> {
        registry().iter().position(|profile| profile.arena_type_id == id).map(|index| MapId(index as u8))
            .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "unsupported pinned arena type"))
    }
    pub fn all() -> impl Iterator<Item = MapId> { (0..registry().len()).map(|index| MapId(index as u8)) }
    pub fn asset(self) -> &'static str { self.spec().asset }
    pub fn spec(self) -> &'static MapProfile { &registry()[self.0 as usize] }
    pub fn arena_type_id(self) -> i32 { self.spec().arena_type_id }
}

/// Immutable source admission profile of one exported original #717 map.
#[derive(Debug, PartialEq)]
pub struct MapProfile {
    pub asset: &'static str,
    pub arena_type_id: i32,
    pub terrain_manifest_sha256: &'static str,
    pub terrain_vertices_sha256: &'static str,
    pub terrain_triangles_sha256: &'static str,
    pub terrain_revision: &'static str,
    pub world_revision: &'static str,
    /// Square original terrain grid: samples per side, world origin (both axes), metres per cell.
    pub grid_width: usize,
    pub grid_origin: f64,
    pub grid_spacing: f64,
    /// Original space chunk bounds (minX, maxX, minZ, maxZ); destructible chunk IDs use +127.
    pub chunk_bounds: [i32; 4],
    pub physics_manifest_sha256: &'static str,
    pub physics_triangle_count: usize,
    pub instance_count: usize,
    pub projectile_manifest_sha256: &'static str,
    pub projectile_manifest_bytes: usize,
    pub projectile_vertex_count: usize,
    pub projectile_triangle_count: usize,
    pub projectile_vertices_sha256: &'static str,
    pub projectile_triangles_sha256: &'static str,
    pub projectile_flags_sha256: &'static str,
    pub projectile_manifest_relative: &'static str,
    /// Client arena definition: ctf team1/team2 base XZ and round length.
    pub ctf_bases: Option<[[f32; 2]; 2]>,
    pub round_length_s: u32,
    /// Accepted before the registry (legacy evidence paths and budgets).
    pub accepted_legacy: bool,
}

impl MapProfile {
    /// Original destructible chunk ID (x+127)<<8|(z+127) inside this space.
    pub fn contains_chunk_id(&self, chunk_id: u16) -> bool {
        let [min_x, max_x, min_z, max_z] = self.chunk_bounds;
        let (x, z) = (i32::from(chunk_id >> 8) - 127, i32::from(chunk_id & 255) - 127);
        (min_x..=max_x).contains(&x) && (min_z..=max_z).contains(&z)
    }
    pub fn chunk_count(&self) -> usize {
        let [min_x, max_x, min_z, max_z] = self.chunk_bounds;
        ((max_x - min_x + 1) * (max_z - min_z + 1)) as usize
    }
}

fn registry() -> &'static [MapProfile] {
    static REGISTRY: OnceLock<Vec<MapProfile>> = OnceLock::new();
    REGISTRY.get_or_init(|| parse_registry(REGISTRY_JSON).expect("compiled map registry is valid (unit tested)"))
}

fn bad(reason: &str) -> io::Error { io::Error::new(io::ErrorKind::InvalidData, format!("map registry: {reason}")) }
fn leak(value: String) -> &'static str { Box::leak(value.into_boxed_str()) }
fn fields(value: &Value, expected: &[&str]) -> io::Result<()> {
    let object = value.as_object().ok_or_else(|| bad("object"))?;
    if object.len() != expected.len() || expected.iter().any(|key| !object.contains_key(*key)) { return Err(bad("exact fields")); }
    Ok(())
}
fn hash(value: &Value) -> io::Result<&'static str> {
    let text = value.as_str().filter(|s| s.len() == 64 && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)))
        .ok_or_else(|| bad("lowercase SHA256"))?;
    Ok(leak(text.into()))
}
fn count(value: &Value, max: u64) -> io::Result<usize> {
    value.as_u64().filter(|n| (1..=max).contains(n)).map(|n| n as usize).ok_or_else(|| bad("count bound"))
}
fn int(value: &Value, lo: i64, hi: i64) -> io::Result<i64> {
    value.as_i64().filter(|n| (lo..=hi).contains(n)).ok_or_else(|| bad("integer bound"))
}
fn real(value: &Value, lo: f64, hi: f64) -> io::Result<f64> {
    value.as_f64().filter(|n| n.is_finite() && (lo..=hi).contains(n)).ok_or_else(|| bad("number bound"))
}
fn asset_name(value: &Value) -> io::Result<&'static str> {
    let text = value.as_str().ok_or_else(|| bad("asset"))?;
    let bytes = text.as_bytes();
    if bytes.len() < 4 || bytes.len() > 43 || !bytes[..2].iter().all(u8::is_ascii_digit) || bytes[2] != b'_'
        || !bytes[3..].iter().all(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || *b == b'_') { return Err(bad("asset name")); }
    Ok(leak(text.into()))
}
fn relative(value: &Value) -> io::Result<&'static str> {
    let text = value.as_str().ok_or_else(|| bad("relative path"))?;
    if text.is_empty() || text.len() > 240 || text.starts_with('/') || text.contains('\\') || text.contains(':')
        || text.split('/').any(|part| part.is_empty() || part == "." || part == "..") { return Err(bad("relative path")); }
    Ok(leak(text.into()))
}

fn parse_registry(raw: &str) -> io::Result<Vec<MapProfile>> {
    let value: Value = serde_json::from_str(raw).map_err(|_| bad("JSON"))?;
    fields(&value, &["version", "kind", "maps"])?;
    if value["version"] != 1 || value["kind"] != "wot091_server_map_registry" { return Err(bad("identity")); }
    let rows = value["maps"].as_array().filter(|rows| (2..=MAX_MAPS).contains(&rows.len())).ok_or_else(|| bad("map count"))?;
    let mut maps: Vec<MapProfile> = Vec::with_capacity(rows.len());
    for row in rows {
        fields(row, &["asset", "arena_type_id", "revision_name", "grid", "chunk_bounds", "terrain", "physics",
            "projectile", "arena", "source"])?;
        let asset = asset_name(&row["asset"])?;
        let name = row["revision_name"].as_str().filter(|s| (1..=40).contains(&s.len()) && s.bytes().all(|b| b.is_ascii_lowercase() || b == b'_'))
            .ok_or_else(|| bad("revision name"))?;
        let grid = &row["grid"]; fields(grid, &["width", "origin", "spacing"])?;
        let width = count(&grid["width"], 1025)?;
        let origin = real(&grid["origin"], -1600., 0.)?;
        let spacing = real(&grid["spacing"], 0.5, 10.)?;
        let bounds = &row["chunk_bounds"]; fields(bounds, &["minX", "maxX", "minY", "maxY"])?;
        let chunk_bounds = [int(&bounds["minX"], -64, 0)? as i32, int(&bounds["maxX"], 0, 64)? as i32,
            int(&bounds["minY"], -64, 0)? as i32, int(&bounds["maxY"], 0, 64)? as i32];
        // Terrain must lie inside the space and be an original 100 m chunk multiple.
        let cells = (width - 1) as f64 * spacing;
        if width < 3 || (100. / spacing).fract() != 0. || (cells / 100.).fract() != 0. || (origin / 100.).fract() != 0.
            || origin < f64::from(chunk_bounds[0]) * 100. || origin < f64::from(chunk_bounds[2]) * 100.
            || origin + cells > f64::from(chunk_bounds[1] + 1) * 100. || origin + cells > f64::from(chunk_bounds[3] + 1) * 100. {
            return Err(bad("terrain grid outside original chunk space"));
        }
        let terrain = &row["terrain"]; fields(terrain, &["manifest_sha256", "vertices_sha256", "triangles_sha256"])?;
        let physics = &row["physics"]; fields(physics, &["manifest_sha256", "triangle_count", "instance_count"])?;
        let projectile = &row["projectile"];
        fields(projectile, &["manifest_sha256", "manifest_bytes", "vertex_count", "triangle_count", "vertices_sha256",
            "triangles_sha256", "flags_sha256", "manifest_relative"])?;
        let arena = &row["arena"]; fields(arena, &["round_length_s", "ctf_bases"])?;
        let ctf_bases = match &arena["ctf_bases"] {
            Value::Null => None,
            Value::Array(pair) if pair.len() == 2 => {
                let mut out = [[0f32; 2]; 2];
                for (team, point) in pair.iter().enumerate() {
                    let xz = point.as_array().filter(|xz| xz.len() == 2).ok_or_else(|| bad("base point"))?;
                    for axis in 0..2 { out[team][axis] = real(&xz[axis], -2000., 2000.)? as f32; }
                }
                Some(out)
            }
            _ => return Err(bad("ctf bases")),
        };
        let source = &row["source"];
        let accepted_legacy = source == "legacy-accepted-evidence";
        if !accepted_legacy {
            fields(source, &["package_relative", "package_sha256"])?;
            relative(&source["package_relative"])?; hash(&source["package_sha256"])?;
        }
        let terrain_manifest = hash(&terrain["manifest_sha256"])?;
        let projectile_manifest = hash(&projectile["manifest_sha256"])?;
        let profile = MapProfile {
            asset, arena_type_id: int(&row["arena_type_id"], 0, 1024)? as i32,
            terrain_manifest_sha256: terrain_manifest,
            terrain_vertices_sha256: hash(&terrain["vertices_sha256"])?,
            terrain_triangles_sha256: hash(&terrain["triangles_sha256"])?,
            terrain_revision: leak(format!("{name}-terrain-717:{terrain_manifest}")),
            world_revision: leak(format!("{name}-projectile-world-717:{terrain_manifest}:{projectile_manifest}")),
            grid_width: width, grid_origin: origin, grid_spacing: spacing, chunk_bounds,
            physics_manifest_sha256: hash(&physics["manifest_sha256"])?,
            physics_triangle_count: count(&physics["triangle_count"], 3_000_000)?,
            instance_count: count(&physics["instance_count"], 20_000)?,
            projectile_manifest_sha256: projectile_manifest,
            projectile_manifest_bytes: count(&projectile["manifest_bytes"], 64 * 1024 * 1024)?,
            projectile_vertex_count: count(&projectile["vertex_count"], 9_000_000)?,
            projectile_triangle_count: count(&projectile["triangle_count"], 3_000_000)?,
            projectile_vertices_sha256: hash(&projectile["vertices_sha256"])?,
            projectile_triangles_sha256: hash(&projectile["triangles_sha256"])?,
            projectile_flags_sha256: hash(&projectile["flags_sha256"])?,
            projectile_manifest_relative: relative(&projectile["manifest_relative"])?,
            ctf_bases, round_length_s: count(&arena["round_length_s"], 3600)? as u32, accepted_legacy,
        };
        if profile.projectile_vertex_count != profile.projectile_triangle_count * 3
            || maps.iter().any(|old| old.asset == profile.asset || old.arena_type_id == profile.arena_type_id
                || old.terrain_revision == profile.terrain_revision) { return Err(bad("duplicate or inconsistent map")); }
        maps.push(profile);
    }
    if maps[0].asset != KARELIA_ASSET || maps[1].asset != PROHOROVKA_ASSET || !maps[0].accepted_legacy || !maps[1].accepted_legacy
        || maps[2..].iter().any(|map| map.accepted_legacy) { return Err(bad("accepted map ordinals")); }
    Ok(maps)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn original_map_identity_is_explicit_and_never_inferred_from_filename_prefix() {
        assert_eq!(MapId::from_asset("01_karelia").unwrap().arena_type_id(), 1);
        assert_eq!(MapId::from_asset("05_prohorovka").unwrap().arena_type_id(), 4);
        for value in ["", "prohorovka", "5", "04_prohorovka", "05_prohorovka/../01_karelia"] {
            assert!(MapId::from_asset(value).is_err());
        }
        assert_eq!(MapId::from_arena_type_id(4).unwrap(), MapId::Prohorovka);
        assert!(MapId::from_arena_type_id(5).is_err() || MapId::from_arena_type_id(5).unwrap().asset() != "05_prohorovka");
    }

    /// Byte-for-byte the constants this registry replaced (main 2b835b7).
    #[test]
    fn accepted_maps_keep_their_previous_pins_exactly() {
        let k = MapId::Karelia.spec();
        assert_eq!((k.asset, k.arena_type_id), ("01_karelia", 1));
        assert_eq!(k.terrain_manifest_sha256, "5e23f58d4e9d78398bd9cd861f6bc09a038cce7e8f7b311731e50c30bcc958f9");
        assert_eq!(k.terrain_vertices_sha256, "dc0752ceaaa6b469b36062a5c0a1d397edfa7a39815bf0d19d1290d0c8a08a92");
        assert_eq!(k.terrain_triangles_sha256, "27ba25b1f81a37cb678584a898b0efed2b497ef1fc26ecb342ff852f72ec479c");
        assert_eq!(k.terrain_revision, "karelia-terrain-717:5e23f58d4e9d78398bd9cd861f6bc09a038cce7e8f7b311731e50c30bcc958f9");
        assert_eq!(k.world_revision, "karelia-projectile-world-717:5e23f58d4e9d78398bd9cd861f6bc09a038cce7e8f7b311731e50c30bcc958f9:ccd28d8e3320d041e569e217a8c20e0285db0459bc2ef447c5bd95dd97d80cea");
        assert_eq!(k.physics_manifest_sha256, "ea6ef22aed0fdd4e4826500c280a616737f8990ce7ab7cd808b9382227ec5ffd");
        assert_eq!((k.physics_triangle_count, k.instance_count), (335551, 2918));
        assert_eq!(k.projectile_manifest_sha256, "ccd28d8e3320d041e569e217a8c20e0285db0459bc2ef447c5bd95dd97d80cea");
        assert_eq!((k.projectile_manifest_bytes, k.projectile_vertex_count, k.projectile_triangle_count), (2190312, 538095, 179365));
        assert_eq!(k.projectile_vertices_sha256, "8900634a1fd9dacbebe785d6c0289e2102f0811df7a677be473e2d0ea607db26");
        assert_eq!(k.projectile_triangles_sha256, "06f3dcd079e6de79b4f653b4c6a23865b92d20449aab7480bbc8d6d2c8b85304");
        assert_eq!(k.projectile_flags_sha256, "9c601f8bc5463af3dc7107d1592d984eeaffd6cb453f338b34cffdf5dc02d1a1");
        assert_eq!(k.projectile_manifest_relative, "evidence/20261010-p06m-terrain-impact-01/projectile-obstacles01/01_karelia/manifest.json");
        let p = MapId::Prohorovka.spec();
        assert_eq!((p.asset, p.arena_type_id), ("05_prohorovka", 4));
        assert_eq!(p.terrain_manifest_sha256, "d598db1dafee75e56e71a3453c1bc9824e86f32280df56854780127ceedad984");
        assert_eq!(p.terrain_vertices_sha256, "4038d2967c2b8f66affdd729cc475050b1b9cadec3c1f1d187f0c99114d3fcbf");
        assert_eq!(p.terrain_triangles_sha256, "27ba25b1f81a37cb678584a898b0efed2b497ef1fc26ecb342ff852f72ec479c");
        assert_eq!(p.terrain_revision, "prohorovka-terrain-717:d598db1dafee75e56e71a3453c1bc9824e86f32280df56854780127ceedad984");
        assert_eq!(p.world_revision, "prohorovka-projectile-world-717:d598db1dafee75e56e71a3453c1bc9824e86f32280df56854780127ceedad984:3db1ad3859ae2f5fed678ac5f148005cff38a3c915bb33dde3303de22e22bef7");
        assert_eq!(p.physics_manifest_sha256, "9d358a48da303abaf15572f478dddc16971864960d9341943cc6d207b32b3265");
        assert_eq!((p.physics_triangle_count, p.instance_count), (428597, 3904));
        assert_eq!(p.projectile_manifest_sha256, "3db1ad3859ae2f5fed678ac5f148005cff38a3c915bb33dde3303de22e22bef7");
        assert_eq!((p.projectile_manifest_bytes, p.projectile_vertex_count, p.projectile_triangle_count), (3004854, 856050, 285350));
        assert_eq!(p.projectile_vertices_sha256, "e764c437c1f7676ec7916daba59e88f8ecea4fac558653d1fb3eb6fb3856de16");
        assert_eq!(p.projectile_triangles_sha256, "c954bbc7bc893d80d26d720cb6be09e4059047a614ba6288af56c11803648a31");
        assert_eq!(p.projectile_flags_sha256, "088d726205104d0da6a79b7a956f1e1281cd516c0b8a5248f7110dd8205f6bc5");
        assert_eq!(p.projectile_manifest_relative, "evidence/20261012-p06p-prohorovka-01/import/projectile-obstacles01/05_prohorovka/manifest.json");
        for map in [k, p] {
            assert_eq!((map.grid_width, map.grid_origin, map.grid_spacing, map.chunk_bounds), (769, -600., 1.5625, [-6, 5, -6, 5]));
            assert_eq!(map.chunk_count(), 144);
            assert!(map.contains_chunk_id(121 << 8 | 132) && !map.contains_chunk_id(120 << 8 | 127) && !map.contains_chunk_id(127 << 8 | 133));
        }
        // lifecycle::Rules::prohorovka() bases are exactly the client ctf bases.
        assert_eq!(p.ctf_bases, Some([[-125.100021, 448.300110], [51.599991, -447.]]));
        assert_eq!(p.round_length_s, 900);
    }

    #[test]
    fn registry_rejects_malformed_or_ambiguous_entries() {
        let good: Value = serde_json::from_str(REGISTRY_JSON).unwrap();
        assert_eq!(parse_registry(REGISTRY_JSON).unwrap().len(), good["maps"].as_array().unwrap().len());
        let mut cases = Vec::new();
        let mut swap = good.clone(); swap["maps"].as_array_mut().unwrap().swap(0, 1); cases.push(swap);
        let mut duplicate = good.clone(); let first = duplicate["maps"][0].clone(); duplicate["maps"].as_array_mut().unwrap().push(first); cases.push(duplicate);
        for (key, value) in [("asset", serde_json::json!("../01_karelia")), ("arena_type_id", serde_json::json!(-1)),
            ("revision_name", serde_json::json!("Karelia")), ("source", serde_json::json!("guessed"))] {
            let mut bad = good.clone(); bad["maps"][0][key] = value; cases.push(bad);
        }
        let mut grid = good.clone(); grid["maps"][0]["grid"]["width"] = serde_json::json!(770); cases.push(grid);
        let mut outside = good.clone(); outside["maps"][0]["grid"]["origin"] = serde_json::json!(-700.0); cases.push(outside);
        let mut hash = good.clone(); hash["maps"][0]["terrain"]["manifest_sha256"] = serde_json::json!("A".repeat(64)); cases.push(hash);
        let mut extra = good.clone(); extra["maps"][0]["guess"] = serde_json::json!(true); cases.push(extra);
        let mut path = good.clone(); path["maps"][0]["projectile"]["manifest_relative"] = serde_json::json!("../x.json"); cases.push(path);
        for case in cases { assert!(parse_registry(&case.to_string()).is_err(), "{case}"); }
    }
}
