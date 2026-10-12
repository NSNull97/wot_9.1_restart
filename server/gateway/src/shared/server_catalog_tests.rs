//! Real owned IPC3 workers, no game clients or sockets. Source geometry is
//! original; ordinal native_index values below are ONLY unpublished unit data.
use super::*;
use super::super::{fragiles,geometry};
use crate::map_drive_worker091::{CatalogSpec,Pool,Scene};

const WORKER_CATALOG_SHA:&str="58606f16e1fc08769f11b72eb29c90a595ef2c8b1ca611cdd81ae8bfbd1a2b63";
const INVENTORY_SHA:&str="5658e7620389e9726b1ff06f1eb80125224a45fe17d8558c2e072b4a7cc6bbf3";
const POOL_SHA:&str="c2dd3da12e275b94172107e3e358dfb8452dc3dc7895fd3e295a0ac38c0db22b";

fn local()->std::path::PathBuf{
    Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap()
}
fn fixture(now:Instant)->(World,Arc<Pool>,CatalogSpec){
    let local=local();let evidence=local.join("evidence/20261012-p06o-destructible-import-01");
    let pool=Arc::new(Pool::load(&local,&local.join("build/server/physics-integrated-p06o-01/pool-near.json")).unwrap());
    assert_eq!(pool.sha256,POOL_SHA);
    let spec=CatalogSpec::load(&local,&evidence.join("boundary/worker-ipc01/catalog.json"),WORKER_CATALOG_SHA).unwrap();
    let raw=fs::read(evidence.join("resource-contract/inventory02/inventory.json")).unwrap();
    assert!(raw.len()<4*1024*1024);assert_eq!(format!("{:x}",Sha256::digest(&raw)),INVENTORY_SHA);
    let inventory:serde_json::Value=serde_json::from_slice(&raw).unwrap();
    let rows=inventory["eligible"].as_array().unwrap();assert_eq!(rows.len(),6);
    let mut next_index=std::collections::BTreeMap::<u16,u8>::new();
    let objects=rows.iter().map(|row|{
        let id=row["instance_id"].as_u64().unwrap() as u32;
        let chunk=row["chunk_id"].as_u64().unwrap() as u16;
        let index=next_index.entry(chunk).or_insert(0);let native_index=*index;*index+=1;
        let worker=spec.entries().iter().find(|entry|entry.instance_id()==id).unwrap();
        assert_eq!(worker.object_id(),id+1);assert_eq!(worker.object_revision(),row["object_revision"].as_str().unwrap());
        assert_eq!(worker.first_triangle(),row["physics_first_triangle"].as_u64().unwrap() as u32);
        assert_eq!(worker.triangle_count(),row["physics_triangle_count"].as_u64().unwrap() as u32);
        fragiles::Object{object_id:id+1,instance_id:id,chunk_id:chunk,native_index,
            resource:row["resource"].as_str().unwrap().into(),health:row["reference_health"].as_u64().unwrap() as u32,material_kind:73,
            projectile_first_triangle:row["projectile_first_triangle"].as_u64().unwrap() as u32,
            projectile_triangle_count:row["projectile_triangle_count"].as_u64().unwrap() as u32,
            physics_first_triangle:worker.first_triangle(),physics_triangle_count:worker.triangle_count(),object_revision:worker.object_revision().into(),kind:fragiles::ObjectKind::Fragile}
    }).collect();
    let catalog=Arc::new(fragiles::Catalog{map:crate::map_profile091::MapId::Karelia,sha256:INVENTORY_SHA.into(),worker_file:"physics-removals.json".into(),worker_sha256:WORKER_CATALOG_SHA.into(),contacts:false,objects});
    let mut world=World::new(913,now).unwrap();world.bind_geometry(Arc::new(geometry::tests::bundle())).unwrap();
    world.enable_ap_test_lab().unwrap();world.bind_terrain(model::tests::destructible_terrain()).unwrap();world.bind_fragiles(catalog).unwrap();
    for slot in 0..2{world.attach(model::Identity{account:format!("catalog-worker-{slot}"),database:slot+1,name:format!("worker_{slot}")},slot as u32+1).unwrap();}
    world.start(now).unwrap();
    world.rebase_external_spawns([[-402.07458,55.34893,-412.],[-380.,55.34893,-410.]]).unwrap();
    world.set_ready(0,1).unwrap();world.set_ready(1,2).unwrap();
    (world,pool,spec)
}
fn fired_candidate(world:&mut World,now:Instant)->World{
    world.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).unwrap();
    let mut candidate=world.clone();candidate.advance(now+model::STEP).unwrap();
    assert_eq!(world.scene_version(),0);assert_eq!(candidate.scene_version(),1);
    assert_eq!(candidate.fragiles.as_ref().unwrap().removed_ids(),[1514]);
    assert_eq!(candidate.fragiles.as_ref().unwrap().events.len(),1);
    assert_eq!(candidate.terrain_contacts.len(),1);assert!(world.terrain_contacts.is_empty());candidate
}
fn wait_ready(runtime:&mut IntegratedRuntime,slot:usize,deadline:Instant){
    while !runtime.workers[slot].as_ref().unwrap().ready(){
        let at=Instant::now();assert!(at<deadline,"bounded owned worker startup");
        if let Some(state)=runtime.workers[slot].as_mut().unwrap().poll(at).unwrap(){
            assert_eq!(state.seq,0);runtime.anchored[slot]=true;
            runtime.poses[slot]=Some((state.pose.position,state.pose.direction,state.pose.speed));
        }
        std::thread::sleep(Duration::from_millis(2));
    }
}
fn finish(runtime:&mut IntegratedRuntime,world:&mut World,deadline:Instant){
    while runtime.blocked(){assert!(Instant::now()<deadline,"bounded catalog barrier");
        runtime.finish_removal(world,Instant::now()).unwrap();std::thread::sleep(Duration::from_millis(2));}
}
fn proof(name:&str,value:serde_json::Value){
    let directory=local().join("evidence/20261012-p06o-destructible-import-01/boundary");
    let path=directory.join(format!("{name}-{}.json",std::process::id()));
    fs::write(path,serde_json::to_vec_pretty(&value).unwrap()).unwrap();
}

