//! Bounded measured 0.9.1 transport subset. No fragments or entity dispatch.
use std::{collections::VecDeque,io,time::{Duration,Instant}};
pub(crate) const MAX_SEQUENCE:u32=32; // Lab lifetime bound, not the native wraparound modulus.
pub(crate) const INTERACTIVE_MAX_SEQUENCE:u32=1_000_000; // Safety stop before any unmeasured wraparound.
pub const RETRY:Duration=Duration::from_millis(700);
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
pub fn reliable(sequence:u32,next:u32)->Vec<u8> {let mut b=vec![0x58,4];b.extend(sequence.to_le_bytes());b.extend(next.to_le_bytes());b}

#[derive(Clone)]
struct Pending {sequence:u32,last:Option<Instant>,attempts:u8,body:Vec<u8>}
#[derive(Clone)]
pub struct Window {pending:VecDeque<Pending>,next:u32,sent_prefix:u32,limit:u32,pub cumulative:u32}
impl Window {
    pub fn new()->Self {Self::bounded(MAX_SEQUENCE)}
    pub fn interactive()->Self {Self::bounded(INTERACTIVE_MAX_SEQUENCE)}
    fn bounded(limit:u32)->Self {Self {pending:VecDeque::new(),next:0,sent_prefix:0,limit,cumulative:0}}
    pub fn enqueue(&mut self)->io::Result<()> {
        self.enqueue_body(&[])
    }
    pub fn enqueue_body(&mut self,body:&[u8])->io::Result<()> {
        if body.len()>512 || self.pending.len()>=8 || self.next>=self.limit {return Err(invalid());}
        self.pending.push_back(Pending {sequence:self.next,last:None,attempts:0,body:body.to_vec()});self.next+=1;Ok(())
    }
    // Return the sequence only after the existing atomic enqueue succeeds.
    // This adds no ACK policy, wraparound or alternative queue implementation.
    pub fn enqueue_body_tracked(&mut self,body:&[u8])->io::Result<u32> {
        let sequence=self.next;self.enqueue_body(body)?;Ok(sequence)
    }
    pub fn len(&self)->usize {self.pending.len()}
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
        self.pending.retain(|p|p.sequence>=self.cumulative && !frame.selective.contains(&p.sequence));Ok(())
    }
    pub fn due(&mut self,now:Instant,next_rx:u32)->io::Result<Option<(u32,u8,Vec<u8>)>> {
        if let Some(p)=self.pending.iter_mut().find(|p|p.last.is_none_or(|t|now.duration_since(t)>=RETRY)) {
            if p.attempts>=5 {return Err(io::Error::new(io::ErrorKind::TimedOut,"reliable retry exhausted"));}
            // The queue sends every first transmission in sequence order.
            // A prefix counter proves all older packets were actually sent,
            // including packets already selectively ACKed and freed. Memory
            // stays eight pending packets instead of a lifetime bitset/history.
            if p.last.is_none() {
                if p.sequence!=self.sent_prefix {return Err(invalid());}
                self.sent_prefix+=1;
            }
            p.attempts+=1;p.last=Some(now);
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
