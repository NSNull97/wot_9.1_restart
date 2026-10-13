//! Test binary only. Bounded byte observation; no replacement IPC or acceptance.
use super::*;
use std::collections::BTreeMap;
const CHILD_BYTES:usize=16*1024*1024;
const ALL_BYTES:usize=144*1024*1024;
static REGISTRY:std::sync::OnceLock<Mutex<BTreeMap<(String,u32),Tap>>>=std::sync::OnceLock::new();
static BYTES:std::sync::atomic::AtomicUsize=std::sync::atomic::AtomicUsize::new(0);
static REGISTRATIONS:std::sync::atomic::AtomicUsize=std::sync::atomic::AtomicUsize::new(0);
pub(super) type Tap=Arc<Mutex<Capture>>;
#[derive(Default)]pub(super) struct Capture {requests:Vec<Vec<u8>>,replies:Vec<Vec<u8>>,frames:Vec<State>,stderr:Vec<u8>,bytes:usize,error:Option<String>,reader_done:bool,writer_started:bool,writer_done:bool,stderr_started:bool,stderr_done:bool}
pub(super) struct Completion{tap:Option<Tap>,kind:u8}
pub(super) fn completion(tap:&Option<Tap>,kind:u8)->io::Result<Completion>{
    if let Some(t)=tap{let mut c=t.lock().map_err(|_|bad())?;match kind{0=>(),1=>c.writer_started=true,2=>c.stderr_started=true,_=>return Err(bad())}}
    Ok(Completion{tap:tap.clone(),kind})
}
impl Drop for Completion{fn drop(&mut self){if let Some(t)=&self.tap{if let Ok(mut c)=t.lock(){match self.kind{0=>c.reader_done=true,1=>c.writer_done=true,2=>c.stderr_done=true,_=>c.error=Some("observer completion kind".into())}}}}}
pub(super) fn stderr(tap:&Option<Tap>,raw:&[u8])->io::Result<()>{let Some(t)=tap else{return Ok(())};let mut c=t.lock().map_err(|_|bad())?;
    let keep=raw.len().min(4096-c.stderr.len());c.stderr.extend_from_slice(&raw[..keep]);c.error=Some("actual stderr is nonempty (first4096 bytes retained)".into());Ok(())}
