//! Pure-domain tests. Fixture writer refs below are opaque synthetic adapter
//! inputs, NOT fake owned-loadout validators or proof of writer/native behavior.
use super::*;
fn lease(n:u8)->AuthLease{AuthLease{account:Account([n;16]),generation:1}}
fn settings(n:u8)->Settings{Settings{capacity:n,map:QualifiedMap::Karelia,seconds:600,opened:true,comment:"bounded room".into()}}
fn reference(n:u8,revision:u32)->WriterReadyRef{WriterReadyRef::from_verified_writer(lease(n).account,format!("fixture-owned-ref-{n}"),revision,[n;32]).unwrap()}
fn ready(r:&Registry,n:u8,selection:WriterReadyRef)->Command{Command::Ready{context:r.selection_context(lease(n)).unwrap(),selection}}
fn bound(n:u8)->Registry{let mut r=Registry::default();for i in 1..=n{r.bind_authenticated(lease(i),format!("Player{i}"),0).unwrap();}r}
fn created(r:&mut Registry,n:u8)->RoomKey{let events=r.command(lease(1),Command::Create(settings(n)),0).unwrap();match events[0]{Event::Created(k)=>k,_=>panic!()}}
fn populated(n:u8)->(Registry,RoomKey){let mut r=bound(n);let k=created(&mut r,n);for i in 2..=n{r.command(lease(i),Command::Join(k),0).unwrap();}
    for i in 1..=n{r.command(lease(1),Command::Assign{target:lease(i).account,roster:Roster::assigned(if i%2==1{Side::One}else{Side::Two})},0).unwrap();
        r.command(lease(i),ready(&r,i,reference(i,13)),0).unwrap();}(r,k)}
fn prepare(r:&mut Registry)->LaunchSnapshot{r.command(lease(1),Command::TeamReady{side:Side::One,ready:true,force:true},0).unwrap();
    r.command(lease(1),Command::TeamReady{side:Side::Two,ready:true,force:true},0).unwrap().into_iter().find_map(|e|if let Event::Prepare(s)=e{Some(s)}else{None}).unwrap()}
fn reserves(s:&LaunchSnapshot,b:BattleKey)->Vec<ReservedRef>{s.members.iter().map(|m|ReservedRef::from_verified_writer(m.ready.clone(),format!("fixture-reserve:{}:{}",s.ticket,m.account.0[0]),b,s.ticket).unwrap()).collect()}
fn released(s:&LaunchSnapshot)->Vec<ReleasedRef>{s.members.iter().map(|m|ReleasedRef::from_verified_writer(m.ready.clone(),s.ticket).unwrap()).collect()}
fn finished(s:&LaunchSnapshot,b:BattleKey)->Vec<FinishedRef>{reserves(s,b).into_iter().map(|r|FinishedRef::from_verified_writer(r.ready.owner,r.key,b).unwrap()).collect()}
fn reject_unchanged<T:std::fmt::Debug>(r:&mut Registry,f:impl FnOnce(&mut Registry)->Result<T>,want:Error){let before=r.clone();assert_eq!(f(r).unwrap_err(),want);assert_eq!(*r,before);}

