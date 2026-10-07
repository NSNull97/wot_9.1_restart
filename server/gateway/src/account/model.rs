//! Opt-in Account wire experiment, measured on #717. See P02_NATIVE_ACCOUNT.md.
//! No incoming PYTHON object is deserialized. Outgoing PYTHON is fixed lab config.
pub const ENTITY_ID:u32=0x09100001;

#[derive(Debug,Clone,PartialEq)]
pub struct Request {pub id:i16,pub command:i16}
pub fn requests(body:&[u8])->std::io::Result<Vec<Request>> {
    let bad=||std::io::Error::new(std::io::ErrorKind::InvalidData,"unmeasured Account request");
    if body.is_empty() || body.len()>69 || body.len()%23!=0 {return Err(bad());}
    let mut rows=Vec::new();
    for b in body.chunks_exact(23) {
        // Real native #717 doCmdInt3: 0x86 + measured exposed index8; VAR2.
        if b[..3]!=[0x8e,20,0] || b[7..].iter().any(|x|*x!=0) {return Err(bad());}
        let id=i16::from_le_bytes([b[3],b[4]]);let command=i16::from_le_bytes([b[5],b[6]]);
        if id<=0 || ![100,300,600].contains(&command) || rows.iter().any(|r:&Request|r.id==id || r.command==command) {return Err(bad());}
        rows.push(Request{id,command});
    } Ok(rows)
}
pub fn command_bit(command:i16)->u8 {match command {100=>1,300=>2,600=>4,_=>0}}
fn variable16(id:u8,payload:&[u8])->Vec<u8> {
    let mut b=vec![id];b.extend((payload.len() as u16).to_le_bytes());b.extend(payload);b
}
pub fn response(request:&Request)->Vec<u8> {
    // Native range begins at 0x3b; stable-size ordering predicts slot18.
    // Verified separately by original onCmdResponseExt trace, not by this encoder.
    let mut payload=Vec::new();payload.extend(request.id.to_le_bytes());
    payload.extend((if request.command==600 {1i16} else {0i16}).to_le_bytes());
    payload.push(0); // empty error STRING
    let ext=if request.command==100 {
        // Own laboratory account: revision1, empty inventory/stats/economics.
        b"\x80\x02}(U\x03revK\x01U\x09inventory}U\x05stats}U\x09economics}u.".as_slice()
    } else {b"\x80\x02}.".as_slice()};
    payload.push(ext.len() as u8);payload.extend(ext);
    let mut out=vec![0x13,0x4d,payload.len() as u8]; // selectPlayerEntity, method VAR1
    out.extend(payload);
    if request.command==600 {
        // One bounded native resource stream, original SyncController expects
        // zlib(protocol2((cacheVersion, dossiers))). Own empty dossier cache v0.
        let raw=b"\x80\x02K\x00]\x86.";
        let mut data=vec![0x78,0x01,0x01];
        data.extend((raw.len() as u16).to_le_bytes());data.extend((!(raw.len() as u16)).to_le_bytes());data.extend(raw);
        let(mut a,mut b)=(1u32,0u32);for x in raw {a=(a+*x as u32)%65521;b=(b+a)%65521;}data.extend(((b<<16)|a).to_be_bytes());
        let mut crc=0xffffffffu32;for x in &data {crc^=*x as u32;for _ in 0..8 {crc=(crc>>1)^if crc&1!=0 {0xedb88320}else{0};}}crc^=0xffffffff;
        // game.onStreamComplete checks signed Python2 zlib.crc32 and data length.
        let mut desc=vec![0x80,2,b'J'];desc.extend((data.len() as i32).to_le_bytes());desc.push(b'J');desc.extend(crc.to_le_bytes());desc.extend([0x86,b'.']);
        let mut header=request.id.to_le_bytes().to_vec();header.push(desc.len() as u8);header.extend(desc);
        out.extend(variable16(52,&header));
        let mut fragment=request.id.to_le_bytes().to_vec();fragment.extend([0,1]);fragment.extend(data);
        out.extend(variable16(53,&fragment));
    } out
}
pub fn creation()->Vec<u8> {
    creation_settings(b"\x80\x02}q\x00.")
}
pub fn creation_ready()->Vec<u8> {
    // Own service has no file endpoints or voice service. The original client
    // explicitly handles absent file types and empty voipDomain as unavailable.
    // Protocol 2: {'file_server': {}, 'voipDomain': ''}. No GLOBAL/REDUCE opcodes.
    creation_settings(b"\x80\x02}(U\x0bfile_server}U\x0avoipDomainU\x00u.")
}
fn creation_settings(settings:&[u8])->Vec<u8> {
    let mut payload=Vec::new();
    payload.extend(ENTITY_ID.to_le_bytes());
    payload.extend(0u16.to_le_bytes()); // Account type 0 confirmed by native player/class/fields.
    for text in [b"ru_0.9.1_2".as_slice(),b"p02-native-account".as_slice(),settings] {
        payload.push(text.len() as u8);payload.extend(text);
    }
    // createBasePlayer registration: #717 EXE 0x1683d50, VAR2; body reader 0xd6da50.
    let mut result=vec![5];result.extend((payload.len() as u16).to_le_bytes());result.extend(payload);result
}

#[cfg(test)]
mod tests {
    use super::*;
    // Application bytes measured from the original #717 client (request221).
    const SYNC:[u8;23]=[0x8e,20,0,221,0,100,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0];
    #[test] fn measured_request_and_boundary_mutations() {
        assert_eq!(requests(&SYNC).unwrap(),vec![Request{id:221,command:100}]);
        for length in 0..23 {assert!(requests(&SYNC[..length]).is_err());}
        for offset in [0,1,2,5,6,7,14,15,18,19,22] {
            let mut invalid=SYNC;invalid[offset]^=0x80;
            assert!(requests(&invalid).is_err(),"offset {offset}");
        }
        let mut invalid=SYNC;invalid[3..5].fill(0);assert!(requests(&invalid).is_err());
        invalid[4]=0x80;assert!(requests(&invalid).is_err());
        assert!(requests(&[SYNC,SYNC].concat()).is_err());
        assert!(requests(&[0;70]).is_err());
    }
    #[test] fn bundle_rejects_duplicate_command_or_request() {
        let mut other=SYNC;other[3]=222;
        assert!(requests(&[SYNC,other].concat()).is_err());
        other[3]=221;other[5..7].copy_from_slice(&300i16.to_le_bytes());
        assert!(requests(&[SYNC,other].concat()).is_err());
        other[3]=222;assert_eq!(requests(&[SYNC,other].concat()).unwrap().len(),2);
    }
}
