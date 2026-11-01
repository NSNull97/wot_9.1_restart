//! Actual serde/native codec tests registered inside lifecycle_wire, Root gate.
use super::*;
fn result()->Results{
    let mut result=tests::result();
    let d=lifecycle_details::project(&summaries(&result.participants),
        &[lifecycle_details::Shot{id:1,attacker:0},lifecycle_details::Shot{id:2,attacker:0},lifecycle_details::Shot{id:3,attacker:0}],
        &[lifecycle_details::Hit{shot:1,target:1},lifecycle_details::Hit{shot:2,target:1},lifecycle_details::Hit{shot:3,target:1}],
        &[lifecycle_details::Hit{shot:1,target:1},lifecycle_details::Hit{shot:2,target:1},lifecycle_details::Hit{shot:3,target:1}],
        &[lifecycle_details::Damage{sequence:1,shot:1,attacker:0,target:1,health_before:90,health_after:60,lethal:false,reason:0},
        lifecycle_details::Damage{sequence:2,shot:2,attacker:0,target:1,health_before:60,health_after:30,lethal:false,reason:0},
        lifecycle_details::Damage{sequence:3,shot:3,attacker:0,target:1,health_before:30,health_after:0,lethal:true,reason:0}],
        &[],Some(&[lifecycle_details::Spot{observer:0,target:1,tick:1001}])).unwrap();
    result.interaction_details=Some(d);result
}
#[test]fn p06t_compact_results_carries_critical_and_fire_counters(){
    let mut result=result();
    let mut details=result.interaction_details.take().unwrap();
    lifecycle_details::apply_module_facts(&mut details,&summaries(&result.participants),&[
        lifecycle_details::Module{attacker:0,target:1,extra_index:27,critical:true,fire:true},
    ]).unwrap();
    result.interaction_details=Some(details);
    let root=tests::inert(&compact_results(&result,1).unwrap());let outer=tests::tuple(&root);
    let personal=tests::list(&outer[1]);
    let fields=PUBLIC_FIELDS.into_iter().chain(PRIVATE_FIELDS).chain(UPDATE_FIELDS).chain(FINAL_FIELDS).collect::<Vec<_>>();
    let get=|name|&personal[fields.iter().position(|f|*f==name).unwrap()];
    let tests::Data::Bytes(packed)=get("details")else{panic!("details bytes")};
    assert_eq!(&packed[18..22],&[1,0,0,0]);
    assert_eq!(&packed[22..24],&[1,0]);
}
fn with_ledger()->Results{
    let mut result=result();
    let mut details=result.interaction_details.take().unwrap();
    lifecycle_details::apply_assists(&mut details,&summaries(&result.participants),&[
        lifecycle_details::Assisted{recipient:1,target:0,track:7,radio:11}]).unwrap();
    result.interaction_details=Some(details);
    let row=|p:&Participant|LedgerRow{vehicle_id:p.vehicle_id,..LedgerRow::default()};
    let mut rows=result.participants.iter().map(row).collect::<Vec<_>>();
    rows[1]=LedgerRow{blocked:300,potential_received:420,assist_spot:11,assist_track:7,..rows[1].clone()};
    rows[0].burned=40;
    result.ledger=Some(Ledger{version:1,policy:LEDGER_POLICY.into(),rows});result
}
fn field_of(result:&Results,own:i32,name:&str)->tests::Data{
    let root=tests::inert(&compact_results(result,own).unwrap());let personal=tests::list(&tests::tuple(&root)[1]);
    let fields=PUBLIC_FIELDS.into_iter().chain(PRIVATE_FIELDS).chain(UPDATE_FIELDS).chain(FINAL_FIELDS).collect::<Vec<_>>();
    personal[fields.iter().position(|f|*f==name).unwrap()].clone()
}
#[test]fn ui04_native_fields_read_the_ledger_and_stay_zero_without_it(){
    let result=with_ledger();
    for(name,value)in [("damageBlockedByArmor",300),("potentialDamageReceived",420),("damageAssistedRadio",11),("damageAssistedTrack",7)]{
        assert_eq!(field_of(&result,2,name),tests::Data::Int(value),"{name}");
        assert_eq!(field_of(&result,1,name),tests::Data::Int(0),"{name}");
    }
    let tests::Data::Bytes(packed)=field_of(&result,2,"details")else{panic!("details bytes")};
    assert_eq!(&packed[0..4],&0x09100003u32.to_le_bytes(),"the target of the assist");
    assert_eq!(&packed[4+10..4+14],&[7,0,11,0],"track then radio, the #717 order");
    let mut old=result.clone();old.ledger=None;
    for row in old.interaction_details.as_mut().unwrap().rows.iter_mut(){row.targets.retain(|t|t.damage_assisted_track==0&&t.damage_assisted_radio==0);}
    assert_eq!(field_of(&old,2,"damageBlockedByArmor"),tests::Data::Int(0));
}
#[test]fn ui04_results9_json_is_closed_and_old_journals_decode_unchanged(){
    let result=with_ledger();let raw=serde_json::to_string(&result).unwrap();
    let decoded:Results=serde_json::from_str(&raw).unwrap();decoded.validate().unwrap();assert_eq!(decoded,result);
    assert_eq!(serde_json::from_str::<serde_json::Value>(&raw).unwrap().as_object().unwrap().len(),9);
    assert!(serde_json::from_str::<Results>(&raw.replacen("\"ledger\":{","\"ledger\":{\"x\":1,",1)).is_err());
    let stored=result_json_without_ledger();
    let old:Results=serde_json::from_str(&stored).unwrap();old.validate().unwrap();
    assert_eq!(old.ledger,None);assert_eq!(serde_json::to_string(&old).unwrap(),stored,"a stored battle stays byte for byte");
}
fn result_json_without_ledger()->String{serde_json::to_string(&result()).unwrap()}
#[test]fn ui04_validator_refuses_a_ledger_that_disagrees(){
    assert!(with_ledger().validate().is_ok());
    let broken:[fn(&mut Results);9]=[
        |r|r.interaction_details=None,
        |r|r.ledger=None,
        |r|r.ledger.as_mut().unwrap().version=2,
        |r|r.ledger.as_mut().unwrap().policy="fake".into(),
        |r|{r.ledger.as_mut().unwrap().rows.pop();},
        |r|r.ledger.as_mut().unwrap().rows[1].assist_spot=12,
        |r|r.ledger.as_mut().unwrap().rows[1].assist_track=8,
        |r|r.ledger.as_mut().unwrap().rows[1].blocked=421,
        |r|r.ledger.as_mut().unwrap().rows[0].burned=91,
    ];
    for(index,poison)in broken.into_iter().enumerate(){
        let mut value=with_ledger();poison(&mut value);assert!(value.validate().is_err(),"{index}");
    }
    let mut ally=with_ledger();ally.participants[1].team=1;ally.participants[0].team=1;
    assert!(ally.validate().is_err(),"both teams, and an assist on an ally never validates");
    let mut own=with_ledger();
    let details=own.interaction_details.as_mut().unwrap();
    details.rows[0].targets.push(lifecycle_details::Target{vehicle_id:0x09100003,death_reason:-1,damage_assisted_radio:1,..Default::default()});
    own.ledger.as_mut().unwrap().rows[0].assist_spot=1;
    assert!(own.validate().is_err(),"assist on oneself");
}
#[test]fn p08c_personal_closed_old7_and_new8_json_serde(){
    let old=tests::result();let raw=serde_json::to_string(&old).unwrap();
    assert_eq!(serde_json::from_str::<Results>(&raw).unwrap(),old);
    assert_eq!(serde_json::from_str::<serde_json::Value>(&raw).unwrap().as_object().unwrap().len(),7);
    let result=result();let raw=serde_json::to_string(&result).unwrap();
    let decoded:Results=serde_json::from_str(&raw).unwrap();decoded.validate().unwrap();assert_eq!(decoded,result);
    assert_eq!(serde_json::from_str::<serde_json::Value>(&raw).unwrap().as_object().unwrap().len(),8);
    assert!(serde_json::from_str::<Results>(&raw.replacen("\"interaction_details\":{","\"interaction_details\":null,\"x\":{",1)).is_err());
    assert!(serde_json::from_str::<Results>(&raw.replacen("\"version\":1","\"version\":1,\"version\":1",1)).is_err());
}
#[test]fn p08c_personal_nested_bounds_are_checked_while_decoding(){
    let good=serde_json::to_value(result()).unwrap();
    for outer in [true,false]{let mut bad=good.clone();
        let rows=if outer{bad["interaction_details"]["rows"].as_array_mut().unwrap()}
            else{bad["interaction_details"]["rows"][0]["targets"].as_array_mut().unwrap()};
        // RES-30: the decoding bound follows the 30-actor roster.
        while rows.len()<=MAX_PARTICIPANTS{rows.push(rows[0].clone());}
        assert!(serde_json::from_value::<Results>(bad).is_err());
    }
    let mut bad=good;bad["interaction_details"]["rows"][0]["targets"][0]["damage_dealt"]=89.into();
    assert!(serde_json::from_value::<Results>(bad).unwrap().validate().is_err());
}
#[test]fn p08c_personal_native_personal_and_public_use_same_checked_snapshot(){
    let result=result();let root=tests::inert(&compact_results(&result,1).unwrap());let outer=tests::tuple(&root);
    let personal=tests::list(&outer[1]);let fields=PUBLIC_FIELDS.into_iter().chain(PRIVATE_FIELDS).chain(UPDATE_FIELDS).chain(FINAL_FIELDS).collect::<Vec<_>>();
    let get=|name|&personal[fields.iter().position(|f|*f==name).unwrap()];
    let bytes=result.interaction_details.as_ref().unwrap().packed(0x09100003).unwrap();
    // Independent original format: one target ID, then B,b,6H,I,H.
    assert_eq!(bytes,vec![5,0,16,9,1,0,3,0,0,0,3,0,90,0,0,0,0,0,0,0,0,0,0,0]);
    assert_eq!(get("details"),&tests::Data::Bytes(bytes));assert_eq!(get("spotted"),&tests::Data::Int(1));
    assert_eq!(get("damaged"),&tests::Data::Int(1));assert_eq!(get("kills"),&tests::Data::Int(1));
    let tests::Data::Bytes(shared)=&outer[2]else{panic!("shared bytes")};
    let shared=tests::inert(shared);let shared=tests::tuple(&shared);
    let tests::Data::Dict(vehicles)=&shared[2]else{panic!("vehicles")};
    assert_eq!(tests::list(&vehicles[1].1)[17],tests::Data::Int(3));
    assert_eq!(tests::list(&vehicles[1].1)[20],tests::Data::Int(3));
    let victim=tests::inert(&compact_results(&result,2).unwrap());
    let victim=tests::tuple(&victim);let victim=tests::list(&victim[1]);
    assert_eq!(victim[fields.iter().position(|f|*f=="details").unwrap()],tests::Data::Bytes(vec![]));
}
