"""Opt-in curated stock services on the existing SQLite authority.

Frozen F-K validators remain the default. An explicitly activated owner gets a
new current-snapshot contract while immutable source/legacy receipts survive.
New battle types remain denied by the retained P08B admission policy.
"""
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import threading

from game_profile_tx import TransactionError, _bounded_id, _revision, _decode_object
from p09d_ammo_store import require, sha, REQUEST_FIELDS
from p09d_ammo_projection import canonical, encode, MAX_UPDATE
from p09c_ammo_catalog import MOUNTS, SHELLS, Mount, Shell
from p09e_research_store import _json, MAX_OWNED, ResearchStore
from p09c_ammo_service import MAX_JSON
from p08c_battle_results import ResultsStore
from p04k_crew_store import NativeBarracksRecruitmentStore
from p04j_crew_store import MEMBER_COLUMNS
from p04m_stock_registry import StockRegistry, SCHEMA, DEFINITION_SHA256, NEW_KINDS, PINS
from p04m_pool_crew import (CrewContract, CrewContractV2, native_crew, decode, contract_for_command,
    POLICY_SHA256 as CREW_POLICY_SHA256)

SHELL_ROWS = {
    "t26": (("ap", "_37mm_UBR-160", "ARMOR_PIERCING", 4), ("apcr", "_37mm_UBR-160P", "ARMOR_PIERCING_CR", 5), ("he", "_37mm_UOF-160", "HIGH_EXPLOSIVE", 6)),
    "t34": (("ap", "_76mm_UBR-354A", "ARMOR_PIERCING", 28), ("heat", "_76mm_BP-354", "HOLLOW_CHARGE", 29), ("he", "_76mm_UOF-354", "HIGH_EXPLOSIVE", 30)),
    "t3485": (("ap", "_76mm_UBR-354MA", "ARMOR_PIERCING", 31), ("apcr", "_76mm_UBR-354MP", "ARMOR_PIERCING_CR", 32), ("he", "_76mm_UOF-354M", "HIGH_EXPLOSIVE", 33)),
}
POLICY = {"schema": SCHEMA, "definition_sha256": DEFINITION_SHA256, "crew_policy_sha256": CREW_POLICY_SHA256,
    "migration": "verified-profile13-owner-no-active-reservation-preserve-legacy-proof-and-balances",
    "ammo": "existing-owned-depot-only-no-grants-no-purchases", "new_admission": False, "crew_capacity": 16,
    "new_shells": SHELL_ROWS}
POLICY_SHA256 = sha(canonical(POLICY))


class _ProcessMemo:
    """Per-process, thread-safe, byte-bounded LRU of canonical JSON values.

    Store instances are opened per command; a long-lived writer process (DOM-01
    Domain) keeps the memo across them. Values are stored as canonical bytes and
    decoded on every hit, so no caller ever shares a mutable object.
    """
    def __init__(self, max_bytes):
        self.max_bytes, self.size, self.rows, self.lock = max_bytes, 0, OrderedDict(), threading.Lock()

    def get(self, key, compute):
        with self.lock:
            raw = self.rows.get(key)
            if raw is not None: self.rows.move_to_end(key)
        if raw is None:
            raw = canonical(compute())
            with self.lock:
                if key not in self.rows:
                    self.rows[key] = raw; self.size += len(raw)
                    while self.size > self.max_bytes and self.rows: self.size -= len(self.rows.popitem(last=False)[1])
        return json.loads(raw)


# Pure plan/response of one hash-verified immutable ledger row (see _replay_mutation).
_REPLAY_MEMO = _ProcessMemo(64 * 1024 * 1024)
# SHA-256 of v2 JSON strings that already passed the bounded depth scan.
_SCANNED_JSON, _SCANNED_LOCK = OrderedDict(), threading.Lock()


def _shell_rows(registry):
    """Legacy SHELL_ROWS, or (CAT-01 active) catalog rows for every registry kind
    without a P09C mount; kinds present in both must agree exactly."""
    import catalog_v1
    if not catalog_v1.active():
        return SHELL_ROWS
    rows = {kind: row for kind, row in catalog_v1.shell_rows().items()
            if kind in registry.profiles and registry.profiles[kind].assembly_id not in MOUNTS}
    require(all(rows[kind] == SHELL_ROWS[kind] for kind in set(rows) & set(SHELL_ROWS)), "CAT01_CATALOG_DISAGREES")
    return rows


def _catalog_shell_compact_ids(kind):
    """{suffix: native compact ID} of a catalog kind, or None in legacy mode."""
    import catalog_v1
    if not catalog_v1.active():
        return None
    return {s["suffix"]: s["native_compact_id"] for s in catalog_v1.by_kind(kind)["shells"]}


LINEAGE = ("p09d_import", "p04f_crew_meta", "p04g_crew_meta", "p04h_crew_meta", "p04i_crew_meta", "p04j_crew_meta", "p04k_crew_meta")
CREW_V2_COMMAND, CREW_V1_COMMAND = "p04m.crew_contract_v2.v1", "p04m.crew_contract_v1.v1"
# Exact retained P04H meta DDL (v1) and its widened lifetime-192 form (v2).
META_COLUMNS = """account_id TEXT PRIMARY KEY REFERENCES game_snapshot(account_id),
                next_native_id INTEGER NOT NULL CHECK(next_native_id BETWEEN 4 AND %d),
                free_left INTEGER NOT NULL CHECK(free_left BETWEEN 0 AND %d),
                configuration_revision INTEGER NOT NULL CHECK(configuration_revision BETWEEN 1 AND 2147483647),
                source_bundle_sha256 TEXT NOT NULL,source_audit_sha256 TEXT NOT NULL,policy_sha256 TEXT NOT NULL"""


