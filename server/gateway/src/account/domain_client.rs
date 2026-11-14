//! DOM-01 loopback client of the Domain/Account service (`server/domain/protocol.py`, wot091-domain.v1).
//! Same request bytes, reply budgets and deadline as the bridge HTTP path it replaces;
//! only the fixed hangar/battle/late-result writer paths below are routed. No fallback to HTTP.
use std::{fs, io::{self,Read,Write}, net::{SocketAddrV4,TcpStream}, path::Path, time::{Duration,Instant}};
use serde_json::Value;
use sha2::{Digest,Sha256};
use rsa::rand_core::{OsRng,RngCore};
use subtle::ConstantTimeEq;

pub(crate) const SCHEMA:&str="wot091-domain.v1";
// RES-30: one escaped 7..30-row result journal plus header (was 72KiB).
const MAX_FRAME:usize=crate::gateway091::shared::lifecycle_wire::MAX_RESULT_REQUEST+8192;
const MAX_HEADER:usize=1024;

fn invalid(message:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,message)}

/// Bridge paths whose writer is the Domain; login/profile (identity) and room selection stay on the bridge.
pub(crate) fn operation(path:&str)->Option<&'static str>{
    Some(match path{
        "/internal/native/ammo"=>"service","/internal/native/crew"=>"recruit","/internal/native/crew-transfer"=>"transfer",
        "/internal/native/crew-recruit-barracks"=>"recruit-barracks","/internal/native/crew-dismiss"=>"dismiss",
        "/internal/native/crew-learn"=>"learn","/internal/native/research"=>"research","/internal/native/battle"=>"battle",
        "/internal/native/battle-results"=>"results","/internal/native/late-result-append"=>"late-append",
        "/internal/native/late-result-pending"=>"late-pending","/internal/native/int-settings"=>"int-settings",_=>return None,
    })
}

pub(crate) fn hmac_sha256(key:&[u8],message:&[u8])->[u8;32]{
    let mut block=[0u8;64];
    if key.len()>64{block[..32].copy_from_slice(&Sha256::digest(key));}else{block[..key.len()].copy_from_slice(key);}
    let pad=|byte:u8|block.map(|b|b^byte);
    let inner=Sha256::new().chain_update(pad(0x36)).chain_update(message).finalize();
    Sha256::new().chain_update(pad(0x5c)).chain_update(inner).finalize().into()
}
fn hex(bytes:&[u8])->String{bytes.iter().map(|b|format!("{b:02x}")).collect()}
fn hex64(s:&str)->bool{s.len()==64&&s.bytes().all(|c|c.is_ascii_digit()||(b'a'..=b'f').contains(&c))}
fn part(out:&mut Vec<u8>,value:&str){out.extend((value.len() as u32).to_be_bytes());out.extend(value.as_bytes());}
fn optional(out:&mut Vec<u8>,value:Option<&str>){match value{None=>out.push(0),Some(s)=>{out.push(1);part(out,s);}}}
fn request_proof(secret:&[u8],hello:&str,nonce:&str,generation:&str,header:&Value,body:&[u8])->io::Result<String>{
    let id=header["id"].as_u64().and_then(|x|u32::try_from(x).ok()).ok_or_else(||invalid("domain capability id"))?;
    let op=header["op"].as_str().ok_or_else(||invalid("domain capability operation"))?;
    let scalar=|key:&str|match header.get(key){Some(Value::Null)=>Ok(None),Some(Value::String(s))=>Ok(Some(s.as_str())),_=>Err(invalid("domain capability scalar"))};
    let mut bytes=b"wot091-domain.v1:camouflage.v1:request\0".to_vec();
    part(&mut bytes,hello);part(&mut bytes,nonce);part(&mut bytes,generation);bytes.extend(id.to_be_bytes());part(&mut bytes,op);
    optional(&mut bytes,scalar("account_id")?);optional(&mut bytes,scalar("key")?);bytes.extend(Sha256::digest(body));
    Ok(hex(&hmac_sha256(secret,&bytes)))
}
fn response_proof(secret:&[u8],request:&str,generation:&str,status:u16,body:&[u8])->String{
    let mut bytes=b"wot091-domain.v1:camouflage.v1:response\0".to_vec();
    part(&mut bytes,request);part(&mut bytes,generation);bytes.extend(status.to_be_bytes());bytes.extend(Sha256::digest(body));
    hex(&hmac_sha256(secret,&bytes))
}

