use super::*;
#[test]fn p06t_source_catalog_has_exact_curated_mounts_and_no_cross_mount_shell_fallback(){
    let mut ids=std::collections::BTreeSet::new();
    for (index,mount)in Mount::ALL.into_iter().enumerate(){
        assert_eq!(mount.index(),index);let p=profile(mount);assert_eq!(p.mount,mount);
        assert_eq!(p.burst_count,1);assert_eq!(p.burst_interval_seconds,0.);
        assert_eq!(p.additional_vehicle_qualification_required,index>=5);
        for s in p.shots{assert!(ids.insert(s.compact_descr));assert_eq!(shell(mount,s.compact_descr as i32),Some(&s));
            assert_eq!(s.explosion_radius_m.is_some(),s.family==Family::HighExplosive);
            assert!((s.speed_mps-s.raw_speed_mps*0.8).abs()<1e-10);
            assert!((s.gravity_mps2-9.81*0.8f64.powi(2)).abs()<1e-12);}
        assert!(shell(mount,-1).is_none());assert!(shell(mount,i32::MAX).is_none());
    }assert_eq!(ids.len(),24);assert!(shell(Mount::Ms1Stock,14602).is_none());assert!(Mount::from_label("future-tank").is_none());
}
#[test]fn p06t_source_mounted_reload_overrides_and_historical_clips_are_distinct(){
    for(mount,reload,capacity)in[(Mount::Ms1Stock,2.5,96),(Mount::Is7Stock,13.7,30),(Mount::T26Stock,2.3,160),(Mount::T34Stock,6.,77),(Mount::T3485Stock,4.1,68)]{
        let p=profile(mount);assert_eq!(p.reload_seconds,reload);assert_eq!(p.capacity,capacity);assert_eq!((p.clip_count,p.clip_interval_seconds),(1,0.));assert!(!p.clip_from_mounted_source);}
    let a=profile(Mount::WtE100128);let b=profile(Mount::WtE100150);
    assert_eq!((a.clip_count,a.clip_interval_seconds,a.reload_seconds,a.capacity),(6,2.,60.,60));
    assert_eq!((b.clip_count,b.clip_interval_seconds,b.reload_seconds,b.capacity),(4,3.,50.,60));assert!(a.clip_from_mounted_source&&b.clip_from_mounted_source);
}
#[test]fn p06t_source_fv_premium_hesh_is_he275_and_uses_original_uk_nation5(){
    let p=profile(Mount::Fv215b183);assert_eq!(p.native_nation_id,5);assert_eq!(p.vehicle_type_compact_descr,(36<<8)+(5<<4)+1);
    let h=p.shots[1];assert_eq!(h.resource,"_183mm_HESH");assert_eq!(h.family,Family::HighExplosive);
    assert_eq!(h.penetration_mm,[275.,275.]);assert_eq!(h.damage_hp,1750);assert_eq!(h.device_damage,244);
    assert_eq!(h.caliber_mm,182.9);assert_eq!(h.explosion_radius_m,Some(5.05));assert!(h.premium_gold_flag);
    assert_eq!(h.compact_descr,(82<<8)+(5<<4)+10);assert_eq!(p.shots[2].penetration_mm,[92.,92.]);
}
#[test]fn p06t_source_shell_family_changes_actual_speed_damage_and_radius(){
    let ms=profile(Mount::Ms1Stock);assert_eq!(ms.shots[1].family,Family::HollowCharge);assert_eq!(ms.shots[1].raw_speed_mps,354.);assert_eq!(ms.shots[0].raw_speed_mps,442.);
    let t=profile(Mount::T3485Stock);assert_eq!(t.shots[0].damage_hp,115);assert_eq!(t.shots[1].damage_hp,110);assert_eq!(t.shots[1].family,Family::ArmorPiercingCr);
    assert_eq!(profile(Mount::T26Stock).shots[1].raw_speed_mps,838.);assert_eq!(profile(Mount::T34Stock).shots[1].raw_speed_mps,490.);
    assert_eq!(profile(Mount::Is7Stock).shots[2].explosion_radius_m,Some(2.78));
}
#[test] fn battle_any_generated_gun_shells_are_known_and_forged_ones_are_not(){
    // Stand -11 2026-10-28: an M4 shot closed the battle because only PROFILES was searched.
    let kind=crate::gateway091::shared::vehicle_profile::VehicleKind::from_owned_label("usa-M4_Sherman").unwrap();
    let gun=profile(kind.mount());for shot in gun.shots{assert!(known_shell(&shot),"{}",shot.resource);}
    assert!(known_shell(&PROFILES[0].shots[0]));
    let mut forged=gun.shots[0];forged.damage_hp+=1;assert!(!known_shell(&forged));
}
