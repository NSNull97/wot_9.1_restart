//! Native #717 CMD105 adapter. The common assignment rules live in the store.
//! Versioned profiles bind the imported vehicles; the request codec is shared.
//! Wire0x8e was observed in the accepted P04F original-client captures.
use std::{io,path::Path};
use sha2::{Digest,Sha256};

pub const CANDIDATE_METHOD:u8=0x8e;
pub const PAYLOAD_BYTES:usize=20;
pub const COMMAND:i16=105;
pub const POLICY_SHA256:&str="35a58c8e13d9b815f8552371bbd6556ba10c091753861e697e522d6a5c877cb2";
pub const CROSS_POLICY_SHA256:&str="20f7d65c6d360a17f164cb6e4eaa73056a58a793727d4bfbecc1358e1f21969f";
pub const ROSTER_POLICY_SHA256:&str="3e86a495c028570d96a479f409dc578875652e01f60f6ac8c42c5c1bae51737c";
pub const PROGRESSION_POLICY_SHA256:&str="fd79729bbaf926fe2567382be086c5e730c7c6474debe338b3052bb12ba62184";
pub const DISMISSAL_POLICY_SHA256:&str="c7f6d05be033d7ea75b8be50b3a4578d6a4167a9d3d5dc4ea8975878633c74b2";
pub const BARRACKS_POLICY_SHA256:&str="e9a12e9000cc255679d5dad6d744943f325ae1982c5a21060a5996f62c433fd7";
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Profile {Ms1,Ms1Is7,Roster,Progression,Dismissal,Barracks}
impl Profile {
    pub fn selected(cross_vehicle:bool)->Self {if cross_vehicle {Self::Ms1Is7}else {Self::Ms1}}
    pub fn selected_roster(cross_vehicle:bool,roster:bool)->Self {if roster {Self::Roster}else {Self::selected(cross_vehicle)}}
    pub fn selected_progression(cross:bool,roster:bool,progression:bool)->Self {if progression {Self::Progression}else {Self::selected_roster(cross,roster)}}
    pub fn selected_dismissal(cross:bool,roster:bool,progression:bool,dismissal:bool)->Self {if dismissal {Self::Dismissal}else {Self::selected_progression(cross,roster,progression)}}
    pub fn selected_barracks(cross:bool,roster:bool,progression:bool,dismissal:bool,barracks:bool)->Self {if barracks {Self::Barracks}else {Self::selected_dismissal(cross,roster,progression,dismissal)}}
    pub fn roster(self)->bool {matches!(self,Self::Roster|Self::Progression|Self::Dismissal|Self::Barracks)}
    fn minimum_revision(self)->u64 {match self {Self::Barracks=>12,Self::Dismissal=>11,Self::Progression=>10,Self::Roster=>9,Self::Ms1Is7=>8,Self::Ms1=>7}}
    fn policy(self)->&'static str {match self {Self::Barracks=>BARRACKS_POLICY_SHA256,Self::Dismissal=>DISMISSAL_POLICY_SHA256,Self::Progression=>PROGRESSION_POLICY_SHA256,Self::Roster=>ROSTER_POLICY_SHA256,Self::Ms1Is7=>CROSS_POLICY_SHA256,Self::Ms1=>POLICY_SHA256}}
    fn vehicle_key(self)->&'static str {if self!=Self::Ms1 {"vehicle_count"}else {"vehicle_inventory_id"}}
}
fn invalid(message:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,message)}

