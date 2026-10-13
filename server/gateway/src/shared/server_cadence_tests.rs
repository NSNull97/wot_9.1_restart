//! Controlled IPC clock regression plus a separately pinned actual-worker
//! cadence smoke. Neither establishes native-client presentation acceptance.
use super::*;
use super::super::fragiles;
use crate::map_drive_worker091::{self as drive, controlled_ipc, CatalogSpec, Scene};
use serde_json::{json, Value};

struct Fixture {
    world: World,
    runtime: IntegratedRuntime,
    peers: [controlled_ipc::Peer; model::CAPACITY],
    map: drive::MapSpec,
    spec: CatalogSpec,
    origins: [[f32;3]; model::CAPACITY],
}

fn fixture(now: Instant) -> Fixture {
    let catalog=fragiles::tests::contact_catalog();
    let mut world=model::tests::world(now);
    world.impact.bind_fragiles(catalog.clone()).unwrap();
    world.fragiles=Some(fragiles::State::new(catalog.clone()));
    for actor in &mut world.actors { actor.input=model::Input { throttle:1,steer:0 }; }
    let origins=std::array::from_fn(|slot|world.actors[slot].position);
    let manifest=json!({"version":3,"profile":"test_lab","map":"01_karelia","contacts":true,
        "physics_manifest_sha256":MapId::Karelia.spec().physics_manifest_sha256,
        "projectile_manifest_sha256":MapId::Karelia.spec().projectile_manifest_sha256,
        "objects":catalog.objects.iter().map(|o|json!({"object_id":o.object_id,"instance_id":o.instance_id,
            "first_triangle":o.physics_first_triangle,"triangle_count":o.physics_triangle_count,
            "object_revision":o.object_revision,"kind":if matches!(o.kind,fragiles::ObjectKind::Tree){"tree"}else{"fragile"}
        })).collect::<Vec<_>>()});
    let raw=serde_json::to_vec(&manifest).unwrap();
    static NEXT:std::sync::atomic::AtomicUsize=std::sync::atomic::AtomicUsize::new(0);
    let directory=std::env::temp_dir().join(format!("wot091-cadence-{}-{}",std::process::id(),
        NEXT.fetch_add(1,std::sync::atomic::Ordering::Relaxed)));
    fs::create_dir(&directory).unwrap();let path=directory.join("catalog.json");fs::write(&path,&raw).unwrap();
    let spec=CatalogSpec::load(&directory,&path,&format!("{:x}",Sha256::digest(&raw))).unwrap();
    fs::remove_file(&path).unwrap();fs::remove_dir(&directory).unwrap();
    let map=drive::tests::map();
    let mut runtime=IntegratedRuntime::new(controlled_ipc::pool(map.clone()));
    runtime.catalog=Some(spec.clone());runtime.started=true;
    let scene=Scene::new(&spec,&[]).unwrap();
    let peers=std::array::from_fn(|slot| {
        let (worker,peer)=controlled_ipc::ready(map.clone(),slot as u32+2,spec.clone(),scene.clone(),now);
        runtime.workers[slot]=Some(worker);runtime.worker_sessions[slot]=world.actors[slot].session;
        runtime.anchored[slot]=true;runtime.poses[slot]=Some((origins[slot],world.actors[slot].direction,0.));peer
    });
    Fixture { world,runtime,peers,map,spec,origins }
}

impl Fixture {
    fn step(&mut self, now: Instant) { self.runtime.step(&mut self.world,now).unwrap(); }
    fn dispatch(&mut self, now: Instant) {
        self.step(now);
        for peer in &self.peers { assert_eq!(peer.request()["seq"],1); }
    }
    fn pair(&self, now: Instant, seq:u32) {
        for slot in 0..2 { self.peers[slot].reply(now,&self.frame(slot,seq)); }
    }
    fn ack(&self, slot:usize, request:&Value, now:Instant) {
        assert_eq!(request["op"],"sync_removed");let mut ack=request.clone();
        let object=ack.as_object_mut().unwrap();object.remove("op");
        object.insert("event".into(),json!("scene_synced"));
        object.insert("tick".into(),json!(180+request["advance_seq"].as_u64().unwrap()*6));
        self.peers[slot].reply(now,&ack);
    }
    fn frame(&self,slot:usize,seq:u32)->Value {
        let worker=self.runtime.workers[slot].as_ref().unwrap();let scene=worker.catalog_scene().unwrap();
        let mut position=self.origins[slot];position[0]+=seq as f32;
        json!({"version":4,"event":"state","seq":seq,"tick":180+seq*6,"settle_ticks":180,
            "map":self.map.asset,"config_sha256":self.map.config_sha256,"generation":worker.generation,
            "catalog_sha256":self.spec.sha256(),"contacts":true,"scene_version":scene.version(),"scene_sha256":scene.hash(),
            "state":{"position":position,"direction":[0.,0.,0.],"speed":10.,"rspeed":0.,"contacts":6,
            "linear_velocity":[10.,0.,0.],"angular_velocity":[0.,0.,0.],"wheel_contact_masks":[63,63,63,63,63,63],
            "object_contacts":[]}})
    }
}

