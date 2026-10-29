//! Explicit v4 ammo-rack loss accounting. V2 source/terminal policies remain
//! immutable; the new wrapper freezes its separate spending rule at admit.
use std::{fmt,io};
use serde_json::Value;
use sha2::{Digest,Sha256};
pub use crate::battle091::profile13::{Context,FinishReason};
pub use crate::profile13_v2091::{Remaining,ReservationStatus,TerminalState};
use crate::profile13_v2091::{self as base,Frozen};
use crate::gateway091::shared::lifecycle_wire::{Results,MAX_RESULT_REQUEST};

pub const VERSION:u64=4;
pub const CONTRACT:&str="p06t-ammo-rack-loss.v1";
pub const POLICY_SHA256:&str="f6369197bcf83e4915dbbb16c4c173a6fd3b38103ac08bc2e33913a9071fe94e";
pub const MAX_REPLY:usize=8192;
fn bad(reason:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("profile13 ammo loss v4: {reason}"))}
fn keys(v:&Value,names:&[&str])->io::Result<()>{let m=v.as_object().ok_or_else(||bad("object"))?;
    if m.len()!=names.len()||names.iter().any(|k|!m.contains_key(*k)){return Err(bad("exact fields"));}Ok(())}
fn text<'a>(v:&'a Value,k:&str)->io::Result<&'a str>{v[k].as_str().ok_or_else(||bad("text"))}
fn number(v:&Value,k:&str)->io::Result<u64>{v[k].as_u64().ok_or_else(||bad("integer"))}
fn flag(v:&Value,k:&str)->io::Result<bool>{v[k].as_bool().ok_or_else(||bad("boolean"))}
fn digest(v:&Value)->io::Result<String>{Ok(format!("{:x}",Sha256::digest(serde_json::to_vec(v).map_err(|_|bad("canonical"))?)))}
fn uuid(s:&str)->bool{s.len()==36&&s.bytes().enumerate().all(|(i,b)|if[8,13,18,23].contains(&i){b==b'-'}else{b.is_ascii_digit()||(b'a'..=b'f').contains(&b)})&&matches!(s.as_bytes()[14],b'1'..=b'5')}
fn id(s:&str)->bool{!s.is_empty()&&s.len()<=96&&s.bytes().all(|b|b.is_ascii_alphanumeric()||b"_:-".contains(&b))}
fn context(c:&Context)->io::Result<()>{if !uuid(&c.account_id)||!uuid(&c.run_id)||c.native_database_id<=0||!id(&c.command_key)
    ||c.expected_revision>i32::MAX as u64{return Err(bad("context"));}Ok(())}
fn rows_value(rows:&[Remaining;3])->Value{Value::Array(rows.iter().map(|s|serde_json::json!({"shell_compact_id":s.shell_compact_id,"count":s.count})).collect())}
fn rows(v:&Value)->io::Result<[Remaining;3]>{let a=v.as_array().ok_or_else(||bad("ammunition array"))?;
    if a.len()!=3{return Err(bad("three ammunition stacks"));}let mut out=Vec::new();
    for r in a{keys(r,&["shell_compact_id","count"])?;let compact=u16::try_from(number(r,"shell_compact_id")?).map_err(|_|bad("shell width"))?;
        let count=u16::try_from(number(r,"count")?).map_err(|_|bad("count width"))?;
        if compact==0||count>160||out.iter().any(|old:&Remaining|old.shell_compact_id==compact){return Err(bad("source stack bounds/unique"));}
        out.push(Remaining{shell_compact_id:compact,count});}
    out.try_into().map_err(|_|bad("stacks"))}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct LossEvent{pub shot:u32,pub attacker_slot:u8,pub target_slot:u8,pub tick:u32,pub device_sequence:u32}
