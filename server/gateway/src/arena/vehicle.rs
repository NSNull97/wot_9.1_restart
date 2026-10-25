//! One fixed, authenticated MS-1 lifecycle checkpoint for native #717.
//!
//! See arena-entry/wire/roster-contract-03, pe-vehicle-aoi-01..03 and
//! data/vehicle-data-01: original PE/type/consumer contracts are VERIFIED_STATIC.
//! Vehicle02 falsified create-before-AoI: cached server entities skip prerequisites.
//! Version2 announces AoI, then requires the actual native requestEntityUpdate08
//! before sending createDetailed. See wire/vehicle-integration-02 PE/byte proof.
//! Native acceptance of the repaired ordering is NOT_RUN until independently captured.
//! No battle simulation, ammo transfer, client-provided state, or object loader.
use std::{fs::File, io::{self,Read}, path::Path};
use serde_json::Value;
use sha2::{Digest,Sha256};

pub const PRIMARY_ACCOUNT:&str="c5326cc1-8524-479c-8bba-72e973489c22";
pub const PRIMARY_NAME:&str="sr_ascii_f4d1e9";
pub const VEHICLE_ENTITY_ID:u32=0x09100003;
pub const MAX_VEHICLE_BODY:usize=512;
pub const PRIMARY_STATE_SHA256:&str="a2858ec04b42c4974332176faa9faee3dc78e5f23cf7e270b70762845e48b14e";
// Exact native constructor export and authenticated state inventory[1].compDescr[1].
pub const MS1_DESCRIPTOR:&[u8]=&[0x01,0x0d,0x1a,0x00,0x0e,0x00,0xc9,0x00,0x00,0x00,0x17,0x00,0x17,0x00,0x00];
pub const LAB_POSITION:[f32;3]=[-58.499908447265625,33.770267486572266,-445.81304931640625];
pub const PORTABLE_BUNDLE_MANIFEST_SIZE:usize=36184;
pub const PORTABLE_BUNDLE_MANIFEST_SHA256:&str="d99f2ba765e39d096cf2d0858c9864ed897a36eb9c4ea6972a15385e2355b2db";
pub const PORTABLE_CHAIN_SIZE:usize=6482;
pub const PORTABLE_CHAIN_SHA256:&str="9bbd7f825662fa17717fbd6f256596251cc8809e8acbd9e641f9488fca91980a";
pub const LEGACY_MANIFEST_SHA256:&str="ea967805376908e939fa691bb3bbc51e72253162aff98732bd753762eec35718";
const PORTABLE_PROFILE_SHA256:&str="2610dbd9ee64a12852986def336da057326f14a3289dda43eaae616286998d2d";
const PORTABLE_COMPAT_SHA256:&str="825a7e7024993c83b132499fe6f383b233ac288049bb77ca94b5407430f8d4d3";
const PORTABLE_MODEL_SHA256:&str="1b5dfa8974e17572f9cfbdaf610842835bb03d3b41ad244f2644db8921942f53";
const PORTABLE_AMMO_SHA256:&str="683daac81143a9d7edfbe671870ba163db088c54f5101fa52e077f596ebbfc74";
const INVENTORY_ID:&str="c5326cc1-8524-479c-8bba-72e973489c22:starter-vehicle-v1";
const PINNED_FILES:[(&str,usize,&str);5]=[
    ("profile-input.json",1877,"2610dbd9ee64a12852986def336da057326f14a3289dda43eaae616286998d2d"),
    ("manifest.json",15490,"ea967805376908e939fa691bb3bbc51e72253162aff98732bd753762eec35718"),
    ("compatibility.json",1603,"825a7e7024993c83b132499fe6f383b233ac288049bb77ca94b5407430f8d4d3"),
    ("fixture.json",3363,"1b5dfa8974e17572f9cfbdaf610842835bb03d3b41ad244f2644db8921942f53"),
    ("state.bin",1329,PRIMARY_STATE_SHA256),
];

fn invalid()->io::Error {io::Error::new(io::ErrorKind::InvalidData,"unverified own MS-1 arena checkpoint")}
fn hex(bytes:&[u8])->String {bytes.iter().map(|v|format!("{v:02x}")).collect()}
fn digest(bytes:&[u8])->String {format!("{:x}",Sha256::digest(bytes))}

