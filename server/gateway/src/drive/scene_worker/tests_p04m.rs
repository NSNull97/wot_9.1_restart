//! Actual frozen Jolt producer -> IPC7 batch -> original scalar FrameProof.
//! These tests qualify physics evidence; no owned/native World gate is inferred.
use super::*;
use crate::gateway091::shared::ram_proof;
use crate::map_drive_worker091::{self as legacy, CatalogSpec, ObjectContact};
use std::{fs::OpenOptions, time::{SystemTime, UNIX_EPOCH}};

const COMPONENT_ARTIFACTS:&str="C:/Users/NSNull/.codex/worktrees/p05c-night-shared-physics/WoT_9.1_Server/local/build/server/physics-p04m06/artifacts.json";
const COMPONENT_DLL_SHA:&str="22ffadca8cbf8b4a6fa7f66644e1a65c65855377745b65d53e10e4c8eed6f1ff";
const CATALOG_SHA:&str="41c0d9ccfd5b608a07e80a4eb68a3b6ed70bacffdd1444bb58c3f2ebb179bea9";
const ALL:[Kind;6]=[Kind::Ms1,Kind::Is7,Kind::T26,Kind::T34,Kind::T3485,Kind::T26];

struct Fixture {root:PathBuf,directory:PathBuf,catalog:CatalogSpec,artifacts:Artifacts}
impl Fixture {
    fn new(label:&str)->Self {
        let root=PathBuf::from(std::env::var_os("WOT091_ROOT").unwrap_or_else(||"D:/WoT_9.1_Server".into())).join("local");
        let parent=root.join("evidence/20261016-p04m-physics01");
        let stamp=SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
        let directory=parent.join(format!("rust-scene-{label}-{}-{stamp}",std::process::id()));
        fs::create_dir_all(&directory).unwrap();plain(&directory).unwrap();
        let catalog_path=root.join("evidence/20261013-p05b-tracked-handling-01/night-angular-export01/catalog/physics-removals.json");
        let catalog=CatalogSpec::load(&root,&catalog_path,CATALOG_SHA).unwrap();
        let artifacts=Artifacts::load(Path::new(COMPONENT_ARTIFACTS)).unwrap();
        assert_eq!(digest(&fs::read(artifacts.executable.with_extension("dll")).unwrap()),COMPONENT_DLL_SHA,
            "this gate deliberately targets the already qualified frozen component06 producer");
        Self{root,directory,catalog,artifacts}
    }
    fn authored(&self,name:&str,value:&Value)->PathBuf {
        let path=self.directory.join(name);let raw=serde_json::to_vec(value).unwrap();
        assert!(raw.len()<=MAX_INPUT);let mut out=OpenOptions::new().write(true).create_new(true).open(&path).unwrap();
        out.write_all(&raw).unwrap();out.write_all(b"\n").unwrap();out.sync_all().unwrap();path
    }
    fn manifest(&self,kinds:&[Kind])->Value {
        let prefix=self.root.join("evidence/20261016-p04m-physics01");
        let rows=kinds.iter().enumerate().map(|(slot,&kind)|{
            let config=if kind.vehicle().expect("old five-kind fixture").index()<2 {
                self.root.join(format!("evidence/20261014-p05b-handling-fixes-01/pools-{}-c17/05_prohorovka-{}-handling-config.json",kind.label(),kind.label()))
            }else{prefix.join(format!("source-export06/05_prohorovka-{}-config.json",kind.label()))};
            let (config,_)=crate::portable_test_fixtures::verified(&config,None);
            let source=if kind.vehicle().expect("old five-kind fixture").index()<2 {Value::Null}else{
                let path=prefix.join(format!("getters06/{}-qualified-profile.json",kind.label()));
                assert_eq!(digest(&fs::read(&path).unwrap()),kind.profile_sha());
                json!({"path":path,"sha256":kind.profile_sha()})};
            json!({"slot":slot,"kind":kind.label(),"config":{"path":config,"sha256":digest(&fs::read(&config).unwrap())},
                "source_profile":source,"spawn_origin":[-209.+8.*(slot%2)as f32,6.046776865530075,458.-12.*(slot/2)as f32],"spawn_yaw":0})
        }).collect::<Vec<_>>();
        json!({"version":2,"profile":"test_lab","policy":POLICY,"map":"05_prohorovka",
            "catalog":{"path":worker_argument(self.catalog.path()).unwrap(),"sha256":CATALOG_SHA},"actors":rows})
    }
    fn load(&self,name:&str,value:&Value)->io::Result<Arc<SceneSpec>> {
        let path=self.authored(name,value);let sha=digest(&fs::read(&path)?);
        SceneSpec::load(&self.root,&path,&sha).map(Arc::new)
    }
    fn launch(&self,spec:Arc<SceneSpec>)->Worker {
        let scene=Scene::new(&spec,&[]).unwrap();
        Worker::launch(self.artifacts.clone(),spec,17,scene,Instant::now()).unwrap()
    }
}

