//! Pinned IS-7 private workers through receipt parsing and the actual world
//! transaction. This proves neither native visuals nor complete fence passage.
use super::*;
use super::super::fragiles;
use crate::map_drive_worker091::{CatalogSpec, FractureReceipt, Input as WorkerInput, Scene, Worker};

const BASE: &str = "evidence/20261013-p03m-is7-01";
const CATALOG_BASE: &str = "evidence/20261013-p06r-compound-01/import/fence-response01";
const DOMAIN_SHA: &str = "39bb68815dd2d7ca54789a1cc71be619cc4f2f5cf351bf52f22de92f2afca11d";
const CATALOG_SHA: &str = "0a7c8fd70f00c8c49c3282ac1fe574281f384d042b1adb7da549d1680c192ef9";
const TARGETS: [u32; 2] = [3307,3308];
const MASS: f32 = 68190.;
const FORWARD: WorkerInput = WorkerInput { throttle:1, steer:0, brake:false };

fn dot(a:[f32;3],b:[f32;3])->f64 {
    a.iter().zip(b).map(|(a,b)|f64::from(*a)*f64::from(b)).sum()
}

fn verify_actual_energy(receipt:&FractureReceipt) {
    assert_eq!(receipt.energy_j,8000);
    let closing=dot(receipt.velocity,receipt.normal);
    assert!(closing>=0.1 && 0.5*f64::from(MASS)*closing*closing>=8000.);
    // Independent conservation check on actual C# outputs: shadow admission
    // costs 8kJ, while a solid solver contact may leave less normal energy to
    // debit. The post-solver response must never refund that lost velocity.
    for (before,after,shadow) in [(receipt.budget_before,receipt.budget_after,true),
        (receipt.solver_before,receipt.solver_after,false)] {
        let incoming=dot(before,receipt.normal).max(0.);
        let expected=8000f64.min(0.5*f64::from(MASS)*incoming*incoming);
        let loss=0.5*f64::from(MASS)*(dot(before,before)-dot(after,after));
        assert!((loss-expected).abs()<2.,"actual 68190kg energy: {loss} versus {expected}");
        if shadow {assert!((loss-8000.).abs()<2.);}
    }
}

fn next_state(worker:&mut Worker,deadline:Instant)->crate::map_drive_worker091::State {
    loop {
        assert!(Instant::now()<deadline,"bounded IS-7 worker reply");
        if let Some(state)=worker.poll(Instant::now()).unwrap(){return state;}
        std::thread::sleep(Duration::from_millis(2));
    }
}

fn wait_owned_exit(pid:u32,deadline:Instant) {
    // Drop reaps asynchronously. Wait for this captured owned PID before
    // starting the pair, so this case itself never owns three live workers.
    // This fixture targets the pinned Windows platform, like its .exe assets.
    assert!(Instant::now()<deadline);
    let command=format!("$ErrorActionPreference='Stop'; $p=Get-Process -Id {pid} -ErrorAction SilentlyContinue; if ($null -ne $p) {{ if (-not $p.WaitForExit(5000)) {{ exit 1 }} }}; exit 0");
    let mut process=std::process::Command::new("powershell.exe");
    #[cfg(windows)] {
        use std::os::windows::process::CommandExt;
        process.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }
    let output=process.args(["-NoProfile","-NonInteractive","-Command",&command]).output().unwrap();
    assert!(output.status.success(),"owned worker exit wait: {}",String::from_utf8_lossy(&output.stderr));
    assert!(Instant::now()<deadline);
}

