//! Actual Session/Frame/Window + Controller tests. Tiny authored Account caches;
//! no live identity/writer/owned validation, socket, original-client or native UI.
use super::*;
use std::sync::atomic::{AtomicU64,Ordering};

fn account(n:u32,now:Instant)->Session{
    static SERIAL:AtomicU64=AtomicU64::new(0);
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/p10b-receive-host");fs::create_dir_all(&root).unwrap();
    let nanos=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let dir=root.join(format!("{}-{nanos}-{}",std::process::id(),SERIAL.fetch_add(1,Ordering::Relaxed)));fs::create_dir(&dir).unwrap();
    fs::write(dir.join("state.bin"),b"\x80\x02}(U\x03revK\x01u.").unwrap();fs::write(dir.join("shop.bin"),b"\x80\x02}(U\x03revK\x03u.").unwrap();
    fs::write(dir.join("dossier.bin"),b"\x80\x02(K\x00]t.").unwrap();
    let mut s=Session::new(n,[n as u8;16],format!("127.0.0.1:{}",42000+n).parse().unwrap(),now);
    s.identity=Some(Arc::new(crate::identity091::Profile{account_id:format!("{n:08x}-1234-4234-8234-123456789abc"),database_id:n as i32,name:format!("Player{n}"),fixture_dir:dir.clone()}));
    s.hangar=Some(Arc::new(crate::hangar091::Fixtures::load_interactive(&dir).unwrap()));
    s.base_peer=Some(format!("127.0.0.1:{}",43000+n).parse().unwrap());s.account_probe=true;s.account_ready=true;s.active=true;s.sync_mask=7;s.rx=1;
    s.training_opt_in=true;s.training_flights=Some(flight::Flights::default());s.tx=Window::interactive();
    s.ammo_service=Some(ammo_session::State::new(crate::ammo_service091::Metadata{revision:13,wire_revision:1},false));s
}
type Facts=BTreeMap<Account,NativeFacts>;
type Bindings=BTreeMap<u32,[u8;32]>;
fn fixture(n:u32,now:Instant)->(Vec<Session>,Controller,World,Bindings,Facts){
    let sessions=(1..=n).map(|id|account(id,now)).collect::<Vec<_>>();let mut bindings=Bindings::new();let mut facts=Facts::new();
    for s in &sessions{bindings.insert(s.id,[s.id as u8;32]);facts.insert(account_id(&s.identity.as_ref().unwrap().account_id).unwrap(),NativeFacts{
        database_id:s.id as i32,selected:None,descriptor:Vec::new(),igr_type:0,clan_database_id:0,clan_abbrev:String::new()});}
    (sessions,Controller::default(),World::new_for_map(701,now,crate::map_profile091::MapId::Prohorovka).unwrap(),bindings,facts)
}
fn rpc(id:i16,command:i16,a:i64,b:i32)->Vec<u8>{let mut p=vec![0x8e,20,0];p.extend(id.to_le_bytes());p.extend(command.to_le_bytes());p.extend(a.to_le_bytes());p.extend(b.to_le_bytes());p.extend(0i32.to_le_bytes());p}
fn create()->Vec<u8>{let comment=b"source-bound";let mut p=Vec::new();p.extend(4i32.to_le_bytes());p.extend(600i32.to_le_bytes());p.push(1);p.push(comment.len()as u8);p.extend(comment);let mut body=vec![0x9a];body.extend((p.len()as u16).to_le_bytes());body.extend(p);body}
fn listing(start:i32,end:i32)->Vec<u8>{let mut p=vec![0x97,28,0];p.extend(200i16.to_le_bytes());p.extend(520i16.to_le_bytes());for v in[5,2,7,0,start,end]{p.extend(v.to_le_bytes());}p}
fn frame(s:&Session,n:u32,payload:&[u8])->Frame{Frame{flags:0x458,sequence:Some(n),cumulative:Some(0),selective:Vec::new(),body:[vec![1],s.token.to_le_bytes().to_vec(),payload.to_vec()].concat(),piggybacks:Vec::new()}}
fn bodies(s:&Session,now:Instant)->Vec<Vec<u8>>{let mut tx=s.tx.clone();let mut result=Vec::new();while let Some((_,_,raw))=tx.due(now,s.rx).unwrap(){result.push(transport091::parse_interactive(&raw).unwrap().body);}result.extend(s.outbox.iter().cloned());result}
fn send(sessions:&mut Vec<Session>,engine:&mut Controller,w:&World,b:&Bindings,f:&Facts,id:u32,payload:&[u8],now:Instant)->io::Result<RoomReceived>{
    let s=sessions.iter().find(|s|s.id==id).unwrap();let p=frame(s,s.rx,payload);receive_room_frame(sessions,engine,id,&p,w,b,f,now,0)
}
fn flush(sessions:&mut Vec<Session>,engine:&mut Controller,w:&World,b:&Bindings,f:&Facts,now:Instant){
    for _ in 0..64{let mut progressed=false;
        for index in 0..sessions.len(){let mut last=None;let s=&mut sessions[index];while let Some((seq,_,_))=s.tx.due(now,s.rx).unwrap(){last=Some(seq);}
            if let Some(last)=last{let id=s.id;let ack=Frame{flags:0,cumulative:Some(last+1),selective:Vec::new(),sequence:None,body:Vec::new(),piggybacks:Vec::new()};
                receive_room_frame(sessions,engine,id,&ack,w,b,f,now,0).unwrap();progressed=true;}
        }
        if !progressed{assert!(sessions.iter().all(|s|s.outbox.is_empty()&&s.tx.len()==0));return;}
    }panic!("bounded flush did not finish")
}
fn same(a:&[Session],b:&[Session],now:Instant){assert_eq!(a.len(),b.len());for(a,b)in a.iter().zip(b){
    assert_eq!((a.id,a.rx,a.last_rx,a.active,a.sync_mask,a.language,a.stats_requests),(b.id,b.rx,b.last_rx,b.active,b.sync_mask,b.language,b.stats_requests));
    assert_eq!(a.request_ids,b.request_ids);assert_eq!(a.unsupported_request_ids,b.unsupported_request_ids);assert_eq!(a.training_ids,b.training_ids);assert_eq!(a.training_ids_generation,b.training_ids_generation);
    assert_eq!(a.chat_request_ids,b.chat_request_ids);assert_eq!(a.received,b.received);assert_eq!(a.outbox,b.outbox);assert_eq!(a.ammo_service,b.ammo_service);assert_eq!(a.training_flights,b.training_flights);
    assert_eq!(a.tx.cumulative,b.tx.cumulative);assert_eq!(bodies(a,now),bodies(b,now));
    let(mut ta,mut tb)=(a.tx.clone(),b.tx.clone());assert_eq!(ta.enqueue_body_tracked(b"counter").ok(),tb.enqueue_body_tracked(b"counter").ok());
}}
fn room(engine:&Controller,s:&Session)->(room::RoomKey,u32){let a=account_id(&s.identity.as_ref().unwrap().account_id).unwrap();let key=engine.registry().authenticated_room(room::AuthLease{account:a,generation:u64::from(s.id)}).unwrap();(key,engine.native_room(key).unwrap())}
fn peer_alias(bodies:&[Vec<u8>],name:&str)->u32{
    let b=bodies.iter().find(|b|b.starts_with(&[0x13,0x56])&&b[3]==2&&b.windows(name.len()).any(|s|s==name.as_bytes())).unwrap();
    assert_eq!(&b[5..8],b"\x80\x02(");match b[8]{b'K'=>u32::from(b[9]),b'M'=>u32::from(u16::from_le_bytes(b[9..11].try_into().unwrap())),b'J'=>u32::try_from(i32::from_le_bytes(b[9..13].try_into().unwrap())).unwrap(),_=>panic!("closed native integer")}
}

