//! Bounded read-only P10B selection codec; independent of the V2 writer DTO.
//! A distinct read-only contract. Existing battle-v2 Request/Inspect are intact.
//! Stamp must originate in the trusted verified current fixture, never in CMD402.
use std::io;
use serde_json::{Value,json};
use sha2::{Digest,Sha256};
use crate::profile13_v2091 as battle;
use crate::battle091::profile13::Context;

pub const SCHEMA:&str="p10b-owned-selection.v1";
pub const MAX_REQUEST:usize=2048;
pub const MAX_REPLY:usize=4096;
const CATALOG_SHA256:&str="b6baecd204444d1e894253fa6c19c61478993b8ae87c71373633989d3a8ee460";
fn bad(s:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("P10B selection: {s}"))}
fn sha(s:&str)->bool{s.len()==64&&s.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b))}
fn uuid(s:&str)->bool{s.len()==36&&s.bytes().enumerate().all(|(i,b)|if[8,13,18,23].contains(&i){b==b'-'}else{
    b.is_ascii_digit()||(b'a'..=b'f').contains(&b)})&&matches!(s.as_bytes()[14],b'1'..=b'5')}
fn exact(v:&Value,keys:&[&str])->io::Result<()>{let m=v.as_object().ok_or_else(||bad("object"))?;
    if m.len()!=keys.len()||keys.iter().any(|k|!m.contains_key(*k)){return Err(bad("exact fields"));}Ok(())}
fn text<'a>(v:&'a Value,k:&str)->io::Result<&'a str>{v[k].as_str().ok_or_else(||bad("text"))}
fn number(v:&Value,k:&str)->io::Result<u64>{v[k].as_u64().ok_or_else(||bad("integer"))}
fn json_digest(v:&Value)->io::Result<String>{Ok(format!("{:x}",Sha256::digest(serde_json::to_vec(v).map_err(|_|bad("canonical JSON"))?)))}

#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Stamp{
    pub native_state_sha256:String,
    pub owner_source_sha256:String,
    pub catalog_sha256:String,
    pub pool_registry_sha256:String,
    pub mixed_policy_sha256:String,
    pub shell_catalog_sha256:String,
    pub terminal_policy_sha256:String,
}
impl Stamp{
    pub fn parse(v:&Value)->io::Result<Self>{
        exact(v,&["native_state_sha256","owner_source_sha256","catalog_sha256","pool_registry_sha256","mixed_policy_sha256","shell_catalog_sha256","terminal_policy_sha256"])?;
        let s=Self{native_state_sha256:text(v,"native_state_sha256")?.into(),owner_source_sha256:text(v,"owner_source_sha256")?.into(),
            catalog_sha256:text(v,"catalog_sha256")?.into(),pool_registry_sha256:text(v,"pool_registry_sha256")?.into(),
            mixed_policy_sha256:text(v,"mixed_policy_sha256")?.into(),shell_catalog_sha256:text(v,"shell_catalog_sha256")?.into(),
            terminal_policy_sha256:text(v,"terminal_policy_sha256")?.into()};s.validate()?;Ok(s)
    }
    pub fn value(&self)->Value{json!({"native_state_sha256":self.native_state_sha256,"owner_source_sha256":self.owner_source_sha256,
        "catalog_sha256":self.catalog_sha256,"pool_registry_sha256":self.pool_registry_sha256,"mixed_policy_sha256":self.mixed_policy_sha256,
        "shell_catalog_sha256":self.shell_catalog_sha256,"terminal_policy_sha256":self.terminal_policy_sha256})}
    pub fn validate(&self)->io::Result<()>{
        if ![&self.native_state_sha256,&self.owner_source_sha256,&self.catalog_sha256,&self.pool_registry_sha256,
            &self.mixed_policy_sha256,&self.shell_catalog_sha256,&self.terminal_policy_sha256].into_iter().all(|s|sha(s))
            ||self.catalog_sha256!=CATALOG_SHA256||self.pool_registry_sha256!=crate::p04m_companion091::REGISTRY_SHA256
            ||self.mixed_policy_sha256!=battle::POLICY_SHA256||self.shell_catalog_sha256!=crate::p06t_shells091::SOURCE_DATA_SHA256
            ||self.terminal_policy_sha256!=battle::TERMINAL_MANIFEST_SHA256{return Err(bad("source stamp"));}Ok(())
    }
}

#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Request{pub account_id:String,pub native_database_id:i32,pub run_id:String,
    pub expected_revision:u64,pub native_inventory_id:u32,pub projection_stamp:Stamp}
