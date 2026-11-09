//! Internal module and crew volumes of one vehicle, built by `tools/module_volumes.py` from the
//! penetration-zone skins of the 0.9.x era (owner 2026-11-09). The #717 client carries no such
//! volumes, so these are the skin authors' estimate (`project.module-volumes-from-skins.v1`),
//! never server data. A module or seat without a volume stays on its LAB box. Boxes are in the
//! component frame of the collision model. The file is pinned by the stand manifest.
use std::{fs, io::{self, Read}, path::Path};
use serde_json::Value;
use sha2::{Digest, Sha256};
use crate::p06t_device_caps::Device;

pub const SCHEMA: &str = "wot091-module-volumes.v1";
pub const POLICY: &str = "project.module-volumes-from-skins.v1";
const MAX_BYTES: u64 = 512 * 1024;
const MAX_BOXES: usize = 64;
const MAX_SEATS: usize = 8;
/// Allowed difference between the file's collision box and the bundle's collision mesh extents.
const BOUNDS_TOLERANCE_M: f32 = 0.01;

fn bad() -> io::Error { io::Error::new(io::ErrorKind::InvalidData, "invalid module volumes") }

#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Aabb { pub low: [f32; 3], pub high: [f32; 3] }
// BW-01 wire codec (tools/bw01_wire_gen.py): Aabb
impl crate::bw_wire::Wire for Aabb {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{low,high}=self;W::put(low,bw_o);W::put(high,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{low:W::get(bw_i)?,high:W::get(bw_i)?})}
}
// end BW-01 wire codec
#[derive(Clone, Debug, PartialEq, Default)]
pub struct Component { pub bounds: Option<Aabb>, pub ammo: Vec<Aabb>, pub engine: Vec<Aabb>, pub fuel: Vec<Aabb>, pub crew: Vec<Vec<Aabb>> }
// BW-01 wire codec (tools/bw01_wire_gen.py): Component
impl crate::bw_wire::Wire for Component {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{bounds,ammo,engine,fuel,crew}=self;W::put(bounds,bw_o);W::put(ammo,bw_o);W::put(engine,bw_o);W::put(fuel,bw_o);W::put(crew,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{bounds:W::get(bw_i)?,ammo:W::get(bw_i)?,engine:W::get(bw_i)?,fuel:W::get(bw_i)?,crew:W::get(bw_i)?})}
}
// end BW-01 wire codec
#[derive(Clone, Debug, PartialEq)]
pub struct ModuleVolumes { pub vehicle: String, pub sha256: String, pub hull: Component, pub turret: Component }
// BW-01 wire codec (tools/bw01_wire_gen.py): ModuleVolumes
impl crate::bw_wire::Wire for ModuleVolumes {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{vehicle,sha256,hull,turret}=self;W::put(vehicle,bw_o);W::put(sha256,bw_o);W::put(hull,bw_o);W::put(turret,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{vehicle:W::get(bw_i)?,sha256:W::get(bw_i)?,hull:W::get(bw_i)?,turret:W::get(bw_i)?})}
}
// end BW-01 wire codec

fn exact(value: &Value, keys: &[&str]) -> io::Result<()> {
    let map = value.as_object().ok_or_else(bad)?;
    if map.len() != keys.len() || keys.iter().any(|k| !map.contains_key(*k)) { return Err(bad()); }
    Ok(())
}
fn triple(value: &Value) -> io::Result<[f32; 3]> {
    let row = value.as_array().filter(|r| r.len() == 3).ok_or_else(bad)?;
    let mut out = [0f32; 3];
    for (slot, item) in out.iter_mut().zip(row) {
        *slot = item.as_f64().filter(|v| v.is_finite() && v.abs() <= 32.).ok_or_else(bad)? as f32;
    }
    Ok(out)
}
fn aabb(value: &Value) -> io::Result<Aabb> {
    let row = value.as_array().filter(|r| r.len() == 2).ok_or_else(bad)?;
    let (low, high) = (triple(&row[0])?, triple(&row[1])?);
    if (0..3).any(|i| low[i] >= high[i]) { return Err(bad()); }
    Ok(Aabb { low, high })
}
fn boxes(value: &Value) -> io::Result<Vec<Aabb>> {
    if value.is_null() { return Ok(Vec::new()); }
    let rows = value.as_array().filter(|r| !r.is_empty() && r.len() <= MAX_BOXES).ok_or_else(bad)?;
    rows.iter().map(aabb).collect()
}
fn component(value: &Value) -> io::Result<Component> {
    if value.is_null() { return Ok(Component::default()); }
    exact(value, &["box", "volumes"])?;
    let volumes = value["volumes"].as_object().filter(|m| !m.is_empty()).ok_or_else(bad)?;
    if volumes.keys().any(|k| !["ammo", "engine", "fuel", "crew"].contains(&k.as_str())) { return Err(bad()); }
    let v = &value["volumes"];
    let crew = if v["crew"].is_null() { Vec::new() } else {
        v["crew"].as_array().filter(|r| !r.is_empty() && r.len() <= MAX_SEATS).ok_or_else(bad)?.iter().map(boxes).collect::<io::Result<Vec<_>>>()?
    };
    if crew.iter().any(Vec::is_empty) { return Err(bad()); }
    Ok(Component { bounds: Some(aabb(&value["box"])?), ammo: boxes(&v["ammo"])?, engine: boxes(&v["engine"])?, fuel: boxes(&v["fuel"])?, crew })
}

