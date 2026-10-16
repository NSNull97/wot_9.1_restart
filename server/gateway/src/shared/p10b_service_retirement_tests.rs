//! Child of p10b_host_bench_tests: reuses labelled source SQL/authored scheduler
//! seams. These are retirement-routing tests, not HTTP/native proof.
use super::*;

#[test]fn p10b_host03_service_garage_failure_keeps_room_bench_and_immediate_abort_instead_of_direct_remove(){
    let now=Instant::now();let mut i=input(now,false);let id=i.calls[2].channel.session;let who=i.calls[2].caller.account;
    let key=i.host.preparing.as_ref().unwrap().prepare().snapshot().room();
    let mut host=Some(i.host);let mut runtime=None;let mut dispatcher=profile13_dispatch::Dispatcher::default();let mut pending=Vec::new();
    retire_service_failure(&mut host,&mut dispatcher,&mut i.preparation.table,&mut i.world,&mut runtime,&i.template,
        &mut pending,id,"garage_writer_ambiguous",now,0).unwrap();
    let h=host.as_ref().unwrap();assert!(h.preparing.as_ref().unwrap().saga().aborting());assert!(h.owns_preparing(id));
    assert_eq!(h.controller.registry().claim(who),Some(room::Claim::Room(key)));assert!(h.closed_members.contains_key(&who));
    let held=i.preparation.table.sessions.iter().find(|s|s.id==id).unwrap();assert!(!held.active&&held.base_peer.is_none());assert_bench_has_no_writer_claim(held);
    assert_eq!(pending,vec![(id,"garage_writer_ambiguous")]);assert_eq!(i.preparation.table.retirement.retained_count(),1);
    retire_service_failure(&mut host,&mut dispatcher,&mut i.preparation.table,&mut i.world,&mut runtime,&i.template,
        &mut pending,id,"later_duplicate_reason",now+Duration::from_secs(1),1).unwrap();
    assert_eq!(pending,vec![(id,"garage_writer_ambiguous")]);assert_eq!(i.preparation.table.retirement.retained_count(),1);
    assert!(!dispatcher.busy());
}

#[test]fn p10b_host03_service_results_validation_failure_routes_actual_pending1500_through_Host(){
    let now=Instant::now();let mut i=input(now,true);let id=i.calls[2].channel.session;let who=i.calls[2].caller.account;
    let s=i.preparation.table.sessions.iter_mut().find(|s|s.id==id).unwrap();
    let mut raw=vec![0x8e,20,0];raw.extend(221i16.to_le_bytes());raw.extend(1500i16.to_le_bytes());raw.extend(91i64.to_le_bytes());raw.extend([0;8]);
    assert!(s.battle_results.stage(&raw).unwrap());assert!(!s.battle_results.idle());
    let manager=crate::gateway091::shared::results_session::Manager::default();assert_eq!(manager.failure_session(&i.preparation.table.sessions),Some(id));
    let mut host=Some(i.host);let mut runtime=None;let mut dispatcher=profile13_dispatch::Dispatcher::default();let mut pending=Vec::new();
    contain_results_failure_with_training(&manager,&mut host,&mut dispatcher,&mut i.preparation.table,&mut i.world,&mut runtime,
        &i.template,&mut pending,now,0,&io::Error::new(io::ErrorKind::InvalidData,"AUTHORED result validation/native delivery failure")).unwrap();
    let h=host.as_ref().unwrap();assert!(h.preparing.as_ref().unwrap().saga().aborting());assert!(h.closed_members.contains_key(&who));
    assert!(i.preparation.table.sessions.iter().any(|s|s.id==id&&!s.active));assert_eq!(pending,vec![(id,"native_results_delivery")]);
    assert_eq!(i.preparation.table.retirement.retained_count(),1);assert!(!dispatcher.busy());
}

#[test]fn p10b_host03_service_failed_close_keeps_retry_reason_and_safety_abort_without_forgetting_registry(){
    let now=Instant::now();let mut i=input(now,false);let id=i.calls[2].channel.session;let who=i.calls[2].caller.account;
    i.preparation.table.sessions.iter_mut().find(|s|s.id==id).unwrap().shared.as_mut().unwrap().profile13.as_mut().unwrap().selection=Some(1);
    let controller=i.host.controller.clone();let mut host=Some(i.host);let mut runtime=None;let mut dispatcher=profile13_dispatch::Dispatcher::default();let mut pending=Vec::new();
    retire_service_failure(&mut host,&mut dispatcher,&mut i.preparation.table,&mut i.world,&mut runtime,&i.template,
        &mut pending,id,"garage_writer_ambiguous",now,0).unwrap();
    let h=host.as_ref().unwrap();assert_eq!(h.controller,controller);assert!(h.preparing.as_ref().unwrap().saga().aborting());
    assert!(h.controller.registry().claim(who).is_some());assert!(h.bindings.contains_key(&id));assert!(h.closed_members.is_empty());
    assert!(i.preparation.table.sessions.iter().any(|s|s.id==id&&s.active));assert_eq!(i.preparation.table.retirement.retained_count(),0);
    assert_eq!(pending,vec![(id,"garage_writer_ambiguous")]);
    for _ in 0..64{hold_training_close(&mut pending,id,"duplicate");}assert_eq!(pending.len(),1);
}

#[test]fn p10b_host03_service_legacy_mode_keeps_direct_retirement_without_room_queue(){
    let now=Instant::now();let mut i=input(now,false);let id=i.calls[2].channel.session;let mut host=None;
    let mut runtime=None;let mut dispatcher=profile13_dispatch::Dispatcher::default();let mut pending=Vec::new();
    retire_service_failure(&mut host,&mut dispatcher,&mut i.preparation.table,&mut i.world,&mut runtime,&i.template,
        &mut pending,id,"legacy_garage_failure",now,0).unwrap();
    assert!(!i.preparation.table.sessions.iter().any(|s|s.id==id));assert!(pending.is_empty());assert_eq!(i.preparation.table.retirement.retained_count(),1);
}
