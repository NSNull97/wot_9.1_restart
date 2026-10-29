//! BW-01: bounded binary codec for the arena step crossing a process boundary.
//! Only this gateway build talks to its own worker child over loopback; the
//! format is not a stable protocol and both sides check the same build hash.
//! Every length is bounded by the bytes that remain and by `MAX_LEN`; an `Arc`
//! resource crosses once per connection and is then named by id (pointer
//! identity is kept on both sides); an `Instant` crosses as signed nanoseconds
//! from the side's anchor, so a round trip returns the same instant. A NET-01
//! `Journal` crosses as the tail appended since it last crossed this
//! connection at the same position in the frame, or whole when it changed.
//! Struct/enum impls live next to their types (tools/bw01_wire_gen.py) and
//! destructure exhaustively: a new field without a codec does not compile.
use std::{any::Any,collections::{BTreeMap,BTreeSet,HashMap,HashSet,VecDeque},hash::Hash,io,sync::{Arc,Mutex},time::{Duration,Instant}};

/// Elements of one sequence; a frame is bounded separately by the transport.
pub(crate) const MAX_LEN:usize=1<<24;
/// Distinct shared resources per connection (templates x kinds x maps is far below).
pub(crate) const MAX_ARCS:usize=1<<16;
const MAX_INTERNED:usize=4096;
const MAX_JSON:usize=1<<20;
const MAX_INTERNED_LEN:usize=256;
/// Journals per frame (a World holds a few per actor).
pub(crate) const MAX_JOURNALS:usize=1<<16;

pub(crate) fn bad(what:&str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,format!("bw01 wire: {what}"))}

/// Per-connection table of shared resources. Each side numbers what it sends
/// first (gateway even, worker odd) and keeps a strong reference, so a pointer
/// is never reused for another resource while the connection lives.
/// `journals[k]` = the k-th journal of the last frame that crossed (either way):
/// both sides hold equal contents, so the next frame sends only what was appended.
pub(crate) struct Arcs {next:u32,by_ptr:HashMap<usize,u32>,by_id:HashMap<u32,Box<dyn Any+Send+Sync>>,journals:Vec<Box<dyn Any+Send+Sync>>}
impl Arcs {
    pub(crate) fn new(worker:bool)->Self {Self{next:worker as u32,by_ptr:HashMap::new(),by_id:HashMap::new(),journals:Vec::new()}}
    /// Remember journal slot `k` of this frame (slots are numbered in encode order).
    fn keep_journal(&mut self,k:usize,value:Box<dyn Any+Send+Sync>)->bool {
        match k.cmp(&self.journals.len()) {
            std::cmp::Ordering::Less=>{self.journals[k]=value;true},
            std::cmp::Ordering::Equal if k<MAX_JOURNALS=>{self.journals.push(value);true},
            _=>false,
        }
    }
    pub(crate) fn len(&self)->usize {self.by_id.len()}
    /// `value` is the `Arc` itself (sized or slice), kept alive with its pointer.
    fn insert(&mut self,id:u32,ptr:usize,value:Box<dyn Any+Send+Sync>)->io::Result<()> {
        if self.by_id.len()>=MAX_ARCS||self.by_id.contains_key(&id)||self.by_ptr.contains_key(&ptr) {return Err(bad("shared resource table"));}
        self.by_ptr.insert(ptr,id);self.by_id.insert(id,value);Ok(())
    }
    fn put<T:?Sized+Send+Sync+'static>(w:&mut Enc,arc:&Arc<T>,content:impl FnOnce(&mut Enc)) {
        let ptr=Arc::as_ptr(arc) as *const () as usize;
        if let Some(id)=w.arcs.by_ptr.get(&ptr).copied() {w.bytes(&[0]);id.put(w);return;}
        let id=w.arcs.next;w.arcs.next=w.arcs.next.wrapping_add(2);
        if w.arcs.insert(id,ptr,Box::new(arc.clone())).is_err() {w.fail("shared resource table");}
        w.bytes(&[1]);id.put(w);content(w);
    }
    fn get<T:?Sized+Send+Sync+'static>(r:&mut Dec,content:impl FnOnce(&mut Dec)->io::Result<Arc<T>>)->io::Result<Arc<T>> {
        let tag=u8::get(r)?;let id=u32::get(r)?;
        match tag {
            0=>r.arcs.by_id.get(&id).and_then(|v|v.downcast_ref::<Arc<T>>()).cloned().ok_or_else(||bad("unknown shared resource")),
            1=>{let v=content(r)?;r.arcs.insert(id,Arc::as_ptr(&v) as *const () as usize,Box::new(v.clone()))?;Ok(v)},
            _=>Err(bad("shared resource tag")),
        }
    }
}

