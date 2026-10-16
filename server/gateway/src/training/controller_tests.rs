//! Component inputs are authored metadata, NOT real writer/Session/native proof.
use super::*;
fn lease(n:u8)->d::AuthLease{d::AuthLease{account:d::Account([n;16]),generation:1}}
fn call(n:u8)->Call{Call{caller:lease(n),channel:current::Channel{session:u32::from(n),generation:1},profile:current::ProfileStamp{revision:13,source_binding:[17;32]},expected_revision:13}}
fn fixture(n:u8)->(Controller,BTreeMap<d::Account,adapter::NativeFacts>){
    let mut c=Controller::default();let mut facts=BTreeMap::new();for n in 1..=n{c.bind(lease(n),call(n).channel,format!("Player{n}"),i32::from(n),0).unwrap();
        facts.insert(lease(n).account,adapter::NativeFacts{database_id:i32::from(n),selected:None,descriptor:Vec::new(),igr_type:0,clan_database_id:0,clan_abbrev:String::new()});}(c,facts)
}
fn request(id:i16,command:i16,a:i64,b:i32)->i::Request{
    let mut raw=vec![0x8e,20,0];raw.extend(id.to_le_bytes());raw.extend(command.to_le_bytes());raw.extend(a.to_le_bytes());raw.extend(b.to_le_bytes());raw.extend(0i32.to_le_bytes());i::record(&raw).unwrap().unwrap()
}
fn create(map:i32,opened:bool,comment:&[u8])->i::Request{
    let mut raw=Vec::new();raw.extend(map.to_le_bytes());raw.extend(600i32.to_le_bytes());raw.push(u8::from(opened));raw.push(comment.len()as u8);raw.extend(comment);
    let mut packet=vec![0x9a];packet.extend((raw.len()as u16).to_le_bytes());packet.extend(raw);i::record(&packet).unwrap().unwrap()
}
fn room(c:&mut Controller,facts:&BTreeMap<d::Account,adapter::NativeFacts>,n:u8,opened:bool)->(d::RoomKey,u32){
    c.apply(call(n),create(4,opened,b"source-bound"),facts,0).unwrap();let key=c.registry.authenticated_room(lease(n)).unwrap();(key,c.native_room(key).unwrap())
}
fn joined(n:u8)->(Controller,BTreeMap<d::Account,adapter::NativeFacts>,d::RoomKey,u32){
    let(mut c,facts)=fixture(n);let(key,native)=room(&mut c,&facts,1,true);
    for who in 2..=n{c.apply(call(who),request(202,400,i64::from(native),0),&facts,0).unwrap();}(c,facts,key,native)
}
fn ready(c:&mut Controller,facts:&mut BTreeMap<d::Account,adapter::NativeFacts>,who:u8)->d::WriterReadyRef{
    let batch=c.apply(call(who),request(221,402,1,0),facts,0).unwrap();assert!(batch.bodies.is_empty());assert_eq!(batch.ready.len(),1);
    let selected=d::WriterReadyRef::from_verified_writer(lease(who).account,format!("fixture-owned-{who}"),13,[who;32]).unwrap();
    let f=facts.get_mut(&lease(who).account).unwrap();f.selected=Some(selected.clone());f.descriptor=vec![who,2,3];
    c.complete_ready(&batch.ready[0],call(who),1,selected.clone(),facts,0).unwrap();selected
}
fn prepared()->(Controller,BTreeMap<d::Account,adapter::NativeFacts>,PrepareTask){
    let(mut c,mut facts,_,_)=joined(2);let peer=c.recipients[&lease(1).account].last.as_ref().unwrap().rows[&lease(2).account].entity_id;
    c.apply(call(1),request(222,404,i64::from(peer),2),&facts,0).unwrap();ready(&mut c,&mut facts,1);ready(&mut c,&mut facts,2);
    let first=c.apply(call(1),request(223,411,1,0),&facts,0).unwrap();assert_eq!(first.bodies[&lease(1).account][0],w::plain_response(223,w::CommandResult::Success,"").unwrap());
    let last=c.apply(call(1),request(224,411,2,0),&facts,0).unwrap();assert_eq!(last.prepare.len(),1);
    assert!(!last.bodies.values().flatten().any(|b|b.get(..2)==Some(&[0x13,0x4c])));(c,facts,last.prepare[0].clone())
}
fn reserve(task:&PrepareTask,battle:d::BattleKey)->Vec<d::ReservedRef>{task.snapshot.members().iter().map(|m|
    d::ReservedRef::from_verified_writer(m.ready().clone(),format!("fixture-reserve:{}",m.account().0[0]),battle,task.snapshot.ticket()).unwrap()).collect()}
