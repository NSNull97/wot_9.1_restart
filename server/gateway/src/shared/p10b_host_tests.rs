//! Actual Host/Table/Session/World boundary tests.
//! Reuse pinned ACTUAL Selection/Admit SQL DTOs unchanged. The pre-existing
//! launch fixture explicitly authors cache/Fresh/current-run seams; health,
//! elapsed time, queue pressure and failed-read descriptors here are AUTHORED
//! scheduler inputs, not claims of HTTP/native/combat compatibility.
use super::*;
use super::super::{p10b_launch_host::tests as launch_fixture,p10b_preparing_host::tests as prep_fixture};
use crate::gateway091::shared::profile13_session as persistence;
use crate::training091::{adapter,controller::Call,ingress,selection};
use sha2::{Digest,Sha256};

fn install_logins(table:&mut Table){
    for s in &mut table.sessions{
        s.login_attempt=Some(crate::gateway091::LoginAttempt::new(s.key,s.id,s.login_peer));
    }
}
fn accepted(host:&mut Host,origins:&BTreeMap<room::Account,launch::LaunchOrigin>){
    for(who,origin)in origins{
        host.bindings.insert(origin.selection().session(),origin.ready_task().profile().source_binding);
        host.ready.accepted.insert(*who,readiness::Accepted{task:origin.ready_task().clone(),selection:origin.selection().clone()});
    }
}
fn committed(now:Instant)->(Host,launch_fixture::Input,Option<IntegratedRuntime>){
    let mut input=launch_fixture::input(now);install_logins(&mut input.table);
    let staged=launch::stage_launch(&input.table,&input.controller,&input.world,&None,&input.template,
        &input.saga,&input.held,&input.origins,now,0).unwrap();
    let mut runtime=None;let event=staged.commit(&mut input.table,&mut input.controller,&mut input.world,&mut runtime);
    let mut host=Host{controller:input.controller.clone(),active:Some(Active{battle:event.battle,
        selected:event.awaiting_handoff,finished:Vec::new(),committed_at:now}),..Host::default()};
    for origin in input.origins.values(){host.bindings.insert(origin.selection().session(),origin.ready_task().profile().source_binding);}
    (host,input,runtime)
}
fn authored_current_outcomes(world:&mut World,now:Instant)->BTreeMap<u32,(i16,[u16;3])>{
    let mut expected=BTreeMap::new();
    for(slot,actor)in world.actors.iter_mut().enumerate(){
        // Exercise terminal capture against deliberately non-pristine server
        // state. This is not an authored hit or a fake writer result.
        actor.health=37+slot as i16;
        let outcomes=actor.fire.apply_typed(&[crate::p06t_armament091::Command::Shoot],now).unwrap();
        assert!(matches!(outcomes.as_slice(),[crate::battle091::fire::Outcome::Typed(crate::p06t_armament091::Outcome::Shot{..})]));
        expected.insert(actor.session.unwrap(),(actor.health,actor.fire.typed().unwrap().counts()));
    }expected
}
fn terminal(s:&Session)->&persistence::TerminalV2{
    s.shared.as_ref().unwrap().profile13.as_ref().unwrap().pending_return_v2.as_ref().unwrap()
}
fn assert_actual_terminal(s:&Session,expected:(i16,[u16;3]),battle:room::BattleKey){
    let t=terminal(s);assert_eq!(t.reason,crate::battle091::profile13::FinishReason::BattleFailure);
    assert_eq!(t.terminal_hp,expected.0);assert_eq!(t.remaining_ammunition.map(|a|a.count),expected.1);
    assert_eq!(t.reservation.battle,battle.0);assert_ne!(t.terminal_hp,t.reservation.frozen.max_hp);
    assert_ne!(expected.1,t.reservation.frozen.counts());assert!(t.results_json.is_none());
    assert!(matches!(t.request(),crate::profile13_v2091::Request::Finish{reason:crate::battle091::profile13::FinishReason::BattleFailure,..}));
}

