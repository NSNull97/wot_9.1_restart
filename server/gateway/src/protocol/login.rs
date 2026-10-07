//! Narrow observed 0.9.1 login profile. No accounts, login success, or arena.
//! Evidence: 20261002-p01-bootstrap/native-02, exact client EXE hash in report.
use std::{fs, io::{self, Read, Write}, net::{SocketAddr, UdpSocket}, time::{Duration, Instant}};
use rsa::{pkcs8::DecodePrivateKey, Oaep, PublicKeyParts, RsaPrivateKey};
use sha1::Sha1;
use wgtk::net::{codec::Codec, bundle::Bundle, packet::{Packet, PacketConfig}};

pub const PROTOCOL: u32 = 0x02030000;
const MAX_DATAGRAM: usize = 1024;
// OBSERVED email-prepare-11: email254/password512 produces two native UDP
// fragments (1437/142 bytes), a1553-byte logical request and12 RSA blocks.
// This limit is logical, not a claim that its largest value is one UDP packet.
pub(crate) const MAX_INTERACTIVE_DATAGRAM:usize=17+12*128;
const MAX_INTERACTIVE_PLAINTEXT:usize=1+(4+391)+(4+512)+(1+16)+20;
const MESSAGE: &str = "P01_LOCAL_PROBE: no game service";
// Exact measured lab username; this is intentionally not a general auth API.
const LAB_USERNAME: &[u8] = br#"{"auth_realm": "P01_LOCAL", "login": "p01-local-test", "game": "wot", "auth_method": "basic"}"#;
// Verified EXE VA 0x60da55: SERVER_NOT_READY=0x49. Modern toolkit uses 74,
// which this actual client interpreted as UPDATER_NOT_READY in native-03.
const SERVER_NOT_READY: u8 = 73;

struct DiagnosticRejection;
impl Codec<()> for DiagnosticRejection {
    fn write(&self, writer: &mut dyn Write, _: &()) -> io::Result<()> {
        writer.write_all(&[SERVER_NOT_READY, MESSAGE.len() as u8])?;
        writer.write_all(MESSAGE.as_bytes())
    }
    fn read(reader: &mut dyn Read, _: &()) -> io::Result<Self> {
        let mut header = [0;2];
        reader.read_exact(&mut header)?;
        if header != [SERVER_NOT_READY, MESSAGE.len() as u8] { return Err(invalid("not the diagnostic rejection")); }
        let mut message = [0;MESSAGE.len()];
        reader.read_exact(&mut message)?;
        if message != MESSAGE.as_bytes() { return Err(invalid("unexpected rejection message")); }
        Ok(Self)
    }
}

fn invalid(message: &str) -> io::Error { io::Error::new(io::ErrorKind::InvalidData, message) }

