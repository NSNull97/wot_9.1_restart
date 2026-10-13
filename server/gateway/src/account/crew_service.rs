//! P04D opt-in CMD309 boundary. No database, socket or worker lives here.
//!
//! Original #717 Account.def proves the argument widths and Shop proves their
//! order. The stable inherited method table gives candidate wire0x90; it is
//! INFERRED until an original client capture verifies it. Dispatch is permitted
//! only by the explicit test_lab crew_service flag, with ammunition service on.
use std::{collections::BTreeMap,fs::File,io::{self,Read},path::Path};
use serde::{Deserialize,Deserializer,de::{self,MapAccess,Visitor}};
use serde_json::Value;
use sha2::{Digest,Sha256};

pub const CANDIDATE_METHOD:u8=0x90;
pub const PAYLOAD_BYTES:usize=24;
pub const COMMAND:i16=309;
pub const POLICY_SHA256:&str="7d0e3d7ef28d85bfe32e4fcdea0547696a9b4fd04922a725a2d895e1395f0d55";
pub const SHOP_REVISION:i64=3;

fn invalid(message:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,message)}

#[derive(Debug,Clone,Copy,PartialEq,Eq)]
pub struct Metadata {
    pub revision:u64,pub wire_revision:i64,
    pub configuration_revision:u64,pub free_recruitment_left:u64,
}

pub(crate) struct MetadataObject(pub(crate) BTreeMap<String,Value>);
impl<'de> Deserialize<'de> for MetadataObject {
    fn deserialize<D:Deserializer<'de>>(deserializer:D)->Result<Self,D::Error> {
        struct Fields;
        impl<'de> Visitor<'de> for Fields {
            type Value=MetadataObject;
            fn expecting(&self,f:&mut std::fmt::Formatter)->std::fmt::Result {f.write_str("unique primitive crew metadata")}
            fn visit_map<M:MapAccess<'de>>(self,mut map:M)->Result<MetadataObject,M::Error> {
                let mut values=BTreeMap::new();
                while let Some((key,value))=map.next_entry::<String,Value>()? {
                    if values.len()>=14 || key.len()>64 || value.is_array() || value.is_object()
                        || value.as_str().is_some_and(|s|s.len()>128) || values.insert(key,value).is_some() {
                        return Err(de::Error::custom("duplicate/large/nonprimitive crew metadata"));
                    }
                }
                Ok(MetadataObject(values))
            }
        }
        deserializer.deserialize_map(Fields)
    }
}

pub(crate) fn identity(account_id:&str,database_id:i32)->io::Result<()> {
    if database_id<=0 || account_id.len()!=36 || !account_id.bytes().enumerate().all(|(index,byte)| {
        if [8,13,18,23].contains(&index) {byte==b'-'} else {byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)}
    }) {return Err(invalid("crew authenticated identity shape"));}
    Ok(())
}

pub(crate) fn fixture_file(directory:&Path,name:&str,maximum:usize)->io::Result<Vec<u8>> {
    let root=directory.canonicalize()?;
    let candidate=directory.join(name);
    if std::fs::symlink_metadata(&candidate)?.file_type().is_symlink() {
        return Err(invalid("crew fixture link forbidden"));
    }
    let path=candidate.canonicalize()?;
    if !path.starts_with(&root) {return Err(invalid("crew metadata escapes fixture"));}
    let file=File::open(path)?;
    if !file.metadata()?.is_file() || file.metadata()?.len()>maximum as u64 {return Err(invalid("crew metadata file size/type"));}
    let mut bytes=Vec::new();file.take(maximum as u64+1).read_to_end(&mut bytes)?;
    if bytes.len()>maximum {return Err(invalid("crew metadata grew beyond bound"));}Ok(bytes)
}

/// The caller first validates the ammunition fixture and its literal state.
/// This additional binding checks the same immutable state bytes, identity and
/// shared aggregate/wire cursors. It never creates a second service revision.
pub fn metadata(directory:&Path,account_id:&str,database_id:i32,
                shared_revision:u64,shared_wire_revision:i64)->io::Result<Metadata> {
    let bytes=fixture_file(directory,"crew-service.json",4096)?;
    let state=fixture_file(directory,"state.bin",16384)?;
    metadata_bytes(&bytes,&state,account_id,database_id,shared_revision,shared_wire_revision)
}

