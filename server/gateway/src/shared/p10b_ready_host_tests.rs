//! Actual Manager/Controller/Session/Window; real readonly SQL-exported C/D
//! cache+Selection DTOs. Session/channel/scheduling are AUTHORED fixtures.
//! No HTTP worker, identity login, native UI, grant, reserve or World launch.
use super::*;
use crate::training091::{ingress as ingress,selection,wire as native};
use sha2::{Digest,Sha256};
use serde_json::Value;
use std::sync::atomic::{AtomicU64,Ordering};
const SAVED:&[u8]=include_bytes!("../../../../tests/fixtures/p10b-selection-writer-vectors.json");
const SAVED_SHA:&str="493511296d5c3b09fa1ce5d9906b48d565b02eab345191659d079d1294e7da97";
const PROJECT:&[u8]=include_bytes!("../../../../tests/fixtures/p10b-ready-project-projection.json");
const PROJECT_SHA:&str="8502c7154a1a18f0a4ba447895860103400181033c39672e3bf0aa107f132d0c";
fn row(index:usize)->Value{assert_eq!(format!("{:x}",Sha256::digest(SAVED)),SAVED_SHA);serde_json::from_slice::<Value>(SAVED).unwrap()["vectors"][index].clone()}
fn profile(index:usize)->Arc<crate::identity091::Profile>{
    static SERIAL:AtomicU64=AtomicU64::new(0);assert_eq!(format!("{:x}",Sha256::digest(PROJECT)),PROJECT_SHA);
    let proof:Value=serde_json::from_slice(PROJECT).unwrap();assert_eq!(proof["schema"],"p10b-ready-project-projection.v1");
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/p10b-ready-host");fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();
    let nanos=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();let dir=root.join(format!("{}-{nanos}-{}",std::process::id(),SERIAL.fetch_add(1,Ordering::Relaxed)));fs::create_dir(&dir).unwrap();
    let files=proof["profiles"][index]["files"].as_array().unwrap();assert_eq!(files.len(),9);
    for file in files{let name=file["name"].as_str().unwrap();assert!(["state.bin","shop.bin","dossier.bin","manifest.json","compatibility.json","ammo-service.json","crew-barracks.json","research-service.json","p04m-pool.json"].contains(&name));
        let hex=file["hex"].as_str().unwrap();assert!(hex.len()<=131072&&hex.len()%2==0);let bytes=hex.as_bytes().chunks_exact(2).map(|pair|u8::from_str_radix(std::str::from_utf8(pair).unwrap(),16).unwrap()).collect::<Vec<_>>();
        assert_eq!(bytes.len()as u64,file["bytes"].as_u64().unwrap());assert_eq!(format!("{:x}",Sha256::digest(&bytes)),file["sha256"].as_str().unwrap());fs::write(dir.join(name),bytes).unwrap();
    }
    let owner=&proof["profiles"][index]["owner"];Arc::new(crate::identity091::Profile{account_id:owner["account_id"].as_str().unwrap().into(),database_id:owner["native_database_id"].as_i64().unwrap()as i32,name:owner["name"].as_str().unwrap().into(),fixture_dir:dir})
}
fn session(index:usize,now:Instant)->Session{
    let sql=row(index);let q=&sql["request"];let owner=profile(index);let id=103+index as u32;
    let mut s=Session::new(id,[id as u8;16],format!("127.0.0.1:{}",44000+id).parse().unwrap(),now);s.base_peer=Some(format!("127.0.0.1:{}",45000+id).parse().unwrap());
    let fixtures=Arc::new(crate::hangar091::Fixtures::load_p04m(&owner.fixture_dir).unwrap());assert_eq!(format!("{:x}",Sha256::digest(fs::read(owner.fixture_dir.join("state.bin")).unwrap())),q["projection_stamp"]["native_state_sha256"].as_str().unwrap());
    s.identity=Some(owner);s.hangar=Some(fixtures);s.account_probe=true;s.account_ready=true;s.active=true;s.sync_mask=7;s.rx=1;s.tx=Window::interactive();s.training_opt_in=true;s.training_flights=Some(crate::training091::stream_flight::Flights::default());
    let mut state=ammo_session::State::new(crate::ammo_service091::Metadata{revision:q["expected_revision"].as_u64().unwrap(),wire_revision:1},true)
        .with_transfer(true).with_cross_vehicle(true).with_roster_recruitment(true).with_progression(true).with_dismissal(true).with_barracks(true).with_research(true);
    state.replace_pool(s.hangar.as_ref().unwrap().p04m_binding().cloned()).unwrap();s.ammo_service=Some(state);
    let mut c=Client::new(index);c.join_requested=false;c.profile13=Some(super::super::super::profile13_session::State::new(q["run_id"].as_str().unwrap().into(),q["expected_revision"].as_u64().unwrap()).unwrap());s.shared=Some(c);assert!(s.training_account_ready());s
}
fn completion(index:usize,s:&Session)->query::Completion{
    let sql=row(index);let q=&sql["request"];let owner=s.identity.clone().unwrap();
    let c=crate::battle091::profile13::Context{account_id:owner.account_id.clone(),native_database_id:owner.database_id,run_id:q["run_id"].as_str().unwrap().into(),expected_revision:q["expected_revision"].as_u64().unwrap(),command_key:"p10b:read-only-selection".into()};
    let request=selection::Request::new(&c,q["native_inventory_id"].as_u64().unwrap()as u32,selection::Stamp::parse(&q["projection_stamp"]).unwrap()).unwrap();
    assert_eq!(serde_json::from_slice::<Value>(&selection::encode_request(&request).unwrap()).unwrap(),sql["request"]);
    let selected=selection::parse_reply(&serde_json::to_vec(&sql["response"]).unwrap(),&request).unwrap();
    query::Completion{task:query::Task{session:s.id,owner:owner.clone(),expected_revision:c.expected_revision,native_inventory_id:request.native_inventory_id,run_id:c.run_id},snapshot:crate::identity091::room_selection::SelectionSnapshot{owner,fixtures:s.hangar.clone().unwrap(),binding:crate::ammo_service091::Metadata{revision:c.expected_revision,wire_revision:1},selection:selected}}
}
fn rpc(id:i16,command:i16,a:i64,b:i32)->ingress::Request{let mut p=vec![0x8e,20,0];p.extend(id.to_le_bytes());p.extend(command.to_le_bytes());p.extend(a.to_le_bytes());p.extend(b.to_le_bytes());p.extend(0i32.to_le_bytes());ingress::record(&p).unwrap().unwrap()}
fn create()->ingress::Request{let mut p=vec![0x9a,10,0];p.extend(4i32.to_le_bytes());p.extend(600i32.to_le_bytes());p.extend([1,0]);ingress::record(&p).unwrap().unwrap()}
fn bodies(s:&Session,now:Instant)->Vec<Vec<u8>>{let mut tx=s.tx.clone();let mut out=Vec::new();while let Some((_,_,raw))=tx.due(now,s.rx).unwrap(){out.push(transport091::parse_interactive(&raw).unwrap().body);}out.extend(s.outbox.iter().cloned());out}
fn flush(sessions:&mut[Session],now:Instant){for s in sessions{for _ in 0..64{s.drain_outbox().unwrap();let mut last=None;while let Some((n,_,_))=s.tx.due(now,s.rx).unwrap(){last=Some(n);}if let Some(n)=last{
    let ack=Frame{flags:0,sequence:None,cumulative:Some(n+1),selective:Vec::new(),body:Vec::new(),piggybacks:Vec::new()};assert!(s.receive_training_collected(&ack,now).unwrap().records.is_empty());
}else{assert!(s.outbox.is_empty()&&s.tx.len()==0);break;}}}}
fn fixture(now:Instant)->(Vec<Session>,Controller,Manager,Vec<ReadyTask>){
    let mut sessions=vec![session(0,now),session(1,now)];let mut engine=Controller::default();let manager=Manager::default();
    for s in &sessions{let call=current_call(s,source_binding(s).unwrap()).unwrap();let p=s.identity.as_ref().unwrap();engine.bind(call.caller,call.channel,p.name.clone(),p.database_id,0).unwrap();}
    let facts=manager.facts(&sessions,&engine).unwrap();let a=current_call(&sessions[0],source_binding(&sessions[0]).unwrap()).unwrap();let b=current_call(&sessions[1],source_binding(&sessions[1]).unwrap()).unwrap();
    let made=engine.apply(a,create(),&facts,0).unwrap();Manager::publish(&mut sessions,&engine,&made).unwrap();let key=engine.registry().authenticated_room(a.caller).unwrap();let native=engine.native_room(key).unwrap();flush(&mut sessions,now);
    let joined=engine.apply(b,rpc(202,400,i64::from(native),0),&facts,0).unwrap();Manager::publish(&mut sessions,&engine,&joined).unwrap();flush(&mut sessions,now);
    let mut tasks=Vec::new();for call in[a,b]{let batch=engine.apply(call,rpc(221,402,1,0),&facts,0).unwrap();assert_eq!(batch.ready.len(),1);tasks.extend(batch.ready);}
    (sessions,engine,manager,tasks)
}
fn same(sessions:&[Session],before:&[Session],now:Instant){for(s,b)in sessions.iter().zip(before){assert_eq!((s.rx,s.last_rx,s.tx.len(),s.tx.cumulative),(b.rx,b.last_rx,b.tx.len(),b.tx.cumulative));assert_eq!(s.outbox,b.outbox);assert_eq!(s.ammo_service,b.ammo_service);assert_eq!(s.training_flights,b.training_flights);assert_eq!(s.training_ids,b.training_ids);assert_eq!(s.received,b.received);assert_eq!(bodies(s,now),bodies(b,now));}}
fn no_ready(m:&Manager,c:&Controller){assert!(m.accepted.is_empty());assert!(c.registry().rooms().flat_map(|r|r.members()).all(|m|m.ready().is_none()));}
fn retained(m:&Manager,task:&ReadyTask,success:bool){let(t,r)=m.completed.as_ref().unwrap();assert_eq!(t,task);assert_eq!(r.is_ok(),success);if !success{assert_eq!(r.as_ref().err().unwrap(),"CONTROLLED_QUERY_FAILURE");}}

