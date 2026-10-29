//! MM-01 gateway glue. A native Join ("В бой") becomes a queue ticket; the
//! matcher puts tickets of a free arena into one group; the Domain admission
//! writer reserves a member's vehicle only in its matched battle; the lease
//! returns the reservations of a group that did not start in time. Without
//! `matchmaker` in the config none of this runs (fixed roster, old path).
use super::*;
use super::super::matchmaker::{self as mm,Matchmaker,Refusal,Ticket};
use super::super::profile13_session::MatchGate;
use crate::battle091::profile13::FinishReason;

/// `spent`: battles of dissolved groups. Their id is never matched again; the
/// arena resets to its next battle once nothing holds a reservation for it.
/// `published`: the last queue counts written to sessions and the log.
pub(super) struct Runtime {pub(super) mm:Matchmaker,bot_tiers:Vec<(VehicleKind,u8)>,spent:Vec<u64>,published:Option<mm::QueueStats>}

fn bad(reason:&str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,format!("MM-01: {reason}"))}
fn profile(s:&Session)->Option<&super::super::profile13_session::State> {s.shared.as_ref().and_then(|c|c.profile13.as_ref())}

/// Client tier and vehicle class of the selected owned vehicle (p04m inventory row; 1/2 are MS-1/IS-7).
fn selected_profile(s:&Session)->io::Result<Option<(u8,u8)>> {
    match s.queue_vehicle_kind() {Some(kind)=>kind.queue_profile(),None=>Ok(None)}
}
/// A hangar Join with no reservation, return, writer or arena place.
fn wants_queue(s:&Session,arenas:&[arena::Arena])->bool {
    s.active&&!s.arena_base&&s.shared.as_ref().is_some_and(|c|c.phase==Phase::Account&&c.join_requested&&c.contained_world.is_none())
        &&profile(s).is_some_and(|p|p.selection.is_some()&&!p.has_reservation()&&!p.has_pending_return()&&!p.in_flight)
        &&!arenas.iter().any(|a|a.has_session(s.id))
}
fn refuse(s:&mut Session,code:&str)->io::Result<()> {
    let c=s.shared.as_mut().ok_or_else(||bad("refuse without client"))?;
    c.join_requested=false;if let Some(p)=c.profile13.as_mut() {p.selection=None;}
    s.outbox.push_back(crate::battle091::profile13::enqueue_failure(code)?);Ok(())
}
/// The old homogeneous-denial return: a reservation goes back to Domain through
/// its cancel terminal; the native queue sees an enqueue failure.
fn cancel(s:&mut Session,world:&World)->io::Result<()> {
    if profile(s).is_some_and(|p|p.has_reservation()) {
        profile13_dispatch::Dispatcher::terminal(s,world,FinishReason::Cancelled)?;
    }
    let c=s.shared.as_mut().ok_or_else(||bad("cancel without client"))?;
    c.join_requested=false;c.queue_announced=false;
    if let Some(p)=c.profile13.as_mut() {p.selection=None;}
    if s.active {s.outbox.push_back(crate::battle091::profile13::enqueue_failure("BATTLE_BUSY")?);}
    Ok(())
}

