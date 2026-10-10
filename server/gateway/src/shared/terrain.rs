//! Pinned Karelia terrain triangles and a bounded nearest-segment query.
//!
//! Geometry is the exact accepted map-drive export, not a bilinear surface.
//! Its 144 source chunks contain no hole members. Loading any other map,
//! hole-bearing export, LOD or changed bytes is unsupported, not filled in.
//! The checkerboard topology matches the static #717 heightAt parity evidence
//! (0x101dd20, XOR at 0x101de09). Native projectile collision equivalence is a
//! separate measured gate. Two-sided closed triangles, no coplanar contact and
//! no invented hit for an underground segment are explicit query policies.
//!
//! Rechecked source pins: original 01_karelia.pkg SHA256
//! a476c913acce8d385c027400fbd97cc93ff3253fd9f8249b60f186a9eb1fa12e;
//! 144 cdata member digests match surface export SHA256
//! 1952f94cfb0d52684a446de8017f2269e746a39b016597de567de93863624650.
//! Exact original EXE SHA256
//! 86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed;
//! measured 1024-byte heightAt window SHA256
//! ab07c185b4918b835f0f1a3cc8f4aaaab72e1e8172fbcb4599d127dae82fb139.

use std::{collections::BTreeSet, fs, io::{self, Read}, path::{Component, Path}, sync::Arc};
use serde_json::Value;
use sha2::{Digest, Sha256};

pub const MANIFEST_SHA256: &str = "5e23f58d4e9d78398bd9cd861f6bc09a038cce7e8f7b311731e50c30bcc958f9";
pub const SOURCE_REVISION: &str = "karelia-terrain-717:5e23f58d4e9d78398bd9cd861f6bc09a038cce7e8f7b311731e50c30bcc958f9";
const VERTICES_SHA256: &str = "dc0752ceaaa6b469b36062a5c0a1d397edfa7a39815bf0d19d1290d0c8a08a92";
const TRIANGLES_SHA256: &str = "27ba25b1f81a37cb678584a898b0efed2b497ef1fc26ecb342ff852f72ec479c";
const GRID_WIDTH: usize = 769;
const GRID_CELLS: usize = GRID_WIDTH - 1;
const SPACING: f64 = 1.5625;
const ORIGIN: f64 = -600.;
const VERTEX_BYTES: usize = GRID_WIDTH * GRID_WIDTH * 12;
const TRIANGLE_BYTES: usize = GRID_CELLS * GRID_CELLS * 24;
const MANIFEST_MAX_BYTES: usize = 16 * 1024;
pub const MAX_QUERY_COORDINATE: f32 = 10_000.;
/// Supercover includes cells on both sides of grid lines and at corners.
pub const MAX_QUERY_CELLS: usize = 8 * GRID_CELLS + 16;
pub const MAX_QUERY_CROSSINGS: usize = 2 * GRID_WIDTH + 2;
const TOLERANCE: f64 = 1e-12;
// Broadphase only: include both neighbors of a rounded grid boundary. This
// does not inflate triangles or change the narrowphase contact parameter.
const GRID_BOUNDARY_TOLERANCE: f64 = 1e-9;

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Hit {
    /// Stable row-major source ID: (z * 768 + x) * 2 + local triangle.
    pub triangle_id: u32,
    pub t: f64,
    pub point: [f32; 3],
    /// Unit normal from the pinned positive-Y winding; never face-flipped.
    pub normal: [f32; 3],
}

#[derive(Clone, Debug)]
pub struct Terrain {
    // Immutable compact heights make World clone transactions cheap. X/Z and
    // triangle indices are reconstructed only after validating every original
    // vertex coordinate and every original index, including both parities.
    heights: Arc<[f32]>,
    width: usize,
    origin: f64,
    spacing: f64,
}

fn bad(reason: &'static str) -> io::Error { io::Error::new(io::ErrorKind::InvalidData, reason) }

fn non_reparse(path: &Path) -> io::Result<()> {
    if !path.is_absolute() || path.components().any(|part| matches!(part, Component::ParentDir)) {
        return Err(bad("terrain absolute non-traversing path required"));
    }
    for parent in path.ancestors() {
        let metadata = fs::symlink_metadata(parent)?;
        if metadata.file_type().is_symlink() { return Err(bad("terrain symlink refused")); }
        #[cfg(windows)] {
            use std::os::windows::fs::MetadataExt;
            if metadata.file_attributes() & 0x400 != 0 { return Err(bad("terrain reparse path refused")); }
        }
    }
    Ok(())
}

