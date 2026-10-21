"""Opt-in full native projection from actual PoolStore crew/ammo rows only."""
from copy import deepcopy
import json

from p09d_ammo_store import require, sha
from p09d_ammo_projection import canonical, encode
from p09c_ammo_catalog import MOUNTS
from p09e_research_projection import garage_record, shop_tree, elite_ids, item_cd, MAX_STATE, MAX_SHOP, MAX_NODES
from p08b_battle_projection import BattleProjectionSource, capabilities as legacy_capabilities
from p08b_battle_store import POLICY_SHA256 as LEGACY_BATTLE_POLICY, SCHEMA as LEGACY_BATTLE_SCHEMA
from p04m_stock_registry import SCHEMA, DEFINITION_SHA256
from p04m_pool_crew import native_crew, contract_for_crew
from p04m_pool_store import POLICY_SHA256


class PoolProjectionSource(BattleProjectionSource):
    def __init__(self, source, store):
        require(isinstance(source, BattleProjectionSource) and store.pool_active(), "P04M_PROJECTION_REQUIRED")
        self.__dict__.update(source.__dict__)
        self._pool_base = source
        self._pool_snapshot, self._pool_profile = store._baseline(store._pool_row())
        self.registry, self.shells, self.mounts = store.registry, store.shells, store.mounts
        self.ammo_catalog_sha256 = store.ammo_catalog_sha256
        self._zero_gold = store.zero_economy(self._pool_profile["account_id"])

    def state(self, aggregate, layouts):
        require(aggregate["account_id"] == self._pool_profile["account_id"], "FOREIGN_ACCOUNT")
        state = deepcopy(self.trees["state.bin"]); state["rev"] = 1
        research, inventory = aggregate["research"], state["inventory"]
        crew_inventory, crews = native_crew(aggregate["crew_inventory"], contract_for_crew(aggregate["crew_inventory"]))
        inventory[8] = crew_inventory
        inventory[10] = {self.shells[key].native_compact_id: n for key, n in aggregate["depot"].items()}
        for kind in range(2, 8):
            inventory[kind] = {item_cd(self.catalog, key): n for key, n in research["depot"].items()
                if self.catalog.modules[key]["native_compact_id"] & 15 == kind}
        owned_by_id = {r["vehicle_inventory_id"]: r for r in research["vehicles"]}
        require(len(owned_by_id) == len(research["vehicles"]), "CORRUPT_STORE")
        records = {r["native_id"]: garage_record(self.catalog, r) for r in research["vehicles"]}
        for native, record in records.items():
            if native in crews: record["crew"] = crews[native]
        for ammo in aggregate["ammunition"]:
            owned = owned_by_id[ammo["vehicle_id"]]; native = owned["native_id"]
            p = self.registry.by_vehicle[owned["vehicle_id"]]
            if any(owned["modules"][role] != dict(p.modules)[role] for role in ("turret", "gun")):
                require(not any(ammo["loaded"].values()), "AMMUNITION_CONFIGURATION_UNSUPPORTED")
                continue
            mount = self.mounts[ammo["mount_id"]]; layout = layouts[native]
            records[native]["shells"] = [n if i % 2 else abs(n) for i, n in enumerate(layout)]
            records[native]["shellsLayout"] = {(mount.turret_native_compact_id, mount.gun_native_compact_id): layout}
        fields = tuple(next(iter(records.values())))
        inventory[1] = {field: {native: record[field] for native, record in records.items()} for field in fields}
        locks = {}
        for row in aggregate["vehicles"]:
            require(row["vehicle_id"] in owned_by_id, "CORRUPT_STORE")
            require((row["state"] == "available" and row["battle_id"] is None)
                or (row["state"] == "reserved" and type(row["battle_id"]) is str and 1 <= len(row["battle_id"]) <= 96), "CORRUPT_STORE")
            if row["state"] == "reserved": locks[owned_by_id[row["vehicle_id"]]["native_id"]] = 1
        require(len(locks) <= 1 and len(aggregate["vehicles"]) == len(owned_by_id), "CORRUPT_STORE")
        inventory[1]["lock"] = locks
        stats = state["stats"]
        stats.update(unlocks=sorted(item_cd(self.catalog, key) for key in research["unlocked"]),
            eliteVehicles=sorted(elite_ids(self.catalog, research["unlocked"])), slots=research["garage_slots"],
            freeVehiclesLeft=research["garage_slots"] - len(research["vehicles"]),
            freeTMenLeft=aggregate["crew_inventory"]["free_recruitment_left"], battlesTillCaptcha=1)
        for row in research["vehicles"]: stats["vehTypeXP"].setdefault(item_cd(self.catalog, row["vehicle_id"]), 0)
        return state

    def fixture_files(self, profile, aggregate, layouts):
        # Frozen legacy builders validate their original baseline. Their source
        # bytes/proof remain intact; every current payload is replaced below.
        baseline_layouts = {}
        by_id = {r["vehicle_inventory_id"]: r["native_id"] for r in self._pool_snapshot["research"]["vehicles"]}
        for row in self._pool_snapshot["ammunition"]:
            mount = MOUNTS[row["mount_id"]]
            from p09c_ammo_catalog import SHELLS
            baseline_layouts[by_id[row["vehicle_id"]]] = [n for key in mount.shell_ids for n in (SHELLS[key].native_compact_id, row["loaded"][key])]
        files = self._pool_base.fixture_files(self._pool_profile, self._pool_snapshot, baseline_layouts)
        files["state.bin"] = encode(self.state(aggregate, layouts), MAX_STATE, max_nodes=MAX_NODES)
        files["shop.bin"] = encode(shop_tree(self.catalog, self.trees["shop.bin"], zero_gold=self._zero_gold), MAX_SHOP, max_nodes=MAX_NODES)
        files["profile-input.json"] = canonical(profile)
        state_sha = sha(files["state.bin"])
        manifest = json.loads(files["manifest.json"])
        manifest.update(snapshot_revision=aggregate["revision"], profile_sha256=sha(canonical(profile)),
            pool_schema=SCHEMA, pool_registry_sha256=self.registry.sha256, pool_policy_sha256=POLICY_SHA256)
        manifest["files"] = [{"file": name, "bytes": len(files[name]), "sha256": sha(files[name])} for name in ("state.bin", "shop.bin", "dossier.bin")]
        files["manifest.json"] = canonical(manifest)
        compatibility = json.loads(files["compatibility.json"]); compatibility["snapshot_revision"] = aggregate["revision"]
        compatibility["crew_mapping"] = [{"crew_id": r["crew_id"], "native_inventory_id": r["native_id"],
            "native_vehicle_inventory_id": r["vehicle_native_id"], "slot_index": r["seat"]} for r in aggregate["crew_inventory"]["members"]]
        compatibility["research_mapping"] = [{"vehicle_inventory_id": r["vehicle_inventory_id"], "native_inventory_id": r["native_id"],
            "vehicle_id": r["vehicle_id"], "type_compact_id": item_cd(self.catalog, r["vehicle_id"]), "battle": False} for r in aggregate["research"]["vehicles"]]
        compatibility["ammo_mapping"] = [{"shell_definition_id": key, "native_shell_compact_descr": self.shells[key].native_compact_id,
            "vehicle_inventory_id": row["vehicle_id"], "native_vehicle_inventory_id": next(r["native_id"] for r in aggregate["research"]["vehicles"] if r["vehicle_inventory_id"] == row["vehicle_id"]),
            "native_turret_compact_descr": self.mounts[row["mount_id"]].turret_native_compact_id,
            "native_gun_compact_descr": self.mounts[row["mount_id"]].gun_native_compact_id} for row in aggregate["ammunition"] for key in self.mounts[row["mount_id"]].shell_ids]
        files["compatibility.json"] = canonical(compatibility)
        for name in list(files):
            if name.endswith(".json") and name not in ("manifest.json", "compatibility.json", "profile-input.json"):
                metadata = json.loads(files[name])
                if "state_sha256" in metadata:
                    metadata.update(state_sha256=state_sha, revision=aggregate["revision"])
                    if "shop_sha256" in metadata: metadata["shop_sha256"] = sha(files["shop.bin"])
                    files[name] = canonical(metadata)
        files["p08b-battle.json"] = canonical(dict(version=1, schema=LEGACY_BATTLE_SCHEMA, policy_sha256=LEGACY_BATTLE_POLICY,
            account_id=profile["account_id"], native_database_id=profile["native_database_id"], revision=aggregate["revision"],
            state_sha256=state_sha, capabilities=legacy_capabilities(self.catalog, aggregate)))
        crew = contract_for_crew(aggregate["crew_inventory"])
        files["p04m-pool.json"] = canonical(dict(version=1, schema=SCHEMA, definition_sha256=DEFINITION_SHA256,
            registry_sha256=self.registry.sha256, policy_sha256=POLICY_SHA256, crew_policy_sha256=crew.POLICY_SHA256,
            ammo_catalog_sha256=self.ammo_catalog_sha256, account_id=profile["account_id"], native_database_id=profile["native_database_id"],
            revision=aggregate["revision"], state_sha256=state_sha, crew_capacity=crew.CAPACITY, capabilities=self.registry.capabilities(aggregate)))
        require(len(files["p04m-pool.json"]) <= 65536, "PROFILE_TOO_LARGE")
        return files
