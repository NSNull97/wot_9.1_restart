//! Linked producer fixtures test JSON, parser, scalar proof and domain/replay.
//! Their envelopes and contact geometry are authored component inputs, not
//! evidence of actual workers, map contacts or native acceptance.
use super::*;
use crate::gateway091::shared::{fragiles,model,terrain,vehicle_profile::VehicleKind};

fn evidence()->PathBuf {
    std::env::var_os("WOT_ANGULAR_EVIDENCE").map(PathBuf::from).unwrap_or_else(||
        Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/evidence/20261013-p05b-tracked-handling-01"))
}
fn fixture(name:&str)->Value {
    let bytes=fs::read(evidence().join("night-angular-worker-b01/component02/wire.json")).unwrap();
    assert_eq!(format!("{:x}",Sha256::digest(&bytes)),"1b990777cf2fff45852bf304e714a246e1d04280daa1f4bf76f938597884e5e4");
    let v:Value=serde_json::from_slice(&bytes).unwrap();let rows=v["fixtures"].as_array().unwrap();assert_eq!(rows.len(),8);
    rows.iter().find(|r|r["name"]==name).unwrap()["frame"].clone()
}
fn catalogs()->(CatalogSpec,Arc<fragiles::Catalog>){
    let e=evidence();let local=e.parent().unwrap().parent().unwrap();
    let worker=CatalogSpec::load(local,&e.join("night-angular-export01/catalog/physics-removals.json"),
        "41c0d9ccfd5b608a07e80a4eb68a3b6ed70bacffdd1444bb58c3f2ebb179bea9").unwrap();
    let domain=fragiles::Catalog::load(local,&e.join("night-angular-export01/catalog/manifest.json"),
        "1dca4febb0bc4921263682f82b927e26c33248c5b837a885f075245adf948f99").unwrap();
    (worker,Arc::new(domain))
}
fn map(profile:Profile)->MapSpec {
    MapSpec{asset:"03_campania".into(),arena_type_id:3,config:"component-config".into(),config_sha256:"c".repeat(64),
        bounds:[-500.,-500.,500.,500.],spawn:[0.;3],spawn_yaw:0.,mass_kg:profile.mass()}
}
pub(in super::super) fn bound(name:&str)->(Value,CatalogSpec,Arc<fragiles::Catalog>,Profile){
    let(mut value,(catalog,domain))=(fixture(name),catalogs());
    let profile=if name.starts_with("ms1"){Profile::Ms1}else{Profile::Is7};
    // One normal-response fixture row maps to a real normal-response catalog
    // member. Geometry remains explicitly authored, no physical-hit claim.
    for key in ["object_contacts","fractures"] {for row in value["state"][key].as_array_mut().unwrap(){
        if row["object_id"]==2 {row["object_id"]=18.into();}}}
    value["state"]["object_contacts"].as_array_mut().unwrap().sort_by_key(|r|r["object_id"].as_u64().unwrap());
    let scene=Scene::new(&catalog,&[]).unwrap();value["map"]=catalog.map_id().asset().into();
    value["catalog_sha256"]=catalog.sha256().into();value["scene_sha256"]=scene.hash().into();
    value["generation"]=1.into();(value,catalog,domain,profile)
}
fn decode(value:&Value,catalog:&CatalogSpec,profile:Profile)->io::Result<State>{
    let mut map=map(profile);map.asset=catalog.map_id().asset().into();map.arena_type_id=catalog.map_id().arena_type_id();
    let p=vector(&value["state"]["position"],-2000.,2000.)?;
    catalog::response_with_profile(&serde_json::to_vec(value).unwrap(),&map,catalog,1,
        uint(&value["seq"])? as u32,Some(p),&Scene::new(catalog,&[]).unwrap(),Some(profile))
}

#[test]fn angular_linked_csharp_wire_is_decoded_by_full_production_parser(){
    let mut branches=BTreeSet::new();let mut rows=0;
    for name in ["ms1-ready","ms1-angular-example","is7-ready","is7-angular-example","mixed-False","mixed-True","nonclosing-post","quantized-post"] {
        let(v,c,_,p)=bound(name);let state=decode(&v,&c,p).unwrap_or_else(|e|panic!("{name}: {e}"));
        let proof=state.angular_proof.unwrap();assert_eq!(proof.profile,p);
        for r in &proof.receipts {if let Some(branch)=r.solver_branch{branches.insert(format!("{branch:?}"));}rows+=1;}
        assert_eq!(state.fractures.len(),proof.receipts.len());
    }
    assert_eq!(branches.len(),3);assert_eq!(rows,9);
}

