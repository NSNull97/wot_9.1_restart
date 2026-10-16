//! NOT_RUN scheduling tests. Strict actual saved Selection/Frozen source data,
//! with explicitly AUTHORED small cache/Session/Fresh and retargeted Task keys.
//! No current ownership, HTTP execution, Job thread or native UI proof.
use super::*;
use super::super::p10b_launch_host;
use crate::training091::{adapter,aliases,controller::Call,current_room::{ProfileStamp,Channel},ingress,selection};
use serde_json::{json,Value};
use sha2::{Digest,Sha256};
use std::{path::{Path,PathBuf},sync::atomic::{AtomicU64,Ordering}};
const SELECT:&[u8]=include_bytes!("../../../../tests/fixtures/p10b-selection-writer-vectors.json");
const SQL:&[u8]=include_bytes!("../../../../tests/fixtures/p10b-saga-writer-vectors.json");
fn account(s:&str)->io::Result<room::Account>{
 let mut bytes=[0;16];let compact=s.replace('-',"");if compact.len()!=32{return Err(bad("test UUID"));}
 for(i,pair)in compact.as_bytes().chunks_exact(2).enumerate(){bytes[i]=u8::from_str_radix(std::str::from_utf8(pair).map_err(|_|bad("test UUID"))?,16).map_err(|_|bad("test UUID"))?;}Ok(room::Account(bytes))
}
fn source_hex(bytes:&[u8;32])->String{bytes.iter().map(|b|format!("{b:02x}")).collect()}
fn values()->(Value,Value){
    assert_eq!(format!("{:x}",Sha256::digest(SELECT)),"493511296d5c3b09fa1ce5d9906b48d565b02eab345191659d079d1294e7da97");
    assert_eq!(format!("{:x}",Sha256::digest(SQL)),"2986a4eca23fb1cfe176be460ebbbeb015df0bfc0a48fcf86eb69675e92abee9");
    (serde_json::from_slice(SELECT).unwrap(),serde_json::from_slice(SQL).unwrap())
}
fn ctx(v:&Value)->crate::battle091::profile13::Context{crate::battle091::profile13::Context{
    account_id:v["account_id"].as_str().unwrap().into(),native_database_id:v["native_database_id"].as_i64().unwrap().try_into().unwrap(),
    command_key:v.get("command_key").and_then(Value::as_str).unwrap_or("selection-only").into(),expected_revision:v["expected_revision"].as_u64().unwrap(),run_id:v["run_id"].as_str().unwrap().into()}}
