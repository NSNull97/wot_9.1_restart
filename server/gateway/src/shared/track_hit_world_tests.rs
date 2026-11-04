//! Live track hits through the pinned source chassis of MS-1 (World + Trace).
//! Shooter identities are authored LAB fixtures; the geometry, chassis bundle,
//! shells and module HP are the pinned #717 sources. No hand-made contact.
use super::*;
use crate::{p06t_armament091 as arm,p06t_shells091 as source,p06t_lab_proxy::Target};
use std::path::PathBuf;

fn root()->PathBuf{PathBuf::from(std::env::var("WOT091_ROOT").unwrap_or_else(|_|"D:/WoT_9.1_Server".into()))}
fn ms1_chassis()->Arc<super::super::super::chassis_armor::ChassisArmor>{
    Arc::new(super::super::super::chassis_armor::ChassisArmor::load(&root().join("local"),
        &root().join("local/evidence/shell-01-chassis-20261104-02/bundles/ussr-MS-1.json")).unwrap())
}
fn template(now:Instant,id:u64,chassis:bool,ground:f32)->World{
    let mut w=World::new_for_roster(id,now,crate::map_profile091::MapId::Karelia,2).unwrap();
    let ms1=super::super::super::geometry::tests::bundle();
    w.bind_geometry(Arc::new(if chassis{ms1.with_chassis(ms1_chassis()).unwrap()}else{ms1})).unwrap();
    w.bind_geometry(Arc::new(super::super::super::geometry::tests::is7_bundle())).unwrap();
    w.enable_ap_test_lab().unwrap();w.bind_terrain(Arc::new(super::super::super::terrain::tests::fixture(-1000.,2000.,2,vec![ground;4]))).unwrap();
    w.enable_mixed_ammo().unwrap();w.enable_lifecycle(super::super::super::lifecycle::Rules{
        prebattle_ms:1000,battle_ms:60000,..super::super::super::lifecycle::Rules::prohorovka()}).unwrap();w
}
fn lab_attach(w:&mut World,slot:usize,counts:[u16;3]){
    w.mixed_ammo=false;
    assert_eq!(tests::attach_physics_profile(w,VehicleKind::Ms1,Identity{account:format!("authored-track-lab-{slot}"),
        database:300+slot as i32,name:format!("track-lab-{slot}")},slot as u32+1).unwrap(),slot);
    w.mixed_ammo=true;
    let shell=source::PROFILES[0].shots[counts.iter().position(|v|*v>0).unwrap()];
    w.actors[slot].fire=fire::State::with_typed(source::Mount::Ms1Stock,counts,shell.compact_descr).unwrap();
    w.actors[slot].devices=Some(device::State::new(caps::Profile::Ms1).unwrap());
}
fn ready(chassis:bool,counts:[u16;3],id:u64,now:Instant)->World{ready_at(chassis,counts,id,now,-100.,20.)}
/// `ground`: flat terrain height; `target_z`: distance of the side-on target.
fn ready_at(chassis:bool,counts:[u16;3],id:u64,now:Instant,ground:f32,target_z:f32)->World{
    let mut w=template(now,id,chassis,ground);lab_attach(&mut w,0,[4,4,4]);lab_attach(&mut w,1,[1,1,1]);
    w.actors[0].fire=fire::State::with_typed(source::Mount::Ms1Stock,counts,
        source::PROFILES[0].shots[counts.iter().position(|v|*v>0).unwrap()].compact_descr).unwrap();
    for(slot,p)in [[0.;3],[0.,0.,target_z]].into_iter().enumerate(){w.actors[slot].position=p;w.actors[slot].origin=p;}
    // Side-on target: its chassis covers the lower hull side toward the shooter.
    w.actors[1].direction=[std::f32::consts::FRAC_PI_2,0.,0.];w.actors[1].yaw=std::f32::consts::FRAC_PI_2;
    w.start(now).unwrap();w.lifecycle_created_unix=Some(1792152000);
    for slot in 0..2{w.set_ready(slot,slot as u32+1).unwrap();}
    w.advance_lifecycle(now).unwrap();w
}
fn shoot(base:&World,point:[f32;3],now:Instant)->World{
    let mut w=base.clone();
    w.apply(0,1,&[Command::Aim(aim::Intent::Point(point))],now).unwrap();
    for step in 1..=20{let at=now+STEP*step;w.advance(at).unwrap();w.advance_lifecycle(at).unwrap();}
    let at=now+Duration::from_secs(2);
    w.apply(0,1,&[Command::Armament(arm::Command::Shoot)],at).unwrap();
    for step in 1..=10{w.advance(at+STEP*step).unwrap();}
    w
}
fn track_rows(w:&World)->Vec<(caps::Device,f64,crate::p06t_damage::TrackPass)>{
    w.impact.events().iter().filter_map(|e|match e{impact::Event::TrackContact{target:1,device,armor_mm,pass,..}=>Some((*device,*armor_mm,*pass)),_=>None}).collect()
}
fn hull_rows(w:&World)->Vec<(crate::p06t_damage::Resolution,i16,i16)>{
    w.impact.events().iter().filter_map(|e|match e{impact::Event::MixedResolution{target:1,resolution,health_before,health_after,..}
        =>Some((*resolution,*health_before,*health_after)),_=>None}).collect()
}
/// Bounded search over legal low aim points for a shot whose first contact is a track.
fn track_shot_where(base:&World,now:Instant,accept:impl Fn(&World)->bool)->(World,[f32;3]){
    for y in [0.15,0.25,0.35,0.45,0.55,0.65]{for x in [-1.2,-0.9,-0.6,-0.3,0.,0.3,0.6,0.9,1.2]{
        let point=[x,y,19.];let w=shoot(base,point,now);
        if !track_rows(&w).is_empty()&&accept(&w){return(w,point);}
    }}
    panic!("a low side-on shot must cross the source MS-1 chassis track");
}
fn first_track_shot(base:&World,now:Instant)->(World,[f32;3]){track_shot_where(base,now,|_|true)}
fn track(device:caps::Device)->bool{matches!(device,caps::Device::LeftTrack|caps::Device::RightTrack)}

