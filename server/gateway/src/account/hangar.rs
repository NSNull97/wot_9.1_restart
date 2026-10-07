//! Bounded, opt-in #717 hangar experiment. No incoming Python objects are loaded.
//! The fixture is our own laboratory player state, not a second identity store.
//! showGUI routing and multi-part resource streams require native verification;
//! initial command IDs, responseExt and the one-part stream were measured earlier.
use std::{fs::File, io::{self, Read}, path::Path};
use crate::account091::Request;
use serde::Deserialize;
use sha2::{Digest, Sha256};

const MAX_FIXTURE: usize = 16 * 1024;
const MAX_NODES: usize = 4096;
const MAX_DEPTH: usize = 16;
const CHUNK_SIZE: usize = 400;
const EMPTY_DICT: &[u8] = b"\x80\x02}.";

fn invalid(message: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message)
}

#[derive(Debug, Clone)]
pub struct Fixtures {
    state: Vec<u8>,
    shop: Vec<u8>,
    dossier: Vec<u8>,
    dossier_cursor: Option<DossierCursor>,
}

#[derive(Debug, Clone, Copy, PartialEq)]
struct DossierCursor {
    version: i64,
    last_change_time: i32,
    vehicle_type_compact_descr: i32,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ChatRequest { pub id: i64, pub command: u8 }

#[derive(Debug, Clone, PartialEq)]
pub enum Incoming { Sync(Request), Refresh(Request), Chat(ChatRequest), Language { id: i16 }, ServerStats,
                    DossierSync { request:Request, version:i64, last_change_time:i32 },
                    CachedSync { request:Request, descriptor_a:i32, descriptor_b:i32 },
                    CachedRefresh { request:Request, persistent_hash:i32 },
                    UnsupportedIntArray { id:i16, command:i16, argument_count:usize } }

/// Measured gui-01 bundle: three ordinary sync calls plus friend status, roster
/// and service-history chat calls. No arbitrary command arguments are accepted.
/// Empty means the measured token-only application body; token validation stays
/// in the gateway. Unknown methods or any truncated tail reject the whole bundle.
pub fn requests(body: &[u8]) -> io::Result<Vec<Incoming>> {
    requests_profile(body,false)
}
pub fn requests_interactive(body:&[u8])->io::Result<Vec<Incoming>> {
    requests_profile(body,true)
}
fn requests_profile(body:&[u8],interactive:bool)->io::Result<Vec<Incoming>> {
    if body.len() > 512 { return Err(invalid("hangar request bundle size")); }
    let mut cursor = 0;
    let mut rows = Vec::new();
    while cursor < body.len() {
        if rows.len() >= 16 || body.len() - cursor < 3 { return Err(invalid("hangar request count/header")); }
        let header = &body[cursor..cursor + 3];
        let length = u16::from_le_bytes([header[1], header[2]]) as usize;
        let end = cursor.checked_add(3 + length).ok_or_else(|| invalid("hangar request length overflow"))?;
        let packet = body.get(cursor..end).ok_or_else(|| invalid("truncated hangar request"))?;
        let row = match header[0] {
            0x8e if length == 20 && packet[3..7] == [202, 0, 245, 1] => {
                if packet[7..] != [0;16] || rows.contains(&Incoming::ServerStats) {
                    return Err(invalid("unmeasured server statistics request"));
                }
                Incoming::ServerStats
            },
            0x8e if length == 20 => {
                // gui-02: after the state stream, AccountSyncData requests
                // revision1 once more before releasing its subscribers.
                let refresh = packet[5..7] == 100i16.to_le_bytes()
                    && packet[7..15] == 1i64.to_le_bytes() && packet[15..] == [0; 8];
                // Original DossierCache.__sendSyncRequest: CMD600(version,
                // maxChangeTime, 0). Native relogin of the new granted fixture
                // remains NOT_RUN until captured; the old laboratory is strict.
                let cached = interactive && packet[5..7] == 600i16.to_le_bytes()
                    && packet[7..].iter().any(|byte| *byte != 0);
                let version = i64::from_le_bytes(packet[7..15].try_into().map_err(|_|invalid("dossier version"))?);
                let last_change_time = i32::from_le_bytes(packet[15..19].try_into().map_err(|_|invalid("dossier change time"))?);
                let third = i32::from_le_bytes(packet[19..23].try_into().map_err(|_|invalid("sync third argument"))?);
                // UI09 original persistent caches: initial Account CMD100 is
                // (revision0, persistent hash, 0); Shop CMD300 is (revision0,
                // compressed size, signed CRC32). These are opaque cache hints,
                // not client state. This service always sends its complete
                // authenticated fixture through the original RES_STREAM branch.
                // Existing laboratory requests and revision1 refresh stay strict.
                let cache_hint = interactive && version==0 && match i16::from_le_bytes([packet[5],packet[6]]) {
                    100 => last_change_time!=0 && third==0,
                    300 => (1..=(MAX_FIXTURE+64) as i32).contains(&last_change_time),
                    _ => false,
                };
                // UI10: __onSyncComplete advances revision, then the same
                // __sendSyncRequest still supplies persistentCache.getDescr().
                let cache_refresh = interactive && packet[5..7]==100i16.to_le_bytes()
                    && version==1 && last_change_time!=0 && third==0;
                if cached && (version != 1 || last_change_time <= 0 || packet[19..] != [0;4]) {
                    return Err(invalid("unsupported dossier cache cursor"));
                }
                let r = if refresh || cached || cache_hint || cache_refresh {
                    let id = i16::from_le_bytes([packet[3], packet[4]]);
                    if id <= 0 { return Err(invalid("refresh request ID")); }
                    Request { id, command: i16::from_le_bytes([packet[5],packet[6]]) }
                } else {
                    crate::account091::requests(packet)?.pop().ok_or_else(|| invalid("empty sync request"))?
                };
                if rows.iter().any(|r0| matches!(r0, Incoming::Sync(previous) | Incoming::Refresh(previous)
                    | Incoming::DossierSync {request:previous,..}
                    | Incoming::CachedSync {request:previous,..}
                    | Incoming::CachedRefresh {request:previous,..}
                    if previous.id == r.id || previous.command == r.command)
                    || matches!(r0, Incoming::Language { id } | Incoming::UnsupportedIntArray {id,..} if *id == r.id)) {
                    return Err(invalid("duplicate sync in hangar bundle"));
                }
                if cached { Incoming::DossierSync {request:r,version,last_change_time} }
                else if cache_hint { Incoming::CachedSync {request:r,descriptor_a:last_change_time,descriptor_b:third} }
                else if cache_refresh { Incoming::CachedRefresh {request:r,persistent_hash:last_change_time} }
                else if refresh { Incoming::Refresh(r) } else { Incoming::Sync(r) }
            },
            0x93 if length == 25 => {
                let payload = &packet[3..];
                let id = i64::from_le_bytes(payload[..8].try_into().map_err(|_| invalid("chat request ID"))?);
                let command = payload[8];
                let argument = i64::from_le_bytes(payload[13..21].try_into().map_err(|_| invalid("chat argument"))?);
                if !(1..=30000).contains(&id) || ![9, 10, 30].contains(&command)
                    || payload[9..13] != [0; 4] || payload[21..] != [0; 4]
                    || argument != if command == 10 { -1 } else { 0 }
                    || rows.iter().any(|r| matches!(r, Incoming::Chat(previous) if previous.id == id)) {
                    return Err(invalid("unmeasured chat command shape"));
                }
                Incoming::Chat(ChatRequest { id, command })
            },
            0x95 if length == 7 => {
                // gui-03 observed doCmdStr(request225, CMD_SET_LANGUAGE1000,
                // STRING "ru"). Account.setLanguage:1269 passes callback=None.
                let id = i16::from_le_bytes([packet[3], packet[4]]);
                if id <= 0 || packet[5..] != [0xe8, 0x03, 2, b'r', b'u']
                    || rows.iter().any(|r0| match r0 {
                        Incoming::Language { .. } => true,
                        Incoming::Sync(r) | Incoming::Refresh(r) | Incoming::DossierSync {request:r,..}
                        | Incoming::CachedSync {request:r,..} => r.id == id,
                        Incoming::CachedRefresh {request:r,..} => r.id == id,
                        Incoming::Chat(_) => false,
                        Incoming::ServerStats => id == 202,
                        Incoming::UnsupportedIntArray {id:previous,..} => *previous==id,
                    }) {
                    return Err(invalid("unmeasured language request"));
                }
                Incoming::Language { id }
            },
            0x97 if interactive && length==72 => {
                // Actual auth09 packet222: doCmdIntArr, CMD_SET_AND_FILL_LAYOUTS.
                // Only its measured 16-INT32 layout shape is recognized here.
                // The command is unavailable; no ammo/equipment/price is applied.
                let payload=&packet[3..];
                let id=i16::from_le_bytes(payload[..2].try_into().map_err(|_|invalid("array request ID"))?);
                let command=i16::from_le_bytes(payload[2..4].try_into().map_err(|_|invalid("array command"))?);
                let count=u32::from_le_bytes(payload[4..8].try_into().map_err(|_|invalid("array count"))?);
                if id<=0 || command!=108 || count!=16 || payload[16..20]!=6i32.to_le_bytes()
                    || payload[44..48]!=6i32.to_le_bytes() || rows.iter().any(|r|match r {
                        Incoming::Sync(r)|Incoming::Refresh(r)|Incoming::DossierSync {request:r,..}
                        |Incoming::CachedSync {request:r,..}=>r.id==id,
                        Incoming::CachedRefresh {request:r,..}=>r.id==id,
                        Incoming::Language{id:previous}|Incoming::UnsupportedIntArray{id:previous,..}=>*previous==id,
                        Incoming::ServerStats=>id==202,Incoming::Chat(_)=>false,
                    }) {return Err(invalid("unmeasured unavailable integer-array command"));}
                Incoming::UnsupportedIntArray {id,command,argument_count:count as usize}
            },
            _ => return Err(invalid("unmeasured hangar method")),
        };
        rows.push(row);
        cursor = end;
    }
    Ok(rows)
}

/// Original AccountCommands.RES_NOT_AVAILABLE=-10. The real Account response
/// dispatcher and vehicle layout processor route this to the UI error handler;
/// it is not a success and must never mutate fixture or inventory state.
pub fn unavailable_response(id:i16)->io::Result<Vec<u8>> {
    if id<=0 {return Err(invalid("unavailable response request ID"));}
    let mut payload=id.to_le_bytes().to_vec();payload.extend((-10i16).to_le_bytes());
    payload.push(0);payload.push(EMPTY_DICT.len() as u8);payload.extend(EMPTY_DICT);
    method(0x4d,&payload)
}

/// Original receiveServerStats FIXED_DICT has clusterCCU/regionCCU UINT32.
/// This isolated gateway has exactly one authenticated active session when called.
/// Fixed-size client slot13 => 0x48; native gui-07 must confirm this route.
pub fn server_stats() -> Vec<u8> {
    let mut body=vec![0x13,0x48];
    body.extend(1u32.to_le_bytes());body.extend(1u32.to_le_bytes());body
}

/// Read the actual empty contact/history state of this disposable new account.
/// UsersManager.__onRequestUsersRoster accepts [] with flags0 and clears rosters.
/// With no friends, command10 has no per-friend status events to push; with no
/// service history, command30 has no events either. Both are fire-and-forget
/// ClientChat calls with no completion callback/terminator. Messaging and contact
/// mutations remain unsupported; no invented users or service messages are sent.
pub fn chat_response(request: &ChatRequest) -> io::Result<Option<Vec<u8>>> {
    if !(1..=30000).contains(&request.id) || ![9, 10, 30].contains(&request.command) {
        return Err(invalid("unimplemented chat request"));
    }
    if request.command != 9 { return Ok(None); }
    let time = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| invalid("server UTC clock"))?.as_secs_f64();
    let mut payload = request.id.to_le_bytes().to_vec();
    payload.extend([13, 0]); // requestUsersRoster / success, actual empty new roster.
    payload.extend(time.to_le_bytes());
    payload.extend(time.to_le_bytes());
    payload.extend(0i32.to_le_bytes()); // no channel
    payload.extend((-1i64).to_le_bytes()); // no originator
    payload.extend([0, 0]); // empty nickname STRING, member group0
    let roster = b"\x80\x02].";
    payload.push(roster.len() as u8);
    payload.extend(roster); // PYTHON data=[], primitive own roster.
    payload.push(0); // flags
    Ok(Some(method(0x4b, &payload)?))
}

