use super::*;
use crate::{p06t_device_caps::Profile,p06t_device_state::{self as devices,State as Devices},p06t_shells091 as shells};
fn healthy(kind:VehicleKind)->devices::Capabilities {Devices::new_v2(Profile::SUPPORTED[kind.index()]).unwrap().capabilities()}
fn limits(kind:VehicleKind,aim:&State) {
    let e=kind.source_aim().unwrap().envelope;
    assert_eq!(e.clamp_yaw(aim.yaw).unwrap(),aim.yaw);let p=pitch_limits_for(kind,aim.yaw).unwrap();
    assert!(aim.pitch>=p.0&&aim.pitch<=p.1,"{:?} yaw={} pitch={} limits={p:?}",kind,aim.yaw,aim.pitch);
}

#[test] fn p06t_extended_fv_hold_and_points_never_cross_source_yaw_or_pitch() {
    let kind=VehicleKind::Fv183;let mut aim=State::new();
    for intent in [Intent::Hold{yaw:PI-0.1,pitch:-1.},Intent::Hold{yaw:-PI+0.1,pitch:1.},
        Intent::Point([500.,100.,-500.]),Intent::Point([-500.,-100.,-500.])] {
        aim.set(intent).unwrap();
        for _ in 0..180 {aim.advance_pose_for(kind,[0.;3],[0.2,0.1,-0.1],0.1).unwrap();limits(kind,&aim);}
    }
    // The bounded FV interval uses the long legal forward turn, rather than
    // wrapping through a forbidden rear when the wanted target changes sides.
    aim.yaw=45f32.to_radians();aim.pitch=0.;aim.set(Intent::Hold{yaw:-PI+0.01,pitch:0.}).unwrap();
    let before=aim.yaw;aim.advance_pose_for(kind,[0.;3],[0.;3],0.1).unwrap();assert!(aim.yaw<before);
    assert!((before-aim.yaw-kind.source_aim().unwrap().yaw_rate*0.1).abs()<1e-6);
}

#[test] fn p06t_extended_wt_both_pitch_bounds_follow_actual_yaw_through_rear_transition() {
    let kind=VehicleKind::Wt128;let mut aim=State::new();aim.pitch=source_aim::SourceEnvelope::wt_e100().basic().min;
    aim.set(Intent::Hold{yaw:PI,pitch:-1.}).unwrap();
    for _ in 0..200 {aim.advance_pose_for(kind,[0.;3],[0.;3],0.1).unwrap();limits(kind,&aim);}
    assert!((aim.yaw.abs()-PI).abs()<1e-5);assert_eq!(aim.pitch.to_bits(),0xbdfa35dd);
    aim.set(Intent::Hold{yaw:0.,pitch:1.}).unwrap();
    for _ in 0..200 {aim.advance_pose_for(kind,[0.;3],[0.;3],0.1).unwrap();limits(kind,&aim);}
    assert_eq!(aim.pitch.to_bits(),0x3db2b8c2);
    for deg in [138f32,140.5,143.,180.] {
        let p=pitch_limits_for(kind,deg.to_radians()).unwrap();assert!(p.0>=(-15f32).to_radians()-1e-6&&p.0<=(-7f32).to_radians()+1e-6);
        assert!((p.1-5f32.to_radians()).abs()<1e-6);
    }
}

#[test] fn p06t_extended_flat_tilted_unreachable_and_degenerate_solver_exits_are_bounded() {
    for kind in [VehicleKind::Wt128,VehicleKind::Fv183] {
        for direction in [[0.;3],[0.7,-0.13,0.09],[-2.1,0.25,-0.15]] {
            for point in [[30.,500.,70.],[-300.,-500.,-400.],[0.,0.,0.],[0.,900000.,1.]] {
                let (yaw,pitch)=source_target_angles(kind,[0.;3],direction,point,0.,0.,830.,9.81).unwrap();
                let aim=State{yaw,pitch,intent:Intent::Hold{yaw,pitch}};limits(kind,&aim);
                for shell in shells::profile(kind.mount()).shots {
                    let mut actual=State::new();actual.set(Intent::Point(point)).unwrap();
                    for _ in 0..120 {actual.advance_pose_for_selected(kind,[0.;3],direction,0.1,shell,healthy(kind)).unwrap();limits(kind,&actual);}
                }
            }
        }
    }
}

