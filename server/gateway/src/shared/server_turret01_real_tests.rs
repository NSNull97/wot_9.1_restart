//! TURRET-01 checks with a real Jolt scene worker (ignored; run explicitly).
//! One profile13 arena from a pinned battle-profiles manifest whose
//! `shared_physics` is a build of this branch, SYNTHETIC owned actors or bots,
//! and SYNTHETIC rack detonations through `force_detonation_for_test` (the real
//! ledger, death bookkeeping, battle RNG launch and worker body; no projectile).
//! Not a native client run: what the 0.9.1 client draws is NOT_RUN here.
use super::*;
use super::arena_bench::{env,summary};

fn template(resources:&[super::super::profile13_templates::Resources],size:usize,id:u64,now:Instant)->BattleTemplate{
    let mut template=BattleTemplate::from_shared_policy(resources,size,id,now,None,false).unwrap();
    template.world.enable_mixed_ammo().unwrap();
    template.world.enable_original_spotting(super::super::spotting::Rules::selected().unwrap()).unwrap();
    template.world.enable_ammo_detonation().unwrap();
    if size>wire::MAX_NATIVE_ACTORS{template.world.enable_team_base_spawn().unwrap();}
    template
}
fn step(a:&mut arena::Arena,what:&str){
    match a.handle(arena::Command::Step{now:Instant::now(),start:false}) {
        arena::Event::Stepped=>{},
        arena::Event::Failed{stage,error}=>panic!("TURRET01 {what} failed stage={stage} error={error}"),
    }
}
fn settle(a:&mut arena::Arena,humans:usize){
    let startup=Instant::now();let mut first=true;
    while !a.native_ready() {
        assert!(startup.elapsed()<Duration::from_secs(150),"scene startup bound");
        let event=a.handle(arena::Command::Step{now:Instant::now(),start:first});first=false;
        assert!(matches!(event,arena::Event::Stepped),"{event:?}");thread::sleep(Duration::from_millis(5));
    }
    for slot in 0..humans {a.world.set_ready(slot,slot as u32+1).unwrap();}
}
fn resting(a:&arena::Arena)->bool{
    a.world.turret_flights().iter().all(|f|f.trajectory().is_some()&&f.sample().phase==super::super::ammo_detonation::FlightPhase::Resting)
}
fn trajectory_json(a:&arena::Arena,slot:usize)->serde_json::Value{
    let f=a.world.turret_flights().iter().find(|f|f.event().target()==slot).unwrap();let t=f.trajectory().unwrap();
    let(rest,all)=a.world.turret_clearance_for_test(slot).unwrap();
    let first=t.samples[0].position;let last=t.samples.last().unwrap().position;
    serde_json::json!({"slot":slot,"attacker":f.event().attacker(),"kind":f.event().kind().label(),"launch":format!("{:?}",f.launch().unwrap()),
        "samples":t.samples.len(),"slept":t.slept,"start":first,"rest":last,"rest_direction":t.samples.last().unwrap().direction,
        "displacement":[last[0]-first[0],last[1]-first[1],last[2]-first[2]],"rest_min_clearance_m":rest,"flight_min_clearance_m":all})
}

