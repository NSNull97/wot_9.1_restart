use super::*;
fn wire_with(peers:&[String])->LanWire{
    serde_json::from_value(serde_json::json!({"version":1,"mode":"lan_test","advertised_base":"192.168.50.10:20131",
        "allowed_peer_cidrs":peers})).unwrap()
}
fn lan()->Network{Network::parse("192.168.50.10:20130","192.168.50.10:20131",
    Some(wire_with(&["192.168.50.10/32".into(),"192.168.50.11/32".into()]))).unwrap()}

#[test]
fn net02_default_network_is_exact_numeric_loopback_and_binds_are_fenced(){
    let network=Network::parse("127.0.0.1:20130","127.0.0.1:20131",None).unwrap();
    assert!(!network.is_lan());assert_eq!(network.advertised_base().address(),network.base_bind());
    for mode in[Runtime::LoopbackOnly,Runtime::SharedOwnedProfile13]{
        network.require_runtime(mode,network.login_bind(),network.base_bind()).unwrap();
    }
    for peer in["127.0.0.2:50000","192.168.50.11:50000","[::1]:50000"]{assert!(!network.allows_peer(peer.parse().unwrap()));}
    assert!(network.allows_peer("127.0.0.1:50000".parse().unwrap()));
    assert!(network.require_runtime(Runtime::LoopbackOnly,"192.168.50.10:20130".parse().unwrap(),network.base_bind()).is_err());
    for bad in["0.0.0.0:20130","localhost:20130","192.168.50.10:20130","127.0.0.1:0"]{
        assert!(Network::parse(bad,"127.0.0.1:20131",None).is_err());
    }
}

#[test]
fn net02_lan_requires_concrete_same_host_advertised_base_and_explicit_runtime(){
    let network=lan();
    assert_eq!(network.require_runtime(Runtime::LoopbackOnly,network.login_bind(),network.base_bind()).unwrap_err().to_string(),UNSUPPORTED_RUNTIME);
    network.require_runtime(Runtime::SharedOwnedProfile13,network.login_bind(),network.base_bind()).unwrap();
    for(login,base)in[("0.0.0.0:20130","192.168.50.10:20131"),("8.8.8.8:20130","8.8.8.8:20131"),
        ("192.168.50.10:1023","192.168.50.10:20131"),("192.168.50.11:20130","192.168.50.10:20131"),
        ("192.168.50.10:20130","192.168.50.10:20132"),("192.168.50.10:20131","192.168.50.10:20131")]{
        assert!(Network::parse(login,base,Some(wire_with(&["192.168.50.11/32".into()]))).is_err());
    }
}

#[test]
fn net02_lan_peers_are_closed_canonical_unique_host_cidrs(){
    let accepted=(1..=24).map(|n|format!("10.0.0.{n}/32")).collect::<Vec<_>>();
    let network=Network::parse("192.168.50.10:20130","192.168.50.10:20131",Some(wire_with(&accepted))).unwrap();
    assert!(network.allows_peer("10.0.0.24:65535".parse().unwrap()));
    assert!(!network.allows_peer("10.0.0.25:50000".parse().unwrap()));
    for peers in[vec![],vec!["10.0.0.1/32";2],(0..25).map(|_|"10.0.0.1/32").collect()]{
        let value=serde_json::json!({"version":1,"mode":"lan_test","advertised_base":"192.168.50.10:20131","allowed_peer_cidrs":peers});
        assert!(serde_json::from_value::<LanWire>(value).is_err());
    }
    let unique25=(1..=25).map(|n|format!("10.0.0.{n}/32")).collect::<Vec<_>>();
    let value=serde_json::json!({"version":1,"mode":"lan_test","advertised_base":"192.168.50.10:20131","allowed_peer_cidrs":unique25});
    assert!(serde_json::from_value::<LanWire>(value).is_err());
    for peer in["0.0.0.0/32","8.8.8.8/32","127.0.0.1/32","169.254.1.1/32","224.0.0.1/32","255.255.255.255/32",
        "192.168.050.11/32","192.168.50.11/31","192.168.50.11/0","192.168.50.11/33","192.168.50.11/+32",
        "192.168.50.11","192.168.50.11/32/32"," 192.168.50.11/32","192.168.50.11/32 ","localhost/32","::1/32","::ffff:192.168.50.11/32"]{
        let value=serde_json::json!({"version":1,"mode":"lan_test","advertised_base":"192.168.50.10:20131","allowed_peer_cidrs":[peer]});
        assert!(serde_json::from_value::<LanWire>(value).is_err(),"{peer}");
    }
    // Host bits are not inferred from a private /32. Actual interface ownership
    // and broadcast reachability remain a later OS/native gate.
    for peer in["10.0.0.0/32","10.0.0.255/32","172.16.0.1/32","172.31.255.255/32","192.168.255.255/32"]{
        let value=serde_json::json!({"version":1,"mode":"lan_test","advertised_base":"192.168.50.10:20131","allowed_peer_cidrs":[peer]});
        assert!(serde_json::from_value::<LanWire>(value).is_ok());
    }
}

