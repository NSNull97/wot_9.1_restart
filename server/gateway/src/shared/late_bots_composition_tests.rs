//! LATE-BOTS release-only composition: real HTTP/SQLite and actual writer
//! completion, synthetic Session/ACK and an authored shortened lifecycle clock.
//! This is not a native client, UDP or Jolt gameplay test.
use super::*;
use super::p08c_late_composition_tests as common;
use super::super::{geometry,terrain,lifecycle,late_results_runtime};
use std::{path::PathBuf,process::{Command,Stdio},time::{Duration,Instant}};
use sha2::{Digest,Sha256};

fn receive(s:&mut Session,raw:&[u8]){let frame=Frame{flags:0x458,sequence:Some(s.rx),cumulative:Some(s.tx.cumulative),selective:vec![],
    body:[vec![1],s.token.to_le_bytes().to_vec(),raw.to_vec()].concat(),piggybacks:vec![]};assert!(!s.receive(&frame,Instant::now()).unwrap());}
fn settle(dispatch:&mut profile13_dispatch::Dispatcher,table:&mut Table,world:&World,config:Arc<crate::identity091::Config>){
    dispatch.start(table,world,config.clone(),Instant::now()).unwrap();assert!(dispatch.busy());let deadline=Instant::now()+Duration::from_secs(40);
    while dispatch.busy(){assert!(Instant::now()<deadline);dispatch.poll(table,config.clone(),Instant::now()).unwrap();std::thread::sleep(Duration::from_millis(10));}
}
fn utc()->u32{std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs().try_into().unwrap()}
fn phase(v:&serde_json::Value)->serde_json::Value{
    let config=Arc::new(crate::identity091::Config::load(v["config"].as_str().unwrap()).unwrap());
    assert!(config.late_bots&&config.p08c_late_results);let users=v["users"].as_array().unwrap();assert_eq!(users.len(),2);
    let arena=v["arena_id"].as_str().unwrap().parse::<u64>().unwrap();
    if v["phase"]=="reopen"{
        assert!(config.p08c_late_notice_experimental);let s=common::session(&config,&users[0],7);let mut table=Table{sessions:vec![s],..Table::default()};
        common::barrier(v,"after-reopen-auth",serde_json::json!({"run":config.battle_run_id,"actual_login":true}));
        let mut late=late_results_runtime::Manager::new(config.p08c_late_results_accounts.clone(),true).unwrap();late.enable_bots();
        let deadline=Instant::now()+Duration::from_secs(40);let mut notice=false;
        while !notice{assert!(Instant::now()<deadline);late.poll(&mut table.sessions,config.clone(),Instant::now(),true,utc());
            for body in common::drain(&mut table.sessions[0]){notice|=body.starts_with(&[0x13,0x4b]);}std::thread::sleep(Duration::from_millis(10));}
        receive(&mut table.sessions[0],&common::sync(601,1500,arena as i64));let mut queries=super::super::results_session::Manager::default();
        common::results(&mut table,&mut queries,config.clone());let expected=super::super::lifecycle_wire::Results::from_json_p06t(v["expected_results_json"].as_str().unwrap()).unwrap();
        assert_eq!(table.sessions[0].battle_results.cached().unwrap().as_ref(),&expected);common::drain(&mut table.sessions[0]);
        receive(&mut table.sessions[0],&common::sync(202,1501,arena as i64));common::results(&mut table,&mut queries,config.clone());
        assert!(common::drain(&mut table.sessions[0]).is_empty());return serde_json::json!({"phase":"reopen","run":config.battle_run_id,"notice_candidate":notice,"query_1500":true,"ack_1501":true,"native":"NOT_RUN"});
    }
    assert_eq!(v["phase"],"battle");assert!(!config.p08c_late_notice_experimental);
    let now=Instant::now();let mut world=World::new_for_roster(arena,now,crate::map_profile091::MapId::Karelia,4).unwrap();
    world.bind_geometry(Arc::new(geometry::tests::bundle())).unwrap();world.bind_geometry(Arc::new(geometry::tests::is7_bundle())).unwrap();world.enable_ap_test_lab().unwrap();
    world.bind_terrain(Arc::new(terrain::tests::fixture(-1000.,2000.,2,vec![-100.;4]))).unwrap();world.enable_mixed_ammo().unwrap();
    world.enable_lifecycle(lifecycle::Rules{prebattle_ms:1000,battle_ms:1000,afterbattle_ms:1000,..lifecycle::Rules::prohorovka()}).unwrap();world.enable_ammo_detonation().unwrap();
    world.enable_bots(config.bots.clone().unwrap()).unwrap();
    let template=BattleTemplate::new(&world,&None);let mut runtime=None;let mut table=Table{sessions:vec![common::session(&config,&users[0],7)],..Table::default()};
    let mut dispatch=profile13_dispatch::Dispatcher::default();let mut late=late_results_runtime::Manager::new(config.p08c_late_results_accounts.clone(),false).unwrap();late.enable_bots();dispatch.late=Some(late);
    let mut join=common::sync(202,700,1);join[15..19].copy_from_slice(&1i32.to_le_bytes());receive(&mut table.sessions[0],&join);
    settle(&mut dispatch,&mut table,&world,config.clone());assert!(table.sessions[0].shared.as_ref().unwrap().profile13.as_ref().unwrap().reservation_loss.is_some());
    assert!(common::drain(&mut table.sessions[0]).contains(&crate::map_drive_world091::queue_callback(true)));
    attach_waiting_sessions(&mut table,&mut world,Instant::now()).unwrap();assert_eq!(world.actors.len(),1);dispatch.late.as_mut().unwrap().register_world(&table.sessions,&world,&config.battle_run_id).unwrap();
    assert_eq!(world.fill_bots().unwrap(),3);let s=&mut table.sessions[0];s.arena_base=true;let c=s.shared.as_mut().unwrap();c.phase=Phase::Driving;c.correction=true;c.binding=Some((0,true));c.return_generation=1;c.view=Some(world.clone());
    world.lifecycle_created_unix=Some(utc());world.start(now).unwrap();world.set_ready(0,7).unwrap();assert_eq!(world.ready_bots().unwrap(),3);
    world.advance_lifecycle(now).unwrap();world.advance_lifecycle(now+Duration::from_millis(1000)).unwrap();
    profile13_dispatch::Dispatcher::terminal(&mut table.sessions[0],&world,crate::battle091::profile13::FinishReason::ManualLeave).unwrap();
    dispatch.late.as_mut().unwrap().observe_sessions(table.sessions.iter());world.detach(7).unwrap();settle(&mut dispatch,&mut table,&world,config.clone());common::warm(&mut table.sessions[0]);
    assert!(dispatch.late.as_ref().unwrap().holds_bot_battle(&world));assert!(!parked_battle_reset_ready_with_hold(&table,&world,true));
    world.advance_lifecycle(now+Duration::from_millis(1500)).unwrap();world.advance_lifecycle(now+Duration::from_millis(2100)).unwrap();
    assert_eq!(world.lifecycle.as_ref().unwrap().outcome().unwrap().reason,lifecycle::Reason::Timeout);
    dispatch.late.as_mut().unwrap().seal_world(&world);let result=dispatch.late.as_ref().unwrap().sealed_results(arena).unwrap();
    assert!(!dispatch.late.as_ref().unwrap().holds_bot_battle(&world));assert_eq!(result.participants.len(),4);assert!(result.participants[0].premature_leave);
    let result_json=super::super::late_results_capture::canonical(&serde_json::to_value(result.as_ref()).unwrap()).unwrap();
    dispatch.late.as_mut().unwrap().before_reset(&world,"late_bots_composition");template.replace(&mut world,&mut runtime,Instant::now()).unwrap();
    common::barrier(v,"after-finish",serde_json::json!({"run":config.battle_run_id,"arena_id":arena.to_string(),"results_json":result_json,"native":"NOT_RUN"}));
    let manager=dispatch.late.as_mut().unwrap();let deadline=Instant::now()+Duration::from_secs(50);
    loop{assert!(Instant::now()<deadline);manager.poll(&mut table.sessions,config.clone(),Instant::now(),true,utc());
        if !manager.worker_running(){break;}std::thread::sleep(Duration::from_millis(10));}
    let q=serde_json::json!({"version":1,"contract":"p08c-late-result-append.v1","operation":"pending","account_id":users[0]["account_id"],
        "native_database_id":table.sessions[0].identity.as_ref().unwrap().database_id,"command_key":"late:bots:verify","after_arena_id":null});
    let raw=config.late_results_pending_post(table.sessions[0].identity.as_ref().unwrap(),&serde_json::to_vec(&q).unwrap()).unwrap();
    let pending=crate::profile13_v2091::bounded_json(&raw,4096).unwrap();assert_eq!(pending["rows"].as_array().unwrap().len(),1);assert_eq!(pending["rows"][0]["arena_id"],arena.to_string());
    serde_json::json!({"phase":"battle","run":config.battle_run_id,"arena_id":arena.to_string(),"results_json":result_json,"real_admit":true,"real_finish":true,"actual_outcome":true,"native":"NOT_RUN"})
}
#[test]
#[ignore = "explicit release composition; requires local readonly source seed, bundle and original"]
fn late_bots_real_http_sqlite_release(){
    assert!(!cfg!(debug_assertions),"four-place World runs only in release");
    if let Some(input)=std::env::var_os("LATE_BOTS_COMPOSITION_CONTROL"){
        let output=PathBuf::from(std::env::var_os("LATE_BOTS_COMPOSITION_OUTPUT").unwrap());assert!(!output.exists());
        let raw=fs::read(input).unwrap();assert!(raw.len()<=65536);let value=crate::profile13_v2091::bounded_json(&raw,65536).unwrap();
        let keys=["schema","phase","config","users","barrier","arena_id","expected_results_json"];
        assert_eq!(value.as_object().unwrap().len(),keys.len());assert!(keys.iter().all(|k|value.get(*k).is_some()));assert_eq!(value["schema"],"late-bots-composition.v1");
        fs::write(output,serde_json::to_vec_pretty(&phase(&value)).unwrap()).unwrap();return;
    }
    let root=PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap();let executable=std::env::current_exe().unwrap().canonicalize().unwrap();
    assert_eq!(executable.parent().unwrap().file_name().unwrap(),"deps");assert_eq!(executable.parent().unwrap().parent().unwrap().file_name().unwrap(),"release");
    for(path,compiled) in [
        ("server/gateway/src/shared/late_bots_composition_tests.rs",include_bytes!("late_bots_composition_tests.rs").as_slice()),
        ("server/gateway/src/shared/server.rs",include_bytes!("server.rs").as_slice()),
        ("server/gateway/src/shared/p08c_late_composition_tests.rs",include_bytes!("p08c_late_composition_tests.rs").as_slice()),
        ("server/gateway/src/shared/late_results_capture.rs",include_bytes!("late_results_capture.rs").as_slice()),
        ("server/gateway/src/shared/late_results_runtime.rs",include_bytes!("late_results_runtime.rs").as_slice()),
        ("server/gateway/src/account/identity.rs",include_bytes!("../account/identity.rs").as_slice()),
        ("web/tests/helpers/late-bots-composition.mjs",include_bytes!("../../../../web/tests/helpers/late-bots-composition.mjs").as_slice()),
        ("web/tests/helpers/p08c-late-result-composition.mjs",include_bytes!("../../../../web/tests/helpers/p08c-late-result-composition.mjs").as_slice()),
        ("tests/helpers/late_bots_composition_seed.py",include_bytes!("../../../../tests/helpers/late_bots_composition_seed.py").as_slice())]{
        assert_eq!(Sha256::digest(fs::read(root.join(path)).unwrap()),Sha256::digest(compiled),"compiled source differs: {path}");
    }
    let out=Command::new("git").args(["status","--porcelain","--untracked-files=all","--","server","tools","client_patch","tests","web/src","web/tests"]).current_dir(&root).output().unwrap();assert!(out.status.success()&&out.stdout.is_empty(),"commit source before proof");
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();let base=root.join("local/test-runs/late-bots-composition");fs::create_dir_all(&base).unwrap();
    let output=base.join(format!("run-{}-{stamp}",std::process::id()));fs::create_dir(&output).unwrap();
    let stdout=fs::File::create(output.join("controller.stdout.log")).unwrap();let stderr=fs::File::create(output.join("controller.stderr.log")).unwrap();
    let exe_sha=format!("{:x}",Sha256::digest(fs::read(&executable).unwrap()));
    let mut cmd=Command::new("node");cmd.arg(root.join("web/tests/helpers/late-bots-composition.mjs")).arg(&executable).arg(&output)
        .arg(std::process::id().to_string()).arg(exe_sha).current_dir(&root).env_remove("PYTHONPATH").stdin(Stdio::null()).stdout(Stdio::from(stdout)).stderr(Stdio::from(stderr));
    #[cfg(windows)]{use std::os::windows::process::CommandExt;cmd.creation_flags(0x08000000);}
    assert!(cmd.status().unwrap().success(),"controller failed; see {}",output.display());
    let result:serde_json::Value=serde_json::from_slice(&fs::read(output.join("result.json")).unwrap()).unwrap();
    assert_eq!(result["status"],"PASS_ACTUAL_HTTP_SQLITE_SYNTHETIC_BOT_COMPOSITION");assert_eq!(result["native"],"NOT_RUN");println!("LATE_BOTS_COMPOSITION_PASS evidence={}",output.display());
}