fn read_pinned(root: &Path, path: &Path, limit: usize, exact_size: Option<usize>, digest: &str) -> io::Result<Vec<u8>> {
    non_reparse(path)?;
    let path = path.canonicalize()?;
    if path == root || !path.starts_with(root) { return Err(bad("terrain file outside local root")); }
    let file = fs::File::open(path)?;
    let metadata = file.metadata()?;
    if !metadata.is_file() || metadata.len() == 0 || metadata.len() > limit as u64 {
        return Err(bad("terrain source file size/type"));
    }
    let mut raw = Vec::with_capacity(metadata.len() as usize);
    file.take(limit as u64 + 1).read_to_end(&mut raw)?;
    if raw.len() > limit || exact_size.is_some_and(|size| size != raw.len())
        || format!("{:x}", Sha256::digest(&raw)) != digest {
        return Err(bad("terrain source size/SHA256 mismatch"));
    }
    Ok(raw)
}

fn indices(width: usize, x: usize, z: usize) -> [[usize; 3]; 2] {
    let a = z * width + x; let b = a + 1; let c = a + width; let d = c + 1;
    if (x ^ z) & 1 == 1 { [[a, c, b], [b, c, d]] } else { [[a, c, d], [a, d, b]] }
}

impl Terrain {
    /// Load only the exact accepted Karelia map-drive mesh. Hashes are checked
    /// before JSON/binary decoding; source paths from JSON are never followed.
    pub fn load(local_root: &Path, manifest_path: &Path) -> io::Result<Self> {
        non_reparse(local_root)?;
        let root = local_root.canonicalize()?;
        let manifest = read_pinned(&root, manifest_path, MANIFEST_MAX_BYTES, None, MANIFEST_SHA256)?;
        let value: Value = serde_json::from_slice(&manifest).map_err(|_| bad("terrain manifest JSON"))?;
        if value["version"] != 1 || value["kind"] != "original_091_static_triangle_mesh"
            || value["map"] != "01_karelia" || value["vertices"]["file"] != "terrain.vertices.f32"
            || value["triangles"]["file"] != "terrain.triangles.u32"
            || value["vertices"]["count"] != GRID_WIDTH * GRID_WIDTH
            || value["triangles"]["count"] != GRID_CELLS * GRID_CELLS * 2
            || value["vertices"]["sha256"] != VERTICES_SHA256 || value["triangles"]["sha256"] != TRIANGLES_SHA256 {
            return Err(bad("terrain manifest schema/profile"));
        }
        let directory = manifest_path.parent().ok_or_else(|| bad("terrain manifest parent"))?;
        let vertices = read_pinned(&root, &directory.join("terrain.vertices.f32"), VERTEX_BYTES, Some(VERTEX_BYTES), VERTICES_SHA256)?;
        let triangles = read_pinned(&root, &directory.join("terrain.triangles.u32"), TRIANGLE_BYTES, Some(TRIANGLE_BYTES), TRIANGLES_SHA256)?;
        Self::decode_buffers(&vertices, &triangles)
    }

