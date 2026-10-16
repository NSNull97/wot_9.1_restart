//! Fresh source-bound, read-only room selection over the existing private bridge.
//! The caller retains/fences its immutable room/channel origin independently.
use super::*;
use crate::training091::selection::{self,Request,Selection,Stamp};
use std::sync::Arc;

#[derive(Clone)]
pub(crate) struct SelectionSnapshot {
    pub(crate) owner:Arc<Profile>,
    pub(crate) fixtures:Arc<crate::hangar091::Fixtures>,
    pub(crate) binding:crate::ammo_service091::Metadata,
    pub(crate) selection:Selection,
}

/// Metadata belongs to a previously authenticated/configured fixture directory.
/// Never accept a path, source digest or Frozen object from native CMD402.
pub(crate) fn source_binding(owner:&Profile)->io::Result<String>{
    let path=owner.fixture_dir.join("manifest.json").canonicalize()?;
    if !path.starts_with(&owner.fixture_dir){return Err(invalid("room source metadata escaped fixture"));}
    let Bounded::<FIXTURE_METADATA_FIELDS>(manifest)=serde_json::from_slice(&bounded_file(&path,65536)?)
        .map_err(|_|invalid("room source manifest"))?;
    if text(&manifest,"account_id")?!=owner.account_id
        ||manifest.get("native_database_id").and_then(Value::as_i64)!=Some(i64::from(owner.database_id)){
        return Err(invalid("room source owner/native binding"));
    }
    Ok(text(&manifest,"source_bundle_sha256")?.to_owned())
}

impl Config {
    /// Refresh first, then compare to the revision CAPTURED at native receipt.
    /// A garage mutation cannot silently turn the old request into "latest".
    pub(crate) fn select_room_loadout(&self,owner:&Profile,expected_revision:u64,native_inventory_id:u32)
        ->io::Result<SelectionSnapshot>{
        if !self.p06t_mixed_ammo||!self.p04m_pool||!self.profile13_battle
            ||!(13..=i32::MAX as u64).contains(&expected_revision){
            return Err(invalid("room selection requires mixed owned profile13"));
        }
        let captured_source=source_binding(owner)?;
        let fresh=self.refresh_battle_profile(owner)?;
        let binding=crate::ammo_service091::metadata_research(&fresh.fixture_dir,&fresh.account_id,fresh.database_id)?;
        if binding.revision!=expected_revision||binding.wire_revision!=1{
            return Err(invalid("room readiness origin revision became stale"));
        }
        let fixtures=crate::hangar091::Fixtures::load_p04m(&fresh.fixture_dir)?;
        let path=fresh.fixture_dir.join("manifest.json").canonicalize()?;
        if !path.starts_with(&fresh.fixture_dir){return Err(invalid("room source metadata escaped refreshed fixture"));}
        let Bounded::<FIXTURE_METADATA_FIELDS>(manifest)=serde_json::from_slice(&bounded_file(&path,65536)?)
            .map_err(|_|invalid("room refreshed source manifest"))?;
        let owner_source=source_binding(&fresh)?;
        if owner_source!=captured_source{return Err(invalid("room readiness source changed"));}
        let stamp=Stamp{
            native_state_sha256:fixtures.state_sha256().iter().map(|b|format!("{b:02x}")).collect(),
            owner_source_sha256:owner_source,
            catalog_sha256:text(&manifest,"research_catalog_sha256")?.into(),
            pool_registry_sha256:crate::p04m_companion091::REGISTRY_SHA256.into(),
            mixed_policy_sha256:crate::profile13_v2091::POLICY_SHA256.into(),
            shell_catalog_sha256:crate::p06t_shells091::SOURCE_DATA_SHA256.into(),
            terminal_policy_sha256:crate::profile13_v2091::TERMINAL_MANIFEST_SHA256.into(),
        };
        let context=crate::battle091::profile13::Context{
            account_id:owner.account_id.clone(),native_database_id:owner.database_id,
            run_id:self.battle_run_id.clone(),expected_revision,command_key:"p10b:read-only-selection".into(),
        };
        let request=Request::new(&context,native_inventory_id,stamp)?;
        let body=selection::encode_request(&request)?;
        let(status,reply)=self.post_with_budget("/internal/native/room-selection",&body,Duration::from_secs(9),
            selection::MAX_REPLY,selection::MAX_REPLY+4100)?;
        if status!=200{return Err(selection_http_failure(status,&reply));}
        let selection=selection::parse_reply(&reply,&request)?;
        Ok(SelectionSnapshot{owner:Arc::new(fresh),fixtures:Arc::new(fixtures),binding,selection})
    }
}