impl LossEvent{
    // RES-30: slots/shots/device journal of a 30-actor battle (was 6/960/15360).
    fn validate(self)->io::Result<()>{use crate::gateway091::shared::model::{MAX_ACTORS,MAX_BATTLE_SHOTS,MAX_DAMAGE_EVENTS};
        if !(1..=MAX_BATTLE_SHOTS as u32).contains(&self.shot)||usize::from(self.attacker_slot)>=MAX_ACTORS||usize::from(self.target_slot)>=MAX_ACTORS||self.attacker_slot==self.target_slot
        ||!(1000..=216000).contains(&self.tick)||!(1..=MAX_DAMAGE_EVENTS as u32).contains(&self.device_sequence){return Err(bad("loss cause bounds"));}Ok(())}
    fn value(self)->Value{serde_json::json!({"shot":self.shot,"attacker_slot":self.attacker_slot,"target_slot":self.target_slot,"tick":self.tick,"device_sequence":self.device_sequence})}
}
fn event(v:&Value)->io::Result<Option<LossEvent>>{if v.is_null(){return Ok(None);}keys(v,&["shot","attacker_slot","target_slot","tick","device_sequence"])?;
    let e=LossEvent{shot:u32::try_from(number(v,"shot")?).map_err(|_|bad("shot width"))?,attacker_slot:u8::try_from(number(v,"attacker_slot")?).map_err(|_|bad("slot width"))?,
        target_slot:u8::try_from(number(v,"target_slot")?).map_err(|_|bad("slot width"))?,tick:u32::try_from(number(v,"tick")?).map_err(|_|bad("tick width"))?,
        device_sequence:u32::try_from(number(v,"device_sequence")?).map_err(|_|bad("device sequence width"))?};e.validate()?;Ok(Some(e))}
fn event_value(e:Option<LossEvent>)->Value{e.map_or(Value::Null,LossEvent::value)}

#[derive(Clone,Debug,PartialEq,Eq)]
pub struct FrozenLoss{pub base:Frozen,pub policy_sha256:String,pub sha256:String}
// BW-01 wire codec (tools/bw01_wire_gen.py): FrozenLoss
impl crate::bw_wire::Wire for FrozenLoss {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{base,policy_sha256,sha256}=self;W::put(base,bw_o);W::put(policy_sha256,bw_o);W::put(sha256,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{base:W::get(bw_i)?,policy_sha256:W::get(bw_i)?,sha256:W::get(bw_i)?})}
}
// end BW-01 wire codec
fn base_value(f:&Frozen)->Value{serde_json::json!({"kind":f.kind.label(),"descriptor_hex":f.descriptor.iter().map(|b|format!("{b:02x}")).collect::<String>(),
    "native_inventory_id":f.native_inventory_id,"vehicle_inventory_id":f.vehicle_inventory_id,"max_hp":f.max_hp,"crew_ids":f.crew_ids,"capacity":f.capacity,
    "initial_shell_compact_id":f.initial_shell_compact_id,"ammunition":f.ammunition.iter().map(|r|serde_json::json!({"shell_definition_id":r.shell_definition_id,
        "shell_compact_id":r.shell_compact_id,"family":r.family.source_name(),"count":r.count})).collect::<Vec<_>>()})}
fn wrapper_value(f:&FrozenLoss)->Value{serde_json::json!({"policy_sha256":f.policy_sha256,"loadout":base_value(&f.base),"loadout_sha256":f.base.sha256})}
impl FrozenLoss{pub fn validate_owned(&self,account:&str)->io::Result<()>{if parse_frozen(&wrapper_value(self),account,&self.sha256)?!=*self{return Err(bad("changed frozen wrapper"));}Ok(())}}
pub fn parse_frozen(v:&Value,account:&str,sha:&str)->io::Result<FrozenLoss>{keys(v,&["policy_sha256","loadout","loadout_sha256"])?;
    if text(v,"policy_sha256")?!=POLICY_SHA256||digest(v)?!=sha{return Err(bad("frozen spending policy/hash"));}
    let f=base::parse_frozen(&v["loadout"],account,text(v,"loadout_sha256")?)?;
    Ok(FrozenLoss{base:f,policy_sha256:POLICY_SHA256.into(),sha256:sha.into()})}

#[derive(Clone,Debug,PartialEq,Eq)]
pub enum Request{RunOpen,Inspect,Admit{battle:u64,native_inventory_id:u32},Finish{battle:u64,native_inventory_id:u32,reservation_id:String,
    remaining_ammunition:[Remaining;3],fired_ammunition:[Remaining;3],lost_ammunition:[Remaining;3],loss_event:Option<LossEvent>,
    terminal_hp:i16,terminal_state_json:String,reason:FinishReason,results_json:Option<String>}}
impl Request{pub fn operation(&self)->&'static str{match self{Self::RunOpen=>"run_open",Self::Inspect=>"inspect",Self::Admit{..}=>"admit",Self::Finish{..}=>"finish"}}
    pub fn finished_battle(&self)->Option<u64>{match self{Self::Finish{battle,..}=>Some(*battle),_=>None}}}