#[test]fn p10b_host_committed_prestart_disconnect_freezes_ALL_actual_owned_and_retains_Active(){
    let now=Instant::now();let(host,mut input,mut runtime)=committed(now);let battle=host.active.as_ref().unwrap().battle;
    let expected=authored_current_outcomes(&mut input.world,now);let selected=host.active.as_ref().unwrap().selected.clone();
    let closed=selected[0];let mut host=Some(host);let mut dispatcher=profile13_dispatch::Dispatcher::default();
    assert!(retire_training_session(&mut host,&mut dispatcher,&mut input.table,&mut input.world,&mut runtime,
        &input.template,closed,"AUTHORED_prestart_disconnect",now,0).unwrap());
    let h=host.as_ref().unwrap();assert!(h.preparing.is_none());assert_eq!(h.active.as_ref().unwrap().selected,selected);
    assert!(h.active.as_ref().unwrap().finished.is_empty());assert_ne!(input.world.id,battle.0);
    assert!(input.world.actors.is_empty()&&input.world.started.is_none());assert!(runtime.is_none());
    assert_eq!(input.table.retirement.retained_count(),1);assert_eq!(input.table.sessions.len(),1);
    let survivor=&input.table.sessions[0];let removed=dispatcher.retired_for_test(closed).unwrap();
    for s in[survivor,removed]{
        assert_actual_terminal(s,expected[&s.id],battle);
        let who=readiness::account(&s.identity.as_ref().unwrap().account_id).unwrap();
        assert_eq!(h.controller.registry().claim(who),Some(room::Claim::Battle(battle)));
    }
    assert!(dispatcher.busy());assert!(h.prestart_failure(&input.world,None,now+Duration::from_secs(120)).is_none());
}

#[test]fn p10b_host_handoff_deadline_boundary_and_missing_actor_are_explicit_before_start(){
    let now=Instant::now();let(mut host,mut input,mut runtime)=committed(now);let battle=host.active.as_ref().unwrap().battle;
    assert!(host.prestart_failure(&input.world,None,now+HANDOFF_TIMEOUT-Duration::from_nanos(1)).is_none());
    let error=host.prestart_failure(&input.world,None,now+HANDOFF_TIMEOUT).unwrap();
    assert!(error.to_string().contains(HANDOFF_POLICY));assert!(error.to_string().contains("60 seconds"));
    let mut missing=input.world.clone();missing.actors.pop();
    assert!(host.prestart_failure(&missing,None,now).unwrap().to_string().contains("exact actor set"));
    let mut reordered=input.world.clone();reordered.actors.swap(0,1);
    assert!(host.prestart_failure(&reordered,None,now).is_some());
    let expected=authored_current_outcomes(&mut input.world,now);
    contain_battle_failure(&mut input.table,&mut input.world,&mut runtime,&input.template,now+HANDOFF_TIMEOUT,
        "AUTHORED_training_handoff_deadline",&error).unwrap();
    for s in &input.table.sessions{assert_actual_terminal(s,expected[&s.id],battle);}
    assert_eq!(host.active.as_ref().unwrap().battle,battle);assert!(host.active.as_ref().unwrap().finished.is_empty());
    assert!(host.prestart_failure(&input.world,None,now+HANDOFF_TIMEOUT).is_none());
    // A timeout itself creates no Finished receipt and releases no owner claim.
    for call in &input.calls{assert_eq!(host.controller.registry().claim(call.caller.account),Some(room::Claim::Battle(battle)));}
    host.prune_accepted();assert!(host.active.is_some());
}

fn preparing(now:Instant)->(Host,prep_fixture::Input){
    let mut input=prep_fixture::input(now);install_logins(&mut input.table);
    let mut host=Host{controller:input.controller.clone(),..Host::default()};accepted(&mut host,&input.origins);
    host.preparing=Some(prep_fixture::begin(&mut input));(host,input)
}
#[test]fn p10b_host_preparing_disconnect_records_one_real_retirement_and_keeps_claim_guards(){
    let now=Instant::now();let(mut host,mut input)=preparing(now);let id=input.table.sessions[0].id;
    assert!(host.closing(&mut input.table,id,now,0).unwrap());
    assert!(host.previously_retired(id)&&host.owns_preparing(id));assert_eq!(input.table.retirement.retained_count(),1);
    let s=input.table.sessions.iter().find(|s|s.id==id).unwrap();assert!(!s.active&&s.base_peer.is_none());
    assert!(s.shared.as_ref().unwrap().profile13.as_ref().unwrap().in_flight);
    let who=readiness::account(&s.identity.as_ref().unwrap().account_id).unwrap();
    assert!(matches!(host.controller.registry().claim(who),Some(room::Claim::Room(_))));
    assert!(host.preparing.as_ref().unwrap().saga().aborting());
    assert!(host.closing(&mut input.table,id,now+Duration::from_secs(1),1).unwrap());
    assert_eq!(input.table.retirement.retained_count(),1);assert!(host.previously_retired(id));
}

