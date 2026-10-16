//! Trace invariants use an actual computed synthetic plate query and source
//! material catalogue. Splash additionally requeries the real original mesh.
use super::*;
use super::super::model::{self,Contact,Actor};
use crate::p06t_shells091::PROFILES;
use std::time::Instant;

fn source_contact(index:usize,heavy:bool)->(Trace,Contact,crate::p06t_damage::Resolution,Actor){
    let now=Instant::now();let world=model::tests::world(now);
    let mut shooter=if heavy {
        let mut w=model::World::new_for_vehicle(123,now,crate::map_profile091::MapId::Karelia,VehicleKind::Is7).unwrap();
        w.attach(world.actors[0].identity.clone(),999).unwrap();w.actors[0].clone()
    }else{world.actors[0].clone()};
    shooter.position=[-10.,0.,0.];let shell=PROFILES[usize::from(heavy)].shots[index];
    let mut target=world.actors[1].clone();target.position=[0.;3];target.direction=[0.;3];target.aim.yaw=0.;target.aim.pitch=0.;
    let mut trace=Trace::new();trace.configure_roster(3).unwrap();
    trace.bind_actor(0,shooter.vehicle_kind()).unwrap();trace.bind_actor(1,VehicleKind::Ms1).unwrap();trace.bind_actor(2,VehicleKind::Ms1).unwrap();
    trace.admission_shell(123,1,1000,0,2,1,shell).unwrap();
    let projectile=Projectile::launch_shell_for_limit(1,0,&shooter,now,trace.shot_limit(),shell).unwrap();
    trace.launch(123,&projectile,1000).unwrap();
    let tag=super::super::geometry::transform_revision(target.position,target.direction,[target.aim.yaw,target.aim.pitch],1,1001);
    let mesh=collision::Mesh::new(vec![[0.,-1.,-1.],[0.,1.,-1.],[0.,0.,1.]],
        vec![collision::Triangle{triangle_id:7,a:0,b:1,c:2,mesh:"Hull".into(),group:"p06t-trace-synthetic-contract".into(),material:"armor_1".into()}],
        super::super::geometry::SOURCE_REVISION,tag.clone()).unwrap();
    let(start,end)=([-1.,0.,0.],[3.,0.,0.]);trace.segment(123,1,1001,1000,start,end).unwrap();
    let bundle=super::super::geometry::tests::bundle();
    let(hits,facts)=trace.collision_query_classified(123,1,1001,&mesh,bundle.materials()).unwrap();
    let triangle=hits[0].clone();let endpoint=std::array::from_fn(|i|start[i]+triangle.t*(end[i]-start[i]));
    let contact=Contact{shot:1,target_slot:1,tick:1001,segment_start:start,segment_end:end,segment_seconds:0.1,endpoint,
        target_position:target.position,target_direction:target.direction,target_aim:[target.aim.yaw,target.aim.pitch],triangle,
        geometry_revision:mesh.geometry_revision().into(),transform_revision:tag,material_facts:facts.unwrap()};
    let chord=std::array::from_fn(|i|end[i]-start[i]);let distance=(0..3).map(|i|(f64::from(endpoint[i])-f64::from(projectile.origin[i])).powi(2)).sum::<f64>().sqrt();
    let plate=plate_for(VehicleKind::Ms1,&contact.material_facts,chord,contact.triangle.normal,distance).unwrap();
    let result=crate::p06t_damage::resolve_direct(crate::p06t_damage::DirectInput{shell,plate,chord,winding_normal:contact.triangle.normal,distance_m:distance}).unwrap();
    (trace,contact,result,target)
}
#[test]fn p06t_trace_selected_source_launch_cannot_fall_back_to_old_ap_or_change_shell(){
    let now=Instant::now();let world=model::tests::world(now);let heat=PROFILES[0].shots[1];
    let mut trace=Trace::new();trace.admission_shell(123,1,1000,0,2,1,heat).unwrap();let baseline=trace.clone();
    let old=Projectile::launch(1,0,&world.actors[0],now).unwrap();assert!(trace.launch(123,&old,1000).is_err());assert_eq!(trace,baseline);
    let wrong=Projectile::launch_shell_for_limit(1,0,&world.actors[0],now,192,PROFILES[0].shots[2]).unwrap();
    assert!(trace.launch(123,&wrong,1000).is_err());assert_eq!(trace,baseline);
    let right=Projectile::launch_shell_for_limit(1,0,&world.actors[0],now,192,heat).unwrap();trace.launch(123,&right,1000).unwrap();
    let mut legacy=Trace::new();legacy.admission(123,1,1000,0,2,1).unwrap();assert!(legacy.launch(123,&right,1000).is_err());
    let mut bad=Trace::new();assert!(bad.admission_shell(123,1,1000,0,2,1,PROFILES[1].shots[1]).is_err());assert!(bad.events().is_empty());
}
#[test]fn p06t_trace_mixed_recomputes_selected_source_plate_and_hp_before_terminal(){
    for index in 0..3 {
        let(mut trace,c,r,_)=source_contact(index,false);let after=90i16.saturating_sub(r.damage_hp as i16).max(0);
        trace.mixed_resolution(123,1,1001,0,1,&c,&r,90,after).unwrap();
        let before=trace.clone();assert!(trace.mixed_resolution(123,1,1001,0,1,&c,&r,90,after).is_err());assert_eq!(trace,before);
        trace.terminal(123,1,1001,TerminalReason::TestLabMixedImpact).unwrap();
        assert!(matches!(trace.events().iter().rev().nth(1),Some(Event::MixedResolution{shell,..})if *shell==PROFILES[0].shots[index]));
    }
}
#[test]fn p06t_trace_rejects_forged_contact_pose_material_normal_damage_and_hp_atomically(){
    let(base,c,r,_)=source_contact(1,false);
    for which in 0..7 {
        let mut contact=c.clone();match which{0=>contact.endpoint[0]+=0.1,1=>contact.segment_start[0]+=0.1,
            2=>contact.target_position[0]+=0.1,3=>contact.triangle.normal[0]*=-1.,4=>contact.triangle.triangle_id+=1,
            5=>contact.material_facts.profile_revision="wrong".into(),_=>contact.target_aim[0]+=0.1}
        let mut trace=base.clone();assert!(trace.mixed_resolution(123,1,1001,0,1,&contact,&r,90,60).is_err());assert_eq!(trace,base);
    }
    let mut bad=r;bad.damage_hp+=1;let mut trace=base.clone();assert!(trace.mixed_resolution(123,1,1001,0,1,&c,&bad,90,59).is_err());assert_eq!(trace,base);
    assert!(trace.mixed_resolution(123,1,1001,0,1,&c,&r,90,61).is_err());assert_eq!(trace,base);
    let old=ap::resolve(ap::Input{material:&c.material_facts,segment_direction:[4.,0.,0.],winding_normal:c.triangle.normal,distance:10.}).unwrap();
    assert!(trace.ap_resolution(123,1,1001,0,1,&old,90,60).is_err());assert_eq!(trace,base);
}
#[test]fn p06t_trace_splash_requeries_real_mesh_los_and_blocks_forged_bool_or_center(){
    let(mut trace,c,r,mut actor)=source_contact(2,true);trace.mixed_resolution(123,1,1001,0,1,&c,&r,90,0).unwrap();
    actor.position=[0.;3];let center=c.endpoint;let shell=PROFILES[1].shots[2];let radius=shell.explosion_radius_m.unwrap();
    let bundle=super::super::geometry::tests::bundle();
    let contact=bundle.explosion_contact(&actor,center,radius as f32,1,2,1001).unwrap().unwrap();
    let chord=std::array::from_fn(|i|contact.segment_end[i]-contact.segment_start[i]);
    let distance=(0..3).map(|i|(f64::from(contact.endpoint[i])-f64::from(center[i])).powi(2)).sum::<f64>().sqrt();
    let plate=plate_for(VehicleKind::Ms1,&contact.material_facts,chord,contact.triangle.normal,distance).unwrap();assert!(plate.ordinary);
    let terrain=terrain::tests::fixture(-10.,10.,3,vec![-10.;9]);assert!(splash_los(&terrain,center,contact.endpoint,&[]).unwrap());
    let result=crate::p06t_damage::resolve_splash(shell,&[crate::p06t_damage::SplashTarget{slot:2,distance_m:distance,armor_mm:plate.armor_mm.unwrap(),los_clear:true}]).unwrap()[0];
    assert!(result.damage_hp>0);let after=90i16.saturating_sub(result.damage_hp as i16).max(0);
    let baseline=trace.clone();let mut wrong=result;wrong.damage_hp=0;
    assert!(trace.splash_resolution(123,1,1001,0,2,&contact,center,&wrong,90,90,&terrain,&bundle,&actor).is_err());assert_eq!(trace,baseline);
    let mut wrong_center=center;wrong_center[0]+=0.001;
    assert!(trace.splash_resolution(123,1,1001,0,2,&contact,wrong_center,&result,90,after,&terrain,&bundle,&actor).is_err());assert_eq!(trace,baseline);
    trace.splash_resolution(123,1,1001,0,2,&contact,center,&result,90,after,&terrain,&bundle,&actor).unwrap();
    let good=trace.clone();assert!(trace.splash_resolution(123,1,1001,0,2,&contact,center,&result,90,after,&terrain,&bundle,&actor).is_err());assert_eq!(trace,good);
    trace.terminal(123,1,1001,TerminalReason::TestLabMixedImpact).unwrap();
}
#[test]fn p06t_splash_los_uses_true_terrain_and_only_explicit_one_mm_self_contact(){
    let t=terrain::tests::fixture(-10.,10.,3,vec![0.;9]);
    assert!(splash_los(&t,[0.,0.,0.],[0.,1.,0.],&[]).unwrap());
    assert!(!splash_los(&t,[0.,1.,0.],[0.,-1.,0.],&[]).unwrap());
    assert!(splash_los(&t,[0.,0.,0.],[0.,0.0005,0.],&[]).unwrap());
    assert!(splash_los(&t,[0.;3],[f32::NAN,0.,0.],&[]).is_err());
}
#[test]fn p06t_fragile_uses_selected_source_damage_and_keeps_old_ap_wrapper(){
    let mut catalog=(*fragiles::tests::catalog()).clone();catalog.objects[0].health=600;
    let mut legacy=fragiles::State::new(std::sync::Arc::new(catalog.clone()));
    let mut typed=fragiles::State::new(std::sync::Arc::new(catalog));
    let hit=terrain::Hit{surface:terrain::Surface::StaticObstacle{instance_id:1512,material_kind:73},triangle_id:88716,t:0.5,point:[0.;3],normal:[0.,1.,0.]};
    assert_eq!(legacy.contact_for(VehicleKind::Ms1,1,0,1001,hit).unwrap().unwrap().health_after,570);
    assert_eq!(typed.contact_shell_for(VehicleKind::Ms1,PROFILES[0].shots[2],1,0,1001,hit).unwrap().unwrap().health_after,564);
    let before=typed.clone();assert!(typed.contact_shell_for(VehicleKind::Ms1,PROFILES[1].shots[2],2,0,1002,hit).is_err());assert_eq!(typed,before);
}
