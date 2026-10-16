//! Additive draft. Version4 selection proves the loss wrapper, not a V2 cast.
//! The old selection.rs codec and policies remain unchanged.
use std::io;
use serde_json::{Value,json};
use sha2::{Digest,Sha256};
use crate::{profile13_loss091 as loss,profile13_v2091 as base};
use crate::battle091::profile13::Context;
use super::selection as old;

pub const SCHEMA:&str="p10b-owned-selection-loss.v1";
pub const MAX_REQUEST:usize=3072;
pub const MAX_REPLY:usize=6144;
fn bad(s:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("P10B loss selection: {s}"))}
fn sha(s:&str)->bool{s.len()==64&&s.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b))}
fn exact(v:&Value,keys:&[&str])->io::Result<()>{let m=v.as_object().ok_or_else(||bad("object"))?;
    if m.len()!=keys.len()||keys.iter().any(|k|!m.contains_key(*k)){return Err(bad("exact fields"));}Ok(())}
fn text<'a>(v:&'a Value,k:&str)->io::Result<&'a str>{v[k].as_str().ok_or_else(||bad("text"))}
fn number(v:&Value,k:&str)->io::Result<u64>{v[k].as_u64().ok_or_else(||bad("integer"))}
fn digest(v:&Value)->io::Result<String>{Ok(format!("{:x}",Sha256::digest(serde_json::to_vec(v).map_err(|_|bad("canonical"))?)))}

#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Stamp{pub base:old::Stamp,pub loss_policy_sha256:String,pub loss_companion_sha256:String}
impl Stamp{
    pub fn parse(v:&Value)->io::Result<Self>{
        exact(v,&["native_state_sha256","owner_source_sha256","catalog_sha256","pool_registry_sha256",
            "mixed_policy_sha256","shell_catalog_sha256","terminal_policy_sha256","loss_policy_sha256","loss_companion_sha256"])?;
        let mut b=v.clone();b.as_object_mut().ok_or_else(||bad("stamp"))?.remove("loss_policy_sha256");
        b.as_object_mut().ok_or_else(||bad("stamp"))?.remove("loss_companion_sha256");
        let s=Self{base:old::Stamp::parse(&b)?,loss_policy_sha256:text(v,"loss_policy_sha256")?.into(),
            loss_companion_sha256:text(v,"loss_companion_sha256")?.into()};s.validate()?;Ok(s)
    }
    pub fn validate(&self)->io::Result<()>{self.base.validate()?;
        if self.loss_policy_sha256!=loss::POLICY_SHA256||!sha(&self.loss_companion_sha256){return Err(bad("loss stamp"));}Ok(())}
    pub fn value(&self)->Value{let mut v=self.base.value();v["loss_policy_sha256"]=self.loss_policy_sha256.clone().into();
        v["loss_companion_sha256"]=self.loss_companion_sha256.clone().into();v}
}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Request{pub base:old::Request,pub projection_stamp:Stamp}
impl Request{
    pub fn new(c:&Context,native_inventory_id:u32,stamp:Stamp)->io::Result<Self>{stamp.validate()?;
        let r=Self{base:old::Request::new(c,native_inventory_id,stamp.base.clone())?,projection_stamp:stamp};r.validate()?;Ok(r)}
    fn validate(&self)->io::Result<()>{self.projection_stamp.validate()?;old::encode_request(&self.base)?;
        if self.base.projection_stamp!=self.projection_stamp.base{return Err(bad("changed old stamp member"));}Ok(())}
}
pub fn encode_request(r:&Request)->io::Result<Vec<u8>>{r.validate()?;
    let mut v=base::bounded_json(&old::encode_request(&r.base)?,old::MAX_REQUEST)?;
    v["version"]=4.into();v["contract"]=loss::CONTRACT.into();v["projection_stamp"]=r.projection_stamp.value();
    let raw=serde_json::to_vec(&v).map_err(|_|bad("request JSON"))?;base::bounded_json(&raw,MAX_REQUEST)?;Ok(raw)}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Selection{request:Request,aggregate_sha256:String,frozen:loss::FrozenLoss,fingerprint:String}
impl Selection{
    pub fn request(&self)->&Request{&self.request}
    pub fn frozen(&self)->&loss::FrozenLoss{&self.frozen}
    pub fn fingerprint(&self)->&str{&self.fingerprint}
    pub fn aggregate_sha256(&self)->&str{&self.aggregate_sha256}
    pub(crate) fn into_parts(self)->(Request,String,loss::FrozenLoss,String){(self.request,self.aggregate_sha256,self.frozen,self.fingerprint)}
}
pub fn parse_reply(raw:&[u8],r:&Request)->io::Result<Selection>{r.validate()?;let v=base::bounded_json(raw,MAX_REPLY)?;
    exact(&v,&["version","contract","schema","operation","status","account_id","native_database_id","run_id","native_inventory_id",
        "revision","projection_stamp","aggregate_sha256","frozen","frozen_sha256","fingerprint"])?;
    let q=&r.base;
    if number(&v,"version")?!=4||text(&v,"contract")?!=loss::CONTRACT||text(&v,"schema")?!=SCHEMA
        ||text(&v,"operation")?!="select"||text(&v,"status")?!="ready"||text(&v,"account_id")?!=q.account_id
        ||number(&v,"native_database_id")?!=q.native_database_id as u64||text(&v,"run_id")?!=q.run_id
        ||number(&v,"native_inventory_id")?!=q.native_inventory_id as u64||number(&v,"revision")?!=q.expected_revision{
        return Err(bad("owner/run/revision/selection"));}
    let stamp=Stamp::parse(&v["projection_stamp"])?;if stamp!=r.projection_stamp{return Err(bad("actual stamp changed"));}
    let aggregate=text(&v,"aggregate_sha256")?;let frozen_sha=text(&v,"frozen_sha256")?;let fingerprint=text(&v,"fingerprint")?;
    if !sha(aggregate)||!sha(frozen_sha)||!sha(fingerprint){return Err(bad("digest shape"));}
    let frozen=loss::parse_frozen(&v["frozen"],&q.account_id,frozen_sha)?;
    if frozen.base.native_inventory_id!=q.native_inventory_id{return Err(bad("frozen inventory"));}
    let binding=json!({"schema":SCHEMA,"contract":loss::CONTRACT,"account_id":q.account_id,"native_database_id":q.native_database_id,
        "run_id":q.run_id,"native_inventory_id":q.native_inventory_id,"revision":q.expected_revision,"projection_stamp":stamp.value(),
        "aggregate_sha256":aggregate,"frozen_sha256":frozen_sha});
    if digest(&binding)?!=fingerprint{return Err(bad("wrapper fingerprint"));}
    Ok(Selection{request:r.clone(),aggregate_sha256:aggregate.into(),frozen,fingerprint:fingerprint.into()})}

#[cfg(test)]
#[path="selection_loss_tests.rs"]
mod tests;
