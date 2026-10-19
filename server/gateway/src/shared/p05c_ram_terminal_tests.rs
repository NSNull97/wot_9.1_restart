//! Terminal projection from real contact commits. The fixture maps one
//! preserved writer Frozen to an authored World; admission itself is not tested.
use super::*;
use crate::{profile13_v2091 as v2,battle091::profile13::Context};
use crate::gateway091::shared::turret_publication_test_fixture as f;

fn frozen()->v2::Frozen{
    let v:serde_json::Value=serde_json::from_slice(include_bytes!("../../../../tests/fixtures/p06t-writer-vectors.json")).unwrap();
    let row=v["vectors"].as_array().unwrap().iter().find(|r|r["operation"]=="battle"
        &&r["request"]["operation"]=="admit"&&r["response"]["status"]=="admitted").unwrap();
    let q=&row["request"];
    let context=Context{account_id:q["account_id"].as_str().unwrap().into(),
        native_database_id:q["native_database_id"].as_i64().unwrap()as i32,
        command_key:q["command_key"].as_str().unwrap().into(),expected_revision:q["expected_revision"].as_u64().unwrap(),
        run_id:q["run_id"].as_str().unwrap().into()};
    let request=v2::Request::Admit{battle:q["battle_id"].as_str().unwrap().rsplit(':').next().unwrap().parse().unwrap(),
        native_inventory_id:q["native_inventory_id"].as_u64().unwrap()as u32};
    v2::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&context,&request).unwrap().reservation.unwrap().frozen
}
fn contact(world:&mut World,speed:f32){
    world.apply_tank_contacts(&[TankContactInput{slot_a:0,slot_b:1,substep:1,
        point:[0.,1.,0.],normal:[1.,0.,0.],relative_velocity:[speed,0.,0.]}],1,186).unwrap();
}
#[test]
fn p05c_ram_terminal_lethal_uses_domain_tick_and_keeps_real_shots_empty(){
    let now=Instant::now();let(_,mut w)=f::fixture(now);let frozen=frozen();
    w.actors[0].owned_v2=Some(frozen.clone());w.tick=1242;contact(&mut w,50.);
    assert!(w.actors.iter().all(|a|a.health==0&&a.devices.as_ref().unwrap().frozen()));
    assert!(w.shots.is_empty()&&w.projectiles.is_empty()&&w.damage_events.is_empty());
    assert_eq!((w.ram_damage_events[0].tick,w.ram_damage_events[0].domain_tick),(186,1242));
    let raw=w.terminal_state_json(0).unwrap();let parsed=v2::validate_terminal_json(&raw,&frozen,0).unwrap();
    assert_eq!((parsed.death_reason,parsed.killer_slot),(2,Some(1)));
    assert_eq!(parsed.raw["death"]["tick"],1242);
}
#[test]
fn p05c_ram_terminal_nonlethal_has_no_invented_death(){
    let now=Instant::now();let(_,mut w)=f::fixture(now);let frozen=frozen();
    w.actors[0].owned_v2=Some(frozen.clone());contact(&mut w,2.);
    let hp=w.actors[0].health;assert!((1..90).contains(&hp));
    let raw=w.terminal_state_json(0).unwrap();let parsed=v2::validate_terminal_json(&raw,&frozen,hp).unwrap();
    assert_eq!((parsed.death_reason,parsed.killer_slot),(-1,None));assert_eq!(parsed.raw["death"]["tick"],0);
}
#[test]
fn p05c_ram_terminal_conflicting_death_journals_remain_an_error(){
    let now=Instant::now();let(_,mut w)=f::fixture(now);w.actors[0].owned_v2=Some(frozen());contact(&mut w,50.);
    w.damage_events.push(DamageRecord{sequence:1,tick:1000,attacker:1,target:0,shot:1,reason:0,
        health_before:1,health_after:0,crew_before:true,crew_after:false,direct:true,pierced:true});
    assert!(w.death_cause(0).is_err());assert!(w.terminal_state_json(0).is_err());
}
