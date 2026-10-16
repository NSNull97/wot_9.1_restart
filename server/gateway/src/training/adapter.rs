//! Ignored candidate adapter composition. No sockets, writer jobs, active
//! Session implementation or new client RPC fields. Types imported by harness.
use super::{aliases,domain,wire};
use std::collections::{BTreeMap,VecDeque};
#[derive(Clone,Debug,PartialEq)]pub enum Error{Domain(domain::Error),Alias(aliases::Error),Wire(wire::Error),Facts,Queue}
impl From<domain::Error>for Error{fn from(e:domain::Error)->Self{Self::Domain(e)}}
impl From<aliases::Error>for Error{fn from(e:aliases::Error)->Self{Self::Alias(e)}}
impl From<wire::Error>for Error{fn from(e:wire::Error)->Self{Self::Wire(e)}}
type Result<T>=std::result::Result<T,Error>;
pub fn canonical(who:domain::AuthLease)->aliases::Canonical{aliases::Canonical{account:who.account.0,auth_generation:who.generation}}
fn current_members(reg:&domain::Registry,key:domain::RoomKey)->Result<Vec<aliases::Membership>>{
    reg.room(key).ok_or(domain::Error::NoRoom)?.members().map(|m|{
        let(lease,join_generation)=reg.member_context(key,m.account()).ok_or(Error::Facts)?;
        Ok(aliases::Membership{canonical:canonical(lease),join_generation})
    }).collect()
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum TargetAction{Assign(domain::Roster),Kick}
/// Receives canonical authenticated caller from actual Session, never from the
/// native404/414 account argument. Resolve TARGET through this recipient's book
/// and fresh domain membership, then retain actual creator/domain checks.
pub fn target_command(reg:&mut domain::Registry,book:&aliases::Book,caller:domain::AuthLease,target_alias:u32,action:TargetAction,now:u64)->Result<Vec<domain::Event>>{
    if book.recipient()!=canonical(caller){return Err(Error::Alias(aliases::Error::Identity));}
    let key=reg.authenticated_room(caller)?;let room=reg.room(key).ok_or(domain::Error::NoRoom)?;
    if room.creator()!=caller.account{return Err(Error::Domain(domain::Error::NotCreator));}
    let current=current_members(reg,key)?;let target=book.resolve_peer(key.0,target_alias,&current)?;
    let account=domain::Account(target.canonical.account);
    let command=match action{TargetAction::Assign(roster)=>domain::Command::Assign{target:account,roster},TargetAction::Kick=>domain::Command::Kick(account)};
    Ok(reg.command(caller,command,now)?)
}
/// Trusted actual identity/owned-descriptor projection, supplied separately
/// from native input. Equality is binding only; it does not prove provenance.
#[derive(Clone,Debug,PartialEq)]pub struct NativeFacts{
    pub database_id:i32,pub selected:Option<domain::WriterReadyRef>,pub descriptor:Vec<u8>,
    pub igr_type:u8,pub clan_database_id:i32,pub clan_abbrev:String,
}
/// Initial holder creation only. Future in-room membership deltas must use
/// PLAYER_REMOVED/PLAYER_ADDED with the same staged Book, not reset Joined.
/// Candidate queue surface is synthetic; actual production must clone all
/// affected Sessions plus Registry and obey real reliable ACK/receive rules.
pub fn stage_room_view(reg:&domain::Registry,book:&mut aliases::Book,caller:domain::AuthLease,native_room_id:u32,
    facts:&BTreeMap<domain::Account,NativeFacts>,joined_seconds:f64)->Result<wire::RoomView>{
    if book.recipient()!=canonical(caller){return Err(Error::Alias(aliases::Error::Identity));}
    let key=reg.authenticated_room(caller)?;let room=reg.room(key).ok_or(domain::Error::NoRoom)?;
    let mut next=book.clone();let bindings=next.stage_view(key.0,&current_members(reg,key)?)?;let mut members=Vec::new();
    for m in room.members(){
        let context=reg.member_context(key,m.account()).ok_or(Error::Facts)?;let entry=bindings.iter().find(|b|b.member.canonical==canonical(context.0)&&b.member.join_generation==context.1).ok_or(Error::Facts)?;
        let f=facts.get(&m.account()).ok_or(Error::Facts)?;
        if f.selected.as_ref()!=m.ready(){return Err(Error::Facts);}
        let roster=m.roster();let code=match(roster.side,roster.assigned){(domain::Side::One,true)=>1,(domain::Side::Two,true)=>2,(domain::Side::One,false)=>17,(domain::Side::Two,false)=>18};
        members.push(wire::Member{entity_id:entry.alias,database_id:f.database_id,name:m.name().to_owned(),roster:code,
            state:if m.ready().is_some(){wire::PlayerState::Ready}else{wire::PlayerState::NotReady},joined_seconds,
            descriptor:if m.ready().is_some(){f.descriptor.clone()}else{Vec::new()},igr_type:f.igr_type,clan_database_id:f.clan_database_id,clan_abbrev:f.clan_abbrev.clone()});
    }
    let creator=facts.get(&room.creator()).ok_or(Error::Facts)?;let settings=room.settings();
    let states=if room.preparing().is_some(){[wire::TeamState::Locked;2]}else{room.team_ready().map(|b|if b{wire::TeamState::Ready}else{wire::TeamState::NotReady})};
    let view=wire::RoomView{room_id:native_room_id,creator_database_id:creator.database_id,map:match settings.map{domain::QualifiedMap::Karelia=>wire::SourceMap::Karelia,domain::QualifiedMap::Prohorovka=>wire::SourceMap::Prohorovka},
        seconds:settings.seconds,opened:settings.opened,comment:settings.comment.clone(),members,team_states:states};
    wire::validate_view(&view)?;*book=next;Ok(view)
}
pub fn stage_initialization(reg:&domain::Registry,book:&mut aliases::Book,caller:domain::AuthLease,native_room_id:u32,
    facts:&BTreeMap<domain::Account,NativeFacts>,joined_seconds:f64,outbox:&mut VecDeque<wire::Body>)->Result<()>{
    let mut next=book.clone();let view=stage_room_view(reg,&mut next,caller,native_room_id,facts,joined_seconds)?;
    let bodies=wire::initialization(&view,aliases::OWN_ENTITY_ID)?;
    let old_bytes=outbox.iter().try_fold(0usize,|sum,b|sum.checked_add(b.len())).ok_or(Error::Queue)?;
    if outbox.len()+bodies.len()>wire::MAX_OUTBOX||old_bytes+bodies.iter().map(Vec::len).sum::<usize>()>wire::MAX_OUTBOX_BYTES{return Err(Error::Queue);}
    outbox.extend(bodies);*book=next;Ok(())
}

#[cfg(test)]#[path="alias_adapter_tests.rs"]mod tests;
