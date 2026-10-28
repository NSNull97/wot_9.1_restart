//! VIS-PERF equivalence: `any_hit_excluding_many` returns exactly what
//! `nearest_excluding_many(..).is_some()` returns (or the same error), and the
//! Vec supercover gives the same nearest ground hit as the former BTreeSet walk,
//! on the pinned Karelia and Prohorovka worlds with their obstacle meshes.
use super::*;
use std::collections::BTreeSet;

struct Lcg(u64);
impl Lcg {
    fn unit(&mut self) -> f32 {
        self.0 = self.0.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        (self.0 >> 40) as f32 / (1u64 << 24) as f32
    }
    fn range(&mut self, low: f32, high: f32) -> f32 { low + (high - low) * self.unit() }
}

/// The former nearest-ground walk, kept verbatim as the reference.
fn old_nearest_ground(terrain: &Terrain, start: [f32; 3], end: [f32; 3]) -> io::Result<Option<Hit>> {
    if start.into_iter().chain(end).any(|v| !v.is_finite() || v.abs() > MAX_QUERY_COORDINATE) {
        return Err(bad("terrain segment finite/coordinate bound"));
    }
    let start = start.map(f64::from); let end = end.map(f64::from);
    let direction = subtract(end, start);
    if length(direction) == 0. { return Err(bad("terrain zero segment")); }
    let cells = old_segment_cells(terrain, start, direction)?;
    let mut nearest: Option<Hit> = None;
    for cell in cells {
        for local in 0..2 {
            let id = cell * 2 + local;
            if let Some(hit) = intersect(start, direction, terrain.triangle(id), id as u32) {
                let replace = nearest.as_ref().is_none_or(|old| hit.t.total_cmp(&old.t).then(hit.triangle_id.cmp(&old.triangle_id)).is_lt());
                if replace { nearest = Some(hit); }
            }
        }
    }
    Ok(nearest)
}
fn old_segment_cells(terrain: &Terrain, start: [f64; 3], direction: [f64; 3]) -> io::Result<BTreeSet<usize>> {
    let count = terrain.width - 1;
    let maximum = terrain.origin + count as f64 * terrain.spacing;
    let (mut enter, mut leave) = (0.0_f64, 1.0_f64);
    for axis in [0, 2] {
        if direction[axis] == 0. {
            if start[axis] < terrain.origin || start[axis] > maximum { return Ok(BTreeSet::new()); }
        } else {
            let a = (terrain.origin - start[axis]) / direction[axis];
            let b = (maximum - start[axis]) / direction[axis];
            enter = enter.max(a.min(b)); leave = leave.min(a.max(b));
            if enter > leave { return Ok(BTreeSet::new()); }
        }
    }
    let mut crossings = vec![enter, leave];
    for axis in [0, 2] {
        if direction[axis] == 0. { continue; }
        let a = (start[axis] + direction[axis] * enter - terrain.origin) / terrain.spacing;
        let b = (start[axis] + direction[axis] * leave - terrain.origin) / terrain.spacing;
        let first = a.min(b).ceil().max(0.) as usize;
        let last = a.max(b).floor().min(count as f64) as usize;
        for line in first..=last {
            let t = (terrain.origin + line as f64 * terrain.spacing - start[axis]) / direction[axis];
            if t >= enter && t <= leave { crossings.push(t); }
        }
    }
    if crossings.len() > max_query_crossings(terrain.width) { return Err(bad("terrain crossing bound")); }
    crossings.sort_by(f64::total_cmp);
    crossings.dedup();
    let mut cells = BTreeSet::new();
    let mut add = |t: f64| -> io::Result<()> {
        let neighbors = |axis: usize| {
            let grid = (start[axis] + direction[axis] * t - terrain.origin) / terrain.spacing;
            let base = grid.floor() as isize;
            let rounded = grid.round();
            if (grid - rounded).abs() <= GRID_BOUNDARY_TOLERANCE { [rounded as isize - 1, rounded as isize] } else { [base, base] }
        };
        for x in neighbors(0) { for z in neighbors(2) {
            if x >= 0 && z >= 0 && x < count as isize && z < count as isize {
                cells.insert(z as usize * count + x as usize);
                if cells.len() > max_query_cells(terrain.width) { return Err(bad("terrain visited-cell bound")); }
            }
        }}
        Ok(())
    };
    for &t in &crossings { add(t)?; }
    for window in crossings.windows(2) { add(window[0] + (window[1] - window[0]) * 0.5)?; }
    Ok(cells)
}

fn same<T: PartialEq + std::fmt::Debug>(new: io::Result<T>, old: io::Result<T>, what: &str) {
    match (new, old) {
        (Ok(a), Ok(b)) => assert_eq!(a, b, "{what}"),
        (Err(a), Err(b)) => assert_eq!(a.to_string(), b.to_string(), "{what}"),
        (a, b) => panic!("{what}: new {a:?} old {b:?}"),
    }
}

#[derive(Default, Debug)]
struct Tally { rays: usize, blocked: usize, clear: usize, obstacle_first: usize, excluded_rechecks: usize, errors: usize }

