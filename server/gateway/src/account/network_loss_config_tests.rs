//! Authored combined config fixtures; no network/native ownership proof.
use super::*;
fn full()->(PathBuf,Value){
    let(path,mut value)=super::net02_config_tests::fixture();
    for key in ["p06t_ammo_rack_detonation","p08c_late_results"]{value[key]=true.into();}
    value["p08c_late_results_accounts"]=serde_json::json!(["c5326cc1-8524-479c-8bba-72e973489c22","271022a3-41e0-406e-b6fa-59930c320442"]);
    value["p08c_late_notice_experimental"]=false.into();
    assert_eq!(value.as_object().unwrap().len(),26);(path,value)
}
#[test]
fn net02_loss_full26_config_keeps_loss_late_and_training_with_http16(){
    let(path,value)=full();fs::write(&path,serde_json::to_vec(&value).unwrap()).unwrap();
    let c=Config::load(path.to_str().unwrap()).unwrap();
    assert!(c.p06t_ammo_rack_detonation&&c.p08c_late_results&&c.training_rooms&&c.game_network().is_lan());
    assert_eq!(c.p08c_late_results_accounts.len(),2);assert!(!c.p08c_late_notice_experimental);
    assert_eq!(REQUEST_FIELDS,16);assert_eq!(c.identity_endpoint.to_string(),"127.0.0.1:3491");
    c.require_game_network(game_network::Runtime::SharedOwnedProfile13).unwrap();
}
#[test]
fn net02_loss_full26_nested_duplicate_stays_rejected_before_value_decode(){
    let(path,value)=full();let raw=serde_json::to_string(&value).unwrap();
    for pair in [r#""mode":"lan_test""#,r#""advertised_base":"192.168.50.10:20131""#]{
        let poisoned=raw.replacen(r#""game_network":{"#,&format!(r#""game_network":{{{pair},"#),1);
        assert_ne!(raw,poisoned);fs::write(&path,poisoned).unwrap();assert!(Config::load(path.to_str().unwrap()).is_err());
    }
}
#[test]
fn net02_loss_config_only28_budget_does_not_expand_request16(){
    let json=|count:usize|serde_json::to_vec(&(0..count).map(|n|(format!("key{n}"),Value::Null)).collect::<BTreeMap<_,_>>()).unwrap();
    assert!(serde_json::from_slice::<ConfigFields>(&json(28)).is_ok());
    assert!(serde_json::from_slice::<ConfigFields>(&json(29)).is_err());
    assert!(serde_json::from_slice::<Bounded<REQUEST_FIELDS>>(&json(16)).is_ok());
    assert!(serde_json::from_slice::<Bounded<REQUEST_FIELDS>>(&json(17)).is_err());
}
