//! P09D account service scheduling. External writes only run after the parent
//! Session::receive commits its complete cloned frame/piggyback tree.
use super::*;
use crate::{account091,ammo_service091 as codec,crew_service091 as crew_codec,identity091};

const MAX_COMMANDS:usize=512;
const MAX_PENDING:usize=4;

#[derive(Clone,Debug,PartialEq,Eq)]
enum Command {Ammo(codec::Request),Crew(crew_codec::Request)}
impl Command {
    fn id(&self)->i16 {match self {Self::Ammo(r)=>r.id,Self::Crew(r)=>r.id}}
    fn vehicle(&self)->i32 {match self {Self::Ammo(r)=>r.vehicle_inventory_id(),Self::Crew(r)=>r.vehicle_inventory_id}}
    fn kind(&self)->&'static str {match self {Self::Ammo(_)=>"AMMO",Self::Crew(_)=>"CREW"}}
    fn validate_supported(&self)->io::Result<()> {match self {Self::Ammo(r)=>r.validate_supported(),Self::Crew(r)=>r.validate_supported()}}
}

#[derive(Clone,Debug,PartialEq,Eq)]
pub(super) struct State {
    revision:u64,wire_revision:i64,prefix:String,crew_enabled:bool,
    seen:Vec<i16>,pending:VecDeque<Command>,inflight:Option<Command>,
}
impl State {
    pub(super) fn new(binding:codec::Metadata,crew_enabled:bool)->Self {
        let mut random=[0;16];OsRng.fill_bytes(&mut random);
        let prefix=random.iter().map(|byte|format!("{byte:02x}")).collect();
        Self{revision:binding.revision,wire_revision:binding.wire_revision,prefix,crew_enabled,
             seen:Vec::new(),pending:VecDeque::new(),inflight:None}
    }
    pub(super) fn crew_enabled(&self)->bool {self.crew_enabled}
    pub(super) fn used_id(&self,id:i16)->bool {self.seen.contains(&id)}
    fn command_key(&self,request:&Command)->String {
        let card=match request {Command::Ammo(_)=>"p09d",Command::Crew(_)=>"p04d"};
        format!("{card}:{}:{}",self.prefix,request.id())
    }
}

fn available(session:&Session)->io::Result<()> {
    if !session.active || !session.account_ready || session.identity.is_none() || session.hangar.is_none()
        || session.sync_mask!=7 || session.ammo_service.is_none() || session.arena_base || session.drive.is_some()
        || session.map_drive || session.shared.is_some() || session.drive_account_policy.is_some() {
        return Err(invalid());
    }
    Ok(())
}

pub(super) fn enqueue(session:&mut Session,request:codec::Request,events:&mut Vec<String>)->io::Result<()> {
    enqueue_command(session,Command::Ammo(request),events)
}
pub(super) fn enqueue_crew(session:&mut Session,request:crew_codec::Request,events:&mut Vec<String>)->io::Result<()> {
    if !session.ammo_service.as_ref().is_some_and(State::crew_enabled) {return Err(invalid());}
    enqueue_command(session,Command::Crew(request),events)
}
fn enqueue_command(session:&mut Session,request:Command,events:&mut Vec<String>)->io::Result<()> {
    available(session)?;
    let state=session.ammo_service.as_mut().ok_or_else(invalid)?;
    let id=request.id();let kind=request.kind();
    if id==202 || state.seen.contains(&id) || state.seen.len()>=MAX_COMMANDS
        || session.request_ids.contains(&id) || session.unsupported_request_ids.contains(&id)
        || state.pending.len()+usize::from(state.inflight.is_some())>=MAX_PENDING || session.outbox.len()>120 {
        return Err(invalid());
    }
    state.seen.push(id);
    if request.validate_supported().is_err() {
        session.outbox.push_back(crate::hangar091::unavailable_response(id)?);
        events.push(format!("{kind}_SERVICE_REJECTED session={} request={id} result=-10 reason=unsupported_layout domain_applied=false",session.id));
    } else {
        events.push(format!("{kind}_SERVICE_PENDING session={} request={id} vehicle={} mutation_started=false",session.id,request.vehicle()));
        state.pending.push_back(request);
    }
    Ok(())
}

