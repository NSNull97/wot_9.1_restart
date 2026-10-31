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
    VehicleKind::Wt128=>super::p06t_geometry_source::Assembly::Wt128.revision(),
    VehicleKind::Fv183=>super::p06t_geometry_source::Assembly::Fv183.revision(),
    VehicleKind::Generated(id)=>&super::generated_vehicles::entry(id).geometry_revision,
} }
fn bundle_sha256(kind: VehicleKind) -> &'static str { match kind {
    VehicleKind::Ms1 => BUNDLE_SHA256, VehicleKind::Is7 => IS7_BUNDLE_SHA256,
    VehicleKind::T26 => "7b6c41b5d8678a6f935701547781090c517649f741c05621a0cbaf063670e55e",
    VehicleKind::T34 => "6c64732e7421f139991df3cdb0d0d161a3d563a3312fcef040a089d26508c306",
    VehicleKind::T3485 => "25b6c69fd51e26abbda9b16c35572b5f289f2320d0dffe4085dea1b7bdeba1bb",
    VehicleKind::Wt128=>super::p06t_geometry_source::Assembly::Wt128.sha256(),
    VehicleKind::Fv183=>super::p06t_geometry_source::Assembly::Fv183.sha256(),
    VehicleKind::Generated(id)=>&super::generated_vehicles::entry(id).geometry_sha256,
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

fn same_surface(a:&super::collision::Candidate,b:&super::collision::Candidate)->bool {
    a.triangle_id==b.triangle_id && a.mesh==b.mesh && a.group==b.group && a.material==b.material
}

// Public candidates retain f32 t even though collision ordering uses f64.
// Treat equal reported t as ambiguous instead of inventing a tie policy.
fn first_surface_unambiguous(hits:&[super::collision::Candidate],expected:&super::collision::Candidate)->bool {
    match hits.first() {
        Some(first) if same_surface(first,expected) => !hits.get(1).is_some_and(|next|next.t.to_bits()==first.t.to_bits()),
        _=>false,
    }
}

/// Outward-rounded binary64 intervals for the fallback's world-space
/// barycentric proof. Inputs are exact promotions of already-fixed f32 facts;
/// this certifies arithmetic over those facts, not pose/native uncertainty.
#[derive(Clone,Copy,Debug)]
struct ImpactInterval {lo:f64,hi:f64}
impl ImpactInterval {
    fn exact(value:f64)->Option<Self> {value.is_finite().then_some(Self{lo:value,hi:value})}
    fn rounded(lo:f64,hi:f64)->Option<Self> {
        let (lo,hi)=(lo.next_down(),hi.next_up());
        (lo.is_finite()&&hi.is_finite()&&lo<=hi).then_some(Self{lo,hi})
    }
    fn add(self,other:Self)->Option<Self> {Self::rounded(self.lo+other.lo,self.hi+other.hi)}
    fn sub(self,other:Self)->Option<Self> {Self::rounded(self.lo-other.hi,self.hi-other.lo)}
    fn mul(self,other:Self)->Option<Self> {
        let p=[self.lo*other.lo,self.lo*other.hi,self.hi*other.lo,self.hi*other.hi];
        if p.iter().any(|x|!x.is_finite()){return None;}
        Self::rounded(p.into_iter().fold(f64::INFINITY,f64::min),p.into_iter().fold(f64::NEG_INFINITY,f64::max))
    }
    fn div(self,other:Self)->Option<Self> {
        if other.lo<=0. && other.hi>=0. {return None;}
        let reciprocal=Self::rounded(1./other.hi,1./other.lo)?;
        self.mul(reciprocal)
    }
}

/// Requires the exact world-f32 segment/triangle intersection to lie strictly
/// inside the triangle and segment, with enough separation to prove that fact
/// despite every rounded f64 operation. A denominator interval containing zero
/// (including an insufficiently resolved near-parallel ray) is always refused.
fn impact_interior_certified(vertices:[[f64;3];3],start:[f64;3],end:[f64;3])->Option<(ImpactInterval,ImpactInterval)> {
    fn sub(a:[ImpactInterval;3],b:[ImpactInterval;3])->Option<[ImpactInterval;3]> {
        Some([a[0].sub(b[0])?,a[1].sub(b[1])?,a[2].sub(b[2])?])
    }
    fn cross(a:[ImpactInterval;3],b:[ImpactInterval;3])->Option<[ImpactInterval;3]> {
        Some([a[1].mul(b[2])?.sub(a[2].mul(b[1])?)?,a[2].mul(b[0])?.sub(a[0].mul(b[2])?)?,
            a[0].mul(b[1])?.sub(a[1].mul(b[0])?)?])
    }
    fn dot(a:[ImpactInterval;3],b:[ImpactInterval;3])->Option<ImpactInterval> {
        a[0].mul(b[0])?.add(a[1].mul(b[1])?)?.add(a[2].mul(b[2])?)
    }
    fn vec(v:[f64;3])->Option<[ImpactInterval;3]> {
        Some([ImpactInterval::exact(v[0])?,ImpactInterval::exact(v[1])?,ImpactInterval::exact(v[2])?])
    }
    (||->Option<(ImpactInterval,ImpactInterval)>{
        let a=vec(vertices[0])?;let b=vec(vertices[1])?;let c=vec(vertices[2])?;
        let s0=vec(start)?;let e=vec(end)?;let edge1=sub(b,a)?;let edge2=sub(c,a)?;
        let d=sub(e,s0)?;let h=cross(d,edge2)?;let det=dot(edge1,h)?;
        let s=sub(s0,a)?;let u=dot(s,h)?.div(det)?;let q=cross(s,edge1)?;
        let v=dot(d,q)?.div(det)?;let t=dot(edge2,q)?.div(det)?;
        let one=ImpactInterval::exact(1.)?;let w=one.sub(u)?.sub(v)?;
        if u.lo>0. && v.lo>0. && w.lo>0. && t.lo>0. && t.hi<1. { Some((u,v)) } else { None }
    })()
}

/// Enclose the exact source-local barycentric point and every f32 rounding of
/// that enclosure. Refuse unless the entire enclosure fits the existing
/// per-coordinate contact tolerance, including the selected f32 anchor.
fn impact_anchor_certified(local:[[f32;3];3],point:[f32;3],u:ImpactInterval,v:ImpactInterval,
    anchor:[f32;3])->bool {
    let proof=(||->Option<bool>{
        for i in 0..3 {
            let a=ImpactInterval::exact(f64::from(local[0][i]))?;
            let b=ImpactInterval::exact(f64::from(local[1][i]))?;
            let c=ImpactInterval::exact(f64::from(local[2][i]))?;
            let exact=a.add(u.mul(b.sub(a)?)?)?.add(v.mul(c.sub(a)?)?)?;
            let rounded_lo=f64::from(exact.lo as f32);
            let rounded_hi=f64::from(exact.hi as f32);
            if !rounded_lo.is_finite() || !rounded_hi.is_finite() || !anchor[i].is_finite() || !point[i].is_finite() {return None;}
            let lo=exact.lo.min(rounded_lo);let hi=exact.hi.max(rounded_hi);
            let chosen=f64::from(anchor[i]);let origin=f64::from(point[i]);
            if chosen<lo || chosen>hi || (lo-origin).abs().next_up()>CONTACT_TOLERANCE
                || (hi-origin).abs().next_up()>CONTACT_TOLERANCE {return Some(false);}
        }
        Some(true)
    })();
    proof==Some(true)
}

/// Component-local line through a measured contact, before native quantization.
/// This has no outcome, health or native method/component number semantics.
#[derive(Clone, Debug, PartialEq)]
pub struct ImpactSegment {
    pub component: materials::Component,
    pub bounds: [[f32; 3]; 2],
    pub start: [f32; 3],
    pub end: [f32; 3],
}
// BW-01 wire codec (tools/bw01_wire_gen.py): ImpactSegment
impl crate::bw_wire::Wire for ImpactSegment {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{component,bounds,start,end}=self;W::put(component,bw_o);W::put(bounds,bw_o);W::put(start,bw_o);W::put(end,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{component:W::get(bw_i)?,bounds:W::get(bw_i)?,start:W::get(bw_i)?,end:W::get(bw_i)?})}
}
// end BW-01 wire codec

/// Test-only, bounded evidence for an impact-segment refusal. Float values are
/// recorded as IEEE bits so a replay does not depend on decimal formatting.
#[cfg(test)]
thread_local! {
    // Test-local replay witness, never serialized into the production World.
    static LAST_IMPACT_DIAGNOSTIC_BRANCH:std::cell::Cell<Option<&'static str>> = const { std::cell::Cell::new(None) };
}
#[cfg(test)]
struct ImpactDiagnostic<'a> {
    bundle: &'a Bundle, contact: &'a Contact, branch: &'static str,
    point: [f32;3], direction: [f32;3], bounds: [[f32;3];2], start: [f32;3], end: [f32;3],
    hits: &'a [super::collision::Candidate], at_contact: &'a [bool],
    contact_index: Option<usize>, interval: Option<(f64,f64)>, shifted_start: Option<[f32;3]>,
    shifted_hits: &'a [super::collision::Candidate], shifted_at_contact: &'a [bool],
}
#[cfg(test)]
impl ImpactDiagnostic<'_> {
    fn json(&self)->Value {
        let c=self.contact;
        let candidate=|h:&super::collision::Candidate| serde_json::json!({
            "candidate_index":h.candidate_index,"triangle_id":h.triangle_id,"mesh":h.mesh,
            "group":h.group,"material":h.material,"normal_bits":h.normal.map(f32::to_bits),"t_bits":h.t.to_bits()});
        // Collision itself limits candidates; truncate defensively in case a
        // test constructs this diagnostic directly with a larger slice.
        let local=|hits:&[super::collision::Candidate],at:&[bool]| serde_json::json!({
            "count":hits.len(),"truncated":hits.len()>super::collision::MAX_CANDIDATES,
            "rows":hits.iter().take(super::collision::MAX_CANDIDATES).enumerate().map(|(i,h)|
                serde_json::json!({"triangle_id":h.triangle_id,"t_bits":h.t.to_bits(),"at_contact":at.get(i).copied()})).collect::<Vec<_>>()});
        let effective_bits=c.material_facts.effective.as_ref().map(|m|serde_json::json!({
            "armor_bits":m.armor.map(f32::to_bits),"vehicle_damage_factor_bits":m.vehicle_damage_factor.to_bits(),
            "chance_to_hit_by_projectile_bits":m.chance_to_hit_by_projectile.to_bits(),
            "chance_to_hit_by_explosion_bits":m.chance_to_hit_by_explosion.to_bits()}));
        serde_json::json!({"schema":"perf02-impact-diagnostic.v1","branch":self.branch,
            "vehicle":self.bundle.vehicle_kind().label(),"bundle_sha256":self.bundle.bundle_sha256(),
            "contact":{"shot":c.shot,"target_slot":c.target_slot,"tick":c.tick,
                "segment_start_bits":c.segment_start.map(f32::to_bits),"segment_end_bits":c.segment_end.map(f32::to_bits),
                "segment_seconds_bits":c.segment_seconds.to_bits(),"endpoint_bits":c.endpoint.map(f32::to_bits),
                "target_position_bits":c.target_position.map(f32::to_bits),"target_direction_bits":c.target_direction.map(f32::to_bits),
                "target_aim_bits":c.target_aim.map(f32::to_bits),"triangle":candidate(&c.triangle),
                "geometry_revision":c.geometry_revision,"transform_revision":c.transform_revision,
                "material_facts":c.material_facts.json(),"material_float_bits":effective_bits},
            "local":{"point_bits":self.point.map(f32::to_bits),"direction_bits":self.direction.map(f32::to_bits),
                "bounds_bits":self.bounds.map(|p|p.map(f32::to_bits)),"start_bits":self.start.map(f32::to_bits),
                "end_bits":self.end.map(f32::to_bits),"hits":local(self.hits,self.at_contact),
                "contact_index":self.contact_index,"interval_f64_bits":self.interval.map(|(a,b)|[a.to_bits(),b.to_bits()]),
                "shifted_start_bits":self.shifted_start.map(|p|p.map(f32::to_bits)),
                "shifted_hits":local(self.shifted_hits,self.shifted_at_contact)}})
    }
    fn emit(&self)->io::Result<()> {
        LAST_IMPACT_DIAGNOSTIC_BRANCH.with(|branch|branch.set(Some(self.branch)));
        if std::env::var("PERF02_CAPTURE_IMPACT").as_deref()==Ok("1") {
            write_impact_diagnostic(&mut io::stderr().lock(),&self.json())?;
        }
        Ok(())
    }
}

