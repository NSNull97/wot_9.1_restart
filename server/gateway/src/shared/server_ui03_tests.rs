//! UI-03 packet fixtures: feed records reach only a client that asked for them,
//! carry no hidden data and are never repeated. Native UI acceptance is separate.
use super::*;
use super::tests::frame;
use super::ui02_tests::{all_bodies,before_hit,channel_frames,contains,enable,hello,hello_record,hit_world,spotted};
use super::super::battle_events::{self,Channel,FeedCursors,FeedKind,FEED_FEATURE,VERSION};
use crate::p06t_device_caps::Device;
use crate::p06t_device_state as device;

fn feed_record() -> Vec<u8> {
    let mut args=vec![FEED_FEATURE.len() as u8];args.extend(FEED_FEATURE);args.extend(i32::from(VERSION).to_le_bytes());
    let mut raw=vec![0xa1];raw.extend((args.len() as u16).to_le_bytes());raw.extend(args);raw
}
const FROM_START:FeedCursors=FeedCursors{impacts:0,damage:0,ram:0,devices:0,spots:0,capture:0,defence:0};
/// A channel whose feed sees the journals of the fixture as new facts.
fn open(s:&mut Session) {
    let c=s.shared.as_mut().unwrap();
    let mut channel=Channel::new();channel.open_feed();channel.cursors=Some(FROM_START);c.battle_events=Some(channel);
}
#[derive(Debug,PartialEq,Clone,Copy)]
struct Row {kind:u8,value:Option<u16>,vehicle:u32}
fn rows_of(frames:&[Vec<u8>])->Vec<Row> {
    let mut rows=Vec::new();
    for f in frames {
        let (mut at,count)=(6,f[5]);
        for _ in 0..count {
            let (kind,size)=(f[at],usize::from(f[at+1]));let p=&f[at+2..at+2+size];at+=2+size;
            if kind==2 {
                assert_eq!(size,7);
                let value=u16::from_le_bytes([p[1],p[2]]);
                rows.push(Row{kind:p[0],value:(value!=0xffff).then_some(value),vehicle:u32::from_le_bytes([p[3],p[4],p[5],p[6]])});
            }
        }
        assert_eq!(at,f.len());
    }
    rows
}
fn feed(s:&mut Session,w:&mut World,now:Instant)->Vec<Row> {
    poll(s,w,now).unwrap();rows_of(&channel_frames(&all_bodies(s,now)))
}
fn id(slot:usize)->u32 {wire::vehicle_id(slot).unwrap()}
fn impact_hp(w:&World)->u16 {(w.impacts[0].health_before-w.impacts[0].health_after) as u16}
fn transition(sequence:u32,attacker:usize,from_fire:bool,change:device::Change)->device::Transition {
    device::Transition{sequence,at_ms:100,cause:device::Cause{shot:1,attacker_slot:attacker as u8},from_fire,change}
}
fn module(device:Device,after:device::Condition)->device::Change {
    device::Change::Device{device,extra_index:device.extra(),max_health:100,before:100,after:0,
        before_condition:device::Condition::Normal,after_condition:after,repair:false}
}
fn ram(attacker:usize,target:usize,before:i16,after:i16)->model::RamDamageRecord {
    model::RamDamageRecord{sequence:1,tick:1,domain_tick:1000,attacker,target,pair:(0,1),energy_j:1.,closing_speed:1.,health_before:before,health_after:after}
}
fn damage(reason:u8,attacker:usize,target:usize,before:i16,after:i16)->model::DamageRecord {
    model::DamageRecord{sequence:1,tick:1000,attacker,target,shot:1,reason,health_before:before,health_after:after,
        crew_before:true,crew_after:after>0,direct:true,pierced:true}
}
fn mixed(now:Instant)->World {
    let authored=model::tests::world(now);
    let mut w=World::new_for_roster(6963,now,crate::map_profile091::MapId::Karelia,2).unwrap();
    w.enable_mixed_ammo().unwrap();w.actors=authored.actors;
    w.lifecycle=Some(super::super::lifecycle::State::new(super::super::lifecycle::Rules::prohorovka()).unwrap());w
}
/// The publication alone: a mixed world's native path has its own fixtures.
fn publish(s:&mut Session,w:&World,now:Instant)->Vec<Row> {
    let mut lines=Vec::new();let mut outbox=VecDeque::new();
    battle_events_publication::publish(s.shared.as_mut().unwrap(),&mut outbox,w,now,&mut lines).unwrap();
    rows_of(&channel_frames(&outbox.into_iter().collect::<Vec<_>>()))
}

