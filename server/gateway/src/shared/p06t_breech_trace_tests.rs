//! The fixture is a real World launch/contact against the original WT mesh.
//! Only the post-query trace is rewound; no material, normal or t is authored.
use super::*;
use super::super::{model::{self,Actor,Contact},geometry};
use std::{sync::Arc,time::Duration};

fn fixture()->(Trace,Contact,crate::p06t_damage::Resolution,Actor,Arc<geometry::Bundle>){
    let(mut world,now)=model::extended::breech_tests::launch31();
    let actor=world.actors[1].clone();let bundle=world.geometry_for(actor.vehicle_kind()).unwrap().clone();
    world.advance(now+Duration::from_millis(2300)).unwrap();
    let contact=world.contacts[0].clone();let model::ImpactOutcome::Mixed(result)=world.impacts[0].outcome.clone()else{panic!("mixed")};
    let mut trace=world.impact;let index=trace.events.iter().position(|e|matches!(e,Event::MixedResolution{shot_id:1,..})).unwrap();
    trace.events.truncate(index);trace.terminal_shots.clear();trace.next_order=trace.events.last().unwrap().order();trace.last_tick=contact.tick;
    assert!(matches!(trace.events.last(),Some(Event::MaterialContact{..})));
    (trace,contact,result,actor,bundle)
}
fn apply(trace:&mut Trace,c:&Contact,r:&crate::p06t_damage::Resolution,a:&Actor,b:&geometry::Bundle)->io::Result<()>{
    trace.mixed_resolution_source(28531,1,c.tick,0,1,c,r,2000,850,b,a)
}

#[test]
fn p06t_breech_trace_requires_source_witness_and_records_one_tagged_result(){
    let(mut trace,c,r,a,b)=fixture();let old=trace.clone();
    assert_eq!(trace.extended_breech_lab_policy(),Some(crate::p06t_damage::UNARMORED_DEVICE_POLICY));
    assert!(trace.mixed_resolution(28531,1,c.tick,0,1,&c,&r,2000,850).is_err());assert_eq!(trace,old);
    apply(&mut trace,&c,&r,&a,&b).unwrap();let once=trace.clone();
    assert!(apply(&mut trace,&c,&r,&a,&b).is_err());assert_eq!(trace,once);
    assert!(matches!(trace.events.last(),Some(Event::MixedResolution{resolution,..})
        if resolution.policy==crate::p06t_damage::UNARMORED_DEVICE_POLICY&&resolution.decision==crate::p06t_damage::Decision::UnarmoredDevice));
    trace.terminal(28531,1,c.tick,TerminalReason::TestLabMixedImpact).unwrap();
    assert_eq!(trace.terminal_shots(),[1]);
}

