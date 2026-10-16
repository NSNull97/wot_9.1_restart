use super::*;
#[test]fn source_wt_limits_match_nine_preexisting_independent_sse_restatement_samples_bit_exact(){
    // Retained BEFORE this Rust implementation in pinned source proof result:
    // local/evidence/20261016-p06t-aim01/result.json numeric_candidates. They
    // are static-analysis samples, not execution of original machine code.
    for(degrees,bits)in[(-180.,0xbdfa35dd),(-143.,0xbdfa3604),(-140.5,0xbe44981c),(-138.,0xbe860a92),
        (0.,0xbe860a92),(138.,0xbe860a92),(140.5,0xbe44981c),(143.,0xbdfa3604),(180.,0xbdfa35dd)]{
        let limits=SourceEnvelope::wt_e100().pitch_limits(rad(degrees)).unwrap();assert_eq!(limits.min.to_bits(),bits,"degrees={degrees}");assert_eq!(limits.max.to_bits(),0x3db2b8c2);
    }
}
#[test]fn explicit_wt_transition_is_five_degrees_and_rear_minimum_varies_in_both_directions(){
    let e=SourceEnvelope::wt_e100();assert_eq!(e.transition_radians().to_bits(),rad(5.).to_bits());assert_ne!(e.transition_radians(),0.4);
    for angle in[138.,139.,140.,140.5,141.,142.,143.,150.,180.]{let a=e.pitch_limits(rad(angle)).unwrap();let b=e.pitch_limits(rad(-angle)).unwrap();assert_eq!(a,b);
        assert!(a.min>=rad(-15.)-1e-7&&a.min<=rad(-7.)+1e-7);assert!((a.max-rad(5.)).abs()<1e-7);}
    assert_eq!(e.clamp_pitch(rad(140.5),rad(-14.)).unwrap().to_bits(),0xbe44981c);
}
#[test]fn fv_turret_yaw_clamps_to_source_plus_minus_45_and_pitch_stays_mounted_limits(){
    let e=SourceEnvelope::fv215b_183();assert_eq!(e.clamp_yaw(rad(180.)).unwrap(),rad(45.));assert_eq!(e.clamp_yaw(rad(-180.)).unwrap(),rad(-45.));
    for yaw in[-45.,-10.,0.,10.,45.]{let l=e.pitch_limits(rad(yaw)).unwrap();assert!((l.min-rad(-15.)).abs()<1e-7);assert!((l.max-rad(5.)).abs()<1e-7);}
    assert_eq!(e.pitch_limits(rad(46.)).unwrap_err(),Error::Yaw);assert_eq!(e.transition_radians(),0.4);
}
#[test]fn generic_blend_interpolates_upper_as_well_as_lower_without_constant_maximum_shortcut(){
    // Synthetic algebra input only, not a new tank profile or historical row.
    let mut e=SourceEnvelope::wt_e100();e.rear.limits=Limits{min:rad(-7.),max:rad(1.)};let mid=e.pitch_limits(rad(140.5)).unwrap();
    assert_eq!(mid.min.to_bits(),0xbe44981c);assert!((mid.max-rad(3.)).abs()<1e-6);
    e.front=Extra{limits:Limits{min:rad(-10.),max:rad(2.)},sector:rad(10.)};
    let mid=e.pitch_limits(rad(12.5)).unwrap();assert!((mid.min-rad(-12.5)).abs()<1e-6);assert!((mid.max-rad(3.5)).abs()<1e-6);
}
#[test]fn invalid_finite_bounds_yaw_pitch_and_poisoned_source_parameters_fail_closed(){
    let e=SourceEnvelope::wt_e100();for x in[f32::NAN,f32::INFINITY,-f32::INFINITY,PI+0.01]{assert!(e.pitch_limits(x).is_err());assert!(e.clamp_yaw(x).is_err());}
    for p in[f32::NAN,f32::INFINITY,FRAC_PI_2+0.01]{assert_eq!(e.clamp_pitch(0.,p).unwrap_err(),Error::Pitch);}
    for poison in 0..6{let mut p=e;match poison{0=>p.transition=0.,1=>p.rear.sector=f32::NAN,2=>p.basic.min=1.,3=>p.rear.limits.max=1.,4=>p.front.sector=PI,5=>p.yaw=Some(Limits{min:1.,max:0.}),_=>unreachable!()}
        assert_eq!(p.pitch_limits(0.).unwrap_err(),Error::SourceBounds);}
}
#[test]fn mounted_rates_and_128_150_shared_envelope_do_not_share_clip_or_profile_admission(){
    let a=SourceAim::wt128();let b=SourceAim::wt150();let c=SourceAim::fv183();assert_eq!(a.envelope,b.envelope);
    assert_eq!(a.yaw_rate,rad(22.));assert_eq!(a.pitch_rate,rad(26.25));assert_eq!(b.pitch_rate,rad(23.625));assert_eq!(c.yaw_rate,rad(16.));
    assert_eq!(c.pitch_rate,b.pitch_rate);assert_eq!(a.envelope.yaw_limits(),None);assert_eq!(c.envelope.yaw_limits(),Some(Limits{min:rad(-45.),max:rad(45.)}));
}
