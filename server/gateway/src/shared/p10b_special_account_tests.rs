//! NOT_RUN: actual Session/Frame/Window/Results State; authored Account cache.
//! No HTTP worker, incoming pickle, Controller ownership or native UI claim.
use super::*;
use super::super::*;
use std::sync::atomic::{AtomicU64,Ordering};
fn account(now:Instant)->Session{
    static SERIAL:AtomicU64=AtomicU64::new(0);
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/p10b-special-account");
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
        database_id:7,name:"p10b-special-account-fixture".into(),fixture_dir:dir}));
    s.hangar=Some(fixtures);s.account_probe=true;s.account_ready=true;s.active=true;s.sync_mask=7;s.rx=1;
    s.base_peer=Some("127.0.0.1:41918".parse().unwrap());s.tx=Window::interactive();s.training_opt_in=true;
    s.ammo_service=Some(ammo_session::State::new(crate::ammo_service091::Metadata{revision:13,wire_revision:1},false));
    let mut client=Client::new(0);client.join_requested=false;
    client.profile13=Some(profile13_session::State::new("61ced794-71e9-4719-af94-7a606c431558".into(),13).unwrap());s.shared=Some(client);s
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
    assert_eq!(a.battle_results,b.battle_results);
    let ac=a.shared.as_ref().unwrap();let bc=b.shared.as_ref().unwrap();
    assert_eq!(ac.profile13,bc.profile13);assert_eq!((ac.join_requested,ac.queue_announced),(bc.join_requested,bc.queue_announced));
    assert_eq!(a.training_flights,b.training_flights);assert_eq!((a.tx.len(),a.tx.cumulative),(b.tx.len(),b.tx.cumulative));
    let(mut ta,mut tb)=(a.tx.clone(),b.tx.clone());let(mut wa,mut wb)=(Vec::new(),Vec::new());
    while let Some(row)=ta.due(now+transport091::RETRY,a.rx).unwrap(){wa.push(row);}
    while let Some(row)=tb.due(now+transport091::RETRY,b.rx).unwrap(){wb.push(row);}
    assert_eq!(wa,wb);
}

#[test]fn p10b_special_actual_results_and_legacy_room_order_keep_real_failure_bytes_and_pending_state(){
    let now=Instant::now();let mut s=account(now);
    let payload=[rpc(202,700,1,1),rpc(221,1500,9007199254740993,0),rpc(222,101,0,0),rpc(223,401,0,0),language(224)].concat();
    let f=frame(&s,1,&payload);let got=collect(&mut s,&f,now).unwrap();assert_eq!(got.records.len(),1);assert_eq!(got.records[0].outbox_index,2);
    assert!(s.battle_results.used_id(221));assert!(!s.battle_results.idle());assert_eq!(s.training_ids,vec![223]);assert_eq!(s.request_ids,vec![224]);
    assert_eq!(s.unsupported_request_ids,VecDeque::from([222]));let before=s.shared.as_ref().unwrap();
    assert!(!before.join_requested);assert!(!before.queue_announced);let p=before.profile13.as_ref().unwrap();assert!(p.garage_idle());assert_eq!(p.command_counter,0);
    let first=s.tx.due(now,s.rx).unwrap().unwrap().2;let body=transport091::parse_interactive(&first).unwrap().body;
    assert_eq!(body,crate::battle091::profile13::enqueue_failure("BATTLE_PROFILE_UNSUPPORTED").unwrap());
    let second=s.tx.due(now,s.rx).unwrap().unwrap().2;assert_eq!(transport091::parse_interactive(&second).unwrap().body,crate::hangar091::unavailable_response(222).unwrap());
}

