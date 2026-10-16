//! Explicit project LAN laboratory transport policy. No public/NAT listener.
//! Values are configuration-derived, never native commands or game authority.
use std::{collections::BTreeSet,fmt,io,net::{IpAddr,Ipv4Addr,SocketAddr,SocketAddrV4}};
use serde::{Deserialize,Deserializer,de::{self,MapAccess,SeqAccess,Visitor}};

pub(crate) const MAX_PEERS:usize=24;
pub(crate) const DATAGRAMS_PER_SECOND:u32=256;
pub(crate) const UNSUPPORTED_RUNTIME:&str="LAN game network requires the explicit shared owned profile13 runtime";
fn bad(message:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidInput,message)}
fn private(ip:Ipv4Addr)->bool{
    let [a,b,_,_]=ip.octets();a==10||(a==172&&(16..=31).contains(&b))||(a==192&&b==168)
}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub(crate) struct GameBind(SocketAddrV4);
impl GameBind{
    fn parse(value:&str,lan:bool)->io::Result<Self>{
        let address:SocketAddrV4=value.parse().map_err(|_|bad("numeric IPv4 game endpoint required"))?;
        if lan{
            if !private(*address.ip())||address.port()<1024||address.to_string()!=value{
                return Err(bad("LAN game endpoint must be canonical private IPv4 with unprivileged port"));
            }
        }else if *address.ip()!=Ipv4Addr::LOCALHOST||address.port()==0{
            return Err(bad("game endpoint must be 127.0.0.1 with a nonzero port"));
        }
        Ok(Self(address))
    }
    pub(crate) fn address(self)->SocketAddrV4{self.0}
}

/// Private field prevents ordinary SocketAddr values entering the LAN codec.
#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub(crate) struct AdvertisedBase(SocketAddrV4);
impl AdvertisedBase{pub(crate) fn address(self)->SocketAddrV4{self.0}}

#[derive(Clone,Copy,Debug,PartialEq,Eq)]
pub(crate) enum Runtime{LoopbackOnly,SharedOwnedProfile13}

struct PeerList(Vec<Ipv4Addr>);
impl<'de> Deserialize<'de> for PeerList{
    fn deserialize<D:Deserializer<'de>>(input:D)->Result<Self,D::Error>{
        struct Peers;
        impl<'de> Visitor<'de> for Peers{
            type Value=PeerList;
            fn expecting(&self,f:&mut fmt::Formatter)->fmt::Result{f.write_str("1..24 unique canonical private IPv4 /32 peers")}
            fn visit_seq<S:SeqAccess<'de>>(self,mut input:S)->Result<PeerList,S::Error>{
                let mut output=Vec::new();
                while let Some(value)=input.next_element::<String>()?{
                    if output.len()>=MAX_PEERS{return Err(de::Error::custom("LAN peer count"));}
                    let host=value.strip_suffix("/32").ok_or_else(||de::Error::custom("LAN peer requires /32"))?;
                    let ip:Ipv4Addr=host.parse().map_err(|_|de::Error::custom("LAN peer numeric IPv4"))?;
                    if !private(ip)||format!("{ip}/32")!=value||output.contains(&ip){return Err(de::Error::custom("LAN peer canonical/private/unique"));}
                    output.push(ip);
                }
                if output.is_empty(){return Err(de::Error::custom("LAN peer list empty"));}
                Ok(PeerList(output))
            }
        }
        input.deserialize_seq(Peers)
    }
}

