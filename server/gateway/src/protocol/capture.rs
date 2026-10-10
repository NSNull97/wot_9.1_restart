//! Opt-in bounded raw native UDP observer. Never records the identity HTTP link.
use std::{fs::{self,File,OpenOptions},io::{self,Write},net::SocketAddr,path::{Path,PathBuf},time::Instant};

const MAX_PACKETS:usize=10_000;
const MAX_WIRE_BYTES:usize=16*1024*1024;
fn invalid(message:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidInput,message)}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Profile {Ordinary,MapDrivePhase2V1,SharedWorldV1,IntegratedWorldV1}
impl Profile {
    pub fn for_map_drive(capture_path:Option<&str>,name:Option<&str>)->io::Result<Self> {
        match name {
            None=>Ok(Self::Ordinary),
            Some("map-drive-phase2-v1") if capture_path.is_some_and(|p|!p.is_empty())=>Ok(Self::MapDrivePhase2V1),
            _=>Err(invalid("unknown capture profile or missing map-drive capture path")),
        }
    }
    fn name(self)->Option<&'static str>{match self{Self::Ordinary=>None,Self::MapDrivePhase2V1=>Some("map-drive-phase2-v1"),Self::SharedWorldV1=>Some("shared-world-v1"),Self::IntegratedWorldV1=>Some("integrated-world-v1")}}
    fn limits(self)->(usize,usize){match self{
        Self::Ordinary=>(MAX_PACKETS,MAX_WIRE_BYTES),Self::MapDrivePhase2V1|Self::SharedWorldV1|Self::IntegratedWorldV1=>(48_000,32*1024*1024),
    }}
}

#[derive(Clone,Copy)]
pub enum Channel { Login, Base }
impl Channel {
    fn name(self)->&'static str {match self {Self::Login=>"login",Self::Base=>"base"}}
    fn direction(self,incoming:bool)->&'static str {match (self,incoming) {
        (Self::Login,true)=>"client_to_server",(Self::Login,false)=>"server_to_client",
        (Self::Base,true)=>"base_client_to_server",(Self::Base,false)=>"base_server_to_client",
    }}
}

pub struct Recorder {root:PathBuf,manifest:File,started:Instant,count:usize,bytes:usize,disabled:bool,
                     packet_limit:usize,byte_limit:usize}