#[test]fn p10b_special_random_join_cancel_info_preserve_actual_room_guard_and_selection(){
    let now=Instant::now();let mut s=account(now);
    let c=s.shared.as_mut().unwrap();c.join_requested=true;c.queue_announced=true;
    let p=c.profile13.as_mut().unwrap();p.in_flight=true;p.selection=Some(2);let saved=p.clone();
    let f=frame(&s,1,&[rpc(202,700,1,1),rpc(202,701,0,0),rpc(202,502,1,0)].concat());
    let got=collect(&mut s,&f,now).unwrap();assert!(got.records.is_empty());let c=s.shared.as_ref().unwrap();assert_eq!(c.profile13.as_ref(),Some(&saved));assert!(c.join_requested&&c.queue_announced);
    assert!(!s.battle_results.used_id(202));assert_eq!(s.tx.len(),1,"only native Join refusal, no fake dequeue/queue info");
    let sent=s.tx.due(now,s.rx).unwrap().unwrap().2;assert_eq!(transport091::parse_interactive(&sent).unwrap().body,crate::battle091::profile13::enqueue_failure("BATTLE_PROFILE_UNSUPPORTED").unwrap());
}

#[test]fn p10b_special_compact_remaining_legacy_decodes_once_and_late_duplicate_rolls_back_result_and_ack(){
    let now=Instant::now();let mut s=account(now);s.tx.enqueue_body(&[0xb0]).unwrap();s.tx.due(now,s.rx).unwrap().unwrap();
    let payload=[rpc(202,501,0,0),rpc(221,1500,1,0),rpc(222,401,0,0),rpc(202,501,0,0)].concat();
    let mut f=frame(&s,1,&payload);f.cumulative=Some(1);let before=s.clone();
    assert!(collect(&mut s,&f,now).is_err());same(&s,&before,now);assert!(s.battle_results.idle());assert_eq!(s.stats_requests,0);
}

#[test]fn p10b_special_room_result_same_id_in_whole_bundle_or_piggybacks_is_atomic_both_orders(){
    let now=Instant::now();
    for piggyback in [false,true]{for room_first in [false,true]{
        let mut s=account(now);s.tx.enqueue_body(&[0xb0]).unwrap();s.tx.due(now,s.rx).unwrap().unwrap();
        let room=rpc(225,401,0,0);let result=rpc(225,1500,1,0);
        let(first,last)=if room_first{(room,result)}else{(result,room)};
        let f=if piggyback{let mut child=frame(&s,1,&first);child.cumulative=Some(1);
            let mut parent=frame(&s,2,&last);parent.cumulative=Some(1);parent.flags|=2;parent.piggybacks.push(child);parent}
            else{let mut f=frame(&s,1,&[first,last].concat());f.cumulative=Some(1);f};
        let before=s.clone();assert!(collect(&mut s,&f,now).is_err());same(&s,&before,now);
        assert!(!s.battle_results.used_id(225));assert!(s.training_ids.is_empty());
    }}
}

#[test]fn p10b_special_results_cross_frame_language_ammo_unavailable_and_room_collide_both_directions(){
    let now=Instant::now();
    for kind in 0..4{for result_first in [false,true]{
        let mut s=account(now);let old=match kind{0=>language(226),1=>ammo(226),2=>rpc(226,101,0,0),_=>rpc(226,401,0,0)};
        let result=rpc(226,1500,1,0);let(first,last)=if result_first{(result,old)}else{(old,result)};
        let f=frame(&s,1,&first);collect(&mut s,&f,now).unwrap();let before=s.clone();
        let f=frame(&s,2,&last);assert!(collect(&mut s,&f,now).is_err(),"kind={kind} results_first={result_first}");same(&s,&before,now);
    }}
}

#[test]fn p10b_special_reserved_result_query_ids_do_not_change_flights_results_or_reliable_ack(){
    let now=Instant::now();
    for id in [200,201,202]{
        let mut s=account(now);s.training_flights=Some(Default::default());s.tx.enqueue_body(&[0xb0]).unwrap();s.tx.due(now,s.rx).unwrap().unwrap();
        let mut f=frame(&s,1,&rpc(id,1500,1,0));f.cumulative=Some(1);let before=s.clone();
        assert!(collect(&mut s,&f,now).is_err());same(&s,&before,now);assert!(s.battle_results.idle());
    }
}

#[test]fn p10b_special_actual_results_ack202_remains_repeatable_without_plain_lifetime_claim(){
    let now=Instant::now();let mut s=account(now);let f=frame(&s,1,&rpc(202,1501,1,0));
    collect(&mut s,&f,now).unwrap();let saved=s.battle_results.clone();assert!(!saved.idle());assert!(!saved.used_id(202));
    let f=frame(&s,2,&rpc(202,1501,1,0));collect(&mut s,&f,now).unwrap();assert_eq!(s.battle_results,saved);assert!(s.training_ids.is_empty());
}

