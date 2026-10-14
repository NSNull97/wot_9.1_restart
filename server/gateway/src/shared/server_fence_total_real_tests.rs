//! Version7 projection and coordinator negatives use explicit synthetic IPC.
//! Separately pinned actual-worker tests below do not establish native acceptance.
use super::*;
use super::super::fragiles;
use crate::map_drive_worker091::{self as drive,controlled_ipc,CatalogSpec,Scene};
use serde_json::{json,Value};

const BASE:&str="evidence/20261013-p05b-tracked-handling-01";
const DOMAIN_SHA:&str="9f54f371441a825c4d3f0dbd975e82a8c9644470d63188421a130e6639918165";
const WORKER_SHA:&str="9c40f5bdeb8b77364805f31f18a9c6943a811630f7676fd10c6ec55d8ec5fd5e";

fn load_value(value:&Value)->CatalogSpec {
    static NEXT:std::sync::atomic::AtomicUsize=std::sync::atomic::AtomicUsize::new(0);
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
    let parent=root.join(BASE).join("night-fence-gateway-tests");fs::create_dir_all(&parent).unwrap();
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let dir=parent.join(format!("schema-{}-{stamp}-{}",std::process::id(),NEXT.fetch_add(1,std::sync::atomic::Ordering::Relaxed)));
    fs::create_dir(&dir).unwrap();let path=dir.join("worker.json");let raw=serde_json::to_vec(value).unwrap();
    let mut file=fs::OpenOptions::new().write(true).create_new(true).open(&path).unwrap();
    std::io::Write::write_all(&mut file,&raw).unwrap();drop(file);
    CatalogSpec::load(&root,&path,&format!("{:x}",Sha256::digest(raw))).unwrap()
}

fn worker_manifest(c:&fragiles::Catalog)->Value {
    json!({"version":7,"profile":"test_lab","map":c.map.asset(),"contacts":true,
        "physics_manifest_sha256":c.map.spec().physics_manifest_sha256,
        "projectile_manifest_sha256":c.map.spec().projectile_manifest_sha256,
        "ram_policy":fragiles::FENCE_TOTAL_RAM_POLICY,
        "objects":c.objects.iter().map(|o|json!({"object_id":o.object_id,"instance_id":o.instance_id,
            "first_triangle":o.physics_first_triangle,"triangle_count":o.physics_triangle_count,
            "object_revision":o.object_revision,"kind":o.kind.worker_kind(),"ram_energy_j":8000,
            "ram_response":c.ram_response(o).unwrap()})).collect::<Vec<_>>()})
}

#[test]
fn fence_total_projection_compares_discriminator_identity_geometry_and_hash() {
    let mut catalog=(*fragiles::tests::fence_total_catalog()).clone();
    let v=worker_manifest(&catalog);let good=load_value(&v);catalog.worker_sha256=good.sha256().into();
    validate_catalog_projection(&catalog,&good,MapId::Karelia).unwrap();
    for (field,value) in [("ram_response",json!("normal_linear")),("object_revision",json!("a".repeat(64))),
        ("first_triangle",json!(171815)),("triangle_count",json!(41))]{
        let mut invalid=v.clone();invalid["objects"][1][field]=value;let bad=load_value(&invalid);
        let mut adjusted=catalog.clone();adjusted.worker_sha256=bad.sha256().into();
        assert!(validate_catalog_projection(&adjusted,&bad,MapId::Karelia).is_err(),"projection accepted {field}");
    }
    let mut forged=catalog.clone();forged.worker_sha256="0".repeat(64);
    assert!(validate_catalog_projection(&forged,&good,MapId::Karelia).is_err());
    assert!(validate_catalog_projection(&catalog,&good,MapId::Prohorovka).is_err());
    // Ordinary fragile and fence share worker kind. It must not erase the
    // policy discriminator at this domain-to-worker boundary.
    let mut invalid=v.clone();invalid["objects"][0]["ram_response"]=json!("total_linear");let bad=load_value(&invalid);
    catalog.worker_sha256=bad.sha256().into();assert!(validate_catalog_projection(&catalog,&bad,MapId::Karelia).is_err());
}

