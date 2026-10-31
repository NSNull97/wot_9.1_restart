//! Local website identity boundary. No credential registry or native object loader.
use std::{collections::BTreeMap, fs, fmt, io::{self,Read,Write}, net::{Ipv4Addr,SocketAddrV4,TcpStream},
          path::{Path,PathBuf}, time::{Duration,Instant}};
use serde::{Deserialize,Deserializer,de::{self,MapAccess,Visitor}};
use serde_json::Value;
use rsa::rand_core::{OsRng,RngCore};
#[path="identity_loss.rs"]
mod loss;
#[path="identity_hold.rs"]
mod hold;
pub(crate) use hold::HoldLogin;
#[path="room_selection.rs"]
pub(crate) mod room_selection;
#[path="room_selection_loss.rs"]
pub(crate) mod room_selection_loss;
#[path="game_network.rs"]
pub(crate) mod game_network;
#[path="domain_client.rs"]
pub(crate) mod domain_client;

fn invalid(message:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,message)}

// Reject duplicate top-level keys instead of accepting an ambiguous last value.
/// Unique-key JSON object with at most LIMIT top-level fields.
struct Bounded<const LIMIT:usize>(BTreeMap<String,Value>);
/// Requests and replies keep the original16-field guard. The gateway config
/// has a separate budget for explicitly validated opt-in service fields.
const REQUEST_FIELDS:usize=16;
/// Fixture manifests gain fields with each opt-in service (P09E writes 17) and
/// are already size-bounded by bounded_file.
const FIXTURE_METADATA_FIELDS:usize=64;
impl<'de,const LIMIT:usize> Deserialize<'de> for Bounded<LIMIT> {
    fn deserialize<D:Deserializer<'de>>(deserializer:D)->Result<Self,D::Error> {
        struct Fields<const N:usize>;
        impl<'de,const N:usize> Visitor<'de> for Fields<N> {
            type Value=Bounded<N>;
            fn expecting(&self,f:&mut fmt::Formatter)->fmt::Result {f.write_str("a bounded object with unique keys")}
            fn visit_map<M:MapAccess<'de>>(self,mut input:M)->Result<Bounded<N>,M::Error> {
                let mut output=BTreeMap::new();
                while let Some((key,value))=input.next_entry::<String,Value>()? {
                    if output.len()>=N || output.insert(key,value).is_some() {return Err(de::Error::custom("duplicate/too many fields"));}
                }
                Ok(Bounded(output))
            }
        }
        deserializer.deserialize_map(Fields::<LIMIT>)
    }
}
fn object(bytes:&[u8],keys:&[&str])->io::Result<BTreeMap<String,Value>> {
    if bytes.len()>4096 {return Err(invalid("JSON size bound"));}
    let Bounded::<REQUEST_FIELDS>(value)=serde_json::from_slice(bytes).map_err(|_|invalid("invalid bounded JSON object"))?;
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

struct BattleCapability {
    native_inventory_id:u32,admission:bool,code:Value,kind:Value,
}
impl<'de> Deserialize<'de> for BattleCapability {
    fn deserialize<D:Deserializer<'de>>(input:D)->Result<Self,D::Error> {
        let Bounded::<4>(value)=Bounded::deserialize(input)?;
        let expected=["native_inventory_id","admission","code","kind"];
        if value.len()!=4 || expected.iter().any(|key|!value.contains_key(*key)) {
            return Err(de::Error::custom("battle capability fields"));
        }
        let native_inventory_id=value["native_inventory_id"].as_u64().and_then(|v|u32::try_from(v).ok())
            .ok_or_else(||de::Error::custom("battle inventory integer"))?;
        let admission=value["admission"].as_bool().ok_or_else(||de::Error::custom("battle admission boolean"))?;
        Ok(Self{native_inventory_id,admission,code:value["code"].clone(),kind:value["kind"].clone()})
    }
}
struct BattleProjection {
    version:u8,schema:String,policy_sha256:String,account_id:String,native_database_id:i32,
    revision:u64,state_sha256:String,capabilities:Vec<BattleCapability>,
}
impl<'de> Deserialize<'de> for BattleProjection {
    fn deserialize<D:Deserializer<'de>>(input:D)->Result<Self,D::Error> {
        struct Fields;
        impl<'de> Visitor<'de> for Fields {
            type Value=BattleProjection;
            fn expecting(&self,f:&mut fmt::Formatter)->fmt::Result {f.write_str("unique battle projection fields")}
            fn visit_map<M:MapAccess<'de>>(self,mut input:M)->Result<BattleProjection,M::Error> {
                let mut values=BTreeMap::new();let mut capabilities=None;
                while let Some(key)=input.next_key::<String>()? {
                    if values.len()>=8 || values.contains_key(&key) {return Err(de::Error::custom("duplicate/too many battle projection fields"));}
                    if key=="capabilities" {
                        let rows=input.next_value::<Vec<BattleCapability>>()?;
                        if rows.len()>256 {return Err(de::Error::custom("battle capability count"));}
                        capabilities=Some(rows);values.insert(key,Value::Null);
                    }else{values.insert(key,input.next_value::<Value>()?);}
                }
                let expected=["version","schema","policy_sha256","account_id","native_database_id","revision","state_sha256","capabilities"];
                if values.len()!=8 || expected.iter().any(|key|!values.contains_key(*key)) {return Err(de::Error::custom("battle projection fields"));}
                let string=|key:&str|values[key].as_str().map(str::to_owned).ok_or_else(||de::Error::custom("battle projection string"));
                let version=values["version"].as_u64().and_then(|v|u8::try_from(v).ok()).ok_or_else(||de::Error::custom("battle projection version"))?;
                let native_database_id=values["native_database_id"].as_i64().and_then(|v|i32::try_from(v).ok()).ok_or_else(||de::Error::custom("battle projection native ID"))?;
                let revision=values["revision"].as_u64().ok_or_else(||de::Error::custom("battle projection revision"))?;
                Ok(BattleProjection{version,schema:string("schema")?,policy_sha256:string("policy_sha256")?,account_id:string("account_id")?,
                    native_database_id,revision,state_sha256:string("state_sha256")?,capabilities:capabilities.ok_or_else(||de::Error::custom("battle capabilities absent"))?})
            }
        }
        input.deserialize_map(Fields)
    }
}
fn battle_projection_bytes(raw:&[u8],profile:&Profile,revision:u64,state_sha256:&str)->io::Result<()> {
    if raw.is_empty() || raw.len()>65536 {return Err(invalid("battle projection metadata size"));}
    let value:BattleProjection=serde_json::from_slice(raw).map_err(|_|invalid("battle projection unique typed fields"))?;
    if value.version!=1 || value.schema!="p08b-profile13-battle.v1"
        || value.policy_sha256!=crate::battle091::profile13::POLICY_SHA256
        || value.account_id!=profile.account_id || value.native_database_id!=profile.database_id
        || value.revision!=revision || value.state_sha256!=state_sha256
        || !(2..=256).contains(&value.capabilities.len()) {return Err(invalid("battle projection identity/revision/policy"));}
    let mut ids=Vec::new();
    for row in value.capabilities {
        if row.native_inventory_id==0 || row.native_inventory_id>i32::MAX as u32
            || ids.last().is_some_and(|old|*old>=row.native_inventory_id) {return Err(invalid("battle capability inventory order/duplicates"));}
        let expected=match row.native_inventory_id{1=>Some("ms1"),2=>Some("is7"),_=>None};
        if row.kind.as_str()!=expected || (expected.is_none() && !row.kind.is_null()) {
            return Err(invalid("battle capability mounted profile"));
        }
        if row.admission {
            if expected.is_none() || !row.code.is_null() {return Err(invalid("unsupported battle capability admitted"));}
        } else {
            let code=row.code.as_str().ok_or_else(||invalid("battle capability rejection code"))?;
            if code.is_empty() || code.len()>64 || !code.bytes().all(|b|b.is_ascii_uppercase()||b==b'_') {
                return Err(invalid("battle capability rejection code"));
            }
        }
        ids.push(row.native_inventory_id);
    }
    if ids.get(..2)!=Some(&[1,2]) {return Err(invalid("battle projection missing base vehicles"));}
    Ok(())
}
fn verify_battle_projection(profile:&Profile,revision:u64)->io::Result<()> {
    use sha2::{Digest,Sha256};
    let root=profile.fixture_dir.canonicalize()?;
    let file=|name:&str,maximum:u64|->io::Result<Vec<u8>>{
        let path=root.join(name).canonicalize()?;
        if !path.starts_with(&root){return Err(invalid("battle projection escapes fixture"));}
        bounded_file(&path,maximum)
    };
    let state=file("state.bin",crate::research_service091::MAX_STATE_BYTES as u64)?;
    let raw=file("p08b-battle.json",65536)?;
    battle_projection_bytes(&raw,profile,revision,&format!("{:x}",Sha256::digest(&state)))
}

fn mixed_projection_bytes(raw:&[u8],profile:&Profile,revision:u64,state_sha256:&str)->io::Result<()> {
    let value=crate::profile13_v2091::bounded_json(raw,65536)?;
    let keys=["version","schema","policy_sha256","shell_catalog_sha256","account_id","native_database_id","revision","state_sha256","max_stacks","capabilities"];
    if value.as_object().is_none_or(|m|m.len()!=keys.len()||keys.iter().any(|k|!m.contains_key(*k)))
        ||value["version"].as_u64()!=Some(2)||value["schema"]!="p06t-owned-mixed-ammunition.v2"
        ||value["policy_sha256"]!=crate::profile13_v2091::POLICY_SHA256||value["shell_catalog_sha256"]!=crate::p06t_shells091::SOURCE_DATA_SHA256
        ||value["account_id"]!=profile.account_id||value["native_database_id"].as_i64()!=Some(profile.database_id as i64)
        ||value["revision"].as_u64()!=Some(revision)||value["state_sha256"]!=state_sha256||value["max_stacks"].as_u64()!=Some(3){
        return Err(invalid("P06T projection policy/identity/revision/state"));
    }
    let rows=value["capabilities"].as_array().ok_or_else(||invalid("P06T capabilities"))?;
    if !(2..=256).contains(&rows.len()){return Err(invalid("P06T capability count"));}let mut previous=0;
    for row in rows{
        if row.as_object().is_none_or(|m|m.len()!=4||["native_inventory_id","kind","admission","code"].iter().any(|k|!m.contains_key(*k))){return Err(invalid("P06T capability fields"));}
        let native=row["native_inventory_id"].as_u64().ok_or_else(||invalid("P06T inventory type"))?;
        if native<=previous||native>i32::MAX as u64{return Err(invalid("P06T inventory order/bound"));}previous=native;
        let kind=row["kind"].as_str();let admitted=row["admission"].as_bool().ok_or_else(||invalid("P06T admission boolean"))?;
        if (native==1&&kind!=Some("ms1"))||(native==2&&kind!=Some("is7"))
            ||(native>2&&!row["kind"].is_null()&&!kind.is_some_and(|k|matches!(k,"t26"|"t34"|"t3485")||crate::profile13_v2091::catalog_generated_kind(k))){
            return Err(invalid("P06T source kind"));}
        if admitted{
            // Purchased pool kinds (t26/t34/t3485, checked above) are admitted by
            // the writer only under the owner's explicit full-stand policy.
            if native>2&&row["kind"].is_null()||!row["code"].is_null(){return Err(invalid("P06T unaccepted machine admitted"));}
        }else{
            let code=row["code"].as_str().ok_or_else(||invalid("P06T denial code"))?;
            if !["VEHICLE_RESERVED","BATTLE_PROFILE_UNSUPPORTED","OWNER_ACCEPTANCE_REQUIRED","INCOMPLETE_CREW","AMMUNITION_EMPTY","AMMUNITION_UNSUPPORTED"].contains(&code){return Err(invalid("P06T closed denial"));}
        }
    }
    if rows[0]["native_inventory_id"]!=1||rows[1]["native_inventory_id"]!=2{return Err(invalid("P06T base vehicles missing"));}Ok(())
}
fn verify_mixed_projection(profile:&Profile,revision:u64)->io::Result<()> {
    use sha2::{Digest,Sha256};
    let root=profile.fixture_dir.canonicalize()?;
    let file=|name:&str,maximum:u64|->io::Result<Vec<u8>>{let path=root.join(name).canonicalize()?;
        if !path.starts_with(&root){return Err(invalid("P06T projection escapes fixture"));}bounded_file(&path,maximum)};
    let state=file("state.bin",crate::research_service091::MAX_STATE_BYTES as u64)?;
    mixed_projection_bytes(&file("p06t-ammunition.json",65536)?,profile,revision,&format!("{:x}",Sha256::digest(&state)))
}