fn fixture(account:&str,db:i32,rev:u64,extra:bool)->(PathBuf,Arc<crate::hangar091::Fixtures>){
    static NEXT:AtomicU64=AtomicU64::new(0);
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/p10b-launch-host");fs::create_dir_all(&root).unwrap();
    let path=root.join(format!("{}-{}-{}",std::process::id(),std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos(),NEXT.fetch_add(1,Ordering::Relaxed)));fs::create_dir(&path).unwrap();
    let mut state=b"\x80\x02}(U\x03revK\x01U\x05ownerU".to_vec();state.push(account.len()as u8);state.extend(account.as_bytes());
    if extra{state.extend(b"U\x01xK\x01");}state.extend(b"u.");
    fs::write(path.join("state.bin"),&state).unwrap();fs::write(path.join("shop.bin"),b"\x80\x02}(U\x03revK\x03u.").unwrap();fs::write(path.join("dossier.bin"),b"\x80\x02(K\x00]t.").unwrap();
    let p=&crate::p04m_companion091::test_value(account,rev);let mut pool=p.clone();pool["native_database_id"]=db.into();pool["state_sha256"]=format!("{:x}",Sha256::digest(&state)).into();
    fs::write(path.join("p04m-pool.json"),serde_json::to_vec(&pool).unwrap()).unwrap();
    let manifest=json!({"fixture_version":13,"profile_version":13,"snapshot_revision":rev,"account_id":account,"native_database_id":db,
        "pool_schema":crate::p04m_companion091::SCHEMA,"pool_registry_sha256":crate::p04m_companion091::REGISTRY_SHA256,"pool_policy_sha256":crate::p04m_companion091::POLICY_SHA256});
    fs::write(path.join("manifest.json"),serde_json::to_vec(&manifest).unwrap()).unwrap();
    let f=Arc::new(crate::hangar091::Fixtures::load_p04m(&path).unwrap());(path,f)
}
fn live(owner:Arc<crate::identity091::Profile>,fixtures:Arc<crate::hangar091::Fixtures>,c:&crate::battle091::profile13::Context,now:Instant)->Session{
    let mut s=Session::new(100+owner.database_id as u32,[7;16],"127.0.0.1:41707".parse().unwrap(),now);
    s.identity=Some(owner);s.hangar=Some(fixtures);s.active=true;s.account_ready=true;s.sync_mask=7;s.rx=1;s.tx=Window::interactive();
    s.training_opt_in=true;s.training_flights=Some(Default::default());s.base_peer=Some("127.0.0.1:41708".parse().unwrap());
    s.ammo_service=Some(ammo_session::State::new(crate::ammo_service091::Metadata{revision:c.expected_revision,wire_revision:1},true).with_transfer(true).with_cross_vehicle(true)
        .with_roster_recruitment(true).with_progression(true).with_dismissal(true).with_barracks(true).with_research(true));
    s.ammo_service.as_mut().unwrap().replace_pool(s.hangar.as_ref().unwrap().p04m_binding().cloned()).unwrap();
    let mut client=Client::new(0);client.join_requested=false;client.hangar_since=Some(now);client.profile13=Some(persistence::State::new(c.run_id.clone(),c.expected_revision).unwrap());s.shared=Some(client);s
}
fn native(id:i16,cmd:i16,a:i64,b:i32)->ingress::Request{let mut raw=vec![0x8e,20,0];raw.extend(id.to_le_bytes());raw.extend(cmd.to_le_bytes());raw.extend(a.to_le_bytes());raw.extend(b.to_le_bytes());raw.extend(0i32.to_le_bytes());ingress::record(&raw).unwrap().unwrap()}
fn create()->ingress::Request{let mut raw=vec![0x9a,10,0];raw.extend(4i32.to_le_bytes());raw.extend(600i32.to_le_bytes());raw.extend([1,0]);ingress::record(&raw).unwrap().unwrap()}
fn call(s:&Session,stamp:&selection::Stamp)->Call{
    let mut source=[0;32];for(i,pair)in stamp.owner_source_sha256.as_bytes().chunks_exact(2).enumerate(){source[i]=u8::from_str_radix(std::str::from_utf8(pair).unwrap(),16).unwrap();}
    Call{caller:room::AuthLease{account:account(&s.identity.as_ref().unwrap().account_id).unwrap(),generation:u64::from(s.id)},
        channel:Channel{session:s.id,generation:s.training_account_generation()},profile:ProfileStamp{revision:s.ammo_service.as_ref().unwrap().revision()as u32,source_binding:source},expected_revision:s.ammo_service.as_ref().unwrap().revision()as u32}
}

