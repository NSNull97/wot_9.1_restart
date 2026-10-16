use super::*;
fn c(n:u8)->Canonical{Canonical{account:[n;16],auth_generation:1}}
fn m(n:u8,j:u64)->Membership{Membership{canonical:c(n),join_generation:j}}
fn alias(b:&[Binding],n:u8)->u32{b.iter().find(|b|b.member.canonical==c(n)).unwrap().alias}
#[test]fn own_fixed_and_unique_peer_aliases_are_stable_for_two_to_six_members(){
    for n in 2..=6{let current:Vec<_>=(1..=n).map(|n|m(n,n as u64)).collect();for own in &current{let mut book=Book::new(own.canonical).unwrap();
        let bindings=book.stage_view(17,&current).unwrap();assert_eq!(bindings.iter().find(|b|b.member==*own).unwrap().alias,OWN_ENTITY_ID);
        assert_eq!(bindings.iter().map(|b|b.alias).collect::<BTreeSet<_>>().len(),n as usize);assert_eq!(book.stage_view(17,&current).unwrap(),bindings);
        for peer in &bindings{if peer.member!=*own{assert_eq!(book.resolve_peer(17,peer.alias,&current).unwrap(),peer.member);}}
    }}
}
#[test]fn departed_alias_never_targets_a_new_peer_even_before_removed_update_is_published(){
    let mut book=Book::new(c(1)).unwrap();let old=book.stage_view(11,&[m(1,1),m(2,2)]).unwrap();let old_alias=alias(&old,2);
    let current=[m(1,1),m(3,3)];assert_eq!(book.resolve_peer(11,old_alias,&current).unwrap_err(),Error::StaleAlias);
    let new=book.stage_view(11,&current).unwrap();assert!(alias(&new,3)>old_alias);assert_eq!(book.resolve_peer(11,old_alias,&current).unwrap_err(),Error::StaleAlias);
}
#[test]fn same_peer_same_auth_and_room_rejoin_between_publications_requires_fresh_join_generation(){
    let mut book=Book::new(c(1)).unwrap();let old=book.stage_view(11,&[m(1,1),m(2,2)]).unwrap();let old_alias=alias(&old,2);
    let current=[m(1,1),m(2,99)];assert_eq!(book.resolve_peer(11,old_alias,&current).unwrap_err(),Error::StaleAlias);
    let new=book.stage_view(11,&current).unwrap();assert!(alias(&new,2)>old_alias);
    assert_eq!(book.resolve_peer(11,old_alias,&current).unwrap_err(),Error::StaleAlias);
}
#[test]fn recipient_rejoin_or_room_change_does_not_resurrect_unchanged_peer_binding(){
    let mut book=Book::new(c(1)).unwrap();let old=book.stage_view(11,&[m(1,1),m(2,2)]).unwrap();let first=alias(&old,2);
    let current=[m(1,3),m(2,2)];assert_eq!(book.resolve_peer(11,first,&current).unwrap_err(),Error::StaleAlias);
    let second=alias(&book.stage_view(11,&current).unwrap(),2);assert!(second>first);
    let third=alias(&book.stage_view(12,&current).unwrap(),2);assert!(third>second);
    let fourth=alias(&book.stage_view(11,&current).unwrap(),2);assert!(fourth>third);
    book.leave_room();let fifth=alias(&book.stage_view(11,&current).unwrap(),2);assert!(fifth>fourth);
}
#[test]fn changed_auth_generation_retires_peer_target_and_self_target_is_explicitly_unsupported(){
    let mut book=Book::new(c(1)).unwrap();let old=book.stage_view(11,&[m(1,1),m(2,2)]).unwrap();let old_alias=alias(&old,2);
    let mut peer=m(2,3);peer.canonical.auth_generation=2;let current=[m(1,1),peer];
    assert_eq!(book.resolve_peer(11,old_alias,&current).unwrap_err(),Error::StaleAlias);
    assert_eq!(book.resolve_peer(11,OWN_ENTITY_ID,&current).unwrap_err(),Error::SelfTargetUnsupported);
    let new=book.stage_view(11,&current).unwrap();assert!(new[1].alias>old_alias);
}
#[test]fn exhaustion_is_bounded_explicit_and_rolls_back_whole_alias_batch(){
    let mut book=Book::new(c(1)).unwrap();for i in 1..=MAX_ALIASES{book.stage_view(1,&[m(1,1),m(2,i as u64)]).unwrap();}
    assert_eq!(book.entries.len(),MAX_ALIASES);let before=book.clone();assert_eq!(book.stage_view(1,&[m(1,1),m(2,9999)]).unwrap_err(),Error::Exhausted);assert_eq!(book,before);
    assert!(book.stage_view(1,&[m(1,1),m(2,MAX_ALIASES as u64)]).is_ok()); // same active mapping uses no new capacity
    book.leave_room();let before=book.clone();assert_eq!(book.stage_view(1,&[m(1,1),m(2,MAX_ALIASES as u64)]).unwrap_err(),Error::Exhausted);assert_eq!(book,before);
}
#[test]fn duplicate_account_wrong_self_missing_self_zero_room_and_large_roster_reject_atomically(){
    let mut book=Book::new(c(1)).unwrap();let before=book.clone();
    assert_eq!(book.stage_view(1,&[m(2,2)]).unwrap_err(),Error::MissingOwn);assert_eq!(book,before);
    assert_eq!(book.stage_view(0,&[m(1,1)]).unwrap_err(),Error::Room);assert_eq!(book,before);
    assert_eq!(book.stage_view(1,&[m(1,1),m(1,2)]).unwrap_err(),Error::Members);assert_eq!(book,before);
    let many:Vec<_>=(1..=7).map(|i|m(i,i as u64)).collect();assert_eq!(book.stage_view(1,&many).unwrap_err(),Error::Members);assert_eq!(book,before);
    let mut wrong=m(1,1);wrong.canonical.auth_generation=2;assert_eq!(book.stage_view(1,&[wrong]).unwrap_err(),Error::MissingOwn);assert_eq!(book,before);
}