/// Must be decoded directly by the Config visitor; Value/from_value loses
/// duplicate nested keys. No constructors accept a client or service URL.
pub(crate) struct LanWire{advertised:AdvertisedBase,peers:Vec<Ipv4Addr>}
impl<'de> Deserialize<'de> for LanWire{
    fn deserialize<D:Deserializer<'de>>(input:D)->Result<Self,D::Error>{
        struct Fields;
        impl<'de> Visitor<'de> for Fields{
            type Value=LanWire;
            fn expecting(&self,f:&mut fmt::Formatter)->fmt::Result{f.write_str("exact unique LAN v1 fields")}
            fn visit_map<M:MapAccess<'de>>(self,mut input:M)->Result<LanWire,M::Error>{
                let mut seen=BTreeSet::new();let(mut version,mut mode,mut advertised,mut peers)=(None,None,None,None);
                while let Some(key)=input.next_key::<String>()?{
                    if seen.len()>=4||!seen.insert(key.clone()){return Err(de::Error::custom("duplicate/too many LAN fields"));}
                    match key.as_str(){
                        "version"=>version=Some(input.next_value::<u8>()?),
                        "mode"=>mode=Some(input.next_value::<String>()?),
                        "advertised_base"=>advertised=Some(input.next_value::<String>()?),
                        "allowed_peer_cidrs"=>peers=Some(input.next_value::<PeerList>()?),
                        _=>return Err(de::Error::custom("unknown LAN field")),
                    }
                }
                if version!=Some(1)||mode.as_deref()!=Some("lan_test")||seen.len()!=4{return Err(de::Error::custom("LAN version/mode/fields"));}
                let address=GameBind::parse(advertised.as_deref().ok_or_else(||de::Error::custom("LAN advertised field"))?,true)
                    .map_err(de::Error::custom)?.address();
                Ok(LanWire{advertised:AdvertisedBase(address),peers:peers.ok_or_else(||de::Error::custom("LAN peers field"))?.0})
            }
        }
        input.deserialize_map(Fields)
    }
}

#[derive(Clone,Debug)]
pub(crate) struct Network{
    login:GameBind,base:GameBind,advertised:AdvertisedBase,
    peers:[Ipv4Addr;MAX_PEERS],peer_count:usize,lan:bool,
}
impl Network{
    pub(crate) fn parse(login:&str,base:&str,lan:Option<LanWire>)->io::Result<Self>{
        let is_lan=lan.is_some();let login=GameBind::parse(login,is_lan)?;let base=GameBind::parse(base,is_lan)?;
        if login==base{return Err(bad("game ports must be distinct"));}
        let mut network=Self{login,base,advertised:AdvertisedBase(base.address()),
            peers:[Ipv4Addr::UNSPECIFIED;MAX_PEERS],peer_count:0,lan:is_lan};
        if let Some(wire)=lan{
            if login.address().ip()!=base.address().ip()||wire.advertised.address()!=base.address(){
                return Err(bad("LAN bind hosts and advertised Base must match concrete Base endpoint"));
            }
            network.advertised=wire.advertised;network.peer_count=wire.peers.len();
            network.peers[..wire.peers.len()].copy_from_slice(&wire.peers);
        }
        Ok(network)
    }
    pub(crate) fn login_bind(&self)->SocketAddrV4{self.login.address()}
    pub(crate) fn base_bind(&self)->SocketAddrV4{self.base.address()}
    pub(crate) fn advertised_base(&self)->AdvertisedBase{self.advertised}
    pub(crate) fn is_lan(&self)->bool{self.lan}
    pub(crate) fn require_runtime(&self,runtime:Runtime,login:SocketAddrV4,base:SocketAddrV4)->io::Result<()>{
        if self.login_bind()!=login||self.base_bind()!=base{return Err(bad("game bind fields changed after network validation"));}
        if self.lan&&runtime!=Runtime::SharedOwnedProfile13{return Err(bad(UNSUPPORTED_RUNTIME));}Ok(())
    }
    pub(crate) fn allows_peer(&self,peer:SocketAddr)->bool{
        let IpAddr::V4(ip)=peer.ip()else{return false;};
        if self.lan{self.peers[..self.peer_count].contains(&ip)}else{ip==Ipv4Addr::LOCALHOST}
    }
    /// The old aggregate256/s bound remains. Unallowed IPs neither allocate nor
    /// consume this accepted-peer budget; no per-IP throughput promise is made.
    pub(crate) fn admit_datagram(&self,peer:SocketAddr,length:usize,maximum:usize,count:&mut u32)->bool{
        if !self.allows_peer(peer){return false;}
        *count=count.saturating_add(1);
        *count<=DATAGRAMS_PER_SECOND&&length<=maximum
    }
    pub(crate) fn allows_first_base(&self,login:SocketAddr,base:SocketAddr)->bool{
        self.allows_peer(base)&&(!self.lan||login.ip()==base.ip())
    }
}

#[cfg(test)]
#[path="game_network_tests.rs"]
mod tests;
