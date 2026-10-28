//! MM-01 queue and matching. Pure state: tickets (who waits, with which tier,
//! since when) and groups (who was matched into which arena battle, until when
//! the reservation lease holds). The gateway glue (`server_matchmaker.rs`) owns
//! sessions, Domain writers and arenas. The rules are explicit PROJECT policy,
//! not a reconstruction of the historical matchmaker.
use std::{io,time::{Duration,Instant}};

pub const POLICY:&str="project.mm01.queue-tier-window.v1";
/// Tickets the queue holds at once (the connection table holds at most 256).
pub const MAX_QUEUE:usize=1024;
const MAX_WAIT_SECONDS:u64=600;
const MAX_LEASE_SECONDS:u64=900;

fn bad(reason:&str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("matchmaker: {reason}"))}

/// Explicit gateway configuration of every arena's matching.
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Rules {pub team_size:usize,pub tiers:(u8,u8),pub tier_spread:u8,pub wait:Duration,pub lease:Duration}
impl Rules {
    /// Arena places: both teams; native players and bots together.
    pub fn places(&self)->usize {2*self.team_size}
    pub fn validate(&self,battle_players:usize)->io::Result<()> {
        let (lo,hi)=self.tiers;
        if self.team_size==0||self.places()!=battle_players||!(1..=10).contains(&lo)||!(lo..=10).contains(&hi)
            ||self.tier_spread>9||!(1..=MAX_WAIT_SECONDS).contains(&self.wait.as_secs())||self.wait.subsec_nanos()!=0
            ||self.lease<self.wait||self.lease>Duration::from_secs(MAX_LEASE_SECONDS)||self.lease.subsec_nanos()!=0 {return Err(bad("rules"));}
        Ok(())
    }
}

