//! Actual private HTTP/SQLite/JobLoss/Dispatcher/Manager composition. Synthetic
//! native Session/ACKs and authored flat terrain/ready/lifecycle clock/Forfeit.
//! No authored HP/death/DamageRecord/Finished proof and no native/UDP/Jolt claim.
use super::*;
use crate::{identity091,hangar091,ammo_service091,transport091};
use sha2::{Digest,Sha256};use std::path::PathBuf;
use super::super::{late_results_runtime,lifecycle_wire::Results,geometry,terrain,lifecycle};
pub(super) fn sync(id:i16,command:i16,value:i64)->Vec<u8>{let mut out=vec![0x8e,20,0];out.extend(id.to_le_bytes());out.extend(command.to_le_bytes());out.extend(value.to_le_bytes());out.extend([0;8]);out}
fn receive(s:&mut Session,raw:&[u8]){let frame=Frame{flags:0x458,sequence:Some(s.rx),cumulative:Some(s.tx.cumulative),selective:vec![],
    body:[vec![1],s.token.to_le_bytes().to_vec(),raw.to_vec()].concat(),piggybacks:vec![]};assert!(!s.receive(&frame,Instant::now()).unwrap());}
pub(super) fn drain(s:&mut Session)->Vec<Vec<u8>>{let mut out=Vec::new();let mut rounds=0;
    while !s.outbox.is_empty()||s.tx.len()!=0{rounds+=1;assert!(rounds<=128,"bounded synthetic native ACK drain");s.drain_outbox().unwrap();let mut ack=s.tx.cumulative;
        while let Some((seq,_,raw))=s.tx.due(Instant::now()+Duration::from_secs(1),s.rx).unwrap(){ack=ack.max(seq+1);out.push(transport091::parse_interactive(&raw).unwrap().body);}
        let frame=Frame{flags:0x408,sequence:None,cumulative:Some(ack),selective:vec![],body:vec![],piggybacks:vec![]};assert!(!s.receive(&frame,Instant::now()).unwrap());
    }out}
