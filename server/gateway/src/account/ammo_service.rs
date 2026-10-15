//! P09D opt-in #717 native ammunition service boundary.
//!
//! Only the measured 16-INT32 CMD108 envelope is parsed. Account identity,
//! ownership, mounted descriptors, revision and stock stay authoritative in the
//! authenticated persistence adapter. This module has no storage side effects.
use std::{collections::BTreeMap,fs::File,io::{self,Read},path::Path};
use serde::{Deserialize,Deserializer,de::{self,MapAccess,Visitor}};
use serde_json::Value;
use sha2::{Digest,Sha256};

/// Preserve the measured short VAR1 method and short STRING length. Oversize
/// Mercury framing has not been verified on #717 and must never be guessed.
/// The backend must enforce this same bound BEFORE committing its delta.
pub const MAX_DELTA_BYTES:usize=240;
const CATALOG_SHA256:&str="9c50c64b85c6301e64145f9fbb90450417dc9063bcd8c136ac6de0c9cbabca62";

fn invalid(message:&'static str)->io::Error {
    io::Error::new(io::ErrorKind::InvalidData,message)
}

#[derive(Debug,Clone,Copy,PartialEq,Eq)]
pub struct Metadata {pub revision:u64,pub wire_revision:i64}

struct MetadataObject(BTreeMap<String,Value>);
impl<'de> Deserialize<'de> for MetadataObject {
    fn deserialize<D:Deserializer<'de>>(deserializer:D)->Result<Self,D::Error> {
        struct Fields;
        impl<'de> Visitor<'de> for Fields {
            type Value=MetadataObject;
            fn expecting(&self,f:&mut std::fmt::Formatter)->std::fmt::Result {f.write_str("unique primitive ammunition metadata")}
            fn visit_map<M:MapAccess<'de>>(self,mut map:M)->Result<MetadataObject,M::Error> {
                let mut values=BTreeMap::new();
                while let Some((key,value))=map.next_entry::<String,Value>()? {
                    if values.len()>=9 || value.is_array() || value.is_object() || values.insert(key,value).is_some() {
                        return Err(de::Error::custom("duplicate/large/nonprimitive ammunition metadata"));
                    }
                }
                Ok(MetadataObject(values))
            }
        }
        deserializer.deserialize_map(Fields)
    }
}

fn fixture_file(directory:&Path,name:&str,maximum:usize)->io::Result<Vec<u8>> {
    let root=directory.canonicalize()?;
    let path=directory.join(name).canonicalize()?;
    if !path.starts_with(&root) {return Err(invalid("ammo metadata escapes fixture"));}
    let file=File::open(path)?;
    if !file.metadata()?.is_file() || file.metadata()?.len()>maximum as u64 {
        return Err(invalid("ammo metadata file size/type"));
    }
    let mut bytes=Vec::new();file.take(maximum as u64+1).read_to_end(&mut bytes)?;
    if bytes.len()>maximum {return Err(invalid("ammo metadata grew beyond bound"));}
    Ok(bytes)
}

/// Bind the immutable service fixture to the authenticated account and exact
/// outgoing state bytes. The dossier loader separately verifies the original
/// granted cache payload and the matching v5 manifest/compatibility revisions.
pub fn metadata(directory:&Path,account_id:&str,database_id:i32)->io::Result<Metadata> {
    metadata_with_policy(directory,account_id,database_id,false)
}
pub fn metadata_research(directory:&Path,account_id:&str,database_id:i32)->io::Result<Metadata> {
    metadata_with_policy(directory,account_id,database_id,true)
}
fn metadata_with_policy(directory:&Path,account_id:&str,database_id:i32,research:bool)->io::Result<Metadata> {
    if database_id<=0 || account_id.len()!=36 || !account_id.bytes().enumerate().all(|(index,byte)| {
        if [8,13,18,23].contains(&index) {byte==b'-'} else {byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)}
    }) {return Err(invalid("ammo authenticated identity shape"));}
    let bytes=fixture_file(directory,"ammo-service.json",4096)?;
    let MetadataObject(values)=serde_json::from_slice(&bytes).map_err(|_|invalid("ammo metadata JSON"))?;
    let keys=["version","account_id","native_database_id","revision","wire_revision","catalog_sha256","state_sha256","purchases","battle"];
    if values.len()!=keys.len() || keys.iter().any(|key|!values.contains_key(*key)) {
        return Err(invalid("ammo metadata field contract"));
    }
    let revision=values["revision"].as_u64().ok_or_else(||invalid("ammo metadata revision type"))?;
    if values["version"].as_u64()!=Some(1) || values["account_id"].as_str()!=Some(account_id)
        || values["native_database_id"].as_i64()!=Some(database_id as i64)
        || !(5..=i32::MAX as u64).contains(&revision) || values["wire_revision"].as_i64()!=Some(1)
        || values["catalog_sha256"].as_str()!=Some(CATALOG_SHA256)
        || values["purchases"].as_bool()!=Some(false) || values["battle"].as_bool()!=Some(false) {
        return Err(invalid("ammo metadata identity/catalog/policy/revision binding"));
    }
    let state=fixture_file(directory,"state.bin",if research {crate::research_service091::MAX_STATE_BYTES}else {16384})?;
    if research {crate::hangar091::validate_research_state(&state)?;}else {crate::hangar091::validate_account_delta(&state)?;}
    let expected=format!("{:x}",Sha256::digest(&state));
    if values["state_sha256"].as_str()!=Some(expected.as_str()) {return Err(invalid("ammo metadata state digest"));}
    Ok(Metadata{revision,wire_revision:1})
}

