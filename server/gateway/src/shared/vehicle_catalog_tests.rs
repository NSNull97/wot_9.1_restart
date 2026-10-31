//! CAT-01 contract: the generated catalog agrees with its own bytes, with every
//! retained closed Rust list and with the legacy admission identity.
use super::*;
use crate::gateway091::shared::vehicle_profile::VehicleKind;
use crate::p06t_device_caps as caps;
use crate::p06t_shells091 as source;
use crate::profile13_v2091 as v2;
use serde_json::Value;
use sha2::{Digest,Sha256};

const ACCOUNT:&str="0f1e2d3c-4b5a-4968-8776-655443322110";

#[test] fn embedded_catalog_bytes_match_generated_hash_and_table() {
    assert_eq!(format!("{:x}",Sha256::digest(CATALOG_JSON.as_bytes())),CATALOG_SHA256);
    let doc:Value=serde_json::from_str(CATALOG_JSON).unwrap();
    assert_eq!(doc["schema"],CATALOG_SCHEMA);
    let rows=doc["vehicles"].as_array().unwrap();assert_eq!(rows.len(),VEHICLES.len());
    for(row,v)in rows.iter().zip(VEHICLES){
        assert_eq!(row["kind"],v.kind);assert_eq!(row["vehicle_id"],v.vehicle_id);
        assert_eq!(row["native_compact_id"],v.native_compact_id);
        assert_eq!(row["descriptor_hex"],v.descriptor.iter().map(|b|format!("{b:02x}")).collect::<String>());
        assert_eq!((row["max_hp"].as_u64(),row["ammo_capacity"].as_u64()),(Some(u64::from(v.max_hp)),Some(u64::from(v.ammo_capacity))));
        assert_eq!(row["crew"].as_array().unwrap().len(),v.seats);
        assert_eq!(row["modules"]["gun"]["native_compact_id"],v.gun_compact_id);
        let admission=match v.battle_admission{Admission::Always=>"always",Admission::ZeroEconomyPolicy=>"zero_economy_policy",Admission::None=>"none"};
        assert_eq!(row["battle_admission"],admission);
        for(s,t)in row["shells"].as_array().unwrap().iter().zip(v.shells){
            assert_eq!((s["suffix"].as_str(),s["family"].as_str(),s["native_compact_id"].as_u64(),s["shell_definition_id"].as_str()),
                (Some(t.suffix),Some(t.family),Some(u64::from(t.native_compact_id)),Some(t.shell_definition_id)));}
        for(d,t)in row["devices"].as_array().unwrap().iter().zip(v.devices){
            assert_eq!((d["max_health"].as_u64(),d["max_regen_health"].as_u64()),(Some(u64::from(t.0)),Some(u64::from(t.1))));}
    }
}

const LEGACY:[&str;5]=["ms1","is7","t26","t34","t3485"];
/// BATTLE-ANY stage 3 pilot (owner 2026-10-27): generated rows after the legacy five.
const PILOT:[&str;7]=["ussr-KV-3","usa-M4_Sherman","germany-Waffentrager_E100","japan-Chi_Ri",
    "uk-GB48_FV215b_183","china-Ch22_113","france-Bat_Chatillon25t"];
fn legacy_rows()->impl Iterator<Item=&'static Vehicle>{VEHICLES.iter().filter(|v|LEGACY.contains(&v.kind))}

#[test] fn catalog_equals_retained_closed_rust_lists() {
    let labels:Vec<&str>=VEHICLES.iter().map(|v|v.kind).collect();
    assert_eq!(labels,LEGACY.iter().chain(PILOT.iter()).copied().collect::<Vec<_>>());
    for v in legacy_rows(){
        let kind=VehicleKind::from_label(v.kind).unwrap();
        assert_eq!(kind.descriptor(),v.descriptor,"{}",v.kind);
        assert_eq!(kind.vehicle_compact_id(),v.native_compact_id);
        assert_eq!(kind.gun_compact_id(),v.gun_compact_id);
        assert_eq!(i32::from(kind.max_health()),i32::from(v.max_hp));
        assert_eq!(kind.ammo_limit(),v.ammo_capacity);
        assert_eq!(kind.shell_compact_id(),v.shells[0].native_compact_id);
        assert_eq!(kind.panel_rows().map(|r|r.0),[0,1,2].map(|i|v.shells[i].native_compact_id));
        assert_eq!(kind.battle_admission(),v.battle_admission==Admission::Always);
        let p=source::profile(kind.mount());assert_eq!(p.capacity,v.ammo_capacity);
        assert_eq!(p.shots.each_ref().map(|s|(u32::from(s.compact_descr),s.family.source_name())),
            [0,1,2].map(|i|(v.shells[i].native_compact_id,v.shells[i].family)));
        let d=caps::Profile::ALL.into_iter().find(|d|d.label()==v.kind).unwrap();
        assert_eq!(caps::MAX_HP[d.index()],v.max_hp);assert_eq!(caps::CREW[d.index()].len(),v.seats);
        assert_eq!(caps::CAPS[d.index()].map(|c|(c.max,c.regen)).as_slice(),v.devices);
    }
}