pub(super) fn refresh(session:&mut Session,request:account091::Request,revision:i64,persistent_hash:i32,
                      events:&mut Vec<String>)->io::Result<()> {
    available(session)?;
    let state=session.ammo_service.as_mut().ok_or_else(invalid)?;
    if !(1..=state.wire_revision).contains(&revision) || request.command!=100 || request.id<=0
        || state.seen.contains(&request.id) || state.seen.len()>=MAX_COMMANDS
        || session.request_ids.contains(&request.id) || session.unsupported_request_ids.contains(&request.id)
        || session.outbox.len()>=128 {
        return Err(invalid());
    }
    // A request can have left the client before the worker committed an update
    // already queued ahead of this reply. Original #717 AccountSyncData
    // __onSyncResponse:163 compares ext.prevRev against CURRENT self.revision,
    // not the revision carried in its original request. Reliable queue order
    // therefore requires a no-change response at the current published cursor.
    // Only earlier cursors from this session's monotonic sequence are accepted;
    // a future/zero cursor never changes authoritative state.
    let published_revision=state.wire_revision;
    let body=codec::refresh_response(request.id,published_revision)?;
    state.seen.push(request.id);session.outbox.push_back(body);
    events.push(format!("AMMO_ACCOUNT_REFRESH session={} request={} requested_revision={revision} revision={published_revision} cache_hint={persistent_hash} changed=false",session.id,request.id));
    Ok(())
}

pub(super) struct Job {
    session_id:u32,account_id:String,request_id:i16,
    receiver:mpsc::Receiver<io::Result<identity091::AmmoReply>>,
}

/// At most one worker exists across active and retired sessions. Retain a
/// retired worker until its bounded request returns; never launch a second DB
/// writer or hand a new login stale data while the prior commit is ambiguous.
pub(super) fn start(session:&mut Session,slot:&mut Option<Job>,config:Arc<identity091::Config>)->io::Result<()> {
    if slot.is_some() {return Ok(());}
    let Some(state)=session.ammo_service.as_ref() else {return Ok(());};
    let Some(request)=state.pending.front().cloned() else {return Ok(());};
    available(session)?;
    if state.inflight.is_some() || session.outbox.len()>126 {return Err(invalid());}
    let profile=session.identity.clone().ok_or_else(invalid)?;
    let (revision,wire_revision,key)=(state.revision,state.wire_revision,state.command_key(&request));
    let account_id=profile.account_id.clone();let request_id=request.id();let kind=request.kind();
    let (sender,receiver)=mpsc::sync_channel(1);
    let dispatched=request.clone();
    thread::Builder::new().name("local-account-service".to_owned()).spawn(move || {
        let outcome=match dispatched {
            Command::Ammo(request)=>config.service_ammunition(&profile,&key,revision,wire_revision,request.arguments),
            Command::Crew(request)=>config.recruit_crew(&profile,&key,revision,wire_revision,request),
        };
        let _=sender.send(outcome); // A stopped gateway has no native recipient.
    })?;
    let state=session.ammo_service.as_mut().ok_or_else(invalid)?;
    state.pending.pop_front();state.inflight=Some(request);
    *slot=Some(Job{session_id:session.id,account_id,request_id,receiver});
    println!("{kind}_SERVICE_DISPATCH session={} request={request_id} source_revision={revision} wire_revision={wire_revision} shared_writer=true",session.id);
    Ok(())
}