pub(crate) struct Probe {key:(String,u32),tap:Tap,exit:Option<Arc<Mutex<Option<ExitEvidence>>>>}
fn registry()->&'static Mutex<BTreeMap<(String,u32),Tap>>{REGISTRY.get_or_init(||Mutex::new(BTreeMap::new()))}
pub(crate) fn verified_profile(pool:&Pool,map:&MapSpec)->io::Result<ram_proof::Profile>{pool.angular_profile(map)}
pub(super) fn lookup(config:&str,generation:u32)->io::Result<Option<Tap>>{
    Ok(registry().lock().map_err(|_|bad())?.get(&(config.into(),generation)).cloned())
}
pub(crate) fn register(config:&str,generation:u32)->io::Result<Probe>{
    hash_text(config)?;if generation==0{return Err(bad());}
    let mut r=registry().lock().map_err(|_|bad())?;let key=(config.into(),generation);
    if r.contains_key(&key)||REGISTRATIONS.load(Ordering::SeqCst)>=9{return Err(bad());}
    REGISTRATIONS.fetch_add(1,Ordering::SeqCst);let tap=Arc::new(Mutex::new(Capture::default()));r.insert(key.clone(),tap.clone());
    Ok(Probe{key,tap,exit:None})
}
pub(super) fn error(tap:&Option<Tap>,message:&str){if let Some(t)=tap{if let Ok(mut c)=t.lock(){
    if c.error.is_none(){c.error=Some(message.chars().take(1024).collect());}
}}}
pub(super) fn record(tap:&Option<Tap>,request:bool,raw:&[u8])->io::Result<()>{
    let Some(t)=tap else{return Ok(())};let mut c=t.lock().map_err(|_|bad())?;
    let rows=if request{c.requests.len()}else{c.replies.len()};
    if c.error.is_some()||rows>=256||c.bytes+raw.len()>CHILD_BYTES
        ||BYTES.fetch_update(Ordering::SeqCst,Ordering::SeqCst,|n|n.checked_add(raw.len()).filter(|n|*n<=ALL_BYTES)).is_err(){
        c.error=Some("bounded actual IPC capture overflow or earlier error".into());return Err(bad());}
    c.bytes+=raw.len();if request{c.requests.push(raw.to_vec());}else{c.replies.push(raw.to_vec());}Ok(())
}
pub(super) fn parsed(config:&str,generation:u32,state:&State)->io::Result<()>{
    let Some(t)=lookup(config,generation)? else{return Ok(())};let mut c=t.lock().map_err(|_|bad())?;
    if c.frames.len()>=256 {c.error=Some("parsed frame observer overflow".into());return Err(bad());}
    c.frames.push(state.clone());Ok(())
}
impl Probe {
    pub(crate) fn attach(&mut self,w:&Worker)->io::Result<()>{
        if self.exit.is_some()||self.key!=(w.map.config_sha256.clone(),w.generation){return Err(bad());}
        self.exit=Some(w.exit.clone());Ok(())
    }
    pub(crate) fn rows(&self)->io::Result<(Vec<Vec<u8>>,Vec<Vec<u8>>)> {
        let c=self.tap.lock().map_err(|_|bad())?;if c.error.is_some(){return Err(bad());}Ok((c.requests.clone(),c.replies.clone()))
    }
    pub(crate) fn frames(&self)->io::Result<Vec<State>>{let c=self.tap.lock().map_err(|_|bad())?;
        if c.error.is_some(){return Err(bad());}Ok(c.frames.clone())}
    pub(crate) fn snapshot(&self)->Value {
        match self.tap.lock(){Ok(c)=>serde_json::json!({"config_sha256":self.key.0,"generation":self.key.1,
            "requests":c.requests.len(),"replies":c.replies.len(),"parsed_frames":c.frames.len(),"bytes":c.bytes,"error":c.error,"reader_done":c.reader_done,"writer_started":c.writer_started,"writer_done":c.writer_done,"stderr_started":c.stderr_started,"stderr_done":c.stderr_done,"stderr_bytes_retained":c.stderr.len()}),
            Err(_)=>serde_json::json!({"error":"capture mutex poisoned"})}
    }
    pub(crate) fn io_complete(&self)->io::Result<bool>{let c=self.tap.lock().map_err(|_|bad())?;Ok(c.reader_done&&(!c.writer_started||c.writer_done)&&(!c.stderr_started||c.stderr_done))}
    pub(crate) fn exit(&self)->io::Result<Option<Value>> {
        Ok(self.exit.as_ref().ok_or_else(bad)?.lock().map_err(|_|bad())?.map(|e|
            serde_json::json!({"forced":e.forced,"code":e.code,"reaped":e.reaped})))
    }
    pub(crate) fn save(&self,dir:&Path)->io::Result<Value>{
        let c=self.tap.lock().map_err(|_|bad())?;let mut pins=serde_json::Map::new();
        for(name,rows,request)in[("requests.jsonl",&c.requests,true),("stdout.jsonl",&c.replies,false)]{
            let path=dir.join(name);let mut f=fs::OpenOptions::new().create_new(true).write(true).open(&path)?;
            let mut sha=Sha256::new();let mut bytes=0;
            for row in rows {f.write_all(row)?;sha.update(row);bytes+=row.len();if !request{f.write_all(b"\n")?;sha.update(b"\n");bytes+=1;}}
            pins.insert(name.into(),serde_json::json!({"path":path,"bytes":bytes,"sha256":format!("{:x}",sha.finalize())}));
        }
        let path=dir.join("stderr.bin");let mut f=fs::OpenOptions::new().create_new(true).write(true).open(&path)?;f.write_all(&c.stderr)?;
        pins.insert("stderr.bin".into(),serde_json::json!({"path":path,"bytes":c.stderr.len(),"sha256":format!("{:x}",Sha256::digest(&c.stderr))}));
        pins.insert("complete_io_snapshot".into(),Value::Bool(c.reader_done&&(!c.writer_started||c.writer_done)&&(!c.stderr_started||c.stderr_done)));
        Ok(Value::Object(pins))
    }
    pub(crate) fn unregister(&self)->io::Result<()>{
        let mut r=registry().lock().map_err(|_|bad())?;
        if !r.remove(&self.key).is_some_and(|v|Arc::ptr_eq(&v,&self.tap)){return Err(bad());}Ok(())
    }
}

#[test]fn real_capture_unregistered_path_and_bounds_are_explicit(){
    assert!(lookup(&"f".repeat(64),u32::MAX).unwrap().is_none());record(&None,true,b"x").unwrap();
    let tap=Some(Arc::new(Mutex::new(Capture::default())));
    for _ in 0..256{record(&tap,false,b"{}").unwrap();}
    assert!(record(&tap,false,b"{}").is_err());assert!(tap.unwrap().lock().unwrap().error.is_some());
    let tap=Some(Arc::new(Mutex::new(Capture{bytes:CHILD_BYTES,..Capture::default()})));
    assert!(record(&tap,true,b"x").is_err());assert!(tap.unwrap().lock().unwrap().error.is_some());
    let tap=Some(Arc::new(Mutex::new(Capture::default())));let read=completion(&tap,0).unwrap();let write=completion(&tap,1).unwrap();let err=completion(&tap,2).unwrap();
    assert!(!tap.as_ref().unwrap().lock().unwrap().reader_done);drop(write);drop(err);drop(read);
    {let c=tap.as_ref().unwrap().lock().unwrap();assert!(c.reader_done&&c.writer_done&&c.stderr_done);}
    stderr(&tap,b"late stderr").unwrap();let c=tap.as_ref().unwrap().lock().unwrap();assert_eq!(c.stderr,b"late stderr");assert!(c.error.is_some());
}
