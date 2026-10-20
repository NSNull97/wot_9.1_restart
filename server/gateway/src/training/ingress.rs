//! P10B candidate only. Native method numbers stay here; domain gets typed
//! intent. No incoming pickle, ownership assumptions or client epoch fields.
use std::{collections::{BTreeSet,VecDeque},io};
pub const MAX_BODY:usize=512;
pub const MAX_RECORDS:usize=16;
pub const MAX_STRING:usize=64;
#[derive(Clone,Copy,Debug,Default,PartialEq,Eq)]pub enum Gate{#[default]Disabled,TrainingV1}
#[derive(Clone,Debug,PartialEq,Eq)]pub enum Error{Bound,Header,Truncated,Method,Shape,String,Request,Duplicate,Legacy,LegacyArity}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct ShortString(Vec<u8>);
impl ShortString{pub fn as_bytes(&self)->&[u8]{&self.0}}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Reply{JoinedOrFailure,ListStream,RosterStream,JoinEvent,Plain(i16)}
impl Reply{pub fn request_id(self)->Option<i16>{match self{Self::ListStream=>Some(200),Self::RosterStream=>Some(201),Self::Plain(id)=>Some(id),_=>None}}}
#[derive(Clone,Debug,PartialEq,Eq)]pub enum Kind{
    Create{arena_type:i32,seconds:i32,opened:bool,comment:ShortString},
    List{prebattle_type:i32,sort_key:i32,idle:bool,start:i32,end:i32},
    ListByCreator{prebattle_type:i64,idle:bool,mask:ShortString},Preview{room:i64},Join{room:i64},
    Leave,Ready{native_inventory:i64},NotReady{state:i64},Assign{account_entity:i64,roster:i32},
    SwapTeams,ChangeArena{arena_type:i64},ChangeDuration{seconds:i64},ChangeOpened{opened:bool},
    ChangeComment{comment:ShortString},ChangeVoip{mask:i64},
    TeamReady{team:i64,force:bool},TeamNotReady{team:i64},Kick{account_entity:i64},
}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct Request{pub reply:Reply,pub kind:Kind}
#[derive(Clone,Debug,PartialEq)]pub enum Incoming<T>{Legacy(T),Room(Request)}
fn i16at(b:&[u8],at:usize)->Result<i16,Error>{Ok(i16::from_le_bytes(b.get(at..at+2).ok_or(Error::Truncated)?.try_into().map_err(|_|Error::Shape)?))}
fn i32at(b:&[u8],at:usize)->Result<i32,Error>{Ok(i32::from_le_bytes(b.get(at..at+4).ok_or(Error::Truncated)?.try_into().map_err(|_|Error::Shape)?))}
fn i64at(b:&[u8],at:usize)->Result<i64,Error>{Ok(i64::from_le_bytes(b.get(at..at+8).ok_or(Error::Truncated)?.try_into().map_err(|_|Error::Shape)?))}
fn flag(value:i64)->Result<bool,Error>{match value{0=>Ok(false),1=>Ok(true),_=>Err(Error::Shape)}}
fn string(b:&[u8])->Result<ShortString,Error>{
    let len=usize::from(*b.first().ok_or(Error::Truncated)?);
    // No 0xff extended String path. Byte content stays opaque; UTF8/comment
    // policy is a semantic adapter decision, not invented source encoding.
    if len>MAX_STRING||b.len()!=len+1{return Err(Error::String);}Ok(ShortString(b[1..].to_vec()))
}
fn plain(id:i16)->Result<Reply,Error>{if id<221{return Err(Error::Request);}Ok(Reply::Plain(id))}
fn zeros(a:i64,b:i32,c:i32)->Result<(),Error>{if a!=0||b!=0||c!=0{Err(Error::Shape)}else{Ok(())}}
fn claimed_command(command:i16)->bool{matches!(command,400..=412|414|520|521|523)}

