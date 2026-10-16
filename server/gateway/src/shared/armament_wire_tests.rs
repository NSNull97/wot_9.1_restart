use crate::{armament_wire091 as w,p06t_shells091::{Mount,PROFILES}};
fn hex(bytes:Vec<u8>)->String{bytes.iter().map(|v|format!("{v:02x}")).collect()}

#[test]fn p06t_effects_all24_original_order_and_launch_snapshot_identity(){
    let expected=[[2,4,3],[14,17,15],[2,5,3],[6,8,7],[6,9,7],[14,17,15],[14,16,15],[18,19,19]];
    for(m,p)in PROFILES.iter().enumerate(){for(s,shell)in p.shots.into_iter().enumerate(){assert_eq!(w::effect_index(shell).unwrap(),expected[m][s]);}}
    let mut forged=PROFILES[0].shots[0];forged.effects_resource="largeHighExplosive";assert!(w::effect_index(forged).is_err());
    let mut forged=PROFILES[0].shots[0];forged.damage_hp+=1;assert!(w::effect_index(forged).is_err());
}
#[test]fn p06t_literal_current_next_and_partial_reload_from_original_caller(){
    assert_eq!(w::command(&[0x8d,5,0,0,10,11,0,0]).unwrap(),Some(w::Intent::Select(w::Setting::Current,2826)));
    assert_eq!(w::command(&[0x8d,5,0,1,10,11,0,0]).unwrap(),Some(w::Intent::Select(w::Setting::Next,2826)));
    assert_eq!(w::command(&[0x8d,5,0,17,0,0,0,0]).unwrap(),Some(w::Intent::ReloadPartialClip));
    assert!(w::command(&[0x8d,5,0,17,1,0,0,0]).is_err());
    assert_eq!(hex(w::setting(Mount::Ms1Stock,w::Setting::Current,2826).unwrap()),"1340000a0b0000");
    assert_eq!(hex(w::setting(Mount::Ms1Stock,w::Setting::Next,3082).unwrap()),"1340010a0c0000");
    let good=[0x8d,5,0,0,10,11,0,0];for n in 1..8{assert!(w::command(&good[..n]).is_err());}
    for mut bad in [good;4].into_iter().enumerate(){match bad.0{0=>bad.1[1]=4,1=>bad.1[3]=18,2=>bad.1[4..8].copy_from_slice(&(-1i32).to_le_bytes()),_=>bad.1[4..8].copy_from_slice(&65536i32.to_le_bytes())};assert!(w::command(&bad.1).is_err());}
    assert_eq!(w::command(&[0x8d,5,0,0,1,0,0,0]).unwrap(),Some(w::Intent::Select(w::Setting::Current,1)));
    assert_eq!(w::command(&[0x87]).unwrap(),None);
}
#[test]fn p06t_literal_ammo160_six_vs_four_clips_and_three_stack_reconciliation(){
    assert_eq!(hex(w::ammo_row(Mount::T26Stock,1034,160,0).unwrap()),"13440a040000a000000000");
    assert_eq!(hex(w::ammo_row(Mount::WtE100128,13850,60,6).unwrap()),"13441a3600003c00060000");
    assert_eq!(hex(w::ammo_row(Mount::WtE100150,19482,60,4).unwrap()),"13441a4c00003c00040000");
    assert_eq!(hex(w::ammo_snapshot(Mount::Ms1Stock,[0,2,3],2826,3082,1).unwrap()),
        "13440a0a0000000000000013440a0b0000020000000013440a0c000003000000001340000a0b00001340010a0c0000");
    assert_eq!(w::ammo_snapshot(Mount::Ms1Stock,[0,0,0],2570,2570,0).unwrap().len(),47);
    assert!(w::ammo_snapshot(Mount::Ms1Stock,[0,0,0],2570,2570,1).is_err());
    assert!(w::ammo_snapshot(Mount::T26Stock,[160,1,0],1034,1290,1).is_err());
    assert!(w::ammo_row(Mount::WtE100128,13850,5,6).is_err());
    assert!(w::ammo_row(Mount::WtE100150,19482,60,6).is_err());
    assert!(w::ammo_row(Mount::Ms1Stock,14602,1,0).is_err());
    assert!(w::ammo_row(Mount::Ms1Stock,2570,1,1).is_err());
}
#[test]fn p06t_literal_full_fire_property_preserves_other_modifiers_and_create_value(){
    assert_eq!(hex(w::modifiers_value(&[4]).unwrap()),"0100000004");
    assert_eq!(hex(w::public_modifiers(1002,&[4]).unwrap()),"12ea030000a505010000000413");
    assert_eq!(hex(w::public_modifiers(1002,&[]).unwrap()),"12ea030000a5040000000013");
    assert_eq!(hex(w::public_modifiers(1002,&[26,4]).unwrap()),"12ea030000a506020000001a0413");
    assert_eq!(hex(w::public_modifiers(1002,&[26]).unwrap()),"12ea030000a505010000001a13");
    for bad in [&[0][..],&[43][..],&[4,4][..]]{assert!(w::modifiers_value(bad).is_err());}
    assert!(w::public_modifiers(0,&[4]).is_err());
}
#[test]fn p06t_literal_critical_fire_stop_and_positive_hp_inactive_crew(){
    assert_eq!(hex(w::damage_info(1002,4,32,1001).unwrap()),"1345ea0300000420e9030000");
    assert_eq!(hex(w::damage_info(1002,3,0,1001).unwrap()),"1345ea0300000300e9030000");
    assert_eq!(hex(w::damage_info(1002,35,0,0).unwrap()),"1345ea030000230000000000");
    assert_eq!(hex(w::owner_health(90,false,90).unwrap()),"133f5a0000");
    assert_eq!(hex(w::public_crew_active(1002,false).unwrap()),"12ea0300009f0013");
    for(code,extra)in [(0,0),(4,4),(10,26),(3,27),(35,35),(26,32),(36,0)]{assert!(w::damage_info(1002,code,extra,1001).is_err());}
    assert!(w::owner_health(91,false,90).is_err());assert!(w::owner_health(-3,false,90).is_err());
    assert_eq!(hex(w::owner_health(-1,false,90).unwrap()),"133fffff00");
}
#[test]fn p06t_literal_explosion_uses_frozen_he_effect_and_bounded_native_fields(){
    let he=PROFILES[Mount::Is7Stock.index()].shots[2];
    assert_eq!(hex(w::explosion(1002,1001,[1.5,2.,-3.25],he).unwrap()),"12ea03000040e90300000000c03f00000040000050c00f13");
    assert_eq!(hex(w::ammo_bay_explosion(1002,2.,3.).unwrap()),"12ea0300003d000000400000404013");
    assert!(w::explosion(1002,1001,[0.;3],PROFILES[0].shots[0]).is_err());
    assert!(w::explosion(1002,1001,[f32::NAN,0.,0.],he).is_err());
    assert!(w::explosion(1002,1001,[100_001.,0.,0.],he).is_err());
    assert!(w::ammo_bay_explosion(1002,f32::INFINITY,0.).is_err());
}
#[test]fn p06t_literal_reload_start_end_keep_original_float32_order(){
    assert_eq!(hex(w::reload(1002,2.,60.).unwrap()),"1346ea0300000000004000007042");
    assert_eq!(hex(w::reload(1002,0.,60.).unwrap()),"1346ea0300000000000000007042");
    assert!(w::reload(1002,240.,240.).is_ok());assert!(w::reload(1002,480.,480.).is_ok());assert!(w::reload(1002,0.,481.).is_err());
    for(left,base)in [(f32::NAN,60.),(61.,60.),(-1.,60.),(0.,0.),(0.,f32::INFINITY)]{assert!(w::reload(1002,left,base).is_err());}
    assert!(w::reload(0,0.,60.).is_err());
}
