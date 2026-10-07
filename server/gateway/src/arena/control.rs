//! One-shot local authorization for an explicitly selected Avatar checkpoint.
//! No arbitrary payload, credentials, network endpoint, nonce, or clock input.
use std::{fmt,fs,io::{self,Read},path::{Path,PathBuf}};
use serde::{Deserialize,Deserializer,de::{self,MapAccess,Visitor}};

pub const MAX_TRIGGER_BYTES:u64=1024;
pub const AVATAR_ENTITY_ID:u32=0x09100002;
pub const ARENA_UNIQUE_ID:u64=1;

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Checkpoint {AvatarBase,AvatarSpace,AvatarVehicle,AvatarReady,AvatarMovement,AvatarDrive}
impl Checkpoint {
    pub fn name(self)->&'static str {match self {Self::AvatarBase=>"avatar_base",Self::AvatarSpace=>"avatar_space",Self::AvatarVehicle=>"avatar_vehicle",Self::AvatarReady=>"avatar_ready",Self::AvatarMovement=>"avatar_movement",Self::AvatarDrive=>"avatar_drive"}}
    pub fn cli(self)->&'static str {match self {Self::AvatarBase=>"legacy091-arena-base-probe",Self::AvatarSpace=>"legacy091-arena-space-probe",Self::AvatarVehicle=>"legacy091-arena-vehicle-probe",Self::AvatarReady=>"legacy091-arena-ready-probe",Self::AvatarMovement=>"legacy091-arena-movement-probe",Self::AvatarDrive=>"legacy091-map-drive-probe"}}
    pub fn scope(self)->&'static str {match self {Self::AvatarBase=>"one_shot_avatar_base",Self::AvatarSpace=>"one_shot_avatar_cell_space",Self::AvatarVehicle=>"one_shot_avatar_own_vehicle",Self::AvatarReady=>"one_shot_avatar_preparation",Self::AvatarMovement=>"one_shot_avatar_lab_movement",Self::AvatarDrive=>"one_shot_avatar_binding"}}
}

fn invalid(message:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidInput,message)}

// Typed manual Deserialize has deny_unknown_fields semantics without enabling
// a new derive dependency feature. Duplicate/missing fields also fail closed.
struct Trigger {version:u8,account_id:String,database_id:i32,checkpoint:String}
impl<'de> Deserialize<'de> for Trigger {
    fn deserialize<D:Deserializer<'de>>(deserializer:D)->Result<Self,D::Error> {
        struct Fields;
        impl<'de> Visitor<'de> for Fields {
            type Value=Trigger;
            fn expecting(&self,f:&mut fmt::Formatter)->fmt::Result {f.write_str("exact arena checkpoint object")}
            fn visit_map<M:MapAccess<'de>>(self,mut input:M)->Result<Trigger,M::Error> {
                let (mut version,mut account_id,mut database_id,mut checkpoint)=(None,None,None,None);
                while let Some(key)=input.next_key::<String>()? {
                    match key.as_str() {
                        "version"=>{if version.is_some(){return Err(de::Error::duplicate_field("version"));}version=Some(input.next_value::<u8>()?);},
                        "account_id"=>{if account_id.is_some(){return Err(de::Error::duplicate_field("account_id"));}account_id=Some(input.next_value::<String>()?);},
                        "database_id"=>{if database_id.is_some(){return Err(de::Error::duplicate_field("database_id"));}database_id=Some(input.next_value::<i32>()?);},
                        "checkpoint"=>{if checkpoint.is_some(){return Err(de::Error::duplicate_field("checkpoint"));}checkpoint=Some(input.next_value::<String>()?);},
                        _=>return Err(de::Error::custom("unknown arena checkpoint field")),
                    }
                }
                Ok(Trigger {
                    version:version.ok_or_else(||de::Error::missing_field("version"))?,
                    account_id:account_id.ok_or_else(||de::Error::missing_field("account_id"))?,
                    database_id:database_id.ok_or_else(||de::Error::missing_field("database_id"))?,
                    checkpoint:checkpoint.ok_or_else(||de::Error::missing_field("checkpoint"))?,
                })
            }
        }
        deserializer.deserialize_map(Fields)
    }
}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Rejection {Malformed,TargetMismatch,UnsafePath,InputIo}