impl Fixtures {
    pub fn load(directory: &Path) -> io::Result<Self> {
        Self::load_with_budget(directory,crate::transport091::MAX_SEQUENCE)
    }
    pub fn load_interactive(directory: &Path) -> io::Result<Self> {
        let mut fixtures=Self::load_with_budget(directory,crate::transport091::INTERACTIVE_MAX_SEQUENCE)?;
        fixtures.dossier_cursor=grant_dossier_cursor(directory,&fixtures.dossier)?;
        Ok(fixtures)
    }
    fn load_with_budget(directory:&Path,sequence_budget:u32)->io::Result<Self> {
        fn read(directory: &Path, name: &str, root: Kind) -> io::Result<Vec<u8>> {
            let file = File::open(directory.join(name))?;
            let metadata = file.metadata()?;
            if !metadata.is_file() || !(4..=MAX_FIXTURE as u64).contains(&metadata.len()) {
                return Err(invalid("fixture file size/type"));
            }
            let mut bytes = Vec::new();
            file.take((MAX_FIXTURE + 1) as u64).read_to_end(&mut bytes)?;
            validate_pickle(&bytes, root)?;
            Ok(bytes)
        }
        let fixtures = Self {
            state: read(directory, "state.bin", Kind::Dict)?,
            shop: read(directory, "shop.bin", Kind::Dict)?,
            dossier: read(directory, "dossier.bin", Kind::Tuple)?,
            dossier_cursor: None,
        };
        // Necessary startup bound, not a promise of a 30-second session. Each
        // stream adds 11 zlib bytes; its response/header share the first chunk.
        // Six other measured messages: creation, initial heartbeat, showGUI,
        // empty roster, revision1 refresh, and first server statistics reply.
        // Later heartbeats/statistics still consume the remaining lab budget.
        let initial_sequences = fixtures.sizes().into_iter()
            .map(|bytes| (bytes + 11).div_ceil(CHUNK_SIZE)).sum::<usize>() + 6;
        if initial_sequences > sequence_budget as usize {
            return Err(io::Error::new(io::ErrorKind::InvalidData, format!(
                "hangar fixture needs at least {initial_sequences} reliable sequences for initial sync/GUI; \
                 lab budget is {}; periodic traffic needs additional capacity",
                sequence_budget)));
        }
        Ok(fixtures)
    }

    pub fn sizes(&self) -> [usize; 3] {
        [self.state.len(), self.shop.len(), self.dossier.len()]
    }

    /// Read-only binding to the exact state already loaded for this session.
    /// It does not reread files or alter any existing fixture validation.
    pub fn state_sha256(&self) -> [u8; 32] {
        Sha256::digest(&self.state).into()
    }

    /// Immutable source bytes for a separately versioned outgoing policy. The
    /// original fixture hash/VehicleSeed binding must never become its output.
    pub(crate) fn state_bytes(&self) -> &[u8] { &self.state }

    /// Only our published granted fixture may authorize its exact native cache
    /// cursor. A client timestamp is never used to modify history or the stream.
    pub fn validate_dossier_cursor(&self,version:i64,last_change_time:i32)->io::Result<()> {
        if (version==0 && last_change_time==0) || self.dossier_cursor
            .is_some_and(|cursor| cursor.version==version && cursor.last_change_time==last_change_time) {
            Ok(())
        } else {Err(invalid("dossier cache cursor differs from authenticated fixture"))}
    }
}

struct DossierPayloadMetadata {
    version:i64,last_change_time:i32,vehicle_type_compact_descr:i32,payload_sha256:String,
}
struct DossierPreservation { dossier_cache:Option<DossierPayloadMetadata> }
struct TestGrantMetadata { grant_id:String,granted_at_ms:u64,base_profile_sha256:String }
struct DossierManifest {
    fixture_version:Option<u32>,profile_version:Option<u32>,snapshot_revision:Option<u32>,
    wire_sync_revision:Option<u32>,compatibility_catalog_revision:Option<u32>,
    grant:Option<TestGrantMetadata>,preservation:Option<DossierPreservation>,
}
struct DossierCompatibility {
    snapshot_revision:Option<u32>,wire_sync_revision:Option<u32>,compatibility_catalog_revision:Option<u32>,
    dossier_cache:Option<DossierCursor>,
}

