//! Host03: actual Table/Session/Controller/Preparing boundaries.
//! Selected C/D reuse strict actual saved Selection/Frozen DTOs through the
//! existing labelled authored cache/current-run fixture seam. Bench5 is ONLY
//! authored authenticated metadata: no owned Selection/Ready/reservation.
//! Abort drain uses the existing explicitly retargeted strict reply helper,
//! not a claim that fresh SQLite writes or native UI were exercised here.
use super::*;
use super::super::{p10b_launch_host::tests as launch_fixture,p10b_preparing_host::tests as prep_fixture};
use crate::training091::{adapter,aliases,controller::Call};

struct Input{host:Host,preparation:prep_fixture::Input,world:World,template:BattleTemplate,calls:Vec<Call>}
fn input(now:Instant,creator_bench:bool)->Input{
    let mut launched=launch_fixture::input_mode(now,true);
    let calls=launched.calls.clone();assert_eq!(calls.len(),3);let creator=if creator_bench{2}else{0};
    let mut controller=Controller::default();let mut facts=BTreeMap::new();
    for(s,call)in launched.table.sessions.iter_mut().zip(&calls){
        s.login_attempt=Some(crate::gateway091::LoginAttempt::new(s.key,s.id,s.login_peer));
        s.shared.as_mut().unwrap().profile13.as_mut().unwrap().in_flight=false;
        controller.bind(call.caller,call.channel,s.identity.as_ref().unwrap().name.clone(),s.identity.as_ref().unwrap().database_id,0).unwrap();
        facts.insert(call.caller.account,adapter::NativeFacts{database_id:s.identity.as_ref().unwrap().database_id,
            selected:None,descriptor:Vec::new(),igr_type:0,clan_database_id:0,clan_abbrev:String::new()});
    }
    controller.apply(calls[creator],launch_fixture::create(),&facts,0).unwrap();
    let key=controller.registry().authenticated_room(calls[creator].caller).unwrap();let native=controller.native_room(key).unwrap();
    let peers=(0..3).filter(|i|*i!=creator).collect::<Vec<_>>();
    for i in &peers{controller.apply(calls[*i],launch_fixture::native(202,400,i64::from(native),0),&facts,0).unwrap();}
    if creator_bench{controller.apply(calls[creator],launch_fixture::native(226,404,i64::from(aliases::OWN_ENTITY_ID),17),&facts,0).unwrap();}
    for(index,team)in[(0,1),(1,2)]{
        let alias=if index==creator{aliases::OWN_ENTITY_ID}else{aliases::OWN_ENTITY_ID+1+peers.iter().position(|i|*i==index).unwrap()as u32};
        controller.apply(calls[creator],launch_fixture::native(227+index as i16,404,i64::from(alias),team),&facts,0).unwrap();
    }
    let mut origins=BTreeMap::new();let mut accepted=BTreeMap::new();
    for index in 0..2{
        let call=calls[index];let selected=launched.origins[&call.caller.account].selection().clone();
        let batch=controller.apply(call,launch_fixture::native(223,402,1,0),&facts,0).unwrap();let task=batch.ready[0].clone();
        let fact=facts.get_mut(&call.caller.account).unwrap();fact.selected=Some(selected.reference().clone());fact.descriptor=selected.loadout().descriptor.clone();
        controller.complete_ready(&task,call,1,selected.reference().clone(),&facts,0).unwrap();
        let s=launched.table.sessions.iter().find(|s|s.id==call.channel.session).unwrap();
        origins.insert(call.caller.account,launch::LaunchOrigin::capture(s,&controller,task.clone(),selected.clone()).unwrap());
        accepted.insert(call.caller.account,readiness::Accepted{task,selection:selected});
    }
    controller.apply(calls[creator],launch_fixture::native(224,411,1,0),&facts,0).unwrap();
    let batch=controller.apply(calls[creator],launch_fixture::native(225,411,2,0),&facts,0).unwrap();
    let mut host=Host{controller:controller.clone(),..Host::default()};host.ready.accepted=accepted;
    for call in &calls{host.bindings.insert(call.channel.session,call.profile.source_binding);}
    let mut preparation=prep_fixture::Input{table:launched.table,controller,prepare:batch.prepare[0].clone(),origins,
        sql:prep_fixture::input(now).sql};
    host.preparing=Some(prep_fixture::begin(&mut preparation));
    assert_eq!(host.preparing.as_ref().unwrap().origins().len(),2);
    assert!(!host.preparing.as_ref().unwrap().owns(calls[2].channel.session));
    Input{host,preparation,world:launched.world,template:launched.template,calls}
}
fn bench(input:&Input)->&Session{input.preparation.table.sessions.iter().find(|s|s.id==input.calls[2].channel.session).unwrap()}
fn assert_bench_has_no_writer_claim(s:&Session){
    let p=s.shared.as_ref().unwrap().profile13.as_ref().unwrap();
    assert!(!p.in_flight&&!p.has_reservation()&&!p.has_pending_return()&&p.selection.is_none());assert_eq!(p.command_counter,0);
}
fn config(input:&Input)->Arc<crate::identity091::Config>{
    let root=bench(input).identity.as_ref().unwrap().fixture_dir.canonicalize().unwrap();
    fs::write(root.join("host-bench-token.txt"),"a".repeat(43)).unwrap();
    let raw=serde_json::json!({"login_bind":"127.0.0.1:28201","base_bind":"127.0.0.1:28202","identity_endpoint":"127.0.0.1:28203",
        "identity_token_file":root.join("host-bench-token.txt"),"local_root":root,"session_duration_seconds":600});
    let path=root.join("host-bench-config.json");fs::write(&path,serde_json::to_vec(&raw).unwrap()).unwrap();
    let mut config=crate::identity091::Config::load(path.to_str().unwrap()).unwrap();
    // AUTHORED room scheduler mode, no actual writer/HTTP capability granted.
    config.training_rooms=true;Arc::new(config)
}
fn drain_abort(input:&mut Input,now:Instant){
    let config=config(input);
    prep_fixture::finish_all_abort(input.host.preparing.as_mut().unwrap(),&mut input.preparation);
    let released=input.host.preparing.as_ref().unwrap().saga().released_refs().unwrap();assert_eq!(released.len(),2);
    assert!(input.host.preparing.as_ref().unwrap().saga().snapshot().members().iter().all(|m|m.account()!=input.calls[2].caller.account));
    let mut dispatcher=profile13_dispatch::Dispatcher::default();let mut runtime=None;
    let previous=input.world.id;
    assert!(input.host.poll(&mut input.preparation.table,&mut input.world,&mut runtime,&input.template,&mut dispatcher,config,now,0,true).unwrap());
    assert_ne!(input.world.id,previous,"compensated scopes must not reuse a settled writer battle key");
    assert_eq!(input.world.scene_version(),0);assert!(input.world.impact.events().is_empty());
    assert!(input.host.preparing.is_none()&&input.host.active.is_none());assert!(input.world.actors.is_empty()&&input.world.started.is_none());
}

