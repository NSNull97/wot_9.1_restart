//! Bounded world-space segment/triangle intersection primitives.
//!
//! This module knows nothing about vehicles, armor, local transforms or damage.
//! Revision strings are caller-supplied provenance labels, not proof that a
//! mesh/transform was measured. Normals follow source triangle winding; their
//! outward orientation is not established here.

use std::collections::HashSet;
use std::io;

pub const MAX_VERTICES: usize = 4096;
pub const MAX_TRIANGLES: usize = 8192;
pub const MAX_CANDIDATES: usize = 128;
pub const MAX_REVISION_BYTES: usize = 128;
pub const MAX_COORDINATE: f32 = 100_000.0;
// Inputs are f32 facts, promoted before subtraction/multiplication. Query
// arithmetic is f64, so coordinate magnitudes do not also become area bounds.
// Degeneracy rejects sin(angle(edge1, edge2)) <= 1e-12; parallel rejection uses
// |dot(direction, normal)| / (|direction| |normal|) <= 1e-12. These relative
// tolerances are invariant under uniform scaling. Coplanar overlap has no
// unique point intersection and produces no candidate.
const ANGULAR_TOLERANCE: f64 = 1e-12;
// Closed boundaries allow this dimensionless arithmetic tolerance in u/v/t;
// accepted t is clamped to [0, 1]. This is not shell radius or hitbox inflation.
const PARAMETER_TOLERANCE: f64 = 1e-12;

fn invalid(reason: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, reason)
}

fn bounded(v: [f32; 3]) -> bool {
    v.iter().all(|value| value.is_finite() && value.abs() <= MAX_COORDINATE)
}

fn wide(v: [f32; 3]) -> [f64; 3] { v.map(f64::from) }

fn sub(a: [f64; 3], b: [f64; 3]) -> [f64; 3] { [a[0] - b[0], a[1] - b[1], a[2] - b[2]] }

