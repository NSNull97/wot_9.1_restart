//! Actual Session/Window transaction tests with tiny authored Account fixtures.
//! No Registry dispatcher, HTTP writer, native packet observation or owned proof.
use super::*;
use std::sync::atomic::{AtomicU64,Ordering};

fn account(now:Instant)->Session{
    static SERIAL:AtomicU64=AtomicU64::new(0);
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/p10b-session");
    fs::create_dir_all(&root).unwrap();
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let dir=root.join(format!("{}-{stamp}-{}",std::process::id(),SERIAL.fetch_add(1,Ordering::Relaxed)));
    fs::create_dir(&dir).unwrap();
    fs::write(dir.join("state.bin"),b"\x80\x02}(U\x03revK\x01u.").unwrap();
    fs::write(dir.join("shop.bin"),b"\x80\x02}(U\x03revK\x03u.").unwrap();
    fs::write(dir.join("dossier.bin"),b"\x80\x02(K\x00]t.").unwrap();
    let fixtures=Arc::new(crate::hangar091::Fixtures::load_interactive(&dir).unwrap());
    let mut s=Session::new(7,[7;16],"127.0.0.1:41907".parse().unwrap(),now);
    s.identity=Some(Arc::new(crate::identity091::Profile{account_id:"12345678-1234-4234-8234-123456789abc".into(),
        database_id:7,name:"p10b-session-fixture".into(),fixture_dir:dir}));
    s.hangar=Some(fixtures);s.account_probe=true;s.account_ready=true;s.active=true;s.sync_mask=7;s.rx=1;
    s.base_peer=Some("127.0.0.1:41908".parse().unwrap());s.tx=Window::interactive();s
}
fn rpc(id:i16,command:i16,a:i64,b:i32)->Vec<u8>{
    let mut v=vec![0x8e,20,0];v.extend(id.to_le_bytes());v.extend(command.to_le_bytes());
    v.extend(a.to_le_bytes());v.extend(b.to_le_bytes());v.extend(0i32.to_le_bytes());v
}
fn frame(s:&Session,n:u32,payload:&[u8])->Frame{
    Frame{flags:0x458,sequence:Some(n),cumulative:Some(0),selective:Vec::new(),
        body:[vec![1],s.token.to_le_bytes().to_vec(),payload.to_vec()].concat(),piggybacks:Vec::new()}
}
#[derive(Debug,PartialEq)]
struct Stamp{
    rx:u32,last_rx:Instant,active:bool,ready:bool,sync:u8,ids:Vec<i16>,unsupported:VecDeque<i16>,
    chat:Vec<i64>,stats:u32,language:Option<&'static str>,history:VecDeque<(u32,Vec<u8>)>,
    outbox:VecDeque<Vec<u8>>,pending:usize,cumulative:u32,next_wire:Option<(u32,u8,Vec<u8>)>,avatar_count:u8,
}
fn stamp(s:&Session,now:Instant)->Stamp{
    let mut tx=s.tx.clone();let next_wire=tx.due(now+transport091::RETRY,s.rx).unwrap();
    Stamp{rx:s.rx,last_rx:s.last_rx,active:s.active,ready:s.account_ready,sync:s.sync_mask,ids:s.request_ids.clone(),
        unsupported:s.unsupported_request_ids.clone(),chat:s.chat_request_ids.clone(),stats:s.stats_requests,language:s.language,
        history:s.received.clone(),outbox:s.outbox.clone(),pending:s.tx.len(),cumulative:s.tx.cumulative,next_wire,
        avatar_count:s.avatar_unsupported_envelopes}
}

