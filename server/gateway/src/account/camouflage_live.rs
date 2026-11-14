//! Closed-loopback challenge proving a live, opted-in gateway to Domain.
//! The dedicated secret is not used by the bridge's Domain RPC client.
use std::{io::{self,Read,Write},net::{Ipv4Addr,SocketAddrV4,TcpListener,TcpStream},path::Path,
    sync::{Arc,atomic::{AtomicBool,AtomicU64,Ordering}},thread::{self,JoinHandle},time::{Duration,Instant}};
use serde_json::Value;
use super::domain_client::hmac_sha256;

fn invalid(message:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,message)}
pub(crate) struct Config { address:SocketAddrV4,secret:Vec<u8> }
impl Config {
    pub(crate) fn parse(value:&Value,local:&Path)->io::Result<Self>{
        let m=value.as_object().filter(|m|m.len()==3&&m.get("version")==Some(&Value::from(1))
            &&m.contains_key("bind")&&m.contains_key("secret_file")).ok_or_else(||invalid("camouflage_guard fields"))?;
        let address=super::local_address(m["bind"].as_str().ok_or_else(||invalid("camouflage guard bind"))?)?;
        let path=Path::new(m["secret_file"].as_str().ok_or_else(||invalid("camouflage guard secret path"))?).canonicalize()?;
        if !path.starts_with(local){return Err(invalid("camouflage guard secret escapes local root"));}
        let secret=super::bounded_file(&path,43)?;
        if secret.len()!=43||!secret.iter().all(|b|b.is_ascii_alphanumeric()||*b==b'_'||*b==b'-'){
            return Err(invalid("camouflage guard secret must be 43 base64url characters"));
        }
        Ok(Self{address,secret})
    }
    pub(crate) fn address(&self)->SocketAddrV4{self.address}
    pub(crate) fn secret_matches(&self,domain:&super::domain_client::Endpoint)->bool{domain.secret_matches(&self.secret)}
    pub(crate) fn is_secret(&self,value:&[u8])->bool {use subtle::ConstantTimeEq;self.secret.len()==value.len() && bool::from(self.secret.as_slice().ct_eq(value))}
    pub(crate) fn start(&self,generation:&str)->io::Result<Guard>{
        if generation.len()!=64||!generation.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)){
            return Err(invalid("camouflage guard generation"));
        }
        let listener=TcpListener::bind(self.address)?;listener.set_nonblocking(true)?;
        let stop=Arc::new(AtomicBool::new(false));let stopping=Arc::clone(&stop);
        let progress=Arc::new(AtomicU64::new(0));let advances=Arc::clone(&progress);let started=Instant::now();
        let secret=self.secret.clone();let generation=generation.to_owned();
        let worker=thread::Builder::new().name("camouflage-live-guard".into()).spawn(move||{
            while !stopping.load(Ordering::Acquire) {
                match listener.accept(){
                    Ok((mut stream,peer))=>{
                        if peer.ip()!=std::net::IpAddr::V4(Ipv4Addr::LOCALHOST){continue;}
                        let result=(||->io::Result<()>{
                            if !fresh(&advances,started) {
                                return Err(invalid("camouflage guard main loop stalled"));
                            }
                            // Winsock inherits the listener's nonblocking state on
                            // accept; SO_RCVTIMEO alone does not change it.
                            stream.set_nonblocking(false)?;
                            stream.set_write_timeout(Some(Duration::from_millis(300)))?;
                            let nonce=read_nonce(&mut stream)?;
                            if !fresh(&advances,started) {
                                return Err(invalid("camouflage guard main loop stalled"));
                            }
                            stream.write_all(&proof(&secret,&generation,&nonce))?;Ok(())
                        })();
                        if let Err(error)=result {eprintln!("camouflage guard request failed: {error}");}
                    },
                    Err(error) if error.kind()==io::ErrorKind::WouldBlock=>thread::sleep(Duration::from_millis(5)),
                    Err(error)=>{eprintln!("camouflage guard stopped: {error}");break;},
                }
            }
        })?;
        Ok(Guard{stop,progress,started,worker:Some(worker)})
    }
}
fn fresh(progress:&AtomicU64,started:Instant)->bool {
    let last=progress.load(Ordering::Acquire);
    let now=u64::try_from(started.elapsed().as_millis()).unwrap_or(u64::MAX).saturating_add(1);
    last!=0 && now.saturating_sub(last)<=500
}
fn read_nonce(stream:&mut TcpStream)->io::Result<[u8;32]> {
    let deadline=Instant::now()+Duration::from_millis(300);let mut nonce=[0u8;32];let mut used=0;
    while used<nonce.len() {
        let remaining=deadline.checked_duration_since(Instant::now()).filter(|d|!d.is_zero())
            .ok_or_else(||io::Error::new(io::ErrorKind::TimedOut,"camouflage guard nonce deadline"))?;
        stream.set_read_timeout(Some(remaining.max(Duration::from_millis(1))))?;
        match stream.read(&mut nonce[used..]) {
            Ok(0)=>return Err(io::Error::new(io::ErrorKind::UnexpectedEof,"camouflage guard incomplete nonce")),
            Ok(n)=>used+=n,
            Err(e) if matches!(e.kind(),io::ErrorKind::Interrupted|io::ErrorKind::WouldBlock|io::ErrorKind::TimedOut)=>{},
            Err(e)=>return Err(e),
        }
    }
    if Instant::now()>deadline{return Err(io::Error::new(io::ErrorKind::TimedOut,"camouflage guard nonce deadline"));}
    Ok(nonce)
}
fn proof(secret:&[u8],generation:&str,nonce:&[u8;32])->[u8;32]{
    let mut message=b"wot091-domain.v1:camouflage-live.v1\0".to_vec();message.extend(generation.as_bytes());message.extend(nonce);
    hmac_sha256(secret,&message)
}
pub(crate) struct Guard {stop:Arc<AtomicBool>,progress:Arc<AtomicU64>,started:Instant,worker:Option<JoinHandle<()>>}
impl Guard {pub(crate) fn pulse(&self){let ms=u64::try_from(self.started.elapsed().as_millis()).unwrap_or(u64::MAX).saturating_add(1);self.progress.store(ms,Ordering::Release);}}
impl Drop for Guard {
    fn drop(&mut self){self.stop.store(true,Ordering::Release);if let Some(worker)=self.worker.take(){
        if worker.join().is_err(){eprintln!("camouflage guard thread panicked");}
    }}
}