#[test] fn ui03_dealt_shot_names_a_visible_enemy_with_the_committed_hp() {
    let (mut w,now)=hit_world(Instant::now(),0,1);
    let mut s=spotted(now,&w,0);open(&mut s);
    assert!(s.shared.as_ref().unwrap().visible()[1]);
    let hp=impact_hp(&w);assert!(hp>0);
    assert_eq!(feed(&mut s,&mut w,now),vec![Row{kind:FeedKind::ShotDamage as u8,value:Some(hp),vehicle:id(1)}]);
}

#[test] fn ui03_dealt_shot_to_a_hidden_enemy_has_no_name_no_amount_no_hp() {
    let (mut w,now)=hit_world(Instant::now(),0,1);
    w.actors[1].position[0]=500.;let mut s=spotted(now,&w,0);open(&mut s);
    assert!(!s.shared.as_ref().unwrap().visible()[1]);
    poll(&mut s,&mut w,now).unwrap();
    let frames=channel_frames(&all_bodies(&mut s,now));
    assert_eq!(rows_of(&frames),vec![Row{kind:FeedKind::ShotDamage as u8,value:None,vehicle:0}]);
    assert_eq!(frames[0].len(),6+9,"the frame has room for nothing else");
    assert!(!contains(&frames[0],&id(1).to_le_bytes()));
    assert!(!contains(&frames[0],&w.actors[1].health.to_le_bytes()));
    for axis in w.actors[1].position.into_iter().filter(|axis|*axis!=0.) {assert!(!contains(&frames[0],&axis.to_le_bytes()));}
}

#[test] fn ui03_a_lethal_shot_gives_damage_then_kill_and_the_kill_keeps_its_public_id() {
    let (mut w,now)=hit_world(Instant::now(),0,1);
    w.impacts[0].health_after=0;let hp=impact_hp(&w);
    let mut s=spotted(now,&w,0);open(&mut s);
    assert_eq!(rows_of(&channel_frames(&{poll(&mut s,&mut w,now).unwrap();all_bodies(&mut s,now)})),vec![
        Row{kind:FeedKind::ShotDamage as u8,value:Some(hp),vehicle:id(1)},
        Row{kind:FeedKind::Kill as u8,value:None,vehicle:id(1)}]);
}

#[test] fn ui03_a_hit_on_an_ally_or_on_oneself_is_no_effectiveness() {
    // Without lifecycle teams the fixture puts both vehicles on one team.
    let now=Instant::now();let mut w=model::tests::terrain_world(now,1000.);
    w.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).unwrap();
    w.advance(now+model::STEP).unwrap();let now=now+model::STEP;
    assert_eq!(w.team(0).unwrap(),w.team(1).unwrap());
    let mut s=spotted(now,&w,0);open(&mut s);
    assert_eq!(feed(&mut s,&mut w,now),vec![]);
    w.ram_damage_events.push(ram(0,1,50,40));w.device_events.push((1,transition(1,0,false,module(Device::Engine,device::Condition::Destroyed))));
    assert_eq!(feed(&mut s,&mut w,now),vec![]);
}

