//! UI-02: the recipient-only project channel of battle events. Research, the
//! transport decision and the disclosure policy: docs/plans/UI02_HIT_INDICATOR.md.
//!
//! Domain events name server slots and facts; `frame` is the only place where
//! a slot becomes a network ID. Nothing here decides a hit, damage or
//! visibility: the publication passes what this recipient may learn.
use std::io;
use std::time::{Duration,Instant};
use super::{lifecycle_wire,wire};

/// Project type of Avatar.updateArena. #717 ARENA_UPDATE ends at 11 and
/// ClientArena.update (line 203) ignores an unknown type (VERIFIED bytecode).
pub const ARENA_UPDATE_TYPE:u8=200;
pub const VERSION:u8=1;
/// setDevelopmentFeature name of a prepared client; no #717 path sends it.
pub const HELLO_FEATURE:&[u8]=b"sr_battle_events";
/// UI-03: a client with the feed widget asks for feed records on top of the
/// channel. Without this hello the channel carries no feed byte.
pub const FEED_FEATURE:&[u8]=b"sr_battle_feed";
const MAGIC:[u8;2]=*b"BE";
/// One frame stays in one VAR1 argument of updateArena.
pub const MAX_FRAME_BYTES:usize=240;
pub const MAX_EVENTS_PER_FRAME:usize=8;
pub const MAX_CRITICALS:usize=4;
pub const MAX_FRAMES_PER_SECOND:u8=10;
/// A slow peer loses events, never the channel: above this backlog of the
/// reliable outbox a frame is dropped and counted.
pub const MAX_OUTBOX_BACKLOG:usize=16;
/// A prepared client repeats its hello a few times; more are not answered.
pub const MAX_HELLOS:u8=8;
const NO_VALUE:u16=u16::MAX;

fn bad(reason:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,reason)}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Verdict {Unknown=0,Pierced=1,NotPierced=2,Ricochet=3,Splash=4}
/// The shooter as this recipient may know it: a hidden one has no identity.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Source {Hidden,Visible(usize)}
/// `extra` is the native index of an own-vehicle extra, as in
/// showVehicleDamageInfo; the vehicle owner already receives it.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum Critical {Device{extra:u8,destroyed:bool},Crew{extra:u8},Fire}
/// One shell that reached the recipient's own vehicle.
#[derive(Clone,Debug,PartialEq)]
pub struct HitReceived {
    pub shot:u32,
    /// The native hit-indicator yaw: horizontal flight heading of the shell.
    pub yaw:f32,
    pub damage:u16,
    /// None: this recipient has no fact to show. It is never estimated.
    pub blocked:Option<u16>,
    pub verdict:Verdict,
    pub friendly:bool,
    pub fatal:bool,
    pub source:Source,
    pub criticals:Vec<Critical>,
}
/// UI-03: facts of the recipient's own battle. A number is the wire value of
/// the record, so it never changes meaning. docs/plans/UI03_BATTLE_FEEDS.md
/// lists what the server does not model and therefore has no kind here.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub enum FeedKind {ShotDamage=1,RamDamage=2,Kill=3,Spotted=4,CapturePoints=5,DefencePoints=6,
    Ignition=7,FireDamage=8,Critical=9,TrackDown=10,RamReceived=11,FireReceived=12,FireCritical=13,
    AssistSpot=14,AssistTrack=15}
/// `value` and `vehicle` None: this recipient may not know that fact.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct FeedEvent {pub kind:FeedKind,pub value:Option<u16>,pub vehicle:Option<usize>}
#[derive(Clone,Debug,PartialEq)]
pub enum Event {HitReceived(HitReceived),Feed(FeedEvent)}

/// Event kinds of the wire. A client skips an unknown kind by its length, so
/// UI-03/04 add kinds without a new version; a layout change bumps VERSION.
const KIND_HELLO:u8=0;
const KIND_HIT_RECEIVED:u8=1;
const KIND_FEED:u8=2;

