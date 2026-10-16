use super::*;
use crate::{p06t_device_caps::{Device,Profile},p06t_device_state::{self as devices,State as Devices},p06t_lab_proxy::Target,p06t_shells091::{self as source,Mount}};
fn healthy(kind:VehicleKind)->devices::Capabilities {Devices::new(Profile::ALL[kind.index()]).unwrap().capabilities()}
fn wound(state:&mut Devices,target:Target) {
    state.apply_hits(&[devices::ModuleHit{cause:devices::Cause{shot:1,attacker_slot:1},ordinal:0,at_ms:0,target,
        shell:source::profile(Mount::Is7Stock).shots[0],ignition_roll:0.9}],devices::Health{hp:90,max_hp:90,terminal:false}).unwrap();
}
#[test] fn p06t_selected_ap_all_one_caps_preserve_legacy_angles_bit_for_bit() {
    for kind in VehicleKind::ALL {
        for direction in [[0.;3],[0.7,-0.13,0.09],[-2.1,0.25,-0.15]] {
            for point in [[30.,5.,70.],[450.,-20.,310.],[-300.,60.,-400.]] {
                let mut old=State::new();old.set(Intent::Point(point)).unwrap();let mut selected=old.clone();
                old.yaw=0.6;selected.yaw=0.6;
                for step in 0..100 {
                    let dt=[0.,0.05,0.1,0.2][step%4];
                    old.advance_pose_for(kind,[0.;3],direction,dt).unwrap();
                    selected.advance_pose_for_selected(kind,[0.;3],direction,dt,source::profile(kind.mount()).shots[0],healthy(kind)).unwrap();
                    assert_eq!([old.yaw.to_bits(),old.pitch.to_bits()],[selected.yaw.to_bits(),selected.pitch.to_bits()]);
                }
            }
        }
    }
}
#[test] fn p06t_selected_heat_uses_its_slower_source_speed_and_reaches_real_world_point() {
    let kind=VehicleKind::Ms1;let position=[37.,21.,-105.];let point=[37.,21.,195.];
    for direction in [[0.;3],[0.25,-0.1,0.07]] {
        let mut results=Vec::new();
        for shot in [0,1] {
            let shell=source::profile(Mount::Ms1Stock).shots[shot];let mut aim=State::new();aim.set(Intent::Point(point)).unwrap();
            for _ in 0..100 {aim.advance_pose_for_selected(kind,position,direction,0.1,shell,healthy(kind)).unwrap();}
            let (origin,velocity)=shot_geometry_pose_for(kind,position,direction,aim.yaw,aim.pitch,shell.raw_speed_mps as f32);
            let horizontal2=velocity[0]*velocity[0]+velocity[2]*velocity[2];
            let t=((point[0]-origin[0])*velocity[0]+(point[2]-origin[2])*velocity[2])/horizontal2;
            let endpoint=[origin[0]+velocity[0]*t,origin[1]+velocity[1]*t-0.5*shell.raw_gravity_mps2 as f32*t*t,origin[2]+velocity[2]*t];
            assert!((0..3).map(|i|(endpoint[i]-point[i]).powi(2)).sum::<f32>().sqrt()<0.003);
            results.push(aim.pitch);
        }
        assert!(results[1]<results[0]-0.003,"HEAT must require a higher arc than stock AP");
    }
}
#[test] fn p06t_turret_and_combined_gunner_wound_change_actual_aim_rates_and_gun_state() {
    let kind=VehicleKind::Ms1;let shell=source::profile(kind.mount()).shots[0];let intent=Intent::Hold{yaw:1.,pitch:-0.3};
    let mut initial=State::new();initial.set(intent).unwrap();
    let mut normal=initial.clone();normal.advance_pose_for_selected(kind,[0.;3],[0.;3],0.1,shell,healthy(kind)).unwrap();
    let mut turret=Devices::new(Profile::Ms1).unwrap();wound(&mut turret,Target::Device(Device::TurretRotator));
    let mut stopped=initial.clone();stopped.advance_pose_for_selected(kind,[0.;3],[0.;3],0.1,shell,turret.capabilities()).unwrap();
    assert_eq!(stopped.yaw.to_bits(),0f32.to_bits());assert_eq!(stopped.pitch,normal.pitch);
    let mut gunner=Devices::new(Profile::Ms1).unwrap();wound(&mut gunner,Target::Seat(0));
    let mut slowed=initial.clone();slowed.advance_pose_for_selected(kind,[0.;3],[0.;3],0.1,shell,gunner.capabilities()).unwrap();
    assert!((slowed.yaw-normal.yaw*0.5).abs()<1e-6);assert!((slowed.pitch-normal.pitch*0.5).abs()<1e-6);
    let mut gun=Devices::new(Profile::Ms1).unwrap();wound(&mut gun,Target::Device(Device::Gun));assert!(!gun.capabilities().can_fire);
}
#[test] fn p06t_selected_aim_rejects_wrong_mount_or_invalid_caps_atomically() {
    let mut aim=State::new();aim.set(Intent::Point([0.,0.,100.])).unwrap();let before=aim.clone();
    assert!(aim.advance_pose_for_selected(VehicleKind::Ms1,[0.;3],[0.;3],0.1,source::profile(Mount::Is7Stock).shots[0],healthy(VehicleKind::Ms1)).is_err());assert_eq!(aim,before);
    let mut caps=healthy(VehicleKind::Ms1);caps.turret_scale=f32::NAN;
    assert!(aim.advance_pose_for_selected(VehicleKind::Ms1,[0.;3],[0.;3],0.1,source::profile(Mount::Ms1Stock).shots[0],caps).is_err());assert_eq!(aim,before);
}
