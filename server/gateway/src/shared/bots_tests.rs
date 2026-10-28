//! BOT-01 unit tests on the bounded LAB kinematics World (no Jolt, no native
//! client): identity, the player's input path, visibility gating, firing gate,
//! map bounds and deterministic replay. The real scene is the ignored bench.
use super::*;
use super::super::super::{lifecycle,geometry,terrain,spotting,obstacles};
use crate::map_profile091::MapId;

const ID:u64=0x5eed_b071;

/// A bot-enabled template World before any native attaches.
pub(crate) fn prepared(map:MapId,humans:usize,places:usize,seed:u64,now:Instant)->World{
    let mut w=World::new_for_roster(ID,now,map,places).unwrap();
    let mut rules=lifecycle::Rules::for_map(map).unwrap();rules.prebattle_ms=1000;w.enable_lifecycle(rules).unwrap();
    w.bind_geometry(Arc::new(geometry::tests::bundle())).unwrap();
    w.terrain=Some(Arc::new(terrain::tests::fixture_for_map(map)));
    w.enable_original_spotting(spotting::Rules::selected().unwrap()).unwrap();
    w.enable_bots(Plan{human_places:humans,seed,kinds:vec![VehicleKind::Ms1]}).unwrap();w
}
fn fixture_on(map:MapId,humans:usize,places:usize,seed:u64,now:Instant)->World{
    let mut w=prepared(map,humans,places,seed,now);
    for slot in 0..humans{
        let(identity,loadout)=super::super::tests::profile13_loadout(VehicleKind::Ms1,slot,7);
        assert_eq!(w.attach_owned(identity,slot as u32+1,&loadout).unwrap(),slot);
    }
    w
}
fn fixture(humans:usize,places:usize,seed:u64,now:Instant)->World{fixture_on(MapId::Prohorovka,humans,places,seed,now)}
fn place(w:&mut World,slot:usize,position:[f32;3],yaw:f32){
    let a=&mut w.actors[slot];a.position=position;a.origin=position;a.yaw=yaw;a.direction=[yaw,0.,0.];
}
/// Start, ready everyone, run the countdown; returns the first battle instant.
fn begin(w:&mut World,now:Instant)->Instant{
    w.start(now).unwrap();
    for slot in 0..w.human_places(){w.set_ready(slot,slot as u32+1).unwrap();}
    assert_eq!(w.ready_bots().unwrap(),w.actors.len()-w.human_places());
    let mut at=now;w.advance_lifecycle(at).unwrap();
    for _ in 0..10{at+=STEP;w.advance_lifecycle(at).unwrap();w.advance(at).unwrap();}
    assert!(w.lifecycle.as_ref().unwrap().allows_actions());at
}
/// The arena step order: bot decisions, motion, spotting, lifecycle.
fn tick(w:&mut World,at:Instant)->usize{
    let issued=w.drive_bots(at).unwrap();w.advance(at).unwrap();w.refresh_original_spotting(at).unwrap();w.advance_lifecycle(at).unwrap();issued
}

