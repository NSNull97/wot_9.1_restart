//! Bounded reader and segment query for project-calibrated Malinovka bushes.
//!
//! This is not an original-server law and is not wired into spotting. Source
//! transforms come from #717; the ellipsoids and coefficients are explicitly
//! project calibration. Each query reports individual intersections only:
//! stacking, firing, destruction, and line-of-sight policy remain undecided.
use std::{collections::{BTreeMap, BTreeSet}, fs::File, io::{self, Read}, path::Path};
use serde::de::{Deserialize, Deserializer, Error as _, MapAccess, SeqAccess, Visitor};
use serde_json::Value;
use sha2::{Digest, Sha256};

const MAX_BYTES: u64 = 2 * 1024 * 1024;
// Maximum 6 actors, 2*7 rays per pair and 1024 volumes: at most 430,080
// broad-phase volume checks per scan. Runtime latency is platform-dependent.
const MAX_INSTANCES: usize = 1024;
const MAX_COORD: f64 = 10_000.;
const MAX_EXTENT: f64 = 1000.;
const MIN_DETERMINANT: f64 = 1e-8;
const SCHEMA: &str = "content0-s5a-malinovka-bush-volumes.v1";
const CAL_SCHEMA: &str = "content0-s5a-malinovka-bush-calibration.v1";
const MAP_SHA: &str = "bcefe13bd0a82916292075c976210770fea2d7e2cef81ec2fdaea9b427b197a0";
const SHARED_SHA: &str = "11b3dd86eef85eb2128c78ec993d259b3f5c1fb187b0ce061f79088b68350025";
const RESOURCES: [(&str, u64, &str); 3] = [
    ("speedtree/02_Malinovka/Bush.spt", 13477, "a88d6635fd6ce65c7b4ae01fbd98ccb5695df3cde4d03fe1140879595a6f4118"),
    ("speedtree/02_Malinovka/Shrub_1.spt", 13410, "02c12d819d3b4409f1056563e190b235cf7ff71308f67dd75dfb55c44316d60a"),
    ("speedtree/02_Malinovka/Shrub_2.spt", 13420, "c304486045179ace4810918dc4352a9a96c9ebb6114ac7da29352dae65c0c92e"),
];
type Point = [f64; 3];

fn bad(message: &'static str) -> io::Error { io::Error::new(io::ErrorKind::InvalidData, message) }
fn sha(s: &str) -> bool { s.len()==64 && s.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) }
fn fields(v: &Value, names: &[&str]) -> io::Result<()> {
    let obj=v.as_object().ok_or_else(||bad("foliage expected object"))?;
    if obj.len()!=names.len() || names.iter().any(|n|!obj.contains_key(*n)) {return Err(bad("foliage unexpected fields"));} Ok(())
}
fn text<'a>(v: &'a Value, max: usize) -> io::Result<&'a str> {
    v.as_str().filter(|s|!s.is_empty() && s.len()<=max).ok_or_else(||bad("foliage text bound"))
}
fn number(v: &Value, min: f64, max: f64) -> io::Result<f64> {
    v.as_f64().filter(|x|x.is_finite() && *x>=min && *x<=max).ok_or_else(||bad("foliage number bound"))
}
fn point(v: &Value, min: f64, max: f64) -> io::Result<Point> {
    let a=v.as_array().filter(|a|a.len()==3).ok_or_else(||bad("foliage point"))?;
    Ok([number(&a[0],min,max)?,number(&a[1],min,max)?,number(&a[2],min,max)?])
}
fn chunk(v: &Value) -> io::Result<[i32;2]> {
    let a=v.as_array().filter(|a|a.len()==2).ok_or_else(||bad("foliage chunk"))?;
    let get=|v:&Value|v.as_i64().filter(|x|(-64..=64).contains(x)).map(|x|x as i32).ok_or_else(||bad("foliage chunk bound"));
    Ok([get(&a[0])?,get(&a[1])?])
}
fn pin(v:&Value, bytes:u64, digest:&str) -> io::Result<()> {
    fields(v,&["bytes","sha256"])?;
    if v["bytes"].as_u64()!=Some(bytes) || v["sha256"].as_str()!=Some(digest) {return Err(bad("foliage source pin"));} Ok(())
}