fn wait_frame(worker:&mut Worker)->Frame {
    let deadline=Instant::now()+Duration::from_secs(120);
    loop {if let Some(frame)=worker.poll(Instant::now()).unwrap_or_else(|error|{
            let stderr=worker.stderr.lock().map(|s|String::from_utf8_lossy(&s).into_owned()).unwrap_or_default();
            panic!("actual P04M worker{} poll failed: {error}; producer stderr={stderr}",worker.process_id());
        }){return frame;}
        assert!(Instant::now()<deadline,"actual P04M IPC7 frame deadline");thread::sleep(Duration::from_millis(1));}
}
fn wait_ack(worker:&mut Worker) {
    let deadline=Instant::now()+Duration::from_secs(3);
    loop {assert!(worker.poll(Instant::now()).unwrap().is_none(),"ACK cannot publish another physics tick");
        if worker.take_scene_ack(){return;}
        assert!(Instant::now()<deadline,"actual P04M scene ACK deadline");thread::sleep(Duration::from_millis(1));}
}
fn vec3(v:&Value)->[f32;3] {std::array::from_fn(|i|v[i].as_f64().unwrap()as f32)}
fn contacts(state:&Value)->Vec<ObjectContact> {
    state["object_contacts"].as_array().unwrap().iter().map(|c|ObjectContact{
        object_id:c["object_id"].as_u64().unwrap().try_into().unwrap(),
        substep:c["substep"].as_u64().unwrap().try_into().unwrap(),kind:c["kind"].as_str().unwrap().into(),
        point:vec3(&c["point"]),normal:vec3(&c["normal"]),velocity:vec3(&c["velocity"])}).collect()
}
fn scalar(actor:&ActorFrame,catalog:&CatalogSpec,seq:u32)->Arc<ram_proof::FrameProof> {
    let raw=contacts(&actor.proof);let profile=actor.kind.physical_profile();
    let proof=legacy::shared_angular_proof(&actor.proof,&raw,catalog,profile,seq).unwrap();
    proof.final_motion(actor.pose.linear_velocity,actor.pose.angular_velocity,actor.pose.rspeed).unwrap();proof
}
fn log_frame(out:&mut fs::File,frame:&Frame) {
    let raw=serde_json::to_vec(&frame.raw).unwrap();assert!(raw.len()<=MAX_OUTPUT);
    out.write_all(&raw).unwrap();out.write_all(b"\n").unwrap();
}

