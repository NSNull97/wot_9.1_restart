//! UI-04 fixtures: the ledger reaches the results only with its gateway key, the
//! totals record only a client that asked for it and only after the outcome.
//! Native UI acceptance is separate.
use super::*;
use super::tests::frame;
use super::ui02_tests::{all_bodies,before_hit,channel_frames,contains,enable,hello,hit_world,spotted};
use super::super::battle_events::{self,Channel,FeedCursors,FeedKind,HISTORY_FEATURE,VERSION};
use super::super::lifecycle::{Reason,Rules,State};
use super::super::lifecycle_result;
use super::super::lifecycle_wire::{LEDGER_POLICY,Results};

const FROM_START:FeedCursors=FeedCursors{impacts:0,damage:0,ram:0,devices:0,spots:0,capture:0,defence:0};
fn history_record(version:i32)->Vec<u8> {
    let mut args=vec![HISTORY_FEATURE.len() as u8];args.extend(HISTORY_FEATURE);args.extend(version.to_le_bytes());
    let mut raw=vec![0xa1];raw.extend((args.len() as u16).to_le_bytes());raw.extend(args);raw
}
fn open(s:&mut Session) {
    let mut channel=Channel::new();channel.open_history();channel.cursors=Some(FROM_START);
    s.shared.as_mut().unwrap().battle_events=Some(channel);
}
fn finish(w:&mut World) {
    let mut state=State::new(Rules::prohorovka()).unwrap();state.finish_for_test(1,Reason::Timeout);
    w.lifecycle=Some(state);w.lifecycle_created_unix=Some(1792080000);
}
/// A real shell of slot 0 on slot 1; slot 2 is their ally, the holder of the spot credit.
fn trio(now:Instant)->(World,Instant,u32) {
    let (mut w,now)=hit_world(now,0,1);
    let mut ally=w.actors[0].clone();ally.identity.database=77;ally.identity.name="ally".into();
    w.actors.push(ally);w.push_test_team_plan();
    let tick=w.impacts[0].tick;w.push_test_spot(2,1,tick);
    let hp=u32::from((w.impacts[0].health_before-w.impacts[0].health_after) as u16);
    (w,now,hp)
}
fn totals_of(frames:&[Vec<u8>])->Vec<[u32;5]> {
    let mut rows=Vec::new();
    for f in frames {
        let (mut at,count)=(6,f[5]);
        for _ in 0..count {
            let (kind,size)=(f[at],usize::from(f[at+1]));let p=&f[at+2..at+2+size];at+=2+size;
            if kind==3 {assert_eq!(size,20);rows.push(std::array::from_fn(|i|u32::from_le_bytes(p[i*4..i*4+4].try_into().unwrap())));}
        }
    }
    rows
}
fn publish(s:&mut Session,w:&World,now:Instant,lines:&mut Vec<String>)->Vec<Vec<u8>> {
    let mut outbox=VecDeque::new();
    battle_events_publication::publish(s.shared.as_mut().unwrap(),&mut outbox,w,now,lines).unwrap();
    channel_frames(&outbox.into_iter().collect::<Vec<_>>())
}

