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
// Measured in both identity02 native clients: filename, matrix and five rays.
pub(super) const NATIVE_INDEX: u8 = 1;
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

/// Catalog-order area controllers. Native chunk coordinates use floor(x/100).
/// The catalog supplies only original, independently verified item identities.
pub(super) fn area_id(area:usize)->io::Result<u32>{
    if area>=super::fragiles::MAX_OBJECTS{return Err(super::model::bad());}Ok(ENTITY_ID+area as u32)
}
pub(super) fn area_announcement(area:usize)->io::Result<Vec<u8>>{
    let mut out=vec![10];out.extend(area_id(area)?.to_le_bytes());out.push(ALIAS+area as u8);Ok(out)
}
pub(super) fn area_request(payload:&[u8],count:usize)->Option<usize>{
    if count>super::fragiles::MAX_OBJECTS||payload.len()!=7||payload[..3]!=[8,4,0]{return None;}
    let id=u32::from_le_bytes(payload[3..].try_into().ok()?);
    let area=id.checked_sub(ENTITY_ID)? as usize;(area<count).then_some(area)
}
fn checked_indices(indices:&[u8])->io::Result<()>{
    // Only verified short VAR1 bodies: do not guess the extended length codec.
    if indices.len()>super::fragiles::MAX_OBJECTS||indices.windows(2).any(|w|w[0]>=w[1]){return Err(super::model::bad());}Ok(())
}
pub(super) fn area_create(area:usize,chunk:u16,indices:&[u8])->io::Result<Vec<u8>>{
    checked_indices(indices)?;let mut body=vec![0];body.extend(area_id(area)?.to_le_bytes());body.extend(CLIENT_TYPE.to_le_bytes());
    for v in [((chunk>>8) as i32-127) as f32*100.+50.,0.,((chunk&255) as i32-127) as f32*100.+50.]{body.extend(v.to_le_bytes());}
    body.extend([0u8;12]);body.push(4);
    for prop in 0..4u8{body.push(prop);if prop==1{body.extend((indices.len() as i32).to_le_bytes());for &id in indices{body.extend(fragile(id).to_le_bytes());}}
        else{body.extend(0i32.to_le_bytes());}}
    let mut out=vec![9];out.extend((body.len() as u16).to_le_bytes());out.extend(body);Ok(out)
}
pub(super) fn area_update(area:usize,indices:&[u8])->io::Result<Vec<u8>>{
    checked_indices(indices)?;let mut out=vec![0x12];out.extend(area_id(area)?.to_le_bytes());
    out.extend([DESTROYED_FRAGILES,(4+2*indices.len()) as u8]);out.extend((indices.len() as i32).to_le_bytes());
    for &id in indices{out.extend(fragile(id).to_le_bytes());}out.push(0x13);Ok(out)
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

    #[test]fn catalog_arrays_use_complete_cumulative_state_and_original_fragile_packing(){
        assert_eq!(area_create(0,CHUNK_ID,&[]).unwrap(),create(None).unwrap());
        assert_eq!(area_create(0,CHUNK_ID,&[1]).unwrap(),create(Some(1)).unwrap());
        assert_eq!(area_update(0,&[1]).unwrap(),update(1));
        let indices=[0,1,255];let packet=area_update(2,&indices).unwrap();
        assert_eq!(&packet[..7],&[18,9,0,16,9,159,10]);
        assert_eq!(&packet[7..],&[3,0,0,0,1,0,1,1,1,255,19]);
        let creation=area_create(2,33667,&indices).unwrap();assert_eq!(&creation[3..10],&[0,9,0,16,9,3,0]);
        assert_eq!(f32::from_le_bytes(creation[10..14].try_into().unwrap()),450.);
        assert_eq!(f32::from_le_bytes(creation[18..22].try_into().unwrap()),450.);
        assert_eq!(&creation[45..51],&[1,0,1,1,1,255]);
        assert_eq!(area_update(2,&indices).unwrap(),packet);
    }
    #[test]fn catalog_wire_refuses_overflow_alias_duplicate_or_unsorted_arrays(){
        let full=(0..64u8).collect::<Vec<_>>();assert_eq!(area_update(63,&full).unwrap()[6],132);
        for ids in [vec![1,1],vec![2,0],(0..65u8).collect()]{assert!(area_update(0,&ids).is_err());assert!(area_create(0,CHUNK_ID,&ids).is_err());}
        assert!(area_create(64,CHUNK_ID,&[]).is_err());assert!(area_announcement(64).is_err());
        let mut request=vec![8,4,0];request.extend(area_id(63).unwrap().to_le_bytes());
        assert_eq!(area_request(&request,64),Some(63));assert_eq!(area_request(&request,63),None);
        request.push(0);assert_eq!(area_request(&request,64),None);
    }

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
