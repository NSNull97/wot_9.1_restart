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
        if status!=200{return Err(invalid("room readiness unavailable; no ready/reserve committed"));}
        let selection=selection::parse_reply(&reply,&request)?;
        Ok(SelectionSnapshot{owner:Arc::new(fresh),fixtures:Arc::new(fixtures),binding,selection})
    }
}
