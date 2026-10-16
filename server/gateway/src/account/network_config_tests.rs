//! Authored bounded local config fixtures only; no native/ownership/LAN proof.
use super::*;
pub(crate) fn fixture()->(PathBuf,Value){
    static NEXT:std::sync::atomic::AtomicU64=std::sync::atomic::AtomicU64::new(1);
    let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let id=NEXT.fetch_add(1,std::sync::atomic::Ordering::Relaxed);
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs").join(format!("net02-config-{stamp}-{id}"));
    fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();fs::write(root.join("token.txt"),"a".repeat(43)).unwrap();
    let mut value=serde_json::json!({"login_bind":"192.168.50.10:20130","base_bind":"192.168.50.10:20131",
        "identity_endpoint":"127.0.0.1:3491","identity_token_file":root.join("token.txt"),"local_root":root,
        "session_duration_seconds":600,"game_network":{"version":1,"mode":"lan_test","advertised_base":"192.168.50.10:20131",
            "allowed_peer_cidrs":["192.168.50.10/32","192.168.50.11/32"]}});
    for key in["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression",
        "crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle","p04m_pool","p06t_mixed_ammo","visibility_v1","training_rooms"]{value[key]=true.into();}
    value["battle_players"]=6.into();(root.join("gateway.json"),value)
}
pub(crate) fn lan_file()->PathBuf{let(path,value)=fixture();fs::write(&path,serde_json::to_vec(&value).unwrap()).unwrap();path}
fn load(path:&Path,value:&Value)->io::Result<Config>{fs::write(path,serde_json::to_vec(value).unwrap()).unwrap();Config::load(path.to_str().unwrap())}

#[test]
fn net02_config_accepts22_fields_without_changing_http16_and_keeps_identity_loopback(){
    let(path,value)=fixture();assert_eq!(value.as_object().unwrap().len(),22);assert_eq!(REQUEST_FIELDS,16);
    let config=load(&path,&value).unwrap();assert!(config.game_network().is_lan());
    assert_eq!(config.identity_endpoint.to_string(),"127.0.0.1:3491");
    config.require_game_network(game_network::Runtime::SharedOwnedProfile13).unwrap();
    assert_eq!(config.require_game_network(game_network::Runtime::LoopbackOnly).unwrap_err().to_string(),game_network::UNSUPPORTED_RUNTIME);
    for address in["192.168.50.10:3491","0.0.0.0:3491","localhost:3491","[::1]:3491"]{
        let mut wrong=value.clone();wrong["identity_endpoint"]=address.into();assert!(load(&path,&wrong).is_err());
    }
    for key in["profile13_battle","p04m_pool","p06t_mixed_ammo"]{let mut wrong=value.clone();wrong[key]=false.into();assert!(load(&path,&wrong).is_err());}
    let mut config=load(&path,&value).unwrap();config.base_bind="192.168.50.10:20132".parse().unwrap();
    assert!(config.require_game_network(game_network::Runtime::SharedOwnedProfile13).is_err());
}

#[test]
fn net02_config_default_complete21_and_minimum6_old_shapes_remain_loopback_only(){
    let(path,mut value)=fixture();value.as_object_mut().unwrap().remove("game_network");
    value["login_bind"]="127.0.0.1:20130".into();value["base_bind"]="127.0.0.1:20131".into();
    assert_eq!(value.as_object().unwrap().len(),21);let config=load(&path,&value).unwrap();assert!(!config.game_network().is_lan());
    config.require_game_network(game_network::Runtime::LoopbackOnly).unwrap();
    for key in["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression",
        "crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle","p04m_pool","p06t_mixed_ammo","visibility_v1","training_rooms","battle_players"]{
        value.as_object_mut().unwrap().remove(key);
    }
    assert_eq!(value.as_object().unwrap().len(),6);assert!(!load(&path,&value).unwrap().game_network().is_lan());
    value["login_bind"]="192.168.50.10:20130".into();assert!(load(&path,&value).is_err());
}

#[test]
fn net02_config_streaming_visitor_rejects_raw_nested_and_outer_duplicates(){
    let(path,value)=fixture();let raw=serde_json::to_string(&value).unwrap();
    for pair in[r#""version":1"#,r#""mode":"lan_test""#,r#""advertised_base":"192.168.50.10:20131""#,
        r#""allowed_peer_cidrs":["192.168.50.11/32"]"#]{
        let poison=raw.replacen(r#""game_network":{"#, &format!(r#""game_network":{{{pair},"#),1);
        assert_ne!(poison,raw);fs::write(&path,poison).unwrap();assert!(Config::load(path.to_str().unwrap()).is_err());
    }
    for field in[r#""game_network":null"#,r#""profile13_battle":true"#]{
        fs::write(&path,format!("{},{} }}",&raw[..raw.len()-1],field)).unwrap();assert!(Config::load(path.to_str().unwrap()).is_err());
    }
    let mut extra=value.clone();extra["extra1"]=0.into();extra["extra2"]=0.into();assert_eq!(extra.as_object().unwrap().len(),24);
    assert!(load(&path,&extra).is_err());fs::write(&path,vec![b' ';4097]).unwrap();assert!(Config::load(path.to_str().unwrap()).is_err());
}
