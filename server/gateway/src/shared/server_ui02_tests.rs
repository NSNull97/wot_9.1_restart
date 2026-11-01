//! UI-02 packet fixtures: the project channel reaches only a prepared client of
//! an enabled gateway and carries no hidden data. Native UI acceptance is separate.
use super::*;
use super::tests::{visible_pair,frame,queued_bodies};
use super::super::battle_events::{self,HELLO_FEATURE,VERSION};
use crate::p06t_device_state as device;

fn request(slots:&[usize])->Vec<u8> {
    let mut raw=Vec::new();for &slot in slots {raw.extend([8,4,0]);raw.extend(wire::vehicle_id(slot).unwrap().to_le_bytes());}raw
}
fn send_and_ack(s:&mut Session,now:Instant)->Vec<Vec<u8>> {
    let mut bodies=Vec::new();let mut cumulative=s.tx.cumulative;
    while let Some((seq,_,raw))=s.tx.due(now,s.rx).unwrap() {
        cumulative=cumulative.max(seq+1);bodies.push(transport091::parse_interactive(&raw).unwrap().body);
    }
    let mut f=frame(s,&[]);f.cumulative=Some(cumulative);s.receive(&f,now).unwrap();bodies
}
fn spotted(now:Instant,w:&World,slot:usize)->Session {
    let(a,b,_)=visible_pair(now);let mut s=if slot==0 {a} else {b};
    let c=s.shared.as_mut().unwrap();c.creations=[None;model::MAX_ACTORS];
    c.phase=Phase::Account;c.enable_spotting().unwrap();c.phase=Phase::Driving;
    s.shared_refresh_world(w).unwrap();s.flush_shared_interest(&mut Vec::new()).unwrap();
    send_and_ack(&mut s,now);
    let slots=(0..w.actors.len()).filter(|&other|w.desired_visibility(slot).unwrap()[other]).collect::<Vec<_>>();
    s.receive(&frame(&s,&request(&slots)),now).unwrap();send_and_ack(&mut s,now);
    assert!(s.shared.as_ref().unwrap().visible()[slot]);s
}
fn lifecycle(w:&mut World){w.lifecycle=Some(super::super::lifecycle::State::new(super::super::lifecycle::Rules::prohorovka()).unwrap());}
fn hello_record(version:i32)->Vec<u8> {
    let mut args=vec![HELLO_FEATURE.len() as u8];args.extend(HELLO_FEATURE);args.extend(version.to_le_bytes());
    let mut raw=vec![0xa1];raw.extend((args.len() as u16).to_le_bytes());raw.extend(args);raw
}
fn hello(s:&mut Session,now:Instant) {s.receive(&frame(s,&hello_record(i32::from(VERSION))),now).unwrap();}
fn enable(s:&mut Session) {s.shared.as_mut().unwrap().battle_events_enabled=true;}
fn all_bodies(s:&mut Session,now:Instant)->Vec<Vec<u8>> {
    let mut bodies=Vec::new();
    for _ in 0..4 {bodies.extend(send_and_ack(s,now));s.flush_shared_private().unwrap();}
    bodies.extend(queued_bodies(s,now));bodies
}
/// Frames of the channel, as the literal of each updateArena(200, ...).
fn channel_frames(bodies:&[Vec<u8>])->Vec<Vec<u8>> {
    let mut rows=Vec::new();
    for raw in bodies {
        let mut at=0;
        while at+5<=raw.len() {
            if raw[at..at+2]==[0x13,0x58]&&raw[at+3]==battle_events::ARENA_UPDATE_TYPE&&raw.get(at+5..at+7)==Some(b"BE") {
                let end=at+5+usize::from(raw[at+4]);rows.push(raw[at+5..end].to_vec());at=end;
            } else {at+=1;}
        }
    }
    rows
}
fn event_frames(bodies:&[Vec<u8>])->Vec<Vec<u8>> {channel_frames(bodies).into_iter().filter(|f|f[6]==1).collect()}
fn contains(raw:&[u8],part:&[u8])->bool {raw.windows(part.len()).any(|v|v==part)}
fn hit_world(now:Instant,attacker:usize,target:usize)->(World,Instant) {
    let mut w=model::tests::terrain_world(now,1000.);
    w.apply(attacker,attacker as u32+1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).unwrap();
    w.advance(now+model::STEP).unwrap();assert_eq!(w.impacts.len(),1);assert_eq!(w.impacts[0].target,target);
    lifecycle(&mut w);(w,now+model::STEP)
}
/// Takes the session past READY at the hit, as a live battle would be.
fn before_hit(s:&mut Session) {s.shared.as_mut().unwrap().impact_cursor=0;}

