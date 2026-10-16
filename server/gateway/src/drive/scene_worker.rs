//! P05C private IPC7 batch client. Native IDs and client poses never enter it.
//! A frame validates the whole producer batch before any pose is returned.
//! Catalog proof data is retained for the domain's existing scalar verifier;
//! structural IPC validation alone does not authorize a world/HP mutation.
use std::{collections::{BTreeMap,BTreeSet},fmt,fs,io::{self,Read,Write,BufRead,BufReader},
    path::{Component,Path,PathBuf},process::{Child,Command,Stdio},sync::{Arc,Mutex,mpsc},thread,
    time::{Duration,Instant}};
use serde::{Deserialize,Deserializer,de::{self,Visitor,MapAccess,SeqAccess}};
use serde_json::{Value,Map,Number,json};
use sha2::{Digest,Sha256};
pub const MAX_ACTORS:usize=6;
#[cfg(test)]
#[path="scene_worker/tests_p04m.rs"]
mod tests_p04m;
pub const MAX_INPUT:usize=32768;
pub const MAX_OUTPUT:usize=512*1024;
pub const START_TIMEOUT:Duration=Duration::from_secs(120);
pub const REPLY_TIMEOUT:Duration=Duration::from_millis(500);
pub const STEP:Duration=Duration::from_millis(100);
pub const POLICY:&str="p05c-shared-scene-v1";
const ZERO:&str="0000000000000000000000000000000000000000000000000000000000000000";
fn bad(reason:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,format!("shared scene IPC7: {reason}"))}
fn digest(bytes:&[u8])->String{format!("{:x}",Sha256::digest(bytes))}
fn hash(value:&str)->io::Result<()>{if value.len()!=64||!value.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)){return Err(bad("SHA256"));}Ok(())}
fn keys(v:&Value,names:&[&str])->io::Result<()>{let o=v.as_object().ok_or_else(||bad("object"))?;
    if o.len()!=names.len()||names.iter().any(|k|!o.contains_key(*k)){return Err(bad("exact fields"));}Ok(())}
fn string<'a>(v:&'a Value,k:&str)->io::Result<&'a str>{v[k].as_str().ok_or_else(||bad("string"))}
fn uint(v:&Value)->io::Result<u64>{v.as_u64().ok_or_else(||bad("unsigned integer"))}
fn number(v:&Value,limit:f32)->io::Result<f32>{let n=v.as_f64().ok_or_else(||bad("number"))?;
    if !n.is_finite()||n.abs()>limit as f64{return Err(bad("finite number bound"));}Ok(n as f32)}
fn vector<const N:usize>(v:&Value,limit:f32)->io::Result<[f32;N]>{let a=v.as_array().filter(|a|a.len()==N).ok_or_else(||bad("vector length"))?;
    let mut result=[0.;N];for(i,n)in a.iter().enumerate(){result[i]=number(n,limit)?;}Ok(result)}
fn array(v:&Value,max:usize)->io::Result<&Vec<Value>>{v.as_array().filter(|v|v.len()<=max).ok_or_else(||bad("array bound"))}
fn normal(v:&Value)->io::Result<[f32;3]>{let n=vector::<3>(v,1.001)?;let l=n.iter().map(|v|f64::from(*v).powi(2)).sum::<f64>();
    if (l-1.).abs()>0.002{return Err(bad("unit normal"));}Ok(n)}

// Reject duplicate keys at every depth before constructing ordinary Values.
struct Unique(Value);
impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D:Deserializer<'de>>(d:D)->Result<Self,D::Error>{
        struct V;impl<'de>Visitor<'de>for V{
            type Value=Unique;
            fn expecting(&self,f:&mut fmt::Formatter)->fmt::Result{f.write_str("bounded unique scene JSON")}
            fn visit_bool<E:de::Error>(self,v:bool)->Result<Unique,E>{Ok(Unique(v.into()))}
            fn visit_i64<E:de::Error>(self,v:i64)->Result<Unique,E>{Ok(Unique(v.into()))}
            fn visit_u64<E:de::Error>(self,v:u64)->Result<Unique,E>{Ok(Unique(v.into()))}
            fn visit_f64<E:de::Error>(self,v:f64)->Result<Unique,E>{Ok(Unique(Value::Number(Number::from_f64(v).ok_or_else(||E::custom("finite"))?)))}
            fn visit_str<E:de::Error>(self,v:&str)->Result<Unique,E>{if v.len()>4096{return Err(E::custom("string bound"));}Ok(Unique(v.into()))}
            fn visit_string<E:de::Error>(self,v:String)->Result<Unique,E>{self.visit_str(&v)}
            fn visit_unit<E:de::Error>(self)->Result<Unique,E>{Ok(Unique(Value::Null))}
            fn visit_seq<A:SeqAccess<'de>>(self,mut a:A)->Result<Unique,A::Error>{let mut v=Vec::new();while let Some(Unique(x))=a.next_element::<Unique>()?{
                if v.len()>=2048{return Err(de::Error::custom("array bound"));}v.push(x);}Ok(Unique(Value::Array(v)))}
            fn visit_map<A:MapAccess<'de>>(self,mut a:A)->Result<Unique,A::Error>{let mut v=Map::new();while let Some((k,Unique(x)))=a.next_entry::<String,Unique>()?{
                if k.len()>128||v.len()>=64||v.insert(k,x).is_some(){return Err(de::Error::custom("duplicate/object bound"));}}Ok(Unique(Value::Object(v)))}
        }d.deserialize_any(V)
    }
}
fn parse(raw:&[u8],max:usize)->io::Result<Value>{if raw.is_empty()||raw.len()>max{return Err(bad("JSON bytes"));}
    let Unique(v)=serde_json::from_slice(raw).map_err(|_|bad("unique bounded JSON"))?;
    fn check(v:&Value,depth:usize,count:&mut usize)->io::Result<()>{*count+=1;if depth>12||*count>40000{return Err(bad("JSON depth/nodes"));}
        match v{Value::Array(a)=>for c in a{check(c,depth+1,count)?;},Value::Object(a)=>for c in a.values(){check(c,depth+1,count)?;},_=>()}Ok(())}
    check(&v,0,&mut 0)?;Ok(v)
}
fn plain(path:&Path)->io::Result<()>{for item in path.ancestors(){let m=fs::symlink_metadata(item)?;
    if m.file_type().is_symlink(){return Err(bad("linked path"));}
    #[cfg(windows)] {use std::os::windows::fs::MetadataExt;if m.file_attributes()&0x400!=0{return Err(bad("reparse path"));}}
}Ok(())}
fn owned(root:&Path,path:&Path)->io::Result<PathBuf>{if !path.is_absolute(){return Err(bad("absolute path required"));}plain(root)?;plain(path)?;
    let root=root.canonicalize()?;let p=path.canonicalize()?;if !p.starts_with(&root)||p==root{return Err(bad("asset escapes root"));}Ok(p)}