#[derive(Debug,Clone,Copy,PartialEq,Eq)]
pub struct ShellCount {
    /// Signed original compact ID: negative means the native credits currency
    /// preference. Neither sign authorizes a purchase; only owned depot is used.
    pub compact_id:i32,
    pub count:u32,
}

#[derive(Debug,Clone,PartialEq,Eq)]
pub struct Request {
    pub id:i16,
    pub arguments:[i32;16],
}

impl Request {
    /// Decode only the bounded envelope. Unsupported semantic arguments remain
    /// available for a real native RES_NOT_AVAILABLE response, not disconnect.
    pub fn decode(payload:&[u8])->io::Result<Self> {
        if payload.len()!=72 {return Err(invalid("ammo command payload length"));}
        let id=i16::from_le_bytes([payload[0],payload[1]]);
        if id<=0 || payload[2..4]!=108i16.to_le_bytes()
            || payload[4..8]!=16u32.to_le_bytes() {
            return Err(invalid("ammo command envelope"));
        }
        let mut arguments=[0;16];
        for (target,bytes) in arguments.iter_mut().zip(payload[8..].chunks_exact(4)) {
            *target=i32::from_le_bytes(bytes.try_into().map_err(|_|invalid("ammo argument"))?);
        }
        Ok(Self{id,arguments})
    }

    pub fn shop_revision(&self)->i32 {self.arguments[0]}
    pub fn vehicle_inventory_id(&self)->i32 {self.arguments[1]}

    /// A narrow fixture-to-catalogue guard, not proof of vehicle ownership or
    /// installed gun. The persistence adapter must check those independently.
    pub fn layout(&self)->io::Result<[ShellCount;3]> {
        if self.id<=0 || self.shop_revision()<0 || self.arguments[2]!=6
            || self.arguments[9]!=6 || self.arguments[10..]!=[0;6] {
            return Err(invalid("unsupported ammo service layout"));
        }
        let (compatible,capacity)=match self.vehicle_inventory_id() {
            1=>([2570,2826,3082],96u32),
            2=>([14602,14858,15114],30u32),
            _=>return Err(invalid("unsupported ammo service vehicle")),
        };
        self.checked_layout(compatible,capacity)
    }

    /// P04M caller must first bind actual inventory -> curated mounted source.
    /// The legacy selector above retains its exact two-vehicle policy.
    pub(crate) fn layout_for_catalog(&self,compatible:[i32;3],capacity:u32,shop:i32)->io::Result<[ShellCount;3]> {
        if self.id<=0 || self.shop_revision()!=shop || self.arguments[2]!=6
            || self.arguments[9]!=6 || self.arguments[10..]!=[0;6] {return Err(invalid("pool ammo service layout/shop"));}
        self.checked_layout(compatible,capacity)
    }
    fn checked_layout(&self,compatible:[i32;3],capacity:u32)->io::Result<[ShellCount;3]> {
        let mut layout=[ShellCount{compact_id:0,count:0};3];
        let mut seen=[0;3];
        let mut total=0u32;
        for index in 0..3 {
            let compact_id=self.arguments[3+index*2];
            let unsigned=compact_id.checked_abs().ok_or_else(||invalid("ammo compact ID overflow"))?;
            let count=u32::try_from(self.arguments[4+index*2]).map_err(|_|invalid("negative ammo count"))?;
            if !compatible.contains(&unsigned) || seen[..index].contains(&unsigned) || count>capacity {
                return Err(invalid("incompatible or duplicate ammo/count"));
            }
            total=total.checked_add(count).ok_or_else(||invalid("ammo total overflow"))?;
            seen[index]=unsigned;
            layout[index]=ShellCount{compact_id,count};
        }
        if total>capacity {return Err(invalid("ammo capacity exceeded"));}
        Ok(layout)
    }