/// Log only the numeric status and an allowlisted static classification. Never
/// put private HTTP response text, account fields or arbitrary worker errors in
/// native logs. The failed read publishes neither Ready nor a reservation.
fn selection_http_failure(status:u16,raw:&[u8])->io::Error{
    const DENIALS:[&str;13]=["INVALID_INPUT","STALE_REVISION","SOURCE_STAMP_MISMATCH",
        "NATIVE_STATE_STAMP_MISMATCH","RUN_NOT_OPEN","RUN_FENCED","VEHICLE_RESERVED",
        "UNKNOWN_VEHICLE","BATTLE_PROFILE_UNSUPPORTED","OWNER_ACCEPTANCE_REQUIRED",
        "INCOMPLETE_CREW","AMMUNITION_EMPTY","AMMUNITION_UNSUPPORTED"];
    let detail=(||->Option<&'static str>{
        if raw.len()>512{return None;}
        let Bounded::<2>(value)=serde_json::from_slice(raw).ok()?;
        let error=value.get("error")?.as_str()?;
        if status==409&&error=="selection_not_ready"&&value.len()==2{
            let code=value.get("code")?.as_str()?;
            return DENIALS.iter().copied().find(|known|*known==code);
        }
        None
    })().unwrap_or("unclassified");
    io::Error::new(io::ErrorKind::InvalidData,format!(
        "room readiness HTTP status={status} detail={detail}; no ready/reserve committed"))
}

#[cfg(test)]
mod p10b_room_http_diagnostic_tests{
    use super::*;
    #[test]
    fn p10b_room_http_preserves_status_and_all_closed_selection_denials(){
        for code in ["INVALID_INPUT","STALE_REVISION","SOURCE_STAMP_MISMATCH","NATIVE_STATE_STAMP_MISMATCH",
            "RUN_NOT_OPEN","RUN_FENCED","VEHICLE_RESERVED","UNKNOWN_VEHICLE","BATTLE_PROFILE_UNSUPPORTED",
            "OWNER_ACCEPTANCE_REQUIRED","INCOMPLETE_CREW","AMMUNITION_EMPTY","AMMUNITION_UNSUPPORTED"]{
            let raw=format!(r#"{{"error":"selection_not_ready","code":"{code}"}}"#);
            let error=selection_http_failure(409,raw.as_bytes());
            assert_eq!(error.kind(),io::ErrorKind::InvalidData);
            assert_eq!(error.to_string(),format!("room readiness HTTP status=409 detail={code}; no ready/reserve committed"));
        }
    }
    #[test]
    fn p10b_room_http_preserves_status_without_copying_other_response_bodies(){
        for(status,detail)in [(400,"invalid_request"),(403,"forbidden"),(404,"not_found"),
            (413,"invalid_request"),(503,"busy"),(503,"timeout"),(503,"unavailable")]{
            let raw=format!(r#"{{"error":"{detail}"}}"#);
            assert_eq!(selection_http_failure(status,raw.as_bytes()).to_string(),
                format!("room readiness HTTP status={status} detail=unclassified; no ready/reserve committed"));
        }
    }
    #[test]
    fn p10b_room_http_never_logs_arbitrary_private_response_or_ambiguous_json(){
        let poison=[
            br#"{"error":"selection_not_ready","code":"secret-password"}"#.as_slice(),
            br#"{"error":"selection_not_ready","code":"STALE_REVISION","code":"SOURCE_STAMP_MISMATCH"}"#,
            br#"{"error":"selection_not_ready","error":"selection_not_ready","code":"STALE_REVISION"}"#,
            br#"{"error":"selection_not_ready","code":"STALE_REVISION","account_id":"secret-owner"}"#,
            br#"{"error":"forbidden","account_id":"secret-owner"}"#,
            b"<secret-worker-stderr>",
        ];
        for raw in poison{
            assert_eq!(selection_http_failure(409,raw).to_string(),
                "room readiness HTTP status=409 detail=unclassified; no ready/reserve committed");
        }
        let long=vec![b'x';513];assert!(selection_http_failure(503,&long).to_string().contains("detail=unclassified;"));
        assert!(selection_http_failure(503,br#"{"error":"selection_not_ready","code":"STALE_REVISION"}"#)
            .to_string().contains("detail=unclassified;"));
    }
}
