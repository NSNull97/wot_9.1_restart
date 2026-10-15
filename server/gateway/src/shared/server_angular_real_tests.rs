//! Isolated actual producer/domain/ACK gate; explicitly not native/all-alive acceptance.
use super::*;
use super::super::fragiles;
use crate::map_drive_worker091::{self as drive,CatalogSpec,Scene,real_test_capture::{self as capture,Probe}};
use serde_json::{json,Value};
use std::path::PathBuf;
const DOMAIN:&str="1dca4febb0bc4921263682f82b927e26c33248c5b837a885f075245adf948f99";
const CATALOG:&str="41c0d9ccfd5b608a07e80a4eb68a3b6ed70bacffdd1444bb58c3f2ebb179bea9";
const BASE:&str="evidence/20261013-p05b-tracked-handling-01";
const CASES:[(&str,VehicleKind,&str,u32);3]=[
    ("ms1_graze",VehicleKind::Ms1,"312c6cf7c8a0609319e40da79557ce4d84e590bef990e0e241b62a833dba9cff",91),
    ("is7_graze",VehicleKind::Is7,"9876b8f09533bc813c7f3d9dd597d5d80d4efe03911075b5ce636163417e5313",73),
    ("is7_pivot",VehicleKind::Is7,"01196e542262095406e59cc8ba9b17f9679a63704ee0e197dca53b5bcddf854c",120)];

