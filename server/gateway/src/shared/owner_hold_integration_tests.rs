//! Real World/Session/Window with actual SQLite-generated Frozen5, replies and
//! source-bound project caches. Identity login, transport ACKs/clock are
//! AUTHORED fixtures; HTTP jobs/native UI/N4 owned composition are NOT_RUN here.
use super::*;
use sha2::{Digest,Sha256};
use serde_json::Value;
use std::{fs,path::{Path,PathBuf},sync::atomic::{AtomicU64,Ordering}};
const PROJECT:&[u8]=include_bytes!("../../../../tests/fixtures/p08b-hold-project-projection.json");
const PROJECT_SHA:&str="204d1e03c8a14d68b8c89442842edb7366f0a608662a0ed1342e55ad4749bf93";
fn data()->Value{assert_eq!(format!("{:x}",Sha256::digest(PROJECT)),PROJECT_SHA);serde_json::from_slice(PROJECT).unwrap()}
fn context(q:&Value)->hold::Context{hold::Context{account_id:q["account_id"].as_str().unwrap().into(),native_database_id:q["native_database_id"].as_i64().unwrap()as i32,
    command_key:q["command_key"].as_str().unwrap().into(),expected_revision:q["expected_revision"].as_u64().unwrap(),run_id:q["run_id"].as_str().unwrap().into()}}
fn directory(index:usize)->(Arc<crate::identity091::Profile>,Arc<crate::hangar091::Fixtures>,crate::ammo_service091::Metadata){
    static SERIAL:AtomicU64=AtomicU64::new(0);
    let d=data();let row=match index{3=>next_admission(),4=>contained_projection(),_=>d["rows"][index].clone()};let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/p08b-hold5");fs::create_dir_all(&root).unwrap();
    let dir=root.join(format!("{}-{}-{}",std::process::id(),std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos(),SERIAL.fetch_add(1,Ordering::Relaxed)));
    fs::create_dir(&dir).unwrap();let dir=dir.canonicalize().unwrap();
    let names=["state.bin","shop.bin","dossier.bin","manifest.json","compatibility.json","ammo-service.json","crew-barracks.json","research-service.json","p04m-pool.json","p06t-ammo-loss.json","p06t-ammunition.json","p08b-battle.json","p08b-owner-hold.json"];
    let files=row["files"].as_array().unwrap();assert_eq!(files.len(),names.len());
    for f in files{let name=f["name"].as_str().unwrap();assert!(names.contains(&name));let hex=f["hex"].as_str().unwrap();assert!(hex.len()<=65536&&hex.len()%2==0);
        let b=hex.as_bytes().chunks_exact(2).map(|p|u8::from_str_radix(std::str::from_utf8(p).unwrap(),16).unwrap()).collect::<Vec<_>>();
        assert_eq!(b.len()as u64,f["bytes"].as_u64().unwrap());assert_eq!(format!("{:x}",Sha256::digest(&b)),f["sha256"].as_str().unwrap());fs::write(dir.join(name),b).unwrap();}
    let o=&row["owner"];let owner=Arc::new(crate::identity091::Profile{account_id:o["account_id"].as_str().unwrap().into(),database_id:o["native_database_id"].as_i64().unwrap()as i32,name:o["name"].as_str().unwrap().into(),fixture_dir:dir});
    let fixture=Arc::new(crate::hangar091::Fixtures::load_p04m(&owner.fixture_dir).unwrap());
    let binding=crate::ammo_service091::metadata_research(&owner.fixture_dir,&owner.account_id,owner.database_id).unwrap();
    assert_eq!(binding.revision,row["reply"]["revision"].as_u64().unwrap());(owner,fixture,binding)
}
fn next_admission()->Value{let raw=include_bytes!("../../../../tests/fixtures/p08b-hold-next-admission.json");assert_eq!(format!("{:x}",Sha256::digest(raw)),"178f0e20ff864e7756dfeb650ed2470050563ce6b04b5d1eef6014b818e05b5d");serde_json::from_slice::<Value>(raw).unwrap()["row"].clone()}
fn contained_projection()->Value{let raw=include_bytes!("../../../../tests/fixtures/p08b-hold-contained-projection.json");assert_eq!(format!("{:x}",Sha256::digest(raw)),"45fd0a3754d302882aecbcaf72d5e21ace0c9c4d481c3a1663f2ef2a5c0d5a66");serde_json::from_slice::<Value>(raw).unwrap()["row"].clone()}
fn source()->(hold::Context,hold::Reservation,u64){let d=data();let q=&d["rows"][0]["request"];let c=context(q);
    let r=hold::Request::Admit{battle:q["battle_id"].as_str().unwrap().rsplit(':').next().unwrap().parse().unwrap(),native_inventory_id:1};
    let out=hold::parse_reply(&serde_json::to_vec(&d["rows"][0]["reply"]).unwrap(),&c,&r).unwrap();(c,out.reservation.unwrap(),out.revision)}
