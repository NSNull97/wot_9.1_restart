//! Launch scheduling tests. Selection/Admit bytes are pinned ACTUAL SQL DTOs.
//! Cache/Fresh/Session identity/current source epochs are AUTHORED tiny seams;
//! the two separate SQL runs are bridged ONLY by an explicit cfg(test) helper.
//! No current ownership, actual refresh, native or physical start is claimed.
use super::*;
use crate::profile13_v2091 as writer;
use crate::training091::{adapter,aliases,controller::Call,current_room::ProfileStamp,ingress,selection,wire as room_wire};
use serde_json::{json,Value};
use sha2::{Digest,Sha256};
use std::{path::{Path,PathBuf},sync::atomic::{AtomicU64,Ordering}};
const SELECT:&[u8]=include_bytes!("../../../../tests/fixtures/p10b-selection-writer-vectors.json");
const SQL:&[u8]=include_bytes!("../../../../tests/fixtures/p10b-saga-writer-vectors.json");
fn values()->(Value,Value){
    assert_eq!(format!("{:x}",Sha256::digest(SELECT)),"b9a5b3a693242b958efd7b0e853b22b028e5b8ac13b9b3315194f13622b7c9cf");
    assert_eq!(format!("{:x}",Sha256::digest(SQL)),"2986a4eca23fb1cfe176be460ebbbeb015df0bfc0a48fcf86eb69675e92abee9");
    (serde_json::from_slice(SELECT).unwrap(),serde_json::from_slice(SQL).unwrap())
}
fn ctx(v:&Value)->crate::battle091::profile13::Context{crate::battle091::profile13::Context{
    account_id:v["account_id"].as_str().unwrap().into(),native_database_id:v["native_database_id"].as_i64().unwrap().try_into().unwrap(),
    command_key:v.get("command_key").and_then(Value::as_str).unwrap_or("selection-only").into(),expected_revision:v["expected_revision"].as_u64().unwrap(),run_id:v["run_id"].as_str().unwrap().into()}}