fn no_worker_config(input:&prep_fixture::Input)->Arc<crate::identity091::Config>{
    let root=input.table.sessions[0].identity.as_ref().unwrap().fixture_dir.canonicalize().unwrap();
    fs::write(root.join("host-test-token.txt"),"a".repeat(43)).unwrap();
    let value=serde_json::json!({"login_bind":"127.0.0.1:28101","base_bind":"127.0.0.1:28102","identity_endpoint":"127.0.0.1:28103",
        "identity_token_file":root.join("host-test-token.txt"),"local_root":root,"session_duration_seconds":600});
    let path=root.join("host-test-config.json");fs::write(&path,serde_json::to_vec(&value).unwrap()).unwrap();
    let config=crate::identity091::Config::load(path.to_str().unwrap()).unwrap();
    // Task.start structurally refuses this explicit configuration BEFORE any
    // worker/HTTP start. Host must still retain its allocated immutable Task.
    assert!(!config.profile13_battle&&!config.p06t_mixed_ammo);Arc::new(config)
}
#[test]fn p10b_host_queued_and_unpublished_readonly_errors_do_not_starve_immutable_preparing_task(){
    let now=Instant::now();let(mut host,mut input)=preparing(now);let config=no_worker_config(&input);
    let stale=host.ready.accepted.values().next().unwrap().task.clone();
    // AUTHORED queue-pressure descriptors, not a fabricated verified Selection.
    host.ready.enqueue(vec![stale.clone()]).unwrap();host.ready.completed_failure_for_test(stale);
    let read=deferred(&host,&input.table.sessions[0]);host.deferred.push(read);
    input.table.sessions[0].outbox=std::iter::repeat_n(vec![0x13,0x3b],128).collect();
    assert!(host.ready.busy()&&!host.ready.query_running());assert!(host.writer_idle(true));assert!(!host.writer_idle(false));
    let mut world=World::new_for_roster(9007199254740993,now,MapId::Prohorovka,6).unwrap();let template=BattleTemplate::new(&world,&None);
    let mut runtime=None;let mut dispatcher=profile13_dispatch::Dispatcher::default();
    assert!(!host.poll(&mut input.table,&mut world,&mut runtime,&template,&mut dispatcher,config,now,0,true).unwrap());
    let pending=host.preparing.as_ref().unwrap().saga().retry().expect("durable task allocation must not be starved by readonly publication error");
    assert!(matches!(pending.request(),crate::profile13_v2091::Request::Admit{..}));
    assert_eq!(input.table.sessions.iter().map(|s|s.shared.as_ref().unwrap().profile13.as_ref().unwrap().command_counter).sum::<u32>(),1);
    assert!(host.ready.busy()&&!host.ready.query_running());assert!(host.driver.known_status().is_none());
    assert_eq!(host.deferred.len(),1);assert_eq!(input.table.sessions[0].outbox.len(),128);
    for s in &input.table.sessions{let p=s.shared.as_ref().unwrap().profile13.as_ref().unwrap();assert!(p.in_flight&&!p.has_reservation()&&!p.has_pending_return());}
}

