//! Synthetic Session/transport flow tests using hash-pinned real SQLite DTOs.
//! No HTTP worker, process, client installation or native/UI claim is involved.
use super::*;
use crate::battle091::profile13::{self, Reply, Reservation};
use sha2::{Digest, Sha256};
use std::{path::{Path, PathBuf}, sync::atomic::{AtomicU64, Ordering}};

fn writer_result(index:usize) -> (Context, Request, Reply) {
    let path=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/profile13-writer-vectors.json");
    let raw=fs::read(path).unwrap();assert!(raw.len()<=65536);
    assert_eq!(format!("{:x}",Sha256::digest(&raw)),"39ce1c7a9bdd0a44b80013c91deeb086449b5794a498d2d73db0c3cdffcfd3d6");
    let data:serde_json::Value=serde_json::from_slice(&raw).unwrap();let row=&data["vectors"][index];let input=&row["request"];
    let context=Context{account_id:input["account_id"].as_str().unwrap().into(),native_database_id:input["native_database_id"].as_i64().unwrap().try_into().unwrap(),
        command_key:input["command_key"].as_str().unwrap().into(),expected_revision:input["expected_revision"].as_u64().unwrap(),run_id:input["run_id"].as_str().unwrap().into()};
    let battle=input["battle_id"].as_str().unwrap().rsplit_once(':').unwrap().1.parse::<u64>().unwrap();
    let request=match input["operation"].as_str().unwrap() {
        "admit"=>Request::Admit{battle,native_inventory_id:1},
        "finish"=>{
            assert_eq!(input["reason"],"manual_leave");
            Request::Finish{battle,native_inventory_id:1,reservation_id:input["reservation_id"].as_str().unwrap().into(),
                remaining_ap:input["remaining_ap"].as_u64().unwrap().try_into().unwrap(),
                terminal_hp:input["terminal_hp"].as_i64().unwrap().try_into().unwrap(),reason:FinishReason::ManualLeave}
        },
        operation=>panic!("unsupported test vector operation {operation}"),
    };
    let reply=profile13::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&context,&request).unwrap();
    (context,request,reply)
}
fn writer_admission() -> (Context, Request, Reply) {writer_result(2)}

fn synthetic_inputs() -> (PathBuf, Arc<crate::hangar091::Fixtures>) {
    // Tiny authored protocol2 primitives for scheduling/queue behavior only.
    // Retained under ignored test-runs for failed-test diagnosis, never served
    // to an actual client or passed off as profile13 ownership evidence.
    static SERIAL:AtomicU64=AtomicU64::new(0);
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/p08b-flow");
    fs::create_dir_all(&root).unwrap();
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let path=root.join(format!("session-{}-{stamp}-{}",std::process::id(),SERIAL.fetch_add(1,Ordering::Relaxed)));
    fs::create_dir(&path).unwrap();
    fs::write(path.join("state.bin"),b"\x80\x02}(U\x03revK\x01u.").unwrap();
    fs::write(path.join("shop.bin"),b"\x80\x02}(U\x03revK\x03u.").unwrap();
    fs::write(path.join("dossier.bin"),b"\x80\x02(K\x00]t.").unwrap();
    let fixtures=Arc::new(crate::hangar091::Fixtures::load_interactive(&path).unwrap());
    (path,fixtures)
}

fn account(now:Instant) -> Session {
    let(context,_,_)=writer_admission();let(path,fixtures)=synthetic_inputs();
    let mut s=Session::new(7,[7;16],"127.0.0.1:41707".parse().unwrap(),now);
    s.identity=Some(Arc::new(crate::identity091::Profile{account_id:context.account_id.clone(),database_id:context.native_database_id,
        name:"synthetic-owned-flow".into(),fixture_dir:path}));
    s.hangar=Some(fixtures);s.active=true;s.account_ready=true;s.sync_mask=7;s.rx=1;
    s.tx=Window::interactive();s.base_peer=Some("127.0.0.1:41708".parse().unwrap());
    s.login_attempt=Some(LoginAttempt::new(s.key,s.id,s.login_peer));
    s.ammo_service=Some(ammo_session::State::new(crate::ammo_service091::Metadata{revision:context.expected_revision,wire_revision:4},true)
        .with_transfer(true).with_cross_vehicle(true).with_roster_recruitment(true).with_progression(true)
        .with_dismissal(true).with_barracks(true).with_research(true));
    let mut c=Client::new(0);c.join_requested=false;c.hangar_since=Some(now);
    c.profile13=Some(service::State::new(context.run_id,context.expected_revision).unwrap());s.shared=Some(c);s
}

