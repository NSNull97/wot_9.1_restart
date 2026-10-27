//! Closed homogeneous vehicle/handling profiles. Native IDs never enter the worker.
use super::*;
use crate::gateway091::shared::vehicle_profile::VehicleKind;

pub(super) const IS7_PROFILE_SHA256:&str="2fefea06de45fd172894ea7330f59d8efa9f9914a4f88192bb7b5f6ce8d47a90";
const MS1_HANDLING_SHA256:&str="48f8ac675afafbe8605bd97bd92dc2c37f26673b65a548d4f0402b815f7ee9a1";
const IS7_HANDLING_SHA256:&str="2b72923c904678b5471ca4c8e01125f787d0baeb8cf2153c322a126fa1b6cfd7";
const PHYSICS_FIELDS:[&str;14]=["body_half_extents","body_center_offset","wheel_points","mass_kg",
    "max_forward_mps","max_reverse_mps","engine_max_torque_nm","wheel_radius","suspension_min",
    "suspension_max","track_max_brake_torque","longitudinal_friction","lateral_friction","stationary_steering_ratio"];

#[derive(Clone,Debug)]
pub(super) struct VehicleProfile {path:PathBuf,sha256:String,kind:VehicleKind,config_version:u64,physics:Value,handling:Option<Value>}
impl VehicleProfile {
    pub(super) fn load(root:&Path,reference:&Value,pool_version:u64)->io::Result<Self>{
        fields(reference,&["path","sha256"])?;
        let hash=text(reference,"sha256")?;
        if let Some(kind)=VehicleKind::SUPPORTED.into_iter().filter(|kind|if pool_version==4 {kind.is_extended()}else{kind.index()>=2&&!kind.is_extended()})
            .find(|kind|ram_proof::Profile::for_vehicle(*kind).sha()==hash) {
            let extended=kind.is_extended();
            if pool_version!=if extended{4}else{3} {return Err(bad());}
            let path=owned(root,Path::new(text(reference,"path")?))?;
            let raw=read(&path,16384)?;
            if format!("{:x}",Sha256::digest(&raw))!=hash {return Err(bad());}
            let v=json(&raw,16384)?;
            fields(&v,&["version","profile","policy","kind","battle_admission","definition_sha256","definition","native_binding"])?;
            if uint(&v["version"])?!=if extended{2}else{1} || text(&v,"profile")?!="test_lab" || text(&v,"kind")?!=kind.label()
                ||text(&v,"policy")?!=if extended{"p06t-extended-six-support-v2"}else{"p04m-stock-six-support-v1"}||v["battle_admission"]!=false
                ||text(&v["definition"],"kind")?!=kind.label() {return Err(bad());}
            let definition=&v["definition"];fields(&definition["physics"],&PHYSICS_FIELDS)?;
            let handling=&definition["handling"];
            fields(handling,&["version","policy","max_yaw_rate_rad_s"])?;
            if uint(&handling["version"])?!=1||text(handling,"policy")?!="p05b-track-yaw-v1" {return Err(bad());}
            number(&handling["max_yaw_rate_rad_s"],0.1,1.)?;
            let binding=ram_proof::Profile::for_vehicle(kind).binding();let native=&v["native_binding"];
            if uint(&native["inverse_mass_bits"])?!=binding.inverse_mass.to_bits() as u64 {return Err(bad());}
            for (field,want) in [("principal_inverse_bits",binding.principal.to_vec()),("inertia_rotation_bits_xyzw",binding.inertia_rotation.to_vec())] {
                let rows=native[field].as_array().filter(|rows|rows.len()==want.len()).ok_or_else(bad)?;
                for (row,want)in rows.iter().zip(want){if uint(row)?!=want.to_bits() as u64{return Err(bad());}}
            }
            return Ok(Self{path,sha256:hash.into(),kind,config_version:3,physics:definition["physics"].clone(),handling:Some(handling.clone())});
        }
        let (kind,profile_version,revision)=match (pool_version,hash) {
            (2,IS7_PROFILE_SHA256)=>(VehicleKind::Is7,1,"is7-717-s70-no-optional-six-support-traction-v2"),
            (3,MS1_HANDLING_SHA256)=>(VehicleKind::Ms1,2,"p05b-tracked-handling-v1"),
            (3,IS7_HANDLING_SHA256)=>(VehicleKind::Is7,2,"p05b-tracked-handling-v1"),
            _=>return Err(bad()),
        };
        let path=owned(root,Path::new(text(reference,"path")?))?;
        let raw=read(&path,16384)?;
        if format!("{:x}",Sha256::digest(&raw))!=hash{return Err(bad());}
        let v=json(&raw,16384)?;
        let mut names=vec!["version","profile","vehicle","revision","sources","physics"];
        if pool_version==3{names.push("handling");}
        fields(&v,&names)?;
        if uint(&v["version"])?!=profile_version || text(&v,"profile")?!="test_lab" || text(&v,"vehicle")?!=kind.label()
            || text(&v,"revision")?!=revision {return Err(bad());}
        fields(&v["physics"],&PHYSICS_FIELDS)?;
        // Exact admitted SHA binds source hashes and all derived numbers/policy.
        // Config projection must still match: a valid profile cannot bless a
        // separately supplied MS1 collider or a mass-only substitution.
        let handling=if pool_version==3 {
            fields(&v["handling"],&["version","policy","max_yaw_rate_rad_s"])?;
            if uint(&v["handling"]["version"])?!=1 || text(&v["handling"],"policy")?!="p05b-track-yaw-v1" {return Err(bad());}
            number(&v["handling"]["max_yaw_rate_rad_s"],0.1,1.)?;
            Some(v["handling"].clone())
        }else{None};
        Ok(Self{path,sha256:hash.into(),kind,config_version:pool_version,physics:v["physics"].clone(),handling})
    }
    pub(super) fn angular_profile(&self)->io::Result<ram_proof::Profile>{
        let expected=ram_proof::Profile::for_vehicle(self.kind);
        if self.config_version!=3||self.handling.is_none()||self.sha256!=expected.sha(){return Err(bad());}Ok(expected)
    }
    pub(super) fn kind(&self)->VehicleKind{self.kind}
    pub(super) fn shared_source_profile(&self)->Option<(PathBuf,String)> {
        (self.kind.index()>=2).then(||(self.path.clone(),self.sha256.clone()))
    }
    pub(super) fn config_version(&self)->u64{self.config_version}
    pub(super) fn verify_map(&self,root:&Path,map:&MapSpec)->io::Result<()>{
        let raw=read(&owned(root,&self.path)?,16384)?;
        if format!("{:x}",Sha256::digest(&raw))!=self.sha256{return Err(bad());}
        let raw=read(&owned(root,&map.config)?,16384)?;
        if format!("{:x}",Sha256::digest(&raw))!=map.config_sha256{return Err(bad());}
        let config=json(&raw,16384)?;
        if uint(&config["version"])?!=self.config_version{return Err(bad());}
        for field in PHYSICS_FIELDS {if !same_numeric(&config[field],&self.physics[field]){return Err(bad());}}
        if let Some(expected)=&self.handling {
            let actual=&config["handling"];
            fields(actual,&["version","policy","max_yaw_rate_rad_s"])?;
            if uint(&actual["version"])?!=uint(&expected["version"])? || text(actual,"policy")?!=text(expected,"policy")?
                || !same_numeric(&actual["max_yaw_rate_rad_s"],&expected["max_yaw_rate_rad_s"]) {return Err(bad());}
        }
        if map.mass_kg!=number(&self.physics["mass_kg"],1000.,100000.)? {return Err(bad());}
        Ok(())
    }
}

