//! MM-01 rules: tier window, full group, timeout, FIFO anchors, several
//! arenas, lease renewal, and one ticket per session/account (no two battles).
use super::*;

fn rules(team_size:usize,spread:u8,wait:u64)->Rules {
    Rules{team_size,tiers:(1,10),tier_spread:spread,wait:Duration::from_secs(wait),lease:Duration::from_secs(wait*3)}
}
fn ticket(session:u32,tier:u8,since:Instant)->Ticket {Ticket{session,account:format!("account-{session}"),tier,class:(tier%5),since}}
fn sessions(g:&Group)->Vec<u32> {g.members.iter().map(|t|t.session).collect()}

#[test]
fn mm01_rules_are_bounded_and_size_the_arena(){
    let ok=rules(3,1,20);ok.validate(6).unwrap();assert_eq!(ok.places(),6);
    assert!(ok.validate(4).is_err(),"team size must match the arena places");
    let mut big=rules(15,0,30);big.validate(30).unwrap();big.tiers=(5,5);big.validate(30).unwrap();
    for broken in [Rules{team_size:0,..rules(3,1,20)},Rules{tiers:(0,10),..rules(3,1,20)},Rules{tiers:(6,5),..rules(3,1,20)},
        Rules{tiers:(1,11),..rules(3,1,20)},Rules{tier_spread:10,..rules(3,1,20)},Rules{wait:Duration::ZERO,..rules(3,1,20)},
        Rules{wait:Duration::from_secs(601),lease:Duration::from_secs(900),..rules(3,1,20)},Rules{wait:Duration::from_millis(1500),..rules(3,1,20)},
        Rules{lease:Duration::from_secs(19),..rules(3,1,20)},Rules{lease:Duration::from_secs(901),..rules(3,1,20)}] {
        assert!(broken.validate(6).is_err(),"{broken:?}");
    }
}

#[test]
fn mm01_full_group_forms_at_once_and_waits_otherwise(){
    let now=Instant::now();let mut mm=Matchmaker::new(rules(2,1,30));
    for s in 1..=3 {mm.enqueue(ticket(s,5,now)).unwrap();}
    assert!(mm.form(&[(0,100)],now+Duration::from_secs(29)).is_empty(),"three of four places, no timeout yet");
    mm.enqueue(ticket(4,6,now)).unwrap();
    let g=mm.form(&[(0,100)],now+Duration::from_secs(1));
    assert_eq!(g.len(),1);assert_eq!(sessions(&g[0]),[1,2,3,4]);assert_eq!(g[0].formed,Formed::Full);
    assert_eq!((g[0].arena,g[0].battle,g[0].tiers()),(0,100,(5,6)));
    assert!(mm.queue().is_empty());assert_eq!(mm.group_of(3).unwrap().battle,100);
}

#[test]
fn mm01_tier_spread_keeps_far_tiers_apart(){
    let now=Instant::now();let mut mm=Matchmaker::new(rules(2,1,30));
    // FIFO: 10, 5, 6, 5, 10, 6. Spread 1: the tier-10 anchor cannot fill; the next anchor can.
    for (s,tier) in [(1,10),(2,5),(3,6),(4,5),(5,10),(6,6)] {mm.enqueue(ticket(s,tier,now)).unwrap();}
    let g=mm.form(&[(0,100)],now);
    assert_eq!(sessions(&g[0]),[2,3,4,6],"a younger anchor of another tier fills a full group");
    assert_eq!(mm.queue().iter().map(|t|t.session).collect::<Vec<_>>(),[1,5]);
    // Spread 0 (same tier only), window [5,6] is no longer one group.
    let mut strict=Matchmaker::new(rules(2,0,30));
    for (s,tier) in [(1,5),(2,6),(3,5),(4,6),(5,5),(6,5)] {strict.enqueue(ticket(s,tier,now)).unwrap();}
    assert_eq!(sessions(&strict.form(&[(0,100)],now)[0]),[1,3,5,6]);
    // A window never exceeds the spread even when anchored in the middle.
    let mut mid=Matchmaker::new(rules(3,2,30));
    for (s,tier) in [(1,6),(2,4),(3,8),(4,5),(5,7),(6,6),(7,6),(8,7)] {mid.enqueue(ticket(s,tier,now)).unwrap();}
    let g=mid.form(&[(0,100)],now);let (lo,hi)=g[0].tiers();
    assert_eq!(g[0].members.len(),6);assert!(hi-lo<=2,"{lo}..{hi}");
    assert_eq!(sessions(&g[0]),[1,3,5,6,7,8],"anchors 6 and 4 reach five; anchor 8 fills 6..8");
}

