//! Owned, hash-bound test_lab physics process. No native IDs or client poses.
//! IPC is one bounded JSON line per fixed six-step request; never catch up.
use std::{collections::BTreeSet,fmt,fs,io::{self,Read,Write},path::{Path,PathBuf},
    process::{Child,Command,Stdio},sync::{Arc,Mutex,mpsc,atomic::{AtomicBool,Ordering}},thread,
    time::{Duration,Instant}};
use serde::{Deserialize,Deserializer,de::{self,Visitor,MapAccess,SeqAccess}};
use serde_json::{Value,Map,Number};
use sha2::{Digest,Sha256};
#[path="worker/catalog.rs"]
mod catalog;
#[path="worker/fracture.rs"]
mod fracture;
#[path="worker/angular.rs"]
mod angular;
#[cfg(test)]
#[path="worker/angular_capture_tests.rs"]
mod angular_capture_tests;
#[cfg(test)]
#[path="worker/real_test_capture.rs"]
pub(crate) mod real_test_capture;
use crate::gateway091::shared::ram_proof;
#[path="worker/profile.rs"]
mod profile;
use crate::gateway091::shared::vehicle_profile::VehicleKind;
pub use fracture::Receipt as FractureReceipt;
pub use catalog::{CatalogSpec,CatalogEntry,Scene,CatalogAck,MAX_CATALOG_OBJECTS,MAX_REMOVED_OBJECTS};

pub const STEP:Duration=Duration::from_millis(100);
pub const MAX_SEQUENCE:u32=36000;
pub const MAX_IPC_LINE:usize=32*1024;
pub const MAX_ANGULAR_IPC_LINE:usize=64*1024;
pub const START_TIMEOUT:Duration=Duration::from_secs(120);
pub const REPLY_TIMEOUT:Duration=Duration::from_millis(500);
pub const MAX_LAG:Duration=Duration::from_millis(500);
pub const REMOVAL_REVISION:&str="karelia-instance1513-v1";
const PHYSICS_MANIFEST:&str="ea6ef22aed0fdd4e4826500c280a616737f8990ce7ab7cd808b9382227ec5ffd";
const PROJECTILE_MANIFEST:&str="ccd28d8e3320d041e569e217a8c20e0285db0459bc2ef447c5bd95dd97d80cea";
fn bad()->io::Error {io::Error::new(io::ErrorKind::InvalidData,"map-drive worker contract")}

// serde_json::Value normally accepts duplicate keys. Reject them at EVERY depth.
struct Unique<const ARRAY_LIMIT:usize>(Value);
impl<'de,const ARRAY_LIMIT:usize> Deserialize<'de> for Unique<ARRAY_LIMIT> {
    fn deserialize<D:Deserializer<'de>>(d:D)->Result<Self,D::Error> {
        struct V<const ARRAY_LIMIT:usize>;
        impl<'de,const ARRAY_LIMIT:usize> Visitor<'de> for V<ARRAY_LIMIT> {
            type Value=Unique<ARRAY_LIMIT>;
            fn expecting(&self,f:&mut fmt::Formatter)->fmt::Result {f.write_str("bounded unique JSON")}
            fn visit_bool<E:de::Error>(self,v:bool)->Result<Unique<ARRAY_LIMIT>,E>{Ok(Unique(v.into()))}
            fn visit_i64<E:de::Error>(self,v:i64)->Result<Unique<ARRAY_LIMIT>,E>{Ok(Unique(v.into()))}
            fn visit_u64<E:de::Error>(self,v:u64)->Result<Unique<ARRAY_LIMIT>,E>{Ok(Unique(v.into()))}
            fn visit_f64<E:de::Error>(self,v:f64)->Result<Unique<ARRAY_LIMIT>,E>{Ok(Unique(Value::Number(Number::from_f64(v).ok_or_else(||E::custom("finite"))?)))}
            fn visit_str<E:de::Error>(self,v:&str)->Result<Unique<ARRAY_LIMIT>,E>{Ok(Unique(v.into()))}
            fn visit_string<E:de::Error>(self,v:String)->Result<Unique<ARRAY_LIMIT>,E>{Ok(Unique(v.into()))}
            fn visit_unit<E:de::Error>(self)->Result<Unique<ARRAY_LIMIT>,E>{Ok(Unique(Value::Null))}
            fn visit_seq<A:SeqAccess<'de>>(self,mut a:A)->Result<Unique<ARRAY_LIMIT>,A::Error>{
                let mut v=Vec::new();while let Some(Unique(x))=a.next_element::<Unique<ARRAY_LIMIT>>()? {
                    if v.len()>=ARRAY_LIMIT{return Err(de::Error::custom("array bound"));}v.push(x);
                }Ok(Unique(Value::Array(v)))
            }
            fn visit_map<A:MapAccess<'de>>(self,mut a:A)->Result<Unique<ARRAY_LIMIT>,A::Error>{
                let mut v=Map::new();while let Some((k,Unique(x)))=a.next_entry::<String,Unique<ARRAY_LIMIT>>()? {
                    if v.len()>=256 || v.insert(k,x).is_some(){return Err(de::Error::custom("duplicate/bound"));}
                }Ok(Unique(Value::Object(v)))
            }
        }d.deserialize_any(V::<ARRAY_LIMIT>)
    }
}
fn json_with_node_limit<const ARRAY_LIMIT:usize>(raw:&[u8],maximum:usize,node_limit:usize)->io::Result<Value> {
    if raw.is_empty() || raw.len()>maximum{return Err(bad());}
    let Unique(v)=serde_json::from_slice::<Unique<ARRAY_LIMIT>>(raw).map_err(|_|bad())?;
    fn depth(v:&Value,d:usize,n:&mut usize,node_limit:usize)->io::Result<()> {
        if d>12 || *n>=node_limit{return Err(bad());}*n+=1;
        match v {Value::Object(o)=>for x in o.values(){depth(x,d+1,n,node_limit)?;},Value::Array(a)=>for x in a{depth(x,d+1,n,node_limit)?;},_=>{}}Ok(())
    }depth(&v,0,&mut 0,node_limit)?;Ok(v)
}
pub(crate) fn json(raw:&[u8],maximum:usize)->io::Result<Value> {
    json_with_node_limit::<1024>(raw,maximum,4096)
}
/// Catalog manifests have a larger row bound than ordinary IPC packets. Keep
/// the same depth/array/object limits while admitting 1024 six-field rows.
pub(crate) fn json_catalog(raw:&[u8],maximum:usize)->io::Result<Value> {
    json_with_node_limit::<1024>(raw,maximum,20000)
}
/// The explicit extended catalog profile admits at most 2048 whole objects.
/// Ordinary IPC and historical catalogs retain their smaller parser budgets.
pub(crate) fn json_catalog_extended(raw:&[u8],maximum:usize)->io::Result<Value> {
    json_with_node_limit::<2048>(raw,maximum,40000)
}
pub(crate) fn fields<'a>(v:&'a Value,keys:&[&str])->io::Result<&'a Map<String,Value>> {
    let m=v.as_object().ok_or_else(bad)?;
    if m.len()!=keys.len() || keys.iter().any(|k|!m.contains_key(*k)){return Err(bad());}Ok(m)
}
fn text<'a>(v:&'a Value,key:&str)->io::Result<&'a str>{v[key].as_str().ok_or_else(bad)}
fn uint(v:&Value)->io::Result<u64>{v.as_u64().ok_or_else(bad)}
fn number(v:&Value,lo:f32,hi:f32)->io::Result<f32>{
    let x=v.as_f64().ok_or_else(bad)? as f32;
    if !x.is_finite() || x<lo || x>hi{return Err(bad());}Ok(x)
}
fn vector(v:&Value,lo:f32,hi:f32)->io::Result<[f32;3]>{
    let a=v.as_array().ok_or_else(bad)?;if a.len()!=3{return Err(bad());}
    Ok([number(&a[0],lo,hi)?,number(&a[1],lo,hi)?,number(&a[2],lo,hi)?])
}
fn hash_text(s:&str)->io::Result<()> {
    if s.len()!=64 || !s.bytes().all(|c|c.is_ascii_digit() || (b'a'..=b'f').contains(&c)){return Err(bad());}Ok(())
}
fn non_reparse(path:&Path)->io::Result<()> {
    for p in path.ancestors() {
        let m=fs::symlink_metadata(p)?;
        if m.file_type().is_symlink(){return Err(bad());}
        #[cfg(windows)] {use std::os::windows::fs::MetadataExt;if m.file_attributes()&0x400!=0{return Err(bad());}}
    }Ok(())
}
fn owned(root:&Path,path:&Path)->io::Result<PathBuf>{
    if !path.is_absolute(){return Err(bad());}non_reparse(path)?;
    let p=path.canonicalize()?;if !p.starts_with(root) || p==root{return Err(bad());}Ok(p)
}
// Rust's Windows canonicalize yields \\?\D:\..., while the checked JSON
// geometry references use D:\.... .NET compares these prefixes textually.
// Preserve canonical ownership internally; pass the same absolute drive path
// spelling to the owned .NET worker only after those checks have succeeded.
fn worker_path_argument(path:&Path)->io::Result<PathBuf>{
    #[cfg(windows)] {
        let s=path.to_str().ok_or_else(bad)?;
        if let Some(p)=s.strip_prefix(r"\\?\") {
            let b=p.as_bytes();if b.len()<3 || !b[0].is_ascii_alphabetic() || b[1]!=b':' || b[2]!=b'\\'{return Err(bad());}
            return Ok(PathBuf::from(p));
        }
    }
    if !path.is_absolute(){return Err(bad());}Ok(path.to_path_buf())
}
fn read(path:&Path,max:usize)->io::Result<Vec<u8>> {
    let f=fs::File::open(path)?;let m=f.metadata()?;
    if !m.is_file() || m.len()==0 || m.len()>max as u64{return Err(bad());}
    let mut raw=Vec::new();f.take(max as u64+1).read_to_end(&mut raw)?;
    if raw.len()>max || raw.len() as u64!=m.len(){return Err(bad());}Ok(raw)
}
fn file_hash(path:&Path,size:u64)->io::Result<String>{
    let mut f=fs::File::open(path)?;if !f.metadata()?.is_file() || f.metadata()?.len()!=size{return Err(bad());}
    let mut h=Sha256::new();let mut b=[0;65536];let mut n=0u64;
    loop{let got=f.read(&mut b)?;if got==0{break;}n+=got as u64;if n>size{return Err(bad());}h.update(&b[..got]);}
    if n!=size{return Err(bad());}Ok(format!("{:x}",h.finalize()))
}

#[derive(Clone,Debug,PartialEq)]
pub struct MapSpec {pub asset:String,pub arena_type_id:i32,pub config:PathBuf,pub config_sha256:String,
    pub bounds:[f32;4],pub spawn:[f32;3],pub spawn_yaw:f32,pub mass_kg:f32}