fn releases(task:&PrepareTask)->Vec<d::ReleasedRef>{task.snapshot.members().iter().map(|m|d::ReleasedRef::from_verified_writer(m.ready().clone(),task.snapshot.ticket()).unwrap()).collect()}
fn denied(c:&mut Controller,who:u8,request:i::Request,facts:&BTreeMap<d::Account,adapter::NativeFacts>){let before=c.clone();assert!(c.apply(call(who),request,facts,0).is_err());assert_eq!(*c,before);}

#[test]fn p10b_controller_create_join_and_mutation_publish_incremental_peers_without_repeated_joined(){
    let(mut c,facts)=fixture(2);let(key,native)=room(&mut c,&facts,1,true);
    let batch=c.apply(call(2),request(202,400,i64::from(native),0),&facts,0).unwrap();
    assert_eq!(&batch.bodies[&lease(2).account][0][..2],&[0x13,0x46]);
    assert!(!batch.bodies[&lease(1).account].iter().any(|b|b.starts_with(&[0x13,0x46])));
    assert!(batch.bodies[&lease(1).account].iter().any(|b|b.starts_with(&[0x13,0x56])&&b[3]==2));
    let batch=c.apply(call(1),request(221,404,i64::from(aliases::OWN_ENTITY_ID),2),&facts,0).unwrap();
    assert_eq!(c.registry.room(key).unwrap().members().find(|m|m.account()==lease(1).account).unwrap().roster(),d::Roster::assigned(d::Side::Two));
    for who in 1..=2{let b=&batch.bodies[&lease(who).account];assert!(!b.iter().any(|b|b.starts_with(&[0x13,0x46])));assert!(b.iter().any(|b|b.starts_with(&[0x13,0x56])&&b[3]==5));}
    denied(&mut c,2,request(222,405,0,0),&facts);
}

#[test]fn p10b_controller_closed_join_utf8_unsupported_map_mask_and_typed_route_poison_are_atomic(){
    let(mut c,facts)=fixture(2);let(_,native)=room(&mut c,&facts,1,false);
    denied(&mut c,2,request(202,400,i64::from(native),0),&facts);
    denied(&mut c,2,create(1,true,b"known type but no runtime resource"),&facts);
    denied(&mut c,2,create(4,true,&[0xff]),&facts);denied(&mut c,2,create(4,true,b"bad\ncomment"),&facts);
    let mask=[0x96,18,0,200,0,9,2,2,0,0,0,0,0,0,0,0,0,0,0,1,b'A'];
    denied(&mut c,2,i::record(&mask).unwrap().unwrap(),&facts);
    let mut wrong=request(221,401,0,0);wrong.reply=i::Reply::ListStream;denied(&mut c,1,wrong,&facts);
}

#[test]fn p10b_controller_real_list_and_preview_use_distinct_aliases_and_repeated_reads(){
    let(mut c,facts,key,native)=joined(2);c.bind(lease(3),call(3).channel,"Player3".into(),3,0).unwrap();
    let mut facts=facts;facts.insert(lease(3).account,adapter::NativeFacts{database_id:3,selected:None,descriptor:Vec::new(),igr_type:0,clan_database_id:0,clan_abbrev:String::new()});
    let query=i::Request{reply:i::Reply::ListStream,kind:i::Kind::List{prebattle_type:2,sort_key:7,idle:false,start:0,end:50}};
    let expected=lp::list_stream(&c.listing(0,50).unwrap()).unwrap();
    for _ in 0..2{assert_eq!(c.apply(call(3),query.clone(),&facts,0).unwrap().bodies[&lease(3).account],expected);}
    let list=c.listing(0,50).unwrap();assert_eq!(list.total,1);assert_eq!(list.rows[0].players,2);assert_eq!(list.rows[0].arena_type,4);
    c.apply(call(1),request(201,523,i64::from(native),0),&facts,0).unwrap();assert_eq!(c.recipients[&lease(1).account].preview.allocated(),1);
    denied(&mut c,1,request(221,414,i64::from(lp::PREVIEW_ALIAS_START),0),&facts);
    c.apply(call(3),request(201,523,i64::from(native),0),&facts,0).unwrap();assert_eq!(c.recipients[&lease(3).account].preview.allocated(),2);
    assert_eq!(c.recipients[&lease(3).account].book.allocated(),0);assert_eq!(c.registry.room(key).unwrap().members().count(),2);
}

