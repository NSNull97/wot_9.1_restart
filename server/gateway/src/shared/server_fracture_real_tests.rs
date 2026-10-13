//! Required pinned private IPC5 workers, original close-joint geometry, and the
//! actual runtime/parser/domain/both-ACK transaction. No native game clients.
use super::*;
use super::super::fragiles;
use crate::map_drive_worker091::{CatalogSpec, Pool, Scene, Worker};

const BASE: &str = "evidence/20261013-p06r-compound-01";
const POOL_SHA: &str = "62549fb3b3652edadbf6756445141a192f3157e741ab94d2e890c5a54de9783e";
const CONFIG_SHA: &str = "a1d8f4406661e53636c5430588def8af96de93a1d56b4781a4bedf6a01e8c49e";
const DOMAIN_SHA: &str = "39bb68815dd2d7ca54789a1cc71be619cc4f2f5cf351bf52f22de92f2afca11d";
const CATALOG_SHA: &str = "0a7c8fd70f00c8c49c3282ac1fe574281f384d042b1adb7da549d1680c192ef9";

#[test]
fn real_ipc5_chain_receipts_cross_runtime_and_publish_only_after_both_workers_ack() {
    let local=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
    let base=local.join(BASE);
    let path=base.join("fracture-gateway-real01/pool-chain.json");
    let metadata=fs::metadata(&path).expect("required pinned IPC5 chain pool");
    assert!(metadata.is_file() && metadata.len()<=16_384);
    assert_eq!(format!("{:x}",Sha256::digest(fs::read(&path).unwrap())),POOL_SHA);
    let pool=Arc::new(Pool::load(&local,&path).unwrap());
    let map=selected_pool_map(&pool,MapId::Prohorovka).unwrap().clone();
    assert_eq!(map.config_sha256,CONFIG_SHA);assert_eq!(map.mass_kg,4691.);
    let spec=CatalogSpec::load(&local,&base.join("import/fence-response01/physics-removals.json"),CATALOG_SHA).unwrap();
    let catalog=Arc::new(fragiles::Catalog::load(&local,&base.join("import/fence-response01/manifest.json"),DOMAIN_SHA).unwrap());
    assert_eq!(catalog.version,4);assert_eq!(spec.version(),5);assert_eq!(catalog.worker_sha256,spec.sha256());
    for id in [3307,3308] {
        let object=catalog.objects.iter().find(|o|o.object_id==id).unwrap();
        let entry=spec.entries().iter().find(|o|o.object_id()==id).unwrap();
        assert_eq!(object.kind,fragiles::ObjectKind::MovementFragile);
        assert_eq!(object.object_revision,entry.object_revision());assert_eq!(entry.ram_energy_j(),8000);
    }
    let begin=Instant::now();let deadline=begin+Duration::from_secs(60);
    let mut world=World::new_for_map(916,begin,MapId::Prohorovka).unwrap();
    // This movement-only fixture binds the real catalog and trace directly;
    // projectile geometry/firing is outside this test and never simulated.
    world.impact.bind_fragiles(catalog.clone()).unwrap();
    world.fragiles=Some(fragiles::State::new(catalog));
    for slot in 0..2 {
        world.attach(model::Identity { account:format!("fracture-real-{slot}"),database:slot+1,
            name:format!("fracture_{slot}") },slot as u32+1).unwrap();
    }
    world.start(begin).unwrap();world.rebase_external_spawns([map.spawn;2]).unwrap();
    for slot in 0..2 {world.set_ready(slot,slot as u32+1).unwrap();world.actors[slot].input=model::Input{throttle:1,steer:0};}
    let mut runtime=IntegratedRuntime::new_for_map(pool,MapId::Prohorovka);
    runtime.catalog=Some(spec.clone());runtime.started=true;
    let empty=Scene::new(&spec,&[]).unwrap();
    // Deliberately run both independent actor workers down the same source
    // path: each owes its own energy, while the shared object changes once.
    for slot in 0..2 {
        runtime.workers[slot]=Some(Worker::launch_with_catalog(runtime.pool.clone(),map.clone(),
            slot as u32+2,Instant::now(),None,spec.clone(),empty.clone()).unwrap());
        runtime.worker_sessions[slot]=world.actors[slot].session;
    }
    let mut commits=Vec::new();
    while runtime.contact_sequences.iter().any(|seq|*seq<26) {
        assert!(Instant::now()<deadline,"bounded real IPC5 chain");
        let before=world.clone();
        runtime.step(&mut world,Instant::now()).unwrap();
        if let Some(candidate)=runtime.staged.clone() {
            assert_eq!(world.actors,before.actors);assert_eq!(world.fragiles,before.fragiles);
            assert!(!runtime.ready_for_native());
            let ids=candidate.fragiles.as_ref().unwrap().removed_ids();
            let target=Scene::new(&spec,&ids).unwrap();
            let expected=if commits.is_empty(){vec![3307]}else{vec![3307,3308]};
            assert_eq!(ids,expected);assert!(commits.len()<2);
            let prepared=runtime.workers.iter().map(|w|w.as_ref().unwrap().prepared_ids().to_vec()).collect::<Vec<_>>();
            assert!(prepared.iter().all(|v|v==&vec![*ids.last().unwrap()]));
            for worker in &mut runtime.workers {
                assert!(worker.as_mut().unwrap().advance(crate::map_drive_worker091::Input::STOP,Instant::now()).is_err());
            }
            // Intentionally consume only A's real ACK. B may already have
            // changed its private scene; its queued ACK is not acceptance.
            while runtime.workers[0].as_ref().unwrap().catalog_scene()!=Some(&target) {
                assert!(Instant::now()<deadline);
                assert!(runtime.workers[0].as_mut().unwrap().poll(Instant::now()).unwrap().is_none());
                std::thread::sleep(Duration::from_millis(2));
            }
            assert_eq!(world.actors,before.actors);assert_eq!(world.fragiles,before.fragiles);
            assert_ne!(runtime.workers[1].as_ref().unwrap().catalog_scene(),Some(&target));
            while runtime.staged.is_some() {
                assert!(Instant::now()<deadline);
                runtime.finish_catalog(&mut world,Instant::now()).unwrap();
                std::thread::sleep(Duration::from_millis(2));
            }
            assert_eq!(world.actors,candidate.actors);assert_eq!(world.fragiles,candidate.fragiles);
            assert_eq!(world.fragiles.as_ref().unwrap().vehicle_events.len(),ids.len());
            assert!(runtime.workers.iter().all(|w|w.as_ref().unwrap().catalog_scene()==Some(&target)
                && w.as_ref().unwrap().prepared_ids().is_empty()));
            commits.push(serde_json::json!({"scene_version":target.version(),"scene_sha256":target.hash(),
                "removed_ids":ids,"prepared_per_slot":prepared,"advance_sequences":runtime.contact_sequences,
                "world_unchanged_until_both_ack":true}));
        }
        std::thread::sleep(Duration::from_millis(2));
    }
    assert_eq!(commits.len(),2);assert_eq!(world.scene_version(),2);
    assert_eq!(world.fragiles.as_ref().unwrap().vehicle_events.len(),2);
    assert!(runtime.poses.iter().all(|pose|pose.unwrap().0[2]>464.));
    assert!(world.actors.iter().all(|actor|actor.position[2]>464.));
    let pids=runtime.workers.iter().map(|w|w.as_ref().unwrap().process_id().unwrap()).collect::<Vec<_>>();
    let proof=serde_json::json!({"status":"PASS_REAL_IPC5_RUNTIME_DOMAIN_BOTH_ACK","native_clients":"NOT_RUN",
        "pool_sha256":POOL_SHA,"config_sha256":CONFIG_SHA,"domain_sha256":DOMAIN_SHA,"catalog_sha256":CATALOG_SHA,
        "pids":pids,"mass_kg":map.mass_kg,"commits":commits,"final_sequences":runtime.contact_sequences,
        "final_positions":world.actors.iter().map(|a|a.position).collect::<Vec<_>>()});
    fs::write(base.join(format!("fracture-gateway-real01/result-{}.json",std::process::id())),
        serde_json::to_vec_pretty(&proof).unwrap()).unwrap();
    // Dropping these handles closes/reaps only the two children owned here.
    drop(runtime);
}