#[cfg(test)]
fn matches_target(raw:&[u8],account_id:&str,database_id:i32)->Result<(),Rejection> {
    matches_checkpoint(raw,account_id,database_id,Checkpoint::AvatarBase)
}

fn matches_checkpoint(raw:&[u8],account_id:&str,database_id:i32,checkpoint:Checkpoint)->Result<(),Rejection> {
    if raw.is_empty() || raw.len() as u64>MAX_TRIGGER_BYTES {return Err(Rejection::Malformed);}
    let value:Trigger=serde_json::from_slice(raw).map_err(|_|Rejection::Malformed)?;
    if value.version!=1 || value.checkpoint!=checkpoint.name() || value.database_id<=0
        || value.account_id.len()!=36 || !value.account_id.bytes().enumerate().all(|(i,b)|
            if [8,13,18,23].contains(&i) {b==b'-'} else {b.is_ascii_digit() || (b'a'..=b'f').contains(&b)}) {
        return Err(Rejection::Malformed);
    }
    if value.account_id!=account_id || value.database_id!=database_id {return Err(Rejection::TargetMismatch);}
    Ok(())
}

fn is_link(metadata:&fs::Metadata)->bool {
    if metadata.file_type().is_symlink() {return true;}
    #[cfg(windows)] {
        use std::os::windows::fs::MetadataExt;
        if metadata.file_attributes()&0x400!=0 {return true;} // any reparse point, including junctions
    }
    false
}

fn checked_parent(parent:&Path,root:&Path)->io::Result<PathBuf> {
    let canonical=parent.canonicalize()?;
    if canonical==root || !canonical.starts_with(root) {return Err(invalid("trigger parent must be strictly inside local root"));}
    let mut current=parent;
    for _ in 0..128 {
        let metadata=fs::symlink_metadata(current)?;
        if !metadata.is_dir() || is_link(&metadata) {return Err(invalid("trigger parent chain must contain only real directories"));}
        if current.canonicalize()?==root {return Ok(canonical);}
        current=current.parent().ok_or_else(||invalid("trigger parent chain escaped root"))?;
    }
    Err(invalid("trigger parent depth bound"))
}

pub struct ArenaControl {path:PathBuf,parent:PathBuf,root:PathBuf,finished:bool,checkpoint:Checkpoint}
impl ArenaControl {
    pub fn new(path:&Path,local_root:&Path)->io::Result<Self> {
        Self::for_checkpoint(path,local_root,Checkpoint::AvatarBase)
    }
    pub fn checkpoint(&self)->Checkpoint {self.checkpoint}
    pub fn for_checkpoint(path:&Path,local_root:&Path,checkpoint:Checkpoint)->io::Result<Self> {
        if !path.is_absolute() || !local_root.is_absolute() {return Err(invalid("absolute local trigger and root required"));}
        if path.components().any(|c|matches!(c,std::path::Component::ParentDir)) {return Err(invalid("trigger parent traversal refused"));}
        let root=local_root.canonicalize()?;
        if !root.is_dir() {return Err(invalid("local root must be a directory"));}
        let parent=checked_parent(path.parent().ok_or_else(||invalid("trigger parent absent"))?,&root)?;
        let name=path.file_name().ok_or_else(||invalid("trigger file name absent"))?;
        let path=parent.join(name);
        match fs::symlink_metadata(&path) {
            Err(e) if e.kind()==io::ErrorKind::NotFound=>{},
            _=>return Err(invalid("trigger must not exist when this diagnostic process starts")),
        }
        Ok(Self {path,parent,root,finished:false,checkpoint})
    }

