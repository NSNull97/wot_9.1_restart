//! Explicit, hash-pinned stock MS-1 surface binding. No armor/damage semantics.
use std::{fs, io::{self, Read}, path::Path};
use serde_json::Value;
use sha2::{Digest, Sha256};
use super::{collision::{Mesh, Triangle}, model::{bad, Actor}, pose};

pub const SOURCE_REVISION: &str = "ms1-717:b21e25230f1e5d35d9ae95a713622dfa9606a1b916a22bd0350a73c5f3fcce86";
pub const BUNDLE_SHA256: &str = "e975427c05d40fc2850ad3829165f287cef9655092032c8e515b597a7a262e00";
const MAX_BYTES: u64 = 512 * 1024;
const NAMES: [&str; 3] = ["Hull", "Turret_01", "Gun_02"];
const COUNTS: [(usize, usize); 3] = [(436, 258), (311, 218), (146, 90)];

#[derive(Clone, Debug)]
struct Component { vertices: Vec<[f32; 3]>, triangles: Vec<Triangle> }
#[derive(Clone, Debug)]
pub struct Bundle {
    components: Vec<Component>,
    hull: [f32; 3], turret: [f32; 3], gun: [f32; 3],
}
fn fields(value: &Value, keys: &[&str]) -> io::Result<()> {
    crate::map_drive_worker091::fields(value, keys).map(|_| ())
}
fn vector(value: &Value) -> io::Result<[f32; 3]> {
    let row = value.as_array().filter(|v| v.len() == 3).ok_or_else(bad)?;
    let mut out = [0.; 3];
    for i in 0..3 { let x = row[i].as_f64().ok_or_else(bad)?;
        if !x.is_finite() || x.abs() > 10. { return Err(bad()); } out[i] = x as f32; }
    Ok(out)
}
fn text(value: &Value) -> io::Result<String> {
    let s = value.as_str().filter(|s| !s.is_empty() && s.len() <= 128).ok_or_else(bad)?;
    Ok(s.into())
}
fn uint(value: &Value) -> io::Result<u32> { u32::try_from(value.as_u64().ok_or_else(bad)?).map_err(|_| bad()) }
fn non_reparse(path: &Path) -> io::Result<()> {
    for p in path.ancestors() {
        let m = fs::symlink_metadata(p)?;
        if m.file_type().is_symlink() { return Err(bad()); }
        #[cfg(windows)] { use std::os::windows::fs::MetadataExt;
            if m.file_attributes() & 0x400 != 0 { return Err(bad()); } }
    } Ok(())
}
impl Bundle {
    pub fn load(local_root: &Path, path: &Path) -> io::Result<Self> {
        if !path.is_absolute() { return Err(bad()); }
        non_reparse(local_root)?; non_reparse(path)?;
        let root = local_root.canonicalize()?; let path = path.canonicalize()?;
        if !path.starts_with(&root) || path == root { return Err(bad()); }
        let file = fs::File::open(path)?;
        if !file.metadata()?.is_file() || file.metadata()?.len() > MAX_BYTES { return Err(bad()); }
        let mut raw = Vec::new(); file.take(MAX_BYTES + 1).read_to_end(&mut raw)?;
        Self::from_bytes(&raw)
    }
    fn from_bytes(raw: &[u8]) -> io::Result<Self> {
        // Exact approved export only: untrusted/duplicate-key JSON cannot reach
        // deserialization by supplying its own expected digest at startup.
        if raw.is_empty() || raw.len() as u64 > MAX_BYTES
            || format!("{:x}", Sha256::digest(raw)) != BUNDLE_SHA256 { return Err(bad()); }
        let value: Value = serde_json::from_slice(raw).map_err(|_| bad())?;
        Self::from_value(&value)
    }
    fn from_value(v: &Value) -> io::Result<Self> {
        fields(v, &["schema", "vehicle_compact_id", "gun_compact_id", "source_revision", "components",
            "hull_position", "turret_position", "gun_position"])?;
        if v["schema"] != "ms1-collision.v1" || v["vehicle_compact_id"] != 3329
            || v["gun_compact_id"] != 5892 || v["source_revision"] != SOURCE_REVISION { return Err(bad()); }
        let hull = vector(&v["hull_position"])?; let turret = vector(&v["turret_position"])?;
        let gun = vector(&v["gun_position"])?;
        if hull != [-0.012, 0.894681, -0.055245] || turret != [0.013778, 0.421721, 0.08902]
            || gun != [-0.238144, 0.234668, 0.410043] { return Err(bad()); }
        let rows = v["components"].as_array().filter(|a| a.len() == 3).ok_or_else(bad)?;
        let mut components = Vec::new();
        for (i, row) in rows.iter().enumerate() {
            fields(row, &["name", "vertices", "triangles"])?;
            if row["name"] != NAMES[i] { return Err(bad()); }
            let vr = row["vertices"].as_array().filter(|a| a.len() == COUNTS[i].0).ok_or_else(bad)?;
            let tr = row["triangles"].as_array().filter(|a| a.len() == COUNTS[i].1).ok_or_else(bad)?;
            let vertices = vr.iter().map(vector).collect::<io::Result<Vec<_>>>()?;
            let mut triangles = Vec::new();
            for (index, t) in tr.iter().enumerate() {
                fields(t, &["triangle_id", "a", "b", "c", "mesh", "group", "material"])?;
                let triangle = Triangle { triangle_id: uint(&t["triangle_id"])?, a: uint(&t["a"])?,
                    b: uint(&t["b"])?, c: uint(&t["c"])?, mesh: text(&t["mesh"])?,
                    group: text(&t["group"])?, material: text(&t["material"])? };
                if triangle.triangle_id != (i * 100000 + index) as u32 || triangle.mesh != NAMES[i] { return Err(bad()); }
                triangles.push(triangle);
            }
            Mesh::new(vertices.clone(), triangles.clone(), SOURCE_REVISION, "component-local-v1")?;
            components.push(Component { vertices, triangles });
        }
        Ok(Self { components, hull, turret, gun })
    }
    pub fn world_mesh(&self, actor: &Actor, slot: usize, tick: u32) -> io::Result<Mesh> {
        if slot >= 2 || tick < 1000 || actor.position.iter().any(|x| !x.is_finite() || x.abs() > 2000.)
            || actor.direction.iter().any(|x| !x.is_finite() || x.abs() > std::f32::consts::PI)
            || !actor.aim.yaw.is_finite() || !actor.aim.pitch.is_finite() { return Err(bad()); }
        let mut vertices = Vec::new(); let mut triangles = Vec::new();
        for (i, component) in self.components.iter().enumerate() {
            let base = vertices.len() as u32;
            for &v in &component.vertices {
                let local = self.component_point(i, v, actor.aim.yaw, actor.aim.pitch);
                let rotated = pose::rotate(local, actor.direction);
                vertices.push(std::array::from_fn(|axis| actor.position[axis] + rotated[axis]));
            }
            for triangle in &component.triangles {
                let mut t = triangle.clone(); t.a += base; t.b += base; t.c += base; triangles.push(t);
            }
        }
        // Hash the precise authoritative transform facts, including aim, so
        // the identity stays unambiguous even within one server tick.
        let mut hash = Sha256::new();
        for v in actor.position.into_iter().chain(actor.direction).chain([actor.aim.yaw, actor.aim.pitch]) {
            hash.update(v.to_le_bytes());
        }
        Mesh::new(vertices, triangles, SOURCE_REVISION,
            format!("pose-v1:{slot}:{tick}:{:x}", hash.finalize()))
    }
    fn component_point(&self, index: usize, vertex: [f32; 3], yaw: f32, pitch: f32) -> [f32; 3] {
        let add = |a: [f32; 3], b: [f32; 3]| std::array::from_fn(|i| a[i] + b[i]);
        match index {
            0 => add(self.hull, vertex),
            1 => add(add(self.hull, self.turret), pose::rotate(vertex, [yaw, 0., 0.])),
            2 => add(add(self.hull, self.turret), pose::rotate(
                add(self.gun, pose::rotate(vertex, [0., pitch, 0.])), [yaw, 0., 0.])),
            _ => unreachable!("validated component count"),
        }
    }
}

