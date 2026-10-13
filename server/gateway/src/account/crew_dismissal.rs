//! Original #717 CMD306 / doCmdInt3. Ownership, reservation and terminal
//! identity history are validated by the authoritative account writer.
use std::io;

pub const CANDIDATE_METHOD:u8=0x8e;
pub const PAYLOAD_BYTES:usize=20;
pub const COMMAND:i16=306;
fn invalid(message:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,message)}

#[derive(Debug,Clone,Copy,PartialEq,Eq)]
pub struct Request {pub id:i16,pub tankman_inventory_id:i64,pub reserved_a:i32,pub reserved_b:i32}
impl Request {
    pub fn decode(payload:&[u8])->io::Result<Self> {
        if payload.len()!=PAYLOAD_BYTES {return Err(invalid("dismissal payload length"));}
        let id=i16::from_le_bytes([payload[0],payload[1]]);
        if id<=0 || payload[2..4]!=COMMAND.to_le_bytes() {return Err(invalid("dismissal envelope"));}
        Ok(Self{id,tankman_inventory_id:i64::from_le_bytes(payload[4..12].try_into().map_err(|_|invalid("dismissal member"))?),
            reserved_a:i32::from_le_bytes(payload[12..16].try_into().map_err(|_|invalid("dismissal reserved a"))?),
            reserved_b:i32::from_le_bytes(payload[16..20].try_into().map_err(|_|invalid("dismissal reserved b"))?)})
    }
    pub fn validate_supported(&self)->io::Result<()> {
        if self.id<=0 || !(1..=16).contains(&self.tankman_inventory_id) || self.reserved_a!=0 || self.reserved_b!=0 {
            return Err(invalid("unsupported dismissal layout"));
        } Ok(())
    }
    pub fn layout(&self)->[i64;3] {[self.tankman_inventory_id,self.reserved_a as i64,self.reserved_b as i64]}
}
pub fn service_request(account_id:&str,database_id:i32,key:&str,revision:u64,wire:i64,request:Request)->io::Result<Vec<u8>> {
    super::crew_service091::identity(account_id,database_id)?;request.validate_supported()?;
    if !(11..i32::MAX as u64).contains(&revision) || !(1..i32::MAX as i64).contains(&wire)
        || !(1..=96).contains(&key.len()) || !key.bytes().all(|b|b.is_ascii_alphanumeric() || b"-_:".contains(&b)) {
        return Err(invalid("dismissal service identity/cursor/key"));
    }
    let raw=serde_json::to_vec(&serde_json::json!({"account_id":account_id,"native_database_id":database_id,
        "command_key":key,"expected_revision":revision,"wire_revision":wire,"layout":request.layout()}))
        .map_err(|_|invalid("dismissal service encoding"))?;
    if raw.len()>2048 {return Err(invalid("dismissal service size"));}Ok(raw)
}

#[cfg(test)]
mod tests {
    use super::*;
    const ACCOUNT:&str="00000000-0000-0000-0000-000000000001";
    fn request()->Request {Request{id:226,tankman_inventory_id:3,reserved_a:0,reserved_b:0}}
    fn bytes(r:Request)->Vec<u8> {let mut b=r.id.to_le_bytes().to_vec();b.extend(COMMAND.to_le_bytes());
        b.extend(r.tankman_inventory_id.to_le_bytes());b.extend(r.reserved_a.to_le_bytes());b.extend(r.reserved_b.to_le_bytes());b}
    #[test] fn exact_signed_envelope_and_closed_bridge_layout() {
        let r=request();assert_eq!(Request::decode(&bytes(r)).unwrap(),r);
        let raw=service_request(ACCOUNT,900001,"p04j:key:226",49,1,r).unwrap();
        let v:serde_json::Value=serde_json::from_slice(&raw).unwrap();
        assert_eq!(v.as_object().unwrap().len(),6);assert_eq!(v["layout"],serde_json::json!([3,0,0]));
        let r=Request{tankman_inventory_id:i64::MAX,reserved_a:i32::MIN,reserved_b:i32::MAX,..r};
        assert_eq!(Request::decode(&bytes(r)).unwrap(),r);assert!(r.validate_supported().is_err());
    }
    #[test] fn malformed_and_absent_identity_requests_cannot_dispatch() {
        let b=bytes(request());for n in 0..20 {assert!(Request::decode(&b[..n]).is_err());}
        let mut trailing=b.clone();trailing.push(0);assert!(Request::decode(&trailing).is_err());
        for id in [0,-1] {assert!(Request::decode(&bytes(Request{id,..request()})).is_err());}
        for cmd in [105i16,151,152,153,309] {let mut b=b.clone();b[2..4].copy_from_slice(&cmd.to_le_bytes());assert!(Request::decode(&b).is_err());}
        for r in [Request{tankman_inventory_id:0,..request()},Request{tankman_inventory_id:17,..request()},
            Request{reserved_a:1,..request()},Request{reserved_b:1,..request()}] {
            assert!(r.validate_supported().is_err());assert!(service_request(ACCOUNT,900001,"k",11,1,r).is_err());
        }
        for rev in [0,10,i32::MAX as u64,u64::MAX] {assert!(service_request(ACCOUNT,900001,"k",rev,1,request()).is_err());}
        for wire in [-1,0,i32::MAX as i64] {assert!(service_request(ACCOUNT,900001,"k",11,wire,request()).is_err());}
        for key in ["", "a b", "\n", "ключ"] {assert!(service_request(ACCOUNT,900001,key,11,1,request()).is_err());}
    }
}
