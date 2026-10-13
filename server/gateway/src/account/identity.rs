//! Local website identity boundary. No credential registry or native object loader.
use std::{collections::BTreeMap, fs, fmt, io::{self,Read,Write}, net::{Ipv4Addr,SocketAddrV4,TcpStream},
          path::{Path,PathBuf}, time::{Duration,Instant}};
use serde::{Deserialize,Deserializer,de::{self,MapAccess,Visitor}};
use serde_json::Value;

fn invalid(message:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,message)}

// Reject duplicate top-level keys instead of accepting an ambiguous last value.
struct Object(BTreeMap<String,Value>);
impl<'de> Deserialize<'de> for Object {
    fn deserialize<D:Deserializer<'de>>(deserializer:D)->Result<Self,D::Error> {
        struct Fields;
        impl<'de> Visitor<'de> for Fields {
            type Value=Object;
            fn expecting(&self,f:&mut fmt::Formatter)->fmt::Result {f.write_str("a bounded object with unique keys")}
            fn visit_map<M:MapAccess<'de>>(self,mut input:M)->Result<Object,M::Error> {
                let mut output=BTreeMap::new();
                while let Some((key,value))=input.next_entry::<String,Value>()? {
                    if output.len()>=16 || output.insert(key,value).is_some() {return Err(de::Error::custom("duplicate/too many fields"));}
                }
                Ok(Object(output))
            }
        }
        deserializer.deserialize_map(Fields)
    }
}
fn object(bytes:&[u8],keys:&[&str])->io::Result<BTreeMap<String,Value>> {
    if bytes.len()>4096 {return Err(invalid("JSON size bound"));}
    let Object(value)=serde_json::from_slice(bytes).map_err(|_|invalid("invalid bounded JSON object"))?;
    if value.len()!=keys.len() || keys.iter().any(|key|!value.contains_key(*key)) {return Err(invalid("JSON field contract"));}
    Ok(value)
}
fn text<'a>(value:&'a BTreeMap<String,Value>,key:&str)->io::Result<&'a str> {
    value.get(key).and_then(Value::as_str).ok_or_else(||invalid("JSON string type"))
}
fn local_address(value:&str)->io::Result<SocketAddrV4> {
    let address:SocketAddrV4=value.parse().map_err(|_|invalid("numeric IPv4 endpoint required"))?;
    if *address.ip()!=Ipv4Addr::LOCALHOST || address.port()==0 {return Err(invalid("endpoint must be 127.0.0.1 with a nonzero port"));}
    Ok(address)
}
fn bounded_file(path:&Path,max:u64)->io::Result<Vec<u8>> {
    let file=fs::File::open(path)?;
    if !file.metadata()?.is_file() || file.metadata()?.len()>max {return Err(invalid("local input file size/type"));}
    let mut bytes=Vec::new();file.take(max+1).read_to_end(&mut bytes)?;
    if bytes.len() as u64>max {return Err(invalid("local input grew beyond bound"));}Ok(bytes)
}