#[test]fn p10b_controller_ready_is_task_only_until_verified_binding_and_rejects_late_channel_or_inventory(){
    let(mut c,mut facts,key,_)=joined(2);let batch=c.apply(call(2),request(221,402,7,0),&facts,0).unwrap();let task=&batch.ready[0];
    assert!(batch.bodies.is_empty());assert!(c.registry.room(key).unwrap().members().all(|m|m.ready().is_none()));
    let selected=d::WriterReadyRef::from_verified_writer(lease(2).account,"fixture-owned-seven".into(),13,[2;32]).unwrap();
    let f=facts.get_mut(&lease(2).account).unwrap();f.selected=Some(selected.clone());f.descriptor=vec![1,2,3];
    for poison in 0..3{let mut bad=call(2);let native=if poison==0{8}else{7};if poison==1{bad.channel.generation+=1;}if poison==2{bad.profile.source_binding=[18;32];}
        let before=c.clone();assert!(c.complete_ready(task,bad,native,selected.clone(),&facts,0).is_err());assert_eq!(c,before);}
    let done=c.complete_ready(task,call(2),7,selected.clone(),&facts,0).unwrap();
    assert_eq!(done.bodies[&lease(2).account][0],w::plain_response(221,w::CommandResult::Success,"").unwrap());
    assert_eq!(c.registry.room(key).unwrap().members().find(|m|m.account()==lease(2).account).unwrap().ready(),Some(&selected));
    let before=c.clone();assert!(c.complete_ready(task,call(2),7,selected,&facts,0).is_err());assert_eq!(c,before);
}

#[test]fn p10b_controller_final411_is_held_until_complete_reserve_and_finish_claim_release(){
    let(mut c,_,task)=prepared();let room=task.snapshot.room();let ticket=task.snapshot.ticket();let battle=d::BattleKey(77);
    let mut partial=reserve(&task,battle);partial.pop();let before=c.clone();assert!(c.commit_launch(room,ticket,battle,partial,0).is_err());assert_eq!(c,before);
    let done=c.commit_launch(room,ticket,battle,reserve(&task,battle),0).unwrap();
    assert_eq!(done.bodies[&lease(1).account][0],w::plain_response(224,w::CommandResult::Success,"").unwrap());
    assert!(!done.bodies.values().flatten().any(|b|b==&w::left()));
    for who in 1..=2{assert_eq!(c.registry.claim(lease(who).account),Some(d::Claim::Battle(battle)));assert!(c.recipients[&lease(who).account].last.is_none());}
    assert!(c.rooms.is_empty()&&c.joined.is_empty()&&c.held.is_empty());
    let finish=task.snapshot.members().iter().map(|m|d::FinishedRef::from_verified_writer(m.account(),format!("fixture-reserve:{}",m.account().0[0]),battle).unwrap()).collect();
    c.finish_battle(battle,finish,0).unwrap();assert!(c.registry.claim(lease(1).account).is_none());
}

#[test]fn p10b_controller_prepare_leave_retains_claim_and_abort_answers_exact_held_callback_failure(){
    let(mut c,facts,task)=prepared();let room=task.snapshot.room();let ticket=task.snapshot.ticket();
    let leave=c.apply(call(2),request(222,401,0,0),&facts,0).unwrap();assert!(leave.events.iter().any(|e|matches!(e,d::Event::AbortRequested{..})));
    assert!(!leave.bodies.values().flatten().any(|b|b.starts_with(&[0x13,0x4c])));
    assert_eq!(c.registry.claim(lease(2).account),Some(d::Claim::Room(room)));assert!(c.held.contains_key(&ticket));
    let batch=c.abort_launch(room,ticket,releases(&task),0).unwrap();assert_eq!(batch.bodies[&lease(1).account][0],w::plain_response(224,w::CommandResult::Failure,"").unwrap());
    assert!(c.registry.claim(lease(2).account).is_none());assert!(c.held.is_empty());
    assert_eq!(c.registry.room(room).unwrap().team_ready(),[false;2]);assert!(c.registry.room(room).unwrap().members().all(|m|m.ready().is_none()));
    assert!(batch.bodies[&lease(1).account].iter().any(|b|b==&w::team_states([w::TeamState::NotReady;2]).unwrap()));
    assert_eq!(batch.bodies[&lease(2).account],vec![w::left(),w::plain_response(222,w::CommandResult::Success,"").unwrap()]);
}

#[test]fn p10b_controller_late_bad_native_facts_reject_whole_registry_and_alias_publication(){
    let(mut c,mut facts,_,_)=joined(3);facts.get_mut(&lease(3).account).unwrap().igr_type=3;
    denied(&mut c,1,request(221,405,0,0),&facts);
}

