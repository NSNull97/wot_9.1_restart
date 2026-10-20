//! Child of actual account::identity. Explicit v5 route, no v4 reply retagging.
use super::*;
use crate::{profile13_hold091 as codec,profile13_hold_projection091 as projection};

pub(crate) struct HoldLogin{pub(crate) reservation:Option<codec::Reservation>,pub(crate) projection:projection::Binding,pub(crate) reply:codec::Reply}

pub(super) fn hold_projection(owner:&Profile,revision:u64,state_sha:&str)->io::Result<projection::Binding>{
    let root=owner.fixture_dir.canonicalize()?;
    let file=root.join("p08b-owner-hold.json").canonicalize()?;
    if !file.starts_with(&root){return Err(invalid("owner hold5 companion escapes actual fixture"));}
    projection::parse(&bounded_file(&file,4096)?,&owner.account_id,owner.database_id,revision,state_sha)
}

#[cfg(test)]
mod tests{
    use super::*;
    #[test]fn p08b_hold5_config_explicit_policy_and_training_four_fence(){
        let root=Path::new(env!("CARGO_MANIFEST_DIR")).join("../../local/test-runs").join(format!("hold5-config-{}-{}",std::process::id(),std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos()));
        fs::create_dir_all(&root).unwrap();let root=root.canonicalize().unwrap();fs::write(root.join("token"),"a".repeat(43)).unwrap();
        let mut value=serde_json::json!({"login_bind":"127.0.0.1:26001","base_bind":"127.0.0.1:26002","identity_endpoint":"127.0.0.1:26003","identity_token_file":root.join("token"),"local_root":root,"session_duration_seconds":600});
        for name in["ammunition_service","crew_service","crew_transfer","crew_cross_vehicle","crew_roster_recruitment","crew_progression","crew_dismissal","crew_barracks_recruitment","research_service","profile13_battle","p04m_pool","p06t_mixed_ammo","visibility_v1","p06t_ammo_rack_detonation"]{value[name]=true.into();}
        let path=root.join("config.json");let load=|v:&Value|{fs::write(&path,serde_json::to_vec(v).unwrap()).unwrap();Config::load(path.to_str().unwrap())};
        assert!(!load(&value).unwrap().p08b_owner_battle_hold);value["p08b_owner_battle_hold"]=true.into();assert!(load(&value).unwrap().p08b_owner_battle_hold);
        for key in["profile13_battle","p04m_pool","p06t_mixed_ammo","visibility_v1","p06t_ammo_rack_detonation"]{let mut bad=value.clone();bad[key]=false.into();assert!(load(&bad).is_err(),"{key}");}
        for bad in[Value::Null,1.into(),"true".into()]{let mut v=value.clone();v["p08b_owner_battle_hold"]=bad;assert!(load(&v).is_err());}
        let mut training=value.clone();training["training_rooms"]=true.into();training["battle_players"]=6.into();assert!(load(&training).is_err());
        let mut late=value.clone();late["p08c_late_results"]=true.into();late["p08c_late_results_accounts"]=serde_json::json!(["80ad3bc2-476e-4fbd-899d-a4679ea167d2"]);assert!(load(&late).is_err());
        let mut raw=serde_json::to_vec(&value).unwrap();raw.pop();raw.extend(b",\"p08b_owner_battle_hold\":false}");fs::write(&path,raw).unwrap();assert!(Config::load(path.to_str().unwrap()).is_err());
    }
    #[test]fn p08b_hold5_net_full27_config_keeps_typed_nested_duplicates_and_request16_boundary(){
        let(path,mut value)=super::super::net02_config_tests::fixture();
        value["training_rooms"]=false.into();value["p06t_ammo_rack_detonation"]=true.into();value["p08c_late_results"]=false.into();
        value["p08c_late_results_accounts"]=serde_json::json!([]);value["p08c_late_notice_experimental"]=false.into();value["p08b_owner_battle_hold"]=true.into();
        assert_eq!(value.as_object().unwrap().len(),27);fs::write(&path,serde_json::to_vec(&value).unwrap()).unwrap();
        let c=Config::load(path.to_str().unwrap()).unwrap();assert!(c.p08b_owner_battle_hold&&c.p06t_ammo_rack_detonation&&c.game_network().is_lan());
        assert!(!c.training_rooms&&!c.p08c_late_results);assert_eq!(REQUEST_FIELDS,16);assert_eq!(c.identity_endpoint.to_string(),"127.0.0.1:3491");
        c.require_game_network(game_network::Runtime::SharedOwnedProfile13).unwrap();
        let raw=serde_json::to_string(&value).unwrap();let poison=raw.replacen(r#""game_network":{"#,r#""game_network":{"mode":"lan_test","#,1);
        assert_ne!(raw,poison);fs::write(&path,poison).unwrap();assert!(Config::load(path.to_str().unwrap()).is_err());
        let mut duplicate=raw;duplicate.pop();duplicate.push_str(",\"p08b_owner_battle_hold\":false}");fs::write(&path,duplicate).unwrap();assert!(Config::load(path.to_str().unwrap()).is_err());
    }
}
pub(super) fn verify_hold_projection(owner:&Profile,revision:u64)->io::Result<()> {
    use sha2::{Digest,Sha256};
    let root=owner.fixture_dir.canonicalize()?;
    let state=root.join("state.bin").canonicalize()?;
    if !state.starts_with(&root){return Err(invalid("owner hold5 state escapes actual fixture"));}
    let raw=bounded_file(&state,crate::research_service091::MAX_STATE_BYTES as u64)?;
    hold_projection(owner,revision,&format!("{:x}",Sha256::digest(raw)))?;Ok(())
}
impl Config{
    /// Called in the actual credential worker after its real RunOpen5 and
    /// trusted profile publication. It carries current Active5 explicitly to
    /// Session creation; a fixture lock shape alone never creates a receipt.
    pub(crate) fn inspect_hold_login(&self,owner:&Profile,fixtures:&crate::hangar091::Fixtures,binding:crate::ammo_service091::Metadata)->io::Result<Option<HoldLogin>>{
        if !self.p08b_owner_battle_hold{return Ok(None);}
        let c=codec::Context{account_id:owner.account_id.clone(),native_database_id:owner.database_id,
            command_key:format!("hold5:login-inspect:{}:{}",owner.database_id,binding.revision),expected_revision:0,run_id:self.battle_run_id.clone()};
        let r=self.service_battle_hold(owner,&c,&codec::Request::Inspect)?;
        if r.status!=codec::Status::Inspected||r.revision!=binding.revision||r.replayed{return Err(invalid("hold5 login/current inspected projection"));}
        let sha=fixtures.state_sha256().iter().map(|b|format!("{b:02x}")).collect::<String>();
        let projection=self.hold_binding(owner,binding.revision,&sha)?;
        if let Some(active)=&r.reservation{
            if active.run_id!=self.battle_run_id{return Err(invalid("hold5 login foreign run cannot restore authority"));}
            projection.layout_for(&active.frozen,active.frozen.loss().base.counts())?;
        }
        Ok(Some(HoldLogin{reservation:r.reservation.clone(),projection,reply:r}))
    }
    pub(crate) fn service_battle_hold(&self,owner:&Profile,context:&codec::Context,request:&codec::Request)->io::Result<codec::Reply>{
        if !self.p08b_owner_battle_hold||!self.p06t_ammo_rack_detonation||!self.p06t_mixed_ammo||!self.visibility_v1||!self.p04m_pool||!self.profile13_battle
            ||context.account_id!=owner.account_id||context.native_database_id!=owner.database_id||context.run_id!=self.battle_run_id{
            return Err(invalid("hold5 authenticated owner/current run/explicit opt-in"));}
        let body=codec::encode_request(context,request)?;
        let(status,raw)=self.post_with_budget("/internal/native/battle",&body,Duration::from_secs(20),65536,65536+4100)?;
        if status!=200{return Err(invalid("owner hold5 worker unavailable; immutable operation retained"));}
        codec::parse_reply(&raw,context,request)
    }
    pub(crate) fn hold_binding(&self,owner:&Profile,revision:u64,state_sha:&str)->io::Result<projection::Binding>{
        if !self.p08b_owner_battle_hold{return Err(invalid("hold5 companion requires explicit gateway mode"));}
        hold_projection(owner,revision,state_sha)
    }
    pub(crate) fn results_post_hold(&self,owner:&Profile,body:&[u8])->io::Result<Vec<u8>>{
        if !self.p08b_owner_battle_hold||!self.p06t_ammo_rack_detonation||!self.profile13_battle||owner.database_id<=0||body.is_empty()||body.len()>2048{
            return Err(invalid("hold5 results explicit mode/body bound"));}
        let(status,raw)=self.post_with_budget("/internal/native/battle-results",body,Duration::from_secs(20),65536,65536+4100)?;
        if status!=200{return Err(invalid("hold5 results worker unavailable; immutable task retained"));}Ok(raw)
    }
}
