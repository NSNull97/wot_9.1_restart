//! Real Table/Session parsing with authored transport identities, not Login or
//! owned vehicle proof. Every refusal path stops before missing key/resources.
use super::*;
use crate::identity091::game_network::{Network,LanWire};
fn network()->Network{
    let wire:LanWire=serde_json::from_value(serde_json::json!({"version":1,"mode":"lan_test","advertised_base":"192.168.50.10:20131",
        "allowed_peer_cidrs":["192.168.50.10/32","192.168.50.11/32"]})).unwrap();
    Network::parse("192.168.50.10:20130","192.168.50.10:20131",Some(wire)).unwrap()
}
fn handshake(handoff:u32)->Vec<u8>{
    let mut raw=vec![1,0,0,8,0];raw.extend(1u32.to_le_bytes());raw.extend([0,0]);
    raw.extend(handoff.to_le_bytes());raw.extend(0u32.to_le_bytes());raw.extend([2,0]);raw
}
fn refusal(result:Result<(),Box<dyn std::error::Error>>){
    assert_eq!(result.unwrap_err().downcast_ref::<io::Error>().unwrap().to_string(),crate::identity091::game_network::UNSUPPORTED_RUNTIME);
}

#[test]
fn net02_table_first_base_checks_login_ip_before_binding_even_another_allowlisted_peer(){
    let now=Instant::now();let mut table=Table::default();
    let s=Session::new(1,[7;16],"192.168.50.11:41000".parse().unwrap(),now);let token=s.handoff;table.sessions.push(s);
    let network=network();let bytes=handshake(token);assert!(base::base_request(&bytes,token).is_ok());
    assert!(table.route_with_network("192.168.50.10:42000".parse().unwrap(),&bytes,&network).is_err());
    assert_eq!(table.sessions[0].base_peer,None);
    assert_eq!(table.route_with_network("192.168.50.11:42000".parse().unwrap(),&bytes,&network).unwrap(),0);
    assert_eq!(table.sessions[0].base_peer,None); // route proposes, actual loop binds only after retirement guard.
    table.sessions[0].base_peer=Some("192.168.50.11:42000".parse().unwrap());
    assert!(table.route_with_network("192.168.50.11:42001".parse().unwrap(),&bytes,&network).is_err());
    assert_eq!(table.route_with_network("192.168.50.11:42000".parse().unwrap(),&[0;24],&network).unwrap(),0);
}

#[test]
fn net02_table_two_sessions_same_allowed_ip_keep_distinct_tokens_and_live_peers(){
    let now=Instant::now();let network=network();let mut table=Table::default();
    for id in[1u32,2]{let mut s=Session::new(id,[id as u8;16],format!("192.168.50.11:{}",41000+id).parse().unwrap(),now);
        s.handoff=100+id;table.sessions.push(s);}
    let a="192.168.50.11:42001".parse().unwrap();let b="192.168.50.11:42002".parse().unwrap();
    assert_eq!(table.route_with_network(a,&handshake(101),&network).unwrap(),0);
    table.sessions[0].base_peer=Some(a);
    assert!(table.route_with_network(a,&handshake(102),&network).is_err());
    assert_eq!(table.route_with_network(b,&handshake(102),&network).unwrap(),1);
    assert!(table.route_with_network("192.168.50.12:42002".parse().unwrap(),&handshake(102),&network).is_err());
    assert!(table.route_with_network(b,&handshake(999),&network).is_err());assert_eq!(table.sessions[1].base_peer,None);
}

#[test]
fn net02_shared_unsupported_loaders_and_direct_runtime_fail_before_any_socket(){
    let path=crate::identity091::net02_config_tests::lan_file();let path=path.to_str().unwrap();
    refusal(serve("missing","missing",path,"missing"));
    refusal(serve_integrated("missing","missing",path,"missing","missing",None,false,false,false,None));
    refusal(serve_integrated_for_map("missing","missing",path,"missing","missing",None,false,false,false,None,MapId::Karelia));
    refusal(serve_integrated_for_vehicle("missing","missing",path,"missing","missing",None,false,false,false,None,MapId::Karelia,VehicleKind::Ms1));
    refusal(serve_curated_lab("missing","missing",path,"missing","missing",VehicleKind::Ms1));
    refusal(serve_curated_lab("missing","missing",path,"missing","missing",VehicleKind::Wt128));
    refusal(serve_curated_lab_v2("missing","missing",path,"missing","missing",VehicleKind::Wt128));
    refusal(serve_with_pool_policy("missing","missing",path,"missing",None,None,false,None,None,None,MapId::Karelia,VehicleKind::Ms1,None,None,false));
}

#[test]
fn net02_only_profile13_loader_passes_network_guard_and_stops_at_missing_manifest(){
    let path=crate::identity091::net02_config_tests::lan_file();let path=path.to_str().unwrap();
    let missing=Path::new(path).parent().unwrap().join("missing-templates.json");
    let error=serve_profile13("missing","missing",path,missing.to_str().unwrap(),"missing").unwrap_err();
    // No game assets or sockets are needed to prove the selected real loader
    // passes the mode guard and reaches its original resource validator.
    assert_ne!(error.to_string(),crate::identity091::game_network::UNSUPPORTED_RUNTIME);
    assert_eq!(error.downcast_ref::<io::Error>().unwrap().kind(),io::ErrorKind::NotFound);
}
