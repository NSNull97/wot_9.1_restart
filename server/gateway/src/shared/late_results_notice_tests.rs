//! Source-width literal fixture only. No native callback observation/UI claim.
use super::*;
fn result()->Results{
 let v:serde_json::Value=serde_json::from_slice(include_bytes!("../../../../tests/fixtures/p08c-late-loss-two-owner-vectors.json")).unwrap();
 let seal:serde_json::Value=serde_json::from_str(v["append_vectors"][1]["request"]["seal_json"].as_str().unwrap()).unwrap();
 Results::from_json_p06t(seal["results_json"].as_str().unwrap()).unwrap()
}
#[test]fn p08c_late_notice_source_width_literal_defeat_is_minus_one_and_numeric_rewards_zero(){
 let packet=candidate_direct(&result(),1,1792080060).unwrap();let hex=packet.iter().map(|b|format!("{b:02x}")).collect::<String>();
 // Authored independently with Python struct widths + primitive protocol2,
 // never a captured native packet and never a compatibility PASS by roundtrip.
 assert_eq!(hex,"134bb3ffffffffffffffff16000000002f3eb4da410000002f3eb4da4100000000ffffffffffffffff00008980027d285504747970654b025504646174617d28550b6172656e615479706549444b04550f6172656e6143726561746554696d654a80f8d06a550d6172656e61556e6971756549448a07010000000000205508697357696e6e65724affffffff551076656854797065436f6d7044657363724d010d550278704b005507637265646974734b0075752e00");assert_eq!(packet[..3],[0x13,0x4b,(packet.len()-3)as u8]);
 assert_eq!(i64::from_le_bytes(packet[3..11].try_into().unwrap()),-1);assert_eq!(&packet[11..13],&[22,0]);
 assert_eq!(f64::from_le_bytes(packet[13..21].try_into().unwrap()),1792080060.);
 assert_eq!(f64::from_le_bytes(packet[21..29].try_into().unwrap()),1792080060.);assert_eq!(packet[43]as usize,packet.len()-45);
}
#[test]fn p08c_late_notice_foreign_owner_and_non_utc_zero_fail(){
 let r=result();assert!(candidate_direct(&r,99,1792080060).is_err());assert!(candidate_direct(&r,1,0).is_err());assert!(candidate_direct(&r,1,r.created_unix-1).is_err());
}
#[test]fn p08c_late_notice_int64_arena_never_truncates_and_short_envelope_stays_bounded(){
 let mut r=result();r.arena_id=i64::MAX as u64;let packet=candidate_direct(&r,1,r.created_unix).unwrap();assert!(packet.len()-3<=254);
 let key=b"arenaUniqueID";let at=packet.windows(key.len()).position(|w|w==key).unwrap()+key.len();
 assert_eq!(&packet[at..at+2],&[0x8a,8]);assert_eq!(i64::from_le_bytes(packet[at+2..at+10].try_into().unwrap()),i64::MAX);
}