#[test]fn angular_catalog_versions_fields_and_old_policies_remain_closed(){
    let(c,d)=catalogs();assert_eq!((c.version(),c.ipc_version(),d.version),(8,6,7));
    assert_eq!(c.entries().len(),1038);assert_eq!(c.entries().iter().filter(|e|e.ram_response()==Some(proof::FALLBACK)).count(),403);
    for o in &d.objects {let e=c.entries().iter().find(|e|e.object_id()==o.object_id).unwrap();
        assert_eq!(e.ram_response(),d.ram_response(o));assert_eq!(e.ram_energy_j(),8000);}
    let bytes=fs::read(evidence().join("night-angular-export01/catalog/physics-removals.json")).unwrap();
    let good:Value=serde_json::from_slice(&bytes).unwrap();
    for version in [2,3,4,5,6,7,9] {let mut v=good.clone();v["version"]=version.into();assert!(catalog::CatalogSpec::validate(&v).is_err());}
}

#[test]fn angular_closed_fields_body_identity_and_signed_zero_are_not_tolerant(){
    let(v,c,_,p)=bound("is7-angular-example");
    for key in ["body_binding","motion_witnesses","fractures"] {let mut bad=v.clone();bad["state"].as_object_mut().unwrap().remove(key);assert!(decode(&bad,&c,p).is_err());}
    for key in ["inverse_mass","principal_inverse_diagonal","inertia_rotation_xyzw"] {
        let mut bad=v.clone();bad["state"]["body_binding"][key]=Value::Null;assert!(decode(&bad,&c,p).is_err());
    }
    let mut bad=v.clone();bad["state"]["body_binding"]["inertia_rotation_xyzw"][2]=serde_json::json!(-0.0);
    assert!(decode(&bad,&c,p).is_err());
    let mut bad=v.clone();bad["state"]["body_binding"]["inverse_mass"]=serde_json::json!(Profile::Ms1.binding().inverse_mass);
    assert!(decode(&bad,&c,p).is_err());
    for target in ["fractures","motion_witnesses"] {let mut bad=v.clone();bad["state"][target][0]["unexpected"]=true.into();assert!(decode(&bad,&c,p).is_err());}
    assert!(decode(&v,&c,Profile::Ms1).is_err());
    let raw=serde_json::to_string(&v).unwrap().replacen("\"version\":6","\"version\":6,\"version\":6",1);
    assert!(json(raw.as_bytes(),MAX_ANGULAR_IPC_LINE).is_err());
    assert_eq!(number(&json(b"-0",64).unwrap(),-1.,1.).unwrap().to_bits(),(-0f32).to_bits());
}

#[test]fn angular_chain_refill_order_subset_and_mode_substitution_fail(){
    let(v,c,_,p)=bound("mixed-False");assert!(decode(&v,&c,p).is_ok());
    for key in ["budget_after","solver_after"] {
        let mut bad=v.clone();bad["state"]["fractures"][0][key]=v["state"]["fractures"][1][key].clone();assert!(decode(&bad,&c,p).is_err());
    }
    let mut bad=v.clone();bad["state"]["fractures"].as_array_mut().unwrap().remove(0);
    for (i,r) in bad["state"]["fractures"].as_array_mut().unwrap().iter_mut().enumerate(){r["order"]=(i+1).into();}
    assert!(decode(&bad,&c,p).is_err());
    let mut bad=v.clone();bad["state"]["fractures"].as_array_mut().unwrap().swap(0,1);assert!(decode(&bad,&c,p).is_err());
    for key in ["mode","solver_branch","energy_j"] {let mut bad=v.clone();bad["state"]["fractures"][1][key]=Value::Null;assert!(decode(&bad,&c,p).is_err());}
    let mut linear_first=v.clone();linear_first["state"]["fractures"][1]["legacy_linear_candidate"]["normal"]=serde_json::json!([1.,0.,0.]);assert!(decode(&linear_first,&c,p).is_err());
    let mut bad=v;let a=number(&bad["state"]["fractures"][1]["budget_after"]["angular_velocity"][1],-20.,20.).unwrap();
    bad["state"]["fractures"][1]["budget_after"]["angular_velocity"][1]=serde_json::json!(f32::from_bits(a.to_bits()+1));assert!(decode(&bad,&c,p).is_err());
}