fn apply(session:&mut Session,request_id:i16,reply:identity091::AmmoReply)->io::Result<()> {
    available(session)?;
    let mut next=session.clone();
    let state=next.ammo_service.as_mut().ok_or_else(invalid)?;
    if state.inflight.as_ref().map(Command::id)!=Some(request_id) {return Err(invalid());}
    let kind=state.inflight.as_ref().ok_or_else(invalid)?.kind();
    let bodies=if reply.serviced {
        if reply.revision!=state.revision.checked_add(1).ok_or_else(invalid)?
            || reply.wire_revision!=state.wire_revision.checked_add(1).ok_or_else(invalid)? {return Err(invalid());}
        codec::response(request_id,&reply.update)?
    } else {
        if reply.revision!=state.revision || reply.wire_revision!=state.wire_revision || !reply.update.is_empty() {
            return Err(invalid());
        }
        vec![crate::hangar091::unavailable_response(request_id)?]
    };
    if next.outbox.len()+bodies.len()>128 {return Err(invalid());}
    state.revision=reply.revision;state.wire_revision=reply.wire_revision;state.inflight=None;
    next.outbox.extend(bodies);next.drain_outbox()?;
    *session=next;
    println!("{kind}_SERVICE_RESULT session={} request={request_id} serviced={} revision={} wire_revision={} replayed={} result={} update_bytes={} response_queued=true",
        session.id,reply.serviced,reply.revision,reply.wire_revision,reply.replayed,reply.result_code,reply.update.len());
    Ok(())
}

pub(super) fn complete(session:Option<&mut Session>,slot:&mut Option<Job>)->io::Result<()> {
    let Some(job)=slot.as_ref() else {return Ok(());};
    let result=match job.receiver.try_recv() {
        Ok(value)=>value,
        Err(mpsc::TryRecvError::Empty)=>return Ok(()),
        Err(mpsc::TryRecvError::Disconnected)=>Err(io::Error::new(io::ErrorKind::BrokenPipe,"ammunition worker stopped")),
    };
    let job=slot.take().ok_or_else(invalid)?;
    let Some(session)=session.filter(|session|session.id==job.session_id
        && session.identity.as_ref().is_some_and(|profile|profile.account_id==job.account_id)) else {
        println!("AMMO_SERVICE_RETIRED_RESULT session={} request={} native_delivery=false result_available={}",job.session_id,job.request_id,result.is_ok());
        return Ok(());
    };
    apply(session,job.request_id,result?)
}

