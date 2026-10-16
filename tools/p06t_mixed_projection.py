"""Staged opt-in companion; source-bound existing profile payloads stay intact."""
from copy import deepcopy
from p08b_battle_projection import BattleProjectionSource
from p04m_pool_projection import PoolProjectionSource
from p08b_battle_store import BattleStore
from p09d_ammo_projection import canonical
from p09d_ammo_store import sha, require
from game_profile_tx import TransactionError
from p06t_mixed_store import SCHEMA, POLICY_SHA256, SOURCE_SHA256, REJECTIONS


class MixedProjectionSource(BattleProjectionSource):
    def __init__(self, source, store):
        require(isinstance(source,BattleProjectionSource) and store.mixed_active(),"P06T_PROJECTION_REQUIRED")
        self.__dict__.update(source.__dict__)
        self._mixed_base,self._mixed_store=source,store

    def state(self,aggregate,layouts):return self._mixed_base.state(aggregate,layouts)

    def fixture_files(self,profile,aggregate,layouts):
        files=self._mixed_base.fixture_files(profile,aggregate,layouts)
        caps=[]
        for owned in aggregate["research"]["vehicles"]:
            known=self._mixed_store.registry.by_vehicle.get(owned["vehicle_id"])
            entry=dict(native_inventory_id=owned["native_id"],kind=known.kind if known else None,admission=False,code="BATTLE_PROFILE_UNSUPPORTED")
            try:
                self._mixed_store.freeze_mixed(aggregate,owned["native_id"]);entry.update(admission=True,code=None)
            except TransactionError as error:
                if error.code not in REJECTIONS:raise
                entry["code"]=error.code
            caps.append(entry)
        files["p06t-ammunition.json"]=canonical(dict(version=2,schema=SCHEMA,policy_sha256=POLICY_SHA256,
            shell_catalog_sha256=SOURCE_SHA256,account_id=profile["account_id"],native_database_id=profile["native_database_id"],
            revision=aggregate["revision"],state_sha256=sha(files["state.bin"]),max_stacks=3,capabilities=caps))
        require(len(files["p06t-ammunition.json"])<=65536,"PROFILE_TOO_LARGE")
        return files


def publish_mixed(store,source,account_id,fixture_root):
    """Candidate adapter hook; never enabled by old/default publication."""
    from pathlib import Path
    if store.pool_active() and not isinstance(source,PoolProjectionSource):source=PoolProjectionSource(source,store)
    source=MixedProjectionSource(source,store)
    return BattleStore.publish(store,source,account_id,Path(fixture_root)/"p06t-v2")
