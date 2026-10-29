//! Candidate typed API5; no active admission/store/HTTP route is enabled here.
//! The inner actual v4 source parser remains the sole loss-loadout validator.
use std::io;
use serde_json::Value;
use sha2::{Digest, Sha256};
use crate::{profile13_loss091 as loss, profile13_v2091 as mixed};

pub const VERSION: u64 = 5;
pub const CONTRACT: &str = "p08b-owner-battle-hold.v1";
pub const POLICY_SHA256: &str = "98cdc5d657e4cdf30225c26913f2c70a89865de9ae2bb97704fa4b623efd806e";
pub const MAX_FROZEN: usize = 8192;

fn bad(why: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, format!("owner battle hold5: {why}"))
}
fn sha(value: &Value) -> io::Result<String> {
    Ok(format!("{:x}", Sha256::digest(serde_json::to_vec(value).map_err(|_| bad("canonical JSON"))?)))
}
fn hash(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FrozenHold {
    loss: loss::FrozenLoss,
    value: Value,
    sha256: String,
}
// BW-01 wire codec (tools/bw01_wire_gen.py): FrozenHold
impl crate::bw_wire::Wire for FrozenHold {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{loss,value,sha256}=self;W::put(loss,bw_o);W::put(value,bw_o);W::put(sha256,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{loss:W::get(bw_i)?,value:W::get(bw_i)?,sha256:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl FrozenHold {
    pub fn loss(&self) -> &loss::FrozenLoss { &self.loss }
    pub fn sha256(&self) -> &str { &self.sha256 }
    pub fn value(&self) -> &Value { &self.value }
    pub fn validate_owned(&self, account: &str) -> io::Result<()> {
        if parse_frozen(&self.value, account, &self.sha256)? != *self {
            return Err(bad("changed typed frozen envelope"));
        }
        Ok(())
    }
}

/// Validates an envelope, not a reservation or selected-ready authority.
/// Only an actual writer-confirmed v5 receipt may later supply this to World.
pub fn parse_frozen(value: &Value, account: &str, expected_sha: &str) -> io::Result<FrozenHold> {
    let object = value.as_object().ok_or_else(|| bad("frozen object"))?;
    let keys = ["hold_policy_sha256", "loss_frozen", "loss_frozen_sha256"];
    if object.len() != keys.len() || keys.iter().any(|k| !object.contains_key(*k)) {
        return Err(bad("exact frozen fields"));
    }
    if !hash(expected_sha) || value["hold_policy_sha256"].as_str() != Some(POLICY_SHA256)
        || serde_json::to_vec(value).map_err(|_| bad("frozen JSON"))?.len() > MAX_FROZEN
        || sha(value)? != expected_sha {
        return Err(bad("hold policy/hash/size"));
    }
    let inner_sha = value["loss_frozen_sha256"].as_str().filter(|v| hash(v))
        .ok_or_else(|| bad("inner loss SHA"))?;
    let source = loss::parse_frozen(&value["loss_frozen"], account, inner_sha)?;
    Ok(FrozenHold { loss: source, value: value.clone(), sha256: expected_sha.into() })
}

/// Raw input always passes the existing bounded, duplicate-rejecting parser.
pub fn parse_raw(raw: &[u8], account: &str, expected_sha: &str) -> io::Result<FrozenHold> {
    parse_frozen(&mixed::bounded_json(raw, MAX_FROZEN)?, account, expected_sha)
}

/// Source-candidate authoring helper only. This does NOT authorize admission.
#[cfg(test)]
pub fn wrap_source_candidate(inner: &Value, account: &str) -> io::Result<FrozenHold> {
    let inner_sha = sha(inner)?;
    loss::parse_frozen(inner, account, &inner_sha)?;
    let value = serde_json::json!({"hold_policy_sha256": POLICY_SHA256,
        "loss_frozen": inner, "loss_frozen_sha256": inner_sha});
    parse_frozen(&value, account, &sha(&value)?)
}

pub use crate::battle091::profile13::{Context, FinishReason};
pub use mixed::Remaining;
pub const MAX_REPLY: usize = 65536;
fn keys(v:&Value,names:&[&str])->io::Result<()> {let o=v.as_object().ok_or_else(||bad("object"))?;
    if o.len()!=names.len()||names.iter().any(|k|!o.contains_key(*k)){return Err(bad("exact fields"));}Ok(())}
fn text<'a>(v:&'a Value,k:&str)->io::Result<&'a str>{v[k].as_str().ok_or_else(||bad("text"))}
fn num(v:&Value,k:&str)->io::Result<u64>{v[k].as_u64().ok_or_else(||bad("unsigned integer"))}
fn uuid(s:&str)->bool{s.len()==36&&s.bytes().enumerate().all(|(i,c)|if[8,13,18,23].contains(&i){c==b'-'}else{c.is_ascii_digit()||(b'a'..=b'f').contains(&c)})&&matches!(s.as_bytes()[14],b'1'..=b'5')}
fn identifier(s:&str)->bool{!s.is_empty()&&s.len()<=96&&s.bytes().all(|c|c.is_ascii_alphanumeric()||b"_:-".contains(&c))}
fn context(c:&Context)->io::Result<()>{if !uuid(&c.account_id)||!uuid(&c.run_id)||c.native_database_id<=0||!identifier(&c.command_key)||c.expected_revision>=i32::MAX as u64{return Err(bad("context"));}Ok(())}
fn clock(tick:u32)->bool{(1000..=37000).contains(&tick)}
fn rows_value(rows:&[Remaining;3])->Value{serde_json::json!(rows.iter().map(|r|serde_json::json!({"shell_compact_id":r.shell_compact_id,"count":r.count})).collect::<Vec<_>>())}
fn rows(v:&Value)->io::Result<[Remaining;3]>{let a=v.as_array().ok_or_else(||bad("stacks"))?;if a.len()!=3{return Err(bad("three stacks"));}
    let mut out=Vec::new();for row in a{keys(row,&["shell_compact_id","count"])?;let id=u16::try_from(num(row,"shell_compact_id")?).map_err(|_|bad("shell width"))?;
        let count=u16::try_from(num(row,"count")?).map_err(|_|bad("count width"))?;
        if id==0||count>160||out.iter().any(|r:&Remaining|r.shell_compact_id==id){return Err(bad("stack/source bounds"));}out.push(Remaining{shell_compact_id:id,count});}
    out.try_into().map_err(|_|bad("three stacks"))}
fn event_value(e:Option<loss::LossEvent>)->Value{e.map_or(Value::Null,|e|serde_json::json!({"shot":e.shot,"attacker_slot":e.attacker_slot,"target_slot":e.target_slot,"tick":e.tick,"device_sequence":e.device_sequence}))}
fn event(v:&Value)->io::Result<Option<loss::LossEvent>>{if v.is_null(){return Ok(None);}keys(v,&["shot","attacker_slot","target_slot","tick","device_sequence"])?;
    let e=loss::LossEvent{shot:u32::try_from(num(v,"shot")?).map_err(|_|bad("shot width"))?,attacker_slot:u8::try_from(num(v,"attacker_slot")?).map_err(|_|bad("attacker width"))?,
        target_slot:u8::try_from(num(v,"target_slot")?).map_err(|_|bad("target width"))?,tick:u32::try_from(num(v,"tick")?).map_err(|_|bad("tick width"))?,device_sequence:u32::try_from(num(v,"device_sequence")?).map_err(|_|bad("device width"))?};
    if !(1..=960).contains(&e.shot)||e.attacker_slot>=6||e.target_slot>=6||e.attacker_slot==e.target_slot||!clock(e.tick)||!(1..=15360).contains(&e.device_sequence){return Err(bad("loss event bounds"));}Ok(Some(e))}

#[derive(Clone,Debug,PartialEq,Eq)]
pub struct SourceLink{pub account_id:String,pub native_database_id:i32,pub run_id:String,pub battle:u64,pub reservation_id:String,
    pub native_inventory_id:u32,pub vehicle_inventory_id:String,pub frozen_sha256:String,pub source_session_id:u32,pub actor_slot:u8,pub team:u8,pub vehicle_kind:String}
impl SourceLink{
    pub fn value(&self)->Value{serde_json::json!({"account_id":self.account_id,"native_database_id":self.native_database_id,"run_id":self.run_id,"battle_id":format!("{}:{}",self.run_id,self.battle),
        "reservation_id":self.reservation_id,"native_inventory_id":self.native_inventory_id,"vehicle_inventory_id":self.vehicle_inventory_id,"frozen_sha256":self.frozen_sha256,
        "source_session_id":self.source_session_id,"actor_slot":self.actor_slot,"team":self.team,"vehicle_kind":self.vehicle_kind})}
    pub fn validate(&self)->io::Result<()>{if !uuid(&self.account_id)||!uuid(&self.run_id)||self.battle==0||self.native_database_id<=0||self.native_inventory_id==0
        ||!identifier(&self.reservation_id)||!identifier(&self.vehicle_inventory_id)||!self.vehicle_inventory_id.starts_with(&format!("{}:",self.account_id))
        ||!hash(&self.frozen_sha256)||self.source_session_id==0||self.actor_slot>=6||!(1..=2).contains(&self.team)||!matches!(self.vehicle_kind.as_str(),"ms1"|"is7"){return Err(bad("source link bounds"));}Ok(())}
    pub fn validate_reservation(&self,r:&Reservation,account:&str,database:i32)->io::Result<()>{self.validate()?;
        if self.account_id!=account||self.native_database_id!=database||self.run_id!=r.run_id||self.battle!=r.battle||self.reservation_id!=r.reservation_id
            ||self.native_inventory_id!=r.frozen.loss().base.native_inventory_id||self.vehicle_inventory_id!=r.frozen.loss().base.vehicle_inventory_id
            ||self.frozen_sha256!=r.frozen.sha256()||self.vehicle_kind!=r.frozen.loss().base.kind.label(){return Err(bad("link actual reservation identity"));}Ok(())}
}
fn link(v:&Value)->io::Result<Option<SourceLink>>{if v.is_null(){return Ok(None);}keys(v,&["account_id","native_database_id","run_id","battle_id","reservation_id","native_inventory_id","vehicle_inventory_id","frozen_sha256","source_session_id","actor_slot","team","vehicle_kind"])?;
    let run=text(v,"run_id")?;let battle=battle(text(v,"battle_id")?,run)?;
    let out=SourceLink{account_id:text(v,"account_id")?.into(),native_database_id:i32::try_from(num(v,"native_database_id")?).map_err(|_|bad("database width"))?,run_id:run.into(),battle,
        reservation_id:text(v,"reservation_id")?.into(),native_inventory_id:u32::try_from(num(v,"native_inventory_id")?).map_err(|_|bad("inventory width"))?,vehicle_inventory_id:text(v,"vehicle_inventory_id")?.into(),
        frozen_sha256:text(v,"frozen_sha256")?.into(),source_session_id:u32::try_from(num(v,"source_session_id")?).map_err(|_|bad("session width"))?,actor_slot:u8::try_from(num(v,"actor_slot")?).map_err(|_|bad("slot width"))?,
        team:u8::try_from(num(v,"team")?).map_err(|_|bad("team width"))?,vehicle_kind:text(v,"vehicle_kind")?.into()};out.validate()?;Ok(Some(out))}
fn battle(raw:&str,run:&str)->io::Result<u64>{let n=raw.strip_prefix(&format!("{run}:")).ok_or_else(||bad("battle run"))?.parse::<u64>().map_err(|_|bad("battle number"))?;
    if n==0||raw!=format!("{run}:{n}"){return Err(bad("canonical battle"));}Ok(n)}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum DepartureReason{ManualLeave,Disconnect}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub struct Departure{pub reason:DepartureReason,pub tick:u32}
impl Departure{pub fn value(self)->Value{serde_json::json!({"reason":match self.reason{DepartureReason::ManualLeave=>"manual_leave",DepartureReason::Disconnect=>"disconnect"},"tick":self.tick})}}
fn departure(v:&Value)->io::Result<Option<Departure>>{if v.is_null(){return Ok(None);}keys(v,&["reason","tick"])?;let tick=u32::try_from(num(v,"tick")?).map_err(|_|bad("departure tick width"))?;
    if !clock(tick){return Err(bad("departure tick"));}Ok(Some(Departure{tick,reason:match text(v,"reason")?{"manual_leave"=>DepartureReason::ManualLeave,"disconnect"=>DepartureReason::Disconnect,_=>return Err(bad("departure reason"))}}))}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Finalization{Outcome{tick:u32},ContainedFailure{tick:u32},PristineCancel,AbortedRestart}
impl Finalization{pub fn value(self)->Value{match self{Self::Outcome{tick}=>serde_json::json!({"kind":"outcome","tick":tick}),Self::ContainedFailure{tick}=>serde_json::json!({"kind":"contained_failure","tick":tick}),Self::PristineCancel=>serde_json::json!({"kind":"pristine_cancel"}),Self::AbortedRestart=>serde_json::json!({"kind":"aborted_restart"})}}
    pub fn tick(self)->Option<u32>{match self{Self::Outcome{tick}|Self::ContainedFailure{tick}=>Some(tick),_=>None}}}
fn finalization(v:&Value)->io::Result<Finalization>{match text(v,"kind")?{"outcome"|"contained_failure"=>{keys(v,&["kind","tick"])?;let tick=u32::try_from(num(v,"tick")?).map_err(|_|bad("final tick width"))?;
    if !clock(tick){return Err(bad("final tick"));}Ok(if v["kind"]=="outcome"{Finalization::Outcome{tick}}else{Finalization::ContainedFailure{tick}})},"pristine_cancel"=>{keys(v,&["kind"])?;Ok(Finalization::PristineCancel)},"aborted_restart"=>{keys(v,&["kind"])?;Ok(Finalization::AbortedRestart)},_=>Err(bad("finalization kind"))}}

#[derive(Clone,Debug,PartialEq,Eq)]pub struct Finish{
    pub battle:u64,pub native_inventory_id:u32,pub reservation_id:String,pub remaining:[Remaining;3],pub fired:[Remaining;3],pub lost:[Remaining;3],pub loss_event:Option<loss::LossEvent>,
    pub terminal_hp:i16,pub terminal_state_json:String,pub reason:FinishReason,pub results_json:Option<String>,pub source_link:Option<SourceLink>,pub departure:Option<Departure>,pub finalization:Finalization,
}
#[derive(Clone,Debug,PartialEq,Eq)]pub enum Request{RunOpen,Inspect,Admit{battle:u64,native_inventory_id:u32},Finish(Finish)}
impl Request{pub fn operation(&self)->&'static str{match self{Self::RunOpen=>"run_open",Self::Inspect=>"inspect",Self::Admit{..}=>"admit",Self::Finish(_)=>"finish"}}
    pub fn finished_battle(&self)->Option<u64>{if let Self::Finish(f)=self{Some(f.battle)}else{None}}}
impl Finish{
    fn validate_shape(&self,c:&Context)->io::Result<()>{if self.battle==0||self.native_inventory_id==0||!identifier(&self.reservation_id){return Err(bad("finish identifiers"));}
        // Reuse old loss scalar/source-terminal syntax only; never create or
        // reinterpret an old Reservation/Reply and never route this request4.
        loss::encode_request(c,&loss::Request::Finish{battle:self.battle,native_inventory_id:self.native_inventory_id,reservation_id:self.reservation_id.clone(),
            remaining_ammunition:self.remaining,fired_ammunition:self.fired,lost_ammunition:self.lost,loss_event:self.loss_event,terminal_hp:self.terminal_hp,
            terminal_state_json:self.terminal_state_json.clone(),reason:self.reason,results_json:self.results_json.clone()})?;
        match self.finalization{
            Finalization::Outcome{tick}|Finalization::ContainedFailure{tick}=>{if !clock(tick)||self.departure.is_some_and(|d|!clock(d.tick)||d.tick>tick){return Err(bad("final/departure clock"));}
                let l=self.source_link.as_ref().ok_or_else(||bad("attached final lacks source link"))?;l.validate()?;
                if l.account_id!=c.account_id||l.native_database_id!=c.native_database_id||l.run_id!=c.run_id||l.battle!=self.battle||l.reservation_id!=self.reservation_id||l.native_inventory_id!=self.native_inventory_id{return Err(bad("finish link/context"));}
                if self.loss_event.is_some_and(|e|e.target_slot!=l.actor_slot||e.tick>tick){return Err(bad("loss cause versus original linked target/final"));}
                if matches!(self.finalization,Finalization::Outcome{..}){if self.reason!=FinishReason::BattleFinished{return Err(bad("Outcome final reason"));}
                    let stats=crate::gateway091::shared::lifecycle_wire::Results::from_json_p06t(self.results_json.as_deref().ok_or_else(||bad("Outcome result"))?)?;
                    if stats.interaction_details.is_none(){return Err(bad("new5 Outcome requires Results8"));}
                }else if self.reason!=FinishReason::BattleFailure||self.results_json.is_some(){return Err(bad("failure is not Outcome"));}
            },Finalization::PristineCancel=>{if self.reason!=FinishReason::Cancelled||self.source_link.is_some()||self.departure.is_some()||self.results_json.is_some(){return Err(bad("pristine metadata"));}},
            Finalization::AbortedRestart=>return Err(bad("restart is generated only by run_open")),
        }Ok(())}
    pub fn validate_against(&self,c:&Context,r:&Reservation)->io::Result<()>{self.validate_shape(c)?;let f=&r.frozen.loss().base;
        if r.status!=ReservationStatus::Active||r.result.is_some()||r.run_id!=c.run_id||r.battle!=self.battle||r.reservation_id!=self.reservation_id||f.native_inventory_id!=self.native_inventory_id{return Err(bad("finish active5 receipt"));}
        r.frozen.validate_owned(&c.account_id)?;for i in 0..3{let a=&f.ammunition[i];if [self.remaining[i],self.fired[i],self.lost[i]].iter().any(|r|r.shell_compact_id!=a.shell_compact_id)
            ||u32::from(self.remaining[i].count)+u32::from(self.fired[i].count)+u32::from(self.lost[i].count)!=u32::from(a.count){return Err(bad("finish stack conservation"));}}
        let state=mixed::validate_terminal_json(&self.terminal_state_json,f,self.terminal_hp)?;
        if self.finalization.tick().is_some_and(|tick|state.raw["death"]["tick"].as_u64().is_none_or(|death|death>u64::from(tick))){return Err(bad("terminal death after final source clock"));}
        if let Some(l)=&self.source_link{l.validate_reservation(r,&c.account_id,c.native_database_id)?;if u64::from(l.actor_slot)>=state.raw["roster_size"].as_u64().ok_or_else(||bad("terminal roster"))?{return Err(bad("source slot/terminal roster"));}}
        if let Some(e)=self.loss_event{let bay=state.raw["devices"].as_array().and_then(|a|a.iter().find(|d|d["extra_index"]==27));
            if self.terminal_hp!=0||self.remaining.iter().any(|r|r.count!=0)||self.lost.iter().all(|r|r.count==0)||bay.is_none_or(|d|d["health"]!=0)||state.killer_slot!=Some(e.attacker_slot)
                ||state.raw["death"]["tick"].as_u64()!=Some(u64::from(e.tick)){return Err(bad("loss5 final device/death/cause"));}
        }else if self.lost.iter().any(|r|r.count!=0){return Err(bad("loss without event"));}
        if self.finalization==Finalization::PristineCancel&&(self.terminal_hp!=f.max_hp||self.fired.iter().chain(&self.lost).any(|r|r.count!=0)||self.loss_event.is_some()
            ||state.raw!=mixed::bounded_json(crate::gateway091::shared::model::World::cancelled_terminal_state(f)?.as_bytes(),8192)?){return Err(bad("not a pristine cancellation"));}
        if let Some(raw)=&self.results_json{let stats=crate::gateway091::shared::lifecycle_wire::Results::from_json_p06t(raw)?;let l=self.source_link.as_ref().ok_or_else(||bad("result source link"))?;
            let p=stats.participants.get(l.actor_slot as usize).ok_or_else(||bad("result original slot"))?;
            if stats.arena_id!=self.battle||stats.participants.len()!=usize::from(state.roster_size)||p.account_dbid!=c.native_database_id||p.vehicle_id!=crate::gateway091::shared::wire::vehicle_id(l.actor_slot as usize)?||p.team!=l.team||p.type_compact_descr!=f.kind.vehicle_compact_id()
                ||p.health!=self.terminal_hp||p.premature_leave!=self.departure.is_some()
                ||u32::from(p.shots)!=self.fired.iter().map(|r|u32::from(r.count)).sum::<u32>()||p.death_reason!=state.raw["death"]["reason"].as_i64().ok_or_else(||bad("death reason"))? as i8{
                return Err(bad("actual result/source terminal mismatch"));}
            if p.killer_id!=state.killer_slot.map_or(Ok(0),|slot|stats.participants.get(slot as usize).map(|p|p.vehicle_id).ok_or_else(||bad("killer source slot")))?
                ||self.loss_event.is_some_and(|e|stats.participants.iter().map(|p|u32::from(p.shots)).sum::<u32>()<e.shot){return Err(bad("actual result death/cause"));}}
        Ok(())}
}
pub fn encode_request(c:&Context,r:&Request)->io::Result<Vec<u8>>{context(c)?;if !matches!(r,Request::Inspect)&&c.expected_revision<13{return Err(bad("mutation revision"));}
    let mut v=serde_json::json!({"version":VERSION,"contract":CONTRACT,"operation":r.operation(),"account_id":c.account_id,"native_database_id":c.native_database_id,"command_key":c.command_key,"expected_revision":c.expected_revision,"run_id":c.run_id});
    match r{Request::Admit{battle,native_inventory_id}=>{if *battle==0||*native_inventory_id==0{return Err(bad("admit battle/vehicle"));}v["battle_id"]=format!("{}:{battle}",c.run_id).into();v["native_inventory_id"]=(*native_inventory_id).into();},Request::Finish(f)=>{
        f.validate_shape(c)?;v["battle_id"]=format!("{}:{}",c.run_id,f.battle).into();v["native_inventory_id"]=f.native_inventory_id.into();v["reservation_id"]=f.reservation_id.clone().into();
        v["remaining_ammunition"]=rows_value(&f.remaining);v["fired_ammunition"]=rows_value(&f.fired);v["lost_ammunition"]=rows_value(&f.lost);v["loss_event"]=event_value(f.loss_event);
        v["terminal_hp"]=f.terminal_hp.into();v["terminal_state_json"]=serde_json::to_string(&mixed::bounded_json(f.terminal_state_json.as_bytes(),8192)?).map_err(|_|bad("terminal JSON"))?.into();v["reason"]=f.reason.name().into();
        v["source_link"]=f.source_link.as_ref().map_or(Value::Null,SourceLink::value);v["departure"]=f.departure.map_or(Value::Null,Departure::value);v["finalization"]=f.finalization.value();
        if let Some(raw)=&f.results_json{v["results_json"]=serde_json::to_string(&mixed::bounded_json(raw.as_bytes(),32768)?).map_err(|_|bad("results JSON"))?.into();}},_=>{}}
    let raw=serde_json::to_vec(&v).map_err(|_|bad("request JSON"))?;if raw.len()>if matches!(r,Request::Finish(_)){65536}else{2048}{return Err(bad("request bound"));}Ok(raw)}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum ReservationStatus{Active,Finished,AbortedRestart}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct Terminal{pub reason:String,pub remaining:[Remaining;3],pub fired:[Remaining;3],pub lost:[Remaining;3],pub loss_event:Option<loss::LossEvent>,pub hp:Option<i16>,
    pub destroyed:Option<bool>,pub repaired_hp:i16,pub state:Option<mixed::TerminalState>,pub source_link:Option<SourceLink>,pub departure:Option<Departure>,pub finalization:Finalization}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct Reservation{pub reservation_id:String,pub run_id:String,pub battle:u64,pub frozen:FrozenHold,pub status:ReservationStatus,pub result:Option<Terminal>}
fn reservation(v:&Value,account:&str,database:i32)->io::Result<Reservation>{keys(v,&["reservation_id","run_id","battle_id","native_inventory_id","vehicle_inventory_id","status","frozen","frozen_sha256","result"])?;
    let run=text(v,"run_id")?;if !uuid(run)||!identifier(text(v,"reservation_id")?){return Err(bad("receipt run/id"));}let b=battle(text(v,"battle_id")?,run)?;
    let frozen=parse_frozen(&v["frozen"],account,text(v,"frozen_sha256")?)?;let f=&frozen.loss().base;
    if num(v,"native_inventory_id")?!=u64::from(f.native_inventory_id)||text(v,"vehicle_inventory_id")?!=f.vehicle_inventory_id{return Err(bad("receipt source vehicle"));}
    let status=match text(v,"status")?{"active"=>ReservationStatus::Active,"finished"=>ReservationStatus::Finished,"aborted_restart"=>ReservationStatus::AbortedRestart,_=>return Err(bad("receipt status"))};
    let mut r=Reservation{reservation_id:text(v,"reservation_id")?.into(),run_id:run.into(),battle:b,frozen,status,result:None};
    if v["result"].is_null(){if status!=ReservationStatus::Active{return Err(bad("missing terminal"));}return Ok(r);}
    if status==ReservationStatus::Active{return Err(bad("active terminal"));}let t=&v["result"];
    keys(t,&["reason","remaining_ammunition","fired_ammunition","lost_ammunition","loss_event","terminal_hp","destroyed","repaired_hp","credits","xp","terminal_state","source_link","departure","finalization"])?;
    let remaining=rows(&t["remaining_ammunition"])?;let fired=rows(&t["fired_ammunition"])?;let lost=rows(&t["lost_ammunition"])?;let e=event(&t["loss_event"])?;
    let finalization=finalization(&t["finalization"])?;let source_link=link(&t["source_link"])?;let departure=departure(&t["departure"])?;let reason=text(t,"reason")?;
    let f=&r.frozen.loss().base;if num(t,"credits")?!=0||num(t,"xp")?!=0||num(t,"repaired_hp")?!=f.max_hp as u64{return Err(bad("terminal policy rewards/repair"));}
    let(hp,destroyed,state)=if status==ReservationStatus::AbortedRestart{if reason!="aborted_restart"||finalization!=Finalization::AbortedRestart||source_link.is_some()||departure.is_some()||!t["terminal_hp"].is_null()||!t["destroyed"].is_null()||!t["terminal_state"].is_null()
            ||e.is_some()||fired.iter().chain(&lost).any(|s|s.count!=0)||remaining!=f.ammunition.each_ref().map(|s|Remaining{shell_compact_id:s.shell_compact_id,count:s.count}){return Err(bad("restart must not infer uncommitted actor"));}(None,None,None)
        }else{let hp=i16::try_from(num(t,"terminal_hp")?).map_err(|_|bad("health width"))?;let raw=serde_json::to_string(&t["terminal_state"]).map_err(|_|bad("terminal JSON"))?;let state=mixed::validate_terminal_json(&raw,f,hp)?;
            let destroyed=t["destroyed"].as_bool().ok_or_else(||bad("destroyed bool"))?;if destroyed!=(hp==0||!state.raw["crew_active"].as_bool().ok_or_else(||bad("crew bool"))?){return Err(bad("destroyed source state"));}
            let reason_enum=match reason{"battle_finished"=>FinishReason::BattleFinished,"battle_failure"=>FinishReason::BattleFailure,"cancelled"=>FinishReason::Cancelled,_=>return Err(bad("terminal5 final reason"))};
            // Full Outcome result lives in its separate authoritative result row;
            // reply terminal validates scalar/meta identity here. Request/result
            // equality is checked below against the immutable actual command.
            if let Some(l)=&source_link{l.validate_reservation(&r,account,database)?;if l.actor_slot as u64>=state.raw["roster_size"].as_u64().ok_or_else(||bad("roster"))?{return Err(bad("terminal linked roster"));}}
            for i in 0..3{if [remaining[i],fired[i],lost[i]].iter().any(|s|s.shell_compact_id!=f.ammunition[i].shell_compact_id)||u32::from(remaining[i].count)+u32::from(fired[i].count)+u32::from(lost[i].count)!=u32::from(f.ammunition[i].count){return Err(bad("terminal5 stack conservation"));}}
            match finalization{Finalization::Outcome{tick}|Finalization::ContainedFailure{tick}=>{if source_link.is_none()||departure.is_some_and(|d|d.tick>tick)||e.is_some_and(|e|e.tick>tick||Some(e.target_slot)!=source_link.as_ref().map(|l|l.actor_slot))
                    ||state.raw["death"]["tick"].as_u64().is_none_or(|death|death>u64::from(tick))
                    ||(matches!(finalization,Finalization::Outcome{..}))!=(reason_enum==FinishReason::BattleFinished)
                    ||matches!(finalization,Finalization::ContainedFailure{..})&&reason_enum!=FinishReason::BattleFailure{return Err(bad("terminal finalization metadata"));}},
                Finalization::PristineCancel=>{if reason_enum!=FinishReason::Cancelled||source_link.is_some()||departure.is_some()||hp!=f.max_hp||fired.iter().chain(&lost).any(|s|s.count!=0)||e.is_some()
                    ||state.raw!=mixed::bounded_json(crate::gateway091::shared::model::World::cancelled_terminal_state(f)?.as_bytes(),8192)?{return Err(bad("terminal pristine"));}},_=>return Err(bad("finished cannot be restart"))}
            if let Some(e)=e{let bay=state.raw["devices"].as_array().and_then(|a|a.iter().find(|d|d["extra_index"]==27));
                if hp!=0||remaining.iter().any(|s|s.count!=0)||lost.iter().all(|s|s.count==0)||bay.is_none_or(|d|d["health"]!=0)
                    ||state.killer_slot!=Some(e.attacker_slot)||state.raw["death"]["tick"].as_u64()!=Some(u64::from(e.tick))
                    ||e.attacker_slot>=state.roster_size||e.target_slot>=state.roster_size{return Err(bad("terminal loss device/death/cause"));}
            }else if lost.iter().any(|s|s.count!=0){return Err(bad("terminal loss without cause"));}
            (Some(hp),Some(destroyed),Some(state))};
    r.result=Some(Terminal{reason:reason.into(),remaining,fired,lost,loss_event:e,hp,destroyed,repaired_hp:f.max_hp,state,source_link,departure,finalization});Ok(r)}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Status{Ready,Admitted,Finished,Inspected,Rejected}
#[derive(Clone,Debug)]pub struct Reply{pub revision:u64,pub status:Status,pub replayed:bool,pub code:Option<String>,pub reservation:Option<Reservation>}
fn rejection(code:&str)->bool{matches!(code,"STALE_REVISION"|"RUN_FENCED"|"RUN_NOT_OPEN"|"VEHICLE_RESERVED"|"UNKNOWN_VEHICLE"|"BATTLE_PROFILE_UNSUPPORTED"|"OWNER_ACCEPTANCE_REQUIRED"|"INCOMPLETE_CREW"|"AMMUNITION_EMPTY"|"AMMUNITION_UNSUPPORTED"|"RESERVATION_TERMINAL"|"RESERVATION_MISMATCH"|"INVALID_RESULT"|"INVALID_TERMINAL_STATE"|"RESULT_MISMATCH"|"DUPLICATE_PAYLOAD_MISMATCH"|"OWNER_HOLD_POLICY_REQUIRED"|"OWNER_HOLD_WRONG_ACTIVE_CONTRACT"|"INVALID_SOURCE_LINK")}
pub fn parse_reply(raw:&[u8],c:&Context,request:&Request)->io::Result<Reply>{encode_request(c,request)?;let v=mixed::bounded_json(raw,MAX_REPLY)?;
    keys(&v,&["version","contract","operation","account_id","native_database_id","command_key","run_id","source_revision","revision","replayed","status","code","reservation","legacy_reservation","policy_sha256"])?;
    if num(&v,"version")?!=VERSION||text(&v,"contract")?!=CONTRACT||text(&v,"operation")?!=request.operation()||text(&v,"account_id")?!=c.account_id||num(&v,"native_database_id")?!=c.native_database_id as u64
        ||text(&v,"command_key")?!=c.command_key||text(&v,"run_id")?!=c.run_id||num(&v,"source_revision")?!=c.expected_revision||text(&v,"policy_sha256")?!=POLICY_SHA256||!v["legacy_reservation"].is_null(){return Err(bad("reply context/policy"));}
    let revision=num(&v,"revision")?;if revision<13||revision>=i32::MAX as u64{return Err(bad("reply revision"));}let replayed=v["replayed"].as_bool().ok_or_else(||bad("replayed bool"))?;
    let status=match text(&v,"status")?{"ready"=>Status::Ready,"admitted"=>Status::Admitted,"finished"=>Status::Finished,"inspected"=>Status::Inspected,"rejected"=>Status::Rejected,_=>return Err(bad("reply status"))};
    if status==Status::Rejected{let code=text(&v,"code")?;if !rejection(code)||!v["reservation"].is_null()||replayed{return Err(bad("rejection contract"));}return Ok(Reply{revision,status,replayed,code:Some(code.into()),reservation:None});}
    if !v["code"].is_null(){return Err(bad("success code"));}let reservation=if v["reservation"].is_null(){None}else{Some(reservation(&v["reservation"],&c.account_id,c.native_database_id)?)};
    match request{Request::RunOpen=>{if status!=Status::Ready||!matches!(revision,r if r==c.expected_revision||r==c.expected_revision+1)
            ||reservation.as_ref().is_some_and(|r|match r.status{
                ReservationStatus::AbortedRestart=>r.run_id==c.run_id||revision!=c.expected_revision+1,
                ReservationStatus::Active=>r.run_id!=c.run_id||revision!=c.expected_revision,_=>true}){return Err(bad("run_open result"));}},
        Request::Inspect=>if status!=Status::Inspected||replayed||reservation.as_ref().is_some_and(|r|r.status!=ReservationStatus::Active){return Err(bad("Inspect cannot mint finished/replay"));},
        Request::Admit{battle,native_inventory_id}=>{let r=reservation.as_ref().ok_or_else(||bad("missing admit receipt"))?;if status!=Status::Admitted||revision!=c.expected_revision+1||r.status!=ReservationStatus::Active||r.run_id!=c.run_id||r.battle!=*battle||r.frozen.loss().base.native_inventory_id!=*native_inventory_id||r.reservation_id!=c.command_key{return Err(bad("admit typed5 receipt"));}},
        Request::Finish(f)=>{let r=reservation.as_ref().ok_or_else(||bad("missing Finish receipt"))?;let t=r.result.as_ref().ok_or_else(||bad("missing final terminal"))?;
            if status!=Status::Finished||revision!=c.expected_revision+1||r.status!=ReservationStatus::Finished||r.run_id!=c.run_id||r.battle!=f.battle||r.reservation_id!=f.reservation_id||r.frozen.loss().base.native_inventory_id!=f.native_inventory_id
                ||t.remaining!=f.remaining||t.fired!=f.fired||t.lost!=f.lost||t.loss_event!=f.loss_event||t.hp!=Some(f.terminal_hp)||t.reason!=f.reason.name()||t.source_link!=f.source_link||t.departure!=f.departure||t.finalization!=f.finalization
                ||t.state.as_ref().is_none_or(|s|mixed::bounded_json(f.terminal_state_json.as_bytes(),8192).ok().as_ref()!=Some(&s.raw)){return Err(bad("Finished differs from immutable final command"));}
            let mut active=r.clone();active.status=ReservationStatus::Active;active.result=None;f.validate_against(c,&active)?;},
    }Ok(Reply{revision,status,replayed,code:None,reservation})}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum ResultsRequest{Query{arena:u64},Ack{arena:u64}}
impl ResultsRequest{pub fn operation(self)->&'static str{match self{Self::Query{..}=>"query",Self::Ack{..}=>"ack"}}pub fn arena(self)->u64{match self{Self::Query{arena}|Self::Ack{arena}=>arena}}}
pub fn encode_results_request(c:&Context,r:ResultsRequest)->io::Result<Vec<u8>>{context(c)?;if r.arena()==0||r.arena()>i64::MAX as u64{return Err(bad("result arena"));}
    serde_json::to_vec(&serde_json::json!({"version":VERSION,"contract":CONTRACT,"operation":r.operation(),"account_id":c.account_id,"native_database_id":c.native_database_id,"command_key":c.command_key,"arena_id":r.arena().to_string()})).map_err(|_|bad("result request"))}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum RecordContract{ApV1,MixedV2,LossV1,HoldV1}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum ResultsStatus{Found,Missing,Acked,Rejected}
#[derive(Clone,Debug,PartialEq)]pub struct ResultsReply{pub status:ResultsStatus,pub acked:bool,pub replayed:bool,pub code:Option<String>,pub results:Option<crate::gateway091::shared::lifecycle_wire::Results>,pub results_json:Option<String>,pub record_contract:Option<RecordContract>}
pub fn parse_results_reply(raw:&[u8],c:&Context,r:ResultsRequest)->io::Result<ResultsReply>{encode_results_request(c,r)?;let v=mixed::bounded_json(raw,65536)?;
    keys(&v,&["version","contract","operation","account_id","native_database_id","command_key","arena_id","status","acked","results_json","replayed","code","policy_sha256","record_contract"])?;
    if num(&v,"version")?!=VERSION||text(&v,"contract")?!=CONTRACT||text(&v,"operation")?!=r.operation()||text(&v,"account_id")?!=c.account_id||num(&v,"native_database_id")?!=c.native_database_id as u64||text(&v,"command_key")?!=c.command_key||text(&v,"arena_id")?!=r.arena().to_string()||text(&v,"policy_sha256")?!=POLICY_SHA256{return Err(bad("result context/policy"));}
    let status=match text(&v,"status")?{"found"=>ResultsStatus::Found,"missing"=>ResultsStatus::Missing,"acked"=>ResultsStatus::Acked,"rejected"=>ResultsStatus::Rejected,_=>return Err(bad("result status"))};
    let acked=v["acked"].as_bool().ok_or_else(||bad("acked bool"))?;let replayed=v["replayed"].as_bool().ok_or_else(||bad("replayed bool"))?;
    let code=if v["code"].is_null(){None}else{let s=text(&v,"code")?;if !matches!(s,"RESULT_MISMATCH"|"DUPLICATE_PAYLOAD_MISMATCH"|"OWNER_HOLD_POLICY_REQUIRED"){return Err(bad("result code"));}Some(s.into())};
    let record_contract=if v["record_contract"].is_null(){None}else{Some(match text(&v,"record_contract")?{"ap-v1"=>RecordContract::ApV1,"mixed-v2"=>RecordContract::MixedV2,"loss-v1"=>RecordContract::LossV1,"hold-v1"=>RecordContract::HoldV1,_=>return Err(bad("actual record contract"))})};
    let results_json=if v["results_json"].is_null(){None}else{Some(text(&v,"results_json")?.to_owned())};
    let results=results_json.as_ref().map(|s|crate::gateway091::shared::lifecycle_wire::Results::from_json_p06t(s)).transpose()?;
    if (status==ResultsStatus::Rejected)!=code.is_some()||matches!(status,ResultsStatus::Missing|ResultsStatus::Rejected)&&(acked||replayed||results.is_some()||record_contract.is_some())
        ||matches!(status,ResultsStatus::Found|ResultsStatus::Acked)&&(results.is_none()||record_contract.is_none())||status==ResultsStatus::Found&&r.operation()!="query"||status==ResultsStatus::Acked&&(r.operation()!="ack"||!acked)||replayed&&status!=ResultsStatus::Acked{return Err(bad("result status/state"));}
    if let Some(result)=&results{if result.arena_id!=r.arena()||!result.participants.iter().any(|p|p.account_dbid==c.native_database_id)||record_contract==Some(RecordContract::HoldV1)&&result.interaction_details.is_none(){return Err(bad("result owner/arena/version"));}}
    Ok(ResultsReply{status,acked,replayed,code,results,results_json,record_contract})}

#[cfg(test)]
mod tests {
    use super::*;
    const ACTUAL: &[u8] = include_bytes!("../../../../tests/fixtures/p06t-ammo-loss-writer-vectors.json");
    fn fixture() -> (Value, String) {
        assert_eq!(format!("{:x}", Sha256::digest(ACTUAL)),
            "251c60f587d14d916e5381567d8af2982b26f0f98335af8464b75bbf1cc1f154");
        let document: Value = serde_json::from_slice(ACTUAL).unwrap();
        let row = document["vectors"].as_array().unwrap().iter()
            .find(|r| r["request"]["operation"] == "admit").unwrap();
        (row["response"]["reservation"]["frozen"].clone(),
            row["request"]["account_id"].as_str().unwrap().into())
    }
    #[test]
    fn p08b_hold5_actual_loss4_inner_remains_exact_and_separate() {
        let (inner, owner) = fixture();
        let frozen = wrap_source_candidate(&inner, &owner).unwrap();
        assert_eq!(frozen.value()["loss_frozen"], inner);
        assert_eq!(frozen.loss().sha256, sha(&inner).unwrap());
        frozen.validate_owned(&owner).unwrap();
        assert!(loss::parse_frozen(frozen.value(), &owner, frozen.sha256()).is_err());
        assert!(parse_frozen(&inner, &owner, &sha(&inner).unwrap()).is_err());
    }
    #[test]
    fn p08b_hold5_rehashed_policy_owner_and_nested_source_poison_refuse() {
        let (inner, owner) = fixture();
        let frozen = wrap_source_candidate(&inner, &owner).unwrap();
        let mut wrong = frozen.value().clone();
        wrong["hold_policy_sha256"] = loss::POLICY_SHA256.into();
        assert!(parse_frozen(&wrong, &owner, &sha(&wrong).unwrap()).is_err());
        assert!(parse_frozen(frozen.value(), "ffffffff-ffff-4fff-8fff-ffffffffffff", frozen.sha256()).is_err());
        let mut wrong = frozen.value().clone();
        wrong["loss_frozen"]["loadout"]["ammunition"][0]["count"] = 161.into();
        wrong["loss_frozen"]["loadout_sha256"] = sha(&wrong["loss_frozen"]["loadout"]).unwrap().into();
        wrong["loss_frozen_sha256"] = sha(&wrong["loss_frozen"]).unwrap().into();
        assert!(parse_frozen(&wrong, &owner, &sha(&wrong).unwrap()).is_err());
    }
    #[test]
    fn p08b_hold5_unknown_field_nested_hash_and_duplicate_raw_refuse() {
        let (inner, owner) = fixture();
        let frozen = wrap_source_candidate(&inner, &owner).unwrap();
        let mut wrong = frozen.value().clone();
        wrong["hold"] = true.into();
        assert!(parse_frozen(&wrong, &owner, &sha(&wrong).unwrap()).is_err());
        let mut wrong = frozen.value().clone();
        wrong["loss_frozen_sha256"] = "0".repeat(64).into();
        assert!(parse_frozen(&wrong, &owner, &sha(&wrong).unwrap()).is_err());
        let raw = serde_json::to_string(frozen.value()).unwrap();
        let duplicate = format!("{{\"hold_policy_sha256\":\"{POLICY_SHA256}\",{}", &raw[1..]);
        assert!(parse_raw(duplicate.as_bytes(), &owner, frozen.sha256()).is_err());
    }
    #[test]
    fn p08b_hold5_draft_policy_bytes_are_canonically_pinned() {
        let value: Value = serde_json::from_slice(include_bytes!("p08b_hold_policy_v1.json")).unwrap();
        assert_eq!(sha(&value).unwrap(), POLICY_SHA256);
        assert_eq!(value["base_loss_policy_sha256"], loss::POLICY_SHA256);
        assert_eq!(value["per_shot_wal"], false);
        assert_eq!(value["committed_final_refund"], false);
    }
}

#[cfg(test)]
#[path="profile13_hold_tests.rs"]
mod tests_v5;
