//! Domain-only battle loadout gate.
//!
//! This module validates the server-owned relationship between an authenticated
//! vehicle profile, its mounted turret/gun, and a selected shell stack. It does
//! not serialize a native packet, draw a HUD, mutate a fixture, or accept client
//! coordinates. Native Avatar loadout delivery remains a separate capture task.

use std::fmt;

const MAX_ID_BYTES: usize = 192;
const MAX_SHELL_STACKS: usize = 16;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AuthenticatedVehicleProfile {
    pub authenticated: bool,
    pub account_id: String,
    pub vehicle_inventory_id: String,
    pub vehicle_definition_id: String,
    pub native_inventory_id: u32,
    pub turret_compact_descr: u32,
    pub gun_compact_descr: u32,
    pub max_ammo: u16,
    pub shells: Vec<ShellStack>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct ShellStack {
    pub shell_definition_id: String,
    pub native_shell_compact_descr: u32,
    pub count: u16,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct AmmoMapping {
    pub shell_definition_id: String,
    pub vehicle_inventory_id: String,
    pub native_vehicle_inventory_id: u32,
    pub native_turret_compact_descr: u32,
    pub native_gun_compact_descr: u32,
    pub native_shell_compact_descr: u32,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BattleLoadout {
    pub account_id: String,
    pub vehicle_inventory_id: String,
    pub native_inventory_id: u32,
    pub turret_compact_descr: u32,
    pub gun_compact_descr: u32,
    pub selected_shell_definition_id: String,
    pub selected_shell_compact_descr: u32,
    pub selected_shell_count: u16,
    pub total_shell_count: u16,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum LoadoutError {
    EmptyField(&'static str),
    FieldTooLong(&'static str),
    InvalidNativeId(&'static str),
    InvalidAmmoCapacity,
    NoShells,
    TooManyShells,
    DuplicateShell(String),
    DuplicateMapping(String),
    ShellCountExceedsCapacity,
    MappingMissing(String),
    MappingMismatch(&'static str),
    SelectedShellUnavailable(String),
}

impl fmt::Display for LoadoutError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::EmptyField(name) => write!(f, "{name} is empty"),
            Self::FieldTooLong(name) => write!(f, "{name} exceeds bounded length"),
            Self::InvalidNativeId(name) => write!(f, "{name} is invalid"),
            Self::InvalidAmmoCapacity => write!(f, "ammo capacity is invalid"),
            Self::NoShells => write!(f, "no shell stacks are present"),
            Self::TooManyShells => write!(f, "too many shell stacks"),
            Self::DuplicateShell(id) => write!(f, "duplicate shell stack {id}"),
            Self::DuplicateMapping(id) => write!(f, "duplicate shell mapping {id}"),
            Self::ShellCountExceedsCapacity => write!(f, "shell count exceeds vehicle capacity"),
            Self::MappingMissing(id) => write!(f, "mapping for {id} is missing"),
            Self::MappingMismatch(name) => write!(f, "mapping mismatch: {name}"),
            Self::SelectedShellUnavailable(id) => write!(f, "selected shell {id} is unavailable"),
        }
    }
}

fn bounded_id(name: &'static str, value: &str) -> Result<(), LoadoutError> {
    if value.is_empty() {
        return Err(LoadoutError::EmptyField(name));
    }
    if value.len() > MAX_ID_BYTES || value.bytes().any(|byte| byte == 0 || byte < 0x20) {
        return Err(LoadoutError::FieldTooLong(name));
    }
    Ok(())
}

/// Validate a server-owned loadout and return a typed domain value.
///
/// `selected_shell_definition_id` is a domain choice, not a client-supplied
/// packet. Any missing or inconsistent relationship fails closed.
pub fn validate(
    profile: &AuthenticatedVehicleProfile,
    mappings: &[AmmoMapping],
    selected_shell_definition_id: &str,
) -> Result<BattleLoadout, LoadoutError> {
    if !profile.authenticated {
        return Err(LoadoutError::EmptyField("authenticated_profile"));
    }
    bounded_id("account_id", &profile.account_id)?;
    bounded_id("vehicle_inventory_id", &profile.vehicle_inventory_id)?;
    bounded_id("vehicle_definition_id", &profile.vehicle_definition_id)?;
    bounded_id("selected_shell_definition_id", selected_shell_definition_id)?;
    if profile.native_inventory_id == 0 {
        return Err(LoadoutError::InvalidNativeId("native_inventory_id"));
    }
    if profile.turret_compact_descr == 0 {
        return Err(LoadoutError::InvalidNativeId("turret_compact_descr"));
    }
    if profile.gun_compact_descr == 0 {
        return Err(LoadoutError::InvalidNativeId("gun_compact_descr"));
    }
    if profile.max_ammo == 0 {
        return Err(LoadoutError::InvalidAmmoCapacity);
    }
    if profile.shells.is_empty() {
        return Err(LoadoutError::NoShells);
    }
    if profile.shells.len() > MAX_SHELL_STACKS {
        return Err(LoadoutError::TooManyShells);
    }

    let mut total_shell_count: u32 = 0;
    let mut selected: Option<&ShellStack> = None;
    for shell in &profile.shells {
        bounded_id("shell_definition_id", &shell.shell_definition_id)?;
        if shell.native_shell_compact_descr == 0 {
            return Err(LoadoutError::InvalidNativeId("native_shell_compact_descr"));
        }
        if profile.shells.iter().filter(|row| row.shell_definition_id == shell.shell_definition_id).count() != 1 {
            return Err(LoadoutError::DuplicateShell(shell.shell_definition_id.clone()));
        }
        total_shell_count = total_shell_count
            .checked_add(shell.count as u32)
            .ok_or(LoadoutError::ShellCountExceedsCapacity)?;
        if shell.shell_definition_id == selected_shell_definition_id {
            selected = Some(shell);
        }
    }
    if total_shell_count == 0 || total_shell_count > profile.max_ammo as u32 {
        return Err(LoadoutError::ShellCountExceedsCapacity);
    }
    let selected = selected.ok_or_else(|| LoadoutError::SelectedShellUnavailable(selected_shell_definition_id.to_owned()))?;
    if selected.count == 0 {
        return Err(LoadoutError::SelectedShellUnavailable(selected_shell_definition_id.to_owned()));
    }

    let matching_mappings: Vec<&AmmoMapping> = mappings
        .iter()
        .filter(|row| row.shell_definition_id == selected.shell_definition_id)
        .collect();
    if matching_mappings.is_empty() {
        return Err(LoadoutError::MappingMissing(selected.shell_definition_id.clone()));
    }
    if matching_mappings.len() != 1 {
        return Err(LoadoutError::DuplicateMapping(selected.shell_definition_id.clone()));
    }
    let mapping = matching_mappings[0];
    if mapping.vehicle_inventory_id != profile.vehicle_inventory_id {
        return Err(LoadoutError::MappingMismatch("vehicle_inventory_id"));
    }
    if mapping.native_vehicle_inventory_id != profile.native_inventory_id {
        return Err(LoadoutError::MappingMismatch("native_vehicle_inventory_id"));
    }
    if mapping.native_turret_compact_descr != profile.turret_compact_descr {
        return Err(LoadoutError::MappingMismatch("native_turret_compact_descr"));
    }
    if mapping.native_gun_compact_descr != profile.gun_compact_descr {
        return Err(LoadoutError::MappingMismatch("native_gun_compact_descr"));
    }
    if mapping.native_shell_compact_descr != selected.native_shell_compact_descr {
        return Err(LoadoutError::MappingMismatch("native_shell_compact_descr"));
    }

    Ok(BattleLoadout {
        account_id: profile.account_id.clone(),
        vehicle_inventory_id: profile.vehicle_inventory_id.clone(),
        native_inventory_id: profile.native_inventory_id,
        turret_compact_descr: profile.turret_compact_descr,
        gun_compact_descr: profile.gun_compact_descr,
        selected_shell_definition_id: selected.shell_definition_id.clone(),
        selected_shell_compact_descr: selected.native_shell_compact_descr,
        selected_shell_count: selected.count,
        total_shell_count: total_shell_count as u16,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn profile() -> AuthenticatedVehicleProfile {
        AuthenticatedVehicleProfile {
            authenticated: true,
            account_id: "c5326cc1-8524-479c-8bba-72e973489c22".to_owned(),
            vehicle_inventory_id: "c5326cc1-8524-479c-8bba-72e973489c22:starter-vehicle-v1".to_owned(),
            vehicle_definition_id: "vehicle:ms1".to_owned(),
            native_inventory_id: 1,
            turret_compact_descr: 5891,
            gun_compact_descr: 5892,
            max_ammo: 96,
            shells: vec![ShellStack {
                shell_definition_id: "shell:ms1-stock-ap".to_owned(),
                native_shell_compact_descr: 2570,
                count: 20,
            }],
        }
    }

    fn mapping() -> AmmoMapping {
        AmmoMapping {
            shell_definition_id: "shell:ms1-stock-ap".to_owned(),
            vehicle_inventory_id: "c5326cc1-8524-479c-8bba-72e973489c22:starter-vehicle-v1".to_owned(),
            native_vehicle_inventory_id: 1,
            native_turret_compact_descr: 5891,
            native_gun_compact_descr: 5892,
            native_shell_compact_descr: 2570,
        }
    }

    #[test]
    fn valid_authenticated_ms1_loadout_passes_without_wire_bytes() {
        let loadout = validate(&profile(), &[mapping()], "shell:ms1-stock-ap").unwrap();
        assert_eq!(loadout.selected_shell_compact_descr, 2570);
        assert_eq!(loadout.selected_shell_count, 20);
        assert_eq!(loadout.total_shell_count, 20);
    }

    #[test]
    fn missing_shell_fails_closed() {
        let mut value = profile();
        value.shells.clear();
        assert_eq!(validate(&value, &[mapping()], "shell:ms1-stock-ap"), Err(LoadoutError::NoShells));
    }

    #[test]
    fn zero_selected_count_fails_closed() {
        let mut value = profile();
        value.shells[0].count = 0;
        assert!(matches!(validate(&value, &[mapping()], "shell:ms1-stock-ap"), Err(LoadoutError::ShellCountExceedsCapacity)));
    }

    #[test]
    fn selected_shell_without_mapping_fails_closed() {
        assert!(matches!(validate(&profile(), &[], "shell:ms1-stock-ap"), Err(LoadoutError::MappingMissing(_))));
    }

    #[test]
    fn mapping_vehicle_or_module_mismatch_fails_closed() {
        let mut wrong_vehicle = mapping();
        wrong_vehicle.vehicle_inventory_id = "other-vehicle".to_owned();
        assert!(matches!(validate(&profile(), &[wrong_vehicle], "shell:ms1-stock-ap"), Err(LoadoutError::MappingMismatch("vehicle_inventory_id"))));
        let mut wrong_gun = mapping();
        wrong_gun.native_gun_compact_descr = 7169;
        assert!(matches!(validate(&profile(), &[wrong_gun], "shell:ms1-stock-ap"), Err(LoadoutError::MappingMismatch("native_gun_compact_descr"))));
    }

    #[test]
    fn duplicate_shell_definition_fails_closed() {
        let mut value = profile();
        value.shells.push(value.shells[0].clone());
        assert!(matches!(validate(&value, &[mapping()], "shell:ms1-stock-ap"), Err(LoadoutError::DuplicateShell(_))));
    }

    #[test]
    fn shell_count_over_capacity_fails_closed() {
        let mut value = profile();
        value.shells[0].count = 97;
        assert_eq!(validate(&value, &[mapping()], "shell:ms1-stock-ap"), Err(LoadoutError::ShellCountExceedsCapacity));
    }

    #[test]
    fn invalid_identity_and_native_ids_fail_closed() {
        let mut value = profile();
        value.account_id.clear();
        assert!(matches!(validate(&value, &[mapping()], "shell:ms1-stock-ap"), Err(LoadoutError::EmptyField("account_id"))));
        let mut value = profile();
        value.gun_compact_descr = 0;
        assert_eq!(validate(&value, &[mapping()], "shell:ms1-stock-ap"), Err(LoadoutError::InvalidNativeId("gun_compact_descr")));
    }

    #[test]
    fn unauthenticated_profile_fails_closed() {
        let mut value = profile();
        value.authenticated = false;
        assert_eq!(validate(&value, &[mapping()], "shell:ms1-stock-ap"), Err(LoadoutError::EmptyField("authenticated_profile")));
    }

    #[test]
    fn excessive_shell_stack_count_fails_closed() {
        let mut value = profile();
        for index in 0..MAX_SHELL_STACKS {
            value.shells.push(ShellStack {
                shell_definition_id: format!("shell:extra-{index}"),
                native_shell_compact_descr: 3000 + index as u32,
                count: 1,
            });
        }
        assert_eq!(validate(&value, &[mapping()], "shell:ms1-stock-ap"), Err(LoadoutError::TooManyShells));
    }

    #[test]
    fn duplicate_shell_mapping_fails_closed() {
        let duplicate = mapping();
        assert_eq!(validate(&profile(), &[mapping(), duplicate], "shell:ms1-stock-ap"), Err(LoadoutError::DuplicateMapping("shell:ms1-stock-ap".to_owned())));
    }
}