#[test]
fn early_pair_waits_for_native_bucket_without_redispatch_or_aim_from_cached_pose() {
    let start=Instant::now();let mut f=fixture(start);
    f.world.apply(0,1,&[model::Command::Aim(super::super::aim::Intent::Hold{yaw:1.,pitch:0.})],start).unwrap();
    f.dispatch(start);let before=f.world.actors.clone();
    f.pair(start+Duration::from_millis(1),1);
    for millis in [1,2,50,99] {
        f.step(start+Duration::from_millis(millis));
        assert_eq!(f.world.tick,1000);assert_eq!(f.world.actors,before);
        assert_eq!(f.runtime.pose_pending,[true,true]);
        assert!(f.peers.iter().all(controlled_ipc::Peer::no_request));
    }
    f.step(start+drive::STEP);
    assert_eq!(f.world.tick,1001);assert_eq!(f.world.actors[0].position[0],f.origins[0][0]+1.);
    assert!(f.world.actors[0].aim.yaw>before[0].aim.yaw);
    for peer in &f.peers { assert_eq!(peer.request()["seq"],2); }
    let published=f.world.actors.clone();
    // Missing next reply: no fake native motion tick or advancing turret from
    //the old source, even though the wall clock enters another100ms bucket.
    f.step(start+Duration::from_millis(220));
    assert_eq!(f.world.tick,1001);assert_eq!(f.world.actors,published);
    assert!(f.peers.iter().all(controlled_ipc::Peer::no_request));
}

#[test]
fn delayed_peer_and_fast_catchup_never_overwrite_or_skip_an_unpublished_source() {
    let start=Instant::now();let mut f=fixture(start);f.dispatch(start);
    f.peers[0].reply(start+Duration::from_millis(1),&f.frame(0,1));
    for millis in [1,99,100,199] {
        f.step(start+Duration::from_millis(millis));assert_eq!(f.world.tick,1000);
        assert_eq!(f.runtime.contact_sequences,[1,0]);
        assert!(f.peers.iter().all(controlled_ipc::Peer::no_request));
    }
    f.peers[1].reply(start+Duration::from_millis(200),&f.frame(1,1));f.step(start+Duration::from_millis(200));
    assert_eq!(f.world.tick,1002);
    for peer in &f.peers { assert_eq!(peer.request()["seq"],2); }
    f.pair(start+Duration::from_millis(201),2);
    for millis in [201,202,250,299] {
        f.step(start+Duration::from_millis(millis));assert_eq!(f.world.tick,1002);
        assert_eq!(f.world.actors[0].position[0],f.origins[0][0]+1.);
        assert_eq!(f.runtime.pose_pending,[true,true]);
        assert!(f.peers.iter().all(controlled_ipc::Peer::no_request));
    }
    f.step(start+Duration::from_millis(300));assert_eq!(f.world.tick,1003);
    for slot in 0..2 {
        assert_eq!(f.world.actors[slot].position[0],f.origins[slot][0]+2.);
        assert_eq!(f.peers[slot].request()["seq"],3);
        assert_eq!(f.runtime.dispatched[slot],Some(start+Duration::from_millis(200)));
    }
}

#[test]
fn persistent_slow_worker_is_bounded_and_overload_does_not_publish_a_last_success() {
    //Each actual reply takes200ms, within the existing500ms IPC timeout.
    //Accumulating logical debt reaches500ms, then fails rather than silently
    //slowing simulation forever or accepting unlimited catch-up requests.
    let start=Instant::now();let mut f=fixture(start);f.dispatch(start);
    for seq in 1..=5 {
        let now=start+Duration::from_millis(seq as u64*200);f.pair(now,seq);f.step(now);
        assert_eq!(f.world.actors[0].position[0],f.origins[0][0]+seq as f32);
        for peer in &f.peers { assert_eq!(peer.request()["seq"],seq+1); }
    }
    let before=f.world.actors.clone();let tick=f.world.tick;let now=start+Duration::from_millis(1200);
    f.pair(now,6);let error=f.runtime.step(&mut f.world,now).unwrap_err();
    assert_eq!(error.kind(),io::ErrorKind::TimedOut);assert!(error.to_string().contains("logical deadline lag"));
    assert_eq!(f.world.tick,tick);assert_eq!(f.world.actors,before);
    assert!(f.peers.iter().all(controlled_ipc::Peer::no_request));
}

