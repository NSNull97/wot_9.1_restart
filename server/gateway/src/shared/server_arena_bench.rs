//! ARENA-01 bench (ignored; run explicitly). K real profile13 arenas from a
//! pinned battle-profiles manifest, each with N SYNTHETIC owned actors (test
//! loadouts, scripted inputs) and its own real Jolt scene process. Measures the
//! arena step on its thread, the gateway-side view clone, process CPU and RSS.
//! Optional isolation: kill one arena's physics process mid-run. This is not a
//! native client and proves no native publication for more than six vehicles.
use super::*;
use std::process::Command as Process;
use std::collections::BTreeMap;

fn env(key:&str)->Option<String>{std::env::var(key).ok().filter(|v|!v.is_empty())}
fn percentile(sorted:&[f64],p:f64)->f64{
    if sorted.is_empty(){return 0.;}
    sorted[((sorted.len() as f64-1.)*p).round() as usize]
}
fn summary(mut values:Vec<f64>)->serde_json::Value{
    values.sort_by(|a,b|a.partial_cmp(b).unwrap());
    let mean=if values.is_empty(){0.}else{values.iter().sum::<f64>()/values.len() as f64};
    serde_json::json!({"n":values.len(),"mean_ms":mean,"p50_ms":percentile(&values,0.5),"p95_ms":percentile(&values,0.95),
        "p99_ms":percentile(&values,0.99),"max_ms":values.last().copied().unwrap_or(0.)})
}
/// CPU seconds and working set of the given processes, read by PowerShell.
fn sample(pids:&[u32])->BTreeMap<u32,(f64,u64)>{
    let list=pids.iter().map(u32::to_string).collect::<Vec<_>>().join(",");
    let script=format!("Get-Process -Id {list} -ErrorAction SilentlyContinue | ForEach-Object {{ \"$($_.Id) $($_.TotalProcessorTime.TotalSeconds) $($_.WorkingSet64)\" }}");
    let out=Process::new("powershell").args(["-NoProfile","-Command",&script]).output().expect("powershell sample");
    String::from_utf8_lossy(&out.stdout).lines().filter_map(|l|{let mut p=l.split_whitespace();
        Some((p.next()?.parse().ok()?,(p.next()?.replace(',',".").parse().ok()?,p.next()?.parse().ok()?)))}).collect()
}
fn physics_pid(a:&arena::Arena)->Option<u32>{
    a.integrated.as_ref()?.batch.as_ref()?.failure_snapshot()["process_id"].as_u64().map(|p|p as u32)
}
fn bench_arena(index:usize,template:&BattleTemplate,id:u64,size:usize,now:Instant)->arena::Arena{
    let mut a=arena::Arena::from_template(index,template,id,now).unwrap();
    for slot in 0..size {
        let kind=if slot%2==0{VehicleKind::Ms1}else{VehicleKind::Is7};
        let(mut owner,loadout)=model::tests::profile13_loadout(kind,slot,kind.ammo_limit());
        // Unique synthetic owners per arena; the loadout hash binds the account.
        owner.name=format!("arena{index}-synthetic-{slot}");
        let session=(index*100+slot+1) as u32;a.world.attach_owned(owner,session,&loadout).unwrap();
    }
    a
}
/// Scripted LAB inputs: forward with a slow per-slot steering pattern.
fn drive(a:&mut arena::Arena,tick:u64){
    for (slot,actor) in a.world.actors.iter_mut().enumerate() {
        let phase=(tick/40+slot as u64)%4;
        actor.input=model::Input{throttle:1,steer:match phase{0=>0,1=>1,2=>0,_=>-1},speed_percent:100};
    }
}