class PoolStore(ResultsStore):
    def __init__(self, path, catalog, *, account_id, failpoint=None):
        super().__init__(path, catalog, failpoint=failpoint)
        self.pool_account = account_id
        self.registry = StockRegistry(catalog)
        self._pool_activating = False
        self._legacy_contract = False
        self.shells, self.mounts = dict(SHELLS), dict(MOUNTS)
        for kind, rows in sorted(_shell_rows(self.registry).items()):
            p = self.registry.profiles[kind]
            shells = []
            compact = _catalog_shell_compact_ids(kind)
            for suffix, name, shell_kind, item_id in rows:
                key = "shell:" + p.assembly_id + "-" + suffix
                # Legacy rows are USSR (nation 0); catalog rows carry their own nation.
                cd = (item_id << 8) + 10 if compact is None else compact[suffix]
                self.shells[key] = Shell(key, name, shell_kind, item_id, cd); shells.append(key)
            modules = dict(p.modules)
            self.mounts[p.assembly_id] = Mount(p.assembly_id, p.vehicle_id, p.vehicle_id.split(":")[-1], p.type_compact_id,
                modules["turret"].split(":")[-1], catalog.modules[modules["turret"]]["native_compact_id"],
                modules["gun"].split(":")[-1], catalog.modules[modules["gun"]]["native_compact_id"], p.capacity, tuple(shells))
        # CONTENT-0 4 (catalog mode): one mount per other turret x gun pair of a generated stock kind, from the pinned
        # build table (capacity and ordered shells of the client's turret/gun XML); `self.pair_mount` maps
        # (vehicle, turret, gun) -> mount ID for every pair, the stock pair included.
        self.pair_mount, pair_shells = {}, []
        for p in self.registry.profiles.values():
            if not p.assembly_kind and p.assembly_id in self.mounts:
                m = dict(p.modules); self.pair_mount[(p.vehicle_id, m["turret"], m["gun"])] = p.assembly_id
        import catalog_v1
        if catalog_v1.active():
            import content0_builds
            from p04m_stock_registry import pair_name
            for (vehicle_id, turret, gun), source in sorted(content0_builds.mounts().items()):
                stock = self.registry.by_vehicle.get(vehicle_id)
                if stock is None or stock.kind in PINS or (vehicle_id, turret, gun) in self.pair_mount:
                    continue
                assembly = stock.kind + "@" + pair_name({"turret": turret, "gun": gun})
                shells = []
                for suffix, name, shell_kind, item_id, cd, _ in source["shells"]:
                    key = "shell:" + assembly + "-" + suffix
                    self.shells[key] = Shell(key, name, shell_kind, item_id, cd); shells.append(key); pair_shells.append(key)
                self.mounts[assembly] = Mount(assembly, vehicle_id, vehicle_id.split(":")[-1], stock.type_compact_id,
                    turret.split(":")[-1], catalog.modules[turret]["native_compact_id"], gun.split(":")[-1],
                    catalog.modules[gun]["native_compact_id"], source["capacity"], tuple(shells))
                self.pair_mount[(vehicle_id, turret, gun)] = assembly
        # The ammo catalog hash pinned by the gateway covers the legacy mounts only;
        # BATTLE-ANY generated mounts are bound by the activated catalog hash.
        legacy = {key: value for key, value in self.mounts.items()
                  if key in MOUNTS or key[:-len("-stock")] in PINS}
        legacy_shells = {key for mount in legacy.values() for key in mount.shell_ids}
        self.ammo_catalog_sha256 = sha(canonical({key: vars(value) for key, value in sorted(legacy.items())}
            | {"shells": {key: vars(value) for key, value in sorted(self.shells.items()) if key in legacy_shells}}))
        # CONTENT-0 step 1 (owner 2026-11-11): the account depot keeps one count per shell compact ID, shared by every
        # mount of that shell, as the #717 client (inventory 10). Mounts, loadouts and battles keep their per-mount shell
        # definitions; only the depot row is shared. The row key of a compact ID is the definition of its first owner:
        # the legacy MS-1/IS-7 shells (their P09C keys, written by the P09D service), then catalogue order (rows are
        # appended). A shell of one vehicle keeps its old key, so stores without shared shells read unchanged; a
        # vehicle added later with an existing shell joins the existing row.
        import catalog_v1
        order = {v["kind"]: i for i, v in enumerate(catalog_v1.vehicles())} if catalog_v1.active() else {}
        rank = {key: (-1, key) for key in SHELLS}
        for kind, rows in _shell_rows(self.registry).items():
            assembly = self.registry.profiles[kind].assembly_id
            for suffix, *_ in rows:
                key = "shell:" + assembly + "-" + suffix
                rank.setdefault(key, (order.get(kind, len(order)), key))
        # CONTENT-0 4: shells of the other pairs come after every stock shell, so existing depot keys never move.
        for key in pair_shells:
            rank.setdefault(key, (len(order) + 1, key))
        first = {}
        for key, shell in self.shells.items():
            cd = shell.native_compact_id
            if cd not in first or rank[key] < rank[first[cd]]:
                first[cd] = key
        self.depot_key = {key: first[shell.native_compact_id] for key, shell in self.shells.items()}
        self.depot_cd = {self.depot_key[key]: shell.native_compact_id for key, shell in self.shells.items()}
        require(len(self.depot_cd) == len({shell.native_compact_id for shell in self.shells.values()}), "CORRUPT_STORE")
        self.depot_keys = tuple(sorted(self.depot_cd))
        # CONTENT-0 2.6: the largest mounted capacity that can carry each depot shell, so the zero-economy floor
        # covers a full load (M2 light: 1800 rounds) and not only the policy's 100.
        self.depot_mount_capacity = {key: 0 for key in self.depot_keys}
        for mount in self.mounts.values():
            for shell_id in mount.shell_ids:
                if shell_id in self.depot_key:
                    key = self.depot_key[shell_id]
                    self.depot_mount_capacity[key] = max(self.depot_mount_capacity[key], mount.capacity)

    def _pool_row(self):
        exists = self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p04m_schema'").fetchone()
        if not exists: return None
        markers = self.connection.execute("SELECT version,definition_sha256,registry_sha256,policy_sha256,catalog_sha256 FROM p04m_schema").fetchall()
        require([tuple(row) for row in markers] == [(SCHEMA, DEFINITION_SHA256, self.registry.sha256, POLICY_SHA256, self.catalog.sha256)], "UNSUPPORTED_POOL_SCHEMA")
        return self.connection.execute("SELECT * FROM p04m_owner WHERE account_id=?", (self.pool_account,)).fetchone()

    def pool_active(self): return not self._pool_activating and self._pool_row() is not None

    def initialize(self):
        # These markers identify the untouched historical F-K source contract;
        # the opt-in current crew contract has its own marker below.
        previous = self._legacy_contract; self._legacy_contract = True
        try: super().initialize()
        finally: self._legacy_contract = previous
        row = self._pool_row()
        if row is not None: self._baseline(row)

    def _contract(self):
        return self._crew_contract() if not self._legacy_contract and self.pool_active() else NativeBarracksRecruitmentStore

    def _crew_contract(self, account=None):
        """The account's stored pool crew contract: no marker row means v1."""
        exists = self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p04m_crew_contract'").fetchone()
        if not exists: return CrewContract
        rows = self.connection.execute("SELECT version,policy_sha256 FROM p04m_crew_contract WHERE account_id=?",
            (self.pool_account if account is None else account,)).fetchall()
        if not rows: return CrewContract
        require([tuple(row) for row in rows] == [(CrewContractV2.SCHEMA, CrewContractV2.POLICY_SHA256)], "UNSUPPORTED_POOL_SCHEMA")
        return CrewContractV2

    def _stored_json(self, raw):
        # v2 profile/ledger rows legitimately exceed the frozen 16 KiB F-K bound;
        # every smaller row keeps the frozen reader.
        # A v2 marker row exists only for an activated pool owner (set_crew_contract). Since the CONTENT-0 main
        # transfer (12.11) a v1 profile takes the same bound (the main catalogue's depot), still read by _json
        # (P09E MAX_STATE, 256 KB).
        if type(raw) is str and len(raw) > MAX_JSON:
            # The bounded depth scan is pure Python; an identical string that
            # already passed it in this process is only decoded again.
            digest = hashlib.sha256(raw.encode("utf-8")).digest()
            with _SCANNED_LOCK: known = digest in _SCANNED_JSON
            if known: return _decode_object(raw, "P09E")
            value = _json(raw)
            with _SCANNED_LOCK:
                _SCANNED_JSON[digest] = True
                while len(_SCANNED_JSON) > 65536: _SCANNED_JSON.popitem(last=False)
            return value
        return super()._stored_json(raw)

    def _replay_mutation(self, row, request, profile, *, operation, contract=None):
        """Every read re-verifies each pool receipt against the current profile.
        The pure part (plan/response of one hash-verified immutable ledger row)
        is memoized per process: v2 retirements make it quadratic otherwise."""
        contract = self._contract() if contract is None else contract
        if contract in (CrewContract, CrewContractV2):
            contract = self._memo_contract(contract, (contract.SCHEMA, operation, row["p09c_result_sha256"], sha(canonical(request))))
        return super()._replay_mutation(row, request, profile, operation=operation, contract=contract)

    def _memo_contract(self, contract, key):
        # Key: contract schema, operation, verified result SHA and request SHA; the
        # catalogue binding (catalog_v1) is fixed for the life of the process.
        class Memoized(contract):
            @classmethod
            def plan_operation(cls, before, layout, *, operation, account_id):
                return _REPLAY_MEMO.get(("plan",) + key,
                    lambda: contract.plan_operation(before, layout, operation=operation, account_id=account_id))
            @classmethod
            def operation_response(cls, request, revision, crew, *, operation, before_crew):
                return _REPLAY_MEMO.get(("response", revision) + key,
                    lambda: contract.operation_response(request, revision, crew, operation=operation, before_crew=before_crew))
        return Memoized

    def _crew_row_limit(self):
        # No marker row (any non-v2 owner) keeps the retained bound 17.
        return max(self._crew_contract().CAPACITY + 1, super()._crew_row_limit())

    def migrate_research(self, *args, **kwargs):
        # Rechecking the retained predecessor at bridge startup still uses its
        # historical marker, while current state is verified by this store.
        previous = self._legacy_contract; self._legacy_contract = True
        try: return super().migrate_research(*args, **kwargs)
        finally: self._legacy_contract = previous

    def _lineage(self, account):
        value = {}
        for table in LINEAGE:
            rows = self.connection.execute("SELECT * FROM " + table + " WHERE account_id=?", (account,)).fetchall()
            require(len(rows) == 1, "CORRUPT_STORE"); value[table] = dict(rows[0])
        meta = self.connection.execute("SELECT source_bundle_sha256,source_audit_sha256,policy_sha256 FROM p04d_crew_meta WHERE account_id=?", (account,)).fetchone()
        require(meta is not None, "CORRUPT_STORE"); value["p04d_crew_meta_source"] = tuple(meta)
        return value

    def _baseline(self, row):
        require(row["account_id"] == self.pool_account, "FOREIGN_ACCOUNT")
        for field in ("snapshot", "profile", "lineage"):
            raw = row["base_" + field + "_json"]
            require(type(raw) is str and len(raw) <= 262144 and sha(raw.encode("ascii")) == row["base_" + field + "_sha256"], "CORRUPT_STORE")
        snapshot, profile, lineage = (_json(row["base_" + field + "_json"]) for field in ("snapshot", "profile", "lineage"))
        require(snapshot["account_id"] == profile["account_id"] == self.pool_account
            and snapshot["revision"] + 1 == row["activated_revision"] and profile["snapshot_revision"] == snapshot["revision"]
            and canonical(lineage) == canonical(self._lineage(self.pool_account)), "CORRUPT_STORE")
        NativeBarracksRecruitmentStore.native_crew(snapshot["crew_inventory"])
        return snapshot, profile

    def _vehicle_map(self, account, research=None):
        research = self._research(account) if research is None else research
        result = []
        for owned in research["vehicles"]:
            p = self.registry.by_vehicle.get(owned["vehicle_id"])
            if p is not None:
                require(owned["vehicle_inventory_id"] == self.registry.inventory_id(account, owned["native_id"], p.kind), "CORRUPT_STORE")
                result.append({"native_inventory_id": owned["native_id"], "vehicle_inventory_id": owned["vehicle_inventory_id"], "kind": p.kind})
        return result

    def _crew_projection(self, account):
        if not self.pool_active(): return super()._crew_projection(account)
        require(account == self.pool_account, "FOREIGN_ACCOUNT")
        meta = self.connection.execute("SELECT * FROM p04d_crew_meta WHERE account_id=?", (account,)).fetchone()
        require(meta is not None, "CORRUPT_STORE")
        contract = self._crew_contract(account); limit = contract.CAPACITY + 1
        value = dict(policy_sha256=contract.POLICY_SHA256, account_id=account, vehicles=self._vehicle_map(account),
            free_recruitment_left=meta["free_left"], next_native_id=meta["next_native_id"], configuration_revision=meta["configuration_revision"],
            members=[dict(row) for row in self.connection.execute("SELECT " + MEMBER_COLUMNS + " FROM p04d_crew_member WHERE account_id=? ORDER BY native_id LIMIT ?", (account, limit))],
            retired_members=[dict(row) for row in self.connection.execute("SELECT " + MEMBER_COLUMNS + " FROM p04j_retired_member WHERE account_id=? ORDER BY native_id LIMIT ?", (account, limit))])
        try: native_crew(value, contract)
        except (TransactionError, ValueError, KeyError, TypeError, IndexError) as error: raise TransactionError("CORRUPT_STORE") from error
        baseline, _ = self._baseline(self._pool_row())
        prior = {r["native_id"]: r for r in baseline["crew_inventory"]["members"] + baseline["crew_inventory"]["retired_members"]}
        current = {r["native_id"]: r for r in value["members"] + value["retired_members"]}
        require(all(identity in current and self._historical_member_matches(old, current[identity]) for identity, old in prior.items())
            and all(r in value["retired_members"] for r in baseline["crew_inventory"]["retired_members"]), "CORRUPT_STORE")
        return value

    def _ammo_projection(self, account):
        if not self.pool_active(): return super()._ammo_projection(account)
        rows = self.connection.execute("SELECT vehicle_id,mount_id,loaded_json FROM p09c_ammo_mount WHERE account_id=? ORDER BY vehicle_id LIMIT ?", (account, MAX_OWNED + 1)).fetchall()
        require(len(rows) <= MAX_OWNED, "CORRUPT_STORE")
        result = []
        for row in rows:
            mount = self.mounts.get(row["mount_id"]); require(mount is not None, "CORRUPT_STORE")
            loaded = _json(row["loaded_json"])
            require(type(loaded) is dict and set(loaded) == set(mount.shell_ids)
                and all(type(n) is int and 0 <= n <= mount.capacity for n in loaded.values()) and sum(loaded.values()) <= mount.capacity, "CORRUPT_STORE")
            result.append({"vehicle_id": row["vehicle_id"], "mount_id": row["mount_id"], "loaded": loaded})
        # Bound by this store's own shell set (+1 detects an extra row); a fixed 16
        # held only the legacy 15 pool shells (BATTLE-ANY catalog rows add more).
        depot_rows = self.connection.execute("SELECT shell_id,quantity FROM p09c_ammo_depot WHERE account_id=? ORDER BY shell_id LIMIT ?", (account, len(self.depot_keys) + 1)).fetchall()
        depot = {row[0]: row[1] for row in depot_rows}
        require(len(depot_rows) == len(self.depot_keys) and set(depot) == set(self.depot_keys)
            and all(type(n) is int and 0 <= n <= 1000000 for n in depot.values()), "CORRUPT_STORE")
        expected = {r["vehicle_inventory_id"]: self.mount_id_of(r) for r in self._research(account)["vehicles"] if r["vehicle_id"] in self.registry.by_vehicle}
        require({row["vehicle_id"]: row["mount_id"] for row in result} == expected, "CORRUPT_STORE")
        return result, depot

    def _snapshot(self, account, revision, vehicles):
        if not self.pool_active(): return super()._snapshot(account, revision, vehicles)
        require(account == self.pool_account, "FOREIGN_ACCOUNT"); _revision(revision)
        value, _ = self._baseline(self._pool_row()); value = deepcopy(value)
        research = self._research(account)
        rows = [{"vehicle_id": vehicle, "state": state, "battle_id": battle} for vehicle, state, battle in sorted(vehicles)]
        require(len(rows) <= MAX_OWNED and {r["vehicle_id"] for r in rows} == {r["vehicle_inventory_id"] for r in research["vehicles"]}, "CORRUPT_STORE")
        require(all((r["state"] == "available" and r["battle_id"] is None)
            or (r["state"] == "reserved" and type(r["battle_id"]) is str and 1 <= len(r["battle_id"]) <= 96) for r in rows)
            and sum(r["state"] == "reserved" for r in rows) <= 1, "CORRUPT_STORE")
        value.update(revision=revision, vehicles=rows, research=research, crew_schema=self._crew_contract(account).SCHEMA,
            crew_inventory=self._crew_projection(account), pool={"schema": SCHEMA, "registry_sha256": self.registry.sha256, "policy_sha256": POLICY_SHA256})
        value["ammunition"], value["depot"] = self._ammo_projection(account)
        raw = canonical(value); require(len(raw) <= 262144, "PROFILE_TOO_LARGE")
        return raw.decode("ascii"), sha(raw)

    def _project_profile(self, account, aggregate):
        if not self.pool_active(): return super()._project_profile(account, aggregate)
        _, value = self._baseline(self._pool_row()); value = deepcopy(value)
        contract = self._crew_contract(account)
        inv, seats = native_crew(aggregate["crew_inventory"], contract)
        owned = aggregate["research"]["vehicles"]; by_native = {r["native_id"]: r["vehicle_inventory_id"] for r in owned}
        prior = {r["inventory_id"]: r for r in value["inventory"]}
        ammunition = {r["vehicle_id"]: r for r in aggregate["ammunition"]}
        value["inventory"] = []
        for row in owned:
            key = row["vehicle_inventory_id"]; definition = self.catalog.vehicles[row["vehicle_id"]]
            entry = deepcopy(prior.get(key, {"inventory_id": key, "vehicle_definition_id": row["vehicle_id"], "vehicle_xp": 0}))
            entry.update(health=definition["hull_max_hp"] + definition["turret_max_hp"][row["modules"]["turret"]],
                crew_assigned=row["native_id"] in seats and all(i is not None for i in seats[row["native_id"]]),
                ammunition_count=sum(ammunition[key]["loaded"].values()) if key in ammunition else 0,
                research_vehicle_id=row["vehicle_id"], modules=deepcopy(row["modules"]), battle_admission=False)
            value["inventory"].append(entry)
        value.update(snapshot_revision=aggregate["revision"], crew=[{"crew_id": r["crew_id"],
            "vehicle_inventory_id": by_native.get(r["vehicle_native_id"]), "role": r["role"],
            "role_level": self.member_role_level(r), "skills": self.member_skills(r)}
            for r in aggregate["crew_inventory"]["members"]],
            crew_service={"schema": contract.SCHEMA, "policy_sha256": contract.POLICY_SHA256, "battle": False,
                "free_recruitment_left": aggregate["crew_inventory"]["free_recruitment_left"], "configuration_revision": aggregate["crew_inventory"]["configuration_revision"]},
            ammunition=[{"vehicle_inventory_id": r["vehicle_id"], "shell_definition_id": key, "count": n} for r in aggregate["ammunition"] for key, n in sorted(r["loaded"].items())],
            ammunition_depot=aggregate["depot"], pool_service=aggregate["pool"])
        # The baseline is frozen at activation; the catalogue is the one _pool_row() verified (CAT-NATIONS).
        value["research"].update(catalog_sha256=self.catalog.sha256, garage_slots=aggregate["research"]["garage_slots"], unlocked_count=len(aggregate["research"]["unlocked"]), depot_types=len(aggregate["research"]["depot"]))
        require(len(canonical(value)) <= contract.PROFILE_BOUND, "PROFILE_TOO_LARGE"); return value

    def _verified_snapshot(self, row, account):
        if not self.pool_active(): return super()._verified_snapshot(row, account)
        self.initialize(); require(account == self.pool_account, "FOREIGN_ACCOUNT")
        rows = self.connection.execute("SELECT vehicle_id,state,battle_id FROM game_vehicle WHERE account_id=? ORDER BY vehicle_id LIMIT ?", (account, MAX_OWNED + 1)).fetchall()
        raw, digest = self._snapshot(account, row["revision"], [tuple(r) for r in rows])
        require(row["snapshot_json"] == raw and row["snapshot_sha256"] == digest, "CORRUPT_STORE")
        aggregate = _json(raw)
        if self._hangar_mutation: require(all(r["state"] == "available" for r in aggregate["vehicles"]), "VEHICLE_RESERVED")
        public = self.connection.execute("SELECT native_id,profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()
        expected = self._project_profile(account, aggregate)
        require(public is not None and public["native_id"] == expected["native_database_id"] and _json(public["profile_json"]) == expected, "CORRUPT_STORE")
        self.layouts(account); self._verify_active(aggregate); return aggregate

    def _economy_grants(self, account):
        # Zero economy: every pool shell (incl. the new T-26/T-34/T-34-85 mounts,
        # otherwise depot-only and empty) is topped up, never reduced.
        super()._economy_grants(account)
        if not self.pool_active(): return
        from p09e_research_store import ECONOMY_SHELL_MINIMUM
        self._ensure_pool_rows(account)
        # The policy's shell_depot_minimum (100) stays the floor; a shell of a larger magazine/belt is topped up
        # to that vehicle's full load (CONTENT-0 2.6, owner 12.11: the M2 light got 100 of 1800 rounds).
        for key in self.depot_keys:
            floor = max(ECONOMY_SHELL_MINIMUM, self.depot_mount_capacity[key])
            require(self.connection.execute("UPDATE p09c_ammo_depot SET quantity=MAX(quantity,?) WHERE account_id=? AND shell_id=?",
                (floor, account, key)).rowcount == 1, "CORRUPT_STORE")

    def mount_id_of(self, owned):
        """CONTENT-0 4: the mount of an owned vehicle's current turret x gun pair; a pair outside the build table
        (legacy kinds) keeps the stock mount, whose shells stay unloaded and hidden."""
        p = self.registry.by_vehicle[owned["vehicle_id"]]
        return self.pair_mount.get((owned["vehicle_id"], owned["modules"]["turret"], owned["modules"]["gun"]), p.assembly_id)

    def pair_mounted(self, owned):
        """True when the stored mount is the one of the current pair (always for the stock pair)."""
        return (owned["vehicle_id"], owned["modules"]["turret"], owned["modules"]["gun"]) in self.pair_mount

    def pair_layouts(self, aggregate):
        """CONTENT-0 4: {native: (shells, shellsLayout)} of every owned vehicle on its pair's mount, from the stored
        loaded counts (the native record of p04m_pool_projection)."""
        owned = {r["vehicle_inventory_id"]: r for r in aggregate["research"]["vehicles"]}
        result = {}
        for ammo in aggregate["ammunition"]:
            vehicle = owned[ammo["vehicle_id"]]
            if not self.pair_mounted(vehicle) or ammo["mount_id"] != self.mount_id_of(vehicle): continue
            mount = self.mounts[ammo["mount_id"]]
            layout = [n for key in mount.shell_ids for n in (self.shells[key].native_compact_id, ammo["loaded"][key])]
            result[vehicle["native_id"]] = (layout, {(mount.turret_native_compact_id, mount.gun_native_compact_id): layout})
        return result

    def _mount_change(self, account, research):
        """CONTENT-0 4: after a module install, a vehicle whose turret x gun pair changed takes that pair's mount
        (loaded counts zero: the research plan refuses the change while shells are loaded, UNLOAD_AMMUNITION_REQUIRED)."""
        if not self.pool_active(): return
        c = self.connection
        require(c.in_transaction, "POOL_TRANSACTION_REQUIRED")
        for owned in research["vehicles"]:
            if owned["vehicle_id"] not in self.registry.by_vehicle: continue
            row = c.execute("SELECT mount_id,loaded_json FROM p09c_ammo_mount WHERE account_id=? AND vehicle_id=?", (account, owned["vehicle_inventory_id"])).fetchone()
            target = self.mount_id_of(owned)
            if row is None or row["mount_id"] == target: continue
            require(not any(_json(row["loaded_json"]).values()), "UNLOAD_AMMUNITION_REQUIRED")
            mount = self.mounts[target]
            require(c.execute("UPDATE p09c_ammo_mount SET mount_id=?,loaded_json=? WHERE account_id=? AND vehicle_id=?",
                (target, canonical({key: 0 for key in mount.shell_ids}).decode("ascii"), account, owned["vehicle_inventory_id"])).rowcount == 1, "CORRUPT_STORE")
            layout = [n for key in mount.shell_ids for n in (self.shells[key].native_compact_id, 0)]
            require(c.execute("UPDATE p09d_native_layout SET layout_json=? WHERE account_id=? AND native_vehicle_id=?",
                (json.dumps(layout), account, owned["native_id"])).rowcount == 1, "CORRUPT_STORE")

    def _ensure_pool_rows(self, account):
        require(self.connection.in_transaction, "POOL_TRANSACTION_REQUIRED")
        for key in self.depot_keys:
            self.connection.execute("INSERT OR IGNORE INTO p09c_ammo_depot VALUES (?,?,0)", (account, key))
        for owned in self._research(account)["vehicles"]:
            p = self.registry.by_vehicle.get(owned["vehicle_id"])
            if p is None: continue
            mount_id = self.mount_id_of(owned); mount = self.mounts[mount_id]
            loaded = {key: 0 for key in mount.shell_ids}
            exists = self.connection.execute("SELECT 1 FROM p09c_ammo_mount WHERE account_id=? AND vehicle_id=?", (account, owned["vehicle_inventory_id"])).fetchone()
            if exists is None:
                self.connection.execute("INSERT INTO p09c_ammo_mount VALUES (?,?,?,?)", (account, owned["vehicle_inventory_id"], mount_id, canonical(loaded).decode("ascii")))
                layout = [n for key in mount.shell_ids for n in (self.shells[key].native_compact_id, 0)]
                self.connection.execute("INSERT INTO p09d_native_layout VALUES (?,?,?)", (account, owned["native_id"], json.dumps(layout)))

    def extend_catalog_shells(self, *, account_id):
        """BATTLE-ANY stand migration: depot rows of the shells a newer catalog added.

        A stand switched from the five-kind catalog keeps snapshots without the
        new shells, so every profile read fails. Only when the stored snapshot
        equals this store's projection except exactly the missing zero rows, and
        no owned vehicle mounts a missing shell, the rows are inserted, the
        zero-economy top-up applied and the profile re-projected at revision+1;
        the full reader must then verify it (all or nothing). Idempotent.

        CONTENT-0 4: the same migration moves a vehicle whose turret x gun pair was changed before step 4 (its row
        kept the stock mount, nothing loaded) to its pair's mount; the stored snapshot must equal the new projection
        with those rows put back as they were."""
        self.initialize()
        require(self.pool_active() and account_id == self.pool_account, "POOL_INACTIVE")
        c = self.connection
        c.execute("BEGIN IMMEDIATE")
        try:
            row = c.execute("SELECT * FROM game_snapshot WHERE account_id=?", (account_id,)).fetchone()
            require(row is not None, "UNKNOWN_ACCOUNT")
            present = {r[0] for r in c.execute("SELECT shell_id FROM p09c_ammo_depot WHERE account_id=? LIMIT ?",
                                                (account_id, len(self.depot_keys) + 1))}
            require(present <= set(self.depot_keys), "CORRUPT_STORE")
            missing = sorted(set(self.depot_keys) - present)
            research = self._research(account_id)
            moved = []
            for owned in research["vehicles"]:
                if owned["vehicle_id"] not in self.registry.by_vehicle: continue
                stored = c.execute("SELECT mount_id,loaded_json FROM p09c_ammo_mount WHERE account_id=? AND vehicle_id=?", (account_id, owned["vehicle_inventory_id"])).fetchone()
                if stored is not None and stored["mount_id"] != self.mount_id_of(owned):
                    loaded = _json(stored["loaded_json"])
                    require(stored["mount_id"] in self.mounts and not any(loaded.values()), "UNLOAD_AMMUNITION_REQUIRED")
                    moved.append((owned["vehicle_inventory_id"], stored["mount_id"], loaded))
            if not missing and not moved:
                c.commit()
                return {"status": "unchanged", "revision": row["revision"], "added": []}
            for owned in research["vehicles"]:
                p = self.registry.by_vehicle.get(owned["vehicle_id"])
                require(p is None or not {self.depot_key[s] for s in self.mounts[p.assembly_id].shell_ids} & set(missing), "CORRUPT_STORE")
            for key in missing:
                c.execute("INSERT INTO p09c_ammo_depot VALUES (?,?,0)", (account_id, key))
            self._mount_change(account_id, research)
            vehicles = c.execute("SELECT vehicle_id,state,battle_id FROM game_vehicle WHERE account_id=? ORDER BY vehicle_id LIMIT ?",
                                 (account_id, MAX_OWNED + 1)).fetchall()
            require(all(r["state"] == "available" for r in vehicles), "VEHICLE_RESERVED")
            raw, _ = self._snapshot(account_id, row["revision"], [tuple(r) for r in vehicles])
            value = _json(raw)
            for key in missing:
                require(value["depot"].pop(key) == 0, "CORRUPT_STORE")
            for vehicle_id, mount_id, loaded in moved:
                entry = next(r for r in value["ammunition"] if r["vehicle_id"] == vehicle_id)
                require(not any(entry["loaded"].values()), "CORRUPT_STORE")
                entry.update(mount_id=mount_id, loaded=loaded)
            require(canonical(value).decode("ascii") == row["snapshot_json"], "CORRUPT_STORE")
            before = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account_id,)).fetchone()[0]
            if self.zero_economy(account_id):
                self._economy_grants(account_id)
            self._save_crew_projection(account_id, row["revision"] + 1, before)
            after = self.read_profile(account_id)
            require(after["revision"] == row["revision"] + 1, "CORRUPT_STORE")
            c.commit()
            return {"status": "extended", "revision": after["revision"], "added": missing, "moved": [m[0] for m in moved]}
        except Exception:
            c.rollback()
            raise

    def share_depot(self, *, account_id):
        """CONTENT-0 step 1 stand migration: per-definition depot rows -> one row per shell compact ID.

        Run on a stopped stand. Each old row moves to its compact-ID row (quantities of definitions that now share a
        row add up, bounded by 1000000); the stored snapshot must equal this store's projection of the old rows, the
        profile is re-projected at revision+1 and the full reader must verify it (all or nothing). Idempotent."""
        self.initialize()
        require(self.pool_active() and account_id == self.pool_account, "POOL_INACTIVE")
        c = self.connection
        c.execute("BEGIN IMMEDIATE")
        try:
            row = c.execute("SELECT * FROM game_snapshot WHERE account_id=?", (account_id,)).fetchone()
            require(row is not None, "UNKNOWN_ACCOUNT")
            old = {r[0]: r[1] for r in c.execute("SELECT shell_id,quantity FROM p09c_ammo_depot WHERE account_id=? LIMIT ?",
                                                (account_id, len(self.shells) + 1))}
            if set(old) == set(self.depot_keys):
                c.commit()
                return {"status": "unchanged", "revision": row["revision"], "moved": []}
            # Sources: per-definition rows (before step 1) or the first step-1 build's shell:native:<cd> rows (stand -15).
            native = {"shell:native:%d" % cd: key for key, cd in self.depot_cd.items()}
            require(set(old) <= set(self.shells) | set(self.depot_keys) | set(native), "CORRUPT_STORE")
            vehicles = c.execute("SELECT vehicle_id,state,battle_id FROM game_vehicle WHERE account_id=? ORDER BY vehicle_id LIMIT ?",
                                 (account_id, MAX_OWNED + 1)).fetchall()
            require(all(r["state"] == "available" for r in vehicles), "VEHICLE_RESERVED")
            stored = _json(row["snapshot_json"])
            require(stored.get("depot") == old, "CORRUPT_STORE")
            merged = {}
            for key, quantity in old.items():
                target = native[key] if key in native else key if key in self.depot_cd else self.depot_key[key]
                merged[target] = merged.get(target, 0) + quantity
            require(all(n <= 1000000 for n in merged.values()), "DEPOT_OVERFLOW")
            c.execute("DELETE FROM p09c_ammo_depot WHERE account_id=?", (account_id,))
            for key in self.depot_keys:
                c.execute("INSERT INTO p09c_ammo_depot VALUES (?,?,?)", (account_id, key, merged.get(key, 0)))
            before = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account_id,)).fetchone()[0]
            if self.zero_economy(account_id):
                self._economy_grants(account_id)
            self._save_crew_projection(account_id, row["revision"] + 1, before)
            after = self.read_profile(account_id)
            require(after["revision"] == row["revision"] + 1, "CORRUPT_STORE")
            c.commit()
            return {"status": "shared", "revision": after["revision"], "moved": sorted(k for k in old if k not in self.depot_cd)}
        except Exception:
            c.rollback()
            raise

    def economy_topup(self, *, account_id):
        """CONTENT-0 2.6 stand operation: apply the current zero-economy depot floor to an existing account.

        The floor is applied when the economy is granted or the depot migrated; an account granted before the
        floor rose (owner 12.11: M2 light 20 + 80 of 1800) keeps its old counts until this runs. Explicit
        zero-economy accounts only, every owned vehicle available; counts only rise; the profile is
        re-projected at revision+1 and verified (all or nothing). Idempotent: nothing to raise -> unchanged."""
        self.initialize()
        require(self.pool_active() and account_id == self.pool_account, "POOL_INACTIVE")
        c = self.connection
        c.execute("BEGIN IMMEDIATE")
        try:
            row = c.execute("SELECT * FROM game_snapshot WHERE account_id=?", (account_id,)).fetchone()
            require(row is not None, "UNKNOWN_ACCOUNT")
            require(self.zero_economy(account_id), "EXPLICIT_TEST_LAB_POLICY_REQUIRED")
            states = [r[0] for r in c.execute("SELECT state FROM game_vehicle WHERE account_id=? LIMIT ?",
                                               (account_id, MAX_OWNED + 1))]
            require(all(state == "available" for state in states), "VEHICLE_RESERVED")
            depot = lambda: dict(c.execute("SELECT shell_id,quantity FROM p09c_ammo_depot WHERE account_id=?", (account_id,)))
            old = depot()
            before = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account_id,)).fetchone()[0]
            self._economy_grants(account_id)
            new = depot()
            require(all(new.get(k, 0) >= v for k, v in old.items()), "CORRUPT_STORE")
            raised = {k: [old.get(k, 0), v] for k, v in sorted(new.items()) if v != old.get(k, 0)}
            if not raised:
                c.rollback()
                return {"status": "unchanged", "revision": row["revision"], "raised": {}}
            self._save_crew_projection(account_id, row["revision"] + 1, before)
            after = self.read_profile(account_id)
            require(after["revision"] == row["revision"] + 1, "CORRUPT_STORE")
            c.commit()
            return {"status": "topped_up", "revision": after["revision"], "raised": raised}
        except Exception:
            c.rollback()
            raise

    def _save_crew_projection(self, account, revision, before):
        if self.pool_active(): self._ensure_pool_rows(account)
        return super()._save_crew_projection(account, revision, before)

    def _validate_layout(self, layout):
        if not self.pool_active(): return super()._validate_layout(layout)
        # Native setVehicleLayout: [shop, vehicle, 2*n, (shell, count)*n, 6, 0*6]; SPG-02: n is the gun's shell count (1..3).
        require(type(layout) is list and len(layout) in (12, 14, 16) and all(type(v) is int and -2**31 <= v < 2**31 for v in layout), "INVALID_INPUT")
        require(layout[0] in (3, 4, 5), "SHOP_REVISION_MISMATCH")
        k = layout[2]
        require(k in (2, 4, 6) and len(layout) == 10 + k and layout[3 + k] == 6 and layout[4 + k:] == [0] * 6, "INVALID_INPUT")
        owned = next((r for r in self._research(self.pool_account)["vehicles"] if r["native_id"] == layout[1]), None)
        require(owned is not None, "UNKNOWN_VEHICLE")
        p = self.registry.by_vehicle.get(owned["vehicle_id"])
        require(p is not None, "UNSUPPORTED_MOUNT")
        mount = self.mounts[self.mount_id_of(owned)]
        expected = {self.shells[key].native_compact_id: key for key in mount.shell_ids}
        values = layout[3:3 + k]; shells, counts = range(0, k, 2), range(1, k, 2)
        require(k == 2 * len(expected) and {abs(values[i]) for i in shells} == set(expected), "INCOMPATIBLE_SHELL")
        require(all(0 <= values[i] <= mount.capacity for i in counts), "INVALID_QUANTITY")
        require(sum(values[i] for i in counts) <= mount.capacity, "CAPACITY_EXCEEDED")
        return mount, {expected[abs(values[i])]: values[i + 1] for i in shells}

    def layouts(self, account):
        if not self.pool_active(): return super().layouts(account)
        require(account == self.pool_account, "FOREIGN_ACCOUNT")
        owned = {r["native_id"]: r for r in self._research(account)["vehicles"] if r["vehicle_id"] in self.registry.by_vehicle}
        rows = self.connection.execute("SELECT native_vehicle_id,layout_json FROM p09d_native_layout WHERE account_id=? ORDER BY native_vehicle_id", (account,)).fetchall()
        require({row[0] for row in rows} == set(owned), "CORRUPT_STORE")
        result = {}
        ammo = {r["vehicle_id"]: r for r in self._ammo_projection(account)[0]}
        for native, raw in rows:
            require(type(raw) is str and len(raw) <= 128, "CORRUPT_STORE")
            try:
                layout = json.loads(raw); mount, counts = self._validate_layout([5, native, len(layout), *layout, 6, 0, 0, 0, 0, 0, 0])
            except (ValueError, TypeError, TransactionError) as error: raise TransactionError("CORRUPT_STORE") from error
            require(ammo[owned[native]["vehicle_inventory_id"]]["loaded"] == counts, "CORRUPT_STORE")
            result[native] = layout
        return result

    def _rebuild_crew_tables(self, native_max=16, meta_bounds=None):
        """Rebuild the shared crew tables with identity bound ``native_max``;
        ``meta_bounds`` (next_native_id max, free_left max) also rebuilds meta."""
        c = self.connection
        before = {table: [tuple(r) for r in c.execute("SELECT * FROM " + table + " ORDER BY account_id,native_id")]
            for table in ("p04d_crew_member", "p04j_retired_member")}
        c.execute("DROP INDEX p04d_crew_seat")
        for action in ("update", "delete"): c.execute("DROP TRIGGER p04j_retired_no_" + action)
        for table in before:
            c.execute("ALTER TABLE " + table + " RENAME TO p04m_old_" + table)
            terminal = table == "p04j_retired_member"
            columns = """account_id TEXT NOT NULL REFERENCES game_snapshot(account_id),
                native_id INTEGER NOT NULL CHECK(native_id BETWEEN 1 AND """ + str(native_max) + """),crew_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('commander','radioman','driver','gunner','loader')),
                descriptor_hex TEXT NOT NULL CHECK(length(descriptor_hex) BETWEEN 50 AND 100 AND length(descriptor_hex)%2=0),
                vehicle_native_id INTEGER NOT NULL CHECK(vehicle_native_id=-1 OR vehicle_native_id BETWEEN 1 AND 2147483647),seat INTEGER"""
            if terminal:
                columns += ",command_key TEXT NOT NULL,dismissed_revision INTEGER NOT NULL CHECK(dismissed_revision>0),configuration_revision INTEGER NOT NULL CHECK(configuration_revision>0),member_sha256 TEXT NOT NULL"
            columns += ",PRIMARY KEY(account_id,native_id),UNIQUE(account_id,crew_id)"
            if terminal: columns += ",UNIQUE(account_id,command_key)"
            columns += ",CHECK((vehicle_native_id=-1 AND seat IS NULL) OR (vehicle_native_id>0 AND seat BETWEEN 0 AND 7))"
            c.execute("CREATE TABLE " + table + "(" + columns + ")")
            c.execute("INSERT INTO " + table + " SELECT * FROM p04m_old_" + table)
            c.execute("DROP TABLE p04m_old_" + table)
            require([tuple(r) for r in c.execute("SELECT * FROM " + table + " ORDER BY account_id,native_id")] == before[table], "POOL_MIGRATION_CHANGED_CREW")
        c.execute("CREATE UNIQUE INDEX p04d_crew_seat ON p04d_crew_member(account_id,vehicle_native_id,seat) WHERE vehicle_native_id>=0")
        for action in ("UPDATE", "DELETE"):
            c.execute("CREATE TRIGGER p04j_retired_no_" + action.lower() + " BEFORE " + action + " ON p04j_retired_member BEGIN SELECT RAISE(ABORT,'terminal crew is immutable'); END")
        if meta_bounds is not None:
            meta = [tuple(r) for r in c.execute("SELECT * FROM p04d_crew_meta ORDER BY account_id")]
            c.execute("ALTER TABLE p04d_crew_meta RENAME TO p04m_old_p04d_crew_meta")
            c.execute("CREATE TABLE p04d_crew_meta(" + META_COLUMNS % meta_bounds + ")")
            c.execute("INSERT INTO p04d_crew_meta SELECT * FROM p04m_old_p04d_crew_meta")
            c.execute("DROP TABLE p04m_old_p04d_crew_meta")
            require([tuple(r) for r in c.execute("SELECT * FROM p04d_crew_meta ORDER BY account_id")] == meta, "POOL_MIGRATION_CHANGED_CREW")
        self._failpoint("after_pool_crew_schema")

    def _crew_tables_widened(self):
        sql = self.connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='p04d_crew_member'").fetchone()
        require(sql is not None, "CORRUPT_STORE")
        widened = "native_id BETWEEN 1 AND %d)" % CrewContractV2.CAPACITY in sql[0]
        require(widened or "native_id BETWEEN 1 AND 16)" in sql[0], "UNSUPPORTED_POOL_SCHEMA")
        return widened

    def set_crew_contract(self, request, *, authenticated_account_id):
        """Versioned, reversible owner migration v1 <-> v2 (lifetime 16 <-> 192).

        One ledger command and one revision, like pool activation. Members,
        passports, seats and retirements are unchanged; only bounds, the
        derived free count and the contract marker move. v2 -> v1 is refused
        once any identity above 16 was issued.
        """
        require(type(request) is dict and set(request) == {"version", "account_id", "native_database_id", "command_key", "expected_revision", "crew_policy_sha256"}
            and type(request["version"]) is int and request["version"] in (1, 2), "INVALID_INPUT")
        target = CrewContractV2 if request["version"] == 2 else CrewContract
        require(request["crew_policy_sha256"] == target.POLICY_SHA256, "P04M_DEFINITION_MISMATCH")
        account = request["account_id"]
        require(account == authenticated_account_id == self.pool_account, "FOREIGN_ACCOUNT")
        _bounded_id(request["command_key"], "command_key"); _revision(request["expected_revision"])
        command = CREW_V2_COMMAND if target is CrewContractV2 else CREW_V1_COMMAND
        payload_sha = sha(canonical(request)); c = self.connection
        c.execute("BEGIN IMMEDIATE")
        try:
            self.initialize()
            require(self.pool_active(), "POOL_ACTIVATION_REQUIRED")
            ledger = c.execute("SELECT * FROM game_command_ledger WHERE account_id=? AND command_id=?", (account, request["command_key"])).fetchone()
            if ledger is not None:
                require(ledger["command_type"] == command and ledger["payload_sha256"] == payload_sha, "DUPLICATE_PAYLOAD_MISMATCH")
                result = _json(ledger["result_json"]); require(sha(canonical(result)) == ledger["p09c_result_sha256"], "CORRUPT_STORE")
                self.read_profile(account); c.commit(); return dict(result, replayed=True)
            aggregate = self.read_profile(account)
            public = c.execute("SELECT native_id,profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()
            require(type(request["native_database_id"]) is int and request["native_database_id"] == public["native_id"], "FOREIGN_ACCOUNT")
            revision = aggregate["revision"]
            require(revision == request["expected_revision"], "STALE_REVISION")
            require(revision < 2**31 - 1, "REVISION_EXHAUSTED")
            require(all(r["state"] == "available" for r in aggregate["vehicles"]), "VEHICLE_RESERVED")
            current = self._crew_contract(account)
            require(current is not target, "CREW_CONTRACT_UNCHANGED")
            crew = aggregate["crew_inventory"]
            free = target.CAPACITY + 1 - crew["next_native_id"]
            def set_free():
                require(c.execute("UPDATE p04d_crew_meta SET free_left=? WHERE account_id=? AND next_native_id=? AND free_left=?",
                    (free, account, crew["next_native_id"], crew["free_recruitment_left"])).rowcount == 1, "STALE_CREW")
            if target is CrewContractV2:
                if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p04m_crew_contract'").fetchone():
                    c.execute("""CREATE TABLE p04m_crew_contract(account_id TEXT PRIMARY KEY REFERENCES game_snapshot(account_id),
                        version TEXT NOT NULL,policy_sha256 TEXT NOT NULL,migrated_revision INTEGER NOT NULL CHECK(migrated_revision>0))""")
                if not self._crew_tables_widened():
                    self._rebuild_crew_tables(CrewContractV2.CAPACITY, (CrewContractV2.CAPACITY + 1, CrewContractV2.CAPACITY - 3))
                c.execute("INSERT INTO p04m_crew_contract VALUES (?,?,?,?)", (account, target.SCHEMA, target.POLICY_SHA256, revision + 1))
                set_free()
            else:
                require(crew["next_native_id"] <= CrewContract.CAPACITY + 1, "CREW_V2_ROLLBACK_BLOCKED")
                require(c.execute("DELETE FROM p04m_crew_contract WHERE account_id=?", (account,)).rowcount == 1, "CORRUPT_STORE")
                set_free()
                if c.execute("SELECT COUNT(*) FROM p04m_crew_contract").fetchone()[0] == 0:
                    # Last v2 account: the narrowed CHECKs refuse any remaining wider row.
                    c.execute("DROP TABLE p04m_crew_contract")
                    self._rebuild_crew_tables(CrewContract.CAPACITY, (CrewContract.CAPACITY + 1, CrewContract.CAPACITY - 3))
            self._failpoint("after_crew_contract_schema")
            self._save_crew_projection(account, revision + 1, public["profile_json"])
            result = dict(status="crew_contract_set", account_id=account, revision=revision + 1, crew_schema=target.SCHEMA,
                crew_policy_sha256=target.POLICY_SHA256, capacity=target.CAPACITY, free_recruitment_left=free,
                members=len(crew["members"]), retired_members=len(crew["retired_members"]), replayed=False)
            encoded = canonical(result)
            c.execute("INSERT INTO game_command_ledger VALUES (?,?,?,?,?,?,?,?)", (account, request["command_key"], command, payload_sha, revision, revision + 1, encoded.decode("ascii"), sha(encoded)))
            self.read_profile(account); self._failpoint("before_crew_contract_commit"); c.commit(); return result
        except Exception:
            c.rollback(); raise

    def activate_pool(self, request, *, authenticated_account_id):
        require(type(request) is dict and set(request) == {"version", "account_id", "native_database_id", "command_key", "expected_revision", "definition_sha256", "registry_sha256"}
            and type(request["version"]) is int and request["version"] == 1, "INVALID_INPUT")
        account = request["account_id"]
        require(account == authenticated_account_id == self.pool_account, "FOREIGN_ACCOUNT")
        _bounded_id(request["command_key"], "command_key"); _revision(request["expected_revision"])
        require(request["definition_sha256"] == DEFINITION_SHA256 and request["registry_sha256"] == self.registry.sha256, "P04M_DEFINITION_MISMATCH")
        payload_sha = sha(canonical(request)); c = self.connection
        c.execute("BEGIN IMMEDIATE")
        try:
            self.initialize()
            existing = self._pool_row()
            if existing is not None:
                ledger = c.execute("SELECT * FROM game_command_ledger WHERE account_id=? AND command_id=?", (account, request["command_key"])).fetchone()
                require(ledger is not None and ledger["command_type"] == "p04m.activate.v1" and ledger["payload_sha256"] == payload_sha, "DUPLICATE_PAYLOAD_MISMATCH")
                result = _json(ledger["result_json"]); require(sha(canonical(result)) == ledger["p09c_result_sha256"], "CORRUPT_STORE")
                self.read_profile(account); c.commit(); return dict(result, replayed=True)
            aggregate = self.read_profile(account)
            public = c.execute("SELECT native_id,profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()
            require(type(request["native_database_id"]) is int and request["native_database_id"] == public["native_id"], "FOREIGN_ACCOUNT")
            revision = aggregate["revision"]
            require(revision == request["expected_revision"], "STALE_REVISION")
            require(revision < 2**31 - 1, "REVISION_EXHAUSTED")
            require(all(r["state"] == "available" for r in aggregate["vehicles"]), "VEHICLE_RESERVED")
            self._pool_activating = True
            if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='p04m_schema'").fetchone():
                c.execute("CREATE TABLE p04m_schema(version TEXT PRIMARY KEY,definition_sha256 TEXT NOT NULL,registry_sha256 TEXT NOT NULL,policy_sha256 TEXT NOT NULL,catalog_sha256 TEXT NOT NULL)")
                c.execute("INSERT INTO p04m_schema VALUES (?,?,?,?,?)", (SCHEMA, DEFINITION_SHA256, self.registry.sha256, POLICY_SHA256, self.catalog.sha256))
                c.execute("""CREATE TABLE p04m_owner(account_id TEXT PRIMARY KEY REFERENCES game_snapshot(account_id),
                    activated_revision INTEGER NOT NULL,base_snapshot_json TEXT NOT NULL,base_snapshot_sha256 TEXT NOT NULL,
                    base_profile_json TEXT NOT NULL,base_profile_sha256 TEXT NOT NULL,base_lineage_json TEXT NOT NULL,base_lineage_sha256 TEXT NOT NULL)""")
                self._rebuild_crew_tables()
                for action in ("UPDATE", "DELETE"):
                    c.execute("CREATE TRIGGER p04m_owner_no_" + action.lower() + " BEFORE " + action + " ON p04m_owner BEGIN SELECT RAISE(ABORT,'pool activation baseline is immutable'); END")
            raw = canonical(aggregate).decode("ascii"); lineage = canonical(self._lineage(account)).decode("ascii")
            c.execute("INSERT INTO p04m_owner VALUES (?,?,?,?,?,?,?,?)", (account, revision + 1, raw, sha(raw.encode("ascii")),
                public["profile_json"], sha(public["profile_json"].encode("ascii")), lineage, sha(lineage.encode("ascii"))))
            self._failpoint("after_pool_owner")
            self._pool_activating = False
            self._save_crew_projection(account, revision + 1, public["profile_json"])
            result = dict(status="activated", account_id=account, revision=revision + 1, policy_sha256=POLICY_SHA256,
                registry_sha256=self.registry.sha256, definition_sha256=DEFINITION_SHA256, new_admission=False, ammunition_granted=0, replayed=False)
            encoded = canonical(result)
            c.execute("INSERT INTO game_command_ledger VALUES (?,?,?,?,?,?,?,?)", (account, request["command_key"], "p04m.activate.v1", payload_sha, revision, revision + 1, encoded.decode("ascii"), sha(encoded)))
            self.read_profile(account); self._failpoint("before_pool_activation_commit"); c.commit(); return result
        except Exception:
            c.rollback(); raise
        finally: self._pool_activating = False

    def _operation_replay(self, ledger, request, profile, *, operation, command, payload_sha):
        if ledger["command_type"].startswith("p04m."):
            # A v1 receipt replays under v1 after a migration; its payload hash
            # binds that contract's own schema/policy/command.
            contract = contract_for_command(ledger["command_type"], "DUPLICATE_PAYLOAD_MISMATCH")
            old_command = contract.operation_command(operation)
            expected = payload_sha if contract is self._crew_contract() else sha(canonical({"schema": contract.SCHEMA,
                "policy_sha256": contract.POLICY_SHA256, "command": old_command, "request": request}))
            require(ledger["command_type"] == old_command and ledger["payload_sha256"] == expected, "DUPLICATE_PAYLOAD_MISMATCH")
            return self._replay_mutation(ledger, request, profile, operation=operation, contract=contract)
        from p04j_crew_store import NativeCrewDismissalStore
        from p04i_crew_store import NativeCrewProgressionStore
        from p04h_crew_store import NativeRosterRecruitmentStore
        from p04f_crew_store import NativeCrewTransferStore
        for contract in (NativeBarracksRecruitmentStore, NativeCrewDismissalStore, NativeCrewProgressionStore, NativeRosterRecruitmentStore, NativeCrewTransferStore):
            try: old_command = contract.operation_command(operation)
            except TransactionError: continue
            if ledger["command_type"] == old_command:
                expected = sha(canonical({"schema": contract.SCHEMA, "policy_sha256": contract.POLICY_SHA256, "command": old_command, "request": request}))
                require(ledger["payload_sha256"] == expected, "DUPLICATE_PAYLOAD_MISMATCH")
                return self._replay_mutation(ledger, request, profile, operation=operation, contract=contract)
        previous = self._legacy_contract; self._legacy_contract = True
        try: return super()._operation_replay(ledger, request, profile, operation=operation,
            command=NativeBarracksRecruitmentStore.operation_command(operation), payload_sha=payload_sha)
        finally: self._legacy_contract = previous

    def _operation_vehicle_id(self, profile, stored, native):
        if not self.pool_active(): return super()._operation_vehicle_id(profile, stored, native)
        rows = [r for r in profile["research"]["vehicles"] if r["native_id"] == native]
        require(len(rows) == 1, "UNKNOWN_VEHICLE")
        return rows[0]["vehicle_inventory_id"]

    def _retirement_contract(self, command):
        for contract in (CrewContract, CrewContractV2):
            if command == contract.DISMISS_COMMAND: return contract
        return super()._retirement_contract(command)

    def _historical_member_matches(self, historical, current):
        if any(historical[key] != current[key] for key in ("native_id", "crew_id", "role")): return False
        if historical["descriptor_hex"] == current["descriptor_hex"]: return True  # same bytes: nothing learned
        before = decode(bytes.fromhex(historical["descriptor_hex"])); after = decode(bytes.fromhex(current["descriptor_hex"]))
        return (after["skills"][:len(before["skills"])] == before["skills"]
            and (not before["skills"] or after["last_skill_level"] >= before["last_skill_level"])
            and all(before[key] == after[key] for key in before if key not in ("skills", "last_skill_level")))

    def _next_aggregate(self, before, research, revision):
        value = ResearchStore._next_aggregate(before, research, revision)
        if "pool" not in before: return value
        value["crew_inventory"]["vehicles"] = self._vehicle_map(before["account_id"], research)
        mounts = {row["vehicle_id"]: row for row in value["ammunition"]}
        for owned in research["vehicles"]:
            p = self.registry.by_vehicle.get(owned["vehicle_id"])
            if p is None: continue
            mount_id = self.mount_id_of(owned)
            row = mounts.get(owned["vehicle_inventory_id"])
            if row is not None and row["mount_id"] != mount_id:
                # CONTENT-0 4: another turret x gun pair (see _mount_change).
                require(not any(row["loaded"].values()), "UNLOAD_AMMUNITION_REQUIRED")
                value["ammunition"].remove(row); row = None
            if row is None:
                value["ammunition"].append({"vehicle_id": owned["vehicle_inventory_id"], "mount_id": mount_id,
                    "loaded": {key: 0 for key in self.mounts[mount_id].shell_ids}})
        value["ammunition"].sort(key=lambda row: row["vehicle_id"])
        return value

    # CONTENT-0: Shop.buyVehicle with BUY_VEHICLE_FLAG.CREW and/or SHELLS (see
    # docs/research/CONTENT0_BUY_WITH_CREW.md). Free like the rest of P09E: the crew
    # comes from the account's lifetime allocator at the tariff level, the base
    # ammunition (0.9.1 getDefaultAmmoForGun) is bought free and loaded; the shared
    # depot is not touched. All of it inside the research purchase transaction.
    def _equipment_plan(self, before, research, payload):
        """Pure: new crew rows and loaded counts of one equipped purchase."""
        require(self.pool_active() and "pool" in before, "AUTOBUY_CREW_SHELLS_UNSUPPORTED")
        account = before["account_id"]
        require(account == self.pool_account, "FOREIGN_ACCOUNT")
        old = {r["vehicle_inventory_id"] for r in before["research"]["vehicles"]}
        new = [r for r in research["vehicles"] if r["vehicle_inventory_id"] not in old]
        require(len(new) == 1 and new[0]["vehicle_id"] == payload["vehicle_id"], "CORRUPT_STORE")
        owned = new[0]
        p = self.registry.by_vehicle.get(owned["vehicle_id"])
        require(p is not None, "UNSUPPORTED_MOUNT")
        members, loaded = [], {}
        if payload["crew_role_level"]:
            contract = self._crew_contract(account)
            crew = dict(before["crew_inventory"], vehicles=self._vehicle_map(account, research))
            after = contract.plan_purchase(crew, owned["native_id"], payload["crew_role_level"], account_id=account)
            members = [r for r in after["members"] if r["native_id"] >= crew["next_native_id"]]
        if payload["load_shells"]:
            from content0_default_ammo import default_ammo
            mount = self.mounts[p.assembly_id]
            source = default_ammo(p.kind)
            require(source is not None, "AMMUNITION_CONFIGURATION_UNSUPPORTED")
            capacity, counts = source
            by_cd = {self.shells[key].native_compact_id: key for key in mount.shell_ids}
            require(capacity == mount.capacity and set(counts) == set(by_cd) and sum(counts.values()) <= capacity,
                    "AMMUNITION_CONFIGURATION_UNSUPPORTED")
            loaded = {by_cd[cd]: count for cd, count in counts.items()}
        return {"vehicle_native_id": owned["native_id"], "crew_role_level": payload["crew_role_level"],
                "members": members, "loaded": loaded}

    def _apply_purchase_crew(self, crew, equipment, contract):
        value = deepcopy(crew)
        rows = equipment["members"]
        require(type(rows) is list and [r["native_id"] for r in rows]
                == list(range(value["next_native_id"], value["next_native_id"] + len(rows))), "CORRUPT_STORE")
        value["members"] = sorted(value["members"] + deepcopy(rows), key=lambda r: r["native_id"])
        value["next_native_id"] += len(rows)
        value.update(free_recruitment_left=contract.CAPACITY + 1 - value["next_native_id"],
                     configuration_revision=value["configuration_revision"] + 1)
        native_crew(value, contract)
        return value

    def _expected_aggregate(self, before, research, revision, equipment):
        value = self._next_aggregate(before, research, revision)
        if equipment is None: return value
        require("pool" in before and type(equipment) is dict
                and set(equipment) == {"vehicle_native_id", "crew_role_level", "members", "loaded"}, "CORRUPT_STORE")
        if equipment["members"]:
            value["crew_inventory"] = self._apply_purchase_crew(value["crew_inventory"], equipment, self._crew_contract(before["account_id"]))
        if equipment["loaded"]:
            owned = next(r for r in research["vehicles"] if r["native_id"] == equipment["vehicle_native_id"])
            row = next(r for r in value["ammunition"] if r["vehicle_id"] == owned["vehicle_inventory_id"])
            require(set(row["loaded"]) == set(equipment["loaded"]), "CORRUPT_STORE")
            row["loaded"] = dict(equipment["loaded"])
        return value

    def _equip_purchase(self, account, before, research, payload):
        equipment = self._equipment_plan(before, research, payload)
        c = self.connection
        require(c.in_transaction, "POOL_TRANSACTION_REQUIRED")
        if equipment["members"]:
            contract = self._crew_contract(account)
            crew = dict(before["crew_inventory"], vehicles=self._vehicle_map(account, research))
            after = self._apply_purchase_crew(crew, equipment, contract)
            self._persist_crew_members(account, crew, after, None, before["revision"] + 1)
            require(c.execute("UPDATE p04d_crew_meta SET next_native_id=?,free_left=?,configuration_revision=? WHERE account_id=? AND configuration_revision=?",
                (after["next_native_id"], after["free_recruitment_left"], after["configuration_revision"], account, crew["configuration_revision"])).rowcount == 1, "STALE_CREW")
            self._failpoint("after_purchase_crew")
        if equipment["loaded"]:
            self._ensure_pool_rows(account)
            owned = next(r for r in research["vehicles"] if r["native_id"] == equipment["vehicle_native_id"])
            mount = self.mounts[self.mount_id_of(owned)]
            layout = [n for key in mount.shell_ids for n in (self.shells[key].native_compact_id, equipment["loaded"][key])]
            require(c.execute("UPDATE p09c_ammo_mount SET loaded_json=? WHERE account_id=? AND vehicle_id=?",
                (canonical(equipment["loaded"]).decode("ascii"), account, owned["vehicle_inventory_id"])).rowcount == 1, "CORRUPT_STORE")
            require(c.execute("UPDATE p09d_native_layout SET layout_json=? WHERE account_id=? AND native_vehicle_id=?",
                (json.dumps(layout), account, owned["native_id"])).rowcount == 1, "CORRUPT_STORE")
        return equipment

    def purchase_updates(self, before, final, response, wire_revision):
        """Native Account.update chain of one equipped purchase: the vehicle record, one
        tankman (inventory 8 + the vehicle's crew list + freeTMenLeft) per part, then the
        loaded shells/shellsLayout, packed greedily into <=240-byte diffs."""
        from p09e_research_projection import delta_tree, chained_updates
        from p09e_research_store import EQUIPPED_UPDATES
        equipment = response["details"]["equipment"]
        native = equipment["vehicle_native_id"]
        parts = []
        if equipment["members"]:
            _, seats = native_crew(final["crew_inventory"], self._crew_contract(before["account_id"]))
            slots, left = [None] * len(seats[native]), before["crew_inventory"]["free_recruitment_left"]
            for row in sorted(equipment["members"], key=lambda r: r["seat"]):
                slots[row["seat"]] = row["native_id"]; left -= 1
                parts.append({"inventory": {8: {"vehicle": {row["native_id"]: native},
                                                "compDescr": {row["native_id"]: bytes.fromhex(row["descriptor_hex"])}},
                                            1: {"crew": {native: list(slots)}}},
                              "stats": {"freeTMenLeft": left}})
            require(slots == seats[native] and left == final["crew_inventory"]["free_recruitment_left"], "INVALID_NATIVE_PROJECTION")
        if equipment["loaded"]:
            owned = next(r for r in final["research"]["vehicles"] if r["native_id"] == native)
            mount = self.mounts[self.mount_id_of(owned)]
            layout = [n for key in mount.shell_ids for n in (self.shells[key].native_compact_id, equipment["loaded"][key])]
            parts.append({"inventory": {1: {"shells": {native: list(layout)}, "shellsLayout": {native: {
                (mount.turret_native_compact_id, mount.gun_native_compact_id): list(layout)}}}}})
        first = delta_tree(self.catalog, before["research"], final["research"], wire_revision)
        return chained_updates(first, parts, wire_revision, EQUIPPED_UPDATES)

    def _pool_ammo_response(self, request, revision, depot):
        mount, desired = self._validate_layout(request["layout"])
        native, layout = request["layout"][1], request["layout"][3:3 + request["layout"][2]]
        data = {"prevRev": request["wire_revision"], "rev": request["wire_revision"] + 1,
            "inventory": {1: {"shells": {native: [n if i % 2 else abs(n) for i, n in enumerate(layout)]},
                "shellsLayout": {native: {(mount.turret_native_compact_id, mount.gun_native_compact_id): layout}}},
                10: {self.shells[key].native_compact_id: depot[key] for key in mount.shell_ids}}}
        return dict(status="serviced", account_id=request["account_id"], native_database_id=request["native_database_id"],
            command_key=request["command_key"], revision=revision, wire_revision=request["wire_revision"] + 1,
            update_hex=encode(data, MAX_UPDATE).hex(), replayed=False, result_code=0)

    def service(self, request, *, authenticated_account_id):
        native = request.get("layout", [None, None])[1] if type(request) is dict and type(request.get("layout")) is list and len(request["layout"]) > 1 else None
        if not self.pool_active() or type(native) is not int or native in (1, 2):
            return super().service(request, authenticated_account_id=authenticated_account_id)
        return self._guarded(self._pool_service, request, authenticated_account_id=authenticated_account_id)

    def _pool_service(self, request, *, authenticated_account_id):
        require(type(request) is dict and set(request) == REQUEST_FIELDS, "INVALID_INPUT")
        account, key = request["account_id"], request["command_key"]
        require(account == authenticated_account_id == self.pool_account, "FOREIGN_ACCOUNT")
        _bounded_id(key, "command_key"); _revision(request["expected_revision"])
        require(type(request["wire_revision"]) is int and 1 <= request["wire_revision"] < 2**31 - 1
            and len(canonical(request)) <= 4096, "INVALID_INPUT")
        payload = sha(canonical({"request": request, "registry_sha256": self.registry.sha256, "policy_sha256": POLICY_SHA256}))
        c = self.connection; c.execute("BEGIN IMMEDIATE")
        try:
            profile = self.read_profile(account)
            public_before = c.execute("SELECT native_id,profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()
            require(type(request["native_database_id"]) is int and request["native_database_id"] == public_before["native_id"], "FOREIGN_ACCOUNT")
            mount, desired = self._validate_layout(request["layout"])
            ledger = c.execute("SELECT * FROM game_command_ledger WHERE account_id=? AND command_id=?", (account, key)).fetchone()
            if ledger is not None:
                require(ledger["command_type"] == "p04m.set_ammunition.v1" and ledger["payload_sha256"] == payload, "DUPLICATE_PAYLOAD_MISMATCH")
                result = _json(ledger["result_json"])
                require(sha(canonical(result)) == ledger["p09c_result_sha256"]
                    and set(result) == {"schema", "request", "before_loaded", "before_depot", "response"}
                    and result["schema"] == SCHEMA and result["request"] == request, "CORRUPT_STORE")
                loaded, depot = result["before_loaded"], result["before_depot"]
                require(type(loaded) is dict and type(depot) is dict and set(loaded) == set(depot) == set(mount.shell_ids)
                    and all(type(n) is int and 0 <= n <= mount.capacity for n in loaded.values()) and sum(loaded.values()) <= mount.capacity
                    and all(type(n) is int and 0 <= n <= 1000000 for n in depot.values()), "CORRUPT_STORE")
                remaining = {shell: depot[shell] + loaded[shell] - desired[shell] for shell in mount.shell_ids}
                require(all(0 <= n <= 1000000 for n in remaining.values()) and ledger["source_revision"] == request["expected_revision"]
                    and ledger["destination_revision"] == ledger["source_revision"] + 1 <= profile["revision"], "CORRUPT_STORE")
                expected = self._pool_ammo_response(request, ledger["destination_revision"], remaining)
                native = c.execute("SELECT * FROM p09d_native_command WHERE account_id=? AND command_id=?", (account, key)).fetchone()
                require(result["response"] == expected and native is not None and native["request_sha256"] == sha(canonical(request))
                    and native["response_json"] == canonical(expected).decode("ascii") and native["response_sha256"] == sha(canonical(expected)), "CORRUPT_STORE")
                c.commit(); return dict(expected, replayed=True)
            require(profile["revision"] == request["expected_revision"], "STALE_REVISION")
            require(profile["revision"] < 2**31 - 1, "REVISION_EXHAUSTED")
            require(request["layout"][0] == 5, "SHOP_REVISION_MISMATCH")
            owned = next(r for r in profile["research"]["vehicles"] if r["native_id"] == request["layout"][1])
            # CONTENT-0 4: the layout of the current pair's mount; a pair outside the build table stays unsupported.
            require(self.pair_mounted(owned), "AMMUNITION_CONFIGURATION_UNSUPPORTED")
            ammo = next(r for r in profile["ammunition"] if r["vehicle_id"] == owned["vehicle_inventory_id"])
            require(ammo["mount_id"] == mount.mount_id, "CORRUPT_STORE")
            loaded = ammo["loaded"]; depot = {shell: profile["depot"][self.depot_key[shell]] for shell in mount.shell_ids}
            remaining = {shell: depot[shell] + loaded[shell] - desired[shell] for shell in mount.shell_ids}
            require(all(n >= 0 for n in remaining.values()), "INSUFFICIENT_STOCK")
            require(all(n <= 1000000 for n in remaining.values()), "DEPOT_OVERFLOW")
            for shell, n in remaining.items():
                require(c.execute("UPDATE p09c_ammo_depot SET quantity=? WHERE account_id=? AND shell_id=?", (n, account, self.depot_key[shell])).rowcount == 1, "CORRUPT_STORE")
            self._failpoint("after_depot_update")
            require(c.execute("UPDATE p09c_ammo_mount SET loaded_json=? WHERE account_id=? AND vehicle_id=?", (canonical(desired).decode("ascii"), account, owned["vehicle_inventory_id"])).rowcount == 1, "CORRUPT_STORE")
            c.execute("UPDATE p09d_native_layout SET layout_json=? WHERE account_id=? AND native_vehicle_id=?", (json.dumps(request["layout"][3:3 + request["layout"][2]]), account, owned["native_id"]))
            self._failpoint("after_ammo_update")
            destination = profile["revision"] + 1
            self._save_crew_projection(account, destination, public_before["profile_json"])
            response = self._pool_ammo_response(request, destination, remaining)
            result = dict(schema=SCHEMA, request=request, before_loaded=loaded, before_depot=depot, response=response)
            raw = canonical(result); encoded = canonical(response)
            c.execute("INSERT INTO game_command_ledger VALUES (?,?,?,?,?,?,?,?)", (account, key, "p04m.set_ammunition.v1", payload, profile["revision"], destination, raw.decode("ascii"), sha(raw)))
            c.execute("INSERT INTO p09d_native_command VALUES (?,?,?,?,?)", (account, key, sha(canonical(request)), encoded.decode("ascii"), sha(encoded)))
            self.read_profile(account); self._failpoint("before_commit"); c.commit(); return response
        except Exception:
            c.rollback(); raise

    def publish(self, source, account_id, fixture_root):
        if self.pool_active():
            from p04m_pool_projection import PoolProjectionSource
            if not isinstance(source, PoolProjectionSource): source = PoolProjectionSource(source, self)
            fixture_root = Path(fixture_root) / "p04m-v1"
        return super().publish(source, account_id, fixture_root)

    @staticmethod
    def member_role_level(row): return decode(bytes.fromhex(row["descriptor_hex"]))["role_level"]

    @staticmethod
    def member_skills(row):
        raw = bytes.fromhex(row["descriptor_hex"])
        if raw[1] in (13, 28) and raw[2] != 2:
            return NativeBarracksRecruitmentStore.member_skills(row)
        require(not decode(raw)["skills"], "CORRUPT_STORE")
        return []