#[test]
fn mm01_timeout_starts_the_oldest_group_short_for_bots(){
    let start=Instant::now();let mut mm=Matchmaker::new(rules(3,1,20));
    mm.enqueue(ticket(1,5,start)).unwrap();
    mm.enqueue(ticket(2,9,start+Duration::from_secs(5))).unwrap();
    mm.enqueue(ticket(3,6,start+Duration::from_secs(10))).unwrap();
    assert!(mm.form(&[(0,100)],start+Duration::from_secs(19)).is_empty());
    let g=mm.form(&[(0,100),(1,200)],start+Duration::from_secs(20));
    assert_eq!(g.len(),1,"only the timed-out anchor is ready");
    assert_eq!((sessions(&g[0]),g[0].formed),(vec![1,3],Formed::Timeout),"tier 9 is outside the window");
    let late=mm.form(&[(1,200)],start+Duration::from_secs(25));
    assert_eq!((sessions(&late[0]),late[0].formed,late[0].arena),(vec![2],Formed::Timeout,1),"alone after its own wait");
}

#[test]
fn mm01_one_group_per_free_arena_in_order(){
    let now=Instant::now();let mut mm=Matchmaker::new(rules(1,0,30));
    for s in 1..=5 {mm.enqueue(ticket(s,3,now)).unwrap();}
    let g=mm.form(&[(1,200),(0,100)],now);
    assert_eq!(g.iter().map(|g|(g.arena,sessions(g))).collect::<Vec<_>>(),[(1,vec![1,2]),(0,vec![3,4])]);
    assert!(mm.form(&[(0,100),(1,200)],now).is_empty(),"arenas with a group are not free");
    assert!(mm.form(&[(2,100)],now).is_empty(),"nor is the battle of a group");
    assert_eq!(mm.started(100).unwrap().arena,0);assert!(mm.group_of(3).is_none());
}

#[test]
fn mm01_a_player_holds_one_ticket_and_never_two_battles(){
    let now=Instant::now();let mut mm=Matchmaker::new(Rules{tiers:(2,8),..rules(1,1,30)});
    assert_eq!(mm.enqueue(ticket(1,1,now)),Err(Refusal::Tier));assert_eq!(mm.enqueue(ticket(1,9,now)),Err(Refusal::Tier));
    mm.enqueue(ticket(1,4,now)).unwrap();
    assert_eq!(mm.enqueue(ticket(1,4,now)),Err(Refusal::Duplicate),"same session");
    assert_eq!(mm.enqueue(Ticket{session:9,..ticket(1,4,now)}),Err(Refusal::Duplicate),"same account, another session");
    mm.enqueue(ticket(2,4,now)).unwrap();
    let g=mm.form(&[(0,100),(1,200)],now);assert_eq!(g.len(),1);
    // Matched players cannot queue again while their group holds them.
    assert_eq!(mm.enqueue(ticket(1,4,now)),Err(Refusal::Duplicate));
    assert_eq!(mm.enqueue(Ticket{session:7,..ticket(2,4,now)}),Err(Refusal::Duplicate));
    mm.enqueue(ticket(3,4,now)).unwrap();mm.enqueue(ticket(4,4,now)).unwrap();
    let second=mm.form(&[(1,200)],now);assert_eq!(sessions(&second[0]),[3,4]);
    let mut seen=std::collections::BTreeSet::new();
    for g in mm.groups() {for t in &g.members {assert!(seen.insert(t.session),"session {} in two groups",t.session);}}
    // Leaving frees the ticket; the group shrinks, the other group is untouched.
    assert_eq!(mm.leave(1),Some(100));assert_eq!(mm.group_of(2).unwrap().members.len(),1);
    assert_eq!(mm.leave(1),None);mm.enqueue(ticket(1,4,now)).unwrap();assert!(mm.queued(1));
    assert_eq!(mm.leave(1),None);assert!(!mm.queued(1));
}

#[test]
fn mm01_lease_expires_renews_once_with_seated_members(){
    let now=Instant::now();let mut mm=Matchmaker::new(rules(2,0,10));
    for s in 1..=4 {mm.enqueue(ticket(s,2,now)).unwrap();}
    mm.form(&[(0,100)],now);
    assert!(mm.expired(now+Duration::from_secs(29)).is_empty());
    let at=now+Duration::from_secs(30);assert_eq!(mm.expired(at),[100]);
    assert!(mm.renew(100,&[],at).is_err(),"no seated member: dissolve instead");
    assert!(mm.renew(100,&[9],at).is_err(),"only members");
    mm.renew(100,&[1,3],at).unwrap();
    let g=mm.group_of(1).unwrap();assert_eq!((sessions(g),g.renewed),(vec![1,3],true));
    assert!(mm.group_of(2).is_none()&&!mm.queued(2),"cancelled members are out, not re-queued");
    assert!(mm.expired(at+Duration::from_secs(29)).is_empty());
    assert!(mm.renew(100,&[1],at+Duration::from_secs(30)).is_err(),"one renewal");
    assert_eq!(mm.dissolve(100).unwrap().members.len(),2);assert!(mm.groups().is_empty());
}

#[test]
fn mm01_bot_kinds_follow_the_group_window(){
    let kinds=[('a',5),('b',7),('c',5),('d',10),('e',1)];
    assert_eq!(bot_kinds((5,6),1,&kinds),(vec!['a','c'],false));
    assert_eq!(bot_kinds((6,6),1,&kinds),(vec!['a','b','c'],false));
    assert_eq!(bot_kinds((8,8),0,&kinds),(vec!['b'],true),"nearest when none fits");
    assert_eq!(bot_kinds((10,10),0,&kinds),(vec!['d'],false));
    assert_eq!(bot_kinds((1,1),9,&kinds),(vec!['a','b','c','d','e'],false));
}

