//! Additive loss4 read-only room binding. Never converts a V2 ready proof.
use super::*;
use crate::training091::selection_loss::{self,Request,Selection,Stamp};
use std::sync::Arc;
use sha2::{Digest,Sha256};
#[derive(Clone)]pub(crate) struct SelectionSnapshot{
    pub(crate) owner:Arc<Profile>,pub(crate) fixtures:Arc<crate::hangar091::Fixtures>,
    pub(crate) binding:crate::ammo_service091::Metadata,pub(crate) selection:Selection,
}
impl Config{
    pub(crate) fn select_room_loadout_loss(&self,owner:&Profile,expected_revision:u64,native_inventory_id:u32)->io::Result<SelectionSnapshot>{
        if !self.training_rooms||!self.p06t_ammo_rack_detonation||!self.p06t_mixed_ammo||!self.p04m_pool||!self.profile13_battle
            ||!(13..=i32::MAX as u64).contains(&expected_revision){return Err(invalid("loss room mode/source writer required"));}
        let captured_source=room_selection::source_binding(owner)?;
        let fresh=self.refresh_battle_profile(owner)?; // Already validates exact loss companion.
        let binding=crate::ammo_service091::metadata_research(&fresh.fixture_dir,&fresh.account_id,fresh.database_id)?;
        if binding.revision!=expected_revision||binding.wire_revision!=1{return Err(invalid("loss readiness origin revision became stale"));}
        let fixtures=crate::hangar091::Fixtures::load_p04m(&fresh.fixture_dir)?;
        let root=fresh.fixture_dir.canonicalize()?;
        let read=|name:&str,limit:u64|->io::Result<Vec<u8>>{let p=root.join(name).canonicalize()?;
            if !p.starts_with(&root){return Err(invalid("loss selection fixture escaped root"));}bounded_file(&p,limit)};
        let Bounded::<FIXTURE_METADATA_FIELDS>(manifest)=serde_json::from_slice(&read("manifest.json",65536)?)
            .map_err(|_|invalid("loss selection source manifest"))?;
        let source=room_selection::source_binding(&fresh)?;if source!=captured_source{return Err(invalid("loss selection changed source"));}
        // Hash actual immutable companion bytes; policy/owner/revision/state were
        // checked in Config.refresh_battle_profile, not supplied by CMD402.
        let companion=read("p06t-ammo-loss.json",4096)?;
        let stamp=Stamp{base:crate::training091::selection::Stamp{
            native_state_sha256:fixtures.state_sha256().iter().map(|b|format!("{b:02x}")).collect(),owner_source_sha256:source,
            catalog_sha256:text(&manifest,"research_catalog_sha256")?.into(),pool_registry_sha256:crate::p04m_companion091::REGISTRY_SHA256.into(),
            mixed_policy_sha256:crate::profile13_v2091::POLICY_SHA256.into(),shell_catalog_sha256:crate::p06t_shells091::SOURCE_DATA_SHA256.into(),
            terminal_policy_sha256:crate::profile13_v2091::TERMINAL_MANIFEST_SHA256.into()},loss_policy_sha256:crate::profile13_loss091::POLICY_SHA256.into(),
            loss_companion_sha256:format!("{:x}",Sha256::digest(companion))};
        let c=crate::battle091::profile13::Context{account_id:fresh.account_id.clone(),native_database_id:fresh.database_id,
            run_id:self.battle_run_id.clone(),expected_revision,command_key:"p10b:loss:read-only-selection".into()};
        let request=Request::new(&c,native_inventory_id,stamp)?;let body=selection_loss::encode_request(&request)?;
        let(status,bytes)=self.post_with_budget("/internal/native/room-selection-loss",&body,Duration::from_secs(9),selection_loss::MAX_REPLY,selection_loss::MAX_REPLY+4100)?;
        if status!=200{return Err(http_failure(status,&bytes));}
        let selection=selection_loss::parse_reply(&bytes,&request)?;
        Ok(SelectionSnapshot{owner:Arc::new(fresh),fixtures:Arc::new(fixtures),binding,selection})
    }
}

fn http_failure(status:u16,raw:&[u8])->io::Error{
    const DENIALS:[&str;15]=["INVALID_INPUT","STALE_REVISION","SOURCE_STAMP_MISMATCH","NATIVE_STATE_STAMP_MISMATCH",
        "RUN_NOT_OPEN","RUN_FENCED","VEHICLE_RESERVED","UNKNOWN_VEHICLE","BATTLE_PROFILE_UNSUPPORTED","OWNER_ACCEPTANCE_REQUIRED",
        "INCOMPLETE_CREW","AMMUNITION_EMPTY","AMMUNITION_UNSUPPORTED","AMMO_LOSS_POLICY_REQUIRED","OWNER_CONTRACT_UNSUPPORTED"];
    let detail=(||{if raw.len()>512{return None;}let Bounded::<2>(v)=serde_json::from_slice(raw).ok()?;
        if status!=409||v.len()!=2||v.get("error")?.as_str()?!="selection_not_ready"{return None;}
        let code=v.get("code")?.as_str()?;DENIALS.into_iter().find(|known|*known==code)
    })().unwrap_or("unclassified");
    io::Error::new(io::ErrorKind::InvalidData,format!("loss room readiness HTTP status={status} detail={detail}; no ready/reserve committed"))
}
#[cfg(test)]mod tests{
    use super::*;
    #[test]fn p10b_loss_room_binding_diagnostic_keeps_new_closed_denials(){
        for code in["AMMO_LOSS_POLICY_REQUIRED","OWNER_CONTRACT_UNSUPPORTED","STALE_REVISION"]{
            let raw=format!(r#"{{"error":"selection_not_ready","code":"{code}"}}"#);
            assert_eq!(http_failure(409,raw.as_bytes()).to_string(),format!("loss room readiness HTTP status=409 detail={code}; no ready/reserve committed"));}
    }
    #[test]fn p10b_loss_room_binding_diagnostic_never_copies_unknown_or_duplicate_private_fields(){
        for raw in[br#"{"error":"selection_not_ready","code":"private-password"}"#.as_slice(),
            br#"{"error":"selection_not_ready","code":"STALE_REVISION","code":"AMMO_LOSS_POLICY_REQUIRED"}"#,
            br#"{"error":"selection_not_ready","code":"STALE_REVISION","owner":"private"}"#]{
            assert_eq!(http_failure(409,raw).to_string(),"loss room readiness HTTP status=409 detail=unclassified; no ready/reserve committed");}
        assert!(http_failure(503,b"private-worker-stderr").to_string().contains("status=503 detail=unclassified"));
    }
}
