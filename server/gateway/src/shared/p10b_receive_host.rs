//! Room receive/publication transaction. Intended child of shared/server.rs.
//! No socket, DB, writer dispatch or World launch occurs inside this transaction.
use super::*;
use std::collections::{BTreeMap,BTreeSet};
use crate::training091::{adapter::NativeFacts,controller::{Controller,Call,Refusal,ReadyTask,PrepareTask,Batch},
    current_room as current,domain::{self as room,Account},ingress::{self as ingress,Request,Reply},
    stream_flight as flight,wire as native};
use sha2::{Digest,Sha256};

pub(super) const POLICY:&str="test_lab.p10b.session-controller-receive.v1";
const MAX_RECORDS:usize=32*ingress::MAX_RECORDS;
#[derive(Clone,Debug)]
pub(super) struct RefusedRecord{pub call:Call,pub request:Request,pub refusal:Refusal}
#[derive(Clone,Debug)]
pub(super) struct DeferredRead{
    pub call:Call,pub request:Request,pub read:flight::ReadRevision,pub context:flight::StreamContext,
}
#[derive(Debug,Default)]
#[must_use="dispatch jobs/diagnostics only after committed receive; retain bounded deferred reads"]
pub(super) struct RoomReceived{
    pub close:bool,pub diagnostics:Vec<String>,pub ready:Vec<ReadyTask>,pub prepare:Vec<PrepareTask>,
    pub events:Vec<room::Event>,pub refusals:Vec<RefusedRecord>,pub deferred_reads:Vec<DeferredRead>,
}
fn bad(message:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("P10B receive host: {message}"))}
fn account_id(value:&str)->io::Result<Account>{
    if value.len()!=36{return Err(bad("canonical authenticated UUID"));}
    let mut out=[0u8;16];let mut cursor=0;let mut high=None;
    for(index,byte)in value.bytes().enumerate(){
        if [8,13,18,23].contains(&index){if byte!=b'-'{return Err(bad("canonical UUID separators"));}continue;}
        let nibble=match byte{b'0'..=b'9'=>byte-b'0',b'a'..=b'f'=>byte-b'a'+10,_=>return Err(bad("canonical UUID hexadecimal"))};
        if let Some(h)=high.take(){out[cursor]=h*16+nibble;cursor+=1;}else{high=Some(nibble);}
    }
    if cursor!=16||high.is_some()||out==[0;16]{return Err(bad("authenticated UUID bytes"));}Ok(Account(out))
}
pub(super) fn bound_call<'a>(s:&'a Session,bindings:&BTreeMap<u32,[u8;32]>)->io::Result<(Call,i32,&'a str)>{
    if s.id==0||!s.training_account_ready(){return Err(bad("actual Account not ready"));}
    let identity=s.identity.as_ref().ok_or_else(||bad("actual identity"))?;
    let account=account_id(&identity.account_id)?;
    if identity.database_id<=0{return Err(bad("actual native database"));}
    let revision=u32::try_from(s.ammo_service.as_ref().ok_or_else(||bad("actual profile cursor"))?.revision()).map_err(|_|bad("profile revision range"))?;
    if !(13..=i32::MAX as u32).contains(&revision){return Err(bad("profile revision range"));}
    let source=*bindings.get(&s.id).filter(|v|**v!=[0;32]).ok_or_else(||bad("trusted source binding missing"))?;
    Ok((Call{caller:room::AuthLease{account,generation:u64::from(s.id)},
        channel:current::Channel{session:s.id,generation:s.training_account_generation()},
        profile:current::ProfileStamp{revision,source_binding:source},expected_revision:revision},identity.database_id,&identity.name))
}
fn unique_session(sessions:&[Session],account:Account)->io::Result<usize>{
    let mut found=None;
    for(index,s)in sessions.iter().enumerate(){
        if s.identity.as_ref().is_some_and(|p|account_id(&p.account_id).ok()==Some(account)){
            if found.replace(index).is_some(){return Err(bad("duplicate live account Session"));}
        }
    }found.ok_or_else(||bad("publication recipient absent"))
}
/// Current trusted projection only. Idle authenticated Sessions that have never
/// bound Controller are not yet native room recipients. In contrast, every
/// retained room member must have its actual current Session/fact represented.
pub(super) fn current_facts(sessions:&[Session],engine:&Controller,selected:&BTreeMap<Account,NativeFacts>)->io::Result<BTreeMap<Account,NativeFacts>>{
    let mut out=BTreeMap::new();
    for s in sessions{
        let Some(identity)=&s.identity else{continue;};let account=account_id(&identity.account_id)?;
        let lease=room::AuthLease{account,generation:u64::from(s.id)};
        let channel=current::Channel{session:s.id,generation:s.training_account_generation()};
        if engine.is_current_recipient(lease,channel,identity.database_id){
            let fact=selected.get(&account).filter(|f|f.database_id==identity.database_id).ok_or_else(||bad("bound recipient current facts missing"))?;
            if out.insert(account,fact.clone()).is_some(){return Err(bad("duplicate bound facts"));}
        }
    }
    for r in engine.registry().rooms(){for member in r.members(){
        let fact=out.get_mut(&member.account()).ok_or_else(||bad("room member current facts missing"))?;
        let current=if let Some(ready)=member.ready(){let i=unique_session(sessions,member.account())?;
            ready.owner()==member.account()&&fact.selected.as_ref()==Some(ready)
                &&sessions[i].ammo_service.as_ref().is_some_and(|s|s.revision()==u64::from(ready.revision()))
        }else{false};
        // A prior NotReady in this same compound frame has already invalidated
        // the pre-frame external cache. Never resurrect it. Stale references
        // also project None: the real Controller rejects another TeamReady,
        // while explicit NotReady/Leave can still clear the stale member.
        if !current{fact.selected=None;fact.descriptor.clear();}
    }}Ok(out)
}
fn bounds(s:&Session)->io::Result<()>{
    if s.outbox.len()>native::MAX_OUTBOX||s.outbox.iter().any(|b|b.is_empty()||b.len()>512)
        ||s.outbox.iter().try_fold(0usize,|n,b|n.checked_add(b.len())).is_none_or(|n|n>native::MAX_OUTBOX_BYTES){return Err(bad("native outbox bound"));}Ok(())
}
fn insert(s:&mut Session,at:usize,bodies:Vec<Vec<u8>>)->io::Result<usize>{
    if at>s.outbox.len(){return Err(bad("caller outbox insertion offset"));}bounds(s)?;
    if s.outbox.len().checked_add(bodies.len()).is_none_or(|n|n>native::MAX_OUTBOX)
        ||bodies.iter().any(|b|b.is_empty()||b.len()>512)
        ||s.outbox.iter().chain(&bodies).try_fold(0usize,|n,b|n.checked_add(b.len())).is_none_or(|n|n>native::MAX_OUTBOX_BYTES){return Err(bad("native insertion bound"));}
    let n=bodies.len();for(offset,body)in bodies.into_iter().enumerate(){s.outbox.insert(at+offset,body);}bounds(s)?;Ok(n)
}
fn source_failure(reason:&Refusal)->u8{
    let domain=match reason{Refusal::Domain(e)|Refusal::Current(current::Error::Domain(e))=>Some(*e),
        Refusal::Adapter(crate::training091::adapter::Error::Domain(e))=>Some(*e),_=>None};
    match domain{Some(room::Error::NoRoom|room::Error::NotMember)=>2,Some(room::Error::AlreadyClaimed|room::Error::BusyBattle)=>3,
        Some(room::Error::RoomFull|room::Error::InvalidTeam)=>5,Some(room::Error::ClosedRoom)=>10,
        Some(room::Error::BadSettings|room::Error::BadWriterRef|room::Error::BadIdentity)=>6,
        _=>if matches!(reason,Refusal::BadArgs|Refusal::Unsupported){6}else{9}}
}
fn refusal_bodies(reply:Reply,reason:&Refusal)->io::Result<Vec<Vec<u8>>>{
    // The enum values come from source; this choice of error mapping is LAB.
    Ok(match reply{Reply::Plain(id)=>vec![native::plain_response(id,native::CommandResult::Failure,"P10B_ROOM_REFUSED").map_err(|_|bad("failure callback codec"))?],
        Reply::JoinedOrFailure|Reply::JoinEvent=>vec![native::join_failure(source_failure(reason))],
        Reply::ListStream|Reply::RosterStream=>Vec::new()})
}
fn stream_kind(reply:Reply)->Option<flight::Kind>{match reply{Reply::ListStream=>Some(flight::Kind::Listing),Reply::RosterStream=>Some(flight::Kind::Preview),_=>None}}
fn stream_context(engine:&Controller,call:Call,request:&Request)->io::Result<(flight::ReadRevision,flight::StreamContext)>{
    let kind=stream_kind(request.reply).ok_or_else(||bad("fixed read route"))?;
    let read=match kind{flight::Kind::Listing=>flight::ReadRevision::Listing(engine.read_revision()),flight::Kind::Preview=>{
        let ingress::Kind::Preview{room}=request.kind else{return Err(bad("preview typed request"));};
        let native=u32::try_from(room).map_err(|_|bad("preview native room"))?;
        let(key,revision)=engine.room_read(native).ok_or_else(||bad("preview current room"))?;
        flight::ReadRevision::Preview{room:key,revision}
    }};
    // Closed enum Debug representation under a versioned policy; never a
    // client-authored hash or claimed historical serialization.
    let mut h=Sha256::new();h.update(POLICY.as_bytes());h.update([0]);h.update(format!("{request:?}").as_bytes());
    let query:[u8;32]=h.finalize().into();
    let context=flight::StreamContext::capture(call.caller,flight::Channel{session:call.channel.session,generation:call.channel.generation},
        kind,query,read,call.profile.revision,call.profile.source_binding).map_err(|_|bad("read origin"))?;Ok((read,context))
}
fn fail(out:&mut RoomReceived,call:Call,request:Request,refusal:Refusal)->io::Result<Vec<Vec<u8>>>{
    if out.refusals.len()>=MAX_RECORDS{return Err(bad("refusal budget"));}
    let bodies=refusal_bodies(request.reply,&refusal)?;
    out.diagnostics.push(format!("P10B_ROOM_REFUSED session={} reply={:?} reason={refusal:?} policy={POLICY}",call.channel.session,request.reply));
    out.refusals.push(RefusedRecord{call,request,refusal});Ok(bodies)
}