#[test]
fn p06t_breech_trace_rejects_forged_pose_normal_flags_profile_hp_and_late_anchor_atomically(){
    let(base,c,r,a,b)=fixture();
    for poison in 0..13 {
        let(mut trace,mut contact,mut actor,mut result)=(base.clone(),c.clone(),a.clone(),r);
        match poison {
            0=>contact.triangle.normal[0]=-contact.triangle.normal[0]+0.1,
            1=>contact.endpoint[1]+=0.001,
            2=>contact.material_facts.profile_revision="forged".into(),
            3=>contact.material_facts.effective.as_mut().unwrap().vehicle_damage_factor=0.,
            4=>actor.position[0]+=0.001,
            5=>actor.health-=1,
            6=>actor.aim.pitch+=0.001,
            7=>result.damage_hp-=1,
            8=>{trace.events.push(Event::Segment{order:trace.next_order+1,battle_id:28531,shot_id:1,server_tick:c.tick,
                segment_tick_start:c.tick,segment_tick_end:c.tick,start:c.endpoint,end:[100.,200.,100.],geometry_revision:FLIGHT_ONLY_GEOMETRY_REVISION});trace.next_order+=1;},
            9=>trace.next_order=u32::MAX-1,
            10=>contact.material_facts.kind=25,
            11=>{},
            _=>contact.triangle.group="forged-same-retained-query".into(),
        }
        // Poison the retained records together with their supplied copy. The
        // source requery/closed flags, rather than only copy equality, must
        // reject these cases before any event/HP mutation.
        if [0,2,3,10,12].contains(&poison){
            for event in &mut trace.events{match event{
                Event::MaterialContact{facts,..}=>*facts=contact.material_facts.clone(),
                Event::Intersection{triangle_id,normal,group,..}if *triangle_id==c.triangle.triangle_id=>{
                    *normal=contact.triangle.normal;*group=contact.triangle.group.clone();
                },_=>{},
            }}
        }
        // Substitute a different genuine source bundle for the target.
        let wrong=super::super::profile13_templates::extended_test_resources();
        let bundle=if poison==11{wrong.iter().find(|row|row.kind==VehicleKind::Fv183).unwrap().geometry.as_ref()}else{b.as_ref()};
        let baseline=trace.clone();assert!(apply(&mut trace,&contact,&result,&actor,bundle).is_err(),"poison {poison}");assert_eq!(trace,baseline);
    }
    let mut trace=base.clone();assert!(trace.mixed_resolution_source(28531,1,c.tick,0,1,&c,&r,2000,849,&b,&a).is_err());assert_eq!(trace,base);
}

#[test]
fn p06t_breech_source_flags_are_closed_and_default_policy_stays_unsupported(){
    let(base,c,_,_,_)=fixture();let shell=base.selected_shell(1).flatten().unwrap();
    let chord=std::array::from_fn(|i|c.segment_end[i]-c.segment_start[i]);
    let old=resolve_mixed_for(VehicleKind::Wt128,&c.material_facts,shell,chord,c.triangle.normal,40.,false).unwrap();
    assert_eq!((old.decision,old.damage_hp),(crate::p06t_damage::Decision::Unsupported,0));
    for poison in 0..15 {
        let mut facts=c.material_facts.clone();let e=facts.effective.as_mut().unwrap();
        match poison {0=>e.armor=Some(1.),1=>e.vehicle_damage_factor=0.,2=>e.extra_is_none=true,
            3=>e.damage_kind=0,4=>e.use_hit_angle=false,5=>e.use_armor_homogenization=false,
            6=>e.use_antifragmentation_lining=true,7=>e.may_ricochet=false,8=>e.collide_once_only=true,
            9=>e.chance_to_hit_by_projectile=0.33,10=>e.chance_to_hit_by_explosion=0.33,
            11=>e.continue_trace_if_no_hit=false,12=>facts.component=materials::Component::Turret01,
            13=>facts.source_class=materials::SourceClass::GunVisualMaterial,_=>facts.name="gun".into()}
        assert!(resolve_mixed_for(VehicleKind::Wt128,&facts,shell,chord,c.triangle.normal,40.,true).is_err(),"flags {poison}");
    }
    assert!(resolve_mixed_for(VehicleKind::Fv183,&c.material_facts,shell,chord,c.triangle.normal,40.,true).is_err());
}

#[test]
fn p06t_breech_trace_policy_is_pristine_only_and_failed_enable_does_not_mutate(){
    let mut t=Trace::new();assert!(t.enable_extended_breech_lab().is_err());assert!(!t.extended_breech_lab());
    t.configure_roster(2).unwrap();t.enable_extended_breech_lab().unwrap();let enabled=t.clone();
    assert!(t.enable_extended_breech_lab().is_err());assert_eq!(t,enabled);
    let mut t=Trace::new();t.configure_roster(2).unwrap();t.bind_actor(0,VehicleKind::Wt128).unwrap();let bound=t.clone();
    assert!(t.enable_extended_breech_lab().is_err());assert_eq!(t,bound);
}
