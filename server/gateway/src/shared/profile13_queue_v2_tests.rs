//! Synthetic native Session flow with pinned actual SQLite queue receipts.
//! No HTTP worker, native client, installation or UI compatibility claim.
use super::*;
use crate::profile13_v2091::{self as codec,Reply,Reservation};
use sha2::{Digest,Sha256};
use std::{path::{Path,PathBuf},sync::atomic::{AtomicU64,Ordering}};

fn writer(index:usize)->(Context,RequestV2,Reply){
    let raw=include_bytes!("../../../../tests/fixtures/p06t-queue-writer-vectors.json");
    assert_eq!(format!("{:x}",Sha256::digest(raw)),"6a0dd7856242a0105864de7985ec309c4e25b76616e1a5732102201c2abf580f");
    let document:serde_json::Value=serde_json::from_slice(raw).unwrap();
    let row=&document["vectors"][index];let input=&row["request"];
    let context=Context{account_id:input["account_id"].as_str().unwrap().into(),
        native_database_id:input["native_database_id"].as_i64().unwrap().try_into().unwrap(),
        command_key:input["command_key"].as_str().unwrap().into(),expected_revision:input["expected_revision"].as_u64().unwrap(),
        run_id:input["run_id"].as_str().unwrap().into()};
    let battle=input["battle_id"].as_str().unwrap().rsplit_once(':').unwrap().1.parse().unwrap();
    let request=match input["operation"].as_str().unwrap(){
        "admit"=>RequestV2::Admit{battle,native_inventory_id:1},
        "finish"=>{assert_eq!(input["reason"],"cancelled");RequestV2::Finish{battle,native_inventory_id:1,
            reservation_id:input["reservation_id"].as_str().unwrap().into(),terminal_hp:input["terminal_hp"].as_i64().unwrap().try_into().unwrap(),
            terminal_state_json:input["terminal_state_json"].as_str().unwrap().into(),reason:FinishReason::Cancelled,results_json:None,
            remaining_ammunition:input["remaining_ammunition"].as_array().unwrap().iter().map(|r|codec::Remaining{
                shell_compact_id:r["shell_compact_id"].as_u64().unwrap().try_into().unwrap(),count:r["count"].as_u64().unwrap().try_into().unwrap()
            }).collect::<Vec<_>>().try_into().unwrap()}},
        operation=>panic!("queue fixture operation {operation}"),
    };
    assert_eq!(serde_json::from_slice::<serde_json::Value>(&codec::encode_request(&context,&request).unwrap()).unwrap(),*input);
    let reply=codec::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&context,&request).unwrap();
    (context,request,reply)
}

