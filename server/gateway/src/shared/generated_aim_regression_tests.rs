//! Generated profile source-envelope regression; native aim is NOT_RUN.
use super::*;
use crate::{p06t_device_caps::Profile,p06t_device_state::State as Devices,p06t_shells091 as shells};

fn fv()->(VehicleKind,crate::gateway091::shared::generated_vehicles::GeneratedId){
    let id=crate::gateway091::shared::generated_vehicles::registry().unwrap()
        .by_vehicle("vehicle:uk:GB48_FV215b_183").unwrap();
    (VehicleKind::Generated(id),id)
}

#[test]
fn generated_fv_source_yaw_is_bounded_for_ordinary_and_selected_controller(){
    let(kind,id)=fv();assert!(!kind.is_extended());
    let envelope=kind.source_aim().unwrap().envelope;let bounds=envelope.yaw_limits().unwrap();
    assert!((bounds.min-(-45f32).to_radians()).abs()<1e-6);
    assert!((bounds.max-45f32.to_radians()).abs()<1e-6);
    let caps=Devices::new(Profile::Generated(id)).unwrap().capabilities();let shell=shells::profile(kind.mount()).shots[0];
    for selected in [false,true]{
        let mut aim=State::new();
        for intent in [Intent::Hold{yaw:PI-0.1,pitch:0.},Intent::Hold{yaw:-PI+0.1,pitch:0.},
                       Intent::Point([500.,0.,-500.]),Intent::Point([-500.,0.,-500.])] {
            aim.set(intent).unwrap();
            for _ in 0..240{
                if selected{aim.advance_pose_for_selected(kind,[0.;3],[0.;3],0.1,shell,caps).unwrap();}
                else{aim.advance_pose_for(kind,[0.;3],[0.;3],0.1).unwrap();}
                assert!((bounds.min..=bounds.max).contains(&aim.yaw));
                let limits=envelope.pitch_limits(aim.yaw).unwrap();assert!((limits.min..=limits.max).contains(&aim.pitch));
                assert!(crate::gateway091::shared::wire::packed_angles_for(kind,&aim).is_ok());
            }
        }
    }
}

#[test]
fn seven_hybrid_generated_profiles_remain_representable_and_encode_both_sides(){
    let registry=crate::gateway091::shared::generated_vehicles::registry().unwrap();
    for label in ["ussr-KV-3","usa-M4_Sherman","germany-Waffentrager_E100","japan-Chi_Ri",
                  "uk-GB48_FV215b_183","china-Ch22_113","france-Bat_Chatillon25t"]{
        let id=registry.by_label(label).unwrap();let kind=VehicleKind::Generated(id);
        assert!(source_controller_supported(kind).unwrap(),"{label}");
        assert!(crate::gateway091::shared::profile13_templates::require_source_wire_support(kind).is_ok(),"{label}");
        let limits=kind.source_aim().unwrap().envelope.absolute();let wire=kind.aim();
        assert!(limits.min>=wire.min_pitch&&limits.max<=wire.max_pitch,"{label}");
        let caps=Devices::new(Profile::Generated(id)).unwrap().capabilities();let shell=shells::profile(kind.mount()).shots[0];
        for selected in [false,true]{
            let mut aim=State::new();
            for yaw in [2.8,-2.8]{
                aim.set(Intent::Hold{yaw,pitch:0.}).unwrap();
                for _ in 0..160{
                    if selected{aim.advance_pose_for_selected(kind,[0.;3],[0.;3],0.1,shell,caps).unwrap();}
                    else{aim.advance_pose_for(kind,[0.;3],[0.;3],0.1).unwrap();}
                    assert!(crate::gateway091::shared::wire::packed_angles_for(kind,&aim).is_ok(),"{label}");
                }
            }
        }
    }
}

/// #717 `decodeRestrictedAngleFromUint(code & 63, 6, *pitchLimits['absolute'])`.
fn client_pitch(code:u16,(min,max):(f32,f32))->f64{min as f64+(code&63) as f64/63.*(max as f64-min as f64)}