pub(in crate::gateway091::shared::server) struct Input{pub(in crate::gateway091::shared::server) table:Table,pub(in crate::gateway091::shared::server) controller:Controller,pub(in crate::gateway091::shared::server) prepare:PrepareTask,pub(in crate::gateway091::shared::server) origins:BTreeMap<room::Account,LaunchOrigin>,pub(in crate::gateway091::shared::server) sql:Value}
pub(in crate::gateway091::shared::server) fn input(now:Instant)->Input{
    let(select,sql)=values();let sql=sql["cases"].as_array().unwrap().iter().find(|c|c["case"].as_str().unwrap().contains("two_real_owned")).unwrap().clone();
    let mut selections=Vec::new();let mut sessions=Vec::new();let mut calls=Vec::new();let mut controller=Controller::default();let mut facts=BTreeMap::new();
    for row in select["vectors"].as_array().unwrap().iter().take(2){let q=&row["request"];let c=ctx(q);
        let request=selection::Request::new(&c,1,selection::Stamp::parse(&q["projection_stamp"]).unwrap()).unwrap();
        let parsed=selection::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&request).unwrap();
        let lane=if c.native_database_id==3{"C"}else{"D"};let admit=sql["calls"][lane].as_array().unwrap().iter().find(|r|r["request"]["operation"]=="admit").unwrap();let mut admitted=ctx(&admit["request"]);
        admitted.expected_revision=c.expected_revision;
        let(path,fixtures)=fixture(&c.account_id,c.native_database_id,c.expected_revision,false);
        let owner=Arc::new(crate::identity091::Profile{account_id:c.account_id.clone(),database_id:c.native_database_id,name:format!("Owner{}",c.native_database_id),fixture_dir:path});
        let selected=saga::ReadySelection::from_selection(owner.clone(),100+c.native_database_id as u32,parsed).unwrap()
            .with_launch_scheduler_seam_for_test(admitted.run_id.clone(),source_hex(&fixtures.state_sha256()));
        let s=live(owner,fixtures,&admitted,now);let call=call(&s,selected.source_stamp());
        controller.bind(call.caller,call.channel,s.identity.as_ref().unwrap().name.clone(),c.native_database_id,0).unwrap();
        facts.insert(call.caller.account,adapter::NativeFacts{database_id:c.native_database_id,selected:None,descriptor:Vec::new(),igr_type:0,clan_database_id:0,clan_abbrev:String::new()});
        selections.push(selected);sessions.push(s);calls.push(call);
    }
    controller.apply(calls[0],create(),&facts,0).unwrap();let room=controller.registry().authenticated_room(calls[0].caller).unwrap();let native_room=controller.native_room(room).unwrap();
    controller.apply(calls[1],native(202,400,i64::from(native_room),0),&facts,0).unwrap();
    controller.apply(calls[0],native(222,404,i64::from(aliases::OWN_ENTITY_ID+1),2),&facts,0).unwrap();
    let mut origins=BTreeMap::new();
    for index in 0..2{let selected=&selections[index];let batch=controller.apply(calls[index],native(223,402,1,0),&facts,0).unwrap();let task=batch.ready[0].clone();
        let fact=facts.get_mut(&calls[index].caller.account).unwrap();fact.selected=Some(selected.reference().clone());fact.descriptor=selected.frozen().descriptor.clone();
        controller.complete_ready(&task,calls[index],1,selected.reference().clone(),&facts,0).unwrap();
        origins.insert(calls[index].caller.account,LaunchOrigin::capture(&sessions[index],&controller,task,selected.clone()).unwrap());
    }
    controller.apply(calls[0],native(224,411,1,0),&facts,0).unwrap();let batch=controller.apply(calls[0],native(225,411,2,0),&facts,0).unwrap();
    Input{table:Table{sessions,capacity:6,..Table::default()},controller,prepare:batch.prepare[0].clone(),origins,sql}
}
pub(in crate::gateway091::shared::server) fn begin(i:&mut Input)->Preparing{Preparing::begin(i.prepare.clone(),room::BattleKey(9007199254740993),i.origins.clone(),&i.controller,&mut i.table).unwrap()}
fn state(table:&Table)->Vec<(u32,persistence::State,u64,i64,VecDeque<Vec<u8>>,usize,bool)>{
    table.sessions.iter().map(|s|(s.id,owned_state(s).unwrap().clone(),s.ammo_service.as_ref().unwrap().revision(),s.ammo_service.as_ref().unwrap().wire_revision(),s.outbox.clone(),s.tx.len(),s.active)).collect()
}
/// Retarget ONLY scheduler keys to actual State.next_context output. Frozen,
/// source shell/crew/terminal data are actual DTOs; retargeted envelope is
/// AUTHORED component input, not a new actual SQL/HTTP capture.
fn completion(task:&saga::Task,sql:&Value,fresh:bool)->persistence::CompletionV2{
    let lane=if task.owner().database_id==3{"C"}else{"D"};
    let row=sql["calls"][lane].as_array().unwrap().iter().find(|r|r["request"]["operation"]==task.request().operation()).unwrap();
    let mut raw=row["response"].clone();let context=task.context().clone();let request=task.request().clone();
    raw["account_id"]=context.account_id.clone().into();raw["native_database_id"]=context.native_database_id.into();
    raw["command_key"]=context.command_key.clone().into();raw["run_id"]=context.run_id.clone().into();raw["source_revision"]=context.expected_revision.into();
    raw["revision"]=(context.expected_revision+1).into();
    if let Some(r)=raw["reservation"].as_object_mut(){
        let key=if let writer::Request::Finish{reservation_id,..}=&request{reservation_id.clone()}else{context.command_key.clone()};
        r.insert("reservation_id".into(),key.into());r.insert("run_id".into(),context.run_id.clone().into());
    }
    let reply=writer::parse_reply(&serde_json::to_vec(&raw).unwrap(),&context,&request).unwrap();
    done(task,reply,fresh)
}
fn done(task:&saga::Task,reply:writer::Reply,fresh:bool)->persistence::CompletionV2{
    let f=if fresh{let(path,fixtures)=fixture(&task.owner().account_id,task.owner().database_id,reply.revision,false);
        Some(persistence::Fresh{owner:Arc::new(crate::identity091::Profile{fixture_dir:path,account_id:task.owner().account_id.clone(),database_id:task.owner().database_id,name:task.owner().name.clone()}),fixtures,
            binding:crate::ammo_service091::Metadata{revision:reply.revision,wire_revision:1}})}else{None};
    persistence::CompletionV2{session:task.session(),old_owner:task.owner().clone(),context:task.context().clone(),request:task.request().clone(),reply,
        fresh:f,refresh_error:if fresh{None}else{Some(bad("AUTHORED projection failure"))}}
}
fn inspected(task:&saga::Task,fresh:bool)->persistence::CompletionV2{
    assert_eq!(task.request(),&writer::Request::Inspect);let c=task.context();
    let raw=json!({"version":2,"operation":"inspect","status":"inspected","account_id":c.account_id,"native_database_id":c.native_database_id,
        "command_key":c.command_key,"run_id":c.run_id,"source_revision":c.expected_revision,"revision":c.expected_revision,
        "replayed":false,"code":null,"reservation":null,"legacy_reservation":null,"policy_sha256":writer::POLICY_SHA256});
    done(task,writer::parse_reply(&serde_json::to_vec(&raw).unwrap(),c,task.request()).unwrap(),fresh)
}
fn admitted(p:&mut Preparing,i:&mut Input)->saga::Task{
    let task=p.next_task(&mut i.table,true).unwrap().unwrap();assert!(matches!(task.request(),writer::Request::Admit{..}));
    p.accept(&completion(&task,&i.sql,true)).unwrap();task
}
pub(in crate::gateway091::shared::server) fn finish_all_abort(p:&mut Preparing,i:&mut Input){
    while !p.ready_to_abort(){
        let task=p.next_task(&mut i.table,true).unwrap().unwrap();
        let c=if task.request()==&writer::Request::Inspect{inspected(&task,true)}else{completion(&task,&i.sql,true)};
        p.accept(&c).unwrap();
    }
}