fn late_results_owner_id(owner:&str)->bool{
    owner.len()==36&&owner.bytes().enumerate().all(|(i,b)|if [8,13,18,23].contains(&i){b==b'-'}else{b.is_ascii_digit()||(b'a'..=b'f').contains(&b)})
        &&matches!(owner.as_bytes()[14],b'1'..=b'5')&&matches!(owner.as_bytes()[19],b'8'|b'9'|b'a'|b'b')
}
/// Config-only streaming visitor. The nested typed decode must happen BEFORE
/// serde_json::Value could collapse duplicate game_network fields.
/// Known keys: 6 required + 28 optional = 34 (SPAWN-15); the bound leaves
/// headroom for later options and still refuses an unbounded object.
pub(crate) const MAX_CONFIG_FIELDS:usize=48;
struct ConfigFields{fields:BTreeMap<String,Value>,network:Option<game_network::LanWire>}
impl<'de> Deserialize<'de> for ConfigFields{
    fn deserialize<D:Deserializer<'de>>(input:D)->Result<Self,D::Error>{
        struct Fields;
        impl<'de> Visitor<'de> for Fields{
            type Value=ConfigFields;
            fn expecting(&self,f:&mut fmt::Formatter)->fmt::Result{f.write_str("unique bounded gateway config")}
            fn visit_map<M:MapAccess<'de>>(self,mut input:M)->Result<ConfigFields,M::Error>{
                let mut fields=BTreeMap::new();let mut network=None;
                while let Some(key)=input.next_key::<String>()?{
                    if fields.contains_key(&key){return Err(de::Error::custom("duplicate config field"));}
                    if fields.len()>=MAX_CONFIG_FIELDS{return Err(de::Error::custom("too many config fields"));}
                    if key=="game_network"{
                        network=Some(input.next_value::<game_network::LanWire>()?);
                        fields.insert(key,Value::Null);
                    }else{fields.insert(key,input.next_value::<Value>()?);}
                }
                Ok(ConfigFields{fields,network})
            }
        }
        input.deserialize_map(Fields)
    }
}

/// GW-01 target from ADR-002: one gateway process holds at most this many sessions.
pub const MAX_CONNECTIONS:usize=256;
/// ARENA-01: arenas per gateway process (ADR-002: 2 workers x 4 arenas).
pub const MAX_ARENAS:usize=4;