fn hit_payload(hit:&HitReceived)->io::Result<Vec<u8>> {
    if !hit.yaw.is_finite()||hit.criticals.len()>MAX_CRITICALS||hit.blocked==Some(NO_VALUE)||hit.damage==NO_VALUE {
        return Err(bad("battle event hit bound"));
    }
    let mut b=hit.shot.to_le_bytes().to_vec();
    b.extend(hit.yaw.to_le_bytes());
    b.extend(hit.damage.to_le_bytes());
    b.extend(hit.blocked.unwrap_or(NO_VALUE).to_le_bytes());
    b.push(hit.verdict as u8);
    b.push(u8::from(hit.friendly)|u8::from(hit.fatal)<<1);
    b.extend(match hit.source {Source::Hidden=>0,Source::Visible(slot)=>wire::vehicle_id(slot)?}.to_le_bytes());
    b.push(hit.criticals.len() as u8);
    for critical in &hit.criticals {
        b.extend(match *critical {
            Critical::Device{extra,destroyed:false}=>[1,extra],
            Critical::Device{extra,destroyed:true}=>[2,extra],
            Critical::Crew{extra}=>[3,extra],
            Critical::Fire=>[4,0],
        });
    }
    Ok(b)
}
fn feed_payload(event:&FeedEvent)->io::Result<Vec<u8>> {
    if event.value==Some(NO_VALUE) {return Err(bad("battle event feed bound"));}
    let mut b=vec![event.kind as u8];
    b.extend(event.value.unwrap_or(NO_VALUE).to_le_bytes());
    b.extend(event.vehicle.map(wire::vehicle_id).transpose()?.unwrap_or(0).to_le_bytes());
    Ok(b)
}
fn with_header(sequence:u16,count:usize,body:&[u8])->io::Result<Vec<u8>> {
    if count>MAX_EVENTS_PER_FRAME {return Err(bad("battle event count"));}
    let mut literal=MAGIC.to_vec();
    literal.push(VERSION);literal.extend(sequence.to_le_bytes());literal.push(count as u8);
    literal.extend(body);
    if literal.len()>MAX_FRAME_BYTES {return Err(bad("battle event frame size"));}
    lifecycle_wire::update(ARENA_UPDATE_TYPE,literal)
}
fn record(kind:u8,payload:&[u8],out:&mut Vec<u8>)->io::Result<()> {
    out.push(kind);out.push(u8::try_from(payload.len()).map_err(|_|bad("battle event size"))?);
    out.extend(payload);Ok(())
}
/// The reply that tells a prepared client this gateway speaks the channel.
pub fn hello_frame(sequence:u16)->io::Result<Vec<u8>> {
    let mut body=Vec::new();record(KIND_HELLO,&[VERSION],&mut body)?;with_header(sequence,1,&body)
}
pub fn frame(sequence:u16,events:&[Event])->io::Result<Vec<u8>> {
    let mut body=Vec::new();
    for event in events {
        match event {
            Event::HitReceived(hit)=>record(KIND_HIT_RECEIVED,&hit_payload(hit)?,&mut body)?,
            Event::Feed(feed)=>record(KIND_FEED,&feed_payload(feed)?,&mut body)?,
        }
    }
    with_header(sequence,events.len(),&body)
}

/// The version of a prepared client's setDevelopmentFeature record (0xa1:
/// STRING name, INT32 value); None: any other record keeps the old path.
pub fn hello(raw:&[u8])->Option<i32> {feature(raw,HELLO_FEATURE)}
/// The same record with the UI-03 name.
pub fn feed_hello(raw:&[u8])->Option<i32> {feature(raw,FEED_FEATURE)}
fn feature(raw:&[u8],wanted:&[u8])->Option<i32> {
    let args=raw.get(3..)?;
    let name=args.get(1..1+usize::from(*args.first()?))?;
    if name!=wanted {return None;}
    let value:[u8;4]=args.get(1+name.len()..)?.try_into().ok()?;
    Some(i32::from_le_bytes(value))
}

/// UI-03: how far this channel has read the journals. The native cursors are
/// not used: several move only on one publication path, and a feed fact must
/// not depend on it. Set once at the first pass after the hello, so a channel
/// opened late starts from "now" and never replays history.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct FeedCursors {pub impacts:usize,pub damage:usize,pub ram:usize,pub devices:usize,pub spots:usize,pub capture:u16,pub defence:u16}