/// CONTENT-0 2.5: front/back sectors wider than basic. Every generated kind is
/// now supported; the wide ones quantize over the source absolute envelope.
#[test]
fn wide_pitch_generated_profiles_are_supported_and_quantize_over_absolute(){
    let registry=crate::gateway091::shared::generated_vehicles::registry().unwrap();
    let mut wide=Vec::new();
    for entry in registry.entries(){
        let kind=VehicleKind::Generated(entry.id);
        assert!(source_controller_supported(kind).unwrap(),"{}",entry.label);
        assert!(crate::gateway091::shared::profile13_templates::require_source_wire_support(kind).is_ok(),"{}",entry.label);
        let absolute=kind.source_aim().unwrap().envelope.absolute();let basic=kind.aim();
        assert_eq!(wire_pitch_range(kind).unwrap(),(absolute.min,absolute.max),"{}",entry.label);
        assert!(absolute.min<=basic.min_pitch&&basic.max_pitch<=absolute.max,"{}",entry.label);
        // CONTENT-0 3.3: every build is checked above; the pinned list names the stock builds.
        if entry.stock&&(absolute.min,absolute.max)!=(basic.min_pitch,basic.max_pitch){wide.push(entry.label.as_str());}
    }
    wide.sort_unstable();
    // main and test_lab share the generated rows since the CONTENT-0 main transfer (owner 12.11).
    let expected=["china-Ch24_Type64","france-AMX_13_75","france-D2","germany-Pz_IV_AusfH","japan-Ke_Ni","japan-Ke_Ni_B",
                  "uk-GB40_Gun_Carrier_Churchill","usa-M4A2E4","usa-T7_Combat_Car","ussr-Object_430"].as_slice();
    assert_eq!(wide,expected);
}

/// Both controllers reach each sector's own limits, never beyond the current
/// yaw's sector, and every published code decodes (client formula) to within
/// half a 6-bit bin of the authoritative pitch.
#[test]
fn wide_pitch_controller_keeps_sector_clamp_and_wire_round_trips_through_client_decoder(){
    let registry=crate::gateway091::shared::generated_vehicles::registry().unwrap();
    let mut checked=0;
    // CONTENT-0 3.3: the envelope and the aim are the turret x gun pair's; each distinct pair once.
    let mut pairs=std::collections::BTreeSet::new();
    for entry in registry.entries(){
        if !pairs.insert((entry.vehicle_id.as_str(),entry.parts[1].as_str(),entry.parts[2].as_str(),format!("{:?}{:?}",entry.source_aim,entry.aim))){continue;}
        let kind=VehicleKind::Generated(entry.id);let envelope=kind.source_aim().unwrap().envelope;
        let absolute=envelope.absolute();let basic=kind.aim();
        if (absolute.min,absolute.max)==(basic.min_pitch,basic.max_pitch){continue;}
        checked+=1;let range=wire_pitch_range(kind).unwrap();let bin=(range.1 as f64-range.0 as f64)/63.;
        let caps=Devices::new(Profile::Generated(entry.id)).unwrap().capabilities();let shell=shells::profile(kind.mount()).shots[0];
        let yaws:Vec<f32>=match envelope.yaw_limits(){Some(l)=>vec![0.,l.min,l.max],None=>vec![0.,PI/2.,-PI/2.,PI-0.01,-PI+0.01]};
        let (mut reached_min,mut reached_max)=(false,false);
        for selected in [false,true]{
            for &yaw in &yaws{
                for pitch in [-1.5f32,1.5]{
                    let mut aim=State::new();aim.set(Intent::Hold{yaw,pitch}).unwrap();
                    for _ in 0..400{
                        if selected{aim.advance_pose_for_selected(kind,[0.;3],[0.;3],0.1,shell,caps).unwrap();}
                        else{aim.advance_pose_for(kind,[0.;3],[0.;3],0.1).unwrap();}
                        let limits=envelope.pitch_limits(aim.yaw).unwrap();
                        assert!((limits.min..=limits.max).contains(&aim.pitch),"{} yaw={} pitch={}",entry.label,aim.yaw,aim.pitch);
                        let code=crate::gateway091::shared::wire::packed_angles_for(kind,&aim).unwrap();
                        assert!((client_pitch(code,range)-aim.pitch as f64).abs()<=bin/2.+1e-6,"{}",entry.label);
                    }
                    let limits=envelope.pitch_limits(aim.yaw).unwrap();
                    assert_eq!(aim.pitch,if pitch<0.{limits.min}else{limits.max},"{} yaw={}",entry.label,aim.yaw);
                    reached_min|=aim.pitch==absolute.min;reached_max|=aim.pitch==absolute.max;
                }
            }
        }
        assert!(reached_min&&reached_max,"{}: absolute extremes reachable in some sector",entry.label);
    }
    assert!(checked>=6);
}

