//! Actual shared::model::extended::hit_tests. Real source meshes/resources
//! and World commands;
//! synthetic server-owned airborne poses isolate flight from actual map ground.
//! No authored Contact/MaterialContact/HP result or owned loadout is supplied.
use super::*;
use crate::{p06t_armament091 as arm,p06t_shells091 as shells,p06t_device_state as devices};
use super::super::super::{collision,materials};
use std::f32::consts::{FRAC_PI_2,PI};

#[derive(Clone,Copy,Debug)]enum Surface{OrdinaryHull,Gun25,Breech31}

fn identity(slot:usize)->Identity{Identity{account:format!("p06t-actual-hit-lab-{slot}"),database:28500+slot as i32,name:format!("source-hit{slot}")}}
fn pair(id:u64,now:Instant,source:VehicleKind,target:VehicleKind,shot_index:usize,source_pose:([f32;3],f32),target_yaw:f32)->World{
    let rows=super::super::super::profile13_templates::extended_test_resources();
    let mut world=World::new_for_roster(id,now,crate::map_profile091::MapId::Prohorovka,2).unwrap();
    for row in &rows{world.bind_geometry(row.geometry.clone()).unwrap();}
    world.enable_ap_test_lab().unwrap();world.bind_terrain(rows[0].terrain.clone()).unwrap();
    world.bind_fragiles(rows[0].catalog.0.clone()).unwrap();world.enable_extended_lab().unwrap();
    let shell=shells::profile(source.mount()).shots[shot_index];let mut counts=[0;3];counts[shot_index]=2;
    world.attach_extended_lab(identity(0),1,LabLoadout{kind:source,counts,initial:shell.compact_descr}).unwrap();
    world.attach_extended_lab(identity(1),2,LabLoadout::temporary(target)).unwrap();world.start(now).unwrap();
    // Explicit LAB placement, not source spawns/worker settling/native driving.
    // Real Prohorovka terrain/static BVH remain bound; no fake clear-LOS flag.
    world.rebase_external_spawns([source_pose.0,[0.,200.,0.]]).unwrap();
    for(slot,yaw)in[(0,source_pose.1),(1,target_yaw)]{world.actors[slot].yaw=yaw;world.actors[slot].direction=[yaw,0.,0.];world.set_ready(slot,slot as u32+1).unwrap();}
    assert!(world.actors.iter().all(|actor|actor.owned_loadout.is_none()&&actor.owned_v2.is_none()));
    assert!(world.actors.iter().all(|actor|actor.devices.as_ref().unwrap().policy_revision()==devices::POLICY_V2));
    world
}
fn settle(world:&mut World,point:[f32;3],now:Instant){
    world.apply(0,1,&[Command::Aim(aim::Intent::Point(point))],now).unwrap();
    for step in 1..=20{world.advance(now+Duration::from_millis(step*100)).unwrap();}
}
fn eligible(surface:Surface,facts:&materials::MaterialFacts,start:[f32;3],end:[f32;3],normal:[f32;3])->bool{
    let Some(e)=facts.effective.as_ref()else{return false;};
    match surface{
        Surface::OrdinaryHull=>{
            let chord:[f64;3]=std::array::from_fn(|i|f64::from(end[i])-f64::from(start[i]));
            let length=chord.iter().map(|x|x*x).sum::<f64>().sqrt();
            let cosine=chord.iter().zip(normal).map(|(a,b)|a*f64::from(b)).sum::<f64>().abs()/length;
            facts.component==materials::Component::Hull&&facts.source_class==materials::SourceClass::ArmorDescriptor
                &&e.extra_is_none&&e.damage_kind==0&&e.vehicle_damage_factor==1.&&e.armor.is_some_and(|a|a>0.)
                &&cosine>=20f64.to_radians().cos()
        },
        Surface::Gun25=>facts.component==materials::Component::Gun01&&facts.name=="gun"&&facts.kind==25
            &&facts.source_class==materials::SourceClass::GunVisualMaterial&&e.vehicle_damage_factor==0.&&e.damage_kind==1,
        Surface::Breech31=>facts.component==materials::Component::Gun01&&facts.name=="gunBreech"&&facts.kind==31
            &&facts.source_class==materials::SourceClass::GunBreechVisualMaterial&&e.armor==Some(0.)
            &&e.vehicle_damage_factor==1.&&e.damage_kind==1,
    }
}

