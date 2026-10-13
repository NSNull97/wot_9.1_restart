//! Deterministic coordinator/IPC ordering, without clocks, threads or clients.
//! Synthetic worker replies cross the actual bounded Worker parser and step
//! barrier; they do not establish physical or native-client compatibility.
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
}

fn fixture(now: Instant) -> Fixture {
    fixture_profile(now,false)
}
fn fixture_profile(now: Instant, fracture:bool) -> Fixture {
    let catalog = fragiles::tests::contact_catalog();
    let mut world = model::tests::world(now);
    world.impact.bind_fragiles(catalog.clone()).unwrap();
    world.fragiles = Some(fragiles::State::new(catalog.clone()));
    let mut manifest = json!({"version":3,"profile":"test_lab","map":"01_karelia",
        "contacts":true,"physics_manifest_sha256":MapId::Karelia.spec().physics_manifest_sha256,
        "projectile_manifest_sha256":MapId::Karelia.spec().projectile_manifest_sha256,
        "objects":catalog.objects.iter().map(|o| json!({"object_id":o.object_id,"instance_id":o.instance_id,
            "first_triangle":o.physics_first_triangle,"triangle_count":o.physics_triangle_count,
            "object_revision":o.object_revision,"kind":if matches!(o.kind,fragiles::ObjectKind::Tree){"tree"}else{"fragile"}
        })).collect::<Vec<_>>() });
    if fracture {
        manifest["version"]=5.into();manifest["ram_policy"]="test_lab-fence-energy-v1".into();
        for entry in manifest["objects"].as_array_mut().unwrap(){entry["ram_energy_j"]=if entry["kind"]=="fragile"{8000}else{0}.into();}
    }
    let raw=serde_json::to_vec(&manifest).unwrap();
    static NEXT: std::sync::atomic::AtomicUsize = std::sync::atomic::AtomicUsize::new(0);
    let directory = std::env::temp_dir().join(format!("wot091-contact-barrier-{}-{}",
        std::process::id(), NEXT.fetch_add(1, std::sync::atomic::Ordering::Relaxed)));
    fs::create_dir(&directory).unwrap();
    let path = directory.join("catalog.json");
    fs::write(&path, &raw).unwrap();
    let spec = CatalogSpec::load(&directory, &path, &format!("{:x}", Sha256::digest(&raw))).unwrap();
    fs::remove_file(&path).unwrap();
    fs::remove_dir(&directory).unwrap();
    let map = drive::tests::map();
    let mut runtime = IntegratedRuntime::new(controlled_ipc::pool(map.clone()));
    runtime.catalog = Some(spec.clone());
    runtime.started = true;
    let scene = Scene::new(&spec, &[]).unwrap();
    let peers = std::array::from_fn(|slot| {
        let (worker, peer) = controlled_ipc::ready(map.clone(), slot as u32 + 2,
            spec.clone(), scene.clone(), now);
        runtime.workers[slot] = Some(worker);
        runtime.worker_sessions[slot] = world.actors[slot].session;
        runtime.anchored[slot] = true;
        runtime.poses[slot] = Some((world.actors[slot].position, world.actors[slot].direction, 0.));
        peer
    });
    Fixture { world, runtime, peers, map, spec }
}

fn contact(object_id: u32, speed: f32) -> Value {
    json!({"object_id":object_id,"kind":"hull","substep":1,"point":[0.,0.,0.],
        "normal":[0.,0.,1.],"velocity":[0.,0.,speed]})
}

