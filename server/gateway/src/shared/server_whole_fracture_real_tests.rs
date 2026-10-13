//! Required private catalog6 workers through the real IPC5 receipt parser,
//! domain fall encoding and both-ACK transaction. No native clients are used.
use super::*;
use super::super::fragiles;
use crate::map_drive_worker091::{CatalogSpec, FractureReceipt, Input as WorkerInput, Pool, Scene, Worker};

const BASE: &str = "evidence/20261013-p05b-tracked-handling-01";
const DOMAIN_SHA: &str = "944ca90d9b8855fbba2206abc0d32138b9807106afb4c5d60c270d2257bd87c8";
const CATALOG_SHA: &str = "6d9a57de3b86f1e3b9a66390ff0968677b9a29e9238ca8559158d99dfb3dce16";
const FORWARD: WorkerInput = WorkerInput { throttle:1, steer:0, brake:false };

struct Case {
    name: &'static str,
    pool_path: &'static str,
    pool_sha: &'static str,
    config_sha: &'static str,
    vehicle: VehicleKind,
    target: u32,
    kind: fragiles::ObjectKind,
}

#[test]
fn real_whole_objects_preserve_receipts_fallen_trees_and_both_ack_barrier() {
    let cases=[
        Case{name:"ms1-tree",pool_path:"ram-gateway-fixtures13/ms1-tree-pool.json",
            pool_sha:"28b57688256a5ca7f21db0df2dbf5251936e78ba4803de4581b06056626bbfb9",
            config_sha:"2032d6a2c1675f76e83472fa88c8fc9d171ecb4d8da24a929e3d9f12a388206c",
            vehicle:VehicleKind::Ms1,target:3680,kind:fragiles::ObjectKind::Tree},
        Case{name:"ms1-crate",pool_path:"ram-gateway-fixtures13/ms1-crate-pool.json",
            pool_sha:"b8ca95a62622707581ce277e0165ce3301bf681f81fd5184ddc31e7d5c4d8956",
            config_sha:"a30d3d3d832ca4218a398c099a705a5c8f2be148af0c97702129806efed88c9d",
            vehicle:VehicleKind::Ms1,target:3618,kind:fragiles::ObjectKind::Fragile},
        Case{name:"is7-tree",pool_path:"ram-gateway-fixtures13/is7-tree-pool.json",
            pool_sha:"5e12497e89aea58cc38bdfc3273c4512445bf78cedd030acce98504346369f4c",
            config_sha:"cbff9473c254757b16a55ecad974d753b0b6496fb7674f53db91c3257f174cb8",
            vehicle:VehicleKind::Is7,target:3680,kind:fragiles::ObjectKind::Tree},
        Case{name:"is7-crate",pool_path:"ram-gateway-fixtures13/is7-crate-pool.json",
            pool_sha:"d6ce6f557aade74c6b8ec7bc2319d82b2ff63d84f7b717f553340b0a133a0daf",
            config_sha:"719bca031fbb6abdb679759569620fa01d906a3b09f240517c66c6b10af6077d",
            vehicle:VehicleKind::Is7,target:3618,kind:fragiles::ObjectKind::Fragile},
    ];
    for case in &cases {run_case(case);}
}

fn dot(a:[f32;3],b:[f32;3])->f64 {
    a.iter().zip(b).map(|(a,b)|f64::from(*a)*f64::from(b)).sum()
}

