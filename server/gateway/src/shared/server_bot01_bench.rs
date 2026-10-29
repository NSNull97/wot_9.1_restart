//! BOT-01 bench (ignored; run explicitly). One profile13 arena from a pinned
//! battle-profiles manifest: one native place held by a SYNTHETIC owned actor
//! with scripted input (no client), the rest server bots, a real Jolt scene,
//! the real lifecycle countdown and the gateway's own arena step. Measures the
//! step, process CPU and RSS, and what the bots did. Not a native battle.
use super::*;
use super::arena_bench::{env,summary,sample,physics_pid};
use std::collections::BTreeMap;

/// BW-01: the same step through the arena's worker process when it has one.
pub(super) fn step(a:&mut arena::Arena,command:arena::Command)->arena::Event {
    if a.worker.is_none() {return a.handle(command);}
    super::battle_worker::step_all(std::slice::from_mut(a),&[Some(command)]).pop().flatten().expect("one event")
}
/// Child processes of `pid` (the worker's Jolt scene process).
pub(super) fn children(pid:u32)->Vec<u32> {
    let script=format!("Get-CimInstance Win32_Process -Filter 'ParentProcessId={pid}' | ForEach-Object {{ $_.ProcessId }}");
    let out=std::process::Command::new("powershell").args(["-NoProfile","-Command",&script]).output().expect("powershell children");
    String::from_utf8_lossy(&out.stdout).lines().filter_map(|l|l.trim().parse().ok()).collect()
}
fn alive(pid:u32)->bool {sample(&[pid]).contains_key(&pid)}

