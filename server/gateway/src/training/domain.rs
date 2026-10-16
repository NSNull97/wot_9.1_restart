//! P10B preparation ONLY: bounded authoritative room component, no native I/O.
//! Trust boundary: AuthLease comes from existing authentication; WriterReadyRef,
//! ReservedRef/ReleasedRef/FinishedRef come only from a separately verified
//! writer adapter. Their constructors check shape/binding, NOT ownership,
//! availability, ammunition, crew, source admission, or durable transactions.
//! No network decoder or substitute owned-loadout validator is provided here.
use std::collections::{BTreeMap,BTreeSet};

pub const POLICY:&str="test_lab.p10b.room-one-shot-six.v1";
pub const MAX_ROOMS:usize=4;
pub const MAX_ACCOUNTS:usize=24;
/// Per-Registry lifetime identity budget. Floors are never evicted or reused.
pub const MAX_GENERATIONS:usize=1024;
pub const MAX_MEMBERS:usize=6;
pub const MAX_SIDE:usize=3;

#[derive(Clone,Copy,Debug,PartialEq,Eq,PartialOrd,Ord)]pub struct Account(pub [u8;16]);
#[derive(Clone,Copy,Debug,PartialEq,Eq,PartialOrd,Ord)]pub struct RoomKey(pub u64);
#[derive(Clone,Copy,Debug,PartialEq,Eq,PartialOrd,Ord)]pub struct BattleKey(pub u64);
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub struct AuthLease{pub account:Account,pub generation:u64}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Side{One,Two}
impl Side{fn index(self)->usize{match self{Self::One=>0,Self::Two=>1}}fn other(self)->Self{match self{Self::One=>Self::Two,Self::Two=>Self::One}}}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub struct Roster{pub side:Side,pub assigned:bool}
impl Roster{pub fn assigned(side:Side)->Self{Self{side,assigned:true}}pub fn bench(side:Side)->Self{Self{side,assigned:false}}}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum QualifiedMap{Karelia,Prohorovka}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct Settings{pub capacity:u8,pub map:QualifiedMap,pub seconds:u16,pub opened:bool,pub comment:String}
impl Settings{
    fn validate(&self)->Result<()>{
        // Explicit test-lab limits; original server's room limits are UNKNOWN.
        if !(2..=6).contains(&self.capacity)||!(60..=1800).contains(&self.seconds)||self.comment.len()>64
            ||self.comment.chars().any(char::is_control){return Err(Error::BadSettings);}Ok(())
    }
}

#[derive(Clone,Debug,PartialEq,Eq)]pub struct WriterReadyRef{owner:Account,inventory:String,revision:u32,fingerprint:[u8;32]}
impl WriterReadyRef{
    /// Call ONLY after real writer validation. This function validates bounded
    /// metadata and does not infer ownership from an inventory string/hash.
    pub(crate) fn from_verified_writer(owner:Account,inventory:String,revision:u32,fingerprint:[u8;32])->Result<Self>{
        if owner.0==[0;16]||inventory.is_empty()||inventory.len()>96||!inventory.is_ascii()
            ||inventory.bytes().any(|b|b.is_ascii_control())||!(13..=i32::MAX as u32).contains(&revision)
            ||fingerprint==[0;32]{return Err(Error::BadWriterRef);}Ok(Self{owner,inventory,revision,fingerprint})
    }
    pub fn owner(&self)->Account{self.owner}
    pub fn inventory(&self)->&str{&self.inventory}
    pub fn revision(&self)->u32{self.revision}
    pub fn fingerprint(&self)->[u8;32]{self.fingerprint}
}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct ReservedRef{ready:WriterReadyRef,key:String,battle:BattleKey,ticket:u64}
impl ReservedRef{
    /// Only a checked durable reservation reply may construct this adapter input.
    pub(crate) fn from_verified_writer(ready:WriterReadyRef,key:String,battle:BattleKey,ticket:u64)->Result<Self>{
        if !bounded_key(&key)||battle.0==0||battle.0>i64::MAX as u64||ticket==0{return Err(Error::BadWriterRef);}Ok(Self{ready,key,battle,ticket})
    }
}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct ReleasedRef{ready:WriterReadyRef,ticket:u64}
impl ReleasedRef{
    /// Writer adapter proves NO reservation was made, or its exact reservation
    /// was durably cancelled. Domain equality below is only snapshot binding.
    pub(crate) fn from_verified_writer(ready:WriterReadyRef,ticket:u64)->Result<Self>{if ticket==0{return Err(Error::BadWriterRef);}Ok(Self{ready,ticket})}
}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct FinishedRef{owner:Account,reservation:String,battle:BattleKey}
impl FinishedRef{
    /// Adapter must first check the real Finish/FinishResults receipt.
    pub(crate) fn from_verified_writer(owner:Account,reservation:String,battle:BattleKey)->Result<Self>{
        if !bounded_key(&reservation)||battle.0==0||battle.0>i64::MAX as u64{return Err(Error::BadWriterRef);}Ok(Self{owner,reservation,battle})
    }
}
fn bounded_key(s:&str)->bool{!s.is_empty()&&s.len()<=96&&s.bytes().all(|b|b.is_ascii_alphanumeric()||b"_-:.".contains(&b))}

