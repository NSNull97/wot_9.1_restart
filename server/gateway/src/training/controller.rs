//! Native room command/publication component. No sockets, async writer or World.
//! Facts/leases/channels come from actual verified Session adapters, never input.
use std::collections::BTreeMap;
use super::{adapter,aliases,current_room as current,domain as d,ingress as i,list_preview as lp,wire as w};

pub const POLICY:&str="test_lab.p10b.controller-prohorovka-one-shot.v1";
const MAX_PENDING:usize=4;
#[derive(Clone,Debug,PartialEq)]
pub enum Refusal{Domain(d::Error),Current(current::Error),Adapter(adapter::Error),BadArgs,Unsupported,StaleChannel,Facts,Codec,Limit,Busy}
impl From<d::Error>for Refusal{fn from(e:d::Error)->Self{Self::Domain(e)}}
impl From<current::Error>for Refusal{fn from(e:current::Error)->Self{Self::Current(e)}}
impl From<adapter::Error>for Refusal{fn from(e:adapter::Error)->Self{Self::Adapter(e)}}
type Result<T>=std::result::Result<T,Refusal>;

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct Call{pub caller:d::AuthLease,pub channel:current::Channel,pub profile:current::ProfileStamp,pub expected_revision:u32}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct ReadyTask{
    caller:d::AuthLease,channel:current::Channel,profile:current::ProfileStamp,
    expected_revision:u32,room:d::RoomKey,room_revision:u64,membership:u64,
    native_inventory:u32,callback:i16,context:d::ReadyContext,id:u64,
}
impl ReadyTask{
    pub fn caller(&self)->d::AuthLease{self.caller}pub fn channel(&self)->current::Channel{self.channel}
    pub fn profile(&self)->current::ProfileStamp{self.profile}pub fn expected_revision(&self)->u32{self.expected_revision}
    pub fn room(&self)->d::RoomKey{self.room}pub fn room_revision(&self)->u64{self.room_revision}pub fn membership(&self)->u64{self.membership}
    pub fn native_inventory(&self)->u32{self.native_inventory}pub fn callback(&self)->i16{self.callback}
    pub fn id(&self)->u64{self.id}
}
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct PrepareTask{snapshot:d::LaunchSnapshot,caller:d::AuthLease,channel:current::Channel,callback:i16}
impl PrepareTask{
    pub fn snapshot(&self)->&d::LaunchSnapshot{&self.snapshot}pub fn caller(&self)->d::AuthLease{self.caller}
    pub fn channel(&self)->current::Channel{self.channel}pub fn callback(&self)->i16{self.callback}
}
#[derive(Clone,Debug,Default,PartialEq)]
pub struct Batch{
    pub bodies:BTreeMap<d::Account,Vec<w::Body>>,pub ready:Vec<ReadyTask>,pub prepare:Vec<PrepareTask>,pub events:Vec<d::Event>,
}
impl Batch{
    fn append(&mut self,account:d::Account,bodies:Vec<w::Body>)->Result<()>{
        if !self.bodies.contains_key(&account)&&self.bodies.len()>=d::MAX_ACCOUNTS{return Err(Refusal::Limit);}
        let old=self.bodies.get(&account);let bytes=old.into_iter().flatten().chain(&bodies).try_fold(0usize,|n,b|n.checked_add(b.len())).ok_or(Refusal::Limit)?;
        if old.map_or(0,Vec::len)+bodies.len()>w::MAX_OUTBOX||bytes>w::MAX_OUTBOX_BYTES||bodies.iter().any(|b|b.len()>512){return Err(Refusal::Limit);}
        self.bodies.entry(account).or_default().extend(bodies);Ok(())
    }
}
#[derive(Clone,Debug,PartialEq)]
struct LastView{view:w::RoomView,rows:BTreeMap<d::Account,w::Member>}
#[derive(Clone,Debug,PartialEq)]
struct Recipient{lease:d::AuthLease,channel:current::Channel,database:i32,book:aliases::Book,preview:lp::PreviewBook,last:Option<LastView>}
#[derive(Clone,Debug,PartialEq)]
struct RoomMeta{native:u32,created:f64}
#[derive(Clone,Debug,PartialEq,Eq)]
struct PendingDeparture{caller:d::AuthLease,channel:current::Channel,callback:i16,target:d::Account,kicked:bool}
#[derive(Clone,Debug,PartialEq,Default)]
pub struct Controller{
    registry:d::Registry,recipients:BTreeMap<d::Account,Recipient>,facts:BTreeMap<d::Account,adapter::NativeFacts>,
    rooms:BTreeMap<d::RoomKey,RoomMeta>,joined:BTreeMap<(d::RoomKey,d::Account),(u64,f64)>,next_native:u32,
    held:BTreeMap<u64,PrepareTask>,
    departures:BTreeMap<u64,Vec<PendingDeparture>>,read_revision:u64,
    pending_ready:BTreeMap<d::Account,ReadyTask>,next_ready:u64,
}
impl Controller{
    pub fn registry(&self)->&d::Registry{&self.registry}
    /// Readonly comparison with the actual native Account recipient.
    pub fn is_current_recipient(&self,lease:d::AuthLease,channel:current::Channel,database:i32)->bool{
        self.recipients.get(&lease.account).is_some_and(|r|r.lease==lease&&r.channel==channel&&r.database==database)
    }
    pub fn native_room(&self,key:d::RoomKey)->Option<u32>{self.rooms.get(&key).map(|m|m.native)}
    /// Server-owned observation generation, not a native/client timestamp.
    pub fn read_revision(&self)->u64{self.read_revision}
    pub fn room_read(&self,native:u32)->Option<(d::RoomKey,u64)>{self.rooms.iter().find_map(|(key,meta)|
        (meta.native==native).then(||self.registry.room(*key).map(|room|(*key,room.revision()))).flatten())}
    fn changed(&mut self)->Result<()>{self.read_revision=self.read_revision.checked_add(1).ok_or(Refusal::Limit)?;Ok(())}
    fn seconds(now:u64)->Result<f64>{if now>1_000_000_000_000_000{return Err(Refusal::BadArgs);}Ok(now as f64/1000.)}
    fn channel(&self,call:Call)->Result<()>{
        let r=self.recipients.get(&call.caller.account).ok_or(Refusal::StaleChannel)?;
        if r.lease!=call.caller||r.channel!=call.channel||call.channel.session==0||call.channel.generation==0
            ||call.expected_revision!=call.profile.revision||!(13..=i32::MAX as u32).contains(&call.expected_revision)||call.profile.source_binding==[0;32]{return Err(Refusal::StaleChannel);}Ok(())
    }
    pub fn bind(&mut self,lease:d::AuthLease,channel:current::Channel,name:String,database:i32,now:u64)->Result<()>{
        let mut next=self.clone();Self::seconds(now)?;
        next.registry.bind_authenticated(lease,name,now)?;
        if channel.session==0||channel.generation==0||database<=0{return Err(Refusal::BadArgs);}
        if let Some(old)=next.recipients.get(&lease.account){
            if old.lease!=lease||old.database!=database{return Err(Refusal::StaleChannel);}
            if old.channel!=channel{
                if old.channel.session!=channel.session||channel.generation<=old.channel.generation{return Err(Refusal::StaleChannel);}
                if next.registry.claim(lease.account).is_some()||old.last.is_some()||next.pending_ready.contains_key(&lease.account)
                    ||next.held.values().any(|p|p.caller.account==lease.account)||next.departures.values().flatten().any(|p|p.caller.account==lease.account){return Err(Refusal::Busy);}
                // Warm Account recreation reuses its underlying Session. Keep
                // peer/preview tombstones: a fresh old semantic404 has no epoch.
                next.recipients.get_mut(&lease.account).ok_or(Refusal::StaleChannel)?.channel=channel;
            }
        }else{
            if next.recipients.len()>=d::MAX_ACCOUNTS||next.recipients.values().any(|r|r.channel==channel||r.database==database){return Err(Refusal::Limit);}
            let principal=adapter::canonical(lease);
            next.recipients.insert(lease.account,Recipient{lease,channel,database,book:aliases::Book::new(principal).map_err(|_|Refusal::Codec)?,
                preview:lp::PreviewBook::new(principal).map_err(|_|Refusal::Codec)?,last:None});
        }*self=next;Ok(())
    }
    fn refresh_facts(&mut self,facts:&BTreeMap<d::Account,adapter::NativeFacts>)->Result<()>{
        if facts.len()>d::MAX_ACCOUNTS{return Err(Refusal::Limit);}
        for(account,fact)in facts{
            if let Some(r)=self.recipients.get(account){if r.database!=fact.database_id{return Err(Refusal::Facts);}}
            else if self.registry.claim(*account).is_none(){return Err(Refusal::Facts);}
            // Source references stay opaque trusted inputs; shape here cannot
            // establish ownership. Actual descriptor is bounded by the encoder.
            if fact.database_id<=0||fact.descriptor.len()>64{return Err(Refusal::Facts);}
            self.facts.insert(*account,fact.clone());
        }Ok(())
    }
    fn metadata(&mut self,now:u64)->Result<()>{
        let seconds=Self::seconds(now)?;
        self.rooms.retain(|key,_|self.registry.room(*key).is_some());
        self.joined.retain(|(key,account),(membership,_)|self.registry.member_context(*key,*account).is_some_and(|(_,m)|m==*membership));
        for room in self.registry.rooms(){
            if !self.rooms.contains_key(&room.key()){
                self.next_native=self.next_native.checked_add(1).filter(|n|*n<=i32::MAX as u32).ok_or(Refusal::Limit)?;
                self.rooms.insert(room.key(),RoomMeta{native:self.next_native,created:seconds});
            }
            for member in room.members(){let(_,membership)=self.registry.member_context(room.key(),member.account()).ok_or(Refusal::Facts)?;
                self.joined.entry((room.key(),member.account())).or_insert((membership,seconds));
                if member.ready().is_none(){if let Some(f)=self.facts.get_mut(&member.account()){f.selected=None;}}
            }
        }
        self.facts.retain(|a,_|self.recipients.contains_key(a)||self.registry.claim(*a).is_some());
        if self.rooms.len()>d::MAX_ROOMS||self.joined.len()>d::MAX_ACCOUNTS||self.facts.len()>d::MAX_ACCOUNTS{return Err(Refusal::Limit);}Ok(())
    }
    fn room_key(&self,native:i64)->Result<d::RoomKey>{
        let native=u32::try_from(native).ok().filter(|n|*n>0&&*n<=i32::MAX as u32).ok_or(Refusal::BadArgs)?;
        self.rooms.iter().find_map(|(key,m)|(m.native==native).then_some(*key)).ok_or(Refusal::Domain(d::Error::NoRoom))
    }
    fn callback(batch:&mut Batch,account:d::Account,request:i16,result:w::CommandResult)->Result<()>{
        batch.append(account,vec![w::plain_response(request,result,"").map_err(|_|Refusal::Codec)?])
    }
    fn room_view(&mut self,account:d::Account,key:d::RoomKey)->Result<LastView>{
        let native=self.rooms.get(&key).ok_or(Refusal::Facts)?.native;
        let recipient=self.recipients.get_mut(&account).ok_or(Refusal::StaleChannel)?;
        let mut view=adapter::stage_room_view(&self.registry,&mut recipient.book,recipient.lease,native,&self.facts,0.)?;
        let members=self.registry.room(key).ok_or(d::Error::NoRoom)?.members().collect::<Vec<_>>();
        let mut rows=BTreeMap::new();
        for(member,row)in members.into_iter().zip(view.members.iter_mut()){
            row.joined_seconds=self.joined.get(&(key,member.account())).ok_or(Refusal::Facts)?.1;rows.insert(member.account(),row.clone());
        }w::validate_view(&view).map_err(|_|Refusal::Codec)?;Ok(LastView{view,rows})
    }
    fn publish(&mut self,actor:d::Account,events:&[d::Event],now:u64,batch:&mut Batch)->Result<()>{
        self.metadata(now)?;let accounts=self.recipients.keys().copied().collect::<Vec<_>>();
        for account in accounts{
            let key=match self.registry.claim(account){Some(d::Claim::Room(key))=>Some(key),_=>None};
            let old=self.recipients.get(&account).ok_or(Refusal::Facts)?.last.clone();
            let Some(key)=key else{
                if old.is_some(){
                    let kicked=events.iter().any(|e|matches!(e,d::Event::Kicked{account:a,..}if *a==account));
                    batch.append(account,vec![if kicked{w::kicked(10)}else{w::left()}])?;
                    let r=self.recipients.get_mut(&account).ok_or(Refusal::Facts)?;r.last=None;r.book.leave_room();
                }continue;
            };
            let new=self.room_view(account,key)?;let mut bodies=Vec::new();
            match old{
                None=>bodies=w::initialization(&new.view,aliases::OWN_ENTITY_ID).map_err(|_|Refusal::Codec)?,
                Some(old)if old.view.room_id!=new.view.room_id=>return Err(Refusal::Facts),
                Some(old)=>{
                    for(a,row)in &old.rows{if !new.rows.contains_key(a){bodies.push(w::player_removed(row.entity_id,row.roster).map_err(|_|Refusal::Codec)?);}}
                    let settings=old.view.map!=new.view.map||old.view.seconds!=new.view.seconds||old.view.opened!=new.view.opened||old.view.comment!=new.view.comment
                        ||old.rows.keys().ne(new.rows.keys());
                    if settings{bodies.extend(w::settings_updates(&new.view).map_err(|_|Refusal::Codec)?);}
                    for(a,row)in &new.rows{match old.rows.get(a){
                        None=>bodies.push(w::player_added(row).map_err(|_|Refusal::Codec)?),
                        Some(prior)=>{
                            if prior.entity_id!=row.entity_id||prior.database_id!=row.database_id||prior.name!=row.name{return Err(Refusal::Facts);}
                            if prior.roster!=row.roster{let actor_id=new.rows.get(&actor).ok_or(Refusal::Facts)?.entity_id;
                                bodies.push(w::roster_changed(row.entity_id,prior.roster,row.roster,actor_id).map_err(|_|Refusal::Codec)?);}
                            if prior.state!=row.state||prior.descriptor!=row.descriptor||prior.igr_type!=row.igr_type||prior.clan_database_id!=row.clan_database_id||prior.clan_abbrev!=row.clan_abbrev{
                                bodies.push(w::player_state(row).map_err(|_|Refusal::Codec)?);}
                        },
                    }}
                    if old.view.team_states!=new.view.team_states{bodies.push(w::team_states(new.view.team_states).map_err(|_|Refusal::Codec)?);}
                },
            }batch.append(account,bodies)?;self.recipients.get_mut(&account).ok_or(Refusal::Facts)?.last=Some(new);
        }Ok(())
    }
    fn listing(&self,start:i32,end:i32)->Result<lp::Listing>{
        if start<0||end<start||end>50{return Err(Refusal::BadArgs);}let mut rows=Vec::new();
        for room in self.registry.rooms(){let meta=self.rooms.get(&room.key()).ok_or(Refusal::Facts)?;
            let creator=room.members().find(|m|m.account()==room.creator()).ok_or(Refusal::Facts)?;
            let fact=self.facts.get(&room.creator()).ok_or(Refusal::Facts)?;
            rows.push(lp::ListRow{native_room_id:meta.native,created_seconds:meta.created,arena_type:4,creator:creator.name().into(),
                creator_database_id:fact.database_id,players:u8::try_from(room.members().count()).map_err(|_|Refusal::Limit)?,opened:room.settings().opened,
                comment:room.settings().comment.clone(),creator_clan_abbrev:fact.clan_abbrev.clone(),creator_igr_type:fact.igr_type});
        }
        // Explicit LAB sort: newest first, native-ID tie-break. Original server
        // sorting/privacy rules are UNKNOWN; all actual live rooms are shown.
        rows.sort_by(|a,b|b.created_seconds.total_cmp(&a.created_seconds).then_with(||b.native_room_id.cmp(&a.native_room_id)));
        let total=rows.len()as u32;let rows=rows.into_iter().skip(start as usize).take((end-start)as usize).collect();Ok(lp::Listing{total,rows})
    }
    fn preview(&mut self,account:d::Account,key:d::RoomKey)->Result<Vec<w::Body>>{
        let room=self.registry.room(key).ok_or(d::Error::NoRoom)?;let meta=self.rooms.get(&key).ok_or(Refusal::Facts)?;let mut members=Vec::new();
        for member in room.members(){let(lease,membership)=self.registry.member_context(key,member.account()).ok_or(Refusal::Facts)?;
            let fact=self.facts.get(&member.account()).ok_or(Refusal::Facts)?;
            if fact.selected.as_ref()!=member.ready(){return Err(Refusal::Facts);}let roster=member.roster();
            members.push(lp::PreviewMember{canonical:adapter::canonical(lease),membership,row:w::Member{entity_id:1,database_id:fact.database_id,name:member.name().into(),
                roster:match(roster.side,roster.assigned){(d::Side::One,true)=>1,(d::Side::Two,true)=>2,(d::Side::One,false)=>17,(d::Side::Two,false)=>18},
                state:if member.ready().is_some(){w::PlayerState::Ready}else{w::PlayerState::NotReady},joined_seconds:self.joined.get(&(key,member.account())).ok_or(Refusal::Facts)?.1,
                descriptor:if member.ready().is_some(){fact.descriptor.clone()}else{Vec::new()},igr_type:fact.igr_type,clan_database_id:fact.clan_database_id,clan_abbrev:fact.clan_abbrev.clone()}});
        }
        let preview=lp::Preview{room_key:key.0,native_room_id:meta.native,revision:room.revision(),members};
        let recipient=self.recipients.get_mut(&account).ok_or(Refusal::StaleChannel)?;
        lp::preview_stream(&mut recipient.preview,&preview).map_err(|_|Refusal::Codec)
    }
    pub fn apply(&mut self,call:Call,request:i::Request,facts:&BTreeMap<d::Account,adapter::NativeFacts>,now:u64)->Result<Batch>{
        let mut next=self.clone();let batch=next.apply_inner(call,request,facts,now)?;*self=next;Ok(batch)
    }
    fn apply_inner(&mut self,call:Call,request:i::Request,facts:&BTreeMap<d::Account,adapter::NativeFacts>,now:u64)->Result<Batch>{
        let route=match(&request.kind,request.reply){
            (i::Kind::Create{..},i::Reply::JoinedOrFailure)|(i::Kind::Join{..},i::Reply::JoinEvent)
                |(i::Kind::List{..}|i::Kind::ListByCreator{..},i::Reply::ListStream)|(i::Kind::Preview{..},i::Reply::RosterStream)=>true,
            (i::Kind::Create{..}|i::Kind::Join{..}|i::Kind::List{..}|i::Kind::ListByCreator{..}|i::Kind::Preview{..},_)=>false,
            (_,i::Reply::Plain(id))=>id>220,_=>false,
        };if !route{return Err(Refusal::BadArgs);}
        self.channel(call)?;Self::seconds(now)?;self.registry.heartbeat(call.caller,now)?;self.refresh_facts(facts)?;self.metadata(now)?;
        let mut batch=Batch::default();let callback=match request.reply{i::Reply::Plain(id)if id>220=>Some(id),i::Reply::Plain(_)=>return Err(Refusal::BadArgs),_=>None};
        let departure=self.pending_departure(call,&request)?;
        let command=match request.kind{
            i::Kind::List{prebattle_type:2,sort_key:7,idle:false,start,end}=>{batch.append(call.caller.account,lp::list_stream(&self.listing(start,end)?).map_err(|_|Refusal::Codec)?)?;return Ok(batch);},
            i::Kind::List{..}|i::Kind::ListByCreator{..}=>return Err(Refusal::Unsupported),
            i::Kind::Preview{room}=>{let key=self.room_key(room)?;let bodies=self.preview(call.caller.account,key)?;batch.append(call.caller.account,bodies)?;return Ok(batch);},
            i::Kind::Create{arena_type,seconds,opened,comment}=>{
                if arena_type!=4{return Err(Refusal::Unsupported);}let seconds=u16::try_from(seconds).map_err(|_|Refusal::BadArgs)?;
                let comment=std::str::from_utf8(comment.as_bytes()).map_err(|_|Refusal::BadArgs)?.to_owned();
                Some(d::Command::Create(d::Settings{capacity:6,map:d::QualifiedMap::Prohorovka,seconds,opened,comment}))
            },
            i::Kind::Join{room}=>Some(d::Command::Join(self.room_key(room)?)),
            i::Kind::Ready{native_inventory}=>{
                if self.pending_ready.contains_key(&call.caller.account){return Err(Refusal::Busy);}if self.pending_ready.len()>=d::MAX_ACCOUNTS{return Err(Refusal::Limit);}
                let native_inventory=u32::try_from(native_inventory).ok().filter(|n|*n>0&&*n<=i32::MAX as u32).ok_or(Refusal::BadArgs)?;
                let callback=callback.ok_or(Refusal::BadArgs)?;
                let prior_room=self.registry.authenticated_room(call.caller)?;
                if self.registry.room(prior_room).ok_or(d::Error::NoRoom)?.members().any(|m|m.account()==call.caller.account&&m.ready().is_some()){
                    // A new selection query revokes the previous validated loadout
                    // before any later411 in this same compound native frame.
                    batch.events=self.registry.command(call.caller,d::Command::NotReady,now)?;
                    self.changed()?;
                    let events=batch.events.clone();self.publish(call.caller.account,&events,now,&mut batch)?;
                }
                let context=self.registry.selection_context(call.caller)?;
                let room=self.registry.authenticated_room(call.caller)?;let revision=self.registry.room(room).ok_or(d::Error::NoRoom)?.revision();
                let(lease,membership)=self.registry.member_context(room,call.caller.account).ok_or(Refusal::Facts)?;if lease!=call.caller{return Err(Refusal::StaleChannel);}
                self.next_ready=self.next_ready.checked_add(1).ok_or(Refusal::Limit)?;
                let task=ReadyTask{caller:call.caller,channel:call.channel,profile:call.profile,expected_revision:call.expected_revision,room,room_revision:revision,membership,native_inventory,callback,context,id:self.next_ready};
                self.pending_ready.insert(call.caller.account,task.clone());batch.ready.push(task);return Ok(batch);
            },
            kind=>{
                let key=self.registry.authenticated_room(call.caller)?;let room=self.registry.room(key).ok_or(d::Error::NoRoom)?;
                let action=match kind{
                    i::Kind::Leave=>current::Action::Leave,i::Kind::NotReady{state:1}=>current::Action::NotReady,
                    i::Kind::NotReady{..}=>return Err(Refusal::Unsupported),
                    i::Kind::Assign{account_entity,roster}=>current::Action::Assign{target_alias:u32::try_from(account_entity).map_err(|_|Refusal::BadArgs)?,roster:match roster{
                        1=>d::Roster::assigned(d::Side::One),2=>d::Roster::assigned(d::Side::Two),17=>d::Roster::bench(d::Side::One),18=>d::Roster::bench(d::Side::Two),_=>return Err(Refusal::BadArgs)}},
                    i::Kind::Kick{account_entity}=>current::Action::Kick{target_alias:u32::try_from(account_entity).map_err(|_|Refusal::BadArgs)?},
                    i::Kind::SwapTeams=>current::Action::SwapTeams,
                    i::Kind::TeamReady{team,force}=>current::Action::TeamReady{side:side(team)?,ready:true,force},
                    i::Kind::TeamNotReady{team}=>current::Action::TeamReady{side:side(team)?,ready:false,force:false},
                    i::Kind::ChangeVoip{mask:0}=>{
                        self.registry.selection_context(call.caller)?;if room.creator()!=call.caller.account{return Err(d::Error::NotCreator.into());}
                        Self::callback(&mut batch,call.caller.account,callback.ok_or(Refusal::BadArgs)?,w::CommandResult::Success)?;return Ok(batch);
                    },
                    i::Kind::ChangeVoip{..}=>return Err(Refusal::Unsupported),
                    setting=>{let mut s=room.settings().clone();match setting{
                        i::Kind::ChangeArena{arena_type:4}=>s.map=d::QualifiedMap::Prohorovka,
                        i::Kind::ChangeArena{..}=>return Err(Refusal::Unsupported),
                        i::Kind::ChangeDuration{seconds}=>s.seconds=u16::try_from(seconds).map_err(|_|Refusal::BadArgs)?,
                        i::Kind::ChangeOpened{opened}=>s.opened=opened,
                        i::Kind::ChangeComment{comment}=>s.comment=std::str::from_utf8(comment.as_bytes()).map_err(|_|Refusal::BadArgs)?.to_owned(),
                        _=>return Err(Refusal::BadArgs),
                    }current::Action::UpdateSettings(s)},
                };
                let book=&self.recipients.get(&call.caller.account).ok_or(Refusal::StaleChannel)?.book;
                batch.events=current::current(&mut self.registry,book,call.caller,action,now)?;None
            },
        };
        if let Some(command)=command{batch.events=self.registry.command(call.caller,command,now)?;}
        self.changed()?;
        if let Some((ticket,pending))=departure{self.departures.entry(ticket).or_default().push(pending);}
        else if let Some(snapshot)=batch.events.iter().find_map(|e|if let d::Event::Prepare(s)=e{Some(s.clone())}else{None}){
            let task=PrepareTask{snapshot,caller:call.caller,channel:call.channel,callback:callback.ok_or(Refusal::BadArgs)?};
            if self.held.len()>=MAX_PENDING||self.held.insert(task.snapshot.ticket(),task.clone()).is_some(){return Err(Refusal::Limit);}batch.prepare.push(task);
        }else if let Some(callback)=callback{Self::callback(&mut batch,call.caller.account,callback,w::CommandResult::Success)?;}
        let events=batch.events.clone();self.publish(call.caller.account,&events,now,&mut batch)?;Ok(batch)
    }
    fn pending_departure(&self,call:Call,request:&i::Request)->Result<Option<(u64,PendingDeparture)>>{
        if !matches!(request.kind,i::Kind::Leave|i::Kind::Kick{..}){return Ok(None);}
        let room=self.registry.authenticated_room(call.caller)?;let state=self.registry.room(room).ok_or(d::Error::NoRoom)?;
        let Some(snapshot)=state.preparing()else{return Ok(None);};let i::Reply::Plain(callback)=request.reply else{return Err(Refusal::BadArgs);};
        let(target,kicked)=match request.kind{
            i::Kind::Leave=>(call.caller.account,false),
            i::Kind::Kick{account_entity}=>{
                let alias=u32::try_from(account_entity).map_err(|_|Refusal::BadArgs)?;
                if alias==aliases::OWN_ENTITY_ID{return Err(d::Error::NotCreator.into());}
                let members=state.members().map(|m|{let(lease,join_generation)=self.registry.member_context(room,m.account()).ok_or(Refusal::Facts)?;
                    Ok(aliases::Membership{canonical:adapter::canonical(lease),join_generation})}).collect::<Result<Vec<_>>>()?;
                let peer=self.recipients.get(&call.caller.account).ok_or(Refusal::StaleChannel)?.book.resolve_peer(room.0,alias,&members).map_err(|_|Refusal::StaleChannel)?;
                (d::Account(peer.canonical.account),true)
            },_=>return Err(Refusal::BadArgs),
        };
        let ticket=snapshot.ticket();let pending=self.departures.get(&ticket);
        if pending.is_some_and(|p|p.iter().any(|p|p.caller==call.caller&&p.target==target&&p.kicked==kicked)){return Err(Refusal::Busy);}
        if pending.map_or(0,Vec::len)>=2*d::MAX_MEMBERS||pending.is_none()&&self.departures.len()>=MAX_PENDING{return Err(Refusal::Limit);}
        Ok(Some((ticket,PendingDeparture{caller:call.caller,channel:call.channel,callback,target,kicked})))
    }
    /// Pure binding completion; actual writer parser/admission must run first.
    pub fn complete_ready(&mut self,task:&ReadyTask,call:Call,verified_native_inventory:u32,selection:d::WriterReadyRef,facts:&BTreeMap<d::Account,adapter::NativeFacts>,now:u64)->Result<Batch>{
        let mut next=self.clone();next.channel(call)?;
        if next.pending_ready.get(&task.caller.account)!=Some(task)||call.caller!=task.caller||call.channel!=task.channel||call.profile!=task.profile||call.expected_revision!=task.expected_revision
            ||verified_native_inventory!=task.native_inventory||selection.owner()!=call.caller.account||selection.revision()!=call.expected_revision
            ||next.registry.authenticated_room(call.caller).ok()!=Some(task.room)||next.registry.room(task.room).map(d::Room::revision)!=Some(task.room_revision)
            ||next.registry.member_context(task.room,call.caller.account)!=Some((task.caller,task.membership)){return Err(Refusal::StaleChannel);}
        next.refresh_facts(facts)?;let fact=next.facts.get(&call.caller.account).ok_or(Refusal::Facts)?;
        if fact.selected.as_ref()!=Some(&selection)||fact.descriptor.is_empty(){return Err(Refusal::Facts);}
        let events=next.registry.command(call.caller,d::Command::Ready{context:task.context,selection},now)?;
        next.pending_ready.remove(&task.caller.account);
        next.changed()?;
        let mut batch=Batch{events,..Batch::default()};Self::callback(&mut batch,call.caller.account,task.callback,w::CommandResult::Success)?;
        let events=batch.events.clone();next.publish(call.caller.account,&events,now,&mut batch)?;*self=next;Ok(batch)
    }
    /// Resolve exactly one failed/stale read-only selection job. Failure never
    /// grants ready state. A vanished or recreated Account gets no old callback.
    pub fn finish_ready_failure(&mut self,task:&ReadyTask)->Result<Batch>{
        let mut next=self.clone();if next.pending_ready.get(&task.caller.account)!=Some(task){return Err(Refusal::StaleChannel);}
        next.pending_ready.remove(&task.caller.account);let mut batch=Batch::default();
        if next.recipients.get(&task.caller.account).is_some_and(|r|r.lease==task.caller&&r.channel==task.channel){
            Self::callback(&mut batch,task.caller.account,task.callback,w::CommandResult::Failure)?;
        }*self=next;Ok(batch)
    }
    pub fn commit_launch(&mut self,room:d::RoomKey,ticket:u64,battle:d::BattleKey,reserved:Vec<d::ReservedRef>,now:u64)->Result<Batch>{
        let mut next=self.clone();let held=next.held.remove(&ticket).filter(|h|h.snapshot.room()==room).ok_or(Refusal::StaleChannel)?;
        let events=next.registry.commit_launch(room,ticket,battle,reserved,now)?;
        next.changed()?;
        let mut batch=Batch{events,..Batch::default()};next.held_callback(&held,w::CommandResult::Success,&mut batch)?;
        let events=batch.events.clone();next.publish(held.caller.account,&events,now,&mut batch)?;
        // Original Account.onArenaCreated clears its prebattle itself. Root's
        // statically supported candidate order is final411 callback then arena
        // transition; an explicit combat Left would navigate the training list.
        // Domain Left events and Book retirement remain intact. Native NOT_RUN.
        for member in held.snapshot.members(){if let Some(bodies)=batch.bodies.get_mut(&member.account()){bodies.retain(|body|body!=&w::left());}}
        *self=next;Ok(batch)
    }
    pub fn abort_launch(&mut self,room:d::RoomKey,ticket:u64,released:Vec<d::ReleasedRef>,now:u64)->Result<Batch>{
        let mut next=self.clone();let held=next.held.remove(&ticket).filter(|h|h.snapshot.room()==room).ok_or(Refusal::StaleChannel)?;
        let mut events=next.registry.abort_launch(room,ticket,released,now)?;let departures=next.departures.remove(&ticket).unwrap_or_default();
        // Preserve the first accepted departure cause. A staged Kick completes
        // only here, after the target actually loses its room membership.
        for event in &mut events{if let d::Event::Left{room,account}=*event{
            if departures.iter().find(|p|p.target==account).is_some_and(|p|p.kicked){*event=d::Event::Kicked{room,account};}
        }}next.changed()?;
        let mut batch=Batch{events,..Batch::default()};next.held_callback(&held,w::CommandResult::Failure,&mut batch)?;
        let events=batch.events.clone();next.publish(held.caller.account,&events,now,&mut batch)?;
        for pending in departures{
            if next.registry.claim(pending.target)==Some(d::Claim::Room(room)){return Err(Refusal::Facts);}
            if next.recipients.get(&pending.caller.account).is_some_and(|r|r.lease==pending.caller&&r.channel==pending.channel){
                Self::callback(&mut batch,pending.caller.account,pending.callback,w::CommandResult::Success)?;
            }
        }*self=next;Ok(batch)
    }
    fn held_callback(&self,held:&PrepareTask,result:w::CommandResult,batch:&mut Batch)->Result<()>{
        // A closed channel receives no fabricated callback on a new incarnation.
        if self.recipients.get(&held.caller.account).is_some_and(|r|r.lease==held.caller&&r.channel==held.channel){Self::callback(batch,held.caller.account,held.callback,result)?;}Ok(())
    }
    pub fn finish_battle(&mut self,battle:d::BattleKey,finished:Vec<d::FinishedRef>,now:u64)->Result<Batch>{
        let mut next=self.clone();let events=next.registry.finish_battle(battle,finished,now)?;
        next.changed()?;
        let mut batch=Batch{events,..Batch::default()};let events=batch.events.clone();next.publish(d::Account([0;16]),&events,now,&mut batch)?;*self=next;Ok(batch)
    }
    pub fn retire(&mut self,lease:d::AuthLease,channel:current::Channel,facts:&BTreeMap<d::Account,adapter::NativeFacts>,now:u64)->Result<Batch>{
        let mut next=self.clone();let r=next.recipients.get(&lease.account).ok_or(Refusal::StaleChannel)?;
        if r.lease!=lease||r.channel!=channel{return Err(Refusal::StaleChannel);}next.refresh_facts(facts)?;
        let events=next.registry.disconnect(lease,now)?;next.recipients.remove(&lease.account);
        next.changed()?;
        let mut batch=Batch{events,..Batch::default()};let events=batch.events.clone();next.publish(lease.account,&events,now,&mut batch)?;*self=next;Ok(batch)
    }
}
fn side(team:i64)->Result<d::Side>{match team{1=>Ok(d::Side::One),2=>Ok(d::Side::Two),_=>Err(Refusal::BadArgs)}}

#[cfg(test)]#[path="controller_tests.rs"]mod tests;
