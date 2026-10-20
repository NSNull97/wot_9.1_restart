//! Actual Controller/domain scheduling tests with authored trusted metadata.
//! These fixtures do NOT prove real writer ownership, native UI, or sockets.
use super::*;

type Facts=BTreeMap<d::Account,adapter::NativeFacts>;
fn lease(n:u8)->d::AuthLease{d::AuthLease{account:d::Account([n;16]),generation:1}}
fn call(n:u8,generation:u64)->Call{Call{caller:lease(n),channel:current::Channel{session:u32::from(n),generation},
    profile:current::ProfileStamp{revision:13,source_binding:[17;32]},expected_revision:13}}
fn request(id:i16,command:i16,a:i64,b:i32)->i::Request{
    let mut raw=vec![0x8e,20,0];raw.extend(id.to_le_bytes());raw.extend(command.to_le_bytes());
    raw.extend(a.to_le_bytes());raw.extend(b.to_le_bytes());raw.extend(0i32.to_le_bytes());i::record(&raw).unwrap().unwrap()
}
fn create()->i::Request{
    let mut args=4i32.to_le_bytes().to_vec();args.extend(600i32.to_le_bytes());args.extend([1,4]);args.extend(b"warm");
    let mut raw=vec![0x9a];raw.extend((args.len()as u16).to_le_bytes());raw.extend(args);i::record(&raw).unwrap().unwrap()
}
fn list()->i::Request{i::Request{reply:i::Reply::ListStream,kind:i::Kind::List{prebattle_type:2,sort_key:7,idle:false,start:0,end:50}}}
fn fixture()->(Controller,Facts){
    let mut c=Controller::default();let mut facts=Facts::new();
    for n in 1..=3{c.bind(lease(n),call(n,1).channel,format!("Player{n}"),i32::from(n),0).unwrap();
        facts.insert(lease(n).account,adapter::NativeFacts{database_id:i32::from(n),selected:None,descriptor:Vec::new(),igr_type:0,clan_database_id:0,clan_abbrev:String::new()});}
    (c,facts)
}
fn joined()->(Controller,Facts,d::RoomKey,u32){
    let(mut c,facts)=fixture();c.apply(call(1,1),create(),&facts,0).unwrap();
    let room=c.registry.authenticated_room(lease(1)).unwrap();let native=c.native_room(room).unwrap();
    c.apply(call(2,1),request(202,400,i64::from(native),0),&facts,0).unwrap();(c,facts,room,native)
}
fn prepared()->(Controller,Facts,PrepareTask){
    let(mut c,mut facts,_,native)=joined();
    // Allocate both room and preview aliases before launch, so warm tests can
    // detect resetting either namespace rather than only comparing zeroes.
    for n in 1..=2{c.apply(call(n,1),request(201,523,i64::from(native),0),&facts,0).unwrap();}
    let peer=c.recipients[&lease(1).account].last.as_ref().unwrap().rows[&lease(2).account].entity_id;
    c.apply(call(1,1),request(221,404,i64::from(peer),2),&facts,0).unwrap();
    for n in 1..=2{
        let task=c.apply(call(n,1),request(222,402,1,0),&facts,0).unwrap().ready.remove(0);
        let selected=d::WriterReadyRef::from_verified_writer(lease(n).account,format!("authored-owned-{n}"),13,[n;32]).unwrap();
        let fact=facts.get_mut(&lease(n).account).unwrap();fact.selected=Some(selected.clone());fact.descriptor=vec![n,2,3];
        c.complete_ready(&task,call(n,1),1,selected,&facts,0).unwrap();
    }
    c.apply(call(1,1),request(223,411,1,0),&facts,0).unwrap();
    let task=c.apply(call(1,1),request(224,411,2,0),&facts,0).unwrap().prepare.remove(0);(c,facts,task)
}
fn commit(c:&mut Controller,task:&PrepareTask,battle:d::BattleKey)->Vec<d::FinishedRef>{
    let reserved=task.snapshot().members().iter().map(|m|d::ReservedRef::from_verified_writer(m.ready().clone(),
        format!("authored-reserve:{}",m.account().0[0]),battle,task.snapshot().ticket()).unwrap()).collect();
    c.commit_launch(task.snapshot().room(),task.snapshot().ticket(),battle,reserved,0).unwrap();
    task.snapshot().members().iter().map(|m|d::FinishedRef::from_verified_writer(m.account(),
        format!("authored-reserve:{}",m.account().0[0]),battle).unwrap()).collect()
}
fn battle()->(Controller,Facts,d::BattleKey,Vec<d::FinishedRef>){
    let(mut c,facts,task)=prepared();let battle=d::BattleKey(77);let finished=commit(&mut c,&task,battle);(c,facts,battle,finished)
}
fn bind_warm(c:&mut Controller,n:u8,generation:u64){c.bind(lease(n),call(n,generation).channel,format!("Player{n}"),i32::from(n),0).unwrap();}
fn deny(c:&mut Controller,call:Call,request:i::Request,facts:&Facts,reason:Refusal){
    let before=c.clone();assert_eq!(c.apply(call,request,facts,0),Err(reason));assert_eq!(*c,before);
}

