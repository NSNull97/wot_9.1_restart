//! NOT_RUN candidate. Actual Session/Frame/Window, authored tiny Account cache.
//! The transaction helper models only the outer clone/collect/claim/drain seam;
//! it is NOT a Registry/Controller, writer, native callback or room UI proof.
use super::*;
use std::sync::atomic::{AtomicU64,Ordering};

fn account(now:Instant)->Session{
    static SERIAL:AtomicU64=AtomicU64::new(0);
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/p10b-request-namespace");
    fs::create_dir_all(&root).unwrap();
    let nanos=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let dir=root.join(format!("{}-{nanos}-{}",std::process::id(),SERIAL.fetch_add(1,Ordering::Relaxed)));
    fs::create_dir(&dir).unwrap();
    fs::write(dir.join("state.bin"),b"\x80\x02}(U\x03revK\x01u.").unwrap();
    fs::write(dir.join("shop.bin"),b"\x80\x02}(U\x03revK\x03u.").unwrap();
    fs::write(dir.join("dossier.bin"),b"\x80\x02(K\x00]t.").unwrap();
    let fixtures=Arc::new(crate::hangar091::Fixtures::load_interactive(&dir).unwrap());
    let mut s=Session::new(7,[7;16],"127.0.0.1:41917".parse().unwrap(),now);
    s.identity=Some(Arc::new(crate::identity091::Profile{account_id:"12345678-1234-4234-8234-123456789abc".into(),
        database_id:7,name:"p10b-request-namespace-fixture".into(),fixture_dir:dir}));
    s.hangar=Some(fixtures);s.account_probe=true;s.account_ready=true;s.active=true;s.sync_mask=7;s.rx=1;
    s.base_peer=Some("127.0.0.1:41918".parse().unwrap());s.tx=Window::interactive();s.training_opt_in=true;
    s.ammo_service=Some(ammo_session::State::new(crate::ammo_service091::Metadata{revision:13,wire_revision:1},false));s
}
fn rpc(id:i16,command:i16,a:i64,b:i32)->Vec<u8>{
    let mut v=vec![0x8e,20,0];v.extend(id.to_le_bytes());v.extend(command.to_le_bytes());
    v.extend(a.to_le_bytes());v.extend(b.to_le_bytes());v.extend(0i32.to_le_bytes());v
}
fn language(id:i16)->Vec<u8>{
    let mut v=vec![0x95,7,0];v.extend(id.to_le_bytes());v.extend(1000i16.to_le_bytes());v.extend([2,b'r',b'u']);v
}
fn ammo(id:i16)->Vec<u8>{
    let mut v=vec![0x97,72,0];v.extend(id.to_le_bytes());v.extend(108i16.to_le_bytes());v.extend(16u32.to_le_bytes());
    for n in [1i32,1,6,2570,20,2826,0,3082,0,6,0,0,0,0,0,0]{v.extend(n.to_le_bytes());}v
}
fn frame(s:&Session,n:u32,payload:&[u8])->Frame{
    Frame{flags:0x458,sequence:Some(n),cumulative:Some(0),selective:Vec::new(),
        body:[vec![1],s.token.to_le_bytes().to_vec(),payload.to_vec()].concat(),piggybacks:Vec::new()}
}
fn collect(s:&mut Session,f:&Frame,now:Instant)->io::Result<TrainingReceived>{
    let mut staged=s.clone();let got=staged.receive_training_collected(f,now)?;
    // Deliberately outside receive/child parse: every legacy ID is final now.
    for record in &got.records{
        if let crate::training091::ingress::Reply::Plain(id)=record.request.reply{staged.claim_training_request(id)?;}
    }
    staged.drain_outbox()?;*s=staged;Ok(got)
}
fn same(a:&Session,b:&Session,now:Instant){
    assert_eq!((a.rx,a.last_rx,a.active,a.account_ready,a.sync_mask,a.language,a.stats_requests),
        (b.rx,b.last_rx,b.active,b.account_ready,b.sync_mask,b.language,b.stats_requests));
    assert_eq!(a.request_ids,b.request_ids);assert_eq!(a.unsupported_request_ids,b.unsupported_request_ids);
    assert_eq!(a.training_ids,b.training_ids);assert_eq!(a.training_ids_generation,b.training_ids_generation);
    assert_eq!(a.chat_request_ids,b.chat_request_ids);assert_eq!(a.received,b.received);assert_eq!(a.outbox,b.outbox);
    assert_eq!(a.ammo_service,b.ammo_service);assert_eq!(a.account_cache_hash,b.account_cache_hash);
    assert_eq!(a.training_flights,b.training_flights);assert_eq!((a.tx.len(),a.tx.cumulative),(b.tx.len(),b.tx.cumulative));
    let(mut ta,mut tb)=(a.tx.clone(),b.tx.clone());let(mut wa,mut wb)=(Vec::new(),Vec::new());
    while let Some(row)=ta.due(now+transport091::RETRY,a.rx).unwrap(){wa.push(row);}
    while let Some(row)=tb.due(now+transport091::RETRY,b.rx).unwrap(){wb.push(row);}
    assert_eq!(wa,wb);
}
fn warm(s:&mut Session){
    // Authored completed warm boundary, same established helper as existing
    // Session tests. No native UI/ACK acceptance is asserted by this assignment.
    s.drive_return_account=Some(WarmAccountReturn{generation:1,queue_ahead:0,creation:Some((0,true)),enabled:true,stale_avatar_envelopes:0});
    s.request_ids.clear();s.unsupported_request_ids.clear();
    s.ammo_service.as_mut().unwrap().rebind(crate::ammo_service091::Metadata{revision:13,wire_revision:1}).unwrap();
}

