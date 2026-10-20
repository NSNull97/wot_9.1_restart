//! Actual Session/Controller/Window + readonly C/D SQL Selection cache.
//! p13.in_flight is AUTHORED exactly at the Preparing handoff; no reserve/Saga
//! execution is claimed. Third BENCH identity/display is AUTHORED, not owned.
use super::*;
use crate::training091::domain as room;
use super::super::super::p10b_receive_host as receive;
type Facts=BTreeMap<room::Account,crate::training091::adapter::NativeFacts>;
type Bindings=BTreeMap<u32,[u8;32]>;
type Retained=BTreeMap<room::Account,receive::RetainedMember>;

fn integer_prefix(body:&[u8])->u32{
    assert_eq!(&body[5..8],b"\x80\x02(");match body[8]{b'K'=>u32::from(body[9]),
        b'M'=>u32::from(u16::from_le_bytes(body[9..11].try_into().unwrap())),
        b'J'=>u32::try_from(i32::from_le_bytes(body[9..13].try_into().unwrap())).unwrap(),_=>panic!("closed source primitive integer")}
}
fn preparing(now:Instant,bench:bool)->(Vec<Session>,Controller,Manager,Vec<ReadyTask>,Bindings,Facts,Retained){
    let(mut sessions,mut c,mut m,tasks)=fixture(now);
    let mut bindings=sessions.iter().map(|s|(s.id,source_binding(s).unwrap())).collect::<Bindings>();
    if bench{
        let mut s=session(1,now);let p=s.identity.as_ref().unwrap();s.id=105;
        s.identity=Some(Arc::new(crate::identity091::Profile{account_id:"00000069-1234-4234-8234-123456789abc".into(),database_id:105,name:"AuthoredBench105".into(),fixture_dir:p.fixture_dir.clone()}));
        // Display-only trusted Session fixture. It never submits a query,
        // constructs a ReadyRef or borrows D's owned Selection.
        bindings.insert(s.id,[105;32]);let call=receive::bound_call(&s,&bindings).unwrap().0;
        let owner=s.identity.as_ref().unwrap();c.bind(call.caller,call.channel,owner.name.clone(),owner.database_id,0).unwrap();sessions.push(s);
        let facts=m.facts(&sessions,&c).unwrap();let native=c.native_room(tasks[0].room()).unwrap();
        let batch=c.apply(call,rpc(202,400,i64::from(native),0),&facts,0).unwrap();Manager::publish(&mut sessions,&c,&batch).unwrap();flush(&mut sessions,now);
    }
    for index in 0..2{
        m.completed=Some((tasks[index].clone(),Ok(completion(index,&sessions[index]))));m.poll(&mut sessions,&mut c,0).unwrap();
        if index==0{flush(&mut sessions,now);}
    }
    let actual=bodies(&sessions[0],now);let alias=integer_prefix(actual.iter().find(|b|b.starts_with(&[0x13,0x56])&&b[3]==4).unwrap());
    flush(&mut sessions,now);let facts=m.facts(&sessions,&c).unwrap();let a=receive::bound_call(&sessions[0],&bindings).unwrap().0;
    let batch=c.apply(a,rpc(230,404,i64::from(alias),2),&facts,0).unwrap();Manager::publish(&mut sessions,&c,&batch).unwrap();flush(&mut sessions,now);
    let batch=c.apply(a,rpc(231,411,1,0),&facts,0).unwrap();assert!(batch.prepare.is_empty());Manager::publish(&mut sessions,&c,&batch).unwrap();flush(&mut sessions,now);
    let batch=c.apply(a,rpc(232,411,2,0),&facts,0).unwrap();assert_eq!(batch.prepare.len(),1);assert_eq!(batch.prepare[0].snapshot().members().len(),2);
    Manager::publish(&mut sessions,&c,&batch).unwrap();flush(&mut sessions,now);
    // AUTHORED actual Preparing.begin guard, not an authored writer receipt.
    for s in &mut sessions[..2]{s.shared.as_mut().unwrap().profile13.as_mut().unwrap().in_flight=true;}
    let facts=m.facts(&sessions,&c).unwrap();let mut held=Retained::new();
    for(index,s)in sessions.iter().enumerate(){
        let call=receive::bound_call(s,&bindings).unwrap().0;let selected=if index<2{Some(receive::RetainedReady{task:tasks[index].clone(),reference:m.accepted[&call.caller.account].selection.reference().clone()})}else{None};
        let retained=receive::RetainedMember::capture(s,&c,&bindings,&facts[&call.caller.account],selected).unwrap();
        assert_eq!(retained.session(),s.id);assert_eq!(retained.call(),call);assert_eq!(retained.room(),tasks[0].room());assert!(retained.membership()>0);
        held.insert(call.caller.account,retained);
    }
    (sessions,c,m,tasks,bindings,facts,held)
}
fn close(sessions:&mut[Session],c:&mut Controller,index:usize,b:&Bindings,f:&Facts){
    let call=receive::bound_call(&sessions[index],b).unwrap().0;
    c.retire(call.caller,call.channel,f,0).unwrap();sessions[index].active=false;
    assert!(!c.is_current_recipient(call.caller,call.channel,sessions[index].identity.as_ref().unwrap().database_id));
}