#[test]
fn scene_ack_pause_rebases_deadlines_and_retains_same_bucket_source() {
    let start=Instant::now();let mut f=fixture(start);f.dispatch(start);
    let at=start+Duration::from_millis(90);let mut frame=f.frame(0,1);
    frame["state"]["object_contacts"]=json!([{"object_id":1513,"kind":"hull","substep":1,
        "point":[0.,0.,0.],"normal":[0.,0.,1.],"velocity":[0.,0.,2.]}]);
    f.peers[0].reply(at,&frame);f.peers[1].reply(at,&f.frame(1,1));f.step(at);
    assert!(f.runtime.blocked());assert_eq!(f.world.tick,1000);assert_eq!(f.runtime.pose_pending,[true,true]);
    let requests=[f.peers[0].request(),f.peers[1].request()];
    f.ack(0,&requests[0],start+Duration::from_millis(500));f.step(start+Duration::from_millis(500));
    assert_eq!(f.world.scene_version(),0);assert_eq!(f.world.tick,1000);
    f.ack(1,&requests[1],start+Duration::from_millis(590));f.step(start+Duration::from_millis(590));
    assert_eq!(f.world.scene_version(),1);assert_eq!(f.world.tick,1000);
    assert_eq!(f.runtime.dispatched,[Some(start+Duration::from_millis(500));2]);
    f.step(start+Duration::from_millis(591));assert_eq!(f.world.tick,1005);
    for slot in 0..2 { assert_eq!(f.world.actors[slot].position[0],f.origins[slot][0]+1.); }
    assert!(f.peers.iter().all(controlled_ipc::Peer::no_request));
    f.step(start+Duration::from_millis(600));
    for peer in &f.peers { assert_eq!(peer.request()["seq"],2); }
    assert_eq!(f.world.fragiles.as_ref().unwrap().vehicle_events.len(),1);
}

#[test]
fn initial_native_wait_creates_no_historical_dispatch_debt() {
    let start=Instant::now();let mut f=fixture(start);f.world.actors[1].ready=false;
    for millis in [0,100,2000] {
        f.step(start+Duration::from_millis(millis));assert_eq!(f.world.tick,1000);
        assert!(f.peers.iter().all(controlled_ipc::Peer::no_request));
    }
    f.world.set_ready(1,2).unwrap();f.step(start+Duration::from_millis(2055));
    for peer in &f.peers { assert_eq!(peer.request()["seq"],1); }
    assert_eq!(f.runtime.dispatched,[Some(start+Duration::from_millis(2000));2]);
}

#[test]
fn clearing_a_slot_revokes_held_source_and_parked_world_keeps_its_clock() {
    let start=Instant::now();let mut f=fixture(start);f.dispatch(start);
    f.peers[0].reply(start+Duration::from_millis(1),&f.frame(0,1));f.step(start+Duration::from_millis(1));
    assert!(f.runtime.pose_pending[0]);f.world.detach(1).unwrap();f.world.detach(2).unwrap();
    let parked=f.world.actors.clone();f.step(start+Duration::from_millis(100));
    assert_eq!(f.runtime.pose_pending,[false,false]);assert_eq!(f.runtime.dispatched,[None,None]);
    assert!(f.runtime.workers.iter().all(Option::is_none));
    assert_eq!(f.world.actors,parked);assert_eq!(f.world.tick,1001);
    f.step(start+Duration::from_millis(200));assert_eq!(f.world.tick,1002);
}

#[test]
fn rejoin_ack_wait_rebases_survivor_without_waiting_for_native_readiness() {
    let start=Instant::now();let mut f=fixture(start);
    f.world.apply_vehicle_contacts(&[model::VehicleContactInput {object_id:1513,substep:1,point:[0.;3],
        normal:[0.,0.,1.],velocity:[0.,0.,2.],mass_kg:f.map.mass_kg,kind:"hull".into(),shooter:0,proof:None}]).unwrap();
    f.world.advance(start+drive::STEP).unwrap();
    let (worker,peer)=controlled_ipc::ready(f.map.clone(),2,f.spec.clone(),Scene::new(&f.spec,&[1513]).unwrap(),start);
    f.runtime.workers[0]=Some(worker);f.peers[0]=peer;
    f.world.actors[1].ready=false;f.world.actors[1].input=model::Input::STOP;
    let at=start+drive::STEP;
    f.runtime.workers[0].as_mut().unwrap().advance(drive::Input::STOP,at).unwrap();
    f.runtime.dispatched[0]=Some(at);assert_eq!(f.peers[0].request()["seq"],1);
    f.peers[0].reply(at+Duration::from_millis(1),&f.frame(0,1));f.step(at+Duration::from_millis(2));
    let restore=f.peers[1].request();assert_eq!(restore["op"],"sync_removed");
    f.ack(1,&restore,start+Duration::from_millis(602));f.step(start+Duration::from_millis(602));
    assert!(!f.world.actors[1].ready);assert_eq!(f.world.tick,1006);
    assert_eq!(f.world.actors[0].position[0],f.origins[0][0]+1.);
    assert_eq!(f.runtime.dispatched[0],Some(start+Duration::from_millis(600)));
    assert!(f.peers[0].no_request());
}