pub fn encode_request(c:&Context,r:&Request)->io::Result<Vec<u8>>{context(c)?;
    if !matches!(r,Request::Inspect)&&c.expected_revision<13{return Err(bad("mutation revision"));}
    let mut v=serde_json::json!({"version":VERSION,"contract":CONTRACT,"operation":r.operation(),"account_id":c.account_id,
        "native_database_id":c.native_database_id,"command_key":c.command_key,"expected_revision":c.expected_revision,"run_id":c.run_id});
    if let Request::Admit{battle,native_inventory_id}|Request::Finish{battle,native_inventory_id,..}=r{
        if *battle==0||*native_inventory_id==0{return Err(bad("battle/vehicle"));}v["battle_id"]=format!("{}:{battle}",c.run_id).into();v["native_inventory_id"]=(*native_inventory_id).into();}
    if let Request::Finish{reservation_id,remaining_ammunition,fired_ammunition,lost_ammunition,loss_event,terminal_hp,terminal_state_json,reason,results_json,..}=r{
        if !id(reservation_id)||!(0..=10000).contains(terminal_hp){return Err(bad("terminal identity/health"));}
        for a in [remaining_ammunition,fired_ammunition,lost_ammunition]{rows(&rows_value(a))?;}
        if let Some(e)=loss_event{e.validate()?;}
        let state=base::bounded_json(terminal_state_json.as_bytes(),8192)?;
        keys(&state,&["policy_revision","roster_size","crew_active","crew","devices","fire","death"])?;
        v["reservation_id"]=reservation_id.clone().into();v["remaining_ammunition"]=rows_value(remaining_ammunition);
        v["fired_ammunition"]=rows_value(fired_ammunition);v["lost_ammunition"]=rows_value(lost_ammunition);v["loss_event"]=event_value(*loss_event);
        v["terminal_hp"]=(*terminal_hp).into();v["terminal_state_json"]=serde_json::to_string(&state).map_err(|_|bad("terminal serialization"))?.into();v["reason"]=reason.name().into();
        if (*reason==FinishReason::BattleFinished)!=results_json.is_some(){return Err(bad("natural full result required"));}
        if let Some(raw)=results_json{let result=Results::from_json_p06t(raw)?;if result.participants.iter().find(|p|p.account_dbid==c.native_database_id).is_none(){return Err(bad("result owner"));}
            v["results_json"]=serde_json::to_string(&base::bounded_result_json(raw.as_bytes())?).map_err(|_|bad("result serialization"))?.into();}
    }
    let raw=serde_json::to_vec(&v).map_err(|_|bad("request serialization"))?;
    if raw.len()>if matches!(r,Request::Finish{results_json:Some(_),..}){MAX_RESULT_REQUEST}else if matches!(r,Request::Finish{..}){16384}else{2048}{return Err(bad("request bound"));}Ok(raw)
}

#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Terminal{pub reason:String,pub remaining:[Remaining;3],pub fired:[Remaining;3],pub lost:[Remaining;3],pub loss_event:Option<LossEvent>,
    pub terminal_hp:Option<i16>,pub destroyed:Option<bool>,pub repaired_hp:i16,pub state:Option<TerminalState>}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Reservation{pub reservation_id:String,pub run_id:String,pub battle:u64,pub frozen:FrozenLoss,pub status:ReservationStatus,pub result:Option<Terminal>}