#[test]
fn fence_total_imported_catalog_preserves_all1038_exact_projected_entries() {
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();let base=root.join(BASE).join("night-fence-export01/catalog");
    let domain=fragiles::Catalog::load(&root,&base.join("manifest.json"),DOMAIN_SHA).unwrap();
    let worker=CatalogSpec::load(&root,&base.join("physics-removals.json"),WORKER_SHA).unwrap();
    validate_catalog_projection(&domain,&worker,MapId::Prohorovka).unwrap();assert_eq!((domain.version,worker.version()),(6,7));
    assert_eq!((domain.objects.len(),domain.area_chunks.len()),(1038,119));
    assert_eq!(domain.objects.iter().filter(|o|domain.ram_response(o)==Some("total_linear")).count(),403);
    assert_eq!(domain.objects.iter().filter(|o|domain.ram_response(o)==Some("normal_linear")).count(),635);
    assert!(worker.entries().iter().all(|e|e.ram_energy_j()==8000));
}

struct Barrier {world:World,runtime:IntegratedRuntime,peers:[controlled_ipc::Peer;2],map:drive::MapSpec,spec:CatalogSpec}
impl Barrier {
    fn new(now:Instant)->Self {
        let mut catalog=(*fragiles::tests::fence_total_catalog()).clone();let spec=load_value(&worker_manifest(&catalog));catalog.worker_sha256=spec.sha256().into();
        validate_catalog_projection(&catalog,&spec,MapId::Karelia).unwrap();let catalog=Arc::new(catalog);
        let mut world=model::tests::world(now);world.impact.bind_fragiles(catalog.clone()).unwrap();world.fragiles=Some(fragiles::State::new(catalog));
        let map=drive::tests::map();let mut runtime=IntegratedRuntime::new(controlled_ipc::pool(map.clone()));runtime.catalog=Some(spec.clone());runtime.started=true;
        let scene=Scene::new(&spec,&[]).unwrap();
        let peers=std::array::from_fn(|slot| {let(worker,peer)=controlled_ipc::ready(map.clone(),slot as u32+2,spec.clone(),scene.clone(),now);
            runtime.workers[slot]=Some(worker);runtime.worker_sessions[slot]=world.actors[slot].session;runtime.anchored[slot]=true;
            runtime.poses[slot]=Some((world.actors[slot].position,world.actors[slot].direction,0.));peer});
        Self{world,runtime,peers,map,spec}
    }
    fn dispatch(&mut self,now:Instant){self.runtime.step(&mut self.world,now).unwrap();for peer in &self.peers {assert_eq!(peer.request()["seq"],1);}}
    fn frame(&self,slot:usize,prepared:bool)->Value {
        let worker=self.runtime.workers[slot].as_ref().unwrap();let scene=worker.catalog_scene().unwrap();
        let velocity=[0.1f32,0.,3.];let e=0.5*f64::from(self.map.mass_kg)*velocity.iter().map(|v|f64::from(*v).powi(2)).sum::<f64>();
        assert!(e>8000.);let factor=(1.-8000./e).sqrt();let after=velocity.map(|v|(f64::from(v)*factor)as f32);
        let contacts=if prepared{json!([{"object_id":1514,"kind":"hull","substep":1,"point":[0.,0.,0.],"normal":[1.,0.,0.],"velocity":velocity}])}else{json!([])};
        let fractures=if prepared{json!([{"object_id":1514,"substep":1,"order":1,"point":[0.,0.,0.],"normal":[1.,0.,0.],"velocity":velocity,
            "budget_before":velocity,"budget_after":after,"solver_before":[0.,0.,0.],"solver_after":[0.,0.,0.],"energy_j":8000}])}else{json!([])};
        json!({"version":5,"event":if prepared{"prepared"}else{"state"},"seq":1,"tick":186,"settle_ticks":180,
            "map":self.map.asset,"config_sha256":self.map.config_sha256,"generation":worker.generation,"catalog_sha256":self.spec.sha256(),
            "contacts":true,"scene_version":scene.version(),"scene_sha256":scene.hash(),"state":{"position":self.world.actors[slot].position,
                "direction":self.world.actors[slot].direction,"speed":0.,"rspeed":0.,"contacts":6,"linear_velocity":[0.,0.,0.],"angular_velocity":[0.,0.,0.],
                "wheel_contact_masks":[63,63,63,63,63,63],"object_contacts":contacts,"fractures":fractures}})
    }
    fn ack(&self,slot:usize,request:&Value,now:Instant){let mut ack=request.clone();let a=ack.as_object_mut().unwrap();a.remove("op");a.insert("event".into(),json!("scene_synced"));a.insert("tick".into(),json!(180+request["advance_seq"].as_u64().unwrap()*6));self.peers[slot].reply(now,&ack);}
    fn step(&mut self,now:Instant){self.runtime.step(&mut self.world,now).unwrap();}
}