#[test]fn p10b_special_actual_stats202_then_results_ack202_and_repeat_are_no_response_origins(){
    let now=Instant::now();let mut s=account(now);
    let f=frame(&s,1,&rpc(202,501,0,0));collect(&mut s,&f,now).unwrap();assert_eq!(s.stats_requests,1);
    let f=frame(&s,2,&rpc(202,1501,1,0));collect(&mut s,&f,now).unwrap();let saved=s.battle_results.clone();
    assert!(!saved.idle());assert!(!saved.used_id(202));assert!(s.training_ids.is_empty());
    let f=frame(&s,3,&rpc(202,1501,1,0));collect(&mut s,&f,now).unwrap();assert_eq!(s.battle_results,saved);
    // Query202 is still forbidden; it must not share this fixed ACK/stat origin.
    let before=s.clone();let f=frame(&s,4,&rpc(202,1500,1,0));assert!(collect(&mut s,&f,now).is_err());same(&s,&before,now);
}

#[test]fn p10b_special_results_ack202_survives_real_native_legacy_id202_history_after_stats(){
    let now=Instant::now();let mut s=account(now);
    // Actual existing Language RPC creates request_ids202; ServerStats itself
    // only increments stats_requests in current source. These are distinct
    // frames so the old whole-bundle duplicate parser is not bypassed.
    let f=frame(&s,1,&language(202));collect(&mut s,&f,now).unwrap();assert_eq!(s.request_ids,vec![202]);
    let f=frame(&s,2,&rpc(202,501,0,0));collect(&mut s,&f,now).unwrap();assert_eq!(s.stats_requests,1);
    let f=frame(&s,3,&rpc(202,1501,1,0));collect(&mut s,&f,now).unwrap();let saved=s.battle_results.clone();
    let f=frame(&s,4,&rpc(202,1501,1,0));collect(&mut s,&f,now).unwrap();assert_eq!(s.battle_results,saved);assert_eq!(s.request_ids,vec![202]);
    // ACK's exemption is not a fake parser: actual State.stage still rejects
    // an ACK with a dynamic ID, and the entire received frame rolls back.
    let before=s.clone();let f=frame(&s,5,&rpc(229,1501,1,0));assert!(collect(&mut s,&f,now).is_err());same(&s,&before,now);
}

#[test]fn p10b_special_result_shape_record_bound_and_oversize_fail_without_earlier_queue_callback(){
    let now=Instant::now();
    let mut bad_result=rpc(227,1500,1,0);bad_result[15]=1;
    let mut malformed_join=rpc(202,700,1,1);malformed_join[3]=221;
    let packets=[vec![0;513],(0..17).flat_map(|_|rpc(202,502,1,0)).collect::<Vec<_>>(),[rpc(202,700,1,1),bad_result].concat(),malformed_join];
    for packet in packets{let mut s=account(now);let before=s.clone();let f=frame(&s,1,&packet);assert!(collect(&mut s,&f,now).is_err());same(&s,&before,now);}
}

#[test]fn p10b_special_default_false_keeps_original_random_queue_native_selection_path(){
    let now=Instant::now();let mut s=account(now);s.training_opt_in=false;let f=frame(&s,1,&rpc(202,700,1,1));
    assert!(!s.receive(&f,now).unwrap());let c=s.shared.as_ref().unwrap();assert!(c.join_requested);assert_eq!(c.profile13.as_ref().unwrap().selection,Some(1));
    assert!(s.outbox.is_empty());assert_eq!(s.tx.len(),0);assert!(s.battle_results.idle());
}

#[test]fn p10b_special_result_transport_retry_does_not_restage_or_consume_plain_id(){
    let now=Instant::now();let mut s=account(now);let f=frame(&s,1,&rpc(228,1500,1,0));collect(&mut s,&f,now).unwrap();
    let before=s.clone();assert!(collect(&mut s,&f,now).unwrap().records.is_empty());same(&s,&before,now);assert!(s.training_ids.is_empty());
}