fn metadata_bytes(bytes:&[u8],state:&[u8],account_id:&str,database_id:i32,
                  shared_revision:u64,shared_wire_revision:i64)->io::Result<Metadata> {
    identity(account_id,database_id)?;
    if bytes.len()>4096 || state.len()>16384 || state.is_empty() {return Err(invalid("crew metadata/state bound"));}
    let MetadataObject(values)=serde_json::from_slice(bytes).map_err(|_|invalid("crew metadata JSON"))?;
    let keys=["version","account_id","native_database_id","revision","wire_revision","policy_sha256","state_sha256",
        "command","vehicle_inventory_id","slot","tariff_index","free_recruitment_left","configuration_revision","battle"];
    if values.len()!=keys.len() || keys.iter().any(|key|!values.contains_key(*key)) {return Err(invalid("crew metadata field contract"));}
    let revision=values["revision"].as_u64().ok_or_else(||invalid("crew metadata revision type"))?;
    let free=values["free_recruitment_left"].as_u64().ok_or_else(||invalid("crew quota type"))?;
    let configuration_revision=values["configuration_revision"].as_u64().ok_or_else(||invalid("crew configuration revision type"))?;
    if values["version"].as_u64()!=Some(1) || values["account_id"].as_str()!=Some(account_id)
        || values["native_database_id"].as_i64()!=Some(database_id as i64)
        || !(6..=i32::MAX as u64).contains(&revision) || revision!=shared_revision
        || values["wire_revision"].as_i64()!=Some(1) || shared_wire_revision!=1
        || values["policy_sha256"].as_str()!=Some(POLICY_SHA256)
        || values["command"].as_i64()!=Some(COMMAND as i64) || values["vehicle_inventory_id"].as_i64()!=Some(1)
        || values["slot"].as_i64()!=Some(1) || values["tariff_index"].as_i64()!=Some(0)
        || free>1 || configuration_revision!=2-free || values["battle"].as_bool()!=Some(false) {
        return Err(invalid("crew metadata identity/policy/shared revision binding"));
    }
    let expected=format!("{:x}",Sha256::digest(state));
    if values["state_sha256"].as_str()!=Some(expected.as_str()) {return Err(invalid("crew metadata state digest"));}
    Ok(Metadata{revision,wire_revision:1,configuration_revision,free_recruitment_left:free})
}

#[derive(Debug,Clone,Copy,PartialEq,Eq)]
pub struct Request {
    pub id:i16,pub shop_revision:i64,pub vehicle_inventory_id:i32,pub slot:i32,pub tariff_index:i32,
}

impl Request {
    /// Source-verified <hhqiii> payload. Native method framing is a separate
    /// whole-bundle check; no external mutation is allowed during this decode.
    pub fn decode(payload:&[u8])->io::Result<Self> {
        if payload.len()!=PAYLOAD_BYTES {return Err(invalid("crew command payload length"));}
        let id=i16::from_le_bytes([payload[0],payload[1]]);
        if id<=0 || payload[2..4]!=COMMAND.to_le_bytes() {return Err(invalid("crew command envelope"));}
        Ok(Self{id,shop_revision:i64::from_le_bytes(payload[4..12].try_into().map_err(|_|invalid("crew shop revision"))?),
            vehicle_inventory_id:i32::from_le_bytes(payload[12..16].try_into().map_err(|_|invalid("crew vehicle ID"))?),
            slot:i32::from_le_bytes(payload[16..20].try_into().map_err(|_|invalid("crew slot"))?),
            tariff_index:i32::from_le_bytes(payload[20..24].try_into().map_err(|_|invalid("crew tariff"))?)})
    }