// Typed projections with duplicate-field rejection, without adding an uncached
// procedural-macro dependency. Missing scalar fields default to0/empty and are
// rejected by the exact binding checks below; missing optional fields stayNone.
// Unknown provenance fields are skipped only in the explicitly open containers.
macro_rules! metadata_fields {
    ($name:ident,$strict:expr,{$($field:ident:$kind:ty),*$(,)?}) => {
        impl<'de> Deserialize<'de> for $name {
            fn deserialize<D:serde::Deserializer<'de>>(deserializer:D)->Result<Self,D::Error> {
                struct Fields;
                impl<'de> serde::de::Visitor<'de> for Fields {
                    type Value=$name;
                    fn expecting(&self,f:&mut std::fmt::Formatter)->std::fmt::Result {f.write_str("bounded unique metadata object")}
                    fn visit_map<M:serde::de::MapAccess<'de>>(self,mut map:M)->Result<$name,M::Error> {
                        $(let mut $field:Option<$kind>=None;)*
                        let mut keys=std::collections::BTreeSet::new();
                        while let Some(key)=map.next_key::<String>()? {
                            if keys.len()>=16 || !keys.insert(key.clone()) {return Err(serde::de::Error::custom("duplicate/too many metadata fields"));}
                            match key.as_str() {
                                $(stringify!($field)=>{$field=Some(map.next_value::<$kind>()?);},)*
                                _=>{if $strict {return Err(serde::de::Error::custom("unknown metadata field"));}
                                    map.next_value::<serde::de::IgnoredAny>()?;}
                            }
                        }
                        Ok($name {$($field:$field.unwrap_or_default()),*})
                    }
                }
                deserializer.deserialize_map(Fields)
            }
        }
    }
}
metadata_fields!(DossierCursor,true,{version:i64,last_change_time:i32,vehicle_type_compact_descr:i32});
metadata_fields!(DossierPayloadMetadata,true,{version:i64,last_change_time:i32,vehicle_type_compact_descr:i32,payload_sha256:String});
metadata_fields!(DossierPreservation,false,{dossier_cache:Option<DossierPayloadMetadata>});
metadata_fields!(TestGrantMetadata,true,{grant_id:String,granted_at_ms:u64,base_profile_sha256:String});
metadata_fields!(DossierManifest,false,{fixture_version:Option<u32>,profile_version:Option<u32>,snapshot_revision:Option<u32>,
    wire_sync_revision:Option<u32>,compatibility_catalog_revision:Option<u32>,
    grant:Option<TestGrantMetadata>,preservation:Option<DossierPreservation>});
metadata_fields!(DossierCompatibility,false,{snapshot_revision:Option<u32>,wire_sync_revision:Option<u32>,
    compatibility_catalog_revision:Option<u32>,dossier_cache:Option<DossierCursor>});

fn metadata<T:serde::de::DeserializeOwned>(directory:&Path,name:&str)->io::Result<Option<T>> {
    let file=directory.join(name);
    if !file.exists() {return Ok(None);}
    let canonical=file.canonicalize()?;
    if !canonical.starts_with(directory.canonicalize()?) {return Err(invalid("dossier metadata escapes fixture"));}
    let input=File::open(canonical)?;
    if !input.metadata()?.is_file() || input.metadata()?.len()>65536 {return Err(invalid("dossier metadata size/type"));}
    let mut bytes=Vec::new();input.take(65537).read_to_end(&mut bytes)?;
    if bytes.len()>65536 {return Err(invalid("dossier metadata grew beyond bound"));}
    serde_json::from_slice(&bytes).map(Some).map_err(|_|invalid("invalid dossier metadata schema"))
}

// This comparison validates the exact own encoder layout and native UI06 blank
// descriptor; it does not generate a replacement for the bytes being served.
// Native version81: 25 UINT16 block sizes, total block9=18; only creationTime
// at52..56 is set by our explicit grant. All played-history bytes remain zero.
fn granted_dossier_bytes(time:i32)->Vec<u8> {
    let mut descriptor=[0u8;70];descriptor[..2].copy_from_slice(&81u16.to_le_bytes());
    descriptor[20..22].copy_from_slice(&18u16.to_le_bytes());
    descriptor[52..56].copy_from_slice(&time.to_le_bytes());
    let mut result=b"\x80\x02(K\x01]((M\x01\x1cJ".to_vec();
    result.extend(time.to_le_bytes());result.extend([b'U',70]);result.extend(descriptor);result.extend(b"tet.");result
}

fn grant_dossier_cursor(directory:&Path,raw:&[u8])->io::Result<Option<DossierCursor>> {
    let manifest=metadata::<DossierManifest>(directory,"manifest.json")?;
    let compatibility=metadata::<DossierCompatibility>(directory,"compatibility.json")?;
    let manifest_cursor=manifest.as_ref().and_then(|m|m.preservation.as_ref()).and_then(|p|p.dossier_cache.as_ref());
    let compatibility_cursor=compatibility.as_ref().and_then(|c|c.dossier_cache);
    if manifest_cursor.is_none() && compatibility_cursor.is_none() {
        if raw==b"\x80\x02(K\x00]t." {return Ok(None);}
        return Err(invalid("nonempty interactive dossier requires verified grant metadata"));
    }
    let manifest=manifest.as_ref().ok_or_else(||invalid("grant manifest missing"))?;
    let compatibility=compatibility.as_ref().ok_or_else(||invalid("grant compatibility missing"))?;
    let record=manifest_cursor.ok_or_else(||invalid("grant dossier manifest cursor missing"))?;
    let cursor=compatibility_cursor.ok_or_else(||invalid("grant dossier compatibility cursor missing"))?;
    let grant=manifest.grant.as_ref().ok_or_else(||invalid("dossier test grant missing"))?;
    // Profiles3/4 add MS-1 crew/ammunition in state.bin while retaining the
    // exact profile2 IS-7 dossier grant. The bridge validates the domain
    // snapshot; this projection binds only its unchanged cache cursor/bytes.
    let supported_profile=matches!((manifest.fixture_version,manifest.profile_version,
        manifest.snapshot_revision,compatibility.snapshot_revision),
        (Some(2),Some(2),Some(2),Some(2)) | (Some(3),Some(3),Some(3),Some(3))
        | (Some(4),Some(4),Some(4),Some(4)));
    if !supported_profile
        || manifest.wire_sync_revision!=Some(1) || manifest.compatibility_catalog_revision!=Some(3)
        || compatibility.wire_sync_revision!=Some(1)
        || compatibility.compatibility_catalog_revision!=Some(3) || grant.grant_id!="test-is7-v1"
        || grant.base_profile_sha256.len()!=64 || !grant.base_profile_sha256.bytes().all(|b|b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
        || grant.granted_at_ms/1000==0 || grant.granted_at_ms/1000>i32::MAX as u64
        || cursor.version!=1 || cursor.vehicle_type_compact_descr!=7169 || cursor.last_change_time<=0
        || cursor.last_change_time as u64!=grant.granted_at_ms/1000
        || (record.version,record.last_change_time,record.vehicle_type_compact_descr)
            !=(cursor.version,cursor.last_change_time,cursor.vehicle_type_compact_descr)
        || record.payload_sha256!=format!("{:x}",Sha256::digest(raw))
        || raw!=granted_dossier_bytes(cursor.last_change_time) {
        return Err(invalid("dossier grant/payload/cursor binding differs from supported fixture"));
    }
    Ok(Some(cursor))
}

/// Own isolated service configuration. `roaming` is consumed by the original
/// lobby bootstrap; no remote centers or file/voice endpoints are configured.
pub fn creation() -> Vec<u8> {
    creation_named("p02-hangar-player").expect("static laboratory player name")
}
pub fn creation_named(name:&str) -> io::Result<Vec<u8>> {
    if !(3..=24).contains(&name.chars().count()) || name.len()>96 || name.chars().any(char::is_control) {
        return Err(invalid("native account name size/encoding"));
    }
    // Own UTC laboratory calendar, not a claim about historical region values.
    // time_utils adds day seconds; account_shared uses integer week-start index.
    let settings = b"\x80\x02}(U\x0bfile_server}U\x0avoipDomainU\x00U\x07roaming(K\x00K\x00]]tU\x0cxmpp_enabled\x89U\x11regional_settings}(U\x1astarting_time_of_a_new_dayK\x00U\x1astarting_day_of_a_new_weekK\x00uU\x06wallet(\x89\x89tu.";
    let mut payload = crate::account091::ENTITY_ID.to_le_bytes().to_vec();
    payload.extend(0u16.to_le_bytes());
    for value in [b"ru_0.9.1_2".as_slice(), name.as_bytes(), settings.as_slice()] {
        payload.push(value.len() as u8);
        payload.extend(value);
    }
    let mut output = vec![5];
    output.extend((payload.len() as u16).to_le_bytes());
    output.extend(payload);
    Ok(output)
}

#[derive(Clone, Copy, Debug, PartialEq)]
enum Kind { Scalar, List, Tuple, Dict, Mark }
#[derive(Clone, Copy)]
struct Value { kind: Kind, depth: usize }

/// Validate only the literal opcode language emitted by tools/hangar_state.py.
/// This is a structural scanner, not pickle deserialization: no imports, object
/// constructors, memo references, persistent IDs, or executable opcodes exist.
fn validate_pickle(bytes: &[u8], root: Kind) -> io::Result<()> {
    if !(4..=MAX_FIXTURE).contains(&bytes.len()) || bytes[..2] != [0x80, 2] {
        return Err(invalid("fixture protocol/size"));
    }
    fn take<'a>(bytes: &'a [u8], cursor: &mut usize, length: usize) -> io::Result<&'a [u8]> {
        let end = cursor.checked_add(length).ok_or_else(|| invalid("fixture length overflow"))?;
        let result = bytes.get(*cursor..end).ok_or_else(|| invalid("truncated fixture"))?;
        *cursor = end;
        Ok(result)
    }
    let mut cursor = 2;
    let mut nodes = 0;
    let mut stack: Vec<Value> = Vec::new();
    while cursor < bytes.len() {
        nodes += 1;
        if nodes > MAX_NODES { return Err(invalid("fixture node budget")); }
        let opcode = take(bytes, &mut cursor, 1)?[0];
        let value = match opcode {
            b'N' | 0x88 | 0x89 => Some(Value { kind: Kind::Scalar, depth: 0 }),
            b'K' | b'M' | b'J' => {
                take(bytes, &mut cursor, match opcode { b'K' => 1, b'M' => 2, _ => 4 })?;
                Some(Value { kind: Kind::Scalar, depth: 0 })
            },
            b'G' => {
                let raw: [u8; 8] = take(bytes, &mut cursor, 8)?.try_into().map_err(|_| invalid("float length"))?;
                if !f64::from_be_bytes(raw).is_finite() { return Err(invalid("nonfinite fixture float")); }
                Some(Value { kind: Kind::Scalar, depth: 0 })
            },
            b'U' | b'T' => {
                let length = if opcode == b'U' {
                    take(bytes, &mut cursor, 1)?[0] as usize
                } else {
                    let raw: [u8; 4] = take(bytes, &mut cursor, 4)?.try_into().map_err(|_| invalid("string length"))?;
                    u32::from_le_bytes(raw) as usize
                };
                if length > MAX_FIXTURE { return Err(invalid("fixture string budget")); }
                take(bytes, &mut cursor, length)?;
                Some(Value { kind: Kind::Scalar, depth: 0 })
            },
            b']' => Some(Value { kind: Kind::List, depth: 1 }),
            b')' => Some(Value { kind: Kind::Tuple, depth: 1 }),
            b'}' => Some(Value { kind: Kind::Dict, depth: 1 }),
            b'(' => Some(Value { kind: Kind::Mark, depth: 0 }),
            b'e' | b'u' | b't' => {
                let mark = stack.iter().rposition(|v| v.kind == Kind::Mark)
                    .ok_or_else(|| invalid("fixture missing mark"))?;
                let count = stack.len() - mark - 1;
                let depth = 1 + stack[mark + 1..].iter().map(|v| v.depth).max().unwrap_or(0);
                if depth > MAX_DEPTH { return Err(invalid("fixture depth budget")); }
                if opcode == b't' {
                    stack.truncate(mark);
                    Some(Value { kind: Kind::Tuple, depth })
                } else {
                    if mark == 0 || (opcode == b'u' && count % 2 != 0) {
                        return Err(invalid("fixture container arity"));
                    }
                    let target = &mut stack[mark - 1];
                    if target.kind != if opcode == b'e' { Kind::List } else { Kind::Dict } {
                        return Err(invalid("fixture container type"));
                    }
                    target.depth = target.depth.max(depth);
                    stack.truncate(mark);
                    None
                }
            },
            b'.' => {
                if cursor != bytes.len() || stack.len() != 1 || stack[0].kind != root {
                    return Err(invalid("fixture root/trailing bytes"));
                }
                return Ok(());
            },
            _ => return Err(invalid("fixture forbidden opcode")),
        };
        if let Some(value) = value { stack.push(value); }
        if stack.len() > MAX_NODES || stack.iter().filter(|v| v.kind == Kind::Mark).count() > MAX_DEPTH {
            return Err(invalid("fixture stack/depth budget"));
        }
    }
    Err(invalid("fixture missing stop"))
}