impl MapSpec {
    fn load(root:&Path,v:&Value,config_version:u64)->io::Result<Self>{
        fields(v,&["asset","arena_type_id","config","config_sha256"])?;
        let asset=text(v,"asset")?;let id=uint(&v["arena_type_id"])?;
        if !matches!((asset,id),("01_karelia",1)|("05_prohorovka",4)){return Err(bad());}
        let config=owned(root,Path::new(text(v,"config")?))?;let hash=text(v,"config_sha256")?;hash_text(hash)?;
        let raw=read(&config,16384)?;if format!("{:x}",Sha256::digest(&raw))!=hash{return Err(bad());}
        let c=json(&raw,16384)?;
        let mut names=vec!["version","profile","map","terrain","obstacles","spawn_origin","spawn_yaw","body_half_extents",
            "body_center_offset","wheel_points","mass_kg","max_forward_mps","max_reverse_mps","engine_max_torque_nm",
            "wheel_radius","suspension_min","suspension_max","track_max_brake_torque","bounds_xz"];
        if config_version>=2 {names.extend(["longitudinal_friction","lateral_friction","stationary_steering_ratio"]);}
        if config_version==3 {names.push("handling");}
        fields(&c,&names)?;
        if !(1..=3).contains(&config_version) || uint(&c["version"])?!=config_version || text(&c,"profile")?!="test_lab" || text(&c,"map")?!=asset{return Err(bad());}
        for k in ["terrain","obstacles"]{fields(&c[k],&["path","sha256"])?;hash_text(text(&c[k],"sha256")?)?;owned(root,Path::new(text(&c[k],"path")?))?;}
        let a=c["bounds_xz"].as_array().ok_or_else(bad)?;if a.len()!=4{return Err(bad());}
        let bounds=[number(&a[0],-1000.,0.)?,number(&a[1],-1000.,0.)?,number(&a[2],0.,1000.)?,number(&a[3],0.,1000.)?];
        let spawn=vector(&c["spawn_origin"],-1000.,1000.)?;let yaw=number(&c["spawn_yaw"],-std::f32::consts::PI,std::f32::consts::PI)?;
        let mass_kg=number(&c["mass_kg"],1000.,100000.)?;
        if bounds[2]-bounds[0]<100. || bounds[3]-bounds[1]<100. || spawn[0]<bounds[0]+5. || spawn[0]>bounds[2]-5.
            || spawn[2]<bounds[1]+5. || spawn[2]>bounds[3]-5. {return Err(bad());}
        Ok(Self {asset:asset.into(),arena_type_id:id as i32,config,config_sha256:hash.into(),bounds,spawn,spawn_yaw:yaw,mass_kg})
    }
}
/// The one approved test_lab object. Private fields prevent callers from
/// constructing a different identity after the source descriptor is checked.
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct RemovalSpec {path:PathBuf,sha256:String}
impl RemovalSpec {
    pub fn load(local_root:&Path,path:&Path,sha256:&str)->io::Result<Self>{
        non_reparse(local_root)?;let root=local_root.canonicalize()?;hash_text(sha256)?;
        let path=owned(&root,path)?;let raw=read(&path,4096)?;
        if format!("{:x}",Sha256::digest(&raw))!=sha256{return Err(bad());}
        Self::validate(&json(&raw,4096)?)?;Ok(Self{path,sha256:sha256.into()})
    }
    fn validate(v:&Value)->io::Result<()>{
        fields(v,&["version","profile","map","object_id","instance_id","physics_manifest_sha256","projectile_manifest_sha256",
            "first_triangle","triangle_count","object_revision"])?;
        if uint(&v["version"])?!=1 || text(v,"profile")?!="test_lab" || text(v,"map")?!="01_karelia" || uint(&v["object_id"])?!=1
            || uint(&v["instance_id"])?!=1513 || text(v,"physics_manifest_sha256")?!=PHYSICS_MANIFEST
            || text(v,"projectile_manifest_sha256")?!=PROJECTILE_MANIFEST || uint(&v["first_triangle"])?!=171814
            || uint(&v["triangle_count"])?!=42 || text(v,"object_revision")?!=REMOVAL_REVISION {return Err(bad());}Ok(())
    }
    fn verify(&self,root:&Path,map:&MapSpec)->io::Result<()>{
        if map.asset!="01_karelia" || map.arena_type_id!=1 || Self::load(root,&self.path,&self.sha256)?!=*self{return Err(bad());}
        let raw=read(&owned(root,&map.config)?,16384)?;
        if format!("{:x}",Sha256::digest(&raw))!=map.config_sha256{return Err(bad());}
        let v=json(&raw,16384)?;
        if text(&v["obstacles"],"sha256")?!=PHYSICS_MANIFEST{return Err(bad());}Ok(())
    }
    pub fn sha256(&self)->&str{&self.sha256}
    pub fn object_id(&self)->u32{1}
    pub fn object_revision(&self)->&str{REMOVAL_REVISION}
}
#[derive(Clone,Debug)]
struct Asset {path:PathBuf,bytes:u64,sha256:String}
#[derive(Clone,Debug)]
pub struct Pool {pub local_root:PathBuf,pub maps:Vec<MapSpec>,pub sha256:String,executable:PathBuf,
    runtime:PathBuf,assets:Vec<Asset>,vehicle_profile:Option<profile::VehicleProfile>,shared_only:bool}
impl Pool {
    pub fn load(local_root:&Path,path:&Path)->io::Result<Self>{
        non_reparse(local_root)?;let root=local_root.canonicalize()?;let raw=read(&owned(&root,path)?,16384)?;
        let v=json(&raw,16384)?;
        let pool_version=uint(&v["version"])?;
        let vehicle_profile=match pool_version {
            1=>{fields(&v,&["version","profile","worker","maps"])?;None},
            2|3|4=>{fields(&v,&["version","profile","worker","maps","vehicle_profile"])?;
                Some(profile::VehicleProfile::load(&root,&v["vehicle_profile"],pool_version)?)},
            _=>return Err(bad()),
        };
        if text(&v,"profile")?!="test_lab"{return Err(bad());}
        let w=&v["worker"];fields(w,&["executable","artifact_manifest","artifact_manifest_sha256"])?;
        let executable=owned(&root,Path::new(text(w,"executable")?))?;
        if executable.extension().and_then(|s|s.to_str())!=Some("exe"){return Err(bad());}
        let runtime=executable.parent().ok_or_else(bad)?.to_path_buf();
        let manifest=owned(&root,Path::new(text(w,"artifact_manifest")?))?;
        if manifest.starts_with(&runtime){return Err(bad());}
        let h=text(w,"artifact_manifest_sha256")?;hash_text(h)?;let bytes=read(&manifest,131072)?;
        if format!("{:x}",Sha256::digest(&bytes))!=h{return Err(bad());}
        let doc=json(&bytes,131072)?;fields(&doc,&["version","files"])?;if uint(&doc["version"])?!=1{return Err(bad());}
        let rows=doc["files"].as_array().ok_or_else(bad)?;if rows.is_empty() || rows.len()>256{return Err(bad());}
        let mut assets=Vec::new();let mut seen=BTreeSet::new();let mut total=0u64;
        for row in rows{
            fields(row,&["relative_path","bytes","sha256"])?;let relative=text(row,"relative_path")?;
            if relative.is_empty() || relative.contains('\\') || relative.split('/').any(|c|c.is_empty() || c=="." || c==".." || c.contains(':')){return Err(bad());}
            let p=owned(&runtime,&runtime.join(relative))?;let bytes=uint(&row["bytes"])?;total=total.checked_add(bytes).ok_or_else(bad)?;
            let h=text(row,"sha256")?;hash_text(h)?;
            if !seen.insert(p.clone()) || total>256*1024*1024 {return Err(bad());}
            assets.push(Asset{path:p,bytes,sha256:h.into()});
        }
        if !seen.contains(&executable){return Err(bad());}
        let specs=v["maps"].as_array().ok_or_else(bad)?;if specs.len()!=2{return Err(bad());}
        let config_version=vehicle_profile.as_ref().map_or(1,|p|p.config_version());
        let maps=specs.iter().map(|m|MapSpec::load(&root,m,config_version)).collect::<io::Result<Vec<_>>>()?;
        if maps[0].arena_type_id==maps[1].arena_type_id || maps[0].config==maps[1].config{return Err(bad());}
        if let Some(profile)=&vehicle_profile {for map in &maps{profile.verify_map(&root,map)?;}}
        let out=Self{local_root:root,maps,sha256:format!("{:x}",Sha256::digest(&raw)),executable,runtime,assets,vehicle_profile,shared_only:pool_version==4};
        out.verify_assets()?;Ok(out)
    }
    fn angular_profile(&self,map:&MapSpec)->io::Result<ram_proof::Profile>{
        let profile=self.vehicle_profile.as_ref().ok_or_else(bad)?;
        profile.verify_map(&self.local_root,map)?;
        let selected=profile.angular_profile()?;
        for (relative,sha,bytes) in [
            ("JoltPhysicsSharp.dll","b4a700ac859c9304a7217e2ea499dec6e2b280dcad2ee02e910c4cc909f0ba67",None),
            ("runtimes/win-x64/native/joltc.dll","79125ab6882a1aeeecd5509bfe9edf383e8e48a34d9a8b642a6b9a197d44df74",Some(2013696))] {
            let expected=self.runtime.join(relative);
            if !self.assets.iter().any(|a|a.path==expected&&a.sha256==sha&&bytes.is_none_or(|n|a.bytes==n)){return Err(bad());}
        }
        Ok(selected)
    }
    /// Version4 is metadata for IPC7 only; it never authorizes the independent worker.
    pub fn shared_only(&self)->bool{self.shared_only}
    pub fn vehicle_kind(&self)->VehicleKind{self.vehicle_profile.as_ref().map_or(VehicleKind::Ms1,|p|p.kind())}
    pub fn shared_source_profile(&self)->Option<(PathBuf,String)> {self.vehicle_profile.as_ref().and_then(|p|p.shared_source_profile())}
    fn verify_assets(&self)->io::Result<()> {
        let mut found=BTreeSet::new();let mut stack=vec![self.runtime.clone()];let mut directories=0;
        while let Some(dir)=stack.pop(){directories+=1;if directories>256{return Err(bad());}non_reparse(&dir)?;
            for e in fs::read_dir(dir)?{let p=e?.path();non_reparse(&p)?;let m=fs::metadata(&p)?;
                if m.is_dir(){stack.push(p);}else if m.is_file(){found.insert(p.canonicalize()?);if found.len()>256{return Err(bad());}}else{return Err(bad());}
            }
        }
        if found!=self.assets.iter().map(|a|a.path.clone()).collect(){return Err(bad());}
        for a in &self.assets{if file_hash(&a.path,a.bytes)?!=a.sha256{return Err(bad());}}
        Ok(())
    }
}