#[cfg(test)]
mod tests {
    use super::*;
    fn ready(now:Instant)->Session {
        // Synthetic scheduling fixture only; no native UI/compatibility claim.
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let directory=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/p09d")
            .join(format!("session-{}-{stamp}",std::process::id()));
        fs::create_dir_all(&directory).unwrap();
        for name in ["state.bin","shop.bin"] {fs::write(directory.join(name),b"\x80\x02}.").unwrap();}
        fs::write(directory.join("dossier.bin"),b"\x80\x02(K\x00]t.").unwrap();
        let mut session=Session::new(1,[1;16],"127.0.0.1:40000".parse().unwrap(),now);
        session.identity=Some(Arc::new(identity091::Profile{account_id:"00000000-0000-0000-0000-000000000001".into(),
            database_id:900001,name:"TestAmmo".into(),fixture_dir:directory.clone()}));
        session.hangar=Some(Arc::new(crate::hangar091::Fixtures::load_interactive(&directory).unwrap()));
        session.active=true;session.account_ready=true;session.sync_mask=7;session.rx=1;
        session.tx=Window::interactive();session.base_peer=Some("127.0.0.1:40001".parse().unwrap());
        session.ammo_service=Some(State::new(codec::Metadata{revision:5,wire_revision:1},false));session
    }
    fn request(id:i16)->codec::Request {codec::Request{id,arguments:[1,1,6,2570,20,2826,0,3082,0,6,0,0,0,0,0,0]}}
    fn packet(request:codec::Request)->Vec<u8> {
        let mut body=vec![0x97,72,0];body.extend(request.id.to_le_bytes());body.extend(108i16.to_le_bytes());
        body.extend(16u32.to_le_bytes());for arg in request.arguments {body.extend(arg.to_le_bytes());}body
    }
    fn ready_crew(now:Instant)->Session {
        let mut session=ready(now);session.ammo_service=Some(State::new(codec::Metadata{revision:6,wire_revision:1},true));session
    }
    fn crew_request(id:i16)->crew_codec::Request {
        crew_codec::Request{id,shop_revision:3,vehicle_inventory_id:1,slot:1,tariff_index:0}
    }
    fn crew_packet(request:crew_codec::Request)->Vec<u8> {
        let mut body=vec![crew_codec::CANDIDATE_METHOD,24,0];body.extend(request.id.to_le_bytes());body.extend(309i16.to_le_bytes());
        body.extend(request.shop_revision.to_le_bytes());body.extend(request.vehicle_inventory_id.to_le_bytes());
        body.extend(request.slot.to_le_bytes());body.extend(request.tariff_index.to_le_bytes());body
    }
    fn crew_reply(revision:u64,wire:i64)->identity091::AmmoReply {
        let mut delta=b"\x80\x02}(U\x07prevRevJ".to_vec();delta.extend((wire as i32-1).to_le_bytes());
        delta.extend(b"U\x03revJ");delta.extend((wire as i32).to_le_bytes());delta.extend(b"u.");
        identity091::AmmoReply{serviced:true,revision,wire_revision:wire,update:delta,replayed:false,result_code:0}
    }
    fn refresh_packet(id:i16,revision:i64)->Vec<u8> {
        let mut body=vec![0x8e,20,0];body.extend(id.to_le_bytes());body.extend(100i16.to_le_bytes());
        body.extend(revision.to_le_bytes());body.extend([0;8]);body
    }
    fn frame(session:&Session,n:u32,payload:&[u8])->Frame {
        let mut clear=vec![0x58,4,1];clear.extend(session.token.to_le_bytes());clear.extend(payload);
        clear.extend(n.to_le_bytes());clear.extend(0u32.to_le_bytes());transport091::parse_interactive(&clear).unwrap()
    }
    fn reply(serviced:bool)->identity091::AmmoReply {
        identity091::AmmoReply{serviced,revision:if serviced{6}else{5},wire_revision:if serviced{2}else{1},
            update:if serviced {b"\x80\x02}(U\x07prevRevK\x01U\x03revK\x02u.".to_vec()}else{vec![]},
            replayed:false,result_code:if serviced{0}else{-10}}
    }
    fn inflight(session:&mut Session,id:i16) {
        enqueue(session,request(id),&mut vec![]).unwrap();
        let state=session.ammo_service.as_mut().unwrap();state.inflight=state.pending.pop_front();
    }

    #[test]
    fn valid_receive_queues_once_and_transport_duplicate_has_no_extra_effect() {
        let now=Instant::now();let mut session=ready(now);
        let frame=frame(&session,1,&packet(request(226)));
        session.receive(&frame,now).unwrap();
        assert_eq!(session.ammo_service.as_ref().unwrap().pending.len(),1);
        assert!(session.ammo_service.as_ref().unwrap().inflight.is_none());
        assert_eq!(session.ammo_service.as_ref().unwrap().revision,5);
        let before=session.ammo_service.clone();session.receive(&frame,now).unwrap();
        assert_eq!(session.ammo_service,before);assert_eq!(session.tx.len(),0);
    }

    #[test]
    fn malformed_tail_and_later_invalid_piggyback_roll_back_pending_command() {
        let now=Instant::now();let ready=ready(now);let mut payload=packet(request(226));payload.push(0xff);
        let bad_tail=frame(&ready,1,&payload);
        let mut bad_parent=frame(&ready,2,&[0xff]);bad_parent.piggybacks.push(frame(&ready,1,&packet(request(226))));
        for frame in [bad_tail,bad_parent] {
            let mut session=ready.clone();assert!(session.receive(&frame,now).is_err());
            assert_eq!(session.ammo_service,ready.ammo_service);assert_eq!(session.rx,ready.rx);
            assert_eq!(session.received,ready.received);assert_eq!(session.tx.len(),0);
        }
    }