#[test]
fn p10b_namespace_cross_frame_plain_and_language_ids_reject_both_orders(){
    let now=Instant::now();
    for room_first in [false,true]{
        let mut s=account(now);
        let first=if room_first{rpc(221,401,0,0)}else{language(221)};
        let f=frame(&s,1,&first);collect(&mut s,&f,now).unwrap();
        let before=s.clone();let second=if room_first{language(221)}else{rpc(221,405,0,0)};
        assert!(collect(&mut s,&frame(&before,2,&second),now).is_err());same(&s,&before,now);
        assert_eq!(s.training_ids,if room_first{vec![221]}else{vec![]});
        assert_eq!(s.request_ids,if room_first{vec![]}else{vec![221]});
    }
}

#[test]
fn p10b_namespace_cross_frame_plain_and_real_native_ammo_ids_reject_both_orders(){
    let now=Instant::now();
    for room_first in [false,true]{
        let mut s=account(now);
        let first=if room_first{rpc(226,401,0,0)}else{ammo(226)};
        let f=frame(&s,1,&first);collect(&mut s,&f,now).unwrap();
        assert_eq!(s.ammo_service.as_ref().unwrap().used_id(226),!room_first);
        let before=s.clone();let second=if room_first{ammo(226)}else{rpc(226,405,0,0)};
        assert!(collect(&mut s,&frame(&before,2,&second),now).is_err());same(&s,&before,now);
    }
}

#[test]
fn p10b_namespace_old_unavailable_history_blocks_later_plain_and_reverse(){
    let now=Instant::now();
    for room_first in [false,true]{
        let mut s=account(now);
        let first=if room_first{rpc(227,401,0,0)}else{rpc(227,101,0,0)};
        let f=frame(&s,1,&first);collect(&mut s,&f,now).unwrap();
        let before=s.clone();let second=if room_first{rpc(227,101,0,0)}else{rpc(227,405,0,0)};
        assert!(collect(&mut s,&frame(&before,2,&second),now).is_err());same(&s,&before,now);
    }
}

#[test]
fn p10b_namespace_actual_initial_sync_id_blocks_later_plain_in_same_account(){
    let now=Instant::now();let mut s=account(now);s.training_opt_in=false;s.sync_mask=0;
    let f=frame(&s,1,&rpc(236,100,0,0));s.receive(&f,now).unwrap();
    assert_eq!(s.request_ids,vec![236]);assert_eq!(s.sync_mask,1);
    s.training_opt_in=true;s.sync_mask=7;let before=s.clone();
    let f=frame(&s,2,&rpc(236,401,0,0));assert!(collect(&mut s,&f,now).is_err());same(&s,&before,now);
}

#[test]
fn p10b_namespace_late_piggyback_collision_rolls_back_actual_ack_history_and_pending_ammo(){
    let now=Instant::now();
    for ammo_legacy in [false,true]{for room_child in [false,true]{
        let mut s=account(now);s.outbox.push_back(vec![0xa0]);
        s.tx.enqueue_body(&[0xb0]).unwrap();s.tx.due(now,s.rx).unwrap().unwrap();
        let legacy=if ammo_legacy{ammo(228)}else{language(228)};
        let room=rpc(228,401,0,0);
        let mut child=frame(&s,1,if room_child{&room}else{&legacy});child.cumulative=Some(1);
        let mut parent=frame(&s,2,if room_child{&legacy}else{&room});
        parent.flags|=2;parent.cumulative=Some(1);parent.piggybacks.push(child);
        let before=s.clone();assert!(collect(&mut s,&parent,now+Duration::from_millis(1)).is_err());same(&s,&before,now);
        assert!(!s.ammo_service.as_ref().unwrap().used_id(228));assert_eq!(s.tx.cumulative,0);
    }}
}