pub(crate) struct Enc<'a> {pub(crate) buf:Vec<u8>,anchor:Instant,arcs:&'a mut Arcs,failed:Option<&'static str>,journal:usize}
pub(crate) struct Dec<'a> {buf:&'a [u8],pos:usize,anchor:Instant,arcs:&'a mut Arcs,journal:usize}

impl<'a> Enc<'a> {
    pub(crate) fn new(anchor:Instant,arcs:&'a mut Arcs)->Self {Self{buf:Vec::new(),anchor,arcs,failed:None,journal:0}}
    /// Encoding itself cannot fail midway; a refused value marks the frame.
    pub(crate) fn finish(self)->io::Result<Vec<u8>> {match self.failed {Some(what)=>Err(bad(what)),None=>Ok(self.buf)}}
    pub(crate) fn fail(&mut self,what:&'static str) {self.failed.get_or_insert(what);}
    pub(crate) fn bytes(&mut self,b:&[u8]) {self.buf.extend_from_slice(b);}
    pub(crate) fn tag(&mut self,t:u16) {self.bytes(&t.to_le_bytes());}
    pub(crate) fn len(&mut self,n:usize) {if n>MAX_LEN {self.fail("sequence length");}self.bytes(&(n as u32).to_le_bytes());}
}
impl<'a> Dec<'a> {
    pub(crate) fn new(buf:&'a [u8],anchor:Instant,arcs:&'a mut Arcs)->Self {Self{buf,pos:0,anchor,arcs,journal:0}}
    pub(crate) fn remaining(&self)->usize {self.buf.len()-self.pos}
    pub(crate) fn done(&self)->io::Result<()> {if self.remaining()==0 {Ok(())} else {Err(bad("trailing bytes"))}}
    pub(crate) fn take(&mut self,n:usize)->io::Result<&'a [u8]> {
        if n>self.remaining() {return Err(bad("truncated"));}
        let s=&self.buf[self.pos..self.pos+n];self.pos+=n;Ok(s)
    }
    fn arr<const N:usize>(&mut self)->io::Result<[u8;N]> {Ok(self.take(N)?.try_into().expect("exact length"))}
    pub(crate) fn tag(&mut self)->io::Result<u16> {Ok(u16::from_le_bytes(self.arr()?))}
    /// A count no larger than the remaining bytes: every element takes >= 1 byte.
    pub(crate) fn len(&mut self)->io::Result<usize> {
        let n=u32::from_le_bytes(self.arr()?) as usize;
        if n>MAX_LEN||n>self.remaining() {return Err(bad("sequence length"));}
        Ok(n)
    }
}

pub(crate) trait Wire:Sized {
    fn put(&self,w:&mut Enc);
    fn get(r:&mut Dec)->io::Result<Self>;
}
/// Unknown enum tag (generated impls).
pub(crate) fn variant<T>(_:u16)->io::Result<T> {Err(bad("enum variant"))}

macro_rules! num {($($t:ty),*)=>{$(impl Wire for $t {
    fn put(&self,w:&mut Enc){w.bytes(&self.to_le_bytes());}
    fn get(r:&mut Dec)->io::Result<Self>{Ok(<$t>::from_le_bytes(r.arr()?))}
})*}}
num!(u8,u16,u32,u64,u128,i8,i16,i32,i64,i128,f32,f64);
impl Wire for usize {
    fn put(&self,w:&mut Enc){(*self as u64).put(w);}
    fn get(r:&mut Dec)->io::Result<Self>{usize::try_from(u64::get(r)?).map_err(|_|bad("usize"))}
}
impl Wire for isize {
    fn put(&self,w:&mut Enc){(*self as i64).put(w);}
    fn get(r:&mut Dec)->io::Result<Self>{isize::try_from(i64::get(r)?).map_err(|_|bad("isize"))}
}
impl Wire for bool {
    fn put(&self,w:&mut Enc){w.bytes(&[*self as u8]);}
    fn get(r:&mut Dec)->io::Result<Self>{match u8::get(r)? {0=>Ok(false),1=>Ok(true),_=>Err(bad("bool"))}}
}
impl Wire for char {
    fn put(&self,w:&mut Enc){(*self as u32).put(w);}
    fn get(r:&mut Dec)->io::Result<Self>{char::from_u32(u32::get(r)?).ok_or_else(||bad("char"))}
}
impl Wire for () {fn put(&self,_:&mut Enc){} fn get(_:&mut Dec)->io::Result<Self>{Ok(())}}
impl Wire for String {
    fn put(&self,w:&mut Enc){w.len(self.len());w.bytes(self.as_bytes());}
    fn get(r:&mut Dec)->io::Result<Self>{let n=r.len()?;String::from_utf8(r.take(n)?.to_vec()).map_err(|_|bad("utf8"))}
}
/// Policy/label constants. A decoded name is interned once (bounded set).
impl Wire for &'static str {
    fn put(&self,w:&mut Enc){if self.len()>MAX_INTERNED_LEN {w.fail("static string");}w.len(self.len());w.bytes(self.as_bytes());}
    fn get(r:&mut Dec)->io::Result<Self>{
        static SET:Mutex<BTreeSet<&'static str>>=Mutex::new(BTreeSet::new());
        let n=r.len()?;if n>MAX_INTERNED_LEN {return Err(bad("static string"));}
        let s=std::str::from_utf8(r.take(n)?).map_err(|_|bad("utf8"))?;
        let mut set=SET.lock().map_err(|_|bad("intern table"))?;
        if let Some(found)=set.get(s) {return Ok(found);}
        if set.len()>=MAX_INTERNED {return Err(bad("intern table full"));}
        let leaked:&'static str=Box::leak(s.to_owned().into_boxed_str());set.insert(leaked);Ok(leaked)
    }
}
impl Wire for std::path::PathBuf {
    fn put(&self,w:&mut Enc){match self.to_str() {Some(s)=>s.to_owned().put(w),None=>{w.fail("non-UTF-8 path");String::new().put(w);}}}
    fn get(r:&mut Dec)->io::Result<Self>{Ok(String::get(r)?.into())}
}
/// Bounded JSON facts (hold capture fields); parsed with serde_json's depth limit.
impl Wire for serde_json::Value {
    fn put(&self,w:&mut Enc){let text=self.to_string();if text.len()>MAX_JSON {w.fail("json size");}text.put(w);}
    fn get(r:&mut Dec)->io::Result<Self>{
        let text=String::get(r)?;if text.len()>MAX_JSON {return Err(bad("json size"));}
        serde_json::from_str(&text).map_err(|_|bad("json"))
    }
}
impl Wire for Duration {
    fn put(&self,w:&mut Enc){self.as_secs().put(w);self.subsec_nanos().put(w);}
    fn get(r:&mut Dec)->io::Result<Self>{
        let (s,n)=(u64::get(r)?,u32::get(r)?);if n>=1_000_000_000 {return Err(bad("duration"));}Ok(Duration::new(s,n))
    }
}
impl Wire for Instant {
    fn put(&self,w:&mut Enc){
        let n=if *self>=w.anchor {i64::try_from(self.duration_since(w.anchor).as_nanos()).ok()}
            else {i64::try_from(w.anchor.duration_since(*self).as_nanos()).ok().map(|n|-n)};
        match n {Some(n)=>n.put(w),None=>{w.fail("instant range");0i64.put(w);}}
    }
    fn get(r:&mut Dec)->io::Result<Self>{
        let n=i64::get(r)?;
        if n>=0 {r.anchor.checked_add(Duration::from_nanos(n as u64))} else {r.anchor.checked_sub(Duration::from_nanos(n.unsigned_abs()))}
            .ok_or_else(||bad("instant range"))
    }
}
impl<T:Wire> Wire for Option<T> {
    fn put(&self,w:&mut Enc){match self {None=>w.bytes(&[0]),Some(v)=>{w.bytes(&[1]);v.put(w);}}}
    fn get(r:&mut Dec)->io::Result<Self>{match u8::get(r)? {0=>Ok(None),1=>Ok(Some(T::get(r)?)),_=>Err(bad("option"))}}
}
impl<T:Wire,E:Wire> Wire for Result<T,E> {
    fn put(&self,w:&mut Enc){match self {Ok(v)=>{w.bytes(&[0]);v.put(w);},Err(e)=>{w.bytes(&[1]);e.put(w);}}}
    fn get(r:&mut Dec)->io::Result<Self>{match u8::get(r)? {0=>Ok(Ok(T::get(r)?)),1=>Ok(Err(E::get(r)?)),_=>Err(bad("result"))}}
}
impl<T:Wire> Wire for Box<T> {
    fn put(&self,w:&mut Enc){(**self).put(w);}
    fn get(r:&mut Dec)->io::Result<Self>{Ok(Box::new(T::get(r)?))}
}
impl<T:Wire> Wire for Vec<T> {
    fn put(&self,w:&mut Enc){w.len(self.len());for v in self {v.put(w);}}
    fn get(r:&mut Dec)->io::Result<Self>{let n=r.len()?;let mut v=Vec::with_capacity(n);for _ in 0..n {v.push(T::get(r)?);}Ok(v)}
}
impl<T:Wire> Wire for VecDeque<T> {
    fn put(&self,w:&mut Enc){w.len(self.len());for v in self {v.put(w);}}
    fn get(r:&mut Dec)->io::Result<Self>{Ok(Vec::get(r)?.into())}
}
impl<T:Wire,const N:usize> Wire for [T;N] {
    fn put(&self,w:&mut Enc){for v in self {v.put(w);}}
    fn get(r:&mut Dec)->io::Result<Self>{
        let mut v=Vec::with_capacity(N);for _ in 0..N {v.push(T::get(r)?);}
        v.try_into().map_err(|_|bad("array"))
    }
}
impl<K:Wire+Ord,V:Wire> Wire for BTreeMap<K,V> {
    fn put(&self,w:&mut Enc){w.len(self.len());for (k,v) in self {k.put(w);v.put(w);}}
    fn get(r:&mut Dec)->io::Result<Self>{
        let n=r.len()?;let mut m=BTreeMap::new();
        for _ in 0..n {let k=K::get(r)?;if m.insert(k,V::get(r)?).is_some() {return Err(bad("duplicate key"));}}Ok(m)
    }
}
impl<K:Wire+Ord> Wire for BTreeSet<K> {
    fn put(&self,w:&mut Enc){w.len(self.len());for k in self {k.put(w);}}
    fn get(r:&mut Dec)->io::Result<Self>{
        let n=r.len()?;let mut m=BTreeSet::new();
        for _ in 0..n {if !m.insert(K::get(r)?) {return Err(bad("duplicate key"));}}Ok(m)
    }
}
impl<K:Wire+Eq+Hash,V:Wire> Wire for HashMap<K,V> {
    fn put(&self,w:&mut Enc){w.len(self.len());for (k,v) in self {k.put(w);v.put(w);}}
    fn get(r:&mut Dec)->io::Result<Self>{
        let n=r.len()?;let mut m=HashMap::with_capacity(n);
        for _ in 0..n {let k=K::get(r)?;if m.insert(k,V::get(r)?).is_some() {return Err(bad("duplicate key"));}}Ok(m)
    }
}
impl<K:Wire+Eq+Hash> Wire for HashSet<K> {
    fn put(&self,w:&mut Enc){w.len(self.len());for k in self {k.put(w);}}
    fn get(r:&mut Dec)->io::Result<Self>{
        let n=r.len()?;let mut m=HashSet::with_capacity(n);
        for _ in 0..n {if !m.insert(K::get(r)?) {return Err(bad("duplicate key"));}}Ok(m)
    }
}
macro_rules! tuple {($($n:ident),+)=>{impl<$($n:Wire),+> Wire for ($($n,)+) {
    #[allow(non_snake_case)] fn put(&self,w:&mut Enc){let ($($n,)+)=self;$($n.put(w);)+}
    fn get(r:&mut Dec)->io::Result<Self>{Ok(($($n::get(r)?,)+))}
}}}
tuple!(A);tuple!(A,B);tuple!(A,B,C);tuple!(A,B,C,D);tuple!(A,B,C,D,E);tuple!(A,B,C,D,E,F);tuple!(A,B,C,D,E,F,G);tuple!(A,B,C,D,E,F,G,H);
/// A shared resource: content on first use per connection, then its id.
impl<T:Wire+Send+Sync+'static> Wire for Arc<T> {
    fn put(&self,w:&mut Enc){Arcs::put(w,self,|w|(**self).put(w));}
    fn get(r:&mut Dec)->io::Result<Self>{Arcs::get(r,|r|Ok(Arc::new(T::get(r)?)))}
}
impl<T:Wire+Send+Sync+'static> Wire for Arc<[T]> {
    fn put(&self,w:&mut Enc){Arcs::put(w,self,|w|{w.len(self.len());for v in self.iter() {v.put(w);}});}
    fn get(r:&mut Dec)->io::Result<Self>{Arcs::get(r,|r|Ok(Vec::<T>::get(r)?.into()))}
}
impl<T:Wire> Wire for Box<[T]> {
    fn put(&self,w:&mut Enc){w.len(self.len());for v in self.iter() {v.put(w);}}
    fn get(r:&mut Dec)->io::Result<Self>{Ok(Vec::<T>::get(r)?.into_boxed_slice())}
}