    #[test]
    fn multiple_commands_are_bounded_and_duplicate_id_rolls_back_bundle() {
        let now=Instant::now();let ready=ready(now);
        let mut session=ready.clone();let good=[packet(request(226)),packet(request(227))].concat();
        session.receive(&frame(&session,1,&good),now).unwrap();assert_eq!(session.ammo_service.as_ref().unwrap().pending.len(),2);
        for ids in [vec![226,226],vec![226,227,228,229,230]] {
            let mut session=ready.clone();let wire:Vec<u8>=ids.into_iter().flat_map(|id|packet(request(id))).collect();
            assert!(session.receive(&frame(&session,1,&wire),now).is_err());assert_eq!(session.ammo_service,ready.ammo_service);
        }
    }

    #[test]
    fn semantic_rejection_is_native_unavailable_without_pending_or_revision_change() {
        let now=Instant::now();let mut session=ready(now);let mut unsupported=request(226);unsupported.arguments[4]=97;
        session.receive(&frame(&session,1,&packet(unsupported)),now).unwrap();
        let state=session.ammo_service.as_ref().unwrap();assert!(state.pending.is_empty());assert_eq!(state.revision,5);
        let clear=session.tx.due(now,session.rx).unwrap().unwrap().2;
        let frame=transport091::parse_interactive(&clear).unwrap();
        assert_eq!(frame.body,crate::hangar091::unavailable_response(226).unwrap());
    }

    #[test]
    fn committed_result_queues_update_before_success_and_advances_exact_revision() {
        let now=Instant::now();let mut session=ready(now);inflight(&mut session,226);
        apply(&mut session,226,reply(true)).unwrap();
        let state=session.ammo_service.as_ref().unwrap();assert_eq!((state.revision,state.wire_revision),(6,2));assert!(state.inflight.is_none());
        let first=session.tx.due(now,session.rx).unwrap().unwrap().2;
        let second=session.tx.due(now,session.rx).unwrap().unwrap().2;
        assert_eq!(transport091::parse_interactive(&first).unwrap().body[1],0x57);
        assert_eq!(transport091::parse_interactive(&second).unwrap().body,codec::success_response(226).unwrap());
    }

    #[test]
    fn failed_backend_result_preserves_revision_and_unverified_replies_preserve_clone() {
        let now=Instant::now();let mut session=ready(now);inflight(&mut session,226);
        apply(&mut session,226,reply(false)).unwrap();assert_eq!(session.ammo_service.as_ref().unwrap().revision,5);
        for mutation in 0..4 {
            let mut session=ready(now);inflight(&mut session,226);let before=session.ammo_service.clone();
            let mut result=reply(true);match mutation {0=>result.revision=7,1=>result.wire_revision=3,
                2=>result.update=vec![0;241],_=>result.update=b"\x80\x02].".to_vec()}
            assert!(apply(&mut session,226,result).is_err());assert_eq!(session.ammo_service,before);assert_eq!(session.tx.len(),0);
        }
    }

    #[test]
    fn refresh_uses_current_revision_and_cannot_reuse_service_request_id() {
        let now=Instant::now();let mut session=ready(now);inflight(&mut session,226);apply(&mut session,226,reply(true)).unwrap();
        for (id,revision) in [(226,2),(227,0),(227,3)] {
            assert!(refresh(&mut session,account091::Request{id,command:100},revision,0,&mut vec![]).is_err());
        }
        refresh(&mut session,account091::Request{id:227,command:100},2,-123,&mut vec![]).unwrap();
        assert_eq!(session.outbox.back().unwrap(),&codec::refresh_response(227,2).unwrap());
    }