#[test]
fn nondividing_poll_interval_does_not_repeat_a_moving_pose_every_second() {
    //11ms polling is intentionally not a divisor of100ms. Resetting a
    //deadline to actual-send+100ms drifts to110ms and periodically publishes
    //the cached position again despite uninterrupted throttle on both lanes.
    for latency in [[1u64,1u64],[1,45]] {
        let start=Instant::now();let mut f=fixture(start);
        let mut pending:[Option<(u64,u32)>;2]=[None,None];let mut sent=[0u32;2];
        let mut rows=Vec::new();let mut send_times:[Vec<u64>;2]=std::array::from_fn(|_|Vec::new());
        for millis in (0u64..=3300).step_by(11) {
            let now=start+Duration::from_millis(millis);
            for slot in 0..2 {
                if let Some((due,seq))=pending[slot] {
                    if due<=millis { f.peers[slot].reply(now,&f.frame(slot,seq));pending[slot]=None; }
                }
            }
            let old=f.world.tick;f.runtime.step(&mut f.world,now).unwrap();
            if f.world.tick!=old { rows.push((f.world.tick,f.world.actors[0].position[0],f.world.actors[1].position[0])); }
            for slot in 0..2 {
                if f.runtime.workers[slot].as_ref().unwrap().pending() && pending[slot].is_none() {
                    let request=f.peers[slot].request();assert_eq!(request["op"],"advance");
                    sent[slot]+=1;assert_eq!(request["seq"],sent[slot]);assert_eq!(request["ticks"],6);
                    assert_eq!(request["input"],json!({"throttle":1,"steer":0,"brake":false}));
                    pending[slot]=Some((millis+latency[slot],sent[slot]));send_times[slot].push(millis);
                }
            }
        }
        assert_eq!(rows.len(),33,"new world tick must have a fresh completed pair");
        for (index,row) in rows.iter().enumerate() {
            assert_eq!(row.0,1001+index as u32);
            assert_eq!(row.1,f.origins[0][0]+index as f32+1.,"stale/repeated or skipped source pose at tick{}",row.0);
            assert_eq!(row.2,f.origins[1][0]+index as f32+1.,"paired lane source drift at tick{}",row.0);
        }
        assert_eq!(sent,[34,34]);
        for times in send_times { for (index,time) in times.into_iter().enumerate() {
            assert!(time>=index as u64*100 && time<index as u64*100+11,"logical deadline drift: request{} at{}ms",index+1,time);
        }}
    }
}

// Private, actual producer evidence for the existing scheduling policy. All
// helpers stay in cfg(test); the production dispatcher and worker are unchanged.
const REAL_BASE:&str="evidence/20261013-p05b-tracked-handling-01";
const REAL_DOMAIN:&str="9f54f371441a825c4d3f0dbd975e82a8c9644470d63188421a130e6639918165";
const REAL_CATALOG:&str="9c40f5bdeb8b77364805f31f18a9c6943a811630f7676fd10c6ec55d8ec5fd5e";

fn cadence_non_reparse(path:&Path) {
    for ancestor in path.ancestors() {
        let metadata=fs::symlink_metadata(ancestor).unwrap();
        assert!(!metadata.file_type().is_symlink());
        #[cfg(windows)] {
            use std::os::windows::fs::MetadataExt;
            assert_eq!(metadata.file_attributes()&0x400,0,"reparse ancestor {}",ancestor.display());
        }
    }
}
fn cadence_json(file:&mut fs::File,value:&Value) {
    std::io::Write::write_all(file,&serde_json::to_vec(value).unwrap()).unwrap();
    std::io::Write::write_all(file,b"\n").unwrap();
}
fn cadence_file(parent:&Path,name:&str)->fs::File {
    cadence_non_reparse(parent);
    fs::OpenOptions::new().write(true).create_new(true).open(parent.join(name)).unwrap()
}
fn cadence_state(state:&drive::State)->Value {
    json!({"seq":state.seq,"tick":state.tick,"scene_version":state.scene_version,
        "position":state.pose.position,"direction":state.pose.direction,"speed":state.pose.speed,
        "linear_velocity":state.pose.linear_velocity,"angular_velocity":state.pose.angular_velocity,
        "rspeed":state.pose.rspeed,"contacts":state.pose.contacts,"wheel_contact_masks":state.pose.wheel_contact_masks,
        "object_contacts":state.object_contacts.iter().map(|c|json!({"object_id":c.object_id,"kind":c.kind,
            "substep":c.substep,"point":c.point,"normal":c.normal,"velocity":c.velocity})).collect::<Vec<_>>(),
        "fractures_debug":format!("{:?}",state.fractures)})
}
fn cadence_next(worker:&mut drive::Worker,deadline:Instant)->drive::State {
    loop {assert!(Instant::now()<deadline,"bounded reference worker");
        if let Some(state)=worker.poll(Instant::now()).unwrap(){return state;}
        std::thread::sleep(Duration::from_millis(2));}
}