#[test]fn angular_raw_post_inertia_contact_identity_and_lever_are_checked(){
    let(v,c,_,p)=bound("is7-angular-example");
    for stage in ["pre","post_solver"] {for change in 0..4 {
        let mut bad=v.clone();let w=&mut bad["state"]["motion_witnesses"][0][stage];
        match change {0=>w["inverse_inertia_row_major"][0]=(-0.01).into(),1=>w["rotation_xyzw"] = serde_json::json!([0,0,0,0]),
            2=>w["com"][0]=2000.into(),_=>w["angular_velocity"][0]=21.into()}
        assert!(decode(&bad,&c,p).is_err(),"{stage} {change}");
    }}
    for change in 0..4 {let mut bad=v.clone();let contact=&mut bad["state"]["object_contacts"][0];
        match change {0=>contact["kind"]="wheel".into(),1=>contact["substep"]=2.into(),2=>contact["point"][0]=0.into(),_=>contact["velocity"][0]=20.into()}
        assert!(decode(&bad,&c,p).is_err());}
    let mut bad=v;bad["state"]["fractures"][0]["legacy_linear_candidate"]["point"][0]=2000.into();assert!(decode(&bad,&c,p).is_err());
}

#[test]fn angular_final_substep_six_binds_exact_motion_but_earlier_receipts_allow_native_steps(){
    let(v,c,_,p)=bound("is7-angular-example");let good=decode(&v,&c,p).unwrap();let proof=good.angular_proof.unwrap();
    let last=proof.receipts.last().unwrap();
    let mut earlier=v.clone();for key in ["object_contacts","fractures","motion_witnesses"] {earlier["state"][key][0]["substep"]=1.into();}
    earlier["state"]["linear_velocity"]=serde_json::json!([1.,2.,3.]);assert!(decode(&earlier,&c,p).is_ok());
    let mut final_step=v;for key in ["object_contacts","fractures","motion_witnesses"] {final_step["state"][key][0]["substep"]=6.into();}
    final_step["state"]["linear_velocity"]=serde_json::json!(last.solver_after.v);
    final_step["state"]["angular_velocity"]=serde_json::json!(last.solver_after.w);
    final_step["state"]["rspeed"]=serde_json::json!(last.solver_after.w[1]);assert!(decode(&final_step,&c,p).is_ok());
    for key in ["linear_velocity","angular_velocity"] {let mut bad=final_step.clone();bad["state"][key][0]=9.into();assert!(decode(&bad,&c,p).is_err());}
    final_step["state"]["rspeed"]=8.into();assert!(decode(&final_step,&c,p).is_err());
}

