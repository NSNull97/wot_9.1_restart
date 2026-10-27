//! Source-bound exterior queries, not synthetic AABB collision acceptance.
use super::*;
use super::super::{collision,model};

fn bundle(kind:VehicleKind)->Bundle {
    let root=std::path::PathBuf::from(std::env::var_os("WOT091_ROOT").unwrap_or_else(||"D:/WoT_9.1_Server".into()));
    let relative=match kind {
        VehicleKind::Ms1=>"local/evidence/20261010-p06j-contact-materials-01/ms1-contact.json".into(),
        VehicleKind::Is7=>"local/evidence/20261013-p03m-is7-01/geometry-surface01/is7-contact.json".into(),
        _=>format!("local/evidence/20261016-p04m-source-import01/{}-stock.json",kind.label()),
    };
    Bundle::load(&root.join("local"),&root.join(relative)).unwrap()
}
fn actor(kind:VehicleKind)->Actor {
    let mut w=model::World::new_for_vehicle(6911,std::time::Instant::now(),crate::map_profile091::MapId::Prohorovka,kind).unwrap();
    let slot=w.attach(model::Identity{account:"p06t-source-geometry".into(),database:6911,name:"source_geometry".into()},6911).unwrap();
    let mut actor=w.actors[slot].clone();actor.position=[37.,21.,-105.];actor.direction=[0.7,-0.13,0.09];
    actor.aim.yaw=-0.47;actor.aim.pitch=0.11;actor
}
fn world(b:&Bundle,a:&Actor,index:usize,p:[f32;3])->[f32;3] {
    let local=b.component_point(index,p,a.aim.yaw,a.aim.pitch);let rotated=pose::rotate(local,a.direction);
    std::array::from_fn(|i|a.position[i]+rotated[i])
}
fn midpoint(b:&Bundle)->[f32;3] {std::array::from_fn(|i|(b.bounds[0][0][i]+b.bounds[0][1][i])*0.5)}
fn center(b:&Bundle,a:&Actor,axis:usize,sign:f32)->[f32;3] {
    let mut p=midpoint(b);p[axis]+=sign*((b.bounds[0][1][axis]-b.bounds[0][0][axis])*0.5+1.);
    // Avoid exact source shared-edge symmetry; this is an explosion position,
    // never an authored hit point or a substitute shape for the source mesh.
    p[1]+=0.073;p[2]+=0.041;world(b,a,0,p)
}
fn distance(a:[f32;3],b:[f32;3])->f64 {(0..3).map(|i|(f64::from(a[i])-f64::from(b[i])).powi(2)).sum::<f64>().sqrt()}

#[test]
fn p06t_geometry_all_five_explosion_contacts_match_first_actual_source_triangles() {
    let mut checked=0;
    for kind in VehicleKind::ALL {
        let b=bundle(kind);let mut a=actor(kind);
        for posed in [false,true] {
            if !posed {a.direction=[0.;3];a.aim.yaw=0.;a.aim.pitch=0.;}
            else {a=actor(kind);}
            for (axis,sign) in [(0,-1.),(0,1.),(2,-1.),(2,1.)] {
                let c=center(&b,&a,axis,sign);let target=world(&b,&a,0,midpoint(&b));
                let mesh=b.world_mesh(&a,5,1234).unwrap();
                // Independently query the shorter ray ending at source hull
                // center; do not reuse the helper's extended endpoint policy.
                let reference=collision::query(&mesh,c,target).unwrap().into_iter().next().unwrap();
                let expected=std::array::from_fn(|i|c[i]+reference.t*(target[i]-c[i]));
                let hit=b.explosion_contact(&a,c,5.05,960,5,1234).unwrap().unwrap();
                assert_eq!((hit.triangle.triangle_id,&hit.triangle.mesh,&hit.triangle.material),
                    (reference.triangle_id,&reference.mesh,&reference.material),"{} posed={posed}",kind.label());
                assert!(distance(hit.endpoint,expected)<0.0002);
                assert!(distance(c,hit.endpoint)<=5.05);
                assert_eq!(hit.geometry_revision,b.geometry_revision());assert_eq!(hit.transform_revision,mesh.transform_revision());
                assert_eq!(hit.material_facts,b.materials.lookup(&hit.triangle.mesh,&hit.triangle.material).unwrap());
                assert_eq!((hit.shot,hit.target_slot,hit.tick,hit.segment_seconds),(960,5,1234,0.));
                assert_eq!(b.explosion_contact(&a,c,5.05,960,5,1234).unwrap().unwrap(),hit);
                let actual=collision::query(&mesh,hit.segment_start,hit.segment_end).unwrap().remove(0);
                assert_eq!(actual,hit.triangle);checked+=1;
            }
        }
    }
    assert_eq!(checked,40);
}

