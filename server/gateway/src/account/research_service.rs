//! Explicit P09E original #717 research/shop boundary. Source signatures are
//! verified; this command family's native UI/wire acceptance remains NOT_RUN.
//! The shared account writer owns catalog, prices, inventory and transaction.
use std::{collections::BTreeMap,io,path::Path};
use serde::{Deserialize,Deserializer,de::{self,Visitor,MapAccess}};
use serde_json::Value;
use sha2::{Digest,Sha256};

pub const POLICY_SHA256:&str="46875923affb6bd307ad4d35397880fae1dd16fb1992ae2bfbfed607d132361c";
pub const CATALOG_SHA256:&str="b6baecd204444d1e894253fa6c19c61478993b8ae87c71373633989d3a8ee460";
pub const SHOP_REVISION:i64=5;
pub const MAX_STATE_BYTES:usize=32768;
pub const MAX_SHOP_BYTES:usize=32768;
pub const MAX_STATE_NODES:usize=32768;
pub const COMMANDS:[i16;5]=[101,201,301,302,308];
fn invalid(message:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,message)}

#[derive(Clone,Debug,PartialEq,Eq)]
pub struct Request {pub id:i16,pub command:i16,pub arguments:Vec<i64>}
impl Request {
    pub fn decode(method:u8,payload:&[u8])->io::Result<Self> {
        if payload.len()<4 || payload.len()>32 {return Err(invalid("research payload bound"));}
        let id=i16::from_le_bytes([payload[0],payload[1]]);
        let command=i16::from_le_bytes([payload[2],payload[3]]);
        if id<=0 {return Err(invalid("research request ID"));}
        let mut arguments=Vec::new();
        match (method,command,payload.len()) {
            (0x8e,101|201,20)|(0x90,301|302,24)=>{
                arguments.push(i64::from_le_bytes(payload[4..12].try_into().map_err(|_|invalid("research int64"))?));
                for raw in payload[12..].chunks_exact(4) {
                    arguments.push(i32::from_le_bytes(raw.try_into().map_err(|_|invalid("research int32"))?) as i64);
                }
            },
            (0x97,308,32)=>{
                if payload[4..8]!=6u32.to_le_bytes() {return Err(invalid("research array count"));}
                for raw in payload[8..].chunks_exact(4) {
                    arguments.push(i32::from_le_bytes(raw.try_into().map_err(|_|invalid("research array argument"))?) as i64);
                }
            },
            _=>return Err(invalid("research method/command/length")),
        }
        Ok(Self{id,command,arguments})
    }
    pub fn validate_supported(&self)->io::Result<()> {
        let positive=|value:i64|(1..=i32::MAX as i64).contains(&value);
        let nonnegative=|value:i64|(0..=i32::MAX as i64).contains(&value);
        let ok=self.id>0 && match (self.command,self.arguments.as_slice()) {
            (201,[vehicle,index,zero])=>positive(*vehicle) && (0..4096).contains(index) && *zero==0,
            (101,[vehicle,module,gun])=>positive(*vehicle) && positive(*module) && nonnegative(*gun),
            (301,[shop,vehicle,flags,tariff])=>*shop==SHOP_REVISION && positive(*vehicle) && *flags==0 && *tariff==-1,
            (302,[shop,module,count,gold])=>*shop==SHOP_REVISION && positive(*module) && (1..=100).contains(count) && *gold==0,
            (308,[shop,module,vehicle,slot,paid,gun])=>*shop==SHOP_REVISION && positive(*module) && positive(*vehicle)
                && *slot==0 && *paid==0 && nonnegative(*gun),
            _=>false,
        };
        if !ok {return Err(invalid("unsupported research options"));}Ok(())
    }
    pub fn vehicle_hint(&self)->i64 {
        match self.command {101|201=>self.arguments.first().copied().unwrap_or(0),301=>self.arguments.get(1).copied().unwrap_or(0),
            308=>self.arguments.get(2).copied().unwrap_or(0),_=>0}
    }
}

pub fn service_request(account:&str,database:i32,key:&str,revision:u64,wire:i64,request:&Request)->io::Result<Vec<u8>> {
    super::crew_service091::identity(account,database)?;request.validate_supported()?;
    if !(9..i32::MAX as u64).contains(&revision) || !(1..i32::MAX as i64).contains(&wire)
        || !(1..=96).contains(&key.len()) || !key.bytes().all(|b|b.is_ascii_alphanumeric() || b"-_:".contains(&b)) {
        return Err(invalid("research identity/revision/key boundary"));
    }
    let bytes=serde_json::to_vec(&serde_json::json!({"account_id":account,"native_database_id":database,"command_key":key,
        "expected_revision":revision,"wire_revision":wire,"command":request.command,"arguments":request.arguments}))
        .map_err(|_|invalid("research request encoding"))?;
    if bytes.len()>2048 {return Err(invalid("research request size"));}Ok(bytes)
}

