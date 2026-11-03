//! UI-06 fixtures: frags and the team killer flag come from the journals, reach
//! a recipient once by its native update and carry nothing else. Native UI
//! acceptance is separate.
use super::*;
use super::tests::frame;
use super::ui02_tests::{all_bodies,contains,hit_world,spotted};
use super::super::lifecycle::{Reason,Rules,State};
use super::super::lifecycle_result;
use super::super::lifecycle_wire::{self,Results,TEAM_SCORE_POLICY};
use super::super::team_score;

fn id(slot:usize)->u32 {wire::vehicle_id(slot).unwrap()}
fn ram(attacker:usize,target:usize,before:i16,after:i16)->model::RamDamageRecord {
    model::RamDamageRecord{sequence:1,tick:1,domain_tick:1000,attacker,target,pair:(0,1),energy_j:1.,closing_speed:1.,health_before:before,health_after:after}
}
fn damage(reason:u8,attacker:usize,target:usize,before:i16,after:i16)->model::DamageRecord {
    model::DamageRecord{sequence:1,tick:1000,attacker,target,shot:1,reason,health_before:before,health_after:after,
        crew_before:true,crew_after:after>0,direct:reason==0,pierced:reason==0}
}
/// Four vehicles of the mixed-ammo journal: 0, 2, 3 against 1.
fn mixed(now:Instant)->World {let mut w=unplanned(now);w.set_test_teams(&[1,2,1,1]);w}
/// No plan: slots alternate, as in a large battle of the template.
fn unplanned(now:Instant)->World {
    let authored=model::tests::world(now);
    let mut w=World::new_for_roster(6963,now,crate::map_profile091::MapId::Karelia,2).unwrap();
    w.enable_mixed_ammo().unwrap();w.actors=authored.actors;
    for database in [77,78] {let mut ally=w.actors[0].clone();ally.identity.database=database;ally.identity.name=format!("ally{database}");w.actors.push(ally);}
    w.lifecycle=Some(State::new(Rules::prohorovka()).unwrap());w.force_team_score_for_test();w
}
/// A real shell of slot 0 turned into a journal entry on `target`; 0 and 2 are one team.
fn shell_on(now:Instant,target:usize,lethal:bool)->(World,Instant) {
    let (mut w,now)=hit_world(now,0,1);
    let mut ally=w.actors[0].clone();ally.identity.database=77;ally.identity.name="ally".into();
    w.actors.push(ally);w.push_test_team_plan();
    w.actors[1].health=w.impacts[0].health_before;
    if lethal {w.impacts[0].health_after=0;}
    w.impacts[0].target=target;w.contacts[0].target_slot=target;
    w.actors[target].health=w.impacts[0].health_after;(w,now)
}
fn finish(w:&mut World) {
    let mut state=State::new(Rules::prohorovka()).unwrap();state.finish_for_test(1,Reason::Timeout);
    w.lifecycle=Some(state);w.lifecycle_created_unix=Some(1792080000);
}
fn publish(s:&mut Session,w:&World)->Vec<u8> {
    let mut outbox=VecDeque::new();
    team_score_publication::publish(s.shared.as_mut().unwrap(),&mut outbox,w).unwrap();
    assert!(outbox.iter().all(|body|!body.is_empty()&&body.len()<=500));
    outbox.into_iter().flatten().collect()
}
fn stat(slot:usize,frags:i16)->Vec<u8> {lifecycle_wire::vehicle_statistics(id(slot),frags).unwrap()}
fn flag(slot:usize)->Vec<u8> {lifecycle_wire::team_killer(id(slot)).unwrap()}
/// Native records of the concatenated stream, in order, without the frame around them.
fn native_records(raw:&[u8])->Vec<(u8,Vec<u8>)> {
    let (mut rows,mut at)=(Vec::new(),0);
    while at+5<=raw.len() {
        if raw[at..at+2]==[0x13,0x58]&&[5,10].contains(&raw[at+3]) {
            let end=at+5+usize::from(raw[at+4]);rows.push((raw[at+3],raw[at+5..end].to_vec()));at=end;
        } else {at+=1;}
    }
    rows
}
fn strip(mut raw:Vec<u8>,records:&[Vec<u8>])->Vec<u8> {
    for record in records {
        let at=raw.windows(record.len()).position(|v|v==record).expect("record in the stream");
        raw.drain(at..at+record.len());
    }
    raw
}

