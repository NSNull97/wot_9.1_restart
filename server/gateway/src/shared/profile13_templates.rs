//! Source-bound profile13 resources, validated before opening login sockets.
//! Version1 retains homogeneous IPC6. Version2 explicitly binds the complete
//! IPC7 artifact tree and admits both existing kinds to one physical scene.
//! Version3 adds the complete five-kind curated source registry; registering
//! resources never overrides the separate owner/native battle-admission gate.
//! Version4 separately binds seven profiles and shared-only extended pools;
//! only the explicit LAB route may use the new source assemblies.
use std::{fs, io::{self, Read}, path::{Path, PathBuf}, sync::Arc};
use serde_json::Value;
use sha2::{Digest,Sha256};
use crate::{battle091::profile13, map_drive_worker091::{Pool,CatalogSpec}, map_profile091::MapId};
use super::{geometry::Bundle,fragiles::Catalog,terrain::Terrain,vehicle_profile::VehicleKind};

fn bad(reason:&'static str)->io::Error {io::Error::new(io::ErrorKind::InvalidData,format!("profile13 templates: {reason}"))}

#[derive(Clone,Debug,PartialEq,Eq)]
struct Reference {path:PathBuf,sha256:String}
#[derive(Clone,Debug,PartialEq,Eq)]
struct Profile {kind:VehicleKind,pool:Reference,geometry:Reference}
#[derive(Clone,Debug,PartialEq,Eq)]
struct Manifest {version:u8,map:MapId,catalog:Reference,profiles:Vec<Profile>,shared_physics:Option<Reference>}

fn keys(value:&Value,expected:&[&str])->io::Result<()> {
    let object=value.as_object().ok_or_else(||bad("object type"))?;
    if object.len()!=expected.len()||expected.iter().any(|key|!object.contains_key(*key)){return Err(bad("exact object fields"));}
    Ok(())
}
fn text<'a>(value:&'a Value,key:&str)->io::Result<&'a str>{value[key].as_str().ok_or_else(||bad("string field"))}
fn reference(value:&Value)->io::Result<Reference> {
    keys(value,&["path","sha256"])?;
    let path=PathBuf::from(text(value,"path")?);let sha256=text(value,"sha256")?;
    if !path.is_absolute()||path.as_os_str().len()>1024||sha256.len()!=64
        ||!sha256.bytes().all(|b|b.is_ascii_digit()||(b'a'..=b'f').contains(&b)) {return Err(bad("absolute reference and SHA"));}
    Ok(Reference{path,sha256:sha256.into()})
}
fn parse(raw:&[u8])->io::Result<Manifest> {
    let value=profile13::bounded_json(raw,profile13::MAX_REPLY_BYTES)?;
    let version=value["version"].as_u64();
    if matches!(version,Some(2|3|4|5)){keys(&value,&["version","map","catalog","profiles","shared_physics"])?;}
    else{keys(&value,&["version","map","catalog","profiles"])?;}
    if !matches!(version,Some(1|2|3|4|5)){return Err(bad("version/map"));}
    // Any registry map whose client arena has ctf bases (lifecycle rules).
    let map=MapId::from_asset(text(&value,"map")?).map_err(|_|bad("version/map"))?;
    super::lifecycle::Rules::for_map(map).map_err(|_|bad("map lifecycle rules"))?;
    let rows=value["profiles"].as_array().ok_or_else(||bad("profile list"))?;
    // Version5 (BATTLE-ANY): the five curated kinds plus 1..=MAX_GENERATED generated kinds.
    let count=match version{Some(4)=>7,Some(3|5)=>5,_=>2};
    if version==Some(5){if !(count+1..=count+MAX_GENERATED).contains(&rows.len()){return Err(bad("generated profile count"));}}
    else if rows.len()!=count{return Err(bad("exact curated source profile count"));}
    let mut profiles:Vec<Option<Profile>>=vec![None;count];let mut generated:Vec<Profile>=Vec::new();
    for row in rows {
        keys(row,&["kind","pool","geometry"])?;
        let label=text(row,"kind")?;
        if version==Some(5)&&VehicleKind::from_label(label).is_none(){
            let kind=VehicleKind::from_owned_label(label).filter(|k|k.is_generated()).ok_or_else(||bad("unknown vehicle profile"))?;
            if generated.iter().any(|p|p.kind==kind){return Err(bad("duplicate vehicle profile"));}
            generated.push(Profile{kind,pool:reference(&row["pool"])?,geometry:reference(&row["geometry"])?});continue;
        }
        let kind=if version==Some(4){VehicleKind::from_extended_label(label)}else{VehicleKind::from_label(label)}
            .ok_or_else(||bad("unknown vehicle profile"))?;
        let index=kind.index();if index>=count{return Err(bad("kind requires version3 curated pool"));}
        if profiles[index].is_some(){return Err(bad("duplicate vehicle profile"));}
        profiles[index]=Some(Profile{kind,pool:reference(&row["pool"])?,geometry:reference(&row["geometry"])?});
    }
    generated.sort_by(|a,b|a.kind.label().cmp(b.kind.label()));
    Ok(Manifest{version:version.ok_or_else(||bad("version"))? as u8,map,catalog:reference(&value["catalog"])?,
        profiles:profiles.into_iter().map(|p|p.ok_or_else(||bad("missing curated source profile"))).chain(generated.into_iter().map(Ok)).collect::<io::Result<_>>()?,
        shared_physics:if matches!(version,Some(2|3|4|5)){Some(reference(&value["shared_physics"])?)}else{None}})
}
fn plain(path:&Path)->io::Result<()> {
    for parent in path.ancestors(){
        let metadata=fs::symlink_metadata(parent)?;
        if metadata.file_type().is_symlink(){return Err(bad("linked resource"));}
        #[cfg(windows)]{
            use std::os::windows::fs::MetadataExt;
            if metadata.file_attributes()&0x400!=0{return Err(bad("reparse resource"));}
        }
    }
    Ok(())
}
fn owned(root:&Path,path:&Path)->io::Result<PathBuf> {
    if !path.is_absolute(){return Err(bad("relative resource path"));}
    plain(root)?;plain(path)?;let root=root.canonicalize()?;let actual=path.canonicalize()?;
    if !actual.starts_with(&root)||actual==root{return Err(bad("resource escapes local root"));}
    Ok(actual)
}
fn read(path:&Path,maximum:usize)->io::Result<Vec<u8>>{
    let file=fs::File::open(path)?;let metadata=file.metadata()?;
    if !metadata.is_file()||metadata.len()==0||metadata.len()>maximum as u64{return Err(bad("resource size/type"));}
    let mut raw=Vec::new();file.take(maximum as u64+1).read_to_end(&mut raw)?;
    if raw.len() as u64!=metadata.len(){return Err(bad("resource changed while reading"));}Ok(raw)
}
fn pin(root:&Path,reference:&Reference,maximum:usize)->io::Result<PathBuf>{
    let path=owned(root,&reference.path)?;let raw=read(&path,maximum)?;
    if format!("{:x}",Sha256::digest(&raw))!=reference.sha256{return Err(bad("resource SHA mismatch"));}Ok(path)
}