struct Binding {
    version:u32,account_id:String,native_database_id:i32,revision:u64,wire_revision:i64,
    policy_sha256:String,state_sha256:String,command:i16,vehicle_inventory_id:i64,
    free_recruitment_left:u64,configuration_revision:u64,battle:bool,
}
impl Binding {
    fn parse(raw:&[u8],profile:Profile)->io::Result<Self> {
        let super::crew_service091::MetadataObject(v)=serde_json::from_slice(raw).map_err(|_|invalid("transfer metadata shape"))?;
        let mut keys=vec!["version","account_id","native_database_id","revision","wire_revision","policy_sha256","state_sha256",
            "command",profile.vehicle_key(),"free_recruitment_left","configuration_revision","battle"];
        if profile.roster() {
            keys.extend(["transfer_command","role_level"]);
            if v.get("transfer_command").and_then(|v|v.as_i64())!=Some(105)
                || v.get("role_level").and_then(|v|v.as_i64())!=Some(50) {return Err(invalid("roster metadata transfer/training policy"));}
        }
        if v.len()!=keys.len() || keys.iter().any(|k|!v.contains_key(*k)) {return Err(invalid("transfer metadata fields"));}
        let u=|k:&str|v[k].as_u64().ok_or_else(||invalid("transfer metadata unsigned integer"));
        let i=|k:&str|v[k].as_i64().ok_or_else(||invalid("transfer metadata signed integer"));
        let s=|k:&str|v[k].as_str().map(str::to_owned).ok_or_else(||invalid("transfer metadata string"));
        Ok(Self{version:u("version")?.try_into().map_err(|_|invalid("transfer version bound"))?,account_id:s("account_id")?,
            native_database_id:i("native_database_id")?.try_into().map_err(|_|invalid("transfer database ID bound"))?,
            revision:u("revision")?,wire_revision:i("wire_revision")?,policy_sha256:s("policy_sha256")?,state_sha256:s("state_sha256")?,
            command:i("command")?.try_into().map_err(|_|invalid("transfer command bound"))?,vehicle_inventory_id:i(profile.vehicle_key())?,
            free_recruitment_left:u("free_recruitment_left")?,configuration_revision:u("configuration_revision")?,
            battle:v["battle"].as_bool().ok_or_else(||invalid("transfer battle flag"))?})
    }
}

pub fn metadata(directory:&Path,account_id:&str,database_id:i32,revision:u64,wire:i64)->io::Result<()> {
    metadata_for(Profile::Ms1,directory,account_id,database_id,revision,wire)
}
pub fn metadata_for(profile:Profile,directory:&Path,account_id:&str,database_id:i32,revision:u64,wire:i64)->io::Result<()> {
    metadata_with_limit(profile,directory,account_id,database_id,revision,wire,16384,true)
}
/// Research profile13 keeps the accepted P04K crew binding. Its larger state and
/// its research shop are bound by research metadata, not P04K's exact shop.
pub fn metadata_for_research(directory:&Path,account_id:&str,database_id:i32,revision:u64,wire:i64)->io::Result<()> {
    metadata_with_limit(Profile::Barracks,directory,account_id,database_id,revision,wire,crate::research_service091::MAX_STATE_BYTES,false)
}
fn metadata_with_limit(profile:Profile,directory:&Path,account_id:&str,database_id:i32,revision:u64,wire:i64,maximum:usize,barracks_shop:bool)->io::Result<()> {
    let filename=match profile {Profile::Barracks=>"crew-barracks.json",Profile::Dismissal=>"crew-dismissal.json",Profile::Progression=>"crew-progression.json",Profile::Roster=>"crew-roster.json",Profile::Ms1Is7=>"crew-cross-transfer.json",Profile::Ms1=>"crew-transfer.json"};
    let raw=super::crew_service091::fixture_file(directory,filename,4096)?;
    let state=super::crew_service091::fixture_file(directory,"state.bin",maximum)?;
    if barracks_shop && profile==Profile::Barracks {crate::crew_barracks091::shop(directory)?;}
    metadata_bytes_with_limit(profile,&raw,&state,account_id,database_id,revision,wire,maximum)
}
#[cfg(test)]
fn metadata_bytes(raw:&[u8],state:&[u8],account_id:&str,database_id:i32,revision:u64,wire:i64)->io::Result<()> {
    metadata_bytes_for(Profile::Ms1,raw,state,account_id,database_id,revision,wire)
}
fn metadata_bytes_for(profile:Profile,raw:&[u8],state:&[u8],account_id:&str,database_id:i32,revision:u64,wire:i64)->io::Result<()> {
    metadata_bytes_with_limit(profile,raw,state,account_id,database_id,revision,wire,16384)
}
fn metadata_bytes_with_limit(profile:Profile,raw:&[u8],state:&[u8],account_id:&str,database_id:i32,revision:u64,wire:i64,maximum:usize)->io::Result<()> {
    super::crew_service091::identity(account_id,database_id)?;
    if raw.len()>4096 || state.is_empty() || state.len()>maximum {return Err(invalid("transfer metadata size"));}
    let b=Binding::parse(raw,profile)?;
    if b.version!=1 || b.account_id!=account_id || b.native_database_id!=database_id
        || !(profile.minimum_revision()..=i32::MAX as u64).contains(&b.revision) || b.revision!=revision
        || b.wire_revision!=1 || wire!=1 || b.policy_sha256!=profile.policy()
        || b.state_sha256!=format!("{:x}",Sha256::digest(state))
        || b.command!=(if profile==Profile::Barracks {303}else if profile==Profile::Dismissal {306}else if profile==Profile::Progression {151}else if profile.roster() {309}else {COMMAND}) || b.vehicle_inventory_id!=(if profile!=Profile::Ms1 {2}else {1})
        || b.free_recruitment_left>match profile {Profile::Barracks|Profile::Dismissal|Profile::Progression|Profile::Roster=>13,Profile::Ms1Is7=>0,Profile::Ms1=>1}
        || !((if profile.roster() {2}else {1})..=i32::MAX as u64).contains(&b.configuration_revision)
        || (!profile.roster() && b.configuration_revision<2-b.free_recruitment_left) || b.battle {
        return Err(invalid("transfer metadata identity/policy/state/revision binding"));
    }
    Ok(())
}