fn reservation(v:&Value,account:&str)->io::Result<Reservation>{keys(v,&["reservation_id","run_id","battle_id","native_inventory_id","vehicle_inventory_id","status","frozen","frozen_sha256","result"])?;
    let key=text(v,"reservation_id")?;let run=text(v,"run_id")?;let raw=text(v,"battle_id")?;
    let battle=raw.strip_prefix(&format!("{run}:")).ok_or_else(||bad("battle run"))?.parse::<u64>().map_err(|_|bad("battle number"))?;
    if !id(key)||!uuid(run)||battle==0||raw!=format!("{run}:{battle}"){return Err(bad("reservation identity"));}
    let f=parse_frozen(&v["frozen"],account,text(v,"frozen_sha256")?)?;
    if number(v,"native_inventory_id")?!=u64::from(f.base.native_inventory_id)||text(v,"vehicle_inventory_id")?!=f.base.vehicle_inventory_id{return Err(bad("reservation source vehicle"));}
    let status=match text(v,"status")?{"active"=>ReservationStatus::Active,"finished"=>ReservationStatus::Finished,"aborted_restart"=>ReservationStatus::AbortedRestart,_=>return Err(bad("reservation status"))};
    let result=if v["result"].is_null(){if status!=ReservationStatus::Active{return Err(bad("missing terminal"));}None}else{
        if status==ReservationStatus::Active{return Err(bad("active terminal"));}let t=&v["result"];
        keys(t,&["reason","remaining_ammunition","fired_ammunition","lost_ammunition","loss_event","terminal_hp","destroyed","repaired_hp","credits","xp","terminal_state"])?;
        let remaining=rows(&t["remaining_ammunition"])?;let fired=rows(&t["fired_ammunition"])?;let lost=rows(&t["lost_ammunition"])?;let loss_event=event(&t["loss_event"])?;
        for (((a,b),d),initial)in remaining.iter().zip(fired.iter()).zip(lost.iter()).zip(&f.base.ammunition){
            if [a,b,d].iter().any(|r|r.shell_compact_id!=initial.shell_compact_id)||a.count+b.count+d.count!=initial.count{return Err(bad("source per-stack conservation"));}}
        if number(t,"repaired_hp")?!=f.base.max_hp as u64||number(t,"credits")?!=0||number(t,"xp")?!=0{return Err(bad("free repair/rewards"));}
        let reason=text(t,"reason")?;
        let(hp,destroyed,state)=if status==ReservationStatus::AbortedRestart{
            if reason!="aborted_restart"||!t["terminal_hp"].is_null()||!t["destroyed"].is_null()||!t["terminal_state"].is_null()
                ||loss_event.is_some()||fired.iter().chain(&lost).any(|s|s.count!=0){return Err(bad("unknown restart/refund"));}(None,None,None)
        }else{
            let hp=i16::try_from(number(t,"terminal_hp")?).map_err(|_|bad("terminal HP width"))?;let destroyed=flag(t,"destroyed")?;
            let state=base::validate_terminal_json(&serde_json::to_string(&t["terminal_state"]).map_err(|_|bad("terminal JSON"))?,&f.base,hp)?;
            if destroyed!=(hp==0||!state.crew_active)||!["manual_leave","battle_failure","disconnect","cancelled","battle_finished"].contains(&reason){return Err(bad("terminal outcome"));}
            if let Some(e)=loss_event{
                let bay=state.raw["devices"].as_array().and_then(|a|a.iter().find(|r|r["extra_index"].as_u64()==Some(27))).ok_or_else(||bad("source ammo bay"))?;
                if lost.iter().all(|s|s.count==0)||remaining.iter().any(|s|s.count!=0)||hp!=0||number(bay,"health")?!=0||reason=="cancelled"
                    ||e.attacker_slot>=state.roster_size||e.target_slot>=state.roster_size||state.killer_slot!=Some(e.attacker_slot)
                    ||number(&state.raw["death"],"tick")?!=u64::from(e.tick){return Err(bad("detonation terminal/cause/loss"));}
            }else if lost.iter().any(|s|s.count!=0){return Err(bad("loss without detonation"));}
            if reason=="cancelled"&&(hp!=f.base.max_hp||loss_event.is_some()||fired.iter().chain(&lost).any(|s|s.count!=0)){return Err(bad("pristine queue cancellation"));}
            (Some(hp),Some(destroyed),Some(state))};
        Some(Terminal{reason:reason.into(),remaining,fired,lost,loss_event,terminal_hp:hp,destroyed,repaired_hp:f.base.max_hp,state})};
    Ok(Reservation{reservation_id:key.into(),run_id:run.into(),battle,frozen:f,status,result})}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Status{Ready,Admitted,Finished,Inspected,Rejected}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct Reply{pub status:Status,pub revision:u64,pub replayed:bool,pub code:Option<String>,pub reservation:Option<Reservation>}
fn rejection(s:&str)->bool{["STALE_REVISION","RUN_FENCED","RUN_NOT_OPEN","VEHICLE_RESERVED","UNKNOWN_VEHICLE","BATTLE_PROFILE_UNSUPPORTED","OWNER_ACCEPTANCE_REQUIRED",
    "INCOMPLETE_CREW","AMMUNITION_EMPTY","AMMUNITION_UNSUPPORTED","RESERVATION_TERMINAL","RESERVATION_MISMATCH","DUPLICATE_PAYLOAD_MISMATCH","INVALID_RESULT","RESULT_MISMATCH",
    "INVALID_TERMINAL_STATE","AMMO_LOSS_POLICY_REQUIRED","AMMO_LOSS_WRONG_ACTIVE_CONTRACT"].contains(&s)}