pub(crate) struct Endpoint{address:SocketAddrV4,secret:Vec<u8>,camouflage_generation:Option<String>}
impl Endpoint{
    /// `{"version":1,"endpoint":"127.0.0.1:N","secret_file":<inside local_root>}`.
    pub(crate) fn parse(value:&Value,local_root:&Path)->io::Result<Self>{
        let map=value.as_object().filter(|m|m.len()==3&&["version","endpoint","secret_file"].iter().all(|k|m.contains_key(*k)))
            .ok_or_else(||invalid("domain_service must be {version,endpoint,secret_file}"))?;
        if map["version"].as_u64()!=Some(1){return Err(invalid("domain_service version must be 1"));}
        let address=super::local_address(map["endpoint"].as_str().ok_or_else(||invalid("domain endpoint string"))?)?;
        let path=Path::new(map["secret_file"].as_str().ok_or_else(||invalid("domain secret path string"))?).canonicalize()?;
        if !path.starts_with(local_root){return Err(invalid("domain secret file escapes local root"));}
        let secret=super::bounded_file(&path,43)?;
        if secret.len()!=43||!secret.iter().all(|b|b.is_ascii_alphanumeric()||*b==b'_'||*b==b'-'){return Err(invalid("domain secret must be exactly 43 base64url characters"));}
        Ok(Self{address,secret,camouflage_generation:None})
    }
    pub(crate) fn address(&self)->SocketAddrV4{self.address}
    pub(crate) fn secret_matches(&self,other:&[u8])->bool{bool::from(self.secret.as_slice().ct_eq(other))}
    pub(crate) fn camouflage_generation(&self)->Option<&str>{self.camouflage_generation.as_deref()}

    /// Bind one immutable Domain process generation before accepting players.
    /// Rebinding after a restart is deliberately not automatic: stale calls
    /// are refused by Domain before they can mutate an account.
    pub(crate) fn bind_camouflage(&mut self)->io::Result<()> {
        if self.camouflage_generation.is_some(){return Err(invalid("domain camouflage already bound"));}
        let request=serde_json::json!({"schema":SCHEMA,"id":1,"op":"describe","account_id":null,"key":null});
        let (status,body)=self.exchange(&request,&[],Duration::from_secs(5),32*1024,Some("-"))?;
        if status!=200 {return Err(invalid("domain camouflage describe refused"));}
        let super::Bounded::<16>(reply)=serde_json::from_slice(&body).map_err(|_|invalid("domain camouflage describe JSON"))?;
        if reply.get("schema").and_then(Value::as_str)!=Some(SCHEMA) || reply.get("version").and_then(Value::as_u64)!=Some(1)
            || reply.get("camouflage_v1").and_then(Value::as_bool)!=Some(true) {return Err(invalid("domain camouflage capability mismatch"));}
        let generation=reply.get("camouflage_generation").and_then(Value::as_str)
            .filter(|s|hex64(s))
            .ok_or_else(||invalid("domain camouflage generation"))?;
        self.camouflage_generation=Some(generation.to_owned());Ok(())
    }

    /// One authenticated connection per call. Returns the Domain status and raw reply body,
    /// exactly as the HTTP path returns (status, body); callers keep their own status checks.
    pub(crate) fn call(&self,op:&str,body:&[u8],timeout:Duration,max_body:usize)->io::Result<(u16,Vec<u8>)>{
        let request:Value=serde_json::from_slice(body).map_err(|_|invalid("domain request JSON"))?;
        let account=request.get("account_id").and_then(Value::as_str).ok_or_else(||invalid("domain request account"))?;
        let key=request.get("command_key").and_then(Value::as_str);
        let header=serde_json::json!({"schema":SCHEMA,"id":1,"op":op,"account_id":account,"key":key});
        self.exchange(&header,body,timeout,max_body,self.camouflage_generation.as_deref())
    }