pub struct Config {
    pub login_bind:SocketAddrV4,pub base_bind:SocketAddrV4,identity_endpoint:SocketAddrV4,
    token:String,pub local_root:PathBuf,pub session_duration:Duration,
    game_network:game_network::Network,
    pub ammo_service:bool,pub crew_service:bool,pub crew_transfer:bool,pub crew_cross_vehicle:bool,pub crew_roster_recruitment:bool,pub crew_progression:bool,pub crew_dismissal:bool,pub crew_barracks_recruitment:bool,
    pub research_service:bool,pub profile13_battle:bool,pub battle_run_id:String,pub battle_players:usize,pub visibility_v1:bool,pub p04m_pool:bool,pub p06t_mixed_ammo:bool,pub p06t_ammo_rack_detonation:bool,
    pub p08c_late_results:bool,pub p08c_late_results_accounts:Vec<String>,pub p08c_late_notice_experimental:bool,
    pub training_rooms:bool,
    pub p08b_owner_battle_hold:bool,
    /// CAT-01 single catalog for mixed admission identity (default: legacy lists).
    pub catalog_v1:bool,
    /// DOM-01: hangar/battle writer paths go to the long-lived Domain service (default: bridge HTTP).
    domain:Option<domain_client::Endpoint>,
    /// GW-01: connections the gateway holds, separate from arena places (absent: battle_players, old path).
    pub connection_capacity:Option<usize>,
    /// ARENA-01: arenas run by this gateway (absent or 1: the one old World).
    pub arenas:usize,
    /// SPAWN-15: `spawn_policy` = the team-base formation policy (absent: LAB lanes).
    pub team_base_spawn:bool,
    /// BOT-01: server bots fill each arena after `human_places` native places (absent: none).
    pub bots:Option<crate::gateway091::shared::model::bots::Plan>,
    /// MM-01: "В бой" queues; rules match players into arenas (absent: fixed roster, old path).
    pub matchmaker:Option<crate::gateway091::shared::matchmaker::Rules>,
    /// NET-01: `pose_delivery` (absent: reliable poses, one reliable body per loop — the old path).
    pub pose_delivery:crate::gateway091::shared::net01::PoseDelivery,
    /// BW-01: each arena steps in its own worker process (absent: arenas in this process, old path).
    pub battle_worker:Option<BattleWorker>,
}
/// BW-01 `battle_worker` = {"version":1[,"step_timeout_ms":100..60000][,"startup_timeout_ms":1000..300000]}.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub struct BattleWorker {pub step_timeout:Duration,pub startup_timeout:Duration}
impl BattleWorker {
    pub const DEFAULT_STEP_MS:u64=2000;
    pub const DEFAULT_STARTUP_MS:u64=30000;
    fn parse(v:&Value)->io::Result<Self> {
        let Some(m)=v.as_object().filter(|m|m.get("version")==Some(&Value::from(1u64))
            &&m.keys().all(|k|["version","step_timeout_ms","startup_timeout_ms"].contains(&k.as_str()))) else {
            return Err(invalid("battle_worker must be {version:1} with optional step_timeout_ms and startup_timeout_ms"));
        };
        let ms=|key:&str,default:u64,range:std::ops::RangeInclusive<u64>|match m.get(key){
            None=>Ok(Duration::from_millis(default)),
            Some(v)=>v.as_u64().filter(|n|range.contains(n)).map(Duration::from_millis)
                .ok_or_else(||invalid("battle_worker step_timeout_ms must be 100..60000 and startup_timeout_ms 1000..300000")),
        };
        Ok(Self{step_timeout:ms("step_timeout_ms",Self::DEFAULT_STEP_MS,100..=60000)?,
            startup_timeout:ms("startup_timeout_ms",Self::DEFAULT_STARTUP_MS,1000..=300000)?})
    }
}
impl Config {
    pub fn load(path:&str)->io::Result<Self> {
        let bytes=bounded_file(Path::new(path),4096)?;
        // The parser's own message (duplicate/too many fields, syntax) is project text, not input echo.
        let ConfigFields{fields:mut value,network}=serde_json::from_slice(&bytes)
            .map_err(|e|io::Error::new(io::ErrorKind::InvalidData,format!("invalid gateway config: {e}")))?;
        value.remove("game_network");
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
        let crew_progression=match value.remove("crew_progression") {None=>false,Some(Value::Bool(value))=>value,_=>return Err(invalid("crew progression must be explicit boolean"))};
        if crew_progression && !crew_roster_recruitment {return Err(invalid("crew progression requires roster recruitment"));}
        let crew_dismissal=match value.remove("crew_dismissal") {None=>false,Some(Value::Bool(value))=>value,_=>return Err(invalid("crew dismissal must be explicit boolean"))};
        if crew_dismissal && !crew_progression {return Err(invalid("crew dismissal requires crew progression"));}
        let crew_barracks_recruitment=match value.remove("crew_barracks_recruitment") {None=>false,Some(Value::Bool(value))=>value,_=>return Err(invalid("crew barracks must be explicit boolean"))};
        if crew_barracks_recruitment && !crew_dismissal {return Err(invalid("crew barracks requires dismissal"));}
        let research_service=match value.remove("research_service") {
            None=>false,Some(Value::Bool(value))=>value,_=>return Err(invalid("research service must be explicit boolean")),
        };
        if research_service && !crew_barracks_recruitment {return Err(invalid("research service requires accepted barracks profile"));}
        let profile13_battle=match value.remove("profile13_battle") {
            None=>false,Some(Value::Bool(value))=>value,_=>return Err(invalid("profile13 battle must be explicit boolean")),
        };
        if profile13_battle && !research_service {return Err(invalid("profile13 battle requires the complete research writer"));}
        let p04m_pool=match value.remove("p04m_pool") {
            None=>false,Some(Value::Bool(v))=>v,_=>return Err(invalid("p04m_pool must be explicit boolean")),
        };
        if p04m_pool&&!profile13_battle{return Err(invalid("P04M pool requires the complete profile13 writer"));}
        let p06t_mixed_ammo=match value.remove("p06t_mixed_ammo"){
            None=>false,Some(Value::Bool(v))=>v,_=>return Err(invalid("p06t_mixed_ammo must be explicit boolean")),
        };
        if p06t_mixed_ammo&&!p04m_pool{return Err(invalid("P06T mixed ammunition requires the complete P04M profile13 writer"));}
        let visibility_v1=match value.remove("visibility_v1") {
            None=>false,Some(Value::Bool(value))=>value,_=>return Err(invalid("visibility_v1 must be explicit boolean")),
        };
        if visibility_v1&&!profile13_battle{return Err(invalid("visibility_v1 requires profile13 battle"));}
        let p06t_ammo_rack_detonation=match value.remove("p06t_ammo_rack_detonation"){
            None=>false,Some(Value::Bool(v))=>v,_=>return Err(invalid("p06t_ammo_rack_detonation must be explicit boolean")),
        };
        if p06t_ammo_rack_detonation&&(!p06t_mixed_ammo||!visibility_v1){return Err(invalid("ammo-rack loss requires mixed ammunition and server visibility"));}
        let p08c_late_results=match value.remove("p08c_late_results"){
            None=>false,Some(Value::Bool(v))=>v,_=>return Err(invalid("late results must be explicit boolean")),
        };
        if p08c_late_results&&(!profile13_battle||!p06t_mixed_ammo){return Err(invalid("late results require owned mixed profile13; legacy unsupported"));}
        let p08c_late_notice_experimental=match value.remove("p08c_late_notice_experimental"){
            None=>false,Some(Value::Bool(v))=>v,_=>return Err(invalid("late notice must be explicit boolean")),
        };
        if p08c_late_notice_experimental&&!p08c_late_results{return Err(invalid("experimental native notice requires durable late results"));}
        let p08c_late_results_accounts=match value.remove("p08c_late_results_accounts"){
            None=>Vec::new(),Some(Value::Array(rows)) if rows.len()<=6=>{
                let mut owners=Vec::new();for row in rows{let owner=row.as_str().ok_or_else(||invalid("late owner UUID string"))?;
                    if !late_results_owner_id(owner)||owners.iter().any(|old|old==owner){return Err(invalid("late owner unique canonical UUID"));}owners.push(owner.to_owned());}owners
            },_=>return Err(invalid("late owners bounded explicit array")),
        };
        if p08c_late_results!=!p08c_late_results_accounts.is_empty(){return Err(invalid("late flag requires explicit1..6 owner capability list; disabled requires empty"));}
        let team_base_spawn=match value.remove("spawn_policy"){
            None=>false,
            Some(Value::String(p)) if p==crate::gateway091::shared::team_spawn::POLICY=>true,
            _=>return Err(invalid("spawn_policy must be the team-base formation policy of this gateway build")),
        };
        if team_base_spawn&&!profile13_battle{return Err(invalid("spawn_policy requires profile13 battle"));}
        // SPAWN-15: more than the native six places only with team-base spawns
        // (LAB lanes are not a battle layout) and GW-01 connection capacity.
        let most=if team_base_spawn{crate::gateway091::shared::model::MAX_ACTORS as u64}else{6};
        let battle_players=match value.remove("battle_players") {
            None=>2,Some(Value::Number(n))=>n.as_u64().filter(|n|(2..=most).contains(n))
                .ok_or_else(||invalid(if team_base_spawn{"battle_players must be2..30"}else{"battle_players must be2..6"}))? as usize,
            _=>return Err(invalid("battle_players must be integer")),
        };
        if battle_players!=2&&!profile13_battle{return Err(invalid("variable roster requires profile13"));}
        let training_rooms=match value.remove("training_rooms") {
            None=>false,Some(Value::Bool(value))=>value,_=>return Err(invalid("training_rooms must be explicit boolean")),
        };
        if training_rooms&&(!p06t_mixed_ammo||!visibility_v1||battle_players!=6){return Err(invalid("training rooms require mixed owned profiles, visibility and six-place template"));}
        let p08b_owner_battle_hold=match value.remove("p08b_owner_battle_hold"){
            None=>false,Some(Value::Bool(v))=>v,_=>return Err(invalid("owner hold5 must be explicit boolean")),
        };
        if p08b_owner_battle_hold&&(!profile13_battle||!p04m_pool||!p06t_mixed_ammo||!p06t_ammo_rack_detonation||!visibility_v1||training_rooms||p08c_late_results){
            return Err(invalid("hold5 requires complete owned loss policy; TrainingLoss4 and old late observer are not version5"));
        }
        let connection_capacity=match value.remove("connection_capacity"){
            None=>None,
            Some(Value::Number(n))=>Some(n.as_u64().filter(|n|(battle_players as u64..=MAX_CONNECTIONS as u64).contains(n))
                .ok_or_else(||invalid("connection_capacity must be battle_players..256"))? as usize),
            _=>return Err(invalid("connection_capacity must be integer")),
        };
        // Training rooms and hold5 start only when every session is in the arena.
        if connection_capacity.is_some()&&(!profile13_battle||training_rooms||p08b_owner_battle_hold){
            return Err(invalid("connection_capacity requires profile13 battle without training rooms or hold5"));
        }
        if battle_players>6&&connection_capacity.is_none(){return Err(invalid("more than six battle places require connection_capacity"));}
        // ARENA-01: K arenas share the connection table; each needs its own places.
        let arenas=match value.remove("arenas"){
            None=>1,
            Some(Value::Number(n))=>n.as_u64().filter(|n|(1..=MAX_ARENAS as u64).contains(n))
                .ok_or_else(||invalid("arenas must be 1..4"))? as usize,
            _=>return Err(invalid("arenas must be integer")),
        };
        if arenas>1&&connection_capacity.is_none_or(|n|n<arenas*battle_players){
            return Err(invalid("arenas requires connection_capacity of at least arenas*battle_players"));
        }
        // BOT-01: {"policy":<this build's>,"human_places":H,"seed":S[,"kinds":[labels]]}.
        let bots=match value.remove("bots"){
            None=>None,
            Some(Value::Object(b))=>{
                if b.keys().any(|k|!["policy","human_places","seed","kinds"].contains(&k.as_str()))
                    ||b.get("policy").and_then(Value::as_str)!=Some(crate::gateway091::shared::model::bots::POLICY){
                    return Err(invalid("bots must name this build's bot policy with human_places, seed and optional kinds"));
                }
                let human_places=b.get("human_places").and_then(Value::as_u64).filter(|h|(1..battle_players as u64).contains(h))
                    .ok_or_else(||invalid("bots human_places must be 1..battle_players-1"))? as usize;
                let seed=b.get("seed").and_then(Value::as_u64).ok_or_else(||invalid("bots seed must be a non-negative integer"))?;
                let kinds=match b.get("kinds"){
                    None=>crate::gateway091::shared::vehicle_profile::VehicleKind::ALL.to_vec(),
                    // BATTLE-ANY: curated or generated owned labels; the battle profiles must bind each.
                    Some(Value::Array(rows)) if !rows.is_empty()&&rows.len()<=crate::gateway091::shared::model::bots::MAX_KINDS=>rows.iter().map(|r|r.as_str()
                        .and_then(crate::gateway091::shared::vehicle_profile::VehicleKind::from_owned_label)
                        .ok_or_else(||invalid("bots kinds must be owned battle vehicle labels"))).collect::<io::Result<Vec<_>>>()?,
                    _=>return Err(invalid("bots kinds must be 1..16 owned battle vehicle labels")),
                };
                let plan=crate::gateway091::shared::model::bots::Plan{human_places,seed,kinds};
                plan.validate(battle_players).map_err(|_|invalid("bots kinds must be distinct profile13 vehicles"))?;
                Some(plan)
            },
            _=>return Err(invalid("bots must be an object")),
        };
        if bots.is_some()&&(!profile13_battle||connection_capacity.is_none()||!visibility_v1||training_rooms||p08b_owner_battle_hold){
            return Err(invalid("bots require profile13 battle, connection_capacity and visibility_v1, without training rooms or hold5"));
        }
        // MM-01: {"policy":<this build's>,"team_size":T,"tiers":[lo,hi],"tier_spread":D,"wait_seconds":W,"lease_seconds":L}.
        let matchmaker=match value.remove("matchmaker"){
            None=>None,
            Some(Value::Object(m)) if m.len()==6&&m.get("policy").and_then(Value::as_str)==Some(crate::gateway091::shared::matchmaker::POLICY)=>{
                let number=|key:&str|m.get(key).and_then(Value::as_u64).ok_or_else(||invalid("matchmaker team_size, tier_spread, wait_seconds and lease_seconds must be non-negative integers"));
                let tiers=match m.get("tiers"){
                    Some(Value::Array(t)) if t.len()==2=>(t[0].as_u64(),t[1].as_u64()),
                    _=>return Err(invalid("matchmaker tiers must be [lo,hi]")),
                };
                let tier=|t:Option<u64>|t.and_then(|t|u8::try_from(t).ok()).ok_or_else(||invalid("matchmaker tiers must be 1..10"));
                let rules=crate::gateway091::shared::matchmaker::Rules{
                    team_size:usize::try_from(number("team_size")?).map_err(|_|invalid("matchmaker team_size"))?,
                    tiers:(tier(tiers.0)?,tier(tiers.1)?),
                    tier_spread:u8::try_from(number("tier_spread")?).map_err(|_|invalid("matchmaker tier_spread must be 0..9"))?,
                    wait:Duration::from_secs(number("wait_seconds")?),lease:Duration::from_secs(number("lease_seconds")?)};
                rules.validate(battle_players).map_err(|_|invalid("matchmaker: 2*team_size=battle_players, tiers 1..10, tier_spread 0..9, wait 1..600 s, lease wait..900 s"))?;
                Some(rules)
            },
            _=>return Err(invalid("matchmaker must name this build's policy with team_size, tiers, tier_spread, wait_seconds and lease_seconds")),
        };
        if matchmaker.is_some()&&(bots.is_none()||!p04m_pool){
            return Err(invalid("matchmaker requires bots (timeout fill) and the P04M pool (vehicle tiers)"));
        }
        let pose_delivery=match value.remove("pose_delivery"){
            None=>crate::gateway091::shared::net01::PoseDelivery::Reliable,
            Some(Value::String(mode))=>crate::gateway091::shared::net01::PoseDelivery::parse(Some(&mode))
                .ok_or_else(||invalid("pose_delivery must be reliable-burst-v1, reliable-burst-v2 or latest-unreliable-v1"))?,
            _=>return Err(invalid("pose_delivery must be a string")),
        };
        if pose_delivery==crate::gateway091::shared::net01::PoseDelivery::LatestUnreliable&&!visibility_v1{
            return Err(invalid("latest-unreliable poses require visibility_v1"));
        }
        // BW-01: the training/hold5 hosts keep the scene runtime on the gateway thread.
        let battle_worker=value.remove("battle_worker").map(|v|BattleWorker::parse(&v)).transpose()?;
        if battle_worker.is_some()&&(!profile13_battle||training_rooms||p08b_owner_battle_hold){
            return Err(invalid("battle_worker requires profile13 battle without training rooms or hold5"));
        }
        // CAT-01: exact {"version":1,"sha256":<this build's catalog>}; a foreign hash refuses start.
        let catalog_v1=match value.remove("catalog"){
            None=>false,
            Some(Value::Object(c)) if c.len()==2&&c.get("version")==Some(&Value::from(1u64))
                &&c.get("sha256").and_then(Value::as_str)==Some(crate::gateway091::shared::vehicle_catalog::CATALOG_SHA256)=>true,
            _=>return Err(invalid("catalog must be {version:1,sha256} of this gateway build")),
        };
        if catalog_v1&&(!profile13_battle||!p06t_mixed_ammo){return Err(invalid("catalog v1 applies to the owned mixed profile13 writer only"));}
        let domain_value=value.remove("domain_service");
        if domain_value.is_some()&&(!profile13_battle||training_rooms){
            return Err(invalid("domain_service requires profile13 battle; training-room selection keeps its bridge writer"));
        }
        let keys=["login_bind","base_bind","identity_endpoint","identity_token_file","local_root","session_duration_seconds"];
        if value.len()!=keys.len() || keys.iter().any(|key|!value.contains_key(*key)) {return Err(invalid("gateway config fields"));}
        let game_network=game_network::Network::parse(text(&value,"login_bind")?,text(&value,"base_bind")?,network)?;
        if game_network.is_lan()&&(!profile13_battle||!p04m_pool||!p06t_mixed_ammo){return Err(invalid("LAN game network requires the complete mixed profile13 writer"));}
        let login_bind=game_network.login_bind();let base_bind=game_network.base_bind();
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
        let domain=domain_value.map(|v|domain_client::Endpoint::parse(&v,&local_root)).transpose()?;
        if domain.as_ref().is_some_and(|d|[login_bind,base_bind,identity_endpoint].contains(&d.address())){return Err(invalid("service ports must be distinct"));}
        let seconds=value["session_duration_seconds"].as_u64().ok_or_else(||invalid("session duration integer"))?;
        if !(600..=7200).contains(&seconds) {return Err(invalid("session duration must be 600..7200 seconds"));}
        let battle_run_id=if profile13_battle {
            let mut raw=[0u8;16];OsRng.fill_bytes(&mut raw);raw[6]=(raw[6]&15)|64;raw[8]=(raw[8]&63)|128;
            let hex=raw.iter().map(|byte|format!("{byte:02x}")).collect::<String>();
            format!("{}-{}-{}-{}-{}",&hex[..8],&hex[8..12],&hex[12..16],&hex[16..20],&hex[20..])
        }else{String::new()};
        Ok(Self {login_bind,base_bind,identity_endpoint,token,game_network,local_root,session_duration:Duration::from_secs(seconds),ammo_service,crew_service,crew_transfer,crew_cross_vehicle,crew_roster_recruitment,crew_progression,crew_dismissal,crew_barracks_recruitment,research_service,profile13_battle,battle_run_id,battle_players,visibility_v1,p04m_pool,p06t_mixed_ammo,p06t_ammo_rack_detonation,p08c_late_results,p08c_late_results_accounts,p08c_late_notice_experimental,training_rooms,p08b_owner_battle_hold,catalog_v1,domain,connection_capacity,arenas,team_base_spawn,bots,matchmaker,pose_delivery,battle_worker})
    }
    pub(crate) fn game_network(&self)->&game_network::Network{&self.game_network}
    pub fn domain_endpoint(&self)->Option<SocketAddrV4>{self.domain.as_ref().map(domain_client::Endpoint::address)}
    pub(crate) fn require_game_network(&self,runtime:game_network::Runtime)->io::Result<()>{
        self.game_network.require_runtime(runtime,self.login_bind,self.base_bind)?;
        if self.game_network.is_lan()&&(!self.profile13_battle||!self.p04m_pool||!self.p06t_mixed_ammo){return Err(invalid("LAN game network requires the complete mixed profile13 writer"));}Ok(())
    }
    fn authentication_timeout(&self)->Duration {
        // A configured curated owner publishes its source-bound projection
        // during login. Its bounded 7s writer/9s bridge budget must fit inside
        // this caller's deadline; legacy authentication retains its 5s limit.
        Duration::from_secs(if self.p04m_pool {20} else {5})
    }
    pub fn authenticate(&self,email:&str,password:&str)->io::Result<Option<Profile>> {
        let email=canonical_email(email)?;
        let body=serde_json::to_vec(&serde_json::json!({"email":email,"password":password}))
            .map_err(|_|invalid("identity request serialization"))?;
        if body.len()>2048 {return Err(invalid("identity request size"));}
        let (status,body)=self.post("/internal/native/login",&body,self.authentication_timeout())?;
        if status==401 {return Ok(None);}
        if status!=200 {return Err(invalid("identity service unavailable or rejected service authentication"));}
        let profile=profile(&body,&self.local_root)?;
        verify_fixture_identity(&profile)?;
        if self.ammo_service {
            let binding=if self.research_service {crate::ammo_service091::metadata_research(&profile.fixture_dir,&profile.account_id,profile.database_id)?}
                else {crate::ammo_service091::metadata(&profile.fixture_dir,&profile.account_id,profile.database_id)?};
            if self.research_service {crate::research_service091::metadata(&profile.fixture_dir,&profile.account_id,profile.database_id,binding.revision,binding.wire_revision)?;}
            if self.p04m_pool {crate::p04m_companion091::Binding::metadata(&profile.fixture_dir,&profile.account_id,profile.database_id,binding.revision)?;}
            if self.crew_transfer {
                if self.research_service {crate::crew_transfer091::metadata_for_research(&profile.fixture_dir,&profile.account_id,profile.database_id,binding.revision,binding.wire_revision)?;}
                else {crate::crew_transfer091::metadata_for(crate::crew_transfer091::Profile::selected_barracks(self.crew_cross_vehicle,self.crew_roster_recruitment,self.crew_progression,self.crew_dismissal,self.crew_barracks_recruitment),&profile.fixture_dir,&profile.account_id,profile.database_id,binding.revision,binding.wire_revision)?;}
            } else if self.crew_service {
                crate::crew_service091::metadata(&profile.fixture_dir,&profile.account_id,profile.database_id,binding.revision,binding.wire_revision)?;
            }
        }
        if self.profile13_battle {return self.begin_battle_run(&profile).map(Some);}
        Ok(Some(profile))
    }