pub struct Config {
    pub login_bind:SocketAddrV4,pub base_bind:SocketAddrV4,identity_endpoint:SocketAddrV4,
    token:String,pub local_root:PathBuf,pub session_duration:Duration,
    pub ammo_service:bool,pub crew_service:bool,pub crew_transfer:bool,pub crew_cross_vehicle:bool,pub crew_roster_recruitment:bool,
}
impl Config {
    pub fn load(path:&str)->io::Result<Self> {
        let bytes=bounded_file(Path::new(path),4096)?;
        let Object(mut value)=serde_json::from_slice(&bytes).map_err(|_|invalid("invalid gateway config"))?;
        let ammo_service=match value.remove("ammunition_service") {
            None=>false,Some(Value::Bool(value))=>value,_=>return Err(invalid("ammunition service must be explicit boolean")),
        };
        let crew_service=match value.remove("crew_service") {
            None=>false,Some(Value::Bool(value))=>value,_=>return Err(invalid("crew service must be explicit boolean")),
        };
        if crew_service && !ammo_service {return Err(invalid("crew service requires shared ammunition service"));}
        let crew_transfer=match value.remove("crew_transfer") {
            None=>false,Some(Value::Bool(value))=>value,_=>return Err(invalid("crew transfer must be explicit boolean")),
        };
        if crew_transfer && !crew_service {return Err(invalid("crew transfer requires shared crew service"));}
        let crew_cross_vehicle=match value.remove("crew_cross_vehicle") {
            None=>false,Some(Value::Bool(value))=>value,_=>return Err(invalid("cross-vehicle crew must be explicit boolean")),
        };
        if crew_cross_vehicle && !crew_transfer {return Err(invalid("cross-vehicle crew requires crew transfer"));}
        let crew_roster_recruitment=match value.remove("crew_roster_recruitment") {
            None=>false,Some(Value::Bool(value))=>value,_=>return Err(invalid("roster recruitment must be explicit boolean")),
        };
        if crew_roster_recruitment && !crew_cross_vehicle {return Err(invalid("roster recruitment requires cross-vehicle crew"));}
        let keys=["login_bind","base_bind","identity_endpoint","identity_token_file","local_root","session_duration_seconds"];
        if value.len()!=keys.len() || keys.iter().any(|key|!value.contains_key(*key)) {return Err(invalid("gateway config fields"));}
        let login_bind=local_address(text(&value,"login_bind")?)?;
        let base_bind=local_address(text(&value,"base_bind")?)?;
        let identity_endpoint=local_address(text(&value,"identity_endpoint")?)?;
        if login_bind==base_bind || login_bind==identity_endpoint || base_bind==identity_endpoint {return Err(invalid("service ports must be distinct"));}
        let root=Path::new(text(&value,"local_root")?);
        if !root.is_absolute() {return Err(invalid("absolute local root required"));}
        let local_root=root.canonicalize()?;
        if !local_root.is_dir() {return Err(invalid("local root directory required"));}
        let token_path=Path::new(text(&value,"identity_token_file")?).canonicalize()?;
        if !token_path.starts_with(&local_root) {return Err(invalid("identity token file escapes local root"));}
        let token=String::from_utf8(bounded_file(&token_path,43)?).map_err(|_|invalid("service token encoding"))?;
        if token.len()!=43 || !token.bytes().all(|b|b.is_ascii_alphanumeric() || b==b'_' || b==b'-') {return Err(invalid("service token must be exactly 43 base64url characters"));}
        let seconds=value["session_duration_seconds"].as_u64().ok_or_else(||invalid("session duration integer"))?;
        if !(600..=7200).contains(&seconds) {return Err(invalid("session duration must be 600..7200 seconds"));}
        Ok(Self {login_bind,base_bind,identity_endpoint,token,local_root,session_duration:Duration::from_secs(seconds),ammo_service,crew_service,crew_transfer,crew_cross_vehicle,crew_roster_recruitment})
    }
    pub fn authenticate(&self,email:&str,password:&str)->io::Result<Option<Profile>> {
        let email=canonical_email(email)?;
        let body=serde_json::to_vec(&serde_json::json!({"email":email,"password":password}))
            .map_err(|_|invalid("identity request serialization"))?;
        if body.len()>2048 {return Err(invalid("identity request size"));}
        let (status,body)=self.post("/internal/native/login",&body,Duration::from_secs(5))?;
        if status==401 {return Ok(None);}
        if status!=200 {return Err(invalid("identity service unavailable or rejected service authentication"));}
        let profile=profile(&body,&self.local_root)?;
        verify_fixture_identity(&profile)?;
        if self.ammo_service {
            let binding=crate::ammo_service091::metadata(&profile.fixture_dir,&profile.account_id,profile.database_id)?;
            if self.crew_transfer {
                crate::crew_transfer091::metadata_for(crate::crew_transfer091::Profile::selected_roster(self.crew_cross_vehicle,self.crew_roster_recruitment),&profile.fixture_dir,&profile.account_id,profile.database_id,binding.revision,binding.wire_revision)?;
            } else if self.crew_service {
                crate::crew_service091::metadata(&profile.fixture_dir,&profile.account_id,profile.database_id,binding.revision,binding.wire_revision)?;
            }
        }
        Ok(Some(profile))
    }

