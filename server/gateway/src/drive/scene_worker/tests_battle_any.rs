//! BATTLE-ANY live smoke: a stand switched by `tools/full_test_stand.py battle-any`
//! -> its own pools/qualified profiles -> the stand's IPC7 physics build -> original
//! scalar FrameProof for every actor. Physics evidence only; no owned/native gate.
//! Run explicitly: `--ignored battle_any_` with BATTLE_ANY_STAND=<stand dir> and
//! WOT091_ROOT=<checkout whose local/ holds the stand> (default D:/WoT_9.1_Server).
use super::*;
use crate::map_drive_worker091::{self as legacy, CatalogSpec, ObjectContact};
use std::{fs::OpenOptions, time::{SystemTime, UNIX_EPOCH}};

const CATALOG_SHA:&str="41c0d9ccfd5b608a07e80a4eb68a3b6ed70bacffdd1444bb58c3f2ebb179bea9";

fn vec3(v:&Value)->[f32;3] {std::array::from_fn(|i|v[i].as_f64().unwrap()as f32)}
fn contacts(state:&Value)->Vec<ObjectContact> {
    state["object_contacts"].as_array().unwrap().iter().map(|c|ObjectContact{
        object_id:c["object_id"].as_u64().unwrap().try_into().unwrap(),
        substep:c["substep"].as_u64().unwrap().try_into().unwrap(),kind:c["kind"].as_str().unwrap().into(),
        point:vec3(&c["point"]),normal:vec3(&c["normal"]),velocity:vec3(&c["velocity"])}).collect()
}
fn wait_frame(worker:&mut Worker)->Frame {
    let deadline=Instant::now()+Duration::from_secs(120);
    loop {if let Some(frame)=worker.poll(Instant::now()).unwrap_or_else(|error|{
            let stderr=worker.stderr.lock().map(|s|String::from_utf8_lossy(&s).into_owned()).unwrap_or_default();
            panic!("BATTLE-ANY worker{} poll failed: {error}; producer stderr={stderr}",worker.process_id());
        }){return frame;}
        assert!(Instant::now()<deadline,"BATTLE-ANY IPC7 frame deadline");thread::sleep(Duration::from_millis(1));}
}