#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Ticket {pub session:u32,pub account:String,pub tier:u8,pub since:Instant}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Formed {Full,Timeout}
impl Formed {pub fn label(self)->&'static str {match self {Self::Full=>"full",Self::Timeout=>"timeout"}}}

#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Group {pub arena:usize,pub battle:u64,pub members:Vec<Ticket>,pub formed:Formed,pub leased_until:Instant,pub renewed:bool}
impl Group {
    pub fn has(&self,session:u32)->bool {self.members.iter().any(|t|t.session==session)}
    pub fn tiers(&self)->(u8,u8) {
        let lo=self.members.iter().map(|t|t.tier).min().unwrap_or(0);
        (lo,self.members.iter().map(|t|t.tier).max().unwrap_or(lo))
    }
}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Refusal {Tier,Duplicate,Full}

#[derive(Clone,Debug)]
pub struct Matchmaker {rules:Rules,queue:Vec<Ticket>,groups:Vec<Group>}
impl Matchmaker {
    pub fn new(rules:Rules)->Self {Self{rules,queue:Vec::new(),groups:Vec::new()}}
    pub fn rules(&self)->&Rules {&self.rules}
    pub fn queue(&self)->&[Ticket] {&self.queue}
    pub fn groups(&self)->&[Group] {&self.groups}
    pub fn queued(&self,session:u32)->bool {self.queue.iter().any(|t|t.session==session)}
    pub fn group_of(&self,session:u32)->Option<&Group> {self.groups.iter().find(|g|g.has(session))}
    /// One ticket per session and per account, across the queue and every group.
    pub fn enqueue(&mut self,ticket:Ticket)->Result<(),Refusal> {
        if !(self.rules.tiers.0..=self.rules.tiers.1).contains(&ticket.tier) {return Err(Refusal::Tier);}
        if self.queue.iter().chain(self.groups.iter().flat_map(|g|&g.members))
            .any(|t|t.session==ticket.session||t.account==ticket.account) {return Err(Refusal::Duplicate);}
        if self.queue.len()>=MAX_QUEUE {return Err(Refusal::Full);}
        self.queue.push(ticket);Ok(())
    }
    /// Cancel, disconnect or a refused writer: leaves the queue or its group.
    /// Returns the battle of the group it left.
    pub fn leave(&mut self,session:u32)->Option<u64> {
        self.queue.retain(|t|t.session!=session);
        let g=self.groups.iter_mut().find(|g|g.has(session))?;
        g.members.retain(|t|t.session!=session);Some(g.battle)
    }
    /// At most one group per free arena `(index, battle)`, in the given order.
    pub fn form(&mut self,free:&[(usize,u64)],now:Instant)->Vec<Group> {
        let mut formed=Vec::new();
        for &(arena,battle) in free {
            if self.groups.iter().any(|g|g.arena==arena||g.battle==battle) {continue;}
            let Some((picked,how))=self.pick(now) else {break;};
            let members=picked.iter().map(|i|self.queue[*i].clone()).collect::<Vec<_>>();
            self.queue=self.queue.iter().enumerate().filter(|(i,_)|!picked.contains(i)).map(|(_,t)|t.clone()).collect();
            let group=Group{arena,battle,members,formed:how,leased_until:now+self.rules.lease,renewed:false};
            self.groups.push(group.clone());formed.push(group);
        }
        formed
    }
    /// Oldest anchor first: FIFO tickets join while the group's tier range stays
    /// within `tier_spread`. Ready when full, or when its anchor waited `wait`.
    fn pick(&self,now:Instant)->Option<(Vec<usize>,Formed)> {
        let places=self.rules.places();
        for (anchor,a) in self.queue.iter().enumerate() {
            let (mut lo,mut hi)=(a.tier,a.tier);let mut picked=vec![anchor];
            for (i,t) in self.queue.iter().enumerate() {
                if picked.len()>=places {break;}
                if i==anchor||t.tier.max(hi)-t.tier.min(lo)>self.rules.tier_spread {continue;}
                lo=lo.min(t.tier);hi=hi.max(t.tier);picked.push(i);
            }
            picked.sort_unstable();
            if picked.len()==places {return Some((picked,Formed::Full));}
            if now.saturating_duration_since(a.since)>=self.rules.wait {return Some((picked,Formed::Timeout));}
        }
        None
    }
    /// The battle started: its members are arena participants, no longer matched.
    pub fn started(&mut self,battle:u64)->Option<Group> {self.dissolve(battle)}
    pub fn dissolve(&mut self,battle:u64)->Option<Group> {
        let index=self.groups.iter().position(|g|g.battle==battle)?;Some(self.groups.remove(index))
    }
    /// Unstarted groups whose reservation lease ran out.
    pub fn expired(&self,now:Instant)->Vec<u64> {self.groups.iter().filter(|g|now>=g.leased_until).map(|g|g.battle).collect()}
    /// First expiry with seated members: keep them, one more lease.
    pub fn renew(&mut self,battle:u64,keep:&[u32],now:Instant)->io::Result<()> {
        let lease=self.rules.lease;
        let g=self.groups.iter_mut().find(|g|g.battle==battle).ok_or_else(||bad("renew unknown group"))?;
        if g.renewed||keep.is_empty()||keep.iter().any(|s|!g.has(*s)) {return Err(bad("renew"));}
        g.members.retain(|t|keep.contains(&t.session));g.leased_until=now+lease;g.renewed=true;Ok(())
    }
}

/// Bot kinds for a group of tiers `(lo, hi)`: kinds within `[hi - spread, lo + spread]`
/// (the battle keeps the tolerance); none there: the kinds nearest to it (`true`).
pub fn bot_kinds<K:Copy>(group:(u8,u8),spread:u8,kinds:&[(K,u8)])->(Vec<K>,bool) {
    let (from,to)=(group.1.saturating_sub(spread),group.0.saturating_add(spread));
    let distance=|t:u8|if t<from {from-t} else {t.saturating_sub(to)};
    let near=kinds.iter().map(|(_,t)|distance(*t)).min().unwrap_or(0);
    (kinds.iter().filter(|(_,t)|distance(*t)==near).map(|(k,_)|*k).collect(),near>0)
}

#[cfg(test)]
#[path="matchmaker_tests.rs"]
mod tests;
