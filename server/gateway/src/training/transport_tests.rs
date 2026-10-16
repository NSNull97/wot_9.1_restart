use crate::transport091 as t;
use super::aliases;
use std::time::Instant;

fn own404()->Vec<u8>{
    // Source doCmdInt3: method8e, VAR2 length20, request221, command404,
    // own fixed Account entityID, encoded roster2, trailing0. No room epoch.
    let mut b=vec![0x8e,20,0];b.extend(221i16.to_le_bytes());b.extend(404i16.to_le_bytes());
    b.extend(i64::from(aliases::OWN_ENTITY_ID).to_le_bytes());b.extend(2i32.to_le_bytes());b.extend(0i32.to_le_bytes());b
}

#[test]
fn actual_window_retry_keeps_old_payload_and_sequence_but_carries_new_ack_counterexample(){
    let now=Instant::now();let mut w=t::Window::interactive();let body=own404();
    assert_eq!(w.enqueue_body_tracked(&body).unwrap(),0);
    let first=t::parse_interactive(&w.due(now,7).unwrap().unwrap().2).unwrap();
    let retry=t::parse_interactive(&w.due(now+t::RETRY,42).unwrap().unwrap().2).unwrap();
    assert_eq!(first.body,body);assert_eq!(retry.body,body);assert_eq!(first.sequence,retry.sequence);
    assert_eq!((first.cumulative,retry.cumulative),(Some(7),Some(42)));
    // This is OUR actual Window's behavior, not a proven native C++ retry rule.
    // Therefore a later ACK cannot generally prove newer semantic body origin.
}

#[test]
fn actual_window_queued_barrier_cannot_be_acked_before_sent_and_sequence_zero_is_valid(){
    let now=Instant::now();let mut w=t::Window::interactive();let seq=w.enqueue_body_tracked(&[0x13,0x46,1,0,0,0]).unwrap();assert_eq!(seq,0);
    let ack=t::parse_interactive(&t::ack(1)).unwrap();assert!(w.acknowledge(&ack).is_err());assert_eq!(w.len(),1);
    w.due(now,0).unwrap().unwrap();w.acknowledge(&ack).unwrap();assert_eq!((w.cumulative,w.len()),(1,0));
    // Delivery knowledge, not ClientPrebattle/UI initialization or command age.
}

#[test]
fn actual_window_selective_final_packet_does_not_prove_a_cumulative_prefix(){
    let now=Instant::now();let mut w=t::Window::interactive();
    for _ in 0..3{w.enqueue_body_tracked(&[42]).unwrap();}while w.due(now,0).unwrap().is_some(){}
    let f=t::Frame{flags:0x44c,sequence:Some(0),cumulative:Some(0),selective:vec![2],body:vec![],piggybacks:vec![]};
    w.acknowledge(&f).unwrap();assert_eq!((w.cumulative,w.len()),(0,2));
    w.acknowledge(&t::parse_interactive(&t::ack(3)).unwrap()).unwrap();assert_eq!((w.cumulative,w.len()),(3,0));
}