pub(super) fn session(config:&identity091::Config,user:&serde_json::Value,id:u32)->Session{
    assert!(config.p04m_pool&&config.p06t_ammo_rack_detonation&&config.p08c_late_results&&config.p06t_mixed_ammo&&config.visibility_v1);
    let owner=Arc::new(config.authenticate(user["email"].as_str().unwrap(),user["password"].as_str().unwrap()).unwrap().expect("actual isolated own login"));
    assert_eq!(owner.account_id,user["account_id"]);let fixtures=Arc::new(hangar091::Fixtures::load_p04m(&owner.fixture_dir).unwrap());
    let binding=ammo_service091::metadata_research(&owner.fixture_dir,&owner.account_id,owner.database_id).unwrap();let now=Instant::now();
    let mut s=Session::new(id,[id as u8;16],format!("127.0.0.1:{}",41800+id).parse().unwrap(),now);
    s.active=true;s.account_ready=true;s.sync_mask=7;s.rx=1;s.tx=Window::interactive();s.base_peer=Some(format!("127.0.0.1:{}",41900+id).parse().unwrap());
    s.login_attempt=Some(LoginAttempt::new(s.key,s.id,s.login_peer));s.identity=Some(owner);s.hangar=Some(fixtures);
    s.ammo_service=Some(ammo_session::State::new(binding,config.crew_service).with_transfer(config.crew_transfer).with_cross_vehicle(config.crew_cross_vehicle)
        .with_roster_recruitment(config.crew_roster_recruitment).with_progression(config.crew_progression).with_dismissal(config.crew_dismissal)
        .with_barracks(config.crew_barracks_recruitment).with_research(config.research_service));
    s.ammo_service.as_mut().unwrap().replace_pool(s.hangar.as_ref().and_then(|f|f.p04m_binding()).cloned()).unwrap();
    let mut c=Client::new(0);c.enable_spotting().unwrap();c.join_requested=false;c.hangar_since=Some(now-Duration::from_secs(3));
    c.profile13=Some(super::super::profile13_session::State::new(config.battle_run_id.clone(),binding.revision).unwrap());s.shared=Some(c);s
}
fn settle(dispatch:&mut profile13_dispatch::Dispatcher,table:&mut Table,world:&World,config:Arc<identity091::Config>){
    dispatch.start(table,world,config.clone(),Instant::now()).unwrap();assert!(dispatch.busy(),"real JobLoss must start");let deadline=Instant::now()+Duration::from_secs(40);
    while dispatch.busy(){assert!(Instant::now()<deadline,"real writer completion bounded");dispatch.poll(table,config.clone(),Instant::now()).unwrap();std::thread::sleep(Duration::from_millis(10));}
}
pub(super) fn results(table:&mut Table,manager:&mut super::super::results_session::Manager,config:Arc<identity091::Config>){
    manager.start_if_idle(&mut table.sessions,config.clone(),Instant::now()).unwrap();assert!(manager.busy());let deadline=Instant::now()+Duration::from_secs(40);
    while manager.busy(){assert!(Instant::now()<deadline);manager.poll(&mut table.sessions,Instant::now()).unwrap();manager.start_if_idle(&mut table.sessions,config.clone(),Instant::now()).unwrap();std::thread::sleep(Duration::from_millis(10));}
}
pub(super) fn warm(s:&mut Session){assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Returning);drain(s);receive(s,&[9]);drain(s);
    let cursor=s.shared.as_ref().unwrap().return_source_revision;let fixtures=s.hangar.as_ref().unwrap().clone();receive(s,&sync(501,100,cursor));drain(s);
    let mut tail=sync(502,300,fixtures.shop_sync_revision().unwrap());tail.extend(sync(503,600,0));receive(s,&tail);drain(s);
    assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Account);assert!(s.shared.as_ref().unwrap().profile13_garage_idle());
}
pub(super) fn barrier(value:&serde_json::Value,phase:&str,summary:serde_json::Value){let root=PathBuf::from(value["barrier"].as_str().unwrap());
    let marker=root.join(format!("{phase}.ready.json"));assert!(!marker.exists());fs::write(marker,serde_json::to_vec_pretty(&summary).unwrap()).unwrap();let go=root.join(format!("{phase}.go"));
    let deadline=Instant::now()+Duration::from_secs(40);while !go.is_file(){assert!(Instant::now()<deadline,"controller read-only SQL barrier timed out");std::thread::sleep(Duration::from_millis(10));}
}
fn world(battle:u64,now:Instant)->World{let mut w=World::new_for_roster(battle,now,crate::map_profile091::MapId::Karelia,2).unwrap();
    w.bind_geometry(Arc::new(geometry::tests::bundle())).unwrap();w.bind_geometry(Arc::new(geometry::tests::is7_bundle())).unwrap();w.enable_ap_test_lab().unwrap();
    w.bind_terrain(Arc::new(terrain::tests::fixture(-1000.,2000.,2,vec![-100.;4]))).unwrap();w.enable_mixed_ammo().unwrap();
    w.enable_lifecycle(lifecycle::Rules{prebattle_ms:1000,battle_ms:60000,afterbattle_ms:1000,..lifecycle::Rules::prohorovka()}).unwrap();w.enable_ammo_detonation().unwrap();w
}
fn phase(value:&serde_json::Value)->serde_json::Value{
    let config=Arc::new(identity091::Config::load(value["config"].as_str().unwrap()).unwrap());let users=value["users"].as_array().unwrap();assert_eq!(users.len(),2);
    let arena=value["arena_id"].as_str().unwrap().parse::<u64>().unwrap();let utc=||u32::try_from(std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs()).unwrap();
    if value["phase"]=="discover_query_ack"{
        assert!(config.p08c_late_notice_experimental);let s=session(&config,&users[0],7);let mut table=Table{sessions:vec![s],..Table::default()};
        barrier(value,"after-reopen-auth",serde_json::json!({"run":config.battle_run_id,"phase":"after-reopen-auth","actual_login":true}));
        let mut manager=late_results_runtime::Manager::new(config.p08c_late_results_accounts.clone(),true).unwrap();let deadline=Instant::now()+Duration::from_secs(40);let mut notice=false;
        while !notice{assert!(Instant::now()<deadline,"committed pending discovery must survive empty gateway memory");manager.poll(&mut table.sessions,config.clone(),Instant::now(),true,utc());
            for body in drain(&mut table.sessions[0]){notice|=body.starts_with(&[0x13,0x4b]);}std::thread::sleep(Duration::from_millis(10));}
        let s=&mut table.sessions[0];assert!(s.battle_results.idle(),"notice/transport ACK must not create durable1501");receive(s,&sync(601,1500,arena as i64));
        let mut queries=super::super::results_session::Manager::default();results(&mut table,&mut queries,config.clone());let s=&mut table.sessions[0];let expected=Results::from_json_p06t(value["expected_results_json"].as_str().unwrap()).unwrap();
        assert_eq!(s.battle_results.cached().unwrap().as_ref(),&expected);let bodies=drain(s);assert!(bodies.iter().any(|b|b.starts_with(&[0x13,0x4d])));
        receive(s,&sync(202,1501,arena as i64));results(&mut table,&mut queries,config.clone());assert!(drain(&mut table.sessions[0]).is_empty());
        return serde_json::json!({"phase":"discover_query_ack","run":config.battle_run_id,"arena_id":arena.to_string(),"source_run_id":value["source_run_id"],
            "notice_experimental_source_static":notice,"native_client":"NOT_RUN","query_matches_actual_final_world":true,"real1501":true});
    }
    assert_eq!(value["phase"],"manual_then_natural_append");assert!(!config.p08c_late_notice_experimental);
    let a=session(&config,&users[0],7);let b=session(&config,&users[1],8);let now=Instant::now();let mut world=world(arena,now);let template=BattleTemplate::new(&world,&None);let mut runtime=None;
    let mut table=Table{sessions:vec![a,b],..Table::default()};let mut dispatch=profile13_dispatch::Dispatcher::default();
    dispatch.late=Some(late_results_runtime::Manager::new(config.p08c_late_results_accounts.clone(),false).unwrap());
    for s in &mut table.sessions{let mut join=sync(202,700,1);join[15..19].copy_from_slice(&1i32.to_le_bytes());receive(s,&join);}
    for _ in 0..2{settle(&mut dispatch,&mut table,&world,config.clone());}
    for s in &mut table.sessions{let p=s.shared.as_ref().unwrap().profile13.as_ref().unwrap();assert!(p.reservation_loss.is_some());assert!(drain(s).contains(&crate::map_drive_world091::queue_callback(true)));}
    attach_waiting_sessions(&mut table,&mut world,now).unwrap();dispatch.late.as_mut().unwrap().register_world(&table.sessions,&world,&config.battle_run_id).unwrap();
    assert_eq!(world.actors.len(),2);for(slot,s)in table.sessions.iter_mut().enumerate(){assert_eq!(world.actors[slot].session,Some(s.id));s.arena_base=true;
        let c=s.shared.as_mut().unwrap();c.phase=Phase::Driving;c.correction=true;c.binding=Some((0,true));c.return_generation=1;c.view=Some(world.clone());}
    world.lifecycle_created_unix=Some(utc());world.start(now).unwrap();for(slot,s)in table.sessions.iter().enumerate(){world.set_ready(slot,s.id).unwrap();}
    world.advance_lifecycle(now).unwrap();world.advance_lifecycle(now+Duration::from_millis(1000)).unwrap();
    profile13_dispatch::Dispatcher::terminal(&mut table.sessions[0],&world,crate::battle091::profile13::FinishReason::ManualLeave).unwrap();world.detach(table.sessions[0].id).unwrap();
    settle(&mut dispatch,&mut table,&world,config.clone());warm(&mut table.sessions[0]);
    assert_eq!(world.actors[0].health,90);assert!(world.damage_events.is_empty());assert!(world.shots.is_empty());
    world.advance_lifecycle(now+Duration::from_millis(1100)).unwrap();assert_eq!(world.lifecycle.as_ref().unwrap().outcome().unwrap().winner,2);
    dispatch.late.as_mut().unwrap().seal_world(&world);let final_result=dispatch.late.as_ref().unwrap().sealed_results(arena).expect("actual final seal");
    assert!(final_result.participants[0].premature_leave);assert!(!final_result.participants[1].premature_leave);
    stage_lifecycle_results_from(&mut table,&world,Some(final_result.clone())).unwrap();assert!(Arc::ptr_eq(table.sessions[1].shared.as_ref().unwrap().natural_result.as_ref().unwrap(),&final_result));
    world.advance_lifecycle(now+Duration::from_millis(2100)).unwrap();profile13_dispatch::Dispatcher::terminal(&mut table.sessions[1],&world,crate::battle091::profile13::FinishReason::BattleFinished).unwrap();
    world.detach(table.sessions[1].id).unwrap();dispatch.late.as_mut().unwrap().before_reset(&world,"composition_actual_before_reset");template.replace(&mut world,&mut runtime,Instant::now()).unwrap();assert_ne!(world.id,arena);
    settle(&mut dispatch,&mut table,&world,config.clone());let s=&mut table.sessions[1];assert!(s.shared.as_ref().unwrap().result_committed);
    assert!(deliver_lifecycle_result(s,&world,Instant::now()).unwrap());drain(s);receive(s,&[0x99,1,0,0,0x87,0,0]);assert!(s.battle_results.avatar_confirmed());
    assert!(deliver_lifecycle_result(s,&world,Instant::now()).unwrap());warm(s);let mut queries=super::super::results_session::Manager::default();results(&mut table,&mut queries,config.clone());
    for s in &mut table.sessions{drain(s);assert!(s.shared.as_ref().unwrap().profile13.as_ref().unwrap().garage_idle());}
    let result_json=super::super::late_results_capture::canonical(&serde_json::to_value(final_result.as_ref()).unwrap()).unwrap();
    barrier(value,"after-finish",serde_json::json!({"phase":"after-finish","run":config.battle_run_id,"arena_id":arena.to_string(),"results_json":result_json,
        "actual_manual_and_natural_finish":true,"world_reset":true,"native_client":"NOT_RUN"}));
    let manager=dispatch.late.as_mut().unwrap();manager.poll(&mut table.sessions,config.clone(),Instant::now(),true,utc());assert!(manager.worker_running());let deadline=Instant::now()+Duration::from_secs(50);
    while manager.worker_running(){assert!(Instant::now()<deadline,"actual late stamp/append bounded");manager.poll(&mut table.sessions,config.clone(),Instant::now(),true,utc());std::thread::sleep(Duration::from_millis(10));}
    let q=serde_json::json!({"version":1,"contract":"p08c-late-result-append.v1","operation":"pending","account_id":users[0]["account_id"],
        "native_database_id":table.sessions[0].identity.as_ref().unwrap().database_id,"command_key":"late:composition:verify","after_arena_id":null});
    let raw=config.late_results_pending_post(table.sessions[0].identity.as_ref().unwrap(),&serde_json::to_vec(&q).unwrap()).unwrap();let pending=crate::profile13_v2091::bounded_json(&raw,4096).unwrap();assert_eq!(pending["rows"].as_array().unwrap().len(),1);assert_eq!(pending["rows"][0]["arena_id"],arena.to_string());
    serde_json::json!({"phase":"manual_then_natural_append","run":config.battle_run_id,"arena_id":arena.to_string(),"results_json":result_json,
        "real_job_admissions":2,"real_job_finishes":2,"actual_seal_before_reset":true,"natural_result_same_arc":true,"actual_pending":pending,
        "authored_control":"synthetic Session/ACK; flat terrain; ready and Forfeit clock","native_client":"NOT_RUN"})
}

