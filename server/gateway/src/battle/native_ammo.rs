//! Candidate native Avatar ammo updates for the pinned #717 MS-1 profile.
//!
//! The method id and fixed argument widths are VERIFIED_STATIC from the
//! original `avatar.def` registration table.  The MS-1 tuple is a bounded
//! candidates derived from the accepted server-owned loadout; native battle
//! receipt and the live value of `quantityInClip` remain NOT_RUN.

use std::io;

use super::loadout::BattleLoadout;

pub const ENTITY_METHOD_PREFIX: u8 = 0x13;
pub const UPDATE_VEHICLE_AMMO: u8 = 0x44;
pub const UPDATE_VEHICLE_SETTING: u8 = 0x40;
pub const UPDATE_VEHICLE_GUN_RELOAD_TIME: u8 = 0x46;
pub const CURRENT_SHELLS: u8 = 0;
pub const MS1_RELOAD_SECONDS: f32 = 2.5;
pub const ARGUMENT_BYTES: usize = 9;
pub const BODY_BYTES: usize = 2 + ARGUMENT_BYTES;
pub const MS1_INVENTORY_ID: u32 = 1;
pub const MS1_TURRET: u32 = 5891;
pub const MS1_GUN: u32 = 5892;
pub const MS1_SHELL: u32 = 2570;
pub const MS1_HEAT_SHELL: u32 = 2826;
pub const MS1_HE_SHELL: u32 = 3082;
pub const MS1_SHELL_ID: &str = "shell:ms1-stock-ap";
pub const MS1_SHELL_COUNT: u16 = 20;
pub const MS1_HEAT_COUNT: u16 = 0;
pub const MS1_HE_COUNT: u16 = 0;
pub const PANEL_UPDATES: usize = 3;
pub const PANEL_BODY_BYTES: usize = BODY_BYTES * PANEL_UPDATES;
pub const SELECTED_SHELL_BODY_BYTES: usize = 2 + 1 + 4;
pub const INITIAL_RELOAD_BODY_BYTES: usize = 2 + 4 + 4 + 4;
pub const BATTLE_SUFFIX_BYTES: usize = PANEL_BODY_BYTES + SELECTED_SHELL_BODY_BYTES + INITIAL_RELOAD_BODY_BYTES;

/// The order is pinned by the native MS-1 export and the closed GUI
/// `as_setAmmoS` callback: AP, hollow charge, high explosive.  The profile
/// owns only the AP stack; the other two rows are present with zero quantity
/// so the native battle panel can render their real shell types.
pub const MS1_PANEL_ROWS: [(u32, u16); PANEL_UPDATES] = [
    (MS1_SHELL, MS1_SHELL_COUNT),
    (MS1_HEAT_SHELL, MS1_HEAT_COUNT),
    (MS1_HE_SHELL, MS1_HE_COUNT),
];

// A single-shot MS-1 has no observed cassette/clip update in the closed
// hangar capture.  Keep this explicit candidate zero visible until an Avatar
// battle callback proves the native server value.
pub const CANDIDATE_QUANTITY_IN_CLIP: u8 = 0;
pub const CANDIDATE_TIME_REMAINING: i16 = 0;

