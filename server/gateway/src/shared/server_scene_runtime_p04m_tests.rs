//! Five real source resources and the actual root C# producer cross the normal
//! World/Trace/scalar-proof/staged-ACK boundary. Explicit laboratory attachment
//! does not fabricate owned inventory or override native admission=false.
use super::*;
use sha2::{Digest,Sha256};
use std::{path::PathBuf,time::{SystemTime,UNIX_EPOCH}};

const TEMPLATE:&str="evidence/20261016-p04m-runtime01/domain-fixture01/battle-profiles-five.json";
const TEMPLATE_SHA:&str="b7f272aace7a7746643bf00f0a49d343931d139477765ab30fcacbbf24c668e4";
const ROOT_DLL_SHA:&str="9da077b8ad07b7b605963ce49426bb8e8033821815aa89a406c61dbd87e7bb03";
const KINDS:[VehicleKind;6]=[VehicleKind::T26,VehicleKind::T34,VehicleKind::T3485,VehicleKind::Ms1,VehicleKind::Is7,VehicleKind::T26];

fn resources()->Vec<super::super::super::profile13_templates::Resources> {
    let root=PathBuf::from(std::env::var_os("WOT091_ROOT").unwrap_or_else(||"D:/WoT_9.1_Server".into())).join("local");
    let path=root.join(TEMPLATE);assert_eq!(format!("{:x}",Sha256::digest(fs::read(&path).unwrap())),TEMPLATE_SHA);
    let rows=super::super::super::profile13_templates::load(&root,&path).unwrap();
    assert_eq!(rows.len(),5);assert_eq!(rows.iter().map(|r|r.kind).collect::<Vec<_>>(),VehicleKind::ALL);
    let shared=rows[0].shared.as_ref().unwrap();
    assert_eq!(format!("{:x}",Sha256::digest(fs::read(shared.artifacts.executable.with_extension("dll")).unwrap())),ROOT_DLL_SHA);
    for row in &rows {assert_eq!(row.pool.vehicle_kind(),row.kind);assert_eq!(row.geometry.vehicle_kind(),row.kind);}
    rows
}
#[test]
fn p04m_explicit_qualification_template_selects_temporary_kind_without_opening_owned_admission() {
    let rows=resources();let now=Instant::now();
    for kind in VehicleKind::ALL {
        let template=BattleTemplate::from_shared_mode(&rows,2,9710+kind.index()as u64,now,Some(kind)).unwrap();
        let mut world=template.world.fresh_battle(9800+kind.index()as u64,now).unwrap();
        assert!(world.mixed_profiles());assert!(world.lifecycle.is_none());assert_eq!(world.vehicle_kind(),kind);
        for slot in 0..2 {world.attach(model::Identity{account:format!("qualify-{slot}"),database:slot+1,name:format!("qualify-{slot}")},slot as u32+1).unwrap();}
        world.start(now).unwrap();
        for(slot,actor)in world.actors.iter().enumerate(){assert_eq!(actor.vehicle_kind(),kind);assert_eq!(actor.fire.ammo(),kind.initial_ammo());
            assert_eq!(actor.health,kind.max_health());assert_eq!(super::super::super::wire::create_vehicle(&world,slot).unwrap()[0],9);
            let binding=super::super::super::wire::binding(&world,slot,now).unwrap();assert!(binding.windows(4).any(|b|b==kind.shell_compact_id().to_le_bytes()));}
        if kind.index()>=2 {assert!(!kind.battle_admission());}
    }
    assert!(BattleTemplate::from_shared_mode(&rows[..2],2,9900,now,Some(VehicleKind::T26)).is_err());
    let owned=BattleTemplate::from_shared(&rows,2,9901,now).unwrap();assert!(owned.world.lifecycle.is_some());
    assert_eq!(owned.world.vehicle_kind(),VehicleKind::Ms1);
}
fn spin(runtime:&mut BatchRuntime,world:&mut World,at:Instant,done:impl Fn(&BatchRuntime,&World)->bool) {
    let deadline=Instant::now()+Duration::from_secs(120);
    loop {runtime.step(world,at).unwrap();if done(runtime,world){return;}
        assert!(Instant::now()<deadline,"P04M actual World/scene deadline");std::thread::sleep(Duration::from_millis(1));}
}

