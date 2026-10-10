//! Pinned Karelia projectile static-obstacle export; geometry and source kind.
//!
//! World XYZ already includes each original instance transform. Per-triangle
//! original flags select the native ProjectileMover mask-128 subset. The
//! accepted vehicle-physics mask-18 mesh is intentionally not interchangeable.
//! Undamaged static objects only: no destruction, water or moving obstacles.
//! Two-sided closed segment intersections and coplanar misses are explicit
//! project policies, not reconstructed historical server behaviour.

use std::{fs, io::{self, Read}, path::{Component, Path}, sync::Arc};
use serde_json::Value;
use sha2::{Digest, Sha256};

pub const MANIFEST_SHA256: &str = "ccd28d8e3320d041e569e217a8c20e0285db0459bc2ef447c5bd95dd97d80cea";
pub const SOURCE_REVISION: &str = "karelia-projectile-obstacles-717:ccd28d8e3320d041e569e217a8c20e0285db0459bc2ef447c5bd95dd97d80cea";
const VERTICES_SHA256: &str = "8900634a1fd9dacbebe785d6c0289e2102f0811df7a677be473e2d0ea607db26";
const TRIANGLES_SHA256: &str = "06f3dcd079e6de79b4f653b4c6a23865b92d20449aab7480bbc8d6d2c8b85304";
const FLAGS_SHA256: &str = "9c601f8bc5463af3dc7107d1592d984eeaffd6cb453f338b34cffdf5dc02d1a1";
const MANIFEST_BYTES: usize = 2_190_312;
const VERTEX_COUNT: usize = 538_095;
const TRIANGLE_COUNT: usize = 179_365;
const INSTANCE_COUNT: usize = 2_918;
pub const MAX_QUERY_COORDINATE: f32 = 10_000.;
const LEAF_SIZE: usize = 8;
const MAX_DEPTH: usize = 32;
const TOLERANCE: f64 = 1e-12;
// Broadphase only. Covers the narrowphase barycentric/endpoint tolerance at
// the maximum coordinate/segment extent without enlarging any triangle.
const BOX_PADDING: f64 = 1e-7;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Hit {
    /// Original exported triangle array index, stable across BVH construction.
    pub triangle_id: u32,
    /// Zero-based original manifest instance index, including empty instances.
    pub instance_id: u32,
    /// Original resolved triangle flag >> 8, not an inferred surface label.
    pub material_kind: u8,
    pub t: f64,
    pub point: [f32; 3],
    /// Original world-space winding, normalised; never flipped to face a ray.
    pub normal: [f32; 3],
}

#[derive(Clone, Copy, Debug, PartialEq)]
struct Bounds { min: [f32; 3], max: [f32; 3] }

impl Bounds {
    fn triangle(points: [[f32; 3]; 3]) -> Self {
        Self { min: std::array::from_fn(|a| points[0][a].min(points[1][a]).min(points[2][a])),
            max: std::array::from_fn(|a| points[0][a].max(points[1][a]).max(points[2][a])) }
    }
    fn union(self, other: Self) -> Self {
        Self { min: std::array::from_fn(|a| self.min[a].min(other.min[a])),
            max: std::array::from_fn(|a| self.max[a].max(other.max[a])) }
    }
    fn entry(self, start: [f64; 3], direction: [f64; 3]) -> Option<f64> {
        let (mut first, mut last) = (-TOLERANCE, 1. + TOLERANCE);
        for axis in 0..3 {
            let low = f64::from(self.min[axis]) - BOX_PADDING;
            let high = f64::from(self.max[axis]) + BOX_PADDING;
            if direction[axis] == 0. {
                if start[axis] < low || start[axis] > high { return None; }
            } else {
                let a = (low - start[axis]) / direction[axis];
                let b = (high - start[axis]) / direction[axis];
                first = f64::max(first, a.min(b)); last = f64::min(last, a.max(b));
                if first > last { return None; }
            }
        }
        Some(first.max(0.))
    }
}

#[derive(Clone, Copy, Debug)]
struct Node {
    bounds: Bounds,
    // count > 0: [first, first+count) in order; count == 0: child indices.
    first: u32,
    count: u32,
    right: u32,
}

#[derive(Debug)]
struct Mesh {
    vertices: Box<[[f32; 3]]>,
    triangles: Box<[[u32; 3]]>,
    instances: Box<[u32]>,
    material_kinds: Box<[u8]>,
    order: Box<[u32]>,
    nodes: Box<[Node]>,
}