fn plain(path:&std::path::Path)->PathBuf{
    use std::path::Component;
    assert!(path.is_absolute(),"absolute owned path required");
    let mut cursor=PathBuf::new();
    for part in path.components(){
        assert!(!matches!(part,Component::ParentDir|Component::CurDir),"noncanonical lexical path");
        cursor.push(part.as_os_str());
        if matches!(part,Component::Normal(_)){
            let metadata=fs::symlink_metadata(&cursor).unwrap();assert!(!metadata.file_type().is_symlink(),"linked path refused");
            #[cfg(windows)]{use std::os::windows::fs::MetadataExt;assert_eq!(metadata.file_attributes()&0x400,0,"reparse path refused");}
        }
    }
    path.canonicalize().unwrap()
}
fn bounded_record(path:&std::path::Path)->serde_json::Value{
    let path=plain(path);let raw=fs::read(path).unwrap();assert!(raw.len()<=16384);
    crate::profile13_v2091::bounded_json(&raw,16384).unwrap()
}
fn record_ref(path:&std::path::Path)->serde_json::Value{
    let path=plain(path);serde_json::json!({"path":path,"sha256":format!("{:x}",Sha256::digest(fs::read(&path).unwrap()))})
}
fn allocation(root:&std::path::Path,target:&std::path::Path)->(PathBuf,serde_json::Value){
    let build=plain(&root.join("local/build"));
    if target.starts_with(&build){
        assert_eq!(target.file_name().unwrap(),"target");let output=plain(target.parent().unwrap());assert_ne!(output,build);
        assert!(!output.join("cargo-temp-target.json").exists(),"normal target cannot impersonate temporary allocation");
        return (output,serde_json::Value::Null);
    }
    let os_temp=plain(&std::env::temp_dir());assert_eq!(target.parent().unwrap(),os_temp);
    assert!(target.file_name().unwrap().to_str().unwrap().starts_with("wot091-cargo-"));
    let origin_path=target.join("wot091-build-origin.json");let origin=bounded_record(&origin_path);
    assert_eq!(origin.as_object().unwrap().len(),8);assert_eq!(origin["schema"],"wot091-cargo-temp-target.v1");
    let output=plain(&PathBuf::from(origin["output"].as_str().unwrap()));assert!(output.starts_with(&build)&&output!=build);
    #[cfg(windows)]{
        assert_ne!(os_temp.components().next().unwrap().as_os_str().to_string_lossy().to_lowercase(),
            output.components().next().unwrap().as_os_str().to_string_lossy().to_lowercase(),"temporary allocation must be on another drive");
    }
    let metadata_path=output.join("cargo-temp-target.json");let metadata=bounded_record(&metadata_path);
    assert_eq!(metadata.as_object().unwrap().len(),7);let mut without_output=origin.clone();without_output.as_object_mut().unwrap().remove("output");
    assert_eq!(metadata,without_output);assert_eq!(plain(&PathBuf::from(metadata["target"].as_str().unwrap())),target);
    assert_eq!(plain(&PathBuf::from(metadata["default_os_temp"].as_str().unwrap())),os_temp);
    assert_eq!(metadata["retained_for_audit"],true);assert_eq!(metadata["automatic_delete"],false);
    assert_eq!(metadata["source"],"tempfile.gettempdir(); fresh mkdtemp; no caller path");
    assert!(!metadata["created_utc"].as_str().unwrap().is_empty());
    let environment_path=output.join("cargo-temp-environment.json");let environment=bounded_record(&environment_path);
    let allowed=["CARGO_HOME","RUSTUP_HOME","CARGO_TARGET_DIR","CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER","RUSTFLAGS","CARGO_INCREMENTAL","RUST_TEST_THREADS","CARGO_PROFILE_DEV_DEBUG","CARGO_PROFILE_TEST_DEBUG"];
    assert!(environment.as_object().unwrap().keys().all(|key|allowed.contains(&key.as_str())));
    assert_eq!(plain(&PathBuf::from(environment["CARGO_TARGET_DIR"].as_str().unwrap())),target);
    for (key,value) in environment.as_object().unwrap(){assert_eq!(std::env::var(key).unwrap(),value.as_str().unwrap(),"recorded Cargo environment differs");}
    (output,serde_json::json!({"origin":record_ref(&origin_path),"metadata":record_ref(&metadata_path),"environment":record_ref(&environment_path)}))
}