#[cfg(test)]
const IMPACT_DIAGNOSTIC_MAX_BYTES:usize=65536;
/// Buffer before touching stderr: oversize/serialization failures never leave
/// a partial receipt. An I/O failure may leave a partial line and is reported.
/// Both serialization and the newline count toward the cap.
#[cfg(test)]
fn write_impact_diagnostic<W:io::Write>(writer:&mut W,value:&Value)->io::Result<()> {
    struct Bounded(Vec<u8>);
    impl io::Write for Bounded {
        fn write(&mut self,bytes:&[u8])->io::Result<usize> {
            if bytes.len()>IMPACT_DIAGNOSTIC_MAX_BYTES.saturating_sub(self.0.len()) {
                return Err(io::Error::new(io::ErrorKind::InvalidData,"impact diagnostic size limit"));
            }
            self.0.extend_from_slice(bytes);Ok(bytes.len())
        }
        fn flush(&mut self)->io::Result<()> {Ok(())}
    }
    let mut buffer=Bounded(Vec::new());
    serde_json::to_writer(&mut buffer,value).map_err(|e|io::Error::new(io::ErrorKind::InvalidData,format!("impact diagnostic serialization/size: {e}")))?;
    io::Write::write_all(&mut buffer,b"\n").map_err(|e|io::Error::new(e.kind(),format!("impact diagnostic newline/size: {e}")))?;
    writer.write_all(&buffer.0).map_err(|e|io::Error::new(e.kind(),format!("impact diagnostic stderr write: {e}")))
}