#[test] fn ui04_without_the_key_the_journal_stays_results8() {
    let (mut w,_,_)=trio(Instant::now());finish(&mut w);
    let result=lifecycle_result::build(&w).unwrap();
    assert_eq!(result.ledger,None);
    let raw=serde_json::to_string(&result).unwrap();assert!(!raw.contains("ledger"));
    assert!(result.interaction_details.unwrap().rows.iter().flat_map(|row|&row.targets)
        .all(|t|t.damage_assisted_radio==0&&t.damage_assisted_track==0));
}
#[test] fn ui04_ledger_of_a_real_shell_fills_totals_and_the_row_of_its_target() {
    let (mut w,_,hp)=trio(Instant::now());w.force_result_ledger_for_test();finish(&mut w);
    let result=lifecycle_result::build(&w).unwrap();
    let ledger=result.ledger.as_ref().unwrap();
    assert_eq!((ledger.version,ledger.policy.as_str(),ledger.rows.len()),(1,LEDGER_POLICY,3));
    assert_eq!((ledger.rows[2].assist_spot,ledger.rows[2].assist_track),(hp,0),"the holder of the credit");
    assert_eq!(ledger.rows[0].assist_spot,0,"own damage earns no assist");
    assert_eq!(ledger.rows[1].assist_spot,0);
    let details=result.interaction_details.as_ref().unwrap();
    let target=&details.row(wire::vehicle_id(2).unwrap()).unwrap().targets[0];
    assert_eq!((target.vehicle_id,target.damage_assisted_radio,target.spotted),(wire::vehicle_id(1).unwrap(),hp as u16,1));
    let decoded:Results=serde_json::from_str(&serde_json::to_string(&result).unwrap()).unwrap();
    decoded.validate().unwrap();assert_eq!(decoded,result);
}
#[test] fn ui04_blocked_shell_is_counted_in_the_results_as_in_the_feed() {
    let (mut w,_)=hit_world(Instant::now(),1,0);
    w.projectiles[0].shell=Some(crate::p06t_shells091::PROFILES[0].shots[1]);
    let before=w.impacts[0].health_before;w.impacts[0].health_after=before;
    if let model::ImpactOutcome::Ap(resolution)=&mut w.impacts[0].outcome {resolution.outcome=ap::Outcome::NotPierced;}
    let nominal=u32::from(battle_ledger::nominal(&w,w.impacts[0].shot).unwrap());
    w.force_result_ledger_for_test();finish(&mut w);
    let result=lifecycle_result::build(&w).unwrap();
    let row=&result.ledger.unwrap().rows[0];
    assert_eq!((row.blocked,row.potential_received),(nominal,nominal));
}
#[test] fn ui04_totals_wait_for_the_outcome_then_leave_once() {
    let (mut w,now,hp)=trio(Instant::now());
    let mut s=spotted(now,&w,0);open(&mut s);
    let mut lines=Vec::new();
    assert!(totals_of(&publish(&mut s,&w,now,&mut lines)).is_empty(),"no sum while the battle goes on");
    finish(&mut w);
    let sent=totals_of(&publish(&mut s,&w,now,&mut lines));
    assert_eq!(sent,vec![[hp,0,0,0,0]]);
    assert!(lines.iter().any(|line|line.starts_with("BATTLE_HISTORY_TOTALS ")));
    assert!(totals_of(&publish(&mut s,&w,now+model::STEP,&mut lines)).is_empty(),"one record per channel");
}
#[test] fn ui04_a_channel_without_the_history_hello_never_gets_totals() {
    let (mut w,now,_)=trio(Instant::now());finish(&mut w);
    let mut s=spotted(now,&w,0);
    let mut channel=Channel::new();channel.open_feed();channel.cursors=Some(FROM_START);s.shared.as_mut().unwrap().battle_events=Some(channel);
    assert!(totals_of(&publish(&mut s,&w,now,&mut Vec::new())).is_empty());
}
#[test] fn ui04_history_hello_needs_the_key_and_opens_the_feed() {
    let (w,now)=hit_world(Instant::now(),0,1);
    let mut s=spotted(now,&w,0);enable(&mut s);hello(&mut s,now);
    s.receive(&frame(&s,&history_record(i32::from(VERSION))),now).unwrap();
    let channel=s.shared.as_ref().unwrap().battle_events.as_ref().unwrap();
    assert!(!channel.feed()&&!channel.totals_due(),"without the key the old unsupported path");
    s.shared.as_mut().unwrap().battle_history_enabled=true;
    s.receive(&frame(&s,&history_record(9)),now).unwrap();
    assert!(!s.shared.as_ref().unwrap().battle_events.as_ref().unwrap().totals_due(),"a wrong version opens nothing");
    s.receive(&frame(&s,&history_record(i32::from(VERSION))),now).unwrap();
    let channel=s.shared.as_ref().unwrap().battle_events.as_ref().unwrap();
    assert!(channel.feed()&&channel.totals_due());
}
#[test] fn ui04_a_refused_totals_frame_is_due_again() {
    let (mut w,now,hp)=trio(Instant::now());finish(&mut w);
    let mut s=spotted(now,&w,0);open(&mut s);
    let c=s.shared.as_mut().unwrap();let mut lines=Vec::new();
    let mut outbox=VecDeque::from(vec![Vec::new();battle_events::MAX_OUTBOX_BACKLOG]);
    battle_events_publication::publish(c,&mut outbox,&w,now,&mut lines).unwrap();
    assert_eq!(outbox.len(),battle_events::MAX_OUTBOX_BACKLOG,"the slow peer lost nothing but the turn");
    assert!(c.battle_events.as_ref().unwrap().totals_due());
    assert_eq!(totals_of(&publish(&mut s,&w,now,&mut lines)),vec![[hp,0,0,0,0]]);
}
/// A hidden target: during the battle no byte carries the sum, its HP or its ID.
#[test] fn ui04_a_hidden_target_stays_absent_until_the_battle_is_over() {
    let (mut w,now,hp)=trio(Instant::now());
    w.actors[1].position[0]=500.;
    let mut s=spotted(now,&w,0);before_hit(&mut s);enable(&mut s);open(&mut s);
    assert!(!s.shared.as_ref().unwrap().visible()[1]);
    poll(&mut s,&mut w,now).unwrap();
    let bodies=all_bodies(&mut s,now);let frames=channel_frames(&bodies);
    let dealt=frames.iter().flat_map(|f|f[6..].windows(3)).filter(|v|v[0]==FeedKind::ShotDamage as u8&&v[1]==0xff&&v[2]==0xff).count();
    assert_eq!(dealt,1,"the event, no amount");
    let id=wire::vehicle_id(1).unwrap().to_le_bytes();let sum=(hp as u16).to_le_bytes();
    for f in &frames {assert!(!contains(&f[6..],&id),"no ID of the hidden target");assert!(!contains(&f[6..],&sum),"no amount");}
    assert!(totals_of(&frames).is_empty());
    finish(&mut w);
    assert_eq!(totals_of(&publish(&mut s,&w,now,&mut Vec::new())),vec![[hp,0,0,0,0]],"the sum tells no single shot any more");
}
/// The enemy of the recipient learns nothing from the recipient's channel: the
/// frame is built per session, and its own sums are its own.
#[test] fn ui04_each_recipient_gets_only_its_own_sums() {
    let (mut w,now,hp)=trio(Instant::now());finish(&mut w);
    let (mut own,mut enemy)=(spotted(now,&w,0),spotted(now,&w,1));open(&mut own);open(&mut enemy);
    assert_eq!(totals_of(&publish(&mut own,&w,now,&mut Vec::new())),vec![[hp,0,0,0,0]]);
    assert_eq!(totals_of(&publish(&mut enemy,&w,now,&mut Vec::new())),vec![[0,0,0,0,0]]);
}