    fn exchange(&self,header:&Value,body:&[u8],timeout:Duration,max_body:usize,generation:Option<&str>)->io::Result<(u16,Vec<u8>)>{
        let deadline=Instant::now()+timeout;
        let mut stream=TcpStream::connect_timeout(&self.address.into(),Duration::from_millis(500))?;
        stream.set_nodelay(true)?;stream.set_write_timeout(Some(Duration::from_secs(2)))?;
        let (challenge,_)=read_frame(&mut stream,deadline,0)?;
        let nonce=challenge.get("nonce").and_then(Value::as_str).filter(|n|n.len()==64&&n.bytes().all(|b|b.is_ascii_hexdigit()&&!b.is_ascii_uppercase()))
            .ok_or_else(||invalid("domain challenge"))?;
        let proof=hex(&hmac_sha256(&self.secret,format!("{SCHEMA}:{nonce}").as_bytes()));
        write_frame(&mut stream,&serde_json::json!({"schema":SCHEMA,"op":"hello","proof":proof}),&[])?;
        let (ready,_)=read_frame(&mut stream,deadline,0)?;
        if ready.get("status").and_then(Value::as_u64)!=Some(200){return Err(invalid("domain authentication refused"));}
        let mut header=header.clone();
        let request=if let Some(generation)=generation {
            let mut random=[0u8;32];OsRng.fill_bytes(&mut random);let client_nonce=hex(&random);
            let proof=request_proof(&self.secret,nonce,&client_nonce,generation,&header,body)?;
            header["camouflage_nonce"]=client_nonce.into();header["camouflage_generation"]=generation.into();
            header["camouflage_request_proof"]=proof.clone().into();Some(proof)
        }else{None};
        write_frame(&mut stream,&header,body)?;
        let (header,reply)=read_frame(&mut stream,deadline,max_body)?;
        if header.get("id").and_then(Value::as_u64)!=Some(1){return Err(invalid("domain reply identity"));}
        let status=header.get("status").and_then(Value::as_u64).and_then(|s|u16::try_from(s).ok()).ok_or_else(||invalid("domain reply status"))?;
        if let Some(request)=request {
            let actual=header.get("camouflage_generation").and_then(Value::as_str).filter(|s|*s=="-"||hex64(s)).ok_or_else(||invalid("domain reply generation"))?;
            let received=header.get("camouflage_proof").and_then(Value::as_str).filter(|s|hex64(s)).ok_or_else(||invalid("domain reply proof"))?;
            let expected=response_proof(&self.secret,&request,actual,status,&reply);
            if !bool::from(expected.as_bytes().ct_eq(received.as_bytes())) {return Err(invalid("domain reply authentication"));}
            if generation.is_some_and(|expected|expected!="-" && expected!=actual) {return Err(invalid("domain generation changed"));}
            if generation==Some("-") && status==200 {
                let super::Bounded::<16>(description)=serde_json::from_slice(&reply).map_err(|_|invalid("domain camouflage describe JSON"))?;
                let body_generation=description.get("camouflage_generation").and_then(Value::as_str).unwrap_or("-");
                if body_generation!=actual {return Err(invalid("domain describe generation mismatch"));}
            }
        }
        Ok((status,reply))
    }
}

fn write_frame(stream:&mut TcpStream,header:&Value,body:&[u8])->io::Result<()>{
    let raw=serde_json::to_vec(header).map_err(|_|invalid("domain header encoding"))?;
    if raw.is_empty()||raw.len()>MAX_HEADER||2+raw.len()+body.len()>MAX_FRAME{return Err(invalid("domain frame bound"));}
    let mut frame=Vec::with_capacity(6+raw.len()+body.len());
    frame.extend(((2+raw.len()+body.len()) as u32).to_be_bytes());frame.extend((raw.len() as u16).to_be_bytes());
    frame.extend(&raw);frame.extend(body);stream.write_all(&frame)
}
fn read_exact(stream:&mut TcpStream,buffer:&mut [u8],deadline:Instant)->io::Result<()>{
    let mut filled=0;
    while filled<buffer.len(){
        let remaining=deadline.checked_duration_since(Instant::now()).ok_or_else(||io::Error::new(io::ErrorKind::TimedOut,"domain deadline"))?;
        stream.set_read_timeout(Some(remaining.min(Duration::from_millis(500)).max(Duration::from_millis(1))))?;
        match stream.read(&mut buffer[filled..]){
            Ok(0)=>return Err(io::Error::new(io::ErrorKind::UnexpectedEof,"domain closed")),
            Ok(n)=>filled+=n,
            Err(error) if matches!(error.kind(),io::ErrorKind::WouldBlock|io::ErrorKind::TimedOut)=>{},
            Err(error)=>return Err(error),
        }
    }
    Ok(())
}
/// Flat bounded header object with the schema; body at most `max_body` bytes.
fn read_frame(stream:&mut TcpStream,deadline:Instant,max_body:usize)->io::Result<(serde_json::Map<String,Value>,Vec<u8>)>{
    let mut length=[0u8;4];read_exact(stream,&mut length,deadline)?;
    let length=u32::from_be_bytes(length) as usize;
    if !(3..=MAX_FRAME).contains(&length){return Err(invalid("domain frame length"));}
    let mut payload=vec![0u8;length];read_exact(stream,&mut payload,deadline)?;
    let size=u16::from_be_bytes([payload[0],payload[1]]) as usize;
    if size==0||size>MAX_HEADER||2+size>length||!payload[2..2+size].is_ascii(){return Err(invalid("domain header bound"));}
    let super::Bounded::<8>(fields)=serde_json::from_slice(&payload[2..2+size]).map_err(|_|invalid("domain header JSON"))?;
    if fields.get("schema").and_then(Value::as_str)!=Some(SCHEMA)||fields.values().any(|v|v.is_object()||v.is_array()){return Err(invalid("domain header schema"));}
    let body=payload[2+size..].to_vec();
    if body.len()>max_body{return Err(invalid("domain response size"));}
    Ok((fields.into_iter().collect(),body))
}