// serde_json::Value alone silently overwrites duplicate object members. A
// recursive visitor rejects those before policy validation; serde_json retains
// its normal recursion limit and the entire document is already byte-bounded.
struct Strict(Value);
impl<'de> Deserialize<'de> for Strict {
    fn deserialize<D:Deserializer<'de>>(d:D)->Result<Self,D::Error> {
        struct V;
        impl<'de> Visitor<'de> for V {
            type Value=Strict;
            fn expecting(&self,f:&mut std::fmt::Formatter)->std::fmt::Result {f.write_str("bounded JSON without duplicate keys")}
            fn visit_bool<E:serde::de::Error>(self,v:bool)->Result<Strict,E>{Ok(Strict(Value::Bool(v)))}
            fn visit_i64<E:serde::de::Error>(self,v:i64)->Result<Strict,E>{Ok(Strict(Value::from(v)))}
            fn visit_u64<E:serde::de::Error>(self,v:u64)->Result<Strict,E>{Ok(Strict(Value::from(v)))}
            fn visit_f64<E:serde::de::Error>(self,v:f64)->Result<Strict,E>{serde_json::Number::from_f64(v).map(|n|Strict(Value::Number(n))).ok_or_else(||E::custom("non-finite number"))}
            fn visit_str<E:serde::de::Error>(self,v:&str)->Result<Strict,E>{Ok(Strict(Value::String(v.to_owned())))}
            fn visit_string<E:serde::de::Error>(self,v:String)->Result<Strict,E>{Ok(Strict(Value::String(v)))}
            fn visit_none<E:serde::de::Error>(self)->Result<Strict,E>{Ok(Strict(Value::Null))}
            fn visit_unit<E:serde::de::Error>(self)->Result<Strict,E>{Ok(Strict(Value::Null))}
            fn visit_seq<A:SeqAccess<'de>>(self,mut a:A)->Result<Strict,A::Error>{
                let mut values=Vec::new();while let Some(Strict(v))=a.next_element()?{values.push(v);}Ok(Strict(Value::Array(values)))
            }
            fn visit_map<A:MapAccess<'de>>(self,mut a:A)->Result<Strict,A::Error>{
                let mut values=serde_json::Map::new();while let Some((key,Strict(v)))=a.next_entry::<String,Strict>()? {
                    if values.insert(key,v).is_some(){return Err(A::Error::custom("duplicate object key"));}
                } Ok(Strict(Value::Object(values)))
            }
        }
        d.deserialize_any(V)
    }
}
fn cross(a:Point,b:Point)->Point {[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]}
fn dot(a:Point,b:Point)->f64 {a.into_iter().zip(b).map(|(x,y)|x*y).sum()}
fn sub(a:Point,b:Point)->Point {std::array::from_fn(|i|a[i]-b[i])}

#[derive(Clone, Debug)]
struct Volume { chunk:[i32;2], index:u32, resource:String, coefficient:f64, center:Point, extents:Point, inverse:[Point;3] }
#[derive(Clone, Debug)]
pub struct Foliage { pub calibration_sha256:String, pub source_sha256:String, raw:Vec<u8>, volumes:Vec<Volume>, fire_near_m:f64, fire_multiplier:f64 }
#[derive(Clone, Debug, PartialEq)]
pub struct Hit { pub chunk:[i32;2], pub speedtree_index:u32, pub resource:String,
    pub concealment_additive:f64, pub t_enter:f64, pub t_exit:f64 }

