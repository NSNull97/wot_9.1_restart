//! Closed-loopback challenge proving a live, opted-in gateway to Domain.
//! The dedicated secret is not used by the bridge's Domain RPC client.
use std::{io::{self,Read,Write},net::{Ipv4Addr,SocketAddrV4,TcpListener},path::Path,
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
                            let last=advances.load(Ordering::Acquire);
                            let now=u64::try_from(started.elapsed().as_millis()).unwrap_or(u64::MAX).saturating_add(1);
                            if last==0 || now.saturating_sub(last)>500 {
                                return Err(invalid("camouflage guard main loop stalled"));
                            }
                            stream.set_read_timeout(Some(Duration::from_millis(300)))?;
                            stream.set_write_timeout(Some(Duration::from_millis(300)))?;
                            let mut nonce=[0u8;32];stream.read_exact(&mut nonce)?;
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