#[test]
fn p04m_actual_three_new_and_all_five_six_actor_batches_pass_original_scalar_frameproof_and_scene_ack() {
    let fixture=Fixture::new("scalar-actual");let mut summary=Vec::new();
    for kinds in [vec![Kind::T26],vec![Kind::T34],vec![Kind::T3485],ALL.to_vec()] {
        let name=kinds.iter().map(|k|k.label()).collect::<Vec<_>>().join("-");
        let manifest=fixture.manifest(&kinds);let spec=fixture.load(&format!("{name}-scene.json"),&manifest).unwrap();
        let mut log=OpenOptions::new().write(true).create_new(true).open(fixture.directory.join(format!("{name}-actual-frames.jsonl"))).unwrap();
        let mut worker=fixture.launch(spec.clone());let pid=worker.process_id();let ready=wait_frame(&mut worker);
        assert_eq!(ready.sequence,0);assert_eq!(ready.actors.len(),kinds.len());
        for actor in &ready.actors {assert!(scalar(actor,&fixture.catalog,0).receipts.is_empty());}
        log_frame(&mut log,&ready);
        let mut actor_frames=ready.actors.len();let mut receipts=0;let mut witnesses=0;let mut acks=0;
        let mut seen=BTreeSet::new();let mut rejected=0;
        for seq in 1..=150 {
            let inputs=vec![Input{throttle:1,steer:0,brake:false,speed_percent:100};kinds.len()];
            assert_eq!(worker.advance(&inputs,Instant::now()).unwrap(),seq);
            let frame=wait_frame(&mut worker);assert_eq!(worker.process_id(),pid);
            assert_eq!(frame.sequence,seq);assert_eq!(frame.tick,180+seq*6);assert_eq!(frame.actors.len(),kinds.len());
            log_frame(&mut log,&frame);
            for actor in &frame.actors {
                let proof=scalar(actor,&fixture.catalog,seq);actor_frames+=1;
                receipts+=proof.receipts.len();witnesses+=proof.witnesses.len();
                if !proof.receipts.is_empty(){seen.insert(actor.kind.label());}
                // The real published state, not a hand-built positive fixture,
                // must fail original scalar validation after a native bit flip.
                if seq==1 {
                    let mut poison=actor.proof.clone();let old=poison["body_binding"]["inverse_mass"].as_f64().unwrap()as f32;
                    poison["body_binding"]["inverse_mass"]=json!(f32::from_bits(old.to_bits()^1));
                    assert!(legacy::shared_angular_proof(&poison,&contacts(&poison),&fixture.catalog,proof.profile,seq).is_err());rejected+=1;
                }
                if !proof.receipts.is_empty() {
                    let mut poison=actor.proof.clone();let tensor=&mut poison["motion_witnesses"][0]["post_solver"]["inverse_inertia_row_major"];
                    tensor[0]=json!(tensor[0].as_f64().unwrap()+0.00001);
                    assert!(legacy::shared_angular_proof(&poison,&contacts(&poison),&fixture.catalog,proof.profile,seq).is_err(),
                        "native tensor corruption must fail the original scalar basis proof");rejected+=1;
                }
            }
            // Complete IPC7 validation is atomic even when only the last row
            // carries a false source/binding/config identity.
            if seq==1 {
                let last=kinds.len()-1;
                for mutation in 0..3 {
                    let mut poison=frame.raw.clone();match mutation {
                        0=>poison["actors"][last]["profile_sha256"]="f".repeat(64).into(),
                        1=>poison["actors"][last]["config_sha256"]="f".repeat(64).into(),
                        _=>{let old=poison["actors"][last]["state"]["body_binding"]["inertia_rotation_xyzw"][0].as_f64().unwrap()as f32;
                            poison["actors"][last]["state"]["body_binding"]["inertia_rotation_xyzw"][0]=json!(f32::from_bits(old.to_bits()^1));}
                    }
                    assert!(response(&serde_json::to_vec(&poison).unwrap(),&spec,17,worker.scene(),seq).is_err());rejected+=1;
                }
                assert!(response(&serde_json::to_vec(&frame.raw).unwrap(),&spec,17,worker.scene(),seq).is_ok());
            }
            if frame.prepared {
                assert!(!frame.prepared_ids.is_empty());
                assert!(worker.advance(&inputs,Instant::now()).is_err(),"unvalidated prepare cannot advance");
                assert!(worker.sync_removed(worker.scene().clone(),Instant::now()).is_err(),"claim omission must not be ACKed");
                let mut ids=worker.scene().ids.clone();ids.extend(frame.prepared_ids.iter().copied());ids.sort_unstable();ids.dedup();
                let next=Scene::new(&spec,&ids).unwrap();
                // ACK only follows successful original scalar validation of ALL actors.
                for _ in 0..2 {worker.sync_removed(next.clone(),Instant::now()).unwrap();wait_ack(&mut worker);assert_eq!(worker.scene(),&next);}
                acks+=1;
            }
        }
        assert!(receipts>0&&witnesses>0&&acks>0,"source route must exercise real static object physics, not empty receipts");
        if kinds.len()==1 {assert!(seen.contains(kinds[0].label()));}
        assert!(!worker.scene().ids.is_empty());log.sync_all().unwrap();
        summary.push(json!({"kinds":kinds.iter().map(|k|k.label()).collect::<Vec<_>>(),"status":"PASS","single_worker_pid":pid,
            "batches":150,"all_scalar_actor_frames":actor_frames,"native_receipts":receipts,"native_witnesses":witnesses,
            "prepared_acks":acks,"scalar_and_batch_corruption_rejections":rejected,"committed_removed_ids":worker.scene().ids,
            "receipt_kinds":seen,"world_domain":"NOT_RUN","native_owner":"NOT_RUN"}));
        worker.shutdown().unwrap();
        println!("P04M_ACTUAL_SCALAR_ACCEPTED kinds={name} actor_frames={actor_frames} receipts={receipts} witnesses={witnesses} acks={acks} pid={pid}");
    }
    fixture.authored("result.json",&json!({"status":"PASS_ACTUAL_WORKER_ORIGINAL_SCALAR_FRAMEPROOF_ACK","tests":summary,
        "artifacts":COMPONENT_ARTIFACTS,"worker_dll_sha256":COMPONENT_DLL_SHA,"battle_admission":false,"world_domain":"NOT_RUN","native_owner":"NOT_RUN"}));
    println!("P04M_SCALAR_EVIDENCE {}",fixture.directory.display());
}