impl Foliage {
    /// `expected_sha256` must come from the operator's trusted, versioned map
    /// configuration, not from this file. Loading alone never enables foliage.
    pub fn load(path:&Path, expected_sha256:&str)->io::Result<Self> {
        if !sha(expected_sha256) {return Err(bad("foliage expected hash"));}
        let file=File::open(path)?;
        if !file.metadata()?.is_file() {return Err(bad("foliage file type"));}
        let mut raw=Vec::new();file.take(MAX_BYTES+1).read_to_end(&mut raw)?;
        if raw.is_empty() || raw.len() as u64>MAX_BYTES {return Err(bad("foliage input size"));}
        let actual=format!("{:x}",Sha256::digest(&raw));
        if actual!=expected_sha256 {return Err(bad("foliage input hash"));}
        Self::parse(&raw)
    }
    fn parse(raw:&[u8])->io::Result<Self> {
        if raw.is_empty() || raw.len() as u64>MAX_BYTES {return Err(bad("foliage input size"));}
        let Strict(doc)=serde_json::from_slice(raw).map_err(|_|bad("foliage JSON"))?;
        fields(&doc,&["schema","map","classification","calibration_schema","calibration_sha256","map_package_pin",
            "shared_package_pin","selected_resource_pins","chunk_pins","geometry_contract","aabb_contract","effect_contract","instances","fire_near_distance_m","fire_near_multiplier"])?;
        if doc["schema"]!=SCHEMA || doc["map"]!="02_malinovka" || doc["classification"]!="PROJECT_CALIBRATION_NOT_HISTORICAL"
            || doc["calibration_schema"]!=CAL_SCHEMA {return Err(bad("foliage identity"));}
        for key in ["geometry_contract","aabb_contract","effect_contract"] {text(&doc[key],512)?;}
        let calibration_sha256=text(&doc["calibration_sha256"],64)?;
        if !sha(calibration_sha256) {return Err(bad("foliage calibration hash"));}
        let fire_near_m=number(&doc["fire_near_distance_m"],0.,1000.)?;
        let fire_multiplier=number(&doc["fire_near_multiplier"],0.,1.)?;
        pin(&doc["map_package_pin"],86993684,MAP_SHA)?;pin(&doc["shared_package_pin"],1295549695,SHARED_SHA)?;
        let rp=&doc["selected_resource_pins"];fields(rp,&RESOURCES.map(|r|r.0))?;
        for (name,size,digest) in RESOURCES {pin(&rp[name],size,digest)?;}
        let chunks=doc["chunk_pins"].as_array().filter(|v|v.len()==144).ok_or_else(||bad("foliage chunk count"))?;
        let mut chunk_set=BTreeSet::new();
        for row in chunks {
            fields(row,&["chunk","sha256"])?;let c=chunk(&row["chunk"])?;let hash=text(&row["sha256"],64)?;
            if !sha(hash) || !chunk_set.insert(c) {return Err(bad("foliage duplicate chunk or hash"));}
        }
        let rows=doc["instances"].as_array().filter(|a|!a.is_empty() && a.len()<=MAX_INSTANCES).ok_or_else(||bad("foliage instance count"))?;
        let mut volumes=BTreeMap::new();
        for row in rows {
            fields(row,&["chunk","speedtree_index","resource","seed","center_world","basis_world_rows","aabb_half_extents_world","concealment_additive"])?;
            let c=chunk(&row["chunk"])?;
            let index=row["speedtree_index"].as_u64().filter(|n|(1..=5000).contains(n)).ok_or_else(||bad("foliage index"))? as u32;
            if !chunk_set.contains(&c) || row["seed"].as_u64().filter(|n|*n<=u32::MAX as u64).is_none() {return Err(bad("foliage identity"));}
            let resource=text(&row["resource"],128)?;
            if !RESOURCES.iter().any(|r|r.0==resource) {return Err(bad("foliage resource"));}
            let coefficient=number(&row["concealment_additive"],0.,1.)?;
            let center=point(&row["center_world"],-MAX_COORD,MAX_COORD)?;
            let basis=row["basis_world_rows"].as_array().filter(|a|a.len()==3).ok_or_else(||bad("foliage basis"))?;
            let basis=[point(&basis[0],-MAX_EXTENT,MAX_EXTENT)?,point(&basis[1],-MAX_EXTENT,MAX_EXTENT)?,point(&basis[2],-MAX_EXTENT,MAX_EXTENT)?];
            let det=dot(basis[0],cross(basis[1],basis[2]));
            if !det.is_finite() || det.abs()<MIN_DETERMINANT {return Err(bad("foliage degenerate basis"));}
            let inverse=[cross(basis[1],basis[2]).map(|x|x/det),cross(basis[2],basis[0]).map(|x|x/det),cross(basis[0],basis[1]).map(|x|x/det)];
            let extents=std::array::from_fn::<_,3,_>(|j|basis.iter().map(|r|r[j]*r[j]).sum::<f64>().sqrt());
            let supplied=point(&row["aabb_half_extents_world"],0.,MAX_EXTENT)?;
            if extents.into_iter().zip(supplied).any(|(a,b)|a<=0. || a>MAX_EXTENT || (a-b).abs()>1e-9*(1.+a)) {return Err(bad("foliage aabb mismatch"));}
            let v=Volume{chunk:c,index,resource:resource.to_owned(),coefficient,center,extents,inverse};
            if volumes.insert((c,index),v).is_some() {return Err(bad("foliage duplicate instance"));}
        }
        Ok(Self{calibration_sha256:calibration_sha256.to_owned(),source_sha256:format!("{:x}",Sha256::digest(raw)),raw:raw.to_vec(),volumes:volumes.into_values().collect(),fire_near_m,fire_multiplier})
    }
    pub fn len(&self)->usize {self.volumes.len()}
    /// Closed segment, including endpoints/tangencies and a point inside a
    /// volume. Stable source-key order, independent of input row order. An
    /// invalid query returns an error instead of partial results.
    pub fn intersections(&self,start:Point,end:Point)->io::Result<Vec<Hit>> {
        if start.into_iter().chain(end).any(|v|!v.is_finite() || v.abs()>MAX_COORD) {return Err(bad("foliage query bounds"));}
        let mut hits=Vec::new();
        for v in &self.volumes {
            if !aabb_intersects(start,end,v.center,v.extents) {continue;}
            let p=sub(start,v.center);let d=sub(end,start);
            let u=v.inverse.map(|r|dot(r,p));let delta=v.inverse.map(|r|dot(r,d));
            if let Some((t_enter,t_exit))=unit_segment(u,delta) {
                hits.push(Hit{chunk:v.chunk,speedtree_index:v.index,resource:v.resource.clone(),concealment_additive:v.coefficient,t_enter,t_exit});
            }
        }
        Ok(hits)
    }
    /// Project v1: strongest crossed volume. While the target is in its
    /// server fire window, only shrubs whose ray-exit point is within the
    /// calibrated distance of that target control point are attenuated.
    pub fn contribution(&self,start:Point,end:Point,fired:bool)->io::Result<f32> {
        if start.into_iter().chain(end).any(|v|!v.is_finite() || v.abs()>MAX_COORD) {return Err(bad("foliage query bounds"));}
        let d=sub(end,start);let length=dot(d,d).sqrt();let mut best=0_f64;
        for v in &self.volumes {
            if !aabb_intersects(start,end,v.center,v.extents) {continue;}
            let p=sub(start,v.center);let u=v.inverse.map(|r|dot(r,p));let delta=v.inverse.map(|r|dot(r,d));
            if let Some((_,exit))=unit_segment(u,delta) {
                // Inclusive project threshold with a small distance-only
                // tolerance for a boundary derived from quadratic roots.
                let near=(1.-exit)*length <= self.fire_near_m+1e-9*(1.+length);
                let effect=if fired && near {v.coefficient*self.fire_multiplier} else {v.coefficient};
                best=best.max(effect);
            }
        }
        Ok(best as f32)
    }
}