#[test]fn ap_shell_hits_the_source_track_without_hp_then_continues_with_residual_power(){
    let now=Instant::now();let base=ready(true,[4,0,0],401,now);
    // The shell must pass the track and still reach the hull plate in the same flight.
    let(w,_)=track_shot_where(&base,now,|w|!hull_rows(w).is_empty());
    let rows=track_rows(&w);
    // collideOnceOnly: one row per track per shot.
    assert!(rows.len()<=2&&(rows.len()<2||rows[0].0!=rows[1].0),"{rows:?}");
    let(side,armor,pass)=rows[0];assert!(track(side));assert_eq!(armor,5.);
    assert!(!pass.stopped&&pass.power_before_mm==34.&&pass.power_after_mm==29.,"{pass:?}");
    let max=caps::Profile::Ms1.caps()[side as usize].max;
    assert!(w.device_events.iter().any(|(slot,e)|*slot==1&&matches!(e.change,device::Change::Device{device,before,..}
        if device==side&&before==max)),"track module hit at source HP");
    assert!(w.actors[1].devices.as_ref().unwrap().health()[side as usize]<max);
    // A track never changes HP itself: any HP loss comes from a following hull resolution.
    let mixed=hull_rows(&w);assert_eq!(mixed.len(),1);
    assert_eq!(mixed[0].0.nominal_power_mm,29.,"hull law sees the residual power");
    assert_eq!(base.actors[1].health-w.actors[1].health,mixed[0].1-mixed[0].2,"only the hull resolution changes HP");
    // The internal LAB proxy no longer carries invented track boxes when the chassis is bound.
    assert!(w.device_events.iter().filter(|(slot,e)|*slot==1&&matches!(e.change,device::Change::Device{device,..}if track(device)))
        .count()<=rows.len());
}

#[test]fn a_track_only_crossing_leaves_vehicle_hp_untouched(){
    let now=Instant::now();let base=ready(true,[4,0,0],406,now);
    let(w,point)=track_shot_where(&base,now,|w|hull_rows(w).is_empty());
    assert_eq!(w.actors[1].health,base.actors[1].health,"point={point:?}");
    assert!(w.damage_events.iter().all(|e|e.target!=1),"no HP record from a track");
}