#[test] fn ui06_native_records_are_the_pickles_the_client_reads() {
    let mut expected=vec![0x13,0x58,14,5,12,0x80,2,b'J'];expected.extend(id(3).to_le_bytes());expected.push(b'J');
    expected.extend((-2i32).to_le_bytes());expected.extend([0x86,b'.']);
    expected[2]=expected.len() as u8-3;expected[4]=expected.len() as u8-5;
    assert_eq!(stat(3,-2),expected);
    let mut small=vec![0x80,2,b'J'];small.extend(id(3).to_le_bytes());small.extend([b'K',3,0x86,b'.']);
    assert_eq!(&stat(3,3)[5..],&small[..]);
    let mut bare=vec![0x13,0x58,10,10,8,0x80,2,b'J'];bare.extend(id(1).to_le_bytes());bare.push(b'.');
    assert_eq!(flag(1),bare);
    assert!(lifecycle_wire::vehicle_statistics(0,1).is_err());assert!(lifecycle_wire::team_killer(0).is_err());
    assert!(lifecycle_wire::vehicle_statistics(id(0),30).is_err()&&lifecycle_wire::vehicle_statistics(id(0),-30).is_err());
    assert!(lifecycle_wire::vehicle_statistics(id(0),-29).is_ok());
}
#[test] fn ui06_enemy_adds_ally_takes_away_down_to_negative() {
    let mut w=mixed(Instant::now());
    w.damage_events=vec![damage(0,0,1,100,0)].into();
    assert_eq!(team_score::table(&w).unwrap()[0].frags,1);
    w.damage_events.push(damage(0,0,2,100,0));
    let row=team_score::table(&w).unwrap()[0];
    assert_eq!((row.frags,row.team_kills,row.team_killer),(0,1,true));
    w.damage_events.push(damage(0,0,3,100,0));
    w.ram_damage_events.push(ram(2,3,50,0));
    let rows=team_score::table(&w).unwrap();
    assert_eq!((rows[0].frags,rows[0].team_kills),(-1,2));
    assert_eq!((rows[2].frags,rows[2].team_killer),(-1,true),"a ram kill counts like a shell");
    assert_eq!((rows[1].frags,rows[1].team_killer),(0,false));
}
#[test] fn ui06_fire_scores_for_its_author_and_a_death_by_ones_own_hand_for_nobody() {
    let mut w=mixed(Instant::now());
    w.damage_events=vec![damage(1,2,0,20,0),damage(1,0,1,20,0),damage(0,3,3,20,0)].into();
    let rows=team_score::table(&w).unwrap();
    assert_eq!((rows[2].frags,rows[2].team_kills,rows[2].team_damage,rows[2].team_killer),(-1,1,20,true));
    assert_eq!((rows[0].frags,rows[0].team_killer),(1,false));
    assert_eq!((rows[3].frags,rows[3].team_kills,rows[3].team_damage,rows[3].team_killer),(0,0,0,false));
}
#[test] fn ui06_any_shell_or_fire_hp_on_an_ally_paints_ramming_only_by_a_kill() {
    let mut w=mixed(Instant::now());
    w.damage_events=vec![damage(0,0,2,100,99)].into();
    let row=team_score::table(&w).unwrap()[0];
    assert_eq!((row.frags,row.team_damage,row.team_killer),(0,1,true));
    w.damage_events=vec![damage(0,0,2,100,100)].into();
    assert!(!team_score::table(&w).unwrap()[0].team_killer,"no HP lost, nothing to punish");
    w.damage_events=vec![damage(0,0,1,100,1)].into();
    assert_eq!(team_score::table(&w).unwrap()[0],team_score::Score::default(),"the enemy is not team damage");
    w.damage_events.clear();w.ram_damage_events=vec![ram(0,2,100,90),ram(2,0,100,95)].into();
    let rows=team_score::table(&w).unwrap();
    assert_eq!((rows[0].team_damage,rows[0].team_killer),(10,false));
    assert_eq!((rows[2].team_damage,rows[2].team_killer),(5,false));
}
#[test] fn ui06_the_flag_never_goes_back_while_the_battle_lasts() {
    let mut w=mixed(Instant::now());
    w.damage_events=vec![damage(0,0,2,100,50)].into();
    w.ram_damage_events=vec![ram(1,2,50,0)].into();
    assert!(team_score::table(&w).unwrap()[0].team_killer,"a journal only grows, the victim's death changes nothing");
}
#[test] fn ui06_without_the_key_not_one_byte_and_the_row_stays_clean() {
    let (w,now)=shell_on(Instant::now(),2,true);
    let mut s=spotted(now,&w,0);
    assert!(publish(&mut s,&w).is_empty());
    let mut on=w.clone();on.force_team_score_for_test();
    assert_eq!(wire::roster_updates(&w,0,2).unwrap().iter().filter(|b|**b==0x88).count()+1,
        wire::roster_updates(&on,0,2).unwrap().iter().filter(|b|**b==0x88).count(),"one boolean turned on");
}
#[test] fn ui06_frags_go_to_all_the_flag_only_to_the_team_of_the_violator() {
    let (mut w,now)=shell_on(Instant::now(),2,true);w.force_team_score_for_test();
    let mut ally=spotted(now,&w,0);
    assert_eq!(publish(&mut ally,&w),[stat(0,-1),flag(0)].concat());
    let mut enemy=spotted(now,&w,1);
    assert_eq!(publish(&mut enemy,&w),stat(0,-1),"the enemy team gets no flag at all");
    let (for_team,for_enemy)=(wire::roster_updates(&w,0,0).unwrap(),wire::roster_updates(&w,0,1).unwrap());
    let diff=for_team.iter().zip(&for_enemy).filter(|(a,b)|a!=b).collect::<Vec<_>>();
    assert_eq!((for_team.len(),diff),(for_enemy.len(),vec![(&0x88u8,&0x89u8)]),"one boolean of the native row");
}
#[test] fn ui06_a_fact_is_sent_once_and_a_loaded_scene_gets_all_of_them_again() {
    let (mut w,now)=shell_on(Instant::now(),2,true);w.force_team_score_for_test();
    let mut s=spotted(now,&w,0);
    assert!(!publish(&mut s,&w).is_empty());
    assert!(publish(&mut s,&w).is_empty(),"nothing new");
    w.ram_damage_events.push(ram(2,1,100,90));
    assert!(publish(&mut s,&w).is_empty(),"a journal moved, the score did not");
    w.ram_damage_events.push(ram(2,1,90,0));
    assert_eq!(publish(&mut s,&w),stat(2,1));
    // The measured native READY of a scene load (wire::ready), for the own vehicle.
    let c=s.shared.as_mut().unwrap();c.phase=Phase::Entities;c.creations[0]=Some((0,true));
    let mut ready=[0x0d,8,0,0,0,0,0,3,0,16,9,0x8d,5,0,2,1,0,0,0,0x86,0,0,0x0c,8,0,0,0,0,0,0,0,0,0];
    ready[7..11].copy_from_slice(&id(0).to_le_bytes());
    s.receive(&frame(&s,&ready),now).unwrap();
    assert_eq!(s.shared.as_ref().unwrap().phase,Phase::Driving);
    assert_eq!(publish(&mut s,&w),[stat(0,-1),flag(0),stat(2,1)].concat());
}
#[test] fn ui06_a_score_back_at_zero_is_still_sent() {
    let (mut w,now)=shell_on(Instant::now(),2,true);w.force_team_score_for_test();
    let mut s=spotted(now,&w,0);publish(&mut s,&w);
    w.ram_damage_events.push(ram(0,1,100,0));
    assert_eq!(publish(&mut s,&w),stat(0,0),"the client prints nothing for zero, it still has to know");
}
#[test] fn ui06_thirty_changes_fit_the_native_body_limit() {
    let mut w=unplanned(Instant::now());
    let template=w.actors[2].clone();
    while w.actors.len()<model::MAX_ACTORS {let mut a=template.clone();a.identity.database=w.actors.len() as i32+100;w.actors.push(a);}
    w.damage_events=(0..model::MAX_ACTORS as usize).map(|slot|damage(0,slot,(slot+2)%model::MAX_ACTORS,100,0)).collect::<Vec<_>>().into();
    let mut s=spotted(Instant::now(),&{let (w,_)=shell_on(Instant::now(),2,true);w},0);
    assert_eq!(native_records(&publish(&mut s,&w)).len(),model::MAX_ACTORS*2-model::MAX_ACTORS/2,"every record, each body within 500 bytes");
}
/// The whole native pass of a recipient, with the key and without.
fn pass(w:&mut World,own:usize,enabled:bool,now:Instant)->Vec<u8> {
    if enabled {w.force_team_score_for_test();}
    let mut s=spotted(now,w,own);
    s.shared.as_mut().unwrap().impact_cursor=0;
    poll(&mut s,w,now).unwrap();all_bodies(&mut s,now).concat()
}
#[test] fn ui06_the_key_adds_only_its_records_about_a_hidden_vehicle() {
    // Slot 1 is out of sight of slot 0 and has just killed it.
    let build=|now:Instant|{let (mut w,now)=hit_world(now,1,0);w.actors[1].position[0]=500.;
        w.impacts[0].health_after=0;w.actors[0].health=0;(w,now)};
    let start=Instant::now();
    let (mut off,now)=build(start);let plain=pass(&mut off,0,false,now);
    let (mut on,now)=build(start);let spotted_raw=pass(&mut on,0,true,now);
    assert_eq!(native_records(&spotted_raw),vec![(5,stat(1,1)[5..].to_vec())],"its frag, public like vehicle_killed");
    assert_eq!(strip(spotted_raw.clone(),&[stat(1,1)]),plain,"nothing else in the recipient's stream changed");
    let position=&on.actors[1].position;
    for bytes in [position[0].to_le_bytes(),position[2].to_le_bytes()] {assert!(!contains(&spotted_raw,&bytes),"no position of the hidden vehicle");}
    // HP of the hidden vehicle: its only records above hold an ID and a frag,
    // and everything else is byte for byte the stream without the key.
}
#[test] fn ui06_the_flag_of_an_ally_adds_only_its_record() {
    // Ally 2 far away has the shell of slot 1 in the journals: on recipient 0.
    let build=|now:Instant|{let (mut w,now)=hit_world(now,1,0);
        let mut ally=w.actors[1].clone();ally.identity.database=77;ally.identity.name="ally".into();ally.position[0]=500.;
        w.actors.push(ally);w.push_test_team_plan();
        w.impacts[0].attacker=2;w.shots[0].slot=2;(w,now)};
    let start=Instant::now();
    let (mut off,now)=build(start);let plain=pass(&mut off,0,false,now);
    let (mut on,now)=build(start);let raw=pass(&mut on,0,true,now);
    assert_eq!(native_records(&raw),vec![(10,flag(2)[5..].to_vec())]);
    assert_eq!(strip(raw.clone(),&[flag(2)]),plain,"nothing else in the recipient's stream changed");
}
#[test] fn ui06_damage_to_an_ally_changes_nothing_for_the_other_team() {
    let build=|now:Instant|shell_on(now,2,false);
    let start=Instant::now();
    let (mut off,now)=build(start);let plain=pass(&mut off,1,false,now);
    let (mut on,now)=build(start);
    assert_eq!(pass(&mut on,1,true,now),plain,"no flag, no frag, the same stream");
}
#[test] fn ui06_results_carry_the_battle_values_into_the_native_fields() {
    let (mut w,_)=shell_on(Instant::now(),2,true);w.force_team_score_for_test();finish(&mut w);
    let result=lifecycle_result::build(&w).unwrap();
    let score=result.team_score.as_ref().unwrap();
    assert_eq!((score.version,score.policy.as_str(),score.rows.len()),(1,TEAM_SCORE_POLICY,3));
    let hp=u32::from(w.impacts[0].health_before as u16);
    let row=&score.rows[0];
    assert_eq!((row.vehicle_id,row.frags,row.team_kills,row.team_damage,row.team_hits,row.team_killer),(id(0),-1,1,hp,1,true));
    assert_eq!((score.rows[1].frags,score.rows[1].team_killer),(0,false));
    assert_eq!(result.participants[0].kills,1,"native kills keep every kill, the window subtracts tkills itself");
    let decoded:Results=serde_json::from_str(&serde_json::to_string(&result).unwrap()).unwrap();
    decoded.validate().unwrap();assert_eq!(decoded,result);
    let raw=lifecycle_wire::compact_results(&result,w.actors[0].identity.database).unwrap();
    let plain={let mut r=result.clone();r.team_score=None;lifecycle_wire::compact_results(&r,w.actors[0].identity.database).unwrap()};
    assert_ne!(raw,plain,"the native fields stopped being zero");
}
#[test] fn ui06_without_the_key_the_journal_stays_as_it_was() {
    let (mut w,_)=shell_on(Instant::now(),2,true);finish(&mut w);
    let result=lifecycle_result::build(&w).unwrap();
    assert_eq!(result.team_score,None);
    assert!(!serde_json::to_string(&result).unwrap().contains("team_score"));
}
#[test] fn ui06_a_score_that_disagrees_with_the_deaths_is_refused() {
    let (mut w,_)=shell_on(Instant::now(),2,true);w.force_team_score_for_test();finish(&mut w);
    let result=lifecycle_result::build(&w).unwrap();
    let refused=|edit:fn(&mut Results)|{let mut r=result.clone();edit(&mut r);assert!(r.validate().is_err());};
    refused(|r|r.team_score.as_mut().unwrap().version=2);
    refused(|r|r.team_score.as_mut().unwrap().policy="fake".into());
    refused(|r|{r.team_score.as_mut().unwrap().rows.pop();});
    refused(|r|r.team_score.as_mut().unwrap().rows.reverse());
    refused(|r|r.team_score.as_mut().unwrap().rows[0].frags=0);
    refused(|r|r.team_score.as_mut().unwrap().rows[0].team_kills=0);
    refused(|r|r.team_score.as_mut().unwrap().rows[0].team_killer=false);
    refused(|r|r.team_score.as_mut().unwrap().rows[0].team_damage=60001);
    refused(|r|r.team_score.as_mut().unwrap().rows[1].team_hits=1);
}