/// Pilot rows come from the research catalogue (catalog_build); the gateway registry
/// comes from the generated battle table. Both must state the same vehicle.
#[test] fn pilot_rows_equal_the_verified_generated_registry() {
    for v in VEHICLES.iter().filter(|v|PILOT.contains(&v.kind)){
        let kind=VehicleKind::from_owned_label(v.kind).unwrap();
        let e=kind.generated().unwrap();
        assert!(VehicleKind::from_label(v.kind).is_none(),"{} must not shadow a closed kind",v.kind);
        assert_eq!((kind.descriptor(),kind.vehicle_compact_id(),kind.gun_compact_id()),(v.descriptor,v.native_compact_id,v.gun_compact_id),"{}",v.kind);
        assert_eq!((i32::from(kind.max_health()),kind.ammo_limit(),e.crew.len()),(i32::from(v.max_hp),v.ammo_capacity,v.seats),"{}",v.kind);
        assert_eq!(e.gun.shots.each_ref().map(|s|(u32::from(s.compact_descr),s.family.source_name())),
            [0,1,2].map(|i|(v.shells[i].native_compact_id,v.shells[i].family)),"{}",v.kind);
        assert_eq!(e.suffixes.each_ref().map(|s|s.as_str()),[0,1,2].map(|i|v.shells[i].suffix),"{}",v.kind);
        assert_eq!(e.caps.map(|c|(c.max,c.regen)).as_slice(),v.devices,"{}",v.kind);
        assert_eq!(v.battle_admission,Admission::Always,"{}",v.kind);
    }
}

fn frozen(v:&Vehicle,native:u64,suffix:&str)->(Value,String){
    let crew:Vec<String>=(0..v.seats).map(|i|format!("{ACCOUNT}:crew-{i}")).collect();
    let ammunition:Vec<Value>=v.shells.iter().enumerate().map(|(i,s)|serde_json::json!({"shell_definition_id":s.shell_definition_id,
        "shell_compact_id":s.native_compact_id,"family":s.family,"count":if i==0{1}else{0}})).collect();
    let value=serde_json::json!({"kind":v.kind,"descriptor_hex":v.descriptor.iter().map(|b|format!("{b:02x}")).collect::<String>(),
        "native_inventory_id":native,"vehicle_inventory_id":format!("{ACCOUNT}:{suffix}"),"max_hp":v.max_hp,"crew_ids":crew,
        "capacity":v.ammo_capacity,"ammunition":ammunition,"initial_shell_compact_id":v.shells[0].native_compact_id});
    let sha=format!("{:x}",Sha256::digest(serde_json::to_vec(&value).unwrap()));(value,sha)
}

#[test] fn catalog_and_legacy_admission_identity_are_identical() {
    for v in legacy_rows(){
        let (native,suffix)=match v.legacy_inventory{Some((n,s))=>(u64::from(n),s.to_string()),None=>(7,"p09e-vehicle:7".to_string())};
        let(value,sha)=frozen(v,native,&suffix);
        let legacy=v2::parse_frozen_with(&value,ACCOUNT,&sha,false).unwrap();
        let catalog=v2::parse_frozen_with(&value,ACCOUNT,&sha,true).unwrap();
        assert_eq!(legacy,catalog,"{}",v.kind);
        // Wrong inventory binding is refused identically in both modes.
        for wrong in [1u64,2,3]{if wrong==native{continue;}
            assert_eq!(v2::legacy_identity_for_tests(v.kind,wrong).is_ok(),v2::catalog_identity_in(VEHICLES,v.kind,wrong).is_ok(),"{} {wrong}",v.kind);}
    }
    for label in ["wt-e100-128","fv215b-183","kv1",""]{
        assert!(v2::legacy_identity_for_tests(label,7).is_err());assert!(v2::catalog_identity_in(VEHICLES,label,7).is_err());}
    // Stage 3c: catalog mode admits the pilot through the verified registry; legacy mode never does.
    for v in VEHICLES.iter().filter(|v|PILOT.contains(&v.kind)){
        assert!(v2::catalog_identity_in(VEHICLES,v.kind,7).is_ok(),"{}",v.kind);
        assert!(v2::catalog_identity_in(VEHICLES,v.kind,1).is_err(),"{} base inventory",v.kind);
        let(value,sha)=frozen(v,7,"p09e-vehicle:7");
        assert!(v2::parse_frozen_with(&value,ACCOUNT,&sha,false).is_err(),"{}",v.kind);
        let f=v2::parse_frozen_with(&value,ACCOUNT,&sha,true).unwrap();
        assert_eq!((f.kind,f.kind.is_generated()),(VehicleKind::from_owned_label(v.kind).unwrap(),true));
        assert!(v2::catalog_generated_kind_in(true,v.kind)&&!v2::catalog_generated_kind_in(false,v.kind));
    }
    for label in LEGACY.into_iter().chain(["wt-e100-128","fv215b-183","ussr-KV1","china-Ch04_T34_1",""]){
        assert!(!v2::catalog_generated_kind_in(true,label),"{label}");}
}

#[test] fn battle_admission_is_a_data_field() {
    // Turning one entry's data to `none` closes it without a code change.
    let mut table=VEHICLES.to_vec();
    let t34=table.iter_mut().find(|v|v.kind=="t34").unwrap();
    assert!(v2::catalog_identity_in(&[*t34],"t34",9).is_ok());
    t34.battle_admission=Admission::None;
    assert!(v2::catalog_identity_in(&table,"t34",9).is_err());
    // A catalog fact that disagrees with the battle profile is refused, not trusted.
    let mut wrong=*VEHICLES.iter().find(|v|v.kind=="t26").unwrap();wrong.max_hp+=1;
    assert!(v2::catalog_identity_in(&[wrong],"t26",9).is_err());
}