#[test]
fn bot01_fill_is_synthetic_atomic_and_follows_the_native_places(){
    let now=Instant::now();let mut w=fixture(2,6,3,now);
    let before=w.actors.clone();
    w.fill_bots().unwrap();
    assert_eq!(w.actors.len(),6);assert_eq!(&w.actors[..2],&before[..]);
    for slot in 2..6{
        let a=&w.actors[slot];
        assert_eq!(a.bot,Some((slot-2) as u8));assert_eq!(a.session,Some(SESSION_BASE+slot as u32));
        assert_eq!(a.identity.account,format!("bot01:{}",slot-2));assert_eq!(a.identity.name,format!("Bot-{:02}",slot-1));
        assert!(a.identity.database>=DATABASE_BASE);assert!(!a.ready);
        assert!(a.owned_v2.is_none()&&a.owned_loss.is_none()&&a.owned_hold.is_none(),"no owned admission");
        assert_eq!(w.team(slot).unwrap(),(slot%2) as u8+1);
    }
    assert!(!w.is_bot(0)&&w.is_bot(5));
    assert!(w.fill_bots().is_err(),"one fill per battle");
    // Too few natives: refused and unchanged.
    let mut short=fixture(2,6,3,now);short.actors.pop();let snapshot=short.actors.clone();
    assert!(short.fill_bots().is_err());assert_eq!(short.actors,snapshot);
    // A native already holding the first bot id: the bots skip it.
    let mut taken=World::new_for_roster(ID,now,MapId::Prohorovka,4).unwrap();
    taken.enable_lifecycle(lifecycle::Rules::for_map(MapId::Prohorovka).unwrap()).unwrap();
    taken.bind_geometry(Arc::new(geometry::tests::bundle())).unwrap();
    taken.terrain=Some(Arc::new(terrain::tests::fixture_for_map(MapId::Prohorovka)));
    taken.enable_bots(Plan{human_places:1,seed:0,kinds:vec![VehicleKind::Ms1]}).unwrap();
    let(mut identity,loadout)=super::super::tests::profile13_loadout(VehicleKind::Ms1,0,7);identity.database=DATABASE_BASE;
    taken.attach_owned(identity,1,&loadout).unwrap();taken.fill_bots().unwrap();
    let ids=taken.actors.iter().map(|a|a.identity.database).collect::<Vec<_>>();
    assert_eq!(ids,[DATABASE_BASE,DATABASE_BASE+1,DATABASE_BASE+2,DATABASE_BASE+3]);
}

#[test]
fn bot01_plan_and_enable_are_bounded(){
    let now=Instant::now();
    for plan in [Plan{human_places:0,seed:0,kinds:vec![VehicleKind::Ms1]},Plan{human_places:6,seed:0,kinds:vec![VehicleKind::Ms1]},
        Plan{human_places:1,seed:0,kinds:vec![]},Plan{human_places:1,seed:0,kinds:vec![VehicleKind::Ms1,VehicleKind::Ms1]},
        Plan{human_places:1,seed:0,kinds:vec![VehicleKind::Wt128]}]{assert!(plan.validate(6).is_err(),"{plan:?}");}
    // Kinds must be bound by the template's geometry (here only MS-1).
    let mut w=World::new_for_roster(ID,now,MapId::Prohorovka,6).unwrap();
    w.enable_lifecycle(lifecycle::Rules::for_map(MapId::Prohorovka).unwrap()).unwrap();
    w.bind_geometry(Arc::new(geometry::tests::bundle())).unwrap();
    w.terrain=Some(Arc::new(terrain::tests::fixture_for_map(MapId::Prohorovka)));
    assert!(w.enable_bots(Plan{human_places:1,seed:0,kinds:vec![VehicleKind::Is7]}).is_err());
    assert!(w.bot_plan().is_none()&&w.human_places()==6,"refused plan leaves the old path");
}