/// Owner test 2026-10-29: four T-34 (tier 5) got KV-3 (7) on one side and M4
/// (5) on the other. Facing places now take one tier, the group's own first.
#[test]
fn mm01_facing_bot_places_share_one_tier(){
    let stand=[("ms1",1),("t26",2),("t34",5),("t3485",6),("kv3",7),("m4",5)];
    let (window,_)=bot_kinds((5,5),2,&stand);
    let kinds=stand.iter().filter(|(k,_)|window.contains(k)).copied().collect::<Vec<_>>();
    let tier=|k:&str|stand.iter().find(|(x,_)|*x==k).unwrap().1;
    let alternate=|places:usize|(0..places).map(|s|(s%2) as u8+1).collect::<Vec<_>>();
    for seed in 0..8 {
        let bots=paired_kinds(&alternate(6),&[Some(5);4],(5,5),seed,&kinds).unwrap();
        assert_eq!(bots.len(),2);assert_eq!((tier(bots[0]),tier(bots[1])),(5,5),"seed {seed}: {bots:?}");
        // One native: every bot place faces a bot or that native; pairs are equal.
        let bots=paired_kinds(&alternate(6),&[Some(5)],(5,5),seed,&kinds).unwrap();
        let tiers=std::iter::once(5).chain(bots.iter().map(|k|tier(k))).collect::<Vec<_>>();
        for pair in tiers.chunks(2) {assert_eq!(pair[0],pair[1],"seed {seed}: {tiers:?}");}
        assert_eq!(tiers,[5;6]);
    }
    // A native of another tier: the bot facing it takes the nearest allowed tier.
    let bots=paired_kinds(&alternate(4),&[Some(5),Some(5),Some(7)],(5,7),0,&kinds).unwrap();
    assert_eq!(bots.iter().map(|k|tier(k)).collect::<Vec<_>>(),[7]);
    // Bot pairs: the allowed tier nearest the group's middle, the lower on ties.
    let wide=[('a',4),('b',6),('c',8)];
    assert_eq!(paired_kinds(&alternate(4),&[],(5,7),0,&wide),Some(vec!['b';4]));
    assert_eq!(paired_kinds(&alternate(4),&[],(5,5),0,&wide),Some(vec!['a';4]));
    // Within a tier the kind rotates; facing places may differ in kind, not tier.
    let same=[('x',5),('y',5)];
    let bots=paired_kinds(&alternate(4),&[],(5,5),0,&same).unwrap();
    assert_eq!(bots,['x','x','y','y']);
    // An explicit team plan (1,1,2,2): place 0 faces 2, place 1 faces 3.
    let bots=paired_kinds(&[1,1,2,2],&[Some(4)],(4,8),0,&wide).unwrap();
    assert_eq!(bots,['b','a','b'],"place 2 faces the native (4), 3 faces the bot at 1");
    assert_eq!(paired_kinds::<char>(&alternate(4),&[],(5,5),0,&[]),None);
    assert_eq!(paired_kinds(&alternate(2),&[None;3],(5,5),0,&wide),None);
}

#[test]
fn mm01_client_tiers_of_the_stand_kinds(){
    use super::super::vehicle_profile::VehicleKind;
    let tier=|label:&str|VehicleKind::from_owned_label(label).unwrap().tier().unwrap();
    for (label,expected) in [("ms1",1),("t26",2),("t34",5),("t3485",6),("is7",10),("ussr-KV-3",7),("usa-M4_Sherman",5),
        ("japan-Chi_Ri",7),("germany-Waffentrager_E100",10)] {assert_eq!(tier(label),Some(expected),"{label}");}
    assert_eq!(VehicleKind::Fv183.tier().unwrap(),Some(10));
}

#[test]
fn mm01_queue_stats_count_waiting_players_by_class_and_tier(){
    let now=Instant::now();let mut mm=Matchmaker::new(rules(2,0,30));
    assert_eq!(mm.stats(),QueueStats::default());
    let t=|s:u32,tier:u8,class:u8|Ticket{session:s,account:format!("a{s}"),tier,class,since:now};
    for x in [t(1,5,1),t(2,5,1),t(3,5,2),t(4,5,1),t(5,1,0),t(6,10,4)] {mm.enqueue(x).unwrap();}
    assert_eq!(mm.enqueue(t(7,5,5)),Err(Refusal::Tier),"no sixth class");
    let all=mm.stats();
    assert_eq!(all.classes,[1,3,1,0,1]);assert_eq!(all.levels,[1,0,0,0,4,0,0,0,0,1]);
    // A matched group still waits for its battle; a started one leaves the counts.
    mm.form(&[(0,100)],now);assert_eq!(mm.stats(),all);
    mm.started(100);
    let left=mm.stats();assert_eq!(left.classes,[1,0,0,0,1]);assert_eq!(left.levels,[1,0,0,0,0,0,0,0,0,1]);
}