/// `speed_percent` is the #717 partial cruise stage: 100 for ordinary keys and
/// full cruise, 50 for FWD50/BCKW50, 25 for FWD25. The stage only lowers the
/// worker's speed cutoff; it is never a client speed or position.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct Input {pub throttle:i8,pub steer:i8,pub brake:bool,pub speed_percent:u8}
impl Input {pub const STOP:Self=Self{throttle:0,steer:0,brake:true,speed_percent:100};}
pub fn partial_cruise_valid(throttle:i8,brake:bool,speed_percent:u8)->bool{
    match speed_percent{100=>true,50=>!brake && throttle!=0,25=>!brake && throttle==1,_=>false}
}
pub fn request(seq:u32,input:Input)->io::Result<Vec<u8>> {
    if seq==0 || seq>MAX_SEQUENCE || !(-1..=1).contains(&input.throttle) || !(-1..=1).contains(&input.steer)
        || (input.brake && (input.throttle!=0 || input.steer!=0))
        || !partial_cruise_valid(input.throttle,input.brake,input.speed_percent){return Err(bad());}
    // Full-speed requests keep the original exact three-field input bytes.
    let mut controls=serde_json::json!({"throttle":input.throttle,"steer":input.steer,"brake":input.brake});
    if input.speed_percent!=100{controls["speed_percent"]=input.speed_percent.into();}
    let mut b=serde_json::to_vec(&serde_json::json!({"version":1,"op":"advance","seq":seq,"ticks":6,
        "input":controls})).map_err(|_|bad())?;
    if b.len()>1024{return Err(bad());}b.push(b'\n');Ok(b)
}
fn request_scene(seq:u32,input:Input,scene:u32)->io::Result<Vec<u8>>{
    if scene>1{return Err(bad());}let mut v=json(&request(seq,input)?,1024)?;
    v["version"]=2.into();v["scene_version"]=scene.into();ipc_bytes(&v)
}
fn ipc_bytes(v:&Value)->io::Result<Vec<u8>>{
    let mut raw=serde_json::to_vec(v).map_err(|_|bad())?;if raw.len()>MAX_IPC_LINE{return Err(bad());}raw.push(b'\n');Ok(raw)
}
fn removal_request(map:&MapSpec,spec:&RemovalSpec,generation:u32,seq:u32)->io::Result<Vec<u8>>{
    if generation==0 || seq>MAX_SEQUENCE{return Err(bad());}
    ipc_bytes(&serde_json::json!({"version":2,"op":"remove_one","mutation_seq":1,"expected_scene_version":0,"scene_version":1,
        "generation":generation,"object_id":1,"object_revision":REMOVAL_REVISION,"descriptor_sha256":spec.sha256,
        "config_sha256":map.config_sha256,"advance_seq":seq}))
}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct RemovalAck {pub generation:u32,pub config_sha256:String,pub descriptor_sha256:String,pub object_id:u32,
    pub object_revision:String,pub mutation_seq:u32,pub advance_seq:u32,pub tick:u32,pub scene_version:u32}
fn removal_ack(raw:&[u8],map:&MapSpec,spec:&RemovalSpec,generation:u32,seq:u32)->io::Result<RemovalAck>{
    if !raw.is_ascii() || generation==0 || seq>MAX_SEQUENCE{return Err(bad());}let v=json(raw,1024)?;
    fields(&v,&["version","event","mutation_seq","advance_seq","tick","generation","config_sha256","descriptor_sha256",
        "object_id","object_revision","scene_version"])?;
    if uint(&v["version"])?!=2 || text(&v,"event")?!="removed" || uint(&v["mutation_seq"])?!=1
        || uint(&v["advance_seq"])?!=seq as u64 || uint(&v["tick"])?!=180+seq as u64*6
        || uint(&v["generation"])?!=generation as u64 || text(&v,"config_sha256")?!=map.config_sha256
        || text(&v,"descriptor_sha256")?!=spec.sha256 || uint(&v["object_id"])?!=1 || text(&v,"object_revision")?!=REMOVAL_REVISION
        || uint(&v["scene_version"])?!=1{return Err(bad());}
    Ok(RemovalAck{generation,config_sha256:map.config_sha256.clone(),descriptor_sha256:spec.sha256.clone(),object_id:1,
        object_revision:REMOVAL_REVISION.into(),mutation_seq:1,advance_seq:seq,tick:180+seq*6,scene_version:1})
}
#[derive(Clone,Debug,PartialEq)]
pub struct ObjectContact {pub object_id:u32,pub kind:String,pub substep:u8,pub point:[f32;3],pub normal:[f32;3],pub velocity:[f32;3]}
/// IPC7 uses exactly the accepted IPC6 scalar proof parser and verifier.
pub(crate) fn shared_angular_proof(state:&Value,contacts:&[ObjectContact],spec:&CatalogSpec,profile:ram_proof::Profile,seq:u32)->io::Result<Arc<ram_proof::FrameProof>> {
    angular::parse(state,contacts,spec,profile,seq)
}
#[derive(Clone,Debug,PartialEq)]
pub struct Pose {pub position:[f32;3],pub direction:[f32;3],pub speed:f32,pub rspeed:f32,pub contacts:u8,
    pub linear_velocity:[f32;3],pub angular_velocity:[f32;3],pub wheel_contact_masks:[u8;6]}
#[derive(Clone,Debug,PartialEq)]
pub struct State {pub seq:u32,pub tick:u32,pub pose:Pose,pub scene_version:u32,pub object_contacts:Vec<ObjectContact>,pub fractures:Vec<FractureReceipt>,pub angular_proof:Option<Arc<ram_proof::FrameProof>>}
pub fn response(raw:&[u8],map:&MapSpec,seq:u32)->io::Result<State>{
    response_at_spawn(raw,map,seq,None)
}
pub fn response_at_spawn(raw:&[u8],map:&MapSpec,seq:u32,expected_spawn:Option<[f32;3]>)->io::Result<State>{
    response_context(raw,map,seq,expected_spawn,None)
}
fn response_context(raw:&[u8],map:&MapSpec,seq:u32,expected_spawn:Option<[f32;3]>,removal:Option<(&RemovalSpec,u32,u32)>)->io::Result<State>{
    if !raw.is_ascii(){return Err(bad());}let v=json(raw,1024)?;
    let scene_version=if let Some((spec,generation,scene))=removal{
        fields(&v,&["version","event","seq","tick","settle_ticks","map","config_sha256","state","generation","descriptor_sha256","object_id","object_revision","scene_version"])?;
        if generation==0 || scene>1 || (seq==0 && scene!=0) || uint(&v["generation"])?!=generation as u64 || text(&v,"descriptor_sha256")?!=spec.sha256
            || uint(&v["object_id"])?!=1 || text(&v,"object_revision")?!=REMOVAL_REVISION || uint(&v["scene_version"])?!=scene as u64{return Err(bad());}scene
    }else{fields(&v,&["version","event","seq","tick","settle_ticks","map","config_sha256","state"])?;0};
    if uint(&v["version"])?!=if removal.is_some(){2}else{1} || text(&v,"event")?!=if seq==0{"ready"}else{"state"}
        || uint(&v["seq"])?!=seq as u64 || seq>MAX_SEQUENCE || uint(&v["tick"])?!=180+seq as u64*6
        || uint(&v["settle_ticks"])?!=180 || text(&v,"map")?!=map.asset || text(&v,"config_sha256")?!=map.config_sha256{return Err(bad());}
    let s=&v["state"];fields(s,&["position","direction","speed","rspeed","contacts","linear_velocity","angular_velocity","wheel_contact_masks"])?;
    let contacts=uint(&s["contacts"])?;if contacts>6{return Err(bad());}
    let masks=s["wheel_contact_masks"].as_array().ok_or_else(bad)?;if masks.len()!=6{return Err(bad());}
    let mut wheel_contact_masks=[0;6];for (i,v) in masks.iter().enumerate(){let n=uint(v)?;if n>63{return Err(bad());}wheel_contact_masks[i]=n as u8;}
    if wheel_contact_masks[5].count_ones() as u64!=contacts{return Err(bad());}
    let pose=Pose{position:vector(&s["position"],-2000.,2000.)?,direction:vector(&s["direction"],-std::f32::consts::PI,std::f32::consts::PI)?,
        speed:number(&s["speed"],-25.,25.)?,rspeed:number(&s["rspeed"],-20.,20.)?,contacts:contacts as u8,
        linear_velocity:vector(&s["linear_velocity"],-25.,25.)?,angular_velocity:vector(&s["angular_velocity"],-20.,20.)?,wheel_contact_masks};
    if pose.position[0]<map.bounds[0]-2. || pose.position[0]>map.bounds[2]+2. || pose.position[2]<map.bounds[1]-2.
        || pose.position[2]>map.bounds[3]+2. || !(-105. ..=505.).contains(&pose.position[1]) {return Err(bad());}
    if seq==0 {
        let spawn=expected_spawn.unwrap_or(map.spawn);
        if contacts<3 || pose.linear_velocity.iter().map(|v|v*v).sum::<f32>()>1.001
            || (pose.position[0]-spawn[0]).abs()>5. || (pose.position[2]-spawn[2]).abs()>5. { return Err(bad()); }
    }
    Ok(State{seq,tick:180+seq*6,pose,scene_version,object_contacts:Vec::new(),fractures:Vec::new(),angular_proof:None})
}
fn line(reader:&mut impl Read)->io::Result<Vec<u8>> {line_with_limit(reader,MAX_IPC_LINE)}
fn line_with_limit(reader:&mut impl Read,limit:usize)->io::Result<Vec<u8>> {
    let mut raw=Vec::new();loop{let mut b=[0];if reader.read(&mut b)?!=1{return Err(bad());}
        if b[0]==10{return Ok(raw);}if raw.len()>=limit || b[0]==0 || b[0]>127{return Err(bad());}raw.push(b[0]);}
}

enum Event {Line(Instant,Vec<u8>),Failed}
#[derive(Clone,Copy)]
enum Pending {Advance(u32,Instant),Remove(u32,Instant),Catalog(u32,Instant)}
impl Pending {fn sent(self)->Instant{match self{Self::Advance(_,sent)|Self::Remove(_,sent)|Self::Catalog(_,sent)=>sent}}}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
struct ExitEvidence {forced:bool,code:Option<i32>,reaped:bool}
fn reap_owned(mut child:Child,generation:u32,exit:Arc<Mutex<Option<ExitEvidence>>>) {
    let pid=child.id();let until=Instant::now()+Duration::from_secs(1);
    let result=loop{match child.try_wait(){
        Ok(Some(s))=>break ExitEvidence{forced:false,code:s.code(),reaped:true},
        Ok(None) if Instant::now()<until=>thread::sleep(Duration::from_millis(10)),
        _=>{let _=child.kill();break match child.wait(){
            Ok(s)=>ExitEvidence{forced:true,code:s.code(),reaped:true},
            Err(_)=>ExitEvidence{forced:true,code:None,reaped:false},
        };}
    }};
    println!("MAP_DRIVE_WORKER_EXIT generation={generation} pid={pid} forced={} code={:?} reaped={}",result.forced,result.code,result.reaped);
    if let Ok(mut e)=exit.lock(){*e=Some(result);}
}
/// Handles live outside Session's receive clone. No process side effects happen
/// while authenticating a compound packet. Drop revokes and reaps this generation.
pub struct Worker {pub generation:u32,pub map:MapSpec,receiver:mpsc::Receiver<Event>,sender:Option<mpsc::SyncSender<Vec<u8>>>,
    child:Arc<Mutex<Option<Child>>>,exit:Arc<Mutex<Option<ExitEvidence>>>,cancel:Arc<AtomicBool>,started:Instant,
    expected_spawn:Option<[f32;3]>,pending:Option<Pending>,ready:bool,last_seq:u32,
    removal:Option<RemovalSpec>,scene_version:u32,removal_ack:Option<RemovalAck>,
    catalog:Option<CatalogSpec>,catalog_scene:Option<Scene>,pending_scene:Option<Scene>,catalog_ack:Option<CatalogAck>,prepared_ids:Vec<u32>,angular_profile:Option<ram_proof::Profile>}