#[test] fn ui03_the_victim_gets_no_dealt_record_and_a_third_party_gets_nothing() {
    let (mut w,now)=hit_world(Instant::now(),1,0);
    let mut s=spotted(now,&w,0);open(&mut s);
    assert_eq!(feed(&mut s,&mut w,now),vec![],"the hit reaches the victim as HitReceived only");
    let mut third=spotted(now,&w,0);before_hit(&mut third);
    third.shared.as_mut().unwrap().slot=2;open(&mut third);
    let c=third.shared.as_mut().unwrap();
    let rows=publish_or_empty(c,&w,now);assert_eq!(rows,vec![]);
}
fn publish_or_empty(c:&mut Client,w:&World,now:Instant)->Vec<Row> {
    let mut lines=Vec::new();let mut outbox=VecDeque::new();
    battle_events_publication::publish(c,&mut outbox,w,now,&mut lines).unwrap();
    rows_of(&channel_frames(&outbox.into_iter().collect::<Vec<_>>()))
}

#[test] fn ui03_ram_counts_for_both_sides_and_keeps_the_source_rule() {
    let (mut w,now)=hit_world(Instant::now(),1,0);
    let mut s=spotted(now,&w,0);open(&mut s);
    w.ram_damage_events.push(ram(0,1,300,0));w.ram_damage_events.push(ram(1,0,200,170));
    assert_eq!(feed(&mut s,&mut w,now),vec![
        Row{kind:FeedKind::RamDamage as u8,value:Some(300),vehicle:id(1)},
        Row{kind:FeedKind::Kill as u8,value:None,vehicle:id(1)},
        Row{kind:FeedKind::RamReceived as u8,value:Some(30),vehicle:id(1)}]);
    let (mut w,now)=hit_world(now,1,0);
    w.actors[1].position[0]=500.;let mut s=spotted(now,&w,0);open(&mut s);
    w.ram_damage_events.push(ram(1,0,200,170));w.ram_damage_events.push(ram(0,1,300,290));
    assert_eq!(feed(&mut s,&mut w,now),vec![
        Row{kind:FeedKind::RamReceived as u8,value:Some(30),vehicle:0},
        Row{kind:FeedKind::RamDamage as u8,value:None,vehicle:0}]);
}

#[test] fn ui03_modules_of_a_visible_enemy_are_named_a_hidden_ones_are_silent() {
    let (mut w,now)=hit_world(Instant::now(),1,0);
    let visible=spotted(now,&w,0);
    let (mut hidden_world,_)=(w.clone(),());hidden_world.actors[1].position[0]=500.;
    let mut hidden=spotted(now,&hidden_world,0);
    let events=[
        (1,transition(1,0,false,module(Device::LeftTrack,device::Condition::Destroyed))),
        (1,transition(2,0,false,module(Device::RightTrack,device::Condition::Critical))),
        (1,transition(3,0,false,module(Device::Engine,device::Condition::Destroyed))),
        (1,transition(4,0,false,device::Change::Crew{seat:0,extra_index:9,before_active:true,after_active:false})),
        (1,transition(5,0,false,device::Change::Fire{before_active:false,after_active:true})),
        // Not the recipient's doing, or no fresh loss: nothing.
        (1,transition(6,1,false,module(Device::Gun,device::Condition::Destroyed))),
        (1,transition(7,0,true,module(Device::Gun,device::Condition::Destroyed))),
        (1,transition(8,0,false,device::Change::Fire{before_active:true,after_active:false})),
    ];
    for row in events {w.device_events.push(row);}
    let mut s=visible;open(&mut s);
    let rows=feed(&mut s,&mut w,now);
    let kinds=rows.iter().map(|row|row.kind).collect::<Vec<_>>();
    assert_eq!(kinds,[FeedKind::TrackDown,FeedKind::Critical,FeedKind::Critical,FeedKind::Critical,FeedKind::Ignition].map(|k|k as u8).to_vec());
    assert!(rows.iter().all(|row|row.value.is_none()&&row.vehicle==id(1)));
    open(&mut hidden);let mut w=w.clone();w.actors[1].position[0]=500.;
    assert_eq!(feed(&mut hidden,&mut w,now),vec![],"no module fact of a hidden vehicle");
}

