//! Actual promoted hangar shim with unchanged legacy decoder. No native proof.
use crate::hangar091::{self as hangar,TrainingIncoming};
const SYNC:&[u8]=&[0x8e,20,0,225,0,100,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0];
const OWN404:&[u8]=&[0x8e,20,0,222,0,0x94,1,1,0,0x10,9,0,0,0,0,2,0,0,0,0,0,0,0];
#[test]fn p10b_actual_hangar_shim_keeps_default_closed_and_enabled_record_order(){
    assert!(hangar::requests_training_with(OWN404,false,hangar::requests_interactive).is_err());
    let old=hangar::requests_training_with(SYNC,false,hangar::requests_interactive).unwrap();
    assert!(matches!(&old[..],[TrainingIncoming::Account(hangar::Incoming::Sync(_))]));
    let both=hangar::requests_training_with(&[SYNC,OWN404].concat(),true,hangar::requests_interactive).unwrap();
    assert!(matches!(both[0],TrainingIncoming::Account(hangar::Incoming::Sync(_))));
    assert!(matches!(both[1],TrainingIncoming::Room(super::ingress::Request{kind:super::ingress::Kind::Assign{account_entity:0x09100001,roster:2},..})));
}
#[test]fn p10b_actual_hangar_shim_preserves_cross_record_request_collision_and_late_poison(){
    let mut collision=OWN404.to_vec();collision[3..5].copy_from_slice(&225i16.to_le_bytes());
    assert!(hangar::requests_training_with(&[SYNC,&collision].concat(),true,hangar::requests_interactive).is_err());
    let mut legacy=SYNC.to_vec();legacy[3..5].copy_from_slice(&226i16.to_le_bytes());
    let bad=[SYNC,OWN404,&legacy].concat();
    assert!(hangar::requests_training_with(&bad,true,hangar::requests_interactive).is_err());
    let mut bad=[SYNC,OWN404].concat();bad.push(0x9a);
    assert!(hangar::requests_training_with(&bad,true,hangar::requests_interactive).is_err());
}