#[test]
fn real_is7_receipts_match_domain_and_world_waits_for_both_scene_acks() {
    let local=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
    let base=local.join(BASE);
    // Exact archived pool/config/profile pins precede test-only path relocation.
    // The production loader still validates the derived local pool and assets.
    let pool=Arc::new(worker_fixtures::p03m());assert_eq!(pool.vehicle_kind(),VehicleKind::Is7);
    let map=selected_pool_map(&pool,MapId::Prohorovka).unwrap().clone();
    assert_eq!(map.mass_kg,MASS);
    assert_eq!(VehicleKind::Is7.mass_kg(),f64::from(MASS));
    let spec=CatalogSpec::load(&local,&local.join(CATALOG_BASE).join("physics-removals.json"),CATALOG_SHA).unwrap();
    let catalog=Arc::new(fragiles::Catalog::load(&local,&local.join(CATALOG_BASE).join("manifest.json"),DOMAIN_SHA).unwrap());
    assert_eq!(catalog.version,4);assert_eq!(spec.version(),5);assert_eq!(catalog.worker_sha256,spec.sha256());
    for id in TARGETS {
        let object=catalog.objects.iter().find(|o|o.object_id==id).unwrap();
        let entry=spec.entries().iter().find(|o|o.object_id()==id).unwrap();
        assert_eq!(object.kind,fragiles::ObjectKind::MovementFragile);
        assert_eq!(object.object_revision,entry.object_revision());assert_eq!(entry.ram_energy_j(),8000);
    }
    let deadline=Instant::now()+Duration::from_secs(90);
    let empty=Scene::new(&spec,&[]).unwrap();
    // First, collect fresh real receipts through the public Rust parser. This
    // worker is dropped before the two arena workers start (max two at once).
    let mut reference=Worker::launch_with_catalog(pool.clone(),map.clone(),1,Instant::now(),None,spec.clone(),empty.clone()).unwrap();
    assert_eq!(next_state(&mut reference,deadline).seq,0);
    let reference_pid=reference.process_id().unwrap();
    let mut receipts=Vec::new();let mut removed=Vec::new();
    for advance in 1..=48 {
        assert_eq!(reference.advance(FORWARD,Instant::now()).unwrap(),advance);
        let state=next_state(&mut reference,deadline);assert_eq!(state.seq,advance);
        for receipt in state.fractures {
            assert!(receipts.len()<TARGETS.len(),"unexpected extra fracture");
            assert_eq!(receipt.object_id,TARGETS[receipts.len()]);verify_actual_energy(&receipt);
            removed.push(receipt.object_id);receipts.push((advance,receipt));
        }
        if !reference.prepared_ids().is_empty() {
            assert!(reference.advance(FORWARD,Instant::now()).is_err());
            let scene=Scene::new(&spec,&removed).unwrap();reference.sync_removed(scene.clone(),Instant::now()).unwrap();
            while reference.catalog_scene()!=Some(&scene) {
                assert!(Instant::now()<deadline);
                assert!(reference.poll(Instant::now()).unwrap().is_none());
                std::thread::sleep(Duration::from_millis(2));
            }
            assert!(reference.take_catalog_ack().is_some());assert!(reference.prepared_ids().is_empty());
        }
        if receipts.len()==TARGETS.len(){break;}
    }
    assert_eq!(removed,TARGETS);drop(reference);wait_owned_exit(reference_pid,deadline);
    let begin=Instant::now();let mut world=World::new_for_vehicle(917,begin,MapId::Prohorovka,VehicleKind::Is7).unwrap();
    // Movement-only: source physics geometry is bound by Pool2 and catalog;
    // projectile bundle/shot/HP have separate actual source-mesh tests.
    world.impact.bind_fragiles(catalog.clone()).unwrap();world.fragiles=Some(fragiles::State::new(catalog));
    for slot in 0..2 {world.attach(model::Identity {account:format!("is7-real-{slot}"),database:slot+1,
        name:format!("is7_{slot}")},slot as u32+1).unwrap();}
    world.start(begin).unwrap();world.rebase_external_spawns([map.spawn;2]).unwrap();
    for slot in 0..2 {world.set_ready(slot,slot as u32+1).unwrap();world.actors[slot].input=model::Input{throttle:1,steer:0};
        assert_eq!(world.actors[slot].vehicle_kind(),VehicleKind::Is7);assert_eq!(world.actors[slot].health,2150);
        assert_eq!(world.actors[slot].fire.ammo(),30);}
    let mut runtime=IntegratedRuntime::new_for_map(pool,MapId::Prohorovka);runtime.catalog=Some(spec.clone());runtime.started=true;
    for slot in 0..2 {
        runtime.workers[slot]=Some(Worker::launch_with_catalog(runtime.pool.clone(),map.clone(),slot as u32+2,
            Instant::now(),None,spec.clone(),empty.clone()).unwrap());
        runtime.worker_sessions[slot]=world.actors[slot].session;
    }
    let mut commits=Vec::new();
    while commits.len()<TARGETS.len() {
        assert!(Instant::now()<deadline,"bounded IS-7 runtime transaction");
        assert!(runtime.contact_sequences.iter().all(|seq|*seq<=48));
        let before=world.clone();runtime.step(&mut world,Instant::now()).unwrap();
        if let Some(candidate)=runtime.staged.clone() {
            assert_eq!(world.actors,before.actors);assert_eq!(world.fragiles,before.fragiles);assert!(!runtime.ready_for_native());
            let ids=candidate.fragiles.as_ref().unwrap().removed_ids();assert_eq!(ids,TARGETS[..commits.len()+1]);
            let target=Scene::new(&spec,&ids).unwrap();let (sequence,receipt)=&receipts[commits.len()];
            assert_eq!(runtime.contact_sequences,[*sequence;2]);
            let event=candidate.fragiles.as_ref().unwrap().vehicle_events.last().unwrap();
            assert_eq!(event.object_id,receipt.object_id);assert_eq!(event.substep,receipt.substep);
            assert_eq!(event.point,receipt.point);assert_eq!(event.normal,receipt.normal);assert_eq!(event.velocity,receipt.velocity);
            assert_eq!(event.mass_kg,MASS);assert_eq!(event.kind,"hull");assert_eq!(event.shooter,0);
            let prepared=runtime.workers.iter().map(|w|w.as_ref().unwrap().prepared_ids().to_vec()).collect::<Vec<_>>();
            assert_eq!(prepared,vec![vec![receipt.object_id];2]);
            for worker in &mut runtime.workers {assert!(worker.as_mut().unwrap().advance(FORWARD,Instant::now()).is_err());}
            // A's real ACK alone cannot publish the new pose or remove the
            // object from World; leave B's independently queued ACK unconsumed.
            while runtime.workers[0].as_ref().unwrap().catalog_scene()!=Some(&target) {
                assert!(Instant::now()<deadline);
                assert!(runtime.workers[0].as_mut().unwrap().poll(Instant::now()).unwrap().is_none());
                std::thread::sleep(Duration::from_millis(2));
            }
            assert_eq!(world.actors,before.actors);assert_eq!(world.fragiles,before.fragiles);
            assert_ne!(runtime.workers[1].as_ref().unwrap().catalog_scene(),Some(&target));assert!(!runtime.ready_for_native());
            while runtime.staged.is_some() {
                assert!(Instant::now()<deadline);runtime.finish_catalog(&mut world,Instant::now()).unwrap();
                std::thread::sleep(Duration::from_millis(2));
            }
            assert_eq!(world.actors,candidate.actors);assert_eq!(world.fragiles,candidate.fragiles);
            assert_eq!(world.fragiles.as_ref().unwrap().vehicle_events.len(),ids.len());
            assert!(runtime.workers.iter().all(|w|w.as_ref().unwrap().catalog_scene()==Some(&target)
                && w.as_ref().unwrap().prepared_ids().is_empty()));
            commits.push(serde_json::json!({"scene_version":target.version(),"scene_sha256":target.hash(),"removed_ids":ids,
                "prepared_per_slot":prepared,"advance_sequences":runtime.contact_sequences,"world_unchanged_until_both_ack":true,
                "receipt":{"object_id":receipt.object_id,"substep":receipt.substep,"order":receipt.order,"point":receipt.point,
                    "normal":receipt.normal,"velocity":receipt.velocity,"energy_j":receipt.energy_j,
                    "budget_before":receipt.budget_before,"budget_after":receipt.budget_after,
                    "solver_before":receipt.solver_before,"solver_after":receipt.solver_after}}));
        }
        std::thread::sleep(Duration::from_millis(2));
    }
    assert_eq!(world.scene_version(),2);assert_eq!(world.fragiles.as_ref().unwrap().vehicle_events.len(),2);
    let pids=runtime.workers.iter().map(|w|w.as_ref().unwrap().process_id().unwrap()).collect::<Vec<_>>();
    let proof=serde_json::json!({"status":"PASS_REAL_IS7_RECEIPT_RUNTIME_DOMAIN_BOTH_ACK","native_clients":"NOT_RUN",
        "full_fence_passage":"NOT_ASSERTED","source_pool_sha256":worker_fixtures::P03M_SOURCE_SHA,
        "source_config_sha256":worker_fixtures::P03M_CONFIG_SHA,"derived_pool_sha256":runtime.pool.sha256,
        "derived_config_sha256":map.config_sha256,"domain_sha256":DOMAIN_SHA,
        "catalog_sha256":CATALOG_SHA,"reference_pid":reference_pid,"pids":pids,"mass_kg":MASS,"vehicle_kind":"is7",
        "owned_exit_wait":"PASS",
        "commits":commits,"final_positions":world.actors.iter().map(|a|a.position).collect::<Vec<_>>()});
    drop(runtime);for pid in pids {wait_owned_exit(pid,deadline);}
    let evidence=base.join("gateway-real01");fs::create_dir_all(&evidence).unwrap();
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let mut file=fs::OpenOptions::new().write(true).create_new(true)
        .open(evidence.join(format!("result-{}-{stamp}.json",std::process::id()))).unwrap();
    std::io::Write::write_all(&mut file,&serde_json::to_vec_pretty(&proof).unwrap()).unwrap();
}