impl Runtime {
    /// Every bot kind needs its client tier: the group's bots keep its tolerance.
    pub(super) fn new(rules:mm::Rules,plan:&model::bots::Plan)->io::Result<Self> {
        let bot_tiers=plan.kinds.iter().map(|k|k.tier()?.map(|t|(*k,t)).ok_or_else(||bad("bot kind without a client tier")))
            .collect::<io::Result<Vec<_>>>()?;
        Ok(Self{mm:Matchmaker::new(rules),bot_tiers,spent:Vec::new(),published:None})
    }
    pub(super) fn bot_tiers(&self)->&[(VehicleKind,u8)] {&self.bot_tiers}
    fn dissolve(&mut self,battle:u64,reason:&str) {
        if self.mm.dissolve(battle).is_some() {self.spent.push(battle);println!("MM01_GROUP_DISSOLVED battle={battle} reason={reason}");}
    }
    /// Arenas of dissolved groups that nobody holds a place or reservation in:
    /// the caller resets them (late/hold hooks, new battle id). Ids of arenas
    /// already reset elsewhere are forgotten.
    pub(super) fn take_resets(&mut self,table:&Table,arenas:&[arena::Arena],retired:&[Session])->Vec<usize> {
        self.spent.retain(|battle|arenas.iter().any(|a|a.world.id==*battle));
        let mut ready=Vec::new();
        self.spent.retain(|battle|{
            let Some(index)=arenas.iter().position(|a|a.world.id==*battle) else {return false;};
            let a=&arenas[index];
            // STAB-02: a closed arena is reopened by its own path, not here.
            let held=a.closed.is_some()||a.started()||!a.world.actors.is_empty()||table.sessions.iter().chain(retired)
                .any(|s|profile(s).is_some_and(|p|p.reservation_battle()==Some(*battle)));
            if !held {ready.push(index);}
            held
        });
        ready
    }
    /// Arenas the admission writer may serve this tick: the lobby (terminals)
    /// and every arena with an unstarted group.
    pub(super) fn admission_arenas(&self,arenas:&[arena::Arena],lobby:usize)->Vec<usize> {
        let mut targets=vec![lobby];
        for g in self.mm.groups() {
            if let Some(i)=arenas.iter().position(|a|a.world.id==g.battle) {if !targets.contains(&i) {targets.push(i);}}
        }
        targets
    }
    pub(super) fn tick(&mut self,table:&mut Table,arenas:&mut [arena::Arena],retired:&[Session],closed:impl Fn(u64)->bool,now:Instant)->io::Result<()> {
        self.settle_groups(table,arenas,now)?;
        self.sync_queue(table,arenas,now)?;
        self.expire(table,arenas,now)?;
        self.form(table,arenas,retired,closed,now)?;
        // Gate the admission writer: matched → that battle only; queued → none.
        // Waiting players get the queue counts for the native BattleQueue poll.
        let stats=self.mm.stats();
        for s in &mut table.sessions {
            let group=self.mm.group_of(s.id).map(|g|g.battle);
            let waiting=group.is_some()||self.mm.queued(s.id);
            if let Some(p)=s.shared.as_mut().and_then(|c|c.profile13.as_mut()) {
                p.match_gate=group.map_or(MatchGate::Queued,MatchGate::Matched);
                p.queue_classes=waiting.then_some(stats.classes);
            }
        }
        if self.published!=Some(stats) {
            self.published=Some(stats);
            println!("MM01_QUEUE_STATS classes={:?} class_order=light,medium,heavy,SPG,AT-SPG levels={:?} native=classes_only",stats.classes,stats.levels);
        }
        Ok(())
    }
    /// Started battles release their groups; members that cancelled, were
    /// refused by Domain or disconnected leave theirs (an empty group dissolves).
    fn settle_groups(&mut self,table:&Table,arenas:&mut [arena::Arena],now:Instant)->io::Result<()> {
        for g in self.mm.groups().to_vec() {
            let Some(index)=arenas.iter().position(|a|a.world.id==g.battle) else {
                self.mm.dissolve(g.battle);println!("MM01_GROUP_DISSOLVED battle={} reason=arena_reset",g.battle);continue;
            };
            if arenas[index].started() {
                self.mm.started(g.battle);
                let a=&arenas[index].world;
                println!("MM01_STARTED battle={} arena={index} humans={} bots={} waited_ms={}",g.battle,
                    a.actors.iter().filter(|x|x.bot.is_none()).count(),a.actors.iter().filter(|x|x.bot.is_some()).count(),
                    g.members.iter().map(|t|now.saturating_duration_since(t.since).as_millis()).max().unwrap_or(0));
                continue;
            }
            for t in &g.members {
                let live=table.sessions.iter().find(|s|s.id==t.session)
                    .is_some_and(|s|s.active&&s.shared.as_ref().is_some_and(|c|c.join_requested));
                if !live {self.mm.leave(t.session);println!("MM01_MEMBER_LEFT battle={} session={}",g.battle,t.session);}
            }
            let left=self.mm.groups().iter().find(|x|x.battle==g.battle).map_or(0,|x|x.members.len());
            if left==0 {self.dissolve(g.battle,"no_members");continue;}
            let world=&mut arenas[index].world;
            if left!=world.human_places()&&world.actors.len()<=left {
                let kinds=world.bot_plan().ok_or_else(||bad("arena without bots"))?.kinds.clone();
                let group=world.match_tiers().ok_or_else(||bad("matched arena without tiers"))?;
                world.set_match_roster(left,kinds,group)?;
            }
        }
        Ok(())
    }
    fn sync_queue(&mut self,table:&mut Table,arenas:&[arena::Arena],now:Instant)->io::Result<()> {
        let live=table.sessions.iter().map(|s|s.id).collect::<Vec<_>>();
        for t in self.mm.queue().to_vec() {
            if !live.contains(&t.session) {self.mm.leave(t.session);println!("MM01_DEQUEUED session={} reason=session_closed",t.session);}
        }
        for s in &mut table.sessions {
            if self.mm.group_of(s.id).is_some() {continue;}
            if !wants_queue(s,arenas) {
                if self.mm.queued(s.id) {self.mm.leave(s.id);println!("MM01_DEQUEUED session={} reason=cancel_or_busy",s.id);}
                continue;
            }
            if self.mm.queued(s.id)||s.outbox.len()>=125 {continue;}
            let account=s.identity.as_ref().ok_or_else(||bad("queue without identity"))?.account_id.clone();
            let Some((tier,class))=selected_profile(s)? else {
                refuse(s,"BATTLE_PROFILE_UNSUPPORTED")?;println!("MM01_REFUSED session={} reason=tier_unknown",s.id);continue;
            };
            match self.mm.enqueue(Ticket{session:s.id,account,tier,class,since:now}) {
                Ok(())=>{
                    let c=s.shared.as_mut().ok_or_else(||bad("queue without client"))?;
                    if !c.queue_announced {s.outbox.push_back(crate::map_drive_world091::queue_callback(true));}
                    c.queue_announced=true;
                    println!("MM01_QUEUED session={} tier={tier} queue={} policy={}",s.id,self.mm.queue().len(),mm::POLICY);
                },
                Err(refusal)=>{
                    let code=match refusal {Refusal::Tier=>"BATTLE_PROFILE_UNSUPPORTED",Refusal::Duplicate=>"VEHICLE_RESERVED",Refusal::Full=>"BATTLE_BUSY"};
                    refuse(s,code)?;println!("MM01_REFUSED session={} tier={tier} reason={refusal:?}",s.id);
                },
            }
        }
        Ok(())
    }
    /// Lease ran out before the start: members without an arena place return
    /// their reservations; seated ones keep the battle for one more lease
    /// (bots take the freed places). Second expiry or nobody seated: all return.
    fn expire(&mut self,table:&mut Table,arenas:&mut [arena::Arena],now:Instant)->io::Result<()> {
        for battle in self.mm.expired(now) {
            let group=self.mm.groups().iter().find(|g|g.battle==battle).cloned().ok_or_else(||bad("expired group"))?;
            let Some(index)=arenas.iter().position(|a|a.world.id==battle) else {self.dissolve(battle,"arena_reset");continue;};
            let seated=if group.renewed {Vec::new()} else {
                group.members.iter().map(|t|t.session).filter(|s|arenas[index].has_session(*s)).collect::<Vec<_>>()
            };
            for t in group.members.iter().filter(|t|!seated.contains(&t.session)) {
                if let Some(s)=table.sessions.iter_mut().find(|s|s.id==t.session) {cancel(s,&arenas[index].world)?;}
            }
            if seated.is_empty() {self.dissolve(battle,"lease_expired");}
            else {
                self.mm.renew(battle,&seated,now)?;
                let world=&mut arenas[index].world;
                let kinds=world.bot_plan().ok_or_else(||bad("arena without bots"))?.kinds.clone();
                let group=world.match_tiers().ok_or_else(||bad("matched arena without tiers"))?;
                world.set_match_roster(seated.len(),kinds,group)?;
            }
            println!("MM01_LEASE_EXPIRED battle={battle} members={} kept={} returned={} renewed={}",group.members.len(),seated.len(),
                group.members.len()-seated.len(),!seated.is_empty());
        }
        Ok(())
    }
    /// A free arena: not started, nobody seated, no reservation or group for its
    /// battle and its queue not closed by a finished admission.
    fn form(&mut self,table:&Table,arenas:&mut [arena::Arena],retired:&[Session],closed:impl Fn(u64)->bool,now:Instant)->io::Result<()> {
        if self.mm.queue().is_empty() {return Ok(());}
        let free=arenas.iter().enumerate().filter(|(_,a)|a.closed.is_none()&&!a.started()&&a.world.actors.is_empty()&&!closed(a.world.id)&&!self.spent.contains(&a.world.id)
            &&!table.sessions.iter().chain(retired).any(|s|profile(s).is_some_and(|p|p.reservation_battle()==Some(a.world.id))))
            .map(|(i,a)|(i,a.world.id)).collect::<Vec<_>>();
        for g in self.mm.form(&free,now) {
            let (kinds,nearest)=mm::bot_kinds(g.tiers(),self.mm.rules().tier_spread,&self.bot_tiers);
            let world=&mut arenas[g.arena].world;
            world.set_match_roster(g.members.len(),kinds.clone(),g.tiers())?;
            let (lo,hi)=g.tiers();
            println!("MM01_MATCHED battle={} arena={} humans={} bots={} tiers={lo}..{hi} formed={} waited_ms={} sessions={:?} bot_kinds={:?} lease_s={}",
                g.battle,g.arena,g.members.len(),world.expected_actors()-g.members.len(),g.formed.label(),
                g.members.iter().map(|t|now.saturating_duration_since(t.since).as_millis()).max().unwrap_or(0),
                g.members.iter().map(|t|t.session).collect::<Vec<_>>(),kinds.iter().map(|k|k.label()).collect::<Vec<_>>(),
                self.mm.rules().lease.as_secs());
            if nearest {println!("MM01_BOT_TIER_NEAREST battle={} tiers={lo}..{hi} spread={}",g.battle,self.mm.rules().tier_spread);}
        }
        Ok(())
    }
}
