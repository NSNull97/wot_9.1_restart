//! Original #717 arena lifecycle and compact battle-result presentation.
//!
//! Static consumers and exact field orders are pinned in P08C_NATIVE_LIFECYCLE.
//! Only server-owned scalar data is encoded; this module never decodes PYTHON.
//! Native UI/audio acceptance remains a separate owner gate.
use std::io;
use serde::{Deserialize,Serialize};

pub const AVATAR_RESULTS_STREAM:i16=100;
pub const MAX_RESULT_BYTES:usize=32768;
pub const MAX_PARTICIPANTS:usize=6;

fn bad(reason:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,reason)}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Period {Waiting=1,Prebattle=2,Battle=3,Afterbattle=4}

fn update(kind:u8,literal:Vec<u8>)->io::Result<Vec<u8>> {
    if literal.is_empty()||literal.len()>252{return Err(bad("lifecycle arena update size"));}
    let mut out=vec![0x13,0x58,(literal.len()+2) as u8,kind,literal.len() as u8];
    out.extend(literal);Ok(out)
}
fn integer(out:&mut Vec<u8>,value:i64) {
    if (0..=255).contains(&value) {out.extend([b'K',value as u8]);}
    else if (i32::MIN as i64..=i32::MAX as i64).contains(&value) {out.push(b'J');out.extend((value as i32).to_le_bytes());}
    else {out.extend([0x8a,8]);out.extend(value.to_le_bytes());}
}
fn bytes(out:&mut Vec<u8>,value:&[u8]) {
    if value.len()<256 {out.extend([b'U',value.len() as u8]);}
    else {out.push(b'T');out.extend((value.len() as u32).to_le_bytes());}
    out.extend(value);
}
fn boolean(out:&mut Vec<u8>,value:bool) {out.push(if value{0x88}else{0x89});}

/// Period is a protocol2 tuple(period, endServerTime, length, additionalInfo).
/// AFTERBATTLE requires (winnerTeam, finishReason): MusicController indexes0,
/// and original ExtendedBattleClientCtx explicitly reads indices0 and1.
pub fn period(value:Period,end_game_seconds:f64,length_seconds:f64,
    outcome:Option<(u8,u8)>)->io::Result<Vec<u8>> {
    if !end_game_seconds.is_finite()||!length_seconds.is_finite()
        ||!(0.0..=86400.0).contains(&end_game_seconds)||!(0.0..=3600.0).contains(&length_seconds)
        || (value==Period::Afterbattle)!=outcome.is_some()
        ||outcome.is_some_and(|(winner,reason)|winner>2||!(1..=5).contains(&reason)) {
        return Err(bad("lifecycle period or outcome bound"));
    }
    let mut out=vec![0x80,2,b'('];integer(&mut out,value as i64);
    out.push(b'G');out.extend(end_game_seconds.to_be_bytes());
    out.push(b'G');out.extend(length_seconds.to_be_bytes());
    if let Some((winner,reason))=outcome {integer(&mut out,winner as i64);integer(&mut out,reason as i64);out.push(0x86);}
    else {out.push(b'N');}
    out.extend(b"t.");update(3,out)
}
pub fn base_points(team:u8,base_id:u8,points:u8,capturing_stopped:bool)->io::Result<Vec<u8>> {
    if !(1..=2).contains(&team)||base_id>2||points>100 {return Err(bad("lifecycle base points bound"));}
    let mut out=vec![0x80,2,b'('];
    for value in [team,base_id,points] {integer(&mut out,value as i64);}
    boolean(&mut out,capturing_stopped);out.extend(b"t.");update(8,out)
}
pub fn base_captured(team:u8,base_id:u8)->io::Result<Vec<u8>> {
    if !(1..=2).contains(&team)||base_id>2{return Err(bad("lifecycle captured base bound"));}
    let mut out=vec![0x80,2];integer(&mut out,team as i64);integer(&mut out,base_id as i64);
    out.extend([0x86,b'.']);update(9,out)
}
pub fn vehicle_killed(victim_id:u32,killer_id:u32,reason:u8)->io::Result<Vec<u8>> {
    if victim_id==0||victim_id>i32::MAX as u32||killer_id>i32::MAX as u32||reason>10 {
        return Err(bad("lifecycle killed vehicle bound"));
    }
    let mut out=vec![0x80,2];integer(&mut out,victim_id as i64);integer(&mut out,killer_id as i64);
    integer(&mut out,reason as i64);out.extend([0x87,b'.']);update(6,out)
}

