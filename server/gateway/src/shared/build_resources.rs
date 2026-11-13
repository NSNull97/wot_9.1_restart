//! CONTENT-0 3.3: battle resources of a non-stock build (mounted modules), derived when the build
//! enters a battle from its vehicle's stock template row and the build's own pinned files:
//! - geometry: the three collision parts (`<dir>/parts/<sha256>.json`), the track armour part of its
//!   chassis when the stock row binds track armour, the stock module volumes only with the stock turret;
//! - physics: the stock map config with the build's physics/handling (written once to
//!   `<dir>/builds/`), and the build's qualified profile `<dir>/<label>-qualified-profile.json`.
//! `<dir>` is the stand's BATTLE-ANY resource directory (the stock qualified profiles' directory).
//! Every file is checked against the registry SHA-256; a missing or refused piece fails the build's
//! admission explicitly, it is never replaced by the stock one.
use std::{collections::BTreeMap,fs,io::{self,Read,Write},path::{Path,PathBuf},sync::{Arc,Mutex,OnceLock}};
use serde_json::Value;
use sha2::{Digest,Sha256};
use super::{geometry::{non_reparse,Bundle},generated_vehicles as generated,vehicle_profile::VehicleKind};

fn bad(reason:&str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("build resources: {reason}"))}

/// Bounded cache of loaded build geometries (one battle seats at most 30 actors).
const MAX_CACHED:usize=256;
const MAX_CONFIG:u64=16384;

struct Source{root:PathBuf,dir:PathBuf}
static SOURCE:OnceLock<Source>=OnceLock::new();
static GEOMETRY:OnceLock<Mutex<BTreeMap<usize,Arc<Bundle>>>>=OnceLock::new();

/// Bind the stand's resource directory once (the directory of the stock generated qualified profiles).
pub fn configure(local_root:&Path,dir:&Path)->io::Result<()> {
    non_reparse(local_root)?;non_reparse(dir)?;
    let root=local_root.canonicalize()?;let dir=dir.canonicalize()?;
    if !dir.starts_with(&root)||dir==root {return Err(bad("resource directory outside the local root"));}
    match SOURCE.get() {
        Some(s) if s.root==root&&s.dir==dir=>Ok(()),
        Some(_)=>Err(bad("resource directory already bound")),
        None=>{let _=SOURCE.set(Source{root,dir});Ok(())},
    }
}
fn source()->io::Result<&'static Source>{SOURCE.get().ok_or_else(||bad("resource directory not bound"))}
/// The bound (local root, directory): the BW01 worker process binds the same pair (CONTENT-0 4: builds fought
/// in a worker failed with "resource directory not bound").
pub fn bound()->Option<(PathBuf,PathBuf)>{SOURCE.get().map(|s|(s.root.clone(),s.dir.clone()))}

/// A non-stock generated build (stock kinds and the closed kinds are not builds).
pub fn is_build(kind:VehicleKind)->bool{kind.generated().is_some_and(|e|!e.stock)}
/// The stock entry of a build's vehicle (None: the vehicle's stock build is refused or legacy).
pub fn stock_of(kind:VehicleKind)->Option<VehicleKind> {
    let e=kind.generated().filter(|e|!e.stock)?;
    generated::registry().ok()?.by_vehicle(&e.vehicle_id).map(VehicleKind::Generated)
}

/// Geometry of a build: its three parts, its chassis track armour (when the stock row has track armour)
/// and the stock module volumes only when the build keeps the stock turret.
pub fn geometry(kind:VehicleKind,stock:&Bundle)->io::Result<Arc<Bundle>> {
    let e=kind.generated().filter(|e|!e.stock).ok_or_else(||bad("not a build"))?;
    let stock_kind=stock.vehicle_kind();
    if stock_of(kind)!=Some(stock_kind) {return Err(bad("stock geometry of another vehicle"));}
    let cache=GEOMETRY.get_or_init(||Mutex::new(BTreeMap::new()));
    if let Some(found)=cache.lock().map_err(|_|bad("cache"))?.get(&kind.index()) {return Ok(found.clone());}
    let s=source()?;
    let parts=s.dir.join("parts");
    let mut bundle=Bundle::load_generated_parts(&s.root,&parts,kind)?;
    if stock.chassis().is_some() {
        if e.chassis_armor_sha256.is_none() {return Err(bad("track armour of this chassis is unavailable"));}
        let chassis=super::chassis_armor::ChassisArmor::load_build_part(&s.root,&parts,kind)?;
        bundle=bundle.with_chassis(Arc::new(chassis))?;
    }
    if let Some(volumes)=stock.module_volumes_arc() {
        let s_e=stock_kind.generated().ok_or_else(||bad("stock entry"))?;
        if e.parts[1]==s_e.parts[1]&&e.pivots[1..]==s_e.pivots[1..] {bundle=bundle.with_module_volumes(volumes)?;}
        else {
            // CONTENT-0 4: the skins mark only the stock turret model; the hull volumes (same hull) still bind,
            // the other turret's modules and seats stay on their LAB boxes.
            let hull_only=super::module_volumes::ModuleVolumes{turret:Default::default(),..(*volumes).clone()};
            bundle=bundle.with_module_volumes(Arc::new(hull_only))?;
            println!("CONTENT0_BUILD_MODVOL_HULL_ONLY kind={} reason=non_stock_turret turret_policy=lab_boxes",e.label);
        }
    }
    let bundle=Arc::new(bundle);
    let mut cache=cache.lock().map_err(|_|bad("cache"))?;
    if cache.len()>=MAX_CACHED {cache.clear();}
    cache.insert(kind.index(),bundle.clone());
    println!("CONTENT0_BUILD_GEOMETRY_BOUND kind={} stock={} parts={:?} chassis={:?}",e.label,stock_kind.label(),e.part_sha256,e.chassis_armor_sha256);
    Ok(bundle)
}

