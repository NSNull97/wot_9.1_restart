use super::*;
const ACCOUNT:&str="00000000-0000-0000-0000-000000000001";
fn parse(v:&Value)->io::Result<Binding>{Binding::parse(&serde_json::to_vec(v).unwrap(),ACCOUNT,900001,14,&format!("{:x}",Sha256::digest(b"\x80\x02}.")))}
#[test]fn p04m_companion_loads_three_actual_sqlite_writer_fixtures_and_rejects_legacy_optin(){
    let root=std::env::var_os("WOT091_ROOT").map(std::path::PathBuf::from).unwrap_or_else(||std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../.."));
    let base=root.join("local/evidence/20261031-cat-nations-restamp/p04m-native-fixtures03");
    let owner="c5326cc1-8524-479c-8bba-72e973489c22";
    for(name,kind,revision,state_sha,companion_sha)in[
        ("t26-ap160",Kind::T26,23,"1f9e917a57145d67fe50f479bc3ce0d437997ca15ba827fea600ab8e02022f20","80923e925c94126bfbab6cffca2fd28bdcb3833654b7c6f0b877ab7925236fe8"),
        ("t34-full-crew",Kind::T34,33,"7bff0ded7639eed2e24ac5f0bc9164e667a04eed46f5379f52613a3926734142","56ce372f2e8bd17631843d1ef811041a8aa78b15c0c13c82d0e2adb306931403"),
        ("t3485-full-crew",Kind::T3485,37,"9eeff48a5366b73a8e7464151f1bc62e6d92ccf156309c6e88d6dee448feeb20","297c0e6dff027537d4db412e1beb166e70ca85ac9586d5525f72f6adc68d94ca"),
    ]{
        let directory=base.join(name);let raw=std::fs::read(directory.join("p04m-pool.json")).expect("actual writer export required");
        assert_eq!(format!("{:x}",Sha256::digest(&raw)),companion_sha);
        assert_eq!(format!("{:x}",Sha256::digest(std::fs::read(directory.join("state.bin")).unwrap())),state_sha);
        let p=Binding::metadata(&directory,owner,1,revision).unwrap();assert_eq!(p.kind(3).unwrap(),kind);
        let fixtures=crate::hangar091::Fixtures::load_p04m(&directory).unwrap();
        assert!(fixtures.p04m_binding().unwrap().matches(owner,1,revision));assert!(crate::hangar091::Fixtures::load_research(&directory).is_err());
        let(shells,capacity)=kind.ammo();let request=crate::ammo_service091::Request{id:230,arguments:[5,3,6,shells[0],capacity as i32,shells[1],0,shells[2],0,6,0,0,0,0,0,0]};
        assert_eq!(p.ammo_layout(&request).unwrap()[0].count,capacity);
        assert!(Binding::parse(&raw,ACCOUNT,1,revision,state_sha).is_err());
    }
}
#[test]fn p04m_companion_binds_actual_owner_source_kind_and_closed_admission(){
    let good=test_value(ACCOUNT,14);let p=parse(&good).unwrap();
    assert_eq!(p.kind(3).unwrap(),Kind::T34);assert_eq!(p.kind(7).unwrap(),Kind::T26);
    for n in 0..22{
        let mut v=good.clone();match n{
            0=>v["account_id"]="foreign".into(),1=>v["native_database_id"]=900002.into(),2=>v["revision"]=13.into(),
            3=>v["state_sha256"]="b".repeat(64).into(),4=>v["definition_sha256"]="b".repeat(64).into(),5=>v["registry_sha256"]="b".repeat(64).into(),
            6=>v["policy_sha256"]="b".repeat(64).into(),7=>v["crew_policy_sha256"]="b".repeat(64).into(),8=>v["ammo_catalog_sha256"]="b".repeat(64).into(),
            9=>v["capabilities"][2]["vehicle_inventory_id"]=format!("{ACCOUNT}:p09e-vehicle:4").into(),10=>v["capabilities"][2]["assembly_id"]="t26-stock".into(),
            11=>v["capabilities"][2]["native_inventory_id"]=2.into(),12=>v["capabilities"][2]["kind"]="is7".into(),
            13=>v["capabilities"][2]["admission"]=true.into(),14=>v["capabilities"][2]["readiness_code"]=Value::Null,
            15=>v["capabilities"][2]["extra"]=true.into(),16=>v["capabilities"][0]["kind"]="t34".into(),
            17=>v["crew_capacity"]=17.into(),18=>v["version"]=true.into(),19=>v["extra"]=true.into(),
            20=>{v["capabilities"].as_array_mut().unwrap().remove(0);},21=>v["capabilities"][2]["readiness_code"]="INCOMPLETE_CREW".into(),_=>unreachable!(),
        }assert!(parse(&v).is_err(),"mutation={n}");
    }
    // An upgraded/non-stock owned vehicle is explicit unsupported, never guessed.
    let mut unsupported=good;unsupported["capabilities"][0]["assembly_id"]=Value::Null;
    unsupported["capabilities"][0]["readiness_code"]="BATTLE_PROFILE_UNSUPPORTED".into();unsupported["capabilities"][0]["admission"]=false.into();
    let p=parse(&unsupported).unwrap();assert_eq!(p.kind(1).unwrap(),Kind::Ms1);
    p.recruit(crate::crew_service091::Request{id:230,shop_revision:3,vehicle_inventory_id:1,slot:1,tariff_index:0}).unwrap();
    assert!(p.ammo_layout(&crate::ammo_service091::Request{id:230,arguments:[5,1,6,2570,20,2826,0,3082,0,6,0,0,0,0,0,0]}).is_ok());
}
#[test]fn p04m_companion_rejects_duplicate_fields_at_both_levels_and_bounded_input(){
    let good=serde_json::to_string(&test_value(ACCOUNT,14)).unwrap();let sha=format!("{:x}",Sha256::digest(b"\x80\x02}."));
    for raw in [good.replacen("\"version\":1","\"version\":1,\"version\":1",1),
        good.replacen("\"native_inventory_id\":3","\"native_inventory_id\":3,\"native_inventory_id\":7",1)," ".repeat(65537)]{
        assert!(Binding::parse(raw.as_bytes(),ACCOUNT,900001,14,&sha).is_err());
    }
}
#[test]fn p04m_companion_ammo_all_five_capacities_and_native_ids_are_independent(){
    let p=test_binding(ACCOUNT,14);
    for (native,kind)in[(1,Kind::Ms1),(2,Kind::Is7),(3,Kind::T34),(4,Kind::T3485),(7,Kind::T26)]{
        let(shells,capacity)=kind.ammo();let mut r=crate::ammo_service091::Request{id:230,arguments:[5,native,6,shells[0],capacity as i32,shells[1],0,shells[2],0,6,0,0,0,0,0,0]};
        assert_eq!(p.ammo_layout(&r).unwrap()[0].count,capacity);
        r.arguments[4]+=1;assert!(p.ammo_layout(&r).is_err());r.arguments[4]-=1;
        r.arguments[3]=-shells[0];assert!(p.ammo_layout(&r).is_ok());
        r.arguments[5]=shells[0];assert!(p.ammo_layout(&r).is_err());
    }
    let r=crate::ammo_service091::Request{id:230,arguments:[5,7,6,1034,160,1290,0,1546,0,6,0,0,0,0,0,0]};
    assert!(r.layout().is_err());assert!(p.ammo_layout(&r).is_ok());
    for native in[0,5,4609]{let mut bad=r.clone();bad.arguments[1]=native;assert!(p.ammo_layout(&bad).is_err());}
}
#[test]fn p04m_companion_primary_seats_include_radioman_and_keep_legacy_closed(){
    let p=test_binding(ACCOUNT,14);
    for(native,count)in[(1,2),(2,5),(3,4),(4,5),(7,3)]{
        for slot in 0..count{let r=crate::crew_service091::Request{id:230,shop_revision:3,vehicle_inventory_id:native,slot,tariff_index:0};p.recruit(r).unwrap();}
        assert!(p.recruit(crate::crew_service091::Request{id:230,shop_revision:3,vehicle_inventory_id:native,slot:count,tariff_index:0}).is_err());
    }
    let radio=crate::crew_barracks091::Request{id:230,shop_revision:3,vehicle_type:1,role:2,cost:0};p.barracks(radio).unwrap();assert!(radio.validate_supported().is_err());
    let transfer=crate::crew_transfer091::Request{id:231,vehicle_inventory_id:3,slot:1,tankman_inventory_id:16};p.transfer(transfer).unwrap();assert!(transfer.validate_for(crate::crew_transfer091::Profile::Barracks).is_err());
    for role in[1,3,4]{p.barracks(crate::crew_barracks091::Request{vehicle_type:4609,role,..radio}).unwrap();}
    assert!(p.barracks(crate::crew_barracks091::Request{vehicle_type:4609,role:5,..radio}).is_err());
    assert!(p.barracks(crate::crew_barracks091::Request{vehicle_type:4609,role:2,..radio}).is_err());
    for wire in[0,i32::MAX as i64]{assert!(p.service_request("key",14,wire,&[3,1,2,0]).is_err());}
}

