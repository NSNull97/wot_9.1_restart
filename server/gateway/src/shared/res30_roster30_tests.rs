//! RES-30: result journals, native compact results and late seals for 7..30
//! actors. Synthetic AUTHORED rosters (one owner + 29 rows such as BOT-01
//! bots), not a native trace; 2..6 rows keep their original budgets.
use super::*;
use super::tests::{inert,list,tuple,Data};
use super::super::{lifecycle_details as d,late_results_capture as capture,model::MAX_ACTORS,wire};

/// Bot-like rows: BOT-01 database ids start at 0x7F000000.
const BOT_DATABASE:i32=0x7F00_0000;
/// One owner (slot 0, team 1) + `n-1` synthetic rows; the owner destroyed
/// slot 1 (team 2) so kills/killer/details stay consistent.
fn roster(n:usize)->Results{
    let mut participants=Vec::new();
    for slot in 0..n{
        let team=1+(slot%2) as u8;
        let (account_dbid,name)=if slot==0{(1,"owner_1".to_string())}else{(BOT_DATABASE+slot as i32,format!("Bot-{slot:02}"))};
        participants.push(Participant{vehicle_id:wire::vehicle_id(slot).unwrap(),account_dbid,name,team,type_compact_descr:17,
            health:90,life_time:75,death_reason:-1,..Default::default()});
    }
    let killer=0;
    participants[killer].shots=1;participants[killer].direct_hits=1;participants[killer].piercings=1;
    participants[killer].damage_dealt=90;participants[killer].kills=1;
    let victim=1;participants[victim].health=0;participants[victim].damage_received=90;
    participants[victim].killer_id=participants[killer].vehicle_id;participants[victim].death_reason=0;participants[victim].life_time=70;
    Results{arena_id:0x1_0000_0001,arena_type_id:4,created_unix:1792080000,winner_team:1,finish_reason:1,duration_seconds:75,
        interaction_details:None,participants}
}
fn with_details(mut r:Results)->Results{
    let roster=summaries(&r.participants);
    let killer=r.participants.iter().position(|p|p.kills==1).unwrap();
    let shots=[d::Shot{id:1,attacker:killer}];let hit=[d::Hit{shot:1,target:1}];
    let damage=[d::Damage{sequence:1,shot:1,attacker:killer,target:1,health_before:90,health_after:0,lethal:true,reason:0}];
    r.interaction_details=Some(d::project(&roster,&shots,&hit,&hit,&damage,&[],None).unwrap());r
}
fn json(r:&Results)->String{serde_json::to_string(r).unwrap()}