/// This DTO is a presentation snapshot, not an admission/damage command.
/// Callers derive it from their committed authoritative world and durable result.
#[derive(Clone,Debug,Default,PartialEq,Eq)]
pub struct Participant {
    pub vehicle_id:u32,pub account_dbid:i32,pub name:String,pub team:u8,
    pub type_compact_descr:u32,pub health:i16,pub shots:u16,pub direct_hits:u16,
    pub piercings:u16,pub damage_dealt:u32,pub damage_received:u32,pub kills:u8,
    pub capture_points:u16,pub dropped_capture_points:u16,pub mileage_metres:u32,
    pub life_time:u32,pub killer_id:u32,pub death_reason:i8,pub premature_leave:bool,
}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Results {
    pub arena_id:u64,pub arena_type_id:i32,pub created_unix:u32,pub winner_team:u8,
    pub finish_reason:u8,pub duration_seconds:u32,pub participants:Vec<Participant>,
}
// Keep the existing dependency set: serde's derive feature is not enabled.
macro_rules! next_dto_field {
    ($map:ident,$ty:ty)=>{$map.next_value::<$ty>()?};
    ($map:ident,$ty:ty,$decode:expr)=>{$decode};
}
macro_rules! dto_serde {
    ($name:ident,$map:ident,{$($field:ident:$ty:ty $(=> $decode:expr)?),*$(,)?})=>{
        impl Serialize for $name {
            fn serialize<S:serde::Serializer>(&self,serializer:S)->Result<S::Ok,S::Error> {
                use serde::ser::SerializeStruct;
                let mut state=serializer.serialize_struct(stringify!($name),[$(stringify!($field)),*].len())?;
                $(state.serialize_field(stringify!($field),&self.$field)?;)*state.end()
            }
        }
        impl<'de> Deserialize<'de> for $name {
            fn deserialize<D:serde::Deserializer<'de>>(deserializer:D)->Result<Self,D::Error> {
                struct DtoVisitor;
                impl<'de> serde::de::Visitor<'de> for DtoVisitor {
                    type Value=$name;
                    fn expecting(&self,f:&mut std::fmt::Formatter)->std::fmt::Result{f.write_str(stringify!($name))}
                    fn visit_map<M:serde::de::MapAccess<'de>>(self,mut $map:M)->Result<$name,M::Error> {
                        $(let mut $field:Option<$ty>=None;)*
                        while let Some(key)=$map.next_key::<String>()? {match key.as_str() {
                            $(stringify!($field)=>{if $field.is_some(){return Err(serde::de::Error::duplicate_field(stringify!($field)));}
                                $field=Some(next_dto_field!($map,$ty $(,$decode)?));},)*
                            _=>return Err(serde::de::Error::unknown_field(&key,&[$(stringify!($field)),*])),
                        }}
                        Ok($name{$($field:$field.ok_or_else(||serde::de::Error::missing_field(stringify!($field)))?),*})
                    }
                }
                deserializer.deserialize_map(DtoVisitor)
            }
        }
    };
}
struct BoundedParticipants(Vec<Participant>);
impl<'de> Deserialize<'de> for BoundedParticipants {
    fn deserialize<D:serde::Deserializer<'de>>(d:D)->Result<Self,D::Error> {
        struct ParticipantVisitor;
        impl<'de> serde::de::Visitor<'de> for ParticipantVisitor {
            type Value=BoundedParticipants;
            fn expecting(&self,f:&mut std::fmt::Formatter)->std::fmt::Result{f.write_str("at most six participants")}
            fn visit_seq<S:serde::de::SeqAccess<'de>>(self,mut seq:S)->Result<Self::Value,S::Error> {
                let mut rows=Vec::new();while let Some(row)=seq.next_element::<Participant>()? {
                    if rows.len()>=MAX_PARTICIPANTS{return Err(serde::de::Error::custom("participant count exceeds6"));}rows.push(row);
                }Ok(BoundedParticipants(rows))
            }
        }d.deserialize_seq(ParticipantVisitor)
    }
}
dto_serde!(Participant,fields,{
    vehicle_id:u32,account_dbid:i32,name:String,team:u8,type_compact_descr:u32,health:i16,shots:u16,
    direct_hits:u16,piercings:u16,damage_dealt:u32,damage_received:u32,kills:u8,capture_points:u16,
    dropped_capture_points:u16,mileage_metres:u32,life_time:u32,killer_id:u32,death_reason:i8,premature_leave:bool,
});
dto_serde!(Results,fields,{
    arena_id:u64,arena_type_id:i32,created_unix:u32,winner_team:u8,finish_reason:u8,duration_seconds:u32,
    participants:Vec<Participant> => fields.next_value::<BoundedParticipants>()?.0,
});
impl Results {
    pub fn validate(&self)->io::Result<()> {
        self.validate_inner(false)
    }
    /// A v2 terminal journal separately binds positive-HP crew death. The
    /// legacy result contract remains strict and cannot accept these rows.
    pub fn validate_p06t(&self)->io::Result<()>{self.validate_inner(true)}
    pub fn from_json_p06t(raw:&str)->io::Result<Self>{
        if raw.len()>MAX_RESULT_BYTES{return Err(bad("P06T results byte bound"));}
        let result:Self=serde_json::from_str(raw).map_err(|_|bad("P06T bounded results schema"))?;
        result.validate_p06t()?;Ok(result)
    }
    fn validate_inner(&self,mixed:bool)->io::Result<()> {
        if self.arena_id==0||self.arena_id>i64::MAX as u64||![1,4].contains(&self.arena_type_id)
            ||self.created_unix==0||self.winner_team>2||!(1..=5).contains(&self.finish_reason)
            ||self.duration_seconds>3600||!(2..=MAX_PARTICIPANTS).contains(&self.participants.len()) {
            return Err(bad("lifecycle result header bound"));
        }
        for (index,p) in self.participants.iter().enumerate() {
            if p.vehicle_id==0||p.vehicle_id>i32::MAX as u32||p.account_dbid<=0||!(1..=2).contains(&p.team)
                ||p.type_compact_descr==0||p.type_compact_descr>i32::MAX as u32
                ||!(0..=10000).contains(&p.health)||p.shots>192||p.direct_hits>192||p.piercings>192
                ||p.damage_dealt>60000||p.damage_received>10000||p.kills>6
                ||p.capture_points>600||p.dropped_capture_points>600||p.mileage_metres>200000
                ||p.life_time>self.duration_seconds||p.killer_id>i32::MAX as u32
                ||!(-1..=10).contains(&p.death_reason)||p.name.is_empty()||p.name.len()>48
                ||p.name.chars().any(|c|c.is_control())
                ||!mixed&&p.health>0&&(p.death_reason!=-1||p.killer_id!=0)
                ||mixed&&p.death_reason==-1&&p.killer_id!=0
                ||p.health==0&&p.death_reason<0
                ||p.killer_id!=0&&!self.participants.iter().any(|q|q.vehicle_id==p.killer_id)
                ||self.participants[..index].iter().any(|q|q.vehicle_id==p.vehicle_id||q.account_dbid==p.account_dbid) {
                return Err(bad("lifecycle result participant bound"));
            }
        }
        if ![1,2].into_iter().all(|team|self.participants.iter().any(|p|p.team==team)) {
            return Err(bad("lifecycle result requires both teams"));
        }
        Ok(())
    }
}

