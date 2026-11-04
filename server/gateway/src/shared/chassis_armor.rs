//! SHELL-01: chassis (track) armour of #717 vehicles and the ordered layer query.
//!
//! The chassis bundle is a separate pinned file per vehicle (tools/chassis_armor_export.py);
//! the existing Hull/Turret/Gun bundles are unchanged. `armor_layers` lists every crossing
//! of a shot segment with all four components in segment order. It assigns no armour
//! outcome. SHELL-02: a bundle bound to its geometry (`geometry::Bundle::with_chassis`,
//! optional `chassis` reference of the profile13 manifest) puts the tracks into the live
//! hit (`model.rs` → `impact::Trace::track_contact` → `p06t_damage::track_pass`).
// `armor_layers` is still test-only (the ordered all-layer resolver is a later card).
#![allow(dead_code)]
use std::{collections::BTreeMap, fs, io::{self, Read}, path::Path, sync::OnceLock};
use serde_json::Value;
use sha2::{Digest, Sha256};
use super::{collision::{self, Mesh, Triangle}, geometry::{non_reparse, Bundle}, materials::MaterialFacts, model::{bad, Actor}, pose, vehicle_profile::VehicleKind};
use crate::p06t_device_caps::Device;

include!("chassis_armor_pins.rs");
const TABLE: &[u8] = include_bytes!("../../../../config/catalog/chassis_armor.v1.json");
const MAX_BYTES: u64 = 512 * 1024;
const MAX_VERTICES: usize = 8192;
const MAX_TRIANGLES: usize = 16384;
/// Triangle IDs follow the 100000-per-component rule; the chassis is component 3.
const COMPONENT_STRIDE: u32 = 100_000;
const CHASSIS_BASE: u32 = 3 * COMPONENT_STRIDE;
const TRACKS: [(&str, u16, &str); 2] = [("leftTrack", 23, "leftTrackHealth"), ("rightTrack", 24, "rightTrackHealth")];

/// One pinned table row: the vehicle identity a chassis bundle must carry.
#[derive(Clone, Debug, PartialEq)]
struct Pin { vehicle_id: String, bytes: u64, type_compact_id: u32, descriptor_hex: String }

static PINS: OnceLock<Result<BTreeMap<String, Pin>, String>> = OnceLock::new();

fn digest(raw: &[u8]) -> String { format!("{:x}", Sha256::digest(raw)) }

fn pins() -> io::Result<&'static BTreeMap<String, Pin>> {
    PINS.get_or_init(|| parse_table(TABLE).map_err(|e| e.to_string())).as_ref()
        .map_err(|message| io::Error::new(io::ErrorKind::InvalidData, message.clone()))
}

fn parse_table(raw: &[u8]) -> io::Result<BTreeMap<String, Pin>> {
    if digest(raw) != TABLE_SHA256 { return Err(bad()); }
    let table: Value = serde_json::from_slice(raw).map_err(|_| bad())?;
    if table["schema"] != "wot091-chassis-armor.v1" { return Err(bad()); }
    let rows = table["vehicles"].as_array().filter(|r| !r.is_empty() && r.len() <= 1024).ok_or_else(bad)?;
    let mut pins = BTreeMap::new();
    for row in rows {
        if row["status"] != "generated" { continue; }
        let sha = row["sha256"].as_str().filter(|s| s.len() == 64).ok_or_else(bad)?.to_owned();
        let pin = Pin { vehicle_id: row["vehicle_id"].as_str().ok_or_else(bad)?.to_owned(),
            bytes: row["bytes"].as_u64().filter(|b| *b > 0 && *b <= MAX_BYTES).ok_or_else(bad)?,
            type_compact_id: u32::try_from(row["identity"]["type_compact_id"].as_u64().ok_or_else(bad)?).map_err(|_| bad())?,
            descriptor_hex: row["identity"]["descriptor_hex"].as_str().ok_or_else(bad)?.to_owned() };
        if pins.insert(sha, pin).is_some() { return Err(bad()); }
    }
    Ok(pins)
}