impl Request{
    /// Context comes from authenticated Session/Config. This read does not use
    /// command_key or consume a State admission/mandatory-terminal command slot.
    pub fn new(c:&Context,native_inventory_id:u32,projection_stamp:Stamp)->io::Result<Self>{
        let r=Self{account_id:c.account_id.clone(),native_database_id:c.native_database_id,run_id:c.run_id.clone(),
            expected_revision:c.expected_revision,native_inventory_id,projection_stamp};r.validate()?;Ok(r)
    }
    fn validate(&self)->io::Result<()>{
        if !uuid(&self.account_id)||!uuid(&self.run_id)||self.native_database_id<=0
            ||!(13..=i32::MAX as u64).contains(&self.expected_revision)||!(1..=i32::MAX as u32).contains(&self.native_inventory_id){
                return Err(bad("owner/run/revision/selection"));}self.projection_stamp.validate()
    }
}
pub fn encode_request(r:&Request)->io::Result<Vec<u8>>{
    r.validate()?;let v=json!({"version":1,"operation":"select","account_id":r.account_id,"native_database_id":r.native_database_id,
        "run_id":r.run_id,"expected_revision":r.expected_revision,"native_inventory_id":r.native_inventory_id,"projection_stamp":r.projection_stamp.value()});
    let raw=serde_json::to_vec(&v).map_err(|_|bad("request JSON"))?;battle::bounded_json(&raw,MAX_REQUEST)?;Ok(raw)
}

#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Selection{request:Request,aggregate_sha256:String,frozen:battle::Frozen,fingerprint:String}
impl Selection{
    pub fn request(&self)->&Request{&self.request}
    pub fn frozen(&self)->&battle::Frozen{&self.frozen}
    pub fn aggregate_sha256(&self)->&str{&self.aggregate_sha256}
    pub fn fingerprint(&self)->&str{&self.fingerprint}
    pub(crate) fn into_parts(self)->(Request,String,battle::Frozen,String){
        (self.request,self.aggregate_sha256,self.frozen,self.fingerprint)
    }
}
pub fn parse_reply(raw:&[u8],request:&Request)->io::Result<Selection>{
    request.validate()?;let v=battle::bounded_json(raw,MAX_REPLY)?;
    exact(&v,&["version","schema","operation","status","account_id","native_database_id","run_id","native_inventory_id", "revision",
        "projection_stamp","aggregate_sha256","frozen","frozen_sha256","fingerprint"])?;
    if number(&v,"version")?!=1||text(&v,"schema")?!=SCHEMA||text(&v,"operation")?!="select"||text(&v,"status")?!="ready"
        ||text(&v,"account_id")?!=request.account_id||number(&v,"native_database_id")?!=request.native_database_id as u64
        ||text(&v,"run_id")?!=request.run_id||number(&v,"native_inventory_id")?!=u64::from(request.native_inventory_id)
        ||number(&v,"revision")?!=request.expected_revision{return Err(bad("bound reply identity/revision"));}
    let stamp=Stamp::parse(&v["projection_stamp"])?;
    stamp.validate()?;if stamp!=request.projection_stamp{return Err(bad("projection stamp mismatch"));}
    let aggregate=text(&v,"aggregate_sha256")?;let frozen_sha=text(&v,"frozen_sha256")?;let fingerprint=text(&v,"fingerprint")?;
    if !sha(aggregate)||!sha(frozen_sha)||!sha(fingerprint){return Err(bad("hash shape"));}
    let frozen=battle::parse_frozen(&v["frozen"],&request.account_id,frozen_sha)?;
    if frozen.native_inventory_id!=request.native_inventory_id{return Err(bad("selected frozen mismatch"));}
    // aggregate_sha256 hashes canonical authoritative aggregate JSON. The
    // distinct stamp.native_state_sha256 hashes actual encoded state.bin.
    // Neither claims to be recomputable from the other hash or from Frozen.
    let binding=json!({"schema":SCHEMA,"account_id":request.account_id,"native_database_id":request.native_database_id,
        "run_id":request.run_id,"native_inventory_id":request.native_inventory_id,"revision":request.expected_revision,
        "projection_stamp":stamp.value(),"aggregate_sha256":aggregate,"frozen_sha256":frozen_sha});
    if json_digest(&binding)?!=fingerprint{return Err(bad("selection fingerprint"));}
    Ok(Selection{request:request.clone(),aggregate_sha256:aggregate.into(),frozen,fingerprint:fingerprint.into()})
}

#[cfg(test)]
#[path="selection_tests.rs"]
mod tests;