#[test]
fn two_real_catalog_workers_gate_world_until_both_ack_then_restore_new_generation(){
    let now=Instant::now();let (mut world,pool,spec)=fixture(now);let deadline=now+Duration::from_secs(60);
    let mut runtime=IntegratedRuntime::new(pool);runtime.catalog=Some(spec.clone());let map=runtime.map().unwrap();
    for slot in 0..2{runtime.spawn_slot(&world,slot,map.clone(),now).unwrap();wait_ready(&mut runtime,slot,deadline);}
    let pids=runtime.workers.iter().map(|worker|worker.as_ref().unwrap().process_id().unwrap()).collect::<Vec<_>>();
    let candidate=fired_candidate(&mut world,now);let expected=candidate.fragiles.as_ref().unwrap().events.clone();
    let health=world.actors.iter().map(|a|a.health).collect::<Vec<_>>();
    let ammo=world.actors.iter().map(|a|a.fire.ammo()).collect::<Vec<_>>();
    runtime.staged=Some(candidate.clone());assert!(!runtime.ready_for_native());
    runtime.finish_removal(&mut world,Instant::now()).unwrap();
    assert_eq!(world.scene_version(),0);assert!(world.fragiles.as_ref().unwrap().events.is_empty());assert!(world.terrain_contacts.is_empty());
    assert!(runtime.workers.iter().all(|worker|worker.as_ref().unwrap().pending()));
    // Poll ONLY the first worker. The second may have applied its private body
    // change already, but no verified ACK from it has reached the coordinator.
    while runtime.workers[0].as_ref().unwrap().scene_version()!=1{
        assert!(Instant::now()<deadline);assert!(runtime.workers[0].as_mut().unwrap().poll(Instant::now()).unwrap().is_none());
        std::thread::sleep(Duration::from_millis(2));
    }
    assert_eq!(world.scene_version(),0);assert_eq!(runtime.workers[1].as_ref().unwrap().scene_version(),0);
    assert!(runtime.blocked());assert!(!runtime.ready_for_native());
    finish(&mut runtime,&mut world,deadline);
    let scene=Scene::new(&spec,&[1514]).unwrap();
    assert!(runtime.workers.iter().all(|worker|worker.as_ref().unwrap().catalog_scene()==Some(&scene)));
    assert_eq!(world.fragiles.as_ref().unwrap().events,expected);assert_eq!(world.terrain_contacts,candidate.terrain_contacts);
    assert_eq!(world.actors.iter().map(|a|a.health).collect::<Vec<_>>(),health);
    assert_eq!(world.actors.iter().map(|a|a.fire.ammo()).collect::<Vec<_>>(),ammo);
    let identity=world.actors[1].identity.clone();world.detach(2).unwrap();runtime.workers[1].take();runtime.poses[1]=None;
    world.attach(identity,3).unwrap();let later=Instant::now();runtime.spawn_slot(&world,1,map,later).unwrap();
    assert!(!runtime.ready_for_native());assert!(runtime.workers[1].as_ref().unwrap().catalog_scene().is_none());
    wait_ready(&mut runtime,1,deadline);
    let replacement=runtime.workers[1].as_mut().unwrap();
    assert_eq!(replacement.generation,5);assert_eq!(replacement.catalog_scene(),Some(&scene));
    // The new generation's FIRST ready already confirms scene1: no post-ready
    // removal RPC/ACK was needed to repair an old starting collider.
    assert!(replacement.take_catalog_ack().is_none());assert!(!replacement.pending());
    let replacement_pid=replacement.process_id().unwrap();assert_ne!(replacement_pid,pids[1]);
    assert_eq!(world.fragiles.as_ref().unwrap().events,expected);
    proof("catalog-two-real-workers",serde_json::json!({"status":"PASS_CHILD_IPC_ONLY","native_clients":"NOT_RUN",
        "native_indices":"unpublished synthetic unit labels; no native compatibility claim","pool_sha256":POOL_SHA,
        "worker_catalog_sha256":WORKER_CATALOG_SHA,"pids":pids,"replacement_pid":replacement_pid,
        "scene_version":scene.version(),"scene_sha256":scene.hash(),"removed_ids":scene.ids(),
        "world_commit_after_both_ack":true,"restore_before_first_ready":true,"health":health,"ammo":ammo}));
}

