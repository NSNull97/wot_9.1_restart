//! Opt-in training-only Finished receipts. This queue does not verify ownership:
//! the adapter must first match the real immutable worker Task and strict reply.
use std::{collections::VecDeque,io};
use crate::training091::domain::{Account,BattleKey,FinishedRef};

fn bad(message:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,message)}
#[derive(Clone,Debug,PartialEq,Eq)]
struct Key{owner:Account,reservation:String,battle:BattleKey}
#[derive(Clone,Default)]
pub(super) struct FinishedEvents{
    battle:Option<BattleKey>,seen:Vec<Key>,pending:VecDeque<FinishedRef>,
}
impl FinishedEvents{
    pub(super) fn battle(&self)->Option<BattleKey>{self.battle}
    /// Host calls only after committing a new launch and settling the previous
    /// Registry's claims. Draining the queue alone is not proof of settlement.
    /// Re-arming the SAME battle preserves tombstones; no replay becomes fresh.
    pub(super) fn begin(&mut self,battle:BattleKey)->io::Result<()>{
        if battle.0==0||battle.0>i64::MAX as u64{return Err(bad("training Finished battle"));}
        if self.battle==Some(battle){return Ok(());}
        if !self.pending.is_empty(){return Err(bad("training Finished queue must drain before next battle"));}
        self.battle=Some(battle);self.seen.clear();Ok(())
    }
    /// Pure preflight: caller installs this staged clone ONLY after successful
    /// transactional Session delivery. Failure never consumes a writer receipt.
    pub(super) fn staged(&self,owner:Account,reservation:&str,battle:BattleKey)->io::Result<Self>{
        if owner.0==[0;16]||self.battle!=Some(battle){return Err(bad("training Finished foreign or unarmed battle"));}
        let key=Key{owner,reservation:reservation.into(),battle};
        if self.seen.contains(&key){return Ok(self.clone());}
        if self.seen.iter().any(|k|k.owner==owner||k.reservation==reservation){return Err(bad("training Finished conflicting owner/reservation"));}
        if self.seen.len()>=6||self.pending.len()>=6{return Err(bad("training Finished capacity"));}
        let receipt=FinishedRef::from_verified_writer(owner,reservation.into(),battle)
            .map_err(|_|bad("training Finished reference shape"))?;
        let mut next=self.clone();next.seen.push(key);next.pending.push_back(receipt);Ok(next)
    }
    pub(super) fn take(&mut self)->Option<FinishedRef>{self.pending.pop_front()}
}

/// Existing Profile UUID converted only after real worker/Task identity checks.
/// This shape check is not authentication or proof of a durable transaction.
pub(super) fn account(value:&str)->io::Result<Account>{
    if value.len()!=36{return Err(bad("training Finished UUID length"));}
    let mut out=[0u8;16];let mut n=0usize;let mut high=None;
    for(i,b)in value.bytes().enumerate(){
        if [8,13,18,23].contains(&i){if b!=b'-'{return Err(bad("training Finished UUID separators"));}continue;}
        let nibble=match b{b'0'..=b'9'=>b-b'0',b'a'..=b'f'=>b-b'a'+10,_=>return Err(bad("training Finished UUID alphabet"))};
        if let Some(h)=high.take(){out[n]=h*16+nibble;n+=1;}else{high=Some(nibble);}
    }
    if n!=16||high.is_some()||out==[0;16]{return Err(bad("training Finished UUID value"));}Ok(Account(out))
}

#[cfg(test)]#[path="profile13_finished_tests.rs"]mod tests;
