//! Bounded P08B protocol and authenticated owned-loadout boundary.
//! Native queue arguments are preferences, never ownership or battle state.
//! JSON is private loopback data from the existing single account writer; it
//! contains no executable objects, native pickle or caller-selected paths.
use std::{collections::BTreeMap, fmt, io};
use serde::{Deserialize, Deserializer, de::{self, MapAccess, SeqAccess, Visitor}};
use serde_json::Value;
use sha2::{Digest, Sha256};
use crate::gateway091::shared::vehicle_profile::VehicleKind;

pub const MAX_REQUEST_BYTES: usize = 4096;
pub const MAX_REPLY_BYTES: usize = 8192;
pub const POLICY_SHA256: &str = "cddd7d8cfabe8a4df5543fdcef14dd5518c36bc8bce431cfb502a5c72903ccda";
const MAX_DEPTH: usize = 8;
const MAX_NODES: usize = 256;

fn bad(reason: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, format!("profile13 battle: {reason}"))
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NativeCommand {
    Join { native_inventory_id: i64, gameplays_mask: i32 },
    Cancel,
    QueueInfo,
}

/// Exact original #717 doCmdInt3 / REQUEST_ID_NO_RESPONSE queue family.
/// Queue-info's first argument is queue type 1, not the selected inventory ID.
pub fn native_command(packet: &[u8]) -> io::Result<Option<NativeCommand>> {
    if packet.first() != Some(&0x8e) || packet.len() < 7 { return Ok(None); }
    let command = i16::from_le_bytes([packet[5], packet[6]]);
    if ![502, 700, 701].contains(&command) { return Ok(None); }
    if packet.len() != 23 || packet[..5] != [0x8e, 20, 0, 202, 0] {
        return Err(bad("native queue envelope"));
    }
    let first = i64::from_le_bytes(packet[7..15].try_into().map_err(|_| bad("queue argument"))?);
    let mask = i32::from_le_bytes(packet[15..19].try_into().map_err(|_| bad("queue mask"))?);
    let map = i32::from_le_bytes(packet[19..23].try_into().map_err(|_| bad("queue map"))?);
    let result = match command {
        700 if (1..=i32::MAX as i64).contains(&first) && (1..=7).contains(&mask)
            && mask & 1 == 1 && map == 0 => NativeCommand::Join {
                native_inventory_id: first, gameplays_mask: mask,
            },
        701 if first == 0 && mask == 0 && map == 0 => NativeCommand::Cancel,
        502 if first == 1 && mask == 0 && map == 0 => NativeCommand::QueueInfo,
        _ => return Err(bad("unsupported native queue arguments")),
    };
    Ok(Some(result))
}

/// #717 Account.onEnqueueFailure(UINT8 queueType, UINT8 errorCode, STRING).
/// Source-bound method ordering yields index20 / wire0x4f; indices4/5/18
/// independently match the native onEnqueued/onDequeued/onCmdResponseExt.
/// Original RandomQueueFunctional stops its request and displays the localized
/// JOIN_FAILURE name. No fabricated queue-success/dequeue is sent on refusal.
/// Native reception of this newly used failure callback remains a live gate.
pub fn enqueue_failure(code: &str) -> io::Result<Vec<u8>> {
    if code.is_empty() || code.len()>64 || !code.bytes().all(|b|b.is_ascii_uppercase()||b==b'_'||b.is_ascii_digit()) {
        return Err(bad("admission rejection code"));
    }
    // constants.JOIN_FAILURE: ACCOUNT_LOCK=3, WRONG_VEHICLE=4,
    // WRONG_ARENA_STATE=8. The original functional ignores errorStr and uses
    // its own localized message for this code; STRING is therefore empty.
    let error=match code {
        "VEHICLE_RESERVED"=>3,
        "BATTLE_BUSY"|"BATTLE_PROFILE_MISMATCH"|"STALE_REVISION"|"RUN_FENCED"|"RUN_NOT_OPEN"=>8,
        _=>4,
    };
    Ok(vec![0x13,0x4f,3,1,error,0])
}

/// serde_json::Value accepts duplicate keys. This visitor deliberately rejects
/// them at every level, and rejects floating point throughout this integer DTO.
struct Unique(Value);
impl<'de> Deserialize<'de> for Unique {
    fn deserialize<D: Deserializer<'de>>(input: D) -> Result<Self, D::Error> {
        struct Fields;
        impl<'de> Visitor<'de> for Fields {
            type Value = Unique;
            fn expecting(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.write_str("bounded unique-key primitive JSON")
            }
            fn visit_bool<E: de::Error>(self, v: bool) -> Result<Unique, E> { Ok(Unique(v.into())) }
            fn visit_i64<E: de::Error>(self, v: i64) -> Result<Unique, E> { Ok(Unique(v.into())) }
            fn visit_u64<E: de::Error>(self, v: u64) -> Result<Unique, E> { Ok(Unique(v.into())) }
            fn visit_unit<E: de::Error>(self) -> Result<Unique, E> { Ok(Unique(Value::Null)) }
            fn visit_str<E: de::Error>(self, v: &str) -> Result<Unique, E> {
                if v.len() > MAX_REQUEST_BYTES { return Err(E::custom("string bound")); }
                Ok(Unique(v.into()))
            }
            fn visit_string<E: de::Error>(self, v: String) -> Result<Unique, E> { self.visit_str(&v) }
            fn visit_seq<S: SeqAccess<'de>>(self, mut input: S) -> Result<Unique, S::Error> {
                let mut rows = Vec::new();
                while let Some(Unique(value)) = input.next_element()? {
                    if rows.len() >= 64 { return Err(de::Error::custom("array bound")); }
                    rows.push(value);
                }
                Ok(Unique(Value::Array(rows)))
            }
            fn visit_map<M: MapAccess<'de>>(self, mut input: M) -> Result<Unique, M::Error> {
                let mut rows = BTreeMap::new();
                while let Some((key, Unique(value))) = input.next_entry::<String, Unique>()? {
                    if key.is_empty() || key.len() > 64 || rows.len() >= 32
                        || rows.insert(key, value).is_some() {
                        return Err(de::Error::custom("duplicate/key/object bound"));
                    }
                }
                Ok(Unique(Value::Object(rows.into_iter().collect())))
            }
        }
        input.deserialize_any(Fields)
    }
}

