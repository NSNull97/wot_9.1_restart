//! Versioned outgoing Account service policy for the ordinary own map drive.
//! The accepted r4 fixture/DB/VehicleSeed remain immutable. This projection
//! declares CAPTCHA unnecessary for test_lab; it never answers a challenge or
//! alters the original native controller/decorator. See R/wire/captcha-policy-design-01.
use std::io;
use sha2::{Digest,Sha256};
use crate::{account091::Request,hangar091::Fixtures,identity091::Profile};

pub const POLICY_VERSION:u8=1;
pub const OUTGOING_STATE_SHA256:&str="138c21ed9063b36e30ca5995d6d200045c3db99dc9d54f4dc70fd34b94f58698";
const STATE_BYTES:usize=1329;
const VALUE_OFFSET:usize=802;
const ORIGINAL_FIELD:&[u8]=b"U\x12battlesTillCaptchaK\x00";

fn invalid()->io::Error {io::Error::new(io::ErrorKind::InvalidData,"unverified ordinary Account service policy")}
fn hex(value:&[u8])->String {value.iter().map(|byte|format!("{byte:02x}")).collect()}

#[derive(Debug,Clone,PartialEq,Eq)]
pub(crate) struct AccountPolicy {
    source_sha256:[u8;32],
    outgoing:Vec<u8>,
}

impl AccountPolicy {
    /// Only the supported primary gets this projection. Other authenticated
    /// accounts retain their old Hangar bytes and existing drive-entry refusal.
    /// An incompatible primary is an error BEFORE publishing its Session.
    pub(crate) fn for_mode(ordinary:bool,identity:&Profile,fixtures:&Fixtures)->io::Result<Option<Self>> {
        if !ordinary || identity.account_id!=crate::arena_vehicle091::PRIMARY_ACCOUNT {return Ok(None);}
        Self::prepare(identity,fixtures).map(Some)
    }

    fn prepare(identity:&Profile,fixtures:&Fixtures)->io::Result<Self> {
        // This unchanged loader pins the primary UUID/profile4/HP/descriptor,
        // manifest/compatibility and original raw state, never the projected SHA.
        crate::arena_vehicle091::load(identity,fixtures.state_sha256())?;
        let outgoing=project_state(fixtures.state_bytes())?;
        let policy=Self {source_sha256:fixtures.state_sha256(),outgoing};
        policy.validate(identity,fixtures)?;Ok(policy)
    }

    pub(crate) fn validate(&self,identity:&Profile,fixtures:&Fixtures)->io::Result<()> {
        if identity.account_id!=crate::arena_vehicle091::PRIMARY_ACCOUNT || identity.database_id!=1
            || identity.name!=crate::arena_vehicle091::PRIMARY_NAME
            || hex(&self.source_sha256)!=crate::arena_vehicle091::PRIMARY_STATE_SHA256
            || fixtures.state_sha256()!=self.source_sha256
            || self.outgoing.len()!=STATE_BYTES
            || hex(&Sha256::digest(&self.outgoing))!=OUTGOING_STATE_SHA256 {return Err(invalid());}
        Ok(())
    }

    pub(crate) fn response(&self,request:&Request,identity:&Profile,fixtures:&Fixtures)->io::Result<Vec<Vec<u8>>> {
        self.validate(identity,fixtures)?;
        crate::hangar091::response_state(request,&self.outgoing)
    }

    pub(crate) fn binding_event(&self,session:u32)->String {
        format!("MAP_DRIVE_ACCOUNT_POLICY session={session} policy_version={POLICY_VERSION} profile=test_lab source_state_sha256={} outgoing_state_sha256={OUTGOING_STATE_SHA256} field=stats.battlesTillCaptcha source_value=0 outgoing_value=1 persisted=false captcha_answer_generated=false",hex(&self.source_sha256))
    }