#[test] fn ui03_own_fire_loss_is_a_fact_without_a_source() {
    let (mut w,now)=hit_world(Instant::now(),1,0);
    let mut s=spotted(now,&w,0);open(&mut s);
    w.device_events.push((0,transition(1,1,true,module(Device::Radio,device::Condition::Critical))));
    w.device_events.push((0,transition(2,1,false,module(Device::Radio,device::Condition::Destroyed))));
    assert_eq!(feed(&mut s,&mut w,now),vec![Row{kind:FeedKind::FireCritical as u8,value:None,vehicle:0}]);
}

#[test] fn ui03_mixed_journal_counts_splash_fire_and_a_lethal_crew_loss() {
    let now=Instant::now();let (terrain,now)=hit_world(now,0,1);
    let mut s=spotted(now,&terrain,0);open(&mut s);
    let mut w=mixed(now);
    let mut splash=damage(0,0,1,500,450);splash.direct=false;w.damage_events.push(splash);
    w.damage_events.push(damage(1,0,1,450,440));
    w.damage_events.push(damage(1,1,0,300,290));
    let mut crew=damage(0,0,1,440,440);crew.crew_after=false;w.damage_events.push(crew);
    assert_eq!(publish(&mut s,&w,now),vec![
        Row{kind:FeedKind::ShotDamage as u8,value:Some(50),vehicle:id(1)},
        Row{kind:FeedKind::FireDamage as u8,value:Some(10),vehicle:id(1)},
        Row{kind:FeedKind::FireReceived as u8,value:Some(10),vehicle:id(1)},
        Row{kind:FeedKind::Kill as u8,value:None,vehicle:id(1)}]);
}

#[test] fn ui03_fire_on_a_hidden_enemy_is_silent_and_own_fire_keeps_the_source_rule() {
    let now=Instant::now();let (mut terrain,now)=hit_world(now,0,1);terrain.actors[1].position[0]=500.;
    let mut s=spotted(now,&terrain,0);open(&mut s);
    let mut w=mixed(now);
    w.damage_events.push(damage(1,0,1,450,440));w.damage_events.push(damage(1,1,0,300,290));
    assert_eq!(publish(&mut s,&w,now),vec![Row{kind:FeedKind::FireReceived as u8,value:Some(10),vehicle:0}]);
}

#[test] fn ui03_spot_credit_reaches_only_its_observer_without_a_name() {
    let (mut w,now)=hit_world(Instant::now(),1,0);
    let mut s=spotted(now,&w,0);open(&mut s);
    w.push_test_spot(0,1,1000);
    let frames={poll(&mut s,&mut w,now).unwrap();channel_frames(&all_bodies(&mut s,now))};
    assert_eq!(rows_of(&frames),vec![Row{kind:FeedKind::Spotted as u8,value:None,vehicle:0}]);
    let mut other=spotted(now,&w,1);open(&mut other);
    other.shared.as_mut().unwrap().battle_events.as_mut().unwrap().cursors=Some(FeedCursors{impacts:w.impacts.len(),..FROM_START});
    let mut w2=w.clone();
    assert_eq!(feed(&mut other,&mut w2,now),vec![]);
}