/// Read a bounded file below an explicit portable content bundle root.
pub fn portable_file(root:&Path,relative:&str,size:usize,sha:&str)->io::Result<Vec<u8>> {
    if !root.is_absolute() || relative.is_empty() || relative.contains("..") || size>64*1024 {return Err(invalid());}
    let base=root.canonicalize().map_err(|_|invalid())?;if !base.is_dir(){return Err(invalid());}
    let canonical=base.join(relative).canonicalize().map_err(|_|invalid())?;
    if !canonical.starts_with(&base)||!canonical.is_file(){return Err(invalid());}
    let mut file=File::open(canonical).map_err(|_|invalid())?;let meta=file.metadata().map_err(|_|invalid())?;
    if meta.len()!=size as u64{return Err(invalid());}
    let mut bytes=Vec::with_capacity(size);file.take(size as u64+1).read_to_end(&mut bytes).map_err(|_|invalid())?;
    if bytes.len()!=size||digest(&bytes)!=sha{return Err(invalid());}Ok(bytes)
}

/// Verify the hash-anchored portable profile4 chain. This is separate from
/// the strict legacy-manifest loader; the bundle intentionally omits absolute
/// path manifests and we never fabricate one.
pub fn verify_portable_bundle(root:&Path)->io::Result<()> {
    let manifest=portable_file(root,"manifest.json",PORTABLE_BUNDLE_MANIFEST_SIZE,PORTABLE_BUNDLE_MANIFEST_SHA256)?;
    let chain=portable_file(root,"content/metadata/profile-chain.blob",PORTABLE_CHAIN_SIZE,PORTABLE_CHAIN_SHA256)?;
    let m:Value=serde_json::from_slice(&manifest).map_err(|_|invalid())?;let c:Value=serde_json::from_slice(&chain).map_err(|_|invalid())?;
    if m["format"].as_str()!=Some("server-content.v1")||m["ruleset"].as_str()!=Some("test_lab")
        ||c["version"].as_i64()!=Some(1)||c["status"].as_str()!=Some("PASS_LEGACY_HASH_ANCHORS"){return Err(invalid());}
    let row=c["chain"].as_array().and_then(|a|a.iter().find(|v|v["fixture"]=="profile4")).ok_or_else(invalid)?;
    if row["profile_content_id"].as_str()!=Some("fixtures/profile4/profile-input.json")
        ||row["profile_sha256"].as_str()!=Some(PORTABLE_PROFILE_SHA256)
        ||row["legacy_manifest_sha256"].as_str()!=Some(LEGACY_MANIFEST_SHA256){return Err(invalid());}
    let profile=portable_file(root,"content/fixtures/profile4/profile-input.json.blob",1877,PORTABLE_PROFILE_SHA256)?;
    let compat=portable_file(root,"content/fixtures/profile4/compatibility.json.blob",1603,PORTABLE_COMPAT_SHA256)?;
    let model=portable_file(root,"content/fixtures/profile4/fixture.json.blob",3363,PORTABLE_MODEL_SHA256)?;
    let state=portable_file(root,"content/fixtures/profile4/state.bin.blob",1329,PRIMARY_STATE_SHA256)?;
    let p:Value=serde_json::from_slice(&profile).map_err(|_|invalid())?;let cpt:Value=serde_json::from_slice(&compat).map_err(|_|invalid())?;let mdl:Value=serde_json::from_slice(&model).map_err(|_|invalid())?;
    validate_metadata(&p,&cpt,&mdl)?;if digest(&state)!=PRIMARY_STATE_SHA256{return Err(invalid());}Ok(())
}
pub fn portable_bundle_state(root:&Path)->io::Result<[u8;32]> {
    verify_portable_bundle(root)?;Ok(Sha256::digest(portable_file(root,"content/fixtures/profile4/state.bin.blob",1329,PRIMARY_STATE_SHA256)?).into())
}
pub fn load_source_bundle(identity:&crate::identity091::Profile,root:&Path)->io::Result<VehicleSeed> {
    if identity.account_id!=PRIMARY_ACCOUNT||identity.database_id!=1||identity.name!=PRIMARY_NAME{return Err(invalid());}
    verify_portable_bundle(root)?;
    let p:Value=serde_json::from_slice(&portable_file(root,"content/fixtures/profile4/profile-input.json.blob",1877,PORTABLE_PROFILE_SHA256)?).map_err(|_|invalid())?;
    let c:Value=serde_json::from_slice(&portable_file(root,"content/fixtures/profile4/compatibility.json.blob",1603,PORTABLE_COMPAT_SHA256)?).map_err(|_|invalid())?;
    let m:Value=serde_json::from_slice(&portable_file(root,"content/fixtures/profile4/fixture.json.blob",3363,PORTABLE_MODEL_SHA256)?).map_err(|_|invalid())?;
    if p["account_id"].as_str()!=Some(identity.account_id.as_str())||p["username"].as_str()!=Some(identity.name.as_str())||p["native_database_id"].as_i64()!=Some(identity.database_id as i64){return Err(invalid());}
    validate_metadata(&p,&c,&m)?;Ok(VehicleSeed{name:identity.name.clone(),database_id:identity.database_id,descriptor:MS1_DESCRIPTOR.to_vec(),health:90,state_sha256:portable_bundle_state(root)?})
}