struct Object(BTreeMap<String,Value>);
impl<'de> Deserialize<'de> for Object {
    fn deserialize<D:Deserializer<'de>>(d:D)->Result<Self,D::Error> {
        struct Fields;
        impl<'de> Visitor<'de> for Fields {
            type Value=Object;
            fn expecting(&self,f:&mut std::fmt::Formatter)->std::fmt::Result {f.write_str("unique bounded research metadata")}
            fn visit_map<M:MapAccess<'de>>(self,mut map:M)->Result<Object,M::Error> {
                let mut v=BTreeMap::new();
                while let Some((key,value))=map.next_entry::<String,Value>()? {
                    if v.len()>=11 || key.len()>64 || value.is_object() || (key!="commands" && value.is_array())
                        || value.as_str().is_some_and(|s|s.len()>128) || v.insert(key,value).is_some() {
                        return Err(de::Error::custom("duplicate/large research metadata"));
                    }
                }Ok(Object(v))
            }
        }d.deserialize_map(Fields)
    }
}

pub fn metadata(directory:&Path,account:&str,database:i32,revision:u64,wire:i64)->io::Result<String> {
    let read=super::crew_service091::fixture_file;
    let raw=read(directory,"research-service.json",4096)?;
    let state=read(directory,"state.bin",MAX_STATE_BYTES)?;
    let shop=read(directory,"shop.bin",MAX_SHOP_BYTES)?;
    metadata_bytes(&raw,&state,&shop,account,database,revision,wire)
}
fn metadata_bytes(raw:&[u8],state:&[u8],shop:&[u8],account:&str,database:i32,revision:u64,wire:i64)->io::Result<String> {
    super::crew_service091::identity(account,database)?;
    if raw.len()>4096 || state.len()>MAX_STATE_BYTES || shop.len()>MAX_SHOP_BYTES {return Err(invalid("research metadata size"));}
    let Object(v)=serde_json::from_slice(raw).map_err(|_|invalid("research metadata JSON"))?;
    let keys=["version","account_id","native_database_id","revision","wire_revision","policy_sha256","catalog_sha256","state_sha256","shop_sha256","commands","battle"];
    if v.len()!=keys.len() || keys.iter().any(|k|!v.contains_key(*k)) {return Err(invalid("research metadata fields"));}
    let catalog=v["catalog_sha256"].as_str().ok_or_else(||invalid("research catalog digest type"))?;
    if v["version"].as_u64()!=Some(1) || v["account_id"].as_str()!=Some(account) || v["native_database_id"].as_i64()!=Some(database as i64)
        || !(9..=i32::MAX as u64).contains(&revision) || v["revision"].as_u64()!=Some(revision) || wire!=1
        || v["wire_revision"].as_i64()!=Some(wire) || v["policy_sha256"].as_str()!=Some(POLICY_SHA256)
        || v["commands"]!=serde_json::json!(COMMANDS) || v["battle"].as_bool()!=Some(false)
        || catalog!=CATALOG_SHA256
        || v["state_sha256"].as_str()!=Some(format!("{:x}",Sha256::digest(state)).as_str())
        || v["shop_sha256"].as_str()!=Some(format!("{:x}",Sha256::digest(shop)).as_str()) {
        return Err(invalid("research metadata identity/policy/hash/revision"));
    }
    crate::hangar091::validate_research_state(state)?;
    crate::hangar091::validate_research_shop(shop)?;
    Ok(catalog.to_owned())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn packet(command:i16)->(u8,Vec<u8>) {
        let (method,args):(u8,Vec<i64>)=match command {101=>(0x8e,vec![1,6658,0]),201=>(0x8e,vec![3329,1,0]),
            301=>(0x90,vec![SHOP_REVISION,1,0,-1]),302=>(0x90,vec![SHOP_REVISION,6658,1,0]),308=>(0x97,vec![SHOP_REVISION,6658,1,0,0,0]),_=>unreachable!()};
        let mut bytes=226i16.to_le_bytes().to_vec();bytes.extend(command.to_le_bytes());
        if method==0x97 {bytes.extend(6u32.to_le_bytes());for a in args {bytes.extend((a as i32).to_le_bytes());}}
        else {bytes.extend(args[0].to_le_bytes());for a in &args[1..] {bytes.extend((*a as i32).to_le_bytes());}}
        (method,bytes)
    }
    #[test] fn exact_source_shapes_and_semantic_options() {
        for command in COMMANDS {
            let (method,bytes)=packet(command);let r=Request::decode(method,&bytes).unwrap();
            assert_eq!(r.command,command);assert!(r.validate_supported().is_ok());
            let mut bad=r.clone();bad.arguments.push(0);assert!(bad.validate_supported().is_err());
            for end in 0..bytes.len() {assert!(Request::decode(method,&bytes[..end]).is_err());}
            let mut bad=bytes.clone();bad.push(0);assert!(Request::decode(method,&bad).is_err());
        }
    }
    #[test] fn signed_widths_survive_decode_but_unsupported_cannot_dispatch() {
        let (method,mut raw)=packet(201);raw[4..12].copy_from_slice(&i64::MAX.to_le_bytes());raw[12..16].copy_from_slice(&i32::MIN.to_le_bytes());
        let r=Request::decode(method,&raw).unwrap();assert_eq!(r.arguments,[i64::MAX,i32::MIN as i64,0]);assert!(r.validate_supported().is_err());
        for (command,index,value) in [(301,2,1),(301,2,16),(301,3,0),(301,3,1),(301,3,2),(301,0,4),(302,0,3),(302,0,4),(302,2,101),(302,3,1),(308,3,1),(308,4,1),(201,1,4096)] {
            let (method,raw)=packet(command);let mut r=Request::decode(method,&raw).unwrap();r.arguments[index]=value;assert!(r.validate_supported().is_err());
        }
    }
    #[test] fn malformed_method_count_id_and_command_fail() {
        for command in COMMANDS {
            let (method,raw)=packet(command);let mut b=raw.clone();b[0..2].copy_from_slice(&0i16.to_le_bytes());assert!(Request::decode(method,&b).is_err());
            let mut b=raw.clone();b[2..4].copy_from_slice(&309i16.to_le_bytes());assert!(Request::decode(method,&b).is_err());
            assert!(Request::decode(0x91,&raw).is_err());
        }
        let (method,mut raw)=packet(308);raw[4..8].copy_from_slice(&u32::MAX.to_le_bytes());assert!(Request::decode(method,&raw).is_err());
    }
    #[test] fn service_request_has_original_command_and_closed_authenticated_fields() {
        let (method,raw)=packet(201);let request=Request::decode(method,&raw).unwrap();
        let bytes=service_request("00000000-0000-0000-0000-000000000001",900001,"p09e:abc:226",9,1,&request).unwrap();
        let v:Value=serde_json::from_slice(&bytes).unwrap();assert_eq!(v.as_object().unwrap().len(),7);assert_eq!(v["command"],201);
        assert_eq!(v["arguments"],serde_json::json!([3329,1,0]));
        assert!(service_request("bad",900001,"p09e:key",9,1,&request).is_err());
    }
    #[test] fn mixed_account_bundle_rejects_reused_ids_and_preserves_legacy_opt_in() {
        for command in COMMANDS {
            let (method,payload)=packet(command);let mut wire=vec![method];wire.extend((payload.len() as u16).to_le_bytes());wire.extend(payload);
            assert!(crate::hangar091::refused(crate::hangar091::requests_interactive(&wire)));
            assert_eq!(crate::hangar091::requests_research_service(&wire).unwrap().len(),1);
            assert!(crate::hangar091::requests_research_service(&[wire.clone(),wire].concat()).is_err());
        }
        let (method,payload)=packet(201);let mut first=vec![method];first.extend(20u16.to_le_bytes());first.extend(payload);
        let mut sync=vec![0x8e,20,0];sync.extend(226i16.to_le_bytes());sync.extend(100i16.to_le_bytes());sync.extend([0;16]);
        for raw in [[first.clone(),sync.clone()].concat(),[sync,first].concat()] {
            assert!(crate::hangar091::requests_research_service(&raw).is_err());
        }
    }
    #[test] fn metadata_requires_exact_policy_identity_hashes_and_no_duplicate_fields() {
        let account="00000000-0000-0000-0000-000000000001";let state=b"\x80\x02}.";let shop=state;
        let value=serde_json::json!({"version":1,"account_id":account,"native_database_id":900001,"revision":9,
            "wire_revision":1,"policy_sha256":POLICY_SHA256,"catalog_sha256":CATALOG_SHA256,
            "state_sha256":format!("{:x}",Sha256::digest(state)),"shop_sha256":format!("{:x}",Sha256::digest(shop)),
            "commands":COMMANDS,"battle":false});
        let check=|v:&Value|metadata_bytes(&serde_json::to_vec(v).unwrap(),state,shop,account,900001,9,1);
        assert!(check(&value).is_ok());
        for (key,bad) in [("version",serde_json::json!(2)),("revision",serde_json::json!(8)),("wire_revision",serde_json::json!(2)),
            ("policy_sha256",serde_json::json!("x")),("battle",serde_json::json!(true)),("catalog_sha256",serde_json::json!([])),("catalog_sha256",serde_json::json!("a".repeat(64))),
            ("commands",serde_json::json!([201])),("state_sha256",serde_json::json!("0".repeat(64)))] {
            let mut v=value.clone();v[key]=bad;assert!(check(&v).is_err(),"{key}");
        }
        let mut bytes=serde_json::to_vec(&value).unwrap();bytes.pop();bytes.extend(b",\"version\":1}");
        assert!(metadata_bytes(&bytes,state,shop,account,900001,9,1).is_err());
        assert!(metadata_bytes(&serde_json::to_vec(&value).unwrap(),state,b"bad",account,900001,9,1).is_err());
    }
}