    fn decode_buffers(vertices: &[u8], triangles: &[u8]) -> io::Result<Self> {
        if vertices.len() != VERTEX_BYTES || triangles.len() != TRIANGLE_BYTES {
            return Err(bad("terrain exact buffer lengths"));
        }
        let mut heights = Vec::with_capacity(GRID_WIDTH * GRID_WIDTH);
        for (index, vertex) in vertices.chunks_exact(12).enumerate() {
            let numbers: [f32; 3] = std::array::from_fn(|axis| {
                f32::from_le_bytes(vertex[axis * 4..axis * 4 + 4].try_into().expect("bounded four bytes"))
            });
            let x = (ORIGIN + (index % GRID_WIDTH) as f64 * SPACING) as f32;
            let z = (ORIGIN + (index / GRID_WIDTH) as f64 * SPACING) as f32;
            if numbers.iter().any(|v| !v.is_finite() || v.abs() > MAX_QUERY_COORDINATE)
                || numbers[0].to_bits() != x.to_bits() || numbers[2].to_bits() != z.to_bits() {
                return Err(bad("terrain vertex grid/finite bound"));
            }
            heights.push(numbers[1]);
        }
        for (cell, data) in triangles.chunks_exact(24).enumerate() {
            let expected = indices(GRID_WIDTH, cell % GRID_CELLS, cell / GRID_CELLS);
            for (index, bytes) in data.chunks_exact(4).enumerate() {
                let value = u32::from_le_bytes(bytes.try_into().expect("bounded four bytes"));
                if value as usize != expected[index / 3][index % 3] {
                    return Err(bad("terrain checkerboard/source index mismatch"));
                }
            }
        }
        Ok(Self { heights: heights.into(), width: GRID_WIDTH, origin: ORIGIN, spacing: SPACING })
    }

    fn vertex(&self, index: usize) -> [f64; 3] {
        [self.origin + (index % self.width) as f64 * self.spacing,
         f64::from(self.heights[index]), self.origin + (index / self.width) as f64 * self.spacing]
    }

    fn triangle(&self, id: usize) -> [[f64; 3]; 3] {
        let width = self.width - 1; let cell = id / 2;
        indices(self.width, cell % width, cell / width)[id % 2].map(|index| self.vertex(index))
    }

    /// Closest intersection from either face of a finite closed segment.
    /// Equal f64 t uses the lowest stable source triangle ID. Outside the
    /// exported [-600,600] square is empty; no border wall is manufactured.
    /// A segment entirely below terrain does not become a fabricated t=0 hit.
    pub fn nearest(&self, start: [f32; 3], end: [f32; 3]) -> io::Result<Option<Hit>> {
        if start.into_iter().chain(end).any(|v| !v.is_finite() || v.abs() > MAX_QUERY_COORDINATE) {
            return Err(bad("terrain segment finite/coordinate bound"));
        }
        let start = start.map(f64::from); let end = end.map(f64::from);
        let direction = subtract(end, start);
        if length(direction) == 0. { return Err(bad("terrain zero segment")); }
        let cells = self.segment_cells(start, direction)?;
        let mut nearest: Option<Hit> = None;
        for cell in cells {
            for local in 0..2 {
                let id = cell * 2 + local;
                if let Some(hit) = intersect(start, direction, self.triangle(id), id as u32) {
                    let replace = nearest.as_ref().is_none_or(|old| {
                        hit.t.total_cmp(&old.t).then(hit.triangle_id.cmp(&old.triangle_id)).is_lt()
                    });
                    if replace { nearest = Some(hit); }
                }
            }
        }
        Ok(nearest)
    }

    fn segment_cells(&self, start: [f64; 3], direction: [f64; 3]) -> io::Result<BTreeSet<usize>> {
        let count = self.width - 1;
        let maximum = self.origin + count as f64 * self.spacing;
        let (mut enter, mut leave) = (0.0_f64, 1.0_f64);
        // Clip before traversing, even when both endpoints are far outside.
        for axis in [0, 2] {
            if direction[axis] == 0. {
                if start[axis] < self.origin || start[axis] > maximum { return Ok(BTreeSet::new()); }
            } else {
                let a = (self.origin - start[axis]) / direction[axis];
                let b = (maximum - start[axis]) / direction[axis];
                enter = enter.max(a.min(b)); leave = leave.min(a.max(b));
                if enter > leave { return Ok(BTreeSet::new()); }
            }
        }
        // Crossings are generated only for the grid lines crossed by this
        // clipped segment. Merging their sorted t values is a 2D grid walk;
        // midpoint cells plus closed-boundary neighbors form the supercover.
        // At most 2*769+2 parameters, never a scan of 768*768 cells.
        let mut crossings = vec![enter, leave];
        for axis in [0, 2] {
            if direction[axis] == 0. { continue; }
            let a = (start[axis] + direction[axis] * enter - self.origin) / self.spacing;
            let b = (start[axis] + direction[axis] * leave - self.origin) / self.spacing;
            let first = a.min(b).ceil().max(0.) as usize;
            let last = a.max(b).floor().min(count as f64) as usize;
            for line in first..=last {
                let t = (self.origin + line as f64 * self.spacing - start[axis]) / direction[axis];
                if t >= enter && t <= leave { crossings.push(t); }
            }
        }
        if crossings.len() > MAX_QUERY_CROSSINGS { return Err(bad("terrain crossing bound")); }
        crossings.sort_by(f64::total_cmp);
        crossings.dedup();
        let mut cells = BTreeSet::new();
        for &t in &crossings { self.add_cells_at(start, direction, t, &mut cells)?; }
        for window in crossings.windows(2) {
            self.add_cells_at(start, direction, window[0] + (window[1] - window[0]) * 0.5, &mut cells)?;
        }
        Ok(cells)
    }