/// Journal: 0 + all rows, or 1 + the row count both sides already hold in this
/// slot + the appended rows. A journal that shrank or changed a crossed row
/// (a reset arena, another actor in the slot) crosses whole.
impl<T:Wire+Clone+PartialEq+Send+Sync+'static> Wire for crate::gateway091::shared::journal::Journal<T> {
    fn put(&self,w:&mut Enc){
        let k=w.journal;w.journal+=1;
        let held=w.arcs.journals.get(k).and_then(|v|v.downcast_ref::<Self>())
            .filter(|h|h.len()<=self.len()&&(std::ptr::eq(&***h,&**self)||h[..]==self[..h.len()])).map(|h|h.len());
        match held {
            Some(n)=>{w.bytes(&[1]);(n as u64).put(w);w.len(self.len()-n);for v in &self[n..] {v.put(w);}},
            None=>{w.bytes(&[0]);(**self).put(w);},
        }
        if !w.arcs.keep_journal(k,Box::new(self.clone())) {w.fail("journal table");}
    }
    fn get(r:&mut Dec)->io::Result<Self>{
        let k=r.journal;r.journal+=1;
        let value:Self=match u8::get(r)? {
            0=>Vec::<T>::get(r)?.into(),
            1=>{
                let n=u64::get(r)?;
                let mut v=r.arcs.journals.get(k).and_then(|v|v.downcast_ref::<Self>()).filter(|h|h.len() as u64==n).cloned()
                    .ok_or_else(||bad("journal base"))?;
                let tail=Vec::<T>::get(r)?;
                if !tail.is_empty() {v.extend(tail);}
                v
            },
            _=>return Err(bad("journal tag")),
        };
        if !r.arcs.keep_journal(k,Box::new(value.clone())) {return Err(bad("journal table"));}
        Ok(value)
    }
}