#[derive(Debug,Clone,Copy,PartialEq,Eq)]
pub struct Request {pub id:i16,pub vehicle_inventory_id:i64,pub slot:i32,pub tankman_inventory_id:i32}
impl Request {
    pub fn decode(payload:&[u8])->io::Result<Self> {
        if payload.len()!=PAYLOAD_BYTES {return Err(invalid("transfer payload length"));}
        let id=i16::from_le_bytes([payload[0],payload[1]]);
        if id<=0 || payload[2..4]!=COMMAND.to_le_bytes() {return Err(invalid("transfer envelope"));}
        Ok(Self{id,vehicle_inventory_id:i64::from_le_bytes(payload[4..12].try_into().map_err(|_|invalid("transfer vehicle"))?),
            slot:i32::from_le_bytes(payload[12..16].try_into().map_err(|_|invalid("transfer slot"))?),
            tankman_inventory_id:i32::from_le_bytes(payload[16..20].try_into().map_err(|_|invalid("transfer tankman"))?)})
    }
    pub fn validate_supported(&self)->io::Result<()> {
        self.validate_for(Profile::Ms1)
    }
    pub fn validate_for(&self,profile:Profile)->io::Result<()> {
        // Available imported profile only; ownership/role/seat/reservation are
        // independently checked against authoritative data by the shared writer.
        let maximum_slot=match (profile,self.vehicle_inventory_id) {(Profile::Ms1Is7|Profile::Roster|Profile::Progression|Profile::Dismissal|Profile::Barracks,2)=>4,(_,1)=>1,_=>return Err(invalid("unsupported transfer vehicle"))};
        if self.id<=0 || !(-1..=maximum_slot).contains(&self.slot)
            || !(self.tankman_inventory_id==-1 || (1..=if profile.roster() {16}else {3}).contains(&self.tankman_inventory_id))
            || (self.slot==-1 && self.tankman_inventory_id!=-1) {
            return Err(invalid("unsupported transfer profile/selection"));
        }
        Ok(())
    }
    pub fn layout(&self)->[i64;3] {[self.vehicle_inventory_id,self.slot as i64,self.tankman_inventory_id as i64]}
}
pub fn service_request(account_id:&str,database_id:i32,key:&str,revision:u64,wire:i64,request:Request)->io::Result<Vec<u8>> {
    service_request_for(Profile::Ms1,account_id,database_id,key,revision,wire,request)
}
pub fn service_request_for(profile:Profile,account_id:&str,database_id:i32,key:&str,revision:u64,wire:i64,request:Request)->io::Result<Vec<u8>> {
    super::crew_service091::identity(account_id,database_id)?;request.validate_for(profile)?;
    if !(profile.minimum_revision()..i32::MAX as u64).contains(&revision) || !(1..i32::MAX as i64).contains(&wire)
        || !(1..=96).contains(&key.len()) || !key.bytes().all(|b|b.is_ascii_alphanumeric() || b"-_:".contains(&b)) {
        return Err(invalid("transfer service identity/cursor/key"));
    }
    let raw=serde_json::to_vec(&serde_json::json!({"account_id":account_id,"native_database_id":database_id,
        "command_key":key,"expected_revision":revision,"wire_revision":wire,"layout":request.layout()}))
        .map_err(|_|invalid("transfer service encoding"))?;
    if raw.len()>2048 {return Err(invalid("transfer service size"));}Ok(raw)
}