#[derive(Clone)]
pub(super) struct Resources {
    pub(super) kind:VehicleKind,
    pub(super) pool:Arc<Pool>,
    pub(super) geometry:Arc<Bundle>,
    pub(super) terrain:Arc<Terrain>,
    pub(super) catalog:(Arc<Catalog>,CatalogSpec),
    pub(super) shared:Option<Arc<SharedResources>>,
    pub(super) map:MapId,
}
#[derive(Clone)]
pub(super) struct SharedResources {
    pub version:u8,
    pub root:PathBuf,pub artifacts:crate::scene_worker::Artifacts,
    /// Row order of the template: curated kinds by index, then generated kinds by label.
    pub kinds:Vec<VehicleKind>,
    pub maps:Vec<crate::map_drive_worker091::MapSpec>,
    pub source_profiles:Vec<Option<(PathBuf,String)>>,
}
// BW-01 wire codec (tools/bw01_wire_gen.py): SharedResources
impl crate::bw_wire::Wire for SharedResources {
    fn put(&self,bw_o:&mut crate::bw_wire::Enc){use crate::bw_wire::Wire as W;let Self{version,root,artifacts,kinds,maps,source_profiles}=self;W::put(version,bw_o);W::put(root,bw_o);W::put(artifacts,bw_o);W::put(kinds,bw_o);W::put(maps,bw_o);W::put(source_profiles,bw_o);}
    fn get(bw_i:&mut crate::bw_wire::Dec)->std::io::Result<Self>{use crate::bw_wire::Wire as W;Ok(Self{version:W::get(bw_i)?,root:W::get(bw_i)?,artifacts:W::get(bw_i)?,kinds:W::get(bw_i)?,maps:W::get(bw_i)?,source_profiles:W::get(bw_i)?})}
}
// end BW-01 wire codec
impl SharedResources {
    /// Row of a kind in `kinds`/`maps`/`source_profiles`.
    pub fn slot(&self,kind:VehicleKind)->Option<usize>{self.kinds.iter().position(|k|*k==kind)}
}
/// Bound of generated rows in one template (same as the generated registry bound).
const MAX_GENERATED:usize=super::generated_vehicles::MAX_GENERATED;
fn shared_source_reference(kind:VehicleKind,version:u8,source:Option<(PathBuf,String)>)->io::Result<Option<Reference>> {
    if kind.index()<2 {
        if source.is_some(){return Err(bad("legacy kind with unexpected stock source profile"));}return Ok(None);
    }
    if !(version==4||matches!(version,3|5)&&!kind.is_extended()){return Err(bad("qualified source requires its explicit resource version"));}
    let (path,sha256)=source.ok_or_else(||bad("missing qualified stock source profile"))?;
    Ok(Some(reference(&serde_json::json!({"path":path,"sha256":sha256}))?))
}