/// Track MaterialInfo as loaded by #717 `_readMaterials`/`_readArmor` (source facts only).
#[derive(Clone, Debug, PartialEq)]
pub struct TrackMaterial {
    pub name: String, pub kind: u16, pub armor_mm: f64, pub extra: String,
    /// Loader damageKind (0 armour, 1 device); `auto` maps to 1 and sets `auto_damage_kind`.
    pub damage_kind: u8, pub auto_damage_kind: bool,
    pub vehicle_damage_factor: f64, pub chance_to_hit_by_projectile: f64, pub chance_to_hit_by_explosion: f64,
    pub use_armor_homogenization: bool, pub use_hit_angle: bool, pub use_antifragmentation_lining: bool,
    pub may_ricochet: bool, pub collide_once_only: bool, pub continue_trace_if_no_hit: bool,
}
// BW-01 wire codec (tools/bw01_wire_gen.py): TrackMaterial
impl crate::bw_wire::Wire for TrackMaterial {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{name,kind,armor_mm,extra,damage_kind,auto_damage_kind,vehicle_damage_factor,chance_to_hit_by_projectile,chance_to_hit_by_explosion,use_armor_homogenization,use_hit_angle,use_antifragmentation_lining,may_ricochet,collide_once_only,continue_trace_if_no_hit}=self;W::put(name,bw_o);W::put(kind,bw_o);W::put(armor_mm,bw_o);W::put(extra,bw_o);W::put(damage_kind,bw_o);W::put(auto_damage_kind,bw_o);W::put(vehicle_damage_factor,bw_o);W::put(chance_to_hit_by_projectile,bw_o);W::put(chance_to_hit_by_explosion,bw_o);W::put(use_armor_homogenization,bw_o);W::put(use_hit_angle,bw_o);W::put(use_antifragmentation_lining,bw_o);W::put(may_ricochet,bw_o);W::put(collide_once_only,bw_o);W::put(continue_trace_if_no_hit,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{name:W::get(bw_i)?,kind:W::get(bw_i)?,armor_mm:W::get(bw_i)?,extra:W::get(bw_i)?,damage_kind:W::get(bw_i)?,auto_damage_kind:W::get(bw_i)?,vehicle_damage_factor:W::get(bw_i)?,chance_to_hit_by_projectile:W::get(bw_i)?,chance_to_hit_by_explosion:W::get(bw_i)?,use_armor_homogenization:W::get(bw_i)?,use_hit_angle:W::get(bw_i)?,use_antifragmentation_lining:W::get(bw_i)?,may_ricochet:W::get(bw_i)?,collide_once_only:W::get(bw_i)?,continue_trace_if_no_hit:W::get(bw_i)?})}
}
// end BW-01 wire codec

#[derive(Clone, Debug, PartialEq)]
pub struct ChassisArmor {
    pub vehicle_id: String, pub sha256: String, pub type_compact_id: u32, pub descriptor_hex: String,
    pub hull_position: [f32; 3], pub mesh: String,
    /// Collision `.visual` boundingBox, the bbox of the native chassis presentation
    /// segment (the same source class the Hull/Turret/Gun bundles use).
    pub visual_bounds: [[f32; 3]; 2],
    vertices: Vec<[f32; 3]>, triangles: Vec<Triangle>,
    /// A mesh label without a record here has no MaterialInfo (missing is not armour 0).
    pub materials: Vec<TrackMaterial>,
}
// BW-01 wire codec (tools/bw01_wire_gen.py): ChassisArmor
impl crate::bw_wire::Wire for ChassisArmor {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{vehicle_id,sha256,type_compact_id,descriptor_hex,hull_position,mesh,visual_bounds,vertices,triangles,materials}=self;W::put(vehicle_id,bw_o);W::put(sha256,bw_o);W::put(type_compact_id,bw_o);W::put(descriptor_hex,bw_o);W::put(hull_position,bw_o);W::put(mesh,bw_o);W::put(visual_bounds,bw_o);W::put(vertices,bw_o);W::put(triangles,bw_o);W::put(materials,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{vehicle_id:W::get(bw_i)?,sha256:W::get(bw_i)?,type_compact_id:W::get(bw_i)?,descriptor_hex:W::get(bw_i)?,hull_position:W::get(bw_i)?,mesh:W::get(bw_i)?,visual_bounds:W::get(bw_i)?,vertices:W::get(bw_i)?,triangles:W::get(bw_i)?,materials:W::get(bw_i)?})}
}
// end BW-01 wire codec

