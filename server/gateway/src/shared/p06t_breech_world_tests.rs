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
fn pair(id:u64,now:Instant,source:VehicleKind,target:VehicleKind,shot_index:usize,source_pose:([f32;3],f32),target_yaw:f32,breech:bool)->World{
    let rows=super::super::super::profile13_templates::extended_test_resources();
    let mut world=World::new_for_roster(id,now,crate::map_profile091::MapId::Prohorovka,2).unwrap();
    for row in &rows{world.bind_geometry(row.geometry.clone()).unwrap();}
    world.enable_ap_test_lab().unwrap();world.bind_terrain(rows[0].terrain.clone()).unwrap();
    world.bind_fragiles(rows[0].catalog.0.clone()).unwrap();world.enable_extended_lab().unwrap();
    if breech{world.enable_extended_breech_lab().unwrap();}
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

/// Shared actual launch fixture, cached after bounded source-surface search.
/// Synthetic airborne server poses isolate collision; no owned/UI/Jolt claim.
pub(crate) fn launch31()->(World,Instant){
    static ACTUAL:std::sync::OnceLock<(World,Instant)>=std::sync::OnceLock::new();
    ACTUAL.get_or_init(||{
        let now=Instant::now();let mut found=None;
        for(position,yaw)in[
            ([-40.,200.,-1.],FRAC_PI_2),([40.,200.,-1.],-FRAC_PI_2),([0.,200.,-40.],0.),([0.,200.,40.],-PI),
            ([-160.,212.,-1.],FRAC_PI_2),([160.,212.,-1.],-FRAC_PI_2),([0.,212.,-160.],0.),([0.,212.,160.],-PI),
        ]{
            let initial=pair(28531,now,VehicleKind::Fv183,VehicleKind::Wt128,0,(position,yaw),0.,true);
            if let Some(w)=find_launch(&initial,now,Surface::Breech31,&[0.,0.3,-0.3,0.6,-0.6],&[2.8,2.6,3.,2.4,3.2,2.2,3.4],&[-1.,-1.5,-0.5,-2.,0.,-2.5,0.5]){found=Some(w);break;}
        }
        (found.expect("real first WT31 surface required; no authored contact fallback"),now)
    }).clone()
}

#[test]
fn p06t_breech_world_explicit_source31_has_one_nominal_hp_and_direct_gun_ledger(){
    let(mut w,now)=launch31();assert!(w.extended_breech_lab());let shell=w.projectiles[0].shell.unwrap();
    assert_eq!((shell.compact_descr,shell.damage_hp,shell.device_damage),(20826,1150,244));
    let before=w.actors[1].devices.clone().unwrap();let gun=crate::p06t_device_caps::Device::Gun as usize;
    w.advance(now+Duration::from_millis(2300)).unwrap();assert_eq!(w.contacts.len(),1);assert_eq!(w.impacts.len(),1);
    let c=&w.contacts[0];let b=w.geometry_for(VehicleKind::Wt128).unwrap();let mesh=b.world_mesh(&w.actors[1],1,c.tick).unwrap();
    assert_eq!(collision::query(&mesh,c.segment_start,c.segment_end).unwrap()[0],c.triangle);
    assert_eq!((c.material_facts.name.as_str(),c.material_facts.kind),("gunBreech",31));
    let ImpactOutcome::Mixed(r)=&w.impacts[0].outcome else{panic!("mixed actual source31")};
    assert_eq!((r.policy,r.decision,r.damage_hp),(crate::p06t_damage::UNARMORED_DEVICE_POLICY,crate::p06t_damage::Decision::UnarmoredDevice,1150));
    assert_eq!(w.actors[1].health,850);assert_eq!(w.damage_events.len(),1);
    let hp=&w.damage_events[0];assert_eq!((hp.attacker,hp.target,hp.shot,hp.health_before,hp.health_after,hp.direct,hp.pierced),(0,1,1,2000,850,true,false));
    let after=w.actors[1].devices.as_ref().unwrap();assert_eq!(after.health()[gun],before.health()[gun].saturating_sub(244));
    for index in 0..9{if index!=gun{assert_eq!(after.health()[index],before.health()[index]);}}
    assert_eq!(after.crew(),before.crew());assert_eq!(after.sequence(),1);assert_eq!(w.device_events.len(),1);
    assert!(matches!(w.device_events[0],(1,devices::Transition{cause:devices::Cause{shot:1,attacker_slot:0},from_fire:false,
        change:devices::Change::Device{device:crate::p06t_device_caps::Device::Gun,extra_index:32,before:240,after:0,..},..})));
    assert!(w.rng_draws.is_empty());assert!(!after.fire_active());
    assert_eq!(w.impact.events().iter().filter(|e|matches!(e,impact::Event::MixedResolution{..})).count(),1);
    assert_eq!(w.impact.events().iter().filter(|e|matches!(e,impact::Event::Terminal{..})).count(),1);
    let snapshot=w.failure_snapshot();let actors=w.actors.clone();let trace=w.impact.clone();let ledger=w.device_events.clone();
    w.advance(now+Duration::from_millis(2400)).unwrap();assert_eq!(w.actors[1].health,actors[1].health);assert_eq!(w.actors[1].devices.as_ref().unwrap().health(),actors[1].devices.as_ref().unwrap().health());assert_eq!(w.actors[1].devices.as_ref().unwrap().sequence(),1);assert_eq!(w.impact,trace);assert_eq!(w.device_events,ledger);
    assert_eq!(w.damage_events.len(),1);assert_eq!(snapshot["damage_event_count"],1);
}

#[test]
fn p06t_breech_world_late_device_capacity_failure_rolls_back_hp_trace_modules_and_rng(){
    let(mut finished,now)=launch31();finished.advance(now+Duration::from_millis(2300)).unwrap();
    let event=finished.device_events[0];let(mut w,now)=launch31();w.device_events=vec![event;MAX_DAMAGE_EVENTS];
    let snapshot=w.failure_snapshot();let actors=w.actors.clone();let trace=w.impact.clone();let projectiles=w.projectiles.clone();
    assert!(w.advance(now+Duration::from_millis(2300)).is_err());
    assert_eq!(w.failure_snapshot(),snapshot);assert_eq!(w.actors,actors);assert_eq!(w.impact,trace);assert_eq!(w.projectiles,projectiles);
    assert!(w.damage_events.is_empty()&&w.contacts.is_empty()&&w.impacts.is_empty()&&w.rng_draws.is_empty());
}

#[test]
fn p06t_breech_world_policy_cannot_be_enabled_on_regular_or_already_attached_world(){
    let now=Instant::now();let mut ordinary=World::new_for_roster(28532,now,crate::map_profile091::MapId::Prohorovka,2).unwrap();
    assert!(ordinary.enable_extended_breech_lab().is_err());assert!(!ordinary.extended_breech_lab());
    let(mut w,_)=launch31();let snapshot=w.failure_snapshot();let trace=w.impact.clone();
    assert!(w.enable_extended_breech_lab().is_err());assert_eq!(w.failure_snapshot(),snapshot);assert_eq!(w.impact,trace);
}