#[test]
fn bot01_commands_take_the_players_apply_path_and_its_refusals(){
    let now=Instant::now();let mut w=fixture(1,4,5,now);w.fill_bots().unwrap();
    place(&mut w,0,[0.,0.,-400.],0.);for slot in 1..4{place(&mut w,slot,[slot as f32*30.,0.,400.],0.);}
    w.start(now).unwrap();w.set_ready(0,1).unwrap();w.ready_bots().unwrap();
    // Countdown: the lifecycle forbids actions; bots issue nothing.
    w.advance_lifecycle(now).unwrap();assert_eq!(w.drive_bots(now).unwrap(),0);
    let fire=[Command::Fire(fire::Command::Shoot)];
    assert_eq!(w.apply(1,SESSION_BASE+1,&fire,now).unwrap(),vec![fire::Outcome::RejectedBattlePeriod],"same gate as a native shot");
    let at=begin_from(&mut w,now);
    // Ownership: a native session cannot drive a bot, a bot session cannot drive a native.
    let go=[Command::Move(Input{throttle:1,steer:0,speed_percent:100})];
    assert!(w.apply(1,1,&go,at).is_err());assert!(w.apply(0,SESSION_BASE+1,&go,at).is_err());
    assert!(w.apply(1,SESSION_BASE+2,&go,at).is_err());
    assert!(w.apply(1,SESSION_BASE+1,&[Command::Move(Input{throttle:2,steer:0,speed_percent:100})],at).is_err(),"same Input validation");
    // A shot through the bot session spends the bot's own ammo and reload, exactly once.
    let ammo=w.actors[1].fire.ammo();
    assert!(matches!(w.apply(1,SESSION_BASE+1,&fire,at).unwrap()[0],fire::Outcome::AcceptedShot{..}));
    assert_eq!(w.actors[1].fire.ammo(),ammo-1);
    assert!(!matches!(w.apply(1,SESSION_BASE+1,&fire,at).unwrap()[0],fire::Outcome::AcceptedShot{..}),"reload refuses a second shot");
    assert_eq!(w.shots.last().unwrap().slot,1);
    // drive_bots: one decision per domain tick, through apply.
    let next=at+STEP;let issued=w.drive_bots(next).unwrap();assert!(issued>0);
    assert_eq!(w.drive_bots(next).unwrap(),0,"same tick: no second decision");
    // A dead bot is skipped (apply would ignore it anyway).
    let before=w.bot_digest();w.actors[2].health=0;w.actors[3].health=0;w.actors[1].health=0;
    w.advance(next+STEP).unwrap();assert_eq!(w.drive_bots(next+STEP).unwrap(),0);assert_eq!(w.bot_digest(),before);
}
fn begin_from(w:&mut World,now:Instant)->Instant{
    let mut at=now;for _ in 0..10{at+=STEP;w.advance_lifecycle(at).unwrap();w.advance(at).unwrap();}
    assert!(w.lifecycle.as_ref().unwrap().allows_actions());at
}

fn wall_at(z:f32)->Arc<terrain::Terrain>{
    let a=[[-200.,-150.,z],[200.,-150.,z],[200.,150.,z]];let b=[[-200.,-150.,z],[200.,150.,z],[-200.,150.,z]];
    Arc::new(terrain::tests::fixture_for_map(MapId::Karelia).with_obstacles(Arc::new(obstacles::tests::fixture(vec![a,b]))).unwrap())
}
fn duel(now:Instant,wall:bool)->World{
    // One native (team 1) 150 m ahead of one bot (team 2) that faces it.
    let mut w=fixture_on(MapId::Karelia,1,2,9,now);w.fill_bots().unwrap();
    if wall{w.terrain=Some(wall_at(75.));}
    place(&mut w,0,[0.,0.,150.],0.);place(&mut w,1,[0.,0.,0.],0.);w
}

#[test]
fn bot01_targets_only_what_its_team_is_shown(){
    let now=Instant::now();
    let mut hidden=duel(now,true);let at=begin(&mut hidden,now);
    for k in 1..=5{tick(&mut hidden,at+STEP*k);}
    assert!(!hidden.desired_visibility(1).unwrap()[0],"wall: the enemy is not spotted");
    assert!(matches!(hidden.actors[1].aim.intent,aim::Intent::Hold{..}),"no aim through a wall");
    assert_ne!(hidden.actors[1].input,Input::STOP,"keeps its route");
    assert!(hidden.shots.is_empty());
    let mut open=duel(now,false);let at=begin(&mut open,now);
    for k in 1..=5{tick(&mut open,at+STEP*k);}
    assert!(open.desired_visibility(1).unwrap()[0]);
    assert_eq!(open.actors[1].input,Input::STOP,"hold on contact");
    let aim::Intent::Point(p)=open.actors[1].aim.intent else{panic!("aims at the spotted enemy")};
    assert!((p[0]-0.).abs()<5.&&(p[2]-150.).abs()<5.&&p[1]>0.,"{p:?}");
}