// Worker::Drop revokes/reaps its exact child even during unwinding. Keep PID
// receipts outside that scope and bound the independent exit-wait helper too.
fn cadence_wait_exit(pid:u32)->Result<(),String> {
    let mut command=std::process::Command::new("powershell.exe");
    #[cfg(windows)] {use std::os::windows::process::CommandExt;command.creation_flags(0x08000000);}
    let script=format!("$p=Get-Process -Id {pid} -ErrorAction SilentlyContinue; if ($null -ne $p -and -not $p.WaitForExit(5000)) {{ exit 1 }}; exit 0");
    let mut child=command.args(["-NoProfile","-NonInteractive","-Command",&script])
        .stdin(std::process::Stdio::null()).stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null())
        .spawn().map_err(|e|e.to_string())?;
    let deadline=Instant::now()+Duration::from_secs(8);
    loop {if let Some(status)=child.try_wait().map_err(|e|e.to_string())? {
        return if status.success(){Ok(())}else{Err(format!("owned worker {pid} exit wait failed: {status}"))};}
        if Instant::now()>=deadline {let _=child.kill();let _=child.wait();return Err(format!("owned exit helper timeout for worker {pid}"));}
        std::thread::sleep(Duration::from_millis(10));}
}
fn cadence_reap(pids:&mut Vec<u32>,pid:u32,cleanup:&mut fs::File) {
    let result=cadence_wait_exit(pid);
    cadence_json(cleanup,&json!({"pid":pid,"exit_wait":if result.is_ok(){"PASS"}else{"FAIL"},"error":result.as_ref().err()}));
    if result.is_ok(){pids.retain(|p|*p!=pid);}
    result.unwrap();
}

fn cadence_capture_pid(worker:&drive::Worker,deadline:Instant)->u32 {
    // launch returns before the verified-assets thread creates its child.
    // Do not poll here: the integrated coordinator owns its reply channel.
    loop {
        if let Some(pid)=worker.process_id(){return pid;}
        assert!(Instant::now()<deadline,"bounded asynchronous process creation");
        std::thread::sleep(Duration::from_millis(2));
    }
}