fn fixtures()->(PathBuf,Arc<crate::hangar091::Fixtures>){
    static SERIAL:AtomicU64=AtomicU64::new(0);
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/p06t-queue");fs::create_dir_all(&root).unwrap();
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let path=root.join(format!("flow-{}-{stamp}-{}",std::process::id(),SERIAL.fetch_add(1,Ordering::Relaxed)));fs::create_dir(&path).unwrap();
    fs::write(path.join("state.bin"),b"\x80\x02}(U\x03revK\x01u.").unwrap();
    fs::write(path.join("shop.bin"),b"\x80\x02}(U\x03revK\x03u.").unwrap();
    fs::write(path.join("dossier.bin"),b"\x80\x02(K\x00]t.").unwrap();
    let loaded=Arc::new(crate::hangar091::Fixtures::load_interactive(&path).unwrap());(path,loaded)
}
fn account_context(now:Instant,context:Context)->Session{
    let(path,fixtures)=fixtures();
    let mut s=Session::new(7,[7;16],"127.0.0.1:41707".parse().unwrap(),now);
    s.identity=Some(Arc::new(crate::identity091::Profile{account_id:context.account_id.clone(),database_id:context.native_database_id,
        name:"synthetic-v2-queue".into(),fixture_dir:path}));s.hangar=Some(fixtures);
    s.active=true;s.account_ready=true;s.sync_mask=7;s.rx=1;s.tx=Window::interactive();s.base_peer=Some("127.0.0.1:41708".parse().unwrap());
    s.login_attempt=Some(LoginAttempt::new(s.key,s.id,s.login_peer));
    s.ammo_service=Some(ammo_session::State::new(crate::ammo_service091::Metadata{revision:context.expected_revision,wire_revision:4},true)
        .with_transfer(true).with_cross_vehicle(true).with_roster_recruitment(true).with_progression(true)
        .with_dismissal(true).with_barracks(true).with_research(true));
    let mut client=Client::new(0);client.join_requested=false;client.hangar_since=Some(now);
    client.profile13=Some(service::State::new(context.run_id,context.expected_revision).unwrap());s.shared=Some(client);s
}
fn account(now:Instant)->Session{account_context(now,writer(1).0)}
fn native(command:i16,first:i64,mask:i32)->Vec<u8>{
    let mut bytes=vec![0x8e,20,0,202,0];bytes.extend(command.to_le_bytes());bytes.extend(first.to_le_bytes());
    bytes.extend(mask.to_le_bytes());bytes.extend(0i32.to_le_bytes());bytes
}
fn frame(s:&Session,sequence:u32,payload:&[u8])->Frame{
    Frame{flags:0x458,sequence:Some(sequence),cumulative:Some(0),selective:vec![],
        body:[vec![1],s.token.to_le_bytes().to_vec(),payload.to_vec()].concat(),piggybacks:vec![]}
}
fn receive(s:&mut Session,payload:&[u8],now:Instant){let packet=frame(s,s.rx,payload);assert!(!s.receive(&packet,now).unwrap());}
fn due_native(s:&mut Session,now:Instant)->Vec<Vec<u8>>{
    let mut bodies=Vec::new();
    while let Some((_,_,raw))=s.tx.due(now,s.rx).unwrap(){bodies.push(crate::transport091::parse_interactive(&raw).unwrap().body);}
    bodies
}
fn no_native(s:&mut Session,now:Instant){assert!(s.outbox.is_empty());assert!(due_native(s,now).is_empty());}
fn refusal(s:&mut Session,code:&str,now:Instant){
    assert!(s.outbox.is_empty());
    assert_eq!(due_native(s,now),vec![crate::battle091::profile13::enqueue_failure(code).unwrap()]);
}
fn completion(s:&Session,index:usize)->service::CompletionV2{
    let(context,request,reply)=writer(index);let owner=s.identity.clone().unwrap();
    service::CompletionV2{session:s.id,old_owner:owner.clone(),context,request,
        fresh:Some(service::Fresh{owner,fixtures:s.hangar.clone().unwrap(),
            binding:crate::ammo_service091::Metadata{revision:reply.revision,wire_revision:1}}),reply,refresh_error:None}
}
fn reserve(s:&mut Session,now:Instant)->Reservation{
    receive(s,&native(700,1,1),now);state(s).unwrap().in_flight=true;
    let ready=completion(s,1);Dispatcher::deliver_v2(s,ready,now).unwrap();
    assert_eq!(s.outbox.pop_front().unwrap(),crate::map_drive_world091::queue_callback(true));assert!(s.outbox.is_empty());
    state(s).unwrap().reservation_v2.clone().unwrap()
}
fn empty_world(reservation:&Reservation,now:Instant)->World{
    let mut world=World::new_for_roster(reservation.battle,now,crate::map_profile091::MapId::Karelia,2).unwrap();
    world.enable_mixed_ammo().unwrap();world
}
fn legacy_writer()->(Context,crate::battle091::profile13::Request,crate::battle091::profile13::Reply){
    let raw=include_bytes!("../../../../tests/fixtures/profile13-writer-vectors.json");
    assert_eq!(format!("{:x}",Sha256::digest(raw)),"39ce1c7a9bdd0a44b80013c91deeb086449b5794a498d2d73db0c3cdffcfd3d6");
    let data:serde_json::Value=serde_json::from_slice(raw).unwrap();let row=&data["vectors"][2];let input=&row["request"];
    assert_eq!(input["operation"],"admit");
    let context=Context{account_id:input["account_id"].as_str().unwrap().into(),native_database_id:input["native_database_id"].as_i64().unwrap().try_into().unwrap(),
        command_key:input["command_key"].as_str().unwrap().into(),expected_revision:input["expected_revision"].as_u64().unwrap(),run_id:input["run_id"].as_str().unwrap().into()};
    let request=crate::battle091::profile13::Request::Admit{battle:input["battle_id"].as_str().unwrap().rsplit_once(':').unwrap().1.parse().unwrap(),native_inventory_id:1};
    let reply=crate::battle091::profile13::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&context,&request).unwrap();(context,request,reply)
}
fn reserve_legacy(s:&mut Session,now:Instant){
    receive(s,&native(700,1,1),now);state(s).unwrap().in_flight=true;
    let(context,request,reply)=legacy_writer();let owner=s.identity.clone().unwrap();
    let done=service::Completion{session:s.id,old_owner:owner.clone(),context,request,
        fresh:Some(service::Fresh{owner,fixtures:s.hangar.clone().unwrap(),binding:crate::ammo_service091::Metadata{revision:reply.revision,wire_revision:1}}),
        reply,refresh_error:None};
    Dispatcher::deliver(s,done,now).unwrap();assert_eq!(s.outbox.pop_front().unwrap(),crate::map_drive_world091::queue_callback(true));
    assert!(s.outbox.is_empty());
}