#[test]
fn bot01_team_shown_target_behind_a_wall_does_not_park_the_bot(){
    // Bot 1 (team 2) is behind a wall; its ally bot 3 sees the native from the side.
    let now=Instant::now();let mut w=fixture_on(MapId::Karelia,1,4,9,now);w.fill_bots().unwrap();
    w.terrain=Some(wall_at(75.));
    place(&mut w,0,[0.,0.,150.],0.);place(&mut w,1,[0.,0.,0.],0.);
    place(&mut w,2,[-400.,0.,-400.],0.);place(&mut w,3,[80.,0.,150.],0.);
    let at=begin(&mut w,now);
    for k in 1..=5{tick(&mut w,at+STEP*k);}
    assert!(w.desired_visibility(1).unwrap()[0],"the team shows the native");
    assert!(matches!(w.actors[1].aim.intent,aim::Intent::Point(_)),"turret on the shown target");
    assert_eq!(w.actors[1].input,Input::STOP,"first waits for a line");
    for k in 6..=30{tick(&mut w,at+STEP*k);}
    assert_ne!(w.actors[1].input,Input::STOP,"no own line for 2 s: advances along its route");
    assert!(matches!(w.actors[1].aim.intent,aim::Intent::Point(_)));
    assert!(w.shots.iter().all(|s|s.slot!=1),"never fires into the wall");
}

#[test]
fn bot01_fires_only_after_aim_time_and_reload(){
    let now=Instant::now();let mut w=duel(now,false);let at=begin(&mut w,now);
    let tau=VehicleKind::Ms1.aim().aiming_time;
    let mut first=None;let mut shots=Vec::new();
    for k in 1..=200u32{
        let before=w.shots.len();tick(&mut w,at+STEP*k);
        if w.shots.len()>before{shots.push(k);first.get_or_insert(k);}
    }
    let first=first.expect("the bot eventually fires at a visible, aimed target");
    assert!(first as f32*0.1>=tau,"no shot before the aiming time: tick {first}");
    assert!(shots.windows(2).all(|p|(p[1]-p[0]) as f32*0.1>=VehicleKind::Ms1.reload_seconds()-0.05),"{shots:?}");
    assert!(w.shots.iter().all(|s|s.slot==1));assert_eq!(w.bot_shots() as usize,w.shots.len());
}

#[test]
fn bot01_routes_and_recovery_stay_inside_the_playable_area(){
    let now=Instant::now();
    for map in [MapId::Karelia,MapId::Prohorovka,MapId::all().find(|m|m.asset()=="02_malinovka").unwrap()]{
        let b=playable_bounds(map.asset()).unwrap();let inner=[b[0]+BOUNDS_INSET_M,b[1]+BOUNDS_INSET_M,b[2]-BOUNDS_INSET_M,b[3]-BOUNDS_INSET_M];
        for seed in 0..16{
            let mut w=fixture_on(map,1,30,seed,now);w.fill_bots().unwrap();
            for brain in &w.bots.as_ref().unwrap().brains{
                assert!(brain.route.iter().all(|p|inside(*p,inner)),"{} {seed} {:?}",map.asset(),brain.route);
                let enemy=map.spec().ctf_bases.unwrap()[2-usize::from(w.team(brain.slot).unwrap())];
                assert!(distance(*brain.route.last().unwrap(),enemy)<=25.5,"route ends at the enemy base");
            }
        }
    }
    // Outside the inset: head back to the centre, turning in place first.
    let mut w=fixture(1,2,1,now);w.fill_bots().unwrap();
    place(&mut w,0,[0.,0.,-300.],0.);place(&mut w,1,[480.,0.,0.],0.);
    let at=begin(&mut w,now);tick(&mut w,at+STEP);
    assert_eq!(w.actors[1].input,Input{throttle:0,steer:-1,speed_percent:100});
}