fn v2_value()->Value{let mut v=test_value(ACCOUNT,14);v["crew_policy_sha256"]=CREW_V2_POLICY_SHA256.into();v["crew_capacity"]=192.into();v}
fn hex(text:&str)->Vec<u8>{(0..text.len()).step_by(2).map(|i|u8::from_str_radix(&text[i..i+2],16).unwrap()).collect()}
#[test]fn p04m_companion_crew_contract_v2_is_selected_only_by_the_writer_pair(){
    assert_eq!(parse(&test_value(ACCOUNT,14)).unwrap().capacity(),16);
    assert_eq!(parse(&v2_value()).unwrap().capacity(),192);
    for(sha,capacity)in[(CREW_POLICY_SHA256,192),(CREW_V2_POLICY_SHA256,16),(CREW_V2_POLICY_SHA256,193),(CREW_POLICY_SHA256,17)]{
        let mut v=test_value(ACCOUNT,14);v["crew_policy_sha256"]=sha.into();v["crew_capacity"]=capacity.into();assert!(parse(&v).is_err(),"{sha}/{capacity}");
    }
    let(v1,v2)=(parse(&test_value(ACCOUNT,14)).unwrap(),parse(&v2_value()).unwrap());
    for(id,ok1,ok2)in[(1i64,true,true),(16,true,true),(17,false,true),(192,false,true),(193,false,false),(0,false,false)]{
        let t=crate::crew_transfer091::Request{id:231,vehicle_inventory_id:3,slot:1,tankman_inventory_id:id as i32};
        let d=crate::crew_dismissal091::Request{id:231,tankman_inventory_id:id,reserved_a:0,reserved_b:0};
        let s=crate::crew_progression091::Request{id:231,tankman_inventory_id:id,skill_index:6,reserved:0};
        assert_eq!((v1.transfer(t).is_ok(),v1.dismiss(d).is_ok(),v1.learn(s).is_ok()),(ok1,ok1,ok1),"v1 {id}");
        assert_eq!((v2.transfer(t).is_ok(),v2.dismiss(d).is_ok(),v2.learn(s).is_ok()),(ok2,ok2,ok2),"v2 {id}");
    }
    assert!(v2.dismiss(crate::crew_dismissal091::Request{id:231,tankman_inventory_id:20,reserved_a:1,reserved_b:0}).is_err());
    assert!(v2.learn(crate::crew_progression091::Request{id:231,tankman_inventory_id:20,skill_index:18,reserved:0}).is_err());
}
#[test]fn p04m_companion_v2_actual_writer_barracks_vector_id32_wrapped_icon(){
    // tests/test_p04m_pool_crew_v2.py actual isolated SQLite writer vector:
    // CMD303 IS-7 gunner, identity 32 -> names (32,32,2), freeTMenLeft 160.
    let descriptor:[u8;25]=hex("081c0432000000200020000200400600000000420000000000").try_into().unwrap();
    let update=hex("80027d285507707265765265764b0155037265764b025509696e76656e746f72797d284b087d28550776656869636c657d284b204affffffff755509636f6d7044657363727d284b205519081c0432000000200020000200400600000000420000000000757575550573746174737d28550c66726565544d656e4c6566744ba075752e");
    let member=crate::crew_barracks091::Recruitment{tankman_id:32,descriptor};
    let request=crate::crew_barracks091::Request{id:230,shop_revision:3,vehicle_type:7169,role:4,cost:0};
    let v2=parse(&v2_value()).unwrap();v2.validate_recruitment(&member,request,1,&update).unwrap();
    assert!(parse(&test_value(ACCOUNT,14)).unwrap().validate_recruitment(&member,request,1,&update).is_err());
    assert!(member.validate_delta(request,1,&update).is_err());
    assert!(member.success_response(226).is_err());
    assert_eq!(member.success_response_within(226,192).unwrap()[1],0x4d);
    let mut forged=member.clone();forged.descriptor[11]=32;assert!(v2.validate_recruitment(&forged,request,1,&update).is_err());
    let mut stale=update.clone();let n=stale.len();stale[n-5]=176;assert!(v2.validate_recruitment(&member,request,1,&stale).is_err());
}

