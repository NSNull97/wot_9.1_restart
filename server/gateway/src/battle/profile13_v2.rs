//! Staged P06T mixed-ammo codec. Not registered in the live gateway.
//! Matches p06t_mixed_store.py candidate; terminal policy integration is pending
//! the root World DTO. Version1 parser, policies and fields remain untouched.
use std::{collections::BTreeMap,fmt,io};
use serde::{Deserialize,Deserializer,de::{self,MapAccess,SeqAccess,Visitor}};
use serde_json::Value;
use sha2::{Digest,Sha256};
use crate::battle091::profile13::{Context,FinishReason,Reservation as LegacyReservation};
use crate::gateway091::shared::{vehicle_profile::VehicleKind,lifecycle_wire::Results};
use crate::p06t_shells091 as source;
use crate::gateway091::shared::vehicle_catalog::{self as catalog,Admission};
use std::sync::atomic::{AtomicBool,Ordering};

pub const POLICY_SHA256:&str="71fddc60e36780a4be2eb4dfcfa1709791e23edf1a69d074940024404b37e0d5";
pub const TERMINAL_MANIFEST_SHA256:&str="cded466bf3c21243c10c0bcee8a013ab4cffc20f31f7275d4eab1672060b3717";
pub const MAX_REPLY:usize=8192;
fn bad(reason:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("profile13 mixed v2: {reason}"))}
fn uuid(s:&str)->bool{s.len()==36&&s.bytes().enumerate().all(|(i,b)|if[8,13,18,23].contains(&i){b==b'-'}else{b.is_ascii_digit()||(b'a'..=b'f').contains(&b)})
    &&matches!(s.as_bytes()[14],b'1'..=b'5')}
fn id(s:&str)->bool{!s.is_empty()&&s.len()<=96&&s.bytes().all(|b|b.is_ascii_alphanumeric()||b"_:-".contains(&b))}
fn keys(v:&Value,fields:&[&str])->io::Result<()>{let m=v.as_object().ok_or_else(||bad("object"))?;
    if m.len()!=fields.len()||fields.iter().any(|k|!m.contains_key(*k)){return Err(bad("exact fields"));}Ok(())}
fn text<'a>(v:&'a Value,k:&str)->io::Result<&'a str>{v[k].as_str().ok_or_else(||bad("text"))}
fn number(v:&Value,k:&str)->io::Result<u64>{v[k].as_u64().ok_or_else(||bad("integer"))}
fn flag(v:&Value,k:&str)->io::Result<bool>{v[k].as_bool().ok_or_else(||bad("boolean"))}
fn digest(v:&Value)->io::Result<String>{Ok(format!("{:x}",Sha256::digest(serde_json::to_vec(v).map_err(|_|bad("canonical"))?)))}

struct Unique(Value);
impl<'de>Deserialize<'de>for Unique{fn deserialize<D:Deserializer<'de>>(d:D)->Result<Self,D::Error>{struct V;
    impl<'de>Visitor<'de>for V{type Value=Unique;
        fn expecting(&self,f:&mut fmt::Formatter<'_>)->fmt::Result{f.write_str("bounded unique integer JSON")}
        fn visit_bool<E:de::Error>(self,v:bool)->Result<Unique,E>{Ok(Unique(v.into()))}
        fn visit_i64<E:de::Error>(self,v:i64)->Result<Unique,E>{Ok(Unique(v.into()))}
        fn visit_u64<E:de::Error>(self,v:u64)->Result<Unique,E>{Ok(Unique(v.into()))}
        fn visit_unit<E:de::Error>(self)->Result<Unique,E>{Ok(Unique(Value::Null))}
        fn visit_str<E:de::Error>(self,v:&str)->Result<Unique,E>{if v.len()>32768{return Err(E::custom("string"));}Ok(Unique(v.into()))}
        fn visit_string<E:de::Error>(self,v:String)->Result<Unique,E>{self.visit_str(&v)}
        fn visit_seq<S:SeqAccess<'de>>(self,mut s:S)->Result<Unique,S::Error>{let mut rows=Vec::new();while let Some(Unique(v))=s.next_element()?{
            if rows.len()>=256{return Err(de::Error::custom("array"));}rows.push(v);}Ok(Unique(Value::Array(rows)))}
        fn visit_map<M:MapAccess<'de>>(self,mut m:M)->Result<Unique,M::Error>{let mut rows=BTreeMap::new();while let Some((k,Unique(v)))=m.next_entry::<String,Unique>()?{
            if k.is_empty()||k.len()>64||rows.len()>=32||rows.insert(k,v).is_some(){return Err(de::Error::custom("duplicate/object"));}}
            Ok(Unique(Value::Object(rows.into_iter().collect())))}
    }d.deserialize_any(V)}}
fn walk(v:&Value,d:usize,n:&mut usize)->io::Result<()>{*n+=1;if d>12||*n>2048{return Err(bad("depth/nodes"));}
    match v{Value::Object(m)=>for v in m.values(){walk(v,d+1,n)?},Value::Array(a)=>for v in a{walk(v,d+1,n)?},_=>{}}Ok(())}