#[test]
fn bot01_replay_is_deterministic_and_seed_sensitive(){
    let now=Instant::now();
    let run=|seed:u64|{
        let mut w=fixture(1,6,seed,now);w.fill_bots().unwrap();
        place(&mut w,0,[0.,0.,0.],0.);
        for slot in 1..6{place(&mut w,slot,[(slot as f32-3.)*20.,0.,if slot%2==0{-300.}else{300.}],0.);}
        let at=begin(&mut w,now);let mut issued=0;
        for k in 1..=300u32{issued+=tick(&mut w,at+STEP*k);}
        (w.bot_digest().unwrap(),issued,w.actors.iter().map(|a|(a.position,a.yaw,a.input,a.aim.intent)).collect::<Vec<_>>(),w.shots.len())
    };
    let a=run(11);let b=run(11);
    assert_eq!(a,b,"same seed, same battle: same command journal and state");
    assert!(a.1>0);
    assert_ne!(run(12).0,a.0,"another seed changes decisions");
}

#[test]
fn bot01_mixed_ammo_bot_has_a_stock_lab_loadout_and_shoots_through_the_typed_ledger(){
    let now=Instant::now();let map=MapId::Prohorovka;
    let mut w=World::new_for_roster(ID,now,map,2).unwrap();
    let mut rules=lifecycle::Rules::for_map(map).unwrap();rules.prebattle_ms=1000;w.enable_lifecycle(rules).unwrap();
    w.bind_geometry(Arc::new(geometry::tests::bundle())).unwrap();
    w.terrain=Some(Arc::new(terrain::tests::fixture_for_map(map)));
    w.enable_mixed_ammo().unwrap();
    for slot in 0..2{
        let identity=Identity{account:format!("bot01:{slot}"),database:DATABASE_BASE+slot as i32,name:format!("Bot-{:02}",slot+1)};
        assert_eq!(w.attach_bot_actor(identity,SESSION_BASE+slot as u32,VehicleKind::Ms1).unwrap(),slot);
        w.actors[slot].bot=Some(slot as u8);
    }
    let source=crate::p06t_shells091::profile(VehicleKind::Ms1.mount());
    let typed=w.actors[0].fire.typed().expect("typed ledger");
    assert_eq!(typed.counts(),[source.capacity,0,0]);assert_eq!(typed.current(),source.shots[0]);
    assert!(w.actors[0].devices.is_some()&&w.actors[0].owned_v2.is_none(),"devices as a player, no owned admission");
    assert!(w.mixed_ammo(),"world mode restored");
    place(&mut w,0,[0.,0.,0.],0.);place(&mut w,1,[0.,0.,200.],std::f32::consts::PI);
    w.start(now).unwrap();w.actors[0].ready=true;w.actors[1].ready=true;w.advance_lifecycle(now).unwrap();
    let at=begin_from(&mut w,now);
    let outcomes=w.apply(0,SESSION_BASE,&[Command::Fire(fire::Command::Shoot)],at).unwrap();
    assert!(matches!(outcomes[0],fire::Outcome::Typed(crate::p06t_armament091::Outcome::Shot{..})),"{outcomes:?}");
    assert_eq!(w.actors[0].fire.typed().unwrap().counts()[0],source.capacity-1);
    // The bot never gained an owned terminal: writers have nothing to read.
    assert!(w.terminal_state_json(0).is_err());
}

