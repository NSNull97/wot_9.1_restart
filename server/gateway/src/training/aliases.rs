//! Candidate recipient aliases; no original/default protocol change. Each Book
//! belongs to one actual native Session until that Session is finally closed.
//! All tombstones and counters survive room/Account-return changes. No client
//! epoch is invented: membership generation is internal authoritative metadata.
use std::collections::BTreeSet;
pub const OWN_ENTITY_ID:u32=0x09100001;
pub const MAX_ALIASES:usize=512;
#[derive(Clone,Copy,Debug,PartialEq,Eq,PartialOrd,Ord)]pub struct Canonical{pub account:[u8;16],pub auth_generation:u64}
#[derive(Clone,Copy,Debug,PartialEq,Eq,PartialOrd,Ord)]pub struct Membership{pub canonical:Canonical,pub join_generation:u64}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub struct Binding{pub member:Membership,pub alias:u32}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Error{Identity,Room,Members,MissingOwn,Exhausted,StaleAlias,SelfTargetUnsupported}
pub type Result<T>=std::result::Result<T,Error>;
#[derive(Clone,Debug,PartialEq,Eq)]struct Entry{room:u64,member:Membership,alias:u32,active:bool}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct Book{recipient:Canonical,room:Option<u64>,own_membership:Option<u64>,entries:Vec<Entry>,allocated:u32}
fn valid(c:Canonical)->bool{c.account!=[0;16]&&c.auth_generation>0}
fn members(recipient:Canonical,current:&[Membership])->Result<Membership>{
    if current.is_empty()||current.len()>6{return Err(Error::Members);}let mut accounts=BTreeSet::new();let mut own=None;
    for m in current{if !valid(m.canonical)||m.join_generation==0||!accounts.insert(m.canonical.account){return Err(Error::Members);}if m.canonical==recipient{own=Some(*m);}}
    own.ok_or(Error::MissingOwn)
}
impl Book{
    pub fn new(recipient:Canonical)->Result<Self>{if !valid(recipient){return Err(Error::Identity);}Ok(Self{recipient,room:None,own_membership:None,entries:Vec::new(),allocated:0})}
    pub fn recipient(&self)->Canonical{self.recipient}
    pub fn allocated(&self)->usize{self.allocated as usize}
    /// Call on a clone while staging the SAME complete native view update;
    /// commit Book together with actual Session queues. Never clear/reset Book
    /// on room leave/rejoin or Account recreation within the same channel.
    pub fn stage_view(&mut self,room:u64,current:&[Membership])->Result<Vec<Binding>>{
        if room==0{return Err(Error::Room);}let own=members(self.recipient,current)?;let mut next=self.clone();
        // Own membership also matters: after the recipient leaves/rejoins, a
        // room's otherwise unchanged peer bindings must not be resurrected.
        let same_epoch=next.room==Some(room)&&next.own_membership==Some(own.join_generation);
        for e in &mut next.entries{e.active&=same_epoch&&e.room==room&&current.contains(&e.member);}
        let mut result=Vec::with_capacity(current.len());
        for member in current{
            let alias=if member.canonical==next.recipient{OWN_ENTITY_ID}else if let Some(e)=next.entries.iter().find(|e|e.active&&e.room==room&&e.member==*member){e.alias}else{
                if next.allocated as usize>=MAX_ALIASES{return Err(Error::Exhausted);}
                let allocated=next.allocated.checked_add(1).ok_or(Error::Exhausted)?;let alias=OWN_ENTITY_ID.checked_add(allocated).ok_or(Error::Exhausted)?;
                if alias>i32::MAX as u32{return Err(Error::Exhausted);}next.allocated=allocated;
                next.entries.push(Entry{room,member:*member,alias,active:true});alias
            };result.push(Binding{member:*member,alias});
        }
        next.room=Some(room);next.own_membership=Some(own.join_generation);*self=next;Ok(result)
    }
    /// Room-left only retires bindings. No alias may be allocated again until
    /// the native Session closes and this entire Book ceases to exist.
    pub fn leave_room(&mut self){for e in &mut self.entries{e.active=false;}self.room=None;self.own_membership=None;}
    /// Before translating404/414 use FRESH authoritative Registry membership,
    /// even if PLAYER_REMOVED has not yet fit the native publication window.
    pub fn resolve_peer(&self,room:u64,alias:u32,current:&[Membership])->Result<Membership>{
        let own=members(self.recipient,current)?;
        if self.room!=Some(room)||self.own_membership!=Some(own.join_generation){return Err(Error::StaleAlias);}
        // Fixed own ID cannot distinguish old own404 after room reuse; the
        // first candidate refuses it until reliable ordering is qualified.
        if alias==OWN_ENTITY_ID{return Err(Error::SelfTargetUnsupported);}
        let entry=self.entries.iter().find(|e|e.alias==alias&&e.active&&e.room==room).ok_or(Error::StaleAlias)?;
        if !current.contains(&entry.member){return Err(Error::StaleAlias);}Ok(entry.member)
    }
}

#[cfg(test)]#[path="aliases_tests.rs"]mod tests;
