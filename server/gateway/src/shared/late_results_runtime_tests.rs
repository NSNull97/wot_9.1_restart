//! Meaningful observer/worker boundaries. Actual saved SQLite admission/finish
//! replies + source World adapter; HTTP/Fresh/native delivery NOT claimed.
use super::*;
use super::super::{late_results_capture as capture,model};
fn ready()->(Manager,World,Instant){let(capture,world,now)=capture::saved_sql_component_fixture();
    let owners=capture.links().iter().map(|l|l.owner().account_id.clone()).collect();let mut manager=Manager::new(owners,false).unwrap();
    let install=manager.stage_install(capture).unwrap();manager.commit_install(install);(manager,world,now)}
#[test]fn p08c_late_runtime_empty_world_loop_never_consumes_retained_capacity(){
    let now=Instant::now();let world=World::new(17,now).unwrap();let mut m=Manager::new(vec!["12345678-1234-4234-8234-123456789abc".into()],false).unwrap();
    for _ in 0..1024{m.register_world(&[],&world,"12345678-1234-4234-8234-123456789abc").unwrap();}assert!(m.captures.is_empty());assert!(m.registration_refused.is_empty());
}
#[test]fn p08c_late_runtime_actual_saved_finish_selects_read_stamp_not_another_finish(){
    let(mut m,world,_)=ready();let work=m.select_work().unwrap().unwrap();let v:serde_json::Value=serde_json::from_slice(work.task.body()).unwrap();
    assert_eq!(v["operation"],"release_stamp");assert_eq!(v["arena_id"],world.id.to_string());assert_eq!(v.as_object().unwrap().len(),13);
    assert!(v.get("terminal_hp").is_none());assert!(v.get("expected_revision").is_none());assert_eq!(world.actors[0].health,90);
}
#[test]fn p08c_late_runtime_not_configured_owner_is_terminal_local_refusal_not_http_retry(){
    let(mut m,world,_)=ready();m.accounts.clear();assert!(m.select_work().unwrap().is_none());
    assert!(matches!(&m.captures[0].owners[0],OwnerState::Rejected(code)if code=="LATE_RESULTS_DISABLED"));assert!(m.work.is_none());assert!(m.job.is_none());assert_eq!(world.actors[0].health,90);
}
#[test]fn p08c_late_runtime_spawn_failure_retains_identical_actual_source_request(){
    let(mut m,_world,now)=ready();m.work=m.select_work().unwrap();let old=m.work.as_ref().unwrap().task.body().to_vec();let hash=m.work.as_ref().unwrap().task.request_sha256().to_owned();
    for at in[now,now+Duration::from_secs(2)]{m.spawn_with(at,|_|Err(io::Error::new(io::ErrorKind::Other,"injected OS thread allocation refusal")));
        assert!(m.job.is_none());assert_eq!(m.work.as_ref().unwrap().task.body(),old);assert_eq!(m.work.as_ref().unwrap().task.request_sha256(),hash);assert_eq!(m.retry,Some(at+RETRY));}
}
#[test]fn p08c_late_runtime_worker_reply_is_not_consumed_before_real_thread_exit(){
    let(tx,rx)=mpsc::channel();let(release,wait)=mpsc::sync_channel(0);let(sent,received)=mpsc::sync_channel(0);
    let handle=thread::spawn(move||{tx.send(Ok(Reply::Rejected("RELEASE_NOT_READY".into()))).unwrap();sent.send(()).unwrap();wait.recv().unwrap();});
    received.recv().unwrap();let mut job=Job{rx,handle};assert!(job.poll().is_none());release.send(()).unwrap();
    let deadline=Instant::now()+Duration::from_secs(2);while !job.handle.is_finished(){assert!(Instant::now()<deadline);thread::yield_now();}
    assert!(matches!(job.poll().unwrap().unwrap(),Reply::Rejected(code)if code=="RELEASE_NOT_READY"));job.handle.join().unwrap();
}
#[test]fn p08c_late_runtime_retained_bound_cannot_evict_exact_ambiguous_worker_capture(){
    let(mut m,_world,_)=ready();m.work=m.select_work().unwrap();let protected=m.work.as_ref().unwrap().battle;m.captures[0].invalid=Some("known diagnostic while request still ambiguous".into());
    // AUTHORED registry-only pressure, no fabricated admitted/eligible owner.
    for id in 1..MAX_CAPTURES{m.captures.push(Entry::new(Capture::new("12345678-1234-4234-8234-123456789abc".into(),id as u64).unwrap()));}
    let new=||Capture::new("12345678-1234-4234-8234-123456789abc".into(),999).unwrap();assert!(m.stage_install(new()).is_err());assert_eq!(m.captures.len(),MAX_CAPTURES);
    m.captures.last_mut().unwrap().invalid=Some("abandoned unstarted authored book fixture".into());let install=m.stage_install(new()).unwrap();m.commit_install(install);
    assert_eq!(m.captures.len(),MAX_CAPTURES);assert!(m.captures.iter().any(|e|e.capture.battle()==protected));assert_eq!(m.work.as_ref().unwrap().battle,protected);
}
#[test]fn p08c_late_runtime_sealed_arc_survives_natural_detach_and_world_reset(){
    let(mut m,mut world,now)=ready();let old=m.sealed_results(world.id).unwrap();assert!(!old.participants[1].premature_leave);
    world.detach(2).unwrap();m.before_reset(&world,"normal_all_parked_reset");let after=m.sealed_results(world.id).unwrap();assert!(Arc::ptr_eq(&old,&after));assert_eq!(old,after);
    let battle=world.id;world=World::new(battle+1,now).unwrap();assert!(world.actors.is_empty());assert_eq!(m.sealed_results(battle).unwrap(),old);
}
#[test]fn p08c_late_runtime_failed_optional_observer_cannot_mutate_world_or_lose_other_capture(){
    let(mut m,world,_)=ready();let run=m.captures[0].capture.run().to_owned();let hp=world.actors.iter().map(|a|a.health).collect::<Vec<_>>();
    let capture=Capture::new("12345678-1234-4234-8234-123456789abc".into(),42).unwrap();let install=m.stage_install(capture).unwrap();m.commit_install(install);
    m.invalidate_source(&run,world.id);assert!(m.captures[0].invalid.is_some());assert!(m.captures[1].invalid.is_none());assert_eq!(world.actors.iter().map(|a|a.health).collect::<Vec<_>>(),hp);
    assert!(m.select_work().unwrap().is_none());assert_eq!(world.actors.len(),model::CAPACITY);
}
/// RES-30: an Entry (Capture + per-owner states) is cloned by value on the gateway main thread.
#[test]fn res30_late_entry_stays_small_on_the_stack(){
    assert!(std::mem::size_of::<Entry>()<=1024,"Entry {}",std::mem::size_of::<Entry>());
    assert!(std::mem::size_of::<Install>()<=1024,"Install {}",std::mem::size_of::<Install>());
}
/// RES-30: the late observer runs on the gateway main thread (Windows: 1MB).
/// Even the debug build's install/register/select path fits 256KiB now
/// (before the heap rows, register_world_inner alone took a 267KB debug frame).
/// Fixture World construction (pre-existing ~107KB frames) stays outside.
#[test]fn res30_late_manager_path_fits_a_quarter_megabyte_thread(){
    let(capture,world,_)=capture::saved_sql_component_fixture();let world=Box::new(world);let capture=Box::new(capture);
    thread::Builder::new().stack_size(256*1024).spawn(move||{
        let owners=capture.links().iter().map(|l|l.owner().account_id.clone()).collect();let mut m=Box::new(Manager::new(owners,false).unwrap());
        let install=m.stage_install(*capture).unwrap();m.commit_install(install);
        let sessions:[super::super::super::Session;0]=[];let _=m.register_world(&sessions,&world,"87654321-4321-4321-8321-cba987654321");
        assert!(m.select_work().unwrap().is_some());
    }).unwrap().join().unwrap();
}
