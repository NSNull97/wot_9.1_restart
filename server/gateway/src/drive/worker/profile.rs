//! P03M homogeneous source profile. Native wire IDs never enter the worker.
use super::*;
use crate::gateway091::shared::vehicle_profile::VehicleKind;

pub(super) const IS7_PROFILE_SHA256:&str="faafa06b92f6d06c1a5f08a07a7f04681e8e24643e940a6263ebc0f0425bc4b6";
const PHYSICS_FIELDS:[&str;11]=["body_half_extents","body_center_offset","wheel_points","mass_kg",
    "max_forward_mps","max_reverse_mps","engine_max_torque_nm","wheel_radius","suspension_min",
    "suspension_max","track_max_brake_torque"];

#[derive(Clone,Debug)]
pub(super) struct VehicleProfile {path:PathBuf,physics:Value}
impl VehicleProfile {
    pub(super) fn load(root:&Path,reference:&Value)->io::Result<Self>{
        fields(reference,&["path","sha256"])?;
        if text(reference,"sha256")?!=IS7_PROFILE_SHA256{return Err(bad());}
        let path=owned(root,Path::new(text(reference,"path")?))?;
        let raw=read(&path,16384)?;
        if format!("{:x}",Sha256::digest(&raw))!=IS7_PROFILE_SHA256{return Err(bad());}
        let v=json(&raw,16384)?;
        fields(&v,&["version","profile","vehicle","revision","sources","physics"])?;
        if uint(&v["version"])?!=1 || text(&v,"profile")?!="test_lab" || text(&v,"vehicle")?!="is7"
            || text(&v,"revision")?!="is7-717-s70-no-optional-six-support-v1" {return Err(bad());}
        fields(&v["physics"],&PHYSICS_FIELDS)?;
        // Exact admitted SHA binds source hashes and all derived numbers/policy.
        // Config projection must still match: a valid profile cannot bless a
        // separately supplied MS1 collider or a mass-only substitution.
        Ok(Self{path,physics:v["physics"].clone()})
    }
    pub(super) fn kind(&self)->VehicleKind{VehicleKind::Is7}
    pub(super) fn verify_map(&self,root:&Path,map:&MapSpec)->io::Result<()>{
        let raw=read(&owned(root,&self.path)?,16384)?;
        if format!("{:x}",Sha256::digest(&raw))!=IS7_PROFILE_SHA256{return Err(bad());}
        let raw=read(&owned(root,&map.config)?,16384)?;
        if format!("{:x}",Sha256::digest(&raw))!=map.config_sha256{return Err(bad());}
        let config=json(&raw,16384)?;
        for field in PHYSICS_FIELDS {if !same_numeric(&config[field],&self.physics[field]){return Err(bad());}}
        if map.mass_kg!=number(&self.physics["mass_kg"],1000.,100000.)? {return Err(bad());}
        Ok(())
    }
}