#[test]fn p10b_retained_selected_actual_SQL_reference_survives_disconnect_only_as_facts(){
    let now=Instant::now();let(mut sessions,mut c,_m,tasks,b,f,held)=preparing(now,false);
    close(&mut sessions,&mut c,0,&b,&f);let before=c.clone();
    assert!(receive::current_facts(&sessions,&c,&f).is_err());
    let facts=receive::current_facts_with_retained(&sessions,&c,&f,&b,&held).unwrap();assert_eq!(facts.len(),2);
    for task in &tasks{assert_eq!(facts[&task.caller().account].selected,f[&task.caller().account].selected);}
    let mut batch=Batch::default();batch.bodies.insert(tasks[0].caller().account,vec![native::left()]);let snapshot=sessions.clone();
    assert!(receive::stage_batch(&mut sessions,&c,&batch,&b,&facts,None,None).is_err());same(&sessions,&snapshot,now);assert_eq!(c,before);
    close(&mut sessions,&mut c,1,&b,&facts);let second=receive::current_facts_with_retained(&sessions,&c,&f,&b,&held).unwrap();assert_eq!(facts,second);
    assert!(tasks.iter().all(|t|c.registry().claim(t.caller().account)==Some(room::Claim::Room(t.room()))));
}
#[test]fn p10b_retained_selected_actual_origin_poison_fails_without_new_recipient_or_claim_release(){
    let now=Instant::now();let(mut sessions,mut c,_m,tasks,b,f,held)=preparing(now,false);close(&mut sessions,&mut c,0,&b,&f);
    for poison in 0..11{let mut copy=sessions.clone();let mut bindings=b.clone();let mut retained=held.clone();let who=tasks[0].caller().account;
        match poison{
            0=>copy[0].active=true,
            1=>copy[0].shared.as_mut().unwrap().profile13.as_mut().unwrap().in_flight=false,
            2=>copy[0].shared.as_mut().unwrap().return_generation+=1,
            3=>{bindings.insert(copy[0].id,[9;32]);},
            4=>{retained.remove(&who);},
            5=>{let old=copy[0].ammo_service.as_ref().unwrap().revision();copy[0].ammo_service.as_mut().unwrap().refresh_revision(old+1).unwrap();},
            6=>{copy.remove(0);},
            7=>{let owner=copy[0].identity.as_ref().unwrap();copy[0].identity=Some(Arc::new(crate::identity091::Profile{account_id:owner.account_id.clone(),database_id:owner.database_id+10,name:owner.name.clone(),fixture_dir:owner.fixture_dir.clone()}));},
            8=>{copy[0].shared.as_mut().unwrap().join_requested=true;},
            9=>{copy[0].shared.as_mut().unwrap().profile13.as_mut().unwrap().run_id="12345678-1234-4234-8234-123456789abc".into();},
            _=>{copy[0].shared.as_mut().unwrap().profile13.as_mut().unwrap().revision+=1;},
        }
        let before=c.clone();assert!(receive::current_facts_with_retained(&copy,&c,&f,&bindings,&retained).is_err(),"poison {poison}");assert_eq!(c,before);
    }
}
#[test]fn p10b_retained_capture_rejects_forged_selected_class_and_still_live_unretired_account(){
    let now=Instant::now();let(mut sessions,mut c,_m,tasks,b,f,held)=preparing(now,false);
    let wrong=receive::RetainedReady{task:tasks[1].clone(),reference:f[&tasks[1].caller().account].selected.clone().unwrap()};
    assert!(receive::RetainedMember::capture(&sessions[0],&c,&b,&f[&tasks[0].caller().account],Some(wrong)).is_err());
    assert!(receive::RetainedMember::capture(&sessions[0],&c,&b,&f[&tasks[0].caller().account],None).is_err());
    sessions[0].active=false;assert!(receive::current_facts_with_retained(&sessions,&c,&f,&b,&held).is_err());
    sessions[0].active=true;close(&mut sessions,&mut c,0,&b,&f);assert!(receive::RetainedMember::capture(&sessions[0],&c,&b,&f[&tasks[0].caller().account],None).is_err());
}
#[test]fn p10b_retained_bench_disconnect_is_display_only_no_ready_guard_or_selected_slot(){
    let now=Instant::now();let(mut sessions,mut c,_m,tasks,b,f,held)=preparing(now,true);
    let bench=receive::bound_call(&sessions[2],&b).unwrap().0;assert!(f[&bench.caller.account].selected.is_none());
    assert!(!c.registry().room(tasks[0].room()).unwrap().preparing().unwrap().members().iter().any(|m|m.account()==bench.caller.account));
    assert!(!sessions[2].shared.as_ref().unwrap().profile13.as_ref().unwrap().in_flight);
    close(&mut sessions,&mut c,2,&b,&f);let facts=receive::current_facts_with_retained(&sessions,&c,&f,&b,&held).unwrap();assert_eq!(facts[&bench.caller.account],f[&bench.caller.account]);
    assert!(facts[&bench.caller.account].selected.is_none());let original=c.clone();
    let mut bad=sessions.clone();bad[2].shared.as_mut().unwrap().profile13.as_mut().unwrap().in_flight=true;
    assert!(receive::current_facts_with_retained(&bad,&c,&f,&b,&held).is_err());assert_eq!(c,original);
    // Real legacy garage completion could advance this cursor. The first
    // version fails closed rather than upgrading old display provenance.
    let old=sessions[2].ammo_service.as_ref().unwrap().revision();sessions[2].ammo_service.as_mut().unwrap().refresh_revision(old+1).unwrap();
    assert!(receive::current_facts_with_retained(&sessions,&c,&f,&b,&held).is_err());assert_eq!(c,original);
}
#[test]fn p10b_retained_external_fact_replacement_never_changes_disconnected_display(){
    let now=Instant::now();let(mut sessions,mut c,_m,tasks,b,mut f,held)=preparing(now,false);close(&mut sessions,&mut c,0,&b,&f);
    let who=tasks[0].caller().account;let expected=f[&who].clone();let fact=f.get_mut(&who).unwrap();fact.database_id+=1;fact.descriptor=vec![0xff];fact.selected=None;
    assert_eq!(receive::current_facts_with_retained(&sessions,&c,&f,&b,&held).unwrap()[&who],expected);
}
#[test]fn p10b_retained_actual_second_Session_leave_frame_commits_without_reviving_disconnected_recipient(){
    let now=Instant::now();let(mut sessions,mut c,_m,tasks,b,f,held)=preparing(now,false);close(&mut sessions,&mut c,0,&b,&f);
    let id=sessions[1].id;let mut payload=vec![0x8e,20,0];payload.extend(240i16.to_le_bytes());payload.extend(401i16.to_le_bytes());payload.extend(0i64.to_le_bytes());payload.extend(0i32.to_le_bytes());payload.extend(0i32.to_le_bytes());
    let frame=Frame{flags:0x458,sequence:Some(sessions[1].rx),cumulative:Some(0),selective:Vec::new(),body:[vec![1],sessions[1].token.to_le_bytes().to_vec(),payload].concat(),piggybacks:Vec::new()};
    let world=World::new_for_map(701,now,crate::map_profile091::MapId::Prohorovka).unwrap();let old_rx=sessions[1].rx;
    let out=receive::receive_room_frame_with_retained(&mut sessions,&mut c,id,&frame,&world,&b,&f,now,0,false,&held).unwrap();
    assert!(out.refusals.is_empty()&&out.ready.is_empty()&&out.prepare.is_empty());assert!(sessions[1].rx>old_rx);
    assert!(!sessions[0].active);assert!(!c.is_current_recipient(tasks[0].caller(),tasks[0].channel(),sessions[0].identity.as_ref().unwrap().database_id));
    let r=c.registry().room(tasks[0].room()).unwrap();assert!(r.abort_requested()&&r.preparing().is_some());
    assert_eq!(r.members().count(),2);assert!(tasks.iter().all(|t|c.registry().claim(t.caller().account)==Some(room::Claim::Room(t.room()))));
    // Preparing Leave is deferred, never a fabricated immediate completion.
    assert!(!bodies(&sessions[1],now).contains(&native::plain_response(240,native::CommandResult::Success,"").unwrap()));
}
#[test]fn p10b_retained_bench_old_persistence_cursor_is_not_owned_ready_or_current_garage_revision(){
    let now=Instant::now();let(mut sessions,mut c,_m,_tasks,b,f,mut held)=preparing(now,true);
    let call=receive::bound_call(&sessions[2],&b).unwrap().0;let old=sessions[2].shared.as_ref().unwrap().profile13.as_ref().unwrap().revision;
    // AUTHORED pre-existing cursor lag models ordinary garage mutation: a
    // bench has no accepted owned Ready and does not allocate battle contexts.
    assert!(old>13);sessions[2].shared.as_mut().unwrap().profile13.as_mut().unwrap().revision=old-1;
    let captured=receive::RetainedMember::capture(&sessions[2],&c,&b,&f[&call.caller.account],None).unwrap();held.insert(call.caller.account,captured);
    close(&mut sessions,&mut c,2,&b,&f);assert!(receive::current_facts_with_retained(&sessions,&c,&f,&b,&held).unwrap()[&call.caller.account].selected.is_none());
    sessions[2].shared.as_mut().unwrap().profile13.as_mut().unwrap().revision=old;
    assert!(receive::current_facts_with_retained(&sessions,&c,&f,&b,&held).is_err());
}
