//! NET-01: pose delivery modes on the real publication and send path.
use super::*;
use super::super::net01::PoseDelivery;
use super::tests::{visible_pair,frame};

fn world(now:Instant)->World {
    let mut w=model::tests::terrain_world(now,1000.);
    w.lifecycle=Some(super::super::lifecycle::State::new(super::super::lifecycle::Rules::prohorovka()).unwrap());
    w
}
fn request(slots:&[usize])->Vec<u8> {
    let mut raw=Vec::new();for &slot in slots {raw.extend([8,4,0]);raw.extend(wire::vehicle_id(slot).unwrap().to_le_bytes());}raw
}
fn ack_all(s:&mut Session,now:Instant) {
    let mut cumulative=s.tx.cumulative;
    while let Some((seq,_,_))=s.tx.due(now,s.rx).unwrap() {cumulative=cumulative.max(seq+1);}
    let mut f=frame(s,&[]);f.cumulative=Some(cumulative);s.receive(&f,now).unwrap();
}
/// Both vehicles created and acknowledged through the AoI book, in `mode`.
fn spotted(now:Instant,w:&World,mode:PoseDelivery)->Session {
    let(mut s,_,_)=visible_pair(now);
    let c=s.shared.as_mut().unwrap();c.creations=[None;model::MAX_ACTORS];
    c.phase=Phase::Account;c.enable_spotting().unwrap();c.set_pose_delivery(mode).unwrap();c.phase=Phase::Driving;
    s.shared_refresh_world(w).unwrap();s.flush_shared_interest(&mut Vec::new()).unwrap();
    ack_all(&mut s,now);
    s.receive(&frame(&s,&request(&[0,1])),now).unwrap();ack_all(&mut s,now);
    assert_eq!(&s.shared.as_ref().unwrap().visible()[..2],&[true,true]);s
}
/// First publications (period, readiness) go out and are acknowledged.
fn settle(s:&mut Session,w:&mut World,now:Instant) {
    for _ in 0..2 {w.tick+=1;poll(s,w,now).unwrap();ack_all(s,now);}
    assert_eq!(s.tx.len(),0);s.shared.as_mut().unwrap().poses_out.clear();
}
fn pose_frames(frames:&[Vec<u8>])->Vec<transport091::Frame> {
    frames.iter().map(|f|transport091::parse_interactive(f).unwrap()).filter(|f|f.flags&0x10==0).collect()
}

#[test] fn net01_latest_pose_bypasses_a_full_window_and_replaces_an_unsent_one() {
    let now=Instant::now();let mut w=world(now);let mut s=spotted(now,&w,PoseDelivery::LatestUnreliable);
    for _ in 0..8 {s.tx.enqueue_body(&[0x13,1]).unwrap();}
    w.tick+=1;poll(&mut s,&mut w,now).unwrap();
    assert_eq!(s.tx.len(),8,"a pose takes no reliable slot");
    assert_eq!(s.shared.as_ref().unwrap().poses_out,wire::publication_parts(&w,s.shared.as_ref().unwrap().visible()).unwrap());
    // Not sent before the next tick: the stale pose is replaced, not queued behind.
    w.tick+=1;w.actors[0].position[0]+=1.;poll(&mut s,&mut w,now).unwrap();
    let newest=wire::publication(&w,[true,true]).unwrap();
    assert_eq!(s.shared.as_ref().unwrap().poses_out,vec![newest.clone()]);
    assert_eq!(s.shared.as_ref().unwrap().pose_stats.replaced_unsent,1);
    let frames=transmit(&mut s,now).unwrap().unwrap();
    assert_eq!(frames.len(),9,"all eight due reliable bodies, then the pose");
    assert!(frames[..8].iter().all(|f|transport091::parse_interactive(f).unwrap().flags&0x10!=0));
    let pose=transport091::parse_interactive(&frames[8]).unwrap();
    assert_eq!((pose.flags,pose.sequence,pose.cumulative),(0x408,None,Some(s.rx)));
    assert_eq!(pose.body,newest);assert_eq!(frames[8],transport091::unreliable(s.rx,&newest).unwrap());
    // Sent once: never repeated, and nothing reliable is due before the retry timer.
    assert!(s.shared.as_ref().unwrap().poses_out.is_empty());
    assert!(transmit(&mut s,now).unwrap().unwrap().is_empty());
    let stats=s.shared.as_ref().unwrap().pose_stats;assert_eq!((stats.published,stats.packets),(2,1));
}