#[test]
fn p10b_warm_battle_same_session_rebind_preserves_claim_and_serves_actual_list_stream(){
    let(mut c,facts,battle,_)=battle();
    c.apply(call(3,1),create(),&facts,0).unwrap();let listing=c.listing(0,50).unwrap();assert_eq!(listing.total,1);
    let mut expected=c.clone();expected.recipients.get_mut(&lease(1).account).unwrap().channel=call(1,2).channel;
    bind_warm(&mut c,1,2);assert_eq!(c,expected);
    assert!(c.is_current_recipient(lease(1),call(1,2).channel,1));
    assert_eq!(c.recipient_channel(lease(1),1),Some(call(1,2).channel));
    assert_eq!(c.recipient_channel(lease(1),99),None);
    for _ in 0..2{let result=c.apply(call(1,2),list(),&facts,0).unwrap();
        assert_eq!(result.bodies[&lease(1).account],lp::list_stream(&listing).unwrap());assert!(result.ready.is_empty()&&result.prepare.is_empty());}
    for n in 1..=2{assert_eq!(c.registry.claim(lease(n).account),Some(d::Claim::Battle(battle)));}
    assert_eq!(c.recipients[&lease(2).account].channel,call(2,1).channel);
    deny(&mut c,call(1,1),list(),&facts,Refusal::StaleChannel);
}

#[test]
fn p10b_warm_battle_new_channel_cannot_create_join_or_ready_until_every_finish(){
    let(mut c,facts,battle,finished)=battle();bind_warm(&mut c,1,2);
    c.apply(call(3,1),create(),&facts,0).unwrap();let room=c.registry.authenticated_room(lease(3)).unwrap();let native=c.native_room(room).unwrap();
    deny(&mut c,call(1,2),create(),&facts,Refusal::Domain(d::Error::AlreadyClaimed));
    deny(&mut c,call(1,2),request(202,400,i64::from(native),0),&facts,Refusal::Domain(d::Error::AlreadyClaimed));
    for request in [request(225,402,1,0),request(226,403,1,0),request(227,401,0,0)]{
        deny(&mut c,call(1,2),request,&facts,Refusal::Domain(d::Error::BusyBattle));
    }
    let before=c.clone();assert_eq!(c.finish_battle(battle,finished[..1].to_vec(),0),Err(Refusal::Domain(d::Error::WrongReceipt)));assert_eq!(c,before);
    assert!(c.pending_ready.is_empty()&&c.held.is_empty());assert_eq!(c.registry.claim(lease(1).account),Some(d::Claim::Battle(battle)));
}

#[test]
fn p10b_warm_battle_full_finish_allows_next_room_without_alias_or_generation_reset(){
    let(mut c,facts,battle,finished)=battle();let room_alias=aliases::OWN_ENTITY_ID+1;
    let own_before=c.recipients[&lease(1).account].clone();let peer_before=c.recipients[&lease(2).account].clone();
    assert!(own_before.book.allocated()>0&&own_before.preview.allocated()>0);
    bind_warm(&mut c,1,2);c.finish_battle(battle,finished,0).unwrap();
    for n in 1..=2{assert_eq!(c.registry.claim(lease(n).account),None);}
    assert_eq!(c.recipients[&lease(1).account].book,own_before.book);assert_eq!(c.recipients[&lease(1).account].preview,own_before.preview);
    c.apply(call(1,2),create(),&facts,0).unwrap();let room=c.registry.authenticated_room(lease(1)).unwrap();let native=c.native_room(room).unwrap();
    assert!(native>1);bind_warm(&mut c,2,2);c.apply(call(2,2),request(202,400,i64::from(native),0),&facts,0).unwrap();
    let own=&c.recipients[&lease(1).account];assert!(own.book.allocated()>own_before.book.allocated());
    let new_peer=own.last.as_ref().unwrap().rows[&lease(2).account].entity_id;assert!(new_peer>room_alias);
    assert!(c.recipients[&lease(2).account].book.allocated()>peer_before.book.allocated());
    let before=c.clone();assert!(c.apply(call(1,2),request(228,414,i64::from(room_alias),0),&facts,0).is_err());assert_eq!(c,before);
    c.apply(call(1,2),request(201,523,i64::from(native),0),&facts,0).unwrap();
    assert!(c.recipients[&lease(1).account].preview.allocated()>own_before.preview.allocated());
    deny(&mut c,call(1,1),list(),&facts,Refusal::StaleChannel);
    let before=c.clone();assert_eq!(c.bind(lease(1),call(1,1).channel,"Player1".into(),1,0),Err(Refusal::StaleChannel));assert_eq!(c,before);
}

