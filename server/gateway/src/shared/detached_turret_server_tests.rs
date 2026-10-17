//! Real server reset/result gates on an explicitly AUTHORED presentation fixture.
//! No SQL admission, original native client or swept-body physics is implied.
use super::*;
use super::super::{turret_publication_test_fixture as f,detached_turret as dt,lifecycle_wire::{Results,Participant}};
fn result(w:&World)->Arc<Results>{
    Arc::new(Results{arena_id:w.id,arena_type_id:4,created_unix:1792080000,winner_team:1,finish_reason:1,
        duration_seconds:10,interaction_details:None,participants:(0..2).map(|slot|Participant{
            vehicle_id:wire::vehicle_id(slot).unwrap(),account_dbid:w.actors[slot].identity.database,
            name:w.actors[slot].identity.name.clone(),team:slot as u8+1,type_compact_descr:3329,health:w.actors[slot].health,
            life_time:10,death_reason:if slot==1{0}else{-1},killer_id:if slot==1{wire::vehicle_id(0).unwrap()}else{0},
            shots:if slot==0{3}else{0},direct_hits:if slot==0{3}else{0},piercings:if slot==0{3}else{0},
            damage_dealt:if slot==0{90}else{0},damage_received:if slot==1{90}else{0},kills:if slot==0{1}else{0},..Default::default()
        }).collect()})
}
#[test]fn p06t_detonation_server_holds_old_world_until_avatar_handoff(){
    let now=Instant::now();let(s,mut w)=f::fixture(now);let mut table=Table::default();table.sessions.push(s);
    assert!(current_avatar_pending(&table,&w));assert!(w.ammo_detonations().is_empty());f::detonate(&mut w);
    for actor in &mut w.actors{actor.session=None;}
    assert!(current_avatar_pending(&table,&w));
    table.sessions[0].shared.as_mut().unwrap().phase=Phase::Leaving;assert!(current_avatar_pending(&table,&w));
    table.sessions[0].arena_base=false;table.sessions[0].shared.as_mut().unwrap().phase=Phase::Returning;
    assert!(!current_avatar_pending(&table,&w));
}
#[test]fn p06t_detonation_server_result_stream_waits_expiry_and_real_leave_ack(){
    let now=Instant::now();let(mut s,mut w)=f::fixture(now);f::detonate(&mut w);
    s.tx.enqueue_body(&dt::terminal_health(1,Some(0),0,dt::DeathKind::Detached).unwrap()).unwrap();f::ack_all(&mut s,now);
    s.shared.as_mut().unwrap().health_sent[1]=Some(0);s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();
    let mut req=vec![8,4,0];req.extend(dt::entity_id(1).unwrap().to_le_bytes());
    s.receive(&f::frame(&s,&req),now).unwrap();s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();f::ack_all(&mut s,now);
    let frozen=result(&w);let c=s.shared.as_mut().unwrap();c.phase=Phase::Leaving;c.natural_result=Some(frozen);c.result_committed=true;
    assert!(deliver_lifecycle_result(&mut s,&w,now).unwrap());assert!(!s.shared.as_ref().unwrap().result_stream_queued);
    let expired=now+Duration::from_secs(5);w.advance_turret_flights(expired).unwrap();
    s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();
    assert!(deliver_lifecycle_result(&mut s,&w,expired).unwrap());assert!(!s.shared.as_ref().unwrap().result_stream_queued);
    assert_eq!(f::send_pending(&mut s,expired),dt::leave(1).unwrap());f::ack_all(&mut s,expired);
    assert!(deliver_lifecycle_result(&mut s,&w,expired).unwrap());
    assert!(s.shared.as_ref().unwrap().result_stream_queued);assert!(s.battle_results.avatar_pending());
    assert_eq!(w.actors[1].health,0);assert_eq!(w.ammo_detonations().len(),1);
}