    #[test]
    fn stale_refresh_arriving_after_commit_advances_receive_and_follows_update() {
        let now=Instant::now();let mut session=ready(now);inflight(&mut session,226);
        apply(&mut session,226,reply(true)).unwrap();
        // The client formed this rev1 packet before update2 was delivered.
        let late=frame(&session,1,&refresh_packet(227,1));
        session.receive(&late,now).unwrap();assert_eq!(session.rx,2);
        let before=session.ammo_service.clone();let pending=session.tx.len();
        session.receive(&late,now).unwrap();assert_eq!(session.ammo_service,before);assert_eq!(session.tx.len(),pending);
        let bodies:Vec<Vec<u8>>=(0..3).map(|_| {
            let clear=session.tx.due(now,session.rx).unwrap().unwrap().2;
            transport091::parse_interactive(&clear).unwrap().body
        }).collect();
        assert_eq!(bodies[0][1],0x57);
        assert_eq!(bodies[1],codec::success_response(226).unwrap());
        assert_eq!(bodies[2],codec::refresh_response(227,2).unwrap());
        assert_eq!(session.ammo_service.as_ref().unwrap().revision,6);
    }

    #[test]
    fn refresh_during_inflight_precedes_later_update_and_bad_tail_rolls_back() {
        let now=Instant::now();let mut session=ready(now);inflight(&mut session,226);
        let before=session.ammo_service.clone();let mut bad=refresh_packet(227,1);bad.push(0xff);
        assert!(session.receive(&frame(&session,1,&bad),now).is_err());
        assert_eq!(session.ammo_service,before);assert_eq!(session.rx,1);assert_eq!(session.tx.len(),0);
        session.receive(&frame(&session,1,&refresh_packet(227,1)),now).unwrap();
        apply(&mut session,226,reply(true)).unwrap();
        let bodies:Vec<Vec<u8>>=(0..3).map(|_| {
            let clear=session.tx.due(now,session.rx).unwrap().unwrap().2;
            transport091::parse_interactive(&clear).unwrap().body
        }).collect();
        assert_eq!(bodies[0],codec::refresh_response(227,1).unwrap());
        assert_eq!(bodies[1][1],0x57);assert_eq!(bodies[2],codec::success_response(226).unwrap());
        assert_eq!(session.ammo_service.as_ref().unwrap().wire_revision,2);
    }

    #[test]
    fn worker_slot_retains_inflight_and_retired_result_never_applies_to_new_session() {
        let now=Instant::now();let mut old=ready(now);inflight(&mut old,226);
        let (sender,receiver)=mpsc::sync_channel(1);
        let mut slot=Some(Job{session_id:old.id,account_id:old.identity.as_ref().unwrap().account_id.clone(),request_id:226,receiver});
        complete(Some(&mut old),&mut slot).unwrap();assert!(slot.is_some());assert!(old.ammo_service.as_ref().unwrap().inflight.is_some());
        let mut next=ready(now);next.id=2;let before=next.ammo_service.clone();
        sender.send(Ok(reply(true))).unwrap();complete(Some(&mut next),&mut slot).unwrap();
        assert!(slot.is_none());assert_eq!(next.ammo_service,before);assert_eq!(next.tx.len(),0);
    }

    #[test]
    fn ambiguous_worker_failure_leaves_no_success_or_claimed_local_commit() {
        let now=Instant::now();let mut session=ready(now);inflight(&mut session,226);let before=session.ammo_service.clone();
        let (sender,receiver)=mpsc::sync_channel(1);let mut slot=Some(Job{session_id:session.id,
            account_id:session.identity.as_ref().unwrap().account_id.clone(),request_id:226,receiver});
        sender.send(Err(io::Error::new(io::ErrorKind::TimedOut,"test timeout"))).unwrap();
        assert!(complete(Some(&mut session),&mut slot).is_err());assert!(slot.is_none());
        assert_eq!(session.ammo_service,before);assert_eq!(session.tx.len(),0);
    }