fn fixture(account:&str,db:i32,rev:u64,extra:bool)->(PathBuf,Arc<crate::hangar091::Fixtures>){
    static NEXT:AtomicU64=AtomicU64::new(0);
    let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs/p10b-launch-host");fs::create_dir_all(&root).unwrap();
    let path=root.join(format!("{}-{}-{}",std::process::id(),std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos(),NEXT.fetch_add(1,Ordering::Relaxed)));fs::create_dir(&path).unwrap();
    let mut state=b"\x80\x02}(U\x03revK\x01U\x05ownerU".to_vec();state.push(account.len()as u8);state.extend(account.as_bytes());
    if extra{state.extend(b"U\x01xK\x01");}state.extend(b"u.");
    fs::write(path.join("state.bin"),&state).unwrap();fs::write(path.join("shop.bin"),b"\x80\x02}(U\x03revK\x03u.").unwrap();fs::write(path.join("dossier.bin"),b"\x80\x02(K\x00]t.").unwrap();
    let p=&crate::p04m_companion091::test_value(account,rev);let mut pool=p.clone();pool["native_database_id"]=db.into();pool["state_sha256"]=format!("{:x}",Sha256::digest(&state)).into();
    fs::write(path.join("p04m-pool.json"),serde_json::to_vec(&pool).unwrap()).unwrap();
    let manifest=json!({"fixture_version":13,"profile_version":13,"snapshot_revision":rev,"account_id":account,"native_database_id":db,
        "pool_schema":crate::p04m_companion091::SCHEMA,"pool_registry_sha256":crate::p04m_companion091::REGISTRY_SHA256,"pool_policy_sha256":crate::p04m_companion091::POLICY_SHA256});
    fs::write(path.join("manifest.json"),serde_json::to_vec(&manifest).unwrap()).unwrap();
    let f=Arc::new(crate::hangar091::Fixtures::load_p04m(&path).unwrap());(path,f)
}
fn live(owner:Arc<crate::identity091::Profile>,fixtures:Arc<crate::hangar091::Fixtures>,c:&crate::battle091::profile13::Context,now:Instant)->Session{
    let mut s=Session::new(100+owner.database_id as u32,[7;16],"127.0.0.1:41707".parse().unwrap(),now);
    s.identity=Some(owner);s.hangar=Some(fixtures);s.active=true;s.account_ready=true;s.sync_mask=7;s.rx=1;s.tx=Window::interactive();
    s.training_opt_in=true;s.training_flights=Some(Default::default());s.base_peer=Some("127.0.0.1:41708".parse().unwrap());
    s.ammo_service=Some(ammo_session::State::new(crate::ammo_service091::Metadata{revision:c.expected_revision,wire_revision:1},true).with_transfer(true).with_cross_vehicle(true)
        .with_roster_recruitment(true).with_progression(true).with_dismissal(true).with_barracks(true).with_research(true));
    s.ammo_service.as_mut().unwrap().replace_pool(s.hangar.as_ref().unwrap().p04m_binding().cloned()).unwrap();
    let mut client=Client::new(0);client.join_requested=false;client.hangar_since=Some(now);client.profile13=Some(persistence::State::new(c.run_id.clone(),c.expected_revision).unwrap());s.shared=Some(client);s
}
pub(in crate::gateway091::shared::server) fn native(id:i16,cmd:i16,a:i64,b:i32)->ingress::Request{let mut raw=vec![0x8e,20,0];raw.extend(id.to_le_bytes());raw.extend(cmd.to_le_bytes());raw.extend(a.to_le_bytes());raw.extend(b.to_le_bytes());raw.extend(0i32.to_le_bytes());ingress::record(&raw).unwrap().unwrap()}
pub(in crate::gateway091::shared::server) fn create()->ingress::Request{let mut raw=vec![0x9a,10,0];raw.extend(4i32.to_le_bytes());raw.extend(600i32.to_le_bytes());raw.extend([1,0]);ingress::record(&raw).unwrap().unwrap()}
fn call(s:&Session,stamp:&selection::Stamp)->Call{
    let mut source=[0;32];for(i,pair)in stamp.owner_source_sha256.as_bytes().chunks_exact(2).enumerate(){source[i]=u8::from_str_radix(std::str::from_utf8(pair).unwrap(),16).unwrap();}
    Call{caller:room::AuthLease{account:account(&s.identity.as_ref().unwrap().account_id).unwrap(),generation:u64::from(s.id)},
        channel:Channel{session:s.id,generation:s.training_account_generation()},profile:ProfileStamp{revision:s.ammo_service.as_ref().unwrap().revision()as u32,source_binding:source},expected_revision:s.ammo_service.as_ref().unwrap().revision()as u32}
}
pub(in crate::gateway091::shared::server) struct Input{pub(in crate::gateway091::shared::server) table:Table,pub(in crate::gateway091::shared::server) controller:Controller,pub(in crate::gateway091::shared::server) world:World,pub(in crate::gateway091::shared::server) template:BattleTemplate,pub(in crate::gateway091::shared::server) saga:saga::Saga,pub(in crate::gateway091::shared::server) held:Vec<HeldFresh>,pub(in crate::gateway091::shared::server) origins:BTreeMap<room::Account,LaunchOrigin>,pub(in crate::gateway091::shared::server) calls:Vec<Call>,pub(in crate::gateway091::shared::server) facts:BTreeMap<room::Account,adapter::NativeFacts>}
pub(in crate::gateway091::shared::server) fn input(now:Instant)->Input{input_mode(now,false)}
pub(in crate::gateway091::shared::server) fn input_mode(now:Instant,bench:bool)->Input{
    let(select,sql)=values();let sql=sql["cases"].as_array().unwrap().iter().find(|c|c["case"].as_str().unwrap().contains("two_real_owned")).unwrap();
    let mut selections=Vec::new();let mut sessions=Vec::new();let mut calls=Vec::new();let mut controller=Controller::default();let mut facts=BTreeMap::new();
    for row in select["vectors"].as_array().unwrap().iter().take(2){let q=&row["request"];let c=ctx(q);
        let request=selection::Request::new(&c,1,selection::Stamp::parse(&q["projection_stamp"]).unwrap()).unwrap();
        let parsed=selection::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&request).unwrap();
        let lane=if c.native_database_id==3{"C"}else{"D"};let admit=sql["calls"][lane].as_array().unwrap().iter().find(|r|r["request"]["operation"]=="admit").unwrap();let admit_context=ctx(&admit["request"]);
        let(path,fixtures)=fixture(&c.account_id,c.native_database_id,c.expected_revision,false);
        let owner=Arc::new(crate::identity091::Profile{account_id:c.account_id.clone(),database_id:c.native_database_id,name:format!("Owner{}",c.native_database_id),fixture_dir:path});
        let selected=saga::ReadySelection::from_selection(owner.clone(),100+c.native_database_id as u32,parsed).unwrap()
            .with_launch_scheduler_seam_for_test(admit_context.run_id.clone(),source_hex(&fixtures.state_sha256()));
        let s=live(owner,fixtures,&admit_context,now);let call=call(&s,selected.source_stamp().base());
        controller.bind(call.caller,call.channel,s.identity.as_ref().unwrap().name.clone(),c.native_database_id,0).unwrap();
        facts.insert(call.caller.account,adapter::NativeFacts{database_id:c.native_database_id,selected:None,descriptor:Vec::new(),igr_type:0,clan_database_id:0,clan_abbrev:String::new()});
        selections.push(selected);sessions.push(s);calls.push(call);
    }
    controller.apply(calls[0],create(),&facts,0).unwrap();let room=controller.registry().authenticated_room(calls[0].caller).unwrap();let native_room=controller.native_room(room).unwrap();
    controller.apply(calls[1],native(202,400,i64::from(native_room),0),&facts,0).unwrap();
    // Fresh controller, one peer: its first actual room alias is OWN+1.
    controller.apply(calls[0],native(222,404,i64::from(aliases::OWN_ENTITY_ID+1),2),&facts,0).unwrap();
    if bench{
        // Authored authenticated spectator metadata; no Ready/Frozen/reservation
        // is created for this additional account and it never becomes an actor.
        let uuid="55555555-5555-4555-8555-555555555555";let base=ctx(&select["vectors"][0]["request"]);
        let c=crate::battle091::profile13::Context{account_id:uuid.into(),native_database_id:5,expected_revision:13,..base};
        let(path,fixtures)=fixture(uuid,5,13,false);let owner=Arc::new(crate::identity091::Profile{account_id:uuid.into(),database_id:5,name:"Bench5".into(),fixture_dir:path});
        let s=live(owner,fixtures,&c,now);let call=call(&s,selections[0].source_stamp().base());
        controller.bind(call.caller,call.channel,"Bench5".into(),5,0).unwrap();facts.insert(call.caller.account,adapter::NativeFacts{database_id:5,selected:None,descriptor:Vec::new(),igr_type:0,clan_database_id:0,clan_abbrev:String::new()});
        controller.apply(call,native(202,400,i64::from(native_room),0),&facts,0).unwrap();sessions.push(s);calls.push(call);
    }
    let mut origins=BTreeMap::new();
    for index in 0..2{let selected=&selections[index];let batch=controller.apply(calls[index],native(223,402,1,0),&facts,0).unwrap();let task=batch.ready[0].clone();
        let fact=facts.get_mut(&calls[index].caller.account).unwrap();fact.selected=Some(selected.reference().clone());fact.descriptor=selected.loadout().descriptor.clone();
        controller.complete_ready(&task,calls[index],1,selected.reference().clone(),&facts,0).unwrap();
        let origin=LaunchOrigin::capture(&sessions[index],&controller,task,selected.clone()).unwrap();origins.insert(calls[index].caller.account,origin);
    }
    controller.apply(calls[0],native(224,411,1,0),&facts,0).unwrap();let batch=controller.apply(calls[0],native(225,411,2,0),&facts,0).unwrap();let snapshot=batch.prepare[0].snapshot().clone();
    let battle=room::BattleKey(9007199254740993);let mut saga=saga::Saga::new(snapshot,battle,selections).unwrap();
    for s in sessions.iter_mut().take(2){s.shared.as_mut().unwrap().profile13.as_mut().unwrap().in_flight=true;}
    let mut held=Vec::new();
    for _ in 0..2{let(sid,owner,_)=saga.next_admission_origin().unwrap();let lane=if owner.database_id==3{"C"}else{"D"};let row=sql["calls"][lane].as_array().unwrap().iter().find(|r|r["request"]["operation"]=="admit").unwrap();
        let context=ctx(&row["request"]);let task=saga.next_admit(context.clone()).unwrap().unwrap();assert_eq!(sid,task.session());
        let request=writer::Request::Admit{battle:battle.0,native_inventory_id:1};assert_eq!(&request,task.request().v2());
        let reply=writer::parse_reply(&serde_json::to_vec(&row["response"]).unwrap(),&context,&request).unwrap();
        let(path,fixtures)=fixture(&owner.account_id,owner.database_id,reply.revision,false);let fresh_owner=Arc::new(crate::identity091::Profile{fixture_dir:path,account_id:owner.account_id.clone(),database_id:owner.database_id,name:owner.name.clone()});
        let done=saga::Completion::V2(persistence::CompletionV2{session:sid,old_owner:owner,context,request,fresh:Some(persistence::Fresh{owner:fresh_owner,fixtures,binding:crate::ammo_service091::Metadata{revision:reply.revision,wire_revision:1}}),reply,refresh_error:None});
        let cached=HeldFresh::capture(&task,&done).unwrap();saga.complete(&done).unwrap();held.push(cached);
    }
    let mut world=World::new_for_roster(battle.0,now,MapId::Prohorovka,6).unwrap();world.enable_mixed_ammo().unwrap();world.enable_lifecycle(super::super::super::lifecycle::Rules::prohorovka()).unwrap();
    let template=BattleTemplate::new(&world,&None);Input{table:Table{sessions,capacity:6,..Table::default()},controller,world,template,saga,held,origins,calls,facts}
}
fn stage(i:&Input,now:Instant)->io::Result<LaunchStage>{stage_launch(&i.table,&i.controller,&i.world,&None,&i.template,&i.saga,&i.held,&i.origins,now,0)}
fn unchanged(i:&Input)->(Controller,Vec<(u32,persistence::State,u64,usize,usize)>,String){
    (i.controller.clone(),i.table.sessions.iter().map(|s|(s.id,s.shared.as_ref().unwrap().profile13.as_ref().unwrap().clone(),s.ammo_service.as_ref().unwrap().revision(),s.outbox.len(),s.tx.len())).collect(),i.world.failure_snapshot().to_string())
}