#[test]fn p10b_ready_host_real_SQL_two_simultaneous_original_requests_complete_after_native_publication(){
    let now=Instant::now();let(mut sessions,mut c,mut m,tasks)=fixture(now);
    for index in 0..2{let task=tasks[index].clone();
        let done=completion(index,&sessions[index]);let stamp=done.snapshot.fixtures.state_sha256();m.completed=Some((task.clone(),Ok(done)));m.poll(&mut sessions,&mut c,0).unwrap();
        assert!(m.completed.is_none());let who=task.caller().account;assert_eq!(m.accepted[&who].selection.reference().owner(),who);assert_eq!(sessions[index].hangar.as_ref().unwrap().state_sha256(),stamp);
        assert!(bodies(&sessions[index],now).contains(&native::plain_response(221,native::CommandResult::Success,"").unwrap()));flush(&mut sessions,now);
    }assert_eq!(m.accepted.len(),2);assert!(c.registry().rooms().flat_map(|r|r.members()).all(|m|m.ready().is_some()));
}
#[test]fn p10b_ready_host_success_peer_pressure_retains_identical_completed_before_callback_then_retries(){
    let now=Instant::now();let(mut sessions,mut c,mut m,tasks)=fixture(now);let done=completion(0,&sessions[0]);let owner=done.snapshot.owner.clone();let fixtures=done.snapshot.fixtures.clone();m.completed=Some((tasks[0].clone(),Ok(done)));
    sessions[1].outbox=VecDeque::from(vec![native::left();128]);let before=sessions.clone();let engine=c.clone();assert!(m.poll(&mut sessions,&mut c,0).is_err());same(&sessions,&before,now);assert_eq!(c,engine);no_ready(&m,&c);retained(&m,&tasks[0],true);
    let completion=m.completed.as_ref().unwrap().1.as_ref().unwrap();assert!(Arc::ptr_eq(&owner,&completion.snapshot.owner)&&Arc::ptr_eq(&fixtures,&completion.snapshot.fixtures));
    assert!(!bodies(&sessions[0],now).contains(&native::plain_response(221,native::CommandResult::Failure,"").unwrap()));flush(&mut sessions,now);
    m.poll(&mut sessions,&mut c,0).unwrap();assert!(m.completed.is_none());assert_eq!(m.accepted.len(),1);let q=bodies(&sessions[0],now);assert_eq!(q.iter().filter(|b|**b==native::plain_response(221,native::CommandResult::Success,"").unwrap()).count(),1);
    let q2=q.clone();m.poll(&mut sessions,&mut c,0).unwrap();assert_eq!(bodies(&sessions[0],now),q2);
}
#[test]fn p10b_ready_host_failed_query_callback_pressure_retains_exact_error_then_publishes_once(){
    let now=Instant::now();let(mut sessions,mut c,mut m,tasks)=fixture(now);m.completed=Some((tasks[0].clone(),Err("CONTROLLED_QUERY_FAILURE".into())));sessions[0].outbox=VecDeque::from(vec![native::left();128]);let before=sessions.clone();let engine=c.clone();
    assert!(m.poll(&mut sessions,&mut c,0).is_err());same(&sessions,&before,now);assert_eq!(c,engine);retained(&m,&tasks[0],false);no_ready(&m,&c);flush(&mut sessions,now);
    m.poll(&mut sessions,&mut c,0).unwrap();assert!(m.completed.is_none());no_ready(&m,&c);let q=bodies(&sessions[0],now);assert_eq!(q.iter().filter(|b|**b==native::plain_response(221,native::CommandResult::Failure,"").unwrap()).count(),1);
}
#[test]fn p10b_ready_host_explicit_own_notready_cannot_complete_prior_valid_SQL_ready(){
    let now=Instant::now();let(mut sessions,mut c,mut m,tasks)=fixture(now);let done=completion(0,&sessions[0]);let call=current_call(&sessions[0],source_binding(&sessions[0]).unwrap()).unwrap();let facts=m.facts(&sessions,&c).unwrap();
    c.apply(call,rpc(222,403,1,0),&facts,0).unwrap();m.completed=Some((tasks[0].clone(),Ok(done)));m.poll(&mut sessions,&mut c,0).unwrap();assert!(m.completed.is_none());no_ready(&m,&c);assert!(bodies(&sessions[0],now).contains(&native::plain_response(221,native::CommandResult::Failure,"").unwrap()));
}
#[test]fn p10b_ready_host_new_Account_generation_never_receives_old_callback_and_retirement_drains_job(){
    let now=Instant::now();let(mut sessions,mut c,mut m,tasks)=fixture(now);let done=completion(0,&sessions[0]);sessions[0].shared.as_mut().unwrap().return_generation+=1;
    m.completed=Some((tasks[0].clone(),Ok(done)));let before=sessions.clone();let engine=c.clone();assert!(m.poll(&mut sessions,&mut c,0).is_err());same(&sessions,&before,now);assert_eq!(c,engine);retained(&m,&tasks[0],true);no_ready(&m,&c);
    let facts=m.facts(&sessions,&c).unwrap();c.retire(tasks[0].caller(),tasks[0].channel(),&facts,0).unwrap();m.poll(&mut sessions,&mut c,0).unwrap();assert!(m.completed.is_none());no_ready(&m,&c);assert!(!bodies(&sessions[0],now).iter().any(|p|p.starts_with(&[0x13,0x4c])));
}
#[test]fn p10b_ready_host_actual_Fresh_owner_revision_state_wire_and_run_poison_cannot_grant_ready(){
    for poison in 0..7{let now=Instant::now();let(mut sessions,mut c,mut m,tasks)=fixture(now);let mut done=completion(0,&sessions[0]);
        match poison{
            0..=2=>{let p=&done.snapshot.owner;done.snapshot.owner=Arc::new(crate::identity091::Profile{account_id:if poison==0{row(1)["request"]["account_id"].as_str().unwrap().into()}else{p.account_id.clone()},database_id:if poison==1{p.database_id+1}else{p.database_id},name:if poison==2{"DifferentName".into()}else{p.name.clone()},fixture_dir:p.fixture_dir.clone()});},
            3=>done.snapshot.binding.revision+=1,
            4=>{done.snapshot.fixtures=sessions[1].hangar.clone().unwrap();},
            5=>done.snapshot.binding.wire_revision=2,
            _=>sessions[0].shared.as_mut().unwrap().profile13.as_mut().unwrap().run_id="12345678-1234-4234-8234-123456789abc".into(),
        }
        m.completed=Some((tasks[0].clone(),Ok(done)));m.poll(&mut sessions,&mut c,0).unwrap();assert!(m.completed.is_none(),"poison {poison}");no_ready(&m,&c);assert!(bodies(&sessions[0],now).contains(&native::plain_response(221,native::CommandResult::Failure,"").unwrap()),"poison {poison}");
    }
}
#[test]fn p10b_ready_host_accepted_reference_never_projects_ready_after_actual_ammo_revision_changes(){
    let now=Instant::now();let(mut sessions,mut c,mut m,tasks)=fixture(now);m.completed=Some((tasks[0].clone(),Ok(completion(0,&sessions[0]))));m.poll(&mut sessions,&mut c,0).unwrap();
    let who=tasks[0].caller().account;assert!(m.facts(&sessions,&c).unwrap()[&who].selected.is_some());let revision=sessions[0].ammo_service.as_ref().unwrap().revision();sessions[0].ammo_service.as_mut().unwrap().refresh_revision(revision+1).unwrap();
    match m.facts(&sessions,&c){Ok(facts)=>assert!(facts[&who].selected.is_none()),Err(_)=>{}};
}
#[test]fn p10b_ready_host_start_stale_account_stores_completed_failure_without_dispatching_HTTP(){
    let now=Instant::now();let(mut sessions,mut c,mut m,tasks)=fixture(now);m.enqueue(vec![tasks[0].clone()]).unwrap();
    let root=sessions[0].identity.as_ref().unwrap().fixture_dir.join("own-config");fs::create_dir(&root).unwrap();fs::write(root.join("token.txt"),"a".repeat(43)).unwrap();
    let mut value=serde_json::json!({"login_bind":"127.0.0.1:23014","base_bind":"127.0.0.1:23015","identity_endpoint":"127.0.0.1:3395","identity_token_file":root.join("token.txt"),"local_root":root.canonicalize().unwrap(),"session_duration_seconds":600,"battle_players":6,"visibility_v1":true,"training_rooms":true,"p04m_pool":true,"p06t_mixed_ammo":true});
    for key in["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression","crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle"]{value[key]=true.into();}
    let path=root.join("gateway.json");fs::write(&path,serde_json::to_vec(&value).unwrap()).unwrap();let mut config=crate::identity091::Config::load(path.to_str().unwrap()).unwrap();config.battle_run_id=row(0)["request"]["run_id"].as_str().unwrap().into();let config=Arc::new(config);
    m.start(&mut sessions,&mut c,config.clone(),false).unwrap();assert_eq!(m.queued.len(),1);assert!(m.pending.is_none()&&m.completed.is_none());
    sessions[0].shared.as_mut().unwrap().return_generation+=1;m.start(&mut sessions,&mut c,config,true).unwrap();assert!(m.queued.is_empty()&&m.pending.is_none());assert!(m.completed.as_ref().unwrap().1.is_err());no_ready(&m,&c);
}

#[path="p10b_retained_facts_tests.rs"]mod retained_facts;