/// Mutates only the outer caller's staged Session clones. On ANY error the
/// caller must discard all clones, including its staged Controller/World.
/// For async Ready/abort/finish publication pass caller=None to append all.
pub(super) fn stage_batch(sessions:&mut [Session],engine:&Controller,batch:&Batch,
    bindings:&BTreeMap<u32,[u8;32]>,facts:&BTreeMap<Account,NativeFacts>,
    caller:Option<(u32,usize)>,stream:Option<&flight::StreamContext>)->io::Result<usize>{
    if batch.bodies.len()>room::MAX_ACCOUNTS{return Err(bad("publication recipient budget"));}let mut inserted=0;
    for(account,bodies)in &batch.bodies{
        if bodies.len()>native::MAX_OUTBOX||bodies.iter().any(|b|b.is_empty()||b.len()>512)
            ||bodies.iter().try_fold(0usize,|n,b|n.checked_add(b.len())).is_none_or(|n|n>native::MAX_OUTBOX_BYTES){return Err(bad("publication body budget"));}
        let target=unique_session(sessions,*account)?;let(peer,database,name)=bound_call(&sessions[target],bindings)?;
        if !engine.is_current_recipient(peer.caller,peer.channel,database)||facts.get(account).is_none_or(|f|f.database_id!=database){return Err(bad("publication origin mismatch"));}
        if let Some(room::Claim::Room(key))=engine.registry().claim(*account){
            if engine.registry().room(key).and_then(|r|r.members().find(|m|m.account()==*account)).is_none_or(|m|m.name()!=name){return Err(bad("publication name mismatch"));}
        }
        if let Some(context)=stream{
            let Some((id,at))=caller else{return Err(bad("fixed stream insertion origin"));};if id!=sessions[target].id{return Err(bad("fixed stream foreign recipient"));}
            sessions[target].queue_training_stream(context.clone(),bodies.clone(),at)?;inserted+=bodies.len();
        }else{
            let at=caller.filter(|(id,_)|*id==sessions[target].id).map_or(sessions[target].outbox.len(),|(_,at)|at);
            let count=insert(&mut sessions[target],at,bodies.clone())?;if caller.is_some_and(|(id,_)|id==sessions[target].id){inserted+=count;}
        }
    }Ok(inserted)
}

