//! MAPS-02 falling atom domain rule. Catalog rows are synthetic parser
//! fixtures on the Karelia registry pins; masses are the server profile masses
//! (vehicle_profile.rs). No native identity or rendered fall is claimed here.
use super::*;
use serde_json::json;

const IS7_KG:f32=68190.;
const MS1_KG:f32=4691.;

fn v8_manifest()->Value{
    let mut v=super::tests::v7_static_manifest_for_columns();
    v["version"]=json!(8);v["falling_atom_policy"]=json!(FALLING_ATOM_POLICY);
    v["objects"].as_array_mut().unwrap().push(json!({"object_id":1601,"instance_id":1600,"chunk_id":31355,"native_index":7,
        "resource":"content/Environment/env414_Pole/normal/lod0/env414_Pole1.model","health":18,"material_kind":0,
        "projectile_first_triangle":89316,"projectile_triangle_count":0,"physics_first_triangle":173433,"physics_triangle_count":0,
        "object_revision":"4".repeat(64),"kind":"falling_atom","ram_response":FALLING_ATOM_RAM_RESPONSE,
        "scaled_health":18,"kinetic_damage_correction":0.0,"trigger_first_triangle":0,"trigger_triangle_count":10}));
    v
}
fn parse(v:&Value)->io::Result<Catalog>{let raw=serde_json::to_vec(v).unwrap();Catalog::parse(&raw,&format!("{:x}",Sha256::digest(&raw)))}
pub(crate) fn column_catalog()->Arc<Catalog>{Arc::new(parse(&v8_manifest()).unwrap())}
fn state()->State{let mut s=State::new(Arc::new(parse(&v8_manifest()).unwrap()));s.configure_roster(2).unwrap();s}

#[test]
fn client_break_predicate_matches_the_verified_formula_thresholds(){
    // 0.5*m*0.00015 = 5.11425 (IS-7) and 0.351825 (MS-1); HP18, kdc0.
    assert!(!column_breaks(18,0.,f64::from(IS7_KG),1.87*1.87));
    assert!(column_breaks(18,0.,f64::from(IS7_KG),1.88*1.88));
    assert!(!column_breaks(18,0.,f64::from(MS1_KG),7.15*7.15));
    assert!(column_breaks(18,0.,f64::from(MS1_KG),7.16*7.16));
    // kineticDamageCorrection2 (mle024_ObstacleRail): (68190/35000)^2 = 3.7958.
    assert!(!column_breaks(18,0.,f64::from(IS7_KG),1.));
    assert!(column_breaks(18,2.,f64::from(IS7_KG),1.));
    assert!(!column_breaks(18,2.,f64::from(MS1_KG),25.));
    assert!(!column_breaks(18,0.,f64::NAN,1.));
}

#[test]
fn catalog8_admits_only_exact_falling_atom_rows_and_v7_refuses_them(){
    let catalog=parse(&v8_manifest()).unwrap();
    let pole=catalog.objects.iter().find(|o|o.object_id==1601).unwrap();
    assert_eq!(pole.kind,ObjectKind::FallingAtom);assert_eq!(pole.kind.worker_kind(),"falling_atom");
    assert_eq!(catalog.ram_response(pole),Some(FALLING_ATOM_RAM_RESPONSE));
    let mut v7=v8_manifest();v7["version"]=json!(7);v7.as_object_mut().unwrap().remove("falling_atom_policy");
    assert!(parse(&v7).is_err());
    for (key,value) in [("physics_triangle_count",json!(3)),("projectile_triangle_count",json!(1)),("material_kind",json!(73)),
        ("trigger_triangle_count",json!(0)),("trigger_triangle_count",json!(257)),("scaled_health",json!(0)),
        ("kinetic_damage_correction",json!(-1.0)),("ram_response",json!("normal_linear")),("resource",json!("speedtree/x.spt"))]{
        let mut v=v8_manifest();v["objects"][3][key]=value;assert!(parse(&v).is_err(),"{key}");
    }
    let mut v=v8_manifest();v["falling_atom_policy"]=json!("other");assert!(parse(&v).is_err());
    let mut v=v8_manifest();v["objects"][3]["native_index"]=json!(0);v["objects"][3]["chunk_id"]=json!(31354);assert!(parse(&v).is_err());
    let mut v=v8_manifest();v["objects"][3].as_object_mut().unwrap().remove("trigger_first_triangle");assert!(parse(&v).is_err());
    let mut v=v8_manifest();v.as_object_mut().unwrap().remove("native_index_source");
    v["native_exports_sha256"]=json!(["1".repeat(64)]);assert!(parse(&v).is_err());
}