fn read(path:&Path,limit:u64)->io::Result<Vec<u8>> {
    non_reparse(path)?;
    let file=fs::File::open(path)?;
    if !file.metadata()?.is_file()||file.metadata()?.len()>limit {return Err(bad("file bound"));}
    let mut raw=Vec::new();file.take(limit+1).read_to_end(&mut raw)?;
    if raw.is_empty()||raw.len() as u64>limit {return Err(bad("file bound"));}
    Ok(raw)
}
fn digest(raw:&[u8])->String{format!("{:x}",Sha256::digest(raw))}

/// The build's map spec (stock config with the build's physics and handling) and qualified profile.
pub fn map_and_source(kind:VehicleKind,stock_map:&crate::map_drive_worker091::MapSpec)
    ->io::Result<(crate::map_drive_worker091::MapSpec,(PathBuf,String))> {
    let e=kind.generated().filter(|e|!e.stock).ok_or_else(||bad("not a build"))?;
    let s=source()?;
    // The qualified profile the worker loads: exact registry pin.
    let profile=s.dir.join(format!("{}-qualified-profile.json",e.label));
    let raw=read(&profile,MAX_CONFIG)?;
    if digest(&raw)!=e.qualified_sha256||raw.len() as u64!=e.qualified_bytes {return Err(bad("qualified profile pin"));}
    // Stock config of this map with the build's physical projection.
    let stock_config=stock_map.config.canonicalize()?;
    if !stock_config.starts_with(&s.root) {return Err(bad("stock config outside the local root"));}
    let raw=read(&stock_config,MAX_CONFIG)?;
    if digest(&raw)!=stock_map.config_sha256 {return Err(bad("stock config pin"));}
    let mut config:Value=serde_json::from_slice(&raw).map_err(|_|bad("stock config JSON"))?;
    let object=config.as_object_mut().ok_or_else(||bad("stock config object"))?;
    let physics=e.physics.as_object().ok_or_else(||bad("build physics"))?;
    for field in crate::map_drive_worker091::PHYSICS_FIELDS {
        let value=physics.get(field).ok_or_else(||bad("build physics field"))?;
        if !object.contains_key(field) {return Err(bad("stock config field"));}
        object.insert(field.to_owned(),value.clone());
    }
    if !object.contains_key("handling") {return Err(bad("stock config handling"));}
    object.insert("handling".to_owned(),e.handling.clone());
    let bytes=serde_json::to_vec(&config).map_err(|_|bad("config JSON"))?;
    if bytes.len() as u64>MAX_CONFIG {return Err(bad("config bound"));}
    let builds=s.dir.join("builds");
    if !builds.exists() {fs::create_dir(&builds)?;}
    non_reparse(&builds)?;
    let path=builds.join(format!("{}-{}-config.json",stock_map.asset,e.label));
    if path.exists() {
        if read(&path,MAX_CONFIG)?!=bytes {return Err(bad("existing build config differs"));}
    } else {
        let temp=builds.join(format!(".{}-{}-{}.tmp",stock_map.asset,e.label,std::process::id()));
        {let mut f=fs::OpenOptions::new().write(true).create_new(true).open(&temp)?;f.write_all(&bytes)?;f.sync_all()?;}
        if let Err(error)=fs::rename(&temp,&path) {let _=fs::remove_file(&temp);
            // A concurrent writer of the same derived bytes is fine; anything else is an error.
            if read(&path,MAX_CONFIG).ok().as_deref()!=Some(&bytes[..]) {return Err(error);}}
    }
    let mass=e.physics["mass_kg"].as_f64().filter(|m|(1000. ..=200000.).contains(m)).ok_or_else(||bad("build mass"))? as f32;
    let mut map=stock_map.clone();
    map.config=path;map.config_sha256=digest(&bytes);map.mass_kg=mass;
    Ok((map,(profile,e.qualified_sha256.clone())))
}
