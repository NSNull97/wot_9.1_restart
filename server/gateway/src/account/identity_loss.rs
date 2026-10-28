//! Opt-in loss-v1 transport. Existing v2 projections remain byte-for-byte v2.
use super::*;
use crate::profile13_loss091 as codec;

fn projection_bytes(raw:&[u8],owner:&Profile,revision:u64,state_sha:&str)->io::Result<()> {
    let value=crate::profile13_v2091::bounded_json(raw,4096)?;
    let keys=["version","contract","policy_sha256","base_policy_sha256","account_id","native_database_id","revision","state_sha256"];
    if value.as_object().is_none_or(|m|m.len()!=keys.len()||keys.iter().any(|k|!m.contains_key(*k)))
        ||value["version"]!=4||value["contract"]!=codec::CONTRACT||value["policy_sha256"]!=codec::POLICY_SHA256
        ||value["base_policy_sha256"]!=crate::profile13_v2091::POLICY_SHA256
        ||value["account_id"]!=owner.account_id||value["native_database_id"].as_i64()!=Some(owner.database_id as i64)
        ||value["revision"].as_u64()!=Some(revision)||value["state_sha256"]!=state_sha{
        return Err(invalid("ammo-loss projection closed policy/identity/revision/state"));
    }Ok(())
}
pub(super) fn verify_loss_projection(owner:&Profile,revision:u64)->io::Result<()> {
    use sha2::{Digest,Sha256};
    let root=owner.fixture_dir.canonicalize()?;
    let read=|name:&str,max:u64|->io::Result<Vec<u8>>{
        let path=root.join(name).canonicalize()?;
        if !path.starts_with(&root){return Err(invalid("ammo-loss projection escapes fixture"));}
        bounded_file(&path,max)
    };
    let state=read("state.bin",crate::research_service091::MAX_STATE_BYTES as u64)?;
    projection_bytes(&read("p06t-ammo-loss.json",4096)?,owner,revision,&format!("{:x}",Sha256::digest(state)))
}
impl Config {
    pub(crate) fn service_battle_loss(&self,owner:&Profile,context:&crate::battle091::profile13::Context,request:&codec::Request)->io::Result<codec::Reply>{
        if self.p08b_owner_battle_hold||!self.p06t_ammo_rack_detonation||!self.p06t_mixed_ammo||!self.visibility_v1||!self.p04m_pool||!self.profile13_battle
            ||context.account_id!=owner.account_id||context.native_database_id!=owner.database_id||context.run_id!=self.battle_run_id{
            return Err(invalid("ammo-loss authenticated owner/run/opt-in"));
        }
        let body=codec::encode_request(context,request)?;
        let(status,bytes)=self.post_with_budget("/internal/native/battle",&body,Duration::from_secs(20),65536,16384+4100)?;
        if status!=200{return Err(invalid("ammo-loss writer unavailable; immutable outcome retained"));}
        codec::parse_reply(&bytes,context,request)
    }
    pub(crate) fn results_post_loss(&self,owner:&Profile,body:&[u8])->io::Result<Vec<u8>>{
        if self.p08b_owner_battle_hold||!self.p06t_ammo_rack_detonation||!self.p06t_mixed_ammo||!self.profile13_battle||owner.database_id<=0
            ||body.is_empty()||body.len()>2048{return Err(invalid("ammo-loss result mode/body bound"));}
        const RESULT:usize=crate::gateway091::shared::lifecycle_wire::MAX_RESULT_REQUEST;
        let(status,reply)=self.post_with_budget("/internal/native/battle-results",body,Duration::from_secs(20),RESULT,RESULT+4100)?;
        if status!=200{return Err(invalid("ammo-loss result writer unavailable; immutable task retained"));}Ok(reply)
    }
}

#[cfg(test)]
mod tests{
    use super::*;
    #[test]fn p06t_loss_companion_binds_exact_owner_revision_state_and_version(){
        let owner=Profile{account_id:"12345678-1234-4234-8234-123456789abc".into(),database_id:1,name:"loss-test".into(),fixture_dir:PathBuf::new()};
        let value=serde_json::json!({"version":4,"contract":codec::CONTRACT,"policy_sha256":codec::POLICY_SHA256,
            "base_policy_sha256":crate::profile13_v2091::POLICY_SHA256,"account_id":owner.account_id,"native_database_id":1,"revision":14,"state_sha256":"a".repeat(64)});
        let bytes=serde_json::to_vec(&value).unwrap();projection_bytes(&bytes,&owner,14,&"a".repeat(64)).unwrap();
        for(key,badvalue)in[("version",Value::from(2)),("contract",Value::from("mixed-v2")),("revision",Value::from(15)),
            ("native_database_id",Value::from(2)),("policy_sha256",Value::from(crate::profile13_v2091::POLICY_SHA256)),("state_sha256",Value::from("b".repeat(64)))]{
            let mut wrong=value.clone();wrong[key]=badvalue;assert!(projection_bytes(&serde_json::to_vec(&wrong).unwrap(),&owner,14,&"a".repeat(64)).is_err(),"{key}");
        }
        let mut extra=value.clone();extra["ignored"]=Value::Null;assert!(projection_bytes(&serde_json::to_vec(&extra).unwrap(),&owner,14,&"a".repeat(64)).is_err());
        let duplicate=String::from_utf8(bytes).unwrap().replacen("{","{\"version\":4,",1);
        assert!(projection_bytes(duplicate.as_bytes(),&owner,14,&"a".repeat(64)).is_err());
    }
    #[test]fn p06t_loss_config_is_explicit_and_requires_mixed_visibility_and_writer(){
        let stamp=std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs").join(format!("p06t-loss-config-{stamp}"));
        fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();fs::write(root.join("token"),"a".repeat(43)).unwrap();
        let mut v=serde_json::json!({"login_bind":"127.0.0.1:26001","base_bind":"127.0.0.1:26002","identity_endpoint":"127.0.0.1:26003",
            "identity_token_file":root.join("token"),"local_root":root,"session_duration_seconds":600});
        for name in["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression",
            "crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle","p04m_pool","p06t_mixed_ammo","visibility_v1"]{v[name]=true.into();}
        let path=root.join("gateway.json");let load=|v:&Value|{fs::write(&path,serde_json::to_vec(v).unwrap()).unwrap();Config::load(path.to_str().unwrap())};
        assert!(!load(&v).unwrap().p06t_ammo_rack_detonation);v["p06t_ammo_rack_detonation"]=true.into();assert!(load(&v).unwrap().p06t_ammo_rack_detonation);
        for name in["visibility_v1","p06t_mixed_ammo","p04m_pool","profile13_battle","research_service"]{let mut wrong=v.clone();wrong[name]=false.into();assert!(load(&wrong).is_err(),"{name}");}
        for value in[Value::Null,Value::from(1),Value::from("true")]{let mut wrong=v.clone();wrong["p06t_ammo_rack_detonation"]=value;assert!(load(&wrong).is_err());}
    }
}