#[test]fn p10b_controller_kick_and_rejoin_never_reuse_peer_alias_or_send_second_joined_to_creator(){
    let(mut c,facts,_,native)=joined(2);let old=c.recipients[&lease(1).account].last.as_ref().unwrap().rows[&lease(2).account].entity_id;
    let batch=c.apply(call(1),request(221,414,i64::from(old),0),&facts,0).unwrap();assert_eq!(batch.bodies[&lease(2).account],vec![w::kicked(10)]);
    c.apply(call(2),request(202,400,i64::from(native),0),&facts,0).unwrap();let new=c.recipients[&lease(1).account].last.as_ref().unwrap().rows[&lease(2).account].entity_id;assert!(new>old);
    denied(&mut c,1,request(222,414,i64::from(old),0),&facts);
}

#[test]fn p10b_controller_closed_room_metadata_cleanup_and_channel_floor_remain_bounded(){
    let(mut c,facts)=fixture(1);let mut last=0;
    for n in 0..12{let(_,native)=room(&mut c,&facts,1,true);assert!(native>last);last=native;
        c.apply(call(1),request(221+n,401,0,0),&facts,0).unwrap();assert!(c.rooms.is_empty()&&c.joined.is_empty());}
    c.retire(lease(1),call(1).channel,&facts,0).unwrap();assert!(c.recipients.is_empty()&&c.facts.is_empty());
    let before=c.clone();assert!(c.bind(lease(1),call(1).channel,"Player1".into(),1,0).is_err());assert_eq!(c,before);
}

#[test]fn p10b_controller_room_capacity_and_actual_live_counts_are_preserved_in_listing(){
    let(mut c,facts)=fixture(5);for who in 1..=4{room(&mut c,&facts,who,who!=4);}
    denied(&mut c,5,create(4,true,b"fifth"),&facts);let list=c.listing(0,50).unwrap();
    assert_eq!(list.total,4);assert_eq!(list.rows.iter().map(|r|r.native_room_id).collect::<Vec<_>>(),[4,3,2,1]);
    assert!(!list.rows[0].opened);assert!(list.rows.iter().all(|r|r.players==1));
    assert_eq!(c.listing(1,3).unwrap().rows.iter().map(|r|r.native_room_id).collect::<Vec<_>>(),[3,2]);
}

#[test]fn p10b_controller_512_peer_tombstones_exhaust_without_reusing_alias_or_committing_failed_join(){
    let(mut c,facts,_,native)=joined(2);
    for n in 1..512{c.apply(call(2),request(1000+n,401,0,0),&facts,0).unwrap();c.apply(call(2),request(202,400,i64::from(native),0),&facts,0).unwrap();}
    assert_eq!(c.recipients[&lease(1).account].book.allocated(),512);
    c.apply(call(2),request(1600,401,0,0),&facts,0).unwrap();
    denied(&mut c,2,request(202,400,i64::from(native),0),&facts);
    assert_eq!(c.recipients[&lease(1).account].book.allocated(),512);assert!(c.registry.claim(lease(2).account).is_none());
}

#[test]fn p10b_controller_batch128_64k_and_native_id_exhaustion_are_atomic_at_exact_bounds(){
    let mut batch=Batch::default();batch.append(lease(1).account,vec![vec![0;512];128]).unwrap();
    assert_eq!(batch.bodies[&lease(1).account].iter().map(Vec::len).sum::<usize>(),65536);
    let before=batch.clone();assert_eq!(batch.append(lease(1).account,vec![vec![1]]),Err(Refusal::Limit));assert_eq!(batch,before);
    assert_eq!(batch.append(lease(2).account,vec![vec![0;513]]),Err(Refusal::Limit));assert_eq!(batch,before);
    let(mut c,mut facts)=fixture(1);facts.get_mut(&lease(1).account).unwrap().igr_type=3;
    denied(&mut c,1,create(4,true,b"late publication failure"),&facts);assert_eq!(c.next_native,0);
    facts.get_mut(&lease(1).account).unwrap().igr_type=0;c.next_native=i32::MAX as u32-1;
    let(_,native)=room(&mut c,&facts,1,true);assert_eq!(native,i32::MAX as u32);
    c.apply(call(1),request(221,401,0,0),&facts,0).unwrap();denied(&mut c,1,create(4,true,b"no wrap"),&facts);
    assert_eq!(c.next_native,i32::MAX as u32);assert!(c.rooms.is_empty());
}

