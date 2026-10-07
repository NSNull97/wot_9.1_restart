//! Narrow outgoing arena checkpoint for the pinned native 0.9.1 #717 client.
//!
//! STATIC contracts: original EXE SHA256
//! 86f5e351d44c12e0d2b89ed741ee9a4e70d21f234c39aa9cfd709536d49f04ed,
//! original entity_defs, and local/evidence/20261005-p02-arena-entry/wire.
//! These encoders are NOT a claim of native arena acceptance. In particular,
//! createBasePlayer immediately invokes original onBecomePlayer; it is not a
//! constructor-only checkpoint. Vehicle creation/readiness is a separate gate.
//!
//! No sockets, incoming object decoding, arbitrary PYTHON, or mutable fixtures.
//! Return values are application message bodies for the existing reliable
//! channel. The caller owns authentication, one-shot authorization, and ordering.

use std::io::{Error, ErrorKind, Result};

pub const AVATAR_CLIENT_TYPE: u16 = 1;
pub const KARELIA_ARENA_TYPE: i32 = 1;
pub const KARELIA_GEOMETRY: &str = "spaces/01_karelia";
pub const MAX_CHECKPOINT_BODY: usize = 256;

/// Values owned by the authenticated session, never values supplied by a client.
#[derive(Clone, Debug)]
pub struct AvatarBaseSeed<'a> {
    pub entity_id: u32,
    pub name: &'a str,
    pub arena_unique_id: u64,
}

/// One own player in one space. This is a server-selected placement, not physics.
#[derive(Clone, Debug)]
pub struct AvatarCellSeed {
    pub space_id: u32,
    pub player_vehicle_id: u32,
    pub position: [f32; 3],
}

fn invalid(message: &'static str) -> Error {
    Error::new(ErrorKind::InvalidInput, message)
}

fn positive_id(value: u32) -> Result<()> {
    if value == 0 || value > i32::MAX as u32 {
        return Err(invalid("arena checkpoint requires a positive signed32 ID"));
    }
    Ok(())
}

fn nickname(value: &str) -> Result<()> {
    // Same narrow nickname alphabet as the authenticated local identity bridge.
    // All accepted scalars fit in at most 48 UTF8 bytes; no extended STRING.
    if !(3..=24).contains(&value.chars().count())
        || value.len() > 48
        || !value.chars().all(|c| {
            c.is_ascii_alphanumeric() || c == '_' || ('\u{0410}'..='\u{044f}').contains(&c)
                || c == '\u{0401}' || c == '\u{0451}'
        })
    {
        return Err(invalid("arena checkpoint nickname is outside the local identity contract"));
    }
    Ok(())
}

fn variable16(id: u8, payload: &[u8]) -> Result<Vec<u8>> {
    if payload.len() + 3 > MAX_CHECKPOINT_BODY {
        return Err(invalid("arena checkpoint application message exceeds bound"));
    }
    let mut out = Vec::with_capacity(payload.len() + 3);
    out.push(id);
    out.extend_from_slice(&(payload.len() as u16).to_le_bytes());
    out.extend_from_slice(payload);
    Ok(out)
}

/// Exact #717 resetEntities(false), FIXED1 (registration 0x1684890).
/// Native 0xd6d8d0 -> EntityManager 0x5c8d90 clears the old native player;
/// Player::onBecomeNonPlayer is original code. This does not disconnect/login.
pub fn reset_entities() -> [u8; 2] {
    [0x04, 0]
}

/// createBasePlayer VAR2: entityID:u32, clientType:u16, then nine base values.
/// #717 0xd6da50/0x5c7b40, sequential reader mask0x0b at0x5bfc40.
/// Avatar client type1 follows original client-script presence indexing; it is
/// not an arbitrary position chosen from a modern entity table.
pub fn create_base_avatar(seed: &AvatarBaseSeed<'_>) -> Result<Vec<u8>> {
    positive_id(seed.entity_id)?;
    nickname(seed.name)?;
    if seed.arena_unique_id == 0 {
        return Err(invalid("arena unique ID must be nonzero"));
    }
    let mut payload = Vec::with_capacity(80);
    payload.extend_from_slice(&seed.entity_id.to_le_bytes());
    payload.extend_from_slice(&AVATAR_CLIENT_TYPE.to_le_bytes());
    payload.push(seed.name.len() as u8);
    payload.extend_from_slice(seed.name.as_bytes()); // name STRING
    payload.extend_from_slice(&seed.arena_unique_id.to_le_bytes()); // UINT64
    payload.extend_from_slice(&KARELIA_ARENA_TYPE.to_le_bytes()); // arenaTypeID INT32
    payload.extend_from_slice(&[2, 2]); // TRAINING bonus/gui, original constants
    // Own empty arenaExtraData PYTHON: protocol2 EMPTY_DICT STOP, no object code.
    payload.extend_from_slice(&[4, 0x80, 2, b'}', b'.']);
    payload.push(0); // weatherPresetID: sole default preset in original map1
    payload.extend_from_slice(&0i16.to_le_bytes()); // no denunciations granted
    payload.push(0); // clientCtx empty STRING; original default context branch
    variable16(0x05, &payload)
}