impl Fixture {
    fn dispatch(&mut self, now: Instant) {
        self.runtime.step(&mut self.world, now).unwrap();
        for peer in &self.peers {
            let request = peer.request();
            assert_eq!(request["op"], "advance");
            assert_eq!(request["seq"], 1);
        }
    }
    fn reply(&self, slot: usize, seq: u32, now: Instant, contacts: Vec<Value>) {
        self.peers[slot].reply(now,&self.frame(slot,seq,contacts));
    }
    fn frame(&self,slot:usize,seq:u32,contacts:Vec<Value>)->Value {
        let worker = self.runtime.workers[slot].as_ref().unwrap();
        let scene = worker.catalog_scene().unwrap();
        // Deliberately zero post-step velocity: an impact must retain its
        // nonzero pre-collision velocity while the other reply is delayed.
        let mut value=json!({"version":4,"event":"state","seq":seq,
            "tick":180+seq*6,"settle_ticks":180,"map":self.map.asset,"config_sha256":self.map.config_sha256,
            "generation":worker.generation,"catalog_sha256":self.spec.sha256(),"contacts":true,
            "scene_version":scene.version(),"scene_sha256":scene.hash(),
            "state":{"position":self.world.actors[slot].position,"direction":self.world.actors[slot].direction,
                "speed":0.,"rspeed":0.,"contacts":6,"linear_velocity":[0.,0.,0.],
                "angular_velocity":[0.,0.,0.],"wheel_contact_masks":[63,63,63,63,63,63],"object_contacts":contacts}});
        if self.spec.version()==5{value["version"]=5.into();value["state"]["fractures"]=json!([]);}
        value
    }
    fn ack(&self, slot: usize, request: &Value, now: Instant) {
        assert_eq!(request["op"], "sync_removed");
        let mut ack = request.clone();
        let object = ack.as_object_mut().unwrap();
        object.remove("op");
        object.insert("event".into(), json!("scene_synced"));
        object.insert("tick".into(), json!(180 + request["advance_seq"].as_u64().unwrap() * 6));
        self.peers[slot].reply(now, &ack);
    }
    fn step(&mut self, now: Instant) { self.runtime.step(&mut self.world, now).unwrap(); }
    fn events(&self) -> usize { self.world.fragiles.as_ref().unwrap().vehicle_events.len() }
}

#[test]
fn delayed_worker_preserves_consumed_contact_until_both_scene_acks_exactly_once() {
    for first in 0..2 {
        let now = Instant::now();
        let mut f = fixture(now);
        f.dispatch(now);
        f.reply(first, 1, now + Duration::from_millis(1), vec![contact(1513, 2.)]);
        f.step(now + Duration::from_millis(2));
        assert_eq!(f.events(), 0);
        assert_eq!(f.world.scene_version(), 0);
        assert!(!f.runtime.workers[first].as_ref().unwrap().pending());
        assert!(f.runtime.workers[1-first].as_ref().unwrap().pending());
        // Repeat the exact old failure path with the first IPC reply already
        // consumed and no replacement contact to reconstruct from the pose.
        f.step(now + Duration::from_millis(3));
        assert!(f.peers.iter().all(controlled_ipc::Peer::no_request));
        f.reply(1-first, 1, now + Duration::from_millis(4), vec![]);
        f.step(now + Duration::from_millis(5));
        assert!(f.runtime.blocked(), "the retained impact must stage destruction");
        assert_eq!(f.runtime.staged.as_ref().unwrap().scene_version(), 1);
        assert_eq!(f.events(), 0);
        assert!(f.runtime.contact_batches.iter().all(Option::is_none));
        let requests = [f.peers[0].request(), f.peers[1].request()];
        for request in &requests { assert_eq!(request["removed_object_ids"], json!([1513])); }
        f.ack(first, &requests[first], now + Duration::from_millis(6));
        f.step(now + Duration::from_millis(7));
        assert_eq!(f.events(), 0, "one scene ACK cannot publish destruction");
        f.ack(1-first, &requests[1-first], now + Duration::from_millis(8));
        f.step(now + Duration::from_millis(9));
        assert_eq!(f.events(), 1);
        assert_eq!(f.world.scene_version(), 1);
        assert_eq!(f.world.fragiles.as_ref().unwrap().vehicle_events[0].shooter, first);
        f.step(now + Duration::from_millis(10));
        f.step(now + Duration::from_millis(11));
        assert_eq!(f.events(), 1, "ACK/no-reply polls must not replay a batch");
        assert!(f.peers.iter().all(controlled_ipc::Peer::no_request));
    }
}

#[test]
fn ineffective_contact_is_consumed_and_does_not_block_the_next_advance() {
    let now = Instant::now();
    let mut f = fixture(now);
    f.dispatch(now);
    f.reply(0, 1, now + Duration::from_millis(1), vec![contact(1513, 0.5)]);
    f.step(now + Duration::from_millis(2));
    f.reply(1, 1, now + Duration::from_millis(3), vec![]);
    f.step(now + Duration::from_millis(4));
    assert_eq!(f.events(), 0);
    assert!(f.runtime.contact_batches.iter().all(Option::is_none));
    f.step(now + drive::STEP);
    for peer in &f.peers { assert_eq!(peer.request()["seq"], 2); }
    f.reply(0, 2, now + drive::STEP, vec![contact(1513, 2.)]);
    f.reply(1, 2, now + drive::STEP, vec![]);
    f.step(now + drive::STEP);
    assert!(f.runtime.blocked());
    assert_eq!(f.runtime.staged.as_ref().unwrap().scene_version(), 1);
}