#[cfg(test)]
mod tests{
    use super::*;
    use std::{net::TcpListener,thread};

    #[test]
    fn hmac_matches_rfc4231_case2_and_long_key(){
        assert_eq!(hex(&hmac_sha256(b"Jefe",b"what do ya want for nothing?")),"5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843");
        // RFC 4231 case 6: 131-byte key is hashed first.
        assert_eq!(hex(&hmac_sha256(&[0xaa;131],b"Test Using Larger Than Block-Size Key - Hash Key First")),"60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54");
    }
    #[test]
    fn camouflage_cross_language_wire_vector(){
        let hello="ab".repeat(32);let nonce="cd".repeat(32);let generation="12".repeat(32);
        let header=serde_json::json!({"id":42,"op":"research","account_id":"5b0b6a52-7d4e-4f1a-9c3b-2e1d0f9a8b7c","key":"k:1"});
        let proof=request_proof(SECRET,&hello,&nonce,&generation,&header,br#"{"x":1}"#).unwrap();
        assert_eq!(proof,"70416858b4c486502cf3aaaedb38957ebf6e3f6332bf5da3c154983e05457fc2");
        assert_eq!(response_proof(SECRET,&proof,&generation,200,br#"{"ok":true}"#),"ab82b8343c9f2e7ce97bf46d748dda79e0038c5d45bf4df424f1ab9fa42a379e");
    }
    #[test]
    fn only_domain_writer_paths_are_routed(){
        assert_eq!(operation("/internal/native/battle-results"),Some("results"));
        assert_eq!(operation("/internal/native/crew-recruit-barracks"),Some("recruit-barracks"));
        assert_eq!(operation("/internal/native/late-result-pending"),Some("late-pending"));
        for path in["/internal/native/login","/internal/native/profile","/internal/native/room-selection","/internal/native/room-selection-loss"]{assert_eq!(operation(path),None);}
    }

    fn frame(header:&Value,body:&[u8])->Vec<u8>{let raw=serde_json::to_vec(header).unwrap();
        let mut out=((2+raw.len()+body.len()) as u32).to_be_bytes().to_vec();out.extend((raw.len() as u16).to_be_bytes());out.extend(raw);out.extend(body);out}
    fn take(stream:&mut TcpStream)->(Value,Vec<u8>){let mut n=[0u8;4];stream.read_exact(&mut n).unwrap();let mut p=vec![0u8;u32::from_be_bytes(n) as usize];stream.read_exact(&mut p).unwrap();
        let h=u16::from_be_bytes([p[0],p[1]]) as usize;(serde_json::from_slice(&p[2..2+h]).unwrap(),p[2+h..].to_vec())}
    /// Fake Domain: checks the proof, records the request, answers with `reply`.
    fn fake(secret:&'static [u8],reply:Option<(u64,u64,&'static [u8])>)->(SocketAddrV4,thread::JoinHandle<Option<(Value,Vec<u8>)>>){
        let listener=TcpListener::bind("127.0.0.1:0").unwrap();let address=match listener.local_addr().unwrap(){std::net::SocketAddr::V4(a)=>a,_=>unreachable!()};
        (address,thread::spawn(move||{
            let(mut stream,_)=listener.accept().unwrap();let nonce="ab".repeat(32);
            stream.write_all(&frame(&serde_json::json!({"schema":SCHEMA,"nonce":nonce}),&[])).unwrap();
            let(hello,_)=take(&mut stream);
            if hello["proof"]!=hex(&hmac_sha256(secret,format!("{SCHEMA}:{nonce}").as_bytes())){return None;}
            stream.write_all(&frame(&serde_json::json!({"schema":SCHEMA,"status":200}),&[])).unwrap();
            let request=take(&mut stream);
            if let Some((id,status,body))=reply{stream.write_all(&frame(&serde_json::json!({"schema":SCHEMA,"id":id,"status":status,"error":null}),body)).unwrap();}
            else{thread::sleep(Duration::from_millis(600));}
            Some(request)
        }))
    }
    const SECRET:&[u8]=b"dom01-test-secret-0123456789abcdefghijklmno";

    fn fake_signed(secret:&'static [u8],status:u64,body:&'static [u8],actual:&'static str,tamper:bool)
        ->(SocketAddrV4,thread::JoinHandle<(Value,Vec<u8>)>){
        let listener=TcpListener::bind("127.0.0.1:0").unwrap();let address=match listener.local_addr().unwrap(){std::net::SocketAddr::V4(a)=>a,_=>unreachable!()};
        (address,thread::spawn(move||{
            let(mut stream,_)=listener.accept().unwrap();let hello_nonce="ab".repeat(32);
            stream.write_all(&frame(&serde_json::json!({"schema":SCHEMA,"nonce":hello_nonce}),&[])).unwrap();
            let(hello,_)=take(&mut stream);assert_eq!(hello["proof"],hex(&hmac_sha256(secret,format!("{SCHEMA}:{hello_nonce}").as_bytes())));
            stream.write_all(&frame(&serde_json::json!({"schema":SCHEMA,"status":200}),&[])).unwrap();
            let(header,request_body)=take(&mut stream);
            let nonce=header["camouflage_nonce"].as_str().unwrap();let generation=header["camouflage_generation"].as_str().unwrap();
            let supplied=header["camouflage_request_proof"].as_str().unwrap();
            assert_eq!(supplied,request_proof(secret,&hello_nonce,nonce,generation,&header,&request_body).unwrap());
            let proof=if tamper {"0".repeat(64)} else {response_proof(secret,supplied,actual,status as u16,body)};
            stream.write_all(&frame(&serde_json::json!({"schema":SCHEMA,"id":1,"status":status,"error":null,"camouflage_generation":actual,"camouflage_proof":proof}),body)).unwrap();
            (header,request_body)
        }))
    }

    /// Interop with the real Python service: start server/domain/service.py, then run with
    /// DOM01_DOMAIN_ENDPOINT, DOM01_DOMAIN_SECRET_FILE, DOM01_DOMAIN_ACCOUNT, DOM01_DOMAIN_NATIVE_ID and --ignored.
    #[test]
    #[ignore="needs a running Python Domain (DOM01_DOMAIN_* environment)"]
    fn real_python_domain_authenticates_and_authorizes(){
        let env=|k:&str|std::env::var(k).unwrap_or_else(|_|panic!("{k} required"));
        let address=env("DOM01_DOMAIN_ENDPOINT").parse().unwrap();let secret=std::fs::read(env("DOM01_DOMAIN_SECRET_FILE")).unwrap();
        let account=env("DOM01_DOMAIN_ACCOUNT");let native:i64=env("DOM01_DOMAIN_NATIVE_ID").parse().unwrap();
        let endpoint=Endpoint{address,secret,camouflage_generation:None};
        let foreign=serde_json::to_vec(&serde_json::json!({"account_id":account,"native_database_id":native+1,"command_key":"dom01-interop"})).unwrap();
        assert_eq!(endpoint.call("research",&foreign,Duration::from_secs(5),8192).unwrap(),(403,Vec::new()));
        let stranger=serde_json::to_vec(&serde_json::json!({"account_id":"00000000-0000-4000-8000-000000000000","command_key":"k"})).unwrap();
        assert_eq!(endpoint.call("research",&stranger,Duration::from_secs(5),8192).unwrap().0,403);
        let unkeyed=serde_json::to_vec(&serde_json::json!({"account_id":account,"native_database_id":native})).unwrap();
        assert_eq!(endpoint.call("research",&unkeyed,Duration::from_secs(20),8192).unwrap().0,503,"worker path reached, store fails closed");
        let wrong=Endpoint{address,secret:b"x".repeat(43),camouflage_generation:None};assert!(wrong.call("research",&foreign,Duration::from_secs(5),8192).is_err());
    }

    #[test]
    #[ignore="needs an isolated camouflage-enabled Python Domain and DOM01_DOMAIN_* environment"]
    fn real_python_domain_camouflage_interop(){
        let env=|k:&str|std::env::var(k).unwrap_or_else(|_|panic!("{k} required"));
        let address=env("DOM01_DOMAIN_ENDPOINT").parse().unwrap();let secret=std::fs::read(env("DOM01_DOMAIN_SECRET_FILE")).unwrap();
        let mut endpoint=Endpoint{address,secret,camouflage_generation:None};endpoint.bind_camouflage().unwrap();
        let stranger=br#"{"account_id":"00000000-0000-4000-8000-000000000000","command_key":"k"}"#;
        let(status,body)=endpoint.call("research",stranger,Duration::from_secs(5),8192).unwrap();
        assert_eq!(status,403);assert!(body.is_empty());
    }
    #[test]
    #[ignore="needs an isolated Python Domain and dedicated gateway guard environment"]
    fn real_python_domain_camouflage_live_interop(){
        let env=|k:&str|std::env::var(k).unwrap_or_else(|_|panic!("{k} required"));
        let address=env("DOM01_DOMAIN_ENDPOINT").parse().unwrap();let secret=std::fs::read(env("DOM01_DOMAIN_SECRET_FILE")).unwrap();
        let guard_secret=std::path::PathBuf::from(env("DOM01_GATEWAY_GUARD_SECRET_FILE"));
        let local=guard_secret.parent().unwrap().canonicalize().unwrap();
        let guard_config=super::super::camouflage_live::Config::parse(&serde_json::json!({"version":1,"bind":env("DOM01_GATEWAY_GUARD_BIND"),"secret_file":guard_secret}),&local).unwrap();
        let mut endpoint=Endpoint{address,secret,camouflage_generation:None};endpoint.bind_camouflage().unwrap();
        let ping=serde_json::json!({"schema":SCHEMA,"id":1,"op":"ping","account_id":null,"key":null});
        let probe=||endpoint.exchange(&ping,&[],Duration::from_secs(3),8192,endpoint.camouflage_generation.as_deref()).unwrap().0;
        assert_eq!(probe(),503,"missing gateway must fail closed");
        let guard=guard_config.start(endpoint.camouflage_generation.as_deref().unwrap()).unwrap();
        guard.pulse();
        assert_eq!(probe(),200,"live gateway must prove the challenge");
        std::thread::sleep(Duration::from_millis(650));
        assert_eq!(probe(),503,"a stalled main loop must fail closed");
        guard.pulse();
        assert_eq!(probe(),200,"fresh main loop progress restores liveness");
        drop(guard);
        assert_eq!(probe(),503,"stopped gateway must fail closed without a lease window");
    }

    #[test]
    fn call_sends_same_body_with_header_and_returns_status_and_raw_reply(){
        let(address,server)=fake(SECRET,Some((1,200,br#"{"status":"admitted"}"#)));
        let endpoint=Endpoint{address,secret:SECRET.to_vec(),camouflage_generation:None};
        let body=br#"{"account_id":"5b0b6a52-7d4e-4f1a-9c3b-2e1d0f9a8b7c","command_key":"open:1","version":2}"#;
        assert_eq!(endpoint.call("battle",body,Duration::from_secs(5),8192).unwrap(),(200,br#"{"status":"admitted"}"#.to_vec()));
        let(header,sent)=server.join().unwrap().unwrap();
        assert_eq!(header,serde_json::json!({"schema":SCHEMA,"id":1,"op":"battle","account_id":"5b0b6a52-7d4e-4f1a-9c3b-2e1d0f9a8b7c","key":"open:1"}));
        assert_eq!(sent,body.to_vec());
    }
    #[test]
    fn camouflage_handshake_binds_generation_and_sends_it_on_every_rpc(){
        let describe=br#"{"schema":"wot091-domain.v1","version":1,"camouflage_v1":true,"camouflage_generation":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","accounts":[],"operations":[]}"#;
        const GEN:&str="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        let(address,server)=fake_signed(SECRET,200,describe,GEN,false);
        let mut endpoint=Endpoint{address,secret:SECRET.to_vec(),camouflage_generation:None};
        endpoint.bind_camouflage().unwrap();
        let(header,body)=server.join().unwrap();
        assert_eq!(header["op"],"describe");assert_eq!(header["camouflage_generation"],"-");
        assert!(body.is_empty());
        assert!(endpoint.bind_camouflage().is_err(),"the generation cannot be silently replaced");
        let(address,server)=fake_signed(SECRET,403,b"","bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",false);endpoint.address=address;
        let body=br#"{"account_id":"5b0b6a52-7d4e-4f1a-9c3b-2e1d0f9a8b7c","command_key":"open:1"}"#;
        assert!(endpoint.call("battle",body,Duration::from_secs(5),8192).is_err(),"restarted Domain must fail closed");
        let(header,sent)=server.join().unwrap();assert_eq!(header["camouflage_generation"],"a".repeat(64));assert_eq!(sent,body);
    }
    #[test]
    fn camouflage_handshake_rejects_disabled_missing_invalid_duplicate_and_non200(){
        let samples:&[(u64,&'static [u8])]=&[
            (200,br#"{"schema":"wot091-domain.v1","version":1,"camouflage_v1":false,"camouflage_generation":null}"#),
            (200,br#"{"schema":"wot091-domain.v1","version":1}"#),
            (200,br#"{"schema":"wot091-domain.v1","version":1,"camouflage_v1":true,"camouflage_generation":"ABC"}"#),
            (200,br#"{"schema":"wot091-domain.v1","version":1,"camouflage_v1":true,"camouflage_v1":true,"camouflage_generation":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}"#),
            (403,b""),
        ];
        for &(status,body) in samples {
            let(address,server)=fake_signed(SECRET,status,body,"-",false);
            let mut endpoint=Endpoint{address,secret:SECRET.to_vec(),camouflage_generation:None};
            assert!(endpoint.bind_camouflage().is_err());assert!(endpoint.camouflage_generation.is_none());server.join().unwrap();
        }
    }
    #[test]
    fn camouflage_rejects_response_tampering_and_never_binds_generation(){
        let body=br#"{"schema":"wot091-domain.v1","version":1,"camouflage_v1":true,"camouflage_generation":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}"#;
        let(address,server)=fake_signed(SECRET,200,body,"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",true);
        let mut endpoint=Endpoint{address,secret:SECRET.to_vec(),camouflage_generation:None};
        assert!(endpoint.bind_camouflage().is_err());assert!(endpoint.camouflage_generation.is_none());server.join().unwrap();
    }
    #[test]
    fn non_200_wrong_id_oversize_deadline_and_wrong_secret_fail(){
        let body=br#"{"account_id":"5b0b6a52-7d4e-4f1a-9c3b-2e1d0f9a8b7c"}"#;
        let(address,server)=fake(SECRET,Some((1,503,b"")));
        assert_eq!(Endpoint{address,secret:SECRET.to_vec(),camouflage_generation:None}.call("fixture",body,Duration::from_secs(5),8192).unwrap().0,503);server.join().unwrap();
        let(address,server)=fake(SECRET,Some((2,200,b"{}")));
        assert!(Endpoint{address,secret:SECRET.to_vec(),camouflage_generation:None}.call("fixture",body,Duration::from_secs(5),8192).is_err());server.join().unwrap();
        let(address,server)=fake(SECRET,Some((1,200,b"0123456789")));
        assert!(Endpoint{address,secret:SECRET.to_vec(),camouflage_generation:None}.call("fixture",body,Duration::from_secs(5),4).is_err());server.join().unwrap();
        let(address,server)=fake(SECRET,None);
        assert_eq!(Endpoint{address,secret:SECRET.to_vec(),camouflage_generation:None}.call("fixture",body,Duration::from_millis(300),8192).unwrap_err().kind(),io::ErrorKind::TimedOut);server.join().unwrap();
        let(address,server)=fake(b"other-secret-0123456789abcdefghijklmnopqrst",Some((1,200,b"{}")));
        assert!(Endpoint{address,secret:SECRET.to_vec(),camouflage_generation:None}.call("fixture",body,Duration::from_secs(5),8192).is_err());assert!(server.join().unwrap().is_none());
        assert!(Endpoint{address,secret:SECRET.to_vec(),camouflage_generation:None}.call("fixture",b"not json",Duration::from_secs(1),8192).is_err());
    }
}
