//! Closed test-lab visibility diagnostics: bounded per-operator transport.
//! Never derives LOS or accepts client positions. Publication is opt-in and
//! caller must bind the channel to an authenticated allowlisted account.
use std::{io,time::{Duration,Instant}};
use serde_json::{json,Value};
use rsa::rand_core::{OsRng,RngCore};
use subtle::ConstantTimeEq;
use sha2::{Digest,Sha256};
use super::lifecycle_wire;

pub const FEATURE:&[u8]=b"sr_visibility_debug_v1";
pub const ARENA_UPDATE_TYPE:u8=201;
pub const MAX_BODY:usize=8192;
const MAX_CHUNK:usize=145;
const MAX_PARTS:usize=57;
const MAX_QUEUE:usize=16;
const PARTIAL_TIMEOUT:Duration=Duration::from_secs(12);
const FRAME_INTERVAL:Duration=Duration::from_millis(100);
fn bad()->io::Error {io::Error::new(io::ErrorKind::InvalidData,"visibility debug bound")}
fn run_token(run:&str)->io::Result<[u8;16]> {
    let b=run.as_bytes();if b.len()!=36{return Err(bad());}
    let mut out=[0;16];let mut n=0;let mut high=None;
    for (i,&v) in b.iter().enumerate() {
        if [8,13,18,23].contains(&i) {if v!=b'-'{return Err(bad());}continue;}
        let x=match v {b'0'..=b'9'=>v-b'0',b'a'..=b'f'=>v-b'a'+10,_=>return Err(bad())};
        if let Some(h)=high.take(){out[n]=(h<<4)|x;n+=1;}else{high=Some(x);}
    }
    if n!=16||high.is_some(){return Err(bad());}Ok(out)
}

/// Decode only a bounded slot selection; no client coordinates or results.
pub fn hello(raw:&[u8])->Option<(usize,usize)> {
    let args=raw.get(3..)?;
    let name=args.get(1..1+usize::from(*args.first()?))?;
    if name!=FEATURE {return None;}
    let value=i32::from_le_bytes(args.get(1+name.len()..)?.try_into().ok()?);
    if value<0 || value & !0xffff != 0 {return None;}
    let a=(value>>8) as usize;let b=(value&255) as usize;
    if a>=6||b>=6||a==b {return None;}
    Some((a,b))
}

const AUTH_FEATURE:&[u8]=b"sr_visibility_debug_auth_v1:";
#[derive(Clone)]
pub struct Challenge { run:[u8;16],battle:u64,session:u32,nonce:[u8;32],pair:(usize,usize),issued:Instant }
impl Challenge {
    pub fn new(run:&str,battle:u64,session:u32,pair:(usize,usize),now:Instant)->io::Result<(Self,Vec<u8>)> {
        let mut nonce=[0;32];OsRng.fill_bytes(&mut nonce);let token=run_token(run)?;
        let mut frame=b"VC".to_vec();frame.push(1);frame.extend(battle.to_le_bytes());frame.extend(token);frame.extend(session.to_le_bytes());frame.extend(nonce);
        Ok((Self{run:token,battle,session,nonce,pair,issued:now},lifecycle_wire::update(ARENA_UPDATE_TYPE,frame)?))
    }
    pub fn verify(&self,raw:&[u8],grant:&[u8],account:&str,run:&str,battle:u64,session:u32,now:Instant)->bool {
        if now.saturating_duration_since(self.issued)>=Duration::from_secs(30) || self.battle!=battle || self.session!=session || run_token(run).ok()!=Some(self.run) {return false;}
        let Some(args)=raw.get(3..) else{return false;};let Some(&size)=args.first() else{return false;};
        let Some(name)=args.get(1..1+size as usize) else{return false;};
        let Some(hex)=name.strip_prefix(AUTH_FEATURE) else{return false;};
        if hex.len()!=64{return false;}let Some(value)=args.get(1+name.len()..).and_then(|v|<&[u8;4]>::try_from(v).ok()).map(|v|i32::from_le_bytes(*v)) else{return false;};
        if value!=((self.pair.0 as i32)<<8|self.pair.1 as i32){return false;}
        let mut supplied=[0u8;32];
        for (i,pair) in hex.chunks_exact(2).enumerate(){let digit=|b|match b{b'0'..=b'9'=>Some(b-b'0'),b'a'..=b'f'=>Some(b-b'a'+10),_=>None};
            let Some(a)=digit(pair[0]) else{return false;};let Some(b)=digit(pair[1]) else{return false;};supplied[i]=a<<4|b;}
        let mut msg=b"wot091:visibility-operator:v1\0".to_vec();msg.extend(self.run);msg.extend(self.battle.to_le_bytes());msg.extend(self.session.to_le_bytes());msg.extend(self.nonce);msg.extend(account.as_bytes());
        let expected=crate::identity091::domain_client::hmac_sha256(grant,&msg);
        bool::from(expected.ct_eq(&supplied))
    }
    #[cfg(test)]
    pub fn test_response(&self,grant:&[u8],account:&str)->Vec<u8> {
        let mut msg=b"wot091:visibility-operator:v1\0".to_vec();msg.extend(self.run);msg.extend(self.battle.to_le_bytes());msg.extend(self.session.to_le_bytes());msg.extend(self.nonce);msg.extend(account.as_bytes());
        let mac=crate::identity091::domain_client::hmac_sha256(grant,&msg);
        let name=[AUTH_FEATURE,mac.iter().map(|b|format!("{b:02x}")).collect::<String>().as_bytes()].concat();
        let mut args=vec![name.len() as u8];args.extend(name);args.extend(((self.pair.0 as i32)<<8|self.pair.1 as i32).to_le_bytes());
        let mut raw=vec![0xa1];raw.extend((args.len() as u16).to_le_bytes());raw.extend(args);raw
    }
    /// Derive a fresh public epoch from the one-time authentication challenge.
    pub fn epoch(&self)->[u8;16] {let digest=Sha256::digest(self.nonce);let mut epoch=[0;16];epoch.copy_from_slice(&digest[..16]);epoch}
    pub fn pair(&self)->(usize,usize){self.pair}
    pub fn expired(&self,now:Instant)->bool {now.saturating_duration_since(self.issued)>=Duration::from_secs(30)}
}
pub fn is_auth(raw:&[u8])->bool {
    raw.get(3..).and_then(|args|args.first().and_then(|&n|args.get(1..1+n as usize))).is_some_and(|name|name.starts_with(AUTH_FEATURE))
}