/// Natural results: bots are ordinary roster rows of the natives' result
/// (exactly what the client shows). <= 6 places builds; more is the existing
/// results/Domain roster bound (RES-30), refused rather than truncated.
fn finished(places:usize,now:Instant)->World{
    let map=MapId::Prohorovka;
    let mut w=prepared(map,2,places,4,now);
    let mut rules=lifecycle::Rules::for_map(map).unwrap();rules.prebattle_ms=1000;rules.battle_ms=1000;
    w.lifecycle=None;w.enable_lifecycle(rules).unwrap();
    for slot in 0..2{let(identity,loadout)=super::super::tests::profile13_loadout(VehicleKind::Ms1,slot,7);w.attach_owned(identity,slot as u32+1,&loadout).unwrap();}
    w.fill_bots().unwrap();
    for slot in 0..places{place(&mut w,slot,[slot as f32*15.-40.,0.,if slot%2==0{-200.}else{200.}],0.);}
    let mut at=begin(&mut w,now);w.lifecycle_created_unix=Some(1_800_000_000);
    for _ in 0..40{at+=STEP;tick(&mut w,at);if w.lifecycle.as_ref().unwrap().outcome().is_some(){break;}}
    assert!(w.lifecycle.as_ref().unwrap().outcome().is_some());w
}
#[test]
fn bot01_results_keep_natives_exact_and_mark_no_bot_as_departed(){
    let now=Instant::now();let w=finished(6,now);
    let r=super::super::super::lifecycle_result::build(&w).unwrap();
    assert_eq!(r.participants.len(),6);
    for (slot,p) in r.participants.iter().enumerate(){
        assert_eq!(p.account_dbid,w.actors[slot].identity.database);assert!(!p.premature_leave);
        assert_eq!(u32::from(p.shots),w.actors[slot].fire.accepted_shots());
    }
    assert_eq!(r.participants[0].account_dbid,1);assert!(r.participants[2..].iter().all(|p|p.account_dbid>=DATABASE_BASE&&p.name.starts_with("Bot-")));
    // 30 places: the results bound of today's writers refuses (RES-30), no partial row set.
    let big=finished(30,now);assert!(super::super::super::lifecycle_result::build(&big).is_err());
}

/// BATTLE-ANY: a generated kind of the battle profiles seats a bot as a
/// player's owned generated kind (typed gun, v1 devices) and shoots through
/// the typed ledger; without mixed ammo generated bot kinds are refused.
#[test]
fn bot01_generated_kind_bot_seats_typed_and_shoots(){
    let root=std::path::PathBuf::from(std::env::var_os("WOT091_ROOT").unwrap_or_else(||"D:/WoT_9.1_Server".into()));
    let kv3=VehicleKind::from_owned_label("ussr-KV-3").unwrap();assert!(kv3.is_generated());
    let bundle=Arc::new(geometry::Bundle::load(&root.join("local"),
        &root.join("local/evidence/20261028-battleany-pilot-sources02/bundles/ussr-KV-3.json")).unwrap());
    let now=Instant::now();let map=MapId::Prohorovka;
    let world=|mixed:bool|{
        let mut w=World::new_for_roster(ID,now,map,3).unwrap();
        let mut rules=lifecycle::Rules::for_map(map).unwrap();rules.prebattle_ms=1000;w.enable_lifecycle(rules).unwrap();
        w.bind_geometry(Arc::new(geometry::tests::bundle())).unwrap();w.bind_geometry(bundle.clone()).unwrap();
        w.terrain=Some(Arc::new(terrain::tests::fixture_for_map(map)));
        if mixed{w.enable_mixed_ammo().unwrap();}w
    };
    let plan=Plan{human_places:1,seed:0,kinds:vec![kv3]};
    assert!(world(false).enable_bots(plan.clone()).is_err(),"generated bots need the typed (mixed-ammo) battle");
    let mut w=world(true);w.enable_bots(plan).unwrap();
    // The native place: seated by the same server path (test stand-in for an owned player).
    let human=Identity{account:"bot01-native".into(),database:1,name:"native".into()};
    assert_eq!(w.attach_bot_actor(human,1,VehicleKind::Ms1).unwrap(),0);
    assert_eq!(w.fill_bots().unwrap(),2);
    let source=crate::p06t_shells091::profile(kv3.mount());
    for slot in 1..3{
        let a=&w.actors[slot];
        assert_eq!(a.vehicle_kind(),kv3);assert_eq!(a.health,kv3.max_health());
        let typed=a.fire.typed().expect("typed gun");
        assert_eq!((typed.mount(),typed.counts()),(kv3.mount(),[source.capacity,0,0]));
        let devices=a.devices.as_ref().unwrap();
        assert_eq!((devices.policy_version(),devices.profile()),(crate::p06t_device_state::PolicyVersion::V1,crate::p06t_device_caps::Profile::for_owned(kv3).unwrap()));
        assert!(a.owned_v2.is_none(),"no owned admission");
    }
    place(&mut w,0,[0.,0.,-200.],0.);place(&mut w,1,[0.,0.,200.],std::f32::consts::PI);place(&mut w,2,[60.,0.,200.],std::f32::consts::PI);
    w.start(now).unwrap();w.actors[0].ready=true;w.ready_bots().unwrap();w.advance_lifecycle(now).unwrap();
    let at=begin_from(&mut w,now);
    let outcomes=w.apply(1,SESSION_BASE+1,&[Command::Fire(fire::Command::Shoot)],at).unwrap();
    assert!(matches!(outcomes[0],fire::Outcome::Typed(crate::p06t_armament091::Outcome::Shot{..})),"{outcomes:?}");
    assert_eq!(w.actors[1].fire.typed().unwrap().counts()[0],source.capacity-1);
}