/// Select by actual first geometric surface and source class/normal, never by
/// a successful HP/module result. Every accepted candidate remains unadvanced
/// after its real admitted launch; the test then drives actual World/Trace.
fn find_launch(initial:&World,now:Instant,surface:Surface,xs:&[f32],ys:&[f32],zs:&[f32])->Option<World>{
    assert!(xs.len()<=7&&ys.len()<=9&&zs.len()<=9);
    let at=now+Duration::from_secs(2);let end_tick=1023;
    for &x in xs{for &y in ys{for &z in zs{
        let mut world=initial.clone();let point=[x,200.+y,z];settle(&mut world,point,now);
        world.apply(0,1,&[Command::Armament(arm::Command::Shoot)],at).unwrap();
        assert_eq!(world.projectiles.len(),1,"real selected launch must be admitted");let p=world.projectiles[0];
        let b=world.geometry_for(world.actors[1].vehicle_kind()).unwrap();let mesh=b.world_mesh(&world.actors[1],1,end_tick).unwrap();
        let mut accept=false;
        for step in 0..3{
            let start=p.position_at(at+STEP*step);let end=p.position_at(at+STEP*(step+1));
            if let Some(hit)=collision::query(&mesh,start,end).unwrap().first(){
                let facts=b.materials().lookup(&hit.mesh,&hit.material).unwrap();
                let ground=world.terrain.as_ref().unwrap().nearest_excluding_many(start,end,&[]).unwrap();
                accept=ground.is_none_or(|g|(g.t as f32)>hit.t)&&eligible(surface,&facts,start,end,hit.normal);break;
            }
        }
        if accept{return Some(world);}
    }}}None
}
fn ordinary_launch(source:VehicleKind,target:VehicleKind,shot_index:usize,now:Instant)->World{
    let initial=pair(28501+source.index()as u64*10+shot_index as u64,now,source,target,shot_index,([0.,200.,-40.],0.),FRAC_PI_2);
    find_launch(&initial,now,Surface::OrdinaryHull,&[0.,0.2,-0.2,0.4,-0.4,0.8,-0.8],&[1.2,1.1,1.3,1.,1.4,0.9,1.5],&[0.,0.4,-0.4,0.8,-0.8])
        .expect("bounded actual launch must reach a near-normal ordinary side Hull; no authored contact fallback")
}