/// Candidate 0x3b + client method slot24 from the measured native range and
/// Account.def's stable size ordering. Verify original Account.showGUI line573
/// normal return offset297 in the native trace before reporting this as PASS.
pub fn show_gui(database_id: i32) -> io::Result<Vec<u8>> {
    if database_id <= 0 { return Err(invalid("laboratory database ID")); }
    let mut context = b"\x80\x02}(U\x0adatabaseIDJ".to_vec();
    context.extend(database_id.to_le_bytes());
    // Original local-service switches read by gui.game_control controllers.
    // AOGAS defaults true when omitted; this laboratory enables no such service.
    context.extend(b"U\x0eisAogasEnabled\x89U\x0ecollectUiStats\x89U\x0blogUXEvents\x89u.");
    let mut payload = vec![context.len() as u8];
    payload.extend(context);
    method(0x53, &payload)
}

/// Initial sync results use the original SyncController's RES_STREAM path.
/// Shop RES_SUCCESS ignores its ext payload and cannot populate the catalog.
/// Bodies fit the existing <=512-byte reliable packet bound. The gateway must
/// queue these gradually instead of overflowing its eight-packet send window.
pub fn response(request: &Request, fixtures: &Fixtures) -> io::Result<Vec<Vec<u8>>> {
    if request.id <= 0 { return Err(invalid("request ID")); }
    let raw = match request.command {
        100 => &fixtures.state,
        300 => &fixtures.shop,
        600 => &fixtures.dossier,
        _ => return Err(invalid("unimplemented hangar command")),
    };
    response_raw(request, raw)
}

/// Explicit Account-only outgoing service projection. Its caller binds the
/// approved source and projected digest; this encoder still rejects objects,
/// malformed roots, unbounded data and every non-Account command.
pub(crate) fn response_state(request: &Request, state: &[u8]) -> io::Result<Vec<Vec<u8>>> {
    if request.id <= 0 || request.command != 100 {return Err(invalid("Account policy request"));}
    validate_pickle(state, Kind::Dict)?;
    response_raw(request, state)
}

fn response_raw(request: &Request, raw: &[u8]) -> io::Result<Vec<Vec<u8>>> {
    let mut payload = request.id.to_le_bytes().to_vec();
    payload.extend(1i16.to_le_bytes()); // RES_STREAM
    payload.push(0); // error STRING
    payload.push(EMPTY_DICT.len() as u8);
    payload.extend(EMPTY_DICT);
    let prefix = method(0x4d, &payload)?;
    stream(request.id, raw, prefix)
}

/// Complete the measured second stage of revision1 synchronization. An empty
/// dictionary would mean a new full state to Account._update and erase values;
/// this explicit no-change diff preserves the server-owned inventory/statistics.
/// The gateway must require prior revision1 stream dispatch and a fresh requestID.
pub fn response_refresh(request: &Request) -> io::Result<Vec<u8>> {
    if request.id <= 0 || request.command != 100 { return Err(invalid("unmeasured refresh request")); }
    let ext = b"\x80\x02}(U\x07prevRevK\x01U\x03revK\x01u.";
    let mut payload = request.id.to_le_bytes().to_vec();
    payload.extend(0i16.to_le_bytes()); // RES_SUCCESS: actual no-change revision1.
    payload.push(0);
    payload.push(ext.len() as u8);
    payload.extend(ext);
    method(0x4d, &payload)
}

fn method(id: u8, payload: &[u8]) -> io::Result<Vec<u8>> {
    // No extended VAR1 method length needed: all RPC payloads remain <255 B.
    if payload.len() >= 255 { return Err(invalid("unmeasured extended method length")); }
    let mut result = vec![0x13, id, payload.len() as u8]; // selectPlayerEntity
    result.extend(payload);
    Ok(result)
}

fn variable16(id: u8, payload: &[u8]) -> io::Result<Vec<u8>> {
    if payload.len() > 509 { return Err(invalid("resource body size")); }
    let mut result = vec![id];
    result.extend((payload.len() as u16).to_le_bytes());
    result.extend(payload);
    Ok(result)
}