    /// Call only for an authenticated, fully synced idle channel. The first
    /// present file disarms the control in memory, even on rejection. Keep the
    /// file unchanged as evidence; a replacement cannot authorize another try.
    pub fn poll(&mut self,account_id:&str,database_id:i32)->Result<bool,Rejection> {
        if self.finished {return Ok(false);}
        match checked_parent(&self.parent,&self.root) {
            Ok(parent) if parent==self.parent=>{},
            _=>{self.finished=true;return Err(Rejection::UnsafePath);},
        }
        let before=match fs::symlink_metadata(&self.path) {
            Err(e) if e.kind()==io::ErrorKind::NotFound=>return Ok(false),
            Err(_)=>{self.finished=true;return Err(Rejection::InputIo);},
            Ok(metadata)=>metadata,
        };
        self.finished=true;
        if is_link(&before) || !before.is_file() {return Err(Rejection::UnsafePath);}
        if before.len()==0 || before.len()>MAX_TRIGGER_BYTES {return Err(Rejection::Malformed);}
        let mut options=fs::OpenOptions::new();options.read(true);
        #[cfg(windows)] {
            use std::os::windows::fs::OpenOptionsExt;
            // Do not traverse a leaf reparse point swapped after metadata;
            // deny concurrent writers/deleters while holding this read handle.
            options.custom_flags(0x00200000).share_mode(1);
        }
        let file=options.open(&self.path).map_err(|_|Rejection::InputIo)?;
        let actual=file.metadata().map_err(|_|Rejection::InputIo)?;
        if is_link(&actual) || !actual.is_file() || actual.len()!=before.len() {return Err(Rejection::UnsafePath);}
        let mut raw=Vec::new();(&file).take(MAX_TRIGGER_BYTES+1).read_to_end(&mut raw).map_err(|_|Rejection::InputIo)?;
        if raw.len() as u64!=before.len() {return Err(Rejection::Malformed);}
        if checked_parent(&self.parent,&self.root).map_err(|_|Rejection::UnsafePath)?!=self.parent
            || self.path.canonicalize().map_err(|_|Rejection::UnsafePath)?!=self.path
            || is_link(&fs::symlink_metadata(&self.path).map_err(|_|Rejection::InputIo)?) {
            return Err(Rejection::UnsafePath);
        }
        matches_checkpoint(&raw,account_id,database_id,self.checkpoint)?;
        Ok(true)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize,Ordering};
    const ACCOUNT:&str="00000000-0000-0000-0000-000000000001";
    fn raw()->Vec<u8> {format!(r#"{{"version":1,"account_id":"{ACCOUNT}","database_id":1,"checkpoint":"avatar_base"}}"#).into_bytes()}
    struct Place {root:PathBuf,parent:PathBuf,path:PathBuf,allowed:PathBuf}
    impl Place {
        fn new()->Self {
            static SEQ:AtomicUsize=AtomicUsize::new(0);
            let allowed=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/evidence/20261005-p02-arena-entry/data/arena-control-unit-files");
            fs::create_dir_all(&allowed).unwrap();let allowed=allowed.canonicalize().unwrap();
            let root=allowed.join(format!("unit-{}-{}",std::process::id(),SEQ.fetch_add(1,Ordering::Relaxed)));
            fs::create_dir(&root).unwrap();let parent=root.join("controls");fs::create_dir(&parent).unwrap();
            let path=parent.join("trigger.json");Self {root,parent,path,allowed}
        }
    }
    impl Drop for Place {
        fn drop(&mut self) {
            let resolved=self.root.canonicalize().unwrap();
            assert!(resolved.starts_with(&self.allowed) && resolved!=self.allowed);
            fs::remove_dir_all(resolved).unwrap();
        }
    }
    #[test] fn typed_schema_rejects_unknown_duplicate_missing_and_wrong_types() {
        let good=String::from_utf8(raw()).unwrap();assert_eq!(matches_target(good.as_bytes(),ACCOUNT,1),Ok(()));
        for bad in [good.replace("\"version\":1","\"version\":true"),good.replace("\"version\":1","\"version\":1.0"),
            good.replace("\"version\":1","\"version\":2"),good.replace("\"database_id\":1","\"database_id\":0"),
            good.replace("\"database_id\":1","\"database_id\":2147483648"),good.replace("\"database_id\":1","\"database_id\":true"),
            good.replace("avatar_base","avatar_cell"),good.replace("\"version\":1,",""),
            good.replace("\"version\":1","\"version\":1,\"version\":1"),
            good.replace("\"version\":1","\"version\":1,\"nonce\":7"),
            good.replace("\"version\":1","\"version\":1,\"payload\":\"00\""),
            good.replace("\"version\":1","\"version\":1,\"username\":\"unit\""),
            good.replace(ACCOUNT,"bad"),format!("{good} null"),"[]".to_owned(),"{}".to_owned()] {
            assert_eq!(matches_target(bad.as_bytes(),ACCOUNT,1),Err(Rejection::Malformed));
        }
        assert_eq!(matches_target(&[b' ';1025],ACCOUNT,1),Err(Rejection::Malformed));
        assert_eq!(matches_target(&[],ACCOUNT,1),Err(Rejection::Malformed));
    }
    #[test] fn target_requires_both_verified_account_and_database_identity() {
        assert_eq!(matches_target(&raw(),"00000000-0000-0000-0000-000000000002",1),Err(Rejection::TargetMismatch));
        assert_eq!(matches_target(&raw(),ACCOUNT,2),Err(Rejection::TargetMismatch));
    }
    #[test] fn startup_requires_fresh_absent_file_in_strict_child_directory() {
        let p=Place::new();
        assert!(ArenaControl::new(Path::new("relative.json"),&p.root).is_err());
        assert!(ArenaControl::new(&p.root.join("at-root.json"),&p.root).is_err());
        assert!(ArenaControl::new(&p.allowed.join("outside.json"),&p.root).is_err());
        assert!(ArenaControl::new(&p.parent.join("../escape.json"),&p.root).is_err());
        fs::write(&p.path,raw()).unwrap();assert!(ArenaControl::new(&p.path,&p.root).is_err());
    }
    #[test] fn first_file_consumed_once_in_memory_and_evidence_left_unchanged() {
        let p=Place::new();let mut control=ArenaControl::new(&p.path,&p.root).unwrap();
        assert_eq!(control.poll(ACCOUNT,1),Ok(false));fs::write(&p.path,raw()).unwrap();
        assert_eq!(control.poll(ACCOUNT,1),Ok(true));assert_eq!(fs::read(&p.path).unwrap(),raw());
        fs::write(&p.path,raw()).unwrap();assert_eq!(control.poll(ACCOUNT,1),Ok(false));
    }
    #[test] fn rejected_target_or_malformed_file_cannot_be_replaced_to_retry() {
        for bytes in [raw(),b"not-json".to_vec(),vec![b' ';1025]] {
            let p=Place::new();let mut control=ArenaControl::new(&p.path,&p.root).unwrap();
            fs::write(&p.path,bytes).unwrap();assert!(control.poll(ACCOUNT,2).is_err());
            fs::write(&p.path,raw()).unwrap();assert_eq!(control.poll(ACCOUNT,1),Ok(false));
        }
    }
    #[test] fn directory_instead_of_file_is_not_an_instruction() {
        let p=Place::new();let mut control=ArenaControl::new(&p.path,&p.root).unwrap();
        fs::create_dir(&p.path).unwrap();assert_eq!(control.poll(ACCOUNT,1),Err(Rejection::UnsafePath));
    }
    #[test] fn lost_parent_disarms_once_even_if_recreated_with_valid_file() {
        let p=Place::new();let mut control=ArenaControl::new(&p.path,&p.root).unwrap();
        fs::remove_dir(&p.parent).unwrap();
        assert_eq!(control.poll(ACCOUNT,1),Err(Rejection::UnsafePath));
        fs::create_dir(&p.parent).unwrap();fs::write(&p.path,raw()).unwrap();
        assert_eq!(control.poll(ACCOUNT,1),Ok(false));
    }
    #[test] fn checkpoint_is_bound_to_cli_not_chosen_by_trigger_input() {
        let base=raw();let space=String::from_utf8(base.clone()).unwrap().replace("avatar_base","avatar_space").into_bytes();
        assert_eq!(matches_checkpoint(&base,ACCOUNT,1,Checkpoint::AvatarBase),Ok(()));
        assert_eq!(matches_checkpoint(&space,ACCOUNT,1,Checkpoint::AvatarSpace),Ok(()));
        assert_eq!(matches_checkpoint(&space,ACCOUNT,1,Checkpoint::AvatarBase),Err(Rejection::Malformed));
        assert_eq!(matches_checkpoint(&base,ACCOUNT,1,Checkpoint::AvatarSpace),Err(Rejection::Malformed));
        for text in [String::from_utf8(space.clone()).unwrap().replace("avatar_space","avatar_vehicle"),
                     String::from_utf8(space.clone()).unwrap().replace("\"version\":1","\"version\":true"),
                     String::from_utf8(space.clone()).unwrap().replace("\"version\":1","\"version\":1,\"position\":[0,0,0]"),
                     String::from_utf8(space.clone()).unwrap().replace("\"version\":1","\"version\":1,\"geometry\":\"spaces/other\"")] {
            assert_eq!(matches_checkpoint(text.as_bytes(),ACCOUNT,1,Checkpoint::AvatarSpace),Err(Rejection::Malformed));
        }
        assert_eq!(matches_checkpoint(&space,ACCOUNT,2,Checkpoint::AvatarSpace),Err(Rejection::TargetMismatch));
    }
    #[test] fn space_control_uses_same_fresh_path_and_once_only_rejection_contract() {
        let p=Place::new();
        assert!(ArenaControl::for_checkpoint(&p.root.join("at-root.json"),&p.root,Checkpoint::AvatarSpace).is_err());
        let mut control=ArenaControl::for_checkpoint(&p.path,&p.root,Checkpoint::AvatarSpace).unwrap();
        assert_eq!(control.checkpoint(),Checkpoint::AvatarSpace);
        assert_eq!(control.poll(ACCOUNT,1),Ok(false));
        fs::write(&p.path,raw()).unwrap();
        assert_eq!(control.poll(ACCOUNT,1),Err(Rejection::Malformed));
        let space=String::from_utf8(raw()).unwrap().replace("avatar_base","avatar_space");
        fs::write(&p.path,space.as_bytes()).unwrap();
        assert_eq!(control.poll(ACCOUNT,1),Ok(false));
        assert!(ArenaControl::for_checkpoint(&p.path,&p.root,Checkpoint::AvatarSpace).is_err());
        assert_eq!(fs::read(&p.path).unwrap(),space.as_bytes());
    }
    #[test] fn valid_space_control_is_consumed_once_without_file_or_source_mutation() {
        let p=Place::new();let mut control=ArenaControl::for_checkpoint(&p.path,&p.root,Checkpoint::AvatarSpace).unwrap();
        let space=String::from_utf8(raw()).unwrap().replace("avatar_base","avatar_space");
        fs::write(&p.path,space.as_bytes()).unwrap();assert_eq!(control.poll(ACCOUNT,1),Ok(true));
        assert_eq!(control.poll(ACCOUNT,1),Ok(false));assert_eq!(fs::read(&p.path).unwrap(),space.as_bytes());
    }
    #[test] fn vehicle_checkpoint_is_exact_once_and_cannot_select_another_mode() {
        let p=Place::new();let mut control=ArenaControl::for_checkpoint(&p.path,&p.root,Checkpoint::AvatarVehicle).unwrap();
        let vehicle=String::from_utf8(raw()).unwrap().replace("avatar_base","avatar_vehicle");
        for checkpoint in [Checkpoint::AvatarBase,Checkpoint::AvatarSpace] {
            assert_eq!(matches_checkpoint(vehicle.as_bytes(),ACCOUNT,1,checkpoint),Err(Rejection::Malformed));
        }
        assert_eq!(matches_checkpoint(&raw(),ACCOUNT,1,Checkpoint::AvatarVehicle),Err(Rejection::Malformed));
        assert_eq!(matches_checkpoint(vehicle.as_bytes(),ACCOUNT,2,Checkpoint::AvatarVehicle),Err(Rejection::TargetMismatch));
        for changed in [vehicle.replace("\"version\":1","\"version\":true"),
                        vehicle.replace("\"version\":1","\"version\":1,\"health\":90"),
                        vehicle.replace("\"version\":1","\"version\":1,\"descriptor\":\"00\"")] {
            assert_eq!(matches_checkpoint(changed.as_bytes(),ACCOUNT,1,Checkpoint::AvatarVehicle),Err(Rejection::Malformed));
        }
        fs::write(&p.path,&vehicle).unwrap();assert_eq!(control.poll(ACCOUNT,1),Ok(true));
        assert_eq!(control.poll(ACCOUNT,1),Ok(false));assert_eq!(fs::read(&p.path).unwrap(),vehicle.as_bytes());
        assert!(ArenaControl::for_checkpoint(&p.path,&p.root,Checkpoint::AvatarVehicle).is_err());
    }
    #[test] fn ready_checkpoint_is_typed_and_cannot_override_server_clock_or_period() {
        let ready=String::from_utf8(raw()).unwrap().replace("avatar_base","avatar_ready");
        assert_eq!(matches_checkpoint(ready.as_bytes(),ACCOUNT,1,Checkpoint::AvatarReady),Ok(()));
        assert_eq!(Checkpoint::AvatarReady.cli(),"legacy091-arena-ready-probe");
        assert_eq!(Checkpoint::AvatarReady.scope(),"one_shot_avatar_preparation");
        for checkpoint in [Checkpoint::AvatarBase,Checkpoint::AvatarSpace,Checkpoint::AvatarVehicle] {
            assert_eq!(matches_checkpoint(ready.as_bytes(),ACCOUNT,1,checkpoint),Err(Rejection::Malformed));
            let other=ready.replace("avatar_ready",checkpoint.name());
            assert_eq!(matches_checkpoint(other.as_bytes(),ACCOUNT,1,Checkpoint::AvatarReady),Err(Rejection::Malformed));
        }
        for added in ["\"duration\":30","\"frequency\":10","\"game_ticks\":1000","\"period\":3","\"ready\":true"] {
            let changed=ready.replace("\"version\":1",&format!("\"version\":1,{added}"));
            assert_eq!(matches_checkpoint(changed.as_bytes(),ACCOUNT,1,Checkpoint::AvatarReady),Err(Rejection::Malformed));
        }
        assert_eq!(matches_checkpoint(ready.as_bytes(),ACCOUNT,2,Checkpoint::AvatarReady),Err(Rejection::TargetMismatch));
        assert_eq!(matches_checkpoint(ready.replace("\"version\":1","\"version\":true").as_bytes(),ACCOUNT,1,Checkpoint::AvatarReady),Err(Rejection::Malformed));
    }
    #[test] fn ready_control_is_once_only_fresh_local_and_keeps_original_authorization_bytes() {
        let p=Place::new();let ready=String::from_utf8(raw()).unwrap().replace("avatar_base","avatar_ready");
        assert!(ArenaControl::for_checkpoint(&p.root.join("at-root.json"),&p.root,Checkpoint::AvatarReady).is_err());
        let mut control=ArenaControl::for_checkpoint(&p.path,&p.root,Checkpoint::AvatarReady).unwrap();
        assert_eq!(control.poll(ACCOUNT,1),Ok(false));fs::write(&p.path,&ready).unwrap();
        assert_eq!(control.poll(ACCOUNT,1),Ok(true));assert_eq!(control.poll(ACCOUNT,1),Ok(false));
        assert_eq!(fs::read(&p.path).unwrap(),ready.as_bytes());
        assert!(ArenaControl::for_checkpoint(&p.path,&p.root,Checkpoint::AvatarReady).is_err());
        let p=Place::new();let mut control=ArenaControl::for_checkpoint(&p.path,&p.root,Checkpoint::AvatarReady).unwrap();
        fs::write(&p.path,raw()).unwrap();assert_eq!(control.poll(ACCOUNT,1),Err(Rejection::Malformed));
        fs::write(&p.path,&ready).unwrap();assert_eq!(control.poll(ACCOUNT,1),Ok(false));
    }
    #[test] fn movement_control_is_new_exact_mode_with_no_pose_or_speed_override() {
        let value=String::from_utf8(raw()).unwrap().replace("avatar_base","avatar_movement");
        assert_eq!(matches_checkpoint(value.as_bytes(),ACCOUNT,1,Checkpoint::AvatarMovement),Ok(()));
        assert_eq!(Checkpoint::AvatarMovement.cli(),"legacy091-arena-movement-probe");
        for checkpoint in [Checkpoint::AvatarBase,Checkpoint::AvatarSpace,Checkpoint::AvatarVehicle,Checkpoint::AvatarReady] {
            assert_eq!(matches_checkpoint(value.as_bytes(),ACCOUNT,1,checkpoint),Err(Rejection::Malformed));
            assert_eq!(matches_checkpoint(value.replace("avatar_movement",checkpoint.name()).as_bytes(),ACCOUNT,1,Checkpoint::AvatarMovement),Err(Rejection::Malformed));
        }
        for added in ["\"speed\":1","\"position\":[1,2,3]","\"deadline\":8","\"flags\":1","\"game_ticks\":1000"] {
            assert_eq!(matches_checkpoint(value.replace("\"version\":1",&format!("\"version\":1,{added}")).as_bytes(),ACCOUNT,1,Checkpoint::AvatarMovement),Err(Rejection::Malformed));
        }
        assert_eq!(matches_checkpoint(value.as_bytes(),ACCOUNT,2,Checkpoint::AvatarMovement),Err(Rejection::TargetMismatch));
        let p=Place::new();let mut control=ArenaControl::for_checkpoint(&p.path,&p.root,Checkpoint::AvatarMovement).unwrap();
        fs::write(&p.path,&value).unwrap();assert_eq!(control.poll(ACCOUNT,1),Ok(true));assert_eq!(control.poll(ACCOUNT,1),Ok(false));
        assert_eq!(fs::read(&p.path).unwrap(),value.as_bytes());assert!(ArenaControl::for_checkpoint(&p.path,&p.root,Checkpoint::AvatarMovement).is_err());
    }
    #[test] fn drive_binding_control_is_distinct_exact_target_and_once_only() {
        let value=String::from_utf8(raw()).unwrap().replace("avatar_base","avatar_drive");
        assert_eq!(matches_checkpoint(value.as_bytes(),ACCOUNT,1,Checkpoint::AvatarDrive),Ok(()));
        assert_eq!(Checkpoint::AvatarDrive.cli(),"legacy091-map-drive-probe");assert_eq!(Checkpoint::AvatarDrive.scope(),"one_shot_avatar_binding");
        for old in [Checkpoint::AvatarBase,Checkpoint::AvatarSpace,Checkpoint::AvatarVehicle,Checkpoint::AvatarReady,Checkpoint::AvatarMovement] {
            assert!(matches_checkpoint(value.as_bytes(),ACCOUNT,1,old).is_err());
            assert!(matches_checkpoint(value.replace("avatar_drive",old.name()).as_bytes(),ACCOUNT,1,Checkpoint::AvatarDrive).is_err());
        }
        for added in ["\"position\":[0,0,0]","\"control_entity\":true","\"speed\":1","\"map_id\":5"] {
            assert!(matches_checkpoint(value.replace("\"version\":1",&format!("\"version\":1,{added}")).as_bytes(),ACCOUNT,1,Checkpoint::AvatarDrive).is_err());
        }
        assert!(matches_checkpoint(value.as_bytes(),ACCOUNT,2,Checkpoint::AvatarDrive).is_err());
        let p=Place::new();let mut control=ArenaControl::for_checkpoint(&p.path,&p.root,Checkpoint::AvatarDrive).unwrap();
        fs::write(&p.path,&value).unwrap();assert_eq!(control.poll(ACCOUNT,1),Ok(true));assert_eq!(control.poll(ACCOUNT,1),Ok(false));
        assert_eq!(fs::read(&p.path).unwrap(),value.as_bytes());assert!(ArenaControl::for_checkpoint(&p.path,&p.root,Checkpoint::AvatarDrive).is_err());
    }
}