#[test]fn angular_reader_and_ack_use_catalog_selected_exact_budgets(){
    for (limit,good,bad_len) in [(MAX_IPC_LINE,32768,32769),(MAX_ANGULAR_IPC_LINE,65536,65537)] {
        let mut raw=vec![b'x';good];raw.push(b'\n');assert_eq!(line_with_limit(&mut raw.as_slice(),limit).unwrap().len(),good);
        let mut raw=vec![b'x';bad_len];raw.push(b'\n');assert!(line_with_limit(&mut raw.as_slice(),limit).is_err());
    }
    let c=catalog::tests::angular_spec(2048);
    let scene=Scene::new(&c,&(1..=2048).collect::<Vec<_>>()).unwrap();let mut m=map(Profile::Is7);m.asset=c.map_id().asset().into();m.arena_type_id=c.map_id().arena_type_id();
    let ack=serde_json::json!({"version":6,"event":"scene_synced","advance_seq":1,"tick":186,"generation":1,
        "config_sha256":m.config_sha256,"catalog_sha256":c.sha256(),"scene_version":2048,"removed_object_ids":scene.ids(),"scene_sha256":scene.hash(),"contacts":true});
    assert!(catalog::ack(&serde_json::to_vec(&ack).unwrap(),&m,&c,1,1,&scene).is_ok());
    let mut extra=ack.clone();extra["extra"]=serde_json::json!([vec![0;2048],vec![0;2048]]);
    assert!(json_with_node_limit::<2048>(&serde_json::to_vec(&extra).unwrap(),65536,4096).is_err());
    assert!(catalog::ack(&serde_json::to_vec(&extra).unwrap(),&m,&c,1,1,&scene).is_err());
    for key in ["generation","advance_seq","scene_version"] {let mut bad=ack.clone();bad[key]=0.into();assert!(catalog::ack(&serde_json::to_vec(&bad).unwrap(),&m,&c,1,1,&scene).is_err());}
}

