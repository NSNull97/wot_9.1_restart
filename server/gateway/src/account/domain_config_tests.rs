//! DOM-01 gateway flag: absent = bridge HTTP for every path; present = exact, loopback, profile13 only.
use super::*;
use super::net02_config_tests::fixture;

fn load(path:&Path,value:&Value)->io::Result<Config>{fs::write(path,serde_json::to_vec(value).unwrap()).unwrap();Config::load(path.to_str().unwrap())}
fn loopback()->(PathBuf,Value,PathBuf){
    let(path,mut value)=fixture();value.as_object_mut().unwrap().remove("game_network");
    value["login_bind"]="127.0.0.1:20130".into();value["base_bind"]="127.0.0.1:20131".into();value["training_rooms"]=false.into();
    let root=PathBuf::from(value["local_root"].as_str().unwrap());fs::write(root.join("domain.secret"),"d".repeat(43)).unwrap();
    (path,value,root)
}

#[test]
fn domain_flag_absent_keeps_bridge_and_present_selects_the_writer_paths_only(){
    let(path,mut value,root)=loopback();
    assert!(load(&path,&value).unwrap().domain_endpoint().is_none());
    value["domain_service"]=serde_json::json!({"version":1,"endpoint":"127.0.0.1:3700","secret_file":root.join("domain.secret")});
    assert_eq!(value.as_object().unwrap().len(),22);
    let config=load(&path,&value).unwrap();
    assert_eq!(config.domain_endpoint().unwrap().to_string(),"127.0.0.1:3700");
    assert_eq!(config.identity_endpoint.to_string(),"127.0.0.1:3491");
}

#[test]
fn domain_flag_is_exact_loopback_bounded_and_refuses_bridge_only_writers(){
    let(path,value,root)=loopback();
    let good=serde_json::json!({"version":1,"endpoint":"127.0.0.1:3700","secret_file":root.join("domain.secret")});
    let outside=std::env::temp_dir().join("dom01-outside.secret");fs::write(&outside,"d".repeat(43)).unwrap();
    fs::write(root.join("short.secret"),"d".repeat(42)).unwrap();
    for wrong in[serde_json::json!(true),serde_json::json!({"version":2,"endpoint":"127.0.0.1:3700","secret_file":root.join("domain.secret")}),
        serde_json::json!({"version":1,"endpoint":"0.0.0.0:3700","secret_file":root.join("domain.secret")}),
        serde_json::json!({"version":1,"endpoint":"127.0.0.1:3491","secret_file":root.join("domain.secret")}),
        serde_json::json!({"version":1,"endpoint":"127.0.0.1:3700","secret_file":outside}),
        serde_json::json!({"version":1,"endpoint":"127.0.0.1:3700","secret_file":root.join("short.secret")}),
        serde_json::json!({"version":1,"endpoint":"127.0.0.1:3700","secret_file":root.join("domain.secret"),"extra":1})]{
        let mut config=value.clone();config["domain_service"]=wrong.clone();assert!(load(&path,&config).is_err(),"{wrong}");
    }
    let mut late=value.clone();late["domain_service"]=good.clone();late["p08c_late_results"]=true.into();
    late["p08c_late_results_accounts"]=serde_json::json!(["5b0b6a52-7d4e-4f1a-9c3b-2e1d0f9a8b7c"]);
    assert!(load(&path,&late).unwrap().domain_endpoint().is_some(),"late results go to the Domain too");
    let mut rooms=value.clone();rooms["domain_service"]=good.clone();rooms["training_rooms"]=true.into();
    assert!(load(&path,&rooms).err().unwrap().to_string().contains("domain_service requires profile13"));
    let mut legacy=value.clone();legacy["domain_service"]=good;for key in["profile13_battle","p04m_pool","p06t_mixed_ammo","visibility_v1","battle_players"]{legacy.as_object_mut().unwrap().remove(key);}
    assert!(load(&path,&legacy).err().unwrap().to_string().contains("domain_service requires profile13"));
}