impl Recorder {
    pub fn open(path:&str,local_root:&Path)->io::Result<Self> {
        Self::open_bounded(Path::new(path),local_root,MAX_PACKETS,MAX_WIRE_BYTES)
    }
    pub fn open_profile(path:&str,local_root:&Path,profile:Profile)->io::Result<Self> {
        let (packets,bytes)=profile.limits();Self::open_with_header(Path::new(path),local_root,packets,bytes,profile.name())
    }
    fn open_bounded(path:&Path,local_root:&Path,packet_limit:usize,byte_limit:usize)->io::Result<Self> {
        Self::open_with_header(path,local_root,packet_limit,byte_limit,None)
    }
    fn open_with_header(path:&Path,local_root:&Path,packet_limit:usize,byte_limit:usize,profile:Option<&str>)->io::Result<Self> {
        if !path.is_absolute() {return Err(invalid("absolute capture directory required"));}
        let parent=path.parent().ok_or_else(||invalid("capture parent missing"))?.canonicalize()?;
        if !parent.starts_with(local_root) {return Err(invalid("capture parent escapes local root"));}
        if !path.exists() {fs::create_dir(path)?;}
        let root=path.canonicalize()?;
        if !root.starts_with(local_root) || !root.is_dir() || fs::read_dir(&root)?.next().is_some() {
            return Err(invalid("capture needs a fresh empty local directory"));
        }
        let manifest=OpenOptions::new().write(true).create_new(true).open(root.join("packets.jsonl"))?;
        let mut this=Self {root,manifest,started:Instant::now(),count:0,bytes:0,disabled:false,packet_limit,byte_limit};
        let mut header=serde_json::json!({"event":"capture_started","max_packets":packet_limit,"max_wire_bytes":byte_limit,
            "scope":"native UDP only; identity HTTP and plaintext credentials excluded; packet hashes computed after run"});
        // Historical readers keep their exact header. Only an explicit named
        // diagnostic profile publishes this extra field and enlarged limits.
        if let Some(name)=profile {header["profile"]=serde_json::Value::String(name.to_owned());}
        this.event(header)?;
        println!("CAPTURE_READY max_packets={packet_limit} max_wire_bytes={byte_limit}");
        Ok(this)
    }
    fn event(&mut self,value:serde_json::Value)->io::Result<()> {
        serde_json::to_writer(&mut self.manifest,&value)?;self.manifest.write_all(b"\n")?;self.manifest.flush()
    }
    /// Observer failure disables capture explicitly; it never changes UDP replies.
    pub fn observe(&mut self,channel:Channel,incoming:bool,peer:SocketAddr,bytes:&[u8]) {
        if self.disabled {return;}
        if let Err(error)=self.write_packet(channel,incoming,peer,bytes) {
            self.disabled=true;println!("CAPTURE_ERROR disabled=true kind={:?} error={error}",error.kind());
        }
    }
    fn write_packet(&mut self,channel:Channel,incoming:bool,peer:SocketAddr,bytes:&[u8])->io::Result<()> {
        if self.count>=self.packet_limit || self.bytes.saturating_add(bytes.len())>self.byte_limit {
            self.disabled=true;
            println!("CAPTURE_LIMIT packets={} wire_bytes={} service_continues=true",self.count,self.bytes);
            return self.event(serde_json::json!({"event":"capture_limit","packets":self.count,"wire_bytes":self.bytes,
                "elapsed_seconds":self.started.elapsed().as_secs_f64()}));
        }
        let direction=channel.direction(incoming);
        let file=format!("packet-{:06}-{direction}.bin",self.count);
        let mut output=OpenOptions::new().write(true).create_new(true).open(self.root.join(&file))?;
        output.write_all(bytes)?;output.flush()?;
        self.event(serde_json::json!({"event":"packet","index":self.count,"file":file,"direction":direction,
            "channel":channel.name(),"peer":peer.to_string(),"bytes":bytes.len(),
            "elapsed_seconds":self.started.elapsed().as_secs_f64()}))?;
        self.count+=1;self.bytes+=bytes.len();Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn location()->(PathBuf,PathBuf){
        use std::sync::atomic::{AtomicUsize,Ordering};static NEXT:AtomicUsize=AtomicUsize::new(0);
        let local=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/unified-wire");
        fs::create_dir_all(&local).unwrap();let local=local.canonicalize().unwrap();
        let epoch=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let path=local.join(format!("profile-{}-{epoch}-{}",std::process::id(),NEXT.fetch_add(1,Ordering::Relaxed)));(local,path)
    }
    fn events(p:&Path)->Vec<serde_json::Value>{fs::read_to_string(p.join("packets.jsonl")).unwrap().lines().map(|l|serde_json::from_str(l).unwrap()).collect()}
    #[test]fn named_capture_profile_requires_explicit_path_and_exact_version(){
        assert_eq!(Profile::for_map_drive(None,None).unwrap(),Profile::Ordinary);
        assert_eq!(Profile::for_map_drive(Some("capture"),None).unwrap(),Profile::Ordinary);
        assert_eq!(Profile::for_map_drive(Some("capture"),Some("map-drive-phase2-v1")).unwrap(),Profile::MapDrivePhase2V1);
        for name in ["","ordinary","map-drive-phase2-v2","map-drive-phase2-v1 ","MAP-DRIVE-PHASE2-V1"]{
            assert!(Profile::for_map_drive(Some("capture"),Some(name)).is_err());
        }
        assert!(Profile::for_map_drive(None,Some("map-drive-phase2-v1")).is_err());
        assert!(Profile::for_map_drive(Some(""),Some("map-drive-phase2-v1")).is_err());
    }
    #[test]fn capture_headers_bind_new_budget_without_changing_default_header(){
        let (local,old)=location();let (_,default)=location();let (_,extended)=location();
        Recorder::open(old.to_str().unwrap(),&local).unwrap();
        Recorder::open_profile(default.to_str().unwrap(),&local,Profile::Ordinary).unwrap();
        let recorder=Recorder::open_profile(extended.to_str().unwrap(),&local,Profile::MapDrivePhase2V1).unwrap();
        assert_eq!(fs::read(old.join("packets.jsonl")).unwrap(),fs::read(default.join("packets.jsonl")).unwrap());
        let first=events(&old);assert_eq!(first.len(),1);assert!(first[0].get("profile").is_none());
        assert_eq!(first[0]["max_packets"],10_000);assert_eq!(first[0]["max_wire_bytes"],16*1024*1024);
        let first=events(&extended);assert_eq!(first.len(),1);assert_eq!(first[0]["profile"],"map-drive-phase2-v1");
        assert_eq!(first[0]["max_packets"],48_000);assert_eq!(first[0]["max_wire_bytes"],32*1024*1024);
        assert_eq!((recorder.packet_limit,recorder.byte_limit),(48_000,32*1024*1024));
    }
    #[test]fn both_profile_packet_caps_fail_explicitly_once_without_a_silent_wrap(){
        let peer="127.0.0.1:32123".parse().unwrap();
        for profile in [Profile::Ordinary,Profile::MapDrivePhase2V1]{
            let (local,path)=location();let mut r=Recorder::open_profile(path.to_str().unwrap(),&local,profile).unwrap();
            // Boundary injection avoids writing48k irrelevant test files; this
            // is a limit unit, never a claimed complete native packet corpus.
            r.count=r.packet_limit-1;r.observe(Channel::Base,true,peer,&[8,4]);
            assert!(!r.disabled);assert_eq!(r.count,r.packet_limit);
            r.observe(Channel::Base,true,peer,&[9]);r.observe(Channel::Base,true,peer,&[9]);
            assert!(r.disabled);let rows=events(&path);assert_eq!(rows.len(),3);assert_eq!(rows[2]["event"],"capture_limit");
            assert_eq!(rows[1]["index"],r.packet_limit-1);assert_eq!(rows[2]["packets"],r.packet_limit);
            let name=format!("packet-{:06}-base_client_to_server.bin",r.packet_limit-1);
            assert_eq!(fs::read(path.join(name)).unwrap(),vec![8,4]);assert_eq!(fs::read_dir(&path).unwrap().count(),2);
        }
    }
    #[test]fn extended_profile_byte_cap_and_saturating_overflow_disable_before_writing(){
        let peer="127.0.0.1:32123".parse().unwrap();let (local,path)=location();
        let mut r=Recorder::open_profile(path.to_str().unwrap(),&local,Profile::MapDrivePhase2V1).unwrap();
        r.bytes=r.byte_limit-2;r.observe(Channel::Base,false,peer,&[1,2]);assert!(!r.disabled);
        r.observe(Channel::Base,false,peer,&[3]);assert!(r.disabled);assert_eq!(r.bytes,32*1024*1024);assert_eq!(r.count,1);
        assert_eq!(events(&path).last().unwrap()["event"],"capture_limit");
        let (_,path)=location();let mut r=Recorder::open_profile(path.to_str().unwrap(),&local,Profile::MapDrivePhase2V1).unwrap();
        r.bytes=usize::MAX;r.observe(Channel::Base,false,peer,&[1]);assert!(r.disabled);assert_eq!(r.count,0);
        assert_eq!(fs::read_dir(&path).unwrap().count(),1);assert_eq!(events(&path)[1]["event"],"capture_limit");
    }
    #[test]fn extended_capture_preserves_exact_packet_file_indices_and_never_reuses_directory(){
        let (local,path)=location();let mut r=Recorder::open_profile(path.to_str().unwrap(),&local,Profile::MapDrivePhase2V1).unwrap();
        let peer="127.0.0.1:32123".parse().unwrap();r.observe(Channel::Login,true,peer,&[1,2]);r.observe(Channel::Base,false,peer,&[3,4,5]);
        let rows=events(&path);assert_eq!(rows.len(),3);assert_eq!(rows[1]["index"],0);assert_eq!(rows[2]["index"],1);
        for (row,body) in [(&rows[1],vec![1,2]),(&rows[2],vec![3,4,5])]{assert_eq!(fs::read(path.join(row["file"].as_str().unwrap())).unwrap(),body);}
        assert!(Recorder::open_profile(path.to_str().unwrap(),&local,Profile::MapDrivePhase2V1).is_err());
        assert!(Recorder::open_profile("relative-capture",&local,Profile::MapDrivePhase2V1).is_err());
        assert!(Recorder::open_profile(local.parent().unwrap().join("outside-capture-profile").to_str().unwrap(),&local,Profile::MapDrivePhase2V1).is_err());
    }
    #[test]fn extended_capture_io_error_is_fail_closed_and_cannot_overwrite_existing_raw_packet(){
        let (local,path)=location();let mut r=Recorder::open_profile(path.to_str().unwrap(),&local,Profile::MapDrivePhase2V1).unwrap();
        let target=path.join("packet-000000-base_client_to_server.bin");fs::write(&target,[42]).unwrap();
        let peer="127.0.0.1:32123".parse().unwrap();r.observe(Channel::Base,true,peer,&[1,2]);r.observe(Channel::Base,true,peer,&[3]);
        assert!(r.disabled);assert_eq!((r.count,r.bytes),(0,0));assert_eq!(fs::read(target).unwrap(),vec![42]);assert_eq!(events(&path).len(),1);
    }
    #[test] fn capture_limits_are_explicit_preserve_existing_files_and_stop_writes() {
        let epoch=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let local=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/unified-wire");
        fs::create_dir_all(&local).unwrap();let local=local.canonicalize().unwrap();
        let path=local.join(format!("capture-{}-{epoch}",std::process::id()));
        let mut recorder=Recorder::open_bounded(&path,&local,2,5).unwrap();
        let peer="127.0.0.1:32123".parse().unwrap();
        recorder.observe(Channel::Login,true,peer,&[1,2,3]);
        recorder.observe(Channel::Base,false,peer,&[4,5]);
        recorder.observe(Channel::Base,false,peer,&[6]);
        recorder.observe(Channel::Base,false,peer,&[7]);
        assert!(recorder.disabled);assert_eq!((recorder.count,recorder.bytes),(2,5));
        let manifest=fs::read_to_string(path.join("packets.jsonl")).unwrap();
        assert_eq!(manifest.lines().count(),4);assert_eq!(manifest.matches("capture_limit").count(),1);
        assert_eq!(fs::read(path.join("packet-000000-client_to_server.bin")).unwrap(),vec![1,2,3]);
        assert_eq!(fs::read_dir(&path).unwrap().count(),3);
        assert!(Recorder::open_bounded(&path,&local,2,5).is_err());
        assert!(Recorder::open_bounded(&local.parent().unwrap().join("outside-capture"),&local,2,5).is_err());
    }
}