fn worker_argument(path:&Path)->io::Result<PathBuf>{
    #[cfg(windows)]{let text=path.to_str().ok_or_else(||bad("path UTF8"))?;if let Some(p)=text.strip_prefix(r"\\?\"){
        let b=p.as_bytes();if b.len()<3||!b[0].is_ascii_alphabetic()||b[1]!=b':'||b[2]!=b'\\'{return Err(bad("worker path namespace"));}return Ok(PathBuf::from(p));}}
    if !path.is_absolute(){return Err(bad("worker absolute path"));}Ok(path.to_path_buf())}
fn read(path:&Path,max:usize,expected:&str)->io::Result<Vec<u8>>{hash(expected)?;let f=fs::File::open(path)?;let n=f.metadata()?.len();
    if n==0||n>max as u64{return Err(bad("asset size"));}let mut raw=Vec::new();f.take(max as u64+1).read_to_end(&mut raw)?;
    if raw.len()as u64!=n||digest(&raw)!=expected{return Err(bad("asset SHA/size changed"));}Ok(raw)}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Kind{Ms1,Is7,T26,T34,T3485,WtE100128,Fv215b183}
impl Kind{
    // Physical component kinds cannot implicitly enter the owned World enum.
    fn vehicle(self)->Option<crate::gateway091::shared::vehicle_profile::VehicleKind> {
        use crate::gateway091::shared::vehicle_profile::VehicleKind as V;
        Some(match self{Self::Ms1=>V::Ms1,Self::Is7=>V::Is7,Self::T26=>V::T26,Self::T34=>V::T34,Self::T3485=>V::T3485,
            Self::WtE100128|Self::Fv215b183=>return None})
    }
    /// Explicit seven-kind mapping for a separately qualified combat route.
    /// Caller must already require resources4 + SceneManifest3 + opt-in. The
    /// legacy vehicle() above intentionally remains old5/None for new kinds.
    pub(crate) fn extended_vehicle(self)->crate::gateway091::shared::vehicle_profile::VehicleKind {
        use crate::gateway091::shared::vehicle_profile::VehicleKind as V;
        match self{Self::Ms1=>V::Ms1,Self::Is7=>V::Is7,Self::T26=>V::T26,Self::T34=>V::T34,Self::T3485=>V::T3485,
            Self::WtE100128=>V::Wt128,Self::Fv215b183=>V::Fv183}
    }
    pub(crate) fn physical_profile(self)->crate::gateway091::shared::ram_proof::Profile {
        use crate::gateway091::shared::ram_proof::Profile as P;
        match self{Self::Ms1=>P::Ms1,Self::Is7=>P::Is7,Self::T26=>P::T26,Self::T34=>P::T34,Self::T3485=>P::T3485,
            Self::WtE100128=>P::WtE100128,Self::Fv215b183=>P::Fv215b183}
    }
    fn minimum_manifest_version(self)->u64{match self{Self::Ms1|Self::Is7=>1,Self::T26|Self::T34|Self::T3485=>2,
        Self::WtE100128|Self::Fv215b183=>3}}
    pub fn label(self)->&'static str{match self{Self::Ms1=>"ms1",Self::Is7=>"is7",Self::T26=>"t26",Self::T34=>"t34",Self::T3485=>"t3485",
        Self::WtE100128=>"wt-e100-128",Self::Fv215b183=>"fv215b-183"}}
    pub fn profile_sha(self)->&'static str{self.physical_profile().sha()}
    fn source(self)->&'static[u8]{match self{
        Self::Ms1=>include_bytes!("worker/ms1-handling-profile.json"),Self::Is7=>include_bytes!("worker/is7-handling-profile.json"),
        Self::T26=>include_bytes!("worker/p04m-t26-qualified-profile.json"),Self::T34=>include_bytes!("worker/p04m-t34-qualified-profile.json"),
        Self::T3485=>include_bytes!("worker/p04m-t3485-qualified-profile.json"),
        Self::WtE100128=>include_bytes!("worker/p06t-wt-e100-128-qualified-profile.json"),Self::Fv215b183=>include_bytes!("worker/p06t-fv215b-183-qualified-profile.json")}}
    fn binding_bits(self)->(u32,[u32;3]){let b=self.physical_profile().binding();(b.inverse_mass.to_bits(),b.principal.map(f32::to_bits))}
}
#[derive(Clone,Debug)]pub struct ActorSpec{pub slot:usize,pub kind:Kind,pub config_sha256:String,pub spawn:[f32;3],pub yaw:f32}
#[derive(Clone,Debug)]pub struct SceneSpec{
    pub local_root:PathBuf,pub manifest_path:PathBuf,pub manifest_sha256:String,pub map:String,pub actors:Vec<ActorSpec>,
    catalog_sha256:String,catalog_ids:BTreeSet<u32>,pins:Vec<(PathBuf,String,usize)>,
}
impl SceneSpec{
    pub fn load(root:&Path,path:&Path,sha:&str)->io::Result<Self>{let manifest_path=owned(root,path)?;let raw=read(&manifest_path,MAX_INPUT,sha)?;let m=parse(&raw,MAX_INPUT)?;
        keys(&m,&["version","profile","policy","map","catalog","actors"])?;
        let version=uint(&m["version"])?;
        let map=string(&m,"map")?;if !matches!(version,1|2|3)||string(&m,"profile")?!="test_lab"||string(&m,"policy")?!=POLICY||!matches!(map,"01_karelia"|"05_prohorovka"){return Err(bad("manifest policy"));}
        let rows=array(&m["actors"],MAX_ACTORS)?;if rows.is_empty(){return Err(bad("empty roster"));}
        let mut actors=Vec::new();let mut pins=vec![(manifest_path.clone(),sha.to_string(),MAX_INPUT)];let mut geometry=None;
        for row in rows{
            if version>=2 {keys(row,&["slot","kind","config","spawn_origin","spawn_yaw","source_profile"])?;}
            else {keys(row,&["slot","kind","config","spawn_origin","spawn_yaw"])?;}
            if uint(&row["slot"])?!=actors.len()as u64{return Err(bad("ordered actor slots"));}
            let kind=match string(row,"kind")?{"ms1"=>Kind::Ms1,"is7"=>Kind::Is7,
                "t26"=>Kind::T26,"t34"=>Kind::T34,"t3485"=>Kind::T3485,
                "wt-e100-128"=>Kind::WtE100128,"fv215b-183"=>Kind::Fv215b183,_=>return Err(bad("actor kind"))};
            if version<kind.minimum_manifest_version(){return Err(bad("actor kind requires newer manifest"));}
            if kind.minimum_manifest_version()>=2 {
                let source=&row["source_profile"];keys(source,&["path","sha256"])?;
                if string(source,"sha256")?!=kind.profile_sha(){return Err(bad("curated source identity"));}
                let path=owned(root,Path::new(string(source,"path")?))?;
                read(&path,16384,kind.profile_sha())?;pins.push((path,kind.profile_sha().into(),16384));
            }else if version>=2&&!row["source_profile"].is_null(){return Err(bad("legacy actor source profile must be null"));}
            let r=&row["config"];keys(r,&["path","sha256"])?;let path=owned(root,Path::new(string(r,"path")?))?;let hash=string(r,"sha256")?;
            let c=parse(&read(&path,16384,hash)?,16384)?;
            keys(&c,&["version","profile","map","terrain","obstacles","spawn_origin","spawn_yaw","body_half_extents","body_center_offset","wheel_points",
                "mass_kg","max_forward_mps","max_reverse_mps","engine_max_torque_nm","wheel_radius","suspension_min","suspension_max","track_max_brake_torque",
                "bounds_xz","longitudinal_friction","lateral_friction","stationary_steering_ratio","handling"])?;
            if uint(&c["version"])?!=3||string(&c,"profile")?!="test_lab"||string(&c,"map")?!=map||digest(kind.source())!=kind.profile_sha(){return Err(bad("source config identity"));}
            let source=parse(kind.source(),16384)?;
            let profile=if kind.minimum_manifest_version()>=2{&source["definition"]}else{&source};
            fn same(a:&Value,b:&Value)->bool{if b.is_number(){return a.as_f64()==b.as_f64();}if let(Value::Array(a),Value::Array(b))=(a,b){return a.len()==b.len()&&a.iter().zip(b).all(|(a,b)|same(a,b));}a==b}
            if profile["physics"].as_object().ok_or_else(||bad("profile object"))?.iter().any(|(k,v)|!same(&c[k],v))||!same(&c["handling"],&profile["handling"]){return Err(bad("complete source physical projection"));}
            let references=json!([c["terrain"],c["obstacles"],c["bounds_xz"]]);if geometry.as_ref().is_some_and(|g|*g!=references){return Err(bad("mixed map geometry"));}geometry=Some(references);
            for field in ["terrain","obstacles"]{let r=&c[field];keys(r,&["path","sha256"])?;let p=owned(root,Path::new(string(r,"path")?))?;let sha=string(r,"sha256")?;
                read(&p,8*1024*1024,sha)?;pins.push((p,sha.into(),8*1024*1024));}
            let spawn=vector::<3>(&row["spawn_origin"],1000.)?;let yaw=number(&row["spawn_yaw"],std::f32::consts::PI)?;let b=vector::<4>(&c["bounds_xz"],1000.)?;
            if b[2]-b[0]<100.||b[3]-b[1]<100.||spawn[0]<b[0]+5.||spawn[0]>b[2]-5.||spawn[2]<b[1]+5.||spawn[2]>b[3]-5.{return Err(bad("spawn/bounds"));}
            pins.push((path,hash.into(),16384));actors.push(ActorSpec{slot:actors.len(),kind,config_sha256:hash.into(),spawn,yaw});
        }
        let mut catalog_sha256=ZERO.into();let mut catalog_ids=BTreeSet::new();
        if !m["catalog"].is_null(){let r=&m["catalog"];keys(r,&["path","sha256"])?;let p=owned(root,Path::new(string(r,"path")?))?;let h=string(r,"sha256")?;
            let c=parse(&read(&p,1024*1024,h)?,1024*1024)?;
            keys(&c,&["version","profile","map","physics_manifest_sha256","projectile_manifest_sha256","contacts","objects","ram_policy"])?;
            if uint(&c["version"])?!=8||string(&c,"profile")?!="test_lab"||string(&c,"map")?!=map||c["contacts"]!=true||string(&c,"ram_policy")?!="test_lab-fence-linear-angular-energy-v1"{return Err(bad("catalog8 policy"));}
            for row in array(&c["objects"],2048)?{let id=u32::try_from(uint(&row["object_id"])?).map_err(|_|bad("object ID"))?;
                if id==0||catalog_ids.last().is_some_and(|p|*p>=id)||!catalog_ids.insert(id){return Err(bad("ordered catalog IDs"));}}
            if catalog_ids.is_empty(){return Err(bad("empty catalog"));}catalog_sha256=h.into();pins.push((p,h.into(),1024*1024));
        }
        Ok(Self{local_root:root.canonicalize()?,manifest_path,manifest_sha256:sha.into(),map:map.into(),actors,catalog_sha256,catalog_ids,pins})
    }
    pub fn verify(&self)->io::Result<()>{for(p,h,n)in &self.pins{read(&owned(&self.local_root,p)?,*n,h)?;}Ok(())}
    pub fn catalog_sha256(&self)->&str{&self.catalog_sha256}
}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct Scene{pub ids:Vec<u32>,pub sha256:String}
impl Scene{
    pub fn new(spec:&SceneSpec,ids:&[u32])->io::Result<Self>{if ids.len()>2048||ids.iter().any(|id|!spec.catalog_ids.contains(id))||ids.windows(2).any(|a|a[0]>=a[1]){return Err(bad("scene removal set"));}
        let sha256=if spec.catalog_sha256==ZERO{if !ids.is_empty(){return Err(bad("no catalog removals"));}digest(b"wot091-empty-battle-scene-v1\0")}else{
            let mut h=Sha256::new();h.update(b"wot091-fragile-scene-v3\0");for i in(0..64).step_by(2){h.update([u8::from_str_radix(&spec.catalog_sha256[i..i+2],16).map_err(|_|bad("hash hex"))?]);}
            h.update((ids.len()as u32).to_le_bytes());for id in ids{h.update(id.to_le_bytes());}format!("{:x}",h.finalize())};Ok(Self{ids:ids.to_vec(),sha256})}
    pub fn version(&self)->u32{self.ids.len()as u32}
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub struct Input{pub throttle:i8,pub steer:i8,pub brake:bool,pub speed_percent:u8}
impl Input{pub const STOP:Self=Self{throttle:0,steer:0,brake:true,speed_percent:100};
    fn valid(self)->bool{(-1..=1).contains(&self.throttle)&&(-1..=1).contains(&self.steer)&&(!self.brake||(self.throttle==0&&self.steer==0))&&
        (self.speed_percent==100||self.speed_percent==50&&!self.brake&&self.throttle!=0||self.speed_percent==25&&!self.brake&&self.throttle==1)}}
fn header(spec:&SceneSpec,generation:u32)->Value{json!({"version":7,"generation":generation,"manifest_sha256":spec.manifest_sha256,"catalog_sha256":spec.catalog_sha256})}
fn scene_request(spec:&SceneSpec,generation:u32,scene:&Scene,seq:u32,op:&str)->Value{let mut v=header(spec,generation);let o=v.as_object_mut().unwrap();
    o.extend([("op".into(),op.into()),("advance_seq".into(),seq.into()),("scene_version".into(),scene.version().into()),("removed_object_ids".into(),json!(scene.ids)),("scene_sha256".into(),scene.sha256.clone().into())]);v}
pub fn advance_request(spec:&SceneSpec,generation:u32,scene:&Scene,seq:u32,inputs:&[Input])->io::Result<Vec<u8>>{
    if generation==0||!(1..=36000).contains(&seq)||inputs.len()!=spec.actors.len()||inputs.iter().any(|i|!i.valid()){return Err(bad("batch inputs/sequence"));}
    let mut v=header(spec,generation);v["op"]="advance".into();v["seq"]=seq.into();v["ticks"]=6.into();v["scene_version"]=scene.version().into();v["scene_sha256"]=scene.sha256.clone().into();
    v["inputs"]=json!(inputs.iter().enumerate().map(|(slot,i)|json!({"slot":slot,"throttle":i.throttle,"steer":i.steer,"brake":i.brake,"speed_percent":i.speed_percent})).collect::<Vec<_>>());line(&v)}
fn line(v:&Value)->io::Result<Vec<u8>>{let mut b=serde_json::to_vec(v).map_err(|_|bad("JSON encoding"))?;if b.len()>MAX_INPUT{return Err(bad("input size"));}b.push(b'\n');Ok(b)}

#[derive(Clone,Debug,PartialEq)]pub struct Pose{pub position:[f32;3],pub direction:[f32;3],pub speed:f32,pub rspeed:f32,pub linear_velocity:[f32;3],pub angular_velocity:[f32;3],pub contacts:u8,pub wheel_contact_masks:[u8;6]}
#[derive(Clone,Debug)]pub struct ActorFrame{pub slot:usize,pub kind:Kind,pub pose:Pose,
    /// Exact source evidence, structurally checked. Domain must run its scalar proof verifier before commit.
    pub proof:Value}