#[test]
fn net02_raw_nested_duplicates_unknowns_and_wrong_types_fail_before_validation(){
    let raw=r#"{"version":1,"mode":"lan_test","advertised_base":"192.168.50.10:20131","allowed_peer_cidrs":["192.168.50.11/32"]}"#;
    assert!(serde_json::from_str::<LanWire>(raw).is_ok());
    for extra in[r#""version":1"#,r#""mode":"lan_test""#,r#""advertised_base":"192.168.50.10:20131""#,
        r#""allowed_peer_cidrs":["192.168.50.11/32"]"#,r#""unknown":1"#]{
        let duplicate=format!("{},{} }}",&raw[..raw.len()-1],extra);
        assert!(serde_json::from_str::<LanWire>(&duplicate).is_err());
    }
    for key in["version","mode","advertised_base","allowed_peer_cidrs"]{
        let mut value:serde_json::Value=serde_json::from_str(raw).unwrap();value[key]=serde_json::Value::Null;
        assert!(serde_json::from_value::<LanWire>(value).is_err());
    }
    for version in[serde_json::json!(true),serde_json::json!("1"),serde_json::json!(0),serde_json::json!(2),serde_json::json!(1.0)]{
        let mut value:serde_json::Value=serde_json::from_str(raw).unwrap();value["version"]=version;
        assert!(serde_json::from_value::<LanWire>(value).is_err());
    }
}

#[test]
fn net02_unallowed_sources_do_not_spend_the_actual_aggregate_admission_budget(){
    let network=lan();let mut count=0;
    for _ in 0..1024{assert!(!network.admit_datagram("192.168.50.12:50000".parse().unwrap(),21,1024,&mut count));}
    assert_eq!(count,0);
    for n in 1..=256{assert!(network.admit_datagram("192.168.50.11:50000".parse().unwrap(),21,1024,&mut count));assert_eq!(count,n);}
    assert!(!network.admit_datagram("192.168.50.10:50000".parse().unwrap(),21,1024,&mut count));assert_eq!(count,257);
    count=0;assert!(!network.admit_datagram("192.168.50.11:50000".parse().unwrap(),1025,1024,&mut count));assert_eq!(count,1);
    count=u32::MAX;assert!(!network.admit_datagram("192.168.50.11:50000".parse().unwrap(),21,1024,&mut count));assert_eq!(count,u32::MAX);
}

#[test]
fn net02_first_base_binds_authenticated_login_ip_and_not_login_port(){
    let network=lan();let login="192.168.50.11:41000".parse().unwrap();
    assert!(network.allows_first_base(login,"192.168.50.11:42000".parse().unwrap()));
    assert!(!network.allows_first_base(login,"192.168.50.10:42000".parse().unwrap()));
    assert!(!network.allows_first_base(login,"192.168.50.12:42000".parse().unwrap()));
}