    pub(crate) fn stream_event(&self,session:u32,request:i16)->String {
        format!("MAP_DRIVE_ACCOUNT_POLICY_STREAM session={session} request={request} command=100 policy_version={POLICY_VERSION} source_state_sha256={} outgoing_state_sha256={OUTGOING_STATE_SHA256} raw_bytes={STATE_BYTES} full_stream=true client_cache_authoritative=false",hex(&self.source_sha256))
    }
}

fn project_state(source:&[u8])->io::Result<Vec<u8>> {
    if source.len()!=STATE_BYTES
        || hex(&Sha256::digest(source))!=crate::arena_vehicle091::PRIMARY_STATE_SHA256
        || source.get(781..803)!=Some(ORIGINAL_FIELD) {return Err(invalid());}
    let mut output=source.to_vec();output[VALUE_OFFSET]=1;
    if hex(&Sha256::digest(&output))!=OUTGOING_STATE_SHA256 {return Err(invalid());}
    // No generic object loader or key-search patch: this one integer byte is
    // independently decoded at stats.battlesTillCaptcha in the pinned source.
    if output[..VALUE_OFFSET]!=source[..VALUE_OFFSET] || output[VALUE_OFFSET+1..]!=source[VALUE_OFFSET+1..] {
        return Err(invalid());
    }
    Ok(output)
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;
    use std::path::PathBuf;

    pub(crate) fn actual()->(Profile,Fixtures) {
        let identity=Profile {account_id:crate::arena_vehicle091::PRIMARY_ACCOUNT.into(),database_id:1,
            name:crate::arena_vehicle091::PRIMARY_NAME.into(),fixture_dir:PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .join("../../local/server/fixtures").join(crate::arena_vehicle091::PRIMARY_ACCOUNT)
                .join("r4-catalog3").canonicalize().unwrap()};
        let fixtures=Fixtures::load_interactive(&identity.fixture_dir).unwrap();(identity,fixtures)
    }
    fn copy_identity(i:&Profile)->Profile {Profile{account_id:i.account_id.clone(),database_id:i.database_id,
        name:i.name.clone(),fixture_dir:i.fixture_dir.clone()}}

    /// Test-only independent resource envelope reader. The stored block/checksums
    /// are checked against the literal bytes, not a producer decoder round-trip.
    pub(crate) fn assembled(bodies:&[Vec<u8>],id:i16)->Vec<u8> {
        let mut data=Vec::new();let mut description=None;
        for (index,body) in bodies.iter().enumerate() {
            assert!(body.len()<=512);let mut at=0;
            if index==0 {
                assert_eq!(&body[..2],&[0x13,0x4d]);
                let size=body[2] as usize;let response=&body[3..3+size];
                assert_eq!(&response[..2],&id.to_le_bytes());
                assert_eq!(&response[2..],b"\x01\x00\x00\x04\x80\x02}.");at=3+size;
                assert_eq!(body[at],52);let length=u16::from_le_bytes([body[at+1],body[at+2]]) as usize;
                let h=&body[at+3..at+3+length];assert_eq!(&h[..2],&id.to_le_bytes());assert_eq!(h[2],14);
                description=Some(h[3..].to_vec());at+=3+length;
            }
            assert_eq!(body[at],53);let length=u16::from_le_bytes([body[at+1],body[at+2]]) as usize;
            assert_eq!(at+3+length,body.len());let f=&body[at+3..];assert_eq!(&f[..2],&id.to_le_bytes());
            assert_eq!(f[2] as usize,index);assert_eq!(f[3],u8::from(index+1==bodies.len()));data.extend(&f[4..]);
        }
        assert_eq!(&data[..3],&[0x78,1,1]);let n=u16::from_le_bytes([data[3],data[4]]);
        assert_eq!(u16::from_le_bytes([data[5],data[6]]),!n);assert_eq!(data.len(),n as usize+11);
        let raw=data[7..7+n as usize].to_vec();let (mut a,mut b)=(1u32,0u32);
        for x in &raw{a=(a+*x as u32)%65521;b=(b+a)%65521;}
        assert_eq!(&data[data.len()-4..],&((b<<16)|a).to_be_bytes());
        let d=description.unwrap();assert_eq!(&d[..3],b"\x80\x02J");assert_eq!(d[7],b'J');assert_eq!(&d[12..],b"\x86.");
        assert_eq!(i32::from_le_bytes(d[3..7].try_into().unwrap()) as usize,data.len());
        let mut crc=!0u32;for x in data {crc^=u32::from(x);for _ in 0..8 {crc=(crc>>1)^if crc&1==1{0xedb88320}else{0};}}
        assert_eq!(&d[8..12],&(!crc).to_le_bytes());raw
    }

    #[test]fn exact_primary_policy_changes_one_byte_and_is_reversible() {
        let (i,f)=actual();let before=f.state_sha256();let p=AccountPolicy::prepare(&i,&f).unwrap();
        assert_eq!(hex(&before),crate::arena_vehicle091::PRIMARY_STATE_SHA256);assert_eq!(hex(&Sha256::digest(&p.outgoing)),OUTGOING_STATE_SHA256);
        let differences:Vec<_>=f.state_bytes().iter().zip(&p.outgoing).enumerate().filter(|(_, (a,b))|a!=b).map(|(i,_)|i).collect();
        assert_eq!(differences,vec![802]);let mut inverse=p.outgoing.clone();inverse[802]=0;assert_eq!(inverse,f.state_bytes());
        assert_eq!(f.state_sha256(),before);crate::arena_vehicle091::load(&i,before).unwrap();
        assert!(crate::arena_vehicle091::load(&i,Sha256::digest(&p.outgoing).into()).is_err());
    }
    #[test]fn every_source_byte_mutation_truncation_and_extension_is_rejected() {
        let (_,f)=actual();for n in 0..STATE_BYTES {let mut b=f.state_bytes().to_vec();b[n]^=1;assert!(project_state(&b).is_err());}
        for n in 0..STATE_BYTES {assert!(project_state(&f.state_bytes()[..n]).is_err());}
        let mut b=f.state_bytes().to_vec();b.push(0);assert!(project_state(&b).is_err());
        assert!(project_state(&project_state(f.state_bytes()).unwrap()).is_err());
    }
    #[test]fn wrong_primary_identity_revision_directory_or_loaded_state_cannot_project() {
        let (i,f)=actual();for change in 0..6 {let mut wrong=copy_identity(&i);match change {
            0=>wrong.account_id="other".into(),1=>wrong.database_id=2,2=>wrong.name="other".into(),
            3=>{wrong.fixture_dir.pop();wrong.fixture_dir.push("r3-catalog3");},4=>wrong.fixture_dir="relative".into(),
            5=>{wrong.fixture_dir.pop();wrong.fixture_dir.push("r2-catalog3");},_=>unreachable!()}
            assert!(AccountPolicy::prepare(&wrong,&f).is_err());}
        let mut old=i.fixture_dir.clone();old.pop();old.push("r3-catalog3");let old=Fixtures::load_interactive(&old).unwrap();
        assert!(AccountPolicy::prepare(&i,&old).is_err());
    }
    #[test]fn older_modes_and_secondary_account_do_not_install_primary_policy() {
        let (i,f)=actual();assert!(AccountPolicy::for_mode(false,&i,&f).unwrap().is_none());
        let mut secondary=copy_identity(&i);secondary.account_id="other".into();
        assert!(AccountPolicy::for_mode(true,&secondary,&f).unwrap().is_none());
        assert!(AccountPolicy::for_mode(false,&secondary,&f).unwrap().is_none());
        secondary=copy_identity(&i);secondary.database_id=2;assert!(AccountPolicy::for_mode(true,&secondary,&f).is_err());
    }
    #[test]fn policy_full_stream_has_exact_new_bytes_and_checked_old_encoder() {
        let (i,f)=actual();let p=AccountPolicy::prepare(&i,&f).unwrap();let r=Request{id:221,command:100};
        let bodies=p.response(&r,&i,&f).unwrap();assert_eq!(bodies.len(),4);
        assert_eq!(assembled(&bodies,221),p.outgoing);
        assert_eq!(assembled(&crate::hangar091::response(&r,&f).unwrap(),221),f.state_bytes());
        for command in [300,600] {let r=Request{id:222,command};assert!(p.response(&r,&i,&f).is_err());}
        for id in [0,-1] {assert!(p.response(&Request{id,command:100},&i,&f).is_err());}
    }
    #[test]fn outgoing_or_source_hash_corruption_never_passes_policy_validation() {
        let (i,f)=actual();let p=AccountPolicy::prepare(&i,&f).unwrap();
        for n in 0..STATE_BYTES {let mut bad=p.clone();bad.outgoing[n]^=1;assert!(bad.validate(&i,&f).is_err());}
        let mut bad=p.clone();bad.source_sha256[0]^=1;assert!(bad.validate(&i,&f).is_err());
        let mut bad=p.clone();bad.outgoing.pop();assert!(bad.validate(&i,&f).is_err());
    }
    #[test]fn public_policy_binding_distinguishes_base_from_outgoing_and_no_persistence() {
        let (i,f)=actual();let p=AccountPolicy::prepare(&i,&f).unwrap();let event=p.binding_event(1);
        for required in ["policy_version=1","profile=test_lab","persisted=false","source_value=0 outgoing_value=1",
            crate::arena_vehicle091::PRIMARY_STATE_SHA256,OUTGOING_STATE_SHA256] {assert!(event.contains(required));}
        assert!(p.stream_event(1,221).contains("request=221 command=100"));assert!(p.stream_event(1,221).contains("client_cache_authoritative=false"));
        for private in ["password","credential","nonce","session_key"] {assert!(!event.contains(private));}
    }
    #[test]fn all_original_resource_response_bytes_match_frozen_envelope_goldens() {
        // Independent Python primitive framing + zlib(level=0), using the exact
        // three Ride01 accepted raw streams. See integration-01/legacy-response-golden.json.
        let (_,f)=actual();
        for (id,command,sha) in [(221,100,"99f2994e6924fc0f29fb9bceae918e017d0ffc662f3fdf7e9e8992be2767de8f"),
            (222,300,"6bdd1e8551cf0455451afa7b007d9444a6efa5c5fe8b1ae92a67120bda134785"),
            (223,600,"1a5a4ba0926251dd84b0176b9ae154ef102726f16df17abb5ee4b7db082b9644")] {
            let bodies=crate::hangar091::response(&Request{id,command},&f).unwrap();
            assert_eq!(hex(&Sha256::digest(bodies.concat())),sha);
            let path=fpath(command);let raw=std::fs::read(path).unwrap();assert_eq!(assembled(&bodies,id),raw);
        }
    }
    fn fpath(command:i16)->PathBuf {actual().0.fixture_dir.join(match command{100=>"state.bin",300=>"shop.bin",600=>"dossier.bin",_=>panic!()})}

    #[test]fn explicit_state_api_refuses_other_commands_objects_and_unbounded_roots() {
        let (_,f)=actual();let r=Request{id:221,command:100};
        for raw in [b"\x80\x02].".as_slice(),b"\x80\x02cposix\nsystem\n.",b"\x80\x02}.x",b"\x80\x02}(U\x01xu."] {
            assert!(crate::hangar091::response_state(&r,raw).is_err());}
        assert!(crate::hangar091::response_state(&r,&vec![0;16385]).is_err());
        for command in [300,600,700] {assert!(crate::hangar091::response_state(&Request{id:221,command},f.state_bytes()).is_err());}
        for id in [0,-1] {assert!(crate::hangar091::response_state(&Request{id,command:100},f.state_bytes()).is_err());}
        assert_eq!(crate::hangar091::response_state(&r,f.state_bytes()).unwrap(),crate::hangar091::response(&r,&f).unwrap());
    }
}