#[test]fn p10b_host03_selected_then_bench_close_retains_both_facts_until_two_selected_releases(){
    let now=Instant::now();let mut i=input(now,false);let selected=i.calls[1].channel.session;let bench_id=i.calls[2].channel.session;
    assert!(i.host.closing(&mut i.preparation.table,selected,now,0).unwrap());
    assert!(i.host.closing(&mut i.preparation.table,bench_id,now,0).unwrap());
    assert!(i.host.owns_preparing(selected)&&i.host.owns_preparing(bench_id));assert_eq!(i.host.closed_members.len(),2);
    assert_eq!(i.preparation.table.retirement.retained_count(),2);assert!(i.host.preparing.as_ref().unwrap().saga().aborting());
    assert_bench_has_no_writer_claim(bench(&i));assert!(!bench(&i).active&&bench(&i).base_peer.is_none());
    let facts=i.host.current_facts(&i.preparation.table.sessions,&i.host.controller).unwrap();
    assert_eq!(facts.len(),3);assert!(facts[&i.calls[2].caller.account].selected.is_none());
    assert!(i.host.closed_members[&i.calls[2].caller.account].display_task.is_none());
    assert_eq!(i.host.preparing.as_ref().unwrap().saga().snapshot().members().len(),2);
    drain_abort(&mut i,now);
    assert!(i.host.controller.registry().claim(i.calls[1].caller.account).is_none());
    assert!(i.host.controller.registry().claim(i.calls[2].caller.account).is_none());
    let key=i.preparation.prepare.snapshot().room();
    assert_eq!(i.host.controller.registry().claim(i.calls[0].caller.account),Some(room::Claim::Room(key)));
    let remaining=i.host.controller.registry().room(key).unwrap().members().map(|m|m.account()).collect::<Vec<_>>();
    assert_eq!(remaining,vec![i.calls[0].caller.account]);
    assert_bench_has_no_writer_claim(bench(&i));assert!(!i.host.owns_preparing(bench_id));
    let mut host=Some(i.host);let mut runtime=None;let mut dispatcher=profile13_dispatch::Dispatcher::default();
    assert!(retire_training_session(&mut host,&mut dispatcher,&mut i.preparation.table,&mut i.world,&mut runtime,&i.template,bench_id,"AUTHORED_bench_cleanup",now,0).unwrap());
    assert_eq!(i.preparation.table.retirement.retained_count(),2);assert!(!i.preparation.table.sessions.iter().any(|s|s.id==bench_id));
    assert!(!host.as_ref().unwrap().previously_retired(bench_id));assert_eq!(host.as_ref().unwrap().closed_members.len(),1);
}

