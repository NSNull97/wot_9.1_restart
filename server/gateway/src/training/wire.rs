//! Outgoing native #717 P10B candidate. INFERRED static numeric IDs; native
//! dispatch/UI NOT_RUN. Inert primitive protocol2 ONLY; no incoming pickle.
//! Account/member/room IDs are adapter mappings, not domain physics identifiers.
use std::collections::{BTreeMap,BTreeSet,VecDeque};
pub const MAX_MEMBERS:usize=6;
pub const MAX_OUTBOX:usize=128;
pub const MAX_OUTBOX_BYTES:usize=65536;
pub const MAX_PAYLOAD:usize=254;
pub const SETTING_COUNT:usize=18;
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Error{Bound,Identity,Descriptor,Roster,Duplicate,MissingOwner,NoRecipient,QueueFull,Request,Settings}
pub type Result<T>=std::result::Result<T,Error>;
pub type Body=Vec<u8>;
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum PlayerState{Unknown,NotReady,Afk,Ready,InBattle,Offline}
impl PlayerState{fn value(self)->i32{match self{Self::Unknown=>0,Self::NotReady=>1,Self::Afk=>3,Self::Ready=>4,Self::InBattle=>8,Self::Offline=>16}}
    fn vehicle_specified(self)->bool{matches!(self,Self::Ready|Self::InBattle)}}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum TeamState{NotReady,Ready,Locked}
impl TeamState{fn value(self)->i32{match self{Self::NotReady=>1,Self::Ready=>2,Self::Locked=>3}}}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum SourceMap{Karelia,Prohorovka}
impl SourceMap{fn native(self)->i32{match self{Self::Karelia=>1,Self::Prohorovka=>4}}}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum CommandResult{Success,Failure,WrongArgs,Cooldown,Unavailable}
impl CommandResult{fn value(self)->i16{match self{Self::Success=>0,Self::Failure=>-1,Self::WrongArgs=>-2,Self::Cooldown=>-5,Self::Unavailable=>-10}}}
#[derive(Clone,Debug,PartialEq)]pub struct Member{
    pub entity_id:u32,pub database_id:i32,pub name:String,pub roster:u8,pub state:PlayerState,pub joined_seconds:f64,
    pub descriptor:Vec<u8>,pub igr_type:u8,pub clan_database_id:i32,pub clan_abbrev:String,
}
impl Member{
    fn validate(&self)->Result<()>{
        if self.entity_id==0||self.entity_id>i32::MAX as u32||self.database_id<=0||!(3..=24).contains(&self.name.chars().count())
            ||self.name.len()>48||self.name.chars().any(char::is_control)||!self.joined_seconds.is_finite()||!(0.0..=1e12).contains(&self.joined_seconds)
            ||self.igr_type>2||self.clan_database_id<0||self.clan_abbrev.len()>8||!self.clan_abbrev.is_ascii()||self.clan_abbrev.bytes().any(|b|b.is_ascii_control()){
            return Err(Error::Identity);}
        if ![1,2,17,18].contains(&self.roster){return Err(Error::Roster);}
        if self.descriptor.len()>64||self.state.vehicle_specified()&&self.descriptor.is_empty(){return Err(Error::Descriptor);}Ok(())
    }
}
#[derive(Clone,Debug,PartialEq)]pub struct RoomView{
    pub room_id:u32,pub creator_database_id:i32,pub map:SourceMap,pub seconds:u16,pub opened:bool,pub comment:String,
    pub members:Vec<Member>,pub team_states:[TeamState;2],
}
impl RoomView{
    fn validate(&self)->Result<()>{
        if self.room_id==0||self.room_id>i32::MAX as u32||self.creator_database_id<=0||!(60..=1800).contains(&self.seconds)
            ||self.comment.len()>64||self.comment.chars().any(char::is_control)||self.members.is_empty()||self.members.len()>MAX_MEMBERS{return Err(Error::Settings);}
        let mut entities=BTreeSet::new();let mut databases=BTreeSet::new();
        for m in &self.members{m.validate()?;if !entities.insert(m.entity_id)||!databases.insert(m.database_id){return Err(Error::Duplicate);}}
        if !databases.contains(&self.creator_database_id){return Err(Error::MissingOwner);}Ok(())
    }
}