/// Two detonations at once and one later: each gets its own Jolt body; the
/// bodies come to rest with every turret and gun support point above the
/// terrain; an identical body request repeats the trajectory bit for bit.
#[test]
#[ignore]
fn turret01_detached_bodies_in_real_jolt_scene(){
    let manifest=PathBuf::from(env("TURRET01_MANIFEST").expect("TURRET01_MANIFEST"));
    let root=PathBuf::from(env("TURRET01_LOCAL_ROOT").unwrap_or_else(||"D:/WoT_9.1_Server/local".into()));
    let out=PathBuf::from(env("TURRET01_OUT").expect("TURRET01_OUT"));
    let resources=super::super::profile13_templates::load(&root,&manifest).unwrap();
    let now=Instant::now();let id=env("TURRET01_SEED").map_or(0x7e57_7e01_0001,|v|v.parse().unwrap());let size=6;
    let template=template(&resources,size,id,now);
    let mut a=arena::Arena::from_template(0,&template,id,now).unwrap();
    for slot in 0..size {
        let kind=if slot%2==0{VehicleKind::Ms1}else{VehicleKind::Is7};
        let(mut owner,loadout)=model::tests::profile13_loadout(kind,slot,kind.ammo_limit());
        owner.name=format!("turret01-synthetic-{slot}");a.world.attach_owned(owner,slot as u32+1,&loadout).unwrap();
    }
    a.world.start(Instant::now()).unwrap();settle(&mut a,size);
    assert!(a.world.turret_jolt(),"the scene runtime selects Jolt turrets");
    for _ in 0..20 {step(&mut a,"warm");thread::sleep(Duration::from_millis(5));}
    // Two detonations in one tick, a third one second later.
    a.world.force_detonation_for_test(1,0,1).unwrap();a.world.force_detonation_for_test(4,3,2).unwrap();
    let detonated=Instant::now();let mut third=false;
    while !(third&&resting(&a)) {
        assert!(detonated.elapsed()<Duration::from_secs(30),"bodies must come to rest");
        if !third&&detonated.elapsed()>=Duration::from_secs(1){a.world.force_detonation_for_test(5,2,3).unwrap();third=true;}
        step(&mut a,"flight");thread::sleep(Duration::from_millis(5));
    }
    let slots=[1,4,5];let rows=slots.iter().map(|s|trajectory_json(&a,*s)).collect::<Vec<_>>();
    // Same body request, same worker: the identical trajectory.
    let batch=a.integrated.as_mut().unwrap().batch.as_mut().unwrap();
    let mut repeats=Vec::new();
    for slot in slots {
        let again=batch.relaunch_turret_for_test(&a.world,slot).unwrap();
        let installed=a.world.turret_flights().iter().find(|f|f.event().target()==slot).unwrap().trajectory().unwrap().clone();
        let same=again.samples.len()==installed.samples.len()&&again.samples.iter().zip(&installed.samples).all(|((p,d),j)|
            p.iter().zip(j.position).chain(d.iter().zip(j.direction)).all(|(x,y)|x.to_bits()==y.to_bits()));
        repeats.push((slot,same));
    }
    let displacement=|i:usize|rows[i]["displacement"].as_array().unwrap().iter().map(|v|v.as_f64().unwrap()).collect::<Vec<_>>();
    let distinct=(0..3).all(|i|(i+1..3).all(|j|displacement(i).iter().zip(displacement(j)).any(|(x,y)|(x-y).abs()>0.05)));
    let clear=rows.iter().all(|r|r["rest_min_clearance_m"].as_f64().unwrap()>=-0.05&&r["flight_min_clearance_m"].as_f64().unwrap()>=-0.15);
    let slept=rows.iter().all(|r|r["slept"]==true);
    let ok=distinct&&clear&&slept&&repeats.iter().all(|(_,s)|*s);
    let report=serde_json::json!({"schema":"turret01-real.v1","label":"SYNTHETIC actors and detonations, real Jolt scene worker; not native",
        "build":if cfg!(debug_assertions){"debug"}else{"release"},"manifest":manifest,"map":a.world.map.asset(),"battle_seed":id,
        "launch_policy":super::super::ammo_detonation::JOLT_POLICY,"body_policy":crate::scene_worker::TURRET_POLICY,
        "flights":rows,"identical_repeat":repeats.iter().map(|(s,b)|serde_json::json!({"slot":s,"bitwise_equal":b})).collect::<Vec<_>>(),
        "distinct_displacements":distinct,"clearance_ok":clear,"all_slept":slept,"pass":ok});
    if let Some(parent)=out.parent(){fs::create_dir_all(parent).unwrap();}
    fs::write(&out,serde_json::to_vec_pretty(&report).unwrap()).unwrap();
    println!("TURRET01_REAL map={} pass={ok} distinct={distinct} clear={clear} slept={slept} repeats={repeats:?}",a.world.map.asset());
    assert!(ok,"see {}",out.display());
}