impl Worker {
    pub fn launch(pool:Arc<Pool>,map:MapSpec,generation:u32,now:Instant)->io::Result<Self>{
        Self::launch_at_spawn(pool,map,generation,now,None)
    }
    pub fn launch_at_spawn(pool:Arc<Pool>,map:MapSpec,generation:u32,now:Instant,spawn:Option<[f32;3]>)->io::Result<Self>{
        Self::launch_inner(pool,map,generation,now,spawn,None,None)
    }
    pub fn launch_with_removal(pool:Arc<Pool>,map:MapSpec,generation:u32,now:Instant,spawn:Option<[f32;3]>,spec:RemovalSpec)->io::Result<Self>{
        spec.verify(&pool.local_root,&map)?;
        Self::launch_inner(pool,map,generation,now,spawn,Some(spec),None)
    }
    pub fn launch_with_catalog(pool:Arc<Pool>,map:MapSpec,generation:u32,now:Instant,spawn:Option<[f32;3]>,spec:CatalogSpec,initial_scene:Scene)->io::Result<Self>{
        spec.verify(&pool.local_root,&map)?;initial_scene.validate(&spec)?;
        Self::launch_inner(pool,map,generation,now,spawn,None,Some((spec,initial_scene)))
    }
    fn launch_inner(pool:Arc<Pool>,map:MapSpec,generation:u32,now:Instant,spawn:Option<[f32;3]>,removal:Option<RemovalSpec>,initial:Option<(CatalogSpec,Scene)>)->io::Result<Self>{
        if pool.shared_only {return Err(io::Error::new(io::ErrorKind::InvalidInput,
            "extended shared-only pool requires IPC7 SceneManifest3"));}
        if let Some(profile)=&pool.vehicle_profile{profile.verify_map(&pool.local_root,&map)?;}
        let angular_profile=if initial.as_ref().is_some_and(|(s,_)|s.version()==8){Some(pool.angular_profile(&map)?)}else{None};
        if generation==0{return Err(bad());}
        if removal.is_some() && initial.is_some(){return Err(bad());}
        if let Some(target)=spawn {
            if target.iter().any(|v| !v.is_finite()) || (target[1]-map.spawn[1]).abs()>f32::EPSILON
                || target[0]<map.bounds[0]+5. || target[0]>map.bounds[2]-5.
                || target[2]<map.bounds[1]+5. || target[2]>map.bounds[3]-5.
                || (target[0]-map.spawn[0]).abs()>12. || (target[2]-map.spawn[2]).abs()>12. { return Err(bad()); }
        }
        let (events,receiver)=mpsc::sync_channel(4);let (sender,commands)=mpsc::sync_channel::<Vec<u8>>(1);
        if let Some((spec,scene))=&initial {
            // Queued before the process starts; IPC3 reads this BEFORE settle.
            sender.try_send(catalog::scene_request(&map,spec,generation,0,scene,true)?).map_err(|_|bad())?;
        }
        let child=Arc::new(Mutex::new(None::<Child>));let cancel=Arc::new(AtomicBool::new(false));
        let exit=Arc::new(Mutex::new(None));let exit_thread=exit.clone();
        let slot=child.clone();let revoked=cancel.clone();let selected=map.clone();let removal_thread=removal.clone();
        let catalog_thread=initial.as_ref().map(|(spec,_)|spec.clone());
        #[cfg(test)] let capture=real_test_capture::lookup(&selected.config_sha256,generation)?;
        thread::spawn(move||{
            #[cfg(test)] let _reader_complete=match real_test_capture::completion(&capture,0){
                Ok(guard)=>guard,Err(_)=>{let _=events.try_send(Event::Failed);return;}
            };
            let run=||->io::Result<()> {
                pool.verify_assets()?;owned(&pool.local_root,&selected.config)?;let raw=read(&selected.config,16384)?;
                if format!("{:x}",Sha256::digest(&raw))!=selected.config_sha256 || revoked.load(Ordering::SeqCst){return Err(bad());}
                let mut cmd=Command::new(&pool.executable);
                cmd.args(["--local-root"]).arg(worker_path_argument(&pool.local_root)?).arg("--config").arg(worker_path_argument(&selected.config)?)
                    .arg("--config-sha256").arg(&selected.config_sha256).current_dir(&pool.runtime)
                    .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped());
                if let Some(target)=spawn {
                    cmd.arg("--spawn-xz").arg(target[0].to_string()).arg(target[2].to_string());
                }
                if let Some(spec)=removal_thread.as_ref(){
                    spec.verify(&pool.local_root,&selected)?;
                    cmd.arg("--remove-one").arg(worker_path_argument(&spec.path)?).arg("--remove-one-sha256").arg(&spec.sha256)
                        .arg("--generation").arg(generation.to_string());
                }
                if let Some(spec)=catalog_thread.as_ref(){
                    spec.verify(&pool.local_root,&selected)?;
                    cmd.arg("--destructible-catalog").arg(worker_path_argument(&spec.path)?).arg("--catalog-sha256").arg(&spec.sha256)
                        .arg("--generation").arg(generation.to_string());
                }
                #[cfg(windows)] {use std::os::windows::process::CommandExt;cmd.creation_flags(0x08000000);}
                let mut c=cmd.spawn()?;let mut input=c.stdin.take().ok_or_else(bad)?;
                let mut output=c.stdout.take().ok_or_else(bad)?;let mut errors=c.stderr.take().ok_or_else(bad)?;
                {let mut guard=slot.lock().map_err(|_|bad())?;if revoked.load(Ordering::SeqCst){drop(input);reap_owned(c,generation,exit_thread.clone());return Err(bad());}*guard=Some(c);}
                let e=events.clone();let stopped=revoked.clone();
                #[cfg(test)] let writes=capture.clone();
                #[cfg(test)] let writer_complete=real_test_capture::completion(&writes,1)?;
                thread::spawn(move||{
                    #[cfg(test)] let _writer_complete=writer_complete;
                    while let Ok(bytes)=commands.recv(){if stopped.load(Ordering::SeqCst){break;}
                    if input.write_all(&bytes).and_then(|_|input.flush()).is_err(){
                        #[cfg(test)] real_test_capture::error(&writes,"actual stdin write/flush failed");
                        let _=e.try_send(Event::Failed);break;}
                    #[cfg(test)] if real_test_capture::record(&writes,true,&bytes).is_err(){let _=e.try_send(Event::Failed);break;}
                }});
                #[cfg(test)] let err_capture=capture.clone();
                #[cfg(test)] let stderr_complete=real_test_capture::completion(&err_capture,2)?;
                let e=events.clone();thread::spawn(move||{
                    #[cfg(test)] let _stderr_complete=stderr_complete;
                    let mut b=[0;1024];let mut size=0usize;
                    loop {match errors.read(&mut b){Ok(0)=>break,Ok(n)=>{
                        #[cfg(test)] if real_test_capture::stderr(&err_capture,&b[..n]).is_err(){let _=e.try_send(Event::Failed);break;}
                        let keep=n.min(4096-size);let value=String::from_utf8_lossy(&b[..keep]);
                        println!("MAP_DRIVE_WORKER_STDERR generation={generation} bytes={keep} truncated={} text={}",keep<n,serde_json::to_string(&value).unwrap_or_else(|_|"\"diagnostic_encoding_error\"".into()));
                        size+=keep;let _=e.try_send(Event::Failed);if size>=4096{break;}
                    },Err(_)=>{
                        #[cfg(test)] real_test_capture::error(&err_capture,"actual stderr read failed");
                        let _=e.try_send(Event::Failed);break;}}}
                });
                let line_limit=catalog_thread.as_ref().map_or(MAX_IPC_LINE,CatalogSpec::line_limit);
                loop {let raw=line_with_limit(&mut output,line_limit)?;
                    #[cfg(test)] real_test_capture::record(&capture,false,&raw)?;
                    if revoked.load(Ordering::SeqCst){
                        // Selected test captures drain complete final payloads to EOF.
                        // Release binaries retain the original immediate cancellation.
                        #[cfg(test)] if capture.is_some(){continue;}
                        break;
                    }
                    events.try_send(Event::Line(Instant::now(),raw)).map_err(|_|bad())?;}
                Ok(())
            };
            if let Err(error)=run(){if !revoked.load(Ordering::SeqCst){
                #[cfg(test)] real_test_capture::error(&capture,&format!("actual IPC thread: {error}"));
                let message=error.to_string().chars().take(1024).collect::<String>();
                println!("MAP_DRIVE_WORKER_IO_ERROR generation={generation} kind={:?} message={}",error.kind(),serde_json::to_string(&message).unwrap_or_else(|_|"\"diagnostic_encoding_error\"".into()));
                let _=events.try_send(Event::Failed);
            }}
        });
        let (catalog,catalog_scene)=initial.map(|(spec,scene)|(Some(spec),Some(scene))).unwrap_or((None,None));
        Ok(Self{generation,map,receiver,sender:Some(sender),child,exit,cancel,started:now,expected_spawn:spawn,
            pending:None,ready:false,last_seq:0,removal,scene_version:0,removal_ack:None,
            catalog,catalog_scene,pending_scene:None,catalog_ack:None,prepared_ids:Vec::new(),angular_profile})
    }
    pub fn pending(&self)->bool{self.pending.is_some()}
    pub fn prepared_ids(&self)->&[u32]{&self.prepared_ids}
    pub fn ready(&self)->bool{self.ready}
    pub fn process_id(&self)->Option<u32>{self.child.lock().ok().and_then(|c|c.as_ref().map(Child::id))}
    #[cfg(test)]
    pub(crate) fn exit_observer(&self)->impl Fn()->Option<(bool,Option<i32>,bool)>+'static {
        let exit=self.exit.clone();
        move||exit.lock().unwrap().as_ref().map(|e|(e.forced,e.code,e.reaped))
    }
    pub fn scene_version(&self)->u32{self.scene_version}
    pub fn take_removal_ack(&mut self)->Option<RemovalAck>{self.removal_ack.take()}
    pub fn take_catalog_ack(&mut self)->Option<CatalogAck>{self.catalog_ack.take()}
    /// None until ready confirms the bootstrap was applied before settle.
    pub fn catalog_scene(&self)->Option<&Scene>{if self.ready{self.catalog_scene.as_ref()}else{None}}
    pub fn sync_removed(&mut self,scene:Scene,now:Instant)->io::Result<()>{
        if !self.ready || self.pending.is_some() || self.removal_ack.is_some() || self.catalog_ack.is_some() || now<self.started{return Err(bad());}
        let spec=self.catalog.as_ref().ok_or_else(bad)?;scene.validate(spec)?;
        if !scene.extends(self.catalog_scene.as_ref().ok_or_else(bad)?){return Err(bad());}
        if self.prepared_ids.iter().any(|id|scene.ids().binary_search(id).is_err()){return Err(bad());}
        let raw=catalog::scene_request(&self.map,spec,self.generation,self.last_seq,&scene,false)?;
        self.sender.as_ref().ok_or_else(bad)?.try_send(raw).map_err(|_|bad())?;
        self.pending_scene=Some(scene);self.pending=Some(Pending::Catalog(self.last_seq,now));Ok(())
    }
    /// One outstanding operation only. The caller must stop both arena lanes
    /// and commit the domain change only after checking BOTH workers' ACKs.
    pub fn remove_one(&mut self,now:Instant)->io::Result<()>{
        if !self.ready || self.pending.is_some() || self.removal_ack.is_some() || self.catalog_ack.is_some() || now<self.started{return Err(bad());}
        let spec=self.removal.as_ref().ok_or_else(bad)?;
        let raw=removal_request(&self.map,spec,self.generation,self.last_seq)?;
        self.sender.as_ref().ok_or_else(bad)?.try_send(raw).map_err(|_|bad())?;
        self.pending=Some(Pending::Remove(self.last_seq,now));Ok(())
    }
    pub fn advance(&mut self,input:Input,now:Instant)->io::Result<u32>{
        if !self.ready || self.pending.is_some() || self.removal_ack.is_some() || self.catalog_ack.is_some() || !self.prepared_ids.is_empty() || now<self.started || self.last_seq>=MAX_SEQUENCE{return Err(bad());}
        let seq=self.last_seq+1;let raw=if let Some(scene)=&self.catalog_scene{catalog::request_catalog(seq,input,scene,self.catalog.as_ref().ok_or_else(bad)?)?}
            else if self.removal.is_some(){request_scene(seq,input,self.scene_version)?}else{request(seq,input)?};
        self.sender.as_ref().ok_or_else(bad)?.try_send(raw).map_err(|_|bad())?;
        self.pending=Some(Pending::Advance(seq,now));Ok(seq)
    }
    pub fn poll(&mut self,now:Instant)->io::Result<Option<State>>{
        if now<self.started || (!self.ready && now.duration_since(self.started)>START_TIMEOUT)
            || self.pending.is_some_and(|pending|now<pending.sent() || now.duration_since(pending.sent())>REPLY_TIMEOUT){return Err(bad());}
        match self.receiver.try_recv(){
            Ok(Event::Failed)|Err(mpsc::TryRecvError::Disconnected)=>Err(bad()),
            Err(mpsc::TryRecvError::Empty)=>Ok(None),
            Ok(Event::Line(received,raw))=>{
                let seq=if !self.ready {0}else{
                    let pending=self.pending.ok_or_else(bad)?;if received<pending.sent(){return Err(bad());}
                    match pending {
                        Pending::Advance(seq,_)=>seq,
                        Pending::Remove(seq,_)=>{
                            let ack=removal_ack(&raw,&self.map,self.removal.as_ref().ok_or_else(bad)?,self.generation,seq)?;
                            self.scene_version=1;self.removal_ack=Some(ack);self.pending=None;return Ok(None);
                        }
                        Pending::Catalog(seq,_)=>{
                            let scene=self.pending_scene.as_ref().ok_or_else(bad)?;
                            let ack=catalog::ack(&raw,&self.map,self.catalog.as_ref().ok_or_else(bad)?,self.generation,seq,scene)?;
                            self.scene_version=scene.version();self.catalog_scene=self.pending_scene.take();
                            self.prepared_ids.clear();
                            self.catalog_ack=Some(ack);self.pending=None;return Ok(None);
                        }
                    }
                };
                let context=self.removal.as_ref().map(|spec|(spec,self.generation,self.scene_version));
                let state=if let Some(spec)=&self.catalog{catalog::response_with_profile(&raw,&self.map,spec,self.generation,seq,self.expected_spawn,self.catalog_scene.as_ref().ok_or_else(bad)?,self.angular_profile)?}
                    else{response_context(&raw,&self.map,seq,self.expected_spawn,context)?};
                if !self.prepared_ids.is_empty(){return Err(bad());}
                #[cfg(test)] real_test_capture::parsed(&self.map.config_sha256,self.generation,&state)?;
                self.prepared_ids=state.fractures.iter().map(|receipt|receipt.object_id).collect();
                self.prepared_ids.sort_unstable();
                self.scene_version=state.scene_version;self.ready=true;self.last_seq=seq;self.pending=None;Ok(Some(state))
            },
        }
    }
}
impl Drop for Worker {
    fn drop(&mut self){self.cancel.store(true,Ordering::SeqCst);self.sender.take();
        if let Ok(mut guard)=self.child.lock(){if let Some(child)=guard.take(){
            // Revoke authority immediately; closing our stdin lets the owned
            // worker dispose its arena normally. A stuck child is killed/reaped
            // after a bounded grace period off the UDP loop.
            let exit=self.exit.clone();let generation=self.generation;thread::spawn(move||reap_owned(child,generation,exit));
        }}
    }
}

