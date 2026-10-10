//! Explicit, hash-pinned stock MS-1 surface binding. No armor/damage semantics.
use std::{fs, io::{self, Read}, path::Path};
use serde_json::Value;
use sha2::{Digest, Sha256};
use super::{collision::{Mesh, Triangle}, model::{bad, Actor, Contact}, pose, materials::{self, Catalog}};

pub const SOURCE_REVISION: &str = "ms1-717:b21e25230f1e5d35d9ae95a713622dfa9606a1b916a22bd0350a73c5f3fcce86";
pub const BUNDLE_SHA256: &str = "26a6714ea562bbc81b64835a8a9495ab9105ae648894b724ea94467d9d7771c2";
const MAX_BYTES: u64 = 512 * 1024;
const NAMES: [&str; 3] = ["Hull", "Turret_01", "Gun_02"];
const COUNTS: [(usize, usize); 3] = [(436, 258), (311, 218), (146, 90)];
// Original #717 hitTester.bbox, also rechecked against hash-pinned collision
// .visual boundingBox fields. These are NOT primitive vertex extrema: the
// turret's native minimum Y is -.364419, while its mesh minimum is near zero.
// Visual SHA256 in Hull/Turret_01/Gun_02 order:
// 247d9128d0246ccaf888184a56878f0f52770af92ec6afb9d51894be0a2977ed
// 6a7ee9e7d5c4d92791066bf952d8f848b20fc8edb97c6866b5c32d6920ef4a49
// 6e21999574feec23e641afb1e9c218560a9d7a68eb85e1c472cb6a47c7046014
const NATIVE_BOUNDS: [[[f32; 3]; 2]; 3] = [
    [[-0.8080300092697144, -0.6045309901237488, -2.392045021057129],
     [0.8321380019187927, 0.5576249957084656, 1.619907021522522]],
    [[-0.5180299878120422, -0.36441901326179504, -0.6558679938316345],
     [0.5145779848098755, 0.7172920107841492, 0.5534660220146179]],
    [[-0.15181100368499756, -0.11368700116872787, -0.27410298585891724],
     [0.15446600317955017, 0.10141299664974213, 0.7375900149345398]],
];
// Allows f32 pose/mesh rounding at the native AABB boundary, not hitbox growth.
const CONTACT_TOLERANCE: f64 = 0.0002;

/// Component-local line through a measured contact, before native quantization.
/// This has no outcome, health or native method/component number semantics.
#[derive(Clone, Debug, PartialEq)]
pub struct ImpactSegment {
    pub component: materials::Component,
    pub bounds: [[f32; 3]; 2],
    pub start: [f32; 3],
    pub end: [f32; 3],
}

fn subtract(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    std::array::from_fn(|i| a[i] - b[i])
}

fn transform_revision(position: [f32; 3], direction: [f32; 3], aim: [f32; 2], slot: usize, tick: u32) -> String {
    let mut hash = Sha256::new();
    for value in position.into_iter().chain(direction).chain(aim) { hash.update(value.to_le_bytes()); }
    format!("pose-v1:{slot}:{tick}:{:x}", hash.finalize())
}

fn clipped_line(point: [f32; 3], direction: [f32; 3], bounds: [[f32; 3]; 2], minimum: Option<f64>)
    -> io::Result<([f32; 3], [f32; 3])> {
    if point.into_iter().chain(direction).chain(bounds.into_iter().flatten())
        .any(|x| !x.is_finite()) { return Err(bad()); }
    let length = direction.iter().map(|&x| f64::from(x).powi(2)).sum::<f64>().sqrt();
    if length < 1e-6 { return Err(bad()); }
    let unit: [f64; 3] = direction.map(|x| f64::from(x) / length);
    let point = point.map(f64::from);
    let mut enter = f64::NEG_INFINITY; let mut leave = f64::INFINITY;
    for axis in 0..3 {
        let low = f64::from(bounds[0][axis]); let high = f64::from(bounds[1][axis]);
        if low >= high { return Err(bad()); }
        if unit[axis] == 0. {
            if point[axis] < low || point[axis] > high { return Err(bad()); }
        } else {
            let a = (low - point[axis]) / unit[axis];
            let b = (high - point[axis]) / unit[axis];
            enter = enter.max(a.min(b)); leave = leave.min(a.max(b));
        }
    }
    if let Some(minimum) = minimum {
        if !minimum.is_finite() { return Err(bad()); }
        enter = enter.max(minimum);
    }
    if !enter.is_finite() || !leave.is_finite() || leave-enter < 1e-6
        || enter > CONTACT_TOLERANCE || leave < -CONTACT_TOLERANCE { return Err(bad()); }
    // Intersect the whole directed line, not each coordinate independently.
    // Extend through the component exit even when the simulation segment stops
    // at its first surface, but do not move before a segment starting inside
    // the AABB. The native decoder extends this segment by 1%.
    let at = |t: f64| std::array::from_fn(|i| (point[i] + unit[i] * t) as f32);
    Ok((at(enter), at(leave)))
}

