//! GW-01 gateway flag: absent = Table capacity equals battle_players (old path);
//! present = bounded connection count, profile13 only, no training rooms or hold5.
use super::*;
use super::net02_config_tests::fixture;

fn load(path:&Path,value:&Value)->io::Result<Config>{fs::write(path,serde_json::to_vec(value).unwrap()).unwrap();Config::load(path.to_str().unwrap())}
fn loopback()->(PathBuf,Value){
    let(path,mut value)=fixture();value.as_object_mut().unwrap().remove("game_network");
    value["login_bind"]="127.0.0.1:20130".into();value["base_bind"]="127.0.0.1:20131".into();
    value["training_rooms"]=false.into();value["battle_players"]=2.into();
    (path,value)
}

#[test]
fn gw01_capacity_absent_keeps_old_table_and_present_is_bounded_by_roster_and_256(){
    let(path,mut value)=loopback();
    assert_eq!(load(&path,&value).unwrap().connection_capacity,None);
    for n in [2u64,3,200,256]{value["connection_capacity"]=n.into();assert_eq!(load(&path,&value).unwrap().connection_capacity,Some(n as usize));}
    for bad in [serde_json::json!(1),serde_json::json!(0),serde_json::json!(257),serde_json::json!(-1),serde_json::json!(2.5),
        serde_json::json!("256"),serde_json::json!(true),Value::Null,serde_json::json!([256])]{
        value["connection_capacity"]=bad.clone();assert!(load(&path,&value).is_err(),"{bad}");
    }
    value["battle_players"]=6.into();value["connection_capacity"]=5.into();
    assert!(load(&path,&value).is_err(),"capacity below the arena size");
    value["connection_capacity"]=6.into();assert_eq!(load(&path,&value).unwrap().connection_capacity,Some(6));
}

#[test]
fn gw01_capacity_refuses_runtimes_that_start_only_with_every_session_in_the_arena(){
    let(path,value)=loopback();
    let mut rooms=value.clone();rooms["training_rooms"]=true.into();rooms["battle_players"]=6.into();rooms["connection_capacity"]=64.into();
    assert!(load(&path,&rooms).err().unwrap().to_string().contains("connection_capacity requires profile13"));
    let mut legacy=value.clone();legacy["connection_capacity"]=64.into();
    for key in["profile13_battle","p04m_pool","p06t_mixed_ammo","visibility_v1","battle_players"]{legacy.as_object_mut().unwrap().remove(key);}
    assert!(load(&path,&legacy).err().unwrap().to_string().contains("connection_capacity requires profile13"));
    let mut hold=value.clone();hold["connection_capacity"]=64.into();
    for key in["p06t_ammo_rack_detonation","p08b_owner_battle_hold"]{hold[key]=true.into();}
    assert!(load(&path,&hold).is_err());
    hold["p08b_owner_battle_hold"]=false.into();assert_eq!(load(&path,&hold).unwrap().connection_capacity,Some(64));
}

#[test]
fn arena01_arenas_absent_is_one_and_more_need_connections_for_every_arena(){
    let(path,mut value)=loopback();
    assert_eq!(load(&path,&value).unwrap().arenas,1);
    value["arenas"]=1.into();assert_eq!(load(&path,&value).unwrap().arenas,1);
    value["arenas"]=2.into();assert!(load(&path,&value).err().unwrap().to_string().contains("arenas requires connection_capacity"));
    value["connection_capacity"]=3.into();assert!(load(&path,&value).is_err(),"two arenas of two places need four connections");
    value["connection_capacity"]=4.into();assert_eq!(load(&path,&value).unwrap().arenas,2);
    value["connection_capacity"]=256.into();
    for n in [2u64,3,4]{value["arenas"]=n.into();assert_eq!(load(&path,&value).unwrap().arenas,n as usize);}
    for bad in [serde_json::json!(0),serde_json::json!(5),serde_json::json!(-1),serde_json::json!(2.5),serde_json::json!("2"),serde_json::json!(true)]{
        value["arenas"]=bad.clone();assert!(load(&path,&value).is_err(),"{bad}");
    }
}
