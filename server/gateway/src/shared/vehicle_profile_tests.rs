//! Runtime profile isolation; native display/input remains a separate owner gate.
use super::VehicleKind;
use super::super::{aim,ap,geometry,impact_wire,materials,model,projectile,terrain_wire,wire};
use crate::{battle091::fire,map_profile091::MapId};
use std::{sync::Arc,time::{Duration,Instant}};

fn world(now:Instant,kind:VehicleKind)->model::World {
    let mut w=model::World::new_for_vehicle(71,now,MapId::Prohorovka,kind).unwrap();
    for slot in 0..2 { w.attach(model::Identity { account:format!("owned-is7-{slot}"),
        database:slot+1,name:format!("is7-{slot}") },slot as u32+1).unwrap(); }
    w.start(now).unwrap();w.set_ready(0,1).unwrap();w.set_ready(1,2).unwrap();w
}

#[test] fn is7_actor_descriptor_health_binding_and_mixed_kind_rejection() {
    let now=Instant::now();let w=world(now,VehicleKind::Is7);
    for slot in 0..2 {
        let a=&w.actors[slot];assert_eq!(a.vehicle_kind(),VehicleKind::Is7);
        assert_eq!((a.health,a.fire.ammo()),(2150,30));
        let create=wire::create_vehicle(&w,slot).unwrap();
        assert!(create.windows(15).any(|v|v==VehicleKind::Is7.descriptor()));
        assert_eq!(&create[43..45],&2150i16.to_le_bytes());
        let binding=wire::binding(&w,slot,now).unwrap();
        let rows=&binding[binding.len()-54..binding.len()-21];
        for (i,(id,count)) in [(14602u32,30u16),(14858,0),(15114,0)].into_iter().enumerate() {
            assert_eq!(&rows[i*11..i*11+2],&[0x13,0x44]);
            assert_eq!(&rows[i*11+2..i*11+6],&id.to_le_bytes());
            assert_eq!(&rows[i*11+6..i*11+8],&count.to_le_bytes());
        }
        assert_eq!(&binding[binding.len()-4..],&13.7f32.to_le_bytes());
    }
    let mut mixed=w.clone();mixed.actors[1]=world(now,VehicleKind::Ms1).actors[1].clone();
    assert!(wire::roster(&mixed).is_err());assert!(wire::create_vehicle(&mixed,1).is_err());
    let mut fresh=model::World::new_for_vehicle(72,now,MapId::Prohorovka,VehicleKind::Is7).unwrap();
    assert!(fresh.bind_geometry(Arc::new(geometry::tests::bundle())).is_err());
    assert!(fresh.bind_destructible_test_lab().is_err());
}

#[test] fn is7_runtime_reload_boundary_rejoin_and_frozen_projectile() {
    let now=Instant::now();let mut w=world(now,VehicleKind::Is7);
    w.actors[0].position=[0.;3];
    let shot=[model::Command::Fire(fire::Command::Shoot)];
    assert_eq!(w.apply(0,1,&shot,now).unwrap(),vec![fire::Outcome::AcceptedShot{ammo_remaining:29}]);
    let p=w.projectiles[0];assert_eq!(p.vehicle_kind,VehicleKind::Is7);
    for (actual,expected) in p.origin.into_iter().zip([-0.046449,1.8522,1.546217]) {
        assert!((actual-expected).abs()<2e-6);
    }
    assert!((p.velocity.iter().map(|v|v*v).sum::<f32>().sqrt()-720.).abs()<0.001);
    assert!((p.gravity-6.2784).abs()<1e-5);
    let start=wire::tracer_start(&p).unwrap();assert_eq!(start[10],14);
    assert_eq!(start.len(),43);
    let deadline=now+Duration::from_secs_f32(13.7);
    assert_eq!(w.actors[0].fire.reload_until(),Some(deadline));
    assert_eq!(w.apply(0,1,&shot,deadline-Duration::from_nanos(1)).unwrap(),vec![fire::Outcome::RejectedReload]);
    let identity=w.actors[0].identity.clone();w.actors[0].health=1660;
    w.detach(1).unwrap();assert_eq!(w.attach(identity,3).unwrap(),0);w.set_ready(0,3).unwrap();
    assert_eq!((w.actors[0].health,w.actors[0].fire.ammo()),(1660,29));
    assert_eq!(w.actors[0].fire.reload_until(),Some(deadline));
    assert_eq!(w.apply(0,3,&shot,deadline).unwrap(),vec![fire::Outcome::AcceptedShot{ammo_remaining:28}]);
    assert_eq!(w.projectiles[0],p);
    assert!(projectile::Projectile::launch(61,0,&w.actors[0],now).is_err());
}