pub fn bounded_json(raw:&[u8],maximum:usize)->io::Result<Value>{if raw.is_empty()||raw.len()>maximum||maximum>65536{return Err(bad("size"));}
    let Unique(v)=serde_json::from_slice(raw).map_err(|_|bad("unique integer JSON"))?;walk(&v,0,&mut 0)?;
    if!v.is_object(){return Err(bad("root"));}Ok(v)}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct Remaining{pub shell_compact_id:u16,pub count:u16}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Stack{pub shell_definition_id:String,pub shell_compact_id:u16,pub family:source::Family,pub count:u16}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Frozen{pub kind:VehicleKind,pub mount:source::Mount,pub descriptor:Vec<u8>,pub native_inventory_id:u32,
    pub vehicle_inventory_id:String,pub max_hp:i16,pub crew_ids:Vec<String>,pub capacity:u16,pub ammunition:[Stack;3],
    pub initial_shell_compact_id:u16,pub sha256:String}
impl Frozen{pub fn counts(&self)->[u16;3]{self.ammunition.each_ref().map(|r|r.count)}
    pub fn validate_owned(&self,account:&str)->io::Result<()>{let v=serde_json::json!({"kind":self.kind.label(),
        "descriptor_hex":self.descriptor.iter().map(|b|format!("{b:02x}")).collect::<String>(),"native_inventory_id":self.native_inventory_id,
        "vehicle_inventory_id":self.vehicle_inventory_id,"max_hp":self.max_hp,"crew_ids":self.crew_ids,"capacity":self.capacity,
        "initial_shell_compact_id":self.initial_shell_compact_id,"ammunition":self.ammunition.iter().map(|r|serde_json::json!({
            "shell_definition_id":r.shell_definition_id,"shell_compact_id":r.shell_compact_id,"family":r.family.source_name(),"count":r.count})).collect::<Vec<_>>()});
        if parse_frozen(&v,account,&self.sha256)?!=*self{return Err(bad("changed frozen"));}Ok(())}}

fn device_profile(kind:VehicleKind)->Option<crate::p06t_device_caps::Profile>{use crate::p06t_device_caps::Profile as P;
    Some(match kind{VehicleKind::Ms1=>P::Ms1,VehicleKind::Is7=>P::Is7,VehicleKind::T26=>P::T26,VehicleKind::T34=>P::T34,VehicleKind::T3485=>P::T3485,_=>return None})}

/// CAT-01: admission identity read from the generated single catalog instead of
/// the closed kind list below. Off by default; the gateway config key `catalog`
/// (with this build's hash) turns it on once at startup. Rollback = drop the key.
static CATALOG_V1:AtomicBool=AtomicBool::new(false);
pub fn enable_catalog_v1()->io::Result<()>{
    if format!("{:x}",Sha256::digest(catalog::CATALOG_JSON.as_bytes()))!=catalog::CATALOG_SHA256{return Err(bad("embedded catalog hash"));}
    CATALOG_V1.store(true,Ordering::SeqCst);Ok(())}
pub fn catalog_v1_enabled()->bool{CATALOG_V1.load(Ordering::SeqCst)}