    #[test]
    fn crew_candidate_requires_explicit_gate_and_preserves_full_frame_atomicity() {
        let now=Instant::now();let wire=crew_packet(crew_request(226));
        assert!(crate::hangar091::requests(&wire).is_err());assert!(crate::hangar091::requests_interactive(&wire).is_err());
        assert!(crate::hangar091::requests_ammo_service(&wire).is_err());
        let mut session=ready(now);let before=session.ammo_service.clone();
        assert!(session.receive(&frame(&session,1,&wire),now).is_err());assert_eq!(session.ammo_service,before);
        let original=ready_crew(now);
        let mut bad=wire.clone();bad.push(0xff);
        let mut invalid_parent=frame(&original,2,&[0xff]);invalid_parent.piggybacks.push(frame(&original,1,&wire));
        for incoming in [frame(&original,1,&bad),invalid_parent] {
            let mut session=original.clone();assert!(session.receive(&incoming,now).is_err());
            assert_eq!(session.ammo_service,original.ammo_service);assert_eq!(session.rx,1);assert_eq!(session.tx.len(),0);
        }
        let mut session=original.clone();let accepted=frame(&session,1,&wire);session.receive(&accepted,now).unwrap();
        let state=session.ammo_service.as_ref().unwrap();assert_eq!(state.pending.len(),1);assert!(state.inflight.is_none());
        assert_eq!(state.revision,6);let committed=session.ammo_service.clone();
        session.receive(&accepted,now).unwrap();assert_eq!(session.ammo_service,committed);
    }

    #[test]
    fn mixed_commands_have_one_fifo_revision_and_update_before_each_callback() {
        let now=Instant::now();
        for crew_first in [false,true] {
            let mut session=ready_crew(now);
            let wires=if crew_first {[crew_packet(crew_request(226)),packet(request(227))]}
                else {[packet(request(226)),crew_packet(crew_request(227))]};
            session.receive(&frame(&session,1,&wires.concat()),now).unwrap();
            let state=session.ammo_service.as_mut().unwrap();assert_eq!(state.pending.len(),2);
            let first=state.pending.front().unwrap();assert_eq!(first.kind(),if crew_first {"CREW"}else{"AMMO"});
            assert!(state.command_key(first).starts_with(if crew_first {"p04d:"}else{"p09d:"}));
            state.inflight=state.pending.pop_front();
            apply(&mut session,226,crew_reply(7,2)).unwrap();
            let state=session.ammo_service.as_mut().unwrap();assert_eq!(state.revision,7);assert_eq!(state.wire_revision,2);
            assert!(state.inflight.is_none());assert_eq!(state.pending.front().unwrap().id(),227);
            state.inflight=state.pending.pop_front();apply(&mut session,227,crew_reply(8,3)).unwrap();
            let state=session.ammo_service.as_ref().unwrap();assert_eq!(state.revision,8);assert_eq!(state.wire_revision,3);
            assert!(state.pending.is_empty());assert!(state.inflight.is_none());
            let bodies:Vec<Vec<u8>>=(0..4).map(|_| {
                let clear=session.tx.due(now,session.rx).unwrap().unwrap().2;
                transport091::parse_interactive(&clear).unwrap().body
            }).collect();
            assert_eq!(bodies[0][1],0x57);assert_eq!(bodies[1],codec::success_response(226).unwrap());
            assert_eq!(bodies[2][1],0x57);assert_eq!(bodies[3],codec::success_response(227).unwrap());
        }
    }

