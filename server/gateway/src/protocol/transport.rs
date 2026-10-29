//! Bounded measured 0.9.1 transport subset. No fragments or entity dispatch.
use std::{collections::VecDeque,io,time::{Duration,Instant}};
pub(crate) const MAX_SEQUENCE:u32=32; // Lab lifetime bound, not the native wraparound modulus.
pub(crate) const INTERACTIVE_MAX_SEQUENCE:u32=1_000_000; // Safety stop before any unmeasured wraparound.
pub const RETRY:Duration=Duration::from_millis(700);
/// Project policy, not a historical constant: an interactive #717 client may
/// block its main thread for seconds (hangar refresh measured 6.7 s). Lab
/// windows keep their five-send bound.
pub const INTERACTIVE_LIVENESS:Duration=Duration::from_secs(30);
const LAB_SENDS:u8=5;
const LAB_IDLE:Duration=Duration::from_secs(8);
fn invalid()->io::Error {io::Error::new(io::ErrorKind::InvalidData,"unsupported/bounded channel frame")}

#[derive(Debug,Clone)]
pub struct Frame {pub flags:u16,pub sequence:Option<u32>,pub cumulative:Option<u32>,pub selective:Vec<u32>,pub body:Vec<u8>,pub piggybacks:Vec<Frame>}
pub fn parse(clear:&[u8])->io::Result<Frame> {parse_inner(clear,0,&mut 32,4096,MAX_SEQUENCE)}
pub fn parse_interactive(clear:&[u8])->io::Result<Frame> {parse_inner(clear,0,&mut 32,INTERACTIVE_MAX_SEQUENCE-1,INTERACTIVE_MAX_SEQUENCE)}
fn parse_inner(clear:&[u8],depth:usize,budget:&mut usize,rx_limit:u32,tx_limit:u32)->io::Result<Frame> {
    if clear.len()<2 || clear.len()>1024 || depth>8 || *budget==0 {return Err(invalid());} *budget-=1;
    let flags=u16::from_le_bytes([clear[0],clear[1]]);
    if ![0x408,0x448,0x44c,0x458,0x45a,0x58,0x5a].contains(&flags) {return Err(invalid());}
    let mut end=clear.len();
    fn pop<'a>(clear:&'a[u8],end:&mut usize,n:usize)->io::Result<&'a[u8]> {
        if n>*end || *end-n<2 {return Err(invalid());} *end-=n;Ok(&clear[*end..*end+n])
    }
    fn word(b:&[u8])->io::Result<u32> {Ok(u32::from_le_bytes(b.try_into().map_err(|_|invalid())?))}
    let mut piggybacks=Vec::new();
    if flags&2!=0 {
        loop {
            if piggybacks.len()>=16 {return Err(invalid());}
            let n=i16::from_le_bytes(pop(clear,&mut end,2)?.try_into().map_err(|_|invalid())?);
            let last=n<0;let length=if last {!n} else {n};
            piggybacks.push(parse_inner(pop(clear,&mut end,length as usize)?,depth+1,budget,rx_limit,tx_limit)?);
            if last {break;}
        }
    }
    let cumulative=if flags&0x400!=0 {Some(word(pop(clear,&mut end,4)?)?)} else {None};
    let mut selective=Vec::new();
    if flags&4!=0 {
        let count=pop(clear,&mut end,1)?[0] as usize;
        if !(1..=16).contains(&count) {return Err(invalid());}
        for _ in 0..count {selective.push(word(pop(clear,&mut end,4)?)?);}
    }
    let sequence=if flags&0x40!=0 {Some(word(pop(clear,&mut end,4)?)?)} else {None};
    if sequence.is_some_and(|s|s>rx_limit) || cumulative.is_some_and(|s|s>tx_limit)
        || selective.iter().any(|s|*s>=tx_limit) {return Err(invalid());}
    Ok(Frame {flags,sequence,cumulative,selective,body:clear[2..end].to_vec(),piggybacks})
}
pub fn ack(next:u32)->Vec<u8> {let mut b=vec![8,4];b.extend(next.to_le_bytes());b}
/// NET-01: channel packet without the reliable bit and without a sequence
/// number, the same 0x0408 form as `ack` (accepted by #717 for hours), with
/// application messages in the body. Volatile poses only: a lost one is never
/// resent; the next tick carries a fresh pose.
pub fn unreliable(next:u32,body:&[u8])->io::Result<Vec<u8>> {
    if body.is_empty() || body.len()>512 {return Err(invalid());}
    let mut b=vec![8,4];b.extend_from_slice(body);b.extend(next.to_le_bytes());Ok(b)
}