#[test]
fn p04m_forged_profile_and_last_actor_config_pins_fail_before_worker_launch() {
    let fixture=Fixture::new("source-rejection");let original=fixture.manifest(&ALL);
    let good=fixture.load("good-scene.json",&original).unwrap();assert_eq!(good.actors.len(),6);
    for mutation in 0..6 {
        let mut wrong=original.clone();match mutation {
            0=>wrong["actors"][5]["source_profile"]["sha256"]="f".repeat(64).into(),
            1=>wrong["actors"][5]["kind"]="t34".into(),
            2=>{
                let source=PathBuf::from(original["actors"][5]["config"]["path"].as_str().unwrap());
                let mut config:Value=serde_json::from_slice(&fs::read(source).unwrap()).unwrap();
                config["mass_kg"]=json!(config["mass_kg"].as_f64().unwrap()+1.);
                let path=fixture.authored("bad-last-mass-config.json",&config);
                wrong["actors"][5]["config"]=json!({"path":path,"sha256":digest(&fs::read(&path).unwrap())});
            }
            3=>{wrong["actors"][0].as_object_mut().unwrap().remove("source_profile");}
            4=>wrong["actors"][0]["source_profile"]=wrong["actors"][5]["source_profile"].clone(),
            _=>{
                let source=PathBuf::from(original["actors"][5]["source_profile"]["path"].as_str().unwrap());
                let mut profile:Value=serde_json::from_slice(&fs::read(source).unwrap()).unwrap();
                profile["definition"]["source"]["assembly"]["gun"]="_45mm_20K".into();
                let path=fixture.authored("bad-source-mounted-gun-profile.json",&profile);
                wrong["actors"][5]["source_profile"]=json!({"path":path,"sha256":digest(&fs::read(&path).unwrap())});
            }
        }
        assert!(fixture.load(&format!("rejected-{mutation}-scene.json"),&wrong).is_err(),"source mutation{mutation}");
    }
    // Rejection never changed the original source files or successfully loaded spec.
    good.verify().unwrap();
    fixture.authored("result.json",&json!({"status":"PASS_REJECTED_BEFORE_LAUNCH","mutations":6,
        "profile_kinds":ALL.map(Kind::label),"launched_processes":0,"battle_admission":false}));
    println!("P04M_SOURCE_REJECTION_EVIDENCE {}",fixture.directory.display());
}