fn native(command:i16,first:i64,mask:i32)->Vec<u8> {
    let mut bytes=vec![0x8e,20,0,202,0];bytes.extend(command.to_le_bytes());bytes.extend(first.to_le_bytes());
    bytes.extend(mask.to_le_bytes());bytes.extend(0i32.to_le_bytes());bytes
}
fn frame_at(s:&Session,sequence:u32,payload:&[u8])->Frame {
    Frame{flags:0x458,sequence:Some(sequence),cumulative:Some(0),selective:vec![],
        body:[vec![1],s.token.to_le_bytes().to_vec(),payload.to_vec()].concat(),piggybacks:vec![]}
}
fn receive(s:&mut Session,payload:&[u8],now:Instant) {
    let frame=frame_at(s,s.rx,payload);assert!(!s.receive(&frame,now).unwrap());
}
fn completion(s:&Session)->service::Completion {
    let(context,request,reply)=writer_admission();
    let owner=s.identity.clone().unwrap();
    service::Completion{session:s.id,old_owner:owner.clone(),context,request,
        fresh:Some(service::Fresh{owner:Arc::new(crate::identity091::Profile{account_id:owner.account_id.clone(),database_id:owner.database_id,
            name:owner.name.clone(),fixture_dir:owner.fixture_dir.clone()}),fixtures:s.hangar.clone().unwrap(),
            binding:crate::ammo_service091::Metadata{revision:reply.revision,wire_revision:1}}),reply,refresh_error:None}
}
fn reserve(s:&mut Session,now:Instant)->Reservation {
    receive(s,&native(700,1,1),now);state(s).unwrap().in_flight=true;
    let done=completion(s);Dispatcher::deliver(s,done,now).unwrap();state(s).unwrap().reservation.clone().unwrap()
}
fn driving(s:&mut Session,reservation:&Reservation,now:Instant)->World {
    let owner=s.identity.as_ref().unwrap();let mut world=World::new(reservation.battle,now).unwrap();
    world.attach_owned(model::Identity{account:owner.account_id.clone(),database:owner.database_id,name:owner.name.clone()},s.id,&reservation.frozen).unwrap();
    world.attach(model::Identity{account:"synthetic-flow-peer".into(),database:2,name:"synthetic-flow-peer".into()},8).unwrap();
    world.start(now).unwrap();world.set_ready(0,s.id).unwrap();world.set_ready(1,8).unwrap();
    s.arena_base=true;s.outbox.clear();let c=s.shared.as_mut().unwrap();c.phase=Phase::Driving;c.correction=true;
    c.binding=Some((0,true));c.return_generation=1;c.view=Some(world.clone());world
}

#[test]
fn profile13_flow_join_stages_only_after_a_complete_native_frame_without_ack_or_writer() {
    let now=Instant::now();let mut s=account(now);let old=s.ammo_service.clone();
    receive(&mut s,&native(700,1,1),now);
    let c=s.shared.as_ref().unwrap();let p=c.profile13.as_ref().unwrap();
    assert_eq!(p.selection,Some(1));assert!(c.join_requested);assert!(!c.queue_announced);
    assert!(p.reservation.is_none() && p.pending_return.is_none() && !p.in_flight);assert_eq!(p.command_counter,0);
    assert_eq!(s.tx.len(),0);assert!(s.outbox.is_empty());assert_eq!(s.ammo_service,old);
    assert!(!s.arena_base);assert!(!s.ready_for_arena_base());
}