    /// Bounded loopback transport; only fixed internal paths supplied by this module.
    fn post(&self,path:&str,body:&[u8],timeout:Duration)->io::Result<(u16,Vec<u8>)> {
        let deadline=Instant::now()+timeout;
        let mut stream=TcpStream::connect_timeout(&self.identity_endpoint.into(),Duration::from_millis(500))?;
        stream.set_write_timeout(Some(Duration::from_secs(2)))?;
        let header=format!("POST {path} HTTP/1.1\r\nHost: {}\r\nAuthorization: Bearer {}\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n",self.identity_endpoint,self.token,body.len());
        stream.write_all(header.as_bytes())?;stream.write_all(&body)?;
        let mut response=Vec::new();
        loop {
            let remaining=deadline.checked_duration_since(Instant::now()).ok_or_else(||io::Error::new(io::ErrorKind::TimedOut,"identity deadline"))?;
            stream.set_read_timeout(Some(remaining.min(Duration::from_millis(500))))?;
            let mut buffer=[0u8;1024];
            match stream.read(&mut buffer) {
                Ok(0)=>break,
                Ok(n)=>{if response.len()+n>8192 {return Err(invalid("identity response size"));}response.extend(&buffer[..n]);},
                Err(error) if matches!(error.kind(),io::ErrorKind::WouldBlock|io::ErrorKind::TimedOut)=>{},
                Err(error)=>return Err(error),
            }
        }
        let (status,body)=http_response(&response)?;
        Ok((status,body.to_vec()))
    }

    pub fn service_ammunition(&self,profile:&Profile,command_key:&str,expected_revision:u64,
                              wire_revision:i64,layout:[i32;16])->io::Result<AmmoReply> {
        if !self.ammo_service || !valid_command_key(command_key) || !(5..i32::MAX as u64).contains(&expected_revision)
            || !(1..i32::MAX as i64).contains(&wire_revision) {return Err(invalid("ammunition service request boundary"));}
        let body=serde_json::to_vec(&serde_json::json!({"account_id":profile.account_id,
            "native_database_id":profile.database_id,"command_key":command_key,
            "expected_revision":expected_revision,"wire_revision":wire_revision,"layout":layout}))
            .map_err(|_|invalid("ammo request serialization"))?;
        if body.len()>2048 {return Err(invalid("ammo request size"));}
        let (status,bytes)=self.post("/internal/native/ammo",&body,Duration::from_secs(20))?;
        if status!=200 {return Err(invalid("ammo service HTTP failure; outcome must be recovered by fresh login"));}
        ammo_reply(&bytes,profile,command_key,expected_revision,wire_revision)
    }

    pub fn recruit_crew(&self,profile:&Profile,command_key:&str,expected_revision:u64,
                        wire_revision:i64,request:crate::crew_service091::Request)->io::Result<AmmoReply> {
        if !self.crew_service || !self.ammo_service {return Err(invalid("crew service is not enabled"));}
        let body=crate::crew_service091::service_request_for(self.crew_roster_recruitment,&profile.account_id,profile.database_id,command_key,
            expected_revision,wire_revision,request)?;
        let (status,bytes)=self.post("/internal/native/crew",&body,Duration::from_secs(20))?;
        if status!=200 {return Err(invalid("crew service HTTP failure; outcome must be recovered by fresh login"));}
        service_reply(&bytes,profile,command_key,expected_revision,wire_revision,"recruited")
    }

    pub fn transfer_crew(&self,profile:&Profile,command_key:&str,expected_revision:u64,
                         wire_revision:i64,request:crate::crew_transfer091::Request)->io::Result<AmmoReply> {
        if !self.crew_transfer || !self.crew_service || !self.ammo_service {return Err(invalid("crew transfer is not enabled"));}
        let body=crate::crew_transfer091::service_request_for(crate::crew_transfer091::Profile::selected_roster(self.crew_cross_vehicle,self.crew_roster_recruitment),&profile.account_id,profile.database_id,command_key,
            expected_revision,wire_revision,request)?;
        let (status,bytes)=self.post("/internal/native/crew-transfer",&body,Duration::from_secs(20))?;
        if status!=200 {return Err(invalid("crew transfer HTTP failure; recover outcome by fresh login"));}
        service_reply(&bytes,profile,command_key,expected_revision,wire_revision,"transferred")
    }
}

pub struct AmmoReply {pub serviced:bool,pub revision:u64,pub wire_revision:i64,
    pub update:Vec<u8>,pub replayed:bool,pub result_code:i32}

fn valid_command_key(key:&str)->bool {
    (1..=96).contains(&key.len()) && key.bytes().all(|b|b.is_ascii_alphanumeric() || b"-_:".contains(&b))
}

fn ammo_reply(bytes:&[u8],profile:&Profile,key:&str,expected:u64,wire:i64)->io::Result<AmmoReply> {
    service_reply(bytes,profile,key,expected,wire,"serviced")
}

