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

#[test]
fn qualified_wider_than_wire_profiles_are_refused_without_mutation_or_encoding(){
    let registry=crate::gateway091::shared::generated_vehicles::registry().unwrap();
    let mut refused=Vec::new();
    for entry in registry.entries(){
        let kind=VehicleKind::Generated(entry.id);
        if source_controller_supported(kind).is_err(){
            refused.push(entry.label.as_str());
            assert!(crate::gateway091::shared::profile13_templates::require_source_wire_support(kind).is_err());
            let mut aim=State::new();let before=aim.clone();
            assert!(aim.advance_pose_for(kind,[0.;3],[0.;3],0.1).is_err());assert_eq!(aim,before);
            let caps=Devices::new(Profile::Generated(entry.id)).unwrap().capabilities();
            let shell=shells::profile(kind.mount()).shots[0];
            assert!(aim.advance_pose_for_selected(kind,[0.;3],[0.;3],0.1,shell,caps).is_err());assert_eq!(aim,before);
            assert!(crate::gateway091::shared::wire::packed_angles_for(kind,&aim).is_err());
        }
    }
    refused.sort_unstable();
    assert_eq!(refused,["france-AMX_13_75","germany-Pz_IV_AusfH","japan-Ke_Ni","japan-Ke_Ni_B",
                        "uk-GB40_Gun_Carrier_Churchill","usa-M4A2E4"]);
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