#[test]
fn detached_actors_consumed_contact_cannot_damage_for_a_survivor() {
    let now = Instant::now();
    let mut f = fixture(now);
    f.dispatch(now);
    f.reply(0, 1, now + Duration::from_millis(1), vec![contact(1513, 2.)]);
    f.step(now + Duration::from_millis(2));
    f.world.detach(1).unwrap();
    f.reply(1, 1, now + Duration::from_millis(3), vec![]);
    f.step(now + Duration::from_millis(4));
    assert_eq!(f.events(), 0);
    assert!(!f.runtime.blocked());
    assert!(f.runtime.workers[0].is_none());
    assert!(f.runtime.contact_batches.iter().all(Option::is_none));
    assert_eq!(f.runtime.contact_sequences[0], 0);
}

#[test]
fn initial_native_readiness_wait_retains_an_already_consumed_advance() {
    let now = Instant::now();
    let mut f = fixture(now);
    f.dispatch(now);
    f.world.actors[1].ready = false;
    for slot in 0..2 {
        f.reply(slot, 1, now + Duration::from_millis(1),
            if slot == 0 { vec![contact(1513, 2.)] } else { vec![] });
    }
    f.step(now + Duration::from_millis(2));
    assert!(!f.runtime.blocked());
    assert_eq!(f.events(), 0);
    f.world.set_ready(1, 2).unwrap();
    f.step(now + Duration::from_millis(3));
    assert!(f.runtime.blocked());
    assert_eq!(f.runtime.staged.as_ref().unwrap().scene_version(), 1);
}

#[test]
fn rejoin_scene_ack_keeps_survivor_contact_without_waiting_for_native_ready() {
    let now = Instant::now();
    let mut f = fixture(now);
    f.world.apply_vehicle_contacts(&[model::VehicleContactInput { object_id: 1513,
        substep: 1, point: [0.;3], normal: [0.,0.,1.], velocity: [0.,0.,2.],
        mass_kg: f.map.mass_kg, kind: "hull".into(), shooter: 0 }]).unwrap();
    f.world.advance(now + drive::STEP).unwrap();
    let scene1 = Scene::new(&f.spec, &[1513]).unwrap();
    // Survivor already knows scene1; the rejoining worker needs its scene ACK
    // and has supplied neither a native READY nor an authoritative pose yet.
    let (worker, peer) = controlled_ipc::ready(f.map.clone(), 2, f.spec.clone(), scene1,
        now + drive::STEP);
    f.runtime.workers[0] = Some(worker);
    f.peers[0] = peer;
    f.world.actors[1].ready = false;
    f.runtime.poses[1] = None;
    f.runtime.anchored[1] = false;
    let at = now + drive::STEP;
    f.runtime.workers[0].as_mut().unwrap().advance(drive::Input { throttle: 1, steer: 0, brake: false }, at).unwrap();
    f.runtime.dispatched[0] = Some(at);
    assert_eq!(f.peers[0].request()["seq"], 1);
    f.reply(0, 1, at + Duration::from_millis(1), vec![contact(1514, 2.)]);
    f.step(at + Duration::from_millis(2));
    assert_eq!(f.events(), 1);
    assert!(f.runtime.synchronizing[1]);
    assert!(!f.runtime.blocked());
    let restore = f.peers[1].request();
    assert_eq!(restore["removed_object_ids"], json!([1513]));
    f.ack(1, &restore, at + Duration::from_millis(3));
    f.step(at + Duration::from_millis(4));
    assert!(!f.world.actors[1].ready);
    assert!(f.runtime.blocked());
    assert_eq!(f.runtime.staged.as_ref().unwrap().scene_version(), 2);
    let requests = [f.peers[0].request(), f.peers[1].request()];
    for slot in 0..2 { f.ack(slot, &requests[slot], at + Duration::from_millis(5)); }
    f.step(at + Duration::from_millis(6));
    assert_eq!(f.events(), 2);
    assert_eq!(f.world.scene_version(), 2);
    assert!(!f.world.actors[1].ready);
}