#[test]
fn fence_total_prepared_waits_for_peer_and_both_acks_without_wall_refund() {
    for first in 0..2 {let now=Instant::now();let mut f=Barrier::new(now);f.dispatch(now);let before=f.world.clone();
        f.peers[first].reply(now+Duration::from_millis(1),&f.frame(first,true));f.step(now+Duration::from_millis(2));
        assert!(f.runtime.blocked());assert!(f.runtime.staged.is_none());assert_eq!(f.world.fragiles,before.fragiles);assert_eq!(f.world.actors,before.actors);
        assert!(f.runtime.workers[first].as_mut().unwrap().advance(drive::Input::STOP,now+Duration::from_millis(2)).is_err());
        f.peers[1-first].reply(now+Duration::from_millis(3),&f.frame(1-first,true));f.step(now+Duration::from_millis(4));
        assert_eq!(f.runtime.staged.as_ref().unwrap().scene_version(),1);let requests=[f.peers[0].request(),f.peers[1].request()];
        f.ack(first,&requests[first],now+Duration::from_millis(5));f.step(now+Duration::from_millis(6));assert_eq!(f.world.fragiles,before.fragiles);
        f.ack(1-first,&requests[1-first],now+Duration::from_millis(7));f.step(now+Duration::from_millis(8));
        let s=f.world.fragiles.as_ref().unwrap();assert_eq!(s.vehicle_events.len(),1);assert_eq!(s.removed_ids(),vec![1514]);assert_eq!(s.native_fragile_values(31354),vec![1<<8]);
        assert!(f.world.actors.iter().all(|a|a.speed==0.));assert!(!f.runtime.blocked());
    }
}

#[test]
fn fence_total_retained_generation_and_wrong_scene_ack_fail_before_publication() {
    for generation in [true,false] {let now=Instant::now();let mut f=Barrier::new(now);f.dispatch(now);let before=f.world.clone();
        f.peers[0].reply(now+Duration::from_millis(1),&f.frame(0,true));f.step(now+Duration::from_millis(2));
        if generation {f.runtime.workers[0].as_mut().unwrap().generation+=2;}
        f.peers[1].reply(now+Duration::from_millis(3),&f.frame(1,false));
        if generation {assert!(f.runtime.step(&mut f.world,now+Duration::from_millis(4)).is_err());}
        else {f.step(now+Duration::from_millis(4));let mut request=f.peers[0].request();let _=f.peers[1].request();request["generation"]=json!(999);
            f.ack(0,&request,now+Duration::from_millis(5));assert!(f.runtime.step(&mut f.world,now+Duration::from_millis(6)).is_err());}
        assert_eq!(f.world.fragiles,before.fragiles);assert_eq!(f.world.actors,before.actors);
    }
}

#[test]
fn fence_total_rejoin_restores_scene_but_does_not_grant_native_ready() {
    for corrupt_ack in [false,true] {
        let now=Instant::now();let mut f=Barrier::new(now);
        f.world.apply_vehicle_contacts(&[model::VehicleContactInput {object_id:1514,shooter:0,substep:1,
            point:[0.;3],normal:[1.,0.,0.],velocity:[0.1,0.,3.],mass_kg:f.map.mass_kg,kind:"hull".into(),proof:None}]).unwrap();
        f.world.advance(now+drive::STEP).unwrap();let committed=f.world.fragiles.clone();
        let scene=Scene::new(&f.spec,&[1514]).unwrap();
        let(worker,peer)=controlled_ipc::ready(f.map.clone(),2,f.spec.clone(),scene,now+drive::STEP);
        f.runtime.workers[0]=Some(worker);f.peers[0]=peer;
        f.world.actors[1].ready=false;f.runtime.poses[1]=None;f.runtime.anchored[1]=false;
        f.step(now+drive::STEP);assert!(f.runtime.synchronizing[1]);assert!(!f.runtime.ready_for_native());
        let mut restore=f.peers[1].request();assert_eq!(restore["removed_object_ids"],json!([1514]));
        assert!(f.runtime.workers[1].as_mut().unwrap().advance(drive::Input::STOP,now+drive::STEP).is_err());
        if corrupt_ack {restore["scene_sha256"]=json!("0".repeat(64));}
        f.ack(1,&restore,now+drive::STEP+Duration::from_millis(1));
        let result=f.runtime.step(&mut f.world,now+drive::STEP+Duration::from_millis(2));
        if corrupt_ack {assert!(result.is_err());}else{result.unwrap();assert!(!f.runtime.synchronizing[1]);}
        assert!(!f.world.actors[1].ready);assert_eq!(f.world.fragiles,committed);
    }
}