struct FragmentSet {
    peer:SocketAddr, first:u32, started:Instant, parts:[Option<Vec<u8>>;2],
}
/// Narrow login-only native fragment observer/reassembler. No arbitrary bundle
/// fragmentation, compression, wraparound or BaseApp fragments are supported.
/// The footer contract is independently measured in all ten email11 pairs.
#[derive(Default)]
pub(super) struct LoginFragments {pending:Vec<FragmentSet>}
impl LoginFragments {
    pub(super) fn push(&mut self,peer:SocketAddr,now:Instant,data:&[u8])->io::Result<Option<Vec<u8>>> {
        self.pending.retain(|set|now.saturating_duration_since(set.started)<Duration::from_secs(5));
        if data.starts_with(&[1,0]) {envelope_interactive(data)?;return Ok(Some(data.to_vec()));}
        let (part,footer)=match data.get(..2) {
            Some([0x61,0]) if data.len()==1437=>(0,14),
            Some([0x60,0]) if data.len()==142=>(1,12),
            _=>return Err(invalid("unmeasured login fragment flags/size")),
        };
        let end=data.len()-footer;
        let first=u32::from_le_bytes(data[end..end+4].try_into().map_err(|_|invalid("fragment first"))?);
        let last=u32::from_le_bytes(data[end+4..end+8].try_into().map_err(|_|invalid("fragment last"))?);
        let sequence=u32::from_le_bytes(data[data.len()-4..].try_into().map_err(|_|invalid("fragment sequence"))?);
        // A finite pre-wrap safety bound; full sequence wrap is unverified.
        if first==0 || first>=1_000_000 || last!=first+1 || sequence!=first+part as u32 {
            return Err(invalid("login fragment range/sequence"));
        }
        if part==0 && (data[end+8..end+10]!=[2,0] || data[2]!=0
            || u16::from_le_bytes([data[3],data[4]]) as usize+13!=MAX_INTERACTIVE_DATAGRAM
            || data[9..15]!=[0,0,0,0,3,2]) {return Err(invalid("login fragment request header/footer"));}
        let index=match self.pending.iter().position(|set|set.peer==peer && set.first==first) {
            Some(index)=>index,
            None=>{
                if self.pending.len()>=4 {return Err(invalid("login fragment pending limit"));}
                self.pending.push(FragmentSet {peer,first,started:now,parts:[None,None]});self.pending.len()-1
            },
        };
        let body=&data[2..end];
        if let Some(previous)=self.pending[index].parts[part].as_ref() {
            if previous!=body {
                self.pending.remove(index);return Err(invalid("changed login fragment duplicate"));
            }
            return Ok(None);
        }
        self.pending[index].parts[part]=Some(body.to_vec());
        if self.pending[index].parts.iter().any(Option::is_none) {return Ok(None);}
        let set=self.pending.remove(index);
        let mut logical=Vec::with_capacity(MAX_INTERACTIVE_DATAGRAM);logical.extend([1,0]);
        for fragment in set.parts {logical.extend(fragment.ok_or_else(||invalid("missing login fragment"))?);}
        logical.extend([2,0]);envelope_interactive(&logical)?;
        Ok(Some(logical))
    }
}

#[derive(Debug)]
pub struct Envelope<'a> { pub request_id: u32, pub ciphertext: &'a [u8] }

pub fn envelope(data: &[u8]) -> io::Result<Envelope<'_>> {
    envelope_bounded(data,MAX_DATAGRAM)
}
pub(super) fn envelope_interactive(data:&[u8])->io::Result<Envelope<'_>> {
    envelope_bounded(data,MAX_INTERACTIVE_DATAGRAM)
}
fn envelope_bounded(data:&[u8],maximum:usize)->io::Result<Envelope<'_>> {
    if data.len() < 17 || data.len() > maximum { return Err(invalid("datagram size")); }
    if data[..3] != [1, 0, 0] { return Err(invalid("requires flags=HAS_REQUESTS, element=0")); }
    let length = u16::from_le_bytes([data[3], data[4]]) as usize;
    if length < 4 || length + 13 != data.len() { return Err(invalid("element length mismatch")); }
    if data[9..11] != [0, 0] || data[data.len()-2..] != [2, 0] {
        return Err(invalid("unsupported request chain/footer"));
    }
    let protocol = u32::from_le_bytes(data[11..15].try_into().map_err(|_| invalid("protocol"))?);
    if protocol != PROTOCOL { return Err(invalid("unverified login protocol version")); }
    let request_id = u32::from_le_bytes(data[5..9].try_into().map_err(|_| invalid("request id"))?);
    Ok(Envelope { request_id, ciphertext: &data[15..data.len()-2] })
}