#[test] fn is7_sixty_shots_and_ms1_forty_remain_distinct_bounded_lifecycles() {
    let now=Instant::now();
    for (kind,count,interval) in [(VehicleKind::Ms1,20,3),(VehicleKind::Is7,30,14)] {
        let mut w=world(now,kind);
        for round in 0..count { for slot in 0..2 {
            let t=now+Duration::from_secs(round*interval);
            let outcomes=w.apply(slot,slot as u32+1,&[model::Command::Fire(fire::Command::Shoot)],t).unwrap();
            assert!(matches!(outcomes.as_slice(),[fire::Outcome::AcceptedShot{..}]));
        } }
        assert_eq!(w.latest_shot() as usize,kind.battle_shot_limit());
        assert_eq!(w.projectiles.len(),kind.battle_shot_limit());
        for slot in 0..2 {
            assert_eq!(w.actors[slot].fire.ammo(),0);
            let outcomes=w.apply(slot,slot as u32+1,&[model::Command::Fire(fire::Command::Shoot)],now+Duration::from_secs(500)).unwrap();
            assert_eq!(outcomes,vec![fire::Outcome::RejectedNoAmmo]);
        }
        assert_eq!(w.latest_shot() as usize,kind.battle_shot_limit());
    }
}

fn plate(armor:f32)->materials::MaterialFacts {
    materials::MaterialFacts { component:materials::Component::Hull,name:"armor_1".into(),kind:1,
        source_class:materials::SourceClass::ArmorDescriptor,
        profile_revision:materials::profile_revision(VehicleKind::Is7).into(),
        effective:Some(materials::EffectiveMaterial {kind:1,armor:Some(armor),extra_is_none:true,
            vehicle_damage_factor:1.,use_armor_homogenization:true,use_hit_angle:true,
            use_antifragmentation_lining:true,may_ricochet:true,collide_once_only:false,
            damage_kind:0,chance_to_hit_by_projectile:1.,chance_to_hit_by_explosion:1.,continue_trace_if_no_hit:true}) }
}
fn resolve(m:&materials::MaterialFacts,distance:f64)->ap::Resolution {
    ap::resolve_for(VehicleKind::Is7,ap::Input {material:m,segment_direction:[0.,0.,1.],
        winding_normal:[0.,0.,-1.],distance}).unwrap()
}

#[test] fn is7_ap_uses_s70_power_damage_and_refuses_mixed_or_special_materials() {
    let mut m=plate(240.);
    assert_eq!(resolve(&m,100.).damage,490);
    let far=resolve(&m,500.);assert_eq!(far.nominal_power,Some(240.));
    assert_eq!(far.outcome,ap::Outcome::NotPierced);assert_eq!(far.damage,0);
    assert_eq!(resolve(&m,720.).nominal_power,Some(0.));
    m.profile_revision=materials::profile_revision(VehicleKind::Ms1).into();
    assert_eq!(resolve(&m,100.).outcome,ap::Outcome::Unsupported(ap::Reason::MaterialRevision));
    m=plate(100.);m.effective.as_mut().unwrap().vehicle_damage_factor=0.;
    assert_eq!(resolve(&m,100.).outcome,ap::Outcome::Unsupported(ap::Reason::VehicleDamageFactor));
    m=plate(0.);assert_eq!(resolve(&m,100.).outcome,ap::Outcome::Unsupported(ap::Reason::ZeroArmor));
    m=plate(100.);m.kind=16;m.name="armor_16".into();m.effective.as_mut().unwrap().kind=16;
    assert_eq!(resolve(&m,100.).damage,490);
    m.kind=17;m.name="armor_17".into();m.effective.as_mut().unwrap().kind=17;
    assert!(ap::resolve_for(VehicleKind::Is7,ap::Input {material:&m,segment_direction:[0.,0.,1.],
        winding_normal:[0.,0.,-1.],distance:100.}).is_err());
}

#[test] fn is7_native_effect_health_and_angle_encodings_keep_profile_bounds() {
    let kind=VehicleKind::Is7;
    assert_eq!(impact_wire::owner_health_for(kind,2150).unwrap(),[0x13,0x3f,0x66,0x08,1]);
    assert!(impact_wire::owner_health(2150).is_err());
    assert!(impact_wire::health_changed_for(kind,1,2151,0).is_err());
    let health=impact_wire::health_changed_for(kind,1,1660,0).unwrap();
    assert_eq!(&health[5..8],&[0xa1,0x7c,0x06]);
    let effect=impact_wire::show_damage_for(kind,0,1,1,[[0.;3],[1.;3]],
        [0.,0.5,0.5],[1.,0.5,0.5],impact_wire::ShotOutcome::Pierced).unwrap();
    assert_eq!(&effect[23..],&[14,0x13]);
    let ground=terrain_wire::explode_material_for(kind,60,[0.;3],[0.,0.,1.],0).unwrap();
    assert_eq!(ground[7],14);assert!(terrain_wire::explode(60,[0.;3],[0.,0.,1.]).is_err());
    let mut state=aim::State::new();state.pitch=kind.aim().min_pitch;
    assert_eq!(wire::packed_angles_for(kind,&state).unwrap(),0x8000);
    state.pitch=kind.aim().max_pitch;assert_eq!(wire::packed_angles_for(kind,&state).unwrap(),0x803f);
    state.pitch=aim::MIN_PITCH;assert!(wire::packed_angles_for(kind,&state).is_err());
    assert!(wire::ammo_count_for(kind,31).is_err());assert!(wire::reload_for(kind,0,13.71).is_err());
}