// The containing World uses Arc<Foliage>. BW interns each Arc once per worker
// connection; reconnects intentionally revalidate and retransmit the source.
impl crate::bw_wire::Wire for Foliage {
    fn put(&self,w:&mut crate::bw_wire::Enc) {
        self.source_sha256.put(w);w.len(self.raw.len());w.bytes(&self.raw);
    }
    fn get(r:&mut crate::bw_wire::Dec)->io::Result<Self> {
        let expected=String::get(r)?;let n=r.len()?;
        if !sha(&expected) || n==0 || n as u64>MAX_BYTES{return Err(bad("foliage worker length/hash"));}
        let raw=r.take(n)?;
        if format!("{:x}",Sha256::digest(raw))!=expected{return Err(bad("foliage worker hash"));}
        Self::parse(raw)
    }
}

fn aabb_intersects(start:Point,end:Point,center:Point,extent:Point)->bool {
    let (mut low,mut high)=(0_f64,1_f64);
    for i in 0..3 {
        // Expand only the broad phase for floating-point boundary rounding;
        // the ellipsoid test still uses the unmodified basis.
        let margin=1e-9*(1.+extent[i]);
        let a=center[i]-extent[i]-margin;let b=center[i]+extent[i]+margin;let d=end[i]-start[i];
        if d==0. {if start[i]<a || start[i]>b{return false;}}
        else {let t1=(a-start[i])/d;let t2=(b-start[i])/d;low=low.max(t1.min(t2));high=high.min(t1.max(t2));if low>high{return false;}}
    } true
}
fn unit_segment(p:Point,d:Point)->Option<(f64,f64)> {
    let a=dot(d,d);let c=dot(p,p)-1.;
    if a==0. {return (c<=0.).then_some((0.,0.));}
    let b=dot(p,d);let disc=b*b-a*c;
    if disc<0. {return None;}
    let root=disc.sqrt();let enter=((-b-root)/a).max(0.);let exit=((-b+root)/a).min(1.);
    (enter<=exit).then_some((enter,exit))
}