#[test]fn p06t_queue_duplicate_join_is_idempotent_before_and_after_actual_v2_reservation(){
    let now=Instant::now();let mut s=account(now);receive(&mut s,&native(700,1,1),now);
    let initial=state(&mut s).unwrap().clone();receive(&mut s,&native(700,1,1),now);
    assert_eq!(state(&mut s).unwrap(),&initial);assert!(s.outbox.is_empty());assert_eq!(initial.command_counter,0);
    state(&mut s).unwrap().in_flight=true;let done=completion(&s,1);Dispatcher::deliver_v2(&mut s,done,now).unwrap();
    assert_eq!(s.outbox.pop_front().unwrap(),crate::map_drive_world091::queue_callback(true));
    let reserved=state(&mut s).unwrap().clone();assert_eq!(reserved.reservation_native_inventory_id(),Some(1));
    for _ in 0..3{receive(&mut s,&native(700,1,1),now);}
    assert_eq!(state(&mut s).unwrap(),&reserved);no_native(&mut s,now);
    let client=s.shared.as_ref().unwrap();assert!(client.join_requested&&client.queue_announced);assert!(!s.arena_base);
}

#[test]fn p06t_queue_changed_vehicle_rejects_without_selection_or_early_dequeue_and_cancel_cannot_reopen(){
    let now=Instant::now();let mut s=account(now);let reservation=reserve(&mut s,now);
    receive(&mut s,&native(700,2,1),now);
    refusal(&mut s,"VEHICLE_RESERVED",now);
    let p=state(&mut s).unwrap();assert_eq!(p.reservation_v2.as_ref(),Some(&reservation));assert!(p.selection.is_none());
    assert!(s.shared.as_ref().unwrap().join_requested);assert!(s.shared.as_ref().unwrap().queue_announced);
    for _ in 0..2{receive(&mut s,&native(701,0,0),now);no_native(&mut s,now);}
    assert!(!s.shared.as_ref().unwrap().join_requested);
    assert!(s.outbox.is_empty());assert_eq!(state(&mut s).unwrap().reservation_v2.as_ref(),Some(&reservation));
}

#[test]fn p06t_queue_busy_join_preserves_original_v1_and_v2_pending_inflight_and_reserved(){
    let now=Instant::now();
    for mixed in[false,true]{for phase in[0,1,2]{
        let context=if mixed{writer(1).0}else{legacy_writer().0};let mut s=account_context(now,context);
        if phase==2{if mixed{reserve(&mut s,now);}else{reserve_legacy(&mut s,now);}}
        else{receive(&mut s,&native(700,1,1),now);state(&mut s).unwrap().in_flight=phase==1;}
        let before=state(&mut s).unwrap().clone();let announced=s.shared.as_ref().unwrap().queue_announced;
        receive(&mut s,&native(700,2,1),now);
        refusal(&mut s,"VEHICLE_RESERVED",now);
        assert!(s.outbox.is_empty());assert_eq!(state(&mut s).unwrap(),&before,"mixed={mixed} phase={phase}");
        let client=s.shared.as_ref().unwrap();assert!(client.join_requested);assert_eq!(client.queue_announced,announced);
        assert!(!client.profile13.as_ref().unwrap().has_pending_return());assert!(!s.arena_base);
    }}
}

