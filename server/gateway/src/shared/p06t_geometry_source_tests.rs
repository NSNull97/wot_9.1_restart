use super::*;
fn fixture(assembly:Assembly)->Vec<u8>{
    use std::io::Read;
    let directory=std::env::var_os("P06T_COMBAT_GEOMETRY_ROOT").map(std::path::PathBuf::from).unwrap_or_else(||{
        let root=std::env::var_os("WOT091_ROOT").map(std::path::PathBuf::from).unwrap_or_else(||"D:/WoT_9.1_Server".into());
        root.join("local/night-staging/20261016/p06t-combat-geometry01/promotion-source01")
    });
    let path=directory.join(format!("{}.json",assembly.label()));
    let mut bytes=Vec::new();std::fs::File::open(&path).unwrap_or_else(|e|panic!("required actual P06T geometry fixture {}: {e}",path.display()))
        .take(MAX_BYTES as u64+1).read_to_end(&mut bytes).unwrap();
    assert!(!bytes.is_empty()&&bytes.len()<=MAX_BYTES,"bounded actual fixture");
    assert_eq!(SourceBundle::parse(&bytes).unwrap().assembly,assembly,"closed actual source digest and assembly");
    bytes
}
#[test]fn p06t_geometry_actual_two_sources_load_all_six_meshes_and_exact_caps(){
    let wt=fixture(Assembly::Wt128);let fv=fixture(Assembly::Fv183);let WT=wt.as_slice();let FV=fv.as_slice();
    for(raw,assembly,total)in[(WT,Assembly::Wt128,549),(FV,Assembly::Fv183,614)]{let b=SourceBundle::parse(raw).unwrap();assert_eq!(b.assembly,assembly);
        assert_eq!(b.components.iter().map(|c|c.triangles.len()).sum::<usize>(),total);assert_eq!(b.pivots,assembly.pivots());
        for(i,c)in b.components.iter().enumerate(){assert_eq!((c.vertices.len(),c.triangles.len()),assembly.counts()[i]);assert_eq!(c.materials.iter().map(|m|m.kind).collect::<Vec<_>>(),assembly.material_ids(i));}
    }
}
#[test]fn p06t_geometry_closed_preparse_digest_rejects_poison_trailing_old_or_arbitrary(){
    let wt=fixture(Assembly::Wt128);let fv=fixture(Assembly::Fv183);let WT=wt.as_slice();let FV=fv.as_slice();
    for raw in[&[][..],b"{\"schema\":\"p04m-battle-source.v1\"}",b"[]"]{assert!(SourceBundle::parse(raw).is_err());}
    for raw in[WT,FV]{let mut bad=raw.to_vec();bad.push(b' ');assert!(SourceBundle::parse(&bad).is_err());}
}
#[test]fn p06t_geometry_gun31_source_fact_is_distinct_unsupported_not_gun25(){
    let wt=fixture(Assembly::Wt128);let fv=fixture(Assembly::Fv183);let WT=wt.as_slice();let FV=fv.as_slice();
    let b=SourceBundle::parse(WT).unwrap();let gun=&b.components[2];assert_eq!(gun.materials.len(),2);
    let breech=&gun.materials[1];assert_eq!((breech.kind,breech.source_class),(31,SourceClass::GunBreechVisualUnsupported));
    assert_eq!(breech.effective.as_ref().unwrap()["vehicleDamageFactor"],1.);assert_eq!(gun.triangles.iter().filter(|t|t.material=="gunBreech").count(),142);
    let fv=SourceBundle::parse(FV).unwrap();for c in &fv.components[..2]{assert!(c.materials.iter().find(|m|m.kind==28).unwrap().effective.is_none());}
}
#[test]fn p06t_geometry_late_structural_poison_rejects_without_partial_sourcebundle(){
    let wt=fixture(Assembly::Wt128);let fv=fixture(Assembly::Fv183);let WT=wt.as_slice();let FV=fv.as_slice();
    for poison in 0..7{let mut v:Value=serde_json::from_slice(WT).unwrap();match poison{
        0=>v["geometry"]["components"][2]["triangles"][237]["a"]=999999.into(),
        1=>v["geometry"]["components"][2]["triangles"][237]["a"]=true.into(),
        2=>v["geometry"]["components"][2]["triangles"][237]["material"]="gun".into(),
        3=>v["geometry"]["components"][2]["materials"][1]["source_class"]="gun_visual_material".into(),
        4=>v["geometry"]["components"][2]["materials"][1]["effective"]["vehicleDamageFactor"]=0.into(),
        5=>v["geometry"]["components"][2]["index_layout"]["width_bytes"]=4.into(),
        6=>v["geometry"]["pivots"][2][2]=0.into(),_=>unreachable!()}
        assert!(SourceBundle::from_value(Assembly::Wt128,&v).is_err(),"poison{poison}");
    }
}
#[test]fn p06t_geometry_actual_production_mesh_query_can_contact_source_breech_triangles(){
    let wt=fixture(Assembly::Wt128);let fv=fixture(Assembly::Fv183);let WT=wt.as_slice();let FV=fv.as_slice();
    let b=SourceBundle::parse(WT).unwrap();let c=&b.components[2];
    let mesh=Mesh::new(c.vertices.clone(),c.triangles.clone(),b.assembly.revision(),"component-local-v1").unwrap();
    // Deterministic actual mesh probes; no AABB/authored material contact.
    let mut found=false;
    for y in[-0.5,-0.25,0.,0.25,0.5]{for z in[-1.5,-1.,-0.5,0.,0.5,1.,1.5,2.]{
        let hits=super::super::collision::query(&mesh,[-3.,y,z],[3.,y,z]).unwrap();
        if hits.first().is_some_and(|h|h.material=="gunBreech"){found=true;}
    }}assert!(found,"actual source breech must be a queryable surface");
}
