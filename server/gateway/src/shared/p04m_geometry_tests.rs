use super::*;
fn raw(kind:VehicleKind)->Vec<u8> {
    let root=std::env::var("WOT091_ROOT").unwrap_or_else(|_|"D:/WoT_9.1_Server".into());
    fs::read(Path::new(&root).join("local/evidence/20261016-p04m-source-import01").join(format!("{}-stock.json",kind.label()))).unwrap()
}
#[test] fn p04m_real_exports_preserve_mesh_counts_pivots_and_visual_bounds() {
    for kind in [VehicleKind::T26,VehicleKind::T34,VehicleKind::T3485] {
        let bytes=raw(kind);let b=Bundle::from_bytes(&bytes).unwrap();let spec=source_spec(kind).unwrap();
        assert_eq!(b.vehicle_kind(),kind);assert_eq!([b.hull,b.turret,b.gun],spec.pivots);assert_eq!(b.component_bounds(),spec.visual_bounds);
        for (index,part) in b.components.iter().enumerate() {
            assert_eq!((part.vertices.len(),part.triangles.len()),spec.counts[index]);
            assert_eq!(part.triangles.iter().map(|t|t.triangle_id).collect::<Vec<_>>(),(0..spec.counts[index].1 as u32).map(|i|index as u32*100000+i).collect::<Vec<_>>());
        }
        let expected=std::array::from_fn::<_,3,_>(|axis|b.hull[axis]+b.turret[axis]);
        assert_eq!(kind.aim().pivot,expected);assert_eq!(kind.aim().gun,b.gun);
        let mut changed=bytes.clone();changed.push(b' ');assert!(Bundle::from_bytes(&changed).is_err());
    }
}
#[test] fn p04m_sparse_materials_distinguish_absent_ids_missing_record_and_explicit_zero() {
    let b=Bundle::from_bytes(&raw(VehicleKind::T3485)).unwrap();
    assert!(b.materials.lookup("Hull","armor_14").is_err());assert!(b.materials.lookup("Gun_01","armor_3").is_err());
    assert_eq!(b.materials.lookup("Gun_01","armor_6").unwrap().effective.unwrap().armor,Some(0.));
    assert!(b.materials.lookup("Hull","surveyingDevice").unwrap().effective.is_none());
    assert_eq!(b.materials.lookup("Gun_01","gun").unwrap().effective.unwrap().vehicle_damage_factor,0.);
    let mut fake=b.materials.lookup("Hull","armor_15").unwrap();fake.kind=14;fake.name="armor_14".into();fake.effective.as_mut().unwrap().kind=14;
    assert!(super::super::ap::resolve_for_pair(VehicleKind::T26,VehicleKind::T3485,super::super::ap::Input{material:&fake,segment_direction:[0.,0.,1.],winding_normal:[0.,0.,-1.],distance:10.}).is_err());
    let mut value:Value=serde_json::from_slice(&raw(VehicleKind::T3485)).unwrap();let rows=value["geometry"]["components"][0]["materials"].as_array_mut().unwrap();
    rows[13]["kind"]=14.into();rows[13]["name"]="armor_14".into();rows[13]["effective"]["kind"]=14.into();
    assert!(Catalog::from_p04m_for(VehicleKind::T3485,&value["geometry"]["components"]).is_err());
}