#[test]fn capacities_two_to_six_create_exact_immutable_balanced_launch_rosters(){
    for n in 2..=6{let(mut r,k)=populated(n);let snapshot=prepare(&mut r);
        assert_eq!(snapshot.members.len(),usize::from(n));assert_eq!(r.room(k).unwrap().preparing(),Some(&snapshot));
        assert!(snapshot.members.iter().all(|m|m.ready.owner==m.account));
        let one=snapshot.members.iter().filter(|m|m.side==Side::One).count();let two=usize::from(n)-one;assert!((1..=3).contains(&one)&&(1..=3).contains(&two));
        let b=BattleKey(9007199254740993);r.commit_launch(k,snapshot.ticket,b,reserves(&snapshot,b),0).unwrap();
        assert!(r.room(k).is_none());assert_eq!(r.battle_snapshot(b),Some(&snapshot));for i in 1..=n{assert_eq!(r.claim(lease(i).account),Some(Claim::Battle(b)));}
    }
}
#[test]fn bounded_settings_identity_registry_and_side_limits_are_atomic(){
    let mut r=bound(1);for n in[0,1,7,255]{reject_unchanged(&mut r,|r|r.command(lease(1),Command::Create(settings(n)),0),Error::BadSettings);}
    for seconds in[0,59,1801,u16::MAX]{let mut s=settings(2);s.seconds=seconds;reject_unchanged(&mut r,|r|r.command(lease(1),Command::Create(s),0),Error::BadSettings);}
    reject_unchanged(&mut r,|r|r.bind_authenticated(lease(2),"x".repeat(49),0),Error::BadIdentity);
    reject_unchanged(&mut r,|r|r.bind_authenticated(AuthLease{generation:0,..lease(2)},"Player2".into(),0),Error::BadIdentity);
    let mut r=bound(24);reject_unchanged(&mut r,|r|r.bind_authenticated(lease(25),"Player25".into(),0),Error::Limit);
    for i in 1..=4{r.command(lease(i),Command::Create(settings(6)),0).unwrap();}
    reject_unchanged(&mut r,|r|r.command(lease(5),Command::Create(settings(6)),0),Error::Limit);
    let(mut r,k)=populated(6);r.command(lease(1),Command::Assign{target:lease(2).account,roster:Roster::bench(Side::Two)},0).unwrap();
    reject_unchanged(&mut r,|r|r.command(lease(1),Command::Assign{target:lease(2).account,roster:Roster::assigned(Side::One)},0),Error::InvalidTeam);
    assert_eq!(r.room(k).unwrap().members.len(),6);
}
#[test]fn commands_require_current_authenticated_lease_and_server_monotonic_clock(){
    let mut r=bound(2);let k=created(&mut r,2);
    reject_unchanged(&mut r,|r|r.command(lease(3),Command::Join(k),0),Error::Unauthenticated);
    reject_unchanged(&mut r,|r|r.command(AuthLease{generation:2,..lease(2)},Command::Join(k),0),Error::StaleLease);
    r.heartbeat(lease(1),100).unwrap();reject_unchanged(&mut r,|r|r.command(lease(2),Command::Join(k),99),Error::Clock);
    reject_unchanged(&mut r,|r|r.bind_authenticated(AuthLease{generation:2,..lease(1)},"Player1".into(),100),Error::AlreadyClaimed);
    r.bind_authenticated(AuthLease{generation:2,..lease(2)},"Player2".into(),100).unwrap();
    reject_unchanged(&mut r,|r|r.command(lease(2),Command::Join(k),100),Error::StaleLease);
}
#[test]fn membership_and_battle_claims_prevent_second_room_or_battle_before_durable_finish(){
    let(mut r,k)=populated(2);reject_unchanged(&mut r,|r|r.command(lease(2),Command::Create(settings(2)),0),Error::AlreadyClaimed);
    let s=prepare(&mut r);let b=BattleKey(41);r.commit_launch(k,s.ticket,b,reserves(&s,b),0).unwrap();
    reject_unchanged(&mut r,|r|r.command(lease(1),Command::Create(settings(2)),0),Error::AlreadyClaimed);
    reject_unchanged(&mut r,|r|r.command(lease(2),Command::Leave,0),Error::BusyBattle);
    reject_unchanged(&mut r,|r|r.bind_authenticated(AuthLease{generation:2,..lease(2)},"Player2".into(),0),Error::AlreadyClaimed);
    let fs=finished(&s,b);r.finish_battle(b,fs,0).unwrap();assert!(r.claim(lease(1).account).is_none());
    r.command(lease(1),Command::Create(settings(2)),0).unwrap();
}
#[test]fn selected_reference_requires_self_binding_and_selection_changes_reset_both_team_votes(){
    let(mut r,k)=populated(2);
    reject_unchanged(&mut r,|r|r.command(lease(1),ready(r,1,reference(2,13)),0),Error::WrongOwner);
    r.command(lease(1),Command::TeamReady{side:Side::One,ready:true,force:false},0).unwrap();
    assert_eq!(r.room(k).unwrap().team_ready,[true,false]);
    let mut changed=reference(1,14);changed.fingerprint=[9;32];r.command(lease(1),ready(&r,1,changed.clone()),0).unwrap();
    assert_eq!(r.room(k).unwrap().team_ready,[false,false]);assert_eq!(r.room(k).unwrap().members[&lease(1).account].ready,Some(changed));
    r.command(lease(2),Command::NotReady,0).unwrap();
    reject_unchanged(&mut r,|r|r.command(lease(1),Command::TeamReady{side:Side::Two,ready:true,force:true},0),Error::NotReady);
}
#[test]fn creator_two_native_team_steps_do_not_launch_early_and_force_cannot_bypass_predicates(){
    let(mut r,k)=populated(2);
    reject_unchanged(&mut r,|r|r.command(lease(2),Command::TeamReady{side:Side::One,ready:true,force:true},0),Error::NotCreator);
    let first=r.command(lease(1),Command::TeamReady{side:Side::One,ready:true,force:true},0).unwrap();assert_eq!(first,vec![Event::TeamsChanged(k)]);
    assert!(r.room(k).unwrap().preparing().is_none());assert!(r.battles.is_empty());
    r.command(lease(1),Command::TeamReady{side:Side::One,ready:false,force:true},0).unwrap();assert_eq!(r.room(k).unwrap().team_ready,[false,false]);
    r.command(lease(1),Command::Assign{target:lease(2).account,roster:Roster::bench(Side::Two)},0).unwrap();
    r.command(lease(1),Command::TeamReady{side:Side::One,ready:true,force:true},0).unwrap();
    reject_unchanged(&mut r,|r|r.command(lease(1),Command::TeamReady{side:Side::Two,ready:true,force:true},0),Error::InvalidTeam);
    assert!(r.room(k).unwrap().preparing().is_none());assert_eq!(r.room(k).unwrap().team_ready,[true,false]);
}
#[test]fn preparing_snapshot_is_immutable_and_wrong_late_receipts_cannot_bind_a_different_battle(){
    let(mut r,k)=populated(2);let s=prepare(&mut r);let b=BattleKey(41);
    let late_ready=Command::Ready{context:ReadyContext{room:k,revision:r.room(k).unwrap().revision},selection:reference(1,14)};
    for cmd in[Command::NotReady,late_ready,Command::SwapTeams,Command::UpdateSettings(settings(2))]{reject_unchanged(&mut r,|r|r.command(lease(1),cmd,0),Error::LaunchPending);}
    assert_eq!(r.room(k).unwrap().preparing(),Some(&s));
    reject_unchanged(&mut r,|r|r.commit_launch(k,s.ticket+1,b,reserves(&s,b),0),Error::WrongTicket);
    for poison in 0..7{let mut rs=reserves(&s,b);match poison{0=>{rs.pop();},1=>rs[1]=rs[0].clone(),2=>rs[0].ready.revision+=1,
        3=>rs[0].ready.fingerprint=[99;32],4=>rs[0].battle=BattleKey(42),5=>rs[0].ticket+=1,6=>rs[1].key=rs[0].key.clone(),_=>unreachable!()}
        reject_unchanged(&mut r,|r|r.commit_launch(k,s.ticket,b,rs,0),Error::WrongReceipt);}
    r.commit_launch(k,s.ticket,b,reserves(&s,b),0).unwrap();assert_eq!(r.battle_snapshot(b),Some(&s));
}
#[test]fn leave_during_prepare_requests_abort_but_retains_claims_until_every_writer_release(){
    let(mut r,k)=populated(2);let s=prepare(&mut r);let b=BattleKey(41);
    assert_eq!(r.command(lease(2),Command::Leave,0).unwrap(),vec![Event::AbortRequested{room:k,ticket:s.ticket}]);
    assert_eq!(r.claim(lease(2).account),Some(Claim::Room(k)));assert!(r.room(k).unwrap().abort_requested());
    reject_unchanged(&mut r,|r|r.commit_launch(k,s.ticket,b,reserves(&s,b),0),Error::LaunchPending);
    let mut partial=released(&s);partial.pop();reject_unchanged(&mut r,|r|r.abort_launch(k,s.ticket,partial,0),Error::WrongReceipt);
    let mut late=released(&s);late[0].ticket+=1;reject_unchanged(&mut r,|r|r.abort_launch(k,s.ticket,late,0),Error::WrongReceipt);
    r.abort_launch(k,s.ticket,released(&s),0).unwrap();assert!(r.claim(lease(2).account).is_none());
    assert_eq!(r.room(k).unwrap().members.len(),1);assert!(r.room(k).unwrap().members.values().all(|m|m.ready.is_none()));assert_eq!(r.room(k).unwrap().team_ready,[false,false]);
}
#[test]fn creator_leave_closes_room_and_creator_prepare_disconnect_closes_only_after_release(){
    let(mut r,k)=populated(3);r.command(lease(1),Command::Leave,0).unwrap();assert!(r.room(k).is_none());for i in 1..=3{assert!(r.claim(lease(i).account).is_none());}
    let(mut r,k)=populated(2);let s=prepare(&mut r);r.disconnect(lease(1),0).unwrap();assert!(r.room(k).is_some());
    assert_eq!(r.claim(lease(1).account),Some(Claim::Room(k)));r.abort_launch(k,s.ticket,released(&s),0).unwrap();assert!(r.room(k).is_none());
    assert!(r.auth.get(&lease(1).account).is_none());assert!(r.claim(lease(2).account).is_none());
}
#[test]fn kick_is_creator_only_and_room_full_closed_bench_and_swap_are_authoritative(){
    let mut r=bound(3);let k=created(&mut r,2);r.command(lease(2),Command::Join(k),0).unwrap();
    assert_eq!(r.room(k).unwrap().members[&lease(2).account].roster,Roster::bench(Side::One));
    reject_unchanged(&mut r,|r|r.command(lease(3),Command::Join(k),0),Error::RoomFull);
    reject_unchanged(&mut r,|r|r.command(lease(2),Command::Kick(lease(1).account),0),Error::NotCreator);
    let ev=r.command(lease(1),Command::Kick(lease(2).account),0).unwrap();assert!(ev.contains(&Event::Kicked{room:k,account:lease(2).account}));
    let mut closed=settings(2);closed.opened=false;r.command(lease(1),Command::UpdateSettings(closed),0).unwrap();
    reject_unchanged(&mut r,|r|r.command(lease(3),Command::Join(k),0),Error::ClosedRoom);
    r.command(lease(1),Command::SwapTeams,0).unwrap();assert_eq!(r.room(k).unwrap().members[&lease(1).account].roster.side,Side::Two);
}
#[test]fn timeout_obeys_auth_heartbeat_and_cannot_unlock_preparing_or_battle_claims(){
    let(mut r,k)=populated(2);r.heartbeat(lease(1),900).unwrap();r.expire(1000,1000).unwrap();
    assert!(r.claim(lease(2).account).is_none());assert!(r.room(k).is_some());r.expire(1900,1000).unwrap();assert!(r.room(k).is_none());
    let(mut r,k)=populated(2);let s=prepare(&mut r);r.heartbeat(lease(1),900).unwrap();r.expire(1000,1000).unwrap();
    assert!(r.room(k).unwrap().abort_requested());assert_eq!(r.claim(lease(2).account),Some(Claim::Room(k)));r.abort_launch(k,s.ticket,released(&s),1000).unwrap();
    let(mut r,k)=populated(2);let s=prepare(&mut r);let b=BattleKey(44);r.commit_launch(k,s.ticket,b,reserves(&s,b),0).unwrap();
    let ev=r.expire(1000,1000).unwrap();assert_eq!(ev.len(),2);for i in 1..=2{assert_eq!(r.claim(lease(i).account),Some(Claim::Battle(b)));}
    r.finish_battle(b,finished(&s,b),1000).unwrap();assert!(r.claims.is_empty()&&r.auth.is_empty());
}
#[test]fn finish_proofs_are_exact_complete_unique_and_do_not_unlock_on_forged_or_partial_outcome(){
    let(mut r,k)=populated(3);let s=prepare(&mut r);let b=BattleKey(45);r.commit_launch(k,s.ticket,b,reserves(&s,b),0).unwrap();
    for poison in 0..4{let mut fs=finished(&s,b);match poison{0=>{fs.pop();},1=>fs[1]=fs[0].clone(),2=>fs[0].reservation="other:key".into(),3=>fs[0].battle=BattleKey(46),_=>unreachable!()}
        reject_unchanged(&mut r,|r|r.finish_battle(b,fs,0),Error::WrongReceipt);}
    r.disconnect(lease(2),0).unwrap();assert_eq!(r.claim(lease(2).account),Some(Claim::Battle(b)));
    r.finish_battle(b,finished(&s,b),0).unwrap();assert!(r.claims.is_empty());
    reject_unchanged(&mut r,|r|r.finish_battle(b,finished(&s,b),0),Error::WrongReceipt);
}
#[test]fn benched_member_does_not_become_a_world_actor_and_is_released_by_one_shot_policy(){
    let(mut r,k)=populated(3);r.command(lease(1),Command::Assign{target:lease(3).account,roster:Roster::bench(Side::One)},0).unwrap();
    let s=prepare(&mut r);assert_eq!(s.members.len(),2);let b=BattleKey(46);r.commit_launch(k,s.ticket,b,reserves(&s,b),0).unwrap();
    assert!(r.claim(lease(3).account).is_none());assert_eq!(r.battle_snapshot(b).unwrap().members.len(),2);
}
#[test]fn late_ready_completion_cannot_retarget_new_room_or_override_newer_selection_settings(){
    let mut r=bound(2);let old=created(&mut r,2);r.command(lease(2),Command::Join(old),0).unwrap();
    let context=r.selection_context(lease(2)).unwrap();r.command(lease(2),Command::Leave,0).unwrap();
    let events=r.command(lease(2),Command::Create(settings(2)),0).unwrap();let new=match events[0]{Event::Created(k)=>k,_=>panic!()};assert_ne!(old,new);
    reject_unchanged(&mut r,|r|r.command(lease(2),Command::Ready{context,selection:reference(2,13)},0),Error::StaleSelection);
    let stale=r.selection_context(lease(2)).unwrap();r.command(lease(2),ready(&r,2,reference(2,14)),0).unwrap();
    reject_unchanged(&mut r,|r|r.command(lease(2),Command::Ready{context:stale,selection:reference(2,13)},0),Error::StaleSelection);
    let stale=r.selection_context(lease(2)).unwrap();let mut changed=settings(2);changed.map=QualifiedMap::Prohorovka;
    r.command(lease(2),Command::UpdateSettings(changed),0).unwrap();
    reject_unchanged(&mut r,|r|r.command(lease(2),Command::Ready{context:stale,selection:reference(2,14)},0),Error::StaleSelection);
    assert_eq!(r.room(new).unwrap().members[&lease(2).account].ready,Some(reference(2,14)));
}