fn wall_box(half:f32,z:f32)->Arc<terrain::Terrain>{
    let a=[[-half,-150.,z],[half,-150.,z],[half,150.,z]];let b=[[-half,-150.,z],[half,150.,z],[-half,150.,z]];
    Arc::new(terrain::tests::fixture_for_map(MapId::Karelia).with_obstacles(Arc::new(obstacles::tests::fixture(vec![a,b]))).unwrap())
}
/// Test motion for one vehicle (the LAB kinematics keep a body within 2 m of
/// its origin): 8 m/s forward/back, 0.8 rad/s turn; `free=false` holds it in place.
fn sim(w:&mut World,slot:usize,free:bool){
    let a=&mut w.actors[slot];let dt=0.1;
    a.yaw=aim::wrap(a.yaw+a.input.steer as f32*0.8*dt);a.direction=[a.yaw,0.,0.];
    if free{let v=8.*a.input.throttle as f32;a.position[0]+=a.yaw.sin()*v*dt;a.position[2]+=a.yaw.cos()*v*dt;a.speed=v;}else{a.speed=0.;}
    a.origin=a.position;
}
/// One native far away (never visible), one bot driving to a single waypoint.
fn driver(now:Instant,goal:[f32;2])->World{
    let mut w=fixture_on(MapId::Karelia,1,2,9,now);w.fill_bots().unwrap();
    place(&mut w,0,[-400.,0.,-400.],0.);place(&mut w,1,[0.,0.,0.],0.);
    let brain=&mut w.bots.as_mut().unwrap().brains[0];brain.route=vec![goal];brain.waypoint=0;w
}
/// Drive up to `ticks`; returns the x where the bot crossed z=line, if it did.
fn drive(w:&mut World,at:Instant,ticks:u32,line:f32)->Option<f32>{
    let mut crossed=None;
    for k in 1..=ticks{
        let last=w.actors[1].position;tick(w,at+STEP*k);sim(w,1,true);let p=w.actors[1].position;
        if (last[2]-line)*(p[2]-line)<=0.&&last[2]!=p[2]{crossed=Some(0.5*(last[0]+p[0]));}
    }
    crossed
}

#[test]
fn bot01_steers_around_an_obstacle_instead_of_into_it(){
    let now=Instant::now();
    // Control: no obstacle, the bot drives straight across x=0.
    let mut open=driver(now,[0.,120.]);let at=begin(&mut open,now);
    let x=drive(&mut open,at,300,30.).expect("crosses z=30");
    assert!(x.abs()<2.,"straight without obstacles: x={x}");
    assert!(open.actors[1].position[2]>95.,"reaches the goal: {:?}",open.actors[1].position);
    // A 30 m wall across the path at z=30 (the test motion would drive through it).
    let mut w=driver(now,[0.,120.]);w.terrain=Some(wall_box(15.,30.));let at=begin(&mut w,now);
    let x=drive(&mut w,at,400,30.).expect("passes the wall line");
    assert!(x.abs()>15.+PROBE_HALF_WIDTH_M,"goes around the wall, not through it: x={x}");
    assert!(w.actors[1].position[2]>95.,"and still reaches its goal: {:?}",w.actors[1].position);
}

