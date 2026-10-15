"""Explicit battle-mode profile13 projection; ordinary P09E stays strict."""
from __future__ import annotations

from copy import deepcopy
import json

from p09e_research_projection import ResearchProjectionSource
from p09d_ammo_projection import canonical
from p09d_ammo_store import require, sha
from game_profile_tx import TransactionError
from p08b_battle_store import POLICY_SHA256, SCHEMA, freeze_loadout, REJECTIONS


def capabilities(catalog, aggregate):
    result = []
    for owned in aggregate["research"]["vehicles"]:
        native = owned["native_id"]
        value = {"native_inventory_id": native, "admission": False, "code": None,
            "kind": {1: "ms1", 2: "is7"}.get(native)}
        try:
            freeze_loadout(catalog, aggregate, native)
            value["admission"] = True
        except TransactionError as error:
            if error.code not in REJECTIONS: raise
            value["code"] = error.code
        result.append(value)
    return result


class BattleProjectionSource(ResearchProjectionSource):
    """LOCK_REASON.ON_ARENA=1; source-audited #717, never fake crew/ammo."""

    def state(self, aggregate, layouts):
        vehicles = aggregate.get("vehicles")
        require(type(vehicles) is list and len(vehicles) == len(aggregate["research"]["vehicles"]), "INVALID_BATTLE_PROJECTION")
        by_id = {r["vehicle_inventory_id"]: r["native_id"] for r in aggregate["research"]["vehicles"]}
        locks = {}
        for row in vehicles:
            require(type(row) is dict and set(row) == {"vehicle_id", "state", "battle_id"}
                and row["vehicle_id"] in by_id, "INVALID_BATTLE_PROJECTION")
            require((row["state"] == "available" and row["battle_id"] is None)
                or (row["state"] == "reserved" and type(row["battle_id"]) is str and 1 <= len(row["battle_id"]) <= 96), "INVALID_BATTLE_PROJECTION")
            if row["state"] == "reserved": locks[by_id[row["vehicle_id"]]] = 1
        require(len({r["vehicle_id"] for r in vehicles}) == len(vehicles) and len(locks) <= 1, "INVALID_BATTLE_PROJECTION")
        # The inherited P04K projector deliberately supports available records
        # only. Reuse its crew/ammo encoder after validating every actual state,
        # then project the independently audited lock map explicitly below.
        plain = deepcopy(aggregate)
        for row in plain["vehicles"]: row.update(state="available", battle_id=None)
        value = super().state(plain, layouts)
        value["inventory"][1]["lock"] = locks
        value["stats"]["battlesTillCaptcha"] = 1
        return value

    def fixture_files(self, profile, aggregate, layouts):
        files = super().fixture_files(profile, aggregate, layouts)
        files["p08b-battle.json"] = canonical({"version": 1, "schema": SCHEMA,
            "policy_sha256": POLICY_SHA256, "account_id": profile["account_id"],
            "native_database_id": profile["native_database_id"], "revision": aggregate["revision"],
            "state_sha256": sha(files["state.bin"]), "capabilities": capabilities(self.catalog, aggregate)})
        return files