fn world_inputs(name:&str)->(model::World,Vec<model::VehicleContactInput>){
    let(v,c,d,p)=bound(name);let state=decode(&v,&c,p).unwrap();let proof=state.angular_proof.unwrap();
    let kind=if p==Profile::Ms1{VehicleKind::Ms1}else{VehicleKind::Is7};
    let mut world=model::World::new_for_vehicle(7,Instant::now(),c.map_id(),kind).unwrap();
    for (i,n) in ["one","two"].into_iter().enumerate(){world.attach(model::Identity{account:n.into(),database:i as i32+1,name:n.into()},i as u32+1).unwrap();}
    world.fragiles=Some(fragiles::State::new(d.clone()));world.impact.bind_fragiles(d.clone()).unwrap();
    let source=proof::Source{session:1,generation:1,config_sha256:"c".repeat(64),profile:p};world.bind_contact_source(0,source).unwrap();
    let context=proof::Context{battle:7,slot:0,session:1,generation:1,seq:state.seq,tick:state.tick,
        config_sha256:"c".repeat(64),catalog_sha256:c.sha256().into(),domain_sha256:d.sha256.clone(),scene_version:0,
        scene_sha256:Scene::new(&c,&[]).unwrap().hash().into()};
    let frame=Arc::new(proof::ContextFrame{context,proof});
    let mut inputs=state.object_contacts.iter().map(|r|model::VehicleContactInput{object_id:r.object_id,substep:r.substep,point:r.point,normal:r.normal,
        velocity:r.velocity,mass_kg:p.mass(),kind:r.kind.clone(),shooter:0,proof:Some(proof::ContactProof{frame:frame.clone(),
            index:frame.proof.receipts.iter().position(|p|p.object_id==r.object_id).unwrap()})}).collect::<Vec<_>>();inputs.sort_by_key(|c|c.proof.as_ref().unwrap().index);(world,inputs)
}
#[test]fn angular_domain_trace_recompute_complete_chain_in_reverse_id_order(){
    let(mut world,inputs)=world_inputs("mixed-False");
    assert_eq!(inputs.iter().map(|c|c.object_id).collect::<Vec<_>>(),vec![18,1,3]);
    assert_eq!(inputs.iter().map(|c|c.proof.as_ref().unwrap().index).collect::<Vec<_>>(),vec![0,1,2]);
    let events=world.apply_vehicle_contacts(&inputs).unwrap();assert_eq!(events.len(),3);assert_eq!(world.scene_version(),3);
    assert_eq!(world.impact.contact_source_history().len(),1);
    assert!(events.iter().all(|e|e.proof.as_ref().unwrap().frame.proof.receipts.len()==3));
    assert!(world.apply_vehicle_contacts(&inputs).is_err());
}
#[test]fn angular_domain_rejects_missing_subset_forged_context_or_frame_atomically(){
    let(world,inputs)=world_inputs("mixed-False");
    for change in 0..10 {let mut w=world.clone();let mut rows=inputs.clone();
        match change {
            0=>rows[0].proof=None,1=>{rows.pop();},2=>{rows.push(rows[0].clone());},9=>rows.swap(0,1),
            _=>{let p=rows[1].proof.as_mut().unwrap();let frame=Arc::make_mut(&mut p.frame);
                match change {3=>frame.context.config_sha256="a".repeat(64),4=>frame.context.scene_sha256="a".repeat(64),
                    5=>frame.context.generation=2,6=>frame.context.session=2,7=>frame.context.battle=8,
                    _=>{Arc::make_mut(&mut frame.proof).receipts[0].budget_after.v[0]=9.;}}
            }
        }
        assert!(w.apply_vehicle_contacts(&rows).is_err(),"{change}");assert_eq!(w.scene_version(),0);assert!(w.impact.events().is_empty());
    }
}
#[test]fn angular_duplicate_producer_advances_watermark_and_rejoin_retains_old_source(){
    let(mut world,inputs)=world_inputs("is7-angular-example");
    assert_eq!(world.apply_vehicle_contacts(&inputs).unwrap().len(),1);
    let mut peer=inputs.clone();let p=peer[0].proof.as_mut().unwrap();let frame=Arc::make_mut(&mut p.frame);
    frame.context.slot=1;frame.context.session=2;frame.context.generation=2;peer[0].shooter=1;
    world.bind_contact_source(1,proof::Source{session:2,generation:2,config_sha256:"c".repeat(64),profile:Profile::Is7}).unwrap();
    assert!(world.apply_vehicle_contacts(&peer).unwrap().is_empty());assert!(world.apply_vehicle_contacts(&peer).is_err());
    world.actors[0].session=None;world.revoke_contact_source(0).unwrap();world.actors[0].session=Some(3);
    assert!(world.bind_contact_source(0,proof::Source{session:3,generation:1,config_sha256:"c".repeat(64),profile:Profile::Is7}).is_err());
    world.bind_contact_source(0,proof::Source{session:3,generation:3,config_sha256:"c".repeat(64),profile:Profile::Is7}).unwrap();
    assert!(world.apply_vehicle_contacts(&inputs).is_err());assert_eq!(world.impact.contact_source_history()[0].2.session,1);
    let mut fresh=inputs.clone();fresh[0].object_id=3;
    let p=fresh[0].proof.as_mut().unwrap();let frame=Arc::make_mut(&mut p.frame);
    frame.context.session=3;frame.context.generation=3;frame.context.scene_version=1;
    frame.context.scene_sha256=world.fragiles.as_ref().unwrap().historical_scene_hash(1).unwrap();
    Arc::make_mut(&mut frame.proof).receipts[0].object_id=3;
    assert_eq!(world.apply_vehicle_contacts(&fresh).unwrap().len(),1);
    assert_eq!(world.impact.contact_source_history().len(),2);
    assert_eq!(world.impact.contact_source_history()[0].2.session,1);
    assert_eq!(world.impact.contact_source_history()[1].2.session,3);
}
#[test]fn angular_historical_source_scene_survives_same_tick_projectile_change(){
    let(world,inputs)=world_inputs("is7-angular-example");let mut state=world.fragiles.unwrap();
    let object=state.catalog.objects.iter().find(|o|o.object_id==18).unwrap().clone();
    let hit=terrain::Hit{t:0.5,point:[0.;3],normal:[1.,0.,0.],triangle_id:object.projectile_first_triangle,
        surface:terrain::Surface::StaticObstacle{instance_id:object.instance_id,material_kind:object.material_kind}};
    let damage=state.contact_for(VehicleKind::Is7,1,0,1000,hit).unwrap().unwrap();assert_eq!(damage.scene_after,1);
    let c=&inputs[0];let event=state.ram_contact_with_proof(c.object_id,c.shooter,1000,c.substep,c.point,c.normal,c.velocity,c.mass_kg,c.kind.clone(),c.proof.clone()).unwrap().unwrap();
    assert_eq!((event.scene_before,event.scene_after),(1,2));assert_eq!(event.proof.unwrap().frame.context.scene_version,0);
}