/// 30 places (1 scripted native + 29 bots), several detonations during the
/// battle: the arena step after the detonations versus before them.
#[test]
#[ignore]
fn turret01_bench_thirty_places_with_detonations(){
    let manifest=PathBuf::from(env("TURRET01_MANIFEST").expect("TURRET01_MANIFEST"));
    let root=PathBuf::from(env("TURRET01_LOCAL_ROOT").unwrap_or_else(||"D:/WoT_9.1_Server/local".into()));
    let out=PathBuf::from(env("TURRET01_OUT").expect("TURRET01_OUT"));
    let size:usize=env("TURRET01_SIZE").map_or(30,|v|v.parse().unwrap());
    let waves:usize=env("TURRET01_WAVES").map_or(4,|v|v.parse().unwrap());
    let resources=super::super::profile13_templates::load(&root,&manifest).unwrap();
    let kinds=resources.iter().map(|r|r.kind).collect::<Vec<_>>();
    let now=Instant::now();let id=arena::arena_ids(1,0x7e57_7e01_0030).unwrap()[0];
    let mut template=template(&resources,size,id,now);
    template.world.enable_result_spots().unwrap();
    template.world.enable_bots(model::bots::Plan{human_places:1,seed:1,kinds}).unwrap();
    let mut a=arena::Arena::from_template(0,&template,id,now).unwrap();
    let(mut owner,loadout)=model::tests::profile13_loadout(VehicleKind::Ms1,0,VehicleKind::Ms1.ammo_limit());
    owner.name="turret01-bench-native".into();a.world.attach_owned(owner,1,&loadout).unwrap();
    assert_eq!(a.world.fill_bots().unwrap(),size-1);
    let startup=Instant::now();let mut first=true;
    while !a.native_ready() {
        assert!(startup.elapsed()<Duration::from_secs(150),"scene startup bound");
        let event=a.handle(arena::Command::Step{now:Instant::now(),start:first});first=false;
        assert!(matches!(event,arena::Event::Stepped),"{event:?}");thread::sleep(Duration::from_millis(5));
    }
    a.world.set_ready(0,1).unwrap();
    let names=super::super::step_profile::NAMES;let turret_part=names.iter().position(|n|*n=="turret_flights").unwrap();
    let mut before=Vec::new();let mut after=Vec::new();let mut turret_ms=Vec::new();
    let mut battle_from=None;let mut next_wave=0usize;let mut detonated=Vec::new();let mut failure=None;let measured=Instant::now();
    let mut loops=0u64;
    while measured.elapsed()<Duration::from_secs(30+20+10*waves as u64+15) {
        loops+=1;let phase=(loops/400)%4;
        a.world.actors[0].input=model::Input{throttle:1,steer:match phase{0=>0,1=>1,2=>0,_=>-1},speed_percent:100};
        let battle=a.world.lifecycle.as_ref().is_some_and(|l|l.allows_actions());
        if battle {let from=*battle_from.get_or_insert(Instant::now());
            // A wave of two detonations every 10 s, from the 10th battle second.
            if next_wave<waves&&from.elapsed()>=Duration::from_secs(10+10*next_wave as u64) {
                let alive=(1..a.world.actors.len()).filter(|s|a.world.actors[*s].alive()).collect::<Vec<_>>();
                for target in alive.iter().rev().take(2) {
                    let attacker=*alive.iter().find(|s|*s!=target).unwrap();
                    let shot=a.world.shots.len() as u32+1+detonated.len() as u32;
                    a.world.force_detonation_for_test(*target,attacker,shot).unwrap();detonated.push(*target);
                }
                next_wave+=1;
            }
        }
        let parts0=super::super::step_profile::snapshot();
        let t=Instant::now();let event=a.handle(arena::Command::Step{now:t,start:false});let ms=t.elapsed().as_secs_f64()*1000.;
        let parts1=super::super::step_profile::snapshot();
        if battle {if detonated.is_empty(){before.push(ms);}else{after.push(ms);}
            turret_ms.push((parts1[turret_part]-parts0[turret_part]) as f64/1e6);}
        if let arena::Event::Failed{stage,error}=event {failure=Some(serde_json::json!({"stage":stage,"error":error.to_string()}));break;}
        if a.world.lifecycle.as_ref().is_some_and(|l|l.outcome().is_some())&&next_wave>=waves&&resting(&a) {break;}
        thread::sleep(Duration::from_millis(5));
    }
    let flights=a.world.turret_flights().iter().map(|f|serde_json::json!({"slot":f.event().target(),
        "installed":f.trajectory().is_some(),"samples":f.trajectory().map(|t|t.samples.len()),"slept":f.trajectory().map(|t|t.slept),
        "phase":format!("{:?}",f.sample().phase)})).collect::<Vec<_>>();
    let (b,af)=(summary(before),summary(after));
    let installed=a.world.turret_flights().iter().all(|f|f.trajectory().is_some());
    let grown=af["p99_ms"].as_f64().unwrap()>b["p99_ms"].as_f64().unwrap()*1.5+5.;
    let report=serde_json::json!({"schema":"turret01-bench.v1","label":"SYNTHETIC native place + bots, SYNTHETIC detonations, real Jolt scene; not native",
        "build":if cfg!(debug_assertions){"debug"}else{"release"},"manifest":manifest,"map":a.world.map.asset(),"actors":size,"waves":waves,
        "detonated":detonated,"loops":loops,"step_battle_before_detonations":b,"step_battle_after_detonations":af,"turret_part":summary(turret_ms),
        "flights":flights,"all_installed":installed,"step_grown":grown,"failure":failure,
        "outcome":a.world.lifecycle.as_ref().and_then(|l|l.outcome()).map(|o|format!("{o:?}"))});
    if let Some(parent)=out.parent(){fs::create_dir_all(parent).unwrap();}
    fs::write(&out,serde_json::to_vec_pretty(&report).unwrap()).unwrap();
    println!("TURRET01_BENCH {}",serde_json::to_string(&report).unwrap());
    assert!(report["failure"].is_null(),"{}",report["failure"]);
    assert!(installed&&!detonated.is_empty(),"every detonation got its body");assert!(!grown,"step grew after detonations");
}