#[test] fn ui02_hidden_shooter_frame_has_only_recipient_facts() {
    let (mut w,now)=hit_world(Instant::now(),1,0);
    w.actors[1].position[0]=500.;let mut s=spotted(now,&w,0);before_hit(&mut s);enable(&mut s);
    assert!(!s.shared.as_ref().unwrap().visible()[1]);
    hello(&mut s,now);poll(&mut s,&mut w,now).unwrap();
    let frames=event_frames(&all_bodies(&mut s,now));assert_eq!(frames.len(),1);
    let f=&frames[0];
    assert_eq!(&f[..3],&[b'B',b'E',VERSION]);
    let event=&f[8..];
    assert_eq!(&event[0..4],&w.impacts[0].shot.to_le_bytes());
    let hp=(w.impacts[0].health_before-w.impacts[0].health_after) as u16;assert!(hp>0);
    assert_eq!(&event[8..10],&hp.to_le_bytes());
    assert_eq!(&event[10..12],&[0xff,0xff],"blocked is absent");
    assert_eq!(&event[14..18],&[0;4],"a hidden shooter has no ID");
    assert_eq!(event[18],0,"no module or crew fact");
    // A zero coordinate has the same bytes as the empty ID; the field layout
    // above already pins those. Every non-zero value must be absent.
    let hidden=&w.actors[1];
    assert!(!contains(f,&wire::vehicle_id(1).unwrap().to_le_bytes()));
    for axis in hidden.position.into_iter().filter(|axis|*axis!=0.) {assert!(!contains(f,&axis.to_le_bytes()),"hidden position");}
    for origin in w.projectiles[0].origin.into_iter().filter(|axis|*axis!=0.) {assert!(!contains(f,&origin.to_le_bytes()),"muzzle position");}
    assert!(!event[10..].windows(2).any(|v|v==hidden.health.to_le_bytes()),"hidden HP after the own damage field");
    assert_eq!(f.len(),8+19,"the frame has room for nothing else");
}

#[test] fn ui02_visible_enemy_gives_its_id_and_marks_no_friendly_fire() {
    let (mut w,now)=hit_world(Instant::now(),1,0);
    let mut s=spotted(now,&w,0);before_hit(&mut s);enable(&mut s);
    assert!(s.shared.as_ref().unwrap().visible()[1]);
    hello(&mut s,now);poll(&mut s,&mut w,now).unwrap();
    let frames=event_frames(&all_bodies(&mut s,now));assert_eq!(frames.len(),1);
    let event=&frames[0][8..];
    assert_eq!(&event[14..18],&wire::vehicle_id(1).unwrap().to_le_bytes());
    assert_eq!(event[13]&1,0);
}

#[test] fn ui02_friendly_fire_is_flagged_and_keeps_the_source_rule() {
    let now=Instant::now();let mut w=model::tests::terrain_world(now,1000.);
    w.apply(1,2,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).unwrap();
    w.advance(now+model::STEP).unwrap();let now=now+model::STEP;
    assert_eq!(w.team(0).unwrap(),w.team(1).unwrap());
    let mut s=spotted(now,&w,0);before_hit(&mut s);enable(&mut s);hello(&mut s,now);poll(&mut s,&mut w,now).unwrap();
    let frames=event_frames(&all_bodies(&mut s,now));assert_eq!(frames.len(),1);
    let event=&frames[0][8..];assert_eq!(event[13]&1,1);
    assert_eq!(&event[14..18],&wire::vehicle_id(1).unwrap().to_le_bytes());
}

#[test] fn ui02_unprepared_client_receives_the_same_bytes_as_without_the_key() {
    let (w,now)=hit_world(Instant::now(),1,0);
    let mut off=spotted(now,&w,0);before_hit(&mut off);
    let mut on=off.clone();enable(&mut on);
    let (mut world_off,mut world_on)=(w.clone(),w.clone());
    poll(&mut off,&mut world_off,now).unwrap();poll(&mut on,&mut world_on,now).unwrap();
    let (off,on)=(all_bodies(&mut off,now),all_bodies(&mut on,now));
    assert!(!off.is_empty());assert_eq!(off,on,"an enabled gateway adds no byte for an unprepared client");
    assert!(channel_frames(&on).is_empty());
    for raw in &on {assert!(!contains(raw,b"BE\x01"));}
}

#[test] fn ui02_prepared_client_of_a_gateway_without_the_key_stays_on_the_old_path() {
    let (mut w,now)=hit_world(Instant::now(),1,0);
    let mut s=spotted(now,&w,0);before_hit(&mut s);
    let mut plain=s.clone();
    hello(&mut s,now);assert!(s.shared.as_ref().unwrap().battle_events.is_none());
    let mut world=w.clone();poll(&mut s,&mut w,now).unwrap();poll(&mut plain,&mut world,now).unwrap();
    assert!(channel_frames(&all_bodies(&mut s,now)).is_empty());
    assert!(channel_frames(&all_bodies(&mut plain,now)).is_empty());
}