/// Encode one value with this side's anchor and resource table.
pub(crate) fn encode<T:Wire>(value:&T,anchor:Instant,arcs:&mut Arcs)->io::Result<Vec<u8>> {
    let mut w=Enc::new(anchor,arcs);value.put(&mut w);w.finish()
}
/// Decode exactly one value; trailing bytes are refused.
pub(crate) fn decode<T:Wire>(bytes:&[u8],anchor:Instant,arcs:&mut Arcs)->io::Result<T> {
    let mut r=Dec::new(bytes,anchor,arcs);let v=T::get(&mut r)?;r.done()?;Ok(v)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn bw01_wire_primitives_round_trip_and_bounds() {
        let anchor=Instant::now();let mut a=Arcs::new(false);let mut b=Arcs::new(true);
        let value=(7u8,-3i64,1.5f32,true,"x".to_owned(),Some(vec![1u16,2,3]),[Some(2usize),None],anchor+Duration::from_millis(5));
        let bytes=encode(&value,anchor,&mut a).unwrap();
        let back:(u8,i64,f32,bool,String,Option<Vec<u16>>,[Option<usize>;2],Instant)=decode(&bytes,anchor,&mut b).unwrap();
        assert!(back==value);
        // A length larger than the remaining bytes is refused before allocation.
        let mut huge=Vec::new();huge.extend_from_slice(&(u32::MAX).to_le_bytes());
        assert!(decode::<Vec<u8>>(&huge,anchor,&mut b).is_err());
        assert!(decode::<bool>(&[2],anchor,&mut b).is_err());
        assert!(decode::<u8>(&[1,2],anchor,&mut b).is_err());
    }
    #[test] fn bw01_wire_instant_crosses_between_anchors_exactly() {
        let g=Instant::now();let w=g+Duration::from_secs(3);
        let (mut a,mut b)=(Arcs::new(false),Arcs::new(true));
        for t in [g,g+Duration::from_nanos(123_456_789),g.checked_sub(Duration::from_millis(40)).unwrap_or(g)] {
            let on_worker:Instant=decode(&encode(&t,g,&mut a).unwrap(),w,&mut b).unwrap();
            if t>=g {assert_eq!(on_worker.duration_since(w),t.duration_since(g));}
            let back:Instant=decode(&encode(&on_worker,w,&mut b).unwrap(),g,&mut a).unwrap();
            assert_eq!(back,t);
        }
    }
    #[test] fn bw01_wire_shared_resource_crosses_once_and_keeps_identity() {
        let anchor=Instant::now();let (mut gw,mut wk)=(Arcs::new(false),Arcs::new(true));
        let r=Arc::new(vec![9u8;1000]);
        let first=encode(&(r.clone(),r.clone()),anchor,&mut gw).unwrap();
        assert!(first.len()<1100,"content sent once per frame pair");
        let (x,y):(Arc<Vec<u8>>,Arc<Vec<u8>>)=decode(&first,anchor,&mut wk).unwrap();
        assert!(Arc::ptr_eq(&x,&y));
        let again=encode(&r,anchor,&mut gw).unwrap();assert_eq!(again.len(),5);
        // The worker returns the same resource by id; the gateway gets its own pointer back.
        let back:Arc<Vec<u8>>=decode(&encode(&x,anchor,&mut wk).unwrap(),anchor,&mut gw).unwrap();
        assert!(Arc::ptr_eq(&back,&r));
        assert!(decode::<Arc<Vec<u8>>>(&[0,99,0,0,0],anchor,&mut wk).is_err());
    }
    #[test] fn bw01_wire_journal_crosses_its_appended_rows_and_whole_when_it_changed() {
        use crate::gateway091::shared::journal::Journal;
        let anchor=Instant::now();let (mut gw,mut wk)=(Arcs::new(false),Arcs::new(true));
        let mut a:Journal<u64>=(0..1000).collect::<Vec<_>>().into();let b:Journal<u64>=vec![5].into();
        let first=encode(&(a.clone(),b.clone()),anchor,&mut gw).unwrap();assert!(first.len()>8000);
        let (mut x,y):(Journal<u64>,Journal<u64>)=decode(&first,anchor,&mut wk).unwrap();
        assert_eq!((&x,&y),(&a,&b));
        // The worker appends; only the new rows come back.
        x.push(1000);x.push(1001);
        let back=encode(&(x.clone(),y.clone()),anchor,&mut wk).unwrap();assert!(back.len()<50,"{}",back.len());
        let (x2,y2):(Journal<u64>,Journal<u64>)=decode(&back,anchor,&mut gw).unwrap();
        assert_eq!((&x2,&y2),(&x,&y));
        // A changed crossed row (or a shorter journal) crosses whole; the slots swap types safely.
        a=x2.clone();a[3]=7;
        let changed=encode(&(a.clone(),Journal::<u64>::new()),anchor,&mut gw).unwrap();assert!(changed.len()>8000);
        let (x3,y3):(Journal<u64>,Journal<u64>)=decode(&changed,anchor,&mut wk).unwrap();
        assert_eq!((&x3,y3.len()),(&a,0));
        // A delta naming rows the receiver does not hold is refused.
        let mut fresh=Arcs::new(true);
        assert!(decode::<Journal<u64>>(&encode(&x3,anchor,&mut gw).unwrap(),anchor,&mut fresh).is_err());
    }
}