fn cadence_real_case(local:&Path,out:&Path,name:&str,kind:VehicleKind,pool_sha:&str,config_sha:&str,
    pids:&mut Vec<u32>,cleanup:&mut fs::File,launch_unverified:&mut bool)->Value {
    let base=local.join(REAL_BASE);
    let path=base.join(format!("night-cadence-real02/fixtures/{name}-pool.json"));
    let raw=fs::read(&path).unwrap();assert!(raw.len()<16384);
    assert_eq!(format!("{:x}",Sha256::digest(raw)),pool_sha);
    let pool=Arc::new(drive::Pool::load(local,&path).unwrap());assert_eq!(pool.vehicle_kind(),kind);
    let map=selected_pool_map(&pool,MapId::Prohorovka).unwrap().clone();
    assert_eq!(map.config_sha256,config_sha);assert_eq!(map.spawn,[-180.,2.5,-350.]);
    let catalog=Arc::new(fragiles::Catalog::load(local,&base.join("night-fence-export01/catalog/manifest.json"),REAL_DOMAIN).unwrap());
    let spec=CatalogSpec::load(local,&base.join("night-fence-export01/catalog/physics-removals.json"),REAL_CATALOG).unwrap();
    validate_catalog_projection(&catalog,&spec,MapId::Prohorovka).unwrap();
    let scene=Scene::new(&spec,&[]).unwrap();let forward=drive::Input{throttle:1,steer:0,brake:false};
    let lanes: [[f32;3];2]=std::array::from_fn(|slot|IntegratedRuntime::lane_spawn(&map,slot));
    assert_eq!(lanes,[[-184.,2.5,-350.],[-176.,2.5,-350.]]);
    let mut reference:[Vec<drive::State>;2]=std::array::from_fn(|_|Vec::new());
    for slot in 0..2 {
        let mut trace=cadence_file(out,&format!("reference-{slot}.jsonl"));
        let deadline=Instant::now()+Duration::from_secs(45);
        *launch_unverified=true;
        let mut worker=drive::Worker::launch_with_catalog(pool.clone(),map.clone(),slot as u32+2,
            Instant::now(),Some(lanes[slot]),spec.clone(),scene.clone()).unwrap();
        let pid=cadence_capture_pid(&worker,deadline);pids.push(pid);*launch_unverified=false;
        cadence_json(&mut trace,&json!({"event":"launch","pid":pid,"slot":slot,"spawn":lanes[slot],
            "config_sha256":config_sha,"catalog_sha256":REAL_CATALOG,"generation":worker.generation,"removed_ids":[]}));
        for seq in 0..=121 {
            if seq>0 {assert_eq!(worker.advance(forward,Instant::now()).unwrap(),seq);}
            let state=cadence_next(&mut worker,deadline);cadence_json(&mut trace,&cadence_state(&state));
            assert_eq!((state.seq,state.tick,state.scene_version),(seq,180+6*seq,0));
            assert!(state.object_contacts.is_empty(),"{name} lane{slot} contact at seq{seq}: {:?}",state.object_contacts);
            assert!(state.fractures.is_empty()&&worker.prepared_ids().is_empty());
            if (20..=120).contains(&seq) {
                assert!(state.pose.speed>0.1,"{name} lane{slot} stopped at seq{seq}");
                assert_ne!(state.pose,reference[slot].last().unwrap().pose,"nonmoving reference pose");
            }
            reference[slot].push(state);
        }
        drop(worker);cadence_reap(pids,pid,cleanup);
    }
    // Derive the mapping from fixture inputs/reference, not from the runtime
    // field which this test is meant to verify. Y is deliberately unshifted.
    let offsets:[[f32;3];2]=std::array::from_fn(|slot|[
        lanes[slot][0]-reference[slot][0].pose.position[0],0.,
        lanes[slot][2]-reference[slot][0].pose.position[2]]);
    let expected_pose=|slot:usize,seq:u32| {
        let pose=&reference[slot][seq as usize].pose;
        ([pose.position[0]+offsets[slot][0],pose.position[1],pose.position[2]+offsets[slot][2]],pose.direction,pose.speed)
    };
    let begin=Instant::now();let mut world=World::new_for_vehicle(921,begin,MapId::Prohorovka,kind).unwrap();
    world.impact.bind_fragiles(catalog.clone()).unwrap();world.fragiles=Some(fragiles::State::new(catalog));
    for slot in 0..2 {world.attach(model::Identity{account:format!("cadence-{name}-{slot}"),database:slot+1,
        name:format!("cadence_{slot}")},slot as u32+1).unwrap();}
    world.start(begin).unwrap();
    let mut runtime=IntegratedRuntime::new_for_map(pool,MapId::Prohorovka);runtime.catalog=Some(spec);
    // Capture a successful first spawn even if the second spawn returns Err.
    *launch_unverified=true;
    let start_result=runtime.start(&mut world,Instant::now());
    let spawn_deadline=Instant::now()+Duration::from_secs(45);
    for worker in runtime.workers.iter().flatten(){pids.push(cadence_capture_pid(worker,spawn_deadline));}
    *launch_unverified=false;
    start_result.unwrap();
    let mut polls=cadence_file(out,"polls.jsonl");let mut publications=cadence_file(out,"publications.jsonl");
    let warm_deadline=Instant::now()+Duration::from_secs(45);let mut warm_polls=0;
    while !runtime.ready_for_native()||!runtime.anchored.iter().all(|v|*v) {
        assert!(Instant::now()<warm_deadline);let now=Instant::now();let result=runtime.step(&mut world,now);warm_polls+=1;
        cadence_json(&mut polls,&json!({"phase":"warmup","at_us":now.duration_since(begin).as_micros(),"world_tick":world.tick,
            "seq":runtime.contact_sequences,"dispatched":runtime.dispatched.map(|d|d.map(|v|v.duration_since(begin).as_micros())),
            "ready":runtime.ready_for_native(),"anchored":runtime.anchored,"poses":runtime.poses,"pose_pending":runtime.pose_pending,
            "actors":world.actors.iter().map(|a|json!({"position":a.position,"direction":a.direction,"speed":a.speed,"ready":a.ready})).collect::<Vec<_>>(),
            "worker_pending":runtime.workers.iter().map(|w|w.as_ref().unwrap().pending()).collect::<Vec<_>>(),
            "error":result.as_ref().err().map(ToString::to_string)}));
        result.unwrap();assert_eq!(world.tick,1000);assert_eq!(runtime.contact_sequences,[0,0]);
        assert!(runtime.dispatched.iter().all(Option::is_none));assert_eq!(runtime.pose_pending,[false,false]);
        std::thread::sleep(Duration::from_millis(11));
    }
    assert_eq!(runtime.offsets,offsets);
    for slot in 0..2 {
        assert_eq!(runtime.poses[slot],Some(expected_pose(slot,0)));
        let actor=&world.actors[slot];assert!(!actor.ready);
        assert_eq!((actor.position,actor.direction,actor.speed),expected_pose(slot,0));
        world.set_ready(slot,slot as u32+1).unwrap();world.actors[slot].input=model::Input{throttle:1,steer:0};
        world.actors[slot].aim.set(super::super::aim::Intent::Hold{yaw:0.8,pitch:0.05}).unwrap();
    }
    let active=Instant::now();let deadline=active+Duration::from_secs(15);
    let mut consumed_at=[None;2];let mut sent_at:[Vec<Instant>;2]=std::array::from_fn(|_|Vec::new());
    let(mut count,mut polls_count,mut aim_changes,mut no_tick_polls)=(0u32,0u32,0u32,0u32);
    let mut last_publication=None;let mut intervals=Vec::new();let mut prior_poll=None;let mut max_poll_gap=Duration::ZERO;
    while count<120 {
        assert!(Instant::now()<deadline,"15s active bound, publications={count}");
        let now=Instant::now();if let Some(previous)=prior_poll{max_poll_gap=max_poll_gap.max(now.duration_since(previous));}prior_poll=Some(now);
        let before_world=world.clone();let before_seq=runtime.contact_sequences;let before_pending=runtime.pose_pending;
        let before_worker_pending=runtime.workers.iter().map(|w|w.as_ref().unwrap().pending()).collect::<Vec<_>>();
        let before_deadline=runtime.dispatched;let result=runtime.step(&mut world,now);let after=Instant::now();polls_count+=1;
        cadence_json(&mut polls,&json!({"phase":"active","poll":polls_count,"at_us":now.duration_since(begin).as_micros(),
            "active_us":now.duration_since(active).as_micros(),"step_duration_us":after.duration_since(now).as_micros(),
            "world_tick_before":before_world.tick,"world_tick_after":world.tick,"seq_before":before_seq,"seq_after":runtime.contact_sequences,
            "pose_pending_before":before_pending,"pose_pending_after":runtime.pose_pending,"poses":runtime.poses,
            "input":{"throttle":1,"steer":0,"brake":false},"worker_pending_before":before_worker_pending,
            "worker_pending":runtime.workers.iter().map(|w|w.as_ref().unwrap().pending()).collect::<Vec<_>>(),
            "deadlines_us":runtime.dispatched.map(|d|d.map(|v|v.duration_since(begin).as_micros())),"scene":world.scene_version(),
            "ready":runtime.ready_for_native(),"staged":runtime.staged.is_some(),"aim":world.actors.iter().map(|a|[a.aim.yaw,a.aim.pitch]).collect::<Vec<_>>(),
            "error":result.as_ref().err().map(ToString::to_string)}));
        result.unwrap();assert!(polls_count<1600);assert_eq!(world.scene_version(),0);
        assert!(!runtime.blocked()&&runtime.ready_for_native());assert!(world.fragiles.as_ref().unwrap().removed_ids().is_empty());
        for slot in 0..2 {
            let seq=runtime.contact_sequences[slot];assert!(seq<=121);
            if seq!=before_seq[slot] {assert_eq!(seq,before_seq[slot]+1);assert!(!before_pending[slot],"pending source replaced");consumed_at[slot]=Some(now);}
            assert_eq!(runtime.poses[slot],Some(expected_pose(slot,seq)),"actual source mismatch {name} slot{slot} seq{seq}");
            if runtime.dispatched[slot]!=before_deadline[slot] {
                let d=runtime.dispatched[slot].unwrap();
                if let Some(previous)=before_deadline[slot] {assert_eq!(d.duration_since(previous),drive::STEP);}
                else {let start=world.started.unwrap();let ticks=now.duration_since(start).as_millis()/100;
                    assert_eq!(d,start+Duration::from_millis((ticks*100).try_into().unwrap()));}
                assert!(now>=d&&now.duration_since(d)<=drive::MAX_LAG);assert!(!runtime.pose_pending[slot]);
                assert!(runtime.workers[slot].as_ref().unwrap().pending());
                assert_eq!(seq as usize+1,sent_at[slot].len()+1);sent_at[slot].push(now);
            }
        }
        if world.tick!=before_world.tick {
            count+=1;assert_eq!(runtime.contact_sequences,[count,count]);assert_eq!(runtime.pose_pending,[false,false]);
            assert_eq!(u128::from(world.tick),1000+now.duration_since(world.started.unwrap()).as_millis()/100);
            if count>1 {assert_eq!(world.tick,before_world.tick+1,"timing smoke skipped world bucket; inspect actual poll gaps");}
            for slot in 0..2 {
                let expected=expected_pose(slot,count);let actor=&world.actors[slot];
                assert_eq!((actor.position,actor.direction,actor.speed),expected);
                assert_eq!(actor.yaw,actor.direction[0]);
                if actor.aim!=before_world.actors[slot].aim{aim_changes+=1;}
            }
            let interval=last_publication.map(|last|now.duration_since(last).as_micros());
            if let Some(value)=interval {intervals.push(value);}last_publication=Some(now);
            cadence_json(&mut publications,&json!({"publication":count,"world_tick":world.tick,"source_seq":runtime.contact_sequences,
                "at_us":now.duration_since(begin).as_micros(),"active_us":now.duration_since(active).as_micros(),"interval_us":interval,
                "poses":runtime.poses,"observed_held_us":consumed_at.map(|t|now.duration_since(t.unwrap()).as_micros()),
                "dispatch_to_publication_us":[now.duration_since(sent_at[0][count as usize-1]).as_micros(),now.duration_since(sent_at[1][count as usize-1]).as_micros()],
                "age_definition":"held since reply consumption; dispatch age includes request/producer/IPC/poll wait, not a producer timestamp"}));
        }else {no_tick_polls+=1;assert_eq!(world.actors,before_world.actors,"actor/aim changed without a publication");}
        if count<120 {std::thread::sleep(Duration::from_millis(11));}
    }
    assert_eq!(count,120);assert!(no_tick_polls>0&&aim_changes>0);assert_eq!(intervals.len(),119);
    assert!(sent_at.iter().all(|v|(120..=121).contains(&v.len())));
    let active_us=Instant::now().duration_since(active).as_micros();
    let paired_pids=runtime.workers.iter().map(|w|w.as_ref().unwrap().process_id().unwrap()).collect::<Vec<_>>();
    drop(runtime);for pid in &paired_pids{cadence_reap(pids,*pid,cleanup);}
    json!({"status":"PASS_REAL_WORKER_CADENCE_NOT_NATIVE","vehicle":name,"mass_kg":map.mass_kg,"pool_sha256":pool_sha,
        "config_sha256":config_sha,"domain_sha256":REAL_DOMAIN,"catalog_sha256":REAL_CATALOG,"lanes":lanes,"offsets":offsets,
        "reference_advances_per_lane":121,"publications":count,"dispatch_counts":sent_at.map(|v|v.len()),"warmup_polls":warm_polls,
        "active_polls":polls_count,"requested_poll_ms":11,"active_us":active_us,"max_poll_gap_us":max_poll_gap.as_micros(),
        "publication_intervals_us":intervals,"aim_changes":aim_changes,"unchanged_no_tick_polls":no_tick_polls,"paired_pids":paired_pids,
        "native":"NOT_RUN","uncatalogued_static_contacts":"NOT_OBSERVED_BY_IPC"})
}