fn parent(){
    use std::{collections::BTreeMap,process::{Command,Stdio}};
    let root=PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap();
    let test_source="server/gateway/src/shared/p08c_late_composition_tests.rs";
    let helper="web/tests/helpers/p08c-late-result-composition.mjs";
    let compiled_test=format!("{:x}",Sha256::digest(include_bytes!("p08c_late_composition_tests.rs")));
    let compiled_helper=format!("{:x}",Sha256::digest(include_bytes!("../../../../web/tests/helpers/p08c-late-result-composition.mjs")));
    assert_eq!(format!("{:x}",Sha256::digest(fs::read(root.join(test_source)).unwrap())),compiled_test);
    assert_eq!(format!("{:x}",Sha256::digest(fs::read(root.join(helper)).unwrap())),compiled_helper);
    let executable=plain(&std::env::current_exe().unwrap());
    let target=plain(&PathBuf::from(std::env::var_os("CARGO_TARGET_DIR").expect("recorded canonical Cargo target required")));
    assert_eq!(executable.parent().unwrap(),target.join("debug/deps"));
    let name=executable.file_name().unwrap().to_str().unwrap();
    assert!(name.starts_with("sr_gateway-")&&name.ends_with(".exe"),"same canonical gateway test artifact required");
    let (output_root,allocation)=allocation(&root,&target);
    let git=|args:&[&str]|{let out=Command::new("git").args(args).current_dir(&root).output().unwrap();assert!(out.status.success());out.stdout};
    let head=String::from_utf8(git(&["rev-parse","HEAD"])).unwrap().trim().to_owned();
    let scopes=["server","tools","client_patch","web/src","tests","web/tests"];
    let mut status=vec!["status","--porcelain","--untracked-files=all","--"];status.extend(scopes);assert!(git(&status).is_empty());
    let mut args=vec!["ls-files","-z","--"];args.extend(scopes);let names=git(&args);
    let mut files=BTreeMap::new();for raw in names.split(|b|*b==0).filter(|s|!s.is_empty()){
        let name=std::str::from_utf8(raw).unwrap().to_owned();let path=root.join(&name).canonicalize().unwrap();assert!(path.starts_with(&root));
        files.insert(name,format!("{:x}",Sha256::digest(fs::read(path).unwrap())));
    }
    let base=root.join("local/test-runs/p08c-late-composition05");fs::create_dir_all(&base).unwrap();
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let output=base.join(format!("run-{}-{stamp}",std::process::id()));fs::create_dir(&output).unwrap();
    let guard=serde_json::json!({"schema":"p08c-late-result-parent-in-progress.v1","full_gate":"PENDING_PARENT_FULL_GATE",
        "head":head,"files":files,"parent_pid":std::process::id(),"target_dir":target,"build_output":output_root,"allocation":allocation,
        "compiled_test_source_sha256":compiled_test,"compiled_driver_sha256":compiled_helper,
        "test_executable":{"path":executable,"sha256":format!("{:x}",Sha256::digest(fs::read(&executable).unwrap()))},
        "test_name":"gateway091::shared::server::p08c_late_composition_tests::p08c_late_result_runtime05_real_http_phase"});
    let control=output.join("parent-control.json");fs::write(&control,serde_json::to_vec_pretty(&guard).unwrap()).unwrap();
    let bundle=std::env::var_os("P04D_TEST_BUNDLE").map(PathBuf::from).unwrap_or_else(||root.join("local/stands/p09e-main-01/source-bundle-05"));
    let original=std::env::var_os("P04D_TEST_ORIGINAL").map(PathBuf::from).unwrap_or_else(||PathBuf::from("C:/WoT_0.9.1_RU_0717_original"));
    assert!(bundle.is_dir()&&original.is_dir(),"actual source prerequisites missing; no skip");
    let stdout=fs::File::create(output.join("controller.stdout.log")).unwrap();let stderr=fs::File::create(output.join("controller.stderr.log")).unwrap();
    let mut child=Command::new("node");child.arg(root.join(helper)).arg("--parent-full").arg(&control).arg(&output).arg(bundle).arg(original).arg(root.join("local/evidence/20261016-p06t-owned01/seed01/seed.json"))
        .current_dir(&root).env_remove("PYTHONPATH").stdin(Stdio::null()).stdout(Stdio::from(stdout)).stderr(Stdio::from(stderr));
    #[cfg(windows)]{use std::os::windows::process::CommandExt;child.creation_flags(0x08000000);}
    let mut child=child.spawn().unwrap();let status=child.wait().unwrap();assert!(status.success(),"composition controller failed; retained {}",output.display());
    let result:serde_json::Value=serde_json::from_slice(&fs::read(output.join("result.json"))
        .expect("controller exited successfully but actual composition result is absent")).unwrap();
    assert_eq!(result["status"],"PASS_ACTUAL_LATE_HTTP_SQLITE_SYNTHETIC_SESSION_COMPOSITION");
    assert_eq!(result["parent_full_gate"],"PENDING_PARENT_FULL_GATE");assert_eq!(result["native_client"],"NOT_RUN");
    println!("P08C_LATE_COMPOSITION_ACTUAL_PASS evidence={} native=NOT_RUN full_gate=PENDING_PARENT_FULL_GATE",output.display());
}

#[test]
fn p08c_late_result_runtime05_real_http_phase(){
    if std::env::var_os("P08C_LATE_COMPOSITION_CONTROL").is_none(){parent();return;}
    let input=PathBuf::from(std::env::var_os("P08C_LATE_COMPOSITION_CONTROL").unwrap());
    let output=PathBuf::from(std::env::var_os("P08C_LATE_COMPOSITION_OUTPUT").unwrap());
    assert!(!output.exists());let raw=fs::read(input).unwrap();assert!(raw.len()<=65536);
    let value=crate::profile13_v2091::bounded_json(&raw,65536).unwrap();
    let keys=["schema","phase","config","users","barrier","arena_id","expected_results_json","source_run_id"];
    assert_eq!(value.as_object().unwrap().len(),keys.len());assert!(keys.iter().all(|k|value.get(*k).is_some()));
    assert_eq!(value["schema"],"p08c-late-result-composition.v1");
    let result=phase(&value);fs::write(output,serde_json::to_vec_pretty(&result).unwrap()).unwrap();
}