#[test]
fn p04m_actual_five_profile_world_keeps_typed_scalar_sources_and_commits_one_scene_ack() {
    let rows=resources();let shared=rows[0].shared.clone().unwrap();
    let now=Instant::now();let template=BattleTemplate::from_shared(&rows,6,9705,now).unwrap();
    let mut world=template.world.clone();
    // Isolate the physical/domain boundary, as in the existing P05C actual
    // gate. P08C lifecycle/native outcomes have their own acceptance matrix.
    world.lifecycle=None;
    let identities=(0..6).map(|slot|model::Identity{
        account:format!("{:08x}-1234-4234-8234-123456789abc",900+slot),database:900+slot,
        name:format!("p04m-physics-{slot}")}).collect::<Vec<_>>();
    for (slot,kind) in KINDS.into_iter().enumerate() {
        if kind.index()>=2 {assert!(!kind.battle_admission());}
        assert_eq!(model::tests::attach_physics_profile(&mut world,kind,identities[slot].clone(),3000+slot as u32).unwrap(),slot);
        assert_eq!(world.actors[slot].vehicle_kind(),kind);
        assert_eq!(world.actors[slot].fire.ammo(),kind.initial_ammo());
    }
    let ammo=world.actors.iter().map(|a|a.fire.ammo()).collect::<Vec<_>>();
    world.start(now).unwrap();let mut runtime=BatchRuntime::new(shared.clone(),rows[0].catalog.1.clone());
    runtime.start(&mut world,now).unwrap();
    spin(&mut runtime,&mut world,Instant::now(),|r,_|r.ready_for_native());
    let pid=runtime.runtime.as_ref().unwrap().process_id();
    let origins=world.actors.iter().map(|a|a.position).collect::<Vec<_>>();
    for slot in 0..6 {world.set_ready(slot,3000+slot as u32).unwrap();world.actors[slot].input=model::Input{throttle:1,steer:0,speed_percent:100};}
    let base=Instant::now();let mut staged_acks=0;let mut departed=false;let mut rejoined=false;
    let mut staged_snapshots=Vec::new();
    for frame in 1..=120 {
        if frame==80 {
            assert!(rejoined,"actual prepared barrier and rejoin must happen before parked-body phase");
            world.detach(9305).unwrap();
            // A test-specified dead new-profile body must remain physical in
            // this same producer. This does not claim a tested AP death path.
            world.actors[2].health=0;world.actors[2].input=model::Input::STOP;
        }
        let at=base+Duration::from_millis(frame*100);let before_tick=world.tick;let before_scene=world.scene_version();
        let deadline=Instant::now()+Duration::from_secs(120);let mut saw_staged=false;
        loop {
            runtime.step(&mut world,at).unwrap();
            if let Some(staged)=&runtime.staged {
                assert_eq!(world.scene_version(),before_scene,"physical prepare cannot publish its candidate early");
                assert!(staged.scene_version()>before_scene);assert!(staged.tick>before_tick);
                assert!(!runtime.runtime.as_ref().unwrap().prepared_ids().is_empty());
                if !saw_staged {staged_acks+=1;staged_snapshots.push(runtime.failure_snapshot());saw_staged=true;}
                if !departed {world.detach(3005).unwrap();departed=true;}
            }
            if world.tick>before_tick&&!runtime.blocked(){break;}
            assert!(Instant::now()<deadline,"actual new-profile World commit deadline");std::thread::sleep(Duration::from_millis(1));
        }
        if departed&&!rejoined {
            assert_eq!(world.actors[5].session,None);let position=world.actors[5].position;
            // Reattach an existing laboratory body/identity, preserving kind,
            // ammunition and position. No new actor or owned loadout is made.
            assert_eq!(world.attach(identities[5].clone(),9305).unwrap(),5);
            assert_eq!(world.actors[5].position,position);assert_eq!(world.actors[5].vehicle_kind(),VehicleKind::T26);
            world.set_ready(5,9305).unwrap();world.actors[5].input=model::Input{throttle:1,steer:0,speed_percent:100};rejoined=true;
        }
        assert_eq!(runtime.runtime.as_ref().unwrap().process_id(),pid);assert_eq!(world.actors.len(),6);
        assert_eq!(world.actors.iter().map(|a|a.vehicle_kind()).collect::<Vec<_>>(),KINDS);
        let state=world.fragiles.as_ref().unwrap();
        assert_eq!(runtime.runtime.as_ref().unwrap().scene().ids,state.removed_ids());
        assert_eq!(state.vehicle_events.len(),world.scene_version()as usize);
    }
    assert!(departed&&rejoined&&staged_acks>0);assert!(world.scene_version()>0);
    assert!(world.actors[0].position[2]>origins[0][2]+5.);
    assert_eq!(world.actors[5].session,None);assert_eq!(world.actors[5].input,model::Input::STOP);
    assert_eq!(world.actors[2].health,0);assert_eq!(world.actors[2].input,model::Input::STOP);
    assert_eq!(world.actors.iter().map(|a|a.fire.ammo()).collect::<Vec<_>>(),ammo);
    assert!(world.shots.is_empty()&&world.impacts.is_empty());
    let state=world.fragiles.as_ref().unwrap();let mut new_receipts=0;
    for event in &state.vehicle_events {
        let proof=event.proof.as_ref().unwrap();let kind=KINDS[event.shooter];
        assert_eq!(proof.frame.proof.profile,ram_proof::Profile::for_vehicle(kind));
        assert_eq!(proof.frame.context.slot,event.shooter);assert_eq!(proof.frame.context.session,3000+event.shooter as u32);
        assert_eq!(proof.receipt().unwrap().object_id,event.object_id);
        if kind.index()>=2 {new_receipts+=1;}
    }
    assert!(new_receipts>0,"a genuinely new profile must commit a typed scalar receipt into the domain");
    assert!(world.impact.events().len()>=state.vehicle_events.len());
    for kind in VehicleKind::ALL.into_iter().skip(2){assert!(!kind.battle_admission());}
    let stamp=SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_nanos();
    let out=shared.root.join(format!("evidence/20261016-p04m-runtime01/domain-world-{}-{stamp}",std::process::id()));
    fs::create_dir(&out).unwrap();
    let result=serde_json::json!({"status":"PASS_ACTUAL_WORLD_SCALAR_TRACE_SCENE_ACK","kinds":KINDS.map(VehicleKind::label),
        "single_worker_pid":pid,"batches":120,"staged_scene_acks":staged_acks,"committed_scene":world.scene_version(),
        "typed_vehicle_events":state.vehicle_events.len(),"new_profile_typed_receipts":new_receipts,"trace_events":world.impact.events().len(),
        "prepared_window_new_profile_disconnect":departed,"same_body_new_profile_rejoin":rejoined,
        "root_worker_dll_sha256":ROOT_DLL_SHA,"template_sha256":TEMPLATE_SHA,"battle_admission":false,
        "world":world.failure_snapshot(),"native_owner":"NOT_RUN","owned_inventory":"NOT_RUN"});
    fs::write(out.join("result.json"),serde_json::to_vec_pretty(&result).unwrap()).unwrap();
    fs::write(out.join("staged-ack-snapshots.json"),serde_json::to_vec_pretty(&staged_snapshots).unwrap()).unwrap();
    println!("P04M_DOMAIN_ACCEPTED actors=6 all_kinds=5 process_id={pid} batches=120 scene={} new_typed_receipts={new_receipts} acks={staged_acks} evidence={}",world.scene_version(),out.display());
    runtime.runtime.take().unwrap().shutdown().unwrap();
}