    #[test]
    fn crew_paid_invalid_slot_and_wrong_shop_reply_unavailable_without_worker() {
        let now=Instant::now();
        for change in 0..4 {
            let mut req=crew_request(226);match change {0=>req.tariff_index=1,1=>req.slot=0,2=>req.shop_revision=1,_=>req.vehicle_inventory_id=2};
            let mut session=ready_crew(now);session.receive(&frame(&session,1,&crew_packet(req)),now).unwrap();
            let state=session.ammo_service.as_ref().unwrap();assert!(state.pending.is_empty());assert!(state.inflight.is_none());assert_eq!(state.revision,6);
            let clear=session.tx.due(now,session.rx).unwrap().unwrap().2;
            assert_eq!(transport091::parse_interactive(&clear).unwrap().body,crate::hangar091::unavailable_response(226).unwrap());
        }
    }

    #[test]
    fn mixed_duplicates_malformed_tail_and_shared_queue_limit_roll_back_every_command() {
        let now=Instant::now();let original=ready_crew(now);
        let mut tail=[crew_packet(crew_request(226)),packet(request(227))].concat();tail.push(0xff);
        let overflow=[crew_packet(crew_request(226)),packet(request(227)),crew_packet(crew_request(228)),packet(request(229)),crew_packet(crew_request(230))].concat();
        for wire in [[crew_packet(crew_request(226)),packet(request(226))].concat(),
                     [packet(request(226)),crew_packet(crew_request(226))].concat(),tail,overflow] {
            let mut session=original.clone();assert!(session.receive(&frame(&session,1,&wire),now).is_err());
            assert_eq!(session.ammo_service,original.ammo_service);assert_eq!(session.rx,1);assert_eq!(session.tx.len(),0);
        }
    }

    #[test]
    fn crew_request_id_cannot_collide_with_later_language_or_account_refresh() {
        let now=Instant::now();let mut session=ready_crew(now);
        session.receive(&frame(&session,1,&crew_packet(crew_request(226))),now).unwrap();let before=session.ammo_service.clone();
        let mut language=vec![0x95,7,0];language.extend(226i16.to_le_bytes());language.extend([0xe8,3,2,b'r',b'u']);
        for wire in [language,refresh_packet(226,1)] {
            assert!(session.receive(&frame(&session,2,&wire),now).is_err());assert_eq!(session.ammo_service,before);assert_eq!(session.rx,2);
        }
        assert!(enqueue_crew(&mut session,crew_request(202),&mut vec![]).is_err());
    }

    #[test]
    fn crew_rejection_and_ambiguous_or_retired_worker_never_report_success() {
        let now=Instant::now();let mut session=ready_crew(now);
        enqueue_crew(&mut session,crew_request(226),&mut vec![]).unwrap();
        let state=session.ammo_service.as_mut().unwrap();state.inflight=state.pending.pop_front();
        let before=session.ammo_service.clone();let mut invalid_reply=crew_reply(8,2);
        assert!(apply(&mut session,226,invalid_reply).is_err());assert_eq!(session.ammo_service,before);assert_eq!(session.tx.len(),0);
        invalid_reply=crew_reply(7,3);assert!(apply(&mut session,226,invalid_reply).is_err());assert_eq!(session.ammo_service,before);
        let (sender,receiver)=mpsc::sync_channel(1);let mut slot=Some(Job{session_id:session.id,
            account_id:session.identity.as_ref().unwrap().account_id.clone(),request_id:226,receiver});
        complete(Some(&mut session),&mut slot).unwrap();assert!(slot.is_some());
        let mut next=ready_crew(now);next.id=2;let clean=next.ammo_service.clone();
        sender.send(Ok(crew_reply(7,2))).unwrap();complete(Some(&mut next),&mut slot).unwrap();
        assert_eq!(next.ammo_service,clean);assert_eq!(next.tx.len(),0);
        apply(&mut session,226,identity091::AmmoReply{serviced:false,revision:6,wire_revision:1,update:vec![],replayed:false,result_code:-10}).unwrap();
        assert_eq!(session.ammo_service.as_ref().unwrap().revision,6);
        let clear=session.tx.due(now,session.rx).unwrap().unwrap().2;
        assert_eq!(transport091::parse_interactive(&clear).unwrap().body,crate::hangar091::unavailable_response(226).unwrap());
    }
}