#[test]
fn profile13_flow_bad_later_piggyback_rolls_back_queue_selection_receive_history_and_ack() {
    let now=Instant::now();let mut s=account(now);let before=state(&mut s).unwrap().clone();
    s.tx.enqueue().unwrap();assert!(s.tx.due(now,s.rx).unwrap().is_some());
    let mut good=frame_at(&s,1,&native(700,1,1));good.cumulative=Some(1);
    let mut poisoned=frame_at(&s,2,&native(502,1,0));poisoned.cumulative=Some(1);
    poisoned.body[1]^=1;let mut parent=frame_at(&s,3,&[]);parent.cumulative=Some(1);parent.piggybacks=vec![good,poisoned];
    let revision=s.ammo_service.as_ref().unwrap().revision();let received=s.received.clone();let last_rx=s.last_rx;
    assert!(s.receive(&parent,now+Duration::from_secs(1)).is_err());
    assert_eq!(state(&mut s).unwrap(),&before);assert_eq!(s.rx,1);assert_eq!(s.received,received);assert_eq!(s.last_rx,last_rx);
    assert_eq!(s.tx.cumulative,0);assert_eq!(s.tx.len(),1);assert!(s.outbox.is_empty());
    assert_eq!(s.ammo_service.as_ref().unwrap().revision(),revision);assert!(!s.shared.as_ref().unwrap().join_requested);
}

#[test]
fn profile13_flow_cancel_inflight_admission_retains_unspent_cancelled_result_and_same_account_cursor() {
    let now=Instant::now();let mut s=account(now);
    receive(&mut s,&native(700,1,1),now);state(&mut s).unwrap().in_flight=true;
    // An ordinary periodic refresh remains legal while awaiting the writer.
    ammo_session::refresh(&mut s,crate::account091::Request{id:301,command:100},4,0,&mut vec![]).unwrap();
    assert_eq!(s.outbox.pop_back().unwrap(),crate::ammo_service091::refresh_response(301,4).unwrap());
    receive(&mut s,&native(701,0,0),now);assert!(s.outbox.is_empty());
    let done=completion(&s);let revision=done.reply.revision;Dispatcher::deliver(&mut s,done,now).unwrap();
    let c=s.shared.as_ref().unwrap();let p=c.profile13.as_ref().unwrap();let terminal=p.pending_return.as_ref().unwrap();
    assert_eq!(terminal.reason,FinishReason::Cancelled);assert_eq!((terminal.remaining_ap,terminal.terminal_hp),(20,90));
    assert!(p.reservation.is_some() && !p.in_flight && p.selection.is_none());
    assert_eq!(c.phase,Phase::Account);assert!(!c.queue_announced && !c.join_requested && !s.arena_base);
    assert!(s.outbox.is_empty());assert_eq!(s.ammo_service.as_ref().unwrap().revision(),revision);
    assert!(s.ammo_service.as_ref().unwrap().used_id(301));
    ammo_session::refresh(&mut s,crate::account091::Request{id:302,command:100},4,0,&mut vec![]).unwrap();
    assert_eq!(s.outbox.pop_back().unwrap(),crate::ammo_service091::refresh_response(302,4).unwrap());
    let mut events=vec![];
    ammo_session::enqueue_research(&mut s,crate::research_service091::Request{id:303,command:201,arguments:vec![3329,1,0]},&mut events).unwrap();
    assert!(s.ammo_service.as_ref().unwrap().idle());assert!(events.iter().any(|e|e.contains("reason=vehicle_reserved")));
    assert_eq!(s.outbox.pop_back().unwrap(),crate::hangar091::unavailable_response(303).unwrap());
}

#[test]
fn profile13_flow_disconnect_preserves_terminal_receipt_before_world_detach_and_fences_owner() {
    let now=Instant::now();let mut s=account(now);let receipt=reserve(&mut s,now);let mut world=driving(&mut s,&receipt,now);
    world.actors[0].fire.apply(&[crate::battle091::fire::Command::Shoot],now).unwrap();world.actors[0].health=23;
    let owner=s.identity.as_ref().unwrap().account_id.clone();let id=s.id;
    let mut table=Table{sessions:vec![s],..Table::default()};let mut dispatcher=Dispatcher::default();
    dispatcher.retire(&mut table,&mut world,id,now,"synthetic_test_disconnect").unwrap();
    assert!(table.sessions.is_empty());assert_eq!(world.actors[0].session,None);assert!(dispatcher.owner_busy(&owner));
    assert_eq!(dispatcher.retired.len(),1);let retired=&dispatcher.retired[0];assert!(!retired.active);
    let terminal=retired.shared.as_ref().unwrap().profile13.as_ref().unwrap().pending_return.as_ref().unwrap();
    assert_eq!(terminal.reservation,receipt);assert_eq!(terminal.reason,FinishReason::Disconnect);
    assert_eq!((terminal.remaining_ap,terminal.terminal_hp),(19,23));assert_eq!(world.actors[0].fire.ammo(),19);
}