/// Atomically select a single pair from the committed World diagnostic value.
/// No geometry is queried again. Missing pairs are normal (inactive observer).
pub fn snapshot(world:&super::model::World,run:&str,observer:usize,target:usize)->io::Result<Option<Vec<u8>>> {
    if observer>=6||target>=6||observer==target{return Err(bad());}
    let _=run_token(run)?;
    let Some(source)=world.spotting_diagnostics() else{return Ok(None);};
    encode_snapshot(source,run,world.id,observer,target)
}
fn encode_snapshot(source:&Value,run:&str,battle:u64,observer:usize,target:usize)->io::Result<Option<Vec<u8>>> {
    if source.get("schema").and_then(Value::as_str)!=Some("content0-s5a-spotting-trace.v1"){return Err(bad());}
    let rows=source.get("pairs").and_then(Value::as_array).ok_or_else(bad)?;
    let pubs=source.get("publications").and_then(Value::as_array).ok_or_else(bad)?;
    let actors=source.get("actors").and_then(Value::as_array).ok_or_else(bad)?;
    if rows.len()>30||pubs.len()>30||actors.len()>6{return Err(bad());}
    let direct=rows.iter().filter_map(|p|if p["direct"].as_bool()==Some(true) {
        Some(json!([p["observer"],p["target"]]))
    }else{None}).collect::<Vec<_>>();
    let mut pair=rows.iter().filter(|p|p["observer"].as_u64()==Some(observer as u64)&&p["target"].as_u64()==Some(target as u64));
    let Some(pair_row)=pair.next() else{return Ok(None);};
    if pair.next().is_some(){return Err(bad());}
    let mut pubrow=pubs.iter().filter(|p|p["recipient"].as_u64()==Some(observer as u64)&&p["target"].as_u64()==Some(target as u64));
    let Some(publication)=pubrow.next() else{return Ok(None);};
    if pubrow.next().is_some(){return Err(bad());}
    let body=serde_json::to_vec(&json!({"schema":"content0-s5a-operator.v1","run":run,"battle":battle.to_string(),
        "tick":source.get("scan_tick").and_then(Value::as_u64).ok_or_else(bad)?,"scan_ms":source["scan_ms"],"next_scan_ms":source["next_scan_ms"],"pair":pair_row,"publication":publication,
        "map":{"asset":source.get("map_asset").and_then(Value::as_str).ok_or_else(bad)?,"actors":actors,"direct":direct,"publications":pubs}}))
        .map_err(|_|bad())?;
    if body.is_empty()||body.len()>MAX_BODY{return Err(bad());}
    Ok(Some(body))
}

