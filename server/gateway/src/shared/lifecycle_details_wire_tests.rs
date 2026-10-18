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
        while rows.len()<7{rows.push(rows[0].clone());}
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
