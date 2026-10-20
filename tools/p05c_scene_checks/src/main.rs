//! Standalone component harness: no gateway/local vendor checkout dependency.
#[path = "../../../server/gateway/src/drive/scene_worker.rs"]
mod scene_worker;
#[path = "../../../server/gateway/src/shared/scene_runtime.rs"]
mod scene_runtime;
fn main() {
    if let Err(error) = run() { eprintln!("P05C_CHECK_FAILED {error}"); std::process::exit(1); }
}
fn run() -> std::io::Result<()> {
    use std::{path::Path, sync::Arc, time::{Duration, Instant}};
    let args = std::env::args().collect::<Vec<_>>();
    if !(args.len()==5||args.len()==6&&args[5]=="--physical-acks") { return Err(std::io::Error::new(std::io::ErrorKind::InvalidInput,
        "p05c-scene-checks ASSET_ROOT SCENE_MANIFEST SCENE_SHA ARTIFACT_MANIFEST [--physical-acks]")); }
    let physical_acks=args.len()==6;
    let spec=Arc::new(scene_worker::SceneSpec::load(Path::new(&args[1]),Path::new(&args[2]),&args[3])?);
    let artifacts=scene_worker::Artifacts::load(Path::new(&args[4]))?;
    let scene=scene_worker::Scene::new(&spec,&[])?;
    let mut runtime=scene_runtime::Runtime::launch(artifacts,spec.clone(),1,scene,Instant::now())?;
    let deadline=Instant::now()+Duration::from_secs(60);
    let wait=|runtime:&mut scene_runtime::Runtime|->std::io::Result<scene_worker::Frame>{loop {
        if Instant::now()>deadline {return Err(std::io::Error::new(std::io::ErrorKind::TimedOut,"component deadline"));}
        if let Some(frame)=runtime.poll(Instant::now())? {return Ok(frame);}
        std::thread::sleep(Duration::from_millis(1));
    }};
    let ready=wait(&mut runtime)?;
    assert_eq!(ready.sequence,0);assert_eq!(ready.actors.len(),spec.actors.len());
    println!("P05C_READY pid={} actors={} tick={}",runtime.process_id(),ready.actors.len(),ready.tick);
    let mut ack_count=0;
    for sequence in 1..=120 {
        let inputs=spec.actors.iter().map(|a|if a.slot==0||physical_acks {scene_worker::Input{throttle:1,steer:0,brake:false,speed_percent:100}}else{scene_worker::Input::STOP}).collect::<Vec<_>>();
        runtime.advance(&inputs,Instant::now())?;
        let frame=wait(&mut runtime)?;
        assert_eq!(frame.sequence,sequence);assert_eq!(frame.tick,180+sequence*6);
        if frame.prepared {
            if !physical_acks {return Err(std::io::Error::new(std::io::ErrorKind::InvalidData,"component route unexpectedly fractured; domain proof acceptance needed"));}
            // This explicit component gate checks physical ACK machinery only.
            // It does not create a World or claim scalar/domain acceptance.
            let mut ids=runtime.scene().ids.clone();ids.extend(frame.prepared_ids);ids.sort_unstable();ids.dedup();
            let scene=scene_worker::Scene::new(&spec,&ids)?;
            for _ in 0..2 {
                runtime.sync_removed(scene.clone(),Instant::now())?;
                loop {
                    if Instant::now()>deadline{return Err(std::io::Error::new(std::io::ErrorKind::TimedOut,"scene ACK component deadline"));}
                    if runtime.poll(Instant::now())?.is_some(){return Err(std::io::Error::new(std::io::ErrorKind::InvalidData,"scene ACK unexpectedly advanced"));}
                    if runtime.take_scene_ack(){break;}
                    std::thread::sleep(Duration::from_millis(1));
                }
            }
            ack_count+=1;
        }
    }
    if physical_acks&&ack_count==0{return Err(std::io::Error::new(std::io::ErrorKind::InvalidData,"physical ACK flag did not exercise prepared frame"));}
    println!("P05C_PHYSICAL_ACKS prepared_frames={ack_count} scalar_domain_gate=NOT_RUN");
    println!("P05C_PASS batches=120 actors={} single_worker_pid={}",spec.actors.len(),runtime.process_id());
    runtime.shutdown()?;println!("P05C_SHUTDOWN EOF_exit0_reaped=true");
    Ok(())
}
