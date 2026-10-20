//! Authored, linked-serializer IPC6 coordinator tests. No worker process/native input.
use super::*;
use crate::map_drive_worker091::{self as drive,controlled_ipc,Scene};
use serde_json::{json,Value};

struct Fixture {world:World,runtime:IntegratedRuntime,peers:[controlled_ipc::Peer;2],template:Value}
fn fixture(now:Instant,name:&str)->Fixture {
    let(template,spec,catalog,profile)=controlled_ipc::angular_fixture(name);
    let kind=match profile{ram_proof::Profile::Ms1=>VehicleKind::Ms1,ram_proof::Profile::Is7=>VehicleKind::Is7,
        ram_proof::Profile::T26|ram_proof::Profile::T34|ram_proof::Profile::T3485|ram_proof::Profile::WtE100128|ram_proof::Profile::Fv215b183=>panic!("legacy two-profile fixture; curated profiles have separate actual gates")};
    let mut world=World::new_for_vehicle(7,now,spec.map_id(),kind).unwrap();
    for(i,name)in["one","two"].into_iter().enumerate(){world.attach(model::Identity{account:name.into(),name:name.into(),database:i as i32+1},i as u32+1).unwrap();}
    world.actors.iter_mut().for_each(|a|a.ready=true);world.started=Some(now);
    world.impact.bind_fragiles(catalog.clone()).unwrap();world.fragiles=Some(super::super::fragiles::State::new(catalog));
    let map=drive::MapSpec{asset:spec.map_id().asset().into(),arena_type_id:spec.map_id().arena_type_id(),config:"component".into(),config_sha256:"c".repeat(64),
        bounds:[-500.,-500.,500.,500.],spawn:[0.;3],spawn_yaw:0.,mass_kg:profile.mass()};
    let mut runtime=IntegratedRuntime::new(controlled_ipc::angular_pool(map.clone(),profile));
    runtime.map_id=spec.map_id();runtime.catalog=Some(spec.clone());runtime.started=true;
    let peers=std::array::from_fn(|slot|{let(worker,peer)=controlled_ipc::angular_ready(map.clone(),slot as u32+2,
        spec.clone(),Scene::new(&spec,&[]).unwrap(),now,profile);
        runtime.workers[slot]=Some(worker);runtime.worker_sessions[slot]=world.actors[slot].session;runtime.anchored[slot]=true;
        runtime.poses[slot]=Some((world.actors[slot].position,[0.;3],0.));peer});
    Fixture{world,runtime,peers,template}
}
impl Fixture {
    fn dispatch(&mut self,now:Instant){self.runtime.step(&mut self.world,now).unwrap();for p in &self.peers{assert_eq!(p.request()["seq"],1);}}
    fn frame(&self,slot:usize,paid:bool)->Value {
        let mut v=self.template.clone();v["generation"]=(slot+2).into();
        if !paid{v["event"]="state".into();for k in["object_contacts","fractures","motion_witnesses"]{v["state"][k]=json!([]);}}
        v
    }
    fn ack(&self,slot:usize,request:&Value,now:Instant){let mut v=request.clone();v.as_object_mut().unwrap().remove("op");v["event"]="scene_synced".into();
        v["tick"]=(180+request["advance_seq"].as_u64().unwrap()*6).into();self.peers[slot].reply(now,&v);}
}
#[test]fn angular_paired_proof_waits_for_both_acks_and_does_not_repeat(){
    for first in 0..2 {let now=Instant::now();let mut f=fixture(now,"mixed-False");f.dispatch(now);
        f.peers[first].reply(now+Duration::from_millis(1),&f.frame(first,true));
        f.runtime.step(&mut f.world,now+Duration::from_millis(2)).unwrap();assert_eq!(f.world.scene_version(),0);
        f.peers[1-first].reply(now+Duration::from_millis(3),&f.frame(1-first,false));
        f.runtime.step(&mut f.world,now+Duration::from_millis(4)).unwrap();assert!(f.runtime.blocked());
        let requests=[f.peers[0].request(),f.peers[1].request()];assert_eq!(requests[0]["removed_object_ids"],json!([1,3,18]));
        f.ack(first,&requests[first],now+Duration::from_millis(5));f.runtime.step(&mut f.world,now+Duration::from_millis(6)).unwrap();assert_eq!(f.world.scene_version(),0);
        f.ack(1-first,&requests[1-first],now+Duration::from_millis(7));f.runtime.step(&mut f.world,now+Duration::from_millis(8)).unwrap();
        assert_eq!(f.world.scene_version(),3);assert!(!f.runtime.blocked());
        f.runtime.step(&mut f.world,now+Duration::from_millis(9)).unwrap();assert_eq!(f.world.fragiles.as_ref().unwrap().vehicle_events.len(),3);
    }
}
#[test]fn angular_unpaid_hull_and_wheel_rows_remain_observed_but_cannot_destroy(){
    for wheel in [false,true] {let now=Instant::now();let mut f=fixture(now,"ms1-angular-example");f.dispatch(now);
        let mut v=f.frame(0,true);assert!(v["state"]["fractures"].as_array().unwrap().is_empty());
        if v["state"]["object_contacts"].as_array().unwrap().is_empty(){v["state"]["object_contacts"]=json!([{"object_id":1,"kind":"hull","substep":1,"point":[0,0,0],"normal":[1,0,0],"velocity":[0,0,0]}]);}
        if wheel{v["state"]["object_contacts"][0]["kind"]="wheel".into();}
        f.peers[0].reply(now+Duration::from_millis(1),&v);f.runtime.step(&mut f.world,now+Duration::from_millis(2)).unwrap();
        let batch=f.runtime.contact_batches[0].as_ref().unwrap();assert!(batch.observed_contacts>0);assert!(batch.contacts.is_empty());
        f.peers[1].reply(now+Duration::from_millis(3),&f.frame(1,false));f.runtime.step(&mut f.world,now+Duration::from_millis(4)).unwrap();
        assert_eq!(f.world.scene_version(),0);assert!(!f.runtime.blocked());
    }
}
#[test]fn angular_mixed_paid_unpaid_rows_preserve_complete_physical_order(){
    let now=Instant::now();let mut f=fixture(now,"mixed-False");f.dispatch(now);
    let mut v=f.frame(0,true);v["state"]["object_contacts"].as_array_mut().unwrap().push(json!({"object_id":20,"kind":"wheel","substep":6,"point":[0,0,0],"normal":[1,0,0],"velocity":[0,0,0]}));
    f.peers[0].reply(now+Duration::from_millis(1),&v);f.runtime.step(&mut f.world,now+Duration::from_millis(2)).unwrap();
    let batch=f.runtime.contact_batches[0].as_ref().unwrap();assert_eq!(batch.observed_contacts,4);assert_eq!(batch.contacts.len(),3);
    assert_eq!(batch.contacts.iter().map(|c|c.proof.as_ref().unwrap().index).collect::<Vec<_>>(),vec![0,1,2]);
    f.peers[1].reply(now+Duration::from_millis(3),&f.frame(1,false));f.runtime.step(&mut f.world,now+Duration::from_millis(4)).unwrap();
    assert_eq!(f.runtime.staged.as_ref().unwrap().scene_version(),3);
}
#[test]fn angular_stale_scene_ack_cannot_publish_prepared_frame(){
    let now=Instant::now();let mut f=fixture(now,"is7-angular-example");f.dispatch(now);
    for slot in 0..2{f.peers[slot].reply(now+Duration::from_millis(1),&f.frame(slot,slot==0));}
    f.runtime.step(&mut f.world,now+Duration::from_millis(2)).unwrap();
    let mut request=f.peers[0].request();let _=f.peers[1].request();request["generation"]=99.into();
    f.ack(0,&request,now+Duration::from_millis(3));assert!(f.runtime.step(&mut f.world,now+Duration::from_millis(4)).is_err());assert_eq!(f.world.scene_version(),0);
}

#[test]fn angular_unpaid_observations_still_share_the_aggregate_32_contact_cap(){
    let now=Instant::now();let mut f=fixture(now,"ms1-angular-example");f.dispatch(now);
    for slot in 0..2 {
        let mut v=f.frame(slot,false);let catalog=f.world.fragiles.as_ref().unwrap();
        v["state"]["object_contacts"]=json!(catalog.catalog.objects.iter().take(17).map(|o|json!({"object_id":o.object_id,
            "kind":"wheel","substep":1,"point":[0,0,0],"normal":[1,0,0],"velocity":[0,0,0]})).collect::<Vec<_>>());
        f.peers[slot].reply(now+Duration::from_millis(1),&v);
    }
    assert!(f.runtime.step(&mut f.world,now+Duration::from_millis(2)).is_err());assert_eq!(f.world.scene_version(),0);
}