#[test]
fn profile13_flow_terminal_freezes_ap_hp_and_late_avatar_records_never_regain_authority() {
    let now=Instant::now();let mut s=account(now);let receipt=reserve(&mut s,now);let mut world=driving(&mut s,&receipt,now);
    world.actors[0].fire.apply(&[crate::battle091::fire::Command::Shoot],now).unwrap();world.actors[0].health=23;
    s.shared.as_mut().unwrap().view=Some(world.clone());
    Dispatcher::terminal(&mut s,&world,FinishReason::ManualLeave).unwrap();let frozen=state(&mut s).unwrap().pending_return.clone();
    world.detach(s.id).unwrap();receive(&mut s,&[0x88,0,0],now);
    assert_eq!(state(&mut s).unwrap().pending_return,frozen);assert_eq!(state(&mut s).unwrap().stale_envelopes,1);
    assert!(s.shared.as_ref().unwrap().commands.is_empty());assert_eq!(world.actors[0].fire.ammo(),19);assert_eq!(world.actors[0].health,23);
    super::super::poll_battle_session(&mut s,&mut world,now+Duration::from_secs(1),true,false).unwrap();
    assert!(world.owned(0,s.id).is_err());assert!(world.shots.is_empty());assert_eq!(world.actors[0].fire.ammo(),19);
    let before=state(&mut s).unwrap().clone();let rx=s.rx;let malformed=frame_at(&s,rx,&[0x88,1,0]);
    assert!(s.receive(&malformed,now).is_err());assert_eq!(state(&mut s).unwrap(),&before);assert_eq!(s.rx,rx);
    Dispatcher::terminal(&mut s,&world,FinishReason::Disconnect).unwrap();assert_eq!(state(&mut s).unwrap().pending_return,frozen);
}

#[test]
fn profile13_flow_failed_delivery_is_atomic_and_successful_queue_preserves_native_revision() {
    let now=Instant::now();let mut s=account(now);receive(&mut s,&native(700,1,1),now);state(&mut s).unwrap().in_flight=true;
    let before=state(&mut s).unwrap().clone();let owner=s.identity.clone().unwrap();let revision=s.ammo_service.as_ref().unwrap().revision();
    s.outbox.extend((0..128).map(|_|vec![0]));let outbox=s.outbox.clone();
    let done=completion(&s);assert!(Dispatcher::deliver(&mut s,done,now).is_err());
    assert_eq!(state(&mut s).unwrap(),&before);assert!(Arc::ptr_eq(s.identity.as_ref().unwrap(),&owner));
    assert_eq!(s.ammo_service.as_ref().unwrap().revision(),revision);assert_eq!(s.outbox,outbox);
    s.outbox.clear();let done=completion(&s);let revision=done.reply.revision;Dispatcher::deliver(&mut s,done,now).unwrap();
    assert!(state(&mut s).unwrap().reservation.is_some());assert!(!state(&mut s).unwrap().in_flight);
    assert!(s.shared.as_ref().unwrap().queue_announced);assert_eq!(s.outbox.pop_back().unwrap(),crate::map_drive_world091::queue_callback(true));
    assert_eq!(s.ammo_service.as_ref().unwrap().revision(),revision);assert!(!s.arena_base);
    ammo_session::refresh(&mut s,crate::account091::Request{id:304,command:100},4,0,&mut vec![]).unwrap();
    assert_eq!(s.outbox.pop_back().unwrap(),crate::ammo_service091::refresh_response(304,4).unwrap());
}