fn service_reply(bytes:&[u8],profile:&Profile,key:&str,expected:u64,wire:i64,success_status:&str)->io::Result<AmmoReply> {
    if !(5..i32::MAX as u64).contains(&expected) || !(1..i32::MAX as i64).contains(&wire)
        || !matches!(success_status,"serviced"|"recruited"|"transferred") {return Err(invalid("service reply cursor/status boundary"));}
    let value=object(bytes,&["status","account_id","native_database_id","command_key","revision",
        "wire_revision","update_hex","replayed","result_code"])?;
    if text(&value,"account_id")?!=profile.account_id || value["native_database_id"].as_i64()!=Some(profile.database_id as i64)
        || text(&value,"command_key")?!=key {return Err(invalid("ammo reply authentication binding"));}
    let status=text(&value,"status")?;
    let serviced=if status==success_status {true} else if status=="rejected" {false} else {return Err(invalid("service reply status"));};
    let revision=value["revision"].as_u64().ok_or_else(||invalid("ammo reply revision"))?;
    let wire_revision=value["wire_revision"].as_i64().ok_or_else(||invalid("ammo reply wire revision"))?;
    if revision!=expected+u64::from(serviced) || wire_revision!=wire+i64::from(serviced) {
        return Err(invalid("ammo reply revision transition"));
    }
    let replayed=value["replayed"].as_bool().ok_or_else(||invalid("ammo reply replay type"))?;
    let result_code=value["result_code"].as_i64().ok_or_else(||invalid("ammo reply result code type"))?;
    if result_code!=if serviced {0} else {-10} {
        return Err(invalid("ammo reply result code"));
    }
    let hex=text(&value,"update_hex")?;
    if hex.len()>crate::ammo_service091::MAX_DELTA_BYTES*2 || hex.len()%2!=0
        || !hex.bytes().all(|b|b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) {
        return Err(invalid("ammo reply delta encoding"));
    }
    let mut update=Vec::with_capacity(hex.len()/2);
    for offset in (0..hex.len()).step_by(2) {
        update.push(u8::from_str_radix(&hex[offset..offset+2],16).map_err(|_|invalid("ammo reply delta hex"))?);
    }
    if serviced {crate::ammo_service091::response(1,&update)?;}
    else if !update.is_empty() || replayed {return Err(invalid("rejected ammo reply changed state"));}
    Ok(AmmoReply{serviced,revision,wire_revision,update,replayed,result_code:result_code as i32})
}

/// Native ConnectionManager.connect115, checked RU basic branch only. Other
/// auth providers, saved passwords/tokens and registration are not this entry.
pub fn credentials(username:&[u8],password:&[u8])->io::Result<(String,String)> {
    let data=object(username,&["login","auth_method","session","auth_realm","game","temporary"])?;
    if text(&data,"auth_method")?!="basic" || text(&data,"auth_realm")?!="RU" || text(&data,"game")?!="wot"
        || text(&data,"temporary")?!="1" {return Err(invalid("unsupported native authentication branch"));}
    let hardware=text(&data,"session")?;
    if hardware.len()!=32 || !hardware.bytes().all(|b|b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) {return Err(invalid("native hardware token shape"));}
    let email=canonical_email(text(&data,"login")?)?;
    let password=std::str::from_utf8(password).map_err(|_|invalid("native password encoding"))?;
    // Match the website's scalar/UTF-8 resource bounds. The bridge owns password
    // policy and verification; never trim or normalize the password here.
    if password.len()>512 || password.chars().count()>128 {return Err(invalid("native password scalar/byte bound"));}
    Ok((email,password.to_owned()))
}

fn canonical_email(raw:&str)->io::Result<String> {
    if !raw.is_ascii() {return Err(invalid("email must be ASCII"));}
    let clean=raw.trim_matches(|c:char|matches!(c,'\t'..='\r'|' ')).to_ascii_lowercase();
    if clean.len()>254 {return Err(invalid("email length"));}
    let (local,domain)=clean.split_once('@').ok_or_else(||invalid("email separator"))?;
    if !(1..=64).contains(&local.len()) || local.starts_with('.') || local.ends_with('.') || local.contains("..")
        || !local.bytes().all(|b|b.is_ascii_lowercase() || b.is_ascii_digit() || b".!#$%&'*+/=?^_`{|}~-".contains(&b)) {
        return Err(invalid("email local part"));
    }
    let labels:Vec<&str>=domain.split('.').collect();
    if labels.len()<2 || labels.iter().any(|label|label.is_empty() || label.len()>63
        || !label.as_bytes()[0].is_ascii_alphanumeric() || !label.as_bytes()[label.len()-1].is_ascii_alphanumeric()
        || !label.bytes().all(|b|b.is_ascii_lowercase() || b.is_ascii_digit() || b==b'-'))
        || !labels.last().is_some_and(|label|label.bytes().any(|b|b.is_ascii_lowercase())) {
        return Err(invalid("email domain"));
    }
    Ok(clean)
}