#[test]
#[ignore]
fn bot01_bench_real_scene(){
    let manifest=PathBuf::from(env("BOT01_BENCH_MANIFEST").expect("BOT01_BENCH_MANIFEST"));
    let root=PathBuf::from(env("BOT01_BENCH_LOCAL_ROOT").unwrap_or_else(||"D:/WoT_9.1_Server/local".into()));
    let out=PathBuf::from(env("BOT01_BENCH_OUT").expect("BOT01_BENCH_OUT"));
    let size:usize=env("BOT01_BENCH_SIZE").map_or(30,|v|v.parse().unwrap());
    let humans:usize=env("BOT01_BENCH_HUMANS").map_or(1,|v|v.parse().unwrap());
    let seconds:u64=env("BOT01_BENCH_SECONDS").map_or(180,|v|v.parse().unwrap());
    let seed:u64=env("BOT01_BENCH_SEED").map_or(1,|v|v.parse().unwrap());
    let resources=super::super::profile13_templates::load(&root,&manifest).unwrap();
    let kinds=resources.iter().map(|r|r.kind).collect::<Vec<_>>();
    let now=Instant::now();
    let id=arena::arena_ids(1,0x5eed_b071_0001).unwrap()[0];
    let mut template=BattleTemplate::from_shared_policy(&resources,size,id,now,None,false).unwrap();
    template.world.enable_original_spotting(super::super::spotting::Rules::selected().unwrap()).unwrap();
    template.world.enable_result_spots().unwrap();
    if size>wire::MAX_NATIVE_ACTORS||env("BOT01_BENCH_TEAM_BASES").as_deref()==Some("1"){template.world.enable_team_base_spawn().unwrap();}
    template.world.enable_bots(model::bots::Plan{human_places:humans,seed,kinds:kinds.clone()}).unwrap();
    let mut a=arena::Arena::from_template(0,&template,id,now).unwrap();
    // BW-01: BOT01_BENCH_WORKER=1 steps the arena in its worker process;
    // BOT01_BENCH_KILL_S kills that worker at the given measured second.
    let worker=env("BOT01_BENCH_WORKER").as_deref()==Some("1");
    let kill_at:Option<f64>=env("BOT01_BENCH_KILL_S").map(|v|v.parse().unwrap());
    assert!(kill_at.is_none()||worker,"BOT01_BENCH_KILL_S needs BOT01_BENCH_WORKER=1");
    if worker {a.worker=Some(Box::new(super::battle_worker::Remote::new(super::battle_worker::tests::settings())));}
    for slot in 0..humans {
        let kind=VehicleKind::Ms1;
        let(mut owner,loadout)=model::tests::profile13_loadout(kind,slot,kind.ammo_limit());
        owner.name=format!("bench-native-{slot}");
        assert_eq!(a.world.attach_owned(owner,slot as u32+1,&loadout).unwrap(),slot);
    }
    // The service start turn: fill, then the arena step with start=true.
    let startup=Instant::now();
    assert_eq!(a.world.fill_bots().unwrap(),size-humans);
    let mut first=true;
    while !a.native_ready() {
        assert!(startup.elapsed()<Duration::from_secs(150),"scene startup bound");
        let event=step(&mut a,arena::Command::Step{now:Instant::now(),start:first});first=false;
        assert!(matches!(event,arena::Event::Stepped),"{event:?}");
        thread::sleep(Duration::from_millis(5));
    }
    let startup_ms=startup.elapsed().as_secs_f64()*1000.;
    for slot in 0..humans {a.world.set_ready(slot,slot as u32+1).unwrap();}
    let me=std::process::id();
    let worker_pid=a.worker.as_ref().and_then(|w|w.pid());
    let pid=match worker_pid {Some(w)=>{let c=children(w);assert_eq!(c.len(),1,"one scene process under the worker: {c:?}");c[0]},None=>physics_pid(&a).unwrap()};
    let all=[Some(me),worker_pid,Some(pid)].into_iter().flatten().collect::<Vec<_>>();
    let mut killed:Option<(u32,f64)>=None;
    let stop=Arc::new(std::sync::atomic::AtomicBool::new(false));
    let sampler={let stop=stop.clone();let all=all.clone();thread::spawn(move||{
        let mut rows=Vec::new();
        while !stop.load(std::sync::atomic::Ordering::Acquire){rows.push((Instant::now(),sample(&all)));thread::sleep(Duration::from_millis(500));}
        rows.push((Instant::now(),sample(&all)));rows})};
    let measured=Instant::now();let mut step_ms=Vec::new();let mut battle_step_ms=Vec::new();let mut failure=None;
    let mut battle_from=None;let mut loops=0u64;let start_tick=a.world.tick;
    let origins=a.world.actors.iter().map(|x|[x.position[0],x.position[2]]).collect::<Vec<_>>();
    let mut max_abs=0f32;
    // VIS-PERF: per-part wall time of each battle loop (step_profile spans).
    let names=super::super::step_profile::NAMES;let mut parts:Vec<Vec<f64>>=vec![Vec::new();names.len()];let mut heavy:Vec<[f64;11]>=Vec::new();
    // Countdown plus the measured battle seconds; ends early only at an outcome.
    while measured.elapsed()<Duration::from_secs(30+seconds) {
        loops+=1;
        // Scripted native place: forward with a slow steering pattern (no client).
        for slot in 0..humans {let phase=(loops/400+slot as u64)%4;
            a.world.actors[slot].input=model::Input{throttle:1,steer:match phase{0=>0,1=>1,2=>0,_=>-1},speed_percent:100};}
        let before=super::super::step_profile::snapshot();
        if let (Some(at),None)=(kill_at,killed) {if measured.elapsed().as_secs_f64()>=30.+at {
            killed=Some((super::battle_worker::tests::kill(&a),measured.elapsed().as_secs_f64()));}}
        let t=Instant::now();let event=step(&mut a,arena::Command::Step{now:t,start:false});
        let ms=t.elapsed().as_secs_f64()*1000.;step_ms.push(ms);
        let after=super::super::step_profile::snapshot();
        let battle=a.world.lifecycle.as_ref().is_some_and(|l|l.allows_actions());
        if battle {battle_from.get_or_insert(Instant::now());battle_step_ms.push(ms);
            let delta:[f64;11]=std::array::from_fn(|i|(after[i]-before[i]) as f64/1e6);
            for (i,v) in delta.iter().enumerate(){parts[i].push(*v);}
            heavy.push([ms,delta[1],delta[2],delta[3],delta[5],delta[6],delta[7],delta[8],delta[0],delta[9],delta[10]]);}
        if let arena::Event::Failed{stage,error}=event {failure=Some(serde_json::json!({"stage":stage,"error":error.to_string(),"at_s":measured.elapsed().as_secs_f64()}));break;}
        for x in &a.world.actors {max_abs=max_abs.max(x.position[0].abs()).max(x.position[2].abs());}
        if a.world.lifecycle.as_ref().is_some_and(|l|l.outcome().is_some()) {break;}
        // Gateway-side view clone per native session, as in ARENA-01.
        for _ in 0..humans {std::hint::black_box(a.world.clone());}
        thread::sleep(Duration::from_millis(5));
    }
    let wall=measured.elapsed().as_secs_f64();
    // A killed worker must not leave its scene process behind.
    let jolt_after_kill=killed.map(|_|{thread::sleep(Duration::from_secs(5));alive(pid)});
    stop.store(true,std::sync::atomic::Ordering::Release);let rows=sampler.join().unwrap();
    let (first_row,last_row)=(rows.first().unwrap(),rows.last().unwrap());let interval=last_row.0.duration_since(first_row.0).as_secs_f64();
    let mut peak:BTreeMap<u32,u64>=BTreeMap::new();
    for (_,row) in &rows {for (p,(_,ws)) in row {let e=peak.entry(*p).or_default();*e=(*e).max(*ws);}}
    let cpu=|p:u32|last_row.1.get(&p).zip(first_row.1.get(&p)).map(|(e,b)|e.0-b.0);
    let steps=interval*10.;
    let w=&a.world;
    let battle_steps=battle_from.map_or(1.,|t|t.elapsed().as_secs_f64()*10.).max(1.);
    let step_parts=names.iter().zip(&parts).map(|(n,v)|(n.to_string(),serde_json::json!({"ms_per_domain_step":v.iter().sum::<f64>()/battle_steps,"loop":summary(v.clone())}))).collect::<serde_json::Map<_,_>>();
    // The slowest 1% of battle loops: mean of each part inside them.
    heavy.sort_by(|a,b|b[0].total_cmp(&a[0]));let top=&heavy[..heavy.len().div_ceil(100)];
    let top_mean=|i:usize|top.iter().map(|r|r[i]).sum::<f64>()/top.len().max(1) as f64;
    let slowest=serde_json::json!({"loops":top.len(),"step":top_mean(0),"scene_step":top_mean(1),"scene_world_clone":top_mean(2),"advance":top_mean(3),
        "projectiles":top_mean(4),"spotting":top_mean(5),"spotting_actors":top_mean(6),"spotting_rays":top_mean(7),"bots":top_mean(8),"lifecycle":top_mean(9),"turret_flights":top_mean(10)});
    let bots=(humans..w.actors.len()).collect::<Vec<_>>();
    let moved=bots.iter().map(|s|{let p=[w.actors[*s].position[0],w.actors[*s].position[2]];(p[0]-origins[*s][0]).hypot(p[1]-origins[*s][1])}).collect::<Vec<_>>();
    let by_bots=w.damage_events.iter().filter(|e|w.is_bot(e.attacker)).count()+w.impacts.iter().filter(|e|w.is_bot(e.attacker)).count();
    let dead=w.actors.iter().filter(|x|!x.alive()).count();
    let report=serde_json::json!({
        "schema":"bot01-bench.v1","label":"SYNTHETIC native place (scripted input) + server bots, real Jolt scene, real lifecycle; not native",
        "build":if cfg!(debug_assertions){"debug"}else{"release"},"manifest":manifest,"map":w.map.asset(),"actors":size,"native_places":humans,
        "bots":size-humans,"seed":seed,"kinds":kinds.iter().map(|k|k.label()).collect::<Vec<_>>(),"bot_policy":model::bots::POLICY,
        "spawn":if w.team_base_spawn(){super::super::team_spawn::POLICY}else{"lab-lanes"},"mixed_ammo":w.mixed_ammo(),
        "seconds":wall,"battle_seconds":battle_from.map(|t|t.elapsed().as_secs_f64()),"startup_ms":startup_ms,"loops":loops,
        "domain_steps":w.tick.saturating_sub(start_tick),"step_wall_all":summary(step_ms),"step_wall_battle":summary(battle_step_ms),
        "gateway":{"pid":me,"cpu_s":cpu(me),"cpu_ms_per_domain_step":cpu(me).map(|c|c*1000./steps),"cpu_share_of_one_core":cpu(me).map(|c|c/interval),
            "working_set_end":last_row.1.get(&me).map(|v|v.1),"working_set_peak":peak.get(&me)},
        "mode":if worker{"battle_worker"}else{"in_process"},
        "worker":worker_pid.map(|w|serde_json::json!({"pid":w,"cpu_s":cpu(w),"cpu_ms_per_domain_step":cpu(w).map(|c|c*1000./steps),
            "cpu_share_of_one_core":cpu(w).map(|c|c/interval),"working_set_end":last_row.1.get(&w).map(|v|v.1),"working_set_peak":peak.get(&w),
            "steps":a.worker.as_ref().map(|r|r.steps),"last_frame_bytes":a.worker.as_ref().map(|r|r.frame_bytes),
            "killed_at_s":killed.map(|k|k.1),"scene_process_alive_5s_after_kill":jolt_after_kill})),
        "physics":{"pid":pid,"cpu_s":cpu(pid),"cpu_ms_per_domain_step":cpu(pid).map(|c|c*1000./steps),"cpu_share_of_one_core":cpu(pid).map(|c|c/interval),
            "working_set_end":last_row.1.get(&pid).map(|v|v.1),"working_set_peak":peak.get(&pid)},
        "step_parts":step_parts,"slowest_1pct_loops_mean_ms":slowest,
        "bot_think_ms_per_domain_step":w.bot_think_ns() as f64/1e6/w.tick.saturating_sub(start_tick).max(1) as f64,
        "behaviour":{"bot_shots":w.bot_shots(),"bot_stucks":w.bot_stucks(),"shots_total":w.shots.len(),"damage_rows_by_bots":by_bots,"vehicles_dead":dead,
            "bots_moved_over_50m":moved.iter().filter(|m|**m>50.).count(),"bot_moved_m_max":moved.iter().copied().fold(0f32,f32::max),
            "max_abs_xz":max_abs,"digest":w.bot_digest().map(|d|format!("{d:016x}")),
            "outcome":w.lifecycle.as_ref().and_then(|l|l.outcome()).map(|o|format!("{o:?}"))},
        "failure":failure,
    });
    if let Some(parent)=out.parent(){fs::create_dir_all(parent).unwrap();}
    fs::write(&out,serde_json::to_vec_pretty(&report).unwrap()).unwrap();
    println!("BOT01_BENCH {}",serde_json::to_string(&report).unwrap());
    if killed.is_some() {
        assert_eq!(report["failure"]["stage"],"battle_worker_lost","{}",report["failure"]);
        assert_eq!(jolt_after_kill,Some(false),"scene process outlived its killed worker");
    } else {assert!(report["failure"].is_null(),"{}",report["failure"]);}
    assert!(max_abs<=500.,"never leaves the playable area: {max_abs}");
}