#[test]
fn profile13_flow_finished_result_preserves_warm_source_cursor_then_full_state_restarts_at_one() {
    fn sync(id:i16,command:i16,revision:i64)->Vec<u8> {
        let mut bytes=vec![0x8e,20,0];bytes.extend(id.to_le_bytes());bytes.extend(command.to_le_bytes());
        bytes.extend(revision.to_le_bytes());bytes.extend(0i32.to_le_bytes());bytes.extend(0i32.to_le_bytes());bytes
    }
    fn sent(s:&mut Session,now:Instant)->Vec<Vec<u8>> {
        let mut bodies=vec![];
        while let Some((_,_,raw))=s.tx.due(now,s.rx).unwrap() {
            bodies.push(crate::transport091::parse_interactive(&raw).unwrap().body);
        }
        bodies
    }
    let now=Instant::now();let mut s=account(now);let receipt=reserve(&mut s,now);let mut world=driving(&mut s,&receipt,now);
    for step in 0..3 {world.actors[0].fire.apply(&[crate::battle091::fire::Command::Shoot],now+Duration::from_secs(30*step)).unwrap();}
    world.actors[0].health=23;s.shared.as_mut().unwrap().view=Some(world.clone());
    Dispatcher::terminal(&mut s,&world,FinishReason::ManualLeave).unwrap();world.detach(s.id).unwrap();
    let(context,request,reply)=writer_result(4);assert_eq!(state(&mut s).unwrap().pending_return.as_ref().unwrap().request(),request);
    assert_eq!((s.ammo_service.as_ref().unwrap().revision(),s.ammo_service.as_ref().unwrap().wire_revision()),(16,4));
    state(&mut s).unwrap().in_flight=true;
    let owner=s.identity.clone().unwrap();let fixtures=s.hangar.clone().unwrap();
    let fresh=service::Fresh{owner:Arc::new(crate::identity091::Profile{account_id:owner.account_id.clone(),database_id:owner.database_id,
        name:owner.name.clone(),fixture_dir:owner.fixture_dir.clone()}),fixtures:fixtures.clone(),
        binding:crate::ammo_service091::Metadata{revision:reply.revision,wire_revision:1}};
    let at=now+Duration::from_secs(61);
    let done=service::Completion{session:s.id,old_owner:owner,context,request,reply,fresh:Some(fresh),refresh_error:None};
    Dispatcher::deliver(&mut s,done,at).unwrap();
    let p=s.shared.as_ref().unwrap().profile13.as_ref().unwrap();
    assert!(p.garage_idle());assert_eq!(p.revision,17);
    assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Returning);assert!(!s.arena_base);
    assert_eq!(s.shared.as_ref().unwrap().return_source_revision,4);
    assert_eq!((s.ammo_service.as_ref().unwrap().revision(),s.ammo_service.as_ref().unwrap().wire_revision()),(17,1));
    let(reset,acked)=s.drive_return_account.as_ref().unwrap().creation.unwrap();assert!(!acked);
    assert_eq!(sent(&mut s,at),vec![crate::map_drive_world091::return_account(&s.identity.as_ref().unwrap().name).unwrap()]);
    let mut enable=frame_at(&s,s.rx,&[9]);enable.cumulative=Some(reset+1);
    assert!(!s.receive(&enable,at).unwrap());assert!(s.drive_return_account.as_ref().unwrap().enabled);
    assert_eq!(s.tx.len(),0);

    // The original global Account repository still carries its old cursor4
    // here. Accepting cursor1 before the full stream hides a broken epoch.
    let before=s.clone();let wrong=frame_at(&s,s.rx,&sync(401,100,1));
    assert!(s.receive(&wrong,at).is_err());
    assert_eq!((s.rx,s.tx.cumulative,s.tx.len(),s.last_rx),(before.rx,before.tx.cumulative,before.tx.len(),before.last_rx));
    assert_eq!(s.received,before.received);assert_eq!(s.outbox,before.outbox);assert_eq!(s.request_ids,before.request_ids);
    assert_eq!(s.drive_return_account,before.drive_return_account);assert_eq!(s.account_cache_hash,before.account_cache_hash);
    assert_eq!(s.ammo_service,before.ammo_service);assert_eq!(s.shared.as_ref().unwrap().return_mask,0);
    assert_eq!(s.shared.as_ref().unwrap().profile13,before.shared.as_ref().unwrap().profile13);

    receive(&mut s,&sync(401,100,4),at);
    assert_eq!(s.shared.as_ref().unwrap().return_mask,1);assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Returning);
    let full=crate::hangar091::response(&crate::account091::Request{id:401,command:100},&fixtures).unwrap();
    assert_eq!(sent(&mut s,at),full);assert_eq!(fixtures.state_bytes(),b"\x80\x02}(U\x03revK\x01u.");
    // Complete the other native warm requests before enabling garage actions.
    let mut tail=sync(402,300,3);tail.extend(sync(403,600,0));receive(&mut s,&tail,at);
    let c=s.shared.as_ref().unwrap();assert_eq!(c.phase,Phase::Account);assert_eq!(c.return_mask,7);
    assert!(c.profile13_garage_idle());assert!(!c.join_requested);assert_eq!(s.request_ids,vec![401,402,403]);
    let mut expected=crate::hangar091::response(&crate::account091::Request{id:402,command:300},&fixtures).unwrap();
    expected.extend(crate::hangar091::response(&crate::account091::Request{id:403,command:600},&fixtures).unwrap());
    expected.push(crate::hangar091::show_gui(s.identity.as_ref().unwrap().database_id).unwrap());
    assert_eq!(sent(&mut s,at),expected);
    receive(&mut s,&sync(404,100,1),at);
    assert_eq!(sent(&mut s,at),vec![crate::ammo_service091::refresh_response(404,1).unwrap()]);
    assert!(s.ammo_service.as_ref().unwrap().used_id(404));
    assert_eq!((s.ammo_service.as_ref().unwrap().revision(),s.ammo_service.as_ref().unwrap().wire_revision()),(17,1));
}