    /// Narrow project test_lab selection, not ownership or persisted quota.
    /// Invalid semantics receive RES_NOT_AVAILABLE without a worker dispatch.
    pub fn validate_supported(&self)->io::Result<()> {self.validate_for(false)}
    pub fn validate_for(&self,roster:bool)->io::Result<()> {
        let seat=if roster {match self.vehicle_inventory_id {1=>(0..=1).contains(&self.slot),2=>(0..=4).contains(&self.slot),_=>false}}
            else {self.vehicle_inventory_id==1 && self.slot==1};
        if self.id<=0 || self.shop_revision!=SHOP_REVISION || !seat || self.tariff_index!=0 {
            return Err(invalid("unsupported crew service selection"));
        }
        Ok(())
    }

    pub fn layout(&self)->[i64;4] { [self.shop_revision,self.vehicle_inventory_id as i64,self.slot as i64,self.tariff_index as i64] }
}

/// Encode a bounded request for the existing authenticated loopback bridge.
/// Call only from the shared post-commit ammo/crew worker; this helper does not
/// send anything. Account/command key/revisions come from the server session.
pub fn service_request(account_id:&str,database_id:i32,command_key:&str,expected_revision:u64,
                       wire_revision:i64,request:Request)->io::Result<Vec<u8>> {
    service_request_for(false,account_id,database_id,command_key,expected_revision,wire_revision,request)
}
pub fn service_request_for(roster:bool,account_id:&str,database_id:i32,command_key:&str,expected_revision:u64,
                       wire_revision:i64,request:Request)->io::Result<Vec<u8>> {
    identity(account_id,database_id)?;request.validate_for(roster)?;
    if !((if roster {9}else {6})..i32::MAX as u64).contains(&expected_revision) || !(1..i32::MAX as i64).contains(&wire_revision)
        || !(1..=96).contains(&command_key.len())
        || !command_key.bytes().all(|b|b.is_ascii_alphanumeric() || b"-_:".contains(&b)) {
        return Err(invalid("crew request identity/revision/key boundary"));
    }
    let body=serde_json::to_vec(&serde_json::json!({"account_id":account_id,"native_database_id":database_id,
        "command_key":command_key,"expected_revision":expected_revision,"wire_revision":wire_revision,"layout":request.layout()}))
        .map_err(|_|invalid("crew request serialization"))?;
    if body.len()>2048 {return Err(invalid("crew request size"));}Ok(body)
}

#[cfg(test)]
mod tests {
    use super::*;
    const ACCOUNT:&str="00000000-0000-0000-0000-000000000001";
    const STATE:&[u8]=b"\x80\x02}."; // Literal codec fixture, not native acceptance.
    fn request()->Request {Request{id:226,shop_revision:3,vehicle_inventory_id:1,slot:1,tariff_index:0}}
    fn payload(request:Request)->Vec<u8> {
        let mut bytes=request.id.to_le_bytes().to_vec();bytes.extend(COMMAND.to_le_bytes());
        bytes.extend(request.shop_revision.to_le_bytes());bytes.extend(request.vehicle_inventory_id.to_le_bytes());
        bytes.extend(request.slot.to_le_bytes());bytes.extend(request.tariff_index.to_le_bytes());bytes
    }
    fn value()->Value {serde_json::json!({"version":1,"account_id":ACCOUNT,"native_database_id":900001,
        "revision":6,"wire_revision":1,"policy_sha256":POLICY_SHA256,"state_sha256":format!("{:x}",Sha256::digest(STATE)),
        "command":309,"vehicle_inventory_id":1,"slot":1,"tariff_index":0,"free_recruitment_left":1,
        "configuration_revision":1,"battle":false})}
    fn check(value:&Value)->io::Result<Metadata> {
        metadata_bytes(&serde_json::to_vec(value).unwrap(),STATE,ACCOUNT,900001,6,1)
    }

    #[test]
    fn native_source_width_order_and_signed_values_are_preserved() {
        let original=Request{id:32767,shop_revision:i64::MAX,vehicle_inventory_id:i32::MIN,slot:-1,tariff_index:i32::MAX};
        let raw=payload(original);assert_eq!(raw.len(),24);assert_eq!(raw[2..4],[53,1]);
        assert_eq!(Request::decode(&raw).unwrap(),original);
        assert!(original.validate_supported().is_err());assert!(request().validate_supported().is_ok());
    }