#[test]fn p10b_preparing_begin_sets_every_guard_atomically_before_any_task_and_budget_failure_sets_none(){
    let now=Instant::now();let mut i=input(now);let before=state(&i.table);
    // C is last in canonical snapshot order (D then C): the late failure must
    // not leave D guarded on a failed whole begin.
    i.table.sessions[0].shared.as_mut().unwrap().profile13.as_mut().unwrap().command_counter=511;
    let refused=state(&i.table);assert!(Preparing::begin(i.prepare.clone(),room::BattleKey(77),i.origins.clone(),&i.controller,&mut i.table).is_err());
    assert_eq!(state(&i.table),refused);assert!(i.table.sessions.iter().all(|s|!owned_state(s).unwrap().in_flight));
    i.table.sessions[0].shared.as_mut().unwrap().profile13.as_mut().unwrap().command_counter=0;
    assert_eq!(state(&i.table),before);let p=begin(&mut i);
    assert!(i.table.sessions.iter().all(|s|owned_state(s).unwrap().in_flight));assert!(p.saga.retry().is_none());assert!(p.held.is_empty());
    assert!(i.table.sessions.iter().all(|s|owned_state(s).unwrap().command_counter==0));
}

#[test]fn p10b_preparing_serial_actual_state_contexts_and_held_outputs_never_publish_partial_reserve(){
    let now=Instant::now();let mut i=input(now);let mut p=begin(&mut i);
    let task=p.next_task(&mut i.table,true).unwrap().unwrap();assert_eq!(task.session(),104);assert!(task.context().command_key.ends_with(":104:1"));
    let before=state(&i.table);let retry=p.next_task(&mut i.table,true).unwrap().unwrap();assert_eq!(task.context(),retry.context());assert_eq!(task.request(),retry.request());assert_eq!(state(&i.table),before);
    assert!(!p.ready_to_launch());assert!(p.held.is_empty());p.accept(&completion(&task,&i.sql,true)).unwrap();assert_eq!(p.held.len(),1);assert!(!p.ready_to_launch());
    let task2=admitted(&mut p,&mut i);assert_eq!(task2.session(),103);assert!(p.ready_to_launch());assert_eq!(p.saga.reserved_refs().unwrap().len(),2);
    for s in &i.table.sessions{assert!(owned_state(s).unwrap().in_flight);assert!(!owned_state(s).unwrap().has_reservation());assert!(s.outbox.is_empty());assert_eq!(s.tx.len(),0);}
}