#[test]
fn p06t_geometry_proxy_starts_at_actual_contact_and_preserves_legacy_wire_segment() {
    let mut recessed=0;let mut checked=0;
    for kind in VehicleKind::ALL {
        let b=bundle(kind);let a=actor(kind);
        for (axis,sign) in [(0,-1.),(0,1.),(2,-1.),(2,1.)] {
            let hit=b.explosion_contact(&a,center(&b,&a,axis,sign),5.05,1,5,1234).unwrap().unwrap();
            let legacy=b.impact_segment(&hit).unwrap();let legacy_bits=[legacy.start.map(f32::to_bits),legacy.end.map(f32::to_bits)];
            let ray=b.proxy_ray(&hit).unwrap();
            let index=match ray.component {materials::Component::Hull=>0,materials::Component::Turret01=>1,_=>2};
            let transformed=world(&b,&a,index,ray.start);
            assert!(distance(transformed,hit.endpoint)<0.0002);
            assert_eq!([ray.bbox_min,ray.bbox_max],b.bounds[index]);
            assert!(!ray.is_empty());
            assert!((0..3).all(|i|ray.end[i]>=ray.bbox_min[i]-0.0002&&ray.end[i]<=ray.bbox_max[i]+0.0002));
            assert!((0..3).any(|i|(ray.end[i]-ray.bbox_min[i]).abs()<0.0002||(ray.end[i]-ray.bbox_max[i]).abs()<0.0002));
            let actual_direction=subtract(hit.segment_end,hit.segment_start);
            let local_direction=b.inverse_component_direction(index,pose::inverse_rotate(actual_direction,a.direction),[a.aim.yaw,a.aim.pitch]);
            assert!((0..3).map(|i|f64::from(ray.end[i]-ray.start[i])*f64::from(local_direction[i])).sum::<f64>()>0.);
            if distance(ray.start,legacy.start)>0.001 {recessed+=1;}
            let after=b.impact_segment(&hit).unwrap();assert_eq!([after.start.map(f32::to_bits),after.end.map(f32::to_bits)],legacy_bits);
            checked+=1;
        }
    }
    assert_eq!(checked,20);assert!(recessed>0,"source geometry must witness why AABB entry cannot be used as contact start");
}

#[test]
fn p06t_geometry_forged_contact_facts_are_rejected_without_mutating_bundle() {
    for kind in VehicleKind::ALL {
        let b=bundle(kind);let a=actor(kind);
        let good=b.explosion_contact(&a,center(&b,&a,0,-1.),5.05,1,5,1234).unwrap().unwrap();
        let expected=b.proxy_ray(&good).unwrap();
        let mut poisons=Vec::new();
        let mut p=good.clone();p.triangle.normal[0]+=0.01;poisons.push(p);
        let mut p=good.clone();p.triangle.t=(p.triangle.t+0.01).min(1.);p.endpoint=std::array::from_fn(|i|p.segment_start[i]+p.triangle.t*(p.segment_end[i]-p.segment_start[i]));poisons.push(p);
        let mut p=good.clone();p.triangle.candidate_index+=1;poisons.push(p);
        let mut p=good.clone();p.triangle.triangle_id+=1;poisons.push(p);
        let mut p=good.clone();p.endpoint[0]+=0.0001;poisons.push(p);
        let mut p=good.clone();p.geometry_revision.push('x');poisons.push(p);
        let mut p=good.clone();p.transform_revision.push('x');poisons.push(p);
        let mut p=good.clone();p.target_position[0]+=1.;poisons.push(p);
        let mut p=good.clone();p.target_aim[0]+=0.1;poisons.push(p);
        let mut p=good.clone();p.material_facts.effective=None;poisons.push(p);
        let mut p=good.clone();p.segment_seconds=f32::NAN;poisons.push(p);
        let mut p=good.clone();p.segment_end=p.segment_start;poisons.push(p);
        let mut p=good.clone();p.shot=0;poisons.push(p);
        let mut p=good.clone();p.target_slot=6;poisons.push(p);
        let mut p=good.clone();p.tick=999;poisons.push(p);
        for poison in poisons {assert!(b.proxy_ray(&poison).is_err(),"{} accepted poisonedcontact",kind.label());}
        assert_eq!(b.proxy_ray(&good).unwrap(),expected);
    }
}

#[test]
fn p06t_geometry_inside_and_zero_direction_centers_still_require_actual_surfaces() {
    for kind in VehicleKind::ALL {
        let b=bundle(kind);let a=actor(kind);let c=world(&b,&a,0,midpoint(&b));
        let hit=b.explosion_contact(&a,c,5.05,1,0,1000).unwrap().unwrap();
        let mesh=b.world_mesh(&a,0,1000).unwrap();let actual=collision::query(&mesh,c,hit.segment_end).unwrap().remove(0);
        assert_eq!(hit.triangle,actual);assert!(distance(c,hit.endpoint)>0.);assert!(distance(c,hit.endpoint)<=5.05);
        let direction=subtract(hit.segment_end,c);let forward=pose::rotate([0.,0.,1.],a.direction);
        assert!(direction.iter().zip(forward).map(|(d,f)|f64::from(*d)*f64::from(f)).sum::<f64>()>0.);
        // A tiny blast entirely inside the surface does not gain an AABB hit.
        assert!(b.explosion_contact(&a,c,0.0001,1,0,1000).unwrap().is_none());
        let outside=center(&b,&a,0,-1.);
        assert!(b.explosion_contact(&a,outside,0.01,1,0,1000).unwrap().is_none());
        for radius in [0.,-1.,f32::NAN,f32::INFINITY,16.01] {assert!(b.explosion_contact(&a,outside,radius,1,0,1000).is_err());}
        for shot in [0,model::MAX_BATTLE_SHOTS as u32+1,u32::MAX] {assert!(b.explosion_contact(&a,outside,5.05,shot,0,1000).is_err());}
        assert!(b.explosion_contact(&a,[f32::NAN,0.,0.],5.05,1,0,1000).is_err());
        assert!(b.explosion_contact(&a,outside,5.05,1,model::MAX_ACTORS,1000).is_err());
        assert!(b.explosion_contact(&a,outside,5.05,1,0,999).is_err());
        let wrong=actor(if kind==VehicleKind::Ms1{VehicleKind::Is7}else{VehicleKind::Ms1});
        assert!(b.explosion_contact(&wrong,outside,5.05,1,0,1000).is_err());
    }
}
