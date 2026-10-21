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
/// MAPS-02: client property index2 (`158 + 2`). INFERRED from the PE-verified
/// property base and the natively observed neighbours 0x9f/0xa1.
const FALLEN_COLUMNS: u8 = 0xa0;
const FALLEN_TREES: u8 = 0xa1;
/// Prohorovka has 144 destructible chunks.  This is an area-controller
/// bound, separate from the 64-object fragile catalog bound.
pub(super) const MAX_AREAS: usize = 144;
/// A short VAR1 property length is one byte.  ARRAY<UINT32> carries a signed
/// i32 count, so 4 + 4*62 = 252 is the largest safe body before 255.
const MAX_TREES_PER_AREA: usize = 62;

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
    if area>=MAX_AREAS{return Err(super::model::bad());}Ok(ENTITY_ID+area as u32)
}
pub(super) fn area_announcement(area:usize)->io::Result<Vec<u8>>{
    let mut out=vec![10];out.extend(area_id(area)?.to_le_bytes());out.push(ALIAS+area as u8);Ok(out)
}
pub(super) fn area_request(payload:&[u8],count:usize)->Option<usize>{
    if count>MAX_AREAS||payload.len()!=7||payload[..3]!=[8,4,0]{return None;}
    let id=u32::from_le_bytes(payload[3..].try_into().ok()?);
    let area=id.checked_sub(ENTITY_ID)? as usize;(area<count).then_some(area)
}

fn checked_fragiles(fragiles:&[u16])->io::Result<()>{
    // DestructiblesCache.encodeFragile is (destrID << 8) | int(isShotDamage).
    // Keep both projectile (low bit 1) and vehicle (low bit 0) records, but
    // reject guessed bits and duplicate/out-of-order set members.
    // ARRAY<UINT16>: 4 + 2*125 = 254 bytes fits native short VAR1.
    if fragiles.len()>125
        || fragiles.windows(2).any(|w|w[0]>=w[1])
        || fragiles.iter().any(|value| value & 0xfe != 0) {
        return Err(super::model::bad());
    }
    Ok(())
}
fn checked_trees(trees:&[u32])->io::Result<()>{
    if trees.len()>MAX_TREES_PER_AREA||trees.windows(2).any(|w|w[0]>=w[1]){return Err(super::model::bad());}
    Ok(())
}
/// ARRAY<UINT16> in a short VAR1 property: 4 + 2*125 = 254 bytes.
pub(super) const MAX_COLUMNS_PER_AREA: usize = 125;
fn checked_columns(columns:&[u16])->io::Result<()>{
    // Every UINT16 is a valid encodeFallenColumn value; keep the set exact.
    if columns.len()>MAX_COLUMNS_PER_AREA||columns.windows(2).any(|w|w[0]>=w[1]){return Err(super::model::bad());}
    Ok(())
}
fn area_body(area:usize,chunk:u16,fragiles:&[u16],columns:&[u16],fallen_trees:&[u32])->io::Result<Vec<u8>>{
    checked_fragiles(fragiles)?;checked_columns(columns)?;checked_trees(fallen_trees)?;
    let mut body=vec![0];body.extend(area_id(area)?.to_le_bytes());body.extend(CLIENT_TYPE.to_le_bytes());
    for v in [((chunk>>8) as i32-127) as f32*100.+50.,0.,((chunk&255) as i32-127) as f32*100.+50.]{body.extend(v.to_le_bytes());}
    body.extend([0u8;12]);body.push(4);
    for prop in 0..4u8{body.push(prop);match prop {
        1=>{body.extend((fragiles.len() as i32).to_le_bytes());for &value in fragiles{body.extend(value.to_le_bytes());}},
        2=>{body.extend((columns.len() as i32).to_le_bytes());for &value in columns{body.extend(value.to_le_bytes());}},
        3=>{body.extend((fallen_trees.len() as i32).to_le_bytes());for &value in fallen_trees{body.extend(value.to_le_bytes());}},
        _=>body.extend(0i32.to_le_bytes()),
    }}
    if body.len()>u16::MAX as usize{return Err(super::model::bad());}
    Ok(body)
}