#[derive(Clone, Debug)]
pub struct Obstacles { mesh: Arc<Mesh> }

fn bad(reason: &'static str) -> io::Error { io::Error::new(io::ErrorKind::InvalidData, reason) }

fn non_reparse(path: &Path) -> io::Result<()> {
    if !path.is_absolute() || path.components().any(|part| matches!(part, Component::ParentDir)) {
        return Err(bad("obstacles absolute non-traversing path required"));
    }
    for parent in path.ancestors() {
        let metadata = fs::symlink_metadata(parent)?;
        if metadata.file_type().is_symlink() { return Err(bad("obstacles symlink refused")); }
        #[cfg(windows)] {
            use std::os::windows::fs::MetadataExt;
            if metadata.file_attributes() & 0x400 != 0 { return Err(bad("obstacles reparse path refused")); }
        }
    }
    Ok(())
}

fn read_pinned(root: &Path, path: &Path, size: usize, digest: &str) -> io::Result<Vec<u8>> {
    non_reparse(path)?;
    let path = path.canonicalize()?;
    if path == root || !path.starts_with(root) { return Err(bad("obstacles file outside local root")); }
    let file = fs::File::open(path)?;
    let metadata = file.metadata()?;
    if !metadata.is_file() || metadata.len() != size as u64 { return Err(bad("obstacles source size/type")); }
    let mut raw = Vec::with_capacity(size);
    file.take(size as u64 + 1).read_to_end(&mut raw)?;
    if raw.len() != size || format!("{:x}", Sha256::digest(&raw)) != digest {
        return Err(bad("obstacles source size/SHA256 mismatch"));
    }
    Ok(raw)
}

fn integer(value: &Value, maximum: usize) -> io::Result<usize> {
    let value = value.as_u64().ok_or_else(|| bad("obstacles integer required"))?;
    if value > maximum as u64 { return Err(bad("obstacles integer bound")); }
    Ok(value as usize)
}

fn vector(value: &Value) -> io::Result<[f32; 3]> {
    let values = value.as_array().filter(|a| a.len() == 3).ok_or_else(|| bad("obstacles bounds shape"))?;
    let mut result = [0.; 3];
    for axis in 0..3 {
        let value = values[axis].as_f64().ok_or_else(|| bad("obstacles bounds scalar"))?;
        if !value.is_finite() || value.abs() > f64::from(MAX_QUERY_COORDINATE) {
            return Err(bad("obstacles bounds finite limit"));
        }
        result[axis] = value as f32;
    }
    Ok(result)
}