#[test]fn p10b_preparing_ambiguous_error_and_disconnect_keep_exact_pending_admit_before_compensation(){
    let now=Instant::now();let mut i=input(now);let mut p=begin(&mut i);let task=p.next_task(&mut i.table,true).unwrap().unwrap();
    let mut driver=Driver{key:Some(p.key()),unresolved:true,..Driver::default()};
    let report=driver.completed(&mut p,Err(bad("AUTHORED lost HTTP response")),now);assert_eq!(report.progress,Progress::RetryRetained);assert!(!driver.idle());
    assert!(p.abort_on_disconnect(task.session()));assert!(!p.abort_on_disconnect(999));
    i.table.sessions.iter_mut().find(|s|s.id==task.session()).unwrap().active=false;
    assert!(p.next_task(&mut i.table,false).unwrap().is_none());let retry=p.next_task(&mut i.table,true).unwrap().unwrap();
    assert_eq!(retry.context(),task.context());assert_eq!(retry.request(),task.request());assert!(!p.ready_to_abort());
    let c=completion(&task,&i.sql,true);assert_eq!(driver.completed(&mut p,Ok(c),now).progress,Progress::Accepted);
    let cancel=p.next_task(&mut i.table,true).unwrap().unwrap();assert_eq!(cancel.session(),task.session());
    let writer::Request::Finish{reason,remaining_ammunition,terminal_hp,..}=cancel.request()else{panic!("late admit must be cancelled, never Inspect")};
    assert_eq!(*reason,crate::battle091::profile13::FinishReason::Cancelled);assert_eq!(remaining_ammunition.map(|a|a.count),[0,4,10]);assert_eq!(*terminal_hp,90);
    p.accept(&completion(&cancel,&i.sql,true)).unwrap();assert!(!p.ready_to_abort());
    finish_all_abort(&mut p,&mut i);assert_eq!(p.saga.released_refs().unwrap().len(),2);
    let stage=p.stage_abort(&driver,&i.table,&i.controller,0).unwrap();
    assert!(!stage.sessions.iter().find(|s|s.id==task.session()).unwrap().active);
    assert!(stage.sessions.iter().all(|s|!owned_state(s).unwrap().in_flight));
}

#[test]fn p10b_preparing_projection_failure_retains_known_real_typed_reply_and_same_key_until_fresh_replay(){
    let now=Instant::now();let mut i=input(now);let mut p=begin(&mut i);let task=p.next_task(&mut i.table,true).unwrap().unwrap();
    let mut driver=Driver{key:Some(p.key()),unresolved:true,..Driver::default()};
    assert_eq!(driver.completed(&mut p,Ok(completion(&task,&i.sql,false)),now).progress,Progress::RetryRetained);
    assert_eq!(driver.known_status(),Some(writer::Status::Admitted));assert!(!driver.idle());assert!(p.held.is_empty());
    let retry=p.saga.retry().unwrap();assert_eq!(retry.context(),task.context());assert_eq!(retry.request(),task.request());
    let mut replay=completion(&task,&i.sql,true);replay.reply.replayed=true;
    assert_eq!(driver.completed(&mut p,Ok(replay),now).progress,Progress::Accepted);assert!(driver.idle());assert_eq!(p.held.len(),1);
    assert!(i.table.sessions.iter().all(|s|owned_state(s).unwrap().in_flight));
}