// AUTHORED Session/clock/completion boundary, real World lifecycle and native
// Window/parser. No HTTP writer, SQLite completion or original-client claim.
fn parked_forfeit(now:Instant)->(Table,World){
    use crate::profile13_loss091 as loss;
    use sha2::{Digest,Sha256};
    let(mut s,authored)=f::fixture(now);
    // Genuine pinned SQL admission DTO; only the peer, clock and completion
    // boundary are authored. Build the real typed terminal from attached state.
    let raw=include_bytes!("../../../../tests/fixtures/p06t-ammo-loss-queue-vectors.json");
    assert_eq!(format!("{:x}",Sha256::digest(raw)),"9c3d0ca15a66238b3e1f0991562c37a9c096cbd93e2261b67858489a2297d450");
    let rows:serde_json::Value=serde_json::from_slice(raw).unwrap();let row=&rows["vectors"][1];let request=&row["request"];
    let context=crate::battle091::profile13::Context{account_id:request["account_id"].as_str().unwrap().into(),
        native_database_id:request["native_database_id"].as_i64().unwrap()as i32,command_key:request["command_key"].as_str().unwrap().into(),
        expected_revision:request["expected_revision"].as_u64().unwrap(),run_id:request["run_id"].as_str().unwrap().into()};
    let battle=request["battle_id"].as_str().unwrap().rsplit(':').next().unwrap().parse().unwrap();
    let admit=loss::Request::Admit{battle,native_inventory_id:request["native_inventory_id"].as_u64().unwrap()as u32};
    let reply=loss::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&context,&admit).unwrap();let receipt=reply.reservation.unwrap();
    let mut w=World::new_for_roster(battle,now,crate::map_profile091::MapId::Karelia,2).unwrap();
    w.bind_geometry(Arc::new(super::super::geometry::tests::bundle())).unwrap();
    w.bind_geometry(Arc::new(super::super::geometry::tests::is7_bundle())).unwrap();w.enable_ap_test_lab().unwrap();
    w.bind_terrain(Arc::new(super::super::terrain::tests::fixture(-1000.,2000.,2,vec![0.;4]))).unwrap();w.enable_mixed_ammo().unwrap();
    w.enable_lifecycle(super::super::lifecycle::Rules::prohorovka()).unwrap();w.enable_ammo_detonation().unwrap();
    let who=model::Identity{account:context.account_id.clone(),database:context.native_database_id,name:"reset-regression-owner".into()};
    s.identity=Some(Arc::new(crate::identity091::Profile{account_id:who.account.clone(),database_id:who.database,name:who.name.clone(),fixture_dir:std::path::PathBuf::new()}));
    w.attach_owned_loss(who,s.id,&receipt.frozen).unwrap();w.actors.push(authored.actors[1].clone());
    w.start(now).unwrap();w.set_ready(0,s.id).unwrap();w.lifecycle_created_unix=Some(1792080000);
    let c=s.shared.as_mut().unwrap();let mut state=super::super::profile13_session::State::new(context.run_id,reply.revision).unwrap();
    state.reservation_loss=Some(receipt);c.profile13=Some(state);c.view=Some(w.clone());
    w.advance_lifecycle(now).unwrap();
    for second in 1..=30{w.advance_lifecycle(now+Duration::from_secs(second)).unwrap();}
    w.detach(2).unwrap();w.advance_lifecycle(now+Duration::from_millis(30_100)).unwrap();
    assert_eq!(w.lifecycle.as_ref().unwrap().outcome().unwrap().reason,super::super::lifecycle::Reason::Forfeit);
    s.shared.as_mut().unwrap().natural_result=Some(Arc::new(super::super::lifecycle_result::build(&w).unwrap()));
    profile13_dispatch::Dispatcher::terminal(&mut s,&w,crate::battle091::profile13::FinishReason::BattleFinished).unwrap();
    w.detach(s.id).unwrap();s.shared.as_mut().unwrap().view=Some(w.clone());
    assert!(s.shared.as_ref().unwrap().profile13.as_ref().unwrap().pending_return_loss.is_some());
    (Table{sessions:vec![s],..Table::default()},w)
}
fn commit_authored_result_boundary(s:&mut Session){
    let c=s.shared.as_mut().unwrap();let p=c.profile13.as_mut().unwrap();
    p.reservation_loss=None;p.pending_return_loss=None;c.result_committed=true;
}

