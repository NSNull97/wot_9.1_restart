//! Explicit P08B resource set. Both existing homogeneous native profiles are
//! loaded and source-validated before login sockets are opened. Selection of
//! one profile for a battle never changes another actor's owned loadout.
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
struct Manifest {catalog:Reference,profiles:[Profile;2]}

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
    keys(&value,&["version","map","catalog","profiles"])?;
    if value["version"].as_u64()!=Some(1)||text(&value,"map")?!="05_prohorovka"{return Err(bad("version/map"));}
    let rows=value["profiles"].as_array().ok_or_else(||bad("profile list"))?;
    if rows.len()!=2{return Err(bad("exactly two source profiles required"));}
    let mut profiles=[None,None];
    for row in rows {
        keys(row,&["kind","pool","geometry"])?;
        let (kind,index)=match text(row,"kind")?{"ms1"=>(VehicleKind::Ms1,0),"is7"=>(VehicleKind::Is7,1),_=>return Err(bad("unknown vehicle profile"))};
        if profiles[index].is_some(){return Err(bad("duplicate vehicle profile"));}
        profiles[index]=Some(Profile{kind,pool:reference(&row["pool"])?,geometry:reference(&row["geometry"])?});
    }
    Ok(Manifest{catalog:reference(&value["catalog"])?,profiles:[profiles[0].take().ok_or_else(||bad("missing MS-1"))?,
        profiles[1].take().ok_or_else(||bad("missing IS-7"))?]})
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
}

pub(super) fn load(local_root:&Path,manifest_path:&Path)->io::Result<[Resources;2]> {
    let path=owned(local_root,manifest_path)?;let manifest=parse(&read(&path,profile13::MAX_REPLY_BYTES)?)?;
    let catalog_path=owned(local_root,&manifest.catalog.path)?;
    let catalog=Arc::new(Catalog::load(local_root,&catalog_path,&manifest.catalog.sha256)?);
    let worker_path=catalog_path.parent().ok_or_else(||bad("catalog parent"))?.join(&catalog.worker_file);
    owned(local_root,&worker_path)?;
    let worker=CatalogSpec::load(local_root,&worker_path,&catalog.worker_sha256)?;
    super::server::validate_catalog_projection(&catalog,&worker,MapId::Prohorovka)?;
    let load_profile=|profile:Profile|->io::Result<Resources>{
        let pool_path=pin(local_root,&profile.pool,16384)?;
        let geometry_path=pin(local_root,&profile.geometry,512*1024)?;
        let pool=Arc::new(Pool::load(local_root,&pool_path)?);
        super::server::selected_pool_config(&pool,MapId::Prohorovka)?;
        let geometry=Arc::new(Bundle::load(local_root,&geometry_path)?);
        super::server::validate_vehicle_binding(profile.kind,&pool,Some(&geometry))?;
        let terrain=super::server::terrain_for_pool_for_map(&pool,MapId::Prohorovka)?;
        catalog.bind_geometry(&terrain)?;
        println!("P08B_TEMPLATE_VALIDATED kind={} pool_sha256={} geometry_sha256={} catalog_sha256={} map=05_prohorovka resources_only=true",
            profile.kind.label(),pool.sha256,profile.geometry.sha256,manifest.catalog.sha256);
        Ok(Resources{kind:profile.kind,pool,geometry,terrain,catalog:(catalog.clone(),worker.clone())})
    };
    let [first,second]=manifest.profiles;
    Ok([load_profile(first)?,load_profile(second)?])
}

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
    #[test]fn profile13_templates_require_two_exact_homogeneous_source_profiles(){
        let value=value();let expected=parse(&serde_json::to_vec(&value).unwrap()).unwrap();
        assert_eq!(expected.profiles[0].kind,VehicleKind::Ms1);assert_eq!(expected.profiles[1].kind,VehicleKind::Is7);
        let mut reversed=value.clone();reversed["profiles"].as_array_mut().unwrap().reverse();
        assert_eq!(parse(&serde_json::to_vec(&reversed).unwrap()).unwrap(),expected);
        for mutation in 0..10{
            let mut wrong=value.clone();match mutation{
                0=>wrong["map"]="01_karelia".into(),1=>wrong["version"]=2.into(),
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
}