#[test] fn net01_shot_body_enters_the_window_while_poses_flow_every_tick() {
    let now=Instant::now();let mut w=world(now);let mut s=spotted(now,&w,PoseDelivery::LatestUnreliable);
    settle(&mut s,&mut w,now);s.shared.as_mut().unwrap().take_pose_stats();
    // Twenty ticks of poses with no ACK at all: the window stays empty.
    for _ in 0..20 {w.tick+=1;poll(&mut s,&mut w,now).unwrap();assert_eq!(pose_frames(&transmit(&mut s,now).unwrap().unwrap()).len(),1);}
    assert_eq!(s.tx.len(),0);
    let shot=wire::shooting(1).unwrap();s.outbox.push_back(shot.clone());
    w.tick+=1;poll(&mut s,&mut w,now).unwrap();assert_eq!(s.tx.len(),1);
    let frames=transmit(&mut s,now).unwrap().unwrap();assert_eq!(frames.len(),2);
    assert_eq!(transport091::parse_interactive(&frames[0]).unwrap().body,shot,"the shot goes first");
    assert_eq!(pose_frames(&frames).len(),1);
    let stats=s.shared.as_ref().unwrap().pose_stats;assert_eq!((stats.published,stats.gap_max,stats.gaps_over_one),(21,1,0));
}

#[test] fn net01_reliable_mode_keeps_the_old_pose_gate_and_one_body_per_loop() {
    let now=Instant::now();let mut w=world(now);let mut s=spotted(now,&w,PoseDelivery::Reliable);
    settle(&mut s,&mut w,now);
    for _ in 0..4 {s.tx.enqueue_body(&[0x13,1]).unwrap();}
    w.tick+=1;poll(&mut s,&mut w,now).unwrap();assert_eq!(s.tx.len(),4,"no pose at four pending");
    assert!(s.shared.as_ref().unwrap().poses_out.is_empty());
    let frames=transmit(&mut s,now).unwrap().unwrap();assert_eq!(frames.len(),1);
    assert!(pose_frames(&frames).is_empty());
}

#[test] fn net01_reliable_burst_sends_every_due_body_and_keeps_reliable_poses() {
    let now=Instant::now();let mut w=world(now);let mut s=spotted(now,&w,PoseDelivery::ReliableBurst);
    settle(&mut s,&mut w,now);
    w.tick+=1;poll(&mut s,&mut w,now).unwrap();
    assert_eq!(s.tx.len(),1);assert!(s.shared.as_ref().unwrap().poses_out.is_empty());
    for _ in 0..2 {s.tx.enqueue_body(&[0x13,1]).unwrap();}
    let frames=transmit(&mut s,now).unwrap().unwrap();assert_eq!(frames.len(),3);
    assert_eq!(transport091::parse_interactive(&frames[0]).unwrap().body,wire::publication(&w,[true,true]).unwrap());
    assert!(pose_frames(&frames).is_empty());
}

