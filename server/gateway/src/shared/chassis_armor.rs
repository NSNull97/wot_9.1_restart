//! SHELL-01: chassis (track) armour of #717 vehicles and the ordered layer query.
//!
//! The chassis bundle is a separate pinned file per vehicle (tools/chassis_armor_export.py);
//! the existing Hull/Turret/Gun bundles are unchanged. `armor_layers` lists every crossing
//! of a shot segment with all four components in segment order. It assigns no armour
//! outcome: penetration, ricochet and track damage are SHELL-02 and later. The live hit
//! path (`Bundle::impact_segment`) does not use it yet.
// Consumed by the SHELL-02 resolver; until then only tests call it.
#![allow(dead_code)]
use std::{collections::BTreeMap, fs, io::{self, Read}, path::Path, sync::OnceLock};
use serde_json::Value;
use sha2::{Digest, Sha256};
use super::{collision::{self, Mesh, Triangle}, geometry::{non_reparse, Bundle}, materials::MaterialFacts, model::{bad, Actor}, pose, vehicle_profile::VehicleKind};

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

#[derive(Clone, Debug, PartialEq)]
pub struct ChassisArmor {
    pub vehicle_id: String, pub sha256: String, pub type_compact_id: u32, pub descriptor_hex: String,
    pub hull_position: [f32; 3], pub mesh: String,
    vertices: Vec<[f32; 3]>, triangles: Vec<Triangle>,
    /// A mesh label without a record here has no MaterialInfo (missing is not armour 0).
    pub materials: Vec<TrackMaterial>,
}

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
            hull_position, mesh, vertices, triangles, materials })
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
