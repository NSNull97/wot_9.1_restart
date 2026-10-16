//! Source-local P10B candidate. Fixed native stream reuse is transport delivery
//! only: no ACK implies UI consumption, historical origin or writer release.
use super::domain::{AuthLease,RoomKey};
pub const MAX_OUTBOX:usize=128;
/// Existing hangar stream: <=32768 raw bytes +11 zlib bytes, chunks400.
pub const MAX_BODIES:usize=82;
const MAX_SEQUENCE:u32=1_000_000;
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Kind{Listing,Preview}
impl Kind{fn index(self)->usize{match self{Self::Listing=>0,Self::Preview=>1}}pub fn stream_id(self)->i16{match self{Self::Listing=>200,Self::Preview=>201}}}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub struct Channel{pub session:u32,pub generation:u64}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum ReadRevision{Listing(u64),Preview{room:RoomKey,revision:u64}}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct StreamContext{
    caller:AuthLease,channel:Channel,kind:Kind,query:[u8;32],read:ReadRevision,
    profile_revision:u32,source_binding:[u8;32],
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Error{Context,Bound,Busy,Overlap,Sequence,Ack}
pub type Result<T>=std::result::Result<T,Error>;
impl StreamContext{
    /// Trusted authenticated/query metadata ONLY; shape checks cannot establish
    /// authorization, current Registry revision, or source projection provenance.
    pub fn capture(caller:AuthLease,channel:Channel,kind:Kind,query_fingerprint:[u8;32],
        read:ReadRevision,profile_revision:u32,source_binding:[u8;32])->Result<Self>{
        let c=Self{caller,channel,kind,query:query_fingerprint,read,profile_revision,source_binding};c.validate()?;Ok(c)
    }
    fn validate(&self)->Result<()>{
        if self.caller.account.0==[0;16]||self.caller.generation==0||self.channel.session==0||self.channel.generation==0
            ||self.query==[0;32]||self.source_binding==[0;32]||!(13..=i32::MAX as u32).contains(&self.profile_revision){return Err(Error::Context);}
        match(self.kind,self.read){(Kind::Listing,ReadRevision::Listing(_))=>{},
            (Kind::Preview,ReadRevision::Preview{room,revision})if room.0>0&&revision>0=>{},_=>return Err(Error::Context)}Ok(())
    }
    pub fn kind(&self)->Kind{self.kind}
    pub fn caller(&self)->AuthLease{self.caller}
    pub fn channel(&self)->Channel{self.channel}
    pub fn profile_revision(&self)->u32{self.profile_revision}
    /// Re-capture from CURRENT auth/channel/source/query/Registry facts before
    /// staging an async read result. Equality is an origin fence, not authority.
    pub fn matches_current(&self,current:&Self)->bool{self==current}
}
#[derive(Clone,Debug,PartialEq,Eq)]struct Stamp{sequence:u32,acked:bool}
#[derive(Clone,Debug,PartialEq,Eq)]struct Flight{context:StreamContext,ahead:usize,remaining:usize,total:usize,stamps:Vec<Stamp>}
#[derive(Clone,Debug,Default,PartialEq,Eq)]pub struct Flights{active:[Option<Flight>;2],last_enqueued:Option<u32>,cumulative:u32}
impl Flights{
    pub fn busy(&self,kind:Kind)->bool{self.active[kind.index()].is_some()}
    pub fn context(&self,kind:Kind)->Option<&StreamContext>{self.active[kind.index()].as_ref().map(|f|&f.context)}
    /// Call inside the SAME cloned Session transaction that appends ALL bounded
    /// response bodies. ahead is that clone's outbox.len() BEFORE append.
    /// On failure discard clone; no callback/output/Registry state is committed.
    pub fn stage(&mut self,context:StreamContext,ahead:usize,body_count:usize)->Result<()>{
        context.validate()?;
        if body_count==0||body_count>MAX_BODIES||ahead.checked_add(body_count).is_none_or(|n|n>MAX_OUTBOX){return Err(Error::Bound);}
        let slot=context.kind.index();if self.active[slot].is_some(){return Err(Error::Busy);}
        let end=ahead+body_count;
        for old in self.active.iter().flatten(){
            if old.remaining>0&&ahead<old.ahead+old.remaining&&old.ahead<end{return Err(Error::Overlap);}
        }
        self.active[slot]=Some(Flight{context,ahead,remaining:body_count,total:body_count,stamps:Vec::with_capacity(body_count)});Ok(())
    }
    /// ONLY after successful actual Window.enqueue_body_tracked(front), once per
    /// outbox pop. Retry/due/direct-tx enqueue MUST NOT call this. Sequence0 valid.
    /// Even this metadata update is in the outer staged Session transaction.
    pub fn on_enqueued(&mut self,sequence:u32)->Result<()>{
        if sequence>=MAX_SEQUENCE||self.last_enqueued.is_some_and(|last|sequence<=last){return Err(Error::Sequence);}
        for f in self.active.iter_mut().flatten(){
            if f.ahead>0{f.ahead-=1;}
            else if f.remaining>0{f.stamps.push(Stamp{sequence,acked:false});f.remaining-=1;}
        }
        self.last_enqueued=Some(sequence);Ok(())
    }
    /// ONLY after actual Window.acknowledge(frame) succeeds. Pass its resulting
    /// monotone cumulative and that frame's selective list. It cannot validate
    /// ACK-of-unsent by itself. ALL body stamps must be delivered; last-only is
    /// unsafe for selective ACKs with earlier gaps.
    pub fn on_validated_ack(&mut self,cumulative:u32,selectives:&[u32])->Result<[Option<StreamContext>;2]>{
        if cumulative<self.cumulative||cumulative>MAX_SEQUENCE||selectives.len()>16||selectives.iter().any(|s|*s>=MAX_SEQUENCE){return Err(Error::Ack);}
        self.cumulative=cumulative;let mut done=[None,None];
        for(i,entry)in self.active.iter_mut().enumerate(){
            if let Some(f)=entry{
                for s in &mut f.stamps{s.acked|=cumulative>s.sequence||selectives.contains(&s.sequence);}
                if f.remaining==0&&f.stamps.len()==f.total&&f.stamps.iter().all(|s|s.acked){done[i]=Some(f.context.clone());*entry=None;}
            }
        }Ok(done)
    }
}
#[cfg(test)]#[path="stream_flight_tests.rs"]mod tests;