struct Cursor<'a> { bytes: &'a [u8], pos: usize }
impl<'a> Cursor<'a> {
    fn take(&mut self, length: usize) -> io::Result<&'a [u8]> {
        let end = self.pos.checked_add(length).ok_or_else(|| invalid("cursor overflow"))?;
        let value = self.bytes.get(self.pos..end).ok_or_else(|| invalid("truncated plaintext"))?;
        self.pos = end;
        Ok(value)
    }
    fn blob(&mut self, max: usize) -> io::Result<&'a [u8]> {
        let length = self.take(1)?[0] as usize;
        // Extended lengths are not required by this measured lab profile.
        if length == 255 || length > max { return Err(invalid("blob exceeds observed profile")); }
        self.take(length)
    }
    fn extended_blob(&mut self,max:usize)->io::Result<&'a [u8]> {
        let first=self.take(1)?[0];
        let length=if first==255 {
            let bytes=self.take(3)?;
            let length=usize::from(bytes[0]) | (usize::from(bytes[1])<<8) | (usize::from(bytes[2])<<16);
            if length<255 {return Err(invalid("noncanonical extended credential length"));}length
        } else {usize::from(first)};
        if length>max {return Err(invalid("interactive credential size bound"));}
        self.take(length)
    }
}

pub struct Fields {
    pub username_len: usize, pub password_len: usize, pub key_len: usize, pub nonce: u32,
    // Never print this key. The redirect experiment uses the client's own key.
    pub(super) session_key: [u8; 16],
    pub(super) digest: [u8;16],
    pub(super) lab_credentials_valid: bool,
    // Ephemeral decoded credentials for the separate local identity boundary.
    // Fields deliberately has no Debug implementation. Never log these bytes.
    pub(super) username: Vec<u8>,
    pub(super) password: Vec<u8>,
}

pub fn fields(plain: &[u8]) -> io::Result<Fields> {
    let fields=parse_fields(plain)?;
    if !fields.lab_credentials_valid {return Err(invalid("only disposable P01 credentials accepted by diagnostic decoder"));}
    Ok(fields)
}

fn parse_fields(plain: &[u8]) -> io::Result<Fields> {
    parse_fields_profile(plain,false)
}
fn parse_fields_profile(plain:&[u8],interactive:bool)->io::Result<Fields> {
    if plain.len() > if interactive {MAX_INTERACTIVE_PLAINTEXT} else {512} { return Err(invalid("plaintext limit")); }
    let mut cursor = Cursor { bytes: plain, pos: 0 };
    if cursor.take(1)? != [1] { return Err(invalid("only observed flags=1 supported")); }
    let username = if interactive {cursor.extended_blob(391)?} else {cursor.blob(200)?};
    let password = if interactive {cursor.extended_blob(512)?} else {cursor.blob(100)?};
    let key = cursor.blob(56)?;
    if key.len() != 16 { return Err(invalid("only observed 16-byte session key supported")); }
    let digest=cursor.take(16)?.try_into().map_err(|_|invalid("digest"))?;
    let nonce = u32::from_le_bytes(cursor.take(4)?.try_into().map_err(|_| invalid("nonce"))?);
    if cursor.pos != plain.len() { return Err(invalid("unexpected trailing login fields")); }
    Ok(Fields { username_len: username.len(), password_len: password.len(), key_len: key.len(), nonce,
        username: username.to_vec(), password: password.to_vec(),
        digest, lab_credentials_valid:password==b"p01-disposable-local-only" && username==LAB_USERNAME,
        session_key: key.try_into().map_err(|_| invalid("session key length"))? })
}

pub(super) fn load_key(path: &str) -> Result<RsaPrivateKey, Box<dyn std::error::Error>> {
    if fs::metadata(path)?.len() > 16384 { return Err(invalid("key file size").into()); }
    let key = RsaPrivateKey::from_pkcs8_pem(&fs::read_to_string(path)?)?;
    if key.size() != 128 { return Err(invalid("lab requires RSA-1024").into()); }
    Ok(key)
}

pub(super) fn decode(data: &[u8], key: &RsaPrivateKey) -> Result<(u32, Fields), Box<dyn std::error::Error>> {
    let (request_id,fields)=decode_unauthed(data,key)?;
    if !fields.lab_credentials_valid {return Err(invalid("only disposable P01 credentials accepted by diagnostic decoder").into());}
    Ok((request_id,fields))
}