#[test]
fn p10b_session_default_receive_uses_existing_legacy_application_and_drain(){
    let now=Instant::now();let mut s=account(now);assert!(!s.training_opt_in);
    let request=rpc(221,101,0,0);let f=frame(&s,1,&request);
    assert!(!s.receive(&f,now).unwrap());assert_eq!(s.rx,2);assert!(s.outbox.is_empty());
    assert_eq!(s.unsupported_request_ids,VecDeque::from([221]));assert_eq!(s.tx.len(),1);
    let wire=s.tx.due(now,2).unwrap().unwrap().2;
    assert_eq!(transport091::parse_interactive(&wire).unwrap().body,crate::hangar091::unavailable_response(221).unwrap());
}

#[test]
fn p10b_session_opt_in_cannot_silently_use_ordinary_receive_or_unselected_collector(){
    let now=Instant::now();let mut s=account(now);let f=frame(&s,1,&rpc(221,401,0,0));
    let before=stamp(&s,now);assert!(s.receive_training_collected(&f,now).is_err());assert_eq!(stamp(&s,now),before);
    s.training_opt_in=true;let before=stamp(&s,now);
    assert!(s.receive(&f,now).is_err());assert_eq!(stamp(&s,now),before);
    let got=s.receive_training_collected(&f,now).unwrap();assert_eq!(got.records.len(),1);assert!(!got.close);
    assert_eq!(got.records[0].request.kind,crate::training091::ingress::Kind::Leave);
    assert!(!got.diagnostics.is_empty());
}

#[test]
fn p10b_session_ordered_room_offsets_include_existing_prefix_and_intervening_legacy_bytes(){
    let now=Instant::now();let mut s=account(now);s.training_opt_in=true;s.outbox.push_back(vec![0xa0]);
    let payload=[rpc(221,401,0,0),rpc(222,101,0,0),rpc(223,405,0,0),rpc(202,501,0,0),rpc(224,403,1,0)].concat();
    let got=s.receive_training_collected(&frame(&s,1,&payload),now).unwrap();
    assert_eq!(got.records.iter().map(|r|r.outbox_index).collect::<Vec<_>>(),[1,2,3]);
    assert_eq!(got.records.iter().map(|r|r.request.kind.clone()).collect::<Vec<_>>(),[
        crate::training091::ingress::Kind::Leave,crate::training091::ingress::Kind::SwapTeams,crate::training091::ingress::Kind::NotReady{state:1}]);
    assert_eq!(s.tx.len(),0);assert_eq!(s.outbox,VecDeque::from([vec![0xa0],crate::hangar091::unavailable_response(222).unwrap(),crate::hangar091::server_stats()]));
    // Authored opaque bodies exercise insertion only; this is NOT a dispatcher
    // or evidence that these room commands generated a real native response.
    for(i,record)in got.records.iter().enumerate(){s.outbox.insert(record.outbox_index+i,vec![0xa1+i as u8]);}
    assert_eq!(s.outbox,VecDeque::from([vec![0xa0],vec![0xa1],crate::hangar091::unavailable_response(222).unwrap(),vec![0xa2],crate::hangar091::server_stats(),vec![0xa3]]));
    s.drain_outbox().unwrap();assert_eq!(s.tx.len(),6);assert!(s.outbox.is_empty());
}

#[test]
fn p10b_session_piggyback_ack_and_room_order_keep_offsets_until_outer_drain_and_retry_collects_nothing(){
    let now=Instant::now();let mut s=account(now);s.training_opt_in=true;
    s.tx.enqueue_body(&[0xb0]).unwrap();s.tx.due(now,s.rx).unwrap().unwrap();
    let mut child=frame(&s,1,&[rpc(221,101,0,0),rpc(222,401,0,0)].concat());child.cumulative=Some(1);
    let mut parent=frame(&s,2,&rpc(223,405,0,0));parent.flags|=2;parent.cumulative=Some(1);parent.piggybacks.push(child);
    let got=s.receive_training_collected(&parent,now).unwrap();
    assert_eq!(s.rx,3);assert_eq!((s.tx.cumulative,s.tx.len()),(1,0));assert_eq!(s.outbox.len(),1);
    assert_eq!(got.records.iter().map(|r|r.outbox_index).collect::<Vec<_>>(),[1,1]);
    assert_eq!(got.records[0].request.kind,crate::training091::ingress::Kind::Leave);
    assert_eq!(got.records[1].request.kind,crate::training091::ingress::Kind::SwapTeams);
    let before=stamp(&s,now);let retry=s.receive_training_collected(&parent,now).unwrap();
    assert!(retry.records.is_empty());assert_eq!(stamp(&s,now),before);
}

