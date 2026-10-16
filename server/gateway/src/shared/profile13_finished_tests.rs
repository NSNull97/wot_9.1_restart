use super::*;
fn owner(n:u8)->Account{Account([n;16])}
fn batch()->FinishedEvents{let mut q=FinishedEvents::default();q.begin(BattleKey(9007199254740993)).unwrap();q}
#[test]fn p10b_finished_default_unarmed_and_uuid_are_bounded(){
    let q=FinishedEvents::default();assert_eq!(q.battle(),None);
    assert!(q.staged(owner(1),"reservation:1",BattleKey(1)).is_err());
    assert!(account("00000000-0000-0000-0000-000000000000").is_err());
    assert!(account("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa").is_ok());
    for v in ["AAAAAAAA-aaaa-aaaa-aaaa-aaaaaaaaaaaa","aaaaaaaa_aaaa-aaaa-aaaa-aaaaaaaaaaaa","a"]{assert!(account(v).is_err());}
}
#[test]fn p10b_finished_six_exact_receipts_and_replays_after_take_stay_once(){
    let mut q=batch();let battle=q.battle().unwrap();
    for n in 1..=6{q=q.staged(owner(n),&format!("reservation:{n}"),battle).unwrap();}
    assert_eq!(q.pending.len(),6);
    assert!(q.staged(owner(7),"reservation:7",battle).is_err());
    let first=q.take().unwrap();
    q=q.staged(owner(1),"reservation:1",battle).unwrap();assert_eq!(q.pending.len(),5);
    assert!(!q.pending.contains(&first));
    while q.take().is_some(){}
    q.begin(battle).unwrap();
    for n in 1..=6{q=q.staged(owner(n),&format!("reservation:{n}"),battle).unwrap();}
    assert!(q.take().is_none());assert_eq!(q.seen.len(),6);
}
#[test]fn p10b_finished_conflicts_and_invalid_reference_fail_before_any_mutation(){
    let q=batch();let battle=q.battle().unwrap();let q=q.staged(owner(1),"reservation:1",battle).unwrap();
    for (o,r,b) in [(owner(1),"reservation:other",battle),(owner(2),"reservation:1",battle),
        (owner(2),"bad key",battle),(owner(0),"reservation:2",battle),(owner(2),"reservation:2",BattleKey(7))]{
        assert!(q.staged(o,r,b).is_err());assert_eq!(q.seen.len(),1);assert_eq!(q.pending.len(),1);
    }
}
#[test]fn p10b_finished_battle_change_needs_drain_and_rejects_old_receipt(){
    let q=batch();let old=q.battle().unwrap();let mut q=q.staged(owner(1),"reservation:1",old).unwrap();
    assert!(q.begin(BattleKey(7)).is_err());assert_eq!(q.battle(),Some(old));assert_eq!(q.pending.len(),1);
    q.take().unwrap();q.begin(BattleKey(7)).unwrap();
    assert!(q.staged(owner(1),"reservation:1",old).is_err());assert!(q.seen.is_empty());assert!(q.pending.is_empty());
}
#[test]fn p10b_finished_staging_rollback_keeps_receipt_available_for_delivery_retry(){
    let q=batch();let battle=q.battle().unwrap();let staged=q.staged(owner(1),"reservation:1",battle).unwrap();
    // A failed actual Session delivery discards staged; source queue stays empty.
    assert!(q.pending.is_empty());assert!(q.seen.is_empty());drop(staged);
    let mut committed=q.staged(owner(1),"reservation:1",battle).unwrap();
    assert_eq!(committed.take(),Some(FinishedRef::from_verified_writer(owner(1),"reservation:1".into(),battle).unwrap()));
    assert!(committed.take().is_none());
}
