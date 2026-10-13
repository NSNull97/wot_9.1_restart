//! Native #717 CMD105 adapter. The common assignment rules live in the store.
//! This opt-in profile binds only the currently imported mutable MS-1 crew.
//! Wire0x8e is a source-table candidate until measured in a real client capture.
use std::{io,path::Path};
use sha2::{Digest,Sha256};

pub const CANDIDATE_METHOD:u8=0x8e;
pub const PAYLOAD_BYTES:usize=20;
pub const COMMAND:i16=105;
pub const POLICY_SHA256:&str="35a58c8e13d9b815f8552371bbd6556ba10c091753861e697e522d6a5c877cb2";
fn invalid(message:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,message)}

struct Binding {
    version:u32,account_id:String,native_database_id:i32,revision:u64,wire_revision:i64,
    policy_sha256:String,state_sha256:String,command:i16,vehicle_inventory_id:i64,
    free_recruitment_left:u64,configuration_revision:u64,battle:bool,
}
impl Binding {
    fn parse(raw:&[u8])->io::Result<Self> {
        let super::crew_service091::MetadataObject(v)=serde_json::from_slice(raw).map_err(|_|invalid("transfer metadata shape"))?;
        let keys=["version","account_id","native_database_id","revision","wire_revision","policy_sha256","state_sha256",
            "command","vehicle_inventory_id","free_recruitment_left","configuration_revision","battle"];
        if v.len()!=keys.len() || keys.iter().any(|k|!v.contains_key(*k)) {return Err(invalid("transfer metadata fields"));}
        let u=|k:&str|v[k].as_u64().ok_or_else(||invalid("transfer metadata unsigned integer"));
        let i=|k:&str|v[k].as_i64().ok_or_else(||invalid("transfer metadata signed integer"));
        let s=|k:&str|v[k].as_str().map(str::to_owned).ok_or_else(||invalid("transfer metadata string"));
        Ok(Self{version:u("version")?.try_into().map_err(|_|invalid("transfer version bound"))?,account_id:s("account_id")?,
            native_database_id:i("native_database_id")?.try_into().map_err(|_|invalid("transfer database ID bound"))?,
            revision:u("revision")?,wire_revision:i("wire_revision")?,policy_sha256:s("policy_sha256")?,state_sha256:s("state_sha256")?,
            command:i("command")?.try_into().map_err(|_|invalid("transfer command bound"))?,vehicle_inventory_id:i("vehicle_inventory_id")?,
            free_recruitment_left:u("free_recruitment_left")?,configuration_revision:u("configuration_revision")?,
            battle:v["battle"].as_bool().ok_or_else(||invalid("transfer battle flag"))?})
    }
}

pub fn metadata(directory:&Path,account_id:&str,database_id:i32,revision:u64,wire:i64)->io::Result<()> {
    let raw=super::crew_service091::fixture_file(directory,"crew-transfer.json",4096)?;
    let state=super::crew_service091::fixture_file(directory,"state.bin",16384)?;
    metadata_bytes(&raw,&state,account_id,database_id,revision,wire)
}
fn metadata_bytes(raw:&[u8],state:&[u8],account_id:&str,database_id:i32,revision:u64,wire:i64)->io::Result<()> {
    super::crew_service091::identity(account_id,database_id)?;
    if raw.len()>4096 || state.is_empty() || state.len()>16384 {return Err(invalid("transfer metadata size"));}
    let b=Binding::parse(raw)?;
    if b.version!=1 || b.account_id!=account_id || b.native_database_id!=database_id
        || !(7..=i32::MAX as u64).contains(&b.revision) || b.revision!=revision
        || b.wire_revision!=1 || wire!=1 || b.policy_sha256!=POLICY_SHA256
        || b.state_sha256!=format!("{:x}",Sha256::digest(state))
        || b.command!=COMMAND || b.vehicle_inventory_id!=1 || b.free_recruitment_left>1
        || !(1..=i32::MAX as u64).contains(&b.configuration_revision)
        || b.configuration_revision<2-b.free_recruitment_left || b.battle {
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
        // Available imported profile only; ownership/role/seat/reservation are
        // independently checked against authoritative data by the shared writer.
        if self.id<=0 || self.vehicle_inventory_id!=1 || !(-1..=1).contains(&self.slot)
            || !(self.tankman_inventory_id==-1 || (1..=3).contains(&self.tankman_inventory_id))
            || (self.slot==-1 && self.tankman_inventory_id!=-1) {
            return Err(invalid("unsupported transfer profile/selection"));
        }
        Ok(())
    }
    pub fn layout(&self)->[i64;3] {[self.vehicle_inventory_id,self.slot as i64,self.tankman_inventory_id as i64]}
}
pub fn service_request(account_id:&str,database_id:i32,key:&str,revision:u64,wire:i64,request:Request)->io::Result<Vec<u8>> {
    super::crew_service091::identity(account_id,database_id)?;request.validate_supported()?;
    if !(7..i32::MAX as u64).contains(&revision) || !(1..i32::MAX as i64).contains(&wire)
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
}