#[cfg(test)]
pub(super) fn component_profile(profile:ram_proof::Profile)->VehicleProfile {
    let (bytes,kind)=match profile{ram_proof::Profile::Ms1=>(include_bytes!("ms1-handling-profile.json").as_slice(),VehicleKind::Ms1),
        ram_proof::Profile::Is7=>(include_bytes!("is7-handling-profile.json").as_slice(),VehicleKind::Is7),
        ram_proof::Profile::T26=>(include_bytes!("p04m-t26-qualified-profile.json").as_slice(),VehicleKind::T26),
        ram_proof::Profile::T34=>(include_bytes!("p04m-t34-qualified-profile.json").as_slice(),VehicleKind::T34),
        ram_proof::Profile::T3485=>(include_bytes!("p04m-t3485-qualified-profile.json").as_slice(),VehicleKind::T3485),
        ram_proof::Profile::WtE100128|ram_proof::Profile::Fv215b183|ram_proof::Profile::Generated(_)=>panic!("physical-only profile has no legacy owned VehicleProfile")};
    assert_eq!(format!("{:x}",Sha256::digest(bytes)),profile.sha());let v=json(bytes,16384).unwrap();
    let definition=if kind.index()>=2{&v["definition"]}else{&v};
    VehicleProfile{path:PathBuf::new(),sha256:profile.sha().into(),kind,config_version:3,physics:definition["physics"].clone(),handling:Some(definition["handling"].clone())}
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
    const MS1_HANDLING:&[u8]=include_bytes!("ms1-handling-profile.json");
    const IS7_HANDLING:&[u8]=include_bytes!("is7-handling-profile.json");
    fn fixture()->(PathBuf,PathBuf,Value){
        let (root,path,mut pool)=super::super::tests::fixture_pool();
        let profile=json(ADMITTED,16384).unwrap();
        let profile_path=root.join("is7-profile.json");fs::write(&profile_path,ADMITTED).unwrap();
        pool["version"]=2.into();pool["vehicle_profile"]=serde_json::json!({"path":profile_path,"sha256":IS7_PROFILE_SHA256});
        for row in pool["maps"].as_array_mut().unwrap(){
            let config_path=Path::new(row["config"].as_str().unwrap());
            let mut c=json(&fs::read(config_path).unwrap(),16384).unwrap();
            c["version"]=2.into();
            for field in PHYSICS_FIELDS{c[field]=profile["physics"][field].clone();}
            let raw=serde_json::to_vec(&c).unwrap();fs::write(config_path,&raw).unwrap();
            row["config_sha256"]=format!("{:x}",Sha256::digest(raw)).into();
        }
        fs::write(&path,serde_json::to_vec(&pool).unwrap()).unwrap();(root,path,pool)
    }
    fn handling_fixture(kind:VehicleKind)->(PathBuf,PathBuf,Value){
        let(root,path,mut pool)=super::super::tests::fixture_pool();
        let(raw,hash)=match kind{VehicleKind::Ms1=>(MS1_HANDLING,MS1_HANDLING_SHA256),VehicleKind::Is7=>(IS7_HANDLING,IS7_HANDLING_SHA256),
            VehicleKind::T26|VehicleKind::T34|VehicleKind::T3485|VehicleKind::Wt128|VehicleKind::Fv183|VehicleKind::Generated(_)=>panic!("legacy profile schema fixture; use curated profile gates")};
        assert_eq!(format!("{:x}",Sha256::digest(raw)),hash);
        let profile=json(raw,16384).unwrap();let profile_path=root.join("handling-profile.json");
        fs::write(&profile_path,raw).unwrap();pool["version"]=3.into();
        pool["vehicle_profile"]=serde_json::json!({"path":profile_path,"sha256":hash});
        for row in pool["maps"].as_array_mut().unwrap(){
            let config_path=Path::new(row["config"].as_str().unwrap());
            let mut c=json(&fs::read(config_path).unwrap(),16384).unwrap();c["version"]=3.into();
            for field in PHYSICS_FIELDS{c[field]=profile["physics"][field].clone();}
            c["handling"]=profile["handling"].clone();
            let raw=serde_json::to_vec(&c).unwrap();fs::write(config_path,&raw).unwrap();
            row["config_sha256"]=format!("{:x}",Sha256::digest(raw)).into();
        }
        fs::write(&path,serde_json::to_vec(&pool).unwrap()).unwrap();(root,path,pool)
    }
    fn replace_config(pool:&mut Value,config:&Value){
        let path=PathBuf::from(pool["maps"][0]["config"].as_str().unwrap());
        let raw=serde_json::to_vec(config).unwrap();fs::write(path,&raw).unwrap();
        pool["maps"][0]["config_sha256"]=format!("{:x}",Sha256::digest(raw)).into();
    }
    #[test]fn both_p05b_profiles_bind_exact_vehicle_and_preserve_legacy_sources(){
        for(kind,mass)in [(VehicleKind::Ms1,4691.),(VehicleKind::Is7,68190.)]{
            let(root,path,_)=handling_fixture(kind);let pool=Pool::load(&root,&path).unwrap();
            assert_eq!(pool.vehicle_kind(),kind);assert_eq!(pool.maps[0].mass_kg,mass);
            let p=pool.vehicle_profile.as_ref().unwrap();assert_eq!(p.config_version(),3);
            assert_eq!(p.physics["lateral_friction"].as_f64(),Some(1.));
            for map in &pool.maps{p.verify_map(&root,map).unwrap();}
        }
        let(root,path,_)=fixture();assert_eq!(Pool::load(&root,&path).unwrap().vehicle_profile.unwrap().config_version(),2);
    }
    #[test]fn p05b_projection_rejects_every_physics_substitution_for_both_masses(){
        for kind in [VehicleKind::Ms1,VehicleKind::Is7]{for field in PHYSICS_FIELDS{
            let(root,path,mut pool)=handling_fixture(kind);
            let mut c=json(&fs::read(pool["maps"][0]["config"].as_str().unwrap()).unwrap(),16384).unwrap();
            match field{
                "body_half_extents"|"body_center_offset"=>c[field][0]=(c[field][0].as_f64().unwrap()+0.01).into(),
                "wheel_points"=>c[field][5][2]=(c[field][5][2].as_f64().unwrap()+0.01).into(),
                _=>c[field]=(c[field].as_f64().unwrap()+0.01).into(),
            }
            replace_config(&mut pool,&c);fs::write(&path,serde_json::to_vec(&pool).unwrap()).unwrap();
            assert!(Pool::load(&root,&path).is_err(),"{kind:?} {field}");
        }}
    }
    #[test]fn p05b_handling_config_rejects_missing_forged_or_cross_vehicle_policy(){
        for kind in [VehicleKind::Ms1,VehicleKind::Is7]{for change in 0..10{
            let(root,path,mut pool)=handling_fixture(kind);
            let mut c=json(&fs::read(pool["maps"][0]["config"].as_str().unwrap()).unwrap(),16384).unwrap();
            match change{
                0=>{c.as_object_mut().unwrap().remove("handling");},
                1=>c["version"]=2.into(),
                2=>c["handling"]["version"]=2.into(),
                3=>c["handling"]["version"]=true.into(),
                4=>c["handling"]["policy"]="other-policy".into(),
                5=>c["handling"]["max_yaw_rate_rad_s"]=0.5.into(),
                6=>c["handling"]["max_yaw_rate_rad_s"]=true.into(),
                7=>c["handling"]["untrusted_extra"]=1.into(),
                8=>{c["handling"].as_object_mut().unwrap().remove("policy");},
                9=>{let other=if kind==VehicleKind::Ms1{IS7_HANDLING}else{MS1_HANDLING};
                    c["handling"]=json(other,16384).unwrap()["handling"].clone();},
                _=>unreachable!(),
            }
            replace_config(&mut pool,&c);fs::write(&path,serde_json::to_vec(&pool).unwrap()).unwrap();
            assert!(Pool::load(&root,&path).is_err(),"{kind:?} handling{change}");
        }}
    }
    #[test]fn p05b_pool_cannot_relabel_legacy_profiles_or_foreign_mass(){
        for change in 0..7{
            let(root,path,mut pool)=handling_fixture(VehicleKind::Ms1);
            let profile_path=PathBuf::from(pool["vehicle_profile"]["path"].as_str().unwrap());
            match change{
                0=>pool["version"]=2.into(),
                1=>{pool["version"]=1.into();pool.as_object_mut().unwrap().remove("vehicle_profile");},
                2=>{fs::write(&profile_path,ADMITTED).unwrap();pool["vehicle_profile"]["sha256"]=IS7_PROFILE_SHA256.into();},
                3=>{fs::write(&profile_path,IS7_HANDLING).unwrap();pool["vehicle_profile"]["sha256"]=IS7_HANDLING_SHA256.into();},
                4=>{let mut p=json(MS1_HANDLING,16384).unwrap();p["vehicle"]="is7".into();
                    let raw=serde_json::to_vec(&p).unwrap();fs::write(profile_path,&raw).unwrap();pool["vehicle_profile"]["sha256"]=format!("{:x}",Sha256::digest(raw)).into();},
                5=>pool["vehicle_profile"]["extra"]=1.into(),
                6=>{let mut c=json(&fs::read(pool["maps"][0]["config"].as_str().unwrap()).unwrap(),16384).unwrap();
                    c["mass_kg"]=68190.into();replace_config(&mut pool,&c);},
                _=>unreachable!(),
            }
            fs::write(&path,serde_json::to_vec(&pool).unwrap()).unwrap();assert!(Pool::load(&root,&path).is_err(),"mix{change}");
        }
    }
    #[test]fn loaded_p05b_profile_is_rechecked_before_launch(){
        for kind in [VehicleKind::Ms1,VehicleKind::Is7]{
            let(root,path,_)=handling_fixture(kind);let pool=Pool::load(&root,&path).unwrap();
            let profile=pool.vehicle_profile.as_ref().unwrap();fs::write(&profile.path,b"{}").unwrap();
            assert!(profile.verify_map(&root,&pool.maps[0]).is_err());
        }
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
    #[test]fn versioned_traction_cannot_enter_legacy_pool_or_omit_policy_fields(){
        for change in 0..5 {
            let(root,path,mut pool)=fixture();
            let config_path=PathBuf::from(pool["maps"][0]["config"].as_str().unwrap());
            let mut c=json(&fs::read(&config_path).unwrap(),16384).unwrap();
            match change {
                0=>{pool["version"]=1.into();pool.as_object_mut().unwrap().remove("vehicle_profile");},
                1=>{c["version"]=1.into();for field in ["longitudinal_friction","lateral_friction","stationary_steering_ratio"]{c.as_object_mut().unwrap().remove(field);}},
                2=>{c.as_object_mut().unwrap().remove("stationary_steering_ratio");},
                3=>c["lateral_friction"]=0.into(),
                4=>c["stationary_steering_ratio"]=true.into(),
                _=>unreachable!(),
            }
            let raw=serde_json::to_vec(&c).unwrap();fs::write(config_path,&raw).unwrap();
            pool["maps"][0]["config_sha256"]=format!("{:x}",Sha256::digest(raw)).into();
            fs::write(&path,serde_json::to_vec(&pool).unwrap()).unwrap();
            assert!(Pool::load(&root,&path).is_err(),"traction change{change}");
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

#[cfg(test)]
#[path="p06t_extended_pool_tests.rs"]
mod extended_tests;