fn walk(value: &Value, depth: usize, nodes: &mut usize) -> io::Result<()> {
    *nodes += 1;
    if depth > MAX_DEPTH || *nodes > MAX_NODES { return Err(bad("JSON depth/node bound")); }
    match value {
        Value::Object(rows) => for row in rows.values() { walk(row, depth + 1, nodes)?; },
        Value::Array(rows) => for row in rows { walk(row, depth + 1, nodes)?; },
        _ => {},
    }
    Ok(())
}

pub fn bounded_json(raw: &[u8], maximum: usize) -> io::Result<Value> {
    if ![MAX_REQUEST_BYTES, MAX_REPLY_BYTES].contains(&maximum) || raw.is_empty() || raw.len() > maximum {
        return Err(bad("JSON byte bound"));
    }
    let Unique(value) = serde_json::from_slice(raw).map_err(|_| bad("unique integer JSON"))?;
    walk(&value, 0, &mut 0)?;
    if !value.is_object() { return Err(bad("JSON root object")); }
    Ok(value)
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Context {
    pub account_id: String,
    pub native_database_id: i32,
    pub command_key: String,
    pub expected_revision: u64,
    pub run_id: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum FinishReason { ManualLeave, BattleFailure, Disconnect, Cancelled }
impl FinishReason {
    pub fn name(self) -> &'static str {
        match self { Self::ManualLeave => "manual_leave", Self::BattleFailure => "battle_failure",
            Self::Disconnect => "disconnect", Self::Cancelled => "cancelled" }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Request {
    RunOpen,
    Inspect,
    Admit { battle: u64, native_inventory_id: u32 },
    Finish { battle: u64, native_inventory_id: u32, reservation_id: String,
        remaining_ap: u16, terminal_hp: i16, reason: FinishReason },
}
impl Request {
    pub fn operation(&self) -> &'static str {
        match self { Self::RunOpen => "run_open", Self::Inspect => "inspect",
            Self::Admit { .. } => "admit", Self::Finish { .. } => "finish" }
    }
}

fn uuid(value: &str) -> bool {
    value.len() == 36 && value != "00000000-0000-0000-0000-000000000000"
        && value.bytes().enumerate().all(|(i, b)| if [8, 13, 18, 23].contains(&i) { b == b'-' }
            else { b.is_ascii_digit() || (b'a'..=b'f').contains(&b) })
}
fn identifier(value: &str, maximum: usize) -> bool {
    !value.is_empty() && value.len() <= maximum && value.bytes().all(|b|
        b.is_ascii_alphanumeric() || b"-_: .".contains(&b)) && !value.contains(' ')
}
fn digest(value: &Value) -> io::Result<String> {
    // Every loadout string is ASCII; sorted JSON then matches the writer's
    // canonical ensure_ascii=True/separators=(',', ':') representation.
    let bytes = serde_json::to_vec(value).map_err(|_| bad("canonical loadout"))?;
    Ok(format!("{:x}", Sha256::digest(bytes)))
}
fn validate_context(context: &Context) -> io::Result<()> {
    if !uuid(&context.account_id) || !uuid(&context.run_id) || context.native_database_id <= 0
        || !identifier(&context.command_key, 96) || context.expected_revision > i32::MAX as u64 {
        return Err(bad("request identity/revision/key"));
    }
    Ok(())
}
fn battle_id(run: &str, battle: u64) -> io::Result<String> {
    if !uuid(run) || battle == 0 { return Err(bad("battle ID")); }
    Ok(format!("{run}:{battle}"))
}

pub fn encode_request(context: &Context, request: &Request) -> io::Result<Vec<u8>> {
    validate_context(context)?;
    if !matches!(request, Request::Inspect) && context.expected_revision < 13 { return Err(bad("mutation source revision")); }
    let mut value = serde_json::json!({"version":1,"operation":request.operation(),
        "account_id":context.account_id,"native_database_id":context.native_database_id,
        "command_key":context.command_key,"expected_revision":context.expected_revision,"run_id":context.run_id});
    match request {
        Request::RunOpen | Request::Inspect => {},
        Request::Admit { battle, native_inventory_id }
        | Request::Finish { battle, native_inventory_id, .. } => {
            if !(1..=i32::MAX as u32).contains(native_inventory_id) { return Err(bad("native inventory ID")); }
            value["battle_id"] = battle_id(&context.run_id, *battle)?.into();
            value["native_inventory_id"] = (*native_inventory_id).into();
        },
    }
    if let Request::Finish { reservation_id, remaining_ap, terminal_hp, reason, .. } = request {
        if !identifier(reservation_id, 96) || *remaining_ap > 96 || !(0..=2150).contains(terminal_hp) {
            return Err(bad("finish arguments"));
        }
        value["reservation_id"] = reservation_id.as_str().into();
        value["remaining_ap"] = (*remaining_ap).into(); value["terminal_hp"] = (*terminal_hp).into();
        value["reason"] = reason.name().into();
    }
    let raw = serde_json::to_vec(&value).map_err(|_| bad("request serialization"))?;
    bounded_json(&raw, MAX_REQUEST_BYTES)?;
    Ok(raw)
}

fn keys<'a>(value: &'a Value, expected: &[&str]) -> io::Result<&'a serde_json::Map<String, Value>> {
    let object = value.as_object().ok_or_else(|| bad("object type"))?;
    if object.len() != expected.len() || expected.iter().any(|key| !object.contains_key(*key)) {
        return Err(bad("exact object fields"));
    }
    Ok(object)
}
fn text<'a>(value: &'a Value, key: &str) -> io::Result<&'a str> {
    value[key].as_str().ok_or_else(|| bad("string field"))
}
fn number(value: &Value, key: &str) -> io::Result<u64> {
    value[key].as_u64().ok_or_else(|| bad("unsigned integer field"))
}
fn boolean(value: &Value, key: &str) -> io::Result<bool> {
    value[key].as_bool().ok_or_else(|| bad("boolean field"))
}
fn owned_id(value: &str, account: &str) -> bool {
    identifier(value, 128) && value.strip_prefix(account).is_some_and(|tail| tail.starts_with(':') && tail.len() > 1)
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct FrozenLoadout {
    pub kind: VehicleKind,
    pub descriptor: Vec<u8>,
    pub native_inventory_id: u32,
    pub vehicle_inventory_id: String,
    pub ap_count: u16,
    pub shell_definition_id: String,
    pub shell_compact_id: u32,
    pub max_hp: i16,
    pub crew_ids: Vec<String>,
    pub sha256: String,
}

fn frozen(value: &Value, account: &str, expected_sha: &str) -> io::Result<FrozenLoadout> {
    keys(value, &["kind", "descriptor_hex", "native_inventory_id", "vehicle_inventory_id", "ap_count",
        "shell_definition_id", "shell_compact_id", "max_hp", "crew_ids"])?;
    let kind = match text(value, "kind")? { "ms1" => VehicleKind::Ms1, "is7" => VehicleKind::Is7,
        _ => return Err(bad("unsupported mounted vehicle")) };
    let descriptor = kind.descriptor().iter().map(|b| format!("{b:02x}")).collect::<String>();
    let native_inventory_id = u32::try_from(number(value, "native_inventory_id")?).map_err(|_| bad("inventory bound"))?;
    let ap_count = u16::try_from(number(value, "ap_count")?).map_err(|_| bad("AP bound"))?;
    let shell_compact_id = u32::try_from(number(value, "shell_compact_id")?).map_err(|_| bad("shell bound"))?;
    let max_hp = i16::try_from(number(value, "max_hp")?).map_err(|_| bad("health bound"))?;
    let vehicle_inventory_id = text(value, "vehicle_inventory_id")?;
    let shell_definition_id = text(value, "shell_definition_id")?;
    let crew = value["crew_ids"].as_array().ok_or_else(|| bad("crew list"))?;
    let mut crew_ids = Vec::new();
    for row in crew {
        let id = row.as_str().ok_or_else(|| bad("crew ID type"))?;
        if id.len() > 96 || !owned_id(id, account) || crew_ids.iter().any(|other| other == id) { return Err(bad("crew ownership/duplicate")); }
        crew_ids.push(id.to_owned());
    }
    if text(value, "descriptor_hex")? != descriptor || !(1..=i32::MAX as u32).contains(&native_inventory_id)
        || !(1..=kind.ammo_limit()).contains(&ap_count) || shell_compact_id != kind.shell_compact_id()
        || max_hp != kind.max_health() || !owned_id(vehicle_inventory_id, account)
        || native_inventory_id != (if kind == VehicleKind::Ms1 { 1 } else { 2 })
        || vehicle_inventory_id != format!("{account}:{}", if kind == VehicleKind::Ms1 { "starter-vehicle-v1" } else { "test-is7-v1" })
        || shell_definition_id != (if kind == VehicleKind::Ms1 { "shell:ms1-stock-ap" } else { "shell:is7-stock-ap" })
        || crew_ids.len() != (if kind == VehicleKind::Ms1 { 2 } else { 5 })
        || digest(value)? != expected_sha {
        return Err(bad("frozen owned loadout binding"));
    }
    Ok(FrozenLoadout { kind, descriptor: kind.descriptor().to_vec(), native_inventory_id, vehicle_inventory_id: vehicle_inventory_id.into(),
        ap_count, shell_definition_id: shell_definition_id.into(), shell_compact_id, max_hp, crew_ids,
        sha256: expected_sha.into() })
}

impl FrozenLoadout {
    /// Recheck the authenticated immutable receipt at the world boundary. This
    /// also prevents a local caller from forging public DTO fields after parse.
    pub fn validate_owned(&self, account: &str) -> io::Result<()> {
        let descriptor = self.descriptor.iter().map(|b| format!("{b:02x}")).collect::<String>();
        let value = serde_json::json!({"kind":self.kind.label(),"descriptor_hex":descriptor,
            "native_inventory_id":self.native_inventory_id,"vehicle_inventory_id":self.vehicle_inventory_id,
            "ap_count":self.ap_count,"shell_definition_id":self.shell_definition_id,
            "shell_compact_id":self.shell_compact_id,"max_hp":self.max_hp,"crew_ids":self.crew_ids});
        if frozen(&value, account, &self.sha256)? != *self { return Err(bad("changed frozen loadout")); }
        Ok(())
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BattleResult {
    pub reason: String,
    pub remaining_ap: u16,
    pub consumed_ap: u16,
    pub terminal_hp: Option<i16>,
    pub destroyed: Option<bool>,
    pub repaired_hp: i16,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReservationStatus { Active, Finished, AbortedRestart }

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Reservation {
    pub reservation_id: String,
    pub run_id: String,
    pub battle: u64,
    pub native_inventory_id: u32,
    pub vehicle_inventory_id: String,
    pub status: ReservationStatus,
    pub frozen: FrozenLoadout,
    pub result: Option<BattleResult>,
}

fn reservation(value: &Value, account: &str) -> io::Result<Reservation> {
    keys(value, &["reservation_id", "run_id", "battle_id", "native_inventory_id", "vehicle_inventory_id",
        "status", "frozen", "frozen_sha256", "result"])?;
    let reservation_id = text(value, "reservation_id")?;
    let run_id = text(value, "run_id")?;
    if !identifier(reservation_id, 96) || !uuid(run_id) { return Err(bad("reservation identity")); }
    let raw_battle = text(value, "battle_id")?;
    let suffix = raw_battle.strip_prefix(run_id).and_then(|v| v.strip_prefix(':')).ok_or_else(|| bad("battle run binding"))?;
    let battle = suffix.parse::<u64>().map_err(|_| bad("battle integer"))?;
    if raw_battle != battle_id(run_id, battle)? { return Err(bad("canonical battle ID")); }
    let frozen = frozen(&value["frozen"], account, text(value, "frozen_sha256")?)?;
    let native_inventory_id = number(value, "native_inventory_id")?;
    let vehicle_inventory_id = text(value, "vehicle_inventory_id")?;
    if native_inventory_id != u64::from(frozen.native_inventory_id) || vehicle_inventory_id != frozen.vehicle_inventory_id {
        return Err(bad("reservation selected vehicle"));
    }
    let status = match text(value, "status")? { "active" => ReservationStatus::Active,
        "finished" => ReservationStatus::Finished, "aborted_restart" => ReservationStatus::AbortedRestart,
        _ => return Err(bad("reservation status")) };
    let result = if value["result"].is_null() {
        if status != ReservationStatus::Active { return Err(bad("terminal reservation without result")); }
        None
    } else {
        if status == ReservationStatus::Active { return Err(bad("active reservation has result")); }
        let result = &value["result"];
        keys(result, &["reason", "remaining_ap", "consumed_ap", "terminal_hp", "destroyed", "repaired_hp", "credits", "xp"])?;
        let reason = text(result, "reason")?;
        let remaining_ap = u16::try_from(number(result, "remaining_ap")?).map_err(|_| bad("remaining AP bound"))?;
        let consumed_ap = u16::try_from(number(result, "consumed_ap")?).map_err(|_| bad("consumed AP bound"))?;
        let repaired_hp = i16::try_from(number(result, "repaired_hp")?).map_err(|_| bad("repaired HP bound"))?;
        let (terminal_hp, destroyed) = if status == ReservationStatus::AbortedRestart {
            if !result["terminal_hp"].is_null() || !result["destroyed"].is_null() {
                return Err(bad("restart terminal state must remain unknown"));
            }
            (None, None)
        } else {
            let hp = i16::try_from(number(result, "terminal_hp")?).map_err(|_| bad("terminal HP bound"))?;
            let destroyed = boolean(result, "destroyed")?;
            if !(0..=frozen.max_hp).contains(&hp) || destroyed != (hp == 0) {
                return Err(bad("terminal health/destruction"));
            }
            (Some(hp), Some(destroyed))
        };
        if remaining_ap.checked_add(consumed_ap) != Some(frozen.ap_count)
            || repaired_hp != frozen.max_hp || number(result, "credits")? != 0 || number(result, "xp")? != 0
            || (status == ReservationStatus::Finished && !["manual_leave", "battle_failure", "disconnect", "cancelled"].contains(&reason))
            || (status == ReservationStatus::AbortedRestart && (reason != "aborted_restart" || consumed_ap != 0)) {
            return Err(bad("terminal result policy"));
        }
        Some(BattleResult { reason: reason.into(), remaining_ap, consumed_ap, terminal_hp, destroyed, repaired_hp })
    };
    Ok(Reservation { reservation_id: reservation_id.into(), run_id: run_id.into(), battle,
        native_inventory_id: frozen.native_inventory_id, vehicle_inventory_id: vehicle_inventory_id.into(), status, frozen, result })
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReplyStatus { Ready, Admitted, Finished, Inspected, Rejected }

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Reply {
    pub status: ReplyStatus,
    pub source_revision: u64,
    pub revision: u64,
    pub replayed: bool,
    pub code: Option<String>,
    pub reservation: Option<Reservation>,
}

const REJECTIONS: &[&str] = &["AMMUNITION_EMPTY", "AMMUNITION_UNSUPPORTED", "BATTLE_PROFILE_UNSUPPORTED",
    "DUPLICATE_PAYLOAD_MISMATCH", "INCOMPLETE_CREW", "INVALID_RESULT", "RESERVATION_MISMATCH",
    "RESERVATION_TERMINAL", "RUN_FENCED", "RUN_NOT_OPEN", "STALE_REVISION", "UNKNOWN_VEHICLE", "VEHICLE_RESERVED"];

pub fn parse_reply(raw: &[u8], context: &Context, request: &Request) -> io::Result<Reply> {
    // This also rejects impossible caller-selected operation arguments.
    encode_request(context, request)?;
    let value = bounded_json(raw, MAX_REPLY_BYTES)?;
    keys(&value, &["version", "operation", "status", "account_id", "native_database_id", "command_key", "run_id",
        "source_revision", "revision", "replayed", "code", "reservation", "policy_sha256"])?;
    if number(&value, "version")? != 1 || text(&value, "operation")? != request.operation()
        || text(&value, "account_id")? != context.account_id
        || number(&value, "native_database_id")? != context.native_database_id as u64
        || text(&value, "command_key")? != context.command_key || text(&value, "run_id")? != context.run_id
        || text(&value, "policy_sha256")? != POLICY_SHA256 {
        return Err(bad("reply identity/operation/policy"));
    }
    let source_revision = number(&value, "source_revision")?;
    let revision = number(&value, "revision")?;
    if source_revision != context.expected_revision || !(13..=i32::MAX as u64).contains(&revision) {
        return Err(bad("reply revision binding"));
    }
    let replayed = boolean(&value, "replayed")?;
    let status = match text(&value, "status")? { "ready" => ReplyStatus::Ready, "admitted" => ReplyStatus::Admitted,
        "finished" => ReplyStatus::Finished, "inspected" => ReplyStatus::Inspected, "rejected" => ReplyStatus::Rejected,
        _ => return Err(bad("reply status")) };
    let code = if value["code"].is_null() { None }
        else { let code = text(&value, "code")?;
            if !REJECTIONS.contains(&code) { return Err(bad("unknown rejection code")); }
            Some(code.to_owned()) };
    if (status == ReplyStatus::Rejected) != code.is_some() { return Err(bad("rejection status/code")); }
    let reservation = if value["reservation"].is_null() { None }
        else { Some(reservation(&value["reservation"], &context.account_id)?) };
    if status == ReplyStatus::Rejected && reservation.is_some() { return Err(bad("rejection carries reservation")); }
    if status != ReplyStatus::Rejected {
        let expected_status = match request { Request::RunOpen => ReplyStatus::Ready, Request::Inspect => ReplyStatus::Inspected,
            Request::Admit { .. } => ReplyStatus::Admitted, Request::Finish { .. } => ReplyStatus::Finished };
        if status != expected_status { return Err(bad("operation result status")); }
        match request {
            Request::Inspect => {
                if reservation.as_ref().is_some_and(|row| row.status != ReservationStatus::Active) {
                    return Err(bad("inspect carries terminal reservation"));
                }
            },
            Request::RunOpen => {
                if revision != source_revision && revision != source_revision.checked_add(1).ok_or_else(|| bad("revision exhausted"))? {
                    return Err(bad("run-open revision"));
                }
                if reservation.as_ref().is_some_and(|row| row.status != ReservationStatus::AbortedRestart
                    || row.run_id == context.run_id || revision == source_revision) {
                    return Err(bad("run-open recovery reservation"));
                }
            },
            Request::Admit { battle, native_inventory_id } | Request::Finish { battle, native_inventory_id, .. } => {
                if revision != source_revision.checked_add(1).ok_or_else(|| bad("revision exhausted"))? {
                    return Err(bad("mutation revision"));
                }
                let row = reservation.as_ref().ok_or_else(|| bad("missing reservation"))?;
                if row.run_id != context.run_id || row.battle != *battle || row.native_inventory_id != *native_inventory_id {
                    return Err(bad("reservation operation binding"));
                }
                match request {
                    Request::Admit { .. } => {
                        if row.status != ReservationStatus::Active || row.reservation_id != context.command_key || row.result.is_some() {
                            return Err(bad("admission reservation binding"));
                        }
                    },
                    Request::Finish { reservation_id, remaining_ap, terminal_hp, reason, .. } => {
                        let result = row.result.as_ref().ok_or_else(|| bad("missing terminal result"))?;
                        if row.status != ReservationStatus::Finished || row.reservation_id != *reservation_id
                            || result.remaining_ap != *remaining_ap || result.terminal_hp != Some(*terminal_hp)
                            || result.reason != reason.name() {
                            return Err(bad("terminal operation binding"));
                        }
                    },
                    _ => unreachable!(),
                }
            },
        }
    }
    Ok(Reply { status, source_revision, revision, replayed, code, reservation })
}

#[cfg(test)]
mod tests {
    use super::*;
    const ACCOUNT: &str = "12345678-1234-4234-8234-123456789abc";
    const RUN: &str = "87654321-4321-4321-8321-cba987654321";
    const OLD_RUN: &str = "11111111-1111-4111-8111-111111111111";
    fn context() -> Context {
        Context { account_id: ACCOUNT.into(), native_database_id: 17, command_key: "p08b:admit:7".into(),
            expected_revision: 13, run_id: RUN.into() }
    }
    fn loadout(is7: bool) -> Value {
        let crew_ids = if is7 { (1..=5).map(|n| format!("{ACCOUNT}:recruit-crew:{n}")).collect::<Vec<_>>() }
            else { vec![format!("{ACCOUNT}:ms1-commander-v1"), format!("{ACCOUNT}:ms1-driver-v1")] };
        serde_json::json!({"kind":if is7 {"is7"} else {"ms1"},
            "descriptor_hex":if is7 {"011c3a002400cd000b002f003a0000"} else {"010d1a000e00c90000001700170000"},
            "native_inventory_id":if is7 {2} else {1},
            "vehicle_inventory_id":format!("{ACCOUNT}:{}",if is7 {"test-is7-v1"} else {"starter-vehicle-v1"}),
            "ap_count":if is7 {30} else {7},"shell_definition_id":if is7 {"shell:is7-stock-ap"} else {"shell:ms1-stock-ap"},
            "shell_compact_id":if is7 {14602} else {2570},"max_hp":if is7 {2150} else {90},"crew_ids":crew_ids})
    }
    fn admitted(is7: bool) -> (Context, Request, Value) {
        let context = context();
        let frozen = loadout(is7);
        let native_inventory_id = if is7 { 2 } else { 1 };
        let request = Request::Admit { battle: u64::MAX, native_inventory_id };
        let value = serde_json::json!({"version":1,"operation":"admit","status":"admitted","account_id":ACCOUNT,
            "native_database_id":17,"command_key":context.command_key,"run_id":RUN,"source_revision":13,
            "revision":14,"replayed":false,"code":null,"policy_sha256":POLICY_SHA256,
            "reservation":{"reservation_id":context.command_key,"run_id":RUN,"battle_id":format!("{RUN}:{}",u64::MAX),
                "native_inventory_id":native_inventory_id,"vehicle_inventory_id":frozen["vehicle_inventory_id"],
                "status":"active","frozen_sha256":digest(&frozen).unwrap(),"frozen":frozen,"result":null}});
        (context, request, value)
    }
    fn parse(value: &Value, context: &Context, request: &Request) -> io::Result<Reply> {
        parse_reply(&serde_json::to_vec(value).unwrap(), context, request)
    }
    fn native(command: i16, first: i64, mask: i32, map: i32) -> Vec<u8> {
        let mut bytes = vec![0x8e, 20, 0, 202, 0]; bytes.extend(command.to_le_bytes());
        bytes.extend(first.to_le_bytes()); bytes.extend(mask.to_le_bytes()); bytes.extend(map.to_le_bytes()); bytes
    }
    #[test] fn profile13_native_admission_failure_uses_original_queue_error_callback() {
        assert_eq!(enqueue_failure("INCOMPLETE_CREW").unwrap(),vec![0x13,0x4f,3,1,4,0]);
        assert_eq!(enqueue_failure("VEHICLE_RESERVED").unwrap(),vec![0x13,0x4f,3,1,3,0]);
        assert_eq!(enqueue_failure("BATTLE_BUSY").unwrap(),vec![0x13,0x4f,3,1,8,0]);
        for bad in ["","not-a-code","../path","external message",&"A".repeat(65)] {assert!(enqueue_failure(bad).is_err());}
    }
    #[test] fn selected_native_inventory_is_preserved_and_queue_info_remains_queue_type() {
        for inventory in [1, 2, 100, i32::MAX as i64] {
            for mask in [1, 3, 5, 7] {
                assert_eq!(native_command(&native(700, inventory, mask, 0)).unwrap(),
                    Some(NativeCommand::Join { native_inventory_id: inventory, gameplays_mask: mask }));
            }
        }
        assert_eq!(native_command(&native(502, 1, 0, 0)).unwrap(), Some(NativeCommand::QueueInfo));
        assert!(native_command(&native(502, 2, 0, 0)).is_err());
        assert_eq!(native_command(&native(701, 0, 0, 0)).unwrap(), Some(NativeCommand::Cancel));
        for (first, mask, map) in [(0, 1, 0), (-1, 1, 0), (i32::MAX as i64 + 1, 1, 0),
            (1, 0, 0), (1, 2, 0), (1, 8, 0), (1, 7, 1)] {
            assert!(native_command(&native(700, first, mask, map)).is_err());
        }
        assert!(native_command(&native(701, 1, 0, 0)).is_err());
        assert_eq!(native_command(&native(100, 1, 0, 0)).unwrap(), None);
    }
    #[test] fn native_queue_truncation_extension_and_wrong_request_id_fail_closed() {
        let bytes = native(700, 2, 7, 0);
        for size in 7..bytes.len() { assert!(native_command(&bytes[..size]).is_err()); }
        let mut changed = bytes.clone(); changed.push(9); assert!(native_command(&changed).is_err());
        for offset in 1..5 { let mut changed = bytes.clone(); changed[offset] ^= 1;
            assert!(native_command(&changed).is_err()); }
    }
    #[test] fn json_rejects_ambiguity_at_any_depth_and_bounded_resources() {
        for bytes in [br#"{"a":1,"a":2}"#.as_slice(), br#"{"a":{"b":1,"b":2}}"#,
            br#"{"a":[{"b":1,"b":2}]}"#, br#"{"a":1.0}"#, br#"{"a":1e2}"#, b"[]", b"null"] {
            assert!(bounded_json(bytes, MAX_REPLY_BYTES).is_err());
        }
        bounded_json(br#"{"a":[1,true,null,"ascii",18446744073709551615]}"#, MAX_REPLY_BYTES).unwrap();
        let deep = format!("{{\"a\":{}0{}}}", "[".repeat(9), "]".repeat(9));
        assert!(bounded_json(deep.as_bytes(), MAX_REPLY_BYTES).is_err());
        let large = serde_json::json!({"a":vec![0;65]});
        assert!(bounded_json(&serde_json::to_vec(&large).unwrap(), MAX_REPLY_BYTES).is_err());
        let many = serde_json::json!({"a":vec![vec![0;64];4]});
        assert!(bounded_json(&serde_json::to_vec(&many).unwrap(), MAX_REPLY_BYTES).is_err());
        assert!(bounded_json(&vec![b' '; MAX_REPLY_BYTES+1], MAX_REPLY_BYTES).is_err());
    }
    #[test] fn requests_preserve_u64_battle_without_json_number_precision_loss() {
        let context = context();
        let request = Request::Admit { battle: u64::MAX, native_inventory_id: 2 };
        let value = bounded_json(&encode_request(&context, &request).unwrap(), MAX_REQUEST_BYTES).unwrap();
        assert_eq!(value["battle_id"], format!("{RUN}:18446744073709551615"));
        assert_eq!(value["native_inventory_id"], 2);
        assert_eq!(value.as_object().unwrap().len(), 9);
        for change in 0..7 {
            let mut wrong = context.clone(); match change {
                0 => wrong.account_id = "OTHER".into(), 1 => wrong.native_database_id = 0,
                2 => wrong.command_key = "../caller/path".into(), 3 => wrong.command_key = "x".repeat(97),
                4 => wrong.expected_revision = 12, 5 => wrong.run_id = "0".repeat(36),
                6 => wrong.expected_revision = i32::MAX as u64 + 1, _ => unreachable!(),
            }
            assert!(encode_request(&wrong, &request).is_err());
        }
        assert!(encode_request(&context, &Request::Admit { battle: 0, native_inventory_id: 1 }).is_err());
        assert!(encode_request(&context, &Request::Admit { battle: 1, native_inventory_id: 0 }).is_err());
    }
    #[test] fn frozen_owned_both_stock_profiles_have_actual_ap_and_python_canonical_hash() {
        // Independently computed with Python json.dumps(sort_keys=True,
        // ensure_ascii=True,separators=(',', ':')) over the literal fixture.
        assert_eq!(digest(&loadout(false)).unwrap(), "5631e70e35c8788d61a5249da92c58967fceeb53b4f6768a2d53cbfb5311ecc4");
        for is7 in [false, true] {
            let (context, request, value) = admitted(is7);
            let reply = parse(&value, &context, &request).unwrap();
            let frozen = &reply.reservation.unwrap().frozen;
            assert_eq!(frozen.ap_count, if is7 { 30 } else { 7 });
            assert_eq!(frozen.kind, if is7 { VehicleKind::Is7 } else { VehicleKind::Ms1 });
            assert_eq!(frozen.crew_ids.len(), if is7 { 5 } else { 2 });
            let mut replay = value.clone(); replay["replayed"] = true.into();
            assert!(parse(&replay, &context, &request).unwrap().replayed);
        }
    }
    #[test] fn loadout_rejects_semantic_changes_even_when_hash_is_recomputed() {
        for is7 in [false, true] {
            let (context, request, original) = admitted(is7);
            for change in 0..18 {
                let mut value = original.clone();
                let row = &mut value["reservation"]["frozen"];
                match change {
                    0 => row["kind"] = "other".into(), 1 => row["descriptor_hex"] = "00".into(),
                    2 => row["native_inventory_id"] = 100.into(), 3 => row["vehicle_inventory_id"] = "foreign:vehicle".into(),
                    4 => row["ap_count"] = 0.into(), 5 => row["ap_count"] = 97.into(),
                    6 => row["shell_definition_id"] = "shell:ms1-stock-he".into(),
                    7 => row["shell_compact_id"] = 3082.into(), 8 => row["max_hp"] = 1.into(),
                    9 => row["crew_ids"] = serde_json::json!([]),
                    10 => row["crew_ids"][0] = "foreign:crew".into(),
                    11 => row["crew_ids"][0] = row["crew_ids"][1].clone(),
                    12 => row["crew_ids"][0] = format!("{ACCOUNT}:{}", "a".repeat(97)).into(),
                    13 => row["ap_count"] = true.into(), 14 => row["unexpected"] = 1.into(),
                    15 => { row.as_object_mut().unwrap().remove("crew_ids"); },
                    16 => row["vehicle_inventory_id"] = format!("{ACCOUNT}:other-owned-vehicle").into(),
                    17 => row["crew_ids"][0] = format!("{ACCOUNT}:É").into(), _ => unreachable!(),
                }
                value["reservation"]["frozen_sha256"] = digest(&value["reservation"]["frozen"]).unwrap().into();
                assert!(parse(&value, &context, &request).is_err(), "is7={is7} mutation={change}");
            }
        }
    }
    #[test] fn replies_bind_identity_operation_revision_and_reservation_to_request() {
        let (context, request, original) = admitted(false);
        for change in 0..18 {
            let mut value = original.clone(); match change {
                0 => value["account_id"] = OLD_RUN.into(), 1 => value["native_database_id"] = 18.into(),
                2 => value["command_key"] = "other-command".into(), 3 => value["run_id"] = OLD_RUN.into(),
                4 => value["operation"] = "finish".into(), 5 => value["policy_sha256"] = "0".repeat(64).into(),
                6 => value["source_revision"] = 12.into(), 7 => value["revision"] = 15.into(),
                8 => value["status"] = "ready".into(), 9 => value["code"] = "VEHICLE_RESERVED".into(),
                10 => value["reservation"] = Value::Null,
                11 => value["reservation"]["native_inventory_id"] = 2.into(),
                12 => value["reservation"]["reservation_id"] = "other-command".into(),
                13 => value["reservation"]["battle_id"] = format!("{RUN}:1").into(),
                14 => value["reservation"]["frozen_sha256"] = "0".repeat(64).into(),
                15 => value["reservation"]["battle_id"] = format!("{RUN}:01").into(),
                16 => value["unexpected"] = 1.into(), 17 => value["version"] = true.into(), _ => unreachable!(),
            }
            assert!(parse(&value, &context, &request).is_err(), "mutation={change}");
        }
        let raw = serde_json::to_string(&original).unwrap().replacen("\"kind\":\"ms1\"", "\"kind\":\"ms1\",\"kind\":\"ms1\"", 1);
        assert!(parse_reply(raw.as_bytes(), &context, &request).is_err());
    }
    #[test] fn finished_result_is_zero_economy_full_repair_and_bound_to_exact_consumption() {
        let (mut context, _, mut value) = admitted(false);
        let reservation_id = context.command_key.clone(); context.command_key = "p08b:finish:7".into();
        context.expected_revision = 14;
        let request = Request::Finish { battle: u64::MAX, native_inventory_id: 1, reservation_id,
            remaining_ap: 3, terminal_hp: 0, reason: FinishReason::ManualLeave };
        value["operation"] = "finish".into(); value["status"] = "finished".into();
        value["command_key"] = context.command_key.clone().into(); value["source_revision"] = 14.into(); value["revision"] = 15.into();
        value["reservation"]["status"] = "finished".into();
        value["reservation"]["result"] = serde_json::json!({"reason":"manual_leave","remaining_ap":3,"consumed_ap":4,
            "terminal_hp":0,"destroyed":true,"repaired_hp":90,"credits":0,"xp":0});
        let reply = parse(&value, &context, &request).unwrap();
        assert_eq!(reply.reservation.unwrap().result.unwrap().consumed_ap, 4);
        for (key, wrong) in [("remaining_ap", 8.into()), ("consumed_ap", 5.into()), ("terminal_hp", 91.into()),
            ("repaired_hp", 89.into()), ("credits", 1.into()), ("xp", 1.into()), ("credits", false.into()),
            ("destroyed", false.into()), ("reason", "aborted_restart".into())] {
            let mut changed = value.clone(); changed["reservation"]["result"][key] = wrong;
            assert!(parse(&changed, &context, &request).is_err(), "field={key}");
        }
        let mut wrong = request.clone();
        if let Request::Finish { remaining_ap, .. } = &mut wrong { *remaining_ap = 4; }
        assert!(parse(&value, &context, &wrong).is_err());
    }
    #[test] fn read_rejection_and_restart_refund_have_separate_strict_contracts() {
        let (context, _, original) = admitted(false);
        let mut value = original.clone(); value["operation"] = "inspect".into(); value["status"] = "inspected".into();
        value["revision"] = 100.into();
        parse(&value, &context, &Request::Inspect).unwrap();
        value["status"] = "rejected".into(); value["code"] = "STALE_REVISION".into(); value["reservation"] = Value::Null;
        assert_eq!(parse(&value, &context, &Request::Inspect).unwrap().code.as_deref(), Some("STALE_REVISION"));
        value["code"] = "UNRECOGNIZED".into(); assert!(parse(&value, &context, &Request::Inspect).is_err());
        value = original; value["operation"] = "run_open".into(); value["status"] = "ready".into();
        value["reservation"]["run_id"] = OLD_RUN.into();
        value["reservation"]["battle_id"] = format!("{OLD_RUN}:7").into();
        value["reservation"]["status"] = "aborted_restart".into();
        value["reservation"]["result"] = serde_json::json!({"reason":"aborted_restart","remaining_ap":7,"consumed_ap":0,
            "terminal_hp":null,"destroyed":null,"repaired_hp":90,"credits":0,"xp":0});
        parse(&value, &context, &Request::RunOpen).unwrap();
        let mut lost = value.clone(); lost["reservation"]["result"]["remaining_ap"] = 6.into();
        lost["reservation"]["result"]["consumed_ap"] = 1.into();
        assert!(parse(&lost, &context, &Request::RunOpen).is_err());
        assert!(parse(&value, &context, &Request::Inspect).is_err());
        value["revision"] = 13.into(); assert!(parse(&value, &context, &Request::RunOpen).is_err());
        value["reservation"] = Value::Null; parse(&value, &context, &Request::RunOpen).unwrap();
    }
    #[test] fn profile13_actual_sqlite_writer_vectors_agree_byte_for_byte_with_rust_dto() {
        // Authored trusted writer output; no credentials, pickle or client
        // resource dump. Original: local/evidence/20261015-p08b-01/writer-vectors-01.json.
        const SHA: &str = "39ce1c7a9bdd0a44b80013c91deeb086449b5794a498d2d73db0c3cdffcfd3d6";
        let path=std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tests/fixtures/profile13-writer-vectors.json");
        let raw=std::fs::read(path).unwrap();assert!(raw.len()<=65536);
        assert_eq!(format!("{:x}",Sha256::digest(&raw)),SHA);
        let vectors:Value=serde_json::from_slice(&raw).unwrap();
        assert_eq!(vectors["version"],1);let rows=vectors["vectors"].as_array().unwrap();assert_eq!(rows.len(),8);
        for (index,row) in rows.iter().enumerate() {
            let input=&row["request"];
            let context=Context{account_id:input["account_id"].as_str().unwrap().into(),
                native_database_id:input["native_database_id"].as_i64().unwrap().try_into().unwrap(),
                command_key:input["command_key"].as_str().unwrap().into(),expected_revision:input["expected_revision"].as_u64().unwrap(),
                run_id:input["run_id"].as_str().unwrap().into()};
            let request=match input["operation"].as_str().unwrap() {
                "run_open"=>Request::RunOpen,"inspect"=>Request::Inspect,
                operation=>{
                    let battle=input["battle_id"].as_str().unwrap().rsplit_once(':').unwrap().1.parse::<u64>().unwrap();
                    let native_inventory_id=input["native_inventory_id"].as_u64().unwrap().try_into().unwrap();
                    if operation=="admit"{Request::Admit{battle,native_inventory_id}}
                    else {assert_eq!(operation,"finish");Request::Finish{battle,native_inventory_id,
                        reservation_id:input["reservation_id"].as_str().unwrap().into(),
                        remaining_ap:input["remaining_ap"].as_u64().unwrap().try_into().unwrap(),
                        terminal_hp:input["terminal_hp"].as_u64().unwrap().try_into().unwrap(),
                        reason:match input["reason"].as_str().unwrap(){"manual_leave"=>FinishReason::ManualLeave,
                            "battle_failure"=>FinishReason::BattleFailure,"disconnect"=>FinishReason::Disconnect,
                            "cancelled"=>FinishReason::Cancelled,_=>panic!("unexpected own vector reason")}}}
                },
            };
            assert_eq!(encode_request(&context,&request).unwrap(),serde_json::to_vec(input).unwrap(),"vector={index}");
            let reply=parse(&row["response"],&context,&request).unwrap_or_else(|error|panic!("vector={index}: {error}"));
            if let Some(reservation)=reply.reservation {reservation.frozen.validate_owned(&context.account_id).unwrap();}
        }
    }
}
