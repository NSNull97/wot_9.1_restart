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
        # The ammo catalog hash pinned by the gateway covers the legacy mounts only;
        # BATTLE-ANY generated mounts are bound by the activated catalog hash.
        legacy = {key: value for key, value in self.mounts.items()
                  if key in MOUNTS or key[:-len("-stock")] in PINS}
        legacy_shells = {key for mount in legacy.values() for key in mount.shell_ids}
        self.ammo_catalog_sha256 = sha(canonical({key: vars(value) for key, value in sorted(legacy.items())}
            | {"shells": {key: vars(value) for key, value in sorted(self.shells.items()) if key in legacy_shells}}))

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
        # A v2 marker row exists only for an activated pool owner (set_crew_contract).
        if type(raw) is str and len(raw) > MAX_JSON and self._crew_contract() is CrewContractV2:
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
        depot_rows = self.connection.execute("SELECT shell_id,quantity FROM p09c_ammo_depot WHERE account_id=? ORDER BY shell_id LIMIT ?", (account, len(self.shells) + 1)).fetchall()
        depot = {row[0]: row[1] for row in depot_rows}
        require(len(depot_rows) == len(self.shells) and set(depot) == set(self.shells)
            and all(type(n) is int and 0 <= n <= 1000000 for n in depot.values()), "CORRUPT_STORE")
        expected = {r["vehicle_inventory_id"]: self.registry.by_vehicle[r["vehicle_id"]].assembly_id for r in self._research(account)["vehicles"] if r["vehicle_id"] in self.registry.by_vehicle}
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
        value["research"].update(garage_slots=aggregate["research"]["garage_slots"], unlocked_count=len(aggregate["research"]["unlocked"]), depot_types=len(aggregate["research"]["depot"]))
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
        for key in sorted(self.shells):
            require(self.connection.execute("UPDATE p09c_ammo_depot SET quantity=MAX(quantity,?) WHERE account_id=? AND shell_id=?",
                (ECONOMY_SHELL_MINIMUM, account, key)).rowcount == 1, "CORRUPT_STORE")

    def _ensure_pool_rows(self, account):
        require(self.connection.in_transaction, "POOL_TRANSACTION_REQUIRED")
        for key in self.shells:
            self.connection.execute("INSERT OR IGNORE INTO p09c_ammo_depot VALUES (?,?,0)", (account, key))
        for owned in self._research(account)["vehicles"]:
            p = self.registry.by_vehicle.get(owned["vehicle_id"])
            if p is None: continue
            mount = self.mounts[p.assembly_id]
            loaded = {key: 0 for key in mount.shell_ids}
            exists = self.connection.execute("SELECT 1 FROM p09c_ammo_mount WHERE account_id=? AND vehicle_id=?", (account, owned["vehicle_inventory_id"])).fetchone()
            if exists is None:
                self.connection.execute("INSERT INTO p09c_ammo_mount VALUES (?,?,?,?)", (account, owned["vehicle_inventory_id"], p.assembly_id, canonical(loaded).decode("ascii")))
                layout = [n for key in mount.shell_ids for n in (self.shells[key].native_compact_id, 0)]
                self.connection.execute("INSERT INTO p09d_native_layout VALUES (?,?,?)", (account, owned["native_id"], json.dumps(layout)))

    def _save_crew_projection(self, account, revision, before):
        if self.pool_active(): self._ensure_pool_rows(account)
        return super()._save_crew_projection(account, revision, before)

    def _validate_layout(self, layout):
        if not self.pool_active(): return super()._validate_layout(layout)
        require(type(layout) is list and len(layout) == 16 and all(type(v) is int and -2**31 <= v < 2**31 for v in layout), "INVALID_INPUT")
        require(layout[0] in (3, 4, 5), "SHOP_REVISION_MISMATCH")
        require(layout[2] == layout[9] == 6 and layout[10:] == [0] * 6, "INVALID_INPUT")
        owned = next((r for r in self._research(self.pool_account)["vehicles"] if r["native_id"] == layout[1]), None)
        require(owned is not None, "UNKNOWN_VEHICLE")
        p = self.registry.by_vehicle.get(owned["vehicle_id"])
        require(p is not None, "UNSUPPORTED_MOUNT")
        mount = self.mounts[p.assembly_id]
        expected = {self.shells[key].native_compact_id: key for key in mount.shell_ids}
        values = layout[3:9]
        require({abs(values[i]) for i in (0, 2, 4)} == set(expected), "INCOMPATIBLE_SHELL")
        require(all(0 <= values[i] <= mount.capacity for i in (1, 3, 5)), "INVALID_QUANTITY")
        require(sum(values[i] for i in (1, 3, 5)) <= mount.capacity, "CAPACITY_EXCEEDED")
        return mount, {expected[abs(values[i])]: values[i + 1] for i in (0, 2, 4)}

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
                layout = json.loads(raw); mount, counts = self._validate_layout([5, native, 6, *layout, 6, 0, 0, 0, 0, 0, 0])
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
            if p is not None and owned["vehicle_inventory_id"] not in mounts:
                mount = self.mounts[p.assembly_id]
                value["ammunition"].append({"vehicle_id": owned["vehicle_inventory_id"], "mount_id": p.assembly_id,
                    "loaded": {key: 0 for key in mount.shell_ids}})
        value["ammunition"].sort(key=lambda row: row["vehicle_id"])
        return value

    def _pool_ammo_response(self, request, revision, depot):
        mount, desired = self._validate_layout(request["layout"])
        native, layout = request["layout"][1], request["layout"][3:9]
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
            stock = dict(self.registry.by_vehicle[owned["vehicle_id"]].modules)
            require(all(owned["modules"][role] == stock[role] for role in ("turret", "gun")), "AMMUNITION_CONFIGURATION_UNSUPPORTED")
            ammo = next(r for r in profile["ammunition"] if r["vehicle_id"] == owned["vehicle_inventory_id"])
            loaded = ammo["loaded"]; depot = {shell: profile["depot"][shell] for shell in mount.shell_ids}
            remaining = {shell: depot[shell] + loaded[shell] - desired[shell] for shell in mount.shell_ids}
            require(all(n >= 0 for n in remaining.values()), "INSUFFICIENT_STOCK")
            require(all(n <= 1000000 for n in remaining.values()), "DEPOT_OVERFLOW")
            for shell, n in remaining.items():
                require(c.execute("UPDATE p09c_ammo_depot SET quantity=? WHERE account_id=? AND shell_id=?", (n, account, shell)).rowcount == 1, "CORRUPT_STORE")
            self._failpoint("after_depot_update")
            require(c.execute("UPDATE p09c_ammo_mount SET loaded_json=? WHERE account_id=? AND vehicle_id=?", (canonical(desired).decode("ascii"), account, owned["vehicle_inventory_id"])).rowcount == 1, "CORRUPT_STORE")
            c.execute("UPDATE p09d_native_layout SET layout_json=? WHERE account_id=? AND native_vehicle_id=?", (json.dumps(request["layout"][3:9]), account, owned["native_id"]))
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