fn exact(value: &Value, keys: &[&str]) -> io::Result<()> {
    let map = value.as_object().ok_or_else(bad)?;
    if map.len() != keys.len() || keys.iter().any(|k| !map.contains_key(*k)) { return Err(bad()); }
    Ok(())
}
fn vector(value: &Value, limit: f64) -> io::Result<[f32; 3]> {
    let row = value.as_array().filter(|r| r.len() == 3).ok_or_else(bad)?;
    let mut out = [0.; 3];
    for (i, x) in row.iter().enumerate() {
        let x = x.as_f64().filter(|x| x.is_finite() && x.abs() <= limit).ok_or_else(bad)?;
        out[i] = x as f32;
    }
    Ok(out)
}
fn text(value: &Value) -> io::Result<String> {
    Ok(value.as_str().filter(|s| !s.is_empty() && s.len() <= 128).ok_or_else(bad)?.to_owned())
}
fn uint(value: &Value) -> io::Result<u32> { u32::try_from(value.as_u64().ok_or_else(bad)?).map_err(|_| bad()) }
fn fraction(value: &Value) -> io::Result<f64> { value.as_f64().filter(|x| x.is_finite() && (0. ..=1.).contains(x)).ok_or_else(bad) }
fn flag(value: &Value) -> io::Result<bool> { value.as_bool().ok_or_else(bad) }

fn track_material(value: &Value) -> io::Result<TrackMaterial> {
    exact(value, &["name", "kind", "effective"])?;
    let name = text(&value["name"])?;
    let (_, kind, extra) = *TRACKS.iter().find(|(n, _, _)| *n == name).ok_or_else(bad)?;
    if value["kind"].as_u64() != Some(u64::from(kind)) { return Err(bad()); }
    let e = &value["effective"];
    exact(e, &["armor", "auto_damage_kind", "chanceToHitByExplosion", "chanceToHitByProjectile", "collideOnceOnly",
        "continueTraceIfNoHit", "damage_kind", "extra", "kind", "mayRicochet", "useAntifragmentationLining",
        "useArmorHomogenization", "useHitAngle", "vehicleDamageFactor"])?;
    if e["kind"].as_u64() != Some(u64::from(kind)) || e["extra"] != extra { return Err(bad()); }
    let armor_mm = e["armor"].as_f64().filter(|a| a.is_finite() && (0. ..=10_000.).contains(a)).ok_or_else(bad)?;
    let damage_kind = match e["damage_kind"].as_u64() { Some(0) => 0, Some(1) => 1, _ => return Err(bad()) };
    let auto_damage_kind = flag(&e["auto_damage_kind"])?;
    if auto_damage_kind && damage_kind != 1 { return Err(bad()); }
    Ok(TrackMaterial { name, kind, armor_mm, extra: extra.into(), damage_kind, auto_damage_kind,
        vehicle_damage_factor: fraction(&e["vehicleDamageFactor"])?,
        chance_to_hit_by_projectile: fraction(&e["chanceToHitByProjectile"])?,
        chance_to_hit_by_explosion: fraction(&e["chanceToHitByExplosion"])?,
        use_armor_homogenization: flag(&e["useArmorHomogenization"])?, use_hit_angle: flag(&e["useHitAngle"])?,
        use_antifragmentation_lining: flag(&e["useAntifragmentationLining"])?, may_ricochet: flag(&e["mayRicochet"])?,
        collide_once_only: flag(&e["collideOnceOnly"])?, continue_trace_if_no_hit: flag(&e["continueTraceIfNoHit"])? })
}

impl ChassisArmor {
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

