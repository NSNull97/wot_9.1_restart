//! Actual Loss4 Host/HTTP/SQL composition. Synthetic native envelopes, Session,
//! validated ACKs, binding/ready gates, source Prohorovka terrain and authored Forfeit clock only.
//! No authored ReadyRef, Selection, Saga, Admit/Finished reply, HP or hit record.
use super::*;
use super::super::p08c_late_composition_tests as common;
use super::super::super::{geometry,terrain,lifecycle,late_results_runtime};
use crate::identity091;
use sha2::{Digest,Sha256};use std::path::PathBuf;

fn rpc(id:i16,command:i16,a:i64,b:i32)->Vec<u8>{let mut out=common::sync(id,command,a);out[15..19].copy_from_slice(&b.to_le_bytes());out}
fn send(h:&mut Host,t:&mut Table,w:&World,id:u32,payload:&[u8],logical:u64){
    let s=t.sessions.iter().find(|s|s.id==id).unwrap();let f=Frame{flags:0x458,sequence:Some(s.rx),cumulative:Some(s.tx.cumulative),selective:vec![],
        body:[vec![1],s.token.to_le_bytes().to_vec(),payload.to_vec()].concat(),piggybacks:vec![]};
    assert!(!h.receive(t,id,&f,w,Instant::now(),logical).unwrap());
}
/// Synthetic validated ACKs enter through the SAME actual outer training
/// transaction as production. Ordinary Session.receive intentionally refuses
/// training_opt_in, even for an ACK; never toggle that guard in a test.
fn ack(h:&mut Host,t:&mut Table,w:&World,logical:u64)->Vec<Vec<u8>>{
    let mut bodies=Vec::new();let mut rounds=0;
    while t.sessions.iter().any(|s|!s.outbox.is_empty()||s.tx.len()!=0){
        rounds+=1;assert!(rounds<=128,"bounded actual Host/Window synthetic ACK drain");
        let ids=t.sessions.iter().filter(|s|!s.outbox.is_empty()||s.tx.len()!=0).map(|s|s.id).collect::<Vec<_>>();
        for id in ids{
            let cumulative={let s=t.sessions.iter_mut().find(|s|s.id==id).unwrap();s.drain_outbox().unwrap();let mut ack=s.tx.cumulative;
                while let Some((sequence,_,raw))=s.tx.due(Instant::now()+Duration::from_secs(1),s.rx).unwrap(){
                    ack=ack.max(sequence+1);bodies.push(crate::transport091::parse_interactive(&raw).unwrap().body);
                }ack};
            let frame=Frame{flags:0x408,sequence:None,cumulative:Some(cumulative),selective:vec![],body:vec![],piggybacks:vec![]};
            assert!(!h.receive(t,id,&frame,w,Instant::now(),logical).unwrap());
        }
    }bodies
}
/// Original warm Account envelopes, also routed through real Host.receive.
/// No source/generation flag is disabled and no fixtures/CAS are authored.
fn warm(h:&mut Host,t:&mut Table,w:&World,id:u32,logical:u64){
    assert_eq!(t.sessions.iter().find(|s|s.id==id).unwrap().shared.as_ref().unwrap().phase,Phase::Returning);
    ack(h,t,w,logical);send(h,t,w,id,&[9],logical);ack(h,t,w,logical);
    let(cursor,shop)={let s=t.sessions.iter().find(|s|s.id==id).unwrap();(s.shared.as_ref().unwrap().return_source_revision,s.hangar.as_ref().unwrap().shop_sync_revision().unwrap())};
    send(h,t,w,id,&rpc(501,100,cursor,0),logical);ack(h,t,w,logical);
    let mut tail=rpc(502,300,shop,0);tail.extend(rpc(503,600,0,0));send(h,t,w,id,&tail,logical);ack(h,t,w,logical);
    let s=t.sessions.iter().find(|s|s.id==id).unwrap();assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Account);assert!(s.shared.as_ref().unwrap().profile13_garage_idle());
}
fn claim(h:&Host,s:&Session)->Option<room::Claim>{h.controller.registry().claim(readiness::account(&s.identity.as_ref().unwrap().account_id).unwrap())}
fn pristine(battle:u64,now:Instant)->World{
    let mut w=World::new_for_roster(battle,now,MapId::Prohorovka,6).unwrap();
    w.bind_geometry(Arc::new(geometry::tests::bundle())).unwrap();w.bind_geometry(Arc::new(geometry::tests::is7_bundle())).unwrap();w.enable_ap_test_lab().unwrap();
    w.bind_terrain(Arc::new(terrain::tests::actual_prohorovka().clone())).unwrap();w.enable_mixed_ammo().unwrap();
    w.enable_lifecycle(lifecycle::Rules::prohorovka()).unwrap();w.enable_ammo_detonation().unwrap();w
}
fn poll(h:&mut Host,t:&mut Table,w:&mut World,r:&mut Option<IntegratedRuntime>,template:&BattleTemplate,d:&mut profile13_dispatch::Dispatcher,c:Arc<identity091::Config>,logical:u64)->bool{
    h.poll(t,w,r,template,d,c,Instant::now(),logical,true).unwrap()
}
fn ready(h:&mut Host,t:&mut Table,w:&mut World,r:&mut Option<IntegratedRuntime>,template:&BattleTemplate,d:&mut profile13_dispatch::Dispatcher,c:Arc<identity091::Config>,logical:u64){
    let deadline=Instant::now()+Duration::from_secs(60);
    while h.ready.accepted.len()!=2{
        assert!(Instant::now()<deadline,"real readonly Loss4 selections must become Ready");poll(h,t,w,r,template,d,c.clone(),logical);ack(h,t,w,logical);std::thread::sleep(Duration::from_millis(10));
    }
    for item in h.ready.accepted.values(){assert_eq!(item.selection.mode(),super::super::super::p10b_writer_mode::Mode::LossV4);
        assert_eq!(item.selection.run_id(),c.battle_run_id.as_str());assert_eq!(item.selection.reference().owner(),item.task.caller().account);}
}
fn make_room(h:&mut Host,t:&mut Table,w:&World,callback:i16,logical:u64)->u32{
    let a=t.sessions[0].id;let b=t.sessions[1].id;let mut create=vec![0x9a,10,0];create.extend(4i32.to_le_bytes());create.extend(600i32.to_le_bytes());create.extend([1,0]);
    send(h,t,w,a,&create,logical);ack(h,t,w,logical);
    let who=readiness::account(&t.sessions[0].identity.as_ref().unwrap().account_id).unwrap();let peer=readiness::account(&t.sessions[1].identity.as_ref().unwrap().account_id).unwrap();
    let room=h.controller.registry().authenticated_room(room::AuthLease{account:who,generation:u64::from(a)}).unwrap();let native=h.controller.native_room(room).unwrap();
    send(h,t,w,b,&rpc(202,400,i64::from(native),0),logical);ack(h,t,w,logical);
    let alias=h.controller.published_entity_for_test(who,peer).expect("actual already-published peer alias");
    send(h,t,w,a,&rpc(callback,404,i64::from(alias),2),logical);ack(h,t,w,logical);
    send(h,t,w,a,&rpc(callback+1,402,1,0),logical);send(h,t,w,b,&rpc(callback,402,1,0),logical);ack(h,t,w,logical);alias
}
fn votes(h:&mut Host,t:&mut Table,w:&World,id:i16,logical:u64){let a=t.sessions[0].id;send(h,t,w,a,&rpc(id,411,1,0),logical);ack(h,t,w,logical);send(h,t,w,a,&rpc(id+1,411,2,0),logical);}
fn finish(d:&mut profile13_dispatch::Dispatcher,t:&mut Table,w:&World,c:Arc<identity091::Config>){
    d.start(t,w,c.clone(),Instant::now()).unwrap();assert!(d.busy());let deadline=Instant::now()+Duration::from_secs(45);
    while d.busy(){assert!(Instant::now()<deadline);d.poll(t,c.clone(),Instant::now()).unwrap();std::thread::sleep(Duration::from_millis(10));}
}
fn clock(w:&mut World,start:Instant,from_ms:u64,to_ms:u64){
    assert!(from_ms<=to_ms);let mut at=from_ms;
    while at<to_ms{at=(at+1000).min(to_ms);w.advance_lifecycle(start+Duration::from_millis(at)).unwrap();}
}
fn phase(v:&serde_json::Value)->serde_json::Value{
    let c=Arc::new(identity091::Config::load(v["config"].as_str().unwrap()).unwrap());assert!(c.training_rooms);assert_eq!(c.battle_players,6);
    let users=v["users"].as_array().unwrap();let a=common::session(&c,&users[0],7);let b=common::session(&c,&users[1],8);
    let mut t=Table{sessions:vec![a,b],capacity:24,..Table::default()};let mut h=Host::for_config(&c).unwrap();for s in&mut t.sessions{h.bind_session(s).unwrap();}
    let initial=v["arena_id"].as_str().unwrap().parse::<u64>().unwrap();let now=Instant::now();let mut w=pristine(initial,now);let template=BattleTemplate::new(&w,&None);let mut runtime=None;
    let mut d=profile13_dispatch::Dispatcher::default();if c.training_rooms{d.enable_training_finished();}d.late=Some(late_results_runtime::Manager::new(c.p08c_late_results_accounts.clone(),false).unwrap());
    common::barrier(v,"after-auth",serde_json::json!({"run":c.battle_run_id,"actual_auth":2,"native":"NOT_RUN"}));
    let alias1=make_room(&mut h,&mut t,&w,221,0);ready(&mut h,&mut t,&mut w,&mut runtime,&template,&mut d,c.clone(),0);
    common::barrier(v,"first-ready",serde_json::json!({"actual_http_ready":2,"run":c.battle_run_id}));
    votes(&mut h,&mut t,&w,223,1);assert!(h.preparing());let deadline=Instant::now()+Duration::from_secs(45);
    while h.preparing.as_ref().map_or(0,|p|p.held().len())!=1{
        assert!(Instant::now()<deadline);assert!(!poll(&mut h,&mut t,&mut w,&mut runtime,&template,&mut d,c.clone(),1));ack(&mut h,&mut t,&w,1);std::thread::sleep(Duration::from_millis(10));
    }
    assert!(!h.driver.job_active(),"accepted first Admit must have exited its worker");
    common::barrier(v,"first-admit",serde_json::json!({"actual_admitted":1,"actors":w.actors.len(),"battle":w.id.to_string()}));
    let creator=t.sessions[0].id;send(&mut h,&mut t,&w,creator,&rpc(225,401,0,0),2);assert!(h.preparing.as_ref().unwrap().saga().aborting());ack(&mut h,&mut t,&w,2);
    let deadline=Instant::now()+Duration::from_secs(60);while h.preparing(){assert!(Instant::now()<deadline);poll(&mut h,&mut t,&mut w,&mut runtime,&template,&mut d,c.clone(),2);ack(&mut h,&mut t,&w,2);std::thread::sleep(Duration::from_millis(10));}
    assert!(h.active.is_none()&&w.actors.is_empty()&&w.started.is_none());for s in&t.sessions{assert!(claim(&h,s).is_none());assert!(s.shared.as_ref().unwrap().profile13_garage_idle());}
    // Actual regression: no authored World reset, no new authentication/run.
    // An issued+compensated battle key must be revoked before next real Admit.
    assert_ne!(w.id,initial,"Host must retire compensated battle key before a fresh room");
    common::barrier(v,"compensated",serde_json::json!({"claims_released":2,"new_battle":w.id.to_string(),"same_actual_run":c.battle_run_id,"world_started":false}));
    let alias2=make_room(&mut h,&mut t,&w,231,3);assert_ne!(alias1,alias2,"no peer alias reuse across retired rooms");
    ready(&mut h,&mut t,&mut w,&mut runtime,&template,&mut d,c.clone(),3);common::barrier(v,"second-ready",serde_json::json!({"actual_http_ready":2,"run":c.battle_run_id}));
    votes(&mut h,&mut t,&w,233,4);let deadline=Instant::now()+Duration::from_secs(60);while h.active.is_none(){assert!(Instant::now()<deadline);poll(&mut h,&mut t,&mut w,&mut runtime,&template,&mut d,c.clone(),4);std::thread::sleep(Duration::from_millis(10));}
    let arena=w.id;assert_eq!(w.actors.len(),2);assert_eq!(w.expected_actors(),2);assert_eq!(w.actors[0].identity.account,users[1]["account_id"].as_str().unwrap());assert_eq!(w.actors[1].identity.account,users[0]["account_id"].as_str().unwrap());
    assert_eq!([w.team(0).unwrap(),w.team(1).unwrap()],[2,1]);let entry=Instant::now()+Duration::from_millis(3100);assert!(!h.can_start(&t,&w,entry).unwrap(),"actual final411 still in reliable queue");
    ack(&mut h,&mut t,&w,4);assert!(h.can_start(&t,&w,entry).unwrap());
    common::barrier(v,"launched",serde_json::json!({"actual_admitted":2,"arena":arena.to_string(),"teams":[2,1],"frozen_order":"B,A","arrival":"A,B","final411_acked":true}));
    // AUTHORED native engine binding/correction completion. Authority/source
    // ownership and World launch were actual Host/HTTP, no Avatar/Jolt claim.
    let start=Instant::now();w.lifecycle_created_unix=Some(std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_secs()as u32);
    w.start(start).unwrap();for(slot,actor)in w.actors.iter().enumerate(){let id=actor.session.unwrap();let s=t.sessions.iter_mut().find(|s|s.id==id).unwrap();
        s.arena_base=true;let client=s.shared.as_mut().unwrap();client.phase=Phase::Driving;client.correction=true;client.binding=Some((0,true));client.return_generation=1;client.view=Some(w.clone());assert_eq!(client.slot,slot);}
    for slot in 0..2{w.set_ready(slot,w.actors[slot].session.unwrap()).unwrap();}w.advance_lifecycle(start).unwrap();clock(&mut w,start,0,30000);
    let sid=t.sessions[0].id;profile13_dispatch::Dispatcher::terminal(&mut t.sessions[0],&w,crate::battle091::profile13::FinishReason::ManualLeave).unwrap();w.detach(sid).unwrap();
    finish(&mut d,&mut t,&w,c.clone());let owner=t.sessions[0].id;warm(&mut h,&mut t,&w,owner,5);poll(&mut h,&mut t,&mut w,&mut runtime,&template,&mut d,c.clone(),5);
    assert_eq!(h.active.as_ref().unwrap().finished.len(),1);for s in&t.sessions{assert_eq!(claim(&h,s),Some(room::Claim::Battle(room::BattleKey(arena))));}
    common::barrier(v,"one-finished",serde_json::json!({"actual_finished":1,"both_claims_still_battle":true,"arena":arena.to_string()}));
    w.advance_lifecycle(start+Duration::from_millis(30001)).unwrap();assert_eq!(w.lifecycle.as_ref().unwrap().outcome().unwrap().winner,2);
    d.late.as_mut().unwrap().seal_world(&w);let sealed=d.late.as_ref().unwrap().sealed_results(arena).expect("actual training launch installed full late Capture");
    super::super::stage_lifecycle_results_from(&mut t,&w,Some(sealed.clone())).unwrap();assert!(Arc::ptr_eq(t.sessions[1].shared.as_ref().unwrap().natural_result.as_ref().unwrap(),&sealed));
    clock(&mut w,start,30001,38001);let sid=t.sessions[1].id;profile13_dispatch::Dispatcher::terminal(&mut t.sessions[1],&w,crate::battle091::profile13::FinishReason::BattleFinished).unwrap();w.detach(sid).unwrap();
    d.late.as_mut().unwrap().before_reset(&w,"p10b_actual_host_composition_before_reset");template.replace(&mut w,&mut runtime,Instant::now()).unwrap();finish(&mut d,&mut t,&w,c.clone());
    poll(&mut h,&mut t,&mut w,&mut runtime,&template,&mut d,c.clone(),6);assert!(h.active.is_none());for s in&t.sessions{assert!(claim(&h,s).is_none());let p=s.shared.as_ref().unwrap().profile13.as_ref().unwrap();assert!(!p.has_reservation()&&!p.has_pending_return()&&!p.in_flight);}
    assert!(t.sessions[1].shared.as_ref().unwrap().result_committed);assert!(sealed.participants.iter().all(|p|p.health==90&&p.shots==0&&p.damage_dealt==0));
    common::barrier(v,"all-finished",serde_json::json!({"actual_finished":2,"claims_released":2,"arena":arena.to_string(),"actual_training_late_capture":true}));
    serde_json::json!({"status":"PASS_ACTUAL_P10B_LOSS_HOST_HTTP_SQLITE","run":c.battle_run_id,"arena_id":arena.to_string(),"compensation":true,"actual_readies":4,
        "actual_admits":3,"actual_finishes":3,"immutable_order_teams":true,"actual_capture":true,"native_client":"NOT_RUN","jolt":"NOT_RUN"})
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
    let test_source="server/gateway/src/shared/p10b_loss_composition_tests.rs";
    let helper="web/tests/helpers/p10b-loss-composition.mjs";
    let compiled_test=format!("{:x}",Sha256::digest(include_bytes!("p10b_loss_composition_tests.rs")));
    let compiled_helper=format!("{:x}",Sha256::digest(include_bytes!("../../../../web/tests/helpers/p10b-loss-composition.mjs")));
    let compiled_common=format!("{:x}",Sha256::digest(include_bytes!("../../../../web/tests/helpers/p08c-late-result-composition.mjs")));
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
    let base=root.join("local/test-runs/p10b-loss-composition09");fs::create_dir_all(&base).unwrap();
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let output=base.join(format!("run-{}-{stamp}",std::process::id()));fs::create_dir(&output).unwrap();
    crate::gateway091::shared::composition_storage_tests::compress_fresh_output(&root,&output).unwrap();
    let guard=serde_json::json!({"schema":"p10b-loss-parent-in-progress.v1","full_gate":"PENDING_PARENT_FULL_GATE",
        "head":head,"files":files,"parent_pid":std::process::id(),"target_dir":target,"build_output":output_root,"allocation":allocation,
        "compiled_test_source_sha256":compiled_test,"compiled_driver_sha256":compiled_helper,"compiled_common_driver_sha256":compiled_common,
        "test_executable":{"path":executable,"sha256":format!("{:x}",Sha256::digest(fs::read(&executable).unwrap()))},
        "test_name":"gateway091::shared::server::p10b_host::loss_composition_tests::p10b_loss_composition09_actual_http_host"});
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
    assert_eq!(result["status"],"PASS_ACTUAL_P10B_LOSS_HOST_HTTP_SQLITE");
    assert_eq!(result["parent_full_gate"],"PENDING_PARENT_FULL_GATE");assert_eq!(result["native_client"],"NOT_RUN");
    println!("P10B_LOSS_HOST_COMPOSITION_ACTUAL_PASS evidence={} native=NOT_RUN full_gate=PENDING_PARENT_FULL_GATE",output.display());
}

#[test]
fn p10b_loss_composition09_actual_http_host(){
    if std::env::var_os("P08C_LATE_COMPOSITION_CONTROL").is_none(){parent();return;}
    let input=PathBuf::from(std::env::var_os("P08C_LATE_COMPOSITION_CONTROL").unwrap());
    let output=PathBuf::from(std::env::var_os("P08C_LATE_COMPOSITION_OUTPUT").unwrap());
    assert!(!output.exists());let raw=fs::read(input).unwrap();assert!(raw.len()<=65536);
    let value=crate::profile13_v2091::bounded_json(&raw,65536).unwrap();
    let keys=["schema","phase","config","users","barrier","arena_id"];
    assert_eq!(value.as_object().unwrap().len(),keys.len());assert!(keys.iter().all(|k|value.get(*k).is_some()));
    assert_eq!(value["schema"],"p10b-loss-composition.v1");assert_eq!(value["phase"],"abort_then_launch");
    let result=phase(&value);fs::write(output,serde_json::to_vec_pretty(&result).unwrap()).unwrap();
}