/// Full initial state for one native AreaDestructibles controller.  Fragile
/// entries are already DestructiblesCache.encodeFragile values; tree entries
/// are the original UINT32 encodeFallenTree values.
pub(super) fn area_create_state(area:usize,chunk:u16,fragiles:&[u16],fallen_trees:&[u32])->io::Result<Vec<u8>>{
    area_create_full(area,chunk,fragiles,&[],fallen_trees)
}
/// MAPS-02 full initial state including cumulative encodeFallenColumn values.
/// Original onEnterWorld restores columns without the fall animation.
pub(super) fn area_create_full(area:usize,chunk:u16,fragiles:&[u16],columns:&[u16],fallen_trees:&[u32])->io::Result<Vec<u8>>{
    let body=area_body(area,chunk,fragiles,columns,fallen_trees)?;
    let mut out=vec![9];out.extend((body.len() as u16).to_le_bytes());out.extend(body);Ok(out)
}

fn area_update_property(area:usize,property:u8,element_size:usize,count:usize)->io::Result<Vec<u8>>{
    let body_len=4usize.checked_add(element_size.checked_mul(count).ok_or_else(|| super::model::bad())?).ok_or_else(|| super::model::bad())?;
    if body_len>u8::MAX as usize{return Err(super::model::bad());}
    let mut out=vec![0x12];out.extend(area_id(area)?.to_le_bytes());out.extend([property,body_len as u8]);
    out.extend((count as i32).to_le_bytes());Ok(out)
}

pub(super) fn area_update_fragiles(area:usize,fragiles:&[u16])->io::Result<Vec<u8>>{
    checked_fragiles(fragiles)?;let mut out=area_update_property(area,DESTROYED_FRAGILES,2,fragiles.len())?;
    for &value in fragiles{out.extend(value.to_le_bytes());}out.push(0x13);Ok(out)
}

pub(super) fn area_update_trees(area:usize,fallen_trees:&[u32])->io::Result<Vec<u8>>{
    checked_trees(fallen_trees)?;let mut out=area_update_property(area,FALLEN_TREES,4,fallen_trees.len())?;
    for &value in fallen_trees{out.extend(value.to_le_bytes());}out.push(0x13);Ok(out)
}

/// Complete cumulative fallenColumns replacement; original set_fallenColumns
/// animates only the set difference against its previous value.
pub(super) fn area_update_columns(area:usize,columns:&[u16])->io::Result<Vec<u8>>{
    checked_columns(columns)?;let mut out=area_update_property(area,FALLEN_COLUMNS,2,columns.len())?;
    for &value in columns{out.extend(value.to_le_bytes());}out.push(0x13);Ok(out)
}

/// Match DestructiblesCache.encodeFallenColumn from the pinned Python 2.7
/// bytecode: `int(fallSpeed)` clamped to 0..3, then
/// `int(64*(yaw+PI)/PI_2) % 64`, packed `destrIndex<<8 | yaw<<2 | speed`.
/// The original does not mask destrIndex; u8 keeps it inside UINT16.
pub(super) fn encode_fallen_column<Y:Into<f64>,S:Into<f64>>(native_index:u8,yaw:Y,speed:S)->io::Result<u16>{
    let yaw=yaw.into();let speed=speed.into();
    if !yaw.is_finite()||!speed.is_finite(){return Err(super::model::bad());}
    let speed=speed.trunc();let speed=if speed<=0. {0} else if speed>=3. {3} else {speed as u16};
    let scaled=64. * (yaw+std::f64::consts::PI)/(2.*std::f64::consts::PI);
    if !scaled.is_finite(){return Err(super::model::bad());}
    let discrete_yaw=scaled.trunc().rem_euclid(64.) as u16;
    Ok((u16::from(native_index)<<8)|(discrete_yaw<<2)|speed)
}

pub(super) fn area_create(area:usize,chunk:u16,indices:&[u8])->io::Result<Vec<u8>>{
    let fragiles=indices.iter().map(|&index|fragile(index)).collect::<Vec<_>>();
    area_create_state(area,chunk,&fragiles,&[])
}
pub(super) fn area_update(area:usize,indices:&[u8])->io::Result<Vec<u8>>{
    let fragiles=indices.iter().map(|&index|fragile(index)).collect::<Vec<_>>();
    area_update_fragiles(area,&fragiles)
}