#[test]fn p06t_queue_cancel_waits_for_actual_durable_v2_finish_and_emits_dequeue_once(){
    let now=Instant::now();let mut s=account(now);let reservation=reserve(&mut s,now);
    receive(&mut s,&native(701,0,0),now);no_native(&mut s,now);
    let world=empty_world(&reservation,now);Dispatcher::terminal_mixed(&mut s,&world,FinishReason::ManualLeave).unwrap();
    let terminal=state(&mut s).unwrap().pending_return_v2.clone().unwrap();assert_eq!(terminal.reason,FinishReason::Cancelled);
    assert_eq!(terminal.remaining_ammunition.map(|r|r.count),[0,4,11]);assert_eq!(terminal.terminal_hp,90);
    let(_,actual_request,_)=writer(2);assert_eq!(terminal.request(),actual_request);
    receive(&mut s,&native(701,0,0),now);no_native(&mut s,now);
    receive(&mut s,&native(700,1,1),now);
    refusal(&mut s,"VEHICLE_RESERVED",now);
    assert!(s.outbox.is_empty());assert_eq!(state(&mut s).unwrap().pending_return_v2.as_ref(),Some(&terminal));
    state(&mut s).unwrap().in_flight=true;
    // A committed reply without its trusted refreshed projection still cannot
    // clear the reservation or publish onDequeued.
    let before=state(&mut s).unwrap().clone();let mut missing=completion(&s,2);missing.fresh=None;
    assert!(Dispatcher::deliver_v2(&mut s,missing,now).is_err());assert_eq!(state(&mut s).unwrap(),&before);assert!(s.outbox.is_empty());
    let done=completion(&s,2);Dispatcher::deliver_v2(&mut s,done,now).unwrap();
    assert_eq!(s.outbox.pop_front().unwrap(),crate::map_drive_world091::queue_callback(false));assert!(s.outbox.is_empty());
    assert!(state(&mut s).unwrap().garage_idle());assert_eq!(s.ammo_service.as_ref().unwrap().wire_revision(),4);
    assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Account);assert!(!s.arena_base);
    let replay=completion(&s,3);assert!(replay.reply.replayed);Dispatcher::deliver_v2(&mut s,replay,now).unwrap();
    receive(&mut s,&native(701,0,0),now);no_native(&mut s,now);assert!(state(&mut s).unwrap().garage_idle());
}

#[test]fn p06t_queue_cancel_inflight_admit_freezes_actual_unspent_receipt_without_native_enqueue(){
    let now=Instant::now();let mut s=account(now);receive(&mut s,&native(700,1,1),now);state(&mut s).unwrap().in_flight=true;
    receive(&mut s,&native(701,0,0),now);no_native(&mut s,now);
    let done=completion(&s,1);Dispatcher::deliver_v2(&mut s,done,now).unwrap();
    let p=state(&mut s).unwrap();assert!(p.has_reservation()&&p.has_pending_return());assert!(!p.in_flight);
    assert_eq!(p.pending_return_v2.as_ref().unwrap().request(),writer(2).1);
    let client=s.shared.as_ref().unwrap();assert!(!client.queue_announced&&!client.join_requested);assert!(s.outbox.is_empty());
    let done=completion(&s,2);Dispatcher::deliver_v2(&mut s,done,now).unwrap();assert!(s.outbox.is_empty());
    assert!(state(&mut s).unwrap().garage_idle());assert!(!s.arena_base);
}

#[test]fn p06t_queue_poisoned_later_piggyback_rolls_back_v2_cancel_and_transport_ack(){
    let now=Instant::now();let mut s=account(now);reserve(&mut s,now);
    let before=state(&mut s).unwrap().clone();let revision=s.ammo_service.as_ref().unwrap().revision();let rx=s.rx;
    let last_rx=s.last_rx;let history=s.received.clone();s.tx.enqueue().unwrap();assert!(s.tx.due(now,s.rx).unwrap().is_some());
    let mut good=frame(&s,rx,&native(701,0,0));good.cumulative=Some(1);
    let mut bad=frame(&s,rx+1,&native(502,1,0));bad.cumulative=Some(1);bad.body[1]^=1;
    let mut parent=frame(&s,rx+2,&[]);parent.cumulative=Some(1);parent.piggybacks=vec![good,bad];
    assert!(s.receive(&parent,now+Duration::from_secs(1)).is_err());assert_eq!(state(&mut s).unwrap(),&before);
    assert_eq!(s.rx,rx);assert_eq!(s.last_rx,last_rx);assert_eq!(s.received,history);assert_eq!(s.tx.cumulative,0);assert_eq!(s.tx.len(),1);
    assert_eq!(s.ammo_service.as_ref().unwrap().revision(),revision);assert!(s.outbox.is_empty());
    let client=s.shared.as_ref().unwrap();assert!(client.join_requested&&client.queue_announced);
}