// Original battle_results_shared.pyc order: CELL_PUBLIC36 + BASE_PUBLIC5.
const PUBLIC_FIELDS:[&str;41]=[
    "health","credits","xp","achievementCredits","achievementXP","achievementFreeXP",
    "shots","directHits","directTeamHits","explosionHits","piercings","damageDealt",
    "sniperDamageDealt","damageAssistedRadio","damageAssistedTrack","damageReceived",
    "damageBlockedByArmor","directHitsReceived","noDamageDirectHitsReceived","explosionHitsReceived",
    "piercingsReceived","spotted","damaged","kills","tdamageDealt","tkills","isTeamKiller",
    "capturePoints","droppedCapturePoints","mileage","lifeTime","killerID","achievements",
    "potentialDamageReceived","isPrematureLeave","fortResource","accountDBID","team",
    "typeCompDescr","gold","deathReason",
];
const PRIVATE_FIELDS:[&str;8]=["repair","freeXP","details","xpPenalty","creditsPenalty",
    "creditsContributionIn","creditsContributionOut","creditsToDraw"];
const UPDATE_FIELDS:[&str;28]=["tmenXP","isPremium","eventCredits","eventGold","eventXP",
    "eventFreeXP","eventTMenXP","autoRepairCost","autoLoadCost","autoEquipCost","histAmmoCost",
    "premiumXPFactor10","premiumCreditsFactor10","dailyXPFactor10","igrXPFactor10","aogasFactor10",
    "markOfMastery","dossierPopUps","vehTypeLockTime","serviceProviderID","marksOnGun",
    "movingAvgDamage","damageRating","orderCredits","orderXP","orderTMenXP","orderFreeXP","orderFortResource"];
