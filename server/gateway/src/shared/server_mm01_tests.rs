//! MM-01 gateway glue on two LAB arenas (no Domain, no scene): Join queues and
//! is announced, groups take free arenas by the rules, the writer gate names
//! exactly one battle, the timeout starts a short roster with bots, the lease
//! returns unseated members, and nobody ends up in two battles.
use super::*;
use super::super::matchmaker::Rules;
use super::super::profile13_session::{MatchGate,State};
use crate::map_profile091::MapId;

fn peer(port:u16)->SocketAddr{SocketAddr::from(([127,0,0,1],port))}
fn rules()->Rules{Rules{team_size:2,tiers:(1,10),tier_spread:1,wait:Duration::from_secs(20),lease:Duration::from_secs(60)}}
/// A hangar session that pressed "В бой" with native inventory row `native` (1 = MS-1, 2 = IS-7).
fn joined(now:Instant,id:u32,native:u32)->Session{
    let (mut s,_,_)=super::tests::visible_pair(now);s.id=id;
    let original=s.identity.as_ref().unwrap();
    s.identity=Some(Arc::new(crate::identity091::Profile{account_id:format!("mm01-owner-{id}"),database_id:id as i32,
        name:format!("player_{id}"),fixture_dir:original.fixture_dir.clone()}));
    s.key=[id as u8;16];s.login_peer=peer(32200+id as u16);s.login_attempt=Some(LoginAttempt::new(s.key,id,s.login_peer));
    s.base_peer=Some(peer(34200+id as u16));s.sync_mask=7;s.arena_base=false;s.active=true;s.outbox.clear();
    let c=s.shared.as_mut().unwrap();c.phase=Phase::Account;c.join_requested=true;c.queue_announced=false;
    c.hangar_since=Some(now-Duration::from_secs(3));
    let mut p=State::new("12345678-1234-4234-8234-123456789abc".into(),13).unwrap();p.selection=Some(native);c.profile13=Some(p);
    s
}
fn gate(s:&Session)->MatchGate{s.shared.as_ref().unwrap().profile13.as_ref().unwrap().match_gate}
/// Two unstarted arenas of four places, MS-1 bots (tier 1), LAB kinematics.
fn arenas(now:Instant)->Vec<arena::Arena>{
    (0..2).map(|i|{
        let mut w=model::bots::tests::prepared(MapId::Prohorovka,1,4,1,now);w.id+=i as u64*arena::ARENA_ID_STRIDE;
        let t=BattleTemplate::new(&w,&None);arena::Arena::new(i,w,None,t)
    }).collect()
}
fn runtime()->matchmaking::Runtime{
    matchmaking::Runtime::new(rules(),&model::bots::Plan{human_places:1,seed:1,kinds:vec![VehicleKind::Ms1]}).unwrap()
}
fn table(sessions:Vec<Session>)->Table{
    Table{sessions,capacity:256,arena_split:true,multi_arena:true,retirement:RetirementWindow::with_limit(1024),..Table::default()}
}
fn tick(m:&mut matchmaking::Runtime,t:&mut Table,a:&mut [arena::Arena],now:Instant){m.tick(t,a,&[],|_|false,now).unwrap();}
fn session(t:&Table,id:u32)->&Session{t.sessions.iter().find(|s|s.id==id).unwrap()}