fn verify_actual_energy(receipt:&FractureReceipt,mass:f32) {
    assert_eq!(receipt.energy_j,8000);
    let closing=dot(receipt.velocity,receipt.normal);
    assert!(closing>=0.1 && 0.5*f64::from(mass)*closing*closing>=8000.);
    for (before,after,shadow) in [(receipt.budget_before,receipt.budget_after,true),
        (receipt.solver_before,receipt.solver_after,false)] {
        let incoming=dot(before,receipt.normal).max(0.);
        let expected=8000f64.min(0.5*f64::from(mass)*incoming*incoming);
        let loss=0.5*f64::from(mass)*(dot(before,before)-dot(after,after));
        assert!((loss-expected).abs()<2.,"actual normal energy: {loss} versus {expected}");
        if shadow {assert!((loss-8000.).abs()<2.);}
        // The response cannot consume tangential momentum or restore a wall
        // impulse. Compare each component after removing the normal impulse.
        let delta=std::array::from_fn(|i|before[i]-after[i]);
        let normal_delta=dot(delta,receipt.normal);
        for i in 0..3 {
            assert!((f64::from(delta[i])-normal_delta*f64::from(receipt.normal[i])).abs()<1e-5);
        }
        assert!(dot(after,after)<=dot(before,before)+1e-5);
    }
}

fn next_state(worker:&mut Worker,deadline:Instant)->crate::map_drive_worker091::State {
    loop {
        assert!(Instant::now()<deadline,"bounded whole-object worker reply");
        if let Some(state)=worker.poll(Instant::now()).unwrap(){return state;}
        std::thread::sleep(Duration::from_millis(2));
    }
}

fn wait_owned_exit(pid:u32,deadline:Instant) {
    // Only the captured child PID is waited on; this never terminates a peer.
    let command=format!("$ErrorActionPreference='Stop'; $p=Get-Process -Id {pid} -ErrorAction SilentlyContinue; if ($null -ne $p) {{ if (-not $p.WaitForExit(5000)) {{ exit 1 }} }}; exit 0");
    let mut process=std::process::Command::new("powershell.exe");
    #[cfg(windows)] {
        use std::os::windows::process::CommandExt;
        process.creation_flags(0x08000000);
    }
    let output=process.args(["-NoProfile","-NonInteractive","-Command",&command]).output().unwrap();
    assert!(output.status.success(),"owned worker exit wait: {}",String::from_utf8_lossy(&output.stderr));
    assert!(Instant::now()<deadline);
}