fn profile(kind:VehicleKind)->ram_proof::Profile{ram_proof::Profile::for_vehicle(kind)}
fn closed(v:&Value,keys:&[&str]){let o=v.as_object().unwrap();assert_eq!(o.len(),keys.len());assert!(keys.iter().all(|k|o.contains_key(*k)));}
fn no_reparse(path:&Path){for p in path.ancestors(){let m=fs::symlink_metadata(p).unwrap();assert!(!m.file_type().is_symlink());
    #[cfg(windows)] {use std::os::windows::fs::MetadataExt;assert_eq!(m.file_attributes()&0x400,0);}}}
fn owned(root:&Path,path:&Path)->PathBuf{no_reparse(path);let p=path.canonicalize().unwrap();assert!(p.starts_with(root));p}
fn pin(root:&Path,v:&Value,max:usize)->PathBuf{closed(v,&["path","bytes","sha256"]);let p=owned(root,Path::new(v["path"].as_str().unwrap()));
    let n=fs::metadata(&p).unwrap().len();assert!(n<=max as u64);assert_eq!(n,v["bytes"].as_u64().unwrap());
    assert_eq!(format!("{:x}",Sha256::digest(fs::read(&p).unwrap())),v["sha256"].as_str().unwrap());p}
fn file(dir:&Path,name:&str)->fs::File{fs::OpenOptions::new().write(true).create_new(true).open(dir.join(name)).unwrap()}
fn write_json(f:&mut fs::File,v:&Value){use std::io::Write;f.write_all(&serde_json::to_vec(v).unwrap()).unwrap();f.write_all(b"\n").unwrap();}

// Explicitly authored component tensor, reconstructed from the exact approved
// binding at identity body orientation. It is not claimed as a map readback.
fn synthetic_motion(p:ram_proof::Profile,v:[f32;3])->ram_proof::FullMotion {
    let b=p.binding();let[x,y,z,w]=b.inertia_rotation.map(f64::from);
    let r=[[1.-2.*(y*y+z*z),2.*(x*y-z*w),2.*(x*z+y*w)],
        [2.*(x*y+z*w),1.-2.*(x*x+z*z),2.*(y*z-x*w)],
        [2.*(x*z-y*w),2.*(y*z+x*w),1.-2.*(x*x+y*y)]];
    let d=b.principal.map(f64::from);
    let inertia=std::array::from_fn(|i|{let a=r[i/3];let c=r[i%3];((a[0]*d[0]*c[0]+a[1]*d[1]*c[1])+a[2]*d[2]*c[2])as f32});
    ram_proof::FullMotion{com:[0.;3],rotation:[0.,0.,0.,1.],motion:ram_proof::After{v,w:[0.;3]},inertia}
}
fn bootstrap(world:&mut World,map:&drive::MapSpec,spec:&CatalogSpec,record:&mut fs::File)->Vec<u32>{
    let p=profile(world.vehicle_kind());let initial=world.fragiles.as_ref().unwrap().catalog.objects.iter()
        .map(|o|o.object_id).filter(|id|*id!=3167).collect::<Vec<_>>();assert_eq!(initial.len(),1037);
    world.bind_contact_source(0,ram_proof::Source{session:1,generation:1,config_sha256:map.config_sha256.clone(),profile:p}).unwrap();
    for (batch,ids) in initial.chunks(32).enumerate(){
        let state=world.fragiles.as_ref().unwrap();let mut current=[0f32,0.,25.];let mut receipts=Vec::new();
        for(id_index,id)in ids.iter().enumerate(){let o=state.catalog.objects.iter().find(|o|o.object_id==*id).unwrap();
            let total=state.catalog.ram_response(o)==Some(ram_proof::FALLBACK);let mass=f64::from(p.mass());
            let energy=0.5*mass*f64::from(current[2]).powi(2);assert!(energy>=8000.);
            let next=if total{let factor=(1.-8000./energy).sqrt();current.map(|v|(f64::from(v)*factor)as f32)}
                else{[0.,0.,(f64::from(current[2]).powi(2)-16000./mass).max(0.).sqrt()as f32]};
            receipts.push(ram_proof::Receipt{object_id:*id,substep:1,order:id_index as u8+1,
                geometry:ram_proof::Geometry{point:[0.;3],normal:[0.,0.,1.]},mode:if total{ram_proof::Mode::Total}else{ram_proof::Mode::Normal},
                budget_after:ram_proof::After{v:next,w:[0.;3]},solver_after:ram_proof::After{v:[0.;3],w:[0.;3]},energy_j:8000,legacy:None,solver_branch:None});current=next;
        }
        let physical=Arc::new(ram_proof::FrameProof{profile:p,binding:p.binding(),witnesses:vec![ram_proof::Witness{substep:1,
            pre:synthetic_motion(p,[0.,0.,25.]),post:synthetic_motion(p,[0.;3])}],receipts});
        if batch==0 {for field in 0..5{let mut changed=(*physical).clone();match field{
            0=>changed.binding.inertia_rotation[2]=-0.,1=>changed.witnesses[0].pre.com[0]=-0.,
            2=>changed.receipts[0].geometry.point[0]=-0.,3=>changed.receipts[0].budget_after.v[0]=-0.,
            _=>changed.receipts[0].solver_after.w[0]=-0.}assert_ne!(*physical,changed,"physical proof equality must preserve signed zero");}}
        let frame=Arc::new(ram_proof::ContextFrame{proof:physical,context:ram_proof::Context{battle:world.id,slot:0,session:1,generation:1,
            seq:batch as u32+1,tick:180+(batch as u32+1)*6,config_sha256:map.config_sha256.clone(),catalog_sha256:CATALOG.into(),domain_sha256:DOMAIN.into(),
            scene_version:state.scene_version(),scene_sha256:state.historical_scene_hash(state.scene_version()).unwrap()}});
        let contacts=frame.proof.receipts.iter().enumerate().map(|(index,r)|model::VehicleContactInput{object_id:r.object_id,shooter:0,substep:r.substep,
            point:r.geometry.point,normal:r.geometry.normal,velocity:[0.,0.,25.],mass_kg:p.mass(),kind:"hull".into(),proof:Some(ram_proof::ContactProof{frame:frame.clone(),index})}).collect::<Vec<_>>();
        assert_eq!(world.apply_vehicle_contacts(&contacts).unwrap().len(),ids.len());
        write_json(record,&json!({"label":"SYNTHETIC_NOT_CONTACT_EVIDENCE","batch":batch,"full_context_frame_debug":format!("{frame:?}"),"removed_ids":ids}));
    }
    let state=world.fragiles.as_ref().unwrap();assert_eq!(state.vehicle_events.len(),1037);assert_eq!(state.removed_ids(),initial);
    assert_eq!(state.historical_scene_hash(1037).unwrap(),Scene::new(spec,&initial).unwrap().hash());initial
}
fn make_world(kind:VehicleKind,catalog:Arc<fragiles::Catalog>,spawn:[f32;3])->World{
    let now=Instant::now();let mut w=World::new_for_vehicle(925,now,MapId::Prohorovka,kind).unwrap();
    w.impact.bind_fragiles(catalog.clone()).unwrap();w.fragiles=Some(fragiles::State::new(catalog));
    for slot in 0..2{w.attach(model::Identity{account:format!("angular-pair-{slot}"),database:slot as i32+1,name:format!("pair{slot}")},slot as u32+1).unwrap();}
    w.start(now).unwrap();w.rebase_external_spawns([spawn;2]).unwrap();w
}
#[test]fn angular_paired_bootstrap_uses_checked_full_history_for_both_source_profiles(){
    let e=std::env::var_os("WOT_ANGULAR_EVIDENCE").map(PathBuf::from).unwrap_or_else(||Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").join(BASE));
    let local=e.parent().unwrap().parent().unwrap().canonicalize().unwrap();let catalog=Arc::new(fragiles::Catalog::load(&local,&e.join("night-angular-export01/catalog/manifest.json"),DOMAIN).unwrap());
    let spec=CatalogSpec::load(&local,&e.join("night-angular-export01/catalog/physics-removals.json"),CATALOG).unwrap();
    let target=PathBuf::from(std::env::var_os("CARGO_TARGET_DIR").expect("owned canonical/private target directory"));no_reparse(&target);
    let out=target.join(format!("angular-bootstrap-component-{}-{}",std::process::id(),std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()));fs::create_dir(&out).unwrap();
    for (name,kind,config,_) in CASES.into_iter().take(2){let p=profile(kind);
        let path=e.join(format!("night-angular-integration01/paired-pools/{}-graze-pool.json",kind.label()));
        let pool=drive::Pool::load(&local,&path).unwrap();assert_eq!(pool.sha256,if name=="ms1_graze"{"8386381562420f9b0ad9edcc5395ffecba1f80c9380521a795144f26e24bbf29"}else{"738d2da23683ef46a0a88a0bd0b5aeaef03bc65d44a3941de9f1eefec2fad064"});
        let map=selected_pool_map(&pool,MapId::Prohorovka).unwrap();assert_eq!(map.config_sha256,config);assert_eq!(capture::verified_profile(&pool,map).unwrap(),p);
        let mut world=make_world(kind,catalog.clone(),map.spawn);
        let mut record=file(&out,&format!("{}-synthetic.jsonl",kind.label()));bootstrap(&mut world,map,&spec,&mut record);
        assert_eq!(world.impact.contact_source_history().len(),1);assert_eq!(world.impact.events().len(),1037);
    }
}

// These waits belong to the harness, not the drive clock. While a survivor is
// active they must service the real runtime; wall time must not disappear into
// a PID/exit busy wait and then masquerade as a production cadence failure.
fn cooperative_wait<S,T>(state:&mut S,deadline:Instant,mut check:impl FnMut(&S)->Option<T>,mut pump:impl FnMut(&mut S))->T{
    loop {assert!(Instant::now()<deadline,"cooperative wait deadline");if let Some(value)=check(state){return value;}pump(state);}
}
struct TimedLog {file:fs::File,origin:Instant,records:u32,last_poll:Option<Instant>}
impl TimedLog {
    fn new(path:&Path)->Self{Self{file:file(path,"runtime.jsonl"),origin:Instant::now(),records:0,last_poll:None}}
    fn ns(&self,at:Instant)->u64{u64::try_from(at.duration_since(self.origin).as_nanos()).unwrap()}
    fn write(&mut self,mut row:Value){assert!(self.records<100_000,"bounded timing log");
        row["monotonic_ns"]=json!(self.ns(Instant::now()));row["record"]=json!(self.records);self.records+=1;write_json(&mut self.file,&row);}
}
#[test]fn angular_paired_cooperative_wait_services_pending_work_and_enforces_deadline(){
    // No worker: completion becomes available only after servicing the pending
    // side three times. An already complete or expired wait must not pump.
    let mut calls=0;let value=cooperative_wait(&mut calls,Instant::now()+Duration::from_secs(1),
        |n|(*n==3).then_some(17),|n|*n+=1);assert_eq!((value,calls),(17,3));
    assert_eq!(cooperative_wait(&mut calls,Instant::now()+Duration::from_secs(1),|_|Some(23),|_|panic!("unexpected pump")),23);
    let failure=std::panic::catch_unwind(||cooperative_wait(&mut (),Instant::now(),|_|None::<()>,|_|panic!("expired wait pumped")));
    let error=failure.unwrap_err();assert_eq!(error.downcast_ref::<&str>(),Some(&"cooperative wait deadline"));
}
fn exited(probe:&Probe,deadline:Instant)->Value{loop{if let Some(e)=probe.exit().unwrap(){if probe.io_complete().unwrap(){return e;}}assert!(Instant::now()<deadline,"owned exit and both I/O completion deadline");std::thread::sleep(Duration::from_millis(2));}}
fn launch(runtime:&mut IntegratedRuntime,world:&World,slot:usize,generation:u32,scene:Scene,probes:&mut Vec<Probe>,log:&mut TimedLog,deadline:Instant){
    assert!(Instant::now()<deadline,"deadline expired before owned launch");
    let map=runtime.map().unwrap();probes.push(capture::register(&map.config_sha256,generation).unwrap());let i=probes.len()-1;
    log.write(json!({"event":"launch_sync_begin","slot":slot,"generation":generation}));let start=Instant::now();
    let launched=drive::Worker::launch_with_catalog(runtime.pool.clone(),map.clone(),generation,Instant::now(),None,runtime.catalog.clone().unwrap(),scene);
    log.write(json!({"event":"launch_sync_end","slot":slot,"generation":generation,"duration_ns":start.elapsed().as_nanos(),"error":launched.as_ref().err().map(ToString::to_string)}));
    runtime.workers[slot]=Some(launched.unwrap());let worker=runtime.workers[slot].as_ref().unwrap();probes[i].attach(worker).unwrap();
    runtime.worker_sessions[slot]=world.actors[slot].session;log.write(json!({"event":"launch_async","slot":slot,"generation":generation,"config_sha256":map.config_sha256,"spawn_override":null}));
}
fn loop_step(runtime:&mut IntegratedRuntime,world:&mut World,deadline:Instant,log:&mut TimedLog){
    assert!(Instant::now()<deadline,"bounded paired runtime deadline");let now=Instant::now();
    log.write(json!({"event":"poll_begin","since_previous_poll_ns":log.last_poll.map(|last|now.duration_since(last).as_nanos()),"seq":runtime.contact_sequences}));
    log.last_poll=Some(now);let result=runtime.step(world,now);
    log.write(json!({"event":"poll","started_ns":log.ns(now),"duration_ns":now.elapsed().as_nanos(),"tick":world.tick,"scene":world.scene_version(),"seq":runtime.contact_sequences,
        "worker_ready":runtime.workers.iter().map(|w|w.as_ref().is_some_and(drive::Worker::ready)).collect::<Vec<_>>(),"anchored":runtime.anchored,
        "staged":runtime.staged.is_some(),"pose_pending":runtime.pose_pending,"ready":runtime.ready_for_native(),"error":result.as_ref().err().map(ToString::to_string)}));
    result.unwrap();assert!(runtime.contact_sequences[0]<=250,"survivor advance budget");std::thread::sleep(Duration::from_millis(2));
}
fn wait_pid(runtime:&mut IntegratedRuntime,world:&mut World,slot:usize,deadline:Instant,log:&mut TimedLog){
    let deadline=deadline.min(Instant::now()+Duration::from_secs(30));log.write(json!({"event":"pid_wait_begin","slot":slot}));
    let pid=cooperative_wait(&mut(runtime,world,&mut *log),deadline,
        |(runtime,_,_)|runtime.workers[slot].as_ref().unwrap().process_id(),
        |(runtime,world,log)|loop_step(runtime,world,deadline,log));
    log.write(json!({"event":"pid_observed","slot":slot,"pid":pid}));
}
fn run_case(local:&Path,binding:&Value,case:(&str,VehicleKind,&str,u32),out:&Path,probes:&mut Vec<Probe>,global:Instant)->Value{
    let(name,kind,config,expected)=case;let pivot=name.ends_with("pivot");let deadline=global.min(Instant::now()+Duration::from_secs(90));
    let path=pin(local,&binding["pools"][name],65536);let pool=Arc::new(drive::Pool::load(local,&path).unwrap());assert_eq!(pool.vehicle_kind(),kind);
    let map=selected_pool_map(&pool,MapId::Prohorovka).unwrap().clone();assert_eq!(map.config_sha256,config);
    assert_eq!(capture::verified_profile(&pool,&map).unwrap(),profile(kind));
    let domain=pin(local,&binding["domain"],1024*1024);let catalog=Arc::new(fragiles::Catalog::load(local,&domain,DOMAIN).unwrap());
    let catalog_path=pin(local,&binding["catalog"],1024*1024);let spec=CatalogSpec::load(local,&catalog_path,CATALOG).unwrap();validate_catalog_projection(&catalog,&spec,MapId::Prohorovka).unwrap();
    let mut world=make_world(kind,catalog,map.spawn);let mut seeded=file(out,"synthetic-history.jsonl");let initial=bootstrap(&mut world,&map,&spec,&mut seeded);drop(seeded);
    let scene=Scene::new(&spec,&initial).unwrap();let mut runtime=IntegratedRuntime::new_for_map(pool,MapId::Prohorovka);runtime.catalog=Some(spec.clone());runtime.started=true;runtime.generations=[1,1];
    let mut log=TimedLog::new(out);for slot in 0..2{launch(&mut runtime,&world,slot,slot as u32+2,scene.clone(),probes,&mut log,deadline);}
    for slot in 0..2{wait_pid(&mut runtime,&mut world,slot,deadline,&mut log);}
    while !runtime.ready_for_native()||!runtime.anchored.iter().all(|v|*v){loop_step(&mut runtime,&mut world,deadline,&mut log);assert_eq!(runtime.contact_sequences,[0,0]);}
    let input=model::Input{throttle:if pivot{0}else{1},steer:if pivot{1}else{0},speed_percent:100};
    for slot in 0..2{world.set_ready(slot,slot as u32+1).unwrap();world.actors[slot].input=input;}
    let before_events=world.impact.events().len();let mut staged_once=false;let mut prepared_seq=0;let mut old_slot1=None;
    while !staged_once {let before=world.clone();loop_step(&mut runtime,&mut world,deadline,&mut log);assert!(runtime.contact_sequences.iter().all(|n|*n<=120));
        if let Some(candidate)=runtime.staged.clone(){
            assert_eq!(world.fragiles,before.fragiles);assert_eq!(world.actors,before.actors);assert_eq!(world.impact.events().len(),before_events);assert_eq!(world.scene_version(),1037);
            assert_eq!(runtime.contact_sequences[0],runtime.contact_sequences[1]);prepared_seq=runtime.contact_sequences[0];if !pivot{assert_eq!(prepared_seq,expected);}
            let frames=probes.iter().take(2).map(|p|p.frames().unwrap().into_iter().find(|f|f.seq==prepared_seq).unwrap()).collect::<Vec<_>>();
            let first=frames[0].angular_proof.as_ref().unwrap();assert_eq!(Some(first),frames[1].angular_proof.as_ref());assert_eq!(first.receipts.len(),1);
            let r=&first.receipts[0];assert_eq!(r.object_id,3167);assert_eq!(r.mode,if pivot{ram_proof::Mode::Angular}else{ram_proof::Mode::Total});
            if pivot{assert_eq!(r.solver_branch,Some(ram_proof::SolverBranch::Applied));}
            let event=candidate.fragiles.as_ref().unwrap().vehicle_events.last().unwrap();assert_eq!(event.object_id,3167);
            assert_eq!(event.proof.as_ref().unwrap().frame.proof.as_ref(),first.as_ref());assert_eq!(candidate.impact.events().len(),before_events+1);
            let mut context=event.proof.as_ref().unwrap().frame.context.clone();context.slot=1;context.session=2;context.generation=3;
            old_slot1=Some(ram_proof::ContactProof{frame:Arc::new(ram_proof::ContextFrame{context,proof:frames[1].angular_proof.clone().unwrap()}),index:0});
            log.write(json!({"event":"validated_pair_proofs","slot0":format!("{:?}",event.proof.as_ref().unwrap()),"slot1":format!("{:?}",old_slot1.as_ref().unwrap())}));
            assert_eq!(candidate.fragiles.as_ref().unwrap().vehicle_events.len(),1038);let committed=Scene::new(&spec,&candidate.fragiles.as_ref().unwrap().removed_ids()).unwrap();
            for w in runtime.workers.iter_mut().flatten(){assert_eq!(w.prepared_ids(),&[3167]);assert!(w.advance(drive::Input::STOP,Instant::now()).is_err());}
            while runtime.workers[0].as_ref().unwrap().catalog_scene()!=Some(&committed){assert!(Instant::now()<deadline);
                assert!(runtime.workers[0].as_mut().unwrap().poll(Instant::now()).unwrap().is_none());std::thread::sleep(Duration::from_millis(2));}
            assert_ne!(runtime.workers[1].as_ref().unwrap().catalog_scene(),Some(&committed));assert_eq!(world.fragiles,before.fragiles);assert_eq!(world.actors,before.actors);assert!(!runtime.ready_for_native());
            log.write(json!({"event":"only_slot0_ack_consumed","scene":world.scene_version(),"seq":prepared_seq,"world_unchanged":true}));
            while runtime.staged.is_some(){assert!(Instant::now()<deadline);runtime.finish_catalog(&mut world,Instant::now()).unwrap();std::thread::sleep(Duration::from_millis(2));}
            assert_eq!(world.fragiles,candidate.fragiles);assert_eq!(world.actors,candidate.actors);assert_eq!(world.scene_version(),1038);
            assert!(runtime.workers.iter().flatten().all(|w|w.catalog_scene()==Some(&committed)&&w.prepared_ids().is_empty()));staged_once=true;
            log.write(json!({"event":"both_ack_committed","scene":world.scene_version(),"seq":prepared_seq}));
        }
    }
    let history=world.fragiles.clone();let trace_count=world.impact.events().len();
    world.actors[0].input=model::Input::STOP;let identity=world.actors[1].identity.clone();world.detach(2).unwrap();world.revoke_contact_source(1).unwrap();
    log.write(json!({"event":"clear_drop_begin","slot":1}));runtime.clear_slot(1);log.write(json!({"event":"clear_drop_end","slot":1}));
    let exit_deadline=deadline.min(Instant::now()+Duration::from_secs(8));log.write(json!({"event":"exit_wait_begin","slot":1}));
    let exit=cooperative_wait(&mut(&mut runtime,&mut world,&mut log),exit_deadline,
        |_|probes[1].exit().unwrap().filter(|_|probes[1].io_complete().unwrap()),
        |(runtime,world,log)|{loop_step(runtime,world,exit_deadline,log);assert!(world.actors[1].session.is_none());
            assert_eq!(world.fragiles,history);assert_eq!(world.impact.events().len(),trace_count);assert!(runtime.contact_sequences[0]<=250);});
    log.write(json!({"event":"exit_wait_end","slot":1,"exit":exit}));assert_eq!(exit,json!({"forced":false,"code":0,"reaped":true}));
    assert_eq!(world.attach(identity,3).unwrap(),1);world.reset_external_spawn(1,map.spawn).unwrap();
    let committed=Scene::new(&spec,&world.fragiles.as_ref().unwrap().removed_ids()).unwrap();launch(&mut runtime,&world,1,5,committed.clone(),probes,&mut log,deadline);
    wait_pid(&mut runtime,&mut world,1,deadline,&mut log);
    while !runtime.ready_for_native()||!runtime.anchored[1]{loop_step(&mut runtime,&mut world,deadline,&mut log);assert!(!world.actors[1].ready);assert_eq!(world.fragiles,history);}
    assert!(!world.actors[1].ready);assert_eq!(runtime.contact_sequences[1],0);assert_eq!(runtime.workers[1].as_ref().unwrap().catalog_scene(),Some(&committed));
    log.write(json!({"event":"replacement_ready_anchored","slot":1,"seq":runtime.contact_sequences,"scene":world.scene_version()}));
    let warmup_stop=u32::from(runtime.workers[1].as_ref().unwrap().pending());
    world.set_ready(1,3).unwrap();world.actors[1].input=input;let target_seq=expected+warmup_stop;
    while runtime.contact_sequences[1]<target_seq{loop_step(&mut runtime,&mut world,deadline,&mut log);assert_eq!(world.fragiles,history);assert_eq!(world.impact.events().len(),trace_count);
        assert!(runtime.contact_sequences[0]<=250);assert!(!runtime.blocked());}
    for f in probes[2].frames().unwrap(){assert!(f.fractures.is_empty());assert!(f.object_contacts.iter().all(|c|c.object_id!=3167));assert_eq!(f.scene_version,1038);}
    let proof=old_slot1.unwrap();let old=proof.receipt().unwrap();let rejected=model::VehicleContactInput{object_id:old.object_id,shooter:1,substep:old.substep,point:old.geometry.point,normal:old.geometry.normal,
        velocity:proof.frame.proof.witness(old.substep).unwrap().pre.motion.v,mass_kg:map.mass_kg,kind:"hull".into(),proof:Some(proof)};
    assert!(world.apply_vehicle_contacts(&[rejected]).is_err());assert_eq!(world.fragiles,history);assert_eq!(world.impact.events().len(),trace_count);
    let source_history=world.impact.contact_source_history().len();assert_eq!(source_history,2);
    log.write(json!({"event":"final_drop_begin"}));drop(runtime);log.write(json!({"event":"final_drop_end"}));
    json!({"status":"PASS_REAL_ISOLATED_TYPED_PAIRED_ACK_REJOIN","case":name,"pool":binding["pools"][name],"config_sha256":config,
        "prepared_seq":prepared_seq,"rejoin_commanded_advances":expected,"rejoin_warmup_stop_advances":warmup_stop,"rejoin_last_consumed_seq":target_seq,"synthetic_prior_events":1037,"synthetic_label":"SYNTHETIC_NOT_CONTACT_EVIDENCE",
        "actual_events":1,"both_source_proofs_equal":true,"source_history_entries":source_history,"timing_clock":"monotonic nanoseconds relative to runtime log creation",
        "native":"NOT_RUN","all_alive":"NOT_RUN","full_passage":"NOT_ASSERTED"})
}

fn command_audit(probe:&Probe,case:&str,index:usize,result:&Value)->Value{
    let(requests,replies)=probe.rows().unwrap();let requests=requests.iter().map(|r|serde_json::from_slice::<Value>(r).unwrap()).collect::<Vec<_>>();
    assert_eq!(requests[0]["op"],"restore_scene");assert_eq!(requests.iter().filter(|r|r["op"]=="restore_scene").count(),1);
    let advances=requests.iter().filter(|r|r["op"]=="advance").collect::<Vec<_>>();let parsed=probe.frames().unwrap();
    let command=if case.ends_with("pivot"){json!({"throttle":0,"steer":1,"brake":false})}else{json!({"throttle":1,"steer":0,"brake":false})};
    let stop=json!({"throttle":0,"steer":0,"brake":true});let prepared=result["prepared_seq"].as_u64().unwrap();
    let warmup=if index==2{result["rejoin_warmup_stop_advances"].as_u64().unwrap()}else{0};
    let required=if index==2{result["rejoin_last_consumed_seq"].as_u64().unwrap()}else{prepared};
    for(i,row)in advances.iter().enumerate(){assert_eq!(row["version"],6);assert_eq!(row["seq"],i as u64+1);assert_eq!(row["ticks"],6);
        let expected=if (index==0&&i as u64>=prepared)||(index==2&&(i as u64)<warmup){&stop}else{&command};assert_eq!(&row["input"],expected);}
    assert!(advances.len()as u64>=required);if index==1{assert_eq!(advances.len()as u64,prepared);}if index==2{assert!(advances.len()as u64<=required+1);}
    let parsed_advance=parsed.iter().filter(|f|f.seq>0).count();let raw_advance=replies.iter().map(|r|serde_json::from_slice::<Value>(r).unwrap()).filter(|v|v["event"]=="state"||v["event"]=="prepared").count();
    assert!(raw_advance>=parsed_advance&&raw_advance<=parsed_advance+1);
    json!({"request_count":requests.len(),"advance_requests":advances.len(),"raw_reply_count":replies.len(),"parsed_frames":parsed.len(),
        "validated_advance_frames":parsed_advance,"teardown_unconsumed_advance_replies":raw_advance-parsed_advance,"teardown_status":"NOT_CONSUMED_NOT_PUBLISHED",
        "warmup_stop":warmup,"command_sequence_checked":true})
}

#[test]
#[ignore="requires reviewed three-pool binding and explicit bounded actual-worker GO"]
fn angular_actual_pair_both_ack_and_fresh_rejoin(){
    let binding_path=PathBuf::from(std::env::var_os("WOT_ANGULAR_PAIR_BINDING").expect("approved binding"));no_reparse(&binding_path);
    assert!(fs::metadata(&binding_path).unwrap().len()<=65536);let raw=fs::read(&binding_path).unwrap();
    assert_eq!(format!("{:x}",Sha256::digest(&raw)),std::env::var("WOT_ANGULAR_PAIR_BINDING_SHA256").unwrap());
    let binding:Value=serde_json::from_slice(&raw).unwrap();closed(&binding,&["version","local_root","domain","catalog","pools"]);assert_eq!(binding["version"],1);
    closed(&binding["pools"],&["ms1_graze","is7_graze","is7_pivot"]);let local=PathBuf::from(binding["local_root"].as_str().unwrap()).canonicalize().unwrap();owned(&local,&binding_path);
    let out=PathBuf::from(std::env::var_os("WOT_ANGULAR_PAIR_OUT").expect("fresh owned directory"));assert!(out.is_absolute());owned(&local,out.parent().unwrap());fs::create_dir(&out).unwrap();
    let global=Instant::now()+Duration::from_secs(300);let mut results=Vec::new();
    for case in CASES {assert!(Instant::now()<global);let dir=out.join(case.0);fs::create_dir(&dir).unwrap();let mut probes=Vec::new();
        let run=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||run_case(&local,&binding,case,&dir,&mut probes,global)));
        let mut cleanup=Vec::new();let mut raw_pins=Vec::new();let mut errors=Vec::new();let mut observations=Vec::new();
        for(i,p)in probes.iter().enumerate(){let exit=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||exited(p,Instant::now()+Duration::from_secs(8))));
            match exit{Ok(e)=>{if e!=json!({"forced":false,"code":0,"reaped":true}){errors.push(format!("child{i} unclean exit {e}"));}cleanup.push(e);},Err(_)=>errors.push(format!("child{i} exit evidence missing"))}
            let child=dir.join(format!("child{i}"));fs::create_dir(&child).unwrap();match p.save(&child){Ok(v)=>raw_pins.push(v),Err(e)=>errors.push(e.to_string())}
            if let Ok(result)=&run{match std::panic::catch_unwind(std::panic::AssertUnwindSafe(||command_audit(p,case.0,i,result))){Ok(v)=>observations.push(v),Err(_)=>errors.push(format!("child{i} actual command sequence mismatch"))}}
            if p.snapshot()["error"]!=Value::Null{errors.push(p.snapshot().to_string());}if let Err(e)=p.unregister(){errors.push(e.to_string());}
        }
        let result=match run{Ok(v)=>v,Err(e)=>json!({"status":"FAIL","panic":e.downcast_ref::<String>().cloned().or_else(||e.downcast_ref::<&str>().map(|s|s.to_string())).unwrap_or_else(||"nonstring panic".into())})};
        let pass=result["status"]=="PASS_REAL_ISOLATED_TYPED_PAIRED_ACK_REJOIN"&&errors.is_empty()&&probes.len()==3;
        let row=json!({"pass":pass,"result":result,"raw":raw_pins,"cleanup":cleanup,"observations":observations,"errors":errors});write_json(&mut file(&dir,"result.json"),&row);results.push(row);if !pass{break;}
    }
    let pass=results.len()==3&&results.iter().all(|r|r["pass"]==true);write_json(&mut file(&out,"result.json"),&json!({"pass":pass,"binding":binding,"cases":results}));assert!(pass,"retained actual paired gate failure");
}