#[test]fn p10b_controller_preparing_kick_and_leave_defer_once_and_never_reply_on_retired_channel(){
    let(mut c,facts,task)=prepared();let peer=c.recipients[&lease(1).account].last.as_ref().unwrap().rows[&lease(2).account].entity_id;
    let kicked=c.apply(call(1),request(225,414,i64::from(peer),0),&facts,0).unwrap();
    assert!(!kicked.bodies.values().flatten().any(|b|b.starts_with(&[0x13,0x4c])));
    let before=c.clone();assert_eq!(c.apply(call(1),request(226,414,i64::from(peer),0),&facts,0),Err(Refusal::Busy));assert_eq!(c,before);
    c.apply(call(2),request(222,401,0,0),&facts,0).unwrap();assert_eq!(c.departures[&task.snapshot.ticket()].len(),2);
    c.retire(lease(1),call(1).channel,&facts,0).unwrap();
    let batch=c.abort_launch(task.snapshot.room(),task.snapshot.ticket(),releases(&task),0).unwrap();
    assert!(!batch.bodies.contains_key(&lease(1).account));assert!(c.departures.is_empty()&&c.held.is_empty());
    assert_eq!(batch.bodies[&lease(2).account],vec![w::kicked(10),w::plain_response(222,w::CommandResult::Success,"").unwrap()]);
}

#[test]fn p10b_controller_read_generation_is_server_owned_stable_for_reads_and_bumps_on_state_change(){
    let(mut c,facts)=fixture(2);assert_eq!(c.read_revision(),0);let(key,native)=room(&mut c,&facts,1,true);
    let revision=c.read_revision();assert!(revision>0);assert_eq!(c.room_read(native),Some((key,c.registry.room(key).unwrap().revision())));
    let read=i::Request{reply:i::Reply::ListStream,kind:i::Kind::List{prebattle_type:2,sort_key:7,idle:false,start:0,end:50}};
    c.apply(call(2),read.clone(),&facts,0).unwrap();c.apply(call(2),read,&facts,0).unwrap();assert_eq!(c.read_revision(),revision);
    c.apply(call(2),request(202,400,i64::from(native),0),&facts,0).unwrap();assert!(c.read_revision()>revision);
    c.apply(call(1),request(221,401,0,0),&facts,0).unwrap();assert!(c.room_read(native).is_none());
}

#[test]fn p10b_controller_failed_ready_retry_has_distinct_origin_and_late_old_reply_cannot_grant_ready(){
    let(mut c,mut facts,_,_)=joined(2);let first=c.apply(call(2),request(221,402,1,0),&facts,0).unwrap().ready.remove(0);
    let failed=c.finish_ready_failure(&first).unwrap();assert_eq!(failed.bodies[&lease(2).account],vec![w::plain_response(221,w::CommandResult::Failure,"").unwrap()]);
    let second=c.apply(call(2),request(221,402,1,0),&facts,0).unwrap().ready.remove(0);assert!(second.id()>first.id());
    assert_eq!(first.context,second.context);assert_eq!(first.profile,second.profile);assert_eq!(first.channel,second.channel);
    let selected=d::WriterReadyRef::from_verified_writer(lease(2).account,"fixture-owned-two".into(),13,[2;32]).unwrap();
    let f=facts.get_mut(&lease(2).account).unwrap();f.selected=Some(selected.clone());f.descriptor=vec![1,2,3];
    let before=c.clone();assert!(c.complete_ready(&first,call(2),1,selected.clone(),&facts,0).is_err());assert_eq!(c,before);
    c.complete_ready(&second,call(2),1,selected,&facts,0).unwrap();assert!(c.pending_ready.is_empty());
}

#[test]fn p10b_controller_account_incarnation_rebind_requires_idle_and_preserves_session_tombstones(){
    let(mut c,facts,_,native)=joined(2);c.apply(call(1),request(201,523,i64::from(native),0),&facts,0).unwrap();
    let alias_count=c.recipients[&lease(1).account].book.allocated();let preview_count=c.recipients[&lease(1).account].preview.allocated();
    let warm=current::Channel{generation:2,..call(1).channel};let before=c.clone();
    assert_eq!(c.bind(lease(1),warm,"Player1".into(),1,0),Err(Refusal::Busy));assert_eq!(c,before);
    c.apply(call(1),request(221,401,0,0),&facts,0).unwrap();c.bind(lease(1),warm,"Player1".into(),1,0).unwrap();
    assert_eq!(c.recipients[&lease(1).account].book.allocated(),alias_count);assert_eq!(c.recipients[&lease(1).account].preview.allocated(),preview_count);
    let before=c.clone();assert_eq!(c.apply(call(1),create(4,true,b"old Account"),&facts,0),Err(Refusal::StaleChannel));assert_eq!(c,before);
    let fresh=Call{channel:warm,..call(1)};c.apply(fresh,create(4,true,b"new Account"),&facts,0).unwrap();
    let native=c.native_room(c.registry.authenticated_room(lease(1)).unwrap()).unwrap();
    c.apply(call(2),request(202,400,i64::from(native),0),&facts,0).unwrap();assert!(c.recipients[&lease(1).account].book.allocated()>alias_count);
}