#[cfg(test)]
mod tests {
    use super::*;
    pub(super) fn fixture()->Value {
        let chunks=(-6..6).flat_map(|x|(-6..6).map(move |z|serde_json::json!({"chunk":[x,z],"sha256":"a".repeat(64)}))).collect::<Vec<_>>();
        let mut resources=serde_json::Map::new();
        for (name,bytes,digest) in RESOURCES {resources.insert(name.into(),serde_json::json!({"bytes":bytes,"sha256":digest}));}
        serde_json::json!({"schema":SCHEMA,"map":"02_malinovka","classification":"PROJECT_CALIBRATION_NOT_HISTORICAL",
            "calibration_schema":CAL_SCHEMA,"calibration_sha256":"b".repeat(64),"map_package_pin":{"bytes":86993684,"sha256":MAP_SHA},
            "shared_package_pin":{"bytes":1295549695_u64,"sha256":SHARED_SHA},"selected_resource_pins":resources,"chunk_pins":chunks,
            "geometry_contract":"fixture","aabb_contract":"fixture","effect_contract":"fixture","fire_near_distance_m":15.,"fire_near_multiplier":0.25,
            "instances":[{"chunk":[0,0],"speedtree_index":2,"resource":RESOURCES[0].0,"seed":1,
                "center_world":[0,0,0],"basis_world_rows":[[1,0,0],[0,1,0],[0,0,1]],
                "aabb_half_extents_world":[1,1,1],"concealment_additive":0.2}]})
    }
    fn parse_fixture(v:&Value)->io::Result<Foliage> {Foliage::parse(&serde_json::to_vec(v).unwrap())}
    #[test] fn segment_endpoint_tangent_inside_and_miss() {
        assert_eq!(unit_segment([-2.,0.,0.],[4.,0.,0.]),Some((0.25,0.75)));
        assert_eq!(unit_segment([0.,1.,0.],[1.,0.,0.]),Some((0.,0.)));
        assert_eq!(unit_segment([0.,0.,0.],[0.,0.,0.]),Some((0.,0.)));
        assert_eq!(unit_segment([2.,0.,0.],[0.,0.,0.]),None);
        assert_eq!(unit_segment([-2.,2.,0.],[4.,0.,0.]),None);
    }
    #[test] fn rotated_sheared_ellipsoid_keeps_aabb_and_stable_order() {
        let basis=[[0.,0.,2.],[0.,2.4,0.],[-4.,0.,1.]];
        let det=dot(basis[0],cross(basis[1],basis[2]));
        let inverse=[cross(basis[1],basis[2]).map(|x|x/det),cross(basis[2],basis[0]).map(|x|x/det),cross(basis[0],basis[1]).map(|x|x/det)];
        let v=Volume{chunk:[-2,3],index:1,resource:"fixture".into(),coefficient:0.2,center:[0.;3],extents:[4.,2.4,5_f64.sqrt()],inverse};
        let f=Foliage{calibration_sha256:"fixture".into(),source_sha256:"fixture".into(),raw:vec![],volumes:vec![v],fire_near_m:15.,fire_multiplier:0.25};
        let hits=f.intersections([-8.,0.,0.],[8.,0.,0.]).unwrap();
        assert_eq!(hits.len(),1);assert!(hits[0].t_enter<0.5 && hits[0].t_exit>0.5);
        assert!(f.intersections([f64::NAN,0.,0.],[0.;3]).is_err());
        assert!(f.intersections([-8.,3.,0.],[8.,3.,0.]).unwrap().is_empty());
    }
    #[test] fn validates_hash_format_and_json_bound() {
        assert!(Foliage::load(Path::new("missing"),"untrusted").is_err());
        assert!(Foliage::parse(&vec![b' '; MAX_BYTES as usize + 1]).is_err());
        assert!(Foliage::parse(b"{}").is_err());
        assert!(serde_json::from_slice::<Strict>(br#"{"x":1,"x":2}"#).is_err());
        assert!(serde_json::from_slice::<Strict>(br#"{"x":{"y":1,"y":2}}"#).is_err());
    }
    #[test] fn parsed_source_validation_and_order_are_fail_closed() {
        let original=fixture();let mut v=original.clone();
        let mut second=v["instances"][0].clone();second["speedtree_index"]=1.into();
        v["instances"].as_array_mut().unwrap().push(second);
        let f=parse_fixture(&v).unwrap();let hits=f.intersections([-2.,0.,0.],[2.,0.,0.]).unwrap();
        assert_eq!(hits.iter().map(|h|h.speedtree_index).collect::<Vec<_>>(),vec![1,2]);
        v["instances"][1]["speedtree_index"]=2.into();assert!(parse_fixture(&v).is_err());
        let mut v=original.clone();v["instances"][0]["basis_world_rows"][0]=serde_json::json!([0,0,0]);assert!(parse_fixture(&v).is_err());
        let mut v=original.clone();v["instances"][0]["aabb_half_extents_world"][0]=0.01.into();assert!(parse_fixture(&v).is_err());
        let mut v=original.clone();v["map_package_pin"]["sha256"]="0".repeat(64).into();assert!(parse_fixture(&v).is_err());
        let mut v=original.clone();v["instances"][0]["chunk"]=serde_json::json!([40,40]);assert!(parse_fixture(&v).is_err());
        let mut v=original;v["instances"][0]["concealment_additive"]=2.into();assert!(parse_fixture(&v).is_err());
    }
    #[test] fn foliage_bw_arc_sends_content_once_per_connection() {
        use std::{sync::Arc,time::Instant};
        let mut document=serde_json::to_vec(&fixture()).unwrap();
        // Match the actual 1,024-instance receipt's 501,974 byte size while
        // keeping the fixture hermetic and the JSON valid.
        document.resize(501_974,b' ');
        let source=Arc::new(Foliage::parse(&document).unwrap());let raw_len=source.raw.len();
        let now=Instant::now();let mut gateway=crate::bw_wire::Arcs::new(false);let mut worker=crate::bw_wire::Arcs::new(true);
        let first=crate::bw_wire::encode(&source,now,&mut gateway).unwrap();
        let received:Arc<Foliage>=crate::bw_wire::decode(&first,now,&mut worker).unwrap();
        assert_eq!(received.source_sha256,source.source_sha256);assert_eq!(first.len(),raw_len+77);
        let reply=crate::bw_wire::encode(&received,now,&mut worker).unwrap();assert_eq!(reply.len(),5);
        let back:Arc<Foliage>=crate::bw_wire::decode(&reply,now,&mut gateway).unwrap();assert!(Arc::ptr_eq(&source,&back));
        let again=crate::bw_wire::encode(&back,now,&mut gateway).unwrap();assert_eq!(again.len(),5);
        let _:Arc<Foliage>=crate::bw_wire::decode(&again,now,&mut worker).unwrap();
        let mut reconnected=crate::bw_wire::Arcs::new(false);
        let fresh=crate::bw_wire::encode(&source,now,&mut reconnected).unwrap();assert_eq!(first.len(),fresh.len());
    }
    #[test] fn project_fire_near_and_far_shrubs_have_distinct_contributions() {
        let near=super::test_fixture_at([95.,0.,0.],1.);
        let far=super::test_fixture_at([50.,0.,0.],1.);
        let a=[0.,0.,0.];let b=[100.,0.,0.];
        assert!((near.contribution(a,b,false).unwrap()-0.2).abs()<1e-6);
        assert!((near.contribution(a,b,true).unwrap()-0.05).abs()<1e-6);
        assert!((far.contribution(a,b,true).unwrap()-0.2).abs()<1e-6);
        let boundary=super::test_fixture_at([84.,0.,0.],1.);
        assert!((boundary.contribution(a,b,true).unwrap()-0.05).abs()<1e-6);
    }
}

#[cfg(test)]
pub(super) fn test_fixture_at(center:Point, radius:f64)->Foliage {
    let mut v=tests::fixture();
    v["instances"][0]["center_world"]=serde_json::json!(center);
    v["instances"][0]["basis_world_rows"]=serde_json::json!([[radius,0.,0.],[0.,radius,0.],[0.,0.,radius]]);
    v["instances"][0]["aabb_half_extents_world"]=serde_json::json!([radius,radius,radius]);
    Foliage::parse(&serde_json::to_vec(&v).unwrap()).unwrap()
}

#[cfg(test)]
pub(crate) fn test_document()->(Vec<u8>,String) {
    let raw=serde_json::to_vec(&tests::fixture()).unwrap();let hash=format!("{:x}",Sha256::digest(&raw));(raw,hash)
}