#[derive(Clone,Debug,PartialEq,Eq)]struct Auth{generation:u64,name:String,last_seen:u64,connected:bool}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Claim{Room(RoomKey),Battle(BattleKey)}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub struct ReadyContext{room:RoomKey,revision:u64}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct Member{account:Account,name:String,roster:Roster,ready:Option<WriterReadyRef>,membership:u64}
impl Member{
    pub fn account(&self)->Account{self.account}pub fn name(&self)->&str{&self.name}
    pub fn roster(&self)->Roster{self.roster}pub fn ready(&self)->Option<&WriterReadyRef>{self.ready.as_ref()}
}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct LaunchMember{account:Account,name:String,side:Side,ready:WriterReadyRef}
impl LaunchMember{
    pub fn account(&self)->Account{self.account}pub fn name(&self)->&str{&self.name}
    pub fn side(&self)->Side{self.side}pub fn ready(&self)->&WriterReadyRef{&self.ready}
}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct LaunchSnapshot{ticket:u64,room:RoomKey,creator:Account,settings:Settings,members:Vec<LaunchMember>}
impl LaunchSnapshot{
    pub fn ticket(&self)->u64{self.ticket}pub fn room(&self)->RoomKey{self.room}pub fn creator(&self)->Account{self.creator}
    pub fn settings(&self)->&Settings{&self.settings}pub fn members(&self)->&[LaunchMember]{&self.members}
}
#[derive(Clone,Debug,PartialEq,Eq)]struct Preparing{snapshot:LaunchSnapshot,departures:BTreeSet<Account>,abort_requested:bool}
#[derive(Clone,Debug,PartialEq,Eq)]enum Phase{Lobby,Preparing(Preparing)}
#[derive(Clone,Debug,PartialEq,Eq)]pub struct Room{key:RoomKey,creator:Account,settings:Settings,revision:u64,members:BTreeMap<Account,Member>,team_ready:[bool;2],phase:Phase}
impl Room{
    pub fn key(&self)->RoomKey{self.key}pub fn creator(&self)->Account{self.creator}pub fn settings(&self)->&Settings{&self.settings}
    pub fn revision(&self)->u64{self.revision}pub fn members(&self)->impl Iterator<Item=&Member>{self.members.values()}
    pub fn team_ready(&self)->[bool;2]{self.team_ready}pub fn preparing(&self)->Option<&LaunchSnapshot>{if let Phase::Preparing(p)=&self.phase{Some(&p.snapshot)}else{None}}
    pub fn abort_requested(&self)->bool{matches!(&self.phase,Phase::Preparing(p)if p.abort_requested)}
    fn lobby(&self)->Result<()>{if matches!(self.phase,Phase::Lobby){Ok(())}else{Err(Error::LaunchPending)}}
    fn creator_only(&self,who:Account)->Result<()>{if self.creator==who{Ok(())}else{Err(Error::NotCreator)}}
    fn revised(&mut self)->Result<()>{self.revision=self.revision.checked_add(1).ok_or(Error::Limit)?;Ok(())}
    fn invalidate_teams(&mut self){self.team_ready=[false;2];}
    fn valid_side(&self,side:Side)->Result<()>{
        let selected:Vec<_>=self.members.values().filter(|m|m.roster.assigned&&m.roster.side==side).collect();
        if selected.is_empty()||selected.len()>MAX_SIDE{return Err(Error::InvalidTeam);}
        if selected.iter().any(|m|m.ready.is_none()){return Err(Error::NotReady);}Ok(())
    }
}
#[derive(Clone,Debug,PartialEq,Eq)]struct Battle{snapshot:LaunchSnapshot,reservations:Vec<ReservedRef>}
#[derive(Clone,Debug,PartialEq,Eq)]pub enum Command{
    Create(Settings),Join(RoomKey),Leave,Kick(Account),Assign{target:Account,roster:Roster},SwapTeams,
    UpdateSettings(Settings),Ready{context:ReadyContext,selection:WriterReadyRef},NotReady,
    TeamReady{side:Side,ready:bool,force:bool},
}
#[derive(Clone,Debug,PartialEq,Eq)]pub enum Event{
    Created(RoomKey),Joined{room:RoomKey,account:Account},Left{room:RoomKey,account:Account},Kicked{room:RoomKey,account:Account},
    Closed(RoomKey),RosterChanged{room:RoomKey,account:Account},PlayerState{room:RoomKey,account:Account},
    SettingsChanged(RoomKey),TeamsChanged(RoomKey),Prepare(LaunchSnapshot),AbortRequested{room:RoomKey,ticket:u64},
    Aborted(RoomKey),Launched{battle:BattleKey,snapshot:LaunchSnapshot},BattleDisconnected{battle:BattleKey,account:Account},BattleFinished(BattleKey),
}
#[derive(Clone,Copy,Debug,PartialEq,Eq)]pub enum Error{Unauthenticated,StaleLease,Clock,Limit,BadIdentity,BadSettings,BadWriterRef,
    AlreadyClaimed,NoRoom,ClosedRoom,RoomFull,NotMember,NotCreator,InvalidTeam,NotReady,WrongOwner,LaunchPending,
    WrongTicket,WrongReceipt,BusyBattle,StaleSelection}