#[test]
fn bot01_stuck_reverses_to_a_side_detour_and_gives_up_the_spot_on_the_third_time(){
    let now=Instant::now();let mut w=driver(now,[0.,300.]);
    w.bots.as_mut().unwrap().brains[0].route=vec![[0.,300.],[200.,300.]];
    let at=begin(&mut w,now);
    // Held in place by something the probes cannot see: it only turns.
    let mut events=Vec::new();let mut seen=None;
    for _ in 0..3000{
        w.tick+=1;w.drive_bots(at).unwrap();sim(&mut w,1,false);
        let b=w.bots.as_ref().unwrap().brains[0].clone();
        let key=b.stuck_spot.map(|(_,n)|n);
        if b.unstick==UNSTICK_TICKS-1&&key!=seen{seen=key;events.push((key,b.side,b.detour,b.waypoint,w.actors[1].input));}
        if b.waypoint==1{events.push((None,b.side,b.detour,1,w.actors[1].input));break;}
    }
    assert!(events.len()>=3,"{events:?}");
    let (n,side,detour,_,input)=events[0];
    assert_eq!(n,Some(1));assert!(input.throttle<0,"backs out");
    let (point,_)=detour.expect("a side point after the reversal");
    assert!((distance(point,[0.,0.])-DETOUR_M).abs()<0.5&&point[0].abs()>20.,"off the blocked bearing: {point:?}");
    assert_eq!((events[1].0,events[1].1),(Some(2),-side),"second time at the spot: the other side");
    assert_eq!(events.last().unwrap().3,1,"third time: this waypoint is given up");
}

#[test]
fn bot01_lead_point_follows_flight_time(){
    let p=lead_point([0.;3],[0.,0.,200.],[10.,0.,0.],353.6);
    let t=(200f32.powi(2)+p[0].powi(2)).sqrt()/353.6;
    assert!((p[0]-10.*t).abs()<0.01&&(p[0]-5.66).abs()<0.05&&p[2]==200.,"{p:?}");
    assert_eq!(lead_point([0.;3],[0.,0.,200.],[0.;3],353.6),[0.,0.,200.],"standing target: no lead");
    assert_eq!(lead_point([0.;3],[0.,0.,200.],[10.,0.,0.],0.),[0.,0.,200.],"no flight speed: no lead");
}

#[test]
fn bot01_leads_a_crossing_target(){
    // The native crosses 200 m in front of the bot at 10 m/s; the bot aims ahead of it.
    let now=Instant::now();let mut w=fixture_on(MapId::Karelia,1,2,9,now);w.fill_bots().unwrap();
    place(&mut w,0,[-50.,0.,200.],0.);place(&mut w,1,[0.,0.,0.],0.);
    let at=begin(&mut w,now);
    for k in 1..=100u32{let a=&mut w.actors[0];a.position[0]+=1.;a.origin=a.position;tick(&mut w,at+STEP*k);}
    let brain=&w.bots.as_ref().unwrap().brains[0];
    let (_,_,_,v)=brain.track.expect("tracks the target");
    assert!((v[0]-10.).abs()<0.5&&v[2].abs()<0.5,"velocity estimate {v:?}");
    let aim::Intent::Point(point)=w.actors[1].aim.intent else{panic!("aims")};
    let target=w.actors[0].position;
    let lead=point[0]-target[0];
    let flight=VehicleKind::Ms1.shell().speed();let expected=10.*200.6/flight;
    assert!((lead-expected).abs()<1.5,"aims {lead:.2} m ahead, expected about {expected:.2}");
}
