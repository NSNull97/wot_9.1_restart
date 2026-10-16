//! Real server reset/result gates on an explicitly AUTHORED presentation fixture.
//! No SQL admission, original native client or swept-body physics is implied.
use super::*;
use super::super::{turret_publication_test_fixture as f,detached_turret as dt,lifecycle_wire::{Results,Participant}};
fn result(w:&World)->Arc<Results>{
    Arc::new(Results{arena_id:w.id,arena_type_id:4,created_unix:1792080000,winner_team:1,finish_reason:1,
        duration_seconds:10,interaction_details:None,participants:(0..2).map(|slot|Participant{
            vehicle_id:wire::vehicle_id(slot).unwrap(),account_dbid:w.actors[slot].identity.database,
            name:w.actors[slot].identity.name.clone(),team:slot as u8+1,type_compact_descr:3329,health:w.actors[slot].health,
            life_time:10,death_reason:if slot==1{0}else{-1},killer_id:if slot==1{wire::vehicle_id(0).unwrap()}else{0},
            shots:if slot==0{3}else{0},direct_hits:if slot==0{3}else{0},piercings:if slot==0{3}else{0},
            damage_dealt:if slot==0{90}else{0},damage_received:if slot==1{90}else{0},kills:if slot==0{1}else{0},..Default::default()
        }).collect()})
}
#[test]fn p06t_detonation_server_holds_old_world_until_avatar_handoff(){
    let now=Instant::now();let(s,mut w)=f::fixture(now);let mut table=Table::default();table.sessions.push(s);
    assert!(!turret_avatar_pending(&table,&w));f::detonate(&mut w);
    for actor in &mut w.actors{actor.session=None;}
    assert!(turret_avatar_pending(&table,&w));
    table.sessions[0].shared.as_mut().unwrap().phase=Phase::Leaving;assert!(turret_avatar_pending(&table,&w));
    table.sessions[0].arena_base=false;table.sessions[0].shared.as_mut().unwrap().phase=Phase::Returning;
    assert!(!turret_avatar_pending(&table,&w));
}
#[test]fn p06t_detonation_server_result_stream_waits_expiry_and_real_leave_ack(){
    let now=Instant::now();let(mut s,mut w)=f::fixture(now);f::detonate(&mut w);
    s.tx.enqueue_body(&dt::terminal_health(1,Some(0),0,dt::DeathKind::Detached).unwrap()).unwrap();f::ack_all(&mut s,now);
    s.shared.as_mut().unwrap().health_sent[1]=Some(0);s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();
    let mut req=vec![8,4,0];req.extend(dt::entity_id(1).unwrap().to_le_bytes());
    s.receive(&f::frame(&s,&req),now).unwrap();s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();f::ack_all(&mut s,now);
    let frozen=result(&w);let c=s.shared.as_mut().unwrap();c.phase=Phase::Leaving;c.natural_result=Some(frozen);c.result_committed=true;
    assert!(deliver_lifecycle_result(&mut s,&w,now).unwrap());assert!(!s.shared.as_ref().unwrap().result_stream_queued);
    let expired=now+Duration::from_secs(5);w.advance_turret_flights(expired).unwrap();
    s.flush_shared_turrets(&w,&mut Vec::new()).unwrap();
    assert!(deliver_lifecycle_result(&mut s,&w,expired).unwrap());assert!(!s.shared.as_ref().unwrap().result_stream_queued);
    assert_eq!(f::send_pending(&mut s,expired),dt::leave(1).unwrap());f::ack_all(&mut s,expired);
    assert!(deliver_lifecycle_result(&mut s,&w,expired).unwrap());
    assert!(s.shared.as_ref().unwrap().result_stream_queued);assert!(s.battle_results.avatar_pending());
    assert_eq!(w.actors[1].health,0);assert_eq!(w.ammo_detonations().len(),1);
}
