//! Candidate actual Session/strict-SQL DTO scheduling tests; NOT_COMPILED until root gate.
//! Tiny cache/Fresh/identity are AUTHORED scheduling seams, not actual refresh.
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


fn finished_task(s:&Session)->TaskV2{
    let(context,request,_)=writer(2);TaskV2{session:s.id,owner:s.identity.clone().unwrap(),context,request}
}
fn prepared_finished(now:Instant)->(Session,TaskV2){
    let mut s=account(now);reserve(&mut s,now);s.outbox.clear();
    let task=finished_task(&s);(s,task)
}
fn armed(task:&TaskV2)->Dispatcher{
    let mut d=Dispatcher::default();d.enable_training_finished();
    d.begin_training_finished_battle(crate::training091::domain::BattleKey(task.request.finished_battle().unwrap())).unwrap();d
}

#[test]fn p10b_finished_hook_default_and_unarmed_preserve_actual_v2_delivery_without_receipts(){
    let now=Instant::now();
    for enabled in[false,true]{let(mut s,task)=prepared_finished(now);let mut d=Dispatcher::default();
        if enabled{d.enable_training_finished();}
        let mut legacy=s.clone();let done=completion(&legacy,2);Dispatcher::deliver_v2(&mut legacy,done,now).unwrap();
        let done=completion(&s,2);Dispatcher::deliver_training_finished_v2(&mut d.training_finished,&mut s,&task,done,now).unwrap();
        assert!(state(&mut s).unwrap().garage_idle());assert_eq!(s.ammo_service.as_ref().unwrap().revision(),19);
        assert!(d.take_training_finished().is_none());assert_eq!(s.outbox,legacy.outbox);assert_eq!(state(&mut s).unwrap(),state(&mut legacy).unwrap());
    }
}
#[test]fn p10b_finished_hook_actual_finished_delivery_and_replay_publish_one_exact_reference(){
    let now=Instant::now();let(mut s,task)=prepared_finished(now);let mut d=armed(&task);
    let done=completion(&s,2);let row=done.reply.reservation.as_ref().unwrap();
    let expected=crate::training091::domain::FinishedRef::from_verified_writer(
        finished_events::account(&task.owner.account_id).unwrap(),row.reservation_id.clone(),
        crate::training091::domain::BattleKey(row.battle)).unwrap();
    Dispatcher::deliver_training_finished_v2(&mut d.training_finished,&mut s,&task,done,now).unwrap();
    assert!(state(&mut s).unwrap().garage_idle());assert_eq!(d.take_training_finished(),Some(expected));
    let replay=completion(&s,3);assert!(replay.reply.replayed);
    Dispatcher::deliver_training_finished_v2(&mut d.training_finished,&mut s,&task,replay,now).unwrap();
    assert!(d.take_training_finished().is_none());
}
#[test]fn p10b_finished_hook_failed_session_delivery_never_publishes_and_retry_keeps_receipt(){
    let now=Instant::now();let(mut s,task)=prepared_finished(now);let mut d=armed(&task);
    let before=state(&mut s).unwrap().clone();let outbox=s.outbox.clone();
    // Real delivery calls refresh_revision: an absent ammo State must fail.
    let ammo=s.ammo_service.take();let done=completion(&s,2);
    assert!(Dispatcher::deliver_training_finished_v2(&mut d.training_finished,&mut s,&task,done,now).is_err());
    assert_eq!(state(&mut s).unwrap(),&before);assert_eq!(s.outbox,outbox);assert!(d.take_training_finished().is_none());
    s.ammo_service=ammo;let done=completion(&s,2);
    Dispatcher::deliver_training_finished_v2(&mut d.training_finished,&mut s,&task,done,now).unwrap();assert!(d.take_training_finished().is_some());
}
#[test]fn p10b_finished_hook_wrong_task_session_native_source_or_terminal_receipt_roll_back(){
    let now=Instant::now();
    for poison in 0..11{let(mut s,task)=prepared_finished(now);let mut d=armed(&task);let mut done=completion(&s,2);
        match poison{
            0=>done.session+=1,
            1=>done.context.command_key.push('x'),
            2=>done.context.native_database_id+=1,
            3=>if let RequestV2::Finish{terminal_hp,..}=&mut done.request{*terminal_hp-=1;},
            4=>{let p=&done.old_owner;done.old_owner=Arc::new(crate::identity091::Profile{account_id:p.account_id.clone(),database_id:p.database_id+1,name:p.name.clone(),fixture_dir:p.fixture_dir.clone()});},
            5=>{let f=done.fresh.as_mut().unwrap();let p=&f.owner;f.owner=Arc::new(crate::identity091::Profile{account_id:p.account_id.clone(),database_id:p.database_id+1,name:p.name.clone(),fixture_dir:p.fixture_dir.clone()});},
            6=>done.reply.reservation.as_mut().unwrap().status=codec::ReservationStatus::Active,
            7=>done.reply.reservation.as_mut().unwrap().reservation_id.push('x'),
            8=>done.reply.reservation.as_mut().unwrap().battle+=1,
            9=>done.reply.reservation.as_mut().unwrap().run_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb".into(),
            10=>done.fresh.as_mut().unwrap().binding.revision+=1,_=>unreachable!(),
        }
        let before=state(&mut s).unwrap().clone();let revision=s.ammo_service.as_ref().unwrap().revision();let outbox=s.outbox.clone();
        assert!(Dispatcher::deliver_training_finished_v2(&mut d.training_finished,&mut s,&task,done,now).is_err(),"poison {poison}");
        assert_eq!(state(&mut s).unwrap(),&before);assert_eq!(s.ammo_service.as_ref().unwrap().revision(),revision);
        assert_eq!(s.outbox,outbox);assert!(d.take_training_finished().is_none());
        let done=completion(&s,2);Dispatcher::deliver_training_finished_v2(&mut d.training_finished,&mut s,&task,done,now).unwrap();
        assert!(d.take_training_finished().is_some());
    }
}
#[test]fn p10b_finished_hook_capacity_rejects_before_clearing_actual_reservation(){
    let now=Instant::now();let(mut s,task)=prepared_finished(now);let mut d=armed(&task);
    let battle=crate::training091::domain::BattleKey(task.request.finished_battle().unwrap());
    for n in 1..=6{let q=d.training_finished.as_ref().unwrap().staged(
        crate::training091::domain::Account([n;16]),&format!("authored:prior:{n}"),battle).unwrap();d.training_finished=Some(q);}
    let before=state(&mut s).unwrap().clone();let revision=s.ammo_service.as_ref().unwrap().revision();let done=completion(&s,2);
    assert!(Dispatcher::deliver_training_finished_v2(&mut d.training_finished,&mut s,&task,done,now).is_err());
    assert_eq!(state(&mut s).unwrap(),&before);assert_eq!(s.ammo_service.as_ref().unwrap().revision(),revision);
    let mut count=0;while d.take_training_finished().is_some(){count+=1;}assert_eq!(count,6);
}
