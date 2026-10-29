"""Opt-in version2 owned mixed-ammunition reservations.

Only trusted configured source facts enter the constructor. Incoming requests
contain owner/command/selection/results, never loadouts, source paths or grants.
The retained version1 implementation and its policy are not modified.
"""
from copy import deepcopy
from pathlib import Path
import json

from game_profile_tx import TransactionError, _bounded_id, _revision
from p09d_ammo_store import require, sha
from p09d_ammo_projection import canonical
from p09e_research_store import _json
from p04m_pool_store import PoolStore
from p04m_stock_registry import mixed_admission
from p08b_battle_store import _uuid, _integer, REASONS, MAX_RESULT_BYTES, MAX_RESULT_REQUEST
from p08c_battle_results import results_value
from destructible_catalog import json_value, no_links
from p06t_terminal import TerminalPolicy, MANIFEST_SHA256

SCHEMA = "p06t-owned-mixed-ammunition.v2"
SOURCE_SHA256 = "6af1bdc74aff853360b282c3850e0aa3c97c856a7d39835c198c67fdeb342430"
POLICY = {"id": "test_lab.profile13-stock-mixed-free-repair.v2", "version": 2,
    "shell_catalog_sha256": SOURCE_SHA256, "admitted": ["ms1-stock", "is7-stock"],
    "new_three": "OWNER_ACCEPTANCE_REQUIRED", "loadout": "actual-complete-crew-exact-six-component-stock-three-owned-stacks",
    "initial_shell": "first-nonempty-in-source-shot-order", "finish": "persist-actual-per-stack-terminal-HP-free-full-repair",
    "restart": "atomic-abort-refund-original-per-stack-full-repair", "credits": 0, "xp": 0,
    "per_shot_durability": False, "clip_quantity_convention": "test_lab-quantities-include-clip-historical-convention-UNKNOWN",
    "terminal_policy_manifest_sha256": MANIFEST_SHA256, "terminal": "actual-devices-crew-fire-death-free-full-restoration"}
POLICY_SHA256 = sha(canonical(POLICY))
COMMON = {"version", "operation", "account_id", "native_database_id", "command_key", "expected_revision", "run_id"}
EXTRA = {"run_open": set(), "inspect": set(), "admit": {"battle_id", "native_inventory_id"},
    "finish": {"battle_id", "native_inventory_id", "reservation_id", "remaining_ammunition", "terminal_hp", "reason", "terminal_state_json"}}
MAX_REPLY = 8192
REJECTIONS = frozenset(("STALE_REVISION", "RUN_FENCED", "RUN_NOT_OPEN", "VEHICLE_RESERVED", "UNKNOWN_VEHICLE",
    "BATTLE_PROFILE_UNSUPPORTED", "OWNER_ACCEPTANCE_REQUIRED", "INCOMPLETE_CREW", "AMMUNITION_EMPTY",
    "AMMUNITION_UNSUPPORTED", "RESERVATION_TERMINAL", "RESERVATION_MISMATCH", "DUPLICATE_PAYLOAD_MISMATCH",
    "INVALID_RESULT", "RESULT_MISMATCH", "INVALID_TERMINAL_STATE", "RUN_HAS_LEGACY_RESERVATION", "MIXED_RESERVATION_ACTIVE"))


def validate_request(value, account):
    require(type(value) is dict and type(value.get("operation")) is str and value["operation"] in EXTRA, "INVALID_INPUT")
    natural = value["operation"] == "finish" and value.get("reason") == "battle_finished"
    require(set(value) == COMMON | EXTRA[value["operation"]] | ({"results_json"} if natural else set())
        and type(value["version"]) is int and value["version"] == 2, "INVALID_INPUT")
    require(value["account_id"] == account, "FOREIGN_ACCOUNT"); _uuid(account); _uuid(value["run_id"])
    _bounded_id(value["command_key"], "command_key"); _integer(value["native_database_id"], 1); _revision(value["expected_revision"])
    key = value["command_key"]
    require(key.isascii() and all(c.isalnum() or c in "_:-" for c in key), "INVALID_INPUT")
    if value["operation"] in ("admit", "finish"):
        _integer(value["native_inventory_id"], 1)
        battle = value["battle_id"]
        require(type(battle) is str and battle.startswith(value["run_id"] + ":"), "INVALID_INPUT")
        tail = battle[37:]
        require(tail.isascii() and tail.isdecimal() and tail[0] != "0" and len(tail) <= 20 and int(tail) <= 2**64 - 1, "INVALID_INPUT")
    if value["operation"] == "finish":
        _bounded_id(value["reservation_id"], "reservation_id"); _integer(value["terminal_hp"], 0, 100000)
        require(type(value["reason"]) is str and value["reason"] in REASONS, "INVALID_INPUT")
        require(type(value["terminal_state_json"]) is str and len(value["terminal_state_json"].encode("utf8"))<=8192,"INVALID_INPUT")
        value=dict(value,terminal_state_json=canonical(_json(value["terminal_state_json"])).decode("ascii"))
        remaining = value["remaining_ammunition"]
        require(type(remaining) is list and len(remaining) == 3, "INVALID_INPUT")
        for row in remaining:
            require(type(row) is dict and set(row) == {"shell_compact_id", "count"}, "INVALID_INPUT")
            _integer(row["shell_compact_id"], 1); _integer(row["count"], 0, 160)
    if natural:
        require(type(value["results_json"]) is str and len(value["results_json"].encode("utf8")) <= MAX_RESULT_BYTES, "INVALID_INPUT")
        value = dict(value, results_json=canonical(results_value(value["results_json"])).decode("ascii"))
    require(len(canonical(value)) <= (MAX_RESULT_REQUEST if natural else 16384 if value["operation"]=="finish" else 2048), "INVALID_INPUT")
    return deepcopy(value)


