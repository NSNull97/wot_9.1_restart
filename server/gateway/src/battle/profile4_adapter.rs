//! Bind the trusted `game.account.v1` assertion to the accepted profile4 MS-1
//! loadout.  This is a domain adapter only: it emits no native bytes, does not
//! reserve or consume ammunition, and is not a battle admission decision.

use std::fmt;

use serde_json::{Map, Value};
use sha2::{Digest, Sha256};

use super::loadout::{validate, AmmoMapping, AuthenticatedVehicleProfile, BattleLoadout, LoadoutError, ShellStack};

const MAX_OWNERSHIP_BYTES: usize = 4096;
const MAX_SOURCE_BYTES: usize = 8192;
const PROFILE_SHA256: &str = "2610dbd9ee64a12852986def336da057326f14a3289dda43eaae616286998d2d";
const COMPATIBILITY_SHA256: &str = "825a7e7024993c83b132499fe6f383b233ac288049bb77ca94b5407430f8d4d3";
const NATIVE_AMMO_SHA256: &str = "683daac81143a9d7edfbe671870ba163db088c54f5101fa52e077f596ebbfc74";
const POLICY: &str = "test_lab.profile4-ms1.v1";
const ACCOUNT_CONTRACT: &str = "identity.account.v1";

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct LoadoutSelection {
    pub vehicle_inventory_id: String,
    pub shell_definition_id: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BoundBattleLoadout {
    pub account_id: String,
    pub native_database_id: u32,
    pub profile_version: u32,
    pub snapshot_revision: u32,
    pub profile_sha256: String,
    pub policy: String,
    pub crew_count: u8,
    pub loadout: BattleLoadout,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum AdapterError {
    InputTooLarge(&'static str),
    InvalidJson(&'static str),
    ContractMismatch(&'static str),
    PolicyMismatch(&'static str),
    Loadout(LoadoutError),
}

impl fmt::Display for AdapterError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InputTooLarge(name) => write!(f, "{name} input exceeds bounded size"),
            Self::InvalidJson(name) => write!(f, "{name} input is not valid JSON"),
            Self::ContractMismatch(name) => write!(f, "{name} contract mismatch"),
            Self::PolicyMismatch(name) => write!(f, "{name} policy mismatch"),
            Self::Loadout(error) => write!(f, "loadout validation failed: {error}"),
        }
    }
}

impl From<LoadoutError> for AdapterError {
    fn from(error: LoadoutError) -> Self { Self::Loadout(error) }
}

fn digest(bytes: &[u8]) -> String {
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("{:x}", hasher.finalize())
}

fn bounded<'a>(bytes: &'a [u8], name: &'static str, maximum: usize) -> Result<&'a [u8], AdapterError> {
    if bytes.is_empty() || bytes.len() > maximum { return Err(AdapterError::InputTooLarge(name)); }
    Ok(bytes)
}

fn parse(bytes: &[u8], name: &'static str) -> Result<Value, AdapterError> {
    serde_json::from_slice(bytes).map_err(|_| AdapterError::InvalidJson(name))
}

fn object<'a>(value: &'a Value, name: &'static str) -> Result<&'a Map<String, Value>, AdapterError> {
    value.as_object().ok_or(AdapterError::ContractMismatch(name))
}

fn array<'a>(value: &'a Value, name: &'static str) -> Result<&'a Vec<Value>, AdapterError> {
    value.as_array().ok_or(AdapterError::ContractMismatch(name))
}

fn field<'a>(value: &'a Map<String, Value>, key: &str, name: &'static str) -> Result<&'a Value, AdapterError> {
    value.get(key).ok_or(AdapterError::ContractMismatch(name))
}

fn string<'a>(value: &'a Map<String, Value>, key: &str, name: &'static str) -> Result<&'a str, AdapterError> {
    field(value, key, name)?.as_str().ok_or(AdapterError::ContractMismatch(name))
}

fn number(value: &Map<String, Value>, key: &str, name: &'static str) -> Result<u64, AdapterError> {
    field(value, key, name)?.as_u64().ok_or(AdapterError::ContractMismatch(name))
}

fn keys_are(value: &Map<String, Value>, expected: &[&str]) -> bool {
    value.len() == expected.len() && expected.iter().all(|key| value.contains_key(*key))
}

fn exact_u32(value: &Map<String, Value>, key: &str, expected: u32, name: &'static str) -> Result<(), AdapterError> {
    if number(value, key, name)? != u64::from(expected) { return Err(AdapterError::PolicyMismatch(name)); }
    Ok(())
}

fn parse_ownership(bytes: &[u8]) -> Result<Map<String, Value>, AdapterError> {
    let parsed = parse(bounded(bytes, "ownership", MAX_OWNERSHIP_BYTES)?, "ownership")?;
    let root = object(&parsed, "ownership")?;
    if !keys_are(root, &["contract", "operation", "ok", "data"])
        || root.get("contract").and_then(Value::as_str) != Some("game.account.v1")
        || root.get("operation").and_then(Value::as_str) != Some("ownership/assert")
        || root.get("ok").and_then(Value::as_bool) != Some(true) {
        return Err(AdapterError::ContractMismatch("ownership envelope"));
    }
    let data = object(field(root, "data", "ownership data")?, "ownership data")?;
    if !keys_are(data, &["account_id", "native_database_id", "nickname", "created_at", "profile_version", "snapshot_revision", "profile_sha256", "ruleset", "identity_contract", "ownership_source"])
        || string(data, "identity_contract", "ownership data")? != ACCOUNT_CONTRACT
        || string(data, "ownership_source", "ownership data")? != "game-account-owner"
        || string(data, "ruleset", "ownership data")? != "test_lab" {
        return Err(AdapterError::ContractMismatch("ownership data"));
    }
    Ok(data.clone())
}

fn inventory_row<'a>(profile: &'a Map<String, Value>, definition: &str) -> Result<&'a Map<String, Value>, AdapterError> {
    let rows = array(field(profile, "inventory", "profile inventory")?, "profile inventory")?;
    let found: Vec<&Map<String, Value>> = rows.iter().filter_map(Value::as_object)
        .filter(|row| row.get("vehicle_definition_id").and_then(Value::as_str) == Some(definition)).collect();
    if found.len() != 1 { return Err(AdapterError::PolicyMismatch("profile inventory")); }
    Ok(found[0])
}

fn mapping_row<'a>(compatibility: &'a Map<String, Value>, shell: &str) -> Result<&'a Map<String, Value>, AdapterError> {
    let rows = array(field(compatibility, "ammo_mapping", "ammo mapping")?, "ammo mapping")?;
    let found: Vec<&Map<String, Value>> = rows.iter().filter_map(Value::as_object)
        .filter(|row| row.get("shell_definition_id").and_then(Value::as_str) == Some(shell)).collect();
    if found.len() != 1 { return Err(AdapterError::PolicyMismatch("ammo mapping")); }
    Ok(found[0])
}