/// NET-01 diagnostics: fixed log-scale buckets (ms upper bounds), exact max.
#[derive(Clone,Copy,Debug,Default,PartialEq)]
pub struct Histogram {buckets:[u32;15],count:u32,sum_ms:f64,max_ms:f64}
const BOUNDS_MS:[f64;14]=[1.,2.,5.,10.,20.,50.,100.,200.,500.,1000.,2000.,5000.,10000.,30000.];
impl Histogram {
    pub fn record(&mut self,value:Duration) {self.record_ms(value.as_secs_f64()*1000.);}
    pub fn record_ms(&mut self,ms:f64) {
        let i=BOUNDS_MS.iter().position(|b|ms<=*b).unwrap_or(BOUNDS_MS.len());
        self.buckets[i]=self.buckets[i].saturating_add(1);self.count=self.count.saturating_add(1);
        self.sum_ms+=ms;self.max_ms=self.max_ms.max(ms);
    }
    pub fn count(&self)->u32 {self.count}
    pub fn merge(&mut self,other:&Self) {
        for (a,b) in self.buckets.iter_mut().zip(other.buckets) {*a=a.saturating_add(b);}
        self.count=self.count.saturating_add(other.count);self.sum_ms+=other.sum_ms;self.max_ms=self.max_ms.max(other.max_ms);
    }
    pub fn max_ms(&self)->f64 {self.max_ms}
    /// Upper bound of the bucket holding quantile `q`, never above the exact max.
    pub fn quantile_ms(&self,q:f64)->f64 {
        if self.count==0 {return 0.;}
        let rank=((self.count as f64)*q).ceil().max(1.) as u32;let mut seen=0;
        for (i,n) in self.buckets.iter().enumerate() {
            seen+=n;if seen>=rank {return BOUNDS_MS.get(i).copied().unwrap_or(self.max_ms).min(self.max_ms);}
        }
        self.max_ms
    }
    pub fn summary(&self)->String {
        format!("n={} mean={:.1} p50<={:.1} p95<={:.1} p99<={:.1} max={:.1}",self.count,
            if self.count==0 {0.} else {self.sum_ms/self.count as f64},
            self.quantile_ms(0.5),self.quantile_ms(0.95),self.quantile_ms(0.99),self.max_ms)
    }
}
/// NET-01: what the reliable window waited on since the last report.
#[derive(Clone,Copy,Debug,Default,PartialEq)]
pub struct WindowStats {pub ack_wait:Histogram,pub queue_wait:Histogram,pub pending_max:usize,pub resends:u32}
pub fn reliable(sequence:u32,next:u32)->Vec<u8> {let mut b=vec![0x58,4];b.extend(sequence.to_le_bytes());b.extend(next.to_le_bytes());b}