pub(super) fn load(local_root:&Path,manifest_path:&Path)->io::Result<Vec<Resources>> {
    let path=owned(local_root,manifest_path)?;let manifest=parse(&read(&path,profile13::MAX_REPLY_BYTES)?)?;
    let catalog_path=owned(local_root,&manifest.catalog.path)?;
    let catalog=Arc::new(Catalog::load(local_root,&catalog_path,&manifest.catalog.sha256)?);
    let worker_path=catalog_path.parent().ok_or_else(||bad("catalog parent"))?.join(&catalog.worker_file);
    owned(local_root,&worker_path)?;
    let worker=CatalogSpec::load(local_root,&worker_path,&catalog.worker_sha256)?;
    let map=manifest.map;
    super::server::validate_catalog_projection(&catalog,&worker,map)?;
    let load_profile=|profile:Profile|->io::Result<Resources>{
        let pool_path=pin(local_root,&profile.pool,16384)?;
        let geometry_path=pin(local_root,&profile.geometry,512*1024)?;
        let pool=Arc::new(Pool::load(local_root,&pool_path)?);
        let shared_only=profile.kind.is_extended()||profile.kind.is_generated();
        if pool.shared_only()!=shared_only||profile.kind.is_extended()&&manifest.version!=4||profile.kind.is_generated()&&manifest.version!=5 {
            return Err(bad("extended/generated profile requires its shared-only pool and resource version"));
        }
        super::server::selected_pool_config(&pool,map)?;
        let geometry=Arc::new(Bundle::load(local_root,&geometry_path)?);
        super::server::validate_vehicle_binding(profile.kind,&pool,Some(&geometry))?;
        let terrain=super::server::terrain_for_pool_for_map(&pool,map)?;
        catalog.bind_geometry(&terrain)?;
        println!("P08B_TEMPLATE_VALIDATED kind={} pool_sha256={} geometry_sha256={} catalog_sha256={} map={} resources_only=true",
            profile.kind.label(),pool.sha256,profile.geometry.sha256,manifest.catalog.sha256,map.asset());
        Ok(Resources{kind:profile.kind,pool,geometry,terrain,catalog:(catalog.clone(),worker.clone()),shared:None,map})
    };
    let mut rows=manifest.profiles.into_iter().map(load_profile).collect::<io::Result<Vec<_>>>()?;
    if let Some(reference)=manifest.shared_physics {
        let path=pin(local_root,&reference,65536)?;
        let mut source_profiles:Vec<Option<(PathBuf,String)>>=vec![None;rows.len()];
        for (slot,row) in rows.iter().enumerate() {
            if let Some(reference)=shared_source_reference(row.kind,manifest.version,row.pool.shared_source_profile())? {
                let path=pin(local_root,&reference,65536)?;
                source_profiles[slot]=Some((path,reference.sha256));
            }
        }
        let shared=Arc::new(SharedResources{version:manifest.version,root:local_root.canonicalize()?,artifacts:crate::scene_worker::Artifacts::load(&path)?,
            kinds:rows.iter().map(|row|row.kind).collect(),
            maps:rows.iter().map(|row|super::server::selected_pool_map(&row.pool,map).cloned()).collect::<io::Result<_>>()?,source_profiles});
        for row in &mut rows{row.shared=Some(shared.clone());}
    }
    Ok(rows)
}

