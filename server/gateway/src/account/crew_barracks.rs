//! Original #717 CMD303. This codec admits only the frozen free50 project catalog.
use std::{io,path::Path};
use sha2::{Digest,Sha256};

pub const CANDIDATE_METHOD:u8=0x90;
pub const PAYLOAD_BYTES:usize=24;
pub const COMMAND:i16=303;
pub const SHOP_REVISION:i64=3;
pub const SHOP_SHA256:&str="b55573c5b14fbbc034fbc2091d9e381645926c67e561ab46917ecd3d6965129a";
fn invalid(message:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,message)}

pub fn shop(directory:&Path)->io::Result<()> {
    let bytes=super::crew_service091::fixture_file(directory,"shop.bin",16384)?;
    if format!("{:x}",Sha256::digest(&bytes))!=SHOP_SHA256 {return Err(invalid("barracks shop fixture binding"));}
    Ok(())
}

#[derive(Debug,Clone,Copy,PartialEq,Eq)]
pub struct Request {pub id:i16,pub shop_revision:i64,pub vehicle_type:i32,pub role:i32,pub cost:i32}
impl Request {
    pub fn decode(payload:&[u8])->io::Result<Self> {
        if payload.len()!=PAYLOAD_BYTES {return Err(invalid("barracks payload length"));}
        let id=i16::from_le_bytes([payload[0],payload[1]]);
        if id<=0 || payload[2..4]!=COMMAND.to_le_bytes() {return Err(invalid("barracks envelope"));}
        Ok(Self{id,shop_revision:i64::from_le_bytes(payload[4..12].try_into().map_err(|_|invalid("barracks shop"))?),
            vehicle_type:i32::from_le_bytes(payload[12..16].try_into().map_err(|_|invalid("barracks vehicle type"))?),
            role:i32::from_le_bytes(payload[16..20].try_into().map_err(|_|invalid("barracks role"))?),
            cost:i32::from_le_bytes(payload[20..24].try_into().map_err(|_|invalid("barracks cost"))?)})
    }
    pub fn validate_supported(&self)->io::Result<()> {
        let role=match self.vehicle_type {3329=>matches!(self.role,1|3),7169=>matches!(self.role,1|3|4|5),_=>false};
        if self.id<=0 || self.shop_revision!=SHOP_REVISION || !role || self.cost!=0 {return Err(invalid("unsupported barracks layout"));}
        Ok(())
    }
    pub fn layout(&self)->[i64;4] {[self.shop_revision,self.vehicle_type as i64,self.role as i64,self.cost as i64]}
}
pub fn service_request(account_id:&str,database_id:i32,key:&str,revision:u64,wire:i64,request:Request)->io::Result<Vec<u8>> {
    super::crew_service091::identity(account_id,database_id)?;request.validate_supported()?;
    if !(12..i32::MAX as u64).contains(&revision) || !(1..i32::MAX as i64).contains(&wire)
        || !(1..=96).contains(&key.len()) || !key.bytes().all(|b|b.is_ascii_alphanumeric() || b"-_:".contains(&b)) {
        return Err(invalid("barracks service identity/cursor/key"));
    }
    let raw=serde_json::to_vec(&serde_json::json!({"account_id":account_id,"native_database_id":database_id,
        "command_key":key,"expected_revision":revision,"wire_revision":wire,"layout":request.layout()}))
        .map_err(|_|invalid("barracks service encoding"))?;
    if raw.len()>2048 {return Err(invalid("barracks service size"));}Ok(raw)
}

/// A typed result; there is no generic client-supplied pickle/object extension.
#[derive(Debug,Clone,PartialEq,Eq)]
pub struct Recruitment {pub tankman_id:u8,pub descriptor:[u8;25]}
impl Recruitment {
    pub fn validate(&self,request:Request)->io::Result<()> {
        request.validate_supported()?;
        if !(4..=16).contains(&self.tankman_id) {return Err(invalid("barracks response identity"));}
        // Exact H free50 allocation passport, not arbitrary serialized descriptor.
        let id=self.tankman_id;
        let expected=[8,(request.vehicle_type>>8) as u8,request.role as u8,50,0,0,0,
            id,0,id,0,id,0,0x40,6,0,0,0,0,66,0,0,0,0,0];
        if self.descriptor!=expected {return Err(invalid("barracks response descriptor/request/passport"));}
        Ok(())
    }
    pub fn validate_delta(&self,request:Request,wire:i64,delta:&[u8])->io::Result<()> {
        self.validate(request)?;
        if !(1..i32::MAX as i64).contains(&wire) {return Err(invalid("barracks response wire bound"));}
        if delta!=self.delta(wire as i32) {return Err(invalid("barracks response delta/ext/allocator binding"));}
        crate::hangar091::validate_account_delta(delta)
    }
    fn delta(&self,wire:i32)->Vec<u8> {
        let mut out=b"\x80\x02}(U\x07prevRev".to_vec();integer(&mut out,wire);
        out.extend(b"U\x03rev");integer(&mut out,wire+1);
        out.extend(b"U\x09inventory}(K\x08}(U\x09compDescr}(K");out.push(self.tankman_id);
        out.extend(b"U\x19");out.extend(self.descriptor);
        out.extend(b"uU\x07vehicle}(K");out.push(self.tankman_id);
        out.extend(b"J\xff\xff\xff\xffuuuU\x05stats}(U\x0cfreeTMenLeftK");
        out.push(16-self.tankman_id);out.extend(b"uu.");out
    }
    pub fn success_response(&self,id:i16)->io::Result<Vec<u8>> {
        if id<=0 || !(4..=16).contains(&self.tankman_id) {return Err(invalid("barracks success request/identity"));}
        let mut ext=b"\x80\x02}(U\x09tmanInvIDK".to_vec();ext.push(self.tankman_id);
        ext.extend(b"U\x0dtmanCompDescrU\x19");ext.extend(self.descriptor);ext.extend(b"u.");
        let mut payload=id.to_le_bytes().to_vec();payload.extend(0i16.to_le_bytes());
        payload.push(0);payload.push(ext.len() as u8);payload.extend(ext);
        crate::hangar091::method(0x4d,&payload)
    }
}
fn integer(out:&mut Vec<u8>,value:i32) {
    if (0..=255).contains(&value) {out.extend([b'K',value as u8]);}
    else if (0..=65535).contains(&value) {out.push(b'M');out.extend((value as u16).to_le_bytes());}
    else {out.push(b'J');out.extend(value.to_le_bytes());}
}