fn battle_members(position:[f32;3])->[super::super::lifecycle::Member;2] {
    std::array::from_fn(|i|super::super::lifecycle::Member{team:i as u8+1,present:true,ready:true,alive:true,
        position:if i==0 {position} else {[500.,0.,500.]},damage_epoch:0,last_damager:None})
}
#[test] fn ui03_capture_points_are_the_recipient_delta_and_defence_is_its_own_credit() {
    let (mut w,now)=hit_world(Instant::now(),1,0);
    let mut s=spotted(now,&w,0);open(&mut s);
    let rules=super::super::lifecycle::Rules{prebattle_ms:1_000,..super::super::lifecycle::Rules::prohorovka()};
    let mut state=super::super::lifecycle::State::new(rules.clone()).unwrap();
    let enemy_base=[rules.bases[1].xz[0],0.,rules.bases[1].xz[1]];
    state.advance(0,&battle_members(enemy_base)).unwrap();state.advance(1_000,&battle_members(enemy_base)).unwrap();
    for t in 2..=4 {state.advance(t*1_000,&battle_members(enemy_base)).unwrap();}
    assert_eq!(state.capture_points(0),3);
    w.lifecycle=Some(state);
    assert_eq!(feed(&mut s,&mut w,now),vec![Row{kind:FeedKind::CapturePoints as u8,value:Some(3),vehicle:0}]);
    assert_eq!(feed(&mut s,&mut w,now),vec![],"the same points are not told twice");
    let mut advanced=w.lifecycle.clone().unwrap();
    advanced.advance(5_000,&battle_members(enemy_base)).unwrap();w.lifecycle=Some(advanced);
    assert_eq!(feed(&mut s,&mut w,now),vec![Row{kind:FeedKind::CapturePoints as u8,value:Some(1),vehicle:0}]);
    let mut other=spotted(now,&w,1);open(&mut other);other.shared.as_mut().unwrap().battle_events.as_mut().unwrap().cursors=Some(FeedCursors{impacts:w.impacts.len(),..FROM_START});
    assert_eq!(feed(&mut other,&mut w,now),vec![],"another vehicle's points stay its own");
    let mut defender=spotted(now,&w,0);open(&mut defender);
    defender.shared.as_mut().unwrap().battle_events.as_mut().unwrap().cursors=Some(FeedCursors{capture:4,..FROM_START});
    assert_eq!(feed(&mut defender,&mut w,now),vec![]);
}

#[test] fn ui03_feed_hello_of_a_gateway_without_the_key_stays_on_the_old_path() {
    let (mut w,now)=hit_world(Instant::now(),0,1);
    let mut s=spotted(now,&w,0);enable(&mut s);
    hello(&mut s,now);s.receive(&frame(&s,&feed_record()),now).unwrap();
    assert!(!s.shared.as_ref().unwrap().battle_events.as_ref().unwrap().feed(),"no `feed` key: the record is the old unsupported one");
    assert_eq!(feed(&mut s,&mut w,now),vec![]);
}

#[test] fn ui03_a_channel_without_the_feed_hello_carries_no_feed_byte() {
    let (mut w,now)=hit_world(Instant::now(),0,1);
    let mut plain=spotted(now,&w,0);enable(&mut plain);
    plain.shared.as_mut().unwrap().battle_feed_enabled=true;hello(&mut plain,now);
    let mut world=w.clone();
    let frames={poll(&mut plain,&mut world,now).unwrap();channel_frames(&all_bodies(&mut plain,now))};
    assert_eq!(frames,vec![vec![b'B',b'E',VERSION,0,0,1,0,1,VERSION]],"a UI-02 client on a feed gateway keeps its bytes");
    let mut unprepared=spotted(now,&w,0);enable(&mut unprepared);unprepared.shared.as_mut().unwrap().battle_feed_enabled=true;
    let mut off=spotted(now,&w,0);before_hit(&mut off);before_hit(&mut unprepared);
    let mut world=w.clone();
    poll(&mut off,&mut world,now).unwrap();poll(&mut unprepared,&mut w,now).unwrap();
    assert_eq!(all_bodies(&mut off,now),all_bodies(&mut unprepared,now),"no hello: not one new byte");
}

