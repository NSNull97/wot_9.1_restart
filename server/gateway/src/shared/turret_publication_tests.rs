//! AUTHORED terminal fixture, real Session/Window/receive atomicity. These tests
//! do not execute #717, create writer proof or claim physical turret collision.
use super::*;
use super::super::turret_publication_test_fixture::{fixture,fixture_for,detonate,mask,ack_all,send_pending,frame};
use std::time::Duration;

fn request(slot:usize)->Vec<u8>{let mut raw=vec![8,4,0];raw.extend(detached_turret::entity_id(slot).unwrap().to_le_bytes());raw}
fn parent_dead(s:&mut Session,w:&World,now:Instant){
    s.tx.enqueue_body(&detached_turret::terminal_health(1,Some(0),0,detached_turret::DeathKind::Detached).unwrap()).unwrap();
    ack_all(s,now);let c=s.shared.as_mut().unwrap();c.health_sent[1]=Some(0);c.view=Some(w.clone());
}
fn announced(s:&mut Session,w:&World,now:Instant){
    parent_dead(s,w,now);s.flush_shared_turrets(w,&mut Vec::new()).unwrap();
    assert!(matches!(s.shared.as_ref().unwrap().turrets.book.entry(1),Some(Entry::Announced{requested:false,..})));
}
fn created(s:&mut Session,w:&World,now:Instant){
    announced(s,w,now);let f=frame(s,&request(1));s.receive(&f,now).unwrap();
    s.flush_shared_turrets(w,&mut Vec::new()).unwrap();
    assert!(matches!(s.shared.as_ref().unwrap().turrets.book.entry(1),Some(Entry::Created{acked:false,..})));
}
#[test]fn p06t_turret_parent_create_negative_only_for_committed_detonation(){
    let now=Instant::now();let(_,mut w)=fixture(now);
    assert_eq!(parent_create(&w,1).unwrap(),wire::create_vehicle(&w,1).unwrap());
    detonate(&mut w);let raw=parent_create(&w,1).unwrap();let mut expected=wire::create_vehicle(&w,1).unwrap();
    assert_eq!(&expected[42..45],&[3,0,0]);expected[43..45].copy_from_slice(&(-2i16).to_le_bytes());assert_eq!(raw,expected);
    assert_eq!(w.actors[1].health,0);assert_eq!(w.actors[1].fire.typed().unwrap().counts(),[0;3]);
    w.actors[1].health=18;assert!(parent_create(&w,1).is_err());
}
#[test]fn p06t_turret_actual_request_create_ack_pose_and_retry_keep_one_entity(){
    let now=Instant::now();let(mut s,mut w)=fixture(now);detonate(&mut w);
    // It cannot announce before the parent negative-health publication.
    s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();assert_eq!(s.tx.len(),0);
    created(&mut s,&w,now);assert!(!s.shared.as_ref().unwrap().turrets.book.pose_allowed(1));
    let expected=detached_turret::create(1,w.actors[1].vehicle_kind(),Pose{position:w.turret_flights()[0].sample().position,direction:[0.;3]},false,false).unwrap();
    let bodies=send_pending(&mut s,now);assert!(bodies.windows(expected.len()).any(|part|part==expected));
    assert!(!bodies.windows(5).any(|part|part==[0x15,2,0,18,9]));
    let before=s.shared.as_ref().unwrap().turrets.book.clone();
    let retry=send_pending(&mut s,now+Duration::from_secs(1));assert_eq!(retry,bodies);assert_eq!(s.shared.as_ref().unwrap().turrets.book,before);
    ack_all(&mut s,now+Duration::from_secs(1));s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();
    let pose=send_pending(&mut s,now+Duration::from_secs(1));assert_eq!(pose.len(),31);assert_eq!(pose[2],0x15);
    assert_eq!(s.outbox.len(),0);s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();assert_eq!(s.tx.len(),1);
}
#[test]fn p06t_turret_request_late_poison_and_terminal_avatar_world_commands_are_atomic(){
    let now=Instant::now();let(mut s,mut w)=fixture(now);detonate(&mut w);announced(&mut s,&w,now);
    let c=s.shared.as_mut().unwrap();c.phase=Phase::Leaving;
    c.profile13=Some(profile13_session::State::new("12345678-1234-4234-8234-123456789abc".into(),13).unwrap());
    let original=c.turrets.book.clone();let rx=s.rx;let mut bad=request(1);bad.push(0xff);
    assert!(s.receive(&frame(&s,&bad),now).is_err());assert_eq!(s.rx,rx);assert_eq!(s.shared.as_ref().unwrap().turrets.book,original);
    let mut valid=request(1);valid.extend([0x88,0,0]);
    s.receive(&frame(&s,&valid),now).unwrap();let c=s.shared.as_ref().unwrap();
    assert!(matches!(c.turrets.book.entry(1),Some(Entry::Announced{requested:true,..})));
    assert!(c.commands.is_empty());assert_eq!(w.actors[0].fire.typed().unwrap().counts(),[2,3,4]);
    s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();assert!(matches!(s.shared.as_ref().unwrap().turrets.book.entry(1),Some(Entry::Created{..})));
}
#[test]fn p06t_turret_hidden_parent_has_neither_enter_nor_replayed_explosion(){
    let now=Instant::now();let(mut s,mut w)=fixture(now);detonate(&mut w);
    let c=s.shared.as_mut().unwrap();c.health_sent[1]=Some(0);c.interest.as_mut().unwrap().set_desired(mask(true),mask(false)).unwrap();
    effects(c,&mut s.outbox,&w,now).unwrap();s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();
    assert_eq!(s.tx.len(),0);assert_eq!(s.shared.as_ref().unwrap().turrets.book.entry(1),Some(Entry::Hidden));
    let c=s.shared.as_mut().unwrap();c.interest.as_mut().unwrap().set_desired(mask(true),mask(true)).unwrap();
    effects(c,&mut s.outbox,&w,now).unwrap();assert!(c.private_pending.is_empty());assert_eq!(c.turrets.effect_cursor,1);
    s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();assert!(matches!(s.shared.as_ref().unwrap().turrets.book.entry(1),Some(Entry::Announced{..})));
}
#[test]fn p06t_turret_hide_under_full_window_drops_fresh_pose_and_reenter_waits_leave_ack(){
    let now=Instant::now();let(mut s,mut w)=fixture(now);detonate(&mut w);created(&mut s,&w,now);ack_all(&mut s,now);
    for _ in 0..8{s.tx.enqueue().unwrap();}w.advance_turret_flights(now+Duration::from_millis(200)).unwrap();
    s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();assert_eq!(s.tx.len(),8);assert!(s.outbox.is_empty());
    let c=s.shared.as_mut().unwrap();c.interest.as_mut().unwrap().set_desired(mask(true),mask(false)).unwrap();
    s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();ack_all(&mut s,now);
    s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();let leave=send_pending(&mut s,now);
    assert_eq!(leave,detached_turret::leave(1).unwrap());assert!(!s.shared.as_ref().unwrap().turrets.book.pose_allowed(1));
    let c=s.shared.as_mut().unwrap();c.interest.as_mut().unwrap().set_desired(mask(true),mask(true)).unwrap();
    s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();assert_eq!(s.tx.len(),1);
    ack_all(&mut s,now);s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();assert!(matches!(s.shared.as_ref().unwrap().turrets.book.entry(1),Some(Entry::Announced{requested:false,..})));
}
#[test]fn p06t_turret_expired_leaving_avatar_result_gate_requires_actual_leave_ack(){
    let now=Instant::now();let(mut s,mut w)=fixture(now);detonate(&mut w);created(&mut s,&w,now);ack_all(&mut s,now);
    s.shared.as_mut().unwrap().phase=Phase::Leaving;
    assert!(!s.turret_presentation_ready(&w,now).unwrap());
    let expired=now+Duration::from_secs(5);w.advance_turret_flights(expired).unwrap();
    s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();assert!(!s.turret_presentation_ready(&w,expired).unwrap());
    let body=send_pending(&mut s,expired);assert_eq!(body,detached_turret::leave(1).unwrap());
    ack_all(&mut s,expired);assert!(s.turret_presentation_ready(&w,expired).unwrap());
    s.tx.enqueue().unwrap();assert!(!s.turret_presentation_ready(&w,expired).unwrap());
    ack_all(&mut s,expired);assert!(s.turret_presentation_ready(&w,expired).unwrap());
    assert!(s.turret_presentation_ready(&w,now+Duration::from_secs(20)).unwrap());
}
#[test]fn p06t_turret_landing_updates_source_bool_only_after_creation_ack_and_has_bounded_timeout(){
    assert_eq!(colliding(1,true).unwrap(),[18,2,0,18,9,159,1,19]);
    let now=Instant::now();let(mut s,mut w)=fixture_for(now,1);detonate(&mut w);created(&mut s,&w,now);ack_all(&mut s,now);
    // Analytic PROJECT point reaches the actual authored terrain by4s.
    let landed=now+Duration::from_secs(4);w.advance_turret_flights(landed).unwrap();
    assert_eq!(w.turret_flights()[0].sample().phase,FlightPhase::Resting);
    s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();let body=send_pending(&mut s,landed);
    assert!(body.starts_with(&colliding(1,true).unwrap()));
    let expired=now+Duration::from_secs(5);w.advance_turret_flights(expired).unwrap();
    s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();
    assert_eq!(s.turret_presentation_ready(&w,now+Duration::from_secs(20)).unwrap_err().kind(),io::ErrorKind::TimedOut);
}