#[test]fn p10b_launch_actual_two_SQL_reserves_stage_frozen_BTree_order_not_arrival_then_real_ACK_gate(){
    let now=Instant::now();let mut i=input(now);let before=unchanged(&i);let prepared=stage(&i,now).unwrap();assert_eq!(unchanged(&i),before);
    let mut runtime=None;let event=prepared.commit(&mut i.table,&mut i.controller,&mut i.world,&mut runtime);
    assert_eq!(event.awaiting_handoff,vec![104,103]);assert_eq!(i.table.sessions.iter().map(|s|s.id).collect::<Vec<_>>(),vec![103,104]);
    assert_eq!(i.world.actors.iter().map(|a|a.identity.database).collect::<Vec<_>>(),vec![4,3]);assert_eq!(i.world.team_plan().unwrap().teams(),[2,1]);assert_eq!(i.world.expected_actors(),2);
    assert!(i.world.started.is_none()&&runtime.is_none());assert_eq!(i.template.world.expected_actors(),6);assert!(i.template.world.actors.is_empty());
    // Authoritative lifecycle clock only; no physical/native World start.
    let mut life=i.world.lifecycle.clone().unwrap();let members=i.world.actors.iter().enumerate().map(|(slot,a)|super::super::super::lifecycle::Member{
        team:i.world.team(slot).unwrap(),present:true,ready:true,alive:true,position:a.position,damage_epoch:0,last_damager:None}).collect::<Vec<_>>();
    for tick in 0..=30{life.advance(tick*1000,&members).unwrap();}assert_eq!(life.view().length_ms,600_000);
    for(slot,id)in event.awaiting_handoff.iter().enumerate(){let s=i.table.sessions.iter().find(|s|s.id==*id).unwrap();let c=s.shared.as_ref().unwrap();let p=c.profile13.as_ref().unwrap();
        assert_eq!(c.phase,Phase::Account);assert_eq!(c.slot,slot);assert!(c.join_requested&&!c.queue_announced&&!p.in_flight);assert_eq!(p.reservation_v2.as_ref().unwrap().frozen.counts(),[0,4,10]);assert!(!s.arena_base);
        assert_eq!(i.controller.registry().claim(account(&s.identity.as_ref().unwrap().account_id).unwrap()),Some(room::Claim::Battle(event.battle)));
    }
    assert!(!ready_to_start(&i.table,&i.world,&event.awaiting_handoff,now+Duration::from_secs(4)).unwrap());
    for s in &mut i.table.sessions{let mut payloads=Vec::new();while let Some((_,_,bytes))=s.tx.due(now,s.rx).unwrap(){payloads.push(crate::transport091::parse_interactive(&bytes).unwrap().body);}
        if s.id==103{assert_eq!(payloads.first(),Some(&room_wire::plain_response(225,room_wire::CommandResult::Success,"").unwrap()));}
        assert!(!payloads.iter().any(|p|p.starts_with(&[0x13,0x3b])||p==&room_wire::left()));
        let ack=s.tx.len()as u32;s.tx.acknowledge(&crate::transport091::parse(&crate::transport091::ack(ack)).unwrap()).unwrap();}
    i.table.sessions.push(Session::new(999,[9;16],"127.0.0.1:41999".parse().unwrap(),now));
    assert!(ready_to_start(&i.table,&i.world,&event.awaiting_handoff,now+Duration::from_secs(4)).unwrap());
    assert!(ready_to_start(&i.table,&i.world,&[103,104],now+Duration::from_secs(4)).is_err());
}
#[test]fn p10b_launch_late_missing_source_channel_membership_Fresh_or_abort_rolls_back_every_state(){
    let now=Instant::now();
    for poison in 0..12{let mut i=input(now);match poison{
        0=>{i.table.sessions.pop();},1=>i.table.sessions[1].shared.as_mut().unwrap().return_generation+=1,
        2=>i.table.sessions[1].shared.as_mut().unwrap().profile13.as_mut().unwrap().in_flight=false,
        3=>{let p=i.table.sessions[1].identity.as_ref().unwrap();let(_,other)=fixture(&p.account_id,p.database_id,i.table.sessions[1].ammo_service.as_ref().unwrap().revision(),true);i.table.sessions[1].hangar=Some(other);},
        4=>{i.origins.remove(&i.calls[1].caller.account);},5=>{i.held.pop();},
        6=>i.held[1].binding.revision+=1,
        7=>{i.controller.apply(i.calls[0],native(226,401,0,0),&i.facts,0).unwrap();},
        8=>{i.saga.abort();},
        9=>{let mut duplicate=i.table.sessions[0].clone();duplicate.id=999;i.table.sessions.push(duplicate);},
        10=>{match &mut i.held[1].receipt{saga::Reservation::V2(r)=>r.reservation_id.push('x'),_=>panic!("V2 fixture")};},
        11=>{let mut busy=World::new_for_roster(i.world.id,now,MapId::Prohorovka,6).unwrap();busy.attach(model::Identity{account:"authored-preexisting".into(),database:99,name:"BusyWorld".into()},999).unwrap();i.world=busy;},_=>unreachable!()}
        let before=unchanged(&i);assert!(stage(&i,now).is_err(),"poison {poison}");assert_eq!(unchanged(&i),before);
    }
}
#[test]fn p10b_launch_final411_outbox_failure_cannot_commit_one_actor_or_clear_one_guard(){
    let now=Instant::now();let mut i=input(now);for _ in 0..128{i.table.sessions[0].outbox.push_back(vec![0x13,0x3b]);}
    let before=unchanged(&i);assert!(stage(&i,now).is_err());assert_eq!(unchanged(&i),before);
}
#[test]fn p10b_launch_bench_gets_Left_only_and_does_not_block_selected_start_on_its_unacked_bytes(){
    let now=Instant::now();let mut i=input_mode(now,true);let prepared=stage(&i,now).unwrap();let mut runtime=None;
    let event=prepared.commit(&mut i.table,&mut i.controller,&mut i.world,&mut runtime);
    assert_eq!(event.awaiting_handoff,vec![104,103]);assert_eq!(i.world.actors.len(),2);assert_eq!(i.table.sessions.len(),3);
    let spectator=i.table.sessions.iter_mut().find(|s|s.id==105).unwrap();let(_,_,bytes)=spectator.tx.due(now,spectator.rx).unwrap().unwrap();
    assert_eq!(crate::transport091::parse_interactive(&bytes).unwrap().body,room_wire::left());assert!(!spectator.arena_base);
    assert!(i.controller.registry().claim(account("55555555-5555-4555-8555-555555555555").unwrap()).is_none());
    for s in i.table.sessions.iter_mut().filter(|s|event.awaiting_handoff.contains(&s.id)){
        while s.tx.due(now,s.rx).unwrap().is_some(){}let n=s.tx.len()as u32;s.tx.acknowledge(&crate::transport091::parse(&crate::transport091::ack(n)).unwrap()).unwrap();
    }
    assert!(ready_to_start(&i.table,&i.world,&event.awaiting_handoff,now+Duration::from_secs(4)).unwrap());
    assert_eq!(i.table.sessions.iter().find(|s|s.id==105).unwrap().tx.len(),1);
}
#[test]fn p10b_launch_late_bench_recreated_channel_rejects_before_combat_claim_or_native_success(){
    let now=Instant::now();let mut i=input_mode(now,true);i.table.sessions.iter_mut().find(|s|s.id==105).unwrap().shared.as_mut().unwrap().return_generation+=1;
    let before=unchanged(&i);assert!(stage(&i,now).is_err());assert_eq!(unchanged(&i),before);
}
#[test]fn p10b_launch_handoff_N2_to6_explicitly_rejects_missing_sessions_without_forged_owned_refs(){
    // AUTHORED scheduler/World metadata ONLY. No additional owned accounts or
    // reservations are invented. Actual two-owned launch is the separate test.
    let now=Instant::now();
    for count in 2..=6{let mut world=World::new_for_roster(77,now,MapId::Prohorovka,count).unwrap();world.enable_lifecycle(super::super::super::lifecycle::Rules::prohorovka()).unwrap();
        world.set_team_plan(super::super::super::p10b_team_plan::TeamPlan::new(&(0..count).map(|n|n as u8%2+1).collect::<Vec<_>>()).unwrap()).unwrap();
        let mut ids=Vec::new();let mut table=Table{capacity:6,..Table::default()};
        for slot in 0..count{let id=slot as u32+1;world.attach(model::Identity{account:format!("authored-scheduler-{id}"),database:id as i32,name:format!("Actor{id}")},id).unwrap();ids.push(id);}
        assert!(ready_to_start(&table,&world,&ids,now).is_err());
        // No matching native Sessions means explicit failure for every N.
        table.sessions.clear();assert!(ready_to_start(&table,&world,&ids[..ids.len()-1],now).is_err());
    }
}