#[test]
#[ignore = "Real-time no-load gate; run exact isolated --run-ignored through server/build.py"]
fn real_worker_11ms_cadence() {
    let uncanonical=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local");cadence_non_reparse(&uncanonical);
    let local=uncanonical.canonicalize().unwrap();let parent=local.join(REAL_BASE).join("night-cadence-real02");cadence_non_reparse(&parent);
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let out=parent.join(format!("run-{}-{stamp}",std::process::id()));fs::create_dir(&out).unwrap();
    let mut results=Vec::new();
    for (name,kind,pool,config) in [
        ("ms1",VehicleKind::Ms1,"0bd51d7cc9db2b15c224d00b33cda97608fccfe5c4ff7af15537693436f36f54","64cd57affd71f9de0bf60ccc7027bd7d0419ee509910c0dc9cbcd2d621c3678c"),
        ("is7",VehicleKind::Is7,"ef4c3eab74ece370c679b943ff80468013bdedb658fb2fa47851fd64673b12e0","2b01e2b9ea1ef3e24ca6c508f75cefd36ea245252320682c9dfd41a4854b01cb")] {
        let folder=out.join(name);fs::create_dir(&folder).unwrap();let mut cleanup=cadence_file(&folder,"cleanup.jsonl");let mut pids=Vec::new();
        let mut launch_unverified=false;
        let outcome=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||cadence_real_case(&local,&folder,name,kind,pool,config,&mut pids,&mut cleanup,&mut launch_unverified)));
        // The unwound scope has dropped all Worker handles before these waits.
        let mut cleanup_errors=Vec::new();
        if launch_unverified {cleanup_errors.push("asynchronous launch PID was not captured; do not start another profile".into());}
        for pid in pids {let status=cadence_wait_exit(pid);cadence_json(&mut cleanup,&json!({"pid":pid,"failure_cleanup":true,"error":status.as_ref().err()}));if let Err(e)=status{cleanup_errors.push(e);}}
        let mut result=match outcome {Ok(value)=>value,Err(error)=>json!({"status":"FAIL","vehicle":name,
            "error":error.downcast_ref::<String>().cloned().or_else(||error.downcast_ref::<&str>().map(|s|(*s).into())).unwrap_or_else(||"non-string panic".into()),"native":"NOT_RUN"})};
        result["cleanup_errors"]=json!(cleanup_errors);if !cleanup_errors.is_empty(){result["status"]=json!("FAIL_CLEANUP");}
        cadence_json(&mut cadence_file(&folder,"result.json"),&result);results.push(result);
        if !cleanup_errors.is_empty(){break;}
    }
    cadence_json(&mut cadence_file(&out,"result.json"),&json!({"scope":"actual candidate14 producer + IntegratedRuntime; no native/client/network",
        "planned_cases":2,"cases":results,"source_reference":"same pinned build/platform, independent exact production lane replay"}));
    assert!(results.len()==2&&results.iter().all(|v|v["status"]=="PASS_REAL_WORKER_CADENCE_NOT_NATIVE"),"real cadence failures retained at {}",out.display());
}