    pub fn battle(&self,owner:&Profile,context:&crate::battle091::profile13::Context,
        request:&crate::battle091::profile13::Request)->io::Result<crate::battle091::profile13::Reply> {
        if self.p06t_ammo_rack_detonation||!self.profile13_battle || context.account_id!=owner.account_id
            || context.native_database_id!=owner.database_id || context.run_id!=self.battle_run_id {
            return Err(invalid("battle request authenticated owner/run mismatch"));
        }
        let body=crate::battle091::profile13::encode_request(context,request)?;
        let(status,bytes)=self.post("/internal/native/battle",&body,Duration::from_secs(20))?;
        if status!=200 {return Err(invalid("battle writer unavailable; outcome must be recovered"));}
        crate::battle091::profile13::parse_reply(&bytes,context,request)
    }

    pub fn service_battle_v2(&self,owner:&Profile,context:&crate::battle091::profile13::Context,
        request:&crate::profile13_v2091::Request)->io::Result<crate::profile13_v2091::Reply>{
        if self.p06t_ammo_rack_detonation||!self.p06t_mixed_ammo||!self.p04m_pool||!self.profile13_battle||context.account_id!=owner.account_id
            ||context.native_database_id!=owner.database_id||context.run_id!=self.battle_run_id{return Err(invalid("P06T authenticated owner/run/opt-in"));}
        let body=crate::profile13_v2091::encode_request(context,request)?;
        let(status,bytes)=self.post_with_budget("/internal/native/battle",&body,Duration::from_secs(20),65536,8192+4100)?;
        if status!=200{return Err(invalid("P06T writer unavailable; immutable outcome retained"));}
        crate::profile13_v2091::parse_reply(&bytes,context,request)
    }

    /// Called only by the credential worker after this gateway owns its ports.
    /// A new run atomically aborts unfinished old transactions; an old fenced
    /// run can never publish a late admission/result into the new process.
    fn begin_battle_run(&self,owner:&Profile)->io::Result<Profile> {
        let binding=crate::ammo_service091::metadata_research(&owner.fixture_dir,&owner.account_id,owner.database_id)?;
        verify_battle_projection(owner,binding.revision)?;
        let context=crate::battle091::profile13::Context {account_id:owner.account_id.clone(),
            native_database_id:owner.database_id,command_key:format!("open:{}:{}:{}",self.battle_run_id,owner.database_id,binding.revision),
            expected_revision:binding.revision,run_id:self.battle_run_id.clone()};
        if self.p08b_owner_battle_hold{
            verify_mixed_projection(owner,binding.revision)?;loss::verify_loss_projection(owner,binding.revision)?;
            hold::verify_hold_projection(owner,binding.revision)?;
            let reply=self.service_battle_hold(owner,&context,&crate::profile13_hold091::Request::RunOpen)?;
            if reply.status!=crate::profile13_hold091::Status::Ready{return Err(invalid("owner hold5 run was not opened"));}
        }else if self.p06t_ammo_rack_detonation{
            if owner.fixture_dir.join("p08b-owner-hold.json").exists(){return Err(invalid("hold owner requires version5 gateway"));}
            verify_mixed_projection(owner,binding.revision)?;
            loss::verify_loss_projection(owner,binding.revision)?;
            let reply=self.service_battle_loss(owner,&context,&crate::profile13_loss091::Request::RunOpen)?;
            if reply.status!=crate::profile13_loss091::Status::Ready{return Err(invalid("ammo-loss run was not opened"));}
        }else if self.p06t_mixed_ammo{
            if owner.fixture_dir.join("p06t-ammo-loss.json").exists(){return Err(invalid("loss owner requires version4 gateway"));}
            verify_mixed_projection(owner,binding.revision)?;
            let reply=self.service_battle_v2(owner,&context,&crate::profile13_v2091::Request::RunOpen)?;
            if reply.status!=crate::profile13_v2091::Status::Ready{return Err(invalid("P06T run was not opened"));}
        }else{
            let reply=self.battle(owner,&context,&crate::battle091::profile13::Request::RunOpen)?;
            if reply.status!=crate::battle091::profile13::ReplyStatus::Ready {return Err(invalid("battle run was not opened"));}
        }
        self.refresh_battle_profile(owner)
    }

    /// Reload an already authenticated owner after a committed battle write.
    /// The bridge chooses its fixture; neither native input nor a result DTO
    /// can supply a filesystem path or select a different identity.
    pub fn refresh_battle_profile(&self,owner:&Profile)->io::Result<Profile> {
        if !self.profile13_battle || !self.research_service {return Err(invalid("profile13 battle is not enabled"));}
        let body=serde_json::to_vec(&serde_json::json!({"account_id":owner.account_id,
            "native_database_id":owner.database_id})).map_err(|_|invalid("profile refresh encoding"))?;
        let(status,bytes)=self.post("/internal/native/profile",&body,Duration::from_secs(20))?;
        if status!=200 {return Err(invalid("battle profile refresh unavailable"));}
        let fresh=profile(&bytes,&self.local_root)?;
        if fresh.account_id!=owner.account_id || fresh.database_id!=owner.database_id || fresh.name!=owner.name {
            return Err(invalid("battle profile refresh changed authenticated identity"));
        }
        verify_fixture_identity(&fresh)?;
        let binding=crate::ammo_service091::metadata_research(&fresh.fixture_dir,&fresh.account_id,fresh.database_id)?;
        crate::research_service091::metadata(&fresh.fixture_dir,&fresh.account_id,fresh.database_id,binding.revision,binding.wire_revision)?;
        crate::crew_transfer091::metadata_for_research(&fresh.fixture_dir,&fresh.account_id,fresh.database_id,binding.revision,binding.wire_revision)?;
        verify_battle_projection(&fresh,binding.revision)?;
        if self.p04m_pool {crate::p04m_companion091::Binding::metadata(&fresh.fixture_dir,&fresh.account_id,fresh.database_id,binding.revision)?;}
        if self.p06t_mixed_ammo {verify_mixed_projection(&fresh,binding.revision)?;}
        if self.p06t_ammo_rack_detonation{loss::verify_loss_projection(&fresh,binding.revision)?;}
        else if fresh.fixture_dir.join("p06t-ammo-loss.json").exists(){return Err(invalid("loss owner requires version4 gateway"));}
        if self.p08b_owner_battle_hold{hold::verify_hold_projection(&fresh,binding.revision)?;}
        else if fresh.fixture_dir.join("p08b-owner-hold.json").exists(){return Err(invalid("hold owner requires version5 gateway"));}
        Ok(fresh)
    }

    /// Bounded loopback transport; only fixed internal paths supplied by this module.
    fn post(&self,path:&str,body:&[u8],timeout:Duration)->io::Result<(u16,Vec<u8>)> {
        self.post_with_budget(path,body,timeout,4096,8192)
    }
    /// P08C results alone need the bounded complete result string. Keep every
    /// older service on its original4KiB body/8KiB response admission limits.
    pub(crate) fn results_post(&self,owner:&Profile,body:&[u8])->io::Result<Vec<u8>> {
        // RES-30: one escaped 7..30-row journal; 2..6 rows stay within the old 64KiB.
        const RESULT:usize=crate::gateway091::shared::lifecycle_wire::MAX_RESULT_REQUEST;
        if !self.profile13_battle||owner.database_id<=0||body.is_empty()||body.len()>RESULT {
            return Err(invalid("battle result HTTP request bound"));
        }
        let(status,reply)=self.post_with_budget("/internal/native/battle-results",body,Duration::from_secs(20),RESULT,RESULT+4100)?;
        if status!=200{return Err(invalid("battle results writer unavailable; immutable request retained"));}
        Ok(reply)
    }
    pub(crate) fn results_post_v2(&self,owner:&Profile,body:&[u8])->io::Result<Vec<u8>>{
        if self.p06t_ammo_rack_detonation||!self.p06t_mixed_ammo||!self.p04m_pool||!self.profile13_battle||owner.database_id<=0||body.is_empty()||body.len()>2048{
            return Err(invalid("P06T results authenticated mode/body bound"));
        }
        const RESULT:usize=crate::gateway091::shared::lifecycle_wire::MAX_RESULT_REQUEST;
        let(status,reply)=self.post_with_budget("/internal/native/battle-results",body,Duration::from_secs(20),RESULT,RESULT+4100)?;
        if status!=200{return Err(invalid("P06T results writer unavailable; immutable task retained"));}Ok(reply)
    }
    /// New fixed namespace alone. Old body/reply budgets and paths unchanged.
    pub(crate) fn late_results_post(&self,owner:&Profile,body:&[u8])->io::Result<Vec<u8>>{
        self.late_results_http(owner,body,false)
    }
    pub(crate) fn late_results_pending_post(&self,owner:&Profile,body:&[u8])->io::Result<Vec<u8>>{
        self.late_results_http(owner,body,true)
    }
    fn late_results_http(&self,owner:&Profile,body:&[u8],pending:bool)->io::Result<Vec<u8>>{
        if !self.p08c_late_results||!self.profile13_battle||!self.p06t_mixed_ammo||owner.database_id<=0
            ||!self.p08c_late_results_accounts.contains(&owner.account_id)||body.is_empty()||body.len()>if pending{2048}else{crate::gateway091::shared::lifecycle_wire::MAX_RESULT_REQUEST}{
            return Err(invalid("late results configured owner/mode/body boundary"));
        }
        let path=if pending{"/internal/native/late-result-pending"}else{"/internal/native/late-result-append"};
        let(status,reply)=self.post_with_budget(path,body,Duration::from_secs(20),4096,4096+4100)?;
        if status!=200{return Err(io::Error::new(io::ErrorKind::InvalidData,format!("late result HTTP status={status}; immutable request retained")));}
        Ok(reply)
    }
    fn post_with_budget(&self,path:&str,body:&[u8],timeout:Duration,max_body:usize,max_wire:usize)->io::Result<(u16,Vec<u8>)> {
        if let (Some(domain),Some(op))=(&self.domain,domain_client::operation(path)){return domain.call(op,body,timeout,max_body);}
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
                Ok(n)=>{if response.len()+n>max_wire {return Err(invalid("identity response size"));}response.extend(&buffer[..n]);},
                Err(error) if matches!(error.kind(),io::ErrorKind::WouldBlock|io::ErrorKind::TimedOut)=>{},
                Err(error)=>return Err(error),
            }
        }
        let (status,body)=http_response_with_budget(&response,max_body,max_wire)?;
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

    /// Expanded codecs are reachable only with a current authenticated P04M
    /// projection. Fixed paths and immutable owner/request fields stay local.
    pub(crate) fn service_pool(&self,profile:&Profile,pool:&crate::p04m_companion091::Binding,key:&str,revision:u64,wire:i64,
        request:crate::p04m_companion091::Request)->io::Result<AmmoReply>{
        use crate::p04m_companion091::Request;
        if !self.p04m_pool||!self.profile13_battle||!pool.matches(&profile.account_id,profile.database_id,revision){return Err(invalid("P04M bound service owner/revision/opt-in"));}
        let (path,status,layout,barracks)=match request{
            Request::Ammo(r)=>{pool.ammo_layout(&r)?;("/internal/native/ammo","serviced",r.arguments.iter().map(|v|*v as i64).collect::<Vec<_>>(),None)},
            Request::Crew(r)=>{pool.recruit(r)?;("/internal/native/crew","recruited",r.layout().to_vec(),None)},
            Request::Transfer(r)=>{pool.transfer(r)?;("/internal/native/crew-transfer","transferred",r.layout().to_vec(),None)},
            Request::Barracks(r)=>{pool.barracks(r)?;("/internal/native/crew-recruit-barracks","recruited",r.layout().to_vec(),Some(r))},
            // Same writer routes and gates as P04J/P04I; identities bounded by the stored contract.
            Request::Dismiss(r)=>{if !self.crew_dismissal{return Err(invalid("crew dismissal is not enabled"));}pool.dismiss(r)?;("/internal/native/crew-dismiss","dismissed",r.layout().to_vec(),None)},
            Request::Skill(r)=>{if !self.crew_progression{return Err(invalid("crew progression is not enabled"));}pool.learn(r)?;("/internal/native/crew-learn","learned",r.layout().to_vec(),None)},
        };
        let body=pool.service_request(key,revision,wire,&layout)?;
        let (http,bytes)=self.post(path,&body,Duration::from_secs(20))?;
        if http!=200{return Err(invalid("P04M writer HTTP failure; recover by fresh login"));}
        if let Some(r)=barracks{barracks_reply_bound(&bytes,profile,key,revision,wire,r,Some(pool))}
        else{service_reply(&bytes,profile,key,revision,wire,status)}
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

    pub fn recruit_barracks(&self,profile:&Profile,key:&str,revision:u64,wire:i64,request:crate::crew_barracks091::Request)->io::Result<AmmoReply> {
        if !self.crew_barracks_recruitment {return Err(invalid("crew barracks is not enabled"));}
        let body=crate::crew_barracks091::service_request(&profile.account_id,profile.database_id,key,revision,wire,request)?;
        let (status,bytes)=self.post("/internal/native/crew-recruit-barracks",&body,Duration::from_secs(20))?;
        if status!=200 {return Err(invalid("barracks service HTTP failure; recover by fresh login"));}
        barracks_reply(&bytes,profile,key,revision,wire,request)
    }

    pub fn dismiss_crew(&self,profile:&Profile,key:&str,revision:u64,wire:i64,request:crate::crew_dismissal091::Request)->io::Result<AmmoReply> {
        if !self.crew_dismissal {return Err(invalid("crew dismissal is not enabled"));}
        let body=crate::crew_dismissal091::service_request(&profile.account_id,profile.database_id,key,revision,wire,request)?;
        let (status,bytes)=self.post("/internal/native/crew-dismiss",&body,Duration::from_secs(20))?;
        if status!=200 {return Err(invalid("dismissal service HTTP failure; recover by fresh login"));}
        service_reply(&bytes,profile,key,revision,wire,"dismissed")
    }

    pub fn learn_crew(&self,profile:&Profile,key:&str,revision:u64,wire:i64,request:crate::crew_progression091::Request)->io::Result<AmmoReply> {
        if !self.crew_progression {return Err(invalid("crew progression is not enabled"));}
        let body=crate::crew_progression091::service_request(&profile.account_id,profile.database_id,key,revision,wire,request)?;
        let (status,bytes)=self.post("/internal/native/crew-learn",&body,Duration::from_secs(20))?;
        if status!=200 {return Err(invalid("skill service HTTP failure; recover by fresh login"));}
        service_reply(&bytes,profile,key,revision,wire,"learned")
    }

    pub fn research(&self,profile:&Profile,command_key:&str,expected_revision:u64,
                    wire_revision:i64,request:&crate::research_service091::Request)->io::Result<AmmoReply> {
        if !self.research_service || !self.ammo_service {return Err(invalid("research service is not enabled"));}
        let body=crate::research_service091::service_request(&profile.account_id,profile.database_id,command_key,expected_revision,wire_revision,request)?;
        let (status,bytes)=self.post("/internal/native/research",&body,Duration::from_secs(20))?;
        if status!=200 {return Err(invalid("research service HTTP failure; recover outcome by fresh login"));}
        service_reply(&bytes,profile,command_key,expected_revision,wire_revision,"researched")
    }

    pub fn transfer_crew(&self,profile:&Profile,command_key:&str,expected_revision:u64,
                         wire_revision:i64,request:crate::crew_transfer091::Request)->io::Result<AmmoReply> {
        if !self.crew_transfer || !self.crew_service || !self.ammo_service {return Err(invalid("crew transfer is not enabled"));}
        let body=crate::crew_transfer091::service_request_for(crate::crew_transfer091::Profile::selected_barracks(self.crew_cross_vehicle,self.crew_roster_recruitment,self.crew_progression,self.crew_dismissal,self.crew_barracks_recruitment),&profile.account_id,profile.database_id,command_key,
            expected_revision,wire_revision,request)?;
        let (status,bytes)=self.post("/internal/native/crew-transfer",&body,Duration::from_secs(20))?;
        if status!=200 {return Err(invalid("crew transfer HTTP failure; recover outcome by fresh login"));}
        service_reply(&bytes,profile,command_key,expected_revision,wire_revision,"transferred")
    }
}