#[test]fn he_detonates_on_the_track_and_stops(){
    let now=Instant::now();let base=ready(true,[0,0,4],402,now);
    let(w,_)=first_track_shot(&base,now);
    let rows=track_rows(&w);assert_eq!(rows.len(),1);assert!(rows[0].2.stopped);
    assert!(w.impact.events().iter().any(|e|matches!(e,impact::Event::Terminal{reason:impact::TerminalReason::TestLabTrackImpact,..})));
    assert!(!w.impact.events().iter().any(|e|matches!(e,impact::Event::MixedResolution{target:1,..})),"no hull plate behind a stopped shell");
    assert!(w.contacts.is_empty());
}

#[test]fn without_a_bound_chassis_the_old_path_records_no_track_contact(){
    let now=Instant::now();let with=ready(true,[4,0,0],403,now);let(_,point)=first_track_shot(&with,now);
    let old=shoot(&ready(false,[4,0,0],404,now),point,now);
    assert!(track_rows(&old).is_empty());
}

#[test]fn track_contact_refuses_a_forged_candidate_and_a_repeat(){
    let now=Instant::now();let base=ready(true,[4,0,0],405,now);let(w,_)=first_track_shot(&base,now);
    let real=w.impact.events().iter().find_map(|e|match e{impact::Event::TrackContact{candidate,shot_id,server_tick,..}
        =>Some((candidate.clone(),*shot_id,*server_tick)),_=>None}).unwrap();
    let bundle=w.geometry_for(VehicleKind::Ms1).unwrap().clone();
    let mut trace=w.impact.clone();
    let mut forged=real.0.clone();forged.t*=0.5;
    assert!(trace.track_contact(w.id,real.1,real.2,1,&bundle,&w.actors[1],&forged).is_err());
    let mut forged=real.0.clone();forged.material=if forged.material=="leftTrack"{"rightTrack".into()}else{"leftTrack".into()};
    assert!(trace.track_contact(w.id,real.1,real.2,1,&bundle,&w.actors[1],&forged).is_err());
    assert!(trace.track_contact(w.id,real.1,real.2,1,&bundle,&w.actors[1],&real.0).is_err(),"repeat/terminal shot");
}

#[test]fn track_ordinals_are_reserved_for_their_own_track(){
    let mut state=device::State::new(caps::Profile::Ms1).unwrap();
    let shell=source::PROFILES[0].shots[0];
    let hit=|ordinal,target|device::ModuleHit{cause:device::Cause{shot:1,attacker_slot:0},ordinal,at_ms:100,target,shell,ignition_roll:0.};
    let health=device::Health{hp:90,max_hp:90,terminal:false};
    assert!(state.clone().apply_hits(&[hit(2,Target::Device(caps::Device::RightTrack))],health).is_err());
    assert!(state.clone().apply_hits(&[hit(3,Target::Device(caps::Device::Engine))],health).is_err());
    assert!(state.clone().apply_hits(&[hit(4,Target::Device(caps::Device::LeftTrack))],health).is_err());
    state.apply_hits(&[hit(2,Target::Device(caps::Device::LeftTrack)),hit(3,Target::Device(caps::Device::RightTrack))],health).unwrap();
    state.apply_hits(&[hit(0,Target::Device(caps::Device::Engine)),hit(1,Target::Device(caps::Device::Radio))],health).unwrap();
}

#[test]fn track_pass_policy_is_nominal_armour_without_angle_and_he_stops(){
    use crate::p06t_damage::track_pass;
    let shots=source::PROFILES[0].shots;
    let ap=track_pass(shots[0],50.,0.,5.).unwrap();assert_eq!((ap.power_before_mm,ap.power_after_mm,ap.stopped),(34.,29.,false));
    let stop=track_pass(shots[0],50.,0.,34.).unwrap();assert!(stop.stopped&&stop.power_after_mm==0.);
    let second=track_pass(shots[0],50.,30.,5.).unwrap();assert!(second.stopped&&second.power_before_mm==4.);
    let heat=track_pass(shots[1],400.,0.,20.).unwrap();assert_eq!((heat.power_before_mm,heat.power_after_mm),(44.,24.));
    assert!(track_pass(shots[2],50.,0.,0.).unwrap().stopped,"HE detonates on the track");
    let mut forged=shots[0];forged.penetration_mm=[500.,500.];assert!(track_pass(forged,50.,0.,5.).is_err());
}

