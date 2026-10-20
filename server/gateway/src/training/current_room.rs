//! Explicit candidate policy: synchronous native actions address the room
//! authenticated at dispatch time. No client epoch or semantic-origin claim.
//! Authentication/writer/source provenance comes from existing real adapters.
use super::{adapter,aliases,domain};

pub const POLICY:&str="test_lab.p10b.current-room-at-receipt.v1";
#[derive(Clone,Debug,PartialEq,Eq)]
pub enum Error{Domain(domain::Error),Alias(aliases::Error),Identity,Request,StaleJob}
impl From<domain::Error>for Error{fn from(e:domain::Error)->Self{Self::Domain(e)}}
impl From<aliases::Error>for Error{fn from(e:aliases::Error)->Self{Self::Alias(e)}}
pub type Result<T>=std::result::Result<T,Error>;

/// Native parse happens separately. No arbitrary domain Create/Join/Ready can
/// be smuggled through this synchronous room-mutation entry point.
#[derive(Clone,Debug,PartialEq,Eq)]
pub enum Action{
    Assign{target_alias:u32,roster:domain::Roster},Kick{target_alias:u32},
    Leave,NotReady,SwapTeams,UpdateSettings(domain::Settings),
    TeamReady{side:domain::Side,ready:bool,force:bool},
}

/// Call synchronously from the NEW reliable record's staged Session/Registry.
/// The actual Session owns sequence/history/duplicate/piggyback validation.
/// Never save Action here to apply later against a different current room.
pub fn current(reg:&mut domain::Registry,book:&aliases::Book,who:domain::AuthLease,action:Action,now:u64)->Result<Vec<domain::Event>>{
    if book.recipient()!=adapter::canonical(who){return Err(Error::Identity);}
    let key=reg.authenticated_room(who)?;
    let command=match action{
        Action::Assign{target_alias,roster}=>{
            let target=if target_alias==aliases::OWN_ENTITY_ID{who.account}else{
                let members=reg.room(key).ok_or(domain::Error::NoRoom)?.members().map(|m|{
                    let(lease,join_generation)=reg.member_context(key,m.account()).ok_or(Error::Identity)?;
                    Ok(aliases::Membership{canonical:adapter::canonical(lease),join_generation})
                }).collect::<Result<Vec<_>>>()?;
                domain::Account(book.resolve_peer(key.0,target_alias,&members)?.canonical.account)
            };
            domain::Command::Assign{target,roster}
        },
        Action::Kick{target_alias}=>{
            if target_alias==aliases::OWN_ENTITY_ID{return Err(Error::Domain(domain::Error::NotCreator));}
            let members=reg.room(key).ok_or(domain::Error::NoRoom)?.members().map(|m|{
                let(lease,join_generation)=reg.member_context(key,m.account()).ok_or(Error::Identity)?;
                Ok(aliases::Membership{canonical:adapter::canonical(lease),join_generation})
            }).collect::<Result<Vec<_>>>()?;
            domain::Command::Kick(domain::Account(book.resolve_peer(key.0,target_alias,&members)?.canonical.account))
        },
        Action::Leave=>domain::Command::Leave,Action::NotReady=>domain::Command::NotReady,
        Action::SwapTeams=>domain::Command::SwapTeams,Action::UpdateSettings(s)=>domain::Command::UpdateSettings(s),
        Action::TeamReady{side,ready,force}=>domain::Command::TeamReady{side,ready,force},
    };
    // Actual creator, ready/side/capacity/phase/claim checks live in Registry.
    Ok(reg.command(who,command,now)?)
}

/// Existing authenticated native-channel incarnation, never a new client arg.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct Channel{pub session:u32,pub generation:u64}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct ProfileStamp{pub revision:u32,pub source_binding:[u8;32]}
fn valid(channel:Channel,profile:ProfileStamp)->bool{
    channel.session>0&&channel.generation>0&&(13..=i32::MAX as u32).contains(&profile.revision)&&profile.source_binding!=[0;32]
}

/// Immutable async query origin. The real dispatcher additionally retains its
/// exact command key/request/native DB/profile and immutable writer transport
/// request; shape checks here do NOT prove owned loadout readiness.
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct ReadyOrigin{
    caller:domain::AuthLease,channel:Channel,profile:ProfileStamp,room:domain::RoomKey,
    revision:u64,membership:u64,context:domain::ReadyContext,inventory:String,request:i16,
}
impl ReadyOrigin{
    /// inventory is resolved from the authenticated source projection, not from
    /// a caller-invented ownership string. Native request221..32767 is retained.
    pub fn capture(reg:&domain::Registry,caller:domain::AuthLease,channel:Channel,profile:ProfileStamp,
        inventory:String,request:i16)->Result<Self>{
        if !valid(channel,profile)||!(221..=i16::MAX).contains(&request)||inventory.is_empty()||inventory.len()>96
            ||!inventory.is_ascii()||inventory.bytes().any(|b|b.is_ascii_control()){return Err(Error::Request);}
        let room=reg.authenticated_room(caller)?;let revision=reg.room(room).ok_or(domain::Error::NoRoom)?.revision();
        let(lease,membership)=reg.member_context(room,caller.account).ok_or(Error::Identity)?;
        if lease!=caller{return Err(Error::Identity);}
        Ok(Self{caller,channel,profile,room,revision,membership,context:reg.selection_context(caller)?,inventory,request})
    }
    pub fn request(&self)->i16{self.request}
    /// Revalidate the originating room/revision/member/session/source, never
    /// reinterpret a delayed writer reply using current-room receipt policy.
    pub fn complete(&self,reg:&mut domain::Registry,caller:domain::AuthLease,channel:Channel,profile:ProfileStamp,
        ready:domain::WriterReadyRef,now:u64)->Result<Vec<domain::Event>>{
        if caller!=self.caller||channel!=self.channel||profile!=self.profile||!valid(channel,profile)
            ||ready.owner()!=caller.account||ready.inventory()!=self.inventory||ready.revision()!=self.profile.revision
            ||reg.authenticated_room(caller).ok()!=Some(self.room)
            ||reg.room(self.room).map(|r|r.revision())!=Some(self.revision)
            ||reg.member_context(self.room,caller.account)!=Some((self.caller,self.membership)){
            return Err(Error::StaleJob);
        }
        Ok(reg.command(caller,domain::Command::Ready{context:self.context,selection:ready},now)?)
    }
}

#[cfg(test)]#[path="current_room_tests.rs"]mod tests;