fn session(now:Instant,avatar:bool)->Session{
    let(o,f,b)=directory(0);let(c,r,revision)=source();let mut s=Session::new(11,[11;16],"127.0.0.1:46011".parse().unwrap(),now);
    s.base_peer=Some("127.0.0.1:47011".parse().unwrap());s.active=true;s.account_ready=true;s.account_probe=true;s.sync_mask=7;s.rx=1;s.tx=Window::interactive();s.identity=Some(o);s.hangar=Some(f);
    s.ammo_service=Some(ammo_session::State::new(crate::ammo_service091::Metadata{revision,wire_revision:7},true).with_research(true));
    s.ammo_service.as_mut().unwrap().replace_pool(s.hangar.as_ref().unwrap().p04m_binding().cloned()).unwrap();
    let sha=s.hangar.as_ref().unwrap().state_sha256().iter().map(|b|format!("{b:02x}")).collect::<String>();
    let projection=crate::profile13_hold_projection091::parse(&fs::read(s.identity.as_ref().unwrap().fixture_dir.join("p08b-owner-hold.json")).unwrap(),&c.account_id,c.native_database_id,b.revision,&sha).unwrap();
    let mut client=Client::new(0);client.join_requested=false;client.return_generation=1;client.phase=if avatar{Phase::Leaving}else{Phase::Account};
    let mut p=service::State::new(c.run_id,revision).unwrap();p.reservation_hold=Some(r);p.hold_projection=Some(Arc::new(projection));p.hold_return_pending=avatar;
    p.hold_departure_reason=avatar.then_some(hold::DepartureReason::ManualLeave);client.profile13=Some(p);s.shared=Some(client);s.arena_base=avatar;s
}
fn pristine_world(now:Instant,battle:u64)->World{
    let mut w=World::new_for_roster(battle,now,crate::map_profile091::MapId::Prohorovka,2).unwrap();
    w.bind_geometry(Arc::new(super::super::super::super::geometry::tests::bundle())).unwrap();w.bind_geometry(Arc::new(super::super::super::super::geometry::tests::is7_bundle())).unwrap();
    w.enable_ap_test_lab().unwrap();w.bind_terrain(Arc::new(super::super::super::super::terrain::tests::actual_prohorovka().clone())).unwrap();
    w.enable_mixed_ammo().unwrap();w.enable_lifecycle(super::super::super::super::lifecycle::Rules::prohorovka()).unwrap();w.enable_ammo_detonation().unwrap();w.enable_result_spots().unwrap();w.enable_owner_hold().unwrap();w
}
fn attached_world(now:Instant,owner:Arc<crate::identity091::Profile>)->(World,Capture){
    let(c,r,rev)=source();let mut w=pristine_world(now,r.battle);
    let mut capture=Capture::new(c.run_id,r.battle).unwrap();
    let rows:Value=serde_json::from_slice(include_bytes!("../../../../tests/fixtures/p08b-owner-hold-first-vectors.json")).unwrap();let q=&rows["vectors"][3]["request"];let dc=context(q);
    let dr=hold::parse_reply(&serde_json::to_vec(&rows["vectors"][3]["response"]).unwrap(),&dc,&hold::Request::Admit{battle:r.battle,native_inventory_id:1}).unwrap();
    let d=Arc::new(crate::identity091::Profile{account_id:dc.account_id,database_id:dc.native_database_id,name:"ExtendedDTest".into(),fixture_dir:PathBuf::new()});
    for(slot,(o,r,revision))in[(owner,r,rev),(d,dr.reservation.unwrap(),dr.revision)].into_iter().enumerate(){let sid=11+slot as u32;
        let who=model::Identity{account:o.account_id.clone(),database:o.database_id,name:o.name.clone()};assert_eq!(w.attach_owned_hold(who,sid,&r.frozen).unwrap(),slot);capture.register(&w,slot,sid,o,r,revision).unwrap();}
    w.start(now).unwrap();w.lifecycle_created_unix=Some(1792080000);w.set_ready(0,11).unwrap();w.set_ready(1,12).unwrap();w.advance_lifecycle(now).unwrap();(w,capture)
}
fn world(now:Instant,owner:Arc<crate::identity091::Profile>)->(World,Capture){
    let(mut w,mut capture)=attached_world(now,owner);
    w.advance(now+Duration::from_millis(100)).unwrap();w.advance_lifecycle(now+Duration::from_millis(100)).unwrap();w.detach(11).unwrap();capture.departed_after_detach(&w,0,11,hold::DepartureReason::ManualLeave).unwrap();(w,capture)
}
fn completion(index:usize,capture:&Capture)->service::CompletionHold{
    let(o,f,b)=directory(if index==1{0}else{2});let d=data();let q=&d["rows"][index]["request"];let c=context(q);
    let request=if index==1{hold::Request::Inspect}else{hold::Request::Finish(capture.seal().unwrap().finish(0).unwrap().clone())};
    assert_eq!(c,capture.link(0).unwrap().context(index==2));
    if index==2{let hold::Request::Finish(ref finish)=request else{panic!()};
        assert_eq!(serde_json::from_str::<Value>(finish.results_json.as_ref().unwrap()).unwrap(),serde_json::from_str::<Value>(q["results_json"].as_str().unwrap()).unwrap());}
    let reply=hold::parse_reply(&serde_json::to_vec(&d["rows"][index]["reply"]).unwrap(),&c,&request).unwrap();
    let sha=f.state_sha256().iter().map(|b|format!("{b:02x}")).collect::<String>();let projection=crate::profile13_hold_projection091::parse(&fs::read(o.fixture_dir.join("p08b-owner-hold.json")).unwrap(),&o.account_id,o.database_id,b.revision,&sha).unwrap();
    service::CompletionHold{source_session:11,old_owner:o.clone(),context:c,request,reply,fresh:Some(service::FreshHold{fresh:service::Fresh{owner:o,fixtures:f,binding:b},projection}),refresh_error:None}
}
fn seal(w:&mut World,c:&mut Capture,now:Instant){w.advance(now+Duration::from_millis(200)).unwrap();w.advance_lifecycle(now+Duration::from_millis(200)).unwrap();assert!(c.freeze_outcome(w).unwrap());}
fn contained_completion(capture:&Capture)->service::CompletionHold{
    let row=contained_projection();let c=context(&row["request"]);assert_eq!(c,capture.link(0).unwrap().context(true));
    let finish=capture.seal().unwrap().finish(0).unwrap().clone();assert_eq!(finish.finalization,hold::Finalization::ContainedFailure{tick:1001});assert!(finish.results_json.is_none());
    let request=hold::Request::Finish(finish);let reply=hold::parse_reply(&serde_json::to_vec(&row["reply"]).unwrap(),&c,&request).unwrap();
    let(o,fixtures,binding)=directory(4);let sha=fixtures.state_sha256().iter().map(|b|format!("{b:02x}")).collect::<String>();
    let projection=crate::profile13_hold_projection091::parse(&fs::read(o.fixture_dir.join("p08b-owner-hold.json")).unwrap(),&o.account_id,o.database_id,binding.revision,&sha).unwrap();
    service::CompletionHold{source_session:11,old_owner:o.clone(),context:c,request,reply,fresh:Some(service::FreshHold{fresh:service::Fresh{owner:o,fixtures,binding},projection}),refresh_error:None}
}
fn frame(s:&Session,payload:&[u8],ack:u32)->Frame{Frame{flags:0x458,sequence:Some(s.rx),cumulative:Some(ack),selective:vec![],body:[vec![1],s.token.to_le_bytes().to_vec(),payload.to_vec()].concat(),piggybacks:vec![]}}
fn sync(id:i16,cmd:i16,rev:i64)->Vec<u8>{let mut b=vec![0x8e,20,0];b.extend(id.to_le_bytes());b.extend(cmd.to_le_bytes());b.extend(rev.to_le_bytes());b.extend(0i32.to_le_bytes());b.extend(0i32.to_le_bytes());b}
fn warm(s:&mut Session,now:Instant){assert_eq!(s.tx.due(now,s.rx).unwrap().unwrap().0,0);let mut payload=vec![9];payload.extend(sync(226,100,7));payload.extend(sync(227,300,s.hangar.as_ref().unwrap().shop_sync_revision().unwrap()));payload.extend(sync(228,600,0));
    s.receive(&frame(s,&payload,1),now).unwrap();assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Account);assert_eq!(s.ammo_service.as_ref().unwrap().wire_revision(),1);
    for _ in 0..64{s.drain_outbox().unwrap();let mut last=None;while let Some((n,_,_))=s.tx.due(now,s.rx).unwrap(){last=Some(n);}if let Some(n)=last{s.receive(&Frame{flags:0,sequence:None,cumulative:Some(n+1),selective:vec![],body:vec![],piggybacks:vec![]},now).unwrap();}else{assert!(s.outbox.is_empty()&&s.tx.len()==0);break;}}
}
fn same(a:&Session,b:&Session){assert_eq!((a.rx,a.tx.len(),a.tx.cumulative,a.arena_base,a.sync_mask),(b.rx,b.tx.len(),b.tx.cumulative,b.arena_base,b.sync_mask));assert_eq!(a.outbox,b.outbox);assert_eq!(a.shared.as_ref().unwrap().profile13,b.shared.as_ref().unwrap().profile13);assert_eq!(a.hangar.as_ref().unwrap().state_sha256(),b.hangar.as_ref().unwrap().state_sha256());assert_eq!(a.ammo_service.as_ref().unwrap().revision(),b.ammo_service.as_ref().unwrap().revision());assert_eq!(a.ammo_service.as_ref().unwrap().wire_revision(),b.ammo_service.as_ref().unwrap().wire_revision());}
#[test]fn p08b_hold5_real_inspect_warm_then_final_incremental_keeps_source_actor_and_native_epoch(){
    let now=Instant::now();let s=session(now,true);let(mut w,capture)=world(now,s.identity.clone().unwrap());let inspected=completion(1,&capture);
    let held=delivery::stage_held_return(&s,&capture,0,&inspected,now).unwrap();let mut returned=held.session.unwrap();let mut capture=held.capture;
    assert!(capture.held_inspected(0).unwrap());assert!(state(&mut returned).unwrap().reservation_hold.is_some());assert!(!state(&mut returned).unwrap().garage_idle());warm(&mut returned,now);
    seal(&mut w,&mut capture,now);let final_reply=completion(2,&capture);let staged=delivery::stage_final(&returned,&capture,0,&final_reply,now).unwrap();let mut out=staged.session;
    assert_eq!(out.ammo_service.as_ref().unwrap().revision(),41);assert_eq!(out.ammo_service.as_ref().unwrap().wire_revision(),2);assert_eq!(out.shared.as_ref().unwrap().phase,Phase::Account);assert!(state(&mut out).unwrap().garage_idle());
    let mut bodies=Vec::new();while let Some((_,_,b))=out.tx.due(now,out.rx).unwrap(){bodies.push(transport091::parse_interactive(&b).unwrap().body);}bodies.extend(out.outbox.iter().cloned());
    assert_eq!(bodies.len(),1);assert_eq!(&bodies[0][..2],&[0x13,0x57]);assert_eq!(w.actors[0].session,None);assert_eq!(w.actors[0].fire.typed().unwrap().counts(),[0,4,10]);
}
#[test]fn p08b_hold5_known_inspect_and_final_are_atomic_under_real_window_pressure(){
    let now=Instant::now();let s=session(now,true);let(mut w,mut capture)=world(now,s.identity.clone().unwrap());let inspected=completion(1,&capture);
    let mut full=s.clone();for _ in 0..128{full.outbox.push_back(vec![13,1]);}let before=full.clone();assert!(delivery::stage_held_return(&full,&capture,0,&inspected,now).is_err());same(&full,&before);assert!(!capture.held_inspected(0).unwrap());
    let held=delivery::stage_held_return(&s,&capture,0,&inspected,now).unwrap();let mut returned=held.session.unwrap();capture=held.capture;warm(&mut returned,now);seal(&mut w,&mut capture,now);let finished=completion(2,&capture);
    for _ in 0..128{returned.outbox.push_back(vec![13,1]);}let before=returned.clone();assert!(delivery::stage_final(&returned,&capture,0,&finished,now).is_err());same(&returned,&before);assert_eq!(finished.context,capture.link(0).unwrap().context(true));
    returned.outbox.clear();let out=delivery::stage_final(&returned,&capture,0,&finished,now).unwrap();assert!(out.session.shared.as_ref().unwrap().profile13.as_ref().unwrap().reservation_hold.is_none());
}
#[test]fn p08b_hold5_second_locked_account_disconnect_uses_same_source_and_exact_receipt_cleanup(){
    let now=Instant::now();let mut original=session(now,true);original.active=false;let(mut w,capture)=world(now,original.identity.clone().unwrap());let inspected=completion(1,&capture);
    let first=delivery::stage_held_return(&original,&capture,0,&inspected,now).unwrap();assert_eq!(first.release_retired_source,Some(11));let mut capture=first.capture;
    let mut replacement=session(now,false);replacement.id=77;replacement.shared.as_mut().unwrap().profile13.as_mut().unwrap().hold_account_only=true;
    let owner=replacement.identity.as_ref().unwrap();let binding=replacement.shared.as_ref().unwrap().profile13.as_ref().unwrap().hold_projection.as_ref().unwrap();let sha=replacement.hangar.as_ref().unwrap().state_sha256().iter().map(|b|format!("{b:02x}")).collect::<String>();
    delivery::check_locked_resume(&capture,owner,&inspected.reply,binding,&sha).unwrap();replacement.active=false;
    capture.require_retired_inspect(&source().1).unwrap();assert!(!capture.held_inspected(0).unwrap());let second=delivery::stage_held_return(&replacement,&capture,0,&inspected,now).unwrap();assert_eq!(second.release_retired_source,Some(77));capture=second.capture;
    assert_eq!(capture.link(0).unwrap().source().source_session_id,11);assert_eq!(capture.departure(0).unwrap().unwrap().reason,hold::DepartureReason::ManualLeave);
    seal(&mut w,&mut capture,now);let finished=completion(2,&capture);let mut d=Dispatcher::default();d.hold.capture=Some(capture);d.retired.push(replacement.clone());
    let mut foreign=replacement;foreign.id=88;foreign.shared.as_mut().unwrap().profile13.as_mut().unwrap().reservation_hold.as_mut().unwrap().reservation_id="FOREIGN-ACTIVE5".into();d.retired.push(foreign);
    d.hold.task=Some(TaskHold{session:11,owner:finished.old_owner.clone(),context:finished.context.clone(),request:finished.request.clone(),purpose:Purpose::Final(0)});d.hold.completed=Some(finished);
    let mut table=Table::default();d.publish_hold_completed(&mut table,now).unwrap();assert!(d.retired.iter().all(|s|s.id!=77));assert_eq!(d.retired.len(),1);assert_eq!(d.retired[0].id,88);
}
#[test]fn p08b_hold5_outcome_beats_inspect_and_pre_avatar_cancel_is_not_pristine(){
    let now=Instant::now();let s=session(now,true);let(mut w,mut capture)=world(now,s.identity.clone().unwrap());seal(&mut w,&mut capture,now);let finished=completion(2,&capture);
    let out=delivery::stage_final(&s,&capture,0,&finished,now).unwrap();assert!(!out.session.arena_base);assert_eq!(out.session.shared.as_ref().unwrap().phase,Phase::Returning);assert!(out.session.shared.as_ref().unwrap().natural_result.is_none());
    let mut pre=session(now,false);state(&mut pre).unwrap().hold_return_pending=true;state(&mut pre).unwrap().hold_departure_reason=Some(hold::DepartureReason::ManualLeave);
    let(mut w,mut c)=world(now,pre.identity.clone().unwrap());let mut d=Dispatcher::default();d.hold.capture=Some(c.clone());let mut table=Table::default();table.sessions.push(pre);
    assert!(d.hold_pre_avatar_failure(&table,&w).is_some());d.before_hold_reset(&w).unwrap();let f=d.hold.capture.as_ref().unwrap().seal().unwrap().finish(0).unwrap();
    assert!(matches!(f.finalization,hold::Finalization::ContainedFailure{..}));assert!(f.source_link.is_some()&&f.results_json.is_none());
    // Once the same owner really returned to locked Account, subsequent
    // disconnects must not abort the continuing World on this startup guard.
    state(&mut table.sessions[0]).unwrap().hold_account_only=true;d.hold.capture=Some(c.clone());assert!(d.hold_pre_avatar_failure(&table,&w).is_none());
    // Never claim that an already registered source can be no-actor pristine.
    assert_eq!(c.links().len(),2);assert!(w.attach_owned_hold(model::Identity{account:source().0.account_id,database:3,name:"ExtendedCTest".into()},99,&source().1.frozen).is_err());
}
#[test]fn p08b_hold5_same_session_two_actual_admissions_do_not_reuse_first_manual_departure(){
    let now=Instant::now();let s=session(now,true);let(mut w,capture)=world(now,s.identity.clone().unwrap());let inspected=completion(1,&capture);
    let held=delivery::stage_held_return(&s,&capture,0,&inspected,now).unwrap();let mut first=held.session.unwrap();let mut capture=held.capture;warm(&mut first,now);seal(&mut w,&mut capture,now);
    let f=completion(2,&capture);let mut first=delivery::stage_final(&first,&capture,0,&f,now).unwrap().session;
    assert_eq!(state(&mut first).unwrap().hold_departure_reason,Some(hold::DepartureReason::ManualLeave));
    let row=next_admission();let c=context(&row["request"]);assert_eq!(c.expected_revision,first.ammo_service.as_ref().unwrap().revision());
    let battle=row["request"]["battle_id"].as_str().unwrap().rsplit(':').next().unwrap().parse().unwrap();let request=hold::Request::Admit{battle,native_inventory_id:1};
    let reply=hold::parse_reply(&serde_json::to_vec(&row["reply"]).unwrap(),&c,&request).unwrap();let(o,fixtures,binding)=directory(3);
    let sha=fixtures.state_sha256().iter().map(|b|format!("{b:02x}")).collect::<String>();let projection=crate::profile13_hold_projection091::parse(&fs::read(o.fixture_dir.join("p08b-owner-hold.json")).unwrap(),&o.account_id,o.database_id,binding.revision,&sha).unwrap();
    let completion=service::CompletionHold{source_session:11,old_owner:o.clone(),context:c,request,reply,fresh:Some(service::FreshHold{fresh:service::Fresh{owner:o,fixtures,binding},projection}),refresh_error:None};
    first.shared.as_mut().unwrap().join_requested=true;state(&mut first).unwrap().selection=Some(1);
    let mut second=delivery::stage_admitted(&first,&completion).unwrap().session;assert_eq!(state(&mut second).unwrap().hold_departure_reason,None);assert!(!state(&mut second).unwrap().hold_return_pending);
    let next_world=World::new_for_roster(battle,now,crate::map_profile091::MapId::Prohorovka,2).unwrap();Dispatcher::terminal_hold(&mut second,&next_world,FinishReason::Disconnect).unwrap();
    assert_eq!(state(&mut second).unwrap().hold_departure_reason,Some(hold::DepartureReason::Disconnect));assert_eq!(capture.departure(0).unwrap().unwrap().reason,hold::DepartureReason::ManualLeave);
    assert_eq!(capture.seal().unwrap().finish(0).unwrap(),match &f.request{hold::Request::Finish(f)=>f,_=>panic!()});
}
#[test]fn p08b_hold5_dispatch_known_reply_and_peer_validation_failure_roll_back_whole_publish(){
    let now=Instant::now();let s=session(now,false);let(mut w,mut capture)=world(now,s.identity.clone().unwrap());seal(&mut w,&mut capture,now);let finished=completion(2,&capture);
    let mut retained=s.clone();retained.id=77;retained.active=false;retained.shared.as_mut().unwrap().profile13.as_mut().unwrap().revision=41; // poisoned current cached revision
    let mut table=Table::default();table.sessions.push(s);let before=table.sessions[0].clone();let mut d=Dispatcher::default();
    d.hold.capture=Some(capture);d.retired.push(retained);d.hold.task=Some(TaskHold{session:11,owner:finished.old_owner.clone(),context:finished.context.clone(),request:finished.request.clone(),purpose:Purpose::Final(0)});d.hold.completed=Some(finished);
    let key=d.hold.completed.as_ref().unwrap().context.clone();let request=d.hold.completed.as_ref().unwrap().request.clone();
    assert!(d.publish_hold_completed(&mut table,now).is_err());same(&table.sessions[0],&before);assert_eq!(d.hold.completed.as_ref().unwrap().context,key);assert_eq!(d.hold.completed.as_ref().unwrap().request,request);assert!(!d.hold.settled[0]);assert_eq!(d.retired.len(),1);
    state(&mut d.retired[0]).unwrap().revision=40;d.publish_hold_completed(&mut table,now).unwrap();assert!(d.retired.is_empty());assert!(d.hold.completed.is_none());assert_eq!(table.sessions[0].ammo_service.as_ref().unwrap().wire_revision(),8);
}
#[test]fn p08b_hold5_group_attach_defers_first_peer_so_native_account_cancel_remains_no_actor(){
    let now=Instant::now();let mut s=session(now,false);let mut w=pristine_world(now,source().1.battle);let mut d=Dispatcher::default();
    s.shared.as_mut().unwrap().join_requested=true;s.shared.as_mut().unwrap().hangar_since=Some(now);
    let mut table=Table::default();table.sessions.push(s);let before=w.failure_snapshot();d.attach_hold_ready_group(&mut table,&mut w,&source().0.run_id,now+Duration::from_secs(4)).unwrap();
    assert!(w.actors.is_empty()&&d.hold.capture.is_none());assert_eq!(w.failure_snapshot(),before);
    let mut cancel=vec![0x8e,20,0,202,0];cancel.extend(701i16.to_le_bytes());cancel.extend(0i64.to_le_bytes());cancel.extend(0i32.to_le_bytes());cancel.extend(0i32.to_le_bytes());
    let s=&mut table.sessions[0];s.receive(&frame(s,&cancel,0),now).unwrap();assert!(!s.shared.as_ref().unwrap().join_requested);Dispatcher::terminal_hold(s,&w,FinishReason::ManualLeave).unwrap();
    let p=state(s).unwrap();assert!(p.hold_return_pending);let r=p.reservation_hold.as_ref().unwrap().clone();let f=pristine_cancel(&r,s.identity.as_ref().unwrap()).unwrap();
    assert_eq!(f.finalization,hold::Finalization::PristineCancel);assert!(f.source_link.is_none()&&f.departure.is_none());assert_eq!(f.remaining.map(|r|r.count),[0,4,10]);assert!(d.hold_pre_avatar_failure(&table,&w).is_none());
}
#[test]fn p08b_hold5_final_never_patches_a_new_account_that_already_loaded_released_fresh(){
    let now=Instant::now();let original=session(now,false);let(mut w,mut capture)=world(now,original.identity.clone().unwrap());seal(&mut w,&mut capture,now);let finished=completion(2,&capture);
    let(mut current,fixtures,binding)=directory(2);let mut replacement=original.clone();replacement.id=77;replacement.identity=Some(current.clone());replacement.hangar=Some(fixtures);
    replacement.ammo_service=Some(ammo_session::State::new(binding,true).with_research(true));let p=state(&mut replacement).unwrap();p.revision=41;p.reservation_hold=None;p.hold_projection=None;p.hold_return_pending=false;
    let before=replacement.clone();assert_eq!(delivery::current_final_recipient(&[replacement.clone()],&capture,0,41).unwrap(),None);delivery::validate_finished_without_delivery(&capture,0,&finished).unwrap();same(&replacement,&before);
    // A foreign current receipt is never treated as an already-released cache.
    state(&mut replacement).unwrap().reservation_hold=Some(source().1);state(&mut replacement).unwrap().reservation_hold.as_mut().unwrap().reservation_id="foreign".into();
    assert!(delivery::current_final_recipient(&[replacement],&capture,0,41).is_err());
}
#[test]fn p08b_hold5_pre_avatar_final_closes_actual_account_queue_with_update_atomically(){
    let now=Instant::now();let mut s=session(now,false);s.shared.as_mut().unwrap().queue_announced=true;s.shared.as_mut().unwrap().join_requested=true;
    let(mut w,mut capture)=attached_world(now,s.identity.clone().unwrap());
    Dispatcher::terminal_hold(&mut s,&w,FinishReason::ManualLeave).unwrap();w.advance(now+Duration::from_millis(100)).unwrap();w.detach(11).unwrap();
    capture.departed_after_detach(&w,0,11,hold::DepartureReason::ManualLeave).unwrap();assert!(capture.freeze_contained_failure(&w).unwrap());
    let finished=contained_completion(&capture);assert!(!s.arena_base);assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Account);
    let mut pressure=s.clone();for _ in 0..127{pressure.outbox.push_back(vec![13,1]);}let before=pressure.clone();
    assert!(delivery::stage_final(&pressure,&capture,0,&finished,now).is_err());same(&pressure,&before);assert!(pressure.shared.as_ref().unwrap().queue_announced);
    let mut out=delivery::stage_final(&s,&capture,0,&finished,now).unwrap().session;assert!(!out.arena_base);assert_eq!(out.shared.as_ref().unwrap().phase,Phase::Account);
    assert!(!out.shared.as_ref().unwrap().queue_announced&&!out.shared.as_ref().unwrap().join_requested);assert!(state(&mut out).unwrap().garage_idle());
    assert_eq!(out.ammo_service.as_ref().unwrap().revision(),41);assert_eq!(out.ammo_service.as_ref().unwrap().wire_revision(),8);
    let first=out.tx.due(now,out.rx).unwrap().unwrap();let second=out.tx.due(now,out.rx).unwrap().unwrap();
    assert_eq!(&transport091::parse_interactive(&first.2).unwrap().body[..2],&[0x13,0x57]);
    assert_eq!(transport091::parse_interactive(&second.2).unwrap().body,crate::map_drive_world091::queue_callback(false));assert!(out.tx.due(now,out.rx).unwrap().is_none());
}
#[test]fn p08b_hold5_issued_shared_avatar_reset_stays_reliable_and_uses_real_return_path(){
    let now=Instant::now();let mut s=session(now,false);s.shared.as_mut().unwrap().join_requested=true;
    let(mut w,mut capture)=attached_world(now,s.identity.clone().unwrap());let reset=wire::reset(&w,0).unwrap();
    // Production shared_start queues reset and flips arena_base on the SAME
    // clone commit. No test flips the flag or erases that reliable packet.
    assert!(s.ready_for_arena_base());s.shared_start(&w,now).unwrap();assert!(s.arena_base);assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Enable);assert_eq!(s.tx.len(),1);
    Dispatcher::terminal_hold(&mut s,&w,FinishReason::ManualLeave).unwrap();w.advance(now+Duration::from_millis(100)).unwrap();w.detach(11).unwrap();
    capture.departed_after_detach(&w,0,11,hold::DepartureReason::ManualLeave).unwrap();assert!(capture.freeze_contained_failure(&w).unwrap());
    let finished=contained_completion(&capture);let mut out=delivery::stage_final(&s,&capture,0,&finished,now).unwrap().session;
    assert!(!out.arena_base);assert_eq!(out.shared.as_ref().unwrap().phase,Phase::Returning);assert!(out.drive_return_account.is_some());
    let first=out.tx.due(now,out.rx).unwrap().unwrap();let second=out.tx.due(now,out.rx).unwrap().unwrap();
    assert_eq!(first.0,0);assert_eq!(transport091::parse_interactive(&first.2).unwrap().body,reset);
    assert_eq!(second.0,1);assert_eq!(transport091::parse_interactive(&second.2).unwrap().body,crate::map_drive_world091::return_account(&s.identity.as_ref().unwrap().name).unwrap());
    assert!(out.tx.due(now,out.rx).unwrap().is_none());assert_eq!(out.drive_return_account.as_ref().unwrap().creation,Some((1,false)));
}