#[test]fn p10b_receive_host_actual_create_join_incremental_alias_and_typed_refusal(){
    let now=Instant::now();let(mut sessions,mut c,w,b,f)=fixture(2,now);
    let made=send(&mut sessions,&mut c,&w,&b,&f,1,&create(),now).unwrap();assert!(made.refusals.is_empty()&&made.ready.is_empty()&&made.prepare.is_empty());
    let(k,native)=room(&c,&sessions[0]);assert!(bodies(&sessions[0],now).iter().any(|p|p.starts_with(&[0x13,0x46])));flush(&mut sessions,&mut c,&w,&b,&f,now);
    send(&mut sessions,&mut c,&w,&b,&f,2,&rpc(202,400,i64::from(native),0),now).unwrap();
    let owner=bodies(&sessions[0],now);assert!(!owner.iter().any(|p|p.starts_with(&[0x13,0x46])));let alias=peer_alias(&owner,"Player2");
    assert_ne!(alias,crate::training091::aliases::OWN_ENTITY_ID);flush(&mut sessions,&mut c,&w,&b,&f,now);
    let assigned=send(&mut sessions,&mut c,&w,&b,&f,1,&rpc(221,404,i64::from(alias),2),now).unwrap();assert!(assigned.refusals.is_empty());
    let second=account_id(&sessions[1].identity.as_ref().unwrap().account_id).unwrap();assert_eq!(c.registry().room(k).unwrap().members().find(|m|m.account()==second).unwrap().roster(),room::Roster::assigned(room::Side::Two));
    let before=c.clone();let refused=send(&mut sessions,&mut c,&w,&b,&f,2,&rpc(221,405,0,0),now).unwrap();assert_eq!(c,before);assert_eq!(refused.refusals.len(),1);
    assert!(bodies(&sessions[1],now).contains(&native::plain_response(221,native::CommandResult::Failure,"P10B_ROOM_REFUSED").unwrap()));
}
#[test]fn p10b_receive_host_child_ack_and_late_poison_roll_back_all_sessions_engine_and_ids(){
    let now=Instant::now();let(mut sessions,mut c,w,b,f)=fixture(2,now);
    sessions[0].tx.enqueue_body(b"real sent prefix").unwrap();sessions[0].tx.due(now,1).unwrap().unwrap();
    let mut child=frame(&sessions[0],1,&create());child.cumulative=Some(1);
    let mut parent=frame(&sessions[0],2,&rpc(220,401,0,0));parent.cumulative=Some(1);parent.piggybacks.push(child);
    let before=sessions.clone();let engine=c.clone();assert!(receive_room_frame(&mut sessions,&mut c,1,&parent,&w,&b,&f,now,0).is_err());same(&sessions,&before,now);assert_eq!(c,engine);
}
#[test]fn p10b_receive_host_cross_peer_outbox_and_late_actual_window_failure_are_atomic(){
    for exhausted_window in[false,true]{let now=Instant::now();let(mut sessions,mut c,w,b,f)=fixture(2,now);
        send(&mut sessions,&mut c,&w,&b,&f,1,&create(),now).unwrap();let(_,native)=room(&c,&sessions[0]);flush(&mut sessions,&mut c,&w,&b,&f,now);
        if exhausted_window{sessions[0].tx=Window::new();
            for n in 0..transport091::MAX_SEQUENCE{sessions[0].tx.enqueue_body(b"sent").unwrap();assert_eq!(sessions[0].tx.due(now,1).unwrap().unwrap().0,n);
                let ack=Frame{flags:0,sequence:None,cumulative:Some(n+1),selective:Vec::new(),body:Vec::new(),piggybacks:Vec::new()};sessions[0].tx.acknowledge(&ack).unwrap();}
            sessions[0].outbox.push_back(native::left());
        }else{sessions[0].outbox=VecDeque::from(vec![native::left();native::MAX_OUTBOX]);}
        // Receiver drains first; failure of the later peer must discard even
        // its newly enqueued reliable initialization bytes and alias changes.
        sessions.swap(0,1);let before=sessions.clone();let engine=c.clone();
        assert!(send(&mut sessions,&mut c,&w,&b,&f,2,&rpc(202,400,i64::from(native),0),now).is_err());same(&sessions,&before,now);assert_eq!(c,engine);
    }
}
#[test]fn p10b_receive_host_compound_child_legacy_and_room_callbacks_preserve_record_offsets(){
    let now=Instant::now();let(mut sessions,mut c,w,b,f)=fixture(1,now);send(&mut sessions,&mut c,&w,&b,&f,1,&create(),now).unwrap();flush(&mut sessions,&mut c,&w,&b,&f,now);
    sessions[0].outbox.push_back(native::left());let child=frame(&sessions[0],sessions[0].rx,&rpc(221,403,1,0));
    let payload=[rpc(222,101,0,0),rpc(223,405,0,0)].concat();let mut parent=frame(&sessions[0],sessions[0].rx+1,&payload);parent.piggybacks.push(child);
    let out=receive_room_frame(&mut sessions,&mut c,1,&parent,&w,&b,&f,now,0).unwrap();assert!(out.refusals.is_empty());let q=bodies(&sessions[0],now);
    let first=native::plain_response(221,native::CommandResult::Success,"").unwrap();let old=crate::hangar091::unavailable_response(222).unwrap();let last=native::plain_response(223,native::CommandResult::Success,"").unwrap();
    assert_eq!(q.first(),Some(&native::left()));let a=q.iter().position(|p|p==&first).unwrap();let mid=q.iter().position(|p|p==&old).unwrap();let z=q.iter().position(|p|p==&last).unwrap();assert!(a<mid&&mid<z);
    assert_eq!(sessions[0].training_ids,[221,223]);assert_eq!(sessions[0].unsupported_request_ids,VecDeque::from([222]));
}
#[test]fn p10b_receive_host_final_legacy_namespace_collision_is_atomic_across_children(){
    let now=Instant::now();let(mut sessions,mut c,w,b,f)=fixture(1,now);
    send(&mut sessions,&mut c,&w,&b,&f,1,&create(),now).unwrap();flush(&mut sessions,&mut c,&w,&b,&f,now);
    let child=frame(&sessions[0],sessions[0].rx,&rpc(221,403,1,0));let mut parent=frame(&sessions[0],sessions[0].rx+1,&rpc(221,101,0,0));parent.piggybacks.push(child);
    let before=sessions.clone();let engine=c.clone();assert!(receive_room_frame(&mut sessions,&mut c,1,&parent,&w,&b,&f,now,0).is_err());same(&sessions,&before,now);assert_eq!(c,engine);
}
#[test]fn p10b_receive_host_missing_source_wrong_database_and_duplicate_live_identity_fail_closed(){
    for poison in 0..5{let now=Instant::now();let(mut sessions,mut c,w,mut b,mut f)=fixture(2,now);
        let key=account_id(&sessions[0].identity.as_ref().unwrap().account_id).unwrap();match poison{
            0=>{b.remove(&1);},1=>{b.insert(1,[0;32]);},2=>{f.get_mut(&key).unwrap().database_id=99;},
            3=>{let p=sessions[0].identity.as_ref().unwrap();let new=crate::identity091::Profile{account_id:p.account_id.to_uppercase(),database_id:p.database_id,name:p.name.clone(),fixture_dir:p.fixture_dir.clone()};sessions[0].identity=Some(Arc::new(new));},
            _=>{let p=sessions[1].identity.as_ref().unwrap();let new=crate::identity091::Profile{account_id:sessions[0].identity.as_ref().unwrap().account_id.clone(),database_id:p.database_id,name:p.name.clone(),fixture_dir:p.fixture_dir.clone()};sessions[1].identity=Some(Arc::new(new));}
        }
        let before=sessions.clone();let engine=c.clone();assert!(send(&mut sessions,&mut c,&w,&b,&f,1,&create(),now).is_err(),"poison {poison}");same(&sessions,&before,now);assert_eq!(c,engine);
    }
}
#[test]fn p10b_receive_host_keepalive_does_not_rebind_warm_claimed_account_but_stale_peer_publication_rejects(){
    let now=Instant::now();let(mut sessions,mut c,w,b,f)=fixture(2,now);send(&mut sessions,&mut c,&w,&b,&f,1,&create(),now).unwrap();let(_,native)=room(&c,&sessions[0]);flush(&mut sessions,&mut c,&w,&b,&f,now);
    sessions[0].drive_return_account=Some(WarmAccountReturn{generation:1,queue_ahead:0,creation:Some((0,true)),enabled:true,stale_avatar_envelopes:0});
    assert_eq!(sessions[0].training_account_generation(),2);let engine=c.clone();let ack=Frame{flags:0,sequence:None,cumulative:Some(sessions[0].tx.cumulative),selective:Vec::new(),body:Vec::new(),piggybacks:Vec::new()};
    let out=receive_room_frame(&mut sessions,&mut c,1,&ack,&w,&b,&f,now,0).unwrap();assert!(out.refusals.is_empty()&&out.ready.is_empty()&&out.prepare.is_empty());assert_eq!(c,engine);
    let before=sessions.clone();assert!(send(&mut sessions,&mut c,&w,&b,&f,2,&rpc(202,400,i64::from(native),0),now).is_err());same(&sessions,&before,now);assert_eq!(c,engine);
}
#[test]fn p10b_receive_host_busy_listing_and_preview_defer_without_interleaved_stream_or_fake_empty(){
    let now=Instant::now();let(mut sessions,mut c,w,b,f)=fixture(1,now);send(&mut sessions,&mut c,&w,&b,&f,1,&create(),now).unwrap();let(_,native)=room(&c,&sessions[0]);flush(&mut sessions,&mut c,&w,&b,&f,now);
    send(&mut sessions,&mut c,&w,&b,&f,1,&listing(0,50),now).unwrap();assert!(sessions[0].training_flights.as_ref().unwrap().busy(flight::Kind::Listing));let q=bodies(&sessions[0],now);let rev=c.read_revision();
    let payload=[listing(0,50),rpc(201,523,i64::from(native),0)].concat();let out=send(&mut sessions,&mut c,&w,&b,&f,1,&payload,now).unwrap();assert_eq!(out.deferred_reads.len(),1);assert!(out.refusals.is_empty());
    let deferred=&out.deferred_reads[0];assert_eq!(deferred.read,flight::ReadRevision::Listing(rev));assert_eq!(deferred.context.kind(),flight::Kind::Listing);assert_eq!(deferred.call.channel.generation,1);
    let after=bodies(&sessions[0],now);assert_eq!(after.iter().filter(|p|p.first()==Some(&52)&&p[3..5]==200i16.to_le_bytes()).count(),q.iter().filter(|p|p.first()==Some(&52)&&p[3..5]==200i16.to_le_bytes()).count());
    assert!(sessions[0].training_flights.as_ref().unwrap().busy(flight::Kind::Preview));
    let out=send(&mut sessions,&mut c,&w,&b,&f,1,&[listing(0,50),rpc(201,523,i64::from(native),0)].concat(),now).unwrap();assert_eq!(out.deferred_reads.len(),2);assert!(out.refusals.is_empty());
    flush(&mut sessions,&mut c,&w,&b,&f,now);assert!(!sessions[0].training_flights.as_ref().unwrap().busy(flight::Kind::Listing));assert!(!sessions[0].training_flights.as_ref().unwrap().busy(flight::Kind::Preview));
}
#[test]fn p10b_receive_host_ready_job_is_deferred_and_prior_notready_cannot_resurrect_cached_facts(){
    let now=Instant::now();let(mut sessions,mut c,w,b,mut f)=fixture(2,now);send(&mut sessions,&mut c,&w,&b,&f,1,&create(),now).unwrap();let(k,native)=room(&c,&sessions[0]);flush(&mut sessions,&mut c,&w,&b,&f,now);
    send(&mut sessions,&mut c,&w,&b,&f,2,&rpc(202,400,i64::from(native),0),now).unwrap();let alias=peer_alias(&bodies(&sessions[0],now),"Player2");flush(&mut sessions,&mut c,&w,&b,&f,now);
    send(&mut sessions,&mut c,&w,&b,&f,1,&rpc(230,404,i64::from(alias),2),now).unwrap();flush(&mut sessions,&mut c,&w,&b,&f,now);
    for who in 1..=2{let job=send(&mut sessions,&mut c,&w,&b,&f,who,&rpc(221,402,1,0),now).unwrap();assert_eq!(job.ready.len(),1);assert!(job.prepare.is_empty());
        let index=(who-1)as usize;let call=bound_call(&sessions[index],&b).unwrap().0;
        assert!(c.registry().room(k).unwrap().members().find(|m|m.account()==call.caller.account).unwrap().ready().is_none());
        // Fixture completion supplies explicit synthetic verified-DTO metadata;
        // it proves no real writer ownership, SQL CAS or network callback.
        let selected=room::WriterReadyRef::from_verified_writer(call.caller.account,format!("fixture-vehicle-{who}"),13,[who as u8;32]).unwrap();let fact=f.get_mut(&call.caller.account).unwrap();fact.selected=Some(selected.clone());fact.descriptor=vec![who as u8,2,3];
        let batch=c.complete_ready(&job.ready[0],call,1,selected,&f,0).unwrap();stage_batch(&mut sessions,&c,&batch,&b,&f,None,None).unwrap();for s in &mut sessions{s.drain_outbox().unwrap();}
        flush(&mut sessions,&mut c,&w,&b,&f,now);
    }
    let out=send(&mut sessions,&mut c,&w,&b,&f,1,&[rpc(222,403,1,0),rpc(223,405,0,0)].concat(),now).unwrap();assert!(out.refusals.is_empty()&&out.ready.is_empty()&&out.prepare.is_empty());
    let own=account_id(&sessions[0].identity.as_ref().unwrap().account_id).unwrap();let peer=account_id(&sessions[1].identity.as_ref().unwrap().account_id).unwrap();
    assert!(c.registry().room(k).unwrap().members().find(|m|m.account()==own).unwrap().ready().is_none());
    assert_eq!(c.registry().room(k).unwrap().members().find(|m|m.account()==peer).unwrap().ready(),f[&peer].selected.as_ref());
}
#[test]fn p10b_receive_host_busy_invalid_read_is_typed_refusal_without_deferred_or_empty_stream(){
    let now=Instant::now();let(mut sessions,mut c,w,b,f)=fixture(1,now);send(&mut sessions,&mut c,&w,&b,&f,1,&create(),now).unwrap();flush(&mut sessions,&mut c,&w,&b,&f,now);
    send(&mut sessions,&mut c,&w,&b,&f,1,&listing(0,50),now).unwrap();let before=bodies(&sessions[0],now);let revision=c.read_revision();
    let got=send(&mut sessions,&mut c,&w,&b,&f,1,&listing(-1,50),now).unwrap();assert_eq!(got.refusals.len(),1);assert_eq!(got.refusals[0].refusal,Refusal::BadArgs);assert!(got.deferred_reads.is_empty());
    assert_eq!(bodies(&sessions[0],now),before);assert_eq!(c.read_revision(),revision);
}


#[test]fn p10b_receive_host_unavailable_launch_refuses_both411_without_votes_preparing_or_jobs(){
    let now=Instant::now();let(mut sessions,mut c,w,b,f)=fixture(1,now);send(&mut sessions,&mut c,&w,&b,&f,1,&create(),now).unwrap();flush(&mut sessions,&mut c,&w,&b,&f,now);
    let engine=c.clone();let payload=[rpc(221,411,1,0),rpc(222,411,2,1)].concat();let p=frame(&sessions[0],sessions[0].rx,&payload);
    let out=receive_room_frame_with_launch(&mut sessions,&mut c,1,&p,&w,&b,&f,now,0,false).unwrap();
    assert_eq!(out.refusals.len(),2);assert!(out.refusals.iter().all(|r|r.refusal==Refusal::Busy));
    assert!(out.ready.is_empty()&&out.prepare.is_empty()&&out.events.is_empty());assert_eq!(c,engine);
    let q=bodies(&sessions[0],now);for id in[221,222]{assert!(q.contains(&native::plain_response(id,native::CommandResult::Failure,"P10B_ROOM_REFUSED").unwrap()));}
    assert!(c.registry().rooms().all(|r|r.preparing().is_none()&&r.team_ready()==[false;2]));
}
