//! NET-01 bench (ignored; run explicitly, release). The BOT-01 arena (one
//! SYNTHETIC native place with scripted input + server bots, real Jolt scene,
//! real lifecycle) plus that place's gateway Session on the real publication
//! and send path (`poll_battle_session`, `transmit`), and a modelled client:
//! loopback delivery, processing and ACK once per client frame, optional
//! stalls. Measures pose gaps/age as the client sees them and how long
//! reliable bodies wait. Client spotting is off: all 30 vehicles are
//! published every tick (the most bodies). HP bodies are not (see loop).
//! Not a native battle.
use super::*;
use super::super::net01::PoseDelivery;
use super::arena_bench::{env,summary,sample,physics_pid};
use super::bot01_bench::{step,children};

struct ClientModel {
    frame:Duration,stall_every:Option<Duration>,stall:Duration,next_frame:Instant,stall_until:Option<Instant>,last_stall:Instant,
    inbox:Vec<(Instant,Vec<u8>)>,expected:u32,unreliable_seq:u32,newest_pose:Option<u32>,
    pose_ticks:Vec<u32>,pose_age_ticks:Vec<f64>,reliable_delay_ms:Vec<f64>,pose_delay_ms:Vec<f64>,frames:u64,
}
impl ClientModel {
    /// Low tick byte of tickSync relative to the server tick at send (wraps every 256).
    fn unwrap_tick(low:u8,server:u32)->u32 {let base=server&!0xff;let t=base|u32::from(low);if t>server {t-256} else {t}}
    fn frame(&mut self,s:&mut Session,world:&World,now:Instant,server_tick:u32)->io::Result<()> {
        if let Some(until)=self.stall_until {if now<until {return Ok(());} self.stall_until=None;}
        if let Some(every)=self.stall_every {
            if now.duration_since(self.last_stall)>=every {self.last_stall=now;self.stall_until=Some(now+self.stall);return Ok(());}
        }
        if now<self.next_frame {return Ok(());}
        self.next_frame=now+self.frame;self.frames+=1;
        let mut buffered:Vec<(u32,Instant,Vec<u8>)>=Vec::new();
        for (sent,clear) in std::mem::take(&mut self.inbox) {
            let f=transport091::parse_interactive(&clear)?;
            let delay=now.saturating_duration_since(sent).as_secs_f64()*1000.;
            if f.flags&0x10!=0 {
                let seq=f.sequence.ok_or_else(||model::bad())?;
                if seq>=self.expected {buffered.push((seq,sent,f.body));}
                continue;
            }
            if f.body.first()==Some(&0x0d) {
                let tick=Self::unwrap_tick(f.body[1],server_tick);
                self.pose_delay_ms.push(delay);
                if self.newest_pose.is_none_or(|n|tick>n) {self.newest_pose=Some(tick);self.pose_ticks.push(tick);}
            }
        }
        // In-order reliable delivery, as the native channel does.
        buffered.sort_by_key(|b|b.0);buffered.dedup_by_key(|b|b.0);
        for (seq,sent,body) in buffered {
            if seq!=self.expected {break;}
            self.expected+=1;
            let delay=now.saturating_duration_since(sent).as_secs_f64()*1000.;
            if body.first()==Some(&0x0d) {
                let tick=Self::unwrap_tick(body[1],server_tick);self.pose_delay_ms.push(delay);
                if self.newest_pose.is_none_or(|n|tick>n) {self.newest_pose=Some(tick);self.pose_ticks.push(tick);}
            // A reliable-burst-v2 later part (no tickSync) is pose data too.
            } else if !body.is_empty() && body[0]!=0x15 {self.reliable_delay_ms.push(delay);}
        }
        if let Some(newest)=self.newest_pose {self.pose_age_ticks.push(f64::from(server_tick.saturating_sub(newest)));}
        // The client ACKs on its own unreliable channel packet (0x0448, P02).
        let ack=transport091::Frame{flags:0x448,sequence:Some(self.unreliable_seq),cumulative:Some(self.expected),
            selective:vec![],body:vec![],piggybacks:vec![]};
        // Through the gateway's receive path (staged Session clone + refresh).
        self.unreliable_seq+=1;receive_battle_session(s,&ack,world,now)?;Ok(())
    }
}

