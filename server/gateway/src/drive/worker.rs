//! Owned, hash-bound test_lab physics process. No native IDs or client poses.
//! IPC is one bounded JSON line per fixed six-step request; never catch up.
use std::{collections::BTreeSet,fmt,fs,io::{self,Read,Write},path::{Path,PathBuf},
    process::{Child,Command,Stdio},sync::{Arc,Mutex,mpsc,atomic::{AtomicBool,Ordering}},thread,
    time::{Duration,Instant}};
use serde::{Deserialize,Deserializer,de::{self,Visitor,MapAccess,SeqAccess}};
use serde_json::{Value,Map,Number};
use sha2::{Digest,Sha256};

pub const STEP:Duration=Duration::from_millis(100);
pub const MAX_SEQUENCE:u32=36000;
pub const START_TIMEOUT:Duration=Duration::from_secs(120);
pub const REPLY_TIMEOUT:Duration=Duration::from_millis(500);
pub const MAX_LAG:Duration=Duration::from_millis(500);
fn bad()->io::Error {io::Error::new(io::ErrorKind::InvalidData,"map-drive worker contract")}

// serde_json::Value normally accepts duplicate keys. Reject them at EVERY depth.
struct Unique(Value);
impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D:Deserializer<'de>>(d:D)->Result<Self,D::Error> {
        struct V;
        impl<'de> Visitor<'de> for V {
            type Value=Unique;
            fn expecting(&self,f:&mut fmt::Formatter)->fmt::Result {f.write_str("bounded unique JSON")}
            fn visit_bool<E:de::Error>(self,v:bool)->Result<Unique,E>{Ok(Unique(v.into()))}
            fn visit_i64<E:de::Error>(self,v:i64)->Result<Unique,E>{Ok(Unique(v.into()))}
            fn visit_u64<E:de::Error>(self,v:u64)->Result<Unique,E>{Ok(Unique(v.into()))}
            fn visit_f64<E:de::Error>(self,v:f64)->Result<Unique,E>{Ok(Unique(Value::Number(Number::from_f64(v).ok_or_else(||E::custom("finite"))?)))}
            fn visit_str<E:de::Error>(self,v:&str)->Result<Unique,E>{Ok(Unique(v.into()))}
            fn visit_string<E:de::Error>(self,v:String)->Result<Unique,E>{Ok(Unique(v.into()))}
            fn visit_unit<E:de::Error>(self)->Result<Unique,E>{Ok(Unique(Value::Null))}
            fn visit_seq<A:SeqAccess<'de>>(self,mut a:A)->Result<Unique,A::Error>{
                let mut v=Vec::new();while let Some(Unique(x))=a.next_element()? {
                    if v.len()>=512{return Err(de::Error::custom("array bound"));}v.push(x);
                }Ok(Unique(Value::Array(v)))
            }
            fn visit_map<A:MapAccess<'de>>(self,mut a:A)->Result<Unique,A::Error>{
                let mut v=Map::new();while let Some((k,Unique(x)))=a.next_entry::<String,Unique>()? {
                    if v.len()>=256 || v.insert(k,x).is_some(){return Err(de::Error::custom("duplicate/bound"));}
                }Ok(Unique(Value::Object(v)))
            }
        }d.deserialize_any(V)
    }
}
pub(crate) fn json(raw:&[u8],maximum:usize)->io::Result<Value> {
    if raw.is_empty() || raw.len()>maximum{return Err(bad());}
    let Unique(v)=serde_json::from_slice(raw).map_err(|_|bad())?;
    fn depth(v:&Value,d:usize,n:&mut usize)->io::Result<()> {
        if d>12 || *n>=4096{return Err(bad());}*n+=1;
        match v {Value::Object(o)=>for x in o.values(){depth(x,d+1,n)?;},Value::Array(a)=>for x in a{depth(x,d+1,n)?;},_=>{}}Ok(())
    }depth(&v,0,&mut 0)?;Ok(v)
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
    pub bounds:[f32;4],pub spawn:[f32;3],pub spawn_yaw:f32}