#[test]
fn mm01_join_queues_and_full_group_takes_one_free_arena(){
    let now=Instant::now();let mut a=arenas(now);let mut m=runtime();
    let mut t=table((1..=6).map(|id|joined(now,id,if id<=4 {1} else {2})).collect());
    tick(&mut m,&mut t,&mut a,now);
    let (first,second)=(a[0].world.id,a[1].world.id);
    for id in 1..=4 {assert_eq!(gate(session(&t,id)),MatchGate::Matched(first),"tier-1 session {id}");}
    for id in 5..=6 {assert_eq!(gate(session(&t,id)),MatchGate::Queued,"tier 10 waits: spread 1");}
    for s in &t.sessions {
        let c=s.shared.as_ref().unwrap();assert!(c.queue_announced&&c.join_requested);
        assert_eq!(s.outbox.iter().collect::<Vec<_>>(),[&crate::map_drive_world091::queue_callback(true)],"one onEnqueued per Join");
    }
    assert_eq!((a[0].world.human_places(),a[1].world.human_places()),(4,1),"full group: four natives, no bot; arena 1 untouched");
    // The writer gate names one battle; queued Joins reserve nowhere.
    for s in &t.sessions {
        let p=s.shared.as_ref().unwrap().profile13.as_ref().unwrap();
        assert!(!(p.admits_into(first)&&p.admits_into(second)),"session {} admitted into two battles",s.id);
    }
    assert!(!session(&t,5).shared.as_ref().unwrap().profile13.as_ref().unwrap().admits_into(second));
    // A repeated tick keeps groups and queue; no second announcement.
    tick(&mut m,&mut t,&mut a,now+Duration::from_secs(1));
    assert!(t.sessions.iter().all(|s|s.outbox.len()==1));assert_eq!(m.mm.groups().len(),1);
    // Timeout: the two tier-10 Joins start short in the other arena (bots of the nearest tier).
    tick(&mut m,&mut t,&mut a,now+Duration::from_secs(20));
    assert_eq!((gate(session(&t,5)),gate(session(&t,6))),(MatchGate::Matched(second),MatchGate::Matched(second)));
    assert_eq!(a[1].world.human_places(),2);assert_eq!(a[1].world.bot_plan().unwrap().kinds,[VehicleKind::Ms1]);
    // A member cancels before its reservation: the group and the arena shrink.
    t.sessions[0].shared.as_mut().unwrap().join_requested=false;
    tick(&mut m,&mut t,&mut a,now+Duration::from_secs(21));
    assert_eq!(gate(&t.sessions[0]),MatchGate::Queued);assert_eq!(a[0].world.human_places(),3);
    assert!(!m.mm.queued(1),"a cancelled Join does not queue again");
}

#[test]
fn mm01_timeout_starts_a_short_roster_filled_by_bots(){
    let now=Instant::now();let mut a=arenas(now);let mut m=runtime();
    let mut t=table(vec![joined(now,1,1)]);
    tick(&mut m,&mut t,&mut a,now);tick(&mut m,&mut t,&mut a,now+Duration::from_secs(19));
    assert_eq!(gate(&t.sessions[0]),MatchGate::Queued,"no group before the wait");
    assert!(!t.arena_ready(&a[0].world,now),"no place before the match");
    tick(&mut m,&mut t,&mut a,now+Duration::from_secs(20));
    let battle=a[0].world.id;assert_eq!(gate(&t.sessions[0]),MatchGate::Matched(battle));
    assert_eq!(a[0].world.human_places(),1);
    // Seat the matched native (writer receipt elided: LAB attach), then the GW-01 barrier.
    let at=now+Duration::from_secs(21);
    let who=model::Identity{account:"mm01-owner-1".into(),database:1,name:"player_1".into()};
    a[0].world.attach(who,1).unwrap();
    t.sessions[0].outbox.clear();// the live loop moves onEnqueued into the channel
    assert!(t.arena_ready(&a[0].world,at),"one matched native starts the battle");
    assert_eq!(a[0].world.fill_bots().unwrap(),3);
    advance_battle(&mut a[0].world,&mut None,at,true).unwrap();assert!(a[0].started());
    tick(&mut m,&mut t,&mut a,at);
    assert!(m.mm.groups().is_empty(),"a started battle releases its group");
    assert_eq!(gate(&t.sessions[0]),MatchGate::Queued);
    assert_eq!(a[1].world.human_places(),1,"the other arena keeps its template roster");
}

#[test]
fn mm01_lease_returns_unseated_members_then_the_whole_group(){
    let now=Instant::now();let mut a=arenas(now);let mut m=runtime();
    let mut t=table(vec![joined(now,1,1),joined(now,2,1)]);
    tick(&mut m,&mut t,&mut a,now);tick(&mut m,&mut t,&mut a,now+Duration::from_secs(20));
    let battle=a[0].world.id;assert_eq!(a[0].world.human_places(),2);
    let who=model::Identity{account:"mm01-owner-1".into(),database:1,name:"player_1".into()};
    a[0].world.attach(who,1).unwrap();
    for s in &mut t.sessions {s.outbox.clear();}
    tick(&mut m,&mut t,&mut a,now+Duration::from_secs(79));
    assert_eq!(m.mm.groups()[0].members.len(),2,"lease still holds");
    tick(&mut m,&mut t,&mut a,now+Duration::from_secs(80));
    let returned=session(&t,2);let c=returned.shared.as_ref().unwrap();
    assert!(!c.join_requested&&!c.queue_announced&&c.profile13.as_ref().unwrap().selection.is_none());
    assert_eq!(returned.outbox.iter().collect::<Vec<_>>(),[&crate::battle091::profile13::enqueue_failure("BATTLE_BUSY").unwrap()]);
    assert_eq!(gate(session(&t,1)),MatchGate::Matched(battle),"the seated member keeps its battle");
    assert_eq!(a[0].world.human_places(),1,"its freed place goes to a bot");
    assert!(t.arena_ready(&a[0].world,now+Duration::from_secs(80)));
    // Second expiry: everyone returns, the group dissolves.
    tick(&mut m,&mut t,&mut a,now+Duration::from_secs(140));
    assert!(m.mm.groups().is_empty());assert!(!session(&t,1).shared.as_ref().unwrap().join_requested);
    assert_eq!(gate(session(&t,1)),MatchGate::Queued);
}