#[test]fn p10b_controller_pending_ready_blocks_warm_rebind_until_exact_job_is_drained(){
    let(mut c,facts,_,_)=joined(2);let task=c.apply(call(1),request(221,402,1,0),&facts,0).unwrap().ready.remove(0);
    c.apply(call(1),request(222,401,0,0),&facts,0).unwrap();let warm=current::Channel{generation:2,..call(1).channel};
    let before=c.clone();assert_eq!(c.bind(lease(1),warm,"Player1".into(),1,0),Err(Refusal::Busy));assert_eq!(c,before);
    c.finish_ready_failure(&task).unwrap();c.bind(lease(1),warm,"Player1".into(),1,0).unwrap();
    let before=c.clone();assert_eq!(c.finish_ready_failure(&task),Err(Refusal::StaleChannel));assert_eq!(c,before);
}

#[test]fn p10b_controller_creator_benched_gets_final_callback_and_left_while_combat_gets_no_explicit_left(){
    let(mut c,mut facts,key,_)=joined(3);
    c.apply(call(1),request(221,404,i64::from(aliases::OWN_ENTITY_ID),17),&facts,0).unwrap();
    for(who,side)in[(2,1),(3,2)]{let alias=c.recipients[&lease(1).account].last.as_ref().unwrap().rows[&lease(who).account].entity_id;
        c.apply(call(1),request(222+i16::from(who),404,i64::from(alias),side),&facts,0).unwrap();ready(&mut c,&mut facts,who);}
    // The second assignment invalidates no existing selected player's ready
    // reference. Both selected references remain source-adapter metadata here.
    c.apply(call(1),request(230,411,1,0),&facts,0).unwrap();
    let task=c.apply(call(1),request(231,411,2,0),&facts,0).unwrap().prepare.remove(0);
    assert!(task.snapshot.members().iter().all(|m|m.account()!=lease(1).account));
    let battle=d::BattleKey(88);let batch=c.commit_launch(key,task.snapshot.ticket(),battle,reserve(&task,battle),0).unwrap();
    assert_eq!(batch.bodies[&lease(1).account],vec![w::plain_response(231,w::CommandResult::Success,"").unwrap(),w::left()]);
    for who in 2..=3{assert!(!batch.bodies[&lease(who).account].iter().any(|b|b==&w::left()));assert_eq!(c.registry.claim(lease(who).account),Some(d::Claim::Battle(battle)));}
    assert!(c.registry.claim(lease(1).account).is_none());
}

#[test]fn p10b_controller_retired_ready_failure_does_not_reply_to_new_physical_session(){
    let(mut c,facts,_,_)=joined(2);let task=c.apply(call(2),request(221,402,1,0),&facts,0).unwrap().ready.remove(0);
    c.retire(lease(2),call(2).channel,&facts,0).unwrap();
    let fresh=d::AuthLease{generation:99,..lease(2)};let channel=current::Channel{session:99,generation:1};
    c.bind(fresh,channel,"Player2".into(),2,0).unwrap();assert!(c.finish_ready_failure(&task).unwrap().bodies.is_empty());
    assert!(c.pending_ready.is_empty());assert_eq!(c.recipients[&lease(2).account].lease,fresh);
}

#[test]fn p10b_controller_pending_ready24_limit_includes_retired_jobs_until_exact_drain(){
    let(mut c,mut facts)=fixture(24);let mut native=0;
    for creator in[1u8,7,13,19]{let(_,id)=room(&mut c,&facts,creator,true);if creator==1{native=id;}
        for who in creator+1..creator+6{c.apply(call(who),request(202,400,i64::from(id),0),&facts,0).unwrap();}}
    for who in 1..=24{c.apply(call(who),request(221,402,1,0),&facts,0).unwrap();}assert_eq!(c.pending_ready.len(),24);
    let old=c.pending_ready[&lease(6).account].clone();c.retire(lease(6),call(6).channel,&facts,0).unwrap();facts.remove(&lease(6).account);
    c.bind(lease(25),call(25).channel,"Player25".into(),25,0).unwrap();facts.insert(lease(25).account,adapter::NativeFacts{database_id:25,selected:None,descriptor:Vec::new(),igr_type:0,clan_database_id:0,clan_abbrev:String::new()});
    c.apply(call(25),request(202,400,i64::from(native),0),&facts,0).unwrap();denied(&mut c,25,request(221,402,1,0),&facts);
    assert!(c.finish_ready_failure(&old).unwrap().bodies.is_empty());let next=c.apply(call(25),request(221,402,1,0),&facts,0).unwrap();
    assert_eq!(next.ready.len(),1);assert_eq!(c.pending_ready.len(),24);assert!(next.ready[0].id()>old.id());
}