impl MapSpec {
    fn load(root:&Path,v:&Value)->io::Result<Self>{
        fields(v,&["asset","arena_type_id","config","config_sha256"])?;
        let asset=text(v,"asset")?;let id=uint(&v["arena_type_id"])?;
        if !matches!((asset,id),("01_karelia",1)|("05_prohorovka",4)){return Err(bad());}
        let config=owned(root,Path::new(text(v,"config")?))?;let hash=text(v,"config_sha256")?;hash_text(hash)?;
        let raw=read(&config,16384)?;if format!("{:x}",Sha256::digest(&raw))!=hash{return Err(bad());}
        let c=json(&raw,16384)?;
        fields(&c,&["version","profile","map","terrain","obstacles","spawn_origin","spawn_yaw","body_half_extents",
            "body_center_offset","wheel_points","mass_kg","max_forward_mps","max_reverse_mps","engine_max_torque_nm",
            "wheel_radius","suspension_min","suspension_max","track_max_brake_torque","bounds_xz"])?;
        if uint(&c["version"])?!=1 || text(&c,"profile")?!="test_lab" || text(&c,"map")?!=asset{return Err(bad());}
        for k in ["terrain","obstacles"]{fields(&c[k],&["path","sha256"])?;hash_text(text(&c[k],"sha256")?)?;owned(root,Path::new(text(&c[k],"path")?))?;}
        let a=c["bounds_xz"].as_array().ok_or_else(bad)?;if a.len()!=4{return Err(bad());}
        let bounds=[number(&a[0],-1000.,0.)?,number(&a[1],-1000.,0.)?,number(&a[2],0.,1000.)?,number(&a[3],0.,1000.)?];
        let spawn=vector(&c["spawn_origin"],-1000.,1000.)?;let yaw=number(&c["spawn_yaw"],-std::f32::consts::PI,std::f32::consts::PI)?;
        if bounds[2]-bounds[0]<100. || bounds[3]-bounds[1]<100. || spawn[0]<bounds[0]+5. || spawn[0]>bounds[2]-5.
            || spawn[2]<bounds[1]+5. || spawn[2]>bounds[3]-5. {return Err(bad());}
        Ok(Self {asset:asset.into(),arena_type_id:id as i32,config,config_sha256:hash.into(),bounds,spawn,spawn_yaw:yaw})
    }
}
#[derive(Clone,Debug)]
struct Asset {path:PathBuf,bytes:u64,sha256:String}
#[derive(Clone,Debug)]
pub struct Pool {pub local_root:PathBuf,pub maps:Vec<MapSpec>,pub sha256:String,executable:PathBuf,
    runtime:PathBuf,assets:Vec<Asset>}
impl Pool {
    pub fn load(local_root:&Path,path:&Path)->io::Result<Self>{
        non_reparse(local_root)?;let root=local_root.canonicalize()?;let raw=read(&owned(&root,path)?,16384)?;
        let v=json(&raw,16384)?;fields(&v,&["version","profile","worker","maps"])?;
        if uint(&v["version"])?!=1 || text(&v,"profile")?!="test_lab"{return Err(bad());}
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
        let maps=specs.iter().map(|m|MapSpec::load(&root,m)).collect::<io::Result<Vec<_>>>()?;
        if maps[0].arena_type_id==maps[1].arena_type_id || maps[0].config==maps[1].config{return Err(bad());}
        let out=Self{local_root:root,maps,sha256:format!("{:x}",Sha256::digest(&raw)),executable,runtime,assets};
        out.verify_assets()?;Ok(out)
    }
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

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct Input {pub throttle:i8,pub steer:i8,pub brake:bool}
impl Input {pub const STOP:Self=Self{throttle:0,steer:0,brake:true};}
pub fn request(seq:u32,input:Input)->io::Result<Vec<u8>> {
    if seq==0 || seq>MAX_SEQUENCE || !(-1..=1).contains(&input.throttle) || !(-1..=1).contains(&input.steer)
        || (input.brake && (input.throttle!=0 || input.steer!=0)){return Err(bad());}
    let mut b=serde_json::to_vec(&serde_json::json!({"version":1,"op":"advance","seq":seq,"ticks":6,
        "input":{"throttle":input.throttle,"steer":input.steer,"brake":input.brake}})).map_err(|_|bad())?;
    if b.len()>1024{return Err(bad());}b.push(b'\n');Ok(b)
}
#[derive(Clone,Debug,PartialEq)]
pub struct Pose {pub position:[f32;3],pub direction:[f32;3],pub speed:f32,pub rspeed:f32,pub contacts:u8,
    pub linear_velocity:[f32;3],pub angular_velocity:[f32;3],pub wheel_contact_masks:[u8;6]}
#[derive(Clone,Debug,PartialEq)]
pub struct State {pub seq:u32,pub tick:u32,pub pose:Pose}
pub fn response(raw:&[u8],map:&MapSpec,seq:u32)->io::Result<State>{
    response_at_spawn(raw,map,seq,None)
}
pub fn response_at_spawn(raw:&[u8],map:&MapSpec,seq:u32,expected_spawn:Option<[f32;3]>)->io::Result<State>{
    if !raw.is_ascii(){return Err(bad());}let v=json(raw,1024)?;
    fields(&v,&["version","event","seq","tick","settle_ticks","map","config_sha256","state"])?;
    if uint(&v["version"])?!=1 || text(&v,"event")?!=if seq==0{"ready"}else{"state"}
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
    Ok(State{seq,tick:180+seq*6,pose})
}
fn line(reader:&mut impl Read)->io::Result<Vec<u8>> {
    let mut raw=Vec::new();loop{let mut b=[0];if reader.read(&mut b)?!=1{return Err(bad());}
        if b[0]==10{return Ok(raw);}if raw.len()>=1024 || b[0]==0 || b[0]>127{return Err(bad());}raw.push(b[0]);}
}

enum Event {Line(Instant,Vec<u8>),Failed}
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
    expected_spawn:Option<[f32;3]>,pending:Option<(u32,Instant)>,ready:bool,last_seq:u32}