#[cfg(test)]
pub(super) mod tests {
    use super::*;
    pub fn bundle() -> Bundle {
        // Explicit pinned local fixture generated by tools/ms1_collision_bundle.py.
        // Missing fixture is a failure, never a silently skipped native check.
        let root = std::env::var("WOT091_ROOT").unwrap_or_else(|_| "D:/WoT_9.1_Server".into());
        Bundle::load(&Path::new(&root).join("local"), &Path::new(&root)
            .join("local/evidence/20261010-p06i-native-collision-01/ms1-collision.json")).unwrap()
    }
    #[test] fn measured_component_origins_match_native_inverse_matrices() {
        let b = bundle();
        for (i, expected) in [(0, [-0.012, 0.8946809769, -0.055245]),
            (1, [0.001778, 1.3164019585, 0.033774998]),
            (2, [-0.2363659889, 1.5510699749, 0.4438180029])] {
            let p = b.component_point(i, [0.; 3], 0., 0.);
            assert!(p.iter().zip(expected).all(|(a, b)| (a-b).abs() < 2e-7));
        }
    }
    #[test] fn original_native_local_hit_distances_match_pinned_triangles() {
        let b = bundle();
        // Native #717 hitTester.localHitTest, oracle01: local rays avoid shared edges.
        for (i, start, end, expected) in [
            (0, [-4., -0.25, 0.15], [4., -0.25, 0.15], vec![3.4615545273, 4.5625119209]),
            (1, [0.1, 0.25, -4.], [0.1, 0.25, 4.], vec![3.4700529575, 4.4535346031]),
            (1, [-4., -0.25, 0.15], [4., -0.25, 0.15], vec![]),
            (2, [0.1, 0.05, -4.], [0.1, 0.05, 4.], vec![3.7258970737, 4.0326094627, 4.0775485039]),
        ] {
            let c = &b.components[i]; let mesh = Mesh::new(c.vertices.clone(), c.triangles.clone(), SOURCE_REVISION, "native-local").unwrap();
            let hits = super::super::collision::query(&mesh, start, end).unwrap();
            assert_eq!(hits.len(), expected.len());
            for (hit, distance) in hits.iter().zip(expected) { assert!((hit.t*8. - distance).abs() < 2e-6); }
        }
    }
    #[test] fn gun_forward_chain_matches_independent_nonzero_native_inverse() {
        let b = bundle(); let pitch = 0.002493327483534813;
        let origin = [0.23636598885059357, -1.5521717071533203, -0.43994927406311035];
        let axes = [[1.,0.,0.], [0.,0.9999969005584717,-0.0024933249223977327],
            [0.,0.0024933249223977327,0.9999969005584717]];
        for vertex in [[0.;3], [0.2,0.3,0.4], [-0.15,-0.11,0.73]] {
            let p = b.component_point(2, vertex, 0., pitch);
            for i in 0..3 {
                let native = origin[i]+axes[0][i]*p[0]+axes[1][i]*p[1]+axes[2][i]*p[2];
                assert!((native-vertex[i]).abs()<3e-7);
            }
        }
    }
    #[test] fn malformed_bundle_hash_path_and_bounds_fail_closed() {
        assert!(Bundle::from_bytes(b"{}").is_err());
        assert!(Bundle::from_bytes(&vec![0; MAX_BYTES as usize+1]).is_err());
        assert!(Bundle::load(Path::new("."), Path::new("relative.json")).is_err());
        let b = bundle(); let now = std::time::Instant::now(); let mut actor = super::super::model::tests::world(now).actors[0].clone();
        assert!(b.world_mesh(&actor, 2, 1000).is_err());
        actor.position[0] = f32::NAN; assert!(b.world_mesh(&actor, 0, 1000).is_err());
    }
}