#[test]fn res30_one_owner_and_29_rows_validate_and_round_trip(){
    let r=with_details(roster(MAX_ACTORS));
    assert_eq!(r.participants.len(),30);assert!(r.participants[1..].iter().all(|p|p.account_dbid>=BOT_DATABASE));
    r.validate().unwrap();r.validate_p06t().unwrap();
    let raw=json(&r);assert!(raw.len()>MAX_RESULT_JSON_LEGACY/8);
    assert_eq!(Results::from_json_p06t(&raw).unwrap(),r);
    assert_eq!(r.interaction_details.as_ref().unwrap().rows.len(),30);
    // Every roster size 2..=30 is a valid journal; 31 cannot be decoded.
    for n in 2..=MAX_ACTORS{let r=with_details(roster(n));r.validate_p06t().unwrap();Results::from_json_p06t(&json(&r)).unwrap();}
    let mut too_many=serde_json::to_value(&roster(MAX_ACTORS)).unwrap();
    let extra=too_many["participants"][29].clone();too_many["participants"].as_array_mut().unwrap().push(extra);
    assert!(serde_json::from_value::<Results>(too_many).is_err());
}
#[test]fn res30_kills_bound_follows_the_roster(){
    let mut r=roster(MAX_ACTORS);
    // 15 enemies is the realistic maximum; the validator bound is roster-1.
    r.participants[0].kills=29;r.validate().unwrap();
    r.participants[0].kills=30;assert!(r.validate().is_err()&&r.validate_p06t().is_err());
    let mut six=roster(6);six.participants[0].kills=6;six.validate().unwrap();
}
#[test]fn res30_compact_result_for_thirty_fits_native_stream(){
    let mut r=with_details(roster(MAX_ACTORS));
    // Longest permitted names (48 UTF-8 bytes) for every row.
    for p in &mut r.participants{p.name="Ё".repeat(24);}
    let raw=compact_results_p06t(&r,1).unwrap();assert!(raw.len()<=MAX_RESULT_BYTES,"{}",raw.len());
    let root=inert(&raw);let outer=tuple(&root);assert_eq!(list(&outer[1]).len(),81);
    let Data::Bytes(shared)=&outer[2]else{panic!("shared bytes")};let shared=inert(shared);let shared=tuple(&shared);
    let Data::Dict(players)=&shared[1]else{panic!("players")};assert_eq!(players.len(),30);
    let Data::Dict(vehicles)=&shared[2]else{panic!("vehicles")};assert_eq!(vehicles.len(),30);
    assert!(vehicles.iter().all(|(_,row)|list(row).len()==41));
    // A bot row is an ordinary account-less result row: its DBID only keys players.
    assert!(players.iter().any(|(k,_)|*k==Data::Int(i64::from(BOT_DATABASE)+29)));
    assert!(avatar_result_stream_p06t(&r,1).unwrap().iter().all(|body|body.len()<=512));
    // A bot can never be the personal owner of a native result stream here.
    assert!(compact_results_p06t(&r,1).is_ok());
}
/// Structural maximum: 30 rows, 30 targets each, every scalar at its bound.
fn structural_maximum(n:usize)->Results{
    let participants=(0..n).map(|slot|Participant{vehicle_id:wire::vehicle_id(slot).unwrap(),account_dbid:i32::MAX-slot as i32,
        name:"Ё".repeat(24),team:1+(slot%2) as u8,type_compact_descr:i32::MAX as u32,health:10000,shots:192,direct_hits:192,piercings:192,
        damage_dealt:60000,damage_received:10000,kills:(n-1) as u8,capture_points:600,dropped_capture_points:600,mileage_metres:200000,
        life_time:3600,killer_id:wire::vehicle_id(n-1).unwrap(),death_reason:10,premature_leave:true}).collect::<Vec<_>>();
    let target=|slot:usize|d::Target{vehicle_id:wire::vehicle_id(slot).unwrap(),spotted:1,death_reason:10,direct_hits:u16::MAX,
        explosion_hits:u16::MAX,piercings:u16::MAX,damage_dealt:u16::MAX,damage_assisted_track:u16::MAX,damage_assisted_radio:u16::MAX,crits:u32::MAX,fire:u16::MAX};
    let rows=(0..n).map(|slot|d::Row{attacker_vehicle_id:wire::vehicle_id(slot).unwrap(),targets:(0..n).map(target).collect()}).collect();
    Results{arena_id:i64::MAX as u64,arena_type_id:4,created_unix:u32::MAX,winner_team:2,finish_reason:5,duration_seconds:3600,participants,
        interaction_details:Some(d::Details{version:1,policy:d::POLICY.into(),spotting_policy:Some(d::SPOTTING_POLICY.into()),rows})}
}
#[test]fn res30_result_json_budget_covers_structural_maximum(){
    let six=json(&structural_maximum(6));assert!(six.len()<=MAX_RESULT_JSON_LEGACY,"six rows {}",six.len());
    let max=json(&structural_maximum(MAX_ACTORS));assert!(max.len()<=MAX_RESULT_JSON,"thirty rows {}",max.len());
    // Escaped once inside a writer request / reply.
    let request=serde_json::to_string(&serde_json::json!({"results_json":max,"padding":"x".repeat(4096)})).unwrap();
    assert!(request.len()<=MAX_RESULT_REQUEST,"request {}",request.len());
    // A late seal: the escaped journal and 30 final actors of realistic size,
    // then escaped again inside the append request.
    let actor=serde_json::json!({"account_id":"0".repeat(36),"native_database_id":i32::MAX,"slot":29,"vehicle_id":u32::MAX,"team":2,
        "reservation_id":"r".repeat(96),"native_inventory_id":i32::MAX,"source_contract":"mixed-v2","frozen_sha256":"f".repeat(64),
        "final_actor":{"terminal_hp":10000,"terminal_state":{"policy_revision":"test_lab.p06t.devices-proxy-fire.v1","roster_size":30,"crew_active":false,
            "crew":(0..6).map(|i|serde_json::json!({"crew_id":format!("{}:{i}","c".repeat(90)),"alive":false})).collect::<Vec<_>>(),
            "devices":(0..16).map(|i|serde_json::json!({"extra_index":26+i,"health":60000,"max_health":60000})).collect::<Vec<_>>(),
            "fire":{"active":true,"ticks":216000,"damage":60000},"death":{"reason":10,"killer_slot":29,"tick":216000}},
        "remaining_ammunition":(0..3).map(|_|serde_json::json!({"shell_compact_id":u32::MAX,"count":160})).collect::<Vec<_>>(),
        "fired_ammunition":(0..3).map(|_|serde_json::json!({"shell_compact_id":u32::MAX,"count":160})).collect::<Vec<_>>(),
        "lost_ammunition":(0..3).map(|_|serde_json::json!({"shell_compact_id":u32::MAX,"count":160})).collect::<Vec<_>>(),
        "loss_event":{"shot":4800,"attacker_slot":29,"target_slot":28,"tick":216000,"device_sequence":76800}}});
    let seal=capture::canonical(&serde_json::json!({"version":1,"policy":capture::POLICY,"run_id":"0".repeat(36),"battle_id":"0".repeat(56),
        "arena_id":"9".repeat(19),"results_json":max,"actors":vec![actor;MAX_ACTORS]})).unwrap();
    assert!(seal.len()<=capture::MAX_SEAL_ROSTER30,"seal {}",seal.len());
    assert_eq!(capture::seal_budget(6),capture::MAX_SEAL);assert_eq!(capture::seal_budget(7),capture::MAX_SEAL_ROSTER30);
    let append=serde_json::to_string(&serde_json::json!({"seal_json":seal,"padding":"x".repeat(4096)})).unwrap();
    assert!(append.len()<=capture::MAX_HTTP,"append {}",append.len());
    // The loss-mode writer re-reads the journal as a bounded JSON tree.
    crate::profile13_v2091::bounded_result_json(max.as_bytes()).unwrap();
}
#[test]fn res30_legacy_rows_keep_their_32k_journal_budget(){
    let r=roster(6);r.validate_json_bytes(MAX_RESULT_JSON_LEGACY).unwrap();
    assert!(r.validate_json_bytes(MAX_RESULT_JSON_LEGACY+1).is_err());
    // Insignificant whitespace pads a 6-row journal past 32KiB: still rejected.
    let padded=json(&r)+&" ".repeat(MAX_RESULT_JSON_LEGACY);
    assert!(Results::from_json_p06t(&padded).is_err());
    let seven=roster(7);seven.validate_json_bytes(MAX_RESULT_JSON_LEGACY+1).unwrap();
    assert!(seven.validate_json_bytes(MAX_RESULT_JSON+1).is_err());
    let padded7=json(&seven)+&" ".repeat(MAX_RESULT_JSON_LEGACY);Results::from_json_p06t(&padded7).unwrap();
    assert!(Results::from_json_p06t(&(json(&seven)+&" ".repeat(MAX_RESULT_JSON))).is_err());
}
#[test]fn res30_projection_accepts_thirty_actor_journals(){
    let r=roster(MAX_ACTORS);let roster=summaries(&r.participants);
    let killer=r.participants.iter().position(|p|p.kills==1).unwrap();
    // More than the old 960-shot ceiling: 30 actors × 160 shells.
    let shots=(1..=super::super::model::MAX_BATTLE_SHOTS as u32).map(|id|d::Shot{id,attacker:if id==1{killer}else{(id as usize)%MAX_ACTORS}}).collect::<Vec<_>>();
    let hit=[d::Hit{shot:1,target:1}];
    let damage=[d::Damage{sequence:1,shot:1,attacker:killer,target:1,health_before:90,health_after:0,lethal:true,reason:0}];
    // Only shot 1 hit; the other shots are accepted misses of every actor.
    let summary=roster;
    let details=d::project(&summary,&shots,&hit,&hit,&damage,&[],None).unwrap();details.validate(&summary).unwrap();
    assert!(d::project(&summary,&[shots.clone(),vec![d::Shot{id:u32::MAX,attacker:0}]].concat(),&hit,&hit,&damage,&[],None).is_err());
}