const FINAL_FIELDS:[&str;4]=["originalCredits","originalXP","originalFreeXP","questsProgress"];

fn field(out:&mut Vec<u8>,name:&str,p:&Participant) {
    // Zero economy, empty medals/quests and unavailable ancillary statistics are
    // explicit P08C test policy, not historical rewards or imported server code.
    let value=match name {
        "health"=>p.health as i64,"shots"=>p.shots as i64,"directHits"=>p.direct_hits as i64,
        "piercings"=>p.piercings as i64,"damageDealt"=>p.damage_dealt as i64,
        "damageReceived"=>p.damage_received as i64,"kills"=>p.kills as i64,
        "capturePoints"=>p.capture_points as i64,"droppedCapturePoints"=>p.dropped_capture_points as i64,
        "mileage"=>p.mileage_metres as i64,"lifeTime"=>p.life_time as i64,"killerID"=>p.killer_id as i64,
        "accountDBID"=>p.account_dbid as i64,"team"=>p.team as i64,
        "typeCompDescr"=>p.type_compact_descr as i64,"deathReason"=>p.death_reason as i64,
        "premiumXPFactor10"|"premiumCreditsFactor10"|"dailyXPFactor10"|"igrXPFactor10"|"aogasFactor10"=>10,
        "achievements"|"dossierPopUps"=>{out.push(b']');return;},
        "details"=>{bytes(out,&[]);return;},
        "questsProgress"=>{out.push(b'}');return;},
        "autoLoadCost"|"autoEquipCost"|"histAmmoCost"=>{out.extend([b']',b'(',b'K',0,b'K',0,b'e']);return;},
        "isPremium"|"isTeamKiller"=>{boolean(out,false);return;},
        "isPrematureLeave"=>{boolean(out,p.premature_leave);return;},
        _=>0,
    };integer(out,value);
}
fn row(out:&mut Vec<u8>,p:&Participant,personal:bool) {
    out.extend([b']',b'(']);for name in PUBLIC_FIELDS {field(out,name,p);}
    if personal {for name in PRIVATE_FIELDS.into_iter().chain(UPDATE_FIELDS).chain(FINAL_FIELDS){field(out,name,p);}}
    out.push(b'e');
}