def validate_results_request(request,account):
    require(type(request)is dict and set(request)=={"version","operation","account_id","native_database_id","command_key","arena_id"}
        and type(request["version"])is int and request["version"]==2 and type(request["operation"])is str and request["operation"]in("query","ack"),"INVALID_INPUT")
    require(request["account_id"]==account,"FOREIGN_ACCOUNT");_uuid(account)
    _bounded_id(request["command_key"],"command_key");_integer(request["native_database_id"],1)
    key=request["command_key"];require(key.isascii() and all(c.isalnum()or c in"_:-"for c in key),"INVALID_INPUT")
    arena=request["arena_id"]
    require(type(arena)is str and arena.isascii() and arena.isdecimal() and arena[0]!="0" and len(arena)<=19 and int(arena)<=2**63-1,"INVALID_INPUT")
    require(len(canonical(request))<=2048,"INVALID_INPUT");return deepcopy(request)


class MixedAmmoStore(PoolStore):
    def _ammo_loss_fence(self):
        # Lazy import avoids changing the immutable v2 policy/source namespace.
        # Only the explicit new writer class carries this trusted capability.
        from p06t_ammo_loss_store import require_loss_compatible
        return require_loss_compatible(self.connection,self.pool_account,
            contract=getattr(self,"AMMO_LOSS_CONTRACT",None))

    def read_profile(self,account_id):
        if hasattr(self,"pool_account"):self._ammo_loss_fence()
        return super().read_profile(account_id)

    def _guarded(self,function,*args,**kwargs):
        self._ammo_loss_fence()
        return super()._guarded(function,*args,**kwargs)

    def __init__(self, path, catalog, *, account_id, shell_catalog, terminal_policy, failpoint=None):
        super().__init__(path, catalog, account_id=account_id, failpoint=failpoint)
        self.terminal_policy=TerminalPolicy.from_manifest(no_links(terminal_policy))
        source = no_links(shell_catalog).resolve(strict=True)
        require(source.is_file() and source.stat().st_size == 26870, "P06T_SOURCE_REQUIRED")
        with source.open("rb") as stream: raw = stream.read(32769)
        require(sha(raw) == SOURCE_SHA256, "P06T_SOURCE_MISMATCH")
        document = json_value(raw, limit=32768, nodes=6000, depth=12)
        require(document["schema"] == "p06t-shell-catalog.v1" and len(document["mounts"]) == 8, "P06T_SOURCE_MISMATCH")
        self.mixed_mounts = {row["id"]: row for row in document["mounts"] if row["id"] in self.mounts}
        generated = self._generated_mounts()
        require(set(self.mixed_mounts) | set(generated) == set(self.mounts) and not set(self.mixed_mounts) & set(generated), "P06T_SOURCE_MISMATCH")
        if generated:
            self.terminal_policy = self.terminal_policy.with_generated({key[:-len("-stock")]: row for key, row in generated.items()})
        for key, mount in self.mounts.items():
            if key in generated:
                continue
            data = self.mixed_mounts[key]
            require(data["max_ammo"] == mount.capacity and data["clip_count"] == data["burst_count"] == 1
                and data["vehicle_type_compact_descr"] == mount.vehicle_native_compact_id
                and data["gun_compact_descr"] == mount.gun_native_compact_id
                and [row["compact_descr"] for row in data["shots"]] == [self.shells[s].native_compact_id for s in mount.shell_ids]
                and [row["family"] for row in data["shots"]] == [self.shells[s].kind for s in mount.shell_ids], "P06T_SOURCE_MISMATCH")

    def _generated_mounts(self):
        """{assembly_id: generated table row} of BATTLE-ANY catalog kinds; each must
        equal its pool mount exactly (capacity, type/gun IDs, ordered shells)."""
        import catalog_v1
        if not catalog_v1.active():
            return {}
        import battle_any
        from p04m_stock_registry import PINS
        result = {}
        for kind, p in self.registry.profiles.items():
            if kind in PINS or p.assembly_id not in self.mounts or p.assembly_id in self.mixed_mounts:
                continue
            row = battle_any.profile(p.vehicle_id)
            require(row is not None and row["status"] == "generated" and row["kind"] == kind, "P06T_SOURCE_MISMATCH")
            mount = self.mounts[p.assembly_id]
            require(row["gun"]["max_ammo"] == mount.capacity and not row["gun"]["burst"]
                and row["identity"]["type_compact_id"] == mount.vehicle_native_compact_id
                and row["identity"]["module_compact_ids"]["gun"] == mount.gun_native_compact_id
                and [s["compact_descr"] for s in row["shots"]] == [self.shells[s].native_compact_id for s in mount.shell_ids]
                and [s["family"] for s in row["shots"]] == [self.shells[s].kind for s in mount.shell_ids], "P06T_SOURCE_MISMATCH")
            result[p.assembly_id] = row
        return result

    def _mixed_tables(self):
        names = {r[0] for r in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'p06t_%'")}
        require(not names or names == {"p06t_schema", "p06t_owner", "p06t_reservation", "p06t_result", "p06t_command"}, "UNSUPPORTED_MIXED_SCHEMA")
        if names:
            rows = self.connection.execute("SELECT * FROM p06t_schema").fetchall()
            require([tuple(r) for r in rows] == [(SCHEMA, POLICY_SHA256, SOURCE_SHA256, self.catalog.sha256)], "UNSUPPORTED_MIXED_SCHEMA")
        return bool(names)

    def mixed_active(self):
        return self._mixed_tables() and self.connection.execute("SELECT 1 FROM p06t_owner WHERE account_id=?", (self.pool_account,)).fetchone() is not None

    def activate_mixed(self, *, account_id, authenticated_account_id, expected_revision=None, native_database_id=None):
        self._ammo_loss_fence()
        require(account_id == authenticated_account_id == self.pool_account, "FOREIGN_ACCOUNT")
        c = self.connection; c.execute("BEGIN IMMEDIATE")
        try:
            aggregate = self.read_profile(account_id)
            require(self.pool_active(),"P06T_POOL_ACTIVATION_REQUIRED")
            if expected_revision is not None:require(aggregate["revision"]==expected_revision,"STALE_REVISION")
            if native_database_id is not None:require(self._project_profile(account_id,aggregate)["native_database_id"]==native_database_id,"FOREIGN_ACCOUNT")
            require(all(row["state"] == "available" for row in aggregate["vehicles"]), "VEHICLE_RESERVED")
            if not self._mixed_tables():
                c.execute("CREATE TABLE p06t_schema(version TEXT PRIMARY KEY,policy_sha256 TEXT NOT NULL,source_sha256 TEXT NOT NULL,catalog_sha256 TEXT NOT NULL)")
                c.execute("INSERT INTO p06t_schema VALUES (?,?,?,?)", (SCHEMA, POLICY_SHA256, SOURCE_SHA256, self.catalog.sha256))
                c.execute("CREATE TABLE p06t_owner(account_id TEXT PRIMARY KEY REFERENCES game_snapshot(account_id),activated_revision INTEGER NOT NULL)")
                c.execute("""CREATE TABLE p06t_reservation(account_id TEXT NOT NULL,reservation_id TEXT NOT NULL,
                    run_id TEXT NOT NULL,battle_id TEXT NOT NULL,native_inventory_id INTEGER NOT NULL,vehicle_inventory_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('active','finished','aborted_restart')),frozen_json TEXT NOT NULL,frozen_sha256 TEXT NOT NULL,
                    source_revision INTEGER NOT NULL,admitted_revision INTEGER NOT NULL,result_json TEXT,result_sha256 TEXT,finished_revision INTEGER,
                    PRIMARY KEY(account_id,reservation_id),UNIQUE(account_id,battle_id),FOREIGN KEY(account_id) REFERENCES p06t_owner(account_id),
                    FOREIGN KEY(account_id,run_id) REFERENCES p08b_run(account_id,run_id),
                    FOREIGN KEY(account_id,vehicle_inventory_id) REFERENCES game_vehicle(account_id,vehicle_id),
                    CHECK((status='active' AND result_json IS NULL AND result_sha256 IS NULL AND finished_revision IS NULL)
                        OR (status!='active' AND result_json IS NOT NULL AND result_sha256 IS NOT NULL AND finished_revision IS NOT NULL)))""")
                c.execute("CREATE UNIQUE INDEX p06t_one_reservation ON p06t_reservation(account_id) WHERE status='active'")
                c.execute("""CREATE TABLE p06t_result(account_id TEXT NOT NULL,arena_id TEXT NOT NULL,reservation_id TEXT NOT NULL,
                    results_json TEXT NOT NULL,results_sha256 TEXT NOT NULL,acked INTEGER NOT NULL CHECK(acked IN (0,1)),
                    PRIMARY KEY(account_id,arena_id),UNIQUE(account_id,reservation_id),
                    FOREIGN KEY(account_id,reservation_id) REFERENCES p06t_reservation(account_id,reservation_id))""")
                c.execute("CREATE TABLE p06t_command(account_id TEXT NOT NULL,command_key TEXT NOT NULL,payload_sha256 TEXT NOT NULL,response_json TEXT NOT NULL,response_sha256 TEXT NOT NULL,PRIMARY KEY(account_id,command_key))")
            self._failpoint("after_mixed_schema")
            c.execute("INSERT OR IGNORE INTO p06t_owner VALUES (?,?)", (account_id, aggregate["revision"]))
            self._failpoint("before_mixed_activation_commit"); c.commit()
            return dict(status="active", account_id=account_id, policy_sha256=POLICY_SHA256, ammunition_granted=0)
        except Exception: c.rollback(); raise

    def publish(self,source,account_id,fixture_root):
        self._ammo_loss_fence()
        if self.mixed_active():
            from p06t_mixed_projection import publish_mixed
            return publish_mixed(self,source,account_id,fixture_root)
        return super().publish(source,account_id,fixture_root)

    def freeze_mixed(self, aggregate, native, *, available=True):
        p = self.registry.resolve_selected(aggregate, aggregate["account_id"], native)
        # Purchased T-26/T-34/T-34-85 stay closed unless the account carries the
        # owner's explicit full-stand zero-economy policy (order 2026-10-19).
        require(mixed_admission(p.kind, lambda: self.zero_economy(aggregate["account_id"])), "OWNER_ACCEPTANCE_REQUIRED")
        vehicle = next(r for r in aggregate["vehicles"] if r["vehicle_id"] == self.registry.inventory_id(aggregate["account_id"], native, p.kind))
        if available: require(vehicle["state"] == "available" and vehicle["battle_id"] is None, "VEHICLE_RESERVED")
        members = sorted((r for r in aggregate["crew_inventory"]["members"] if r["vehicle_native_id"] == native), key=lambda r: r["seat"])
        require(len(members) == len(p.crew_roles) and [r["seat"] for r in members] == list(range(len(members)))
            and [r["role"] for r in members] == list(p.primary_roles), "INCOMPLETE_CREW")
        mount = self.mounts[p.assembly_id]
        ammo = next((r for r in aggregate["ammunition"] if r["vehicle_id"] == vehicle["vehicle_id"]), None)
        require(ammo is not None and ammo["mount_id"] == p.assembly_id and set(ammo["loaded"]) == set(mount.shell_ids), "AMMUNITION_UNSUPPORTED")
        rows = [dict(shell_definition_id=key, shell_compact_id=self.shells[key].native_compact_id,
            family=self.shells[key].kind, count=ammo["loaded"][key]) for key in mount.shell_ids]
        require(all(type(r["count"]) is int and 0 <= r["count"] <= p.capacity for r in rows), "CORRUPT_STORE")
        require(1 <= sum(r["count"] for r in rows) <= p.capacity, "AMMUNITION_EMPTY")
        return dict(kind=p.kind, descriptor_hex=p.descriptor_hex, native_inventory_id=native, vehicle_inventory_id=vehicle["vehicle_id"],
            max_hp=p.max_hp, crew_ids=[r["crew_id"] for r in members], capacity=p.capacity,
            ammunition=rows, initial_shell_compact_id=next(r["shell_compact_id"] for r in rows if r["count"]))

    def _active_mixed(self, account):
        if not self._mixed_tables(): return []
        return self.connection.execute("SELECT * FROM p06t_reservation WHERE account_id=? AND status='active' LIMIT 2", (account,)).fetchall()

    def _verify_active(self, aggregate):
        active = self._active_mixed(aggregate["account_id"])
        if not active: return super()._verify_active(aggregate)
        old = self.connection.execute("SELECT 1 FROM p08b_reservation WHERE account_id=? AND status='active'", (aggregate["account_id"],)).fetchone()
        reserved = [r for r in aggregate["vehicles"] if r["state"] == "reserved"]
        require(len(active) == len(reserved) == 1 and old is None, "CORRUPT_STORE")
        row = active[0]; value = self._mixed_reservation(row)
        require(reserved[0]["vehicle_id"] == row["vehicle_inventory_id"] and reserved[0]["battle_id"] == row["battle_id"]
            and self._current_run(aggregate["account_id"]) == row["run_id"]
            and value["frozen"] == self.freeze_mixed(aggregate, row["native_inventory_id"], available=False), "CORRUPT_STORE")

    def _mixed_reservation(self, row):
        require(row is not None, "RESERVATION_MISMATCH")
        f = _json(row["frozen_json"])
        require(len(row["frozen_json"]) <= 4096 and sha(canonical(f)) == row["frozen_sha256"]
            and set(f) == {"kind", "descriptor_hex", "native_inventory_id", "vehicle_inventory_id", "max_hp", "crew_ids", "capacity", "ammunition", "initial_shell_compact_id"}, "CORRUPT_STORE")
        p = self.registry.profiles.get(f["kind"])
        require(p is not None and mixed_admission(p.kind, lambda: self.zero_economy(row["account_id"])) and f["descriptor_hex"] == p.descriptor_hex and f["max_hp"] == p.max_hp
            and type(f["max_hp"]) is int and type(f["capacity"]) is int and f["capacity"] == p.capacity
            and f["native_inventory_id"] == row["native_inventory_id"] and type(f["native_inventory_id"]) is int
            and f["vehicle_inventory_id"] == row["vehicle_inventory_id"] == self.registry.inventory_id(row["account_id"], f["native_inventory_id"], p.kind), "CORRUPT_STORE")
        mount = self.mounts[p.assembly_id]; ammo = f["ammunition"]
        require(type(ammo) is list and len(ammo) == 3, "CORRUPT_STORE")
        for value, key in zip(ammo, mount.shell_ids):
            require(type(value) is dict and set(value) == {"shell_definition_id", "shell_compact_id", "family", "count"}
                and value["shell_definition_id"] == key and type(value["shell_compact_id"]) is int
                and value["shell_compact_id"] == self.shells[key].native_compact_id and value["family"] == self.shells[key].kind
                and type(value["count"]) is int and 0 <= value["count"] <= p.capacity, "CORRUPT_STORE")
        require(1 <= sum(r["count"] for r in ammo) <= p.capacity and type(f["initial_shell_compact_id"]) is int
            and f["initial_shell_compact_id"] == next(r["shell_compact_id"] for r in ammo if r["count"]), "CORRUPT_STORE")
        crew = self.connection.execute("SELECT crew_id,role FROM p04d_crew_member WHERE account_id=? UNION ALL SELECT crew_id,role FROM p04j_retired_member WHERE account_id=?", (row["account_id"], row["account_id"])).fetchall()
        by_id = {r[0]: r[1] for r in crew}
        require(type(f["crew_ids"]) is list and len(f["crew_ids"]) == len(p.crew_roles) and len(set(f["crew_ids"])) == len(f["crew_ids"])
            and all(by_id.get(identity) == role for identity, role in zip(f["crew_ids"], p.primary_roles)), "CORRUPT_STORE")
        result = None
        if row["status"] != "active":
            result = _json(row["result_json"])
            require(sha(canonical(result)) == row["result_sha256"] and set(result) == {"reason", "remaining_ammunition", "consumed_ammunition", "terminal_hp", "destroyed", "repaired_hp", "credits", "xp", "terminal_state"}
                and result["reason"] in REASONS | {"aborted_restart"}, "CORRUPT_STORE")
            expected = self._terminal(f, result["remaining_ammunition"], result["terminal_hp"], result["reason"], terminal_state=result["terminal_state"],abort=result["reason"] == "aborted_restart")
            require(result == expected and row["finished_revision"] > row["admitted_revision"], "CORRUPT_STORE")
        else: require(row["result_json"] is None and row["result_sha256"] is None and row["finished_revision"] is None, "CORRUPT_STORE")
        require(row["admitted_revision"] == row["source_revision"] + 1, "CORRUPT_STORE")
        return {key: row[key] for key in ("reservation_id", "run_id", "battle_id", "native_inventory_id", "vehicle_inventory_id", "status")} | dict(frozen=f, frozen_sha256=row["frozen_sha256"], result=result)

    def _terminal(self,frozen, remaining, hp, reason, *, terminal_state=None,abort=False):
        original = frozen["ammunition"]
        require(type(remaining) is list and len(remaining) == 3, "INVALID_RESULT")
        for after, before in zip(remaining, original):
            require(type(after) is dict and set(after) == {"shell_compact_id", "count"}
                and type(after["shell_compact_id"]) is int and after["shell_compact_id"] == before["shell_compact_id"]
                and type(after["count"]) is int and 0 <= after["count"] <= before["count"], "INVALID_RESULT")
        require((abort and hp is None and reason == "aborted_restart" and all(a["count"] == b["count"] for a,b in zip(remaining, original)))
            or (not abort and type(hp) is int and 0 <= hp <= frozen["max_hp"] and reason in REASONS), "INVALID_RESULT")
        if abort:require(terminal_state is None,"INVALID_RESULT")
        else:terminal_state=self.terminal_policy.validate(canonical(terminal_state).decode("ascii"),frozen=frozen,terminal_hp=hp)
        return dict(reason=reason, remaining_ammunition=remaining,
            consumed_ammunition=[dict(shell_compact_id=b["shell_compact_id"], count=b["count"]-a["count"]) for a,b in zip(remaining, original)],
            terminal_hp=hp, destroyed=None if abort else hp == 0 or not terminal_state["crew_active"], repaired_hp=frozen["max_hp"], credits=0, xp=0,terminal_state=terminal_state)

    def _finish_mixed(self, request, aggregate, row, *, abort=False):
        f = self._mixed_reservation(row)["frozen"]; c = self.connection; account = request["account_id"]
        remaining = [dict(shell_compact_id=r["shell_compact_id"], count=r["count"]) for r in f["ammunition"]] if abort else request["remaining_ammunition"]
        result = self._terminal(f, remaining, None if abort else request["terminal_hp"], "aborted_restart" if abort else request["reason"],
            terminal_state=None if abort else _json(request["terminal_state_json"]),abort=abort)
        layout = self.layouts(account)[row["native_inventory_id"]]
        counts = {r["shell_compact_id"]: r["count"] for r in remaining}
        loaded = {r["shell_definition_id"]: counts[r["shell_compact_id"]] for r in f["ammunition"]}
        require(c.execute("UPDATE p09c_ammo_mount SET loaded_json=? WHERE account_id=? AND vehicle_id=?", (canonical(loaded).decode("ascii"), account, row["vehicle_inventory_id"])).rowcount == 1, "CORRUPT_STORE")
        for i in (0,2,4): layout[i+1] = counts[abs(layout[i])]
        require(c.execute("UPDATE p09d_native_layout SET layout_json=? WHERE account_id=? AND native_vehicle_id=?", (json.dumps(layout), account, row["native_inventory_id"])).rowcount == 1, "CORRUPT_STORE")
        require(c.execute("UPDATE game_vehicle SET state='available',battle_id=NULL WHERE account_id=? AND vehicle_id=? AND state='reserved' AND battle_id=?", (account, row["vehicle_inventory_id"], row["battle_id"])).rowcount == 1, "RESERVATION_MISMATCH")
        raw = canonical(result).decode("ascii")
        c.execute("UPDATE p06t_reservation SET status=?,result_json=?,result_sha256=?,finished_revision=? WHERE account_id=? AND reservation_id=?",
            ("aborted_restart" if abort else "finished", raw, sha(raw.encode("ascii")), aggregate["revision"]+1, account, row["reservation_id"]))
        self._failpoint("after_mixed_result")
        receipt = self._mixed_reservation(c.execute("SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?", (account,row["reservation_id"])).fetchone())
        if not abort and result["reason"] == "battle_finished":
            value = results_value(request["results_json"]); arena = request["battle_id"].rsplit(":",1)[1]
            self._match_mixed_result(value, receipt, request["native_database_id"], arena)
            require(not self._arena_has_result(account,arena), "RESULT_MISMATCH")
            raw = canonical(value).decode("ascii")
            c.execute("INSERT INTO p06t_result VALUES (?,?,?,?,?,0)", (account,arena,row["reservation_id"],raw,sha(raw.encode("ascii"))))
            self._failpoint("after_mixed_full_result")
        return receipt

    def _arena_has_result(self,account,arena):
        # Original native results cache keys by arena, without a writer-contract
        # version. Separate SQL tables must not permit ambiguous cache keys.
        for table in ("p08c_result","p06t_result"):
            if self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone():
                if self.connection.execute("SELECT 1 FROM "+table+" WHERE account_id=? AND arena_id=?",(account,arena)).fetchone():return True
        return False

    def _record_natural_result(self,request,reservation):
        arena=request["battle_id"].rsplit(":",1)[1]
        if self._mixed_tables():
            require(self.connection.execute("SELECT 1 FROM p06t_result WHERE account_id=? AND arena_id=?",(request["account_id"],arena)).fetchone() is None,"RESULT_MISMATCH")
        return super()._record_natural_result(request,reservation)

    def _match_mixed_result(self, value, reservation, native, arena):
        own = next((p for p in value["participants"] if p["account_dbid"] == native), None)
        f, result = reservation["frozen"], reservation["result"]
        require(value["arena_id"] == int(arena) and own is not None and own["type_compact_descr"] == self.registry.profiles[f["kind"]].type_compact_id
            and own["health"] == result["terminal_hp"] <= f["max_hp"]
            and own["shots"] == sum(r["count"] for r in result["consumed_ammunition"]), "RESULT_MISMATCH")
        state=self.terminal_policy.validate(canonical(result["terminal_state"]).decode("ascii"),frozen=f,terminal_hp=result["terminal_hp"],results=value)
        killer=state["death"]["killer_slot"]
        require(own["death_reason"]==state["death"]["reason"] and own["killer_id"]==(0 if killer is None else value["participants"][killer]["vehicle_id"]),"RESULT_MISMATCH")

    def _mixed_reply(self, request, revision, status, reservation=None, legacy=None, *, code=None, replayed=False):
        value = {key: request[key] for key in ("version","operation","account_id","native_database_id","command_key","run_id")}
        value.update(source_revision=request["expected_revision"], revision=revision, status=status, replayed=replayed,
            code=code, reservation=reservation, legacy_reservation=legacy, policy_sha256=POLICY_SHA256)
        require(len(canonical(value)) <= MAX_REPLY, "PROFILE_TOO_LARGE"); return value

    def battle(self, request, *, authenticated_account_id):
        self._ammo_loss_fence()
        if type(request) is dict and request.get("version") == 2:
            return self.battle_mixed(request, authenticated_account_id=authenticated_account_id)
        require(not self._active_mixed(authenticated_account_id), "MIXED_RESERVATION_ACTIVE")
        return super().battle(request, authenticated_account_id=authenticated_account_id)

    def battle_mixed(self, request, *, authenticated_account_id):
        self._ammo_loss_fence()
        request = validate_request(request, authenticated_account_id)
        account,key,operation = request["account_id"],request["command_key"],request["operation"]
        require(account == self.pool_account and self.mixed_active(), "P06T_ACTIVATION_REQUIRED")
        c = self.connection; c.execute("BEGIN" if operation == "inspect" else "BEGIN IMMEDIATE")
        try:
            aggregate = self.read_profile(account); revision = aggregate["revision"]
            require(self._project_profile(account,aggregate)["native_database_id"] == request["native_database_id"], "FOREIGN_ACCOUNT")
            current = self._current_run(account)
            seen = c.execute("SELECT status FROM p08b_run WHERE account_id=? AND run_id=?", (account,request["run_id"])).fetchone()
            if operation != "inspect":
                if operation == "run_open": require(seen is None or seen[0] == "active", "RUN_FENCED")
                else: require(current is not None, "RUN_NOT_OPEN"); require(current == request["run_id"], "RUN_FENCED")
            payload = sha(canonical(dict(schema=SCHEMA,policy_sha256=POLICY_SHA256,request=request))); command = SCHEMA+":"+operation
            ledger = c.execute("SELECT * FROM game_command_ledger WHERE account_id=? AND command_id=?", (account,key)).fetchone()
            if ledger is not None and operation != "inspect":
                require(ledger["command_type"] == command and ledger["payload_sha256"] == payload, "DUPLICATE_PAYLOAD_MISMATCH")
                journal = _json(ledger["result_json"])
                require(sha(canonical(journal)) == ledger["p09c_result_sha256"] and set(journal) == {"schema","request","response"}
                    and journal["schema"] == SCHEMA and journal["request"] == request, "CORRUPT_STORE")
                saved = journal["response"]; reservation = saved["reservation"]; legacy = saved["legacy_reservation"]
                require(saved["source_revision"] == ledger["source_revision"] == request["expected_revision"]
                    and saved["revision"] == ledger["destination_revision"] <= revision, "CORRUPT_STORE")
                if reservation is not None:
                    row = c.execute("SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?", (account,reservation["reservation_id"])).fetchone()
                    if operation == "admit": require(row is not None and row["status"] == "active", "RESERVATION_TERMINAL")
                    require(self._mixed_reservation(row) == reservation, "CORRUPT_STORE")
                if legacy is not None:
                    row = c.execute("SELECT * FROM p08b_reservation WHERE account_id=? AND reservation_id=?", (account,legacy["reservation_id"])).fetchone()
                    require(self._reservation(row) == legacy and legacy["status"] == "aborted_restart", "CORRUPT_STORE")
                require(saved == self._mixed_reply(request,ledger["destination_revision"],{"run_open":"ready","admit":"admitted","finish":"finished"}[operation],reservation,legacy)
                    and ledger["destination_revision"] in ((ledger["source_revision"],ledger["source_revision"]+1) if operation == "run_open" else (ledger["source_revision"]+1,)), "CORRUPT_STORE")
                if operation == "finish" and request["reason"] == "battle_finished": self._read_mixed_result(account,request["native_database_id"],request["battle_id"].rsplit(":",1)[1])
                c.commit(); return dict(saved,replayed=True)
            active = self._active_mixed(account)
            old = c.execute("SELECT * FROM p08b_reservation WHERE account_id=? AND status='active'", (account,)).fetchone()
            if operation == "inspect":
                result = self._mixed_reply(request,revision,"inspected",self._mixed_reservation(active[0]) if active else None,self._reservation(old) if old else None)
                c.commit(); return result
            require(revision == request["expected_revision"], "STALE_REVISION"); require(revision < 2**31-1, "REVISION_EXHAUSTED")
            public = c.execute("SELECT profile_json FROM game_profiles WHERE account_id=?", (account,)).fetchone()[0]
            reservation,legacy,destination = None,None,revision+1
            if operation == "run_open":
                if current == request["run_id"]:
                    require(old is None, "RUN_HAS_LEGACY_RESERVATION"); destination = revision
                else:
                    if active: reservation = self._finish_mixed(request,aggregate,active[0],abort=True)
                    if old: legacy = self._finish(request,aggregate,old,abort=True)
                    c.execute("UPDATE p08b_run SET status='retired' WHERE account_id=? AND status='active'", (account,))
                    c.execute("INSERT INTO p08b_run VALUES (?,?,'active')", (account,request["run_id"]))
                    self._failpoint("after_mixed_run")
                status = "ready"
            elif operation == "admit":
                require(not active and old is None, "VEHICLE_RESERVED")
                require(c.execute("SELECT 1 FROM p06t_reservation WHERE account_id=? AND battle_id=?", (account,request["battle_id"])).fetchone() is None
                    and c.execute("SELECT 1 FROM p08b_reservation WHERE account_id=? AND battle_id=?", (account,request["battle_id"])).fetchone() is None, "RESERVATION_TERMINAL")
                frozen = self.freeze_mixed(aggregate,request["native_inventory_id"]); raw = canonical(frozen).decode("ascii")
                require(c.execute("UPDATE game_vehicle SET state='reserved',battle_id=? WHERE account_id=? AND vehicle_id=? AND state='available'", (request["battle_id"],account,frozen["vehicle_inventory_id"])).rowcount == 1, "VEHICLE_RESERVED")
                self._failpoint("after_mixed_vehicle")
                c.execute("INSERT INTO p06t_reservation VALUES (?,?,?,?,?,?,'active',?,?,?,?,NULL,NULL,NULL)", (account,key,request["run_id"],request["battle_id"],request["native_inventory_id"],frozen["vehicle_inventory_id"],raw,sha(raw.encode("ascii")),revision,destination))
                reservation = self._mixed_reservation(c.execute("SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?", (account,key)).fetchone())
                self._failpoint("after_mixed_reservation"); status = "admitted"
            else:
                row = c.execute("SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?", (account,request["reservation_id"])).fetchone()
                require(row is not None and row["run_id"] == request["run_id"] and row["battle_id"] == request["battle_id"] and row["native_inventory_id"] == request["native_inventory_id"], "RESERVATION_MISMATCH")
                require(row["status"] == "active", "RESERVATION_TERMINAL")
                reservation = self._finish_mixed(request,aggregate,row); status = "finished"
            if destination != revision: self._save_crew_projection(account,destination,public)
            response = self._mixed_reply(request,destination,status,reservation,legacy)
            raw = canonical(dict(schema=SCHEMA,request=request,response=response))
            require(len(raw) <= MAX_RESULT_REQUEST, "PROFILE_TOO_LARGE")
            c.execute("INSERT INTO game_command_ledger VALUES (?,?,?,?,?,?,?,?)", (account,key,command,payload,revision,destination,raw.decode("ascii"),sha(raw)))
            self._failpoint("after_mixed_ledger"); self.read_profile(account); self._failpoint("before_mixed_commit")
            c.commit(); return response
        except Exception: c.rollback(); raise

    def _read_mixed_result(self, account, native, arena):
        row = self.connection.execute("SELECT * FROM p06t_result WHERE account_id=? AND arena_id=?", (account,arena)).fetchone()
        require(row is not None, "RESULT_NOT_READY")
        require(type(row["results_json"]) is str and len(row["results_json"].encode("utf8")) <= MAX_RESULT_BYTES
            and sha(row["results_json"].encode("ascii")) == row["results_sha256"], "CORRUPT_STORE")
        value = results_value(row["results_json"])
        reservation = self._mixed_reservation(self.connection.execute("SELECT * FROM p06t_reservation WHERE account_id=? AND reservation_id=?", (account,row["reservation_id"])).fetchone())
        require(reservation["status"] == "finished" and reservation["result"]["reason"] == "battle_finished"
            and reservation["battle_id"] == reservation["run_id"]+":"+arena, "RESULT_MISMATCH")
        self._match_mixed_result(value,reservation,native,arena)
        return row

    def results_mixed(self, request, *, authenticated_account_id):
        self._ammo_loss_fence()
        request=validate_results_request(request,authenticated_account_id)
        account = request["account_id"]; require(account == authenticated_account_id == self.pool_account and self.mixed_active(), "FOREIGN_ACCOUNT")
        _bounded_id(request["command_key"],"command_key"); _integer(request["native_database_id"],1)
        arena = request["arena_id"]
        require(type(arena) is str and arena.isascii() and arena.isdecimal() and arena[0] != "0" and len(arena) <= 19 and int(arena) <= 2**63-1, "INVALID_INPUT")
        c = self.connection; c.execute("BEGIN IMMEDIATE" if request["operation"] == "ack" else "BEGIN")
        try:
            aggregate = self.read_profile(account); require(self._project_profile(account,aggregate)["native_database_id"] == request["native_database_id"], "FOREIGN_ACCOUNT")
            try:row = self._read_mixed_result(account,request["native_database_id"],arena)
            except TransactionError as error:
                if error.code!="RESULT_NOT_READY":raise
                row=None
            value=self._mixed_results_reply(request,"missing"if row is None else"found"if request["operation"]=="query"else"acked",row)
            if request["operation"] == "ack":
                payload = sha(canonical(request)); saved = c.execute("SELECT * FROM p06t_command WHERE account_id=? AND command_key=?", (account,request["command_key"])).fetchone()
                if saved is not None:
                    require(saved["payload_sha256"] == payload, "DUPLICATE_PAYLOAD_MISMATCH")
                    result = _json(saved["response_json"]); require(sha(canonical(result)) == saved["response_sha256"] and result == dict(value,acked=True), "CORRUPT_STORE")
                    c.commit(); return dict(result,replayed=True)
                if row is not None:
                    c.execute("UPDATE p06t_result SET acked=1 WHERE account_id=? AND arena_id=?", (account,arena)); value["acked"] = True
                    raw = canonical(value); c.execute("INSERT INTO p06t_command VALUES (?,?,?,?,?)", (account,request["command_key"],payload,raw.decode("ascii"),sha(raw)))
                    self._failpoint("before_mixed_ack_commit")
            c.commit(); return value
        except Exception: c.rollback(); raise

    @staticmethod
    def _mixed_results_reply(request,status,row=None,*,code=None,replayed=False):
        value={key:request[key]for key in("version","operation","account_id","native_database_id","command_key","arena_id")}
        value.update(status=status,acked=bool(row["acked"])if row else False,results_json=row["results_json"]if row else None,
            replayed=replayed,code=code,policy_sha256=POLICY_SHA256)
        require(len(canonical(value))<=MAX_RESULT_REQUEST,"PROFILE_TOO_LARGE");return value


def results_service_mixed(store,request,*,authenticated_account_id):
    request=validate_results_request(request,authenticated_account_id)
    try:return store.results_mixed(request,authenticated_account_id=authenticated_account_id)
    except TransactionError as error:
        if error.code not in {"RESULT_MISMATCH","DUPLICATE_PAYLOAD_MISMATCH"}:raise
        return store._mixed_results_reply(request,"rejected",code=error.code)