#[test]
#[ignore]
fn arena01_bench_real_scenes(){
    let manifest=PathBuf::from(env("ARENA01_BENCH_MANIFEST").expect("ARENA01_BENCH_MANIFEST"));
    let root=PathBuf::from(env("ARENA01_BENCH_LOCAL_ROOT").unwrap_or_else(||"D:/WoT_9.1_Server/local".into()));
    let out=PathBuf::from(env("ARENA01_BENCH_OUT").expect("ARENA01_BENCH_OUT"));
    let count:usize=env("ARENA01_BENCH_ARENAS").map_or(1,|v|v.parse().unwrap());
    let size:usize=env("ARENA01_BENCH_SIZE").map_or(30,|v|v.parse().unwrap());
    let seconds:u64=env("ARENA01_BENCH_SECONDS").map_or(60,|v|v.parse().unwrap());
    let kill:Option<usize>=env("ARENA01_BENCH_KILL").map(|v|v.parse().unwrap());
    assert!((2..=model::MAX_ACTORS).contains(&size)&&(1..=crate::identity091::MAX_ARENAS).contains(&count));
    let resources=super::super::profile13_templates::load(&root,&manifest).unwrap();
    let now=Instant::now();
    let ids=arena::arena_ids(count,0x5eed_0a7e_0001).unwrap();
    let mut template=BattleTemplate::from_shared_policy(&resources,size,ids[0],now,None,false).unwrap();
    template.world.enable_original_spotting(super::super::spotting::Rules::selected().unwrap()).unwrap();
    template.world.enable_result_spots().unwrap();
    let mut arenas=(0..count).map(|k|bench_arena(k,&template,ids[k],size,now)).collect::<Vec<_>>();
    // Startup: each arena launches its own scene process; wait for its first pose.
    // Start where the service starts a full arena; ready follows the settled
    // scene, as a native entry does (spawn rebase needs unready actors).
    let startup=Instant::now();let mut tick=0u64;
    for a in &mut arenas {a.world.start(startup).unwrap();}
    while !arenas.iter().all(|a|a.integrated.as_ref().is_some_and(|r|r.batch.as_ref().is_some_and(|b|b.ready_for_native()))) {
        assert!(startup.elapsed()<Duration::from_secs(150),"scene startup bound");
        let at=Instant::now();
        let commands=arenas.iter().map(|_|Some(arena::Command::Step{now:at,start:false})).collect::<Vec<_>>();
        for event in arena::step_all(&mut arenas,&commands) {
            assert!(matches!(event,Some(arena::Event::Stepped)),"{event:?} step_ms={} since_start_ms={}",at.elapsed().as_millis(),startup.elapsed().as_millis());
        }
        thread::sleep(Duration::from_millis(5));
    }
    let startup_ms=startup.elapsed().as_secs_f64()*1000.;
    for a in &mut arenas {for slot in 0..size {let session=(a.index*100+slot+1) as u32;a.world.set_ready(slot,session).unwrap();}}
    let pids=arenas.iter().map(|a|physics_pid(a).unwrap()).collect::<Vec<_>>();
    let me=std::process::id();let mut all=vec![me];all.extend(&pids);
    // PowerShell sampling takes ~1 s: it runs on its own thread so the step
    // loop never stalls (the lifecycle refuses a >1 s clock step, as in service).
    let stop=Arc::new(std::sync::atomic::AtomicBool::new(false));
    let sampler={let stop=stop.clone();let all=all.clone();thread::spawn(move||{
        let mut rows=Vec::new();
        while !stop.load(std::sync::atomic::Ordering::Acquire){rows.push((Instant::now(),sample(&all)));thread::sleep(Duration::from_millis(500));}
        rows.push((Instant::now(),sample(&all)));rows})};
    let measured=Instant::now();
    let mut tick_ms=Vec::new();let mut arena_ms:Vec<Vec<f64>>=vec![Vec::new();count];let mut view_ms=Vec::new();
    let mut failures:Vec<serde_json::Value>=Vec::new();let mut killed_at=None;let mut ticks_after_kill=vec![0u64;count];
    let mut failed=vec![false;count];let start_ticks=arenas.iter().map(|a|a.world.tick).collect::<Vec<_>>();
    while measured.elapsed()<Duration::from_secs(seconds) {
        tick+=1;
        if let Some(k)=kill.filter(|_|killed_at.is_none()&&measured.elapsed()>=Duration::from_secs(seconds/2)) {
            let status=Process::new("taskkill").args(["/F","/PID",&pids[k].to_string()]).output().unwrap().status;
            assert!(status.success(),"taskkill physics of arena {k}");killed_at=Some(measured.elapsed());
        }
        for (k,a) in arenas.iter_mut().enumerate() {if !failed[k]{drive(a,tick);}}
        let at=Instant::now();
        // Same shape as step_all, timed per arena: one scoped thread per live arena.
        let results=thread::scope(|scope|{
            let handles=arenas.iter_mut().enumerate().map(|(k,a)|{let skip=failed[k];scope.spawn(move||{
                if skip{return None;}let t=Instant::now();let e=a.handle(arena::Command::Step{now:at,start:false});
                Some((t.elapsed().as_secs_f64()*1000.,e))})}).collect::<Vec<_>>();
            handles.into_iter().map(|h|h.join().unwrap()).collect::<Vec<_>>()
        });
        tick_ms.push(at.elapsed().as_secs_f64()*1000.);
        for (k,r) in results.into_iter().enumerate() {
            let Some((ms,event))=r else{continue;};
            match event {
                arena::Event::Stepped=>{arena_ms[k].push(ms);if killed_at.is_some(){ticks_after_kill[k]+=1;}},
                arena::Event::Failed{stage,error}=>{
                    failures.push(serde_json::json!({"arena":k,"stage":stage,"error":error.to_string(),
                        "after_kill_ms":killed_at.map(|t|(measured.elapsed()-t).as_secs_f64()*1000.)}));
                    failed[k]=true;
                },
            }
        }
        // Gateway-side publication cost: one view clone per attached session.
        let t=Instant::now();
        for a in &arenas {for _ in 0..a.world.actors.len() {std::hint::black_box(a.world.clone());}}
        view_ms.push(t.elapsed().as_secs_f64()*1000.);
        thread::sleep(Duration::from_millis(5));
    }
    let wall=measured.elapsed().as_secs_f64();
    stop.store(true,std::sync::atomic::Ordering::Release);let rows=sampler.join().unwrap();
    let (first,last)=(rows.first().unwrap(),rows.last().unwrap());let interval=last.0.duration_since(first.0).as_secs_f64();
    let (begin,end)=(&first.1,&last.1);
    let mut peak:BTreeMap<u32,u64>=BTreeMap::new();
    for (_,row) in &rows {for (pid,(_,ws)) in row {let e=peak.entry(*pid).or_default();*e=(*e).max(*ws);}}
    let cpu=|pid:u32|end.get(&pid).zip(begin.get(&pid)).map(|(e,b)|e.0-b.0);
    // Domain steps are 100 ms; CPU is attributed over the sampled interval.
    let steps=interval*10.;
    let domain_steps=arenas.iter().zip(&start_ticks).map(|(a,s)|a.world.tick.saturating_sub(*s)).collect::<Vec<_>>();
    let report=serde_json::json!({
        "schema":"arena01-bench.v1","label":"SYNTHETIC actors (test loadouts, scripted inputs), real Jolt scene process per arena; not native",
        "build":if cfg!(debug_assertions){"debug"}else{"release"},"manifest":manifest,"arenas":count,"actors_per_arena":size,
        "spotting":"original_spotting+result_spots","mixed_ammo":false,"seconds":wall,"cpu_interval_s":interval,"samples":rows.len(),"loop_ticks":tick_ms.len(),
        "startup_ms":startup_ms,"domain_steps_per_arena":domain_steps,
        "tick_wall":summary(tick_ms),"arena_step_wall":arena_ms.into_iter().map(summary).collect::<Vec<_>>(),
        "view_clone_per_tick":summary(view_ms),
        "gateway":{"pid":me,"cpu_s":cpu(me),"cpu_ms_per_domain_step_per_arena":cpu(me).map(|c|c*1000./steps/count as f64),"cpu_share_of_one_core":cpu(me).map(|c|c/interval),
            "working_set_end":end.get(&me).map(|v|v.1),"working_set_peak":peak.get(&me)},
        "physics":pids.iter().map(|p|serde_json::json!({"pid":p,"cpu_s":cpu(*p),
            "cpu_ms_per_domain_step":cpu(*p).map(|c|c*1000./steps),"cpu_share_of_one_core":cpu(*p).map(|c|c/interval),
            "working_set_end":end.get(p).map(|v|v.1),"working_set_peak":peak.get(p)})).collect::<Vec<_>>(),
        "kill":kill.map(|k|serde_json::json!({"arena":k,"at_s":killed_at.map(|t|t.as_secs_f64()),"steps_after_kill":ticks_after_kill})),
        "failures":failures,
    });
    if let Some(parent)=out.parent(){fs::create_dir_all(parent).unwrap();}
    fs::write(&out,serde_json::to_vec_pretty(&report).unwrap()).unwrap();
    println!("ARENA01_BENCH {}",serde_json::to_string(&report).unwrap());
    if let Some(k)=kill {
        assert!(failed[k],"killed arena failed closed");
        assert!((0..count).filter(|i|*i!=k).all(|i|!failed[i]),"other arenas kept stepping");
    } else {assert!(failures.is_empty(),"{failures:?}");}
}
