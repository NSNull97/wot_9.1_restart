//! Independently authored primitive/Crypto literal vectors. This verifies this
//! routing codec wiring and old byte preservation; native LAN remains NOT_RUN.
use super::*;
use crate::identity091::game_network::{Network,LanWire};
fn literal(hex:&str)->Vec<u8>{hex.as_bytes().chunks_exact(2).map(|pair|u8::from_str_radix(std::str::from_utf8(pair).unwrap(),16).unwrap()).collect()}

#[test]
fn net02_default_validated_redirect_retains_the_old_literal_success_bytes(){
    let network=Network::parse("127.0.0.1:20130","127.0.0.1:20131",None).unwrap();
    let expected=literal("0000ff150000004433221101aed239778e7ba153d1c493d63ab87cd6");
    let old=reply_to(0x11223344,&[7;16],0x01020304,"127.0.0.1:20131".parse().unwrap()).unwrap();
    let validated=reply_advertised(0x11223344,&[7;16],0x01020304,network.advertised_base()).unwrap();
    assert_eq!(old,expected);assert_eq!(validated,expected);
}

#[test]
fn net02_lan_redirect_accepts_only_validated_advertised_type_and_encodes_exact_endpoint(){
    let wire:LanWire=serde_json::from_str(r#"{"version":1,"mode":"lan_test","advertised_base":"192.168.50.10:20131","allowed_peer_cidrs":["192.168.50.11/32"]}"#).unwrap();
    let network=Network::parse("192.168.50.10:20130","192.168.50.10:20131",Some(wire)).unwrap();
    assert!(reply_to(0x11223344,&[7;16],0x01020304,network.base_bind()).is_err());
    assert_eq!(reply_advertised(0x11223344,&[7;16],0x01020304,network.advertised_base()).unwrap(),
        literal("0000ff1500000044332211017e09ff19da5a00917577ceb6e6084daf"));
}