/// Atomic application body for the first checkpoint; the reliable channel
/// determines retransmission and packet sequencing. No cell data is appended to
/// the base-property stream. Any native callback exception is a failed probe.
pub fn reset_to_avatar_base(seed: &AvatarBaseSeed<'_>) -> Result<Vec<u8>> {
    let base = create_base_avatar(seed)?;
    let mut out = Vec::with_capacity(base.len() + 2);
    out.extend_from_slice(&reset_entities());
    out.extend_from_slice(&base);
    if out.len() > MAX_CHECKPOINT_BODY {
        return Err(invalid("arena checkpoint bundle exceeds bound"));
    }
    Ok(out)
}

/// createCellPlayer VAR2. Native 0xd6da90 reads a 36-byte prefix: spaceID,
/// attachment vehicleID, position, packed-XZ scale, direction. No modern flag
/// or u16 is present. Own cell mask0x0e then reads four declared properties.
pub fn create_cell_avatar(seed: &AvatarCellSeed) -> Result<Vec<u8>> {
    positive_id(seed.space_id)?;
    positive_id(seed.player_vehicle_id)?;
    if seed.position.iter().any(|v| !v.is_finite() || v.abs() > 4096.0) {
        return Err(invalid("arena checkpoint position must be finite and locally bounded"));
    }
    let mut payload = Vec::with_capacity(43);
    payload.extend_from_slice(&seed.space_id.to_le_bytes());
    payload.extend_from_slice(&0u32.to_le_bytes()); // unattached player coordinate frame
    for value in seed.position { payload.extend_from_slice(&value.to_le_bytes()); }
    payload.extend_from_slice(&1f32.to_le_bytes()); // explicit local packed-XZ scale
    for _ in 0..3 { payload.extend_from_slice(&0f32.to_le_bytes()); } // neutral direction
    payload.push(1); // own team UINT8
    payload.extend_from_slice(&seed.player_vehicle_id.to_le_bytes()); // OBJECT_ID
    payload.extend_from_slice(&[0, 0]); // unlocked; no physical ground contact asserted
    debug_assert_eq!(payload.len(), 43);
    variable16(0x06, &payload)
}

