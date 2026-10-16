//! Config-only capability tests. Never connects HTTP or mutates a source DB.
use super::*;
fn setup()->(PathBuf,Value){let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs").join(format!("p08c-late-config-{stamp}"));fs::create_dir_all(&root).unwrap();
    let root=root.canonicalize().unwrap();fs::write(root.join("token.txt"),"a".repeat(43)).unwrap();
    let mut v=serde_json::json!({"login_bind":"127.0.0.1:23014","base_bind":"127.0.0.1:23015","identity_endpoint":"127.0.0.1:3395",
        "identity_token_file":root.join("token.txt"),"local_root":root,"session_duration_seconds":600});
    for key in["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression","crew_dismissal",
        "crew_barracks_recruitment","research_service","profile13_battle","p04m_pool","p06t_mixed_ammo"]{v[key]=true.into();}(root,v)
}
fn load(root:&Path,v:&Value)->io::Result<Config>{let path=root.join("gateway.json");fs::write(&path,serde_json::to_vec(v).unwrap())?;Config::load(path.to_str().unwrap())}
#[test]fn p08c_late_config_disabled_defaults_do_not_enable_original_inferred_notice(){
    let(root,v)=setup();let c=load(&root,&v).unwrap();assert!(!c.p08c_late_results);assert!(c.p08c_late_results_accounts.is_empty());assert!(!c.p08c_late_notice_experimental);
    let mut enabled=v;enabled["p08c_late_results"]=true.into();assert!(load(&root,&enabled).is_err());
    enabled["p08c_late_results_accounts"]=serde_json::json!(["12345678-1234-4234-8234-123456789abc"]);let c=load(&root,&enabled).unwrap();assert!(c.p08c_late_results);assert!(!c.p08c_late_notice_experimental);
    enabled["p08c_late_notice_experimental"]=true.into();assert!(load(&root,&enabled).unwrap().p08c_late_notice_experimental);
    enabled["p08c_late_results"]=false.into();assert!(load(&root,&enabled).is_err());
}
#[test]fn p08c_late_config_exact_owner_allowlist_and_mode_are_closed(){
    let(root,mut v)=setup();v["p08c_late_results"]=true.into();let owner="12345678-1234-4234-8234-123456789abc";
    for list in[serde_json::json!([]),serde_json::json!([owner,owner]),serde_json::json!(["FOREIGN"]),serde_json::json!(["12345678-1234-0234-8234-123456789abc"]),serde_json::json!([null]),Value::Array(vec![Value::String(owner.into());7])]{
        v["p08c_late_results_accounts"]=list;assert!(load(&root,&v).is_err());}
    v["p08c_late_results_accounts"]=serde_json::json!([owner]);assert!(load(&root,&v).is_ok());
    for flag in["p06t_mixed_ammo","profile13_battle"]{let mut bad=v.clone();bad[flag]=false.into();assert!(load(&root,&bad).is_err());}
    for flag in["p08c_late_results","p08c_late_notice_experimental"]{let mut bad=v.clone();bad[flag]="true".into();assert!(load(&root,&bad).is_err());}
    let path=root.join("gateway.json");let mut raw=serde_json::to_string(&v).unwrap();raw.pop();raw.push_str(",\"p08c_late_results\":false}");fs::write(&path,raw).unwrap();assert!(Config::load(path.to_str().unwrap()).is_err());
    assert_eq!(REQUEST_FIELDS,16);
}