/// Compact outer tuple: arenaID, personal81, pickle((common9,players,vehicles)).
/// No GLOBAL/REDUCE/OBJ/INST or arbitrary serializer is exposed.
pub fn compact_results(result:&Results,own_account:i32)->io::Result<Vec<u8>> {
    compact_results_inner(result,own_account,false)
}
pub fn compact_results_p06t(result:&Results,own_account:i32)->io::Result<Vec<u8>>{
    compact_results_inner(result,own_account,true)
}
fn compact_results_inner(result:&Results,own_account:i32,mixed:bool)->io::Result<Vec<u8>>{
    if mixed{result.validate_p06t()?;}else{result.validate()?;}
    let own=result.participants.iter().find(|p|p.account_dbid==own_account)
        .ok_or_else(||bad("lifecycle result owner absent"))?;
    let mut shared=vec![0x80,2,b'(',b']',b'('];
    for value in [result.arena_type_id as i64,result.created_unix as i64,result.winner_team as i64,
        result.finish_reason as i64,result.duration_seconds as i64,2,2,0,0] {integer(&mut shared,value);}
    shared.extend([b'e',b'}',b'(']);
    for p in &result.participants {
        integer(&mut shared,p.account_dbid as i64);shared.extend([b']',b'(']);
        bytes(&mut shared,p.name.as_bytes());integer(&mut shared,0);bytes(&mut shared,b"");
        for value in [0,p.team as i64,0] {integer(&mut shared,value);}
        shared.push(b'e');
    }
    shared.extend([b'u',b'}',b'(']);
    for p in &result.participants {integer(&mut shared,p.vehicle_id as i64);row(&mut shared,p,false);}
    shared.extend(b"ut.");
    let mut out=vec![0x80,2];integer(&mut out,result.arena_id as i64);row(&mut out,own,true);
    bytes(&mut out,&shared);out.extend([0x87,b'.']);
    if out.len()>MAX_RESULT_BYTES{return Err(bad("lifecycle compact result size"));}Ok(out)
}
pub fn avatar_result_stream(result:&Results,own_account:i32)->io::Result<Vec<Vec<u8>>> {
    let raw=compact_results(result,own_account)?;
    crate::hangar091::stream_with_budget(AVATAR_RESULTS_STREAM,&raw,Vec::new(),MAX_RESULT_BYTES)
}
pub fn avatar_result_stream_p06t(result:&Results,own_account:i32)->io::Result<Vec<Vec<u8>>>{
    let raw=compact_results_p06t(result,own_account)?;
    crate::hangar091::stream_with_budget(AVATAR_RESULTS_STREAM,&raw,Vec::new(),MAX_RESULT_BYTES)
}
pub fn account_result_stream_p06t(request_id:i16,first:Vec<u8>,result:&Results,own_account:i32)->io::Result<Vec<Vec<u8>>>{
    if request_id<=0{return Err(bad("P06T result request ID"));}
    let raw=compact_results_p06t(result,own_account)?;
    crate::hangar091::stream_with_budget(request_id,&raw,first,MAX_RESULT_BYTES)
}
/// Caller provides its existing authenticated RES_STREAM response prefix.
pub fn account_result_stream(request_id:i16,first:Vec<u8>,result:&Results,own_account:i32)
    ->io::Result<Vec<Vec<u8>>> {
    if request_id<=0{return Err(bad("lifecycle result request ID"));}
    let raw=compact_results(result,own_account)?;
    crate::hangar091::stream_with_budget(request_id,&raw,first,MAX_RESULT_BYTES)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[derive(Debug,PartialEq)]
    enum Data {Int(i64),Bool(bool),Bytes(Vec<u8>),List(Vec<Data>),Tuple(Vec<Data>),Dict(Vec<(Data,Data)>),Mark}
    // Independent, deliberately tiny reader of this test's inert output. No
    // object constructors/imports, memo, incoming client data or production use.
    fn inert(raw:&[u8])->Data {
        assert!(raw.len()<32768);assert_eq!(&raw[..2],&[128,2]);let mut at=2;let mut stack=Vec::new();
        while at<raw.len() {let op=raw[at];at+=1;match op {
            b'K'=>{stack.push(Data::Int(raw[at] as i64));at+=1;},
            b'J'=>{stack.push(Data::Int(i32::from_le_bytes(raw[at..at+4].try_into().unwrap()) as i64));at+=4;},
            0x8a=>{assert_eq!(raw[at],8);at+=1;stack.push(Data::Int(i64::from_le_bytes(raw[at..at+8].try_into().unwrap())));at+=8;},
            b'U'|b'T'=>{let n=if op==b'U'{let n=raw[at] as usize;at+=1;n}else{let n=u32::from_le_bytes(raw[at..at+4].try_into().unwrap()) as usize;at+=4;n};
                stack.push(Data::Bytes(raw[at..at+n].to_vec()));at+=n;},
            0x88|0x89=>stack.push(Data::Bool(op==0x88)),b'('=>stack.push(Data::Mark),
            b']'=>stack.push(Data::List(Vec::new())),b'}'=>stack.push(Data::Dict(Vec::new())),
            b'e'|b'u'|b't'=>{let mark=stack.iter().rposition(|x|matches!(x,Data::Mark)).unwrap();
                let values=stack.split_off(mark+1);assert_eq!(stack.pop(),Some(Data::Mark));
                if op==b'e'{let Some(Data::List(list))=stack.last_mut()else{panic!("list expected")};list.extend(values);}
                else if op==b'u'{assert_eq!(values.len()%2,0);let Some(Data::Dict(dict))=stack.last_mut()else{panic!("dict expected")};
                    let mut values=values.into_iter();while let Some(key)=values.next(){dict.push((key,values.next().unwrap()));}}
                else{stack.push(Data::Tuple(values));}},
            0x86|0x87=>{let n=if op==0x86{2}else{3};let values=stack.split_off(stack.len()-n);stack.push(Data::Tuple(values));},
            b'.'=>{assert_eq!(at,raw.len());assert_eq!(stack.len(),1);return stack.pop().unwrap();},
            _=>panic!("unpermitted inert opcode {op}"),
        }}panic!("no STOP")
    }
    fn list(data:&Data)->&[Data] {let Data::List(items)=data else{panic!("expected list")};items}
    fn tuple(data:&Data)->&[Data] {let Data::Tuple(items)=data else{panic!("expected tuple")};items}
    #[test] fn original_lifecycle_literals_and_afterbattle_additional_info() {
        assert_eq!(base_captured(2,0).unwrap(),[19,88,10,9,8,128,2,75,2,75,0,134,46]);
        assert_eq!(base_points(1,0,99,true).unwrap(),[19,88,14,8,12,128,2,40,75,1,75,0,75,99,136,116,46]);
        let p=period(Period::Afterbattle,1040.,10.,Some((2,1))).unwrap();
        assert_eq!(&p[p.len()-7..],&[75,2,75,1,134,116,46]);
        assert!(period(Period::Afterbattle,100.,10.,None).is_err());
        assert!(period(Period::Battle,100.,10.,Some((2,1))).is_err());
        assert!(period(Period::Battle,f64::NAN,10.,None).is_err());
        for bad in [0,3,255] {assert!(base_captured(bad,0).is_err());}
        assert!(base_points(1,0,101,false).is_err());assert!(vehicle_killed(0,0,0).is_err());
    }
    fn result()->Results {
        Results {arena_id:0x1_0000_0001,arena_type_id:4,created_unix:1792080000,winner_team:1,
            finish_reason:1,duration_seconds:75,participants:vec![
                Participant {vehicle_id:0x09100003,account_dbid:1,name:"owner_1".into(),team:1,type_compact_descr:17,
                    health:90,shots:3,direct_hits:3,piercings:3,damage_dealt:90,kills:1,life_time:75,death_reason:-1,..Default::default()},
                Participant {vehicle_id:0x09100005,account_dbid:2,name:"Танкист_Ёж".into(),team:2,type_compact_descr:17,
                    health:0,shots:2,damage_received:90,life_time:74,killer_id:0x09100003,death_reason:0,..Default::default()},
            ]}
    }
    #[test] fn bound_result_owner_and_complete_field_count() {
        let r=result();let raw=compact_results(&r,1).unwrap();
        assert_eq!(&raw[..4],&[128,2,138,8]);assert!(raw.ends_with(&[135,46]));
        assert_eq!(PUBLIC_FIELDS.len()+PRIVATE_FIELDS.len()+UPDATE_FIELDS.len()+FINAL_FIELDS.len(),81);
        assert_ne!(raw,compact_results(&r,2).unwrap());assert!(compact_results(&r,3).is_err());
        let mut invalid=r.clone();invalid.arena_id=u64::MAX;assert!(compact_results(&invalid,1).is_err());
        invalid=r.clone();invalid.participants[1].account_dbid=1;assert!(compact_results(&invalid,1).is_err());
        invalid=r.clone();invalid.participants[1].team=1;assert!(compact_results(&invalid,1).is_err());
        invalid=r.clone();invalid.participants[1].name.push('\0');assert!(compact_results(&invalid,1).is_err());
        assert_eq!(serde_json::from_slice::<Results>(&serde_json::to_vec(&r).unwrap()).unwrap(),r);
        let mut unknown=serde_json::to_value(&r).unwrap();unknown["client_winner"]=true.into();
        assert!(serde_json::from_value::<Results>(unknown).is_err());
        let encoded=String::from_utf8(serde_json::to_vec(&r).unwrap()).unwrap();
        let duplicate=encoded.replacen("{","{\"arena_id\":7,",1);
        assert!(serde_json::from_str::<Results>(&duplicate).is_err());
        let mut too_many=serde_json::to_value(&r).unwrap();
        let rows=too_many["participants"].as_array_mut().unwrap();
        while rows.len()<=MAX_PARTICIPANTS {rows.push(rows[0].clone());}
        assert!(serde_json::from_value::<Results>(too_many).is_err());
    }
    #[test] fn original_stream_100_and_account_request_scopes_are_distinct() {
        let r=result();let avatar=avatar_result_stream(&r,1).unwrap();
        assert_eq!(&avatar[0][..5],&[52,17,0,100,0]);
        let account=account_result_stream(221,vec![19,77],&r,1).unwrap();
        assert_eq!(&account[0][..7],&[19,77,52,17,0,221,0]);
        assert!(avatar.iter().all(|body|body.len()<=512));
        assert!(account_result_stream(0,vec![],&r,1).is_err());
    }
    #[test] fn complete_inert_compact_tuple_keeps_authoritative_values_and_native_container_types() {
        let result=result();let root=inert(&compact_results(&result,2).unwrap());let outer=tuple(&root);
        assert_eq!(outer.len(),3);assert_eq!(outer[0],Data::Int(0x1_0000_0001));
        let personal=list(&outer[1]);assert_eq!(personal.len(),81);
        let fields=PUBLIC_FIELDS.into_iter().chain(PRIVATE_FIELDS).chain(UPDATE_FIELDS).chain(FINAL_FIELDS).collect::<Vec<_>>();
        let get=|name|&personal[fields.iter().position(|f|*f==name).unwrap()];
        assert_eq!(get("accountDBID"),&Data::Int(2));assert_eq!(get("team"),&Data::Int(2));
        assert_eq!(get("health"),&Data::Int(0));assert_eq!(get("damageReceived"),&Data::Int(90));
        assert_eq!(get("killerID"),&Data::Int(0x09100003));assert_eq!(get("deathReason"),&Data::Int(0));
        assert_eq!(get("details"),&Data::Bytes(vec![]));assert_eq!(get("questsProgress"),&Data::Dict(vec![]));
        assert_eq!(get("autoLoadCost"),&Data::List(vec![Data::Int(0),Data::Int(0)]));
        assert_eq!(get("isPremium"),&Data::Bool(false));assert_eq!(get("premiumCreditsFactor10"),&Data::Int(10));
        let Data::Bytes(shared)=&outer[2]else{panic!("compact shared bytes")};
        let shared=inert(shared);let shared=tuple(&shared);assert_eq!(shared.len(),3);
        let common=list(&shared[0]);assert_eq!(common.len(),9);assert_eq!(&common[2..5],&[Data::Int(1),Data::Int(1),Data::Int(75)]);
        let Data::Dict(players)=&shared[1]else{panic!("players")};assert_eq!(players.len(),2);
        assert_eq!(list(&players[1].1).len(),6);
        let Data::Dict(vehicles)=&shared[2]else{panic!("vehicles")};assert_eq!(vehicles.len(),2);
        assert!(vehicles.iter().all(|(_,row)|list(row).len()==41));
        assert_eq!(list(&vehicles[0].1)[11],Data::Int(90));assert_eq!(list(&vehicles[0].1)[23],Data::Int(1));
    }
}
