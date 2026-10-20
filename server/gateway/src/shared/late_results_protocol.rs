//! Fixed new late-result namespace. Pure codec, no socket/thread/SQLite here.
//! Old mixed2/loss4 request/reply readers and accounting stay untouched.
use std::{io,sync::Arc};
use serde_json::{Value,json};
use sha2::{Digest,Sha256};
use crate::identity091;
use super::late_results_capture::{self as capture,Capture,Link};
pub(super) const ENDPOINT:&str="/internal/native/late-result-append";
pub(super) const CONTRACT:&str="p08c-late-result-append.v1";
pub(super) const POLICY_SHA256:&str="f6ae697fb920b9359a2cb0375aa1fd68538a183fab1c8f136772c703de6abe04";
fn bad(why:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("late results protocol: {why}"))}
fn keys(v:&Value,names:&[&str])->io::Result<()>{let m=v.as_object().ok_or_else(||bad("object"))?;
    if m.len()!=names.len()||names.iter().any(|n|!m.contains_key(*n)){return Err(bad("closed fields"));}Ok(())}
fn text<'a>(v:&'a Value,key:&str)->io::Result<&'a str>{v[key].as_str().ok_or_else(||bad("string"))}
fn hash(v:&str)->bool{v.len()==64&&v.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b))}
fn digest(raw:&[u8])->String{format!("{:x}",Sha256::digest(raw))}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub(super) enum Operation{ReleaseStamp,Append}
impl Operation{fn label(self)->&'static str{match self{Self::ReleaseStamp=>"release_stamp",Self::Append=>"append"}}}
#[derive(Clone,Debug,PartialEq,Eq)]
pub(super) struct ReleaseStamp{
    source_contract:String,run_id:String,battle_id:String,arena_id:String,
    reservation_id:String,native_inventory_id:u32,frozen_sha256:String,
    release_terminal_sha256:String,finished_revision:u64,reason:String,
}
impl ReleaseStamp{
    pub(super) fn finished_revision(&self)->u64{self.finished_revision}
    pub(super) fn reason(&self)->&str{&self.reason}
    fn parse(v:&Value)->io::Result<Self>{
        keys(v,&["source_contract","run_id","battle_id","arena_id","reservation_id","native_inventory_id","frozen_sha256","release_terminal_sha256","finished_revision","reason"])?;
        let out=Self{source_contract:text(v,"source_contract")?.into(),run_id:text(v,"run_id")?.into(),battle_id:text(v,"battle_id")?.into(),arena_id:text(v,"arena_id")?.into(),
            reservation_id:text(v,"reservation_id")?.into(),native_inventory_id:u32::try_from(v["native_inventory_id"].as_u64().ok_or_else(||bad("native inventory"))?).map_err(|_|bad("native inventory width"))?,
            frozen_sha256:text(v,"frozen_sha256")?.into(),release_terminal_sha256:text(v,"release_terminal_sha256")?.into(),
            finished_revision:v["finished_revision"].as_u64().ok_or_else(||bad("finished revision"))?,reason:text(v,"reason")?.into()};
        if !hash(&out.frozen_sha256)||!hash(&out.release_terminal_sha256)||out.finished_revision<14||out.finished_revision>i32::MAX as u64
            ||out.native_inventory_id==0||out.native_inventory_id>i32::MAX as u32||!["manual_leave","disconnect","battle_finished"].contains(&out.reason.as_str()){
            return Err(bad("source release stamp bounds"));}Ok(out)
    }
}
/// Immutable bounded worker request. Future manager retains SAME Task/body/key
/// after ambiguous completion; it never creates another Finish or writes CAS.
#[derive(Clone)]
pub(super) struct Task{owner:Arc<identity091::Profile>,operation:Operation,body:Arc<Vec<u8>>,request:Value,sha256:String,
    expected_finished_revision:u64,expected_reason:String,expected_seal:Option<String>}
impl Task{
    fn make(capture:&Capture,slot:usize,operation:Operation,stamp:Option<&ReleaseStamp>)->io::Result<Self>{
        let expected_finished_revision=capture.eligible(slot)?.ok_or_else(||bad("not sealed/actually Finished; no task"))?;
        let link=capture.links().iter().find(|l|l.slot()==slot).ok_or_else(||bad("linked slot"))?;
        let expected_reason=capture.release_reason(slot)?.ok_or_else(||bad("missing release reason"))?.to_owned();
        if !["manual_leave","disconnect"].contains(&expected_reason.as_str()){return Err(bad("not a late release"));}
        let mut request=Self::link_request(capture,link,operation);
        let expected_seal=if operation==Operation::Append{
            let stamp=stamp.ok_or_else(||bad("append requires actual readonly stamp"))?;
            Self::matches_stamp(&request,expected_finished_revision,&expected_reason,stamp)?;
            request["release_terminal_sha256"]=stamp.release_terminal_sha256.clone().into();request["finished_revision"]=stamp.finished_revision.into();
            let seal=capture.seal().ok_or_else(||bad("missing immutable seal"))?;request["seal_json"]=seal.raw().into();Some(seal.sha256().to_owned())
        }else{if stamp.is_some(){return Err(bad("stamp read cannot carry append stamp"));}None};
        let raw=capture::canonical(&request)?.into_bytes();
        if raw.len()>if operation==Operation::Append{capture::MAX_HTTP}else{4096}{return Err(bad("encoded HTTP fixed body budget"));}
        // Validate the new outgoing JSON against the established bounded scalar
        // reader; nested strings remain canonical own artifacts, no pickle.
        crate::profile13_v2091::bounded_json(&raw,if operation==Operation::Append{capture::MAX_HTTP}else{4096})?;
        let sha256=digest(&raw);Ok(Self{owner:link.owner().clone(),operation,body:Arc::new(raw),request,sha256,
            expected_finished_revision,expected_reason,expected_seal})
    }
    fn link_request(c:&Capture,l:&Link,operation:Operation)->Value{
        let key=format!("p08c:late:{}:{}:{}:{}",c.run(),c.battle(),l.slot(),operation.label());
        json!({"version":1,"contract":CONTRACT,"operation":operation.label(),"account_id":l.owner().account_id,
            "native_database_id":l.owner().database_id,"command_key":key,"run_id":c.run(),"battle_id":format!("{}:{}",c.run(),c.battle()),
            "arena_id":c.battle().to_string(),"native_inventory_id":l.admission().base().native_inventory_id,
            "reservation_id":l.admission().reservation(),"source_contract":l.admission().source_contract(),"frozen_sha256":l.admission().frozen_sha()})
    }
    fn matches_stamp(request:&Value,revision:u64,reason:&str,stamp:&ReleaseStamp)->io::Result<()>{
        if stamp.source_contract!=text(request,"source_contract")?||stamp.run_id!=text(request,"run_id")?
            ||stamp.battle_id!=text(request,"battle_id")?||stamp.arena_id!=text(request,"arena_id")?
            ||stamp.reservation_id!=text(request,"reservation_id")?||u64::from(stamp.native_inventory_id)!=request["native_inventory_id"].as_u64().ok_or_else(||bad("native inventory"))?
            ||stamp.frozen_sha256!=text(request,"frozen_sha256")?||stamp.finished_revision!=revision||stamp.reason!=reason{
            return Err(bad("actual release stamp differs from frozen source/Finished receipt"));}Ok(())
    }
    pub(super) fn release_stamp(c:&Capture,slot:usize)->io::Result<Self>{Self::make(c,slot,Operation::ReleaseStamp,None)}
    pub(super) fn append(c:&Capture,slot:usize,stamp:&ReleaseStamp)->io::Result<Self>{Self::make(c,slot,Operation::Append,Some(stamp))}
    pub(super) fn owner(&self)->&Arc<identity091::Profile>{&self.owner}
    pub(super) fn body(&self)->&[u8]{&self.body}
    pub(super) fn request_sha256(&self)->&str{&self.sha256}
    pub(super) fn operation(&self)->Operation{self.operation}
    pub(super) fn parse_reply(&self,raw:&[u8])->io::Result<Reply>{
        let v=crate::profile13_v2091::bounded_json(raw,4096)?;
        keys(&v,&["version","contract","operation","account_id","native_database_id","command_key","request_sha256","policy_sha256","status","replayed","code","seal_sha256","release_stamp"])?;
        if v["version"]!=1||text(&v,"contract")?!=CONTRACT||text(&v,"operation")?!=self.operation.label()
            ||text(&v,"account_id")?!=self.owner.account_id||v["native_database_id"].as_i64()!=Some(i64::from(self.owner.database_id))
            ||v["command_key"]!=self.request["command_key"]||text(&v,"request_sha256")?!=self.sha256||text(&v,"policy_sha256")?!=POLICY_SHA256{
            return Err(bad("reply immutable owner/request/source policy"));}
        let replayed=v["replayed"].as_bool().ok_or_else(||bad("replayed boolean"))?;
        if text(&v,"status")?=="rejected"{
            let code=text(&v,"code")?;
            if replayed||!v["seal_sha256"].is_null()||!v["release_stamp"].is_null()
                ||!["RELEASE_NOT_READY","RESULT_MISMATCH","LATE_ACTOR_STATE_CHANGED","RUN_FENCED","FOREIGN_ACCOUNT","DUPLICATE_PAYLOAD_MISMATCH","UNSUPPORTED_LATE_RESULTS_SCHEMA","INVALID_INPUT"].contains(&code){return Err(bad("unrecognized rejection"));}
            return Ok(Reply::Rejected(code.into()));
        }
        if !v["code"].is_null(){return Err(bad("successful reply with denial"));}
        let stamp=ReleaseStamp::parse(&v["release_stamp"])?;Self::matches_stamp(&self.request,self.expected_finished_revision,&self.expected_reason,&stamp)?;
        match self.operation{
            Operation::ReleaseStamp=>{if text(&v,"status")?!="stamped"||replayed||!v["seal_sha256"].is_null(){return Err(bad("readonly stamp reply shape"));}Ok(Reply::Stamped(stamp))},
            Operation::Append=>{let status=text(&v,"status")?;if !["appended","already_present"].contains(&status)||v["seal_sha256"].as_str()!=self.expected_seal.as_deref(){return Err(bad("append result seal/status"));}
                Ok(Reply::Appended{stamp,already_present:status=="already_present",replayed})},
        }
    }
}
#[derive(Clone,Debug,PartialEq,Eq)]
pub(super) enum Reply{Stamped(ReleaseStamp),Appended{stamp:ReleaseStamp,already_present:bool,replayed:bool},Rejected(String)}

#[cfg(test)]
#[path="late_results_protocol_tests.rs"]
mod tests;