pub fn parse_reply(raw:&[u8],c:&Context,r:&Request)->io::Result<Reply>{encode_request(c,r)?;let v=base::bounded_json(raw,MAX_REPLY)?;
    keys(&v,&["version","contract","operation","account_id","native_database_id","command_key","run_id","source_revision","revision","replayed","status","code","reservation","legacy_reservation","policy_sha256"])?;
    if number(&v,"version")?!=VERSION||text(&v,"contract")?!=CONTRACT||text(&v,"operation")?!=r.operation()||text(&v,"account_id")?!=c.account_id
        ||number(&v,"native_database_id")?!=c.native_database_id as u64||text(&v,"command_key")?!=c.command_key||text(&v,"run_id")?!=c.run_id
        ||number(&v,"source_revision")?!=c.expected_revision||text(&v,"policy_sha256")?!=POLICY_SHA256||!v["legacy_reservation"].is_null(){return Err(bad("reply owner/context/policy"));}
    let revision=number(&v,"revision")?;if !(13..=i32::MAX as u64).contains(&revision){return Err(bad("reply revision"));}
    let status=match text(&v,"status")?{"ready"=>Status::Ready,"admitted"=>Status::Admitted,"finished"=>Status::Finished,"inspected"=>Status::Inspected,"rejected"=>Status::Rejected,_=>return Err(bad("reply status"))};
    let replayed=flag(&v,"replayed")?;let code=if v["code"].is_null(){None}else{let s=text(&v,"code")?;if !rejection(s){return Err(bad("rejection code"));}Some(s.into())};
    let receipt=if v["reservation"].is_null(){None}else{Some(reservation(&v["reservation"],&c.account_id)?)};
    if (status==Status::Rejected)!=code.is_some(){return Err(bad("status/code"));}
    if status==Status::Rejected{if replayed||receipt.is_some(){return Err(bad("rejection state"));}}
    else{
        if status!=match r{Request::RunOpen=>Status::Ready,Request::Inspect=>Status::Inspected,Request::Admit{..}=>Status::Admitted,Request::Finish{..}=>Status::Finished}{return Err(bad("operation status"));}
        match r{
            Request::Inspect=>if replayed||receipt.as_ref().is_some_and(|s|s.status!=ReservationStatus::Active){return Err(bad("inspect active only"));},
            Request::RunOpen=>{if revision!=c.expected_revision&&revision!=c.expected_revision+1{return Err(bad("run revision"));}
                if receipt.as_ref().is_some_and(|s|s.status!=ReservationStatus::AbortedRestart||s.run_id==c.run_id||revision==c.expected_revision){return Err(bad("run recovery"));}},
            Request::Admit{battle,native_inventory_id}|Request::Finish{battle,native_inventory_id,..}=>{
                let s=receipt.as_ref().ok_or_else(||bad("mutation receipt"))?;
                if revision!=c.expected_revision+1||s.run_id!=c.run_id||s.battle!=*battle||s.frozen.base.native_inventory_id!=*native_inventory_id{return Err(bad("mutation binding"));}
                if let Request::Admit{..}=r{if s.status!=ReservationStatus::Active||s.reservation_id!=c.command_key{return Err(bad("admit receipt"));}}
                if let Request::Finish{reservation_id,remaining_ammunition,fired_ammunition,lost_ammunition,loss_event,terminal_hp,terminal_state_json,reason,results_json,..}=r{
                    let t=s.result.as_ref().ok_or_else(||bad("finish terminal"))?;
                    if s.status!=ReservationStatus::Finished||s.reservation_id!=*reservation_id||t.remaining!=*remaining_ammunition||t.fired!=*fired_ammunition||t.lost!=*lost_ammunition
                        ||t.loss_event!=*loss_event||t.terminal_hp!=Some(*terminal_hp)||t.reason!=reason.name()||t.state.as_ref().map(|s|&s.raw)!=Some(&base::bounded_json(terminal_state_json.as_bytes(),8192)?){return Err(bad("finish exact terminal binding"));}
                    if let Some(raw)=results_json{let stats=Results::from_json_p06t(raw)?;let own=stats.participants.iter().find(|p|p.account_dbid==c.native_database_id).ok_or_else(||bad("results owner"))?;
                        let state=t.state.as_ref().ok_or_else(||bad("results terminal"))?;
                        if own.shots!=t.fired.iter().map(|s|s.count).sum::<u16>()||usize::from(state.roster_size)!=stats.participants.len()||own.health!=*terminal_hp
                            ||own.death_reason!=state.death_reason||own.killer_id!=state.killer_slot.map_or(0,|i|stats.participants[i as usize].vehicle_id){return Err(bad("results fired/journal"));}
                        if let Some(e)=t.loss_event{if stats.participants[e.target_slot as usize].account_dbid!=c.native_database_id
                            ||u32::from(stats.participants.iter().map(|p|p.shots).sum::<u16>())<e.shot{return Err(bad("results detonation target/shot"));}}
                    }
                }
            }
        }
    }
    Ok(Reply{status,revision,replayed,code,reservation:receipt})}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum ResultsRequest{Query{arena:u64},Ack{arena:u64}}