#[test]fn p10b_preparing_issued_null_inspect_requires_global_drain_and_actual_current_fresh_for_all_slots(){
    let now=Instant::now();let mut i=input(now);let mut p=begin(&mut i);p.abort();
    let before=state(&i.table);assert!(p.next_task(&mut i.table,false).unwrap().is_none());assert_eq!(state(&i.table),before);
    let task=p.next_task(&mut i.table,true).unwrap().unwrap();assert_eq!(task.request(),&writer::Request::Inspect);
    let mut driver=Driver{key:Some(p.key()),unresolved:true,..Driver::default()};
    assert_eq!(driver.completed(&mut p,Ok(inspected(&task,false)),now).progress,Progress::RetryRetained);assert!(!p.ready_to_abort());
    assert_eq!(p.saga.retry().unwrap().context(),task.context());
    assert_eq!(driver.completed(&mut p,Ok(inspected(&task,true)),now).progress,Progress::Accepted);assert!(!p.ready_to_abort());
    assert!(p.stage_abort(&driver,&i.table,&i.controller,0).is_err());
    finish_all_abort(&mut p,&mut i);assert!(p.ready_to_abort());assert_eq!(p.current.len(),2);
}

#[test]fn p10b_preparing_abort_stage_keeps_live_guards_and_native_wire_until_full_host_publication_commit(){
    let now=Instant::now();let mut i=input(now);
    for s in &mut i.table.sessions{
        let revision=s.ammo_service.as_ref().unwrap().revision();let pool=s.hangar.as_ref().unwrap().p04m_binding().cloned();
        s.ammo_service=Some(ammo_session::State::new(crate::ammo_service091::Metadata{revision,wire_revision:4},true));
        s.ammo_service.as_mut().unwrap().replace_pool(pool).unwrap_err();
        // Restore research-enabled state with the same authored warm wire4.
        s.ammo_service=Some(ammo_session::State::new(crate::ammo_service091::Metadata{revision,wire_revision:4},true).with_transfer(true).with_cross_vehicle(true)
            .with_roster_recruitment(true).with_progression(true).with_dismissal(true).with_barracks(true).with_research(true));
        s.ammo_service.as_mut().unwrap().replace_pool(s.hangar.as_ref().unwrap().p04m_binding().cloned()).unwrap();
    }
    let mut p=begin(&mut i);admitted(&mut p,&mut i);admitted(&mut p,&mut i);p.abort();finish_all_abort(&mut p,&mut i);
    let before=state(&i.table);let controller=i.controller.clone();let stage=p.stage_abort(&Driver::default(),&i.table,&i.controller,0).unwrap();
    assert_eq!(state(&i.table),before);assert_eq!(i.controller,controller);
    assert!(i.table.sessions.iter().all(|s|owned_state(s).unwrap().in_flight));
    for s in &stage.sessions{assert!(!owned_state(s).unwrap().in_flight);assert_eq!(s.ammo_service.as_ref().unwrap().wire_revision(),4);assert!(!owned_state(s).unwrap().has_reservation());}
    assert!(stage.batch.ready.is_empty()&&stage.batch.prepare.is_empty());assert!(!stage.batch.bodies.is_empty());
}

#[test]fn p10b_preparing_changed_account_generation_refuses_new_context_without_consuming_counter(){
    let now=Instant::now();let mut i=input(now);let mut p=begin(&mut i);i.table.sessions[1].shared.as_mut().unwrap().return_generation+=1;
    let before=state(&i.table);assert!(p.next_task(&mut i.table,true).is_err());assert_eq!(state(&i.table),before);assert!(p.saga.retry().is_none());
}

#[test]fn p10b_preparing_wrong_completion_cannot_clear_guard_or_advance_saga(){
    let now=Instant::now();let mut i=input(now);let mut p=begin(&mut i);let task=p.next_task(&mut i.table,true).unwrap().unwrap();
    for poison in 0..3{let mut c=completion(&task,&i.sql,true);match poison{0=>c.session+=1,1=>c.context.command_key.push_str("-late"),2=>c.fresh.as_mut().unwrap().binding.revision+=1,_=>unreachable!()}
        let before=state(&i.table);assert!(p.accept(&c).is_err());assert_eq!(state(&i.table),before);assert!(p.held.is_empty());assert_eq!(p.saga.retry().unwrap().context(),task.context());}
}