pub struct AmmoReply {pub serviced:bool,pub revision:u64,pub wire_revision:i64,
    pub update:Vec<u8>,pub recruitment:Option<crate::crew_barracks091::Recruitment>,pub replayed:bool,pub result_code:i32,
    pub(crate) pool:Option<std::sync::Arc<crate::p04m_companion091::Binding>>}

fn valid_command_key(key:&str)->bool {
    (1..=96).contains(&key.len()) && key.bytes().all(|b|b.is_ascii_alphanumeric() || b"-_:".contains(&b))
}

fn ammo_reply(bytes:&[u8],profile:&Profile,key:&str,expected:u64,wire:i64)->io::Result<AmmoReply> {
    service_reply(bytes,profile,key,expected,wire,"serviced")
}

fn service_reply(bytes:&[u8],profile:&Profile,key:&str,expected:u64,wire:i64,success_status:&str)->io::Result<AmmoReply> {
    let value=object(bytes,&["status","account_id","native_database_id","command_key","revision",
        "wire_revision","update_hex","replayed","result_code"])?;
    service_reply_value(value,profile,key,expected,wire,success_status)
}

fn barracks_reply(bytes:&[u8],profile:&Profile,key:&str,expected:u64,wire:i64,request:crate::crew_barracks091::Request)->io::Result<AmmoReply> {
    barracks_reply_bound(bytes,profile,key,expected,wire,request,None)
}
fn barracks_reply_bound(bytes:&[u8],profile:&Profile,key:&str,expected:u64,wire:i64,request:crate::crew_barracks091::Request,pool:Option<&crate::p04m_companion091::Binding>)->io::Result<AmmoReply> {
    let mut value=object(bytes,&["status","account_id","native_database_id","command_key","revision",
        "wire_revision","update_hex","replayed","result_code","tankman_inventory_id","tankman_descriptor_hex"])?;
    let id=value.remove("tankman_inventory_id").and_then(|v|v.as_u64()).ok_or_else(||invalid("barracks response ID type"))?;
    let descriptor=value.remove("tankman_descriptor_hex").and_then(|v|v.as_str().map(str::to_owned)).ok_or_else(||invalid("barracks response descriptor type"))?;
    let mut reply=service_reply_value(value,profile,key,expected,wire,"recruited")?;
    if reply.serviced {
        if !(4..=pool.map_or(16,|p|p.capacity() as u64)).contains(&id) || descriptor.len()!=50 || !descriptor.bytes().all(|b|b.is_ascii_digit() || (b'a'..=b'f').contains(&b)) {return Err(invalid("barracks response descriptor bounds"));}
        let mut raw=[0;25];
        for (index,byte) in raw.iter_mut().enumerate() {*byte=u8::from_str_radix(&descriptor[index*2..index*2+2],16).map_err(|_|invalid("barracks descriptor hex"))?;}
        let member=crate::crew_barracks091::Recruitment{tankman_id:id as u8,descriptor:raw};
        if let Some(pool)=pool{pool.validate_recruitment(&member,request,wire,&reply.update)?;}else{member.validate_delta(request,wire,&reply.update)?;}
        reply.recruitment=Some(member);
    } else if id!=0 || !descriptor.is_empty() {return Err(invalid("rejected barracks response has recruitment"));}
    Ok(reply)
}