/// Validate trusted server-owned inputs and bind them to the existing domain gate.
/// The input bytes are expected to have crossed an already authenticated service
/// boundary; their SHA/policy checks are integrity and revision guards, not a
/// network signature. No reservation, consumption, expiry, or battle admission
/// is created by this function.
pub fn validate_authenticated(
    ownership_bytes: &[u8],
    profile_bytes: &[u8],
    compatibility_bytes: &[u8],
    native_ammo_bytes: &[u8],
    selection: &LoadoutSelection,
) -> Result<BoundBattleLoadout, AdapterError> {
    bounded(profile_bytes, "profile", MAX_SOURCE_BYTES)?;
    bounded(compatibility_bytes, "compatibility", MAX_SOURCE_BYTES)?;
    bounded(native_ammo_bytes, "native ammo", MAX_SOURCE_BYTES)?;
    let profile_sha = digest(profile_bytes);
    if profile_sha != PROFILE_SHA256 { return Err(AdapterError::PolicyMismatch("profile sha256")); }
    if digest(compatibility_bytes) != COMPATIBILITY_SHA256 { return Err(AdapterError::PolicyMismatch("compatibility sha256")); }
    if digest(native_ammo_bytes) != NATIVE_AMMO_SHA256 { return Err(AdapterError::PolicyMismatch("native ammo sha256")); }

    let ownership = parse_ownership(ownership_bytes)?;
    let parsed_profile = parse(profile_bytes, "profile")?;
    let parsed_compatibility = parse(compatibility_bytes, "compatibility")?;
    let parsed_native = parse(native_ammo_bytes, "native ammo")?;
    let profile = object(&parsed_profile, "profile")?;
    let compatibility = object(&parsed_compatibility, "compatibility")?;
    let native_root = object(&parsed_native, "native ammo")?;
    if number(native_root, "version", "native ammo")? != 1 || string(native_root, "kind", "native ammo")? != "native-ms1-ammo" {
        return Err(AdapterError::PolicyMismatch("native ammo schema"));
    }
    let native = object(field(native_root, "data", "native ammo data")?, "native ammo data")?;
    exact_u32(native, "max_ammo", 96, "native max ammo")?;
    exact_u32(native, "vehicle_inventory_id", 1, "native vehicle inventory")?;
    exact_u32(native, "vehicle_type_compact_descr", 3329, "native vehicle type")?;
    let turret = object(field(native, "turret", "native turret")?, "native turret")?;
    let gun = object(field(native, "gun", "native gun")?, "native gun")?;
    exact_u32(turret, "compact_descr", 5891, "native turret")?;
    exact_u32(gun, "compact_descr", 5892, "native gun")?;
    let native_shells = array(field(native, "shells", "native shells")?, "native shells")?;
    let has_ap = native_shells.iter().filter_map(Value::as_object).any(|row|
        row.get("compact_descr").and_then(Value::as_u64) == Some(2570)
            && row.get("compatible_with_mounted_gun").and_then(Value::as_bool) == Some(true));
    if !has_ap { return Err(AdapterError::PolicyMismatch("native AP shell")); }

    if string(&ownership, "profile_sha256", "ownership data")? != profile_sha
        || string(&ownership, "account_id", "ownership data")? != string(profile, "account_id", "profile")?
        || string(&ownership, "nickname", "ownership data")? != string(profile, "username", "profile")?
        || number(&ownership, "created_at", "ownership data")? != number(profile, "created_at_ms", "profile")?
        || number(&ownership, "native_database_id", "ownership data")? != number(profile, "native_database_id", "profile")?
        || number(&ownership, "profile_version", "ownership data")? != 4
        || number(&ownership, "snapshot_revision", "ownership data")? != 4 {
        return Err(AdapterError::PolicyMismatch("ownership/profile binding"));
    }
    if number(profile, "profile_version", "profile")? != 4 || number(profile, "snapshot_revision", "profile")? != 4
        || string(profile, "account_id", "profile")? != string(compatibility, "account_id", "compatibility")?
        || number(profile, "native_database_id", "profile")? != number(compatibility, "native_database_id", "compatibility")?
        || number(compatibility, "snapshot_revision", "compatibility")? != 4
        || number(compatibility, "compatibility_catalog_revision", "compatibility")? != 3
        || number(compatibility, "wire_sync_revision", "compatibility")? != 1 {
        return Err(AdapterError::PolicyMismatch("profile revision"));
    }

    let profile_inventory = inventory_row(profile, "vehicle:ms1")?;
    let vehicle_inventory_id = string(profile_inventory, "inventory_id", "MS-1 inventory")?;
    if vehicle_inventory_id != selection.vehicle_inventory_id
        || string(profile_inventory, "vehicle_definition_id", "MS-1 inventory")? != "vehicle:ms1"
        || profile_inventory.get("crew_assigned").and_then(Value::as_bool) != Some(true)
        || number(profile_inventory, "ammunition_count", "MS-1 inventory")? != 20 {
        return Err(AdapterError::PolicyMismatch("MS-1 inventory"));
    }
    let ammunition = array(field(profile, "ammunition", "profile ammunition")?, "profile ammunition")?;
    if ammunition.len() != 1 { return Err(AdapterError::PolicyMismatch("profile ammunition")); }
    let ammo_row = object(&ammunition[0], "profile ammunition")?;
    if string(ammo_row, "vehicle_inventory_id", "profile ammunition")? != vehicle_inventory_id
        || string(ammo_row, "shell_definition_id", "profile ammunition")? != selection.shell_definition_id
        || string(ammo_row, "shell_definition_id", "profile ammunition")? != "shell:ms1-stock-ap"
        || number(ammo_row, "count", "profile ammunition")? != 20 {
        return Err(AdapterError::PolicyMismatch("selected ammunition"));
    }
    let crew = array(field(profile, "crew", "profile crew")?, "profile crew")?;
    if crew.len() != 2 || crew.iter().any(|row| row.as_object().and_then(|o| o.get("vehicle_inventory_id")).and_then(Value::as_str) != Some(vehicle_inventory_id)) {
        return Err(AdapterError::PolicyMismatch("profile crew"));
    }
    let roles: Vec<&str> = crew.iter().filter_map(|row| row.as_object()).filter_map(|row| row.get("role")).filter_map(Value::as_str).collect();
    if roles.len() != 2 || !roles.contains(&"commander") || !roles.contains(&"driver") { return Err(AdapterError::PolicyMismatch("profile crew roles")); }

    let mapping = mapping_row(compatibility, &selection.shell_definition_id)?;
    if string(mapping, "vehicle_inventory_id", "ammo mapping")? != vehicle_inventory_id
        || number(mapping, "native_vehicle_inventory_id", "ammo mapping")? != 1
        || number(mapping, "native_turret_compact_descr", "ammo mapping")? != 5891
        || number(mapping, "native_gun_compact_descr", "ammo mapping")? != 5892
        || number(mapping, "native_shell_compact_descr", "ammo mapping")? != 2570 {
        return Err(AdapterError::PolicyMismatch("ammo mapping values"));
    }
    let profile_input = AuthenticatedVehicleProfile {
        authenticated: true,
        account_id: string(profile, "account_id", "profile")?.to_owned(),
        vehicle_inventory_id: vehicle_inventory_id.to_owned(),
        vehicle_definition_id: "vehicle:ms1".to_owned(),
        native_inventory_id: 1,
        turret_compact_descr: 5891,
        gun_compact_descr: 5892,
        max_ammo: 96,
        shells: vec![ShellStack { shell_definition_id: selection.shell_definition_id.clone(), native_shell_compact_descr: 2570, count: 20 }],
    };
    let ammo_mapping = AmmoMapping {
        shell_definition_id: selection.shell_definition_id.clone(),
        vehicle_inventory_id: vehicle_inventory_id.to_owned(),
        native_vehicle_inventory_id: 1,
        native_turret_compact_descr: 5891,
        native_gun_compact_descr: 5892,
        native_shell_compact_descr: 2570,
    };
    let loadout = validate(&profile_input, &[ammo_mapping], &selection.shell_definition_id)?;
    Ok(BoundBattleLoadout {
        account_id: profile_input.account_id,
        native_database_id: 1,
        profile_version: 4,
        snapshot_revision: 4,
        profile_sha256: profile_sha,
        policy: POLICY.to_owned(),
        crew_count: crew.len() as u8,
        loadout,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::path::Path;

    fn fixture() -> (Vec<u8>, Vec<u8>, Vec<u8>, Vec<u8>, LoadoutSelection) {
        let roots = [
            Path::new("local/evidence/20261006-profile4-chain/portable-bundle-05/content"),
            Path::new("../../local/evidence/20261006-profile4-chain/portable-bundle-05/content"),
        ];
        let root = roots.iter().find(|path| path.is_dir()).expect("portable fixture root");
        let read = |path: &str| fs::read(root.join(path)).expect("portable fixture");
        let profile = read("fixtures/profile4/profile-input.json.blob");
        let compatibility = read("fixtures/profile4/compatibility.json.blob");
        let native = read("inputs/native-ms1-ammo.blob");
        let value: Value = serde_json::from_slice(&profile).unwrap();
        let account = value["account_id"].as_str().unwrap();
        let assertion_paths = [
            Path::new("local/evidence/20261006-battle-loadout-revision-gate/ownership-assertion.json"),
            Path::new("../../local/evidence/20261006-battle-loadout-revision-gate/ownership-assertion.json"),
        ];
        let ownership = assertion_paths.iter().find(|path| path.is_file()).map(|path| fs::read(path).unwrap()).unwrap_or_else(|| {
            let mut identity = Map::new();
            identity.insert("contract".into(), Value::String("game.account.v1".into()));
            identity.insert("operation".into(), Value::String("ownership/assert".into()));
            identity.insert("ok".into(), Value::Bool(true));
            let mut data = Map::new();
            data.insert("account_id".into(), Value::String(account.into()));
            data.insert("native_database_id".into(), Value::Number(1.into()));
            data.insert("nickname".into(), Value::String(value["username"].as_str().unwrap().into()));
            data.insert("created_at".into(), value["created_at_ms"].clone());
            data.insert("profile_version".into(), Value::Number(4.into()));
            data.insert("snapshot_revision".into(), Value::Number(4.into()));
            data.insert("profile_sha256".into(), Value::String(PROFILE_SHA256.into()));
            data.insert("ruleset".into(), Value::String("test_lab".into()));
            data.insert("identity_contract".into(), Value::String(ACCOUNT_CONTRACT.into()));
            data.insert("ownership_source".into(), Value::String("game-account-owner".into()));
            identity.insert("data".into(), Value::Object(data));
            serde_json::to_vec(&Value::Object(identity)).unwrap()
        });
        (ownership, profile, compatibility, native, LoadoutSelection {
            vehicle_inventory_id: format!("{account}:starter-vehicle-v1"), shell_definition_id: "shell:ms1-stock-ap".into(),
        })
    }

    #[test]
    fn accepted_profile4_is_bound_to_domain_loadout() {
        let (ownership, profile, compatibility, native, selection) = fixture();
        assert_eq!(digest(&profile), PROFILE_SHA256);
        let result = validate_authenticated(&ownership, &profile, &compatibility, &native, &selection).unwrap();
        assert_eq!(result.profile_version, 4);
        assert_eq!(result.snapshot_revision, 4);
        assert_eq!(result.crew_count, 2);
        assert_eq!(result.loadout.selected_shell_compact_descr, 2570);
        assert_eq!(result.loadout.selected_shell_count, 20);
    }

    #[test]
    fn stale_assertion_and_foreign_selection_fail_closed() {
        let (mut ownership, profile, compatibility, native, mut selection) = fixture();
        let mut value: Value = serde_json::from_slice(&ownership).unwrap();
        value["data"]["snapshot_revision"] = Value::Number(3.into());
        ownership = serde_json::to_vec(&value).unwrap();
        assert!(matches!(validate_authenticated(&ownership, &profile, &compatibility, &native, &selection), Err(AdapterError::PolicyMismatch("ownership/profile binding"))));
        let (ownership, profile, compatibility, native, _) = fixture();
        selection.vehicle_inventory_id = "c5326cc1-8524-479c-8bba-72e973489c22:test-is7-v1".into();
        assert!(validate_authenticated(&ownership, &profile, &compatibility, &native, &selection).is_err());
    }

    #[test]
    fn profile_bytes_are_bound_by_exact_digest() {
        let (ownership, mut profile, compatibility, native, selection) = fixture();
        profile[0] = b' ';
        assert!(matches!(validate_authenticated(&ownership, &profile, &compatibility, &native, &selection), Err(AdapterError::PolicyMismatch("profile sha256"))));
    }

    #[test]
    fn malformed_ownership_and_oversized_sources_fail_before_domain_validation() {
        let (mut ownership, profile, compatibility, native, selection) = fixture();
        ownership = br#"{"contract":"game.account.v1","operation":"ownership/assert","ok":true,"data":{}}"#.to_vec();
        assert!(matches!(validate_authenticated(&ownership, &profile, &compatibility, &native, &selection), Err(AdapterError::ContractMismatch("ownership data"))));
        let oversized = vec![b'0'; MAX_SOURCE_BYTES + 1];
        let (ownership, profile, compatibility, native, selection) = fixture();
        assert!(matches!(validate_authenticated(&ownership, &oversized, &compatibility, &native, &selection), Err(AdapterError::InputTooLarge("profile"))));
    }

    #[test]
    fn compatibility_and_native_export_hashes_are_pinned() {
        let (ownership, profile, mut compatibility, native, selection) = fixture();
        compatibility[0] = b' ';
        assert!(matches!(validate_authenticated(&ownership, &profile, &compatibility, &native, &selection), Err(AdapterError::PolicyMismatch("compatibility sha256"))));
        let (ownership, profile, compatibility, mut native, selection) = fixture();
        native[0] = b' ';
        assert!(matches!(validate_authenticated(&ownership, &profile, &compatibility, &native, &selection), Err(AdapterError::PolicyMismatch("native ammo sha256"))));
    }
}