pub(super) fn receive_room_frame(sessions:&mut Vec<Session>,engine:&mut Controller,receiver_session:u32,
    frame:&Frame,world:&World,source_bindings:&BTreeMap<u32,[u8;32]>,selectedfacts:&BTreeMap<Account,NativeFacts>,
    now:Instant,now_ms:u64)->io::Result<RoomReceived>{
    if sessions.is_empty()||sessions.len()>room::MAX_ACCOUNTS||source_bindings.len()>room::MAX_ACCOUNTS||selectedfacts.len()>room::MAX_ACCOUNTS{
        return Err(bad("bounded live table"));}
    let mut ids=BTreeSet::new();if sessions.iter().any(|s|!ids.insert(s.id)){return Err(bad("duplicate Session ID"));}
    let index=sessions.iter().position(|s|s.id==receiver_session).ok_or_else(||bad("receiver absent"))?;
    let mut next=sessions.clone();let mut controller=engine.clone();
    next[index].shared_refresh_world(world)?;
    let received=next[index].receive_training_collected(frame,now)?;
    if received.records.len()>MAX_RECORDS{return Err(bad("record budget"));}
    for record in &received.records{if let Reply::Plain(id)=record.request.reply{next[index].claim_training_request(id)?;}}
    let mut out=RoomReceived{close:received.close,diagnostics:received.diagnostics,..RoomReceived::default()};
    let mut added=0usize;let mut prior=0usize;let original=next[index].outbox.len();
    for record in received.records{
        if record.outbox_index<prior||record.outbox_index>original{return Err(bad("ordered outbox record"));}prior=record.outbox_index;
        let at=record.outbox_index.checked_add(added).ok_or_else(||bad("insertion overflow"))?;
        let request=record.request;let(call,database,name)=bound_call(&next[index],source_bindings)?;
        if unique_session(&next,call.caller.account)?!=index||selectedfacts.get(&call.caller.account).is_none_or(|f|f.database_id!=database){return Err(bad("actual caller facts"));}
        if let Err(reason)=controller.bind(call.caller,call.channel,name.to_owned(),database,now_ms){
            added+=insert(&mut next[index],at,fail(&mut out,call,request,reason)?)?;continue;
        }
        let facts=current_facts(&next,&controller,selectedfacts)?;
        if matches!(request.kind,ingress::Kind::Ready{..})&&next[index].ammo_service.as_ref().is_none_or(|s|!s.idle()){
            added+=insert(&mut next[index],at,fail(&mut out,call,request,Refusal::Busy)?)?;continue;
        }
        if let Some(kind)=stream_kind(request.reply){
            if next[index].training_flights.as_ref().ok_or_else(||bad("training stream ledger absent"))?.busy(kind){
                // Validate through the real command layer on a disposable
                // clone. Unsupported521/bad pages cannot hide in deferred state;
                // preview alias allocation and output are never committed here.
                if let Err(reason)=controller.clone().apply(call,request.clone(),&facts,now_ms){
                    added+=insert(&mut next[index],at,fail(&mut out,call,request,reason)?)?;continue;
                }
                if out.deferred_reads.iter().any(|d|stream_kind(d.request.reply)==Some(kind)){
                    added+=insert(&mut next[index],at,fail(&mut out,call,request,Refusal::Busy)?)?;
                }else{
                    match stream_context(&controller,call,&request){
                        Ok((read,context))=>out.deferred_reads.push(DeferredRead{call,request,read,context}),
                        Err(_)=>{added+=insert(&mut next[index],at,fail(&mut out,call,request,Refusal::BadArgs)?)?;}
                    }
                }continue;
            }
        }
        let batch=match controller.apply(call,request.clone(),&facts,now_ms){Ok(batch)=>batch,Err(reason)=>{
            added+=insert(&mut next[index],at,fail(&mut out,call,request,reason)?)?;continue;
        }};
        if out.ready.len()+batch.ready.len()>room::MAX_ACCOUNTS||out.prepare.len()+batch.prepare.len()>room::MAX_ROOMS
            ||out.events.len()+batch.events.len()>MAX_RECORDS*16{return Err(bad("exported job/event budget"));}
        let context=if stream_kind(request.reply).is_some(){Some(stream_context(&controller,call,&request)?.1)}else{None};
        added+=stage_batch(&mut next,&controller,&batch,source_bindings,&facts,Some((receiver_session,at)),context.as_ref())?;
        out.ready.extend(batch.ready);out.prepare.extend(batch.prepare);out.events.extend(batch.events);
    }
    // All real Windows drain on clones. A late peer failure also rolls back
    // receiver ACK/history/IDs, Registry, aliases, callbacks and job descriptors.
    for s in &mut next{if s.training_opt_in{bounds(s)?;}s.drain_outbox()?;}
    *sessions=next;*engine=controller;Ok(out)
}

#[cfg(test)]#[path="p10b_receive_host_tests.rs"]mod tests;