#[test]
fn p10b_session_late_parent_poison_rolls_back_child_ack_rpc_ids_room_events_and_outbox(){
    let now=Instant::now();let mut original=account(now);original.training_opt_in=true;original.outbox.push_back(vec![0xa0]);
    original.tx.enqueue_body(&[0xb0]).unwrap();original.tx.due(now,original.rx).unwrap().unwrap();
    let mut child=frame(&original,1,&[rpc(221,101,0,0),rpc(222,401,0,0)].concat());child.cumulative=Some(1);
    for poison in 0..3{
        let mut s=original.clone();let payload=if poison==0{vec![0x9a]}else{rpc(223,405,0,0)};
        let mut parent=frame(&s,2,&payload);parent.flags|=2;parent.cumulative=Some(1);parent.piggybacks.push(child.clone());
        if poison==1{parent.body[1]^=1;}if poison==2{parent.sequence=Some(3);}
        let before=stamp(&s,now);assert!(s.receive_training_collected(&parent,now+Duration::from_millis(1)).is_err());
        assert_eq!(stamp(&s,now),before);
    }
}

#[test]
fn p10b_session_whole_legacy_decoder_rejects_duplicate_stats_across_room_before_any_application(){
    let now=Instant::now();let mut s=account(now);s.training_opt_in=true;
    let payload=[rpc(202,501,0,0),rpc(221,401,0,0),rpc(202,501,0,0)].concat();
    let before=stamp(&s,now);assert!(s.receive_training_collected(&frame(&s,1,&payload),now).is_err());assert_eq!(stamp(&s,now),before);
    assert_eq!(s.stats_requests,0);
}

#[test]
fn p10b_session_only_ready_account_collects_room_commands_and_sync200_201_stay_closed(){
    let now=Instant::now();let source=account(now);
    for poison in 0..8{
        let mut s=source.clone();s.training_opt_in=true;
        match poison{0=>s.active=false,1=>s.account_ready=false,2=>s.identity=None,3=>s.hangar=None,
            4=>s.base_peer=None,5=>s.sync_mask=3,6=>s.arena_base=true,
            7=>s.drive_return_account=Some(WarmAccountReturn{generation:1,queue_ahead:0,creation:None,enabled:false,stale_avatar_envelopes:0}),_=>unreachable!()}
        assert!(!s.training_account_ready());let f=frame(&s,1,&rpc(221,401,0,0));
        if let Ok(got)=s.receive_training_collected(&f,now){assert!(got.records.is_empty(),"phase poison {poison}");}
    }
    for id in[200,201]{let mut s=source.clone();s.training_opt_in=true;let before=stamp(&s,now);
        assert!(s.receive_training_collected(&frame(&s,1,&rpc(id,100,0,0)),now).is_err());assert_eq!(stamp(&s,now),before);}
}

fn tree(s:&Session,next:&mut u32,count:usize)->Frame{
    let left=(count-1)/2;let right=count-1-left;let mut children=Vec::new();
    if left>0{children.push(tree(s,next,left));}if right>0{children.push(tree(s,next,right));}
    let mut f=frame(s,*next,&[]);*next+=1;if !children.is_empty(){f.flags|=2;}f.piggybacks=children;f
}
#[test]
fn p10b_session_collector_preserves_actual_total32_frame_budget_without_partial_history(){
    let now=Instant::now();let mut s=account(now);s.training_opt_in=true;
    let good=tree(&s,&mut 1,32);let got=s.receive_training_collected(&good,now).unwrap();assert!(got.records.is_empty());assert_eq!(s.rx,33);
    let mut s=account(now);s.training_opt_in=true;let bad=tree(&s,&mut 1,33);let before=stamp(&s,now);
    assert!(s.receive_training_collected(&bad,now).is_err());assert_eq!(stamp(&s,now),before);
}

