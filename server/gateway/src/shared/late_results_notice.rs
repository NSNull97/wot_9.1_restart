//! Original #717 direct Chat22 source consumer candidate, NEVER native PASS.
//! Method0x4b inherited slot16 is INFERRED, not an observed service packet.
//! No function here enqueues a message, ACKs a result, or discovers ownership.
use std::io;
use super::lifecycle_wire::Results;
fn bad(why:&'static str)->io::Error{io::Error::new(io::ErrorKind::InvalidData,format!("late result notice candidate: {why}"))}
fn string(out:&mut Vec<u8>,value:&str)->io::Result<()>{if value.len()>255||!value.is_ascii(){return Err(bad("own ASCII key bound"));}out.extend([b'U',value.len()as u8]);out.extend(value.as_bytes());Ok(())}
fn integer(out:&mut Vec<u8>,n:i64){
    if (0..=255).contains(&n){out.extend([b'K',n as u8]);}
    else if (0..=65535).contains(&n){out.push(b'M');out.extend((n as u16).to_le_bytes());}
    else if let Ok(n)=i32::try_from(n){out.push(b'J');out.extend(n.to_le_bytes());}
    else{let mut bytes=n.to_le_bytes().to_vec();while bytes.len()>1&&((bytes[bytes.len()-1]==0&&bytes[bytes.len()-2]&0x80==0)||(bytes[bytes.len()-1]==255&&bytes[bytes.len()-2]&0x80!=0)){bytes.pop();}
        out.extend([0x8a,bytes.len()as u8]);out.extend(bytes);}
}
/// Own primitive protocol2 data dictionary only. Full original Formatter.format
/// initializes display strings0 but still subtracts creditsToDraw from credits
/// at bytecode312, so numeric credits0 MUST be explicit. Project rewards are0.
/// No fake history deque or compressed data is sent to this direct callback.
fn data(result:&Results,own:i32)->io::Result<Vec<u8>>{
    result.validate_p06t()?;let owner=result.participants.iter().find(|p|p.account_dbid==own).ok_or_else(||bad("owner not in immutable result"))?;
    summary_data(result.arena_id,result.arena_type_id,result.created_unix,result.winner_team,owner.team,owner.type_compact_descr)
}
fn summary_data(arena:u64,map:i32,created:u32,winner_team:u8,own_team:u8,vehicle:u32)->io::Result<Vec<u8>>{
    if arena==0||arena>i64::MAX as u64||map<=0||created==0||winner_team>2||!(1..=2).contains(&own_team)
        ||vehicle==0||vehicle>u16::MAX as u32{return Err(bad("bounded actual pending summary"));}
    let winner=if winner_team==0{0}else if own_team==winner_team{1}else{-1};
    let mut out=vec![0x80,2,b'}',b'('];string(&mut out,"type")?;integer(&mut out,2);string(&mut out,"data")?;out.extend([b'}',b'(']);
    for(key,n)in [("arenaTypeID",i64::from(map)),("arenaCreateTime",i64::from(created)),("arenaUniqueID",arena as i64),
        ("isWinner",winner),("vehTypeCompDescr",i64::from(vehicle)),("xp",0),("credits",0)]{string(&mut out,key)?;integer(&mut out,n);}
    out.extend([b'u',b'u',b'.']);Ok(out)
}
/// Candidate direct personal service message. Caller must independently hold a
/// durable pending owner row and stage ONLY current authenticated ready Account,
/// sync7/correct epoch. Avatar/Returning/disconnect/pressure must retain notice.
/// This encoder makes none of those authority or delivery decisions.
pub(super) fn candidate_direct(result:&Results,own:i32,sent_unix:u32)->io::Result<Vec<u8>>{
    if sent_unix<result.created_unix||sent_unix==0{return Err(bad("actual UTC timestamp required"));}
    envelope(data(result,own)?,sent_unix)
}
/// Only a strictly parsed committed pending owner row may reach this helper.
pub(super) fn candidate_pending(row:&super::late_results_pending::Row,sent_unix:u32)->io::Result<Vec<u8>>{
    if sent_unix<row.created_unix||sent_unix==0{return Err(bad("actual UTC timestamp required"));}
    envelope(summary_data(row.arena,row.map,row.created_unix,row.winner,row.own_team,row.vehicle)?,sent_unix)
}
fn envelope(value:Vec<u8>,sent_unix:u32)->io::Result<Vec<u8>>{
    if value.len()>=255{return Err(bad("PYTHON scalar short budget; extended UNKNOWN"));}
    let mut body=(-1i64).to_le_bytes().to_vec();body.extend([22,0]); // personalSysMessage / success; source defaults
    let timestamp=f64::from(sent_unix).to_le_bytes();body.extend(timestamp);body.extend(timestamp);
    body.extend(0i32.to_le_bytes());body.extend((-1i64).to_le_bytes());body.extend([0,0]); // no channel/originator/nickname, group member
    body.push(value.len()as u8);body.extend(value);body.push(0); // PYTHON own primitive dictionary, flags0
    if body.len()>254{return Err(bad("unmeasured extended VAR1 callback"));}
    crate::hangar091::method(0x4b,&body)
}
#[cfg(test)]
#[path="late_results_notice_tests.rs"]mod tests;