fn stream(id: i16, raw: &[u8], mut first: Vec<u8>) -> io::Result<Vec<Vec<u8>>> {
    if raw.is_empty() || raw.len() > MAX_FIXTURE { return Err(invalid("stream payload size")); }
    // One bounded stored DEFLATE block. Compression is optional; checksums are not.
    let mut data = vec![0x78, 0x01, 0x01];
    data.extend((raw.len() as u16).to_le_bytes());
    data.extend((!(raw.len() as u16)).to_le_bytes());
    data.extend(raw);
    let (mut a, mut b) = (1u32, 0u32);
    for x in raw { a = (a + *x as u32) % 65521; b = (b + a) % 65521; }
    data.extend(((b << 16) | a).to_be_bytes());
    let mut crc = 0xffffffffu32;
    for x in &data {
        crc ^= *x as u32;
        for _ in 0..8 { crc = (crc >> 1) ^ if crc & 1 != 0 { 0xedb88320 } else { 0 }; }
    }
    crc ^= 0xffffffff;
    // game.onStreamComplete expects protocol2 (length, signed Python2 crc32).
    let mut description = vec![0x80, 2, b'J'];
    description.extend((data.len() as i32).to_le_bytes());
    description.push(b'J');
    description.extend(crc.to_le_bytes());
    description.extend([0x86, b'.']);
    let mut header = id.to_le_bytes().to_vec();
    header.push(description.len() as u8);
    header.extend(description);
    first.extend(variable16(52, &header)?);

    let count = data.len().div_ceil(CHUNK_SIZE);
    let mut output = Vec::with_capacity(count);
    for (sequence, chunk) in data.chunks(CHUNK_SIZE).enumerate() {
        let mut fragment = id.to_le_bytes().to_vec();
        fragment.extend([sequence as u8, u8::from(sequence + 1 == count)]);
        fragment.extend(chunk);
        let mut body = if sequence == 0 { std::mem::take(&mut first) } else { Vec::new() };
        body.extend(variable16(53, &fragment)?);
        if body.len() > 512 { return Err(invalid("stream reliable body size")); }
        output.push(body);
    }
    Ok(output)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn dossier_request(id:i16,version:i64,time:i32,reserved:i32)->Vec<u8> {
        let mut packet=vec![0x8e,20,0];packet.extend(id.to_le_bytes());packet.extend(600i16.to_le_bytes());
        packet.extend(version.to_le_bytes());packet.extend(time.to_le_bytes());packet.extend(reserved.to_le_bytes());packet
    }

    #[test]
    fn native_initial_cache_hints_are_interactive_bounded_and_not_revision_updates() {
        fn sync(command:i16,revision:i64,a:i32,b:i32)->Vec<u8> {
            let mut packet=dossier_request(221,revision,a,b);
            packet[5..7].copy_from_slice(&command.to_le_bytes());packet
        }
        // UI09 packet367: exact native Account and Shop persistent descriptors.
        for (command,a,b) in [(100,-1176871600,0),(300,518,-846328027)] {
            let packet=sync(command,0,a,b);
            assert!(requests(&packet).is_err());
            assert!(crate::account091::requests(&packet).is_err());
            assert_eq!(requests_interactive(&packet).unwrap(),vec![Incoming::CachedSync {
                request:Request{id:221,command},descriptor_a:a,descriptor_b:b}]);
            for n in 1..packet.len() {assert!(requests_interactive(&packet[..n]).is_err());}
            assert!(requests_interactive(&[packet.clone(),packet].concat()).is_err());
        }
        // CRC/hash are opaque signed32 data. No supplied cache object is read.
        for a in [i32::MIN,-1,1,i32::MAX] {assert!(requests_interactive(&sync(100,0,a,0)).is_ok());}
        for size in [1,(MAX_FIXTURE+64) as i32] {
            for crc in [i32::MIN,0,i32::MAX] {assert!(requests_interactive(&sync(300,0,size,crc)).is_ok());}
        }
        for bad in [sync(100,0,1,1),sync(100,2,1,0),sync(100,-1,1,0),
                    sync(300,0,0,1),sync(300,0,-1,0),sync(300,0,(MAX_FIXTURE+65) as i32,0),
                    sync(300,1,518,1),sync(300,i64::MAX,518,1),sync(301,0,518,1)] {
            assert!(requests_interactive(&bad).is_err());
        }
        for command in [100,300] {
            assert_eq!(requests_interactive(&sync(command,0,0,0)).unwrap(),
                vec![Incoming::Sync(Request{id:221,command})]);
            let mut invalid=sync(command,0,1,0);invalid[3..5].fill(0);
            assert!(requests_interactive(&invalid).is_err());
        }
        assert_eq!(requests_interactive(&sync(100,1,0,0)).unwrap(),
            vec![Incoming::Refresh(Request{id:221,command:100})]);
    }

    #[test]
    fn measured_cached_revision1_refresh_preserves_hash_and_rejects_unknown_versions() {
        let mut packet=dossier_request(224,1,-1176871600,0);
        packet[5..7].copy_from_slice(&100i16.to_le_bytes());
        assert!(requests(&packet).is_err());
        assert!(crate::account091::requests(&packet).is_err());
        assert_eq!(requests_interactive(&packet).unwrap(),vec![Incoming::CachedRefresh {
            request:Request{id:224,command:100},persistent_hash:-1176871600}]);
        for n in 1..packet.len() {assert!(requests_interactive(&packet[..n]).is_err());}
        for revision in [-1,2,i64::MAX] {
            let mut invalid=packet.clone();invalid[7..15].copy_from_slice(&revision.to_le_bytes());
            assert!(requests_interactive(&invalid).is_err());
        }
        let mut invalid=packet.clone();invalid[19]=1;assert!(requests_interactive(&invalid).is_err());
        invalid=packet.clone();invalid[3..5].fill(0);assert!(requests_interactive(&invalid).is_err());
        assert!(requests_interactive(&[packet.clone(),packet].concat()).is_err());
    }

    #[test]
    fn granted_dossier_cursor_is_interactive_exact_and_does_not_enable_arbitrary_args() {
        let time=1791125440;
        let packet=dossier_request(223,1,time,0);
        assert!(requests(&packet).is_err());
        assert_eq!(requests_interactive(&packet).unwrap(),vec![Incoming::DossierSync {
            request:Request {id:223,command:600},version:1,last_change_time:time}]);
        for bad in [dossier_request(0,1,time,0),dossier_request(223,2,time,0),
                    dossier_request(223,0,time,0),dossier_request(223,1,0,0),
                    dossier_request(223,1,-1,0),dossier_request(223,1,time,1)] {
            assert!(requests_interactive(&bad).is_err());
        }
        assert!(requests_interactive(&[packet.clone(),packet].concat()).is_err());
        let old=Fixtures {state:EMPTY_DICT.to_vec(),shop:EMPTY_DICT.to_vec(),
            dossier:b"\x80\x02(K\x00]t.".to_vec(),dossier_cursor:None};
        old.validate_dossier_cursor(0,0).unwrap();assert!(old.validate_dossier_cursor(1,time).is_err());
        let granted=Fixtures {dossier:granted_dossier_bytes(time),dossier_cursor:Some(DossierCursor {
            version:1,last_change_time:time,vehicle_type_compact_descr:7169}),..old};
        granted.validate_dossier_cursor(0,0).unwrap();granted.validate_dossier_cursor(1,time).unwrap();
        for (version,changed) in [(0,time),(1,time-1),(1,time+1),(2,time),(1,0)] {
            assert!(granted.validate_dossier_cursor(version,changed).is_err());
        }
    }

    #[test]
    fn granted_fixture_binds_metadata_timestamp_native_blank_and_hash_before_acceptance() {
        let epoch=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let directory=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/wg-probe")
            .join(format!("dossier-metadata-{}-{epoch}",std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        for name in ["state.bin","shop.bin"] {std::fs::write(directory.join(name),EMPTY_DICT).unwrap();}
        let time=1791125440;let raw=granted_dossier_bytes(time);
        validate_pickle(&raw,Kind::Tuple).unwrap();assert_eq!(raw.len(),92);
        std::fs::write(directory.join("dossier.bin"),&raw).unwrap();
        assert!(Fixtures::load_interactive(&directory).is_err());
        let cursor=serde_json::json!({"version":1,"last_change_time":time,"vehicle_type_compact_descr":7169});
        let mut record=cursor.clone();record["payload_sha256"]=serde_json::json!(format!("{:x}",Sha256::digest(&raw)));
        let manifest=serde_json::json!({"fixture_version":2,"profile_version":2,"snapshot_revision":2,
            "wire_sync_revision":1,"compatibility_catalog_revision":3,"preservation":{"dossier_cache":record},
            "grant":{"grant_id":"test-is7-v1","granted_at_ms":1791125440000u64,"base_profile_sha256":"a".repeat(64)}});
        let compatibility=serde_json::json!({"snapshot_revision":2,"wire_sync_revision":1,
            "compatibility_catalog_revision":3,"dossier_cache":cursor});
        fn write_json(directory:&Path,name:&str,value:&serde_json::Value) {
            std::fs::write(directory.join(name),serde_json::to_vec(value).unwrap()).unwrap();
        }
        write_json(&directory,"manifest.json",&manifest);write_json(&directory,"compatibility.json",&compatibility);
        let verified=Fixtures::load_interactive(&directory).unwrap();verified.validate_dossier_cursor(1,time).unwrap();
        for (field,value) in [("version",serde_json::json!(2)),("last_change_time",serde_json::json!(time+1)),
                ("vehicle_type_compact_descr",serde_json::json!(2)),("payload_sha256",serde_json::json!("0".repeat(64)))] {
            let mut wrong=manifest.clone();wrong["preservation"]["dossier_cache"][field]=value;
            write_json(&directory,"manifest.json",&wrong);assert!(Fixtures::load_interactive(&directory).is_err());
        }
        write_json(&directory,"manifest.json",&manifest);
        let duplicate=serde_json::to_string(&manifest).unwrap().replace("\"version\":1","\"version\":1,\"version\":1");
        std::fs::write(directory.join("manifest.json"),duplicate).unwrap();
        assert!(Fixtures::load_interactive(&directory).is_err());
        let mut wrong=manifest.clone();wrong["preservation"]["dossier_cache"]["extra"]=serde_json::json!(0);
        write_json(&directory,"manifest.json",&wrong);assert!(Fixtures::load_interactive(&directory).is_err());
        write_json(&directory,"manifest.json",&manifest);
        let mut wrong=compatibility.clone();wrong["dossier_cache"]["last_change_time"]=serde_json::json!(time+1);
        write_json(&directory,"compatibility.json",&wrong);assert!(Fixtures::load_interactive(&directory).is_err());
        write_json(&directory,"compatibility.json",&compatibility);
        let mut played=raw.clone();played[87]=1; // Last history byte before TUPLE, not an opcode.
        let mut wrong=manifest.clone();wrong["preservation"]["dossier_cache"]["payload_sha256"]=
            serde_json::json!(format!("{:x}",Sha256::digest(&played)));
        std::fs::write(directory.join("dossier.bin"),&played).unwrap();write_json(&directory,"manifest.json",&wrong);
        assert!(Fixtures::load_interactive(&directory).is_err());
        std::fs::write(directory.join("dossier.bin"),&raw).unwrap();
        let mut wrong=manifest.clone();wrong["grant"]["granted_at_ms"]=serde_json::json!(1791125441000u64);
        write_json(&directory,"manifest.json",&wrong);assert!(Fixtures::load_interactive(&directory).is_err());
        write_json(&directory,"manifest.json",&manifest);
        std::fs::write(directory.join("dossier.bin"),b"\x80\x02(K\x00]t.").unwrap();
        assert!(Fixtures::load_interactive(&directory).is_err());
        write_json(&directory,"manifest.json",&serde_json::json!({}));
        write_json(&directory,"compatibility.json",&serde_json::json!({}));
        Fixtures::load_interactive(&directory).unwrap().validate_dossier_cursor(0,0).unwrap();
    }

    #[test]
    fn profile3_preserves_granted_dossier_and_rejects_mixed_or_future_versions() {
        // Parser integration inputs only: no invented crew descriptors and no
        // claim that these small state dictionaries are native crew evidence.
        let epoch=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let directory=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/wg-probe")
            .join(format!("dossier-profile3-{}-{epoch}",std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        for name in ["state.bin","shop.bin"] {std::fs::write(directory.join(name),EMPTY_DICT).unwrap();}
        let time=1791125440;let raw=granted_dossier_bytes(time);
        std::fs::write(directory.join("dossier.bin"),&raw).unwrap();
        let cursor=serde_json::json!({"version":1,"last_change_time":time,"vehicle_type_compact_descr":7169});
        let mut record=cursor.clone();record["payload_sha256"]=serde_json::json!(format!("{:x}",Sha256::digest(&raw)));
        let manifest=serde_json::json!({"fixture_version":3,"profile_version":3,"snapshot_revision":3,
            "wire_sync_revision":1,"compatibility_catalog_revision":3,"preservation":{"dossier_cache":record},
            "grant":{"grant_id":"test-is7-v1","granted_at_ms":1791125440000u64,"base_profile_sha256":"a".repeat(64)}});
        let compatibility=serde_json::json!({"snapshot_revision":3,"wire_sync_revision":1,
            "compatibility_catalog_revision":3,"dossier_cache":cursor});
        let load=|manifest:&serde_json::Value,compatibility:&serde_json::Value| {
            for (name,value) in [("manifest.json",manifest),("compatibility.json",compatibility)] {
                std::fs::write(directory.join(name),serde_json::to_vec(value).unwrap()).unwrap();
            }
            Fixtures::load_interactive(&directory)
        };
        let verified=load(&manifest,&compatibility).unwrap();
        assert_eq!(verified.dossier,raw);
        verified.validate_dossier_cursor(0,0).unwrap();
        verified.validate_dossier_cursor(1,time).unwrap();
        for (version,changed) in [(1,time-1),(1,time+1),(2,time)] {
            assert!(verified.validate_dossier_cursor(version,changed).is_err());
        }
        // All16 combinations of old/new domain revisions: only coherent2/3.
        for bits in 0..16 {
            let versions=std::array::from_fn::<_,4,_>(|i|2+((bits>>i)&1));
            let mut m=manifest.clone();let mut c=compatibility.clone();
            for (key,value) in ["fixture_version","profile_version","snapshot_revision"].into_iter().zip(versions) {
                m[key]=serde_json::json!(value);
            }
            c["snapshot_revision"]=serde_json::json!(versions[3]);
            assert_eq!(load(&m,&c).is_ok(),bits==0 || bits==15,"versions={versions:?}");
        }
        for unsupported in [serde_json::json!(4),serde_json::Value::Null] {
            for key in ["fixture_version","profile_version","snapshot_revision"] {
                let mut wrong=manifest.clone();wrong[key]=unsupported.clone();
                assert!(load(&wrong,&compatibility).is_err());
            }
            let mut wrong=compatibility.clone();wrong["snapshot_revision"]=unsupported;
            assert!(load(&manifest,&wrong).is_err());
        }
        let mut future_manifest=manifest.clone();let mut future_compatibility=compatibility.clone();
        for key in ["fixture_version","profile_version","snapshot_revision"] {
            future_manifest[key]=serde_json::json!(5);
        }
        future_compatibility["snapshot_revision"]=serde_json::json!(5);
        assert!(load(&future_manifest,&future_compatibility).is_err());
        for key in ["wire_sync_revision","compatibility_catalog_revision"] {
            let mut wrong=manifest.clone();wrong[key]=serde_json::json!(4);
            assert!(load(&wrong,&compatibility).is_err());
            let mut wrong=compatibility.clone();wrong[key]=serde_json::json!(4);
            assert!(load(&manifest,&wrong).is_err());
        }
        // A crew grant cannot replace the preserved IS-7 grant or its cursor.
        let mut wrong=manifest.clone();wrong["grant"]["grant_id"]=serde_json::json!("test-ms1-crew-v1");
        assert!(load(&wrong,&compatibility).is_err());
        let mut wrong=manifest.clone();wrong["grant"]["granted_at_ms"]=serde_json::json!(1791125441000u64);
        assert!(load(&wrong,&compatibility).is_err());
        let mut wrong=manifest.clone();wrong["preservation"]["dossier_cache"]["payload_sha256"]=serde_json::json!("0".repeat(64));
        assert!(load(&wrong,&compatibility).is_err());
        let mut wrong=compatibility.clone();wrong["dossier_cache"]["last_change_time"]=serde_json::json!(time+1);
        assert!(load(&manifest,&wrong).is_err());
        let mut played=raw.clone();played[87]=1;
        std::fs::write(directory.join("dossier.bin"),&played).unwrap();
        let mut wrong=manifest.clone();wrong["preservation"]["dossier_cache"]["payload_sha256"]=
            serde_json::json!(format!("{:x}",Sha256::digest(&played)));
        assert!(load(&wrong,&compatibility).is_err());
        std::fs::write(directory.join("dossier.bin"),&raw).unwrap();
        assert_eq!(load(&manifest,&compatibility).unwrap().dossier,raw);
    }

    #[test]
    fn profile4_metadata_requires_coherent_versions_and_unchanged_dossier() {
        // These are parser fixtures only. They do not assert native ammunition
        // compatibility; the bridge and the separate native verifier own that.
        let epoch=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let directory=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/wg-probe")
            .join(format!("dossier-profile4-{}-{epoch}",std::process::id()));
        std::fs::create_dir_all(&directory).unwrap();
        for name in ["state.bin","shop.bin"] {std::fs::write(directory.join(name),EMPTY_DICT).unwrap();}
        let time=1791125440;let raw=granted_dossier_bytes(time);
        std::fs::write(directory.join("dossier.bin"),&raw).unwrap();
        let cursor=serde_json::json!({"version":1,"last_change_time":time,"vehicle_type_compact_descr":7169});
        let mut record=cursor.clone();record["payload_sha256"]=serde_json::json!(format!("{:x}",Sha256::digest(&raw)));
        let manifest=serde_json::json!({"fixture_version":4,"profile_version":4,"snapshot_revision":4,
            "wire_sync_revision":1,"compatibility_catalog_revision":3,"preservation":{"dossier_cache":record},
            "grant":{"grant_id":"test-is7-v1","granted_at_ms":1791125440000u64,"base_profile_sha256":"a".repeat(64)}});
        let compatibility=serde_json::json!({"snapshot_revision":4,"wire_sync_revision":1,
            "compatibility_catalog_revision":3,"dossier_cache":cursor});
        let load=|manifest:&serde_json::Value,compatibility:&serde_json::Value| {
            for (name,value) in [("manifest.json",manifest),("compatibility.json",compatibility)] {
                std::fs::write(directory.join(name),serde_json::to_vec(value).unwrap()).unwrap();
            }
            Fixtures::load_interactive(&directory)
        };
        // All 81 combinations of the three supported domain versions. A new
        // snapshot cannot silently combine old/new manifest and mapping IDs.
        for encoded in 0..81usize {
            let mut n=encoded;
            let versions=std::array::from_fn::<_,4,_>(|_| {let version=2+n%3;n/=3;version});
            let mut m=manifest.clone();let mut c=compatibility.clone();
            for (key,value) in ["fixture_version","profile_version","snapshot_revision"].into_iter().zip(versions) {
                m[key]=serde_json::json!(value);
            }
            c["snapshot_revision"]=serde_json::json!(versions[3]);
            assert_eq!(load(&m,&c).is_ok(),versions.iter().all(|v|*v==versions[0]),"versions={versions:?}");
        }
        for unsupported in [serde_json::json!(5),serde_json::json!(-1),serde_json::json!(true),
                            serde_json::json!(4.0),serde_json::json!("4"),serde_json::Value::Null] {
            let mut m=manifest.clone();let mut c=compatibility.clone();
            for key in ["fixture_version","profile_version","snapshot_revision"] {m[key]=unsupported.clone();}
            c["snapshot_revision"]=unsupported;
            assert!(load(&m,&c).is_err());
        }
        let verified=load(&manifest,&compatibility).unwrap();
        assert_eq!(verified.dossier,raw);
        verified.validate_dossier_cursor(0,0).unwrap();
        verified.validate_dossier_cursor(1,time).unwrap();
        for (version,changed) in [(1,time-1),(1,time+1),(2,time),(0,time)] {
            assert!(verified.validate_dossier_cursor(version,changed).is_err());
        }
        for key in ["wire_sync_revision","compatibility_catalog_revision"] {
            let mut m=manifest.clone();m[key]=serde_json::json!(4);
            assert!(load(&m,&compatibility).is_err());
            let mut c=compatibility.clone();c[key]=serde_json::json!(4);
            assert!(load(&manifest,&c).is_err());
        }
        let mut wrong=manifest.clone();wrong["grant"]["grant_id"]=serde_json::json!("test-ms1-ammo-v1");
        assert!(load(&wrong,&compatibility).is_err());
        let mut played=raw.clone();played[87]=1;
        std::fs::write(directory.join("dossier.bin"),&played).unwrap();
        let mut wrong=manifest.clone();wrong["preservation"]["dossier_cache"]["payload_sha256"]=
            serde_json::json!(format!("{:x}",Sha256::digest(&played)));
        assert!(load(&wrong,&compatibility).is_err());
        std::fs::write(directory.join("dossier.bin"),&raw).unwrap();
        assert_eq!(load(&manifest,&compatibility).unwrap().dossier,raw);
    }

    #[test]
    fn fixture_rejects_executable_opcodes_truncations_and_trailing_bytes() {
        let valid = b"\x80\x02}(U\x01x](K\x01K\x02eu.";
        validate_pickle(valid, Kind::Dict).unwrap();
        for length in 0..valid.len() { assert!(validate_pickle(&valid[..length], Kind::Dict).is_err()); }
        for opcode in [b'c', b'R', b'b', b'P', b'Q', b'0', b'1', b'2', b'q', b'h', 0x81, 0x82] {
            assert!(validate_pickle(&[0x80, 2, opcode, b'.'], Kind::Dict).is_err());
        }
        assert!(validate_pickle(&[EMPTY_DICT, b"x"].concat(), Kind::Dict).is_err());
        assert!(validate_pickle(b"\x80\x02}.\x80\x02}.", Kind::Dict).is_err());
        assert!(validate_pickle(b"\x80\x02}(U\x01xu.", Kind::Dict).is_err());
        assert!(validate_pickle(b"\x80\x02}.", Kind::Tuple).is_err());
    }

    #[test]
    fn fixture_limits_nested_containers_and_untrusted_lengths() {
        let mut nested = vec![0x80, 2];
        for _ in 0..17 { nested.extend(b"]("); }
        nested.extend(b"N"); nested.extend(vec![b'e'; 17]); nested.push(b'.');
        assert!(validate_pickle(&nested, Kind::List).is_err());
        assert!(validate_pickle(b"\x80\x02T\xff\xff\xff\xff.", Kind::Dict).is_err());
        let mut nonfinite = vec![0x80, 2, b'G']; nonfinite.extend(f64::NAN.to_be_bytes()); nonfinite.push(b'.');
        assert!(validate_pickle(&nonfinite, Kind::Scalar).is_err());
        assert!(validate_pickle(&vec![0; MAX_FIXTURE + 1], Kind::Dict).is_err());
    }

    #[test]
    fn fixture_loader_rejects_initial_traffic_that_cannot_fit_the_lab_budget() {
        // File-loader integration with valid, data-only dictionary literals.
        // These are parser/budget inputs, not simulated compatibility evidence.
        fn dictionary(bytes: usize) -> Vec<u8> {
            assert!(bytes >= 14);
            let length = bytes - 14;
            let mut raw = b"\x80\x02}(U\x01xT".to_vec();
            raw.extend((length as u32).to_le_bytes());
            raw.resize(raw.len() + length, b'x');
            raw.extend(b"u.");
            assert_eq!(raw.len(), bytes);
            raw
        }
        // Preserve these small inputs under ignored local/ for diagnosis. A
        // fresh directory prevents overwriting earlier runs; no client is read.
        let root = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/wg-probe");
        std::fs::create_dir_all(&root).unwrap();
        let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let run = root.join(format!("fixture-budget-{}-{stamp}", std::process::id()));
        std::fs::create_dir(&run).unwrap();
        for (label, state_bytes, expected_error) in [
            ("minimum_fits_32", 9589, None),
            ("minimum_needs_33", 9590, Some("at least 33 reliable sequences")),
            ("parser_max_exceeds_transport", MAX_FIXTURE, Some("at least 49 reliable sequences")),
        ] {
            let directory = run.join(label);
            std::fs::create_dir(&directory).unwrap();
            std::fs::write(directory.join("state.bin"), dictionary(state_bytes)).unwrap();
            std::fs::write(directory.join("shop.bin"), dictionary(389)).unwrap();
            std::fs::write(directory.join("dossier.bin"), b"\x80\x02(K\x00]t.").unwrap();
            let result = Fixtures::load(&directory);
            if let Some(message) = expected_error {
                let error = result.unwrap_err();
                assert_eq!(error.kind(), io::ErrorKind::InvalidData);
                assert!(error.to_string().contains(message), "{error}");
            } else {
                let fixtures = result.unwrap();
                let actual_stream_packets = [100, 300, 600].into_iter().map(|command| {
                    response(&Request { id: 221, command }, &fixtures).unwrap().len()
                }).sum::<usize>();
                assert_eq!(actual_stream_packets, 26);
                assert_eq!(actual_stream_packets + 6, crate::transport091::MAX_SEQUENCE as usize);
            }
        }
    }

    #[test]
    fn stream_chunks_fit_transport_and_last_marker_is_unique() {
        let raw = vec![b'x'; MAX_FIXTURE];
        let packets = stream(221, &raw, vec![]).unwrap();
        assert_eq!(packets.len(), 41);
        let mut assembled: Vec<u8> = Vec::new();
        for (index, packet) in packets.iter().enumerate() {
            assert!(packet.len() <= 512);
            let offset = if index == 0 { 3 + u16::from_le_bytes([packet[1], packet[2]]) as usize } else { 0 };
            let fragment = &packet[offset..];
            assert_eq!(fragment[0], 53);
            assert_eq!(u16::from_le_bytes([fragment[1], fragment[2]]) as usize, fragment.len() - 3);
            assert_eq!(&fragment[3..5], &221i16.to_le_bytes());
            assert_eq!(fragment[5] as usize, index);
            assert_eq!(fragment[6], u8::from(index + 1 == packets.len()));
            assembled.extend(&fragment[7..]);
        }
        assert_eq!(&assembled[7..7 + raw.len()], raw.as_slice());
        assert_eq!(assembled.len(), raw.len() + 11);
        assert!(stream(221, &vec![0; MAX_FIXTURE + 1], vec![]).is_err());
    }

    #[test]
    fn response_does_not_accept_other_commands_and_gui_has_one_context() {
        let fixtures = Fixtures { state: EMPTY_DICT.to_vec(), shop: EMPTY_DICT.to_vec(), dossier: b"\x80\x02).".to_vec(), dossier_cursor:None };
        assert!(response(&Request { id: 221, command: 999 }, &fixtures).is_err());
        assert!(response(&Request { id: 0, command: 100 }, &fixtures).is_err());
        let gui = show_gui(1).unwrap();
        assert_eq!(&gui[..2], &[0x13, 0x53]);
        assert_eq!(gui[2] as usize, gui.len() - 3);
        assert_eq!(gui[3] as usize, gui.len() - 4);
        validate_pickle(&gui[4..], Kind::Dict).unwrap();
        assert!(show_gui(0).is_err());
        assert!(show_gui(-1).is_err());
    }

    #[test]
    fn creation_has_only_local_service_configuration() {
        let packet = creation();
        assert_eq!(packet[0], 5);
        assert_eq!(u16::from_le_bytes([packet[1], packet[2]]) as usize, packet.len() - 3);
        let mut cursor = 9;
        for _ in 0..2 { cursor += 1 + packet[cursor] as usize; }
        let length = packet[cursor] as usize;
        assert_eq!(cursor + 1 + length, packet.len());
        validate_pickle(&packet[cursor + 1..], Kind::Dict).unwrap();
    }

    // Native gui-01 application bytes, without the independently validated token.
    fn chat_packet(id: i64, command: u8) -> Vec<u8> {
        let mut packet = vec![0x93, 25, 0];
        packet.extend(id.to_le_bytes()); packet.push(command);
        packet.extend(0i32.to_le_bytes());
        packet.extend((if command == 10 { -1i64 } else { 0 }).to_le_bytes());
        packet.extend([0; 4]); packet
    }

    #[test]
    fn measured_chat_bundle_rejects_unknown_shapes_and_truncated_tail() {
        let packet = chat_packet(1, 10);
        assert_eq!(requests(&packet).unwrap(), vec![Incoming::Chat(ChatRequest { id: 1, command: 10 })]);
        assert!(requests(&[]).unwrap().is_empty());
        for length in 1..packet.len() { assert!(requests(&packet[..length]).is_err()); }
        for offset in [0, 1, 2, 11, 12, 15, 16, 23, 24, 25, 26, 27] {
            let mut wrong = packet.clone(); wrong[offset] ^= 0x80;
            assert!(requests(&wrong).is_err(), "chat offset {offset}");
        }
        assert!(requests(&chat_packet(0, 10)).is_err());
        assert!(requests(&chat_packet(30001, 10)).is_err());
        assert!(requests(&chat_packet(1, 39)).is_err());
        assert!(requests(&[packet.clone(), packet.clone()].concat()).is_err());
        let bundle = [packet, chat_packet(2, 9), chat_packet(3, 30)].concat();
        assert_eq!(requests(&bundle).unwrap().len(), 3);
        assert!(requests(&[bundle, vec![0x8e]].concat()).is_err());
        assert!(requests(&vec![0; 513]).is_err());
    }

    #[test]
    fn empty_new_roster_is_correlated_and_has_no_fake_presence_events() {
        let response = chat_response(&ChatRequest { id: 3, command: 9 }).unwrap().unwrap();
        assert_eq!(&response[..3], &[0x13, 0x4b, 46]);
        assert_eq!(i64::from_le_bytes(response[3..11].try_into().unwrap()), 3);
        assert_eq!(&response[11..13], &[13, 0]);
        assert_eq!(&response[43..], &[4, 0x80, 2, b']', b'.', 0]);
        assert!(chat_response(&ChatRequest { id: 1, command: 10 }).unwrap().is_none());
        assert!(chat_response(&ChatRequest { id: 3, command: 30 }).unwrap().is_none());
        assert!(chat_response(&ChatRequest { id: 3, command: 39 }).is_err());
    }

    #[test]
    fn measured_revision1_refresh_requires_exact_arguments_and_preserves_revision() {
        let packet = [0x8e, 20, 0, 224, 0, 100, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
        let request = Request { id: 224, command: 100 };
        assert_eq!(requests(&packet).unwrap(), vec![Incoming::Refresh(request.clone())]);
        for offset in [0, 1, 2, 5, 6, 7, 8, 14, 15, 19, 22] {
            let mut wrong = packet; wrong[offset] ^= 0x80;
            assert!(requests(&wrong).is_err(), "refresh offset {offset}");
        }
        assert!(requests(&[packet, packet].concat()).is_err());
        let response = response_refresh(&request).unwrap();
        assert_eq!(&response[..2], &[0x13, 0x4d]);
        assert_eq!(&response[3..8], &[224, 0, 0, 0, 0]);
        assert_eq!(&response[9..], b"\x80\x02}(U\x07prevRevK\x01U\x03revK\x01u.");
        validate_pickle(&response[9..], Kind::Dict).unwrap();
        assert!(response_refresh(&Request { id: 224, command: 300 }).is_err());
    }

    #[test]
    fn measured_language_setting_requires_exact_ru_and_unique_request_id() {
        let packet = [0x95, 7, 0, 225, 0, 0xe8, 3, 2, b'r', b'u'];
        assert_eq!(requests(&packet).unwrap(), vec![Incoming::Language { id: 225 }]);
        for length in 1..packet.len() { assert!(requests(&packet[..length]).is_err()); }
        for offset in [0, 1, 2, 5, 6, 7, 8, 9] {
            let mut wrong = packet; wrong[offset] ^= 0x80;
            assert!(requests(&wrong).is_err(), "language offset {offset}");
        }
        let mut wrong = packet; wrong[3..5].fill(0); assert!(requests(&wrong).is_err());
        assert!(requests(&[packet, packet].concat()).is_err());
        let mut another_id = packet; another_id[3] = 226;
        assert!(requests(&[packet, another_id].concat()).is_err());
        let refresh = [0x8e, 20, 0, 225, 0, 100, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0];
        assert!(requests(&[packet.as_slice(), refresh.as_slice()].concat()).is_err());
        assert!(requests(&[refresh.as_slice(), packet.as_slice()].concat()).is_err());
    }

    #[test]
    fn measured_server_stats_query_rejects_extra_arguments_and_duplicates() {
        let mut packet=vec![0x8e,20,0,202,0,245,1];packet.extend([0;16]);
        assert_eq!(requests(&packet).unwrap(),vec![Incoming::ServerStats]);
        assert!(requests(&[packet.clone(),packet.clone()].concat()).is_err());
        for offset in 3..23 {
            let mut wrong=packet.clone();wrong[offset]^=128;
            assert!(requests(&wrong).is_err());
        }
        assert_eq!(server_stats(),vec![0x13,0x48,1,0,0,0,1,0,0,0]);
    }
    #[test]
    fn actual_layout_request_is_explicitly_unavailable_only_in_interactive_mode() {
        let mut packet=vec![0x97,72,0,226,0,108,0];packet.extend(16u32.to_le_bytes());
        for value in [1i32,1,6,2570,96,2826,0,3082,0,6,0,0,0,0,0,0] {packet.extend(value.to_le_bytes());}
        assert_eq!(requests_interactive(&packet).unwrap(),vec![Incoming::UnsupportedIntArray{id:226,command:108,argument_count:16}]);
        assert!(requests(&packet).is_err());
        for end in 1..packet.len() {assert!(requests_interactive(&packet[..end]).is_err());}
        for offset in [0,1,2,5,6,7,8,9,10,19,20,21,22,47,48,49,50] {
            let mut wrong=packet.clone();wrong[offset]^=128;assert!(requests_interactive(&wrong).is_err());
        }
        assert!(requests_interactive(&[packet.clone(),packet].concat()).is_err());
        let response=unavailable_response(226).unwrap();
        assert_eq!(&response[..2],&[0x13,0x4d]);
        assert_eq!(i16::from_le_bytes(response[3..5].try_into().unwrap()),226);
        assert_eq!(i16::from_le_bytes(response[5..7].try_into().unwrap()),-10);
        assert_eq!(&response[7..],&[0,4,0x80,2,b'}',b'.']);
        assert!(unavailable_response(0).is_err());
    }
    #[test]
    fn native_creation_uses_utf8_byte_length_and_preserves_nickname_case() {
        let name="Стальной_Ёж7";let body=creation_named(name).unwrap();
        let prefix=9+1+b"ru_0.9.1_2".len();
        assert_eq!(body[prefix] as usize,name.len());assert_eq!(&body[prefix+1..prefix+1+name.len()],name.as_bytes());
        assert!(creation_named(&"Я".repeat(24)).is_ok());assert!(creation_named(&"Я".repeat(25)).is_err());
        assert!(creation_named("bad\nname").is_err());assert_eq!(creation(),creation_named("p02-hangar-player").unwrap());
    }
}