#[derive(Clone,Debug,PartialEq,Eq)]
pub struct VehicleSeed {
    pub(crate) name:String,
    pub(crate) database_id:i32,
    pub(crate) descriptor:Vec<u8>,
    pub(crate) health:i16,
    pub(crate) state_sha256:[u8;32],
}
impl VehicleSeed {
    fn validate(&self)->io::Result<()> {
        if self.name!=PRIMARY_NAME || self.database_id!=1 || self.descriptor!=MS1_DESCRIPTOR
            || self.health!=90 || hex(&self.state_sha256)!=PRIMARY_STATE_SHA256 {return Err(invalid());}
        Ok(())
    }
    pub fn validate_session(&self,identity:&crate::identity091::Profile,loaded_state:[u8;32])->io::Result<()> {
        self.validate()?;
        if identity.account_id!=PRIMARY_ACCOUNT || identity.database_id!=self.database_id
            || identity.name!=self.name || loaded_state!=self.state_sha256 {return Err(invalid());}
        Ok(())
    }
}

fn read_pinned(directory:&Path,name:&str,size:usize,expected:&str)->io::Result<Vec<u8>> {
    let file=File::open(directory.join(name))?;
    let metadata=file.metadata()?;
    if !metadata.is_file() || metadata.len()!=size as u64 || size>16*1024 {return Err(invalid());}
    let mut raw=Vec::with_capacity(size);
    file.take((size+1) as u64).read_to_end(&mut raw)?;
    if raw.len()!=size || format!("{:x}",Sha256::digest(&raw))!=expected {return Err(invalid());}
    Ok(raw)
}

fn validate_metadata(profile:&Value,compat:&Value,model:&Value)->io::Result<()> {
    // Exact bytes are pinned first. These explicit typed semantics also reject
    // accidental identity/version/HP/mapping changes during future maintenance.
    for object in [profile,compat,model] {
        if object["account_id"].as_str()!=Some(PRIMARY_ACCOUNT)
            || object["snapshot_revision"].as_i64()!=Some(4) {return Err(invalid());}
    }
    if profile["profile_version"].as_i64()!=Some(4) || model["profile_version"].as_i64()!=Some(4)
        || model["fixture_version"].as_i64()!=Some(4) || model["ruleset"].as_str()!=Some("test_lab")
        || profile["native_database_id"].as_i64()!=Some(1) || compat["native_database_id"].as_i64()!=Some(1)
        || profile["username"].as_str()!=Some(PRIMARY_NAME) || compat["client_name"].as_str()!=Some(PRIMARY_NAME)
        || model["display_name"].as_str()!=Some(PRIMARY_NAME)
        || compat["wire_sync_revision"].as_i64()!=Some(1) || compat["compatibility_catalog_revision"].as_i64()!=Some(3)
        || profile["inventory"]!=model["inventory"] {return Err(invalid());}
    let inventory=profile["inventory"].as_array().ok_or_else(invalid)?;
    let mappings=compat["vehicle_mapping"].as_array().ok_or_else(invalid)?;
    if inventory.len()!=2 || mappings.len()!=2 {return Err(invalid());}
    let ms1=&inventory[0];let mapping=&mappings[0];
    if ms1["inventory_id"].as_str()!=Some(INVENTORY_ID)
        || ms1["vehicle_definition_id"].as_str()!=Some("vehicle:ms1")
        || ms1["health"].as_i64()!=Some(90) || ms1["crew_assigned"].as_bool()!=Some(true)
        || mapping["inventory_id"].as_str()!=Some(INVENTORY_ID)
        || mapping["native_inventory_id"].as_i64()!=Some(1)
        || mapping["type_compact_descr"].as_i64()!=Some(3329) {return Err(invalid());}
    Ok(())
}