#[derive(Clone)]
struct Pending {sequence:u32,queued:Instant,sent_wall:Option<Instant>,first:Option<Instant>,last:Option<Instant>,attempts:u8,body:Vec<u8>}
#[derive(Clone)]
pub struct Window {pending:VecDeque<Pending>,next:u32,sent_prefix:u32,limit:u32,unacked:Option<Duration>,pub cumulative:u32,pub stats:WindowStats}
impl Window {
    pub fn new()->Self {Self::bounded(MAX_SEQUENCE)}
    pub fn interactive()->Self {Self {unacked:Some(INTERACTIVE_LIVENESS),..Self::bounded(INTERACTIVE_MAX_SEQUENCE)}}
    fn bounded(limit:u32)->Self {Self {pending:VecDeque::new(),next:0,sent_prefix:0,limit,unacked:None,cumulative:0,stats:WindowStats::default()}}
    pub fn enqueue(&mut self)->io::Result<()> {
        self.enqueue_body(&[])
    }
    pub fn enqueue_body(&mut self,body:&[u8])->io::Result<()> {
        if body.len()>512 || self.pending.len()>=8 || self.next>=self.limit {return Err(invalid());}
        self.pending.push_back(Pending {sequence:self.next,queued:Instant::now(),sent_wall:None,first:None,last:None,attempts:0,body:body.to_vec()});self.next+=1;
        self.stats.pending_max=self.stats.pending_max.max(self.pending.len());Ok(())
    }
    // Return the sequence only after the existing atomic enqueue succeeds.
    // This adds no ACK policy, wraparound or alternative queue implementation.
    pub fn enqueue_body_tracked(&mut self,body:&[u8])->io::Result<u32> {
        let sequence=self.next;self.enqueue_body(body)?;Ok(sequence)
    }
    pub fn len(&self)->usize {self.pending.len()}
    /// Inbound silence a session tolerates; the same bound as unacknowledged age.
    pub fn idle_limit(&self)->Duration {self.unacked.unwrap_or(LAB_IDLE)}
    pub fn validate_ack(&self,frame:&Frame)->io::Result<()> {
        if let Some(c)=frame.cumulative {
            if c>self.sent_prefix {return Err(invalid());}
        }
        for s in &frame.selective {if *s>=self.sent_prefix {return Err(invalid());}}
        Ok(())
    }
    pub fn acknowledge(&mut self,frame:&Frame)->io::Result<()> {
        self.validate_ack(frame)?;
        if let Some(c)=frame.cumulative {self.cumulative=self.cumulative.max(c);}
        // Diagnostics read the wall clock; protocol decisions never do.
        let wall=Instant::now();let stats=&mut self.stats;let cumulative=self.cumulative;
        self.pending.retain(|p|{
            let keep=p.sequence>=cumulative && !frame.selective.contains(&p.sequence);
            if !keep {if let Some(sent)=p.sent_wall {stats.ack_wait.record(wall.saturating_duration_since(sent));}}
            keep
        });Ok(())
    }
    pub fn due(&mut self,now:Instant,next_rx:u32)->io::Result<Option<(u32,u8,Vec<u8>)>> {
        if let Some(p)=self.pending.iter_mut().find(|p|p.last.is_none_or(|t|now.duration_since(t)>=RETRY)) {
            let exhausted=match self.unacked {
                Some(limit)=>p.first.is_some_and(|t|now.duration_since(t)>=limit),
                None=>p.attempts>=LAB_SENDS,
            };
            if exhausted {return Err(io::Error::new(io::ErrorKind::TimedOut,"reliable retry exhausted"));}
            // The queue sends every first transmission in sequence order.
            // A prefix counter proves all older packets were actually sent,
            // including packets already selectively ACKed and freed. Memory
            // stays eight pending packets instead of a lifetime bitset/history.
            if p.last.is_none() {
                if p.sequence!=self.sent_prefix {return Err(invalid());}
                self.sent_prefix+=1;p.first=Some(now);
                let wall=Instant::now();p.sent_wall=Some(wall);
                self.stats.queue_wait.record(wall.saturating_duration_since(p.queued));
            } else {self.stats.resends=self.stats.resends.saturating_add(1);}
            p.attempts=p.attempts.saturating_add(1);p.last=Some(now);
            let mut clear=reliable(p.sequence,next_rx);clear.splice(2..2,p.body.iter().copied());
            return Ok(Some((p.sequence,p.attempts,clear)));
        } Ok(None)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn feedback(c:u32,s:Option<u32>)->Frame {
        let mut b=vec![if s.is_some(){0x4c}else{0x48},4];b.extend(1u32.to_le_bytes());
        if let Some(s)=s {b.extend(s.to_le_bytes());b.push(1);} b.extend(c.to_le_bytes());parse(&b).unwrap()
    }
    #[test] fn real_gap_feedback_and_every_truncation() {
        let b=[0x4c,4,1,0,0,0,1,0,0,0,1,0,0,0,0];let f=parse(&b).unwrap();
        assert_eq!(f.selective,vec![1]);assert_eq!(f.cumulative,Some(0));assert!(f.body.is_empty());
        for n in 0..b.len() {assert!(parse(&b[..n]).is_err());}
        let mut bad=b;bad[10]=0;assert!(parse(&bad).is_err());bad[10]=17;assert!(parse(&bad).is_err());
        assert!(parse(&vec![0;1025]).is_err());assert!(parse(&[0x78,4,0,0,0,0,0,0,0,0]).is_err());
    }
    #[test] fn selective_ack_cannot_confirm_gap_and_retries_stop_after_ack() {
        let now=Instant::now();let mut w=Window::new();w.enqueue().unwrap();w.enqueue().unwrap();
        assert!(w.acknowledge(&feedback(2,None)).is_err());assert_eq!(w.len(),2);
        assert_eq!(w.due(now,1).unwrap().unwrap().0,0);assert_eq!(w.due(now,1).unwrap().unwrap().0,1);
        w.acknowledge(&feedback(0,Some(1))).unwrap();assert_eq!(w.len(),1);assert_eq!(w.cumulative,0);
        assert!(w.due(now+RETRY/2,1).unwrap().is_none());
        assert_eq!(w.due(now+RETRY,1).unwrap().unwrap().0,0);
        w.acknowledge(&feedback(2,None)).unwrap();assert_eq!(w.len(),0);assert_eq!(w.cumulative,2);
        w.acknowledge(&feedback(0,Some(1))).unwrap();assert_eq!(w.cumulative,2);
        assert!(w.due(now+RETRY*2,1).unwrap().is_none());
    }
    #[test] fn invalid_ack_is_atomic_and_retries_bounded() {
        let now=Instant::now();let mut w=Window::new();w.enqueue().unwrap();w.due(now,1).unwrap();
        assert!(w.acknowledge(&feedback(1,Some(2))).is_err());assert_eq!(w.cumulative,0);assert_eq!(w.len(),1);
        for i in 1..5 {assert!(w.due(now+RETRY*i,1).unwrap().is_some());}
        assert!(w.due(now+RETRY*5,1).is_err());
        let mut bounded=Window::new();for _ in 0..8 {bounded.enqueue().unwrap();}assert!(bounded.enqueue().is_err());
    }
    #[test] fn interactive_window_survives_a_measured_client_stall_and_bounds_by_age() {
        let now=Instant::now();let mut w=Window::interactive();w.enqueue().unwrap();w.enqueue().unwrap();
        assert_eq!(w.due(now,1).unwrap().unwrap().1,1);
        // 7.07 s without client traffic was observed while #717 refreshed the hangar.
        let mut at=now;let mut resends=0;
        while at<now+Duration::from_millis(7070) {at+=RETRY;while w.due(at,1).unwrap().is_some() {resends+=1;}}
        assert!(resends>2*LAB_SENDS as usize);
        w.acknowledge(&feedback(2,None)).unwrap();assert_eq!(w.len(),0);
        w.enqueue().unwrap();let start=now+Duration::from_secs(8);assert_eq!(w.due(start,1).unwrap().unwrap().0,2);
        // The age counts from the first send of this packet, not the session start.
        assert!(w.due(start+INTERACTIVE_LIVENESS-RETRY,1).unwrap().is_some());
        assert!(w.due(start+INTERACTIVE_LIVENESS,1).is_err());
        assert!(w.acknowledge(&feedback(4,None)).is_err());assert_eq!((w.len(),w.cumulative),(1,2));
        assert_eq!((w.idle_limit(),Window::new().idle_limit()),(INTERACTIVE_LIVENESS,LAB_IDLE));
    }
    #[test] fn payload_is_owned_bounded_and_preserved_on_retry() {
        let now=Instant::now();let mut w=Window::new();
        assert!(w.enqueue_body(&vec![0;513]).is_err());assert_eq!(w.len(),0);
        let mut body=vec![5,1,0,42];w.enqueue_body(&body).unwrap();body[3]=99;
        let first=parse(&w.due(now,1).unwrap().unwrap().2).unwrap();
        assert_eq!(first.body,vec![5,1,0,42]);assert_eq!(first.sequence,Some(0));
        let retry=parse(&w.due(now+RETRY,2).unwrap().unwrap().2).unwrap();
        assert_eq!(retry.body,first.body);assert_eq!(retry.sequence,first.sequence);
        assert_eq!(retry.cumulative,Some(2));
        w.acknowledge(&feedback(1,None)).unwrap();assert!(w.due(now+RETRY*2,2).unwrap().is_none());
    }
    #[test] fn interactive_ack_prefix_crosses_4096_with_constant_memory_and_no_unsent_ack() {
        let now=Instant::now();let mut w=Window::interactive();
        for n in 0..5000 {
            w.enqueue_body(&[42,7]).unwrap();
            let mut ack=Frame {flags:0x408,sequence:None,cumulative:Some(n+1),selective:vec![],body:vec![],piggybacks:vec![]};
            assert!(w.acknowledge(&ack).is_err());assert_eq!(w.cumulative,n);
            let sent=w.due(now,n).unwrap().unwrap();assert_eq!(sent.0,n);
            let decoded=parse_interactive(&sent.2).unwrap();assert_eq!(decoded.body,vec![42,7]);
            assert_eq!(decoded.sequence,Some(n));
            if n%7==0 {
                ack.cumulative=Some(n);ack.selective=vec![n];w.acknowledge(&ack).unwrap();
                assert_eq!(w.len(),0);ack.cumulative=Some(n+1);ack.selective.clear();
            }
            w.acknowledge(&ack).unwrap();assert_eq!(w.len(),0);assert_eq!(w.sent_prefix,n+1);
            assert_eq!(w.cumulative,n+1);
        }
        let old=Frame {flags:0x40c,sequence:None,cumulative:Some(1),selective:vec![0],body:vec![],piggybacks:vec![]};
        w.acknowledge(&old).unwrap();assert_eq!(w.cumulative,5000);
        let first=w.due(now+RETRY,5000).unwrap();assert!(first.is_none());
        assert!(parse(&reliable(1,33)).is_err()); // Original laboratory parser stays capped.
    }
    #[test] fn interactive_lifetime_stops_without_wrap_or_queue_growth() {
        let mut w=Window::bounded(40);let now=Instant::now();
        for n in 0..40 {
            w.enqueue().unwrap();assert_eq!(w.due(now,n).unwrap().unwrap().0,n);
            let f=Frame {flags:0x408,sequence:None,cumulative:Some(n+1),selective:vec![],body:vec![],piggybacks:vec![]};
            w.acknowledge(&f).unwrap();
        }
        assert!(w.enqueue().is_err());assert_eq!((w.next,w.sent_prefix,w.len()),(40,40,0));
        assert!(parse_interactive(&reliable(INTERACTIVE_MAX_SEQUENCE,0)).is_err());
        assert!(parse_interactive(&reliable(0,INTERACTIVE_MAX_SEQUENCE+1)).is_err());
        assert!(parse_interactive(&reliable(u32::MAX,0)).is_err());
    }
    #[test] fn tracked_enqueue_returns_only_the_owned_body_sequence_after_success() {
        let now=Instant::now();let mut w=Window::new();
        assert!(w.enqueue_body_tracked(&vec![0;513]).is_err());assert_eq!((w.next,w.len()),(0,0));
        for n in 0..8 {assert_eq!(w.enqueue_body_tracked(&[n as u8]).unwrap(),n);}
        assert!(w.enqueue_body_tracked(&[42]).is_err());assert_eq!((w.next,w.len()),(8,8));
        for n in 0..8 {
            let sent=w.due(now,1).unwrap().unwrap();assert_eq!(sent.0,n);
            assert_eq!(parse(&sent.2).unwrap().body,vec![n as u8]);
        }
        w.acknowledge(&feedback(8,None)).unwrap();
        assert_eq!(w.enqueue_body_tracked(&[42]).unwrap(),8);
        assert!(w.acknowledge(&feedback(9,None)).is_err()); // queued is not sent
        let sent=w.due(now,1).unwrap().unwrap();assert_eq!(sent.0,8);assert_eq!(parse(&sent.2).unwrap().body,vec![42]);
    }
    #[test] fn net01_unreliable_frame_is_0408_with_body_and_ack_but_no_sequence() {
        let clear=unreliable(7,&[0x0d,0xe9,0x15]).unwrap();assert_eq!(clear,vec![8,4,0x0d,0xe9,0x15,7,0,0,0]);
        let f=parse_interactive(&clear).unwrap();
        assert_eq!((f.flags,f.sequence,f.cumulative,f.body.as_slice()),(0x408,None,Some(7),&[0x0d,0xe9,0x15][..]));
        assert!(unreliable(7,&[]).is_err());assert!(unreliable(7,&vec![0;513]).is_err());
        assert_eq!(unreliable(7,&vec![1;512]).unwrap().len(),518);
    }
    #[test] fn net01_window_stats_measure_queue_ack_resend_and_pending() {
        let now=Instant::now();let mut w=Window::interactive();
        for _ in 0..3 {w.enqueue().unwrap();}assert_eq!(w.stats.pending_max,3);
        while w.due(now,1).unwrap().is_some() {}
        assert_eq!(w.stats.queue_wait.count(),3);assert_eq!(w.stats.resends,0);
        assert!(w.due(now+RETRY,1).unwrap().is_some());assert_eq!(w.stats.resends,1);
        w.acknowledge(&feedback(2,None)).unwrap();assert_eq!(w.stats.ack_wait.count(),2);
        let mut h=Histogram::default();for ms in [0.5,3.,40.,40.,900.] {h.record_ms(ms);}
        assert_eq!((h.quantile_ms(0.2),h.quantile_ms(0.5),h.quantile_ms(0.8),h.quantile_ms(1.)),(1.,50.,50.,900.));
        assert_eq!(h.summary(),"n=5 mean=196.7 p50<=50.0 p95<=900.0 p99<=900.0 max=900.0");
        assert_eq!(Histogram::default().summary(),"n=0 mean=0.0 p50<=0.0 p95<=0.0 p99<=0.0 max=0.0");
    }
    #[test] fn tracked_sequence_limit_fails_closed_without_reusing_or_wrapping() {
        let now=Instant::now();let mut w=Window::new();
        for n in 0..MAX_SEQUENCE {
            assert_eq!(w.enqueue_body_tracked(&[42]).unwrap(),n);
            assert_eq!(w.due(now,1).unwrap().unwrap().0,n);w.acknowledge(&feedback(n+1,None)).unwrap();
        }
        assert!(w.enqueue_body_tracked(&[42]).is_err());
        assert_eq!((w.next,w.sent_prefix,w.len(),w.cumulative),(MAX_SEQUENCE,MAX_SEQUENCE,0,MAX_SEQUENCE));
    }
}