impl ResultsRequest{pub fn operation(self)->&'static str{match self{Self::Query{..}=>"query",Self::Ack{..}=>"ack"}}pub fn arena(self)->u64{match self{Self::Query{arena}|Self::Ack{arena}=>arena}}}
pub fn encode_results_request(c:&Context,r:ResultsRequest)->io::Result<Vec<u8>>{context(c)?;if r.arena()==0||r.arena()>i64::MAX as u64{return Err(bad("result arena"));}
    serde_json::to_vec(&serde_json::json!({"version":VERSION,"contract":CONTRACT,"operation":r.operation(),"account_id":c.account_id,
        "native_database_id":c.native_database_id,"command_key":c.command_key,"arena_id":r.arena().to_string()})).map_err(|_|bad("result request"))}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum RecordContract{MixedV2,LossV1}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum ResultsStatus{Found,Missing,Acked,Rejected}
#[derive(Clone,Debug,PartialEq)]pub struct ResultsReply{pub status:ResultsStatus,pub acked:bool,pub replayed:bool,pub code:Option<String>,pub results:Option<Results>,pub results_json:Option<String>,pub record_contract:Option<RecordContract>}
pub fn parse_results_reply(raw:&[u8],c:&Context,r:ResultsRequest)->io::Result<ResultsReply>{encode_results_request(c,r)?;let v=base::bounded_json(raw,MAX_RESULT_REQUEST)?;
    keys(&v,&["version","contract","operation","account_id","native_database_id","command_key","arena_id","status","acked","results_json","replayed","code","policy_sha256","record_contract"])?;
    if number(&v,"version")?!=VERSION||text(&v,"contract")?!=CONTRACT||text(&v,"operation")?!=r.operation()||text(&v,"account_id")?!=c.account_id
        ||number(&v,"native_database_id")?!=c.native_database_id as u64||text(&v,"command_key")?!=c.command_key||text(&v,"arena_id")?!=r.arena().to_string()||text(&v,"policy_sha256")?!=POLICY_SHA256{return Err(bad("result reply binding"));}
    let status=match text(&v,"status")?{"found"=>ResultsStatus::Found,"missing"=>ResultsStatus::Missing,"acked"=>ResultsStatus::Acked,"rejected"=>ResultsStatus::Rejected,_=>return Err(bad("result status"))};
    let acked=flag(&v,"acked")?;let replayed=flag(&v,"replayed")?;
    let code=if v["code"].is_null(){None}else{let s=text(&v,"code")?;if !["RESULT_NOT_READY","RESULT_MISMATCH","DUPLICATE_PAYLOAD_MISMATCH","AMMO_LOSS_POLICY_REQUIRED"].contains(&s){return Err(bad("result code"));}Some(s.into())};
    let contract=if v["record_contract"].is_null(){None}else{Some(match text(&v,"record_contract")?{"mixed-v2"=>RecordContract::MixedV2,"loss-v1"=>RecordContract::LossV1,_=>return Err(bad("record contract"))})};
    let result_json=if v["results_json"].is_null(){None}else{Some(text(&v,"results_json")?.to_owned())};
    let result=result_json.as_ref().map(|raw|Results::from_json_p06t(raw)).transpose()?;
    if (status==ResultsStatus::Rejected)!=code.is_some()||matches!(status,ResultsStatus::Missing|ResultsStatus::Rejected)&&(acked||replayed||result.is_some()||contract.is_some())
        ||matches!(status,ResultsStatus::Found|ResultsStatus::Acked)&&(result.is_none()||contract.is_none())||status==ResultsStatus::Found&&r.operation()!="query"
        ||status==ResultsStatus::Acked&&(r.operation()!="ack"||!acked)||replayed&&status!=ResultsStatus::Acked{return Err(bad("result status/state"));}
    if let Some(result)=&result{if result.arena_id!=r.arena()||!result.participants.iter().any(|p|p.account_dbid==c.native_database_id){return Err(bad("result arena/owner"));}}
    Ok(ResultsReply{status,acked,replayed,code,results:result,results_json:result_json,record_contract:contract})}

#[cfg(test)]
mod tests{
    use super::*;
    const ACTUAL:&[u8]=include_bytes!("../../../../tests/fixtures/p06t-ammo-loss-writer-vectors.json");
    fn fixture()->Value{assert_eq!(format!("{:x}",Sha256::digest(ACTUAL)),"251c60f587d14d916e5381567d8af2982b26f0f98335af8464b75bbf1cc1f154");serde_json::from_slice(ACTUAL).unwrap()}
    fn ctx(v:&Value)->Context{Context{account_id:text(v,"account_id").unwrap().into(),native_database_id:number(v,"native_database_id").unwrap()as i32,
        command_key:text(v,"command_key").unwrap().into(),expected_revision:v["expected_revision"].as_u64().unwrap_or(13),
        run_id:v["run_id"].as_str().unwrap_or("788fa1bf-8a21-4bdb-84de-a63310e390a3").into()}}
    fn request(v:&Value)->Request{let battle=||text(v,"battle_id").unwrap().rsplit(':').next().unwrap().parse().unwrap();
        let native=||number(v,"native_inventory_id").unwrap()as u32;
        match text(v,"operation").unwrap(){"run_open"=>Request::RunOpen,"inspect"=>Request::Inspect,
            "admit"=>Request::Admit{battle:battle(),native_inventory_id:native()},"finish"=>Request::Finish{battle:battle(),native_inventory_id:native(),
                reservation_id:text(v,"reservation_id").unwrap().into(),remaining_ammunition:rows(&v["remaining_ammunition"]).unwrap(),
                fired_ammunition:rows(&v["fired_ammunition"]).unwrap(),lost_ammunition:rows(&v["lost_ammunition"]).unwrap(),loss_event:event(&v["loss_event"]).unwrap(),
                terminal_hp:number(v,"terminal_hp").unwrap()as i16,terminal_state_json:text(v,"terminal_state_json").unwrap().into(),
                reason:match text(v,"reason").unwrap(){"battle_finished"=>FinishReason::BattleFinished,"manual_leave"=>FinishReason::ManualLeave,
                    "battle_failure"=>FinishReason::BattleFailure,"disconnect"=>FinishReason::Disconnect,"cancelled"=>FinishReason::Cancelled,_=>panic!("fixture reason")},
                results_json:v["results_json"].as_str().map(str::to_owned)},_=>panic!("battle fixture operation")}}
    fn finish_vector()->Value{fixture()["vectors"].as_array().unwrap().iter().find(|v|v["request"]["operation"]=="finish").unwrap().clone()}
    #[test]fn p06t_loss_actual_sqlite_vectors_encode_and_parse_all_nine_exact_contracts(){
        let data=fixture();let mut seen=0;
        for row in data["vectors"].as_array().unwrap(){let v=&row["request"];let c=ctx(v);let raw=serde_json::to_vec(&row["response"]).unwrap();
            if matches!(text(v,"operation").unwrap(),"query"|"ack"){
                let arena=text(v,"arena_id").unwrap().parse().unwrap();let r=if v["operation"]=="query"{ResultsRequest::Query{arena}}else{ResultsRequest::Ack{arena}};
                assert_eq!(serde_json::from_slice::<Value>(&encode_results_request(&c,r).unwrap()).unwrap(),*v);
                let reply=parse_results_reply(&raw,&c,r).unwrap();assert_eq!(reply.record_contract,Some(RecordContract::LossV1));
                assert_eq!(reply.results.unwrap().participants[0].shots,3);
            }else{let r=request(v);assert_eq!(serde_json::from_slice::<Value>(&encode_request(&c,&r).unwrap()).unwrap(),*v);
                let reply=parse_reply(&raw,&c,&r).unwrap();if let Some(s)=reply.reservation{s.frozen.validate_owned(&c.account_id).unwrap();}}
            seen+=1;
        }assert_eq!(seen,9);
    }
    #[test]fn res30_loss_event_slots_and_shots_of_a_thirty_actor_battle(){
        use crate::gateway091::shared::model::{MAX_BATTLE_SHOTS,MAX_DAMAGE_EVENTS};
        let good=LossEvent{shot:MAX_BATTLE_SHOTS as u32,attacker_slot:29,target_slot:0,tick:1200,device_sequence:MAX_DAMAGE_EVENTS as u32};
        good.validate().unwrap();assert_eq!(event(&good.value()).unwrap(),Some(good));
        LossEvent{attacker_slot:6,target_slot:7,shot:961,device_sequence:15361,..good}.validate().unwrap();
        for bad in [LossEvent{attacker_slot:30,..good},LossEvent{target_slot:30,..good},LossEvent{target_slot:29,..good},
            LossEvent{shot:MAX_BATTLE_SHOTS as u32+1,..good},LossEvent{device_sequence:MAX_DAMAGE_EVENTS as u32+1,..good}]{assert!(bad.validate().is_err(),"{bad:?}");}
    }
    #[test]fn p06t_loss_removed_ammunition_never_substitutes_for_actual_shots(){
        let v=finish_vector();let mut poisoned=v["request"].clone();let mut stats:Value=serde_json::from_str(text(&poisoned,"results_json").unwrap()).unwrap();
        stats["participants"][0]["shots"]=14.into();poisoned["results_json"]=serde_json::to_string(&stats).unwrap().into();
        assert!(parse_reply(&serde_json::to_vec(&v["response"]).unwrap(),&ctx(&poisoned),&request(&poisoned)).is_err());
        let reply=parse_reply(&serde_json::to_vec(&v["response"]).unwrap(),&ctx(&v["request"]),&request(&v["request"])).unwrap();
        let t=reply.reservation.unwrap().result.unwrap();assert_eq!(t.fired.map(|s|s.count),[0,1,2]);assert_eq!(t.lost.map(|s|s.count),[0,3,8]);
    }
    #[test]fn p06t_loss_frozen_wrapper_cannot_be_retagged_or_accepted_as_legacy_receipt(){
        let v=finish_vector();let f=&v["response"]["reservation"]["frozen"];let account=text(&v["request"],"account_id").unwrap();
        let expected=text(&v["response"]["reservation"],"frozen_sha256").unwrap();parse_frozen(f,account,expected).unwrap();
        base::parse_frozen(&f["loadout"],account,text(f,"loadout_sha256").unwrap()).unwrap();
        assert!(base::parse_frozen(f,account,expected).is_err());let mut bad=f.clone();bad["policy_sha256"]=base::POLICY_SHA256.into();
        assert!(parse_frozen(&bad,account,&digest(&bad).unwrap()).is_err());
        bad=f.clone();bad["loadout"]["ammunition"][1]["count"]=5.into();assert!(parse_frozen(&bad,account,&digest(&bad).unwrap()).is_err());
    }
    #[test]fn p06t_loss_terminal_poison_source_order_cause_empty_loss_and_hp_refuse(){
        let v=finish_vector();let c=ctx(&v["request"]);let r=request(&v["request"]);
        for case in 0..7{let mut bad=v["response"].clone();let t=&mut bad["reservation"]["result"];
            match case{0=>t["lost_ammunition"][1]["count"]=2.into(),1=>t["remaining_ammunition"][2]["count"]=1.into(),2=>t["loss_event"]=Value::Null,
                3=>t["loss_event"]["target_slot"]=1.into(),4=>t["loss_event"]["tick"]=1251.into(),5=>t["terminal_hp"]=18.into(),
                _=>{t["fired_ammunition"]=rows_value(&[Remaining{shell_compact_id:2570,count:0},Remaining{shell_compact_id:2826,count:4},Remaining{shell_compact_id:3082,count:10}]);
                    t["lost_ammunition"]=rows_value(&[Remaining{shell_compact_id:2570,count:0},Remaining{shell_compact_id:2826,count:0},Remaining{shell_compact_id:3082,count:0}]);}}
            assert!(parse_reply(&serde_json::to_vec(&bad).unwrap(),&c,&r).is_err(),"case{case}");}
    }
    #[test]fn p06t_loss_result_cache_is_exact_arena_owner_and_record_contract(){
        let data=fixture();let v=data["vectors"].as_array().unwrap().iter().find(|v|v["request"]["operation"]=="query").unwrap();
        let c=ctx(&v["request"]);let r=ResultsRequest::Query{arena:text(&v["request"],"arena_id").unwrap().parse().unwrap()};
        for key in ["contract","policy_sha256","record_contract"]{let mut bad=v["response"].clone();bad[key]="foreign".into();assert!(parse_results_reply(&serde_json::to_vec(&bad).unwrap(),&c,r).is_err());}
        let mut foreign=c.clone();foreign.native_database_id+=10;assert!(parse_results_reply(&serde_json::to_vec(&v["response"]).unwrap(),&foreign,r).is_err());
    }
}