#[test]
fn column_contact_decides_once_with_packed_direction_and_speed(){
    let mut s=state();
    // Below the IS-7 threshold: no change, no event.
    let slow=s.clone();
    assert_eq!(s.column_contact(1601,0,1001,1,[0.;3],[1.,0.,0.],[1.5,0.,0.],IS7_KG).unwrap(),None);assert_eq!(s,slow);
    // Vertical-only motion has no fall direction.
    assert_eq!(s.column_contact(1601,0,1001,1,[0.;3],[1.,0.,0.],[0.,-5.,0.],IS7_KG).unwrap(),None);
    let event=s.column_contact(1601,1,1002,3,[1.,2.,3.],[0.,0.,1.],[0.,0.,5.],IS7_KG).unwrap().unwrap();
    // yaw=atan2(0,5)=0 -> 32; |v|=5 -> bucket2; native index7.
    assert_eq!(event.fallen_column,Some(0x0782));assert_eq!(event.proof,None);assert_eq!(event.kind,"hull");
    assert_eq!((event.scene_before,event.scene_after,event.shooter,event.tick,event.substep),(0,1,1,1002,3));
    assert_eq!(s.scene_version(),1);assert_eq!(s.removed_ids(),vec![1601]);
    assert_eq!(s.native_fallen_columns(31355),vec![0x0782]);assert!(s.native_fallen_columns(31354).is_empty());
    assert!(s.native_fragile_values(31355).is_empty());assert!(s.native_fallen_trees(31355).is_empty());
    // A fallen column never falls again and never changes its packed value.
    assert_eq!(s.column_contact(1601,0,1003,1,[0.;3],[1.,0.,0.],[9.,0.,0.],IS7_KG).unwrap(),None);
    assert_eq!(s.native_fallen_columns(31355),vec![0x0782]);
    // MS-1 needs about 7.15 m/s for HP18.
    let mut light=state();
    assert_eq!(light.column_contact(1601,0,1001,1,[0.;3],[1.,0.,0.],[-7.,0.,0.],MS1_KG).unwrap(),None);
    let e=light.column_contact(1601,0,1002,1,[0.;3],[1.,0.,0.],[-7.5,0.,0.],MS1_KG).unwrap().unwrap();
    // yaw=atan2(-7.5,0)=-pi/2 -> 16; |v|=7.5 -> bucket2.
    assert_eq!(e.fallen_column,Some((7<<8)|(16<<2)|2));
}

#[test]
fn column_contact_rejects_wrong_kind_bounds_and_ram_path(){
    let mut s=state();let before=s.clone();
    assert!(s.column_contact(1514,0,1001,1,[0.;3],[1.,0.,0.],[5.,0.,0.],IS7_KG).is_err());
    assert!(s.column_contact(9999,0,1001,1,[0.;3],[1.,0.,0.],[5.,0.,0.],IS7_KG).is_err());
    for (shooter,tick,step,normal,velocity,mass) in [(2,1001,1,[1.,0.,0.],[5.,0.,0.],IS7_KG),(0,0,1,[1.,0.,0.],[5.,0.,0.],IS7_KG),
        (0,1001,0,[1.,0.,0.],[5.,0.,0.],IS7_KG),(0,1001,7,[1.,0.,0.],[5.,0.,0.],IS7_KG),(0,1001,1,[2.,0.,0.],[5.,0.,0.],IS7_KG),
        (0,1001,1,[1.,0.,0.],[26.,0.,0.],IS7_KG),(0,1001,1,[1.,0.,0.],[f32::NAN,0.,0.],IS7_KG),(0,1001,1,[1.,0.,0.],[5.,0.,0.],999.)]{
        assert!(s.column_contact(1601,shooter,tick,step,[0.;3],normal,velocity,mass).is_err());
    }
    assert_eq!(s,before);
    assert!(s.ram_contact(1601,0,1001,1,[0.;3],[1.,0.,0.],[5.,0.,0.],IS7_KG,"hull".into()).is_err());
    let mut v7=State::new(super::tests::contact_catalog());v7.configure_roster(2).unwrap();
    assert!(v7.column_contact(1513,0,1001,1,[0.;3],[1.,0.,0.],[5.,0.,0.],IS7_KG).is_err());
}