#[test]fn stab01_no_detonation_parked_avatar_waits_uncommitted_result_and_real_confirmation(){
    let now=Instant::now();let(mut table,mut w)=parked_forfeit(now);let id=w.id;
    assert!(w.ammo_detonation_enabled());assert!(w.ammo_detonations().is_empty());
    assert!(w.actors.iter().all(|a|a.session.is_none()));
    // A delayed Finish is not a reason to destroy the Avatar's World. Several
    // loop turns, including beyond the afterbattle period, must still publish.
    for ms in [30_100,31_000,50_000]{
        assert!(!parked_battle_reset_ready(&table,&w));
        poll_battle_session(&mut table.sessions[0],&mut w,now+Duration::from_millis(ms),true,false).unwrap();
        f::ack_all(&mut table.sessions[0],now);
        assert_eq!(w.id,id);assert_eq!(w.actors.len(),2);
        assert!(!table.sessions[0].shared.as_ref().unwrap().result_stream_queued);
    }
    // This flag models only the existing Finished callback boundary. The test
    // makes no durable-writer claim; actual HTTP compositions cover that leaf.
    commit_authored_result_boundary(&mut table.sessions[0]);
    let at=now+Duration::from_secs(50);
    poll_battle_session(&mut table.sessions[0],&mut w,at,true,false).unwrap();
    assert!(table.sessions[0].battle_results.avatar_pending());
    assert!(!parked_battle_reset_ready(&table,&w));
    f::ack_all(&mut table.sessions[0],now);
    let s=&mut table.sessions[0];let frame=f::frame(s,&[0x99,1,0,0,0x87,0,0]);
    assert!(!s.receive(&frame,at+Duration::from_secs(1)).unwrap());
    assert!(s.battle_results.avatar_confirmed());
    poll_battle_session(s,&mut w,at+Duration::from_secs(1),true,false).unwrap();
    assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Returning);assert!(!s.arena_base);
    assert!(parked_battle_reset_ready(&table,&w));
    let mut runtime=None;let template=BattleTemplate::new(&World::new(id,now).unwrap(),&runtime);
    let mut resets=0;
    for turn in 0..3{
        if parked_battle_reset_ready(&table,&w){template.replace(&mut w,&mut runtime,at).unwrap();resets+=1;}
        poll_battle_session(&mut table.sessions[0],&mut w,at+Duration::from_secs(2+turn),true,false).unwrap();
    }
    assert_eq!(resets,1);assert_eq!(w.id,id+1);assert!(w.actors.is_empty());
    assert!(table.sessions[0].active);
}
#[test]fn stab01_avatar_reset_barrier_preserves_queue_cancel_and_old_battle_boundaries(){
    let now=Instant::now();let(s,mut w)=f::fixture(now);let mut table=Table{sessions:vec![s],..Table::default()};
    for actor in &mut w.actors{actor.session=None;}
    for phase in [Phase::Enable,Phase::Entities,Phase::Driving,Phase::Leaving]{
        table.sessions[0].shared.as_mut().unwrap().phase=phase;
        assert!(!parked_battle_reset_ready(&table,&w));
    }
    table.sessions[0].arena_base=false;table.sessions[0].shared.as_mut().unwrap().phase=Phase::Account;
    assert!(parked_battle_reset_ready(&table,&w),"queue cancellation has no native Avatar");
    table.sessions[0].shared.as_mut().unwrap().phase=Phase::Returning;
    assert!(parked_battle_reset_ready(&table,&w));
    table.sessions[0].arena_base=true;let c=table.sessions[0].shared.as_mut().unwrap();c.phase=Phase::Leaving;
    c.view.as_mut().unwrap().id+=1;
    assert!(!current_avatar_pending(&table,&w),"only this exact battle owns the barrier");
    w.actors.clear();assert!(!parked_battle_reset_ready(&table,&w),"empty replacement never resets again");
}
#[test]fn stab01_unconfirmed_normal_result_timeout_does_not_fake_reset_or_confirmation(){
    let now=Instant::now();let(mut table,w)=parked_forfeit(now);let s=&mut table.sessions[0];
    commit_authored_result_boundary(s);let at=now+Duration::from_secs(50);
    assert!(deliver_lifecycle_result(s,&w,at).unwrap());
    assert!(deliver_lifecycle_result(s,&w,at+Duration::from_millis(29_999)).unwrap());
    assert_eq!(deliver_lifecycle_result(s,&w,at+Duration::from_secs(30)).unwrap_err().kind(),io::ErrorKind::TimedOut);
    assert!(s.arena_base);assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Leaving);
    assert!(!s.battle_results.avatar_confirmed());assert!(s.drive_return_account.is_none());
    assert!(!parked_battle_reset_ready(&table,&w));
}

#[test]fn stab01_contained_turret_fault_times_out_without_inventing_expired_flight(){
    let now=Instant::now();let(mut s,mut w)=f::fixture(now);f::detonate(&mut w);let old=w.id;
    for actor in &mut w.actors{actor.session=None;}
    // AUTHORED already-committed boundary. The actual flight stays immutable;
    // containment promises bounded disconnect, not successful native FX/return.
    let frozen=result(&w);let c=s.shared.as_mut().unwrap();c.phase=Phase::Leaving;c.view=Some(w.clone());
    c.profile13=Some(super::super::profile13_session::State::new("12345678-1234-4234-8234-123456789abc".into(),13).unwrap());
    c.natural_result=Some(frozen);c.result_committed=true;
    let mut table=Table{sessions:vec![s],..Table::default()};let mut runtime=None;
    let template=BattleTemplate::new(&World::new(old,now).unwrap(),&runtime);
    contain_battle_failure(&mut table,&mut w,&mut runtime,&template,now,"publication",
        &io::Error::new(io::ErrorKind::InvalidData,"authored mid-flight fault")).unwrap();
    let s=&mut table.sessions[0];let error=poll_battle_session(s,&mut w,now+Duration::from_secs(20),true,false).unwrap_err();
    assert_eq!(error.kind(),io::ErrorKind::TimedOut);assert!(contained_return_failure_reason(s).is_some());
    let c=s.shared.as_ref().unwrap();assert!(!c.result_stream_queued);assert!(!s.battle_results.avatar_confirmed());
    assert!(s.drive_return_account.is_none());assert_eq!(w.id,old+1);
    assert_eq!(c.contained_world.as_ref().unwrap().turret_flights()[0].sample().phase,super::super::ammo_detonation::FlightPhase::Flying);
}