/// Exactly one complete VAR2 record. None means delegate the original packet
/// to the unchanged legacy parser; malformed claimed PRB records never fall back.
pub fn record(packet:&[u8])->Result<Option<Request>,Error>{
    if packet.len()<3{return Err(Error::Header);}
    let method=packet[0];let size=u16::from_le_bytes([packet[1],packet[2]])as usize;
    if packet.len()!=size+3{return Err(Error::Truncated);}let p=&packet[3..];
    if method==0x9a {
        if p.len()<10{return Err(Error::Shape);}
        return Ok(Some(Request{reply:Reply::JoinedOrFailure,kind:Kind::Create{
            arena_type:i32at(p,0)?,seconds:i32at(p,4)?,opened:flag(i64::from(p[8]))?,comment:string(&p[9..])?}}));
    }
    if p.len()<4{return Ok(None);}let id=i16at(p,0)?;let command=i16at(p,2)?;
    if !claimed_command(command){return Ok(None);}
    let request=match command{
        520=>{
            if method!=0x97{return Err(Error::Method);}if p.len()!=28||i32at(p,4)?!=5{return Err(Error::Shape);}if id!=200{return Err(Error::Request);}
            Request{reply:Reply::ListStream,kind:Kind::List{prebattle_type:i32at(p,8)?,sort_key:i32at(p,12)?,idle:flag(i64::from(i32at(p,16)?))?,start:i32at(p,20)?,end:i32at(p,24)?}}
        },
        521=>{
            if method!=0x96{return Err(Error::Method);}if p.len()<17{return Err(Error::Shape);}if id!=200{return Err(Error::Request);}
            Request{reply:Reply::ListStream,kind:Kind::ListByCreator{prebattle_type:i64at(p,4)?,idle:flag(i64::from(i32at(p,12)?))?,mask:string(&p[16..])?}}
        },
        409=>{
            if method!=0x95{return Err(Error::Method);}if p.len()<5{return Err(Error::Shape);}
            Request{reply:plain(id)?,kind:Kind::ChangeComment{comment:string(&p[4..])?}}
        },
        _=>{
            if method!=0x8e{return Err(Error::Method);}if p.len()!=20{return Err(Error::Shape);}
            let(a,b,c)=(i64at(p,4)?,i32at(p,12)?,i32at(p,16)?);
            if c!=0{return Err(Error::Shape);}
            let reply=match command{400=>{if id!=202{return Err(Error::Request);}Reply::JoinEvent},
                523=>{if id!=201{return Err(Error::Request);}Reply::RosterStream},_=>plain(id)?};
            let kind=match command{
                400=>{if b!=0{return Err(Error::Shape);}Kind::Join{room:a}},
                523=>{if b!=0{return Err(Error::Shape);}Kind::Preview{room:a}},
                401=>{zeros(a,b,c)?;Kind::Leave},402=>{if b!=0{return Err(Error::Shape);}Kind::Ready{native_inventory:a}},
                403=>{if b!=0{return Err(Error::Shape);}Kind::NotReady{state:a}},
                404=>Kind::Assign{account_entity:a,roster:b},405=>{zeros(a,b,c)?;Kind::SwapTeams},
                406=>{if b!=0{return Err(Error::Shape);}Kind::ChangeArena{arena_type:a}},
                407=>{if b!=0{return Err(Error::Shape);}Kind::ChangeDuration{seconds:a}},
                408=>{if b!=0{return Err(Error::Shape);}Kind::ChangeOpened{opened:flag(a)?}},
                410=>{if b!=0{return Err(Error::Shape);}Kind::ChangeVoip{mask:a}},
                411=>Kind::TeamReady{team:a,force:flag(i64::from(b))?},
                412=>{if b!=0{return Err(Error::Shape);}Kind::TeamNotReady{team:a}},
                414=>{if b!=0{return Err(Error::Shape);}Kind::Kick{account_entity:a}},
                _=>return Err(Error::Shape),
            };Request{reply,kind}
        },
    };Ok(Some(request))
}

/// Explicit opt-in shim. Legacy records are concatenated and decoded ONCE,
/// preserving the real legacy parser's cross-record invariants. Only after
/// complete parse/arity/namespace validation is a typed ordered Vec returned.
pub fn requests<T>(body:&[u8],gate:Gate,legacy:impl FnOnce(&[u8])->io::Result<Vec<T>>,
    legacy_id:impl Fn(&T)->Option<i16>)->Result<Vec<Incoming<T>>,Error>{
    if gate==Gate::Disabled{return legacy(body).map(|r|r.into_iter().map(Incoming::Legacy).collect()).map_err(|_|Error::Legacy);}
    if body.len()>MAX_BODY{return Err(Error::Bound);}
    let(mut cursor,mut slots,mut legacy_body,mut ids)=(0,Vec::new(),Vec::new(),BTreeSet::new());
    while cursor<body.len(){
        if slots.len()>=MAX_RECORDS||body.len()-cursor<3{return Err(Error::Bound);}
        let n=u16::from_le_bytes([body[cursor+1],body[cursor+2]])as usize;
        let end=cursor.checked_add(3+n).ok_or(Error::Bound)?;let packet=body.get(cursor..end).ok_or(Error::Truncated)?;
        let request=record(packet)?;
        if let Some(r)=&request{if let Some(id)=r.reply.request_id(){if !ids.insert(id){return Err(Error::Duplicate);}}}
        else{legacy_body.extend_from_slice(packet);}
        slots.push(request);cursor=end;
    }
    let mut old:VecDeque<T>=if legacy_body.is_empty(){VecDeque::new()}else{legacy(&legacy_body).map_err(|_|Error::Legacy)?.into()};
    if old.len()!=slots.iter().filter(|s|s.is_none()).count(){return Err(Error::LegacyArity);}
    for r in &old{if let Some(id)=legacy_id(r){if ids.contains(&id){return Err(Error::Duplicate);}}}
    let mut out=Vec::with_capacity(slots.len());for slot in slots{
        out.push(match slot{Some(r)=>Incoming::Room(r),None=>Incoming::Legacy(old.pop_front().ok_or(Error::LegacyArity)?)});
    }Ok(out)
}

#[cfg(test)]#[path="room_ingress_tests.rs"]mod tests;
