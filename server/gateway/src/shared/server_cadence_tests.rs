//! Controlled IPC clock regression. This verifies coordinator scheduling and
//! source-pose publication, not Jolt dynamics or native-client presentation.
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
        normal:[0.,0.,1.],velocity:[0.,0.,2.],mass_kg:f.map.mass_kg,kind:"hull".into(),shooter:0}]).unwrap();
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