fn cross(a: [f64; 3], b: [f64; 3]) -> [f64; 3] {
    [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
}

fn dot(a: [f64; 3], b: [f64; 3]) -> f64 { a[0] * b[0] + a[1] * b[1] + a[2] * b[2] }

fn length(v: [f64; 3]) -> f64 { dot(v, v).sqrt() }

#[derive(Clone, Debug, PartialEq)]
pub struct Triangle {
    pub triangle_id: u32,
    pub a: u32,
    pub b: u32,
    pub c: u32,
    pub mesh: String,
    pub group: String,
    pub material: String,
}

#[derive(Clone, Debug, PartialEq)]
pub struct Mesh {
    // Private storage prevents bypassing validation or mutating validated
    // triangle indices into a query panic.
    vertices: Vec<[f32; 3]>,
    triangles: Vec<Triangle>,
    geometry_revision: String,
    transform_revision: String,
}

impl Mesh {
    pub fn new(vertices: Vec<[f32; 3]>, triangles: Vec<Triangle>,
        geometry_revision: impl Into<String>, transform_revision: impl Into<String>) -> io::Result<Self> {
        if vertices.is_empty() || vertices.len() > MAX_VERTICES || triangles.is_empty()
            || triangles.len() > MAX_TRIANGLES { return Err(invalid("collision mesh bound")); }
        let geometry_revision = geometry_revision.into();
        let transform_revision = transform_revision.into();
        if geometry_revision.is_empty() || geometry_revision.len() > MAX_REVISION_BYTES
            || transform_revision.is_empty() || transform_revision.len() > MAX_REVISION_BYTES {
            return Err(invalid("collision revision bound"));
        }
        if vertices.iter().any(|v| !bounded(*v)) { return Err(invalid("collision vertex facts")); }
        let mut triangle_ids = HashSet::with_capacity(triangles.len());
        for triangle in &triangles {
            if !triangle_ids.insert(triangle.triangle_id) || triangle.a as usize >= vertices.len()
                || triangle.b as usize >= vertices.len() || triangle.c as usize >= vertices.len()
                || triangle.a == triangle.b || triangle.b == triangle.c || triangle.a == triangle.c
                || triangle.mesh.is_empty() || triangle.group.is_empty() || triangle.material.is_empty()
                || triangle.mesh.len() > MAX_REVISION_BYTES || triangle.group.len() > MAX_REVISION_BYTES
                || triangle.material.len() > MAX_REVISION_BYTES {
                return Err(invalid("collision triangle facts"));
            }
            let a = wide(vertices[triangle.a as usize]);
            let edge1 = sub(wide(vertices[triangle.b as usize]), a);
            let edge2 = sub(wide(vertices[triangle.c as usize]), a);
            let area = length(cross(edge1, edge2));
            let edge_scale = length(edge1) * length(edge2);
            if edge_scale == 0.0 || area <= ANGULAR_TOLERANCE * edge_scale {
                return Err(invalid("degenerate collision triangle"));
            }
        }
        Ok(Self { vertices, triangles, geometry_revision, transform_revision })
    }

    pub fn geometry_revision(&self) -> &str { &self.geometry_revision }
    pub fn transform_revision(&self) -> &str { &self.transform_revision }
}

#[derive(Clone, Debug, PartialEq)]
pub struct Candidate {
    pub candidate_index: usize,
    pub triangle_id: u32,
    pub mesh: String,
    pub group: String,
    pub material: String,
    /// Unit normal from source triangle winding, without outward correction.
    pub normal: [f32; 3],
    pub t: f32,
}

/// Query a finite closed segment against supplied world-space triangles from
/// either face. Sort by f64 segment parameter, then unique source triangle ID
/// (sparse IDs are preserved). Shared edges can report distinct triangles at
/// equal t; no guessed surface/armor deduplication occurs. Capacity overflow
/// returns an error, never an incomplete candidate list.
pub fn query(mesh: &Mesh, start: [f32; 3], end: [f32; 3]) -> io::Result<Vec<Candidate>> {
    if !bounded(start) || !bounded(end) { return Err(invalid("collision segment facts")); }
    let start = wide(start);
    let direction = sub(wide(end), start);
    let direction_length = length(direction);
    if direction_length == 0.0 { return Err(invalid("zero collision segment")); }
    let mut hits = Vec::new();
    for triangle in &mesh.triangles {
        let a = wide(mesh.vertices[triangle.a as usize]);
        let b = wide(mesh.vertices[triangle.b as usize]);
        let c = wide(mesh.vertices[triangle.c as usize]);
        let edge1 = sub(b, a); let edge2 = sub(c, a);
        let raw_normal = cross(edge1, edge2);
        let normal_length = length(raw_normal);
        let h = cross(direction, edge2);
        let determinant = dot(edge1, h);
        if determinant.abs() <= ANGULAR_TOLERANCE * direction_length * normal_length { continue; }
        let inverse = 1.0 / determinant;
        let s = sub(start, a);
        let u = inverse * dot(s, h);
        if u < -PARAMETER_TOLERANCE || u > 1.0 + PARAMETER_TOLERANCE { continue; }
        let q = cross(s, edge1);
        let v = inverse * dot(direction, q);
        if v < -PARAMETER_TOLERANCE || u + v > 1.0 + PARAMETER_TOLERANCE { continue; }
        let t = inverse * dot(edge2, q);
        if !t.is_finite() || t < -PARAMETER_TOLERANCE || t > 1.0 + PARAMETER_TOLERANCE { continue; }
        if hits.len() == MAX_CANDIDATES { return Err(invalid("collision candidate bound")); }
        let normal = raw_normal.map(|value| (value / normal_length) as f32);
        // Canonicalize signed zero so an endpoint tie still sorts by ID even
        // when adjacent source triangles have opposing winding.
        let t = if t <= 0.0 { 0.0 } else { t.min(1.0) };
        hits.push((t, Candidate { candidate_index: 0, triangle_id: triangle.triangle_id,
            mesh: triangle.mesh.clone(), group: triangle.group.clone(), material: triangle.material.clone(),
            normal, t: t as f32 }));
    }
    hits.sort_by(|(left_t, left), (right_t, right)| left_t.total_cmp(right_t)
        .then_with(|| left.triangle_id.cmp(&right.triangle_id)));
    Ok(hits.into_iter().enumerate().map(|(index, (_, mut candidate))| {
        candidate.candidate_index = index;
        candidate
    }).collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn triangle(id: u32, a: u32, b: u32, c: u32, group: &str, material: &str) -> Triangle {
        Triangle { triangle_id: id, a, b, c, mesh: "Hull.model".into(), group: group.into(), material: material.into() }
    }

    #[test]
    fn ordered_hit_has_finite_normal_and_material_identity() {
        let mesh = Mesh::new(vec![[0., 0., 0.], [0., 1., 0.], [0., 0., 1.],
                [1., 0., 0.], [1., 1., 0.], [1., 0., 1.]],
            vec![triangle(0, 0, 1, 2, "armor_1", "armor_1"), triangle(1, 3, 4, 5, "armor_8", "armor_8")],
            "synthetic-two-planes-v1", "synthetic-world-identity-v1").unwrap();
        let hits = query(&mesh, [-1.0, 0.25, 0.25], [2.0, 0.25, 0.25]).unwrap();
        assert_eq!(hits.len(), 2);
        assert_eq!((hits[0].candidate_index, hits[0].triangle_id), (0, 0));
        assert!(hits[0].t < hits[1].t && hits[0].normal.iter().all(|value| value.is_finite()));
        assert_eq!(hits[1].material, "armor_8");
    }

    #[test]
    fn invalid_geometry_and_segment_fail_closed() {
        assert!(Mesh::new(vec![[0., 0., 0.], [1., 0., 0.], [2., 0., 0.]],
            vec![triangle(0, 0, 1, 2, "armor_1", "armor_1")], "geometry", "transform").is_err());
        let mesh = Mesh::new(vec![[0., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
            vec![triangle(0, 0, 1, 2, "armor_1", "armor_1")], "geometry", "transform").unwrap();
        assert!(query(&mesh, [0., 0., 0.], [0., 0., 0.]).is_err());
        assert!(query(&mesh, [f32::NAN, 0., 0.], [1., 1., 1.]).is_err());
    }

    #[test]
    fn triangle_ids_must_be_unique_and_revisions_explicit() {
        assert!(Mesh::new(vec![[0., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
            vec![triangle(3, 0, 1, 2, "armor_1", "armor_1")], "geometry", "transform").is_ok());
        assert!(Mesh::new(vec![[0., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
            vec![triangle(3, 0, 1, 2, "armor_1", "armor_1"), triangle(3, 0, 2, 1, "armor_2", "armor_2")],
            "geometry", "transform").is_err());
        assert!(Mesh::new(vec![[0., 0., 0.], [0., 1., 0.], [0., 0., 1.]],
            vec![triangle(1, 0, 1, 2, "armor_1", "armor_1")], "", "transform").is_err());
    }

    #[test]
    fn sparse_source_ids_sort_by_distance_and_reverse_preserves_winding() {
        let mesh = Mesh::new(vec![[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0],
                [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [1.0, 0.0, 1.0]],
            vec![triangle(2, 3, 5, 4, "armor_8", "steel"), triangle(91, 0, 1, 2, "armor_1", "steel")],
            "geometry-v1", "world-transform-v1").unwrap();
        assert_eq!(mesh.geometry_revision(), "geometry-v1");
        assert_eq!(mesh.transform_revision(), "world-transform-v1");
        let hits = query(&mesh, [-1.0, 0.25, 0.25], [2.0, 0.25, 0.25]).unwrap();
        assert_eq!(hits.iter().map(|hit| (hit.candidate_index, hit.triangle_id)).collect::<Vec<_>>(),
            vec![(0, 91), (1, 2)]);
        assert!(hits[0].t < hits[1].t);
        assert_eq!(hits[0].normal, [1.0, 0.0, 0.0]);
        assert_eq!(hits[1].normal, [-1.0, 0.0, 0.0]);
        assert_eq!((&*hits[1].mesh, &*hits[1].group, &*hits[1].material), ("Hull.model", "armor_8", "steel"));
        let reverse = query(&mesh, [2.0, 0.25, 0.25], [-1.0, 0.25, 0.25]).unwrap();
        assert_eq!(reverse.iter().map(|hit| hit.triangle_id).collect::<Vec<_>>(), vec![2, 91]);
        assert_eq!(reverse[0].normal, hits[1].normal);
    }

    #[test]
    fn endpoints_vertices_and_shared_edge_are_closed_and_ties_are_deterministic() {
        let mesh = Mesh::new(vec![[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 1.0, 1.0], [0.0, 0.0, 1.0]],
            vec![triangle(70, 0, 1, 2, "armor_1", "steel"), triangle(4, 0, 3, 2, "armor_1", "steel")],
            "g", "t").unwrap();
        for (start, end, expected_t) in [
            ([-1.0, 0.5, 0.5], [1.0, 0.5, 0.5], 0.5),
            ([0.0, 0.5, 0.5], [1.0, 0.5, 0.5], 0.0),
            ([-1.0, 0.5, 0.5], [0.0, 0.5, 0.5], 1.0),
            ([-1.0, 0.0, 0.0], [1.0, 0.0, 0.0], 0.5),
        ] {
            let hits = query(&mesh, start, end).unwrap();
            assert_eq!(hits.iter().map(|hit| (hit.triangle_id, hit.t)).collect::<Vec<_>>(),
                vec![(4, expected_t), (70, expected_t)]);
        }
    }

    #[test]
    fn misses_parallel_coplanar_and_outside_segment_do_not_invent_candidates() {
        let mesh = Mesh::new(vec![[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            vec![triangle(17, 0, 1, 2, "armor_1", "steel")], "g", "t").unwrap();
        for (start, end) in [
            ([-1.0, 0.75, 0.75], [1.0, 0.75, 0.75]),
            ([-1.0, -0.001, 0.25], [1.0, -0.001, 0.25]),
            ([1.0, 0.25, 0.25], [2.0, 0.25, 0.25]),
            ([-2.0, 0.25, 0.25], [-1.0, 0.25, 0.25]),
            ([1.0, 0.0, 0.0], [1.0, 1.0, 0.0]),
            ([0.0, 0.0, 0.0], [0.0, 1.0, 0.0]),
        ] { assert!(query(&mesh, start, end).unwrap().is_empty()); }
    }

    #[test]
    fn scaling_large_area_and_small_geometry_keep_the_same_intersection() {
        for scale in [1e-9_f32, 1.0, 100_000.0] {
            let mesh = Mesh::new(vec![[0.0, 0.0, 0.0], [0.0, scale, 0.0], [0.0, 0.0, scale]],
                vec![triangle(17, 0, 1, 2, "armor_1", "steel")], "g", "t").unwrap();
            let hits = query(&mesh, [-scale, scale * 0.25, scale * 0.25],
                [scale, scale * 0.25, scale * 0.25]).unwrap();
            assert_eq!(hits.len(), 1);
            assert_eq!(hits[0].t, 0.5);
            assert_eq!(hits[0].normal, [1.0, 0.0, 0.0]);
        }
    }

    #[test]
    fn invalid_indices_labels_and_degenerate_geometry_are_constructor_errors() {
        let vertices = vec![[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]];
        for triangles in [
            vec![triangle(1, 0, 1, 3, "armor_1", "steel")],
            vec![triangle(1, 0, 0, 2, "armor_1", "steel")],
            vec![triangle(1, 0, 1, 2, "", "steel")],
            vec![triangle(1, 0, 1, 2, "armor_1", &"x".repeat(MAX_REVISION_BYTES + 1))],
        ] { assert!(Mesh::new(vertices.clone(), triangles, "g", "t").is_err()); }
        for (geometry, transform) in [("g".to_owned(), "".to_owned()),
            ("x".repeat(MAX_REVISION_BYTES + 1), "t".to_owned())] {
            assert!(Mesh::new(vertices.clone(), vec![triangle(1, 0, 1, 2, "armor_1", "steel")], geometry, transform).is_err());
        }
        for vertices in [vec![[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
            vec![[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [2.0, 0.0, 0.0]],
            vec![[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1e-13, 0.0]]] {
            assert!(Mesh::new(vertices, vec![triangle(1, 0, 1, 2, "armor_1", "steel")], "g", "t").is_err());
        }
    }

    #[test]
    fn nonfinite_out_of_bounds_and_zero_segments_fail_closed() {
        let mesh = Mesh::new(vec![[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            vec![triangle(17, 0, 1, 2, "armor_1", "steel")], "g", "t").unwrap();
        assert!(query(&mesh, [0.0; 3], [0.0; 3]).is_err());
        for value in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, MAX_COORDINATE + 1.0] {
            assert!(query(&mesh, [value, 0.25, 0.25], [1.0, 0.25, 0.25]).is_err());
            assert!(query(&mesh, [-1.0, 0.25, 0.25], [value, 0.25, 0.25]).is_err());
            assert!(Mesh::new(vec![[value, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
                vec![triangle(1, 0, 1, 2, "armor_1", "steel")], "g", "t").is_err());
        }
    }

    #[test]
    fn candidate_capacity_is_exact_and_overflow_never_returns_partial_hits() {
        let make = |count: usize| {
            let mut vertices = Vec::new();
            let mut triangles = Vec::new();
            for index in 0..count {
                let x = index as f32;
                let base = vertices.len() as u32;
                vertices.extend([[x, 0.0, 0.0], [x, 1.0, 0.0], [x, 0.0, 1.0]]);
                triangles.push(triangle(1000 + index as u32 * 3, base, base + 1, base + 2, "armor_1", "steel"));
            }
            Mesh::new(vertices, triangles, "g", "t").unwrap()
        };
        let start = [-1.0, 0.25, 0.25];
        let end = [MAX_CANDIDATES as f32 + 1.0, 0.25, 0.25];
        assert_eq!(query(&make(MAX_CANDIDATES), start, end).unwrap().len(), MAX_CANDIDATES);
        assert!(query(&make(MAX_CANDIDATES + 1), start, end).is_err());
    }

    #[test]
    fn geometry_storage_bounds_reject_before_query() {
        let vertices = vec![[0.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]];
        let triangles = vec![triangle(1, 0, 1, 2, "armor_1", "steel")];
        assert!(Mesh::new(Vec::new(), triangles.clone(), "g", "t").is_err());
        assert!(Mesh::new(vertices.clone(), Vec::new(), "g", "t").is_err());
        assert!(Mesh::new(vec![[0.0; 3]; MAX_VERTICES + 1], triangles, "g", "t").is_err());
        let too_many = (0..=MAX_TRIANGLES).map(|id| triangle(id as u32, 0, 1, 2, "armor_1", "steel")).collect();
        assert!(Mesh::new(vertices, too_many, "g", "t").is_err());
    }
}