#[cfg(test)]
mod tests {
    use super::*;
    const ACCOUNT:&str="00000000-0000-0000-0000-000000000001";
    fn request()->Request {Request{id:226,vehicle_inventory_id:1,slot:1,tankman_inventory_id:-1}}
    fn bytes(r:Request)->Vec<u8> {let mut b=r.id.to_le_bytes().to_vec();b.extend(COMMAND.to_le_bytes());
        b.extend(r.vehicle_inventory_id.to_le_bytes());b.extend(r.slot.to_le_bytes());b.extend(r.tankman_inventory_id.to_le_bytes());b}
    #[test] fn signed_source_widths_and_sentinels_remain_exact() {
        for slot in [-1,0,1] {let r=Request{slot,..request()};assert_eq!(Request::decode(&bytes(r)).unwrap(),r);assert!(r.validate_supported().is_ok());}
        let r=Request{vehicle_inventory_id:i64::MAX,slot:i32::MIN,tankman_inventory_id:i32::MAX,..request()};
        assert_eq!(Request::decode(&bytes(r)).unwrap(),r);assert!(r.validate_supported().is_err());
    }
    #[test] fn truncated_wrong_command_id_and_trailing_envelopes_fail() {
        let b=bytes(request());for n in 0..20 {assert!(Request::decode(&b[..n]).is_err());}
        let mut b=b;b.push(0);assert!(Request::decode(&b).is_err());
        for id in [0,-1] {assert!(Request::decode(&bytes(Request{id,..request()})).is_err());}
        let mut b=bytes(request());b[2..4].copy_from_slice(&157i16.to_le_bytes());assert!(Request::decode(&b).is_err());
    }
    #[test] fn exact_bridge_request_and_unsupported_selection_boundary() {
        let b=service_request(ACCOUNT,900001,"p04f:abc:226",8,1,request()).unwrap();
        let v:serde_json::Value=serde_json::from_slice(&b).unwrap();assert_eq!(v["layout"],serde_json::json!([1,1,-1]));
        for r in [Request{vehicle_inventory_id:2,..request()},Request{slot:2,..request()},Request{tankman_inventory_id:0,..request()},
            Request{slot:-1,tankman_inventory_id:1,..request()}] {assert!(service_request(ACCOUNT,900001,"key",8,1,r).is_err());}
        for (revision,wire) in [(6,1),(8,0),(i32::MAX as u64,1),(8,i32::MAX as i64)] {
            assert!(service_request(ACCOUNT,900001,"key",revision,wire,request()).is_err());}
        for key in ["", "a b", "a\n", "ключ"] {assert!(service_request(ACCOUNT,900001,key,8,1,request()).is_err());}
    }
    #[test] fn metadata_binds_mutable_configuration_and_rejects_forgery_duplicates() {
        let state=b"\x80\x02}.";
        let v=serde_json::json!({"version":1,"account_id":ACCOUNT,"native_database_id":900001,"revision":8,"wire_revision":1,
            "policy_sha256":POLICY_SHA256,"state_sha256":format!("{:x}",Sha256::digest(state)),"command":105,
            "vehicle_inventory_id":1,"free_recruitment_left":0,"configuration_revision":9,"battle":false});
        let raw=serde_json::to_vec(&v).unwrap();assert!(metadata_bytes(&raw,state,ACCOUNT,900001,8,1).is_ok());
        assert!(metadata_bytes(&raw,b"changed",ACCOUNT,900001,8,1).is_err());
        for (k,x) in [("command",157.into()),("configuration_revision",0.into()),("battle",true.into()),("revision",7.into()),
            ("policy_sha256","0".repeat(64).into()),("free_recruitment_left",2.into()),("wire_revision",2.into())] {
            let mut bad=v.clone();bad[k]=x;assert!(metadata_bytes(&serde_json::to_vec(&bad).unwrap(),state,ACCOUNT,900001,8,1).is_err());}
        let mut duplicate=raw[..raw.len()-1].to_vec();duplicate.extend(b",\"version\":1}");
        assert!(metadata_bytes(&duplicate,state,ACCOUNT,900001,8,1).is_err());
        let mut extra=v;extra["unexpected"]=true.into();assert!(metadata_bytes(&serde_json::to_vec(&extra).unwrap(),state,ACCOUNT,900001,8,1).is_err());
    }
    #[test] fn cross_profile_keeps_wire_widths_and_requires_explicit_two_vehicle_policy() {
        let r=Request{vehicle_inventory_id:2,slot:2,tankman_inventory_id:3,..request()};
        assert_eq!(Request::decode(&bytes(r)).unwrap(),r);
        assert!(r.validate_supported().is_err());assert!(r.validate_for(Profile::Ms1Is7).is_ok());
        let encoded=service_request_for(Profile::Ms1Is7,ACCOUNT,900001,"p04g:key:226",16,1,r).unwrap();
        let v:serde_json::Value=serde_json::from_slice(&encoded).unwrap();assert_eq!(v["layout"],serde_json::json!([2,2,3]));
        for r in [Request{vehicle_inventory_id:3,..r},Request{slot:5,..r},Request{slot:-1,..r},
            Request{vehicle_inventory_id:1,slot:2,..r},Request{tankman_inventory_id:4,..r}] {
            assert!(r.validate_for(Profile::Ms1Is7).is_err());
        }
        assert!(service_request_for(Profile::Ms1Is7,ACCOUNT,900001,"key",7,1,r).is_err());
    }
    #[test] fn cross_metadata_cannot_be_substituted_for_predecessor_or_weaken_vehicle_count() {
        let state=b"\x80\x02}.";
        let v=serde_json::json!({"version":1,"account_id":ACCOUNT,"native_database_id":900001,"revision":16,"wire_revision":1,
            "policy_sha256":CROSS_POLICY_SHA256,"state_sha256":format!("{:x}",Sha256::digest(state)),"command":105,
            "vehicle_count":2,"free_recruitment_left":0,"configuration_revision":9,"battle":false});
        let raw=serde_json::to_vec(&v).unwrap();
        assert!(metadata_bytes_for(Profile::Ms1Is7,&raw,state,ACCOUNT,900001,16,1).is_ok());
        assert!(metadata_bytes(&raw,state,ACCOUNT,900001,16,1).is_err());
        for (key,value) in [("vehicle_count",1.into()),("free_recruitment_left",1.into()),("battle",true.into()),
            ("policy_sha256",POLICY_SHA256.into()),("revision",7.into())] {
            let mut bad=v.clone();bad[key]=value;
            assert!(metadata_bytes_for(Profile::Ms1Is7,&serde_json::to_vec(&bad).unwrap(),state,ACCOUNT,900001,16,1).is_err());
        }
        let mut duplicated=raw[..raw.len()-1].to_vec();duplicated.extend(b",\"vehicle_count\":2}");
        assert!(metadata_bytes_for(Profile::Ms1Is7,&duplicated,state,ACCOUNT,900001,16,1).is_err());
    }


    #[test] fn progression_metadata_binds_policy_command_and_cursors_without_accepting_roster_substitution() {
        let state=b"\x80\x02}.";
        let v=serde_json::json!({"version":1,"account_id":ACCOUNT,"native_database_id":900001,"revision":42,"wire_revision":1,
            "policy_sha256":PROGRESSION_POLICY_SHA256,"state_sha256":format!("{:x}",Sha256::digest(state)),"command":151,
            "transfer_command":105,"role_level":50,"vehicle_count":2,"free_recruitment_left":6,"configuration_revision":33,"battle":false});
        let check=|v:&serde_json::Value|metadata_bytes_for(Profile::Progression,&serde_json::to_vec(v).unwrap(),state,ACCOUNT,900001,42,1);
        assert!(check(&v).is_ok());
        for (key,value) in [("command",309.into()),("transfer_command",151.into()),("role_level",100.into()),
            ("policy_sha256",ROSTER_POLICY_SHA256.into()),("revision",9.into()),("wire_revision",2.into()),
            ("vehicle_count",1.into()),("configuration_revision",1.into()),("battle",true.into()),("free_recruitment_left",14.into())] {
            let mut row=v.clone();row[key]=value;assert!(check(&row).is_err(),"{key}");
        }
        for key in v.as_object().unwrap().keys() {let mut row=v.clone();row.as_object_mut().unwrap().remove(key);assert!(check(&row).is_err());}
        let raw=serde_json::to_vec(&v).unwrap();
        assert!(metadata_bytes_for(Profile::Roster,&raw,state,ACCOUNT,900001,42,1).is_err());
        assert!(metadata_bytes_for(Profile::Progression,&raw,b"changed",ACCOUNT,900001,42,1).is_err());
        let mut duplicate=raw[..raw.len()-1].to_vec();duplicate.extend(b",\"command\":151}");
        assert!(metadata_bytes_for(Profile::Progression,&duplicate,state,ACCOUNT,900001,42,1).is_err());
        assert!(service_request_for(Profile::Progression,ACCOUNT,900001,"key",9,1,request()).is_err());
        assert!(Request{vehicle_inventory_id:2,slot:4,tankman_inventory_id:16,..request()}.validate_for(Profile::Progression).is_ok());
    }
    #[test] fn dismissal_metadata_pins_sparse_roster_policy_and_predecessor_incompatibility() {
        let state=b"\x80\x02}.";
        let v=serde_json::json!({"version":1,"account_id":ACCOUNT,"native_database_id":900001,"revision":49,"wire_revision":1,
            "policy_sha256":DISMISSAL_POLICY_SHA256,"state_sha256":format!("{:x}",Sha256::digest(state)),"command":306,
            "transfer_command":105,"role_level":50,"vehicle_count":2,"free_recruitment_left":6,"configuration_revision":39,"battle":false});
        let check=|v:&serde_json::Value|metadata_bytes_for(Profile::Dismissal,&serde_json::to_vec(v).unwrap(),state,ACCOUNT,900001,49,1);
        assert!(check(&v).is_ok());
        for (key,value) in [("command",151.into()),("policy_sha256",PROGRESSION_POLICY_SHA256.into()),("vehicle_count",1.into()),
            ("role_level",100.into()),("free_recruitment_left",14.into()),("battle",true.into()),("revision",10.into())] {
            let mut row=v.clone();row[key]=value;assert!(check(&row).is_err(),"{key}");
        }
        for key in v.as_object().unwrap().keys() {let mut row=v.clone();row.as_object_mut().unwrap().remove(key);assert!(check(&row).is_err());}
        let raw=serde_json::to_vec(&v).unwrap();
        assert!(metadata_bytes_for(Profile::Progression,&raw,state,ACCOUNT,900001,49,1).is_err());
        let mut duplicate=raw[..raw.len()-1].to_vec();duplicate.extend(b",\"command\":306}");
        assert!(metadata_bytes_for(Profile::Dismissal,&duplicate,state,ACCOUNT,900001,49,1).is_err());
        assert!(service_request_for(Profile::Dismissal,ACCOUNT,900001,"key",10,1,request()).is_err());
        assert!(Request{vehicle_inventory_id:2,slot:4,tankman_inventory_id:16,..request()}.validate_for(Profile::Dismissal).is_ok());
    }
    #[test] fn roster_transfer_accepts_bounded_new_identities_only_under_explicit_profile() {
        for id in 1..=16 {for slot in 0..5 {
            let r=Request{vehicle_inventory_id:2,slot,tankman_inventory_id:id,..request()};
            assert!(r.validate_for(Profile::Roster).is_ok());
            assert_eq!(r.validate_for(Profile::Ms1Is7).is_ok(),id<=3);
        }}
        for id in [0,17,i32::MAX] {
            assert!(Request{tankman_inventory_id:id,..request()}.validate_for(Profile::Roster).is_err());
        }
        assert!(service_request_for(Profile::Roster,ACCOUNT,900001,"key",8,1,request()).is_err());
    }
    #[test] fn roster_metadata_binds_both_commands_training_capacity_and_exact_state() {
        let state=b"\x80\x02}.";
        let v=serde_json::json!({"version":1,"account_id":ACCOUNT,"native_database_id":900001,"revision":31,"wire_revision":1,
            "policy_sha256":ROSTER_POLICY_SHA256,"state_sha256":format!("{:x}",Sha256::digest(state)),"command":309,
            "transfer_command":105,"role_level":50,"vehicle_count":2,"free_recruitment_left":13,"configuration_revision":23,"battle":false});
        let check=|v:&serde_json::Value|metadata_bytes_for(Profile::Roster,&serde_json::to_vec(v).unwrap(),state,ACCOUNT,900001,31,1);
        assert!(check(&v).is_ok());
        for free in 0..=13 {let mut row=v.clone();row["free_recruitment_left"]=free.into();assert!(check(&row).is_ok());}
        for (key,value) in [("command",105.into()),("transfer_command",309.into()),("role_level",100.into()),
            ("vehicle_count",1.into()),("free_recruitment_left",14.into()),("battle",true.into()),
            ("policy_sha256",CROSS_POLICY_SHA256.into()),("configuration_revision",1.into()),("revision",8.into())] {
            let mut bad=v.clone();bad[key]=value;assert!(check(&bad).is_err(),"{key}");
        }
        for key in v.as_object().unwrap().keys() {let mut missing=v.clone();missing.as_object_mut().unwrap().remove(key);assert!(check(&missing).is_err());}
        let raw=serde_json::to_vec(&v).unwrap();
        assert!(metadata_bytes_for(Profile::Ms1Is7,&raw,state,ACCOUNT,900001,31,1).is_err());
        assert!(metadata_bytes_for(Profile::Roster,&raw,b"wrong",ACCOUNT,900001,31,1).is_err());
        let mut dup=raw[..raw.len()-1].to_vec();dup.extend(b",\"role_level\":50}");
        assert!(metadata_bytes_for(Profile::Roster,&dup,state,ACCOUNT,900001,31,1).is_err());
    }

    #[test] fn barracks_metadata_pins_command_shop_policy_and_rejects_old_profile() {
        let state=b"\x80\x02}.";
        let value=serde_json::json!({"version":1,"account_id":ACCOUNT,"native_database_id":900001,"revision":56,"wire_revision":1,
            "policy_sha256":BARRACKS_POLICY_SHA256,"state_sha256":format!("{:x}",Sha256::digest(state)),"command":303,
            "transfer_command":105,"role_level":50,"vehicle_count":2,"free_recruitment_left":5,"configuration_revision":45,"battle":false});
        let check=|v:&serde_json::Value|metadata_bytes_for(Profile::Barracks,&serde_json::to_vec(v).unwrap(),state,ACCOUNT,900001,56,1);
        assert!(check(&value).is_ok());
        for (key,replacement) in [("command",306.into()),("policy_sha256",DISMISSAL_POLICY_SHA256.into()),
            ("wire_revision",2.into()),("role_level",100.into()),("free_recruitment_left",14.into()),("battle",true.into())] {
            let mut bad=value.clone();bad[key]=replacement;assert!(check(&bad).is_err());
        }
        for key in value.as_object().unwrap().keys() {let mut bad=value.clone();bad.as_object_mut().unwrap().remove(key);assert!(check(&bad).is_err());}
        let raw=serde_json::to_vec(&value).unwrap();assert!(metadata_bytes_for(Profile::Dismissal,&raw,state,ACCOUNT,900001,56,1).is_err());
        let mut duplicate=raw[..raw.len()-1].to_vec();duplicate.extend(b",\"command\":303}");
        assert!(metadata_bytes_for(Profile::Barracks,&duplicate,state,ACCOUNT,900001,56,1).is_err());
    }

}