type Identity=(VehicleKind,source::Mount,String,[&'static str;3]);
/// Legacy closed list (default until owner acceptance of CAT-01).
fn legacy_identity(label:&str,native:u64)->io::Result<Identity>{
    let(kind,mount)=match label{
        "ms1"=>(VehicleKind::Ms1,source::Mount::Ms1Stock),"is7"=>(VehicleKind::Is7,source::Mount::Is7Stock),
        // Purchased P04M pool kinds. The Python writer admits them only under the
        // owner's explicit full-stand zero-economy policy (order 2026-10-19).
        "t26"=>(VehicleKind::T26,source::Mount::T26Stock),"t34"=>(VehicleKind::T34,source::Mount::T34Stock),
        "t3485"=>(VehicleKind::T3485,source::Mount::T3485Stock),_=>return Err(bad("owner acceptance required/unknown kind"))};
    let suffix=match kind{VehicleKind::Ms1 if native==1=>"starter-vehicle-v1".to_string(),VehicleKind::Is7 if native==2=>"test-is7-v1".to_string(),
        VehicleKind::T26|VehicleKind::T34|VehicleKind::T3485 if (3..=i32::MAX as u64).contains(&native)=>format!("p09e-vehicle:{native}"),
        _=>return Err(bad("stock/source/ownership"))};
    let suffixes=match kind{VehicleKind::Ms1|VehicleKind::T34=>["ap","heat","he"],_=>["ap","apcr","he"]};
    Ok((kind,mount,suffix,suffixes))
}

/// Catalog identity: admission is the data field `battle_admission`; the battle
/// physics/armor profile must still exist and agree with the catalog facts.
/// The zero-economy policy itself stays enforced by the Python writer.
fn catalog_identity(label:&str,native:u64)->io::Result<Identity>{catalog_identity_in(catalog::VEHICLES,label,native)}
pub(crate) fn catalog_identity_in(table:&[catalog::Vehicle],label:&str,native:u64)->io::Result<Identity>{
    let entry=table.iter().find(|e|e.kind==label).filter(|e|e.battle_admission!=Admission::None)
        .ok_or_else(||bad("owner acceptance required/unknown kind"))?;
    let kind=VehicleKind::from_label(label).ok_or_else(||bad("catalog kind without battle profile"))?;
    let mount=kind.mount();let p=source::profile(mount);
    let crew=device_profile(kind).ok_or_else(||bad("device profile"))?.crew().len();
    let shells:[catalog::Shell;3]=entry.shells.try_into().map_err(|_|bad("catalog three stacks"))?;
    if entry.descriptor!=kind.descriptor()||i32::from(entry.max_hp)!=i32::from(kind.max_health())||entry.ammo_capacity!=p.capacity
        ||entry.seats!=crew||entry.native_compact_id!=kind.vehicle_compact_id()
        ||shells.iter().zip(p.shots.iter()).any(|(s,shot)|s.native_compact_id!=u32::from(shot.compact_descr)||s.family!=shot.family.source_name()){
        return Err(bad("catalog disagrees with battle profile"));}
    let suffix=match entry.legacy_inventory{Some((n,s)) if native==u64::from(n)=>s.to_string(),
        None if (3..=i32::MAX as u64).contains(&native)=>format!("p09e-vehicle:{native}"),_=>return Err(bad("stock/source/ownership"))};
    Ok((kind,mount,suffix,shells.map(|s|s.suffix)))
}

pub fn parse_frozen(v:&Value,account:&str,expected_sha:&str)->io::Result<Frozen>{parse_frozen_with(v,account,expected_sha,catalog_v1_enabled())}
pub(crate) fn legacy_identity_for_tests(label:&str,native:u64)->io::Result<Identity>{legacy_identity(label,native)}
pub(crate) fn parse_frozen_with(v:&Value,account:&str,expected_sha:&str,catalog_v1:bool)->io::Result<Frozen>{
    keys(v,&["kind","descriptor_hex","native_inventory_id","vehicle_inventory_id","max_hp","crew_ids","capacity","ammunition","initial_shell_compact_id"])?;
    let native=number(v,"native_inventory_id")?;
    let(kind,mount,suffix,suffixes)=if catalog_v1{catalog_identity(text(v,"kind")?,native)?}else{legacy_identity(text(v,"kind")?,native)?};
    let crew_count=device_profile(kind).ok_or_else(||bad("device profile"))?.crew().len();
    let p=source::profile(mount);let descriptor=kind.descriptor().iter().map(|b|format!("{b:02x}")).collect::<String>();
    if!uuid(account)||text(v,"vehicle_inventory_id")?!=format!("{account}:{suffix}")
        ||text(v,"descriptor_hex")?!=descriptor||number(v,"max_hp")?!=kind.max_health()as u64||number(v,"capacity")?!=u64::from(p.capacity)
        ||p.clip_count!=1||p.additional_vehicle_qualification_required{return Err(bad("stock/source/ownership"));}
    let crew=v["crew_ids"].as_array().ok_or_else(||bad("crew"))?;let mut crew_ids=Vec::new();
    for row in crew{let s=row.as_str().ok_or_else(||bad("crew ID"))?;
        if!id(s)||!s.starts_with(&format!("{account}:"))||s.len()<=account.len()+1||crew_ids.iter().any(|x|x==s){return Err(bad("crew owner/unique"));}crew_ids.push(s.to_owned());}
    if crew_ids.len()!=crew_count{return Err(bad("crew seats"));}
    let a=v["ammunition"].as_array().ok_or_else(||bad("ammo"))?;if a.len()!=3{return Err(bad("three stacks"));}
    let mut stacks=Vec::new();
    for(i,row)in a.iter().enumerate(){keys(row,&["shell_definition_id","shell_compact_id","family","count"])?;let s=p.shots[i];
        let count=u16::try_from(number(row,"count")?).map_err(|_|bad("count bound"))?;
        if number(row,"shell_compact_id")?!=u64::from(s.compact_descr)||text(row,"family")?!=s.family.source_name()
            ||text(row,"shell_definition_id")?!=format!("shell:{}-stock-{}",kind.label(),suffixes[i])||count>p.capacity{return Err(bad("source shell/order/count"));}
        stacks.push(Stack{shell_definition_id:text(row,"shell_definition_id")?.into(),shell_compact_id:s.compact_descr,family:s.family,count});}
    let ammunition:[Stack;3]=stacks.try_into().map_err(|_|bad("stacks"))?;
    let total=ammunition.iter().try_fold(0u16,|n,r|n.checked_add(r.count)).ok_or_else(||bad("total overflow"))?;
    let first=ammunition.iter().find(|r|r.count>0).ok_or_else(||bad("empty loadout"))?.shell_compact_id;
    if total>p.capacity||number(v,"initial_shell_compact_id")?!=u64::from(first)||digest(v)?!=expected_sha{return Err(bad("capacity/initial/digest"));}
    Ok(Frozen{kind,mount,descriptor:kind.descriptor().to_vec(),native_inventory_id:native as u32,vehicle_inventory_id:text(v,"vehicle_inventory_id")?.into(),
        max_hp:kind.max_health(),crew_ids,capacity:p.capacity,ammunition,initial_shell_compact_id:first,sha256:expected_sha.into()})
}

#[derive(Clone,Debug,PartialEq,Eq)]
pub enum Request{RunOpen,Inspect,Admit{battle:u64,native_inventory_id:u32},Finish{battle:u64,native_inventory_id:u32,reservation_id:String,
    remaining_ammunition:[Remaining;3],terminal_hp:i16,terminal_state_json:String,reason:FinishReason,results_json:Option<String>}}
impl Request{pub fn operation(&self)->&'static str{match self{Self::RunOpen=>"run_open",Self::Inspect=>"inspect",Self::Admit{..}=>"admit",Self::Finish{..}=>"finish"}}
    pub fn finished_battle(&self)->Option<u64>{if let Self::Finish{battle,..}=self{Some(*battle)}else{None}}}

/// Independent health/death status is explicit for v2: a dead crew can leave
/// positive hull HP. Existing v1 Results::validate is deliberately unchanged.
fn results_v2(raw:&str)->io::Result<Results>{if raw.is_empty()||raw.len()>32768{return Err(bad("result bytes"));}
    let r:Results=serde_json::from_str(raw).map_err(|_|bad("strict results DTO"))?;
    if r.arena_id==0||r.arena_id>i64::MAX as u64||crate::map_profile091::MapId::from_arena_type_id(r.arena_type_id).is_err()||r.created_unix==0||r.winner_team>2
        ||!(1..=5).contains(&r.finish_reason)||r.duration_seconds>3600||!(2..=6).contains(&r.participants.len()){return Err(bad("result header"));}
    for(i,p)in r.participants.iter().enumerate(){if p.vehicle_id==0||p.vehicle_id>i32::MAX as u32||p.account_dbid<=0||!(1..=2).contains(&p.team)
        ||p.type_compact_descr==0||p.type_compact_descr>i32::MAX as u32||!(0..=10000).contains(&p.health)||p.shots>192||p.direct_hits>192||p.piercings>192
        ||p.damage_dealt>60000||p.damage_received>10000||p.kills>6||p.capture_points>600||p.dropped_capture_points>600||p.mileage_metres>200000
        ||p.life_time>r.duration_seconds||p.killer_id>i32::MAX as u32||!(-1..=10).contains(&p.death_reason)||p.name.is_empty()||p.name.len()>48
        ||p.name.chars().any(|c|c.is_control())||p.health==0&&p.death_reason<0
        ||p.killer_id!=0&&!r.participants.iter().any(|q|q.vehicle_id==p.killer_id)
        ||r.participants[..i].iter().any(|q|q.vehicle_id==p.vehicle_id||q.account_dbid==p.account_dbid){return Err(bad("result participant"));}}
    if![1,2].into_iter().all(|t|r.participants.iter().any(|p|p.team==t)){return Err(bad("result teams"));}Ok(r)}

pub fn encode_request(c:&Context,r:&Request)->io::Result<Vec<u8>>{
    if!uuid(&c.account_id)||!uuid(&c.run_id)||!id(&c.command_key)||c.native_database_id<=0||c.expected_revision>i32::MAX as u64
        ||!matches!(r,Request::Inspect)&&c.expected_revision<13{return Err(bad("context"));}
    let mut v=serde_json::json!({"version":2,"operation":r.operation(),"account_id":c.account_id,"native_database_id":c.native_database_id,
        "command_key":c.command_key,"expected_revision":c.expected_revision,"run_id":c.run_id});
    match r{Request::RunOpen|Request::Inspect=>{},Request::Admit{battle,native_inventory_id}|Request::Finish{battle,native_inventory_id,..}=>{
        if *battle==0||!(1..=i32::MAX as u32).contains(native_inventory_id){return Err(bad("selection"));}
        v["battle_id"]=format!("{}:{}",c.run_id,battle).into();v["native_inventory_id"]=(*native_inventory_id).into();}}
    if let Request::Finish{battle,reservation_id,remaining_ammunition,terminal_hp,terminal_state_json,reason,results_json,..}=r{
        if!id(reservation_id)||!(0..=2150).contains(terminal_hp)||remaining_ammunition.iter().any(|a|a.shell_compact_id==0||a.count>160)
            ||(*reason==FinishReason::BattleFinished)!=results_json.is_some(){return Err(bad("finish arguments"));}
        v["reservation_id"]=reservation_id.as_str().into();v["terminal_hp"]=(*terminal_hp).into();v["reason"]=reason.name().into();
        let terminal=bounded_json(terminal_state_json.as_bytes(),8192)?;
        keys(&terminal,&["policy_revision","roster_size","crew_active","crew","devices","fire","death"])?;
        v["terminal_state_json"]=terminal_state_json.as_str().into();
        v["remaining_ammunition"]=remaining_ammunition.iter().map(|a|serde_json::json!({"shell_compact_id":a.shell_compact_id,"count":a.count})).collect::<Vec<_>>().into();
        if let Some(raw)=results_json{let result=results_v2(raw)?;let own=result.participants.iter().find(|p|p.account_dbid==c.native_database_id).ok_or_else(||bad("result owner"))?;
            if result.arena_id!=*battle||own.health!=*terminal_hp{return Err(bad("result battle/HP"));}v["results_json"]=raw.as_str().into();}}
    let raw=serde_json::to_vec(&v).map_err(|_|bad("encode"))?;bounded_json(&raw,match r{Request::Finish{results_json:Some(_),..}=>65536,Request::Finish{..}=>16384,_=>2048})?;Ok(raw)
}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum ReservationStatus{Active,Finished,AbortedRestart}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct TerminalState{pub crew_active:bool,pub roster_size:u8,pub death_reason:i8,pub killer_slot:Option<u8>,pub raw:Value}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct Terminal{pub reason:String,pub remaining:[Remaining;3],pub consumed:[Remaining;3],pub terminal_hp:Option<i16>,pub destroyed:Option<bool>,pub repaired_hp:i16,pub state:Option<TerminalState>}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct Reservation{pub reservation_id:String,pub run_id:String,pub battle:u64,pub frozen:Frozen,pub status:ReservationStatus,pub result:Option<Terminal>}
fn parse_remaining(v:&Value,f:&Frozen)->io::Result<[Remaining;3]>{let rows=v.as_array().ok_or_else(||bad("remaining list"))?;
    if rows.len()!=3{return Err(bad("remaining3"));}let mut result=Vec::new();
    for(row,source)in rows.iter().zip(&f.ammunition){keys(row,&["shell_compact_id","count"])?;let n=u16::try_from(number(row,"count")?).map_err(|_|bad("remaining count"))?;
        if number(row,"shell_compact_id")?!=u64::from(source.shell_compact_id)||n>source.count{return Err(bad("remaining source/order/increase"));}
        result.push(Remaining{shell_compact_id:source.shell_compact_id,count:n});}result.try_into().map_err(|_|bad("remaining3"))}
fn terminal_state(v:&Value,f:&Frozen,hp:i16)->io::Result<TerminalState>{
    keys(v,&["policy_revision","roster_size","crew_active","crew","devices","fire","death"])?;
    if serde_json::to_vec(v).map_err(|_|bad("terminal JSON"))?.len()>8192||text(v,"policy_revision")?!="test_lab.p06t.devices-proxy-fire.v1"{return Err(bad("terminal pinned policy"));}
    let roster_size=u8::try_from(number(v,"roster_size")?).map_err(|_|bad("roster bound"))?;if roster_size>6{return Err(bad("roster bound"));}
    let crew_active=flag(v,"crew_active")?;let crew=v["crew"].as_array().ok_or_else(||bad("crew state"))?;
    if crew.len()!=f.crew_ids.len(){return Err(bad("frozen crew count"));}let mut any=false;
    for(row,id)in crew.iter().zip(&f.crew_ids){keys(row,&["crew_id","alive"])?;if text(row,"crew_id")?!=id{return Err(bad("frozen crew identity/order"));}any|=flag(row,"alive")?;}
    if any!=crew_active{return Err(bad("crew active policy"));}
    // Source device maxima of the admitted stock profiles (the MS-1/IS-7 rows
    // are the pinned TERMINAL_MANIFEST values). Not universal defaults.
    let maxima=(*device_profile(f.kind).ok_or_else(||bad("terminal admission"))?.caps()).map(|c|u64::from(c.max));
    let devices=v["devices"].as_array().ok_or_else(||bad("devices"))?;if devices.len()!=maxima.len(){return Err(bad("device count"));}
    for(i,(row,max))in devices.iter().zip(maxima).enumerate(){keys(row,&["extra_index","health","max_health"])?;
        if number(row,"extra_index")?!=26+i as u64||number(row,"max_health")?!=max||number(row,"health")?>max{return Err(bad("source device maxima/order"));}}
    let fire=&v["fire"];keys(fire,&["active","ticks","damage"])?;flag(fire,"active")?;
    if number(fire,"ticks")?>216000||number(fire,"damage")?>60000{return Err(bad("fire bound"));}
    let death=&v["death"];keys(death,&["reason","killer_slot","tick"])?;
    let reason=death["reason"].as_i64().ok_or_else(||bad("death reason"))?;
    if!(-1..=10).contains(&reason)||number(death,"tick")?>216000{return Err(bad("death bound"));}
    let killer_slot=if death["killer_slot"].is_null(){None}else{let k=u8::try_from(number(death,"killer_slot")?).map_err(|_|bad("killer slot"))?;
        if k>=roster_size{return Err(bad("killer roster"));}Some(k)};
    if hp>0&&crew_active&&(reason!=-1||killer_slot.is_some())||(hp==0||!crew_active)&&reason<0{return Err(bad("hull/crew death state"));}
    Ok(TerminalState{crew_active,roster_size,death_reason:reason as i8,killer_slot,raw:v.clone()})
}
pub fn validate_terminal_json(raw:&str,frozen:&Frozen,hp:i16)->io::Result<TerminalState>{
    if !(0..=frozen.max_hp).contains(&hp){return Err(bad("terminal HP bound"));}
    terminal_state(&bounded_json(raw.as_bytes(),8192)?,frozen,hp)
}
fn reservation(v:&Value,account:&str)->io::Result<Reservation>{keys(v,&["reservation_id","run_id","battle_id","native_inventory_id","vehicle_inventory_id","status","frozen","frozen_sha256","result"])?;
    let key=text(v,"reservation_id")?;let run=text(v,"run_id")?;let raw=text(v,"battle_id")?;
    let battle=raw.strip_prefix(&format!("{run}:")).ok_or_else(||bad("battle run"))?.parse::<u64>().map_err(|_|bad("battle number"))?;
    if!id(key)||!uuid(run)||battle==0||raw!=format!("{run}:{battle}"){return Err(bad("reservation identity"));}
    let f=parse_frozen(&v["frozen"],account,text(v,"frozen_sha256")?)?;
    if number(v,"native_inventory_id")?!=u64::from(f.native_inventory_id)||text(v,"vehicle_inventory_id")?!=f.vehicle_inventory_id{return Err(bad("reservation vehicle"));}
    let status=match text(v,"status")?{"active"=>ReservationStatus::Active,"finished"=>ReservationStatus::Finished,"aborted_restart"=>ReservationStatus::AbortedRestart,_=>return Err(bad("reservation status"))};
    let result=if v["result"].is_null(){if status!=ReservationStatus::Active{return Err(bad("missing result"));}None}else{
        if status==ReservationStatus::Active{return Err(bad("active terminal"));}let r=&v["result"];
        keys(r,&["reason","remaining_ammunition","consumed_ammunition","terminal_hp","destroyed","repaired_hp","credits","xp","terminal_state"])?;
        let remaining=parse_remaining(&r["remaining_ammunition"],&f)?;let consumed=parse_remaining(&r["consumed_ammunition"],&f)?;
        if remaining.iter().zip(consumed.iter()).zip(&f.ammunition).any(|((a,b),s)|a.count.checked_add(b.count)!=Some(s.count))
            ||number(r,"repaired_hp")?!=f.max_hp as u64||number(r,"credits")?!=0||number(r,"xp")?!=0{return Err(bad("result count/repair policy"));}
        let reason=text(r,"reason")?;let(hp,destroyed,state)=if status==ReservationStatus::AbortedRestart{
            if reason!="aborted_restart"||!r["terminal_hp"].is_null()||!r["destroyed"].is_null()||!r["terminal_state"].is_null()||consumed.iter().any(|a|a.count!=0){return Err(bad("restart unknown/refund"));}(None,None,None)
        }else{let hp=i16::try_from(number(r,"terminal_hp")?).map_err(|_|bad("terminal HP"))?;let d=flag(r,"destroyed")?;
            let state=terminal_state(&r["terminal_state"],&f,hp)?;
            if hp>f.max_hp||d!=(hp==0||!state.crew_active)||!["manual_leave","battle_failure","disconnect","cancelled","battle_finished"].contains(&reason){return Err(bad("normal terminal"));}(Some(hp),Some(d),Some(state))};
        Some(Terminal{reason:reason.into(),remaining,consumed,terminal_hp:hp,destroyed,repaired_hp:f.max_hp,state})};
    Ok(Reservation{reservation_id:key.into(),run_id:run.into(),battle,frozen:f,status,result})}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Status{Ready,Admitted,Finished,Inspected,Rejected}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct Reply{pub status:Status,pub revision:u64,pub replayed:bool,pub code:Option<String>,pub reservation:Option<Reservation>,pub legacy_reservation:Option<LegacyReservation>}
fn legacy(v:&Value,c:&Context,revision:u64,operation:&str)->io::Result<LegacyReservation>{
    // Reuse unchanged v1 validation for an explicitly tagged nested v1 receipt.
    // This internal validation envelope never enters the transport or writer.
    let request=if operation=="run_open"{crate::battle091::profile13::Request::RunOpen}else{crate::battle091::profile13::Request::Inspect};
    let envelope=serde_json::json!({"version":1,"operation":operation,"status":if operation=="run_open"{"ready"}else{"inspected"},"account_id":c.account_id,
        "native_database_id":c.native_database_id,"command_key":c.command_key,"run_id":c.run_id,"source_revision":c.expected_revision,"revision":revision,
        "replayed":false,"code":null,"reservation":v,"policy_sha256":crate::battle091::profile13::POLICY_SHA256});
    crate::battle091::profile13::parse_reply(&serde_json::to_vec(&envelope).map_err(|_|bad("legacy envelope"))?,c,&request)?.reservation.ok_or_else(||bad("legacy receipt"))}

pub fn parse_reply(raw:&[u8],c:&Context,r:&Request)->io::Result<Reply>{encode_request(c,r)?;let v=bounded_json(raw,MAX_REPLY)?;
    keys(&v,&["version","operation","status","account_id","native_database_id","command_key","run_id","source_revision","revision","replayed","code","reservation","legacy_reservation","policy_sha256"])?;
    if number(&v,"version")?!=2||text(&v,"operation")?!=r.operation()||text(&v,"account_id")?!=c.account_id||number(&v,"native_database_id")?!=c.native_database_id as u64
        ||text(&v,"command_key")?!=c.command_key||text(&v,"run_id")?!=c.run_id||number(&v,"source_revision")?!=c.expected_revision||text(&v,"policy_sha256")?!=POLICY_SHA256{return Err(bad("reply binding"));}
    let revision=number(&v,"revision")?;if!(13..=i32::MAX as u64).contains(&revision){return Err(bad("reply revision"));}
    let status=match text(&v,"status")?{"ready"=>Status::Ready,"admitted"=>Status::Admitted,"finished"=>Status::Finished,"inspected"=>Status::Inspected,"rejected"=>Status::Rejected,_=>return Err(bad("reply status"))};
    let replayed=flag(&v,"replayed")?;let code=if v["code"].is_null(){None}else{let s=text(&v,"code")?;
        if!["STALE_REVISION","RUN_FENCED","RUN_NOT_OPEN","VEHICLE_RESERVED","UNKNOWN_VEHICLE","BATTLE_PROFILE_UNSUPPORTED","OWNER_ACCEPTANCE_REQUIRED","INCOMPLETE_CREW","AMMUNITION_EMPTY","AMMUNITION_UNSUPPORTED","RESERVATION_TERMINAL","RESERVATION_MISMATCH","DUPLICATE_PAYLOAD_MISMATCH","INVALID_RESULT","RESULT_MISMATCH","INVALID_TERMINAL_STATE","RUN_HAS_LEGACY_RESERVATION","MIXED_RESERVATION_ACTIVE"].contains(&s){return Err(bad("rejection code"));}Some(s.into())};
    let reservation=if v["reservation"].is_null(){None}else{Some(reservation(&v["reservation"],&c.account_id)?)};
    let legacy_reservation=if v["legacy_reservation"].is_null(){None}else{
        if!matches!(r,Request::RunOpen|Request::Inspect){return Err(bad("legacy operation"));}Some(legacy(&v["legacy_reservation"],c,revision,r.operation())?)};
    if(status==Status::Rejected)!=code.is_some()||reservation.is_some()&&legacy_reservation.is_some(){return Err(bad("status/code/reservation"));}
    if status==Status::Rejected{if replayed||reservation.is_some()||legacy_reservation.is_some(){return Err(bad("rejected state"));}}
    else{let expected=match r{Request::RunOpen=>Status::Ready,Request::Inspect=>Status::Inspected,Request::Admit{..}=>Status::Admitted,Request::Finish{..}=>Status::Finished};
        if status!=expected{return Err(bad("operation status"));}
        match r{Request::Inspect=>{if replayed||reservation.as_ref().is_some_and(|a|a.status!=ReservationStatus::Active){return Err(bad("inspect active only"));}},
            Request::RunOpen=>{if revision!=c.expected_revision&&revision!=c.expected_revision+1{return Err(bad("run revision"));}
                if reservation.as_ref().is_some_and(|a|a.status!=ReservationStatus::AbortedRestart||a.run_id==c.run_id||revision==c.expected_revision){return Err(bad("run recovery"));}},
            Request::Admit{battle,native_inventory_id}|Request::Finish{battle,native_inventory_id,..}=>{
                if revision!=c.expected_revision+1{return Err(bad("mutation revision"));}let row=reservation.as_ref().ok_or_else(||bad("mutation receipt"))?;
                if row.run_id!=c.run_id||row.battle!=*battle||row.frozen.native_inventory_id!=*native_inventory_id{return Err(bad("mutation ownership"));}
                match r{Request::Admit{..}=>{if row.status!=ReservationStatus::Active||row.reservation_id!=c.command_key{return Err(bad("admit identity"));}},
                    Request::Finish{reservation_id,remaining_ammunition,terminal_hp,terminal_state_json,reason,results_json,..}=>{let result=row.result.as_ref().ok_or_else(||bad("finish result"))?;
                        if row.status!=ReservationStatus::Finished||row.reservation_id!=*reservation_id||result.remaining!=*remaining_ammunition||result.terminal_hp!=Some(*terminal_hp)||result.reason!=reason.name(){return Err(bad("finish binding"));}
                        let state=result.state.as_ref().ok_or_else(||bad("finish terminal state"))?;if state.raw!=bounded_json(terminal_state_json.as_bytes(),8192)?{return Err(bad("finish terminal binding"));}
                        if let Some(raw)=results_json{let stats=results_v2(raw)?;let own=stats.participants.iter().find(|p|p.account_dbid==c.native_database_id).ok_or_else(||bad("finish result owner"))?;
                            if own.shots!=result.consumed.iter().map(|s|s.count).sum::<u16>()||usize::from(state.roster_size)!=stats.participants.len()
                                ||own.death_reason!=state.death_reason||own.killer_id!=state.killer_slot.map_or(0,|slot|stats.participants[slot as usize].vehicle_id){return Err(bad("finish per-stack/journal stats"));}}},_=>unreachable!()}
            }}}
    Ok(Reply{status,revision,replayed,code,reservation,legacy_reservation})}

#[cfg(test)]
mod tests{
    use super::*;
    const VECTORS:&[u8]=include_bytes!("../../../../tests/fixtures/p06t-writer-vectors.json");
    fn vectors()->Value{
        assert_eq!(format!("{:x}",Sha256::digest(VECTORS)),"0e293febb5e3053e34f5b543c19aa2f7420918415b22595aaa4bb16e532b2c21");
        serde_json::from_slice(VECTORS).unwrap()
    }
    fn context(v:&Value)->Context{Context{account_id:v["account_id"].as_str().unwrap().into(),native_database_id:v["native_database_id"].as_i64().unwrap()as i32,
        command_key:v["command_key"].as_str().unwrap().into(),expected_revision:v["expected_revision"].as_u64().unwrap(),run_id:v["run_id"].as_str().unwrap().into()}}
    fn request(v:&Value)->Request{
        let battle=||v["battle_id"].as_str().unwrap().rsplit(':').next().unwrap().parse().unwrap();let native=||v["native_inventory_id"].as_u64().unwrap()as u32;
        match v["operation"].as_str().unwrap(){"run_open"=>Request::RunOpen,"inspect"=>Request::Inspect,"admit"=>Request::Admit{battle:battle(),native_inventory_id:native()},
            "finish"=>Request::Finish{battle:battle(),native_inventory_id:native(),reservation_id:v["reservation_id"].as_str().unwrap().into(),terminal_hp:v["terminal_hp"].as_i64().unwrap()as i16,
                remaining_ammunition:v["remaining_ammunition"].as_array().unwrap().iter().map(|r|Remaining{shell_compact_id:r["shell_compact_id"].as_u64().unwrap()as u16,count:r["count"].as_u64().unwrap()as u16}).collect::<Vec<_>>().try_into().unwrap(),
                terminal_state_json:v["terminal_state_json"].as_str().unwrap().into(),reason:match v["reason"].as_str().unwrap(){"battle_finished"=>FinishReason::BattleFinished,_=>panic!("export reason")},
                results_json:v.get("results_json").map(|s|s.as_str().unwrap().into())},_=>panic!("export operation")}
    }
    #[test]fn p06t_actual_sqlite_three_stack_writer_vectors_match_request_and_reply_without_v1_conversion(){
        let v=vectors();let mut battle_count=0;let mut positive_dead=false;let mut recovered_v1=false;let mut refunded=false;
        for row in v["vectors"].as_array().unwrap(){if row["operation"]!="battle"{continue;}battle_count+=1;
            let c=context(&row["request"]);let r=request(&row["request"]);
            assert_eq!(serde_json::from_slice::<Value>(&encode_request(&c,&r).unwrap()).unwrap(),row["request"]);
            let reply=parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&c,&r).unwrap();
            recovered_v1|=reply.legacy_reservation.is_some();
            if let Some(receipt)=reply.reservation{
                receipt.frozen.validate_owned(&c.account_id).unwrap();
                assert_eq!(receipt.frozen.ammunition.len(),3);
                if let Some(result)=receipt.result{
                    positive_dead|=result.terminal_hp==Some(23)&&result.destroyed==Some(true);
                    refunded|=receipt.status==ReservationStatus::AbortedRestart&&result.state.is_none()&&result.terminal_hp.is_none();
                }
            }
        }
        assert_eq!(battle_count,10);assert!(positive_dead&&recovered_v1&&refunded);
    }
    #[test]fn p06t_writer_reply_rejects_foreign_source_ammo_and_terminal_policy_poison(){
        let v=vectors();let row=v["vectors"].as_array().unwrap().iter().find(|r|r["request"]["operation"]=="finish").unwrap();
        let c=context(&row["request"]);let r=request(&row["request"]);
        for n in 0..6{let mut response=row["response"].clone();match n{
            0=>response["account_id"]="foreign".into(),
            1=>response["reservation"]["result"]["terminal_state"]["crew"][0]["crew_id"]="foreign:crew".into(),
            2=>response["reservation"]["result"]["terminal_state"]["devices"][0]["max_health"]=26.into(),
            3=>response["reservation"]["result"]["terminal_state"]["crew_active"]=true.into(),
            4=>{let f=&mut response["reservation"]["frozen"];f["ammunition"][1]["shell_compact_id"]=2570.into();let hash=digest(f).unwrap();response["reservation"]["frozen_sha256"]=hash.into();},
            _=>response["policy_sha256"]="0".repeat(64).into(),
        }assert!(parse_reply(&serde_json::to_vec(&response).unwrap(),&c,&r).is_err(),"poison {n}");}
        assert!(bounded_json(br#"{"x":1,"x":2}"#,2048).is_err());assert!(bounded_json(br#"{"x":0.5}"#,2048).is_err());
    }
    fn pool_frozen(account:&str,kind:VehicleKind,mount:source::Mount,native:u64,suffixes:[&str;3])->Value{
        let p=source::profile(mount);let crew=device_profile(kind).unwrap().crew().len();
        serde_json::json!({"kind":kind.label(),"descriptor_hex":kind.descriptor().iter().map(|b|format!("{b:02x}")).collect::<String>(),
            "native_inventory_id":native,"vehicle_inventory_id":format!("{account}:p09e-vehicle:{native}"),"max_hp":kind.max_health(),
            "crew_ids":(0..crew).map(|i|format!("{account}:recruit-crew:{}",20+i)).collect::<Vec<_>>(),"capacity":p.capacity,
            "ammunition":(0..3).map(|i|serde_json::json!({"shell_definition_id":format!("shell:{}-stock-{}",kind.label(),suffixes[i]),
                "shell_compact_id":p.shots[i].compact_descr,"family":p.shots[i].family.source_name(),"count":if i==0{10}else{0}})).collect::<Vec<_>>(),
            "initial_shell_compact_id":p.shots[0].compact_descr})
    }
    #[test]fn purchased_pool_kinds_parse_only_on_their_own_inventory_and_source_shell_order(){
        // Owner full stand 2026-10-20: a bought T-26/T-34/T-34-85 is a p09e
        // inventory row (native >= 3) with its source mount and device maxima.
        let account="12345678-1234-4234-8234-123456789abc";
        for(kind,mount,suffixes)in[(VehicleKind::T26,source::Mount::T26Stock,["ap","apcr","he"]),
            (VehicleKind::T34,source::Mount::T34Stock,["ap","heat","he"]),(VehicleKind::T3485,source::Mount::T3485Stock,["ap","apcr","he"])]{
            let v=pool_frozen(account,kind,mount,4,suffixes);let f=parse_frozen(&v,account,&digest(&v).unwrap()).unwrap();
            assert_eq!((f.kind,f.native_inventory_id,f.crew_ids.len()),(kind,4,device_profile(kind).unwrap().crew().len()));
            f.validate_owned(account).unwrap();
            for n in 0..4{let mut wrong=v.clone();match n{
                0=>{wrong["native_inventory_id"]=2.into();wrong["vehicle_inventory_id"]=format!("{account}:p09e-vehicle:2").into();},
                1=>wrong["vehicle_inventory_id"]=format!("{account}:test-is7-v1").into(),
                2=>wrong["ammunition"][1]["shell_definition_id"]=format!("shell:{}-stock-he",kind.label()).into(),
                _=>wrong["crew_ids"].as_array_mut().unwrap().pop().map(|_|()).unwrap(),
            }assert!(parse_frozen(&wrong,account,&digest(&wrong).unwrap()).is_err(),"{kind:?} mutation {n}");}
            let maxima=(*device_profile(kind).unwrap().caps());
            let terminal=serde_json::json!({"policy_revision":"test_lab.p06t.devices-proxy-fire.v1","roster_size":2,"crew_active":true,
                "crew":f.crew_ids.iter().map(|id|serde_json::json!({"crew_id":id,"alive":true})).collect::<Vec<_>>(),
                "devices":maxima.iter().enumerate().map(|(i,c)|serde_json::json!({"extra_index":26+i,"health":c.max,"max_health":c.max})).collect::<Vec<_>>(),
                "fire":{"active":false,"ticks":0,"damage":0},"death":{"reason":-1,"killer_slot":null,"tick":0}});
            validate_terminal_json(&terminal.to_string(),&f,f.max_hp).unwrap();
        }
        let ms1=pool_frozen(account,VehicleKind::Ms1,source::Mount::Ms1Stock,3,["ap","heat","he"]);
        assert!(parse_frozen(&ms1,account,&digest(&ms1).unwrap()).is_err());
    }
}