impl Worker {
    pub fn launch(pool:Arc<Pool>,map:MapSpec,generation:u32,now:Instant)->io::Result<Self>{
        Self::launch_at_spawn(pool,map,generation,now,None)
    }
    pub fn launch_at_spawn(pool:Arc<Pool>,map:MapSpec,generation:u32,now:Instant,spawn:Option<[f32;3]>)->io::Result<Self>{
        if generation==0{return Err(bad());}
        if let Some(target)=spawn {
            if target.iter().any(|v| !v.is_finite()) || (target[1]-map.spawn[1]).abs()>f32::EPSILON
                || target[0]<map.bounds[0]+5. || target[0]>map.bounds[2]-5.
                || target[2]<map.bounds[1]+5. || target[2]>map.bounds[3]-5.
                || (target[0]-map.spawn[0]).abs()>12. || (target[2]-map.spawn[2]).abs()>12. { return Err(bad()); }
        }
        let (events,receiver)=mpsc::sync_channel(4);let (sender,commands)=mpsc::sync_channel::<Vec<u8>>(1);
        let child=Arc::new(Mutex::new(None::<Child>));let cancel=Arc::new(AtomicBool::new(false));
        let exit=Arc::new(Mutex::new(None));let exit_thread=exit.clone();
        let slot=child.clone();let revoked=cancel.clone();let selected=map.clone();
        thread::spawn(move||{
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
                #[cfg(windows)] {use std::os::windows::process::CommandExt;cmd.creation_flags(0x08000000);}
                let mut c=cmd.spawn()?;let mut input=c.stdin.take().ok_or_else(bad)?;
                let mut output=c.stdout.take().ok_or_else(bad)?;let mut errors=c.stderr.take().ok_or_else(bad)?;
                {let mut guard=slot.lock().map_err(|_|bad())?;if revoked.load(Ordering::SeqCst){drop(input);reap_owned(c,generation,exit_thread.clone());return Err(bad());}*guard=Some(c);}
                let e=events.clone();let stopped=revoked.clone();
                thread::spawn(move||{while let Ok(bytes)=commands.recv(){if stopped.load(Ordering::SeqCst){break;}
                    if input.write_all(&bytes).and_then(|_|input.flush()).is_err(){let _=e.try_send(Event::Failed);break;}}});
                let e=events.clone();thread::spawn(move||{let mut b=[0;1024];let mut size=0usize;
                    loop {match errors.read(&mut b){Ok(0)=>break,Ok(n)=>{
                        let keep=n.min(4096-size);let value=String::from_utf8_lossy(&b[..keep]);
                        println!("MAP_DRIVE_WORKER_STDERR generation={generation} bytes={keep} truncated={} text={}",keep<n,serde_json::to_string(&value).unwrap_or_else(|_|"\"diagnostic_encoding_error\"".into()));
                        size+=keep;let _=e.try_send(Event::Failed);if size>=4096{break;}
                    },Err(_)=>{let _=e.try_send(Event::Failed);break;}}}
                });
                loop {let raw=line(&mut output)?;if revoked.load(Ordering::SeqCst){break;}
                    events.try_send(Event::Line(Instant::now(),raw)).map_err(|_|bad())?;}
                Ok(())
            };
            if let Err(error)=run(){if !revoked.load(Ordering::SeqCst){
                let message=error.to_string().chars().take(1024).collect::<String>();
                println!("MAP_DRIVE_WORKER_IO_ERROR generation={generation} kind={:?} message={}",error.kind(),serde_json::to_string(&message).unwrap_or_else(|_|"\"diagnostic_encoding_error\"".into()));
                let _=events.try_send(Event::Failed);
            }}
        });
        Ok(Self{generation,map,receiver,sender:Some(sender),child,exit,cancel,started:now,expected_spawn:spawn,
            pending:None,ready:false,last_seq:0})
    }
    pub fn pending(&self)->bool{self.pending.is_some()}
    pub fn ready(&self)->bool{self.ready}
    pub fn process_id(&self)->Option<u32>{self.child.lock().ok().and_then(|c|c.as_ref().map(Child::id))}
    pub fn advance(&mut self,input:Input,now:Instant)->io::Result<u32>{
        if !self.ready || self.pending.is_some() || now<self.started || self.last_seq>=MAX_SEQUENCE{return Err(bad());}
        let seq=self.last_seq+1;let raw=request(seq,input)?;
        self.sender.as_ref().ok_or_else(bad)?.try_send(raw).map_err(|_|bad())?;
        self.pending=Some((seq,now));Ok(seq)
    }
    pub fn poll(&mut self,now:Instant)->io::Result<Option<State>>{
        if now<self.started || (!self.ready && now.duration_since(self.started)>START_TIMEOUT)
            || self.pending.is_some_and(|(_,sent)|now.duration_since(sent)>REPLY_TIMEOUT){return Err(bad());}
        match self.receiver.try_recv(){
            Ok(Event::Failed)|Err(mpsc::TryRecvError::Disconnected)=>Err(bad()),
            Err(mpsc::TryRecvError::Empty)=>Ok(None),
            Ok(Event::Line(received,raw))=>{
                let seq=if !self.ready {0}else{let (seq,sent)=self.pending.ok_or_else(bad)?;if received<sent{return Err(bad());}seq};
                let state=response_at_spawn(&raw,&self.map,seq,self.expected_spawn)?;self.ready=true;self.last_seq=seq;self.pending=None;Ok(Some(state))
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

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    pub(crate) fn map()->MapSpec{MapSpec{asset:"01_karelia".into(),arena_type_id:1,config:"unit".into(),config_sha256:"a".repeat(64),bounds:[-500.,-500.,500.,500.],spawn:[0.,10.,0.],spawn_yaw:0.}}
    fn good(seq:u32)->Value{serde_json::json!({"version":1,"event":if seq==0{"ready"}else{"state"},"seq":seq,"tick":180+seq*6,"settle_ticks":180,"map":"01_karelia","config_sha256":"a".repeat(64),
        "state":{"position":[0,10,0],"direction":[0,0,0],"speed":0,"rspeed":0,"contacts":6,"linear_velocity":[0,0,0],"angular_velocity":[0,0,0],"wheel_contact_masks":[63,63,63,63,63,63]}})}
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
        for throttle in -1..=1{for steer in -1..=1{let b=request(1,Input{throttle,steer,brake:false}).unwrap();let v=json(&b,1024).unwrap();assert_eq!(v["ticks"],6);assert!(v.get("position").is_none());}}
        assert!(request(1,Input{throttle:1,steer:0,brake:true}).is_err());
        assert!(request(1,Input{throttle:0,steer:2,brake:false}).is_err());
    }
    #[test]fn actual_packaged_pool_and_saved_worker_output_readonly_contract(){
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
        let pool=Pool::load(&root,&root.join("server/map-drive/pool.json")).unwrap();
        assert_eq!(pool.sha256,"8994553cd223678e093c44de9cb5bfa78ccfedb5c2b3ff0fe49e1ed84e8cbc12");
        assert_eq!(pool.assets.len(),16);
        let raw=read(&root.join("evidence/20261005-p02-map-drive/physics/packaged-worker-01/stdout.jsonl"),4096).unwrap();
        let lines=raw.split(|b|*b==10).filter(|b|!b.is_empty()).collect::<Vec<_>>();assert_eq!(lines.len(),2);
        let map=pool.maps.iter().find(|m|m.asset=="01_karelia").unwrap();
        for (i,line) in lines.iter().enumerate(){let s=response(line,map,i as u32).unwrap();assert_eq!(s.pose.contacts,5);assert_eq!(s.pose.wheel_contact_masks,[59;6]);}
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
    fn fixture_pool()->(PathBuf,PathBuf,Value){
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
            started:now,pending:None,ready:false,last_seq:0},send,recv)
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
        let local=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
        let pool=Arc::new(Pool::load(&local,&local.join("server/map-drive/pool.json")).unwrap());let out=scratch();let mut proof=Vec::new();
        for (i,map) in pool.maps.iter().enumerate(){
            let begin=Instant::now();let mut w=Worker::launch(pool.clone(),map.clone(),(i+1) as u32,begin).unwrap();
            fn wait(w:&mut Worker,deadline:Instant)->State{loop{assert!(Instant::now()<deadline,"bounded own IPC deadline");
                if let Some(s)=w.poll(Instant::now()).unwrap(){return s;}thread::sleep(Duration::from_millis(5));}}
            let initial=wait(&mut w,begin+Duration::from_secs(30));assert_eq!(initial.seq,0);let pid=w.process_id().unwrap();
            let mut ticks=vec![initial.tick];let mut samples=Vec::new();
            for input in [Input::STOP,Input{throttle:1,steer:0,brake:false},Input::STOP]{
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
