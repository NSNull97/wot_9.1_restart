//! Opt-in composition test. Actual HTTP/Python/SQLite/Job/Dispatcher, synthetic
//! authenticated Session/ACKs and authored terminalHP0. No native/UDP/physics claim.
//! Intended as cfg(test) child of shared/server.rs. Regular parent starts this SAME
//! compiled test executable twice, preserving SQLite and restarting the bridge.
use super::*;
use crate::{identity091,hangar091,ammo_service091,transport091};
use sha2::{Digest,Sha256};
use std::path::PathBuf;

fn sync(id:i16,command:i16,rev:i64)->Vec<u8>{
    let mut b=vec![0x8e,20,0];b.extend(id.to_le_bytes());b.extend(command.to_le_bytes());
    b.extend(rev.to_le_bytes());b.extend([0;8]);b
}
fn receive(s:&mut Session,payload:&[u8]){
    let f=Frame{flags:0x458,sequence:Some(s.rx),cumulative:Some(s.tx.cumulative),selective:vec![],
        body:[vec![1],s.token.to_le_bytes().to_vec(),payload.to_vec()].concat(),piggybacks:vec![]};
    assert!(!s.receive(&f,Instant::now()).unwrap());
}
fn drain(s:&mut Session)->Vec<Vec<u8>>{
    let mut bodies=Vec::new();let mut rounds=0;
    while !s.outbox.is_empty()||s.tx.len()!=0{
        rounds+=1;assert!(rounds<=128,"bounded native queue drain");s.drain_outbox().unwrap();
        let mut ack=s.tx.cumulative;
        while let Some((seq,_,raw))=s.tx.due(Instant::now()+Duration::from_secs(1),s.rx).unwrap(){
            ack=ack.max(seq+1);bodies.push(transport091::parse_interactive(&raw).unwrap().body);
        }
        let f=Frame{flags:0x408,sequence:None,cumulative:Some(ack),selective:vec![],body:vec![],piggybacks:vec![]};
        assert!(!s.receive(&f,Instant::now()).unwrap());
    }bodies
}
fn session(config:&identity091::Config,email:&str,password:&str)->Session{
    assert!(config.profile13_battle&&config.research_service&&!config.p04m_pool&&!config.p06t_mixed_ammo&&!config.p06t_ammo_rack_detonation);
    // Authentication includes production run_open and exact projection checks.
    let owner=Arc::new(config.authenticate(email,password).unwrap().expect("own isolated credentials"));
    let fixtures=Arc::new(hangar091::Fixtures::load_research(&owner.fixture_dir).unwrap());
    let binding=ammo_service091::metadata_research(&owner.fixture_dir,&owner.account_id,owner.database_id).unwrap();
    assert_eq!(binding.wire_revision,1);let now=Instant::now();
    let mut s=Session::new(7,[7;16],"127.0.0.1:41707".parse().unwrap(),now);
    s.active=true;s.account_ready=true;s.sync_mask=7;s.rx=1;s.tx=Window::interactive();
    s.base_peer=Some("127.0.0.1:41708".parse().unwrap());s.identity=Some(owner);s.hangar=Some(fixtures);
    s.login_attempt=Some(LoginAttempt::new(s.key,s.id,s.login_peer));
    s.ammo_service=Some(ammo_session::State::new(binding,config.crew_service).with_transfer(config.crew_transfer)
        .with_cross_vehicle(config.crew_cross_vehicle).with_roster_recruitment(config.crew_roster_recruitment)
        .with_progression(config.crew_progression).with_dismissal(config.crew_dismissal).with_barracks(config.crew_barracks_recruitment)
        .with_research(config.research_service));
    let mut c=Client::new(0);c.join_requested=false;c.hangar_since=Some(now);
    c.profile13=Some(super::super::profile13_session::State::new(config.battle_run_id.clone(),binding.revision).unwrap());
    s.shared=Some(c);s
}
fn settle(d:&mut profile13_dispatch::Dispatcher,t:&mut Table,w:&World,config:Arc<identity091::Config>){
    d.start(t,w,config.clone(),Instant::now()).unwrap();assert!(d.busy(),"actual writer job must exist");
    let until=Instant::now()+Duration::from_secs(35);
    while d.busy(){assert!(Instant::now()<until,"bounded real writer completion");
        d.poll(t,config.clone(),Instant::now()).unwrap();std::thread::sleep(Duration::from_millis(10));}
}
fn reserve(t:&mut Table,w:&World,d:&mut profile13_dispatch::Dispatcher,config:Arc<identity091::Config>)->crate::battle091::profile13::Reservation{
    // Native Join's last INT32 is gameplays mask1, not a forged CAS revision.
    let mut join=sync(202,700,1);join[15..19].copy_from_slice(&1i32.to_le_bytes());receive(&mut t.sessions[0],&join);
    settle(d,t,w,config);let s=&mut t.sessions[0];
    let r=s.shared.as_ref().unwrap().profile13.as_ref().unwrap().reservation.clone().expect("actual admitted receipt");
    assert_eq!(r.battle,w.id);assert_eq!(r.native_inventory_id,1);
    let bodies=drain(s);assert!(bodies.contains(&crate::map_drive_world091::queue_callback(true)));r
}
fn unload(s:&mut Session,config:Arc<identity091::Config>,id:i16,count:i32)->(u64,i64){
    let before=(s.ammo_service.as_ref().unwrap().revision(),s.ammo_service.as_ref().unwrap().wire_revision());
    let args=[5,1,6,2570,count,2826,0,3082,0,6,0,0,0,0,0,0];
    let mut b=vec![0x97,72,0];b.extend(id.to_le_bytes());b.extend(108i16.to_le_bytes());b.extend(16u32.to_le_bytes());
    for n in args{b.extend(n.to_le_bytes());}receive(s,&b);
    let mut job=None;ammo_session::start(s,&mut job,config).unwrap();assert!(job.is_some());
    let until=Instant::now()+Duration::from_secs(30);
    while job.is_some(){assert!(Instant::now()<until);ammo_session::complete(Some(s),&mut job).unwrap();std::thread::sleep(Duration::from_millis(10));}
    let after=(s.ammo_service.as_ref().unwrap().revision(),s.ammo_service.as_ref().unwrap().wire_revision());
    assert_eq!(after,(before.0+1,before.1+1));assert!(s.ammo_service.as_ref().unwrap().idle());
    assert!(!drain(s).is_empty());after
}
fn phase(value:&serde_json::Value)->serde_json::Value{
    let config=Arc::new(identity091::Config::load(value["config"].as_str().unwrap()).unwrap());
    let mut s=session(&config,value["email"].as_str().unwrap(),value["password"].as_str().unwrap());
    let initial_revision=s.ammo_service.as_ref().unwrap().revision();let account=s.identity.as_ref().unwrap().account_id.clone();
    let mut d=profile13_dispatch::Dispatcher::default();let now=Instant::now();
    let battle=if value["phase"]=="reserve_then_exit"{9007199254740993}else{9007199254740994};
    let mut w=World::new(battle,now).unwrap();
    if value["phase"]=="reserve_then_exit"{
        let mut t=Table{sessions:vec![s],..Table::default()};let r=reserve(&mut t,&w,&mut d,config.clone());
        assert_eq!(r.frozen.ap_count,20);assert!(!d.busy());
        return serde_json::json!({"phase":"reserve_then_exit","account":account,"run":config.battle_run_id,"battle":battle.to_string(),
            "reservation":r.reservation_id,"revision":t.sessions[0].ammo_service.as_ref().unwrap().revision(),
            "initial_revision":initial_revision,"writer_settled":true,"native_client":"NOT_RUN"});
    }
    assert_eq!(value["phase"],"restart_warm_then_cas");
    let (_,warm)=unload(&mut s,config.clone(),401,19);assert_eq!(warm,2);
    let mut t=Table{sessions:vec![s],..Table::default()};let r=reserve(&mut t,&w,&mut d,config.clone());
    assert_eq!(r.frozen.ap_count,19);
    let s=&mut t.sessions[0];let owner=s.identity.as_ref().unwrap();
    w.attach_owned(model::Identity{account:owner.account_id.clone(),database:owner.database_id,name:owner.name.clone()},s.id,&r.frozen).unwrap();
    // Explicit AUTHORED terminal state for return composition ONLY. No second
    // fake owner, no World.start, geometry hit, kill/result or battle proof.
    w.actors[0].health=0;s.arena_base=true;let c=s.shared.as_mut().unwrap();c.phase=Phase::Driving;c.correction=true;
    c.binding=Some((0,true));c.return_generation=1;c.view=Some(w.clone());
    profile13_dispatch::Dispatcher::terminal(s,&w,crate::battle091::profile13::FinishReason::ManualLeave).unwrap();
    w.detach(s.id).unwrap();settle(&mut d,&mut t,&w,config.clone());
    let s=&mut t.sessions[0];assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Returning);
    assert_eq!(s.shared.as_ref().unwrap().return_source_revision,warm);
    assert_eq!(s.ammo_service.as_ref().unwrap().wire_revision(),1);
    let fixtures=s.hangar.clone().unwrap();let full_sha=format!("{:x}",Sha256::digest(fixtures.state_bytes()));
    let reset=crate::map_drive_world091::return_account(&s.identity.as_ref().unwrap().name).unwrap();assert!(drain(s).contains(&reset));
    receive(s,&[9]);drain(s);
    let old=s.clone();let wrong=sync(501,100,1);let f=Frame{flags:0x458,sequence:Some(s.rx),cumulative:Some(s.tx.cumulative),selective:vec![],
        body:[vec![1],s.token.to_le_bytes().to_vec(),wrong].concat(),piggybacks:vec![]};
    assert!(s.receive(&f,Instant::now()).is_err());assert_eq!(s.rx,old.rx);assert_eq!(s.ammo_service,old.ammo_service);
    assert_eq!(s.account_cache_hash,old.account_cache_hash);assert_eq!(s.request_ids,old.request_ids);
    receive(s,&sync(501,100,warm));let actual=drain(s);
    assert_eq!(actual,hangar091::response(&crate::account091::Request{id:501,command:100},&fixtures).unwrap());
    let mut tail=sync(502,300,fixtures.shop_sync_revision().unwrap());tail.extend(sync(503,600,0));receive(s,&tail);drain(s);
    assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Account);assert!(s.shared.as_ref().unwrap().profile13_garage_idle());
    receive(s,&sync(504,100,1));assert_eq!(drain(s),vec![ammo_service091::refresh_response(504,1).unwrap()]);
    let finish_revision=s.ammo_service.as_ref().unwrap().revision();let after=unload(s,config,505,18);
    serde_json::json!({"phase":"restart_warm_then_cas","account":account,"run":s.shared.as_ref().unwrap().profile13.as_ref().unwrap().run_id,"initial_revision":initial_revision,
        "warm_revision":warm,"full_revision":1,"fresh_state_sha256":full_sha,"fresh_fixture":s.identity.as_ref().unwrap().fixture_dir,
        "finish_revision":finish_revision,"final_revision":after.0,"final_wire":after.1,
        "reservation":r.reservation_id,"battle":battle.to_string(),"terminal_hp_authored":0,"native_client":"NOT_RUN"})
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
    let test_source="server/gateway/src/shared/profile13_restart_cas_tests.rs";
    let helper="web/tests/helpers/p08b-restart-cas.mjs";
    let compiled_test=format!("{:x}",Sha256::digest(include_bytes!("profile13_restart_cas_tests.rs")));
    let compiled_helper=format!("{:x}",Sha256::digest(include_bytes!("../../../../web/tests/helpers/p08b-restart-cas.mjs")));
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
    let base=root.join("local/test-runs/p08b-composition02");fs::create_dir_all(&base).unwrap();
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let output=base.join(format!("run-{}-{stamp}",std::process::id()));fs::create_dir(&output).unwrap();
    let guard=serde_json::json!({"schema":"p08b-restart-cas-parent-in-progress.v1","full_gate":"PENDING_PARENT_FULL_GATE",
        "head":head,"files":files,"parent_pid":std::process::id(),"target_dir":target,"build_output":output_root,"allocation":allocation,
        "compiled_test_source_sha256":compiled_test,"compiled_driver_sha256":compiled_helper,
        "test_executable":{"path":executable,"sha256":format!("{:x}",Sha256::digest(fs::read(&executable).unwrap()))},
        "test_name":"gateway091::shared::server::p08b_restart_cas_tests::p08b_restart_cas_composition02_real_http_session_phase"});
    let control=output.join("parent-control.json");fs::write(&control,serde_json::to_vec_pretty(&guard).unwrap()).unwrap();
    let bundle=std::env::var_os("P04D_TEST_BUNDLE").map(PathBuf::from).unwrap_or_else(||root.join("local/stands/p09e-main-01/source-bundle-05"));
    let original=std::env::var_os("P04D_TEST_ORIGINAL").map(PathBuf::from).unwrap_or_else(||PathBuf::from("C:/WoT_0.9.1_RU_0717_original"));
    assert!(bundle.is_dir()&&original.is_dir(),"actual source prerequisites missing; no skip");
    let stdout=fs::File::create(output.join("controller.stdout.log")).unwrap();let stderr=fs::File::create(output.join("controller.stderr.log")).unwrap();
    let mut child=Command::new("node");child.arg(root.join(helper)).arg("--parent-full").arg(&control).arg(&output).arg(bundle).arg(original)
        .current_dir(&root).stdin(Stdio::null()).stdout(Stdio::from(stdout)).stderr(Stdio::from(stderr));
    #[cfg(windows)]{use std::os::windows::process::CommandExt;child.creation_flags(0x08000000);}
    let mut child=child.spawn().unwrap();let status=child.wait().unwrap();assert!(status.success(),"composition controller failed; retained {}",output.display());
    let result:serde_json::Value=serde_json::from_slice(&fs::read(output.join("result.json"))
        .expect("controller exited successfully but actual composition result is absent")).unwrap();
    assert_eq!(result["status"],"PASS_ACTUAL_HTTP_SQLITE_SYNTHETIC_SESSION_COMPOSITION");
    assert_eq!(result["parent_full_gate"],"PENDING_PARENT_FULL_GATE");assert_eq!(result["native_client"],"NOT_RUN");
    println!("P08B_COMPOSITION_ACTUAL_PASS evidence={} native=NOT_RUN full_gate=PENDING_PARENT_FULL_GATE",output.display());
}

#[test]
fn p08b_restart_cas_composition02_real_http_session_phase(){
    if std::env::var_os("P08B_COMPOSITION_CONTROL").is_none(){parent();return;}
    let input=PathBuf::from(std::env::var_os("P08B_COMPOSITION_CONTROL").expect("explicit private isolated control required"));
    let output=PathBuf::from(std::env::var_os("P08B_COMPOSITION_OUTPUT").expect("fresh output required"));
    assert!(!output.exists());let raw=fs::read(input).unwrap();assert!(raw.len()<=8192);
    let value=crate::profile13_v2091::bounded_json(&raw,8192).unwrap();assert_eq!(value.as_object().unwrap().len(),5);
    assert_eq!(value["schema"],"p08b-restart-cas-composition.v1");
    let result=phase(&value);fs::write(output,serde_json::to_vec_pretty(&result).unwrap()).unwrap();
}
