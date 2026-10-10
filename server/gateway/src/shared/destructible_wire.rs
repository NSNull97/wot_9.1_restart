//! Original #717 AreaDestructibles wire boundary for one laboratory object.
//!
//! P06N native-contract/contract01.json (SHA256 75bee50824733750d8d547c95daae275
//! a9b22dd6359a98405ac7d1d9d7be490d) pins the original definitions, bytecode and
//! native consumers. Four variable client properties preserve declaration order.
//! Dynamic properties use VAR1; each ARRAY has its own signed32LE element count.
//! Client type3 is the client-script index, not entities.xml ordinal6.
//!
//! The caller admits the source-verified native object index and commits world
//! and physics state before publishing. This encoder does not decide damage or
//! mutate client state. Actual P06N native reception remains a separate gate.
use std::io;

pub(super) const ENTITY_ID: u32 = 0x0910_0007;
pub(super) const ALIAS: u8 = 2;
pub(super) const CHUNK_ID: u16 = 31354;
pub(super) const POSITION: [f32; 3] = [-450., 0., -450.];
const CLIENT_TYPE: u16 = 3;
const DESTROYED_FRAGILES: u8 = 0x9f;

/// Native enterAoI. The caller must complete request/create/reliable-ACK state
/// before sending property updates to this connection.
pub(super) fn announcement() -> Vec<u8> {
    let mut out = vec![0x0a];
    out.extend(ENTITY_ID.to_le_bytes());
    out.push(ALIAS);
    out
}

/// Recognize one exact native requestEntityUpdate record. False is not an
/// authorization decision: the caller's normal bounded parser must handle or
/// reject other/malformed/combined records. Split piggybacked requests first.
pub(super) fn is_request(payload: &[u8]) -> bool {
    payload.len() == 7
        && payload[..3] == [8, 4, 0]
        && payload[3..] == ENTITY_ID.to_le_bytes()
}

fn fragile(index: u8) -> u16 {
    // Original DestructiblesCache.encodeFragile: (destrID << 8) | shotDamage.
    // This card publishes projectile destruction, hence isShotDamage=1.
    (u16::from(index) << 8) | 1
}

/// Full native initial state for a fresh controller/rejoin. Option limits the
/// state to one configured object; duplicate/multiple entries are not expressible.
/// Original onEnterWorld applies these arrays without a transient break effect.
/// A resource-defined decayEffect may still be present in the original client.
pub(super) fn create(destroyed: Option<u8>) -> io::Result<Vec<u8>> {
    let mut body = vec![0]; // original compression mode0
    body.extend(ENTITY_ID.to_le_bytes());
    body.extend(CLIENT_TYPE.to_le_bytes());
    for value in POSITION { body.extend(value.to_le_bytes()); }
    for _ in 0..3 { body.extend(0f32.to_le_bytes()); }
    body.push(4); // count of indexed client properties, not ARRAY length
    for index in 0..4u8 {
        body.push(index);
        if index == 1 {
            body.extend(i32::from(destroyed.is_some()).to_le_bytes());
            if let Some(native_index) = destroyed {
                body.extend(fragile(native_index).to_le_bytes());
            }
        } else {
            // destroyedModules/fallenColumns are ARRAY<UINT16>;
            // fallenTrees is ARRAY<UINT32>. Empty arrays have the same count.
            body.extend(0i32.to_le_bytes());
        }
    }
    if !matches!(body.len(), 52 | 54) {
        return Err(io::Error::new(io::ErrorKind::InvalidData,
            "invalid bounded AreaDestructibles creation length"));
    }
    let mut out = vec![9];
    out.extend((body.len() as u16).to_le_bytes()); // createEntityDetailed VAR2
    out.extend(body);
    Ok(out)
}

/// Full one-entry replacement, never an ARRAY append/slice operation. Repeated
/// delivery has the same packed state; original set_destroyedFragiles uses set
/// difference and does not replay an identical entry's transient break effect.
pub(super) fn update(index: u8) -> Vec<u8> {
    let mut out = vec![0x12];
    out.extend(ENTITY_ID.to_le_bytes());
    out.extend([DESTROYED_FRAGILES, 6]); // VAR1: i32 count + one u16
    out.extend(1i32.to_le_bytes());
    out.extend(fragile(index).to_le_bytes());
    out.push(0x13); // restore selected Avatar
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_initial_creation_has_all_four_empty_properties() {
        let golden = [
            9,52,0, 0, 7,0,16,9, 3,0,
            0,0,225,195, 0,0,0,0, 0,0,225,195,
            0,0,0,0, 0,0,0,0, 0,0,0,0,
            4, 0,0,0,0,0, 1,0,0,0,0, 2,0,0,0,0, 3,0,0,0,0,
        ];
        assert_eq!(create(None).unwrap(), golden);
        // Original chunkIDFromPosition uses floor(x*.01), not truncation.
        let x = (POSITION[0] as f64 * 0.01).floor() as i32;
        let z = (POSITION[2] as f64 * 0.01).floor() as i32;
        assert_eq!(((x+127)<<8 | (z+127)) as u16, CHUNK_ID);
    }

    #[test]
    fn rejoin_and_live_update_use_original_fragile_bit_layout() {
        for index in [0u8, 1, 127, 255] {
            let created = create(Some(index)).unwrap();
            assert_eq!(&created[..10], &[9,54,0,0,7,0,16,9,3,0]);
            assert_eq!(&created[34..], &[
                4, 0,0,0,0,0, 1,1,0,0,0,1,index,
                2,0,0,0,0, 3,0,0,0,0,
            ]);
            assert_eq!(update(index), [
                18,7,0,16,9, 159,6, 1,0,0,0, 1,index, 19,
            ]);
            // Both goldens contain a complete one-entry replacement. Option<u8>
            // prevents duplicate members from being supplied to initial state.
        }
    }

    #[test]
    fn area_request_cannot_alias_a_vehicle_or_accept_trailing_records() {
        let valid = [8,4,0,7,0,16,9];
        assert_eq!(announcement(), [10,7,0,16,9,2]);
        assert!(is_request(&valid));
        for end in 0..valid.len() { assert!(!is_request(&valid[..end])); }
        let mut combined = valid.to_vec();
        combined.extend(valid);
        assert!(!is_request(&combined));
        for at in 0..valid.len() {
            let mut changed = valid;
            changed[at] ^= 1;
            assert!(!is_request(&changed));
        }
        for id in [0x0910_0003u32, 0x0910_0005] {
            let mut other = valid;
            other[3..].copy_from_slice(&id.to_le_bytes());
            assert!(!is_request(&other));
        }
    }
}