#[test]
#[ignore]
fn net01_bench_pose_delivery(){
    let manifest=PathBuf::from(env("BOT01_BENCH_MANIFEST").expect("BOT01_BENCH_MANIFEST"));
    let root=PathBuf::from(env("BOT01_BENCH_LOCAL_ROOT").unwrap_or_else(||"D:/WoT_9.1_Server/local".into()));
    let out=PathBuf::from(env("NET01_BENCH_OUT").expect("NET01_BENCH_OUT"));
    let mode=match env("NET01_BENCH_MODE").as_deref(){None|Some("reliable")=>PoseDelivery::Reliable,
        Some(m)=>PoseDelivery::parse(Some(m)).expect("NET01_BENCH_MODE")};
    let seconds:u64=env("BOT01_BENCH_SECONDS").map_or(90,|v|v.parse().unwrap());
    let seed:u64=env("BOT01_BENCH_SEED").map_or(1,|v|v.parse().unwrap());
    // As on stand -11: p06t mixed ammunition and ammo-rack detonation.
    let mixed=env("NET01_BENCH_MIXED").as_deref()==Some("1");
    let client_frame=Duration::from_millis(env("NET01_BENCH_CLIENT_FRAME_MS").map_or(33,|v|v.parse().unwrap()));
    let stall_every=env("NET01_BENCH_STALL_EVERY_S").map(|v|Duration::from_secs(v.parse().unwrap()));
    let stall=Duration::from_millis(env("NET01_BENCH_STALL_MS").map_or(0,|v|v.parse().unwrap()));
    let size=30;let humans=1;
    let resources=super::super::profile13_templates::load(&root,&manifest).unwrap();
    let kinds=resources.iter().map(|r|r.kind).collect::<Vec<_>>();
    let now=Instant::now();
    let id=arena::arena_ids(1,0x5eed_b071_0001).unwrap()[0];
    let mut template=BattleTemplate::from_shared_policy(&resources,size,id,now,None,false).unwrap();
    template.world.enable_original_spotting(super::super::spotting::Rules::selected().unwrap()).unwrap();
    template.world.enable_result_spots().unwrap();template.world.enable_team_base_spawn().unwrap();
    if mixed {template.world.enable_mixed_ammo().unwrap();template.world.enable_ammo_detonation().unwrap();}
    template.world.enable_bots(model::bots::Plan{human_places:humans,seed,kinds:kinds.clone()}).unwrap();
    let mut a=arena::Arena::from_template(0,&template,id,now).unwrap();
    // BW-01: NET01_BENCH_WORKER=1 steps the arena in its battle worker process.
    let worker=env("NET01_BENCH_WORKER").as_deref()==Some("1");
    if worker {a.worker=Some(Box::new(super::battle_worker::Remote::new(super::battle_worker::tests::settings())));}
    let kind=VehicleKind::Ms1;
    let(mut owner,loadout)=model::tests::profile13_loadout(kind,0,kind.ammo_limit());owner.name="bench-native-0".into();
    if mixed {assert_eq!(a.world.attach_native_stand_in(owner,1,kind).unwrap(),0);}
    else {assert_eq!(a.world.attach_owned(owner,1,&loadout).unwrap(),0);}
    let startup=Instant::now();assert_eq!(a.world.fill_bots().unwrap(),size-humans);
    let mut first=true;
    while !a.native_ready() {
        assert!(startup.elapsed()<Duration::from_secs(150),"scene startup bound");
        let event=step(&mut a,arena::Command::Step{now:Instant::now(),start:first});first=false;
        assert!(matches!(event,arena::Event::Stepped),"{event:?}");thread::sleep(Duration::from_millis(5));
    }
    a.world.set_ready(0,1).unwrap();
    let me=std::process::id();let worker_pid=a.worker.as_ref().and_then(|w|w.pid());
    let scene=match worker_pid {Some(w)=>children(w).first().copied(),None=>physics_pid(&a)};
    let pids=[Some(me),worker_pid,scene].into_iter().flatten().collect::<Vec<_>>();let cpu0=sample(&pids);
    // The native place's Session: Driving, all creations acknowledged.
    let (mut s,_)=super::tests::driving(Instant::now());
    {let c=s.shared.as_mut().unwrap();c.creations=[Some((0,true));model::MAX_ACTORS];c.ready_sent=[true;model::MAX_ACTORS];
        c.area_creation=Some((0,true));c.pose_delivery=mode;c.view=Some(a.world.clone());
        if let Some(state)=a.world.fragiles.as_ref(){let n=state.catalog.chunks().len();c.announced_areas=n;c.areas=vec![(Some((0,true)),Vec::new());n];}}
    let t0=Instant::now();
    let mut client=ClientModel{frame:client_frame,stall_every,stall,next_frame:t0,stall_until:None,last_stall:t0,inbox:Vec::new(),
        expected:s.tx.cumulative,unreliable_seq:1,newest_pose:None,pose_ticks:Vec::new(),pose_age_ticks:Vec::new(),
        reliable_delay_ms:Vec::new(),pose_delay_ms:Vec::new(),frames:0};
    let mut stats=super::super::net01::LoopStats::default();let mut reports=Vec::new();
    let mut window=transport091::WindowStats::default();let mut pose_totals=super::super::net01::PoseStats::default();
    let measured=Instant::now();let mut failure=None;let mut loops=0u64;let start_tick=a.world.tick;
    let mut battle_from_tick=None;let mut frames_sent=(0u64,0u64,0u64);
    while measured.elapsed()<Duration::from_secs(30+seconds) {
        loops+=1;let loop_start=Instant::now();
        let phase=(loops/400)%4;a.world.actors[0].input=model::Input{throttle:1,steer:match phase{0=>0,1=>1,2=>0,_=>-1},speed_percent:100};
        let st=Instant::now();let event=step(&mut a,arena::Command::Step{now:st,start:false});let step_wall=st.elapsed();
        if let arena::Event::Failed{stage,error}=event {failure=Some(format!("{stage}: {error}"));break;}
        let battle=a.world.lifecycle.as_ref().is_some_and(|l|l.allows_actions());
        if battle {battle_from_tick.get_or_insert(a.world.tick);}
        // Without mixed ammo the legacy HP path needs an AP impact per HP change
        // and rams lack one, so HP bodies are left out there. Mixed: published.
        if !mixed {let c=s.shared.as_mut().unwrap();for (i,x) in a.world.actors.iter().enumerate(){c.health_sent[i]=Some(x.health);}c.owner_health_sent=Some(a.world.actors[0].health);}
        let pt=Instant::now();
        let (native_ready,blocked)=(a.native_ready(),a.blocked());
        if let Err(error)=poll_battle_session(&mut s,&mut a.world,pt,native_ready,blocked) {failure=Some(format!("poll: {error}"));break;}
        let sent=Instant::now();
        match transmit(&mut s,sent) {
            Ok(Some(frames))=>for clear in frames {
                let f=transport091::parse_interactive(&clear).unwrap();
                if f.flags&0x10!=0 {frames_sent.0+=1;} else {frames_sent.1+=1;}frames_sent.2+=clear.len() as u64;
                client.inbox.push((sent,clear));
            },
            Ok(None)=>{failure=Some("retry_exhausted".into());break;},
            Err(error)=>{failure=Some(format!("transmit: {error}"));break;},
        }
        let publish=pt.elapsed();
        if let Some(c)=s.shared.as_mut() {c.view=Some(a.world.clone());}
        if let Err(error)=client.frame(&mut s,&a.world,Instant::now(),a.world.tick) {failure=Some(format!("client ack: {error}"));break;}
        let end=Instant::now();stats.record(loop_start,step_wall,publish,&[Some(a.world.tick)],end);
        if let Some(line)=stats.take_report(end) {
            let w=std::mem::take(&mut s.tx.stats);let p=s.shared.as_mut().unwrap().take_pose_stats();
            reports.push(serde_json::json!({"loop":line,"ack_wait":w.ack_wait.summary(),"queue_wait":w.queue_wait.summary(),
                "pending_max":w.pending_max,"resends":w.resends,"pose_gap_max":p.gap_max,"pose_gaps_over_1":p.gaps_over_one,"poses":p.published}));
            merge(&mut window,&w);add(&mut pose_totals,&p);
        }
        if a.world.lifecycle.as_ref().is_some_and(|l|l.outcome().is_some()) {break;}
        thread::sleep(Duration::from_millis(5));
    }
    let cpu1=sample(&pids);let steps=f64::from(a.world.tick.saturating_sub(start_tick)).max(1.);
    let cpu=|pid:Option<u32>|pid.and_then(|p|Some((cpu1.get(&p)?.0-cpu0.get(&p)?.0)*1000./steps));
    let processes=serde_json::json!({"cpu_ms_per_domain_step":{"gateway":cpu(Some(me)),"worker":cpu(worker_pid),"scene":cpu(scene)},
        "working_set_end":{"gateway":cpu1.get(&me).map(|v|v.1),"worker":worker_pid.and_then(|p|cpu1.get(&p)).map(|v|v.1),"scene":scene.and_then(|p|cpu1.get(&p)).map(|v|v.1)}});
    {let w=std::mem::take(&mut s.tx.stats);merge(&mut window,&w);let p=s.shared.as_mut().unwrap().take_pose_stats();add(&mut pose_totals,&p);}
    // What one clone costs at the end of the battle, and what makes it big.
    let clone_ms=|f:&dyn Fn()|{let t=Instant::now();for _ in 0..50 {f();}t.elapsed().as_secs_f64()*1000./50.};
    let world_clone_ms=clone_ms(&||{std::hint::black_box(a.world.clone());});
    let session_clone_ms=clone_ms(&||{std::hint::black_box(s.clone());});
    let w=&a.world;
    let sizes=serde_json::json!({"shots":w.shots.len(),"projectiles":w.projectiles.len(),"impacts":w.impacts.len(),"contacts":w.contacts.len(),
        "terrain_contacts":w.terrain_contacts.len(),"damage_events":w.damage_events.len(),"device_events":w.device_events.len(),
        "rng_draws":w.rng_draws.len(),"ram_damage_events":w.ram_damage_events.len(),"impact_trace":w.impact.events().len()});
    let from=battle_from_tick.unwrap_or(start_tick);
    let ticks:Vec<u32>=client.pose_ticks.iter().copied().filter(|t|*t>=from).collect();
    let gaps:Vec<f64>=ticks.windows(2).map(|w|f64::from(w[1]-w[0])).collect();
    let span=ticks.last().zip(ticks.first()).map_or(0,|(l,f)|l-f+1);
    let report=serde_json::json!({
        "schema":"net01-bench.v1","label":"SYNTHETIC native place + 29 server bots, real Jolt scene, real publication/transmit, modelled loopback client; not native",
        "build":if cfg!(debug_assertions){"debug"}else{"release"},"mode":mode.label(),
        "step_mode":if worker{"battle_worker"}else{"in_process"},"processes":processes,
        "worker":a.worker.as_ref().map(|r|serde_json::json!({"steps":r.steps,"last_frame_bytes":r.frame_bytes,"last_step_ns_in_worker":r.step_ns})),"manifest":manifest,"map":a.world.map.asset(),"seed":seed,
        "client":{"frame_ms":client_frame.as_millis() as u64,"stall_every_s":stall_every.map(|d|d.as_secs()),"stall_ms":stall.as_millis() as u64,"frames":client.frames},
        "loops":loops,"domain_ticks":a.world.tick.saturating_sub(start_tick),"battle_from_tick":battle_from_tick,
        "client_pose":{"distinct_ticks_seen":ticks.len(),"tick_span":span,"missed_ticks":span.saturating_sub(ticks.len() as u32),
            "gap_ticks":summary(gaps.clone()),"gaps_over_1":gaps.iter().filter(|g|**g>1.).count(),
            "age_ticks_at_client_frame":summary(client.pose_age_ticks.clone()),"delivery_ms":summary(client.pose_delay_ms.clone())},
        "reliable_non_pose_delivery_ms":summary(client.reliable_delay_ms.clone()),
        "server":{"ack_wait":window.ack_wait.summary(),"queue_wait":window.queue_wait.summary(),"pending_max":window.pending_max,"resends":window.resends,
            "pose_publications":pose_totals.published,"pose_gap_max_ticks":pose_totals.gap_max,"pose_gaps_over_1":pose_totals.gaps_over_one,
            "pose_replaced_unsent":pose_totals.replaced_unsent,"frames_reliable":frames_sent.0,"frames_unreliable":frames_sent.1,"bytes":frames_sent.2},
        "reports":reports,"failure":failure,"mixed_ammo":mixed,
        "end_of_battle":{"world_clone_ms":world_clone_ms,"session_clone_ms":session_clone_ms,"journal_lengths":sizes},
        "behaviour":{"bot_shots":a.world.bot_shots(),"shots_total":a.world.shots.len(),"vehicles_dead":a.world.actors.iter().filter(|x|!x.alive()).count()},
    });
    if let Some(parent)=out.parent(){fs::create_dir_all(parent).unwrap();}
    fs::write(&out,serde_json::to_vec_pretty(&report).unwrap()).unwrap();
    println!("NET01_BENCH {}",serde_json::to_string(&report).unwrap());
    assert!(report["failure"].is_null(),"{}",report["failure"]);
}
fn merge(total:&mut transport091::WindowStats,w:&transport091::WindowStats) {
    total.ack_wait.merge(&w.ack_wait);total.queue_wait.merge(&w.queue_wait);
    total.pending_max=total.pending_max.max(w.pending_max);total.resends+=w.resends;
}
fn add(total:&mut super::super::net01::PoseStats,p:&super::super::net01::PoseStats) {
    total.published+=p.published;total.gap_max=total.gap_max.max(p.gap_max);total.gaps_over_one+=p.gaps_over_one;
    total.replaced_unsent+=p.replaced_unsent;total.packets+=p.packets;total.bytes+=p.bytes;total.outbox_max=total.outbox_max.max(p.outbox_max);
}