#[test]fn p10b_host03_bench_creator_disconnect_aborts_and_closes_room_without_third_writer_receipt(){
    let now=Instant::now();let mut i=input(now,true);let bench_id=i.calls[2].channel.session;
    let key=i.host.preparing.as_ref().unwrap().prepare().snapshot().room();
    assert_eq!(i.host.controller.registry().room(key).unwrap().creator(),i.calls[2].caller.account);
    assert!(i.host.closing(&mut i.preparation.table,bench_id,now,0).unwrap());
    assert!(i.host.preparing.as_ref().unwrap().saga().aborting());assert!(i.host.owns_preparing(bench_id));
    assert_eq!(i.preparation.table.retirement.retained_count(),1);assert_bench_has_no_writer_claim(bench(&i));
    assert!(i.host.current_facts(&i.preparation.table.sessions,&i.host.controller).is_ok());
    drain_abort(&mut i,now);
    assert!(i.host.controller.registry().room(key).is_none());
    for call in &i.calls{assert!(i.host.controller.registry().claim(call.caller.account).is_none());}
    assert_bench_has_no_writer_claim(bench(&i));
    assert!(i.preparation.table.sessions.iter().filter(|s|s.id!=bench_id).all(|s|s.active&&s.shared.as_ref().unwrap().profile13.as_ref().unwrap().garage_idle()));
}

#[test]fn p10b_host03_late_bench_fact_failure_still_aborts_without_partial_retire_or_fake_guard(){
    let now=Instant::now();let mut i=input(now,false);let bench_id=i.calls[2].channel.session;
    i.preparation.table.sessions.iter_mut().find(|s|s.id==bench_id).unwrap().shared.as_mut().unwrap().profile13.as_mut().unwrap().selection=Some(1);
    let controller=i.host.controller.clone();let before=i.preparation.table.sessions.iter().map(|s|(s.id,s.active,s.base_peer,s.shared.as_ref().unwrap().profile13.as_ref().unwrap().clone())).collect::<Vec<_>>();
    assert!(i.host.closing(&mut i.preparation.table,bench_id,now,0).is_err());
    assert!(i.host.preparing.as_ref().unwrap().saga().aborting());assert_eq!(i.host.controller,controller);
    assert_eq!(i.preparation.table.sessions.iter().map(|s|(s.id,s.active,s.base_peer,s.shared.as_ref().unwrap().profile13.as_ref().unwrap().clone())).collect::<Vec<_>>(),before);
    assert!(i.host.closed_members.is_empty()&&i.host.retired_closed.is_empty());assert_eq!(i.preparation.table.retirement.retained_count(),0);
}

#[path="p10b_service_retirement_tests.rs"]mod service_retirement_tests;