/// #717 spaceData VAR2: spaceID:u32, entryID:8 raw bytes, key:u16, raw data.
/// Key1 add-geometry path at0x5c9696/0xd13ba0 reads a 64-byte matrix followed
/// by the remaining path bytes (no second length or terminator). Only the one
/// exported original local map is allowed. Caller must use a fresh entry ID.
pub fn karelia_space_data(space_id: u32, entry_id: [u8; 8]) -> Result<Vec<u8>> {
    positive_id(space_id)?;
    if entry_id == [0; 8] {
        return Err(invalid("geometry entry ID must be nonzero"));
    }
    let mut payload = Vec::with_capacity(14 + 64 + KARELIA_GEOMETRY.len());
    payload.extend_from_slice(&space_id.to_le_bytes());
    payload.extend_from_slice(&entry_id);
    payload.extend_from_slice(&1u16.to_le_bytes());
    for row in 0..4 {
        for column in 0..4 {
            let value = if row == column { 1f32 } else { 0f32 };
            payload.extend_from_slice(&value.to_le_bytes());
        }
    }
    payload.extend_from_slice(KARELIA_GEOMETRY.as_bytes());
    variable16(0x07, &payload)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn base() -> AvatarBaseSeed<'static> {
        AvatarBaseSeed { entity_id: 0x09100002, name: "test_player", arena_unique_id: 1 }
    }
    fn cell() -> AvatarCellSeed {
        AvatarCellSeed { space_id: 1, player_vehicle_id: 0x09100003, position: [0.0, 10.0, 0.0] }
    }
    #[test]
    fn base_literal_order_and_no_modern_tail() {
        let actual = create_base_avatar(&base()).unwrap();
        let mut expected = vec![5, 41, 0, 2, 0, 16, 9, 1, 0, 11];
        expected.extend_from_slice(b"test_player");
        expected.extend_from_slice(&[1,0,0,0,0,0,0,0, 1,0,0,0, 2,2, 4,128,2,125,46, 0, 0,0, 0]);
        // This literal encodes the audited field layout, not a codec round trip.
        assert_eq!(actual, expected);
    }
    #[test]
    fn reset_and_base_are_distinct_complete_messages() {
        let seed = base();
        let body = reset_to_avatar_base(&seed).unwrap();
        assert_eq!(&body[..2], &[4,0]);
        assert_eq!(&body[2..], create_base_avatar(&seed).unwrap());
        assert_eq!(body.len(), 46);
    }
    #[test]
    fn maximum_cyrillic_name_uses_utf8_byte_length() {
        let name = "Ё".repeat(24);
        let seed = AvatarBaseSeed { name: &name, ..base() };
        let body = create_base_avatar(&seed).unwrap();
        assert_eq!(body[9], 48);
        assert_eq!(&body[10..58], name.as_bytes());
        assert!(reset_to_avatar_base(&seed).unwrap().len() < MAX_CHECKPOINT_BODY);
    }
    #[test]
    fn invalid_ids_names_and_unique_id_fail_before_emission() {
        for entity_id in [0, 0x80000000, u32::MAX] {
            assert!(reset_to_avatar_base(&AvatarBaseSeed { entity_id, ..base() }).is_err());
        }
        for name in ["", "ab", "a b", "a\0b", "a\nb", "a😀b", "е\u{0301}ж", "abcdefghijklmnopqrstuvwxy"] {
            assert!(reset_to_avatar_base(&AvatarBaseSeed { name, ..base() }).is_err());
        }
        assert!(reset_to_avatar_base(&AvatarBaseSeed { arena_unique_id: 0, ..base() }).is_err());
    }
    #[test]
    fn cell_has_exact_36_byte_header_and_seven_own_property_bytes() {
        let message = create_cell_avatar(&cell()).unwrap();
        assert_eq!(message.len(), 46);
        assert_eq!(&message[..11], &[6,43,0, 1,0,0,0, 0,0,0,0]);
        assert_eq!(&message[11..23], &[0,0,0,0, 0,0,32,65, 0,0,0,0]);
        assert_eq!(&message[23..27], &[0,0,128,63]);
        assert_eq!(&message[27..39], &[0;12]);
        assert_eq!(&message[39..], &[1, 3,0,16,9, 0,0]);
    }
    #[test]
    fn cell_rejects_nonfinite_and_outside_own_bounds() {
        for value in [f32::NAN, f32::INFINITY, f32::NEG_INFINITY, 4096.01, -4096.01] {
            for axis in 0..3 {
                let mut seed = cell(); seed.position[axis] = value;
                assert!(create_cell_avatar(&seed).is_err());
            }
        }
        for id in [0, 0x80000000, u32::MAX] {
            assert!(create_cell_avatar(&AvatarCellSeed { space_id: id, ..cell() }).is_err());
            assert!(create_cell_avatar(&AvatarCellSeed { player_vehicle_id: id, ..cell() }).is_err());
        }
    }
    #[test]
    fn geometry_uses_raw_14_byte_prefix_matrix_and_remaining_path() {
        let message = karelia_space_data(1, [1,2,3,4,5,6,7,8]).unwrap();
        assert_eq!(&message[..17], &[7,95,0, 1,0,0,0, 1,2,3,4,5,6,7,8, 1,0]);
        assert_eq!(message.len(), 98);
        for (index, chunk) in message[17..81].chunks_exact(4).enumerate() {
            let expected = if [0,5,10,15].contains(&index) { [0,0,128,63] } else { [0;4] };
            assert_eq!(chunk, expected);
        }
        assert_eq!(&message[81..], b"spaces/01_karelia");
        assert!(karelia_space_data(0, [1;8]).is_err());
        assert!(karelia_space_data(1, [0;8]).is_err());
    }
    #[test]
    fn bounded_internal_var16_rejects_before_length_truncation() {
        assert!(variable16(5, &[0;254]).is_err());
        assert!(variable16(5, &[0;253]).is_ok());
        let body = [reset_to_avatar_base(&base()).unwrap(), create_cell_avatar(&cell()).unwrap(),
            karelia_space_data(1, [1;8]).unwrap()].concat();
        assert!(body.len() <= MAX_CHECKPOINT_BODY);
    }
}