#[test]
fn changed_worker_generation_cannot_apply_a_retained_contact() {
    let now = Instant::now();
    let mut f = fixture(now);
    f.dispatch(now);
    f.reply(0, 1, now + Duration::from_millis(1), vec![contact(1513, 2.)]);
    f.step(now + Duration::from_millis(2));
    f.runtime.workers[0].as_mut().unwrap().generation += 2;
    f.reply(1, 1, now + Duration::from_millis(3), vec![]);
    let before = f.world.fragiles.clone();
    assert!(f.runtime.step(&mut f.world, now + Duration::from_millis(4)).is_err());
    assert_eq!(f.world.fragiles, before);
    assert_eq!(f.events(), 0);
    assert!(!f.runtime.blocked());
}

fn prepared_frame(f:&Fixture,slot:usize)->Value{
    let mut frame=f.frame(slot,1,vec![contact(1513,4.)]);
    frame["event"]="prepared".into();
    frame["state"]["fractures"]=json!([{"object_id":1513,"substep":1,"order":1,"point":[0.,0.,0.],
        "normal":[0.,0.,1.],"velocity":[0.,0.,4.],"budget_before":[0.,0.,4.],
        "budget_after":[0.,0.,(16.-16000./f.map.mass_kg).sqrt()],"solver_before":[0.,0.,0.],
        "solver_after":[0.,0.,0.],"energy_j":8000}]);
    frame
}

#[test]
fn fracture_prepared_pose_waits_for_peer_and_both_acks_before_world_publication(){
    for first in 0..2 {
        let now=Instant::now();let mut f=fixture_profile(now,true);f.dispatch(now);
        let before=f.world.actors.clone();let mut frame=prepared_frame(&f,first);
        frame["state"]["position"][0]=(before[first].position[0]+1.).into();
        f.peers[first].reply(now+Duration::from_millis(1),&frame);
        f.step(now+Duration::from_millis(2));
        assert!(f.runtime.blocked());assert!(f.runtime.staged.is_none());assert!(!f.runtime.ready_for_native());
        assert_eq!(f.world.actors,before);assert_eq!(f.events(),0);
        assert!(f.runtime.workers[first].as_mut().unwrap().advance(drive::Input::STOP,now+Duration::from_millis(2)).is_err());
        f.reply(1-first,1,now+Duration::from_millis(3),vec![]);f.step(now+Duration::from_millis(4));
        assert!(f.runtime.staged.is_some());assert_eq!(f.world.actors,before);assert_eq!(f.events(),0);
        let requests=[f.peers[0].request(),f.peers[1].request()];
        f.ack(first,&requests[first],now+Duration::from_millis(5));f.step(now+Duration::from_millis(6));
        assert_eq!(f.events(),0);assert_eq!(f.world.actors,before);
        f.ack(1-first,&requests[1-first],now+Duration::from_millis(7));f.step(now+Duration::from_millis(8));
        assert_eq!(f.events(),1);assert_eq!(f.world.scene_version(),1);assert!(!f.runtime.blocked());
        // Same-tick poses may remain parked by the domain clock, but no
        // provisional pose or destruction could escape before both ACKs.
        f.step(now+Duration::from_millis(9));assert_eq!(f.events(),1);
    }
}

#[test]
fn fracture_preparation_cannot_import_an_unready_pose_or_omit_the_domain_delta(){
    let now=Instant::now();let mut f=fixture_profile(now,true);
    f.world.advance(now+drive::STEP).unwrap();f.dispatch(now+drive::STEP);
    f.world.actors[0].ready=false;let before=f.world.actors[0].position;
    let mut frame=prepared_frame(&f,0);frame["state"]["position"][0]=(before[0]+1.).into();
    f.peers[0].reply(now+drive::STEP,&frame);f.step(now+drive::STEP);
    assert_eq!(f.world.actors[0].position,before);assert!(f.runtime.blocked());
    // Simulate a rejected candidate: the existing scene does not contain the
    // physical proposal. No commit request may reach either worker.
    let mut omitted=f.world.clone();
    omitted.apply_vehicle_contacts(&[model::VehicleContactInput {object_id:1514,substep:1,point:[0.;3],
        normal:[0.,0.,1.],velocity:[0.,0.,4.],mass_kg:f.map.mass_kg,kind:"hull".into(),shooter:1}]).unwrap();
    f.runtime.staged=Some(omitted);
    assert!(f.runtime.finish_catalog(&mut f.world,now+drive::STEP).is_err());
    assert_eq!(f.events(),0);assert!(f.peers.iter().all(controlled_ipc::Peer::no_request));
}