    /// Only an exact pinned export is decoded: the digest selects the row first.
    pub fn from_bytes(raw: &[u8]) -> io::Result<Self> {
        if raw.is_empty() || raw.len() as u64 > MAX_BYTES { return Err(bad()); }
        let sha256 = digest(raw);
        let pin = pins()?.get(&sha256).ok_or_else(bad)?.clone();
        if raw.len() as u64 != pin.bytes { return Err(bad()); }
        let value: Value = serde_json::from_slice(raw).map_err(|_| bad())?;
        exact(&value, &["battle_admission", "chassis", "classification", "component", "hull_position", "identity", "members", "schema", "vehicle_id"])?;
        if value["schema"] != "chassis-armor.v1" || value["battle_admission"] != false
            || value["classification"] != "VERIFIED_STATIC_ORIGINAL_717" || value["vehicle_id"] != pin.vehicle_id.as_str()
            || value["identity"]["type_compact_id"].as_u64() != Some(u64::from(pin.type_compact_id))
            || value["identity"]["descriptor_hex"] != pin.descriptor_hex.as_str() { return Err(bad()); }
        let hull_position = vector(&value["hull_position"], 10.)?;
        let c = &value["component"];
        exact(c, &["excluded_degenerate_triangle_ids", "materials", "mesh_bounds", "name", "triangles", "vertex_format", "vertices", "visual_bounds"])?;
        let mesh = text(&c["name"])?;
        let visual = c["visual_bounds"].as_array().filter(|r| r.len() == 2).ok_or_else(bad)?;
        let visual_bounds = [vector(&visual[0], 10.)?, vector(&visual[1], 10.)?];
        if (0..3).any(|i| visual_bounds[0][i] >= visual_bounds[1][i]) { return Err(bad()); }
        let vertices = c["vertices"].as_array().filter(|r| !r.is_empty() && r.len() <= MAX_VERTICES).ok_or_else(bad)?
            .iter().map(|v| vector(v, 10.)).collect::<io::Result<Vec<_>>>()?;
        let excluded = c["excluded_degenerate_triangle_ids"].as_array().ok_or_else(bad)?
            .iter().map(uint).collect::<io::Result<Vec<_>>>()?;
        let materials = c["materials"].as_array().filter(|r| !r.is_empty() && r.len() <= TRACKS.len()).ok_or_else(bad)?
            .iter().map(track_material).collect::<io::Result<Vec<_>>>()?;
        if materials.iter().enumerate().any(|(i, m)| materials[..i].iter().any(|o| o.name == m.name)) { return Err(bad()); }
        let rows = c["triangles"].as_array().filter(|r| !r.is_empty() && r.len() <= MAX_TRIANGLES).ok_or_else(bad)?;
        let mut triangles = Vec::with_capacity(rows.len());
        for (index, row) in rows.iter().enumerate() {
            exact(row, &["a", "b", "c", "group", "material", "mesh", "triangle_id"])?;
            let triangle = Triangle { triangle_id: uint(&row["triangle_id"])?, a: uint(&row["a"])?, b: uint(&row["b"])?,
                c: uint(&row["c"])?, mesh: text(&row["mesh"])?, group: text(&row["group"])?, material: text(&row["material"])? };
            if triangle.triangle_id != CHASSIS_BASE + index as u32 || triangle.mesh != mesh
                || !TRACKS.iter().any(|(n, _, _)| *n == triangle.material) { return Err(bad()); }
            // Exact zero-area triangles listed by the source are dropped; IDs are kept.
            if excluded.contains(&triangle.triangle_id) { continue; }
            triangles.push(triangle);
        }
        if excluded.iter().any(|id| *id < CHASSIS_BASE || *id >= CHASSIS_BASE + rows.len() as u32) { return Err(bad()); }
        // Mesh validation (bounds, indices, degenerate area) without trusting the export.
        Mesh::new(vertices.clone(), triangles.clone(), sha256.clone(), "chassis-local-v1")?;
        Ok(Self { vehicle_id: pin.vehicle_id, sha256, type_compact_id: pin.type_compact_id, descriptor_hex: pin.descriptor_hex,
            hull_position, mesh, visual_bounds, vertices, triangles, materials })
    }