fn actual_next(worker:&mut drive::Worker,deadline:Instant)->drive::State {
    loop {assert!(Instant::now()<deadline,"bounded actual fence reply");
        if let Some(state)=worker.poll(Instant::now()).unwrap(){return state;}
        std::thread::sleep(Duration::from_millis(2));}
}
fn actual_exit(pid:u32) {
    let mut cmd=std::process::Command::new("powershell.exe");
    #[cfg(windows)] {use std::os::windows::process::CommandExt;cmd.creation_flags(0x08000000);}
    let script=format!("$p=Get-Process -Id {pid} -ErrorAction SilentlyContinue; if ($null -ne $p -and -not $p.WaitForExit(5000)) {{ exit 1 }}; exit 0");
    assert!(cmd.args(["-NoProfile","-NonInteractive","-Command",&script]).status().unwrap().success());
}
fn dot64(a:[f32;3],b:[f32;3])->f64{a.iter().zip(b).map(|(a,b)|f64::from(*a)*f64::from(b)).sum()}
fn actual_radial(r:&drive::FractureReceipt,mass:f32) {
    assert_eq!((r.object_id,r.energy_j),(3167,8000));assert!(dot64(r.velocity,r.normal)>=0.1);
    assert!(0.5*f64::from(mass)*dot64(r.velocity,r.velocity)>=8000.);
    for (before,after) in [(r.budget_before,r.budget_after),(r.solver_before,r.solver_after)] {
        let energy=0.5*f64::from(mass)*dot64(before,before);
        let expected=if energy<=8000.{[0.;3]}else{before.map(|v|(f64::from(v)*(1.-8000./energy).sqrt())as f32)};
        assert_eq!(after,expected);assert!(dot64(after,after)<=dot64(before,before));
    }
}