#[test]fn p10b_controller_reselect_revokes_prior_ready_and_votes_before_later_start(){
    let(mut c,mut facts,key,_)=joined(2);
    let peer=c.recipients[&lease(1).account].last.as_ref().unwrap().rows[&lease(2).account].entity_id;
    c.apply(call(1),request(222,404,i64::from(peer),2),&facts,0).unwrap();
    let old=ready(&mut c,&mut facts,1);ready(&mut c,&mut facts,2);
    c.apply(call(1),request(223,411,1,0),&facts,0).unwrap();
    let batch=c.apply(call(1),request(224,402,1,0),&facts,0).unwrap();
    assert_eq!(batch.ready.len(),1);assert!(batch.prepare.is_empty());
    let room=c.registry.room(key).unwrap();assert_eq!(room.team_ready(),[false,false]);
    assert!(room.members().find(|m|m.account()==lease(1).account).unwrap().ready().is_none());
    assert!(!batch.bodies.values().flatten().any(|b|b==&w::plain_response(224,w::CommandResult::Success,"").unwrap()));
    denied(&mut c,1,request(225,411,1,0),&facts);
    assert_ne!(Some(&old),c.registry.room(key).unwrap().members().find(|m|m.account()==lease(1).account).unwrap().ready());
}


// Explicit checked LAB rebase. Synthetic DTO refs are shape/binding fixtures,
// never a replacement for the actual source/owned query at the host boundary.
fn rebase_ref(n:u8,facts:&mut BTreeMap<d::Account,adapter::NativeFacts>)->d::WriterReadyRef{
    let selected=d::WriterReadyRef::from_verified_writer(lease(n).account,format!("fixture-owned-{n}"),13,[n;32]).unwrap();
    let f=facts.get_mut(&lease(n).account).unwrap();f.selected=Some(selected.clone());f.descriptor=vec![n,2,3];selected
}
#[test]fn p10b_rebase_two_simultaneous_original_ready_requests_complete_both_after_other_ready(){
    let(mut c,mut f,k,_)=joined(2);let a=c.apply(call(1),request(221,402,1,0),&f,0).unwrap().ready.remove(0);
    let b=c.apply(call(2),request(221,402,1,0),&f,0).unwrap().ready.remove(0);assert_eq!(a.room_revision(),b.room_revision());
    let sa=rebase_ref(1,&mut f);let sb=rebase_ref(2,&mut f);c.complete_ready(&a,call(1),1,sa.clone(),&f,0).unwrap();
    assert_ne!(c.registry.room(k).unwrap().revision(),b.room_revision());let done=c.complete_ready(&b,call(2),1,sb.clone(),&f,0).unwrap();
    assert_eq!(done.bodies[&lease(2).account][0],w::plain_response(221,w::CommandResult::Success,"").unwrap());
    for(n,selected)in[(1,sa),(2,sb)]{assert_eq!(c.registry.room(k).unwrap().members().find(|m|m.account()==lease(n).account).unwrap().ready(),Some(&selected));}
}
#[test]fn p10b_rebase_creator_query_survives_peer_join_and_same_membership(){
    let(mut c,mut f)=fixture(2);let(k,native)=room(&mut c,&f,1,true);let task=c.apply(call(1),request(221,402,1,0),&f,0).unwrap().ready.remove(0);
    let own=c.registry.member_context(k,lease(1).account);c.apply(call(2),request(202,400,i64::from(native),0),&f,0).unwrap();assert_eq!(c.registry.member_context(k,lease(1).account),own);
    let selected=rebase_ref(1,&mut f);c.complete_ready(&task,call(1),1,selected.clone(),&f,0).unwrap();assert_eq!(c.registry.room(k).unwrap().members().find(|m|m.account()==lease(1).account).unwrap().ready(),Some(&selected));
}
#[test]fn p10b_rebase_explicit403_cancels_exact_pending_nonce_and_failure_drains_it(){
    let(mut c,mut f,k,_)=joined(2);let task=c.apply(call(2),request(221,402,1,0),&f,0).unwrap().ready.remove(0);
    c.apply(call(2),request(222,403,1,0),&f,0).unwrap();let selected=rebase_ref(2,&mut f);let before=c.clone();
    assert!(c.complete_ready(&task,call(2),1,selected,&f,0).is_err());assert_eq!(c,before);assert!(c.registry.room(k).unwrap().members().all(|m|m.ready().is_none()));
    let failed=c.finish_ready_failure(&task).unwrap();assert_eq!(failed.bodies[&lease(2).account],vec![w::plain_response(221,w::CommandResult::Failure,"").unwrap()]);assert!(c.pending_ready.is_empty());
    let before=c.clone();assert!(c.finish_ready_failure(&task).is_err());assert_eq!(c,before);
    let new=c.apply(call(2),request(223,402,1,0),&f,0).unwrap().ready.remove(0);assert!(new.id()>task.id());let selected=rebase_ref(2,&mut f);c.complete_ready(&new,call(2),1,selected,&f,0).unwrap();
}
#[test]fn p10b_rebase_side_swap_and_settings_do_not_require_unprompted_native_reready(){
    let(mut c,mut f,k,_)=joined(2);let task=c.apply(call(2),request(221,402,1,0),&f,0).unwrap().ready.remove(0);
    let alias=c.recipients[&lease(1).account].last.as_ref().unwrap().rows[&lease(2).account].entity_id;
    c.apply(call(1),request(222,404,i64::from(alias),2),&f,0).unwrap();c.apply(call(1),request(223,405,0,0),&f,0).unwrap();c.apply(call(1),request(224,407,900,0),&f,0).unwrap();
    let selected=rebase_ref(2,&mut f);c.complete_ready(&task,call(2),1,selected.clone(),&f,0).unwrap();let r=c.registry.room(k).unwrap();assert_eq!(r.settings().seconds,900);assert_eq!(r.members().find(|m|m.account()==lease(2).account).unwrap().ready(),Some(&selected));
}
#[test]fn p10b_rebase_still_rejects_own_rejoin_channel_CAS_source_and_native_selection_changes(){
    for poison in 0..5{let(mut c,mut f,_,native)=joined(2);let task=c.apply(call(2),request(221,402,1,0),&f,0).unwrap().ready.remove(0);let mut actual=call(2);let mut selected=rebase_ref(2,&mut f);let mut inventory=1;
        match poison{0=>{c.apply(call(2),request(222,401,0,0),&f,0).unwrap();c.apply(call(2),request(202,400,i64::from(native),0),&f,0).unwrap();},
            1=>actual.channel.generation+=1,2=>{actual.profile.revision+=1;actual.expected_revision+=1;selected=d::WriterReadyRef::from_verified_writer(lease(2).account,"fixture-owned-2".into(),14,[2;32]).unwrap();f.get_mut(&lease(2).account).unwrap().selected=Some(selected.clone());},3=>actual.profile.source_binding[0]^=1,_=>inventory=2}
        let before=c.clone();assert!(c.complete_ready(&task,actual,inventory,selected,&f,0).is_err(),"poison {poison}");assert_eq!(c,before);
    }
}
#[test]fn p10b_rebase_cancelled_nonce_budget_is_pending24_and_exact_failure_removes_every_marker(){
    let(mut c,mut f)=fixture(24);for host in[1u8,7,13,19]{let(_,native)=room(&mut c,&f,host,true);for who in host+1..host+6{c.apply(call(who),request(202,400,i64::from(native),0),&f,0).unwrap();}}
    let mut tasks=Vec::new();for who in 1..=24{tasks.push(c.apply(call(who),request(221,402,1,0),&f,0).unwrap().ready.remove(0));c.apply(call(who),request(222,403,1,0),&f,0).unwrap();}
    assert_eq!(c.pending_ready.len(),24);for task in tasks{let n=task.caller().account.0[0];let selected=rebase_ref(n,&mut f);let before=c.clone();assert!(c.complete_ready(&task,call(n),1,selected,&f,0).is_err());assert_eq!(c,before);c.finish_ready_failure(&task).unwrap();}
    assert!(c.pending_ready.is_empty());for who in 1..=24{let task=c.apply(call(who),request(223,402,1,0),&f,0).unwrap().ready.remove(0);c.apply(call(who),request(224,403,1,0),&f,0).unwrap();c.finish_ready_failure(&task).unwrap();}assert!(c.pending_ready.is_empty());
}