fn valid_native_nickname(name:&str)->bool {
    (3..=24).contains(&name.chars().count()) && name.len()<=48
        && name.chars().all(|c|c.is_ascii_alphanumeric() || c=='_' || matches!(c,'А'..='я'|'Ё'|'ё'))
}

fn http_response(bytes:&[u8])->io::Result<(u16,&[u8])> {
    let end=bytes.windows(4).position(|b|b==b"\r\n\r\n").ok_or_else(||invalid("HTTP header incomplete"))?;
    if end>4096 || bytes.len()>8192 || !bytes[..end].is_ascii() {return Err(invalid("HTTP response size/ASCII bound"));}
    let header=std::str::from_utf8(&bytes[..end]).map_err(|_|invalid("HTTP header encoding"))?;
    let mut lines=header.split("\r\n");let status=lines.next().ok_or_else(||invalid("HTTP status absent"))?;
    if !status.starts_with("HTTP/1.1 ") || status.len()<12 {return Err(invalid("HTTP version/status"));}
    let status=status[9..12].parse::<u16>().map_err(|_|invalid("HTTP status code"))?;
    let mut length=None;
    for line in lines {
        let (key,value)=line.split_once(':').ok_or_else(||invalid("HTTP header shape"))?;
        if key.eq_ignore_ascii_case("content-length") {
            if length.is_some() {return Err(invalid("duplicate HTTP length"));}
            length=Some(value.trim().parse::<usize>().map_err(|_|invalid("HTTP length integer"))?);
        }
        if key.eq_ignore_ascii_case("transfer-encoding") {return Err(invalid("chunked identity response is unsupported"));}
    }
    let body=&bytes[end+4..];
    if body.len()>4096 || length!=Some(body.len()) {return Err(invalid("HTTP body length mismatch"));}
    Ok((status,body))
}

