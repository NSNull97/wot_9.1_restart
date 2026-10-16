use super::*;

#[test]
fn p06t_breech_math_has_distinct_policy_and_nominal_source_hp_for_every_family(){
    for profile in PROFILES {for shell in profile.shots {
        let input=DirectInput{shell,plate:Plate{armor_mm:Some(0.),ordinary:false},
            chord:[1.,0.,0.],winding_normal:[0.,0.,1.],distance_m:20.};
        let old=resolve_direct(input).unwrap();assert_eq!((old.decision,old.damage_hp),(Decision::Unsupported,0));
        let new=resolve_unarmored_device(input).unwrap();
        assert_eq!((new.policy,new.decision,new.damage_hp),(UNARMORED_DEVICE_POLICY,Decision::UnarmoredDevice,shell.damage_hp));
        assert_eq!((new.effective_armor_mm,new.normalization_degrees),(None,0.));
        assert_eq!(new.incidence_degrees,90.); // zero-armor device is not ordinary angle arithmetic
        let expired=resolve_unarmored_device(DirectInput{distance_m:shell.max_distance_m,..input}).unwrap();
        assert_eq!((expired.policy,expired.decision,expired.damage_hp),(UNARMORED_DEVICE_POLICY,Decision::OutOfRange,0));
    }}
}

#[test]
fn p06t_breech_math_rejects_ordinary_missing_positive_armor_and_forged_shell(){
    let input=DirectInput{shell:PROFILES[0].shots[0],plate:Plate{armor_mm:Some(0.),ordinary:false},
        chord:[1.,0.,0.],winding_normal:[1.,0.,0.],distance_m:10.};
    for plate in [Plate{armor_mm:None,ordinary:false},Plate{armor_mm:Some(1.),ordinary:false},
        Plate{armor_mm:Some(0.),ordinary:true},Plate{armor_mm:Some(f64::NAN),ordinary:false}] {
        assert!(resolve_unarmored_device(DirectInput{plate,..input}).is_err());
    }
    let mut shell=input.shell;shell.damage_hp+=1;
    assert!(resolve_unarmored_device(DirectInput{shell,..input}).is_err());
    assert!(resolve_unarmored_device(DirectInput{chord:[0.;3],..input}).is_err());
    assert!(resolve_unarmored_device(DirectInput{distance_m:f64::INFINITY,..input}).is_err());
}