pub type Result<T>=std::result::Result<T,Error>;

#[derive(Clone,Debug,PartialEq,Eq,Default)]pub struct Registry{
    auth:BTreeMap<Account,Auth>,claims:BTreeMap<Account,Claim>,rooms:BTreeMap<RoomKey,Room>,battles:BTreeMap<BattleKey,Battle>,
    generation_floors:BTreeMap<Account,u64>,
    next_room:u64,next_ticket:u64,next_membership:u64,last_now:u64,
}
impl Registry{
    pub fn claim(&self,account:Account)->Option<Claim>{self.claims.get(&account).copied()}
    pub fn room(&self,key:RoomKey)->Option<&Room>{self.rooms.get(&key)}
    pub fn authenticated_room(&self,who:AuthLease)->Result<RoomKey>{self.authenticated(who)?;self.room_of(who.account)}
    /// Server-only membership generation. It fences a leave/rejoin even when
    /// both happen between native publication ticks; no client epoch is added.
    pub fn member_context(&self,key:RoomKey,account:Account)->Option<(AuthLease,u64)>{
        let member=self.rooms.get(&key)?.members.get(&account)?;let auth=self.auth.get(&account)?;
        Some((AuthLease{account,generation:auth.generation},member.membership))
    }
    pub fn rooms(&self)->impl Iterator<Item=&Room>{self.rooms.values()}
    pub fn battle_snapshot(&self,key:BattleKey)->Option<&LaunchSnapshot>{self.battles.get(&key).map(|b|&b.snapshot)}
    /// Capture on native CMD402 receipt, BEFORE an external readiness check.
    /// Adapter-generated only: no additional client protocol field is needed.
    pub fn selection_context(&self,who:AuthLease)->Result<ReadyContext>{
        self.authenticated(who)?;let key=self.room_of(who.account)?;let room=self.rooms.get(&key).ok_or(Error::NoRoom)?;
        room.lobby()?;Ok(ReadyContext{room:key,revision:room.revision})
    }
    fn transaction<T>(&mut self,now:u64,f:impl FnOnce(&mut Self)->Result<T>)->Result<T>{
        if now<self.last_now{return Err(Error::Clock);}let mut next=self.clone();let result=f(&mut next)?;next.last_now=now;*self=next;Ok(result)
    }
    /// Binding is supplied by the existing authenticated Session, never parsed
    /// from a caller-selected account ID. This is NOT a credential verifier.
    pub fn bind_authenticated(&mut self,lease:AuthLease,name:String,now:u64)->Result<()>{self.transaction(now,|s|{
        if lease.account.0==[0;16]||lease.generation==0||!(3..=24).contains(&name.chars().count())||name.len()>48||name.chars().any(char::is_control){return Err(Error::BadIdentity);}
        if let Some(old)=s.auth.get_mut(&lease.account){
            if old.generation==lease.generation&&old.connected&&old.name==name{old.last_seen=now;return Ok(());}
            if s.claims.contains_key(&lease.account){return Err(Error::AlreadyClaimed);}
            if lease.generation<=old.generation{return Err(Error::StaleLease);}
        }
        // Removing a disconnected auth row must not make its retired lease
        // fresh again. This floor is independent of current room/battle claims.
        if let Some(floor)=s.generation_floors.get(&lease.account){
            if lease.generation<=*floor{return Err(Error::StaleLease);}
        }else if s.generation_floors.len()>=MAX_GENERATIONS{return Err(Error::Limit);}
        if !s.auth.contains_key(&lease.account)&&s.auth.len()>=MAX_ACCOUNTS{return Err(Error::Limit);}
        s.generation_floors.insert(lease.account,lease.generation);
        s.auth.insert(lease.account,Auth{generation:lease.generation,name,last_seen:now,connected:true});Ok(())
    })}
    fn authenticated(&self,who:AuthLease)->Result<()>{
        let a=self.auth.get(&who.account).ok_or(Error::Unauthenticated)?;
        if a.generation!=who.generation{return Err(Error::StaleLease);}if !a.connected{return Err(Error::Unauthenticated);}Ok(())
    }
    pub fn heartbeat(&mut self,who:AuthLease,now:u64)->Result<()>{self.transaction(now,|s|{s.authenticated(who)?;s.auth.get_mut(&who.account).unwrap().last_seen=now;Ok(())})}
    fn room_of(&self,who:Account)->Result<RoomKey>{match self.claim(who){Some(Claim::Room(k))=>Ok(k),Some(Claim::Battle(_))=>Err(Error::BusyBattle),None=>Err(Error::NotMember)}}
    pub fn command(&mut self,who:AuthLease,command:Command,now:u64)->Result<Vec<Event>>{self.transaction(now,|s|{
        s.authenticated(who)?;let result=s.command_inner(who.account,command)?;s.auth.get_mut(&who.account).unwrap().last_seen=now;Ok(result)
    })}
    fn command_inner(&mut self,who:Account,command:Command)->Result<Vec<Event>>{
        match command{
            Command::Create(settings)=>{
                settings.validate()?;if self.claims.contains_key(&who){return Err(Error::AlreadyClaimed);}if self.rooms.len()>=MAX_ROOMS{return Err(Error::Limit);}
                self.next_room=self.next_room.checked_add(1).ok_or(Error::Limit)?;let key=RoomKey(self.next_room);
                self.next_membership=self.next_membership.checked_add(1).ok_or(Error::Limit)?;
                let member=Member{account:who,name:self.auth[&who].name.clone(),roster:Roster::assigned(Side::One),ready:None,membership:self.next_membership};
                self.rooms.insert(key,Room{key,creator:who,settings,revision:1,members:BTreeMap::from([(who,member)]),team_ready:[false;2],phase:Phase::Lobby});
                self.claims.insert(who,Claim::Room(key));Ok(vec![Event::Created(key),Event::Joined{room:key,account:who}])
            },
            Command::Join(key)=>{
                if self.claims.contains_key(&who){return Err(Error::AlreadyClaimed);}
                let room=self.rooms.get_mut(&key).ok_or(Error::NoRoom)?;room.lobby()?;
                if !room.settings.opened{return Err(Error::ClosedRoom);}if room.members.len()>=usize::from(room.settings.capacity){return Err(Error::RoomFull);}
                self.next_membership=self.next_membership.checked_add(1).ok_or(Error::Limit)?;
                room.members.insert(who,Member{account:who,name:self.auth[&who].name.clone(),roster:Roster::bench(Side::One),ready:None,membership:self.next_membership});
                room.invalidate_teams();room.revised()?;self.claims.insert(who,Claim::Room(key));Ok(vec![Event::Joined{room:key,account:who}])
            },
            Command::Leave=>{let key=self.room_of(who)?;self.depart(key,who,false)},
            Command::Kick(target)=>{let key=self.room_of(who)?;let room=&self.rooms[&key];room.creator_only(who)?;
                if target==who{return Err(Error::NotCreator);}if !room.members.contains_key(&target){return Err(Error::NotMember);}self.depart(key,target,true)},
            other=>{
                let key=self.room_of(who)?;let room=self.rooms.get_mut(&key).ok_or(Error::NoRoom)?;room.lobby()?;
                match other{
                    Command::Assign{target,roster}=>{
                        room.creator_only(who)?;if !room.members.contains_key(&target){return Err(Error::NotMember);}
                        if roster.assigned&&room.members.values().filter(|m|m.account!=target&&m.roster.assigned&&m.roster.side==roster.side).count()>=MAX_SIDE{return Err(Error::InvalidTeam);}
                        let member=room.members.get_mut(&target).unwrap();if member.roster==roster{return Ok(Vec::new());}member.roster=roster;member.ready=None;
                        room.invalidate_teams();room.revised()?;Ok(vec![Event::RosterChanged{room:key,account:target},Event::TeamsChanged(key)])
                    },
                    Command::SwapTeams=>{room.creator_only(who)?;for m in room.members.values_mut(){m.roster.side=m.roster.side.other();m.ready=None;}
                        room.invalidate_teams();room.revised()?;Ok(room.members.keys().map(|a|Event::RosterChanged{room:key,account:*a}).chain([Event::TeamsChanged(key)]).collect())},
                    Command::UpdateSettings(settings)=>{room.creator_only(who)?;settings.validate()?;if usize::from(settings.capacity)<room.members.len(){return Err(Error::RoomFull);}
                        room.settings=settings;for m in room.members.values_mut(){m.ready=None;}room.invalidate_teams();room.revised()?;Ok(vec![Event::SettingsChanged(key),Event::TeamsChanged(key)])},
                    Command::Ready{context,selection:ready}=>{
                        if context.room!=key||context.revision!=room.revision{return Err(Error::StaleSelection);}
                        if ready.owner!=who{return Err(Error::WrongOwner);}let member=room.members.get_mut(&who).ok_or(Error::NotMember)?;
                        if member.ready.as_ref()==Some(&ready){return Ok(Vec::new());}member.ready=Some(ready);room.invalidate_teams();room.revised()?;
                        Ok(vec![Event::PlayerState{room:key,account:who},Event::TeamsChanged(key)])
                    },
                    Command::NotReady=>{let member=room.members.get_mut(&who).ok_or(Error::NotMember)?;member.ready=None;room.invalidate_teams();room.revised()?;
                        Ok(vec![Event::PlayerState{room:key,account:who},Event::TeamsChanged(key)])},
                    Command::TeamReady{side,ready,force:_}=>{
                        room.creator_only(who)?;if ready{room.valid_side(side)?;}room.team_ready[side.index()]=ready;room.revised()?;
                        let mut events=vec![Event::TeamsChanged(key)];
                        if room.team_ready==[true,true]{
                            room.valid_side(Side::One)?;room.valid_side(Side::Two)?;
                            let members:Vec<_>=room.members.values().filter(|m|m.roster.assigned).map(|m|LaunchMember{account:m.account,name:m.name.clone(),side:m.roster.side,ready:m.ready.clone().unwrap()}).collect();
                            if !(2..=MAX_MEMBERS).contains(&members.len()){return Err(Error::InvalidTeam);}
                            self.next_ticket=self.next_ticket.checked_add(1).ok_or(Error::Limit)?;
                            let snapshot=LaunchSnapshot{ticket:self.next_ticket,room:key,creator:who,settings:room.settings.clone(),members};
                            room.phase=Phase::Preparing(Preparing{snapshot:snapshot.clone(),departures:BTreeSet::new(),abort_requested:false});events.push(Event::Prepare(snapshot));
                        }Ok(events)
                    },_=>unreachable!(),
                }
            }
        }
    }
    fn depart(&mut self,key:RoomKey,account:Account,kicked:bool)->Result<Vec<Event>>{
        let room=self.rooms.get_mut(&key).ok_or(Error::NoRoom)?;
        if let Phase::Preparing(p)=&mut room.phase{
            let added=p.departures.insert(account);p.abort_requested=true;
            return Ok(if added{vec![Event::AbortRequested{room:key,ticket:p.snapshot.ticket}]}else{Vec::new()});
        }
        if room.creator==account{return self.close_room(key);}
        room.members.remove(&account).ok_or(Error::NotMember)?;room.invalidate_teams();room.revised()?;self.claims.remove(&account);
        if self.auth.get(&account).is_some_and(|a|!a.connected){self.auth.remove(&account);}
        Ok(vec![if kicked{Event::Kicked{room:key,account}}else{Event::Left{room:key,account}},Event::TeamsChanged(key)])
    }
    fn close_room(&mut self,key:RoomKey)->Result<Vec<Event>>{
        let room=self.rooms.remove(&key).ok_or(Error::NoRoom)?;let mut events=Vec::new();
        for account in room.members.keys(){self.claims.remove(account);if self.auth.get(account).is_some_and(|a|!a.connected){self.auth.remove(account);}events.push(Event::Left{room:key,account:*account});}
        events.push(Event::Closed(key));Ok(events)
    }
    pub fn disconnect(&mut self,who:AuthLease,now:u64)->Result<Vec<Event>>{self.transaction(now,|s|{
        s.authenticated(who)?;s.auth.get_mut(&who.account).unwrap().connected=false;s.disconnect_inner(who.account)
    })}
    fn disconnect_inner(&mut self,account:Account)->Result<Vec<Event>>{match self.claim(account){
        Some(Claim::Room(key))=>self.depart(key,account,false),Some(Claim::Battle(battle))=>Ok(vec![Event::BattleDisconnected{battle,account}]),
        None=>{self.auth.remove(&account);Ok(Vec::new())},
    }}
    /// Monotonic server clock only. Timeout never proves a battle reservation
    /// was returned, and never releases a Preparing/Battle claim on its own.
    pub fn expire(&mut self,now:u64,idle_ms:u64)->Result<Vec<Event>>{self.transaction(now,|s|{
        if !(1..=300_000).contains(&idle_ms){return Err(Error::BadSettings);}
        let expired:Vec<_>=s.auth.iter().filter(|(_,a)|a.connected&&now.saturating_sub(a.last_seen)>=idle_ms).map(|(k,_)|*k).collect();let mut events=Vec::new();
        for account in expired{if let Some(a)=s.auth.get_mut(&account){a.connected=false;events.extend(s.disconnect_inner(account)?);}}Ok(events)
    })}
    fn prepared(&self,key:RoomKey,ticket:u64)->Result<&Preparing>{
        let room=self.rooms.get(&key).ok_or(Error::NoRoom)?;if let Phase::Preparing(p)=&room.phase{if p.snapshot.ticket==ticket{Ok(p)}else{Err(Error::WrongTicket)}}else{Err(Error::LaunchPending)}
    }
    /// External saga must supply all separately verified durable reservations.
    /// This component neither creates reservations nor constructs World actors.
    pub fn commit_launch(&mut self,key:RoomKey,ticket:u64,battle:BattleKey,reservations:Vec<ReservedRef>,now:u64)->Result<Vec<Event>>{self.transaction(now,|s|{
        if battle.0==0||battle.0>i64::MAX as u64||s.battles.contains_key(&battle)||s.battles.len()>=MAX_ROOMS{return Err(Error::WrongReceipt);}
        let p=s.prepared(key,ticket)?;if p.abort_requested{return Err(Error::LaunchPending);}let snapshot=p.snapshot.clone();
        if reservations.len()!=snapshot.members.len(){return Err(Error::WrongReceipt);}let mut seen=BTreeSet::new();let mut keys=BTreeSet::new();
        for r in &reservations{
            if r.battle!=battle||r.ticket!=ticket||!seen.insert(r.ready.owner)||!keys.insert(&r.key)||!snapshot.members.iter().any(|m|m.ready==r.ready)
                ||s.claim(r.ready.owner)!=Some(Claim::Room(key)){return Err(Error::WrongReceipt);}
        }
        // One-shot laboratory policy. Benched members receive room-left; combat
        // members move atomically to Battle and remain claimed until Finish.
        let mut events=s.close_room(key)?;
        for m in &snapshot.members{s.claims.insert(m.account,Claim::Battle(battle));}
        s.battles.insert(battle,Battle{snapshot:snapshot.clone(),reservations});events.push(Event::Launched{battle,snapshot});Ok(events)
    })}
    /// All participants require verified no-reserve/released evidence, including
    /// those for whom the saga failed before reserve. No timeout-based refund.
    pub fn abort_launch(&mut self,key:RoomKey,ticket:u64,released:Vec<ReleasedRef>,now:u64)->Result<Vec<Event>>{self.transaction(now,|s|{
        let p=s.prepared(key,ticket)?;let snap=p.snapshot.clone();let departures=p.departures.clone();
        if released.len()!=snap.members.len(){return Err(Error::WrongReceipt);}let mut seen=BTreeSet::new();
        for r in released{if r.ticket!=ticket||!seen.insert(r.ready.owner)||!snap.members.iter().any(|m|m.ready==r.ready){return Err(Error::WrongReceipt);}}
        if departures.contains(&snap.creator){return s.close_room(key);}
        let room=s.rooms.get_mut(&key).ok_or(Error::NoRoom)?;room.phase=Phase::Lobby;room.invalidate_teams();
        for m in room.members.values_mut(){m.ready=None;}room.revised()?;
        let mut events=vec![Event::Aborted(key)];for account in departures{events.extend(s.depart(key,account,false)?);}Ok(events)
    })}
    /// Actual writer Finish/FinishResults receipts are required for every
    /// participant. Claim release is atomic and never inferred from UI/HP/time.
    pub fn finish_battle(&mut self,battle:BattleKey,finished:Vec<FinishedRef>,now:u64)->Result<Vec<Event>>{self.transaction(now,|s|{
        let b=s.battles.get(&battle).ok_or(Error::WrongReceipt)?;if finished.len()!=b.reservations.len(){return Err(Error::WrongReceipt);}let mut seen=BTreeSet::new();
        for f in finished{if f.battle!=battle||!seen.insert(f.owner)||!b.reservations.iter().any(|r|r.ready.owner==f.owner&&r.key==f.reservation)
            ||s.claim(f.owner)!=Some(Claim::Battle(battle)){return Err(Error::WrongReceipt);}}
        let b=s.battles.remove(&battle).unwrap();for m in b.snapshot.members{s.claims.remove(&m.account);if s.auth.get(&m.account).is_some_and(|a|!a.connected){s.auth.remove(&m.account);}}
        Ok(vec![Event::BattleFinished(battle)])
    })}
}

#[cfg(test)]
#[path="room_tests.rs"]
mod tests;

#[cfg(test)]
#[path="p10b_auth_generation_tests.rs"]
mod auth_generation_tests;