/// The order of the card: the first pass after the hellos only fixes the
/// cursors, so what happened before the channel opened is history.
#[test] fn ui03_a_channel_opened_late_starts_from_now_and_never_replays() {
    let (mut w,now)=hit_world(Instant::now(),0,1);
    let mut s=spotted(now,&w,0);enable(&mut s);s.shared.as_mut().unwrap().battle_feed_enabled=true;
    let c=s.shared.as_mut().unwrap();c.impact_cursor=w.impacts.len();
    hello(&mut s,now);s.receive(&frame(&s,&feed_record()),now).unwrap();
    assert!(s.shared.as_ref().unwrap().battle_events.as_ref().unwrap().feed());
    assert_eq!(feed(&mut s,&mut w,now),vec![],"the old hit stays history");
    w.ram_damage_events.push(ram(0,1,300,290));
    assert_eq!(feed(&mut s,&mut w,now).len(),1);
    assert_eq!(feed(&mut s,&mut w,now),vec![],"a fact is told once");
}

#[test] fn ui03_a_scene_load_closes_the_channel_so_the_gap_is_not_replayed() {
    let (mut w,now)=hit_world(Instant::now(),0,1);
    let mut s=spotted(now,&w,0);open(&mut s);
    let c=s.shared.as_mut().unwrap();
    c.phase=Phase::Entities;c.creations[c.slot]=Some((0,true));
    let mut ready=vec![0x0d,8,0,0,0,0,0];ready.extend(id(0).to_le_bytes());
    ready.extend([0x8d,5,0,2,1,0,0,0,0x86,0,0]);ready.extend([0x0c,8,0,0,0,0,0,0,0,0,0]);
    s.receive(&frame(&s,&ready),now).unwrap();
    assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Driving);
    assert!(s.shared.as_ref().unwrap().battle_events.is_none(),"the client says hello again");
    assert_eq!(rows_of(&channel_frames(&{poll(&mut s,&mut w,now).unwrap();all_bodies(&mut s,now)})),vec![]);
}

#[test] fn ui03_records_of_one_pass_are_ordered_by_tick_then_journal() {
    let (mut w,now)=hit_world(Instant::now(),1,0);
    let mut s=spotted(now,&w,0);open(&mut s);
    let mut late=ram(0,1,300,290);late.domain_tick=1002;w.ram_damage_events.push(late);
    w.device_events.push((1,device::Transition{at_ms:100,..transition(1,0,false,module(Device::Gun,device::Condition::Critical))}));
    let rows=feed(&mut s,&mut w,now);
    assert_eq!(rows.iter().map(|row|row.kind).collect::<Vec<_>>(),vec![FeedKind::Critical as u8,FeedKind::RamDamage as u8]);
}

#[test] fn ui03_a_splash_on_thirty_vehicles_fits_the_rate_limit() {
    let now=Instant::now();
    let (terrain,now)=hit_world(now,0,1);
    let mut s=spotted(now,&terrain,0);open(&mut s);
    let mut w=mixed(now);
    for _ in 0..30 {let mut row=damage(0,0,1,500,450);row.direct=false;w.damage_events.push(row);}
    let rows=publish(&mut s,&w,now);
    assert_eq!(rows.len(),30);
    assert_eq!(s.shared.as_ref().unwrap().battle_events.as_ref().unwrap().dropped,0);
    assert!(30usize.div_ceil(battle_events::MAX_EVENTS_PER_FRAME)<=usize::from(battle_events::MAX_FRAMES_PER_SECOND));
}

#[test] fn ui03_a_dropped_frame_is_counted_and_not_repeated_later() {
    let (mut w,now)=hit_world(Instant::now(),0,1);
    let mut s=spotted(now,&w,0);open(&mut s);
    for _ in 0..battle_events::MAX_OUTBOX_BACKLOG {s.outbox.push_back(vec![0x13,0x41,0,0,0,0,0]);}
    poll(&mut s,&mut w,now).unwrap();
    assert_eq!(s.shared.as_ref().unwrap().battle_events.as_ref().unwrap().dropped,1);
    all_bodies(&mut s,now);
    assert_eq!(feed(&mut s,&mut w,now+Duration::from_secs(1)),vec![],"the loss is the server's count, the stream goes on");
}