    #[test]
    fn malformed_envelopes_reject_without_partial_decode() {
        let raw=payload(request());
        for length in 0..raw.len() {assert!(Request::decode(&raw[..length]).is_err());}
        let mut trailing=raw.clone();trailing.push(0);assert!(Request::decode(&trailing).is_err());
        for id in [0,-1,i16::MIN] {let mut row=request();row.id=id;assert!(Request::decode(&payload(row)).is_err());}
        for cmd in [105i16,303,308,310,-1] {let mut bad=raw.clone();bad[2..4].copy_from_slice(&cmd.to_le_bytes());assert!(Request::decode(&bad).is_err());}
    }

    #[test]
    fn unsupported_semantics_survive_decode_but_cannot_dispatch() {
        for change in 0..6 {
            let mut row=request();match change {0=>row.shop_revision=1,1=>row.shop_revision=i64::MAX,
                2=>row.vehicle_inventory_id=2,3=>row.slot=0,4=>row.tariff_index=1,_=>row.tariff_index=2};
            let decoded=Request::decode(&payload(row)).unwrap();assert!(decoded.validate_supported().is_err());
            assert!(service_request(ACCOUNT,900001,"p04d:key:226",6,1,decoded).is_err());
        }
    }

    #[test]
    fn outgoing_request_has_closed_primitive_contract_and_exact_layout() {
        let bytes=service_request(ACCOUNT,900001,"p04d:key:226",6,1,request()).unwrap();
        let value:Value=serde_json::from_slice(&bytes).unwrap();assert_eq!(value.as_object().unwrap().len(),6);
        assert_eq!(value["layout"],serde_json::json!([3,1,1,0]));assert_eq!(value["expected_revision"],6);
        assert_eq!(value["wire_revision"],1);assert_eq!(value["account_id"],ACCOUNT);
        assert_eq!(bytes,service_request(ACCOUNT,900001,"p04d:key:226",6,1,request()).unwrap());
    }

    #[test]
    fn request_boundary_rejects_identity_key_revision_and_overflow() {
        for account in ["", "00000000-0000-0000-0000-00000000000A", "../account"] {
            assert!(service_request(account,900001,"key",6,1,request()).is_err());
        }
        for db in [0,-1,i32::MIN] {assert!(service_request(ACCOUNT,db,"key",6,1,request()).is_err());}
        for key in ["".to_owned(),"x".repeat(97),"a b".into(),"ключ".into(),"a\n".into()] {
            assert!(service_request(ACCOUNT,900001,&key,6,1,request()).is_err());
        }
        for rev in [0,5,i32::MAX as u64,u64::MAX] {assert!(service_request(ACCOUNT,900001,"key",rev,1,request()).is_err());}
        for rev in [-1,0,i32::MAX as i64,i64::MAX] {assert!(service_request(ACCOUNT,900001,"key",6,rev,request()).is_err());}
        assert!(service_request(ACCOUNT,i32::MAX,&"x".repeat(96),i32::MAX as u64-1,i32::MAX as i64-1,request()).is_ok());
    }

    #[test]
    fn metadata_binds_both_quota_states_to_shared_cursors_and_digest() {
        let mut row=value();assert_eq!(check(&row).unwrap(),Metadata{revision:6,wire_revision:1,configuration_revision:1,free_recruitment_left:1});
        row["free_recruitment_left"]=0.into();row["configuration_revision"]=2.into();assert!(check(&row).is_ok());
        let raw=serde_json::to_vec(&row).unwrap();
        for (revision,wire) in [(5,1),(7,1),(6,0),(6,2)] {assert!(metadata_bytes(&raw,STATE,ACCOUNT,900001,revision,wire).is_err());}
        assert!(metadata_bytes(&raw,b"\x80\x02} .",ACCOUNT,900001,6,1).is_err());
        assert!(metadata_bytes(&raw,STATE,ACCOUNT,900002,6,1).is_err());
    }