fn run_case(case:&Case) {
    let local=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
    let base=local.join(BASE);let path=base.join(case.pool_path);
    let metadata=fs::metadata(&path).expect("required pinned whole-object contact pool");
    assert!(metadata.is_file() && metadata.len()<=16_384);
    assert_eq!(format!("{:x}",Sha256::digest(fs::read(&path).unwrap())),case.pool_sha);
    let pool=Arc::new(Pool::load(&local,&path).unwrap());assert_eq!(pool.vehicle_kind(),case.vehicle);
    let map=selected_pool_map(&pool,MapId::Prohorovka).unwrap().clone();
    assert_eq!(map.config_sha256,case.config_sha);assert_eq!(f64::from(map.mass_kg),case.vehicle.mass_kg());
    let spec=CatalogSpec::load(&local,&base.join("ram-import01/physics-removals.json"),CATALOG_SHA).unwrap();
    let catalog=Arc::new(fragiles::Catalog::load(&local,&base.join("ram-import01/manifest.json"),DOMAIN_SHA).unwrap());
    assert_eq!(catalog.version,5);assert_eq!(spec.version(),6);assert_eq!(catalog.worker_sha256,spec.sha256());
    let object=catalog.objects.iter().find(|o|o.object_id==case.target).unwrap();
    let chunk=object.chunk_id;let native_index=object.native_index;
    let entry=spec.entries().iter().find(|o|o.object_id()==case.target).unwrap();
    assert_eq!(object.kind,case.kind);assert_eq!(entry.ram_energy_j(),8000);
    assert_eq!(object.object_revision,entry.object_revision());
    let deadline=Instant::now()+Duration::from_secs(90);
    let empty=Scene::new(&spec,&[]).unwrap();
    // One reference child first, then a pair. No synthetic receipt or domain
    // collision seeds this test, and no more than two owned workers coexist.
    let mut reference=Worker::launch_with_catalog(pool.clone(),map.clone(),1,Instant::now(),None,
        spec.clone(),empty.clone()).unwrap();
    assert_eq!(next_state(&mut reference,deadline).seq,0);
    let reference_pid=reference.process_id().unwrap();let mut actual=None;
    for advance in 1..=60 {
        assert_eq!(reference.advance(FORWARD,Instant::now()).unwrap(),advance);
        let state=next_state(&mut reference,deadline);assert_eq!(state.seq,advance);
        if !state.fractures.is_empty() {
            assert_eq!(state.fractures.len(),1,"first source contact must be the pinned target");
            let receipt=state.fractures[0].clone();assert_eq!(receipt.object_id,case.target);
            verify_actual_energy(&receipt,map.mass_kg);
            assert_eq!(reference.prepared_ids(),&[case.target]);
            assert!(reference.advance(FORWARD,Instant::now()).is_err());
            // This otherwise valid, extending scene omits the real proposal.
            let other=spec.entries().iter().find(|e|e.object_id()!=case.target).unwrap().object_id();
            assert!(reference.sync_removed(Scene::new(&spec,&[other]).unwrap(),Instant::now()).is_err());
            assert_eq!(reference.catalog_scene(),Some(&empty));
            assert_eq!(reference.prepared_ids(),&[case.target]);
            actual=Some((advance,receipt));break;
        }
    }
    let (sequence,receipt)=actual.expect("bounded real source target contact");
    drop(reference);wait_owned_exit(reference_pid,deadline);
    let begin=Instant::now();
    let mut world=World::new_for_vehicle(918,begin,MapId::Prohorovka,case.vehicle).unwrap();
    world.impact.bind_fragiles(catalog.clone()).unwrap();world.fragiles=Some(fragiles::State::new(catalog));
    for slot in 0..2 {world.attach(model::Identity{account:format!("whole-real-{slot}"),database:slot+1,
        name:format!("whole_{slot}")},slot as u32+1).unwrap();}
    world.start(begin).unwrap();world.rebase_external_spawns([map.spawn;2]).unwrap();
    for slot in 0..2 {world.set_ready(slot,slot as u32+1).unwrap();world.actors[slot].input=model::Input{throttle:1,steer:0};}
    let mut runtime=IntegratedRuntime::new_for_map(pool,MapId::Prohorovka);
    runtime.catalog=Some(spec.clone());runtime.started=true;
    for slot in 0..2 {
        runtime.workers[slot]=Some(Worker::launch_with_catalog(runtime.pool.clone(),map.clone(),slot as u32+2,
            Instant::now(),None,spec.clone(),empty.clone()).unwrap());
        runtime.worker_sessions[slot]=world.actors[slot].session;
    }
    let mut committed=false;
    while !committed {
        assert!(Instant::now()<deadline,"bounded whole-object runtime transaction");
        assert!(runtime.contact_sequences.iter().all(|seq|*seq<=60));
        let before=world.clone();runtime.step(&mut world,Instant::now()).unwrap();
        if let Some(candidate)=runtime.staged.clone() {
            assert_eq!(world.actors,before.actors);assert_eq!(world.fragiles,before.fragiles);
            assert_eq!(world.scene_version(),0);assert!(!runtime.ready_for_native());
            let state=candidate.fragiles.as_ref().unwrap();assert_eq!(state.removed_ids(),vec![case.target]);
            assert_eq!(runtime.contact_sequences,[sequence;2]);assert_eq!(state.vehicle_events.len(),1);
            let event=&state.vehicle_events[0];
            assert_eq!(event.object_id,receipt.object_id);assert_eq!(event.substep,receipt.substep);
            assert_eq!(event.point,receipt.point);assert_eq!(event.normal,receipt.normal);assert_eq!(event.velocity,receipt.velocity);
            assert_eq!(event.mass_kg,map.mass_kg);assert_eq!(event.kind,"hull");assert_eq!(event.shooter,0);
            if matches!(case.kind,fragiles::ObjectKind::Tree) {
                let value=event.fallen_tree.expect("actual tree contact must encode fallenTrees");
                assert_eq!(state.native_fallen_trees(chunk),vec![value]);assert!(state.native_destroyed(chunk).is_empty());
            } else {
                assert!(event.fallen_tree.is_none());assert!(state.native_fallen_trees(chunk).is_empty());
                assert_eq!(state.native_destroyed(chunk),vec![native_index]);
                assert_eq!(state.native_fragile_values(chunk),vec![u16::from(native_index)<<8]);
            }
            let target=Scene::new(&spec,&[case.target]).unwrap();
            for worker in &mut runtime.workers {
                assert_eq!(worker.as_ref().unwrap().prepared_ids(),&[case.target]);
                assert!(worker.as_mut().unwrap().advance(FORWARD,Instant::now()).is_err());
            }
            // B's ACK may be queued by its child but remains unconsumed. Only
            // A is acknowledged here, so no world/native state may publish.
            while runtime.workers[0].as_ref().unwrap().catalog_scene()!=Some(&target) {
                assert!(Instant::now()<deadline);
                assert!(runtime.workers[0].as_mut().unwrap().poll(Instant::now()).unwrap().is_none());
                std::thread::sleep(Duration::from_millis(2));
            }
            assert_eq!(world.actors,before.actors);assert_eq!(world.fragiles,before.fragiles);
            assert!(world.fragiles.as_ref().unwrap().native_fallen_trees(chunk).is_empty());
            assert!(world.fragiles.as_ref().unwrap().native_destroyed(chunk).is_empty());
            assert_ne!(runtime.workers[1].as_ref().unwrap().catalog_scene(),Some(&target));
            assert!(!runtime.ready_for_native());
            while runtime.staged.is_some() {
                assert!(Instant::now()<deadline);runtime.finish_catalog(&mut world,Instant::now()).unwrap();
                std::thread::sleep(Duration::from_millis(2));
            }
            assert_eq!(world.actors,candidate.actors);assert_eq!(world.fragiles,candidate.fragiles);
            assert_eq!(world.scene_version(),1);
            assert!(runtime.workers.iter().all(|w|w.as_ref().unwrap().catalog_scene()==Some(&target)
                && w.as_ref().unwrap().prepared_ids().is_empty()));
            committed=true;
        }
        std::thread::sleep(Duration::from_millis(2));
    }
    let pids=runtime.workers.iter().map(|w|w.as_ref().unwrap().process_id().unwrap()).collect::<Vec<_>>();
    let proof=serde_json::json!({"status":"PASS_REAL_WHOLE_OBJECT_RECEIPT_DOMAIN_BOTH_ACK","case":case.name,
        "native_clients":"NOT_RUN","full_passage":"NOT_ASSERTED","initial_removed_ids":[],
        "pool_sha256":case.pool_sha,"config_sha256":case.config_sha,"domain_sha256":DOMAIN_SHA,"catalog_sha256":CATALOG_SHA,
        "reference_pid":reference_pid,"pids":pids,"mass_kg":map.mass_kg,"target":case.target,
        "advance_sequence":sequence,"world_unchanged_until_both_ack":true,"advance_before_ack_rejected":true,
        "omitted_proposal_scene_rejected":true,"fallenTrees":world.fragiles.as_ref().unwrap().native_fallen_trees(chunk),
        "native_destroyed":world.fragiles.as_ref().unwrap().native_destroyed(chunk),
        "receipt":{"object_id":receipt.object_id,"substep":receipt.substep,"order":receipt.order,
            "point":receipt.point,"normal":receipt.normal,"velocity":receipt.velocity,"energy_j":receipt.energy_j,
            "budget_before":receipt.budget_before,"budget_after":receipt.budget_after,
            "solver_before":receipt.solver_before,"solver_after":receipt.solver_after}});
    drop(runtime);for pid in pids {wait_owned_exit(pid,deadline);}
    let evidence=base.join("ram-gateway-real");fs::create_dir_all(&evidence).unwrap();
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let mut file=fs::OpenOptions::new().write(true).create_new(true)
        .open(evidence.join(format!("{}-{}-{stamp}.json",case.name,std::process::id()))).unwrap();
    std::io::Write::write_all(&mut file,&serde_json::to_vec_pretty(&proof).unwrap()).unwrap();
}