/// Only the already accepted primary profile4 is allowed by this experiment.
/// The separately audited literal state supplies the pinned 15-byte descriptor;
/// no generic pickle/object interpreter is introduced into the gateway.
pub fn load(identity:&crate::identity091::Profile,loaded_state:[u8;32])->io::Result<VehicleSeed> {
    if identity.account_id!=PRIMARY_ACCOUNT || identity.database_id!=1 || identity.name!=PRIMARY_NAME
        || !identity.fixture_dir.is_absolute() {return Err(invalid());}
    let mut files=Vec::new();
    for (name,size,sha) in PINNED_FILES {files.push(read_pinned(&identity.fixture_dir,name,size,sha)?);}
    let profile:Value=serde_json::from_slice(&files[0]).map_err(|_|invalid())?;
    let compat:Value=serde_json::from_slice(&files[2]).map_err(|_|invalid())?;
    let model:Value=serde_json::from_slice(&files[3]).map_err(|_|invalid())?;
    validate_metadata(&profile,&compat,&model)?;
    let actual_state:[u8;32]=Sha256::digest(&files[4]).into();
    if loaded_state!=actual_state {return Err(invalid());}
    let seed=VehicleSeed {name:identity.name.clone(),database_id:identity.database_id,
        descriptor:MS1_DESCRIPTOR.to_vec(),health:90,state_sha256:actual_state};
    seed.validate_session(identity,loaded_state)?;Ok(seed)
}

fn string(out:&mut Vec<u8>,bytes:&[u8])->io::Result<()> {
    if bytes.len()>=255 {return Err(invalid());}
    out.push(bytes.len() as u8);out.extend(bytes);Ok(())
}
fn var16(id:u8,payload:&[u8])->io::Result<Vec<u8>> {
    if payload.is_empty() || payload.len()>MAX_VEHICLE_BODY {return Err(invalid());}
    let mut body=vec![id];body.extend((payload.len() as u16).to_le_bytes());body.extend(payload);Ok(body)
}
fn literal_bytes(out:&mut Vec<u8>,bytes:&[u8])->io::Result<()> {out.push(b'U');string(out,bytes)}
fn literal_i32(out:&mut Vec<u8>,value:i32) {out.push(b'J');out.extend(value.to_le_bytes());}

fn roster(seed:&VehicleSeed)->io::Result<Vec<u8>> {
    seed.validate()?;
    // Protocol2 literal list[tuple14], only bounded byte strings, integers,
    // booleans and an empty dict. No GLOBAL/REDUCE/memo/object instructions.
    let mut data=vec![0x80,2,b']',b'('];
    literal_i32(&mut data,VEHICLE_ENTITY_ID as i32);
    literal_bytes(&mut data,&seed.descriptor)?;literal_bytes(&mut data,seed.name.as_bytes())?;
    data.extend([b'K',1,0x88,0x89,0x89]); // team1, alive, not ready, not team killer
    literal_i32(&mut data,seed.database_id);literal_bytes(&mut data,b"")?;
    data.extend([b'K',0,b'K',0,0x89,b'}',b'K',0,b't',b'a',b'.']);
    let mut payload=vec![1];string(&mut payload,&data)?;
    if payload.len()>=255 {return Err(invalid());}
    let mut body=vec![0x13,0x58,payload.len() as u8];body.extend(payload);Ok(body)
}