pub struct Profile {pub account_id:String,pub database_id:i32,pub name:String,pub fixture_dir:PathBuf}
fn profile(bytes:&[u8],local_root:&Path)->io::Result<Profile> {
    let value=object(bytes,&["account_id","native_database_id","name","fixture_dir"])?;
    let account_id=text(&value,"account_id")?;
    if account_id.len()!=36 || !account_id.bytes().enumerate().all(|(i,b)|if [8,13,18,23].contains(&i) {b==b'-'} else {b.is_ascii_digit() || (b'a'..=b'f').contains(&b)}) {return Err(invalid("website UUID identity shape"));}
    let database_id=value["native_database_id"].as_i64().ok_or_else(||invalid("native database identity type"))?;
    if !(1..=i32::MAX as i64).contains(&database_id) {return Err(invalid("native database identity range"));}
    let name=text(&value,"name")?;
    if !valid_native_nickname(name) {return Err(invalid("native player nickname shape"));}
    let fixture_path=Path::new(text(&value,"fixture_dir")?);
    if !fixture_path.is_absolute() {return Err(invalid("absolute identity fixture path required"));}
    let fixture_dir=fixture_path.canonicalize()?;
    if !fixture_dir.starts_with(local_root) || !fixture_dir.is_dir() {return Err(invalid("identity fixture escapes local root"));}
    for name in ["state.bin","shop.bin","dossier.bin"] {
        if !fixture_dir.join(name).canonicalize()?.starts_with(&fixture_dir) {return Err(invalid("identity fixture member escapes directory"));}
    }
    Ok(Profile {account_id:account_id.to_owned(),database_id:database_id as i32,name:name.to_owned(),fixture_dir})
}
fn verify_fixture_identity(profile:&Profile)->io::Result<()> {
    for name in ["manifest.json","compatibility.json"] {
        let path=profile.fixture_dir.join(name).canonicalize()?;
        if !path.starts_with(&profile.fixture_dir) {return Err(invalid("identity metadata escapes fixture"));}
        let bytes=bounded_file(&path,65536)?;
        let Object(data)=serde_json::from_slice(&bytes).map_err(|_|invalid("invalid identity fixture metadata"))?;
        if text(&data,"account_id")?!=profile.account_id || data.get("native_database_id").and_then(Value::as_i64)!=Some(profile.database_id as i64)
            || (name=="compatibility.json" && text(&data,"client_name")?!=profile.name) {
            return Err(invalid("fixture identity differs from authenticated website account"));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn username()->Vec<u8> {br#"{"login":"registered@example.test","auth_method":"basic","session":"0123456789abcdef0123456789abcdef","auth_realm":"RU","game":"wot","temporary":"1"}"#.to_vec()}
    #[test] fn ammunition_reply_is_bound_to_identity_command_and_both_revisions() {
        let profile=Profile{account_id:"12345678-1234-4234-8234-123456789abc".into(),database_id:17,name:"own_user".into(),fixture_dir:PathBuf::new()};
        let delta=b"\x80\x02}(U\x07prevRevK\x01U\x03revK\x02u.";
        let hex=delta.iter().map(|b|format!("{b:02x}")).collect::<String>();
        let good=serde_json::json!({"status":"serviced","account_id":profile.account_id,"native_database_id":17,
            "command_key":"p09d_test_7","revision":6,"wire_revision":2,"update_hex":hex,"replayed":false,"result_code":0});
        let encode=|value:&Value|serde_json::to_vec(value).unwrap();
        let reply=ammo_reply(&encode(&good),&profile,"p09d_test_7",5,1).unwrap();
        assert!(reply.serviced);assert_eq!(reply.update,delta);
        for (field,bad) in [("account_id",serde_json::json!("other")),("native_database_id",serde_json::json!(18)),
            ("command_key",serde_json::json!("another")),("revision",serde_json::json!(5)),
            ("wire_revision",serde_json::json!(3)),("replayed",serde_json::json!(1)),
            ("result_code",serde_json::json!("bad reason\n")),("status",serde_json::json!("success")),
            ("update_hex",serde_json::json!("8002636f732e"))] {
            let mut wrong=good.clone();wrong[field]=bad;
            assert!(ammo_reply(&encode(&wrong),&profile,"p09d_test_7",5,1).is_err(),"{field}");
        }
        let mut rejected=good;rejected["status"]=serde_json::json!("rejected");rejected["revision"]=serde_json::json!(5);
        rejected["wire_revision"]=serde_json::json!(1);rejected["update_hex"]=serde_json::json!("");
        rejected["result_code"]=serde_json::json!(-10);
        assert!(!ammo_reply(&encode(&rejected),&profile,"p09d_test_7",5,1).unwrap().serviced);
        rejected["replayed"]=serde_json::json!(true);
        assert!(ammo_reply(&encode(&rejected),&profile,"p09d_test_7",5,1).is_err());
        for key in ["", "x\r\n", "x/y", "é", &"x".repeat(129)] {assert!(!valid_command_key(key));}
    }
    #[test] fn native_branch_and_ambiguous_json_rejected() {
        assert_eq!(credentials(&username(),b"own-test-password").unwrap().0,"registered@example.test");
        let duplicate=String::from_utf8(username()).unwrap().replace("{","{\"login\":\"other_user\",");
        assert!(credentials(duplicate.as_bytes(),b"own-test-password").is_err());
        let saved=String::from_utf8(username()).unwrap().replace("\"temporary\":\"1\"","\"temporary\":\"0\"");
        assert!(credentials(saved.as_bytes(),b"own-test-password").is_err());
        assert!(credentials(&username(),&[b'x';129]).is_err());
        assert!(credentials(&username(),&[0xff;15]).is_err());
    }
    #[test] fn crew_reply_cannot_cross_ammunition_status_or_mutate_rejected_state() {
        let profile=Profile{account_id:"12345678-1234-4234-8234-123456789abc".into(),database_id:17,name:"own_user".into(),fixture_dir:PathBuf::new()};
        let delta=b"\x80\x02}(U\x07prevRevK\x01U\x03revK\x02u.";
        let good=serde_json::json!({"status":"recruited","account_id":profile.account_id,"native_database_id":17,
            "command_key":"p04d_test_226","revision":7,"wire_revision":2,
            "update_hex":delta.iter().map(|b|format!("{b:02x}")).collect::<String>(),"replayed":false,"result_code":0});
        let raw=serde_json::to_vec(&good).unwrap();
        assert!(service_reply(&raw,&profile,"p04d_test_226",6,1,"recruited").unwrap().serviced);
        assert!(ammo_reply(&raw,&profile,"p04d_test_226",6,1).is_err());
        for (field,bad) in [("status",Value::from("serviced")),("revision",6.into()),("wire_revision",3.into()),
            ("result_code",(-10).into()),("update_hex","00".repeat(241).into()),("update_hex","8002636f732e".into())] {
            let mut wrong=good.clone();wrong[field]=bad;
            assert!(service_reply(&serde_json::to_vec(&wrong).unwrap(),&profile,"p04d_test_226",6,1,"recruited").is_err(),"{field}");
        }
        let mut rejected=good;rejected["status"]="rejected".into();rejected["revision"]=6.into();rejected["wire_revision"]=1.into();
        rejected["update_hex"]="".into();rejected["result_code"]=(-10).into();
        assert!(!service_reply(&serde_json::to_vec(&rejected).unwrap(),&profile,"p04d_test_226",6,1,"recruited").unwrap().serviced);
        rejected["replayed"]=true.into();
        assert!(service_reply(&serde_json::to_vec(&rejected).unwrap(),&profile,"p04d_test_226",6,1,"recruited").is_err());
    }

    #[test] fn crew_configuration_is_explicit_boolean_and_requires_ammunition_service() {
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/p04d").join(format!("config-{stamp}"));
        fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();
        fs::write(root.join("token.txt"),"a".repeat(43)).unwrap();
        let base=serde_json::json!({"login_bind":"127.0.0.1:23014","base_bind":"127.0.0.1:23015",
            "identity_endpoint":"127.0.0.1:3395","identity_token_file":root.join("token.txt").to_str().unwrap(),
            "local_root":root.to_str().unwrap(),"session_duration_seconds":600});
        let path=root.join("gateway.json");
        let load=|value:&Value| {fs::write(&path,serde_json::to_vec(value).unwrap()).unwrap();Config::load(path.to_str().unwrap())};
        let baseline=load(&base).unwrap();assert!(!baseline.ammo_service);assert!(!baseline.crew_service);
        let mut enabled=base.clone();enabled["ammunition_service"]=true.into();enabled["crew_service"]=true.into();
        let selected=load(&enabled).unwrap();assert!(selected.ammo_service);assert!(selected.crew_service);
        for bad in [Value::from("true"),Value::from(1),Value::Null] {
            let mut row=enabled.clone();row["crew_service"]=bad;assert!(load(&row).is_err());
        }
        assert!(!load(&enabled).unwrap().crew_transfer);
        let mut transfer=enabled.clone();transfer["crew_transfer"]=true.into();assert!(load(&transfer).unwrap().crew_transfer);
        for bad in [Value::Null,0.into(),"true".into(),serde_json::json!({})] {
            let mut row=transfer.clone();row["crew_transfer"]=bad;assert!(load(&row).is_err());
        }
        assert!(!load(&transfer).unwrap().crew_cross_vehicle);
        let mut cross=transfer.clone();cross["crew_cross_vehicle"]=true.into();assert!(load(&cross).unwrap().crew_cross_vehicle);
        for bad in [Value::Null,0.into(),"true".into(),serde_json::json!({})] {
            let mut row=cross.clone();row["crew_cross_vehicle"]=bad;assert!(load(&row).is_err());
        }
        assert!(!load(&cross).unwrap().crew_roster_recruitment);
        let mut roster=cross.clone();roster["crew_roster_recruitment"]=true.into();assert!(load(&roster).unwrap().crew_roster_recruitment);
        for bad in [Value::Null,0.into(),"true".into(),serde_json::json!({})] {
            let mut row=roster.clone();row["crew_roster_recruitment"]=bad;assert!(load(&row).is_err());
        }
        roster["crew_cross_vehicle"]=false.into();assert!(load(&roster).is_err());
        cross["crew_transfer"]=false.into();assert!(load(&cross).is_err());
        transfer["crew_service"]=false.into();assert!(load(&transfer).is_err());
        enabled["ammunition_service"]=false.into();assert!(load(&enabled).is_err());
        enabled.as_object_mut().unwrap().remove("ammunition_service");assert!(load(&enabled).is_err());
    }
    #[test] fn interactive_identity_preserves_website_unicode_and_edge_spaces_with_exact_bounds() {
        for password in ["x".repeat(128),"😀".repeat(128),"  own длинный password  ".to_owned(),
                         "line\nbreak\0allowed-by-website".to_owned()] {
            assert_eq!(credentials(&username(),password.as_bytes()).unwrap().1,password);
        }
        assert!(credentials(&username(),"😀".repeat(129).as_bytes()).is_err());
        assert!(credentials(&username(),&[b'x';513]).is_err());
    }
    #[test] fn email_identity_is_separate_from_bounded_native_nickname() {
        assert_eq!(canonical_email(" \tOwn.User+tag@Example.Test\r\n").unwrap(),"own.user+tag@example.test");
        for bad in ["registered_user","own@localhost","a..b@example.test","a.@example.test",".a@example.test",
                    "a@@example.test","a@-example.test","a@example-.test","a@127.0.0.1","а@example.test","a b@example.test"] {
            assert!(canonical_email(bad).is_err());
        }
        let longest=format!("{}@{}.{}.{}.{}","a".repeat(64),"b".repeat(63),"c".repeat(63),"d".repeat(58),"zz");
        assert_eq!(longest.len(),254);assert!(canonical_email(&longest).is_ok());
        assert!(canonical_email(&("a".to_owned()+&longest)).is_err());
        assert!(valid_native_nickname("Стальной_Ёж7"));assert!(valid_native_nickname(&"Я".repeat(24)));
        for bad in ["xy","bad-name","bad name","Ста\u{0301}ль","a\u{202e}b","😀😀😀"] {assert!(!valid_native_nickname(bad));}
        assert!(!valid_native_nickname(&"Я".repeat(25)));
    }
    #[test] fn http_boundary_rejects_truncation_chunking_and_ambiguous_lengths() {
        let good=b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 2\r\nConnection: close\r\n\r\n{}";
        assert_eq!(http_response(good).unwrap(),(401,b"{}".as_slice()));
        for n in 0..good.len() {assert!(http_response(&good[..n]).is_err());}
        assert!(http_response(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n{}").is_err());
        assert!(http_response(b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\nContent-Length: 2\r\n\r\n{}").is_err());
        assert!(http_response("HTTP/1.1 xxé\r\nContent-Length: 2\r\n\r\n{}".as_bytes()).is_err());
    }
    #[test] fn only_loopback_without_dns_and_unique_json_keys() {
        assert!(local_address("127.0.0.1:20020").is_ok());
        for bad in ["0.0.0.0:20020","192.0.2.1:20020","localhost:20020","127.0.0.1:0"] {assert!(local_address(bad).is_err());}
        assert!(object(br#"{"x":1,"x":2}"#,&["x"]).is_err());
        assert!(object(br#"{"x":1,"y":2}"#,&["x"]).is_err());
    }
    #[test] fn persisted_fixture_must_match_authenticated_account_and_native_mapping() {
        let epoch=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/unified-wire").join(format!("identity-{}-{epoch}",std::process::id()));
        fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();
        let account="12345678-1234-4234-8234-123456789abc";
        let profile=Profile {account_id:account.to_owned(),database_id:17,name:"own_user".to_owned(),fixture_dir:root.clone()};
        fs::write(root.join("manifest.json"),serde_json::to_vec(&serde_json::json!({"account_id":account,"native_database_id":17})).unwrap()).unwrap();
        let compatible=serde_json::json!({"account_id":account,"native_database_id":17,"client_name":"own_user"});
        fs::write(root.join("compatibility.json"),serde_json::to_vec(&compatible).unwrap()).unwrap();
        verify_fixture_identity(&profile).unwrap();
        let mut wrong=compatible;wrong["account_id"]=Value::String("12345678-1234-4234-8234-123456789abd".to_owned());
        fs::write(root.join("compatibility.json"),serde_json::to_vec(&wrong).unwrap()).unwrap();
        assert!(verify_fixture_identity(&profile).is_err());
        wrong["account_id"]=Value::String(account.to_owned());wrong["native_database_id"]=serde_json::json!(18);
        fs::write(root.join("compatibility.json"),serde_json::to_vec(&wrong).unwrap()).unwrap();
        assert!(verify_fixture_identity(&profile).is_err());
    }
}