fn same_numeric(actual:&Value,expected:&Value)->bool{
    match expected {
        Value::Number(_)=>matches!((actual.as_f64(),expected.as_f64()),(Some(a),Some(b))if a.is_finite()&&a==b),
        Value::Array(want)=>actual.as_array().is_some_and(|got|got.len()==want.len()&&got.iter().zip(want).all(|(a,b)|same_numeric(a,b))),
        _=>false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const ADMITTED:&[u8]=include_bytes!("is7-physics-profile.json");
    fn fixture()->(PathBuf,PathBuf,Value){
        let (root,path,mut pool)=super::super::tests::fixture_pool();
        let profile=json(ADMITTED,16384).unwrap();
        let profile_path=root.join("is7-profile.json");fs::write(&profile_path,ADMITTED).unwrap();
        pool["version"]=2.into();pool["vehicle_profile"]=serde_json::json!({"path":profile_path,"sha256":IS7_PROFILE_SHA256});
        for row in pool["maps"].as_array_mut().unwrap(){
            let config_path=Path::new(row["config"].as_str().unwrap());
            let mut c=json(&fs::read(config_path).unwrap(),16384).unwrap();
            for field in PHYSICS_FIELDS{c[field]=profile["physics"][field].clone();}
            let raw=serde_json::to_vec(&c).unwrap();fs::write(config_path,&raw).unwrap();
            row["config_sha256"]=format!("{:x}",Sha256::digest(raw)).into();
        }
        fs::write(&path,serde_json::to_vec(&pool).unwrap()).unwrap();(root,path,pool)
    }
    #[test]fn admitted_source_profile_binds_pool_kind_and_preserves_legacy_kind(){
        assert_eq!(format!("{:x}",Sha256::digest(ADMITTED)),IS7_PROFILE_SHA256);
        let(root,path,_)=fixture();let pool=Pool::load(&root,&path).unwrap();
        assert_eq!(pool.vehicle_kind(),VehicleKind::Is7);assert_eq!(pool.maps[0].mass_kg,68190.);
        let(root,path,_)=super::super::tests::fixture_pool();
        assert_eq!(Pool::load(&root,&path).unwrap().vehicle_kind(),VehicleKind::Ms1);
    }
    #[test]fn every_physics_parameter_rejects_rehashed_config_substitution(){
        for field in PHYSICS_FIELDS {
            let(root,path,mut pool)=fixture();let config_path=PathBuf::from(pool["maps"][0]["config"].as_str().unwrap());
            let mut c=json(&fs::read(&config_path).unwrap(),16384).unwrap();
            match field {
                "body_half_extents"|"body_center_offset"=>c[field][0]=1.into(),
                "wheel_points"=>c[field][5][2]=1.into(),
                "mass_kg"=>c[field]=4691.into(),
                _=>c[field]=(c[field].as_f64().unwrap()+0.01).into(),
            }
            let raw=serde_json::to_vec(&c).unwrap();fs::write(config_path,&raw).unwrap();
            pool["maps"][0]["config_sha256"]=format!("{:x}",Sha256::digest(raw)).into();
            fs::write(&path,serde_json::to_vec(&pool).unwrap()).unwrap();
            assert!(Pool::load(&root,&path).is_err(),"{field}");
        }
    }
    #[test]fn forged_or_stale_profile_and_wrong_version_fail_before_worker_launch(){
        for change in 0..7 {
            let(root,path,mut pool)=fixture();
            let profile_path=PathBuf::from(pool["vehicle_profile"]["path"].as_str().unwrap());
            match change {
                0=>pool["vehicle_profile"]["sha256"]="0".repeat(64).into(),
                1=>{let mut p=json(ADMITTED,16384).unwrap();p["vehicle"]="ms1".into();let raw=serde_json::to_vec(&p).unwrap();fs::write(profile_path,&raw).unwrap();pool["vehicle_profile"]["sha256"]=format!("{:x}",Sha256::digest(raw)).into();},
                2=>{fs::write(profile_path,b"{}").unwrap();},
                3=>pool["version"]=1.into(),
                4=>{pool.as_object_mut().unwrap().remove("vehicle_profile");},
                5=>pool["version"]=3.into(),
                6=>pool["vehicle_profile"]["untrusted_extra"]=true.into(),
                _=>unreachable!(),
            }
            fs::write(&path,serde_json::to_vec(&pool).unwrap()).unwrap();
            assert!(Pool::load(&root,&path).is_err(),"change{change}");
        }
    }
    #[test]fn loaded_profile_is_rechecked_and_wrong_cached_mass_is_rejected(){
        let(root,path,_)=fixture();let pool=Pool::load(&root,&path).unwrap();let profile=pool.vehicle_profile.as_ref().unwrap();
        let mut wrong=pool.maps[0].clone();wrong.mass_kg=4691.;assert!(profile.verify_map(&root,&wrong).is_err());
        fs::write(&profile.path,b"{}").unwrap();assert!(profile.verify_map(&root,&pool.maps[0]).is_err());
    }
    #[test]fn numeric_projection_rejects_bools_missing_points_and_nested_extras(){
        assert!(same_numeric(&serde_json::json!([0,1]),&serde_json::json!([0.0,1.0])));
        for value in [serde_json::json!([false,1]),serde_json::json!([0]),serde_json::json!([0,1,2]),serde_json::json!([[0],1])]{
            assert!(!same_numeric(&value,&serde_json::json!([0,1])));
        }
    }
}