#[test]
fn wide_pitch_wire_ends_are_codes_0_and_63_and_out_of_sector_pitch_is_refused(){
    let registry=crate::gateway091::shared::generated_vehicles::registry().unwrap();
    let kind=VehicleKind::Generated(registry.by_label("usa-M4A2E4").unwrap());
    let envelope=kind.source_aim().unwrap().envelope;let absolute=envelope.absolute();
    // Source basic(-25,5), front(-25,10,14), back(-25,10,145), transition 1 degree.
    assert!((absolute.min-(-25f32).to_radians()).abs()<1e-6&&(absolute.max-10f32.to_radians()).abs()<1e-6);
    assert!((kind.aim().max_pitch-5f32.to_radians()).abs()<1e-6);
    let at=|yaw:f32,pitch:f32|State{yaw,pitch,intent:Intent::Hold{yaw,pitch}};
    let wire=|s:&State|crate::gateway091::shared::wire::packed_angles_for(kind,s);
    assert_eq!(wire(&at(0.,absolute.min)).unwrap()&63,0);
    assert_eq!(wire(&at(0.,absolute.max)).unwrap()&63,63);
    assert_eq!(wire(&at(PI,absolute.max)).unwrap()&63,63);
    // Basic sector (yaw 20 degrees) only allows +5: the absolute +10 is refused, never clipped.
    let yaw=20f32.to_radians();let limits=envelope.pitch_limits(yaw).unwrap();
    assert_eq!(limits.max,kind.aim().max_pitch);
    assert!(wire(&at(yaw,limits.max)).is_ok());
    assert!(wire(&at(yaw,absolute.max)).is_err());
    assert!(wire(&at(0.,f32::from_bits(absolute.max.to_bits()+1))).is_err());
    // Basic +5 now lands on code round(63*30/35)=54, not 63 as with the old basic range.
    assert_eq!(wire(&at(yaw,limits.max)).unwrap()&63,54);
}

#[test]
fn generated_fv_invalid_yaw_and_nan_fail_atomically_and_wire_refuses_invalid_yaw(){
    let(kind,id)=fv();let caps=Devices::new(Profile::Generated(id)).unwrap().capabilities();
    let shell=shells::profile(kind.mount()).shots[0];
    for yaw in [f32::from_bits(0x3f4f2d20),f32::NAN]{
        for selected in [false,true]{
            let mut aim=State::new();aim.yaw=yaw;let before=(aim.yaw.to_bits(),aim.pitch.to_bits(),aim.intent);
            let result=if selected{aim.advance_pose_for_selected(kind,[0.;3],[0.;3],0.1,shell,caps)}
                else{aim.advance_pose_for(kind,[0.;3],[0.;3],0.1)};
            assert!(result.is_err());assert_eq!((aim.yaw.to_bits(),aim.pitch.to_bits(),aim.intent),before);
            assert!(crate::gateway091::shared::wire::packed_angles_for(kind,&aim).is_err());
        }
    }
    assert!(crate::gateway091::shared::wire::packed_angles_for(kind,&State::new()).is_ok());
}

#[test]
fn kv3_blend_boundary_controller_stays_representable_on_native_fault_yaw(){
    let registry=crate::gateway091::shared::generated_vehicles::registry().unwrap();
    let id=registry.by_label("ussr-KV-3").unwrap();let kind=VehicleKind::Generated(id);
    let yaw=0.16458893_f32;let wire=kind.aim();let envelope=kind.source_aim().unwrap().envelope;
    // Actual saved native fault: the old source blend overshot basic maximum by one f32 ULP.
    let blended=envelope.pitch_limits(yaw).unwrap();
    assert_eq!(wire.max_pitch.to_bits(),0x3dfa35dd);
    assert_eq!(blended.max.to_bits(),wire.max_pitch.to_bits());
    let caps=Devices::new(Profile::Generated(id)).unwrap().capabilities();let shell=shells::profile(kind.mount()).shots[0];
    for selected in [false,true]{
        let mut aim=State::new();aim.yaw=yaw;aim.set(Intent::Hold{yaw,pitch:1.0}).unwrap();
        for _ in 0..80 {
            if selected {aim.advance_pose_for_selected(kind,[0.;3],[0.;3],0.1,shell,caps).unwrap();}
            else {aim.advance_pose_for(kind,[0.;3],[0.;3],0.1).unwrap();}
            assert!(aim.pitch<=wire.max_pitch,"selected={selected} pitch={:?}, wire={:?}",aim.pitch,wire.max_pitch);
            assert!(crate::gateway091::shared::wire::packed_angles_for(kind,&aim).is_ok());
        }
        assert_eq!(aim.pitch.to_bits(),wire.max_pitch.to_bits());
    }
    let invalid=State{yaw,pitch:f32::from_bits(wire.max_pitch.to_bits()+1),intent:Intent::Hold{yaw,pitch:0.}};
    assert!(crate::gateway091::shared::wire::packed_angles_for(kind,&invalid).is_err());
}