pub(super) fn decode_unauthed(data: &[u8], key: &RsaPrivateKey) -> Result<(u32, Fields), Box<dyn std::error::Error>> {
    decode_profile(data,key,false)
}
pub(super) fn decode_interactive(data:&[u8],key:&RsaPrivateKey)->Result<(u32,Fields),Box<dyn std::error::Error>> {
    decode_profile(data,key,true)
}
fn decode_profile(data:&[u8],key:&RsaPrivateKey,interactive:bool)->Result<(u32,Fields),Box<dyn std::error::Error>> {
    let envelope = if interactive {envelope_interactive(data)?} else {envelope(data)?};
    if envelope.ciphertext.is_empty() || envelope.ciphertext.len() % 128 != 0 || envelope.ciphertext.len() > if interactive {12*128} else {512} {
        return Err(invalid("RSA block count/length").into());
    }
    let mut plain = Vec::with_capacity(344);
    for block in envelope.ciphertext.chunks_exact(128) {
        plain.extend(key.decrypt(Oaep::new::<Sha1>(), block)?);
    }
    Ok((envelope.request_id, parse_fields_profile(&plain,interactive)?))
}

pub(super) fn rejection(request_id:u32,code:u8)->Vec<u8> {
    // Exact EXE maps 67 to INVALID_PASSWORD and 69 to BAD_DIGEST.
    let message=b"P02_LOCAL_LAB_REJECTED";
    let mut wire=vec![0,0,255];wire.extend((6u32+message.len() as u32).to_le_bytes());
    wire.extend(request_id.to_le_bytes());wire.push(code);wire.push(message.len() as u8);wire.extend(message);wire
}

pub(super) fn print_fields(request_id: u32, fields: &Fields) {
    println!("LEGACY091_LOGIN_DECODED protocol=0x{PROTOCOL:08x} request_id={request_id} username_bytes={} password_bytes={} session_key_bytes={} nonce={}",
        fields.username_len, fields.password_len, fields.key_len, fields.nonce);
}

pub fn offline(key_path: &str, packet_path: &str) -> Result<(), Box<dyn std::error::Error>> {
    if fs::metadata(packet_path)?.len() > MAX_DATAGRAM as u64 { return Err(invalid("packet file size").into()); }
    let data = fs::read(packet_path)?;
    envelope(&data)?;
    // Record stock failure and the precise packet-prefix adjustment independently.
    let mut stock = Packet::new();
    stock.set_len(data.len());
    stock.buf_mut()[..data.len()].copy_from_slice(&data);
    println!("STOCK_PACKET_CONFIG {:?}", stock.read_config_locked_ref());
    let mut prefixed = Packet::new();
    prefixed.set_len(data.len()+4);
    prefixed.buf_mut()[4..data.len()+4].copy_from_slice(&data);
    println!("WITH_INTERNAL_PREFIX_PACKET_CONFIG {:?}", prefixed.read_config_locked_ref());
    let (request_id, fields) = decode(&data, &load_key(key_path)?)?;
    print_fields(request_id, &fields);
    Ok(())
}

