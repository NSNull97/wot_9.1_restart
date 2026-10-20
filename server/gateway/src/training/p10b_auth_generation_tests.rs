//! Domain metadata fixtures only. No real Session/writer/native qualification.
use super::*;

fn identity(n:u32,generation:u64)->AuthLease{
    let mut bytes=[0u8;16];bytes[..4].copy_from_slice(&n.to_le_bytes());
    AuthLease{account:Account(bytes),generation}
}
fn bind(reg:&mut Registry,n:u32,generation:u64,now:u64){reg.bind_authenticated(identity(n,generation),format!("Player{n}"),now).unwrap();}
fn denied(reg:&mut Registry,n:u32,generation:u64,now:u64,error:Error){
    let before=reg.clone();assert_eq!(reg.bind_authenticated(identity(n,generation),format!("Player{n}"),now),Err(error));assert_eq!(*reg,before);
}
fn settings()->Settings{Settings{capacity:2,map:QualifiedMap::Karelia,seconds:600,opened:true,comment:String::new()}}
fn prepared(reg:&mut Registry)->LaunchSnapshot{
    let ev=reg.command(identity(1,2),Command::Create(settings()),0).unwrap();
    let key=match ev[0]{Event::Created(k)=>k,_=>panic!()};
    reg.command(identity(2,2),Command::Join(key),0).unwrap();
    reg.command(identity(1,2),Command::Assign{target:identity(2,2).account,roster:Roster::assigned(Side::Two)},0).unwrap();
    for n in 1..=2{
        let ready=WriterReadyRef::from_verified_writer(identity(n,2).account,format!("fixture-owned-{n}"),13,[n as u8;32]).unwrap();
        let context=reg.selection_context(identity(n,2)).unwrap();
        reg.command(identity(n,2),Command::Ready{context,selection:ready},0).unwrap();
    }
    reg.command(identity(1,2),Command::TeamReady{side:Side::One,ready:true,force:false},0).unwrap();
    reg.command(identity(1,2),Command::TeamReady{side:Side::Two,ready:true,force:false},0).unwrap().into_iter()
        .find_map(|e|if let Event::Prepare(s)=e{Some(s)}else{None}).unwrap()
}

#[test]
fn p10b_generation_floor_rejects_retired_same_and_lower_after_disconnect(){
    let mut reg=Registry::default();bind(&mut reg,1,2,0);
    // Live same lease/name remains an idempotent heartbeat.
    bind(&mut reg,1,2,1);assert_eq!(reg.auth[&identity(1,2).account].last_seen,1);
    reg.disconnect(identity(1,2),2).unwrap();assert!(reg.auth.is_empty());
    denied(&mut reg,1,1,3,Error::StaleLease);denied(&mut reg,1,2,3,Error::StaleLease);
    bind(&mut reg,1,3,3);assert_eq!(reg.auth[&identity(1,3).account].generation,3);
    denied(&mut reg,1,2,4,Error::StaleLease);
}

#[test]
fn p10b_generation_floor_survives_exact_battle_finish_release(){
    // Exact original two-player path, with both auth rows removed only
    // after every synthetic durable-Finish binding is present.
    let mut reg=Registry::default();bind(&mut reg,1,2,0);bind(&mut reg,2,2,0);
    let snap=prepared(&mut reg);let battle=BattleKey(77);
    let reserves:Vec<_>=snap.members().iter().map(|m|ReservedRef::from_verified_writer(m.ready().clone(),format!("fixture-reserve:{}",m.account().0[0]),battle,snap.ticket()).unwrap()).collect();
    let finishes:Vec<_>=reserves.iter().map(|r|FinishedRef::from_verified_writer(r.ready.owner(),r.key.clone(),battle).unwrap()).collect();
    reg.commit_launch(snap.room(),snap.ticket(),battle,reserves,0).unwrap();
    for n in 1..=2{reg.disconnect(identity(n,2),0).unwrap();denied(&mut reg,n,1,0,Error::AlreadyClaimed);denied(&mut reg,n,3,0,Error::AlreadyClaimed);assert_eq!(reg.claim(identity(n,2).account),Some(Claim::Battle(battle)));}
    let before=reg.clone();assert_eq!(reg.finish_battle(battle,finishes[..1].to_vec(),0),Err(Error::WrongReceipt));assert_eq!(reg,before);
    reg.finish_battle(battle,finishes,0).unwrap();assert!(reg.auth.is_empty());assert!(reg.claims.is_empty());
    for n in 1..=2{denied(&mut reg,n,1,0,Error::StaleLease);denied(&mut reg,n,2,0,Error::StaleLease);bind(&mut reg,n,3,0);}
}

#[test]
fn p10b_generation_floor_lifetime_bound_never_evicts_and_live_auth_cap_is_unchanged(){
    let mut reg=Registry::default();
    for n in 1..=24{bind(&mut reg,n,1,0);}
    denied(&mut reg,25,1,0,Error::Limit);
    for n in 1..=24{reg.disconnect(identity(n,1),0).unwrap();}
    // A failed active-auth admission must not consume the lifetime identity slot.
    for n in 25..=1024{bind(&mut reg,n,1,0);reg.disconnect(identity(n,1),0).unwrap();}
    denied(&mut reg,1025,1,0,Error::Limit);
    denied(&mut reg,1,1,0,Error::StaleLease);bind(&mut reg,1,2,0);
    bind(&mut reg,1,2,0);reg.disconnect(identity(1,2),0).unwrap();
    denied(&mut reg,1,1,0,Error::StaleLease);denied(&mut reg,1,2,0,Error::StaleLease);
    bind(&mut reg,1,3,0);denied(&mut reg,1025,1,0,Error::Limit);
}