    fn add_cells_at(&self, start: [f64; 3], direction: [f64; 3], t: f64, cells: &mut BTreeSet<usize>) -> io::Result<()> {
        let count = self.width - 1;
        let neighbors = |axis: usize| {
            let grid = (start[axis] + direction[axis] * t - self.origin) / self.spacing;
            let base = grid.floor() as isize;
            let rounded = grid.round();
            if (grid - rounded).abs() <= GRID_BOUNDARY_TOLERANCE {
                [rounded as isize - 1, rounded as isize]
            } else { [base, base] }
        };
        for x in neighbors(0) { for z in neighbors(2) {
            if x >= 0 && z >= 0 && x < count as isize && z < count as isize {
                cells.insert(z as usize * count + x as usize);
                if cells.len() > MAX_QUERY_CELLS { return Err(bad("terrain visited-cell bound")); }
            }
        }}
        Ok(())
    }
}

fn subtract(a: [f64; 3], b: [f64; 3]) -> [f64; 3] { std::array::from_fn(|i| a[i] - b[i]) }
fn dot(a: [f64; 3], b: [f64; 3]) -> f64 { a.into_iter().zip(b).map(|(a,b)| a*b).sum() }
fn cross(a: [f64; 3], b: [f64; 3]) -> [f64; 3] {
    [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
}
fn length(a: [f64; 3]) -> f64 { dot(a,a).sqrt() }

fn intersect(start: [f64; 3], direction: [f64; 3], triangle: [[f64; 3]; 3], triangle_id: u32) -> Option<Hit> {
    let [a,b,c] = triangle; let edge1 = subtract(b,a); let edge2 = subtract(c,a);
    let normal = cross(edge1,edge2); let normal_length = length(normal);
    let h = cross(direction,edge2); let determinant = dot(edge1,h);
    if determinant.abs() <= TOLERANCE * length(direction) * normal_length { return None; }
    let inverse = 1. / determinant; let delta = subtract(start,a);
    let u = inverse * dot(delta,h);
    if u < -TOLERANCE || u > 1.+TOLERANCE { return None; }
    let q = cross(delta,edge1); let v = inverse * dot(direction,q);
    if v < -TOLERANCE || u+v > 1.+TOLERANCE { return None; }
    let t = inverse * dot(edge2,q);
    if !t.is_finite() || t < -TOLERANCE || t > 1.+TOLERANCE { return None; }
    let t = if t <= 0. { 0. } else { t.min(1.) };
    Some(Hit { triangle_id,t,point:std::array::from_fn(|i| (start[i]+direction[i]*t) as f32),
               normal:normal.map(|value| (value/normal_length) as f32) })
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use std::sync::OnceLock;

    pub(crate) fn fixture(origin: f32, spacing: f32, width: usize, heights: Vec<f32>) -> Terrain {
        assert!((2..=GRID_WIDTH).contains(&width) && heights.len()==width*width);
        assert!(origin.is_finite() && spacing.is_finite() && spacing>0.);
        assert!(heights.iter().all(|height| height.is_finite() && height.abs()<=MAX_QUERY_COORDINATE));
        Terrain { heights:heights.into(),width,origin:f64::from(origin),spacing:f64::from(spacing) }
    }

    fn synthetic(width: usize, height: impl Fn(usize,usize)->f32) -> Terrain {
        let mut heights=Vec::new();
        for z in 0..width { for x in 0..width { heights.push(height(x,z)); }}
        Terrain { heights:heights.into(),width,origin:0.,spacing:1. }
    }
    fn actual() -> &'static Terrain {
        static TERRAIN: OnceLock<Terrain> = OnceLock::new();
        TERRAIN.get_or_init(|| {
            let root=std::env::var("WOT091_ROOT").unwrap_or_else(|_| "D:/WoT_9.1_Server".into());
            let local=Path::new(&root).join("local");
            Terrain::load(&local,&local.join("evidence/20261005-p02-map-drive/data/terrain-mesh-01/01_karelia/manifest.json")).unwrap()
        })
    }
    fn brute(terrain: &Terrain, start: [f32;3], end: [f32;3]) -> Option<Hit> {
        let start=start.map(f64::from);let direction=subtract(end.map(f64::from),start);
        (0..(terrain.width-1).pow(2)*2).filter_map(|id| intersect(start,direction,terrain.triangle(id),id as u32))
            .min_by(|a,b| a.t.total_cmp(&b.t).then(a.triangle_id.cmp(&b.triangle_id)))
    }

    #[test]
    fn checkerboard_reconstructs_both_source_diagonals() {
        assert_eq!(indices(3,0,0),[[0,3,4],[0,4,1]]);
        assert_eq!(indices(3,1,0),[[1,4,2],[2,4,5]]);
        assert_eq!(indices(3,0,1),[[3,6,4],[4,6,7]]);
        assert_eq!(indices(3,1,1),[[4,7,8],[4,8,5]]);
        let terrain=synthetic(3,|x,z| if x==1 && z==1 { 4. } else { 0. });
        // A bilinear surface would give 0.25 here; the actual diagonal gives1.
        assert_eq!(terrain.nearest([0.25,10.,0.25],[0.25,-10.,0.25]).unwrap().unwrap().point[1],1.);
        assert_eq!(terrain.nearest([1.75,10.,0.25],[1.75,-10.,0.25]).unwrap().unwrap().point[1],1.);
    }

    #[test]
    fn two_sided_closed_surface_has_no_underground_or_coplanar_fabrication() {
        let terrain=synthetic(3,|_,_|0.);
        let down=terrain.nearest([0.2,1.,0.3],[0.2,-1.,0.3]).unwrap().unwrap();
        let up=terrain.nearest([0.2,-1.,0.3],[0.2,1.,0.3]).unwrap().unwrap();
        assert_eq!(down,up);assert_eq!(down.t,0.5);assert_eq!(down.normal,[0.,1.,0.]);
        assert_eq!(terrain.nearest([0.2,0.,0.3],[0.2,1.,0.3]).unwrap().unwrap().t,0.);
        assert_eq!(terrain.nearest([0.2,1.,0.3],[0.2,0.,0.3]).unwrap().unwrap().t,1.);
        assert!(terrain.nearest([0.2,-1.,0.3],[1.8,-1.,0.3]).unwrap().is_none());
        assert!(terrain.nearest([0.2,0.,0.3],[1.8,0.,0.3]).unwrap().is_none());
    }

    #[test]
    fn grid_lines_corners_outer_edges_and_reversed_traversal_match_exhaustive_query() {
        let terrain=synthetic(5,|x,z| ((x*7+z*11)%9) as f32);
        let cases=[([-1.,9.,2.],[5.,-2.,2.]),([2.,9.,-1.],[2.,-2.,5.]),
            ([-1.,9.,-1.],[5.,-2.,5.]),([-1.,9.,5.],[5.,-2.,-1.]),
            ([0.,9.,0.],[0.,-2.,0.]),([4.,9.,4.],[4.,-2.,4.]),
            ([4.,9.,0.],[4.,-2.,4.]),([0.,9.,0.],[4.,-2.,0.]),
            ([1.,9.,1.],[1.,-2.,1.]),([0.99999994,9.,1.],[1.0000001,-2.,1.])];
        for (start,end) in cases {
            assert_eq!(terrain.nearest(start,end).unwrap(),brute(&terrain,start,end));
            assert_eq!(terrain.nearest(end,start).unwrap(),brute(&terrain,end,start));
        }
    }

    #[test]
    fn deterministic_varied_segments_match_exhaustive_synthetic_mesh() {
        let terrain=synthetic(9,|x,z| ((x*x+z*11+x*z*3)%19) as f32*0.2);
        let mut seed=1234567_u32;
        let mut next=|| { seed=seed.wrapping_mul(1664525).wrapping_add(1013904223); (seed>>8) as f32 / 16777216. * 12. - 2. };
        for _ in 0..256 {
            let start=[next(),next(),next()];let end=[next(),next(),next()];
            assert_eq!(terrain.nearest(start,end).unwrap(),brute(&terrain,start,end));
        }
    }

    #[test]
    fn equal_t_uses_stable_source_id_and_clone_shares_immutable_heights() {
        let terrain=synthetic(3,|_,_|0.);
        let hit=terrain.nearest([1.,2.,1.],[1.,-2.,1.]).unwrap().unwrap();
        assert_eq!(hit.triangle_id,0);
        assert!(Arc::ptr_eq(&terrain.heights,&terrain.clone().heights));
    }

    #[test]
    fn query_bounds_and_far_outside_segments_are_explicit() {
        let terrain=synthetic(3,|_,_|0.);
        for (start,end) in [([0.,0.,0.],[0.,0.,0.]),([f32::NAN,1.,0.],[0.,0.,0.]),
            ([0.,1.,0.],[0.,f32::INFINITY,0.]),([MAX_QUERY_COORDINATE+1.,0.,0.],[0.,0.,0.])] {
            assert!(terrain.nearest(start,end).is_err());
        }
        assert!(terrain.nearest([-5.,1.,-5.],[-3.,-1.,-3.]).unwrap().is_none());
        assert!(terrain.nearest([2.00001,1.,1.],[2.00001,-1.,1.]).unwrap().is_none());
        assert!(terrain.nearest([-10000.,1.,1.],[10000.,-1.,1.]).unwrap().is_some());
    }

    #[test]
    fn exact_karelia_source_loads_and_world_grid_walk_is_bounded() {
        let terrain=actual();
        assert_eq!(terrain.width,769);assert_eq!(terrain.heights.len(),591361);
        assert_eq!(terrain.vertex(0)[0],-600.);assert_eq!(terrain.vertex(591360)[2],600.);
        let cells=terrain.segment_cells([-10000.,500.,-10000.],[20000.,0.,20000.]).unwrap();
        assert!(cells.len()<=3*GRID_CELLS && cells.len()<MAX_QUERY_CELLS);
        assert!(terrain.nearest([-10000.,500.,-10000.],[10000.,500.,10000.]).unwrap().is_none());
        let local=terrain.segment_cells([-64.,40.,-441.],[1.,-50.,1.]).unwrap();
        assert!(local.len()<=4);
    }

    #[test]
    fn accepted_map_triangle_samples_are_not_bilinearly_smoothed() {
        // Independently read from the pinned exported triangle buffers using
        // tools/map_geometry.py, not generated by this Rust query. This is
        // source/export agreement, not an original native projectile oracle.
        let cases=[(-63.5,-440.8125,21.4166813659668,155822),
            (-58.5,-445.8125,20.907481307983396,151220),
            (0.25,0.75,21.12920066833496,590592),
            (-599.75,-599.25,10.415200233459473,0)];
        for (x,z,y,id) in cases {
            let hit=actual().nearest([x,200.,z],[x,-100.,z]).unwrap().unwrap();
            assert_eq!(hit.triangle_id,id);
            assert!((f64::from(hit.point[1])-y).abs()<0.00001);
            assert!((hit.t-(200.-y)/300.).abs()<1e-12);
        }
    }

    #[test]
    fn malformed_buffers_and_manifest_are_rejected_before_query() {
        assert!(Terrain::decode_buffers(&[],&[]).is_err());
        let root=std::env::temp_dir().join(format!("sr-terrain-pin-test-{}",std::process::id()));
        fs::create_dir(&root).unwrap();
        let path=root.join("manifest.json");fs::write(&path,b"{\"version\":1}").unwrap();
        assert!(Terrain::load(&root,&path).is_err());
        assert!(Terrain::load(&root,Path::new("manifest.json")).is_err());
        assert!(Terrain::load(&root,&root.join("../manifest.json")).is_err());
        // Only these exact test-owned files; no recursive cleanup.
        fs::remove_file(path).unwrap();fs::remove_dir(root).unwrap();
    }
}