/// BATTLE-ANY stage 3c: a bought generated catalog vehicle (KV-3) on the v1 companion.
#[test]fn p04m_companion_carries_a_generated_catalog_kind_only_in_catalog_mode(){
    let mut v=test_value(ACCOUNT,14);
    v["capabilities"].as_array_mut().unwrap().push(serde_json::json!({"native_inventory_id":8,"vehicle_inventory_id":format!("{ACCOUNT}:p09e-vehicle:8"),
        "kind":"ussr-KV-3","assembly_id":"ussr-KV-3-stock","readiness_code":"BATTLE_PROFILE_UNSUPPORTED","admission":false}));
    let raw=|v:&Value|serde_json::to_vec(v).unwrap();let state=format!("{:x}",Sha256::digest(b"\x80\x02}."));
    let with=|v:&Value,catalog:bool|Binding::parse_with(&raw(v),ACCOUNT,900001,14,&state,catalog);
    assert!(with(&v,false).is_err(),"legacy mode keeps the closed kind list");
    let p=with(&v,true).unwrap();let kind=p.kind(8).unwrap();
    let row=catalog::by_kind("ussr-KV-3").unwrap();
    assert_eq!((kind.label(),kind.type_cd()),("ussr-KV-3",row.native_compact_id as i32));
    assert_eq!(kind.ammo(),([0,1,2].map(|i|row.shells[i].native_compact_id as i32),u32::from(row.ammo_capacity)));
    assert_eq!(kind.primary_roles().len(),row.seats);assert!(kind.primary_roles().iter().all(|r|(1..=5).contains(r)));
    // The v1 P08B route never admits it and needs the exact v1 refusal.
    for n in 0..4{let mut w=v.clone();let row=&mut w["capabilities"][5];match n{
        0=>row["admission"]=true.into(),1=>row["readiness_code"]="OWNER_ACCEPTANCE_REQUIRED".into(),
        2=>row["assembly_id"]="ussr-KV1-stock".into(),3=>row["kind"]="ussr-KV1".into(),_=>unreachable!()}
        assert!(with(&w,true).is_err(),"mutation={n}");}
    // Barracks recruitment for its type is accepted with a source primary role only.
    let roles=kind.primary_roles();
    let ok=crate::crew_barracks091::Request{id:1,shop_revision:3,cost:0,vehicle_type:kind.type_cd(),role:roles[0]};
    assert!(p.barracks(ok).is_ok());
    assert!(p.barracks(crate::crew_barracks091::Request{role:0,..ok}).is_err());
}

/// BATTLE-ANY 3d: the free50 passport follows the recruited type's nation.
#[test]fn p04m_companion_passport_sets_follow_the_nation_and_keep_ussr_v1(){
    let ussr=passport_sets(0).unwrap();
    for id in 4..=192u8{let old=[112u16,1036,30].map(|bound|(u16::from(id)-1)%bound+1);
        assert_eq!([0,1,2].map(|i|passport_id(&ussr[i],id)),old,"id={id}");}
    let japan=passport_sets(6).unwrap();assert!(japan[1].len()>1,"japan surnames are not contiguous");
    for id in [4u8,100,192]{let v=passport_id(&japan[1],id);assert!(japan[1].iter().any(|(a,b)|(*a..=*b).contains(&v)));}
    assert_eq!(passport_id(&passport_sets(2).unwrap()[2],37),1,"usa icons 1..36 wrap at 37");
    assert!(passport_sets(9).is_err());
}