#[test]#[ignore]
fn battle_any_stand_pilots_and_t26_drive_one_ipc7_scene_with_original_scalar_proof() {
    let root=PathBuf::from(std::env::var_os("WOT091_ROOT").unwrap_or_else(||"D:/WoT_9.1_Server".into())).join("local");
    let stand=PathBuf::from(std::env::var("BATTLE_ANY_STAND").expect("BATTLE_ANY_STAND"));
    let templates:Value=serde_json::from_slice(&fs::read(stand.join("battle-profiles.json")).unwrap()).unwrap();
    assert_eq!(templates["version"],5);
    let artifacts=Artifacts::load(Path::new(templates["shared_physics"]["path"].as_str().unwrap())).unwrap();
    assert_eq!(digest(&fs::read(templates["shared_physics"]["path"].as_str().unwrap()).unwrap()),
        templates["shared_physics"]["sha256"].as_str().unwrap());
    let catalog=CatalogSpec::load(&root,&root.join("evidence/20261013-p05b-tracked-handling-01/night-angular-export01/catalog/physics-removals.json"),CATALOG_SHA).unwrap();
    let listed=std::env::var("BATTLE_ANY_KINDS").unwrap_or_else(|_|"t26,ussr-KV-3,usa-M4_Sherman,germany-Waffentrager_E100,japan-Chi_Ri".into());
    let wanted=listed.split(',').collect::<Vec<_>>();let n=wanted.len();
    let mut rows=Vec::new();
    for (slot,label) in wanted.iter().enumerate() {
        let profile=templates["profiles"].as_array().unwrap().iter().find(|p|p["kind"]==*label).unwrap();
        let pool:Value=serde_json::from_slice(&fs::read(profile["pool"]["path"].as_str().unwrap()).unwrap()).unwrap();
        let map=pool["maps"].as_array().unwrap().iter().find(|m|m["asset"]=="05_prohorovka").unwrap();
        rows.push(json!({"slot":slot,"kind":label,"config":{"path":map["config"],"sha256":map["config_sha256"]},
            "source_profile":pool["vehicle_profile"],
            "spawn_origin":[-209.+8.*(slot%2)as f32,6.046776865530075,458.-12.*(slot/2)as f32],"spawn_yaw":0}));
    }
    let manifest=json!({"version":2,"profile":"test_lab","policy":POLICY,"map":"05_prohorovka",
        "catalog":{"path":worker_argument(catalog.path()).unwrap(),"sha256":CATALOG_SHA},"actors":rows});
    let stamp=SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let directory=root.join(format!("test-runs/battle-any-scene-{}-{stamp}",std::process::id()));
    fs::create_dir_all(&directory).unwrap();
    let path=directory.join("scene.json");let raw=serde_json::to_vec(&manifest).unwrap();
    let mut out=OpenOptions::new().write(true).create_new(true).open(&path).unwrap();out.write_all(&raw).unwrap();out.sync_all().unwrap();drop(out);
    let spec=Arc::new(SceneSpec::load(&root,&path,&digest(&raw)).unwrap());
    let kinds=spec.actors.iter().map(|a|a.kind).collect::<Vec<_>>();
    assert!(kinds.iter().all(|k|matches!(k,Kind::T26|Kind::Generated(_))));
    let mut worker=Worker::launch(artifacts,spec.clone(),17,Scene::new(&spec,&[]).unwrap(),Instant::now()).unwrap();
    let ready=wait_frame(&mut worker);assert_eq!(ready.sequence,0);assert_eq!(ready.actors.len(),n);
    let start=ready.actors.iter().map(|a|a.pose.position).collect::<Vec<_>>();
    let mut last=ready;let mut removed=0;
    for seq in 1..=120 {
        let inputs=vec![Input{throttle:1,steer:0,brake:false,speed_percent:100};n];
        // Destructible objects the actors break are committed before the next tick (scene ACK).
        if !worker.prepared_ids().is_empty() {
            let mut ids=worker.scene().ids.clone();ids.extend_from_slice(worker.prepared_ids());ids.sort();ids.dedup();
            worker.sync_removed(Scene::new(&spec,&ids).unwrap(),Instant::now()).unwrap();removed=ids.len();
            let deadline=Instant::now()+Duration::from_secs(3);
            loop {assert!(worker.poll(Instant::now()).unwrap().is_none());if worker.take_scene_ack(){break;}
                assert!(Instant::now()<deadline,"scene ACK deadline");thread::sleep(Duration::from_millis(1));}
        }
        assert_eq!(worker.advance(&inputs,Instant::now()).unwrap(),seq);
        let frame=wait_frame(&mut worker);assert_eq!(frame.sequence,seq);assert_eq!(frame.actors.len(),n);
        for actor in &frame.actors {
            assert!(actor.pose.position.iter().chain(&actor.pose.direction).all(|v|v.is_finite()));
            let proof=legacy::shared_angular_proof(&actor.proof,&contacts(&actor.proof),&catalog,actor.kind.physical_profile(),seq).unwrap();
            proof.final_motion(actor.pose.linear_velocity,actor.pose.angular_velocity,actor.pose.rspeed).unwrap();
        }
        last=frame;
    }
    let mut report=Vec::new();
    for (i,actor) in last.actors.iter().enumerate() {
        let d=((actor.pose.position[0]-start[i][0]).powi(2)+(actor.pose.position[2]-start[i][2]).powi(2)).sqrt();
        report.push(format!("{}={:.2}m/{:.2}mps",actor.kind.label(),d,actor.pose.speed));
        assert!(d>1.,"{} did not move under full throttle: {d}",actor.kind.label());
    }
    println!("BATTLE_ANY_SCENE_SMOKE frames=120 actors={n} removed_objects={removed} {} dir={}",report.join(" "),directory.display());
    worker.shutdown().unwrap();
}
