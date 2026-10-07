//! One BaseApp handshake experiment; no Account, entities, or game session.
//! Verified narrow reply/first-message corpus: 20261004-p02-baseapp-reply.
use std::{io::{self, Read, Write}, net::{Ipv4Addr, SocketAddr, UdpSocket}, thread, time::{Duration, Instant}};
use blowfish::{Blowfish, cipher::KeyInit};
use rsa::rand_core::{OsRng, RngCore};
use wgtk::net::filter::{BlowfishReader, BlowfishWriter};
use crate::{login091, redirect091};
use crate::channel091::{AckMode, FirstAck};
use crate::reliable091::{FirstServer,GapProbe};

const MAX_WIRE: usize = 1024;
const MAGIC: [u8;4] = 0xDEADBEEFu32.to_le_bytes();

fn invalid(message: &str) -> io::Error { io::Error::new(io::ErrorKind::InvalidData,message) }

pub(super) fn base_request(data: &[u8], login_key: u32) -> io::Result<(u32,u32)> {
    if data.len()!=21 || data[..5]!=[1,0,0,8,0] || data[9..11]!=[0,0] || data[19..]!=[2,0] {
        return Err(invalid("unmeasured BaseApp request framing"));
    }
    if data[11..15]!=login_key.to_le_bytes() { return Err(invalid("handoff token mismatch")); }
    let request_id=u32::from_le_bytes(data[5..9].try_into().map_err(|_|invalid("request id"))?);
    let attempt=u32::from_le_bytes(data[15..19].try_into().map_err(|_|invalid("attempt"))?);
    if attempt>5 { return Err(invalid("attempt outside measured diagnostic window")); }
    Ok((request_id,attempt))
}

fn cipher(key: &[u8;16]) -> io::Result<Blowfish> {
    Blowfish::new_from_slice(key).map_err(|_|invalid("Blowfish key size"))
}

pub(super) fn encrypt(clear: &[u8], key: &[u8;16]) -> io::Result<Vec<u8>> {
    if clear.len()<2 || clear.len()>MAX_WIRE-12 { return Err(invalid("clear packet size")); }
    let padding=(8-(clear.len()+5)%8)%8;
    let mut padded=clear.to_vec();
    padded.resize(clear.len()+padding,0);
    padded.extend(MAGIC);
    padded.push((padding+1) as u8);
    let bf=cipher(key)?;
    let mut wire=Vec::with_capacity(padded.len());
    {
        let mut writer=BlowfishWriter::new(&mut wire,&bf);
        writer.write_all(&padded)?;
        writer.flush()?;
    }
    Ok(wire)
}

pub(super) fn decrypt(wire: &[u8], key: &[u8;16]) -> io::Result<Vec<u8>> {
    if wire.len()<8 || wire.len()>MAX_WIRE || wire.len()%8!=0 { return Err(invalid("encrypted packet size")); }
    let bf=cipher(key)?;
    let mut clear=vec![0;wire.len()];
    BlowfishReader::new(wire,&bf).read_exact(&mut clear)?;
    let end=clear.len();
    let wastage=clear[end-1] as usize;
    if clear[end-5..end-1]!=MAGIC || !(1..=8).contains(&wastage) || end<4+wastage+2 {
        return Err(invalid("encrypted packet footer"));
    }
    // Padding bytes are unspecified until measured; never assert on peer data.
    clear.truncate(end-4-wastage);
    Ok(clear)
}

pub(super) fn base_reply(request_id: u32, session_token: u32) -> Vec<u8> {
    // Measured reply envelope, payload hypothesis supported by EXE d762a0.
    let mut clear=vec![0,0,255];
    clear.extend(8u32.to_le_bytes());
    clear.extend(request_id.to_le_bytes());
    clear.extend(session_token.to_le_bytes());
    clear
}

fn first_channel_message(clear: &[u8], session_token: u32) -> io::Result<bool> {
    // Measured first element: ID 1 followed by the BaseApp reply's token.
    // Remaining messages/footers are NOT dispatched as a general protocol.
    if clear.len()<7 || clear[2]!=1 || clear[3..7]!=session_token.to_le_bytes() {
        return Err(invalid("unverified channel token/element"));
    }
    Ok(clear.len()==16 && clear[..2]==[0x58,0x04] && clear[7]==9 && clear[8..]==[0;8])
}

