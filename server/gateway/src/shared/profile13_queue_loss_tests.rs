//! Actual SQL admission receipt through cloned native Session/Window staging.
//! No native client/UI or HTTP compatibility claim.
use super::*;
use crate::profile13_loss091::{self as codec,Reply,Reservation};
use sha2::{Digest,Sha256};
use std::{path::{Path,PathBuf},sync::atomic::{AtomicU64,Ordering}};
fn writer(index:usize)->(Context,RequestLoss,Reply){
    let raw=include_bytes!("../../../../tests/fixtures/p06t-ammo-loss-queue-vectors.json");
    assert_eq!(format!("{:x}",Sha256::digest(raw)),"9c3d0ca15a66238b3e1f0991562c37a9c096cbd93e2261b67858489a2297d450");
    let data:serde_json::Value=serde_json::from_slice(raw).unwrap();
    let row=&data["vectors"][index];let r=&row["request"];
    let c=Context{account_id:r["account_id"].as_str().unwrap().into(),native_database_id:r["native_database_id"].as_i64().unwrap()as i32,
        command_key:r["command_key"].as_str().unwrap().into(),expected_revision:r["expected_revision"].as_u64().unwrap(),run_id:r["run_id"].as_str().unwrap().into()};
    let battle=r["battle_id"].as_str().unwrap().rsplit(':').next().unwrap().parse().unwrap();let native_inventory_id=r["native_inventory_id"].as_u64().unwrap()as u32;
    let rows=|key:&str|r[key].as_array().unwrap().iter().map(|a|codec::Remaining{shell_compact_id:a["shell_compact_id"].as_u64().unwrap()as u16,count:a["count"].as_u64().unwrap()as u16}).collect::<Vec<_>>().try_into().unwrap();
    let request=if r["operation"]=="admit"{RequestLoss::Admit{battle,native_inventory_id}}else{
        assert_eq!(r["reason"],"cancelled");RequestLoss::Finish{battle,native_inventory_id,reservation_id:r["reservation_id"].as_str().unwrap().into(),
            remaining_ammunition:rows("remaining_ammunition"),fired_ammunition:rows("fired_ammunition"),lost_ammunition:rows("lost_ammunition"),loss_event:None,
            terminal_hp:r["terminal_hp"].as_i64().unwrap()as i16,terminal_state_json:r["terminal_state_json"].as_str().unwrap().into(),reason:FinishReason::Cancelled,results_json:None}};
    let response=codec::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&c,&request).unwrap();(c,request,response)
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
fn completion(s:&Session,index:usize)->service::CompletionLoss{
    let(context,request,reply)=writer(index);let owner=s.identity.clone().unwrap();
    service::CompletionLoss{session:s.id,old_owner:owner.clone(),context,request,reply:reply.clone(),refresh_error:None,
        fresh:Some(service::Fresh{owner,fixtures:s.hangar.clone().unwrap(),binding:crate::ammo_service091::Metadata{revision:reply.revision,wire_revision:1}})}
}
fn reserved(now:Instant)->(Session,Reservation){
    let mut s=account(now);receive(&mut s,&native(700,1,1),now);state(&mut s).unwrap().in_flight=true;
    let c=completion(&s,1);Dispatcher::deliver_loss(&mut s,c,now).unwrap();
    assert_eq!(s.outbox.pop_front().unwrap(),crate::map_drive_world091::queue_callback(true));assert!(s.outbox.is_empty());
    let row=state(&mut s).unwrap().reservation_loss.clone().unwrap();(s,row)
}
fn world(r:&Reservation,now:Instant)->World{
    let mut w=World::new_for_roster(r.battle,now,crate::map_profile091::MapId::Karelia,2).unwrap();
    w.enable_mixed_ammo().unwrap();
    w.bind_geometry(Arc::new(super::super::super::super::geometry::tests::bundle())).unwrap();
    w.bind_geometry(Arc::new(super::super::super::super::geometry::tests::is7_bundle())).unwrap();w.enable_ap_test_lab().unwrap();
    w.bind_terrain(Arc::new(super::super::super::super::terrain::tests::fixture(-1000.,2000.,2,vec![-100.;4]))).unwrap();
    w.enable_lifecycle(super::super::super::super::lifecycle::Rules::prohorovka()).unwrap();w.enable_ammo_detonation().unwrap();w
}
#[test]fn p06t_loss_queue_duplicate_and_busy_join_keep_actual_new_contract_reservation(){
    let now=Instant::now();let(mut s,r)=reserved(now);let before=state(&mut s).unwrap().clone();
    receive(&mut s,&native(700,1,1),now);assert_eq!(state(&mut s).unwrap(),&before);no_native(&mut s,now);
    receive(&mut s,&native(700,2,1),now);assert_eq!(state(&mut s).unwrap(),&before);refusal(&mut s,"VEHICLE_RESERVED",now);
    assert_eq!(state(&mut s).unwrap().reservation_loss,Some(r));
}
#[test]fn p06t_loss_native_cancel_freezes_pristine_receipt_before_any_world_actor(){
    let now=Instant::now();let(mut s,r)=reserved(now);receive(&mut s,&native(701,0,0),now);
    Dispatcher::terminal(&mut s,&world(&r,now),FinishReason::Cancelled).unwrap();
    let p=state(&mut s).unwrap();let t=p.pending_return_loss.as_ref().unwrap();
    assert_eq!(t.reason,FinishReason::Cancelled);assert_eq!(t.remaining_ammunition.map(|a|a.count),r.frozen.base.counts());
    assert_eq!(t.fired_ammunition.map(|a|a.count),[0;3]);assert_eq!(t.lost_ammunition.map(|a|a.count),[0;3]);assert!(t.loss_event.is_none());
    assert!(p.has_reservation());assert!(p.has_pending_return());assert!(!p.garage_idle());
    assert!(s.outbox.is_empty()); // callback must wait for durable terminal commit
}
#[test]fn p06t_loss_late_admission_after_cancel_compensates_and_never_announces_join(){
    let now=Instant::now();let mut s=account(now);receive(&mut s,&native(700,1,1),now);
    state(&mut s).unwrap().in_flight=true;receive(&mut s,&native(701,0,0),now);let c=completion(&s,1);
    Dispatcher::deliver_loss(&mut s,c,now).unwrap();assert!(s.outbox.is_empty());
    let p=state(&mut s).unwrap();assert!(p.reservation_loss.is_some());assert_eq!(p.pending_return_loss.as_ref().unwrap().reason,FinishReason::Cancelled);
    assert!(!s.shared.as_ref().unwrap().join_requested);assert!(!s.shared.as_ref().unwrap().queue_announced);
}
#[test]fn p06t_loss_actual_sql_cancel_commit_releases_reserve_and_allows_second_queue(){
    let now=Instant::now();let(mut s,r)=reserved(now);receive(&mut s,&native(701,0,0),now);
    Dispatcher::terminal(&mut s,&world(&r,now),FinishReason::Cancelled).unwrap();
    assert_eq!(state(&mut s).unwrap().pending_return_loss.as_ref().unwrap().request(),writer(2).1);
    let c=completion(&s,2);Dispatcher::deliver_loss(&mut s,c,now).unwrap();
    assert_eq!(s.outbox.pop_front().unwrap(),crate::map_drive_world091::queue_callback(false));assert!(s.outbox.is_empty());
    assert!(state(&mut s).unwrap().garage_idle());assert_eq!(state(&mut s).unwrap().revision,19);
    receive(&mut s,&native(700,1,1),now);state(&mut s).unwrap().in_flight=true;let c=completion(&s,3);
    Dispatcher::deliver_loss(&mut s,c,now).unwrap();assert_eq!(s.outbox.pop_front().unwrap(),crate::map_drive_world091::queue_callback(true));
    let second=state(&mut s).unwrap().reservation_loss.clone().unwrap();assert_ne!(r.battle,second.battle);assert_eq!(r.frozen,second.frozen);
    receive(&mut s,&native(701,0,0),now);Dispatcher::terminal(&mut s,&world(&second,now),FinishReason::Cancelled).unwrap();
    assert_eq!(state(&mut s).unwrap().pending_return_loss.as_ref().unwrap().request(),writer(4).1);
    let c=completion(&s,4);Dispatcher::deliver_loss(&mut s,c,now).unwrap();assert!(state(&mut s).unwrap().garage_idle());
    assert_eq!(state(&mut s).unwrap().revision,21);assert_eq!(s.outbox.pop_front().unwrap(),crate::map_drive_world091::queue_callback(false));
}