#[cfg(test)]
mod tests {
    use super::*;use std::net::TcpStream;
    fn assert_no_proof(stream:&mut TcpStream) {
        let mut byte=[0u8;1];match stream.read(&mut byte) {
            Ok(0)=>(),
            Err(e) if matches!(e.kind(),io::ErrorKind::ConnectionReset|io::ErrorKind::ConnectionAborted)=>(),
            result=>panic!("expected closed connection without proof, got {result:?}"),
        }
    }
    #[test] fn guard_waits_for_fragmented_nonce_but_rejects_incomplete_challenge() {
        let probe=TcpListener::bind((Ipv4Addr::LOCALHOST,0)).unwrap();let address=match probe.local_addr().unwrap(){std::net::SocketAddr::V4(a)=>a,_=>unreachable!()};drop(probe);
        let config=Config{address,secret:b"0123456789012345678901234567890123456789012".to_vec()};
        let generation="ab".repeat(32);let guard=config.start(&generation).unwrap();guard.pulse();
        let mut client=TcpStream::connect(address).unwrap();client.set_read_timeout(Some(Duration::from_secs(1))).unwrap();
        // On Windows a nonblocking accepted socket used to fail immediately,
        // before this intentionally delayed, split challenge could arrive.
        thread::sleep(Duration::from_millis(100));let nonce=[7u8;32];
        client.write_all(&nonce[..8]).unwrap();thread::sleep(Duration::from_millis(40));client.write_all(&nonce[8..]).unwrap();
        let mut answer=[0u8;32];client.read_exact(&mut answer).unwrap();assert_eq!(answer,proof(&config.secret,&generation,&nonce));
        guard.pulse();let mut incomplete=TcpStream::connect(address).unwrap();incomplete.set_read_timeout(Some(Duration::from_secs(1))).unwrap();
        incomplete.write_all(&nonce[..8]).unwrap();let start=Instant::now();assert_no_proof(&mut incomplete);
        assert!(start.elapsed()<Duration::from_secs(1),"incomplete challenge exceeds deadline");
        guard.pulse();let mut eof=TcpStream::connect(address).unwrap();eof.set_read_timeout(Some(Duration::from_secs(1))).unwrap();
        eof.write_all(&nonce[..8]).unwrap();eof.shutdown(std::net::Shutdown::Write).unwrap();assert_no_proof(&mut eof);
        guard.pulse();let mut fresh=TcpStream::connect(address).unwrap();fresh.set_read_timeout(Some(Duration::from_secs(1))).unwrap();
        fresh.write_all(&nonce).unwrap();fresh.read_exact(&mut answer).unwrap();assert_eq!(answer,proof(&config.secret,&generation,&nonce));
    }
    #[test] fn guard_refuses_challenge_if_main_loop_stalls_during_nonce() {
        let probe=TcpListener::bind((Ipv4Addr::LOCALHOST,0)).unwrap();let address=match probe.local_addr().unwrap(){std::net::SocketAddr::V4(a)=>a,_=>unreachable!()};drop(probe);
        let config=Config{address,secret:b"0123456789012345678901234567890123456789012".to_vec()};
        let generation="ab".repeat(32);let guard=config.start(&generation).unwrap();guard.pulse();
        thread::sleep(Duration::from_millis(360));
        let mut client=TcpStream::connect(address).unwrap();client.set_read_timeout(Some(Duration::from_millis(50))).unwrap();
        let nonce=[9u8;32];client.write_all(&nonce[..8]).unwrap();let mut byte=[0u8;1];
        let pending=client.read(&mut byte).unwrap_err();assert!(matches!(pending.kind(),io::ErrorKind::TimedOut|io::ErrorKind::WouldBlock));
        thread::sleep(Duration::from_millis(130));client.write_all(&nonce[8..]).unwrap();
        client.set_read_timeout(Some(Duration::from_secs(1))).unwrap();assert_no_proof(&mut client);
    }
    #[test] fn guard_total_nonce_deadline_is_not_refreshed_by_fragments() {
        let probe=TcpListener::bind((Ipv4Addr::LOCALHOST,0)).unwrap();let address=match probe.local_addr().unwrap(){std::net::SocketAddr::V4(a)=>a,_=>unreachable!()};drop(probe);
        let config=Config{address,secret:b"0123456789012345678901234567890123456789012".to_vec()};
        let generation="ab".repeat(32);let guard=config.start(&generation).unwrap();guard.pulse();
        let mut client=TcpStream::connect(address).unwrap();client.set_read_timeout(Some(Duration::from_secs(1))).unwrap();
        let nonce=[3u8;32];client.write_all(&nonce[..8]).unwrap();thread::sleep(Duration::from_millis(180));
        client.write_all(&nonce[8..16]).unwrap();let start=Instant::now();assert_no_proof(&mut client);
        assert!(start.elapsed()<Duration::from_millis(250),"second fragment must not reset the 300ms deadline");
    }
    #[test] fn guard_signs_only_live_fresh_challenges_and_stops_with_owner(){
        let probe=TcpListener::bind((Ipv4Addr::LOCALHOST,0)).unwrap();let address=match probe.local_addr().unwrap(){std::net::SocketAddr::V4(a)=>a,_=>unreachable!()};drop(probe);
        let config=Config{address,secret:b"0123456789012345678901234567890123456789012".to_vec()};
        let generation="ab".repeat(32);let guard=config.start(&generation).unwrap();guard.pulse();
        for nonce in [[1u8;32],[2u8;32]] {
            let mut stream=TcpStream::connect(address).unwrap();stream.set_read_timeout(Some(Duration::from_secs(1))).unwrap();
            stream.write_all(&nonce).unwrap();let mut got=[0u8;32];stream.read_exact(&mut got).unwrap();
            assert_eq!(got,proof(&config.secret,&generation,&nonce));
            assert_ne!(got,proof(&config.secret,&"cd".repeat(32),&nonce));
        }
        drop(guard);assert!(TcpStream::connect_timeout(&address.into(),Duration::from_millis(100)).is_err());
    }
}