#[test] fn net01_pose_left_from_an_ended_battle_is_dropped_and_mode_survives_reset() {
    let now=Instant::now();let w=world(now);let mut s=spotted(now,&w,PoseDelivery::LatestUnreliable);
    let c=s.shared.as_mut().unwrap();c.poses_out=vec![wire::publication(&w,[true,true]).unwrap()];c.phase=Phase::Returning;
    assert!(transmit(&mut s,now).unwrap().unwrap().is_empty());
    assert!(s.shared.as_ref().unwrap().poses_out.is_empty());
    let c=s.shared.as_mut().unwrap();c.reset_for_battle(0);assert_eq!(c.pose_delivery(),PoseDelivery::LatestUnreliable);
    // Chosen before a battle only; unreliable poses need the AoI book.
    let mut plain=Client::new(0);assert!(plain.set_pose_delivery(PoseDelivery::LatestUnreliable).is_err());
    plain.set_pose_delivery(PoseDelivery::ReliableBurst).unwrap();
    plain.phase=Phase::Driving;assert!(plain.set_pose_delivery(PoseDelivery::Reliable).is_err());
}

#[test] fn net01_burst_v2_holds_the_pose_aside_and_paces_one_reliable_part_per_loop() {
    let now=Instant::now();let mut w=world(now);let mut s=spotted(now,&w,PoseDelivery::ReliableBurstV2);
    settle(&mut s,&mut w,now);
    s.shared.as_mut().unwrap().take_pose_stats();
    for _ in 0..2 {s.tx.enqueue_body(&[0x13,1]).unwrap();}
    w.tick+=1;poll(&mut s,&mut w,now).unwrap();
    let pose=wire::publication(&w,[true,true]).unwrap();
    assert_eq!((s.tx.len(),s.shared.as_ref().unwrap().poses_out.clone()),(2,vec![pose.clone()]));
    let frames=transmit(&mut s,now).unwrap().unwrap();assert_eq!(frames.len(),3,"both queued bodies, then the pose part");
    let sent=transport091::parse_interactive(&frames[2]).unwrap();assert!(sent.flags&0x10!=0);assert_eq!(sent.body,pose);
    // Three parts of one tick: one per loop; a newer tick replaces the unsent rest.
    let parts=vec![pose.clone(),pose[2..40].to_vec(),pose[40..].to_vec()];s.shared.as_mut().unwrap().poses_out=parts.clone();
    for part in &parts[..2] {
        let frames=transmit(&mut s,now).unwrap().unwrap();assert_eq!(frames.len(),1);
        assert_eq!(&transport091::parse_interactive(&frames[0]).unwrap().body,part);
    }
    w.tick+=1;poll(&mut s,&mut w,now).unwrap();
    let newest=wire::publication(&w,[true,true]).unwrap();
    assert_eq!(s.shared.as_ref().unwrap().poses_out,vec![newest]);
    assert_eq!(s.shared.as_ref().unwrap().pose_stats.replaced_unsent,1);
    // A full window waits; the part stays aside instead of failing.
    while s.tx.len()<8 {s.tx.enqueue_body(&[0x13,1]).unwrap();}
    let frames=transmit(&mut s,now+transport091::RETRY).unwrap().unwrap();
    assert!(frames.iter().all(|f|transport091::parse_interactive(f).unwrap().body!=wire::publication(&w,[true,true]).unwrap()));
    assert_eq!(s.shared.as_ref().unwrap().poses_out.len(),1);
}