#[cfg(test)]
mod tests {
    use super::*;
    pub fn request()->Request {Request{id:226,shop_revision:3,vehicle_type:7169,role:4,cost:0}}
    pub fn recruit()->Recruitment {Recruitment{tankman_id:12,descriptor:[8,28,4,50,0,0,0,12,0,12,0,12,0,64,6,0,0,0,0,66,0,0,0,0,0]}}
    fn bytes(r:Request)->Vec<u8> {let mut b=r.id.to_le_bytes().to_vec();b.extend(COMMAND.to_le_bytes());
        b.extend(r.shop_revision.to_le_bytes());b.extend(r.vehicle_type.to_le_bytes());b.extend(r.role.to_le_bytes());b.extend(r.cost.to_le_bytes());b}
    #[test] fn source_widths_catalog_and_exact_bridge_fields() {
        let r=request();assert_eq!(Request::decode(&bytes(r)).unwrap(),r);
        let v:serde_json::Value=serde_json::from_slice(&service_request("00000000-0000-0000-0000-000000000001",900001,"p04k:k:226",56,1,r).unwrap()).unwrap();
        assert_eq!(v.as_object().unwrap().len(),6);assert_eq!(v["layout"],serde_json::json!([3,7169,4,0]));
        let extremes=Request{shop_revision:i64::MAX,vehicle_type:i32::MAX,role:i32::MIN,cost:i32::MAX,..r};
        assert_eq!(Request::decode(&bytes(extremes)).unwrap(),extremes);assert!(extremes.validate_supported().is_err());
        for n in 0..24 {assert!(Request::decode(&bytes(r)[..n]).is_err());}
        let mut trailing=bytes(r);trailing.push(0);assert!(Request::decode(&trailing).is_err());
        for value in [Request{id:0,..r},Request{shop_revision:0,..r},Request{shop_revision:4,..r},
            Request{vehicle_type:1,..r},Request{vehicle_type:7170,..r},Request{vehicle_type:3329,..r},
            Request{role:2,..r},Request{cost:1,..r},Request{cost:-1,..r}] {assert!(value.validate_supported().is_err());}
    }
    #[test] fn exact_result_binds_descriptor_delta_and_allocator_quota() {
        let r=request();let member=recruit();
        for wire in [1,255,256,65535,65536,i32::MAX-1] {
            let delta=member.delta(wire);assert!(member.validate_delta(r,wire as i64,&delta).is_ok());
            for index in 0..delta.len() {let mut bad=delta.clone();bad[index]^=1;assert!(member.validate_delta(r,wire as i64,&bad).is_err());}
        }
        for index in 0..25 {let mut bad=member.clone();bad.descriptor[index]^=1;assert!(bad.validate(r).is_err());}
        assert!(member.validate(Request{role:5,..r}).is_err());
        assert_eq!(member.delta(1).len(),131);assert_eq!(member.success_response(226).unwrap()[1],0x4d);
        let full=member.success_response(226).unwrap();assert_eq!(full[8],61);
        assert!(member.validate_delta(r,0,&member.delta(1)).is_err());
    }
    #[test] fn native_command_framing_and_cross_kind_collisions_require_opt_in() {
        let b=bytes(request());let mut packet=vec![0x90,24,0];packet.extend(b);
        assert!(crate::hangar091::requests_crew_dismissal(&packet).is_err());
        assert!(matches!(crate::hangar091::requests_crew_barracks(&packet).unwrap().as_slice(),[crate::hangar091::Incoming::CrewBarracks(_)]));
        let mut twice=packet.clone();twice.extend(&packet);assert!(crate::hangar091::requests_crew_barracks(&twice).is_err());
        let mut other=vec![0x8e,20,0];other.extend(226i16.to_le_bytes());other.extend(306i16.to_le_bytes());other.extend(3i64.to_le_bytes());other.extend([0;8]);
        let mut mixed=packet;mixed.extend(other);assert!(crate::hangar091::requests_crew_barracks(&mixed).is_err());
    }
}