pub fn create_requested_vehicle(seed:&VehicleSeed)->io::Result<Vec<u8>> {
    seed.validate()?;
    let mut data=vec![0]; // native compression mode0, no compression
    data.extend(VEHICLE_ENTITY_ID.to_le_bytes());data.extend(2u16.to_le_bytes());
    for value in LAB_POSITION {data.extend(value.to_le_bytes());}
    for value in [0f32;3] {data.extend(value.to_le_bytes());}
    data.push(8); // ordinary client properties, indexed stream, factory mode3
    data.extend([0,0,1,1]); // isStrafing=false, isCrewActive=true
    // Explicit laboratory angle seed0 decodes to yaw=-pi/minimum pitch, NOT
    // a neutral pose or a measured physical tank spawn. Engine0/0 is idle.
    data.push(2);data.extend(0u16.to_le_bytes());
    data.push(3);data.extend(seed.health.to_le_bytes());
    data.extend([4,0,0,5]); // fixed engine tuple2, publicInfo index5
    string(&mut data,seed.name.as_bytes())?;string(&mut data,&seed.descriptor)?;
    data.push(1);data.extend(0i32.to_le_bytes());data.push(0); // team, prebattle, marks
    data.push(6);data.extend(0i32.to_le_bytes()); // empty ARRAY<UINT64>
    data.push(7);data.extend(0i32.to_le_bytes()); // empty ARRAY<UINT8>
    var16(9,&data)
}

/// Preserve old cell/space bytes, then roster and the own AoI announcement.
/// Do NOT create the server entity here: native must request its full data first.
pub fn announce_vehicle(seed:&VehicleSeed)->io::Result<Vec<u8>> {
    seed.validate()?;
    let mut body=crate::arena091::create_cell_avatar(&crate::arena091::AvatarCellSeed {
        space_id:1,player_vehicle_id:VEHICLE_ENTITY_ID,position:LAB_POSITION,
    })?;
    body.extend(crate::arena091::karelia_space_data(1,1u64.to_le_bytes())?);
    body.extend(roster(seed)?);
    body.push(0x0a);body.extend(VEHICLE_ENTITY_ID.to_le_bytes());body.push(0); // alias0
    if body.len()>MAX_VEHICLE_BODY {return Err(invalid());}Ok(body)
}

/// Captured Vehicle02 seq18: requestEntityUpdate08, VAR2 length4, exact own ID.
/// Cache stamps, another entity, trailing data, or another header are unsupported.
pub fn is_own_entity_update_request(payload:&[u8])->bool {
    payload==[0x08,0x04,0x00,0x03,0x00,0x10,0x09]
}