/// Two enemies of slot 2: slots 0 and 2 are one team in this roster.
fn assist_world(now:Instant)->World {
    let mut w=mixed(now);
    let extra=w.actors[1].clone();w.actors.push(extra);w.push_test_team_plan();w
}
fn track(attacker:usize,after:device::Condition,repair:bool,at_ms:u64)->device::Transition {
    let mut row=transition(1,attacker,false,module(Device::LeftTrack,after));row.at_ms=at_ms;
    if let device::Change::Device{repair:flag,..}=&mut row.change {*flag=repair;}row
}
fn ally_shot(tick:u32,before:i16,after:i16)->model::DamageRecord {let mut row=damage(0,2,1,before,after);row.tick=tick;row}
#[test] fn ui03_assist_track_lasts_until_the_repair_and_only_for_its_author() {
    let now=Instant::now();let (terrain,now)=hit_world(now,0,1);
    let mut s=spotted(now,&terrain,0);open(&mut s);
    let mut w=assist_world(now);
    w.device_events.push((1,track(0,device::Condition::Destroyed,false,100)));
    w.damage_events.push(ally_shot(1001,500,400));
    w.device_events.push((1,track(0,device::Condition::Critical,true,300)));
    w.damage_events.push(ally_shot(1003,400,350));
    let rows=publish(&mut s,&w,now);
    assert_eq!(rows,vec![Row{kind:FeedKind::TrackDown as u8,value:None,vehicle:id(1)},
        Row{kind:FeedKind::AssistTrack as u8,value:Some(100),vehicle:id(1)}]);
    let totals=battle_ledger::totals(&w,0).unwrap();
    assert_eq!((totals.assist_track,totals.assist_spot),(100,0));
    assert_eq!(battle_ledger::totals(&w,2).unwrap().assist_track,0,"own damage earns no assist");
}
#[test] fn ui03_assist_spot_has_a_window_and_a_track_takes_priority() {
    let now=Instant::now();let (terrain,now)=hit_world(now,0,1);
    let mut w=assist_world(now);w.push_test_spot(0,1,1000);
    w.damage_events.push(ally_shot(1000+battle_ledger::SPOT_ASSIST_TICKS,500,400));
    w.damage_events.push(ally_shot(1001+battle_ledger::SPOT_ASSIST_TICKS,400,300));
    assert_eq!(battle_ledger::totals(&w,0).unwrap().assist_spot,100,"the window ends");
    w.device_events.push((1,track(0,device::Condition::Destroyed,false,0)));
    let totals=battle_ledger::totals(&w,0).unwrap();
    assert_eq!((totals.assist_spot,totals.assist_track),(0,200),"one harm, one assist");
    let mut s=spotted(now,&terrain,0);open(&mut s);
    let kinds=publish(&mut s,&w,now).iter().map(|row|row.kind).collect::<Vec<_>>();
    assert!(!kinds.contains(&(FeedKind::AssistSpot as u8)));
}
#[test] fn ui03_assist_on_a_hidden_target_keeps_the_sum_for_the_totals_only() {
    let now=Instant::now();let (mut terrain,now)=hit_world(now,0,1);terrain.actors[1].position[0]=500.;
    let mut s=spotted(now,&terrain,0);open(&mut s);
    let mut w=assist_world(now);w.push_test_spot(0,1,1000);w.damage_events.push(ally_shot(1001,500,400));
    let rows=publish(&mut s,&w,now);
    assert_eq!(rows[rows.len()-1],Row{kind:FeedKind::AssistSpot as u8,value:None,vehicle:0});
    assert_eq!(battle_ledger::totals(&w,0).unwrap().assist_spot,100);
}
#[test] fn ui03_burned_hp_belongs_to_the_author_of_the_fire() {
    let now=Instant::now();let (_,now)=hit_world(now,0,1);
    let mut w=assist_world(now);
    w.damage_events.push(damage(1,0,1,500,470));w.damage_events.push(damage(1,0,1,470,440));
    w.damage_events.push(damage(0,0,1,440,400));
    assert_eq!(battle_ledger::totals(&w,0).unwrap().burned,60);
    assert_eq!(battle_ledger::totals(&w,1).unwrap().burned,0);
}
/// Hit of slot 1 on slot 0 with a catalog shell the armor stopped.
fn stopped_world(now:Instant,outcome:ap::Outcome)->(World,Instant) {
    let (mut w,now)=hit_world(now,1,0);
    w.projectiles[0].shell=Some(crate::p06t_shells091::PROFILES[0].shots[1]);
    let before=w.impacts[0].health_before;w.impacts[0].health_after=before;
    if let model::ImpactOutcome::Ap(resolution)=&mut w.impacts[0].outcome {resolution.outcome=outcome;}
    (w,now)
}
#[test] fn ui03_blocked_counts_the_nominal_of_stopped_shells_and_a_hidden_shooter_only_in_the_totals() {
    let (mut w,now)=stopped_world(Instant::now(),ap::Outcome::NotPierced);
    let hp=u32::from(battle_ledger::nominal(&w,w.impacts[0].shot).unwrap());
    let totals=battle_ledger::totals(&w,0).unwrap();
    assert_eq!((totals.blocked,totals.potential_received),(hp,hp));
    let mut s=spotted(now,&w,0);before_hit(&mut s);open(&mut s);
    poll(&mut s,&mut w,now).unwrap();
    let frames=channel_frames(&all_bodies(&mut s,now));
    assert_eq!(&frames[0][8+10..8+12],&(hp as u16).to_le_bytes(),"a visible shooter: the number travels");
    let (mut w,now)=stopped_world(now,ap::Outcome::Ricochet);w.actors[1].position[0]=500.;
    let mut s=spotted(now,&w,0);before_hit(&mut s);open(&mut s);
    assert_eq!(battle_ledger::totals(&w,0).unwrap().blocked,hp);
    poll(&mut s,&mut w,now).unwrap();
    let frames=channel_frames(&all_bodies(&mut s,now));
    assert_eq!(&frames[0][8+10..8+12],&[0xff,0xff],"a hidden shooter: the sum waits for the end of the battle");
}
#[test] fn ui03_a_pierced_shell_is_potential_not_blocked() {
    let (mut w,_)=hit_world(Instant::now(),1,0);
    w.projectiles[0].shell=Some(crate::p06t_shells091::PROFILES[0].shots[1]);
    let totals=battle_ledger::totals(&w,0).unwrap();
    assert_eq!(totals.blocked,0);assert!(totals.potential_received>0);
}
#[test] fn ui03_laboratory_shots_have_no_nominal_so_blocked_stays_absent_not_estimated() {
    let (w,_)=hit_world(Instant::now(),1,0);
    assert_eq!(battle_ledger::nominal(&w,w.impacts[0].shot),None);
    let totals=battle_ledger::totals(&w,0).unwrap();
    assert_eq!((totals.blocked,totals.potential_received),(0,0));
}

#[test] fn ui03_the_hello_version_is_exact() {
    let (_,now)=hit_world(Instant::now(),0,1);
    let (w,_)=hit_world(now,0,1);
    let mut s=spotted(now,&w,0);enable(&mut s);s.shared.as_mut().unwrap().battle_feed_enabled=true;
    let mut raw=feed_record();let at=raw.len()-4;raw[at]=9;
    s.receive(&frame(&s,&raw),now).unwrap();
    assert!(s.shared.as_ref().unwrap().battle_events.is_none());
    s.receive(&frame(&s,&hello_record(i32::from(VERSION))),now).unwrap();
    assert!(!s.shared.as_ref().unwrap().battle_events.as_ref().unwrap().feed());
}