// Closed primitive emitter, no GLOBAL/REDUCE/memo/object opcode surface. Bounds
// are enforced during writing as well as on the complete native VAR1 payload.
struct Pickle{bytes:Vec<u8>}
impl Pickle{
    fn new()->Self{Self{bytes:vec![0x80,2]}}
    fn raw(&mut self,b:&[u8])->Result<()>{if self.bytes.len()+b.len()>MAX_PAYLOAD{return Err(Error::Bound);}self.bytes.extend(b);Ok(())}
    fn byte(&mut self,b:u8)->Result<()>{self.raw(&[b])}
    fn integer(&mut self,n:i32)->Result<()>{if(0..=255).contains(&n){self.raw(&[b'K',n as u8])}else if(0..=65535).contains(&n){self.byte(b'M')?;self.raw(&(n as u16).to_le_bytes())}
        else{self.byte(b'J')?;self.raw(&n.to_le_bytes())}}
    fn boolean(&mut self,b:bool)->Result<()>{self.byte(if b{0x88}else{0x89})}
    fn string(&mut self,b:&[u8])->Result<()>{if b.len()>253{return Err(Error::Bound);}self.raw(&[b'U',b.len()as u8])?;self.raw(b)}
    fn unicode(&mut self,s:&str)->Result<()>{if s.len()>96{return Err(Error::Bound);}self.byte(b'X')?;self.raw(&(s.len()as u32).to_le_bytes())?;self.raw(s.as_bytes())}
    fn float(&mut self,n:f64)->Result<()>{if !n.is_finite(){return Err(Error::Bound);}self.byte(b'G')?;self.raw(&n.to_be_bytes())}
    fn tuple(&mut self,f:impl FnOnce(&mut Self)->Result<()>)->Result<()>{self.byte(b'(')?;f(self)?;self.byte(b't')}
    fn list(&mut self,f:impl FnOnce(&mut Self)->Result<()>)->Result<()>{self.raw(b"](")?;f(self)?;self.byte(b'e')}
    fn dict(&mut self,f:impl FnOnce(&mut Self)->Result<()>)->Result<()>{self.raw(b"}(")?;f(self)?;self.byte(b'u')}
    fn finish(mut self)->Result<Vec<u8>>{self.byte(b'.')?;Ok(self.bytes)}
}
fn update(code:u8,f:impl FnOnce(&mut Pickle)->Result<()>)->Result<Body>{
    if !(1..=11).contains(&code){return Err(Error::Bound);}let mut p=Pickle::new();f(&mut p)?;let raw=p.finish()?;
    let payload=1+1+raw.len();if payload>MAX_PAYLOAD||raw.len()>253{return Err(Error::Bound);}
    let mut body=vec![0x13,0x56,payload as u8,code,raw.len()as u8];body.extend(raw);Ok(body)
}
pub fn joined(room:u32)->Result<Body>{if room==0||room>i32::MAX as u32{return Err(Error::Bound);}let mut b=vec![0x13,0x46];b.extend(room.to_le_bytes());Ok(b)}
pub fn left()->Body{vec![0x13,0x3c]}
pub fn join_failure(source_code:u8)->Body{vec![0x13,0x42,source_code]}
pub fn kicked(source_code:u8)->Body{vec![0x13,0x44,source_code]}
/// #717 original prb callbacks take exactly THREE arguments. Never Ext0x4d.
pub fn plain_response(request:i16,result:CommandResult,error_code:&str)->Result<Body>{
    if request<=220{return Err(Error::Request);}if error_code.len()>64||!error_code.is_ascii()||error_code.bytes().any(|b|b.is_ascii_control()){return Err(Error::Bound);}
    let len=5+error_code.len();let mut b=vec![0x13,0x4c,len as u8];b.extend(request.to_le_bytes());b.extend(result.value().to_le_bytes());b.push(error_code.len()as u8);b.extend(error_code.as_bytes());Ok(b)
}
fn row(p:&mut Pickle,m:&Member)->Result<()>{p.tuple(|p|{
    p.integer(m.entity_id as i32)?;p.unicode(&m.name)?;p.integer(m.database_id)?;p.integer(i32::from(m.roster))?;p.integer(m.state.value())?;
    p.float(m.joined_seconds)?;p.string(&m.descriptor)?;p.integer(i32::from(m.igr_type))?;p.integer(m.clan_database_id)?;p.string(m.clan_abbrev.as_bytes())
})}
pub fn player_added(m:&Member)->Result<Body>{m.validate()?;update(2,|p|row(p,m))}
pub fn player_state(m:&Member)->Result<Body>{m.validate()?;update(4,|p|p.tuple(|p|{
    p.integer(m.entity_id as i32)?;p.integer(i32::from(m.roster))?;p.integer(m.state.value())?;p.string(&m.descriptor)?;
    p.integer(i32::from(m.igr_type))?;p.integer(m.clan_database_id)?;p.string(m.clan_abbrev.as_bytes())
}))}
pub fn player_removed(entity:u32,roster:u8)->Result<Body>{
    if entity==0||entity>i32::MAX as u32||![1,2,17,18].contains(&roster){return Err(Error::Roster);}
    update(3,|p|p.tuple(|p|{p.integer(entity as i32)?;p.integer(i32::from(roster))}))
}
pub fn roster_changed(entity:u32,old:u8,new:u8,actor:u32)->Result<Body>{
    if entity==0||entity>i32::MAX as u32||actor==0||actor>i32::MAX as u32||![1,2,17,18].contains(&old)||![1,2,17,18].contains(&new){return Err(Error::Roster);}
    update(5,|p|p.tuple(|p|{p.integer(entity as i32)?;p.integer(i32::from(old))?;p.integer(i32::from(new))?;p.integer(actor as i32)}))
}
pub fn team_states(states:[TeamState;2])->Result<Body>{update(6,|p|p.tuple(|p|{p.integer(states[0].value())?;p.integer(states[1].value())}))}
fn setting(name:&[u8],value:impl FnOnce(&mut Pickle)->Result<()>)->Result<Body>{update(8,|p|p.tuple(|p|{p.string(name)?;value(p)}))}
fn patches(room:&RoomView)->Result<Vec<Body>>{
    let creator=room.members.iter().find(|m|m.database_id==room.creator_database_id).ok_or(Error::MissingOwner)?;
    let b=vec![
        setting(b"arenaGuiType",|p|p.integer(2))?,setting(b"arenaTypeID",|p|p.integer(room.map.native()))?,
        setting(b"roundLength",|p|p.integer(i32::from(room.seconds)))?,setting(b"creator",|p|p.unicode(&creator.name))?,
        setting(b"creatorDBID",|p|p.integer(creator.database_id))?,setting(b"creatorClanDBID",|p|p.integer(creator.clan_database_id))?,
        setting(b"creatorClanAbbrev",|p|p.string(creator.clan_abbrev.as_bytes()))?,setting(b"creatorIGRType",|p|p.integer(i32::from(creator.igr_type)))?,
        setting(b"isOpened",|p|p.boolean(room.opened))?,setting(b"comment",|p|p.unicode(&room.comment))?,
        setting(b"defaultRoster",|p|p.integer(17))?,setting(b"roles",|p|p.dict(|p|{
            for m in &room.members{p.integer(m.database_id)?;p.integer(if m.database_id==room.creator_database_id{65151}else{96})?;}Ok(())
        }))?,setting(b"clanRoles",|p|p.dict(|_|Ok(())))?,setting(b"teamRoles",|p|p.dict(|p|{p.integer(1)?;p.integer(96)?;p.integer(2)?;p.integer(96)}))?,
        setting(b"limits",|p|p.dict(|p|{
            p.integer(0)?;p.dict(|p|{p.string(b"minCount")?;p.integer(1)?;p.string(b"maxCount")?;p.tuple(|p|{p.integer(3)?;p.integer(6)})})?;
            p.integer(1)?;p.dict(|_|Ok(()))?;p.integer(2)?;p.dict(|_|Ok(()))
        }))?,
        // Explicit candidate policy: creator departure destroys its one-shot
        // room after any outstanding reserve saga has actually been released.
        setting(b"destroyIfCreatorOut",|p|p.boolean(true))?,setting(b"arenaVoipChannels",|p|p.integer(0))?,
        setting(b"startIfReady",|p|p.boolean(false))?,
    ];if b.len()!=SETTING_COUNT{return Err(Error::Settings);}Ok(b)
}
/// Complete split initialization. Every setting precedes the first ROSTER,
/// because that ROSTER releases the original PrbInitFunctional factory barrier.
pub fn initialization(room:&RoomView,recipient:u32)->Result<Vec<Body>>{
    room.validate()?;let own=room.members.iter().find(|m|m.entity_id==recipient).ok_or(Error::NoRecipient)?;
    let mut result=vec![joined(room.room_id)?,update(7,|p|p.dict(|p|{p.string(b"type")?;p.integer(2)}))?];
    result.extend(patches(room)?);result.push(team_states(room.team_states)?);result.push(update(1,|p|p.list(|p|row(p,own)))?);
    for peer in &room.members{if peer.entity_id!=recipient{result.push(player_added(peer)?);}}
    if result.len()!=21+room.members.len(){return Err(Error::Settings);}Ok(result)
}
/// Synthetic bounded queue surface for testing complete-batch atomicity only.
/// Production must stage the Registry and ACTUAL affected Session clones and
/// preserve reliable sequence/ACK rules; this is not a replacement transport.
pub fn stage_initializations(outboxes:&mut BTreeMap<u32,VecDeque<Body>>,room:&RoomView)->Result<()>{
    room.validate()?;if outboxes.len()>MAX_MEMBERS{return Err(Error::Bound);}
    for q in outboxes.values(){
        if q.len()>MAX_OUTBOX||q.iter().try_fold(0usize,|sum,b|sum.checked_add(b.len())).is_none_or(|n|n>MAX_OUTBOX_BYTES){return Err(Error::QueueFull);}
    }
    let mut next=outboxes.clone();
    for member in &room.members{
        let bodies=initialization(room,member.entity_id)?;let queue=next.get_mut(&member.entity_id).ok_or(Error::NoRecipient)?;
        if queue.len()+bodies.len()>MAX_OUTBOX||queue.iter().map(Vec::len).sum::<usize>()+bodies.iter().map(Vec::len).sum::<usize>()>MAX_OUTBOX_BYTES{return Err(Error::QueueFull);}
        queue.extend(bodies);
    }*outboxes=next;Ok(())
}

#[cfg(test)]#[path="room_wire_tests.rs"]mod tests;