/// One ray through every query pair; an obstacle hit is rechecked with its
/// instance excluded (the destructible/fragile exclusion path of spotting).
fn check(world: &Terrain, start: [f32; 3], end: [f32; 3], excluded: &[u32], tally: &mut Tally) {
    let what = format!("{:?} {start:?} -> {end:?} excluded {excluded:?}", world.map_id());
    same(world.nearest_ground(start, end), old_nearest_ground(world, start, end), &what);
    let nearest = world.nearest_excluding_many(start, end, excluded);
    let flag = nearest.as_ref().map(|hit| hit.is_some()).map_err(|e| io::Error::new(e.kind(), e.to_string()));
    same(world.any_hit_excluding_many(start, end, excluded), flag, &what);
    if let Some(mesh) = &world.obstacles {
        same(mesh.any_hit_excluding_many(start, end, excluded), mesh.nearest_excluding_many(start, end, excluded).map(|hit| hit.is_some()), &what);
    }
    tally.rays += 1;
    match nearest {
        Err(_) => tally.errors += 1,
        Ok(None) => tally.clear += 1,
        Ok(Some(hit)) => {
            tally.blocked += 1;
            if let Surface::StaticObstacle { instance_id, .. } = hit.surface {
                tally.obstacle_first += 1;
                if excluded.is_empty() { tally.excluded_rechecks += 1; check(world, start, end, &[instance_id], tally); }
            }
        }
    }
}

fn worlds() -> [Terrain; 2] {
    [super::tests::actual().clone().with_obstacles(Arc::new(super::super::obstacles::tests::actual().clone())).unwrap(),
     super::tests::actual_prohorovka().clone().with_obstacles(Arc::new(super::super::obstacles::tests::actual_prohorovka().clone())).unwrap()]
}
fn ground_y(world: &Terrain, x: f32, z: f32) -> f32 {
    world.nearest_ground([x, 2000., z], [x, -2000., z]).unwrap().map_or(0., |hit| hit.point[1])
}

#[test]
fn any_hit_equals_nearest_on_visibility_rays_of_pinned_worlds() {
    for (index, world) in worlds().iter().enumerate() {
        let mut rng = Lcg(0x5eed_0000 + index as u64); let mut tally = Tally::default();
        for _ in 0..3000 {
            // Spotting geometry: hull-height points within the 445 m maximum.
            let (x, z) = (rng.range(-560., 560.), rng.range(-560., 560.));
            let start = [x, ground_y(world, x, z) + rng.range(0.3, 4.), z];
            let (angle, distance) = (rng.range(-std::f32::consts::PI, std::f32::consts::PI), rng.range(1., 445.));
            let (ex, ez) = (x + angle.sin() * distance, z + angle.cos() * distance);
            let end = [ex, ground_y(world, ex.clamp(-599., 599.), ez.clamp(-599., 599.)) + rng.range(0., 4.), ez];
            check(world, start, end, &[], &mut tally);
        }
        println!("VISPERF_EQUIV visibility {:?} {tally:?}", world.map_id());
        assert!(tally.blocked > 300 && tally.clear > 300 && tally.obstacle_first > 50 && tally.errors == 0, "{tally:?}");
    }
}

#[test]
fn any_hit_equals_nearest_on_long_outside_axis_and_error_rays() {
    for (index, world) in worlds().iter().enumerate() {
        let mut rng = Lcg(0xa11_0000 + index as u64); let mut tally = Tally::default();
        for _ in 0..1500 {
            // Arbitrary segments, many longer than the fast-path cell budget,
            // partly or wholly outside the exported square.
            let start = [rng.range(-900., 900.), rng.range(-80., 300.), rng.range(-900., 900.)];
            let end = [rng.range(-900., 900.), rng.range(-80., 300.), rng.range(-900., 900.)];
            check(world, start, end, &[], &mut tally);
        }
        let spacing = world.spacing as f32; let origin = world.origin as f32;
        for line in [0usize, 1, 17, 400, world.width - 2, world.width - 1] {
            // Exactly on grid lines and corners, both directions, and vertical.
            let g = origin + line as f32 * spacing;
            for (start, end) in [([g, 150., -500.], [g, 60., 500.]), ([-500., 150., g], [500., 60., g]), ([g, 150., g], [g + 300., 40., g + 300.]),
                ([g + 300., 40., g + 300.], [g, 150., g]), ([g, 500., g], [g, -500., g]), ([g, 120., g], [g + 0.001, 120., g])] {
                check(world, start, end, &[], &mut tally);
            }
        }
        let first = 0_u32;
        for (start, end, excluded) in [([0., 100., 0.], [0., 100., 0.], vec![]), ([0., 1e5, 0.], [1., 1., 1.], vec![]), ([f32::NAN, 0., 0.], [1., 1., 1.], vec![]),
            ([0., 100., 0.], [10., 0., 10.], vec![first, first]), ([0., 100., 0.], [10., 0., 10.], vec![u32::MAX]), ([0., 100., 0.], [10., 0., 10.], vec![5, 3])] {
            check(world, start, end, &excluded, &mut tally);
        }
        let bare = Terrain { obstacles: None, ..world.clone() };
        check(&bare, [0., 100., 0.], [10., 0., 10.], &[1], &mut tally);
        check(&bare, [0., 100., 0.], [300., 0., 300.], &[], &mut tally);
        println!("VISPERF_EQUIV long/axis/errors {:?} {tally:?}", world.map_id());
        assert!(tally.errors >= 7 && tally.blocked > 100 && tally.clear > 100, "{tally:?}");
    }
}

#[test]
fn any_hit_equals_nearest_on_synthetic_meshes_with_exhaustive_reference() {
    let terrain = super::tests::fixture(-3., 0.75, 9, (0..81).map(|i| ((i * 37 % 11) as f32 - 5.) * 0.4).collect());
    let mut rng = Lcg(7); let mut tally = Tally::default();
    for _ in 0..4000 {
        let start = [rng.range(-5., 5.), rng.range(-3., 3.), rng.range(-5., 5.)];
        let end = [rng.range(-5., 5.), rng.range(-3., 3.), rng.range(-5., 5.)];
        check(&terrain, start, end, &[], &mut tally);
    }
    assert!(tally.blocked > 500 && tally.clear > 500, "{tally:?}");
}