#[test]
fn profile13_flow_closed_empty_queue_waits_for_peer_receipt_then_renews_battle_id() {
    let now=Instant::now();let mut peer=account(now);let receipt=reserve(&mut peer,now);
    peer.outbox.clear();let old=receipt.battle;let mut world=World::new(old,now).unwrap();let mut runtime=None;
    let template=BattleTemplate::new(&world,&runtime);let mut dispatcher=Dispatcher::default();dispatcher.settled_queue=Some(old);
    let mut table=Table{sessions:vec![peer],..Table::default()};
    // Another accepted reservation for the same queue must settle first.
    assert!(!dispatcher.finish_empty_queue(&table,&mut world,&mut runtime,&template,now).unwrap());
    assert_eq!(world.id,old);assert!(dispatcher.closed_queue(old));
    let p=state(&mut table.sessions[0]).unwrap();p.reservation=None;p.in_flight=true;
    assert!(!dispatcher.finish_empty_queue(&table,&mut world,&mut runtime,&template,now).unwrap());
    assert_eq!(world.id,old);assert!(dispatcher.closed_queue(old));
    state(&mut table.sessions[0]).unwrap().in_flight=false;
    // Neither a live actor nor an already started world is an empty queue.
    let owner=table.sessions[0].identity.as_ref().unwrap();let sid=table.sessions[0].id;
    world.attach_owned(model::Identity{account:owner.account_id.clone(),database:owner.database_id,name:owner.name.clone()},sid,&receipt.frozen).unwrap();
    assert!(!dispatcher.finish_empty_queue(&table,&mut world,&mut runtime,&template,now).unwrap());
    world.detach(sid).unwrap();world.started=Some(now);
    assert!(!dispatcher.finish_empty_queue(&table,&mut world,&mut runtime,&template,now).unwrap());
    assert_eq!(world.id,old);world.started=None;
    assert!(dispatcher.finish_empty_queue(&table,&mut world,&mut runtime,&template,now).unwrap());
    assert_eq!(world.id,old+1);assert!(world.actors.is_empty());assert!(world.started.is_none());assert!(runtime.is_none());
    assert!(!dispatcher.closed_queue(old));assert!(!dispatcher.closed_queue(world.id));
    assert!(!dispatcher.finish_empty_queue(&table,&mut world,&mut runtime,&template,now).unwrap());
    // Staging the next native selection now targets the fresh world. Encoding
    // is local only; this test never starts an HTTP worker or mutates SQLite.
    let s=&mut table.sessions[0];let c=s.shared.as_mut().unwrap();c.join_requested=false;c.queue_announced=false;
    receive(s,&native(700,1,1),now);let owner=s.identity.clone().unwrap();let sid=s.id;let p=state(s).unwrap();
    let context=p.next_context(&owner,sid).unwrap();let request=Request::Admit{battle:world.id,native_inventory_id:p.selection.unwrap()};
    let encoded:serde_json::Value=serde_json::from_slice(&profile13::encode_request(&context,&request).unwrap()).unwrap();
    assert_eq!(encoded["battle_id"],format!("{}:{}",context.run_id,old+1));
    assert!(p.reservation.is_none() && !p.in_flight);
}