/// Match DestructiblesCache.encodeFallenTree from the pinned Python 2.7
/// bytecode.  Python's `int` truncates toward zero; yaw/pitch are deliberately
/// quantized with the original wrap masks, while non-finite input is rejected
/// instead of relying on Rust's float-to-int saturation behavior.
pub(super) fn encode_fallen_tree<Y:Into<f64>,P:Into<f64>,S:Into<f64>>(
    native_index:u8,yaw:Y,pitch:P,speed:S)->io::Result<u32>{
    let yaw=yaw.into();let pitch=pitch.into();let speed=speed.into();
    if !yaw.is_finite()||!pitch.is_finite()||!speed.is_finite(){return Err(super::model::bad());}
    let speed=if speed<=0. {0} else if speed>=3. {3} else {speed as u32};
    // `int` truncates toward zero before Python's integer bit mask.  Reducing
    // the finite float remainder before converting avoids Rust's saturating
    // float-to-int behavior for very large (but still finite) diagnostics.
    let yaw_scaled=64. * (yaw+std::f64::consts::PI)/(2.*std::f64::consts::PI);
    let pitch_scaled=65536. * (pitch+std::f64::consts::PI)/(2.*std::f64::consts::PI);
    if !yaw_scaled.is_finite()||!pitch_scaled.is_finite(){return Err(super::model::bad());}
    let discrete_yaw=yaw_scaled.trunc().rem_euclid(64.) as u32;
    let discrete_pitch=pitch_scaled.trunc().rem_euclid(65536.) as u32;
    Ok((u32::from(native_index)<<24)|(discrete_yaw<<18)|(speed<<16)|discrete_pitch)
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
        for ids in [vec![1,1],vec![2,0],(0..126u8).collect()]{assert!(area_update(0,&ids).is_err());assert!(area_create(0,CHUNK_ID,&ids).is_err());}
        assert!(area_create(144,CHUNK_ID,&[]).is_err());assert!(area_announcement(144).is_err());
        let mut request=vec![8,4,0];request.extend(area_id(143).unwrap().to_le_bytes());
        assert_eq!(area_request(&request,144),Some(143));assert_eq!(area_request(&request,143),None);
        request.push(0);assert_eq!(area_request(&request,64),None);
    }

    #[test]
    fn tree_state_uses_distinct_uint32_property_and_preserves_ramming_fragiles() {
        let fragiles = [0x0100u16, 0x0101]; // vehicle then projectile destruction
        let trees = [0x0102_0000u32, 0x0203_0001];
        let creation = area_create_state(143, CHUNK_ID, &fragiles, &trees).unwrap();
        // Property 1 is ARRAY<UINT16>; property 3 is ARRAY<UINT32>.  Both
        // arrays are cumulative and use signed little-endian element counts.
        assert!(creation.windows(6).any(|window| window == [1, 2, 0, 0, 0, 0]));
        assert!(creation.windows(13).any(|window| window == [3, 2, 0, 0, 0, 0, 0, 2, 1, 1, 0, 3, 2]));
        let update = area_update_trees(143, &trees).unwrap();
        assert_eq!(&update[..7], &[18, 0x96, 0, 16, 9, FALLEN_TREES, 12]);
        assert_eq!(&update[7..], &[2, 0, 0, 0, 0, 0, 2, 1, 1, 0, 3, 2, 19]);
        assert_eq!(area_update_fragiles(143, &fragiles).unwrap(), {
            let mut expected = vec![18, 0x96, 0, 16, 9, DESTROYED_FRAGILES, 8, 2, 0, 0, 0];
            expected.extend([0, 1, 1, 1, 19]); expected
        });
        assert!(area_update_trees(143, &(0..63u32).collect::<Vec<_>>()).is_err());
        assert!(area_create_state(143, CHUNK_ID, &[], &(0..63u32).collect::<Vec<_>>()).is_err());
        assert!(area_update_fragiles(143, &[0x0102]).is_err());
    }

    #[test]
    fn prohorovka_tree_update_preserves_known_native_packed_values() {
        // Values observed in manualtree02 for native indexes 25 and 4.
        // Cumulative State output is sorted, regardless of contact order.
        assert!(area_update_trees(0, &[0x195a_8000, 0x040e_8000]).is_err());
        let update = area_update_trees(0, &[0x040e_8000, 0x195a_8000]).unwrap();
        assert_eq!(&update[..7], &[0x12, 0x07, 0x00, 0x10, 0x09, FALLEN_TREES, 12]);
        assert_eq!(&update[7..], &[
            2, 0, 0, 0,
            0x00, 0x80, 0x0e, 0x04,
            0x00, 0x80, 0x5a, 0x19,
            0x13,
        ]);
    }

    #[test]
    fn cumulative_fences_fit_the_exact_native_short_property_bound() {
        let values=(0..125u16).map(|i|i<<8).collect::<Vec<_>>();
        let bytes=area_update_fragiles(118,&values).unwrap();
        assert_eq!(bytes[6],254);
        assert_eq!(&bytes[7..11],&125i32.to_le_bytes());
        for (i,word) in bytes[11..261].chunks_exact(2).enumerate() {
            assert_eq!(u16::from_le_bytes(word.try_into().unwrap()),(i as u16)<<8);
        }
        assert_eq!(bytes.last(),Some(&0x13));
        let mut overflow=values;overflow.push(125<<8);
        assert!(area_update_fragiles(118,&overflow).is_err());
        assert!(area_create_state(118,CHUNK_ID,&overflow,&[]).is_err());
    }

    #[test]
    fn encode_fallen_tree_matches_pinned_python_quantization_and_rejects_nonfinite() {
        assert_eq!(encode_fallen_tree(7, 0.0f64, 0.0f64, 2).unwrap(), 0x0782_8000);
        assert_eq!(encode_fallen_tree(255, std::f64::consts::PI / 2., -std::f64::consts::PI / 2., 99).unwrap(), 0xffc3_4000);
        assert_eq!(encode_fallen_tree(1, -std::f64::consts::PI, std::f64::consts::PI, 0).unwrap(), 0x0100_0000);
        assert_eq!(encode_fallen_tree(2, 3.2, -3.2, -4).unwrap(), 0x0200_fd9f);
        assert!(encode_fallen_tree(1, f64::NAN, 0., 0).is_err());
        assert!(encode_fallen_tree(1, 0., f64::INFINITY, 0).is_err());
        assert!(encode_fallen_tree(1, 0., 0., f64::NEG_INFINITY).is_err());
    }

    #[test]
    fn encode_fallen_column_matches_pinned_python_quantization() {
        // Hand-derived from destructiblescache.pyc encodeFallenColumn bytecode
        // (tests/test_destructible_wire_columns.py re-derives them independently).
        assert_eq!(encode_fallen_column(7, 0.0f64, 2).unwrap(), 0x0782);
        assert_eq!(encode_fallen_column(255, std::f64::consts::PI / 2., 99).unwrap(), 0xffc3);
        assert_eq!(encode_fallen_column(1, -std::f64::consts::PI, 0).unwrap(), 0x0100);
        assert_eq!(encode_fallen_column(2, 3.2, -4).unwrap(), 0x0200);
        assert_eq!(encode_fallen_column(3, -3.2, 2.9).unwrap(), 0x0302);
        assert_eq!(encode_fallen_column(4, -4.0, 1.5).unwrap(), 0x04e1);
        assert!(encode_fallen_column(1, f64::NAN, 0).is_err());
        assert!(encode_fallen_column(1, 0., f64::INFINITY).is_err());
        assert!(encode_fallen_column(1, f64::MAX, 0).is_err());
    }

    #[test]
    fn fallen_columns_use_property_two_and_0xa0_short_envelope() {
        let columns = [0x0102u16, 0x0782];
        let update = area_update_columns(1, &columns).unwrap();
        assert_eq!(&update[..7], &[0x12, 0x08, 0x00, 0x10, 0x09, 0xa0, 8]);
        assert_eq!(&update[7..], &[2, 0, 0, 0, 0x02, 0x01, 0x82, 0x07, 0x13]);
        let created = area_create_full(1, CHUNK_ID, &[0x0101], &columns, &[0x0102_0000]).unwrap();
        assert!(created.windows(9).any(|w| w == [2, 2, 0, 0, 0, 0x02, 0x01, 0x82, 0x07]));
        assert!(created.windows(7).any(|w| w == [1, 1, 0, 0, 0, 0x01, 0x01]));
        assert_eq!(area_create_full(0, CHUNK_ID, &[], &[], &[]).unwrap(), area_create_state(0, CHUNK_ID, &[], &[]).unwrap());
        let full = (0..125u16).collect::<Vec<_>>();
        assert_eq!(area_update_columns(0, &full).unwrap()[6], 254);
        let mut over = full.clone(); over.push(125);
        assert!(area_update_columns(0, &over).is_err());
        assert!(area_create_full(0, CHUNK_ID, &[], &over, &[]).is_err());
        assert!(area_update_columns(0, &[2, 1]).is_err());
        assert!(area_update_columns(0, &[2, 2]).is_err());
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
