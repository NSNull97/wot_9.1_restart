//! Native-boundary regressions; no physics or original-client execution.
use super::*;
use crate::transport091;

fn mask(slots:&[usize])->[bool;model::MAX_ACTORS] {
    std::array::from_fn(|slot|slots.contains(&slot))
}
fn client()->Client {
    let mut c=Client::new(0);c.enable_spotting().unwrap();c.phase=Phase::Driving;
    c.interest.as_mut().unwrap().set_desired(mask(&[0,1]),mask(&[0,1])).unwrap();
    c.mark_announced(&[0,1],0).unwrap();
    for slot in 0..2 {c.creations[slot]=Some((1,true));c.creation_announcements[slot]=Some(0);c.health_sent[slot]=Some(90);}
    c
}
fn session(now:Instant)->Session {
    let mut s=Session::new(1,[1;16],"127.0.0.1:38301".parse().unwrap(),now);
    let mut c=client();c.view=Some(model::tests::world(now));s.shared=Some(c);s
}
fn free_prefix(s:&mut Session,now:Instant) {
    // Reserve/sent reliable0..2 to match the existing announcement/create epoch.
    for _ in 0..3 {s.tx.enqueue().unwrap();}
    for _ in 0..3 {assert!(s.tx.due(now,s.rx).unwrap().is_some());}
    s.tx.acknowledge(&transport091::parse(&transport091::ack(3)).unwrap()).unwrap();
}
#[test]
fn original_enter_leave_and_filtered_initial_enter_have_exact_target_bytes() {
    assert_eq!(wire::enter_vehicle(1).unwrap(),[10,5,0,16,9,1]);
    assert_eq!(wire::leave_vehicle(1).unwrap(),[12,4,0,5,0,16,9]);
    assert!(wire::leave_vehicle(model::MAX_ACTORS).is_err());
    let w=model::tests::world(Instant::now());
    let parts=wire::announcement_parts_for(&w,0,mask(&[0])).unwrap();
    assert_eq!(parts.iter().flat_map(|p|p.enters.iter().copied()).collect::<Vec<_>>(),vec![0]);
    let raw=parts.iter().flat_map(|p|p.body.iter().copied()).collect::<Vec<_>>();
    assert!(raw.windows(6).any(|bytes|bytes==wire::enter_vehicle(0).unwrap()));
    assert!(!raw.windows(6).any(|bytes|bytes==wire::enter_vehicle(1).unwrap()));
    assert!(wire::announcement_parts_for(&w,0,mask(&[1])).is_err());
}
#[test]
fn first_real_reliable_zero_is_retained_in_the_interest_epoch() {
    let now=Instant::now();let mut s=session(now);let mut c=Client::new(0);c.enable_spotting().unwrap();
    c.phase=Phase::Entities;c.interest.as_mut().unwrap().set_desired(mask(&[0,1]),mask(&[0,1])).unwrap();s.shared=Some(c);
    s.flush_shared_interest(&mut Vec::new()).unwrap();
    assert_eq!(s.shared.as_ref().unwrap().interest.as_ref().unwrap().announcement_sequence(0),Some(0));
    assert_eq!(s.tx.due(now,0).unwrap().unwrap().0,0);
    assert!(s.shared.as_ref().unwrap().request_allowed(0));
    assert!(!s.shared.as_ref().unwrap().visible()[0]);
}
#[test]
fn private_pending_is_revalidated_before_fresh_reliable_enqueue() {
    let now=Instant::now();let mut s=session(now);
    s.shared.as_mut().unwrap().queue_private(&mut s.outbox,vec![0x13,0x48,1],&[1]).unwrap();
    assert_eq!(s.shared.as_ref().unwrap().pending_private_len(),1);assert!(s.outbox.is_empty());
    s.shared.as_mut().unwrap().interest.as_mut().unwrap().set_desired(mask(&[0,1]),mask(&[0])).unwrap();
    s.flush_shared_private().unwrap();assert_eq!(s.tx.len(),0);assert_eq!(s.shared.as_ref().unwrap().pending_private_len(),0);
    s.shared.as_mut().unwrap().interest.as_mut().unwrap().set_desired(mask(&[0,1]),mask(&[0,1])).unwrap();
    s.flush_shared_private().unwrap();assert_eq!(s.tx.len(),0);
}
#[test]
fn dropping_a_hidden_attacker_compound_invalidates_still_visible_victim_health_catchup() {
    let now=Instant::now();let mut s=session(now);
    let c=s.shared.as_mut().unwrap();c.owner_health_sent=Some(60);c.health_sent[0]=Some(60);
    c.queue_private(&mut s.outbox,vec![0x13,0x3f,60,0,1],&[1,0]).unwrap();
    c.interest.as_mut().unwrap().set_desired(mask(&[0,1]),mask(&[0])).unwrap();
    s.flush_shared_private().unwrap();let c=s.shared.as_ref().unwrap();
    assert!(c.visible()[0]);assert_eq!(c.health_sent[0],None);assert_eq!(c.owner_health_sent,None);
    assert_eq!(s.tx.len(),0);assert_eq!(c.pending_private_len(),0);
}
#[test]
fn request_before_enter_ack_is_legal_but_creation_ack_is_required_for_private_state() {
    let mut c=client();c.creations[1]=Some((1,false));
    assert!(c.request_allowed(1));assert!(!c.visible()[1]);
    let mut outbox=VecDeque::new();assert!(c.queue_private(&mut outbox,vec![0x13],&[1]).is_err());
    assert!(outbox.is_empty());assert_eq!(c.pending_private_len(),0);
}
#[test]
fn actual_leave_ack_barrier_clears_old_creation_before_reenter_and_old_ack_cannot_reuse_it() {
    let now=Instant::now();let mut s=session(now);free_prefix(&mut s,now);
    s.shared.as_mut().unwrap().interest.as_mut().unwrap().set_desired(mask(&[0,1]),mask(&[0])).unwrap();
    s.flush_shared_interest(&mut Vec::new()).unwrap();
    assert!(s.shared.as_ref().unwrap().creations[1].is_none());assert!(!s.shared.as_ref().unwrap().visible()[1]);
    s.shared.as_mut().unwrap().interest.as_mut().unwrap().set_desired(mask(&[0,1]),mask(&[0,1])).unwrap();
    s.flush_shared_interest(&mut Vec::new()).unwrap();assert_eq!(s.tx.len(),1);
    let(seq,_,packet)=s.tx.due(now,s.rx).unwrap().unwrap();assert_eq!(seq,3);
    assert_eq!(transport091::parse(&packet).unwrap().body,wire::leave_vehicle(1).unwrap());
    let ack=transport091::parse(&transport091::ack(4)).unwrap();s.tx.acknowledge(&ack).unwrap();
    s.shared.as_mut().unwrap().acknowledge(s.tx.cumulative,&ack).unwrap();
    s.flush_shared_interest(&mut Vec::new()).unwrap();
    let c=s.shared.as_mut().unwrap();assert_eq!(c.interest.as_ref().unwrap().announcement_sequence(1),Some(4));
    assert!(c.creations[1].is_none());c.creations[1]=Some((5,false));c.creation_announcements[1]=Some(4);
    let mut old=ack;old.selective=vec![1];c.acknowledge(4,&old).unwrap();assert!(!c.visible()[1]);
}
#[test]
fn invalid_late_payload_rolls_back_real_leave_ack_and_whole_book() {
    let now=Instant::now();let mut s=session(now);free_prefix(&mut s,now);
    s.shared.as_mut().unwrap().interest.as_mut().unwrap().set_desired(mask(&[0,1]),mask(&[0])).unwrap();
    s.flush_shared_interest(&mut Vec::new()).unwrap();s.tx.due(now,s.rx).unwrap().unwrap();
    s.active=true;s.account_ready=true;s.rx=1;
    let before=s.shared.as_ref().unwrap().interest.clone();let old_tx=(s.tx.cumulative,s.tx.len());
    let frame=Frame{flags:0x458,sequence:Some(1),cumulative:Some(4),selective:vec![],piggybacks:vec![],
        body:[vec![1],s.token.to_le_bytes().to_vec(),vec![255]].concat()};
    assert!(s.receive(&frame,now).is_err());assert_eq!(s.rx,1);assert_eq!((s.tx.cumulative,s.tx.len()),old_tx);
    assert_eq!(s.shared.as_ref().unwrap().interest,before);
}
#[test]
fn full_window_blocks_leave_enqueue_but_never_keeps_hidden_actor_publishable() {
    let now=Instant::now();let mut s=session(now);for _ in 0..8 {s.tx.enqueue().unwrap();}
    let c=s.shared.as_mut().unwrap();c.interest.as_mut().unwrap().set_desired(mask(&[0,1]),mask(&[0])).unwrap();
    assert!(!c.visible()[1]);assert!(!c.request_allowed(1));
    s.flush_shared_interest(&mut Vec::new()).unwrap();assert_eq!(s.tx.len(),8);
    assert!(matches!(s.shared.as_ref().unwrap().interest.as_ref().unwrap().entry(1),Some(interest_wire::Entry::Announced{..})));
}