#[derive(Clone, Debug)]
struct Component { vertices: Vec<[f32; 3]>, triangles: Vec<Triangle> }
#[derive(Clone, Debug)]
pub struct Bundle {
    components: Vec<Component>,
    hull: [f32; 3], turret: [f32; 3], gun: [f32; 3],
    materials: Catalog,
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
        fields(&value, &["schema", "source_revision", "source_pins", "geometry", "materials"])?;
        if value["schema"] != "ms1-contact.v1" || !value["source_pins"].is_object() { return Err(bad()); }
        let materials = Catalog::from_value(&value["source_revision"], &value["materials"])?;
        Self::from_value(&value["geometry"], materials)
    }
    fn from_value(v: &Value, materials: Catalog) -> io::Result<Self> {
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
                materials.lookup(&triangle.mesh, &triangle.material)?;
                triangles.push(triangle);
            }
            Mesh::new(vertices.clone(), triangles.clone(), SOURCE_REVISION, "component-local-v1")?;
            components.push(Component { vertices, triangles });
        }
        Ok(Self { components, hull, turret, gun, materials })
    }
    pub fn materials(&self) -> &Catalog { &self.materials }
    /// Recover a local segment from the authoritative contact's exact target
    /// pose. Attached live hull/turret/gun only; detached/dead component model
    /// transforms are not represented by Contact and must not call this route.
    pub fn impact_segment(&self, contact: &Contact) -> io::Result<ImpactSegment> {
        if contact.geometry_revision != SOURCE_REVISION || contact.target_slot >= 2 || contact.tick < 1000
            || contact.target_position.iter().any(|x| !x.is_finite() || x.abs() > 2000.)
            || contact.target_direction.iter().chain(contact.target_aim.iter())
                .any(|x| !x.is_finite() || x.abs() > std::f32::consts::PI)
            || contact.segment_start.iter().chain(contact.segment_end.iter()).chain(contact.endpoint.iter())
                .any(|x| !x.is_finite() || x.abs() > 100000.)
            || !contact.triangle.t.is_finite() || !(0.0..=1.0).contains(&contact.triangle.t) {
            return Err(bad());
        }
        if contact.transform_revision != transform_revision(contact.target_position, contact.target_direction,
            contact.target_aim, contact.target_slot, contact.tick) { return Err(bad()); }
        let facts = self.materials.lookup(&contact.triangle.mesh, &contact.triangle.material)?;
        if facts != contact.material_facts { return Err(bad()); }
        let component = facts.component;
        let index = match component { materials::Component::Hull => 0,
            materials::Component::Turret01 => 1, materials::Component::Gun02 => 2 };
        let triangle_index = contact.triangle.triangle_id.checked_sub(index as u32 * 100000).ok_or_else(bad)?;
        let source = self.components[index].triangles.get(triangle_index as usize).ok_or_else(bad)?;
        if source.mesh != contact.triangle.mesh || source.group != contact.triangle.group
            || source.material != contact.triangle.material { return Err(bad()); }
        let delta = subtract(contact.segment_end, contact.segment_start);
        if (0..3).any(|i| (f64::from(contact.segment_start[i] + contact.triangle.t * delta[i])
            - f64::from(contact.endpoint[i])).abs() > CONTACT_TOLERANCE) { return Err(bad()); }
        let chassis_point = pose::inverse_rotate(subtract(contact.endpoint, contact.target_position), contact.target_direction);
        let chassis_direction = pose::inverse_rotate(delta, contact.target_direction);
        let point = self.inverse_component_point(index, chassis_point, contact.target_aim);
        let direction = self.inverse_component_direction(index, chassis_direction, contact.target_aim);
        let bounds = NATIVE_BOUNDS[index];
        let length = direction.iter().map(|&x| f64::from(x).powi(2)).sum::<f64>().sqrt();
        let minimum = -f64::from(contact.triangle.t) * length;
        let (start, end) = clipped_line(point, direction, bounds, Some(minimum))?;
        // A line continued behind the current simulation segment must not
        // select another, earlier surface (e.g. a projectile starting inside a
        // component). Verify the first surface before any wire quantization.
        let extended_start = std::array::from_fn(|i| start[i] - 0.01 * (end[i] - start[i]));
        let extended_end = std::array::from_fn(|i| end[i] + 0.01 * (end[i] - start[i]));
        let part = &self.components[index];
        let mesh = Mesh::new(part.vertices.clone(), part.triangles.clone(), SOURCE_REVISION, "impact-component-local-v1")?;
        let hits = super::collision::query(&mesh, extended_start, extended_end)?;
        let first = hits.first().ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "impact segment has no local surface"))?;
        if (0..3).any(|i| (f64::from(extended_start[i] + first.t * (extended_end[i] - extended_start[i]))
            - f64::from(point[i])).abs() > CONTACT_TOLERANCE) {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "impact segment first surface differs from contact"));
        }
        Ok(ImpactSegment { component, bounds, start, end })
    }
    fn inverse_component_point(&self, index: usize, point: [f32; 3], aim: [f32; 2]) -> [f32; 3] {
        let point = subtract(point, self.hull);
        if index == 0 { return point; }
        let point = pose::inverse_rotate(subtract(point, self.turret), [aim[0], 0., 0.]);
        if index == 1 { return point; }
        pose::inverse_rotate(subtract(point, self.gun), [0., aim[1], 0.])
    }
    fn inverse_component_direction(&self, index: usize, vector: [f32; 3], aim: [f32; 2]) -> [f32; 3] {
        if index == 0 { return vector; }
        let vector = pose::inverse_rotate(vector, [aim[0], 0., 0.]);
        if index == 1 { return vector; }
        pose::inverse_rotate(vector, [0., aim[1], 0.])
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
        Mesh::new(vertices, triangles, SOURCE_REVISION,
            transform_revision(actor.position, actor.direction, [actor.aim.yaw, actor.aim.pitch], slot, tick))
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
    fn contact_for(b: &Bundle, index: usize, start: [f32; 3], end: [f32; 3],
        direction: [f32; 3], aim: [f32; 2]) -> Contact {
        let mut actor = super::super::model::tests::world(std::time::Instant::now()).actors[0].clone();
        actor.position = [37., 21., -105.]; actor.direction = direction;
        actor.aim.yaw = aim[0]; actor.aim.pitch = aim[1];
        let world = |p| {
            let rotated = pose::rotate(b.component_point(index, p, aim[0], aim[1]), direction);
            std::array::from_fn(|i| actor.position[i] + rotated[i])
        };
        let segment_start = world(start); let segment_end = world(end);
        let mesh = b.world_mesh(&actor, 1, 1000).unwrap();
        let triangle = super::super::collision::query(&mesh, segment_start, segment_end).unwrap()
            .into_iter().find(|hit| hit.mesh == NAMES[index]).unwrap();
        let endpoint = std::array::from_fn(|i| segment_start[i] + triangle.t * (segment_end[i] - segment_start[i]));
        let material_facts = b.materials.lookup(&triangle.mesh, &triangle.material).unwrap();
        Contact { shot: 1, target_slot: 1, tick: 1000, segment_start, segment_end, segment_seconds: 0.1,
            endpoint, target_position: actor.position, target_direction: direction, target_aim: aim,
            triangle, geometry_revision: SOURCE_REVISION.into(), transform_revision: mesh.transform_revision().into(), material_facts }
    }
    #[test] fn impact_bounds_equal_original_native_records_not_vertex_extrema() {
        let root = std::env::var("WOT091_ROOT").unwrap_or_else(|_| "D:/WoT_9.1_Server".into());
        let file = fs::File::open(Path::new(&root).join(
            "local/evidence/20261010-p06i-native-collision-01/runtime-a-oracle01/native-27076-1791611380111.jsonl")).unwrap();
        let mut raw = Vec::new(); file.take(141176).read_to_end(&mut raw).unwrap();
        assert_eq!(raw.len(), 141176);
        let rows: Vec<&str> = std::str::from_utf8(&raw).unwrap().lines()
            .filter(|line| line.contains("\"event\": \"shared_collision_local_oracle\"")).collect();
        assert_eq!(rows.len(), 3);
        for (index, (line, pin)) in rows.iter().zip([
            "25bd5a90dc48de5c2554f33e8574b234c8a0732873ccbaf63bf903d43e7eaed8",
            "7673f6ee36cc305d9f112a3549e8bc00e89c321104e37a2f763267485494dbaf",
            "9d4fcfc2a3b514e432cb36acdf8842ebdc5cc2c54a478cec618a94d777090467",
        ]).enumerate() {
            assert_eq!(format!("{:x}", Sha256::digest(line.as_bytes())), pin);
            let row: Value = serde_json::from_str(line).unwrap();
            assert_eq!(row["component"], NAMES[index]);
            assert_eq!(row["observer_mutated_gameplay"], false);
            for edge in 0..2 { for axis in 0..3 {
                assert_eq!(NATIVE_BOUNDS[index][edge][axis].to_bits(),
                    (row["native_bounds"][edge][axis].as_f64().unwrap() as f32).to_bits());
            } }
        }
        assert!(bundle().components[1].vertices.iter().all(|v| v[1] > -0.00001));
        assert!(NATIVE_BOUNDS[1][0][1] < -0.36);
    }
    #[test] fn impact_segments_preserve_real_surface_through_mixed_pose_and_component_aim() {
        let b = bundle();
        for (index, start, end) in [(0, [-4., -0.25, 0.15], [4., -0.25, 0.15]),
            (1, [0.1, 0.25, -4.], [0.1, 0.25, 4.]), (2, [0.1, 0.05, -4.], [0.1, 0.05, 4.])] {
            for (pose, aim) in [([0.; 3], [0.; 2]), ([0.7, -0.3, 0.2], [1.1, -0.19]),
                ([-2.1, 0.25, -0.15], [-0.9, 0.24])] {
                for reverse in [false, true] {
                    let (start, end) = if reverse { (end, start) } else { (start, end) };
                    let contact = contact_for(&b, index, start, end, pose, aim);
                    let segment = b.impact_segment(&contact).unwrap();
                    assert_eq!(segment.component.name(), NAMES[index]);
                    assert_eq!(segment.bounds, NATIVE_BOUNDS[index]);
                    let local_hit = b.inverse_component_point(index,
                        pose::inverse_rotate(subtract(contact.endpoint, contact.target_position), pose), aim);
                    let delta = subtract(segment.end, segment.start);
                    let largest = (0..3).max_by(|&a, &c| delta[a].abs().partial_cmp(&delta[c].abs()).unwrap()).unwrap();
                    let t = (local_hit[largest] - segment.start[largest]) / delta[largest];
                    assert!((-0.0002..=1.0002).contains(&t));
                    for axis in 0..3 {
                        assert!((segment.start[axis] + t * delta[axis] - local_hit[axis]).abs() < 2e-5);
                        for edge in [segment.start, segment.end] {
                            assert!(edge[axis] >= segment.bounds[0][axis] - 1e-6);
                            assert!(edge[axis] <= segment.bounds[1][axis] + 1e-6);
                        }
                    }
                    let forward_start = b.component_point(index, segment.start, aim[0], aim[1]);
                    let roundtrip = b.inverse_component_point(index, forward_start, aim);
                    for axis in 0..3 { assert!((roundtrip[axis]-segment.start[axis]).abs() < 4e-7); }
                }
            }
        }
    }
    #[test] fn impact_line_clipping_keeps_direction_instead_of_clamping_each_coordinate() {
        let bounds = [[-1.; 3], [1.; 3]];
        let (start, end) = clipped_line([0., 0., 0.], [2., 1., 0.5], bounds, None).unwrap();
        assert_eq!(start, [-1., -0.5, -0.25]); assert_eq!(end, [1., 0.5, 0.25]);
        let (start, end) = clipped_line([0.; 3], [1., 0., 0.], bounds, Some(-0.25)).unwrap();
        assert_eq!(start, [-0.25, 0., 0.]); assert_eq!(end, [1., 0., 0.]);
        assert!(clipped_line([0.; 3], [0.; 3], bounds, None).is_err());
        assert!(clipped_line([2., 0., 0.], [0., 1., 0.], bounds, None).is_err());
        assert!(clipped_line([0.; 3], [f32::NAN, 0., 0.], bounds, None).is_err());
        assert!(clipped_line([0.; 3], [1., 0., 0.], [[1.; 3], [-1.; 3]], None).is_err());
        assert!(clipped_line([2., 2., 0.], [1., -1., 0.], bounds, None).is_err());
        assert!(clipped_line([0.; 3], [1., 0., 0.], bounds, Some(f64::NAN)).is_err());
    }
    #[test] fn impact_invalid_or_mismatched_contact_fails_without_output() {
        let b = bundle(); let base = contact_for(&b, 0, [-4., -0.25, 0.15], [4., -0.25, 0.15], [0.; 3], [0.; 2]);
        let mut c = base.clone(); c.segment_end = c.segment_start; assert!(b.impact_segment(&c).is_err());
        let mut c = base.clone(); c.endpoint[0] += 0.1; assert!(b.impact_segment(&c).is_err());
        let mut c = base.clone(); c.target_direction[1] = f32::NAN; assert!(b.impact_segment(&c).is_err());
        let mut c = base.clone(); c.target_aim[0] = f32::INFINITY; assert!(b.impact_segment(&c).is_err());
        let mut c = base.clone(); c.triangle.triangle_id = 200000; assert!(b.impact_segment(&c).is_err());
        let mut c = base.clone(); c.triangle.mesh = "Chassis".into(); assert!(b.impact_segment(&c).is_err());
        let mut c = base.clone(); c.material_facts.component = materials::Component::Gun02; assert!(b.impact_segment(&c).is_err());
        let mut c = base.clone(); c.transform_revision = "unverified".into(); assert!(b.impact_segment(&c).is_err());
        let mut c = base; c.geometry_revision = "unverified".into(); assert!(b.impact_segment(&c).is_err());
    }
    #[test] fn impact_start_inside_component_does_not_restore_earlier_entry_surface() {
        let b = bundle();
        let contact = contact_for(&b, 0, [0., -0.25, 0.15], [4., -0.25, 0.15], [0.; 3], [0.; 2]);
        let segment = b.impact_segment(&contact).unwrap();
        assert!(segment.start[0].abs() < 2e-5);
        assert!(segment.end[0] > 0.8);
        let part = &b.components[0];
        let mesh = Mesh::new(part.vertices.clone(), part.triangles.clone(), SOURCE_REVISION, "local-start-inside").unwrap();
        let hit = super::super::collision::query(&mesh, segment.start, segment.end).unwrap().remove(0);
        assert_eq!(hit.triangle_id, contact.triangle.triangle_id);
    }
    pub fn invalid_material_bundle() -> Bundle {
        let mut b = bundle(); b.materials = Catalog::empty_for_test(); b
    }
    pub fn bundle() -> Bundle {
        // Explicit pinned contact bundle; nested P06I geometry is unchanged.
        // Missing fixture is a failure, never a silently skipped native check.
        let root = std::env::var("WOT091_ROOT").unwrap_or_else(|_| "D:/WoT_9.1_Server".into());
        Bundle::load(&Path::new(&root).join("local"), &Path::new(&root)
            .join("local/evidence/20261010-p06j-contact-materials-01/ms1-contact.json")).unwrap()
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
    #[test] fn contact_bundle_keeps_all_accepted_geometry_values_unchanged() {
        let root = std::env::var("WOT091_ROOT").unwrap_or_else(|_| "D:/WoT_9.1_Server".into());
        let root = Path::new(&root).join("local/evidence");
        let old = fs::read(root.join("20261010-p06i-native-collision-01/ms1-collision.json")).unwrap();
        assert_eq!(format!("{:x}",Sha256::digest(&old)),"e975427c05d40fc2850ad3829165f287cef9655092032c8e515b597a7a262e00");
        let new = fs::read(root.join("20261010-p06j-contact-materials-01/ms1-contact.json")).unwrap();
        let value: Value = serde_json::from_slice(&new).unwrap();
        assert_eq!(value["geometry"],serde_json::from_slice::<Value>(&old).unwrap());
        let b = bundle();
        for c in &b.components { for t in &c.triangles { b.materials.lookup(&t.mesh,&t.material).unwrap(); } }
        assert!(Bundle::from_bytes(&old).is_err()); // old EXE + old bundle is the explicit rollback pair
        let mut changed = new; changed.push(b' '); assert!(Bundle::from_bytes(&changed).is_err());
        let mut unknown = value["geometry"].clone(); unknown["components"][0]["triangles"][0]["material"] = Value::String("unknown".into());
        assert!(Bundle::from_value(&unknown,b.materials).is_err());
    }
    #[test] fn accepted_native_segments_recompute_identical_nearest_contacts() {
        // Offline regression over the accepted P06I prefix; this is not a new
        // native shot, nor an assertion about the later StorageFull tail.
        let root = std::env::var("WOT091_ROOT").unwrap_or_else(|_| "D:/WoT_9.1_Server".into());
        let file = fs::File::open(Path::new(&root).join(
            "local/evidence/20261010-p06i-native-collision-01/gateway-native01.stdout.log")).unwrap();
        let mut raw = Vec::new(); file.take(1515254).read_to_end(&mut raw).unwrap();
        assert_eq!(raw.len(),1515254);
        assert_eq!(format!("{:x}",Sha256::digest(&raw)),"1436384426c2bcc4e8142764bfe7ba83849d3800039a4c452d28b58059d3a0dd");
        let text = std::str::from_utf8(&raw).unwrap();
        let contacts: Vec<Value> = text.lines().filter_map(|s| s.strip_prefix("SHARED_GEOMETRIC_CONTACT "))
            .map(|s| serde_json::from_str(s).unwrap()).collect();
        assert_eq!(contacts.len(),9);
        let b = bundle();
        let v3 = |v: &Value| -> [f32;3] { std::array::from_fn(|i| v[i].as_f64().unwrap() as f32) };
        let mut target = super::super::model::tests::world(std::time::Instant::now()).actors[0].clone();
        for contact in contacts {
            target.position = v3(&contact["target_position"]); target.direction = v3(&contact["target_direction"]);
            target.aim.yaw = contact["target_aim"][0].as_f64().unwrap() as f32;
            target.aim.pitch = contact["target_aim"][1].as_f64().unwrap() as f32;
            let mesh = b.world_mesh(&target,contact["target_slot"].as_u64().unwrap() as usize,
                contact["tick"].as_u64().unwrap() as u32).unwrap();
            assert_eq!(mesh.transform_revision(),contact["transform_revision"].as_str().unwrap());
            let start = v3(&contact["segment_start"]); let end = v3(&contact["segment_end"]);
            let hits = super::super::collision::query(&mesh,start,end).unwrap(); let nearest = &hits[0];
            assert_eq!(nearest.triangle_id,contact["triangle_id"].as_u64().unwrap() as u32);
            assert_eq!(nearest.mesh,contact["mesh"].as_str().unwrap());
            assert_eq!(nearest.material,contact["material"].as_str().unwrap());
            assert_eq!(nearest.t.to_bits(),(contact["t"].as_f64().unwrap() as f32).to_bits());
            assert_eq!(nearest.normal.map(f32::to_bits),v3(&contact["normal"]).map(f32::to_bits));
            let endpoint: [f32;3] = std::array::from_fn(|i| start[i]+nearest.t*(end[i]-start[i]));
            assert_eq!(endpoint.map(f32::to_bits),v3(&contact["endpoint"]).map(f32::to_bits));
            let facts = b.materials.lookup(&nearest.mesh,&nearest.material).unwrap();
            assert_eq!(facts.json()["damage_applied"],false);
            let reconstructed = Contact { shot: contact["shot"].as_u64().unwrap() as u32,
                target_slot: contact["target_slot"].as_u64().unwrap() as usize,
                tick: contact["tick"].as_u64().unwrap() as u32, segment_start: start, segment_end: end,
                segment_seconds: contact["segment_seconds"].as_f64().unwrap() as f32, endpoint,
                target_position: target.position, target_direction: target.direction,
                target_aim: [target.aim.yaw, target.aim.pitch], triangle: nearest.clone(),
                geometry_revision: mesh.geometry_revision().into(), transform_revision: mesh.transform_revision().into(),
                material_facts: facts };
            assert_eq!(b.impact_segment(&reconstructed).unwrap().component.name(), nearest.mesh);
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