/// Passive classification of complete, exact automatic envelopes only. The
/// caller still records application unsupported/transport ACK, no domain apply.
pub fn automatic_lifecycle_calls(mut payload:&[u8])->Option<Vec<&'static str>> {
    if payload.is_empty() || payload.len()>14 {return None;}
    let mut result=Vec::new();
    while !payload.is_empty() {
        let (name,size)=if payload.starts_with(&[0x86,0,0]) {("setClientReady",3)}
            else if payload.starts_with(&[0x0c,8,0,0,0,0,0,0,0,0,0]) {("autoAimZero",11)}
            else {return None;};
        if result.contains(&name) {return None;}
        result.push(name);payload=&payload[size..];
    }
    Some(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    pub(crate) fn actual_identity()->crate::identity091::Profile {
        crate::identity091::Profile {account_id:PRIMARY_ACCOUNT.to_owned(),database_id:1,name:PRIMARY_NAME.to_owned(),
            fixture_dir:PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../local/server/fixtures").join(PRIMARY_ACCOUNT).join("r4-catalog3").canonicalize().unwrap()}
    }
    fn actual_seed()->VehicleSeed {
        let identity=actual_identity();let fixtures=crate::hangar091::Fixtures::load_interactive(&identity.fixture_dir).unwrap();
        load(&identity,fixtures.state_sha256()).unwrap()
    }
    #[test] fn accepted_actual_profile_and_loaded_state_are_bound_without_mutation() {
        let identity=actual_identity();let fixtures=crate::hangar091::Fixtures::load_interactive(&identity.fixture_dir).unwrap();
        let before=fixtures.state_sha256();let seed=load(&identity,before).unwrap();
        assert_eq!(seed.descriptor.len(),15);assert_eq!(seed.descriptor,MS1_DESCRIPTOR);assert_eq!(seed.health,90);
        assert_eq!(fixtures.state_sha256(),before);assert_eq!(hex(&before),PRIMARY_STATE_SHA256);
    }
    #[test] fn wrong_identity_loaded_state_or_fixture_path_fails_closed() {
        let seed=actual_seed();
        for change in 0..6 {
            let mut identity=actual_identity();let mut state=seed.state_sha256;
            match change {0=>identity.account_id="00000000-0000-0000-0000-000000000002".to_owned(),
                1=>identity.database_id=2,2=>identity.name="other".to_owned(),3=>state[0]^=1,
                4=>{identity.fixture_dir.pop();identity.fixture_dir.push("r3-catalog3");},
                5=>identity.fixture_dir=PathBuf::from("relative"),_=>unreachable!()}
            assert!(load(&identity,state).is_err());
        }
    }
    #[test] fn metadata_rejects_version_hp_type_and_mapping_substitutions() {
        let identity=actual_identity();
        let profile:Value=serde_json::from_slice(&std::fs::read(identity.fixture_dir.join("profile-input.json")).unwrap()).unwrap();
        let compat:Value=serde_json::from_slice(&std::fs::read(identity.fixture_dir.join("compatibility.json")).unwrap()).unwrap();
        let model:Value=serde_json::from_slice(&std::fs::read(identity.fixture_dir.join("fixture.json")).unwrap()).unwrap();
        for change in 0..9 {
            let (mut p,mut c,mut m)=(profile.clone(),compat.clone(),model.clone());
            match change {0=>p["profile_version"]=serde_json::json!(3),1=>p["native_database_id"]=serde_json::json!(true),
                2=>{p["inventory"][0]["health"]=serde_json::json!(91);m["inventory"]=p["inventory"].clone();},
                3=>{p["inventory"][0]["crew_assigned"]=serde_json::json!(false);m["inventory"]=p["inventory"].clone();},
                4=>c["vehicle_mapping"][0]["type_compact_descr"]=serde_json::json!(7169),
                5=>c["wire_sync_revision"]=serde_json::json!(4),6=>m["account_id"]=serde_json::json!("foreign"),
                7=>c["snapshot_revision"]=serde_json::json!(4.0),8=>c["compatibility_catalog_revision"]=serde_json::json!(4),_=>unreachable!()}
            assert!(validate_metadata(&p,&c,&m).is_err(),"change {change}");
        }
    }
    #[test] fn changed_descriptor_health_name_or_state_rejects_entire_encoder() {
        let good=actual_seed();
        for change in 0..5 {
            let mut seed=good.clone();match change {0=>seed.descriptor[0]^=1,1=>seed.health=91,
                2=>seed.name="other".to_owned(),3=>seed.database_id=2,4=>seed.state_sha256[0]^=1,_=>unreachable!()}
            assert!(announce_vehicle(&seed).is_err());assert!(create_requested_vehicle(&seed).is_err());
        }
    }
    #[test] fn fixed_detailed_properties_have_native_indices_sizes_and_no_implicit_wrappers() {
        let seed=actual_seed();let wire=create_requested_vehicle(&seed).unwrap();
        assert_eq!(wire[0],9);assert_eq!(u16::from_le_bytes([wire[1],wire[2]]) as usize,wire.len()-3);
        let d=&wire[3..];assert_eq!(d[0],0);assert_eq!(&d[1..5],&VEHICLE_ENTITY_ID.to_le_bytes());assert_eq!(&d[5..7],&2u16.to_le_bytes());
        assert_eq!(d[31],8);assert_eq!(&d[32..46],&[0,0,1,1,2,0,0,3,90,0,4,0,0,5]);
        let name_len=d[46] as usize;assert_eq!(&d[47..47+name_len],PRIMARY_NAME.as_bytes());
        let cd_at=47+name_len;assert_eq!(d[cd_at],15);assert_eq!(&d[cd_at+1..cd_at+16],MS1_DESCRIPTOR);
        assert_eq!(&d[cd_at+16..],&[1,0,0,0,0,0,6,0,0,0,0,7,0,0,0,0]);
    }
    #[test] fn announcement_preserves_old_cell_space_then_roster_and_enter_without_creation() {
        let seed=actual_seed();let body=announce_vehicle(&seed).unwrap();assert_eq!(body.len(),221);
        let mut old=crate::arena091::create_cell_avatar(&crate::arena091::AvatarCellSeed{space_id:1,player_vehicle_id:VEHICLE_ENTITY_ID,position:LAB_POSITION}).unwrap();
        old.extend(crate::arena091::karelia_space_data(1,1u64.to_le_bytes()).unwrap());assert_eq!(old.len(),144);assert_eq!(&body[..144],old);
        let roster=roster(&seed).unwrap();assert_eq!(&body[144..144+roster.len()],roster);
        assert_eq!(&roster[..4],&[0x13,0x58,(roster.len()-3) as u8,1]);
        assert_eq!(&roster[5..9],&[0x80,2,b']',b'(']);assert_eq!(&roster[roster.len()-3..],b"ta.");
        let at=144+roster.len();assert_eq!(&body[at..],&[vec![0x0a],VEHICLE_ENTITY_ID.to_le_bytes().to_vec(),vec![0]].concat());
        assert_eq!(create_requested_vehicle(&seed).unwrap().len(),97);
    }
    #[test] fn portable_source_bundle_uses_hash_anchor_without_legacy_manifest_bytes() {
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/stands/p09e-main-01/source-bundle-05").canonicalize().unwrap();
        verify_portable_bundle(&root).unwrap();
        let identity=crate::identity091::Profile{account_id:PRIMARY_ACCOUNT.to_owned(),database_id:1,name:PRIMARY_NAME.to_owned(),fixture_dir:root.clone()};
        let seed=load_source_bundle(&identity,&root).unwrap();
        assert_eq!(seed.descriptor,MS1_DESCRIPTOR);assert_eq!(seed.health,90);assert_eq!(hex(&seed.state_sha256),PRIMARY_STATE_SHA256);
        let foreign=crate::identity091::Profile{account_id:identity.account_id.clone(),database_id:1,name:"foreign".to_owned(),fixture_dir:root.clone()};assert!(load_source_bundle(&foreign,&root).is_err());
        assert!(verify_portable_bundle(&root.join("content")).is_err());
    }
    #[test] fn update_request_exact_measured_header_entity_and_no_extra_stamps() {
        let good=[0x08,4,0,3,0,0x10,9];assert!(is_own_entity_update_request(&good));
        for at in 0..good.len() {let mut bad=good;bad[at]^=1;assert!(!is_own_entity_update_request(&bad));}
        for bad in [&good[..6],&[0x08,4,0,0,0,0,0],&[0x08,8,0,3,0,0x10,9,0,0,0,0],&[9]] {
            assert!(!is_own_entity_update_request(bad));
        }
    }
    #[test] fn lifecycle_observation_requires_exact_complete_automatic_forms() {
        let ready=vec![0x86,0,0];let auto=vec![0x0c,8,0,0,0,0,0,0,0,0,0];
        assert_eq!(automatic_lifecycle_calls(&ready),Some(vec!["setClientReady"]));
        assert_eq!(automatic_lifecycle_calls(&auto),Some(vec!["autoAimZero"]));
        assert_eq!(automatic_lifecycle_calls(&[ready.clone(),auto.clone()].concat()),Some(vec!["setClientReady","autoAimZero"]));
        for bad in [vec![],vec![0x86,1,0,0],vec![0x0c,4,0,0,0,0,0],
            vec![0x0c,8,0,1,0,0,0,0,0,0,0],vec![0x0c,8,0,0,0,0,0,1,0,0,0],
            [ready.clone(),ready.clone()].concat(),[auto.clone(),vec![0xee]].concat()] {
            assert!(automatic_lifecycle_calls(&bad).is_none());
        }
    }
}