    pub fn validate_supported(&self)->io::Result<()> {self.layout().map(|_|())}
}

/// Source-bound candidate Account.update client slot28 / wire0x57. Actual
/// delivery remains a native acceptance gate. Validate and encode this response
/// before authorizing a backend commit, with the same bound enforced there.
/// Queue update before success so the original UI observes committed state.
pub fn response(id:i16,delta:&[u8])->io::Result<Vec<Vec<u8>>> {
    if id<=0 || delta.len()>MAX_DELTA_BYTES {return Err(invalid("ammo response ID/delta bound"));}
    crate::hangar091::validate_account_delta(delta)?;
    let mut update=vec![delta.len() as u8];
    update.extend(delta);
    let update=crate::hangar091::method(0x57,&update)?;
    Ok(vec![update,success_response(id)?])
}

pub fn success_response(id:i16)->io::Result<Vec<u8>> {
    if id<=0 {return Err(invalid("ammo response request ID"));}
    let mut payload=id.to_le_bytes().to_vec();
    payload.extend(0i16.to_le_bytes());
    payload.extend([0,4,0x80,2,b'}',b'.']);
    crate::hangar091::method(0x4d,&payload)
}

/// Revision-bearing no-change AccountSyncData response after a service update.
/// Session admission checks equality with the committed current revision.
pub fn refresh_response(id:i16,revision:i64)->io::Result<Vec<u8>> {
    if id<=0 || !(1..=i32::MAX as i64).contains(&revision) {
        return Err(invalid("ammo refresh ID/revision"));
    }
    let mut delta=b"\x80\x02}(U\x07prevRevJ".to_vec();
    delta.extend((revision as i32).to_le_bytes());
    delta.extend(b"U\x03revJ");
    delta.extend((revision as i32).to_le_bytes());
    delta.extend(b"u.");
    crate::hangar091::validate_account_delta(&delta)?;
    let mut payload=id.to_le_bytes().to_vec();
    payload.extend(0i16.to_le_bytes());
    payload.push(0);
    payload.push(delta.len() as u8);
    payload.extend(delta);
    crate::hangar091::method(0x4d,&payload)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::hangar091::{self,Incoming};

    fn request(vehicle:i32)->Request {
        let shells=if vehicle==1 {[2570,2826,3082]} else {[14602,14858,15114]};
        Request{id:226,arguments:[1,vehicle,6,shells[0],20,shells[1],0,shells[2],0,6,0,0,0,0,0,0]}
    }
    fn packet(request:&Request)->Vec<u8> {
        let mut bytes=vec![0x97,72,0];
        bytes.extend(request.id.to_le_bytes());bytes.extend(108i16.to_le_bytes());
        bytes.extend(16u32.to_le_bytes());
        for argument in request.arguments {bytes.extend(argument.to_le_bytes());}
        bytes
    }
    fn sync(id:i16,revision:i64,hash:i32)->Vec<u8> {
        let mut bytes=vec![0x8e,20,0];bytes.extend(id.to_le_bytes());bytes.extend(100i16.to_le_bytes());
        bytes.extend(revision.to_le_bytes());bytes.extend(hash.to_le_bytes());bytes.extend(0i32.to_le_bytes());bytes
    }

    #[test]
    fn actual_ms1_request_keeps_legacy_unavailable_and_requires_explicit_gate() {
        let request=request(1);let wire=packet(&request);
        assert_eq!(wire.len(),75);
        assert_eq!(&wire[..15],&[0x97,72,0,226,0,108,0,16,0,0,0,1,0,0,0]);
        assert_eq!(hangar091::requests_ammo_service(&wire).unwrap(),vec![Incoming::AmmoService(request.clone())]);
        assert!(hangar091::requests(&wire).is_err());
        assert_eq!(hangar091::requests_interactive(&wire).unwrap(),vec![Incoming::Unavailable{id:226,command:108,method:hangar091::CommandMethod::IntArray,argument_count:16}]);
        assert_eq!(request.layout().unwrap(),[ShellCount{compact_id:2570,count:20},ShellCount{compact_id:2826,count:0},ShellCount{compact_id:3082,count:0}]);
    }

    #[test]
    fn both_mounts_capacity_zero_load_signed_preferences_and_order() {
        for (vehicle,capacity) in [(1,96),(2,30)] {
            let mut request=request(vehicle);
            request.arguments[4]=capacity;assert!(request.validate_supported().is_ok());
            request.arguments[3] = -request.arguments[3];
            request.arguments[5] = -request.arguments[5];assert!(request.validate_supported().is_ok());
            request.arguments.swap(3,7);request.arguments.swap(4,8);
            let loaded=request.layout().unwrap();assert_eq!(loaded[2].count,capacity as u32);
            request.arguments[8]=0;assert!(request.validate_supported().is_ok());
            request.arguments[4]=capacity;request.arguments[6]=1;assert!(request.validate_supported().is_err());
        }
    }

    #[test]
    fn bounded_semantic_rejections_remain_native_commands() {
        for (offset,value) in [(0,-1),(1,0),(1,3),(2,5),(3,0),(3,14602),(3,i32::MIN),
            (4,-1),(4,97),(4,i32::MAX),(5,2570),(5,-2570),(6,96),(9,5),(10,1),(15,-1)] {
            let mut request=request(1);request.arguments[offset]=value;
            assert!(request.validate_supported().is_err(),"offset {offset} value {value}");
            assert_eq!(hangar091::requests_ammo_service(&packet(&request)).unwrap(),vec![Incoming::AmmoService(request)]);
        }
        let mut wrong=request(2);wrong.arguments[4]=31;assert!(wrong.validate_supported().is_err());
    }

    #[test]
    fn every_truncated_envelope_bad_header_and_tail_rejects_whole_bundle() {
        let wire=packet(&request(1));
        for end in 1..wire.len() {assert!(hangar091::requests_ammo_service(&wire[..end]).is_err(),"end {end}");}
        for offset in [0,1,2,4,5,6,7,8,9,10] {
            let mut bad=wire.clone();bad[offset]^=128;
            assert!(hangar091::requests_ammo_service(&bad).is_err(),"offset {offset}");
        }
        let mut bad=wire.clone();bad[3..5].fill(0);assert!(hangar091::requests_ammo_service(&bad).is_err());
        let mut bad=wire.clone();bad.push(0);assert!(hangar091::requests_ammo_service(&bad).is_err());
        assert!(hangar091::requests_ammo_service(&vec![0;513]).is_err());
        assert_eq!(hangar091::requests_ammo_service(&[]).unwrap(),vec![]);
    }

    #[test]
    fn account_request_id_collisions_reject_in_both_orders() {
        let ammo=packet(&request(1));
        let mut language=vec![0x95,7,0];language.extend(226i16.to_le_bytes());language.extend([0xe8,3,2,b'r',b'u']);
        for other in [ammo.clone(),sync(226,0,0),sync(226,4,1),language] {
            assert!(hangar091::requests_ammo_service(&[ammo.clone(),other.clone()].concat()).is_err());
            assert!(hangar091::requests_ammo_service(&[other,ammo.clone()].concat()).is_err());
        }
        let mut stats=vec![0x8e,20,0,202,0,245,1];stats.extend([0;16]);
        let mut request=request(1);request.id=202;let ammo=packet(&request);
        assert!(hangar091::requests_ammo_service(&[ammo.clone(),stats.clone()].concat()).is_err());
        assert!(hangar091::requests_ammo_service(&[stats,ammo].concat()).is_err());
    }

    #[test]
    fn distinct_service_bundle_and_dynamic_refresh_are_explicitly_opt_in() {
        let mut second=request(2);second.id=227;
        let wire=[packet(&request(1)),packet(&second),sync(228,3,-123)].concat();
        let rows=hangar091::requests_ammo_service(&wire).unwrap();assert_eq!(rows.len(),3);
        assert_eq!(rows[2],Incoming::AmmoRefresh{request:crate::account091::Request{id:228,command:100},revision:3,persistent_hash:-123});
        assert!(hangar091::requests_interactive(&wire).is_err());
        for revision in [1,i32::MAX as i64] {assert!(hangar091::requests_ammo_service(&sync(228,revision,0)).is_ok());}
        for revision in [-1,i32::MAX as i64+1,i64::MAX] {assert!(hangar091::requests_ammo_service(&sync(228,revision,0)).is_err());}
        let mut bad=sync(228,2,0);bad[19]=1;assert!(hangar091::requests_ammo_service(&bad).is_err());
    }

    #[test]
    fn exact_update_string_then_measured_success_shape() {
        let delta=b"\x80\x02}(U\x07prevRevK\x01U\x03revK\x02u.";
        let bodies=response(226,delta).unwrap();
        let mut expected=vec![0x13,0x57,delta.len() as u8+1,delta.len() as u8];expected.extend(delta);
        assert_eq!(bodies[0],expected);
        assert_eq!(bodies[1],vec![0x13,0x4d,10,226,0,0,0,0,4,0x80,2,b'}',b'.']);
        assert_eq!(success_response(226).unwrap(),bodies[1]);
    }

    #[test]
    fn outgoing_rejects_executable_pickle_bad_roots_tail_and_size_before_success() {
        for delta in [b"\x80\x02].".as_slice(),b"\x80\x02cfoo\nbar\n.",b"\x80\x02}.x",b"\x80\x02}(K\x01u.",b""] {
            assert!(response(226,delta).is_err());
        }
        // Structurally valid dictionaries exercise the exact measured cap.
        for length in [MAX_DELTA_BYTES,MAX_DELTA_BYTES+1] {
            let mut delta=b"\x80\x02}(K\x01U".to_vec();delta.push((length-10) as u8);
            delta.extend(vec![b'x';length-10]);delta.extend(b"u.");assert_eq!(delta.len(),length);
            assert_eq!(response(226,&delta).is_ok(),length==MAX_DELTA_BYTES);
        }
        for id in [0,-1,i16::MIN] {assert!(response(id,b"\x80\x02}.").is_err());assert!(success_response(id).is_err());}
    }

    #[test]
    fn no_change_refresh_carries_exact_committed_revision() {
        let wire=refresh_response(227,3).unwrap();
        assert_eq!(&wire[..9],&[0x13,0x4d,36,227,0,0,0,0,30]);
        assert_eq!(&wire[9..],b"\x80\x02}(U\x07prevRevJ\x03\x00\x00\x00U\x03revJ\x03\x00\x00\x00u.");
        for revision in [0,-1,i32::MAX as i64+1] {assert!(refresh_response(227,revision).is_err());}
        assert!(refresh_response(0,1).is_err());
        assert!(refresh_response(227,i32::MAX as i64).is_ok());
    }

    #[test]
    fn metadata_binds_identity_state_catalog_policy_and_bounded_revision() {
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let directory=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/p09d")
            .join(format!("metadata-{}-{stamp}",std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        let account="00000000-0000-0000-0000-000000000001";
        let state=b"\x80\x02}(U\x03revK\x01u.";
        std::fs::write(directory.join("state.bin"),state).unwrap();
        let value=serde_json::json!({"version":1,"account_id":account,"native_database_id":900001,
            "revision":5,"wire_revision":1,"catalog_sha256":CATALOG_SHA256,
            "state_sha256":format!("{:x}",Sha256::digest(state)),"purchases":false,"battle":false});
        let save=|value:&serde_json::Value|std::fs::write(directory.join("ammo-service.json"),serde_json::to_vec(value).unwrap()).unwrap();
        save(&value);assert_eq!(metadata(&directory,account,900001).unwrap(),Metadata{revision:5,wire_revision:1});
        assert!(metadata(&directory,account,900002).is_err());
        assert!(metadata(&directory,"00000000-0000-0000-0000-000000000002",900001).is_err());
        for (key,wrong) in [("version",serde_json::json!(2)),("revision",serde_json::json!(4)),
            ("revision",serde_json::json!(2147483648u64)),("revision",serde_json::json!(5.0)),
            ("wire_revision",serde_json::json!(2)),("purchases",serde_json::json!(true)),
            ("battle",serde_json::json!(0)),("catalog_sha256",serde_json::json!("0".repeat(64))),
            ("state_sha256",serde_json::json!("0".repeat(64))), ("extra",serde_json::json!(1))] {
            let mut wrong_value=value.clone();wrong_value[key]=wrong;save(&wrong_value);
            assert!(metadata(&directory,account,900001).is_err(),"key {key}");
        }
        for key in value.as_object().unwrap().keys() {
            let mut wrong=value.clone();wrong.as_object_mut().unwrap().remove(key);save(&wrong);
            assert!(metadata(&directory,account,900001).is_err(),"missing {key}");
        }
        let duplicate=serde_json::to_string(&value).unwrap().replace("\"version\":1","\"version\":1,\"version\":1");
        std::fs::write(directory.join("ammo-service.json"),duplicate).unwrap();assert!(metadata(&directory,account,900001).is_err());
        save(&value);std::fs::write(directory.join("state.bin"),b"\x80\x02}.").unwrap();assert!(metadata(&directory,account,900001).is_err());
        std::fs::write(directory.join("ammo-service.json"),vec![b' ';4097]).unwrap();assert!(metadata(&directory,account,900001).is_err());
    }
}