fn room_only(now:Instant)->(Host,launch_fixture::Input){
    let mut input=launch_fixture::input(now);let mut controller=Controller::default();let mut facts=BTreeMap::new();
    for s in &mut input.table.sessions{s.shared.as_mut().unwrap().profile13.as_mut().unwrap().in_flight=false;}
    for(call,s)in input.calls.iter().zip(&input.table.sessions){
        controller.bind(call.caller,call.channel,s.identity.as_ref().unwrap().name.clone(),s.identity.as_ref().unwrap().database_id,0).unwrap();
        facts.insert(call.caller.account,adapter::NativeFacts{database_id:s.identity.as_ref().unwrap().database_id,selected:None,descriptor:Vec::new(),igr_type:0,clan_database_id:0,clan_abbrev:String::new()});
    }
    controller.apply(input.calls[0],launch_fixture::create(),&facts,0).unwrap();let key=controller.registry().authenticated_room(input.calls[0].caller).unwrap();
    let native=controller.native_room(key).unwrap();controller.apply(input.calls[1],launch_fixture::native(202,400,i64::from(native),0),&facts,0).unwrap();
    let mut host=Host{controller,..Host::default()};
    for call in &input.calls{
        let selected=input.origins[&call.caller.account].selection().clone();
        host.bindings.insert(call.channel.session,call.profile.source_binding);
        let batch=host.controller.apply(*call,launch_fixture::native(223,402,1,0),&facts,0).unwrap();let task=batch.ready[0].clone();
        let fact=facts.get_mut(&call.caller.account).unwrap();fact.selected=Some(selected.reference().clone());fact.descriptor=selected.frozen().descriptor.clone();
        host.controller.complete_ready(&task,*call,1,selected.reference().clone(),&facts,0).unwrap();
        host.ready.accepted.insert(call.caller.account,readiness::Accepted{task,selection:selected});
    }(host,input)
}
#[test]fn p10b_host_committed_native_NotReady_prunes_exact_accepted_cache_only(){
    let now=Instant::now();let(mut host,mut input)=room_only(now);host.prune_accepted();assert_eq!(host.ready.accepted.len(),2);
    let call=input.calls[1];let s=input.table.sessions.iter().find(|s|s.id==call.channel.session).unwrap();
    let mut rpc=vec![0x8e,20,0];rpc.extend(226i16.to_le_bytes());rpc.extend(403i16.to_le_bytes());rpc.extend(1i64.to_le_bytes());rpc.extend([0;8]);
    let frame=Frame{flags:0x458,sequence:Some(s.rx),cumulative:Some(0),selective:Vec::new(),
        body:[vec![1],s.token.to_le_bytes().to_vec(),rpc].concat(),piggybacks:Vec::new()};
    let sid=s.id;assert!(!host.receive(&mut input.table,sid,&frame,&input.world,now,0).unwrap());
    assert!(!host.ready.accepted.contains_key(&call.caller.account));assert_eq!(host.ready.accepted.len(),1);
    let key=host.controller.registry().authenticated_room(call.caller).unwrap();
    assert!(host.controller.registry().room(key).unwrap().members().find(|m|m.account()==call.caller.account).unwrap().ready().is_none());
    assert!(host.ready.accepted.contains_key(&input.calls[0].caller.account));
}

fn listing()->ingress::Request{
    let mut raw=vec![0x97,28,0];raw.extend(200i16.to_le_bytes());raw.extend(520i16.to_le_bytes());
    for value in[5i32,2,7,0,0,50]{raw.extend(value.to_le_bytes());}ingress::record(&raw).unwrap().unwrap()
}
fn deferred(host:&Host,s:&Session)->receive::DeferredRead{
    let(call,_,_)=receive::bound_call(s,&host.bindings).unwrap();let request=listing();let read=flight::ReadRevision::Listing(host.controller.read_revision());
    let mut hash=Sha256::new();hash.update(receive::POLICY.as_bytes());hash.update([0]);hash.update(format!("{request:?}").as_bytes());
    let context=flight::StreamContext::capture(call.caller,flight::Channel{session:call.channel.session,generation:call.channel.generation},
        flight::Kind::Listing,hash.finalize().into(),read,call.profile.revision,call.profile.source_binding).unwrap();
    receive::DeferredRead{call,request,read,context}
}
fn transport_state(sessions:&[Session])->Vec<(u32,u32,VecDeque<Vec<u8>>,Option<flight::Flights>,u32,usize)>{
    sessions.iter().map(|s|{let mut tx=s.tx.clone();(s.id,s.rx,s.outbox.clone(),s.training_flights.clone(),tx.enqueue_body_tracked(b"AUTHORED_probe").unwrap(),s.tx.len())}).collect()
}
#[test]fn p10b_host_late_deferred_read_queue_failure_publishes_neither_stream_and_retries_once(){
    let now=Instant::now();let(mut host,mut input)=room_only(now);
    host.deferred=input.table.sessions.iter().map(|s|deferred(&host,s)).collect();
    // Valid bounded old outbox bytes, then the additional actual stream exceeds
    // the complete insertion budget. First recipient would otherwise succeed.
    input.table.sessions[1].outbox=std::iter::repeat_n(vec![0x13,0x3b],128).collect();
    let before=transport_state(&input.table.sessions);let controller=host.controller.clone();let descriptors=host.deferred.clone();
    assert!(host.flush_reads(&mut input.table,0).is_err());assert_eq!(transport_state(&input.table.sessions),before);assert_eq!(host.controller,controller);
    assert_eq!(host.deferred.len(),2);for(a,b)in host.deferred.iter().zip(&descriptors){assert_eq!(a.context,b.context);assert_eq!(a.call,b.call);}
    assert!(input.table.sessions.iter().all(|s|!s.training_flights.as_ref().unwrap().busy(flight::Kind::Listing)));
    input.table.sessions[1].outbox.clear();host.flush_reads(&mut input.table,0).unwrap();
    assert!(host.deferred.is_empty());assert!(input.table.sessions.iter().all(|s|s.training_flights.as_ref().unwrap().busy(flight::Kind::Listing)&&s.tx.len()>0));
}