#[derive(Clone,Debug)]pub struct Frame{pub sequence:u32,pub tick:u32,pub actors:Vec<ActorFrame>,pub prepared:bool,pub prepared_ids:Vec<u32>,pub raw:Value}
fn motion(v:&Value)->io::Result<()>{keys(v,&["linear_velocity","angular_velocity"])?;vector::<3>(&v["linear_velocity"],25.001)?;vector::<3>(&v["angular_velocity"],20.)?;Ok(())}
fn witness(v:&Value)->io::Result<()>{keys(v,&["com","rotation_xyzw","linear_velocity","angular_velocity","inverse_inertia_row_major"])?;
    vector::<3>(&v["com"],2000.)?;let q=vector::<4>(&v["rotation_xyzw"],1.001)?;if(q.iter().map(|x|x*x).sum::<f32>()-1.).abs()>0.002{return Err(bad("quaternion unit"));}
    vector::<3>(&v["linear_velocity"],25.001)?;vector::<3>(&v["angular_velocity"],20.)?;vector::<9>(&v["inverse_inertia_row_major"],1.)?;Ok(())}
fn actor_frame(row:&Value,spec:&ActorSpec,catalog:&BTreeSet<u32>)->io::Result<ActorFrame>{
    keys(row,&["slot","kind","config_sha256","profile_sha256","state"])?;
    if uint(&row["slot"])?!=spec.slot as u64||string(row,"kind")?!=spec.kind.label()||string(row,"config_sha256")?!=spec.config_sha256||string(row,"profile_sha256")?!=spec.kind.profile_sha(){return Err(bad("actor source identity"));}
    let v=&row["state"];keys(v,&["position","direction","speed","rspeed","contacts","linear_velocity","angular_velocity","wheel_contact_masks","object_contacts","fractures","body_binding","motion_witnesses"])?;
    let position=vector::<3>(&v["position"],2000.)?;let direction=vector::<3>(&v["direction"],std::f32::consts::PI)?;
    let speed=number(&v["speed"],25.001)?;let rspeed=number(&v["rspeed"],20.)?;let linear_velocity=vector::<3>(&v["linear_velocity"],25.001)?;let angular_velocity=vector::<3>(&v["angular_velocity"],20.)?;
    if rspeed.to_bits()!=angular_velocity[1].to_bits(){return Err(bad("Y angular speed identity"));}
    let contacts=uint(&v["contacts"])?;if contacts>6{return Err(bad("support count"));}
    let masks=array(&v["wheel_contact_masks"],6)?;if masks.len()!=6{return Err(bad("six support samples"));}let mut wheel_contact_masks=[0;6];
    for(i,m)in masks.iter().enumerate(){let m=uint(m)?;if m>63{return Err(bad("support mask"));}wheel_contact_masks[i]=m as u8;}
    let b=&v["body_binding"];keys(b,&["inverse_mass","principal_inverse_diagonal","inertia_rotation_xyzw"])?;let(mass,principal)=spec.kind.binding_bits();
    if number(&b["inverse_mass"],1.)?.to_bits()!=mass||vector::<3>(&b["principal_inverse_diagonal"],1.)?.map(f32::to_bits)!=principal||
        vector::<4>(&b["inertia_rotation_xyzw"],1.)?.map(f32::to_bits)!=[0x3f3504f3,0x3f3504f3,0,0]{return Err(bad("actual body source binding"));}
    let mut contacts_ids=BTreeSet::new();for c in array(&v["object_contacts"],32)?{keys(c,&["object_id","kind","substep","point","normal","velocity"])?;
        let id=u32::try_from(uint(&c["object_id"])?).map_err(|_|bad("contact ID range"))?;if !catalog.contains(&id)||!contacts_ids.insert(id)||string(c,"kind")?!="hull"||!(1..=6).contains(&uint(&c["substep"])?){return Err(bad("object contact identity"));}
        vector::<3>(&c["point"],2000.)?;normal(&c["normal"])?;vector::<3>(&c["velocity"],25.001)?;}
    let mut receipt_ids=BTreeSet::new();let mut receipt_steps=BTreeSet::new();let mut last_step=0;
    for(i,r)in array(&v["fractures"],32)?.iter().enumerate(){let mode=string(r,"mode")?;
        if mode=="angular_corner"{keys(r,&["object_id","substep","order","point","normal","mode","budget_after","solver_after","energy_j","legacy_linear_candidate","solver_branch"])?;
            let c=&r["legacy_linear_candidate"];keys(c,&["point","normal"])?;vector::<3>(&c["point"],2000.)?;normal(&c["normal"])?;
            if !matches!(string(r,"solver_branch")?,"applied"|"noop_nonclosing"|"noop_quantized"){return Err(bad("angular branch"));}
        }else{keys(r,&["object_id","substep","order","point","normal","mode","budget_after","solver_after","energy_j"])?;if !matches!(mode,"normal_linear"|"total_linear"){return Err(bad("fracture mode"));}}
        let id=u32::try_from(uint(&r["object_id"])?).map_err(|_|bad("object ID range"))?;let step=uint(&r["substep"])?;
        if !contacts_ids.contains(&id)||!receipt_ids.insert(id)||uint(&r["order"])?!=i as u64+1||!(1..=6).contains(&step)||step<last_step||uint(&r["energy_j"])?!=8000{return Err(bad("fracture ordering/identity"));}
        last_step=step;receipt_steps.insert(step);vector::<3>(&r["point"],2000.)?;normal(&r["normal"])?;motion(&r["budget_after"])?;motion(&r["solver_after"])?;
    }
    if contacts_ids!=receipt_ids{return Err(bad("contact/receipt membership"));}
    let mut witness_steps=BTreeSet::new();for w in array(&v["motion_witnesses"],6)?{keys(w,&["substep","pre","post_solver"])?;
        let step=uint(&w["substep"])?;if !witness_steps.insert(step){return Err(bad("duplicate witness"));}witness(&w["pre"])?;witness(&w["post_solver"])?;}
    if receipt_steps!=witness_steps{return Err(bad("receipt/witness membership"));}
    Ok(ActorFrame{slot:spec.slot,kind:spec.kind,pose:Pose{position,direction,speed,rspeed,linear_velocity,angular_velocity,contacts:contacts as u8,wheel_contact_masks},proof:v.clone()})
}
pub fn response(raw:&[u8],spec:&SceneSpec,generation:u32,scene:&Scene,seq:u32)->io::Result<Frame>{
    let v=parse(raw,MAX_OUTPUT)?;keys(&v,&["version","event","generation","manifest_sha256","catalog_sha256","seq","tick","settle_ticks","map","scene_version","scene_sha256","actors","tank_contacts","fracture_claims"])?;
    check_header(&v,spec,generation)?;
    let event=string(&v,"event")?;if uint(&v["seq"])?!=seq as u64||seq>36000||uint(&v["tick"])?!=180+seq as u64*6||uint(&v["settle_ticks"])?!=180||string(&v,"map")?!=spec.map||
        uint(&v["scene_version"])?!=scene.version()as u64||string(&v,"scene_sha256")?!=scene.sha256||
        !(seq==0&&event=="ready"||seq>0&&matches!(event,"state"|"prepared")){return Err(bad("reply cadence/map/scene"));}
    let rows=array(&v["actors"],MAX_ACTORS)?;if rows.len()!=spec.actors.len(){return Err(bad("complete actor batch"));}
    let actors=rows.iter().zip(&spec.actors).map(|(a,s)|actor_frame(a,s,&spec.catalog_ids)).collect::<io::Result<Vec<_>>>()?;
    let mut pairs=BTreeSet::new();for c in array(&v["tank_contacts"],15)?{keys(c,&["slot_a","slot_b","substep","point","normal","relative_velocity"])?;
        let a=uint(&c["slot_a"])?;let b=uint(&c["slot_b"])?;if a>=b||b>=actors.len()as u64||!pairs.insert((a,b))||!(1..=6).contains(&uint(&c["substep"])?){return Err(bad("tank contact ownership"));}
        vector::<3>(&c["point"],2000.)?;normal(&c["normal"])?;vector::<3>(&c["relative_velocity"],50.002)?;}
    let mut claims=BTreeMap::new();for(i,c)in array(&v["fracture_claims"],192)?.iter().enumerate(){keys(c,&["object_id","slot","substep","order"])?;
        let id=u32::try_from(uint(&c["object_id"])?).map_err(|_|bad("claim ID"))?;let slot=uint(&c["slot"])?;
        if slot>=actors.len()as u64||!spec.catalog_ids.contains(&id)||claims.insert(id,(slot,uint(&c["substep"])?)).is_some()||uint(&c["order"])?!=i as u64+1||!(1..=6).contains(&uint(&c["substep"])?){return Err(bad("global fracture claims"));}}
    let mut actual=BTreeMap::new();for a in &actors{for r in a.proof["fractures"].as_array().unwrap(){let id=uint(&r["object_id"])?as u32;if actual.insert(id,(a.slot as u64,uint(&r["substep"])?)).is_some(){return Err(bad("two actors claimed same object"));}}}
    if claims!=actual||(event=="prepared")!=!claims.is_empty()||seq==0&&(!pairs.is_empty()||!claims.is_empty()){return Err(bad("prepared/receipt/claim agreement"));}
    Ok(Frame{sequence:seq,tick:180+seq*6,actors,prepared:event=="prepared",prepared_ids:claims.into_keys().collect(),raw:v})
}
fn check_header(v:&Value,spec:&SceneSpec,generation:u32)->io::Result<()>{if uint(&v["version"])?!=7||uint(&v["generation"])?!=generation as u64||string(v,"manifest_sha256")?!=spec.manifest_sha256||string(v,"catalog_sha256")?!=spec.catalog_sha256{return Err(bad("reply source/generation"));}Ok(())}