#[test]
fn p10b_warm_battle_rebind_rejects_other_auth_native_database_session_or_old_account_generation(){
    let(mut c,_,battle,_)=battle();bind_warm(&mut c,1,2);
    for (lease,channel,name,database,expected) in [
        (d::AuthLease{generation:2,..lease(1)},call(1,3).channel,"Player1",1,Refusal::Domain(d::Error::AlreadyClaimed)),
        (lease(1),call(1,3).channel,"Renamed",1,Refusal::Domain(d::Error::AlreadyClaimed)),
        (lease(1),call(1,3).channel,"Player1",99,Refusal::StaleChannel),
        (lease(1),current::Channel{session:99,generation:3},"Player1",1,Refusal::StaleChannel),
        (lease(1),call(1,1).channel,"Player1",1,Refusal::StaleChannel),
    ]{
        let before=c.clone();assert_eq!(c.bind(lease,channel,name.into(),database,0),Err(expected));assert_eq!(c,before);
    }
    let before=c.clone();bind_warm(&mut c,1,2);assert_eq!(c,before);bind_warm(&mut c,1,3);
    assert_eq!(c.registry.claim(lease(1).account),Some(d::Claim::Battle(battle)));
    assert!(!c.is_current_recipient(lease(1),call(1,2).channel,1));
}

#[test]
fn p10b_warm_battle_lobby_preparing_and_disconnected_claims_keep_original_bind_fences(){
    let(mut lobby,facts,room,_)=joined();let before=lobby.clone();
    assert_eq!(lobby.bind(lease(1),call(1,2).channel,"Player1".into(),1,0),Err(Refusal::Busy));assert_eq!(lobby,before);
    assert_eq!(lobby.registry.claim(lease(1).account),Some(d::Claim::Room(room)));
    let(mut preparing,_,task)=prepared();let before=preparing.clone();
    assert_eq!(preparing.bind(lease(2),call(2,2).channel,"Player2".into(),2,0),Err(Refusal::Busy));assert_eq!(preparing,before);
    assert!(preparing.held.contains_key(&task.snapshot().ticket()));
    let(mut c,_,battle,_)=battle();c.retire(lease(1),call(1,1).channel,&facts,0).unwrap();
    let before=c.clone();assert_eq!(c.bind(lease(1),call(1,2).channel,"Player1".into(),1,0),Err(Refusal::Domain(d::Error::AlreadyClaimed)));assert_eq!(c,before);
    assert_eq!(c.registry.claim(lease(1).account),Some(d::Claim::Battle(battle)));assert!(!c.recipients.contains_key(&lease(1).account));
}

#[test]
fn p10b_warm_battle_never_bypasses_retained_view_pending_ready_held_or_departure(){
    let(preparing,_,task)=prepared();let old_view=preparing.recipients[&lease(1).account].last.clone();
    let(mut pending,pending_facts,_,_)=joined();let pending_task=pending.apply(call(1,1),request(225,402,1,0),&pending_facts,0).unwrap().ready.remove(0);
    let(mut departing,departing_facts,_)=prepared();departing.apply(call(1,1),request(226,401,0,0),&departing_facts,0).unwrap();
    let retained_departure=departing.departures[&task.snapshot().ticket()].clone();
    let(base,_,battle,_)=battle();
    // Explicit retained-work/invariant fixtures: references were captured via
    // actual Controller operations above; no imaginary writer success is used.
    for guard in 0..4{let mut c=base.clone();match guard{
        0=>c.recipients.get_mut(&lease(1).account).unwrap().last=old_view.clone(),
        1=>{c.pending_ready.insert(lease(1).account,pending_task.clone());},
        2=>{c.held.insert(task.snapshot().ticket(),task.clone());},
        _=>{c.departures.insert(task.snapshot().ticket(),retained_departure.clone());},
    }
        let before=c.clone();assert_eq!(c.bind(lease(1),call(1,2).channel,"Player1".into(),1,0),Err(Refusal::Busy),"retained guard {guard}");assert_eq!(c,before);
        assert_eq!(c.registry.claim(lease(1).account),Some(d::Claim::Battle(battle)));
    }
}
