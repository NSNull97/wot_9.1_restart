use super::*;
fn member(i:u32)->Member{Member{entity_id:150994945+i,database_id:i as i32,name:format!("Player{i}"),roster:if i==1{1}else{17},state:PlayerState::NotReady,
    joined_seconds:1000.,descriptor:Vec::new(),igr_type:0,clan_database_id:0,clan_abbrev:String::new()}}
fn room(n:u32)->RoomView{RoomView{room_id:117,creator_database_id:1,map:SourceMap::Prohorovka,seconds:600,opened:true,comment:"bounded".into(),
    members:(1..=n).map(member).collect(),team_states:[TeamState::NotReady;2]}}
fn queues(r:&RoomView)->BTreeMap<u32,VecDeque<Body>>{r.members.iter().map(|m|(m.entity_id,VecDeque::new())).collect()}
fn raw(body:&[u8])->&[u8]{assert_eq!(&body[..2],&[0x13,0x56]);assert_eq!(body[2]as usize,body.len()-3);assert_eq!(body[4]as usize,body.len()-5);&body[5..]}
fn hex(s:&str)->Vec<u8>{(0..s.len()).step_by(2).map(|i|u8::from_str_radix(&s[i..i+2],16).unwrap()).collect()}

#[test]fn plain_three_argument_callback_has_source_exact_literal_envelope_not_ext(){
    assert_eq!(plain_response(221,CommandResult::Success,"").unwrap(),hex("134c05dd00000000"));
    assert_eq!(plain_response(32767,CommandResult::Unavailable,"").unwrap(),hex("134c05ff7ff6ff00"));
    assert_eq!(plain_response(221,CommandResult::WrongArgs,"ARG").unwrap(),hex("134c08dd00feff03415247"));
    for id in[-1,0,200,201,202,220]{assert_eq!(plain_response(id,CommandResult::Success,"").unwrap_err(),Error::Request);}
    assert!(plain_response(221,CommandResult::Failure,&"x".repeat(65)).is_err());assert!(plain_response(221,CommandResult::Failure,"bad\n").is_err());
}
#[test]fn fixed_callbacks_and_source_update_literals_match_independently_authored_bytes(){
    assert_eq!(joined(117).unwrap(),hex("134675000000"));assert_eq!(left(),hex("133c"));
    assert_eq!(team_states([TeamState::NotReady;2]).unwrap(),hex("13560b06098002284b014b01742e"));
    let init=initialization(&room(2),150994946).unwrap();
    // Exact literals independently preserved in prior source research. These
    // are authored framing vectors, NOT an observed original native packet.
    assert_eq!(init[1],hex("135610070e80027d285504747970654b02752e"));
    assert_eq!(init[2],hex("1356170815800228550c6172656e61477569547970654b02742e"));
    assert_eq!(init[3],hex("1356160814800228550b6172656e615479706549444b04742e"));
    assert_eq!(init[4],hex("1356170815800228550b726f756e644c656e6774684d5802742e"));
    assert_eq!(init[12],hex("1356180816800228550d64656661756c74526f737465724b11742e"));
}
#[test]fn initialization_two_to_six_preserves_join_settings_team_own_roster_barrier_peer_order(){
    for n in 2..=6{let r=room(n);for own in &r.members{let b=initialization(&r,own.entity_id).unwrap();assert_eq!(b.len(),21+n as usize);
        assert_eq!(b[0],joined(r.room_id).unwrap());assert_eq!(b[1][3],7);
        assert!(b[2..20].iter().all(|b|b[3]==8));assert_eq!(b[20][3],6);assert_eq!(b[21][3],1);assert!(b[22..].iter().all(|b|b[3]==2));
        assert!(raw(&b[21]).starts_with(b"\x80\x02]((J"));
        for b in &b[1..]{assert!(b[2]<=254);assert!(raw(b).starts_with(&[0x80,2]));assert_eq!(*raw(b).last().unwrap(),b'.');}
        let mut out=queues(&r);stage_initializations(&mut out,&r).unwrap();assert_eq!(out[&own.entity_id].iter().cloned().collect::<Vec<_>>(),b);
    }}
}
#[test]fn utf8_names_full_i32_identifiers_and_largest_bounded_descriptors_stay_in_short_payloads(){
    let mut r=room(6);r.comment="Ж".repeat(32);r.creator_database_id=i32::MAX;
    for(i,m)in r.members.iter_mut().enumerate(){m.name="Ж".repeat(24);m.database_id=i32::MAX-i as i32;m.entity_id=i32::MAX as u32-i as u32;
        m.descriptor=vec![0xab;64];m.state=PlayerState::Ready;m.clan_database_id=i32::MAX;m.clan_abbrev="ABCDEFGH".into();m.igr_type=2;m.joined_seconds=1e12;}
    let mut max=0;for own in &r.members{for b in initialization(&r,own.entity_id).unwrap().into_iter().skip(1){max=max.max(b[2]);assert!(b[2]<=254);}}
    assert_eq!(max,169,"bounded stress fixture maximum, not native observation");
    let mut n=member(1);n.name="💩".repeat(12);assert_eq!(n.name.len(),48);assert!(player_added(&n).is_ok());n.name.push('x');assert_eq!(player_added(&n).unwrap_err(),Error::Identity);
}
#[test]fn actual_late_poison_and_full_last_recipient_roll_back_every_staged_outbox(){
    let mut r=room(6);let mut out=queues(&r);for queue in out.values_mut(){queue.push_back(vec![0x13,0x3c]);}let before=out.clone();
    r.members.last_mut().unwrap().descriptor=vec![1;65];assert_eq!(stage_initializations(&mut out,&r).unwrap_err(),Error::Descriptor);assert_eq!(out,before);
    r.members.last_mut().unwrap().descriptor.clear();let last=r.members.last().unwrap().entity_id;
    out.get_mut(&last).unwrap().extend((0..101).map(|_|vec![1]));let before=out.clone();
    assert_eq!(stage_initializations(&mut out,&r).unwrap_err(),Error::QueueFull);assert_eq!(out,before);
    out.get_mut(&last).unwrap().clear();out.get_mut(&last).unwrap().push_back(vec![1;65536]);let before=out.clone();
    assert_eq!(stage_initializations(&mut out,&r).unwrap_err(),Error::QueueFull);assert_eq!(out,before);
}
#[test]fn duplicate_namespaces_foreign_recipient_and_invalid_source_shapes_are_rejected(){
    for n in[0,7]{assert!(initialization(&room(n),150994946).is_err());}
    let mut r=room(2);r.members[1].entity_id=r.members[0].entity_id;assert_eq!(initialization(&r,r.members[0].entity_id).unwrap_err(),Error::Duplicate);
    let mut r=room(2);r.members[1].database_id=1;assert_eq!(initialization(&r,r.members[0].entity_id).unwrap_err(),Error::Duplicate);
    let mut r=room(2);r.creator_database_id=99;assert_eq!(initialization(&r,r.members[0].entity_id).unwrap_err(),Error::MissingOwner);
    let r=room(2);assert_eq!(initialization(&r,1).unwrap_err(),Error::NoRecipient);
    let mut out=queues(&r);out.remove(&r.members[1].entity_id);let before=out.clone();assert_eq!(stage_initializations(&mut out,&r).unwrap_err(),Error::NoRecipient);assert_eq!(out,before);
    for id in[0,i32::MAX as u32+1,u32::MAX]{assert!(joined(id).is_err());}
    let mut m=member(1);m.roster=3;assert_eq!(player_added(&m).unwrap_err(),Error::Roster);m.roster=17;m.state=PlayerState::Ready;assert_eq!(player_state(&m).unwrap_err(),Error::Descriptor);
    m.descriptor=vec![1];m.joined_seconds=f64::NAN;assert_eq!(player_added(&m).unwrap_err(),Error::Identity);
}
#[test]fn seven_field_state_and_assignment_removal_literals_have_exact_source_tuple_order(){
    let mut m=member(1);m.entity_id=1;m.roster=2;m.state=PlayerState::Ready;m.descriptor=vec![1,2];m.igr_type=2;m.clan_database_id=4;m.clan_abbrev="TAG".into();
    assert_eq!(raw(&player_state(&m).unwrap()),hex("8002284b014b024b04550201024b024b045503544147742e"));
    assert_eq!(raw(&player_removed(1,17).unwrap()),hex("8002284b014b11742e"));
    assert_eq!(raw(&roster_changed(1,17,2,9).unwrap()),hex("8002284b014b114b024b09742e"));
    assert!(roster_changed(0,17,2,9).is_err());assert!(roster_changed(1,3,2,9).is_err());
}
#[test]fn primitive_budget_rejects_oversize_before_native_ff_sentinel(){
    assert_eq!(update(1,|p|p.raw(&[1;254])).unwrap_err(),Error::Bound);
    let exact=update(1,|p|p.raw(&[1;249])).unwrap();assert_eq!(exact[2],254);assert_ne!(exact[2],255);
    assert_eq!(update(1,|p|p.raw(&[1;250])).unwrap_err(),Error::Bound);
    assert_eq!(update(0,|_|Ok(())).unwrap_err(),Error::Bound);
}