#[test]
fn p10b_session_close_and_diagnostics_are_returned_with_earlier_child_room_records(){
    let now=Instant::now();let mut s=account(now);s.training_opt_in=true;
    let child=frame(&s,1,&rpc(221,401,0,0));let mut parent=frame(&s,2,&[11,0]);parent.flags|=2;parent.piggybacks.push(child);
    let got=s.receive_training_collected(&parent,now).unwrap();assert!(got.close);assert_eq!(got.records.len(),1);
    assert_eq!(got.records[0].outbox_index,0);assert_eq!(got.records[0].request.kind,crate::training091::ingress::Kind::Leave);
    assert_eq!(s.rx,3);assert!(!got.diagnostics.is_empty());assert_eq!(s.tx.len(),0);
}

fn stream_account(now:Instant)->Session{
    let mut s=account(now);s.training_opt_in=true;
    s.training_flights=Some(crate::training091::stream_flight::Flights::default());
    s.ammo_service=Some(ammo_session::State::new(crate::ammo_service091::Metadata{revision:13,wire_revision:1},true));s
}
fn stream_context()->crate::training091::stream_flight::StreamContext{
    use crate::training091::{domain::{Account,AuthLease},stream_flight::{StreamContext,Channel,Kind,ReadRevision}};
    StreamContext::capture(AuthLease{account:Account([0x12,0x34,0x56,0x78,0x12,0x34,0x42,0x34,0x82,0x34,0x12,0x34,0x56,0x78,0x9a,0xbc]),generation:7},
        Channel{session:7,generation:1},Kind::Listing,[1;32],ReadRevision::Listing(0),13,[2;32]).unwrap()
}
#[test]fn p10b_session_old_account_stream_context_cannot_bind_after_warm_recreation(){
    use crate::training091::stream_flight::{StreamContext,Channel,Kind,ReadRevision};
    let now=Instant::now();let mut s=stream_account(now);assert_eq!(s.training_account_generation(),1);
    // Authored completed warm boundary, not a claim of native warm acceptance.
    s.drive_return_account=Some(WarmAccountReturn{generation:1,queue_ahead:0,creation:Some((0,true)),enabled:true,stale_avatar_envelopes:0});
    assert_eq!(s.training_account_generation(),2);let old=stream_context();
    let bodies=crate::hangar091::stream_with_budget(200,b"x",Vec::new(),16384).unwrap();let before=stamp(&s,now);let flight=s.training_flights.clone();
    assert!(s.queue_training_stream(old.clone(),bodies.clone(),0).is_err());assert_eq!(stamp(&s,now),before);assert_eq!(s.training_flights,flight);
    let fresh=StreamContext::capture(old.caller(),Channel{session:7,generation:2},Kind::Listing,[1;32],ReadRevision::Listing(0),13,[2;32]).unwrap();
    s.queue_training_stream(fresh,bodies,0).unwrap();assert_eq!(s.outbox.len(),1);
}
#[test]fn p10b_session_actual_stream_all_ACKs_preserve_prefix_suffix_and_allow_repeat200(){
    use crate::training091::stream_flight::Kind;
    let now=Instant::now();let mut s=stream_account(now);
    s.outbox.push_back(crate::training091::wire::left());
    let bodies=crate::hangar091::stream_with_budget(200,&vec![b'x';900],Vec::new(),16384).unwrap();assert_eq!(bodies.len(),3);
    s.queue_training_stream(stream_context(),bodies,1).unwrap();s.outbox.push_back(crate::training091::wire::left());s.drain_outbox().unwrap();
    assert_eq!(s.tx.len(),5);assert!(s.outbox.is_empty());for _ in 0..5{s.tx.due(now,s.rx).unwrap().unwrap();}
    let mut ack=Frame{flags:0x408,sequence:None,cumulative:Some(0),selective:vec![3],body:vec![],piggybacks:vec![]};
    s.receive_training_collected(&ack,now).unwrap();assert!(s.training_flights.as_ref().unwrap().busy(Kind::Listing));
    let before=stamp(&s,now);let flight=s.training_flights.clone();
    let bodies=crate::hangar091::stream_with_budget(200,b"x",Vec::new(),16384).unwrap();
    assert!(s.queue_training_stream(stream_context(),bodies,0).is_err());assert_eq!(stamp(&s,now),before);assert_eq!(s.training_flights,flight);
    ack.selective=vec![1,2];s.receive_training_collected(&ack,now).unwrap();assert!(!s.training_flights.as_ref().unwrap().busy(Kind::Listing));
    assert_eq!(s.tx.len(),2,"unrelated prefix/suffix need no fake all-window ACK");
    let bodies=crate::hangar091::stream_with_budget(200,b"x",Vec::new(),16384).unwrap();s.queue_training_stream(stream_context(),bodies,0).unwrap();
    s.drain_outbox().unwrap();assert!(s.training_flights.as_ref().unwrap().busy(Kind::Listing));
}
#[test]fn p10b_session_stream_wrong_ID_fragment_identity_revision_and_unsent_ACK_are_atomic(){
    use crate::training091::stream_flight::{Kind,StreamContext,Channel,ReadRevision};
    let now=Instant::now();let base=stream_account(now);
    for poison in 0..6{
        let mut s=base.clone();let mut c=stream_context();let mut bodies=crate::hangar091::stream_with_budget(200,b"x",Vec::new(),16384).unwrap();
        match poison{
            0=>bodies=crate::hangar091::stream_with_budget(201,b"x",Vec::new(),16384).unwrap(),
            1=>{let last=bodies[0].len()-1;bodies[0].truncate(last);},
            2=>c=StreamContext::capture(c.caller(),Channel{session:8,generation:8},Kind::Listing,[1;32],ReadRevision::Listing(0),13,[2;32]).unwrap(),
            3=>c=StreamContext::capture(c.caller(),c.channel(),Kind::Listing,[1;32],ReadRevision::Listing(0),14,[2;32]).unwrap(),
            4=>{s.identity=Some(Arc::new(crate::identity091::Profile{account_id:"00000000-0000-4000-8000-000000000001".into(),database_id:7,name:"foreign".into(),fixture_dir:Path::new("").into()}));},
            5=>{let n=bodies[0].len();bodies[0][n-1]=0;let offset=3+usize::from(u16::from_le_bytes([bodies[0][1],bodies[0][2]]));bodies[0][offset+6]=0;},_=>unreachable!()
        }
        let before=stamp(&s,now);let flight=s.training_flights.clone();assert!(s.queue_training_stream(c,bodies,0).is_err(),"poison {poison}");
        assert_eq!(stamp(&s,now),before);assert_eq!(s.training_flights,flight);
    }
    let mut s=base;let bodies=crate::hangar091::stream_with_budget(200,b"x",Vec::new(),16384).unwrap();
    s.queue_training_stream(stream_context(),bodies,0).unwrap();s.drain_outbox().unwrap();
    let before=stamp(&s,now);let flight=s.training_flights.clone();
    let ack=Frame{flags:0x408,sequence:None,cumulative:Some(1),selective:vec![],body:vec![],piggybacks:vec![]};
    assert!(s.receive_training_collected(&ack,now).is_err());assert_eq!(stamp(&s,now),before);assert_eq!(s.training_flights,flight);
}
