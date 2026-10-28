use super::*;
fn visible(book:&mut Book,slot:usize,epoch:u32){book.set_visibility(slot,Some(epoch),true,true,true).unwrap();}
fn action(book:&Book,kind:ActionKind,slot:usize)->Action{book.transitions().into_iter().find(|a|a.kind==kind&&a.slot==slot).unwrap()}
fn created()->Book{let mut b=Book::new();visible(&mut b,1,0);b.mark_queued(action(&b,ActionKind::Enter,1),0).unwrap();
    assert_eq!(b.on_request(1).unwrap(),RequestDisposition::Queued);b.mark_queued(action(&b,ActionKind::Create,1),1).unwrap();b}

#[test]fn p06t_detached_source_create_has_type8_four_indexed_properties_and_actual_parent_descriptor(){
    let p=Pose{position:[1.,2.,3.],direction:[0.,0.,0.]};
    for kind in VehicleKind::ALL{for slot in 0..MAX_TURRETS{
        let b=create(slot,kind,p,false,true).unwrap();assert_eq!(b.len(),61);
        assert_eq!(&b[..4],&[9,58,0,0]);
        assert_eq!(u32::from_le_bytes(b[4..8].try_into().unwrap()),0x0912_0001+slot as u32);
        assert_eq!(&b[8..10],&[8,0]); // source client index8, never raw ordinal42
        assert_eq!(&b[34..40],&[4,0,0,1,1,2]);
        assert_eq!(u32::from_le_bytes(b[40..44].try_into().unwrap()),super::super::wire::vehicle_id(slot).unwrap());
        assert_eq!(&b[44..46],&[3,15]);assert_eq!(&b[46..],kind.descriptor());
    }}
}
#[test]fn p06t_detached_native_literals_enter_pose_leave_keep_generic_formats(){
    assert_eq!(enter(0).unwrap(),[10,1,0,18,9,248]);
    assert_eq!(leave(5).unwrap(),[12,4,0,6,0,18,9]);
    let v=Pose{position:[1.,2.,3.],direction:[0.5,0.25,-0.5]};let b=pose(0,1000,v).unwrap();
    let expected=[13,232,21,1,0,18,9,0,0,128,63,0,0,0,64,0,0,64,64,
        0,0,0,191,0,0,128,62,0,0,0,63];
    assert_eq!(b,expected); // independent f32 bits; volatile order roll,pitch,yaw
    let mut req=vec![8,4,0];req.extend(0x0912_0006u32.to_le_bytes());assert_eq!(request(&req).unwrap(),Some(5));
    assert_eq!(request(&[8,4,0,3,0,16,9]).unwrap(),None);
}
#[test]fn p06t_detached_terminal_health_and_fx_are_separate_source_fixed_methods(){
    assert_eq!(terminal_health(0,Some(1),0,DeathKind::Detached).unwrap(),
        [18,3,0,16,9,161,254,255,60,254,255,5,0,16,9,0,19]);
    assert_eq!(terminal_health(0,None,1,DeathKind::Exploded).unwrap(),
        [18,3,0,16,9,161,255,255,60,255,255,0,0,0,0,1,19]);
    assert_eq!(explosion(0,1.,2.).unwrap(),[18,3,0,16,9,61,0,0,128,63,0,0,0,64,19]);
}
#[test]fn p06t_detached_codec_rejects_poison_without_arbitrary_type_parent_or_float_fields(){
    let p=Pose{position:[0.;3],direction:[0.;3]};
    for slot in [MAX_TURRETS,usize::MAX]{assert!(entity_id(slot).is_err());assert!(alias(slot).is_err());assert!(enter(slot).is_err());assert!(leave(slot).is_err());
        assert!(create(slot,VehicleKind::Ms1,p,false,false).is_err());assert!(pose(slot,1000,p).is_err());}
    for raw in [&[8][..],&[8,4,0][..],&[8,3,0,1,0,18,9][..],&[8,4,0,1,0,18,9,0][..]]{assert!(request(raw).is_err());}
    for n in [f32::NAN,f32::INFINITY,2000.1]{let mut bad=p;bad.position[0]=n;assert!(create(0,VehicleKind::Ms1,bad,false,false).is_err());}
    for n in [f32::NAN,PI+0.001]{let mut bad=p;bad.direction[0]=n;assert!(pose(0,1000,bad).is_err());}
    for tick in [0,999,37001,u32::MAX]{assert!(pose(0,tick,p).is_err());}
    assert!(terminal_health(0,Some(super::super::wire::MAX_WIRE_ACTORS),0,DeathKind::Detached).is_err());assert!(terminal_health(0,None,11,DeathKind::Detached).is_err());
    for(v,s)in [(f32::NAN,0.),(-1.,0.),(0.,-1.),(0.,1001.)]{assert!(explosion(0,v,s).is_err());}
}
#[test]fn p06t_detached_ids_and_aliases_are_disjoint_from_all_six_vehicles_and144_areas(){
    let mut ids=std::collections::BTreeSet::new();let mut aliases=std::collections::BTreeSet::new();
    for slot in 0..6{ids.insert(super::super::wire::vehicle_id(slot).unwrap());ids.insert(super::super::wire::avatar_id(slot).unwrap());
        aliases.insert(super::super::wire::vehicle_alias(slot).unwrap());}
    for area in 0..144{assert!(ids.insert(super::super::destructible_wire::area_id(area).unwrap()));assert!(aliases.insert(2+area as u8));}
    for slot in 0..6{assert!(ids.insert(entity_id(slot).unwrap()));assert!(aliases.insert(alias(slot).unwrap()));}
}
#[test]fn p06t_detached_book_requires_actual_request_and_create_ack_with_sequence_zero_valid(){
    let mut b=Book::new();visible(&mut b,1,0);assert_eq!(b.on_request(1).unwrap(),RequestDisposition::Stale);
    assert!(!b.pose_allowed(1));let enter=action(&b,ActionKind::Enter,1);b.mark_queued(enter,0).unwrap();
    let before=b.clone();b.mark_queued(enter,0).unwrap();assert_eq!(b,before);assert!(b.propose().is_none());
    assert_eq!(b.on_request(1).unwrap(),RequestDisposition::Queued);assert_eq!(b.on_request(1).unwrap(),RequestDisposition::Duplicate);
    let create=action(&b,ActionKind::Create,1);let before=b.clone();assert!(b.mark_queued(create,0).is_err());assert_eq!(b,before);
    b.mark_queued(create,1).unwrap();assert!(!b.pose_allowed(1));assert_eq!(b.on_request(1).unwrap(),RequestDisposition::Duplicate);
    b.ack(1,&[0]).unwrap();assert!(!b.pose_allowed(1));b.ack(1,&[1]).unwrap();assert!(b.pose_allowed(1));
    let before=b.clone();b.mark_queued(create,1).unwrap();assert_eq!(b,before);assert!(b.propose().is_none());
}
#[test]fn p06t_detached_book_parent_epoch_and_rapid_hide_reveal_never_reuse_creation_ack(){
    let mut b=created();b.ack(2,&[]).unwrap();assert!(b.pose_allowed(1));
    b.set_visibility(1,Some(0),true,true,false).unwrap();assert!(!b.pose_allowed(1));
    let stale=action(&b,ActionKind::Leave,1);visible(&mut b,1,0);let before=b.clone();
    assert!(b.mark_queued(stale,2).is_err());assert_eq!(b,before);assert!(b.pose_allowed(1));
    // Even while visible, a new parent announcement epoch requires a complete
    // leave/ACK/reenter/request/create/ACK cycle of the detached child.
    visible(&mut b,1,20);assert!(!b.pose_allowed(1));assert_eq!(b.on_request(1).unwrap(),RequestDisposition::Stale);
    let leave=action(&b,ActionKind::Leave,1);b.mark_queued(leave,2).unwrap();
    for yes in [false,true,false,true]{b.set_visibility(1,Some(20),true,yes,yes).unwrap();assert!(b.propose().is_none());}
    b.ack(2,&[1]).unwrap();assert_eq!(b.entry(1),Some(Entry::Leaving{leave_seq:2}));
    assert_eq!(b.ack(2,&[2]).unwrap(),[1]);let enter=action(&b,ActionKind::Enter,1);
    assert!(b.mark_queued(enter,2).is_err());b.mark_queued(enter,3).unwrap();
    assert!(!b.pose_allowed(1));b.on_request(1).unwrap();b.mark_queued(action(&b,ActionKind::Create,1),4).unwrap();
    b.ack(4,&[1,2,3]).unwrap();assert!(!b.pose_allowed(1));b.ack(4,&[4]).unwrap();assert!(b.pose_allowed(1));
}
#[test]fn p06t_detached_book_failed_queue_bounds_and_six_targets_remain_atomic(){
    let mut b=Book::new();let empty=b.clone();assert!(b.set_visibility(MAX_TURRETS,Some(0),true,true,true).is_err());assert_eq!(b,empty);
    assert!(b.set_visibility(0,None,true,true,true).is_err());assert_eq!(b,empty);
    for slot in 0..6{visible(&mut b,slot,0);}let actions=b.transitions();assert_eq!(actions.len(),6);
    let unqueued=b.clone();assert_eq!(b.transitions(),actions);assert_eq!(b,unqueued); // failed enqueue has no book effect
    for a in actions{b.mark_queued(a,0).unwrap();}
    for slot in 0..6{assert_eq!(b.on_request(slot).unwrap(),RequestDisposition::Queued);}
    for a in b.transitions(){b.mark_queued(a,1).unwrap();}b.ack(2,&[]).unwrap();
    for slot in 0..6{assert!(b.pose_allowed(slot));}
    let before=b.clone();assert!(b.ack(3,&vec![1;257]).is_err());assert_eq!(b,before);
    assert!(b.on_request(MAX_TURRETS).is_err());assert_eq!(b,before);assert!(!b.pose_allowed(MAX_TURRETS));
    // Outer receive staging: no mutation escapes when a later operation fails.
    let mut staged=b.clone();staged.set_visibility(1,Some(0),true,false,false).unwrap();
    staged.mark_queued(action(&staged,ActionKind::Leave,1),2).unwrap();assert!(staged.on_request(MAX_TURRETS).is_err());assert_eq!(b,before);
}