fn subtract(a: [f64; 3], b: [f64; 3]) -> [f64; 3] { std::array::from_fn(|i| a[i] - b[i]) }
fn dot(a: [f64; 3], b: [f64; 3]) -> f64 { a.into_iter().zip(b).map(|(a,b)| a*b).sum() }
fn cross(a: [f64; 3], b: [f64; 3]) -> [f64; 3] {
    [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
}
fn points(vertices: &[[f32; 3]], triangle: [u32; 3]) -> [[f32; 3]; 3] {
    triangle.map(|index| vertices[index as usize])
}

impl Obstacles {
    /// Exact local files only. Every source hash is verified before decoding;
    /// embedded resource paths are provenance data and are never followed.
    pub fn load(local_root: &Path, manifest_path: &Path) -> io::Result<Self> {
        non_reparse(local_root)?;
        let root = local_root.canonicalize()?;
        let raw = read_pinned(&root, manifest_path, MANIFEST_BYTES, MANIFEST_SHA256)?;
        let directory = manifest_path.parent().ok_or_else(|| bad("obstacles manifest parent"))?;
        let vertices = read_pinned(&root, &directory.join("obstacles.vertices.f32"), VERTEX_COUNT * 12, VERTICES_SHA256)?;
        let triangles = read_pinned(&root, &directory.join("obstacles.triangles.u32"), TRIANGLE_COUNT * 12, TRIANGLES_SHA256)?;
        let flags = read_pinned(&root, &directory.join("obstacles.flags.u16"), TRIANGLE_COUNT * 2, FLAGS_SHA256)?;
        let value: Value = serde_json::from_slice(&raw).map_err(|_| bad("obstacles manifest JSON"))?;
        if value["version"] != 1 || value["kind"] != "original_091_projectile_static_triangle_mesh"
            || value["map"] != "01_karelia" || value["coordinates"] != serde_json::json!({
                "unit":"metre","up_axis":"Y","order":"XYZ","endianness":"little","space":"original world"})
            || value["collision_policy"]["excluded_mask"] != 128
            || value["vertices"]["file"] != "obstacles.vertices.f32" || value["vertices"]["count"] != VERTEX_COUNT
            || value["vertices"]["format"] != "float32_xyz" || value["vertices"]["stride"] != 12
            || value["vertices"]["bytes"] != VERTEX_COUNT * 12 || value["vertices"]["sha256"] != VERTICES_SHA256
            || value["triangles"]["file"] != "obstacles.triangles.u32" || value["triangles"]["count"] != TRIANGLE_COUNT
            || value["triangles"]["format"] != "uint32_abc" || value["triangles"]["stride"] != 12
            || value["triangles"]["bytes"] != TRIANGLE_COUNT * 12 || value["triangles"]["sha256"] != TRIANGLES_SHA256
            || value["flags"]["file"] != "obstacles.flags.u16" || value["flags"]["count"] != TRIANGLE_COUNT
            || value["flags"]["format"] != "uint16_flags" || value["flags"]["stride"] != 2
            || value["flags"]["bytes"] != TRIANGLE_COUNT * 2 || value["flags"]["sha256"] != FLAGS_SHA256
            || value["instances"].as_array().is_none_or(|rows| rows.len() != INSTANCE_COUNT) {
            return Err(bad("obstacles manifest schema/profile"));
        }
        Self::decode_buffers(&vertices, &triangles, &flags, &value["instances"])
    }

    fn decode_buffers(raw_vertices: &[u8], raw_triangles: &[u8], raw_flags: &[u8], rows: &Value) -> io::Result<Self> {
        if raw_vertices.is_empty() || raw_vertices.len() > VERTEX_COUNT * 12 || raw_vertices.len() % 12 != 0
            || raw_triangles.is_empty() || raw_triangles.len() > TRIANGLE_COUNT * 12 || raw_triangles.len() % 12 != 0
            || raw_vertices.len() != raw_triangles.len() * 3 || raw_flags.len() != raw_triangles.len()/6 {
            return Err(bad("obstacles buffer lengths"));
        }
        let mut vertices = Vec::with_capacity(raw_vertices.len()/12);
        for bytes in raw_vertices.chunks_exact(12) {
            let value: [f32; 3] = std::array::from_fn(|a| f32::from_le_bytes(
                bytes[a*4..a*4+4].try_into().expect("bounded four bytes")));
            if value.iter().any(|v| !v.is_finite() || v.abs() > MAX_QUERY_COORDINATE) {
                return Err(bad("obstacles vertex finite/coordinate bound"));
            }
            vertices.push(value);
        }
        let mut triangles = Vec::with_capacity(raw_triangles.len()/12);
        for (id,bytes) in raw_triangles.chunks_exact(12).enumerate() {
            let triangle: [u32; 3] = std::array::from_fn(|a| u32::from_le_bytes(
                bytes[a*4..a*4+4].try_into().expect("bounded four bytes")));
            // This pinned export owns three vertices per source triangle.
            // Enforce that topology rather than accepting cross-instance refs.
            if triangle != [id as u32*3,id as u32*3+1,id as u32*3+2] {
                return Err(bad("obstacles original index topology"));
            }
            triangles.push(triangle);
        }
        let rows = rows.as_array().filter(|rows| !rows.is_empty() && rows.len() <= INSTANCE_COUNT)
            .ok_or_else(|| bad("obstacles instance array"))?;
        let mut instances = Vec::with_capacity(triangles.len());
        let mut cursor = 0;
        for (id,row) in rows.iter().enumerate() {
            if !row.is_object() { return Err(bad("obstacles instance object")); }
            let first = integer(&row["first_triangle"],triangles.len())?;
            let count = integer(&row["triangles"],triangles.len()-cursor)?;
            if first != cursor { return Err(bad("obstacles instance range partition")); }
            if count == 0 {
                if row.get("bounds") != Some(&Value::Null) { return Err(bad("obstacles empty instance bounds")); }
                continue;
            }
            let value = row["bounds"].as_object().filter(|object| object.len() == 2)
                .ok_or_else(|| bad("obstacles bounds object"))?;
            let declared = Bounds { min: vector(value.get("min").unwrap_or(&Value::Null))?,
                max: vector(value.get("max").unwrap_or(&Value::Null))? };
            let mut actual = Bounds::triangle(points(&vertices,triangles[first]));
            for triangle in &triangles[first..first+count] { actual = actual.union(Bounds::triangle(points(&vertices,*triangle))); }
            // Exact equality is required for every nonempty source row;
            // a stale or oversized metadata box is not silently trusted.
            if declared != actual { return Err(bad("obstacles recomputed instance AABB mismatch")); }
            instances.extend(std::iter::repeat_n(id as u32,count)); cursor += count;
        }
        if cursor != triangles.len() { return Err(bad("obstacles incomplete instance partition")); }
        let flags = raw_flags.chunks_exact(2).map(|bytes| u16::from_le_bytes(bytes.try_into().expect("bounded two bytes"))).collect();
        Self::build(vertices,triangles,instances,flags)
    }

    fn build(vertices: Vec<[f32; 3]>, triangles: Vec<[u32; 3]>, instances: Vec<u32>, flags: Vec<u16>) -> io::Result<Self> {
        if triangles.is_empty() || triangles.len() > TRIANGLE_COUNT || instances.len() != triangles.len()
            || flags.len() != triangles.len() || flags.iter().any(|flag| flag & 128 != 0)
            || vertices.len() > VERTEX_COUNT || vertices.iter().flatten().any(|v| !v.is_finite() || v.abs() > MAX_QUERY_COORDINATE) {
            return Err(bad("obstacles mesh construction bounds"));
        }
        let mut boxes = Vec::with_capacity(triangles.len());
        for &triangle in &triangles {
            if triangle.iter().any(|&i| i as usize >= vertices.len()) { return Err(bad("obstacles triangle index")); }
            let source = points(&vertices,triangle);
            let [a,b,c] = source.map(|p| p.map(f64::from));
            let normal = cross(subtract(b,a),subtract(c,a));
            if dot(normal,normal) <= 1e-16 { return Err(bad("obstacles rounded degenerate triangle")); }
            boxes.push(Bounds::triangle(source));
        }
        let mut order: Vec<u32> = (0..triangles.len() as u32).collect();
        let mut nodes = Vec::with_capacity(triangles.len()/2+1);
        build_node(&mut order,0,&boxes,&mut nodes,0)?;
        Ok(Self { mesh: Arc::new(Mesh { vertices: vertices.into_boxed_slice(),triangles:triangles.into_boxed_slice(),
            instances:instances.into_boxed_slice(),material_kinds:flags.into_iter().map(|flag| (flag >> 8) as u8).collect(),
            order:order.into_boxed_slice(),nodes:nodes.into_boxed_slice() }) })
    }

    /// The closest two-sided geometric crossing of a finite closed segment.
    /// Exact f64 ties use source triangle ID. A point inside a closed mesh
    /// hits its actual exit, never an invented t=0 surface. No material rule.
    pub fn nearest(&self, start: [f32; 3], end: [f32; 3]) -> io::Result<Option<Hit>> {
        self.query(start,end).map(|(hit,_)| hit)
    }

    fn query(&self, start: [f32; 3], end: [f32; 3]) -> io::Result<(Option<Hit>,usize)> {
        if start.into_iter().chain(end).any(|v| !v.is_finite() || v.abs() > MAX_QUERY_COORDINATE) {
            return Err(bad("obstacles segment finite/coordinate bound"));
        }
        let start = start.map(f64::from); let direction = subtract(end.map(f64::from),start);
        if dot(direction,direction) == 0. { return Err(bad("obstacles zero segment")); }
        let Some(entry) = self.mesh.nodes[0].bounds.entry(start,direction) else { return Ok((None,0)); };
        let mut stack = Vec::with_capacity(MAX_DEPTH+1); stack.push((0_u32,entry));
        let (mut best,mut tested,mut visited): (Option<Hit>,usize,usize) = (None,0,0);
        while let Some((id,entry)) = stack.pop() {
            visited += 1;
            if visited > self.mesh.nodes.len() { return Err(bad("obstacles traversal node bound")); }
            if best.is_some_and(|hit| entry > hit.t) { continue; }
            let node = self.mesh.nodes[id as usize];
            if node.count > 0 {
                for &triangle_id in &self.mesh.order[node.first as usize..(node.first+node.count) as usize] {
                    tested += 1;
                    let triangle = points(&self.mesh.vertices,self.mesh.triangles[triangle_id as usize]);
                    if let Some(hit) = intersect(start,direction,triangle,triangle_id,self.mesh.instances[triangle_id as usize],
                        self.mesh.material_kinds[triangle_id as usize]) {
                        if best.is_none_or(|old| hit.t.total_cmp(&old.t).then(hit.triangle_id.cmp(&old.triangle_id)).is_lt()) {
                            best = Some(hit);
                        }
                    }
                }
            } else {
                let mut children = [(node.first,None),(node.right,None)];
                for (child,entry) in &mut children { *entry = self.mesh.nodes[*child as usize].bounds.entry(start,direction); }
                // Far child is pushed first; near hits prune later boxes.
                children.sort_by(|a,b| b.1.unwrap_or(f64::INFINITY).total_cmp(&a.1.unwrap_or(f64::INFINITY)).then(b.0.cmp(&a.0)));
                for (child,entry) in children {
                    if let Some(entry) = entry.filter(|t| best.is_none_or(|hit| *t <= hit.t)) { stack.push((child,entry)); }
                }
                if stack.len() > MAX_DEPTH+1 { return Err(bad("obstacles traversal stack bound")); }
            }
        }
        Ok((best,tested))
    }
}

fn build_node(order: &mut [u32], first: usize, boxes: &[Bounds], nodes: &mut Vec<Node>, depth: usize) -> io::Result<u32> {
    if order.is_empty() || depth > MAX_DEPTH || nodes.len() >= boxes.len()*2 { return Err(bad("obstacles BVH construction bound")); }
    let bounds = order.iter().skip(1).fold(boxes[order[0] as usize],|b,&id| b.union(boxes[id as usize]));
    let id = nodes.len() as u32;
    nodes.push(Node { bounds,first:first as u32,count:order.len() as u32,right:0 });
    if order.len() > LEAF_SIZE {
        let axis = (0_usize..3).max_by(|&a,&b| (f64::from(bounds.max[a])-f64::from(bounds.min[a]))
            .total_cmp(&(f64::from(bounds.max[b])-f64::from(bounds.min[b]))).then(b.cmp(&a))).expect("three axes");
        let middle = order.len()/2;
        let centre = |id: u32| f64::from(boxes[id as usize].min[axis])+f64::from(boxes[id as usize].max[axis]);
        order.select_nth_unstable_by(middle,|&a,&b| centre(a).total_cmp(&centre(b)).then(a.cmp(&b)));
        let (left,right) = order.split_at_mut(middle);
        let left = build_node(left,first,boxes,nodes,depth+1)?;
        let right = build_node(right,first+middle,boxes,nodes,depth+1)?;
        nodes[id as usize] = Node { bounds,first:left,count:0,right };
    }
    Ok(id)
}

fn intersect(start: [f64; 3], direction: [f64; 3], triangle: [[f32; 3]; 3], triangle_id: u32, instance_id: u32, material_kind: u8) -> Option<Hit> {
    let [a,b,c] = triangle.map(|p| p.map(f64::from)); let edge1 = subtract(b,a); let edge2 = subtract(c,a);
    let normal = cross(edge1,edge2); let normal_length = dot(normal,normal).sqrt();
    let h = cross(direction,edge2); let determinant = dot(edge1,h);
    if determinant.abs() <= TOLERANCE * dot(direction,direction).sqrt() * normal_length { return None; }
    let inverse = 1./determinant; let delta = subtract(start,a); let u = inverse*dot(delta,h);
    if u < -TOLERANCE || u > 1.+TOLERANCE { return None; }
    let q = cross(delta,edge1); let v = inverse*dot(direction,q);
    if v < -TOLERANCE || u+v > 1.+TOLERANCE { return None; }
    let t = inverse*dot(edge2,q);
    if !t.is_finite() || t < -TOLERANCE || t > 1.+TOLERANCE { return None; }
    let t = t.clamp(0.,1.);
    Some(Hit { triangle_id,instance_id,material_kind,t,point:std::array::from_fn(|a| (start[a]+direction[a]*t) as f32),
        normal:normal.map(|v| (v/normal_length) as f32) })
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use std::sync::OnceLock;

    /// Each input triangle is one instance; IDs preserve the input ordering.
    pub(crate) fn fixture(triangles: Vec<[[f32; 3]; 3]>) -> Obstacles {
        fixture_with_material_kind(triangles,111)
    }
    pub(crate) fn fixture_with_material_kind(triangles: Vec<[[f32; 3]; 3]>, material_kind: u8) -> Obstacles {
        let count = triangles.len();
        let vertices = triangles.into_iter().flatten().collect();
        let indices = (0..count as u32).map(|id| [id*3,id*3+1,id*3+2]).collect();
        Obstacles::build(vertices,indices,(0..count as u32).collect(),vec![u16::from(material_kind)<<8;count]).unwrap()
    }
    fn wall(x: f32) -> [[f32; 3]; 3] { [[x,-2.,-2.],[x,2.,-2.],[x,0.,2.]] }
    fn actual() -> &'static Obstacles {
        static MESH: OnceLock<Obstacles> = OnceLock::new();
        MESH.get_or_init(|| {
            let root = std::env::var_os("WOT091_ROOT").map(std::path::PathBuf::from)
                .unwrap_or_else(|| std::path::PathBuf::from(r"D:\WoT_9.1_Server"));
            Obstacles::load(&root.join("local"),&root.join("local/evidence/20261010-p06m-terrain-impact-01/projectile-obstacles01/01_karelia/manifest.json")).unwrap()
        })
    }
    fn brute(mesh: &Obstacles, start: [f32; 3], end: [f32; 3]) -> Option<Hit> {
        let direction = subtract(end.map(f64::from),start.map(f64::from));
        mesh.mesh.triangles.iter().enumerate().filter_map(|(id,&triangle)| {
            intersect(start.map(f64::from),direction,points(&mesh.mesh.vertices,triangle),id as u32,mesh.mesh.instances[id],mesh.mesh.material_kinds[id])
        }).min_by(|a,b| a.t.total_cmp(&b.t).then(a.triangle_id.cmp(&b.triangle_id)))
    }

    #[test]
    fn fast_reverse_closest_closed_endpoint_and_coplanar_segments() {
        let mesh = fixture(vec![wall(3.),wall(0.),wall(2.)]);
        let hit = mesh.nearest([-10000.,0.,0.],[10000.,0.,0.]).unwrap().unwrap();
        assert_eq!((hit.triangle_id,hit.instance_id),(1,1)); assert_eq!(hit.t,0.5); assert_eq!(hit.point,[0.,0.,0.]);
        assert_eq!(hit.material_kind,111);
        let reverse = mesh.nearest([10.,0.,0.],[-10.,0.,0.]).unwrap().unwrap();
        assert_eq!(reverse.triangle_id,0); assert_eq!(reverse.normal,hit.normal);
        assert_eq!(mesh.nearest([-1.,0.,0.],[0.,0.,0.]).unwrap().unwrap().t,1.);
        assert_eq!(mesh.nearest([0.,0.,0.],[-1.,0.,0.]).unwrap().unwrap().t,0.);
        assert!(mesh.nearest([0.,-1.,0.],[0.,1.,0.]).unwrap().is_none());
        assert!(mesh.nearest([-1.,3.,0.],[5.,3.,0.]).unwrap().is_none());
    }

    #[test]
    fn inside_segment_hits_exit_and_equal_t_keeps_source_id() {
        let mesh = fixture(vec![wall(2.),wall(0.),wall(0.)]);
        assert_eq!(mesh.nearest([1.,0.,0.],[4.,0.,0.]).unwrap().unwrap().triangle_id,0);
        assert_eq!(mesh.nearest([-1.,0.,0.],[1.,0.,0.]).unwrap().unwrap().triangle_id,1);
        assert!(Arc::ptr_eq(&mesh.mesh,&mesh.clone().mesh));
    }

    #[test]
    fn bvh_matches_all_triangles_on_varied_segments_and_boundaries() {
        let mut triangles = Vec::new();
        for x in 0..40 { for z in 0..10 {
            triangles.push(wall(x as f32*2.).map(|mut p| { p[2] += z as f32*6.; p }));
        }}
        let mesh = fixture(triangles);
        let mut seed=728913_u32;
        let mut next=|| { seed=seed.wrapping_mul(1664525).wrapping_add(1013904223); (seed>>8) as f32/16777216. };
        for _ in 0..192 {
            let start=[next()*100.-10.,next()*8.-4.,next()*70.-7.];
            let end=[next()*100.-10.,next()*8.-4.,next()*70.-7.];
            assert_eq!(mesh.nearest(start,end).unwrap(),brute(&mesh,start,end));
        }
        for y in [-2.,0.,2.] { for z in [-2.,0.,2.] {
            let start=[-1.,y,z];let end=[81.,y,z];
            assert_eq!(mesh.nearest(start,end).unwrap(),brute(&mesh,start,end));
        }}
        let (_,tested)=mesh.query([-1.,0.,0.],[81.,0.,0.]).unwrap();
        assert!(tested < mesh.mesh.triangles.len()/4,"near-first BVH must prune distant walls");
    }

    #[test]
    fn finite_query_bounds_and_far_outside_are_explicit() {
        let mesh=fixture(vec![wall(0.)]);
        for (a,b) in [([0.,0.,0.],[0.,0.,0.]),([f32::NAN,0.,0.],[1.,0.,0.]),
            ([0.,0.,0.],[f32::INFINITY,0.,0.]),([-10001.,0.,0.],[0.,0.,0.])] {
            assert!(mesh.nearest(a,b).is_err());
        }
        let (hit,tested)=mesh.query([8000.,8000.,8000.],[9000.,9000.,9000.]).unwrap();
        assert_eq!((hit,tested),(None,0));
    }

    #[test]
    fn exact_source_rocks_match_independently_read_triangle_heights() {
        let mesh=actual();
        assert_eq!(mesh.mesh.vertices.len(),VERTEX_COUNT); assert_eq!(mesh.mesh.triangles.len(),TRIANGLE_COUNT);
        assert_eq!(mesh.mesh.instances.len(),TRIANGLE_COUNT);
        // Independently read source/export triangles, not a native projectile
        // collision oracle. Top and bottom of unchanged original rock meshes.
        for (x,z,top,top_id,bottom,bottom_id,instance) in [
            (51.,89.,24.37917803305798,367,19.053977420573677,447,0),
            (100.,65.,27.36021902091406,1426,19.901245646903316,1274,1)] {
            let (hit,tested)=mesh.query([x,200.,z],[x,-100.,z]).unwrap(); let hit=hit.unwrap();
            assert_eq!((hit.triangle_id,hit.instance_id),(top_id,instance));
            assert_eq!(hit.material_kind,111);
            assert!((f64::from(hit.point[1])-top).abs()<0.00001); assert!((hit.t-(200.-top)/300.).abs()<1e-12);
            assert!(tested < 2048,"a local shot must not scan the complete map");
            let reverse=mesh.nearest([x,-100.,z],[x,200.,z]).unwrap().unwrap();
            assert_eq!(reverse.triangle_id,bottom_id);assert!((f64::from(reverse.point[1])-bottom).abs()<0.00001);
        }
        assert!(mesh.nearest([0.,200.,0.],[0.,-100.,0.]).unwrap().is_none());
    }

    #[test] fn owner_native01_shot3_stops_on_stone_before_distant_ground() {
        // Retained native01 shot3 launch + two clients' actual early FX point.
        // The old terrain-only endpoint was over550m beyond this rock.
        let mesh=actual(); let origin=[-61.35858,22.979078,-437.86508];
        let velocity=[-102.82297,10.104385,338.16907];
        let mut found=None;
        for step in 0..20 {
            let point=|t| super::super::projectile::position_at(origin,velocity,6.2784004,t);
            if let Some(hit)=mesh.nearest(point(step as f32*0.1),point((step+1) as f32*0.1)).unwrap() {
                found=Some((step,hit));break;
            }
        }
        let (step,hit)=found.expect("captured original rock must block shot");
        assert_eq!(step,1); assert_eq!(hit.material_kind,111);
        let expected=[-75.039,24.261,-392.873];
        let distance=(0..3).map(|i|f64::from(hit.point[i]-expected[i]).powi(2)).sum::<f64>().sqrt();
        assert!(distance<0.05,"captured native rock point differs by {distance}m");
    }

    fn small_buffers() -> (Vec<u8>,Vec<u8>,Vec<u8>,Value) {
        let triangle=wall(0.); let bounds=Bounds::triangle(triangle);
        (triangle.into_iter().flatten().flat_map(f32::to_le_bytes).collect(),
            [0_u32,1,2].into_iter().flat_map(u32::to_le_bytes).collect(),
            (111_u16<<8).to_le_bytes().to_vec(),
            serde_json::json!([{"first_triangle":0,"triangles":1,"bounds":{"min":bounds.min,"max":bounds.max}}]))
    }

    #[test]
    fn malformed_coordinates_indices_bounds_and_partitions_are_rejected() {
        let (vertices,triangles,flags,rows)=small_buffers();
        assert!(Obstacles::decode_buffers(&vertices,&triangles,&flags,&rows).is_ok());
        assert!(Obstacles::decode_buffers(&vertices[..35],&triangles,&flags,&rows).is_err());
        assert!(Obstacles::decode_buffers(&vertices,&triangles[..11],&flags,&rows).is_err());
        for value in [f32::NAN,f32::INFINITY,10001.] {
            let mut changed=vertices.clone();changed[0..4].copy_from_slice(&value.to_le_bytes());
            assert!(Obstacles::decode_buffers(&changed,&triangles,&flags,&rows).is_err());
        }
        for value in [0_u32,999] {
            let mut changed=triangles.clone();changed[4..8].copy_from_slice(&value.to_le_bytes());
            assert!(Obstacles::decode_buffers(&vertices,&changed,&flags,&rows).is_err());
        }
        for (field,value) in [("first_triangle",serde_json::json!(1)),("first_triangle",serde_json::json!(-1)),
            ("triangles",serde_json::json!(0)),("triangles",serde_json::json!(1.5)),("triangles",serde_json::json!(2)),
            ("bounds",serde_json::json!({"min":[-1.,-2.,-2.],"max":[0.,2.,2.]})),("bounds",Value::Null)] {
            let mut changed=rows.clone(); changed[0][field]=value;
            assert!(Obstacles::decode_buffers(&vertices,&triangles,&flags,&changed).is_err(),"{field}");
        }
        let duplicate=serde_json::json!([rows[0],rows[0]]);
        assert!(Obstacles::decode_buffers(&vertices,&triangles,&flags,&duplicate).is_err());
        let empty=serde_json::json!([{"first_triangle":0,"triangles":0,"bounds":null},rows[0]]);
        let mesh=Obstacles::decode_buffers(&vertices,&triangles,&flags,&empty).unwrap();
        assert_eq!(mesh.nearest([-1.,0.,0.],[1.,0.,0.]).unwrap().unwrap().instance_id,1);
        let mut degenerate=vertices.clone();degenerate[12..24].copy_from_slice(&vertices[0..12]);
        assert!(Obstacles::decode_buffers(&degenerate,&triangles,&flags,&rows).is_err());
        assert!(Obstacles::decode_buffers(&vertices,&triangles,&[],&rows).is_err());
        let excluded=(111_u16<<8 | 128).to_le_bytes();
        assert!(Obstacles::decode_buffers(&vertices,&triangles,&excluded,&rows).is_err());
        let changed=(73_u16<<8).to_le_bytes();
        let mesh=Obstacles::decode_buffers(&vertices,&triangles,&changed,&rows).unwrap();
        assert_eq!(mesh.nearest([-1.,0.,0.],[1.,0.,0.]).unwrap().unwrap().material_kind,73);
    }

    #[test]
    fn source_hashes_and_path_guards_precede_decoding() {
        let root=std::env::temp_dir().join(format!("sr-obstacles-pin-test-{}",std::process::id()));
        fs::create_dir(&root).unwrap();let path=root.join("manifest.json");
        fs::write(&path,vec![b'!';MANIFEST_BYTES]).unwrap();
        assert!(Obstacles::load(&root,&path).unwrap_err().to_string().contains("SHA256"));
        assert!(Obstacles::load(&root,Path::new("manifest.json")).is_err());
        assert!(Obstacles::load(&root,&root.join("../manifest.json")).is_err());
        let canonical=root.canonicalize().unwrap();
        assert!(read_pinned(&canonical,&path,MANIFEST_BYTES,"wrong").is_err());
        assert!(read_pinned(&root.join("different-root"),&path,MANIFEST_BYTES,MANIFEST_SHA256).is_err());
        // Exact test-owned paths only; no recursive cleanup or client writes.
        fs::remove_file(path).unwrap();fs::remove_dir(root).unwrap();
    }
}