#[test]
fn mm01_a_player_in_a_battle_is_never_queued_or_matched_again(){
    let now=Instant::now();let mut a=arenas(now);let mut m=runtime();
    let mut t=table((1..=4).map(|id|joined(now,id,1)).collect());
    tick(&mut m,&mut t,&mut a,now);
    let first=a[0].world.id;
    for id in 1..=4 {
        let who=model::Identity{account:format!("mm01-owner-{id}"),database:id as i32,name:format!("player_{id}")};
        a[0].world.attach(who,id).unwrap();
    }
    advance_battle(&mut a[0].world,&mut None,now,true).unwrap();
    // Still `join_requested` in the arena; four new Joins of other players arrive.
    t.sessions.extend((5..=8).map(|id|joined(now,id,1)));
    // Within the second group's lease (formed at +10 s, 60 s).
    for step in 1..=6u64 {
        tick(&mut m,&mut t,&mut a,now+Duration::from_secs(step*10));
        for id in 1..=4 {
            assert!(!m.mm.queued(id)&&m.mm.group_of(id).is_none(),"player {id} of battle {first} queued again");
            assert!(!session(&t,id).shared.as_ref().unwrap().profile13.as_ref().unwrap().admits_into(a[1].world.id));
        }
    }
    let second=a[1].world.id;
    for id in 5..=8 {assert_eq!(gate(session(&t,id)),MatchGate::Matched(second));}
    let mut seen=std::collections::BTreeSet::new();
    for s in &t.sessions {if let MatchGate::Matched(_)=gate(s) {assert!(seen.insert(s.identity.as_ref().unwrap().account_id.clone()));}}
}

#[test]
fn mm01_unknown_tier_is_refused_and_absent_matchmaker_keeps_the_gate_open(){
    let now=Instant::now();let mut a=arenas(now);let mut m=runtime();
    let mut t=table(vec![joined(now,1,9)]);
    tick(&mut m,&mut t,&mut a,now);
    let s=&t.sessions[0];assert!(!s.shared.as_ref().unwrap().join_requested);
    assert_eq!(s.outbox.iter().collect::<Vec<_>>(),[&crate::battle091::profile13::enqueue_failure("BATTLE_PROFILE_UNSUPPORTED").unwrap()]);
    // Without `matchmaker` no tick runs: the default gate admits into the lobby battle (old path).
    let old=joined(now,2,1);let p=old.shared.as_ref().unwrap().profile13.as_ref().unwrap();
    assert_eq!(p.match_gate,MatchGate::Off);assert!(p.admits_into(a[0].world.id)&&p.admits_into(a[1].world.id));
}

#[test]
fn mm01_a_dissolved_group_never_reuses_its_battle_id(){
    let now=Instant::now();let mut a=arenas(now);let mut m=runtime();
    let mut t=table((1..=4).map(|id|joined(now,id,1)).collect());
    tick(&mut m,&mut t,&mut a,now);
    let spent=a[0].world.id;assert_eq!(gate(&t.sessions[0]),MatchGate::Matched(spent));
    for s in &mut t.sessions {s.shared.as_mut().unwrap().join_requested=false;}
    tick(&mut m,&mut t,&mut a,now+Duration::from_secs(1));
    assert!(m.mm.groups().is_empty(),"everyone cancelled: the group dissolves");
    // New Joins wait for the other arena, never for the spent battle id.
    t.sessions.extend((5..=8).map(|id|joined(now,id,1)));
    tick(&mut m,&mut t,&mut a,now+Duration::from_secs(2));
    for id in 5..=8 {assert_eq!(gate(session(&t,id)),MatchGate::Matched(a[1].world.id));}
    assert_eq!(m.take_resets(&t,&a,&[]),[0],"nobody holds the spent battle: reset it");
    let x=&mut a[0];x.template.replace(&mut x.world,&mut x.integrated,now).unwrap();
    assert_eq!(a[0].world.id,spent+1);assert!(m.take_resets(&t,&a,&[]).is_empty());
    t.sessions.extend((9..=12).map(|id|joined(now,id,1)));
    tick(&mut m,&mut t,&mut a,now+Duration::from_secs(3));
    for id in 9..=12 {assert_eq!(gate(session(&t,id)),MatchGate::Matched(spent+1));}
}