#[test]
fn fence_total_actual_source_profiles_commit_only_after_both_ack_and_restore_on_rejoin() {
    let cases=[("ms1",VehicleKind::Ms1,"57e2133cdcdb8bdbda2bb671159c55d7a9782c732ee66f743bfdaf5d851b66d8",
        "312c6cf7c8a0609319e40da79557ce4d84e590bef990e0e241b62a833dba9cff",91u32),
        ("is7",VehicleKind::Is7,"f48defe4388fbf5930f54b026b337927a944c9c2fc5c679a17679834a3ae6292",
        "9876b8f09533bc813c7f3d9dd597d5d80d4efe03911075b5ce636163417e5313",73u32)];
    let forward=drive::Input{throttle:1,steer:0,brake:false,speed_percent:100};
    for (name,vehicle,pool_sha,config_sha,sequence) in cases {
        let local=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();let base=local.join(BASE);
        let path=base.join(format!("night-fence-runtime-fixtures03/{name}-pool.json"));
        assert_eq!(format!("{:x}",Sha256::digest(fs::read(&path).unwrap())),pool_sha);
        let pool=Arc::new(drive::Pool::load(&local,&path).unwrap());assert_eq!(pool.vehicle_kind(),vehicle);
        let map=selected_pool_map(&pool,MapId::Prohorovka).unwrap().clone();assert_eq!(map.config_sha256,config_sha);
        let spec=CatalogSpec::load(&local,&base.join("night-fence-export01/catalog/physics-removals.json"),WORKER_SHA).unwrap();
        let catalog=Arc::new(fragiles::Catalog::load(&local,&base.join("night-fence-export01/catalog/manifest.json"),DOMAIN_SHA).unwrap());
        validate_catalog_projection(&catalog,&spec,MapId::Prohorovka).unwrap();
        let initial=catalog.objects.iter().filter(|o|o.object_id!=3167).map(|o|o.object_id).collect::<Vec<_>>();assert_eq!(initial.len(),1037);
        let object=catalog.objects.iter().find(|o|o.object_id==3167).unwrap();let chunk=object.chunk_id;let index=object.native_index;
        assert_eq!(catalog.ram_response(object),Some("total_linear"));
        let scene=Scene::new(&spec,&initial).unwrap();let deadline=Instant::now()+Duration::from_secs(60);
        let mut reference=drive::Worker::launch_with_catalog(pool.clone(),map.clone(),1,Instant::now(),None,spec.clone(),scene.clone()).unwrap();
        assert_eq!(actual_next(&mut reference,deadline).seq,0);let ref_pid=reference.process_id().unwrap();let mut receipts=Vec::new();
        for seq in 1..=sequence {assert_eq!(reference.advance(forward,Instant::now()).unwrap(),seq);let frame=actual_next(&mut reference,deadline);
            assert_eq!(frame.seq,seq);if seq<sequence{assert!(frame.fractures.is_empty());}else{receipts=frame.fractures;}}
        assert_eq!(receipts.len(),1);let receipt=&receipts[0];actual_radial(receipt,map.mass_kg);
        assert!(reference.sync_removed(scene.clone(),Instant::now()).is_err());assert!(reference.advance(forward,Instant::now()).is_err());
        drop(reference);actual_exit(ref_pid);
        let begin=Instant::now();let mut world=World::new_for_vehicle(920,begin,MapId::Prohorovka,vehicle).unwrap();
        world.impact.bind_fragiles(catalog.clone()).unwrap();world.fragiles=Some(fragiles::State::new(catalog));
        for slot in 0..2{world.attach(model::Identity{account:format!("fence-real-{slot}"),database:slot+1,name:format!("fence_{slot}")},slot as u32+1).unwrap();}
        world.start(begin).unwrap();world.rebase_external_spawns([map.spawn;2]).unwrap();
        for slot in 0..2{world.set_ready(slot,slot as u32+1).unwrap();world.actors[slot].input=model::Input{throttle:1,steer:0,speed_percent:100};}
        // Private isolation only. Seed both domain and its replay trace through
        // the bounded atomic API. These1037 synthetic prior removals are
        // explicitly excluded from real collision/native acceptance evidence.
        for ids in initial.chunks(32){let contacts=ids.iter().map(|id|model::VehicleContactInput{object_id:*id,shooter:0,substep:1,
            point:[0.;3],normal:[0.,0.,1.],velocity:[0.,0.,25.],mass_kg:68190.,kind:"hull".into(),proof:None}).collect::<Vec<_>>();
            assert_eq!(world.apply_vehicle_contacts(&contacts).unwrap().len(),ids.len());}
        assert_eq!(world.fragiles.as_ref().unwrap().removed_ids(),initial);world.fragiles.as_mut().unwrap().vehicle_events.clear();
        let mut runtime=IntegratedRuntime::new_for_map(pool.clone(),MapId::Prohorovka);runtime.catalog=Some(spec.clone());runtime.started=true;
        for slot in 0..2{runtime.workers[slot]=Some(drive::Worker::launch_with_catalog(pool.clone(),map.clone(),slot as u32+2,Instant::now(),None,spec.clone(),scene.clone()).unwrap());runtime.worker_sessions[slot]=world.actors[slot].session;}
        loop {assert!(Instant::now()<deadline);assert!(runtime.contact_sequences.iter().all(|s|*s<=sequence));let before=world.clone();runtime.step(&mut world,Instant::now()).unwrap();
            if let Some(candidate)=runtime.staged.clone(){
                assert_eq!(world.fragiles,before.fragiles);assert_eq!(world.actors,before.actors);assert_eq!(world.scene_version(),1037);assert!(!runtime.ready_for_native());
                assert_eq!(runtime.contact_sequences,[sequence;2]);let state=candidate.fragiles.as_ref().unwrap();assert_eq!(state.vehicle_events.len(),1);
                let event=&state.vehicle_events[0];assert_eq!((event.object_id,event.substep),(receipt.object_id,receipt.substep));
                assert_eq!((event.point,event.normal,event.velocity),(receipt.point,receipt.normal,receipt.velocity));assert_eq!(event.mass_kg,map.mass_kg);
                assert!(state.native_destroyed(chunk).contains(&index));assert!(!world.fragiles.as_ref().unwrap().native_destroyed(chunk).contains(&index));
                let mut all=initial.clone();all.push(3167);all.sort_unstable();let committed=Scene::new(&spec,&all).unwrap();
                for worker in &mut runtime.workers{assert_eq!(worker.as_ref().unwrap().prepared_ids(),&[3167]);assert!(worker.as_mut().unwrap().advance(forward,Instant::now()).is_err());}
                while runtime.workers[0].as_ref().unwrap().catalog_scene()!=Some(&committed){assert!(Instant::now()<deadline);assert!(runtime.workers[0].as_mut().unwrap().poll(Instant::now()).unwrap().is_none());std::thread::sleep(Duration::from_millis(2));}
                assert_eq!(world.fragiles,before.fragiles);assert_eq!(world.actors,before.actors);assert!(!runtime.ready_for_native());
                assert_ne!(runtime.workers[1].as_ref().unwrap().catalog_scene(),Some(&committed));
                while runtime.staged.is_some(){assert!(Instant::now()<deadline);runtime.finish_catalog(&mut world,Instant::now()).unwrap();std::thread::sleep(Duration::from_millis(2));}
                assert_eq!(world.fragiles,candidate.fragiles);assert_eq!(world.scene_version(),1038);
                assert!(runtime.workers.iter().all(|w|w.as_ref().unwrap().catalog_scene()==Some(&committed)&&w.as_ref().unwrap().prepared_ids().is_empty()));
                let pids=runtime.workers.iter().map(|w|w.as_ref().unwrap().process_id().unwrap()).collect::<Vec<_>>();drop(runtime);for pid in &pids{actual_exit(*pid);}
                // A fresh real worker restores committed topology before any
                // drive command. Ready/native grants are tested separately.
                let mut rejoin=drive::Worker::launch_with_catalog(pool.clone(),map.clone(),9,Instant::now(),None,spec.clone(),committed.clone()).unwrap();
                let ready=actual_next(&mut rejoin,deadline);assert_eq!(ready.seq,0);assert_eq!(rejoin.catalog_scene(),Some(&committed));
                let rejoin_pid=rejoin.process_id().unwrap();for seq in 1..=sequence {rejoin.advance(forward,Instant::now()).unwrap();let frame=actual_next(&mut rejoin,deadline);assert_eq!(frame.seq,seq);assert!(frame.fractures.is_empty());assert!(frame.object_contacts.iter().all(|c|c.object_id!=3167));}
                drop(rejoin);actual_exit(rejoin_pid);
                let proof=json!({"status":"PASS_REAL_RADIAL_DOMAIN_BOTH_ACK_REJOIN","case":name,"pool_sha256":pool_sha,"config_sha256":config_sha,
                    "domain_sha256":DOMAIN_SHA,"catalog_sha256":WORKER_SHA,"advance_seq":sequence,"reference_pid":ref_pid,"paired_pids":pids,"rejoin_pid":rejoin_pid,
                    "initial_removed_ids":initial,"initial_removals":"SYNTHETIC_PRIVATE_ISOLATION_NOT_COLLISION_EVIDENCE","target":3167,"mass_kg":map.mass_kg,
                    "full_source_profile":true,"normal_energy_j":0.5*f64::from(map.mass_kg)*dot64(receipt.velocity,receipt.normal).powi(2),
                    "receipt":{"substep":receipt.substep,"point":receipt.point,"normal":receipt.normal,"velocity":receipt.velocity,"budget_before":receipt.budget_before,"budget_after":receipt.budget_after,"solver_before":receipt.solver_before,"solver_after":receipt.solver_after},
                    "both_ack":true,"rejoin_restored":true,"native":"NOT_RUN","full_passage":"PRIVATE_PAIRED_REPLAY_SEPARATE"});
                let dir=base.join("night-fence-gateway-real");fs::create_dir_all(&dir).unwrap();let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
                let mut file=fs::OpenOptions::new().write(true).create_new(true).open(dir.join(format!("{name}-{}-{stamp}.json",std::process::id()))).unwrap();std::io::Write::write_all(&mut file,&serde_json::to_vec_pretty(&proof).unwrap()).unwrap();break;
            }std::thread::sleep(Duration::from_millis(2));
        }
    }
}