fn invalid(reason: &'static str) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, reason)
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct NativeAmmoUpdate {
    pub compact_descr: i32,
    pub quantity: u16,
    pub quantity_in_clip: u8,
    pub time_remaining: i16,
}

impl NativeAmmoUpdate {
    /// Build the only currently supported candidate from authenticated domain
    /// data.  No client-provided value reaches this constructor.
    pub fn from_ms1_loadout(loadout: &BattleLoadout) -> io::Result<Self> {
        if loadout.native_inventory_id != MS1_INVENTORY_ID
            || loadout.turret_compact_descr != MS1_TURRET
            || loadout.gun_compact_descr != MS1_GUN
            || loadout.selected_shell_definition_id != MS1_SHELL_ID
            || loadout.selected_shell_compact_descr != MS1_SHELL
            || loadout.selected_shell_count != MS1_SHELL_COUNT
            || loadout.total_shell_count != MS1_SHELL_COUNT
        {
            return Err(invalid("native ammo candidate is not the pinned MS-1 loadout"));
        }
        Ok(Self {
            compact_descr: i32::try_from(MS1_SHELL)
                .map_err(|_| invalid("native shell compact descriptor overflow"))?,
            quantity: MS1_SHELL_COUNT,
            quantity_in_clip: CANDIDATE_QUANTITY_IN_CLIP,
            time_remaining: CANDIDATE_TIME_REMAINING,
        })
    }

    fn panel_row(compact_descr: u32, quantity: u16) -> io::Result<Self> {
        if !MS1_PANEL_ROWS.iter().any(|row| *row == (compact_descr, quantity)) {
            return Err(invalid("native ammo panel row is outside the pinned MS-1 export"));
        }
        Ok(Self {
            compact_descr: i32::try_from(compact_descr)
                .map_err(|_| invalid("native shell compact descriptor overflow"))?,
            quantity,
            quantity_in_clip: CANDIDATE_QUANTITY_IN_CLIP,
            time_remaining: CANDIDATE_TIME_REMAINING,
        })
    }

    /// Build the complete bounded MS-1 battle panel in native export order.
    /// No client-provided shell descriptor or quantity reaches this function.
    pub fn panel_from_ms1_loadout(loadout: &BattleLoadout) -> io::Result<[Self; PANEL_UPDATES]> {
        let selected = Self::from_ms1_loadout(loadout)?;
        Ok([
            selected,
            Self::panel_row(MS1_HEAT_SHELL, MS1_HEAT_COUNT)?,
            Self::panel_row(MS1_HE_SHELL, MS1_HE_COUNT)?,
        ])
    }

    fn encode(&self, avatar_entity_id: u32) -> io::Result<Vec<u8>> {
        if avatar_entity_id != crate::arena_control091::AVATAR_ENTITY_ID
            || self.compact_descr <= 0
            || self.quantity_in_clip != CANDIDATE_QUANTITY_IN_CLIP
            || self.time_remaining != CANDIDATE_TIME_REMAINING
        {
            return Err(invalid("native ammo row is outside the pinned bounds"));
        }
        let mut body = Vec::with_capacity(BODY_BYTES);
        body.extend([ENTITY_METHOD_PREFIX, UPDATE_VEHICLE_AMMO]);
        body.extend(self.compact_descr.to_le_bytes());
        body.extend(self.quantity.to_le_bytes());
        body.push(self.quantity_in_clip);
        body.extend(self.time_remaining.to_le_bytes());
        if body.len() != BODY_BYTES {
            return Err(invalid("native ammo body size"));
        }
        Ok(body)
    }

    /// Encode `Avatar.updateVehicleAmmo` as a fixed-size selected-entity
    /// method.  The caller cannot supply arbitrary framing or extra bytes.
    pub fn body(&self, avatar_entity_id: u32) -> io::Result<Vec<u8>> {
        if avatar_entity_id != crate::arena_control091::AVATAR_ENTITY_ID
            || self.compact_descr != MS1_SHELL as i32
            || self.quantity != MS1_SHELL_COUNT
            || self.quantity_in_clip != CANDIDATE_QUANTITY_IN_CLIP
            || self.time_remaining != CANDIDATE_TIME_REMAINING
        {
            return Err(invalid("native ammo candidate is outside the pinned bounds"));
        }
        self.encode(avatar_entity_id)
    }

    /// Encode one row from the fixed MS-1 panel.  This deliberately accepts
    /// only the three descriptors/counts in `MS1_PANEL_ROWS`.
    pub fn panel_body(&self, avatar_entity_id: u32) -> io::Result<Vec<u8>> {
        let compact_descr = u32::try_from(self.compact_descr)
            .map_err(|_| invalid("native shell compact descriptor"))?;
        if !MS1_PANEL_ROWS.iter().any(|row| *row == (compact_descr, self.quantity)) {
            return Err(invalid("native ammo panel row is outside the pinned bounds"));
        }
        self.encode(avatar_entity_id)
    }

    pub fn event_fields(&self) -> String {
        format!(
            "native_method=0x{UPDATE_VEHICLE_AMMO:02x} entity_method_prefix=0x{ENTITY_METHOD_PREFIX:02x} compact_descr={} quantity={} quantity_in_clip={} time_remaining={} body_bytes={} native_static=true native_delivery_candidate=true native_receipt=NOT_RUN",
            self.compact_descr,
            self.quantity,
            self.quantity_in_clip,
            self.time_remaining,
            BODY_BYTES,
        )
    }
}

pub fn candidate_body(loadout: &BattleLoadout, avatar_entity_id: u32) -> io::Result<Vec<u8>> {
    NativeAmmoUpdate::from_ms1_loadout(loadout)?.body(avatar_entity_id)
}

/// Encode all three native shell rows in one bounded suffix.  The caller
/// appends this suffix to the already measured binding/preparation body before
/// the reliable enqueue, so the rows cannot be delivered independently.
pub fn panel_bodies(loadout: &BattleLoadout, avatar_entity_id: u32) -> io::Result<Vec<u8>> {
    let updates = NativeAmmoUpdate::panel_from_ms1_loadout(loadout)?;
    let mut body = Vec::with_capacity(PANEL_BODY_BYTES);
    for update in updates {
        body.extend(update.panel_body(avatar_entity_id)?);
    }
    if body.len() != PANEL_BODY_BYTES {
        return Err(invalid("native ammo panel body size"));
    }
    Ok(body)
}

/// Set the initial current shell after the three ammo rows exist on the
/// client.  `PlayerAvatar.shoot` refuses to call `vehicle_shoot` while its
/// current-shell index is `None`; the native setting callback is the exact
/// server→client path that fills that index from the compact descriptor.
pub fn selected_shell_body(loadout: &BattleLoadout, avatar_entity_id: u32) -> io::Result<Vec<u8>> {
    if avatar_entity_id != crate::arena_control091::AVATAR_ENTITY_ID {
        return Err(invalid("native selected-shell entity"));
    }
    let selected = NativeAmmoUpdate::from_ms1_loadout(loadout)?;
    let mut body = Vec::with_capacity(SELECTED_SHELL_BODY_BYTES);
    body.extend([ENTITY_METHOD_PREFIX, UPDATE_VEHICLE_SETTING, CURRENT_SHELLS]);
    body.extend(selected.compact_descr.to_le_bytes());
    if body.len() != SELECTED_SHELL_BODY_BYTES {
        return Err(invalid("native selected-shell body size"));
    }
    Ok(body)
}

/// Clear the client's initial gun-reloading latch before the owner can fire.
///
/// `PlayerAvatar.updateVehicleGunReloadTime` ignores the callback unless its
/// first argument is the player's vehicle entity id.  A zero `timeLeft` is
/// converted by the verified client code to the non-reloading sentinel while
/// `baseTime` keeps the pinned MS-1 single-shot duration available to the HUD.
pub fn initial_reload_body(loadout: &BattleLoadout, avatar_entity_id: u32) -> io::Result<Vec<u8>> {
    if avatar_entity_id != crate::arena_control091::AVATAR_ENTITY_ID
        || NativeAmmoUpdate::from_ms1_loadout(loadout)?.compact_descr != MS1_SHELL as i32
    {
        return Err(invalid("native initial reload is outside the pinned MS-1 bounds"));
    }
    let mut body = Vec::with_capacity(INITIAL_RELOAD_BODY_BYTES);
    body.extend([ENTITY_METHOD_PREFIX, UPDATE_VEHICLE_GUN_RELOAD_TIME]);
    body.extend(crate::arena_vehicle091::VEHICLE_ENTITY_ID.to_le_bytes());
    body.extend(0.0f32.to_le_bytes());
    body.extend(MS1_RELOAD_SECONDS.to_le_bytes());
    if body.len() != INITIAL_RELOAD_BODY_BYTES {
        return Err(invalid("native initial reload body size"));
    }
    Ok(body)
}

pub fn panel_event_fields(loadout: &BattleLoadout) -> io::Result<String> {
    let updates = NativeAmmoUpdate::panel_from_ms1_loadout(loadout)?;
    let rows = updates
        .iter()
        .map(|update| format!("{}:{}", update.compact_descr, update.quantity))
        .collect::<Vec<_>>()
        .join(",");
    Ok(format!(
        "native_method=0x{UPDATE_VEHICLE_AMMO:02x} entity_method_prefix=0x{ENTITY_METHOD_PREFIX:02x} panel_count={PANEL_UPDATES} panel_rows={rows} panel_body_bytes={PANEL_BODY_BYTES} body_bytes_each={BODY_BYTES} quantity_in_clip=0 time_remaining=0 native_static=true native_delivery_candidate=true native_receipt=NOT_RUN"
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn loadout() -> BattleLoadout {
        BattleLoadout {
            account_id: "account".to_owned(),
            vehicle_inventory_id: "vehicle".to_owned(),
            native_inventory_id: MS1_INVENTORY_ID,
            turret_compact_descr: MS1_TURRET,
            gun_compact_descr: MS1_GUN,
            selected_shell_definition_id: MS1_SHELL_ID.to_owned(),
            selected_shell_compact_descr: MS1_SHELL,
            selected_shell_count: MS1_SHELL_COUNT,
            total_shell_count: MS1_SHELL_COUNT,
        }
    }

    #[test]
    fn exact_ms1_candidate_body_is_fixed_little_endian_11_bytes() {
        let body = candidate_body(&loadout(), crate::arena_control091::AVATAR_ENTITY_ID).unwrap();
        assert_eq!(body, vec![0x13, 0x44, 0x0a, 0x0a, 0, 0, 20, 0, 0, 0, 0]);
        assert_eq!(body.len(), BODY_BYTES);
    }

    #[test]
    fn selected_ms1_shell_body_sets_current_shell_by_compact_descriptor() {
        let body = selected_shell_body(&loadout(), crate::arena_control091::AVATAR_ENTITY_ID).unwrap();
        assert_eq!(body, vec![0x13, 0x40, 0, 0x0a, 0x0a, 0, 0]);
        assert_eq!(body.len(), SELECTED_SHELL_BODY_BYTES);
        assert!(selected_shell_body(&loadout(), crate::arena_control091::AVATAR_ENTITY_ID + 1).is_err());
    }

    #[test]
    fn initial_reload_body_clears_client_reload_latch_with_ms1_base_time() {
        let body = initial_reload_body(&loadout(), crate::arena_control091::AVATAR_ENTITY_ID).unwrap();
        assert_eq!(body, vec![
            0x13, 0x46, 0x03, 0x00, 0x10, 0x09,
            0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x20, 0x40,
        ]);
        assert_eq!(body.len(), INITIAL_RELOAD_BODY_BYTES);
        assert!(initial_reload_body(&loadout(), crate::arena_control091::AVATAR_ENTITY_ID + 1).is_err());
    }

    #[test]
    fn complete_ms1_panel_is_fixed_order_and_size() {
        let body = panel_bodies(&loadout(), crate::arena_control091::AVATAR_ENTITY_ID).unwrap();
        assert_eq!(body.len(), PANEL_BODY_BYTES);
        assert_eq!(
            body,
            vec![
                0x13, 0x44, 0x0a, 0x0a, 0, 0, 20, 0, 0, 0, 0,
                0x13, 0x44, 0x0a, 0x0b, 0, 0, 0, 0, 0, 0, 0,
                0x13, 0x44, 0x0a, 0x0c, 0, 0, 0, 0, 0, 0, 0,
            ]
        );
        let fields = panel_event_fields(&loadout()).unwrap();
        assert!(fields.contains("panel_count=3"));
        assert!(fields.contains("panel_rows=2570:20,2826:0,3082:0"));
    }

    #[test]
    fn wrong_domain_values_and_entity_are_rejected() {
        let mut value = loadout();
        for change in 0..8 {
            value = loadout();
            match change {
                0 => value.native_inventory_id = 2,
                1 => value.turret_compact_descr = 1,
                2 => value.gun_compact_descr = 1,
                3 => value.selected_shell_definition_id = "shell:other".to_owned(),
                4 => value.selected_shell_compact_descr = 1,
                5 => value.selected_shell_count = 19,
                6 => value.total_shell_count = 21,
                7 => value.total_shell_count = 0,
                _ => unreachable!(),
            }
            assert!(NativeAmmoUpdate::from_ms1_loadout(&value).is_err(), "mutation {change}");
        }
        assert!(candidate_body(&loadout(), crate::arena_control091::AVATAR_ENTITY_ID + 1).is_err());
    }

    #[test]
    fn candidate_mutation_is_rejected_before_encoding() {
        let update = NativeAmmoUpdate::from_ms1_loadout(&loadout()).unwrap();
        for change in [
            NativeAmmoUpdate { compact_descr: 1, ..update },
            NativeAmmoUpdate { quantity: 19, ..update },
            NativeAmmoUpdate { quantity_in_clip: 1, ..update },
            NativeAmmoUpdate { time_remaining: 1, ..update },
        ] {
            assert!(change.body(crate::arena_control091::AVATAR_ENTITY_ID).is_err());
        }
        let outside = NativeAmmoUpdate { compact_descr: 9999, quantity: 0, quantity_in_clip: 0, time_remaining: 0 };
        assert!(outside.panel_body(crate::arena_control091::AVATAR_ENTITY_ID).is_err());
    }

    #[test]
    fn event_keeps_native_receipt_explicitly_unrun() {
        let event = NativeAmmoUpdate::from_ms1_loadout(&loadout()).unwrap().event_fields();
        assert!(event.contains("native_method=0x44"));
        assert!(event.contains("native_receipt=NOT_RUN"));
        assert!(event.contains("quantity_in_clip=0"));
    }
}