// Explicit LAB policy: roster/settings retain only a previously checked opaque
// WriterReadyRef. These synthetic fixtures prove no writer ownership or CAS.
fn retained_refs(r:&Registry,k:RoomKey)->BTreeMap<Account,Option<WriterReadyRef>>{
    r.room(k).unwrap().members.iter().map(|(a,m)|(*a,m.ready.clone())).collect()
}
#[test]fn p10b_ready_preserve_ready_bench_to_three_vs_one_starts_without_another_ready(){
    let mut r=bound(4);let k=created(&mut r,4);
    for n in 2..=4{r.command(lease(n),Command::Join(k),0).unwrap();}
    r.command(lease(1),Command::Assign{target:lease(2).account,roster:Roster::assigned(Side::Two)},0).unwrap();
    r.command(lease(1),Command::Assign{target:lease(3).account,roster:Roster::assigned(Side::One)},0).unwrap();
    for n in 1..=4{r.command(lease(n),ready(&r,n,reference(n,13+u32::from(n))),0).unwrap();}
    assert_eq!(r.room(k).unwrap().members[&lease(4).account].roster,Roster::bench(Side::One));
    let refs=retained_refs(&r,k);let stale=r.selection_context(lease(4)).unwrap();
    r.command(lease(1),Command::TeamReady{side:Side::One,ready:true,force:false},0).unwrap();
    let revision=r.room(k).unwrap().revision;
    let ev=r.command(lease(1),Command::Assign{target:lease(4).account,roster:Roster::assigned(Side::One)},0).unwrap();
    assert_eq!(r.room(k).unwrap().revision,revision+1);assert_eq!(r.room(k).unwrap().team_ready,[false;2]);
    assert_eq!(retained_refs(&r,k),refs);assert_eq!(ev,vec![Event::RosterChanged{room:k,account:lease(4).account},Event::TeamsChanged(k)]);
    reject_unchanged(&mut r,|r|r.command(lease(4),Command::Ready{context:stale,selection:reference(4,90)},0),Error::StaleSelection);
    // No new Ready is issued after the bench move: both native team steps use
    // exactly the pre-existing owner/inventory/revision/fingerprint tuple.
    let snapshot=prepare(&mut r);assert_eq!(snapshot.members.len(),4);
    assert_eq!(snapshot.members.iter().filter(|m|m.side==Side::One).count(),3);
    assert_eq!(snapshot.members.iter().filter(|m|m.side==Side::Two).count(),1);
    for m in &snapshot.members{assert_eq!(Some(m.ready.clone()),refs[&m.account]);}
    let b=BattleKey(91);r.commit_launch(k,snapshot.ticket,b,reserves(&snapshot,b),0).unwrap();
    assert_eq!(r.battle_snapshot(b),Some(&snapshot));
}
#[test]fn p10b_ready_preserve_swap_and_settings_keep_exact_refs_but_fence_old_jobs_and_votes(){
    let(mut r,k)=populated(4);let refs=retained_refs(&r,k);
    let before_sides:BTreeMap<_,_>=r.room(k).unwrap().members.iter().map(|(a,m)|(*a,m.roster)).collect();
    r.command(lease(1),Command::TeamReady{side:Side::One,ready:true,force:false},0).unwrap();
    let stale=r.selection_context(lease(2)).unwrap();let revision=r.room(k).unwrap().revision;
    r.command(lease(1),Command::SwapTeams,0).unwrap();
    assert_eq!(retained_refs(&r,k),refs);assert_eq!(r.room(k).unwrap().revision,revision+1);assert_eq!(r.room(k).unwrap().team_ready,[false;2]);
    for(a,m)in &r.room(k).unwrap().members{assert_eq!(m.roster.side,before_sides[a].side.other());assert_eq!(m.roster.assigned,before_sides[a].assigned);}
    reject_unchanged(&mut r,|r|r.command(lease(2),Command::Ready{context:stale,selection:reference(2,90)},0),Error::StaleSelection);
    r.command(lease(1),Command::TeamReady{side:Side::Two,ready:true,force:false},0).unwrap();
    let stale=r.selection_context(lease(3)).unwrap();let revision=r.room(k).unwrap().revision;
    let mut changed=settings(6);changed.map=QualifiedMap::Prohorovka;changed.seconds=1800;changed.opened=false;changed.comment="retained checked refs".into();
    r.command(lease(1),Command::UpdateSettings(changed.clone()),0).unwrap();
    assert_eq!(r.room(k).unwrap().settings,changed);assert_eq!(r.room(k).unwrap().revision,revision+1);assert_eq!(r.room(k).unwrap().team_ready,[false;2]);assert_eq!(retained_refs(&r,k),refs);
    reject_unchanged(&mut r,|r|r.command(lease(3),Command::Ready{context:stale,selection:reference(3,90)},0),Error::StaleSelection);
    let snapshot=prepare(&mut r);for m in snapshot.members{assert_eq!(Some(m.ready),refs[&m.account]);}
}
#[test]fn p10b_ready_preserve_never_invents_ready_and_keeps_explicit_clear_and_failure_atomicity(){
    let(mut r,k)=populated(6);let refs=retained_refs(&r,k);
    r.command(lease(1),Command::TeamReady{side:Side::One,ready:true,force:false},0).unwrap();
    reject_unchanged(&mut r,|r|r.command(lease(1),Command::Assign{target:lease(2).account,roster:Roster::assigned(Side::One)},0),Error::InvalidTeam);
    reject_unchanged(&mut r,|r|r.command(lease(2),Command::SwapTeams,0),Error::NotCreator);
    let mut invalid=settings(6);invalid.comment="x".repeat(65);
    reject_unchanged(&mut r,|r|r.command(lease(1),Command::UpdateSettings(invalid),0),Error::BadSettings);
    assert_eq!(retained_refs(&r,k),refs);
    r.command(lease(2),Command::NotReady,0).unwrap();assert!(r.room(k).unwrap().members[&lease(2).account].ready.is_none());
    r.command(lease(1),Command::SwapTeams,0).unwrap();r.command(lease(1),Command::UpdateSettings(settings(6)),0).unwrap();
    r.command(lease(1),Command::Assign{target:lease(2).account,roster:Roster::bench(Side::One)},0).unwrap();
    r.command(lease(1),Command::Assign{target:lease(2).account,roster:Roster::assigned(Side::One)},0).unwrap();
    assert!(r.room(k).unwrap().members[&lease(2).account].ready.is_none());
    reject_unchanged(&mut r,|r|r.command(lease(1),Command::TeamReady{side:Side::One,ready:true,force:true},0),Error::NotReady);
    let mut next=reference(2,99);next.fingerprint=[71;32];
    r.command(lease(2),ready(&r,2,next.clone()),0).unwrap();
    for n in[1,3,4,5,6]{assert_eq!(r.room(k).unwrap().members[&lease(n).account].ready,refs[&lease(n).account]);}
    assert_eq!(r.room(k).unwrap().members[&lease(2).account].ready,Some(next));
    let snapshot=prepare(&mut r);r.command(lease(6),Command::Leave,0).unwrap();
    r.abort_launch(k,snapshot.ticket,released(&snapshot),0).unwrap();
    assert!(r.room(k).unwrap().members.values().all(|m|m.ready.is_none()));assert_eq!(r.room(k).unwrap().team_ready,[false;2]);
}
