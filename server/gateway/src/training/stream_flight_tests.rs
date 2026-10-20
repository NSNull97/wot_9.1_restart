use super::*;
use super::super::domain::{Account,AuthLease,RoomKey};
use crate::transport091::{Window,Frame};
use std::time::{Duration,Instant};
fn context(kind:Kind)->StreamContext{
 StreamContext::capture(AuthLease{account:Account([1;16]),generation:3},Channel{session:7,generation:9},kind,[2;32],
  match kind{Kind::Listing=>ReadRevision::Listing(0),Kind::Preview=>ReadRevision::Preview{room:RoomKey(2),revision:4}},13,[3;32]).unwrap()
}
fn frame(c:u32,s:Vec<u32>)->Frame{Frame{flags:0x408,sequence:None,cumulative:Some(c),selective:s,body:vec![],piggybacks:vec![]}}
fn enqueue(w:&mut Window,f:&mut Flights,body:&[u8])->u32{let seq=w.enqueue_body_tracked(body).unwrap();f.on_enqueued(seq).unwrap();seq}
fn sent(w:&mut Window,now:Instant,n:usize){for _ in 0..n{w.due(now,0).unwrap().unwrap();}}
fn ack(w:&mut Window,f:&mut Flights,c:u32,s:Vec<u32>)->[Option<StreamContext>;2]{let a=frame(c,s);w.acknowledge(&a).unwrap();f.on_validated_ack(w.cumulative,&a.selective).unwrap()}
#[test]fn p10b_stream_selective_final_cannot_release_earlier_gap(){
 let(mut w,mut f)=(Window::interactive(),Flights::default());f.stage(context(Kind::Listing),0,3).unwrap();
 for n in 0..3{assert_eq!(enqueue(&mut w,&mut f,&[52,n]),n as u32);}sent(&mut w,Instant::now(),3);
 assert_eq!(ack(&mut w,&mut f,0,vec![2]),[None,None]);assert!(f.busy(Kind::Listing));assert_eq!(w.len(),2);
 assert_eq!(ack(&mut w,&mut f,1,vec![]),[None,None]);
 assert_eq!(ack(&mut w,&mut f,2,vec![])[0],Some(context(Kind::Listing)));assert!(!f.busy(Kind::Listing));
}
#[test]fn p10b_stream_zero_sequence_selective_ack_and_repeat200(){
 let(mut w,mut f)=(Window::interactive(),Flights::default());f.stage(context(Kind::Listing),0,1).unwrap();
 assert_eq!(enqueue(&mut w,&mut f,&[52,200]),0);sent(&mut w,Instant::now(),1);
 assert_eq!(ack(&mut w,&mut f,0,vec![0])[0],Some(context(Kind::Listing)));
 f.stage(context(Kind::Listing),0,1).unwrap();assert_eq!(enqueue(&mut w,&mut f,&[52,200]),1);
 sent(&mut w,Instant::now(),1);assert!(ack(&mut w,&mut f,2,vec![])[0].is_some());
}
#[test]fn p10b_stream_offsets_distinct_ids_and_independent_release(){
 let(mut w,mut f)=(Window::interactive(),Flights::default());
 // Two preexisting ordinary bodies, then list2, preview1, later list1.
 f.stage(context(Kind::Listing),2,2).unwrap();f.stage(context(Kind::Preview),4,1).unwrap();
 for _ in 0..4{enqueue(&mut w,&mut f,&[1]);}sent(&mut w,Instant::now(),4);
 assert!(ack(&mut w,&mut f,4,vec![])[0].is_some());assert!(f.busy(Kind::Preview));
 f.stage(context(Kind::Listing),1,1).unwrap();
 enqueue(&mut w,&mut f,&[201]);enqueue(&mut w,&mut f,&[200]);sent(&mut w,Instant::now(),2);
 let done=ack(&mut w,&mut f,4,vec![5]);assert!(done[0].is_some());assert!(done[1].is_none());
 assert!(f.busy(Kind::Preview));assert!(ack(&mut w,&mut f,5,vec![])[1].is_some());
}
#[test]fn p10b_stream_failed_actual_enqueue_never_marks_body(){
 let(mut w,mut f)=(Window::interactive(),Flights::default());for _ in 0..8{w.enqueue_body(&[9]).unwrap();}
 f.stage(context(Kind::Listing),0,1).unwrap();let before=f.clone();
 assert!(w.enqueue_body_tracked(&[200]).is_err());assert_eq!(f,before);
 sent(&mut w,Instant::now(),8);assert_eq!(ack(&mut w,&mut f,8,vec![]),[None,None]);
 assert_eq!(enqueue(&mut w,&mut f,&[200]),8);sent(&mut w,Instant::now(),1);
 assert!(ack(&mut w,&mut f,9,vec![])[0].is_some());
}
#[test]fn p10b_stream_actual_retry_adds_no_stamp_or_reuse(){
 let(mut w,mut f)=(Window::interactive(),Flights::default());let now=Instant::now();
 f.stage(context(Kind::Listing),0,1).unwrap();let seq=enqueue(&mut w,&mut f,&[52,200]);
 let first=w.due(now,0).unwrap().unwrap();let before=f.clone();
 let retry=w.due(now+Duration::from_millis(701),0).unwrap().unwrap();
 assert_eq!(first.0,retry.0);assert_eq!(first.2,retry.2);assert_eq!(f,before);
 assert_eq!(f.on_enqueued(seq),Err(Error::Sequence));assert_eq!(f,before);
 assert_eq!(f.stage(context(Kind::Listing),0,1),Err(Error::Busy));
 assert!(ack(&mut w,&mut f,1,vec![])[0].is_some());
}
#[test]fn p10b_stream_async_context_fences_every_origin_dimension(){
 let original=context(Kind::Preview);
 for poison in 0..10{
  let mut changed=original.clone();match poison{
   0=>changed.caller.account=Account([9;16]),1=>changed.caller.generation+=1,
   2=>changed.channel.session+=1,3=>changed.channel.generation+=1,4=>changed.query[0]^=1,
   5=>changed.read=ReadRevision::Preview{room:RoomKey(3),revision:4},
   6=>changed.read=ReadRevision::Preview{room:RoomKey(2),revision:5},
   7=>changed.profile_revision+=1,8=>changed.source_binding[0]^=1,9=>changed.kind=Kind::Listing,_=>unreachable!()}
  assert!(!original.matches_current(&changed),"poison{poison}");
 }
 assert!(original.matches_current(&original));
 let mut f=Flights::default();f.stage(original.clone(),0,1).unwrap();
 let mut changed=original.clone();changed.channel.generation+=1;
 assert!(!f.context(Kind::Preview).unwrap().matches_current(&changed));
 assert!(f.busy(Kind::Preview)); // stale origin cannot silently free old bytes.
}
#[test]fn p10b_stream_bounds_overlap_and_ack_poison_are_atomic(){
 let mut f=Flights::default();
 for(a,n)in [(0,0),(0,83),(128,1),(usize::MAX,1)]{let before=f.clone();assert_eq!(f.stage(context(Kind::Listing),a,n),Err(Error::Bound));assert_eq!(f,before);}
 f.stage(context(Kind::Listing),2,3).unwrap();let before=f.clone();
 assert_eq!(f.stage(context(Kind::Preview),4,1),Err(Error::Overlap));assert_eq!(f,before);
 assert_eq!(f.on_enqueued(MAX_SEQUENCE),Err(Error::Sequence));assert_eq!(f,before);
 assert_eq!(f.on_validated_ack(0,&[MAX_SEQUENCE]),Err(Error::Ack));assert_eq!(f,before);
 let(mut w,mut actual)=(Window::interactive(),Flights::default());actual.stage(context(Kind::Listing),0,1).unwrap();enqueue(&mut w,&mut actual,&[200]);
 let before=actual.clone();assert!(w.acknowledge(&frame(1,vec![])).is_err());assert_eq!(actual,before); // never call helper after invalid Window ACK.
}
#[test]fn p10b_stream_eighty_two_bodies_are_bounded_across_real_window(){
 let(mut w,mut f)=(Window::interactive(),Flights::default());f.stage(context(Kind::Listing),0,MAX_BODIES).unwrap();let now=Instant::now();let mut produced=0;
 while produced<MAX_BODIES{
  let n=(MAX_BODIES-produced).min(8);
  for _ in 0..n{enqueue(&mut w,&mut f,&[200]);}sent(&mut w,now,n);produced+=n;
  let done=ack(&mut w,&mut f,produced as u32,vec![]);
  assert_eq!(done[0].is_some(),produced==MAX_BODIES);
 }
 assert!(!f.busy(Kind::Listing));assert_eq!(w.len(),0);
}