    #[test]
    fn metadata_rejects_every_policy_binding_or_field_change() {
        for (key,replacement) in [("version",Value::from(2)),("account_id",Value::from("00000000-0000-0000-0000-000000000002")),
            ("native_database_id",900002.into()),("revision",5.into()),("wire_revision",2.into()),("policy_sha256","0".repeat(64).into()),
            ("state_sha256","0".repeat(64).into()),("command",303.into()),("vehicle_inventory_id",2.into()),("slot",0.into()),
            ("tariff_index",1.into()),("free_recruitment_left",2.into()),("configuration_revision",2.into()),("battle",true.into())] {
            let mut row=value();row[key]=replacement;assert!(check(&row).is_err(),"{key}");
            let mut missing=value();missing.as_object_mut().unwrap().remove(key);assert!(check(&missing).is_err(),"missing {key}");
        }
        let mut extra=value();extra["extra"]=false.into();assert!(check(&extra).is_err());
    }

    #[test]
    fn metadata_rejects_float_bool_null_nested_duplicate_and_oversized_json() {
        for key in ["revision","version","wire_revision","configuration_revision","free_recruitment_left","command","slot"] {
            for replacement in [Value::from(true),Value::from(1.0),Value::Null,serde_json::json!({"value":1}),serde_json::json!([1])] {
                let mut row=value();row[key]=replacement;assert!(check(&row).is_err(),"{key}");
            }
        }
        let raw=serde_json::to_string(&value()).unwrap();
        let duplicate=format!("{{\"version\":1,{}",&raw[1..]);
        for malformed in [duplicate,format!("{raw}{{}}"),format!("{}0{}","[".repeat(130),"]".repeat(130))," ".repeat(4097),
            raw.replace("\"revision\":6","\"revision\":NaN")] {
            assert!(metadata_bytes(malformed.as_bytes(),STATE,ACCOUNT,900001,6,1).is_err());
        }
    }

    #[test]
    fn metadata_file_loader_is_bounded_and_does_not_mutate_inputs() {
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let directory=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/p04d")
            .join(format!("crew-metadata-{}-{stamp}",std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let raw=serde_json::to_vec(&value()).unwrap();std::fs::write(directory.join("crew-service.json"),&raw).unwrap();
        std::fs::write(directory.join("state.bin"),STATE).unwrap();
        assert!(metadata(&directory,ACCOUNT,900001,6,1).is_ok());
        assert_eq!(std::fs::read(directory.join("crew-service.json")).unwrap(),raw);
        assert_eq!(std::fs::read(directory.join("state.bin")).unwrap(),STATE);
        std::fs::write(directory.join("crew-service.json"),vec![b' ';4097]).unwrap();assert!(metadata(&directory,ACCOUNT,900001,6,1).is_err());
        std::fs::write(directory.join("crew-service.json"),raw).unwrap();
        std::fs::write(directory.join("state.bin"),vec![0;16385]).unwrap();assert!(metadata(&directory,ACCOUNT,900001,6,1).is_err());
    }

    #[test] fn roster_hires_derive_all_seats_and_reject_paid_or_unbound_requests() {
        for (vehicle,slots) in [(1,2),(2,5)] {for slot in 0..slots {
            let r=Request{vehicle_inventory_id:vehicle,slot,..request()};
            assert_eq!(Request::decode(&payload(r)).unwrap(),r);assert!(r.validate_for(true).is_ok());
            let raw=service_request_for(true,ACCOUNT,900001,"p04h:key:226",9,1,r).unwrap();
            let v:Value=serde_json::from_slice(&raw).unwrap();assert_eq!(v["layout"],serde_json::json!([3,vehicle,slot,0]));
            assert!(service_request_for(true,ACCOUNT,900001,"key",8,1,r).is_err());
        }}
        for r in [Request{vehicle_inventory_id:3,..request()},Request{slot:-1,..request()},
            Request{slot:2,..request()},Request{vehicle_inventory_id:2,slot:5,..request()},
            Request{tariff_index:1,..request()},Request{tariff_index:2,..request()},Request{shop_revision:4,..request()}] {
            assert!(r.validate_for(true).is_err());
        }
    }

}