#[test]fn p06t_queue_dispatch_does_not_readmit_active_v2_reservation_even_with_stale_selection(){
    let now=Instant::now();let mut s=account(now);let reservation=reserve(&mut s,now);state(&mut s).unwrap().selection=Some(2);
    let before=state(&mut s).unwrap().clone();let world=empty_world(&reservation,now);let root=s.identity.as_ref().unwrap().fixture_dir.clone();
    fs::write(root.join("test-token.txt"),"a".repeat(43)).unwrap();
    let mut value=serde_json::json!({"login_bind":"127.0.0.1:20301","base_bind":"127.0.0.1:20302","identity_endpoint":"127.0.0.1:20303",
        "identity_token_file":root.join("test-token.txt"),"local_root":root,"session_duration_seconds":600});
    for field in["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression",
        "crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle","p04m_pool","p06t_mixed_ammo"]{value[field]=true.into();}
    let path=root.join("test-config.json");fs::write(&path,serde_json::to_vec(&value).unwrap()).unwrap();
    let config=Arc::new(crate::identity091::Config::load(path.to_str().unwrap()).unwrap());
    // A fresh Config has a different run. A missing admission guard must fail
    // the test before any worker thread/HTTP can start; it cannot be a mock success.
    assert_ne!(config.battle_run_id,before.run_id);
    let mut table=Table{sessions:vec![s],..Table::default()};let mut dispatcher=Dispatcher::default();
    dispatcher.start_mixed(&mut table,&world,config,now).unwrap();
    assert_eq!(state(&mut table.sessions[0]).unwrap(),&before);assert!(dispatcher.task_v2.is_none()&&dispatcher.job_v2.is_none());
    assert!(!dispatcher.busy());assert!(table.sessions[0].outbox.is_empty());
}

#[test]fn p06t_queue_command_budget_rejects_only_new_v1_v2_admissions_and_preserves_finish_slot(){
    let now=Instant::now();
    for mixed in[false,true]{for counter in[510,511,512]{
        let context=if mixed{writer(1).0}else{legacy_writer().0};let mut s=account_context(now,context);
        state(&mut s).unwrap().command_counter=counter;let before=state(&mut s).unwrap().clone();
        receive(&mut s,&native(700,1,1),now);
        if counter==510{
            assert!(s.outbox.is_empty());assert!(s.shared.as_ref().unwrap().join_requested);
            assert_eq!(state(&mut s).unwrap().selection,Some(1));assert_eq!(state(&mut s).unwrap().command_counter,510);
            let owner=s.identity.clone().unwrap();let sid=s.id;let context=state(&mut s).unwrap().next_context(&owner,sid).unwrap();
            assert!(context.command_key.ends_with(":511"));assert_eq!(state(&mut s).unwrap().command_counter,511);
            // An already staged request remains idempotent at the boundary.
            let pending=state(&mut s).unwrap().clone();receive(&mut s,&native(700,1,1),now);
            assert_eq!(state(&mut s).unwrap(),&pending);no_native(&mut s,now);
        }else{
            refusal(&mut s,"BATTLE_BUSY",now);
            assert!(s.outbox.is_empty());assert_eq!(state(&mut s).unwrap(),&before);
            let c=s.shared.as_ref().unwrap();assert!(!c.join_requested&&!c.queue_announced);assert!(!s.arena_base);
        }
    }}
}

#[test]fn p06t_queue_command_budget_still_allows_v1_v2_duplicate_cancel_and_terminal_command_512(){
    let now=Instant::now();
    for mixed in[false,true]{
        let context=if mixed{writer(1).0}else{legacy_writer().0};let mut s=account_context(now,context);
        if mixed{reserve(&mut s,now);}else{reserve_legacy(&mut s,now);}
        state(&mut s).unwrap().command_counter=511;let before=state(&mut s).unwrap().clone();
        receive(&mut s,&native(700,1,1),now);assert_eq!(state(&mut s).unwrap(),&before);no_native(&mut s,now);
        receive(&mut s,&native(701,0,0),now);no_native(&mut s,now);assert!(!s.shared.as_ref().unwrap().join_requested);
        let battle=state(&mut s).unwrap().reservation_battle().unwrap();
        let mut world=World::new_for_roster(battle,now,crate::map_profile091::MapId::Karelia,2).unwrap();
        if mixed{world.enable_mixed_ammo().unwrap();}
        Dispatcher::terminal(&mut s,&world,FinishReason::ManualLeave).unwrap();
        assert!(state(&mut s).unwrap().has_pending_return());assert_eq!(state(&mut s).unwrap().command_counter,511);
        let owner=s.identity.clone().unwrap();let sid=s.id;let context=state(&mut s).unwrap().next_context(&owner,sid).unwrap();
        assert!(context.command_key.ends_with(":512"));assert_eq!(state(&mut s).unwrap().command_counter,512);
        assert!(state(&mut s).unwrap().has_reservation());assert!(state(&mut s).unwrap().has_pending_return());
        assert!(s.outbox.is_empty());assert!(!s.arena_base);
    }
}
