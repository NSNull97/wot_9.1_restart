//! AV-01 packet fixtures: hidden-shooter hit feedback, shot-result voice,
//! engine mode and damage stickers. Native sound/UI acceptance is separate.
use super::*;
use super::tests::{visible_pair,frame,queued_bodies};

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
fn contains(raw:&[u8],part:&[u8])->bool {raw.windows(part.len()).any(|v|v==part)}
fn lifecycle(w:&mut World){w.lifecycle=Some(super::super::lifecycle::State::new(super::super::lifecycle::Rules::prohorovka()).unwrap());}

#[test] fn av01_hidden_attacker_owner_hit_has_indicator_and_fx_without_shooter_id() {
    let now=Instant::now();let mut w=model::tests::terrain_world(now,1000.);
    w.apply(1,2,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).unwrap();
    w.advance(now+model::STEP).unwrap();assert_eq!(w.actors[0].health,60);let now=now+model::STEP;
    lifecycle(&mut w);w.actors[1].position[0]=500.;let mut s=spotted(now,&w,0);
    assert!(!s.shared.as_ref().unwrap().visible()[1]);
    poll(&mut s,&mut w,now).unwrap();let raw=queued_bodies(&s,now).concat();
    let p=w.projectiles[0];
    assert!(contains(&raw,&super::super::av01_feedback::hit_direction(p.velocity,true).unwrap()));
    // showDamageFromShot on the own vehicle, attacker entity 0.
    let mut fx=vec![0x12];fx.extend(wire::vehicle_id(0).unwrap().to_le_bytes());fx.extend([0x42,17,0,0,0,0]);
    assert!(contains(&raw,&fx));
    let hidden=wire::vehicle_id(1).unwrap().to_le_bytes();
    let mut hidden_fx=vec![0x42,17];hidden_fx.extend(hidden);assert!(!contains(&raw,&hidden_fx));
    assert!(!contains(&raw,&[0x13,0x55]));
}

#[test] fn av01_shooter_gets_shot_result_and_target_gets_sticker() {
    let now=Instant::now();let mut w=model::tests::terrain_world(now,1000.);
    w.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).unwrap();
    w.advance(now+model::STEP).unwrap();assert_eq!(w.impacts.len(),1);let now=now+model::STEP;
    lifecycle(&mut w);let mut s=spotted(now,&w,0);
    poll(&mut s,&mut w,now).unwrap();
    let mut raw=Vec::new();for _ in 0..4 {raw.extend(send_and_ack(&mut s,now).concat());s.flush_shared_private().unwrap();}
    raw.extend(queued_bodies(&s,now).concat());
    let e=&w.impacts[0];
    let flags=super::super::av01_feedback::shot_result_flags(impact_visual(e).unwrap().map(|v|v.1),false,e.health_before,e.health_after);
    assert!(contains(&raw,&super::super::av01_feedback::shot_results(&[(1,flags)]).unwrap()));
    let codes=sticker_codes(&w,1).unwrap();assert_eq!(codes.len(),1);
    assert!(contains(&raw,&super::super::av01_feedback::damage_stickers_update(1,&codes).unwrap()));
    assert_eq!(s.shared.as_ref().unwrap().stickers_sent[1].as_deref(),Some(codes.as_slice()));
}

#[test] fn av01_engine_mode_follows_server_input_once_per_change() {
    let now=Instant::now();let mut w=model::tests::terrain_world(now,1000.);lifecycle(&mut w);
    let mut s=spotted(now,&w,0);
    poll(&mut s,&mut w,now).unwrap();let raw=send_and_ack(&mut s,now).concat();
    let idle0=super::super::av01_feedback::engine_mode_update(0,[1,0]).unwrap();
    assert!(contains(&raw,&idle0));assert!(contains(&raw,&super::super::av01_feedback::engine_mode_update(1,[1,0]).unwrap()));
    w.tick+=1;poll(&mut s,&mut w,now).unwrap();assert!(!contains(&send_and_ack(&mut s,now).concat(),&idle0));
    w.actors[0].input=model::Input{throttle:1,steer:0,speed_percent:100};w.tick+=1;
    poll(&mut s,&mut w,now).unwrap();
    assert!(contains(&send_and_ack(&mut s,now).concat(),&super::super::av01_feedback::engine_mode_update(0,[3,1]).unwrap()));
}
