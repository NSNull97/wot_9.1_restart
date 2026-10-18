//! Composition39: real Session CMD108 -> singleton garage Job -> HTTP/SQLite
//! -> readonly Fresh -> atomic same-Account delta. Native transport pressure,
//! Session envelope/ACK scheduling are AUTHORED; replies/cache/SQL are genuine.
use super::*;
use crate::{identity091,hangar091,ammo_service091,transport091};
use sha2::{Digest,Sha256};
use std::path::PathBuf;
use super::p08c_late_composition_tests as common;
const TEST:&str="gateway091::shared::server::garage_fresh_composition_tests::p04m_garage_fresh39_actual_http_sqlite";
fn barrier(v:&serde_json::Value,name:&str,summary:serde_json::Value){
    use std::io::Write;
    let dir=plain(&PathBuf::from(v["barrier"].as_str().unwrap()));
    let mut f=fs::OpenOptions::new().write(true).create_new(true).open(dir.join(format!("{name}.ready.json"))).unwrap();
    let raw=serde_json::to_vec(&summary).unwrap();assert!(raw.len()<=65536);f.write_all(&raw).unwrap();f.sync_all().unwrap();drop(f);
    let go=dir.join(format!("{name}.go"));let end=Instant::now()+Duration::from_secs(45);
    while !go.is_file(){assert!(Instant::now()<end,"actual SQL barrier timeout {name}");std::thread::sleep(Duration::from_millis(10));}
    assert_eq!(fs::read(go).unwrap(),b"GO\n");
}
fn receive(s:&mut Session,body:&[u8])->Frame{
    let frame=Frame{flags:0x458,sequence:Some(s.rx),cumulative:Some(s.tx.cumulative),selective:vec![],body:[vec![1],s.token.to_le_bytes().to_vec(),body.to_vec()].concat(),piggybacks:vec![]};
    assert!(!s.receive(&frame,Instant::now()).unwrap());frame
}
fn ammo(id:i16,count:i32)->Vec<u8>{
    let mut body=vec![0x97,72,0];body.extend(id.to_le_bytes());body.extend(108i16.to_le_bytes());body.extend(16u32.to_le_bytes());
    for n in [5_i32,1,6,2570,0,2826,count,3082,10,6,0,0,0,0,0,0]{body.extend(n.to_le_bytes());}body
}
fn session(config:&identity091::Config,user:&serde_json::Value,hold5:bool)->Session{
    assert!(config.p04m_pool&&config.p06t_mixed_ammo&&config.p06t_ammo_rack_detonation&&config.profile13_battle);
    assert_eq!(config.p08b_owner_battle_hold,hold5);assert!(!config.p08c_late_results&&!config.training_rooms);
    let owner=Arc::new(config.authenticate(user["email"].as_str().unwrap(),user["password"].as_str().unwrap()).unwrap().expect("actual C source-owned authentication"));
    assert_eq!(owner.account_id,user["account_id"]);let fixtures=Arc::new(hangar091::Fixtures::load_p04m(&owner.fixture_dir).unwrap());
    let metadata=ammo_service091::metadata_research(&owner.fixture_dir,&owner.account_id,owner.database_id).unwrap();
    let login=if hold5{Some(config.inspect_hold_login(&owner,&fixtures,metadata).unwrap().expect("actual idle Inspect5"))}else{None};
    if let Some(login)=&login{assert_eq!(login.reply.status,crate::profile13_hold091::Status::Inspected);assert!(login.reservation.is_none());}
    let now=Instant::now();let mut s=Session::new(39,[39;16],"127.0.0.1:41839".parse().unwrap(),now);
    // AUTHORED native Account transport state; identity/cache/pool came only from Config.
    s.active=true;s.account_ready=true;s.account_probe=true;s.sync_mask=7;s.rx=1;s.tx=Window::interactive();s.base_peer=Some("127.0.0.1:41939".parse().unwrap());
    s.login_attempt=Some(LoginAttempt::new(s.key,s.id,s.login_peer));s.identity=Some(owner);s.hangar=Some(fixtures);
    s.ammo_service=Some(ammo_session::State::new(metadata,config.crew_service).with_transfer(config.crew_transfer).with_cross_vehicle(config.crew_cross_vehicle)
        .with_roster_recruitment(config.crew_roster_recruitment).with_progression(config.crew_progression).with_dismissal(config.crew_dismissal)
        .with_barracks(config.crew_barracks_recruitment).with_research(config.research_service));
    s.ammo_service.as_mut().unwrap().replace_pool(s.hangar.as_ref().unwrap().p04m_binding().cloned()).unwrap();
    let mut c=Client::new(0);if config.visibility_v1{c.enable_spotting().unwrap();}c.join_requested=false;c.hangar_since=Some(now-Duration::from_secs(4));
    c.profile13=Some(super::super::profile13_session::State::new(config.battle_run_id.clone(),metadata.revision).unwrap());s.shared=Some(c);
    if let Some(login)=login{profile13_dispatch::Dispatcher::default().install_hold_login(&mut s,login).unwrap();}
    // Production login keeps no stale hold projection when no reservation exists.
    let p=s.shared.as_ref().unwrap().profile13.as_ref().unwrap();assert!(!p.has_reservation()&&!p.has_pending_return()&&p.hold_projection.is_none());
    assert!(s.shared.as_ref().unwrap().profile13_garage_idle());s
}
fn summary(s:&Session)->serde_json::Value{
    let state=s.ammo_service.as_ref().unwrap();let h=s.hangar.as_ref().unwrap();let c=s.shared.as_ref().unwrap();let owner=s.identity.as_ref().unwrap();
    serde_json::json!({"revision":state.revision(),"wire_revision":state.wire_revision(),"profile13_revision":c.profile13.as_ref().unwrap().revision,"account_epoch":c.account_incarnation(),"phase":format!("{:?}",c.phase),"fixture_dir":owner.fixture_dir,"state_sha256":format!("{:x}",Sha256::digest(h.state_bytes())),"pool_revision":h.p04m_binding().unwrap().revision,"outbox":s.outbox.len(),"window":s.tx.len()})
}
fn wait_known(s:&mut Session,job:&mut Option<ammo_session::Job>,revision:u64,wire:i64){
    let end=Instant::now()+Duration::from_secs(50);
    loop{
        ammo_session::complete(Some(&mut *s),job).unwrap();
        if job.as_ref().and_then(|j|j.known_reply_for_test())==Some((revision,wire,true))&&job.as_ref().and_then(|j|j.fresh_attempts_for_test()).is_some_and(|n|n>=2){break;}
        assert!(job.is_some()&&Instant::now()<end,"genuine known reply/read retry must remain in the same singleton");std::thread::sleep(Duration::from_millis(10));
    }
}
fn finish(s:&mut Session,job:&mut Option<ammo_session::Job>){let end=Instant::now()+Duration::from_secs(50);while job.is_some(){ammo_session::complete(Some(&mut *s),job).unwrap();assert!(Instant::now()<end,"real immutable Job publication timeout");std::thread::sleep(Duration::from_millis(10));}}
fn native_pair(s:&mut Session,id:i16)->serde_json::Value{
    let bodies=common::drain(s);assert_eq!(bodies.len(),2,"only actual update+callback are published after pressure ACK");
    let update=&bodies[0];assert!(update.len()>=8);assert_eq!(&update[..2],&[0x13,0x57]);assert_eq!(update[2]as usize,update.len()-3);assert_eq!(update[3]as usize,update.len()-4);
    hangar091::validate_account_delta(&update[4..]).unwrap();assert_eq!(bodies[1],ammo_service091::success_response(id).unwrap());
    serde_json::json!({"update_hex":update[4..].iter().map(|b|format!("{b:02x}")).collect::<String>(),"update_method":0x57,"callback_after_update":true,"callback_hex":bodies[1].iter().map(|b|format!("{b:02x}")).collect::<String>(),"bodies":2})
}
fn check_idle_hold(config:&identity091::Config,s:&Session,count:i32){
    if !config.p08b_owner_battle_hold{return;}
    let owner=s.identity.as_ref().unwrap();let a=s.ammo_service.as_ref().unwrap();let h=s.hangar.as_ref().unwrap();
    let state_sha=h.state_sha256().iter().map(|b|format!("{b:02x}")).collect::<String>();
    let binding=config.hold_binding(owner,a.revision(),&state_sha).unwrap();assert!(binding.matches(&owner.account_id,owner.database_id,a.revision(),&state_sha));
    let raw=fs::read(owner.fixture_dir.join("p08b-owner-hold.json")).unwrap();let v=crate::profile13_v2091::bounded_json(&raw,4096).unwrap();
    assert_eq!(v["version"],5);assert_eq!(v["revision"],a.revision());assert_eq!(v["state_sha256"],state_sha);
    let row=v["native_layouts"].as_array().unwrap().iter().find(|r|r["native_inventory_id"]==1).unwrap();
    assert_eq!(row["shells_layout"],serde_json::json!([2570,0,2826,count,3082,10]));
    let p=s.shared.as_ref().unwrap().profile13.as_ref().unwrap();assert!(!p.has_reservation()&&!p.has_pending_return()&&p.hold_projection.is_none());
    assert!(s.shared.as_ref().unwrap().profile13_garage_idle());
}
fn phase(v:&serde_json::Value,hold5:bool)->serde_json::Value{
    let config=Arc::new(identity091::Config::load(v["config"].as_str().unwrap()).unwrap());let users=v["users"].as_array().unwrap();assert_eq!(users.len(),2);
    let mut s=session(&config,&users[0],hold5);check_idle_hold(&config,&s,4);let initial=summary(&s);let n=s.ammo_service.as_ref().unwrap().revision();let wire=s.ammo_service.as_ref().unwrap().wire_revision();assert_eq!(wire,1);
    let epoch=s.shared.as_ref().unwrap().account_incarnation();let old_fixture=s.identity.as_ref().unwrap().fixture_dir.clone();let old_state=s.hangar.as_ref().unwrap().state_sha256();
    barrier(v,"after-auth",initial.clone());
    // Late poison and a whole-packet retry must never dispatch an extra mutation.
    let good=ammo(901,3);let mut poison=good.clone();poison.push(0xff);let mut rejected=s.clone();let before=rejected.ammo_service.clone();
    let f=Frame{flags:0x458,sequence:Some(rejected.rx),cumulative:Some(rejected.tx.cumulative),selective:vec![],body:[vec![1],rejected.token.to_le_bytes().to_vec(),poison].concat(),piggybacks:vec![]};
    assert!(rejected.receive(&f,Instant::now()).is_err());assert_eq!(rejected.ammo_service,before);assert_eq!(rejected.rx,s.rx);assert!(rejected.outbox.is_empty());
    let f=receive(&mut s,&good);let staged=s.ammo_service.clone();assert!(!s.receive(&f,Instant::now()).unwrap());assert_eq!(s.ammo_service,staged);
    let mut job=None;ammo_session::start(&mut s,&mut job,config.clone()).unwrap();assert!(job.is_some());
    // AUTHORED source-valid callback bodies provide bounded native outbox pressure.
    // No authoritative reply/Fresh/SQL completion is fabricated by these fillers.
    for id in 30000_i16..30127{s.outbox.push_back(hangar091::unavailable_response(id).unwrap());}assert_eq!(s.outbox.len(),127);
    let before=s.ammo_service.clone();wait_known(&mut s,&mut job,n+1,wire+1);assert_eq!(s.ammo_service,before);assert_eq!(s.identity.as_ref().unwrap().fixture_dir,old_fixture);assert_eq!(s.hangar.as_ref().unwrap().state_sha256(),old_state);
    barrier(v,"known-retained",serde_json::json!({"session":summary(&s),"known":job.as_ref().unwrap().known_reply_for_test(),"fresh_attempts":job.as_ref().unwrap().fresh_attempts_for_test(),"sql_mutation_reissued":false}));
    for _ in 0..3{ammo_session::complete(Some(&mut s),&mut job).unwrap();std::thread::sleep(Duration::from_millis(20));}assert!(job.is_some());assert_eq!(s.ammo_service,before);
    barrier(v,"pressure-still-retained",summary(&s));
    let pressure=common::drain(&mut s);assert_eq!(pressure.len(),127);assert!(pressure.iter().all(|b|b.get(1)!=Some(&0x57)));finish(&mut s,&mut job);
    assert_eq!(s.ammo_service.as_ref().unwrap().revision(),n+1);assert_eq!(s.ammo_service.as_ref().unwrap().wire_revision(),wire+1);assert_eq!(s.shared.as_ref().unwrap().account_incarnation(),epoch);
    assert_ne!(s.identity.as_ref().unwrap().fixture_dir,old_fixture);assert_ne!(s.hangar.as_ref().unwrap().state_sha256(),old_state);assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Account);
    check_idle_hold(&config,&s,3);let first=native_pair(&mut s,901);barrier(v,"first-published",serde_json::json!({"session":summary(&s),"native":first}));
    receive(&mut s,&ammo(902,4));ammo_session::start(&mut s,&mut job,config.clone()).unwrap();assert!(job.is_some());finish(&mut s,&mut job);
    assert_eq!(s.ammo_service.as_ref().unwrap().revision(),n+2);assert_eq!(s.ammo_service.as_ref().unwrap().wire_revision(),wire+2);assert_eq!(s.shared.as_ref().unwrap().account_incarnation(),epoch);
    check_idle_hold(&config,&s,4);let second=native_pair(&mut s,902);barrier(v,"second-published",serde_json::json!({"session":summary(&s),"native":second}));
    // A third genuine Job gets an actual HTTP503 BEFORE the proxy forwards
    // its mutation. SQL remains at two commits. AUTHORED replacement channel
    // tests the caller-facing unknown-error boundary, not actual re-login.
    receive(&mut s,&ammo(903,3));ammo_session::start(&mut s,&mut job,config.clone()).unwrap();assert!(job.is_some());
    let mut replacement=s.clone();replacement.key[0]^=1;replacement.token^=1;
    let next_generation=replacement.shared.as_ref().unwrap().return_generation.checked_add(1).unwrap();replacement.shared.as_mut().unwrap().return_generation=next_generation;
    let untouched=replacement.clone();let end=Instant::now()+Duration::from_secs(30);
    while job.is_some(){
        // Old32/02 reports the receiver error before checking this foreign
        // recipient, which would make its real caller retire the replacement.
        ammo_session::complete(Some(&mut replacement),&mut job).expect("unknown old-channel HTTP failure must not close same-SID foreign channel");
        assert!(Instant::now()<end,"actual unknown HTTP completion bounded");std::thread::sleep(Duration::from_millis(10));
    }
    assert_eq!(replacement.id,untouched.id);assert!(replacement.active&&untouched.active);
    assert!((replacement.key,replacement.token,replacement.handoff,replacement.login_peer,replacement.base_peer,replacement.login_attempt)==
        (untouched.key,untouched.token,untouched.handoff,untouched.login_peer,untouched.base_peer,untouched.login_attempt),
        "opaque recipient channel identity must remain unchanged");
    assert_eq!(replacement.ammo_service,untouched.ammo_service);assert_eq!(replacement.outbox,untouched.outbox);assert!(replacement.outbox.is_empty());
    assert_eq!((replacement.rx,replacement.tx.len(),replacement.tx.cumulative,replacement.account_ready,replacement.sync_mask),
        (untouched.rx,untouched.tx.len(),untouched.tx.cumulative,untouched.account_ready,untouched.sync_mask));
    assert_eq!(replacement.received,untouched.received);assert_eq!(replacement.request_ids,untouched.request_ids);assert_eq!(replacement.unsupported_request_ids,untouched.unsupported_request_ids);
    assert_eq!(summary(&replacement),summary(&untouched));assert!(Arc::ptr_eq(replacement.identity.as_ref().unwrap(),untouched.identity.as_ref().unwrap()));assert!(Arc::ptr_eq(replacement.hangar.as_ref().unwrap(),untouched.hangar.as_ref().unwrap()));
    barrier(v,"unknown-foreign-retired",serde_json::json!({"foreign_recipient_unchanged":true,"same_sid":replacement.id==s.id,"different_account_epoch":replacement.shared.as_ref().unwrap().account_incarnation()!=epoch,"observer_cleared":job.is_none(),"callbacks":0,"session":summary(&replacement)}));
    serde_json::json!({"status":if hold5{"PASS_ACTUAL_GARAGE_HOLD5_JOB_HTTP_SQLITE_FRESH"}else{"PASS_ACTUAL_GARAGE_JOB_HTTP_SQLITE_FRESH"},"writer_version":if hold5{5}else{4},"actual_login_inspect5":hold5,"actual_commands":2,"actual_http_attempts":3,"unknown_receiver_foreign_channel_preserved":true,"source_revision":n,"final_revision":n+2,"source_wire_revision":wire,"final_wire_revision":wire+2,"same_account_epoch":true,"known_reply_retained":true,"full_rebind":false,"new_grants":0,"native_client":"NOT_RUN","authored":"Session/frame/ACK scheduling,127 native callback pressure bodies and opaque foreign-channel/epoch replacement; two explicit proxy503 failures only, no authored binding/Fresh/AmmoReply/completion"})
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
// Test-only output creation: validate existing ancestors BEFORE each one-level
// mkdir and validate the newly born directory BEFORE any evidence file write.
fn plain_child_directory(parent:&std::path::Path,name:&str)->PathBuf{
    assert!(!name.is_empty()&&name!="."&&name!=".."&&!name.contains('/')&&!name.contains('\\'));
    let parent=plain(parent);assert!(parent.is_dir());let child=parent.join(name);
    match fs::symlink_metadata(&child){
        Ok(_)=>{},
        Err(error)if error.kind()==std::io::ErrorKind::NotFound=>fs::create_dir(&child).unwrap(),
        Err(error)=>panic!("owned test directory metadata: {error}"),
    }
    let child=plain(&child);assert!(child.is_dir());assert_eq!(child.parent(),Some(parent.as_path()));child
}
fn fresh_test_output(root:&std::path::Path,hold5:bool)->PathBuf{
    let local=plain(&root.join("local"));assert_eq!(local.parent(),Some(root));
    let runs=plain_child_directory(&local,"test-runs");
    let base=plain_child_directory(&runs,if hold5{"p04m-garage-hold5-fresh39"}else{"p04m-garage-fresh39"});
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let output=base.join(format!("run-{}-{stamp}",std::process::id()));fs::create_dir(&output).unwrap();
    let output=plain(&output);assert!(output.is_dir());assert_eq!(output.parent(),Some(base.as_path()));
    assert!(fs::read_dir(&output).unwrap().next().is_none());output
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


fn parent(test_name:&str,hold5:bool){
    use std::{collections::BTreeMap,process::{Command,Stdio}};
    let root=PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..").canonicalize().unwrap();
    assert!(root.is_absolute()&&root.join("server").is_dir()&&root.join("web").is_dir()&&root.join("tests").is_dir(),"39 composition root must be the current source checkout");
    let compiled:BTreeMap<String,String>=[
        ("server/gateway/src/shared/garage_fresh_composition_tests.rs",include_bytes!("garage_fresh_composition_tests.rs").as_slice()),
        ("web/tests/helpers/p04m-garage-fresh-composition.mjs",include_bytes!("../../../../web/tests/helpers/p04m-garage-fresh-composition.mjs").as_slice()),
        ("web/tests/helpers/p04m-garage-sql-barriers.mjs",include_bytes!("../../../../web/tests/helpers/p04m-garage-sql-barriers.mjs").as_slice()),
        ("web/tests/helpers/p04m-garage-source-context.mjs",include_bytes!("../../../../web/tests/helpers/p04m-garage-source-context.mjs").as_slice()),
        ("web/tests/helpers/p08c-late-result-composition.mjs",include_bytes!("../../../../web/tests/helpers/p08c-late-result-composition.mjs").as_slice()),
        ("tests/helpers/p04m_garage_fresh_seed.py",include_bytes!("../../../../tests/helpers/p04m_garage_fresh_seed.py").as_slice()),
        ("tests/helpers/p04m_garage_fresh_source.py",include_bytes!("../../../../tests/helpers/p04m_garage_fresh_source.py").as_slice()),
        ("server/gateway/src/account/ammo_session.rs",include_bytes!("../account/ammo_session.rs").as_slice()),
        ("server/gateway/src/account/ammo_session_fresh.rs",include_bytes!("../account/ammo_session_fresh.rs").as_slice()),
        ("server/gateway/src/shared/mod.rs",include_bytes!("mod.rs").as_slice()),
    ].into_iter().map(|(p,b)|(p.to_owned(),format!("{:x}",Sha256::digest(b)))).collect();
    for(p,pin)in &compiled{assert_eq!(format!("{:x}",Sha256::digest(fs::read(root.join(p)).unwrap())),*pin,"compiled composition/32 dependency source changed");}
    let executable=plain(&std::env::current_exe().unwrap());let target=plain(&PathBuf::from(std::env::var_os("CARGO_TARGET_DIR").expect("canonical Cargo target required")));
    assert_eq!(executable.parent().unwrap(),target.join("debug/deps"));let name=executable.file_name().unwrap().to_str().unwrap();assert!(name.starts_with("sr_gateway-")&&name.ends_with(".exe"));let(output_root,allocation)=allocation(&root,&target);
    let git=|args:&[&str]|{let out=Command::new("git").args(args).current_dir(&root).output().unwrap();assert!(out.status.success());out.stdout};let head=String::from_utf8(git(&["rev-parse","HEAD"])).unwrap().trim().to_owned();let scopes=["server","tools","client_patch","web/src","tests","web/tests"];
    let mut status=vec!["status","--porcelain","--untracked-files=all","--"];status.extend(scopes);assert!(git(&status).is_empty());let mut args=vec!["ls-files","-z","--"];args.extend(scopes);let names=git(&args);let mut files=BTreeMap::new();
    for raw in names.split(|b|*b==0).filter(|s|!s.is_empty()){let n=std::str::from_utf8(raw).unwrap().to_owned();let path=plain(&root.join(&n));assert!(path.starts_with(&root));files.insert(n,format!("{:x}",Sha256::digest(fs::read(path).unwrap())));}
    let output=fresh_test_output(&root,hold5);
    // Exact shortC only, sufficient free volume: no D relocation/compression policy change.
    fs::write(output.join("storage.json"),b"{\"mode\":\"fresh-short-C-only\",\"compression\":false,\"old_data_touched\":false}").unwrap();
    let guard=serde_json::json!({"schema":if hold5{"p04m-garage-hold5-fresh39-parent-in-progress.v1"}else{"p04m-garage-fresh39-parent-in-progress.v1"},"full_gate":"PENDING_PARENT_FULL_GATE","head":head,"files":files,"parent_pid":std::process::id(),"target_dir":target,"build_output":output_root,"allocation":allocation,"compiled_files":compiled,"test_executable":{"path":executable,"sha256":format!("{:x}",Sha256::digest(fs::read(&executable).unwrap()))},"test_name":test_name});
    let control=output.join("parent-control.json");fs::write(&control,serde_json::to_vec_pretty(&guard).unwrap()).unwrap();let bundle=root.join("local/stands/p09e-main-01/source-bundle-05");let original=PathBuf::from("C:/WoT_0.9.1_RU_0717_original");assert!(bundle.is_dir()&&original.is_dir(),"source prerequisites required; no skip");
    let stdout=fs::File::create(output.join("controller.stdout.log")).unwrap();let stderr=fs::File::create(output.join("controller.stderr.log")).unwrap();let mut child=Command::new("node");child.arg(root.join("web/tests/helpers/p04m-garage-fresh-composition.mjs")).arg("--parent-full").arg(control).arg(&output).arg(bundle).arg(original).arg(root.join("local/night-staging/20261016/p10b-selection-http01/seed01/seed.json")).current_dir(&root).env_remove("PYTHONPATH").stdin(Stdio::null()).stdout(Stdio::from(stdout)).stderr(Stdio::from(stderr));
    #[cfg(windows)]{use std::os::windows::process::CommandExt;child.creation_flags(0x08000000);}
    let mut child=child.spawn().unwrap();let end=Instant::now()+Duration::from_secs(360);let result=loop{if let Some(s)=child.try_wait().unwrap(){break s;}if Instant::now()>=end{let _=child.kill();let _=child.wait();panic!("own39 controller timeout, evidence retained");}std::thread::sleep(Duration::from_millis(20));};assert!(result.success(),"actual39 failed, retained {}",output.display());
    let result:serde_json::Value=serde_json::from_slice(&fs::read(output.join("result.json")).unwrap()).unwrap();assert_eq!(result["status"],if hold5{"PASS_ACTUAL_GARAGE_HOLD5_JOB_HTTP_SQLITE_FRESH"}else{"PASS_ACTUAL_GARAGE_JOB_HTTP_SQLITE_FRESH"});assert_eq!(result["writer_version"],if hold5{5}else{4});assert_eq!(result["actual_login_inspect5"],hold5);assert_eq!(result["parent_full_gate"],"PENDING_PARENT_FULL_GATE");assert_eq!(result["native_client"],"NOT_RUN");println!("P04M_GARAGE_FRESH39_ACTUAL_PASS evidence={} native=NOT_RUN full_gate=PENDING_PARENT_FULL_GATE",output.display());
}
const HOLD_TEST:&str="gateway091::shared::server::garage_fresh_composition_tests::p04m_garage_fresh39_hold5_actual_http_sqlite";
fn execute(hold5:bool){
    if std::env::var_os("P04M_GARAGE_COMPOSITION_CONTROL").is_none(){assert!(std::env::var_os("P04M_GARAGE_COMPOSITION_OUTPUT").is_none());parent(if hold5{HOLD_TEST}else{TEST},hold5);return;}
    let input=plain(&PathBuf::from(std::env::var_os("P04M_GARAGE_COMPOSITION_CONTROL").unwrap()));let output=PathBuf::from(std::env::var_os("P04M_GARAGE_COMPOSITION_OUTPUT").unwrap());assert!(!output.exists());let dir=plain(output.parent().unwrap());assert!(dir.starts_with(PathBuf::from(if hold5{"C:/wot091-night-20261017-01/w/local/test-runs/p04m-garage-hold5-fresh39"}else{"C:/wot091-night-20261017-01/w/local/test-runs/p04m-garage-fresh39"}).canonicalize().unwrap()));assert_eq!(output.file_name().unwrap(),"phase.json");assert_eq!(input,dir.join("phase-control.private.json"));
    let raw=fs::read(input).unwrap();assert!(raw.len()<=65536);let v=crate::profile13_v2091::bounded_json(&raw,65536).unwrap();let keys=["schema","phase","config","users","barrier"];assert_eq!(v.as_object().unwrap().len(),keys.len());assert!(keys.iter().all(|k|v.get(*k).is_some()));assert_eq!(v["schema"],if hold5{"p04m-garage-hold5-fresh39.v1"}else{"p04m-garage-fresh39.v1"});assert_eq!(v["phase"],if hold5{"actual_hold5_command_fresh_pressure"}else{"actual_command_fresh_pressure"});let result=phase(&v,hold5);
    use std::io::Write;let mut f=fs::OpenOptions::new().write(true).create_new(true).open(output).unwrap();f.write_all(&serde_json::to_vec_pretty(&result).unwrap()).unwrap();
}

#[test]fn p04m_garage_fresh39_actual_http_sqlite(){execute(false);}
#[test]fn p04m_garage_fresh39_hold5_actual_http_sqlite(){execute(true);}