pub fn serve(key_path: &str) -> Result<(),Box<dyn std::error::Error>> {
    serve_mode(key_path, AckMode::Disabled)
}

pub fn serve_mode(key_path: &str, mode: AckMode) -> Result<(),Box<dyn std::error::Error>> {
    let private=login091::load_key(key_path)?;
    let login=UdpSocket::bind("127.0.0.1:20015")?;
    let base=UdpSocket::bind("127.0.0.1:20017")?;
    login.set_nonblocking(true)?;
    base.set_nonblocking(true)?;
    let login_key=OsRng.next_u32();
    let session_token=OsRng.next_u32();
    let mut accepted_key=None;
    let mut login_peer: Option<SocketAddr>=None;
    let mut base_peer: Option<SocketAddr>=None;
    let deadline=Instant::now()+Duration::from_secs(60);
    let mut count=0;
    let mut ack=FirstAck::new(mode);
    let mut server_first=if mode==AckMode::ServerFirst {Some(FirstServer::new())} else {None};
    let mut gap=if mode==AckMode::GapProbe {Some(GapProbe::new())} else {None};
    println!("BOUND 127.0.0.1:20015 base_backend=127.0.0.1:20017 profile={}",mode.profile());
    while Instant::now()<deadline && count<128 {
        for (is_login,socket) in [(true,&login),(false,&base)] {
            // Receive a whole datagram on Windows; reject oversize before crypto.
            let mut buf=[0u8;65536];
            let (length,addr)=match socket.recv_from(&mut buf) {
                Ok(pair)=>pair,
                Err(e) if e.kind()==io::ErrorKind::WouldBlock=>continue,
                Err(e)=>return Err(e.into()),
            };
            count+=1;
            if addr.ip()!=Ipv4Addr::LOCALHOST || length>MAX_WIRE {
                println!("BASEAPP_REJECT reason=address_or_size bytes={length}");continue;
            }
            let data=&buf[..length];
            if is_login {
                if login_peer.is_some_and(|p|p!=addr) {
                    println!("BASEAPP_REJECT reason=other_login_peer");continue;
                }
                let (request_id,fields)=match login091::decode(data,&private) {
                    Ok(value)=>value,
                    Err(_)=>{println!("BASEAPP_REJECT reason=invalid_login");continue;}
                };
                if accepted_key.is_some_and(|k|k!=fields.session_key) {
                    println!("BASEAPP_REJECT reason=second_key");continue;
                }
                accepted_key=Some(fields.session_key);login_peer=Some(addr);
                login091::print_fields(request_id,&fields);
                let wire=redirect091::reply(request_id,&fields.session_key,login_key)?;
                socket.send_to(&wire,addr)?;
                println!("LEGACY091_REDIRECT_SENT request_id={request_id} bytes={}",wire.len());
            } else {
                let Some(key)=accepted_key else {println!("BASEAPP_REJECT reason=no_login");continue;};
                if base_peer.is_some_and(|p|p!=addr) {
                    println!("BASEAPP_REJECT reason=other_base_peer");continue;
                }
                if length==21 {
                    let (request_id,attempt)=match base_request(data,login_key) {
                        Ok(value)=>value,
                        Err(_)=>{println!("BASEAPP_REJECT reason=invalid_base_request");continue;}
                    };
                    base_peer=Some(addr);
                    let wire=encrypt(&base_reply(request_id,session_token),&key)?;
                    socket.send_to(&wire,addr)?;
                    println!("BASEAPP_REPLY_SENT request_id={request_id} attempt={attempt} bytes={}",wire.len());
                } else if base_peer.is_some() {
                    match decrypt(data,&key) {
                        // Route the measured transport-only header before application
                        // token inspection: its counter bytes may accidentally equal a token.
                        Ok(clear) if clear.starts_with(&[0x48,4]) && server_first.is_some()=>{
                            if let Some(state)=server_first.as_mut() {
                                match state.observe_ack(&clear) {
                                    Ok((sequence,cumulative))=>println!("SERVER_RELIABLE_CLIENT_ACK sequence={sequence} cumulative={cumulative} acknowledged={}",state.ack_seen()),
                                    Err(_)=>println!("BASEAPP_REJECT reason=channel_token_or_transport_ack"),
                                }
                            }
                        },
                        Ok(clear)=>match first_channel_message(&clear,session_token) {
                            Ok(true)=>{
                                ack.observe_verified_first();
                                if let Some(state)=server_first.as_mut() {state.start(Instant::now());}
                                if let Some(state)=gap.as_mut() {state.start(Instant::now());}
                                println!("BASEAPP_NEXT_OBSERVED bytes={} clear_bytes={} token_verified=true",data.len(),clear.len());
                            },
                            Ok(false)=>{
                                println!("BASEAPP_UNPARSED_REMAINDER bytes={} clear_bytes={} flags=0x{:04x} token_verified=true",
                                    data.len(),clear.len(),u16::from_le_bytes([clear[0],clear[1]]));
                            },
                            Err(_)=>{
                                if gap.is_some() {
                                    println!("GAP_CLIENT_OBSERVED flags=0x{:04x} clear_bytes={}",u16::from_le_bytes([clear[0],clear[1]]),clear.len());
                                } else if server_first.is_some() {
                                    println!("BASEAPP_REJECT reason=channel_token_or_transport_ack");
                                } else {println!("BASEAPP_REJECT reason=channel_token_or_element");}
                            },
                        },
                        Err(_)=>println!("BASEAPP_REJECT reason=invalid_encrypted_packet bytes={length}"),
                    }
                    // No entity dispatch or manufactured connection callback.
                } else {
                    println!("BASEAPP_REJECT reason=no_base_handshake");
                }
            }
        }
        if let (Some(key),Some(peer))=(accepted_key,base_peer) {
            if let Some(state)=gap.as_mut() {
                if let Some((sequence,clear))=state.due(Instant::now()) {
                    let wire=encrypt(&clear,&key)?;base.send_to(&wire,peer)?;
                    println!("GAP_SERVER_SENT sequence={sequence} bytes={}",wire.len());
                }
            }
            if let Some(state)=server_first.as_mut() {
                if let Some((clear,duplicate))=state.due(Instant::now()) {
                    let wire=encrypt(&clear,&key)?;base.send_to(&wire,peer)?;
                    println!("SERVER_RELIABLE_SENT sequence=0 duplicate={duplicate} bytes={} ack_seen={}",wire.len(),state.ack_seen());
                }
            }
            if let Some(clear)=ack.due(Instant::now()) {
                let wire=encrypt(&clear,&key)?;
                base.send_to(&wire,peer)?;
                println!("CHANNEL_ACK_SENT end_seq={} bytes={} profile={}",clear[2],wire.len(),mode.profile());
            }
        }
        thread::sleep(Duration::from_millis(5));
    }
    Err("diagnostic deadline/packet limit reached".into())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn base_request_rejects_truncation_and_wrong_token() {
        let mut wire=vec![1,0,0,8,0];wire.extend([0;6]);wire.extend(42u32.to_le_bytes());wire.extend([0,0,0,0,2,0]);
        assert!(base_request(&wire,42).is_ok());
        for n in 0..21 {assert!(base_request(&wire[..n],42).is_err());}
        assert!(base_request(&wire,43).is_err());
        wire[15]=6;assert!(base_request(&wire,42).is_err());
    }
    #[test] fn decrypt_size_bounds_and_wrong_key() {
        let key=[17;16];let wire=encrypt(&base_reply(1,2),&key).unwrap();
        assert!(decrypt(&wire,&[18;16]).is_err());
        for n in 0..wire.len() {assert!(decrypt(&wire[..n],&key).is_err());}
        assert!(decrypt(&[0;1032],&key).is_err());
    }
    #[test] fn invalid_footer_is_error_not_panic() {
        let key=[19;16];let bf=cipher(&key).unwrap();
        for wastage in [0,9,255] {
            let mut clear=vec![0;24];clear[19..23].copy_from_slice(&MAGIC);clear[23]=wastage;
            let mut wire=Vec::new();
            {let mut w=BlowfishWriter::new(&mut wire,&bf);w.write_all(&clear).unwrap();w.flush().unwrap();}
            assert!(decrypt(&wire,&key).is_err());
        }
    }
    #[test] fn first_channel_token_required() {
        let mut clear=vec![0x58,4,1];clear.extend(42u32.to_le_bytes());clear.push(9);clear.extend([0;8]);
        assert_eq!(first_channel_message(&clear,42).unwrap(),true);
        assert!(first_channel_message(&clear,43).is_err());
        for n in 0..7 {assert!(first_channel_message(&clear[..n],42).is_err());}
        clear[2]=2;assert!(first_channel_message(&clear,42).is_err());
    }
}