fn assert_trace_contact(world:&World){
    assert_eq!(world.contacts.len(),1);assert_eq!(world.impacts.len(),1);assert_eq!(world.terrain_contacts.len(),0);
    let c=&world.contacts[0];assert_eq!((c.shot,c.target_slot,c.tick),(1,1,1023));
    let b=world.geometry_for(world.actors[1].vehicle_kind()).unwrap();let mesh=b.world_mesh(&world.actors[1],1,c.tick).unwrap();
    assert_eq!(collision::query(&mesh,c.segment_start,c.segment_end).unwrap()[0],c.triangle);
    let mut material=None;let mut resolution=None;let mut terminals=0;
    for event in world.impact.events(){match event{
        impact::Event::MaterialContact{order,shot_id,facts,..}if *shot_id==1=>{assert!(material.is_none());assert_eq!(facts,&c.material_facts);material=Some(*order);},
        impact::Event::MixedResolution{shot_id,material_order,shell,contact,health_before,health_after,..}if *shot_id==1=>{
            assert!(resolution.is_none());assert_eq!(Some(*material_order),material);assert_eq!(contact,c);assert_eq!(Some(*shell),world.projectiles[0].shell);
            assert_eq!((*health_before,*health_after),(2000,world.actors[1].health));resolution=Some(*material_order);
        },
        impact::Event::Terminal{shot_id,reason,..}if *shot_id==1=>{assert_eq!(*reason,impact::TerminalReason::TestLabMixedImpact);terminals+=1;},_=>{},
    }}assert!(material.is_some()&&resolution.is_some());assert_eq!(terminals,1);assert!(world.projectiles[0].stopped);
}
fn assert_one_hp_and_module(world:&World,damage:u16){
    assert_trace_contact(world);let shell=world.projectiles[0].shell.unwrap();assert_eq!(shell.damage_hp,damage);
    let ImpactOutcome::Mixed(resolution)=&world.impacts[0].outcome else{panic!("actual mixed result")};
    assert_eq!(resolution.decision,crate::p06t_damage::Decision::Pierced);assert_eq!(resolution.damage_hp,damage);
    assert_eq!(world.actors[1].health,2000-damage as i16);assert_eq!(world.damage_events.len(),1);
    let d=&world.damage_events[0];assert_eq!((d.sequence,d.target,d.attacker,d.shot,d.health_before,d.health_after,d.direct,d.pierced),(1,1,0,1,2000,2000-damage as i16,true,true));
    assert!(!world.rng_draws.is_empty()&&world.rng_draws.len()<=2);
    let mut changed=0;for(slot,event)in &world.device_events{
        assert_eq!((*slot,event.cause.shot,event.cause.attacker_slot),(1,1,0));assert!(!event.from_fire);
        if let devices::Change::Device{before,after,..}=event.change{assert!(before>after);assert_eq!(after,before.saturating_sub(shell.device_damage));changed+=1;}
    }assert!(changed>0,"same real exterior chord must reach an explicit LAB device proxy");
    assert_eq!(world.actors[1].devices.as_ref().unwrap().sequence()as usize,world.device_events.len());
    assert!(!world.impact.events().iter().any(|e|matches!(e,impact::Event::SplashResolution{..})),"two far-apart actors/direct target exclusion must avoid duplicate splash HP");
}

