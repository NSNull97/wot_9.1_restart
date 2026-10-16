//! Explicit, hash-pinned #717 vehicle surface binding. No armor/damage semantics.
use std::{fs, io::{self, Read}, path::Path};
use serde_json::Value;
use sha2::{Digest, Sha256};
use super::{collision::{Mesh, Triangle}, model::{bad, Actor, Contact}, pose, materials::{self, Catalog}, vehicle_profile::VehicleKind};

pub const SOURCE_REVISION: &str = "ms1-717:b21e25230f1e5d35d9ae95a713622dfa9606a1b916a22bd0350a73c5f3fcce86";
pub const BUNDLE_SHA256: &str = "26a6714ea562bbc81b64835a8a9495ab9105ae648894b724ea94467d9d7771c2";
pub const IS7_SOURCE_REVISION: &str = "is7-717:61dcc6fe0a305b336d89edfddb67839364077e436ed1e7e3ef567efc369c7225";
pub const IS7_BUNDLE_SHA256: &str = "a65013d10b8a8b05bd076a783e6da24749bcf8b823bfc2e0b9919d745694acbe";
pub fn source_revision(kind: VehicleKind) -> &'static str { match kind {
    VehicleKind::Ms1 => SOURCE_REVISION, VehicleKind::Is7 => IS7_SOURCE_REVISION,
    VehicleKind::T26 => "p04m-t26-collision-717:7b6c41b5d8678a6f935701547781090c517649f741c05621a0cbaf063670e55e",
    VehicleKind::T34 => "p04m-t34-collision-717:6c64732e7421f139991df3cdb0d0d161a3d563a3312fcef040a089d26508c306",
    VehicleKind::T3485 => "p04m-t3485-collision-717:25b6c69fd51e26abbda9b16c35572b5f289f2320d0dffe4085dea1b7bdeba1bb",
} }
fn bundle_sha256(kind: VehicleKind) -> &'static str { match kind {
    VehicleKind::Ms1 => BUNDLE_SHA256, VehicleKind::Is7 => IS7_BUNDLE_SHA256,
    VehicleKind::T26 => "7b6c41b5d8678a6f935701547781090c517649f741c05621a0cbaf063670e55e",
    VehicleKind::T34 => "6c64732e7421f139991df3cdb0d0d161a3d563a3312fcef040a089d26508c306",
    VehicleKind::T3485 => "25b6c69fd51e26abbda9b16c35572b5f289f2320d0dffe4085dea1b7bdeba1bb",
} }
const MAX_BYTES: u64 = 512 * 1024;
const NAMES: [&str; 3] = ["Hull", "Turret_01", "Gun_02"];
const COUNTS: [(usize, usize); 3] = [(436, 258), (311, 218), (146, 90)];
const IS7_NAMES: [&str; 3] = ["Hull", "Turret_01", "Gun_01"];
const IS7_COUNTS: [(usize, usize); 3] = [(312, 190), (576, 376), (217, 157)];
const IS7_EXCLUDED_IDS: [u32; 2] = [107, 157];
const MS1_PIVOTS: [[f32; 3]; 3] = [[-0.012, 0.894681, -0.055245], [0.013778, 0.421721, 0.08902], [-0.238144, 0.234668, 0.410043]];
const IS7_PIVOTS: [[f32; 3]; 3] = [[0., 0.9, 0.], [0.0004959999932907522, 0.7019429802894592, 0.5281969904899597], [-0.046945, 0.250257, 1.01802]];
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
// Exact pinned IS-7 .visual boundingBox. Unlike the MS-1 bounds above,
// native hitTester bbox equivalence is NOT_RUN; do not label it native evidence.
const IS7_VISUAL_BOUNDS: [[[f32; 3]; 2]; 3] = [
    [[-1.6452, -0.405365, -3.56061], [1.6452, 0.745642, 3.65744]],
    [[-1.41518, -0.376276, -2.10397], [1.41419, 0.865144, 1.68136]],
    [[-0.3174070119857788, -0.2239149957895279, -0.9830819964408875], [0.4095210134983063, 0.47898298501968384, 5.99207878112793]],
];
const P04M_SOURCE_REVISION:&str="p04m-717:643358d56786865d7da72ddeac313802a5a17e8d152c2950947d685022c78052";
#[derive(Clone,Copy)]
struct SourceSpec {names:[&'static str;3],counts:[(usize,usize);3],pivots:[[f32;3];3],visual_bounds:[[[f32;3];2];3]}
fn source_spec(kind:VehicleKind)->Option<SourceSpec> {Some(match kind {
VehicleKind::T26=>SourceSpec{names:["Hull", "Turret_01", "Gun_02"],counts:[(211,142),(228,190),(217,128)],pivots:[[0.0, 0.978368, -0.10165], [-0.1449889987707138, 0.5241559743881226, 0.053718000650405884], [0.015381000004708767, 0.36966198682785034, 0.6166329979896545]],visual_bounds:[[[-0.880518, -0.582532, -2.05542], [0.880518, 0.559734, 2.21735]], [[-0.641386, -0.462558, -1.0834], [0.6413859724998474, 0.8381450176239014, 0.8154780268669128]], [[-0.22664399445056915, -0.24859599769115448, -0.5619670152664185], [0.2589679956436157, 0.17585399746894836, 1.0363539457321167]]]},
VehicleKind::T34=>SourceSpec{names:["Hull", "Turret_01", "Gun_01"],counts:[(266,172),(382,264),(195,181)],pivots:[[-0.012, 0.7449, 0.0], [0.018293000757694244, 0.7911549806594849, 0.6135830283164978], [-0.01709200069308281, 0.31865400075912476, 0.6391170024871826]],visual_bounds:[[[-1.2882349491119385, -0.4347440004348755, -2.831109046936035], [1.3094680309295654, 0.931177020072937, 2.8744070529937744]], [[-0.845261, -0.381615, -1.16658], [0.8476089835166931, 0.8202030062675476, 0.9668710231781006]], [[-0.22349700331687927, -0.26429998874664307, -0.2709510028362274], [0.2944610118865967, 0.3126809895038605, 1.703971028327942]]]},
VehicleKind::T3485=>SourceSpec{names:["Hull", "Turret_01", "Gun_01"],counts:[(301,198),(575,429),(199,160)],pivots:[[0.0, 0.9230780005455017, 0.0], [0.0015569999814033508, 0.6163769960403442, 0.6951969861984253], [-0.001609, 0.456677, 1.02193]],visual_bounds:[[[-1.2882709503173828, -0.638484001159668, -2.9060280323028564], [1.2811410427093506, 0.744350016117096, 2.9712250232696533]], [[-1.01125, -0.257368, -1.45768], [1.02206, 1.17241, 1.32705]], [[-0.39754199981689453, -0.316197007894516, -0.3959580063819885], [0.419838011264801, 0.31014999747276306, 3.710998058319092]]]},
_=>return None,
})}
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

/// New LAB proxy input after an actual revalidated source surface contact.
/// This is distinct from the native wire segment, whose AABB entry may be in
/// empty space before a recessed source surface. No internal volumes claimed.
#[derive(Clone, Debug, PartialEq)]
pub struct ProxyRay {
    pub component: materials::Component,
    pub bbox_min: [f32; 3],
    pub bbox_max: [f32; 3],
    pub start: [f32; 3],
    pub end: [f32; 3],
}
impl ProxyRay {
    /// A surface at the forward AABB exit has no interior chord. It cannot
    /// select an internal proxy box; callers skip this valid empty result.
    pub fn is_empty(&self) -> bool { self.start == self.end }
}

fn subtract(a: [f32; 3], b: [f32; 3]) -> [f32; 3] {
    std::array::from_fn(|i| a[i] - b[i])
}

pub(super) fn transform_revision(position: [f32; 3], direction: [f32; 3], aim: [f32; 2], slot: usize, tick: u32) -> String {
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
    vehicle: VehicleKind,
    components: Vec<Component>,
    hull: [f32; 3], turret: [f32; 3], gun: [f32; 3],
    materials: Catalog,
    bounds:[[[f32;3];2];3],
}
fn fields(value: &Value, keys: &[&str]) -> io::Result<()> {
    crate::map_drive_worker091::fields(value, keys).map(|_| ())
}
fn vector(value: &Value) -> io::Result<[f32; 3]> {
    let row = value.as_array().filter(|v| v.len() == 3).ok_or_else(|| bad())?;
    let mut out = [0.; 3];
    for i in 0..3 { let x = row[i].as_f64().ok_or_else(|| bad())?;
        if !x.is_finite() || x.abs() > 10. { return Err(bad()); } out[i] = x as f32; }
    Ok(out)
}
fn text(value: &Value) -> io::Result<String> {
    let s = value.as_str().filter(|s| !s.is_empty() && s.len() <= 128).ok_or_else(|| bad())?;
    Ok(s.into())
}
fn uint(value: &Value) -> io::Result<u32> { u32::try_from(value.as_u64().ok_or_else(|| bad())?).map_err(|_| bad()) }
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
        if raw.is_empty() || raw.len() as u64 > MAX_BYTES { return Err(bad()); }
        let vehicle = match format!("{:x}", Sha256::digest(raw)).as_str() {
            BUNDLE_SHA256 => VehicleKind::Ms1, IS7_BUNDLE_SHA256 => VehicleKind::Is7,
            "7b6c41b5d8678a6f935701547781090c517649f741c05621a0cbaf063670e55e"=>VehicleKind::T26,
            "6c64732e7421f139991df3cdb0d0d161a3d563a3312fcef040a089d26508c306"=>VehicleKind::T34,
            "25b6c69fd51e26abbda9b16c35572b5f289f2320d0dffe4085dea1b7bdeba1bb"=>VehicleKind::T3485,
            _ => return Err(bad()),
        };
        let value: Value = serde_json::from_slice(raw).map_err(|_| bad())?;
        if source_spec(vehicle).is_some() {return Self::from_p04m_source(vehicle,&value);}
        fields(&value, &["schema", "source_revision", "source_pins", "geometry", "materials"])?;
        let schema = match vehicle { VehicleKind::Ms1 => "ms1-contact.v1", VehicleKind::Is7 => "is7-contact.v1",_=>return Err(bad()) };
        if value["schema"] != schema || !value["source_pins"].is_object() { return Err(bad()); }
        let materials = Catalog::from_value_for(vehicle, &value["source_revision"], &value["materials"])?;
        Self::from_value_for(vehicle, &value["geometry"], materials)
    }
    #[cfg(test)]
    fn from_value(v: &Value, materials: Catalog) -> io::Result<Self> {
        Self::from_value_for(VehicleKind::Ms1, v, materials)
    }
    fn from_value_for(vehicle: VehicleKind, v: &Value, materials: Catalog) -> io::Result<Self> {
        let mut keys = vec!["schema", "vehicle_compact_id", "gun_compact_id", "source_revision", "components",
            "hull_position", "turret_position", "gun_position"];
        let (names, counts, pivots, schema, vehicle_id, gun_id) = match vehicle {
            VehicleKind::Ms1 => (NAMES, COUNTS, MS1_PIVOTS, "ms1-collision.v1", 3329, 5892),
            VehicleKind::Is7 => { keys.extend(["component_bounds", "excluded_degenerate_triangle_ids"]); (IS7_NAMES, IS7_COUNTS, IS7_PIVOTS, "is7-collision.v1", 7169, 14852) },
            _=>return Err(bad()),
        };
        fields(v, &keys)?;
        if v["schema"] != schema || v["vehicle_compact_id"] != vehicle_id
            || v["gun_compact_id"] != gun_id || v["source_revision"] != source_revision(vehicle) { return Err(bad()); }
        if vehicle == VehicleKind::Is7 {
            if v["excluded_degenerate_triangle_ids"] != serde_json::json!([[107, 157], [], []]) { return Err(bad()); }
            let bounds = v["component_bounds"].as_array().filter(|a| a.len() == 3).ok_or_else(|| bad())?;
            for (i, pair) in bounds.iter().enumerate() {
                let pair = pair.as_array().filter(|a| a.len() == 2).ok_or_else(|| bad())?;
                if [vector(&pair[0])?, vector(&pair[1])?] != IS7_VISUAL_BOUNDS[i] { return Err(bad()); }
            }
        }
        let hull = vector(&v["hull_position"])?; let turret = vector(&v["turret_position"])?;
        let gun = vector(&v["gun_position"])?;
        if [hull, turret, gun] != pivots { return Err(bad()); }
        let rows = v["components"].as_array().filter(|a| a.len() == 3).ok_or_else(|| bad())?;
        let mut components = Vec::new();
        for (i, row) in rows.iter().enumerate() {
            fields(row, &["name", "vertices", "triangles"])?;
            if row["name"] != names[i] { return Err(bad()); }
            let vr = row["vertices"].as_array().filter(|a| a.len() == counts[i].0).ok_or_else(|| bad())?;
            let tr = row["triangles"].as_array().filter(|a| a.len() == counts[i].1).ok_or_else(|| bad())?;
            let vertices = vr.iter().map(vector).collect::<io::Result<Vec<_>>>()?;
            let mut triangles = Vec::new();
            for (index, t) in tr.iter().enumerate() {
                fields(t, &["triangle_id", "a", "b", "c", "mesh", "group", "material"])?;
                let triangle = Triangle { triangle_id: uint(&t["triangle_id"])?, a: uint(&t["a"])?,
                    b: uint(&t["b"])?, c: uint(&t["c"])?, mesh: text(&t["mesh"])?,
                    group: text(&t["group"])?, material: text(&t["material"])? };
                // Keep original triangle IDs after explicit zero-area filtering.
                // Only Hull source IDs 107/157 are absent; nothing is renumbered.
                let mut source_index = index as u32;
                if vehicle == VehicleKind::Is7 && i == 0 {
                    for excluded in IS7_EXCLUDED_IDS { if source_index >= excluded { source_index += 1; } }
                }
                if triangle.triangle_id != i as u32 * 100000 + source_index || triangle.mesh != names[i] { return Err(bad()); }
                materials.lookup(&triangle.mesh, &triangle.material)?;
                triangles.push(triangle);
            }
            Mesh::new(vertices.clone(), triangles.clone(), source_revision(vehicle), "component-local-v1")?;
            components.push(Component { vertices, triangles });
        }
        Ok(Self { vehicle, components, hull, turret, gun, materials, bounds:if vehicle==VehicleKind::Ms1{NATIVE_BOUNDS}else{IS7_VISUAL_BOUNDS} })
    }
    /// Separate closed P04M source export format; the enclosing raw digest was
    /// approved before JSON parsing. Visual bounds stay source facts, not a
    /// claimed native hitTester measurement or an admitted physics collider.
    fn from_p04m_source(vehicle:VehicleKind,value:&Value)->io::Result<Self> {
        let spec=source_spec(vehicle).ok_or_else(||bad())?;
        fields(value,&["assembly_id","battle_admission","classification","geometry","gun","identity",
            "movement_source","runtime_physics","schema","source_pins","source_revision","unknowns"])?;
        let assembly=format!("{}-stock",vehicle.label());
        if value["schema"]!="p04m-battle-source.v1" || value["source_revision"]!=P04M_SOURCE_REVISION
            || value["assembly_id"]!=assembly || value["battle_admission"]!=false
            || !value["runtime_physics"].is_null() || !value["source_pins"].is_object()
            || value["classification"]!="VERIFIED_STATIC_ORIGINAL_717" {return Err(bad());}
        let identity=&value["identity"];
        let descriptor=vehicle.descriptor().iter().map(|byte|format!("{byte:02x}")).collect::<String>();
        if identity["type_compact_id"]!=vehicle.vehicle_compact_id()
            ||identity["module_compact_ids"]["gun"]!=vehicle.gun_compact_id()
            ||identity["descriptor_hex"]!=descriptor ||identity["max_hp"]!=vehicle.max_health()
            ||value["gun"]["shell_compact_id"]!=vehicle.shell_compact_id()
            ||value["gun"]["capacity"]!=vehicle.ammo_limit()
            ||value["gun"]["reload_seconds"].as_f64().map(|v|v as f32)!=Some(vehicle.reload_seconds()) {return Err(bad());}
        let geometry=&value["geometry"];
        fields(geometry,&["components","gun_position","hull_aabb_candidate","hull_position","turret_position"])?;
        let hull=vector(&geometry["hull_position"])?;let turret=vector(&geometry["turret_position"])?;
        let gun=vector(&geometry["gun_position"])?;
        if [hull,turret,gun]!=spec.pivots {return Err(bad());}
        let materials=Catalog::from_p04m_for(vehicle,&geometry["components"])?;
        let rows=geometry["components"].as_array().filter(|rows|rows.len()==3).ok_or_else(||bad())?;
        let mut components=Vec::with_capacity(3);
        for (i,row) in rows.iter().enumerate() {
            fields(row,&["excluded_degenerate_triangle_ids","materials","mesh_bounds","name","triangles","vertices","visual_bounds"])?;
            if row["name"]!=spec.names[i] || row["excluded_degenerate_triangle_ids"]!=serde_json::json!([]) {return Err(bad());}
            let bounds=row["visual_bounds"].as_array().filter(|r|r.len()==2).ok_or_else(||bad())?;
            if [vector(&bounds[0])?,vector(&bounds[1])?]!=spec.visual_bounds[i] {return Err(bad());}
            let vr=row["vertices"].as_array().filter(|r|r.len()==spec.counts[i].0).ok_or_else(||bad())?;
            let tr=row["triangles"].as_array().filter(|r|r.len()==spec.counts[i].1).ok_or_else(||bad())?;
            let vertices=vr.iter().map(vector).collect::<io::Result<Vec<_>>>()?;
            let mut triangles=Vec::with_capacity(tr.len());
            for (index,t) in tr.iter().enumerate() {
                fields(t,&["triangle_id","a","b","c","mesh","group","material"])?;
                let triangle=Triangle{triangle_id:uint(&t["triangle_id"])?,a:uint(&t["a"])?,b:uint(&t["b"])?,c:uint(&t["c"])?,
                    mesh:text(&t["mesh"])?,group:text(&t["group"])?,material:text(&t["material"])?};
                if triangle.triangle_id!=i as u32*100000+index as u32 || triangle.mesh!=spec.names[i] {return Err(bad());}
                materials.lookup(&triangle.mesh,&triangle.material)?;triangles.push(triangle);
            }
            // New profiles have no approved degenerate exclusions; Mesh rejects
            // invalid indices/areas before any authoritative world can use them.
            Mesh::new(vertices.clone(),triangles.clone(),source_revision(vehicle),"component-local-v1")?;
            components.push(Component{vertices,triangles});
        }
        Ok(Self{vehicle,components,hull,turret,gun,materials,bounds:spec.visual_bounds})
    }
    pub fn vehicle_kind(&self) -> VehicleKind { self.vehicle }
    pub fn geometry_revision(&self) -> &'static str { source_revision(self.vehicle) }
    pub fn bundle_sha256(&self) -> &'static str { bundle_sha256(self.vehicle) }
    fn component_bounds(&self) -> [[[f32; 3]; 2]; 3] {self.bounds}
    pub fn materials(&self) -> &Catalog { &self.materials }
    /// Recover a local segment from the authoritative contact's exact target
    /// pose. Attached hull/turret/gun on a live or ordinary HP0 vehicle only:
    /// #717 DamageFromShotDecoder reuses descriptor hitTester/bbox after death.
    /// The wreck policy retains that pose; actual destroyed-model publication
    /// remains a native acceptance gate. Exploded/detached component transforms
    /// are not represented by Contact and must not call this route.
    pub fn impact_segment(&self, contact: &Contact) -> io::Result<ImpactSegment> {
        if contact.geometry_revision != self.geometry_revision() || contact.target_slot >= super::model::MAX_ACTORS || contact.tick < 1000
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
            materials::Component::Turret01 => 1, materials::Component::Gun02 | materials::Component::Gun01 => 2 };
        let source = self.components[index].triangles.iter().find(|triangle| triangle.triangle_id == contact.triangle.triangle_id).ok_or_else(|| bad())?;
        if source.mesh != contact.triangle.mesh || source.group != contact.triangle.group
            || source.material != contact.triangle.material { return Err(bad()); }
        let delta = subtract(contact.segment_end, contact.segment_start);
        if (0..3).any(|i| (f64::from(contact.segment_start[i] + contact.triangle.t * delta[i])
            - f64::from(contact.endpoint[i])).abs() > CONTACT_TOLERANCE) { return Err(bad()); }
        let chassis_point = pose::inverse_rotate(subtract(contact.endpoint, contact.target_position), contact.target_direction);
        let chassis_direction = pose::inverse_rotate(delta, contact.target_direction);
        let point = self.inverse_component_point(index, chassis_point, contact.target_aim);
        let direction = self.inverse_component_direction(index, chassis_direction, contact.target_aim);
        let bounds = self.component_bounds()[index];
        let length = direction.iter().map(|&x| f64::from(x).powi(2)).sum::<f64>().sqrt();
        let minimum = -f64::from(contact.triangle.t) * length;
        let (start, end) = clipped_line(point, direction, bounds, Some(minimum))?;
        // A line continued behind the current simulation segment must not
        // select another, earlier surface (e.g. a projectile starting inside a
        // component). Verify the first surface before any wire quantization.
        let extended_start = std::array::from_fn(|i| start[i] - 0.01 * (end[i] - start[i]));
        let extended_end = std::array::from_fn(|i| end[i] + 0.01 * (end[i] - start[i]));
        let part = &self.components[index];
        let mesh = Mesh::new(part.vertices.clone(), part.triangles.clone(), self.geometry_revision(), "impact-component-local-v1")?;
        let hits = super::collision::query(&mesh, extended_start, extended_end)?;
        let first = hits.first().ok_or_else(|| io::Error::new(io::ErrorKind::InvalidData, "impact segment has no local surface"))?;
        if (0..3).any(|i| (f64::from(extended_start[i] + first.t * (extended_end[i] - extended_start[i]))
            - f64::from(point[i])).abs() > CONTACT_TOLERANCE) {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "impact segment first surface differs from contact"));
        }
        Ok(ImpactSegment { component, bounds, start, end })
    }
    /// Requery the exact authoritative source mesh and contact pose. A source
    /// triangle ID/label alone does not validate the normal, fraction, nearest
    /// order or contact point. This preserves the legacy wire segment method.
    pub fn proxy_ray(&self, contact: &Contact) -> io::Result<ProxyRay> {
        if contact.shot == 0 || contact.shot as usize > super::model::MAX_BATTLE_SHOTS
            || !contact.segment_seconds.is_finite() || !(0. ..=1.).contains(&contact.segment_seconds)
            || contact.geometry_revision != self.geometry_revision() || contact.target_slot >= super::model::MAX_ACTORS || contact.tick < 1000
            || contact.target_position.iter().any(|v|!v.is_finite()||v.abs()>2000.)
            || contact.target_direction.iter().chain(contact.target_aim.iter()).any(|v|!v.is_finite()||v.abs()>std::f32::consts::PI)
            || contact.segment_start.iter().chain(contact.segment_end.iter()).chain(contact.endpoint.iter()).any(|v|!v.is_finite()||v.abs()>100_000.)
            || !contact.triangle.t.is_finite() || !(0. ..=1.).contains(&contact.triangle.t) {
            return Err(bad());
        }
        if contact.transform_revision != transform_revision(contact.target_position,contact.target_direction,
            contact.target_aim,contact.target_slot,contact.tick) {return Err(bad());}
        let facts=self.materials.lookup(&contact.triangle.mesh,&contact.triangle.material)?;
        if facts!=contact.material_facts {return Err(bad());}
        let mesh = self.mesh_for_pose(contact.target_position, contact.target_direction,
            contact.target_aim, contact.target_slot, contact.tick)?;
        let expected = super::collision::query(&mesh, contact.segment_start, contact.segment_end)?
            .into_iter().next().ok_or_else(|| bad())?;
        let endpoint = std::array::from_fn(|i| contact.segment_start[i]
            + expected.t * (contact.segment_end[i] - contact.segment_start[i]));
        if expected != contact.triangle || endpoint != contact.endpoint { return Err(bad()); }
        let index = match facts.component { materials::Component::Hull => 0,
            materials::Component::Turret01 => 1, materials::Component::Gun02 | materials::Component::Gun01 => 2 };
        let bounds=self.component_bounds()[index];
        let point = pose::inverse_rotate(subtract(contact.endpoint, contact.target_position), contact.target_direction);
        let start = self.inverse_component_point(index, point, contact.target_aim);
        let direction = self.inverse_component_direction(index,
            pose::inverse_rotate(subtract(contact.segment_end, contact.segment_start), contact.target_direction), contact.target_aim);
        if start.iter().enumerate().any(|(i,v)| f64::from(*v) < f64::from(bounds[0][i])-CONTACT_TOLERANCE
            || f64::from(*v) > f64::from(bounds[1][i])+CONTACT_TOLERANCE) { return Err(bad()); }
        let norm = direction.iter().map(|v| f64::from(*v).powi(2)).sum::<f64>().sqrt();
        if !norm.is_finite() || norm == 0. { return Err(bad()); }
        let unit = direction.map(|v| f64::from(v)/norm);
        let mut exit = f64::INFINITY;
        for i in 0..3 {
            if unit[i] > 0. { exit = exit.min((f64::from(bounds[1][i])-f64::from(start[i]))/unit[i]); }
            else if unit[i] < 0. { exit = exit.min((f64::from(bounds[0][i])-f64::from(start[i]))/unit[i]); }
        }
        if !exit.is_finite() { return Err(bad()); }
        // Negative rounding-scale exit means a point on the forward boundary,
        // not permission to extend beyond the source box or move backwards.
        let exit = exit.max(0.);
        let end = std::array::from_fn(|i| (f64::from(start[i])+unit[i]*exit) as f32);
        Ok(ProxyRay { component: facts.component, bbox_min: bounds[0], bbox_max: bounds[1], start, end })
    }
    /// Explicit source-exterior HE sampling policy: one ray toward the posed
    /// source Hull bbox center, extended beyond it to leave every actual source
    /// component. Coincident center uses the actual chassis +Z direction. An
    /// inside center is never accepted as an AABB hit: only a real triangle can
    /// produce a Contact. Caller owns source shell radius and terrain/static LOS.
    pub fn explosion_contact(&self, actor: &Actor, center: [f32;3], radius: f32,
        shot: u32, target_slot: usize, tick: u32) -> io::Result<Option<Contact>> {
        const MAX_RADIUS: f32 = 16.; // bounded API ceiling; actual #717 maximum is5.05
        if center.iter().any(|v| !v.is_finite() || v.abs()>100_000.)
            || !radius.is_finite() || radius<=0. || radius>MAX_RADIUS
            || shot==0 || shot as usize>super::model::MAX_BATTLE_SHOTS
            || target_slot>=super::model::MAX_ACTORS || tick<1000
            || [actor.aim.yaw,actor.aim.pitch].iter().any(|v|!v.is_finite()||v.abs()>std::f32::consts::PI) {
            return Err(bad());
        }
        let mesh = self.world_mesh(actor,target_slot,tick)?;
        let midpoint = std::array::from_fn(|i| (self.bounds[0][0][i]+self.bounds[0][1][i])*0.5);
        let local_center = self.component_point(0,midpoint,actor.aim.yaw,actor.aim.pitch);
        let rotated = pose::rotate(local_center,actor.direction);
        let hull_center = std::array::from_fn::<_,3,_>(|i|actor.position[i]+rotated[i]);
        let delta = std::array::from_fn::<_,3,_>(|i|f64::from(hull_center[i])-f64::from(center[i]));
        let length = delta.iter().map(|v|v*v).sum::<f64>().sqrt();
        let unit = if length==0. {pose::rotate([0.,0.,1.],actor.direction).map(f64::from)}
            else {delta.map(|v|v/length)};
        // Derive the ray endpoint from all mounted source vertices; the1cm
        // endpoint margin changes neither triangle positions nor blast radius.
        let mut extent:f64=0.;
        for (index,part) in self.components.iter().enumerate() {
            for vertex in &part.vertices {
                let local=self.component_point(index,*vertex,actor.aim.yaw,actor.aim.pitch);
                let distance=(0..3).map(|i|(f64::from(local[i])-f64::from(local_center[i])).powi(2)).sum::<f64>().sqrt();
                extent=extent.max(distance);
            }
        }
        let end=std::array::from_fn(|i|(f64::from(hull_center[i])+unit[i]*(extent+0.01))as f32);
        if end==center {return Err(bad());}
        let Some(triangle)=super::collision::query(&mesh,center,end)?.into_iter().next() else {return Ok(None)};
        let endpoint=std::array::from_fn(|i|center[i]+triangle.t*(end[i]-center[i]));
        let distance_squared=(0..3).map(|i|(f64::from(endpoint[i])-f64::from(center[i])).powi(2)).sum::<f64>();
        if distance_squared>f64::from(radius).powi(2) {return Ok(None);}
        let material_facts=self.materials.lookup(&triangle.mesh,&triangle.material)?;
        Ok(Some(Contact {shot,target_slot,tick,segment_start:center,segment_end:end,
            segment_seconds:0., // instantaneous geometric sample, not flight time
            endpoint,target_position:actor.position,target_direction:actor.direction,
            target_aim:[actor.aim.yaw,actor.aim.pitch],triangle,
            geometry_revision:mesh.geometry_revision().into(),transform_revision:mesh.transform_revision().into(),material_facts}))
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
        if actor.vehicle_kind() != self.vehicle || slot >= super::model::MAX_ACTORS || tick < 1000 || actor.position.iter().any(|x| !x.is_finite() || x.abs() > 2000.)
            || actor.direction.iter().any(|x| !x.is_finite() || x.abs() > std::f32::consts::PI)
            || !actor.aim.yaw.is_finite() || !actor.aim.pitch.is_finite() { return Err(bad()); }
        self.mesh_for_pose(actor.position,actor.direction,[actor.aim.yaw,actor.aim.pitch],slot,tick)
    }
    fn mesh_for_pose(&self, position: [f32;3], direction: [f32;3], aim: [f32;2], slot: usize, tick: u32) -> io::Result<Mesh> {
        let mut vertices = Vec::new(); let mut triangles = Vec::new();
        for (i, component) in self.components.iter().enumerate() {
            let base = vertices.len() as u32;
            for &v in &component.vertices {
                let local = self.component_point(i, v, aim[0], aim[1]);
                let rotated = pose::rotate(local, direction);
                vertices.push(std::array::from_fn(|axis| position[axis] + rotated[axis]));
            }
            for triangle in &component.triangles {
                let mut t = triangle.clone(); t.a += base; t.b += base; t.c += base; triangles.push(t);
            }
        }
        // Hash the precise authoritative transform facts, including aim, so
        // the identity stays unambiguous even within one server tick.
        Mesh::new(vertices, triangles, self.geometry_revision(),
            transform_revision(position, direction, aim, slot, tick))
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
#[path="p04m_geometry_tests.rs"]
mod p04m_geometry_tests;

#[cfg(test)]
#[path="p06t_geometry_tests.rs"]
mod p06t_geometry_tests;

#[cfg(test)]
pub(super) mod tests {
    use super::*;
    fn actor_for(kind: VehicleKind) -> Actor {
        let mut world = super::super::model::World::new_for_vehicle(991, std::time::Instant::now(),
            crate::map_profile091::MapId::Prohorovka, kind).unwrap();
        let slot = world.attach(super::super::model::Identity {
            account: "geometry-owned-actor".into(), database: 991, name: "geometry_actor".into(),
        }, 991).unwrap();
        world.actors[slot].clone()
    }
    fn contact_for(b: &Bundle, index: usize, start: [f32; 3], end: [f32; 3],
        direction: [f32; 3], aim: [f32; 2]) -> Contact {
        let mut actor = actor_for(b.vehicle_kind());
        actor.position = [37., 21., -105.]; actor.direction = direction;
        actor.aim.yaw = aim[0]; actor.aim.pitch = aim[1];
        let world = |p| {
            let rotated = pose::rotate(b.component_point(index, p, aim[0], aim[1]), direction);
            std::array::from_fn(|i| actor.position[i] + rotated[i])
        };
        let segment_start = world(start); let segment_end = world(end);
        let mesh = b.world_mesh(&actor, 1, 1000).unwrap();
        let triangle = super::super::collision::query(&mesh, segment_start, segment_end).unwrap()
            .into_iter().find(|hit| hit.mesh == match b.vehicle_kind() { VehicleKind::Ms1 => NAMES[index], VehicleKind::Is7 => IS7_NAMES[index],
                kind=>source_spec(kind).expect("closed source profile").names[index] }).unwrap();
        let endpoint = std::array::from_fn(|i| segment_start[i] + triangle.t * (segment_end[i] - segment_start[i]));
        let material_facts = b.materials.lookup(&triangle.mesh, &triangle.material).unwrap();
        Contact { shot: 1, target_slot: 1, tick: 1000, segment_start, segment_end, segment_seconds: 0.1,
            endpoint, target_position: actor.position, target_direction: direction, target_aim: aim,
            triangle, geometry_revision: b.geometry_revision().into(), transform_revision: mesh.transform_revision().into(), material_facts }
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
    pub fn is7_bundle() -> Bundle {
        let root = std::env::var("WOT091_ROOT").unwrap_or_else(|_| "D:/WoT_9.1_Server".into());
        Bundle::load(&Path::new(&root).join("local"), &Path::new(&root)
            .join("local/evidence/20261013-p03m-is7-01/geometry-surface01/is7-contact.json")).unwrap()
    }
    #[test] fn is7_pinned_bundle_preserves_component_coverage_and_vehicle_identity() {
        let b = is7_bundle(); assert_eq!(b.vehicle_kind(), VehicleKind::Is7);
        assert_eq!(b.geometry_revision(), IS7_SOURCE_REVISION); assert_eq!(b.bundle_sha256(), IS7_BUNDLE_SHA256);
        assert_eq!([b.hull, b.turret, b.gun], IS7_PIVOTS);
        let ids: Vec<_> = b.components[0].triangles.iter().map(|t| t.triangle_id).collect();
        assert_eq!(ids, (0..192).filter(|id| !IS7_EXCLUDED_IDS.contains(id)).collect::<Vec<_>>());
        for (index, component) in b.components.iter().enumerate() {
            assert_eq!((component.vertices.len(), component.triangles.len()), IS7_COUNTS[index]);
            for t in &component.triangles {
                assert_eq!(t.mesh, IS7_NAMES[index]);
                assert_eq!(b.materials.lookup(&t.mesh, &t.material).unwrap().profile_revision, materials::IS7_PROFILE_REVISION);
            }
        }
        let ms1 = super::super::model::tests::world(std::time::Instant::now()).actors[0].clone();
        assert!(b.world_mesh(&ms1, 0, 1000).is_err());
        let is7 = actor_for(VehicleKind::Is7);
        assert!(bundle().world_mesh(&is7, 0, 1000).is_err());
        assert_eq!(b.world_mesh(&is7, 0, 1000).unwrap().geometry_revision(), IS7_SOURCE_REVISION);
        assert!(b.materials.lookup("Gun_02", "armor_1").is_err());
    }
    #[test] fn is7_source_visual_bounds_and_articulated_surface_segments() {
        let b = is7_bundle();
        assert!(b.components[0].vertices.iter().all(|v| v[1] < 0.683));
        assert_eq!(b.component_bounds()[0][1][1], 0.745642);
        // These are source geometry checks. Native hitTester bbox/visual effect
        // acceptance must still be measured for IS-7 in the owner run.
        for (index, start, end) in [(0, [-4., 0., 0.], [4., 0., 0.]),
            (1, [0.1, 0.25, -4.], [0.1, 0.25, 4.]), (2, [0., 0.1, -2.], [0., 0.1, 7.])] {
            for (direction, aim) in [([0.; 3], [0.; 2]), ([0.7, -0.3, 0.2], [1.1, -0.09]),
                ([-2.1, 0.25, -0.15], [-0.9, 0.24])] {
                for reverse in [false, true] {
                    let (start, end) = if reverse { (end, start) } else { (start, end) };
                    let c = contact_for(&b, index, start, end, direction, aim);
                    let segment = b.impact_segment(&c).unwrap();
                    assert_eq!(segment.component.name(), IS7_NAMES[index]);
                    assert_eq!(segment.bounds, IS7_VISUAL_BOUNDS[index]);
                    let roundtrip = b.inverse_component_point(index,
                        b.component_point(index, segment.start, aim[0], aim[1]), aim);
                    for axis in 0..3 { assert!((roundtrip[axis] - segment.start[axis]).abs() < 1e-6); }
                    let mut foreign = c.clone(); foreign.geometry_revision = SOURCE_REVISION.into();
                    assert!(b.impact_segment(&foreign).is_err());
                    foreign = c; foreign.material_facts.profile_revision = materials::PROFILE_REVISION.into();
                    assert!(b.impact_segment(&foreign).is_err());
                }
            }
        }
    }
    #[test] fn is7_malformed_source_binding_and_bytes_fail_without_ms1_fallback() {
        let root = std::env::var("WOT091_ROOT").unwrap_or_else(|_| "D:/WoT_9.1_Server".into());
        let raw = fs::read(Path::new(&root).join("local/evidence/20261013-p03m-is7-01/geometry-surface01/is7-contact.json")).unwrap();
        let value: Value = serde_json::from_slice(&raw).unwrap();
        let catalog = || Catalog::from_value_for(VehicleKind::Is7, &value["source_revision"], &value["materials"]).unwrap();
        let mut changed = raw.clone(); changed.push(b' '); assert!(Bundle::from_bytes(&changed).is_err());
        for (key, v) in [("schema", serde_json::json!("ms1-collision.v1")),
            ("gun_compact_id", serde_json::json!(52484)), ("source_revision", serde_json::json!(SOURCE_REVISION)),
            ("hull_position", serde_json::json!([0., 0., 0.])), ("component_bounds", serde_json::json!([])),
            ("excluded_degenerate_triangle_ids", serde_json::json!([[107], [], []]))] {
            let mut bad_geometry = value["geometry"].clone(); bad_geometry[key] = v;
            assert!(Bundle::from_value_for(VehicleKind::Is7, &bad_geometry, catalog()).is_err());
        }
        let mut bad_geometry = value["geometry"].clone(); bad_geometry["components"][2]["name"] = "Gun_02".into();
        assert!(Bundle::from_value_for(VehicleKind::Is7, &bad_geometry, catalog()).is_err());
        let mut bad_geometry = value["geometry"].clone(); bad_geometry["components"][0]["triangles"][0]["a"] = 99999.into();
        assert!(Bundle::from_value_for(VehicleKind::Is7, &bad_geometry, catalog()).is_err());
        assert!(Bundle::from_value_for(VehicleKind::Ms1, &value["geometry"], catalog()).is_err());
        assert!(Catalog::from_value_for(VehicleKind::Ms1, &value["source_revision"], &value["materials"]).is_err());
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
        for slot in 0..super::super::model::MAX_ACTORS { assert!(b.world_mesh(&actor, slot, 1000).is_ok()); }
        assert!(b.world_mesh(&actor, super::super::model::MAX_ACTORS, 1000).is_err());
        actor.position[0] = f32::NAN; assert!(b.world_mesh(&actor, 0, 1000).is_err());
    }
}