#[test] fn ui02_other_version_or_feature_opens_nothing() {
    let (mut w,now)=hit_world(Instant::now(),1,0);
    let mut s=spotted(now,&w,0);before_hit(&mut s);enable(&mut s);
    s.receive(&frame(&s,&hello_record(i32::from(VERSION)+1)),now).unwrap();
    let mut feature=vec![13];feature.extend(b"server_marker");feature.extend(1i32.to_le_bytes());
    let mut raw=vec![0xa1];raw.extend((feature.len() as u16).to_le_bytes());raw.extend(feature);
    s.receive(&frame(&s,&raw),now).unwrap();
    assert!(s.shared.as_ref().unwrap().battle_events.is_none());
    poll(&mut s,&mut w,now).unwrap();assert!(channel_frames(&all_bodies(&mut s,now)).is_empty());
}

/// Before READY every record is refused: why the client patch sends its hello
/// only after setClientReady, on the same ordered reliable channel.
#[test] fn ui02_hello_before_ready_is_a_strict_reject() {
    let (w,now)=hit_world(Instant::now(),1,0);
    let mut s=spotted(now,&w,0);enable(&mut s);s.shared.as_mut().unwrap().phase=Phase::Entities;
    assert!(s.receive(&frame(&s,&hello_record(1)),now).is_err());
}

#[test] fn ui02_the_channel_is_answered_and_a_battle_reset_closes_it() {
    let (mut w,now)=hit_world(Instant::now(),1,0);
    let mut s=spotted(now,&w,0);enable(&mut s);hello(&mut s,now);
    // READY moves the cursor past everything older (mod.rs): this hit is history.
    s.shared.as_mut().unwrap().impact_cursor=w.impacts.len();
    poll(&mut s,&mut w,now).unwrap();
    let frames=channel_frames(&all_bodies(&mut s,now));
    assert_eq!(frames,vec![vec![b'B',b'E',VERSION,0,0,1,0,1,VERSION]],"hello reply; no replay of old impacts");
    let c=s.shared.as_mut().unwrap();c.reset_for_battle(0);
    assert!(c.battle_events.is_none());assert!(c.battle_events_enabled,"the gateway key survives, the channel does not");
}

#[test] fn ui02_observer_gets_no_event_for_another_vehicle() {
    let (mut w,now)=hit_world(Instant::now(),0,1);
    let mut observer=spotted(now,&w,0);before_hit(&mut observer);enable(&mut observer);hello(&mut observer,now);
    poll(&mut observer,&mut w,now).unwrap();
    assert!(event_frames(&all_bodies(&mut observer,now)).is_empty(),"the shooter is not the recipient of a received hit");
}

#[test] fn ui02_own_criticals_come_with_their_shot_only() {
    let (mut w,now)=hit_world(Instant::now(),1,0);
    let shot=w.impacts[0].shot;
    let cause=device::Cause{shot,attacker_slot:1};
    let transition=|cause,change|device::Transition{sequence:1,at_ms:0,cause,from_fire:false,change};
    w.device_events.push((0,transition(cause,device::Change::Fire{before_active:false,after_active:true})));
    w.device_events.push((0,transition(cause,device::Change::Crew{seat:0,extra_index:9,before_active:true,after_active:false})));
    w.device_events.push((1,transition(cause,device::Change::Fire{before_active:false,after_active:true})));
    w.device_events.push((0,transition(device::Cause{shot:shot+1,attacker_slot:1},device::Change::Fire{before_active:false,after_active:true})));
    let mut s=spotted(now,&w,0);before_hit(&mut s);enable(&mut s);s.shared.as_mut().unwrap().device_cursor=0;
    hello(&mut s,now);poll(&mut s,&mut w,now).unwrap();
    let frames=event_frames(&all_bodies(&mut s,now));
    let event=&frames[0][8..];assert_eq!(&event[18..],&[2,4,0,3,9]);
}

#[test] fn ui02_a_slow_peer_loses_events_and_keeps_the_channel() {
    let (mut w,now)=hit_world(Instant::now(),1,0);
    let mut s=spotted(now,&w,0);enable(&mut s);hello(&mut s,now);
    all_bodies(&mut s,now);
    poll(&mut s,&mut w,now).unwrap();all_bodies(&mut s,now);
    before_hit(&mut s);
    for _ in 0..battle_events::MAX_OUTBOX_BACKLOG {s.outbox.push_back(vec![0x13,0x41,0,0,0,0,0]);}
    poll(&mut s,&mut w,now).unwrap();
    let c=s.shared.as_ref().unwrap();
    assert_eq!(c.battle_events.as_ref().unwrap().dropped,1);
}
