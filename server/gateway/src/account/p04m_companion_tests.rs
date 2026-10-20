use super::*;
const ACCOUNT:&str="00000000-0000-0000-0000-000000000001";
fn parse(v:&Value)->io::Result<Binding>{Binding::parse(&serde_json::to_vec(v).unwrap(),ACCOUNT,900001,14,&format!("{:x}",Sha256::digest(b"\x80\x02}.")))}
#[test]fn p04m_companion_loads_three_actual_sqlite_writer_fixtures_and_rejects_legacy_optin(){
    let root=std::env::var_os("WOT091_ROOT").map(std::path::PathBuf::from).unwrap_or_else(||std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../.."));
    let base=root.join("local/evidence/20261016-p04m-writer01/native-fixtures03");
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