#[cfg(test)]
#[path="p06t_extended_templates_tests.rs"]
mod extended_tests;
#[cfg(test)]
pub(crate) fn extended_test_resources()->Vec<Resources>{extended_tests::actual_resources()}

#[cfg(test)]
mod tests {
    use super::*;
    fn value()->Value{
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
        let reference=|name:&str|serde_json::json!({"path":root.join(name).to_string_lossy(),"sha256":"a".repeat(64)});
        serde_json::json!({"version":1,"map":"05_prohorovka","catalog":reference("catalog.json"),
            "profiles":[{"kind":"ms1","pool":reference("ms1-pool.json"),"geometry":reference("ms1-geometry.json")},
                {"kind":"is7","pool":reference("is7-pool.json"),"geometry":reference("is7-geometry.json")} ]})
    }
    /// BATTLE-ANY: version5 = the five curated kinds plus generated registry kinds (sorted by label).
    /// Resources only: catalog admission stays separate (a registry kind outside the catalog binds, never admits).
    #[test]fn profile13_templates_version5_carries_generated_kinds_beside_the_curated_five(){
        let base=value();let reference=|name:&str|{let mut r=base["catalog"].clone();
            r["path"]=Path::new(r["path"].as_str().unwrap()).with_file_name(name).to_string_lossy().into();r};
        let row=|kind:&str|serde_json::json!({"kind":kind,"pool":reference(&format!("{kind}-pool.json")),"geometry":reference(&format!("{kind}-geometry.json"))});
        let mut v=base.clone();v["version"]=5.into();v["shared_physics"]=reference("shared.json");
        v["profiles"]=serde_json::json!([row("ms1"),row("is7"),row("t26"),row("t34"),row("t3485"),row("usa-M4_Sherman"),row("ussr-KV-3")]);
        let m=parse(&serde_json::to_vec(&v).unwrap()).unwrap();
        let labels:Vec<_>=m.profiles.iter().map(|p|p.kind.label()).collect();
        assert_eq!(labels,["ms1","is7","t26","t34","t3485","usa-M4_Sherman","ussr-KV-3"]);
        assert!(m.profiles[5..].iter().all(|p|p.kind.is_generated()));
        for mutation in 0..7{let mut w=v.clone();let rows=w["profiles"].as_array_mut().unwrap();match mutation{
            0=>{rows.truncate(5);},1=>rows.push(row("ussr-KV-3")),2=>rows.push(row("ussr-Object_261")),3=>rows.push(row("wt-e100-128")),
            4=>{rows.remove(2);},5=>w["version"]=3.into(),6=>rows.push(row("ms1")),_=>unreachable!()}
            assert!(parse(&serde_json::to_vec(&w).unwrap()).is_err(),"mutation={mutation}");}
    }
    #[test]fn profile13_templates_require_two_exact_homogeneous_source_profiles(){
        let value=value();let expected=parse(&serde_json::to_vec(&value).unwrap()).unwrap();
        assert_eq!(expected.profiles[0].kind,VehicleKind::Ms1);assert_eq!(expected.profiles[1].kind,VehicleKind::Is7);
        let mut reversed=value.clone();reversed["profiles"].as_array_mut().unwrap().reverse();
        assert_eq!(parse(&serde_json::to_vec(&reversed).unwrap()).unwrap(),expected);
        assert_eq!(expected.map,MapId::Prohorovka);
        // MAPS-01: the map is registry data; another registry map with client ctf bases is carried through.
        let mut karelia=value.clone();karelia["map"]="01_karelia".into();
        assert_eq!(parse(&serde_json::to_vec(&karelia).unwrap()).unwrap().map,MapId::Karelia);
        for mutation in 0..10{
            let mut wrong=value.clone();match mutation{
                0=>wrong["map"]="98_unregistered".into(),1=>wrong["version"]=2.into(),
                2=>wrong["profiles"][1]["kind"]="ms1".into(),3=>wrong["profiles"][0]["kind"]="unknown".into(),
                4=>wrong["profiles"][0]["pool"]["path"]="relative.json".into(),
                5=>wrong["profiles"][0]["pool"]["sha256"]="A".repeat(64).into(),
                6=>wrong["catalog"]["sha256"]="a".repeat(63).into(),7=>wrong["profiles"][0]["extra"]=1.into(),
                8=>{wrong["profiles"].as_array_mut().unwrap().pop();},9=>wrong["extra"]=1.into(),_=>unreachable!(),
            }
            assert!(parse(&serde_json::to_vec(&wrong).unwrap()).is_err(),"mutation={mutation}");
        }
        let raw=serde_json::to_string(&value).unwrap().replacen("\"kind\":\"ms1\"","\"kind\":\"ms1\",\"kind\":\"is7\"",1);
        assert!(parse(raw.as_bytes()).is_err());
    }
    /// MAPS-01 stand check, run explicitly: `--test-filter <this name> --run-ignored`
    /// with MAPS01_BATTLE_PROFILES=<stand>/battle-profiles.json and MAPS01_LOCAL_ROOT=<local>.
    #[test]#[ignore]fn external_battle_profiles_load_every_kind_on_their_registry_map(){
        let path=std::env::var("MAPS01_BATTLE_PROFILES").expect("MAPS01_BATTLE_PROFILES");
        let root=PathBuf::from(std::env::var("MAPS01_LOCAL_ROOT").expect("MAPS01_LOCAL_ROOT"));
        let value:Value=serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        let map=MapId::from_asset(value["map"].as_str().unwrap()).unwrap();
        let rows=load(&root,Path::new(&path)).unwrap();
        assert_eq!(rows.len(),value["profiles"].as_array().unwrap().len());
        assert!(rows.iter().all(|row|row.map==map&&row.catalog.0.map==map&&row.terrain.map_id()==map&&row.shared.is_some()));
        println!("MAPS01_TEMPLATES_LOADED map={} kinds={}",map.asset(),rows.iter().map(|row|row.kind.label()).collect::<Vec<_>>().join(","));
    }
    #[test]fn profile13_templates_pin_bytes_and_refuse_paths_outside_local_root(){
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let directory=root.join(format!("test-runs/profile13-templates-{}-{stamp}",std::process::id()));
        fs::create_dir_all(&directory).unwrap();let path=directory.join("authored-test-asset.txt");
        fs::write(&path,b"owned source bytes").unwrap();
        let reference=Reference{path:path.clone(),sha256:format!("{:x}",Sha256::digest(b"owned source bytes"))};
        assert_eq!(pin(&root,&reference,64).unwrap(),path.canonicalize().unwrap());
        fs::write(&path,b"changed source bytes").unwrap();assert!(pin(&root,&reference,64).is_err());
        assert!(pin(&root,&reference,3).is_err());
        assert!(owned(&root,&Path::new(env!("CARGO_MANIFEST_DIR")).join("Cargo.toml")).is_err());
        assert!(owned(&root,Path::new("relative.json")).is_err());assert!(owned(&root,&root).is_err());
    }
    #[test]fn p05c_template_version_two_requires_a_closed_pinned_shared_artifact_reference(){
        let mut v=value();v["version"]=2.into();assert!(parse(&serde_json::to_vec(&v).unwrap()).is_err());
        v["shared_physics"]=v["catalog"].clone();assert!(parse(&serde_json::to_vec(&v).unwrap()).unwrap().shared_physics.is_some());
        for mutation in 0..5{let mut wrong=v.clone();match mutation{
            0=>wrong["shared_physics"]["path"]="relative.json".into(),1=>wrong["shared_physics"]["sha256"]="A".repeat(64).into(),
            2=>wrong["shared_physics"]["extra"]=true.into(),3=>wrong["version"]=1.into(),_=>wrong["version"]=3.into()}
            assert!(parse(&serde_json::to_vec(&wrong).unwrap()).is_err());}
    }
    fn five()->Value {
        let mut v=value();let base=v["catalog"].clone();v["version"]=3.into();v["shared_physics"]=base.clone();
        v["profiles"]=serde_json::json!(VehicleKind::ALL.map(|kind|serde_json::json!({"kind":kind.label(),"pool":base.clone(),"geometry":base.clone()})));v
    }
    #[test]fn p04m_manifest3_requires_all_five_curated_kinds_in_canonical_resource_order() {
        let v=five();let parsed=parse(&serde_json::to_vec(&v).unwrap()).unwrap();
        assert_eq!(parsed.profiles.iter().map(|p|p.kind).collect::<Vec<_>>(),VehicleKind::ALL);
        let mut reversed=v.clone();reversed["profiles"].as_array_mut().unwrap().reverse();
        assert_eq!(parse(&serde_json::to_vec(&reversed).unwrap()).unwrap(),parsed);
        for kind in VehicleKind::ALL.into_iter().skip(2){assert!(!kind.battle_admission());}
    }
    #[test]fn p04m_manifest3_rejects_missing_extra_duplicate_and_unknown_profile_rows() {
        let v=five();
        for mutation in 0..7 {
            let mut wrong=v.clone();match mutation {
                0=>{wrong["profiles"].as_array_mut().unwrap().pop();},
                1=>wrong["profiles"][4]["kind"]="ms1".into(),
                2=>wrong["profiles"][3]["kind"]="T34".into(),
                3=>{let extra=wrong["profiles"][0].clone();wrong["profiles"].as_array_mut().unwrap().push(extra);},
                4=>wrong["profiles"][2]["source_profile"]=serde_json::Value::Null,
                5=>wrong["profiles"][2]["geometry"]["sha256"]="A".repeat(64).into(),
                _=>wrong.as_object_mut().unwrap().remove("shared_physics").map(|_|()).unwrap(),
            }
            assert!(parse(&serde_json::to_vec(&wrong).unwrap()).is_err(),"mutation={mutation}");
        }
    }
    #[test]fn p04m_old_versions_cannot_smuggle_new_kinds_or_five_rows() {
        for version in [1,2] {
            let mut wrong=value();wrong["version"]=version.into();if version==2{wrong["shared_physics"]=wrong["catalog"].clone();}
            wrong["profiles"][1]["kind"]="t26".into();assert!(parse(&serde_json::to_vec(&wrong).unwrap()).is_err());
            let mut wrong=five();wrong["version"]=version.into();if version==1{wrong.as_object_mut().unwrap().remove("shared_physics");}
            assert!(parse(&serde_json::to_vec(&wrong).unwrap()).is_err());
        }
    }
    #[test]fn p04m_qualified_source_reference_is_mandatory_for_new_kinds_and_absent_for_old() {
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
        let source=(root.join("owned-qualified-profile.json"),"a".repeat(64));
        for kind in VehicleKind::ALL {
            assert_eq!(shared_source_reference(kind,3,None).is_ok(),kind.index()<2);
            assert_eq!(shared_source_reference(kind,3,Some(source.clone())).is_ok(),kind.index()>=2);
            if kind.index()>=2 {
                assert!(shared_source_reference(kind,2,Some(source.clone())).is_err());
                assert!(shared_source_reference(kind,3,Some((PathBuf::from("relative.json"),source.1.clone()))).is_err());
                assert!(shared_source_reference(kind,3,Some((source.0.clone(),"A".repeat(64)))).is_err());
            }
        }
    }
    #[test]fn p04m_real_source_geometry_cannot_bind_to_another_kind_pool() {
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local").canonicalize().unwrap();
        let (path,_)=crate::portable_test_fixtures::verified(&root.join("stands/p08b-profile13-01/battle-profiles.json"),None);
        let old=parse(&read(&path,profile13::MAX_REPLY_BYTES).unwrap()).unwrap();
        let pool=Pool::load(&root,&old.profiles[0].pool.path).unwrap();assert_eq!(pool.vehicle_kind(),VehicleKind::Ms1);
        let geometry=Bundle::load(&root,&root.join("evidence/20261016-p04m-source-import01/t26-stock.json")).unwrap();
        assert!(super::super::server::validate_vehicle_binding(VehicleKind::T26,&pool,Some(&geometry)).is_err());
        assert!(super::super::server::validate_vehicle_binding(VehicleKind::Ms1,&pool,Some(&geometry)).is_err());
    }
}