#[test]fn p06t_extended_hit_wt128_ap_reaches_actual_fv_hull_trace_one_hp_and_module_ledger(){
    let now=Instant::now();let mut w=ordinary_launch(VehicleKind::Wt128,VehicleKind::Fv183,0,now);
    w.advance(now+Duration::from_millis(2300)).unwrap();assert_one_hp_and_module(&w,560);
    assert_eq!(w.projectiles[0].shell.unwrap().compact_descr,13850);assert_eq!(w.actors[0].fire.typed().unwrap().counts(),[1,0,0]);
}
#[test]fn p06t_extended_hit_fv_ap_reaches_actual_wt_hull_trace_one_hp_and_module_ledger(){
    let now=Instant::now();let mut w=ordinary_launch(VehicleKind::Fv183,VehicleKind::Wt128,0,now);
    w.advance(now+Duration::from_millis(2300)).unwrap();assert_one_hp_and_module(&w,1150);
    assert_eq!(w.projectiles[0].shell.unwrap().compact_descr,20826);
}
#[test]fn p06t_extended_hit_fv_premium_hesh275_reaches_actual_wt_hull_without_ap_or_double_hp(){
    let now=Instant::now();let mut w=ordinary_launch(VehicleKind::Fv183,VehicleKind::Wt128,1,now);
    w.advance(now+Duration::from_millis(2300)).unwrap();assert_one_hp_and_module(&w,1750);
    let shell=w.projectiles[0].shell.unwrap();assert_eq!(shell.compact_descr,21082);assert_eq!(shell.family,shells::Family::HighExplosive);
    assert_eq!(shell.penetration_mm,[275.,275.]);assert!(shell.premium_gold_flag);assert_eq!(w.actors[0].fire.typed().unwrap().counts(),[0,1,0]);
}
#[test]fn p06t_extended_hit_wt_source_gun25_has_zero_vehicle_hp_and_one_source_gun_device_change(){
    let now=Instant::now();let initial=pair(28530,now,VehicleKind::Fv183,VehicleKind::Wt128,0,([-40.,200.,3.],FRAC_PI_2),0.);
    let mut w=find_launch(&initial,now,Surface::Gun25,&[0.,0.2,-0.2,0.4,-0.4],&[3.2,3.3,3.1,3.4,3.,2.9,2.8],&[3.,4.,2.,5.,1.])
        .expect("bounded actual World ray must hit the exposed source WT barrel25");
    let gun=crate::p06t_device_caps::Device::Gun as usize;let before=w.actors[1].devices.as_ref().unwrap().health()[gun];
    w.advance(now+Duration::from_millis(2300)).unwrap();assert_trace_contact(&w);
    assert_eq!((w.contacts[0].material_facts.name.as_str(),w.contacts[0].material_facts.kind),("gun",25));
    assert_eq!(w.actors[1].health,2000);assert!(w.damage_events.is_empty());assert_eq!(w.device_events.len(),1);
    assert_eq!(w.actors[1].devices.as_ref().unwrap().health()[gun],before.saturating_sub(244));
    assert!(matches!(w.device_events[0],(1,devices::Transition{change:devices::Change::Device{device:crate::p06t_device_caps::Device::Gun,..},..})));
    assert_eq!(w.rng_draws.len(),1);
}
#[test]fn p06t_extended_hit_wt_breech31_is_real_nearest_contact_but_unsupported_without_fake_hp_or_device(){
    let now=Instant::now();let mut found=None;
    // Near side/rear/front plus raised distant viewpoints. Every source body
    // faces the target so FV's real ±45 yaw limit is respected. Raised poses
    // are explicit LAB; no worker/native driving qualification is claimed.
    for(position,yaw)in[
        ([-40.,200.,-1.],FRAC_PI_2),([40.,200.,-1.],-FRAC_PI_2),([0.,200.,-40.],0.),([0.,200.,40.],-PI),
        ([-160.,212.,-1.],FRAC_PI_2),([160.,212.,-1.],-FRAC_PI_2),([0.,212.,-160.],0.),([0.,212.,160.],-PI),
    ]{
        let initial=pair(28531,now,VehicleKind::Fv183,VehicleKind::Wt128,0,(position,yaw),0.);
        if let Some(w)=find_launch(&initial,now,Surface::Breech31,&[0.,0.3,-0.3,0.6,-0.6],&[2.8,2.6,3.,2.4,3.2,2.2,3.4],&[-1.,-1.5,-0.5,-2.,0.,-2.5,0.5]){found=Some(w);break;}
    }
    let mut w=found.expect("actual whole-vehicle nearest WT breech31 surface required; no authored-contact fallback");
    let before=w.actors[1].devices.clone().unwrap();w.advance(now+Duration::from_millis(2300)).unwrap();assert_trace_contact(&w);
    assert_eq!((w.contacts[0].material_facts.name.as_str(),w.contacts[0].material_facts.kind),("gunBreech",31));
    let ImpactOutcome::Mixed(r)=&w.impacts[0].outcome else{panic!("unsupported still has a recorded selected policy outcome")};
    assert_eq!((r.decision,r.damage_hp),(crate::p06t_damage::Decision::Unsupported,0));assert_eq!(w.actors[1].health,2000);
    let after=w.actors[1].devices.as_ref().unwrap();assert_eq!((after.health(),after.crew(),after.sequence(),after.fire_active()),(before.health(),before.crew(),before.sequence(),before.fire_active()));
    assert!(w.damage_events.is_empty()&&w.device_events.is_empty()&&w.rng_draws.is_empty());
    assert_eq!(w.actors[0].fire.typed().unwrap().counts(),[1,0,0]);
}