fn artifact_tree(path:&Path,set:&mut BTreeSet<PathBuf>,depth:usize,nodes:&mut usize)->io::Result<()>{
    *nodes+=1;if depth>8||*nodes>256{return Err(bad("artifact tree bounds"));}plain(path)?;
    for entry in fs::read_dir(path)?{let entry=entry?;plain(&entry.path())?;
        if entry.file_type()?.is_dir(){artifact_tree(&entry.path(),set,depth+1,nodes)?;}else{if set.len()>=128{return Err(bad("artifact file count"));}set.insert(entry.path().canonicalize()?);}}
    Ok(())
}
#[derive(Clone,Debug)]pub struct Artifacts{pub executable:PathBuf,root:PathBuf,pins:Vec<(PathBuf,String,usize)>}
impl Artifacts{
    pub fn load(path:&Path)->io::Result<Self>{plain(path)?;let path=path.canonicalize()?;let root=path.parent().ok_or_else(||bad("artifact parent"))?;
        let mut raw=Vec::new();fs::File::open(&path)?.take(65537).read_to_end(&mut raw)?;let v=parse(&raw,65536)?;keys(&v,&["version","executable","files"])?;if uint(&v["version"])?!=1{return Err(bad("artifact version"));}
        let relative=|s:&str|->io::Result<PathBuf>{let p=Path::new(s);if p.is_absolute()||!p.components().all(|c|matches!(c,Component::Normal(_)))||!s.starts_with("bin/"){return Err(bad("artifact relative bin path"));}owned(root,&root.join(p))};
        let executable=relative(string(&v,"executable")?)?;let mut pins=Vec::new();let mut seen=BTreeSet::new();
        for row in array(&v["files"],128)?{keys(row,&["path","sha256","bytes"])?;let p=relative(string(row,"path")?)?;if !seen.insert(p.clone()){return Err(bad("duplicate artifact"));}
            let n=usize::try_from(uint(&row["bytes"])?).map_err(|_|bad("artifact bytes"))?;if n==0||n>64*1024*1024{return Err(bad("artifact size bound"));}
            let h=string(row,"sha256")?;if read(&p,n,h)?.len()!=n{return Err(bad("artifact exact size"));}pins.push((p,h.into(),n));}
        let mut actual=BTreeSet::new();artifact_tree(&root.join("bin"),&mut actual,0,&mut 0)?;if actual!=seen||!seen.contains(&executable){return Err(bad("complete artifact tree"));}
        Ok(Self{executable,root:root.to_path_buf(),pins})
    }
    fn verify(&self)->io::Result<()>{for(p,h,n)in &self.pins{plain(p)?;if read(p,*n,h)?.len()!=*n{return Err(bad("artifact changed"));}}
        let mut actual=BTreeSet::new();artifact_tree(&self.root.join("bin"),&mut actual,0,&mut 0)?;
        if actual!=self.pins.iter().map(|p|p.0.clone()).collect(){return Err(bad("artifact tree changed"));}Ok(())}
}