#[test]
fn real_catalog_cold_worker_catches_committed_scene_and_membership_change_is_fail_closed(){
    let now=Instant::now();let(mut world,pool,spec)=fixture(now);let deadline=now+Duration::from_secs(60);
    let candidate=fired_candidate(&mut world,now);world.actors[1].ready=false;
    let mut candidate=candidate;candidate.actors[1].ready=false;
    let mut runtime=IntegratedRuntime::new(pool);runtime.catalog=Some(spec.clone());let map=runtime.map().unwrap();
    runtime.spawn_slot(&world,0,map.clone(),now).unwrap();wait_ready(&mut runtime,0,deadline);
    runtime.spawn_slot(&world,1,map,Instant::now()).unwrap();
    // Its unread ready remains queued until the regular path. It supplied no
    // anchor or authoritative pose and cannot enter the native arena yet.
    runtime.staged=Some(candidate.clone());finish(&mut runtime,&mut world,deadline);
    assert_eq!(world.scene_version(),1);assert!(!runtime.workers[1].as_ref().unwrap().ready());
    assert!(!runtime.anchored[1]);assert!(runtime.poses[1].is_none());assert!(!runtime.ready_for_native());
    let scene=Scene::new(&spec,&[1514]).unwrap();
    while runtime.workers[1].as_ref().unwrap().catalog_scene()!=Some(&scene){
        assert!(Instant::now()<deadline);runtime.step(&mut world,Instant::now()).unwrap();
        std::thread::sleep(Duration::from_millis(2));
    }
    assert!(!world.actors[1].ready);assert_eq!(world.fragiles.as_ref().unwrap().events.len(),1);
    // A staged candidate from the old membership can never replace an actor
    // detached while the coordinator was waiting, even if workers already ACKed.
    let(mut changed,_,_)=fixture(now);changed.detach(2).unwrap();runtime.staged=Some(candidate);
    let before=changed.actors.clone();assert!(runtime.finish_removal(&mut changed,Instant::now()).is_err());
    assert_eq!(changed.scene_version(),0);assert_eq!(changed.actors,before);assert!(runtime.blocked());
    proof("catalog-cold-worker",serde_json::json!({"status":"PASS_CHILD_IPC_ONLY","native_clients":"NOT_RUN",
        "cold_worker_excluded_until_pose":true,"caught_up_scene_hash":scene.hash(),"scene_version":1,
        "membership_change_rejected_without_world_commit":true,"event_count":world.fragiles.as_ref().unwrap().events.len()}));
}