#[test]
fn p10b_namespace_plain_collision_between_child_and_parent_rolls_back_earlier_claim(){
    let now=Instant::now();let mut s=account(now);
    let child=frame(&s,1,&rpc(229,401,0,0));let mut parent=frame(&s,2,&rpc(229,405,0,0));
    parent.flags|=2;parent.piggybacks.push(child);let before=s.clone();
    assert!(collect(&mut s,&parent,now).is_err());same(&s,&before,now);assert!(s.training_ids.is_empty());
}

#[test]
fn p10b_namespace_lifetime_budget_is512_and_never_consumes_legacy32_slots(){
    let now=Instant::now();let mut s=account(now);
    for id in 221..733{s.claim_training_request(id).unwrap();}
    assert_eq!(s.training_ids.len(),512);assert!(s.request_ids.is_empty());
    for id in [221,733,i16::MAX]{let before=s.clone();assert!(s.claim_training_request(id).is_err());same(&s,&before,now);}
    warm(&mut s);s.claim_training_request(i16::MAX).unwrap();assert_eq!(s.training_ids,vec![i16::MAX]);
    assert_eq!(s.training_ids_generation,2);assert!(s.request_ids.is_empty());
}

#[test]
fn p10b_namespace_warm_generation_ignores_old_ids_and_invalid_claim_does_not_clear(){
    let now=Instant::now();let mut s=account(now);s.claim_training_request(230).unwrap();
    assert!(s.training_request_used(230));warm(&mut s);assert!(!s.training_request_used(230));
    for id in [i16::MIN,-1,0,200,201,202,220]{
        let before=s.clone();assert!(s.claim_training_request(id).is_err());same(&s,&before,now);
        assert_eq!(s.training_ids_generation,1);assert_eq!(s.training_ids,vec![230]);
    }
    // A legitimate new-generation legacy request may reuse the old PRB ID.
    let f=frame(&s,1,&language(230));collect(&mut s,&f,now).unwrap();assert_eq!(s.request_ids,vec![230]);
    let before=s.clone();assert!(s.claim_training_request(230).is_err());same(&s,&before,now);
    assert_eq!(s.training_ids_generation,1,"legacy collision must not clear stale generation");
    s.claim_training_request(231).unwrap();assert_eq!(s.training_ids_generation,2);assert_eq!(s.training_ids,vec![231]);
}

#[test]
fn p10b_namespace_warm_generation_can_reuse_same_plain_id_after_ammo_epoch_rebind(){
    let now=Instant::now();let mut s=account(now);let f=frame(&s,1,&rpc(232,401,0,0));
    collect(&mut s,&f,now).unwrap();warm(&mut s);
    let f=frame(&s,2,&rpc(232,405,0,0));collect(&mut s,&f,now).unwrap();
    assert_eq!(s.training_ids,vec![232]);assert_eq!(s.training_ids_generation,2);assert_eq!(s.rx,3);
}

#[test]
fn p10b_namespace_fixed_list_preview_and_join_ids_remain_repeatable_across_frames(){
    let now=Instant::now();let mut s=account(now);s.claim_training_request(233).unwrap();
    let list=vec![0x97,28,0,200,0,8,2,5,0,0,0,2,0,0,0,7,0,0,0,0,0,0,0,0,0,0,0,50,0,0,0];
    let payload=[list,rpc(201,523,7,0),rpc(202,400,7,0)].concat();
    for n in 1..=2{
        let f=frame(&s,n,&payload);let got=collect(&mut s,&f,now).unwrap();assert_eq!(got.records.len(),3);
        assert_eq!(s.training_ids,vec![233]);assert!(s.request_ids.is_empty());
    }
    assert_eq!(s.rx,3);assert!(s.outbox.is_empty());assert_eq!(s.tx.len(),0);
}

#[test]
fn p10b_namespace_transport_retry_does_not_reclaim_application_id(){
    let now=Instant::now();let mut s=account(now);let f=frame(&s,1,&rpc(234,401,0,0));
    assert_eq!(collect(&mut s,&f,now).unwrap().records.len(),1);let before=s.clone();
    assert!(collect(&mut s,&f,now).unwrap().records.is_empty());same(&s,&before,now);assert_eq!(s.training_ids,vec![234]);
}

#[test]
fn p10b_namespace_default_mode_ignores_training_history_and_claim_is_closed(){
    let now=Instant::now();let mut s=account(now);s.claim_training_request(235).unwrap();s.training_opt_in=false;
    assert!(!s.training_request_used(235));let before=s.clone();assert!(s.claim_training_request(236).is_err());same(&s,&before,now);
    let f=frame(&s,1,&language(235));assert!(!s.receive(&f,now).unwrap());assert_eq!(s.request_ids,vec![235]);
    assert_eq!(s.training_ids,vec![235]);
}