enum Event{Line(Vec<u8>),Failed(io::Error)}
enum Pending{Ready(Instant),Advance(u32,Instant),Scene(Scene,Instant)}
pub struct Worker{spec:Arc<SceneSpec>,generation:u32,child:Child,send:Option<mpsc::SyncSender<Vec<u8>>>,receive:Option<mpsc::Receiver<Event>>,
    threads:Vec<thread::JoinHandle<()>>,pending:Option<Pending>,scene:Scene,seq:u32,ready:bool,prepared:Vec<u32>,ack:bool,failed:bool,stderr:Arc<Mutex<Vec<u8>>>}
impl Worker{
    pub fn launch(artifacts:Artifacts,spec:Arc<SceneSpec>,generation:u32,scene:Scene,now:Instant)->io::Result<Self>{
        if generation==0||scene!=Scene::new(&spec,&scene.ids)?{return Err(bad("launch generation/scene"));}artifacts.verify()?;spec.verify()?;
        let mut command=Command::new(&artifacts.executable);command.args(["--battle-scene"]).arg(worker_argument(&spec.manifest_path)?).args(["--scene-sha256",&spec.manifest_sha256,"--local-root"])
            .arg(worker_argument(&spec.local_root)?).args(["--generation",&generation.to_string()]).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped());
        #[cfg(windows)]{use std::os::windows::process::CommandExt;command.creation_flags(0x08000000);}
        let mut child=command.spawn()?;
        let stdin=child.stdin.take().ok_or_else(||bad("stdin pipe"))?;let stdout=child.stdout.take().ok_or_else(||bad("stdout pipe"))?;let stderr_pipe=child.stderr.take().ok_or_else(||bad("stderr pipe"))?;
        let(send,requests)=mpsc::sync_channel::<Vec<u8>>(1);let(events,receive)=mpsc::sync_channel::<Event>(2);
        let ev=events.clone();let writer=thread::spawn(move||{let mut stream=stdin;while let Ok(raw)=requests.recv(){if let Err(e)=stream.write_all(&raw).and_then(|_|stream.flush()){let _=ev.send(Event::Failed(e));break;}}});
        let reader=thread::spawn(move||{let mut stream=BufReader::new(stdout);let mut total=0usize;let run=||->io::Result<()>{loop{let mut line=Vec::new();loop{
            let available=stream.fill_buf()?;if available.is_empty(){return Err(io::Error::new(io::ErrorKind::UnexpectedEof,"IPC7 producer EOF"));}
            let n=available.iter().position(|b|*b==10).map_or(available.len(),|i|i+1);let piece=&available[..n];
            if line.len()+piece.len()>MAX_OUTPUT+1||piece.iter().any(|b|*b!=10&&!(32..=126).contains(b)){return Err(bad("output ASCII/size"));}
            let done=piece.last()==Some(&10);line.extend_from_slice(piece);stream.consume(n);if done{line.pop();break;}}
            total+=line.len();if total>256*1024*1024{return Err(bad("lifetime output bound"));}if events.send(Event::Line(line)).is_err(){return Ok(());}
        }};let mut run=run;if let Err(e)=run(){let _=events.send(Event::Failed(e));}});
        let stderr=Arc::new(Mutex::new(Vec::new()));let target=stderr.clone();let errors=thread::spawn(move||{let mut raw=Vec::new();let _=stderr_pipe.take(65537).read_to_end(&mut raw);if let Ok(mut out)=target.lock(){*out=raw;}});
        let mut worker=Self{spec,generation,child,send:Some(send),receive:Some(receive),threads:vec![writer,reader,errors],pending:Some(Pending::Ready(now)),scene,seq:0,ready:false,prepared:Vec::new(),ack:false,failed:false,stderr};
        worker.send_value(&scene_request(&worker.spec,generation,&worker.scene,0,"restore_scene"))?;Ok(worker)
    }
    fn send_value(&mut self,value:&Value)->io::Result<()>{self.send_bytes(line(value)?)}
    fn send_bytes(&mut self,raw:Vec<u8>)->io::Result<()>{self.send.as_ref().ok_or_else(||bad("closed writer"))?.try_send(raw).map_err(|_|bad("single pending writer"))}
    pub fn process_id(&self)->u32{self.child.id()}
    pub fn shutdown(mut self)->io::Result<()>{
        self.send.take();self.receive.take();let deadline=Instant::now()+Duration::from_secs(3);
        loop{if let Some(status)=self.child.try_wait()?{if status.success(){return Ok(());}return Err(bad("producer failed during EOF shutdown"));}
            if Instant::now()>deadline{return Err(io::Error::new(io::ErrorKind::TimedOut,"shared scene EOF shutdown"));}thread::sleep(Duration::from_millis(5));}
    }
    pub fn ready(&self)->bool{self.ready&&!self.failed}
    pub fn pending(&self)->bool{self.pending.is_some()}
    pub fn scene(&self)->&Scene{&self.scene}
    pub fn prepared_ids(&self)->&[u32]{&self.prepared}
    pub fn advance(&mut self,inputs:&[Input],now:Instant)->io::Result<u32>{if !self.ready()||self.pending()||!self.prepared.is_empty()||self.ack{return Err(bad("advance barrier"));}
        let seq=self.seq.checked_add(1).ok_or_else(||bad("sequence overflow"))?;let raw=advance_request(&self.spec,self.generation,&self.scene,seq,inputs)?;
        self.send_bytes(raw)?;self.pending=Some(Pending::Advance(seq,now));Ok(seq)}
    pub fn sync_removed(&mut self,scene:Scene,now:Instant)->io::Result<()>{if !self.ready()||self.pending()||self.ack||scene!=Scene::new(&self.spec,&scene.ids)?||
        self.scene.ids.iter().chain(&self.prepared).any(|id|scene.ids.binary_search(id).is_err()){return Err(bad("scene commit barrier/set"));}
        self.send_value(&scene_request(&self.spec,self.generation,&scene,self.seq,"sync_removed"))?;self.pending=Some(Pending::Scene(scene,now));Ok(())}
    pub fn take_scene_ack(&mut self)->bool{let ack=self.ack;self.ack=false;ack}
    pub fn poll(&mut self,now:Instant)->io::Result<Option<Frame>>{if self.failed{return Err(bad("worker failed"));}let result=self.poll_inner(now);if result.is_err(){self.failed=true;}result}
    fn poll_inner(&mut self,now:Instant)->io::Result<Option<Frame>>{
        if let Some(pending)=&self.pending{let(start,limit)=match pending{Pending::Ready(t)=>(*t,START_TIMEOUT),Pending::Advance(_,t)|Pending::Scene(_,t)=>(*t,REPLY_TIMEOUT)};
            if now.checked_duration_since(start).ok_or_else(||bad("clock regression"))?>limit{return Err(io::Error::new(io::ErrorKind::TimedOut,"shared scene worker deadline"));}}
        let event=match self.receive.as_ref().ok_or_else(||bad("closed receiver"))?.try_recv(){Ok(e)=>Some(e),Err(mpsc::TryRecvError::Empty)=>None,Err(_)=>return Err(bad("producer channel closed"))};
        let Some(event)=event else{if let Some(pending)=&self.pending{let(start,limit)=match pending{Pending::Ready(t)=>(*t,START_TIMEOUT),Pending::Advance(_,t)|Pending::Scene(_,t)=>(*t,REPLY_TIMEOUT)};
            if now.checked_duration_since(start).ok_or_else(||bad("clock regression"))?>limit{return Err(io::Error::new(io::ErrorKind::TimedOut,"shared scene worker deadline"));}}
            if self.stderr.lock().map_err(|_|bad("stderr lock"))?.len()>65536{return Err(bad("stderr overflow"));}return Ok(None);};
        let raw=match event{Event::Line(raw)=>raw,Event::Failed(e)=>return Err(e)};
        let pending=self.pending.as_ref().ok_or_else(||bad("unsolicited producer frame"))?;
        if let Pending::Scene(scene,_)=pending{let v=parse(&raw,MAX_OUTPUT)?;keys(&v,&["version","event","generation","manifest_sha256","catalog_sha256","advance_seq","tick","scene_version","removed_object_ids","scene_sha256"])?;
            check_header(&v,&self.spec,self.generation)?;
            if string(&v,"event")?!="scene_synced"||uint(&v["advance_seq"])?!=self.seq as u64||uint(&v["tick"])?!=180+self.seq as u64*6||
                uint(&v["scene_version"])?!=scene.version()as u64||string(&v,"scene_sha256")?!=scene.sha256||v["removed_object_ids"]!=json!(scene.ids){return Err(bad("exact scene ACK"));}
            self.scene=scene.clone();self.prepared.clear();self.pending=None;self.ack=true;return Ok(None);
        }
        let seq=match pending{Pending::Ready(_)=>0,Pending::Advance(seq,_)=>*seq,Pending::Scene(..)=>unreachable!()};
        let frame=response(&raw,&self.spec,self.generation,&self.scene,seq)?;
        self.ready=true;self.seq=seq;self.prepared=frame.prepared_ids.clone();self.pending=None;Ok(Some(frame))
    }
}
impl Drop for Worker{fn drop(&mut self){self.send.take();self.receive.take();let _=self.child.kill();let _=self.child.wait();for thread in self.threads.drain(..){let _=thread.join();}}}

#[cfg(test)]#[path="scene_worker/tests.rs"]mod tests;

#[cfg(test)]#[path="scene_worker/tests_p06t_extended.rs"]mod tests_p06t_extended;