    /// The chassis must belong to the same vehicle and frame as the Hull/Turret/Gun bundle.
    pub fn check_binding(&self, bundle: &Bundle) -> io::Result<()> {
        let kind: VehicleKind = bundle.vehicle_kind();
        let descriptor = kind.descriptor().iter().map(|b| format!("{b:02x}")).collect::<String>();
        if kind.vehicle_compact_id() != self.type_compact_id || descriptor != self.descriptor_hex
            || bundle.hull_position() != self.hull_position { return Err(bad()); }
        Ok(())
    }

    pub fn material(&self, label: &str) -> Option<&TrackMaterial> { self.materials.iter().find(|m| m.name == label) }

    /// SHELL-02: the device of a track material label (`leftTrackHealth`/`rightTrackHealth`).
    pub fn side(label: &str) -> Option<Device> {
        match label { "leftTrack" => Some(Device::LeftTrack), "rightTrack" => Some(Device::RightTrack), _ => None }
    }

    /// Farthest chassis vertex from the vehicle origin; a rotation keeps the length.
    pub fn reach_m(&self) -> f32 {
        self.vertices.iter().map(|v| v.iter().map(|x| f64::from(*x).powi(2)).sum::<f64>().sqrt()).fold(0., f64::max) as f32
    }

    /// World chassis mesh of a checked pose: vehicle frame (`direction`), no turret rotation.
    /// The caller (`geometry::Bundle::chassis_mesh`) validates the pose first.
    pub(crate) fn world_mesh_unchecked(&self, position: [f32; 3], direction: [f32; 3], transform_revision: String) -> io::Result<Mesh> {
        let vertices = self.vertices.iter().map(|&v| {
            let rotated = pose::rotate(v, direction);
            std::array::from_fn(|axis| position[axis] + rotated[axis])
        }).collect();
        Mesh::new(vertices, self.triangles.clone(), self.geometry_revision(), transform_revision)
    }

    /// SHELL-02 presentation: the chassis-local (vehicle frame) ray of one world track
    /// crossing at `t` of `start..end`, clipped to `visual_bounds` and continued behind
    /// the segment start only as far as `t`. The unquantized ray's first local surface
    /// must be the crossing point; otherwise there is no honest native segment (Err).
    pub fn visual_segment(&self, position: [f32; 3], direction: [f32; 3], start: [f32; 3], end: [f32; 3], t: f32)
        -> io::Result<super::geometry::VisualSegment> {
        use super::geometry::{clipped_line, CONTACT_TOLERANCE};
        if !t.is_finite() || !(0. ..=1.).contains(&t) { return Err(bad()); }
        let delta: [f32; 3] = std::array::from_fn(|i| end[i] - start[i]);
        let world: [f32; 3] = std::array::from_fn(|i| start[i] + t * delta[i] - position[i]);
        let point = pose::inverse_rotate(world, direction);
        let local_direction = pose::inverse_rotate(delta, direction);
        let length = local_direction.iter().map(|&x| f64::from(x).powi(2)).sum::<f64>().sqrt();
        let (from, to) = clipped_line(point, local_direction, self.visual_bounds, Some(-f64::from(t) * length))?;
        let mesh = Mesh::new(self.vertices.clone(), self.triangles.clone(), self.geometry_revision(), "chassis-component-local-v1")?;
        // The native decoder extends the decoded segment 1% at both ends.
        let a: [f32; 3] = std::array::from_fn(|i| from[i] - 0.01 * (to[i] - from[i]));
        let b: [f32; 3] = std::array::from_fn(|i| to[i] + 0.01 * (to[i] - from[i]));
        let first = collision::query(&mesh, a, b)?.into_iter().next().ok_or_else(bad)?;
        let at: [f32; 3] = std::array::from_fn(|i| a[i] + first.t * (b[i] - a[i]));
        // f32 pose round trip: allow the same order of error as the world query.
        if (0..3).any(|i| (f64::from(at[i]) - f64::from(point[i])).abs() > 100. * CONTACT_TOLERANCE) { return Err(bad()); }
        Ok(super::geometry::VisualSegment { bounds: self.visual_bounds, start: from, end: to })
    }