pub fn serve(key_path: &str) -> Result<(), Box<dyn std::error::Error>> {
    let key = load_key(key_path)?;
    let socket = UdpSocket::bind("127.0.0.1:20015")?;
    socket.set_read_timeout(Some(Duration::from_secs(1)))?;
    println!("BOUND {} profile=legacy091 toolkit_reply_encoder=5b879f0", socket.local_addr()?);
    let deadline = Instant::now()+Duration::from_secs(60);
    let mut packets = 0;
    let mut peer = None;
    while Instant::now() < deadline && packets < 64 {
        let mut buf = [0u8; MAX_DATAGRAM+1];
        let (length, addr) = match socket.recv_from(&mut buf) {
            Ok(pair) => pair,
            Err(e) if matches!(e.kind(), io::ErrorKind::WouldBlock | io::ErrorKind::TimedOut) => continue,
            Err(e) => return Err(e.into()),
        };
        packets += 1;
        if !addr.ip().is_loopback() || peer.is_some_and(|p| p != addr) { return Err(invalid("unexpected peer").into()); }
        peer = Some(addr);
        let (request_id, fields) = decode(&buf[..length], &key)?;
        print_fields(request_id, &fields);
        let mut reply = Bundle::new();
        reply.element_writer().write_simple_reply(DiagnosticRejection, request_id);
        reply.write_config(&mut PacketConfig::new());
        for packet in reply.iter() {
            // The observed 0.9.1 wire has no modern four-byte packet prefix.
            let wire = &packet.slice()[4..];
            socket.send_to(wire, addr)?;
            println!("LEGACY091_REJECTION_SENT code={SERVER_NOT_READY} request_id={request_id} bytes={}", wire.len());
        }
    }
    Err(invalid("diagnostic deadline/packet limit reached").into())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn packet() -> Vec<u8> {
        let mut p = vec![0;273]; p[..5].copy_from_slice(&[1,0,0,4,1]);
        p[11..15].copy_from_slice(&PROTOCOL.to_le_bytes()); p[271] = 2; p
    }
    #[test] fn rejects_every_truncation() {
        let p=packet(); for n in 0..p.len() { assert!(envelope(&p[..n]).is_err()); }
    }
    #[test] fn rejects_unknown_flags_protocol_and_chain() {
        for index in [0,1,2,9,10,11,271,272] { let mut p=packet(); p[index]^=0x80; assert!(envelope(&p).is_err()); }
    }
    #[test] fn rejects_appended_or_oversized_data() {
        let mut p=packet(); p.push(0); assert!(envelope(&p).is_err()); assert!(envelope(&[0;1025]).is_err());
    }
    #[test] fn bounded_plaintext_rejects_empty_and_extended_length() {
        assert!(fields(&[]).is_err()); assert!(fields(&[1,255]).is_err()); assert!(fields(&[1;513]).is_err());
    }
    fn interactive_plain(password:&[u8])->Vec<u8> {
        let mut bytes=vec![1,2,b'{',b'}'];
        if password.len()>=255 {bytes.push(255);bytes.extend_from_slice(&(password.len() as u32).to_le_bytes()[..3]);}
        else {bytes.push(password.len() as u8);}
        bytes.extend_from_slice(password);bytes.push(16);bytes.extend_from_slice(&[5;16]);bytes.extend_from_slice(&[0;20]);bytes
    }
    #[test] fn interactive_password_bound_is_separate_from_historical_profile() {
        for password in [vec![b'a';128],"😀".repeat(128).into_bytes()] {
            let plain=interactive_plain(&password);
            assert_eq!(parse_fields_profile(&plain,true).unwrap().password,password);
            assert!(parse_fields(&plain).is_err());
            for end in 0..plain.len() {assert!(parse_fields_profile(&plain[..end],true).is_err());}
            let mut trailing=plain;trailing.push(0);assert!(parse_fields_profile(&trailing,true).is_err());
        }
        assert!(parse_fields_profile(&interactive_plain(&[1;513]),true).is_err());
        let mut noncanonical=interactive_plain(&[1;255]);noncanonical[5..8].copy_from_slice(&[254,0,0]);
        noncanonical.remove(8);assert!(parse_fields_profile(&noncanonical,true).is_err());
    }
    #[test] fn interactive_envelope_has_exact_finite_rsa_datagram_bound() {
        let mut data=vec![0;MAX_INTERACTIVE_DATAGRAM];data[..3].copy_from_slice(&[1,0,0]);
        data[3..5].copy_from_slice(&((MAX_INTERACTIVE_DATAGRAM-13) as u16).to_le_bytes());
        data[11..15].copy_from_slice(&PROTOCOL.to_le_bytes());data[MAX_INTERACTIVE_DATAGRAM-2]=2;
        assert!(envelope_interactive(&data).is_ok());assert!(envelope(&data).is_err());
        data.push(0);assert!(envelope_interactive(&data).is_err());
    }
    fn native_fragments(first:u32)->[Vec<u8>;2] {
        let mut logical=vec![0;MAX_INTERACTIVE_DATAGRAM];logical[..3].copy_from_slice(&[1,0,0]);
        logical[3..5].copy_from_slice(&((MAX_INTERACTIVE_DATAGRAM-13) as u16).to_le_bytes());
        logical[11..15].copy_from_slice(&PROTOCOL.to_le_bytes());
        let mut a=vec![0x61,0];a.extend_from_slice(&logical[2..1423]);
        a.extend(first.to_le_bytes());a.extend((first+1).to_le_bytes());a.extend([2,0]);a.extend(first.to_le_bytes());
        let mut b=vec![0x60,0];b.extend_from_slice(&logical[1423..1551]);
        b.extend(first.to_le_bytes());b.extend((first+1).to_le_bytes());b.extend((first+1).to_le_bytes());[a,b]
    }
    #[test] fn native_login_fragments_reorder_duplicate_and_expire_without_cross_peer_mix() {
        let now=Instant::now();let peer="127.0.0.1:41001".parse().unwrap();let other="127.0.0.1:41002".parse().unwrap();
        let [a,b]=native_fragments(1);let mut fragments=LoginFragments::default();
        assert!(fragments.push(peer,now,&b).unwrap().is_none());
        assert!(fragments.push(peer,now,&b).unwrap().is_none());
        assert!(fragments.push(other,now,&a).unwrap().is_none());
        let joined=fragments.push(peer,now,&a).unwrap().unwrap();
        assert_eq!(joined.len(),1553);assert_eq!(envelope_interactive(&joined).unwrap().ciphertext.len(),1536);
        assert_eq!(fragments.pending.len(),1);
        assert!(fragments.push(other,now+Duration::from_secs(5),&b).unwrap().is_none());
        assert_eq!(fragments.pending.len(),1);
        assert!(fragments.push(other,now+Duration::from_secs(5),&a).unwrap().is_some());
        assert!(fragments.pending.is_empty());
    }
    #[test] fn native_login_fragments_reject_changed_data_truncation_range_and_resource_abuse() {
        let now=Instant::now();let peer="127.0.0.1:41001".parse().unwrap();let [a,b]=native_fragments(1);
        for packet in [&a,&b] {for end in 0..packet.len() {assert!(LoginFragments::default().push(peer,now,&packet[..end]).is_err());}}
        let mut fragments=LoginFragments::default();fragments.push(peer,now,&a).unwrap();
        let mut changed=a.clone();changed[5]^=1;assert!(fragments.push(peer,now,&changed).is_err());assert!(fragments.pending.is_empty());
        for index in [0,1,2,3,9,11,1423,1427,1431,1433] {
            let mut changed=a.clone();changed[index]^=0x80;assert!(LoginFragments::default().push(peer,now,&changed).is_err());
        }
        for first in [0,1_000_000,u32::MAX-1] {for packet in native_fragments(first) {assert!(LoginFragments::default().push(peer,now,&packet).is_err());}}
        for first in 1..=4 {assert!(fragments.push(peer,now,&native_fragments(first*2)[1]).unwrap().is_none());}
        assert_eq!(fragments.pending.len(),4);assert!(fragments.push(peer,now,&native_fragments(11)[1]).is_err());
        assert!(fragments.push(peer,now+Duration::from_secs(5),&native_fragments(11)[1]).unwrap().is_none());
        assert_eq!(fragments.pending.len(),1);
    }
    #[test] fn interactive_extended_username_has_measured_391_byte_bound() {
        let mut plain=vec![1,255,135,1,0];plain.extend([b'x';391]);
        let rest=interactive_plain(&[b'p';512]);plain.extend_from_slice(&rest[4..]);
        assert_eq!(plain.len(),949);assert_eq!(parse_fields_profile(&plain,true).unwrap().username.len(),391);
        assert!(parse_fields(&plain).is_err());
        let mut too_long=plain.clone();too_long[2]=136;too_long.insert(5,b'x');assert!(parse_fields_profile(&too_long,true).is_err());
        for end in 0..plain.len() {assert!(parse_fields_profile(&plain[..end],true).is_err());}
    }
}