/// Controlled, bounded IPC endpoints for coordinator ordering tests. There is
/// no child process: requests, poll consumption and response validation still
/// use the production Worker methods. This is not native/physics acceptance.
#[cfg(test)]
pub(crate) mod controlled_ipc {
    use super::*;
    pub(crate) struct Peer {
        replies: mpsc::SyncSender<Event>,
        requests: mpsc::Receiver<Vec<u8>>,
    }
    impl Peer {
        pub(crate) fn reply(&self, now: Instant, value: &Value) {
            self.replies.try_send(Event::Line(now, serde_json::to_vec(value).unwrap())).unwrap();
        }
        pub(crate) fn request(&self) -> Value {
            serde_json::from_slice(&self.requests.try_recv().unwrap()).unwrap()
        }
        pub(crate) fn no_request(&self) -> bool {
            matches!(self.requests.try_recv(), Err(mpsc::TryRecvError::Empty))
        }
    }
    pub(crate) fn pool(map: MapSpec) -> Arc<Pool> {
        Arc::new(Pool { local_root: PathBuf::new(), maps: vec![map], sha256: "0".repeat(64),
            executable: PathBuf::new(), runtime: PathBuf::new(), assets: Vec::new(), vehicle_profile: None, shared_only:false })
    }
    pub(crate) fn angular_fixture(name:&str)->(Value,CatalogSpec,Arc<crate::gateway091::shared::fragiles::Catalog>,ram_proof::Profile){angular::tests::bound(name)}
    pub(crate) fn angular_pool(map:MapSpec,profile:ram_proof::Profile)->Arc<Pool>{
        let mut p=Arc::try_unwrap(pool(map)).ok().unwrap();p.vehicle_profile=Some(profile::component_profile(profile));Arc::new(p)
    }
    pub(crate) fn angular_ready(map:MapSpec,generation:u32,spec:CatalogSpec,scene:Scene,now:Instant,profile:ram_proof::Profile)->(Worker,Peer){
        assert_eq!(spec.version(),8);assert_eq!(map.mass_kg.to_bits(),profile.mass().to_bits());
        let(mut worker,peer)=ready(map,generation,spec,scene,now);worker.angular_profile=Some(profile);(worker,peer)
    }
    pub(crate) fn ready(map: MapSpec, generation: u32, spec: CatalogSpec, scene: Scene,
        now: Instant) -> (Worker, Peer) {
        let (replies, receiver) = mpsc::sync_channel(2);
        let (sender, requests) = mpsc::sync_channel(2);
        let worker = Worker { generation, map, receiver, sender: Some(sender),
            child: Arc::new(Mutex::new(None)), exit: Arc::new(Mutex::new(None)),
            cancel: Arc::new(AtomicBool::new(false)), started: now, expected_spawn: None,
            pending: None, ready: true, last_seq: 0, removal: None, scene_version: scene.version(),
            removal_ack: None, catalog: Some(spec), catalog_scene: Some(scene),
            pending_scene: None, catalog_ack: None, prepared_ids: Vec::new(), angular_profile:None };
        (worker, Peer { replies, requests })
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    pub(crate) fn map()->MapSpec{MapSpec{asset:"01_karelia".into(),arena_type_id:1,config:"unit".into(),config_sha256:"a".repeat(64),bounds:[-500.,-500.,500.,500.],spawn:[0.,10.,0.],spawn_yaw:0.,mass_kg:4691.}}
    fn good(seq:u32)->Value{serde_json::json!({"version":1,"event":if seq==0{"ready"}else{"state"},"seq":seq,"tick":180+seq*6,"settle_ticks":180,"map":"01_karelia","config_sha256":"a".repeat(64),
        "state":{"position":[0,10,0],"direction":[0,0,0],"speed":0,"rspeed":0,"contacts":6,"linear_velocity":[0,0,0],"angular_velocity":[0,0,0],"wheel_contact_masks":[63,63,63,63,63,63]}})}
    fn spec()->RemovalSpec{RemovalSpec{path:"unit".into(),sha256:"b".repeat(64)}}
    fn descriptor()->Value{serde_json::json!({"version":1,"profile":"test_lab","map":"01_karelia","object_id":1,"instance_id":1513,
        "physics_manifest_sha256":PHYSICS_MANIFEST,"projectile_manifest_sha256":PROJECTILE_MANIFEST,"first_triangle":171814,
        "triangle_count":42,"object_revision":REMOVAL_REVISION})}
    fn good_scene(seq:u32,scene:u32)->Value{
        let mut v=good(seq);v["version"]=2.into();v["generation"]=1.into();v["descriptor_sha256"]=spec().sha256.into();
        v["object_id"]=1.into();v["object_revision"]=REMOVAL_REVISION.into();v["scene_version"]=scene.into();v
    }
    fn good_ack(seq:u32)->Value{serde_json::json!({"version":2,"event":"removed","mutation_seq":1,"advance_seq":seq,"tick":180+seq*6,
        "generation":1,"config_sha256":"a".repeat(64),"descriptor_sha256":"b".repeat(64),"object_id":1,
        "object_revision":REMOVAL_REVISION,"scene_version":1})}
    #[test]fn removal_descriptor_pins_exact_object_source_span_and_file_hash(){
        RemovalSpec::validate(&descriptor()).unwrap();
        for (key,value) in [("object_id",2.into()),("instance_id",1512.into()),("first_triangle",171813.into()),("triangle_count",41.into()),
            ("physics_manifest_sha256","0".repeat(64).into()),("projectile_manifest_sha256","0".repeat(64).into()),
            ("map","05_prohorovka".into()),("profile","production".into()),("object_revision","other".into()),("version",1.0.into())]{
            let mut v=descriptor();v[key]=value;assert!(RemovalSpec::validate(&v).is_err(),"{key}");
        }
        let root=scratch();let path=root.join("remove.json");let raw=serde_json::to_vec(&descriptor()).unwrap();fs::write(&path,&raw).unwrap();
        let hash=format!("{:x}",Sha256::digest(&raw));let s=RemovalSpec::load(&root,&path,&hash).unwrap();assert_eq!(s.sha256(),hash);
        assert!(RemovalSpec::load(&root,&path,&"0".repeat(64)).is_err());
        assert!(RemovalSpec::load(&root,Path::new("remove.json"),&hash).is_err());
        let mut changed=descriptor();changed["instance_id"]=1512.into();fs::write(&path,serde_json::to_vec(&changed).unwrap()).unwrap();
        assert!(RemovalSpec::load(&root,&path,&hash).is_err());
    }
    #[test]fn removal_ack_and_scene_state_require_every_pin_and_unchanged_tick(){
        let s=spec();let m=map();let v=good_ack(7);let raw=serde_json::to_vec(&v).unwrap();
        let ack=removal_ack(&raw,&m,&s,1,7).unwrap();assert_eq!((ack.advance_seq,ack.tick,ack.scene_version),(7,222,1));
        for (key,value) in [("version",1.into()),("event","state".into()),("generation",2.into()),("advance_seq",8.into()),("tick",228.into()),
            ("mutation_seq",2.into()),("scene_version",0.into()),("object_id",2.into()),("object_revision","other".into()),
            ("descriptor_sha256","c".repeat(64).into()),("config_sha256","c".repeat(64).into())]{
            let mut changed=v.clone();changed[key]=value;assert!(removal_ack(&serde_json::to_vec(&changed).unwrap(),&m,&s,1,7).is_err(),"{key}");
        }
        assert!(removal_ack(&raw,&m,&s,2,7).is_err());assert!(removal_ack(&raw,&m,&s,1,8).is_err());
        let raw=serde_json::to_vec(&good_scene(1,1)).unwrap();
        assert_eq!(response_context(&raw,&m,1,None,Some((&s,1,1))).unwrap().scene_version,1);
        assert!(response_context(&raw,&m,1,None,Some((&s,1,0))).is_err());assert!(response(&raw,&m,1).is_err());
        assert!(response_context(&serde_json::to_vec(&good(1)).unwrap(),&m,1,None,Some((&s,1,0))).is_err());
        assert!(response_context(&serde_json::to_vec(&good_scene(0,1)).unwrap(),&m,0,None,Some((&s,1,1))).is_err());
    }
    #[test]fn removal_transaction_blocks_advances_consumes_no_tick_and_retries_idempotently(){
        let now=Instant::now();let(mut w,send,recv)=fake_worker(now);w.removal=Some(spec());
        assert!(w.remove_one(now).is_err());
        send.send(Event::Line(now,serde_json::to_vec(&good_scene(0,0)).unwrap())).unwrap();w.poll(now).unwrap();
        for expected_seq in [0,1]{
            w.remove_one(now).unwrap();let request=json(&recv.recv().unwrap(),1024).unwrap();
            assert_eq!(request["advance_seq"],expected_seq);assert_eq!(request["mutation_seq"],1);
            assert!(w.remove_one(now).is_err());assert!(w.advance(Input::STOP,now).is_err());
            send.send(Event::Line(now,serde_json::to_vec(&good_ack(expected_seq)).unwrap())).unwrap();
            assert_eq!(w.poll(now).unwrap(),None);assert_eq!(w.scene_version(),1);assert_eq!(w.last_seq,expected_seq);
            assert!(w.advance(Input::STOP,now).is_err());let ack=w.take_removal_ack().unwrap();
            assert_eq!(ack.advance_seq,expected_seq);assert!(w.take_removal_ack().is_none());
            let next=w.advance(Input::STOP,now).unwrap();let request=json(&recv.recv().unwrap(),1024).unwrap();
            assert_eq!(request["version"],2);assert_eq!(request["scene_version"],1);assert_eq!(next,expected_seq+1);
            send.send(Event::Line(now,serde_json::to_vec(&good_scene(next,1)).unwrap())).unwrap();assert_eq!(w.poll(now).unwrap().unwrap().seq,next);
        }
        send.send(Event::Line(now,serde_json::to_vec(&good_ack(2)).unwrap())).unwrap();assert!(w.poll(now).is_err());
    }
    #[test]fn failed_removal_reply_cannot_publish_scene_or_ack_and_timeout_is_fatal(){
        for mode in 0..5{
            let now=Instant::now();let(mut w,send,recv)=fake_worker(now);w.removal=Some(spec());w.ready=true;
            w.remove_one(now).unwrap();recv.recv().unwrap();
            match mode{
                0=>{let mut v=good_ack(0);v["generation"]=2.into();send.send(Event::Line(now,serde_json::to_vec(&v).unwrap())).unwrap();},
                1=>{send.send(Event::Line(now,serde_json::to_vec(&good_scene(1,1)).unwrap())).unwrap();},
                2=>{send.send(Event::Failed).unwrap();},
                3=>{send.send(Event::Line(now-Duration::from_nanos(1),serde_json::to_vec(&good_ack(0)).unwrap())).unwrap();},
                _=>{},
            }
            let poll_at=if mode==4{now+REPLY_TIMEOUT+Duration::from_nanos(1)}else{now};
            assert!(w.poll(poll_at).is_err());assert_eq!(w.scene_version(),0);assert!(w.take_removal_ack().is_none());assert_eq!(w.last_seq,0);
        }
        let now=Instant::now();let(mut w,_,_)=fake_worker(now);w.ready=true;assert!(w.remove_one(now).is_err());
    }
    #[test]fn recursive_duplicate_unknown_numeric_bool_and_deep_json_fail(){
        assert!(json(br#"{"a":{"x":1,"x":2}}"#,1024).is_err());
        assert!(json(format!("{}0{}","[".repeat(13),"]".repeat(13)).as_bytes(),1024).is_err());
        for key in ["version","seq","tick","settle_ticks"]{for replacement in [Value::Bool(true),Value::from(1.0)]{
            let mut v=good(0);v[key]=replacement;assert!(response(&serde_json::to_vec(&v).unwrap(),&map(),0).is_err());}}
        let mut v=good(0);v["password"]=1.into();assert!(response(&serde_json::to_vec(&v).unwrap(),&map(),0).is_err());
    }
    #[test]fn response_requires_exact_generation_map_sequence_tick_and_geometry(){
        for seq in [0,1,36000]{assert_eq!(response(&serde_json::to_vec(&good(seq)).unwrap(),&map(),seq).unwrap().seq,seq);}
        for path in ["map","config_sha256","event"]{let mut v=good(1);v[path]="wrong".into();assert!(response(&serde_json::to_vec(&v).unwrap(),&map(),1).is_err());}
        let mut v=good(1);v["tick"]=187.into();assert!(response(&serde_json::to_vec(&v).unwrap(),&map(),1).is_err());
        let mut v=good(0);v["state"]["contacts"]=2.into();assert!(response(&serde_json::to_vec(&v).unwrap(),&map(),0).is_err());
        for value in [1e99,503.0]{let mut v=good(1);v["state"]["position"][0]=value.into();assert!(response(&serde_json::to_vec(&v).unwrap(),&map(),1).is_err());}
        let mut v=good(0);v["state"]["linear_velocity"][0]=2.into();assert!(response(&serde_json::to_vec(&v).unwrap(),&map(),0).is_err());
    }
    #[test]fn response_accepts_only_the_server_owned_lane_override(){
        let mut v=good(0);
        v["state"]["position"][0]=6.into();
        v["state"]["position"][2]=6.into();
        let raw=serde_json::to_vec(&v).unwrap();
        assert!(response(&raw,&map(),0).is_err());
        assert!(response_at_spawn(&raw,&map(),0,Some([6.,10.,6.])).is_ok());
        assert!(response_at_spawn(&raw,&map(),0,Some([16.,10.,6.])).is_err());
    }
    #[test]fn request_has_only_domain_input_and_fixed_steps(){
        assert!(request(0,Input::STOP).is_err());assert!(request(36001,Input::STOP).is_err());
        for throttle in -1..=1{for steer in -1..=1{let b=request(1,Input{throttle,steer,brake:false,speed_percent:100}).unwrap();let v=json(&b,1024).unwrap();assert_eq!(v["ticks"],6);assert!(v.get("position").is_none());}}
        assert!(request(1,Input{throttle:1,steer:0,brake:true,speed_percent:100}).is_err());
        assert!(request(1,Input{throttle:0,steer:2,brake:false,speed_percent:100}).is_err());
    }
    #[test]fn partial_cruise_stage_is_additive_and_bounded(){
        // Full speed keeps the historical exact bytes and three input fields.
        assert_eq!(request(7,Input{throttle:1,steer:-1,brake:false,speed_percent:100}).unwrap(),
            b"{\"input\":{\"brake\":false,\"steer\":-1,\"throttle\":1},\"op\":\"advance\",\"seq\":7,\"ticks\":6,\"version\":1}\n".to_vec());
        for (throttle,percent) in [(1,50),(-1,50),(1,25)]{
            let v=json(&request(1,Input{throttle,steer:1,brake:false,speed_percent:percent}).unwrap(),1024).unwrap();
            assert_eq!(v["input"],serde_json::json!({"throttle":throttle,"steer":1,"brake":false,"speed_percent":percent}));
        }
        for (throttle,brake,percent) in [(-1,false,25),(0,false,50),(0,true,50),(1,false,0),(1,false,75),(1,false,101)]{
            assert!(request(1,Input{throttle,steer:0,brake,speed_percent:percent}).is_err());
        }
    }
    #[test]fn actual_packaged_pool_and_saved_worker_output_readonly_contract(){
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
        // Immutable original pool pin is verified before checkout-only relocation.
        let pool=crate::worker_fixtures091::packaged();
        assert_eq!(pool.assets.len(),16);
        let raw=read(&root.join("evidence/20261005-p02-map-drive/physics/packaged-worker-01/stdout.jsonl"),4096).unwrap();
        assert_eq!(format!("{:x}",Sha256::digest(&raw)),"49065e18200e9aa93d3c0b6ab7d2c18566aa4cbf8e0a186a9c96b911c01813f5");
        let lines=raw.split(|b|*b==10).filter(|b|!b.is_empty()).collect::<Vec<_>>();assert_eq!(lines.len(),2);
        // Archived IPC is bound to its original config, not the relocated
        // config used by the separate real-child test. Preserve both hashes.
        let mut archived_map=pool.maps.iter().find(|m|m.asset=="01_karelia").unwrap().clone();
        archived_map.config=root.join("server/map-drive/01_karelia-v1.json");
        archived_map.config_sha256=format!("{:x}",Sha256::digest(read(&archived_map.config,16384).unwrap()));
        assert_eq!(archived_map.config_sha256,"cf93c617d328865faaf93b7081eb838eb13262b12fe27b4a603e1f2a7023f4c2");
        for (i,line) in lines.iter().enumerate(){let s=response(line,&archived_map,i as u32).unwrap();assert_eq!(s.pose.contacts,5);assert_eq!(s.pose.wheel_contact_masks,[59;6]);}
    }
    #[test]fn ipc_line_refuses_eof_partial_nul_nonascii_and_overflow(){
        assert_eq!(line(&mut &b"{}\n"[..]).unwrap(),b"{}");
        for b in [vec![],b"{}".to_vec(),b"\0\n".to_vec(),vec![255,10],vec![b'x';1025]]{assert!(line(&mut b.as_slice()).is_err());}
    }

    fn scratch()->PathBuf{
        use std::sync::atomic::{AtomicUsize,Ordering};static NEXT:AtomicUsize=AtomicUsize::new(0);
        let p=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/evidence/20261005-p02-map-drive/wire/drive-integration-01/unit-files")
            .join(format!("{}-{}",std::process::id(),NEXT.fetch_add(1,Ordering::Relaxed)));
        fs::create_dir_all(&p).unwrap();p.canonicalize().unwrap()
    }
    pub(super) fn fixture_pool()->(PathBuf,PathBuf,Value){
        let root=scratch();let runtime=root.join("runtime");fs::create_dir(&runtime).unwrap();
        let exe=runtime.join("worker.exe");fs::write(&exe,b"UNIT_ONLY_NEVER_EXECUTE").unwrap();
        let manifest=serde_json::json!({"version":1,"files":[{"relative_path":"worker.exe","bytes":b"UNIT_ONLY_NEVER_EXECUTE".len(),"sha256":format!("{:x}",Sha256::digest(b"UNIT_ONLY_NEVER_EXECUTE"))}]});
        let manifest_raw=serde_json::to_vec(&manifest).unwrap();let mf=root.join("artifacts.json");fs::write(&mf,&manifest_raw).unwrap();
        let geometry=root.join("mesh.json");fs::write(&geometry,b"UNIT_ONLY_CHILD_NOT_RUN").unwrap();
        let mut rows=Vec::new();
        for (asset,id) in [("01_karelia",1),("05_prohorovka",4)]{
            let c=serde_json::json!({"version":1,"profile":"test_lab","map":asset,
                "terrain":{"path":geometry,"sha256":"b".repeat(64)},"obstacles":{"path":geometry,"sha256":"b".repeat(64)},
                "spawn_origin":[0,10,0],"spawn_yaw":0,"body_half_extents":[1,1,1],"body_center_offset":[0,0,0],
                "wheel_points":[[0,0,0],[0,0,0],[0,0,0],[0,0,0],[0,0,0],[0,0,0]],"mass_kg":6000,"max_forward_mps":8,"max_reverse_mps":4,
                "engine_max_torque_nm":100,"wheel_radius":0.3,"suspension_min":0.1,"suspension_max":0.3,"track_max_brake_torque":1000,"bounds_xz":[-500,-500,500,500]});
            let raw=serde_json::to_vec(&c).unwrap();let path=root.join(format!("{asset}.json"));fs::write(&path,&raw).unwrap();
            rows.push(serde_json::json!({"asset":asset,"arena_type_id":id,"config":path,"config_sha256":format!("{:x}",Sha256::digest(&raw))}));
        }
        let v=serde_json::json!({"version":1,"profile":"test_lab","worker":{"executable":exe,"artifact_manifest":mf,
            "artifact_manifest_sha256":format!("{:x}",Sha256::digest(&manifest_raw))},"maps":rows});
        let path=root.join("pool.json");fs::write(&path,serde_json::to_vec(&v).unwrap()).unwrap();(root,path,v)
    }
    #[test]fn pool_whole_tree_hash_no_extras_and_configuration_map_are_bound(){
        let (root,path,_)=fixture_pool();let pool=Pool::load(&root,&path).unwrap();assert_eq!(pool.maps[1].arena_type_id,4);
        let extra=root.join("runtime/unlisted.dll");fs::write(&extra,b"unit").unwrap();assert!(Pool::load(&root,&path).is_err());
        // A second independent scratch tests replacement without deleting any evidence.
        let (root,path,_)=fixture_pool();let p=Pool::load(&root,&path).unwrap();fs::write(&p.executable,b"DIFFERENT_BINARY").unwrap();assert!(p.verify_assets().is_err());
        assert!(Pool::load(&root,&path).is_err());
    }
    #[test]fn pool_wrong_map5_duplicate_config_unbounded_and_relative_paths_rejected(){
        for change in 0..6{
            let (root,path,mut v)=fixture_pool();match change{
                0=>v["maps"][1]["arena_type_id"]=5.into(),1=>v["maps"][1]=v["maps"][0].clone(),
                2=>v["worker"]["executable"]="runtime/worker.exe".into(),3=>v["maps"][0]["config_sha256"]="0".repeat(64).into(),
                4=>v["worker"]["artifact_manifest_sha256"]="0".repeat(64).into(),5=>v["maps"][0]["arena_type_id"]=1.0.into(),_=>unreachable!()}
            fs::write(&path,serde_json::to_vec(&v).unwrap()).unwrap();assert!(Pool::load(&root,&path).is_err(),"change {change}");
        }
    }
    #[test]fn contact_masks_cover_all_six_substeps_and_match_last_contacts(){
        let good=good(1);assert!(response(&serde_json::to_vec(&good).unwrap(),&map(),1).is_ok());
        for change in 0..5{let mut v=good.clone();match change{
            0=>v["state"]["wheel_contact_masks"][0]=64.into(),1=>v["state"]["wheel_contact_masks"][1]=Value::Bool(true),
            2=>v["state"]["wheel_contact_masks"][2]=63.0.into(),3=>v["state"]["contacts"]=5.into(),
            4=>v["state"]["wheel_contact_masks"].as_array_mut().unwrap().pop().map(|_|()).unwrap(),_=>unreachable!()}
            assert!(response(&serde_json::to_vec(&v).unwrap(),&map(),1).is_err());}
    }
    fn fake_worker(now:Instant)->(Worker,mpsc::SyncSender<Event>,mpsc::Receiver<Vec<u8>>){
        let (send,receiver)=mpsc::sync_channel(4);let(sender,recv)=mpsc::sync_channel(1);
        (Worker{generation:1,map:map(),receiver,sender:Some(sender),child:Arc::new(Mutex::new(None)),exit:Arc::new(Mutex::new(None)),cancel:Arc::new(AtomicBool::new(false)),expected_spawn:None,
            started:now,pending:None,ready:false,last_seq:0,removal:None,scene_version:0,removal_ack:None,
            catalog:None,catalog_scene:None,pending_scene:None,catalog_ack:None,prepared_ids:Vec::new(),angular_profile:None},send,recv)
    }
    fn good_catalog_state(seq:u32,spec:&CatalogSpec,scene:&Scene)->Value{
        let mut v=good(seq);v["version"]=3.into();v["generation"]=1.into();v["catalog_sha256"]=spec.sha256().into();
        v["scene_version"]=scene.version().into();v["scene_sha256"]=scene.hash().into();v
    }
    fn good_catalog_ack(seq:u32,spec:&CatalogSpec,scene:&Scene)->Value{serde_json::json!({
        "version":3,"event":"scene_synced","generation":1,"config_sha256":"a".repeat(64),"catalog_sha256":spec.sha256(),
        "advance_seq":seq,"tick":180+seq*6,"scene_version":scene.version(),"removed_object_ids":scene.ids(),"scene_sha256":scene.hash()})}
    fn good_fracture_state(seq:u32,spec:&CatalogSpec,scene:&Scene,prepared:bool)->Value{
        let mut v=good_catalog_state(seq,spec,scene);v["version"]=5.into();v["contacts"]=true.into();
        v["state"]["object_contacts"]=serde_json::json!([]);v["state"]["fractures"]=serde_json::json!([]);
        if prepared{
            v["event"]="prepared".into();v["state"]["fractures"]=serde_json::json!([fracture::tests::value(1)]);
            v["state"]["object_contacts"]=serde_json::json!([{"object_id":1,"kind":"hull","substep":1,
                "point":[0.,0.,0.],"normal":[0.,0.,1.],"velocity":[0.,0.,4.]}]);
        }v
    }
    #[test]fn fracture_prepared_reply_requires_commit_inclusion_before_next_advance(){
        for spec in [catalog::tests::fracture_spec(2),catalog::tests::whole_spec(2)] {
        let now=Instant::now();let empty=Scene::new(&spec,&[]).unwrap();
        let(mut worker,send,recv)=fake_worker(now);worker.catalog=Some(spec.clone());worker.catalog_scene=Some(empty.clone());
        send.send(Event::Line(now,serde_json::to_vec(&good_fracture_state(0,&spec,&empty,false)).unwrap())).unwrap();
        worker.poll(now).unwrap();worker.advance(Input::STOP,now).unwrap();
        assert_eq!(json(&recv.try_recv().unwrap(),1024).unwrap()["version"],5);
        send.send(Event::Line(now,serde_json::to_vec(&good_fracture_state(1,&spec,&empty,true)).unwrap())).unwrap();
        let state=worker.poll(now).unwrap().unwrap();assert_eq!(state.fractures.len(),1);
        assert_eq!(worker.prepared_ids(),&[1]);assert!(!worker.pending());
        assert!(worker.advance(Input::STOP,now).is_err());
        assert!(worker.sync_removed(empty.clone(),now).is_err());
        assert!(worker.sync_removed(Scene::new(&spec,&[2]).unwrap(),now).is_err());
        assert!(matches!(recv.try_recv(),Err(mpsc::TryRecvError::Empty)));
        let committed=Scene::new(&spec,&[1]).unwrap();worker.sync_removed(committed.clone(),now).unwrap();
        let request=json(&recv.try_recv().unwrap(),1024).unwrap();assert_eq!(request["version"],5);
        assert!(worker.advance(Input::STOP,now).is_err());assert_eq!(worker.prepared_ids(),&[1]);
        let mut ack=good_catalog_ack(1,&spec,&committed);ack["version"]=5.into();ack["contacts"]=true.into();
        send.send(Event::Line(now,serde_json::to_vec(&ack).unwrap())).unwrap();assert!(worker.poll(now).unwrap().is_none());
        assert!(worker.prepared_ids().is_empty());assert_eq!(worker.catalog_scene(),Some(&committed));
        worker.take_catalog_ack().unwrap();assert_eq!(worker.advance(Input::STOP,now).unwrap(),2);
        }
    }
    #[test]fn fracture_state_filters_unreceipted_energy_contacts_and_rejects_wrong_event(){
        for spec in [catalog::tests::fracture_spec(2),catalog::tests::whole_spec(2)] {
        let scene=Scene::new(&spec,&[]).unwrap();
        let mut v=good_fracture_state(1,&spec,&scene,true);
        let mut denied=v["state"]["object_contacts"][0].clone();denied["object_id"]=2.into();
        v["state"]["object_contacts"].as_array_mut().unwrap().push(denied);
        let parse=|v:&Value|catalog::response(&serde_json::to_vec(v).unwrap(),&map(),&spec,1,1,None,&scene);
        let state=parse(&v).unwrap();assert_eq!(state.object_contacts.len(),1);assert_eq!(state.object_contacts[0].object_id,1);
        let mut changed=v.clone();changed["event"]="state".into();assert!(parse(&changed).is_err());
        changed=v.clone();changed["state"]["fractures"]=serde_json::json!([]);assert!(parse(&changed).is_err());
        changed["event"]="state".into();let state=parse(&changed).unwrap();assert!(state.object_contacts.is_empty());
        changed["state"].as_object_mut().unwrap().remove("fractures");assert!(parse(&changed).is_err());
        changed=v;changed["state"]["fractures"][0]["energy_j"]=1.into();assert!(parse(&changed).is_err());
        }
    }
    #[test]fn catalog_ready_is_bound_to_its_selected_map_not_only_config_hash(){
        use crate::map_profile091::MapId;
        for map_id in [MapId::Karelia,MapId::Prohorovka]{
            let spec=catalog::tests::spec_for(map_id,3);let scene=Scene::new(&spec,&[1,3]).unwrap();
            let mut selected=map();selected.asset=map_id.asset().into();selected.arena_type_id=map_id.arena_type_id();
            let mut ready=good_catalog_state(0,&spec,&scene);ready["map"]=map_id.asset().into();
            let raw=serde_json::to_vec(&ready).unwrap();
            assert_eq!(catalog::response(&raw,&selected,&spec,1,0,None,&scene).unwrap().scene_version,2);
            let other=if map_id==MapId::Karelia{MapId::Prohorovka}else{MapId::Karelia};
            let mut mismatched=selected.clone();mismatched.asset=other.asset().into();mismatched.arena_type_id=other.arena_type_id();
            // A self-consistent response with a reused config hash cannot
            // substitute another map underneath this retained catalog.
            ready["map"]=other.asset().into();let raw=serde_json::to_vec(&ready).unwrap();
            assert!(catalog::response(&raw,&mismatched,&spec,1,0,None,&scene).is_err());
            assert!(catalog::response(&raw,&selected,&spec,1,0,None,&scene).is_err());
        }
    }
    #[test]fn catalog_bootstrap_binds_restored_scene_before_ready(){
        let spec=catalog::tests::spec(3);let restored=Scene::new(&spec,&[1,3]).unwrap();let now=Instant::now();
        let (mut worker,send,_)=fake_worker(now);worker.catalog=Some(spec.clone());worker.catalog_scene=Some(restored.clone());
        assert!(worker.catalog_scene().is_none());assert_eq!(worker.scene_version(),0);
        let raw=catalog::scene_request(&map(),&spec,1,0,&restored,true).unwrap();
        let v=json(&raw,1024).unwrap();assert_eq!(v["op"],"restore_scene");assert_eq!(v["advance_seq"],0);
        assert!(catalog::scene_request(&map(),&spec,1,1,&restored,true).is_err());
        let good=good_catalog_state(0,&spec,&restored);
        for (key,value) in [("catalog_sha256","c".repeat(64).into()),("generation",2.into()),("scene_version",1.into()),
            ("scene_sha256",Scene::new(&spec,&[1,2]).unwrap().hash().into()),("version",2.into())]{
            let mut changed=good.clone();changed[key]=value;
            assert!(catalog::response(&serde_json::to_vec(&changed).unwrap(),&map(),&spec,1,0,None,&restored).is_err(),"{key}");
        }
        send.send(Event::Line(now,serde_json::to_vec(&good).unwrap())).unwrap();
        assert_eq!(worker.poll(now).unwrap().unwrap().scene_version,2);assert_eq!(worker.catalog_scene(),Some(&restored));
    }
    #[test]fn catalog_cumulative_ack_blocks_advances_and_preserves_driving_sequence(){
        let now=Instant::now();let spec=catalog::tests::spec(4);let empty=Scene::new(&spec,&[]).unwrap();
        let (mut worker,send,recv)=fake_worker(now);worker.catalog=Some(spec.clone());worker.catalog_scene=Some(empty.clone());
        send.send(Event::Line(now,serde_json::to_vec(&good_catalog_state(0,&spec,&empty)).unwrap())).unwrap();worker.poll(now).unwrap();
        let first=Scene::new(&spec,&[2]).unwrap();let second=Scene::new(&spec,&[1,2,4]).unwrap();
        for (seq,scene) in [first.clone(),second.clone(),second.clone()].into_iter().enumerate(){
            worker.sync_removed(scene.clone(),now).unwrap();let request=json(&recv.recv().unwrap(),1024).unwrap();
            assert_eq!(request["advance_seq"],seq);assert_eq!(request["removed_object_ids"],serde_json::json!(scene.ids()));
            assert!(worker.advance(Input::STOP,now).is_err());assert!(worker.sync_removed(scene.clone(),now).is_err());
            send.send(Event::Line(now,serde_json::to_vec(&good_catalog_ack(seq as u32,&spec,&scene)).unwrap())).unwrap();
            assert!(worker.poll(now).unwrap().is_none());assert_eq!(worker.last_seq,seq as u32);
            assert_eq!(worker.catalog_scene(),Some(&scene));assert!(worker.advance(Input::STOP,now).is_err());
            let ack=worker.take_catalog_ack().unwrap();assert_eq!(ack.tick,180+seq as u32*6);assert_eq!(ack.removed_object_ids,scene.ids());
            assert!(worker.take_catalog_ack().is_none());
            assert!(worker.sync_removed(empty.clone(),now).is_err());
            let replacement=Scene::new(&spec,if scene.version()==1{&[1][..]}else{&[1,3,4][..]}).unwrap();
            assert!(worker.sync_removed(replacement,now).is_err());
            let next=worker.advance(Input::STOP,now).unwrap();let request=json(&recv.recv().unwrap(),1024).unwrap();
            assert_eq!(request["version"],3);assert_eq!(request["scene_sha256"],scene.hash());
            send.send(Event::Line(now,serde_json::to_vec(&good_catalog_state(next,&spec,&scene)).unwrap())).unwrap();worker.poll(now).unwrap();
        }
        send.send(Event::Line(now,serde_json::to_vec(&good_catalog_ack(3,&spec,&second)).unwrap())).unwrap();assert!(worker.poll(now).is_err());
    }
    #[test]fn catalog_failed_ack_cannot_commit_any_scene_metadata(){
        let spec=catalog::tests::spec(3);let empty=Scene::new(&spec,&[]).unwrap();let target=Scene::new(&spec,&[1,3]).unwrap();
        let good=good_catalog_ack(0,&spec,&target);
        let changes=[("generation",2.into()),("catalog_sha256","c".repeat(64).into()),("config_sha256","c".repeat(64).into()),
            ("advance_seq",1.into()),("tick",186.into()),("scene_version",1.into()),("scene_sha256","c".repeat(64).into()),
            ("removed_object_ids",serde_json::json!([1,2])),("removed_object_ids",serde_json::json!([3,1])),
            ("removed_object_ids",serde_json::json!([1,1])),("removed_object_ids",serde_json::json!([1.0,3])),("event","state".into())];
        for (key,value) in changes {
            let now=Instant::now();let (mut worker,send,recv)=fake_worker(now);worker.ready=true;
            worker.catalog=Some(spec.clone());worker.catalog_scene=Some(empty.clone());worker.sync_removed(target.clone(),now).unwrap();recv.recv().unwrap();
            let mut v=good.clone();v[key]=value;send.send(Event::Line(now,serde_json::to_vec(&v).unwrap())).unwrap();
            assert!(worker.poll(now).is_err(),"{key}");assert_eq!(worker.scene_version(),0);assert_eq!(worker.catalog_scene(),Some(&empty));
            assert!(worker.take_catalog_ack().is_none());assert_eq!(worker.last_seq,0);
        }
        for failure in 0..3 {
            let now=Instant::now();let (mut worker,send,recv)=fake_worker(now);worker.ready=true;
            worker.catalog=Some(spec.clone());worker.catalog_scene=Some(empty.clone());worker.sync_removed(target.clone(),now).unwrap();recv.recv().unwrap();
            match failure {0=>send.send(Event::Failed).unwrap(),1=>send.send(Event::Line(now-Duration::from_nanos(1),serde_json::to_vec(&good).unwrap())).unwrap(),_=>{}}
            assert!(worker.poll(if failure==2{now+REPLY_TIMEOUT+Duration::from_nanos(1)}else{now}).is_err());
            assert_eq!(worker.catalog_scene(),Some(&empty));assert!(worker.take_catalog_ack().is_none());
        }
    }
    #[test]fn ipc_unsolicited_stale_duplicate_reply_and_timeout_never_publish(){
        let t=Instant::now();let (mut w,send,_)=fake_worker(t);send.send(Event::Line(t,serde_json::to_vec(&good(0)).unwrap())).unwrap();w.poll(t).unwrap();
        send.send(Event::Line(t,serde_json::to_vec(&good(1)).unwrap())).unwrap();assert!(w.poll(t).is_err());
        let (mut w,send,recv)=fake_worker(t);send.send(Event::Line(t,serde_json::to_vec(&good(0)).unwrap())).unwrap();w.poll(t).unwrap();
        let later=t+Duration::from_millis(100);assert_eq!(w.advance(Input::STOP,later).unwrap(),1);recv.recv().unwrap();
        assert!(w.advance(Input::STOP,later).is_err());send.send(Event::Line(t,serde_json::to_vec(&good(1)).unwrap())).unwrap();assert!(w.poll(later).is_err());
        let (mut w,send,recv)=fake_worker(t);send.send(Event::Line(t,serde_json::to_vec(&good(0)).unwrap())).unwrap();w.poll(t).unwrap();
        w.advance(Input::STOP,t).unwrap();recv.recv().unwrap();send.send(Event::Line(t,serde_json::to_vec(&good(1)).unwrap())).unwrap();assert_eq!(w.poll(t).unwrap().unwrap().seq,1);
        send.send(Event::Line(t,serde_json::to_vec(&good(1)).unwrap())).unwrap();assert!(w.poll(t).is_err());
        let (mut w,_,_)=fake_worker(t);assert!(w.poll(t+START_TIMEOUT+Duration::from_secs(1)).is_err());
        let (mut w,send,recv)=fake_worker(t);send.send(Event::Line(t,serde_json::to_vec(&good(0)).unwrap())).unwrap();w.poll(t).unwrap();
        w.advance(Input::STOP,t).unwrap();recv.recv().unwrap();assert!(w.poll(t+REPLY_TIMEOUT+Duration::from_nanos(1)).is_err());
    }

    #[test]fn packaged_worker_real_child_ipc_both_maps_fixed_steps_then_owned_eof(){
        // Authorized by root for this card. No client/gateway/socket/DB action.
        let pool=Arc::new(crate::worker_fixtures091::packaged());let out=scratch();let mut proof=Vec::new();
        for (i,map) in pool.maps.iter().enumerate(){
            let begin=Instant::now();let mut w=Worker::launch(pool.clone(),map.clone(),(i+1) as u32,begin).unwrap();
            fn wait(w:&mut Worker,deadline:Instant)->State{loop{assert!(Instant::now()<deadline,"bounded own IPC deadline");
                if let Some(s)=w.poll(Instant::now()).unwrap(){return s;}thread::sleep(Duration::from_millis(5));}}
            let initial=wait(&mut w,begin+Duration::from_secs(30));assert_eq!(initial.seq,0);let pid=w.process_id().unwrap();
            let mut ticks=vec![initial.tick];let mut samples=Vec::new();
            for input in [Input::STOP,Input{throttle:1,steer:0,brake:false,speed_percent:100},Input::STOP]{
                w.advance(input,Instant::now()).unwrap();let state=wait(&mut w,Instant::now()+REPLY_TIMEOUT);ticks.push(state.tick);
                samples.push(serde_json::json!({"seq":state.seq,"tick":state.tick,"position":state.pose.position,"direction":state.pose.direction,
                    "contacts":state.pose.contacts,"wheel_contact_masks":state.pose.wheel_contact_masks}));
            }
            assert_eq!(ticks,vec![180,186,192,198]);let child=w.child.clone();let exit=w.exit.clone();drop(w);
            // Revocation is immediate and the handle is removed before the next
            // generation. Actual OS reaping is bounded in the owned Drop task.
            assert!(child.lock().unwrap().is_none());
            let deadline=Instant::now()+Duration::from_secs(3);
            loop{if let Some(observed)=*exit.lock().unwrap(){assert_eq!(observed,ExitEvidence{forced:false,code:Some(0),reaped:true});break;}
                assert!(Instant::now()<deadline,"owned process must be reaped");thread::sleep(Duration::from_millis(10));}
            proof.push(serde_json::json!({"map":map.asset,"config_sha256":map.config_sha256,"pid":pid,"ticks":ticks,"samples":samples,
                "status":"PASS_CHILD_IPC_ONLY","native_game":"NOT_RUN","exit_code":0,"forced":false,"reaped":true}));
        }
        fs::write(out.join("actual-worker-ipc.json"),serde_json::to_vec_pretty(&proof).unwrap()).unwrap();
    }
    #[test]fn worker_arguments_preserve_absolute_drive_identity_not_unc_or_relative(){
        assert!(worker_path_argument(Path::new("relative/config.json")).is_err());
        #[cfg(windows)] {
            assert_eq!(worker_path_argument(Path::new(r"\\?\D:\own\local")).unwrap(),PathBuf::from(r"D:\own\local"));
            assert_eq!(worker_path_argument(Path::new(r"D:\own\local")).unwrap(),PathBuf::from(r"D:\own\local"));
            assert!(worker_path_argument(Path::new(r"\\?\UNC\server\share")).is_err());
        }
    }
}