    /// Bounded identity of the pinned chassis bundle in a collision query.
    pub fn geometry_revision(&self) -> String { format!("chassis-v1:{}", self.sha256) }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Part { Hull, Turret, Gun, Chassis }

#[derive(Clone, Debug, PartialEq)]
pub enum LayerMaterial {
    Component(MaterialFacts),
    Track(TrackMaterial),
    /// A chassis mesh label with no local MaterialInfo record (not armour 0).
    TrackWithoutRecord,
}

/// One crossing of the segment with a source triangle, in segment order.
#[derive(Clone, Debug, PartialEq)]
pub struct Layer {
    pub order: usize, pub part: Part, pub triangle_id: u32, pub mesh: String, pub group: String, pub material: String,
    /// Segment parameter in [0, 1] and the world point.
    pub t: f32, pub point: [f32; 3],
    /// Unit normal from the source winding; winding is not verified outward.
    pub winding_normal: [f32; 3],
    /// The segment runs against the winding normal (dot < 0). Not called entry/exit:
    /// outward winding of #717 collision meshes is not established.
    pub against_winding: bool,
    /// Same reported t as the previous layer (shared edge or coincident faces).
    /// Kept, not merged: the rule for such ties belongs to SHELL-02.
    pub tied_with_previous: bool,
    pub facts: LayerMaterial,
}

/// Every crossing of `start..end` with Hull/Turret/Gun (bundle pose, turret yaw and gun
/// pitch of the actor) and the chassis (vehicle frame: no turret rotation), ordered by the
/// one collision query of the combined mesh. No outcome is assigned.
pub fn armor_layers(bundle: &Bundle, chassis: &ChassisArmor, actor: &Actor, slot: usize, tick: u32,
    start: [f32; 3], end: [f32; 3]) -> io::Result<Vec<Layer>> {
    chassis.check_binding(bundle)?;
    let (mut vertices, mut triangles, transform) = bundle.world_parts(actor, slot, tick)?;
    if triangles.iter().any(|t| t.triangle_id >= CHASSIS_BASE) { return Err(bad()); }
    let base = vertices.len() as u32;
    for &v in &chassis.vertices {
        let rotated = pose::rotate(v, actor.direction);
        vertices.push(std::array::from_fn(|axis| actor.position[axis] + rotated[axis]));
    }
    for t in &chassis.triangles {
        let mut t = t.clone(); t.a += base; t.b += base; t.c += base; triangles.push(t);
    }
    // One bounded identity for both sources (collision revisions are limited to 128 bytes).
    let revision = format!("chassis-layers:{}", digest(format!("{}+{}", bundle.geometry_revision(), chassis.sha256).as_bytes()));
    let mesh = Mesh::new(vertices, triangles, revision, transform)?;
    let hits = collision::query(&mesh, start, end)?;
    let direction: [f64; 3] = std::array::from_fn(|i| f64::from(end[i]) - f64::from(start[i]));
    let mut layers: Vec<Layer> = Vec::with_capacity(hits.len());
    for hit in hits {
        let part = match hit.triangle_id / COMPONENT_STRIDE { 0 => Part::Hull, 1 => Part::Turret, 2 => Part::Gun, 3 => Part::Chassis, _ => return Err(bad()) };
        let facts = if part == Part::Chassis {
            chassis.material(&hit.material).cloned().map_or(LayerMaterial::TrackWithoutRecord, LayerMaterial::Track)
        } else {
            LayerMaterial::Component(bundle.materials().lookup(&hit.mesh, &hit.material)?)
        };
        let dot = (0..3).map(|i| direction[i] * f64::from(hit.normal[i])).sum::<f64>();
        let tied = layers.last().is_some_and(|previous| previous.t.to_bits() == hit.t.to_bits());
        let point = std::array::from_fn(|i| start[i] + hit.t * (end[i] - start[i]));
        layers.push(Layer { order: layers.len(), part, triangle_id: hit.triangle_id, mesh: hit.mesh, group: hit.group,
            material: hit.material, t: hit.t, point, winding_normal: hit.normal, against_winding: dot < 0.,
            tied_with_previous: tied, facts });
    }
    Ok(layers)
}

#[cfg(test)]
#[path = "chassis_armor_tests.rs"]
mod tests;