fn fragments(body:&[u8],battle:u64,run:&str,epoch:[u8;16],sequence:u32,grant:&[u8])->io::Result<Vec<Vec<u8>>> {
    if body.is_empty()||body.len()>MAX_BODY||grant.len()!=43{return Err(bad());}
    let token=run_token(run)?;let count=body.len().div_ceil(MAX_CHUNK);
    if count==0||count>MAX_PARTS{return Err(bad());}
    body.chunks(MAX_CHUNK).enumerate().map(|(index,chunk)| {
        let mut frame=b"VD".to_vec();frame.push(3);frame.extend(battle.to_le_bytes());
        frame.extend(token);frame.extend(epoch);frame.extend(sequence.to_le_bytes());
        frame.push(index as u8);frame.push(count as u8);
        let mut authenticated=b"wot091:visibility-fragment:v3\0".to_vec();authenticated.extend(&frame);authenticated.extend(chunk);
        let tag=crate::identity091::domain_client::hmac_sha256(grant,&authenticated);
        frame.extend(&tag[..16]);frame.extend(chunk);Ok(frame)
    }).collect()
}

#[derive(Clone,Debug)]
pub struct Channel {epoch:[u8;16],pair:Option<(usize,usize)>,sequence:u32,frames:Vec<Vec<u8>>,next:usize,last:Option<Instant>,scan:Option<u64>,battle:Option<u64>,last_frame:Option<Instant>}
impl Channel {
    pub fn new(epoch:[u8;16])->Self {Self{epoch,pair:None,sequence:0,frames:Vec::new(),next:0,last:None,scan:None,battle:None,last_frame:None}}
    pub fn select(&mut self,pair:(usize,usize)) {if self.pair!=Some(pair){self.pair=Some(pair);self.frames.clear();self.next=0;self.scan=None;}}
    pub fn pair(&self)->Option<(usize,usize)>{self.pair}
    /// Queue at most one fully bounded scan every two seconds. Existing partial
    /// data are never mixed with a new scan. An overloaded outbox gets no data.
    pub fn publish(&mut self,world:&super::model::World,run:&str,grant:&[u8],now:Instant,backlog:usize)->io::Result<Option<Vec<u8>>> {
        if self.battle.is_some_and(|battle|battle!=world.id) {
            // Old queued fragments never cross an arena boundary. A new arena
            // requires a fresh client hello and a new selection.
            self.pair=None;self.sequence=0;self.frames.clear();self.next=0;
            self.last=None;self.scan=None;self.battle=None;self.last_frame=None;return Ok(None);
        }
        let Some((observer,target))=self.pair else{return Ok(None);};
        self.battle=Some(world.id);
        if self.next<self.frames.len() && self.last.is_some_and(|at|now.saturating_duration_since(at)>=PARTIAL_TIMEOUT) {
            // Drop stale unsent pieces; never hold a partial frame group forever.
            self.frames.clear();self.next=0;
        }
        if backlog>=MAX_QUEUE{return Ok(None);}
        if self.last_frame.is_some_and(|at|now.saturating_duration_since(at)<FRAME_INTERVAL){return Ok(None);}
        if self.next==self.frames.len() {
            self.frames.clear();self.next=0;
            if self.last.is_some_and(|at|now.saturating_duration_since(at)<Duration::from_secs(2)){return Ok(None);}
            let scan=world.spotting_diagnostics().and_then(|v|v["scan_ms"].as_u64());
            if scan.is_none()||scan==self.scan{return Ok(None);}
            let Some(body)=snapshot(world,run,observer,target)? else{return Ok(None);};
            self.sequence=self.sequence.checked_add(1).ok_or_else(bad)?;
            for frame in fragments(&body,world.id,run,self.epoch,self.sequence,grant)? {
                self.frames.push(lifecycle_wire::update(ARENA_UPDATE_TYPE,frame)?);
            }
            println!("VISIBILITY_DEBUG_SNAPSHOT {}",String::from_utf8_lossy(&body));
            self.scan=scan;self.last=Some(now);
        }
        let out=self.frames.get(self.next).cloned();if out.is_some(){self.next+=1;self.last_frame=Some(now);} Ok(out)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn run_token_requires_canonical_uuid() {
        assert_eq!(run_token("788fa1bf-8a21-4bdb-84de-a63310e390a3").unwrap(),
            [0x78,0x8f,0xa1,0xbf,0x8a,0x21,0x4b,0xdb,0x84,0xde,0xa6,0x33,0x10,0xe3,0x90,0xa3]);
        for invalid in ["788FA1BF-8a21-4bdb-84de-a63310e390a3","788fa1bf_8a21-4bdb-84de-a63310e390a3","x"] {assert!(run_token(invalid).is_err());}
    }
    #[test] fn operator_grant_binds_account_run_battle_and_session() {
        let now=Instant::now();let run="788fa1bf-8a21-4bdb-84de-a63310e390a3";let account=run;
        let grant=b"0123456789012345678901234567890123456789012";
        let (challenge,_)=Challenge::new(run,717,9,(0,1),now).unwrap();
        let reply=challenge.test_response(grant,account);
        assert!(challenge.verify(&reply,grant,account,run,717,9,now));
        assert!(!challenge.verify(&reply,b"wrong",account,run,717,9,now));
        assert!(!challenge.verify(&reply,grant,"888fa1bf-8a21-4bdb-84de-a63310e390a3",run,717,9,now));
        assert!(!challenge.verify(&reply,grant,account,"788fa1bf-8a21-4bdb-84de-a63310e390a4",717,9,now));
        assert!(!challenge.verify(&reply,grant,account,run,718,9,now));
        assert!(!challenge.verify(&reply,grant,account,run,717,10,now));
        assert!(!challenge.verify(&reply,grant,account,run,717,9,now+Duration::from_secs(30)));
        let known=Challenge{run:run_token(run).unwrap(),battle:9_007_199_254_740_993,session:17,nonce:std::array::from_fn(|i|i as u8),pair:(0,1),issued:now};
        let vector=known.test_response(&[b'x';43],"6dfe50ca-84c6-4ad4-9ffa-19f22f92a563");
        assert!(vector.windows(64).any(|v|v==b"c78baa188b7a733cf23fb6a3fd4839eb9361d40b1156099aee723366fbf9cb29"));
    }
    #[test] fn reauthorization_epochs_bind_each_fragment_and_prevent_pair_replay() {
        let now=Instant::now();let run="788fa1bf-8a21-4bdb-84de-a63310e390a3";
        let challenge=|nonce:u8,pair|Challenge{run:run_token(run).unwrap(),battle:717,session:9,nonce:[nonce;32],pair,issued:now};
        let first=challenge(1,(0,1));let middle=challenge(2,(0,2));let last=challenge(3,(0,1));
        assert_ne!(first.epoch(),middle.epoch());assert_ne!(first.epoch(),last.epoch());
        let grant=[b'x';43];
        let a=fragments(b"pair A",717,run,first.epoch(),1,&grant).unwrap();
        let b=fragments(b"pair B",717,run,middle.epoch(),1,&grant).unwrap();
        let anew=fragments(b"pair A",717,run,last.epoch(),1,&grant).unwrap();
        assert_eq!(&a[0][43..47],&anew[0][43..47],"recreated channel may reuse sequence");
        assert_ne!(&a[0][27..43],&anew[0][27..43],"old A epoch cannot match new A");
        assert_ne!(&b[0][27..43],&anew[0][27..43]);
        let known=Challenge{run:run_token(run).unwrap(),battle:717,session:9,nonce:std::array::from_fn(|i|i as u8),pair:(0,1),issued:now};
        assert_eq!(known.epoch(),[0x63,0x0d,0xcd,0x29,0x66,0xc4,0x33,0x66,0x91,0x12,0x54,0x48,0xbb,0xb2,0x5b,0x4f]);
        let vector=fragments(b"pair A",717,run,known.epoch(),1,&grant).unwrap();
        assert_eq!(&vector[0][49..65],&[0x1e,0xc3,0xc4,0xf0,0x5c,0xb0,0x1e,0x23,0x94,0x70,0x40,0x69,0xd2,0xb7,0x13,0x63]);
        let mut forged=a[0].clone();forged[27..43].copy_from_slice(&last.epoch());
        let mut input=b"wot091:visibility-fragment:v3\0".to_vec();input.extend(&forged[..49]);input.extend(&forged[65..]);
        let computed=crate::identity091::domain_client::hmac_sha256(&grant,&input);
        assert_ne!(&computed[..16],&forged[49..65],"replacing the old epoch invalidates the old tag");
    }
    #[test] fn all_thirty_legal_pairs_and_invalid_selections() {
        let frame=|value:i32| {let mut args=vec![0xa1,0,0,FEATURE.len() as u8];args.extend(FEATURE);args.extend(value.to_le_bytes());args};
        for a in 0..6 {for b in 0..6 {let parsed=hello(&frame((a<<8)|b));assert_eq!(parsed,if a==b{None}else{Some((a as usize,b as usize))});}}
        for value in [-1,6,6<<8,65536,0x0106]{assert_eq!(hello(&frame(value)),None);}
    }
    #[test] fn bounded_max_snapshot_uses_scan_tick_not_current_world() {
        let rays=(0..14).map(|i|json!({"observer_point":i/7,"target_point":i%7,
            "start":[-565.3218383789062,9999.123046875,-9999.123046875],
            "end":[565.3218383789062,9999.123046875,-9999.123046875],
            "hit_point":[0.32183837890625,9999.123046875,-9999.123046875],
            "result":"object","foliage":null,"threshold_m":null})).collect::<Vec<_>>();
        let mut source=json!({"schema":"content0-s5a-spotting-trace.v1","scan_tick":1001,"scan_ms":100,"next_scan_ms":200,
            "map_asset":"02_malinovka","actors":(0..6).map(|slot|json!({"slot":slot,"vehicle":"ussr:T-50","team":if slot<3 {1}else{2},"position":[-565.3218383789062,9999.123046875,-9999.123046875]})).collect::<Vec<_>>(),
            "pairs":[{"observer":0,"target":1,"rays":rays,"direct":true}],
            "publications":[{"recipient":0,"target":1,"visible":false,"source":"hidden","spotter":null}]});
        for observer in 0..6 {for target in 0..6 {if observer!=target && (observer,target)!=(0,1) {
            source["pairs"].as_array_mut().unwrap().push(json!({"observer":observer,"target":target,"direct":true}));
            source["publications"].as_array_mut().unwrap().push(json!({"recipient":observer,"target":target,"visible":true,"source":"team_retained","spotter":5}));
        }}}
        let bytes=encode_snapshot(&source,"788fa1bf-8a21-4bdb-84de-a63310e390a3",123,0,1).unwrap().unwrap();
        assert!(bytes.len()>4096 && bytes.len()<=MAX_BODY,"{}",bytes.len());
        let value:Value=serde_json::from_slice(&bytes).unwrap();
        assert_eq!(value["tick"],1001);
        assert_eq!(value["map"]["actors"].as_array().unwrap().len(),6);
        assert_eq!(value["map"]["direct"].as_array().unwrap().len(),30);
        assert_eq!(value["map"]["publications"].as_array().unwrap().len(),30);
        let run="788fa1bf-8a21-4bdb-84de-a63310e390a3";
        let epoch=[7u8;16];let grant=[b'x';43];let frames=fragments(&bytes,123,run,epoch,1,&grant).unwrap();assert!(frames.len()<=MAX_PARTS);
        let mut rebuilt=Vec::new();
        for (i,frame) in frames.iter().enumerate(){
            assert!(frame.len()<=210);assert_eq!(&frame[..3],b"VD\x03");
            assert_eq!(&frame[3..11],&123u64.to_le_bytes());assert_eq!(&frame[11..27],&run_token(run).unwrap());
            assert_eq!(&frame[27..43],&epoch);
            assert_eq!(&frame[43..47],&1u32.to_le_bytes());assert_eq!(frame[47] as usize,i);assert_eq!(frame[48] as usize,frames.len());
            let mut authenticated=b"wot091:visibility-fragment:v3\0".to_vec();authenticated.extend(&frame[..49]);authenticated.extend(&frame[65..]);
            let expected=crate::identity091::domain_client::hmac_sha256(&grant,&authenticated);
            assert_eq!(&frame[49..65],&expected[..16]);rebuilt.extend_from_slice(&frame[65..]);
        }
        assert_eq!(rebuilt,bytes);
        let other=fragments(&bytes,124,run,epoch,1,&grant).unwrap();assert_ne!(&frames[0][3..11],&other[0][3..11]);
        let other_run=fragments(&bytes,123,"788fa1bf-8a21-4bdb-84de-a63310e390a4",epoch,1,&grant).unwrap();
        assert_ne!(&frames[0][11..27],&other_run[0][11..27]);
        let full=fragments(&vec![0;MAX_BODY],123,run,epoch,1,&grant).unwrap();assert_eq!(full.len(),MAX_PARTS);
        // At one part per 100 ms, the last part arrives within 5.6 seconds;
        // sender drops stalled groups at 12s, before the client's 15s limit.
        let delivered_after=Duration::from_millis(100 * (full.len() as u64 - 1));
        assert!(delivered_after<PARTIAL_TIMEOUT && PARTIAL_TIMEOUT<Duration::from_secs(15));
        assert!(fragments(&vec![0;MAX_BODY+1],123,run,epoch,1,&grant).is_err());
        let mut oversized=source;oversized["pairs"][0]["x"]=Value::String("x".repeat(MAX_BODY));
        assert!(encode_snapshot(&oversized,"788fa1bf-8a21-4bdb-84de-a63310e390a3",123,0,1).is_err());
    }
}