#[test]fn a_world_with_track_contacts_crosses_the_battle_worker_wire_unchanged(){
    let now=Instant::now();let base=ready(true,[4,0,0],407,now);let(w,_)=first_track_shot(&base,now);
    let bytes=crate::bw_wire::encode(&w,now,&mut crate::bw_wire::Arcs::new(false)).unwrap();
    let back:World=crate::bw_wire::decode(&bytes,now,&mut crate::bw_wire::Arcs::new(true)).unwrap();
    assert!(back.geometry_for(VehicleKind::Ms1).unwrap().chassis().is_some());
    assert_eq!(track_rows(&back),track_rows(&w));
    assert_eq!(crate::bw_wire::encode(&back,now,&mut crate::bw_wire::Arcs::new(false)).unwrap(),bytes);
}

fn ticks_of(w:&World)->(Vec<u32>,Vec<u32>){
    let track=w.impact.events().iter().filter_map(|e|match e{impact::Event::TrackContact{target:1,server_tick,..}=>Some(*server_tick),_=>None}).collect();
    let hull=w.impact.events().iter().filter_map(|e|match e{impact::Event::MixedResolution{target:1,server_tick,..}=>Some(*server_tick),_=>None}).collect();
    (track,hull)
}
fn terminal_of(w:&World)->Option<impact::TerminalReason>{
    w.impact.events().iter().find_map(|e|match e{impact::Event::Terminal{shot_id:1,reason,..}=>Some(*reason),_=>None})
}

/// Owner battle 04.11 (stand -12): a shell through the road wheels with the ground right
/// behind them in the same segment failed the battle with "impact segment facts".
#[test]fn a_shell_through_the_track_meets_the_terrain_behind_it_in_the_same_segment(){
    let now=Instant::now();let base=ready_at(true,[4,0,0],408,now,0.,20.);
    let mut found=None;
    'search: for y in [0.05,0.1,0.15,0.2,0.25,0.3]{for x in [-1.2,-0.9,-0.6,-0.3,0.,0.3,0.6,0.9,1.2]{for z in [19.,20.,21.,22.]{
        let w=shoot(&base,[x,y,z],now);
        if !track_rows(&w).is_empty()&&hull_rows(&w).is_empty()&&terminal_of(&w)==Some(impact::TerminalReason::TerrainCollision){
            found=Some(w);break 'search;
        }
    }}}
    let w=found.expect("a low shot must pass the source track and stop on the ground behind it");
    let(track,_)=ticks_of(&w);assert_eq!(track.len(),1);
    assert_eq!(w.terrain_contacts.len(),1);assert_eq!(w.terrain_contacts[0].tick,track[0],"same segment as the track");
    assert_eq!(w.actors[1].health,base.actors[1].health,"a track never changes HP");
}

/// The track is crossed in one segment and the hull plate in the next one: the flight
/// continues, the residual power is kept, and collideOnceOnly still holds.
#[test]fn a_track_pass_keeps_flying_and_reaches_the_hull_on_a_later_tick(){
    let now=Instant::now();let mut found=None;
    'search: for step in 0..120{let z=31.+0.05*step as f32;
        let base=ready_at(true,[4,0,0],409,now,-100.,z);
        for y in [0.3,0.4,0.5]{for x in [-0.3,0.,0.3]{
            let w=shoot(&base,[x,y,z-1.],now);
            let(track,hull)=ticks_of(&w);
            if track.len()==1&&hull.len()==1&&hull[0]>track[0]{found=Some(w);break 'search;}
        }}
    }
    let w=found.expect("a segment boundary between the track and the hull plate");
    let rows=track_rows(&w);assert_eq!(rows.len(),1);assert!(!rows[0].2.stopped);
    assert_eq!(hull_rows(&w)[0].0.nominal_power_mm,rows[0].2.power_after_mm,"residual power carried across segments");
    assert_eq!(terminal_of(&w),Some(impact::TerminalReason::TestLabMixedImpact));
}
