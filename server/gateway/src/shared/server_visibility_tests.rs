//! Packet-level authored fixtures; native AoI/UI remains a separate gate.
use super::*;
use super::tests::{visible_pair,frame,queued_bodies};

fn world(now:Instant)->World {
    let mut w=model::tests::terrain_world(now,1000.);
    w.lifecycle=Some(super::super::lifecycle::State::new(super::super::lifecycle::Rules::prohorovka()).unwrap());
    w
}
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
fn spotted(now:Instant,w:&World)->Session {
    let(mut s,_,_)=visible_pair(now);
    let c=s.shared.as_mut().unwrap();c.creations=[None;model::MAX_ACTORS];
    c.phase=Phase::Account;c.enable_spotting().unwrap();c.phase=Phase::Driving;
    s.shared_refresh_world(w).unwrap();s.flush_shared_interest(&mut Vec::new()).unwrap();
    send_and_ack(&mut s,now);
    let slots=(0..w.actors.len()).filter(|&slot|w.desired_visibility(0).unwrap()[slot]).collect::<Vec<_>>();
    s.receive(&frame(&s,&request(&slots)),now).unwrap();send_and_ack(&mut s,now);
    assert!(s.shared.as_ref().unwrap().visible()[0]);s
}
fn contains(raw:&[u8],part:&[u8])->bool {raw.windows(part.len()).any(|v|v==part)}

#[test] fn p07b_initial_hidden_request_is_consumed_without_create_pose_hp_or_aim() {
    let now=Instant::now();let mut w=world(now);w.actors[1].position[0]=500.;
    let mut s=spotted(now,&w);assert!(!s.shared.as_ref().unwrap().visible()[1]);
    let rx=s.rx;s.receive(&frame(&s,&request(&[1])),now).unwrap();assert_eq!(s.rx,rx+1);
    w.tick+=1;poll(&mut s,&mut w,now).unwrap();
    let raw=queued_bodies(&s,now).concat();
    assert!(!contains(&raw,&wire::create_vehicle(&w,1).unwrap()));
    let mut position=vec![0x15];position.extend(wire::vehicle_id(1).unwrap().to_le_bytes());
    let mut aim=vec![0x12];aim.extend(wire::vehicle_id(1).unwrap().to_le_bytes());aim.push(0xa0);
    assert!(!contains(&raw,&position));assert!(!contains(&raw,&aim));
    assert!(!contains(&raw,&impact_wire::health_changed(1,60,0).unwrap()));
    let mut own=vec![0x15];own.extend(wire::vehicle_id(0).unwrap().to_le_bytes());assert!(contains(&raw,&own));
}

#[test] fn p07b_deferred_private_body_is_purged_before_new_sequence_on_hide() {
    let now=Instant::now();let mut w=world(now);let mut s=spotted(now,&w);
    assert!(s.shared.as_ref().unwrap().visible()[1]);
    for _ in 0..8 {s.tx.enqueue_body(&[13,1]).unwrap();}
    let private=wire::create_vehicle(&w,1).unwrap();
    s.shared.as_mut().unwrap().queue_private(&mut s.outbox,private.clone(),&[1]).unwrap();
    assert_eq!(s.shared.as_ref().unwrap().pending_private_len(),1);
    w.actors[1].position[0]=500.;s.shared_refresh_world(&w).unwrap();
    assert_eq!(s.shared.as_ref().unwrap().pending_private_len(),0);
    send_and_ack(&mut s,now);s.flush_shared_interest(&mut Vec::new()).unwrap();s.flush_shared_private().unwrap();
    assert!(!contains(&queued_bodies(&s,now).concat(),&private));
}

#[test] fn p07b_publication_uses_new_tick_after_authoritative_view_refresh() {
    let now=Instant::now();let mut w=world(now);let mut s=spotted(now,&w);
    w.tick+=1;w.actors[0].position[0]=21.25;s.shared_refresh_world(&w).unwrap();
    poll(&mut s,&mut w,now).unwrap();let bodies=queued_bodies(&s,now).concat();
    assert!(contains(&bodies,&wire::publication(&w,[true,true]).unwrap()));
    assert_eq!(s.shared.as_ref().unwrap().last_pose_tick,Some(w.tick));
}

