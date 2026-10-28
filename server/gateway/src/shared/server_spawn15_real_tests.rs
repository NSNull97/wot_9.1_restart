//! SPAWN-15 settle check (ignored; run explicitly). One real profile13 arena
//! from a pinned battle-profiles manifest, team-base formation enabled, N
//! SYNTHETIC owned actors (test loadouts), its own real Jolt scene process.
//! Passes only if the scene settles every actor (the worker refuses fewer than
//! three wheels in contact or > 1 m/s) and each settled pose stays at its spot,
//! facing the enemy base, for a stationary hold. Not a native client run.
use super::*;

fn env(key:&str)->Option<String>{std::env::var(key).ok().filter(|v|!v.is_empty())}

#[test]
#[ignore]
fn spawn15_team_bases_settle_in_real_jolt_scene(){
    let manifest=PathBuf::from(env("SPAWN15_MANIFEST").expect("SPAWN15_MANIFEST"));
    let root=PathBuf::from(env("SPAWN15_LOCAL_ROOT").unwrap_or_else(||"D:/WoT_9.1_Server/local".into()));
    let out=PathBuf::from(env("SPAWN15_OUT").expect("SPAWN15_OUT"));
    let size:usize=env("SPAWN15_SIZE").map_or(30,|v|v.parse().unwrap());
    let heavy=env("SPAWN15_KINDS").as_deref()==Some("is7");
    assert!((2..=model::MAX_ACTORS).contains(&size));
    let resources=super::super::profile13_templates::load(&root,&manifest).unwrap();
    let now=Instant::now();let id=0x5eed_5a05_0001;
    let mut template=BattleTemplate::from_shared_policy(&resources,size,id,now,None,false).unwrap();
    template.world.enable_team_base_spawn().unwrap();
    let mut a=arena::Arena::from_template(0,&template,id,now).unwrap();
    for slot in 0..size {
        let kind=if heavy||slot%2==1{VehicleKind::Is7}else{VehicleKind::Ms1};
        let(mut owner,loadout)=model::tests::profile13_loadout(kind,slot,kind.ammo_limit());
        owner.name=format!("spawn15-synthetic-{slot}");a.world.attach_owned(owner,slot as u32+1,&loadout).unwrap();
    }
    let teams=(0..size).map(|slot|a.world.team(slot).unwrap()).collect::<Vec<_>>();
    let spots=super::super::team_spawn::placement(a.world.map,&teams).unwrap();
    let startup=Instant::now();a.world.start(startup).unwrap();
    while !a.integrated.as_ref().is_some_and(|r|r.batch.as_ref().is_some_and(|b|b.ready_for_native())) {
        assert!(startup.elapsed()<Duration::from_secs(150),"scene startup bound");
        match a.handle(arena::Command::Step{now:Instant::now(),start:false}) {
            arena::Event::Stepped=>{},
            arena::Event::Failed{stage,error}=>panic!("SPAWN15 settle failed map={} size={size} stage={stage} error={error}",a.world.map.asset()),
        }
        thread::sleep(Duration::from_millis(5));
    }
    let startup_ms=startup.elapsed().as_secs_f64()*1000.;
    let settled=a.world.actors.iter().map(|x|(x.position,x.direction)).collect::<Vec<_>>();
    for slot in 0..size {a.world.set_ready(slot,slot as u32+1).unwrap();}
    // Stationary hold: STOP inputs for 3 s of domain steps.
    let hold=Instant::now();
    while hold.elapsed()<Duration::from_secs(3) {
        for x in &mut a.world.actors {x.input=model::Input::STOP;}
        match a.handle(arena::Command::Step{now:Instant::now(),start:false}) {
            arena::Event::Stepped=>{},
            arena::Event::Failed{stage,error}=>panic!("SPAWN15 hold failed stage={stage} error={error}"),
        }
        thread::sleep(Duration::from_millis(5));
    }
    let rows=(0..size).map(|slot|{
        let(p,d)=settled[slot];let end=a.world.actors[slot].position;let s=spots[slot];
        let xz=(p[0]-s.position[0]).hypot(p[2]-s.position[2]);let drift=(end[0]-p[0]).hypot(end[2]-p[2]);
        let mut yaw=(d[0]-s.yaw).abs();if yaw>std::f32::consts::PI{yaw=2.*std::f32::consts::PI-yaw;}
        serde_json::json!({"slot":slot,"team":teams[slot],"kind":a.world.actors[slot].vehicle_kind().label(),"spot":s.position,"spot_yaw":s.yaw,
            "settled":p,"settled_direction":d,"held":end,"xz_from_spot_m":xz,"dy_from_spot_m":p[1]-s.position[1],"yaw_error_rad":yaw,"hold_drift_m":drift,
            "ok":xz<=1.&&(-1.5..=0.5).contains(&(p[1]-s.position[1]))&&yaw<=0.2&&drift<=0.3})
    }).collect::<Vec<_>>();
    let mut separation=f32::MAX;
    for i in 0..size {for j in i+1..size {let(p,q)=(a.world.actors[i].position,a.world.actors[j].position);separation=separation.min((p[0]-q[0]).hypot(p[2]-q[2]));}}
    let ok=rows.iter().all(|r|r["ok"]==true)&&separation>=7.;
    let report=serde_json::json!({"schema":"spawn15-settle.v1","label":"SYNTHETIC actors, real Jolt scene; not native",
        "build":if cfg!(debug_assertions){"debug"}else{"release"},"manifest":manifest,"map":a.world.map.asset(),"policy":super::super::team_spawn::POLICY,
        "actors":size,"kinds":if heavy{"is7"}else{"ms1/is7 alternating"},"startup_ms":startup_ms,"min_separation_m":separation,"pass":ok,"rows":rows});
    if let Some(parent)=out.parent(){fs::create_dir_all(parent).unwrap();}
    fs::write(&out,serde_json::to_vec_pretty(&report).unwrap()).unwrap();
    println!("SPAWN15_SETTLE map={} actors={size} pass={ok} min_separation_m={separation:.2} startup_ms={startup_ms:.0}",a.world.map.asset());
    assert!(ok,"settled poses off their spots: {}",out.display());
}