impl ModuleVolumes {
    pub fn load(local_root: &Path, path: &Path) -> io::Result<Self> {
        if !path.is_absolute() { return Err(bad()); }
        let root = local_root.canonicalize()?; let path = path.canonicalize()?;
        if !path.starts_with(&root) || path == root { return Err(bad()); }
        let file = fs::File::open(path)?;
        if !file.metadata()?.is_file() || file.metadata()?.len() > MAX_BYTES { return Err(bad()); }
        let mut raw = Vec::new(); file.take(MAX_BYTES + 1).read_to_end(&mut raw)?;
        Self::from_bytes(&raw)
    }
    pub fn from_bytes(raw: &[u8]) -> io::Result<Self> {
        if raw.is_empty() || raw.len() as u64 > MAX_BYTES { return Err(bad()); }
        let value: Value = serde_json::from_slice(raw).map_err(|_| bad())?;
        exact(&value, &["components", "depth", "policy", "schema", "source", "vehicle"])?;
        if value["schema"] != SCHEMA || value["policy"] != POLICY { return Err(bad()); }
        let components = value["components"].as_object().filter(|m| !m.is_empty()).ok_or_else(bad)?;
        if components.keys().any(|k| k != "Hull" && k != "Turret_01") { return Err(bad()); }
        let vehicle = value["vehicle"].as_str().filter(|s| !s.is_empty() && s.len() <= 128).ok_or_else(bad)?.to_owned();
        Ok(Self { vehicle, sha256: format!("{:x}", Sha256::digest(raw)),
            hull: component(&value["components"]["Hull"])?, turret: component(&value["components"]["Turret_01"])? })
    }
    /// The file names this vehicle and its boxes are in the frame of these collision mesh extents.
    pub fn check_binding(&self, name: &str, hull: [[f32; 3]; 2], turret: [[f32; 3]; 2]) -> io::Result<()> {
        if self.vehicle != format!("vehicle:{name}") { return Err(bad()); }
        for (component, bounds) in [(&self.hull, hull), (&self.turret, turret)] {
            if let Some(b) = component.bounds {
                if (0..3).any(|i| (b.low[i] - bounds[0][i]).abs() > BOUNDS_TOLERANCE_M || (b.high[i] - bounds[1][i]).abs() > BOUNDS_TOLERANCE_M) { return Err(bad()); }
            }
        }
        Ok(())
    }
    /// A device has volumes when the skins mark it on any component; its LAB box then goes away.
    pub fn replaces(&self, device: Device) -> bool {
        [&self.hull, &self.turret].iter().any(|c| !Self::of(c, device).is_empty())
    }
    fn of(component: &Component, device: Device) -> &[Aabb] {
        match device { Device::AmmoBay => &component.ammo, Device::Engine => &component.engine, Device::FuelTank => &component.fuel, _ => &[] }
    }
    pub fn device_boxes(&self, turret: bool, device: Device) -> &[Aabb] { Self::of(if turret { &self.turret } else { &self.hull }, device) }
    pub fn crew(&self, turret: bool) -> &[Vec<Aabb>] { if turret { &self.turret.crew } else { &self.hull.crew } }
}

#[cfg(test)]
#[path = "module_volumes_tests.rs"]
mod tests;