/// CRASH-01: owner battles 01.11 and 02.11 (captures of stand -12): a part of
/// the tick's pose split, held aside, went out after the leaveAoI of a vehicle
/// it still carried; the #717 client exited silently right there.
fn hide(s:&mut Session,slot:usize) {
    let c=s.shared.as_mut().unwrap();
    let desired=std::array::from_fn(|i|c.visible()[i]&&i!=slot);
    let active=std::array::from_fn(|i|i<2);
    c.interest.as_mut().unwrap().set_desired(active,desired).unwrap();
    assert!(!c.visible()[slot]);
}
fn carries(body:&[u8],slot:usize)->bool {
    let id=wire::vehicle_id(slot).unwrap().to_le_bytes();
    body.windows(5).any(|w|(w[0]==0x15||w[0]==0x12)&&w[1..]==id)
}
#[test] fn crash01_pose_part_held_aside_never_follows_the_leave_of_its_vehicle() {
    let now=Instant::now();let mut w=world(now);let mut s=spotted(now,&w,PoseDelivery::ReliableBurstV2);
    settle(&mut s,&mut w,now);
    w.tick+=1;poll(&mut s,&mut w,now).unwrap();
    // The 02.11 order: tickSync with the own vehicle, then a later part with the other one.
    let pose=s.shared.as_ref().unwrap().poses_out[0].clone();assert!(carries(&pose,1));
    s.shared.as_mut().unwrap().poses_out=vec![pose[..40].to_vec(),pose[40..].to_vec()];
    let first=transmit(&mut s,now).unwrap().unwrap();
    assert_eq!(transport091::parse_interactive(&first[0]).unwrap().body,pose[..40].to_vec());
    hide(&mut s,1);s.flush_shared_interest(&mut Vec::new()).unwrap();
    let mut sent=Vec::new();
    for _ in 0..4 {for f in transmit(&mut s,now).unwrap().unwrap() {sent.push(transport091::parse_interactive(&f).unwrap());}}
    let leave=sent.iter().position(|f|f.body==wire::leave_vehicle(1).unwrap()).expect("leaveAoI sent");
    assert!(sent[leave+1..].iter().all(|f|!carries(&f.body,1)),"no record of the left vehicle after its leaveAoI");
    assert!(sent.iter().all(|f|!carries(&f.body,1)),"the stale part is dropped, not sent before either");
    assert!(s.shared.as_ref().unwrap().poses_out.is_empty());
    // The next tick publishes only what is still visible.
    w.tick+=1;poll(&mut s,&mut w,now).unwrap();
    let parts=s.shared.as_ref().unwrap().poses_out.clone();assert!(parts.iter().all(|p|!carries(p,1)&&carries(p,0)));
}
#[test] fn crash01_latest_unreliable_pose_drops_a_vehicle_hidden_since_its_tick() {
    let now=Instant::now();let mut w=world(now);let mut s=spotted(now,&w,PoseDelivery::LatestUnreliable);
    settle(&mut s,&mut w,now);
    w.tick+=1;poll(&mut s,&mut w,now).unwrap();
    let pose=s.shared.as_ref().unwrap().poses_out[0].clone();assert!(carries(&pose,1));
    hide(&mut s,1);s.flush_shared_interest(&mut Vec::new()).unwrap();
    let frames=transmit(&mut s,now).unwrap().unwrap();
    let bodies:Vec<_>=frames.iter().map(|f|transport091::parse_interactive(f).unwrap()).collect();
    assert!(bodies.iter().any(|f|f.body==wire::leave_vehicle(1).unwrap()));
    let unreliable:Vec<_>=bodies.iter().filter(|f|f.flags&0x10==0).collect();
    assert_eq!(unreliable.len(),1);assert_eq!(unreliable[0].body,[&pose[..2],&pose[2..40]].concat());
}
#[test] fn crash01_record_filter_keeps_visible_bytes_and_refuses_foreign_layouts() {
    let now=Instant::now();let w=world(now);let pose=wire::publication(&w,[true,true]).unwrap();
    assert_eq!(wire::retain_publication_records(&pose,[true,true]).unwrap(),Some(pose.clone()));
    assert_eq!(wire::retain_publication_records(&pose,[true,false]).unwrap(),Some(pose[..40].to_vec()));
    assert_eq!(wire::retain_publication_records(&pose[40..],[true,false]).unwrap(),None);
    assert_eq!(wire::retain_publication_records(&pose[..2],[false,false]).unwrap(),Some(pose[..2].to_vec()));
    assert!(wire::retain_publication_records(&pose[..39],[true,true]).is_err());
    let mut wrong=pose.clone();wrong[2+30]^=1;assert!(wire::retain_publication_records(&wrong,[true,true]).is_err());
    assert!(wire::retain_publication_records(&[0x15,1],[true,true]).is_err());
}