#[test] fn p07b_visible_launch_cannot_disclose_hidden_vehicle_terminal() {
    let now=Instant::now();let mut w=model::tests::terrain_world(now,1000.);
    w.apply(0,1,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).unwrap();
    w.advance(now+model::STEP).unwrap();assert_eq!(w.impacts.len(),1);let now=now+model::STEP;
    let p=w.projectiles[0];assert!(p.stopped);
    w.lifecycle=Some(super::super::lifecycle::State::new(super::super::lifecycle::Rules::prohorovka()).unwrap());
    let mut s=spotted(now,&w);w.actors[1].position[0]=500.;
    let c=s.shared.as_mut().unwrap();c.shot_cursor=1;c.tracer_started[0]=true;
    poll(&mut s,&mut w,now).unwrap();let raw=queued_bodies(&s,now).concat();
    assert!(!contains(&raw,&wire::tracer_stop(&p).unwrap()));
    assert!(s.shared.as_ref().unwrap().tracer_stopped[0]);
    assert_eq!(s.shared.as_ref().unwrap().impact_cursor,1);
}

#[test] fn p07b_hidden_attacker_owner_damage_updates_hud_without_shooter_coordinates() {
    let now=Instant::now();let mut w=model::tests::terrain_world(now,1000.);
    w.apply(1,2,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],now).unwrap();
    w.advance(now+model::STEP).unwrap();assert_eq!(w.actors[0].health,60);let now=now+model::STEP;
    w.lifecycle=Some(super::super::lifecycle::State::new(super::super::lifecycle::Rules::prohorovka()).unwrap());
    w.actors[1].position[0]=500.;let mut s=spotted(now,&w);
    poll(&mut s,&mut w,now).unwrap();let raw=queued_bodies(&s,now).concat();
    assert!(contains(&raw,&impact_wire::owner_health(60).unwrap()));
    assert!(!contains(&raw,&wire::shooting(1).unwrap()));
    let mut hidden=vec![0x15];hidden.extend(wire::vehicle_id(1).unwrap().to_le_bytes());assert!(!contains(&raw,&hidden));
    assert_eq!(s.shared.as_ref().unwrap().impact_cursor,1);
}

#[test] fn p07b_hidden_attacker_kill_is_public_once_without_precision_effects() {
    let start=Instant::now();let mut w=world(start);let mut s=spotted(start,&w);
    let mut delivered=Vec::new();
    for round in 0..3 {
        let at=start+Duration::from_secs(round*3);
        // Authored test policy admits source AP shots before installing the
        // lifecycle view used by the replication check. No client hit claims.
        w.lifecycle=None;w.actors[1].position=[0.,0.,10.];
        w.apply(1,2,&[model::Command::Fire(crate::battle091::fire::Command::Shoot)],at).unwrap();
        let now=at+model::STEP;w.advance(now).unwrap();
        w.lifecycle=Some(super::super::lifecycle::State::new(super::super::lifecycle::Rules::prohorovka()).unwrap());
        w.actors[1].position[0]=500.;poll(&mut s,&mut w,now).unwrap();
        delivered.extend(send_and_ack(&mut s,now));
    }
    assert_eq!(w.actors[0].health,0);
    let killed=super::super::lifecycle_wire::vehicle_killed(wire::vehicle_id(0).unwrap(),wire::vehicle_id(1).unwrap(),0).unwrap();
    let raw=delivered.concat();assert_eq!(raw.windows(killed.len()).filter(|v|*v==killed).count(),1);
    assert!(contains(&raw,&impact_wire::owner_health(0).unwrap()));
    assert!(!contains(&raw,&wire::shooting(1).unwrap()));
    for p in &w.projectiles {assert!(!contains(&raw,&wire::tracer_start(p).unwrap()));}
    poll(&mut s,&mut w,start+Duration::from_secs(7)).unwrap();
    assert!(!contains(&queued_bodies(&s,start+Duration::from_secs(7)).concat(),&killed));
}