/// Decode only the bounded diagnostic schema and revalidate its source facts
/// against the caller's pinned Bundle. No arbitrary object deserialization.
#[cfg(test)]
fn decode_impact_diagnostic(raw:&[u8],bundle:&Bundle)->io::Result<Contact> {
    fn invalid()->io::Error {io::Error::new(io::ErrorKind::InvalidData,"impact diagnostic receipt")}
    fn text<'a>(v:&'a Value,key:&str)->io::Result<&'a str> {
        v.get(key).and_then(Value::as_str).filter(|s|s.len()<=128).ok_or_else(invalid)
    }
    fn u32_value(v:&Value,key:&str)->io::Result<u32> {
        v.get(key).and_then(Value::as_u64).and_then(|n|u32::try_from(n).ok()).ok_or_else(invalid)
    }
    fn bits<const N:usize>(v:&Value,key:&str)->io::Result<[f32;N]> {
        let a=v.get(key).and_then(Value::as_array).filter(|a|a.len()==N).ok_or_else(invalid)?;
        let mut values=[0.;N];
        for (i,item) in a.iter().enumerate() {
            let n=item.as_u64().and_then(|n|u32::try_from(n).ok()).ok_or_else(invalid)?;
            values[i]=f32::from_bits(n);
            if !values[i].is_finite(){return Err(invalid());}
        }
        Ok(values)
    }
    if raw.len()>IMPACT_DIAGNOSTIC_MAX_BYTES {return Err(invalid());}
    let root:Value=serde_json::from_slice(raw).map_err(|_|invalid())?;
    if text(&root,"schema")?!="perf02-impact-diagnostic.v1" || text(&root,"vehicle")?!=bundle.vehicle_kind().label()
        || text(&root,"bundle_sha256")?!=bundle.bundle_sha256() {return Err(invalid());}
    let c=root.get("contact").ok_or_else(invalid)?;let h=c.get("triangle").ok_or_else(invalid)?;
    let t=f32::from_bits(u32_value(h,"t_bits")?);if !t.is_finite(){return Err(invalid());}
    let triangle=super::collision::Candidate{candidate_index:usize::try_from(h.get("candidate_index").and_then(Value::as_u64).ok_or_else(invalid)?).map_err(|_|invalid())?,
        triangle_id:u32_value(h,"triangle_id")?,mesh:text(h,"mesh")?.to_owned(),group:text(h,"group")?.to_owned(),
        material:text(h,"material")?.to_owned(),normal:bits(h,"normal_bits")?,t};
    let facts=bundle.materials.lookup(&triangle.mesh,&triangle.material)?;
    let effective_bits=facts.effective.as_ref().map(|m|serde_json::json!({
        "armor_bits":m.armor.map(f32::to_bits),"vehicle_damage_factor_bits":m.vehicle_damage_factor.to_bits(),
        "chance_to_hit_by_projectile_bits":m.chance_to_hit_by_projectile.to_bits(),
        "chance_to_hit_by_explosion_bits":m.chance_to_hit_by_explosion.to_bits()}));
    if c.get("material_facts")!=Some(&facts.json()) || c.get("material_float_bits")!=Some(&serde_json::json!(effective_bits)) {return Err(invalid());}
    let target_slot=usize::try_from(c.get("target_slot").and_then(Value::as_u64).ok_or_else(invalid)?).map_err(|_|invalid())?;
    let tick=u32_value(c,"tick")?;
    if target_slot>=super::model::MAX_ACTORS || tick<1000 {return Err(invalid());}
    let position=bits(c,"target_position_bits")?;
    let direction=bits(c,"target_direction_bits")?;let aim=bits(c,"target_aim_bits")?;
    let geometry_revision=text(c,"geometry_revision")?.to_owned();let transform_revision=text(c,"transform_revision")?.to_owned();
    if geometry_revision!=bundle.geometry_revision() || transform_revision!=super::geometry::transform_revision(position,direction,aim,target_slot,tick) {return Err(invalid());}
    let seconds=f32::from_bits(u32_value(c,"segment_seconds_bits")?);if !seconds.is_finite(){return Err(invalid());}
    let contact=Contact{shot:u32_value(c,"shot")?,target_slot,tick,segment_start:bits(c,"segment_start_bits")?,
        segment_end:bits(c,"segment_end_bits")?,segment_seconds:seconds,endpoint:bits(c,"endpoint_bits")?,
        target_position:position,target_direction:direction,target_aim:aim,triangle,geometry_revision,transform_revision,material_facts:facts};
    // A receipt cannot substitute a different source triangle for this pose.
    let mesh=bundle.mesh_for_pose(position,direction,aim,target_slot,tick)?;
    if !super::collision::query(&mesh,contact.segment_start,contact.segment_end)?.iter().any(|candidate|
        candidate==&contact.triangle && candidate.t.to_bits()==contact.triangle.t.to_bits()
        && candidate.normal.map(f32::to_bits)==contact.triangle.normal.map(f32::to_bits)) {return Err(invalid());}
    for i in 0..3 {
        let expected=contact.segment_start[i]+contact.triangle.t*(contact.segment_end[i]-contact.segment_start[i]);
        if expected.to_bits()!=contact.endpoint[i].to_bits(){return Err(invalid());}
    }
    Ok(contact)
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
// BW-01 wire codec (tools/bw01_wire_gen.py): Component
impl crate::bw_wire::Wire for Component {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{vertices,triangles}=self;W::put(vertices,bw_o);W::put(triangles,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{vertices:W::get(bw_i)?,triangles:W::get(bw_i)?})}
}
// end BW-01 wire codec
#[derive(Clone, Debug)]
pub struct Bundle {
    vehicle: VehicleKind,
    components: Vec<Component>,
    hull: [f32; 3], turret: [f32; 3], gun: [f32; 3],
    materials: Catalog,
    bounds:[[[f32;3];2];3],
}
// BW-01 wire codec (tools/bw01_wire_gen.py): Bundle
impl crate::bw_wire::Wire for Bundle {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{vehicle,components,hull,turret,gun,materials,bounds}=self;W::put(vehicle,bw_o);W::put(components,bw_o);W::put(hull,bw_o);W::put(turret,bw_o);W::put(gun,bw_o);W::put(materials,bw_o);W::put(bounds,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{vehicle:W::get(bw_i)?,components:W::get(bw_i)?,hull:W::get(bw_i)?,turret:W::get(bw_i)?,gun:W::get(bw_i)?,materials:W::get(bw_i)?,bounds:W::get(bw_i)?})}
}
// end BW-01 wire codec
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
            "0971afa6aed7bbbb0c4ba647560e15002571544cc168005679a9d46a22962aae"=>VehicleKind::Wt128,
            "c14b10be359a86c4c4632cd0943d06c43a47fc9ede2a982880c4f09aed6ecb1d"=>VehicleKind::Fv183,
            digest => return Self::from_generated_source(digest,raw),
        };
        // New schema is decoded by its closed, kind-neutral source importer.
        // Existing five formats and their arithmetic below are unchanged.
        if matches!(vehicle,VehicleKind::Wt128|VehicleKind::Fv183){return Self::from_p06t_source(vehicle,raw);}
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
    /// BATTLE-ANY bundle: the exact digest must be a registry geometry pin.
    /// Slots are Hull/Turret_01/Gun_01; source part names are checked, triangle
    /// IDs kept, exact zero-area triangles listed by the source are dropped.
    fn from_generated_source(digest:&str,raw:&[u8])->io::Result<Self>{
        let registry=super::generated_vehicles::registry()?;
        let vehicle=VehicleKind::Generated(registry.by_geometry(digest).ok_or_else(||bad())?);
        let e=vehicle.generated().ok_or_else(||bad())?;
        if raw.len() as u64!=e.geometry_bytes {return Err(bad());}
        let value:Value=serde_json::from_slice(raw).map_err(|_|bad())?;
        fields(&value,&["battle_admission","classification","geometry","identity","members","schema","vehicle_id","wheel_source"])?;
        let descriptor=vehicle.descriptor().iter().map(|byte|format!("{byte:02x}")).collect::<String>();
        if value["schema"]!="battle-any-source.v1"||value["vehicle_id"]!=e.vehicle_id.as_str()||value["battle_admission"]!=false
            ||value["classification"]!="VERIFIED_STATIC_ORIGINAL_717"||value["identity"]["descriptor_hex"]!=descriptor.as_str()
            ||value["identity"]["type_compact_id"]!=vehicle.vehicle_compact_id() {return Err(bad());}
        let geometry=&value["geometry"];
        fields(geometry,&["components","gun_position","hull_position","turret_position"])?;
        let hull=vector(&geometry["hull_position"])?;let turret=vector(&geometry["turret_position"])?;let gun=vector(&geometry["gun_position"])?;
        if [hull,turret,gun]!=e.pivots {return Err(bad());}
        let materials=Catalog::from_generated(vehicle,&geometry["components"])?;
        let rows=geometry["components"].as_array().filter(|rows|rows.len()==3).ok_or_else(||bad())?;
        let mut components=Vec::with_capacity(3);let mut bounds=[[[0f32;3];2];3];
        for (i,row) in rows.iter().enumerate() {
            fields(row,&["excluded_degenerate_triangle_ids","materials","mesh_bounds","name","triangles","vertex_format","vertices","visual_bounds"])?;
            let part=e.parts[i].as_str();let logical=["Hull","Turret_01","Gun_01"][i];
            if row["name"]!=part||!matches!(row["vertex_format"].as_str(),Some("xyznuv"|"xyznuvtb")) {return Err(bad());}
            let visual=row["visual_bounds"].as_array().filter(|r|r.len()==2).ok_or_else(||bad())?;
            bounds[i]=[vector(&visual[0])?,vector(&visual[1])?];
            let excluded=row["excluded_degenerate_triangle_ids"].as_array().ok_or_else(||bad())?.iter().map(uint).collect::<io::Result<Vec<_>>>()?;
            let vr=row["vertices"].as_array().filter(|r|!r.is_empty()&&r.len()<=8192).ok_or_else(||bad())?;
            let tr=row["triangles"].as_array().filter(|r|!r.is_empty()&&r.len()<=16384).ok_or_else(||bad())?;
            let vertices=vr.iter().map(vector).collect::<io::Result<Vec<_>>>()?;
            let mut triangles=Vec::with_capacity(tr.len());
            for (index,t) in tr.iter().enumerate() {
                fields(t,&["triangle_id","a","b","c","mesh","group","material"])?;
                let id=uint(&t["triangle_id"])?;
                if id!=i as u32*100000+index as u32||t["mesh"]!=part {return Err(bad());}
                if excluded.contains(&id) {continue;}
                let triangle=Triangle{triangle_id:id,a:uint(&t["a"])?,b:uint(&t["b"])?,c:uint(&t["c"])?,
                    mesh:logical.into(),group:text(&t["group"])?,material:text(&t["material"])?};
                materials.lookup(&triangle.mesh,&triangle.material)?;triangles.push(triangle);
            }
            if triangles.len()+excluded.len()!=tr.len() {return Err(bad());}
            Mesh::new(vertices.clone(),triangles.clone(),source_revision(vehicle),"component-local-v1")?;
            components.push(Component{vertices,triangles});
        }
        Ok(Self{vehicle,components,hull,turret,gun,materials,bounds})
    }
    fn from_p06t_source(vehicle:VehicleKind,raw:&[u8])->io::Result<Self>{
        use super::p06t_geometry_source::{Assembly,SourceBundle};
        let source=SourceBundle::parse(raw)?;
        let expected=match vehicle{VehicleKind::Wt128=>Assembly::Wt128,VehicleKind::Fv183=>Assembly::Fv183,_=>return Err(bad())};
        if source.assembly!=expected{return Err(bad());}
        let materials=Catalog::from_p06t_source(vehicle,&source)?;
        let bounds=std::array::from_fn(|i|source.components[i].visual_bounds);
        let [hull,turret,gun]=source.pivots;
        let mut components=Vec::with_capacity(3);
        for component in source.components{
            Mesh::new(component.vertices.clone(),component.triangles.clone(),source_revision(vehicle),"component-local-v1")?;
            components.push(Component{vertices:component.vertices,triangles:component.triangles});
        }
        Ok(Self{vehicle,components,hull,turret,gun,materials,bounds})
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
    /// Source-mounted positions and descriptor bounds used by P07B spotting.
    pub(crate) fn spotting_parts(&self) -> super::spotting::Parts {
        super::spotting::Parts { hull: self.hull, turret: self.turret, gun: self.gun,
            hull_bounds: self.bounds[0], turret_top: self.bounds[1][1][1] }
    }
    pub fn bundle_sha256(&self) -> &'static str { bundle_sha256(self.vehicle) }
    fn component_bounds(&self) -> [[[f32; 3]; 2]; 3] {self.bounds}
    pub fn materials(&self) -> &Catalog { &self.materials }
    /// TURRET-01: source collision vertices of Turret and Gun that are extreme
    /// along 98 fixed directions, in the detached body frame (origin `pivot`
    /// in the vehicle frame, turret yaw applied, gun at neutral pitch as the
    /// client's DetachedTurret attaches its gun). Their convex hull is inscribed
    /// in the component hull; Jolt builds the shape from them.
    pub fn detached_support_points(&self, pivot: [f32; 3]) -> io::Result<(Vec<[f32; 3]>, Vec<[f32; 3]>)> {
        let mut directions = Vec::new();
        for i in -2i8..=2 { for j in -2i8..=2 { for k in -2i8..=2 {
            if i.abs().max(j.abs()).max(k.abs()) == 2 { directions.push([f32::from(i), f32::from(j), f32::from(k)]); }
        }}}
        let origin = |extra: [f32; 3]| -> [f32; 3] { std::array::from_fn(|a| self.hull[a] + self.turret[a] + extra[a] - pivot[a]) };
        let support = |component: &Component, offset: [f32; 3]| -> io::Result<Vec<[f32; 3]>> {
            let mut chosen: Vec<usize> = Vec::new();
            for d in &directions {
                let dot = |v: &[f32; 3]| v[0] * d[0] + v[1] * d[1] + v[2] * d[2];
                let best = (0..component.vertices.len()).max_by(|a, b| dot(&component.vertices[*a]).total_cmp(&dot(&component.vertices[*b])).then(b.cmp(a)))
                    .ok_or_else(|| bad())?;
                if !chosen.contains(&best) { chosen.push(best); }
            }
            let points = chosen.into_iter().map(|i| std::array::from_fn(|a| component.vertices[i][a] + offset[a])).collect::<Vec<[f32; 3]>>();
            let extent = (0..3).map(|a| points.iter().map(|p| p[a]).fold(f32::MIN, f32::max) - points.iter().map(|p| p[a]).fold(f32::MAX, f32::min)).fold(f32::MAX, f32::min);
            if points.len() < 4 || !(0.01..=20.).contains(&extent) || points.iter().flatten().any(|v| !v.is_finite() || v.abs() > 20.) { return Err(bad()); }
            Ok(points)
        };
        Ok((support(&self.components[1], origin([0.; 3]))?, support(&self.components[2], origin(self.gun))?))
    }
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
        let part = &self.components[index];
        let mesh = Mesh::new(part.vertices.clone(), part.triangles.clone(), self.geometry_revision(), "impact-component-local-v1")?;
        let native_hits = |start: [f32; 3], end: [f32; 3]| -> io::Result<_> {
            let extended_start: [f32; 3] = std::array::from_fn(|i| start[i] - 0.01 * (end[i] - start[i]));
            let extended_end: [f32; 3] = std::array::from_fn(|i| end[i] + 0.01 * (end[i] - start[i]));
            let hits = super::collision::query(&mesh, extended_start, extended_end)?;
            let at_contact: Vec<bool> = hits.iter().map(|hit| (0..3).all(|i| (f64::from(extended_start[i]
                + hit.t * (extended_end[i] - extended_start[i])) - f64::from(point[i])).abs() <= CONTACT_TOLERANCE)).collect();
            Ok((hits, at_contact))
        };
        let (hits, at_contact) = native_hits(start, end)?;
        if hits.is_empty() { return Err(io::Error::new(io::ErrorKind::InvalidData, "impact segment has no local surface")); }
        if at_contact[0] { return Ok(ImpactSegment { component, bounds, start, end }); }
        // Point-blank shot: the projectile segment starts just past another
        // surface of this component (owner run 2026-10-19: an MS-1 muzzle
        // already inside the IS-7 hull). The native 1% backward extension
        // would select that surface. Move only the presentation start forward
        // so the extension stays between it and the contact, then re-verify.
        // Contact, armor decision and HP are unchanged.
        let differs = || io::Error::new(io::ErrorKind::InvalidData, "impact segment first surface differs from contact");
        let contact_index = match at_contact.iter().position(|&hit| hit) {
            Some(index)=>index,
            None=>{
                // The authoritative first hit can be exactly on its source
                // face while the inverse-transformed f32 endpoint misses that
                // face by a few ulps. For a grazing ray that tiny normal error
                // moves the local intersection far along the surface. Only a
                // fully revalidated world-first hit may try a bounded reanchor.
                if let Some(anchor) = self.impact_source_anchor(contact,index,point)? {
                    let (reanchored_start,reanchored_end)=clipped_line(anchor,direction,bounds,Some(minimum))?;
                    let (reanchored_hits,reanchored_at_contact)=native_hits(reanchored_start,reanchored_end)?;
                    if reanchored_at_contact.first()==Some(&true)
                        && first_surface_unambiguous(&reanchored_hits,&contact.triangle)
                        && self.impact_packed_first_matches(component,bounds,reanchored_start,reanchored_end,&mesh,&contact.triangle)? {
                        return Ok(ImpactSegment{component,bounds,start:reanchored_start,end:reanchored_end});
                    }
                }
                #[cfg(test)] ImpactDiagnostic{bundle:self,contact,branch:"contact_not_in_local_hits",point,direction,bounds,start,end,
                    hits:&hits,at_contact:&at_contact,contact_index:None,interval:None,shifted_start:None,shifted_hits:&[],shifted_at_contact:&[]}.emit()?;
                return Err(differs());
            },
        };
        // Extended query parameter t maps to segment fraction 1.02t - 0.01; a
        // start at fraction s is extended by the native decoder to s - 0.01(1 - s).
        let fraction = |t: f32| f64::from(t) * 1.02 - 0.01;
        let lowest = (fraction(hits[contact_index - 1].t) + 0.01) / 1.01;
        let highest = fraction(hits[contact_index].t);
        if !(lowest < highest) {
            #[cfg(test)] ImpactDiagnostic{bundle:self,contact,branch:"no_separating_interval",point,direction,bounds,start,end,
                hits:&hits,at_contact:&at_contact,contact_index:Some(contact_index),interval:Some((lowest,highest)),shifted_start:None,shifted_hits:&[],shifted_at_contact:&[]}.emit()?;
            return Err(differs());
        }
        let shifted = 0.5 * (lowest + highest);
        let shifted_start: [f32; 3] = std::array::from_fn(|i| (f64::from(start[i]) + shifted * (f64::from(end[i]) - f64::from(start[i]))) as f32);
        let (shifted_hits, shifted_at_contact) = native_hits(shifted_start, end)?;
        if shifted_at_contact.first() != Some(&true) {
            #[cfg(test)] ImpactDiagnostic{bundle:self,contact,branch:"shifted_first_mismatch",point,direction,bounds,start,end,
                hits:&hits,at_contact:&at_contact,contact_index:Some(contact_index),interval:Some((lowest,highest)),shifted_start:Some(shifted_start),shifted_hits:&shifted_hits,shifted_at_contact:&shifted_at_contact}.emit()?;
            return Err(differs());
        }
        #[cfg(not(test))] let _=shifted_hits;
        Ok(ImpactSegment { component, bounds, start:shifted_start, end })
    }
    /// Reconstruct a source-local point from the first authoritative world
    /// triangle, never from an unverified ID alone. The admissible correction
    /// is the existing CONTACT_TOLERANCE per coordinate, not a wider limit.
    /// Ambiguous triangle edges are refused; this is a conservative fallback.
    fn impact_source_anchor(&self,contact:&Contact,index:usize,point:[f32;3])->io::Result<Option<[f32;3]>> {
        let world=self.mesh_for_pose(contact.target_position,contact.target_direction,contact.target_aim,contact.target_slot,contact.tick)?;
        let hits=super::collision::query(&world,contact.segment_start,contact.segment_end)?;
        let expected=match hits.first() {Some(hit)=>hit,None=>return Ok(None)};
        if !first_surface_unambiguous(&hits,expected) {return Ok(None);}
        if expected!=&contact.triangle || expected.t.to_bits()!=contact.triangle.t.to_bits()
            || expected.normal.map(f32::to_bits)!=contact.triangle.normal.map(f32::to_bits) {return Ok(None);}
        let endpoint:[f32;3]=std::array::from_fn(|i|contact.segment_start[i]
            + expected.t*(contact.segment_end[i]-contact.segment_start[i]));
        if endpoint.map(f32::to_bits)!=contact.endpoint.map(f32::to_bits){return Ok(None);}
        let part=&self.components[index];
        let triangle=match part.triangles.iter().find(|t|t.triangle_id==expected.triangle_id){Some(t)=>t,None=>return Ok(None)};
        if triangle.mesh!=expected.mesh || triangle.group!=expected.group || triangle.material!=expected.material{return Ok(None);}
        let mut local=[[0_f32;3];3];let mut vertices=[[0_f64;3];3];
        for (i,vertex_index) in [triangle.a,triangle.b,triangle.c].into_iter().enumerate() {
            local[i]=*part.vertices.get(vertex_index as usize).ok_or_else(||bad())?;
            let mounted=self.component_point(index,local[i],contact.target_aim[0],contact.target_aim[1]);
            let rotated=pose::rotate(mounted,contact.target_direction);
            vertices[i]=std::array::from_fn(|axis|f64::from(contact.target_position[axis]+rotated[axis]));
        }
        let sub=|a:[f64;3],b:[f64;3]|std::array::from_fn::<_,3,_>(|i|a[i]-b[i]);
        let cross=|a:[f64;3],b:[f64;3]|[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
        let dot=|a:[f64;3],b:[f64;3]|a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
        let a=vertices[0];let edge1=sub(vertices[1],a);let edge2=sub(vertices[2],a);
        let start=contact.segment_start.map(f64::from);
        let (u_interval,v_interval)=match impact_interior_certified(vertices,start,contact.segment_end.map(f64::from)) {
            Some(intervals)=>intervals,None=>return Ok(None),
        };
        let direction=sub(contact.segment_end.map(f64::from),start);
        let h=cross(direction,edge2);let determinant=dot(edge1,h);
        if !determinant.is_finite() || determinant==0. {return Ok(None);}
        let inverse=1./determinant;let s=sub(start,a);let u=inverse*dot(s,h);
        let q=cross(s,edge1);let v=inverse*dot(direction,q);let t=inverse*dot(edge2,q);
        // Strict interior and segment bounds deliberately refuse edge/tie
        // ambiguity and the tolerance-only hits admitted by collision::query.
        if !u.is_finite() || !v.is_finite() || !t.is_finite() || u<=0. || v<=0. || u+v>=1.
            || !(0. ..=1.).contains(&t) || (t as f32).to_bits()!=expected.t.to_bits() {return Ok(None);}
        let anchor:[f32;3]=std::array::from_fn(|i|(f64::from(local[0][i])
            + u*(f64::from(local[1][i])-f64::from(local[0][i]))
            + v*(f64::from(local[2][i])-f64::from(local[0][i]))) as f32);
        if !impact_anchor_certified(local,point,u_interval,v_interval,anchor) {return Ok(None);}
        Ok(Some(anchor))
    }
    /// Conservative models of the documented byte decoder. Actual #717
    /// hitTester bounds, arithmetic and BSP tie order remain native gates.
    fn impact_packed_first_matches(&self,component:materials::Component,bounds:[[f32;3];2],start:[f32;3],end:[f32;3],
        mesh:&Mesh,expected:&super::collision::Candidate)->io::Result<bool> {
        use super::impact_wire::{packed_segment,ShotOutcome};
        let category=match component {materials::Component::Hull=>1,materials::Component::Turret01=>2,
            materials::Component::Gun02|materials::Component::Gun01=>3};
        // Outcome is irrelevant to coordinates. The actual resolved outcome
        // is still supplied by the normal publication path.
        let bytes=packed_segment(category,bounds,start,end,ShotOutcome::Pierced)?;
        for wide in [false,true] {
            let decode=|offset:usize|std::array::from_fn::<_,3,_>(|i|if wide {
                (f64::from(bounds[0][i])+(f64::from(bounds[1][i])-f64::from(bounds[0][i]))
                    *f64::from(bytes[offset+i])/255.0) as f32
            } else {bounds[0][i]+(bounds[1][i]-bounds[0][i])*f32::from(bytes[offset+i])/255.0});
            let s=decode(2);let e=decode(5);
            let extension=|axis:usize,at_end:bool|if wide {
                let (s,e)=(f64::from(s[axis]),f64::from(e[axis]));
                (if at_end {e+0.01*(e-s)} else {s-0.01*(e-s)}) as f32
            }else if at_end {e[axis]+0.01_f32*(e[axis]-s[axis])}
                else {s[axis]-0.01_f32*(e[axis]-s[axis])};
            let qs=std::array::from_fn(|i|extension(i,false));let qe=std::array::from_fn(|i|extension(i,true));
            if !first_surface_unambiguous(&super::collision::query(mesh,qs,qe)?,expected){return Ok(false);}
        }
        Ok(true)
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
    #[test] fn perf02_impact_diagnostic_has_exact_bits_and_bounded_hit_rows() {
        let b=bundle();
        let c=contact_for(&b,0,[-4.,0.,0.],[4.,0.,0.],[0.;3],[0.;2]);
        let hits=vec![c.triangle.clone();super::super::collision::MAX_CANDIDATES+3];
        let at=vec![false;hits.len()];
        let diagnostic=ImpactDiagnostic{bundle:&b,contact:&c,branch:"contact_not_in_local_hits",
            point:[1.,-0.,3.],direction:[4.,5.,6.],bounds:[[-1.;3],[1.;3]],start:[0.;3],end:[1.;3],
            hits:&hits,at_contact:&at,contact_index:None,interval:None,shifted_start:None,shifted_hits:&[],shifted_at_contact:&[]};
        let value=diagnostic.json();
        assert_eq!(value["schema"],"perf02-impact-diagnostic.v1");
        assert_eq!(value["branch"],"contact_not_in_local_hits");
        assert_eq!(value["bundle_sha256"],b.bundle_sha256());
        assert_eq!(value["contact"]["segment_start_bits"][0],c.segment_start[0].to_bits());
        assert_eq!(value["contact"]["triangle"]["t_bits"],c.triangle.t.to_bits());
        assert_eq!(value["local"]["point_bits"][1],(-0.0f32).to_bits());
        assert_eq!(value["local"]["hits"]["truncated"],true);
        assert_eq!(value["local"]["hits"]["rows"].as_array().unwrap().len(),super::super::collision::MAX_CANDIDATES);
        assert!(serde_json::to_vec(&value).unwrap().len()<65536);
        let mut receipt=Vec::new();write_impact_diagnostic(&mut receipt,&value).unwrap();
        assert_eq!(receipt.last(),Some(&b'\n'));
        let restored=decode_impact_diagnostic(&receipt,&b).unwrap();
        assert_eq!(restored,c);
        let rebuilt=ImpactDiagnostic{bundle:&b,contact:&restored,branch:"contact_not_in_local_hits",
            point:[1.,-0.,3.],direction:[4.,5.,6.],bounds:[[-1.;3],[1.;3]],start:[0.;3],end:[1.;3],
            hits:&hits,at_contact:&at,contact_index:None,interval:None,shifted_start:None,shifted_hits:&[],shifted_at_contact:&[]}.json();
        // Compare every serialized input field, including signed zero bits.
        assert_eq!(rebuilt["contact"],value["contact"]);
        let mut foreign=value.clone();foreign["bundle_sha256"]=serde_json::json!("not-the-pinned-bundle");
        assert!(decode_impact_diagnostic(&serde_json::to_vec(&foreign).unwrap(),&b).is_err());
    }
    #[test] fn perf02_impact_diagnostic_writer_rejects_broken_and_oversized() {
        struct Broken;
        impl io::Write for Broken {
            fn write(&mut self,_:&[u8])->io::Result<usize>{Err(io::Error::new(io::ErrorKind::BrokenPipe,"closed"))}
            fn flush(&mut self)->io::Result<()> {Ok(())}
        }
        let error=write_impact_diagnostic(&mut Broken,&serde_json::json!({"a":1})).unwrap_err();
        assert_eq!(error.kind(),io::ErrorKind::BrokenPipe);
        assert!(error.to_string().contains("impact diagnostic stderr write"));
        let mut out=Vec::new();let huge=serde_json::json!({"oversized":"x".repeat(IMPACT_DIAGNOSTIC_MAX_BYTES)});
        let error=write_impact_diagnostic(&mut out,&huge).unwrap_err();
        assert_eq!(error.kind(),io::ErrorKind::InvalidData);assert!(out.is_empty());
        assert!(error.to_string().contains("impact diagnostic serialization/size"));
    }
    /// Explicit opt-in replay of one locally retained diagnostic JSON line.
    /// The caller supplies a pinned geometry bundle and its permitted local root.
    #[test]
    #[ignore]
    fn perf02_impact_receipt_reanchors_first_surface() {
        let receipt=std::env::var("PERF02_IMPACT_RECEIPT").expect("PERF02_IMPACT_RECEIPT");
        let root=std::env::var("PERF02_IMPACT_LOCAL_ROOT").expect("PERF02_IMPACT_LOCAL_ROOT");
        let path=std::env::var("PERF02_IMPACT_BUNDLE").expect("PERF02_IMPACT_BUNDLE");
        let receipt=Path::new(&receipt);
        assert!(receipt.is_absolute(),"receipt must be a local absolute path");
        #[cfg(windows)] {
            use std::path::{Component,Prefix};
            assert!(matches!(receipt.components().next(),Some(Component::Prefix(p))
                if matches!(p.kind(),Prefix::Disk(_)|Prefix::VerbatimDisk(_))),"receipt must be on a local drive");
        }
        non_reparse(receipt).expect("receipt must have no reparse or symlink path");
        let file=fs::File::open(receipt).unwrap();assert!(file.metadata().unwrap().is_file(),"receipt must be a file");
        let mut raw=Vec::new();
        file.take((IMPACT_DIAGNOSTIC_MAX_BYTES+1) as u64).read_to_end(&mut raw).unwrap();
        assert!(raw.len()<=IMPACT_DIAGNOSTIC_MAX_BYTES,"receipt exceeds bound");
        let b=Bundle::load(Path::new(&root),Path::new(&path)).unwrap();
        let contact=decode_impact_diagnostic(&raw,&b).unwrap();
        let value:Value=serde_json::from_slice(&raw).unwrap();
        let branch=value["branch"].as_str().expect("receipt branch");
        assert!(matches!(branch,"contact_not_in_local_hits"|"no_separating_interval"|"shifted_first_mismatch"),"unknown branch");
        LAST_IMPACT_DIAGNOSTIC_BRANCH.with(|state|state.set(None));
        assert_eq!(branch,"contact_not_in_local_hits");
        let segment=b.impact_segment(&contact).expect("bounded reanchor of the retained world-first contact");
        assert!(same_surface(&native_decoder_first(&b,&segment),&contact.triangle));
        assert_eq!(LAST_IMPACT_DIAGNOSTIC_BRANCH.with(|state|state.get()),None);
        let part=&b.components[0];
        let mesh=Mesh::new(part.vertices.clone(),part.triangles.clone(),b.geometry_revision(),"perf02-reanchor-replay").unwrap();
        assert!(b.impact_packed_first_matches(segment.component,segment.bounds,segment.start,segment.end,&mesh,&contact.triangle).unwrap());
        // Exercise rejection through the actual fallback, not just its helper.
        // Neither forged field affects the legacy pre-fallback local query.
        let mut forged_index=contact.clone();
        forged_index.triangle.candidate_index=forged_index.triangle.candidate_index.checked_add(1).unwrap();
        LAST_IMPACT_DIAGNOSTIC_BRANCH.with(|state|state.set(None));
        assert_eq!(b.impact_segment(&forged_index).unwrap_err().to_string(),"impact segment first surface differs from contact");
        assert_eq!(LAST_IMPACT_DIAGNOSTIC_BRANCH.with(|state|state.get()),Some("contact_not_in_local_hits"));
        let mut forged_normal=contact.clone();
        let axis=(0..3).max_by(|&a,&b|forged_normal.triangle.normal[a].abs().total_cmp(&forged_normal.triangle.normal[b].abs())).unwrap();
        assert_ne!(forged_normal.triangle.normal[axis],0.);
        forged_normal.triangle.normal[axis]=-forged_normal.triangle.normal[axis];
        LAST_IMPACT_DIAGNOSTIC_BRANCH.with(|state|state.set(None));
        assert_eq!(b.impact_segment(&forged_normal).unwrap_err().to_string(),"impact segment first surface differs from contact");
        assert_eq!(LAST_IMPACT_DIAGNOSTIC_BRANCH.with(|state|state.get()),Some("contact_not_in_local_hits"));
        println!("PERF02_IMPACT_REPLAY vehicle={} bundle_sha256={} shot={} target={} tick={} original_branch={} bounded_reanchor=true",
            b.vehicle_kind().label(),b.bundle_sha256(),contact.shot,contact.target_slot,contact.tick,branch);
    }
    /// Reconstructs one retained refusal and compares its packed visual ray
    /// under two explicit arithmetic models. This is an offline model, not a
    /// native client or a claim of exact decoder arithmetic/appearance.
    #[test]
    #[ignore]
    fn perf02_impact_receipt_packed_wire_models() {
        use super::super::impact_wire::{packed_segment, ShotOutcome};
        let receipt = std::env::var("PERF02_IMPACT_RECEIPT").expect("PERF02_IMPACT_RECEIPT");
        let root = std::env::var("PERF02_IMPACT_LOCAL_ROOT").expect("PERF02_IMPACT_LOCAL_ROOT");
        let path = std::env::var("PERF02_IMPACT_BUNDLE").expect("PERF02_IMPACT_BUNDLE");
        let receipt = Path::new(&receipt);
        assert!(receipt.is_absolute());
        non_reparse(receipt).expect("no reparse or symlink path");
        let file = fs::File::open(receipt).unwrap();
        assert!(file.metadata().unwrap().is_file());
        let mut raw = Vec::new();
        file.take((IMPACT_DIAGNOSTIC_MAX_BYTES + 1) as u64).read_to_end(&mut raw).unwrap();
        assert!(raw.len() <= IMPACT_DIAGNOSTIC_MAX_BYTES);
        assert_eq!(format!("{:x}", Sha256::digest(&raw)), "973bddd51c407ed10d99350b5753e2fef746c93ee87d1c6a809ae8ecb6ab7763");
        let b = Bundle::load(Path::new(&root), Path::new(&path)).unwrap();
        assert_eq!(b.bundle_sha256(), "25b6c69fd51e26abbda9b16c35572b5f289f2320d0dffe4085dea1b7bdeba1bb");
        let contact = decode_impact_diagnostic(&raw, &b).unwrap();
        let value: Value = serde_json::from_slice(&raw).unwrap();
        assert_eq!(value["branch"], "contact_not_in_local_hits");
        assert_eq!(contact.triangle.triangle_id, 93);
        LAST_IMPACT_DIAGNOSTIC_BRANCH.with(|state|state.set(None));
        assert!(b.impact_segment(&contact).is_ok(),"retained receipt must take the bounded fallback");
        assert_eq!(LAST_IMPACT_DIAGNOSTIC_BRANCH.with(|state|state.get()),None);
        let vec3 = |value: &Value| -> [f32;3] {
            let a = value.as_array().unwrap(); assert_eq!(a.len(),3);
            std::array::from_fn(|i| f32::from_bits(u32::try_from(a[i].as_u64().unwrap()).unwrap()))
        };
        let local = &value["local"];
        let bounds = [vec3(&local["bounds_bits"][0]), vec3(&local["bounds_bits"][1])];
        let start = vec3(&local["start_bits"]); let end = vec3(&local["end_bits"]);
        let point = vec3(&local["point_bits"]);
        assert_eq!(bounds, b.component_bounds()[0]);
        let part = &b.components[0];
        let mesh = Mesh::new(part.vertices.clone(),part.triangles.clone(),b.geometry_revision(),"perf02-offline-wire-model").unwrap();
        let raw_start = std::array::from_fn(|i| start[i] - 0.01_f32 * (end[i] - start[i]));
        let raw_end = std::array::from_fn(|i| end[i] + 0.01_f32 * (end[i] - start[i]));
        let raw_hits = super::super::collision::query(&mesh,raw_start,raw_end).unwrap();
        assert_eq!(raw_hits.first().map(|hit|hit.triangle_id),Some(93));
        assert_eq!(local["hits"]["rows"][0]["triangle_id"],93);
        // Outcome is an arbitrary presentation label: the saved event has no
        // resolved damage. It does not imply penetration or publish damage.
        let packed = packed_segment(1,bounds,start,end,ShotOutcome::Pierced).unwrap();
        assert_eq!(packed,[3,1,31,127,255,45,116,0]);
        println!("PERF02_WIRE_MODEL packed={packed:?} outcome_label=arbitrary_pierced authoritative_triangle=93");
        for model in ["f32", "f64_then_f32"] {
            // Model formula: lo + (hi - lo) * byte / 255. The query API
            // accepts f32 facts; f64_then_f32 narrows decoded coords before
            // extension and narrows extension results before querying.
            let decoded = |offset:usize| -> [f32;3] {
                std::array::from_fn(|i| if model == "f32" {
                    bounds[0][i] + (bounds[1][i]-bounds[0][i]) * f32::from(packed[offset+i]) / 255.0_f32
                } else {
                    (f64::from(bounds[0][i]) + (f64::from(bounds[1][i])-f64::from(bounds[0][i]))
                        * f64::from(packed[offset+i]) / 255.0_f64) as f32
                })
            };
            let ds = decoded(2); let de = decoded(5);
            let ext = |axis:usize,at_end:bool| -> f32 {
                if model == "f32" {
                    if at_end { de[axis] + 0.01_f32*(de[axis]-ds[axis]) }
                    else { ds[axis] - 0.01_f32*(de[axis]-ds[axis]) }
                } else {
                    let (s,e)=(f64::from(ds[axis]),f64::from(de[axis]));
                    (if at_end {e+0.01_f64*(e-s)} else {s-0.01_f64*(e-s)}) as f32
                }
            };
            let qs = std::array::from_fn(|i|ext(i,false));
            let qe = std::array::from_fn(|i|ext(i,true));
            let hits = super::super::collision::query(&mesh,qs,qe).unwrap();
            let first = hits.first();
            let hit_point = first.map(|h| std::array::from_fn::<_,3,_>(|i|qs[i]+h.t*(qe[i]-qs[i])));
            let displacement = hit_point.map(|p|std::array::from_fn::<_,3,_>(|i|f64::from(p[i])-f64::from(point[i])));
            let first = first.expect("model ray must intersect the retained component");
            assert_eq!((first.triangle_id,&first.mesh,&first.group,&first.material),
                (contact.triangle.triangle_id,&contact.triangle.mesh,&contact.triangle.group,&contact.triangle.material));
            let drift = displacement.expect("model hit must have a point");
            assert!((0.07..0.09).contains(&drift[2].abs()), "observed z drift in {model}: {drift:?}");
            println!("PERF02_WIRE_MODEL arithmetic={model} decode=lo+(hi-lo)*byte/255 extension=1pct decoded_start={ds:?} decoded_end={de:?} first={:?} identity_matches={} displacement_xyz_m={displacement:?}",
                Some((&first.triangle_id,&first.mesh,&first.group,&first.material)),
                (first.triangle_id,&first.mesh,&first.group,&first.material) == (contact.triangle.triangle_id,&contact.triangle.mesh,&contact.triangle.group,&contact.triangle.material));
        }
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
    // Synthetic only: reuse the pinned material catalogue, not its shape.
    // Other components are moved far away so the complete posed world mesh
    // cannot accidentally supply an earlier hit to these small segments.
    fn perf02_surface_fixture(vertices: Vec<[f32; 3]>, triangles: Vec<Triangle>) -> Bundle {
        let mut b = bundle();
        b.hull = [0.; 3]; b.turret = [0.; 3]; b.gun = [0.; 3];
        for component in &mut b.components[1..] {
            for vertex in &mut component.vertices { vertex[0] += 20.; }
        }
        b.components[0] = Component { vertices, triangles };
        b.bounds[0] = [[-1.; 3], [1.; 3]];
        b
    }
    fn perf02_surface_triangle(id: u32, a: u32, b: u32, c: u32, material: &str) -> Triangle {
        Triangle { triangle_id:id, a, b, c, mesh:"Hull".into(),
            group:format!("synthetic-group-{id}"), material:material.into() }
    }
    fn perf02_surface_contacts(b: &Bundle) -> Vec<Contact> {
        let start = [-0.5, 0., 0.]; let end = [0.5, 0., 0.];
        let position = [0.; 3]; let direction = [0.; 3]; let aim = [0.; 2];
        let mesh = b.mesh_for_pose(position, direction, aim, 1, 1000).unwrap();
        super::super::collision::query(&mesh, start, end).unwrap().into_iter().map(|triangle| {
            let endpoint = std::array::from_fn(|i| start[i] + triangle.t * (end[i] - start[i]));
            let material_facts = b.materials.lookup(&triangle.mesh, &triangle.material).unwrap();
            Contact { shot:1, target_slot:1, tick:1000, segment_start:start, segment_end:end,
                segment_seconds:0.1, endpoint, target_position:position, target_direction:direction,
                target_aim:aim, triangle, geometry_revision:b.geometry_revision().into(),
                transform_revision:mesh.transform_revision().into(), material_facts }
        }).collect()
    }
    fn perf02_identity(hit: &super::super::collision::Candidate) -> (u32, &str, &str, &str) {
        (hit.triangle_id, &hit.mesh, &hit.group, &hit.material)
    }
    #[test] fn perf02_reanchor_rejects_unverified_world_first_and_large_shift() {
        let b=perf02_surface_fixture(vec![[0.,-0.5,-0.5],[0.,0.5,-0.5],[0.,0.,0.5],
            [0.0001,-0.5,-0.5],[0.0001,0.5,-0.5],[0.0001,0.,0.5]],
            vec![perf02_surface_triangle(0,0,1,2,"armor_4"),perf02_surface_triangle(1,3,4,5,"armor_7")]);
        let contacts=perf02_surface_contacts(&b);assert_eq!(contacts.len(),2);
        let first=&contacts[0];let second=&contacts[1];
        let point=b.inverse_component_point(0,pose::inverse_rotate(subtract(first.endpoint,first.target_position),first.target_direction),first.target_aim);
        assert!(b.impact_source_anchor(first,0,point).unwrap().is_some());
        assert!(b.impact_source_anchor(second,0,second.endpoint).unwrap().is_none());
        let mut forged=first.clone();forged.triangle.normal[0]=-forged.triangle.normal[0];
        assert!(b.impact_source_anchor(&forged,0,point).unwrap().is_none());
        let mut forged=first.clone();forged.endpoint[0]+=0.00001;
        assert!(b.impact_source_anchor(&forged,0,point).unwrap().is_none());
        let mut forged=first.clone();forged.triangle.t=0.75;forged.endpoint=[0.25,0.,0.];
        assert!(b.impact_source_anchor(&forged,0,point).unwrap().is_none());
        let mut too_far=point;too_far[0]+=0.001;
        assert!(b.impact_source_anchor(first,0,too_far).unwrap().is_none());
    }
    #[test] fn perf02_reanchor_rejects_shared_edge_and_packed_equal_t() {
        let b=perf02_surface_fixture(vec![[0.,-0.5,-0.5],[0.,0.5,-0.5],[0.,-0.5,0.5],[0.,0.5,0.5]],
            vec![perf02_surface_triangle(0,0,1,2,"armor_4"),perf02_surface_triangle(1,1,3,2,"armor_7")]);
        let contacts=perf02_surface_contacts(&b);assert_eq!(contacts.len(),2);
        assert!(b.impact_source_anchor(&contacts[0],0,contacts[0].endpoint).unwrap().is_none(),"edge barycentrics are ambiguous");
        let b=perf02_surface_fixture(vec![[0.,-0.5,-0.5],[0.,0.5,-0.5],[0.,0.,0.5]],
            vec![perf02_surface_triangle(0,0,1,2,"armor_4"),perf02_surface_triangle(1,0,1,2,"armor_7")]);
        let part=&b.components[0];let mesh=Mesh::new(part.vertices.clone(),part.triangles.clone(),b.geometry_revision(),"perf02-packed-tie").unwrap();
        let contacts=perf02_surface_contacts(&b);assert_eq!(contacts.len(),2);
        assert_eq!(contacts[0].triangle.t.to_bits(),contacts[1].triangle.t.to_bits());
        assert!(!b.impact_packed_first_matches(materials::Component::Hull,b.component_bounds()[0],[-1.,0.,0.],[1.,0.,0.],&mesh,&contacts[0].triangle).unwrap(),
            "packed equal-t surfaces are ambiguous and must be refused");
    }
    #[test] fn perf02_reanchor_rejects_packed_different_first_with_distinct_t() {
        use super::super::impact_wire::{packed_segment,ShotOutcome};
        let b=perf02_surface_fixture(vec![[0.,-0.5,-0.5],[0.,0.5,-0.5],[0.,0.,0.5],
            [0.0001,-0.5,-0.5],[0.0001,0.5,-0.5],[0.0001,0.,0.5]],
            vec![perf02_surface_triangle(0,0,1,2,"armor_4"),perf02_surface_triangle(1,3,4,5,"armor_7")]);
        let part=&b.components[0];let mesh=Mesh::new(part.vertices.clone(),part.triangles.clone(),b.geometry_revision(),"perf02-packed-distinct").unwrap();
        let contacts=perf02_surface_contacts(&b);assert_eq!(contacts.len(),2);
        let bounds=b.component_bounds()[0];let (start,end)=([-1.,0.,0.],[1.,0.,0.]);
        let bytes=packed_segment(1,bounds,start,end,ShotOutcome::Pierced).unwrap();
        let decode=|offset:usize|std::array::from_fn::<_,3,_>(|i|bounds[0][i]
            +(bounds[1][i]-bounds[0][i])*f32::from(bytes[offset+i])/255.0_f32);
        let s=decode(2);let e=decode(5);
        let qs=std::array::from_fn(|i|s[i]-0.01_f32*(e[i]-s[i]));
        let qe=std::array::from_fn(|i|e[i]+0.01_f32*(e[i]-s[i]));
        let hits=super::super::collision::query(&mesh,qs,qe).unwrap();
        assert_eq!(hits.len(),2);assert_eq!(hits[0].triangle_id,0);assert_eq!(hits[1].triangle_id,1);
        assert_ne!(hits[0].t.to_bits(),hits[1].t.to_bits(),"distinct surfaces must not rely on tie rejection");
        assert!(!b.impact_packed_first_matches(materials::Component::Hull,bounds,start,end,&mesh,&contacts[1].triangle).unwrap(),
            "a different packed first surface must be refused even when t differs");
    }
    #[test] fn perf02_reanchor_interval_refuses_uncertified_edges_and_parallel_lines() {
        let triangle=[[0.,0.,0.],[0.,1.,0.],[0.,0.,1.]];
        assert!(impact_interior_certified(triangle,[-1.,0.25,0.25],[1.,0.25,0.25]).is_some());
        assert!(impact_interior_certified(triangle,[-1.,0.,0.25],[1.,0.,0.25]).is_none(),"shared edge is not strictly interior");
        assert!(impact_interior_certified(triangle,[0.,0.25,0.25],[0.,0.5,0.25]).is_none(),"parallel determinant is ambiguous");
        assert!(impact_interior_certified(triangle,[-1.,f64::NAN,0.25],[1.,0.25,0.25]).is_none());
        let b=perf02_surface_fixture(vec![[0.,-0.5,-0.5],[0.,0.5,-0.5],[0.,0.,0.5]],
            vec![perf02_surface_triangle(0,0,1,2,"armor_4")]);
        let mut near_parallel=perf02_surface_contacts(&b).remove(0);
        near_parallel.segment_start=[-1e-20,0.,-0.25];near_parallel.segment_end=[1e-20,0.,0.25];
        // The authoritative world query enforces collision's existing
        // relative angular threshold before any interval proof is trusted.
        assert!(b.impact_source_anchor(&near_parallel,0,[0.;3]).unwrap().is_none());
    }
    #[test] fn perf02_reanchor_interval_bounds_the_entire_local_anchor() {
        let local=[[0.,0.,0.],[0.,1.,0.],[0.,0.,1.]];
        let u=ImpactInterval{lo:0.24999,hi:0.25001};let v=ImpactInterval{lo:0.25,hi:0.25};
        assert!(impact_anchor_certified(local,[0.,0.25,0.25],u,v,[0.,0.25,0.25]));
        let too_wide=ImpactInterval{lo:0.249,hi:0.251};
        assert!(!impact_anchor_certified(local,[0.,0.25,0.25],too_wide,v,[0.,0.25,0.25]),
            "a central anchor in range cannot hide an uncertified endpoint");
        assert!(!impact_anchor_certified(local,[0.,0.25,0.25],u,v,[0.,0.2501,0.25]),
            "the selected anchor must also belong to the enclosure");
        assert!(!impact_anchor_certified(local,[0.,f32::NAN,0.25],u,v,[0.,0.25,0.25]));
    }
    #[test] fn perf02_impact_synthetic_nonfirst_near_surface_currently_accepted() {
        // The second plane is 0.1 mm behind the first. It has a different ID,
        // group and armor. Its contact is well-formed but is NOT the world
        // query's first hit. This test records an existing unsafe success; it
        // is evidence of the defect, not a security acceptance test.
        let b = perf02_surface_fixture(vec![[0.,-0.5,-0.5],[0.,0.5,-0.5],[0.,0.,0.5],
            [0.0001,-0.5,-0.5],[0.0001,0.5,-0.5],[0.0001,0.,0.5]],
            vec![perf02_surface_triangle(0,0,1,2,"armor_4"),
                 perf02_surface_triangle(1,3,4,5,"armor_7")]);
        let contacts = perf02_surface_contacts(&b);
        assert_eq!(contacts.len(),2);
        assert_eq!((contacts[0].triangle.triangle_id,contacts[1].triangle.triangle_id),(0,1));
        assert_ne!(contacts[0].triangle.material, contacts[1].triangle.material);
        let original = b.impact_segment(&contacts[0]).unwrap();
        assert_eq!(perf02_identity(&native_decoder_first(&b,&original)), perf02_identity(&contacts[0].triangle));
        assert!(b.proxy_ray(&contacts[1]).is_err(),"world query rejects non-first contact");
        let false_success = b.impact_segment(&contacts[1]).expect("documented current defect: neighboring surface is accepted");
        let actual_first = native_decoder_first(&b,&false_success);
        assert_eq!(perf02_identity(&actual_first),perf02_identity(&contacts[0].triangle));
        assert_ne!(perf02_identity(&actual_first),perf02_identity(&contacts[1].triangle));
    }
    #[test] fn perf02_impact_synthetic_nonfirst_equal_t_currently_accepted() {
        // Both triangles meet at the same point; equal-t ordering in this
        // server query is deterministic, but native-client tie order is not
        // established. A matching point alone cannot prove surface identity.
        let b = perf02_surface_fixture(vec![[0.,-0.5,-0.5],[0.,0.5,-0.5],
            [0.,-0.5,0.5],[0.,0.5,0.5]],
            vec![perf02_surface_triangle(0,0,1,2,"armor_4"),
                 perf02_surface_triangle(1,1,3,2,"armor_7")]);
        let contacts = perf02_surface_contacts(&b);
        assert_eq!(contacts.len(),2);
        assert_eq!((contacts[0].triangle.triangle_id,contacts[1].triangle.triangle_id),(0,1));
        assert_eq!(contacts[0].triangle.t.to_bits(), contacts[1].triangle.t.to_bits());
        assert_eq!(contacts[0].endpoint,contacts[1].endpoint);
        let segment = b.impact_segment(&contacts[0]).unwrap();
        assert_eq!(perf02_identity(&native_decoder_first(&b,&segment)),perf02_identity(&contacts[0].triangle));
        assert!(b.proxy_ray(&contacts[1]).is_err());
        let false_success = b.impact_segment(&contacts[1]).expect("documented current defect: edge neighbor is accepted");
        assert_ne!(perf02_identity(&native_decoder_first(&b,&false_success)),perf02_identity(&contacts[1].triangle));
    }
    #[test] fn perf02_impact_rejects_distant_forged_t_and_endpoint() {
        let b = perf02_surface_fixture(vec![[0.,-0.5,-0.5],[0.,0.5,-0.5],[0.,0.,0.5]],
            vec![perf02_surface_triangle(0,0,1,2,"armor_4")]);
        let mut contact = perf02_surface_contacts(&b).remove(0);
        assert!(b.impact_segment(&contact).is_ok());
        contact.triangle.t = 0.75;
        contact.endpoint = [0.25,0.,0.]; // matches the forged t but misses the plane
        assert!(b.impact_segment(&contact).is_err());
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
    /// First surface the native decoder selects after its 1% extension at both ends.
    fn native_decoder_first(b: &Bundle, segment: &ImpactSegment) -> super::super::collision::Candidate {
        let index = match segment.component { materials::Component::Hull => 0,
            materials::Component::Turret01 => 1, materials::Component::Gun02 | materials::Component::Gun01 => 2 };
        let part = &b.components[index];
        let mesh = Mesh::new(part.vertices.clone(), part.triangles.clone(), b.geometry_revision(), "native-decoder-extension").unwrap();
        let (s, e) = (segment.start, segment.end);
        let extended_start = std::array::from_fn(|i| s[i] - 0.01 * (e[i] - s[i]));
        let extended_end = std::array::from_fn(|i| e[i] + 0.01 * (e[i] - s[i]));
        super::super::collision::query(&mesh, extended_start, extended_end).unwrap().remove(0)
    }
    #[test] fn impact_start_just_past_entry_surface_keeps_contact_as_native_first_surface() {
        // A muzzle already inside the target component: the native 1% backward
        // extension would reach the entry surface behind the projectile start.
        for (b, y, z) in [(bundle(), -0.25, 0.15), (is7_bundle(), 0., 0.)] {
            let part = &b.components[0];
            let mesh = Mesh::new(part.vertices.clone(), part.triangles.clone(), b.geometry_revision(), "entry-probe").unwrap();
            let entry = super::super::collision::query(&mesh, [-4., y, z], [4., y, z]).unwrap().remove(0);
            let entry_x = -4. + 8. * entry.t;
            for (direction, aim) in [([0.; 3], [0.; 2]), ([0.7, -0.3, 0.2], [1.1, -0.09])] {
                let contact = contact_for(&b, 0, [entry_x + 0.004, y, z], [4., y, z], direction, aim);
                assert_ne!(contact.triangle.triangle_id, entry.triangle_id);
                let segment = b.impact_segment(&contact).unwrap();
                assert_eq!(native_decoder_first(&b, &segment).triangle_id, contact.triangle.triangle_id);
                for axis in 0..3 { for edge in [segment.start, segment.end] {
                    assert!(edge[axis] >= segment.bounds[0][axis] - 1e-6 && edge[axis] <= segment.bounds[1][axis] + 1e-6);
                } }
            }
        }
    }
    #[test] fn impact_owner_point_blank_ms1_under_is7_20261019_keeps_battle_alive() {
        // Values from local/evidence/20261019-full-polygon-ramfix01/gateway-restart02.stdout.log:
        // battle 4438936055444238071 failed with "impact segment first surface
        // differs from contact" after MS-1 shot 2 from under the IS-7.
        let b = is7_bundle();
        let mut target = actor_for(VehicleKind::Is7);
        target.position = [38.712982177734375, 5.927037239074707, 461.0643615722656];
        target.direction = [-1.8954676389694214, 0.012824684381484985, 0.13134384155273438];
        target.aim.yaw = 2.97872; target.aim.pitch = 0.017453292;
        let origin = [38.204372, 6.614436, 461.4934];
        let end = super::super::projectile::position_at(origin, [323.96603, 140.58948, -17.708313], 6.2784004, 0.1);
        let mesh = b.world_mesh(&target, 1, 4129).unwrap();
        let nearest = super::super::collision::query(&mesh, origin, end).unwrap().remove(0);
        let endpoint = std::array::from_fn(|i| origin[i] + nearest.t * (end[i] - origin[i]));
        let material_facts = b.materials.lookup(&nearest.mesh, &nearest.material).unwrap();
        let contact = Contact { shot: 2, target_slot: 1, tick: 4129, segment_start: origin, segment_end: end,
            segment_seconds: 0.1, endpoint, target_position: target.position, target_direction: target.direction,
            target_aim: [target.aim.yaw, target.aim.pitch], triangle: nearest,
            geometry_revision: b.geometry_revision().into(), transform_revision: mesh.transform_revision().into(), material_facts };
        let segment = b.impact_segment(&contact).unwrap();
        assert_eq!(native_decoder_first(&b, &segment).triangle_id, contact.triangle.triangle_id);
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
    /// Conservative test-only experiment: never adds successes to the existing
    /// impact path. The world query uses the original authoritative segment;
    /// the local query models the existing unquantized 1% extension. Neither
    /// the native decoder's tie order nor the packed-byte ray is verified here.
    fn perf02_strict_impact_model(b:&Bundle,c:&Contact)->io::Result<ImpactSegment> {
        let world=b.mesh_for_pose(c.target_position,c.target_direction,c.target_aim,c.target_slot,c.tick)?;
        let expected=super::super::collision::query(&world,c.segment_start,c.segment_end)?
            .into_iter().next().ok_or_else(||bad())?;
        let expected_endpoint: [f32;3]=std::array::from_fn(|i|c.segment_start[i]
            + expected.t * (c.segment_end[i]-c.segment_start[i]));
        if expected!=c.triangle || expected.t.to_bits()!=c.triangle.t.to_bits()
            || expected.normal.map(f32::to_bits)!=c.triangle.normal.map(f32::to_bits)
            || expected_endpoint.map(f32::to_bits)!=c.endpoint.map(f32::to_bits) {return Err(bad());}
        let segment=b.impact_segment(c)?;
        let index=match segment.component { materials::Component::Hull=>0,
            materials::Component::Turret01=>1,materials::Component::Gun02|materials::Component::Gun01=>2 };
        let local_point=b.inverse_component_point(index,
            pose::inverse_rotate(subtract(c.endpoint,c.target_position),c.target_direction),c.target_aim);
        let s=segment.start;let e=segment.end;
        let qs=std::array::from_fn(|i|s[i]-0.01_f32*(e[i]-s[i]));
        let qe=std::array::from_fn(|i|e[i]+0.01_f32*(e[i]-s[i]));
        let part=&b.components[index];
        let mesh=Mesh::new(part.vertices.clone(),part.triangles.clone(),b.geometry_revision(),"perf02-strict-impact-model")?;
        let hit=super::super::collision::query(&mesh,qs,qe)?.into_iter().next().ok_or_else(||bad())?;
        if perf02_identity(&hit)!=perf02_identity(&c.triangle)
            || (0..3).any(|i|(f64::from(qs[i]+hit.t*(qe[i]-qs[i]))-f64::from(local_point[i])).abs()>CONTACT_TOLERANCE) {
            return Err(bad());
        }
        Ok(segment)
    }
    fn perf02_world_first_for_ray(b:&Bundle,start:[f32;3],end:[f32;3])->Contact {
        let pos=[0.;3];let dir=[0.;3];let aim=[0.;2];
        let mesh=b.mesh_for_pose(pos,dir,aim,1,1000).unwrap();
        let triangle=super::super::collision::query(&mesh,start,end).unwrap().remove(0);
        let endpoint=std::array::from_fn(|i|start[i]+triangle.t*(end[i]-start[i]));
        let material_facts=b.materials.lookup(&triangle.mesh,&triangle.material).unwrap();
        Contact {shot:1,target_slot:1,tick:1000,segment_start:start,segment_end:end,segment_seconds:0.1,
            endpoint,target_position:pos,target_direction:dir,target_aim:aim,triangle,
            geometry_revision:b.geometry_revision().into(),transform_revision:mesh.transform_revision().into(),material_facts}
    }
    #[test] fn perf02_strict_model_rejects_nonfirst_neighbors_and_equal_t() {
        let cases=[
            (vec![[0.,-0.5,-0.5],[0.,0.5,-0.5],[0.,0.,0.5],
                [0.0001,-0.5,-0.5],[0.0001,0.5,-0.5],[0.0001,0.,0.5]],
             vec![perf02_surface_triangle(0,0,1,2,"armor_4"),perf02_surface_triangle(1,3,4,5,"armor_7")]),
            (vec![[0.,-0.5,-0.5],[0.,0.5,-0.5],[0.,-0.5,0.5],[0.,0.5,0.5]],
             vec![perf02_surface_triangle(0,0,1,2,"armor_4"),perf02_surface_triangle(1,1,3,2,"armor_7")])];
        for (vertices,triangles) in cases {
            let b=perf02_surface_fixture(vertices,triangles);let contacts=perf02_surface_contacts(&b);
            assert_eq!(contacts.len(),2);
            assert!(perf02_strict_impact_model(&b,&contacts[0]).is_ok());
            assert!(b.impact_segment(&contacts[1]).is_ok(),"current behavior must remain unchanged");
            assert!(perf02_strict_impact_model(&b,&contacts[1]).is_err(),"non-first world candidate must fail");
            let mut tampered=contacts[0].clone();tampered.triangle.normal[0]=-tampered.triangle.normal[0];
            assert!(perf02_strict_impact_model(&b,&tampered).is_err());
            let mut tampered=contacts[0].clone();tampered.endpoint[0]+=0.00001;
            assert!(perf02_strict_impact_model(&b,&tampered).is_err());
        }
    }
    #[test] fn perf02_strict_model_preserves_point_blank_shift_in_fixture() {
        let b=perf02_surface_fixture(vec![[0.,-0.5,-0.5],[0.,0.5,-0.5],[0.,0.,0.5],
            [0.02,-0.5,-0.5],[0.02,0.5,-0.5],[0.02,0.,0.5]],
            vec![perf02_surface_triangle(0,0,1,2,"armor_4"),perf02_surface_triangle(1,3,4,5,"armor_7")]);
        let contact=perf02_world_first_for_ray(&b,[0.005,0.,0.],[0.8,0.,0.]);
        assert_eq!(contact.triangle.triangle_id,1);
        let delta=subtract(contact.segment_end,contact.segment_start);
        let len=delta.iter().map(|&v|f64::from(v).powi(2)).sum::<f64>().sqrt();
        let (initial_start,initial_end)=clipped_line(contact.endpoint,delta,b.bounds[0],
            Some(-f64::from(contact.triangle.t)*len)).unwrap();
        let before=ImpactSegment{component:materials::Component::Hull,bounds:b.bounds[0],start:initial_start,end:initial_end};
        assert_eq!(native_decoder_first(&b,&before).triangle_id,0,"initial extended model sees the earlier surface");
        let segment=perf02_strict_impact_model(&b,&contact).unwrap();
        assert!(segment.start[0]>contact.segment_start[0],"the model must really exercise the forward shift");
        assert_eq!(perf02_identity(&native_decoder_first(&b,&segment)),perf02_identity(&contact.triangle));
    }
    /// Fixed grid, not a random sample of battles: every accepted Contact is
    /// the first candidate of a world query, including edge/boundary rays.
    /// The counters quantify this corpus only, not all valid input or native
    /// tie ordering. Strict is a filter, so it cannot accept a current failure.
    #[test] fn perf02_strict_model_differential_pinned_world_first_grid() {
        let poses=[([0.;3],[0.;3],[0.;2]),([37.,21.,-105.],[0.7,-0.3,0.2],[1.1,-0.09]),
            ([175.,21.,-395.],[-2.1,0.25,-0.15],[-0.9,0.24])];
        let mut global_pass=0usize;let mut global_model_pass=0usize;
        for b in [bundle(),is7_bundle()] {
            let mut rays=0usize;let mut no_hit=0usize;let mut query_error=0usize;
            let mut current_fail=0usize;let mut both_pass=0usize;let mut rejected=0usize;
            let mut reported=0usize;
            for (position,direction,aim) in poses {
                let mesh=b.mesh_for_pose(position,direction,aim,1,1000).expect("fixed pose world mesh");
                for component_index in 0..3 {for axis in [0usize,2] {
                    let other=if axis==0 {[1usize,2]} else {[0usize,1]};
                    let bounds=b.component_bounds()[component_index];
                    for u in [0.0_f32,0.5,1.0] {for v in [0.0_f32,0.5,1.0] {for reverse in [false,true] {
                        let mut a=[0_f32;3];let mut z=[0_f32;3];
                        for (i,fraction) in [(other[0],u),(other[1],v)] {
                            a[i]=bounds[0][i]+fraction*(bounds[1][i]-bounds[0][i]);z[i]=a[i];
                        }
                        a[axis]=bounds[0][axis]-0.5;z[axis]=bounds[1][axis]+0.5;
                        if reverse {std::mem::swap(&mut a,&mut z);}
                        let to_world=|p|{
                            let local=b.component_point(component_index,p,aim[0],aim[1]);
                            let rotated=pose::rotate(local,direction);
                            std::array::from_fn(|i|position[i]+rotated[i])
                        };
                        let start=to_world(a);let end=to_world(z);rays+=1;
                        let first=match super::super::collision::query(&mesh,start,end) {
                            Ok(hits)=>match hits.into_iter().next() {Some(hit)=>hit,None=>{no_hit+=1;continue}},
                            Err(error)=>{query_error+=1;println!("PERF02_STRICT_GRID_QUERY_ERROR vehicle={} error={error}",b.vehicle_kind().label());continue}
                        };
                        let endpoint=std::array::from_fn(|i|start[i]+first.t*(end[i]-start[i]));
                        let material_facts=b.materials.lookup(&first.mesh,&first.material).unwrap();
                        let c=Contact {shot:1,target_slot:1,tick:1000,segment_start:start,segment_end:end,
                            segment_seconds:0.1,endpoint,target_position:position,target_direction:direction,
                            target_aim:aim,triangle:first,geometry_revision:b.geometry_revision().into(),
                            transform_revision:mesh.transform_revision().into(),material_facts};
                        let old=b.impact_segment(&c);let strict=perf02_strict_impact_model(&b,&c);
                        match (old,strict) {
                            (Ok(_),Ok(_))=>both_pass+=1,
                            (Err(_),Err(_))=>current_fail+=1,
                            (Ok(segment),Err(error))=>{
                                rejected+=1;
                                if reported<8 {
                                    println!("PERF02_STRICT_GRID_REJECT vehicle={} component={component_index} axis={axis} grid=({u},{v}) reverse={reverse} position={position:?} direction={direction:?} aim={aim:?} triangle={} material={} error={error}",
                                        b.vehicle_kind().label(),c.triangle.triangle_id,c.triangle.material);
                                    let index=match segment.component { materials::Component::Hull=>0,
                                        materials::Component::Turret01=>1, materials::Component::Gun02|materials::Component::Gun01=>2 };
                                    let local_point=b.inverse_component_point(index,
                                        pose::inverse_rotate(subtract(c.endpoint,c.target_position),c.target_direction),c.target_aim);
                                    let s=segment.start;let e=segment.end;
                                    let qs=std::array::from_fn(|i|s[i]-0.01_f32*(e[i]-s[i]));
                                    let qe=std::array::from_fn(|i|e[i]+0.01_f32*(e[i]-s[i]));
                                    let part=&b.components[index];
                                    let local_mesh=Mesh::new(part.vertices.clone(),part.triangles.clone(),b.geometry_revision(),"perf02-strict-grid-diagnostic").unwrap();
                                    let local_hits=super::super::collision::query(&local_mesh,qs,qe).unwrap();
                                    let world_hits=super::super::collision::query(&mesh,start,end).unwrap();
                                    let target_index=local_hits.iter().position(|hit|perf02_identity(hit)==perf02_identity(&c.triangle));
                                    println!("PERF02_STRICT_GRID_DETAILS local_point={local_point:?} local_qs={qs:?} local_qe={qe:?} local_hits={} expected_identity={:?} expected_t_f32={} local_expected_index={target_index:?} world_hits={} candidate_t_is_f32_not_ordering_f64",
                                        local_hits.len(),perf02_identity(&c.triangle),c.triangle.t,world_hits.len());
                                    for (which,hits) in [("world",&world_hits),("local",&local_hits)] {
                                        for (candidate_index,hit) in hits.iter().take(8).enumerate() {
                                            let displacement=if which=="local" {Some(std::array::from_fn::<_,3,_>(|i|
                                                f64::from(qs[i]+hit.t*(qe[i]-qs[i]))-f64::from(local_point[i])))} else {None};
                                            let same_f32_t_as_first=hit.t.to_bits()==hits[0].t.to_bits();
                                            println!("PERF02_STRICT_GRID_HIT space={which} index={candidate_index} identity={:?} t_f32={} t_bits={} same_f32_t_as_first={same_f32_t_as_first} displacement_xyz_m={displacement:?}",
                                                perf02_identity(hit),hit.t,hit.t.to_bits());
                                        }
                                    }
                                    if let Some(i)=target_index.filter(|&i|i>=8) {
                                        let hit=&local_hits[i];
                                        let displacement=std::array::from_fn::<_,3,_>(|axis|
                                            f64::from(qs[axis]+hit.t*(qe[axis]-qs[axis]))-f64::from(local_point[axis]));
                                        println!("PERF02_STRICT_GRID_TARGET index={i} identity={:?} t_f32={} t_bits={} displacement_xyz_m={displacement:?}",perf02_identity(hit),hit.t,hit.t.to_bits());
                                    }
                                    reported+=1;
                                }
                            },
                            (Err(error),Ok(_))=>panic!("strict model accepted an existing failure: {error}"),
                        }
                    }}}
                }}
            }
            assert_eq!(rays,324);assert!(both_pass+rejected>10,"insufficient current successes for {}",b.vehicle_kind().label());
            assert!(both_pass>0,"no strict successes for {}",b.vehicle_kind().label());
            println!("PERF02_STRICT_GRID vehicle={} rays={rays} no_hit={no_hit} query_error={query_error} current_fail={current_fail} both_pass={both_pass} current_pass_strict_reject={rejected} sample_cap=8",b.vehicle_kind().label());
            assert_eq!(rays,no_hit+query_error+current_fail+both_pass+rejected);
            global_pass+=both_pass+rejected;global_model_pass+=both_pass;
        }
        assert!(global_pass>20 && global_model_pass>0);
    }
    #[test] #[ignore] fn perf02_strict_model_retained_receipt_reanchors() {
        let receipt=std::env::var("PERF02_IMPACT_RECEIPT").expect("PERF02_IMPACT_RECEIPT");
        let root=std::env::var("PERF02_IMPACT_LOCAL_ROOT").expect("PERF02_IMPACT_LOCAL_ROOT");
        let path=std::env::var("PERF02_IMPACT_BUNDLE").expect("PERF02_IMPACT_BUNDLE");
        let receipt=Path::new(&receipt);assert!(receipt.is_absolute());non_reparse(receipt).unwrap();
        let mut raw=Vec::new();fs::File::open(receipt).unwrap().take((IMPACT_DIAGNOSTIC_MAX_BYTES+1)as u64).read_to_end(&mut raw).unwrap();
        assert!(raw.len()<=IMPACT_DIAGNOSTIC_MAX_BYTES);
        assert_eq!(format!("{:x}",Sha256::digest(&raw)),"973bddd51c407ed10d99350b5753e2fef746c93ee87d1c6a809ae8ecb6ab7763");
        let b=Bundle::load(Path::new(&root),Path::new(&path)).unwrap();
        assert_eq!(b.bundle_sha256(),"25b6c69fd51e26abbda9b16c35572b5f289f2320d0dffe4085dea1b7bdeba1bb");
        let c=decode_impact_diagnostic(&raw,&b).unwrap();
        let segment=perf02_strict_impact_model(&b,&c).expect("retained first surface must survive bounded reanchor");
        assert!(same_surface(&native_decoder_first(&b,&segment),&c.triangle));
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