#[test] fn p06t_extended_selected_source_shell_speed_and_caps_change_real_controller_output() {
    let kind=VehicleKind::Wt128;let shots=shells::profile(kind.mount()).shots;let mut results=Vec::new();
    for shell in [shots[0],shots[1]] {
        let mut aim=State::new();aim.set(Intent::Point([0.,2.,400.])).unwrap();
        for _ in 0..150 {aim.advance_pose_for_selected(kind,[0.;3],[0.;3],0.1,shell,healthy(kind)).unwrap();}
        results.push(aim.pitch);limits(kind,&aim);
    }
    // An independent low-arc equation is stricter than a guessed minimum
    // difference: at this range the source speed difference yields ~0.00049rad.
    let spec=kind.aim();let origin_y=spec.pivot[1]+spec.gun[1];let origin_z=spec.pivot[2]+spec.gun[2];
    let distance=f64::from(400.-origin_z);let height=f64::from(2.-origin_y);
    for(index,shell)in[shots[0],shots[1]].into_iter().enumerate(){
        let v2=shell.raw_speed_mps.powi(2);let g=shell.raw_gravity_mps2;
        let discriminant=v2*v2-g*(g*distance*distance+2.*height*v2);
        let expected=-((v2-discriminant.sqrt())/(g*distance)).atan();
        assert!((f64::from(results[index])-expected).abs()<0.000002,"source low arc {index}");
    }
    assert!(results[0]<results[1],"1200m/s AP needs higher arc than1500m/s APCR");
    let mut initial=State::new();initial.set(Intent::Hold{yaw:1.,pitch:-0.2}).unwrap();
    let mut full=initial.clone();full.advance_pose_for_selected(kind,[0.;3],[0.;3],0.1,shots[0],healthy(kind)).unwrap();
    let mut caps=healthy(kind);caps.turret_scale=0.;let mut locked=initial.clone();
    locked.advance_pose_for_selected(kind,[0.;3],[0.;3],0.1,shots[0],caps).unwrap();assert_eq!(locked.yaw,0.);assert_eq!(locked.pitch,full.pitch);
    caps=healthy(kind);caps.aim_speed_scale=0.5;let mut slowed=initial.clone();
    slowed.advance_pose_for_selected(kind,[0.;3],[0.;3],0.1,shots[0],caps).unwrap();
    assert!((slowed.yaw-full.yaw*0.5).abs()<1e-6);assert!((slowed.pitch-full.pitch*0.5).abs()<1e-6);
}

#[test] fn p06t_extended_corrupt_state_inputs_or_mount_fail_before_any_aim_mutation() {
    let kind=VehicleKind::Fv183;let shell=shells::profile(kind.mount()).shots[0];
    for (yaw,pitch) in [(1.,0.),(0.,-1.),(f32::NAN,0.),(0.,f32::INFINITY)] {
        let mut aim=State::new();aim.yaw=yaw;aim.pitch=pitch;let bits=[aim.yaw.to_bits(),aim.pitch.to_bits()];
        assert!(aim.advance_pose_for_selected(kind,[0.;3],[0.;3],0.1,shell,healthy(kind)).is_err());
        assert_eq!([aim.yaw.to_bits(),aim.pitch.to_bits()],bits);
    }
    let mut aim=State::new();let before=aim.clone();
    assert!(aim.advance_pose_for_selected(kind,[0.;3],[0.;3],0.1,shells::profile(VehicleKind::Ms1.mount()).shots[0],healthy(kind)).is_err());assert_eq!(aim,before);
    let mut caps=healthy(kind);caps.aim_speed_scale=f32::NAN;
    assert!(aim.advance_pose_for_selected(kind,[0.;3],[0.;3],0.1,shell,caps).is_err());assert_eq!(aim,before);
    assert!(aim.advance_pose_for(kind,[0.;3],[0.;3],-0.1).is_err());assert_eq!(aim,before);
}
