//! P02 bounded loopback handoff experiment, not a session/account service.
//! LoginSuccess is a candidate until correlated with the real BaseApp capture.
use std::{io::{self, Read, Write}, net::{Ipv4Addr, SocketAddrV4, UdpSocket}, time::{Duration, Instant}};
use blowfish::{Blowfish, cipher::KeyInit};
use rsa::rand_core::{OsRng, RngCore};
use wgtk::{app::login::element::{LoginResponse, LoginSuccess}, net::{bundle::Bundle, codec::Codec, packet::PacketConfig}};
use crate::login091;

pub const BASE_PORT: u16 = 20016;

struct EncodedReply(Vec<u8>);
impl Codec<()> for EncodedReply {
    fn write(&self, writer: &mut dyn Write, _: &()) -> io::Result<()> {
        writer.write_all(&self.0)
    }
    fn read(_: &mut dyn Read, _: &()) -> io::Result<Self> {
        Err(io::Error::new(io::ErrorKind::Unsupported, "outgoing diagnostic reply only"))
    }
}

pub(super) fn reply(request_id: u32, session_key: &[u8;16], login_key: u32) -> io::Result<Vec<u8>> {
    reply_to(request_id,session_key,login_key,SocketAddrV4::new(Ipv4Addr::LOCALHOST,BASE_PORT))
}
pub(super) fn reply_to(request_id:u32,session_key:&[u8;16],login_key:u32,address:SocketAddrV4)->io::Result<Vec<u8>> {
    if *address.ip()!=Ipv4Addr::LOCALHOST || address.port()==0 {return Err(io::Error::new(io::ErrorKind::InvalidInput,"redirect must remain loopback"));}
    let cipher = Blowfish::new_from_slice(session_key)
        .map_err(|_| io::Error::new(io::ErrorKind::InvalidInput, "Blowfish key size"))?;
    let success = LoginResponse::Success(LoginSuccess {
        addr: address.into(),
        login_key,
        server_message: String::new(),
    });
    let mut payload = Vec::new();
    Codec::<Blowfish>::write(&success, &mut payload, &cipher)?;
    if payload.len() != 17 || payload[0] != 1 {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "unexpected candidate payload"));
    }
    let mut bundle = Bundle::new();
    bundle.element_writer().write_simple_reply(EncodedReply(payload), request_id);
    bundle.write_config(&mut PacketConfig::new());
    let packets: Vec<_> = bundle.iter().collect();
    if packets.len() != 1 {
        return Err(io::Error::new(io::ErrorKind::InvalidData, "unexpected reply fragmentation"));
    }
    // Retain the measured P01 framing, without the toolkit's modern prefix.
    Ok(packets[0].slice()[4..].to_vec())
}

pub fn serve(key_path: &str) -> Result<(), Box<dyn std::error::Error>> {
    let private = login091::load_key(key_path)?;
    let socket = UdpSocket::bind("127.0.0.1:20015")?;
    socket.set_read_timeout(Some(Duration::from_millis(250)))?;
    // One disposable handoff token per process, never logged as plaintext.
    // Repeated requests cannot allocate additional tokens/accounts/sessions.
    let login_key = OsRng.next_u32();
    let mut accepted_key = None;
    let mut peer = None;
    println!("BOUND {} profile=legacy091-redirect base=127.0.0.1:{BASE_PORT} toolkit=5b879f0", socket.local_addr()?);
    let deadline = Instant::now()+Duration::from_secs(60);
    for _ in 0..64 {
        // Read a whole UDP datagram, then enforce the 1024-byte decoder limit.
        // A smaller receive buffer would turn Windows WSAEMSGSIZE into an exit.
        let mut buf = [0u8;65536];
        let received = loop {
            if Instant::now() >= deadline { return Err("diagnostic deadline reached".into()); }
            match socket.recv_from(&mut buf) {
                Ok(value) => break value,
                Err(e) if matches!(e.kind(), io::ErrorKind::WouldBlock | io::ErrorKind::TimedOut) => continue,
                Err(e) => return Err(e.into()),
            }
        };
        let (length, addr) = received;
        if addr.ip() != Ipv4Addr::LOCALHOST || peer.is_some_and(|p| p != addr) {
            println!("REDIRECT_REJECT reason=unexpected_peer");
            continue;
        }
        let (request_id, fields) = match login091::decode(&buf[..length], &private) {
            Ok(value) => value,
            Err(_) => { println!("REDIRECT_REJECT reason=invalid_login bytes={length}"); continue; }
        };
        if accepted_key.is_some_and(|k| k != fields.session_key) {
            println!("REDIRECT_REJECT reason=second_key_not_supported");
            continue;
        }
        accepted_key = Some(fields.session_key);
        peer = Some(addr);
        login091::print_fields(request_id, &fields);
        let wire = reply(request_id, &fields.session_key, login_key)?;
        socket.send_to(&wire, addr)?;
        println!("LEGACY091_REDIRECT_SENT request_id={request_id} bytes={} status=1 base=127.0.0.1:{BASE_PORT}", wire.len());
    }
    Err("diagnostic packet limit reached".into())
}