/// Per-battle state of one prepared recipient.
#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Channel {
    sequence:u16,hello_due:bool,hellos:u8,
    window:Option<Instant>,frames:u8,
    feed:bool,pub cursors:Option<FeedCursors>,
    /// Events not delivered by the limits; reported, never hidden.
    pub dropped:u32,
}
impl Channel {
    pub fn new()->Self {Self{sequence:0,hello_due:false,hellos:0,window:None,frames:0,feed:false,cursors:None,dropped:0}}
    /// A repeated hello is answered again up to the bound.
    pub fn hello(&mut self) {if self.hellos<MAX_HELLOS {self.hellos+=1;self.hello_due=true;}}
    /// Asked by a client with the widget; repeats change nothing.
    pub fn open_feed(&mut self) {self.feed=true;}
    pub fn feed(&self)->bool {self.feed}
    pub fn take_hello(&mut self)->Option<u16> {
        if !std::mem::take(&mut self.hello_due) {return None;}
        Some(self.next_sequence())
    }
    fn next_sequence(&mut self)->u16 {let at=self.sequence;self.sequence=at.wrapping_add(1);at}
    /// The sequence of an admitted frame. A dropped frame takes no sequence:
    /// the loss is the server's `dropped` count, the stream stays contiguous.
    pub fn admit(&mut self,now:Instant,backlog:usize,events:usize)->Option<u16> {
        if self.window.is_none_or(|start|now.duration_since(start)>=Duration::from_secs(1)) {
            self.window=Some(now);self.frames=0;
        }
        if backlog>=MAX_OUTBOX_BACKLOG||self.frames>=MAX_FRAMES_PER_SECOND {
            self.dropped=self.dropped.saturating_add(events as u32);return None;
        }
        self.frames+=1;Some(self.next_sequence())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    fn hit(source:Source,criticals:Vec<Critical>)->Event {
        Event::HitReceived(HitReceived{shot:7,yaw:1.5,damage:120,blocked:None,verdict:Verdict::Pierced,friendly:false,fatal:false,source,criticals})
    }
    fn literal(raw:&[u8])->&[u8] {assert_eq!(&raw[..2],&[0x13,0x58]);assert_eq!(raw[3],ARENA_UPDATE_TYPE);assert_eq!(usize::from(raw[4]),raw.len()-5);&raw[5..]}
    #[test] fn ui02_frame_layout_is_versioned_and_network_ids_stay_in_the_codec() {
        let raw=frame(3,&[hit(Source::Visible(1),vec![Critical::Device{extra:5,destroyed:true},Critical::Fire])]).unwrap();
        let b=literal(&raw);
        assert_eq!(&b[..6],&[b'B',b'E',VERSION,3,0,1]);
        assert_eq!(&b[6..8],&[KIND_HIT_RECEIVED,23]);
        assert_eq!(&b[8..12],&7u32.to_le_bytes());assert_eq!(&b[12..16],&1.5f32.to_le_bytes());
        assert_eq!(&b[16..18],&120u16.to_le_bytes());assert_eq!(&b[18..20],&[0xff,0xff]);
        assert_eq!(b[20],Verdict::Pierced as u8);assert_eq!(b[21],0);
        assert_eq!(&b[22..26],&wire::vehicle_id(1).unwrap().to_le_bytes());
        assert_eq!(&b[26..],&[2,2,5,4,0]);
    }
    #[test] fn ui02_hidden_source_has_no_identity_bytes() {
        let raw=frame(0,&[hit(Source::Hidden,Vec::new())]).unwrap();let b=literal(&raw);
        assert_eq!(&b[22..26],&[0;4]);
    }
    #[test] fn ui02_frame_bounds_hold_for_the_largest_allowed_batch() {
        let big=hit(Source::Hidden,vec![Critical::Fire;MAX_CRITICALS]);
        let raw=frame(0,&vec![big.clone();MAX_EVENTS_PER_FRAME]).unwrap();
        assert!(raw.len()<=MAX_FRAME_BYTES+5);
        assert!(frame(0,&vec![big;MAX_EVENTS_PER_FRAME+1]).is_err());
        assert!(frame(0,&[hit(Source::Hidden,vec![Critical::Fire;MAX_CRITICALS+1])]).is_err());
    }
    #[test] fn ui02_hello_is_exact_and_other_features_keep_the_old_path() {
        let feature=|name:&[u8],tail:&[u8]|{let mut args=vec![name.len() as u8];args.extend(name);args.extend(tail);
            let mut raw=vec![0xa1];raw.extend((args.len() as u16).to_le_bytes());raw.extend(args);raw};
        assert_eq!(hello(&feature(HELLO_FEATURE,&1i32.to_le_bytes())),Some(1));
        assert_eq!(hello(&feature(HELLO_FEATURE,&9i32.to_le_bytes())),Some(9));
        assert_eq!(hello(&feature(b"server_marker",&1i32.to_le_bytes())),None);
        assert_eq!(hello(&feature(HELLO_FEATURE,&[1,0,0])),None);
        assert_eq!(hello(&feature(HELLO_FEATURE,&[1,0,0,0,0])),None);
        assert_eq!(hello(&[0xa1,0,0]),None);
        assert_eq!(hello(&[0xa1,5,0,200,1,2,3,4]),None);
    }
    #[test] fn ui03_feed_record_is_seven_bytes_and_absent_facts_are_marked() {
        let raw=frame(1,&[Event::Feed(FeedEvent{kind:FeedKind::ShotDamage,value:Some(320),vehicle:Some(1)}),
            Event::Feed(FeedEvent{kind:FeedKind::Spotted,value:None,vehicle:None})]).unwrap();
        let b=literal(&raw);
        assert_eq!(&b[6..8],&[KIND_FEED,7]);assert_eq!(b[8],1);
        assert_eq!(&b[9..11],&320u16.to_le_bytes());assert_eq!(&b[11..15],&wire::vehicle_id(1).unwrap().to_le_bytes());
        assert_eq!(&b[15..24],&[KIND_FEED,7,4,0xff,0xff,0,0,0,0]);
        assert!(frame(0,&[Event::Feed(FeedEvent{kind:FeedKind::Kill,value:Some(NO_VALUE),vehicle:None})]).is_err());
    }
    #[test] fn ui03_a_full_frame_of_feed_records_fits_one_argument() {
        let row=Event::Feed(FeedEvent{kind:FeedKind::Critical,value:Some(1),vehicle:Some(1)});
        assert!(frame(0,&vec![row;MAX_EVENTS_PER_FRAME]).unwrap().len()<=MAX_FRAME_BYTES+5);
    }
    #[test] fn ui03_feed_hello_is_its_own_feature_and_opens_nothing_alone() {
        let feature=|name:&[u8]|{let mut args=vec![name.len() as u8];args.extend(name);args.extend(1i32.to_le_bytes());
            let mut raw=vec![0xa1];raw.extend((args.len() as u16).to_le_bytes());raw.extend(args);raw};
        assert_eq!(feed_hello(&feature(FEED_FEATURE)),Some(1));assert_eq!(hello(&feature(FEED_FEATURE)),None);
        assert_eq!(feed_hello(&feature(HELLO_FEATURE)),None);
        let mut c=Channel::new();assert!(!c.feed());c.open_feed();c.open_feed();assert!(c.feed());
    }
    #[test] fn ui02_rate_and_backlog_limits_drop_and_count() {
        let now=Instant::now();let mut c=Channel::new();
        for at in 0..MAX_FRAMES_PER_SECOND {assert_eq!(c.admit(now,0,2),Some(u16::from(at)));}
        assert_eq!(c.admit(now,0,2),None);assert_eq!(c.dropped,2);
        assert_eq!(c.admit(now+Duration::from_secs(1),MAX_OUTBOX_BACKLOG,3),None);assert_eq!(c.dropped,5);
        assert_eq!(c.admit(now+Duration::from_secs(1),0,1),Some(u16::from(MAX_FRAMES_PER_SECOND)));
    }
    #[test] fn ui02_hello_replies_are_bounded() {
        let mut c=Channel::new();assert_eq!(c.take_hello(),None);
        for _ in 0..MAX_HELLOS {c.hello();assert!(c.take_hello().is_some());}
        c.hello();assert_eq!(c.take_hello(),None);
        let raw=hello_frame(4).unwrap();assert_eq!(literal(&raw),&[b'B',b'E',VERSION,4,0,1,KIND_HELLO,1,VERSION]);
    }
}