fn service_reply_value(value:BTreeMap<String,Value>,profile:&Profile,key:&str,expected:u64,wire:i64,success_status:&str)->io::Result<AmmoReply> {
    if !(5..i32::MAX as u64).contains(&expected) || !(1..i32::MAX as i64).contains(&wire)
        || !matches!(success_status,"serviced"|"recruited"|"transferred"|"learned"|"dismissed"|"researched") {return Err(invalid("service reply cursor/status boundary"));}
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
    Ok(AmmoReply{serviced,revision,wire_revision,update,recruitment:None,replayed,result_code:result_code as i32,pool:None})
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
    http_response_with_budget(bytes,4096,8192)
}
fn http_response_with_budget(bytes:&[u8],max_body:usize,max_wire:usize)->io::Result<(u16,&[u8])> {
    let end=bytes.windows(4).position(|b|b==b"\r\n\r\n").ok_or_else(||invalid("HTTP header incomplete"))?;
    if end>4096 || bytes.len()>max_wire || !bytes[..end].is_ascii() {return Err(invalid("HTTP response size/ASCII bound"));}
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
    if body.len()>max_body || length!=Some(body.len()) {return Err(invalid("HTTP body length mismatch"));}
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
        let Bounded::<FIXTURE_METADATA_FIELDS>(data)=serde_json::from_slice(&bytes).map_err(|_|invalid("invalid identity fixture metadata"))?;
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
    fn p04m_vector_fixture(name:&str,sha:&str)->(Profile,crate::p04m_companion091::Binding,Value){
        use sha2::{Digest,Sha256};
        let root=std::env::var_os("WOT091_ROOT").map(PathBuf::from).unwrap_or_else(||Path::new(env!("CARGO_MANIFEST_DIR")).join("../.."));
        let directory=root.join("local/evidence/20261031-cat-nations-restamp/p04m-native-fixtures03").join(name);
        let bytes=bounded_file(&directory.join("writer-vectors.json"),16384).expect("actual writer vectors required");
        assert_eq!(format!("{:x}",Sha256::digest(&bytes)),sha);
        let v:Value=serde_json::from_slice(&bytes).unwrap();let meta:Value=serde_json::from_slice(&bounded_file(&directory.join("p04m-pool.json"),65536).unwrap()).unwrap();
        let owner=Profile{account_id:meta["account_id"].as_str().unwrap().into(),database_id:meta["native_database_id"].as_i64().unwrap()as i32,name:"actual-writer".into(),fixture_dir:directory};
        let binding=crate::p04m_companion091::Binding::metadata(&owner.fixture_dir,&owner.account_id,owner.database_id,meta["revision"].as_u64().unwrap()).unwrap();
        (owner,binding,v)
    }
    #[test]fn p04m_actual_sqlite_cmd309_all_t34_seats_and_radioman_parse_native_update(){
        let(owner,pool,v)=p04m_vector_fixture("t34-full-crew","06f22a2d9d50a845b4cfbefd0867ea69306ec1c501457cd9f060c4d1f56ac218");
        assert_eq!(v.as_array().unwrap().len(),4);
        for(slot,row)in v.as_array().unwrap().iter().enumerate(){
            assert_eq!(row["operation"],"recruit");let r=&row["request"];assert_eq!(r.as_object().unwrap().len(),6);assert_eq!(r["layout"],serde_json::json!([3,3,slot,0]));
            let request=crate::crew_service091::Request{id:230+slot as i16,shop_revision:3,vehicle_inventory_id:3,slot:slot as i32,tariff_index:0};pool.recruit(request).unwrap();assert!(request.validate_for(true).is_err());
            let reply=service_reply(&serde_json::to_vec(&row["response"]).unwrap(),&owner,r["command_key"].as_str().unwrap(),r["expected_revision"].as_u64().unwrap(),1,"recruited").unwrap();
            assert!(reply.serviced);assert_eq!(reply.revision,30+slot as u64);let bodies=crate::ammo_service091::response(request.id,&reply.update).unwrap();
            assert_eq!(bodies.len(),2);assert_eq!(bodies[0][1],0x57);assert_eq!(bodies[1][1],0x4d);
        }
        let fixtures=crate::hangar091::Fixtures::load_p04m(&owner.fixture_dir).unwrap();assert!(fixtures.p04m_binding().unwrap().matches(&owner.account_id,1,33));
    }
    #[test]fn p04m_actual_sqlite_cmd303_radioman_descriptor_and_delta_are_jointly_bound(){
        let(owner,pool,v)=p04m_vector_fixture("t34-radioman-barracks","4522f0ae60a587550071776742a413b700e07bee5fb1692e48468a4955c86833");
        let row=v.as_array().unwrap().last().unwrap();assert_eq!(row["operation"],"recruit_barracks");
        assert_eq!(row["request"]["layout"],serde_json::json!([3,1,2,0]));
        let request=crate::crew_barracks091::Request{id:230,shop_revision:3,vehicle_type:1,role:2,cost:0};
        pool.barracks(request).unwrap();assert!(request.validate_supported().is_err());
        let response=serde_json::to_vec(&row["response"]).unwrap();let reply=barracks_reply_bound(&response,&owner,"pool-crew:9",36,1,request,Some(&pool)).unwrap();
        assert!(reply.serviced);let member=reply.recruitment.unwrap();assert_eq!(member.tankman_id,8);assert_eq!(member.descriptor[1..4],[0,2,50]);
        pool.validate_recruitment(&member,request,1,&reply.update).unwrap();let body=member.success_response(request.id).unwrap();assert_eq!(body[1],0x4d);
        assert!(body.windows(25).any(|b|b==member.descriptor.as_slice()));
        assert!(barracks_reply(&response,&owner,"pool-crew:9",36,1,request).is_err());
        for n in 0..3{let mut wrong=row["response"].clone();match n{0=>wrong["account_id"]="foreign".into(),1=>wrong["tankman_descriptor_hex"]="08000332000000080008000800400600000000420000000000".into(),_=>wrong["tankman_inventory_id"]=9.into()};
            assert!(barracks_reply_bound(&serde_json::to_vec(&wrong).unwrap(),&owner,"pool-crew:9",36,1,request,Some(&pool)).is_err());}
    }
    #[test]fn p04m_configuration_requires_explicit_optin_and_full_profile13(){
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs").join(format!("p04m-config-{stamp}"));
        fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();fs::write(root.join("token.txt"),"a".repeat(43)).unwrap();
        let mut v=serde_json::json!({"login_bind":"127.0.0.1:23014","base_bind":"127.0.0.1:23015","identity_endpoint":"127.0.0.1:3395",
            "identity_token_file":root.join("token.txt"),"local_root":root,"session_duration_seconds":600});
        let path=root.join("gateway.json");let load=|v:&Value|{fs::write(&path,serde_json::to_vec(v).unwrap()).unwrap();Config::load(path.to_str().unwrap())};
        let legacy=load(&v).unwrap();assert!(!legacy.p04m_pool);assert_eq!(legacy.authentication_timeout(),Duration::from_secs(5));
        v["p04m_pool"]=true.into();assert!(load(&v).is_err());
        for key in["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression","crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle"]{v[key]=true.into();}
        let pool=load(&v).unwrap();assert!(pool.p04m_pool);assert_eq!(pool.authentication_timeout(),Duration::from_secs(20));
        for wrong in[Value::Null,1.into(),"true".into()]{v["p04m_pool"]=wrong;assert!(load(&v).is_err());}
        v["p04m_pool"]=true.into();let mut raw=serde_json::to_string(&v).unwrap();raw.pop();raw.push_str(",\"p04m_pool\":false}");fs::write(path,raw).unwrap();
        assert!(Config::load(root.join("gateway.json").to_str().unwrap()).is_err());
    }
    #[test]fn p10b_configuration_requires_explicit_mixed_visible_six_place_template(){
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs").join(format!("p10b-config-{stamp}"));
        fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();fs::write(root.join("token.txt"),"a".repeat(43)).unwrap();
        let mut v=serde_json::json!({"login_bind":"127.0.0.1:23014","base_bind":"127.0.0.1:23015","identity_endpoint":"127.0.0.1:3395",
            "identity_token_file":root.join("token.txt"),"local_root":root,"session_duration_seconds":600});
        let path=root.join("gateway.json");let load=|v:&Value|{fs::write(&path,serde_json::to_vec(v).unwrap()).unwrap();Config::load(path.to_str().unwrap())};
        assert!(!load(&v).unwrap().training_rooms);v["training_rooms"]=true.into();assert!(load(&v).is_err());
        for key in["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression","crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle","p04m_pool","p06t_mixed_ammo","visibility_v1"]{v[key]=true.into();}
        assert!(load(&v).is_err());v["battle_players"]=6.into();assert!(load(&v).unwrap().training_rooms);
        for key in["p06t_mixed_ammo","visibility_v1"]{let mut wrong=v.clone();wrong[key]=false.into();assert!(load(&wrong).is_err());}
        for bad in[Value::Null,1.into(),"true".into()]{let mut wrong=v.clone();wrong["training_rooms"]=bad;assert!(load(&wrong).is_err());}
        for n in 2..6{let mut wrong=v.clone();wrong["battle_players"]=n.into();assert!(load(&wrong).is_err());}
        let mut raw=serde_json::to_string(&v).unwrap();raw.pop();raw.push_str(",\"training_rooms\":false}");fs::write(&path,raw).unwrap();assert!(Config::load(path.to_str().unwrap()).is_err());
    }
    #[test]fn p06t_configuration_requires_explicit_boolean_and_pool_profile13_chain(){
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs").join(format!("p06t-config-{stamp}"));
        fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();fs::write(root.join("token.txt"),"a".repeat(43)).unwrap();
        let mut v=serde_json::json!({"login_bind":"127.0.0.1:23014","base_bind":"127.0.0.1:23015","identity_endpoint":"127.0.0.1:3395",
            "identity_token_file":root.join("token.txt"),"local_root":root,"session_duration_seconds":600});
        let path=root.join("gateway.json");let load=|v:&Value|{fs::write(&path,serde_json::to_vec(v).unwrap()).unwrap();Config::load(path.to_str().unwrap())};
        assert!(!load(&v).unwrap().p06t_mixed_ammo);v["p06t_mixed_ammo"]=true.into();assert!(load(&v).is_err());
        for key in["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression","crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle"]{v[key]=true.into();}
        assert!(load(&v).is_err());v["p04m_pool"]=true.into();assert!(load(&v).unwrap().p06t_mixed_ammo);
        for wrong in[Value::Null,1.into(),"true".into()]{v["p06t_mixed_ammo"]=wrong;assert!(load(&v).is_err());}
        v["p06t_mixed_ammo"]=true.into();let mut raw=serde_json::to_string(&v).unwrap();raw.pop();raw.push_str(",\"p06t_mixed_ammo\":false}");fs::write(path,raw).unwrap();
        assert!(Config::load(root.join("gateway.json").to_str().unwrap()).is_err());
    }
    #[test]fn p06t_actual_sqlite_companion_binds_owner_state_policy_and_keeps_new_three_closed(){
        use sha2::{Digest,Sha256};
        let raw=include_bytes!("../../../../tests/fixtures/p06t-writer-companion.json");
        assert_eq!(format!("{:x}",Sha256::digest(raw)),"e6c5bb9a1ad41574e9b449da76e00f265f0155bc518577d2a61a0aee4706a85e");
        let value:Value=serde_json::from_slice(raw).unwrap();
        let owner=Profile{account_id:value["account_id"].as_str().unwrap().into(),database_id:value["native_database_id"].as_i64().unwrap()as i32,
            name:"actual SQLite".into(),fixture_dir:PathBuf::new()};
        let state="23074e15758a028f907b9c68048f91976fac8a0980136da83918fb46b78510d5";
        mixed_projection_bytes(raw,&owner,19,state).unwrap();
        assert!(mixed_projection_bytes(raw,&owner,20,state).is_err());assert!(mixed_projection_bytes(raw,&owner,19,&"0".repeat(64)).is_err());
        for n in 0..4{let mut bad=value.clone();match n{
            0=>bad["account_id"]="foreign".into(),1=>bad["shell_catalog_sha256"]="0".repeat(64).into(),
            2=>bad["max_stacks"]=4.into(),_=>bad["capabilities"].as_array_mut().unwrap().push(serde_json::json!({"native_inventory_id":3,"kind":null,"admission":true,"code":null})),
        }assert!(mixed_projection_bytes(&serde_json::to_vec(&bad).unwrap(),&owner,19,state).is_err());}
    }
    #[test] fn p08c_results_http_budget_does_not_widen_legacy_services_or_accept_bad_framing() {
        let response=|n:usize|{let mut raw=format!("HTTP/1.1 200 OK\r\nContent-Length: {n}\r\nConnection: close\r\n\r\n").into_bytes();raw.extend(vec![b'x';n]);raw};
        let large=response(5000);assert!(http_response(&large).is_err());
        assert_eq!(http_response_with_budget(&large,65536,65536+4100).unwrap().1.len(),5000);
        assert_eq!(http_response_with_budget(&response(65536),65536,65536+4100).unwrap().1.len(),65536);
        assert!(http_response_with_budget(&response(65537),65536,65536+4100).is_err());
        assert!(http_response_with_budget(b"HTTP/1.1 200 OK\r\nContent-Length: 1\r\nContent-Length: 1\r\n\r\nx",65536,65536+4100).is_err());
        assert!(http_response_with_budget(b"HTTP/1.1 200 OK\r\nContent-Length: 1\r\nTransfer-Encoding: chunked\r\n\r\nx",65536,65536+4100).is_err());
        assert!(http_response_with_budget(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nx",65536,65536+4100).is_err());
        assert!(http_response(&response(4096)).is_ok());assert!(http_response(&response(4097)).is_err());
    }
    #[test] fn profile13_projection_metadata_binds_owner_revision_state_policy_and_capabilities() {
        let owner=Profile{account_id:"12345678-1234-4234-8234-123456789abc".into(),database_id:17,name:"owned".into(),fixture_dir:PathBuf::new()};
        let sha="a".repeat(64);
        let value=serde_json::json!({"version":1,"schema":"p08b-profile13-battle.v1",
            "policy_sha256":crate::battle091::profile13::POLICY_SHA256,"account_id":owner.account_id,
            "native_database_id":17,"revision":14,"state_sha256":sha,
            "capabilities":[{"native_inventory_id":1,"admission":true,"code":null,"kind":"ms1"},
                {"native_inventory_id":2,"admission":false,"code":"INCOMPLETE_CREW","kind":"is7"},
                {"native_inventory_id":3,"admission":false,"code":"BATTLE_PROFILE_UNSUPPORTED","kind":null}]});
        battle_projection_bytes(&serde_json::to_vec(&value).unwrap(),&owner,14,&sha).unwrap();
        for mutation in 0..15 {
            let mut wrong=value.clone();match mutation{
                0=>wrong["account_id"]="foreign".into(),1=>wrong["native_database_id"]=18.into(),
                2=>wrong["revision"]=13.into(),3=>wrong["state_sha256"]="b".repeat(64).into(),
                4=>wrong["policy_sha256"]="b".repeat(64).into(),5=>wrong["capabilities"][1]["native_inventory_id"]=1.into(),
                6=>wrong["capabilities"][2]["admission"]=true.into(),7=>wrong["capabilities"][0]["kind"]="is7".into(),
                8=>wrong["capabilities"][0]["code"]="VEHICLE_RESERVED".into(),9=>wrong["capabilities"][1]["code"]=Value::Null,
                10=>wrong["capabilities"][2]["kind"]="ms1".into(),11=>wrong["capabilities"][0]["extra"]=true.into(),
                12=>{wrong["capabilities"][0].as_object_mut().unwrap().remove("code");},13=>wrong["version"]=true.into(),
                14=>wrong["extra"]=true.into(),_=>unreachable!(),
            }
            assert!(battle_projection_bytes(&serde_json::to_vec(&wrong).unwrap(),&owner,14,&sha).is_err(),"mutation={mutation}");
        }
        let bytes=serde_json::to_string(&value).unwrap().replacen("\"admission\":true","\"admission\":true,\"admission\":false",1);
        assert!(battle_projection_bytes(bytes.as_bytes(),&owner,14,&sha).is_err());
    }
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

    #[test] fn net01_pose_delivery_key_is_exact_and_unreliable_needs_visibility() {
        use crate::gateway091::shared::net01::PoseDelivery;
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs").join(format!("net01-config-{stamp}"));
        fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();fs::write(root.join("token.txt"),"a".repeat(43)).unwrap();
        let base=serde_json::json!({"login_bind":"127.0.0.1:23014","base_bind":"127.0.0.1:23015","identity_endpoint":"127.0.0.1:3395",
            "identity_token_file":root.join("token.txt"),"local_root":root,"session_duration_seconds":600});
        let path=root.join("gateway.json");let load=|v:&Value|{fs::write(&path,serde_json::to_vec(v).unwrap()).unwrap();Config::load(path.to_str().unwrap())};
        assert_eq!(load(&base).unwrap().pose_delivery,PoseDelivery::Reliable);
        let mut burst=base.clone();burst["pose_delivery"]="reliable-burst-v1".into();
        assert_eq!(load(&burst).unwrap().pose_delivery,PoseDelivery::ReliableBurst);
        burst["pose_delivery"]="reliable-burst-v2".into();assert_eq!(load(&burst).unwrap().pose_delivery,PoseDelivery::ReliableBurstV2);
        for bad in [Value::from("reliable"),Value::from("latest-unreliable-v2"),Value::from(true),Value::Null] {
            let mut wrong=base.clone();wrong["pose_delivery"]=bad.clone();assert!(load(&wrong).is_err(),"{bad}");
        }
        let mut latest=base.clone();latest["pose_delivery"]="latest-unreliable-v1".into();assert!(load(&latest).is_err());
        for field in ["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression",
            "crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle","visibility_v1"]{latest[field]=true.into();}
        latest["battle_players"]=6.into();
        assert_eq!(load(&latest).unwrap().pose_delivery,PoseDelivery::LatestUnreliable);
        fs::remove_dir_all(&root).unwrap();
    }

    #[test] fn p07b_configuration_visibility_requires_an_explicit_boolean_and_profile13() {
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs").join(format!("p07b-config-{stamp}"));
        fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();fs::write(root.join("token.txt"),"a".repeat(43)).unwrap();
        let base=serde_json::json!({"login_bind":"127.0.0.1:23014","base_bind":"127.0.0.1:23015","identity_endpoint":"127.0.0.1:3395",
            "identity_token_file":root.join("token.txt"),"local_root":root,"session_duration_seconds":600});
        let path=root.join("gateway.json");let load=|v:&Value|{fs::write(&path,serde_json::to_vec(v).unwrap()).unwrap();Config::load(path.to_str().unwrap())};
        assert!(!load(&base).unwrap().visibility_v1);
        let mut disabled=base.clone();disabled["visibility_v1"]=false.into();assert!(!load(&disabled).unwrap().visibility_v1);
        let mut unsupported=base.clone();unsupported["visibility_v1"]=true.into();assert!(load(&unsupported).is_err());
        let mut enabled=base.clone();
        for field in ["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression",
            "crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle"]{enabled[field]=true.into();}
        enabled["battle_players"]=6.into();enabled["visibility_v1"]=true.into();
        assert_eq!(enabled.as_object().unwrap().len(),18);
        let selected=load(&enabled).unwrap();assert!(selected.visibility_v1);assert_eq!(selected.battle_players,6);
        for bad in [Value::Null,0.into(),1.into(),"true".into(),serde_json::json!([]),serde_json::json!({})]{
            let mut row=enabled.clone();row["visibility_v1"]=bad;assert!(load(&row).is_err());}
        let mut without_battle=enabled.clone();without_battle["profile13_battle"]=false.into();assert!(load(&without_battle).is_err());
        let mut unknown=enabled.clone();unknown["visibility_v2"]=true.into();assert!(load(&unknown).is_err());
        let mut duplicate=serde_json::to_string(&enabled).unwrap();duplicate.pop();duplicate.push_str(",\"visibility_v1\":false}");
        fs::write(&path,duplicate).unwrap();assert!(Config::load(path.to_str().unwrap()).is_err());
        // Configuration has its own budget; public request DTO guards stay16.
        assert_eq!(REQUEST_FIELDS,16);
    }
    #[test] fn bot01_configuration_is_explicit_bounded_and_absent_by_default() {
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs").join(format!("bot01-config-{stamp}"));
        fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();fs::write(root.join("token.txt"),"a".repeat(43)).unwrap();
        let mut value=serde_json::json!({"login_bind":"127.0.0.1:23014","base_bind":"127.0.0.1:23015","identity_endpoint":"127.0.0.1:3395",
            "identity_token_file":root.join("token.txt"),"local_root":root,"session_duration_seconds":600});
        let path=root.join("gateway.json");let load=|v:&Value|{fs::write(&path,serde_json::to_vec(v).unwrap()).unwrap();Config::load(path.to_str().unwrap())};
        for field in ["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression",
            "crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle","visibility_v1"]{value[field]=true.into();}
        value["battle_players"]=30.into();value["connection_capacity"]=32.into();
        value["spawn_policy"]=crate::gateway091::shared::team_spawn::POLICY.into();
        assert!(load(&value).unwrap().bots.is_none(),"absent key: no bots");
        let policy=crate::gateway091::shared::model::bots::POLICY;
        value["bots"]=serde_json::json!({"policy":policy,"human_places":2,"seed":7});
        let plan=load(&value).unwrap().bots.unwrap();
        assert_eq!((plan.human_places,plan.seed,plan.kinds.len()),(2,7,5));
        value["bots"]["kinds"]=serde_json::json!(["t34","is7"]);
        assert_eq!(load(&value).unwrap().bots.unwrap().kinds.iter().map(|k|k.label()).collect::<Vec<_>>(),["t34","is7"]);
        value["bots"]["kinds"]=serde_json::json!(["t34","ussr-KV-3"]);
        assert!(load(&value).unwrap().bots.unwrap().kinds[1].is_generated(),"BATTLE-ANY generated label");
        for bad in [serde_json::json!({"policy":"other","human_places":2,"seed":7}),serde_json::json!({"policy":policy,"human_places":0,"seed":7}),
            serde_json::json!({"policy":policy,"human_places":30,"seed":7}),serde_json::json!({"policy":policy,"human_places":2}),
            serde_json::json!({"policy":policy,"human_places":2,"seed":-1}),serde_json::json!({"policy":policy,"human_places":2,"seed":7,"extra":1}),
            serde_json::json!({"policy":policy,"human_places":2,"seed":7,"kinds":[]}),serde_json::json!({"policy":policy,"human_places":2,"seed":7,"kinds":["t34","t34"]}),
            serde_json::json!({"policy":policy,"human_places":2,"seed":7,"kinds":["wt-e100-128"]}),
            serde_json::json!({"policy":policy,"human_places":2,"seed":7,"kinds":["ussr-NoSuchTank"]}),serde_json::json!(true)]{
            let mut row=value.clone();row["bots"]=bad;assert!(load(&row).is_err(),"{}",row["bots"]);}
        for (field,off) in [("visibility_v1",Value::from(false)),("profile13_battle",Value::from(false))]{
            let mut row=value.clone();row[field]=off;assert!(load(&row).is_err(),"bots need {field}");}
        let mut row=value.clone();row.as_object_mut().unwrap().remove("connection_capacity");row["battle_players"]=6.into();
        row.as_object_mut().unwrap().remove("spawn_policy");assert!(load(&row).is_err(),"bots need GW-01 places");
        row["connection_capacity"]=6.into();assert_eq!(load(&row).unwrap().bots.unwrap().human_places,2);
        // Owner's one-client stand: 6 places, 1 native, 5 bots.
        row["bots"]["human_places"]=1.into();assert_eq!(load(&row).unwrap().bots.unwrap().human_places,1);
    }
    #[test] fn bw01_battle_worker_configuration_is_explicit_bounded_and_absent_by_default() {
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs").join(format!("bw01-config-{stamp}"));
        fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();fs::write(root.join("token.txt"),"a".repeat(43)).unwrap();
        let mut value=serde_json::json!({"login_bind":"127.0.0.1:23024","base_bind":"127.0.0.1:23025","identity_endpoint":"127.0.0.1:3396",
            "identity_token_file":root.join("token.txt"),"local_root":root,"session_duration_seconds":600});
        let path=root.join("gateway.json");let load=|v:&Value|{fs::write(&path,serde_json::to_vec(v).unwrap()).unwrap();Config::load(path.to_str().unwrap())};
        for field in ["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression",
            "crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle"]{value[field]=true.into();}
        assert!(load(&value).unwrap().battle_worker.is_none(),"absent key: arenas in this process");
        value["battle_worker"]=serde_json::json!({"version":1});
        assert_eq!(load(&value).unwrap().battle_worker,Some(BattleWorker{step_timeout:Duration::from_millis(2000),startup_timeout:Duration::from_millis(30000)}));
        value["battle_worker"]=serde_json::json!({"version":1,"step_timeout_ms":500,"startup_timeout_ms":60000});
        assert_eq!(load(&value).unwrap().battle_worker.unwrap().step_timeout,Duration::from_millis(500));
        for bad in [serde_json::json!(true),serde_json::json!({}),serde_json::json!({"version":2}),serde_json::json!({"version":1,"step_timeout_ms":99}),
            serde_json::json!({"version":1,"startup_timeout_ms":300001}),serde_json::json!({"version":1,"other":1})] {
            value["battle_worker"]=bad.clone();assert!(load(&value).is_err(),"{bad}");
        }
        value["battle_worker"]=serde_json::json!({"version":1});value["profile13_battle"]=false.into();
        assert!(load(&value).is_err(),"needs the profile13 battle");
        value["profile13_battle"]=true.into();value["p08b_owner_battle_hold"]=true.into();
        assert!(load(&value).is_err(),"hold5 keeps its runtime on the gateway thread");
    }
    #[test] fn mm01_configuration_is_explicit_bounded_and_absent_by_default() {
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs").join(format!("mm01-config-{stamp}"));
        fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();fs::write(root.join("token.txt"),"a".repeat(43)).unwrap();
        let mut value=serde_json::json!({"login_bind":"127.0.0.1:23014","base_bind":"127.0.0.1:23015","identity_endpoint":"127.0.0.1:3395",
            "identity_token_file":root.join("token.txt"),"local_root":root,"session_duration_seconds":600});
        let path=root.join("gateway.json");let load=|v:&Value|{fs::write(&path,serde_json::to_vec(v).unwrap()).unwrap();Config::load(path.to_str().unwrap())};
        for field in ["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression",
            "crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle","visibility_v1","p04m_pool"]{value[field]=true.into();}
        value["battle_players"]=6.into();value["connection_capacity"]=256.into();value["arenas"]=2.into();
        value["bots"]=serde_json::json!({"policy":crate::gateway091::shared::model::bots::POLICY,"human_places":1,"seed":1});
        assert!(load(&value).unwrap().matchmaker.is_none(),"absent key: fixed roster");
        let policy=crate::gateway091::shared::matchmaker::POLICY;
        value["matchmaker"]=serde_json::json!({"policy":policy,"team_size":3,"tiers":[1,10],"tier_spread":2,"wait_seconds":30,"lease_seconds":90});
        let rules=load(&value).unwrap().matchmaker.unwrap();
        assert_eq!((rules.team_size,rules.tiers,rules.tier_spread,rules.wait.as_secs(),rules.lease.as_secs()),(3,(1,10),2,30,90));
        let good=value["matchmaker"].clone();
        let with=|key:&str,v:Value|{let mut m=good.clone();m[key]=v;m};
        for bad in [with("policy","other".into()),with("team_size",2.into()),with("team_size",0.into()),with("team_size",(-3).into()),
            with("tiers",serde_json::json!([0,10])),with("tiers",serde_json::json!([6,5])),with("tiers",serde_json::json!([1,11])),
            with("tiers",serde_json::json!([1])),with("tiers",serde_json::json!([1,256])),with("tier_spread",10.into()),with("tier_spread",300.into()),
            with("wait_seconds",0.into()),with("wait_seconds",601.into()),with("wait_seconds",1.5.into()),with("lease_seconds",29.into()),
            with("lease_seconds",901.into()),with("extra",1.into()),serde_json::json!({"policy":policy,"team_size":3}),serde_json::json!(true)]{
            let mut row=value.clone();row["matchmaker"]=bad;assert!(load(&row).is_err(),"{}",row["matchmaker"]);}
        let mut row=value.clone();row.as_object_mut().unwrap().remove("bots");assert!(load(&row).is_err(),"matchmaker needs bots for the timeout");
        let mut row=value.clone();row["p04m_pool"]=false.into();assert!(load(&row).is_err(),"matchmaker needs vehicle tiers");
        // No hard place limit: 15 per team with the SPAWN-15 roster.
        let mut row=value.clone();row["battle_players"]=30.into();row["spawn_policy"]=crate::gateway091::shared::team_spawn::POLICY.into();
        row["arenas"]=1.into();row["matchmaker"]["team_size"]=15.into();assert_eq!(load(&row).unwrap().matchmaker.unwrap().places(),30);
    }
    #[test] fn p05c_configuration_roster_is_an_explicit_bounded_profile13_option() {
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs").join(format!("p05c-config-{stamp}"));
        fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();fs::write(root.join("token.txt"),"a".repeat(43)).unwrap();
        let mut value=serde_json::json!({"login_bind":"127.0.0.1:23014","base_bind":"127.0.0.1:23015","identity_endpoint":"127.0.0.1:3395",
            "identity_token_file":root.join("token.txt"),"local_root":root,"session_duration_seconds":600});
        let path=root.join("gateway.json");let load=|v:&Value|{fs::write(&path,serde_json::to_vec(v).unwrap()).unwrap();Config::load(path.to_str().unwrap())};
        assert_eq!(load(&value).unwrap().battle_players,2);value["battle_players"]=6.into();assert!(load(&value).is_err());
        for field in ["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression",
            "crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle"]{value[field]=true.into();}
        for n in 2..=6{value["battle_players"]=n.into();assert_eq!(load(&value).unwrap().battle_players,n as usize);}
        for bad in [serde_json::json!(1),serde_json::json!(7),serde_json::json!(-1),serde_json::json!(2.0),true.into(),"6".into(),Value::Null]{
            value["battle_players"]=bad;assert!(load(&value).is_err());}
        // SPAWN-15: 7..30 places need the team-base policy and connection capacity.
        value["battle_players"]=6.into();assert!(!load(&value).unwrap().team_base_spawn);
        value["spawn_policy"]=crate::gateway091::shared::team_spawn::POLICY.into();assert!(load(&value).unwrap().team_base_spawn);
        value["battle_players"]=30.into();assert!(load(&value).is_err());
        value["connection_capacity"]=30.into();assert_eq!(load(&value).unwrap().battle_players,30);
        for n in [7,15,29]{value["battle_players"]=n.into();assert_eq!(load(&value).unwrap().battle_players,n as usize);}
        for bad in [serde_json::json!(31),serde_json::json!(1)]{value["battle_players"]=bad;assert!(load(&value).is_err());}
        value["battle_players"]=30.into();value["connection_capacity"]=29.into();assert!(load(&value).is_err());
        value["connection_capacity"]=30.into();
        for wrong in ["spawn15-team-base-formation-v2".into(),"".into(),true.into(),Value::Null]{value["spawn_policy"]=wrong;assert!(load(&value).is_err());}
        value["spawn_policy"]=crate::gateway091::shared::team_spawn::POLICY.into();value["profile13_battle"]=false.into();assert!(load(&value).is_err());
    }
    #[test] fn spawn15_full_stand_config_fits_the_field_bound_and_overflow_names_it() {
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs").join(format!("spawn15-fields-{stamp}"));
        fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();fs::write(root.join("token.txt"),"a".repeat(43)).unwrap();
        let mut value=serde_json::json!({"login_bind":"127.0.0.1:23014","base_bind":"127.0.0.1:23015","identity_endpoint":"127.0.0.1:3395",
            "identity_token_file":root.join("token.txt"),"local_root":root,"session_duration_seconds":600});
        let path=root.join("gateway.json");let load=|v:&Value|{fs::write(&path,serde_json::to_vec(v).unwrap()).unwrap();Config::load(path.to_str().unwrap())};
        // 30 keys: the owner stand shape that the old bound (29) refused, defaults spelled out.
        for field in ["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression",
            "crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle","p04m_pool","p06t_mixed_ammo","visibility_v1"]{value[field]=true.into();}
        for field in ["training_rooms","p08b_owner_battle_hold","p08c_late_results","p08c_late_notice_experimental","p06t_ammo_rack_detonation"]{value[field]=false.into();}
        value["p08c_late_results_accounts"]=serde_json::json!([]);value["battle_players"]=2.into();value["connection_capacity"]=256.into();
        value["arenas"]=2.into();value["spawn_policy"]=crate::gateway091::shared::team_spawn::POLICY.into();
        value["catalog"]=serde_json::json!({"version":1,"sha256":crate::gateway091::shared::vehicle_catalog::CATALOG_SHA256});
        assert_eq!(value.as_object().unwrap().len(),30);
        let loaded=load(&value).unwrap();assert!(loaded.team_base_spawn&&loaded.arenas==2);
        let mut many=value.clone();for n in 0..MAX_CONFIG_FIELDS-30{many[format!("unknown_{n}")]=true.into();}
        let error=load(&many).err().unwrap().to_string();assert!(error.contains("gateway config fields"),"{error}");
        many["one_more"]=true.into();let error=load(&many).err().unwrap().to_string();assert!(error.contains("too many config fields"),"{error}");
        let mut raw=serde_json::to_string(&value).unwrap();raw.pop();raw.push_str(",\"arenas\":2}");fs::write(&path,raw).unwrap();
        let error=Config::load(path.to_str().unwrap()).err().unwrap().to_string();assert!(error.contains("duplicate config field"),"{error}");
    }
    #[test] fn cat01_catalog_is_an_explicit_hash_bound_mixed_profile13_option() {
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs").join(format!("cat01-config-{stamp}"));
        fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();fs::write(root.join("token.txt"),"a".repeat(43)).unwrap();
        let mut value=serde_json::json!({"login_bind":"127.0.0.1:23014","base_bind":"127.0.0.1:23015","identity_endpoint":"127.0.0.1:3395",
            "identity_token_file":root.join("token.txt"),"local_root":root,"session_duration_seconds":600});
        let path=root.join("gateway.json");let load=|v:&Value|{fs::write(&path,serde_json::to_vec(v).unwrap()).unwrap();Config::load(path.to_str().unwrap())};
        let sha=crate::gateway091::shared::vehicle_catalog::CATALOG_SHA256;
        assert!(!load(&value).unwrap().catalog_v1);
        value["catalog"]=serde_json::json!({"version":1,"sha256":sha});assert!(load(&value).is_err(),"legacy writer must refuse catalog");
        for field in ["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression",
            "crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle","p04m_pool","p06t_mixed_ammo"]{value[field]=true.into();}
        assert!(load(&value).unwrap().catalog_v1);
        for bad in [serde_json::json!({"version":1,"sha256":"0".repeat(64)}),serde_json::json!({"version":2,"sha256":sha}),
            serde_json::json!({"version":1,"sha256":sha,"extra":true}),serde_json::json!({"version":1}),true.into(),Value::Null,sha.into()]{
            value["catalog"]=bad;assert!(load(&value).is_err());}
        value.as_object_mut().unwrap().remove("catalog");assert!(!load(&value).unwrap().catalog_v1);
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
        assert!(!load(&roster).unwrap().crew_progression);
        let mut progression=roster.clone();progression["crew_progression"]=true.into();assert!(load(&progression).unwrap().crew_progression);
        assert!(!load(&progression).unwrap().crew_dismissal);
        let mut dismissal=progression.clone();dismissal["crew_dismissal"]=true.into();assert!(load(&dismissal).unwrap().crew_dismissal);
        assert!(!load(&dismissal).unwrap().crew_barracks_recruitment);
        let mut barracks=dismissal.clone();barracks["crew_barracks_recruitment"]=true.into();
        assert!(load(&barracks).unwrap().crew_barracks_recruitment);
        for bad in [Value::Null,0.into(),"true".into(),serde_json::json!({})] {
            let mut row=barracks.clone();row["crew_barracks_recruitment"]=bad;assert!(load(&row).is_err());
        }
        barracks["crew_dismissal"]=false.into();assert!(load(&barracks).is_err());
        for bad in [Value::Null,0.into(),"true".into(),serde_json::json!({})] {
            let mut row=dismissal.clone();row["crew_dismissal"]=bad;assert!(load(&row).is_err());
        }
        dismissal["crew_progression"]=false.into();assert!(load(&dismissal).is_err());
        for bad in [Value::Null,0.into(),"true".into(),serde_json::json!({})] {
            let mut row=progression.clone();row["crew_progression"]=bad;assert!(load(&row).is_err());
        }
        progression["crew_roster_recruitment"]=false.into();assert!(load(&progression).is_err());
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
        let mut wrong=compatible.clone();wrong["account_id"]=Value::String("12345678-1234-4234-8234-123456789abd".to_owned());
        fs::write(root.join("compatibility.json"),serde_json::to_vec(&wrong).unwrap()).unwrap();
        assert!(verify_fixture_identity(&profile).is_err());
        wrong["account_id"]=Value::String(account.to_owned());wrong["native_database_id"]=serde_json::json!(18);
        fs::write(root.join("compatibility.json"),serde_json::to_vec(&wrong).unwrap()).unwrap();
        assert!(verify_fixture_identity(&profile).is_err());
        // A P09E research manifest has 17 top-level fields; metadata keeps its
        // own larger bound while duplicate keys stay rejected.
        fs::write(root.join("compatibility.json"),serde_json::to_vec(&compatible).unwrap()).unwrap();
        let manifest=|count:usize|{let mut v=serde_json::json!({"account_id":account,"native_database_id":17});
            for i in 2..count {v[format!("field_{i}")]=serde_json::json!(i);} serde_json::to_vec(&v).unwrap()};
        fs::write(root.join("manifest.json"),manifest(17)).unwrap();verify_fixture_identity(&profile).unwrap();
        fs::write(root.join("manifest.json"),manifest(64)).unwrap();verify_fixture_identity(&profile).unwrap();
        fs::write(root.join("manifest.json"),manifest(65)).unwrap();assert!(verify_fixture_identity(&profile).is_err());
        fs::write(root.join("manifest.json"),format!(r#"{{"account_id":"{account}","native_database_id":17,"native_database_id":17}}"#)).unwrap();
        assert!(verify_fixture_identity(&profile).is_err());
        let seventeen=String::from_utf8(manifest(17)).unwrap();
        assert!(object(seventeen.as_bytes(),&[]).is_err(),"requests keep the 16-field guard");
    }
    #[test] fn barracks_reply_binds_both_extension_fields_to_request_delta_and_identity() {
        let profile=Profile{account_id:"00000000-0000-0000-0000-000000000001".into(),database_id:900001,name:"Test".into(),fixture_dir:PathBuf::from("unused")};
        let request=crate::crew_barracks091::Request{id:226,shop_revision:3,vehicle_type:7169,role:4,cost:0};
        let value=serde_json::json!({"status":"recruited","account_id":profile.account_id,"native_database_id":900001,"command_key":"p04k:key:226",
            "revision":57,"wire_revision":2,"replayed":false,"result_code":0,"tankman_inventory_id":12,
            "tankman_descriptor_hex":"081c04320000000c000c000c00400600000000420000000000",
            "update_hex":"80027d285507707265765265764b0155037265764b025509696e76656e746f72797d284b087d285509636f6d7044657363727d284b0c5519081c04320000000c000c000c0040060000000042000000000075550776656869636c657d284b0c4affffffff757575550573746174737d28550c66726565544d656e4c6566744b0475752e"});
        let check=|v:&Value|barracks_reply(&serde_json::to_vec(v).unwrap(),&profile,"p04k:key:226",56,1,request);
        assert_eq!(check(&value).unwrap().recruitment.unwrap().tankman_id,12);
        assert!(service_reply(&serde_json::to_vec(&value).unwrap(),&profile,"p04k:key:226",56,1,"recruited").is_err());
        for key in value.as_object().unwrap().keys() {let mut bad=value.clone();bad.as_object_mut().unwrap().remove(key);assert!(check(&bad).is_err());}
        for (key,replacement) in [("tankman_inventory_id",13.into()),("tankman_inventory_id",true.into()),
            ("tankman_descriptor_hex","00".repeat(25).into()),("tankman_descriptor_hex",Value::Null),
            ("account_id","foreign".into()),("native_database_id",900002.into()),("command_key","other".into()),
            ("revision",58.into()),("wire_revision",3.into()),("result_code",(-10).into()),("status","dismissed".into())] {
            let mut bad=value.clone();bad[key]=replacement;assert!(check(&bad).is_err(),"{key}");
        }
        let mut rejected=value.clone();rejected["status"]="rejected".into();rejected["revision"]=56.into();rejected["wire_revision"]=1.into();
        rejected["result_code"]=(-10).into();rejected["update_hex"]="".into();assert!(check(&rejected).is_err());
        rejected["tankman_inventory_id"]=0.into();rejected["tankman_descriptor_hex"]="".into();assert!(check(&rejected).unwrap().recruitment.is_none());
        let raw=serde_json::to_vec(&value).unwrap();let mut duplicate=raw[..raw.len()-1].to_vec();duplicate.extend(b",\"tankman_inventory_id\":12}");
        assert!(barracks_reply(&duplicate,&profile,"p04k:key:226",56,1,request).is_err());
        let mut extra=value.clone();extra["extension"]=serde_json::json!({});assert!(check(&extra).is_err());
        let mut replay=value;replay["replayed"]=true.into();assert!(check(&replay).unwrap().replayed);
    }

}

#[cfg(test)]
#[path="identity_late_results_tests.rs"]
mod late_results_tests;

#[cfg(test)]
#[path="network_config_tests.rs"]
pub(crate) mod net02_config_tests;

#[cfg(test)]
#[path="network_loss_config_tests.rs"]
mod net02_loss_config_tests;

#[cfg(test)]
#[path="domain_config_tests.rs"]
mod domain_config_tests;

#[cfg(test)]
#[path="capacity_config_tests.rs"]
mod capacity_config_tests;
